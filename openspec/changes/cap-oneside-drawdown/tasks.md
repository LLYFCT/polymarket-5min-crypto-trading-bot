## 1. 配置

- [x] 1.1 增加 `RESIDUAL_FEE_BUFFER`（默认 0.01）、`RESIDUAL_EDGE_EARLY`（默认 0.15）、`RESIDUAL_TARGET_MID`（默认 0.50）；末段保本分界用 `EXIT_MARKET_SECONDS`；`.env` 中文注释说明与 `MIN_ASK_PRICE` 分工
- [x] 1.2 `load_config` / `StrategyConfig` 读入上述字段，启动日志可核对

## 2. 残腿状态与保本价

- [x] 2.1 窗口内维护轻侧已实现卖出均价 `sold_avg`；满足残腿进入条件时算 `P_be` 并打决策日志
- [x] 2.2 无 `sold_avg` 时不进残腿阶梯（保持原平衡逻辑）

## 3. desired_asks 分支

- [x] 3.1 平衡仓：继续 `MIN_ASK_PRICE` 过滤（第一腿）
- [x] 3.2 残腿：跳过 `MIN_ASK_PRICE`；按 `seconds_left` 三档算 target，挂价 `≥ P_be`，size 为重仓剩余
- [x] 3.3 残腿模式禁用重仓侧 `exit_market_sweep@0.01`；末段贴 `P_be` 或撤单冻结，不破地板

## 4. 对照验证（手工/单测择一）

- [x] 4.1 用例：Up 卖光均价 0.60、Down=10、left=200 → 目标 ≥约 0.55；left=120 → ≥0.50；left=60 → 0.40；且不出现 0.01 扫盘
