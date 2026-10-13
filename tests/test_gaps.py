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
    assert table.loc["AAA"].tolist() == [100, 110, 95, 105, 5000]


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
