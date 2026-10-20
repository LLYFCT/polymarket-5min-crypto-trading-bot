"""Runtime configuration.

Trading mode defaults to simulation. Live sending is a separate, explicit gate
in spork30.live and is never implied by these defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path


class TradingMode(str, Enum):
    SIMULATION = "SIMULATION"
    LIVE = "LIVE"


def _decimal(name: str, default: str) -> Decimal:
    return Decimal(os.environ.get(name, default))


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else int(raw)


@dataclass(frozen=True)
class StrategyConfig:
    """Active policy: regime B, retimed from the reference account's Oct 5-12 2026 tape.

    Constants are the traded-window measurements on 2,012 settled windows:
    750 shares, 293 s lead, merge every remaining pair at +358 s, redeem the
    unpaired winner at +366 s.
    """

    window_seconds: int = 300
    slug_prefix: str = "btc-updown-5m"
    split_size: Decimal = Decimal("750")
    # Median split lead Oct 5-12 (p10 291, p90 296, n=2012): the next window is
    # minted about 7 s after the current one opens. Was 212 s in September.
    split_lead_seconds: int = 293
    # Late-start floor. Below this the account almost never mints.
    min_split_lead_seconds: int = 90
    # The unpaired winner is redeemed at +366 s (median, n=1821), after the merge.
    redeem_delay_seconds: int = 366
    # Every remaining pair is merged at +358 s (median, 1,953 of 2,012 windows),
    # before the oracle is in. Was "merge at +372 only if unresolved".
    flatten_delay_seconds: int = 358
    complement_sum: Decimal = Decimal("1")
    # Fallback tick when the book does not report one. The venue uses 0.01
    # across the middle of the range and 0.001 only below 0.04 / above 0.96;
    # the live book's tick_size overrides this per quote.
    price_tick: Decimal = Decimal("0.01")
    # Venue minimum order size for these markets (orderMinSize = 5).
    min_order_size: Decimal = Decimal("5")
    # Ticks behind the touch each ask rests. 0 joins the ask (the observed
    # regime-B behaviour). Exists so the replay can price the alternative;
    # the default is unchanged.
    ask_offset_ticks: int = 0
    # Resting quotes (U1). A live ask is replaced only when the touch has
    # moved at least `requote_threshold_ticks` from it and the order is at
    # least `requote_min_seconds` old. 0 / 0 replaces on every price change.
    # The 96-window replay rejected both knobs: holding a stale ask for 10 s
    # took the mean from -5.9 to -15 per window (win% 66), a 2-tick
    # threshold was neutral. Kept at 0; see data/backtest/upgrade-fair.json.
    requote_threshold_ticks: int = 0
    requote_min_seconds: int = 0
    # Pair balance cap (U1b). The ask on an outcome is withdrawn while that
    # outcome has been sold more than `max_lean_shares` ahead of the other
    # one; it comes back once the other side catches up. The account's
    # per-window |sold Up - sold Down| has median 6 and p90 14 on 2,012
    # windows; a cap of 3 with 5-share clips reproduces that median (6-7 in
    # the replay) and cuts the worst window from -105 to -8. 0 disables.
    max_lean_shares: Decimal = Decimal("3")
    # Inside-the-spread pricing (U2). When the Up spread is at least this
    # many ticks, both asks step one tick inside the touch (pair = 1 +
    # spread - 2 ticks). The account's Up+Down prints sum to 1.000 at the
    # median, which a maker can only do inside a spread of 2+ ticks. 0 = off.
    improve_spread_ticks: int = 0
    # Spot-referenced fair value (U6). When `fair_edge` > 0 and a BTC spot
    # price and the window's price-to-beat are available, each ask is priced
    # at fair + edge (fair = P(Up) from the spot distance to the beat, the
    # time left and realised volatility) and never below the touch's maker
    # side. The Polymarket touch lags spot by seconds; a taker who lifts an
    # ask at spot-fair is not acting on information the quote lacked. 0 = off
    # (price off the Polymarket touch only, as before).
    #
    # Replay, 96 windows Oct 11-12, lean cap 3, mean PnL per window before
    # rebate: touch-only quoting -21.9 (t -5.0); fair edge 0.03 with 1 s of
    # spot latency +0.71 (t +2.0, worst -8.4, 101 sh/w, win% 53, lean 6),
    # with 2 s of latency -0.31. The sign depends on quoting within about a
    # second of spot; the rebate estimate (+0.2/window) does not change it.
    # With the fair value on and no fresh spot the engine rests nothing.
    fair_edge: Decimal = Decimal("0.03")
    # Allow the fair ask to undercut the current best ask (down to one tick
    # above the bid) when fair + edge is below it. Off: join the touch.
    # Undercutting was 0.3-3 per window worse in the replay.
    fair_undercut: bool = False
    # Seconds of spot the quote is assumed to lag (the replay uses the spot
    # print this many seconds old; live, the feed's own latency applies).
    spot_lag_seconds: int = 1
    # Fallback annualised volatility when realised vol cannot be measured.
    fair_vol_annual: Decimal = Decimal("0.45")
    # Maker rebate as measured on the account's seven daily MAKER_REBATE
    # payments: 41-43 bps of sold notional (64 on one day). Used for the
    # estimate on the screen and in the replay; the bot never sees the
    # actual payment.
    maker_rebate_bps: Decimal = Decimal("42")
    # On-grid clustered fill sizes, with Oct 5-12 fill counts
    # (10 42%, 5 33%, 15 23%, 20 2%). Fill sizes understate order sizes
    # because of partials, so this is a prior. CLIP_SIZE=5 时只挂固定张数。
    clip_sizes: tuple[int, ...] = (5, 10, 15, 20)
    clip_weights: tuple[int, ...] = (8892, 11348, 6151, 581)
    # 可选单边过滤；0=关。主开挂用 pair_ask_*，避免只挂一边。
    min_ask_price: Decimal = Decimal("0")
    max_ask_price: Decimal = Decimal("0")
    # 平衡仓：涨跌算价都须落在此带内才两边开挂（互补可行，勿设成双进 0.6～0.68）
    pair_ask_min: Decimal = Decimal("0.38")
    pair_ask_max: Decimal = Decimal("0.62")
    # 残腿保本：P_be = 1 - 已卖均价 - buffer
    residual_fee_buffer: Decimal = Decimal("0.01")
    # 残腿还早（seconds_left > exit_idle）时目标 = P_be + early
    residual_edge_early: Decimal = Decimal("0.15")
    # 残腿中段目标价（与 P_be 取较大）
    residual_target_mid: Decimal = Decimal("0.50")
    # 末段 be：买一低于保本时贴买一上方，允许破保本成交（非盲目 0.01）
    residual_join_bid: bool = True
    # 贴买一时的最低价；买一更低也至少挂到这（0=可跟到 1 档）
    residual_join_min_price: Decimal = Decimal("0.05")
    # P_be - join价 超过此值则禁止 be_join，冻结残腿报价
    residual_join_max_under_be: Decimal = Decimal("0.15")
    # 窗口结束前 N 秒：残腿贴保本；未进残腿时库存不等仍可能旧扫盘。
    exit_market_seconds: int = 0
    # 兜底是否扫买盘：仅非残腿且仍走旧分支时用；残腿默认不扫 0.01。
    exit_sweep: bool = False
    # 非扫盘时，卖价 = 买价 - N 档，减少追跌挂不上。
    exit_slip_ticks: int = 2
    # 结束前 N 秒：两边库存仍相等（含都没成交）→ 停挂等合并。0 关闭。
    exit_idle_seconds: int = 0
    dust_shares: Decimal = Decimal("1")


@dataclass(frozen=True)
class RiskConfig:
    """Safety bounds around the reconstructed policy.

    These are not inferred strategy rules. They exist so a bug cannot scale
    the policy without a human change. Limits sit outside observed behavior:
    one 750 split, clips of at most 20, about two to three markets open.
    """

    max_position_per_outcome: Decimal = Decimal("800")
    max_order_size: Decimal = Decimal("20")
    max_daily_loss: Decimal = Decimal("1000")
    max_total_exposure: Decimal = Decimal("3000")
    max_orders_per_10s: int = 40
    max_retry_count: int = 3
    stale_data_timeout_seconds: int = 5
    # Halt if a reference price jumps by more than this in one update.
    max_price_jump: Decimal = Decimal("0.50")
    min_price: Decimal = Decimal("0.001")
    max_price: Decimal = Decimal("0.999")


@dataclass(frozen=True)
class AppConfig:
    trading_mode: TradingMode
    strategy: StrategyConfig
    risk: RiskConfig
    state_path: str
    decision_log_path: str
    emergency_stop_path: str
    funder: str = ""
    signature_type: int = 3
    polygon_rpc: str = ""

    @property
    def live_enabled(self) -> bool:
        return self.trading_mode is TradingMode.LIVE


def load_env_file(path: Path | None = None) -> None:
    """Load spork30/.env without overriding variables already set in the process."""
    env_path = path or Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _clip_schedule(defaults: StrategyConfig) -> tuple[tuple[int, ...], tuple[int, ...]]:
    # CLIP_SIZE=5 关闭随机权重，只挂固定张数。以后要加档再改 CLIP_SIZES。
    raw = os.environ.get("CLIP_SIZE", "").strip()
    if raw:
        size = int(raw)
        return (size,), (1,)
    raw_sizes = os.environ.get("CLIP_SIZES", "").strip()
    if not raw_sizes:
        return defaults.clip_sizes, defaults.clip_weights
    sizes = tuple(int(part.strip()) for part in raw_sizes.split(",") if part.strip())
    raw_weights = os.environ.get("CLIP_WEIGHTS", "").strip()
    if raw_weights:
        weights = tuple(int(part.strip()) for part in raw_weights.split(",") if part.strip())
    else:
        weights = tuple(1 for _ in sizes)
    if not sizes or len(sizes) != len(weights):
        raise SystemExit("CLIP_SIZES and CLIP_WEIGHTS must be non-empty and the same length")
    return sizes, weights


def load_config() -> AppConfig:
    load_env_file()
    raw_mode = os.environ.get("TRADING_MODE", "SIMULATION").strip().upper()
    try:
        mode = TradingMode(raw_mode)
    except ValueError as exc:
        raise SystemExit(f"TRADING_MODE must be SIMULATION or LIVE, got {raw_mode!r}") from exc
    base = os.environ.get("BOT_DATA_DIR", "data/runtime")
    # Simulation writes local mints and demo fills. Live keeps a separate log
    # so those lines are not shown as exchange trades.
    root = os.path.join(base, "live" if mode is TradingMode.LIVE else "sim")
    defaults = StrategyConfig()
    clip_sizes, clip_weights = _clip_schedule(defaults)
    # 未写 MAX_ORDER_SIZE 时，跟 CLIP_SIZE（或 CLIP_SIZES 最大档）走。
    max_order = _decimal("MAX_ORDER_SIZE", str(max(clip_sizes)))
    return AppConfig(
        trading_mode=mode,
        strategy=StrategyConfig(
            split_size=_decimal("SPLIT_SIZE", "750"),
            split_lead_seconds=_int("SPLIT_LEAD_SECONDS", defaults.split_lead_seconds),
            min_split_lead_seconds=_int("MIN_SPLIT_LEAD_SECONDS", defaults.min_split_lead_seconds),
            redeem_delay_seconds=_int("REDEEM_DELAY_SECONDS", defaults.redeem_delay_seconds),
            flatten_delay_seconds=_int("FLATTEN_DELAY_SECONDS", defaults.flatten_delay_seconds),
            ask_offset_ticks=_int("ASK_OFFSET_TICKS", defaults.ask_offset_ticks),
            requote_threshold_ticks=_int("REQUOTE_THRESHOLD_TICKS", defaults.requote_threshold_ticks),
            requote_min_seconds=_int("REQUOTE_MIN_SECONDS", defaults.requote_min_seconds),
            max_lean_shares=_decimal("MAX_LEAN_SHARES", str(defaults.max_lean_shares)),
            improve_spread_ticks=_int("IMPROVE_SPREAD_TICKS", defaults.improve_spread_ticks),
            fair_edge=_decimal("FAIR_EDGE", str(defaults.fair_edge)),
            fair_undercut=os.environ.get("FAIR_UNDERCUT", "1" if defaults.fair_undercut else "0").strip() in {"1", "true", "yes", "on"},
            spot_lag_seconds=_int("SPOT_LAG_SECONDS", defaults.spot_lag_seconds),
            fair_vol_annual=_decimal("FAIR_VOL_ANNUAL", str(defaults.fair_vol_annual)),
            maker_rebate_bps=_decimal("MAKER_REBATE_BPS", str(defaults.maker_rebate_bps)),
            clip_sizes=clip_sizes,
            clip_weights=clip_weights,
            min_ask_price=_decimal("MIN_ASK_PRICE", "0"),
            max_ask_price=_decimal("MAX_ASK_PRICE", "0"),
            pair_ask_min=_decimal("PAIR_ASK_MIN", str(defaults.pair_ask_min)),
            pair_ask_max=_decimal("PAIR_ASK_MAX", str(defaults.pair_ask_max)),
            residual_fee_buffer=_decimal("RESIDUAL_FEE_BUFFER", str(defaults.residual_fee_buffer)),
            residual_edge_early=_decimal("RESIDUAL_EDGE_EARLY", str(defaults.residual_edge_early)),
            residual_target_mid=_decimal("RESIDUAL_TARGET_MID", str(defaults.residual_target_mid)),
            residual_join_bid=os.environ.get(
                "RESIDUAL_JOIN_BID", "1" if defaults.residual_join_bid else "0"
            ).strip().lower()
            in {"1", "true", "yes", "on"},
            residual_join_min_price=_decimal(
                "RESIDUAL_JOIN_MIN_PRICE", str(defaults.residual_join_min_price)
            ),
            residual_join_max_under_be=_decimal(
                "RESIDUAL_JOIN_MAX_UNDER_BE", str(defaults.residual_join_max_under_be)
            ),
            exit_market_seconds=_int("EXIT_MARKET_SECONDS", defaults.exit_market_seconds),
            exit_sweep=os.environ.get(
                "EXIT_SWEEP", "1" if defaults.exit_sweep else "0"
            ).strip().lower()
            in {"1", "true", "yes", "on"},
            exit_slip_ticks=_int("EXIT_SLIP_TICKS", defaults.exit_slip_ticks),
            exit_idle_seconds=_int("EXIT_IDLE_SECONDS", defaults.exit_idle_seconds),
        ),
        risk=RiskConfig(
            max_position_per_outcome=_decimal("MAX_POSITION", "800"),
            max_order_size=max_order,
            max_daily_loss=_decimal("MAX_DAILY_LOSS", "1000"),
            max_total_exposure=_decimal("MAX_TOTAL_EXPOSURE", "3000"),
            max_orders_per_10s=_int("MAX_ORDER_RATE", 40),
            max_retry_count=_int("MAX_RETRY_COUNT", 3),
            stale_data_timeout_seconds=_int("STALE_DATA_TIMEOUT", 5),
            # 风控绝对底价，勿与 MIN_ASK_PRICE（第一腿策略下限）混用。
            min_price=_decimal("RISK_MIN_PRICE", str(RiskConfig.min_price)),
        ),
        state_path=os.path.join(root, "state.json"),
        decision_log_path=os.path.join(root, "decisions.jsonl"),
        emergency_stop_path=os.environ.get("EMERGENCY_STOP_FILE", os.path.join(base, "EMERGENCY_STOP")),
        funder=os.environ.get("POLYMARKET_FUNDER", "").strip(),
        signature_type=_int("POLYMARKET_SIGNATURE_TYPE", 3),
        polygon_rpc=os.environ.get("POLYGON_RPC", "").strip(),
    )


def reset_runtime(config: AppConfig) -> None:
    """Delete this mode's decision log and engine state. The emergency stop file stays."""
    for path in (config.decision_log_path, config.state_path):
        file = Path(path)
        if file.is_file():
            file.unlink()
