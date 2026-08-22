# 实现任务：修复港股指数添加与估值覆盖缺口

> 前置说明：`fetch-quote-on-add` 变更与本变更共同修改 watchlist-management 的「股票/ETF 自选添加」需求，归档顺序须为 fetch-quote-on-add 在前、本变更在后（本变更的 delta 已按其合并后文本编写）。

## 1. 港股指数添加修复（symbol 规范化与错误指引）

- [x] 1.1 `app/services/watchlist_service.py` `add()`：symbol 规范化为 `strip().upper()`（在 `build_instrument_id` 与 `repo.exists` 判重之前）
- [x] 1.2 `app/services/watchlist_service.py` `add()`：HK/INDEX 识别失败时，`InstrumentNotFoundError` 文案附加港股指数代码指引（HSI/HSCEI/HSTECH）
- [x] 1.3 `app/templates/watchlist.html`：指数输入框 placeholder 改为 `指数代码，如 000001（上证指数）、HSTECH（恒生科技指数）`
- [x] 1.4 `README.md`：数据源/使用说明补充港股指数代码格式与常见代码表（HSI、HSCEI、HSTECH、CES100）

## 2. 估值覆盖率补刷（fundamental job）

- [x] 2.1 `app/repositories/fundamental.py`：新增 `instrument_ids_with_data(trade_date) -> set[str]`；删除 `has_data_for_date`（确认无其他调用方后）
- [x] 2.2 `app/jobs/fundamental_refresh.py`：`_maybe_run` 改为覆盖率判定--取自选 CN/STOCK 集合与当日已有数据集合求差，缺失非空才刷新，且只刷缺失标的
- [x] 2.3 `app/jobs/fundamental_refresh.py`：新增 `self._attempted: dict[date, set[str]]` 内存标记，补刷后仍缺失的标的当日不再重试；`run_once`（手动刷新）忽略并清空当日标记
- [x] 2.4 `app/jobs/fundamental_refresh.py`：新增 `refresh_instruments(instrument_ids)`--按 id 取 instrument、provider per-stock 查询最近一期、复用 upsert 写库（供添加自选后即时调用）

## 3. 添加自选后的即时估值获取

- [x] 3.1 `app/api/watchlist.py`：`add_watchlist` 成功后，对 CN/STOCK 调用 `_trigger_fundamental_refresh(request, instrument_id)`（仿 `_trigger_refresh`，失败静默，不影响 201）

## 4. 测试

- [x] 4.1 单测：watchlist service symbol 规范化（`hstech` -> `HSTECH`、含空白输入、大小写不同判重 409）
- [x] 4.2 单测：HK/INDEX 识别失败错误文案包含 HSTECH 指引
- [x] 4.3 单测：fundamental job 覆盖率判定（全覆盖跳过、部分缺失补刷、attempted 标记后跳过、run_once 清空标记）
- [x] 4.4 单测：`refresh_instruments` 仅请求传入标的并 upsert；异常时不抛出（api 层静默）
- [x] 4.5 集成测试：`tests/integration/test_watchlist_api.py` 添加 CN/STOCK 后触发一次估值获取；添加 ETF/HK 不触发
- [x] 4.6 运行全量测试（`pytest`）确认无回归
- [x] 4.7 单测：per-stock 估值查询限定日期窗口且同股多行保留最新一期（D7，实现期发现）
- [x] 4.8 单测：`_latest_trade_date` 经日历 Provider 判定，启动初期日历未缓存不误判（D8，实现期发现）
- [x] 4.9 单测：三指标全空的当日行视为未覆盖、继续补刷；任一指标非空视为覆盖（D9，实现期发现）

## 5. 验证与部署

- [x] 5.1 本地启动验证：添加 `HK/INDEX/HSTECH`（及小写 `hstech`）成功识别为恒生科技指数并显示行情；`HK/INDEX/HS2083` 返回 404 且带代码指引
- [x] 5.2 本地验证估值：添加一只新 A 股后 fundamental_snapshot 立即写入该股估值（最新一期而非历史数据，D7）；启动时自动补刷（D8）
- [ ] 5.3 重新构建镜像并更新线上容器（docker compose），验证线上 9 只缺口股票在 30 分钟内补齐 2026-08-20/21 估值、恒生科技指数可添加
- [ ] 5.4 确认 fetch-quote-on-add 变更归档后再归档本变更（`openspec archive`）
