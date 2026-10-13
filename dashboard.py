"""The dashboard: everything the system knows, as charts in your browser.

Run:  streamlit run dashboard.py
It reads the files that update_data.py downloaded, so run that first.
"""

import pandas as pd
import streamlit as st

import config
from trading import (breadth, charts, company, data, flows, indicators, journal, model, news,
                     picks, report, rotation, today, ui, update)
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


def load_picks_log():
    """Every day's top-10 list. Missing days of this week and last are made and saved."""
    return picks.update_log(load_model())


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
        history = (built.market_score * 100).rename("Checks passing").to_frame().tail(126)
        show(charts.share_chart(history, "Share of market checks passing, last 6 months",
                                guides=((config.MODEL_MARKET_MIN * 100, "buying allowed"),
                                        (config.MODEL_STRONG_MARKET * 100, "strong"))))

    wide = breadth.breadth(built.prepared["last_close"], built.prepared["liquid"])
    now_fast = wide["above_20_ema_%"].iloc[-1]
    with st.expander(f"Breadth: {now_fast:.0f}% of stocks above their {config.EMA_FAST}-day EMA"):
        ui.section_note("How many of the liquid Nifty 500 stocks are in an uptrend. Above about "
                        "60% the market is broadly healthy; below about 40% most stocks are "
                        "falling, even if Nifty itself looks fine.")
        show(charts.share_chart(wide.rename(columns={
            "above_20_ema_%": f"Above {config.EMA_FAST}-day EMA",
            "above_200_day_%": "Above 200-day average"}), "Market breadth, last 6 months",
            guides=((50, "half"),)))

    ranking = built.score_on(len(built.calendar) - 1)
    sectors = breadth.sector_strength(ranking, built.prepared["last_close"],
                                      built.trading["in_trend"].iloc[-1], built.industry)
    if len(sectors):
        with st.expander(f"Sectors: strongest {sectors.index[0]}, weakest {sectors.index[-1]}"):
            ui.section_note("From the stocks the model scores, grouped by industry (at least 3 "
                            "stocks). This shows why some industries fill the buy list.")
            show(charts.sector_bars(sectors))
            st.dataframe(sectors.rename(columns={
                "stocks": "Stocks", "month_%": "Median 1-month change %",
                "above_ema_%": f"% above {config.EMA_FAST}-day EMA",
                "score": "Median model score"}), use_container_width=True)

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

    # ---- where the stock stands for you ----
    rules = config.MODEL_STYLES[config.MODEL_STYLE]
    open_rows = journal.open_positions(journal.load())
    log = load_picks_log()
    list_day = log["list_day"].max() if len(log) else None
    weekly = picks.weekly_list(log, list_day) if list_day is not None else log
    todays_list = (set(log.loc[log["list_day"] == list_day, "symbol"])
                   if list_day is not None else set())
    weakest = set(ranking.tail(config.MODEL_WEAKEST).index)
    stands, levels = [], []
    if symbol in set(open_rows["symbol"]):
        mine = open_rows[open_rows["symbol"] == symbol]
        quantity = int(mine["quantity"].sum())
        paid = float((mine["buy_price"] * mine["quantity"]).sum() / quantity)
        hard_stop = paid * (1 - rules["stop_loss"])
        exit_line = max(hard_stop, float(table["ema_fast"].iloc[-1]))
        stands.append(("You hold it", f" {quantity} shares at Rs {paid:,.2f}. Sell on a close "
                                      f"below Rs {exit_line:,.2f}"))
        levels += [(paid, "Bought", charts.BLUE), (hard_stop, "Hard stop", charts.RED)]
    if symbol in set(weekly["symbol"]):
        on = weekly.set_index("symbol").loc[symbol]
        limit = float(on["close"]) * (1 + (rules.get("max_gap") or 0))
        stands.append(("On this week's list", f" rank {int(on['rank'])}, buy up to "
                                              f"Rs {limit:,.2f}"))
        levels.append((limit, "Buy up to", charts.AQUA))
    elif symbol in todays_list:
        stands.append(("On today's list", " not on this week's list, so watch only"))
    if symbol in weakest:
        stands.append(("On the avoid list", " one of the 10 weakest scores"))
    if not stands:
        stands.append(("Not on any list", f" rank {rank} of {len(ranking)}" if rank
                       else " not scored by the model"))
    ui.chips(stands)

    tiles = st.columns(6)
    cap = card["market_cap_crore"]
    cap_text = ("-" if cap is None or pd.isna(cap) else
                f"Rs {cap / 1e5:,.1f}L cr" if cap >= 1e5 else f"Rs {cap:,.0f} cr")
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
        show(charts.add_levels(charts.price_chart(
            recent, f"{symbol}: closing price and trend lines (the {config.EMA_FAST}-day EMA "
                    "is the exit line)"), levels))
        left, right = st.columns(2)
        with left:
            show(charts.volume_chart(recent))
        with right:
            show(charts.rsi_chart(recent))

    # ---- peers ----
    industry_name = built.industry.get(symbol, "")
    peers = [s for s in ranking.index if built.industry.get(s, "") == industry_name]
    if industry_name and len(peers) > 1:
        top = ranking.loc[peers].head(8)
        trend_now = built.trading["in_trend"].iloc[-1]
        with st.expander(f"Peers: {len(peers)} {industry_name} stocks the model scores"):
            ui.section_note("The best-scored stocks in the same industry, to compare with.")
            st.dataframe(pd.DataFrame({
                "Rank": [list(ranking.index).index(s) + 1 for s in top.index],
                "Stock": top.index, "Score": top["score"].round(0),
                "Price": top["close"].round(2),
                "6-month change %": (top["momentum"] * 100).round(1),
                "Model view": [today.model_view(float(top.loc[s, "score"]),
                                                bool(trend_now.get(s, False))) for s in top.index],
                "This stock": ["◀" if s == symbol else "" for s in top.index],
            }), hide_index=True, use_container_width=True,
                column_config={"Score": SCORE_COLUMNS["score"]})

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
    with st.expander(f"Scorecard (a rule of thumb, not part of the model): "
                     f"{company.score(card, financial)} of 10"):
        ui.checks(company.scorecard(card, financial))
        st.caption("– means the figure is not available. These ten checks are common rules of "
                   "thumb. They are not part of the model's score and have not been tested.")


def _my_trades(trades, prices, symbols, last_day=None):
    """Your real positions, with forms to record a buy and a sell."""
    totals = journal.totals(trades, prices, last_day)
    one, two, three, four = st.columns(4)
    one.metric("Money in the market", f"Rs {totals['invested']:,.0f}")
    two.metric("Worth at the last close", f"Rs {totals['value']:,.0f}")
    three.metric("Gain on open positions", f"Rs {totals['open_gain']:+,.0f}")
    four.metric("Closed trades, after charges", f"Rs {totals['closed_net']:+,.0f}",
                f"tax about Rs {totals['tax_estimate']:,.0f}" if totals["tax_estimate"] else None,
                delta_color="off")

    positions = journal.open_positions(trades, prices, last_day)
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
            st.dataframe(closed[["symbol", "buy_date", "buy_price", "sell_date", "sell_price",
                                 "quantity", "profit", "charges", "net_profit", "profit_%",
                                 "note"]].round(2), hide_index=True, use_container_width=True)
    st.caption("Saved in journal/real_trades.csv on this computer only. Keep your own "
               "backup. Open gains are before charges. Closed trades show Zerodha delivery "
               f"charges; the tax estimate is {config.SHORT_TERM_TAX:.0%} short-term gains tax "
               "on the year's net profit (losses offset gains). Check with your CA.")


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
    mine = today.my_stocks(plan, positions, trend_lines, last_day=last_day)
    sells = mine[mine["action"] == "SELL"]
    money = st.session_state.get("_money", int(config.CAPITAL))
    share = built.amount_share()
    per_stock = money / rules["positions"] * share

    # ---- the weekly list (tested), today's list (watch) and the record of every list ----
    log = load_picks_log()
    list_day = log["list_day"].max()
    todays = log[log["list_day"] == list_day].copy()
    weekly = picks.weekly_list(log, list_day)
    places = max(0, rules["positions"] - len(held))
    status = picks.weekly_status(weekly, prices, built.trading["in_trend"].iloc[-1], due,
                                 set(held), places, above, budget=per_stock)
    buy_now = status[status["status"] == "Buy"].head(places)
    watch = todays[~todays["symbol"].isin(set(weekly["symbol"]) | set(held))]
    week_rows, week_days = picks.tracker(log, list_day, close, nifty["Close"])
    days_on = (dict(zip(week_rows["symbol"], week_rows["days_on"])) if len(week_rows) else {})
    from_last_week = (dict(zip(week_rows["symbol"], week_rows["last_week"]))
                      if len(week_rows) else {})
    weekly_day = len(weekly) and weekly["list_day"].iloc[0] == list_day

    to_sell = len(sells)
    sell_text = f", sell {to_sell}" if to_sell else ""
    if not plan["market_ok"]:
        headline = f"Market weak: no new buys{sell_text}"
    elif len(buy_now):
        headline = (f"Buy {len(buy_now)} from the weekly list{sell_text}"
                    + (f". Watch: {len(watch)} others" if len(watch) and not weekly_day else ""))
    elif places == 0:
        headline = f"All places filled: nothing to buy{sell_text}"
    else:
        headline = (f"No weekly pick is buyable today{sell_text}"
                    + (f". Watch: {len(watch)} others" if len(watch) else ""))
    week_start = weekly["list_day"].iloc[0] if len(weekly) else list_day
    note = (f"Buy from the weekly list (made from the close before {week_start:%a %d %b}, the "
            f"tested rule); the other names are on today's list from the {last_day:%a %d %b} "
            "close, for watching. Exits are checked on every close.")
    ui.day_plan(headline, note, plan["market_level"], plan["market_note"])
    if plan["market_level"] != "strong":
        st.caption(plan["market_note"])

    show_what = st.session_state.get("_show", "Buy and sell")
    buy_symbols = set(buy_now["symbol"])

    def weekly_rows(table):
        rows = []
        for row in table.itertuples():
            shares = int(per_stock // row.limit)
            if row.symbol in buy_symbols:
                tag, colour = ("Buy" if row.kind == "Pick" else "Buy (backup)"), ui.BLUE
                bottom = (f"about Rs {shares * row.close:,.0f}" if weekly_day
                          else f"last close Rs {row.last:,.2f}, in range")
            elif row.status == "Buy":
                tag, colour, bottom = "Backup", ui.NEUTRAL, f"last close Rs {row.last:,.2f}"
            else:
                tag, colour = row.status, ui.NEUTRAL
                bottom = {"Too costly": f"one share costs more than Rs {per_stock:,.0f}",
                          "Missed": f"last close Rs {row.last:,.2f}, above the limit",
                          "Trend broke": f"closed below its {config.EMA_FAST}-day EMA",
                          "Results soon": "results within 5 days",
                          "You hold": "see Your stocks"}.get(row.status, "")
            rows.append({
                "symbol": row.symbol, "colour": colour, "tag": tag,
                "note": about(row.symbol, row.rank, row.score),
                "chart": chart(row.symbol),
                "middle": ui.ladder(row.close * (1 - rules["stop_loss"]), row.close, row.limit),
                "right_top": f"{shares} shares",
                "right_bottom": bottom,
            })
        return rows

    def watch_rows(table):
        rows = []
        for row in table.itertuples():
            limit = row.close * (1 + above)
            shares = int(per_stock // limit)
            on = days_on.get(row.symbol, 1)
            tag = (f"Day {on} on list" if on > 1 else
                   "Back from last week" if from_last_week.get(row.symbol) else "New today")
            rows.append({
                "symbol": row.symbol, "colour": ui.GOOD, "tag": tag,
                "note": about(row.symbol, row.rank, row.score),
                "chart": chart(row.symbol),
                "middle": ui.ladder(row.close * (1 - rules["stop_loss"]), row.close, limit),
                "right_top": f"{shares} shares",
                "right_bottom": f"about Rs {shares * row.close:,.0f}",
            })
        return rows

    if show_what != "Sell only":
        # ---- buy: the weekly list ----
        title = (f"Buy: this week's list, {len(buy_now)} to buy" if plan["market_ok"]
                 else "Buy: this week's list, no new buys")
        with st.expander(title, expanded=True):
            if not plan["market_ok"]:
                ui.empty(plan["cash_text"])
            ui.section_note(f"The tested rule. The model holds {rules['positions']} stocks: "
                            f"buy the ones marked Buy, at or below the limit. Limits stay fixed "
                            f"all week. Stop-loss is {rules['stop_loss']:.0%} under the price "
                            "you pay. "
                            + (f"The market is not strong, so each buy uses {share:.0%} of the "
                               f"normal amount: about Rs {per_stock:,.0f} instead of "
                               f"Rs {money / rules['positions']:,.0f}." if share < 1 else
                               f"Each buy uses about Rs {per_stock:,.0f}."))
            if len(status):
                ui.stock_rows(weekly_rows(status))
            else:
                ui.empty("No weekly list yet.")
            left_out = [f"{symbol} ({date:%a %d %b})" for symbol, date in sorted(due.items())
                        if symbol in set(plan["today"].index[:20])]
            notes = []
            if left_out:
                notes.append("Left out because results are due within "
                             f"{config.RESULTS_BLOCK_DAYS} days: " + ", ".join(left_out) + ".")
            notes.append("Best time to buy: the first open of the week, with an AMO limit order "
                         "at the limit placed the evening before. Buying later in the week gave "
                         "about the same return in the tests but a deeper worst fall (about "
                         f"-29% against -21%). The bar shows the stop-loss, the signal close "
                         f"(dot) and the buy limit, {above:.0%} above it.")
            st.caption(" ".join(notes))

        # ---- watch: other names on today's list ----
        if len(watch) and not weekly_day:
            with st.expander(f"Watch: {len(watch)} other names on today's list (not tested)"):
                ui.section_note(f"On today's top {len(todays)} from the {last_day:%a %d %b} close "
                                "but not on this week's list. In the tests, buying new picks "
                                "every day did worse than buying weekly (about +12% a year "
                                "against +20%). Strong ones are likely to be on next week's "
                                "list.")
                ui.stock_rows(watch_rows(watch))

        # ---- the week tracker ----
        if len(week_rows):
            on_today = int(week_rows["on_today"].sum())
            with st.expander(f"This week's tracker: {len(week_rows)} stocks picked, "
                             f"{on_today} on today's list", expanded=True):
                ui.section_note("Every list this week, saved as it was made. The number is "
                                "the stock's rank on that day's list.")
                ui.tracker_table(week_rows.to_dict("records"), week_days, list_day)
                st.caption("Since first picked: from the close the stock was first picked on "
                           "(this week or last) to the latest close. Nifty: Nifty 50 over the "
                           "same days. Lists made before the record started on 13 Oct were "
                           "rebuilt from saved data.")

        card = picks.list_scorecard(log, close, nifty["Close"], top=rules["positions"])
        if len(card):
            ahead = int((card["vs_nifty"] > 0).sum())
            with st.expander(f"Track record: {ahead} of {len(card)} weekly lists ahead of Nifty"):
                ui.section_note(f"Each weekly list's top {rules['positions']} picks, from the "
                                "close they were picked on to the latest close, against Nifty "
                                "over the same days. This grows into the live test of the model.")
                st.dataframe(pd.DataFrame({
                    "Week of": card["list_day"].dt.strftime("%a %d %b %Y"),
                    "Picks": card["picks"], "Picks, average %": card["average_%"],
                    "Nifty %": card["nifty_%"], "Ahead of Nifty (points)": card["vs_nifty"],
                }), hide_index=True, use_container_width=True)
                st.caption("Lists before 13 Oct 2026 were rebuilt from saved data, not saved "
                           "at the time; judge the model on the ones saved from then on.")

    # ---- your stocks ----
    if show_what != "Buy only":
        waiting = int((mine["action"] == "WAIT").sum()) if len(mine) else 0
        if len(mine) == 0:
            title = "Your stocks: none recorded"
        elif len(sells):
            title = f"Your stocks: {len(mine)}, sell {len(sells)}"
        else:
            title = (f"Your stocks: {len(mine)}, all hold" if not waiting else
                     f"Your stocks: {len(mine)}, {waiting} bought today")
        with st.expander(title, expanded=len(mine) > 0):
            if len(mine) == 0:
                ui.empty("After you buy, add it under 'Record a trade' and it shows here, "
                         "marked Hold or Sell each day.")
            else:
                rows = []
                for row in mine.to_dict("records"):
                    new_buy = row["action"] == "WAIT"
                    tag, colour = {"SELL": ("Sell", ui.SELL), "WAIT": ("Bought today", ui.NEUTRAL)
                                   }.get(row["action"], ("Hold", ui.GOOD))
                    exit_line = row["trend_line"]
                    rows.append({
                        "symbol": row["symbol"], "tag": tag, "colour": colour,
                        "note": (f"{row['quantity']} shares at Rs {row['buy_price']:,.2f}, "
                                 f"bought {row['bought']:%a %d %b}"),
                        "chart": chart(row["symbol"]),
                        "middle": ui.holding_ladder(row["stop_loss"], exit_line, row["buy_price"],
                                                    float("nan") if new_buy else row["last_price"]),
                        "right_top": ("Not checked yet" if new_buy else
                                      f"Rs {row['last_price']:,.2f}  {row['gain_%']:+.1f}%"),
                        "right_bottom": ("Checked after today's close" if new_buy else
                                         f"Day {row['days_held']} of holding" if row["action"] != "SELL"
                                         else row["reason"].capitalize()),
                        "foot": [
                            (("Profit locked in" if row["exit_pct"] > 0 else "If it exits now"),
                             f"{row['exit_pct']:+.1f}% ({'+' if row['exit_rs'] >= 0 else '-'}"
                             f"Rs {abs(row['exit_rs']):,.0f}) on a close below "
                             f"Rs {row['exit_line']:,.2f}",
                             "up" if row["exit_pct"] > 0 else "down"),
                            ("GTT stop-loss in Kite",
                             (f"Rs {row['gtt']:,.2f}, your buy price. Move it up from the "
                              f"hard stop (Rs {row['stop_loss']:,.2f})."
                              if row["gtt"] > row["stop_loss"] else
                              f"Rs {row['gtt']:,.2f} (-{rules['stop_loss']:.0%}). Safety net "
                              "if a check is missed.")),
                            ("Target", "None. The exit line rises with the stock and becomes "
                                       "a profit exit once it passes your buy price."),
                            ("Holding", "Typical: 2 weeks. Losers often go within a week, "
                                        "winners can run 4 weeks or more."),
                        ],
                    })
                ui.stock_rows(rows)
                st.caption("The bar shows the hard stop (red), the exit line (today's "
                           f"{config.EMA_FAST}-day EMA: amber below your buy price, green above "
                           "it), your buy price (ring) and the last close (dot). In the tests, 296 of 335 trades ended on the trend exit and "
                           "only 10 on the hard stop. Winners were fewer than losers (39% won) "
                           "but much bigger (median +5.7% against -3.0%); capping winners at a "
                           "target of +10% would have cut the average trade from +1.75% to "
                           "about 0%.")

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
        _my_trades(trades, prices, sorted(load_stocks()), last_day)

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
def run_with_progress(where, **options):
    """Run an update with a progress bar, then refresh the page with a short note."""
    bar = where.progress(0.0, text="Starting ...")

    def show_progress(step, done, total):
        bar.progress(min(1.0, done / max(total, 1)), text=f"{step}: {done} of {total}")

    try:
        summary = update.run_update(report=show_progress, **options)
        note = "Data updated in " + (f"{summary['seconds'] // 60} min "
                                     if summary["seconds"] >= 60 else "") \
            + f"{summary['seconds'] % 60} s. " + update.describe_prices(summary["prices"])
        if summary["failed_markets"]:
            note += " No data for: " + ", ".join(summary["failed_markets"]) + "."
        if summary["results_companies"]:
            note += f" Company results checked for {summary['results_companies']} companies."
        if summary["results_problem"]:
            note += " Company results could not be finished."
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


if st.sidebar.button("Update data now", type="primary", use_container_width=True,
                     help="Adds the newest closing prices from NSE, news, FII/DII figures "
                          "and results of companies that just reported. Usually 1-2 "
                          "minutes; once a week the full price history is downloaded "
                          "too (about 6 minutes more)."):
    run_with_progress(st.sidebar)

if "update_note" in st.session_state:
    st.sidebar.info(st.session_state.pop("update_note"))
st.sidebar.caption("Once a day, after 6 pm, when NSE has published the day's closing "
                   "prices. Earlier in the evening the day's prices come from Yahoo "
                   "and are corrected on the next update.")

with st.sidebar.expander("More data options"):
    age = update.full_download_age_days()
    st.caption("Full price history: not downloaded yet." if age is None
               else f"Full price history from Yahoo: last downloaded {age} days ago "
                    f"(again every {config.FULL_PRICES_REFRESH_DAYS} days by itself).")
    if st.button("Download full price history now", use_container_width=True,
                 help="Downloads 10 years of prices for every stock again from Yahoo. "
                      "About 6 minutes. Only needed if prices look wrong."):
        run_with_progress(st, full_prices=True, include_company_data=False)
    age = update.company_data_age_days()
    st.caption("Company results: not downloaded yet." if age is None
               else "Company results are downloaded by themselves for companies that "
                    "just reported. Shareholding is checked once a week.")
    if st.button("Refresh all company results now", use_container_width=True,
                 help="Downloads results for every company and the shareholding "
                      "filings, without downloading prices again. 20 minutes or more."):
        bar = st.progress(0.0, text="Starting ...")

        def show_company_progress(step, done, total):
            bar.progress(min(1.0, done / max(total, 1)), text=f"{step}: {done} of {total}")

        try:
            result = update.refresh_company_data(show_company_progress, everything=True,
                                                 include_shareholding=True)
            note = f"Company results downloaded for {result['results_companies']} companies."
            if result["results_problem"] or result["shareholding_problem"]:
                note += " Some downloads did not finish: " + (
                    result["results_problem"] or result["shareholding_problem"])
            st.session_state["update_note"] = note
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

ui.side_heading("Your routine")
ui.routine([
    ("Evening, after 6 pm", "Update data. In Your stocks, sell tomorrow at the open if it "
                            "says Sell; move a GTT up if it says so."),
    ("Sunday or Monday early", "Place AMO limit buys at the limits of the weekly list."),
    ("Any day", "Record every buy and sell under Record a trade."),
])
st.sidebar.caption("Light or dark: open the ⋮ menu at the top right, then Settings.")

PAGES[page]()
