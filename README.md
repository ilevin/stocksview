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
alembic upgrade head          # 建表/升级数据库结构（v0.03 起必须，取代自动建表）
uvicorn app.main:app --reload
```

访问 <http://localhost:8000>。数据库结构自 v0.03 起由 Alembic 管理：启动前必须执行
`alembic upgrade head`（容器镜像已内置该步骤），迁移失败时应用不会启动。

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

容器启动命令为 `alembic upgrade head && uvicorn app.main:app`：每次启动先自动执行数据库迁移，成功后才启动应用；迁移失败容器直接退出（不会出现代码与数据库版本不一致的情况）。

## v0.02 → v0.03 升级（操作手册）

适用于已有 v0.02 部署：数据库已有 v0.02 表结构，但没有 Alembic 版本记录（v0.02 时代由 `create_all` 建表）。升级分两段：先给既有库**打基线标记**（stamp，不执行 DDL），再由新容器启动时**自动执行增量迁移**（`alembic upgrade head`，新增 tag / job_status 表与 watchlist.tag_id 列）。

以下命令假设：数据目录 `./data`、配置 `./config.yaml`、容器名 `stock-dashboard`。按实际部署调整路径与端口（如线上 `-p 23.94.2.230:8765:8000`、挂载 `/opt/stocksview/data` 等，替换对应部分即可）。

升级期间服务中断约 1-2 分钟（停旧容器到新容器就绪）。

### 第 1 步：备份数据库（升级前必须）

```bash
sudo cp data/market.db data/market.db.v002.bak
```

### 第 2 步：构建 v0.03 镜像

```bash
sudo docker build -t stock-dashboard:v0.03 .
# 如线上容器引用无 tag 的 stock-dashboard（latest），同步更新引用：
sudo docker tag stock-dashboard:v0.03 stock-dashboard:latest
```

### 第 3 步：停旧容器

```bash
sudo docker rm -f stock-dashboard
```

### 第 4 步：给既有库打基线标记（stamp）

```bash
sudo docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/config.yaml:/app/config.yaml:ro" \
  stock-dashboard:v0.03 alembic stamp 0001_v002_baseline
```

输出 `Running stamp_revision -> 0001_v002_baseline` 即成功。此步只写入 `alembic_version` 表（标记"当前结构 = v0.02 基线"），不改动任何数据。

### 第 5 步：启动新容器（自动执行增量迁移）

```bash
sudo docker run -d --name stock-dashboard \
  --restart unless-stopped \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/config.yaml:/app/config.yaml:ro" \
  stock-dashboard:v0.03
```

容器启动命令为 `alembic upgrade head && uvicorn ...`：先执行 0002 迁移（建 tag / job_status 表、watchlist 加 tag_id 列），成功后才启动应用；迁移失败容器直接退出且数据无损。

### 第 6 步：验收

```bash
# 版本号应为 v0.03
curl -s http://localhost:8000/health
# 期望: {"status":"ok","database":"ok","version":"v0.03"}

# 自选/指数数量与升级前一致，tag 全部为 null（默认无标签）
curl -s http://localhost:8000/api/watchlist | python3 -c \
  "import sys,json; d=json.load(sys.stdin)['items']; print('自选数:', len(d), 'tag全null:', all(i['tag'] is None for i in d))"
curl -s http://localhost:8000/api/index-watchlist | python3 -c \
  "import sys,json; print('指数数:', len(json.load(sys.stdin)['items']))"

# 运行状态接口可用（后台任务 + 数据源指标）
curl -s http://localhost:8000/api/admin/status | head -c 400

# 页面：行情页底部版本号、标签管理页、自选管理页标签列
```

### 回滚

```bash
sudo docker rm -f stock-dashboard
sudo cp data/market.db.v002.bak data/market.db   # 恢复备份
# 使用 v0.02 镜像按原参数重新启动（v0.03 新增的表/列对 v0.02 代码不可见，不影响运行）
```

### 常见问题

- **忘记执行 stamp（第 4 步）**：新容器启动时基线迁移建表报"表已存在"，容器退出、数据无损。补执行第 4 步后重新启动即可。
- **全新部署**（`data/` 为空）：无需 stamp，直接从第 5 步开始，启动时从零建全表。
- **后续版本升级（v0.03 → v0.04+）**：数据库已有版本记录，**不再需要 stamp**，直接构建新镜像替换容器即可（启动自动增量迁移）。


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

### 数据源超时（v0.03）

```yaml
providers:
  timeout:
    tencent: 8      # 秒；缺省时使用默认值 8
    akshare: 45     # 秒；akshare 内部请求不受控，由包装层限时执行
    tushare: 15     # 秒
```

超时后该次调用按失败处理：保留最后一次成功行情（不删缓存），下一个刷新周期自动重试。成功 / 报错 / 超时分别计数，可通过 `GET /api/admin/status` 查看各数据源运行指标（request/success/error/timeout 计数、最近耗时与最近成功/失败时间）。

## 标签（v0.03）

股票 / ETF 自选支持标签分类（指数不支持）：先在「标签管理」页（`/tags`）创建标签，再到「自选管理」页点击操作列「标签」按钮，在弹层中点击标签添加 / 取消关联（即时保存）。一个自选条目可关联多个标签；被引用的标签不能删除（需先解除全部关联）。行情首页可按标签筛选（全部 / 指定标签 / 无标签），筛选为前端本地过滤，不会增加数据源请求。

## 运行状态

- `GET /health`：应用与数据库健康 + 当前版本号
- `GET /api/admin/status`：后台任务最近运行状态（最近开始/成功/失败时间、耗时、连续失败次数）与各数据源运行指标

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
├── version.py         # 应用版本号唯一来源
├── db.py              # engine / session / PRAGMA foreign_keys
├── api/               # quotes / watchlist / index_watchlist / admin / status / tags 路由
├── models/            # SQLAlchemy 模型（instrument / watchlist / quote / fundamental / tag / job_status ...）
├── schemas/           # API Pydantic Schema
├── providers/
│   ├── base.py        # Quote/Fundamental 模型与 Provider Protocol
│   ├── instrument_names.py
│   ├── quote/         # akshare（A股股票）/ tencent（其余）行情 Provider + 注册表（含超时注入）
│   ├── fundamental/   # tushare 估值 Provider
│   └── trading_calendar/  # 交易日历（Tushare + SQLite 缓存）
├── observability/     # ProviderMetrics 指标与超时包装层
├── repositories/      # 数据访问
├── services/          # market_session / quote_cache / refresh / watchlist / tag / job_status
├── jobs/              # 60 秒行情刷新任务、估值刷新任务（均接入 JobStatus）
├── templates/         # index.html / watchlist.html / tags.html（Jinja2）
└── static/            # 原生 JS / CSS
alembic/               # 数据库迁移（versions/0001_v002_baseline、0002_v003）
alembic.ini
tests/                 # unit + integration（含迁移测试）
```
