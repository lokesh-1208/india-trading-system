"""Checks the market movers section: heavy moves, reasons and the day's mood."""

import pandas as pd

from trading import movers

DAYS = pd.bdate_range("2026-09-01", "2026-10-13")


def stock(last_close, last_volume, last_open=None, close=100.0, volume=1000.0):
    table = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                          "Volume": volume}, index=DAYS)
    table.iloc[-1] = [last_open or last_close, last_close, last_close, last_close, last_volume]
    return table


STOCKS = {
    "UPBIG": stock(110.0, 5000, last_open=104.0),   # +10% on 5x volume, gap up 4%
    "UPQUIET": stock(108.0, 1100),                  # +8% on normal volume: drift
    "DOWNBIG": stock(94.0, 3000),                   # -6% on 3x volume
    "FLAT": stock(100.5, 4000),                     # busy but hardly moved
}
DAY, BEFORE = DAYS[-1], DAYS[-2]


def test_day_moves_measures_change_gap_and_volume():
    moves = movers.day_moves(STOCKS, list(STOCKS)).set_index("symbol")
    assert round(moves.loc["UPBIG", "change_%"], 1) == 10.0
    assert round(moves.loc["UPBIG", "gap_%"], 1) == 4.0
    assert round(moves.loc["UPBIG", "volume_x"], 1) == 5.0


def test_only_big_moves_on_heavy_volume_count():
    moves = movers.day_moves(STOCKS, list(STOCKS))
    assert movers.heavy(moves, "up")["symbol"].tolist() == ["UPBIG"]
    assert movers.heavy(moves, "down")["symbol"].tolist() == ["DOWNBIG"]


def test_news_filed_after_yesterdays_close_explains_todays_move():
    news = pd.DataFrame({
        "time": pd.to_datetime(["2026-10-12 18:05", "2026-10-12 11:00", "2026-10-13 09:30"]),
        "symbol": ["UPBIG", "UPBIG", "UPBIG"],
        "category": ["Orders and contracts", "Orders and contracts", "Routine"],
        "subject": ["Order win", "Old news", "Certificate"],
        "detail": ["Bagged a Rs 500 crore order", "Before yesterday's close", "Paper"],
        "link": ["https://example/order.pdf", "", ""],
    })
    found, link = movers.reasons("UPBIG", DAY, BEFORE, announcements=news)
    assert found == ["Orders and contracts: Bagged a Rs 500 crore order"]
    assert link == "https://example/order.pdf"


def test_deals_and_results_are_reasons_too():
    deals = pd.DataFrame({"date": [DAY], "symbol": ["DOWNBIG"], "kind": ["Block"],
                          "client": ["BIG FUND"], "side": ["Sell"],
                          "quantity": [1_000_000.0], "price": [94.0]})
    results = pd.DataFrame({"symbol": ["DOWNBIG"], "date": [DAY]})
    found, _ = movers.reasons("DOWNBIG", DAY, BEFORE, deals=deals, results=results)
    assert found == ["Results announced", "Block deal: BIG FUND sell Rs 9 cr"]


def test_move_without_any_news_is_a_crowd_move():
    moves = movers.heavy(movers.day_moves(STOCKS, list(STOCKS)), "up")
    explained = movers.explain(moves, BEFORE)
    assert explained["why"].iloc[0] == movers.NO_REASON


def test_mood_counts_heavy_moves_both_ways():
    moves = movers.day_moves(STOCKS, list(STOCKS))
    reading = movers.mood(moves)
    assert reading["rushing_in"] == 1 and reading["rushing_out"] == 1
    assert reading["label"] == "Calm"


def test_several_movers_from_one_industry_are_a_sector_move():
    table = pd.DataFrame({"symbol": ["A", "B", "C", "D"], "day": [DAY] * 4})
    industry = {"A": "IT", "B": "IT", "C": "IT", "D": "Banks"}
    explained = movers.explain(table, BEFORE, industry=industry).set_index("symbol")
    assert explained.loc["A", "why"] == ("Sector move: no company news, 3 IT stocks "
                                         "moved together")
    assert explained.loc["D", "why"] == movers.NO_REASON


def test_the_same_filing_twice_is_shown_once():
    news = pd.DataFrame({"time": pd.to_datetime(["2026-10-13 10:00", "2026-10-13 10:05"]),
                         "symbol": ["A", "A"], "category": ["Deals", "Deals"],
                         "subject": ["x", "x"], "detail": ["Same text", "Same text"],
                         "link": ["l1", "l2"]})
    found, _ = movers.reasons("A", DAY, BEFORE, announcements=news)
    assert found == ["Deals: Same text"]
