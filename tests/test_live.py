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
