"""Market movers: where the crowd's money went today, and why if we can tell.

This is NOT part of the model and gives no buy or sell signal. It shows the
stocks with unusually heavy buying or selling on the last trading day: a big
price move on volume well above the stock's normal. A big move on normal
volume is left out, because without the extra volume it is usually drift, not
a crowd rushing in or out.

For each mover the likely reason is looked up in what is already downloaded:
company announcements filed with NSE, results, and bulk or block deals. When
nothing is found the move is labelled a crowd move: sentiment, rumour, sector
news or a wider market swing.
"""

import pandas as pd

import config

NO_REASON = "No company news found: crowd move (sentiment, sector or market)"


def day_moves(stocks, symbols, day=None):
    """One row per stock for one trading day: change, gap and volume against normal.

    stocks: {symbol: price table}. day: the trading day, by default the latest
    day in the data. Only stocks that traded on that day and the day before are
    included.
    """
    rows = []
    for symbol in symbols:
        table = stocks.get(symbol)
        if table is None or len(table) < config.MOVERS_VOLUME_DAYS + 2:
            continue
        last = table.index[-1] if day is None else pd.Timestamp(day)
        if last not in table.index:
            continue
        position = table.index.get_loc(last)
        if position < config.MOVERS_VOLUME_DAYS + 1:
            continue
        today, before = table.iloc[position], table.iloc[position - 1]
        normal = table["Volume"].iloc[position - config.MOVERS_VOLUME_DAYS:position].mean()
        if before["Close"] <= 0:
            continue
        rows.append({
            "symbol": symbol, "day": last,
            "close": float(today["Close"]),
            "change_%": (today["Close"] / before["Close"] - 1) * 100,
            "gap_%": (today["Open"] / before["Close"] - 1) * 100,
            "volume_x": float(today["Volume"] / normal) if normal > 0 else float("nan"),
            "turnover_cr": float(today["Close"] * today["Volume"] / 1e7),
        })
    return pd.DataFrame(rows, columns=["symbol", "day", "close", "change_%", "gap_%",
                                       "volume_x", "turnover_cr"])


def heavy(moves, side, top=None):
    """The biggest moves up (side="up") or down (side="down") on heavy volume."""
    top = config.MOVERS_PER_SIDE if top is None else top
    move = config.MOVERS_MIN_MOVE_PCT
    busy = moves[moves["volume_x"] >= config.MOVERS_MIN_VOLUME_X]
    if side == "up":
        return busy[busy["change_%"] >= move].sort_values("change_%", ascending=False).head(top)
    return busy[busy["change_%"] <= -move].sort_values("change_%").head(top)


def reasons(symbol, day, previous_day, announcements=None, deals=None, results=None):
    """What might explain a stock's move on `day`, newest first.

    Announcements count from the previous trading day's close (3:30 pm) to the
    end of `day`, because news filed after the close moves the next day.
    Returns (list of short texts, link to the most relevant filing or "").
    """
    found, link = [], ""
    if results is not None and len(results):
        dates = results.loc[results["symbol"] == symbol, "date"]
        if ((dates >= previous_day) & (dates <= day)).any():
            found.append("Results announced")
    if announcements is not None and len(announcements):
        start = previous_day + pd.Timedelta(hours=15, minutes=30)
        end = day + pd.Timedelta(days=1)
        filed = announcements[(announcements["symbol"] == symbol)
                              & (announcements["time"] >= start)
                              & (announcements["time"] < end)
                              & (announcements["category"] != "Routine")]
        for row in filed.sort_values("time", ascending=False).itertuples():
            text = row.detail if isinstance(row.detail, str) and row.detail else row.subject
            text = str(text).strip()
            if len(text) > 160:
                text = text[:157].rstrip() + "..."
            if f"{row.category}: {text}" not in found:      # NSE often files twice
                found.append(f"{row.category}: {text}")
            if not link and isinstance(row.link, str):
                link = row.link
    if deals is not None and len(deals):
        done = deals[(deals["symbol"] == symbol) & (deals["date"] == day)]
        for row in done.itertuples():
            value = row.quantity * row.price / 1e7
            found.append(f"{row.kind} deal: {row.client} {row.side.lower()} "
                         f"Rs {value:,.0f} cr")
    return found, link


def explain(table, previous_day, announcements=None, deals=None, results=None,
            industry=None):
    """Add the 'why' and 'link' columns to a table of movers.

    industry: {symbol: industry}. When several movers on the same side share an
    industry (config.MOVERS_SECTOR_MIN or more), a mover without company news is
    marked as part of that sector's move instead of a plain crowd move.
    """
    table = table.copy()
    industry = industry or {}
    sectors = pd.Series([industry.get(symbol, "") for symbol in table["symbol"]],
                        dtype="object")
    counts = sectors[sectors != ""].value_counts()
    whys, links = [], []
    for row, sector in zip(table.itertuples(), sectors):
        found, link = reasons(row.symbol, row.day, previous_day, announcements, deals, results)
        if found:
            why = " | ".join(found[:3])
        elif sector and counts.get(sector, 0) >= config.MOVERS_SECTOR_MIN:
            why = (f"Sector move: no company news, {counts[sector]} {sector} stocks "
                   "moved together")
        else:
            why = NO_REASON
        whys.append(why)
        links.append(link)
    table["why"] = whys
    table["link"] = links
    return table


def mood(moves, vix=None, nifty=None):
    """A one-line reading of the day's crowd behaviour across all stocks.

    Counts stocks that rose or fell sharply (at least config.MOVERS_MIN_MOVE_PCT)
    on heavy volume, and adds the change in Nifty and India VIX.
    """
    move = config.MOVERS_MIN_MOVE_PCT
    busy = moves[moves["volume_x"] >= config.MOVERS_MIN_VOLUME_X]
    rushing_in = int((busy["change_%"] >= move).sum())
    rushing_out = int((busy["change_%"] <= -move).sum())
    rising = int((moves["change_%"] > 0).sum())
    falling = int((moves["change_%"] < 0).sum())

    def day_change(table):
        if table is None or len(table) < 2:
            return None
        return float((table["Close"].iloc[-1] / table["Close"].iloc[-2] - 1) * 100)

    vix_change, nifty_change = day_change(vix), day_change(nifty)
    if rushing_out >= 2 * max(rushing_in, 1) and (vix_change is None or vix_change > 0):
        label = "Fear"
    elif rushing_in >= 2 * max(rushing_out, 1):
        label = "Excitement"
    elif rushing_out > rushing_in:
        label = "Nervous"
    elif rushing_in > rushing_out:
        label = "Upbeat"
    else:
        label = "Calm"
    parts = [f"{rushing_in} stocks with heavy buying, {rushing_out} with heavy selling",
             f"{rising} rose and {falling} fell"]
    if nifty_change is not None:
        parts.append(f"Nifty {nifty_change:+.1f}%")
    if vix_change is not None:
        parts.append(f"India VIX {vix_change:+.1f}%")
    return {"label": label, "text": ". ".join(parts) + ".",
            "rushing_in": rushing_in, "rushing_out": rushing_out}
