## Context

见 proposal.md。15:25：仅跌@0.64 进旧「高价带」并成交 → 残腿涨 early/mid@0.50 无成交 → `be_join`@0.05 成交 → ≈−3。  
「两边都 ∈(0.6,0.68]」与 `fair+edge` / 互补盘口不相容（两边都 >0.6 ⇒ fair 既 >0.57 又 <0.43）。当前代码若已实现双进 (0.6,0.68]，实施本变更时必须拆掉。

## Goals / Non-Goals

**Goals:**

- 用**互补可行**的配对开挂带替代不可能的双高价带。
- 平衡仓：任一端出带 ⇒ **两边都不挂**（避免只挂贵的一边）。
- 残腿：保留阶梯；禁止相对 `P_be` 偏离过大的 `be_join`，改为冻结等结算。
- `.env` 注释写清数学原因，防止再配回 0.6～0.68 双进带当主策略。

**Non-Goals:**

- 不改 SPLIT/CLIP；不恢复 0.01 扫盘作常规手段。
- 不保证单边市仍有成交；接受更多空过。
- 不在本变更解决 `MAX_PRICE_DEVIATION` 与残腿跟价的冲突（可另开）。

## Decisions

1. **默认配对带 `PAIR_ASK_MIN=0.38`、`PAIR_ASK_MAX=0.62`**  
   在 `fair_edge=0.03` 下，约要求 fair ∈≈[0.35, 0.59]，覆盖中性～轻偏；排除 15:25 类「一边 0.64、另一边已出带」的开挂。  
   备选更严：`0.42`–`0.58`（更少单边、更少成交）。

2. **平衡仓逻辑**（`desired_asks` 非残腿分支）：  
   `ok = PAIR_MIN ≤ up_ask ≤ PAIR_MAX and PAIR_MIN ≤ down_ask ≤ PAIR_MAX`；再叠加现有 min/max ask（若启用）。  
   **本变更选定**：任一过滤器失败 ⇒ `return []`（两边都不挂）。  
   撤销「仅双进 0.6～0.68」的硬编码/注释；`MIN_ASK=0.6` / `MAX_ASK=0.68` 若保留，仅作可选附加——但与配对带同时开启时，有效开挂集会更窄；**建议实施时把第一腿主约束迁到 PAIR_***，将 MIN/MAX 默认关掉或放宽**，避免又变相只挂一边。  
   **实施默认建议**：`MIN_ASK_PRICE=0`、`MAX_ASK_PRICE=0`，只开 `PAIR_ASK_*`；lean 维持用户当前值（如 2）。

3. **残腿 `RESIDUAL_JOIN_MAX_UNDER_BE=0.15`**：  
   若 `P_be - join_price > 0.15`（例 0.35−0.05=0.30）⇒ 不 join，`quotes_frozen`（或等价：撤残腿挂单且本窗不再挂 residual）。  
   `RESIDUAL_JOIN_BID=0` 时行为与「永不 join」一致。

4. **15:25 对照**：配对带下跌 0.64>0.62 ⇒ 开盘即不挂，整局空过，避免 −3；若仍因边界进残腿，0.05 join 会被 under-be 门禁挡住。

## Risks / Trade-offs

- [成交变少] → 预期；用空过来换少单边。  
- [PAIR 带仍可能两边同进但随后一笔吃满一边] → lean 仍需要；可另加「仅一边有库存后立即残腿/冻结」。  
- [停 join 后结算仍可能 −4] → 接受；比主动 0.05 锁 −3 多保留反转可能。

## Migration Plan

改 `desired_asks` + `.env` 后重启 live。回滚：扩大 `PAIR_ASK_*` 至 0～1，并把 `RESIDUAL_JOIN_MAX_UNDER_BE` 设很大。

## Open Questions

无。默认 0.38–0.62 与 under-be 0.15 已按 15:25 数字选定；实施前若要更严/更松只改 `.env`。
