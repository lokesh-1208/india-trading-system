"""Step 2: test the rules on past data.

Run:  python run_backtest.py
      python run_backtest.py --start 2020-01-01 --end 2023-12-31
Results are printed and saved in the reports folder.
"""

import argparse

import config
from trading import backtest, data
from trading.screens import Screens

parser = argparse.ArgumentParser(description="Backtest the swing rules.")
parser.add_argument("--start", help="first day, for example 2018-01-01")
parser.add_argument("--end", help="last day, for example 2023-12-31")
parser.add_argument("--no-quality", action="store_true",
                    help="switch the company quality filter off")
parser.add_argument("--no-results-block", action="store_true",
                    help="allow new trades just before results")
arguments = parser.parse_args()

nifty = data.load_market(config.BENCHMARK)
if nifty is None or len(nifty) == 0:
    raise SystemExit("No Nifty data found. Run:  python update_data.py")

print("Loading prices and calculating indicators ...")
screens = Screens(
    use_quality=False if arguments.no_quality else None,
    use_results_block=False if arguments.no_results_block else None,
)
membership = screens.membership
stocks = {
    symbol: screens.add_indicators(symbol, prices, nifty["Close"])
    for symbol, prices in data.load_all_stocks().items()
}
if not stocks:
    raise SystemExit("No stock data found. Run:  python update_data.py")
print(f"{len(stocks)} stocks loaded. Running the backtest ...")

result = backtest.run_backtest(stocks, nifty, start=arguments.start, end=arguments.end)
summary, by_year = backtest.summarise(result)
text = backtest.format_summary(summary, by_year)

if membership is None:
    text += ("\n\nWARNING: no index membership history found, so today's stock list"
             "\nwas used for all past years. These results are too optimistic.")
else:
    coverage = data.coverage_by_year(
        membership, set(stocks), summary["period_start"].year, summary["period_end"].year
    )
    text += (
        "\n\nStock universe: Nifty 500 members as they were on each date."
        f"\nPrice data exists for {coverage['with_prices'].min()} to "
        f"{coverage['with_prices'].max()} of the 500 members, depending on the year."
        "\nThe missing ones are mostly delisted or bankrupt companies, so real"
        "\nresults would be somewhat worse than shown."
    )

first_quality_day = screens.first_quality_date()
if screens.use_quality and first_quality_day is not None:
    text += (
        f"\n\nQuality filter: ON, but for most companies results are only available "
        f"from {first_quality_day.date()}."
        "\nBefore that date nothing could be filtered."
    )
else:
    text += "\n\nQuality filter: OFF."

print()
print(text)

config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
(config.REPORTS_DIR / "backtest_summary.txt").write_text(text + "\n", encoding="utf-8")
result["trades"].to_csv(config.REPORTS_DIR / "backtest_trades.csv", index=False)
result["equity"].to_csv(config.REPORTS_DIR / "backtest_equity.csv")
print()
print("Saved: reports/backtest_summary.txt, backtest_trades.csv, backtest_equity.csv")
