"""本机盈亏页。只读状态和成交日志，不下单。

    python -m spork30.report
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from spork30.activity import Book, LogTail
from spork30.config import load_config

_BJ = timezone(timedelta(hours=8))
_PHASE = {
    "SEEDED": "待开局",
    "DISCOVERED": "已发现",
    "QUOTING": "报价中",
    "FLATTEN_PENDING": "待合并",
    "REDEEM_PENDING": "待兑付",
    "CLOSED": "已结束",
    "HALTED": "已停止",
}
_lock = threading.Lock()
_tail: LogTail | None = None
_book = Book(require_ack=True)


def _dec(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _num(value: Decimal) -> str:
    text = f"{value.quantize(Decimal('0.0001')):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _signed(value: Decimal) -> str:
    text = _num(value)
    if value > 0:
        return "+" + text
    return text


def _replay(path: Path) -> Book:
    """成交日志只往后读。文件被截断时整本重放。"""
    global _tail, _book
    with _lock:
        if _tail is None or _tail.path != path:
            _tail = LogTail(path)
            _book = Book(require_ack=True)
        if path.exists() and path.stat().st_size < _tail.offset:
            _tail = LogTail(path)
            _book = Book(require_ack=True)
        for record in _tail.read_new():
            _book.apply(record)
        return _book


def _day_value(rows: list[dict], day: str) -> dict:
    """所选北京时间日期：亏损只加已结束且为负的局。"""
    picked = [item for item in rows if item["day"] == day]
    closed = [item for item in picked if item["phase_key"] == "CLOSED"]
    loss = sum((_dec(item["cash_value"]) for item in closed if _dec(item["cash_value"]) < 0), Decimal("0"))
    net = sum((_dec(item["cash_value"]) for item in closed), Decimal("0"))
    open_cash = sum(
        (_dec(item["cash_value"]) for item in picked if item["phase_key"] not in {"CLOSED", "HALTED"}),
        Decimal("0"),
    )
    halted = [item for item in picked if item["phase_key"] == "HALTED"]
    reasons: dict[str, list[dict]] = {}
    for item in halted:
        reasons.setdefault(item["note"] or "未写明", []).append(item)
    halts = [
        {
            "reason": reason,
            "count": len(group),
            "cash": _signed(sum((_dec(item["cash_value"]) for item in group), Decimal("0"))),
        }
        for reason, group in sorted(reasons.items())
    ]
    holding = [
        item for item in picked if _dec(item["left_up"]) > 0 or _dec(item["left_down"]) > 0
    ]
    return {
        "loss": _signed(loss),
        "net": _signed(net),
        "open_cash": _signed(open_cash),
        "closed_count": len(closed),
        "wins": sum(1 for item in closed if _dec(item["cash_value"]) > 0),
        "losses": sum(1 for item in closed if _dec(item["cash_value"]) < 0),
        "flats": len(closed) - sum(1 for item in closed if _dec(item["cash_value"]) != 0),
        "halted": len(halted),
        "halts": halts,
        "holding": holding,
        "rows": picked,
    }


def _rows(path: Path, state_path: Path, day: str | None = None) -> dict:
    book = _replay(path)
    markets = []
    if state_path.is_file():
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        markets = payload.get("markets") or []
    rows = []
    for row in markets:
        phase = str(row.get("phase") or "")
        split = _dec(row.get("split_size"))
        cash = _dec(row.get("cash"))
        if phase == "DISCOVERED" and split <= 0 and cash == 0:
            continue
        slug = str(row.get("slug") or "")
        view = book.markets.get(slug)
        up_px = view.vwap("Up") if view else None
        down_px = view.vwap("Down") if view else None
        start = int(row.get("start") or 0)
        stamp = datetime.fromtimestamp(start, tz=_BJ) if start else None
        rows.append(
            {
                "start": start,
                "when": stamp.strftime("%m-%d %H:%M") if stamp else "-",
                "day": stamp.strftime("%Y-%m-%d") if stamp else "",
                "slug": slug.rsplit("-", 1)[-1],
                "phase": _PHASE.get(phase, phase),
                "phase_key": phase,
                "sold_up": _num(view.sold_up) if view else "0",
                "sold_down": _num(view.sold_down) if view else "0",
                "up_px": _num(up_px) if up_px is not None else "-",
                "down_px": _num(down_px) if down_px is not None else "-",
                "pair": _num(up_px + down_px) if up_px is not None and down_px is not None else "-",
                "left_up": _num(_dec(row.get("up"))),
                "left_down": _num(_dec(row.get("down"))),
                "cash": _signed(cash),
                "cash_value": str(cash),
                "winner": {"Up": "涨", "Down": "跌"}.get(str(row.get("winner") or ""), "-"),
                "note": str(row.get("halt_reason") or ""),
            }
        )
    rows.sort(key=lambda item: item["start"], reverse=True)
    today = datetime.now(_BJ).strftime("%Y-%m-%d")
    days = []
    seen: list[str] = []
    for item in rows:
        if item["day"] and item["day"] not in seen:
            seen.append(item["day"])
    for stamp in sorted(seen, reverse=True):
        summary = _day_value(rows, stamp)
        days.append(
            {
                "day": stamp,
                "closed_count": summary["closed_count"],
                "net": summary["net"],
                "loss": summary["loss"],
            }
        )
    if today not in seen:
        days.insert(0, {"day": today, "closed_count": 0, "net": "0", "loss": "0"})
    selected = day if (day in seen or day == today) else today
    current = _day_value(rows, selected)
    return {
        "selected": selected,
        "today_label": today,
        "day_loss": current["loss"],
        "day_net": current["net"],
        "open_cash": current["open_cash"],
        "closed_count": current["closed_count"],
        "wins": current["wins"],
        "losses": current["losses"],
        "flats": current["flats"],
        "halted": current["halted"],
        "days": days,
        "halts": current["halts"],
        "holding": current["holding"],
        "rows": current["rows"],
    }


_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每局盈亏</title>
<style>
  body { margin: 0; background: #f3f0e8; color: #2a2824; font: 14px/1.5 "Songti SC", "Iowan Old Style", Palatino, serif; }
  main { max-width: 1100px; margin: 0 auto; padding: 28px 20px 48px; }
  h1 { font-size: 22px; font-weight: 600; margin: 0; letter-spacing: 0.04em; }
  .bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
  label { color: #6d675e; font-size: 13px; }
  select { margin-left: 8px; background: #fffdf8; color: #2a2824; border: 1px solid #ddd6c8; border-radius: 8px; padding: 7px 10px; font: inherit; }
  .cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
  .card { background: #fffdf8; border: 1px solid #e7e1d6; border-radius: 12px; padding: 12px 16px; min-width: 128px; }
  .card span { display: block; color: #6d675e; font-size: 12px; }
  .card b { display: block; font-size: 20px; margin-top: 2px; font-variant-numeric: tabular-nums; }
  .pos { color: #2f6b45; } .neg { color: #a33b32; }
  .hint { color: #6d675e; font-size: 12px; margin: 8px 0 0; }
  section { background: #fffdf8; border: 1px solid #e7e1d6; border-radius: 12px; padding: 8px 12px 12px; margin-top: 14px; }
  h2 { font-size: 14px; font-weight: 600; margin: 8px 4px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: right; padding: 8px; border-bottom: 1px solid #efeae1; white-space: nowrap; font-variant-numeric: tabular-nums; }
  th { color: #6d675e; font-weight: 500; font-size: 12px; }
  td:first-child, th:first-child, td:nth-child(2), th:nth-child(2), td:nth-child(3), th:nth-child(3) { text-align: left; }
  tr.halt { background: #faf3ef; }
</style>
</head>
<body>
<main>
  <div class="bar">
    <h1>每局盈亏</h1>
    <label>日期<select id="day"></select></label>
  </div>
  <div class="cards" id="cards"></div>
  <p class="hint">当日亏损只加所选日期里已结束且账面为负的局。未结束和停掉仍剩代币的局不算亏损。</p>
  <section>
    <h2>停止原因</h2>
    <table>
      <thead><tr><th>原因</th><th>局数</th><th>账面</th></tr></thead>
      <tbody id="halts"></tbody>
    </table>
  </section>
  <section>
    <h2>还剩代币</h2>
    <table>
      <thead><tr><th>北京时间</th><th>局</th><th>状态</th><th>剩涨/跌</th><th>账面</th><th>备注</th></tr></thead>
      <tbody id="holding"></tbody>
    </table>
  </section>
  <section>
    <h2>明细</h2>
    <table>
      <thead>
        <tr>
          <th>北京时间</th><th>局</th><th>状态</th><th>卖涨</th><th>卖跌</th><th>一对</th><th>剩涨/跌</th><th>账面</th><th>赢家</th><th>备注</th>
        </tr>
      </thead>
      <tbody id="body"></tbody>
    </table>
  </section>
</main>
<script>
let selected = "";
function cls(text) { return String(text).startsWith("-") ? "neg" : (text === "0" ? "" : "pos"); }
function card(label, value) {
  return '<div class="card"><span>' + label + '</span><b class="' + cls(value) + '">' + value + '</b></div>';
}
function rowLine(row) {
  const mark = row.phase_key === "HALTED" ? "halt" : "";
  return '<tr class="' + mark + '"><td>' + row.when + '</td><td>' + row.slug + '</td><td>' + row.phase
    + '</td><td>' + row.sold_up + ' @ ' + row.up_px + '</td><td>' + row.sold_down + ' @ ' + row.down_px
    + '</td><td>' + row.pair + '</td><td>' + row.left_up + ' / ' + row.left_down
    + '</td><td class="' + cls(row.cash) + '">' + row.cash + '</td><td>' + row.winner
    + '</td><td>' + (row.note || '-') + '</td></tr>';
}
async function load() {
  const data = await (await fetch("/api" + (selected ? "?day=" + selected : ""))).json();
  selected = data.selected;
  const day = document.getElementById("day");
  day.innerHTML = data.days.map(function (item) {
    return '<option value="' + item.day + '">' + item.day + '</option>';
  }).join("");
  day.value = data.selected;
  document.getElementById("cards").innerHTML = [
    card("当日亏损", data.day_loss),
    card("当天净盈亏", data.day_net),
    card("未结束账面", data.open_cash),
    card("赢 / 亏 / 平", data.wins + " / " + data.losses + " / " + data.flats),
    card("已结束 / 停止", data.closed_count + " / " + data.halted),
  ].join("");
  document.getElementById("halts").innerHTML = data.halts.map(function (item) {
    return "<tr><td>" + item.reason + "</td><td>" + item.count + "</td><td class='" + cls(item.cash) + "'>" + item.cash + "</td></tr>";
  }).join("") || "<tr><td>-</td><td>0</td><td>0</td></tr>";
  document.getElementById("holding").innerHTML = data.holding.map(function (row) {
    return "<tr><td>" + row.when + "</td><td>" + row.slug + "</td><td>" + row.phase
      + "</td><td>" + row.left_up + " / " + row.left_down + "</td><td class='" + cls(row.cash) + "'>" + row.cash
      + "</td><td>" + (row.note || "-") + "</td></tr>";
  }).join("") || "<tr><td>-</td><td></td><td></td><td></td><td></td><td></td></tr>";
  document.getElementById("body").innerHTML = data.rows.map(rowLine).join("");
}
document.getElementById("day").addEventListener("change", function (event) {
  selected = event.target.value;
  load();
});
load();
setInterval(load, 5000);
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    config = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api"):
            picked = (parse_qs(parsed.query).get("day") or [None])[0]
            payload = _rows(Path(self.config.decision_log_path), Path(self.config.state_path), picked)
            body = json.dumps(payload).encode()
            kind = "application/json; charset=utf-8"
        else:
            body = _PAGE.encode()
            kind = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    config = load_config()
    _Handler.config = config
    server = ThreadingHTTPServer(("127.0.0.1", 8765), _Handler)
    print("盈亏页 http://127.0.0.1:8765", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
