"""Checks sector strength and market breadth."""

import numpy as np
import pandas as pd

from trading import breadth

DAYS = pd.bdate_range("2026-01-01", periods=260)


def test_sector_strength_groups_by_industry_and_sorts_by_last_month():
    close = pd.DataFrame({"A": np.linspace(100, 120, 260), "B": np.linspace(100, 110, 260),
                          "C": np.linspace(100, 130, 260), "D": np.linspace(100, 90, 260)},
                         index=DAYS)
    ranking = pd.DataFrame({"score": [80.0, 70.0, 60.0, 40.0]}, index=list("ABCD"))
    industry = {"A": "Banks", "B": "Banks", "C": "Banks", "D": "IT"}
    table = breadth.sector_strength(ranking, close, {"A": True, "B": True, "C": False, "D": False},
                                    industry, minimum=1)
    assert list(table.index) == ["Banks", "IT"]
    assert table.loc["Banks", "stocks"] == 3 and round(table.loc["Banks", "above_ema_%"]) == 67


def test_breadth_is_the_share_of_stocks_above_their_lines():
    close = pd.DataFrame({"UP": np.linspace(100, 200, 260), "DOWN": np.linspace(200, 100, 260)},
                         index=DAYS)
    liquid = pd.DataFrame(True, index=DAYS, columns=close.columns)
    table = breadth.breadth(close, liquid)
    assert table["above_20_ema_%"].iloc[-1] == 50.0 and table["above_200_day_%"].iloc[-1] == 50.0
