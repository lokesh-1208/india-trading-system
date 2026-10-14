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

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=1m&range=1d"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CACHE_SECONDS = 30
MAX_SYMBOLS = 40
INDIA = timezone(timedelta(hours=5, minutes=30))

_cache = {}                 # symbol -> (fetched at, price row)
_lock = threading.Lock()


def market_open(now=None):
    """True on weekdays from 9:15 am to 3:30 pm India time (holidays are not known)."""
    now = now or datetime.now(INDIA)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 30


def parse(answer):
    """One stock's price row from Yahoo's chart answer, or None."""
    try:
        meta = answer["chart"]["result"][0]["meta"]
    except (KeyError, IndexError, TypeError):
        return None
    price = meta.get("regularMarketPrice")
    previous = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not price:
        return None
    stamp = meta.get("regularMarketTime")
    when = datetime.fromtimestamp(stamp, INDIA).isoformat(timespec="seconds") if stamp else None
    change = round((price / previous - 1) * 100, 2) if previous else None
    return {"price": round(float(price), 2), "previous_close": previous,
            "change_%": change, "time": when}


def _one(client, symbol):
    try:
        answer = client.get(URL.format(symbol=symbol.replace("&", "%26")), timeout=8)
        answer.raise_for_status()
        return symbol, parse(answer.json())
    except Exception:
        return symbol, None


def prices(symbols, fetch=None):
    """{symbol: price row} for the symbols that answered. fetch replaces the download in tests."""
    wanted = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))[:MAX_SYMBOLS]
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
