"""All settings for the trading system live in this one file.

Two kinds of settings:
  1. Risk limits  - fixed by you. They protect the capital and are NOT tuned
                    to make a backtest look better.
  2. Rule settings - starting values. The backtest decides whether they stay.
"""

from pathlib import Path

# ---------------------------------------------------------------- folders ---
ROOT = Path(__file__).resolve().parent
UNIVERSE_FILE = ROOT / "universe" / "nifty200.csv"   # fallback list only
DATA_DIR = ROOT / "data"
MEMBERSHIP_FILE = DATA_DIR / "universe" / "nifty500_membership.csv"
INDUSTRY_FILE = DATA_DIR / "universe" / "nifty500_list.csv"
PRICES_DIR = DATA_DIR / "prices"      # one CSV per stock
MARKET_DIR = DATA_DIR / "market"      # Nifty, India VIX, global indices
REPORTS_DIR = ROOT / "reports"
JOURNAL_FILE = ROOT / "journal" / "trades.csv"

# ------------------------------------------------------------------- data ---
HISTORY_START = "2015-01-01"

# Which stocks were in the Nifty 500 on each past date. Built by a public
# GitHub project from NSE's own inclusion/exclusion records.
MEMBERSHIP_SOURCE = (
    "https://raw.githubusercontent.com/rishabhjain0295-web/"
    "nifty500-momentum-backtest/master/data/"
)

# Name we use -> Yahoo Finance ticker
MARKET_SYMBOLS = {
    "NIFTY50": "^NSEI",
    "INDIAVIX": "^INDIAVIX",
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "FTSE100": "^FTSE",
    "NIKKEI225": "^N225",
    "HANGSENG": "^HSI",
    "SHANGHAI": "000001.SS",
    "USDINR": "INR=X",
    "BRENT": "BZ=F",
    "GOLD": "GC=F",
}
BENCHMARK = "NIFTY50"

# ------------------------------------------------- risk limits (fixed) ------
CAPITAL = 100_000                # rupees
RISK_PER_TRADE = 0.01            # lose at most 1% of capital if the stop is hit
MAX_POSITIONS = 4                # open positions at one time
MAX_POSITION_FRACTION = 0.25     # no single position above 25% of capital
TOTAL_DRAWDOWN_LIMIT = 0.20      # stop taking new trades after a 20% loss

# ------------------------------------------- rule settings (to be tested) ---
EMA_FAST = 20                    # short-term trend
EMA_SLOW = 50                    # medium-term trend
RSI_PERIOD = 14
RSI_MIN = 50                     # momentum present ...
RSI_MAX = 70                     # ... but not overbought
ATR_PERIOD = 14
ATR_STOP_MULTIPLE = 1.5          # stop-loss = entry - 1.5 x ATR
TARGET_R = 2.0                   # target = entry + 2 x (entry - stop)
VOLUME_AVG_DAYS = 20             # today's volume must beat this average
RS_LOOKBACK_DAYS = 63            # about 3 months, for strength versus Nifty
MIN_TURNOVER_CRORE = 50          # average daily traded value, liquidity filter
MARKET_EMA = 50                  # new trades only when Nifty is above this EMA
MIN_HISTORY_DAYS = 100           # ignore a stock until it has this much data

# ------------------------------------------------------ trading costs -------
# Zerodha equity delivery, from zerodha.com/charges (checked 10 Oct 2026).
# Re-check these when Zerodha or the exchanges revise them.
BROKERAGE = 0.0                  # delivery is zero brokerage
STT = 0.001                      # 0.1% on buy and on sell
EXCHANGE_TXN = 0.0000307         # NSE 0.00307%
SEBI_FEE = 0.000001              # Rs 10 per crore
STAMP_DUTY = 0.00015             # 0.015% on buy only
GST = 0.18                       # on brokerage + SEBI fee + exchange charges
DP_CHARGE = 15.34                # per stock, per sell day

# Real fills are slightly worse than the planned price. 0.05% each side.
SLIPPAGE = 0.0005

# --------------------------------------------- company fundamentals ---------
FUNDAMENTALS_DIR = DATA_DIR / "fundamentals"
ANNUAL_FILE = FUNDAMENTALS_DIR / "annual.csv"          # yearly results per company
QUARTERLY_FILE = FUNDAMENTALS_DIR / "quarterly.csv"    # quarterly results
RESULTS_DATES_FILE = FUNDAMENTALS_DIR / "results_dates.csv"
DIVIDENDS_FILE = FUNDAMENTALS_DIR / "dividends.csv"
FUNDAMENTALS_REFRESH_DAYS = 7    # company numbers change slowly; refresh weekly

# A year's results become public some weeks after the year ends. In a backtest
# we only use them from this many days after the year end, never earlier.
REPORTING_LAG_DAYS = 75

# Quality filter: the business behind the chart must pass ALL of these.
USE_QUALITY_FILTER = True
QUALITY_REQUIRE_PROFIT = True        # last full year was profitable
QUALITY_MIN_SALES_GROWTH = 0.0       # sales did not shrink
QUALITY_MIN_RETURN_ON_EQUITY = 0.10  # earns at least 10% on shareholders' money
QUALITY_MAX_DEBT_TO_EQUITY = 2.0     # not applied to banks and finance companies
FINANCIAL_INDUSTRY = "Financial Services"

# No new trade this many calendar days before a company's results (or on the day).
USE_RESULTS_BLOCK = True
RESULTS_BLOCK_DAYS = 5

# Company scorecard: ten yes/no checks shown on the company card and in the
# daily report. The score is the number of checks passed. These thresholds are
# common rules of thumb. They have not been proven by a backtest.
SCORE_MIN_GROWTH = 0.10              # sales and profit growth of at least 10%
SCORE_MIN_RETURN_ON_EQUITY = 0.15
SCORE_MIN_NET_MARGIN = 0.10
SCORE_MAX_DEBT_TO_EQUITY = 1.0       # not applied to banks and finance companies

# ------------------------------------------------------ shareholding --------
# Who owns each company: promoters, foreign funds (FII), Indian funds (DII,
# which includes mutual funds) and the public. From the quarterly filings
# companies make to NSE.
SHAREHOLDING_FILE = FUNDAMENTALS_DIR / "shareholding.csv"
FUND_HOLDERS_FILE = FUNDAMENTALS_DIR / "mutual_fund_holders.csv"
SHAREHOLDING_QUARTERS = 2        # how many recent quarters to download per company
NSE_SITE = "https://www.nseindia.com"
