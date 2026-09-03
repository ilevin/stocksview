## ADDED Requirements

### Requirement: 自选条目标签关联 API

系统 SHALL 提供 `PUT /api/watchlist/{instrument_id}/tags`，body 为 `{"tag_ids": [int...]}`：以全量集合替换该条目的全部标签关联（幂等；空数组即解除全部标签）。一个自选条目 SHALL 可同时关联多个标签（多对多）。自选条目不存在或任一 tag_id 不存在返回 404；指数类型返回 400。

#### Scenario: 股票设置多个标签
- **WHEN** PUT `/api/watchlist/CN:STOCK:600519/tags` `{"tag_ids": [3, 5]}`
- **THEN** 返回 200，该自选条目同时关联标签 3 与 5

#### Scenario: ETF 设置标签
- **WHEN** PUT ETF 自选条目 tags `{"tag_ids": [3]}`
- **THEN** 返回 200，该 ETF 关联标签 3

#### Scenario: 全量替换语义
- **WHEN** 条目已关联 [1, 2]，PUT `{"tag_ids": [2, 4]}`
- **THEN** 条目改为关联且仅关联 [2, 4]

#### Scenario: 解除全部标签
- **WHEN** 已有标签的条目 PUT tags `{"tag_ids": []}`
- **THEN** 返回 200，该条目 tags 为空

#### Scenario: 标签不存在
- **WHEN** PUT tags 传入含不存在 id 的数组
- **THEN** 返回 404

#### Scenario: 指数拒绝设置标签
- **WHEN** 对指数条目设置标签
- **THEN** 返回 400，指数不支持标签

## MODIFIED Requirements

### Requirement: 股票/ETF 自选查询与排序

系统 SHALL 提供 `GET /api/watchlist`（按 sort_order 返回列表）与 `PUT /api/watchlist/order`（批量更新排序）。列表 items SHALL 含 instrument_id、symbol、name、market、asset_type、sort_order、tags（`[{id, name}]` 数组，空数组表示无标签）。

#### Scenario: 查询列表
- **WHEN** GET /api/watchlist
- **THEN** 返回含 instrument_id、symbol、name、market、asset_type、sort_order、tags 的 items，无标签条目 tags 为空数组

#### Scenario: 调整排序
- **WHEN** PUT /api/watchlist/order 传入新的 instrument_id/sort_order 列表
- **THEN** 排序持久化，GET 按新顺序返回

### Requirement: 自选管理页面

系统 SHALL 提供 `/watchlist` 页面（Jinja2），包含股票/ETF 与指数两个独立管理区域，支持查看、添加、删除、调整排序操作。指数添加区域 SHALL 提示港股指数代码格式（字母缩写，示例含恒生科技指数 HSTECH）。股票/ETF 区域 SHALL 提供「标签」列：以行内可点击的标签 chips 展示全部已有标签（已关联高亮、未关联置灰，SHALL NOT 支持在此新建标签），点击 chip 即切换该标签的关联并保存；指数区域 SHALL NOT 出现标签列。

#### Scenario: 空状态
- **WHEN** 无任何自选时访问页面
- **THEN** 显示空状态提示，不报错

#### Scenario: 港股指数代码提示
- **WHEN** 访问 /watchlist 指数管理区域
- **THEN** 输入框提示同时包含 A 股与港股指数代码示例（如 000001 上证指数、HSTECH 恒生科技指数）

#### Scenario: 点击 chip 切换关联
- **WHEN** 在股票/ETF 行点击置灰的「科技」chip
- **THEN** 调用关联 API 保存成功，该 chip 变为高亮（已关联）

#### Scenario: 点击 chip 取消关联
- **WHEN** 点击已高亮的「科技」chip
- **THEN** 该条目解除与「科技」的关联，chip 变为置灰

#### Scenario: chips 仅含已有标签
- **WHEN** 渲染标签列
- **THEN** chips 仅含标签管理中已存在的标签，无输入新建入口
