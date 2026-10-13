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

1. **Each evening after 6 pm:** press **Update data now** in the dashboard sidebar (or let
   the scheduled update do it, see the end of this file).
2. **Each morning:** open the dashboard (`start_dashboard.bat`, or
   `streamlit run dashboard.py`) and read the **Today** page.
3. **After you buy or sell:** record it under **My real trades** on the same page. From then
   on the page tells you each day whether to hold it or sell it.

## The Today page

| Part | What it shows |
|---|---|
| Market strip | Nifty 50, India VIX, USD/INR, Brent crude, gold and the S&P 500, with the day's change. |
| Headline | What to do today, for example "Buy 3 from the weekly list. Watch: 4 others", and the market mood: strong, caution or weak. |
| Buy: this week's list | The tested list, made from the close before the first trading day of the week. Each stock is marked Buy, Buy (backup), Missed (above its limit), Trend broke, Results soon, Too costly or You hold. Limits stay fixed all week. |
| Watch | Other names on today's fresh top 10. Not tested; for watching only. |
| This week's tracker | Every day's top-10 list this week (saved in `journal/picks_log.csv`), with each stock's rank per day, its change since first picked and Nifty over the same days. |
| Track record | Each weekly list's top 5 against Nifty since it was made: the live test of the model. |
| Your stocks | Each stock you recorded: Hold, Sell or Bought today, a bar with the hard stop, exit line, buy price and last close, what you would make or lose if it exited now, the GTT stop-loss to keep in Kite, and how long trades usually last. |
| Avoid | The weakest scores. Do not buy them. |
| Events | Ideas only, not tested: results due this week, results just out, and important company news. Each card is coloured by the model's view of the stock. |
| Record a trade | Forms to record a buy or a sell; profit after charges and an estimate of the tax on closed trades. |
| Details | The market checks, how the model did in the past, and every stock's score. |

The **Market** tab shows the market checks over time, breadth (how many stocks are in an
uptrend), sector strength, world markets and institutional buying. The **Company** tab shows
where a stock stands for you (held, on a list, to avoid), its price with your levels, peers in
the same industry, the business, owners, news and a rule-of-thumb scorecard.

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
| `streamlit run dashboard.py` | Opens the dashboard. Its **Update data now** button does the same job as `update_data.py`. |
| `python update_data.py` | Downloads prices for about 800 stocks, index membership history, Nifty, India VIX, global markets, the rupee, crude, gold, company announcements, FII/DII figures, bulk and block deals, results of companies that just reported, and (weekly) shareholding into `data/`. Daily prices come from NSE's day file; the full Yahoo history is downloaded once a week. |
| `python research/full_model.py` | Runs the model through the past and prints its results and today's scores. |
| `python research/entry_gap.py` | The buy-range test. |
| `python stock_card.py TCS` | Everything known about one company: price range, valuation, growth, profitability, debt, dividend, shareholding and a ten-point scorecard. |
| `python -m pytest` | Runs the automated checks. GitHub runs them on every pull request. |
| `python run_backtest.py`, `python daily_report.py` | The first rule set (chart breakout), kept for reference only. It lost money in its test. |

## Project layout

```
config.py                all settings: model weights, trading rules, risk limits, charges
dashboard.py             the browser dashboard (Streamlit)
trading/model.py         the model: every factor in one score per stock, market checks
trading/rotation.py      the day-by-day simulation used to test the model
trading/today.py         the Today page's lists: buy range, hold or sell, avoid, events
trading/picks.py         each day's top-10 list, saved; the weekly list, tracker and track record
trading/breadth.py       market breadth and sector strength for the Market tab
trading/ui.py            the dashboard's look: colours, rows, price bars, cards
trading/journal.py       your real trades (journal/real_trades.csv, not on GitHub)
trading/update.py        refreshes all data; shared by update_data.py and the dashboard
trading/data.py          downloads and loads prices and index membership
trading/indicators.py    EMA, RSI, ATR
trading/fundamentals.py  company results, ratios, results dates, which companies are due
trading/gaps.py          daily prices from NSE's day file (bhavcopy); fills days Yahoo misses
trading/shareholding.py  who owns each company: promoters, FII, DII, mutual funds, public
trading/news.py          company announcements to NSE, sorted into plain categories
trading/flows.py         daily FII/DII buying and selling, bulk and block deals
trading/nse.py           opens a session with the NSE website
trading/company.py       the company card
trading/charges.py       Zerodha delivery charges
trading/charts.py        the dashboard's charts
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

- `start_dashboard.bat`: double-click to open the dashboard. Right-click it and choose
  "Send to > Desktop (create shortcut)" to get a desktop icon.
- `schedule_daily_update.bat`: double-click once. Windows will then download the latest
  data every weekday at 6:30 pm (the laptop must be on). The log is `reports/update_log.txt`.
