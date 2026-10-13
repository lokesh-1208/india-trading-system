"""Daily stock prices from NSE's own end-of-day file, and filling Yahoo's gaps.

NSE publishes one small file per trading day (the "bhavcopy") with the open,
high, low, close and volume of every stock. This module uses it in two ways:

1. Quick daily update. Instead of downloading 10 years of history for 860
   stocks from Yahoo every day (about 6 minutes), only the new days are added
   from NSE's file (under a minute). The full Yahoo history is still downloaded
   once a week, see data.update_all.

2. Filling gaps. Sometimes Yahoo's daily history skips a whole trading day
   (Monday 12 Oct 2026 was missing for every stock). After a full Yahoo
   download, a recent day Nifty traded but a stock is missing is filled in
   from NSE's file.

Yahoo's prices are adjusted for dividends and splits, NSE's are not:
  - When filling a gap in a fresh Yahoo download, the NSE bar is scaled by
    the factor that separates Yahoo's price from NSE's on a later day both
    have. Normally that factor is 1.0.
  - In the quick update, NSE's "previous close" is compared with the last
    saved close. If they differ by more than config.CORPORATE_ACTION_GAP, the
    company had a split, bonus or big dividend, so the saved (adjusted) history
    is out of date and that one stock's full history is downloaded again.

If NSE's file for a day is not out yet (it appears in the evening), Yahoo's
recent daily bars are used for that day, and for older days Yahoo's hourly bars
as a last resort. The last two trading days are always taken again from NSE
once its file is out, so a bar saved during market hours gets corrected.
"""

import io
import zipfile

import numpy as np
import pandas as pd

import config
from trading import data

BHAVCOPY_URL = ("https://nsearchives.nseindia.com/content/cm/"
                "BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip")
BHAVCOPY_DIR = config.DATA_DIR / "bhavcopy"       # one small CSV per day, kept for reuse
SERIES = ["EQ", "BE", "BZ"]                        # normal shares, in order of preference
BHAVCOPY_COLUMNS = {"TckrSymb": "Symbol", "SctySrs": "Series", "OpnPric": "Open",
                    "HghPric": "High", "LwPric": "Low", "ClsPric": "Close",
                    "TtlTradgVol": "Volume", "PrvsClsgPric": "PrevClose"}
DAY_COLUMNS = data.PRICE_COLUMNS + ["PrevClose"]
LOOKBACK_DAYS = 10            # only the last 10 trading days are checked
FACTOR_LIMITS = (0.2, 5.0)    # a scaling factor outside this means something odd: skip


def _empty_summary():
    return {"days": [], "from_nse": 0, "from_yahoo": 0, "from_hourly": 0,
            "not_filled": 0, "need_full_history": []}


def india_today():
    return pd.Timestamp.now(tz="Asia/Kolkata").normalize().tz_localize(None)


# ------------------------------------------------------------- calendar -----
def trading_days(lookback=LOOKBACK_DAYS):
    """The last `lookback` days Nifty traded, oldest first."""
    nifty = data.load_prices("NIFTY50", config.MARKET_DIR)
    if nifty is None or len(nifty) == 0:
        return []
    return list(nifty.index[-lookback:])


def missing_days(table, days, refresh_last=0):
    """Days from `days` that should be (re)written for one stock.

    Missing days, plus the last `refresh_last` days even when they are saved.
    A stock is only checked when it traded during the window (otherwise it was
    probably delisted or suspended), and only for days after its first price.
    """
    if table is None or len(table) == 0 or not days:
        return []
    if table.index[-1] < days[0]:
        return []
    have = set(table.index)
    redo = set(days[-refresh_last:]) if refresh_last else set()
    return [day for day in days
            if day > table.index[0] and (day not in have or day in redo)]


# ------------------------------------------------------------ bhavcopy ------
def parse_bhavcopy(text):
    """NSE's day file -> table of Open/High/Low/Close/Volume/PrevClose by symbol."""
    raw = pd.read_csv(io.StringIO(text), usecols=list(BHAVCOPY_COLUMNS))
    raw = raw.rename(columns=BHAVCOPY_COLUMNS)
    raw = raw[raw["Series"].isin(SERIES)].copy()
    raw["rank"] = raw["Series"].map({series: rank for rank, series in enumerate(SERIES)})
    raw = raw.sort_values("rank").drop_duplicates("Symbol")
    return raw.set_index("Symbol")[DAY_COLUMNS].astype(float)


def load_bhavcopy(day, browser=None):
    """NSE's end-of-day prices for one day, or None if NSE does not have it (yet).

    A downloaded day is saved in data/bhavcopy so it is not fetched twice.
    """
    saved = BHAVCOPY_DIR / f"{day:%Y-%m-%d}.csv"
    if saved.exists():
        table = pd.read_csv(saved, index_col="Symbol")
        if set(DAY_COLUMNS) <= set(table.columns):
            return table
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


def _nse_browser():
    try:
        from trading import nse
        return nse.session()
    except Exception:
        return None


# ------------------------------------------------------ Yahoo fallbacks -----
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


def _yahoo_recent(symbols, first_day, interval):
    """{symbol: daily table} from Yahoo for the days from `first_day` on."""
    import yfinance as yf

    result = {}
    for first in range(0, len(symbols), data.BATCH_SIZE):
        batch = symbols[first:first + data.BATCH_SIZE]
        tickers = [data.yahoo_ticker(symbol) for symbol in batch]
        try:
            raw = yf.download(tickers, start=first_day, interval=interval, auto_adjust=True,
                              progress=False, group_by="ticker", threads=True)
        except Exception:
            continue
        for symbol, ticker in zip(batch, tickers):
            try:
                part = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            result[symbol] = (daily_from_hourly(part) if interval == "1h"
                              else data.clean_prices(part))
    return result


# -------------------------------------------------------------- filling -----
def scaling_factor(symbol, table, day_files, from_day, skip=()):
    """Yahoo price / NSE price on the latest day both have, on or after `from_day`.

    Days in `skip` are not used (their saved bar is about to be replaced).
    Returns 1.0 when there is no such day, and None when the factor looks wrong.
    """
    for day in sorted(day_files, reverse=True):
        if day < from_day or day in skip or day not in table.index:
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


def had_corporate_action(table, first_new_day, nse_day, symbol):
    """True when NSE's previous close does not match the last saved close.

    That happens after a split, bonus or large dividend: NSE lowers the
    previous close, while the saved history still has the old prices.
    """
    if nse_day is None or symbol not in nse_day.index:
        return False
    before = table[table.index < first_new_day]
    if len(before) == 0:
        return False
    saved = float(before["Close"].iloc[-1])
    previous = float(nse_day.loc[symbol, "PrevClose"])
    if saved <= 0 or previous <= 0:
        return False
    return abs(previous / saved - 1) > config.CORPORATE_ACTION_GAP


def same_bar(table, day, bar):
    """True when the saved bar for this day already has these prices and volume."""
    if day not in table.index:
        return False
    saved = table.loc[day, data.PRICE_COLUMNS].astype(float).to_numpy()
    new = pd.Series(bar)[data.PRICE_COLUMNS].astype(float).to_numpy()
    return bool(np.allclose(saved, new, rtol=1e-6, equal_nan=True))


def add_rows(table, rows):
    """Put daily rows into a price table (replacing those days), sorted by date."""
    new = pd.DataFrame(rows).T[data.PRICE_COLUMNS].astype(float)
    new.index = pd.to_datetime(new.index)
    new.index.name = "Date"
    combined = pd.concat([new, table])
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined.sort_index()


def fill_missing_days(symbols=None, report=data._print_progress, today=None, quick=False):
    """Add recent trading days to the saved price files from NSE's day files.

    quick=False: after a full Yahoo download, only fill days Yahoo left out.
    quick=True:  the daily quick update. Also re-take the last two days, and
                 report stocks whose history needs a full download because of
                 a split, bonus or big dividend (they are not changed here).

    Returns a summary: which days were written, how many stock-days came from
    NSE, from Yahoo's daily or hourly bars, how many could not be filled, and
    which stocks need their full history downloaded again.
    """
    summary = _empty_summary()
    days = trading_days()
    if not days:
        return summary
    today = india_today() if today is None else pd.Timestamp(today)
    symbols = data.all_symbols() if symbols is None else symbols
    refresh_last = 2 if quick else 0

    tables, gaps = {}, {}
    for symbol in symbols:
        table = data.load_prices(symbol)
        wanted = missing_days(table, days, refresh_last)
        if wanted:
            tables[symbol], gaps[symbol] = table, wanted
    if not gaps:
        return summary
    all_wanted = sorted({day for wanted in gaps.values() for day in wanted})

    report("NSE day files", 0, 1)
    browser = _nse_browser()
    day_files = {day: load_bhavcopy(day, browser) for day in set(all_wanted) | {days[-1]}}
    report("NSE day files", 1, 1)

    rows, need_yahoo = {}, {}
    for symbol, wanted in gaps.items():
        table = tables[symbol]
        if quick:
            if had_corporate_action(table, wanted[0], day_files.get(wanted[0]), symbol):
                summary["need_full_history"].append(symbol)
                continue
        for day in wanted:
            nse_day = day_files.get(day)
            if nse_day is None:
                need_yahoo.setdefault(symbol, []).append(day)
                continue
            if symbol not in nse_day.index:
                continue             # did not trade that day (suspended, for example)
            factor = 1.0 if quick else scaling_factor(symbol, table, day_files, day)
            if factor is None:
                summary["not_filled"] += 1
                continue
            bar = nse_day.loc[symbol, data.PRICE_COLUMNS].copy()
            bar[["Open", "High", "Low", "Close"]] *= factor
            rows.setdefault(symbol, {})[day] = bar
            summary["from_nse"] += 1

    # Days NSE's file is not out for: Yahoo's daily bars, then hourly bars.
    if need_yahoo:
        first_day = min(day for wanted in need_yahoo.values() for day in wanted)
        report("Yahoo for days NSE has not published", 0, 1)
        daily = _yahoo_recent(list(need_yahoo), first_day, "1d")
        still = {}
        for symbol, wanted in need_yahoo.items():
            table = daily.get(symbol)
            for day in wanted:
                if table is not None and day in table.index:
                    rows.setdefault(symbol, {})[day] = table.loc[day]
                    summary["from_yahoo"] += 1
                elif day < today:
                    still.setdefault(symbol, []).append(day)
        if still:
            hourly = _yahoo_recent(list(still), min(min(w) for w in still.values()), "1h")
            for symbol, wanted in still.items():
                table = hourly.get(symbol)
                for day in wanted:
                    if table is not None and day in table.index:
                        rows.setdefault(symbol, {})[day] = table.loc[day]
                        summary["from_hourly"] += 1
                    else:
                        summary["not_filled"] += 1
        report("Yahoo for days NSE has not published", 1, 1)

    # Only write files that really change (re-taking a day often gives the same bar).
    for symbol in list(rows):
        table = tables[symbol]
        rows[symbol] = {day: bar for day, bar in rows[symbol].items()
                        if not same_bar(table, day, bar)}
        if not rows[symbol]:
            del rows[symbol]
    for symbol, new_rows in rows.items():
        add_rows(tables[symbol], new_rows).to_csv(config.PRICES_DIR / f"{symbol}.csv")
    summary["days"] = sorted({day for new_rows in rows.values() for day in new_rows})
    return summary
