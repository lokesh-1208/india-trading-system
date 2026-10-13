"""Download price history from Yahoo Finance and load it back from disk.

The stock universe is the Nifty 500 "as it was on each date". A stock only
counts on the days it was really a member of the index. Without this, a
backtest would only see companies that are in the index today, which are the
ones that survived and grew, and every result would look better than reality.
"""

import time
import urllib.request

import pandas as pd

import config

PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
BATCH_SIZE = 40


# ------------------------------------------------------------ membership ----
def update_membership():
    """Download the Nifty 500 membership history. Keeps the old copy on failure.

    Returns True if a fresh copy was saved.
    """
    folder = config.MEMBERSHIP_FILE.parent
    folder.mkdir(parents=True, exist_ok=True)
    downloads = [
        ("nifty500_membership_calendar.csv", config.MEMBERSHIP_FILE, "symbol,start,end"),
        ("nifty500_list.csv", config.INDUSTRY_FILE, "Company Name,Industry,Symbol"),
    ]
    try:
        for remote_name, local_path, expected_header in downloads:
            with urllib.request.urlopen(config.MEMBERSHIP_SOURCE + remote_name, timeout=30) as reply:
                text = reply.read().decode("utf-8")
            # Never replace a good file with an error page or an empty file.
            if not text.startswith(expected_header) or text.count("\n") < 400:
                raise ValueError(f"{remote_name} does not look right")
            local_path.write_text(text, encoding="utf-8")
        return True
    except Exception as error:
        print(f"Could not refresh the index membership list: {error}")
        return False


def load_membership():
    """Table of (symbol, start, end). `end` is empty for a current member.

    Returns None if the membership file has not been downloaded.
    """
    if not config.MEMBERSHIP_FILE.exists():
        return None
    membership = pd.read_csv(config.MEMBERSHIP_FILE, parse_dates=["start", "end"])
    return add_listed_members(membership, load_index_list())


def load_index_list():
    """Symbols on NSE's current Nifty 500 list, or an empty list if not downloaded."""
    if not config.INDUSTRY_FILE.exists():
        return []
    return list(pd.read_csv(config.INDUSTRY_FILE)["Symbol"].dropna().unique())


def add_listed_members(membership, listed, today=None):
    """Add stocks that NSE lists in the index today but the history file misses.

    The membership history comes from a public project and sometimes leaves out
    a current member (ITC, Tata Power and Federal Bank were missing in Oct 2026).
    Such a stock is added as a member from config.MISSING_MEMBER_START_DAYS ago.
    Its older history stays unknown, so backtests over earlier years do not
    count it, which keeps them free of hindsight.
    """
    open_members = set(membership.loc[membership["end"].isna(), "symbol"])
    missing = sorted(set(listed) - open_members)
    if not missing:
        return membership
    today = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today)
    start = today - pd.Timedelta(days=config.MISSING_MEMBER_START_DAYS)
    extra = pd.DataFrame({"symbol": missing, "start": start, "end": pd.NaT})
    return pd.concat([membership, extra], ignore_index=True)


def membership_mask(symbol, dates, membership):
    """True on each date the stock was a member of the index.

    If there is no membership table, every date counts as a member day.
    """
    mask = pd.Series(membership is None, index=dates)
    if membership is None:
        return mask
    for row in membership[membership["symbol"] == symbol].itertuples():
        inside = dates >= row.start
        if pd.notna(row.end):
            inside &= dates < row.end
        mask |= inside
    return mask


def symbols_since(membership, start=config.HISTORY_START):
    """Every stock that was an index member at any time from `start` onward."""
    still_in = membership["end"].isna() | (membership["end"] >= pd.Timestamp(start))
    return sorted(membership.loc[still_in, "symbol"].unique())


def load_universe():
    """Current index members as a table with columns Symbol and Industry."""
    membership = load_membership()
    if membership is None:
        return pd.read_csv(config.UNIVERSE_FILE)  # fallback: the fixed Nifty 200 list

    current = sorted(membership.loc[membership["end"].isna(), "symbol"].unique())
    table = pd.DataFrame({"Symbol": current})
    if config.INDUSTRY_FILE.exists():
        industries = pd.read_csv(config.INDUSTRY_FILE)[["Symbol", "Industry"]]
        table = table.merge(industries, on="Symbol", how="left")
    else:
        table["Industry"] = ""
    table["Industry"] = table["Industry"].fillna("")
    return table


def all_symbols():
    """Every stock we need prices for: current members and former members."""
    membership = load_membership()
    if membership is None:
        return list(load_universe()["Symbol"])
    return symbols_since(membership)


def yahoo_ticker(nse_symbol):
    """Yahoo uses the NSE symbol with .NS at the end (RELIANCE -> RELIANCE.NS)."""
    return f"{nse_symbol}.NS"


# ------------------------------------------------------------- cleaning -----
def clean_prices(raw):
    """Put a downloaded table into one standard shape.

    Result: index named Date (oldest first), columns Open/High/Low/Close/Volume,
    no duplicate dates and no rows without a closing price.
    """
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    table = raw.copy()
    if isinstance(table.columns, pd.MultiIndex):
        table.columns = table.columns.get_level_values(0)
    if not set(PRICE_COLUMNS).issubset(table.columns):
        return pd.DataFrame(columns=PRICE_COLUMNS)

    table = table[PRICE_COLUMNS]
    table.index = pd.to_datetime(table.index)
    if table.index.tz is not None:
        table.index = table.index.tz_localize(None)
    table.index.name = "Date"

    table = table[table["Close"].notna()]
    table = table[~table.index.duplicated(keep="last")]
    return table.sort_index()


# ------------------------------------------------------------- download -----
def download_batch(tickers, start=config.HISTORY_START):
    """Download daily prices for several Yahoo tickers in one request.

    Returns {ticker: clean table}. A ticker Yahoo does not have gets an
    empty table.
    """
    import yfinance as yf  # imported here so the rest works without internet

    raw = yf.download(
        list(tickers),
        start=start,
        auto_adjust=True,          # prices adjusted for splits and dividends
        progress=False,
        group_by="ticker",
        threads=True,
    )
    tables = {}
    for ticker in tickers:
        try:
            tables[ticker] = clean_prices(raw[ticker])
        except KeyError:
            tables[ticker] = pd.DataFrame(columns=PRICE_COLUMNS)
    return tables


def _print_progress(step, done, total):
    print(f"{step}: {done} of {total} done")


def _download_group(jobs, folder, label, report=_print_progress):
    """Download a list of (name, ticker) pairs into a folder. Returns failures.

    report(step, done, total) is called after every batch to show progress.
    """
    failed = []
    for first in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[first:first + BATCH_SIZE]
        try:
            tables = download_batch([ticker for _, ticker in batch])
        except Exception as error:  # network problems and so on
            print(f"  problem with a batch: {error}")
            tables = {}
        for name, ticker in batch:
            table = tables.get(ticker)
            if table is None or len(table) == 0:
                failed.append(name)
            else:
                table.to_csv(folder / f"{name}.csv")
        report(label, min(first + BATCH_SIZE, len(jobs)), len(jobs))
        time.sleep(0.5)  # be polite to the free data source
    return failed


def update_markets(report=_print_progress):
    """Refresh the membership list and download every index (quick: 11 tickers).

    Returns the market names Yahoo had no data for.
    """
    config.PRICES_DIR.mkdir(parents=True, exist_ok=True)
    config.MARKET_DIR.mkdir(parents=True, exist_ok=True)
    update_membership()
    market_jobs = list(config.MARKET_SYMBOLS.items())
    return _download_group(market_jobs, config.MARKET_DIR, "Markets", report)


def download_stocks(symbols, report=_print_progress, label="Stock prices"):
    """Download the full history of these stocks. Returns those Yahoo has no data for."""
    stock_jobs = [(symbol, yahoo_ticker(symbol)) for symbol in symbols]
    return _download_group(stock_jobs, config.PRICES_DIR, label, report)


def update_all(report=_print_progress):
    """Refresh the membership list, then download the full history of everything.

    Yahoo re-adjusts old prices after every dividend and split, which is why
    the full history is downloaded again rather than only the new days. The
    daily update (trading/update.py) does this once a week and adds the days
    in between from NSE's day files.

    Returns (failed market names, stock symbols Yahoo has no data for).
    """
    failed_market = update_markets(report)
    failed_stocks = download_stocks(all_symbols(), report)
    return failed_market, failed_stocks


# ---------------------------------------------------------------- loading ---
def load_prices(name, folder=None):
    """Load one saved CSV. Returns None if the file does not exist."""
    folder = config.PRICES_DIR if folder is None else folder
    path = folder / f"{name}.csv"
    if not path.exists():
        return None
    table = pd.read_csv(path, index_col="Date", parse_dates=True)
    return clean_prices(table)


def load_market(name):
    """Load a market index (Nifty, India VIX, S&P 500 and so on)."""
    return load_prices(name, config.MARKET_DIR)


def load_all_stocks():
    """Load every stock that has a saved file. Returns {symbol: table}.

    Reading 800 CSV files takes several seconds, so the result is also kept in
    one combined file. That file is used as long as no price file is newer
    than it, and rebuilt automatically after every download.
    """
    files = {symbol: config.PRICES_DIR / f"{symbol}.csv" for symbol in all_symbols()}
    files = {symbol: path for symbol, path in files.items() if path.exists()}
    if not files:
        return {}

    newest = max(path.stat().st_mtime for path in files.values())
    if config.PRICES_CACHE.exists() and config.PRICES_CACHE.stat().st_mtime >= newest:
        try:
            stocks = pd.read_pickle(config.PRICES_CACHE)
            if set(stocks) <= set(files):
                return stocks
        except Exception:
            pass  # unreadable or from an older library version: rebuild it below

    stocks = {}
    for symbol in files:
        table = load_prices(symbol)
        if table is not None and len(table) > 0:
            stocks[symbol] = table
    try:
        pd.to_pickle(stocks, config.PRICES_CACHE)
    except Exception:
        pass  # the cache only saves time; nothing depends on it
    return stocks


def coverage_by_year(membership, symbols_with_prices, first_year, last_year):
    """How many index members we have prices for, year by year.

    Members without prices are mostly companies that were later delisted,
    merged or went bankrupt. Yahoo no longer carries them.
    """
    rows = []
    for year in range(first_year, last_year + 1):
        day = pd.Timestamp(year=year, month=7, day=1)
        active = membership[
            (membership["start"] <= day)
            & (membership["end"].isna() | (membership["end"] > day))
        ]["symbol"].unique()
        with_prices = [symbol for symbol in active if symbol in symbols_with_prices]
        rows.append({"year": year, "members": len(active), "with_prices": len(with_prices)})
    return pd.DataFrame(rows)
