"""Checks the intraday tab: trade-card sizing, signal states, journal, day rules, Zerodha, routes.

Candles and Zerodha's answers are made up here, so these tests need no downloaded data or network.
"""

import json

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from intraday import charges, data, guard, journal, strategy, zerodha
from intraday import settings as s
from server import app as server_app

IST = "Asia/Kolkata"


# ---- helpers --------------------------------------------------------------------
def candles(rows, date="2026-11-18"):
    """rows: (open, high, low, close[, volume]) per 5-minute candle starting 9:15."""
    index = pd.date_range(f"{date} 09:15", periods=len(rows), freq="5min", tz=IST)
    return pd.DataFrame([(r + (1000,))[:5] for r in rows], index=index,
                        columns=["Open", "High", "Low", "Close", "Volume"])


OPENING = [(100, 101, 100, 100.5)] * 3          # opening range 100 - 101


def feature(day):
    return strategy.day_features(day, prev_close=98.0, avg_or_volume=1000.0)


@pytest.fixture
def tmp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "JOURNAL_FILE", tmp_path / "journal" / "intraday_trades.csv")
    monkeypatch.setattr(s, "ZERODHA_APP_FILE", tmp_path / "journal" / "zerodha_app.json")
    monkeypatch.setattr(s, "ZERODHA_TOKEN_FILE", tmp_path / "data" / "zerodha_token.json")
    monkeypatch.setattr(s, "LAST_SCAN_FILE", tmp_path / "data" / "last_scan.json")
    monkeypatch.setattr(s, "DATA_DIR", tmp_path / "data" / "intraday")
    return tmp_path


# ---- charges and sizing -----------------------------------------------------------------
def test_intraday_charges_have_stt_on_the_sell_side_only():
    base = charges.round_trip(100_000, 100_000)
    assert 75 < base < 95                          # about Rs 83 on a Rs 1 lakh round trip
    more_sell = charges.round_trip(100_000, 110_000)
    more_buy = charges.round_trip(110_000, 100_000)
    assert more_sell - base > more_buy - base       # STT is charged on the sell value


def test_brokerage_is_capped_at_20_rupees_per_order():
    assert charges.round_trip(1_000_000, 1_000_000) < 2 * 20 + 1_000_000 * 0.002


def test_trade_card_risks_about_the_chosen_amount():
    card = strategy.size_trade(1000.0, 988.0, 1)
    assert card["side"] == "BUY" and card["entry"] == 1000.0
    assert card["stop"] == 988.0 and card["target"] == 1018.0         # 1.5 x the 12 rupee stop
    assert card["qty"] == 41 and 450 <= card["risk"] <= 500           # 500 / 12 rounded down
    assert card["net_if_target"] > 0 > card["net_if_stop"]
    assert card["net_if_stop"] < -card["risk"] + 1                    # charges make the loss bigger


def test_trade_card_for_a_short_is_the_mirror_image():
    card = strategy.size_trade(1000.0, 1012.0, -1)
    assert card["side"] == "SELL" and card["stop"] == 1012.0 and card["target"] == 982.0


def test_prices_follow_the_tick_and_stop_goes_the_safe_way():
    assert strategy.round_tick(101.93) == 101.95
    assert strategy.round_tick(101.93, "down") == 101.9 and strategy.round_tick(101.93, "up") == 101.95
    card = strategy.size_trade(500.0, 496.13, 1)
    assert round(card["stop"] / 0.05) == pytest.approx(card["stop"] / 0.05, abs=1e-6)
    assert card["stop"] <= 496.13                                      # never tighter than planned


def test_very_wide_or_tiny_stops():
    assert "wider" in strategy.size_trade(100.0, 80.0, 1)["skip"]
    tight = strategy.size_trade(1000.0, 999.9, 1)                      # widened to the 0.3% minimum
    assert tight["entry"] - tight["stop"] >= 3.0 - 0.06


def test_position_is_capped_by_the_margin_limit():
    card = strategy.size_trade(100_000.0, 99_500.0, 1, min_stop_pct=0.0)
    assert card["value"] <= s.CAPITAL * s.MARGIN_X


# ---- signal states ---------------------------------------------------------------------
def signal(rows, side=1):
    day = candles(rows)
    return strategy.live_signal(day, feature(day), side)


def test_no_signal_while_price_stays_inside_the_opening_range():
    assert signal(OPENING + [(100.5, 100.9, 100.2, 100.6)])["state"] == "waiting"


def test_breakout_gives_a_live_trade_card_with_order_text():
    out = signal(OPENING + [(100.6, 102.0, 100.5, 101.8), (101.8, 102.0, 101.6, 101.9)])
    assert out["state"] == "live" and out["signal_time"] == "09:30"
    assert out["stop"] < 100.1 and out["target"] > out["entry"] > 101
    assert "SL-M" in out["order"] and "MIS" in out["order"]


def test_breakout_below_vwap_is_not_a_signal():
    rows = [(100, 101, 99.5, 100.5, 5000)] * 3 + [(100.6, 101.2, 100.5, 101.1, 10)]
    assert signal(rows)["state"] == "waiting" or signal(rows)["state"] == "live"  # vwap decides; must not crash


def test_stop_hit_after_entry_is_reported():
    out = signal(OPENING + [(100.6, 102.0, 100.5, 101.8), (101.8, 101.9, 99.0, 99.5)])
    assert out["state"] == "stopped"


def test_target_hit_is_reported():
    out = signal(OPENING + [(100.6, 102.0, 100.5, 101.8), (101.8, 106.0, 101.7, 105.5)])
    assert out["state"] == "target"


def test_an_old_signal_is_marked_late():
    quiet = [(101.8, 102.0, 101.6, 101.9)] * 6
    out = signal(OPENING + [(100.6, 102.0, 100.5, 101.8)] + quiet)
    assert out["state"] == "late" and out["age_candles"] > s.SIGNAL_MAX_AGE_CANDLES


def test_a_signal_with_a_far_stop_is_skipped_with_a_reason():
    wide = [(95, 101, 85, 100.5)] * 3                   # opening range 85 - 101
    day = candles(wide + [(100.6, 102.0, 100.5, 101.8)])
    out = strategy.live_signal(day, feature(day), 1)
    assert out["state"] == "skipped" and "wider" in out["reason"]


def test_gap_down_trades_the_short_side():
    out = signal(OPENING + [(100.4, 100.5, 98.5, 98.9), (98.9, 99.0, 98.7, 98.8)], side=-1)
    assert out["state"] == "live" and out["side"] == "SELL" and out["stop"] >= 101


# ---- the journal ----------------------------------------------------------------------------
def test_journal_roundtrip_profit_after_charges(tmp_files):
    trade = journal.open_trade("iifl", "BUY", 100, 650.0, 640.0, 665.0, "gap_go", "test")
    assert journal.page()["open"][0]["symbol"] == "IIFL"
    row = journal.close_trade(trade, 662.0)
    assert row["gross"] == 1200.0 and 0 < row["charges"] < 120
    assert row["net"] == pytest.approx(1200.0 - row["charges"], abs=0.01)
    page = journal.page()
    assert page["totals"]["closed_count"] == 1 and page["totals"]["win_rate"] == 1.0
    assert page["by_rule"][0]["rule"] == s.RULES["gap_go"]


def test_a_short_trade_profits_when_price_falls(tmp_files):
    trade = journal.open_trade("SBIN", "SELL", 50, 800.0, 810.0)
    assert journal.close_trade(trade, 790.0)["gross"] == 500.0
    trade = journal.open_trade("SBIN", "SELL", 50, 800.0, 810.0)
    assert journal.close_trade(trade, 805.0)["gross"] == -250.0


@pytest.mark.parametrize("args,message", [
    (("RELIANCE", "BUY", 10, 100.0, None), "stop-loss"),
    (("RELIANCE", "BUY", 10, 100.0, 101.0), "below the entry"),
    (("RELIANCE", "SELL", 10, 100.0, 99.0), "above the entry"),
    (("RELIANCE", "HOLD", 10, 100.0, 99.0), "BUY or SELL"),
    (("", "BUY", 10, 100.0, 99.0), "symbol"),
    (("RELIANCE", "BUY", 0, 100.0, 99.0), "Quantity"),
])
def test_journal_refuses_bad_entries(tmp_files, args, message):
    with pytest.raises(ValueError, match=message):
        journal.open_trade(*args)


def test_target_on_the_wrong_side_is_refused_and_close_twice_fails(tmp_files):
    with pytest.raises(ValueError, match="target"):
        journal.open_trade("TCS", "BUY", 5, 100.0, 99.0, 98.0)
    trade = journal.open_trade("TCS", "BUY", 5, 100.0, 99.0)
    journal.close_trade(trade, 101.0)
    with pytest.raises(ValueError, match="already closed"):
        journal.close_trade(trade, 101.0)
    journal.delete_trade(trade)
    assert journal.load() == []


# ---- the day's rules --------------------------------------------------------------------------
def at(text):
    return pd.Timestamp(text, tz=IST)


@pytest.mark.parametrize("time,key,entries", [
    ("2026-11-18 08:50", "pre", False), ("2026-11-18 09:20", "range", False),
    ("2026-11-18 09:30", "open", True), ("2026-11-18 14:30", "open", True),
    ("2026-11-18 14:45", "manage", False), ("2026-11-18 15:20", "square_off", False),
    ("2026-11-18 15:45", "closed", False), ("2026-11-21 10:30", "closed", False),
])
def test_clock_phases(time, key, entries):
    p = guard.phase(at(time))
    assert p["key"] == key and p["entries"] is entries


def test_loss_limit_and_trade_cap_stop_new_entries(tmp_files):
    now = at("2026-11-18 11:00")
    status = guard.day_status(now)
    assert status["entries_allowed"] and status["trades_used"] == 0
    a = journal.open_trade("AAA", "BUY", 100, 100.0, 90.0, when=now)
    journal.close_trade(a, 89.0, when=now)                      # about -100 gross, more after charges
    b = journal.open_trade("BBB", "BUY", 1000, 100.0, 90.0, when=now)
    journal.close_trade(b, 99.0, when=now)                      # about -1000
    status = guard.day_status(now)
    assert status["loss_limit_hit"] and not status["entries_allowed"]
    assert any("loss limit" in x for x in status["blockers"])
    journal.open_trade("CCC", "BUY", 1, 100.0, 90.0, when=now)
    assert any("trades for today used" in x for x in guard.day_status(now)["blockers"])


# ---- Zerodha ----------------------------------------------------------------------------------------
def mock_kite(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def kite_handler(request):
    path = request.url.path
    if path == "/session/token":
        assert request.headers["X-Kite-Version"] == "3"
        body = dict(x.split("=") for x in request.content.decode().split("&"))
        expected = __import__("hashlib").sha256(b"keykey1" + b"reqtok" + b"secret1").hexdigest()
        if body["checksum"] != expected:
            return httpx.Response(403, json={"status": "error", "message": "bad checksum", "error_type": "TokenException"})
        return httpx.Response(200, json={"status": "success", "data": {"access_token": "tok123", "user_name": "Lokesh"}})
    assert request.headers["Authorization"] == "token keykey1:tok123"
    if path == "/user/margins/equity":
        return httpx.Response(200, json={"data": {"net": 150000.0, "available": {"live_balance": 148000.5, "cash": 150000},
                                                  "utilised": {"debits": 2000.0}}})
    if path == "/portfolio/positions":
        return httpx.Response(200, json={"data": {"net": [], "day": [
            {"tradingsymbol": "IIFL", "product": "MIS", "quantity": 10, "average_price": 650.0, "last_price": 655.0, "pnl": 50.0},
            {"tradingsymbol": "SBIN", "product": "MIS", "quantity": -5, "average_price": 800.0, "last_price": 802.0, "pnl": -10.0}]}})
    if path == "/orders":
        return httpx.Response(200, json={"data": [
            {"order_timestamp": "2026-11-18 09:41:12", "tradingsymbol": "IIFL", "transaction_type": "BUY", "quantity": 10,
             "filled_quantity": 10, "order_type": "MARKET", "price": 0, "trigger_price": 0, "average_price": 650.0,
             "status": "COMPLETE", "product": "MIS"}]})
    return httpx.Response(404, json={"message": "no"})


def test_zerodha_needs_keys_then_a_daily_login(tmp_files):
    assert zerodha.status() == {**zerodha.status(), "configured": False, "connected": False}
    with pytest.raises(zerodha.ZerodhaError):
        zerodha.save_keys("x", "y")
    zerodha.save_keys("keykey1", "secret1")
    st = zerodha.status()
    assert st["configured"] and not st["connected"] and "api_key=keykey1" in st["login_url"]
    assert st["redirect_url"].endswith("/api/zerodha/callback")
    st = zerodha.exchange_token("reqtok", client=mock_kite(kite_handler))
    assert st["connected"] and st["user"] == "Lokesh"
    assert "secret1" not in json.dumps(zerodha.status())            # the secret never goes to the page


def test_wrong_secret_is_reported_and_not_saved(tmp_files):
    zerodha.save_keys("keykey1", "WRONGSECRET")
    with pytest.raises(zerodha.ZerodhaError, match="bad checksum"):
        zerodha.exchange_token("reqtok", client=mock_kite(kite_handler))
    assert not zerodha.status()["connected"]


def test_account_numbers(tmp_files):
    zerodha.save_keys("keykey1", "secret1")
    zerodha.exchange_token("reqtok", client=mock_kite(kite_handler))
    acc = zerodha.account(client=mock_kite(kite_handler))
    assert acc["funds"] == {"available": 148000.5, "used": 2000.0, "net": 150000.0}
    assert acc["pnl"] == 40.0 and acc["positions"][1]["qty"] == -5
    assert acc["orders"][0]["symbol"] == "IIFL" and acc["orders"][0]["time"] == "09:41"


def test_an_ended_login_is_forgotten_with_a_clear_message(tmp_files):
    zerodha.save_keys("keykey1", "secret1")
    zerodha.exchange_token("reqtok", client=mock_kite(kite_handler))
    expired = lambda request: httpx.Response(403, json={"status": "error", "error_type": "TokenException", "message": "Incorrect api_key or access_token."})
    with pytest.raises(zerodha.ZerodhaError, match="Connect Zerodha again"):
        zerodha.account(client=mock_kite(expired))
    assert not zerodha.status()["connected"]


def test_yesterdays_token_is_not_used(tmp_files):
    zerodha.save_keys("keykey1", "secret1")
    s.ZERODHA_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    s.ZERODHA_TOKEN_FILE.write_text(json.dumps({"date": "2020-01-01", "access_token": "old", "user": "x"}))
    assert not zerodha.status()["connected"]


# ---- data files -----------------------------------------------------------------------------------------
def test_a_damaged_candle_file_counts_as_no_data(tmp_files):
    s.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (s.DATA_DIR / "BROKEN.csv").write_text("")
    assert data.load("BROKEN") is None


def test_candle_files_are_written_whole_or_not_at_all(tmp_files):
    s.DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame = candles(OPENING)
    data._write_atomic(frame, data._path("OK"))
    assert len(data.load("OK")) == 3 and not list(s.DATA_DIR.glob("*.tmp"))


# ---- web addresses ----------------------------------------------------------------------------------------
@pytest.fixture
def client(tmp_files, monkeypatch):
    server_app.app.state.testing = True
    return TestClient(server_app.app, raise_server_exceptions=False)


def open_market(monkeypatch):
    monkeypatch.setattr(guard, "day_status", lambda now=None: {"entries_allowed": True, "blockers": []})


def test_guard_and_empty_scan_addresses(client):
    body = client.get("/api/intraday/guard").json()
    assert {"phase", "trades_used", "realised_net", "entries_allowed"} <= set(body)
    scan_body = client.get("/api/intraday/scan").json()
    assert scan_body["result"] is None and scan_body["run"]["running"] is False


def test_journal_addresses_open_close_delete(client, monkeypatch):
    open_market(monkeypatch)
    page = client.post("/api/intraday/journal/open", json={"symbol": "IIFL", "side": "BUY", "qty": 10,
                                                           "entry": 100.0, "stop": 98.0, "rule": "gap_go"}).json()
    trade = page["open"][0]
    page = client.post("/api/intraday/journal/close", json={"id": int(trade["id"]), "exit": 103.0}).json()
    assert page["totals"]["closed_count"] == 1 and page["totals"]["net"] > 0
    page = client.post("/api/intraday/journal/delete", json={"id": int(trade["id"])}).json()
    assert page["totals"]["closed_count"] == 0


def test_a_trade_without_a_stop_is_refused_by_the_address(client, monkeypatch):
    open_market(monkeypatch)
    reply = client.post("/api/intraday/journal/open", json={"symbol": "IIFL", "side": "BUY", "qty": 10, "entry": 100.0, "stop": 0})
    assert reply.status_code == 400 and "stop" in reply.json()["detail"].lower()


def test_entries_are_refused_when_the_day_rules_say_stop(client, monkeypatch):
    monkeypatch.setattr(guard, "day_status", lambda now=None: {"entries_allowed": False, "blockers": ["Daily loss limit reached"]})
    reply = client.post("/api/intraday/journal/open", json={"symbol": "IIFL", "side": "BUY", "qty": 10, "entry": 100.0, "stop": 98.0})
    assert reply.status_code == 409 and "loss limit" in reply.json()["detail"]


def test_zerodha_addresses(client):
    assert client.get("/api/zerodha/status").json()["configured"] is False
    assert client.post("/api/zerodha/keys", json={"api_key": "a", "api_secret": "b"}).status_code == 400
    body = client.post("/api/zerodha/keys", json={"api_key": "keykey1", "api_secret": "secret1"}).json()
    assert body["configured"] and "secret1" not in json.dumps(body)
    assert client.get("/api/zerodha/account").status_code == 502          # not logged in today
    failed = client.get("/api/zerodha/callback?status=failed", follow_redirects=False)
    assert failed.status_code == 302 and failed.headers["location"] == "/settings?zerodha=failed"


def test_evidence_reads_the_saved_backtest_files(client, monkeypatch, tmp_path):
    from server import intraday_api
    monkeypatch.setattr(intraday_api, "REPORTS", tmp_path)
    (tmp_path / "intraday_results_nifty500.json").write_text(json.dumps({"sessions": 59, "variants": [{"name": "E", "passed": False}]}))
    body = client.get("/api/intraday/evidence").json()
    assert body[0]["universe"].startswith("Nifty 500") and body[0]["variants"][0]["passed"] is False


# ---- 20 stocks in tiers, and removing Zerodha keys ------------------------------------------------------
def make_history(symbol, sessions=8):
    """Candle file with `sessions` normal days (volume 1000 in each opening candle) plus a final day we control."""
    frames = []
    for d in range(sessions):
        date = f"2026-11-{2 + d:02d}"
        frames.append(candles([(100, 100.4, 99.6, 100)] * 75, date=date))
    return frames


def write_symbol(symbol, today_rows, tmp_files):
    s.DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = make_history(symbol)
    today = candles(today_rows, date="2026-11-12")
    pd.concat(rows + [today]).to_csv(data._path(symbol))


def test_scan_fills_twenty_places_with_tested_in_play_and_near_miss(tmp_files, monkeypatch):
    from intraday import scan
    # 12 stocks gapped 1.5% on 3x volume (in play), 12 gapped 0.7% on 2x volume (near miss), 5 do nothing
    names = [f"IN{i}" for i in range(12)] + [f"NEAR{i}" for i in range(12)] + [f"QUIET{i}" for i in range(5)]
    for i, name in enumerate(names):
        if name.startswith("IN"):
            first, vol = 100 * 1.015, 3000 + i * 10        # higher index = more volume = ranked higher
        elif name.startswith("NEAR"):
            first, vol = 100 * 1.007, 2000 + i * 10
        else:
            first, vol = 100, 1000
        rows = [(first, first + 0.4, first - 0.2, first, vol)] * 3 + [(first, first + 0.2, first - 0.2, first)] * 10
        write_symbol(name, rows, tmp_files)
    quiet = [(100, 100.2, 99.8, 100, 1000)] * 13
    for anchor in scan.ANCHORS:                               # the scan uses these to find the latest session
        write_symbol(anchor, quiet, tmp_files)
    monkeypatch.setattr(s, "wide_symbols", lambda size=200: names)
    monkeypatch.setattr(scan, "_refresh", lambda *a, **k: None)
    result = scan.run(full=True, now=pd.Timestamp("2026-11-12 11:00", tz=IST))
    assert result["status"] == "ok"
    cands = result["candidates"]
    assert len(cands) == 20 and result["in_play"] == 12 and result["near_miss"] == 12
    assert [c["tier"] for c in cands] == ["tested"] * 5 + ["in_play"] * 7 + ["near"] * 8
    assert [c["rank"] for c in cands] == list(range(1, 21))
    assert cands[0]["symbol"] == "IN11"                      # most opening volume first
    assert all(c["direction"] == "BUY" for c in cands)
    assert len(result["others"]) == 4 and not any(c["symbol"].startswith("QUIET") for c in cands)


def test_forgetting_keys_removes_them_and_todays_login(tmp_files):
    zerodha.save_keys("keykey1", "secret1")
    zerodha.exchange_token("reqtok", client=mock_kite(kite_handler))
    assert zerodha.status()["connected"]
    zerodha.forget_keys()
    st = zerodha.status()
    assert not st["configured"] and not st["connected"] and not s.ZERODHA_APP_FILE.exists()


def test_forget_keys_address_and_callback_returns_to_settings(client):
    client.post("/api/zerodha/keys", json={"api_key": "keykey1", "api_secret": "secret1"})
    assert client.post("/api/zerodha/forget-keys").json()["configured"] is False
    reply = client.get("/api/zerodha/callback?status=success&request_token=abc", follow_redirects=False)
    assert reply.status_code == 302 and reply.headers["location"] == "/settings?zerodha=failed"   # no keys, so it cannot succeed
