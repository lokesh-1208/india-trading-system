"""Checks the real-trade journal: recording, closing and the totals."""

import math

import pandas as pd

from trading import journal


def _two_trades():
    table = pd.DataFrame(columns=journal.COLUMNS)
    table = journal.record_buy(table, " tcs ", "2026-11-02", 2000.0, 5, "rotation pick")
    table = journal.record_buy(table, "INFY", "2026-11-02", 1500.0, 6)
    return table


def test_a_buy_is_recorded_as_an_open_position():
    table = _two_trades()
    assert list(table["symbol"]) == ["TCS", "INFY"]         # tidied to upper case
    assert len(journal.open_positions(table)) == 2
    assert len(journal.closed_trades(table)) == 0


def test_value_and_gain_use_the_latest_prices():
    positions = journal.open_positions(_two_trades(), {"TCS": 2200.0, "INFY": 1350.0})
    tcs = positions[positions["symbol"] == "TCS"].iloc[0]
    assert tcs["cost"] == 10_000 and tcs["value"] == 11_000 and tcs["gain"] == 1_000
    assert math.isclose(tcs["gain_%"], 10.0)


def test_selling_closes_the_position_and_gives_the_profit():
    table = journal.record_sell(_two_trades(), 0, "2026-12-01", 2300.0)
    closed = journal.closed_trades(table)
    assert list(closed["symbol"]) == ["TCS"]
    assert closed.iloc[0]["profit"] == 1_500                 # (2300 - 2000) x 5
    assert list(journal.open_positions(table)["symbol"]) == ["INFY"]


def test_totals():
    table = journal.record_sell(_two_trades(), 0, "2026-12-01", 2300.0)
    result = journal.totals(table, {"INFY": 1600.0})
    assert result["open_count"] == 1 and result["closed_count"] == 1
    assert result["invested"] == 9_000 and result["value"] == 9_600
    assert result["open_gain"] == 600 and result["closed_profit"] == 1_500


def test_bad_entries_are_refused():
    table = _two_trades()
    for bad in (lambda: journal.record_buy(table, "X", "2026-11-02", 0, 5),
                lambda: journal.record_buy(table, "X", "2026-11-02", 100, 0),
                lambda: journal.record_sell(table, 0, "2026-12-01", -5)):
        try:
            bad()
            assert False, "should have been refused"
        except ValueError:
            pass


def test_a_position_cannot_be_sold_twice():
    table = journal.record_sell(_two_trades(), 0, "2026-12-01", 2300.0)
    try:
        journal.record_sell(table, 0, "2026-12-02", 2400.0)
        assert False, "should have been refused"
    except ValueError:
        pass


def test_empty_journal_has_zero_totals():
    result = journal.totals(pd.DataFrame(columns=journal.COLUMNS))
    assert result["open_count"] == 0 and result["invested"] == 0 and result["closed_profit"] == 0
