"""The company card: everything we know about one business in one place.

It brings together the price position (52-week range), size (market value),
valuation (PE, price to book, dividend yield), profitability (return on
equity, margin), safety (debt) and growth (1-year, 3-year, latest quarter).
A twelve-point scorecard counts how many common-sense checks the company passes.
From NSE's filings it also shows return on capital employed (ROCE) and whether
profit turns into cash (cash from operations against profit over 3 years).
"""

import pandas as pd

import config
from trading import fundamentals

CRORE = 1e7


def _known(value):
    return value is not None and not pd.isna(value)


def _growth(now, before):
    """Change from `before` to `now` as a fraction. Works when `before` was a loss."""
    if not _known(now) or not _known(before) or before == 0:
        return None
    return (now - before) / abs(before)


def _yearly_growth_rate(now, before, years):
    """Compound growth per year. Needs both values to be positive."""
    if not _known(now) or not _known(before) or now <= 0 or before <= 0 or years <= 0:
        return None
    return (now / before) ** (1 / years) - 1


def _row_near(rows, date_column, target, tolerance_days=25):
    """The row whose date is closest to `target`, if it is close enough."""
    if len(rows) == 0:
        return None
    gaps = (rows[date_column] - target).abs()
    if gaps.min() > pd.Timedelta(days=tolerance_days):
        return None
    return rows.loc[gaps.idxmin()]


def last_four_quarters(quarterly_rows):
    """Total sales and profit of the latest four quarters in a row (TTM).

    TTM means "trailing twelve months". Returns None if a quarter is missing,
    because adding up an incomplete year would give a wrong number.
    """
    if quarterly_rows is None or len(quarterly_rows) < 4:
        return None
    rows = quarterly_rows.sort_values("period_end").drop_duplicates("period_end").tail(4)
    span = rows["period_end"].iloc[-1] - rows["period_end"].iloc[0]
    if span > pd.Timedelta(days=290):       # four quarters in a row span about 9 months
        return None
    if rows[["revenue", "net_income"]].isna().any().any():
        return None
    return {
        "period_end": rows["period_end"].iloc[-1],
        "revenue": float(rows["revenue"].sum()),
        "net_income": float(rows["net_income"].sum()),
    }


def _roce_and_cash(years):
    """ROCE of the latest year, and cash conversion over the last 3 years.

    Needs NSE's figures (profit before tax, finance costs, cash from operations).
    """
    latest = years.iloc[-1]
    roce = None
    if _known(latest.get("pbt")) and _known(latest.get("equity")):
        capital = latest["equity"] + (latest["total_debt"] if _known(latest["total_debt"]) else 0)
        if capital > 0:
            finance = latest["finance_costs"] if _known(latest.get("finance_costs")) else 0
            roce = (latest["pbt"] + finance) / capital
    conversion = None
    if "cfo" in years:
        recent = years.tail(3)
        recent = recent[recent["cfo"].notna() & recent["net_income"].notna()]
        if len(recent) >= 2 and recent["net_income"].sum() > 0:
            conversion = recent["cfo"].sum() / recent["net_income"].sum()
    return roce, conversion


def build_card(symbol, prices, annual_rows, quarterly_rows=None, dividend_rows=None,
               industry=""):
    """Work out every figure on the card for one company.

    prices: that stock's price table. The other tables hold only that
    company's rows and may be None. Returns a dictionary; a figure that
    cannot be worked out is None.
    """
    close = float(prices["Close"].iloc[-1])
    year = prices.tail(252)
    card = {
        "symbol": symbol,
        "industry": industry,
        "as_of": prices.index[-1],
        "close": close,
        "high_52w": float(year["High"].max()),
        "low_52w": float(year["Low"].min()),
    }
    card["below_52w_high"] = close / card["high_52w"] - 1

    names = [
        "financial_year", "market_cap_crore", "revenue_crore", "profit_crore",
        "sales_growth_1y", "profit_growth_1y", "sales_growth_3y", "profit_growth_3y",
        "net_margin", "return_on_equity", "debt_to_equity", "book_value", "price_to_book",
        "eps", "pe", "earnings_basis", "quarter", "quarter_sales_growth",
        "quarter_profit_growth", "dividend_yield", "industry_pe",
        "roce", "cash_conversion", "cash_from_operations_crore", "results_filed",
    ]
    card.update({name: None for name in names})
    card["owners"] = None      # shareholding pattern, filled in by screens.py

    if annual_rows is not None and len(annual_rows) > 0:
        years = annual_rows.sort_values("period_end").reset_index(drop=True)
        latest = years.iloc[-1]
        previous = _row_near(years.iloc[:-1], "period_end",
                             latest["period_end"] - pd.DateOffset(years=1))
        three_back = _row_near(years.iloc[:-1], "period_end",
                               latest["period_end"] - pd.DateOffset(years=3))
        shares, equity = latest["shares"], latest["equity"]

        card["financial_year"] = latest["period_end"]
        card["revenue_crore"] = latest["revenue"] / CRORE if _known(latest["revenue"]) else None
        card["profit_crore"] = (
            latest["net_income"] / CRORE if _known(latest["net_income"]) else None
        )
        if previous is not None:
            card["sales_growth_1y"] = _growth(latest["revenue"], previous["revenue"])
            card["profit_growth_1y"] = _growth(latest["net_income"], previous["net_income"])
        if three_back is not None:
            card["sales_growth_3y"] = _yearly_growth_rate(
                latest["revenue"], three_back["revenue"], 3)
            card["profit_growth_3y"] = _yearly_growth_rate(
                latest["net_income"], three_back["net_income"], 3)
        card["net_margin"] = fundamentals._ratio(latest["net_income"], latest["revenue"])
        card["roce"], card["cash_conversion"] = _roce_and_cash(years)
        if _known(latest.get("cfo")):
            card["cash_from_operations_crore"] = latest["cfo"] / CRORE
        card["return_on_equity"] = fundamentals._ratio(latest["net_income"], equity)
        card["debt_to_equity"] = fundamentals._ratio(latest["total_debt"], equity)

        if _known(shares) and shares > 0:
            card["market_cap_crore"] = close * shares / CRORE
            if _known(equity) and equity > 0:
                card["book_value"] = equity / shares
                card["price_to_book"] = close / card["book_value"]

            # Earnings per share: the last four quarters if complete, else the last year.
            recent = last_four_quarters(quarterly_rows)
            if recent is not None and recent["period_end"] >= latest["period_end"]:
                profit, card["earnings_basis"] = recent["net_income"], "last 4 quarters"
            else:
                profit, card["earnings_basis"] = latest["net_income"], "last full year"
            if _known(profit):
                card["eps"] = profit / shares
                if profit > 0:
                    card["pe"] = close / card["eps"]

    if quarterly_rows is not None and len(quarterly_rows) > 0:
        quarters = quarterly_rows.sort_values("period_end").reset_index(drop=True)
        latest = quarters.iloc[-1]
        year_ago = _row_near(quarters.iloc[:-1], "period_end",
                             latest["period_end"] - pd.DateOffset(years=1))
        card["quarter"] = latest["period_end"]
        if _known(latest.get("filed")):
            card["results_filed"] = pd.Timestamp(latest["filed"])
        if year_ago is not None:
            card["quarter_sales_growth"] = _growth(latest["revenue"], year_ago["revenue"])
            card["quarter_profit_growth"] = _growth(
                latest["net_income"], year_ago["net_income"])

    if dividend_rows is not None and len(dividend_rows) > 0:
        one_year_ago = card["as_of"] - pd.Timedelta(days=365)
        paid = dividend_rows[dividend_rows["date"] > one_year_ago]["amount"].sum()
        card["dividend_yield"] = float(paid) / close
    elif annual_rows is not None and len(annual_rows) > 0:
        card["dividend_yield"] = 0.0      # results exist and no dividend is on record

    return card


def scorecard(card, is_financial=False):
    """Twelve yes/no checks. Returns a list of (check, passed).

    passed is True, False, or None when the figure is not available.
    """
    def at_least(value, minimum):
        return None if not _known(value) else value >= minimum

    growth = config.SCORE_MIN_GROWTH
    if is_financial:
        low_debt = True                    # borrowing is a bank's raw material
    elif _known(card["debt_to_equity"]):
        low_debt = card["debt_to_equity"] <= config.SCORE_MAX_DEBT_TO_EQUITY
    else:
        low_debt = None

    cheaper = None
    if _known(card["pe"]) and _known(card["industry_pe"]):
        cheaper = card["pe"] <= card["industry_pe"]

    return [
        (f"Sales grew {growth:.0%} or more last year", at_least(card["sales_growth_1y"], growth)),
        (f"Profit grew {growth:.0%} or more last year", at_least(card["profit_growth_1y"], growth)),
        (f"Sales grew {growth:.0%} a year over 3 years", at_least(card["sales_growth_3y"], growth)),
        (f"Profit grew {growth:.0%} a year over 3 years", at_least(card["profit_growth_3y"], growth)),
        ("Latest quarter's profit is higher than a year ago",
         None if not _known(card["quarter_profit_growth"]) else card["quarter_profit_growth"] > 0),
        (f"Return on equity {config.SCORE_MIN_RETURN_ON_EQUITY:.0%} or more",
         at_least(card["return_on_equity"], config.SCORE_MIN_RETURN_ON_EQUITY)),
        (f"Profit margin {config.SCORE_MIN_NET_MARGIN:.0%} or more",
         at_least(card["net_margin"], config.SCORE_MIN_NET_MARGIN)),
        ("Low debt", low_debt),
        ("PE is not above the industry's", cheaper),
        ("Pays a dividend",
         None if not _known(card["dividend_yield"]) else card["dividend_yield"] > 0),
        (f"Return on capital employed {config.SCORE_MIN_ROCE:.0%} or more",
         None if is_financial else at_least(card.get("roce"), config.SCORE_MIN_ROCE)),
        (f"Cash from operations at least {config.SCORE_MIN_CASH_CONVERSION:.0%} of profit "
         "(3 years)",
         None if is_financial else at_least(card.get("cash_conversion"),
                                            config.SCORE_MIN_CASH_CONVERSION)),
    ]


def score(card, is_financial=False):
    """Number of checks passed, out of twelve. Unknown checks do not count."""
    return sum(1 for _, passed in scorecard(card, is_financial) if passed)


def industry_pe(cards):
    """Middle (median) PE of each industry, from the cards of its companies.

    Needs at least three companies with a PE to say anything about an industry.
    """
    table = pd.DataFrame(
        [(card["industry"], card["pe"]) for card in cards
         if card["industry"] and _known(card["pe"])],
        columns=["industry", "pe"],
    )
    grouped = table.groupby("industry")["pe"]
    return grouped.median()[grouped.count() >= 3].to_dict()


# ------------------------------------------------------------------ display -
def _pct(value):
    return "-" if not _known(value) else f"{value * 100:+.1f}%"


def _num(value, digits=2):
    return "-" if not _known(value) else f"{value:,.{digits}f}"


def _day(value):
    return "-" if not _known(value) else str(pd.Timestamp(value).date())


def format_card(card, is_financial=False, next_results=None):
    """The card as readable text. Plain ASCII so Windows prints it."""
    checks = scorecard(card, is_financial)
    marks = {True: "yes", False: "no ", None: " - "}
    lines = [
        f"{card['symbol']}  ({card['industry'] or 'industry not known'})   prices to {_day(card['as_of'])}",
        "",
        "PRICE",
        f"  Close                 {_num(card['close'])}",
        f"  52-week low / high    {_num(card['low_52w'])} / {_num(card['high_52w'])}"
        f"   ({_pct(card['below_52w_high'])} from the high)",
        "",
        "SIZE AND VALUATION",
        f"  Market value          Rs {_num(card['market_cap_crore'], 0)} crore",
        f"  PE                    {_num(card['pe'], 1)}   (profit of the {card['earnings_basis'] or '-'})",
        f"  Industry PE           {_num(card['industry_pe'], 1)}",
        f"  Earnings per share    {_num(card['eps'])}",
        f"  Price to book         {_num(card['price_to_book'])}   (book value {_num(card['book_value'])} a share)",
        f"  Dividend yield        {_pct(card['dividend_yield']).lstrip('+')}",
        "",
        f"BUSINESS  (financial year ended {_day(card['financial_year'])})",
        f"  Sales                 Rs {_num(card['revenue_crore'], 0)} crore",
        f"  Profit                Rs {_num(card['profit_crore'], 0)} crore",
        f"  Profit margin         {_pct(card['net_margin']).lstrip('+')}",
        f"  Return on equity      {_pct(card['return_on_equity']).lstrip('+')}",
        f"  Debt to equity        {_num(card['debt_to_equity'])}",
        f"  Return on capital     {_pct(card.get('roce')).lstrip('+')}   (ROCE)",
        f"  Cash from operations  Rs {_num(card.get('cash_from_operations_crore'), 0)} crore"
        f"   (3-year cash / profit {_num(card.get('cash_conversion'))})",
        "",
        "GROWTH",
        f"  Sales, 1 year         {_pct(card['sales_growth_1y'])}",
        f"  Profit, 1 year        {_pct(card['profit_growth_1y'])}",
        f"  Sales, 3 years        {_pct(card['sales_growth_3y'])} a year",
        f"  Profit, 3 years       {_pct(card['profit_growth_3y'])} a year",
        f"  Latest quarter ({_day(card['quarter'])}) against a year ago:"
        f" sales {_pct(card['quarter_sales_growth'])}, profit {_pct(card['quarter_profit_growth'])}",
        f"  Next results          {_day(next_results)}",
    ]
    lines += ["", *_owner_lines(card.get("owners"))]
    lines += ["", f"SCORECARD  {score(card, is_financial)} of {len(checks)} checks passed"]
    lines += [f"  [{marks[passed]}] {name}" for name, passed in checks]
    return "\n".join(lines)


def _owner_lines(owners):
    """The shareholding section of the card."""
    if owners is None:
        return ["WHO OWNS IT", "  Shareholding not downloaded for this company."]

    def change(value):
        return "" if not _known(value) else f"   ({value:+.2f} from the quarter before)"

    lines = [f"WHO OWNS IT  (quarter ended {_day(owners['quarter_end'])})"]
    labels = [
        ("promoter", "Promoters"), ("fii", "Foreign institutions"),
        ("dii", "Indian institutions"), ("mutual_funds", "  of which mutual funds"),
        ("insurance", "  of which insurers"), ("public", "Public and others"),
    ]
    for key, label in labels:
        lines.append(f"  {label:24s}{owners[key]:6.2f}%{change(owners[key + '_change'])}")
    pledged = {True: "yes", False: "no", None: "-"}[owners["promoters_pledged"]]
    lines.append(f"  Promoter shares pledged   {pledged}")
    if owners["funds"]:
        lines.append("  Mutual fund schemes holding over 1%:")
        lines += [f"    {percent:5.2f}%  {name}" for name, percent in owners["funds"]]
    else:
        lines.append("  No single mutual fund scheme holds over 1%.")
    return lines
