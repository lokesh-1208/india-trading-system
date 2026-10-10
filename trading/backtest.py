"""Backtester: replay the swing rules day by day over past data.

How one trade is simulated, in the order things happen:
  1. Signal appears at the close of day 1.
  2. On day 2 we buy only if price goes above day 1's high. If the stock opens
     above that level we pay the (higher) opening price.
  3. Every later day we check, in this order:
       - stop-loss hit  -> sell at the stop (or at the open if it gapped below)
       - target hit     -> sell at the target (or at the open if it gapped above)
       - close below the fast EMA -> sell at the next day's open
     If stop and target are both touched on the same day we assume the stop
     came first. This is the pessimistic choice, on purpose.
  4. Every buy and sell pays Zerodha delivery charges and slippage.

The backtest never uses information from the future: decisions for a day use
only data up to the previous close.
"""

import numpy as np
import pandas as pd

import config
from trading import charges, strategy


def _wide(stocks, column, calendar):
    """One table for a single column: a row per day, a column per stock."""
    return pd.DataFrame(
        {symbol: table[column] for symbol, table in stocks.items()}
    ).reindex(calendar)


def run_backtest(stocks, nifty, start=None, end=None, capital=None):
    """Run the simulation.

    stocks : {symbol: price table with indicator columns from add_indicators}
    nifty  : Nifty price table, which also supplies the trading calendar
    Returns a dictionary with the trades, the daily equity and the settings used.
    """
    capital = config.CAPITAL if capital is None else capital

    calendar = nifty.index
    if start is not None:
        calendar = calendar[calendar >= pd.Timestamp(start)]
    if end is not None:
        calendar = calendar[calendar <= pd.Timestamp(end)]
    if len(calendar) < 2:
        raise ValueError("Not enough days in the chosen period to run a backtest.")

    symbols = list(stocks)
    opens = _wide(stocks, "Open", calendar).to_numpy(dtype=float)
    highs = _wide(stocks, "High", calendar).to_numpy(dtype=float)
    lows = _wide(stocks, "Low", calendar).to_numpy(dtype=float)
    closes = _wide(stocks, "Close", calendar).to_numpy(dtype=float)
    # Last known close, used to value a holding on a day the stock did not trade.
    last_closes = _wide(stocks, "Close", calendar).ffill().to_numpy(dtype=float)
    ema_fast = _wide(stocks, "ema_fast", calendar).to_numpy(dtype=float)
    atrs = _wide(stocks, "atr", calendar).to_numpy(dtype=float)
    strength = _wide(stocks, "relative_strength", calendar).to_numpy(dtype=float)
    signals = (
        _wide(stocks, "signal", calendar).astype("boolean").fillna(False)
        .to_numpy(dtype=bool)
    )
    market_ok = (
        strategy.market_is_healthy(nifty).reindex(calendar).fillna(False)
        .to_numpy(dtype=bool)
    )

    cash = float(capital)
    positions = {}          # column number of the stock -> details of the holding
    trades = []
    equity_by_day = [cash]  # value of the account at each day's close

    def sell(column, day, planned_price, reason):
        nonlocal cash
        holding = positions.pop(column)
        price = planned_price * (1 - config.SLIPPAGE)
        value = holding["quantity"] * price
        sell_cost = charges.sell_charges(value)
        cash += value - sell_cost

        total_charges = holding["buy_cost"] + sell_cost
        profit = value - sell_cost - holding["quantity"] * holding["entry"] - holding["buy_cost"]
        trades.append({
            "symbol": symbols[column],
            "entry_date": calendar[holding["entry_day"]].date(),
            "entry_price": round(holding["entry"], 2),
            "quantity": holding["quantity"],
            "stop": round(holding["stop"], 2),
            "target": round(holding["target"], 2),
            "exit_date": calendar[day].date(),
            "exit_price": round(price, 2),
            "reason": reason,
            "days_held": day - holding["entry_day"],
            "charges": round(total_charges, 2),
            "profit": round(profit, 2),
            "r_multiple": round(profit / holding["risk_rupees"], 2),
        })

    for day in range(1, len(calendar)):
        yesterday = day - 1

        # 1. Trend exits decided at yesterday's close are sold at today's open.
        for column in list(positions):
            if positions[column]["sell_at_open"] and not np.isnan(opens[day, column]):
                sell(column, day, opens[day, column], "trend exit")

        held_before_today = set(positions)

        # 2. New entries, strongest stocks first, only in a healthy market.
        free_slots = config.MAX_POSITIONS - len(positions)
        if market_ok[yesterday] and free_slots > 0:
            candidates = np.flatnonzero(signals[yesterday])
            candidates = sorted(candidates, key=lambda c: -strength[yesterday, c])
            equity = equity_by_day[-1]

            for column in candidates:
                if free_slots == 0:
                    break
                if column in positions:
                    continue
                trigger = highs[yesterday, column]
                today_open, today_high = opens[day, column], highs[day, column]
                if np.isnan(today_open) or np.isnan(today_high) or today_high <= trigger:
                    continue  # no trading today, or price never broke out

                planned = max(today_open, trigger)
                entry = planned * (1 + config.SLIPPAGE)
                stop, target = strategy.stop_and_target(planned, atrs[yesterday, column])
                if stop <= 0:
                    continue
                quantity = strategy.position_size(equity, entry, stop, cash)
                if quantity < 1:
                    continue

                value = quantity * entry
                buy_cost = charges.buy_charges(value)
                cash -= value + buy_cost
                positions[column] = {
                    "entry_day": day,
                    "entry": entry,
                    "quantity": quantity,
                    "stop": stop,
                    "target": target,
                    "buy_cost": buy_cost,
                    "risk_rupees": quantity * (entry - stop),
                    "sell_at_open": False,
                }
                free_slots -= 1

        # 3. Stop-loss and target checks.
        for column in list(positions):
            holding = positions[column]
            today_open, today_high = opens[day, column], highs[day, column]
            today_low = lows[day, column]
            if np.isnan(today_low):
                continue

            if column not in held_before_today:
                # Bought today. Only the stop can be hit, and never at the open.
                if today_low <= holding["stop"]:
                    sell(column, day, holding["stop"], "stop-loss")
                continue

            if today_open <= holding["stop"]:
                sell(column, day, today_open, "stop-loss (gap down)")
            elif today_low <= holding["stop"]:
                sell(column, day, holding["stop"], "stop-loss")
            elif today_open >= holding["target"]:
                sell(column, day, today_open, "target (gap up)")
            elif today_high >= holding["target"]:
                sell(column, day, holding["target"], "target")

        # 4. A close below the fast EMA means sell at tomorrow's open.
        for column, holding in positions.items():
            if closes[day, column] < ema_fast[day, column]:
                holding["sell_at_open"] = True

        # 5. Value of the account at today's close.
        holdings_value = sum(
            holding["quantity"] * last_closes[day, column]
            for column, holding in positions.items()
        )
        equity_by_day.append(cash + holdings_value)

    # Anything still open is closed at the last price so the results are complete.
    last_day = len(calendar) - 1
    for column in list(positions):
        sell(column, last_day, last_closes[last_day, column], "still open at end")
    equity_by_day[-1] = cash

    trade_columns = [
        "symbol", "entry_date", "entry_price", "quantity", "stop", "target",
        "exit_date", "exit_price", "reason", "days_held", "charges", "profit",
        "r_multiple",
    ]
    return {
        "capital": float(capital),
        "trades": pd.DataFrame(trades, columns=trade_columns),
        "equity": pd.Series(equity_by_day, index=calendar, name="equity"),
        "benchmark": nifty["Close"].reindex(calendar),
    }


# ------------------------------------------------------------------ results -
def max_drawdown(values):
    """Largest fall from a peak, as a negative fraction (-0.15 means -15%)."""
    peak = values.cummax()
    return float((values / peak - 1).min())


def yearly_growth(values, starting_value):
    """Return per calendar year, as fractions."""
    year_end = values.groupby(values.index.year).last()
    previous = year_end.shift(1)
    previous.iloc[0] = starting_value
    return year_end / previous - 1


def annual_growth_rate(start_value, end_value, days):
    """Compound annual growth rate (CAGR)."""
    if days <= 0 or start_value <= 0 or end_value <= 0:
        return float("nan")
    return (end_value / start_value) ** (365.25 / days) - 1


def summarise(result):
    """Turn a backtest result into the numbers that matter."""
    equity, trades, capital = result["equity"], result["trades"], result["capital"]
    benchmark = result["benchmark"].dropna()
    days = (equity.index[-1] - equity.index[0]).days

    wins = trades[trades["profit"] > 0]
    losses = trades[trades["profit"] <= 0]
    gross_profit = wins["profit"].sum()
    gross_loss = -losses["profit"].sum()

    summary = {
        "period_start": equity.index[0].date(),
        "period_end": equity.index[-1].date(),
        "starting_capital": capital,
        "final_value": round(float(equity.iloc[-1]), 2),
        "total_return": float(equity.iloc[-1] / capital - 1),
        "annual_growth_rate": annual_growth_rate(capital, equity.iloc[-1], days),
        "max_drawdown": max_drawdown(equity),
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) if len(trades) else float("nan"),
        "average_win": float(wins["profit"].mean()) if len(wins) else 0.0,
        "average_loss": float(losses["profit"].mean()) if len(losses) else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("nan"),
        "average_r": float(trades["r_multiple"].mean()) if len(trades) else float("nan"),
        "average_days_held": float(trades["days_held"].mean()) if len(trades) else float("nan"),
        "total_charges": float(trades["charges"].sum()),
        "benchmark_total_return": float(benchmark.iloc[-1] / benchmark.iloc[0] - 1),
        "benchmark_annual_growth_rate": annual_growth_rate(
            benchmark.iloc[0], benchmark.iloc[-1], days
        ),
        "benchmark_max_drawdown": max_drawdown(benchmark),
    }
    summary["drawdown_limit_breached"] = (
        summary["max_drawdown"] <= -config.TOTAL_DRAWDOWN_LIMIT
    )

    by_year = pd.DataFrame({
        "strategy": yearly_growth(equity, capital),
        "nifty": yearly_growth(benchmark, benchmark.iloc[0]),
    })
    by_year["trades"] = (
        trades.groupby(pd.to_datetime(trades["exit_date"]).dt.year).size()
        .reindex(by_year.index).fillna(0).astype(int)
    )
    return summary, by_year


def format_summary(summary, by_year):
    """Readable text version of the results. Plain ASCII so Windows prints it."""
    def pct(value):
        return "n/a" if pd.isna(value) else f"{value * 100:+.1f}%"

    def rupees(value):
        return f"Rs {value:,.0f}"

    lines = [
        "BACKTEST RESULTS",
        f"Period            : {summary['period_start']} to {summary['period_end']}",
        f"Starting capital  : {rupees(summary['starting_capital'])}",
        f"Final value       : {rupees(summary['final_value'])}",
        "",
        "                     Strategy      Nifty 50 (buy and hold)",
        f"Total return      : {pct(summary['total_return']):>9}     {pct(summary['benchmark_total_return']):>9}",
        f"Growth per year   : {pct(summary['annual_growth_rate']):>9}     {pct(summary['benchmark_annual_growth_rate']):>9}",
        f"Worst drawdown    : {pct(summary['max_drawdown']):>9}     {pct(summary['benchmark_max_drawdown']):>9}",
        "",
        f"Trades            : {summary['trades']}",
        f"Win rate          : {pct(summary['win_rate']).lstrip('+')}",
        f"Average win       : {rupees(summary['average_win'])}",
        f"Average loss      : {rupees(summary['average_loss'])}",
        f"Profit factor     : {summary['profit_factor']:.2f}  (above 1 means profits exceed losses)",
        f"Average result    : {summary['average_r']:+.2f} R  (1 R = the amount risked on a trade)",
        f"Average holding   : {summary['average_days_held']:.1f} trading days",
        f"Charges paid      : {rupees(summary['total_charges'])}",
        "",
        "Year     Strategy      Nifty   Trades",
    ]
    for year, row in by_year.iterrows():
        lines.append(
            f"{year}    {pct(row['strategy']):>8}   {pct(row['nifty']):>8}   {int(row['trades']):>6}"
        )
    lines.append("")
    if summary["drawdown_limit_breached"]:
        lines.append(
            f"WARNING: the worst drawdown is beyond your "
            f"{config.TOTAL_DRAWDOWN_LIMIT:.0%} limit. In live trading you would "
            f"have had to stop."
        )
    beat_return = summary["annual_growth_rate"] > summary["benchmark_annual_growth_rate"]
    smaller_fall = summary["max_drawdown"] > summary["benchmark_max_drawdown"]
    lines.append(f"Beat Nifty on growth per year : {'YES' if beat_return else 'NO'}")
    lines.append(f"Smaller drawdown than Nifty   : {'YES' if smaller_fall else 'NO'}")
    return "\n".join(lines)
