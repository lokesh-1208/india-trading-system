"""Checks the live prices for the Today page: reading Yahoo's answer, the cache, market hours."""

from datetime import datetime

from trading import live


def _answer(price, previous, stamp=1791955000):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price,
                                           "chartPreviousClose": previous,
                                           "regularMarketTime": stamp}}]}}


def test_parse_reads_price_and_change_from_yahoo():
    row = live.parse(_answer(1543.2, 1459.9))
    assert row["price"] == 1543.2 and row["change_%"] == 5.71
    assert row["time"].endswith("+05:30")


def test_parse_gives_none_for_a_broken_answer():
    assert live.parse({"chart": {"result": None}}) is None
    assert live.parse(_answer(None, 100.0)) is None


def test_prices_skip_stocks_that_do_not_answer_and_keep_answers_for_a_while():
    live.clear_cache()
    asked = []

    def fetch(symbol):
        asked.append(symbol)
        return None if symbol == "NOPE" else live.parse(_answer(100.0, 99.0))

    first = live.prices(["aaa", "AAA", "NOPE", " "], fetch=fetch)
    assert set(first) == {"AAA"} and asked == ["AAA", "NOPE"]
    live.prices(["AAA"], fetch=fetch)
    assert asked == ["AAA", "NOPE"]          # AAA came from the cache
    live.clear_cache()


def test_market_hours_are_weekdays_9_15_to_3_30():
    assert live.market_open(datetime(2026, 10, 14, 9, 15))
    assert live.market_open(datetime(2026, 10, 14, 15, 30))
    assert not live.market_open(datetime(2026, 10, 14, 9, 14))
    assert not live.market_open(datetime(2026, 10, 14, 15, 31))
    assert not live.market_open(datetime(2026, 10, 17, 11, 0))   # Saturday


def test_indices_are_named_for_the_top_bar():
    live.clear_cache()
    found = live.indices(fetch=lambda ticker: live.parse(_answer(22700.0, 22721.95)))
    assert set(found) == {"Nifty 50", "India VIX", "USD/INR", "Brent"}
    live.clear_cache()


def test_previous_close_comes_from_the_daily_bars_not_yahoos_stale_figure():
    # 14 Oct 2026: Yahoo said Nifty's previous close was 22,363 (12 Oct); it was 22,722 (13 Oct).
    day = 86400
    today = 1791955000                       # 14 Oct 2026, about 11:00 India time
    answer = _answer(22627.25, 22363.3, stamp=today)
    answer["chart"]["result"][0]["timestamp"] = [today - 2 * day, today - day, today]
    answer["chart"]["result"][0]["indicators"] = {"quote": [{"close": [22363.35, 22721.95, 22629.2]}]}
    row = live.parse(answer)
    assert row["previous_close"] == 22721.95 and row["change_%"] == -0.42
