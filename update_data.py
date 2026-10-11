"""Step 1: download prices, index membership, company announcements, FII/DII
figures, large deals, company results and shareholding.

Run:  python update_data.py
      python update_data.py --fundamentals     (force a refresh of company results
                                                and shareholding)
Prices take a few minutes. Run it once a day after the market closes.
Company results and shareholding change slowly, so they refresh once a week.
The dashboard's "Update data now" button does the same thing.
"""

import argparse

from trading import update

parser = argparse.ArgumentParser(description="Download all data.")
parser.add_argument("--fundamentals", action="store_true",
                    help="refresh company results and shareholding even if they are recent")
arguments = parser.parse_args()

summary = update.run_update(include_company_data=True if arguments.fundamentals else None)

print()
if summary["failed_markets"]:
    print(f"PROBLEM: no data for these markets: {', '.join(summary['failed_markets'])}")
print(f"Stocks without data on Yahoo: {summary['stocks_without_data']}")
print("These are mostly companies that were delisted, merged or renamed.")
if summary["company_data_refreshed"]:
    print("Company results and shareholding refreshed.")
else:
    print(f"Company results are {update.company_data_age_days():.0f} days old; not refreshed.")
if summary["shareholding_problem"]:
    print(f"Could not finish the shareholding download: {summary['shareholding_problem']}")
if summary["news_problem"]:
    print(f"Could not download company announcements: {summary['news_problem']}")
else:
    print(f"New company announcements saved: {summary['news_added']}")
if summary["flows_problem"]:
    print(f"Could not download FII/DII figures and large deals: {summary['flows_problem']}")
print("Downloads finished.")
