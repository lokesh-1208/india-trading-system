"""Checks the company card figures and the scorecard against hand calculations."""

import math

import pandas as pd

from trading import company


def _prices(close=300.0, high=400.0, low=200.0):
    days = pd.bdate_range("2025-10-10", periods=260)
    table = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                          "Volume": 1000.0}, index=days)
    table.iloc[100, table.columns.get_loc("High")] = high
    table.iloc[150, table.columns.get_loc("Low")] = low
    return table


def _annual(rows):
    """rows: (year end, revenue, net income, equity, debt, shares)"""
    return pd.DataFrame(
        [{"symbol": "T", "period_end": pd.Timestamp(end), "revenue": revenue,
          "operating_income": None, "net_income": profit, "equity": equity,
          "total_debt": debt, "shares": shares}
         for end, revenue, profit, equity, debt, shares in rows])


def _quarterly(rows):
    return pd.DataFrame(
        [{"symbol": "T", "period_end": pd.Timestamp(end), "revenue": revenue,
          "net_income": profit} for end, revenue, profit in rows])


ANNUAL = _annual([("2023-03-31", 1000e7, 100e7, 500e7, 100e7, 10e7),
                  ("2024-03-31", 1100e7, 110e7, 560e7, 100e7, 10e7),
                  ("2025-03-31", 1210e7, 121e7, 620e7, 100e7, 10e7),
                  ("2026-03-31", 1331e7, 133.1e7, 700e7, 140e7, 10e7)])
QUARTERS = _quarterly([("2025-06-30", 300e7, 30e7), ("2025-09-30", 320e7, 32e7),
                       ("2025-12-31", 340e7, 34e7), ("2026-03-31", 371e7, 37.1e7),
                       ("2026-06-30", 390e7, 45e7)])
DIVIDENDS = pd.DataFrame({"symbol": "T",
                          "date": pd.to_datetime(["2025-01-10", "2026-02-10", "2026-08-10"]),
                          "amount": [9.0, 2.0, 4.0]})


def _card(**changes):
    arguments = dict(symbol="T", prices=_prices(), annual_rows=ANNUAL,
                     quarterly_rows=QUARTERS, dividend_rows=DIVIDENDS, industry="Chemicals")
    arguments.update(changes)
    return company.build_card(**arguments)


def test_price_range_over_the_last_year():
    card = _card()
    assert card["high_52w"] == 400.0 and card["low_52w"] == 200.0
    assert math.isclose(card["below_52w_high"], -0.25)      # 300 against a high of 400


def test_size_and_book_value():
    card = _card()
    assert math.isclose(card["market_cap_crore"], 3000.0)   # 300 x 10 crore shares
    assert math.isclose(card["book_value"], 70.0)           # 700 crore / 10 crore shares
    assert math.isclose(card["price_to_book"], 300 / 70)


def test_growth_over_one_and_three_years():
    card = _card()
    assert math.isclose(card["sales_growth_1y"], 0.10)      # 1210 -> 1331
    assert math.isclose(card["profit_growth_1y"], 0.10)
    assert math.isclose(card["sales_growth_3y"], 0.10)      # 1000 -> 1331 is 10% a year
    assert math.isclose(card["profit_growth_3y"], 0.10)


def test_profitability_and_debt():
    card = _card()
    assert math.isclose(card["net_margin"], 0.10)           # 133.1 / 1331
    assert math.isclose(card["return_on_equity"], 133.1 / 700)
    assert math.isclose(card["debt_to_equity"], 0.20)       # 140 / 700


def test_pe_uses_the_last_four_quarters_when_they_are_complete():
    card = _card()
    # last four quarters' profit: 32 + 34 + 37.1 + 45 = 148.1 crore, on 10 crore shares
    assert card["earnings_basis"] == "last 4 quarters"
    assert math.isclose(card["eps"], 14.81)
    assert math.isclose(card["pe"], 300 / 14.81)


def test_pe_falls_back_to_the_full_year_when_a_quarter_is_missing():
    with_gap = QUARTERS.drop(index=2)                       # December quarter missing
    card = _card(quarterly_rows=with_gap)
    assert card["earnings_basis"] == "last full year"
    assert math.isclose(card["eps"], 13.31)                 # 133.1 crore / 10 crore shares


def test_no_pe_for_a_loss_making_company():
    losing = _annual([("2026-03-31", 1000e7, -50e7, 500e7, 0.0, 10e7)])
    card = _card(annual_rows=losing, quarterly_rows=None)
    assert card["pe"] is None and math.isclose(card["eps"], -5.0)


def test_latest_quarter_is_compared_with_the_same_quarter_a_year_ago():
    card = _card()
    assert math.isclose(card["quarter_sales_growth"], 0.30)   # 300 -> 390
    assert math.isclose(card["quarter_profit_growth"], 0.50)  # 30 -> 45


def test_dividend_yield_counts_only_the_last_twelve_months():
    card = _card()
    # prices end in October 2026: the 2 and 4 rupee dividends count, the 2025 one does not
    assert math.isclose(card["dividend_yield"], 6.0 / 300.0)


def test_card_without_any_company_results_still_has_prices():
    card = _card(annual_rows=None, quarterly_rows=None, dividend_rows=None)
    assert card["close"] == 300.0 and card["pe"] is None and card["dividend_yield"] is None
    assert company.score(card) == 0


def test_industry_pe_is_the_middle_value_and_needs_three_companies():
    cards = [{"industry": "Chemicals", "pe": pe} for pe in (10.0, 20.0, 90.0)]
    cards += [{"industry": "Power", "pe": 15.0}, {"industry": "Power", "pe": None}]
    result = company.industry_pe(cards)
    assert result == {"Chemicals": 20.0}


def test_scorecard_counts_the_checks_passed():
    card = _card()
    card["industry_pe"] = 25.0
    checks = dict(company.scorecard(card))
    # growth is exactly 10%, quarter profit is up, ROE 19%, margin 10%, debt 0.2,
    # PE 20.3 is below 25, and it pays a dividend: all ten pass
    assert all(checks.values())
    assert company.score(card) == 10


def test_scorecard_marks_unknown_figures_as_unknown_not_failed():
    card = _card(quarterly_rows=None, dividend_rows=None)
    checks = dict(company.scorecard(card))
    assert checks["Latest quarter's profit is higher than a year ago"] is None
    assert checks["PE is not above the industry's"] is None


def test_debt_check_is_skipped_for_financial_companies():
    card = _card()
    card["debt_to_equity"] = 8.0
    assert dict(company.scorecard(card))["Low debt"] is False
    assert dict(company.scorecard(card, is_financial=True))["Low debt"] is True


def test_card_prints_without_error():
    text = company.format_card(_card())
    assert "SCORECARD" in text and "52-week" in text


def test_card_shows_the_shareholding_section():
    card = _card()
    assert "Shareholding not downloaded" in company.format_card(card)
    card["owners"] = {
        "quarter_end": pd.Timestamp("2026-06-30"), "previous_quarter": pd.Timestamp("2026-03-31"),
        "promoter": 50.0, "promoter_change": 0.0, "fii": 18.5, "fii_change": -1.5,
        "dii": 16.25, "dii_change": 1.25, "mutual_funds": 9.0, "mutual_funds_change": 1.0,
        "insurance": 5.0, "insurance_change": 0.0, "public": 15.25, "public_change": 0.25,
        "promoters_pledged": False, "funds": [("Big Fund", 2.4)],
    }
    text = company.format_card(card)
    assert "Foreign institutions     18.50%   (-1.50 from the quarter before)" in text
    assert " 2.40%  Big Fund" in text
