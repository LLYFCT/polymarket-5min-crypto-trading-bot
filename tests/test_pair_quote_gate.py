"""配对开挂带 + 残腿灾难 join 拦截。"""

from decimal import Decimal

from spork30.config import StrategyConfig, load_config
from spork30.execution import ClipSchedule, desired_asks


def _s(**kwargs) -> StrategyConfig:
    base = dict(
        fair_edge=Decimal("0.03"),
        fair_undercut=True,
        pair_ask_min=Decimal("0.38"),
        pair_ask_max=Decimal("0.62"),
        min_ask_price=Decimal("0"),
        max_ask_price=Decimal("0"),
        residual_fee_buffer=Decimal("0"),
        residual_edge_early=Decimal("0.15"),
        residual_target_mid=Decimal("0.50"),
        residual_join_bid=True,
        residual_join_min_price=Decimal("0.05"),
        residual_join_max_under_be=Decimal("0.15"),
        exit_idle_seconds=180,
        exit_market_seconds=90,
        clip_sizes=(10,),
        clip_weights=(1,),
    )
    base.update(kwargs)
    return StrategyConfig(**base)


def test_config_loads_pair_and_join_under():
    s = load_config().strategy
    assert s.pair_ask_min == Decimal("0.38")
    assert s.pair_ask_max == Decimal("0.62")
    assert s.residual_join_max_under_be == Decimal("0.15")
    assert s.min_ask_price == Decimal("0")
    assert s.max_ask_price == Decimal("0")


def test_skewed_pair_quotes_neither():
    # fair≈0.61 → up≈0.64 down≈0.42，跌出配对带上沿
    s = _s()
    clips = ClipSchedule(s, seed=1)
    orders = desired_asks(
        up_reference=Decimal("0.64"),
        inventory_up=Decimal("10"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.63"),
        fair=Decimal("0.61"),
        seconds_left=250,
    )
    assert orders == []


def test_even_pair_allows_both():
    s = _s()
    clips = ClipSchedule(s, seed=1)
    orders = desired_asks(
        up_reference=Decimal("0.52"),
        inventory_up=Decimal("10"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.51"),
        fair=Decimal("0.50"),
        seconds_left=250,
    )
    assert {o.outcome for o in orders} == {"Up", "Down"}
    assert all(Decimal("0.38") <= o.price <= Decimal("0.62") for o in orders)


def test_residual_bypasses_pair_band():
    s = _s()
    clips = ClipSchedule(s, seed=1)
    orders = desired_asks(
        up_reference=Decimal("0.70"),
        inventory_up=Decimal("0"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.69"),
        fair=Decimal("0.70"),
        seconds_left=200,
        sold_up_size=Decimal("10"),
        sold_up_notional=Decimal("6.4"),
    )
    assert len(orders) == 1
    assert orders[0].outcome == "Down"
    assert orders[0].rule.startswith("residual_")


def test_join_blocked_when_far_under_be():
    # 15:25 类：先卖跌侧均价 0.64 → P_be≈0.35；涨很贵则跌买一≈0.10 → join 过深被拦
    s = _s(residual_fee_buffer=Decimal("0.01"))
    clips = ClipSchedule(s, seed=1)
    orders = desired_asks(
        up_reference=Decimal("0.90"),
        inventory_up=Decimal("0"),
        inventory_down=Decimal("10"),
        strategy=s,
        clips=clips,
        up_bid=Decimal("0.89"),
        seconds_left=60,
        sold_up_size=Decimal("10"),
        sold_up_notional=Decimal("6.4"),
    )
    assert len(orders) == 1
    assert orders[0].rule == "residual_join_blocked"


def test_mild_join_still_allowed():
    s = _s(residual_fee_buffer=Decimal("0"), residual_join_min_price=Decimal("0.01"))
    clips = ClipSchedule(s, seed=1)
    # sold@0.60 → P_be=0.40；Down 买一≈0.24 → join 0.25，under=0.15 边界可过
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
    # Down bid = 1-0.76=0.24 → join 0.25；P_be=0.40；under=0.15 需 > 才拦，0.15 不拦
    assert len(orders) == 1
    assert orders[0].rule == "residual_be_join"
    assert orders[0].price == Decimal("0.25")
