"""Free 5-minute candles from Yahoo, cached per stock. The cache keeps growing:
Yahoo gives about 60 days, but every refresh adds to what is already saved."""

import os
import subprocess
import sys

import pandas as pd
import yfinance as yf

from . import settings as s

TZ = "Asia/Kolkata"
COLS = ["Open", "High", "Low", "Close", "Volume"]


def _path(symbol):
    return s.DATA_DIR / (symbol.replace("&", "_").replace("-", "_") + ".csv")


def load(symbol):
    path = _path(symbol)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(TZ)
        return df[COLS]
    except (pd.errors.EmptyDataError, ValueError, KeyError):
        return None                       # a half-written or damaged file counts as "no data"


def _batch_inprocess(symbols, period, interval):
    """Download one group and merge it into the cache. Used by the worker process below."""
    tickers = [x + ".NS" for x in symbols]
    raw = yf.download(tickers, period=period, interval=interval, group_by="ticker",
                      progress=False, auto_adjust=False, threads=True, timeout=20)
    done = 0
    for sym, tk in zip(symbols, tickers):
        try:
            frame = raw[tk] if len(tickers) > 1 else raw
            if isinstance(frame.columns, pd.MultiIndex):
                frame = frame.droplevel(1, axis=1) if frame.columns.nlevels > 1 else frame
            new = frame[COLS].dropna(how="any")
        except KeyError:
            continue
        if new.empty:
            continue
        new.index = pd.to_datetime(new.index, utc=True).tz_convert(TZ)
        old = load(sym)
        merged = new if old is None else pd.concat([old, new])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        _write_atomic(merged, _path(sym))
        done += 1
    return done


def _write_atomic(frame, path):
    """Write to a temporary file, then swap it in, so a killed download never leaves half a file."""
    tmp = path.with_suffix(".tmp")
    frame.to_csv(tmp)
    os.replace(tmp, path)


def _run_batch(symbols, period, interval, seconds=60):
    """Download a group in a SEPARATE process, killed if it stalls (a stalled Yahoo request
    holds a lock inside the library, so a thread cannot be rescued but a process can).
    If a group stalls, it is split in two and retried, down to single stocks."""
    cmd = [sys.executable, "-m", "intraday.data", period, interval, *symbols]
    try:
        out = subprocess.run(cmd, cwd=str(s.ROOT / "backend"), capture_output=True, text=True,
                             timeout=seconds, env={**os.environ, "PYTHONPATH": str(s.ROOT / "backend")})
        for line in reversed(out.stdout.splitlines()):
            if line.startswith("UPDATED "):
                return int(line.split()[1])
        return 0
    except subprocess.TimeoutExpired:
        if len(symbols) == 1:
            return 0                                   # give up on this one stock
        half = len(symbols) // 2
        return (_run_batch(symbols[:half], period, interval, seconds)
                + _run_batch(symbols[half:], period, interval, seconds))


def refresh(symbols=None, period="60d", interval="5m", batch=20):
    """Download recent candles and merge them into the cache. Returns stocks updated."""
    symbols = symbols or s.SYMBOLS
    s.DATA_DIR.mkdir(parents=True, exist_ok=True)
    done = 0
    for i in range(0, len(symbols), batch):
        done += _run_batch(symbols[i:i + batch], period, interval)
        print(f"  downloaded {min(i + batch, len(symbols))}/{len(symbols)}", flush=True)
    return done


if __name__ == "__main__":                      # worker: python -m intraday.data PERIOD INTERVAL SYMBOL...
    print("UPDATED", _batch_inprocess(sys.argv[3:], sys.argv[1], sys.argv[2]))


def _daily_path(symbol):
    return s.DATA_DIR / "daily" / (symbol.replace("&", "_").replace("-", "_") + ".csv")


def refresh_daily(symbols=None, period="1y"):
    """Daily closes (free) for the trend filter."""
    symbols = symbols or s.SYMBOLS
    (s.DATA_DIR / "daily").mkdir(parents=True, exist_ok=True)
    raw = yf.download([x + ".NS" for x in symbols], period=period, interval="1d",
                      group_by="ticker", progress=False, auto_adjust=False, threads=True)
    n = 0
    for sym in symbols:
        try:
            d = raw[sym + ".NS"][["Close"]].dropna()
        except KeyError:
            continue
        if not d.empty:
            d.to_csv(_daily_path(sym))
            n += 1
    return n


def load_daily(symbol):
    p = _daily_path(symbol)
    if not p.exists():
        return None
    d = pd.read_csv(p, index_col=0, parse_dates=True)["Close"]
    d.index = d.index.date
    return d
