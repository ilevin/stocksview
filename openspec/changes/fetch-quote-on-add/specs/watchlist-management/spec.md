## MODIFIED Requirements

### Requirement: 股票/ETF 自选添加

系统 SHALL 提供 `POST /api/watchlist`，接收 symbol、market、asset_type；仅允许 STOCK/ETF；自动识别名称后写入 instrument 与 watchlist。添加成功后 SHALL 无论市场状态如何（OPEN/LUNCH_BREAK/CLOSED/HOLIDAY）均触发一次该资产行情更新；即时刷新失败 SHALL NOT 影响添加结果。

#### Scenario: 添加成功
- **WHEN** POST `{symbol:"600519", market:"CN", asset_type:"STOCK"}` 且证券可识别
- **THEN** 返回 201 Created

#### Scenario: 重复添加
- **WHEN** instrument_id 已在 watchlist
- **THEN** 返回 409 Conflict

#### Scenario: 证券不存在
- **WHEN** 代码无法识别
- **THEN** 返回 404 Not Found 及明确错误信息

#### Scenario: 拒绝指数类型
- **WHEN** asset_type 为 INDEX
- **THEN** 返回校验错误，不写入

#### Scenario: 休市时段添加后立即获取行情
- **WHEN** 市场 CLOSED（或 LUNCH_BREAK/HOLIDAY）时 POST 添加自选成功
- **THEN** 系统对该标的执行一次行情更新，页面能显示最近收盘行情

#### Scenario: 即时刷新失败不影响添加
- **WHEN** 添加成功但行情 Provider 抛异常或超时
- **THEN** 添加接口仍返回 201，刷新失败仅记录日志

### Requirement: 指数配置

系统 SHALL 提供 `GET/POST/DELETE /api/index-watchlist` 与 `PUT /api/index-watchlist/order`，行为与股票/ETF 自选一致，但仅允许 INDEX 类型，存储于独立的 index_watchlist 表。添加成功后 SHALL 无论市场状态如何均触发一次该指数行情更新；即时刷新失败 SHALL NOT 影响添加结果。

#### Scenario: 添加指数
- **WHEN** POST `{symbol:"000300", market:"CN", asset_type:"INDEX"}`
- **THEN** 返回 201，名称自动识别

#### Scenario: 禁止股票/ETF 进入指数配置
- **WHEN** POST /api/index-watchlist 时 asset_type 为 STOCK 或 ETF
- **THEN** 返回校验错误

#### Scenario: 指数重复添加
- **WHEN** 指数已在 index_watchlist
- **THEN** 返回 409 Conflict

#### Scenario: 休市时段添加指数后立即获取行情
- **WHEN** 市场 CLOSED（或 LUNCH_BREAK/HOLIDAY）时 POST 添加指数成功
- **THEN** 系统对该指数执行一次行情更新，页面能显示最近收盘行情

#### Scenario: 即时刷新不改变周期刷新策略
- **WHEN** 市场 CLOSED/LUNCH_BREAK/HOLIDAY 时发生添加操作触发的即时刷新
- **THEN** 该一次性刷新执行后，60 秒后台任务仍遵守「仅 OPEN 市场刷新」策略，不对该市场做周期性行情请求
