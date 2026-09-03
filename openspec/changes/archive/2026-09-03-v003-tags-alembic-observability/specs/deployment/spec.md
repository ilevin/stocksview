## MODIFIED Requirements

### Requirement: Dockerfile

项目 SHALL 提供 Dockerfile，支持 `docker build -t stock-dashboard .` 构建镜像；镜像 SHALL 包含 Alembic 迁移资产（alembic.ini 与 alembic/ 目录）及 alembic 依赖；容器启动命令 SHALL 先执行 `alembic upgrade head`，成功后再启动 uvicorn，迁移失败 SHALL 使容器退出。

#### Scenario: 构建镜像
- **WHEN** 执行 docker build
- **THEN** 成功产出可运行镜像，含迁移资产

#### Scenario: 容器启动自动迁移
- **WHEN** 启动容器且数据库为空或落后于最新迁移
- **THEN** 启动流程先完成 alembic upgrade head，随后应用就绪

#### Scenario: 迁移失败容器退出
- **WHEN** 容器启动时 alembic upgrade head 失败
- **THEN** 容器以非零码退出，uvicorn 不启动

### Requirement: 本地启动

项目 SHALL 支持 Python 3.11+ 本地启动：venv + `pip install -e .` + 复制配置 + `alembic upgrade head` + `uvicorn app.main:app`。

#### Scenario: 本地运行
- **WHEN** 按 README 步骤本地启动
- **THEN** 服务运行且 GET /health 返回 200

### Requirement: README

README SHALL 包含：项目介绍、环境要求、本地启动、Tushare 配置（config.yaml 方式）、Docker 启动、各资产类型字段支持情况、行情刷新说明（60 秒/午休/收盘/节假日停止/收盘补抓）、数据源与延迟说明、Provider 超时配置（providers.timeout）、以及 v0.02→v0.03 升级流程（备份、stamp 基线、upgrade）。

#### Scenario: 按文档部署
- **WHEN** 新用户按 README 操作
- **THEN** 能完成配置并启动应用

#### Scenario: 按文档升级
- **WHEN** v0.02 用户按 README 升级章节操作
- **THEN** 完成备份、基线标记与升级，数据无损且版本显示 v0.03

## ADDED Requirements

### Requirement: v0.02 到 v0.03 升级部署流程

对已有 v0.02 部署（含既有数据卷），升级流程 SHALL 为：备份数据库 → 停旧容器 → 以新镜像执行一次性容器 `alembic stamp 0001_v002_baseline`（挂载既有数据卷）→ 以新镜像启动正式容器（自动 upgrade head 后启动应用）。升级失败 SHALL 可通过恢复备份与旧镜像回滚。

#### Scenario: 线上库升级演练
- **WHEN** 用 v0.02 数据库副本按升级流程操作并在临时端口验证
- **THEN** 升级后原有自选/指数/快照数据完整，/health 显示 v0.03
