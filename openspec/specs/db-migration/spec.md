# db-migration Specification

## Purpose
TBD - created by archiving change v003-tags-alembic-observability. Update Purpose after archive.
## Requirements
### Requirement: Alembic 版本管理

系统 SHALL 使用 Alembic 管理数据库结构：提供 `alembic.ini` 与 `alembic/versions/` 迁移目录；版本链以 `0001_v002_baseline`（v0.02 发布时的完整结构）为基线，`0002_v003` 负责新增 tag 表、job_status 表与 watchlist.tag_id 列；后续版本 SHALL 在基线之上追加。迁移配置 SHALL 复用应用配置的 database.url 与模型 metadata。

#### Scenario: 空库全链升级
- **WHEN** 对空数据库执行 `alembic upgrade head`
- **THEN** 依次建立 v0.02 全部表与 v0.03 新增表/列，alembic_version 记录最新版本

#### Scenario: 迁移与模型一致
- **WHEN** `alembic upgrade head` 完成后比对模型 metadata 建表产物
- **THEN** 两者表集合、列与约束一致，无 schema 漂移

### Requirement: 应用启动时自动迁移

容器启动流程 SHALL 先执行 `alembic upgrade head`，成功后才启动应用；迁移失败时应用 SHALL NOT 启动（容器退出），避免代码与数据库结构版本不一致。应用 lifespan SHALL NOT 再以 `create_all` 建表；`create_all` 仅保留给测试环境使用。

#### Scenario: 全新容器首次启动
- **WHEN** 无历史数据时启动 v0.03 容器
- **THEN** 启动过程自动完成建表迁移，随后应用就绪

#### Scenario: 迁移失败阻止启动
- **WHEN** `alembic upgrade head` 执行失败
- **THEN** 容器退出，uvicorn 不启动，数据库保持迁移前状态

### Requirement: v0.02 到 v0.03 无损升级

对已有 v0.02 数据库（存在全部 v0.02 表、无 alembic_version 记录），升级流程 SHALL：先 `alembic stamp 0001_v002_baseline` 打基线标记（不执行 DDL），再 `alembic upgrade head` 仅执行 v0.03 迁移。升级后 Instrument、Watchlist、QuoteSnapshot、FundamentalSnapshot 数据 SHALL 完整保留，全部既有 Watchlist 行 tag_id 为 NULL（默认无标签）。

#### Scenario: 已有库打基线后升级
- **WHEN** 复制 v0.02 market.db，执行 stamp 基线后 upgrade head，启动 v0.03 应用
- **THEN** 原有自选、指数、行情快照、估值快照全部可查，自选默认无标签

#### Scenario: 未打基线直接升级
- **WHEN** 对已有 v0.02 表但无版本记录的库直接 `alembic upgrade head`
- **THEN** 基线迁移建表失败，流程终止且数据无损

### Requirement: SQLite 结构变更使用 batch 模式

SQLite 上涉及新增外键/约束的表结构变更 SHALL 使用 Alembic `batch_alter_table`（表重建）方式，SHALL NOT 依赖 SQLite 不支持的 `ALTER TABLE` 操作；重建 SHALL 保留原有唯一约束与索引及全部数据。

#### Scenario: watchlist 加列后约束完整
- **WHEN** 0002 迁移以 batch 方式为 watchlist 增加 tag_id 后检查 schema
- **THEN** `uq_watchlist_instrument` 唯一约束与既有索引仍存在，原有行数不变
