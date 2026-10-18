"""Shareholding pattern: who owns each company, and how that is changing.

Every listed company files its shareholding pattern with the exchange each
quarter. From that filing we take the share held by:
  - promoters      the founders and controlling group
  - FII            foreign institutions (foreign portfolio investors and others)
  - DII            Indian institutions (mutual funds, insurers, pension funds, banks)
  - mutual funds   a part of DII, shown separately
  - public         everyone else, mostly individual investors
Each row also keeps the date the company filed it, so a backtest can use a
quarter's figures only from the day they became public.
and the names of the mutual fund schemes that hold more than 1% of the
company (the filing names only holders above 1%).
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import config
from trading import nse

SHAREHOLDING_COLUMNS = [
    "symbol", "quarter_end", "filed_on", "promoter", "fii", "dii", "mutual_funds",
    "insurance", "public", "promoters_pledged",
]
HOLDER_COLUMNS = ["symbol", "quarter_end", "fund", "percent"]

# The filing's own names for each group. The exchange changed the file format
# in 2022 and again in late 2025, so older filings spell these differently.
GROUPS = {
    "promoter": ["shareholdingofpromoterandpromotergroup"],
    "fii": ["institutionsforeign"],
    "dii": ["institutionsdomestic"],
    "mutual_funds": ["mutualfundsoruti"],
    "insurance": ["insurancecompanies"],
    "total": ["shareholdingpattern"],
}

# ------------------------------------------------------------- parsing ------
def _facts(xml_text, tag):
    """All (context, value) pairs for one tag in the filing."""
    pattern = r'<[\w-]+:%s\b[^>]*contextRef="([^"]+)"[^>]*>([^<]*)<' % tag
    return re.findall(pattern, xml_text)


def _group_name(context):
    """Turn the filing's context label into a plain lower-case group name.

    New format: 'MutualFundsOrUTI_ContextI'.  Old format: 'MutualFundsOrUtiI'.
    Returns None for the rows about individual named holders.
    """
    if context.endswith("_ContextI"):
        return context[: -len("_ContextI")].lower()
    if "_Context" in context or re.search(r"\d", context):
        return None
    if context.endswith("I"):
        return context[:-1].lower()
    return None


def parse_filing(xml_text):
    """Read one shareholding filing.

    Returns (percentages, funds):
      percentages - {"promoter": 50.5, "fii": 17.2, ...} in percent
      funds - [(name, percent), ...] for mutual funds holding over 1%
    Returns (None, []) if the file does not look like a shareholding filing.
    """
    holdings = {}
    for context, value in _facts(xml_text, "ShareholdingAsAPercentageOfTotalNumberOfShares"):
        name = _group_name(context)
        try:
            number = float(value)
        except ValueError:
            continue
        if name is not None:
            holdings[name] = number

    total = holdings.get("shareholdingpattern")
    if not total:
        return None, []
    # New filings give fractions (0.5048); old ones give percent (50.48).
    scale = 100.0 if total <= 1.5 else 1.0

    result = {}
    for our_name, their_names in GROUPS.items():
        if our_name == "total":
            continue
        values = [holdings[name] for name in their_names if name in holdings]
        result[our_name] = round(values[0] * scale, 2) if values else 0.0

    # Filings up to mid-2022 give one total for all institutions and list
    # foreign investors inside it, with no foreign and Indian subtotals.
    if "institutionsforeign" not in holdings and "institutions" in holdings:
        foreign = (holdings.get("institutionsforeignportfolioinvestor", 0.0)
                   + holdings.get("foreignventurecapitalinvestors", 0.0))
        result["fii"] = round(foreign * scale, 2)
        result["dii"] = round(max(0.0, holdings["institutions"] - foreign) * scale, 2)
    result["public"] = round(
        max(0.0, 100.0 - result["promoter"] - result["fii"] - result["dii"]), 2
    )
    result["promoters_pledged"] = _promoters_pledged(xml_text)

    return result, _funds(xml_text, scale)


def _promoters_pledged(xml_text):
    """True if the filing says promoters have pledged shares, None if it does not say."""
    new_style = re.findall(
        r"<[\w-]+:WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged"
        r"(?:ForPromoterAndPromoterGroup)?\b[^>]*>([^<]*)<", xml_text)
    old_style = re.findall(
        r"<[\w-]+:WhetherAnySharesHeldByPromotersArePledgeOrOtherwiseEncumbered"
        r"(?:ForPromoterAndPromoterGroup)?\b[^>]*>([^<]*)<", xml_text)
    answers = [answer.strip().lower() for answer in new_style + old_style]
    if not answers:
        return None
    return any(answer in ("true", "yes") for answer in answers)


def _funds(xml_text, scale):
    """Mutual funds named in the filing (holders above 1%), largest first."""
    percents = {}
    for context, value in _facts(xml_text, "ShareholdingAsAPercentageOfTotalNumberOfShares"):
        try:
            percents[context] = float(value) * scale
        except ValueError:
            continue

    houses = []
    for context, name in _facts(xml_text, "NameOfTheShareholder"):
        if "mutualfund" not in context.lower():
            continue
        # The name sits in one context and the percentage in its twin:
        # new format 'D_X_Context16' -> 'X_Context16', old 'X001D' -> 'X001I'.
        if context.startswith("D_"):
            twin = context[2:]
        elif context.endswith("D"):
            twin = context[:-1] + "I"
        else:
            continue
        if twin in percents:
            houses.append((name.strip(), round(percents[twin], 2)))
    return sorted(houses, key=lambda house: -house[1])


# ------------------------------------------------------------- download -----
def is_quarter_end(day):
    """True for the last days of March, June, September and December.

    Companies also file after events such as a bonus issue. Those extra
    filings are skipped so that every company has one row per quarter.
    """
    return day.month in (3, 6, 9, 12) and day.day >= 28


def fetch_symbol(session, symbol, already_have=frozenset()):
    """Download the recent shareholding filings of one company.

    already_have: quarter ends (as text) we have stored, which are skipped.
    Returns (shareholding rows, fund rows).
    """
    filings = nse.get_json(session, "/api/corporate-share-holdings-master",
                           index="equities", symbol=symbol)
    if not isinstance(filings, list):
        return [], []

    rows, houses, seen = [], [], set()
    for filing in filings:
        if len(seen) >= config.SHAREHOLDING_QUARTERS:
            break
        quarter = pd.to_datetime(filing.get("date"), format="%d-%b-%Y", errors="coerce")
        filed = pd.to_datetime(filing.get("submissionDate"), format="%d-%b-%Y", errors="coerce")
        link = filing.get("xbrl") or ""
        if pd.isna(quarter) or not is_quarter_end(quarter) or not link.lower().endswith(".xml"):
            continue
        quarter_text = str(quarter.date())
        if quarter_text in seen:
            continue                      # a revised filing for the same quarter
        seen.add(quarter_text)
        if quarter_text in already_have:
            continue

        percentages, funds = parse_filing(session.get(link, timeout=60).text)
        if percentages is None:
            continue
        rows.append({"symbol": symbol, "quarter_end": quarter_text,
                     "filed_on": None if pd.isna(filed) else str(filed.date()),
                     **percentages})
        houses += [{"symbol": symbol, "quarter_end": quarter_text,
                    "fund": name, "percent": percent}
                   for name, percent in funds]
    return rows, houses


def _append(path, columns, new_rows):
    new = pd.DataFrame(new_rows, columns=columns)
    if path.exists():
        new = pd.concat([pd.read_csv(path), new], ignore_index=True)
    new = new.drop_duplicates(subset=columns[:3] if "fund" in columns else columns[:2],
                              keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    new.reindex(columns=columns).sort_values(columns[:2]).to_csv(path, index=False)


def update_shareholding(symbols, workers=3):
    """Download new shareholding filings for many companies.

    Quarters already saved are not downloaded again, so after the first run
    this is quick. Returns (companies with new data, companies that failed).
    """
    stored = load_shareholding()
    have = {}
    if stored is not None:
        complete = stored[stored["filed_on"].notna()]   # rows without a filing date are redone
        have = {symbol: frozenset(rows["quarter_end"].dt.date.astype(str))
                for symbol, rows in complete.groupby("symbol")}
    session = nse.session()

    def work(symbol):
        for attempt in range(2):
            try:
                return fetch_symbol(session, symbol, have.get(symbol, frozenset()))
            except Exception:
                time.sleep(1.5)
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        fetched = list(pool.map(work, list(symbols)))

    rows = [row for part in fetched if part for row in part[0]]
    houses = [row for part in fetched if part for row in part[1]]
    _append(config.SHAREHOLDING_FILE, SHAREHOLDING_COLUMNS, rows)
    _append(config.FUND_HOLDERS_FILE, HOLDER_COLUMNS, houses)
    return len({row["symbol"] for row in rows}), sum(1 for part in fetched if part is None)


# ---------------------------------------------------------------- loading ---
def load_shareholding():
    """Shareholding by company and quarter, or None if not downloaded yet."""
    if not config.SHAREHOLDING_FILE.exists():
        return None
    table = pd.read_csv(config.SHAREHOLDING_FILE, parse_dates=["quarter_end"])
    if "filed_on" not in table.columns:      # a file saved by an older version
        table["filed_on"] = pd.NaT
    table["filed_on"] = pd.to_datetime(table["filed_on"], errors="coerce")
    return table[table["quarter_end"].map(is_quarter_end)].reset_index(drop=True)


def load_fund_holders():
    """Named mutual fund holders, or None if not downloaded yet."""
    if not config.FUND_HOLDERS_FILE.exists():
        return None
    return pd.read_csv(config.FUND_HOLDERS_FILE, parse_dates=["quarter_end"])


def summary(company_rows, holder_rows=None):
    """Latest shareholding of one company and the change from the quarter before.

    Returns a dictionary, or None if there is no shareholding data.
    """
    if company_rows is None or len(company_rows) == 0:
        return None
    rows = company_rows.sort_values("quarter_end")
    latest = rows.iloc[-1]
    previous = rows.iloc[-2] if len(rows) > 1 else None

    result = {"quarter_end": latest["quarter_end"],
              "previous_quarter": None if previous is None else previous["quarter_end"]}
    for group in ["promoter", "fii", "dii", "mutual_funds", "insurance", "public"]:
        result[group] = float(latest[group])
        result[group + "_change"] = (
            None if previous is None else round(float(latest[group] - previous[group]), 2)
        )
    pledged = latest["promoters_pledged"]
    result["promoters_pledged"] = None if pd.isna(pledged) else bool(pledged)

    result["funds"] = []
    if holder_rows is not None and len(holder_rows) > 0:
        current = holder_rows[holder_rows["quarter_end"] == latest["quarter_end"]]
        current = current.sort_values("percent", ascending=False)
        result["funds"] = list(zip(current["fund"], current["percent"]))
    return result
