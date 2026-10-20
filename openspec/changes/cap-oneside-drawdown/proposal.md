## Why

实盘大亏主因是「只卖掉一边」后末段用 0.01 扫残腿或留到结算，单笔常锁在 −3～−5；赚的局多在 +1～+2，盖不住。砍仓位（10→5）只是同比例缩小，不改变结构，不做。主线应是：**第一腿卖够贵 → 残腿按时间阶梯在保本价以上卖完**，提高两边都平掉的概率，并把 0.01 扫盘从常规路径拿掉。

## What Changes

- **`MIN_ASK_PRICE` 只约束平衡仓 / 第一腿**：两侧库存仍接近齐时，卖价低于该值不挂（建议默认 **0.6**），保证先卖出的一边够贵，残腿保本价落在好卖区间（例如第一腿 0.6 → 残腿保本约 0.4）。
- **残腿模式（一边明显轻于另一边）**：对重仓侧**不再**套用 `MIN_ASK_PRICE`；按剩余秒数阶梯定价，地板为保本价 `P_be ≈ 1 − 已卖均价 − fee_buffer`：
  - `seconds_left > EXIT_IDLE_SECONDS`（默认 180）：更高，目标约 `P_be + early_edge`（如 0.55）
  - `EXIT_MARKET < seconds_left ≤ EXIT_IDLE`（默认 90～180）：小赚目标（默认 **0.50**）
  - `seconds_left ≤ EXIT_MARKET_SECONDS`（默认 90）：贴 `P_be`
  - 更晚仍未成交：继续挂 `P_be`，**禁止破地板的 0.01 扫盘**；可停挂等结算
- 看板/决策日志标出残腿模式、当前阶梯目标与 `P_be`。
- **不**砍 `SPLIT_SIZE`/`CLIP_SIZE`；**不**恢复 `EXIT_LOSS_SECONDS`；**不**默认即时买回对冲。

## Capabilities

### New Capabilities
- `residual-breakeven-exit`: 第一腿最低卖价与残腿时间阶梯保本退出（含禁止无意义破地板扫盘）。

### Modified Capabilities

## Impact

- 策略/执行：`desired_asks` 区分平衡仓 vs 残腿；末段不等库存时优先阶梯保本挂单，不再默认 `exit_market_sweep@0.01`。
- 配置：保留并语义化 `MIN_ASK_PRICE`；新增 `RESIDUAL_FEE_BUFFER`、`RESIDUAL_EDGE_EARLY`、`RESIDUAL_TARGET_MID`；末段保本分界直接用 `EXIT_MARKET_SECONDS`；`EXIT_SWEEP` 对残腿默认无效（本变更默认不破 `P_be`）。
- 期望：更多局两边卖完小赚/打平；大额主动锁亏减少。代价：第一腿更难成交（0.6）；贴保本仍卖不掉时仍可能赌结算方向。
