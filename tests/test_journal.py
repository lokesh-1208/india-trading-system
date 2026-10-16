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


def test_closed_trades_show_profit_after_charges_and_the_tax_estimate():
    table = journal.record_buy(pd.DataFrame(columns=journal.COLUMNS), "ABC", "2026-10-01", 100.0, 100)
    table = journal.record_sell(table, 0, "2026-10-10", 110.0)
    closed = journal.closed_trades(table).iloc[0]
    assert closed["profit"] == 1000.0 and 0 < closed["charges"] < 50
    totals = journal.totals(table)
    assert totals["closed_net"] == closed["net_profit"]
    assert round(totals["tax_estimate"], 2) == round(closed["net_profit"] * 0.20, 2)


def test_a_position_bought_after_the_last_close_is_valued_at_its_cost():
    table = journal.record_buy(pd.DataFrame(columns=journal.COLUMNS), "ABC", "2026-10-13", 100.0, 10)
    positions = journal.open_positions(table, {"ABC": 90.0}, last_day="2026-10-12")
    assert positions.iloc[0]["last_price"] == 100.0


def test_a_sell_saves_when_the_file_has_no_sells_yet(tmp_path, monkeypatch):
    # An all-empty sell_date column is read back as numbers; a sell must still save.
    import config
    monkeypatch.setattr(config, "REAL_TRADES_FILE", tmp_path / "real_trades.csv")
    journal.save(_two_trades())
    table = journal.record_sell(journal.load(), 0, "2026-10-16", 2100.0)
    journal.save(table)
    assert journal.load().loc[0, "sell_date"] == "2026-10-16"


def test_a_mistaken_buy_can_be_deleted():
    table = journal.delete_row(_two_trades(), 0)
    assert list(table["symbol"]) == ["INFY"] and list(table.index) == [0]


def test_a_mistaken_sell_can_be_undone():
    table = journal.undo_sell(journal.record_sell(_two_trades(), 0, "2026-12-01", 2300.0), 0)
    assert len(journal.closed_trades(table)) == 0
    assert list(journal.open_positions(table)["symbol"]) == ["TCS", "INFY"]


def test_undo_and_delete_refuse_bad_rows():
    import pytest
    with pytest.raises(ValueError):
        journal.undo_sell(_two_trades(), 0)                  # not sold
    with pytest.raises(ValueError):
        journal.delete_row(_two_trades(), 9)
