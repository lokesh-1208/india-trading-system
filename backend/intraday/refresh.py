"""Download and cache the latest free 5-minute and daily candles. Run after the market closes."""

from . import data
from . import settings as s

if __name__ == "__main__":
    symbols = sorted(set(s.SYMBOLS) | set(s.wide_symbols(500)))
    print(f"{data.refresh(symbols)} stocks updated (5-minute), {len(symbols)} requested")
    print(f"{data.refresh_daily(s.SYMBOLS)} stocks updated (daily)")
