"""Rule set D: the ownership rotation.

The idea: big investors (foreign funds and mutual funds) research companies
closely. When both raised their holding last quarter, and the share price has
also been strong, the stock has tended to keep doing well for some months.

How it works:
  1. Every quarter, 30 days after the quarter ends (when the shareholding
     filings are public), every liquid Nifty 500 stock gets a score from three
     things, each turned into a rank from 0 to 1:
        - the change in foreign institutions' holding over the quarter
        - the change in mutual funds' holding over the quarter
        - the price change over the last 6 months
     The score is the average of the three ranks.
  2. On the first trading day of each month the portfolio is checked:
        - if Nifty closed below its 200-day average, everything is sold
        - otherwise holdings that fell out of the top 20 are sold, and the
          best-scoring stocks are bought until 10 are held, in equal amounts
  3. Zerodha delivery charges and slippage are paid on every trade.

Nothing here uses information from the future: a quarter's filings count only
if they were filed by the scoring day, and prices only up to that day.
"""

import math

import numpy as np
import pandas as pd

import config
from trading import charges

FORMAT_CHANGE = pd.Timestamp("2022-09-30")   # NSE changed how foreign holdings are reported


# ------------------------------------------------------------------ scoring -
def scoring_days(first_day, last_day):
    """The days on which scores are refreshed: 30 days after each quarter end."""
    wait = pd.Timedelta(days=config.ROTATION_FILING_DAYS)
    quarter_ends = pd.date_range(first_day - pd.Timedelta(days=130), last_day, freq="QE")
    return [day + wait for day in quarter_ends if first_day <= day + wait <= last_day]


def ownership_changes(holdings, scoring_day):
    """Change in FII and mutual fund holding over the latest quarter, per company.

    Only filings made on or before the scoring day are used.
    Returns a table indexed by symbol with columns fii_change and mf_change.
    """
    quarter = scoring_day - pd.Timedelta(days=config.ROTATION_FILING_DAYS)
    previous = quarter - pd.offsets.QuarterEnd(1)
    filed = holdings[holdings["filed_on"] <= scoring_day]
    now = filed[filed["quarter_end"] == quarter].drop_duplicates("symbol").set_index("symbol")
    before = filed[filed["quarter_end"] == previous].drop_duplicates("symbol").set_index("symbol")
    both = now.index.intersection(before.index)

    changes = pd.DataFrame({
        "fii_change": now.loc[both, "fii"] - before.loc[both, "fii"],
        "mf_change": now.loc[both, "mutual_funds"] - before.loc[both, "mutual_funds"],
    })
    if quarter == FORMAT_CHANGE:
        changes["fii_change"] = np.nan    # the two quarters are not comparable
    return changes


def score_table(changes, momentum):
    """Combine ownership changes and price strength into one score per stock.

    changes : table from ownership_changes
    momentum: 6-month price change per symbol (only for stocks that may be bought)
    Returns a table sorted best first, with a `score` between 0 and 1.
    """
    table = changes.join(momentum.rename("momentum"), how="inner").dropna(subset=["momentum"])
    if len(table) == 0:
        return table.assign(score=pd.Series(dtype=float))
    ranks = pd.DataFrame({
        "fii": table["fii_change"].rank(pct=True),
        "mf": table["mf_change"].rank(pct=True),
        "momentum": table["momentum"].rank(pct=True),
    })
    table["score"] = ranks.mean(axis=1)
    return table.sort_values("score", ascending=False)


# --------------------------------------------------------------- simulation -
def _wide(stocks, column, calendar):
    return pd.DataFrame(
        {symbol: table[column] for symbol, table in stocks.items()}
    ).reindex(calendar)


def prepare(stocks, nifty, membership_mask):
    """Tables used by the simulation: prices, liquidity and the market rule.

    membership_mask(symbol, dates) -> True/False per day (was it in the index).
    """
    calendar = nifty.index
    close = _wide(stocks, "Close", calendar)
    volume = _wide(stocks, "Volume", calendar)
    turnover = (close * volume).rolling(config.VOLUME_AVG_DAYS).mean() / 1e7
    member = pd.DataFrame({symbol: membership_mask(symbol, calendar) for symbol in stocks})
    average = nifty["Close"].rolling(config.ROTATION_MARKET_SMA).mean()
    return {
        "calendar": calendar,
        "symbols": list(stocks),
        "open": _wide(stocks, "Open", calendar),
        "low": _wide(stocks, "Low", calendar),
        "close": close,
        "last_close": close.ffill(),
        "liquid": (turnover >= config.MIN_TURNOVER_CRORE) & member,
        "momentum": close / close.shift(config.ROTATION_MOMENTUM_DAYS) - 1,
        "market_ok": (nifty["Close"] > average).fillna(False),
    }


def scores_on(prepared, holdings, scoring_day):
    """The score table for one scoring day (uses prices up to that day only)."""
    calendar = prepared["calendar"]
    position = int(calendar.searchsorted(scoring_day, side="right")) - 1
    if position < 0:
        return score_table(pd.DataFrame(columns=["fii_change", "mf_change"]),
                           pd.Series(dtype=float))
    liquid = prepared["liquid"].iloc[position]
    momentum = prepared["momentum"].iloc[position][liquid]
    table = score_table(ownership_changes(holdings, scoring_day), momentum)
    table["close"] = prepared["close"].iloc[position].reindex(table.index)
    return table


def _new_period(calendar, day, check):
    """Is this the first trading day of a new month (or week)?"""
    today, before = calendar[day], calendar[day - 1]
    if check == "day":
        return True
    if check == "week":
        return today.isocalendar()[:2] != before.isocalendar()[:2]
    return today.month != before.month


def simulate(prepared, holdings, start=None, end=None, capital=None, scorer=None,
             check="month", positions_wanted=None, keep_rank=None, stop_loss=None,
             trend_exit=False, buy_rank=None, max_gap=None, limit_days=None,
             max_drop=None, min_room=None, max_spike=None, midweek_fill=False,
             budget_scale=None, exit_before=None):
    """Follow the rule day by day. Returns equity, trades, open positions and scores.

    scorer: optional. A function that takes a day's position in the calendar and
    returns that day's score table, best first. The full model (model.py) passes
    its own; without it the three-factor ownership score is used. A score table
    may have a True/False column `no_new_buy`; those stocks are not bought.

    check: "month" or "week": how often holdings are reviewed.
    positions_wanted, keep_rank: stocks held, and the rank a holding must stay
    inside. They default to the rotation's settings in config.py.
    stop_loss: for example 0.08. A holding that closes this far below its buy
    price is sold at the next open, on any day. None means no stop-loss.
    trend_exit: True to follow each stock's own trend. A holding is sold the day
    after it closes below its short trend line (prepared["in_trend"] is False),
    and only stocks above that line are bought. So a trade lasts as long as its
    trend does: a week for some, a month or more for others.
    buy_rank: new stocks are bought only from this many top ranks (default: keep_rank).

    How a new stock is bought (the signal is the close the decision was made on):
    max_gap: for example 0.02. Skip the buy when the stock opens more than this
    far above the signal close. None means buy at the open whatever it is.
    min_room: for example 0.03. Skip a stock whose signal close is less than this far
    above its trend line (needs prepared["room"]).
    max_spike: for example 0.10. Skip a stock that rose more than this over the last
    few days (needs prepared["spike"]).
    budget_scale: optional table (a row per day, a column per stock, like
    prepared["close"]) of numbers from 0 to 1 that shrink the money put into a new
    buy, read on the signal day. 1 means the normal equal share.
    exit_before: optional True/False table of the same shape. A holding is sold at
    the next open when it is True on the day before (for example results due soon).
    midweek_fill: True to fill places that are free between checks, but only from the
    list made at the last check, only while the stock is above its trend line, and
    only at or below the limit set from the check day's close (max_gap). No new
    picks between checks; a stock sold since the check is not bought again.
    max_drop: for example 0.03. Skip the buy when the stock opens more than this
    far below the signal close. None means no lower limit.
    limit_days: for example 2. Instead of buying at the open, place a limit order
    at the signal close, valid for this many days. It fills at the open if the
    stock opens at or below that price, at the limit price if the day's low goes
    below it, and is cancelled otherwise. A waiting order keeps its slot.
    Every trade records gap_% (open on the buy day against the signal close).
    """
    positions_wanted = config.ROTATION_POSITIONS if positions_wanted is None else positions_wanted
    keep_rank = config.ROTATION_KEEP_RANK if keep_rank is None else keep_rank
    buy_rank = keep_rank if buy_rank is None else buy_rank
    in_trend = prepared["in_trend"].to_numpy(dtype=bool) if trend_exit else None
    scale = (None if budget_scale is None else
             budget_scale.reindex(index=prepared["calendar"], columns=prepared["symbols"])
             .fillna(1.0).clip(0, 1).to_numpy(dtype=float))
    leave = (None if exit_before is None else
             exit_before.reindex(index=prepared["calendar"], columns=prepared["symbols"])
             .fillna(False).to_numpy(dtype=bool))
    room = prepared["room"].to_numpy(dtype=float) if min_room is not None else None
    spike = prepared["spike"].to_numpy(dtype=float) if max_spike is not None else None
    capital = float(config.CAPITAL if capital is None else capital)
    calendar = prepared["calendar"]
    start = pd.Timestamp(config.ROTATION_START if start is None else start)
    end = calendar[-1] if end is None else pd.Timestamp(end)
    first = int(calendar.searchsorted(start))
    last = int(calendar.searchsorted(end, side="right")) - 1
    if last - first < 1:
        raise ValueError("Not enough days in the chosen period.")

    symbols = prepared["symbols"]
    column = {symbol: number for number, symbol in enumerate(symbols)}
    opens = prepared["open"].to_numpy(dtype=float)
    lows = (prepared["low"].to_numpy(dtype=float) if "low" in prepared
            else np.full_like(opens, np.nan))
    last_close = prepared["last_close"].to_numpy(dtype=float)
    liquid = prepared["liquid"].to_numpy(dtype=bool)
    market_ok = prepared["market_ok"].reindex(calendar).to_numpy(dtype=bool)

    days = scoring_days(calendar[0], calendar[last])
    score_cache = {}
    used_day = [None]       # the scoring day behind the most recent scores

    def current_scores(day_position):
        """Scores from the latest scoring day on or before this day.

        If that quarter's filings have not been downloaded yet, the scores of
        the quarter before are used until they have.
        """
        if scorer is not None:
            if day_position not in score_cache:
                score_cache[day_position] = scorer(day_position)
            used_day[0] = calendar[day_position]
            return score_cache[day_position]
        usable = [day for day in days if day <= calendar[day_position]]
        for scoring_day in reversed(usable[-2:]):
            if scoring_day not in score_cache:
                score_cache[scoring_day] = scores_on(prepared, holdings, scoring_day)
            if len(score_cache[scoring_day]):
                used_day[0] = scoring_day
                return score_cache[scoring_day]
        return None

    cash = capital
    positions = {}      # symbol -> {"quantity", "entry", "entry_day", "buy_cost", "gap"}
    pending = {}        # symbol -> {"limit", "last_day"}: limit orders not filled yet
    skipped = {"gap": 0, "drop": 0, "limit_expired": 0, "room": 0, "spike": 0}
    week = {"list": [], "signal": {}, "sold": set()}   # the last check's picks, for midweek_fill
    trades = []
    equity = [cash]

    def buy(symbol, day, price, gap, account):
        """Buy one position at this price. Returns True when something was bought."""
        nonlocal cash
        share = 1.0 if scale is None else scale[day - 1, column[symbol]]
        budget = min(account / positions_wanted * share, cash / 1.002)
        quantity = math.floor(budget / price)
        if quantity < 1:
            return False
        cost = charges.buy_charges(quantity * price)
        cash -= quantity * price + cost
        positions[symbol] = {"quantity": quantity, "entry": price,
                             "entry_day": day, "buy_cost": cost, "gap": gap}
        return True

    def try_limit(symbol, day, limit):
        """Price a limit order fills at today, or None."""
        today_open, today_low = opens[day, column[symbol]], lows[day, column[symbol]]
        if np.isnan(today_open):
            return None
        if today_open <= limit:
            return today_open * (1 + config.SLIPPAGE)
        if not np.isnan(today_low) and today_low < limit:
            return limit        # a resting limit order fills at its own price
        return None

    def sell(symbol, day, reason):
        nonlocal cash
        holding = positions.pop(symbol)
        week["sold"].add(symbol)
        price = opens[day, column[symbol]] * (1 - config.SLIPPAGE)
        value = holding["quantity"] * price
        cost = charges.sell_charges(value)
        cash += value - cost
        trades.append({
            "symbol": symbol,
            "entry_date": calendar[holding["entry_day"]].date(),
            "entry_price": round(holding["entry"], 2),
            "quantity": holding["quantity"],
            "exit_date": calendar[day].date(),
            "exit_price": round(price, 2),
            "reason": reason,
            "gap_%": round(holding.get("gap", np.nan) * 100, 2),
            "charges": round(holding["buy_cost"] + cost, 2),
            "profit": round(value - cost - holding["quantity"] * holding["entry"]
                            - holding["buy_cost"], 2),
        })

    for day in range(first + 1, last + 1):
        yesterday = day - 1
        for symbol in list(positions):
            if np.isnan(opens[day, column[symbol]]):
                continue
            floor = None if stop_loss is None else positions[symbol]["entry"] * (1 - stop_loss)
            if floor is not None and last_close[yesterday, column[symbol]] <= floor:
                sell(symbol, day, "stop-loss")
            elif trend_exit and not in_trend[yesterday, column[symbol]]:
                sell(symbol, day, "trend broke")
            elif leave is not None and leave[yesterday, column[symbol]]:
                sell(symbol, day, "sold before results")

        # Limit orders from earlier days: fill, or cancel once they expire.
        for symbol in list(pending):
            order = pending[symbol]
            if not market_ok[yesterday]:
                del pending[symbol]
                continue
            price = try_limit(symbol, day, order["limit"])
            if price is not None:
                del pending[symbol]
                buy(symbol, day, price, order["gap"], equity[-1])
            elif day >= order["last_day"]:
                del pending[symbol]
                skipped["limit_expired"] += 1

        if _new_period(calendar, day, check):
            scores = current_scores(yesterday)
            tradable = lambda symbol: not np.isnan(opens[day, column[symbol]])

            if not market_ok[yesterday]:
                pending.clear()
                for symbol in [s for s in positions if tradable(s)]:
                    sell(symbol, day, prepared.get("cash_reason", "Nifty below its average"))
            elif scores is not None and len(scores):
                ranked = [s for s in scores.index if liquid[yesterday, column[s]]]
                rank = {symbol: place for place, symbol in enumerate(ranked)}
                for symbol in [s for s in positions if tradable(s)]:
                    if rank.get(symbol, 10 ** 9) >= keep_rank:
                        sell(symbol, day, "fell out of the top ranks")

                account = equity[-1]
                blocked = _blocked(scores)
                week["list"] = [s for s in ranked[:buy_rank] if s not in blocked]
                week["signal"] = {s: last_close[yesterday, column[s]] for s in week["list"]}
                week["sold"] = set()
                for symbol in ranked[:buy_rank]:
                    if symbol in blocked:
                        continue
                    if trend_exit and not in_trend[yesterday, column[symbol]]:
                        continue
                    if len(positions) + len(pending) >= positions_wanted:
                        break
                    if symbol in positions or symbol in pending or not tradable(symbol):
                        continue
                    if room is not None and not room[yesterday, column[symbol]] >= min_room:
                        skipped["room"] += 1
                        continue
                    if spike is not None and spike[yesterday, column[symbol]] > max_spike:
                        skipped["spike"] += 1
                        continue
                    signal_close = last_close[yesterday, column[symbol]]
                    gap = opens[day, column[symbol]] / signal_close - 1
                    if max_gap is not None and gap > max_gap:
                        skipped["gap"] += 1
                        continue
                    if max_drop is not None and gap < -max_drop:
                        skipped["drop"] += 1
                        continue
                    if limit_days:
                        price = try_limit(symbol, day, signal_close)
                        if price is None:
                            if limit_days > 1:
                                pending[symbol] = {"limit": signal_close, "gap": gap,
                                                   "last_day": day + limit_days - 1}
                            else:
                                skipped["limit_expired"] += 1
                            continue
                        buy(symbol, day, price, gap, account)
                        continue
                    buy(symbol, day, opens[day, column[symbol]] * (1 + config.SLIPPAGE),
                        gap, account)

        elif midweek_fill and market_ok[yesterday] and week["list"]:
            account = equity[-1]
            for symbol in week["list"]:
                if len(positions) + len(pending) >= positions_wanted:
                    break
                col = column[symbol]
                if symbol in positions or symbol in week["sold"] or np.isnan(opens[day, col]):
                    continue
                if trend_exit and not in_trend[yesterday, col]:
                    continue
                gap = opens[day, col] / week["signal"][symbol] - 1
                if max_gap is not None and gap > max_gap:
                    continue
                buy(symbol, day, opens[day, col] * (1 + config.SLIPPAGE), gap, account)

        held_value = sum(holding["quantity"] * last_close[day, column[symbol]]
                         for symbol, holding in positions.items())
        equity.append(cash + held_value)

    open_positions = pd.DataFrame([
        {"symbol": symbol,
         "bought_on": calendar[holding["entry_day"]].date(),
         "buy_price": round(holding["entry"], 2),
         "quantity": holding["quantity"],
         "last_price": round(float(last_close[last, column[symbol]]), 2),
         "value": round(holding["quantity"] * float(last_close[last, column[symbol]])),
         "gain_%": round((last_close[last, column[symbol]] / holding["entry"] - 1) * 100, 1)}
        for symbol, holding in positions.items()
    ], columns=["symbol", "bought_on", "buy_price", "quantity", "last_price", "value", "gain_%"])

    trade_columns = ["symbol", "entry_date", "entry_price", "quantity", "exit_date",
                     "exit_price", "reason", "gap_%", "charges", "profit"]
    return {
        "capital": capital,
        "equity": pd.Series(equity, index=calendar[first:last + 1], name="equity"),
        "trades": pd.DataFrame(trades, columns=trade_columns),
        "positions": open_positions,
        "cash": cash,
        "scores": current_scores(last),
        "scoring_day": used_day[0],
        "market_ok": bool(market_ok[last]),
        "skipped": skipped,
    }


def _blocked(scores):
    """Stocks the score table says not to buy now (for example, results are due)."""
    if scores is None or "no_new_buy" not in scores.columns:
        return set()
    return set(scores.index[scores["no_new_buy"].astype(bool)])


# ----------------------------------------------------------- what to do now -
def _latest_scores(prepared, holdings, day_position):
    """Scores from the newest scoring day on or before a day, with its date."""
    calendar = prepared["calendar"]
    usable = [day for day in scoring_days(calendar[0], calendar[day_position])]
    for scoring_day in reversed(usable[-2:]):
        table = scores_on(prepared, holdings, scoring_day)
        if len(table):
            return table, scoring_day
    return None, None


def decision(prepared, holdings, held_symbols, scorer=None, check="month",
             positions_wanted=None, keep_rank=None, buy_rank=None):
    """What the rule says to do, given the stocks you really hold.

    The rule acts once a month, at the open of the first trading day, using
    the close of the day before. So:
      - if the latest prices are from the last trading day of a month, this is
        the plan for the next session ("due next session");
      - otherwise it is the plan from the start of the current month, which
        tells you whether your holdings still match what the rule would hold.

    Returns a dictionary with: market_ok, sell, keep, buy, candidates, room,
    ranking (table), scoring_day, decided_on, due_next_session, last_price.
    """
    positions_wanted = config.ROTATION_POSITIONS if positions_wanted is None else positions_wanted
    keep_rank = config.ROTATION_KEEP_RANK if keep_rank is None else keep_rank
    calendar = prepared["calendar"]
    last = len(calendar) - 1
    next_weekday = calendar[last] + pd.offsets.BDay(1)
    if check == "day":
        due_next_session = True
    elif check == "week":
        due_next_session = next_weekday.isocalendar()[:2] != calendar[last].isocalendar()[:2]
    else:
        due_next_session = next_weekday.month != calendar[last].month

    if due_next_session:
        decided = last
    else:                                   # the last close of the previous month (or week)
        decided = last
        while decided > 0 and not _new_period(calendar, decided, check):
            decided -= 1
        decided = max(0, decided - 1)

    market_ok = bool(prepared["market_ok"].reindex(calendar).iloc[decided])
    if scorer is None:
        scores, scoring_day = _latest_scores(prepared, holdings, decided)
    else:
        scores, scoring_day = scorer(decided), calendar[decided]
    held = list(held_symbols)

    ranking = pd.DataFrame()
    ranked = []
    if scores is not None:
        liquid = prepared["liquid"].iloc[decided]
        ranked = [symbol for symbol in scores.index if bool(liquid.get(symbol, False))]
        ranking = scores.loc[ranked].head(keep_rank)

    candidates, room = [], 0
    if not market_ok:
        sell, keep, buy = held, [], []
    elif scores is None:
        sell, keep, buy = [], held, []
    else:
        place = {symbol: number for number, symbol in enumerate(ranked)}
        sell = [s for s in held if place.get(s, 10 ** 9) >= keep_rank]
        keep = [s for s in held if s not in sell]
        room = max(0, positions_wanted - len(keep))
        blocked = _blocked(scores)
        candidates = [s for s in ranked[:keep_rank if buy_rank is None else buy_rank]
                      if s not in keep and s not in blocked]
        buy = candidates[:room]

    return {
        "market_ok": market_ok,
        "sell": sell, "keep": keep, "buy": buy,
        # Every top-ranked stock not yet held, best first, and how many places are
        # free. If a share costs more than the money per stock, the next one is used.
        "candidates": candidates, "room": room,
        "ranking": ranking,
        "scoring_day": scoring_day,
        "decided_on": calendar[decided],
        "due_next_session": due_next_session,
        "check": check, "positions": positions_wanted, "keep_rank": keep_rank,
        "last_price": prepared["last_close"].iloc[last],
    }


# ------------------------------------------------------------------ results -
def summarise(result, nifty):
    """The numbers that matter, with Nifty buy-and-hold over the same days."""
    from trading import backtest     # shared maths: drawdown and growth rate

    equity, trades, capital = result["equity"], result["trades"], result["capital"]
    benchmark = nifty["Close"].reindex(equity.index).dropna()
    days = (equity.index[-1] - equity.index[0]).days
    wins = trades[trades["profit"] > 0]
    by_year = pd.DataFrame({
        "strategy": backtest.yearly_growth(equity, capital),
        "nifty": backtest.yearly_growth(benchmark, benchmark.iloc[0]),
    })
    return {
        "period_start": equity.index[0].date(),
        "period_end": equity.index[-1].date(),
        "final_value": float(equity.iloc[-1]),
        "total_return": float(equity.iloc[-1] / capital - 1),
        "annual_growth_rate": backtest.annual_growth_rate(capital, equity.iloc[-1], days),
        "max_drawdown": backtest.max_drawdown(equity),
        "benchmark_total_return": float(benchmark.iloc[-1] / benchmark.iloc[0] - 1),
        "benchmark_annual_growth_rate": backtest.annual_growth_rate(
            benchmark.iloc[0], benchmark.iloc[-1], days),
        "benchmark_max_drawdown": backtest.max_drawdown(benchmark),
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) if len(trades) else float("nan"),
        "total_charges": float(trades["charges"].sum()),
    }, by_year
