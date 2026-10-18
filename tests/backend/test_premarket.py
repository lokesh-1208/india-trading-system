"""Checks the before-the-open section: global moves, pre-open prices and the stock list."""

import pandas as pd

from trading import premarket


def _market(changes):
    """Two closes per market so the last bar shows the given % change."""
    days = pd.to_datetime(["2026-10-12", "2026-10-13"])
    return {name: pd.DataFrame({"Close": [100.0, 100.0 + change]}, index=days)
            for name, change in changes.items()}


def test_us_fall_and_crude_jump_mean_a_weak_start():
    moves = premarket.global_moves(_market({"SP500": -2.0, "SP500_FUTURES": -1.0,
                                            "BRENT": 4.0}))
    guess, reasons = premarket.opening_guess(moves)
    assert guess == "Weak start likely"
    assert "S&P 500 (US) -2.0%" in reasons and "Brent crude +4.0%" in reasons


def test_quiet_night_means_a_flat_start():
    moves = premarket.global_moves(_market({"SP500": 0.1, "NIKKEI225": -0.2}))
    assert premarket.opening_guess(moves)[0] == "Flat start likely"


def test_big_nasdaq_move_points_to_it_stocks():
    moves = premarket.global_moves(_market({"NASDAQ": 2.5}))
    industry = {"TCS": "Information Technology", "HDFCBANK": "Financial Services"}
    effects = premarket.sector_effects(moves, industry)
    assert effects["symbol"].tolist() == ["TCS"] and effects.iloc[0]["direction"] == 1


def test_crude_jump_is_bad_for_oil_marketers():
    moves = premarket.global_moves(_market({"BRENT": 5.0}))
    effects = premarket.sector_effects(moves, {"BPCL": "Oil", "ONGC": "Oil"}).set_index("symbol")
    assert effects.loc["BPCL", "direction"] == -1 and effects.loc["ONGC", "direction"] == 1


PREOPEN = {"data": [
    {"metadata": {"symbol": "AAA", "previousClose": 100, "iep": 105, "pChange": 5.0,
                  "finalQuantity": 1000},
     "detail": {"preOpenMarket": {"lastUpdateTime": "13-Oct-2026 09:07:58"}}},
    {"metadata": {"symbol": "BBB", "previousClose": 100, "iep": 97, "pChange": -3.0,
                  "finalQuantity": 500},
     "detail": {"preOpenMarket": {"lastUpdateTime": "13-Oct-2026 09:07:58"}}},
    {"metadata": {"symbol": "CCC", "previousClose": 100, "iep": 101, "pChange": 1.0,
                  "finalQuantity": 500},
     "detail": {"preOpenMarket": {"lastUpdateTime": "13-Oct-2026 09:07:58"}}},
]}


def test_preopen_movers_need_at_least_two_percent():
    table = premarket.parse_preopen(PREOPEN)
    assert premarket.preopen_movers(table, ["AAA", "BBB", "CCC"], "up")["symbol"].tolist() == ["AAA"]
    assert premarket.preopen_movers(table, ["AAA", "BBB", "CCC"], "down")["symbol"].tolist() == ["BBB"]


def test_stock_list_puts_preopen_and_news_together():
    reading = pd.DataFrame({"symbol": ["AAA", "DDD"], "lean": [1, -2],
                            "label": ["Order or contract win", "Fraud, default or insolvency"],
                            "what": ["big order", "default"], "link": ["l1", "l2"]})
    table = premarket.parse_preopen(PREOPEN)
    up = premarket.preopen_movers(table, ["AAA", "BBB"], "up")
    down = premarket.preopen_movers(table, ["AAA", "BBB"], "down")
    sectors = pd.DataFrame(columns=["symbol", "direction", "why"])
    likely = premarket.stock_list(reading, sectors, up, down).set_index("symbol")
    assert likely.loc["AAA", "direction"] == 1 and likely.loc["AAA", "open_%"] == 5.0
    assert likely.loc["AAA", "strength"] == 4            # pre-open 3 + good news 1
    assert likely.loc["DDD", "direction"] == -1 and likely.loc["BBB", "direction"] == -1


def test_last_close_time_before_the_open_is_yesterday():
    nifty = pd.DatetimeIndex(pd.to_datetime(["2026-10-09", "2026-10-12", "2026-10-13"]))
    morning = premarket.last_close_time(nifty, pd.Timestamp("2026-10-13 08:45"))
    evening = premarket.last_close_time(nifty, pd.Timestamp("2026-10-13 19:00"))
    assert morning == pd.Timestamp("2026-10-12 15:30")
    assert evening == pd.Timestamp("2026-10-13 15:30")
