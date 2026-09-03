## MODIFIED Requirements

### Requirement: 数据库自动初始化

应用启动流程 SHALL 自动完成数据库结构准备，无需用户手工执行 SQL：结构创建与升级由 Alembic 迁移负责（启动时执行 `alembic upgrade head`），SHALL NOT 依赖 `create_all` 作为生产建表机制；测试环境可继续使用 metadata 建表。

#### Scenario: 首次启动
- **WHEN** data 目录无数据库文件时启动应用
- **THEN** 启动流程经迁移自动建立数据库和全部表，服务正常启动

#### Scenario: 结构落后时自动升级
- **WHEN** 数据库结构落后于当前迁移版本时启动应用
- **THEN** 启动流程自动补齐结构至最新版本后启动服务
