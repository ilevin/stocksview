# v0.03 实施任务清单

> 实施顺序遵循技术方案 §37：**先 Alembic，再改数据库结构**。调试期间全程使用新镜像/新容器/临时数据路径/新端口（8766），不影响线上 8765 的 v0.02 容器。

## 1. 数据模型与 Alembic 迁移基础

- [x] 1.1 `pyproject.toml`：dependencies 增加 `alembic>=1.13`（生产镜像 CMD 需要，不放 dev extras）；`version` 由 "1.1.0" 对齐为 `"0.0.3"`；`.venv` 安装依赖
- [x] 1.2 新建 `app/models/tag.py`：`Tag`（表 `tag`：id PK、name VARCHAR(50) NOT NULL + `uq_tag_name` 唯一约束、created_at/updated_at），注册进 `app/models/__init__.py`（模型先于 Alembic 定义以服务手写 0002 迁移；1.9 移除 init_db 前请勿启动应用，避免 create_all 提前建出 v0.03 表）
- [x] 1.3 新建 `app/models/job_status.py`：`JobStatus`（表 `job_status`：job_name VARCHAR(64) PK、last_started_at/last_success_at/last_error_at 可空、last_error TEXT 可空、last_duration_ms 可空、consecutive_failures 默认 0、updated_at），注册进 `app/models/__init__.py`
- [x] 1.4 `app/models/watchlist.py`：`Watchlist` 增加 `tag_id`（Integer 可空，`ForeignKey("tag.id", ondelete="RESTRICT")`）
- [x] 1.5 初始化 Alembic：根目录 `alembic.ini` + `alembic/{env.py,script.py.mako,versions/}`；`env.py` 复用 `app.config.load_config().database.url` 与 `app.db.Base`（`import app.models`）作 target_metadata
- [x] 1.6 手写 `alembic/versions/0001_v002_baseline.py`：v0.02 全部 7 张表（instrument/watchlist/index_watchlist/quote_snapshot/fundamental_snapshot/app_setting/trading_calendar）的 create_table，逐表与 `data/market.db` 实际 schema 核对（含约束名与索引）
- [x] 1.7 手写 `alembic/versions/0002_v003_tags_and_job_status.py`：create_table tag 与 job_status；`batch_alter_table("watchlist")` 增加 tag_id 列与外键，batch 重建保留 `uq_watchlist_instrument`
- [x] 1.8 `app/db.py` `create_db_engine`：增加 SQLite connect 事件开启 `PRAGMA foreign_keys=ON`
- [x] 1.9 `app/main.py` lifespan：移除 `init_db(engine)` 调用（`init_db` 函数保留供测试）
- [x] 1.10 `Dockerfile`：增加 `COPY alembic.ini ./` 与 `COPY alembic ./alembic`；CMD 改为 `["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]`
- [x] 1.11 新建 `tests/integration/test_migrations.py`：v0.02 库 fixture（空库先 `alembic upgrade 0001_v002_baseline` 再 `DROP TABLE alembic_version` 模拟"有 v0.02 表、无版本记录"，勿用当前模型 create_all）→ stamp 0001 → upgrade head 后四类数据保留且 tag_id 全 NULL；同 fixture 不 stamp 直接 upgrade head 应失败且数据不变；空库 upgrade head 全链；`upgrade head` 后 schema 与 `Base.metadata.create_all` inspect 一致性比对；batch 后 watchlist 唯一约束/索引仍在

## 2. 版本信息

- [x] 2.1 新建 `app/version.py`：`APP_VERSION = "v0.03"`
- [x] 2.2 `app/main.py`：`templates.env.globals["app_version"] = APP_VERSION`；`/health` 响应增加 `"version"` 字段
- [x] 2.3 `app/templates/index.html`：底部新增 footer 区块，显示 `StocksView {{ app_version }}`
- [x] 2.4 `tests/integration/test_fault_tolerance.py`：更新 `/health` 精确断言（加 version 字段）

## 3. 标签 Service 与 API

- [x] 3.1 新建 `app/repositories/tag.py`：`TagRepository`（list/get_by_id/get_by_name/create/rename/delete/count_usage——usage 按 watchlist.tag_id 计数）
- [x] 3.2 新建 `app/services/tag_service.py`：`TagService`（名称 strip/非空/≤50 校验、查重、create/rename/delete/list_with_usage、被引用抛 TagInUseError），异常族（TagNameEmptyError/TagNameTooLongError/DuplicateTagNameError/TagInUseError/TagNotFoundError）
- [x] 3.3 `app/schemas/__init__.py`：新增 `TagCreateRequest`/`TagUpdateRequest`/`TagItem{id,name,usage_count}`/`TagListResponse`/`WatchlistTagRequest{tag_id: int|None}`
- [x] 3.4 新建 `app/api/tags.py`：`GET/POST/PATCH/DELETE /api/tags`（201/200/204/404/409/422），`app/main.py` 注册路由
- [x] 3.5 `app/services/watchlist_service.py`：`WatchlistService` 增加 `set_tag(instrument_id, tag_id)`（先按 instrument_id 查 instrument 的 asset_type，INDEX→400——先判类型使指数场景经 API 可达；再查自选行 404、标签 404；覆盖切换语义）
- [x] 3.6 `app/api/watchlist.py`：新增 `PATCH /api/watchlist/{instrument_id}/tag` 端点（含异常映射）
- [x] 3.7 `GET /api/watchlist` 响应 items 增加 `tag` 对象（`{id,name}` 或 null；在 `WatchlistRepository` 子类覆写/新增带 tag 的查询，不改动 `BaseWatchlistRepository` 泛型基类——design D12）
- [x] 3.8 新建 `tests/unit/test_tag_service.py`（校验/查重/删除保护/引用计数/解除关联 + DB 层兜底：直接 session.delete 被引用标签断言 IntegrityError，兼验证 PRAGMA foreign_keys=ON 生效）与 `tests/integration/test_tags_api.py`（CRUD、409 重名与被引用删除、404、422、`GET /tags` 页面渲染 200、watchlist tag 端点场景：股票设置/ETF 设置/股票解除/ETF 解除/指数 400/标签 404/覆盖切换、usage_count 随删除自选递减）

## 4. 行情筛选 API

- [x] 4.1 `app/api/quotes.py`：`get_quotes` 增加 `tag_id: int|None` 与 `untagged: bool` Query 参数，同传返回 422
- [x] 4.2 `app/api/quotes.py` `_assemble`：组装每条目 `tag` 对象（tag 表一次查询建 id→name 映射，仅作用于 STOCK/ETF 条目，`IndexQuoteItem` 与 `/api/indices` 行为不变）；按 tag_id/untagged 在组装层过滤
- [x] 4.3 `app/schemas/__init__.py`：`QuoteItem` 增加 `tag: {id,name}|None` 字段
- [x] 4.4 新建 `tests/integration/test_quotes_tag_filter_api.py`：全部/指定标签/无标签三种返回、tag 字段正确性、互斥 422、筛选请求不触发 Provider（Fake provider 调用计数为 0）

## 5. 前端页面

- [x] 5.1 新建 `app/templates/tags.html`（`data-page="tags"`）：新增表单、标签表格（名称/使用数量/操作）、行内编辑、删除 409 错误展示；`app/main.py` 增加页面路由 `/tags`
- [x] 5.2 `app/static/app.js`：新增 `initTagsPage`（加载列表、创建、行内编辑保存、删除与 409 反馈），注册 `body[data-page]` 分发
- [x] 5.3 `app/templates/watchlist.html` + `app.js`：股票/ETF 区增加「标签」列（行内 `<select>`，选项=无标签+`GET /api/tags`，change 即 `PATCH /api/watchlist/{iid}/tag`），指数区不加标签列
- [x] 5.4 `app/templates/index.html` + `app.js`：自选表格区顶部增加标签筛选下拉（全部/无标签/各标签，选项来自 `GET /api/tags`）；本地过滤渲染、筛选状态在 60 秒轮询重渲染后保持
- [x] 5.5 三页 topbar 导航互链（行情首页/自选管理/标签管理）
- [x] 5.6 `app/static/style.css`：footer、筛选条、标签列等样式补充
- [x] 5.7 手动冒烟：以测试镜像/新容器/临时数据/8766 端口验证三页面（建标签→关联自选→行情筛选→版本 footer）

## 6. JobStatus

- [x] 6.1 新建 `app/services/job_status_service.py`：`JobStatusService(session_factory)` 的 `record_started/record_success/record_failure`（upsert 单行；失败不清 last_success_at；成功清零 consecutive_failures；内部异常吞掉记日志）
- [x] 6.2 `app/jobs/quote_refresh.py`：`_run` 循环体包装（started→tick→success/failure），注入 JobStatusService，job_name=`quote_refresh`
- [x] 6.3 `app/jobs/fundamental_refresh.py`：同样包装 `_maybe_run`，job_name=`fundamental_refresh`
- [x] 6.4 新建 `tests/unit/test_job_status_service.py`：首次成功/连续成功/失败/连续失败/失败后成功五场景（断言失败不清 last_success_at、成功清零、duration 记录）+ 注入抛异常的 session_factory 验证写状态失败被吞且不向调用方传播 + 文件库重建 service/engine 验证跨"重启"状态持久化

## 7. Provider 超时与指标

- [x] 7.1 `app/config.py`：新增 `TimeoutConfig{tencent=8, akshare=15, tushare=15}` 挂 `ProvidersConfig.timeout`；`config.example.yaml` 增加 `providers.timeout` 示例节
- [x] 7.2 新建 `app/observability/provider_metrics.py`：`ProviderMetrics`（request/success/error/timeout 计数、last_success_at/last_error_at/last_error/last_duration_ms）+ `ProviderMetricsRegistry` + `call_with_metrics(source, fn, timeout=None)`（monotonic 计时；TimeoutError/httpx.TimeoutException/requests.Timeout→timeout 类，其余→error 类；超时用 ThreadPoolExecutor + `shutdown(wait=False)`；结构化日志）
- [x] 7.3 `app/providers/quote/__init__.py`：Registry 构造 Tencent client 时从 config 注入 timeout；`get_quotes` 每组调用包 `call_with_metrics`（akshare 组获得线程级超时）
- [x] 7.4 `app/providers/fundamental/tushare.py`：`ts.pro_api(token, timeout=config)`；main.py 构造处包方法级 metrics（TimedFundamentalProvider 或等价组合）
- [x] 7.5 新建 `tests/unit/test_provider_metrics.py`：正常/连接错误/返回异常/超时四场景（FakeProvider+可编程延迟），断言计数分类、last_duration_ms、last_success_at（成功更新为本次时间，未成功过为 null）、超时后调用方拿到异常且不长时间阻塞；超时与非超时 error 两类失败均不影响缓存保留（沿用 FakeRegistry 模式）

## 8. 运行状态接口

- [x] 8.1 新建 `app/api/status.py`：`GET /api/admin/status` 返回 `{version, jobs, providers}`（jobs 读 job_status 表、providers 读内存 metrics；未运行字段为 null；北京时间 ISO），`app/main.py` 注册
- [x] 8.2 新建 `tests/integration/test_admin_status_api.py`：结构断言（jobs 含两 job、providers 含三源、version=v0.03；全新库下两 job 键存在且各状态字段为 null 而非缺键；预写 job_status 记录后时间字段为 +08:00 北京时间 ISO 格式）

## 9. 验证、升级演练与收尾

- [x] 9.1 全量回归：`.venv/bin/python -m pytest -m "not online"` 全绿
- [x] 9.2 构建测试镜像 `stock-dashboard:v0.03-dev` 并以新容器（`stock-dashboard-v003-dev`）、临时数据目录、8766 端口运行（线上 8765 容器不动），验证：启动自动迁移、`/health` 版本、三页面、`/api/admin/status`；另人为制造迁移失败（如挂载结构损坏的库）确认容器退出且 uvicorn 未启动
- [x] 9.3 升级演练（临时路径）：复制 v0.02 `data/market.db` → `alembic stamp 0001_v002_baseline` → 启动测试容器 → 验证自选/指数/行情/估值数据完整、tag_id 全 NULL、标签功能正常
- [x] 9.4 `README.md`：本地启动步骤加 `alembic upgrade head`；新增「v0.02→v0.03 升级」章节（备份/stamp/upgrade/回滚）与 `providers.timeout` 配置说明
- [x] 9.5 `CHANGELOG.md` 增加 v0.03 条目（业务功能 + 架构改进 + 升级注意事项）
- [x] 9.6 `openspec validate v003-tags-alembic-observability` 通过，确认全部 spec delta 合规
- [x] 9.7 （上线，另行执行）按 design.md Migration Plan：备份线上库 → stamp 基线 → 新镜像正式容器替换（沿用 8765 与既有挂载）→ 验收 /health version 与数据完整性

## 10. 多标签支持（v0.03b 需求修订：条目与标签多对多，2026-09-02）

> 用户澄清原始需求「股票、etf 和标签的关系是 1 对多」指一个自选条目可关联多个标签（多对多），推翻技术方案 §1.1 第 5 条的单标签限制，见 design D2 修订。

- [x] 10.1 新建 `app/models/watchlist_tag.py`：`WatchlistTag`（表 `watchlist_tag`：id PK、watchlist_id FK ON DELETE CASCADE、tag_id FK ON DELETE RESTRICT、`uq_watchlist_tag` 联合唯一），注册；`Watchlist` 移除 tag_id 列
- [x] 10.2 新建 `alembic/versions/0003_v003b_watchlist_tags_table.py`：建 watchlist_tag 表；把既有 watchlist.tag_id 数据搬入关联表（零丢失）；batch 移除 watchlist.tag_id 列与外键；downgrade 反向（多标签取 MIN 回搬，有损降级）
- [x] 10.3 `TagRepository`：count_usage/list_with_usage 改按 watchlist_tag；`WatchlistService.set_tags(iid, tag_ids)` 全量替换（先判 INDEX→400、条目 404、各 tag 404、去重）；`WatchlistRepository.list_ordered_with_tags()` 聚合返回 (Watchlist, Instrument, [Tag...])
- [x] 10.4 `app/schemas`：`WatchlistTagsRequest{tag_ids: list[int]}`（替代 WatchlistTagRequest）；`WatchlistItem`/`QuoteItem` 的 tag 字段改为 `tags: list[TagBrief]`；`app/api/watchlist.py` 端点改为 `PUT /{instrument_id}/tags`
- [x] 10.5 `app/api/quotes.py`：`_assemble` 组装 per 条目 tags 数组；筛选 tag_id=包含即命中、untagged=空数组
- [x] 10.6 前端：自选管理页标签列改为可点击 chips（已关联高亮/未关联置灰，点击 toggle 后 PUT 全量保存，失败回滚）；行情页标签列显示多个标签名（顿号连接）；筛选/列渲染适配 tags 数组；style.css 补 chips 样式
- [x] 10.7 测试更新：`test_tags_api`（PUT 端点、多标签/全量替换/解除全部/指数 400/标签 404）、`test_quotes_tag_filter`（tags 数组、多标签命中筛选）、`test_tag_service`（关联表计数与删除保护）、`test_migrations`（head 推进 + 0003 数据搬迁断言 + schema 一致性）
- [x] 10.8 全量回归 → 重建镜像 → 替换线上容器（启动自动执行 0003，无需 stamp）→ 线上验收（多标签关联/筛选/引用计数）
