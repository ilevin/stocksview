## ADDED Requirements

### Requirement: symbol 输入规范化

系统 SHALL 在添加证券时对 symbol 统一规范化：去除首尾空白并转为大写。港股指数代码为字母缩写（如 HSTECH），SHALL 大小写不敏感；规范化 SHALL 在自选唯一性判定之前完成，避免同一证券因大小写不同产生重复配置。

#### Scenario: 港股指数代码大小写不敏感
- **WHEN** 添加 `HK/INDEX/hstech`
- **THEN** 规范化为 `HK:INDEX:HSTECH`，名称识别与行情获取正常

#### Scenario: 大小写不同不产生重复配置
- **WHEN** 已有 `HK:INDEX:HSTECH` 时再添加 `HK/INDEX/hstech`
- **THEN** 返回 409 Conflict（重复添加），不产生新记录

#### Scenario: 含空白的代码
- **WHEN** 添加 symbol 为 `" 600519 "`
- **THEN** 规范化为 `"600519"` 后正常处理

## MODIFIED Requirements

### Requirement: 名称自动识别

添加标的时系统 SHALL 通过 Provider 自动获取证券名称；名称无法识别时 SHALL 添加失败并返回明确错误，不允许保存未知证券。港股指数识别失败时，错误信息 SHALL 附带代码格式指引（字母缩写及常见指数代码示例）。

#### Scenario: 识别成功
- **WHEN** 添加 CN/STOCK/600519
- **THEN** 保存名称为"贵州茅台"

#### Scenario: 识别失败
- **WHEN** 添加的代码在数据源中不存在
- **THEN** 返回错误信息，不写入 watchlist 或 index_watchlist

#### Scenario: 港股指数代码错误的指引
- **WHEN** 添加 `HK/INDEX/HS2083`（无效代码）导致识别失败
- **THEN** 错误信息在「无法识别证券」之外附带港股指数代码指引（如 HSI/HSCEI/HSTECH）
