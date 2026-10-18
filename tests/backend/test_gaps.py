"""Checks the filling of trading days that Yahoo left out."""

import pandas as pd
import pytest

from trading import gaps

DAYS = list(pd.to_datetime(["2026-10-07", "2026-10-08", "2026-10-09",
                            "2026-10-12", "2026-10-13"]))

BHAVCOPY = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4
2026-10-12,2026-10-12,CM,NSE,STK,1,X,AAA,EQ,,,,,AAA LTD,100,110,95,105,105,99,,105,,,5000,1,1,F1,1,,,,,
2026-10-12,2026-10-12,CM,NSE,STK,2,X,BBB,BE,,,,,BBB LTD,50,52,49,51,51,50,,51,,,700,1,1,F1,1,,,,,
2026-10-12,2026-10-12,CM,NSE,STK,3,X,SGB1,GB,,,,,GOLD BOND,9000,9100,8900,9050,9050,9000,,9050,,,10,1,1,F1,1,,,,,
"""


def prices(dates, close=100.0):
    index = pd.to_datetime(dates)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": 1000.0}, index=index).rename_axis("Date")


def test_finds_the_day_in_the_middle_that_is_missing():
    table = prices(["2026-10-01", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-13"])
    assert gaps.missing_days(table, DAYS) == [pd.Timestamp("2026-10-12")]


def test_stock_that_stopped_trading_before_the_window_is_left_alone():
    table = prices(["2026-09-01", "2026-09-02"])
    assert gaps.missing_days(table, DAYS) == []


def test_days_before_a_new_listing_are_not_missing():
    table = prices(["2026-10-12", "2026-10-13"])
    assert gaps.missing_days(table, DAYS) == []


def test_bhavcopy_keeps_only_normal_shares():
    table = gaps.parse_bhavcopy(BHAVCOPY)
    assert sorted(table.index) == ["AAA", "BBB"]           # the gold bond is left out
    assert table.loc["AAA"].tolist() == [100, 110, 95, 105, 5000, 99]   # last: previous close


def test_scaling_factor_is_yahoo_price_over_nse_price():
    table = prices(["2026-10-09", "2026-10-13"], close=98.0)
    nse_day = pd.DataFrame({"Close": [100.0]}, index=["AAA"])
    factor = gaps.scaling_factor("AAA", table, {pd.Timestamp("2026-10-13"): nse_day},
                                 pd.Timestamp("2026-10-12"))
    assert factor == pytest.approx(0.98)


def test_scaling_factor_is_one_without_a_day_to_compare():
    table = prices(["2026-10-09"])
    assert gaps.scaling_factor("AAA", table, {}, pd.Timestamp("2026-10-12")) == 1.0


def test_odd_scaling_factor_is_refused():
    table = prices(["2026-10-13"], close=10.0)            # looks like a 1:10 split
    nse_day = pd.DataFrame({"Close": [100.0]}, index=["AAA"])
    assert gaps.scaling_factor("AAA", table, {pd.Timestamp("2026-10-13"): nse_day},
                               pd.Timestamp("2026-10-12")) is None


def test_hourly_bars_add_up_to_one_day():
    index = pd.DatetimeIndex(["2026-10-12 09:15", "2026-10-12 10:15", "2026-10-12 15:15"],
                             tz="Asia/Kolkata")
    hourly = pd.DataFrame({"Open": [10, 11, 12], "High": [11, 14, 13], "Low": [9, 10, 8],
                           "Close": [11, 12, 12.5], "Volume": [100, 200, 300]}, index=index)
    daily = gaps.daily_from_hourly(hourly)
    assert list(daily.index) == [pd.Timestamp("2026-10-12")]
    assert daily.iloc[0].tolist() == [10, 14, 8, 12.5, 600]


def test_new_row_goes_in_date_order():
    table = prices(["2026-10-09", "2026-10-13"])
    bar = pd.Series({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0})
    combined = gaps.add_rows(table, {pd.Timestamp("2026-10-12"): bar})
    assert list(combined.index.strftime("%d")) == ["09", "12", "13"]
    assert combined.loc["2026-10-12", "Close"] == 1.5


def test_quick_update_takes_the_last_two_days_again():
    table = prices(["2026-10-01", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12"])
    wanted = gaps.missing_days(table, DAYS, refresh_last=2)
    assert wanted == [pd.Timestamp("2026-10-12"), pd.Timestamp("2026-10-13")]


def test_saved_bar_is_replaced_by_the_new_one():
    table = prices(["2026-10-09", "2026-10-12"])
    bar = pd.Series({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0})
    combined = gaps.add_rows(table, {pd.Timestamp("2026-10-12"): bar})
    assert len(combined) == 2 and combined.loc["2026-10-12", "Close"] == 1.5


def _nse_day(prev_close):
    return pd.DataFrame({"Close": [50.0], "PrevClose": [prev_close]}, index=["AAA"])


def test_split_is_noticed_from_nse_previous_close():
    table = prices(["2026-10-08", "2026-10-09"], close=100.0)
    # a 1:2 split: NSE now shows yesterday's close as 50
    assert gaps.had_corporate_action(table, pd.Timestamp("2026-10-12"), _nse_day(50.0), "AAA")


def test_normal_day_is_not_a_corporate_action():
    table = prices(["2026-10-08", "2026-10-09"], close=100.0)
    assert not gaps.had_corporate_action(table, pd.Timestamp("2026-10-12"),
                                         _nse_day(100.0), "AAA")


def test_without_nse_file_no_corporate_action_is_assumed():
    table = prices(["2026-10-09"], close=100.0)
    assert not gaps.had_corporate_action(table, pd.Timestamp("2026-10-12"), None, "AAA")


def test_same_bar_is_recognised_so_the_file_is_not_rewritten():
    table = prices(["2026-10-12"], close=100.0)
    same = pd.Series({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0,
                      "Volume": 1000.0})
    assert gaps.same_bar(table, pd.Timestamp("2026-10-12"), same)
    assert not gaps.same_bar(table, pd.Timestamp("2026-10-12"), same.replace(100.0, 101.0))
    assert not gaps.same_bar(table, pd.Timestamp("2026-10-13"), same)


def test_nse_index_file_gives_nifty_and_vix():
    text = ("Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,"
            "Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,"
            "Div Yield\n"
            "Nifty 50,13-10-2026,22364.15,22721.95,22288.45,22721.95,358.6,1.6,1,1,1,1,1\n"
            "India VIX,13-10-2026,15.25,15.35,13.94,14.12,-1.13,-7.43,-,-,-,-,-\n")
    values = gaps.parse_index_file(text)
    assert values["Nifty 50"] == (22364.15, 22721.95, 22288.45, 22721.95)
    assert values["India VIX"][3] == 14.12
