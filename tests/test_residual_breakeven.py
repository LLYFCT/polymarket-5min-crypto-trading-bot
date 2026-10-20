"""残腿时间阶梯：第一腿均价 0.60 后 Down 按剩余秒数定价，且不扫 0.01。"""

from decimal import Decimal

from spork30.config import StrategyConfig
from spork30.execution import ClipSchedule, desired_asks, residual_leg, residual_target


def _strategy(**kwargs) -> StrategyConfig:
    base = dict(
        fair_edge=Decimal("0"),
        max_lean_shares=Decimal("5"),
        min_ask_price=Decimal("0.6"),
        residual_fee_buffer=Decimal("0"),
        residual_edge_early=Decimal("0.15"),
        residual_target_mid=Decimal("0.50"),
        exit_idle_seconds=180,
        exit_market_seconds=90,
        exit_sweep=True,
        clip_sizes=(10,),
        clip_weights=(1,),
    )
    base.update(kwargs)
    return StrategyConfig(**base)


def test_residual_ladder_targets():
    s = _strategy()
    p_be = Decimal("0.40")
    assert residual_target(p_be, 200, s) == (Decimal("0.55"), "early")
    assert residual_target(p_be, 120, s)[0] == Decimal("0.50")
    assert residual_target(p_be, 120, s)[1] == "mid"
    assert residual_target(p_be, 60, s) == (Decimal("0.40"), "be")


def test_desired_asks_residual_no_sweep():
    s = _strategy(residual_join_bid=True)
    clips = ClipSchedule(s, seed=1)
    common = dict(
        up_reference=Decimal("0.70"),
        inventory_up=Decimal("0"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.69"),
        sold_up_size=Decimal("10"),
        sold_up_notional=Decimal("6.0"),
        sold_down_size=Decimal("0"),
        sold_down_notional=Decimal("0"),
    )
    early = desired_asks(**common, seconds_left=200)
    assert len(early) == 1
    assert early[0].outcome == "Down"
    assert early[0].price >= Decimal("0.55")
    assert early[0].rule == "residual_early"
    assert early[0].size == Decimal("10")
    assert early[0].price != Decimal("0.01")

    mid = desired_asks(**common, seconds_left=120)
    assert mid[0].price >= Decimal("0.50")
    assert mid[0].rule == "residual_mid"

    # Down 买一 0.30 < P_be 0.40 → 贴买一 0.31
    late = desired_asks(**common, seconds_left=60)
    assert late[0].price == Decimal("0.31")
    assert late[0].rule == "residual_be_join"
    assert "sweep" not in late[0].rule


def test_residual_size_is_gap_not_full_inventory():
    s = _strategy()
    clips = ClipSchedule(s, seed=1)
    orders = desired_asks(
        up_reference=Decimal("0.70"),
        inventory_up=Decimal("5"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.69"),
        seconds_left=200,
        sold_up_size=Decimal("5"),
        sold_up_notional=Decimal("3.0"),
    )
    assert len(orders) == 1
    assert orders[0].outcome == "Down"
    assert orders[0].size == Decimal("5")


def test_be_ignores_high_maker():
    """末段买一高于保本时抬到买一+1，不跟高 maker。"""
    s = _strategy(residual_join_bid=True)
    clips = ClipSchedule(s, seed=1)
    # Down maker≈0.80，Down 买一≈0.45；P_be=0.40 → 抬到 0.46
    orders = desired_asks(
        up_reference=Decimal("0.55"),
        inventory_up=Decimal("0"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.20"),
        seconds_left=60,
        sold_up_size=Decimal("10"),
        sold_up_notional=Decimal("6.0"),
    )
    assert len(orders) == 1
    assert orders[0].rule == "residual_be"
    assert orders[0].price == Decimal("0.46")


def test_be_joins_bid_when_below_breakeven():
    """买一低于保本但未超过 under 阈值 → 仍 be_join。"""
    s = _strategy(
        residual_join_bid=True,
        residual_join_min_price=Decimal("0.01"),
        residual_join_max_under_be=Decimal("0.15"),
        residual_fee_buffer=Decimal("0"),
    )
    clips = ClipSchedule(s, seed=1)
    # P_be=0.40；Down 买一≈0.24 → join 0.25，under=0.15 不触发拦截
    orders = desired_asks(
        up_reference=Decimal("0.76"),
        inventory_up=Decimal("0"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.75"),
        seconds_left=60,
        sold_up_size=Decimal("10"),
        sold_up_notional=Decimal("6.0"),
    )
    assert len(orders) == 1
    assert orders[0].rule == "residual_be_join"
    assert orders[0].price == Decimal("0.25")


def test_small_gap_does_not_take_residual_branch():
    s = _strategy()
    clips = ClipSchedule(s, seed=1)
    # gap=2 < min_order 5：可探测残腿，但不下残腿单
    leg = residual_leg(
        Decimal("8"), Decimal("10"), Decimal("2"), Decimal("1.2"), Decimal("0"), Decimal("0"), s
    )
    assert leg is not None
    assert leg[3] == Decimal("2")
    orders = desired_asks(
        up_reference=Decimal("0.70"),
        inventory_up=Decimal("8"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.69"),
        seconds_left=200,
        sold_up_size=Decimal("2"),
        sold_up_notional=Decimal("1.2"),
    )
    assert all(not o.rule.startswith("residual_") for o in orders)


def test_no_sold_avg_skips_residual():
    s = _strategy()
    assert residual_leg(
        Decimal("0"), Decimal("10"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), s
    ) is None
