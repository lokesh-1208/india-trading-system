"""Checks the week's watchlist (buy on any day) and the journal's source tag (5 Nov 2026)."""

import pandas as pd

import config
from trading import journal, picks


def _row(list_day, signal_day, rank, symbol, close=100.0):
    weekly = pd.Timestamp(list_day).isocalendar()[:2] != pd.Timestamp(signal_day).isocalendar()[:2]
    return {"list_day": pd.Timestamp(list_day), "signal_day": pd.Timestamp(signal_day),
            "rank": rank, "symbol": symbol, "score": 70.0 - rank, "close": close,
            "weekly": weekly, "group": "top", "industry": ""}


def _log():
    rows = [
        # week 1: Monday 12 Oct list from the Friday 9 Oct close, then Tuesday adds NEW1
        _row("2026-10-12", "2026-10-09", 1, "AAA", 100.0),
        _row("2026-10-12", "2026-10-09", 2, "BBB", 50.0),
        _row("2026-10-13", "2026-10-12", 1, "AAA", 101.0),
        _row("2026-10-13", "2026-10-12", 2, "NEW1", 200.0),
        # week 2: Monday 19 Oct list from the Friday 16 Oct close, Wednesday adds NEW2
        _row("2026-10-19", "2026-10-16", 1, "CCC", 30.0),
        _row("2026-10-20", "2026-10-19", 1, "CCC", 31.0),
        _row("2026-10-21", "2026-10-20", 1, "NEW2", 10.0),
    ]
    return pd.DataFrame(rows, columns=picks.COLUMNS)


def _rank_on(order):
    return lambda day: order


def test_the_watchlist_grows_through_the_week_and_shows_each_name_once():
    log = _log()
    week1 = picks.watchlist(log[log["list_day"] <= "2026-10-13"], "2026-10-13",
                            _rank_on(["AAA", "BBB", "NEW1"]))
    assert list(week1["symbol"]) == ["AAA", "BBB", "NEW1"]
    assert week1.set_index("symbol").loc["NEW1", "added"] == pd.Timestamp("2026-10-13")
    assert week1.set_index("symbol").loc["AAA", "days_on"] == 2


def test_last_weeks_best_carry_over_and_count_their_weeks(monkeypatch):
    monkeypatch.setattr(picks, "CARRY_OVER", 2)
    # On the 16 Oct close NEW1 ranks first and AAA second; BBB falls out of the carry-over.
    found = picks.watchlist(_log(), "2026-10-21", _rank_on(["NEW1", "AAA", "CCC", "BBB"]))
    table = found.set_index("symbol")
    assert list(found["symbol"]) == ["NEW1", "AAA", "CCC", "NEW2"]
    assert "BBB" not in table.index
    assert bool(table.loc["NEW1", "carried"]) and table.loc["NEW1", "weeks_on"] == 2
    assert table.loc["AAA", "first_day"] == pd.Timestamp("2026-10-12")    # run began week 1
    assert table.loc["AAA", "first_close"] == 100.0
    assert table.loc["CCC", "weeks_on"] == 1 and not bool(table.loc["CCC", "carried"])
    assert table.loc["NEW2", "added"] == pd.Timestamp("2026-10-21")


def test_only_the_monday_top_ten_are_tested_picks():
    table = picks.watchlist(_log(), "2026-10-21", _rank_on(["NEW1", "AAA", "CCC"])) \
        .set_index("symbol")
    assert bool(table.loc["CCC", "tested"])          # on Monday 19 Oct's list
    assert not bool(table.loc["NEW2", "tested"])     # joined on Wednesday: your choice
    assert not bool(table.loc["NEW1", "tested"])     # carried over, not on Monday's list


def test_an_empty_log_gives_an_empty_watchlist():
    empty = pd.DataFrame(columns=picks.COLUMNS)
    assert len(picks.watchlist(empty, None, _rank_on([]))) == 0


def test_daily_limits_come_from_the_latest_close():
    table = pd.DataFrame({"symbol": ["AAA"], "rank": [1], "score": [70.0], "close": [110.0],
                          "group": ["top"], "industry": [""]})
    status = picks.weekly_status(table, {"AAA": 110.0}, {"AAA": True}, set(), set(), 2,
                                 config.MODEL_STYLES["swing"]["max_gap"])
    assert status.loc[0, "status"] == "Buy"
    assert round(status.loc[0, "limit"], 2) == round(110.0 * 1.02, 2)


def test_a_buy_keeps_where_the_idea_came_from_and_old_rows_are_untagged():
    table = journal.record_buy(pd.DataFrame(columns=journal.COLUMNS), "TCS", "2026-11-05",
                               2500.0, 4, source="tested")
    table = journal.record_buy(table, "INFY", "2026-11-05", 1500.0, 6, source="own")
    table = journal.record_buy(table, "OLD", "2026-11-05", 100.0, 1)
    assert list(table["source"]) == ["tested", "own", ""]
    try:
        journal.record_buy(table, "X", "2026-11-05", 100.0, 1, source="tip")
        assert False, "an unknown source should be refused"
    except ValueError:
        pass


def test_closed_trades_are_summed_by_source():
    table = pd.DataFrame(columns=journal.COLUMNS)
    table = journal.record_buy(table, "AAA", "2026-11-02", 100.0, 10, source="tested")
    table = journal.record_buy(table, "BBB", "2026-11-02", 100.0, 10, source="own")
    table = journal.record_sell(table, 0, "2026-11-05", 110.0)
    table = journal.record_sell(table, 1, "2026-11-05", 90.0)
    rows = {row["source"]: row for row in journal.by_source(table)}
    assert rows["tested"]["won"] == 1 and rows["tested"]["net_profit"] > 0
    assert rows["own"]["won"] == 0 and rows["own"]["net_profit"] < 0
    assert "watchlist" not in rows


def test_a_saved_journal_without_the_source_column_still_loads(tmp_path, monkeypatch):
    path = tmp_path / "real_trades.csv"
    path.write_text("symbol,buy_date,buy_price,quantity,sell_date,sell_price,note\n"
                    "CUB,2026-10-13,233.22,85,2026-10-16,225.15,old row\n")
    monkeypatch.setattr(config, "REAL_TRADES_FILE", path)
    table = journal.load()
    assert list(table.columns) == journal.COLUMNS and table.loc[0, "source"] == ""
