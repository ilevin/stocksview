# Spec: instrument-management

证券基础信息模型与 instrument_id 体系。

## ADDED Requirements

### Requirement: instrument_id 生成规则

系统 SHALL 使用 `market + asset_type + symbol` 生成全局唯一 `instrument_id`，格式为 `MARKET:ASSET_TYPE:SYMBOL`。

#### Scenario: A股股票
- **WHEN** symbol=600519, market=CN, asset_type=STOCK
- **THEN** instrument_id 为 `CN:STOCK:600519`

#### Scenario: 指数代码与股票代码同码不同类型
- **WHEN** symbol=000001, market=CN, asset_type=INDEX
- **THEN** instrument_id 为 `CN:INDEX:000001`，与 `CN:STOCK:000001` 不冲突

#### Scenario: 港股
- **WHEN** symbol=00700, market=HK, asset_type=STOCK
- **THEN** instrument_id 为 `HK:STOCK:00700`

### Requirement: instrument 存储

系统 SHALL 将证券基础信息保存到 SQLite `instrument` 表，包含 instrument_id（UNIQUE）、symbol、name、market、asset_type、exchange（可空）、currency、is_active、created_at、updated_at。market 仅允许 CN/HK；asset_type 仅允许 STOCK/ETF/INDEX；currency 为 CNY/HKD。

#### Scenario: 首次保存
- **WHEN** 添加一个新证券
- **THEN** instrument 表插入一条记录，instrument_id 唯一

#### Scenario: 重复保存幂等
- **WHEN** 同一 instrument_id 再次写入
- **THEN** 不产生重复记录，名称等信息可更新

### Requirement: 名称自动识别

添加标的时系统 SHALL 通过 Provider 自动获取证券名称；名称无法识别时 SHALL 添加失败并返回明确错误，不允许保存未知证券。

#### Scenario: 识别成功
- **WHEN** 添加 CN/STOCK/600519
- **THEN** 保存名称为"贵州茅台"

#### Scenario: 识别失败
- **WHEN** 添加的代码在数据源中不存在
- **THEN** 返回错误信息，不写入 watchlist 或 index_watchlist

### Requirement: 数据库自动初始化

应用启动时系统 SHALL 自动创建 SQLite 数据库与全部表，无需用户手工执行 SQL。

#### Scenario: 首次启动
- **WHEN** data 目录无数据库文件时启动应用
- **THEN** 自动建立数据库和表，服务正常启动
