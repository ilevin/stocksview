# Spec: watchlist-management

股票/ETF 自选与指数配置的增删查排序。

## ADDED Requirements

### Requirement: 股票/ETF 自选添加

系统 SHALL 提供 `POST /api/watchlist`，接收 symbol、market、asset_type；仅允许 STOCK/ETF；自动识别名称后写入 instrument 与 watchlist。当前市场 OPEN 时 SHALL 触发一次该资产行情更新。

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

### Requirement: 股票/ETF 自选删除

系统 SHALL 提供 `DELETE /api/watchlist/{instrument_id}`，仅删除 watchlist 记录，保留 instrument/quote/fundamental 历史数据。

#### Scenario: 删除成功
- **WHEN** 删除一个存在的自选
- **THEN** 返回 204 No Content，历史行情快照仍在数据库

### Requirement: 股票/ETF 自选查询与排序

系统 SHALL 提供 `GET /api/watchlist`（按 sort_order 返回列表）与 `PUT /api/watchlist/order`（批量更新排序）。

#### Scenario: 查询列表
- **WHEN** GET /api/watchlist
- **THEN** 返回含 instrument_id、symbol、name、market、asset_type、sort_order 的 items

#### Scenario: 调整排序
- **WHEN** PUT /api/watchlist/order 传入新的 instrument_id/sort_order 列表
- **THEN** 排序持久化，GET 按新顺序返回

### Requirement: 指数配置

系统 SHALL 提供 `GET/POST/DELETE /api/index-watchlist` 与 `PUT /api/index-watchlist/order`，行为与股票/ETF 自选一致，但仅允许 INDEX 类型，存储于独立的 index_watchlist 表。

#### Scenario: 添加指数
- **WHEN** POST `{symbol:"000300", market:"CN", asset_type:"INDEX"}`
- **THEN** 返回 201，名称自动识别

#### Scenario: 禁止股票/ETF 进入指数配置
- **WHEN** POST /api/index-watchlist 时 asset_type 为 STOCK 或 ETF
- **THEN** 返回校验错误

#### Scenario: 指数重复添加
- **WHEN** 指数已在 index_watchlist
- **THEN** 返回 409 Conflict

### Requirement: 自选管理页面

系统 SHALL 提供 `/watchlist` 页面（Jinja2），包含股票/ETF 与指数两个独立管理区域，支持查看、添加、删除、调整排序操作。

#### Scenario: 空状态
- **WHEN** 无任何自选时访问页面
- **THEN** 显示空状态提示，不报错

### Requirement: 数据持久化

自选与指数配置 SHALL 持久化到 SQLite；服务重启后数据仍存在。

#### Scenario: 重启后保留
- **WHEN** 添加自选后重启服务
- **THEN** 自选列表与指数配置完整保留
