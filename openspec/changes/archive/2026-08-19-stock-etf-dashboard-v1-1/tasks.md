# 任务清单：股票与 ETF 行情看板 V1.1

按 PRD Phase 1 -> Phase 9 顺序组织；每个 Phase 完成后运行测试并保持项目可运行，再进入下一阶段。

## 1. Phase 1：项目骨架

- [x] 1.1 创建 `pyproject.toml`（Python 3.11+，依赖：fastapi、uvicorn、jinja2、sqlalchemy>=2、pydantic、pyyaml、akshare、tushare、httpx、pytest 等，含 dev extras）与 `.gitignore`（config.yaml、data/、__pycache__ 等）
- [x] 1.2 实现 `app/config.py`：读取 config.yaml -> Pydantic 配置模型（database、quote.refresh_seconds=60/stale_seconds=180、tushare.token、providers、logging），Token 缺失时允许启动并记录配置错误；提供 `config.example.yaml`（假 Token）
- [x] 1.3 实现 `app/db.py`：SQLAlchemy engine/Session，SQLite 自动建库建表（create_all），`app/models/__init__.py` 汇总模型
- [x] 1.4 实现 `app/main.py`：FastAPI 应用、lifespan、Jinja2 模板与静态文件挂载、`GET /health`（检查数据库，不调数据源）、标准 logging 初始化（脱敏）
- [x] 1.5 验证：服务启动、`GET /health` 返回 `{"status":"ok","database":"ok"}`、数据库自动创建；编写配置读取单测（Token 读取、缺失报错、日志不输出 Token）

## 2. Phase 2：数据模型与 Repository

- [x] 2.1 实现 instrument_id 生成工具（`market + asset_type + symbol`）及单测（600519+CN+STOCK -> CN:STOCK:600519；000001+CN+INDEX -> CN:INDEX:000001）
- [x] 2.2 实现 SQLAlchemy 模型：Instrument（instrument_id UNIQUE）、Watchlist（UNIQUE instrument_id，仅 STOCK/ETF）、IndexWatchlist（UNIQUE，仅 INDEX）、QuoteSnapshot（price/change_percent/volume_ratio/previous_close/source/source_timestamp/fetched_at）、FundamentalSnapshot（UNIQUE(instrument_id, trade_date)）、AppSetting
- [x] 2.3 实现数值清洗工具 `safe_float`（"-"/""/None/NaN/inf -> None）及单测
- [x] 2.4 实现 Repository 层（instrument、watchlist、index_watchlist、quote、fundamental）：基本 CRUD、upsert 快照、最近快照查询，配 SQLite 内存库单测

## 3. Phase 3：自选与指数配置 API + 页面

- [x] 3.1 定义 Pydantic schemas（instrument/quote/watchlist/index_watchlist 请求与响应模型）
- [x] 3.2 实现 `app/api/watchlist.py`：GET/POST/DELETE/PUT order（201/409/404/204；POST 时校验 STOCK/ETF、经 Provider 识别名称、OPEN 市场触发一次该资产行情更新）
- [x] 3.3 实现 `app/api/index_watchlist.py`：GET/POST/DELETE/PUT order（仅 INDEX；重复 409）
- [x] 3.4 实现 WatchlistService / IndexWatchlistService（业务逻辑、日志记录增删）
- [x] 3.5 实现 `/watchlist` 页面（templates/watchlist.html + 原生 JS/CSS）：股票/ETF 与指数两个管理区域，增删排序、空状态提示
- [x] 3.6 编写 API 集成测试：添加/重复添加（409）/删除/排序、指数禁止 STOCK/ETF、名称识别失败 404

## 4. Phase 4：AKShare QuoteProvider

- [x] 4.1 实测 AKShare 接口（在 Python 环境中验证真实接口与列名，不凭记忆猜测）：A股股票 spot、A股ETF spot、港股 spot、A股指数 spot、港股指数 spot，以及代码->名称识别接口；记录实际列名
- [x] 4.2 实现 `app/providers/base.py`：Quote/Fundamental 内部模型、QuoteProvider/FundamentalProvider/TradingCalendarProvider Protocol
- [x] 4.3 实现 `app/providers/quote/akshare.py`：六类资产分派、全市场接口内存过滤、中文列名映射（仅存在于 Provider 内）、safe_float 清洗、超时与单次重试、港股 delayed 标记
- [x] 4.4 编写 Provider 转换单测（构造样例 DataFrame -> Quote，覆盖股票、ETF、指数、脏值）

## 5. Phase 5：交易时段与行情刷新

- [x] 5.1 实现 `app/providers/trading_calendar/`：is_trading_day(market, date)，Tushare 日历 + SQLite 缓存（按年批量），验证港股日历可用数据源并兼容
- [x] 5.2 实现交易日历时区规则：查询日期一律由 `now.astimezone(ZoneInfo("Asia/Shanghai")).date()` 推导，禁止裸 `datetime.now()`/UTC 日期；AKShare 无时区时间字符串统一按北京时间 localize；全链路 datetime 带 tz
- [x] 5.3 编写时区单测：容器 UTC 时区下北京 10:00 判定 OPEN、北京时间跨日边界（UTC 日期 vs 北京日期不同）日历查询取北京日期、系统时区 UTC/Shanghai 双环境下判定结果一致
- [x] 5.4 实现 `app/services/market_session_service.py`：状态判定（OPEN/LUNCH_BREAK/CLOSED/HOLIDAY）、should_refresh、A股港股独立判断、Asia/Shanghai 带时区时间
- [x] 5.5 编写 MarketSessionService 单测：A股/港股上午、午休、下午、收盘、非交易日九种场景
- [x] 5.6 实现 `app/services/quote_cache.py`（内存 dict + SQLite 回退 + 启动预热）与 `app/services/refresh_service.py`（按市场分组、仅 OPEN 刷新、单市场失败隔离、OPEN->CLOSED 收盘补抓边沿检测）
- [x] 5.7 实现 `app/jobs/quote_refresh.py`：lifespan 启动的 60 秒 asyncio 循环（AKShare 同步调用走 to_thread）
- [x] 5.8 实现 `GET /api/quotes` 与 `GET /api/indices`（读缓存、market_status、is_stale 计算含非交易时段不 stale）
- [x] 5.9 编写刷新策略与 stale 单测：OPEN 刷新/午休不刷新/收盘后不刷新/节假日不刷新/两市场独立/收盘补抓一次/180 秒 stale/收盘后不自动 stale/Provider 失败返回最后缓存

## 6. Phase 6：行情首页

- [x] 6.1 实现 `templates/index.html` + `app/static/app.js` + `app/static/style.css`：市场状态区、指数横向卡片区（仅名称/点位/涨跌幅）、自选行情表格（10 列、`-` 缺失、右对齐、红涨绿跌、港股·延时标识、stale ⚠）
- [x] 6.2 实现前端轮询：首次加载立即拉取；任一市场 OPEN 时 60 秒轮询；全部非 OPEN 停止轮询保留数据；错误提示

## 7. Phase 7：Tushare 估值与基本面

- [x] 7.1 实现 `app/providers/fundamental/tushare.py`：daily_basic -> Fundamental（pe_ttm/pb/dv_ttm），Token 从配置对象读取，缺失/失败降级 None 并记日志
- [x] 7.2 实现 `app/jobs/fundamental_refresh.py`：每日收盘后一次 + 启动时当天无数据补一次；保存 FundamentalSnapshot；证券基础信息每日更新
- [x] 7.3 合并估值到 `GET /api/quotes`（ETF/指数不写估值）；编写 Tushare Provider 单测（mock 接口、脏值、无 Token 场景）

## 8. Phase 8：容错与日志完善

- [x] 8.1 全局异常处理：Provider 失败不 500、后台任务异常不退出、AKShare/Tushare 失败日志、单证券解析失败日志
- [x] 8.2 模拟网络错误的集成测试（mock Provider 抛异常）：页面/接口仍返回最后缓存数据
- [x] 8.3 补齐日志：启动、建库、刷新开始/完成、自选增删、任务异常（复核无 Token 泄露）

## 9. Phase 9：Docker 与 README

- [x] 9.1 编写 Dockerfile（单容器，含数据目录挂载点；显式设置 `TZ=Asia/Shanghai` 作为时区双保险，代码不依赖它）
- [x] 9.2 编写 docker-compose.yml（仅应用容器，挂载 ./data 与 ./config.yaml:ro）
- [x] 9.3 编写 README：介绍、环境要求、本地启动、Tushare 配置、Docker 启动、各资产字段支持情况、刷新机制说明（60 秒/午休/收盘/节假日/补抓）、数据源与延迟说明
- [x] 9.4 验证：`cp config.example.yaml config.yaml && docker compose up -d` 后 http://localhost:8000 可访问（或本地等效验证），全量测试通过

## 10. 收尾验收

- [x] 10.1 对照 PRD 第 32 节验收标准逐项核查（功能/行情/自动更新/基本面/配置/容错/部署）
- [x] 10.2 输出 PRD 第 35 节要求的总结：目录结构、已完成功能、实际使用的数据源接口、各资产字段支持、已知限制、本地/Docker 启动方法、测试方法、后续 3 个改进建议
