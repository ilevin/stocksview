# Spec: deployment

Docker 单容器部署与文档。

## ADDED Requirements

### Requirement: Dockerfile

项目 SHALL 提供 Dockerfile，支持 `docker build -t stock-dashboard .` 构建镜像。

#### Scenario: 构建镜像
- **WHEN** 执行 docker build
- **THEN** 成功产出可运行镜像

### Requirement: docker-compose 单容器运行

项目 SHALL 提供 docker-compose.yml，仅运行一个应用容器（无数据库容器），挂载 `./data:/app/data` 与 `./config.yaml:/app/config.yaml:ro`；执行 `cp config.example.yaml config.yaml && docker compose up -d` 后 SHALL 可通过 http://localhost:8000 访问。

#### Scenario: compose 启动
- **WHEN** 复制并填写配置后执行 docker compose up -d
- **THEN** 单容器启动，首页可访问，SQLite 数据持久化在宿主机 ./data

### Requirement: 本地启动

项目 SHALL 支持 Python 3.11+ 本地启动：venv + `pip install -e .` + 复制配置 + `uvicorn app.main:app`。

#### Scenario: 本地运行
- **WHEN** 按 README 步骤本地启动
- **THEN** 服务运行且 GET /health 返回 200

### Requirement: README

README SHALL 包含：项目介绍、环境要求、本地启动、Tushare 配置（config.yaml 方式）、Docker 启动、各资产类型字段支持情况、行情刷新说明（60 秒/午休/收盘/节假日停止/收盘补抓）、数据源与延迟说明。

#### Scenario: 按文档部署
- **WHEN** 新用户按 README 操作
- **THEN** 能完成配置并启动应用
