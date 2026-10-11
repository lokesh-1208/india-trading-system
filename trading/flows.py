"""Money flows: who bought and sold on the exchange each day.

Two things, both published by NSE after the market closes:
  - FII and DII   how much foreign institutions and Indian institutions bought
                  and sold in the cash market, in Rs crore.
  - Large deals   bulk deals (one client trading more than 0.5% of a company's
                  shares in a day) and block deals (large trades agreed
                  between two parties), with the client's name.

NSE only gives the latest day, so a history builds up one day at a time, each
time the data is updated. A day on which no update was run is missed.
"""

import pandas as pd

import config
from trading import nse

FLOW_COLUMNS = ["date", "who", "bought", "sold", "net"]
DEAL_COLUMNS = ["date", "symbol", "company", "kind", "client", "side", "quantity", "price"]


def _number(value):
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return float("nan")


# -------------------------------------------------------------- FII / DII ---
def flow_rows(raw):
    """Turn NSE's FII/DII answer into rows. Values are in Rs crore."""
    rows = []
    for item in raw if isinstance(raw, list) else []:
        day = pd.to_datetime(item.get("date"), errors="coerce", dayfirst=True)
        category = str(item.get("category") or "").upper()
        if pd.isna(day) or not category:
            continue
        rows.append({
            "date": day.normalize(),
            "who": "FII" if "FII" in category else "DII",
            "bought": _number(item.get("buyValue")),
            "sold": _number(item.get("sellValue")),
            "net": _number(item.get("netValue")),
        })
    return pd.DataFrame(rows, columns=FLOW_COLUMNS)


# ------------------------------------------------------------ large deals ---
def deal_rows(raw):
    """Turn NSE's large-deal answer into rows."""
    rows = []
    groups = raw if isinstance(raw, dict) else {}
    for key, kind in (("BULK_DEALS_DATA", "Bulk"), ("BLOCK_DEALS_DATA", "Block")):
        for item in groups.get(key) or []:
            day = pd.to_datetime(item.get("date"), errors="coerce", dayfirst=True)
            symbol = str(item.get("symbol") or "").strip()
            if pd.isna(day) or not symbol:
                continue
            rows.append({
                "date": day.normalize(),
                "symbol": symbol,
                "company": str(item.get("name") or "").strip(),
                "kind": kind,
                "client": " ".join(str(item.get("clientName") or "").split()),
                "side": "Buy" if str(item.get("buySell") or "").upper().startswith("B") else "Sell",
                "quantity": _number(item.get("qty")),
                "price": _number(item.get("watp")),
            })
    return pd.DataFrame(rows, columns=DEAL_COLUMNS)


# ----------------------------------------------------------------- saving ---
def merge(old, new, keys):
    """Join two tables without repeats, oldest day first."""
    frames = [frame for frame in (old, new) if frame is not None and len(frame) > 0]
    if not frames:
        return (old if old is not None else new).iloc[0:0]
    table = pd.concat(frames, ignore_index=True)
    table["date"] = pd.to_datetime(table["date"])
    table = table.drop_duplicates(subset=keys, keep="last")
    return table.sort_values("date", kind="stable").reset_index(drop=True)


def _load(path, columns):
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return pd.read_csv(path, parse_dates=["date"])


def load_flows():
    """Saved daily FII and DII figures."""
    return _load(config.FII_DII_FILE, FLOW_COLUMNS)


def load_deals():
    """Saved bulk and block deals."""
    return _load(config.LARGE_DEALS_FILE, DEAL_COLUMNS)


def update():
    """Add the latest day's figures to the saved files.

    Returns (days of FII/DII history saved, new large deals added).
    """
    browser = nse.session()
    config.FII_DII_FILE.parent.mkdir(parents=True, exist_ok=True)

    flows = merge(load_flows(), flow_rows(nse.get_json(browser, "/api/fiidiiTradeReact")),
                  ["date", "who"])
    flows.to_csv(config.FII_DII_FILE, index=False)

    old_deals = load_deals()
    deals = merge(old_deals,
                  deal_rows(nse.get_json(browser, "/api/snapshot-capital-market-largedeal")),
                  ["date", "symbol", "kind", "client", "side", "quantity", "price"])
    deals.to_csv(config.LARGE_DEALS_FILE, index=False)
    return flows["date"].nunique(), len(deals) - len(old_deals)


# ---------------------------------------------------------------- reading ---
def daily_net(flows):
    """One row per day with columns FII and DII: net buying in Rs crore."""
    if len(flows) == 0:
        return pd.DataFrame(columns=["FII", "DII"])
    table = flows.pivot_table(index="date", columns="who", values="net", aggfunc="last")
    return table.reindex(columns=["FII", "DII"]).sort_index()


def deals_for(deals, symbols, days=30, today=None):
    """Recent large deals in the given stocks, newest first, with value in Rs crore."""
    today = pd.Timestamp.today() if today is None else pd.Timestamp(today)
    rows = deals[deals["symbol"].isin(set(symbols))
                 & (deals["date"] >= today.normalize() - pd.Timedelta(days=days))].copy()
    rows["value_crore"] = rows["quantity"] * rows["price"] / 1e7
    return rows.sort_values(["date", "value_crore"], ascending=False)
