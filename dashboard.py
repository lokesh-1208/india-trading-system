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
    st.subheader("Who is buying and selling")
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
def market_page():
    nifty = load_nifty()
    allowed, trend = market_is_open_for_trades(nifty)
    dashboard = report.market_dashboard()
    last_day = nifty.index[-1].date()

    st.title("Market")
    st.caption(f"Prices up to {last_day}")

    close, previous = nifty["Close"].iloc[-1], nifty["Close"].iloc[-2]
    vix = dashboard[dashboard["market"] == "INDIAVIX"]
    left, middle, right = st.columns(3)
    left.metric("Nifty 50", f"{close:,.0f}", f"{(close / previous - 1) * 100:+.2f}%")
    middle.metric(f"Nifty's {config.MARKET_EMA}-day EMA", f"{trend.iloc[-1]:,.0f}",
                  f"Nifty is {(close / trend.iloc[-1] - 1) * 100:+.1f}% from it",
                  delta_color="off")
    if len(vix):
        right.metric("India VIX (fear gauge)", f"{vix['close'].iloc[0]:.2f}",
                     f"{vix['change_%'].iloc[0]:+.2f}%", delta_color="inverse")

    if allowed:
        st.success("New trades allowed: Nifty is above its trend line.", icon="✅")
    else:
        st.warning("No new trades: Nifty is below its trend line.", icon="⛔")

    period = st.radio("Period", list(PERIODS), index=1, horizontal=True, key="market_period")
    days = PERIODS[period]
    show(charts.trend_chart(
        charts.last_days(nifty["Close"], days), charts.last_days(trend, days),
        "Nifty 50", f"{config.MARKET_EMA}-day EMA", "Nifty 50 and its trend line"))

    left, right = st.columns([3, 2])
    with left:
        show(charts.change_bars(dashboard))
    with right:
        st.markdown("**The same figures as a table**")
        st.dataframe(dashboard, hide_index=True, use_container_width=True)

    money_flow_section()


def company_page():
    stocks, nifty, screens = load_stocks(), load_nifty(), load_screens()
    symbols = sorted(stocks)
    wanted = st.session_state.get("symbol", "RELIANCE")
    start = symbols.index(wanted) if wanted in symbols else 0

    st.title("Company")
    symbol = st.selectbox("Stock (type to search)", symbols, index=start)
    st.session_state["symbol"] = symbol

    prices = stocks[symbol]
    card = screens.card(symbol, prices)
    financial = screens.is_financial(symbol)
    table = screens.add_indicators(symbol, prices, nifty["Close"])
    next_results = screens.next_results(symbol, prices.index[-1])

    st.caption(f"{card['industry'] or 'Industry not known'} · prices up to "
               f"{prices.index[-1].date()} · next results: "
               f"{next_results.date() if next_results is not None else 'not known'}")

    tiles = st.columns(6)
    tiles[0].metric("Close", num(card["close"], 2), pct(card["below_52w_high"]) + " from 52w high",
                    delta_color="off")
    tiles[1].metric("Market value", f"Rs {num(card['market_cap_crore'], 0)} cr")
    tiles[2].metric("PE", num(card["pe"]), f"industry {num(card['industry_pe'])}",
                    delta_color="off")
    tiles[3].metric("Return on equity", pct(card["return_on_equity"], signed=False))
    tiles[4].metric("Debt to equity", num(card["debt_to_equity"], 2))
    tiles[5].metric("Scorecard", f"{company.score(card, financial)} of 10")

    # ---- the full model's view of this stock ----
    today = load_model().score_on(len(nifty.index) - 1)
    if symbol in today.index:
        row = today.loc[symbol]
        place = list(today.index).index(symbol) + 1
        st.subheader("Model score")
        left, right = st.columns([1, 4])
        with left:
            ui.big_score(row["score"], f"of 100, rank {place} of {len(today)}")
        with right:
            ui.score_bars([(group.capitalize(), row[group]) for group in model.GROUPS])
    else:
        st.caption("The full model does not score this stock today (not a current "
                   "Nifty 500 member, or it trades too little).")

    # ---- price ----
    st.subheader("Price")
    period = st.radio("Period", list(PERIODS), index=1, horizontal=True, key="company_period")
    recent = charts.last_days(table, PERIODS[period])
    show(charts.price_chart(recent, f"{symbol}: closing price and trend lines"))
    left, right = st.columns(2)
    with left:
        show(charts.volume_chart(recent))
    with right:
        show(charts.rsi_chart(recent))

    today = table.iloc[-1]
    checks = {
        "In the Nifty 500": bool(today["member"]),
        f"Traded value above Rs {config.MIN_TURNOVER_CRORE} crore a day":
            bool(today["turnover_crore"] >= config.MIN_TURNOVER_CRORE),
        "Close above both trend lines":
            bool(today["Close"] > today["ema_fast"] and today["Close"] > today["ema_slow"]),
        f"RSI between {config.RSI_MIN} and {config.RSI_MAX}":
            bool(config.RSI_MIN <= today["rsi"] <= config.RSI_MAX),
        "Volume above its 20-day average": bool(today["volume_ratio"] > 1),
        "Beat Nifty over 3 months": bool(today["relative_strength"] > 0),
        "Business passes the quality filter": bool(today["quality_ok"]),
        "Results not due in the next few days": not bool(today["near_results"]),
    }
    passed = sum(checks.values())
    with st.expander(f"Trading rules: {passed} of {len(checks)} passed at the last close",
                     expanded=False):
        for name, ok in checks.items():
            st.markdown(f"{'✅' if ok else '❌'} {name}")

    # ---- business ----
    st.subheader("Business")
    annual, quarterly = screens.company_rows(symbol), None
    if screens.quarterly is not None:
        quarterly = screens.quarterly.get(symbol)
    if annual is None:
        st.info("No company results downloaded for this stock.")
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
    st.subheader("Who owns it")
    holdings = None if screens.holdings is None else screens.holdings.get(symbol)
    owners = card["owners"]
    if holdings is None or owners is None:
        st.info("No shareholding data downloaded for this stock.")
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
    st.subheader("News and announcements")
    announcements = load_news()
    if len(announcements) == 0:
        st.info("No announcements yet. Press 'Update data now' in the sidebar.")
    else:
        everything = st.toggle("Also show routine paperwork", key="news_all")
        rows = news.for_symbol(announcements, symbol, days=90, important_only=not everything)
        if len(rows) == 0:
            st.write("Nothing important in the last 90 days "
                     f"(announcements saved from {announcements['time'].min():%d %b %Y}).")
        else:
            show_news(rows)
    _, deals = load_flows()
    stock_deals = flows.deals_for(deals, [symbol], days=90)
    if len(stock_deals):
        st.markdown("**Bulk and block deals in this stock**")
        st.dataframe(stock_deals[["date", "kind", "client", "side", "quantity", "price",
                                  "value_crore"]].round(2),
                     hide_index=True, use_container_width=True)

    # ---- scorecard ----
    st.subheader(f"Scorecard: {company.score(card, financial)} of 10")
    ui.checks(company.scorecard(card, financial))
    st.caption("– means the figure is not available. The thresholds are rules of "
               "thumb and have not been proven by a backtest.")


def _my_trades(trades, prices, symbols):
    """Your real positions, with forms to record a buy and a sell."""
    st.subheader("My real trades")
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
    strip = []
    for label, name in [("Nifty 50", config.BENCHMARK), ("India VIX", "INDIAVIX"),
                        ("USD/INR", "USDINR"), ("Brent", "BRENT"), ("Gold", "GOLD"),
                        ("S&P 500", "SP500")]:
        table = nifty if name == config.BENCHMARK else data.load_market(name)
        if table is not None and len(table) > 1:
            last, before = table["Close"].iloc[-1], table["Close"].iloc[-2]
            strip.append((label, float(last), float((last / before - 1) * 100)))
    ui.market_strip(strip)

    now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
    due = today.results_soon(built.results, today.buy_day(now))
    positions = journal.open_positions(trades, prices)
    trend_lines = {symbol: float(trend[symbol].iloc[-1]) for symbol in held if symbol in trend}
    mine = today.my_stocks(plan, positions, trend_lines)
    sells = mine[mine["action"] == "SELL"]
    money = st.session_state.get("model_money", int(config.CAPITAL))
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

    left, right = st.columns([2, 3])
    with left:
        money = st.number_input("Money for trading (Rs)", min_value=10_000,
                                value=int(config.CAPITAL), step=5_000, key="model_money",
                                help=f"Split equally across {rules['positions']} stocks.")
    with right:
        show_what = st.radio("Show", ["Buy and sell", "Buy only", "Sell only"],
                             horizontal=True, key="today_show")

    # ---- buy ----
    if show_what != "Sell only":
        def buy_rows(table, colour):
            return [{
                "symbol": row.symbol, "colour": colour,
                "tag": None, "note": about(row.symbol, row.rank, row.score),
                "chart": chart(row.symbol),
                "middle": ui.ladder(row.entry * (1 - rules["stop_loss"]), row.entry,
                                    row.buy_up_to),
                "right_top": f"{row.shares} shares",
                "right_bottom": f"about Rs {row.amount:,.0f}",
            } for row in table.itertuples()]

        if not plan["market_ok"]:
            ui.rows_head("To buy")
            ui.empty(plan["cash_text"] + " The stocks below are a watch list only.")
        elif len(picks):
            ui.rows_head("To buy", f"Buy at or below the limit. Stop-loss is "
                                   f"{rules['stop_loss']:.0%} under the price you pay.")
            ui.stock_rows(buy_rows(picks, ui.BLUE))
        else:
            ui.rows_head("To buy")
            ui.empty("Nothing new to buy: your holdings fill all the places.")
        if plan["market_ok"] and not plan["due_next_session"]:
            st.caption("These picks are from the weekly check on "
                       f"{plan['decided_on']:%d %b}. Mid-week, buy only if the price is still "
                       "inside the range.")

        if len(backups):
            ui.rows_head("Backups", "Use the next one if a pick is already above its limit")
            ui.stock_rows(buy_rows(backups, ui.NEUTRAL))
        left_out = [f"{symbol} ({date:%a %d %b})" for symbol, date in sorted(due.items())
                    if symbol in set(plan["today"].index[:20])]
        notes = []
        if left_out:
            notes.append("Left out because results are due within "
                         f"{config.RESULTS_BLOCK_DAYS} days: " + ", ".join(left_out) + ".")
        notes.append(f"The bar shows the stop-loss, the signal close (dot) and the buy limit, "
                     f"{above:.0%} above it. There is no lower limit: in the tests, stocks bought "
                     "below the signal close did best. The chart is the last 4 months, with the "
                     f"{config.EMA_FAST}-day EMA dotted.")
        st.caption(" ".join(notes))

    # ---- your stocks ----
    if show_what != "Buy only":
        ui.rows_head("Your stocks", "Hold or sell, checked on each day's close")
        if len(mine) == 0:
            ui.empty("No stocks recorded yet. After you buy, add it under 'My real trades' "
                     "and it shows here with its exit levels.")
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

        ui.rows_head("Avoid", "The weakest scores. Do not buy; if you hold one, the model "
                              "would rather you were out.")
        avoid = today.avoid_list(plan)
        ui.chips([(row.symbol, f"score {row.score:.0f}") for row in avoid.itertuples()])

    # ---- 4. events ----
    ui.rows_head("Events: results and news", "Ideas only. Trading on news has not been "
                 "tested, so there is no buy or sell here.")
    now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
    ranking = plan["today"]
    in_trend = plan.get("in_trend", {})
    closes = built.prepared["last_close"]
    soon = today.upcoming_results(built.results, ranking, in_trend, set(held),
                                  today.buy_day(now))
    out = today.recent_results(built.results, ranking, in_trend, closes, last_day)
    fresh = today.recent_news(load_news(), ranking, in_trend, closes, last_day)
    entries = today.event_cards(soon, out, fresh, set(held))
    worth = [entry for entry in entries if entry["worth"]]
    choice = st.radio("Which stocks", [f"Worth a look ({len(worth)})", f"All ({len(entries)})"],
                      horizontal=True, key="events_filter",
                      help="Worth a look: stocks you hold, the model's top 30, and any it "
                           "rates strong.")
    shown = worth if choice.startswith("Worth") else entries
    if not shown:
        st.write("No results due, results just out, or important company news for these "
                 "stocks. Update the data to fetch the latest.")
    else:
        ui.event_cards(shown)
    st.caption("📅 results due in the next 7 days · 📊 results in the last 5 days, with the "
               "price move since · 📰 orders, deals, ratings, legal matters, management "
               "changes, fund raising and dividends filed with NSE in the last 3 days. "
               "Card colour is the model's view: green strong, grey neutral, amber below "
               "its trend line, red weak. A missing move means no trading day has closed "
               "since the event.")

    # ---- record trades ----
    _my_trades(trades, prices, sorted(load_stocks()))

    # ---- details, out of the way ----
    st.subheader("Details")
    with st.expander(f"Market checks: {plan['market_score']:.0%} pass"):
        ui.checks([(name, {1.0: True, 0.0: False}.get(passed))
                   for name, passed in plan["checks"].items()])
        st.caption("– means not enough history is saved yet. The model buys when at least "
                   f"{config.MODEL_MARKET_MIN:.0%} of the known checks pass.")

    with st.expander("What goes into the score"):
        st.dataframe(pd.DataFrame({
            "Part": [group.capitalize() for group in model.GROUPS],
            "Weight": [f"{config.MODEL_WEIGHTS[group]:.1%}" for group in model.GROUPS],
            "Factors": [GROUP_NOTES[group] for group in model.GROUPS],
        }), hide_index=True, use_container_width=True)

    ranked = plan["today"].assign(rank=range(1, len(plan["today"]) + 1))
    with st.expander(f"Every stock's score today ({len(ranked)})"):
        st.dataframe(_score_table(ranked), hide_index=True,
                     use_container_width=True, column_config=SCORE_COLUMNS)

    with st.expander("How this model did in the past"):
        result = model_history(style)
        summary, by_year = rotation.summarise(result, nifty)
        st.caption(f"Same rules as this page, including the buy range. "
                   f"{summary['period_start']} to {summary['period_end']}, after charges, "
                   f"starting with Rs {result['capital']:,.0f}.")
        one, two, three, four = st.columns(4)
        one.metric("Growth per year", pct(summary["annual_growth_rate"]),
                   f"Nifty {pct(summary['benchmark_annual_growth_rate'])}", delta_color="off")
        two.metric("Worst drawdown", pct(summary["max_drawdown"]),
                   f"Nifty {pct(summary['benchmark_max_drawdown'])}", delta_color="off")
        three.metric("Trades", summary["trades"],
                     f"{pct(summary['win_rate'], signed=False)} won", delta_color="off")
        four.metric("Charges paid", f"Rs {summary['total_charges']:,.0f}")
        st.warning("Not proven for real money: under five years of history, and most company "
                   "data only covers the last few years.", icon="⚠️")
        show(charts.growth_chart(result["equity"],
                                 nifty["Close"].reindex(result["equity"].index).dropna(),
                                 result["capital"]))
        show(charts.drawdown_chart(result["equity"]))
        show(charts.yearly_bars(by_year))
        st.dataframe(result["trades"], hide_index=True, use_container_width=True)


# ---------------------------------------------------------------- start -----
PAGES = {"Today": today_page, "Market": market_page, "Company": company_page}

if load_nifty() is None or not load_stocks():
    st.title("Kasauti")
    st.error("No data found. In the terminal run:  python update_data.py")
    st.stop()

if st.session_state.get("page") not in PAGES:  # an old page name from before the clean-up
    st.session_state["page"] = "Today"
brand, menu, stamp = st.columns([2, 7, 2])
with brand:
    ui.top_bar_brand()
with menu:
    page = st.radio("Page", list(PAGES), key="page", horizontal=True,
                    label_visibility="collapsed")
with stamp:
    ui.as_of(f"Prices up to {load_nifty().index[-1]:%d %b %Y}")

st.sidebar.subheader("Prices")
now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
fresh, status_text = today.data_status(load_nifty().index[-1], now)
(st.sidebar.success if fresh == "fresh" else st.sidebar.warning)(status_text)

if st.sidebar.button("Update data now", type="primary",
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
st.sidebar.caption("When: once a day, any time after 4 pm (the market closes at 3:30). "
                   "During market hours there is nothing new to download.")

age = update.company_data_age_days()
st.sidebar.caption("Company results and shareholding: not downloaded yet." if age is None
                   else "Company results and shareholding change once a quarter, so they "
                        f"refresh by themselves once a week (last: {age:.0f} days ago).")

with st.sidebar.expander("Rarely needed"):
    if st.button("Refresh company results now",
                 help="Downloads company results and shareholding now instead of waiting "
                      "for the weekly refresh. Adds several minutes."):
        try:
            update.run_update(include_company_data=True)
            st.session_state["update_note"] = "Prices and company results updated."
        except Exception as error:
            st.session_state["update_note"] = f"The update stopped: {error}"
        st.cache_resource.clear()
        st.rerun()
    if st.button("Re-read saved files",
                 help="Only needed if the data was updated outside this page, for example by "
                      "the scheduled evening update or update_data.py in the terminal."):
        st.cache_resource.clear()
        st.rerun()
    st.caption("Re-read saved files: use it if the evening update ran by itself while this "
               "page was open, so the page shows the new prices.")
st.sidebar.divider()
st.sidebar.subheader("Light or dark")
st.sidebar.caption("Open the menu at the top right of the page (three dots), choose "
                   "Settings, then pick Light or Dark under 'Choose app theme'.")

PAGES[page]()
