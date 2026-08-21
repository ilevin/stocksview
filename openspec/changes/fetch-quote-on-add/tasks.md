## 1. API 层修改

- [x] 1.1 在 `app/api/watchlist.py` 中将 `_trigger_refresh_if_open` 重命名为 `_trigger_refresh`，移除 `should_refresh` 市场状态判定，无条件调用 `refresh_instruments_now([instrument_id])`，保留 try/except 静默降级
- [x] 1.2 在 `app/api/index_watchlist.py` 的 `add_index_watchlist` 中添加成功后调用 `_trigger_refresh`（从 `app.api.watchlist` 导入），并为该函数增加 `request: Request` 参数

## 2. 测试

- [x] 2.1 更新 `tests/integration/test_watchlist_api.py`：构造市场 CLOSED 场景（fake session_service 或直接断言 refresh_service 被调用），验证添加自选后即时刷新被触发、不再依赖市场状态
- [x] 2.2 新增/更新指数添加的测试：验证 `POST /api/index-watchlist` 添加成功后同样触发即时刷新
- [x] 2.3 新增测试：即时刷新抛异常时添加接口仍返回 201
- [x] 2.4 确认 `tests/unit/test_refresh_strategy.py` 中既有用例（午休/收盘后/节假日后台不刷新）保持通过且未改动其断言，证明周期刷新策略不受影响
- [x] 2.5 运行完整测试套件（`pytest`），确认无回归

## 3. 验证与收尾

- [ ] 3.1 手动验证：休市时段（或临时将市场状态置为 CLOSED 的测试环境）添加自选与指数，确认页面立即显示行情
- [x] 3.2 运行 `openspec validate fetch-quote-on-add` 确认工件合规
