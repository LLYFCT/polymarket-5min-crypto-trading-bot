## Purpose

本机盈亏页按北京时间算出当日亏损，并补上复盘需要的每日汇总、停止原因和仍留在账上的代币。只读已有记录，不下单。

## ADDED Requirements

### Requirement: Daily loss uses settled losing windows
The page MUST compute daily loss on the Beijing calendar date. 页面必须按北京时间的日期计算当日亏损。当日亏损只等于当天状态为已结束、且账面小于 0 的局的账面之和。当天净盈亏必须同时显示，并等于当天全部已结束局的账面之和。

#### Scenario: Losing and winning windows on the same day
- **WHEN** 当天有已结束局账面 -3.50 和 +0.70
- **THEN** 当日亏损为 -3.50，当天净盈亏为 -2.80

#### Scenario: Unsettled window is excluded
- **WHEN** 当天有一局仍在报价或待合并，账面为 -10
- **THEN** 这 -10 不计入当日亏损，也不计入当天净盈亏，并仍出现在未结束账面中

#### Scenario: Halted window with tokens is excluded
- **WHEN** 当天有一局已停止且剩余代币不为 0
- **THEN** 该局账面不计入当日亏损，并出现在未兑付列表中

### Requirement: Recent days are summarized
The page MUST list each Beijing date present in the saved state. 页面必须列出最近若干个北京时间日期，每个日期给出已结束局数、净盈亏和亏损。选择某一天时，明细表必须只显示该日的局。

#### Scenario: Filter detail by day
- **WHEN** 查看者选择昨天
- **THEN** 明细只含昨天开盘的局，当日亏损和当天净盈亏改按昨天计算

### Requirement: Halt reasons and stranded tokens are visible
The page MUST summarize halt reasons and list windows that still hold tokens. 页面必须按停止原因汇总当天已停止的局数和账面合计。剩余涨或跌大于 0 的局必须单独列出时间、局号、剩余张数、账面和停止原因。

#### Scenario: Split failure with no tokens
- **WHEN** 当天一局因拆分失败停止，剩余涨跌都为 0，账面为 0
- **THEN** 停止原因汇总计入这一局，它不进入未兑付列表，也不进入当日亏损

#### Scenario: Merge failure still holding a pair
- **WHEN** 当天一局因合并失败停止，剩余 10 涨和 10 跌
- **THEN** 未兑付列表显示该局的剩余张数和合并失败原因，其账面不计入当日亏损

### Requirement: Existing window detail stays
The page MUST keep the existing per-window columns and MUST remain read-only. 每局明细必须继续显示北京时间、局号、状态、卖涨、卖跌、一对均价、剩余张数、账面、赢家和停止原因。页面必须只读本地记录，不得下单或展示私钥。

#### Scenario: Refresh keeps the same numbers
- **WHEN** 记录没有新的结算
- **THEN** 刷新后当日亏损、当天净盈亏和每局账面与刷新前一致
