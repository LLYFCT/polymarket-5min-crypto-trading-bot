"""Pane layout for the terminal. Pure rendering: reads a `Book`, draws rich renderables.

    header   mode | gates | clock | window countdown
    market   window, phase, reference, both asks and the pair sum, inventory
    orders   every resting ask with its age
    cycles   last six windows: sold Up/Down at VWAP, pnl, winner
    risk     realized / today / daily-loss bar / exposure bar / refusals
    health   loop tick age, errors, fill feed, chain worker, resolution source
    tape     what happened, newest last
    footer   keys and the log path

Nothing here touches the engine or the venue. Behaviour changes live in the
decision log; this module only decides how to show them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from spork30.activity import Book, MarketView, short_slug
from spork30.config import TradingMode

EVENT_STYLE = {
    "split": "cyan",
    "open": "bright_blue",
    "reprice": "blue",
    "fill": "bright_green",
    "merge": "magenta",
    "redeem": "green",
    "confirm": "green",
    "halt": "bright_red",
    "reject": "bright_red",
    "error": "bright_red",
    "refuse": "yellow",
    "unwind": "yellow",
    "day": "dim",
}

PHASE_STYLE = {
    "SEEDED": "yellow",
    "DISCOVERED": "cyan",
    "QUOTING": "bright_green",
    "FLATTEN_PENDING": "yellow",
    "REDEEM_PENDING": "yellow",
    "CLOSED": "dim",
    "HALTED": "bright_red",
}

PHASE_LABEL = {
    "SEEDED": "待开局",
    "DISCOVERED": "已发现",
    "QUOTING": "报价中",
    "FLATTEN_PENDING": "待合并",
    "REDEEM_PENDING": "待兑付",
    "CLOSED": "已结束",
    "HALTED": "已停止",
}

EVENT_LABEL = {
    "split": "拆分",
    "open": "挂单",
    "reprice": "改价",
    "fill": "成交",
    "merge": "合并",
    "redeem": "兑付",
    "confirm": "确认",
    "halt": "停止",
    "reject": "拒绝",
    "error": "错误",
    "refuse": "拦截",
    "unwind": "平仓",
    "day": "换日",
}

WINDOW = 300


def build(
    book: Book,
    *,
    mode: str,
    status: str,
    log_path: str,
    emergency: bool,
    btc: Decimal | None = None,
    beat: Decimal | None = None,
    clock: int | None = None,
    notice: str = "",
    sends: bool = False,
    limits: dict | None = None,
) -> Layout:
    now = book.last_ts if clock is None else clock
    live = mode == TradingMode.LIVE.value
    limits = limits or {}
    root = Layout()
    root.split_column(
        Layout(name="header", size=4),
        Layout(name="body", ratio=3, minimum_size=22),
        Layout(name="tape", ratio=2, minimum_size=8),
        Layout(name="footer", size=4),
    )
    root["body"].split_row(Layout(name="left", ratio=3), Layout(name="right", ratio=2, minimum_size=38))
    root["left"].split_column(
        Layout(name="market", size=7),
        Layout(name="orders", size=7),
        Layout(name="cycles", minimum_size=8),
    )
    root["right"].split_column(
        Layout(name="risk", size=10),
        Layout(name="health", minimum_size=7),
    )
    root["header"].update(header(book, mode=mode, status=status, emergency=emergency, sends=sends, now=now, notice=notice))
    root["market"].update(market_pane(book, now, btc, beat, notice))
    root["orders"].update(Panel(orders_table(book, now), title="挂着的卖单", border_style="bright_blue"))
    root["cycles"].update(Panel(cycles_table(book, now), title="各局", border_style="cyan"))
    root["risk"].update(risk_pane(book, now, limits))
    root["health"].update(health_pane(book, now, live=live, sends=sends))
    root["tape"].update(Panel(tape_table(book, notice), title="记录", border_style="green"))
    root["footer"].update(footer(log_path, mode, sends))
    return root


def snapshot_text(layout: Layout, width: int = 140, height: int = 50) -> str:
    console = Console(width=width, height=height, force_terminal=True, color_system=None)
    with console.capture() as capture:
        console.print(layout)
    return capture.get()


# --- panes ----------------------------------------------------------------------


def header(book: Book, *, mode: str, status: str, emergency: bool, sends: bool, now: int, notice: str = "") -> Panel:
    live = mode == TradingMode.LIVE.value
    title = Text()
    if emergency:
        title.append(" 紧急停止 ", style="bold white on red")
        title.append(" ")
    title.append(" spork30 ", style="bold white on grey23")
    title.append(" ")
    if live:
        title.append(" 实盘 ", style="bold white on red")
        title.append("  这个画面会发单" if sends else "  只看，这里不发单", style="red")
    else:
        title.append(" 模拟 ", style="bold black on bright_green")
        title.append("  单子只在这台机器上", style="green")
    title.append("    ")
    title.append(_hms(now), style="bold yellow")
    title.append(" 世界时", style="dim")
    if now:
        start = now - (now % WINDOW)
        left = start + WINDOW - now
        title.append(f"    本局 {_span(start)}  ", style="dim")
        title.append(f"剩余 {left // 60:02d}:{left % 60:02d}", style="yellow")
    sub = Text(status, style="dim")
    if notice:
        sub.append("    ")
        sub.append(notice, style="yellow")
    return Panel(Group(title, sub), border_style="red" if live else "green")


def market_pane(book: Book, now: int, btc: Decimal | None, beat: Decimal | None, notice: str = "") -> Panel:
    market = book.active(now) if now else (book.traded()[-1] if book.traded() else None)
    line1 = Text(no_wrap=True, overflow="crop")
    line2 = Text(no_wrap=True, overflow="crop")
    line3 = Text(no_wrap=True, overflow="crop")
    if market is None or market.start is None:
        line1.append("还没有拆分", style="dim")
        if notice:
            line2.append(notice, style="yellow")
    else:
        phase = _phase_shown(market, now)
        line1.append(_span(market.start), style="bold")
        line1.append(f"  {short_slug(market.slug)}  ")
        line1.append(PHASE_LABEL.get(phase, phase), style=PHASE_STYLE.get(phase, ""))
        if market.start <= now < market.start + WINDOW:
            left = market.start + WINDOW - now
            line1.append(f"    剩余 {left // 60:02d}:{left % 60:02d}", style="yellow")
        elif now < market.start:
            line1.append(f"    {market.start - now}秒后开始", style="yellow")
        else:
            line1.append(f"    结束后 {now - market.start - WINDOW}秒", style="dim")
        if market.halt_reason:
            line1.append(f"    {market.halt_reason}", style="bright_red")
        up = market.last_quote.get("Up")
        down = market.last_quote.get("Down")
        line2.append("参考涨卖价 ", style="dim")
        line2.append(_px4(market.reference), style="bold white")
        line2.append("    涨卖价 ", style="dim")
        line2.append(_px4(up), style="bright_green")
        line2.append("  跌卖价 ", style="dim")
        line2.append(_px4(down), style="bright_red")
        if up is not None and down is not None:
            pair = up + down
            line2.append("    一对 ", style="dim")
            line2.append(f"{pair:.2f}", style="bold bright_green" if pair > 1 else "bold bright_red")
            line2.append(f" ({(pair - 1) * 100:+.0f}分)", style="dim")
        line2.append(f"    改价 {market.replaces}", style="dim")
        line3.append("剩余 ", style="dim")
        line3.append(f"涨 {_money(market.up)}  跌 {_money(market.down)}")
        line3.append("    已卖 ", style="dim")
        line3.append(f"涨 {_money(market.sold_up)}" + (f" @ {market.vwap('Up'):.3f}" if market.vwap("Up") else ""), style="bright_green")
        line3.append("  ")
        line3.append(f"跌 {_money(market.sold_down)}" + (f" @ {market.vwap('Down'):.3f}" if market.vwap("Down") else ""), style="bright_red")
        line3.append("    现金 ", style="dim")
        line3.append(_money(market.cash), style="bold")
    spot = Text(no_wrap=True, overflow="crop")
    spot.append("比特币均价 ", style="dim")
    spot.append(_px(btc), style="bold white")
    spot.append("   开盘价 ", style="dim")
    spot.append(_px(beat), style="bold")
    if btc is not None and beat is not None:
        delta = btc - beat
        spot.append(f"   {delta:+,.2f}", style="bright_green" if delta >= 0 else "bright_red")
    return Panel(Group(line1, line2, line3, spot), title="本局", border_style="white")


def orders_table(book: Book, now: int) -> Table:
    table = Table(expand=True, show_edge=False, pad_edge=False)
    table.add_column("局", style="bold", no_wrap=True)
    table.add_column("方向", no_wrap=True)
    table.add_column("价格", justify="right", no_wrap=True)
    table.add_column("张数", justify="right", no_wrap=True)
    table.add_column("剩余", justify="right", no_wrap=True)
    table.add_column("挂了", justify="right", no_wrap=True)
    rows = book.resting_orders()
    if not rows:
        seeded = [m for m in book.traded() if m.phase == "QUOTING" and m.start is not None and now < m.start]
        table.add_row(short_slug(seeded[-1].slug) if seeded else "-", "", "", "", "", "已备好，开局再挂" if seeded else "没有挂单")
        return table
    for market, order in rows[-4:]:
        age = f"{now - order.placed_ts}秒" if order.placed_ts and now else "-"
        style = "bright_green" if order.outcome == "Up" else "bright_red"
        table.add_row(short_slug(market.slug), Text(_side(order.outcome), style=style), order.price, order.size, order.remaining, age)
    return table


def cycles_table(book: Book, now: int) -> Table:
    table = Table(expand=True, show_edge=False, pad_edge=False)
    table.add_column("时间", style="bold", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    table.add_column("卖涨", justify="right", no_wrap=True)
    table.add_column("卖跌", justify="right", no_wrap=True)
    table.add_column("剩涨/跌", justify="right", no_wrap=True)
    table.add_column("盈亏", justify="right", no_wrap=True)
    table.add_column("赢家", no_wrap=True)
    rows = book.traded()[-6:]
    if not rows:
        table.add_row("-", Text("等待", style="dim"), "", "", "", "", "")
        return table
    for market in rows:
        phase = _phase_shown(market, now)
        pnl = market.cash
        pnl_style = "dim" if phase not in {"CLOSED", "HALTED"} else ("bright_green" if pnl >= 0 else "bright_red")
        table.add_row(
            _hhmm(market.start),
            Text(PHASE_LABEL.get(phase, phase), style=PHASE_STYLE.get(phase, "yellow")),
            _sold(market, "Up"),
            _sold(market, "Down"),
            f"{market.up:.0f}/{market.down:.0f}",
            Text(_money(pnl), style=pnl_style),
            _side(market.winner) if market.winner else (market.halt_reason[:12] if market.halt_reason else "-"),
        )
    return table


def risk_pane(book: Book, now: int, limits: dict) -> Panel:
    realized = book.realized()
    closed = book.closed_count()
    day, daily = book.daily_pnl(now)
    today = book.realized_today if book.realized_today is not None else realized
    max_loss = Decimal(str(limits.get("max_daily_loss") or "0"))
    max_exposure = Decimal(str(limits.get("max_total_exposure") or "0"))
    exposure = book.exposure()
    lines: list[Text] = []

    def line() -> Text:
        t = Text(no_wrap=True, overflow="crop")
        lines.append(t)
        return t

    t = line()
    t.append("已结盈亏 ", style="dim")
    t.append(_money(realized), style="bold bright_green" if realized >= 0 else "bold bright_red")
    t.append(f"  / {closed} 局已结算", style="dim")
    t = line()
    t.append("未结现金 ", style="dim")
    t.append(_money(book.open_cash()), style="yellow")
    t.append("  含已拆出、还没结算的", style="dim")
    t = line()
    t.append("今日     ", style="dim")
    t.append(_money(daily), style="bold")
    t.append(f"  {day} 开的局", style="dim")
    t = line()
    t.append("计入上限 ", style="dim")
    t.append(_money(today), style="bold bright_green" if today >= 0 else "bold bright_red")
    t.append("  用来对比每日亏损上限", style="dim")
    rebate_bps = Decimal(str(limits.get("maker_rebate_bps") or "0"))
    if rebate_bps > 0:
        # Estimate only: the rebate is paid outside the CLOB and never appears
        # in this log. 42 bps of sold notional is the reference account's rate.
        rebate = book.sold_notional() * rebate_bps / Decimal("10000")
        t = line()
        t.append("返佣估计 ", style="dim")
        t.append(_money(rebate), style="cyan")
        t.append(f"  卖掉 {_money(book.sold_notional())} 的万分之 {rebate_bps}，未入账", style="dim")
    if max_loss > 0:
        used = max(Decimal("0"), -today)
        t = line()
        t.append("当日亏损 ", style="dim")
        t.append(_bar(used, max_loss), style="bright_red" if used / max_loss > Decimal("0.8") else "yellow")
        t.append(f" {_money(used)} / {_money(max_loss)}", style="dim")
    if max_exposure > 0:
        t = line()
        t.append("占用资金 ", style="dim")
        t.append(_bar(exposure, max_exposure), style="cyan")
        t.append(f" {_money(exposure)} / {_money(max_exposure)}  {len(book.open_markets())} 局未结", style="dim")
    t = line()
    refusals = book.counts.get("risk_refuse", 0)
    rejects = book.counts.get("send_fail", 0)
    halts = book.counts.get("halt", 0)
    t.append("成交 ", style="dim")
    t.append(str(book.counts.get("fill", 0)))
    t.append("  下单 ", style="dim")
    t.append(str(book.counts.get("place", 0)))
    t.append("  拦截 ", style="dim")
    t.append(str(refusals), style="yellow" if refusals else "")
    t.append("  拒单 ", style="dim")
    t.append(str(rejects), style="bright_red" if rejects else "")
    t.append("  停止 ", style="dim")
    t.append(str(halts), style="bright_red" if halts else "")
    return Panel(Group(*lines), title="盈亏和上限", border_style="grey50")


def health_pane(book: Book, now: int, *, live: bool, sends: bool) -> Panel:
    h = book.health
    text = Text(no_wrap=True, overflow="crop")
    age = (now - book.last_ts) if (now and book.last_ts) else None
    text.append("循环 ", style="dim")
    if age is None:
        text.append("还没有事件", style="yellow")
    else:
        text.append(f"上次事件 {age}秒前", style="bright_green" if age <= 3 else ("yellow" if age <= 15 else "bright_red"))
    errors = book.counts.get("loop_error", 0)
    text.append("    错误 ", style="dim")
    text.append(str(errors), style="bright_red" if errors else "")
    if book.counts.get("loop_abort"):
        text.append("  已中止", style="bold bright_red")
    text.append("\n")
    if live:
        text.append("成交 ", style="dim")
        feed = h.get("feed")
        if not h:
            text.append("还没有状态记录", style="dim")
        elif feed is None:
            text.append("只在轮询成交（推送已关）", style="yellow")
        elif feed:
            text.append(f"推送已连接，{h.get('feed_events', 0)} 条", style="bright_green")
        else:
            text.append("推送断开，改为每秒轮询", style="bright_red")
        text.append("\n")
        text.append("链上 ", style="dim")
        pending = int(h.get("chain_pending") or 0)
        text.append(f"{pending} 笔待确认", style="yellow" if pending else "")
        text.append(f"    已确认 {book.counts.get('tx_confirmed', 0)}", style="dim")
        text.append("\n")
        text.append("结算 ", style="dim")
        if not h:
            text.append("-", style="dim")
        else:
            text.append("用节点读兑付" if h.get("rpc") else "没有节点，用网页收盘价", style="" if h.get("rpc") else "yellow")
        text.append("\n")
        text.append("一轮 ", style="dim")
        text.append(f"{h.get('tick_ms', '-')} 毫秒" if h else "-", style="")
        text.append(f"    挂单 {h.get('live_orders', 0)}" if h else "", style="dim")
    else:
        text.append("成交 ", style="dim")
        text.append("模拟：顺着现价的一边，每20秒卖5张", style="dim")
        text.append("\n")
        text.append("盘口 ", style="dim")
        text.append("用比特币和开盘价合成，跳动 0.01", style="dim")
        text.append("\n")
        text.append("说明 ", style="dim")
        text.append("这不是预测。回放命令：python -m spork30.backtest", style="dim")
    return Panel(text, title="状态", border_style="grey50")


def tape_table(book: Book, notice: str = "", rows: int = 14) -> Table:
    table = Table(expand=True, show_edge=False, pad_edge=False)
    table.add_column("时间", width=8, no_wrap=True)
    table.add_column("事件", width=6, no_wrap=True)
    table.add_column("局", width=10, no_wrap=True)
    table.add_column("说明", no_wrap=True, overflow="crop")
    lines = list(book.tape)[-rows:]
    if not lines:
        table.add_row("-", "", "", notice or "还没有记录")
        return table
    for line in lines:
        table.add_row(
            _hms(line.ts) if line.ts else "-",
            Text(EVENT_LABEL.get(line.event, line.event), style=EVENT_STYLE.get(line.event, "")),
            short_slug(line.slug),
            line.detail,
        )
    return table


def footer(log_path: str, mode: str, sends: bool = False) -> Panel:
    hint = "q 退出    Ctrl+C 退出    每秒刷新一次"
    if sends:
        hint += "    q 同时停掉下单，并撤销还挂着的卖单"
    elif mode == TradingMode.LIVE.value:
        hint += "    这个画面不发单"
    else:
        hint += "    均价和开盘价用的是 Polymarket 页面上的 Chainlink"
    text = Text()
    text.append(hint + "\n", style="dim")
    text.append(log_path, style="grey70")
    return Panel(text, border_style="grey37")


# --- formatting -------------------------------------------------------------------


def _side(outcome: str) -> str:
    if outcome == "Up":
        return "涨"
    if outcome == "Down":
        return "跌"
    return outcome or "-"


def _phase_shown(market: MarketView, now: int) -> str:
    if market.phase == "QUOTING" and market.start is not None and now and now < market.start:
        return "SEEDED"
    return market.phase


def _sold(market: MarketView, outcome: str) -> str:
    size = market.sold_up if outcome == "Up" else market.sold_down
    vwap = market.vwap(outcome)
    if size <= 0 or vwap is None:
        return "-"
    return f"{size:.0f} @ {vwap:.3f}"


def _bar(value: Decimal, limit: Decimal, width: int = 12) -> str:
    if limit <= 0:
        return " " * width
    share = min(Decimal("1"), max(Decimal("0"), value / limit))
    filled = int(share * width)
    # ASCII on purpose: legacy Windows consoles are cp1252 and reject block glyphs.
    return "#" * filled + "-" * (width - filled)


def _hhmm(start: int | None) -> str:
    if not start:
        return "-"
    return datetime.fromtimestamp(start, tz=timezone.utc).strftime("%H:%M")


def _span(start: int) -> str:
    end = datetime.fromtimestamp(start + WINDOW, tz=timezone.utc).strftime("%H:%M")
    return f"{_hhmm(start)}-{end}"


def _hms(ts: int) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def _px(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value.quantize(Decimal('0.01')):,}"


def _px4(value: Decimal | None) -> str:
    """Outcome prices sit on the 0.01 grid."""
    if value is None:
        return "-"
    return f"{value:.2f}"
