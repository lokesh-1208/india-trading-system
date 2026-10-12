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
PRICES_CACHE = DATA_DIR / "prices_cache.pkl"   # all price files combined, for speed
MARKET_DIR = DATA_DIR / "market"      # Nifty, India VIX, global indices
REPORTS_DIR = ROOT / "reports"
JOURNAL_FILE = ROOT / "journal" / "trades.csv"
REAL_TRADES_FILE = ROOT / "journal" / "real_trades.csv"   # your real-money trades

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
SHAREHOLDING_QUARTERS = 20       # about 5 years. Each quarter is downloaded only once,
                                 # so the first run is long and later runs are quick.
NSE_SITE = "https://www.nseindia.com"

# ----------------------------------------- ownership rotation (rule set D) --
# Hold the stocks where foreign funds and mutual funds raised their holding
# last quarter and the price has been strong. See trading/rotation.py.
ROTATION_POSITIONS = 10          # stocks held, in equal amounts
ROTATION_KEEP_RANK = 20          # a holding is kept while it stays in the top 20
ROTATION_MOMENTUM_DAYS = 126     # price strength over about 6 months
ROTATION_FILING_DAYS = 30        # wait this long after a quarter ends for filings
ROTATION_MARKET_SMA = 200        # all cash while Nifty is below this average
ROTATION_START = "2022-02-01"    # the shareholding history begins in late 2021
PAPER_START = "2026-10-12"       # paper portfolio: followed from this day, no real money

# ------------------------------------------------ full model (rule set E) ---
# Every factor the system collects goes into one score per stock, from 0 to 100.
# Each factor is turned into a rank among that day's stocks, the ranks are
# averaged inside each group, and the groups are combined with these weights.
# The weights are a starting judgement. They were not tuned on past results.
MODEL_WEIGHTS = {
    "ownership": 0.25,     # FII, mutual fund, promoter, DII, insurer, public changes; pledge
    "business": 0.20,      # growth, margins, return on equity, debt, quarterly results, scorecard
    "valuation": 0.15,     # PE against its industry, price to book, earnings yield, dividend yield
    "price": 0.25,         # 6-month strength, trend (EMA), RSI, volume, ATR, distance from high
    "news": 0.075,         # company announcements in the last 30 days
    "flows": 0.075,        # bulk and block deals in the stock in the last 30 days
}
MODEL_MARKET_MIN = 0.5         # buy only when at least half the market checks pass
MODEL_VIX_MAX = 20             # India VIX above this counts as a fearful market
MODEL_RUPEE_FALL_MAX = 0.02    # rupee weaker by more than 2% in a month fails its check
MODEL_CRUDE_RISE_MAX = 0.15    # crude oil up more than 15% in a month fails its check
MODEL_GOLD_RISE_MAX = 0.08     # gold up more than 8% in a month (money running to safety)
MODEL_MONTH_DAYS = 21          # trading days in "a month" for the checks above
MODEL_QUARTER_LAG_DAYS = 45    # a quarter's results are used from this long after it ends
MODEL_NEWS_DAYS = 30

# Two ways to trade the same score. "swing" is checked every week and holds
# for days to a few weeks; "monthly" is checked once a month.
MODEL_STYLES = {
    # Swing follows each stock's own trend: bought from the top 10 at the weekly
    # check, held while it closes above its 20-day EMA, sold when it does not.
    # max_gap: a buy is skipped if the stock opens more than 2% above the signal
    # close (backtest log, entry 7). No lower limit: buying below it did well.
    "swing": {"check": "week", "positions": 5, "keep_rank": 10, "buy_rank": 10,
              "rank_exit": False, "stop_loss": 0.08, "trend_exit": True, "max_gap": 0.02},
    "monthly": {"check": "month", "positions": 10, "keep_rank": 20, "buy_rank": 20,
                "rank_exit": True, "stop_loss": None, "trend_exit": False},
}
MODEL_STYLE = "swing"
SPIKE_DAYS = 5                 # "recent spike" = rise over this many trading days
MODEL_STRONG_MARKET = 0.75     # at or above this share of checks, with Nifty above its
                               # 200-day average, the market is called strong
MODEL_WEAKEST = 10             # how many of the lowest scores to list as sell / avoid

# ------------------------------------------------------------ short side ----
# Selling first and buying back later, for the weakest scores. Two routes:
# intraday (sell and buy back the same day) and stock futures (can be held).
FO_LOTS_FILE = DATA_DIR / "universe" / "fo_lots.csv"     # which stocks have futures, lot sizes
FO_LOTS_SOURCE = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"
SHORT_POSITIONS = 5
SHORT_POOL = 20                # shorts are picked from this many weakest scores
SHORT_STOP_LOSS = 0.08         # cover if the price closes this far above the sell price
SHORT_COST = 0.0003            # futures charges per side as a share of value (approximate)
SHORT_ORDER_FEE = 20.0         # brokerage per futures order
INTRADAY_STOP_ATR = 1.5        # intraday stop: this many ATRs above the sell price

# ------------------------------------------------- news and money flows -----
ANNOUNCEMENTS_FILE = DATA_DIR / "news" / "announcements.csv"   # company announcements to NSE
FII_DII_FILE = DATA_DIR / "flows" / "fii_dii.csv"              # daily buying and selling
LARGE_DEALS_FILE = DATA_DIR / "flows" / "large_deals.csv"      # bulk and block deals
ANNOUNCEMENT_DAYS_FIRST_RUN = 10     # how far back the first download goes
ANNOUNCEMENT_DAYS_KEPT = 400         # older announcements are dropped from the file
