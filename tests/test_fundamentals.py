"""Checks the company ratios, the quality filter and the results-date block."""

import math

import pandas as pd

import config
from trading import fundamentals


def _company(rows):
    """rows: (year end, revenue, net income, equity, debt, shares)"""
    return pd.DataFrame(
        [{"symbol": "TEST", "period_end": pd.Timestamp(end), "revenue": revenue,
          "operating_income": None, "net_income": profit, "equity": equity,
          "total_debt": debt, "shares": shares}
         for end, revenue, profit, equity, debt, shares in rows]
    )


GOOD = _company([("2023-03-31", 1000.0, 100.0, 500.0, 200.0, 10.0),
                 ("2024-03-31", 1200.0, 150.0, 600.0, 300.0, 10.0)])


def test_ratios_match_hand_calculation():
    latest = fundamentals.yearly_metrics(GOOD).iloc[-1]
    assert math.isclose(latest["sales_growth"], 0.20)        # 1000 -> 1200
    assert math.isclose(latest["profit_growth"], 0.50)       # 100 -> 150
    assert math.isclose(latest["net_margin"], 0.125)         # 150 / 1200
    assert math.isclose(latest["return_on_equity"], 0.25)    # 150 / 600
    assert math.isclose(latest["debt_to_equity"], 0.50)      # 300 / 600


def test_first_year_has_no_growth_figures():
    first = fundamentals.yearly_metrics(GOOD).iloc[0]
    assert pd.isna(first["sales_growth"]) and pd.isna(first["profit_growth"])


def test_profit_growth_from_a_loss_to_a_profit_is_positive():
    company = _company([("2023-03-31", 1000.0, -50.0, 500.0, 0.0, 10.0),
                        ("2024-03-31", 1100.0, 50.0, 550.0, 0.0, 10.0)])
    assert fundamentals.yearly_metrics(company).iloc[-1]["profit_growth"] == 2.0


def _latest(company):
    return fundamentals.yearly_metrics(company).iloc[-1]


def test_a_growing_profitable_low_debt_company_passes():
    assert fundamentals.passes_quality(_latest(GOOD))


def test_a_loss_making_company_fails():
    company = _company([("2023-03-31", 1000.0, 100.0, 500.0, 0.0, 10.0),
                        ("2024-03-31", 1200.0, -10.0, 490.0, 0.0, 10.0)])
    assert not fundamentals.passes_quality(_latest(company))


def test_shrinking_sales_fail():
    company = _company([("2023-03-31", 1000.0, 100.0, 500.0, 0.0, 10.0),
                        ("2024-03-31", 900.0, 100.0, 600.0, 0.0, 10.0)])
    assert not fundamentals.passes_quality(_latest(company))


def test_low_return_on_equity_fails():
    company = _company([("2023-03-31", 1000.0, 100.0, 5000.0, 0.0, 10.0),
                        ("2024-03-31", 1200.0, 120.0, 5100.0, 0.0, 10.0)])
    assert not fundamentals.passes_quality(_latest(company))   # 120 / 5100 = 2.4%


def test_heavy_debt_fails_unless_the_company_is_a_bank():
    company = _company([("2023-03-31", 1000.0, 100.0, 500.0, 2000.0, 10.0),
                        ("2024-03-31", 1200.0, 150.0, 600.0, 3000.0, 10.0)])
    assert not fundamentals.passes_quality(_latest(company))
    assert fundamentals.passes_quality(_latest(company), is_financial=True)


def test_negative_equity_fails():
    company = _company([("2024-03-31", 1200.0, 150.0, -100.0, 3000.0, 10.0)])
    assert not fundamentals.passes_quality(_latest(company))


def test_results_are_not_used_before_they_were_public():
    bad_then_good = _company([("2023-03-31", 1000.0, -100.0, 500.0, 0.0, 10.0),
                              ("2024-03-31", 1200.0, 150.0, 600.0, 0.0, 10.0)])
    dates = pd.to_datetime(["2023-04-10", "2023-07-01", "2024-04-10", "2024-07-01"])
    mask = fundamentals.quality_mask(bad_then_good, dates)
    # 10 Apr 2023: nothing published yet, so nothing is filtered -> True
    # 1 Jul 2023: the loss-making year is public -> False
    # 10 Apr 2024: the good year has ended but is NOT public yet -> still False
    # 1 Jul 2024: the good year is public -> True
    assert list(mask) == [True, False, False, True]
    assert config.REPORTING_LAG_DAYS >= 60


def test_company_without_results_is_not_filtered():
    dates = pd.to_datetime(["2024-01-01"])
    assert fundamentals.quality_mask(None, dates).all()


def test_days_before_results_are_blocked():
    dates = pd.to_datetime(["2024-07-10", "2024-07-15", "2024-07-18", "2024-07-19"])
    mask = fundamentals.near_results_mask([pd.Timestamp("2024-07-18")], dates)
    # 8 days before: free. 3 days before: blocked. Results day: blocked. Day after: free.
    assert list(mask) == [False, True, True, False]


def test_valuation_from_price_and_share_count():
    snapshot = fundamentals.latest_snapshot(GOOD, close=300.0)
    assert math.isclose(snapshot["pe"], 20.0)             # 300 x 10 shares / 150 profit
    assert math.isclose(snapshot["price_to_book"], 5.0)   # 3000 / 600


def test_snapshot_respects_the_reporting_lag():
    snapshot = fundamentals.latest_snapshot(GOOD, close=300.0, as_of="2024-04-10")
    assert snapshot["period_end"] == pd.Timestamp("2023-03-31")
