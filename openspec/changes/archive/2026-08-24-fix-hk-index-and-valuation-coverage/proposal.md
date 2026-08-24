# 变更提案：修复港股指数添加与估值覆盖缺口

## Why

用户报告两个线上缺陷：① 无法添加恒生科技指数，报错「无法识别证券: HK/INDEX/HS2083」；② 部分自选 A 股的 PE(TTM)/PB/股息率(TTM) 一直为空。经排查确认两处根因：

1. **港股指数添加**：`HS2083` 本身不是有效代码（恒生科技指数的通用代码为 `HSTECH`，腾讯接口 `r_hkHSTECH` 实测可用，机制并无缺陷），但系统存在两个放大问题：腾讯代码区分大小写（输入 `hstech` 即识别失败，实测 `r_hkhstech` 无返回）；前端提示与报错信息均只示例 A 股代码，用户无从得知港股指数应填什么。
2. **估值覆盖缺口**：`FundamentalRefreshJob` 用 `has_data_for_date`（当日有任意一条估值即认为已刷新）作为跳过条件。线上实例 2026-08-21 09:39 刷新时自选只有 1 只 A 股（日志 `updated=1 failed=0`），之后添加的 9 只股票因当日已有数据而永远不会被补抓，直到下一个交易日。且添加自选时只即时刷新行情、不获取估值。

## What Changes

- 添加证券时对 symbol 统一规范化：strip + 转大写（港股指数代码为字母，如 `HSTECH`/`HSI`/`HSCEI`；A 股/港股股票与 ETF 代码均为数字，不受影响）
- 名称识别失败的错误信息附带代码指引（提示常见港股指数代码与大小写要求）
- 指数添加表单 placeholder 与 README 补充港股指数代码示例（`HSTECH` 恒生科技指数等）
- 估值刷新的跳过条件由「当日有任意估值数据」改为「当日自选 A 股已全覆盖」：存在缺失即在下一次周期检查（30 分钟）时补刷当日全量数据
- 对当日确实无数据的股票（停牌/新股，Tushare 无该日记录）在内存中标记已尝试，避免每 30 分钟重复请求
- 添加自选股票成功后立即获取该股估值（per-stock 查询最近交易日数据），失败不影响添加结果——与「添加后即时行情刷新」的既有模式一致

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `fundamental-provider`: 「更新频率」需求修正为按自选 A 股覆盖率判定是否跳过；新增停牌/无数据标的的防重试语义；新增添加自选后立即获取该股估值的需求
- `instrument-management`: 新增 symbol 输入规范化需求（strip + 大写化，港股指数代码大小写不敏感）；「名称自动识别」的错误信息增加代码指引
- `watchlist-management`: 「股票/ETF 自选添加」需求新增添加成功后触发该股估值获取（仅 CN/STOCK 有意义）；「自选管理页面」的指数添加提示涵盖港股指数代码示例

## Impact

- `app/services/watchlist_service.py`: `add()` 中 symbol 规范化；识别失败异常信息增加指引
- `app/jobs/fundamental_refresh.py`: `_maybe_run` 改为覆盖率判定；新增 `refresh_instruments()`（按 instrument_id 列表补抓估值）；内存 attempted 集合防重复请求
- `app/repositories/fundamental.py`: 新增按 instrument_id 集合查询当日覆盖情况的方法（`has_data_for_date` 保留或调整语义由 design 决定）
- `app/api/watchlist.py`: 添加成功后触发该股估值获取（仿照 `_trigger_refresh`）
- `app/templates/watchlist.html`: 指数代码输入框 placeholder 更新
- `README.md`: 补充港股指数代码说明（HSI/HSCEI/HSTECH/CES100 等）
- 测试：`tests/unit/test_instrument_id.py` 或新增 service 层单测（大小写规范化）、fundamental job 覆盖率判定单测、watchlist API 集成测试（添加后估值获取触发）
- 无 API 契约变化、无数据库结构变化、无依赖变化

### 不在本次范围

- 不支持按中文名称检索/添加指数
- 港股不提供 PE/PB/股息率（PRD V1 范围仅 A 股股票）
- 已知独立问题：HK 交易日历 Tushare 返回空导致降级警告每分钟刷屏（`Tushare 交易日历返回为空（market=HK...)`），与本变更无关，另行处理
