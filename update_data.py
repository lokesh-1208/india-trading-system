"""Step 1: download prices, index membership, company announcements, FII/DII
figures, large deals, company results and shareholding.

Run:  python update_data.py
      python update_data.py --full-prices      (download the full price history
                                                from Yahoo now, not just new days)
      python update_data.py --fundamentals     (company results for every company,
                                                and shareholding, right now)
Run it once a day after the market closes; it usually takes 1-2 minutes.
The full price history is downloaded once a week by itself (about 6 minutes).
Company results are downloaded only for companies that just reported.
The app's "Update data" button does the same thing.
"""

import argparse

from trading import update

parser = argparse.ArgumentParser(description="Download all data.")
parser.add_argument("--full-prices", action="store_true",
                    help="download the full price history from Yahoo even if it is recent")
parser.add_argument("--fundamentals", action="store_true",
                    help="download every company's results and shareholding now")
arguments = parser.parse_args()

summary = update.run_update(include_company_data=True if arguments.fundamentals else None,
                            full_prices=True if arguments.full_prices else None)

print()
if summary["failed_markets"]:
    print(f"PROBLEM: no data for these markets: {', '.join(summary['failed_markets'])}")
print(update.describe_prices(summary["prices"]))
print(f"Stocks without data on Yahoo: {summary['stocks_without_data']}")
print("These are mostly companies that were delisted, merged or renamed.")
print(f"NSE result filings checked for {summary.get('filings_companies', 0)} companies.")
if summary.get("filings_left"):
    print(f"First download of NSE filings: {summary['filings_left']} companies left "
          "(continued on the next updates).")
print(f"Yahoo company results downloaded for {summary['results_companies']} companies "
      "(those that just reported, or not checked for a month).")
if summary["results_problem"]:
    print(f"Could not finish the company results download: {summary['results_problem']}")
if summary["shareholding_refreshed"]:
    print("Shareholding filings refreshed.")
if summary["shareholding_problem"]:
    print(f"Could not finish the shareholding download: {summary['shareholding_problem']}")
if summary["news_problem"]:
    print(f"Could not download company announcements: {summary['news_problem']}")
else:
    print(f"New company announcements saved: {summary['news_added']}")
if summary["flows_problem"]:
    print(f"Could not download FII/DII figures and large deals: {summary['flows_problem']}")
print(f"Downloads finished in {summary['seconds'] // 60} min {summary['seconds'] % 60} s.")
