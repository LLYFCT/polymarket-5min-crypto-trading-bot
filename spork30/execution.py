"""Maker-ask execution policy for regime B.

The strategy asks for two complementary sells. This module turns that into
resting post-only orders and replaces them when the reference price moves.
Fill timing is exogenous. This does not invent a directional signal.
"""

from __future__ import annotations

import random
from decimal import Decimal

from spork30.config import StrategyConfig
from spork30.models import BookTop, DesiredOrder, OrderKind, Side
from spork30.strategy import ceil_price, complement_asks, fair_asks, quantize_price


class ClipSchedule:
    """Seeded sampler over the observed 5/10/15/20 cluster weights.

    The activity feed does not identify which of those sizes the account
    chooses on the next order. Sampling the observed weights is the
    best-supported reconstruction. The seed makes a replay repeatable.
    """

    def __init__(self, strategy: StrategyConfig, seed: int = 30) -> None:
        self._sizes = strategy.clip_sizes
        self._weights = strategy.clip_weights
        if len(self._sizes) != len(self._weights):
            raise ValueError("clip sizes and weights differ in length")
        self._rng = random.Random(seed)

    def next_size(self) -> Decimal:
        choice = self._rng.choices(self._sizes, weights=self._weights, k=1)[0]
        return Decimal(choice)


def reference_up(book: BookTop | None, last_trade: Decimal | None) -> Decimal | None:
    """Prefer the observed Up ask. Fall back to the last Up trade print.

    Joining the ask is the best-supported reading of maker sells. The feed
    does not show unfilled quotes, so an inside-spread or behind-touch
    policy cannot be distinguished when no book is present.
    """
    if book is not None and book.ask is not None:
        return book.ask
    return last_trade


def residual_leg(
    inventory_up: Decimal,
    inventory_down: Decimal,
    sold_up_size: Decimal,
    sold_up_notional: Decimal,
    sold_down_size: Decimal,
    sold_down_notional: Decimal,
    strategy: StrategyConfig,
) -> tuple[str, Decimal, Decimal, Decimal] | None:
    """残腿：返回 (重仓 outcome, P_be, sold_avg, gap)；有差额且轻侧有均价即进入。"""
    gap = abs(inventory_up - inventory_down)
    if gap <= 0:
        return None
    if inventory_up < inventory_down:
        if sold_up_size <= 0:
            return None
        sold_avg = sold_up_notional / sold_up_size
        heavy = "Down"
    elif inventory_down < inventory_up:
        if sold_down_size <= 0:
            return None
        sold_avg = sold_down_notional / sold_down_size
        heavy = "Up"
    else:
        return None
    p_be = Decimal("1") - sold_avg - strategy.residual_fee_buffer
    if p_be < strategy.price_tick:
        p_be = strategy.price_tick
    return heavy, p_be, sold_avg, gap


def residual_target(
    p_be: Decimal,
    seconds_left: int | None,
    strategy: StrategyConfig,
) -> tuple[Decimal, str]:
    """按剩余秒数返回 (目标价, 阶梯名)。"""
    idle = strategy.exit_idle_seconds
    market_s = strategy.exit_market_seconds
    if seconds_left is None:
        return max(p_be, strategy.residual_target_mid), "mid"
    if idle > 0 and seconds_left > idle:
        return p_be + strategy.residual_edge_early, "early"
    if market_s > 0 and seconds_left > market_s:
        return max(p_be, strategy.residual_target_mid), "mid"
    return p_be, "be"


def desired_asks(
    *,
    up_reference: Decimal,
    inventory_up: Decimal,
    inventory_down: Decimal,
    strategy: StrategyConfig,
    clips: ClipSchedule,
    up_bid: Decimal | None = None,
    tick: Decimal | None = None,
    rule: str = "regime_B_complementary_maker_ask",
    skip: frozenset[str] = frozenset(),
    fair: Decimal | None = None,
    seconds_left: int | None = None,
    sold_up_size: Decimal = Decimal("0"),
    sold_up_notional: Decimal = Decimal("0"),
    sold_down_size: Decimal = Decimal("0"),
    sold_down_notional: Decimal = Decimal("0"),
) -> list[DesiredOrder]:
    """Both asks, except outcomes in `skip` (the pair-balance cap withdraws one).

    With `fair` (spot-implied P(Up)) and `fair_edge` > 0 the asks are priced
    at fair + edge; otherwise off the Polymarket touch.
    残腿模式：重仓侧按时间阶梯挂 ≥P_be，不扫 0.01；平衡仓仍用 MIN_ASK_PRICE。
    """
    grid = tick or strategy.price_tick
    if fair is not None and strategy.fair_edge > 0:
        up_price, down_price = fair_asks(fair, strategy, up_ask=quantize_price(up_reference, grid), up_bid=up_bid, tick=grid)
        rule = "spot_fair_plus_edge_maker_ask"
    else:
        up_price, down_price = complement_asks(up_reference, strategy, up_bid=up_bid, tick=tick)
    # Best bid each ask must stay above. Down bid is the mirror of the Up ask
    # (the observed touch, not our own price, which may rest behind it).
    bids = {"Up": up_bid, "Down": Decimal("1") - quantize_price(up_reference, tick or strategy.price_tick)}
    prices = {"Up": up_price, "Down": down_price}
    residual = residual_leg(
        inventory_up,
        inventory_down,
        sold_up_size,
        sold_up_notional,
        sold_down_size,
        sold_down_notional,
        strategy,
    )
    # 残腿：只挂重仓侧差额，阶梯保本，禁用 0.01 扫盘。
    # gap 尚不足最小下单量时不拦后续逻辑（交给 lean / 正常挂单）。
    if residual is not None:
        heavy, p_be, sold_avg, gap = residual
        if heavy not in skip and gap >= strategy.min_order_size:
            inventory = inventory_up if heavy == "Up" else inventory_down
            target, tier = residual_target(p_be, seconds_left, strategy)
            bid = bids[heavy]
            rule_tier = tier
            if tier == "be":
                # 末段：优先保本；买一已高于保本则贴买一上；买一远低于保本则贴买一（破保本换成交）
                floor_be = ceil_price(p_be, grid)
                if bid is None or bid <= 0:
                    exit_price = floor_be
                elif floor_be <= bid:
                    exit_price = quantize_price(bid + grid, grid)
                elif strategy.residual_join_bid:
                    joined = quantize_price(bid + grid, grid)
                    min_px = max(strategy.residual_join_min_price, grid)
                    exit_price = max(joined, min_px)
                    # 相对保本砸太深：禁止 join，交由引擎冻结残腿
                    under = p_be - exit_price
                    if (
                        strategy.residual_join_max_under_be > 0
                        and under > strategy.residual_join_max_under_be
                    ):
                        return [
                            DesiredOrder(
                                outcome=heavy,
                                side=Side.SELL,
                                price=floor_be,
                                size=strategy.min_order_size,
                                kind=OrderKind.LIMIT_MAKER,
                                rule="residual_join_blocked",
                                reference_price=up_reference,
                                position=inventory,
                                risk_checks=[],
                                touch_bid=bid,
                            )
                        ]
                    rule_tier = "be_join"
                else:
                    exit_price = floor_be
            else:
                maker = prices[heavy]
                exit_price = ceil_price(max(target, maker, p_be), grid)
                if exit_price < ceil_price(p_be, grid):
                    exit_price = ceil_price(p_be, grid)
            size = min(clips.next_size(), gap)
            if size >= strategy.min_order_size:
                return [
                    DesiredOrder(
                        outcome=heavy,
                        side=Side.SELL,
                        price=exit_price,
                        size=size,
                        kind=OrderKind.LIMIT_MAKER,
                        rule=f"residual_{rule_tier}",
                        reference_price=up_reference,
                        position=inventory,
                        risk_checks=[],
                        touch_bid=bid,
                    )
                ]
    exit_now = (
        strategy.exit_market_seconds > 0
        and seconds_left is not None
        and 0 < seconds_left <= strategy.exit_market_seconds
    )
    orders: list[DesiredOrder] = []
    # 无残腿均价时的旧逻辑：末段库存不等才扫盘。
    if exit_now and inventory_up != inventory_down:
        for outcome, inventory, other in (
            ("Up", inventory_up, inventory_down),
            ("Down", inventory_down, inventory_up),
        ):
            if outcome in skip:
                continue
            heavy = inventory - other
            if heavy < strategy.min_order_size:
                continue
            bid = bids[outcome]
            if strategy.exit_sweep:
                exit_price = grid
                exit_rule = "exit_market_sweep"
            else:
                if bid is None or bid <= 0:
                    continue
                slip = grid * max(0, strategy.exit_slip_ticks)
                exit_price = quantize_price(max(grid, bid - slip), grid)
                exit_rule = "exit_market_bid"
            size = min(clips.next_size(), heavy)
            if size < strategy.min_order_size:
                continue
            orders.append(
                DesiredOrder(
                    outcome=outcome,
                    side=Side.SELL,
                    price=exit_price,
                    size=size,
                    kind=OrderKind.LIMIT_TAKER,
                    rule=exit_rule,
                    reference_price=up_reference,
                    position=inventory,
                    risk_checks=[],
                    touch_bid=bid,
                )
            )
        return orders
    # 平衡仓：涨跌都须落在配对带；任一端失败则两边都不挂（残腿不走这里）。
    def _pair_ok(price: Decimal) -> bool:
        if price < strategy.pair_ask_min or price > strategy.pair_ask_max:
            return False
        if strategy.min_ask_price > 0 and price <= strategy.min_ask_price:
            return False
        if strategy.max_ask_price > 0 and price > strategy.max_ask_price:
            return False
        return True

    if not (_pair_ok(up_price) and _pair_ok(down_price)):
        return []
    for outcome, price, inventory in (
        ("Up", up_price, inventory_up),
        ("Down", down_price, inventory_down),
    ):
        if outcome in skip or inventory < strategy.min_order_size:
            continue
        size = min(clips.next_size(), inventory)
        if size < strategy.min_order_size:
            continue
        orders.append(
            DesiredOrder(
                outcome=outcome,
                side=Side.SELL,
                price=price,
                size=size,
                kind=OrderKind.LIMIT_MAKER,
                rule=rule,
                reference_price=up_reference,
                position=inventory,
                risk_checks=[],
                touch_bid=bids[outcome],
            )
        )
    return orders
