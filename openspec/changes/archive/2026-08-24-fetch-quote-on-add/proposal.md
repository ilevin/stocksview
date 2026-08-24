## Why

在开市时间外（CLOSED/LUNCH_BREAK/HOLIDAY）添加自选股或指数后，页面不显示股价、指数等信息：现有逻辑是仅当市场 OPEN 时才触发添加后的即时行情刷新，而 60 秒后台任务也只在 OPEN 状态刷新，导致新增标的在下一个交易日开盘前完全没有行情数据。

## What Changes

- 添加自选（股票/ETF）后，无论市场状态如何，立即触发一次该资产行情更新
- 添加指数后，同样立即触发一次该指数行情更新（当前指数添加完全没有即时刷新逻辑）
- 即时刷新失败不影响添加操作本身（添加成功仍返回 201）
- 保留 60 秒后台任务仅在 OPEN 市场刷新的既有策略不变

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `watchlist-management`: 「股票/ETF 自选添加」的需求由「当前市场 OPEN 时触发一次该资产行情更新」改为「无论市场状态如何均触发一次该资产行情更新」；「指数配置」需求新增同样的添加后即时刷新要求

## Impact

- `app/api/watchlist.py`：`_trigger_refresh_if_open` 去掉 OPEN 判定（重命名为 `_trigger_refresh`）
- `app/api/index_watchlist.py`：`add_index_watchlist` 增加即时刷新调用
- `app/services/refresh_service.py`：`refresh_instruments_now` 逻辑不变，继续复用
- 测试：更新 `tests/integration/test_watchlist_api.py` 及相关单测，覆盖休市时段添加后仍能获取行情的场景
- 无 API 契约变化（请求/响应结构不变），无数据库结构变化，无依赖变化
