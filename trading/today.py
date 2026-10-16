"""Everything for one trading day, from the one model (full model, swing style).

The app's Today page shows three lists built here:
  buy_list   - the best 10 stocks to buy, with a buy range and a stop-loss
  my_stocks  - the stocks you hold (from the journal), each HOLD or SELL with the reason
  avoid_list - the weakest scores: do not buy, and exit if you hold one

Entry range: the model buys at the open after the signal close. Backtests
(backtest log, entry 7) showed that buying a stock that has already risen more
than 2% above that close lost money, while buying below it did well. So the
range is "anything up to signal close + 2%", with no lower limit.
"""

import math
import re

import numpy as np
import pandas as pd

import config
from trading import holidays


def rules():
    """The trading rules of the one model."""
    return config.MODEL_STYLES[config.MODEL_STYLE]


def buy_day(now):
    """The day an order placed now would be bought: today in market hours, else the next
    trading day (weekends and NSE holidays skipped)."""
    day = pd.Timestamp(now.date())
    if now.hour >= CLOSE_READY_HOUR - 1:                  # after 3:30 pm
        return holidays.next_trading_day(day)
    return holidays.this_or_next_trading_day(day)


def results_soon(results, day):
    """{symbol: results date} for results due within the block window after `day`."""
    if results is None or len(results) == 0:
        return {}
    window = results[(results["date"] >= day)
                     & (results["date"] <= day + pd.Timedelta(days=config.RESULTS_BLOCK_DAYS))]
    return window.groupby("symbol")["date"].min().to_dict()


def buy_list(plan, money, count=10, results_due=None):
    """The top stocks to buy, best first.

    plan: Model.decision(...). Picks are the stocks the model buys now; the rest
    are backups, used when a pick is already above its range.
    results_due: {symbol: date} of results within the block window from the buy
    day. Those are left out (the model buys nothing just before results), and the
    next stock moves up into its place.
    Returns a table with one row per stock.
    """
    style = rules()
    above = style.get("max_gap") or 0.0
    stop = style["stop_loss"]
    per_stock = money / style["positions"]
    held = set(plan["keep"]) | set(plan["sell"])
    # Picks, signal prices and limits come from the weekly check day and do not move
    # during the week. Buying on any day was tested and did worse than buying weekly.
    in_trend = plan.get("signal_in_trend", plan.get("in_trend", {}))
    today = plan.get("signal_scores", plan["today"])
    last_prices = plan.get("last_price", {})
    trend_now = plan.get("in_trend", {})
    results_due = results_due or {}
    picks_wanted = len(plan["buy"]) if plan["market_ok"] else 0

    rows = []
    for rank, (symbol, row) in enumerate(today.iterrows(), start=1):
        if len(rows) >= count:
            break
        if symbol in held or bool(row.get("no_new_buy", False)) or symbol in results_due:
            continue
        if not bool(in_trend.get(symbol, True)):
            continue                      # below its 20-day EMA: the model does not buy it
        entry = float(row["close"])
        if not entry > 0:
            continue
        up_to = entry * (1 + above)
        shares = math.floor(per_stock / up_to)
        last = last_prices.get(symbol, entry) if hasattr(last_prices, "get") else entry
        last = float(last) if last == last else entry
        rows.append({
            "rank": rank,
            "symbol": symbol,
            "score": float(row["score"]),
            "type": "Pick" if len(rows) < picks_wanted else "Backup",
            "entry": round(entry, 2),
            "buy_up_to": round(up_to, 2),
            "stop_loss": round(entry * (1 - stop), 2),
            "shares": shares,
            "amount": round(shares * entry),
            "last": round(last, 2),
            "in_range": last <= up_to,
            "trend_ok": bool(trend_now.get(symbol, True)),
        })
    table = pd.DataFrame(rows, columns=["rank", "symbol", "score", "type", "entry",
                                        "buy_up_to", "stop_loss", "shares", "amount",
                                        "last", "in_range", "trend_ok"])
    # Picks first, then backups, each in score order.
    order = table["type"].map({"Pick": 0, "Backup": 1})
    return table.assign(_order=order).sort_values(["_order", "rank"]).drop(
        columns="_order").reset_index(drop=True)


def money_plan(capital, open_cost, holdings_value, closed_net, positions, held, share, picks,
               scales=None):
    """How much to put in today, from the money you actually have.

    Follows the backtest's sizing rule exactly: each new buy gets
    (cash + holdings at their value) / positions x share, but never more than the
    cash left. Picks are bought in list order until the free places or the cash run out.

    capital:        the total money you set aside for trading
    open_cost:      what your open positions cost
    holdings_value: what they are worth now
    closed_net:     profit (or loss) on closed trades after charges, which stays in the account
    held:           how many positions are open
    share:          1.0 in a strong market, 0.75 in caution
    picks:          [(symbol, buy limit)] buyable now, best first
    scales:         {symbol: share of a full place} from risk sizing (1.0 = full place)
    Returns a dictionary for the page.
    """
    cash = max(0.0, capital + closed_net - open_cost)
    account = cash + holdings_value
    per_stock = account / positions * share
    places = max(0, positions - held)
    left = cash
    buys = []
    for symbol, limit in picks:
        if len(buys) >= places:
            break
        scale = 1.0 if not scales else float(scales.get(symbol, 1.0))
        budget = min(per_stock * scale, left / 1.002)    # leave room for charges
        shares = math.floor(budget / limit) if limit > 0 else 0
        if shares < 1:
            continue
        amount = shares * limit
        left -= amount
        buys.append({"symbol": symbol, "shares": shares, "limit": round(limit, 2),
                     "amount": round(amount), "scale": round(scale, 2)})
    open_places = places - len(buys)
    reserve = min(left, open_places * per_stock)       # kept for places still empty
    idle = max(0.0, left - reserve)
    if places == 0:
        note = f"All {positions} places are full: no new buys until something is sold."
    elif cash < per_stock * 0.25:
        note = "Your holdings already use your trading money: add money or wait for a sale."
    elif not buys:
        note = "Nothing buyable on this week's list right now: keep the cash."
    elif open_places > 0:
        note = (f"Keep ₹{reserve:,.0f} for the {open_places} empty place"
                f"{'s' if open_places != 1 else ''}: a later list fills "
                f"{'them' if open_places != 1 else 'it'}.")
    else:
        note = "All places will be full."
    if idle >= 1000 and places > 0 and cash >= per_stock * 0.25:
        why = ("the market is in caution, so each place gets 75%" if share < 1
               else "holdings bought for less than a full place leave money over")
        note += f" ₹{idle:,.0f} stays as cash ({why})."
    return {"capital": round(capital), "account": round(account), "cash": round(cash),
            "invested": round(open_cost), "holdings_value": round(holdings_value),
            "per_stock": round(per_stock), "share": share, "places": places,
            "buys": buys, "spend": round(sum(item["amount"] for item in buys)),
            "cash_after": round(left), "open_places_after": open_places,
            "reserve": round(reserve), "idle": round(idle), "note": note, "warning": None}


def my_stocks(plan, positions, trend_lines, last_day=None):
    """Your open positions with what to do about each.

    positions: journal.open_positions(trades, prices).
    trend_lines: {symbol: today's 20-day EMA}.
    last_day: the date of the latest close. A stock bought after it has no close
    since the buy yet, so it is marked WAIT and shows no gain.
    """
    stop = rules()["stop_loss"]
    trail = rules().get("profit_trail") or {}
    trailed, peaks = set(plan.get("trailed", [])), plan.get("peaks", {})
    stopped, broken = set(plan.get("stopped", [])), set(plan.get("trend_broken", []))
    warned = set(plan.get("trend_warned", []))
    confirm = int(plan.get("exit_confirm", 1))
    sell = set(plan["sell"])
    rows = []
    if len(positions):
        grouped = positions.groupby("symbol").agg(
            quantity=("quantity", "sum"), cost=("cost", "sum"), last_price=("last_price", "last"),
            bought=("buy_date", "min"))
        for symbol, row in grouped.iterrows():
            paid = row["cost"] / row["quantity"]
            bought = pd.Timestamp(row["bought"]).normalize()
            new = last_day is not None and bought > pd.Timestamp(last_day).normalize()
            days = 0 if (last_day is None or new) else int(
                np.busday_count(bought.date(), pd.Timestamp(last_day).date()))
            if new:
                action, reason = "WAIT", ("bought after the latest close; first check after "
                                          "today's close")
            elif symbol in stopped:
                action, reason = "SELL", f"{stop:.0%} or more below your buy price (stop-loss)"
            elif symbol in trailed:
                action, reason = "SELL", (f"fell {trail['trail']:.0%} from its high after a "
                                          f"{trail['trigger']:.0%}+ gain (profit trail)")
            elif symbol in broken:
                action, reason = "SELL", (
                    f"closed below its {config.EMA_FAST}-day EMA "
                    + (f"{confirm} days in a row " if confirm > 1 else "") + "(trend broke)")
            elif symbol in sell:
                action, reason = "SELL", plan.get("sell_reason", "the model is out of the market")
            elif symbol in warned:
                action, reason = "HOLD", (
                    f"WARNING: closed below its {config.EMA_FAST}-day EMA once. Hold for now; "
                    "sell if the next close is also below it")
            else:
                action, reason = "HOLD", (f"above its {config.EMA_FAST}-day EMA and above the "
                                          "stop-loss")
            rows.append({
                "symbol": symbol, "action": action, "reason": reason,
                "quantity": int(row["quantity"]), "buy_price": round(paid, 2),
                "last_price": round(float(row["last_price"]), 2),
                "gain_%": (float("nan") if new
                           else round((row["last_price"] / paid - 1) * 100, 1)),
                "stop_loss": round(paid * (1 - stop), 2),
                "trend_line": round(float(trend_lines.get(symbol, float("nan"))), 2),
                "bought": bought, "days_held": days, "warning": symbol in warned,
            })
            line = rows[-1]["trend_line"]
            exit_line = max(rows[-1]["stop_loss"], line) if line == line else rows[-1]["stop_loss"]
            # Profit trail: active once the high since the buy is `trigger` above the buy price.
            peak = peaks.get(symbol)
            rows[-1]["peak"] = None if peak is None else round(peak, 2)
            rows[-1]["trail_from"] = round(paid * (1 + trail["trigger"]), 2) if trail else None
            rows[-1]["trail_active"] = bool(trail and peak and peak >= paid * (1 + trail["trigger"]))
            if rows[-1]["trail_active"] and trail.get("trail"):
                exit_line = max(exit_line, peak * (1 - trail["trail"]))
            rows[-1]["exit_line"] = round(exit_line, 2)
            rows[-1]["exit_pct"] = round((exit_line / paid - 1) * 100, 1)
            rows[-1]["exit_rs"] = round((exit_line - paid) * row["quantity"])
            # The GTT stop-loss is a safety net for a missed check. It stays at the hard stop
            # until the exit line passes the buy price; then moving it up to the buy price
            # stops a forgotten check from turning a profit into a loss.
            rows[-1]["gtt"] = round(paid if exit_line > paid else rows[-1]["stop_loss"], 2)
    return pd.DataFrame(rows, columns=["symbol", "action", "reason", "quantity", "buy_price",
                                       "last_price", "gain_%", "stop_loss", "trend_line",
                                       "bought", "days_held", "exit_line", "exit_pct",
                                       "exit_rs", "gtt", "peak", "trail_from",
                                       "trail_active", "warning"])


def avoid_list(plan):
    """The weakest scores today: do not buy them, and exit if you hold one."""
    weakest = plan["weakest"]
    return pd.DataFrame({
        "symbol": weakest.index,
        "score": weakest["score"].round(0).to_numpy(),
        "price": weakest["close"].round(2).to_numpy(),
    })


# Yahoo has the day's closing prices a little after the market closes at 3:30 pm.
CLOSE_READY_HOUR = 16


def latest_close_expected(now):
    """The trading day whose close should be downloadable at `now` (Indian time).

    Weekends and NSE holidays (trading/holidays.py) are skipped.
    """
    day = pd.Timestamp(now.date())
    if now.hour >= CLOSE_READY_HOUR and holidays.is_trading_day(day):
        return day.normalize()
    return holidays.previous_trading_day(day)


def data_status(last_price_day, now):
    """("fresh" or "old", one plain sentence) about the saved prices."""
    last = pd.Timestamp(last_price_day).normalize()
    expected = latest_close_expected(now)
    shown = f"{last:%a %d %b}"
    if last >= expected:
        if now.weekday() < 5 and now.hour < CLOSE_READY_HOUR and pd.Timestamp(now.date()) > last:
            return "fresh", (f"Up to date: prices to {shown} close. Today's close can be "
                             f"downloaded after {CLOSE_READY_HOUR - 12} pm.")
        return "fresh", f"Up to date: prices to {shown} close."
    return "old", (f"Out of date: prices only to {shown} close, but {expected:%a %d %b} "
                   "is available. Press 'Update data now'. (If that day was a market "
                   "holiday, ignore this.)")


# ------------------------------------------------------------- events ------
# Stocks with results due, results just out, or fresh company news. These are
# ideas to look at, not model signals: trading on news has not been backtested.

def model_view(score, in_trend):
    """The model's opinion of a stock in a few words."""
    if score is None or pd.isna(score):
        return "not scored"
    if score >= 60 and in_trend:
        return "strong: model likes it"
    if score <= 40:
        return "weak: model would avoid"
    if not in_trend:
        return "below its trend line"
    return "neutral"


def _context(ranking, in_trend, symbol):
    """Rank, score, price and model view for one stock."""
    if symbol not in ranking.index:
        return {"rank": None, "score": None, "price": None, "view": "not scored"}
    row = ranking.loc[symbol]
    score = float(row["score"])
    trend = bool(in_trend.get(symbol, False))
    return {"rank": int(ranking.index.get_loc(symbol)) + 1, "score": round(score),
            "price": round(float(row["close"]), 2), "view": model_view(score, trend)}


def _move_since(closes, symbol, moment):
    """Price change from the last close before `moment` to the latest close, in %."""
    if symbol not in closes:
        return None
    series = closes[symbol].dropna()
    cutoff = pd.Timestamp(moment)
    # News after the close only moves the price from the next day.
    base_day = cutoff.normalize() if cutoff.hour >= CLOSE_READY_HOUR else \
        cutoff.normalize() - pd.Timedelta(days=1)
    before = series[series.index <= base_day]
    if len(before) == 0 or before.index[-1] == series.index[-1]:
        return None
    return round((series.iloc[-1] / before.iloc[-1] - 1) * 100, 1)


def upcoming_results(results, ranking, in_trend, held, from_day, days=7):
    """Scored stocks whose results fall in the next `days` days."""
    columns = ["symbol", "results_on", "rank", "score", "price", "view", "you_hold"]
    if results is None or len(results) == 0:
        return pd.DataFrame(columns=columns)
    soon = results[(results["date"] >= from_day)
                   & (results["date"] <= from_day + pd.Timedelta(days=days))
                   & results["symbol"].isin(ranking.index)]
    soon = soon.groupby("symbol")["date"].min()
    rows = [{"symbol": symbol, "results_on": date, **_context(ranking, in_trend, symbol),
             "you_hold": "yes" if symbol in held else ""} for symbol, date in soon.items()]
    return pd.DataFrame(rows, columns=columns).sort_values(["results_on", "rank"]).reset_index(drop=True)


def recent_results(results, ranking, in_trend, closes, last_day, days=5):
    """Scored stocks whose results came out in the last `days` days, with the price move since."""
    columns = ["symbol", "results_on", "move_since_%", "rank", "score", "price", "view"]
    if results is None or len(results) == 0:
        return pd.DataFrame(columns=columns)
    done = results[(results["date"] <= last_day)
                   & (results["date"] > last_day - pd.Timedelta(days=days))
                   & results["symbol"].isin(ranking.index)]
    done = done.groupby("symbol")["date"].max()
    rows = [{"symbol": symbol, "results_on": date,
             "move_since_%": _move_since(closes, symbol, date),
             **_context(ranking, in_trend, symbol)} for symbol, date in done.items()]
    return pd.DataFrame(rows, columns=columns).sort_values("results_on", ascending=False) \
        .reset_index(drop=True)


# Only kinds of news that can move a price. "Business update" is mostly press
# releases, presentations and awards, so it is left out with routine filings.
EVENT_NEWS = {"Orders and contracts", "Deals", "Credit rating", "Legal and regulatory",
              "Management change", "Raising money", "Dividend and bonus"}


def recent_news(news_table, ranking, in_trend, closes, last_day, days=3):
    """Important announcements in the last `days` days for scored stocks."""
    columns = ["time", "symbol", "type", "what", "move_since_%", "rank", "score", "view", "price",
               "link"]
    if news_table is None or len(news_table) == 0:
        return pd.DataFrame(columns=columns)
    since = pd.Timestamp(last_day) - pd.Timedelta(days=days)
    fresh = news_table[(news_table["time"] > since)
                       & news_table["category"].isin(EVENT_NEWS)
                       & news_table["symbol"].isin(ranking.index)]
    rows = [{"time": row.time, "symbol": row.symbol, "type": row.category,
             "what": row.detail or row.subject,
             "move_since_%": _move_since(closes, row.symbol, row.time),
             **{k: v for k, v in _context(ranking, in_trend, row.symbol).items()
                if k in ("rank", "score", "view", "price")},
             "link": row.link} for row in fresh.itertuples()]
    return pd.DataFrame(rows, columns=columns).sort_values("time", ascending=False) \
        .reset_index(drop=True)


_FILLER = re.compile(r"^.*?\bhas informed the Exchange (?:about|regarding|that)\s*", re.IGNORECASE)


def short_news(text, limit=110):
    """The useful part of an NSE filing title, without the 'X has informed the Exchange' filler."""
    text = _FILLER.sub("", str(text or "")).strip(" .")
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


VIEW_ORDER = {"strong: model likes it": 0, "neutral": 1, "below its trend line": 2,
              "weak: model would avoid": 3, "not scored": 4}


def event_cards(upcoming, recent, fresh_news, held, worth_rank=30):
    """One entry per stock with all its events, best to look at first.

    upcoming, recent, fresh_news: the tables from upcoming_results, recent_results
    and recent_news. Each entry: symbol, rank, score, price, view, held, worth
    (held, or ranked inside worth_rank, or the model likes it) and events, a list
    of {"kind", "when", "text", "move", "link"}.
    """
    cards = {}

    def card(symbol, row):
        if symbol not in cards:
            cards[symbol] = {"symbol": symbol, "rank": row.get("rank"), "score": row.get("score"),
                             "price": row.get("price"), "view": row.get("view", "not scored"),
                             "held": symbol in held, "events": []}
        return cards[symbol]

    for row in upcoming.to_dict("records"):
        card(row["symbol"], row)["events"].append({
            "kind": "Results due", "when": row["results_on"], "text": "", "move": None,
            "link": None})
    for row in recent.to_dict("records"):
        card(row["symbol"], row)["events"].append({
            "kind": "Results out", "when": row["results_on"], "text": "",
            "move": row["move_since_%"], "link": None})
    for row in fresh_news.to_dict("records"):
        card(row["symbol"], row)["events"].append({
            "kind": row["type"], "when": row["time"], "text": short_news(row["what"]),
            "move": row["move_since_%"], "link": row["link"]})

    entries = []
    for entry in cards.values():
        rank = entry["rank"]
        ranked_well = rank is not None and not pd.isna(rank) and rank <= worth_rank
        entry["worth"] = entry["held"] or ranked_well or entry["view"].startswith("strong")
        seen, events = set(), []
        for event in entry["events"]:                    # drop repeated identical filings
            key = (event["kind"], event["text"])
            if key not in seen:
                seen.add(key)
                events.append(event)
        entry["events"] = events
        entries.append(entry)
    entries.sort(key=lambda e: (not e["held"], VIEW_ORDER.get(e["view"], 9),
                                e["rank"] if e["rank"] is not None and not pd.isna(e["rank"])
                                else 10 ** 6))
    return entries
