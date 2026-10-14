"""Checks the web app's server: its addresses, errors and background updates.

The pages' contents are replaced by small stand-ins, so these tests need no data.
"""

import time

import pandas as pd  # noqa: F401  (load pandas before FastAPI)
import pytest
from fastapi.testclient import TestClient

from server import app as server_app
from server import jobs, views


@pytest.fixture
def client(monkeypatch):
    server_app.app.state.testing = True
    monkeypatch.setattr(views, "status", lambda: {"prices_to": "2026-10-13", "strip": []})
    monkeypatch.setattr(views, "today_page", lambda money=None: {"headline": "Buy 1", "money": money})
    monkeypatch.setattr(views, "stock_page", lambda symbol: None if symbol == "NOPE" else {"symbol": symbol})
    monkeypatch.setattr(views, "stock_prices", lambda symbol, days=None: {"symbol": symbol, "days": days})
    return TestClient(server_app.app, raise_server_exceptions=False)


def test_status_includes_the_update_job(client):
    body = client.get("/api/status").json()
    assert body["prices_to"] == "2026-10-13" and "running" in body["job"]


def test_today_passes_the_money_on(client):
    assert client.get("/api/today?money=50000").json() == {"headline": "Buy 1", "money": 50000.0}


def test_stock_symbols_are_upper_cased_and_unknown_ones_are_404(client):
    assert client.get("/api/stocks/tcs").json() == {"symbol": "TCS"}
    assert client.get("/api/stocks/nope").status_code == 404
    assert client.get("/api/stocks/tcs/prices?days=22").json() == {"symbol": "TCS", "days": 22}


def test_a_problem_in_a_page_comes_back_as_a_readable_error(client, monkeypatch):
    def broken():
        raise KeyError("boom")
    monkeypatch.setattr(views, "news_page", broken)
    answer = client.get("/api/news")
    assert answer.status_code == 500 and "boom" in answer.json()["detail"]


def test_a_bad_trade_is_refused_with_the_reason(client, monkeypatch):
    def refuse(*args):
        raise ValueError("Price and quantity must be above zero.")
    monkeypatch.setattr(views, "record_buy", refuse)
    answer = client.post("/api/trades/buy", json={"symbol": "tcs", "date": "2026-10-14",
                                                   "price": 0, "quantity": 1})
    assert answer.status_code == 400 and "above zero" in answer.json()["detail"]


def test_unknown_update_kind_is_refused(client):
    assert client.post("/api/jobs", json={"kind": "everything"}).status_code == 400


def test_an_update_runs_in_the_background_and_reports_progress(client, monkeypatch):
    def work(report):
        report("Markets", 5, 11)
        time.sleep(0.2)
        return {"seconds": 3, "news_added": 2}
    monkeypatch.setitem(jobs.KINDS, "daily", ("Update data", work))
    monkeypatch.setattr(jobs, "JOBS", jobs.Jobs())
    monkeypatch.setattr(server_app, "JOBS", jobs.JOBS)
    started = client.post("/api/jobs", json={"kind": "daily"}).json()
    assert started["running"] and started["label"] == "Update data"
    assert client.post("/api/jobs", json={"kind": "daily"}).status_code == 409   # one at a time
    for _ in range(50):
        state = client.get("/api/jobs").json()
        if not state["running"]:
            break
        time.sleep(0.05)
    assert not state["running"] and state["message"] == "Done in 3 s. 2 new announcements."


def test_the_page_is_served_for_any_other_address(client, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>Kasauti</html>")
    monkeypatch.setattr(server_app, "PAGE", tmp_path)
    assert "Kasauti" in client.get("/stocks/TCS").text


def test_clean_turns_numpy_and_missing_values_into_json():
    import numpy as np
    cleaned = views.clean({"a": np.float64(1.5), "b": float("nan"), "c": pd.Timestamp("2026-10-13"),
                           "d": [np.int64(3), np.bool_(True)]})
    assert cleaned == {"a": 1.5, "b": None, "c": "2026-10-13T00:00:00", "d": [3, True]}


def test_list_summary_says_why_the_buy_section_is_short():
    table = pd.DataFrame({"status": ["You hold", "You hold", "Missed", "Missed", "Missed",
                                     "Trend broke", "Buy", "Buy"]})
    text = views.list_summary(table, 3, True)
    assert text.startswith("This week's list has 8 stocks: you already hold 2; 3 ran more")
    assert "1 closed below the 20-day average" in text
    assert text.endswith("2 can be bought today, with room for 3 new stocks.")
    assert views.list_summary(table, 3, False).endswith("nothing is bought today.")
    assert views.list_summary(pd.DataFrame({"status": ["Missed"]}), 3, True).endswith(
        "None of them can be bought today.")


def test_missing_flow_days_lists_trading_days_the_update_missed():
    days = pd.to_datetime(["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"])
    missed = views.missing_flow_days(["2026-10-09", "2026-10-13"], days)
    assert missed == [pd.Timestamp("2026-10-12")]       # 8 Oct is before the first saved day
    assert views.missing_flow_days([], days) == []


def test_next_list_is_the_coming_monday():
    assert views.next_list_day("2026-10-12") == pd.Timestamp("2026-10-19")
    assert views.next_list_day("2026-10-16") == pd.Timestamp("2026-10-19")
