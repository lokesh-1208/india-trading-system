"""Live prices for a handful of stocks, for the Today page.

The model still decides from closing prices, as it was tested. Live prices are
only used to show where a stock is right now: still inside its buy limit, or
already above it, and how your holdings are doing during the day.

Source: Yahoo Finance's chart answer (the same source as the daily prices),
one small request per stock, a few at a time. Each price is kept for
CACHE_SECONDS so refreshing the page does not ask again.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx

# Daily bars for the last few days: the previous close is read from them, because
# Yahoo's own "previous close" for indices can be a day older than it should be.
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
# The top bar's indices: name shown -> Yahoo ticker
INDICES = {"Nifty 50": "^NSEI", "India VIX": "^INDIAVIX", "USD/INR": "INR=X", "Brent": "BZ=F"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CACHE_SECONDS = 30
MAX_SYMBOLS = 80     # the weekly list with its sector picks, plus your holdings
INDIA = timezone(timedelta(hours=5, minutes=30))

_cache = {}                 # symbol -> (fetched at, price row)
_lock = threading.Lock()


def market_open(now=None):
    """True on trading days from 9:15 am to 3:30 pm India time (NSE holidays skipped)."""
    from trading import holidays
    now = now or datetime.now(INDIA)
    if not holidays.is_trading_day(now.date()):
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 30


def parse(answer):
    """One stock's price row from Yahoo's chart answer, or None."""
    try:
        result = answer["chart"]["result"][0]
        meta = result["meta"]
    except (KeyError, IndexError, TypeError):
        return None
    price = meta.get("regularMarketPrice")
    if not price:
        return None
    stamp = meta.get("regularMarketTime")
    previous = _previous_close(result, stamp) or meta.get("chartPreviousClose") \
        or meta.get("previousClose")
    when = datetime.fromtimestamp(stamp, INDIA).isoformat(timespec="seconds") if stamp else None
    change = round((price / previous - 1) * 100, 2) if previous else None
    previous = round(float(previous), 2) if previous else None
    return {"price": round(float(price), 2), "previous_close": previous,
            "change_%": change, "time": when}


def _previous_close(result, stamp):
    """The last daily close before the day of the latest price, from the daily bars."""
    try:
        times = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return None
    if not stamp:
        return None
    today = datetime.fromtimestamp(stamp, INDIA).date()
    before = [close for when, close in zip(times, closes)
              if close and datetime.fromtimestamp(when, INDIA).date() < today]
    return before[-1] if before else None


def _one(client, ticker):
    try:
        safe = ticker.replace("&", "%26").replace("^", "%5E").replace("=", "%3D")
        answer = client.get(URL.format(ticker=safe), timeout=8)
        answer.raise_for_status()
        return ticker, parse(answer.json())
    except Exception:
        return ticker, None


def prices(symbols, fetch=None):
    """{symbol: price row} for NSE stocks that answered. fetch replaces the download in tests."""
    wanted = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))[:MAX_SYMBOLS]
    found = quotes([f"{symbol}.NS" for symbol in wanted],
                   fetch=None if fetch is None else (lambda ticker: fetch(ticker[:-3])))
    return {ticker[:-3]: row for ticker, row in found.items()}


def indices(fetch=None):
    """{name: price row} for the top bar's indices."""
    found = quotes(list(INDICES.values()), fetch=fetch)
    return {name: found[ticker] for name, ticker in INDICES.items() if ticker in found}


def quotes(tickers, fetch=None):
    """{Yahoo ticker: price row} for the tickers that answered, kept for CACHE_SECONDS."""
    wanted = list(dict.fromkeys(tickers))
    now = time.time()
    found, missing = {}, []
    with _lock:
        for symbol in wanted:
            kept = _cache.get(symbol)
            if kept and now - kept[0] < CACHE_SECONDS:
                found[symbol] = kept[1]
            else:
                missing.append(symbol)
    if missing:
        if fetch is None:
            with httpx.Client(headers=HEADERS, follow_redirects=True) as client, \
                    ThreadPoolExecutor(max_workers=8) as pool:
                answers = list(pool.map(lambda s: _one(client, s), missing))
        else:
            answers = [(s, fetch(s)) for s in missing]
        with _lock:
            for symbol, row in answers:
                if row is not None:
                    _cache[symbol] = (now, row)
                    found[symbol] = row
    return found


def clear_cache():
    with _lock:
        _cache.clear()
