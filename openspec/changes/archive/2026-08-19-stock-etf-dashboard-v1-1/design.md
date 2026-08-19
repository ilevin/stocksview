# 技术设计：股票与 ETF 行情看板 V1.1

## Context

全新绿地项目（`/home/cc/projects/stocksview`，当前仅有 PRD 文档与 openspec 脚手架）。依据 PRD 文档实现个人使用的轻量行情看板：A 股 + 港股的股票 / ETF / 指数，行情来自 AKShare，估值与交易日历来自 Tushare。单用户、单容器、SQLite 存储，运行于 Linux（Ubuntu 24.04），浏览器访问。

核心约束（来自 PRD）：

- 简单优先：不引入 Redis / MySQL / Celery / 前端框架 / WebSocket
- 业务层禁止直接依赖 AKShare / Tushare，必须走 Provider 接口
- 浏览器不触发数据源请求，只读后端缓存
- 60 秒刷新周期、A 股/港股独立判断市场状态、收盘补抓
- Tushare Token 只存于 `config.yaml`（不提交 Git），不使用环境变量

## Goals / Non-Goals

**Goals:**

- 按 PRD Phase 1 -> Phase 9 交付可运行、可测试、可 Docker 部署的单体应用
- Provider 抽象使 AKShare / Tushare 可替换（配置切换，不做动态插件框架）
- 行情双层缓存（内存 + SQLite 快照），数据源故障时页面仍显示最后一次成功数据
- 全部第三方字段清洗收敛在 Provider 层，业务层只见内部标准模型（Pydantic）

**Non-Goals:**

- 用户系统、多用户、权限
- K 线 / 分时图 / 新闻 / 财报 / AI 分析 / 交易 / 回测
- ETF 指数估值（V1 之后再说）
- 完整插件系统、依赖注入框架

## Decisions

### D1：单体 FastAPI + lifespan 后台任务（不用 APScheduler）

- **选择**：FastAPI lifespan 启动一个 `asyncio` 循环任务，内部 `asyncio.to_thread(...)` 调用同步的 AKShare。
- **理由**：少一个依赖；行情刷新就是一个 60 秒定时循环 + 状态机（收盘补抓需要检测 OPEN->CLOSED 边沿），APScheduler 的 cron/interval 表达式反而不如手写循环直观。
- **备选**：APScheduler（PRD 允许），被否：为一个死循环引库不值。

### D2：instrument_id 作为全局业务主键

- 格式 `MARKET:ASSET_TYPE:SYMBOL`，如 `CN:STOCK:600519`、`HK:INDEX:HSI`。
- 生成逻辑放 `app/services/instrument_service.py`（或 models 层工具函数），独立可测。
- 所有表（watchlist / index_watchlist / quote_snapshot / fundamental_snapshot）用字符串 `instrument_id` 关联 `instrument.instrument_id`，不跨表外键约束整数 id（SQLite 下保持简单，用 UNIQUE 约束保证唯一）。
- **注意**：A 股指数 `000001` 与平安银行 `000001` 代码相同，靠 asset_type 区分 —— 这是引入复合主键的根本原因。

### D3：三层 Provider 抽象（typing.Protocol）

```python
class QuoteProvider(Protocol):
    def get_quotes(self, instruments: list[Instrument]) -> dict[str, Quote]: ...

class FundamentalProvider(Protocol):
    def get_fundamentals(self, instruments: list[Instrument]) -> dict[str, Fundamental]: ...

class TradingCalendarProvider(Protocol):
    def is_trading_day(self, market: str, date: date) -> bool: ...
```

- V1 实现：`AkshareQuoteProvider`（单类内部按 market+asset_type 分派到 AKShare 不同接口）、`TushareFundamentalProvider`、`TushareTradingCalendarProvider`。
- **AKShare 是全市场接口**（如 `stock_zh_a_spot_em` 一次拉全市场）：Provider 内部请求全量 -> 内存过滤用户自选 -> 只返回关注的 Quote；不落库多余数据。
- 具体接口名与 DataFrame 中文列名**必须在 Phase 4 实现时用真实环境验证**（PRD 规则 7/8），候选接口见 `tasks.md` Phase 4 附注；列名映射代码只允许出现在 `app/providers/quote/akshare.py`。

### D4：行情缓存 = 内存 dict + SQLite 快照

- `app/services/quote_cache.py`：进程内 `dict[instrument_id, QuoteSnapshot]`；启动时从 SQLite 预热。
- 写入顺序：Provider 成功 -> 更新内存 -> upsert `quote_snapshot`。失败 -> 两者都不动（不因失败清空缓存）。
- API 读取顺序：内存命中 -> 返回；内存缺失 -> 查 SQLite 最近一条。因此重启后页面仍能显示收盘价。
- 不设 TTL 淘汰；新鲜度用 `is_stale` 表达（见 D6）。

### D5：MarketSessionService —— 唯一的市场状态判定点

- 输入：market、TradingCalendarProvider、当前 `Asia/Shanghai` 时间（ZoneInfo，全部 datetime 带 tz）。
- 输出：`OPEN / LUNCH_BREAK / CLOSED / HOLIDAY` + `should_refresh(market) -> bool`（仅 OPEN 为 True）。
- 交易时段常量：CN `09:30-11:30, 13:00-15:00`；HK `09:30-12:00, 13:00-16:00`。时间规则 + 交易日历双判断，缺一不可。
- 交易日历缓存：`is_trading_day` 结果按 `(market, date)` 查 SQLite，未命中才调 Tushare `trade_cal`，写库后复用；禁止 60 秒级调用日历接口。日历按年批量拉取缓存。
- **港股日历数据源待验证**（Tushare `trade_cal` 对 HK 的支持情况需实测，见 Open Questions），Provider 内部兼容，接口不变。

#### D5.1：交易日历的时区规则（重点）

- **「今天是几号」必须由市场本地时区推导**：查询交易日历用的 date 一律取 `now.astimezone(ZoneInfo("Asia/Shanghai")).date()`。CN 与 HK 均为 UTC+8 且无夏令时，统一用 `Asia/Shanghai`（HK 等价于 `Asia/Hong_Kong`）。
- **禁止**使用服务器本地时区（无 tz 的 `datetime.now()`）、UTC 日期或 Docker 容器默认时区来决定日历查询日期——容器默认 UTC 时，北京时间 0:00-8:00 之间 UTC 日期仍是前一天，会把「今天」错判为前一天，导致市场状态（OPEN/HOLIDAY 等）整体错位一天。
- 状态判定、stale 计算、收盘补抓边沿检测、`fetched_at` 时间戳全部基于同一个 tz-aware 的 `now(ZoneInfo("Asia/Shanghai"))`，任何比较的两个 datetime 必须同为 aware。
- Provider 解析 AKShare 返回的**无时区时间字符串**（如行情时间）时，统一按北京时间 localize（`replace(tzinfo=ZoneInfo("Asia/Shanghai"))`）后再入库；`source_timestamp` 与 `fetched_at` 都以带 tz 形式存储。
- Tushare `trade_cal` 的日历日期是市场本地自然日，直接作为缓存键 `(market, date)` 使用，不做时区换算；北京时间跨日（00:00）前后查询的是不同自然日，缓存按日天然区分。
- 单测必须包含「宿主机/容器时区为 UTC」的用例（注入不同 tz-aware `now`，验证判定结果不随系统时区漂移）。

### D6：stale 判定与收盘补抓

- `is_stale` 在 API 响应时计算（不落库）：
  - 市场 OPEN：`now - fetched_at > stale_seconds(180)` -> stale
  - 市场 LUNCH_BREAK/CLOSED/HOLIDAY：不 stale（保留收盘时刻数据，页面显示 `已收盘 · 15:00:03`）
- 后台任务记录每个市场上一次状态；检测到 OPEN->CLOSED 边沿时补抓一次该市场行情再停。LUNCH_BREAK->OPEN 恢复正常循环即可。
- 每轮循环：分别按市场分组刷新，单市场异常捕获隔离（重试 1 次，再失败仅记录日志），不影响另一市场。

### D7：配置与安全

- `app/config.py` 启动时读 `config.yaml` -> Pydantic 模型，注入各 Provider/Service；业务代码禁止再读 YAML。
- `.gitignore` 含 `config.yaml`、`data/`、`__pycache__` 等；仓库只提交 `config.example.yaml`（假 Token）。
- Token 校验：缺失时应用照常启动，Tushare 功能记 WARNING 并返回 None 数据；日志脱敏（禁止输出 token、禁止 dump 配置全量）。

### D8：Web 层

- Jinja2 模板 `index.html` / `watchlist.html`，原生 JS（`static/app.js`）+ 原生 CSS。
- 首页 JS：加载即拉 `/api/quotes` + `/api/indices`；根据响应中 `market_status` 决定是否 `setTimeout(60s)` 续轮询；两市场都非 OPEN 则停止（页面保留最后数据）。判断逻辑以后端返回为准，前端停止轮询只是省请求。
- 涨跌配色：涨红 / 跌绿 / 平普通；缺失值前端渲染 `-`（API 返回 null）。
- 港股延时行情：行情数据带 `delayed` 标记时市场列显示 `港股 · 延时`。

### D9：数值清洗

- Provider 层统一 `safe_float()`：`"-"`、`""`、`None`、`NaN`、`inf` -> `None`。
- API JSON 序列化禁止 NaN/Infinity（Pydantic 默认满足，序列化前统一 None 化）。

## Risks / Trade-offs

- [AKShare 公开接口不稳定、列名变动] -> Provider 内做列名兼容映射 + 单测锁定转换逻辑；接口失效时页面退回最后缓存而非 500
- [全市场接口数据量大（A股 spot 约 5000 行）] -> 60 秒一次可接受；仅内存过滤不落库；若实测过慢再评估，V1 不优化
- [港股行情可能延迟（免费源多为延时 15 分钟）] -> 明确标注 `港股 · 延时`，不假装实时
- [港股交易日历数据源不确定] -> 优先 Tushare trade_cal；不可用则回退 akshare 港股相关日历接口；接口封装在 TradingCalendarProvider 内，业务无感
- [SQLite 单文件 + 单进程] -> 个人应用足够；写入用 upsert 幂等，重启无迁移负担（SQLAlchemy `create_all` 自动建表，无 Alembic）
- [内存缓存随重启丢失] -> 启动时从 SQLite 预热，窗口内最多一次冷读
- [Tushare Token 权限/积分不足导致 daily_basic 限流] -> 失败降级为估值列显示 `-`，不影响行情主链路
- [服务器/Docker 容器时区不是北京时间（默认 UTC），日历查询日期错位一天] -> 全部日期推导强制 `Asia/Shanghai`（见 D5.1），禁止裸 `datetime.now()`；单测覆盖 UTC 系统时区与北京时间跨日边界用例；Dockerfile 可额外显式设置 `TZ=Asia/Shanghai` 作为双保险（代码不依赖它）

## Migration Plan

绿地项目，无迁移。部署顺序：

1. `cp config.example.yaml config.yaml` 并填写 Tushare Token
2. 本地：`pip install -e . && uvicorn app.main:app`；或 Docker：`docker compose up -d`
3. 首次启动自动建库建表；回滚 = 停容器（数据在挂载的 `./data` 卷中，可整体删除重来）

## Open Questions

- 港股交易日历的具体可用数据源（Tushare `trade_cal` 的 HK 支持度 / akshare 备选）—— Phase 5 实测后定，接口已隔离
- AKShare 港股 spot 接口是否含量比列 —— Phase 4 实测；没有则该列显示 `-`
- 指数名称自动识别的接口（A股 `000001` 上证 vs 平安银行歧义需靠 INDEX 类型与指数表区分）—— Phase 4 实测
