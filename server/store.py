"""Everything the web app reads, loaded once and kept in memory.

Reading 800 price files and scoring every stock takes several seconds, so it
is done once and reused for every page. When the data on disk changes (an
update ran, by the app or by the scheduled task), the next request notices
and loads it again.
"""

import threading

import pandas as pd

import config
from trading import (data, flows, fundamentals, indicators, model, news, newsview, picks,
                     pledge, screens)

# Files whose change means the loaded data is out of date.
WATCHED = [
    lambda: config.MARKET_DIR / f"{config.BENCHMARK}.csv",
    lambda: config.PRICES_CACHE,
    lambda: config.ANNOUNCEMENTS_FILE,
    lambda: config.NSE_RESULTS_FILE,
    lambda: config.ANNUAL_FILE,
    lambda: config.SHAREHOLDING_FILE,
    lambda: config.PLEDGE_FILE,
    lambda: config.LARGE_DEALS_FILE,
    lambda: config.PREOPEN_FILE,
]


def _stamp():
    """A fingerprint of the watched files' modification times."""
    stamp = []
    for path in WATCHED:
        try:
            stamp.append(path().stat().st_mtime)
        except OSError:
            stamp.append(None)
    return tuple(stamp)


class Store:
    """Lazily built, shared, read-only data. Thread-safe."""

    def __init__(self):
        self._lock = threading.RLock()
        self._stamp = None
        self._items = {}

    def clear(self):
        with self._lock:
            self._items = {}
            self._stamp = None

    def _get(self, name, build):
        with self._lock:
            stamp = _stamp()
            if stamp != self._stamp:
                self._items = {}
                self._stamp = stamp
            if name not in self._items:
                self._items[name] = build()
            return self._items[name]

    # ---- the pieces ----
    def stocks(self):
        return self._get("stocks", data.load_all_stocks)

    def nifty(self):
        return self._get("nifty", lambda: data.load_market(config.BENCHMARK))

    def model(self):
        return self._get("model", lambda: model.from_disk(self.stocks(), self.nifty()))

    def ranking(self):
        """Today's scores, best first."""
        return self._get("ranking", lambda: self.model().score_on(len(self.model().calendar) - 1))

    def trend_line(self):
        def build():
            close = self.model().prepared["last_close"]
            return indicators.ema(close, config.EMA_FAST)
        return self._get("trend_line", build)

    def in_trend(self):
        return self._get("in_trend", lambda: self.model().trading["in_trend"].iloc[-1])

    def screens(self):
        def build():
            found = screens.Screens()
            found.learn_industry_pe(self.stocks())
            return found
        return self._get("screens", build)

    def news(self):
        return self._get("news", news.load)

    def deals(self):
        return self._get("deals", flows.load_deals)

    def flows(self):
        return self._get("flows", flows.load_flows)

    def quarterly(self):
        return self._get("quarterly", fundamentals.load_quarterly)

    def pledges(self):
        return self._get("pledges", pledge.latest)

    def news_reading(self):
        """(every announcement read as good or bad, what usually followed each kind)."""
        def build():
            table = newsview.read_all(self.news(), self.deals(), self.quarterly())
            reactions = newsview.past_reactions(table, self.model().prepared["last_close"],
                                                self.nifty()["Close"])
            return table, reactions
        return self._get("news_reading", build)

    def picks_log(self):
        # Makes and saves any missing daily list, so it runs once per data change.
        return self._get("picks_log", lambda: picks.update_log(self.model()))

    def history(self):
        """The model's backtest (a few seconds), for the Market page."""
        def build():
            from trading import rotation
            result = self.model().simulate(start=config.ROTATION_START, style=config.MODEL_STYLE)
            summary, by_year = rotation.summarise(result, self.nifty())
            return result, summary, by_year
        return self._get("history", build)

    def overnight(self, since):
        key = f"overnight-{pd.Timestamp(since):%Y%m%d%H%M}"

        def build():
            announcements = self.news()
            deals = self.deals()
            return newsview.read_all(announcements[announcements["time"] >= since],
                                     deals[deals["date"] >= pd.Timestamp(since).normalize()],
                                     self.quarterly(), read_pdfs=True)
        return self._get(key, build)


STORE = Store()
