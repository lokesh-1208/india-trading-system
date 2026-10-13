"""Fill in trading days that Yahoo is missing.

Sometimes Yahoo's daily history for NSE stocks skips a whole trading day even
though the market was open (Monday 12 Oct 2026 was missing for every stock).
The charts then jump over that day and every indicator is a day off.

After each download this module compares every stock with the days Nifty
traded. A recent day that a stock is missing is filled in from NSE's own
end-of-day file (the "bhavcopy"), which lists the open, high, low, close and
volume of every stock for one day. If NSE's file cannot be downloaded, Yahoo's
hourly bars for that day are added up into one daily bar instead (prices are
right, volume comes out a little low).

Yahoo's daily prices are adjusted for dividends and splits, NSE's are not. So
each filled day is scaled by the same factor that separates Yahoo's price from
NSE's price on a nearby day both of them have. Normally that factor is 1.0.

Because update_all downloads the full history again on every run, a gap comes
back each time until Yahoo fixes it, and this fill simply runs again.
"""

import io
import zipfile

import pandas as pd

import config
from trading import data

BHAVCOPY_URL = ("https://nsearchives.nseindia.com/content/cm/"
                "BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip")
BHAVCOPY_DIR = config.DATA_DIR / "bhavcopy"       # one small CSV per day, kept for reuse
SERIES = ["EQ", "BE", "BZ"]                        # normal shares, in order of preference
BHAVCOPY_COLUMNS = {"TckrSymb": "Symbol", "SctySrs": "Series", "OpnPric": "Open",
                    "HghPric": "High", "LwPric": "Low", "ClsPric": "Close",
                    "TtlTradgVol": "Volume"}
LOOKBACK_DAYS = 10            # only the last 10 trading days are checked
FACTOR_LIMITS = (0.2, 5.0)    # a scaling factor outside this means something odd: skip


# ------------------------------------------------------------- calendar -----
def trading_days(lookback=LOOKBACK_DAYS):
    """The last `lookback` days Nifty traded, oldest first."""
    nifty = data.load_prices("NIFTY50", config.MARKET_DIR)
    if nifty is None or len(nifty) == 0:
        return []
    return list(nifty.index[-lookback:])


def missing_days(table, days):
    """Days from `days` that a stock should have but does not.

    A stock is only checked when it traded during the window (otherwise it was
    probably delisted or suspended), and only for days after its first price.
    """
    if table is None or len(table) == 0 or not days:
        return []
    if table.index[-1] < days[0]:
        return []
    have = set(table.index)
    return [day for day in days if day > table.index[0] and day not in have]


# ------------------------------------------------------------ bhavcopy ------
def parse_bhavcopy(text):
    """NSE's day file -> table of Open/High/Low/Close/Volume indexed by symbol."""
    raw = pd.read_csv(io.StringIO(text), usecols=list(BHAVCOPY_COLUMNS))
    raw = raw.rename(columns=BHAVCOPY_COLUMNS)
    raw = raw[raw["Series"].isin(SERIES)].copy()
    raw["rank"] = raw["Series"].map({series: rank for rank, series in enumerate(SERIES)})
    raw = raw.sort_values("rank").drop_duplicates("Symbol")
    return raw.set_index("Symbol")[data.PRICE_COLUMNS].astype(float)


def load_bhavcopy(day, browser=None):
    """NSE's end-of-day prices for one day, or None if NSE does not have it (yet).

    A downloaded day is saved in data/bhavcopy so it is not fetched twice.
    """
    saved = BHAVCOPY_DIR / f"{day:%Y-%m-%d}.csv"
    if saved.exists():
        return pd.read_csv(saved, index_col="Symbol")
    try:
        if browser is None:
            from trading import nse
            browser = nse.session()
        answer = browser.get(BHAVCOPY_URL.format(day=day), timeout=60)
        if answer.status_code != 200:
            return None
        archive = zipfile.ZipFile(io.BytesIO(answer.content))
        table = parse_bhavcopy(archive.read(archive.namelist()[0]).decode("utf-8"))
    except Exception:
        return None
    BHAVCOPY_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(saved)
    return table


# ------------------------------------------------------- hourly fallback ----
def daily_from_hourly(hourly):
    """Add Yahoo's hourly bars up into one bar per Indian trading day."""
    if hourly is None or len(hourly) == 0:
        return pd.DataFrame(columns=data.PRICE_COLUMNS)
    table = hourly[data.PRICE_COLUMNS].dropna(subset=["Close"])
    index = pd.to_datetime(table.index)
    if index.tz is not None:
        index = index.tz_convert("Asia/Kolkata").tz_localize(None)
    table = table.set_axis(index.normalize())
    daily = table.groupby(level=0).agg({"Open": "first", "High": "max", "Low": "min",
                                        "Close": "last", "Volume": "sum"})
    daily.index.name = "Date"
    return daily


def hourly_bars(symbols, days):
    """{symbol: daily table built from hourly bars} for the given days."""
    import yfinance as yf

    tickers = [data.yahoo_ticker(symbol) for symbol in symbols]
    try:
        raw = yf.download(tickers, start=min(days), end=max(days) + pd.Timedelta(days=1),
                          interval="1h", auto_adjust=True, progress=False,
                          group_by="ticker", threads=True)
    except Exception:
        return {}
    result = {}
    for symbol, ticker in zip(symbols, tickers):
        try:
            part = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        result[symbol] = daily_from_hourly(part)
    return result


# -------------------------------------------------------------- filling -----
def scaling_factor(symbol, table, day_files, from_day):
    """Yahoo price / NSE price on the latest day both have, on or after `from_day`.

    Returns 1.0 when there is no such day, and None when the factor looks wrong.
    """
    for day in sorted(day_files, reverse=True):
        if day < from_day or day not in table.index:
            continue
        nse_day = day_files[day]
        if nse_day is None or symbol not in nse_day.index:
            continue
        nse_close = nse_day.loc[symbol, "Close"]
        if nse_close <= 0:
            continue
        factor = float(table.loc[day, "Close"]) / float(nse_close)
        low, high = FACTOR_LIMITS
        return factor if low < factor < high else None
    return 1.0


def add_rows(table, rows):
    """Put new daily rows into a price table, keeping it sorted by date."""
    new = pd.DataFrame(rows).T[data.PRICE_COLUMNS].astype(float)
    new.index = pd.to_datetime(new.index)
    new.index.name = "Date"
    combined = pd.concat([table, new])
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined.sort_index()


def fill_missing_days(symbols=None, report=data._print_progress, today=None):
    """Fill recent trading days that Yahoo left out of the saved price files.

    Returns a summary: which days were missing, how many stock-days came from
    NSE, how many from Yahoo's hourly bars, and how many could not be filled.
    """
    summary = {"days": [], "from_nse": 0, "from_hourly": 0, "not_filled": 0}
    days = trading_days()
    if not days:
        return summary
    today = pd.Timestamp.now(tz="Asia/Kolkata").normalize().tz_localize(None) \
        if today is None else pd.Timestamp(today)
    symbols = data.all_symbols() if symbols is None else symbols

    tables, gaps = {}, {}
    for symbol in symbols:
        table = data.load_prices(symbol)
        wanted = missing_days(table, days)
        if wanted:
            tables[symbol], gaps[symbol] = table, wanted
    if not gaps:
        return summary
    summary["days"] = sorted({day for wanted in gaps.values() for day in wanted})

    # NSE's file for every missing day, plus the latest day for the scaling factor.
    report("Missing days", 0, 1)
    browser = None
    try:
        from trading import nse
        browser = nse.session()
    except Exception:
        pass
    day_files = {day: load_bhavcopy(day, browser) for day in set(summary["days"]) | {days[-1]}}

    rows, need_hourly = {}, {}
    for symbol, wanted in gaps.items():
        table = tables[symbol]
        for day in wanted:
            nse_day = day_files.get(day)
            if nse_day is not None:
                if symbol not in nse_day.index:
                    continue             # did not trade that day (suspended, for example)
                factor = scaling_factor(symbol, table, day_files, day)
                if factor is None:
                    summary["not_filled"] += 1
                    continue
                bar = nse_day.loc[symbol].copy()
                bar[["Open", "High", "Low", "Close"]] *= factor
                rows.setdefault(symbol, {})[day] = bar
                summary["from_nse"] += 1
            elif day < today:
                need_hourly.setdefault(symbol, []).append(day)
            # today's NSE file appears in the evening; until then wait for it

    if need_hourly:
        hourly_days = sorted({day for wanted in need_hourly.values() for day in wanted})
        built = hourly_bars(list(need_hourly), hourly_days)
        for symbol, wanted in need_hourly.items():
            daily = built.get(symbol)
            for day in wanted:
                if daily is not None and day in daily.index:
                    rows.setdefault(symbol, {})[day] = daily.loc[day]
                    summary["from_hourly"] += 1
                else:
                    summary["not_filled"] += 1

    for symbol, new_rows in rows.items():
        add_rows(tables[symbol], new_rows).to_csv(config.PRICES_DIR / f"{symbol}.csv")
    report("Missing days", 1, 1)
    return summary
