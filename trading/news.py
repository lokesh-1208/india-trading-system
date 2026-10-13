"""Company news: the announcements companies make to the exchange.

Every listed company must tell NSE about anything that matters: results,
new orders, acquisitions, fund raising, dividends, management changes,
credit rating changes, legal matters. This is the official source that news
sites report from, and it is free.

Each announcement is put into a plain category. Paperwork that says nothing
about the business (share certificates, trading window notices, newspaper
copies and so on) is marked as routine so it can be hidden.
"""

import datetime as dt

import pandas as pd

import config
from trading import nse

COLUMNS = ["time", "symbol", "category", "important", "subject", "detail", "link"]
ROUTINE = "Routine"
OTHER = "Other"

# Checked from top to bottom; the first match wins. Words are matched against
# NSE's own subject line in lower case.
CATEGORIES = [
    (ROUTINE, [
        "certificate under sebi", "trading window", "newspaper", "copy of newspaper",
        "loss of share", "duplicate share", "share certificate", "investor meet",
        "analyst", "con. call", "conference call", "earnings call", "transcript",
        "shareholders meeting", "postal ballot", "scrutinizer", "voting result",
        "book closure", "record date", "esop", "esos", "employee stock",
        "allotment of securities", "change in registrar", "address", "website",
        "investor presentation", "notice of", "annual general meeting", "agm", "egm",
        "compliance", "regulation 74", "disclosure under sebi takeover",
        "trading plan", "statement of deviation", "monitoring agency",
        "options to purchase", "structural digital database",
    ]),
    ("Results", ["financial result", "outcome of board meeting", "board meeting",
                 "results", "integrated filing"]),
    ("Orders and contracts", ["order", "contract", "bagging"]),
    ("Deals", ["acquisition", "amalgamation", "merger", "demerger", "arrangement",
               "sale or disposal", "disinvestment", "joint venture", "agreement",
               "slump sale", "open offer", "takeover"]),
    ("Raising money", ["raising of funds", "fund raising", "preferential", "qip",
                       "qualified institution", "rights issue", "debenture", "ncd",
                       "commercial paper", "issue of securities", "buyback", "buy back"]),
    ("Dividend and bonus", ["dividend", "bonus", "split", "sub-division", "corporate action"]),
    ("Management change", ["resignation", "appointment", "change in director",
                           "change in management", "cessation", "key managerial",
                           "auditor", "company secretary"]),
    ("Credit rating", ["credit rating", "rating"]),
    ("Legal and regulatory", ["litigation", "dispute", "penalty", "fine", "show cause",
                              "regulatory", "search", "seizure", "fraud", "default",
                              "insolvency", "tax demand", "gst", "court", "nclt",
                              "strike", "lockout", "fire", "accident", "disruption",
                              "action(s) taken", "action(s) initiated", "clarification",
                              "rumour", "news verification", "spurt in volume",
                              "closure of operations", "termination"]),
    ("Business update", ["press release", "update", "general update", "new product",
                         "launch", "capacity", "expansion", "commencement", "plant",
                         "business", "intimation"]),
]


def classify(subject):
    """Put one NSE subject line into a plain category."""
    text = str(subject).lower()
    for category, words in CATEGORIES:
        if any(word in text for word in words):
            return category
    return OTHER


def to_rows(raw, symbols=None):
    """Turn NSE's answer into our table. Keeps only `symbols` when given."""
    rows = []
    for item in raw if isinstance(raw, list) else []:
        symbol = str(item.get("symbol") or "").strip()
        if not symbol or (symbols is not None and symbol not in symbols):
            continue
        when = pd.to_datetime(item.get("an_dt"), errors="coerce", dayfirst=True)
        if pd.isna(when):
            continue
        subject = str(item.get("desc") or "").strip()
        category = classify(subject)
        detail = " ".join(str(item.get("attchmntText") or "").split())
        rows.append({
            "time": when,
            "symbol": symbol,
            "category": category,
            "important": category not in (ROUTINE, OTHER),
            "subject": subject,
            "detail": detail[:500],
            "link": str(item.get("attchmntFile") or "").strip(),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def merge(old, new, today=None):
    """Join two tables: no repeats, newest first, old announcements dropped."""
    frames = [frame for frame in (old, new) if frame is not None and len(frame) > 0]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    table = pd.concat(frames, ignore_index=True)
    table["time"] = pd.to_datetime(table["time"])
    table = table.drop_duplicates(subset=["time", "symbol", "subject", "link"], keep="last")
    today = pd.Timestamp.today() if today is None else pd.Timestamp(today)
    table = table[table["time"] >= today - pd.Timedelta(days=config.ANNOUNCEMENT_DAYS_KEPT)]
    return table.sort_values("time", ascending=False).reset_index(drop=True)


def load():
    """All saved announcements, newest first. Empty table if none are saved."""
    if not config.ANNOUNCEMENTS_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    table = pd.read_csv(config.ANNOUNCEMENTS_FILE, parse_dates=["time"])
    for column in ("subject", "detail", "link"):
        table[column] = table[column].fillna("")
    table["important"] = table["important"].astype(bool)
    return table


def for_symbol(table, symbol, days=30, important_only=True, today=None):
    """One company's recent announcements, newest first."""
    today = pd.Timestamp.today() if today is None else pd.Timestamp(today)
    rows = table[(table["symbol"] == symbol)
                 & (table["time"] >= today - pd.Timedelta(days=days))]
    if important_only:
        rows = rows[rows["important"]]
    return rows.sort_values("time", ascending=False)


def update(symbols, today=None):
    """Download the announcements made since the last one we have.

    Asks NSE week by week. Returns the number of new announcements saved.
    """
    today = dt.date.today() if today is None else today
    saved = load()
    if len(saved) > 0:
        first_day = saved["time"].max().date()
    else:
        first_day = today - dt.timedelta(days=config.ANNOUNCEMENT_DAYS_FIRST_RUN)
    first_day = max(first_day, today - dt.timedelta(days=config.ANNOUNCEMENT_DAYS_KEPT))

    browser = nse.session()
    wanted = set(symbols)
    pieces = []
    day = first_day
    while day <= today:
        last = min(day + dt.timedelta(days=6), today)
        raw = nse.get_json(browser, "/api/corporate-announcements", index="equities",
                           from_date=day.strftime("%d-%m-%Y"), to_date=last.strftime("%d-%m-%Y"))
        pieces.append(to_rows(raw, wanted))
        day = last + dt.timedelta(days=1)

    fresh = merge(None, pd.concat(pieces, ignore_index=True) if pieces else None, today)
    combined = merge(saved, fresh, today)
    config.ANNOUNCEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(config.ANNOUNCEMENTS_FILE, index=False)
    return len(combined) - len(saved)


def backfill(symbols, days=None, report=None, today=None):
    """Fill in older announcements once, back to `days` days ago (week by week).

    The normal update only adds new announcements. This goes the other way, from
    the oldest saved announcement backwards, so the news reading has enough past
    cases to measure what usually happened after each kind of news.
    Returns the number of announcements added.
    """
    days = config.ANNOUNCEMENT_HISTORY_DAYS if days is None else days
    today = dt.date.today() if today is None else today
    saved = load()
    oldest = saved["time"].min().date() if len(saved) else today
    first_day = today - dt.timedelta(days=days)
    if oldest <= first_day + dt.timedelta(days=7):
        return 0
    browser = nse.session()
    wanted = set(symbols)
    pieces = []
    weeks = max(1, (oldest - first_day).days // 7 + 1)
    last = oldest
    done = 0
    while last > first_day:
        day = max(first_day, last - dt.timedelta(days=6))
        try:
            raw = nse.get_json(browser, "/api/corporate-announcements", index="equities",
                               from_date=day.strftime("%d-%m-%Y"),
                               to_date=last.strftime("%d-%m-%Y"))
            pieces.append(to_rows(raw, wanted))
        except Exception:
            pass                                   # a missed week is filled next time
        last = day - dt.timedelta(days=1)
        done += 1
        if report is not None:
            report("Older announcements", min(done, weeks), weeks)
    if not pieces:
        return 0
    combined = merge(saved, pd.concat(pieces, ignore_index=True), today)
    config.ANNOUNCEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(config.ANNOUNCEMENTS_FILE, index=False)
    return len(combined) - len(saved)
