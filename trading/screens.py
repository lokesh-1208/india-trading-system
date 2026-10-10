"""Builds the per-stock checks (index member, quality, results timing).

Both the backtest and the daily report use this, so they always apply
exactly the same rules.
"""

import pandas as pd

import config
from trading import company, data, fundamentals, shareholding, strategy


class Screens:
    """Loads the membership and fundamentals tables once and reuses them."""

    def __init__(self, use_quality=None, use_results_block=None):
        self.use_quality = config.USE_QUALITY_FILTER if use_quality is None else use_quality
        self.use_results_block = (
            config.USE_RESULTS_BLOCK if use_results_block is None else use_results_block
        )
        self.membership = data.load_membership()

        annual = fundamentals.load_annual()
        self.annual = None if annual is None else dict(tuple(annual.groupby("symbol")))

        results = fundamentals.load_results_dates()
        self.results = (
            None if results is None
            else {symbol: list(rows["date"]) for symbol, rows in results.groupby("symbol")}
        )

        quarterly = fundamentals.load_quarterly()
        self.quarterly = None if quarterly is None else dict(tuple(quarterly.groupby("symbol")))
        dividends = fundamentals.load_dividends()
        self.dividends = None if dividends is None else dict(tuple(dividends.groupby("symbol")))
        self.industry_pe = {}

        holdings = shareholding.load_shareholding()
        self.holdings = None if holdings is None else dict(tuple(holdings.groupby("symbol")))
        funds = shareholding.load_fund_holders()
        self.funds = None if funds is None else dict(tuple(funds.groupby("symbol")))

        universe = data.load_universe()
        self.industry = dict(zip(universe["Symbol"], universe["Industry"]))

    def is_financial(self, symbol):
        return self.industry.get(symbol, "") == config.FINANCIAL_INDUSTRY

    def company_rows(self, symbol):
        return None if self.annual is None else self.annual.get(symbol)

    def card(self, symbol, prices):
        """The company card for one stock (see company.py)."""
        card = company.build_card(
            symbol, prices, self.company_rows(symbol),
            None if self.quarterly is None else self.quarterly.get(symbol),
            None if self.dividends is None else self.dividends.get(symbol),
            self.industry.get(symbol, ""),
        )
        card["industry_pe"] = self.industry_pe.get(card["industry"])
        card["owners"] = shareholding.summary(
            None if self.holdings is None else self.holdings.get(symbol),
            None if self.funds is None else self.funds.get(symbol),
        )
        return card

    def learn_industry_pe(self, stocks):
        """Work out each industry's typical PE from all current index members."""
        cards = [self.card(symbol, prices) for symbol, prices in stocks.items()
                 if symbol in self.industry]
        self.industry_pe = company.industry_pe(cards)

    def next_results(self, symbol, after):
        """The next results date after a given day, or None."""
        if self.results is None:
            return None
        upcoming = [day for day in self.results.get(symbol, []) if day > after]
        return min(upcoming) if upcoming else None

    def add_indicators(self, symbol, prices, nifty_close):
        """Price table with indicators and the final signal for one stock."""
        dates = prices.index
        member = data.membership_mask(symbol, dates, self.membership)

        quality = None
        if self.use_quality and self.annual is not None:
            quality = fundamentals.quality_mask(
                self.company_rows(symbol), dates, self.is_financial(symbol)
            )

        near_results = None
        if self.use_results_block and self.results is not None:
            near_results = fundamentals.near_results_mask(
                self.results.get(symbol, []), dates
            )

        return strategy.add_indicators(prices, nifty_close, member, quality, near_results)

    def first_quality_date(self):
        """The day from which most companies' yearly results could be used."""
        if self.annual is None:
            return None
        first_years = pd.Series([rows["period_end"].min() for rows in self.annual.values()])
        typical = first_years.sort_values().iloc[len(first_years) // 2]
        return typical + pd.Timedelta(days=config.REPORTING_LAG_DAYS)
