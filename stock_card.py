"""Everything the system knows about one company, on one card.

Run:  python stock_card.py RELIANCE
      python stock_card.py TCS INFY WIPRO
"""

import argparse

from trading import company, data, news
from trading.screens import Screens

parser = argparse.ArgumentParser(description="Show the company card for one or more stocks.")
parser.add_argument("symbols", nargs="+", help="NSE symbols, for example RELIANCE TCS")
arguments = parser.parse_args()

stocks = data.load_all_stocks()
if not stocks:
    raise SystemExit("No stock data found. Run:  python update_data.py")

screens = Screens()
if screens.annual is None:
    print("Company results not downloaded yet. Run:  python update_data.py --fundamentals\n")
screens.learn_industry_pe(stocks)
announcements = news.load()

for symbol in [name.upper() for name in arguments.symbols]:
    if symbol not in stocks:
        print(f"{symbol}: no price data. Check the symbol, or run update_data.py.\n")
        continue
    prices = stocks[symbol]
    card = screens.card(symbol, prices)
    text = company.format_card(
        card, screens.is_financial(symbol), screens.next_results(symbol, prices.index[-1])
    )
    print(text)
    recent = news.for_symbol(announcements, symbol, days=30)
    print()
    print("NEWS IN THE LAST 30 DAYS  (company announcements to NSE)")
    if len(recent) == 0:
        print("  Nothing important." if len(announcements) else "  Not downloaded yet.")
    for row in recent.head(8).itertuples():
        print(f"  {row.time:%d %b}  {row.category}: {row.detail[:110] or row.subject}")
    print()
