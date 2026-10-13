"""Checks the index membership logic and the price cleaning."""

import pandas as pd

from trading import data

MEMBERSHIP = pd.DataFrame({
    "symbol": ["AAA", "AAA", "BBB", "CCC"],
    "start": pd.to_datetime(["2015-01-01", "2020-01-01", "2018-06-01", "2010-01-01"]),
    "end": pd.to_datetime(["2016-01-01", None, None, "2014-06-30"]),
})
DATES = pd.to_datetime(["2015-06-01", "2016-01-01", "2017-01-01", "2021-01-01"])


def test_member_only_between_start_and_end():
    mask = data.membership_mask("AAA", DATES, MEMBERSHIP)
    # in during 2015, out from the end date, out in 2017, back in from 2020
    assert list(mask) == [True, False, False, True]


def test_stock_that_joined_later_is_not_a_member_before_that():
    assert list(data.membership_mask("BBB", DATES, MEMBERSHIP)) == [False, False, False, True]


def test_unknown_stock_is_never_a_member():
    assert not data.membership_mask("ZZZ", DATES, MEMBERSHIP).any()


def test_without_a_membership_table_every_day_counts():
    assert data.membership_mask("AAA", DATES, None).all()


def test_symbols_since_leaves_out_stocks_that_left_before_the_start():
    assert data.symbols_since(MEMBERSHIP, "2015-01-01") == ["AAA", "BBB"]


def test_coverage_counts_members_with_and_without_prices():
    coverage = data.coverage_by_year(MEMBERSHIP, {"AAA"}, 2021, 2021)
    assert coverage.iloc[0]["members"] == 2          # AAA and BBB
    assert coverage.iloc[0]["with_prices"] == 1      # only AAA has prices


def test_clean_prices_sorts_drops_empty_rows_and_duplicates():
    raw = pd.DataFrame(
        {"Close": [3.0, 1.0, None, 2.0], "High": 5.0, "Low": 0.5, "Open": 1.0, "Volume": 10},
        index=pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02", "2024-01-03"]),
    )
    clean = data.clean_prices(raw)
    assert list(clean.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert list(clean["Close"]) == [1.0, 2.0]        # sorted, no empty row, last duplicate kept
    assert clean.index.name == "Date"


def test_clean_prices_returns_empty_table_for_no_data():
    assert len(data.clean_prices(None)) == 0
    assert len(data.clean_prices(pd.DataFrame())) == 0


def test_current_member_missing_from_history_is_added_from_a_year_ago():
    added = data.add_listed_members(MEMBERSHIP, ["AAA", "BBB", "ITC"], today="2026-10-13")
    itc = added[added["symbol"] == "ITC"]
    assert len(itc) == 1
    assert itc.iloc[0]["start"] == pd.Timestamp("2025-10-13")
    assert pd.isna(itc.iloc[0]["end"])
    assert data.membership_mask("ITC", pd.to_datetime(["2020-01-01", "2026-10-12"]),
                                added).tolist() == [False, True]


def test_members_already_in_the_history_are_not_added_twice():
    added = data.add_listed_members(MEMBERSHIP, ["AAA", "BBB"], today="2026-10-13")
    assert len(added) == len(MEMBERSHIP)
