"""Company data for the stock page and stock_card.py: the company card, industry PE
and the next results date, loaded once and reused."""

import config
from trading import company, data, fundamentals, shareholding


class Screens:
    """Loads the membership and fundamentals tables once and reuses them."""

    def __init__(self):
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
