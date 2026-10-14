"""Checks the Today page lists: buy range, stop-loss, hold or sell, avoid."""

import pandas as pd

import config
from trading import today

SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "HELD", "LATE", "DOWN"]


def _plan(market_ok=True, buy=("AAA", "BBB"), keep=("HELD",), sell=(), stopped=(), broken=()):
    table = pd.DataFrame({
        "score": [90, 85, 80, 75, 70, 65, 60, 55],
        "close": [1158.0, 500, 200, 100, 50, 300, 400, 250],
        "no_new_buy": [False, False, False, False, False, False, True, False],
    }, index=SYMBOLS)
    return {
        "today": table, "market_ok": market_ok, "buy": list(buy), "keep": list(keep),
        "sell": list(sell), "stopped": list(stopped), "trend_broken": list(broken),
        "in_trend": pd.Series({s: s != "DOWN" for s in SYMBOLS}),
        "weakest": table.tail(2).iloc[::-1],
    }


def test_buy_range_is_up_to_two_percent_above_the_signal_close():
    row = today.buy_list(_plan(), 100_000).set_index("symbol").loc["AAA"]
    assert row["entry"] == 1158.0 and row["buy_up_to"] == round(1158 * 1.02, 2)
    assert row["stop_loss"] == round(1158 * (1 - config.MODEL_STYLES["swing"]["stop_loss"]), 2)


def test_shares_fit_the_money_per_stock_at_the_top_of_the_range():
    row = today.buy_list(_plan(), 100_000).set_index("symbol").loc["AAA"]
    assert row["shares"] == int(20_000 // (1158 * 1.02))


def test_picks_come_first_then_backups():
    table = today.buy_list(_plan(), 100_000)
    assert list(table["type"]) == ["Pick", "Pick", "Backup", "Backup", "Backup"]
    assert list(table["symbol"][:2]) == ["AAA", "BBB"]


def test_held_results_due_and_below_trend_are_not_on_the_buy_list():
    symbols = set(today.buy_list(_plan(), 100_000)["symbol"])
    assert not symbols & {"HELD", "LATE", "DOWN"}


def test_no_picks_in_a_weak_market():
    table = today.buy_list(_plan(market_ok=False), 100_000)
    assert (table["type"] == "Backup").all()


def test_list_stops_at_the_count():
    assert len(today.buy_list(_plan(), 100_000, count=3)) == 3


def _positions(symbol="HELD", paid=300.0, last=310.0, bought="2026-10-01"):
    return pd.DataFrame({"symbol": [symbol], "quantity": [10], "cost": [paid * 10],
                         "last_price": [last], "buy_date": [bought]})


def test_a_healthy_holding_is_held_with_its_stop_and_trend_line():
    row = today.my_stocks(_plan(), _positions(), {"HELD": 290.0}).iloc[0]
    assert row["action"] == "HOLD" and row["stop_loss"] == 276.0 and row["trend_line"] == 290.0


def test_a_stopped_holding_is_sold_with_the_reason():
    row = today.my_stocks(_plan(keep=(), sell=("HELD",), stopped=("HELD",)),
                          _positions(last=270.0), {}).iloc[0]
    assert row["action"] == "SELL" and "stop-loss" in row["reason"]


def test_a_broken_trend_is_sold_with_the_reason():
    row = today.my_stocks(_plan(keep=(), sell=("HELD",), broken=("HELD",)),
                          _positions(), {}).iloc[0]
    assert row["action"] == "SELL" and "trend broke" in row["reason"]


def test_avoid_list_is_weakest_first():
    assert list(today.avoid_list(_plan())["symbol"]) == ["DOWN", "LATE"]


def test_monday_morning_with_friday_prices_is_up_to_date():
    status, text = today.data_status("2026-10-09", pd.Timestamp("2026-10-12 11:52"))
    assert status == "fresh" and "after 4 pm" in text


def test_monday_evening_with_friday_prices_is_out_of_date():
    status, _ = today.data_status("2026-10-09", pd.Timestamp("2026-10-12 17:00"))
    assert status == "old"


def test_weekend_expects_fridays_close():
    for now in ["2026-10-10 10:00", "2026-10-11 20:00"]:
        assert today.latest_close_expected(pd.Timestamp(now)) == pd.Timestamp("2026-10-09")


def test_tuesday_morning_expects_mondays_close():
    assert today.latest_close_expected(pd.Timestamp("2026-10-13 09:00")) == pd.Timestamp("2026-10-12")


def test_a_stock_with_results_soon_is_left_out_and_the_next_moves_up():
    table = today.buy_list(_plan(), 100_000, results_due={"BBB": pd.Timestamp("2026-10-17")})
    assert "BBB" not in set(table["symbol"])
    assert list(table["symbol"][:2]) == ["AAA", "CCC"] and list(table["type"][:2]) == ["Pick"] * 2


def test_results_window_counts_from_the_buy_day():
    results = pd.DataFrame({"symbol": ["ICICIBANK", "LATER"],
                            "date": pd.to_datetime(["2026-10-17", "2026-10-30"])})
    due = today.results_soon(results, today.buy_day(pd.Timestamp("2026-10-12 12:11")))
    assert set(due) == {"ICICIBANK"}


def test_buy_day_is_today_in_market_hours_and_next_weekday_after():
    assert today.buy_day(pd.Timestamp("2026-10-12 10:00")) == pd.Timestamp("2026-10-12")
    assert today.buy_day(pd.Timestamp("2026-10-12 18:00")) == pd.Timestamp("2026-10-13")
    assert today.buy_day(pd.Timestamp("2026-10-10 10:00")) == pd.Timestamp("2026-10-12")


# ---- events ----
RANKING = pd.DataFrame({"score": [80.0, 50.0, 30.0], "close": [110.0, 200.0, 50.0]},
                       index=["UP", "MID", "LOW"])
TREND = pd.Series({"UP": True, "MID": False, "LOW": False})
CLOSES = pd.DataFrame({"UP": [100.0, 105.0, 110.0], "MID": [200.0, 200.0, 200.0],
                       "LOW": [50.0, 50.0, 50.0]},
                      index=pd.to_datetime(["2026-10-07", "2026-10-08", "2026-10-09"]))


def test_model_view_words():
    assert today.model_view(80, True).startswith("strong")
    assert today.model_view(30, True).startswith("weak")
    assert today.model_view(50, False) == "below its trend line"
    assert today.model_view(50, True) == "neutral"


def test_upcoming_results_lists_scored_stocks_in_the_window():
    results = pd.DataFrame({"symbol": ["UP", "MID", "NOTSCORED", "LOW"],
                            "date": pd.to_datetime(["2026-10-14", "2026-10-17", "2026-10-14",
                                                    "2026-11-30"])})
    table = today.upcoming_results(results, RANKING, TREND, {"MID"}, pd.Timestamp("2026-10-12"))
    assert list(table["symbol"]) == ["UP", "MID"]
    assert table.set_index("symbol").loc["MID", "you_hold"] == "yes"


def test_recent_results_show_the_move_since():
    results = pd.DataFrame({"symbol": ["UP"], "date": pd.to_datetime(["2026-10-08"])})
    row = today.recent_results(results, RANKING, TREND, CLOSES, pd.Timestamp("2026-10-09")).iloc[0]
    assert row["move_since_%"] == 10.0         # from 100 (close before results day) to 110


def test_news_after_the_close_counts_from_that_close():
    moved = today._move_since(CLOSES, "UP", pd.Timestamp("2026-10-08 17:30"))
    assert moved == 4.8                        # from 105 (8 Oct close) to 110


def test_recent_news_keeps_only_price_moving_kinds():
    table = pd.DataFrame({
        "time": pd.to_datetime(["2026-10-08 11:00", "2026-10-08 12:00", "2026-10-08 13:00"]),
        "symbol": ["UP", "UP", "MID"],
        "category": ["Orders and contracts", "Routine", "Business update"],
        "important": [True, True, False], "subject": ["Big order", "x", "y"],
        "detail": ["", "", ""], "link": ["l1", "l2", "l3"]})
    news = today.recent_news(table, RANKING, TREND, CLOSES, pd.Timestamp("2026-10-09"))
    assert list(news["what"]) == ["Big order"]
    assert news.iloc[0]["move_since_%"] == 10.0  # in market hours: from the day before


def test_short_news_drops_the_filler():
    assert today.short_news("Tech Mahindra Limited has informed the Exchange about Liquidation "
                            "of a subsidiary") == "Liquidation of a subsidiary"
    assert today.short_news("KEC Secures New T&D Orders") == "KEC Secures New T&D Orders"
    assert today.short_news("x" * 200, limit=20).endswith("…")


def test_event_cards_group_by_stock_and_put_holdings_and_strong_first():
    upcoming = pd.DataFrame([{"symbol": "UP", "results_on": pd.Timestamp("2026-10-17"),
                              "rank": 3, "score": 66, "price": 1355.0,
                              "view": "strong: model likes it", "you_hold": ""}])
    recent = pd.DataFrame(columns=["symbol", "results_on", "move_since_%", "rank", "score",
                                   "price", "view"])
    news = pd.DataFrame([
        {"time": pd.Timestamp("2026-10-09 22:00"), "symbol": "LOW", "type": "Deals",
         "what": "A has informed the Exchange about Sale", "move_since_%": None, "rank": 300,
         "score": 30, "view": "weak: model would avoid", "link": "l1"},
        {"time": pd.Timestamp("2026-10-09 22:05"), "symbol": "LOW", "type": "Deals",
         "what": "A has informed the Exchange about Sale", "move_since_%": None, "rank": 300,
         "score": 30, "view": "weak: model would avoid", "link": "l2"},
        {"time": pd.Timestamp("2026-10-09 21:00"), "symbol": "MID", "type": "Credit rating",
         "what": "Upgrade", "move_since_%": 1.0, "rank": 100, "score": 50,
         "view": "neutral", "link": "l3"},
    ])
    cards = today.event_cards(upcoming, recent, news, held={"MID"})
    assert [c["symbol"] for c in cards] == ["MID", "UP", "LOW"]
    by = {c["symbol"]: c for c in cards}
    assert by["UP"]["worth"] and by["MID"]["worth"] and not by["LOW"]["worth"]
    assert len(by["LOW"]["events"]) == 1                 # the repeated filing is shown once


def test_mid_week_the_signal_day_prices_and_limits_stay_fixed():
    plan = _plan()
    plan["signal_scores"] = plan["today"].copy()
    plan["today"] = plan["today"].assign(close=plan["today"]["close"] * 1.05)   # prices ran
    plan["last_price"] = plan["today"]["close"]
    row = today.buy_list(plan, 100_000).set_index("symbol").loc["AAA"]
    assert row["entry"] == 1158.0 and row["buy_up_to"] == round(1158 * 1.02, 2)
    assert row["last"] == round(1158 * 1.05, 2) and not row["in_range"]


def test_a_pick_still_below_its_limit_is_in_range():
    plan = _plan()
    plan["last_price"] = plan["today"]["close"] * 1.01
    assert today.buy_list(plan, 100_000).set_index("symbol").loc["AAA", "in_range"]


def test_a_pick_that_closed_below_its_trend_line_is_marked():
    plan = _plan()
    plan["signal_scores"] = plan["today"].copy()
    plan["signal_in_trend"] = pd.Series({sym: True for sym in plan["today"].index})
    plan["in_trend"] = pd.Series({sym: sym != "AAA" for sym in plan["today"].index})
    rows = today.buy_list(plan, 100_000).set_index("symbol")
    assert not rows.loc["AAA", "trend_ok"] and rows.loc["BBB", "trend_ok"]


def test_a_stock_bought_after_the_latest_close_waits_and_shows_no_gain():
    row = today.my_stocks(_plan(), _positions(bought="2026-10-13"), {"HELD": 290.0},
                          last_day=pd.Timestamp("2026-10-12")).iloc[0]
    assert row["action"] == "WAIT" and pd.isna(row["gain_%"]) and row["days_held"] == 0


def test_days_held_counts_trading_days_since_the_buy():
    row = today.my_stocks(_plan(), _positions(bought="2026-10-05"), {"HELD": 290.0},
                          last_day=pd.Timestamp("2026-10-12")).iloc[0]
    assert row["action"] == "HOLD" and row["days_held"] == 5 and row["gain_%"] == 3.3


def test_exit_now_shows_the_loss_while_the_exit_line_is_below_the_buy_price():
    row = today.my_stocks(_plan(), _positions(paid=300.0, last=310.0), {"HELD": 290.0},
                          last_day=pd.Timestamp("2026-10-12")).iloc[0]
    assert row["exit_line"] == 290.0 and row["exit_pct"] == -3.3 and row["exit_rs"] == -100
    assert row["gtt"] == 276.0                      # still the hard stop


def test_profit_is_locked_once_the_exit_line_passes_the_buy_price():
    row = today.my_stocks(_plan(), _positions(paid=300.0, last=340.0), {"HELD": 320.0},
                          last_day=pd.Timestamp("2026-10-12")).iloc[0]
    assert row["exit_pct"] == 6.7 and row["exit_rs"] == 200 and row["gtt"] == 300.0


def test_money_plan_follows_the_backtest_sizing_and_the_cash_you_have():
    # 14 Oct 2026: Rs 2 lakh, two holdings that cost 44,661 (worth 45,057), caution market
    plan = today.money_plan(200_000, 44_661, 45_057, 0.0, 5, 2, 0.75,
                            [("CHENNPETRO", 1517.45), ("KOTAKBANK", 449.82)])
    assert plan["cash"] == 155_339 and plan["per_stock"] == 30_059
    assert [(b["symbol"], b["shares"]) for b in plan["buys"]] == [("CHENNPETRO", 19), ("KOTAKBANK", 66)]
    assert plan["open_places_after"] == 1 and plan["reserve"] == 30_059
    assert "caution" in plan["note"]


def test_money_plan_never_spends_more_than_the_cash_left():
    plan = today.money_plan(60_000, 50_000, 50_000, 0.0, 5, 3, 1.0,
                            [("AAA", 1000.0), ("BBB", 1000.0)])
    assert plan["cash"] == 10_000
    assert sum(b["amount"] for b in plan["buys"]) <= 10_000


def test_money_plan_with_full_places_buys_nothing():
    plan = today.money_plan(100_000, 90_000, 95_000, 0.0, 5, 5, 1.0, [("AAA", 100.0)])
    assert plan["buys"] == [] and "full" in plan["note"]
