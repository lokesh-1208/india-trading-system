"""Each day's top-10 list, kept on disk as it was made, and the week tracker.

The model's tested rule picks once a week (the list for the first trading day of
the week). The other days' lists are for watching: which picks stay strong day
after day, which drop off, and what is new. Every list is saved, so a list is
never rewritten later when data changes, and the record becomes a live track
record.

A list is named by the day it is for (list_day): the list made from Friday's
close is Monday's list.
"""

import pandas as pd

import config
from trading import today

COLUMNS = ["list_day", "signal_day", "rank", "symbol", "score", "close", "weekly"]


def next_trading_day(calendar, position):
    """The day a list made from this close is for."""
    if position + 1 < len(calendar):
        return calendar[position + 1]
    day = calendar[position] + pd.Timedelta(days=1)
    while day.weekday() >= 5:
        day += pd.Timedelta(days=1)
    return day


def _week(day):
    return tuple(pd.Timestamp(day).isocalendar()[:2])


def daily_list(built, position, count=None):
    """The top stocks from one close: above their 20-day EMA, no results due soon."""
    count = config.DAILY_LIST_SIZE if count is None else count
    calendar = built.calendar
    signal_day = calendar[position]
    list_day = next_trading_day(calendar, position)
    previous = calendar[position]          # the close the list is made from
    ranking = built.score_on(position)
    trend = built.trading["in_trend"].iloc[position]
    due = today.results_soon(built.results, list_day)
    weekly = _week(list_day) != _week(previous)
    rows = []
    for rank, (symbol, row) in enumerate(ranking.iterrows(), start=1):
        if len(rows) >= count:
            break
        if bool(row.get("no_new_buy", False)) or symbol in due:
            continue
        if not bool(trend.get(symbol, False)):
            continue
        rows.append({"list_day": list_day.normalize(), "signal_day": signal_day.normalize(),
                     "rank": rank, "symbol": symbol, "score": round(float(row["score"]), 1),
                     "close": round(float(row["close"]), 2), "weekly": weekly})
    return pd.DataFrame(rows, columns=COLUMNS)


def load_log(path=None):
    path = config.PICKS_LOG_FILE if path is None else path
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    log = pd.read_csv(path, parse_dates=["list_day", "signal_day"])
    log["weekly"] = log["weekly"].astype(str).str.lower().eq("true")
    return log.reindex(columns=COLUMNS)


def update_log(built, path=None, weeks=2):
    """Make and save any missing lists for this week and the week before. Returns the log."""
    path = config.PICKS_LOG_FILE if path is None else path
    log = load_log(path)
    calendar = built.calendar
    latest = len(calendar) - 1
    this_week = _week(next_trading_day(calendar, latest))
    first_monday = pd.Timestamp.fromisocalendar(this_week[0], this_week[1], 1) \
        - pd.Timedelta(weeks=weeks - 1)
    done = set(pd.to_datetime(log["signal_day"]).dt.normalize()) if len(log) else set()
    new = []
    for position in range(latest, -1, -1):
        if next_trading_day(calendar, position) < first_monday:
            break
        if calendar[position].normalize() not in done:
            new.append(daily_list(built, position))
    if new:
        log = pd.concat([log] + new, ignore_index=True) if len(log) else pd.concat(new)
        log = log.sort_values(["list_day", "rank"]).reset_index(drop=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        log.to_csv(path, index=False)
    return log


def tracker(log, list_day, closes, benchmark=None):
    """One row per stock picked this week (and last week's picks still on today's list).

    closes: a table of closing prices, a column per stock.
    Returns (rows, days): days are this week's list days so far, oldest first.
    Each row: symbol, ranks {day: rank}, days_on, last_week, on_today, first_day,
    since_first_% (from the close the stock was first picked on to the latest close),
    nifty_% (the benchmark over the same days, when given) and vs_nifty.
    """
    if len(log) == 0:
        return pd.DataFrame(), []
    log = log[log["list_day"] <= pd.Timestamp(list_day)].copy()
    log["week"] = log["list_day"].map(_week)
    week = _week(list_day)
    previous = _week(pd.Timestamp(list_day) - pd.Timedelta(weeks=1))
    this = log[log["week"] == week]
    last = log[log["week"] == previous]
    days = sorted(this["list_day"].unique())
    today_list = set(this.loc[this["list_day"] == pd.Timestamp(list_day), "symbol"])
    symbols = list(dict.fromkeys(list(this["symbol"]) + [s for s in last["symbol"]
                                                        if s in today_list]))
    rows = []
    for symbol in symbols:
        mine = pd.concat([last[last["symbol"] == symbol], this[this["symbol"] == symbol]])
        first = mine.sort_values("list_day").iloc[0]
        latest_close = closes[symbol].dropna().iloc[-1] if symbol in closes else float("nan")
        since = round((latest_close / first["close"] - 1) * 100, 1)
        nifty = float("nan")
        if benchmark is not None and len(benchmark):
            base = benchmark[benchmark.index <= first["signal_day"]]
            if len(base):
                nifty = round((benchmark.iloc[-1] / base.iloc[-1] - 1) * 100, 1)
        rows.append({
            "symbol": symbol,
            "ranks": {day: int(r) for day, r in zip(this.loc[this["symbol"] == symbol, "list_day"],
                                                   this.loc[this["symbol"] == symbol, "rank"])},
            "days_on": int((this["symbol"] == symbol).sum()),
            "last_week": bool((last["symbol"] == symbol).any()),
            "on_today": symbol in today_list,
            "first_day": first["list_day"],
            "since_first_%": since,
            "nifty_%": nifty,
            "vs_nifty": round(since - nifty, 1) if nifty == nifty else float("nan"),
        })
    table = pd.DataFrame(rows)
    table = table.sort_values(["on_today", "days_on"], ascending=[False, False],
                              kind="stable").reset_index(drop=True)
    return table, days


def weekly_list(log, list_day):
    """The list made for the first trading day of list_day's week: the tested one."""
    if len(log) == 0:
        return pd.DataFrame(columns=COLUMNS)
    week = _week(list_day)
    rows = log[(log["list_day"] <= pd.Timestamp(list_day)) & log["weekly"]
               & (log["list_day"].map(_week) == week)]
    return rows.sort_values("rank").reset_index(drop=True)


def weekly_status(weekly, last_close, in_trend, results_due, held, places, max_gap,
                  budget=None):
    """What to do with each stock on the weekly list today.

    The first `places` stocks not already held are the picks, the rest backups.
    Limits stay at the weekly list's close + max_gap all week.
    status: "Buy" (in range), "Missed" (above the limit), "Trend broke" (closed
    below its 20-day EMA), "Results soon" (results within the block window), "You hold",
    "Too costly" (one share costs more than `budget`, the money per stock; the
    backtest skipped such stocks too, and they do not use up a pick).
    """
    rows = []
    picks_left = places
    for row in weekly.itertuples():
        limit = row.close * (1 + max_gap)
        last = float(last_close.get(row.symbol, float("nan")))
        if row.symbol in held:
            status, kind = "You hold", "Held"
        elif budget is not None and budget < limit:
            status, kind = "Too costly", "Skipped"
        else:
            kind = "Pick" if picks_left > 0 else "Backup"
            picks_left -= 1 if kind == "Pick" else 0
            if row.symbol in results_due:
                status = "Results soon"
            elif not bool(in_trend.get(row.symbol, True)):
                status = "Trend broke"
            elif last == last and last > limit:
                status = "Missed"
            else:
                status = "Buy"
        rows.append({"symbol": row.symbol, "rank": row.rank, "score": row.score,
                     "close": row.close, "limit": round(limit, 2), "last": round(last, 2),
                     "kind": kind, "status": status})
    return pd.DataFrame(rows, columns=["symbol", "rank", "score", "close", "limit", "last",
                                       "kind", "status"])


def list_scorecard(log, closes, benchmark, top=5):
    """How each weekly list's top picks did from their signal close to the latest close."""
    rows = []
    weekly = log[log["weekly"]]
    for day, group in weekly.groupby("list_day"):
        best = group.sort_values("rank").head(top)
        moves = [(closes[s].dropna().iloc[-1] / c - 1) * 100
                 for s, c in zip(best["symbol"], best["close"]) if s in closes]
        signal = group["signal_day"].iloc[0]
        base = benchmark[benchmark.index <= signal]
        nifty = (benchmark.iloc[-1] / base.iloc[-1] - 1) * 100 if len(base) else float("nan")
        average = sum(moves) / len(moves) if moves else float("nan")
        rows.append({"list_day": day, "picks": ", ".join(best["symbol"]),
                     "average_%": round(average, 1), "nifty_%": round(nifty, 1),
                     "vs_nifty": round(average - nifty, 1)})
    return pd.DataFrame(rows, columns=["list_day", "picks", "average_%", "nifty_%", "vs_nifty"]
                        ).sort_values("list_day", ascending=False).reset_index(drop=True)
