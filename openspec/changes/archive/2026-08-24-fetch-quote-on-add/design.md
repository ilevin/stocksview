## Context

行情数据链路为「后台 60 秒任务 -> Provider -> 内存缓存 -> SQLite quote_snapshot」，API 只读缓存。后台任务仅在市场 OPEN 时刷新（quote-cache-refresh 既有策略）。添加自选时的即时刷新入口在 `app/api/watchlist.py` 的 `_trigger_refresh_if_open`，但其内部先调用 `MarketSessionService.should_refresh`（仅 OPEN 为真），休市时段直接跳过；指数添加接口（`app/api/index_watchlist.py`）则完全没有即时刷新调用。

`RefreshService.refresh_instruments_now`（PRD 17.4）本身不检查市场状态，直接对该标的列表执行 `_refresh_instrument_list`，休市时数据源（AKShare 等）仍会返回最近收盘行情，因此能力已具备，只是 API 层被市场状态守门拦住了。

## Goals / Non-Goals

**Goals:**
- 添加自选/指数后，无论市场处于 OPEN/LUNCH_BREAK/CLOSED/HOLIDAY，都能立即看到该标的的行情（含最近收盘价）
- 即时刷新失败不影响添加操作本身
- 股票/ETF 与指数两个添加入口行为一致

**Non-Goals:**
- 不改变 60 秒后台任务「仅 OPEN 刷新」的策略（休市时段仍不做周期性请求）
- 不改变 stale 判定、收盘补抓等既有 quote-cache-refresh 行为
- 不引入新的 API 端点或请求/响应结构变化

## Decisions

**D1：直接移除 API 层的市场状态守门，复用 `refresh_instruments_now`**

`_trigger_refresh_if_open` 改为 `_trigger_refresh`，去掉 `should_refresh` 判定，无条件调用 `refresher.refresh_instruments_now([instrument_id])`。备选方案是给 `refresh_instruments_now` 加 force 参数——不采用：该方法本来就无状态检查，语义上即为「立即刷新指定标的」，市场状态守门放在 API 层且属误加。

**D2：指数添加接口复用同一触发函数**

将 `_trigger_refresh` 提取到公共位置（保持在 `app/api/watchlist.py` 中，由 `index_watchlist.py` 导入即可，沿用现有 `_error_status` 的共享方式），`add_index_watchlist` 添加成功后同样调用。

**D3：同步调用，不改为后台任务**

即时刷新在请求处理中同步执行（保持现有模式）。添加操作本身已同步调用 `name_provider.get_name`（同样走外部数据源），同步刷一次行情的延迟可接受；引入后台队列会显著增加复杂度且收益低。失败路径已被 try/except 包裹，刷新异常仅记日志。

**D4：刷新失败静默降级**

`refresh_instruments_now` 内部已整体 try/except；API 层同样包一层 try/except。休市时数据源偶发不可用属于正常情况，不应让添加接口返回 5xx。

## Risks / Trade-offs

- [添加接口延迟增加一次行情请求耗时] -> 单标的请求量级与现有名称识别请求相当，可接受；失败路径有超时与异常兜底
- [休市时段数据源返回的可能是前一交易日数据] -> 正是本变更的预期行为：显示最近收盘行情，配合既有 is_stale 判定（休市不过期）
- [指数接口新增刷新逻辑可能影响既有测试] -> 测试中以 Fake/stub 替换 refresh_service，断言调用发生即可，无真实外部请求
