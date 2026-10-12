"""The dashboard: everything the system knows, as charts in your browser.

Run:  streamlit run dashboard.py
It reads the files that update_data.py downloaded, so run that first.
"""

from html import escape

import pandas as pd
import streamlit as st

import config
from trading import (charts, company, data, flows, indicators, journal, model, news, report,
                     rotation, today, ui, update)
from trading.screens import Screens

st.set_page_config(page_title="Kasauti", layout="wide")
MODE = ui.current_mode()        # light or dark, chosen in the browser's Settings menu
ui.apply(MODE)
charts.set_mode(MODE)

PERIODS = {"6 months": 126, "1 year": 252, "3 years": 756, "All": None}


# ------------------------------------------------------------ loading -------
# Streamlit re-runs this file on every click. The cache keeps the slow steps
# (reading 800 files, working out the shortlist) from being repeated. The
# data is only read, never changed, so one shared copy is kept in memory.
@st.cache_resource(show_spinner="Reading price files ...")
def load_stocks():
    return data.load_all_stocks()


@st.cache_resource
def load_nifty():
    return data.load_market(config.BENCHMARK)


@st.cache_resource(show_spinner="Reading company data ...")
def load_screens():
    screens = Screens()
    screens.learn_industry_pe(load_stocks())
    return screens


@st.cache_resource(show_spinner="Scoring every stock on every factor ...")
def load_model():
    """The full model: every factor table, ready to score any day."""
    return model.from_disk(load_stocks(), load_nifty())


@st.cache_resource(show_spinner="Running the model through the past ...")
def model_history(style):
    return load_model().simulate(start=config.ROTATION_START, style=style)


@st.cache_resource(show_spinner=False)
def load_news():
    return news.load()


@st.cache_resource(show_spinner=False)
def load_flows():
    return flows.load_flows(), flows.load_deals()


def show_news(rows, with_symbol=False):
    """A table of announcements with a link to each filing."""
    table = pd.DataFrame({
        "Date": rows["time"].dt.strftime("%d %b %Y"),
        **({"Stock": rows["symbol"]} if with_symbol else {}),
        "Type": rows["category"],
        "What it says": [detail or subject
                         for detail, subject in zip(rows["detail"], rows["subject"])],
        "Filing": rows["link"],
    })
    st.dataframe(table, hide_index=True, use_container_width=True,
                 column_config={"Filing": st.column_config.LinkColumn("Filing", display_text="open"),
                                "What it says": st.column_config.TextColumn(width="large")})


def money_flow_section():
    """Market page: what institutions bought and sold, and the large deals."""
    flow_table, deals = load_flows()
    net = flows.daily_net(flow_table)
    if len(net) == 0:
        st.info("No FII/DII figures yet. Press 'Update data now' in the sidebar.")
        return
    day = net.index[-1]
    fii, dii = net["FII"].iloc[-1], net["DII"].iloc[-1]
    one, two, three = st.columns(3)
    one.metric(f"Foreign institutions, {day:%d %b}", f"Rs {fii:+,.0f} cr",
               "bought more than they sold" if fii > 0 else "sold more than they bought",
               delta_color="off")
    two.metric(f"Indian institutions, {day:%d %b}", f"Rs {dii:+,.0f} cr",
               "bought more than they sold" if dii > 0 else "sold more than they bought",
               delta_color="off")
    three.metric("Days of history saved", len(net))
    if len(net) >= 2:
        show(charts.flows_bars(net))
    st.caption("NSE gives only the latest day, so this history grows by one day each time "
               "you update. A day without an update is missed.")

    recent = flows.deals_for(deals, set(load_stocks()), days=10)
    st.markdown("**Bulk and block deals in Nifty 500 stocks, last 10 days**")
    if len(recent) == 0:
        st.write("None recorded.")
    else:
        st.dataframe(pd.DataFrame({
            "Date": recent["date"].dt.strftime("%d %b"),
            "Stock": recent["symbol"],
            "Deal": recent["kind"],
            "Who": recent["client"],
            "Side": recent["side"],
            "Shares": recent["quantity"].map("{:,.0f}".format),
            "Price": recent["price"].round(2),
            "Value (Rs cr)": recent["value_crore"].round(1),
        }), hide_index=True, use_container_width=True)


def show(figure):
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def pct(value, signed=True):
    if value is None or pd.isna(value):
        return "-"
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def num(value, digits=1):
    return "-" if value is None or pd.isna(value) else f"{value:,.{digits}f}"


def market_is_open_for_trades(nifty):
    trend = indicators.ema(nifty["Close"], config.MARKET_EMA)
    return bool(nifty["Close"].iloc[-1] > trend.iloc[-1]), trend


# -------------------------------------------------------------- pages -------
def market_strip():
    """The line of index levels at the top of a page."""
    nifty = load_nifty()
    items = []
    for label, name in [("Nifty 50", config.BENCHMARK), ("India VIX", "INDIAVIX"),
                        ("USD/INR", "USDINR"), ("Brent", "BRENT"), ("Gold", "GOLD"),
                        ("S&P 500", "SP500")]:
        table = nifty if name == config.BENCHMARK else data.load_market(name)
        if table is not None and len(table) > 1:
            last, before = table["Close"].iloc[-1], table["Close"].iloc[-2]
            items.append((label, float(last), float((last / before - 1) * 100)))
    ui.market_strip(items)


def market_page():
    nifty = load_nifty()
    built = load_model()
    dashboard = report.market_dashboard()
    checks = built.checks.iloc[-1]
    known = checks.dropna()
    level, note = built.market_level()

    market_strip()
    headline = {"strong": "The market is strong", "caution": "Go carefully",
                "weak": "Stay out of new buys"}[level]
    detail = note.split(": ", 1)[-1]
    ui.day_plan(headline, detail[:1].upper() + detail[1:], level, note)

    with st.expander(f"Market checks: {int(known.sum())} of {len(known)} pass", expanded=True):
        ui.section_note(f"The model makes new buys only when at least "
                        f"{config.MODEL_MARKET_MIN:.0%} of the known checks pass.")
        ui.checks([(name, {1.0: True, 0.0: False}.get(passed)) for name, passed in checks.items()])
        st.caption("– means not enough history is saved yet.")

    average = nifty["Close"].rolling(config.ROTATION_MARKET_SMA).mean()
    gap = nifty["Close"].iloc[-1] / average.iloc[-1] - 1
    with st.expander(f"Nifty 50: {gap:+.1%} from its {config.ROTATION_MARKET_SMA}-day average",
                     expanded=True):
        period = st.radio("Period", list(PERIODS), index=1, horizontal=True, key="market_period",
                          label_visibility="collapsed")
        days = PERIODS[period]
        show(charts.trend_chart(
            charts.last_days(nifty["Close"], days), charts.last_days(average, days),
            "Nifty 50", f"{config.ROTATION_MARKET_SMA}-day average",
            f"Nifty 50 and its {config.ROTATION_MARKET_SMA}-day average"))

    rising = int((dashboard["change_%"] > 0).sum())
    with st.expander(f"World markets, rupee, crude and gold: {rising} of {len(dashboard)} rose"):
        left, right = st.columns([3, 2])
        with left:
            show(charts.change_bars(dashboard))
        with right:
            st.dataframe(dashboard.rename(columns={"market": "Market", "date": "Date",
                                                   "close": "Close", "change_%": "Change %"}),
                         hide_index=True, use_container_width=True)

    flow_table, _ = load_flows()
    net = flows.daily_net(flow_table)
    if len(net):
        fii = net["FII"].iloc[-1]
        title = (f"Who is buying and selling: foreign institutions "
                 f"{'bought' if fii > 0 else 'sold'} Rs {abs(fii):,.0f} cr on {net.index[-1]:%d %b}")
    else:
        title = "Who is buying and selling"
    with st.expander(title):
        money_flow_section()


def company_page():
    stocks, nifty, screens = load_stocks(), load_nifty(), load_screens()
    built = load_model()
    symbols = sorted(stocks)
    wanted = st.session_state.get("symbol", "RELIANCE")
    start = symbols.index(wanted) if wanted in symbols else 0

    market_strip()
    symbol = st.selectbox("Stock", symbols, index=start, placeholder="Type to search",
                          help="Type part of the NSE symbol, for example HDFC.")
    st.session_state["symbol"] = symbol

    prices = stocks[symbol]
    card = screens.card(symbol, prices)
    financial = screens.is_financial(symbol)
    table = screens.add_indicators(symbol, prices, nifty["Close"])
    next_results = screens.next_results(symbol, prices.index[-1])

    # ---- header: name, price, the model's view ----
    ranking = built.score_on(len(nifty.index) - 1)
    in_trend = bool(built.trading["in_trend"].iloc[-1].get(symbol, False))
    rank = list(ranking.index).index(symbol) + 1 if symbol in ranking.index else None
    view = (today.model_view(float(ranking.loc[symbol, "score"]), in_trend) if rank
            else "not scored")
    last, before = prices["Close"].iloc[-1], prices["Close"].iloc[-2]
    facts = [card["industry"] or "Industry not known",
             f"prices up to {prices.index[-1]:%d %b %Y}",
             "next results " + (f"{next_results:%a %d %b}" if next_results is not None
                                else "not known")]
    ui.company_header(symbol, ", ".join(facts), float(last), float((last / before - 1) * 100),
                      view, rank, len(ranking))

    tiles = st.columns(6)
    cap = card["market_cap_crore"]
    cap_text = ("-" if cap is None or pd.isna(cap) else
                f"Rs {cap / 1e5:,.1f} lakh cr" if cap >= 1e5 else f"Rs {cap:,.0f} cr")
    tiles[0].metric("From year high", pct(card["below_52w_high"]))
    tiles[1].metric("Market value", cap_text)
    tiles[2].metric("PE", num(card["pe"]), f"industry {num(card['industry_pe'])}",
                    delta_color="off")
    tiles[3].metric("Return on equity", pct(card["return_on_equity"], signed=False))
    tiles[4].metric("Debt to equity", num(card["debt_to_equity"], 2))
    tiles[5].metric("Scorecard", f"{company.score(card, financial)} of 10")

    # ---- the model's view ----
    title = (f"Model view: rank {rank} of {len(ranking)}, score {ranking.loc[symbol, 'score']:.0f}"
             if rank else "Model view: not scored")
    with st.expander(title, expanded=True):
        if not rank:
            ui.empty("The model does not score this stock today: it is not a current Nifty 500 "
                     "member, or it trades too little.")
        else:
            row = ranking.loc[symbol]
            left, right = st.columns([1, 3])
            with left:
                ui.big_score(row["score"], "of 100")
            with right:
                ui.score_bars([(group.capitalize(), row[group]) for group in model.GROUPS])
            rules = config.MODEL_STYLES[config.MODEL_STYLE]
            soon = next_results is not None and next_results <= (
                today.buy_day(pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None))
                + pd.Timedelta(days=config.RESULTS_BLOCK_DAYS))
            ui.checks([
                (f"In the top {rules['buy_rank']} scores (rank {rank})", rank <= rules["buy_rank"]),
                (f"Above its {config.EMA_FAST}-day EMA", in_trend),
                ("No results due in the next 5 days", not soon),
            ])
            st.caption("The model buys a stock only when all three are true, and the market "
                       "checks allow buying.")

    # ---- price ----
    with st.expander("Price chart", expanded=True):
        period = st.radio("Period", list(PERIODS), index=1, horizontal=True,
                          key="company_period", label_visibility="collapsed")
        recent = charts.last_days(table, PERIODS[period])
        show(charts.price_chart(recent, f"{symbol}: closing price and trend lines"))
        left, right = st.columns(2)
        with left:
            show(charts.volume_chart(recent))
        with right:
            show(charts.rsi_chart(recent))

    # ---- business ----
    annual, quarterly = screens.company_rows(symbol), None
    if screens.quarterly is not None:
        quarterly = screens.quarterly.get(symbol)
    with st.expander(f"Business: sales {pct(card['sales_growth_1y'])}, profit "
                     f"{pct(card['profit_growth_1y'])} in the last year"):
        if annual is None:
            ui.empty("No company results downloaded for this stock.")
        else:
            left, right = st.columns(2)
            with left:
                show(charts.results_bars(annual, "Sales and profit by year"))
            with right:
                if quarterly is not None and len(quarterly):
                    show(charts.results_bars(quarterly, "Sales and profit by quarter"))
            growth = pd.DataFrame({
                "": ["Sales", "Profit"],
                "1 year": [pct(card["sales_growth_1y"]), pct(card["profit_growth_1y"])],
                "3 years, per year": [pct(card["sales_growth_3y"]), pct(card["profit_growth_3y"])],
                "Latest quarter against a year ago": [pct(card["quarter_sales_growth"]),
                                                      pct(card["quarter_profit_growth"])],
            })
            left, right = st.columns(2)
            left.markdown("**Growth**")
            left.dataframe(growth, hide_index=True, use_container_width=True)
            valuation = pd.DataFrame({
                "Measure": ["PE", "Industry PE", "Earnings per share", "Price to book",
                            "Book value a share", "Dividend yield", "Profit margin"],
                "Value": [num(card["pe"]), num(card["industry_pe"]), num(card["eps"], 2),
                          num(card["price_to_book"], 2), num(card["book_value"], 2),
                          pct(card["dividend_yield"], signed=False),
                          pct(card["net_margin"], signed=False)],
            })
            right.markdown(f"**Valuation** (profit of the {card['earnings_basis'] or '-'})")
            right.dataframe(valuation, hide_index=True, use_container_width=True)

    # ---- owners ----
    holdings = None if screens.holdings is None else screens.holdings.get(symbol)
    owners = card["owners"]
    if owners is not None:
        fii_change = owners.get("fii_change")
        mf_change = owners.get("mutual_funds_change")
        title = (f"Who owns it: FII {num(fii_change, 2)}, mutual funds {num(mf_change, 2)} "
                 "points last quarter")
    else:
        title = "Who owns it"
    with st.expander(title):
        if holdings is None or owners is None:
            ui.empty("No shareholding data downloaded for this stock.")
        else:
            left, right = st.columns([3, 2])
            with left:
                show(charts.ownership_bars(holdings))
                labels = [("promoter", "Promoters"), ("fii", "Foreign institutions"),
                          ("dii", "Indian institutions"), ("mutual_funds", "of which mutual funds"),
                          ("insurance", "of which insurers"), ("public", "Public and others")]
                st.dataframe(pd.DataFrame({
                    "Holder": [label for _, label in labels],
                    "Holding %": [owners[key] for key, _ in labels],
                    "Change from the quarter before": [owners[key + "_change"] for key, _ in labels],
                }), hide_index=True, use_container_width=True)
            with right:
                pledged = {True: "Yes", False: "No", None: "Not stated"}[owners["promoters_pledged"]]
                st.metric("Promoter shares pledged", pledged)
                st.markdown("**Mutual fund schemes holding over 1%**")
                if owners["funds"]:
                    st.dataframe(pd.DataFrame(owners["funds"], columns=["Scheme", "Holding %"]),
                                 hide_index=True, use_container_width=True)
                else:
                    st.write("No single scheme holds over 1%.")

    # ---- news ----
    announcements = load_news()
    important = (news.for_symbol(announcements, symbol, days=90, important_only=True)
                 if len(announcements) else announcements)
    _, deals = load_flows()
    stock_deals = flows.deals_for(deals, [symbol], days=90)
    def count(number, word):
        return f"{number} {word}{'' if number == 1 else 's'}"
    with st.expander(f"News and deals: {count(len(important), 'announcement')}, "
                     f"{count(len(stock_deals), 'deal')} in 90 days"):
        if len(announcements) == 0:
            ui.empty("No announcements yet. Press 'Update data now' in the left panel.")
        else:
            everything = st.toggle("Also show routine paperwork", key="news_all")
            rows = news.for_symbol(announcements, symbol, days=90, important_only=not everything)
            if len(rows) == 0:
                st.write("Nothing important in the last 90 days "
                         f"(announcements saved from {announcements['time'].min():%d %b %Y}).")
            else:
                show_news(rows)
        if len(stock_deals):
            st.markdown("**Bulk and block deals in this stock**")
            st.dataframe(stock_deals[["date", "kind", "client", "side", "quantity", "price",
                                      "value_crore"]].round(2),
                         hide_index=True, use_container_width=True)

    # ---- scorecard ----
    with st.expander(f"Scorecard: {company.score(card, financial)} of 10"):
        ui.checks(company.scorecard(card, financial))
        st.caption("– means the figure is not available. The thresholds are rules of "
                   "thumb and have not been proven by a backtest.")


def _my_trades(trades, prices, symbols):
    """Your real positions, with forms to record a buy and a sell."""
    totals = journal.totals(trades, prices)
    one, two, three, four = st.columns(4)
    one.metric("Money in the market", f"Rs {totals['invested']:,.0f}")
    two.metric("Worth now", f"Rs {totals['value']:,.0f}")
    three.metric("Gain on open positions", f"Rs {totals['open_gain']:+,.0f}")
    four.metric("Profit on closed trades", f"Rs {totals['closed_profit']:+,.0f}")

    positions = journal.open_positions(trades, prices)
    if len(positions):
        shown = positions[["symbol", "buy_date", "buy_price", "quantity", "cost",
                           "last_price", "value", "gain", "gain_%", "note"]].round(2)
        st.dataframe(shown, hide_index=True, use_container_width=True)
    else:
        st.write("No open positions recorded.")

    left, right = st.columns(2)
    with left, st.form("record_buy", clear_on_submit=True):
        st.markdown("**Record a buy**")
        symbol = st.selectbox("Stock", symbols)
        day = st.date_input("Date bought")
        price = st.number_input("Price paid per share (Rs)", min_value=0.0, step=0.05)
        quantity = st.number_input("Number of shares", min_value=0, step=1)
        note = st.text_input("Note (why you bought it)")
        if st.form_submit_button("Save buy"):
            try:
                journal.save(journal.record_buy(trades, symbol, day, price, quantity, note))
                st.rerun()
            except ValueError as problem:
                st.error(str(problem))
    with right, st.form("record_sell", clear_on_submit=True):
        st.markdown("**Record a sell**")
        labels = {f"{row.symbol}: {int(row.quantity)} shares bought {row.buy_date}": number
                  for number, row in positions.iterrows()}
        choice = st.selectbox("Position", list(labels) or ["No open positions"])
        day = st.date_input("Date sold")
        price = st.number_input("Price received per share (Rs)", min_value=0.0, step=0.05)
        if st.form_submit_button("Save sell") and labels:
            try:
                journal.save(journal.record_sell(trades, labels[choice], day, price))
                st.rerun()
            except ValueError as problem:
                st.error(str(problem))

    closed = journal.closed_trades(trades)
    if len(closed):
        with st.expander(f"Closed trades ({len(closed)})"):
            st.dataframe(closed.round(2), hide_index=True, use_container_width=True)
    st.caption("Saved in journal/real_trades.csv on this computer only. Keep your own "
               "backup. Profit figures are before charges and tax.")


GROUP_NOTES = {
    "ownership": "FII, mutual fund, promoter, DII, insurer and public holding changes; "
                 "pledged shares; number of fund schemes above 1%",
    "business": "sales and profit growth (1 and 3 years), margin, return on equity, debt, "
                "latest quarter against a year ago, the ten-point scorecard",
    "valuation": "PE against its industry, price to book, earnings per share against "
                 "price, dividend yield",
    "price": "6-month strength, EMA trend, RSI, volume, ATR, distance from the 52-week high",
    "news": "company announcements in the last 30 days (orders, rating changes, legal "
            "matters, resignations)",
    "flows": "bulk and block deals in the stock in the last 30 days",
}


SCORE_COLUMNS = {
    name: st.column_config.ProgressColumn(name, min_value=0, max_value=100, format="%d")
    for name in ["score", *model.GROUPS]
}


def _score_table(table):
    """Scores as a table: total, then each group, then a few plain figures."""
    return pd.DataFrame({
        "rank": table["rank"],
        "symbol": table.index,
        "score": table["score"].round(0),
        **{group: table[group].round(0) for group in model.GROUPS},
        "price": table["close"].round(2),
        "PE": table["pe"].round(1),
        "6-month change %": (table["momentum"] * 100).round(1),
        "FII change": table["fii_change"].round(2),
        "MF change": table["mf_change"].round(2),
        "results due": table["no_new_buy"].map({True: "yes", False: ""}),
    })


def today_page():
    """The one page to act from: what to buy, what to do with what you hold, what to avoid."""
    style = config.MODEL_STYLE
    rules = config.MODEL_STYLES[style]
    built = load_model()
    nifty = load_nifty()
    trades = journal.load()
    open_rows = journal.open_positions(trades)
    held = list(open_rows["symbol"].unique())
    paid = dict(open_rows.groupby("symbol")["buy_price"].mean()) if len(open_rows) else {}
    plan = built.decision(held, style=style, buy_prices=paid)
    prices = plan["last_price"]
    last_day = prices.name
    above = rules.get("max_gap") or 0.0

    close = built.prepared["last_close"]
    trend = indicators.ema(close, config.EMA_FAST)

    def chart(symbol):
        if symbol not in close:
            return ""
        return ui.sparkline(close[symbol].iloc[-90:].tolist(), trend[symbol].iloc[-90:].tolist())

    def about(symbol, rank=None, score=None):
        parts = [built.industry.get(symbol, "")]
        if rank is not None:
            parts.insert(0, f"Rank {rank}, score {score:.0f}")
        return ", ".join(part for part in parts if part)

    # ---- market strip and the day's headline ----
    market_strip()

    now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
    due = today.results_soon(built.results, today.buy_day(now))
    positions = journal.open_positions(trades, prices)
    trend_lines = {symbol: float(trend[symbol].iloc[-1]) for symbol in held if symbol in trend}
    mine = today.my_stocks(plan, positions, trend_lines)
    sells = mine[mine["action"] == "SELL"]
    money = st.session_state.get("_money", int(config.CAPITAL))
    buys = today.buy_list(plan, money, results_due=due)
    picks = buys[buys["type"] == "Pick"]
    backups = buys[buys["type"] == "Backup"]

    to_buy = len(picks) if plan["market_ok"] else 0
    to_sell = len(sells)
    if to_buy and to_sell:
        headline = f"Buy {to_buy}, sell {to_sell}"
    elif to_buy:
        headline = f"Buy {to_buy} stock{'s' if to_buy != 1 else ''}, nothing to sell"
    elif to_sell:
        headline = f"Sell {to_sell}, nothing new to buy"
    else:
        headline = "Nothing to do today"
    note = (f"From the {last_day:%a %d %b} close. The model checks for new buys at the start "
            "of each week and checks exits every day.")
    ui.day_plan(headline, note, plan["market_level"], plan["market_note"])
    if plan["market_level"] != "strong":
        st.caption(plan["market_note"])

    show_what = st.session_state.get("_show", "Buy and sell")

    def buy_rows(table, colour):
        return [{
            "symbol": row.symbol, "colour": colour,
            "tag": None, "note": about(row.symbol, row.rank, row.score),
            "chart": chart(row.symbol),
            "middle": ui.ladder(row.entry * (1 - rules["stop_loss"]), row.entry, row.buy_up_to),
            "right_top": f"{row.shares} shares",
            "right_bottom": f"about Rs {row.amount:,.0f}",
        } for row in table.itertuples()]

    # ---- to buy ----
    if show_what != "Sell only":
        count = f"{len(picks)} stock{'s' if len(picks) != 1 else ''}" if plan["market_ok"] \
            else "no new buys"
        with st.expander(f"To buy: {count}", expanded=True):
            if not plan["market_ok"]:
                ui.empty(plan["cash_text"])
            elif len(picks):
                ui.section_note(f"Buy at or below the limit. Stop-loss is "
                                f"{rules['stop_loss']:.0%} under the price you pay. If a pick "
                                "is already above its limit, take the first backup instead.")
                ui.stock_rows(buy_rows(picks, ui.BLUE))
            else:
                ui.empty("Nothing new to buy: your holdings fill all the places.")
            notes = []
            if plan["market_ok"] and not plan["due_next_session"]:
                notes.append(f"These picks are from the weekly check on "
                             f"{plan['decided_on']:%d %b}. Mid-week, buy only if the price is "
                             "still inside the range.")
            left_out = [f"{symbol} ({date:%a %d %b})" for symbol, date in sorted(due.items())
                        if symbol in set(plan["today"].index[:20])]
            if left_out:
                notes.append("Left out because results are due within "
                             f"{config.RESULTS_BLOCK_DAYS} days: " + ", ".join(left_out) + ".")
            notes.append(f"The bar shows the stop-loss, the signal close (dot) and the buy "
                         f"limit, {above:.0%} above it. There is no lower limit: in the tests, "
                         "stocks bought below the signal close did best. The chart is the last "
                         f"4 months, with the {config.EMA_FAST}-day EMA dotted.")
            st.caption(" ".join(notes))

        if len(backups):
            with st.expander(f"Backups: {len(backups)} stocks"):
                ui.section_note("Use them in order when a pick is already above its limit.")
                ui.stock_rows(buy_rows(backups, ui.NEUTRAL))

    # ---- your stocks ----
    if show_what != "Buy only":
        if len(mine) == 0:
            title = "Your stocks: none recorded"
        elif len(sells):
            title = f"Your stocks: {len(mine)}, sell {len(sells)}"
        else:
            title = f"Your stocks: {len(mine)}, all hold"
        with st.expander(title, expanded=len(mine) > 0):
            if len(mine) == 0:
                ui.empty("After you buy, add it under 'Record a trade' and it shows here, "
                         "marked Hold or Sell each day.")
            else:
                ui.stock_rows([{
                    "symbol": row["symbol"], "tag": row["action"].capitalize(),
                    "colour": ui.SELL if row["action"] == "SELL" else ui.GOOD,
                    "note": f"{row['quantity']} shares bought at Rs {row['buy_price']:,.2f}",
                    "chart": chart(row["symbol"]),
                    "middle": ("<span style='font-size:0.86rem'>"
                               + escape(row["reason"].capitalize()) + "</span>"),
                    "right_top": f"Rs {row['last_price']:,.2f}  {row['gain_%']:+.1f}%",
                    "right_bottom": "Sell on a close below Rs "
                                    f"{max(row['stop_loss'], row['trend_line']):,.2f}",
                } for row in mine.to_dict("records")])
                st.caption(f"Sell at the next open after a close below the {config.EMA_FAST}-day "
                           f"EMA or {rules['stop_loss']:.0%} below your buy price, whichever "
                           "comes first.")

        avoid = today.avoid_list(plan)
        with st.expander(f"Avoid: {len(avoid)} weakest scores"):
            ui.section_note("Do not buy these. If you hold one, the model would rather you "
                            "were out.")
            ui.chips([(row.symbol, f"score {row.score:.0f}") for row in avoid.itertuples()])

    # ---- events ----
    ranking = plan["today"]
    in_trend = plan.get("in_trend", {})
    soon = today.upcoming_results(built.results, ranking, in_trend, set(held),
                                  today.buy_day(now))
    out = today.recent_results(built.results, ranking, in_trend, close, last_day)
    fresh_news = today.recent_news(load_news(), ranking, in_trend, close, last_day)
    entries = today.event_cards(soon, out, fresh_news, set(held))
    worth = [entry for entry in entries if entry["worth"]]
    with st.expander(f"Events: {len(worth)} worth a look"):
        ui.section_note("Results due, results just out, and company news. Ideas only: trading "
                        "on news has not been tested, so there is no buy or sell here.")
        choice = st.radio("Which stocks", [f"Worth a look ({len(worth)})",
                                           f"All ({len(entries)})"],
                          horizontal=True, key="events_filter", label_visibility="collapsed")
        shown = worth if choice.startswith("Worth") else entries
        if not shown:
            ui.empty("No results due, results just out, or important company news for these "
                     "stocks.")
        else:
            ui.event_cards(shown)
        st.caption("📅 results due in the next 7 days. 📊 results in the last 5 days, with the "
                   "price move since. 📰 orders, deals, ratings, legal matters, management "
                   "changes, fund raising and dividends filed with NSE in the last 3 days. "
                   "Card colour is the model's view: green strong, grey neutral, amber below "
                   "its trend line, red weak.")

    # ---- record trades ----
    with st.expander("Record a trade, and your profit so far"):
        _my_trades(trades, prices, sorted(load_stocks()))

    # ---- details ----
    known = plan["checks"].dropna()
    with st.expander(f"Market checks: {int(known.sum())} of {len(known)} pass"):
        ui.checks([(name, {1.0: True, 0.0: False}.get(passed))
                   for name, passed in plan["checks"].items()])
        st.caption("– means not enough history is saved yet. The model buys when at least "
                   f"{config.MODEL_MARKET_MIN:.0%} of the known checks pass.")

    with st.expander("How this model did in the past"):
        result = model_history(style)
        summary, by_year = rotation.summarise(result, nifty)
        st.caption(f"Same rules as this page, including the buy range. "
                   f"{summary['period_start']} to {summary['period_end']}, after charges, "
                   f"starting with Rs {result['capital']:,.0f}. Not proven for real money: "
                   "under five years of history, and most company data only covers the last "
                   "few years.")
        one, two, three, four = st.columns(4)
        one.metric("Growth per year", pct(summary["annual_growth_rate"]),
                   f"Nifty {pct(summary['benchmark_annual_growth_rate'])}", delta_color="off")
        two.metric("Worst drawdown", pct(summary["max_drawdown"]),
                   f"Nifty {pct(summary['benchmark_max_drawdown'])}", delta_color="off")
        three.metric("Trades", summary["trades"],
                     f"{pct(summary['win_rate'], signed=False)} won", delta_color="off")
        four.metric("Charges paid", f"Rs {summary['total_charges']:,.0f}")
        show(charts.growth_chart(result["equity"],
                                 nifty["Close"].reindex(result["equity"].index).dropna(),
                                 result["capital"]))
        show(charts.drawdown_chart(result["equity"]))
        show(charts.yearly_bars(by_year))
        st.dataframe(result["trades"], hide_index=True, use_container_width=True)

    ranked = plan["today"].assign(rank=range(1, len(plan["today"]) + 1))
    with st.expander(f"Every stock's score ({len(ranked)}), and what goes into it"):
        st.dataframe(pd.DataFrame({
            "Part": [group.capitalize() for group in model.GROUPS],
            "Weight": [f"{config.MODEL_WEIGHTS[group]:.1%}" for group in model.GROUPS],
            "Factors": [GROUP_NOTES[group] for group in model.GROUPS],
        }), hide_index=True, use_container_width=True)
        st.dataframe(_score_table(ranked), hide_index=True,
                     use_container_width=True, column_config=SCORE_COLUMNS)


# ---------------------------------------------------------------- start -----
PAGES = {"Today": today_page, "Market": market_page, "Company": company_page}

if load_nifty() is None or not load_stocks():
    st.title("Kasauti")
    st.error("No data found. In the terminal run:  python update_data.py")
    st.stop()

# ---- top bar: the name and the three pages. ?page=Market opens a page directly. ----
wanted = st.query_params.get("page")
if wanted in PAGES and st.session_state.get("_page_from_link") != wanted:
    st.session_state["page"] = wanted
    st.session_state["_page_from_link"] = wanted
if st.session_state.get("page") not in PAGES:  # an old page name from before the clean-up
    st.session_state["page"] = "Today"
brand, menu = st.columns([1, 3], vertical_alignment="center")
with brand:
    ui.top_bar_brand()
with menu:
    page = st.radio("Page", list(PAGES), key="page", horizontal=True,
                    label_visibility="collapsed")
st.query_params["page"] = page

# ---- left panel ----
now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
fresh, status_text = today.data_status(load_nifty().index[-1], now)

if page == "Today":
    ui.side_heading("Your settings")
    # Widget values vanish when their page is not shown, so keep a copy.
    st.session_state["_money"] = st.sidebar.number_input(
        "Money for trading (Rs)", min_value=10_000, step=5_000,
        value=int(st.session_state.get("_money", config.CAPITAL)),
        help="Split equally across the stocks the model holds.")
    choices = ["Buy and sell", "Buy only", "Sell only"]
    st.session_state["_show"] = st.sidebar.radio(
        "Show", choices, index=choices.index(st.session_state.get("_show", choices[0])),
        key="today_show_choice")

ui.side_heading("Data")
ui.data_status(fresh == "fresh", status_text)
if st.sidebar.button("Update data now", type="primary", use_container_width=True,
                     help="Downloads the newest closing prices, news and FII/DII figures "
                          "from the internet, then refreshes this page. Takes a few minutes."):
    bar = st.sidebar.progress(0.0, text="Starting ...")

    def show_progress(step, done, total):
        bar.progress(min(1.0, done / total), text=f"{step}: {done} of {total}")

    try:
        summary = update.run_update(include_company_data=None, report=show_progress)
        note = "Data updated."
        if summary["failed_markets"]:
            note += " No data for: " + ", ".join(summary["failed_markets"]) + "."
        if summary["shareholding_problem"]:
            note += " Shareholding could not be refreshed."
        if summary["news_problem"] or summary["flows_problem"]:
            note += " NSE announcements or FII/DII figures could not be downloaded."
        else:
            note += f" {summary['news_added']} new announcements."
        st.session_state["update_note"] = note
    except Exception as error:
        st.session_state["update_note"] = f"The update stopped: {error}"
    st.cache_resource.clear()
    st.rerun()

if "update_note" in st.session_state:
    st.sidebar.info(st.session_state.pop("update_note"))
st.sidebar.caption("Once a day, after 4 pm. The market closes at 3:30, so there is nothing "
                   "new to download during the day.")

with st.sidebar.expander("More data options"):
    age = update.company_data_age_days()
    st.caption("Company results and shareholding: not downloaded yet." if age is None
               else "Company results and shareholding refresh by themselves once a week "
                    f"(last: {age:.0f} days ago).")
    if st.button("Refresh company results now", use_container_width=True,
                 help="Downloads company results and shareholding now instead of waiting "
                      "for the weekly refresh. Adds several minutes."):
        try:
            update.run_update(include_company_data=True)
            st.session_state["update_note"] = "Prices and company results updated."
        except Exception as error:
            st.session_state["update_note"] = f"The update stopped: {error}"
        st.cache_resource.clear()
        st.rerun()
    if st.button("Re-read saved files", use_container_width=True,
                 help="Only needed if the data was updated outside this page, for example by "
                      "the scheduled evening update or update_data.py in the terminal."):
        st.cache_resource.clear()
        st.rerun()
    st.caption("Re-read saved files after the evening update has run by itself while this "
               "page was open.")

st.sidebar.caption("Light or dark: open the ⋮ menu at the top right, then Settings.")

PAGES[page]()
