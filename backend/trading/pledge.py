"""Promoter pledge: how much of the promoters' shares are pledged to lenders.

When promoters borrow against their shares and the price falls, lenders can
sell those shares, which pushes the price down further. A high pledge is a
classic warning sign. The quarterly shareholding filing only says yes or no;
NSE's pledge page gives the actual percentage, which this module saves.

NSE gives only the latest figure, so the history builds up from the first
download on. The model uses a figure only from the day it was published, so
backtests are not given numbers from the future.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import config

COLUMNS = ["symbol", "published", "quarter", "pledged_of_promoter_pct", "pledged_of_total_pct",
           "promoter_holding_pct"]


def _number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse(raw, symbol):
    """NSE's pledge answer -> one row (or None when NSE has no data)."""
    items = raw.get("data", []) if isinstance(raw, dict) else raw or []
    if not items:
        return None
    item = items[0]
    published = pd.to_datetime(item.get("broadcastDt"), errors="coerce", dayfirst=True)
    return {"symbol": symbol, "published": published,
            "quarter": pd.to_datetime(item.get("shp"), errors="coerce", dayfirst=True),
            "pledged_of_promoter_pct": _number(item.get("percPromoterShares")),
            "pledged_of_total_pct": _number(item.get("percTotShares")),
            "promoter_holding_pct": _number(item.get("percPromoterHolding"))}


def load():
    """Every pledge figure saved, oldest first."""
    if not config.PLEDGE_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(config.PLEDGE_FILE, parse_dates=["published", "quarter"])


def latest(table=None):
    """{symbol: % of promoter shares pledged} from the newest figure of each company."""
    table = load() if table is None else table
    if len(table) == 0:
        return {}
    newest = table.sort_values("published").drop_duplicates("symbol", keep="last")
    return dict(zip(newest["symbol"], newest["pledged_of_promoter_pct"]))


def update(symbols, report=None, workers=3):
    """Download the latest pledge figure of each company. Returns how many were saved."""
    from trading import nse
    browser = nse.session()
    symbols = list(symbols)

    def work(symbol):
        for attempt in range(2):
            try:
                raw = nse.get_json(browser, "/api/corporate-pledgedata", index="equities",
                                   symbol=symbol)
                return parse(raw, symbol)
            except Exception:
                time.sleep(1.0)
        return None

    rows = []
    for first in range(0, len(symbols), 60):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows += [row for row in pool.map(work, symbols[first:first + 60]) if row]
        if report is not None:
            report("Promoter pledges", min(first + 60, len(symbols)), len(symbols))
    if not rows:
        return 0
    saved = load()
    fresh = pd.DataFrame(rows, columns=COLUMNS)
    table = pd.concat([saved, fresh], ignore_index=True) if len(saved) else fresh
    table = table.drop_duplicates(["symbol", "published", "quarter"], keep="last")
    config.PLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    table.sort_values(["symbol", "published"]).to_csv(config.PLEDGE_FILE, index=False)
    return len(rows)
