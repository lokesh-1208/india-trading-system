"""Before the market opens: refresh global markets, overnight news and NSE's
pre-open prices. The scheduled task runs this at 9:10 am on weekdays; the
app's "Refresh before open" button does the same thing.

Run:  python backend/premarket_update.py
"""

from trading import update

summary = update.run_premarket()
print()
if summary["failed_markets"]:
    print(f"No data for these markets: {', '.join(summary['failed_markets'])}")
if summary["news_problem"]:
    print(f"Could not download announcements: {summary['news_problem']}")
else:
    print(f"New announcements since the last update: {summary['news_added']}")
if summary["preopen"]:
    print("NSE pre-open prices saved.")
elif summary["preopen_problem"]:
    print(f"NSE pre-open prices: {summary['preopen_problem']}")
else:
    print("NSE pre-open prices: only between 9:00 am and 3:30 pm on a weekday.")
print(f"Finished in {summary['seconds']} s.")
