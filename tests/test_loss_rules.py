"""Checks for the rules added after the first real losses (16 Oct 2026):
two closes below the trend line before a sale, risk sizing, NSE holidays, and no
daily list made from a day that has not closed."""

import math

import pandas as pd

import config
from trading import holidays, picks, rotation, today
from server import views

CALENDAR = pd.bdate_range("2025-07-04", periods=8)


def _prepared(trend):
    close = pd.DataFrame({"AAA": [100.0] * 8}, index=CALENDAR)
    true = pd.DataFrame(True, index=CALENDAR, columns=["AAA"])
    return {"calendar": CALENDAR, "symbols": ["AAA"], "open": close, "low": close,
            "close": close, "last_close": close, "liquid": true,
            "in_trend": pd.DataFrame({"AAA": trend}, index=CALENDAR),
            "momentum": close * 0, "market_ok": pd.Series(True, index=CALENDAR)}


def _run(trend, **entry):
    scorer = lambda position: pd.DataFrame({"score": [1.0]}, index=["AAA"])
    return rotation.simulate(_prepared(trend), None, start=CALENDAR[0], capital=100_000,
                             scorer=scorer, check="week", positions_wanted=1, keep_rank=10,
                             trend_exit=True, **entry)


# Bought Monday (day 1); one close below the line on day 3, back above on day 4.
ONE_DIP = [True, True, True, False, True, True, True, True]
TWO_DIPS = [True, True, True, False, False, True, True, True]


def test_one_close_below_the_line_sells_under_the_old_rule():
    result = _run(ONE_DIP)
    assert list(result["trades"]["reason"]) == ["trend broke"]


def test_one_close_below_the_line_is_held_with_the_two_close_rule():
    result = _run(ONE_DIP, exit_confirm=2)
    assert result["trades"].empty and len(result["positions"]) == 1


def test_two_closes_below_the_line_sell_with_the_two_close_rule():
    result = _run(TWO_DIPS, exit_confirm=2)
    trade = result["trades"].iloc[0]
    assert trade["reason"] == "trend broke" and str(trade["exit_date"]) == str(CALENDAR[5].date())


def test_swing_style_uses_the_two_close_exit_and_risk_sizing():
    swing = config.MODEL_STYLES["swing"]
    assert swing["exit_confirm"] == 2 and swing["risk_per_trade"] == 0.01


def test_money_plan_gives_a_jumpy_stock_a_smaller_amount():
    plan = today.money_plan(100_000, 0, 0, 0, 5, 0, 1.0, [("CALM", 100.0), ("JUMPY", 100.0)],
                            scales={"CALM": 1.0, "JUMPY": 0.5})
    shares = {item["symbol"]: item["shares"] for item in plan["buys"]}
    assert shares["CALM"] == 200 and shares["JUMPY"] == 100


def test_my_stocks_warns_after_one_close_and_sells_after_two():
    positions = pd.DataFrame({"symbol": ["ONE", "TWO"], "buy_date": ["2026-10-13"] * 2,
                              "buy_price": [100.0, 100.0], "quantity": [10, 10],
                              "cost": [1000.0, 1000.0], "last_price": [97.0, 96.0]})
    plan = {"sell": ["TWO"], "keep": ["ONE"], "trend_broken": ["TWO"], "trend_warned": ["ONE"],
            "exit_confirm": 2}
    rows = today.my_stocks(plan, positions, {"ONE": 99.0, "TWO": 99.0},
                           last_day=pd.Timestamp("2026-10-15")).set_index("symbol")
    assert rows.loc["ONE", "action"] == "HOLD" and rows.loc["ONE", "warning"]
    assert "WARNING" in rows.loc["ONE", "reason"]
    assert rows.loc["TWO", "action"] == "SELL" and "2 days in a row" in rows.loc["TWO", "reason"]


# ---- NSE holidays: Dussehra is Tuesday 20 Oct 2026 ----
def test_holidays_are_skipped():
    assert not holidays.is_trading_day("2026-10-20")
    assert holidays.next_trading_day("2026-10-19") == pd.Timestamp("2026-10-21")
    assert holidays.previous_trading_day("2026-10-21") == pd.Timestamp("2026-10-19")


def test_an_order_placed_after_monday_close_is_for_wednesday():
    assert today.buy_day(pd.Timestamp("2026-10-19 18:00")) == pd.Timestamp("2026-10-21")
    assert today.buy_day(pd.Timestamp("2026-10-20 10:00")) == pd.Timestamp("2026-10-21")


def test_the_close_expected_skips_a_holiday():
    assert today.latest_close_expected(pd.Timestamp("2026-10-20 18:00")) == pd.Timestamp("2026-10-19")
    assert today.latest_close_expected(pd.Timestamp("2026-10-21 10:00")) == pd.Timestamp("2026-10-19")


def test_a_holiday_monday_moves_the_weekly_list_to_tuesday():
    # 14 Sep 2026 (Ganesh Chaturthi) was a Monday holiday.
    assert views.next_list_day("2026-09-11") == pd.Timestamp("2026-09-15")
    assert views.next_list_day("2026-10-16") == pd.Timestamp("2026-10-19")
    calendar = pd.DatetimeIndex(["2026-09-10", "2026-09-11"])
    assert picks.next_trading_day(calendar, 1) == pd.Timestamp("2026-09-15")


def test_no_list_is_made_from_a_day_that_has_not_closed():
    assert picks._unfinished_day(pd.Timestamp("2026-10-15 11:34")) == pd.Timestamp("2026-10-15")
    assert picks._unfinished_day(pd.Timestamp("2026-10-15 16:30")) is None
