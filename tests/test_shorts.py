"""Checks the short side: lot sizes, today's figures and the multi-day test."""

import pandas as pd

import config
from trading import shorts
from test_model import _model

LOT_FILE = """UNDERLYING                ,SYMBOL    ,OCT-26   ,NOV-26
NIFTY 50                  ,NIFTY     ,65       ,65
Derivatives on Individual Securities,SYMBOL  ,OCT-26   ,NOV-26
POOR LIMITED              ,POOR      ,500      ,500
NEW LISTING               ,NEWONE    ,         ,250
"""


def test_lot_sizes_are_read_from_the_exchange_file():
    assert shorts.parse_lots(LOT_FILE) == {"NIFTY": 65, "POOR": 500, "NEWONE": 250}


def test_candidates_are_the_weakest_scores_with_both_routes():
    table = shorts.candidates(_model(), {"POOR": 500}, capital=100_000, count=2)
    assert list(table["symbol"]) == ["POOR", "MID"]            # weakest first
    poor = table.iloc[0]
    assert bool(poor["falling"]) and bool(poor["has_futures"]) and poor["lot"] == 500
    assert round(poor["lot_value"]) == round(500 * poor["price"])
    assert poor["intraday_stop"] > poor["price"]
    # Intraday size: losing 1% of capital if the stop is hit.
    loss_at_stop = poor["intraday_shares"] * (poor["intraday_stop"] - poor["price"])
    assert 0 < loss_at_stop <= 100_000 * config.RISK_PER_TRADE
    assert not bool(table.iloc[1]["has_futures"]) and pd.isna(table.iloc[1]["lot_value"])


def test_shorting_a_falling_stock_makes_money_and_a_rising_one_is_never_shorted():
    result = shorts.simulate(_model(), start="2025-07-01", capital=100_000)
    trades = result["trades"]
    shorted = set(trades["symbol"]) | set(result["open"])
    assert "POOR" in shorted and "GOOD" not in shorted         # GOOD is above its EMA throughout
    assert result["equity"].iloc[-1] > 100_000                 # POOR fell 0.1% a day


def test_futures_only_limits_what_is_shorted():
    result = shorts.simulate(_model(), start="2025-07-01", capital=100_000, futures_only={"MID"})
    assert "POOR" not in set(result["trades"]["symbol"]) | set(result["open"])
