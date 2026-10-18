"""Checks which companies are due for a results download."""

import pandas as pd

import config
from trading import fundamentals


# ------------------------------------------------ which companies are due ---
TODAY = pd.Timestamp("2026-10-13")
QUARTERS = pd.DataFrame({"symbol": ["TCS", "INFY", "ABB"],
                         "period_end": pd.to_datetime(["2026-06-30", "2026-09-30",
                                                       "2026-06-30"])})
EVENTS = pd.DataFrame({"symbol": ["TCS", "INFY", "ABB"],
                       "date": pd.to_datetime(["2026-10-09", "2026-10-10", "2026-10-29"])})
CHECKED = {"TCS": pd.Timestamp("2026-10-10"), "INFY": pd.Timestamp("2026-10-10"),
           "ABB": pd.Timestamp("2026-10-10")}


def _due(fetched=CHECKED, quarters=QUARTERS, events=EVENTS, symbols=("TCS", "INFY", "ABB")):
    return fundamentals.due_symbols(list(symbols), today=TODAY, fetched=fetched,
                                    quarterly=quarters, events=events,
                                    annual=pd.DataFrame(columns=["symbol", "period_end"]))


def test_company_that_reported_but_has_no_new_quarter_saved_is_due():
    # TCS reported on 9 Oct; the September quarter is not saved yet
    assert _due() == ["TCS"]


def test_company_whose_new_quarter_is_saved_is_not_due():
    assert "INFY" not in _due()


def test_results_announced_for_later_do_not_count_yet():
    assert "ABB" not in _due()          # its results day (29 Oct) is still ahead


def test_never_downloaded_company_is_due():
    assert _due(fetched={}, symbols=["NEWCO"]) == ["NEWCO"]


def test_company_not_checked_for_a_month_is_due():
    old = dict(CHECKED, ABB=TODAY - pd.Timedelta(days=config.RESULTS_FULL_REFRESH_DAYS))
    assert "ABB" in _due(fetched=old)


def test_nothing_is_downloaded_twice_on_one_day():
    assert _due(fetched=dict(CHECKED, TCS=TODAY)) == []


def test_march_quarter_found_in_yearly_figures_counts_as_saved():
    events = pd.DataFrame({"symbol": ["TCS"], "date": pd.to_datetime(["2026-05-10"])})
    yearly = pd.DataFrame({"symbol": ["TCS"], "period_end": pd.to_datetime(["2026-03-31"])})
    quarters = pd.DataFrame({"symbol": ["TCS"], "period_end": pd.to_datetime(["2025-12-31"])})
    due = fundamentals.due_symbols(["TCS"], today=pd.Timestamp("2026-05-20"),
                                   fetched={"TCS": pd.Timestamp("2026-05-15")},
                                   quarterly=quarters, events=events, annual=yearly)
    assert due == []


def test_nse_results_filings_count_as_results_days():
    announcements = pd.DataFrame({"symbol": ["TCS", "ABB"], "category": ["Results", "Deals"],
                                  "time": pd.to_datetime(["2026-10-09 18:30", "2026-10-09 10:00"])})
    events = fundamentals.results_events(None, announcements)
    assert events["symbol"].tolist() == ["TCS"]
    assert events["date"].iloc[0] == pd.Timestamp("2026-10-09")
