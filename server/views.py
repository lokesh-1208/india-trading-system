"""What each page of the web app shows, as plain data (JSON).

Every function here reads from the shared store and returns dictionaries and
lists of numbers and text. The decisions themselves come from the trading
package; nothing is decided here.
"""

import math

import numpy as np
import pandas as pd

import config
from trading import (company, data, journal, model, movers, news, newsview, picks, premarket,
                     today, update)

from server.store import STORE


# ------------------------------------------------------------- helpers ------
def clean(value):
    """Make a value JSON-friendly: NaN -> None, numpy -> Python, dates -> text."""
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        value = pd.Timestamp(value)
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NaT:
        return None
    return value


def records(table, columns=None):
    if table is None or len(table) == 0:
        return []
    table = table if columns is None else table[columns]
    return [clean(row) for row in table.to_dict("records")]


def india_now():
    return pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)


def _day_change(table):
    if table is None or len(table) < 2:
        return None, None
    last, before = table["Close"].iloc[-1], table["Close"].iloc[-2]
    return float(last), float((last / before - 1) * 100)


def market_strip():
    """The few index levels shown in the top bar."""
    items = []
    for label, name in [("Nifty 50", config.BENCHMARK), ("India VIX", "INDIAVIX"),
                        ("USD/INR", "USDINR"), ("Brent", "BRENT")]:
        value, change = _day_change(data.load_market(name))
        if value is not None:
            items.append({"name": label, "value": value, "change": change})
    return items


def status():
    nifty = STORE.nifty()
    now = india_now()
    last = nifty.index[-1]
    fresh, text = today.data_status(last, now)
    stamps = []
    for path in (config.PRICES_CACHE, config.MARKET_DIR / f"{config.BENCHMARK}.csv"):
        try:
            stamps.append(pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")
                          .tz_convert("Asia/Kolkata").tz_localize(None))
        except OSError:
            pass
    return clean({"prices_to": last, "fresh": fresh == "fresh", "text": text,
                  "updated": max(stamps) if stamps else None, "strip": market_strip(),
                  "now": now})


# --------------------------------------------------------------- today ------
def _plan():
    built = STORE.model()
    trades = journal.load()
    open_rows = journal.open_positions(trades)
    held = list(open_rows["symbol"].unique())
    paid = dict(open_rows.groupby("symbol")["buy_price"].mean()) if len(open_rows) else {}
    plan = built.decision(held, style=config.MODEL_STYLE, buy_prices=paid)
    return built, trades, held, plan


def _ladder(stop, signal, limit, last):
    low, high = stop * 0.98, limit * 1.02
    return {"stop": stop, "signal": signal, "limit": limit, "last": last,
            "low": low, "high": high}


def today_page(money=None):
    """The one page to act from: what to buy, what to hold or sell, what to skip."""
    style = config.MODEL_STYLE
    rules = config.MODEL_STYLES[style]
    built, trades, held, plan = _plan()
    prices = plan["last_price"]
    last_day = prices.name
    above = rules.get("max_gap") or 0.0
    now = india_now()
    due = today.results_soon(built.results, today.buy_day(now))

    money = float(config.CAPITAL if money is None else money)
    share = built.amount_share()
    per_stock = money / rules["positions"] * share

    # ---- the weekly list and its status today ----
    log = STORE.picks_log()
    list_day = log["list_day"].max()
    weekly = picks.weekly_list(log, list_day)
    places = max(0, rules["positions"] - len(held))
    status_table = picks.weekly_status(weekly, prices, built.trading["in_trend"].iloc[-1], due,
                                       set(held), places, above, budget=per_stock)
    buy_now = status_table[status_table["status"] == "Buy"].head(places)
    buy_symbols = set(buy_now["symbol"])
    ranking = plan["today"]

    def about(symbol, rank=None, score=None):
        parts = []
        if rank is not None:
            parts.append(f"Rank {int(rank)} · score {score:.0f}")
        industry = built.industry.get(symbol, "")
        if industry:
            parts.append(industry)
        pledged = STORE.pledges().get(symbol)
        if pledged is not None and pledged == pledged and pledged >= config.PLEDGE_RED_FLAG_PCT:
            parts.append(f"promoter pledge {pledged:.0f}%")
        return " · ".join(parts)

    buys, skips = [], []
    for row in status_table.itertuples():
        stop = row.close * (1 - rules["stop_loss"])
        item = {"symbol": row.symbol, "rank": row.rank, "score": row.score,
                "about": about(row.symbol, row.rank, row.score),
                "ladder": _ladder(stop, row.close, row.limit, row.last),
                "shares": int(per_stock // row.limit) if row.limit > 0 else 0,
                "kind": row.kind, "status": row.status}
        item["amount"] = item["shares"] * row.limit
        if row.symbol in buy_symbols:
            item["tag"] = "Buy" if row.kind == "Pick" else "Backup"
            buys.append(item)
        elif row.status == "Buy":
            item["tag"] = "Backup"
            buys.append(item)
        elif row.status != "You hold":
            item["why"] = {"Too costly": f"one share costs more than ₹{per_stock:,.0f}",
                           "Missed": f"last {row.last:,.2f} is above the limit {row.limit:,.2f}",
                           "Trend broke": f"closed below its {config.EMA_FAST}-day average",
                           "Results soon": "results due within 5 days"}.get(row.status, "")
            skips.append(item)

    # ---- your stocks ----
    trend = STORE.trend_line()
    positions = journal.open_positions(trades, prices, last_day)
    trend_lines = {symbol: float(trend[symbol].iloc[-1]) for symbol in held if symbol in trend}
    mine = today.my_stocks(plan, positions, trend_lines, last_day=last_day)
    holds = []
    for row in mine.to_dict("records"):
        row["gain_rs"] = None if row["gain_%"] != row["gain_%"] else \
            (row["last_price"] - row["buy_price"]) * row["quantity"]
        holds.append(row)
    sells = [row for row in holds if row["action"] == "SELL"]

    # ---- the headline ----
    to_buy = len([item for item in buys if item["tag"] == "Buy"]) if plan["market_ok"] else 0
    holding = len([row for row in holds if row["action"] != "SELL"])
    parts = []
    if to_buy:
        parts.append(f"Buy {to_buy}")
    if sells:
        parts.append(f"sell {len(sells)}")
    if holding:
        parts.append(f"hold {holding}")
    headline = ", ".join(parts).capitalize() if parts else "Nothing to do today"
    if not plan["market_ok"]:
        headline = "Market weak: no new buys" + (f", sell {len(sells)}" if sells else "")

    # ---- watch: today's list but not this week's ----
    todays = log[log["list_day"] == list_day]
    watch = todays[~todays["symbol"].isin(set(weekly["symbol"]) | set(held))]
    weekly_day = len(weekly) and weekly["list_day"].iloc[0] == list_day

    known = plan["checks"].dropna()
    week_rows, week_days = picks.tracker(log, list_day, built.prepared["last_close"],
                                         STORE.nifty()["Close"])
    return clean({
        "list_day": list_day, "signal_day": last_day, "week_of": weekly["list_day"].iloc[0]
        if len(weekly) else list_day,
        "headline": headline, "nothing_to_sell": not sells,
        "market": {"level": plan["market_level"], "note": plan["market_note"],
                   "ok": bool(plan["market_ok"]), "share": share, "per_stock": per_stock,
                   "money": money, "positions": rules["positions"],
                   "checks_pass": int(known.sum()), "checks_total": int(len(known)),
                   "stop_loss": rules["stop_loss"], "max_gap": above},
        "buys": buys if plan["market_ok"] else [],
        "holds": holds,
        "skips": skips,
        "watch": [] if weekly_day else records(watch, ["symbol", "rank", "score", "close"]),
        "avoid": records(today.avoid_list(plan)),
        "tracker": {"days": week_days, "rows": records(week_rows) if len(week_rows) else []},
        "results_due": [{"symbol": symbol, "date": date} for symbol, date in sorted(due.items())
                        if symbol in set(ranking.index[:20])],
    })


# ------------------------------------------------------------ before open --
def before_open():
    now = india_now()
    nifty = STORE.nifty()
    since = premarket.last_close_time(nifty.index, now)
    moves = premarket.global_moves(premarket.load_markets(), since)
    guess, reasons = premarket.opening_guess(moves)
    reading, reactions = STORE.news_reading()
    overnight = STORE.overnight(since)
    if len(overnight):
        overnight = overnight.assign(lean=[newsview.learned_lean(group, lean, reactions)
                                           for group, lean in zip(overnight["group"],
                                                                  overnight["lean"])])
    symbols = list(data.load_universe()["Symbol"])
    preopen = premarket.load_preopen(now)
    up = premarket.preopen_movers(preopen, symbols, "up")
    down = premarket.preopen_movers(preopen, symbols, "down")
    built = STORE.model()
    sectors = premarket.sector_effects(moves, built.industry)
    likely = premarket.stock_list(overnight, sectors, up, down)
    likely = likely[likely["symbol"].isin(set(symbols))]
    _, _, held, _ = _plan()
    log = STORE.picks_log()
    weekly = set(picks.weekly_list(log, log["list_day"].max())["symbol"])
    ranking, in_trend = STORE.ranking(), STORE.in_trend()

    def view(symbol):
        if symbol not in ranking.index:
            return {"view": "not scored", "rank": None}
        return {"view": today.model_view(float(ranking.loc[symbol, "score"]),
                                         bool(in_trend.get(symbol, False))),
                "rank": int(ranking.index.get_loc(symbol)) + 1}

    rows = []
    for row in likely.itertuples():
        rows.append({"symbol": row.symbol, "direction": int(row.direction),
                     "strength": float(row.strength), "reasons": list(row.reasons),
                     "open_pct": row._5, "link": row.link,
                     "industry": built.industry.get(row.symbol, ""),
                     "yours": "held" if row.symbol in held else
                     "weekly" if row.symbol in weekly else None, **view(row.symbol)})
    return clean({
        "since": since, "guess": guess, "reasons": reasons,
        "moves": records(moves),
        "sectors": premarket.sector_summary(sectors),
        "preopen_ready": preopen is not None,
        "up": [row for row in rows if row["direction"] > 0],
        "down": [row for row in rows if row["direction"] < 0],
        "note": "For context: it helps you understand the open. The buy and sell calls "
                "come from the model.",
    })


# ------------------------------------------------------------------ news ----
def news_page():
    reading, reactions = STORE.news_reading()
    ranking, in_trend = STORE.ranking(), STORE.in_trend()
    _, _, held, _ = _plan()
    log = STORE.picks_log()
    weekly = set(picks.weekly_list(log, log["list_day"].max())["symbol"])
    buys, exits = newsview.ideas(reading, ranking, in_trend, STORE.model().prepared["last_close"],
                                 STORE.trend_line().iloc[-1], held=held, weekly=weekly,
                                 reactions=reactions)
    for table in (buys, exits):
        if len(table):
            table["what"] = [today.short_news(text, 180) for text in table["what"]]
    return clean({"buys": records(buys), "exits": records(exits),
                  "reactions": records(reactions), "days": config.NEWS_REACTION_DAYS,
                  "note": newsview.IDEA_TEST_NOTE})


def movers_page():
    stocks = STORE.stocks()
    symbols = [symbol for symbol in data.load_universe()["Symbol"] if symbol in stocks]
    moves = movers.day_moves(stocks, symbols)
    nifty = STORE.nifty()
    if len(moves) == 0:
        return {"day": None, "up": [], "down": [], "mood": None}
    day = moves["day"].max()
    moves = moves[moves["day"] == day]
    calendar = nifty.index[nifty.index < day]
    previous = calendar[-1] if len(calendar) else day - pd.Timedelta(days=1)
    from trading import fundamentals
    industry = STORE.model().industry
    sides = {side: movers.explain(movers.heavy(moves, side), previous, STORE.news(),
                                  STORE.deals(), fundamentals.load_results_dates(),
                                  industry=industry)
             for side in ("up", "down")}
    reading = movers.mood(moves, data.load_market("INDIAVIX"), nifty)
    for table in sides.values():
        table["industry"] = [industry.get(symbol, "") for symbol in table["symbol"]]
    return clean({"day": day, "mood": reading, "up": records(sides["up"]),
                  "down": records(sides["down"]),
                  "rule": {"move": config.MOVERS_MIN_MOVE_PCT,
                           "volume": config.MOVERS_MIN_VOLUME_X}})


# ---------------------------------------------------------------- market ----
def market_page():
    built = STORE.model()
    plan_checks = built.checks.iloc[-1]
    level, note = built.market_level()
    markets = []
    for name in ["NIFTY50", "INDIAVIX", "SP500", "NASDAQ", "FTSE100", "NIKKEI225", "HANGSENG",
                 "SHANGHAI", "USDINR", "BRENT", "GOLD", "SP500_FUTURES"]:
        value, change = _day_change(data.load_market(name))
        if value is not None:
            markets.append({"name": premarket.OVERNIGHT.get(name, "Nifty 50"),
                            "value": value, "change": change})
    flow_table = STORE.flows()
    from trading import flows as flow_module
    net = flow_module.daily_net(flow_table) if len(flow_table) else pd.DataFrame()
    fii = records(net.reset_index().tail(15)) if len(net) else []
    result, summary, by_year = STORE.history()
    equity = result["equity"]
    nifty = STORE.nifty()["Close"].reindex(equity.index).ffill()
    step = max(1, len(equity) // 300)
    return clean({
        "level": level, "note": note,
        "checks": [{"name": name, "passed": None if pd.isna(passed) else bool(passed)}
                   for name, passed in plan_checks.items()],
        "markets": markets, "fii_dii": fii,
        "history": {"summary": summary,
                    "by_year": [{"year": int(year), "model": row["strategy"],
                                 "nifty": row["nifty"]} for year, row in by_year.iterrows()],
                    "equity": [{"time": day.strftime("%Y-%m-%d"), "model": value,
                                "nifty": float(nifty.loc[day] / nifty.iloc[0] * equity.iloc[0])}
                               for day, value in list(equity.items())[::step]]},
    })


# ----------------------------------------------------------------- stocks ---
def stock_list():
    universe = data.load_universe()
    stocks = STORE.stocks()
    current = set(universe["Symbol"])
    return [{"symbol": symbol, "industry": industry} for symbol, industry
            in zip(universe["Symbol"], universe["Industry"]) if symbol in stocks] + \
        [{"symbol": symbol, "industry": ""} for symbol in sorted(stocks) if symbol not in current]


def stock_prices(symbol, days=None):
    stocks = STORE.stocks()
    if symbol not in stocks:
        return None
    table = stocks[symbol]
    ema = table["Close"].ewm(span=config.EMA_FAST, adjust=False).mean()
    if days:
        table, ema = table.tail(days), ema.tail(days)
    return {"symbol": symbol,
            "bars": [{"time": day.strftime("%Y-%m-%d"), "open": round(float(o), 2),
                      "high": round(float(h), 2), "low": round(float(lo), 2),
                      "close": round(float(c), 2), "volume": float(v) if v == v else 0.0}
                     for day, o, h, lo, c, v in zip(table.index, table["Open"], table["High"],
                                                    table["Low"], table["Close"],
                                                    table["Volume"])],
            "ema": [{"time": day.strftime("%Y-%m-%d"), "value": round(float(value), 2)}
                    for day, value in ema.items()]}


def stock_page(symbol):
    stocks = STORE.stocks()
    if symbol not in stocks:
        return None
    prices = stocks[symbol]
    found = STORE.screens()
    card = found.card(symbol, prices)
    financial = found.is_financial(symbol)
    built = STORE.model()
    ranking = STORE.ranking()
    in_trend = bool(STORE.in_trend().get(symbol, False))
    rank = int(ranking.index.get_loc(symbol)) + 1 if symbol in ranking.index else None
    rules = config.MODEL_STYLES[config.MODEL_STYLE]
    next_results = found.next_results(symbol, prices.index[-1])

    # where the stock stands for you
    stands, levels = [], {}
    open_rows = journal.open_positions(journal.load())
    trend_now = float(STORE.trend_line()[symbol].iloc[-1]) \
        if symbol in STORE.trend_line() else float(
            prices["Close"].ewm(span=config.EMA_FAST, adjust=False).mean().iloc[-1])
    if symbol in set(open_rows["symbol"]):
        mine = open_rows[open_rows["symbol"] == symbol]
        quantity = int(mine["quantity"].sum())
        paid = float((mine["buy_price"] * mine["quantity"]).sum() / quantity)
        stop = paid * (1 - rules["stop_loss"])
        stands.append({"kind": "held", "text": f"You hold {quantity} shares at ₹{paid:,.2f}. "
                       f"Sell on a close below ₹{max(stop, trend_now):,.2f}"})
        levels.update(bought=paid, stop=stop)
    log = STORE.picks_log()
    list_day = log["list_day"].max() if len(log) else None
    weekly = picks.weekly_list(log, list_day) if list_day is not None else log
    if symbol in set(weekly["symbol"]):
        on = weekly.set_index("symbol").loc[symbol]
        limit = float(on["close"]) * (1 + (rules.get("max_gap") or 0))
        stands.append({"kind": "weekly", "text": f"On this week's list · buy below ₹{limit:,.2f}"})
        levels.update(limit=limit)
        levels.setdefault("stop", float(on["close"]) * (1 - rules["stop_loss"]))
    elif list_day is not None and symbol in set(log.loc[log["list_day"] == list_day, "symbol"]):
        stands.append({"kind": "today", "text": "On today's list (watch only)"})
    if symbol in set(ranking.tail(config.MODEL_WEAKEST).index):
        stands.append({"kind": "avoid", "text": "On the avoid list: one of the weakest scores"})

    model_view = None
    if rank:
        row = ranking.loc[symbol]
        soon = next_results is not None and next_results <= (
            today.buy_day(india_now()) + pd.Timedelta(days=config.RESULTS_BLOCK_DAYS))
        model_view = {
            "score": float(row["score"]), "rank": rank, "of": len(ranking),
            "view": today.model_view(float(row["score"]), in_trend),
            "groups": [{"name": group.capitalize(), "value": float(row[group])}
                       for group in model.GROUPS],
            "checks": [{"name": f"In the top {rules['buy_rank']} scores (rank {rank})",
                        "passed": rank <= rules["buy_rank"]},
                       {"name": f"Above its {config.EMA_FAST}-day average", "passed": in_trend},
                       {"name": "No results due in the next 5 days", "passed": not soon}]}

    last, before = float(prices["Close"].iloc[-1]), float(prices["Close"].iloc[-2])
    checks = company.scorecard(card, financial)
    pledged = STORE.pledges().get(symbol)
    announcements = STORE.news()
    recent_news = news.for_symbol(announcements, symbol, days=90, important_only=True) \
        if len(announcements) else announcements
    deals = STORE.deals()
    stock_deals = deals[deals["symbol"] == symbol].sort_values("date", ascending=False).head(10)
    calls = announcements[(announcements["symbol"] == symbol)
                          & announcements["subject"].str.contains(
                              r"Analysts|Investor Meet|Con\. Call|Earnings Call|Transcript",
                              case=False, regex=True)
                          & announcements["detail"].str.contains("transcript|recording|audio",
                                                                 case=False, regex=True)].head(6)
    industry_name = built.industry.get(symbol, "")
    peers = [s for s in ranking.index if built.industry.get(s, "") == industry_name] \
        if industry_name else []
    owners = card.get("owners") or {}
    return clean({
        "symbol": symbol, "industry": card["industry"], "price": last,
        "change": last - before, "change_pct": (last / before - 1) * 100,
        "as_of": prices.index[-1], "stands": stands, "levels": levels,
        "trend_line": trend_now, "model": model_view, "next_results": next_results,
        "card": {key: card.get(key) for key in [
            "market_cap_crore", "pe", "industry_pe", "return_on_equity", "roce",
            "cash_conversion", "debt_to_equity", "sales_growth_1y", "profit_growth_1y",
            "sales_growth_3y", "profit_growth_3y", "net_margin", "dividend_yield",
            "below_52w_high", "high_52w", "low_52w", "quarter", "quarter_sales_growth",
            "quarter_profit_growth", "results_filed", "financial_year", "revenue_crore",
            "profit_crore", "cash_from_operations_crore"]},
        "financial": financial,
        "scorecard": {"passed": company.score(card, financial), "total": len(checks),
                      "checks": [{"name": name, "passed": passed} for name, passed in checks]},
        "pledged_pct": pledged, "pledge_red_flag": config.PLEDGE_RED_FLAG_PCT,
        "owners": None if not owners else {
            "quarter": owners.get("quarter_end"),
            "groups": [{"name": name, "value": owners.get(key), "change": owners.get(key + "_change")}
                       for key, name in [("promoter", "Promoters"), ("fii", "Foreign institutions"),
                                         ("mutual_funds", "Mutual funds"), ("dii", "Indian institutions"),
                                         ("insurance", "Insurers"), ("public", "Public")]],
            "funds": [{"name": name, "percent": percent} for name, percent in owners.get("funds", [])[:8]],
            "pledged": owners.get("promoters_pledged")},
        "news": [{"time": row.time, "type": row.category,
                  "what": today.short_news(row.detail or row.subject, 200), "link": row.link}
                 for row in recent_news.head(15).itertuples()],
        "deals": records(stock_deals),
        "calls": [{"time": row.time, "what": today.short_news(row.detail, 160), "link": row.link}
                  for row in calls.itertuples()],
        "peers": [{"symbol": s, "rank": int(ranking.index.get_loc(s)) + 1,
                   "score": float(ranking.loc[s, "score"]), "price": float(ranking.loc[s, "close"])}
                  for s in peers[:8]],
    })


def documents(symbol):
    """Annual reports from NSE (asked live; the browser caches them)."""
    try:
        from trading import nse
        raw = nse.get_json(nse.session(), "/api/annual-reports", index="equities", symbol=symbol)
        items = raw.get("data", []) if isinstance(raw, dict) else raw or []
        return [{"year": f"{item.get('fromYr')}–{item.get('toYr')}", "link": item.get("fileName"),
                 "size": item.get("attFileSize") or ""}
                for item in items[:5] if item.get("fileName")]
    except Exception:
        return []


# ----------------------------------------------------------------- trades ---
def trades_page():
    trades = journal.load()
    prices = STORE.model().prepared["last_close"].iloc[-1]
    last_day = STORE.nifty().index[-1]
    totals = journal.totals(trades, prices, last_day)
    positions = journal.open_positions(trades, prices, last_day)
    positions = positions.assign(row=positions.index)
    closed = journal.closed_trades(trades)
    return clean({"totals": totals, "open": records(positions), "closed": records(closed),
                  "symbols": sorted(STORE.stocks())})


def record_buy(symbol, day, price, quantity, note=""):
    if symbol not in STORE.stocks():
        raise ValueError(f"{symbol} is not a stock the system knows.")
    trades = journal.record_buy(journal.load(), symbol, day, price, quantity, note)
    journal.save(trades)
    return trades_page()


def record_sell(row, day, price):
    trades = journal.load()
    if row not in trades.index:
        raise ValueError("That position was not found.")
    journal.save(journal.record_sell(trades, row, day, price))
    return trades_page()


def update_note(summary):
    return update.describe_prices(summary["prices"]) if summary.get("prices") else ""
