"""Rule set E: the full model. Every factor the system collects, in one score.

Each stock gets a score from 0 to 100 on each day it is checked:

  1. Every factor (for example "profit growth" or "change in mutual fund
     holding") is turned into a rank among that day's stocks: near 1 for the
     best stock, near 0 for the worst. A factor that is not known for a stock gets 0.5,
     the middle, so missing data neither helps nor hurts.
  2. The ranks are averaged inside six groups: ownership, business, valuation,
     price, news and flows.
  3. The six group scores are combined using the weights in config.py.

The whole market gets its own set of yes/no checks (Nifty's trend, India VIX,
global markets, the rupee, crude oil, gold, FII buying). New money goes in
only when at least half of them pass; otherwise the rule holds cash.

The same score can be traded in two styles (MODEL_STYLES in config.py):
  - swing:   follows each stock's own trend. On the first trading day of every
             week it buys from the top 10 scores, 5 stocks in equal amounts,
             only stocks above their 20-day EMA. A holding is sold the day
             after it closes below that EMA, or 8% below its buy price. So a
             trade lasts as long as its trend: a week for some, a month for others.
  - monthly: checked on the first trading day of each month, 10 stocks, kept
             while in the top 20, no stop-loss.
A stock with results due in the next few days is not bought. The lowest
scores are listed as sell / avoid candidates.

Nothing uses information from the future: results count from the day after
the company filed them with NSE (when the NSE filing is known; otherwise 75
days after the year ends, 45 after the quarter), shareholding from the day it
was filed, prices and news only up to the day of the check.
"""

import numpy as np
import pandas as pd

import config
from trading import (data, flows, fundamentals, indicators, news, pledge, rotation,
                     shareholding)

# Factor name -> +1 when a higher figure is better, -1 when a lower one is.
GROUPS = {
    "ownership": {
        "fii_change": 1, "mf_change": 1, "promoter_change": 1, "dii_change": 1,
        "insurance_change": 1, "public_change": -1, "pledged": -1, "fund_count": 1,
        "pledged_pct": -1,
    },
    "business": {
        "sales_growth": 1, "profit_growth": 1, "sales_growth_3y": 1, "profit_growth_3y": 1,
        "net_margin": 1, "return_on_equity": 1, "debt_to_equity": -1,
        "quarter_sales_growth": 1, "quarter_profit_growth": 1, "scorecard": 1,
        "roce": 1, "cash_conversion": 1,
    },
    "valuation": {
        "pe_vs_industry": -1, "price_to_book": -1, "earnings_yield": 1, "dividend_yield": 1,
    },
    "price": {
        "momentum": 1, "trend": 1, "rsi": 1, "volume_ratio": 1, "atr_pct": -1, "near_high": 1,
    },
    "news": {"news_score": 1},
    "flows": {"deal_score": 1},
}

# How one announcement counts in the news score. Only the type is known, not
# whether the news is good or bad, so these are rough.
NEWS_POINTS = {"Orders and contracts": 1.0, "Dividend and bonus": 0.5,
               "Legal and regulatory": -1.0}

GLOBAL_MARKETS = ["SP500", "NASDAQ", "FTSE100", "NIKKEI225", "HANGSENG", "SHANGHAI"]


# ------------------------------------------------- preparing the tables -----
def _years_apart(days, years):
    return days.between(365 * years - 65, 365 * years + 65)


def annual_factors(annual):
    """Growth and ratio figures for every company-year, with the day they count from."""
    table = annual.sort_values(["symbol", "period_end"]).reset_index(drop=True)
    by_company = table.groupby("symbol")
    revenue, profit, equity = table["revenue"], table["net_income"], table["equity"]

    def earlier(column, years):
        gap = (table["period_end"] - by_company["period_end"].shift(years)).dt.days
        return by_company[column].shift(years).where(_years_apart(gap, years))

    revenue_1, profit_1 = earlier("revenue", 1), earlier("net_income", 1)
    revenue_3, profit_3 = earlier("revenue", 3), earlier("net_income", 3)

    # Return on capital employed: profit before interest and tax / (equity + debt).
    # Only from NSE filings, which give profit before tax and finance costs.
    def column(name):
        return table[name] if name in table else pd.Series(np.nan, index=table.index)

    pbt, finance = column("pbt"), column("finance_costs")
    capital = equity + column("total_debt").fillna(0.0)
    roce = ((pbt + finance.fillna(0.0)) / capital).where((capital > 0) & pbt.notna())
    # Cash conversion: cash from operations / profit over the last 3 years (at
    # least 2 with cash flow known). Below about 0.8 the profit is not turning
    # into cash.
    cfo = column("cfo")
    if "cfo" in table:
        cash_years = [cfo, earlier("cfo", 1), earlier("cfo", 2)]
        profit_years = [profit, earlier("net_income", 1), earlier("net_income", 2)]
        known = sum(cash.notna().astype(int) for cash in cash_years)
        cash_3 = sum(cash.fillna(0.0) for cash in cash_years)
        profit_3 = sum(earned.where(cash.notna(), 0.0).fillna(0.0)
                       for earned, cash in zip(profit_years, cash_years))
        usable = (known >= 2) & (profit_3 > 0)
        cash_conversion = (cash_3 / profit_3).where(usable)
    else:
        cash_conversion = pd.Series(np.nan, index=table.index)

    # The day a year's numbers became public: NSE's filing time when known,
    # otherwise a fixed lag after the year end.
    lagged = table["period_end"] + pd.Timedelta(days=config.REPORTING_LAG_DAYS)
    filed = pd.to_datetime(column("filed"), errors="coerce").dt.normalize() \
        + pd.Timedelta(days=1)
    available = filed.where(filed.notna(), lagged)
    return pd.DataFrame({
        "symbol": table["symbol"],
        "period_end": table["period_end"],
        "available": available,
        "roce": roce, "cash_conversion": cash_conversion,
        "net_income": profit, "equity": equity, "shares": table["shares"],
        "sales_growth": (revenue / revenue_1 - 1).where(revenue_1 > 0),
        "profit_growth": ((profit - profit_1) / profit_1.abs()).where(profit_1 != 0),
        "sales_growth_3y": ((revenue / revenue_3) ** (1 / 3) - 1).where(
            (revenue_3 > 0) & (revenue > 0)),
        "profit_growth_3y": ((profit / profit_3) ** (1 / 3) - 1).where(
            (profit_3 > 0) & (profit > 0)),
        "net_margin": (profit / revenue).where(revenue > 0),
        "return_on_equity": (profit / equity).where(equity > 0),
        "debt_to_equity": (table["total_debt"] / equity).where(equity > 0),
    })


def quarterly_factors(quarterly):
    """Each quarter against the same quarter a year before, and the last four added up."""
    table = quarterly.sort_values(["symbol", "period_end"]).copy()
    table["number"] = table["period_end"].dt.year * 4 + table["period_end"].dt.quarter
    table = table.drop_duplicates(["symbol", "number"], keep="last").reset_index(drop=True)

    year_ago = table[["symbol", "number", "revenue", "net_income"]].copy()
    year_ago["number"] += 4
    table = table.merge(year_ago, on=["symbol", "number"], how="left", suffixes=("", "_before"))

    by_company = table.groupby("symbol")
    four = by_company["net_income"].rolling(4).sum().reset_index(level=0, drop=True)
    in_a_row = (table["number"] - by_company["number"].shift(3)) == 3
    before = table["net_income_before"]
    lagged = table["period_end"] + pd.Timedelta(days=config.MODEL_QUARTER_LAG_DAYS)
    if "filed" in table:
        filed = pd.to_datetime(table["filed"], errors="coerce").dt.normalize() \
            + pd.Timedelta(days=1)
        available = filed.where(filed.notna(), lagged)
    else:
        available = lagged
    return pd.DataFrame({
        "symbol": table["symbol"],
        "quarter_end": table["period_end"],
        "available": available,
        "quarter_sales_growth": (table["revenue"] / table["revenue_before"] - 1).where(
            table["revenue_before"] > 0),
        "quarter_profit_growth": ((table["net_income"] - before) / before.abs()).where(
            before != 0),
        "profit_4_quarters": four.where(in_a_row),
    })


def ownership_factors(holdings, fund_holders=None):
    """Each quarter's change in every holder group, with the day it was filed."""
    table = holdings.sort_values(["symbol", "quarter_end"]).reset_index(drop=True)
    by_company = table.groupby("symbol")
    expected = table["quarter_end"] - pd.offsets.QuarterEnd(1)
    follows_on = by_company["quarter_end"].shift(1) == expected

    out = pd.DataFrame({
        "symbol": table["symbol"],
        "quarter_end": table["quarter_end"],
        "available": table["filed_on"].fillna(
            table["quarter_end"] + pd.Timedelta(days=config.MODEL_QUARTER_LAG_DAYS)),
        "pledged": table["promoters_pledged"].astype(float),
    })
    names = {"fii": "fii_change", "mutual_funds": "mf_change", "promoter": "promoter_change",
             "dii": "dii_change", "insurance": "insurance_change", "public": "public_change"}
    for column, name in names.items():
        out[name] = (table[column] - by_company[column].shift(1)).where(follows_on)
    # NSE changed how foreign holdings are reported; that quarter cannot be compared.
    out.loc[out["quarter_end"] == rotation.FORMAT_CHANGE, "fii_change"] = np.nan

    out["fund_count"] = 0.0
    if fund_holders is not None and len(fund_holders) > 0:
        counts = fund_holders.groupby(["symbol", "quarter_end"]).size().rename("schemes")
        joined = out.join(counts, on=["symbol", "quarter_end"])
        out["fund_count"] = joined["schemes"].fillna(0.0).to_numpy()
    return out


def _latest(table, day, date_column, max_age_days):
    """Each company's newest row that was public on `day` and is not too old."""
    if table is None or len(table) == 0:
        return pd.DataFrame()
    rows = table[(table["available"] <= day)
                 & (table[date_column] >= day - pd.Timedelta(days=max_age_days))]
    rows = rows.sort_values(["symbol", date_column])
    return rows.drop_duplicates("symbol", keep="last").set_index("symbol")


# ------------------------------------------------------------ price side ----
def price_factors(prepared, stocks):
    """Chart figures for every stock on every day, as wide tables."""
    calendar = prepared["calendar"]
    close = prepared["last_close"]
    high = rotation._wide(stocks, "High", calendar).ffill()
    low = rotation._wide(stocks, "Low", calendar).ffill()
    volume = rotation._wide(stocks, "Volume", calendar)

    fast = indicators.ema(close, config.EMA_FAST)
    slow = indicators.ema(close, config.EMA_SLOW)
    before = close.shift(1)
    day_range = np.maximum(high - low, np.maximum((high - before).abs(), (low - before).abs()))
    average_range = day_range.ewm(alpha=1 / config.ATR_PERIOD, adjust=False,
                                  min_periods=config.ATR_PERIOD).mean()
    return {
        "momentum": prepared["momentum"],
        "trend": (close > fast).astype(float) + (fast > slow).astype(float),
        "rsi": indicators.rsi(close, config.RSI_PERIOD),
        "volume_ratio": volume.rolling(20).mean() / volume.rolling(120).mean(),
        "atr_pct": average_range / close,
        "near_high": close / high.rolling(252, min_periods=120).max() - 1,
    }


# ----------------------------------------------------------- market side ----
def market_checks(nifty, markets, fii_net=None):
    """Yes/no checks on the whole market for every day.

    markets: {name: closing prices} for India VIX and the global series.
    fii_net: daily net buying by foreign institutions (Rs crore), if saved.
    Returns a table with one column per check: 1 passed, 0 failed, empty if
    the figure is not known that day.
    """
    calendar = nifty.index
    close = nifty["Close"]
    month = config.MODEL_MONTH_DAYS

    def series(name):
        values = markets.get(name)
        return None if values is None else values.reindex(calendar, method="ffill")

    def month_change(name):
        values = series(name)
        return None if values is None else values / values.shift(month) - 1

    def as_check(passed, known):
        return passed.astype(float).where(known)

    checks = {}
    average = close.rolling(config.ROTATION_MARKET_SMA).mean()
    checks[f"Nifty above its {config.ROTATION_MARKET_SMA}-day average"] = as_check(
        close > average, average.notna())
    trend = indicators.ema(close, config.MARKET_EMA)
    checks[f"Nifty above its {config.MARKET_EMA}-day EMA"] = as_check(close > trend, trend.notna())

    vix = series("INDIAVIX")
    if vix is not None:
        checks[f"India VIX below {config.MODEL_VIX_MAX}"] = as_check(
            vix < config.MODEL_VIX_MAX, vix.notna())

    changes = pd.DataFrame({name: month_change(name) for name in GLOBAL_MARKETS
                            if series(name) is not None})
    if len(changes.columns):
        risen = (changes > 0).sum(axis=1) / changes.notna().sum(axis=1).replace(0, np.nan)
        checks["At least half the global markets rose over the last month"] = as_check(
            risen >= 0.5, risen.notna())

    limits = [("USDINR", config.MODEL_RUPEE_FALL_MAX, "Rupee not falling fast"),
              ("BRENT", config.MODEL_CRUDE_RISE_MAX, "Crude oil not jumping"),
              ("GOLD", config.MODEL_GOLD_RISE_MAX, "Gold not surging (money is not running to safety)")]
    for name, limit, label in limits:
        change = month_change(name)
        if change is not None:
            checks[label] = as_check(change <= limit, change.notna())

    label = "Foreign institutions net buyers over the last 5 days"
    checks[label] = pd.Series(np.nan, index=calendar)
    if fii_net is not None and len(fii_net) > 0:
        total = fii_net.reindex(calendar).rolling(5, min_periods=3).sum()
        checks[label] = as_check(total > 0, total.notna())
    return pd.DataFrame(checks)


def market_score(checks):
    """Share of the known checks that passed, for every day (0 to 1)."""
    return checks.mean(axis=1, skipna=True)


# ------------------------------------------------------------- the score ----
def combine(factors, weights=None):
    """Turn a table of raw factors into group scores and one total score.

    factors: one row per stock, one column per factor (missing columns are
    treated as unknown). weights: {group: weight}, config.MODEL_WEIGHTS when not
    given. Returns the same table with a column per group and `score`, all from
    0 to 100, sorted best first.
    """
    weights = config.MODEL_WEIGHTS if weights is None else weights
    table = factors.copy()
    total = pd.Series(0.0, index=table.index)
    for group, members in GROUPS.items():
        ranks = []
        for name, direction in members.items():
            values = (table[name].astype(float) if name in table.columns
                      else pd.Series(np.nan, index=table.index))
            signed = values * direction
            # Worst stock just above 0, best just below 1, and the average exactly 0.5,
            # so a known figure is on average worth the same as an unknown one.
            ranks.append(((signed.rank() - 0.5) / max(signed.count(), 1)).fillna(0.5))
        table[group] = sum(ranks) / len(ranks) * 100
        total += table[group] * weights.get(group, 0.0)
    table["score"] = total / sum(weights.values())
    return table.sort_values("score", ascending=False, kind="stable")


def _industry_scorecard(table, industry, financial):
    """The twelve checks, each against the company's own industry instead of fixed numbers.

    A check passes when the company is at least as good as its industry's median
    (industries with fewer than 5 scored companies use the whole market's median).
    """
    def at_least_median(name, higher_better=True):
        values = table[name].astype(float)
        by_industry = values.groupby(industry)
        median = by_industry.transform("median").where(by_industry.transform("count") >= 5)
        median = median.fillna(values.median())
        return values >= median if higher_better else values <= median

    return [
        at_least_median("sales_growth"), at_least_median("profit_growth"),
        at_least_median("sales_growth_3y"), at_least_median("profit_growth_3y"),
        table["quarter_profit_growth"] > 0,
        at_least_median("return_on_equity"), at_least_median("net_margin"),
        financial | at_least_median("debt_to_equity", higher_better=False),
        table["pe"] <= table["industry_pe"],
        table["dividend_yield"] > 0,
        financial | at_least_median("roce"),
        financial | at_least_median("cash_conversion"),
    ]


def latest_shares(annual, quarterly=None):
    """Each company's most recent share count, {symbol: shares}.

    Prices from Yahoo are adjusted for splits and bonus issues back to today, so the
    share count that matches them on every past day is today's, not the count filed
    at the time (that one is 10x off before a 1:10 split). New shares issued since
    are the only error left, usually a few percent.
    """
    tables = [t[["symbol", "period_end", "shares"]] for t in (annual, quarterly)
              if t is not None and len(t) and "shares" in t]
    if not tables:
        return pd.Series(dtype=float)
    table = pd.concat(tables).dropna(subset=["shares"])
    table = table[table["shares"] > 0].sort_values("period_end")
    return table.groupby("symbol")["shares"].last()


class Model:
    """Holds every table once, and scores all stocks on any day."""

    def __init__(self, stocks, nifty, membership_mask, tables, markets):
        """tables: dictionary with annual, quarterly, dividends, results, holdings,
        fund_holders, industry ({symbol: industry}), news, deals, fii_net. Any may be None.
        """
        self.prepared = rotation.prepare(stocks, nifty, membership_mask)
        self.calendar = self.prepared["calendar"]
        self.price = price_factors(self.prepared, stocks)

        get = tables.get
        self.annual = None if get("annual") is None else annual_factors(get("annual"))
        self.latest_shares = latest_shares(get("annual"), get("quarterly"))
        self.quarterly = None if get("quarterly") is None else quarterly_factors(get("quarterly"))
        self.ownership = (None if get("holdings") is None
                          else ownership_factors(get("holdings"), get("fund_holders")))
        self.dividends = get("dividends")
        self.results = get("results")
        self.industry = get("industry") or {}
        self.news = get("news")
        self.deals = get("deals")
        # Each filing read as good or bad once (only used when MODEL_NEWS_MODE is "lean").
        self.news_read = None
        if self.news is not None and len(self.news) > 0:
            from trading import newsview
            read = newsview.read_all(self.news, None, get("quarterly"), read_pdfs="saved")
            self.news_read = read[["time", "symbol", "lean"]]
        self.pledges = get("pledges")

        # A stock is "in trend" while it closes above its short trend line (20-day EMA).
        close = self.prepared["last_close"]
        trend_line = indicators.ema(close, config.EMA_FAST)
        in_trend = (close > trend_line).fillna(False)
        self.checks = market_checks(nifty, markets, get("fii_net"))
        # Market breadth: share of liquid stocks above their 20-day EMA (optional check).
        liquid = self.prepared["liquid"]
        self.breadth = (in_trend & liquid).sum(axis=1) / liquid.sum(axis=1).replace(0, np.nan)
        if config.MODEL_BREADTH_MIN:
            self.checks[f"At least {config.MODEL_BREADTH_MIN:.0%} of stocks above their "
                        f"{config.EMA_FAST}-day average"] = \
                (self.breadth >= config.MODEL_BREADTH_MIN).astype(float).where(self.breadth.notna())
        self.market_score = market_score(self.checks)
        self.market_ok = (self.market_score >= config.MODEL_MARKET_MIN).fillna(False)
        # Entry quality: how far above the trend line, and how much it rose in 5 days.
        room = close / trend_line - 1
        spike = close / close.shift(config.SPIKE_DAYS) - 1
        fast_line = indicators.ema(close, config.EMA_PROFIT_TRAIL)
        self.trading = {**self.prepared, "market_ok": self.market_ok, "in_trend": in_trend,
                        "in_trend_fast": (close > fast_line).fillna(False),
                        "room": room, "spike": spike,
                        "cash_reason": "too few market checks passed"}
        self._cache = {}
        self.measured_weights = {}       # {position: {group: weight}}, see trading/weights.py

    # ---- one day's factors ----
    def factors_on(self, position):
        """Raw factors for every stock that may be traded on that day."""
        day = self.calendar[position]
        liquid = self.prepared["liquid"].iloc[position]
        symbols = liquid.index[liquid.to_numpy(dtype=bool)]
        table = pd.DataFrame(index=pd.Index(symbols, name="symbol"))
        close = self.prepared["last_close"].iloc[position].reindex(symbols)
        table["close"] = close
        for name, frame in self.price.items():
            table[name] = frame.iloc[position].reindex(symbols)

        industry = pd.Series({symbol: self.industry.get(symbol, "") for symbol in symbols},
                             dtype=object).reindex(symbols)
        financial = industry == config.FINANCIAL_INDUSTRY

        # ---- business ----
        year = _latest(self.annual, day, "period_end", 640).reindex(symbols)
        quarter = _latest(self.quarterly, day, "quarter_end", 250).reindex(symbols)
        for name in ["sales_growth", "profit_growth", "sales_growth_3y", "profit_growth_3y",
                     "net_margin", "return_on_equity", "debt_to_equity", "roce",
                     "cash_conversion"]:
            table[name] = year[name] if name in year else np.nan
        # Borrowing is a bank's raw material, and its cash flow is mostly lending:
        # debt, ROCE and cash conversion say nothing about a finance company.
        table.loc[financial, ["debt_to_equity", "roce", "cash_conversion"]] = np.nan
        for name in ["quarter_sales_growth", "quarter_profit_growth"]:
            table[name] = quarter[name] if name in quarter else np.nan

        # ---- valuation ----
        profit = year["net_income"] if "net_income" in year else pd.Series(np.nan, index=symbols)
        if "profit_4_quarters" in quarter:
            newer = quarter["quarter_end"] >= year["period_end"]
            profit = quarter["profit_4_quarters"].where(
                newer & quarter["profit_4_quarters"].notna(), profit)
        if config.MODEL_SHARES == "latest":
            shares = self.latest_shares.reindex(symbols)
        else:
            shares = year["shares"] if "shares" in year else pd.Series(np.nan, index=symbols)
        equity = year["equity"] if "equity" in year else pd.Series(np.nan, index=symbols)
        earnings_per_share = (profit / shares).where(shares > 0)
        table["earnings_yield"] = earnings_per_share / close
        table["pe"] = (close / earnings_per_share).where(earnings_per_share > 0)
        table["price_to_book"] = (close * shares / equity).where((equity > 0) & (shares > 0))
        pe_by_industry = table["pe"].groupby(industry).transform(
            lambda values: values.median() if values.count() >= 3 else np.nan)
        table["industry_pe"] = pe_by_industry.where(industry != "")
        table["pe_vs_industry"] = table["pe"] / table["industry_pe"]

        table["dividend_yield"] = np.nan
        if self.dividends is not None:
            paid = self.dividends[(self.dividends["date"] > day - pd.Timedelta(days=365))
                                  & (self.dividends["date"] <= day)]
            paid = paid.groupby("symbol")["amount"].sum().reindex(symbols).fillna(0.0)
            table["dividend_yield"] = (paid / close).where(profit.notna() | (paid > 0))

        # ---- the twelve-point scorecard ----
        growth = config.SCORE_MIN_GROWTH
        passed = [
            table["sales_growth"] >= growth, table["profit_growth"] >= growth,
            table["sales_growth_3y"] >= growth, table["profit_growth_3y"] >= growth,
            table["quarter_profit_growth"] > 0,
            table["return_on_equity"] >= config.SCORE_MIN_RETURN_ON_EQUITY,
            table["net_margin"] >= config.SCORE_MIN_NET_MARGIN,
            financial | (table["debt_to_equity"] <= config.SCORE_MAX_DEBT_TO_EQUITY),
            table["pe"] <= table["industry_pe"],
            table["dividend_yield"] > 0,
            financial | (table["roce"] >= config.SCORE_MIN_ROCE),
            financial | (table["cash_conversion"] >= config.SCORE_MIN_CASH_CONVERSION),
        ]
        if config.MODEL_SCORECARD == "industry":
            passed = _industry_scorecard(table, industry, financial)
        table["scorecard"] = sum(check.astype(float) for check in passed).where(profit.notna())
        if config.MODEL_SCORECARD == "off":
            table["scorecard"] = np.nan

        # ---- ownership ----
        owners = _latest(self.ownership, day, "quarter_end", 200).reindex(symbols)
        for name in GROUPS["ownership"]:
            table[name] = owners[name] if name in owners else np.nan
        # Pledge %: only from the day NSE published it (the history starts in Oct 2026).
        table["pledged_pct"] = np.nan
        if self.pledges is not None and len(self.pledges) > 0:
            known = self.pledges[(self.pledges["published"] <= day + pd.Timedelta(days=1))
                                 & (self.pledges["published"] >= day - pd.Timedelta(days=200))]
            if len(known):
                newest = known.sort_values("published").drop_duplicates("symbol", keep="last")
                table["pledged_pct"] = newest.set_index("symbol")["pledged_of_promoter_pct"] \
                    .reindex(symbols)

        # ---- news and deals: only for days the saved history covers ----
        table["news_score"] = np.nan
        if self.news is not None and len(self.news) > 0 \
                and self.news["time"].min() <= day + pd.Timedelta(days=1) \
                and self.news["time"].max() >= day - pd.Timedelta(days=7):
            window = (day - pd.Timedelta(days=config.MODEL_NEWS_DAYS), day + pd.Timedelta(days=1))
            if config.MODEL_NEWS_MODE == "lean" and self.news_read is not None:
                read = self.news_read[(self.news_read["time"] > window[0])
                                      & (self.news_read["time"] < window[1])]
                table["news_score"] = read.groupby("symbol")["lean"].sum().reindex(symbols) \
                    .fillna(0.0)
            recent = self.news[(self.news["time"] > window[0]) & (self.news["time"] < window[1])]
            points = recent["category"].map(NEWS_POINTS).fillna(0.0)
            text = (recent["subject"] + " " + recent["detail"]).str.lower()
            points = points + text.str.contains("upgrad").astype(float) \
                - text.str.contains("downgrad").astype(float) \
                - ((recent["category"] == "Management change")
                   & text.str.contains("resign")).astype(float) * 0.5
            if config.MODEL_NEWS_MODE != "lean" or self.news_read is None:
                table["news_score"] = points.groupby(recent["symbol"]).sum().reindex(symbols) \
                    .fillna(0.0)

        table["deal_score"] = np.nan
        if self.deals is not None and len(self.deals) > 0 \
                and self.deals["date"].min() <= day \
                and self.deals["date"].max() >= day - pd.Timedelta(days=7):
            recent = self.deals[(self.deals["date"] > day - pd.Timedelta(days=config.MODEL_NEWS_DAYS))
                                & (self.deals["date"] <= day)]
            value = recent["quantity"] * recent["price"] / 1e7
            signed = value.where(recent["side"] == "Buy", -value)
            table["deal_score"] = signed.groupby(recent["symbol"]).sum().reindex(symbols).fillna(0.0)

        # ---- events: results due in the next few days ----
        table["no_new_buy"] = False
        if self.results is not None:
            soon = self.results[(self.results["date"] > day)
                                & (self.results["date"] <= day + pd.Timedelta(
                                    days=config.RESULTS_BLOCK_DAYS))]
            table["no_new_buy"] = table.index.isin(set(soon["symbol"]))
        table["industry"] = industry
        return table

    def score_on(self, position):
        """All tradable stocks on that day, scored and sorted best first."""
        if position not in self._cache:
            self._cache[position] = combine(self.factors_on(position), self.weights_on(position))
        return self._cache[position]

    def weights_on(self, position):
        """The group weights for that day: measured ones when set, else config's."""
        if not self.measured_weights:
            return None
        known = [p for p in self.measured_weights if p <= position]
        return self.measured_weights[max(known)] if known else None

    # ---- using the score ----
    def simulate(self, start=None, end=None, capital=None, style=None, **entry):
        """Follow the model through the past (see rotation.simulate).

        style: "swing" or "monthly" (see MODEL_STYLES in config.py).
        entry: optional max_gap / limit_days to override how new stocks are bought
        (see rotation.simulate).
        """
        rules = {**config.MODEL_STYLES[style or config.MODEL_STYLE], **entry}
        if rules.get("caution_share") and rules.get("budget_scale") is None:
            share = np.where(self.strong_market().to_numpy(), 1.0, rules["caution_share"])
            rules["budget_scale"] = pd.DataFrame(
                np.repeat(share[:, None], len(self.prepared["symbols"]), axis=1),
                index=self.calendar, columns=self.prepared["symbols"])
        return rotation.simulate(
            self.trading, None, start, end, capital, scorer=self.score_on,
            check=rules["check"], positions_wanted=rules["positions"],
            keep_rank=_keep_rank(rules), stop_loss=rules["stop_loss"],
            trend_exit=rules.get("trend_exit", False), buy_rank=rules.get("buy_rank"),
            max_gap=rules.get("max_gap"), limit_days=rules.get("limit_days"),
            max_drop=rules.get("max_drop"), min_room=rules.get("min_room"),
            max_spike=rules.get("max_spike"), midweek_fill=rules.get("midweek_fill", False),
            budget_scale=rules.get("budget_scale"), exit_before=rules.get("exit_before"),
            industry=self.industry, max_per_industry=rules.get("max_per_industry"),
            profit_trail=rules.get("profit_trail"))

    def decision(self, held_symbols, style=None, buy_prices=None, buy_dates=None):
        """What the model says to do now, given the stocks you really hold.

        buy_prices: {symbol: the price you paid}. With it, a holding that has
        fallen past the style's stop-loss is put on the sell list.
        """
        rules = config.MODEL_STYLES[style or config.MODEL_STYLE]
        plan = rotation.decision(
            self.trading, None, held_symbols, scorer=self.score_on, check=rules["check"],
            positions_wanted=rules["positions"], keep_rank=_keep_rank(rules),
            buy_rank=rules.get("buy_rank"))
        plan["keep_rank"] = rules["keep_rank"] if rules.get("rank_exit", True) else None
        plan["stop_loss"] = rules["stop_loss"]
        plan["trend_exit"] = bool(rules.get("trend_exit"))
        plan["stopped"] = []
        plan["trend_broken"] = []
        plan["in_trend"] = self.trading["in_trend"].iloc[-1]
        # The week's picks come from the check day's close and stay fixed all week.
        decided = int(self.calendar.get_loc(plan["decided_on"]))
        plan["signal_scores"] = self.score_on(decided)
        plan["signal_in_trend"] = self.trading["in_trend"].iloc[decided]
        if rules.get("trend_exit") and plan["market_ok"]:
            in_trend = plan["in_trend"]
            plan["trend_broken"] = [s for s in plan["keep"] if not bool(in_trend.get(s, True))]
            plan["sell"] = plan["sell"] + plan["trend_broken"]
            plan["keep"] = [s for s in plan["keep"] if s not in plan["trend_broken"]]
            plan["candidates"] = [s for s in plan["candidates"] if bool(in_trend.get(s, False))]
            plan["room"] = max(0, rules["positions"] - len(plan["keep"]))
            plan["buy"] = plan["candidates"][:plan["room"]]
        if rules["stop_loss"] is not None and buy_prices:
            for symbol, paid in buy_prices.items():
                price = plan["last_price"].get(symbol)
                if price is not None and price <= paid * (1 - rules["stop_loss"]):
                    plan["stopped"].append(symbol)
            plan["sell"] = list(dict.fromkeys(plan["sell"] + plan["stopped"]))
            plan["keep"] = [s for s in plan["keep"] if s not in plan["stopped"]]
            plan["candidates"] = [s for s in plan["candidates"] if s not in plan["stopped"]]
        # Profit trail: once a holding has closed `trigger` above the buy price, sell after a
        # close `trail` below its highest close since the buy (backtest log, entry 10).
        plan["trailed"], plan["peaks"] = [], {}
        trail = rules.get("profit_trail")
        if trail and buy_prices and buy_dates:
            close = self.prepared["last_close"]
            for symbol, paid in buy_prices.items():
                if symbol not in close or symbol not in buy_dates:
                    continue
                since = close[symbol][close.index >= pd.Timestamp(buy_dates[symbol]).normalize()]
                peak = max([paid] + [float(v) for v in since.dropna()])
                plan["peaks"][symbol] = peak
                last = plan["last_price"].get(symbol)
                if trail.get("trail") and peak >= paid * (1 + trail["trigger"]) \
                        and last is not None and last <= peak * (1 - trail["trail"]):
                    plan["trailed"].append(symbol)
            plan["sell"] = list(dict.fromkeys(plan["sell"] + plan["trailed"]))
            plan["keep"] = [s for s in plan["keep"] if s not in plan["trailed"]]
        plan["cash_text"] = (f"Fewer than half of the market checks pass. The model buys "
                             "nothing until at least half do.")
        plan["sell_reason"] = "too few market checks pass"
        today = self.score_on(len(self.calendar) - 1)
        plan["today"] = today
        plan["weakest"] = today.tail(config.MODEL_WEAKEST).iloc[::-1]
        plan["checks"] = self.checks.iloc[-1]
        plan["market_score"] = float(self.market_score.iloc[-1])
        plan["market_level"], plan["market_note"] = self.market_level()
        return plan

    def strong_market(self):
        """True on days the market is strong: enough checks pass and Nifty is above its average."""
        return ((self.market_score >= config.MODEL_STRONG_MARKET)
                & self.prepared["market_ok"]).fillna(False)

    def amount_share(self, style=None):
        """The share of the normal amount a new buy gets today (1.0 in a strong market)."""
        rules = config.MODEL_STYLES[style or config.MODEL_STYLE]
        if bool(self.strong_market().iloc[-1]) or not rules.get("caution_share"):
            return 1.0
        return float(rules["caution_share"])

    def market_level(self):
        """How far to trust the market today: "strong", "caution" or "weak", with a sentence."""
        checks = self.checks.iloc[-1].dropna()
        passed, known = int(checks.sum()), len(checks)
        above_average = bool(self.prepared["market_ok"].iloc[-1])
        count = f"{passed} of {known} market checks pass"
        if not bool(self.market_ok.iloc[-1]):
            return "weak", f"Weak market: only {count}. The model holds cash."
        if above_average and self.market_score.iloc[-1] >= config.MODEL_STRONG_MARKET:
            return "strong", (f"Strong market: {count} and Nifty is above its "
                              f"{config.ROTATION_MARKET_SMA}-day average.")
        reason = ("" if above_average else
                  f" and Nifty is below its {config.ROTATION_MARKET_SMA}-day average")
        return "caution", (f"Caution: the model allows buying, but only {count}{reason}. "
                           "Consider smaller amounts or waiting.")


def _keep_rank(rules):
    """The rank a holding must stay inside, or no limit when the style has no rank exit."""
    return rules["keep_rank"] if rules.get("rank_exit", True) else 10 ** 9


def last_stock_day(stocks):
    """The latest day that has stock closing prices, or None."""
    days = [table.index.max() for table in stocks.values() if table is not None and len(table)]
    return max(days) if days else None


def up_to_last_close(nifty, stocks):
    """Nifty cut at the last day with stock closes.

    "Refresh before open" saves today's Nifty while the market is still open. The
    model's calendar comes from Nifty, so without this cut it would score a day
    that has no stock closes yet: every score empty, and the market checks read
    from an unfinished day.
    """
    last = last_stock_day(stocks)
    return nifty if last is None else nifty[nifty.index <= last]


def from_disk(stocks, nifty):
    """Build the model from the files that the update downloaded."""
    nifty = up_to_last_close(nifty, stocks)
    membership = data.load_membership()
    universe = data.load_universe()
    flow_table = flows.load_flows()
    fii_net = flows.daily_net(flow_table)["FII"] if len(flow_table) else None
    tables = {
        "annual": fundamentals.load_annual(),
        "quarterly": fundamentals.load_quarterly(),
        "dividends": fundamentals.load_dividends(),
        "results": fundamentals.load_results_dates(),
        "holdings": shareholding.load_shareholding(),
        "fund_holders": shareholding.load_fund_holders(),
        "industry": dict(zip(universe["Symbol"], universe["Industry"])),
        "news": news.load(),
        "deals": flows.load_deals(),
        "pledges": pledge.load(),
        "fii_net": fii_net,
    }
    markets = {}
    for name in ["INDIAVIX", "USDINR", "BRENT", "GOLD", *GLOBAL_MARKETS]:
        table = data.load_market(name)
        if table is not None and len(table):
            markets[name] = table["Close"]
    return Model(stocks, nifty,
                 lambda symbol, dates: data.membership_mask(symbol, dates, membership),
                 tables, markets)


def results_soon_table(results, calendar, symbols, days=None):
    """True on the days within `days` calendar days before each company's results."""
    days = config.RESULTS_BLOCK_DAYS if days is None else days
    table = pd.DataFrame(False, index=calendar, columns=list(symbols))
    if results is None or len(results) == 0:
        return table
    wanted = results[results["symbol"].isin(table.columns)]
    values = table.to_numpy().copy()
    where = {symbol: number for number, symbol in enumerate(table.columns)}
    for symbol, date in zip(wanted["symbol"], wanted["date"]):
        first = calendar.searchsorted(date - pd.Timedelta(days=days))
        last = calendar.searchsorted(date)          # up to the day before the results
        values[first:last, where[symbol]] = True
    return pd.DataFrame(values, index=calendar, columns=table.columns)
