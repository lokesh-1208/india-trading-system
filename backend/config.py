"""All settings for the trading system live in this one file.

Two kinds of settings:
  1. Risk limits  - fixed by you. They protect the capital and are NOT tuned
                    to make a backtest look better.
  2. Rule settings - starting values. The backtest decides whether they stay.
"""

from pathlib import Path

# ---------------------------------------------------------------- folders ---
# The project folder (this file is in backend/): data, journal and reports live there.
ROOT = Path(__file__).resolve().parent.parent
UNIVERSE_FILE = ROOT / "universe" / "nifty200.csv"   # fallback list only
DATA_DIR = ROOT / "data"
MEMBERSHIP_FILE = DATA_DIR / "universe" / "nifty500_membership.csv"
INDUSTRY_FILE = DATA_DIR / "universe" / "nifty500_list.csv"
PRICES_DIR = DATA_DIR / "prices"      # one CSV per stock
PRICES_CACHE = DATA_DIR / "prices_cache.pkl"   # all price files combined, for speed
MARKET_DIR = DATA_DIR / "market"      # Nifty, India VIX, global indices
REPORTS_DIR = ROOT / "reports"
REAL_TRADES_FILE = ROOT / "journal" / "real_trades.csv"   # your real-money trades
PICKS_LOG_FILE = ROOT / "journal" / "picks_log.csv"    # every day's top-10 list, kept as made
DAILY_LIST_SIZE = 10
# The weekly list also carries the best stocks of each sector (NSE's industry label),
# so the money can be spread across sectors by your own choice. Up to this many per
# sector, counting the top 10; a sector with more in the top 10 keeps them all.
SECTOR_PICKS = 3
# A sector stock must score at least this (the model calls 60+ strong, 40 or less weak).
SECTOR_MIN_SCORE = 50
SHORT_TERM_TAX = 0.20     # tax on gains from shares held under a year (rule in force in 2026;
                          # check with your CA). Losses in the same year reduce taxable gains.

# ------------------------------------------------------------------- data ---
HISTORY_START = "2015-01-01"

# Which stocks were in the Nifty 500 on each past date. Built by a public
# GitHub project from NSE's own inclusion/exclusion records.
MEMBERSHIP_SOURCE = (
    "https://raw.githubusercontent.com/rishabhjain0295-web/"
    "nifty500-momentum-backtest/master/data/"
)
# A stock on NSE's current Nifty 500 list that the history file leaves out is
# counted as a member from this many days ago (its older history is unknown).
MISSING_MEMBER_START_DAYS = 365

# The full price history is downloaded from Yahoo once a week. On other days
# only the new days are added from NSE's day file, which is much faster.
FULL_PRICES_REFRESH_DAYS = 7
FULL_PRICES_MARKER = DATA_DIR / "prices_full_download.txt"   # date of the last full download
YAHOO_NO_DATA_FILE = DATA_DIR / "yahoo_no_data.txt"   # delisted stocks; retried weekly only
# NSE's previous close differing from the saved close by more than this means a
# split, bonus or big dividend: that stock's full history is downloaded again.
CORPORATE_ACTION_GAP = 0.01

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
    "SP500_FUTURES": "ES=F",     # trade almost round the clock: the US mood before India opens
    "NASDAQ_FUTURES": "NQ=F",
}
BENCHMARK = "NIFTY50"

# ------------------------------------------------- risk limits (fixed) ------
CAPITAL = 100_000                # rupees

# ------------------------------------------- rule settings (to be tested) ---
EMA_FAST = 20                    # short-term trend
EMA_SLOW = 50                    # medium-term trend
RSI_PERIOD = 14
ATR_PERIOD = 14
ATR_STOP_MULTIPLE = 1.5          # stop-loss = entry - 1.5 x ATR
VOLUME_AVG_DAYS = 20             # today's volume must beat this average
MIN_TURNOVER_CRORE = 50          # average daily traded value, liquidity filter
MARKET_EMA = 50                  # new trades only when Nifty is above this EMA

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
FUNDAMENTALS_REFRESH_DAYS = 7    # shareholding filings are checked once a week
RESULTS_FETCHED_FILE = FUNDAMENTALS_DIR / "results_fetched.csv"   # when each company was fetched
# Company results from NSE's own filings (trading/filings.py), preferred to Yahoo.
NSE_RESULTS_FILE = FUNDAMENTALS_DIR / "nse_results.csv"     # every filing read, per period
NSE_TRIED_FILE = FUNDAMENTALS_DIR / "nse_filings_tried.csv" # filings already downloaded
NSE_CHECKED_FILE = FUNDAMENTALS_DIR / "nse_checked.csv"     # when each company's list was checked
FILINGS_BACKFILL_SECONDS = 240          # first download: at most this long per daily update
FILINGS_START = "2016-03-31"            # NSE's machine-readable filings start about here
FILINGS_ALL_QUARTERS_FROM = "2020-03-31"  # every quarter from here; before, March and Sept only
FILINGS_WORKERS = 6                     # companies downloaded at the same time
FILINGS_PAUSE = 0.2                     # seconds between two downloads, to be polite to NSE
# Company results are downloaded only for companies that are due (see
# fundamentals.due_symbols): just announced results, or not checked for a month.
RESULTS_WATCH_DAYS = 21          # keep checking this long after a results announcement
RESULTS_FULL_REFRESH_DAYS = 30   # every company is checked again at least this often

# A year's results become public some weeks after the year ends. In a backtest
# we only use them from this many days after the year end, never earlier.
REPORTING_LAG_DAYS = 75

# Banks and finance companies are judged without the debt check on the company card.
FINANCIAL_INDUSTRY = "Financial Services"

# No new trade this many calendar days before a company's results (or on the day).
RESULTS_BLOCK_DAYS = 5

# Company scorecard: twelve yes/no checks shown on the company card. The score is the number of checks passed. These thresholds are
# common rules of thumb. They have not been proven by a backtest.
SCORE_MIN_GROWTH = 0.10              # sales and profit growth of at least 10%
SCORE_MIN_RETURN_ON_EQUITY = 0.15
SCORE_MIN_NET_MARGIN = 0.10
SCORE_MAX_DEBT_TO_EQUITY = 1.0       # not applied to banks and finance companies
SCORE_MIN_ROCE = 0.15                # return on capital employed (not for banks and finance)
SCORE_MIN_CASH_CONVERSION = 0.8      # cash from operations / profit over 3 years (not finance)

# ------------------------------------------------------ shareholding --------
# Who owns each company: promoters, foreign funds (FII), Indian funds (DII,
# which includes mutual funds) and the public. From the quarterly filings
# companies make to NSE.
SHAREHOLDING_FILE = FUNDAMENTALS_DIR / "shareholding.csv"
FUND_HOLDERS_FILE = FUNDAMENTALS_DIR / "mutual_fund_holders.csv"
PLEDGE_FILE = FUNDAMENTALS_DIR / "pledges.csv"   # % of promoter shares pledged (NSE)
PLEDGE_RED_FLAG_PCT = 25.0       # more of the promoters' shares pledged than this: warning
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
# How the news group scores a stock's filings in the last MODEL_NEWS_DAYS:
#   "types": by filing type only (orders +1, dividends +0.5, legal -1, ...): the original
#   "lean":  each filing read as good or bad (-2..+2) by the news reader: results numbers,
#            rating up/down, auditor quitting, fraud, ... (trading/newsview.py rules, no
#            learning from later prices, so a backtest sees only what was known that day)
MODEL_NEWS_MODE = "types"
# The twelve-point scorecard inside the business group:
#   "fixed":    rule-of-thumb numbers (ROE >= 15%, margin >= 10%, ...): the original
#   "industry": each check against the company's own industry median
#   "off":      no scorecard (its checks repeat business factors already scored)
MODEL_SCORECARD = "fixed"
# Market breadth as a 9th market check: at least this share of liquid stocks above
# their 20-day EMA. None leaves it out (entry 10 of the backtest log).
# Share count used for PE, price/book and earnings yield: "latest" (matches the
# split-adjusted prices on every day) or "filed" (the count at the time: wrong after a
# split or bonus; the original behaviour, kept for comparison).
MODEL_SHARES = "latest"
MODEL_BREADTH_MIN = None       # tested 14 Oct 2026 at 40% and 50%: not adopted (entry 10)
EMA_PROFIT_TRAIL = 10          # the faster trend line a "fast" profit trail sells on

# Two ways to trade the same score. "swing" is checked every week and holds
# for days to a few weeks; "monthly" is checked once a month.
MODEL_STYLES = {
    # Swing follows each stock's own trend: bought from the top 10 at the weekly
    # check, held while it closes above its 20-day EMA, sold when it does not.
    # max_gap: a buy is skipped if the stock opens more than 2% above the signal
    # close (backtest log, entry 7). No lower limit: buying below it did well.
    "swing": {"check": "week", "positions": 5, "keep_rank": 10, "buy_rank": 10,
              "rank_exit": False, "stop_loss": 0.08, "trend_exit": True, "max_gap": 0.02,
              # In a caution market (buying allowed but not strong) each new buy gets 75%
              # of the normal amount. Tested 13 Oct 2026: worst fall -20.7% -> -18.1%,
              # smaller in both halves of the history, growth 19.6% -> 18.7% a year.
              "caution_share": 0.75,
              # Sell only after TWO closes in a row below the 20-day EMA, not the first
              # one. Tested 16 Oct 2026 after three real losses (backtest log, entry 11):
              # better growth and a smaller worst fall in all three periods since 2018,
              # with 4, 5 and 6 stocks and from every start month tried.
              "exit_confirm": 2,
              # Size each buy so a 1.5 x ATR fall costs about 1% of the account; a calm
              # stock still gets the normal place. Tested 16 Oct 2026: smaller worst fall in
              # all three periods, growth a little lower in 2022-24 (entry 11).
              "risk_per_trade": 0.01},
              # A profit trail ("profit_trail": {"trigger": 0.15, "trail": 0.10}) was tested
              # on 14 Oct 2026 and not adopted: no clear effect once share counts were fixed
              # (backtest log, entry 10). The option stays in rotation.simulate.
    "monthly": {"check": "month", "positions": 10, "keep_rank": 20, "buy_rank": 20,
                "rank_exit": True, "stop_loss": None, "trend_exit": False},
}
MODEL_STYLE = "swing"
SPIKE_DAYS = 5                 # "recent spike" = rise over this many trading days
MODEL_STRONG_MARKET = 0.75     # at or above this share of checks, with Nifty above its
                               # 200-day average, the market is called strong
MODEL_WEAKEST = 10             # how many of the lowest scores to list as sell / avoid

# ------------------------------------------------- news and money flows -----
ANNOUNCEMENTS_FILE = DATA_DIR / "news" / "announcements.csv"   # company announcements to NSE
FII_DII_FILE = DATA_DIR / "flows" / "fii_dii.csv"              # daily buying and selling
LARGE_DEALS_FILE = DATA_DIR / "flows" / "large_deals.csv"      # bulk and block deals
# A missed FII/DII day is warned about for this many trading days, then dropped: the
# figures can never be fetched later (NSE keeps only the latest day).
FLOW_MISS_WARN_DAYS = 5
ANNOUNCEMENT_DAYS_FIRST_RUN = 10     # how far back the first download goes
ANNOUNCEMENT_DAYS_KEPT = 400         # older announcements are dropped from the file

# ------------------------------------------------- market movers (info only) --
# The "Market movers" section on the Today page: stocks with unusually heavy
# buying or selling on the last day. Not part of the model; no buy or sell.
MOVERS_MIN_MOVE_PCT = 2.0        # price moved at least 2% up or down
MOVERS_MIN_VOLUME_X = 2.0        # on at least 2x the stock's normal volume
MOVERS_VOLUME_DAYS = 20          # normal volume = average of the previous 20 days
MOVERS_PER_SIDE = 20             # how many stocks to show on each side
MOVERS_SECTOR_MIN = 3            # this many movers in one industry = a sector move

# --------------------------------------------- before the open (info only) ---
PREMARKET_DIR = DATA_DIR / "premarket"
PREOPEN_FILE = PREMARKET_DIR / "preopen.csv"     # NSE pre-open session, 9:00-9:08 am
PREOPEN_MIN_PCT = 2.0            # set to open at least 2% up or down
# A global move counts as worth mentioning from this size (%), others from 1%.
PREMARKET_NOTABLE_PCT = {"USDINR": 0.4, "INDIAVIX": 5.0, "BRENT": 2.0, "GOLD": 1.5}

# ------------------------------------------------- reading the news (ideas) --
NEWS_PDF_DIR = DATA_DIR / "news" / "pdf_text"    # text of filings already read
NEWS_RESULTS_GOOD = 0.15         # profit up 15% on a year ago = good results, down 15% = bad
NEWS_DEAL_MIN_CRORE = 10         # bulk/block deals smaller than this are ignored
NEWS_REACTION_DAYS = 3           # "what happened next" is measured over 3 trading days
NEWS_MIN_CASES = 15              # fewer past cases than this: no average shown
NEWS_IDEA_DAYS = 5               # news of the last 5 calendar days makes ideas
NEWS_MAX_RUN_PCT = 8.0           # already up more than this since the news: too late
ANNOUNCEMENT_HISTORY_DAYS = 365  # how far back saved announcements are filled in once
