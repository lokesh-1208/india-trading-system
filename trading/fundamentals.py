"""Company fundamentals: sales, profit, debt, return on equity, results dates.

The price rules say WHEN a stock is moving. These numbers say WHAT KIND of
business is behind the chart. They are used in two ways:
  - quality filter: weak businesses are removed from the shortlist
  - results block: no new trade just before a company announces results
"""

import zlib
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import config
from trading import data

ANNUAL_COLUMNS = [
    "symbol", "period_end", "revenue", "operating_income", "net_income",
    "equity", "total_debt", "shares",
]
QUARTERLY_COLUMNS = ["symbol", "period_end", "revenue", "net_income"]
RESULTS_COLUMNS = ["symbol", "date"]
FETCHED_COLUMNS = ["symbol", "fetched"]
DIVIDEND_COLUMNS = ["symbol", "date", "amount"]


# ------------------------------------------------------------- download -----
def _value(statement, row_names, column):
    """First available value among several possible row names, else None."""
    for name in row_names:
        if name in statement.index:
            value = statement.at[name, column]
            if pd.notna(value):
                return float(value)
    return None


def fetch_symbol(symbol):
    """Download one company's statements from Yahoo Finance.

    Returns (annual rows, quarterly rows, results-date rows, dividend rows).
    Any part Yahoo does not have comes back as an empty list.
    """
    import yfinance as yf  # imported here so the rest works without internet

    ticker = yf.Ticker(data.yahoo_ticker(symbol))
    annual, quarterly, results, dividends = [], [], [], []

    try:
        income, balance = ticker.income_stmt, ticker.balance_sheet
        for period in income.columns:
            row = {
                "symbol": symbol,
                "period_end": pd.Timestamp(period).date(),
                "revenue": _value(income, ["Total Revenue", "Operating Revenue"], period),
                "operating_income": _value(income, ["Operating Income"], period),
                "net_income": _value(
                    income, ["Net Income Common Stockholders", "Net Income"], period
                ),
                "equity": None, "total_debt": None, "shares": None,
            }
            if period in balance.columns:
                row["equity"] = _value(
                    balance, ["Common Stock Equity", "Stockholders Equity"], period
                )
                row["total_debt"] = _value(balance, ["Total Debt"], period)
                row["shares"] = _value(
                    balance, ["Ordinary Shares Number", "Share Issued"], period
                )
            if row["revenue"] is not None or row["net_income"] is not None:
                annual.append(row)
    except Exception:
        pass

    try:
        income = ticker.quarterly_income_stmt
        for period in income.columns:
            row = {
                "symbol": symbol,
                "period_end": pd.Timestamp(period).date(),
                "revenue": _value(income, ["Total Revenue", "Operating Revenue"], period),
                "net_income": _value(
                    income, ["Net Income Common Stockholders", "Net Income"], period
                ),
            }
            if row["revenue"] is not None or row["net_income"] is not None:
                quarterly.append(row)
    except Exception:
        pass

    try:
        dates = ticker.get_earnings_dates(limit=24)
        if dates is not None:
            for moment in dates.index:
                results.append({"symbol": symbol, "date": pd.Timestamp(moment).date()})
    except Exception:
        pass

    try:
        for moment, amount in ticker.dividends.items():
            dividends.append({
                "symbol": symbol,
                "date": pd.Timestamp(moment).date(),
                "amount": float(amount),
            })
    except Exception:
        pass

    return annual, quarterly, results, dividends


def _merge_and_save(path, columns, new_rows, refreshed_symbols):
    """Replace the refreshed companies' rows and keep everyone else's."""
    new = pd.DataFrame(new_rows, columns=columns)
    new[columns[1]] = new[columns[1]].astype(str)   # dates as text, like the saved file
    if path.exists():
        old = pd.read_csv(path)
        got_new_rows = set(new["symbol"])
        keep = old[~old["symbol"].isin(refreshed_symbols & got_new_rows)]
        new = pd.concat([keep, new], ignore_index=True)
    new = new.drop_duplicates().sort_values(columns[:2])
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False)


def update_fundamentals(symbols, workers=6):
    """Download statements for many companies and save them as four CSV files.

    A company Yahoo returns nothing for keeps whatever was saved before.
    Returns the number of companies that came back with yearly results.
    """
    symbols = list(symbols)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fetched = list(pool.map(fetch_symbol, symbols))

    annual = [row for part in fetched for row in part[0]]
    quarterly = [row for part in fetched for row in part[1]]
    results = [row for part in fetched for row in part[2]]
    dividends = [row for part in fetched for row in part[3]]
    refreshed = set(symbols)
    _merge_and_save(config.ANNUAL_FILE, ANNUAL_COLUMNS, annual, refreshed)
    _merge_and_save(config.QUARTERLY_FILE, QUARTERLY_COLUMNS, quarterly, refreshed)
    _merge_and_save(config.RESULTS_DATES_FILE, RESULTS_COLUMNS, results, refreshed)
    _merge_and_save(config.DIVIDENDS_FILE, DIVIDEND_COLUMNS, dividends, refreshed)
    record_fetched(symbols)
    return len({row["symbol"] for row in annual})


# ------------------------------------------------- which companies are due --
def _today():
    return pd.Timestamp.now(tz="Asia/Kolkata").normalize().tz_localize(None)


def load_fetched():
    """{symbol: day its results were last downloaded}.

    The first time (no record yet) every company already saved gets the date of
    the saved files, moved back by 0-29 days depending on its name, so the
    monthly re-check is spread over the month instead of all on one day.
    """
    if config.RESULTS_FETCHED_FILE.exists():
        table = pd.read_csv(config.RESULTS_FETCHED_FILE, parse_dates=["fetched"])
        return dict(zip(table["symbol"], table["fetched"]))
    if not config.ANNUAL_FILE.exists():
        return {}
    saved_on = pd.Timestamp(config.ANNUAL_FILE.stat().st_mtime, unit="s").normalize()
    symbols = set(pd.read_csv(config.ANNUAL_FILE, usecols=["symbol"])["symbol"])
    if config.QUARTERLY_FILE.exists():
        symbols |= set(pd.read_csv(config.QUARTERLY_FILE, usecols=["symbol"])["symbol"])
    spread = config.RESULTS_FULL_REFRESH_DAYS
    return {symbol: saved_on - pd.Timedelta(days=zlib.crc32(symbol.encode()) % spread)
            for symbol in symbols}


def record_fetched(symbols, day=None):
    """Remember that these companies' results were downloaded today."""
    day = _today() if day is None else pd.Timestamp(day)
    fetched = load_fetched()
    fetched.update({symbol: day for symbol in symbols})
    table = pd.DataFrame(sorted(fetched.items()), columns=FETCHED_COLUMNS)
    table["fetched"] = pd.to_datetime(table["fetched"]).dt.strftime("%Y-%m-%d")
    config.RESULTS_FETCHED_FILE.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(config.RESULTS_FETCHED_FILE, index=False)


def quarter_before(day):
    """The last quarter end (31 Mar, 30 Jun, 30 Sep, 31 Dec) before this day."""
    return (pd.Timestamp(day).normalize() - pd.offsets.QuarterEnd(1)).normalize()


def results_events(results_dates=None, announcements=None):
    """Table (symbol, date) of results days: Yahoo's dates and NSE result filings."""
    parts = []
    if results_dates is not None and len(results_dates) > 0:
        parts.append(results_dates[["symbol", "date"]])
    if announcements is not None and len(announcements) > 0:
        filed = announcements[announcements["category"] == "Results"]
        parts.append(pd.DataFrame({"symbol": filed["symbol"],
                                   "date": pd.to_datetime(filed["time"]).dt.normalize()}))
    if not parts:
        return pd.DataFrame(columns=["symbol", "date"])
    return pd.concat(parts, ignore_index=True)


def due_symbols(symbols, today=None, fetched=None, quarterly=None, events=None,
                annual=None):
    """Companies whose results should be downloaded now. A company is due when:

      - its results were never downloaded, or
      - they were last downloaded config.RESULTS_FULL_REFRESH_DAYS or more ago
        (catches corrections and anything missed), or
      - it announced results in the last config.RESULTS_WATCH_DAYS days and the
        saved figures (quarterly or yearly) do not have that quarter yet. Yahoo often takes a few
        days to add a new quarter, so this is tried again once a day until it
        appears or the window passes.

    Nothing is downloaded twice on the same day.
    """
    today = _today() if today is None else pd.Timestamp(today)
    fetched = load_fetched() if fetched is None else fetched
    if quarterly is None:
        quarterly = load_quarterly()
    if annual is None:
        annual = load_annual()
    if events is None:
        from trading import news
        try:
            announcements = news.load()
        except Exception:
            announcements = None
        events = results_events(load_results_dates(), announcements)

    # Newest period saved, quarterly or yearly (Yahoo often lists the March
    # quarter only in the yearly figures).
    periods = [table[["symbol", "period_end"]] for table in (quarterly, annual)
               if table is not None and len(table) > 0]
    latest_quarter = {} if not periods else \
        pd.concat(periods).groupby("symbol")["period_end"].max().to_dict()
    window_start = today - pd.Timedelta(days=config.RESULTS_WATCH_DAYS)
    recent = events[(events["date"] >= window_start) & (events["date"] <= today)]
    last_event = recent.groupby("symbol")["date"].max().to_dict()

    due = []
    for symbol in symbols:
        last = fetched.get(symbol)
        if last is None or pd.isna(last):
            due.append(symbol)
            continue
        last = pd.Timestamp(last).normalize()
        if last >= today:
            continue
        if (today - last).days >= config.RESULTS_FULL_REFRESH_DAYS:
            due.append(symbol)
            continue
        event = last_event.get(symbol)
        if event is not None:
            have = latest_quarter.get(symbol)
            if have is None or pd.Timestamp(have) < quarter_before(event):
                due.append(symbol)
    return due


# ---------------------------------------------------------------- loading ---
def load_annual():
    """Yearly results for all companies, or None if not downloaded yet."""
    if not config.ANNUAL_FILE.exists():
        return None
    return pd.read_csv(config.ANNUAL_FILE, parse_dates=["period_end"])


def load_quarterly():
    """Quarterly results for all companies, or None if not downloaded yet."""
    if not config.QUARTERLY_FILE.exists():
        return None
    return pd.read_csv(config.QUARTERLY_FILE, parse_dates=["period_end"])


def load_dividends():
    """Dividends paid per share, or None if not downloaded yet."""
    if not config.DIVIDENDS_FILE.exists():
        return None
    return pd.read_csv(config.DIVIDENDS_FILE, parse_dates=["date"])


def load_results_dates():
    """Results announcement dates, or None if not downloaded yet."""
    if not config.RESULTS_DATES_FILE.exists():
        return None
    return pd.read_csv(config.RESULTS_DATES_FILE, parse_dates=["date"])


# ---------------------------------------------------------------- metrics ---
def _ratio(top, bottom):
    """top / bottom, or None when either is missing or bottom is not positive."""
    if top is None or bottom is None or pd.isna(top) or pd.isna(bottom) or bottom <= 0:
        return None
    return top / bottom


def yearly_metrics(company_rows):
    """One row of ratios per financial year for a single company.

    company_rows: that company's rows from the annual table.
    """
    rows = company_rows.sort_values("period_end").reset_index(drop=True)
    metrics = []
    for position, year in rows.iterrows():
        previous = rows.iloc[position - 1] if position > 0 else None
        sales_growth = profit_growth = None
        if previous is not None:
            ratio = _ratio(year["revenue"], previous["revenue"])
            sales_growth = None if ratio is None else ratio - 1
            if pd.notna(year["net_income"]) and pd.notna(previous["net_income"]) \
                    and previous["net_income"] != 0:
                profit_growth = (
                    (year["net_income"] - previous["net_income"]) / abs(previous["net_income"])
                )
        metrics.append({
            "period_end": year["period_end"],
            "net_income": year["net_income"],
            "equity": year["equity"],
            "shares": year["shares"],
            "sales_growth": sales_growth,
            "profit_growth": profit_growth,
            "net_margin": _ratio(year["net_income"], year["revenue"]),
            "return_on_equity": _ratio(year["net_income"], year["equity"]),
            "debt_to_equity": _ratio(year["total_debt"], year["equity"]),
        })
    return pd.DataFrame(metrics)


def passes_quality(metric_row, is_financial=False):
    """Does one year's set of ratios pass the quality rules in config.py?

    A ratio that cannot be worked out (missing data) does not fail the company
    on that rule, except profit: an unknown profit fails.
    """
    def known(value):
        return value is not None and pd.notna(value)

    net_income = metric_row["net_income"]
    if config.QUALITY_REQUIRE_PROFIT and not (known(net_income) and net_income > 0):
        return False
    growth = metric_row["sales_growth"]
    if known(growth) and growth < config.QUALITY_MIN_SALES_GROWTH:
        return False
    equity = metric_row["equity"]
    if known(equity) and equity <= 0:
        return False  # the company owes more than it owns
    roe = metric_row["return_on_equity"]
    if known(roe) and roe < config.QUALITY_MIN_RETURN_ON_EQUITY:
        return False
    debt = metric_row["debt_to_equity"]
    if not is_financial and known(debt) and debt > config.QUALITY_MAX_DEBT_TO_EQUITY:
        return False
    return True


def quality_mask(company_rows, dates, is_financial=False):
    """True/False per day: did the company pass the quality rules on that day?

    Each year's results count only from REPORTING_LAG_DAYS after the year end,
    so a backtest never uses numbers that were not yet public. Days before the
    first available results are True (nothing is known, so nothing is filtered).
    """
    mask = pd.Series(True, index=dates)
    if company_rows is None or len(company_rows) == 0:
        return mask
    lag = pd.Timedelta(days=config.REPORTING_LAG_DAYS)
    for _, year in yearly_metrics(company_rows).iterrows():
        mask[dates >= year["period_end"] + lag] = passes_quality(year, is_financial)
    return mask


def near_results_mask(result_dates, dates):
    """True on the days just before (and on) a results announcement."""
    mask = pd.Series(False, index=dates)
    window = pd.Timedelta(days=config.RESULTS_BLOCK_DAYS)
    for day in result_dates:
        mask |= (dates >= day - window) & (dates <= day)
    return mask


def latest_snapshot(company_rows, close=None, as_of=None):
    """The newest available ratios for one company, plus valuation if a price is given.

    Returns a dictionary, or None if the company has no yearly results.
    Valuation uses the share count at the last year end, so it is off after a
    recent bonus issue or split.
    """
    if company_rows is None or len(company_rows) == 0:
        return None
    metrics = yearly_metrics(company_rows)
    if as_of is not None:
        lag = pd.Timedelta(days=config.REPORTING_LAG_DAYS)
        metrics = metrics[metrics["period_end"] + lag <= pd.Timestamp(as_of)]
        if len(metrics) == 0:
            return None
    latest = metrics.iloc[-1].to_dict()
    latest["pe"] = latest["price_to_book"] = None
    if close is not None and latest["shares"] is not None and pd.notna(latest["shares"]):
        market_value = close * latest["shares"]
        latest["pe"] = _ratio(market_value, latest["net_income"])
        latest["price_to_book"] = _ratio(market_value, latest["equity"])
    return latest
