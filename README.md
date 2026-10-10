# india-trading-system

A rule-based swing trading system for Indian stocks (Nifty 500), written in Python.
It downloads free end-of-day data, applies a fixed set of rules, tests those rules
on past years, and prints a daily shortlist with entry, stop-loss, target and quantity.
Orders are placed manually.

This is a personal learning project, not investment advice. A backtest shows how
rules behaved in the past and does not promise future results.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## How to run

| Step | Command | What it does |
|---|---|---|
| 1 | `python update_data.py` | Downloads the index membership history, prices for about 800 stocks, Nifty, India VIX, global markets and (weekly) company results and shareholding into `data/`. Takes a few minutes. |
| 2 | `python run_backtest.py` | Tests the rules from 2015 to today and compares the result with Nifty buy-and-hold. |
| 3 | `python daily_report.py` | Prints the market dashboard and the shortlist from the last close. |
| Card | `python stock_card.py TCS` | Shows everything known about one company: price range, valuation, growth, profitability, debt, dividend, shareholding pattern and a ten-point scorecard. |
| Tests | `python -m pytest` | Runs the automated checks on the calculations. |

The backtest also accepts a period, and each check can be switched off to see its effect:

```
python run_backtest.py --start 2020-01-01 --end 2023-12-31
python run_backtest.py --no-quality --no-results-block
```

## The rules

A stock gives a signal at the close when all of these are true:

- It was a Nifty 500 member on that day.
- Average daily traded value is above Rs 50 crore.
- Close is above the 20-day and the 50-day EMA.
- RSI(14) is between 50 and 70.
- Volume is above its 20-day average.
- The stock beat Nifty over the last 3 months.
- The business passes the quality filter: profitable last year, sales not shrinking,
  return on equity at least 10%, debt no more than 2 x equity (the debt rule is
  skipped for banks and finance companies).
- Results are not due within the next 5 days.

The trade:

- New trades only when Nifty is above its 50-day EMA.
- Buy the next day only if price goes above the signal day's high.
- Stop-loss 1.5 x ATR below the entry. Target at 2 x the risk.
- Exit at the next open if the close falls below the 20-day EMA.

Risk limits (fixed, not tuned):

- Risk 1% of capital per trade. Quantity is calculated from the stop-loss.
- At most 4 positions, each at most 25% of capital. No leverage.
- No new trades after a 20% fall in the account.

Every setting is in `config.py`.

## Project layout

```
config.py            all settings: risk limits, rule values, charges
universe/            fallback stock list (used only if the membership download fails)
research/            scripts used to compare rule sets; not part of the daily tool
trading/data.py      download and load prices
trading/indicators.py  EMA, RSI, ATR
trading/strategy.py  the signal rules and position sizing
trading/fundamentals.py  company results, ratios, quality filter, results dates
trading/screens.py   applies membership, quality and results checks the same way everywhere
trading/company.py   the company card: valuation, growth, dividend yield, industry PE, scorecard
trading/shareholding.py  who owns each company: promoters, FII, DII, mutual funds, public
trading/charges.py   Zerodha delivery charges
trading/backtest.py  day-by-day simulation and results
trading/report.py    daily dashboard and shortlist
tests/               automated checks
```

`data/`, `reports/` and `journal/` are created when you run the scripts and are not
committed to Git.

## Trade journal

`daily_report.py` creates `journal/trades.csv`. Add a row when you enter a trade and
fill in `exit_date` and `exit_price` when you close it. The report uses the journal to
work out your equity, your free slots and whether the drawdown limit has been reached.

## Stock universe

Past dates use the Nifty 500 members as they were on that date, not today's list.
A stock that was later dropped from the index is still included for the years it
was a member. Testing only today's members would make every result look better
than it was, because today's list contains only the companies that survived and grew.

The membership history comes from the public project
[nifty500-momentum-backtest](https://github.com/rishabhjain0295-web/nifty500-momentum-backtest),
which built it from NSE's inclusion/exclusion records. `update_data.py` downloads it
into `data/universe/`. It is not stored in this repository.

## Known limits of the backtest

- **Some survivorship bias remains.** Price data exists for about 410 of the 500
  members in 2015, rising to about 487 in 2026. The missing ones are mostly companies
  that were delisted, merged or went bankrupt, which Yahoo Finance no longer carries.
  Real results would be somewhat worse than shown.
- **Membership dates after 2020 are approximate.** They come from snapshots taken a
  few months apart, so a change can be dated a few months late.
- **Benchmark.** Stock prices include dividends, the Nifty 50 index does not. This
  favours the strategy by roughly 1% a year.
- **Daily data only.** When several stocks break out on the same day, the test takes
  the strongest first. In real trading you take whichever breaks out first.
- **Company results cover only recent years.** Yahoo Finance gives about four years
  of yearly results, so the quality filter can act only from mid-2023. Before that the
  backtest runs on price rules alone.
- **Valuation is approximate.** PE uses the share count at the last year end, so it is
  off after a recent bonus issue or split.
- **Free data.** Yahoo Finance prices occasionally have gaps or errors. Demergers
  show up as a one-day price fall.

## Results so far

No rule set tested so far has qualified for real money. The rules in this version
lost money from 2015 to 2026 after charges. See the backtest log kept with the project.

## Data sources

- Prices, company results, dividends, results dates: Yahoo Finance.
- Shareholding pattern: the quarterly filings companies make to NSE. The filing names
  only holders above 1%, so the list of mutual fund schemes is not complete.
- Index membership history: see "Stock universe" above.

## Not built yet

Exchange announcements and news, daily FII/DII flows, the full list of mutual fund
schemes holding each stock, the intraday module, the long-term module.
