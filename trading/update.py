"""One place that knows how to refresh all the data.

Used by update_data.py (the terminal command) and by the buttons on the
dashboard, so they always do exactly the same thing.

What a normal daily update does, and roughly how long each part takes:
  - indices (Nifty, VIX, global markets) from Yahoo           a few seconds
  - stock prices: only the new days, from NSE's day file      under a minute
    (once a week the full 10-year history comes from Yahoo     about 6 minutes)
  - company announcements, FII/DII figures, large deals       a few seconds
  - company results, only for companies that just reported   a minute or two
  - shareholding filings, once a week                         several minutes
"""

import time

import pandas as pd

import config
from trading import (data, filings, fundamentals, flows, gaps, news, pledge, premarket,
                     shareholding, shorts)

BATCH = 60


# ------------------------------------------------------------------ prices --
def full_download_age_days():
    """Days since the full price history was last downloaded, or None if never."""
    try:
        last = pd.Timestamp(config.FULL_PRICES_MARKER.read_text().strip())
    except Exception:
        return None
    return (gaps.india_today() - last.normalize()).days


def full_download_is_due():
    age = full_download_age_days()
    return age is None or age >= config.FULL_PRICES_REFRESH_DAYS


def _mark_full_download():
    config.FULL_PRICES_MARKER.parent.mkdir(parents=True, exist_ok=True)
    config.FULL_PRICES_MARKER.write_text(f"{gaps.india_today():%Y-%m-%d}\n")


def _no_data_symbols():
    """Stocks Yahoo had no prices for at the last attempt (mostly delisted)."""
    try:
        return set(config.YAHOO_NO_DATA_FILE.read_text().split())
    except Exception:
        return set()


def _save_no_data_symbols(symbols):
    config.YAHOO_NO_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.YAHOO_NO_DATA_FILE.write_text("\n".join(sorted(set(symbols))) + "\n")


def update_prices(report, full=None):
    """Indices from Yahoo; stock prices from NSE's day file, or in full from Yahoo.

    full: True for the full Yahoo history, False for the quick update, None to
    do the full one when a week has passed since the last.
    Returns (failed markets, stocks without data, summary of what was added).
    """
    failed_market = data.update_markets(report)
    try:
        gaps.fill_index_days()          # Nifty or VIX days Yahoo left out, from NSE
    except Exception:
        pass
    symbols = data.all_symbols()
    if full is None:
        full = full_download_is_due()

    if full:
        failed_stocks = data.download_stocks(symbols, report)
        _mark_full_download()
        _save_no_data_symbols(failed_stocks)
        # Yahoo sometimes leaves a whole trading day out; fill it from NSE.
        added = gaps.fill_missing_days(symbols, report)
        added["mode"] = "full"
        return failed_market, failed_stocks, added

    # Quick update. Stocks without a saved file (new in the index) need their
    # history first. Those Yahoo had nothing for last time are only retried in
    # the weekly full download.
    no_data = _no_data_symbols()
    new = [symbol for symbol in symbols if symbol not in no_data
           and not (config.PRICES_DIR / f"{symbol}.csv").exists()]
    failed_new = data.download_stocks(new, report, "New stocks") if new else []
    if failed_new:
        _save_no_data_symbols(no_data | set(failed_new))
    failed_stocks = sorted((no_data & set(symbols)) | set(failed_new))
    added = gaps.fill_missing_days(symbols, report, quick=True)
    redo = added["need_full_history"]
    if redo:
        failed_stocks += data.download_stocks(redo, report, "Stocks with a split or bonus")
        gaps.fill_missing_days(redo, report)
    added["mode"] = "quick"
    return failed_market, failed_stocks, added


# --------------------------------------------------------- company data -----
def company_data_age_days():
    """How many days old the saved company results are, or None if there are none."""
    if not config.ANNUAL_FILE.exists():
        return None
    return (time.time() - config.ANNUAL_FILE.stat().st_mtime) / 86400


def shareholding_is_due():
    """Shareholding filings come once a quarter, so a weekly check is enough."""
    if not config.SHAREHOLDING_FILE.exists():
        return True
    age = (time.time() - config.SHAREHOLDING_FILE.stat().st_mtime) / 86400
    return age > config.FUNDAMENTALS_REFRESH_DAYS


def refresh_company_data(report=None, everything=False, include_shareholding=None,
                         skip=()):
    """Company results (only for companies that are due) and shareholding.

    everything=True downloads results for every company, as before.
    include_shareholding: True/False, or None for the weekly check.
    Returns a summary dictionary.
    """
    report = data._print_progress if report is None else report
    summary = {"results_companies": 0, "results_problem": None,
               "shareholding_refreshed": False, "shareholding_problem": None}
    symbols = [symbol for symbol in data.all_symbols() if symbol not in set(skip)]

    # NSE filings first: companies that just reported (or not checked for a
    # month), then, while the first download is not finished, a few minutes of it.
    summary["filings_companies"] = 0
    try:
        due = symbols if everything else fundamentals.due_symbols(
            symbols, fetched=filings.load_checked())
        missing = set(filings.companies_missing(symbols))
        due = [symbol for symbol in due if symbol not in missing]
        if due:
            summary["filings_companies"] += filings.update_filings(due, report)
        if missing:
            current = set(data.load_universe()["Symbol"])
            order = sorted(missing, key=lambda symbol: symbol not in current)
            summary["filings_companies"] += filings.update_filings(
                order, report, max_seconds=None if everything else config.FILINGS_BACKFILL_SECONDS)
        summary["filings_left"] = len(filings.companies_missing(symbols))
    except Exception as error:
        summary["results_problem"] = f"NSE filings: {error}"
        summary["filings_left"] = None

    if not everything:
        symbols = fundamentals.due_symbols(symbols)
    summary["results_companies"] = len(symbols)
    try:
        report("Company results", 0, max(1, len(symbols)))
        for first in range(0, len(symbols), BATCH):
            fundamentals.update_fundamentals(symbols[first:first + BATCH])
            report("Company results", min(first + BATCH, len(symbols)), len(symbols))
    except Exception as error:
        summary["results_problem"] = str(error)

    if include_shareholding is None:
        include_shareholding = shareholding_is_due()
    if include_shareholding:
        current = list(data.load_universe()["Symbol"])
        try:
            for first in range(0, len(current), BATCH):
                shareholding.update_shareholding(current[first:first + BATCH])
                report("Shareholding", min(first + BATCH, len(current)), len(current))
            pledge.update(current, report)
            summary["shareholding_refreshed"] = True
        except Exception as error:
            summary["shareholding_problem"] = str(error)
    return summary


# -------------------------------------------------------------- everything --
def run_update(include_company_data=None, report=None, full_prices=None):
    """Download prices, announcements, money flows and the company data that is due.

    include_company_data: True for every company's results plus shareholding,
    False to skip company data, None for only what is due.
    full_prices: True/False, or None to decide by the weekly schedule.
    report(step, done, total) is called as the work moves along.
    Returns a short summary as a dictionary.
    """
    report = data._print_progress if report is None else report
    started = time.time()
    failed_market, failed_stocks, added = update_prices(report, full_prices)
    summary = {
        "failed_markets": failed_market,
        "stocks_without_data": len(failed_stocks),
        "prices": added,
        "news_added": 0,
        "news_problem": None,
        "flows_problem": None,
    }

    # Announcements and money flows are quick, so they refresh on every update.
    # They come before company results, which use the announcements.
    report("Company announcements", 0, 1)
    try:
        summary["news_added"] = news.update(list(data.load_universe()["Symbol"]))
        # Once: a year of older announcements, so the news reading has history.
        news.backfill(data.all_symbols(), report=report)
    except Exception as error:
        summary["news_problem"] = str(error)
    try:
        flows.update()
        shorts.update_lots()         # which stocks have futures, and their lot sizes
    except Exception as error:
        summary["flows_problem"] = str(error)
    report("Company announcements", 1, 1)

    if include_company_data is False:
        summary.update(results_companies=0, results_problem=None, filings_companies=0,
                       filings_left=None, shareholding_refreshed=False,
                       shareholding_problem=None)
    else:
        summary.update(refresh_company_data(
            report, everything=bool(include_company_data),
            include_shareholding=True if include_company_data else None,
            skip=failed_stocks))
    summary["seconds"] = round(time.time() - started)
    return summary


def describe_prices(added):
    """One plain sentence about how the stock prices were updated."""
    if added.get("mode") == "full":
        text = "Full price history downloaded from Yahoo (weekly)."
        if added["days"]:
            days = ", ".join(f"{day:%d %b}" for day in added["days"])
            text += f" Yahoo was missing {days}; filled in from NSE."
        return text
    if not added["days"]:
        return "Stock prices were already up to date."
    days = ", ".join(f"{day:%d %b}" for day in added["days"])
    text = f"Stock prices for {days} added from NSE's day file."
    if added["from_yahoo"] or added["from_hourly"]:
        text += (f" NSE's file was not out yet for some days, so "
                 f"{added['from_yahoo'] + added['from_hourly']} stock-days came from Yahoo.")
    if added["need_full_history"]:
        text += (f" {len(added['need_full_history'])} stocks had a split, bonus or big "
                 "dividend; their history was downloaded again.")
    return text


# ----------------------------------------------------------- the morning ----
def run_premarket(report=None, now=None):
    """Before the open: global markets, overnight announcements, NSE pre-open prices.

    Quick (well under a minute). Stock prices are not touched. The NSE pre-open
    prices exist from 9:08 am; before that only the overnight news and global
    markets are refreshed.
    Returns a short summary as a dictionary.
    """
    report = data._print_progress if report is None else report
    now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None) if now is None \
        else pd.Timestamp(now)
    started = time.time()
    summary = {"failed_markets": [], "news_added": 0, "news_problem": None,
               "preopen": False, "preopen_problem": None}
    summary["failed_markets"] = data.update_markets(report)
    try:
        gaps.fill_index_days()
    except Exception:
        pass
    report("Overnight announcements", 0, 1)
    try:
        summary["news_added"] = news.update(list(data.load_universe()["Symbol"]))
    except Exception as error:
        summary["news_problem"] = str(error)
    report("Overnight announcements", 1, 1)
    in_session = now.weekday() < 5 and \
        (9, 0) <= (now.hour, now.minute) <= (15, 30)
    if in_session:
        report("NSE pre-open prices", 0, 1)
        table = premarket.download_preopen()
        summary["preopen"] = table is not None
        if table is None:
            summary["preopen_problem"] = "NSE did not answer"
        report("NSE pre-open prices", 1, 1)
    summary["seconds"] = round(time.time() - started)
    return summary
