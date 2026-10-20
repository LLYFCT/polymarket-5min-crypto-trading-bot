## ADDED Requirements

### Requirement: Balanced quoting requires both asks in a complementary-feasible band
While inventories are balanced (not in residual mode), the system MUST NOT place maker asks unless both the computed Up ask and the computed Down ask lie within the closed interval `[PAIR_ASK_MIN, PAIR_ASK_MAX]`. If either ask is outside that interval, the system MUST place no balanced maker asks on either outcome for that refresh.

#### Scenario: Skewed book blocks all balanced quotes
- **WHEN** the computed Up ask is `0.64` and the computed Down ask is `0.42` and `PAIR_ASK_MIN` is `0.38` and `PAIR_ASK_MAX` is `0.62`
- **THEN** the system MUST NOT place a balanced maker ask on Up or Down

#### Scenario: Near-even book allows both quotes
- **WHEN** the computed Up ask is `0.53` and the computed Down ask is `0.53` and `PAIR_ASK_MIN` is `0.38` and `PAIR_ASK_MAX` is `0.62`
- **THEN** the system MAY place balanced maker asks on both outcomes (subject to inventory and lean)

#### Scenario: Impossible narrow high band is not required
- **WHEN** `PAIR_ASK_MIN` is `0.60` and `PAIR_ASK_MAX` is `0.68`
- **THEN** the configuration is allowed, but the system MUST still apply the same both-in-band rule (operators SHOULD use a complementary-feasible default such as `0.38`–`0.62` because both asks cannot simultaneously sit in `0.60`–`0.68` under normal complement/fair pricing)

### Requirement: Remove reliance on dual 0.6–0.68 as the sole pair gate
The system MUST NOT treat “both asks in (0.6, 0.68]” as the mandatory pair-open condition. Optional per-side `MIN_ASK_PRICE` / `MAX_ASK_PRICE` MAY still apply in addition to the pair band, but failing only one side’s per-side filter MUST NOT be used as a substitute for the pair-band rule above.

#### Scenario: Any active ask filter failure quotes neither side
- **WHEN** balanced quoting is evaluated and either ask fails the pair band or an enabled per-side `MIN_ASK_PRICE` / `MAX_ASK_PRICE` filter
- **THEN** the system MUST place no balanced maker asks on either outcome

### Requirement: Catastrophic residual join is blocked
In residual end-of-window join mode, the system MUST NOT place a residual ask that joins the bid when the join price is more than `RESIDUAL_JOIN_MAX_UNDER_BE` below `P_be` (default suggested `0.15`). When join is blocked by this rule, the system MUST cancel residual asks and MUST NOT place further residual maker asks for that window until flatten/merge/settlement (freeze quoting on that window’s residual).

#### Scenario: 15:25-style join at 0.05 is blocked
- **WHEN** residual mode is active, `P_be` is `0.35`, `RESIDUAL_JOIN_MAX_UNDER_BE` is `0.15`, and the would-be join price is `0.05`
- **THEN** the system MUST NOT place that join ask, and MUST freeze further residual quoting for the window

#### Scenario: Mild under-be join still allowed
- **WHEN** residual mode is active, `P_be` is `0.35`, `RESIDUAL_JOIN_MAX_UNDER_BE` is `0.15`, and the join price is `0.25`
- **THEN** the system MAY place the join ask if `RESIDUAL_JOIN_BID` is enabled

### Requirement: Residual mode still bypasses the pair band
Residual-leg quoting MUST NOT require both Up and Down asks to lie in `[PAIR_ASK_MIN, PAIR_ASK_MAX]`.

#### Scenario: Residual quotes after oneside fill
- **WHEN** residual mode is active after a oneside fill
- **THEN** the system MAY quote the heavy side under residual ladder rules without satisfying the balanced pair band
