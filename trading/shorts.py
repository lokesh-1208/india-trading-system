"""The short side: selling first and buying back later.

The full model's weakest scores are the candidates. There are two ways to
act on them in India, and ordinary delivery shares are not one of them:

  - Intraday: sell shares in the morning and buy them back before the close
    (Zerodha's MIS order). Nothing is carried overnight.
  - Stock futures: sell one futures contract ("lot") and hold it for days.
    Only about 200 large stocks have futures, and one lot is usually worth
    several lakh rupees, so the margin is large and the loss is not capped.

This file knows which stocks have futures and their lot sizes, works out the
figures for both routes, and tests the multi-day route on past prices.
The intraday route cannot be tested: that needs minute-by-minute prices.
"""

import math

import numpy as np
import pandas as pd

import config
from trading import nse, rotation


# ------------------------------------------------------------ lot sizes -----
def parse_lots(text):
    """Read NSE's lot-size file. Returns {symbol: shares in one lot}."""
    lots = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells) < 3 or cells[1] in ("", "SYMBOL"):
            continue
        sizes = [cell for cell in cells[2:] if cell.isdigit()]
        if sizes:
            lots[cells[1]] = int(sizes[0])
    return lots


def update_lots():
    """Download the current lot sizes. Returns how many symbols were saved."""
    browser = nse.session()
    lots = parse_lots(browser.get(config.FO_LOTS_SOURCE, timeout=60).text)
    if len(lots) < 50:
        raise ValueError("the lot-size file does not look right")
    config.FO_LOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"symbol": list(lots), "lot": list(lots.values())}).to_csv(
        config.FO_LOTS_FILE, index=False)
    return len(lots)


def load_lots():
    """{symbol: lot size}, or an empty dictionary if not downloaded yet."""
    if not config.FO_LOTS_FILE.exists():
        return {}
    table = pd.read_csv(config.FO_LOTS_FILE)
    return dict(zip(table["symbol"], table["lot"].astype(int)))


# ------------------------------------------------------- today's figures ----
def candidates(built, lots, capital=None, count=None):
    """The weakest scores today, with the figures for each short route.

    Returns a table, weakest first. `falling` is True when the stock is below
    its 20-day EMA; the tested rule only shorts those.
    """
    capital = float(config.CAPITAL if capital is None else capital)
    count = config.SHORT_POOL if count is None else count
    last = len(built.calendar) - 1
    table = built.score_on(last)
    weakest = table.tail(count).iloc[::-1]
    in_trend = built.trading["in_trend"].iloc[last]

    rows = []
    for symbol, row in weakest.iterrows():
        price = float(row["close"])
        day_range = float(row["atr_pct"]) * price if pd.notna(row["atr_pct"]) else float("nan")
        stop_gap = config.INTRADAY_STOP_ATR * day_range
        risk = capital * config.RISK_PER_TRADE
        quantity = int(risk // stop_gap) if stop_gap > 0 else 0
        lot = lots.get(symbol)
        rows.append({
            "symbol": symbol,
            "score": row["score"],
            "price": price,
            "falling": not bool(in_trend.get(symbol, False)),
            "results_due": bool(row["no_new_buy"]),
            "intraday_stop": price + stop_gap,
            "intraday_shares": quantity,
            "intraday_value": quantity * price,
            "has_futures": lot is not None,
            "lot": lot,
            "lot_value": None if lot is None else lot * price,
            "loss_per_1pct": None if lot is None else lot * price * 0.01,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------- past results ----
def simulate(built, start=None, end=None, capital=None, futures_only=None):
    """Test the multi-day short rule on past prices.

    Each week: sell short the weakest scores that are below their 20-day EMA,
    up to SHORT_POSITIONS, in equal amounts. Buy back the day after a stock
    closes back above its EMA, or SHORT_STOP_LOSS above the sell price.

    It assumes any amount can be shorted. Real futures trade in whole lots of
    several lakh rupees, so with a small account this is a guide to whether
    the idea works, not to what the account would have earned.
    futures_only: a set of symbols; only these are shorted (today's futures
    list, which is not exactly the list of earlier years).
    Returns the same kind of result as rotation.simulate.
    """
    prepared = built.trading
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
    last_close = prepared["last_close"].to_numpy(dtype=float)
    in_trend = prepared["in_trend"].to_numpy(dtype=bool)

    banked = capital            # starting money plus the result of closed trades
    positions = {}              # symbol -> {"quantity", "entry", "entry_day", "cost"}
    trades, equity = [], [capital]

    def side_cost(value):
        return value * (config.SHORT_COST + config.SLIPPAGE) + config.SHORT_ORDER_FEE

    def cover(symbol, day, reason):
        nonlocal banked
        holding = positions.pop(symbol)
        price = opens[day, column[symbol]]
        cost = holding["cost"] + side_cost(holding["quantity"] * price)
        profit = (holding["entry"] - price) * holding["quantity"] - cost
        banked += profit
        trades.append({
            "symbol": symbol, "entry_date": calendar[holding["entry_day"]].date(),
            "entry_price": round(holding["entry"], 2), "quantity": holding["quantity"],
            "exit_date": calendar[day].date(), "exit_price": round(price, 2),
            "reason": reason, "charges": round(cost, 2), "profit": round(profit, 2)})

    for day in range(first + 1, last + 1):
        yesterday = day - 1
        for symbol in list(positions):
            if np.isnan(opens[day, column[symbol]]):
                continue
            ceiling = positions[symbol]["entry"] * (1 + config.SHORT_STOP_LOSS)
            if last_close[yesterday, column[symbol]] >= ceiling:
                cover(symbol, day, "stop-loss")
            elif in_trend[yesterday, column[symbol]]:
                cover(symbol, day, "trend turned up")

        if rotation._new_period(calendar, day, "week"):
            table = built.score_on(yesterday)
            weakest = list(table.index[::-1][:config.SHORT_POOL])
            account = equity[-1]
            for symbol in weakest:
                if len(positions) >= config.SHORT_POSITIONS:
                    break
                number = column[symbol]
                if symbol in positions or np.isnan(opens[day, number]) \
                        or in_trend[yesterday, number]:
                    continue
                if futures_only is not None and symbol not in futures_only:
                    continue
                entry = opens[day, number]
                quantity = math.floor(account / config.SHORT_POSITIONS / entry)
                if quantity < 1:
                    continue
                positions[symbol] = {"quantity": quantity, "entry": entry, "entry_day": day,
                                     "cost": side_cost(quantity * entry)}

        open_result = sum((holding["entry"] - last_close[day, column[symbol]])
                          * holding["quantity"] - holding["cost"]
                          for symbol, holding in positions.items())
        equity.append(banked + open_result)

    columns = ["symbol", "entry_date", "entry_price", "quantity", "exit_date",
               "exit_price", "reason", "charges", "profit"]
    return {
        "capital": capital,
        "equity": pd.Series(equity, index=calendar[first:last + 1], name="equity"),
        "trades": pd.DataFrame(trades, columns=columns),
        "open": sorted(positions),
    }
