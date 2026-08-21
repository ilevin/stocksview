# 股票与 ETF 行情看板

个人自用的轻量行情看板：集中查看自选的 A 股 / 港股股票、ETF 与指数行情，并为 A 股股票提供 PE(TTM)、PB、股息率(TTM) 估值。

- 行情数据：AKShare（A 股股票，腾讯通道）+ 腾讯批量行情接口（ETF / 港股 / 指数）
- 估值数据：Tushare `daily_basic`（A 股股票）
- 单体应用：FastAPI + SQLite + Jinja2 + 原生 JS/CSS，无 Redis / MySQL / Node.js / 前端框架

## 环境要求

- Python 3.11+（本地运行），或 Docker
- 网络：需能访问 `qt.gtimg.cn`（行情）、`tushare.pro`（估值，可选）

## 本地启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
# 编辑 config.yaml，填写 tushare.token（不使用估值功能可不填）
uvicorn app.main:app --reload
```

访问 <http://localhost:8000>。

## 配置 Tushare

编辑 `config.yaml`：

```yaml
tushare:
  token: "实际 Token"
```

- Token 只从 `config.yaml` 读取，**不使用** `TUSHARE_TOKEN` 环境变量
- 未配置 Token 时应用可正常启动，仅估值功能（PE/PB/股息率）不可用并记录日志
- `config.yaml` 已加入 `.gitignore`，仓库只提交不含真实 Token 的 `config.example.yaml`

## Docker 启动

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml 填写 Token 后：
docker compose up -d
```

等价的直接运行方式（必须挂载 config.yaml 与 data 目录）：

```bash
docker build -t stock-dashboard .
docker run -d --name stock-dashboard \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/config.yaml:/app/config.yaml:ro" \
  stock-dashboard
```

访问 <http://localhost:8000>。SQLite 数据与配置均持久化在宿主机（`./data`、`./config.yaml`）。

## 数据支持情况

| 资产 | 价格 | 涨跌幅 | 量比 | PE(TTM) | PB | 股息率(TTM) | 备注 |
|---|---|---|---|---|---|---|---|
| A股股票 | ✅ | ✅ | ✅ | ✅(Tushare) | ✅(Tushare) | ✅(Tushare) | |
| A股ETF | ✅ | ✅ | ✅ | - | - | - | 不套用个股估值概念 |
| 港股股票 | ✅ | ✅ | - | - | - | - | 免费源为延时行情，标注「港股 · 延时」 |
| 港股ETF | ✅ | ✅ | - | - | - | - | 同港股股票 |
| A股指数 | ✅ | ✅ | - | - | - | - | 首页指数卡片区展示 |
| 港股指数 | ✅ | ✅ | - | - | - | - | 首页指数卡片区展示 |

指数配置与股票/ETF 自选独立管理（`/watchlist` 页面），指数显示在首页表格上方，不进入普通自选表格。

指数代码格式：A股指数为 6 位数字（如 `000001` 上证指数、`399001` 深证成指）；港股指数为**字母缩写**（大小写不敏感），常见如下：

| 代码 | 指数 |
|---|---|
| `HSI` | 恒生指数 |
| `HSCEI` | 恒生中国企业指数（国企指数） |
| `HSTECH` | 恒生科技指数 |
| `CES100` | 港股通100 |

代码以腾讯 `qt.gtimg.cn` 接口可识别为准，识别失败会在报错信息中提示。

## 行情刷新说明

- 交易时段内默认 **每 60 秒** 刷新一次后台行情（后台任务，浏览器只读缓存）
- A 股 / 港股 **独立判断** 市场状态：A 股收盘后港股仍交易时，仅刷新港股
- 午间休市（A 股 11:30-13:00 / 港股 12:00-13:00）：停止自动行情请求
- 收盘后、节假日：停止自动行情请求
- 市场状态从「交易中」切换为「已收盘」时，补抓一次收盘行情，避免缓存停留在收盘前一分钟
- 页面首次打开时无论是否交易都会读取一次缓存，收盘后仍能看到最后一次成功行情
- 数据源故障时页面不会报 500，仍显示最后一次成功数据（交易时段超过 180 秒未更新会标记 ⚠）

## 数据源说明

| 数据 | 来源 | 说明 |
|---|---|---|
| A股股票行情/量比 | AKShare `stock_zh_a_spot_tx` | 东财/新浪通道在部分网络环境不可用，故使用腾讯通道 |
| ETF/港股/指数行情 | 腾讯 `qt.gtimg.cn` 批量接口 | 港股为延时行情（约 15 分钟），页面明确标注 |
| A股估值 | Tushare `daily_basic` | 每日收盘后更新一次，需 Token |
| A股交易日历 | Tushare `trade_cal` | 按年缓存到 SQLite |
| 港股交易日历 | Tushare `trade_cal`(HKEX)，不可用时回退周一至周五近似 | 近似规则下港股节假日会尝试刷新（无害），不影响数据正确性 |

所有数据均可能存在延迟，仅供个人参考，不构成投资建议。

## 配置数据源切换

`config.yaml` 中 `providers.quote` 按市场/资产类型声明数据源（`akshare` / `tencent`），估值源在 `providers.fundamental` 中声明。后续增加新数据源只需实现 Provider 并在注册表登记。

## 测试执行方法

```bash
source .venv/bin/activate
pytest                       # 全部测试（不需要网络）
pytest -m online             # 在线冒烟测试（需要真实网络）
```

## 目录结构

```text
app/
├── main.py            # 应用入口、lifespan、页面路由、健康检查
├── config.py          # config.yaml -> Pydantic 配置模型
├── db.py              # engine / session / 建表
├── api/               # quotes / watchlist / index_watchlist / admin 路由
├── models/            # SQLAlchemy 模型
├── schemas/           # API Pydantic Schema
├── providers/
│   ├── base.py        # Quote/Fundamental 模型与 Provider Protocol
│   ├── instrument_names.py
│   ├── quote/         # akshare（A股股票）/ tencent（其余）行情 Provider + 注册表
│   ├── fundamental/   # tushare 估值 Provider
│   └── trading_calendar/  # 交易日历（Tushare + SQLite 缓存）
├── repositories/      # 数据访问
├── services/          # market_session / quote_cache / refresh / watchlist
├── jobs/              # 60 秒行情刷新任务、估值刷新任务
├── templates/         # index.html / watchlist.html（Jinja2）
└── static/            # 原生 JS / CSS
tests/                 # unit + integration
```
