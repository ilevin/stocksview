# v0.03：标签系统、Alembic 迁移与可观测性

## Why

v0.02 已以 Docker 方式部署上线，但存在三类制约长期维护的缺口：①自选证券只能平铺展示，数量增长后无法按自己的分类方式（高股息、科技等）聚焦查看；②数据库结构仅靠 `Base.metadata.create_all()` 创建，只能处理"表不存在→创建"，无法对已运行的生产库安全地新增字段/外键、随版本升级；③后台 Job 与第三方 Provider 的健康状况只能翻日志，无法快速回答"行情任务最近一次成功是什么时候""数据源是报错了还是超时了"。v0.03 在保持 FastAPI + SQLite + Jinja2 + Provider 单体架构不变的前提下，补齐这三类能力。

技术方案全文见 `StocksView_v0.03_技术方案设计.md`（39 节，本变更的设计依据）。

## What Changes

### 业务功能

- **标签系统**：新增 `tag` 表（表名取单数，与现有 7 张表命名约定一致；偏离技术方案字面 "tags" 的理由见 design D1）与标签管理页 `/tags`；标签支持新增/改名/删除，名称 trim 后非空、唯一、限长；被股票/ETF 引用的标签禁止删除（409）。
- **自选条目关联标签**：`watchlist` 增加 `tag_id` 可空外键（ON DELETE RESTRICT 语义）；一个自选条目最多关联一个标签；指数不可设标签；提供设置/解除标签 API；自选管理页增加标签下拉（仅可选已有标签，不支持就地新建）。
- **行情页标签筛选**：行情页顶部增加标签筛选（全部/指定标签/无标签）；`GET /api/quotes` 支持 `tag_id` 与 `untagged` 参数，items 增加 `tag` 对象；筛选为纯展示层过滤，SHALL NOT 触发新的 Provider 请求。
- **版本信息**：新增 `app/version.py` 作为全项目唯一版本号来源；行情页底部显示 `StocksView v0.03`；`/health` 返回 `version` 字段。

### 架构改进

- **Alembic 数据库迁移**：新增 `alembic.ini` 与 `alembic/` 目录；建立 `0001_v002_baseline` 基线（v0.02 发布时结构）与 `0002_v003` 增量迁移（tag 表、watchlist.tag_id、job_status 表）；SQLite 上使用 batch_alter_table；容器启动流程改为 `alembic upgrade head` 成功后才启动应用，迁移失败 SHALL 阻止启动；生产环境 schema 升级职责从 create_all 移交 Alembic（create_all 仅保留给测试环境）。
- **后台 Job last-success 状态**：新增 `job_status` 表（last_started_at/last_success_at/last_error_at/last_error/last_duration_ms/consecutive_failures）；QuoteRefreshJob 与 FundamentalRefreshJob 统一经 JobStatusService 记录状态；失败不清除 last_success_at，成功清零 consecutive_failures；新增 `GET /api/admin/status` 可查看。
- **Provider timeout 与 metrics**：三个 Provider（Tencent/AKShare/Tushare）均有明确超时配置（`providers.timeout.{tencent,akshare,tushare}` 子节，默认 8/15/15 秒，结构见 design D11）；统一 ProviderMetrics 包装层统计 request/success/error/timeout 计数与最近耗时/时间（内存 + 结构化日志，不建表）；error 与 timeout 分开统计；超时后本次调用按失败处理、保留 Last Known Good 行情、下个刷新周期重试；`GET /api/admin/status` 同时返回 providers 指标。

所有改动向后兼容，无 BREAKING 变更。

## Capabilities

### New Capabilities

- `tag-management`: 标签资源的 CRUD API、命名校验（trim/非空/唯一/限长）、引用计数展示、删除保护（业务层 + 数据库约束双层）、标签管理页面 `/tags`。
- `db-migration`: Alembic 目录与版本管理、v0.02 baseline、v0.03 增量迁移、SQLite batch 模式、应用启动时自动 `alembic upgrade head`、迁移失败阻止启动、create_all 退位为测试环境机制。
- `job-status`: job_status 表结构与更新语义（开始/成功/失败三态）、JobStatusService 封装、两个既有 Job 的接入、`GET /api/admin/status` 的 jobs 数据。
- `provider-metrics`: Provider 超时配置（`providers.timeout` 子节，默认 8/15/15 秒）、失败与超时后的行为（保留旧行情、下周期重试）、ProviderMetrics 统一包装层、`GET /api/admin/status` 的 providers 数据。
- `app-version`: 版本号唯一来源 `app/version.py`、行情页 footer 展示、`/health` 返回版本。

### Modified Capabilities

- `watchlist-management`: 新增自选条目与标签的关联行为——设置/解除标签 API（PATCH）、一个条目最多一个标签、指数拒绝设置标签（400）、自选管理页面增加标签列与编辑下拉、列表响应增加 tag 字段（删除自选后引用计数递减归 tag-management capability）。
- `dashboard-ui`: 行情页新增标签筛选交互（全部/指定标签/无标签，前端本地过滤）；页面底部版本信息归 `app-version` capability。
- `rest-api`: `GET /api/quotes` 新增 `tag_id`/`untagged` 查询参数与 items 中 `tag` 字段；`/health` 响应增加 `version`；新增 `GET /api/admin/status` 端点（jobs + providers 运行状态）。
- `deployment`: 容器启动命令前置 `alembic upgrade head`（失败即退出）；README/部署文档补充 v0.02→v0.03 升级流程（含对已有库 stamp 基线）。
- `instrument-management`: 「数据库自动初始化」requirement 调整——首次启动建表从 `create_all` 改为 Alembic 迁移接管，生产环境 schema 由迁移历史唯一决定。

## Impact

- **代码**：`app/models/`（tag.py、job_status.py、watchlist 加 tag_id）、`app/api/`（tags.py、status.py、quotes 扩展、watchlist 扩展）、`app/services/`（tag_service.py、job_status_service.py）、`app/observability/provider_metrics.py`、`app/version.py`、`app/templates/`（tags.html 新增、index/watchlist 页改造）、根目录 `alembic.ini` + `alembic/`、`Dockerfile`（启动命令）、`config.yaml`（新增 providers.timeout 超时节）。
- **API**：新增 `GET/POST/PATCH/DELETE /api/tags`、`PATCH /api/watchlist/{instrument_id}/tag`、`GET /api/admin/status`；扩展 `GET /api/quotes`、`GET /health`。全部向后兼容。
- **数据库**：新增 tag、job_status 两表与 watchlist.tag_id 列；v0.02 线上库经 Alembic 无损升级，原有四类数据（Instrument/Watchlist/QuoteSnapshot/FundamentalSnapshot）完整保留，已有自选默认 tag_id=NULL。
- **依赖**：pyproject.toml 新增 `alembic`。
- **部署**：线上 v0.02 容器（端口 8765，手动 docker run）升级到 v0.03 时按既有拓扑用新镜像重建容器；开发调试期间使用新端口与临时数据路径，不影响已部署版本。
