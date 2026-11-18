"""The day's rules, kept for you: what the clock allows, and whether your limits are hit."""

import pandas as pd

from . import journal
from . import settings as s

IST = "Asia/Kolkata"


def _hm(ts):
    return ts.strftime("%H:%M")


def phase(now=None):
    """What the market clock allows right now (IST)."""
    now = now if now is not None else pd.Timestamp.now(tz=IST)
    p, t = s.PHASES, _hm(now)
    if now.weekday() >= 5:
        return {"key": "closed", "label": "Market closed (weekend)", "entries": False}
    if t < p["range_start"]:
        return {"key": "pre", "label": "Before the open: nothing to do yet", "entries": False}
    if t < p["range_end"]:
        return {"key": "range", "label": "Opening range forming: wait until 9:30", "entries": False}
    if t <= p["last_entry"]:
        return {"key": "open", "label": f"Entries open until {p['last_entry']}", "entries": True}
    if t < p["square_off"]:
        return {"key": "manage", "label": f"No new entries. Manage open trades; square off by {p['square_off']}",
                "entries": False}
    if t < p["close"]:
        return {"key": "square_off", "label": "Square off every open trade now", "entries": False}
    return {"key": "closed", "label": "Market closed", "entries": False}


def day_status(now=None):
    now = now if now is not None else pd.Timestamp.now(tz=IST)
    today = now.strftime("%Y-%m-%d")
    rows = [r for r in journal.load() if r["date"] == today]
    realised = round(sum(float(r["net"]) for r in rows if r["status"] == "closed"), 2)
    open_n = sum(1 for r in rows if r["status"] == "open")
    clock = phase(now)
    limit_hit = realised <= -s.DAILY_LOSS_LIMIT
    used = len(rows)
    blockers = []
    if not clock["entries"]:
        blockers.append(clock["label"])
    if limit_hit:
        blockers.append(f"Daily loss limit of ₹{s.DAILY_LOSS_LIMIT:,} reached: stop for today")
    if used >= s.MAX_TRADES_PER_DAY:
        blockers.append(f"All {s.MAX_TRADES_PER_DAY} trades for today used")
    return {
        "time": now.strftime("%H:%M"), "date": today, "phase": clock,
        "trades_used": used, "trades_max": s.MAX_TRADES_PER_DAY, "open_trades": open_n,
        "realised_net": realised, "loss_limit": s.DAILY_LOSS_LIMIT, "loss_limit_hit": limit_hit,
        "entries_allowed": not blockers, "blockers": blockers,
        "settings": {"capital": s.CAPITAL, "risk_per_trade": s.RISK_PER_TRADE, "target_r": s.TARGET_R,
                     "margin_x": s.MARGIN_X, "square_off": s.EXIT_TIME, "last_entry": s.LAST_ENTRY},
    }
