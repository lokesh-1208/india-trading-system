"""The 9:30 scan: which stocks are "in play" today, and where each one stands.

Steps (the same rules and the same 5-minute figures the backtest used):
  1. Download today's 5-minute candles for the Nifty 500 (a few minutes; Yahoo's daily bars
     disagree with the 5-minute data on the open and the previous close, so they are not used).
  2. In play = opened at least GAP_MIN away from yesterday's close, on at least REL_VOL_MIN times
     the normal opening-15-minute volume.
  3. Rank by that volume multiple and trade only in the direction of the gap. The top TOP_N
     are "tested" (that is what the backtests used); the rest of the in-play stocks follow.
  4. If fewer than WATCH_N are in play, "near misses" (smaller gap or volume) fill the list up to
     WATCH_N. They are NOT tested.
  5. For each, report the opening range and (once a candle closes beyond it) a trade card.

A quick refresh later in the day downloads only the in-play list.
"""

import json
import threading
import time

import numpy as np
import pandas as pd

from . import data, strategy
from . import settings as s

IST = "Asia/Kolkata"
ANCHORS = ["RELIANCE", "TCS", "HDFCBANK", "INFY"]      # liquid names that define "the latest session"
_lock = threading.Lock()


def now_ist():
    return pd.Timestamp.now(tz=IST)


def _fresh(symbol, seconds):
    """True if this stock's candles were saved less than `seconds` ago."""
    try:
        return time.time() - data._path(symbol).stat().st_mtime < seconds
    except OSError:
        return False


def _refresh(symbols, report=None, step="Downloading 5-minute candles", batch=15, fresh_seconds=120):
    """Download 5-minute candles, skipping stocks saved a moment ago."""
    todo = [x for x in symbols if not _fresh(x, fresh_seconds)]
    done = len(symbols) - len(todo)
    for i in range(0, len(todo), batch):
        try:
            data.refresh(todo[i:i + batch], period="5d", batch=batch)
        except Exception:
            pass
        done += len(todo[i:i + batch])
        if report:
            report(step, done, len(symbols))


def _inputs(symbol, session_date, until):
    """(today's completed candles, previous close, normal opening volume) or None."""
    df = data.load(symbol)
    if df is None or df.empty:
        return None
    sessions = {d: g for d, g in df.groupby(df.index.date)}
    past = [d for d in sorted(sessions) if d < session_date and len(sessions[d]) >= s.MIN_CANDLES
            and sessions[d].index[-1].strftime("%H:%M") >= "15:20"]
    day = sessions.get(session_date)
    if day is None or len(past) < 6:
        return None
    day = day[day.index + pd.Timedelta(minutes=5) <= until]          # completed candles only
    if len(day) < s.OR_CANDLES:
        return None
    if [ix.strftime("%H:%M") for ix in day.index[:s.OR_CANDLES]] != ["09:15", "09:20", "09:25"]:
        return None
    avg = float(np.mean([sessions[d]["Volume"].iloc[:s.OR_CANDLES].sum() for d in past[-20:]]))
    return day, float(sessions[past[-1]]["Close"].iloc[-1]), avg


def _card(symbol, day, prev_close, avg, feat=None):
    feat = feat or strategy.day_features(day, prev_close, avg)
    side = 1 if feat["gap_pct"] > 0 else -1
    signal = strategy.live_signal(day, feat, side)
    vwap = strategy._vwap(day).iloc[-1]
    plans = {}
    for name, sd in (("BUY", 1), ("SELL", -1)):
        plans[name] = {"with_gap": sd == side, "levels": strategy.plan_for_side(feat, sd),
                       "signal": signal if sd == side else strategy.live_signal(day, feat, sd)}
    return {
        "symbol": symbol, "gap_pct": round(feat["gap_pct"], 4), "rel_vol": round(feat["rel_vol"], 1),
        "or_high": round(float(feat["or_high"]), 2), "or_low": round(float(feat["or_low"]), 2),
        "or_range_pct": round(float(feat["or_range_pct"]), 4), "direction": "BUY" if side == 1 else "SELL",
        "last": round(float(day["Close"].iloc[-1]), 2), "vwap": round(float(vwap), 2),
        "last_candle": day.index[-1].strftime("%H:%M"), "signal": signal, "plans": plans,
    }, feat


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def latest():
    try:
        return json.loads(s.LAST_SCAN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(full=True, report=None, now=None, fresh_seconds=120):
    """Run the scan. full=True looks at the whole Nifty 500; full=False refreshes the in-play list only."""
    now = now if now is not None else now_ist()
    with _lock:
        previous = latest() if not full else None
        if report:
            report("Finding the latest session", 0, 1)
        _refresh(ANCHORS, step="Finding the latest session", fresh_seconds=fresh_seconds)
        dates = []
        for sym in ANCHORS:
            df = data.load(sym)
            if df is not None and not df.empty:
                dates.append(df.index[-1].date())
        if not dates:
            return {"status": "no_data", "message": "No candles saved yet. Run update_intraday.bat first."}
        session_date = max(dates)
        is_today = session_date == now.date()
        until = now if is_today else pd.Timestamp(session_date, tz=IST) + pd.Timedelta(days=1)

        if is_today and now.strftime("%H:%M") < s.PHASES["range_end"]:
            return {"status": "wait", "as_of": now.strftime("%Y-%m-%d %H:%M"),
                    "message": "The opening range is still forming. Scan after 9:30."}

        universe = s.wide_symbols(500)
        if full or not previous or not previous.get("inplay_symbols"):
            shortlist, checked = universe, len(universe)
        else:
            shortlist, checked = previous["inplay_symbols"], previous.get("scanned", 0)
        _refresh(shortlist, report, batch=10, fresh_seconds=fresh_seconds)

        in_play, near, missing = [], [], 0
        for sym in shortlist:
            got = _inputs(sym, session_date, until)
            if got is None:
                missing += 1
                continue
            day, prev_close, avg = got
            feat = strategy.day_features(day, prev_close, avg)
            gap, vol, rng = abs(feat["gap_pct"]), feat["rel_vol"], feat["or_range_pct"]
            if np.isnan(vol) or rng < s.MIN_OR_RANGE_PCT:
                continue
            if gap >= s.GAP_MIN and vol >= s.REL_VOL_MIN:
                kind = "in_play"
            elif gap >= s.NEAR_GAP and vol >= s.NEAR_REL_VOL:
                kind = "near"
            else:
                continue
            card, _ = _card(sym, day, prev_close, avg, feat)
            card["_vol"] = float(vol)                      # exact figure, used only to rank
            (in_play if kind == "in_play" else near).append(card)
        in_play.sort(key=lambda c: c["_vol"], reverse=True)
        near.sort(key=lambda c: c["_vol"], reverse=True)
        for i, c in enumerate(in_play):
            c["tier"] = "tested" if i < s.TOP_N else "in_play"
        for c in near:
            c["tier"] = "near"
        watch = (in_play + near)[:s.WATCH_N]
        for i, c in enumerate(watch, 1):
            c["rank"] = i
        for c in in_play + near:
            c.pop("_vol", None)
        top = watch
        last_candle = max((c["last_candle"] for c in top), default=None)
        lag = None
        if is_today and last_candle:
            lag = int((now - pd.Timestamp(f"{now.date()} {last_candle}", tz=IST)).total_seconds() // 60) - 5
        result = {
            "status": "ok", "as_of": now.strftime("%Y-%m-%d %H:%M"), "session_date": str(session_date),
            "is_today": is_today, "scanned": checked, "in_play": len(in_play), "near_miss": len(near),
            "no_history": missing, "candidates": top,
            "others": [c["symbol"] for c in (in_play + near)[s.WATCH_N:]],
            "inplay_symbols": [c["symbol"] for c in (in_play + near)], "data_lag_minutes": lag,
        }
        result = _json_safe(result)
        s.DATA_DIR.mkdir(parents=True, exist_ok=True)
        s.LAST_SCAN_FILE.write_text(json.dumps(result), encoding="utf-8")
        return result


class Runner:
    """Runs the scan in the background so the page can show progress."""

    def __init__(self):
        self._lock = threading.Lock()
        self.state = {"running": False, "step": None, "done": 0, "total": 0, "error": None}

    def snapshot(self):
        with self._lock:
            return dict(self.state)

    def start(self, full=True):
        with self._lock:
            if self.state["running"]:
                return False
            self.state.update(running=True, step="Starting", done=0, total=0, error=None)
        threading.Thread(target=self._work, args=(full,), daemon=True).start()
        return True

    def _report(self, step, done, total):
        with self._lock:
            self.state.update(step=step, done=done, total=total)

    def _work(self, full):
        try:
            run(full=full, report=self._report)
            error = None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        with self._lock:
            self.state.update(running=False, error=error)


RUNNER = Runner()
