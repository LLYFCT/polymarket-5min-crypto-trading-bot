## ADDED Requirements

### Requirement: First-leg minimum ask applies only while balanced
While Up and Down inventories are considered balanced (absolute difference below the residual-entry threshold), the system MUST NOT place a maker ask whose price is less than or equal to `MIN_ASK_PRICE` when `MIN_ASK_PRICE` is greater than zero.

#### Scenario: Balanced book skips cheap side
- **WHEN** inventory Up equals inventory Down and the computed maker ask for an outcome is `0.55` and `MIN_ASK_PRICE` is `0.60`
- **THEN** the system MUST NOT place that maker ask for that outcome

### Requirement: Enter residual mode after oneside lead
When absolute inventory difference is at least the residual-entry threshold (default: one full clip / enough that one side has sold a material block), the system MUST treat the heavier side as the residual leg and MUST NOT apply `MIN_ASK_PRICE` to that residual leg's asks.

#### Scenario: Residual bypasses MIN_ASK_PRICE
- **WHEN** inventory Up is `0`, inventory Down is `10`, sold Up average price is `0.60`, and `MIN_ASK_PRICE` is `0.60`
- **THEN** the system MAY place Down asks below `0.60` subject to the residual breakeven floor and time ladder

### Requirement: Residual breakeven floor
In residual mode the system MUST compute `P_be = 1 − sold_avg − RESIDUAL_FEE_BUFFER` from the volume-weighted average sell price of the lighter (already sold) side in the current window, and MUST NOT place a residual ask priced below `P_be` (except the tick grid quantization to the nearest valid price at or above `P_be`).

#### Scenario: Floor after first leg at 0.60
- **WHEN** residual mode is active, sold average on the light side is `0.60`, and `RESIDUAL_FEE_BUFFER` is `0`
- **THEN** residual asks MUST be priced at least `0.40`

### Requirement: Residual time ladder
In residual mode the ask target MUST follow remaining seconds in the window:

- When `seconds_left > EXIT_IDLE_SECONDS`, target MUST be at least `P_be + RESIDUAL_EDGE_EARLY`
- When `EXIT_MARKET_SECONDS < seconds_left ≤ EXIT_IDLE_SECONDS`, target MUST be at least `max(P_be, RESIDUAL_TARGET_MID)`
- When `seconds_left ≤ EXIT_MARKET_SECONDS` and `seconds_left > 0`, target MUST be `P_be` (grid-quantized)

The placed price MUST be the maximum of that target and any higher price the normal maker formula would use for that side, then quantized to the price grid.

#### Scenario: Early residual asks higher
- **WHEN** residual mode is active, `P_be` is `0.40`, `RESIDUAL_EDGE_EARLY` is `0.15`, `EXIT_IDLE_SECONDS` is `180`, and `seconds_left` is `200`
- **THEN** the residual ask target MUST be at least `0.55`

#### Scenario: Mid window targets small edge
- **WHEN** residual mode is active, `P_be` is `0.40`, `RESIDUAL_TARGET_MID` is `0.50`, `EXIT_IDLE_SECONDS` is `180`, `EXIT_MARKET_SECONDS` is `90`, and `seconds_left` is `120`
- **THEN** the residual ask target MUST be at least `0.50`

#### Scenario: Late window sticks to breakeven
- **WHEN** residual mode is active, `P_be` is `0.40`, `EXIT_MARKET_SECONDS` is `90`, and `seconds_left` is `60`
- **THEN** the residual ask target MUST be `0.40` (grid-quantized)

### Requirement: No penny sweep below breakeven
While residual mode is active, the system MUST NOT submit an `exit_market_sweep` (or equivalent ask at the minimum price tick such as `0.01`) for the heavy side when that price would be below `P_be`.

#### Scenario: Late imbalance does not dump at 0.01
- **WHEN** residual mode is active, `P_be` is `0.40`, `seconds_left` is `30`, and `EXIT_SWEEP` is enabled
- **THEN** the system MUST NOT place a residual sell at `0.01`, and MUST keep quoting at least `P_be` or cancel quotes and wait for merge/settlement without crossing below `P_be`

### Requirement: Residual decision logging
When residual mode is active or a below-floor sweep is skipped, the decision log MUST record residual mode, `P_be`, ladder tier (early / mid / be), and the chosen ask price.

#### Scenario: Log ladder tier
- **WHEN** the engine places or skips a residual ask due to the ladder
- **THEN** the decision log MUST include `P_be` and the active tier identifier
