import os
import yfinance as yf

symbol = "RELIANCE.NS"

prices = yf.download(symbol, period="1y", multi_level_index=False)

print(prices.tail())
print("Rows downloaded:", len(prices))

os.makedirs("data", exist_ok=True)
prices.to_csv(f"data/{symbol}.csv")
print("Saved to data folder")