"""Checks how a new stock is bought when it opens away from the signal close."""

import math

import numpy as np
import pandas as pd

import config
from trading import rotation

# Friday is the signal day (close 100); Monday is the weekly buy day.
CALENDAR = pd.bdate_range("2025-07-04", periods=6)


def _prepared(monday_low, tuesday_low=99.0, monday_open=103.0):
    close = pd.DataFrame({"AAA": [100.0, 104, 104, 104, 104, 104]}, index=CALENDAR)
    opens = pd.DataFrame({"AAA": [100.0, monday_open, 104, 104, 104, 104]}, index=CALENDAR)
    low = pd.DataFrame({"AAA": [99.0, monday_low, tuesday_low, 103, 103, 103]}, index=CALENDAR)
    true = pd.DataFrame(True, index=CALENDAR, columns=["AAA"])
    return {
        "calendar": CALENDAR, "symbols": ["AAA"], "open": opens, "low": low,
        "close": close, "last_close": close, "liquid": true, "in_trend": true,
        "momentum": close * 0, "market_ok": pd.Series(True, index=CALENDAR),
    }


def _run(prepared, **entry):
    scorer = lambda position: pd.DataFrame({"score": [1.0]}, index=["AAA"])
    return rotation.simulate(prepared, None, start=CALENDAR[0], capital=100_000,
                             scorer=scorer, check="week", positions_wanted=1,
                             keep_rank=10, **entry)


def test_current_rule_buys_at_the_open_and_records_the_gap():
    result = _run(_prepared(monday_low=99.5))
    held = result["positions"].iloc[0]
    assert math.isclose(held["buy_price"], round(103 * (1 + config.SLIPPAGE), 2))


def test_a_gap_above_the_limit_is_skipped():
    result = _run(_prepared(monday_low=99.5), max_gap=0.02)
    assert result["positions"].empty and result["skipped"]["gap"] == 1


def test_a_gap_inside_the_limit_is_bought():
    result = _run(_prepared(monday_low=99.5), max_gap=0.05)
    assert len(result["positions"]) == 1


def test_limit_order_fills_at_the_signal_close_when_the_low_goes_below_it():
    result = _run(_prepared(monday_low=99.5), limit_days=1)
    assert result["positions"].iloc[0]["buy_price"] == 100.0


def test_limit_order_fills_at_the_open_when_the_stock_opens_below_it():
    result = _run(_prepared(monday_low=97.0, monday_open=98.0), limit_days=1)
    assert math.isclose(result["positions"].iloc[0]["buy_price"],
                        round(98 * (1 + config.SLIPPAGE), 2))


def test_one_day_limit_order_is_cancelled_when_not_filled():
    result = _run(_prepared(monday_low=101.0), limit_days=1)
    assert result["positions"].empty and result["skipped"]["limit_expired"] == 1


def test_two_day_limit_order_can_fill_on_the_second_day():
    result = _run(_prepared(monday_low=101.0, tuesday_low=99.0), limit_days=2)
    held = result["positions"].iloc[0]
    assert held["buy_price"] == 100.0 and str(held["bought_on"]) == str(CALENDAR[2].date())


def test_two_day_limit_order_expires_after_the_second_day():
    result = _run(_prepared(monday_low=101.0, tuesday_low=101.0), limit_days=2)
    assert result["positions"].empty and result["skipped"]["limit_expired"] == 1


def test_closed_trades_carry_the_opening_gap():
    prepared = _prepared(monday_low=99.5)
    prepared["in_trend"].iloc[2:] = False          # trend breaks: sold on Thursday
    result = _run(prepared, trend_exit=True)
    assert math.isclose(result["trades"].iloc[0]["gap_%"], 3.0)


def test_an_open_too_far_below_the_signal_is_skipped():
    result = _run(_prepared(monday_low=94.0, monday_open=95.0), max_drop=0.03)
    assert result["positions"].empty and result["skipped"]["drop"] == 1


def test_an_open_slightly_below_the_signal_is_bought():
    result = _run(_prepared(monday_low=97.0, monday_open=98.0), max_drop=0.03)
    assert len(result["positions"]) == 1
