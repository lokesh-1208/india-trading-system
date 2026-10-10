"""Step 3: today's market dashboard and shortlist.

Run:  python daily_report.py
Run update_data.py first so the prices are fresh.
"""

import config
from trading import data, report

text, shortlist = report.build_report()
print(text)

last_day = data.load_market(config.BENCHMARK).index[-1].date()
text_path, csv_path = report.save_report(text, shortlist, last_day)
print()
print(f"Saved: {text_path.relative_to(config.ROOT)} and {csv_path.relative_to(config.ROOT)}")
