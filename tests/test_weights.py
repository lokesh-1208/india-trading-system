"""Checks the measured group weights and the industry scorecard option."""

import numpy as np
import pandas as pd

import config
from trading import model, weights

GROUPS = ["a", "b", "c"]


def test_weights_use_only_finished_weeks_and_shrink_half_way_to_equal():
    ic = pd.DataFrame({"a": [0.04] * 30 + [-1.0], "b": [0.0] * 31, "c": [np.nan] * 31},
                      index=range(31))
    found = weights.weights_from_ic(ic, GROUPS, lookback=52, min_weeks=26)
    # Week 30 (the last) must not see its own IC of -1.0
    last = found[30]
    assert last["a"] > last["b"]
    assert abs(sum(last.values()) - 1) < 1e-9
    # c has no history: it keeps the equal share
    assert abs(last["c"] - 1 / 3) < 1e-9
    # half way to equal: a gets 0.5 x 1/3 + 0.5 x (2/3 of the weight shared by a and b)
    assert abs(last["a"] - (0.5 / 3 + 0.5 * 2 / 3)) < 1e-9
    # Too few weeks: equal weights
    assert all(abs(w - 1 / 3) < 1e-9 for w in found[10].values())


def test_combine_accepts_its_own_weights():
    factors = pd.DataFrame({"momentum": [1.0, 2.0], "fii_change": [2.0, 1.0]}, index=["X", "Y"])
    by_price = model.combine(factors, {"price": 1.0, "ownership": 0.0})
    by_owners = model.combine(factors, {"price": 0.0, "ownership": 1.0})
    assert by_price.index[0] == "Y" and by_owners.index[0] == "X"


def test_industry_scorecard_compares_with_the_industry_median():
    table = pd.DataFrame({
        "sales_growth": [0.05, 0.06, 0.07, 0.08, 0.09], "profit_growth": [0.1] * 5,
        "sales_growth_3y": [0.1] * 5, "profit_growth_3y": [0.1] * 5,
        "quarter_profit_growth": [0.1] * 5, "return_on_equity": [0.1] * 5,
        "net_margin": [0.1] * 5, "debt_to_equity": [0.5] * 5, "pe": [10.0] * 5,
        "industry_pe": [10.0] * 5, "dividend_yield": [0.0] * 5, "roce": [0.1] * 5,
        "cash_conversion": [1.0] * 5}, index=list("VWXYZ"))
    industry = pd.Series(["Retail"] * 5, index=table.index)
    checks = model._industry_scorecard(table, industry, pd.Series(False, index=table.index))
    # Sales growth of 5% fails and 9% passes against a 7% industry median,
    # although both are under the fixed rule's 10%
    assert list(checks[0]) == [False, False, True, True, True]
