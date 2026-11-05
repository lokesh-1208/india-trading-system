"""Each day's top-10 list, kept on disk as it was made, and the week's watchlist.

A fresh top 10 is made every day. The week's watchlist (watchlist()) grows with
them: Monday's list starts it, each later day adds the names that are new, and on
the next week's first list the whole watchlist is re-ranked and its best 10 carry
over. Any stock on it may be bought on any day it passes the checks (5 Nov 2026,
Lokesh's choice). The tested rule still buys only from the Monday top 10: buying
every day did worse in all three test periods (backtest log, entry 12), so those
ten are marked "tested picks" and the rest "your choice". Every list is saved, so
a list is never rewritten later when data changes, and the record becomes a live
track record.

A list is named by the day it is for (list_day): the list made from Friday's
close is Monday's list.

The weekly list has two parts (group): "top", the model's top 10 overall, which
the tested buying rule picks from; and "sector", the best stocks of each sector
that the top 10 leaves out, so every sector has up to config.SECTOR_PICKS stocks
on the list. A sector that already has more in the top 10 keeps them all. The
sector stocks pass the same checks (above the 20-day EMA, no results due, score
at least config.SECTOR_MIN_SCORE) and get the same limits and stops, but buying
them is your own choice: the backtest only tested buying from the top 10.
"""

import pandas as pd

import config

CARRY_OVER = 10          # best stocks of last week's watchlist that start the next week
from trading import holidays, today

COLUMNS = ["list_day", "signal_day", "rank", "symbol", "score", "close", "weekly", "group",
           "industry"]


def next_trading_day(calendar, position):
    """The day a list made from this close is for."""
    if position + 1 < len(calendar):
        return calendar[position + 1]
    return holidays.next_trading_day(calendar[position])


def _week(day):
    return tuple(pd.Timestamp(day).isocalendar()[:2])


def daily_list(built, position, count=None, per_sector=None, top=None):
    """The top stocks from one close: above their 20-day EMA, no results due soon.

    A weekly list (the one for the first trading day of a week) also gets the best
    stocks of each sector, up to per_sector (config.SECTOR_PICKS) per sector counting
    the top ones, as group "sector".
    top: symbols of a top 10 already saved for this close; the sector part is then
    made around it (used once, to add the sector part to a list saved before it existed).
    """
    count = config.DAILY_LIST_SIZE if count is None else count
    per_sector = config.SECTOR_PICKS if per_sector is None else per_sector
    industry = getattr(built, "industry", None) or {}
    calendar = built.calendar
    signal_day = calendar[position]
    list_day = next_trading_day(calendar, position)
    ranking = built.score_on(position)
    trend = built.trading["in_trend"].iloc[position]
    due = today.results_soon(built.results, list_day)
    weekly = _week(list_day) != _week(signal_day)

    def row_for(rank, symbol, row, group):
        return {"list_day": list_day.normalize(), "signal_day": signal_day.normalize(),
                "rank": rank, "symbol": symbol, "score": round(float(row["score"]), 1),
                "close": round(float(row["close"]), 2), "weekly": weekly, "group": group,
                "industry": industry.get(symbol, "") or "Other"}

    eligible = []
    for rank, (symbol, row) in enumerate(ranking.iterrows(), start=1):
        if bool(row.get("no_new_buy", False)) or symbol in due:
            continue
        if not bool(trend.get(symbol, False)):
            continue
        eligible.append((rank, symbol, row))
        if not weekly and len(eligible) >= count:
            break

    if top is None:
        rows = [row_for(rank, symbol, row, "top") for rank, symbol, row in eligible[:count]]
        taken = {r["symbol"] for r in rows}
    else:
        rows, taken = [], set(top)
    if weekly:
        in_sector = {}
        for symbol in taken:
            sector = industry.get(symbol, "") or "Other"
            in_sector[sector] = in_sector.get(sector, 0) + 1
        for rank, symbol, row in eligible:
            sector = industry.get(symbol, "") or "Other"
            if symbol in taken or in_sector.get(sector, 0) >= per_sector:
                continue
            # Past the top 10: only the best of each sector, and only if the model likes it.
            if float(row["score"]) < config.SECTOR_MIN_SCORE:
                break                                 # the ranking is best first
            in_sector[sector] = in_sector.get(sector, 0) + 1
            rows.append(row_for(rank, symbol, row, "sector"))
    return pd.DataFrame(rows, columns=COLUMNS)


def load_log(path=None):
    path = config.PICKS_LOG_FILE if path is None else path
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    log = pd.read_csv(path, parse_dates=["list_day", "signal_day"])
    log["weekly"] = log["weekly"].astype(str).str.lower().eq("true")
    log = log.reindex(columns=COLUMNS)
    # Lists saved before the sector part existed are all top-10 lists.
    log["group"] = log["group"].fillna("top")
    log["industry"] = log["industry"].fillna("")
    return log


def close_is_final(day):
    """True once NSE's end-of-day file for `day` is saved, so its closes are the real ones.

    16 Oct 2026: Monday's list was saved at 6:42 pm from mid-day prices an earlier
    update had stored (TECHM 1,725 against a real close of 1,790), four minutes
    before NSE's file arrived. The clock alone does not say the closes are final.
    """
    from trading import gaps
    return (gaps.BHAVCOPY_DIR / f"{pd.Timestamp(day):%Y-%m-%d}.csv").exists()


def update_log(built, path=None, weeks=2, final=None):
    """Make and save any missing lists for this week and the week before. Returns the log.

    final(day): whether a day's closes are final; the latest day gets a list only then.
    """
    path = config.PICKS_LOG_FILE if path is None else path
    final = close_is_final if final is None else final
    log = load_log(path)
    calendar = built.calendar
    latest = len(calendar) - 1
    this_week = _week(next_trading_day(calendar, latest))
    first_monday = pd.Timestamp.fromisocalendar(this_week[0], this_week[1], 1) \
        - pd.Timedelta(weeks=weeks - 1)
    done = set(pd.to_datetime(log["signal_day"]).dt.normalize()) if len(log) else set()
    unfinished = _unfinished_day()
    new = []
    for position in range(latest, -1, -1):
        if next_trading_day(calendar, position) < first_monday:
            break
        # A list is saved for good, so never make one from a day that has not closed yet
        # (16 Oct 2026: a list saved at 11:34 am from the morning's prices kept CUB and
        # CHENNPETRO on it after their close fell below the trend line).
        if calendar[position].normalize() == unfinished:
            continue
        if position == latest and not final(calendar[position]):
            continue
        if calendar[position].normalize() not in done:
            new.append(daily_list(built, position))
        elif _missing_sector_part(log, calendar[position], calendar, position):
            # A weekly list saved before the sector part existed: add that part once,
            # from the same close. Its top 10 is left exactly as saved.
            saved = log.loc[pd.to_datetime(log["signal_day"]).dt.normalize()
                            == calendar[position].normalize(), "symbol"]
            new.append(daily_list(built, position, top=list(saved)))
    new = [part for part in new if len(part)]
    if new:
        log = pd.concat([log] + new, ignore_index=True) if len(log) else pd.concat(new)
        log = log.sort_values(["list_day", "rank"]).reset_index(drop=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        log.to_csv(path, index=False)
    return log


def _missing_sector_part(log, signal_day, calendar, position):
    if _week(next_trading_day(calendar, position)) == _week(signal_day):
        return False                                # not a weekly list
    mine = log[pd.to_datetime(log["signal_day"]).dt.normalize() == signal_day.normalize()]
    return len(mine) > 0 and not (mine["group"] == "sector").any()


def _unfinished_day(now=None):
    """Today's date (India time) before its close is final, else None."""
    now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None) if now is None \
        else pd.Timestamp(now)
    return now.normalize() if now.hour < today.CLOSE_READY_HOUR else None


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
    log = top_part(log[log["list_day"] <= pd.Timestamp(list_day)]).copy()
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


def top_part(table):
    """Only the top-10 rows of a list (the part the tested rule buys from)."""
    if "group" not in table.columns:
        return table
    return table[table["group"].fillna("top") == "top"]


def weekly_status(weekly, last_close, in_trend, results_due, held, places, max_gap,
                  budget=None):
    """What to do with each stock on the weekly list today.

    The first `places` buyable stocks (status "Buy") not already held are the
    picks, the other buyable ones backups. A stock that cannot be bought today
    (missed, trend broke, results soon, too costly) does not use up a pick: the
    backtest skips such a stock and moves on to the next one on the list.
    Limits stay at the weekly list's close + max_gap all week.
    Sector rows (group "sector") never take a pick: when buyable their kind is
    "Sector", a choice left to you.
    status: "Buy" (in range), "Missed" (above the limit), "Trend broke" (closed
    below its 20-day EMA), "Results soon" (results within the block window), "You hold",
    "Too costly" (one share costs more than `budget`, the money per stock).
    kind: "Pick", "Backup", "Sector", "Held" or "Skipped".
    """
    rows = []
    picks_left = places
    for row in weekly.itertuples():
        group = getattr(row, "group", "top")
        group = group if isinstance(group, str) and group else "top"
        limit = row.close * (1 + max_gap)
        last = float(last_close.get(row.symbol, float("nan")))
        if row.symbol in held:
            status, kind = "You hold", "Held"
        elif budget is not None and budget < limit:
            status, kind = "Too costly", "Skipped"
        elif row.symbol in results_due:
            status, kind = "Results soon", "Skipped"
        elif not bool(in_trend.get(row.symbol, True)):
            status, kind = "Trend broke", "Skipped"
        elif last == last and last > limit:
            status, kind = "Missed", "Skipped"
        elif group == "sector":
            status, kind = "Buy", "Sector"
        else:
            status = "Buy"
            kind = "Pick" if picks_left > 0 else "Backup"
            picks_left -= 1 if kind == "Pick" else 0
        industry = getattr(row, "industry", "")
        rows.append({"symbol": row.symbol, "rank": row.rank, "score": row.score,
                     "close": row.close, "limit": round(limit, 2), "last": round(last, 2),
                     "kind": kind, "status": status, "group": group,
                     "industry": industry if isinstance(industry, str) else ""})
    return pd.DataFrame(rows, columns=["symbol", "rank", "score", "close", "limit", "last",
                                       "kind", "status", "group", "industry"])


def watchlist(log, list_day, rank_on):
    """The week's watchlist for list_day: last week's best plus every daily top 10 so far.

    rank_on(day): symbols ranked best first on that close (the model's score), used on
    the close the week's first list was made from to choose the CARRY_OVER stocks of
    last week's watchlist that start this week.
    Returns one row per stock, in the order it joined: symbol, added (the list day it
    joined this week, or None when carried over), carried, weeks_on (weeks in a row on
    the watchlist, this one included), first_day / first_signal / first_close (where the
    current run on the watchlist began), tested (on this week's first top 10, the list
    the backtest buys from), days_on (this week's daily lists it was on) and ranks
    {list day: rank}.
    """
    columns = ["symbol", "added", "carried", "weeks_on", "first_day", "first_signal",
               "first_close", "tested", "days_on", "ranks"]
    top = top_part(log[log["list_day"] <= pd.Timestamp(list_day)]).copy() if len(log) \
        else log
    if len(top) == 0:
        return pd.DataFrame(columns=columns)
    top["week"] = top["list_day"].map(_week)
    previous, first, streak = [], {}, {}
    rows = None
    for week in sorted(top["week"].unique()):
        rows = top[top["week"] == week].sort_values(["list_day", "rank"])
        carry = []
        if previous:
            order = {symbol: place for place, symbol in enumerate(rank_on(rows["signal_day"].iloc[0]))}
            carry = sorted([s for s in previous if s in order], key=order.get)[:CARRY_OVER]
        pool = list(carry)
        for symbol in rows["symbol"]:
            if symbol not in pool:
                pool.append(symbol)
        began = {}
        for symbol in pool:
            if symbol in previous and symbol in first:
                began[symbol] = first[symbol]
            else:
                mine = rows[rows["symbol"] == symbol].iloc[0]
                began[symbol] = (mine["list_day"], mine["signal_day"], float(mine["close"]))
        streak = {s: (streak.get(s, 0) + 1 if s in previous else 1) for s in pool}
        first, previous, carried = began, pool, set(carry)
    week_rows = rows
    tested_rows = week_rows[week_rows["weekly"].astype(bool)]
    if len(tested_rows) == 0:              # no Monday list saved: the week's first list
        tested_rows = week_rows[week_rows["list_day"] == week_rows["list_day"].min()]
    tested = set(tested_rows["symbol"])
    out = []
    for symbol in previous:
        mine = week_rows[week_rows["symbol"] == symbol]
        out.append({
            "symbol": symbol,
            "added": None if symbol in carried and symbol not in set(mine["symbol"])
            else (mine["list_day"].min() if len(mine) else None),
            "carried": symbol in carried,
            "weeks_on": int(streak[symbol]),
            "first_day": first[symbol][0], "first_signal": first[symbol][1],
            "first_close": first[symbol][2],
            "tested": symbol in tested,
            "days_on": int(len(mine)),
            "ranks": {day: int(rank) for day, rank in zip(mine["list_day"], mine["rank"])},
        })
    return pd.DataFrame(out, columns=columns)
