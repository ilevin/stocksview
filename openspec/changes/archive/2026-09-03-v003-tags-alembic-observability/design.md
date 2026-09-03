# v0.03 技术设计：标签系统、Alembic 迁移与可观测性

> 设计依据：`StocksView_v0.03_技术方案设计.md`（下称"技术方案"，§n 指其章节）与 2026-09-01 代码库调研。

## Context

v0.02（tag v0.02，容器 `stock-dashboard`，线上 http://23.94.2.230:8765，手动 docker run，挂载 `./data:/app/data` 与 `config.yaml`）现状关键事实：

- **数据层**：7 个模型注册于 `app/models/__init__.py`，`Base` 在 `app/db.py:14`（无 MetaData naming_convention，约束手工命名如 `uq_watchlist_instrument`）。`Watchlist`（`app/models/watchlist.py:17`）仅 id/instrument_id(FK)/sort_order/created_at；全库无 relationship()、无 ondelete、无 PRAGMA foreign_keys。建表唯一生产入口是 lifespan 内 `init_db(engine)` = `Base.metadata.create_all`（`app/main.py:50`）。
- **API 层**：`app/api/{quotes,watchlist,index_watchlist,admin}.py` 四个路由。watchlist 全部端点以 **instrument_id** 寻址（`DELETE /api/watchlist/{instrument_id}`），`WatchlistItem` 响应（`app/schemas/__init__.py`）不含自选行自增 id。错误处理：service 抛业务异常 → `_error_status()`（`app/api/watchlist.py:37`）映射 409/404/422/500。`GET /api/quotes` 无查询参数，`_assemble`（`app/api/quotes.py:25-111`）绕过 service 直查 repo。`/health`（`app/main.py:129`）返回 `{status, database}`。
- **Job**：纯 asyncio 循环（无 APScheduler）。`QuoteRefreshJob._run` 每 `config.quote.refresh_seconds`(60s) `asyncio.to_thread(refresh_service.tick)`；`FundamentalRefreshJob._maybe_run` 每 30min。异常仅日志，无任何状态持久化。Last Known Good 由 `QuoteCache`（`app/services/quote_cache.py`）实现：只 update 本轮成功标的。
- **Provider**：`QuoteProviderRegistry`（`app/providers/quote/__init__.py:18`）按 (market, asset_type) 分组调用，单组异常隔离。Tencent httpx timeout=10.0 硬编码（`tencent.py:38`）；AKShare `ak.stock_zh_a_spot_tx()` **无超时**（内部 requests 不受控）；Tushare `ts.pro_api(token)` **未传 timeout**（SDK 默认 30s，支持 `pro_api(token, timeout=X)`）。无异常分类、无任何计时/计数代码。
- **前端**：仅 `index.html`/`watchlist.html` 两个独立模板（无 base.html），`app/static/app.js`（289 行）按 `body[data-page]` 分发 init 函数；无任何筛选控件、无 footer；Jinja2 无全局 context 注入。
- **测试**：unit 9 文件 + integration 2 文件，无 conftest.py；内存 SQLite + `init_db` 建表；`tests/integration/test_fault_tolerance.py:114` **精确断言** `/health` body（v0.03 加 version 后必改）。`pytest -m "not online"` 当前 107 passed。
- **部署**：Dockerfile 只 `COPY app ./app` + pyproject/README，`CMD uvicorn`；无 alembic 依赖（环境与 pyproject 均无）。git 仅有 dev 分支，tag v0.01/v0.02。pyproject `version = "1.1.0"` 与应用版本体系脱节。
- **约束**：线上 v0.02 容器与库在用，开发调试必须用新镜像/新容器/临时数据路径/新端口隔离；后台仅 OPEN 刷新策略不动（v0.02 已冻结边界）。

## Goals / Non-Goals

**Goals:**

- G1 标签：tag 表 + Watchlist.tag_id 关联 + 标签 CRUD/管理页 + 引用保护（业务层 409 + DB 约束双层）。
- G2 行情页按标签筛选（全部/指定/无标签），筛选不增加任何 Provider 请求；底部版本号。
- G3 Alembic：0001_v002 基线 + 0002_v003 增量，启动自动 upgrade，失败阻止启动；v0.02 库无损升级。
- G4 JobStatus：job_status 表记录两个后台 Job 的 last-success 等状态，`GET /api/admin/status` 可查。
- G5 Provider：三源 timeout 配置化 + 统一 metrics（request/success/error/timeout/耗时），error 与 timeout 分开。

**Non-Goals:**

- 不改整体架构（不拆服务、不加 Redis/MQ/独立任务服务）。
- 不做标签多对多（一个自选条目最多一个标签）、不支持在证券编辑处新建标签（技术方案 §8）。
- 不做 Provider metrics 持久化/长期趋势（Prometheus/Grafana 明确推迟，§31）；不做监控页面（§26）。
- 不动 OPEN 刷新策略与即时刷新边界（v0.02 冻结）。
- 不抽 base.html 模板重构（v0.03 改动面已大，避免回归面扩大；三页各自加导航入口、index 加 footer 即可）。
- 不给指数加标签。

## Decisions

### D1: 标签关系挂在 Watchlist，表名 `tag`（单数）

技术方案 §5 已论证挂 Watchlist 而非 Instrument，确认采纳：现有 `Watchlist.instrument_id` 已是 FK 引用模式（`app/models/watchlist.py:17`），加 `tag_id` 顺延。

**表名从技术方案的"tags"调整为 `tag`**：现有 7 张表全部单数（instrument/watchlist/index_watchlist/quote_snapshot/fundamental_snapshot/app_setting/trading_calendar），schema 命名一致性优先于文档字面（技术方案 §34 的代码结构同样写 `models/tag.py` 单数）。新模型 `app/models/tag.py`：`id PK`、`name VARCHAR(50) NOT NULL`（unique，约束名 `uq_tag_name`）、`created_at/updated_at DateTime default/onupdate utcnow`——时间列沿用 Watchlist 的裸 `DateTime` 风格（不引入新不一致）。`job_status` 表名按技术方案 §23 原样（复合词无单复数问题）。

### D2: 关联 API 遵循现有 instrument_id 寻址惯例（v0.03b 修订：多对多）

**需求修订（2026-09-02，用户澄清）**：原始需求“股票、etf 和标签的关系是 1 对多”指**一个自选条目可关联多个标签**（标签与自选条目为多对多），技术方案 §1.1 第 5 条“一个股票或 ETF 最多关联一个标签”系对需求的收窄，予以推翻。修订内容：

- 数据模型：新增 `watchlist_tag` 关联表（watchlist_id FK ON DELETE CASCADE、tag_id FK ON DELETE RESTRICT、`uq_watchlist_tag` 联合唯一），`watchlist.tag_id` 单列经 `0003` 迁移移除（既有单标签数据先搬入关联表，零丢失）；迁移 `0003_v003b_watchlist_tags_table`。
- API：`PATCH /api/watchlist/{instrument_id}/tag` 改为 **`PUT /api/watchlist/{instrument_id}/tags`**，body `{"tag_ids": [int...]}`（全量替换语义，幂等）；响应与行情/自选列表的 `tag` 字段改为 **`tags: [{id,name}]` 数组**。
- 其余语义不变：指数不支持标签、usage_count 按 watchlist_tag 行计数、被引用标签禁止删除（任一关联存在即 409）、筛选 tag_id 命中“包含该标签”的条目、untagged 为无任何标签。
- 校验顺序沿用：先判 instrument 的 asset_type（INDEX→400），再查自选行（404）、各 tag_id 存在（404）。

技术方案 §10 写 `PATCH /api/watchlist/{watchlist_id}/tag`，但现有 watchlist API 全部以 instrument_id 寻址，`WatchlistItem` 响应不含自选行自增 id——前端根本拿不到 watchlist_id，故继续以 instrument_id 寻址。

### D3: 标签 CRUD 与错误码沿用现有异常→状态码映射模式

新增 `TagService`（`app/services/tag_service.py`）+ `TagRepository`（或直接走 session，参照 AppSetting 的轻量模式——经 Repository 层保持三层一致，`app/repositories/tag.py`）。异常 `TagNameEmptyError`/`TagNameTooLongError`/`DuplicateTagNameError`/`TagInUseError`/`TagNotFoundError`，路由 `_error_status` 同款映射：201 创建 / 200 修改 / 204 删除 / 409 重名与被引用删除 / 404 不存在 / 422 校验。名称校验：strip 后非空、≤50 字符、唯一（service 层查重 + DB unique 兜底）。`GET /api/tags` 返回 `[{id, name, usage_count}]`，usage_count 用 `watchlist.tag_id` 计数（LEFT JOIN/GROUP BY，不数 index_watchlist——指数无标签）。

### D4: 删除保护 = 业务层计数检查 + DB FK 双层，开启 PRAGMA foreign_keys

技术方案 §7 要求双层保护。现状 SQLAlchemy engine 未开 `PRAGMA foreign_keys`，FK 只是声明。v0.03：①`watchlist.tag_id` 声明 `ForeignKey("tag.id", ondelete="RESTRICT")`；②`create_db_engine` 加 connect 事件开启 PRAGMA foreign_keys=ON，让 DB 约束真正生效。风险评估：全库仅两处既有 FK（watchlist/index_watchlist → instrument.instrument_id），且不存在删除 Instrument 的代码路径， enforcement 开启无既有行为破坏。业务层 `TagService.delete` 先计数并抛 `TagInUseError`→409（友好中文文案，技术方案 §7 示例），DB 约束作为绕过业务层时的兜底（IntegrityError → 500 兜底）。不做"删标签自动解除关联"（技术方案 §7 明令禁止）。

### D5: Alembic 集成——手写迁移、env.py 复用应用配置与 metadata

- 目录：根目录 `alembic.ini` + `alembic/{env.py,script.py.mako,versions/}`（技术方案 §16）。`env.py` 不独立维护配置：`from app.config import load_config` 取 `database.url`（与运行时同源），`from app.db import Base` + `import app.models` 作 target_metadata（autogenerate 支持后续演进）。
- 版本文件：`versions/0001_v002_baseline.py`（手写 v0.02 全部 7 张表 create_table，以线上 `data/market.db` 真实 schema 逐表核对，不 import 当前模型——模型已含 v0.03 新表）+ `versions/0002_v003_tags_and_job_status.py`（建 tag、job_status 表；`watchlist` 加 `tag_id`）。revision id 用语义名（`0001_v002_baseline`/`0002_v003`，技术方案 §16-17），down_revision 链式。
- 启动接管：`Dockerfile` CMD 改 `["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]`（技术方案 §20，迁移失败容器退出）；`app/main.py` lifespan **移除 `init_db(engine)` 调用**（生产 schema 唯一由迁移决定，防止 create_all 掩盖迁移遗漏导致 schema 漂移——技术方案 §21）；`init_db` 函数保留供测试使用（6 处测试显式调用不受影响）。本地启动 README 改为 `alembic upgrade head && uvicorn app.main:app`。
- `Dockerfile` 增加 `COPY alembic.ini ./` + `COPY alembic ./alembic`；pyproject 加 `alembic>=1.13` 依赖。
- 一致性防护：新增迁移测试断言 `upgrade head` 后的 schema 与 `Base.metadata.create_all`（当前模型）inspect 比对一致（表集合/列名/类型/nullability），防迁移与模型漂移。

### D6: v0.02→v0.03 升级流程含 stamp 基线（技术方案未覆盖的关键补充）

线上 v0.02 库有表但**没有 `alembic_version` 表**，直接 `alembic upgrade head` 会在 0001 建表时报"表已存在"失败。升级流程（README + CHANGELOG 记录）：

```text
1. 停旧容器；备份 data/market.db
2. 用新镜像跑一次性容器：
   docker run --rm -v ./data:/app/data -v ./config.yaml:/app/config.yaml:ro \
     stock-dashboard:v0.03 alembic stamp 0001_v002_baseline
   （已有 v0.02 结构的库打基线标记，不执行 DDL）
3. 启动正式容器：CMD 内 alembic upgrade head 只执行 0002（建 tag/job_status、加 watchlist.tag_id），成功后启动 uvicorn
```

空库（全新部署）则无需 stamp，upgrade head 从 0001 全链执行。弃用"启动脚本自动检测并 stamp"方案：魔法行为掩盖状态、排障困难；显式运维步骤 + 启动失败即退出（数据无损）更可控。回滚：恢复备份 db + 切回 v0.02 镜像（v0.03 新表/新列对 v0.02 代码不可见，不恢复备份也可运行，但以备份恢复为准）。

### D7: watchlist 加列用 batch_alter_table

`0002` 中 `watchlist` 加 `tag_id` 用 `op.batch_alter_table("watchlist")`（技术方案 §18：SQLite 下外键/约束变更走 batch 重建），显式在 batch 上下文重建 FK 与 `uq_watchlist_instrument`。batch 反射重建有丢约束风险 → 迁移测试在 upgrade 后用 inspect 断言列/索引/唯一约束齐全 + 原有行数与数据不变（技术方案 §36.3：四类数据不丢、全部 tag_id=NULL）。

### D8: JobStatus——job_name 主键单行 upsert，包装在 Job 循环体

`app/models/job_status.py`：`job_name VARCHAR(64) PK`、`last_started_at`/`last_success_at`/`last_error_at` DateTime null、`last_error TEXT null`、`last_duration_ms INTEGER null`、`consecutive_failures INTEGER NOT NULL DEFAULT 0`、`updated_at` onupdate。`JobStatusService`（`app/services/job_status_service.py`）提供 `record_started(job_name)` / `record_success(job_name, duration_ms)` / `record_failure(job_name, duration_ms, error)`，内部 upsert（GET + UPDATE/INSERT），短 session 即开即关。语义（技术方案 §24）：失败不清 `last_success_at`；成功清零 `consecutive_failures`；duration 从 record_started 时刻计。

接入点：`QuoteRefreshJob._run` 循环体内 wrap `tick`（started → try: success / except: failure, re-raise 原有日志逻辑）；`FundamentalRefreshJob._run` 同理 wrap `_maybe_run`。"执行完成无异常 = 成功"（包括无 token / 无缺失标的等空转场景）——Job 状态回答"任务是否正常运转"，Provider 健康由 metrics 回答（D10），两者分离正是 v0.03 意图。手动刷新端点（`POST /api/admin/refresh/*`）不写 job_status（技术方案 §25 仅要求两个后台 Job）。`JobStatusService` 自身异常吞掉记日志——**观测设施故障不得拖垮刷新主流程**。Job 构造注入 `session_factory`（FundamentalRefreshJob 已持有；QuoteRefreshJob 经 RefreshService 转发或直接注入 session_factory）。

### D9: /api/admin/status 响应结构

`app/api/status.py`（router prefix `/api/admin`）新增 `GET /api/admin/status`（技术方案 §26/§33）：

```json
{
  "version": "v0.03",
  "jobs": {"quote_refresh": {"last_started_at": "...", "last_success_at": "...", "last_error_at": "...", "last_error": null, "last_duration_ms": 1280, "consecutive_failures": 0}},
  "providers": {"tencent": {"request_count": 0, "success_count": 0, "error_count": 0, "timeout_count": 0, "last_success_at": null, "last_error_at": null, "last_error": null, "last_duration_ms": null}}
}
```

时间字段统一北京时间 ISO 带时区（现有 API 约定）。无数据（未跑过）返回 null 字段而非缺键。

### D10: Provider timeout 分层实现，统一 ProviderMetrics 包装

**timeout 传递**（各 provider 原生能力不同，分层处理）：
- Tencent：`TencentQuoteClient(timeout=...)` 由 `QuoteProviderRegistry` 构造时从 config 注入（替换 `tencent.py:38` 硬编码 10.0）。
- Tushare：`ts.pro_api(token, timeout=X)`（SDK 原生支持）。
- AKShare：**无原生 timeout**（`ak.stock_zh_a_spot_tx()` 内部 requests 不受控）→ 线程级超时：`concurrent.futures.ThreadPoolExecutor.submit(...).result(timeout=N)`，超时抛 `concurrent.futures.TimeoutError`；**`shutdown(wait=False)` 放弃线程**（避免 with 块 join 卡死整个刷新周期），被放弃线程随 HTTP 自然结束。这是唯一需要线程包装的 provider。

**统一包装层** `app/observability/provider_metrics.py`：`ProviderMetrics` dataclass（request/success/error/timeout 计数 + last_success_at/last_error_at/last_error/last_duration_ms，技术方案 §29）+ `ProviderMetricsRegistry`（按 source 名索引的内存单例，挂 `app.state.provider_metrics`）+ `call_with_metrics(source, fn, *args, timeout=None)` 同步包装函数：monotonic 计时；异常分类——`concurrent.futures.TimeoutError`/`httpx.TimeoutException`/`requests.exceptions.Timeout`/内置 `TimeoutError` → timeout 类；其余 Exception → error 类；超时/错误均向上抛（由调用方按既有容错处理），成功返回结果并记 success。

**挂点**（对齐技术方案 §32 的 RefreshService→包装层→Provider）：
- 行情：`QuoteProviderRegistry.get_quotes` 每组 `provider.get_quotes(...)` 调用包一层 `call_with_metrics(source, ..., timeout=config)`（分组级统计，覆盖周期刷新与添加自选即时刷新两条路径；timeout 传参使 AKShare 获得线程超时，Tencent 双保险无害——httpx 先到即先抛）。单组失败隔离行为不变（timeout/error 异常照常被 except 捕获，failed 计数、缓存保留 LKG、下周期重试——技术方案 §28 由现有机制天然满足）。
- 估值：main.py 构造处包 `TushareFundamentalProvider`（装饰器/组合类 `TimedFundamentalProvider`），`get_fundamentals` 内每次 `_pro()` 调用级或方法级统计——**方法级**（一次 get_fundamentals 一次计数，与行情分组级粒度对齐，简单且足够）。
- 名称识别（Tencent client 复用）**不纳入** metrics：低频一次性调用，保持简单（design 层明确排除）。

Provider 实例化改造：`QuoteProviderRegistry(config)` 构造 provider 时把 `config.providers.timeout` 传入 Tencent client；akshare 的 timeout 由包装层在调用时生效。重启清零（内存指标，技术方案 §31 接受）。

### D11: 配置扩展 `providers.timeout` 节

现有 `ProvidersConfig`（`app/config.py:50`）仅 quote/fundamental 两子节。新增 `TimeoutConfig {tencent: float = 8, akshare: float = 15, tushare: float = 15}`（单位秒，默认值即技术方案 §27 建议值），挂在 `providers.timeout`。不采用技术方案字面的 `providers.tencent.timeout_seconds` 平铺结构——现有 providers 节语义是"source 选择配置"，平铺会混杂两种语义；独立 timeout 子节向后兼容（全部带默认值，旧 config.yaml 无该节也能跑）。`config.example.yaml` 同步补示例。

### D12: 行情筛选——API 参数 + 前端本地过滤

**API**（技术方案 §12）：`GET /api/quotes` 加 `tag_id: int | None = None` 与 `untagged: bool = False` 查询参数（FastAPI Query）。`_assemble` 中 watchlist 行已含 tag_id（模型加列后自然带出），过滤在 Python 层对组装结果按 `watchlist_row.tag_id == tag_id` / `== None` 过滤（行数 ≤ 自选数，内存过滤零成本，不动 `WatchlistRepository.list_ordered()` 泛型基类——避免波及 index_watchlist 共用代码）。两参数同传时 422（互斥校验）。`QuoteItem` 加 `tag: {id, name} | None`（tag 名称经一次 tag 表查询建 id→name 映射）。`/api/quotes` 永远只读缓存不触发 Provider（现状即如此）——"筛选不增加 Provider 请求"在 API 层天然成立。

**前端**：行情页自选 panel 顶部加筛选下拉（`全部 / 无标签 / <各标签>`，选项来自页面加载时一次 `GET /api/tags`）；切换时**本地过滤已渲染数据**（零 HTTP 请求、零延迟），筛选状态存 JS 变量，60s 轮询重渲染后自动重新应用。备选"每次切换带 query 参数重新 fetch"被弃用：多一次请求且延迟明显，本地过滤体验更优；API 参数能力保留（供 API 使用者与测试验证服务端过滤正确性）。

### D13: 版本——app/version.py 单一来源，Jinja2 env.globals 注入

`app/version.py`：`APP_VERSION = "v0.03"`。`main.py` 创建 templates 后 `templates.env.globals["app_version"] = APP_VERSION`（一处注入，全部模板可用，无需 context processor）。`index.html` 底部加 `<footer>` 显示 `StocksView v0.03`（`StocksView {{ app_version }}`，不硬编码版本到 HTML——技术方案 §13）。`/health` 响应加 `"version": APP_VERSION`（保持 JSONResponse 手拼模式）。`pyproject.toml` version 从 "1.1.0" 对齐为 `"0.0.3"`（消除双版本体系；App 发布版本以 APP_VERSION 为准）。技术方案 §14 的 `/health` 版本即此实现。

### D14: 前端结构——新增 /tags 页，不抽 base.html

- `app/templates/tags.html`（`data-page="tags"`）：标签管理页——顶部新增表单（名称输入 + 提交 POST）、表格（标签名称 / 使用数量 / 操作[编辑|删除]）、删除被引用标签时展示后端 409 文案；使用数量 >0 时删除按钮仍可用（点击后得到明确错误提示，技术方案 §6 页面示例"观察 0 编辑/删除"仅示意，实际以 API 校验为准）。行内编辑：名称单元格变 input + 保存/取消。
- `app.js` 加 `initTagsPage`（`body[data-page]` 分发注册）。
- 自选管理页（watchlist.html + `loadList`）：股票/ETF 表加"标签"列，单元格为 `<select>`（选项 `无标签` + GET /api/tags），change 即 `PATCH /api/watchlist/{instrument_id}/tag`（零弹窗，贴合现有行内交互风格）；指数 panel 不加标签列。
- 导航：三页 topbar 互相链接（行情首页 / 自选管理 / 标签管理）。
- 弃用 base.html 抽取：见 Non-Goals。

### D15: 测试策略

- 新增 `tests/unit/test_tag_service.py`（名称校验/重复/删除保护/引用计数 + DB 层兜底：直接 session.delete 被引用标签断言 IntegrityError，兼验证 PRAGMA foreign_keys 生效）、`test_job_status_service.py`（§36.4 五场景：首次成功/连续成功/失败/连续失败/失败后成功，断言失败不清 last_success_at、成功清零；另补两场景——注入抛异常的 session 验证写状态失败被吞且不向调用方传播、文件库重建 service/engine 验证跨"重启"持久化）、`test_provider_metrics.py`（§36.5：正常/连接错误/返回异常/超时，异常分类、计数、last_success_at 与耗时；FakeProvider + monkeypatch sleep；非超时 error 情形同样保留 LKG 缓存）、`tests/integration/test_tags_api.py`（CRUD/409/404/422/页面渲染 + watchlist tag 端点：股票设置/ETF 设置/股票解除/ETF 解除/指数 400/标签 404/覆盖切换）、`test_quotes_tag_filter_api.py`（全部/指定/无标签 + tag 字段 + 互斥 422 + 切换筛选期间 Provider 调用数为 0）、`test_admin_status_api.py`（jobs/providers/version 结构、未运行字段为 null 而非缺键、时间格式北京时间 ISO）、`tests/integration/test_migrations.py`（**核心**：①fixture 生成 v0.02 库——对空库先 `alembic upgrade 0001_v002_baseline` 再 `DROP TABLE alembic_version`（模拟"有 v0.02 表、无版本记录"，不可用当前模型 create_all）；stamp 0001 → upgrade head → 四类数据保留 + tag_id 全 NULL；②不 stamp 直接 upgrade head 应失败且数据不变；③空库 upgrade head；④upgrade head 后 inspect 与 create_all schema 一致性比对；⑤batch 重建后 uq_watchlist_instrument 索引/约束在）。
- **必改**：`tests/integration/test_fault_tolerance.py:114` /health 精确断言加 version 字段。
- 迁移测试依赖 alembic 装入 dev 环境（pyproject dependencies，非 dev extras——生产镜像 CMD 也要用）。
- 全量回归：`.venv/bin/python -m pytest -m "not online"`。

### D16: 开发期部署隔离（不影响线上 8765）

调试用独立资源：新镜像 tag（如 `stock-dashboard:v0.03-dev`）、新容器名（如 `stock-dashboard-v003-dev`）、临时数据目录（如 `~/stocksview-v003-dev/data`）、新端口（如 8766）。线上 `stock-dashboard` 容器与 `./data/market.db` 全程不动；升级演练用 v0.02 库副本在临时路径跑 stamp+upgrade 流程。

## Risks / Trade-offs

- [batch_alter_table 重建丢约束/索引] → 迁移测试 upgrade 后 inspect 断言约束、索引、行数齐全（D7/D15）。
- [PRAGMA foreign_keys=ON 改变既有 FK 行为] → 全库仅 watchlist/index_watchlist→instrument 两处 FK，无删除 Instrument 的代码路径；全量回归兜底（D4）。
- [AKShare 超时线程泄漏累积] → shutdown(wait=False)，被弃线程随请求自然终止；刷新周期 60s、单次泄漏有界；结构化日志记录 timeout 便于观察频率（D10）。
- [线上升级忘 stamp 导致新容器启动失败] → 失败即退出且 SQLite 无损；README/CHANGELOG 显式步骤 + 演练任务（D6/D16）；升级前强制备份。
- [迁移与模型长期漂移] → schema 一致性测试进 CI 位置（当前无 CI，作为 pytest 常规用例）持续拦截（D5）。
- [JobStatus 写库失败拖垮刷新循环] → JobStatusService 内部吞异常记 error 日志，主流程无感（D8）。
- [usage_count 并发不准] → 单用户单进程 SQLite 应用，无并发写场景，可忽略。
- [本地筛选状态在轮询重渲染后丢失] → 筛选变量持久于页面生命周期，renderQuotes 后重放过滤（D12）。
- [双版本来源（pyproject vs APP_VERSION）再度漂移] → pyproject 对齐 0.0.3 并在 CHANGELOG 记录；后续版本发布 checklist 含两处同步（D13）。
- [测试基线变化] → /health 断言更新为含 version；新表使 create_all 产物变化，一致性测试以新模型为准。

## Migration Plan

**开发期**（不影响线上）：dev 分支开发 → 新镜像/新容器/临时 data/8766 端口联调（D16）→ 全量 pytest → 升级演练（v0.02 库副本 stamp+upgrade）。

**上线**（v0.02 → v0.03）：

1. 备份线上 `data/market.db`（容器外宿主机路径）。
2. 构建并推送 `stock-dashboard:v0.03` 镜像（ssh key `~/.ssh/id_ed25519`）。
3. 停 `stock-dashboard`（v0.02）容器。
4. 一次性容器 `alembic stamp 0001_v002_baseline`（挂载线上 data 卷）。
5. docker run 新镜像正式容器（沿用线上挂载与 8765 端口，参数同现有拓扑）——CMD 内 `alembic upgrade head` 执行 0002 后启动 uvicorn。
6. 验收：`GET /health` 返回 `"version": "v0.03"`；自选/指数/行情/估值数据完整；`GET /api/admin/status` 返回 jobs/providers；标签功能可用。

**回滚**：停新容器 → 恢复备份 db → 启动 v0.02 镜像容器（v0.03 的 tag/job_status 表与 tag_id 列对 v0.02 代码不可见，即便不恢复备份 v0.02 亦可运行，但以备份恢复为标准回滚）。

## Open Questions

（无——技术方案已覆盖主要决策；D2/D4/D11 与技术方案字面的偏离及理由已在各决策条目记录，如与预期不符可在实施前调整。）
