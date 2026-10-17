"""Checks the daily top-10 lists, the saved log and the week tracker."""

from types import SimpleNamespace

import pandas as pd
import pytest

from trading import picks

# Fri 9 Oct, Mon 12, Tue 13 Oct 2026
CALENDAR = pd.DatetimeIndex(["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"])
SYMBOLS = ["AAA", "BBB", "CCC", "DOWN", "LATE"]


@pytest.fixture(autouse=True)
def _closes_are_final(monkeypatch):
    """These tests are about the lists, not about NSE's day file being saved."""
    monkeypatch.setattr(picks, "close_is_final", lambda day: True)


def _built(results=None, closes=None):
    closes = closes or {s: [100.0, 100.0, 100.0, 100.0] for s in SYMBOLS}
    close_table = pd.DataFrame(closes, index=CALENDAR)

    def score_on(position):
        return pd.DataFrame({"score": [90.0, 80.0, 70.0, 60.0, 50.0],
                             "close": close_table.iloc[position][SYMBOLS].to_numpy(),
                             "no_new_buy": [False] * 5}, index=SYMBOLS)
    trend = pd.DataFrame({s: [s != "DOWN"] * 4 for s in SYMBOLS}, index=CALENDAR)
    return SimpleNamespace(calendar=CALENDAR, score_on=score_on, results=results,
                           trading={"in_trend": trend}), close_table


def test_a_list_is_named_by_the_day_it_is_for_and_monday_is_the_weekly_one():
    built, _ = _built()
    friday = picks.daily_list(built, 1)
    monday = picks.daily_list(built, 2)
    assert friday["list_day"].iloc[0] == pd.Timestamp("2026-10-12") and friday["weekly"].all()
    assert monday["list_day"].iloc[0] == pd.Timestamp("2026-10-13") and not monday["weekly"].any()


def test_below_trend_and_results_due_are_left_out():
    results = pd.DataFrame({"symbol": ["LATE"], "date": pd.to_datetime(["2026-10-15"])})
    built, _ = _built(results)
    listed = list(picks.daily_list(built, 2)["symbol"])
    assert listed == ["AAA", "BBB", "CCC"]


def test_the_list_stops_at_its_size():
    built, _ = _built()
    assert len(picks.daily_list(built, 2, count=2)) == 2


def test_lists_are_saved_once_and_never_rewritten(tmp_path):
    built, _ = _built()
    path = tmp_path / "log.csv"
    first = picks.update_log(built, path)
    assert set(first["signal_day"].dt.date.astype(str)) >= {"2026-10-09", "2026-10-12"}
    saved = path.read_text()
    picks.update_log(built, path)
    assert path.read_text() == saved


def test_tracker_counts_days_on_the_list_and_return_since_first_picked(tmp_path):
    closes = {s: [100.0, 100.0, 100.0, 100.0] for s in SYMBOLS}
    closes["AAA"] = [100.0, 100.0, 110.0, 121.0]
    built, close_table = _built(closes=closes)
    log = picks.update_log(built, tmp_path / "log.csv")
    table, days = picks.tracker(log, pd.Timestamp("2026-10-13"), close_table)
    row = table.set_index("symbol").loc["AAA"]
    assert [d.day for d in days] == [12, 13]
    assert row["days_on"] == 2 and row["on_today"]
    assert row["first_day"] == pd.Timestamp("2026-10-09")        # last week's list
    assert row["last_week"] and row["since_first_%"] == 21.0     # from 100 to 121


def test_tracker_compares_with_nifty_over_the_same_days(tmp_path):
    closes = {s: [100.0, 100.0, 100.0, 100.0] for s in SYMBOLS}
    closes["AAA"] = [100.0, 100.0, 110.0, 121.0]
    built, close_table = _built(closes=closes)
    log = picks.update_log(built, tmp_path / "log.csv")
    nifty = pd.Series([1000.0, 1000.0, 1050.0, 1100.0], index=CALENDAR)
    table, _ = picks.tracker(log, pd.Timestamp("2026-10-13"), close_table, nifty)
    row = table.set_index("symbol").loc["AAA"]
    assert row["nifty_%"] == 10.0 and row["vs_nifty"] == 11.0


def _weekly():
    return pd.DataFrame({"symbol": ["AAA", "BBB", "CCC", "DDD", "EEE"], "rank": [1, 2, 3, 4, 5],
                         "score": [90.0] * 5, "close": [100.0] * 5})


def test_weekly_status_marks_picks_backups_and_what_to_do():
    last = {"AAA": 101.0, "BBB": 105.0, "CCC": 99.0, "DDD": 100.0, "EEE": 100.0}
    trend = {"CCC": False}
    table = picks.weekly_status(_weekly(), last, trend, {"DDD"}, {"EEE"}, 3, 0.02)
    by = table.set_index("symbol")
    assert list(by["kind"]) == ["Pick", "Skipped", "Skipped", "Skipped", "Held"]
    assert list(by["status"]) == ["Buy", "Missed", "Trend broke", "Results soon", "You hold"]
    assert by.loc["AAA", "limit"] == 102.0


def test_stocks_that_cannot_be_bought_do_not_use_up_a_pick():
    # 14 Oct 2026: five of the first picks had run past their limits, so the
    # stocks further down that were still in range must become the picks.
    last = {"AAA": 110.0, "BBB": 110.0, "CCC": 100.0, "DDD": 101.0, "EEE": 99.0}
    table = picks.weekly_status(_weekly(), last, {}, set(), set(), 2, 0.02)
    by = table.set_index("symbol")
    assert list(by["status"]) == ["Missed", "Missed", "Buy", "Buy", "Buy"]
    assert list(by["kind"]) == ["Skipped", "Skipped", "Pick", "Pick", "Backup"]


def test_weekly_list_is_the_first_list_of_the_week(tmp_path):
    built, _ = _built()
    log = picks.update_log(built, tmp_path / "log.csv")
    weekly = picks.weekly_list(log, pd.Timestamp("2026-10-14"))
    assert set(weekly["list_day"]) == {pd.Timestamp("2026-10-12")}


def test_a_stock_costing_more_than_the_money_per_stock_is_skipped_without_using_a_pick():
    last = {s: 100.0 for s in ["AAA", "BBB", "CCC", "DDD", "EEE"]}
    weekly = _weekly()
    weekly.loc[0, "close"] = 20_000.0
    table = picks.weekly_status(weekly, last, {}, set(), set(), 2, 0.02, budget=15_000)
    by = table.set_index("symbol")
    assert by.loc["AAA", "status"] == "Too costly"
    assert list(table["kind"])[1:3] == ["Pick", "Pick"]


def test_list_scorecard_compares_the_weekly_picks_with_nifty(tmp_path):
    closes = {s: [100.0, 100.0, 100.0, 100.0] for s in SYMBOLS}
    closes["AAA"] = [100.0, 100.0, 110.0, 121.0]
    built, close_table = _built(closes=closes)
    log = picks.update_log(built, tmp_path / "log.csv")
    nifty = pd.Series([1000.0, 1000.0, 1050.0, 1100.0], index=CALENDAR)
    card = picks.list_scorecard(log, close_table, nifty, top=2)
    monday = card.set_index("list_day").loc[pd.Timestamp("2026-10-12")]
    assert monday["average_%"] == 10.5 and monday["nifty_%"] == 10.0 and monday["vs_nifty"] == 0.5


# ---- the sector part of the weekly list ----

SECTOR_SYMBOLS = ["F1", "F2", "F3", "F4", "I1", "I2", "I3", "I4", "P1", "P2", "WEAK"]
SECTOR_OF = {"F1": "Financial Services", "F2": "Financial Services", "F3": "Financial Services",
             "F4": "Financial Services", "I1": "Information Technology",
             "I2": "Information Technology", "I3": "Information Technology",
             "I4": "Information Technology", "P1": "Healthcare", "P2": "Healthcare",
             "WEAK": "Realty"}


def _sector_built():
    scores = [95.0, 94.0, 93.0, 92.0, 80.0, 70.0, 65.0, 60.0, 55.0, 52.0, 30.0]
    close_table = pd.DataFrame({s: [100.0] * 4 for s in SECTOR_SYMBOLS}, index=CALENDAR)

    def score_on(position):
        return pd.DataFrame({"score": scores, "close": close_table.iloc[position].to_numpy(),
                             "no_new_buy": [False] * len(scores)}, index=SECTOR_SYMBOLS)
    trend = pd.DataFrame({s: [True] * 4 for s in SECTOR_SYMBOLS}, index=CALENDAR)
    return SimpleNamespace(calendar=CALENDAR, score_on=score_on, results=None,
                           trading={"in_trend": trend}, industry=SECTOR_OF)


def test_weekly_list_adds_the_best_of_each_sector_after_the_top():
    listed = picks.daily_list(_sector_built(), 1, count=4, per_sector=3)
    top = listed[listed["group"] == "top"]
    sector = listed[listed["group"] == "sector"]
    # A sector with four in the top keeps all four.
    assert list(top["symbol"]) == ["F1", "F2", "F3", "F4"]
    # Other sectors get their best, up to 3 each; a score under the minimum is left out.
    assert list(sector["symbol"]) == ["I1", "I2", "I3", "P1", "P2"]
    assert dict(zip(listed["symbol"], listed["industry"]))["P1"] == "Healthcare"


def test_daily_lists_that_are_not_weekly_have_no_sector_part():
    listed = picks.daily_list(_sector_built(), 2, count=4, per_sector=3)
    assert set(listed["group"]) == {"top"} and len(listed) == 4


def test_sector_stocks_never_take_a_pick():
    weekly = pd.DataFrame({"symbol": ["AAA", "SEC"], "rank": [1, 30], "score": [90.0, 60.0],
                           "close": [100.0, 100.0], "group": ["top", "sector"],
                           "industry": ["X", "Y"]})
    table = picks.weekly_status(weekly, {"AAA": 110.0, "SEC": 100.0}, {}, set(), set(),
                                2, 0.02).set_index("symbol")
    assert table.loc["AAA", "status"] == "Missed"
    assert (table.loc["SEC", "status"], table.loc["SEC", "kind"]) == ("Buy", "Sector")


def test_no_list_is_saved_from_a_day_whose_final_closes_are_not_in(tmp_path):
    built, _ = _built()
    log = picks.update_log(built, tmp_path / "log.csv", final=lambda day: False)
    assert pd.Timestamp("2026-10-13") not in set(log["signal_day"])
    log = picks.update_log(built, tmp_path / "log.csv", final=lambda day: True)
    assert pd.Timestamp("2026-10-13") in set(log["signal_day"])


def test_an_old_weekly_list_gets_its_sector_part_once_and_keeps_its_top(tmp_path):
    path = tmp_path / "log.csv"
    built = _sector_built()
    old = picks.daily_list(built, 1, count=4)
    old = old[old["group"] == "top"][["list_day", "signal_day", "rank", "symbol", "score",
                                      "close", "weekly"]]
    old.to_csv(path, index=False)                   # saved before the sector part existed
    log = picks.update_log(built, path)
    monday = log[log["list_day"] == pd.Timestamp("2026-10-12")]
    assert list(monday.loc[monday["group"] == "top", "symbol"]) == ["F1", "F2", "F3", "F4"]
    assert (monday["group"] == "sector").sum() > 0
    saved = path.read_text()
    picks.update_log(built, path)
    assert path.read_text() == saved
