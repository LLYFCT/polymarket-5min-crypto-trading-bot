## Context

见 proposal.md。当前 `MIN_ASK_PRICE` 对平常 maker 两侧一视同仁；末段 `EXIT_MARKET_SECONDS` + `EXIT_SWEEP` 在库存不等时对重仓侧挂 0.01。二者与「第一腿要贵、残腿按时间贴保本」冲突：全局 0.5/0.6 会挡住残腿 0.4；扫盘又会主动锁大亏。

## Goals / Non-Goals

**Goals:**

- 平衡仓：`MIN_ASK_PRICE`（建议 0.6）只限制第一腿。
- 残腿：动态 `P_be` + 与 `EXIT_IDLE` / `EXIT_MARKET_SECONDS` 对齐的三档时间阶梯；默认不破 `P_be`。
- 配置进 `.env` 中文注释；决策日志可对照阶梯。

**Non-Goals:**

- 不改 `SPLIT_SIZE`/`CLIP_SIZE`。
- 不恢复亏损提前扫盘、不默认买回对冲。
- 不保证贴 `P_be` 一定成交；卖不掉则结算风险仍在。

## Decisions

1. **残腿进入条件**：`|up − down| ≥ residual_enter_shares`。默认 `residual_enter_shares = min_order_size` 且实质「一侧已明显少」；实现上用 `|up-down| ≥ CLIP_SIZE` 或「轻侧为 0 / 轻侧 < 重侧且已有已实现卖出均价」——优先：**轻侧库存为 0 或差额 ≥ clip，且本局该轻侧有卖出成交均价可算 `sold_avg`**。若尚无均价（异常），不进残腿阶梯，保持原逻辑并打日志。
2. **`P_be = 1 − sold_avg − RESIDUAL_FEE_BUFFER`**，再量化到 ≥`P_be` 的价位格。默认 `RESIDUAL_FEE_BUFFER=0.01`。
3. **时间阶梯**（`seconds_left`）：
   - `> EXIT_IDLE_SECONDS`（180）：`target = P_be + RESIDUAL_EDGE_EARLY`（默认 early=0.15 → 第一腿 0.6 时约 0.55）
   - `> EXIT_MARKET_SECONDS`（默认 90）且 ≤ idle：`target = max(P_be, RESIDUAL_TARGET_MID)`（默认 mid=0.50）
   - `≤ EXIT_MARKET_SECONDS`：`target = P_be`
   - 挂价：`quantize(max(target, 该侧原 maker 价若更高))`，且 `≥ P_be`
4. **`MIN_ASK_PRICE` 作用域**：仅非残腿（平衡）分支；残腿分支跳过该检查。
5. **扫盘**：残腿模式下取消「gap 挂 0.01」；改为继续按阶梯挂 `target`，或 `seconds_left` 极小且无买盘时撤单冻结等结算。`EXIT_SWEEP=1` 不再对残腿生效（本变更明确覆盖）。
6. **实现落点**：`execution.desired_asks` 分支；`sold_avg` 由 `portfolio`/窗口状态传入（本局轻侧已实现卖单价量加权）。配置进 `StrategyConfig` + `.env`。
7. **默认建议**：`MIN_ASK_PRICE=0.6`，`RESIDUAL_TARGET_MID=0.5`，`RESIDUAL_EDGE_EARLY=0.15`，`EXIT_MARKET_SECONDS=90`，`RESIDUAL_FEE_BUFFER=0.01`。

## Risks / Trade-offs

- [第一腿 0.6 成交变少] → 接受；换残腿更好平。
- [贴 P_be 仍卖不掉] → 结算方向风险仍在；比 0.01 锁死半仓可控。
- [sold_avg 统计不准] → 只用本局已确认卖出；无均价则不进残腿。

## Migration Plan

改代码与 `.env` 后重启 dashboard。把 `MIN_ASK_PRICE` 设回 `0.5`、`RESIDUAL_EDGE_EARLY=0`、`RESIDUAL_TARGET_MID=0` 可弱化阶梯；恢复旧扫盘需另开变更（本变更默认残腿不扫 0.01）。

## Open Questions

无。阶梯边界已与现有 180/90 对齐；实施按上表默认值写入 `.env` 注释即可。
