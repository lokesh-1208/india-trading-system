"""Your intraday trades, saved in journal/intraday_trades.csv (this computer only).

One row per trade: opened when you enter, closed when you exit. Closing works out the
profit after intraday charges, so the totals are what really reached your account.
"""

import csv
import re

import pandas as pd

from . import charges
from . import settings as s

FIELDS = ["id", "date", "symbol", "side", "qty", "entry", "stop", "target", "entry_time",
          "exit", "exit_time", "rule", "note", "status", "gross", "charges", "net"]
_SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")


def _now():
    return pd.Timestamp.now(tz="Asia/Kolkata")


def load():
    path = s.JOURNAL_FILE
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save(rows):
    s.JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(s.JOURNAL_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDS})


def _num(value, name, minimum=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if number <= minimum:
        raise ValueError(f"{name} must be more than {minimum:g}.")
    return number


def open_trade(symbol, side, qty, entry, stop, target=None, rule="own", note="", when=None):
    """Record a trade you have entered. A stop-loss is required: no stop, no trade."""
    symbol = (symbol or "").strip().upper()
    if not _SYMBOL.match(symbol):
        raise ValueError("Enter a stock symbol such as RELIANCE.")
    side = (side or "").upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("Side must be BUY or SELL.")
    qty = int(_num(qty, "Quantity"))
    entry = _num(entry, "Entry price")
    stop = _num(stop, "Stop-loss (a stop-loss is required)")
    if side == "BUY" and stop >= entry:
        raise ValueError("For a BUY the stop-loss must be below the entry price.")
    if side == "SELL" and stop <= entry:
        raise ValueError("For a SELL the stop-loss must be above the entry price.")
    target = None if target in (None, "") else _num(target, "Target")
    if target is not None and ((side == "BUY" and target <= entry) or (side == "SELL" and target >= entry)):
        raise ValueError("The target must be on the profit side of the entry price.")
    if rule not in s.RULES:
        rule = "own"
    when = when or _now()
    rows = load()
    new_id = max([int(r["id"]) for r in rows], default=0) + 1
    rows.append({"id": new_id, "date": when.strftime("%Y-%m-%d"), "symbol": symbol, "side": side,
                 "qty": qty, "entry": entry, "stop": stop, "target": "" if target is None else target,
                 "entry_time": when.strftime("%H:%M"), "rule": rule, "note": note.strip()[:200],
                 "status": "open"})
    _save(rows)
    return new_id


def close_trade(trade_id, exit_price, when=None):
    exit_price = _num(exit_price, "Exit price")
    when = when or _now()
    rows = load()
    for row in rows:
        if int(row["id"]) == int(trade_id):
            if row["status"] != "open":
                raise ValueError("That trade is already closed.")
            qty, entry = int(row["qty"]), float(row["entry"])
            sign = 1 if row["side"] == "BUY" else -1
            gross = (exit_price - entry) * qty * sign
            buy_v = (entry if sign == 1 else exit_price) * qty
            sell_v = (exit_price if sign == 1 else entry) * qty
            cost = charges.round_trip(buy_v, sell_v)
            row.update(exit=exit_price, exit_time=when.strftime("%H:%M"), status="closed",
                       gross=round(gross, 2), charges=round(cost, 2), net=round(gross - cost, 2))
            _save(rows)
            return row
    raise ValueError("No such trade.")


def delete_trade(trade_id):
    rows = load()
    kept = [r for r in rows if int(r["id"]) != int(trade_id)]
    if len(kept) == len(rows):
        raise ValueError("No such trade.")
    _save(kept)


def page():
    """Everything the journal section of the page shows."""
    rows = load()
    closed = [r for r in rows if r["status"] == "closed"]
    nets = [float(r["net"]) for r in closed]
    by_day = {}
    for r in closed:
        by_day[r["date"]] = by_day.get(r["date"], 0.0) + float(r["net"])
    wins = [n for n in nets if n > 0]
    by_rule = {}
    for r in closed:
        by_rule.setdefault(r["rule"], []).append(float(r["net"]))
    return {
        "open": [r for r in rows if r["status"] == "open"],
        "closed": list(reversed(closed))[:200],
        "totals": {
            "closed_count": len(closed), "net": round(sum(nets), 2),
            "charges": round(sum(float(r["charges"]) for r in closed), 2),
            "win_rate": round(len(wins) / len(nets), 3) if nets else None,
            "days": len(by_day), "best_day": round(max(by_day.values()), 2) if by_day else None,
            "worst_day": round(min(by_day.values()), 2) if by_day else None,
        },
        "by_rule": [{"rule": s.RULES.get(k, k), "trades": len(v), "net": round(sum(v), 2)}
                    for k, v in by_rule.items()],
        "rules": s.RULES,
    }
