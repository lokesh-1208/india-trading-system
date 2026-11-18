"""Intraday entry/exit rules on 5-minute candles (regular OHLC candlesticks).

ORB (opening-range breakout), long side; short is the mirror image:
  1. Opening range = high/low of the first 15 minutes.
  2. Signal: a 5-minute candle CLOSES above the range high and above VWAP.
  3. Entry: open of the next candle (plus slippage).
  4. Stop: range low (widened if tighter than MIN_STOP_PCT, skipped if wider than MAX_STOP_PCT).
  5. Target: TARGET_R x the stop distance. Optional: move the stop to entry once price
     has moved BE_AT_R x the stop distance in our favour (effective from the next candle).
  6. Exit: stop, target, or EXIT_TIME. If a candle touches both stop and target, stop wins.

Pullback (trend-filtered): in the daily trend direction, price has run away from VWAP,
comes back to touch VWAP, and a candle closes back on the trend side of it.
"""

import math

import numpy as np

from . import charges
from . import settings as s


def _t(ts):
    return ts.strftime("%H:%M")


def day_features(day, prev_close, avg_or_volume):
    """What is known at 9:30: gap, opening range, relative volume."""
    orng = day.iloc[:s.OR_CANDLES]
    hi, lo = orng["High"].max(), orng["Low"].min()
    mid = (hi + lo) / 2
    or_vol = orng["Volume"].sum()
    return {
        "or_high": hi, "or_low": lo,
        "or_range_pct": (hi - lo) / mid,
        "gap_pct": (orng["Open"].iloc[0] - prev_close) / prev_close if prev_close else 0.0,
        "rel_vol": (or_vol / avg_or_volume) if avg_or_volume else np.nan,
    }


def _vwap(day):
    typical = (day["High"] + day["Low"] + day["Close"]) / 3
    return (typical * day["Volume"]).cumsum() / day["Volume"].cumsum().replace(0, np.nan)


def _open_trade(day, times, i, side, stop_ref, target_r, be_at_r, symbol):
    """Common part: size the trade and walk it forward from candle i+1."""
    entry = day["Open"].iloc[i + 1] * (1 + side * s.SLIPPAGE)
    dist = abs(entry - stop_ref)
    if dist / entry < s.MIN_STOP_PCT:
        dist = entry * s.MIN_STOP_PCT
    if dist / entry > s.MAX_STOP_PCT:
        return None                         # stop too far away: skip, do not chase
    stop = entry - side * dist
    target = entry + side * target_r * dist
    qty = math.floor(min(s.RISK_PER_TRADE / dist, s.CAPITAL * s.MARGIN_X / entry))
    if qty < 1:
        return None
    return _walk(day, times, i + 1, side, entry, stop, target, qty, symbol, dist, be_at_r)


def find_trade(day, feat, symbol, allowed_side=None, target_r=None, be_at_r=None):
    """Opening-range breakout. allowed_side: 1 long only, -1 short only, None both."""
    target_r = target_r or s.TARGET_R
    vwap = _vwap(day)
    times = [_t(ix) for ix in day.index]
    for i in range(s.OR_CANDLES, len(day) - 1):
        if times[i] > s.LAST_ENTRY:
            break
        c = day["Close"].iloc[i]
        if c > feat["or_high"] and c > vwap.iloc[i]:
            side = 1
        elif c < feat["or_low"] and c < vwap.iloc[i]:
            side = -1
        else:
            continue
        if allowed_side is not None and side != allowed_side:
            continue
        stop_ref = feat["or_low"] if side == 1 else feat["or_high"]
        return _open_trade(day, times, i, side, stop_ref, target_r, be_at_r, symbol)
    return None


def find_pullback(day, feat, symbol, trend, target_r=2.0, be_at_r=None):
    """VWAP pullback in the direction of the daily trend (trend = 1 or -1)."""
    if trend not in (1, -1):
        return None
    vwap = _vwap(day)
    times = [_t(ix) for ix in day.index]
    extended = False
    for i in range(s.OR_CANDLES, len(day) - 1):
        if times[i] > s.LAST_ENTRY:
            break
        v = vwap.iloc[i]
        o, h, l, c = (day[k].iloc[i] for k in ("Open", "High", "Low", "Close"))
        if trend == 1:
            extended = extended or (h > v * 1.002)
            ok = extended and l <= v * 1.001 and c > v and c > o
            stop_ref = min(l, day["Low"].iloc[i - 1])
        else:
            extended = extended or (l < v * 0.998)
            ok = extended and h >= v * 0.999 and c < v and c < o
            stop_ref = max(h, day["High"].iloc[i - 1])
        if ok:
            return _open_trade(day, times, i, trend, stop_ref, target_r, be_at_r, symbol)
    return None


def _walk(day, times, start, side, entry, stop, target, qty, symbol, dist, be_at_r):
    exit_px, reason, j = None, "time", len(day) - 1
    stop_cur, moved = stop, False
    for j in range(start, len(day)):
        o, h, l = day["Open"].iloc[j], day["High"].iloc[j], day["Low"].iloc[j]
        if times[j] >= s.EXIT_TIME:
            exit_px, reason = o * (1 - side * s.SLIPPAGE), "time"
            break
        hit_stop = l <= stop_cur if side == 1 else h >= stop_cur
        hit_tgt = h >= target if side == 1 else l <= target
        if hit_stop:                                   # stop wins a tie
            exit_px, reason = stop_cur * (1 - side * s.SLIPPAGE), ("breakeven" if moved else "stop")
            break
        if hit_tgt:
            exit_px, reason = target * (1 - side * s.SLIPPAGE), "target"
            break
        if be_at_r and not moved:
            reached = h >= entry + be_at_r * dist if side == 1 else l <= entry - be_at_r * dist
            if reached:
                stop_cur, moved = entry, True          # applies from the next candle
    if exit_px is None:
        exit_px, reason = day["Close"].iloc[-1] * (1 - side * s.SLIPPAGE), "time"
    buy_v = (entry if side == 1 else exit_px) * qty
    sell_v = (exit_px if side == 1 else entry) * qty
    gross = (exit_px - entry) * side * qty
    cost = charges.round_trip(buy_v, sell_v)
    return {
        "symbol": symbol, "side": "BUY" if side == 1 else "SELL",
        "entry_time": day.index[start], "exit_time": day.index[min(j, len(day) - 1)],
        "entry": entry, "stop": stop, "target": target, "exit": exit_px, "qty": qty,
        "reason": reason, "gross": gross, "charges": cost, "net": gross - cost,
        "value": entry * qty,
    }


# ---- live use: trade cards ---------------------------------------------------

def round_tick(value, direction="nearest"):
    """Round a price to the NSE tick. direction: nearest, down or up."""
    steps = value / s.TICK
    if direction == "down":
        steps = math.floor(steps + 1e-9)
    elif direction == "up":
        steps = math.ceil(steps - 1e-9)
    else:
        steps = round(steps)
    return round(steps * s.TICK, 2)


def size_trade(entry, stop_ref, side, target_r=None, min_stop_pct=None, max_stop_pct=None):
    """Entry, stop, target and quantity for ONE trade, sized so a stop-out costs about RISK_PER_TRADE.

    Returns a dict, or {"skip": reason}. The stop is rounded away from the entry and the target
    toward it, so the plan is never more optimistic than the real tick grid allows.
    """
    target_r = target_r or s.TARGET_R
    min_stop_pct = s.MIN_STOP_PCT if min_stop_pct is None else min_stop_pct
    max_stop_pct = s.MAX_STOP_PCT if max_stop_pct is None else max_stop_pct
    dist = abs(entry - stop_ref)
    if dist / entry < min_stop_pct:
        dist = entry * min_stop_pct
    if dist / entry > max_stop_pct:
        return {"skip": f"stop would be {dist / entry:.1%} away, wider than the {max_stop_pct:.1%} limit"}
    entry_r = round_tick(entry)
    stop_r = round_tick(entry - side * dist, "down" if side == 1 else "up")
    target_px = round_tick(entry + side * target_r * dist, "down" if side == 1 else "up")
    dist_r = abs(entry_r - stop_r)
    if dist_r <= 0:
        return {"skip": "stop and entry are the same price"}
    qty = math.floor(min(s.RISK_PER_TRADE / dist_r, s.CAPITAL * s.MARGIN_X / entry_r))
    if qty < 1:
        return {"skip": "too expensive for the position limit"}
    if side == 1:
        win = charges.round_trip(entry_r * qty, target_px * qty)
        lose = charges.round_trip(entry_r * qty, stop_r * qty)
    else:
        win = charges.round_trip(target_px * qty, entry_r * qty)
        lose = charges.round_trip(stop_r * qty, entry_r * qty)
    reward = abs(target_px - entry_r) * qty
    risk = dist_r * qty
    return {
        "side": "BUY" if side == 1 else "SELL", "entry": entry_r, "stop": stop_r, "target": target_px,
        "qty": qty, "value": round(entry_r * qty), "risk": round(risk), "reward": round(reward),
        "charges_target": round(win), "charges_stop": round(lose),
        "net_if_target": round(reward - win), "net_if_stop": round(-risk - lose),
        **_exit_levels(entry_r, stop_r, target_px, side, dist_r),
    }


def _exit_levels(entry, stop, target, side, dist):
    """Every exit price to put in Kite up front.

    SL-M trigger = the stop. SL (stop-limit) = the same trigger plus a limit a little beyond it, so a fast
    candle cannot jump past the order. Trail: once price has moved one stop-distance in your favour (+1R), move the
    stop to the entry price. That is the trailing rule that was backtested (variant F). Kite has no automatic
    trailing stop for shares, so you edit the stop order yourself when price reaches `trail_at`.
    """
    buffer = max(round_tick(entry * 0.002), 2 * s.TICK)
    sl_limit = round_tick(stop - side * buffer, "down" if side == 1 else "up")
    trail_at = round_tick(entry + side * dist, "up" if side == 1 else "down")
    return {
        "sl_m_trigger": stop, "sl_trigger": stop, "sl_limit": sl_limit,
        "trail_at": trail_at, "trail_to": entry, "stop_pct": round(dist / entry, 4),
    }


def plan_for_side(feat, side):
    """Levels for BUY (side 1) or SELL (side -1) as they would be if the entry fires at the opening-range edge.

    Shown before any signal, so the stop, target and trail values are known upfront. The entry is the range edge
    plus slippage; the real entry is the next candle's open after a candle closes beyond the range and past VWAP.
    """
    edge = feat["or_high"] if side == 1 else feat["or_low"]
    stop_ref = feat["or_low"] if side == 1 else feat["or_high"]
    entry = edge * (1 + side * s.INPLAY_SLIPPAGE)
    return size_trade(entry, stop_ref, side, max_stop_pct=s.INPLAY_MAX_STOP_PCT)


def live_signal(day, feat, side, target_r=None):
    """Where the gap-and-go setup stands for one stock, from COMPLETED candles only.

    `day` is today's completed 5-minute candles, `side` is 1 (gap up) or -1 (gap down).
    state: waiting, live, late, stopped, target or skipped.
    """
    target_r = target_r or s.TARGET_R
    vwap = _vwap(day)
    times = [_t(ix) for ix in day.index]
    last = len(day) - 1
    for i in range(s.OR_CANDLES, len(day)):
        if times[i] > s.LAST_ENTRY:
            break
        c = day["Close"].iloc[i]
        beyond = c > feat["or_high"] if side == 1 else c < feat["or_low"]
        right_of_vwap = c > vwap.iloc[i] if side == 1 else c < vwap.iloc[i]
        if not (beyond and right_of_vwap):
            continue
        planned = day["Open"].iloc[i + 1] if i + 1 <= last else c
        entry = planned * (1 + side * s.INPLAY_SLIPPAGE)
        stop_ref = feat["or_low"] if side == 1 else feat["or_high"]
        card = size_trade(entry, stop_ref, side, target_r, max_stop_pct=s.INPLAY_MAX_STOP_PCT)
        if "skip" in card:
            return {"state": "skipped", "reason": card["skip"], "signal_time": times[i]}
        state = "live"
        for j in range(i + 1, last + 1):
            h, l = day["High"].iloc[j], day["Low"].iloc[j]
            if (l <= card["stop"]) if side == 1 else (h >= card["stop"]):
                state = "stopped"
                break
            if (h >= card["target"]) if side == 1 else (l <= card["target"]):
                state = "target"
                break
        age = last - i
        if state == "live" and age > s.SIGNAL_MAX_AGE_CANDLES:
            state = "late"
        verb = "BUY" if side == 1 else "SELL"
        exit_verb = "SELL" if side == 1 else "BUY"
        order = (f"{verb} {card['qty']} MIS at about {card['entry']:.2f}; then place {exit_verb} SL-M with trigger "
                 f"{card['stop']:.2f} (or SL: trigger {card['sl_trigger']:.2f}, limit {card['sl_limit']:.2f}) and a {exit_verb} limit at "
                 f"{card['target']:.2f}. When price touches {card['trail_at']:.2f}, edit the stop to {card['trail_to']:.2f}. "
                 f"Square off by {s.EXIT_TIME}.")
        return {"state": state, "signal_time": times[i], "age_candles": age, "order": order, **card}
    return {"state": "waiting"}
