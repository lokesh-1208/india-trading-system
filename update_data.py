"""Step 1: download prices, index membership and company fundamentals.

Run:  python update_data.py
      python update_data.py --fundamentals     (force a refresh of company results)
Takes a few minutes. Run it once a day after the market closes.
Company results change slowly, so they are refreshed once a week.
"""

import argparse
import time

import config
from trading import data, fundamentals

parser = argparse.ArgumentParser(description="Download all data.")
parser.add_argument("--fundamentals", action="store_true",
                    help="refresh company results even if they are recent")
arguments = parser.parse_args()

failed_market, failed_stocks = data.update_all()

print()
if failed_market:
    print(f"PROBLEM: no data for these markets: {', '.join(failed_market)}")
print(f"Stocks without data on Yahoo: {len(failed_stocks)}")
print("These are mostly companies that were delisted, merged or renamed.")

file_age_days = (
    (time.time() - config.ANNUAL_FILE.stat().st_mtime) / 86400
    if config.ANNUAL_FILE.exists() else None
)
if arguments.fundamentals or file_age_days is None \
        or file_age_days > config.FUNDAMENTALS_REFRESH_DAYS:
    symbols = [symbol for symbol in data.all_symbols() if symbol not in failed_stocks]
    print(f"\nDownloading company results for {len(symbols)} stocks ...")
    count = fundamentals.update_fundamentals(symbols)
    print(f"Company results saved for {count} stocks.")
else:
    print(f"\nCompany results are {file_age_days:.0f} days old; not refreshed.")

print("Downloads finished.")
