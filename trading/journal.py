"""Your real-money trades, kept in one CSV file.

Each row is one purchase. When you sell, the same row gets the sell date and
price. The file lives in the journal folder, which is not sent to GitHub, so
keep your own backup of it.
"""

import pandas as pd

import config
from trading import charges

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


def open_positions(table, last_prices=None, last_day=None):
    """Positions not yet sold, with today's value and gain when prices are given.

    last_day: the date of the prices. A position bought after it has no price since
    the buy, so it is valued at what was paid.
    """
    positions = table[table["sell_price"].isna()].copy()
    positions["cost"] = positions["buy_price"] * positions["quantity"]
    if last_prices is not None:
        positions["last_price"] = positions["symbol"].map(last_prices).astype(float)
        if last_day is not None:
            new = pd.to_datetime(positions["buy_date"]) > pd.Timestamp(last_day).normalize()
            positions.loc[new, "last_price"] = positions.loc[new, "buy_price"].astype(float)
        positions["value"] = positions["last_price"] * positions["quantity"]
        positions["gain"] = positions["value"] - positions["cost"]
        positions["gain_%"] = (positions["last_price"] / positions["buy_price"] - 1) * 100
    return positions


def closed_trades(table):
    """Positions that were sold: profit before charges, the charges, and profit after them."""
    closed = table[table["sell_price"].notna()].copy()
    closed["profit"] = (closed["sell_price"] - closed["buy_price"]) * closed["quantity"]
    closed["profit_%"] = (closed["sell_price"] / closed["buy_price"] - 1) * 100
    closed["charges"] = [
        round(charges.buy_charges(b * q) + charges.sell_charges(s * q), 2)
        for b, s, q in zip(closed["buy_price"], closed["sell_price"], closed["quantity"])]
    closed["net_profit"] = closed["profit"] - closed["charges"]
    return closed


def totals(table, last_prices=None, last_day=None):
    """Money in the market, its value now, and profit on closed trades.

    closed_profit is before charges; closed_net after charges; tax_estimate is the
    short-term gains tax on a positive closed_net (losses offset gains).
    """
    positions = open_positions(table, last_prices, last_day)
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
        "closed_charges": float(closed["charges"].sum()),
        "closed_net": float(closed["net_profit"].sum()),
        "tax_estimate": max(0.0, float(closed["net_profit"].sum())) * config.SHORT_TERM_TAX,
    }
