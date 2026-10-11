"""Checks the announcement collector: categories, reading NSE's answer, merging."""

import pandas as pd

from trading import news

RAW = [
    {"symbol": "TCS", "an_dt": "09-Oct-2026 18:23:45", "desc": "Bagging/Receiving of orders/contracts",
     "attchmntText": "TCS has  won an order\nworth Rs 500 crore", "attchmntFile": "https://x/a.pdf"},
    {"symbol": "TCS", "an_dt": "08-Oct-2026 10:00:00",
     "desc": "Certificate under SEBI (Depositories and Participants) Regulations, 2018",
     "attchmntText": "Certificate", "attchmntFile": "https://x/b.pdf"},
    {"symbol": "SMALLCO", "an_dt": "09-Oct-2026 09:00:00", "desc": "Credit Rating",
     "attchmntText": "", "attchmntFile": ""},
    {"symbol": "INFY", "an_dt": "not a date", "desc": "Press Release"},
]


def test_subjects_go_to_plain_categories():
    assert news.classify("Bagging/Receiving of orders/contracts") == "Orders and contracts"
    assert news.classify("Outcome of Board Meeting") == "Results"
    assert news.classify("Acquisition") == "Deals"
    assert news.classify("Credit Rating") == "Credit rating"
    assert news.classify("Resignation") == "Management change"
    assert news.classify("Dividend") == "Dividend and bonus"
    assert news.classify("Press Release") == "Business update"
    assert news.classify("Trading Window") == news.ROUTINE
    assert news.classify("Analysts/Institutional Investor Meet/Con. Call Updates") == news.ROUTINE
    assert news.classify("Something never seen") == news.OTHER


def test_rows_keep_only_our_stocks_and_valid_dates():
    table = news.to_rows(RAW, {"TCS", "INFY"})
    assert list(table["symbol"]) == ["TCS", "TCS"]
    first = table.iloc[0]
    assert first["time"] == pd.Timestamp("2026-10-09 18:23:45")
    assert first["detail"] == "TCS has won an order worth Rs 500 crore"   # spaces tidied
    assert bool(first["important"]) and not bool(table.iloc[1]["important"])


def test_an_error_page_gives_an_empty_table():
    assert len(news.to_rows({"error": "blocked"})) == 0
    assert list(news.to_rows(None).columns) == news.COLUMNS


def test_merge_drops_repeats_and_old_rows():
    table = news.to_rows(RAW)
    old = table.copy()
    old.loc[0, "time"] = pd.Timestamp("2024-01-01")       # far older than what is kept
    merged = news.merge(old, table, today="2026-10-10")
    assert len(merged) == 3                                # 3 unique, the 2024 row dropped
    assert merged["time"].is_monotonic_decreasing


def test_recent_announcements_for_one_stock():
    table = news.to_rows(RAW)
    assert len(news.for_symbol(table, "TCS", days=30, today="2026-10-10")) == 1
    assert len(news.for_symbol(table, "TCS", days=30, important_only=False,
                               today="2026-10-10")) == 2
    assert len(news.for_symbol(table, "TCS", days=30, today="2027-01-01")) == 0


def test_update_saves_and_does_not_repeat(tmp_path, monkeypatch):
    import datetime as dt
    import config
    monkeypatch.setattr(config, "ANNOUNCEMENTS_FILE", tmp_path / "news" / "a.csv")
    monkeypatch.setattr(news.nse, "session", lambda: None)
    monkeypatch.setattr(news.nse, "get_json", lambda browser, path, **params: RAW)
    today = dt.date(2026, 10, 10)
    assert news.update(["TCS"], today) == 2
    assert news.update(["TCS"], today) == 0
    saved = news.load()
    assert len(saved) == 2 and saved["important"].dtype == bool
