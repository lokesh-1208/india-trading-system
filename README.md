# Kasauti

[![Tests](https://github.com/lokesh-1208/india-trading-system/actions/workflows/tests.yml/badge.svg)](https://github.com/lokesh-1208/india-trading-system/actions/workflows/tests.yml)

*Kasauti (कसौटी) is the touchstone used to test gold. Nothing goes into this model until it has passed a test on past data.*

Kasauti is a rule-based swing trading system for Indian stocks (Nifty 500), written in
Python. It downloads free end-of-day data, scores every stock from 0 to 100, and shows
one page each morning: what to buy (with a buy range and stop-loss), what to do with the
stocks you hold, and what to avoid. Orders are placed by hand in your broker's app.

This is a personal learning project, not investment advice. A backtest shows how rules
behaved in the past and does not promise future results.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python update_data.py
```

The first download takes a few minutes.

## Daily use

1. **Open the app:** double-click `start_kasauti.bat`. Kasauti opens in your browser at
   http://127.0.0.1:8765. Keep the black window open while you use it.
2. **Each evening after 6 pm:** press **Update data** on the Today page (or let the
   scheduled update do it, see the end of this file).
3. **Each morning:** read the **Today** page; **Before open** shows what happened overnight.
4. **After you buy or sell:** record it under **Trades**. From then on the Today page tells
   you each day whether to hold it or sell it.

## The web app

| Page | What it shows |
|---|---|
| Today | What to do: buy cards from the weekly list (price bar with stop-loss, last price and buy limit, number of shares), your stocks with Hold or Sell, the rest of the week's list with why it is not buyable, the week tracker, and cards for Before the open, News ideas and Market mood. |
| Before open | Global markets since our close, overnight NSE filings, NSE pre-open prices (after 9:08 am), and stocks likely to open up or down. For context. |
| News & movers | News ideas with the model's view, the stocks with heavy buying or selling, and what usually happened after each kind of news. For context. |
| Market | The model's market checks, world markets, institutions' buying, and the backtest against Nifty. |
| Stocks | One stock: candlestick chart (TradingView lightweight-charts) with the 20-day average, buy limit and stop-loss; the model's view; ROCE, cash flow, scorecard, owners, news, reports. |
| Trades | Record buys and sells; profit after charges. |

How it is built: `server/` is a small FastAPI server that answers the page's questions
from the existing `trading/` code; `web/` is the page, written in React and TypeScript.
The built page (`web/dist`) is kept in the repository, so Node.js is only needed to change
the page (`cd web`, `npm install`, `npm run build`; `npm run dev` for live editing with
the server running). Tests: `python -m pytest` for the server and model, and
`npx playwright test` in `web/` for the page (it uses saved example answers, so it needs
no data).

## The Today page

The buy list is the tested one: made from the close before the first trading day of the
week, with limits fixed all week. Each stock on it is shown as Buy, Backup, Missed (above
its limit), Trend broke, Results soon, Too costly or You hold. Your stocks show Hold, Sell
or Bought today, the close that would trigger a sell, what you would make or lose if it
exited now, and the GTT stop-loss to keep in Kite. The week tracker shows every day's
top-10 list this week (saved in `journal/picks_log.csv`) with each stock's change since it
was first picked against Nifty. Before the open, news ideas and market mood are for
context: they are not buy or sell signals.

## The model

**Score.** Every liquid Nifty 500 stock (average daily traded value above Rs 50 crore) gets
one score from 0 to 100. Each factor is ranked among that day's stocks and the groups are
combined with fixed weights, set by judgement and not tuned on past results:

| Group | Weight | Factors |
|---|---|---|
| Ownership | 25% | Changes in FII, mutual fund, promoter, DII, insurer and public holding; pledged shares; number of fund schemes |
| Price | 25% | 6-month strength, EMA trend, RSI, volume, ATR, distance from the 52-week high |
| Business | 20% | Sales and profit growth (1 and 3 years), margin, return on equity, debt, latest quarter, a ten-point scorecard |
| Valuation | 15% | PE against its industry, price to book, earnings yield, dividend yield |
| News | 7.5% | Company announcements to NSE in the last 30 days |
| Deals | 7.5% | Bulk and block deals in the last 30 days |

**Market check.** Eight yes/no checks: Nifty against its 200-day average and 50-day EMA,
India VIX below 20, global markets, the rupee, crude oil, gold and 5-day FII buying. New
buys only when at least half pass.

**Buying.** Checked once a week. Up to 5 stocks from the top 10 scores. Each gets an equal
share of the money in a strong market and 75% of that share when the market is only
"caution" (buying allowed but not strong).
A stock is bought only if it is above its 20-day EMA and its results are not due within
the next 5 days (counted from the day you buy).

**Buy range.** Any price up to 2% above the signal close. There is no lower limit.

**Selling.** At the next open after a close below the 20-day EMA, or a close 8% below
your buy price, whichever comes first.

Every setting is in `config.py` (`MODEL_STYLES` and `MODEL_WEIGHTS`).

## How it did in the past

1 February 2022 to 9 October 2026, Rs 1,00,000 start, after Zerodha delivery charges and
0.05% slippage on each side:

| | Growth a year | Worst fall |
|---|---|---|
| Kasauti | about +19% | about -18% |
| Nifty 50, bought and held | about +5% | about -16% |

Not proven for real money. The history is under five years and most company data only
covers the last few years. Results are sensitive to the settings (for example the exit-line
length), so treat the figures as a rough guide. Every test, including the ones that failed, is recorded in the project's
backtest log; the scripts are in `research/`.

What was tested and kept:

- **Smaller amounts in a caution market (75%).** Worst fall from -20.7% to -18.1%, smaller in
  both halves of the history, for about 1 point less growth a year (`research/strength.py`).

- **The 2% buy range.** Buying after the stock had already risen more than 2% from the
  signal close lost money. Buying below the signal close did well (`research/entry_gap.py`).
- **No buying just before results.** Slightly better growth and a smaller worst fall in
  every setting tested.

What was tested and rejected (13 Oct 2026, `research/strength.py`, each mixed between the
two halves of the history): selling before results, 4 / 6 / 8 stocks, a 6-12% stop or none,
buying from the top 5 / 15 / 20, exit lines from 10 to 75 days, smaller amounts for
high-swing stocks. Score groups: business, valuation and price each help; ownership helped in
2022-24 and hurt in 2024-26; news and deals cannot be judged yet (only days of history).
From every start date since 2022 the model beat Nifty by 10-25 points a year.


- A lower limit on the buy range, limit orders at the signal close, skipping stocks close
  to their trend line or after a spike (`research/entry_quality.py`).
- Six other rule sets: a chart breakout, monthly momentum, pullback buying, new-high
  breakouts, an ownership-only rotation and short selling the weakest scores.

## Commands

| Command | What it does |
|---|---|
| `start_kasauti.bat` | Opens the app. Its **Update data** button does the same job as `update_data.py`. |
| `python update_data.py` | Downloads prices for about 800 stocks, index membership history, Nifty, India VIX, global markets, the rupee, crude, gold, company announcements, FII/DII figures, bulk and block deals, results of companies that just reported, and (weekly) shareholding into `data/`. Daily prices come from NSE's day file; the full Yahoo history is downloaded once a week. |
| `python research/full_model.py` | Runs the model through the past and prints its results and today's scores. |
| `python research/entry_gap.py` | The buy-range test. |
| `python stock_card.py TCS` | Everything known about one company: price range, valuation, growth, profitability, debt, dividend, shareholding and a ten-point scorecard. |
| `python -m pytest` | Runs the automated checks. GitHub runs them on every pull request. |
| `python run_backtest.py`, `python daily_report.py` | The first rule set (chart breakout), kept for reference only. It lost money in its test. |

## Project layout

```
config.py                all settings: model weights, trading rules, risk limits, charges
server/                  the app's local web server (FastAPI): what each page shows
web/                     the app's page (React, TypeScript); web/dist is the built page
trading/model.py         the model: every factor in one score per stock, market checks
trading/rotation.py      the day-by-day simulation used to test the model
trading/today.py         the Today page's lists: buy range, hold or sell, avoid, events
trading/picks.py         each day's top-10 list, saved; the weekly list, tracker and track record
trading/breadth.py       market breadth and sector strength (not shown in the app yet)
trading/journal.py       your real trades (journal/real_trades.csv, not on GitHub)
trading/update.py        refreshes all data; shared by update_data.py and the app
trading/data.py          downloads and loads prices and index membership
trading/indicators.py    EMA, RSI, ATR
trading/fundamentals.py  company results, ratios, results dates, which companies are due
trading/gaps.py          daily prices from NSE's day file (bhavcopy); fills days Yahoo misses
trading/movers.py        market movers on the Today page: heavy buying/selling and why (info only)
trading/premarket.py     before the open: global moves, overnight news, NSE pre-open prices (info only)
trading/newsview.py      reads announcements as good or bad; news ideas; what usually happened after news
trading/filings.py       company results from NSE's own filings (XBRL): 2018 on, cash flow, ROCE, filing times
trading/pledge.py        % of promoter shares pledged (NSE)
trading/shareholding.py  who owns each company: promoters, FII, DII, mutual funds, public
trading/news.py          company announcements to NSE, sorted into plain categories
trading/flows.py         daily FII/DII buying and selling, bulk and block deals
trading/nse.py           opens a session with the NSE website
trading/company.py       the company card
trading/charges.py       Zerodha delivery charges
trading/shorts.py        the short-selling test (failed; kept for reference)
trading/backtest.py, strategy.py, screens.py, report.py   the first rule set (reference only)
research/                scripts behind every test in the backtest log
tests/                   automated checks
universe/                fallback stock list, used only if the membership download fails
```

`data/`, `reports/` and `journal/` are created when you run the scripts and are not
committed to Git. Keep your own backup of `journal/real_trades.csv`.

## Stock universe

Past dates use the Nifty 500 members as they were on that date, not today's list. A stock
that was later dropped from the index is still included for the years it was a member.
Testing only today's members would make every result look better than it was, because
today's list contains only the companies that survived and grew.

The membership history comes from the public project
[nifty500-momentum-backtest](https://github.com/rishabhjain0295-web/nifty500-momentum-backtest),
which built it from NSE's inclusion/exclusion records. `update_data.py` downloads it into
`data/universe/`. It is not stored in this repository.

That history file sometimes misses a stock that is on NSE's current Nifty 500 list (ITC,
Tata Power and Federal Bank were missing in October 2026). Such a stock is counted as a
member from one year ago, so it appears in today's list while older backtests leave it out.

## Known limits

- **Short history.** Shareholding filings start in 2021 and Yahoo Finance gives about four
  years of yearly results, so the model can only be tested from February 2022.
- **Some survivorship bias remains.** Price data exists for about 410 of the 500 members in
  2015, rising to about 487 in 2026. The missing ones are mostly delisted, merged or
  bankrupt companies. Real results would be somewhat worse than shown.
- **Membership dates after 2020 are approximate.** They come from snapshots a few months
  apart.
- **News and deals history is short.** It grows by one day with each update, so for most
  of the test period those parts counted as average.
- **Daily data only.** The test buys at the open after the signal; it cannot see prices
  during the day.
- **Benchmark.** Stock prices include dividends, the Nifty 50 index does not. This favours
  the model by roughly 1% a year.
- **Tax is not included** in the results. Charges are.
- **Free data.** Yahoo Finance prices occasionally have gaps or errors. Demergers show up
  as a one-day price fall.

## Data sources

- Prices, company results, dividends, results dates: Yahoo Finance.
- Shareholding pattern, company announcements, FII/DII figures, bulk and block deals: NSE.
  The shareholding filing names only holders above 1%, so the list of mutual fund schemes
  is not complete.
- Index membership history: see "Stock universe" above.

## Not built yet

- A link to the broker (Zerodha), so trades are recorded automatically.
- Intraday trading (needs minute-by-minute prices).

## Without typing commands (Windows)

- `start_kasauti.bat`: double-click to open the app. Right-click it and choose
  "Send to > Desktop (create shortcut)" to get a desktop icon.
- `schedule_daily_update.bat`: double-click once. Windows will then download the latest
  data every weekday at 6:30 pm, and refresh the before-the-open data at 9:10 am (the
  laptop must be on). The log is `reports/update_log.txt`.
