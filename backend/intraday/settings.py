"""All intraday settings in one place. Nothing here touches the swing model."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "intraday"
REPORT_DIR = ROOT / "reports"

# ---- money ---------------------------------------------------------------
CAPITAL = 200_000            # intraday capital
RISK_PER_TRADE = 500         # rupees lost if the stop is hit (before charges)
MARGIN_X = 2                 # max position value = capital x this (MIS leverage varies by stock)
MAX_TRADES_PER_DAY = 3
DAILY_LOSS_LIMIT = 1000      # stop taking new trades once the day is this far down

# ---- entry / exit rules (5-minute candles) --------------------------------
OR_CANDLES = 3               # opening range = first 15 minutes (9:15-9:30)
LAST_ENTRY = "14:30"         # no new signals after this
EXIT_TIME = "15:15"          # square off; Zerodha auto square-off is later and costs extra
TARGET_R = 1.5               # target = 1.5 x the stop distance
MIN_STOP_PCT = 0.003         # stops tighter than 0.3% are widened (noise)
MAX_STOP_PCT = 0.012         # stops wider than 1.2% are skipped (risk of a big move)
TOP_N = 5                    # candidates kept per day after ranking at 9:30
MIN_CANDLES = 70             # a full session has 75 five-minute candles
MIN_OR_RANGE_PCT = 0.003     # opening range must be at least 0.3% of price

# ---- costs ----------------------------------------------------------------
SLIPPAGE = 0.0005            # 0.05% each side, same as the swing model
BROKERAGE_PCT = 0.0003       # 0.03% or Rs 20 per order, whichever is lower
BROKERAGE_CAP = 20
STT_SELL = 0.00025           # intraday: 0.025% on the sell side only
EXCHANGE_TXN = 0.0000307
SEBI_FEE = 0.000001
STAMP_BUY = 0.00003          # 0.003% on the buy side
GST = 0.18

# Liquid large caps: tight spreads, so 5-minute candles are meaningful.
SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "BHARTIARTL", "ITC",
    "LT", "KOTAKBANK", "AXISBANK", "HINDUNILVR", "BAJFINANCE", "MARUTI", "SUNPHARMA",
    "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID", "ONGC", "ADANIENT", "ADANIPORTS",
    "WIPRO", "HCLTECH", "TECHM", "M&M", "ASIANPAINT", "ULTRACEMCO", "TITAN", "NESTLEIND",
    "JSWSTEEL", "COALINDIA", "BAJAJFINSV", "INDUSINDBK", "HINDALCO", "GRASIM", "CIPLA",
    "DRREDDY", "EICHERMOT", "BPCL", "HEROMOTOCO", "BRITANNIA", "APOLLOHOSP", "DIVISLAB",
    "TATACONSUM", "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "SHRIRAMFIN", "TRENT",
    "BANKBARODA", "PNB", "CANBK", "VEDL", "DLF", "IOC", "GAIL", "HAL", "BEL", "IRCTC",
]


def wide_symbols(size=200):
    """Nifty 200 or Nifty 500 symbols from the project's universe files (the 'stocks in play' test)."""
    import csv
    path = (ROOT / "universe" / "nifty200.csv") if size == 200 else (ROOT / "data" / "universe" / "nifty500_list.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return [r["Symbol"] for r in csv.DictReader(f) if r.get("Symbol")]


# ---- live use (the Intraday tab) ------------------------------------------
JOURNAL_FILE = ROOT / "journal" / "intraday_trades.csv"     # your intraday trades, local only
LAST_SCAN_FILE = DATA_DIR / "last_scan.json"
ZERODHA_APP_FILE = ROOT / "journal" / "zerodha_app.json"    # API key and secret, local only
ZERODHA_TOKEN_FILE = ROOT / "data" / "zerodha_token.json"   # today's login, local only
TICK = 0.05                  # NSE price tick for most stocks
GAP_MIN = 0.01               # "in play": opens at least 1% away from yesterday's close ...
REL_VOL_MIN = 2.0            # ... on at least 2x the normal opening-15-minute volume
INPLAY_MAX_STOP_PCT = 0.025  # gap stocks open with wide ranges, so allow wider stops
INPLAY_SLIPPAGE = 0.001      # thinner stocks: 0.10% each side
SIGNAL_MAX_AGE_CANDLES = 3   # a signal older than this is marked "late"
WATCH_N = 20                 # stocks shown on the page; only the top TOP_N match what was backtested
NEAR_GAP = 0.005             # "near miss": gap of at least 0.5% ...
NEAR_REL_VOL = 1.5           # ... on at least 1.5x normal opening volume (not tested)
PHASES = {                   # clock rules, IST
    "range_start": "09:15", "range_end": "09:30",
    "last_entry": LAST_ENTRY, "square_off": EXIT_TIME, "close": "15:30",
}
RULES = {
    "gap_go": "Gap-and-go (tested top 5)",
    "gap_go_wide": "Gap-and-go (wider list, untested)",
    "orb": "Opening-range breakout",
    "pullback": "VWAP pullback",
    "own": "Own idea",
}
