"""Your real-money trades, kept in one CSV file.

Each row is one purchase. When you sell, the same row gets the sell date and
price. The file lives in the journal folder, which is not sent to GitHub, so
keep your own backup of it.
"""

import pandas as pd

import config

COLUMNS = ["symbol", "buy_date", "buy_price", "quantity", "sell_date", "sell_price", "note"]


def load():
    """All recorded trades. An empty table if nothing has been recorded."""
    if not config.REAL_TRADES_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    table = pd.read_csv(config.REAL_TRADES_FILE, dtype={"note": str})
    for column in ["buy_price", "quantity", "sell_price"]:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    table["note"] = table["note"].fillna("")
    return table.reindex(columns=COLUMNS)


def save(table):
    config.REAL_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    table.reindex(columns=COLUMNS).to_csv(config.REAL_TRADES_FILE, index=False)


def record_buy(table, symbol, buy_date, buy_price, quantity, note=""):
    """Return the table with one more open position."""
    if buy_price <= 0 or quantity <= 0:
        raise ValueError("Price and quantity must be above zero.")
    row = {"symbol": symbol.strip().upper(), "buy_date": str(buy_date),
           "buy_price": float(buy_price), "quantity": int(quantity),
           "sell_date": None, "sell_price": None, "note": note.strip()}
    return pd.concat([table, pd.DataFrame([row])], ignore_index=True).reindex(columns=COLUMNS)


def record_sell(table, row_number, sell_date, sell_price):
    """Return the table with one open position closed."""
    if sell_price <= 0:
        raise ValueError("Price must be above zero.")
    if pd.notna(table.loc[row_number, "sell_price"]):
        raise ValueError("That position is already closed.")
    result = table.copy()
    result.loc[row_number, "sell_date"] = str(sell_date)
    result.loc[row_number, "sell_price"] = float(sell_price)
    return result


def open_positions(table, last_prices=None):
    """Positions not yet sold, with today's value and gain when prices are given."""
    positions = table[table["sell_price"].isna()].copy()
    positions["cost"] = positions["buy_price"] * positions["quantity"]
    if last_prices is not None:
        positions["last_price"] = positions["symbol"].map(last_prices)
        positions["value"] = positions["last_price"] * positions["quantity"]
        positions["gain"] = positions["value"] - positions["cost"]
        positions["gain_%"] = (positions["last_price"] / positions["buy_price"] - 1) * 100
    return positions


def closed_trades(table):
    """Positions that were sold, with the profit on each (before charges)."""
    closed = table[table["sell_price"].notna()].copy()
    closed["profit"] = (closed["sell_price"] - closed["buy_price"]) * closed["quantity"]
    closed["profit_%"] = (closed["sell_price"] / closed["buy_price"] - 1) * 100
    return closed


def totals(table, last_prices=None):
    """Money in the market, its value now, and profit so far (before charges)."""
    positions = open_positions(table, last_prices)
    closed = closed_trades(table)
    invested = float(positions["cost"].sum())
    value = float(positions["value"].sum()) if "value" in positions else invested
    return {
        "open_count": len(positions),
        "invested": invested,
        "value": value,
        "open_gain": value - invested,
        "closed_count": len(closed),
        "closed_profit": float(closed["profit"].sum()),
    }
