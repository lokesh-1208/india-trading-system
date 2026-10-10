"""Checks the backtester on tiny hand-made price histories.

Each test builds 60 days of one stock. The stock gives a signal on day 54
(high 101, ATR 2). So the plan is always:
    buy above 101, stop-loss 98 (101 - 1.5 x 2), target 107 (101 + 2 x 3)
and each test changes what happens on the following days.
"""

import math

import numpy as np
import pandas as pd

import config
from trading import backtest, charges

DAYS = pd.bdate_range("2024-01-01", periods=60)
SIGNAL_DAY, ENTRY_DAY, NEXT_DAY, DAY_AFTER = 54, 55, 56, 57

ENTRY = 101.0 * (1 + config.SLIPPAGE)
QUANTITY = 247  # 25% of 1,00,000 divided by the entry price, rounded down


def _nifty(rising=True):
    values = np.linspace(20_000, 22_000, 60) if rising else np.linspace(22_000, 20_000, 60)
    return pd.DataFrame({"Close": values}, index=DAYS)


def _stock(later_days):
    """later_days: {day number: (open, high, low, close)} for days after the signal."""
    table = pd.DataFrame({
        "Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0,
        "ema_fast": 50.0, "atr": 2.0, "relative_strength": 0.1, "signal": False,
    }, index=DAYS)
    table.iloc[SIGNAL_DAY, table.columns.get_loc("High")] = 101.0
    table.iloc[SIGNAL_DAY, table.columns.get_loc("signal")] = True
    for day, (day_open, high, low, close) in later_days.items():
        table.iloc[day, :4] = [day_open, high, low, close]
    return {"TEST": table}


def _expected_profit(exit_price):
    buy_value = QUANTITY * ENTRY
    sell_value = QUANTITY * exit_price * (1 - config.SLIPPAGE)
    return (sell_value - charges.sell_charges(sell_value)
            - buy_value - charges.buy_charges(buy_value))


def _run(later_days, rising_market=True):
    return backtest.run_backtest(_stock(later_days), _nifty(rising_market))


def test_trade_that_reaches_its_target():
    result = _run({ENTRY_DAY: (100.5, 103, 100.2, 102.5),
                   NEXT_DAY: (103, 108, 102.5, 107.5)})
    trades = result["trades"]
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["quantity"] == QUANTITY
    assert trade["stop"] == 98.0 and trade["target"] == 107.0
    assert trade["reason"] == "target"
    assert math.isclose(trade["profit"], _expected_profit(107.0), abs_tol=0.01)
    # The account must end with exactly the capital plus the profit.
    assert math.isclose(result["equity"].iloc[-1],
                        config.CAPITAL + _expected_profit(107.0), abs_tol=0.01)


def test_gap_up_at_the_open_pays_the_higher_price():
    result = _run({ENTRY_DAY: (102, 103, 101.5, 102.5)})
    assert math.isclose(result["trades"].iloc[0]["entry_price"],
                        102 * (1 + config.SLIPPAGE), abs_tol=0.01)


def test_no_trade_when_price_never_breaks_the_high():
    result = _run({ENTRY_DAY: (100.5, 101.0, 100.0, 100.8)})
    assert len(result["trades"]) == 0
    assert result["equity"].iloc[-1] == config.CAPITAL


def test_no_trade_when_the_market_is_falling():
    result = _run({ENTRY_DAY: (100.5, 103, 100.2, 102.5)}, rising_market=False)
    assert len(result["trades"]) == 0


def test_stop_loss():
    result = _run({ENTRY_DAY: (100.5, 103, 100.2, 102.5),
                   NEXT_DAY: (102, 102.5, 97.5, 98.5)})
    trade = result["trades"].iloc[0]
    assert trade["reason"] == "stop-loss"
    assert math.isclose(trade["profit"], _expected_profit(98.0), abs_tol=0.01)
    assert trade["profit"] < 0


def test_gap_down_sells_at_the_open_not_at_the_stop():
    result = _run({ENTRY_DAY: (100.5, 103, 100.2, 102.5),
                   NEXT_DAY: (95, 96, 94, 95.5)})
    trade = result["trades"].iloc[0]
    assert trade["reason"] == "stop-loss (gap down)"
    assert math.isclose(trade["profit"], _expected_profit(95.0), abs_tol=0.01)


def test_stop_wins_when_stop_and_target_are_hit_on_the_same_day():
    result = _run({ENTRY_DAY: (100.5, 103, 100.2, 102.5),
                   NEXT_DAY: (102, 108, 97, 105)})
    assert result["trades"].iloc[0]["reason"] == "stop-loss"


def test_close_below_the_fast_ema_sells_at_the_next_open():
    stock = _stock({ENTRY_DAY: (100.5, 103, 100.2, 102.5),
                    NEXT_DAY: (102, 103, 101, 101.5),
                    DAY_AFTER: (100.5, 101, 100, 100.5)})
    stock["TEST"].iloc[NEXT_DAY, stock["TEST"].columns.get_loc("ema_fast")] = 105.0
    result = backtest.run_backtest(stock, _nifty())
    trade = result["trades"].iloc[0]
    assert trade["reason"] == "trend exit"
    assert str(trade["exit_date"]) == str(DAYS[DAY_AFTER].date())
    assert math.isclose(trade["profit"], _expected_profit(100.5), abs_tol=0.01)


def test_max_drawdown():
    values = pd.Series([100.0, 120.0, 90.0, 130.0])
    assert math.isclose(backtest.max_drawdown(values), -0.25)


def test_summary_runs_and_reports_the_trade():
    result = _run({ENTRY_DAY: (100.5, 103, 100.2, 102.5),
                   NEXT_DAY: (103, 108, 102.5, 107.5)})
    summary, by_year = backtest.summarise(result)
    assert summary["trades"] == 1
    assert summary["win_rate"] == 1.0
    assert "BACKTEST RESULTS" in backtest.format_summary(summary, by_year)
