"""Before the market opens: what happened since yesterday's close.

Run in the morning (the app's button, or the 9:10 am scheduled update).
Not part of the tested model. It collects:
  1. Global markets overnight: how the US closed, how Asia is trading, US
     futures, crude, gold, the rupee and India VIX, with a one-line guess of
     how the Indian market may open.
  2. Company news filed after yesterday's close, read as good or bad.
  3. NSE's pre-open session (9:00 to 9:08 am): the price every stock is set
     to open at. After 9:08 this is the best guide to the opening moves.
  4. Industries that usually follow a global move (for example IT with US
     tech, oil marketers against crude). These are rules of thumb.
  5. Warnings for stocks you hold and stocks on this week's list.
"""

import pandas as pd

import config
from trading import data

# Name -> (label, Yahoo ticker). Downloaded with the other markets.
OVERNIGHT = {
    "SP500": "S&P 500 (US)", "NASDAQ": "Nasdaq (US tech)", "SP500_FUTURES": "S&P 500 futures",
    "NASDAQ_FUTURES": "Nasdaq futures", "NIKKEI225": "Nikkei (Japan)",
    "HANGSENG": "Hang Seng (Hong Kong)", "SHANGHAI": "Shanghai (China)",
    "FTSE100": "FTSE (UK)", "BRENT": "Brent crude", "GOLD": "Gold", "USDINR": "Dollar-rupee",
    "INDIAVIX": "India VIX",
}

# Global move -> industries or stocks that usually follow it.
# (market, threshold %, direction for the stocks when the market rises, who,
#  why when the market rises, why when it falls)
SECTOR_LINKS = [
    ("NASDAQ", 1.5, +1, {"industry": "Information Technology"},
     "IT companies trade with US tech", "IT companies trade with US tech"),
    ("NASDAQ_FUTURES", 1.5, +1, {"industry": "Information Technology"},
     "IT companies trade with US tech", "IT companies trade with US tech"),
    ("USDINR", 0.5, +1, {"industry": "Information Technology"},
     "a weaker rupee raises IT export earnings in rupees",
     "a stronger rupee lowers IT export earnings in rupees"),
    ("USDINR", 0.5, +1, {"industry": "Healthcare"},
     "a weaker rupee helps pharma exporters", "a stronger rupee hurts pharma exporters"),
    ("BRENT", 3.0, -1, {"symbols": ["BPCL", "HINDPETRO", "IOC", "INDIGO", "ASIANPAINT",
                                    "BERGEPAINT", "KANSAINER", "PIDILITIND", "MRF",
                                    "APOLLOTYRE", "CEATLTD", "BALKRISIND"]},
     "costlier crude raises costs for oil marketers, airlines, paints and tyres",
     "cheaper crude lowers costs for oil marketers, airlines, paints and tyres"),
    ("BRENT", 3.0, +1, {"symbols": ["ONGC", "OIL", "RELIANCE"]},
     "costlier crude helps oil producers", "cheaper crude hurts oil producers"),
    ("HANGSENG", 2.0, +1, {"industry": "Metals & Mining"},
     "metal prices follow China's demand", "metal prices follow China's demand"),
    ("SHANGHAI", 2.0, +1, {"industry": "Metals & Mining"},
     "metal prices follow China's demand", "metal prices follow China's demand"),
    ("GOLD", 2.0, +1, {"symbols": ["MUTHOOTFIN", "MANAPPURAM", "IIFL"]},
     "dearer gold raises what gold loan companies can lend",
     "cheaper gold lowers what gold loan companies can lend"),
]

# Markets that close after India does, on the same date (their bar for India's
# last trading day still has news India has not traded yet).
CLOSE_AFTER_INDIA = {"SP500", "NASDAQ", "SP500_FUTURES", "NASDAQ_FUTURES", "FTSE100",
                     "BRENT", "GOLD"}


def day_change(table, now=None):
    """(% change of the latest bar against the one before, day of the latest bar)."""
    if table is None or len(table) < 2:
        return None, None
    change = (table["Close"].iloc[-1] / table["Close"].iloc[-2] - 1) * 100
    return float(change), table.index[-1]


def global_moves(markets, since=None):
    """Table of global moves: market, change %, as of which day.

    since: the time of the last Indian close. When given, only markets that
    traded after it are kept: a bar dated after India's last trading day, or
    for markets that close after India (US, UK, crude, gold) a bar on that day.
    Moves India has already traded on are left out.
    """
    rows = []
    for name, label in OVERNIGHT.items():
        change, day = day_change(markets.get(name))
        if change is None:
            continue
        if since is not None:
            last_day = since.normalize()
            if not (day > last_day or (day == last_day and name in CLOSE_AFTER_INDIA)):
                continue
        rows.append({"name": name, "market": label, "change_%": round(change, 2), "day": day})
    return pd.DataFrame(rows, columns=["name", "market", "change_%", "day"])


def opening_guess(moves):
    """A rough guess of how India may open, with the reasons. A rule of thumb.

    Points: US close and US futures (most weight), Asia this morning, crude
    and the rupee (rising is bad for India), VIX rising is bad.
    """
    if len(moves) == 0:
        return "No global trading since the close yet", []
    change = dict(zip(moves["name"], moves["change_%"]))
    weights = {"SP500": 1.0, "NASDAQ": 0.5, "SP500_FUTURES": 1.0, "NIKKEI225": 0.5,
               "HANGSENG": 0.5, "BRENT": -0.3, "USDINR": -1.0}
    points = sum(weight * change[name] for name, weight in weights.items() if name in change)
    reasons = []
    for name, label in OVERNIGHT.items():
        if name in change and abs(change[name]) >= config.PREMARKET_NOTABLE_PCT.get(name, 1.0):
            reasons.append(f"{label} {change[name]:+.1f}%")
    if points >= 1.5:
        guess = "Positive start likely"
    elif points <= -1.5:
        guess = "Weak start likely"
    elif points >= 0.5:
        guess = "Slightly positive start likely"
    elif points <= -0.5:
        guess = "Slightly weak start likely"
    else:
        guess = "Flat start likely"
    return guess, reasons


def sector_effects(moves, industry):
    """Stocks that usually follow today's notable global moves.

    industry: {symbol: industry}. Returns a table: symbol, direction (+1/-1),
    why, and group (the industry or list the link is about).
    """
    change = dict(zip(moves["name"], moves["change_%"]))
    rows = []
    for market, threshold, direction, who, why_up, why_down in SECTOR_LINKS:
        move = change.get(market)
        if move is None or abs(move) < threshold:
            continue
        sign = direction * (1 if move > 0 else -1)
        if "industry" in who:
            symbols = [symbol for symbol, name in industry.items() if name == who["industry"]]
            group = who["industry"]
        else:
            symbols = [symbol for symbol in who["symbols"] if symbol in industry]
            group = ", ".join(symbols)
        label = OVERNIGHT.get(market, market)
        why = f"{label} {move:+.1f}%: {why_up if move > 0 else why_down}"
        for symbol in symbols:
            rows.append({"symbol": symbol, "direction": sign, "why": why, "group": group})
    table = pd.DataFrame(rows, columns=["symbol", "direction", "why", "group"])
    return table.drop_duplicates("symbol")


def sector_summary(effects):
    """One line per global link: which industry may move which way, and why."""
    if len(effects) == 0:
        return []
    lines = []
    for (group, direction, why), _ in effects.groupby(["group", "direction", "why"]):
        lines.append(f"{group}: may open {'up' if direction > 0 else 'down'} ({why})")
    return lines


# ------------------------------------------------------------ pre-open ------
def parse_preopen(raw, symbols=None):
    """NSE's pre-open answer -> symbol, previous close, opening price, change %, quantity."""
    rows = []
    for item in (raw or {}).get("data", []):
        meta = item.get("metadata", {})
        symbol = meta.get("symbol")
        if not symbol or (symbols is not None and symbol not in symbols):
            continue
        detail = item.get("detail", {}).get("preOpenMarket", {})
        try:
            rows.append({"symbol": symbol,
                         "previous_close": float(meta.get("previousClose") or 0),
                         "open_price": float(meta.get("iep") or meta.get("lastPrice") or 0),
                         "change_%": float(meta.get("pChange") or 0),
                         "quantity": float(meta.get("finalQuantity") or 0),
                         "updated": detail.get("lastUpdateTime")})
        except (TypeError, ValueError):
            continue
    table = pd.DataFrame(rows, columns=["symbol", "previous_close", "open_price", "change_%",
                                        "quantity", "updated"])
    table["updated"] = pd.to_datetime(table["updated"], errors="coerce", dayfirst=True)
    return table


def download_preopen(browser=None):
    """Today's pre-open prices for all NSE stocks, saved to data/premarket. None on failure."""
    from trading import nse
    try:
        browser = nse.session() if browser is None else browser
        raw = nse.get_json(browser, "/api/market-data-pre-open", key="ALL")
    except Exception:
        return None
    table = parse_preopen(raw)
    if len(table) == 0:
        return None
    config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(config.PREOPEN_FILE, index=False)
    return table


def load_preopen(today=None):
    """The saved pre-open table if it is from today's session, else None."""
    if not config.PREOPEN_FILE.exists():
        return None
    table = pd.read_csv(config.PREOPEN_FILE, parse_dates=["updated"])
    today = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize() \
        if today is None else pd.Timestamp(today).normalize()
    stamp = table["updated"].dropna()
    if len(stamp) == 0 or stamp.max().normalize() != today:
        return None
    return table


def preopen_movers(preopen, symbols, side, top=None):
    """Nifty 500 stocks set to open sharply up or down (at least config.PREOPEN_MIN_PCT)."""
    top = config.MOVERS_PER_SIDE if top is None else top
    if preopen is None or len(preopen) == 0:
        return pd.DataFrame(columns=["symbol", "change_%", "open_price", "previous_close"])
    table = preopen[preopen["symbol"].isin(set(symbols)) & (preopen["quantity"] > 0)]
    if side == "up":
        table = table[table["change_%"] >= config.PREOPEN_MIN_PCT].sort_values(
            "change_%", ascending=False)
    else:
        table = table[table["change_%"] <= -config.PREOPEN_MIN_PCT].sort_values("change_%")
    return table.head(top)[["symbol", "change_%", "open_price", "previous_close"]]


# ------------------------------------------------------------ together ------
def last_close_time(calendar, now):
    """The time of the last market close before `now` (3:30 pm of the last trading day).

    calendar: the trading days (for example Nifty's dates).
    """
    after_close = now.hour * 60 + now.minute >= 15 * 60 + 30
    days = calendar[calendar <= now.normalize()] if after_close \
        else calendar[calendar < now.normalize()]
    day = days[-1] if len(days) else now.normalize() - pd.Timedelta(days=1)
    return day + pd.Timedelta(hours=15, minutes=30)


def stock_list(read_overnight, sectors, preopen_up, preopen_down):
    """One table of stocks likely to move at the open, up and down, with all reasons.

    Each row: symbol, direction (+1 or -1), strength (higher = more reasons),
    reasons (list of texts), open_% (pre-open change, if known), link.
    """
    found = {}

    def add(symbol, direction, reason, weight, link="", open_change=None):
        entry = found.setdefault(symbol, {"symbol": symbol, "points": 0.0, "reasons": [],
                                          "link": "", "open_%": None})
        entry["points"] += direction * weight
        if reason not in entry["reasons"]:
            entry["reasons"].append(reason)
        if link and not entry["link"]:
            entry["link"] = link
        if open_change is not None:
            entry["open_%"] = open_change

    for row in read_overnight.itertuples():
        if row.lean != 0:
            add(row.symbol, 1 if row.lean > 0 else -1, f"{row.label}: {row.what}"[:200],
                abs(row.lean), row.link)
    for table, direction in ((preopen_up, 1), (preopen_down, -1)):
        for symbol, change in zip(table["symbol"], table["change_%"]):
            add(symbol, direction, f"Pre-open: set to open {change:+.1f}%", 3,
                open_change=round(float(change), 1))
    # A global link only adds a reason to a stock that already has its own
    # (news or pre-open); on its own it is shown once per industry instead.
    for row in sectors.itertuples():
        if row.symbol in found:
            add(row.symbol, row.direction, row.why, 0.5)

    rows = []
    for entry in found.values():
        if entry["points"] == 0:
            continue
        rows.append({"symbol": entry["symbol"], "direction": 1 if entry["points"] > 0 else -1,
                     "strength": abs(entry["points"]), "reasons": entry["reasons"],
                     "open_%": entry["open_%"], "link": entry["link"]})
    table = pd.DataFrame(rows, columns=["symbol", "direction", "strength", "reasons", "open_%",
                                        "link"])
    return table.sort_values("strength", ascending=False).reset_index(drop=True)


def load_markets():
    """{name: price table} for every market in OVERNIGHT that is saved."""
    markets = {}
    for name in OVERNIGHT:
        table = data.load_market(name)
        if table is not None and len(table):
            markets[name] = table
    return markets
