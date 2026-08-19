# 提案：股票与 ETF 行情看板 V1.1

依据文档：`股票ETF行情看板_V1.1_PRD_技术设计_ClaudeCode_Prompt.md`

## Why

需要为个人投资提供查看 A 股、港股股票 / ETF / 指数行情的统一入口。目前没有现成系统：希望有一个自部署、轻量、稳定的看板，集中展示自选标的的价格、涨跌幅与估值（PE / PB / 股息率），并在非交易时段保留最后一次成功行情，避免反复手动查行情软件。

## What Changes

- 新建单体 Web 应用（Python 3.11+ / FastAPI / SQLAlchemy / SQLite / Jinja2 / 原生 JS+CSS），不依赖 Redis、MySQL、Node.js
- 引入统一 `instrument` 模型（`market + asset_type + symbol` 生成 `instrument_id`），管理 A股/港股的股票、ETF、指数
- 两个页面：
  - `/` 行情首页：市场状态、指数行情卡片区、自选股票/ETF 行情表格
  - `/watchlist` 自选管理：股票/ETF 与指数的添加、删除、排序
- 行情数据链路：后台任务 → `MarketSessionService` 判断市场状态 → `QuoteProvider`（AKShare）→ 内存缓存 + `quote_snapshot` 落库；浏览器只读后端缓存 API，不直接触发数据源请求
- 估值数据链路：`FundamentalProvider`（Tushare `daily_basic`）每日收盘后更新 A 股股票 PE(TTM)/PB/股息率(TTM)
- 交易日历（CN/HK）按需获取并缓存到 SQLite；A 股、港股独立判断交易状态；开盘时段每 60 秒刷新，午休/收盘/节假日停止，OPEN→CLOSED 切换时收盘补抓一次
- 数据新鲜度（`is_stale`）判定：交易时段超 180 秒未更新视为 stale；非交易时段不因时间流逝标记 stale
- 完整 REST API（`/api/quotes`、`/api/indices`、`/api/watchlist`、`/api/index-watchlist`、`/api/admin/refresh/*`、`/health`），Pydantic Schema，缺失字段返回 `null`（`-` 由前端渲染）
- 配置统一 `config.yaml`（含 Tushare Token），仓库只提交 `config.example.yaml`
- Provider 抽象（QuoteProvider / FundamentalProvider / TradingCalendarProvider），第三方字段映射只存在于 Provider 层，业务层禁止触碰 DataFrame
- 单容器 Docker 部署（Dockerfile + docker-compose.yml）与 README
- 单元/集成测试覆盖 instrument_id 生成、数值清洗、Provider 转换、watchlist 管理、市场状态判定、刷新策略、stale 判定、容错回退、配置读取

## Capabilities

### New Capabilities

- `instrument-management`: 证券基础信息模型（instrument_id 生成、SQLite 存储、名称自动识别）
- `watchlist-management`: 股票/ETF 自选与指数配置的增删查排序（含重复添加 409、未知证券 404）
- `quote-provider`: AKShare 行情 Provider 抽象与实现（A股/港股股票、ETF、指数统一转换为内部 Quote 模型）
- `fundamental-provider`: Tushare 估值 Provider（A股股票 PE/PB/股息率，每日更新）
- `market-session`: 交易日历 + 市场状态判定（OPEN/LUNCH_BREAK/CLOSED/HOLIDAY，A股港股独立判断）
- `quote-cache-refresh`: 后台行情刷新任务、内存缓存 + SQLite 快照双层缓存、收盘补抓、stale 判定
- `dashboard-ui`: 首页与自选管理页面（Jinja2 + 原生 JS/CSS，60 秒轮询，非交易时段停止轮询）
- `rest-api`: REST API 层（Pydantic Schema、错误处理、健康检查）
- `config-management`: config.yaml 配置管理（Token 安全、config.example.yaml、日志脱敏）
- `deployment`: Docker 单容器部署与 README

### Modified Capabilities

（无 —— 全新项目，无既有 spec）

## Impact

- 全新代码库：`app/`（main、config、db、api、models、schemas、providers、repositories、services、jobs、templates、static）、`tests/`、`data/`
- 外部依赖：AKShare（行情）、Tushare（估值/日历，需 Token）、httpx；均为公开接口，需做好超时、重试（单次最多 1 次）与容错
- 外部系统：无写操作；单容器 SQLite，数据持久化在挂载的 `./data` 目录
- 无破坏性变更（绿地项目）
