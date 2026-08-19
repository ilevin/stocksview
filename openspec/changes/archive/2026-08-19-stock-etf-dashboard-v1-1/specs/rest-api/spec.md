# Spec: rest-api

REST API 层与错误处理。

## ADDED Requirements

### Requirement: 行情查询 API

`GET /api/quotes` SHALL 返回自选股票/ETF 行情：顶层含 market_status（CN/HK 各自状态），items 含 instrument_id、symbol、name、market、asset_type、price、change_percent、volume_ratio、pe_ttm、pb、dividend_yield_ttm、quote_source、fundamental_source、source_timestamp、is_stale。缺失字段 SHALL 返回 null，SHALL NOT 返回 "-"（由前端渲染）。

#### Scenario: 正常返回
- **WHEN** GET /api/quotes 且缓存有数据
- **THEN** 返回 200 与 items 列表，估值缺失字段为 null

#### Scenario: 合并估值
- **WHEN** A股股票有 fundamental_snapshot
- **THEN** pe_ttm/pb/dividend_yield_ttm 来自估值快照，fundamental_source 为 tushare

### Requirement: 指数查询 API

`GET /api/indices` SHALL 返回 index_watchlist 配置的指数行情，items 不含 PE/PB/股息率字段。

#### Scenario: 指数返回
- **WHEN** GET /api/indices
- **THEN** items 仅含名称、点位、涨跌幅、来源、时间、is_stale 等行情字段

### Requirement: watchlist 与 index-watchlist API

系统 SHALL 提供 17.3-17.10 节全部端点（GET/POST/DELETE/PUT order），状态码：201 添加成功、409 重复、404 不存在、204 删除成功。

#### Scenario: 添加已存在
- **WHEN** POST /api/watchlist 重复标的
- **THEN** 409 Conflict

### Requirement: 管理与健康接口

系统 SHALL 提供 POST /api/admin/refresh/quotes、POST /api/admin/refresh/fundamentals 与 GET /health。健康检查 SHALL 只检查应用与数据库，SHALL NOT 实时调用 AKShare/Tushare。

#### Scenario: 健康检查
- **WHEN** GET /health 且数据库可连接
- **THEN** 返回 `{"status":"ok","database":"ok"}`

### Requirement: 全局容错

任何单个 Provider 失败 SHALL NOT 导致 HTTP 500 或进程崩溃；所有 API SHALL 使用明确的 Pydantic Schema；时间统一返回北京时间（带时区 ISO 格式）。

#### Scenario: 单市场故障
- **WHEN** 港股数据源故障
- **THEN** /api/quotes 返回 200，A股数据正常，港股显示最后成功数据并标记过期
