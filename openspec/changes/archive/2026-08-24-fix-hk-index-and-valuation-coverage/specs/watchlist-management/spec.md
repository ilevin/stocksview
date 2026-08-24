## MODIFIED Requirements

### Requirement: 股票/ETF 自选添加

系统 SHALL 提供 `POST /api/watchlist`，接收 symbol、market、asset_type；仅允许 STOCK/ETF；自动识别名称后写入 instrument 与 watchlist。添加成功后 SHALL 无论市场状态如何（OPEN/LUNCH_BREAK/CLOSED/HOLIDAY）均触发一次该资产行情更新；即时刷新失败 SHALL NOT 影响添加结果。添加 CN/STOCK 成功后 SHALL 同时立即获取该股最近一期估值，估值获取失败 SHALL NOT 影响添加结果。

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

#### Scenario: 添加后立即获取估值
- **WHEN** 添加 CN/STOCK 自选成功
- **THEN** 系统立即获取该股最近一期估值并写入，页面无需等待收盘后刷新即可显示

#### Scenario: 估值获取失败不影响添加
- **WHEN** 添加成功但估值 Provider 抛异常或超时
- **THEN** 添加接口仍返回 201，失败仅记录日志

### Requirement: 自选管理页面

系统 SHALL 提供 `/watchlist` 页面（Jinja2），包含股票/ETF 与指数两个独立管理区域，支持查看、添加、删除、调整排序操作。指数添加区域 SHALL 提示港股指数代码格式（字母缩写，示例含恒生科技指数 HSTECH）。

#### Scenario: 空状态
- **WHEN** 无任何自选时访问页面
- **THEN** 显示空状态提示，不报错

#### Scenario: 港股指数代码提示
- **WHEN** 访问 /watchlist 指数管理区域
- **THEN** 输入框提示同时包含 A 股与港股指数代码示例（如 000001 上证指数、HSTECH 恒生科技指数）
