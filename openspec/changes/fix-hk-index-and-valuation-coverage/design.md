# 技术设计：修复港股指数添加与估值覆盖缺口

## Context

- 行情名称识别与港股指数行情均走腾讯 `qt.gtimg.cn`，HK 指数代码映射为 `r_hk{symbol}`（`app/providers/quote/tencent.py:44`）。实测腾讯代码区分大小写：`r_hkHSTECH` 有数据，`r_hkhstech` 无返回。
- 线上（Docker 容器 stock-dashboard，23.94.2.230:8765）实测：fundamental_snapshot 中 10 只自选 A 股仅 `601318` 有 2026-08-20 数据；容器日志 `估值刷新完成: trade_date=2026-08-20 updated=1 failed=0`（当日刷新时自选仅 1 只 A 股）。根因是 `FundamentalRefreshJob._maybe_run` 的跳过条件 `has_data_for_date`（`app/jobs/fundamental_refresh.py:69`）：当日存在任意一条估值即跳过，后添加的股票永远不补。
- 添加自选时已有「即时行情刷新」机制（`app/api/watchlist.py:48` `_trigger_refresh`，fetch-quote-on-add 变更引入），估值无对应机制。
- 前端指数添加表单 placeholder 仅示例 A 股代码（`app/templates/watchlist.html:45`）；`InstrumentNotFoundError` 文案无任何指引。

## Goals / Non-Goals

**Goals:**

- 用户能用正确代码（如 `HSTECH`）添加港股指数；大小写输入不敏感；代码错误时报错能引导用户自查
- 当日已收盘数据发布后，自选 A 股的估值在 30 分钟周期检查内自动补齐（含盘中新添加的股票）
- 添加自选 A 股后立即获得该股最近一期估值

**Non-Goals:**

- 不支持中文名称检索证券
- 不为港股/ETF/指数提供估值（PRD V1 仅 A 股股票）
- 不处理 HK 交易日历降级警告刷屏问题（独立缺陷，另行变更）
- 不改变行情刷新策略（60 秒仅 OPEN 刷新，见 fetch-quote-on-add 边界）

## Decisions

### D1: symbol 规范化放在 WatchlistService.add（业务入口）

`add()` 中统一 `symbol = symbol.strip().upper()`。理由：

- A 股/港股的股票与 ETF 代码均为纯数字，大写化零影响；唯一字母代码是港股指数（HSI/HSCEI/HSTECH/CES100…），恰是需要大小写不敏感的场景
- 必须在 `repo.exists(instrument_id)` 判重之前完成，否则 `hstech` 与 `HSTECH` 会成为两条配置
- 不放在 `build_instrument_id`（纯格式校验工具，单测已锁定行为）；不放在 `to_tencent_code`（那只是识别路径，DB 会存入未规范化 symbol）

### D2: 识别失败错误信息按场景附加指引

仅 HK/INDEX 分支附加：`无法识别证券: HK/INDEX/HS2083。港股指数代码为字母缩写，常见如 HSI（恒生指数）、HSCEI（国企指数）、HSTECH（恒生科技指数），请核对后重试`。其他场景保持现有文案（避免无关噪音）。实现于 `WatchlistService.add` 抛 `InstrumentNotFoundError` 处。

### D3: 估值跳过条件改为「自选 A 股当日全覆盖」

- `FundamentalRepository` 新增 `instrument_ids_with_data(trade_date) -> set[str]`；删除 `has_data_for_date`（无其他调用方，保留易被误用回旧语义）
- `_maybe_run`：解析 latest_trade_date 后取自选 CN/STOCK 的 instrument_id 集合，`missing = ids - covered`；missing 为空才跳过
- 补刷复用 provider 的 trade_date 模式（单次 `daily_basic(trade_date=...)` 全市场查询后按 symbol 过滤），只传 missing 的 instruments，API 调用次数不变（1 次）
- `run_once(trade_date=None)` 保留给 admin 手动刷新：刷新全部自选 A 股、不查 attempted 集合、并清空该日期的 attempted（手动刷新即强制重试）

### D4: 内存 attempted 集合防止对无数据标的反复请求

停牌/新股在 Tushare 当日无记录，补刷后仍缺失；若无防护会每 30 分钟重复全市场查询并刷屏日志。方案：`self._attempted: dict[date, set[str]]`，`_refresh` 完成后将仍缺失的 instrument_id 并入 `attempted[trade_date]`，`_maybe_run` 计算 missing 时剔除。

- 备选「无条件每 30 分钟重刷」：日志与 API 调用无意义重复，弃用
- 备选「attempted 持久化到 DB」：引入新表/字段，收益仅是进程重启后少刷一次，过度设计，弃用
- 代价：进程重启后对无数据标的多刷一次（1 次 API 调用），可接受

### D5: 添加自选后同步获取该股估值（仿 `_trigger_refresh` 模式）

`app/api/watchlist.py` 的 `add_watchlist` 成功后调用 `_trigger_fundamental_refresh(request, instrument_id)`：

- 从 `app.state.fundamental_refresh` 取 job，调用新增的 `job.refresh_instruments([instrument_id])`
- `refresh_instruments`：按 id 取 instrument，`provider.get_fundamentals(insts)`（trade_date=None，per-stock 查询最近一期）→ 复用与 `run_once` 相同的 upsert 写库逻辑
- 仅 CN/STOCK 调用（api 层判断，避免无谓调用）；失败吞掉不影响 201 返回（与 `_trigger_refresh` 一致）
- 同步调用（FastAPI sync 路由本就跑在线程池），单次 Tushare 调用约 1~2 秒，可接受；不引入后台任务管理复杂度
- 边界与 [[fetch-quote-on-add]] 一致：添加时即时获取，后台仅按 D3 修正后的「每日收盘后一次 + 覆盖率补刷」，不引入盘中周期性估值刷新

### D6: 前端与文档

- `app/templates/watchlist.html` 指数输入框 placeholder 改为 `指数代码，如 000001（上证指数）、HSTECH（恒生科技指数）`
- README「数据源」小节补充港股指数代码格式说明与常见代码表（HSI/HSCEI/HSTECH/CES100，标注腾讯源可用性以实测为准）

### D7: per-stock 估值查询限定日期窗口（实现期发现）

实测（2026-08-21，真实 Token）：`daily_basic(ts_code=...)` 不带日期返回**全部历史**（约 6000 行、日期降序），而 `get_fundamentals` 遍历覆盖使同一 symbol 保留**最后一行（最早日期）**，导致添加自选后写入 2001 年上市初期的估值。修复：

- per-stock 分支增加 `start_date`/`end_date`（近 400 天窗口），控制响应体积与语义
- `get_fundamentals` 循环中同一 instrument 仅在 `trade_date` 更大时覆盖（防御性，trade_date 模式不受影响）
- 400 天窗口外的超长停牌股取不到 per-stock 数据，由当日全市场补刷与 attempted 标记兜底，可接受

### D8: 启动补刷改经日历 Provider（实现期发现）

原 `_latest_trade_date` 直接查 `TradingCalendarRepository`，而日历缓存由 quote job 触发的 `TushareTradingCalendarProvider._load_year` 填充。启动时 fundamental job 先于日历缓存完成（纯 DB 查询 vs 3 秒网络拉取），日历仓储为空 -> `trade_date=None` -> 补刷静默跳过，需等 30 分钟周期重试；线上旧日志能启动即刷属时序巧合。修复：

- `_latest_trade_date` 改用 `self.session_service.calendar.is_trading_day("CN", day)`（Provider 未缓存时自动拉取）
- 移除 job 不再使用的 `calendar_repo_factory` 构造参数（main.py 装配与测试同步更新）


### D9: 三指标全空的当日行视为未覆盖（实现期发现）

实测（2026-08-21，真实 Token）：Tushare `daily_basic` 当日的 `dv_ttm`（股息率）晚间才生成（22:29 时全市场为空、22:47 已回填）。旧版本因时序巧合总在次日刷前一日数据，从未暴露；本变更把当日首刷提前到收盘后，每日都会写入三指标部分为空的快照，当日股息率将显示为空。

修复：`covered_instrument_ids`（由 `instrument_ids_with_data` 改名并调整）只统计「三指标全非空」的行（实际缺口形态是 pe/pb 有值、仅 dv 为空）；任一指标为空的行参与周期补刷重试，回填后覆盖完成自动停止。attempted 标记仍只兜「请求结果完全无行」的标的（停牌/新股），不误伤空指标行。代价：指标当日确无值的标的（如亏损股 PE 为空、常年不分红股 dv 为空）每 30 分钟空转一次全市场查询至当日结束（约十余次/天），量级安全、日志如实反映缺失。

## Risks / Trade-offs

- [腾讯接口对未知港股指数代码仍无法识别] -> 属数据源能力边界；D2 的报错指引 + README 代码表降低试错成本，404 行为符合「不允许保存未知证券」的既有需求
- [attempted 为内存态，重启后丢失] -> 重启后多一次全市场查询，无数据正确性风险，接受
- [停牌/新股当日数据 Tushare 盘后才补] -> attempted 标记后当日不再自动重试；可用 `POST /api/admin/refresh/fundamentals` 手动强制刷新（D3 已保证手动刷新清空 attempted）
- [添加时同步 Tushare 调用拖慢 add 响应] -> 仅 CN/STOCK、单标的单次调用（约 1~2s）；失败静默不阻塞添加结果
- [upper() 规范化对未来新增市场代码的影响] -> 当前 VALID_MARKETS 仅 CN/HK 且代码全为数字或大写字母缩写；未来扩展市场时需重新评估

## Migration Plan

- 无数据库结构变更、无 API 契约变更，随下次镜像构建部署即生效
- 部署后首个 30 分钟周期内，`_maybe_run` 会发现线上既有缺口（9 只缺 2026-08-20/21 估值的股票）并自动补刷，无需人工干预
- 回滚：还原镜像即可，已写入的估值数据本身无害
