"""One place that knows how to refresh all the data.

Used by update_data.py (the terminal command) and by the "Update data now"
button on the dashboard, so both always do exactly the same thing.
"""

import time

import config
from trading import data, fundamentals, flows, gaps, news, shareholding, shorts

BATCH = 60


def company_data_age_days():
    """How many days old the saved company results are, or None if there are none."""
    if not config.ANNUAL_FILE.exists():
        return None
    return (time.time() - config.ANNUAL_FILE.stat().st_mtime) / 86400


def company_data_is_due():
    """Company results and shareholding change slowly, so they refresh weekly."""
    age = company_data_age_days()
    return age is None or age > config.FUNDAMENTALS_REFRESH_DAYS


def run_update(include_company_data=None, report=None):
    """Download prices, announcements and money flows, and company data when it is due.

    include_company_data: True to force it, False to skip it, None to decide by age.
    report(step, done, total) is called as the work moves along.
    Returns a short summary as a dictionary.
    """
    report = data._print_progress if report is None else report
    if include_company_data is None:
        include_company_data = company_data_is_due()

    failed_market, failed_stocks = data.update_all(report)
    # Yahoo sometimes leaves a whole trading day out; fill it from NSE's day file.
    try:
        filled = gaps.fill_missing_days(report=report)
        fill_problem = None
    except Exception as error:
        filled, fill_problem = {"days": [], "from_nse": 0, "from_hourly": 0,
                                "not_filled": 0}, str(error)
    summary = {
        "failed_markets": failed_market,
        "stocks_without_data": len(failed_stocks),
        "missing_days": filled,
        "missing_days_problem": fill_problem,
        "company_data_refreshed": False,
        "shareholding_problem": None,
        "news_added": 0,
        "news_problem": None,
        "flows_problem": None,
    }

    # Announcements and money flows are quick, so they refresh on every update.
    report("Company announcements", 0, 1)
    try:
        summary["news_added"] = news.update(list(data.load_universe()["Symbol"]))
    except Exception as error:
        summary["news_problem"] = str(error)
    try:
        flows.update()
        shorts.update_lots()         # which stocks have futures, and their lot sizes
    except Exception as error:
        summary["flows_problem"] = str(error)
    report("Company announcements", 1, 1)
    if not include_company_data:
        return summary

    missing = set(failed_stocks)
    symbols = [symbol for symbol in data.all_symbols() if symbol not in missing]
    for first in range(0, len(symbols), BATCH):
        fundamentals.update_fundamentals(symbols[first:first + BATCH])
        report("Company results", min(first + BATCH, len(symbols)), len(symbols))
    summary["company_data_refreshed"] = True

    current = list(data.load_universe()["Symbol"])
    try:
        for first in range(0, len(current), BATCH):
            shareholding.update_shareholding(current[first:first + BATCH])
            report("Shareholding", min(first + BATCH, len(current)), len(current))
    except Exception as error:
        summary["shareholding_problem"] = str(error)
    return summary
