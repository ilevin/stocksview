## MODIFIED Requirements

### Requirement: 更新频率

估值数据 SHALL 每日收盘后更新一次（每日一次），保存到 fundamental_snapshot（UNIQUE(instrument_id, trade_date)）；应用启动时当天自选 A 股估值未全覆盖 SHALL 执行一次更新。周期检查（每 30 分钟）时，若最近交易日存在自选 A 股缺失当日估值，SHALL 补刷一次。「覆盖」指当日行存在且三项指标（PE/PB/股息率）均非空；任一指标为空的行 SHALL 视为未覆盖（应对数据源当日指标延迟生成，指标当日确无值的标的将每 30 分钟重试至当日结束，每次为一次全市场查询）。对当日确认无数据（停牌、新股等，补刷后仍缺失）的标的，SHALL NOT 在当日重复请求（内存标记，进程重启后允许再试一次）；`POST /api/admin/refresh/fundamentals` 手动刷新 SHALL 忽略该标记并重试全部自选 A 股。估值 SHALL NOT 参与每 60 秒行情刷新。

#### Scenario: 每日一次
- **WHEN** 当日自选 A 股估值已全覆盖
- **THEN** 不再重复请求 Tushare

#### Scenario: 盘中新增自选补齐估值
- **WHEN** 当日估值刷新完成后，用户又添加了新的自选 A 股股票
- **THEN** 下一次周期检查发现缺失并补刷当日估值，新股票的 PE/PB/股息率可显示

#### Scenario: 停牌股不反复请求
- **WHEN** 某自选 A 股当日停牌，Tushare 无该日记录，补刷后仍缺失
- **THEN** 当日后续周期检查跳过该标的，不再对其发起请求

#### Scenario: 当日指标延迟生成的空指标行继续补刷
- **WHEN** 某自选 A 股当日快照任一指标（如股息率）为空
- **THEN** 该标的视为未覆盖，继续参与周期补刷，直至指标回填或当日结束

#### Scenario: 手动强制刷新
- **WHEN** 调用 `POST /api/admin/refresh/fundamentals`
- **THEN** 对全部自选 A 股重新请求估值，忽略已尝试标记

## ADDED Requirements

### Requirement: 添加自选后的即时估值获取

添加自选股票成功后，系统 SHALL 立即获取该股最近一期估值（per-stock 查询，不受收盘时间限制）并写入 fundamental_snapshot；仅 CN/STOCK 生效；获取失败 SHALL NOT 影响添加结果。

#### Scenario: 添加 A 股股票后立即显示估值
- **WHEN** 添加 CN/STOCK 自选成功
- **THEN** 该股最近一期 PE/PB/股息率被写入并可显示，无需等待收盘后的周期刷新

#### Scenario: 添加 ETF 或港股不触发估值获取
- **WHEN** 添加 ETF 或港股股票
- **THEN** 不发起估值请求

#### Scenario: 估值获取失败不影响添加
- **WHEN** 添加成功但 Tushare 请求异常
- **THEN** 添加接口仍返回 201，失败仅记录日志
