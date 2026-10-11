"""Checks the ownership rotation: scoring days, ownership changes, scores and trades."""

import math

import numpy as np
import pandas as pd

import config
from trading import rotation


def _holdings(rows):
    """rows: (symbol, quarter end, filed on, fii, mutual funds)"""
    return pd.DataFrame(
        [{"symbol": symbol, "quarter_end": pd.Timestamp(quarter), "filed_on": pd.Timestamp(filed),
          "promoter": 50.0, "fii": fii, "dii": 20.0, "mutual_funds": funds, "insurance": 5.0,
          "public": 10.0, "promoters_pledged": False}
         for symbol, quarter, filed, fii, funds in rows])


HOLDINGS = _holdings([
    ("AAA", "2025-03-31", "2025-04-15", 10.0, 5.0), ("AAA", "2025-06-30", "2025-07-15", 12.5, 6.0),
    ("BBB", "2025-03-31", "2025-04-15", 20.0, 9.0), ("BBB", "2025-06-30", "2025-07-15", 19.0, 8.5),
    ("LATE", "2025-03-31", "2025-04-15", 10.0, 5.0), ("LATE", "2025-06-30", "2025-08-20", 15.0, 9.0),
])
SCORING_DAY = pd.Timestamp("2025-07-30")


def test_scores_are_refreshed_30_days_after_each_quarter_end():
    days = rotation.scoring_days(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31"))
    assert days == [pd.Timestamp(day) for day in
                    ("2025-01-30", "2025-04-30", "2025-07-30", "2025-10-30")]


def test_ownership_change_is_this_quarter_minus_the_last():
    changes = rotation.ownership_changes(HOLDINGS, SCORING_DAY)
    assert changes.loc["AAA", "fii_change"] == 2.5 and changes.loc["AAA", "mf_change"] == 1.0
    assert changes.loc["BBB", "fii_change"] == -1.0 and changes.loc["BBB", "mf_change"] == -0.5


def test_a_filing_made_after_the_scoring_day_is_not_used():
    changes = rotation.ownership_changes(HOLDINGS, SCORING_DAY)
    assert "LATE" not in changes.index           # filed on 20 August, after 30 July


def test_foreign_holding_change_is_ignored_in_the_quarter_the_format_changed():
    holdings = _holdings([("AAA", "2022-06-30", "2022-07-15", 10.0, 5.0),
                          ("AAA", "2022-09-30", "2022-10-15", 14.0, 6.0)])
    changes = rotation.ownership_changes(holdings, pd.Timestamp("2022-10-30"))
    assert pd.isna(changes.loc["AAA", "fii_change"]) and changes.loc["AAA", "mf_change"] == 1.0


def test_score_is_the_average_of_the_three_ranks():
    changes = pd.DataFrame({"fii_change": [3.0, 1.0, 2.0], "mf_change": [1.0, 3.0, 2.0]},
                           index=["AAA", "BBB", "CCC"])
    momentum = pd.Series({"AAA": 0.30, "BBB": 0.10, "CCC": 0.20})
    table = rotation.score_table(changes, momentum)
    # AAA: best on foreign buying (3/3), worst on fund buying (1/3), best on price (3/3)
    assert math.isclose(table.loc["AAA", "score"], (1 + 1 / 3 + 1) / 3)
    assert math.isclose(table.loc["BBB", "score"], (1 / 3 + 1 + 1 / 3) / 3)
    assert list(table.index) == ["AAA", "CCC", "BBB"]      # best first


def test_a_stock_without_a_price_history_gets_no_score():
    changes = pd.DataFrame({"fii_change": [3.0, 1.0], "mf_change": [1.0, 3.0]}, index=["AAA", "NEW"])
    table = rotation.score_table(changes, pd.Series({"AAA": 0.30, "NEW": np.nan}))
    assert list(table.index) == ["AAA"]


# ---- a small end-to-end run: 3 stocks, 2 scoring days ------------------------
DAYS = pd.bdate_range("2024-06-03", "2025-12-31")


def _stock(start, daily_growth):
    close = start * (1 + daily_growth) ** np.arange(len(DAYS))
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": 5_000_000.0}, index=DAYS)


def _run(nifty_growth=0.0005, **settings):
    stocks = {"UP": _stock(500.0, 0.002), "FLAT": _stock(500.0, 0.0), "DOWN": _stock(500.0, -0.001)}
    nifty = pd.DataFrame({"Close": 20_000 * (1 + nifty_growth) ** np.arange(len(DAYS))}, index=DAYS)
    holdings = _holdings([
        ("UP", "2025-03-31", "2025-04-15", 10.0, 5.0), ("UP", "2025-06-30", "2025-07-15", 13.0, 7.0),
        ("FLAT", "2025-03-31", "2025-04-15", 10.0, 5.0), ("FLAT", "2025-06-30", "2025-07-15", 10.5, 5.2),
        ("DOWN", "2025-03-31", "2025-04-15", 10.0, 5.0), ("DOWN", "2025-06-30", "2025-07-15", 8.0, 4.0),
    ])
    prepared = rotation.prepare(stocks, nifty, lambda symbol, dates: pd.Series(True, index=dates))
    return rotation.simulate(prepared, holdings, start="2025-07-01", capital=100_000)


def test_the_best_scoring_stocks_are_bought_on_the_first_day_of_the_month(monkeypatch):
    monkeypatch.setattr(config, "ROTATION_POSITIONS", 2)
    monkeypatch.setattr(config, "ROTATION_KEEP_RANK", 2)
    result = _run()
    held = result["positions"]
    assert set(held["symbol"]) == {"UP", "FLAT"}           # the two best of three
    # Scores come out on 30 July, so the first purchase is on 1 August.
    assert str(held["bought_on"].min()) == "2025-08-01"
    assert list(result["scores"].index) == ["UP", "FLAT", "DOWN"]
    # Half the money in each, never more than there is.
    spent = (held["buy_price"] * held["quantity"]).sum()
    assert 95_000 < spent <= 100_000
    assert result["equity"].iloc[-1] > 100_000             # UP rose, FLAT stayed level


def test_everything_is_sold_when_nifty_is_below_its_average(monkeypatch):
    monkeypatch.setattr(config, "ROTATION_POSITIONS", 2)
    monkeypatch.setattr(config, "ROTATION_KEEP_RANK", 2)
    result = _run(nifty_growth=-0.0005)                    # a falling market
    assert len(result["positions"]) == 0 and len(result["trades"]) == 0
    assert result["equity"].iloc[-1] == 100_000            # stayed in cash throughout
    assert result["market_ok"] is False


# ---- what to do now ----------------------------------------------------------
def _prepared(nifty_growth=0.0005, last_day="2025-12-31"):
    days = pd.bdate_range("2024-06-03", last_day)
    grow = lambda start, rate: start * (1 + rate) ** np.arange(len(days))
    def stock(start, rate):
        close = grow(start, rate)
        return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                             "Volume": 5_000_000.0}, index=days)
    stocks = {"UP": stock(500.0, 0.002), "FLAT": stock(500.0, 0.0), "DOWN": stock(500.0, -0.001)}
    nifty = pd.DataFrame({"Close": grow(20_000, nifty_growth)}, index=days)
    holdings = _holdings([
        ("UP", "2025-06-30", "2025-07-15", 10.0, 5.0), ("UP", "2025-09-30", "2025-10-15", 13.0, 7.0),
        ("FLAT", "2025-06-30", "2025-07-15", 10.0, 5.0), ("FLAT", "2025-09-30", "2025-10-15", 10.5, 5.2),
        ("DOWN", "2025-06-30", "2025-07-15", 10.0, 5.0), ("DOWN", "2025-09-30", "2025-10-15", 8.0, 4.0),
    ])
    return rotation.prepare(stocks, nifty, lambda symbol, dates: pd.Series(True, index=dates)), holdings


def test_decision_buys_the_top_ranked_and_sells_what_fell_out(monkeypatch):
    monkeypatch.setattr(config, "ROTATION_POSITIONS", 2)
    monkeypatch.setattr(config, "ROTATION_KEEP_RANK", 2)
    prepared, holdings = _prepared()
    plan = rotation.decision(prepared, holdings, held_symbols=["DOWN", "FLAT"])
    assert plan["market_ok"] is True
    assert plan["sell"] == ["DOWN"]            # ranked third, outside the top 2
    assert plan["keep"] == ["FLAT"]
    assert plan["buy"] == ["UP"]               # fills the one free place
    assert list(plan["ranking"].index) == ["UP", "FLAT"]


def test_decision_with_nothing_held_buys_the_top_names(monkeypatch):
    monkeypatch.setattr(config, "ROTATION_POSITIONS", 2)
    monkeypatch.setattr(config, "ROTATION_KEEP_RANK", 2)
    prepared, holdings = _prepared()
    plan = rotation.decision(prepared, holdings, held_symbols=[])
    assert plan["buy"] == ["UP", "FLAT"] and plan["sell"] == [] and plan["keep"] == []


def test_decision_sells_everything_in_a_weak_market():
    prepared, holdings = _prepared(nifty_growth=-0.0005)
    plan = rotation.decision(prepared, holdings, held_symbols=["UP", "FLAT"])
    assert plan["market_ok"] is False
    assert plan["sell"] == ["UP", "FLAT"] and plan["buy"] == []


def test_decision_knows_when_the_monthly_check_is_due():
    month_end, _ = _prepared(last_day="2025-12-31")      # last trading day of December
    mid_month, _ = _prepared(last_day="2025-12-15")
    _, holdings = _prepared()
    due = rotation.decision(month_end, holdings, [])
    not_due = rotation.decision(mid_month, holdings, [])
    assert due["due_next_session"] is True and str(due["decided_on"].date()) == "2025-12-31"
    # Mid-month, the plan is the one made at the last close of November.
    assert not_due["due_next_session"] is False and str(not_due["decided_on"].date()) == "2025-11-28"
