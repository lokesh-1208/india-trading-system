"""Company results from NSE's own filings: 10 years, cash flow, debt, ROCE.

Every listed company files its results with NSE in XBRL, a machine-readable
format. One filing holds the quarter, the year so far, and (every six months)
the balance sheet and the cash flow statement. This module:

  1. asks NSE for the list of a company's result filings (two lists: up to
     Dec 2024, and the "integrated filing" from 2025 on),
  2. downloads the filings it does not have yet and reads the numbers,
  3. builds a yearly and a quarterly table in the same shape as the Yahoo
     tables, plus cash flow, profit before tax, finance costs and borrowings,
     and the exact date and time each filing became public.

NSE has the filing the same evening a company declares its results, days
before Yahoo. Yahoo is kept only for companies or years NSE cannot give.

Which filings are downloaded: every quarter from config.FILINGS_ALL_QUARTERS_FROM,
and before that only the March (full year) and September (half year, with
cash flow) filings back to config.FILINGS_START. The consolidated filing is
used when the company files one, otherwise the standalone one.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import config

OLD_LIST = "/api/corporates-financial-results"
NEW_LIST = "/api/integrated-filing-results"

RESULT_COLUMNS = ["symbol", "period_start", "period_end", "months", "consolidated", "bank",
                  "filed", "revenue", "net_income", "pbt", "finance_costs", "depreciation",
                  "cfo", "capex", "equity", "borrowings", "shares", "xbrl"]
TRIED_COLUMNS = ["symbol", "xbrl", "tried"]

# Several names a figure can have, first found wins (company, bank and older layouts).
FIGURES = {
    "revenue": ["RevenueFromOperations", "TotalRevenueFromOperations"],
    "net_income": ["ProfitOrLossAttributableToOwnersOfParent", "ProfitLossForPeriod",
                   "ProfitLossForThePeriod",
                   "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
                   "NetProfitLossForThePeriod"],
    "pbt": ["ProfitBeforeTax", "ProfitLossBeforeTax", "ProfitLossFromOrdinaryActivitiesBeforeTax"],
    "finance_costs": ["FinanceCosts"],
    "depreciation": ["DepreciationDepletionAndAmortisationExpense",
                     "DepreciationAndAmortisationExpense"],
    "cfo": ["CashFlowsFromUsedInOperatingActivities", "NetCashFlowsFromUsedInOperatingActivities"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
              "PurchaseOfPropertyPlantAndEquipment"],
}
BALANCE = {
    "equity": ["EquityAttributableToOwnersOfParent", "Equity", "TotalEquity"],
    "share_capital": ["EquityShareCapital", "PaidUpValueOfEquityShareCapital"],
    "borrowings_now": ["BorrowingsCurrent", "CurrentBorrowings"],
    "borrowings_later": ["BorrowingsNoncurrent", "NoncurrentBorrowings"],
}
BANK_REVENUE = ["InterestEarned", "OtherIncome"]


# ------------------------------------------------------------ the list ------
def _date(text, dayfirst=True):
    return pd.to_datetime(text, errors="coerce", dayfirst=dayfirst)


def list_rows(old_raw, new_raw):
    """Both NSE lists -> one table: period_end, consolidated, filed, bank, xbrl."""
    rows = []
    for item in old_raw if isinstance(old_raw, list) else []:
        link = str(item.get("xbrl") or "")
        if not link.endswith(".xml"):
            continue
        rows.append({"period_end": _date(item.get("toDate")),
                     "consolidated": str(item.get("consolidated", "")).startswith("Consol"),
                     "filed": _date(item.get("broadCastDate") or item.get("filingDate")),
                     "bank": str(item.get("bank", "N")).upper() == "Y", "xbrl": link})
    items = new_raw.get("data", []) if isinstance(new_raw, dict) else new_raw or []
    for item in items:
        link = str(item.get("xbrl") or "")
        if not link.endswith(".xml") or "Financial" not in str(item.get("type", "Financials")):
            continue
        rows.append({"period_end": _date(item.get("qe_Date")),
                     "consolidated": str(item.get("consolidated", "")).startswith("Consol"),
                     "filed": _date(item.get("broadcast_Date")),
                     "bank": "BANKING" in link.upper(), "xbrl": link})
    table = pd.DataFrame(rows, columns=["period_end", "consolidated", "filed", "bank", "xbrl"])
    return table.dropna(subset=["period_end"])


def wanted_filings(listing):
    """One filing per period: consolidated if there is one, the original version.

    Every quarter from FILINGS_ALL_QUARTERS_FROM; before that only March and
    September, back to FILINGS_START.
    """
    if len(listing) == 0:
        return listing
    table = listing[listing["period_end"] >= pd.Timestamp(config.FILINGS_START)].copy()
    recent = table["period_end"] >= pd.Timestamp(config.FILINGS_ALL_QUARTERS_FROM)
    half_year = table["period_end"].dt.month.isin([3, 9])
    table = table[recent | half_year]
    # The original filing, not a later revision: its date is when the numbers
    # really became public, which keeps backtests honest.
    table = table.assign(_standalone=~table["consolidated"].astype(bool))
    table = table.sort_values(["period_end", "_standalone", "filed"])
    return table.drop_duplicates("period_end", keep="first").drop(columns="_standalone") \
        .reset_index(drop=True)


# ------------------------------------------------------------ one filing ----
_CONTEXT = re.compile(r"<(?:xbrli:)?context\s+id=\"([^\"]+)\"\s*>(.*?)</(?:xbrli:)?context>",
                      re.S)
_FACT = re.compile(r"<([\w-]+):(\w+)\s([^>]*?)>([^<]*)</\1:\2>")
_REF = re.compile(r'contextRef="([^"]+)"')


def parse_xbrl(text):
    """Read one results filing. Returns a list of rows, one per reported period.

    Each row: period_start, period_end, months, consolidated, the figures in
    FIGURES (rupees), and the balance sheet figures at the period end if the
    filing has them.
    """
    contexts = {}
    for cid, body in _CONTEXT.findall(text):
        if "explicitMember" in body or "typedMember" in body:
            continue                              # segment or detail breakdowns
        start = re.search(r"<(?:xbrli:)?startDate>([^<]+)<", body)
        end = re.search(r"<(?:xbrli:)?endDate>([^<]+)<", body)
        instant = re.search(r"<(?:xbrli:)?instant>([^<]+)<", body)
        contexts[cid] = {"start": start.group(1).strip() if start else None,
                         "end": end.group(1).strip() if end else None,
                         "instant": instant.group(1).strip() if instant else None}
    facts = {}
    for _, name, attributes, value in _FACT.findall(text):
        ref = _REF.search(attributes)
        if ref:
            facts.setdefault((name, ref.group(1)), value.strip())
    # Older filings (2018-2023) use the main contexts (OneD = this quarter,
    # FourD = year so far, OneI = balance sheet date) without defining them.
    # Their dates are in the filing's own "start/end of reporting period" facts.
    refs = {ref for (_, ref) in facts}
    for ref in refs - set(contexts):
        if re.fullmatch(r"(One|Two|Three|Four|Five|Six)D", ref):
            start = facts.get(("DateOfStartOfReportingPeriod", ref))
            end = facts.get(("DateOfEndOfReportingPeriod", ref)) \
                or facts.get(("DateOfEndOfReportingPeriod", "OneD"))
            if not start and end and ref == "OneD":            # some bank filings
                start = str((pd.Timestamp(end) - pd.offsets.QuarterBegin(1, startingMonth=1))
                            .date())
            if not start and ref == "FourD":
                start = facts.get(("DateOfStartOfFinancialYear", "OneD"))
            if start and end:
                contexts[ref] = {"start": start, "end": end, "instant": None}
    if "OneI" in refs and "OneI" not in contexts and "OneD" in contexts:
        contexts["OneI"] = {"start": None, "end": None, "instant": contexts["OneD"]["end"]}
    facts = {key: value for key, value in facts.items() if key[1] in contexts}

    def number(names, cid, skip_zero=False):
        for name in names:
            value = facts.get((name, cid))
            if value not in (None, ""):
                try:
                    found = float(value)
                except ValueError:
                    continue
                if skip_zero and found == 0:
                    continue              # some layouts fill an unused line with 0
                return found
        return np.nan

    nature = next((value for (name, _), value in facts.items()
                   if name == "NatureOfReportStandaloneConsolidated"), "")
    consolidated = str(nature).lower().startswith("consol")
    face_value = number(["FaceValueOfEquityShareCapital"], next(
        (cid for (name, cid) in facts if name == "FaceValueOfEquityShareCapital"), ""))

    balances = {}
    for cid, context in contexts.items():
        if context["instant"]:
            values = {key: number(names, cid) for key, names in BALANCE.items()}
            if any(not np.isnan(value) for value in values.values()):
                day = pd.Timestamp(context["instant"])
                # The current period end comes before the year-ago one in the filing.
                balances.setdefault(day, values)

    rows = []
    for cid, context in contexts.items():
        if not context["end"]:
            continue
        figures = {key: number(names, cid, skip_zero=(key == "net_income"))
                   for key, names in FIGURES.items()}
        bank = np.isnan(figures["revenue"]) and not np.isnan(number(["InterestEarned"], cid))
        if bank:
            parts = [number([name], cid) for name in BANK_REVENUE]
            figures["revenue"] = float(np.nansum(parts))
        if np.isnan(figures["revenue"]) and np.isnan(figures["net_income"]):
            continue
        start = facts.get(("DateOfStartOfReportingPeriod", cid)) or context["start"]
        end = facts.get(("DateOfEndOfReportingPeriod", cid)) or context["end"]
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        months = int(round((end - start).days / 30.44))
        if months not in (3, 6, 9, 12):
            continue
        row = {"period_start": start, "period_end": end, "months": months,
               "consolidated": consolidated, "bank": bank, **figures}
        balance = balances.get(end, {})
        row["equity"] = balance.get("equity", np.nan)
        now, later = balance.get("borrowings_now", np.nan), balance.get("borrowings_later", np.nan)
        row["borrowings"] = np.nan if np.isnan(now) and np.isnan(later) \
            else float(np.nansum([now, later]))
        capital = balance.get("share_capital", np.nan)
        row["shares"] = capital / face_value if face_value and face_value > 0 \
            and not np.isnan(capital) else np.nan
        rows.append(row)
    # The same period can appear twice (the quarter and the year so far are the
    # same thing in the first quarter): keep one.
    seen, unique = set(), []
    for row in rows:
        key = (row["period_start"], row["period_end"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


# ------------------------------------------------------------ storage -------
def load_results():
    """Every filing read so far, one row per company and reported period."""
    if not config.NSE_RESULTS_FILE.exists():
        return pd.DataFrame(columns=RESULT_COLUMNS)
    table = pd.read_csv(config.NSE_RESULTS_FILE, parse_dates=["period_start", "period_end",
                                                               "filed"])
    return table


def _load_tried():
    if not config.NSE_TRIED_FILE.exists():
        return pd.DataFrame(columns=TRIED_COLUMNS)
    return pd.read_csv(config.NSE_TRIED_FILE)


def _save(results, tried):
    config.NSE_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    results = results.drop_duplicates(["symbol", "period_start", "period_end", "consolidated"],
                                      keep="last")
    results.sort_values(["symbol", "period_end", "months"]).to_csv(config.NSE_RESULTS_FILE,
                                                                   index=False)
    tried.drop_duplicates(["symbol", "xbrl"], keep="last").to_csv(config.NSE_TRIED_FILE,
                                                                  index=False)


# ----------------------------------------------------------- downloading ----
def company_listing(browser, symbol):
    """The filings NSE lists for one company (both lists)."""
    from trading import nse
    old = nse.get_json(browser, OLD_LIST, index="equities", symbol=symbol, period="Quarterly")
    try:
        new = nse.get_json(browser, NEW_LIST, index="equities", symbol=symbol)
    except Exception:
        new = None
    return list_rows(old, new)


def fetch_company(browser, symbol, done_links):
    """Download and read one company's missing filings.

    Returns (rows read, links tried). A filing that cannot be read is still
    recorded as tried, so it is not downloaded again every day.
    """
    wanted = wanted_filings(company_listing(browser, symbol))
    rows, tried = [], []
    for item in wanted.itertuples():
        if item.xbrl in done_links:
            continue
        try:
            answer = browser.get(item.xbrl, timeout=60)
            parsed = parse_xbrl(answer.text) if answer.status_code == 200 else []
        except Exception:
            parsed = []
        for row in parsed:
            row.update(symbol=symbol, filed=item.filed, xbrl=item.xbrl)
            row["bank"] = bool(row["bank"] or item.bank)
            rows.append(row)
        tried.append({"symbol": symbol, "xbrl": item.xbrl,
                      "tried": pd.Timestamp.now().strftime("%Y-%m-%d")})
        time.sleep(config.FILINGS_PAUSE)
    return rows, tried


def update_filings(symbols, report=None, workers=None, max_seconds=None):
    """Download the missing result filings of these companies, saving as it goes.

    Stops after max_seconds (when given) so a long first download can be done
    in several runs; the next run carries on where this one stopped.
    Returns the number of companies finished.
    """
    from trading import nse
    workers = config.FILINGS_WORKERS if workers is None else workers
    results, tried = load_results(), _load_tried()
    done_links = set(tried["xbrl"])
    browser = nse.session()
    started = time.time()
    finished = 0
    symbols = list(symbols)
    batch = max(workers * 4, 8)
    for first in range(0, len(symbols), batch):
        if max_seconds is not None and time.time() - started > max_seconds:
            break
        group = symbols[first:first + batch]

        def work(symbol):
            try:
                return fetch_company(browser, symbol, done_links)
            except Exception:
                return [], []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(work, group))
        new_rows = [row for part in parts for row in part[0]]
        new_tried = [row for part in parts for row in part[1]]
        if new_rows:
            results = pd.concat([results, pd.DataFrame(new_rows, columns=RESULT_COLUMNS)],
                                ignore_index=True)
        if new_tried:
            tried = pd.concat([tried, pd.DataFrame(new_tried, columns=TRIED_COLUMNS)],
                              ignore_index=True)
            done_links |= {row["xbrl"] for row in new_tried}
        _save(results, tried)
        record_checked(group)
        finished += len(group)
        if report is not None:
            report("Company filings from NSE", min(first + batch, len(symbols)), len(symbols))
    return finished


def load_checked():
    """{symbol: day NSE's list of its filings was last checked}."""
    if not config.NSE_CHECKED_FILE.exists():
        return {}
    table = pd.read_csv(config.NSE_CHECKED_FILE, parse_dates=["checked"])
    return dict(zip(table["symbol"], table["checked"]))


def record_checked(symbols, day=None):
    day = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize() \
        if day is None else pd.Timestamp(day)
    checked = load_checked()
    checked.update({symbol: day for symbol in symbols})
    table = pd.DataFrame(sorted(checked.items()), columns=["symbol", "checked"])
    table["checked"] = pd.to_datetime(table["checked"]).dt.strftime("%Y-%m-%d")
    config.NSE_CHECKED_FILE.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(config.NSE_CHECKED_FILE, index=False)


def companies_missing(symbols):
    """Companies with no NSE filing read yet (the first download is not finished)."""
    have = set(_load_tried()["symbol"]) | set(load_checked())
    return [symbol for symbol in symbols if symbol not in have]


# --------------------------------------------------------------- tables -----
def _best(rows):
    """One row per company and period: consolidated first, then the earliest filing."""
    rows = rows.assign(_standalone=~rows["consolidated"].astype(bool))
    rows = rows.sort_values(["symbol", "period_end", "_standalone", "filed"])
    return rows.drop_duplicates(["symbol", "period_end"], keep="first").drop(columns="_standalone")


def quarterly_table(results=None):
    """Quarterly results from NSE: symbol, period_end, revenue, net_income, filed."""
    results = load_results() if results is None else results
    rows = _best(results[results["months"] == 3])
    return rows[["symbol", "period_end", "revenue", "net_income", "filed"]] \
        .reset_index(drop=True)


def annual_table(results=None):
    """Yearly results from NSE, with cash flow, profit before tax, finance costs, debt."""
    results = load_results() if results is None else results
    rows = _best(results[results["months"] == 12]).copy()
    rows["operating_income"] = rows["pbt"] + rows["finance_costs"].fillna(0.0)
    rows["total_debt"] = rows["borrowings"]
    columns = ["symbol", "period_end", "revenue", "operating_income", "net_income", "equity",
               "total_debt", "shares", "cfo", "capex", "pbt", "finance_costs", "bank", "filed"]
    return rows[columns].reset_index(drop=True)


def merge_with_yahoo(nse_rows, yahoo_rows, columns, fill=()):
    """NSE rows first; Yahoo rows for company-periods NSE does not have.

    fill: columns that, when empty in an NSE row, are taken from Yahoo's row
    for the same company and month (older NSE filings have no balance sheet).
    """
    if yahoo_rows is None or len(yahoo_rows) == 0:
        return nse_rows.reindex(columns=columns)
    if nse_rows is None or len(nse_rows) == 0:
        return yahoo_rows.reindex(columns=columns)
    yahoo = yahoo_rows.copy()
    yahoo["_month"] = yahoo["period_end"].dt.to_period("M")
    yahoo = yahoo.drop_duplicates(["symbol", "_month"], keep="last")
    nse = nse_rows.reindex(columns=columns).copy()
    nse["_month"] = nse["period_end"].dt.to_period("M")
    if fill:
        lookup = yahoo.set_index(["symbol", "_month"])
        keys = pd.MultiIndex.from_arrays([nse["symbol"], nse["_month"]])
        for column in fill:
            if column in lookup.columns:
                values = lookup[column].reindex(keys).to_numpy()
                nse[column] = nse[column].where(nse[column].notna(), values)
    have = set(zip(nse["symbol"], nse["_month"]))
    extra = yahoo[[(symbol, month) not in have
                   for symbol, month in zip(yahoo["symbol"], yahoo["_month"])]]
    parts = [nse.drop(columns="_month")]
    if len(extra):
        parts.append(extra.drop(columns="_month").reindex(columns=columns))
    combined = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
    return combined.sort_values(["symbol", "period_end"]).reset_index(drop=True)
