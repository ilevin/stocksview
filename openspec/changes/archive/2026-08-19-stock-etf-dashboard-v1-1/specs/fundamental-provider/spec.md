# Spec: fundamental-provider

Tushare 估值 Provider（A股股票 PE/PB/股息率）。

## ADDED Requirements

### Requirement: FundamentalProvider 统一接口

系统 SHALL 定义 FundamentalProvider 接口：`get_fundamentals(instruments) -> dict[instrument_id, Fundamental]`；V1 实现 TushareFundamentalProvider，基于 Tushare `daily_basic` 提供A股股票的 pe_ttm、pb、dividend_yield_ttm。

#### Scenario: A股股票估值
- **WHEN** 查询 CN:STOCK 标的估值
- **THEN** 返回 Fundamental（pe_ttm、pb、dividend_yield_ttm），缺失为 None

#### Scenario: ETF 与指数无估值
- **WHEN** 标的 asset_type 为 ETF 或 INDEX
- **THEN** 不请求、不写入估值数据，页面显示 `-`

### Requirement: 更新频率

估值数据 SHALL 每日收盘后更新一次（每日一次），保存到 fundamental_snapshot（UNIQUE(instrument_id, trade_date)）；应用启动时当天无估值数据 SHALL 执行一次更新。估值 SHALL NOT 参与每 60 秒行情刷新。

#### Scenario: 每日一次
- **WHEN** 当天已有估值数据
- **THEN** 不再重复请求 Tushare

### Requirement: Token 读取与降级

Tushare Token SHALL 只从 config.yaml 的 tushare.token 读取，SHALL NOT 依赖环境变量。Token 缺失时应用 SHALL 正常启动，Tushare 功能记录明确配置错误，估值字段降级为空。

#### Scenario: 无 Token 启动
- **WHEN** config.yaml 中 token 为空或缺失
- **THEN** 应用启动成功，日志含配置错误提示，估值列为 `-`，日志不输出 Token

#### Scenario: Tushare 失败
- **WHEN** Tushare 请求异常或限流
- **THEN** 不崩溃，估值保留最后快照或为空，日志记录失败

### Requirement: 证券基础信息与日历

证券基础信息（名称等）SHALL 每天更新一次；A股交易日历按需获取并缓存到 SQLite，SHALL NOT 以 60 秒级频率调用 Tushare 日历接口，也 SHALL NOT 在每次页面访问时调用 Tushare。

#### Scenario: 日历缓存
- **WHEN** 同一交易日历日期被多次查询
- **THEN** 仅首次触发数据源请求，后续命中 SQLite 缓存
