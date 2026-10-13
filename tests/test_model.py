"""Checks the full model: factor tables, the combined score, market checks, trading."""

import numpy as np
import pandas as pd
import pytest

import config
from trading import model

DAYS = pd.bdate_range("2024-06-03", "2025-12-31")


def _stock(start, daily_growth):
    close = start * (1 + daily_growth) ** np.arange(len(DAYS))
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": 5_000_000.0}, index=DAYS)


def _nifty(growth=0.0005):
    return pd.DataFrame({"Close": 20_000 * (1 + growth) ** np.arange(len(DAYS))}, index=DAYS)


ANNUAL = pd.DataFrame(
    [(s, pd.Timestamp(day), revenue, 0.0, profit, 1000.0, debt, 100.0)
     for s, day, revenue, profit, debt in [
         ("GOOD", "2024-03-31", 1000.0, 100.0, 100.0), ("GOOD", "2025-03-31", 1300.0, 200.0, 100.0),
         ("POOR", "2024-03-31", 1000.0, 100.0, 3000.0), ("POOR", "2025-03-31", 900.0, -50.0, 3000.0),
     ]],
    columns=["symbol", "period_end", "revenue", "operating_income", "net_income", "equity",
             "total_debt", "shares"])

HOLDINGS = pd.DataFrame(
    [{"symbol": s, "quarter_end": pd.Timestamp(q), "filed_on": pd.Timestamp(f), "promoter": 50.0,
      "fii": fii, "dii": 20.0, "mutual_funds": mf, "insurance": 5.0, "public": 10.0,
      "promoters_pledged": pledged}
     for s, q, f, fii, mf, pledged in [
         ("GOOD", "2025-06-30", "2025-07-15", 10.0, 5.0, False),
         ("GOOD", "2025-09-30", "2025-10-15", 13.0, 7.0, False),
         ("POOR", "2025-06-30", "2025-07-15", 10.0, 5.0, True),
         ("POOR", "2025-09-30", "2025-10-15", 8.0, 4.0, True),
         ("GAP", "2025-03-31", "2025-04-15", 10.0, 5.0, False),
         ("GAP", "2025-09-30", "2025-10-15", 20.0, 9.0, False),
     ]])


def _model(nifty_growth=0.0005, results=None):
    stocks = {"GOOD": _stock(500.0, 0.002), "POOR": _stock(500.0, -0.001), "MID": _stock(500.0, 0.0)}
    tables = {"annual": ANNUAL, "holdings": HOLDINGS, "results": results,
              "industry": {"GOOD": "IT", "POOR": "IT", "MID": "IT"}}
    return model.Model(stocks, _nifty(nifty_growth),
                       lambda symbol, dates: pd.Series(True, index=dates), tables, {})


def test_yearly_figures_and_the_day_they_count_from():
    table = model.annual_factors(ANNUAL).set_index(["symbol", "period_end"])
    good = table.loc[("GOOD", pd.Timestamp("2025-03-31"))]
    assert round(good["sales_growth"], 2) == 0.30 and good["profit_growth"] == 1.0
    assert good["return_on_equity"] == 0.2 and good["debt_to_equity"] == 0.1
    assert good["available"] == pd.Timestamp("2025-03-31") + pd.Timedelta(days=config.REPORTING_LAG_DAYS)
    assert pd.isna(table.loc[("GOOD", pd.Timestamp("2024-03-31")), "sales_growth"])   # no year before


def test_quarter_is_compared_with_the_same_quarter_a_year_before():
    quarterly = pd.DataFrame({
        "symbol": "AAA",
        "period_end": pd.to_datetime(["2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31",
                                      "2025-06-30"]),
        "revenue": [100.0, 110.0, 120.0, 130.0, 150.0],
        "net_income": [10.0, 11.0, 12.0, 13.0, 20.0]})
    table = model.quarterly_factors(quarterly)
    last = table.iloc[-1]
    assert last["quarter_sales_growth"] == 0.5 and last["quarter_profit_growth"] == 1.0
    assert last["profit_4_quarters"] == 56.0
    assert pd.isna(table.iloc[0]["quarter_profit_growth"])


def test_ownership_change_needs_the_quarter_just_before():
    table = model.ownership_factors(HOLDINGS).set_index(["symbol", "quarter_end"])
    assert table.loc[("GOOD", pd.Timestamp("2025-09-30")), "fii_change"] == 3.0
    assert table.loc[("GOOD", pd.Timestamp("2025-09-30")), "mf_change"] == 2.0
    assert pd.isna(table.loc[("GAP", pd.Timestamp("2025-09-30")), "fii_change"])   # a quarter is missing
    assert table.loc[("POOR", pd.Timestamp("2025-09-30")), "pledged"] == 1.0


def test_unknown_factors_sit_in_the_middle():
    factors = pd.DataFrame({"momentum": [0.3, 0.1, np.nan]}, index=["A", "B", "C"])
    table = model.combine(factors)
    assert list(table.index) == ["A", "C", "B"]            # unknown ranks between best and worst
    assert (table["news"] == 50).all() and (table["flows"] == 50).all()
    assert table["score"].between(0, 100).all()


def test_the_better_company_scores_higher_in_every_known_group():
    built = _model()
    table = built.score_on(len(DAYS) - 1)
    assert table.index[0] == "GOOD" and table.index[-1] == "POOR"
    for group in ["ownership", "business", "price"]:
        assert table.loc["GOOD", group] > table.loc["POOR", group]
    assert table.loc["GOOD", "scorecard"] > table.loc["POOR", "scorecard"]


def test_results_are_not_used_before_they_are_public():
    built = _model()
    early = built.factors_on(int(DAYS.searchsorted(pd.Timestamp("2025-05-15"))))
    later = built.factors_on(int(DAYS.searchsorted(pd.Timestamp("2025-07-01"))))
    assert pd.isna(early.loc["GOOD", "sales_growth"])      # year ended 31 March, public mid-June
    assert round(later.loc["GOOD", "sales_growth"], 2) == 0.30
    before_filing = built.factors_on(int(DAYS.searchsorted(pd.Timestamp("2025-10-10"))))
    assert pd.isna(before_filing.loc["GOOD", "fii_change"])   # September filing came on 15 October


def test_a_stock_with_results_due_is_not_bought(monkeypatch):
    monkeypatch.setitem(config.MODEL_STYLES, "monthly",
                        {"check": "month", "positions": 1, "keep_rank": 2, "stop_loss": None})
    results = pd.DataFrame({"symbol": ["GOOD"], "date": [DAYS[-1] + pd.Timedelta(days=3)]})
    built = _model(results=results)
    table = built.score_on(len(DAYS) - 1)
    assert bool(table.loc["GOOD", "no_new_buy"]) and not bool(table.loc["MID", "no_new_buy"])
    plan = built.decision([], style="monthly")
    assert "GOOD" not in plan["candidates"] and plan["candidates"][0] == "MID"


def test_market_checks_and_cash_in_a_falling_market():
    rising, falling = _model(0.0005), _model(-0.0005)
    assert rising.market_score.iloc[-1] == 1.0 and bool(rising.market_ok.iloc[-1])
    assert falling.market_score.iloc[-1] == 0.0 and not bool(falling.market_ok.iloc[-1])
    result = falling.simulate(start="2025-07-01", capital=100_000, style="swing")
    assert len(result["trades"]) == 0 and result["equity"].iloc[-1] == 100_000


def test_global_markets_and_vix_join_the_checks():
    nifty = _nifty()
    markets = {"INDIAVIX": pd.Series(25.0, index=DAYS),
               "SP500": pd.Series(np.linspace(100, 200, len(DAYS)), index=DAYS),
               "USDINR": pd.Series(np.linspace(80, 200, len(DAYS)), index=DAYS)}
    last = model.market_checks(nifty, markets).iloc[-1]
    assert last[f"India VIX below {config.MODEL_VIX_MAX}"] == 0
    assert last["At least half the global markets rose over the last month"] == 1
    assert last["Rupee not falling fast"] == 0
    assert pd.isna(last["Foreign institutions net buyers over the last 5 days"])


def test_the_model_buys_the_best_and_lists_the_weakest(monkeypatch):
    monkeypatch.setitem(config.MODEL_STYLES, "monthly",
                        {"check": "month", "positions": 2, "keep_rank": 2, "stop_loss": None})
    monkeypatch.setattr(config, "MODEL_WEAKEST", 1)
    built = _model()
    result = built.simulate(start="2025-07-01", capital=100_000, style="monthly")
    assert set(result["positions"]["symbol"]) == {"GOOD", "MID"}
    assert result["equity"].iloc[-1] > 100_000
    plan = built.decision(["POOR"], style="monthly")
    assert plan["sell"] == ["POOR"] and list(plan["weakest"].index) == ["POOR"]
    assert plan["market_score"] == 1.0


def test_swing_style_checks_weekly_and_uses_a_stop_loss(monkeypatch):
    monkeypatch.setitem(config.MODEL_STYLES, "swing",
                        {"check": "week", "positions": 3, "keep_rank": 3, "stop_loss": 0.08})
    built = _model()
    result = built.simulate(start="2025-07-01", capital=90_000, style="swing")
    trades = result["trades"]
    # The first purchase is on the first trading day of the next week, not the next month.
    first = min(list(trades["entry_date"]) + list(result["positions"]["bought_on"]))
    assert str(first) == "2025-07-07"
    # POOR falls 0.1% a day, so it is sold on the stop-loss each time it is bought.
    poor = trades[trades["symbol"] == "POOR"]
    assert len(poor) > 0 and (poor["reason"] == "stop-loss").all()
    assert (poor["exit_price"] < poor["entry_price"] * 0.93).all()


def test_decision_puts_a_holding_past_its_stop_loss_on_the_sell_list(monkeypatch):
    monkeypatch.setitem(config.MODEL_STYLES, "swing",
                        {"check": "week", "positions": 2, "keep_rank": 3, "stop_loss": 0.08})
    built = _model()
    price = float(built.prepared["last_close"].iloc[-1]["GOOD"])
    safe = built.decision(["GOOD"], style="swing", buy_prices={"GOOD": price})
    assert safe["sell"] == [] and safe["keep"] == ["GOOD"]
    hit = built.decision(["GOOD"], style="swing", buy_prices={"GOOD": price * 1.2})
    assert hit["sell"] == ["GOOD"] and hit["stopped"] == ["GOOD"] and hit["keep"] == []


def test_swing_sells_when_the_trend_breaks_and_buys_only_rising_stocks(monkeypatch):
    monkeypatch.setitem(config.MODEL_STYLES, "swing",
                        {"check": "week", "positions": 3, "keep_rank": 3, "buy_rank": 3,
                         "rank_exit": False, "stop_loss": 0.5, "trend_exit": True})
    built = _model()
    result = built.simulate(start="2025-07-01", capital=90_000, style="swing")
    bought = set(result["trades"]["symbol"]) | set(result["positions"]["symbol"])
    assert bought == {"GOOD"}              # POOR falls and MID is flat: neither is above its EMA
    plan = built.decision(["POOR"], style="swing")
    assert plan["sell"] == ["POOR"] and plan["trend_broken"] == ["POOR"]
    assert plan["candidates"] == ["GOOD"]


def test_market_level_names_the_state_of_the_market():
    level, note = _model(0.0005).market_level()
    assert level == "strong" and "2 of 2" in note
    level, note = _model(-0.0005).market_level()
    assert level == "weak" and "cash" in note


def test_caution_market_buys_get_a_smaller_amount():
    built = _model()
    rules = dict(config.MODEL_STYLES["swing"])
    assert rules["caution_share"] == 0.75
    share = built.amount_share()
    assert share in (1.0, 0.75)
    assert share == (1.0 if bool(built.strong_market().iloc[-1]) else 0.75)


def test_nse_figures_give_roce_cash_conversion_and_the_filing_day():
    annual = pd.DataFrame({
        "symbol": ["A"] * 3,
        "period_end": pd.to_datetime(["2024-03-31", "2025-03-31", "2026-03-31"]),
        "revenue": [1000.0, 1100.0, 1200.0], "net_income": [100.0, 110.0, 120.0],
        "equity": [800.0, 850.0, 900.0], "total_debt": [100.0, 100.0, 300.0],
        "shares": [10.0] * 3, "cfo": [90.0, 100.0, 110.0], "pbt": [140.0, 150.0, 160.0],
        "finance_costs": [10.0, 10.0, 20.0],
        "filed": pd.to_datetime(["2024-04-20 18:00", "2025-04-21 19:00", None])})
    factors = model.annual_factors(annual).set_index("period_end")
    latest = factors.loc["2026-03-31"]
    assert latest["roce"] == pytest.approx(180.0 / 1200.0)
    assert latest["cash_conversion"] == pytest.approx(300.0 / 330.0)
    # known filing: usable from the next day; unknown: the 75-day lag
    assert factors.loc["2025-03-31", "available"] == pd.Timestamp("2025-04-22")
    assert latest["available"] == pd.Timestamp("2026-03-31") + pd.Timedelta(days=75)
