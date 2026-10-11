"""The dashboard: everything the system knows, as charts in your browser.

Run:  streamlit run dashboard.py
It reads the files that update_data.py downloaded, so run that first.
"""

import pandas as pd
import streamlit as st

import config
from trading import (backtest, charts, company, data, flows, indicators, journal, news,
                     report, rotation, shareholding, update)
from trading.screens import Screens

st.set_page_config(page_title="India Trading System", layout="wide")

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


@st.cache_resource(show_spinner="Working out today's shortlist ...")
def load_shortlist():
    account = report.account_status(report.load_journal())
    shortlist, removed = report.build_shortlist(
        load_stocks(), load_nifty(), account, load_screens()
    )
    return shortlist, removed, account


@st.cache_resource(show_spinner="Running the backtest, about half a minute ...")
def run_backtest_now():
    nifty, screens = load_nifty(), load_screens()
    stocks = {symbol: screens.add_indicators(symbol, prices, nifty["Close"])
              for symbol, prices in load_stocks().items()}
    result = backtest.run_backtest(stocks, nifty)
    return result["equity"], result["trades"]


@st.cache_resource(show_spinner="Preparing the ownership rotation ...")
def load_rotation():
    """Price tables and shareholding history for the ownership rotation."""
    holdings = shareholding.load_shareholding()
    if holdings is None:
        return None, None
    membership = load_screens().membership
    prepared = rotation.prepare(
        load_stocks(), load_nifty(),
        lambda symbol, dates: data.membership_mask(symbol, dates, membership))
    return prepared, holdings


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


def saved_backtest():
    """The results of the last `python run_backtest.py`, or None."""
    equity_file = config.REPORTS_DIR / "backtest_equity.csv"
    trades_file = config.REPORTS_DIR / "backtest_trades.csv"
    if not equity_file.exists() or not trades_file.exists():
        return None
    equity = pd.read_csv(equity_file, index_col=0, parse_dates=True)["equity"]
    return equity, pd.read_csv(trades_file)


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


def shortlist_page():
    shortlist, removed, account = load_shortlist()
    nifty = load_nifty()
    allowed, _ = market_is_open_for_trades(nifty)

    st.title("Shortlist")
    st.caption(f"Stocks that passed every rule at the close of {nifty.index[-1].date()}")

    one, two, three, four = st.columns(4)
    one.metric("Passed all rules", len(shortlist))
    two.metric("Removed by quality filter", removed["quality"])
    three.metric("Removed, results due soon", removed["results"])
    four.metric("Open positions", f"{len(account['open_symbols'])} of {config.MAX_POSITIONS}")

    if account["blocked_by_drawdown"]:
        st.error("Drawdown limit reached. No new trades.", icon="🛑")
    elif not allowed:
        st.warning("Nifty is below its trend line, so these are for watching only.", icon="⛔")

    if len(shortlist) == 0:
        st.info("Nothing passed the rules. No trade is also a decision.")
        return

    tabs = st.tabs(["Trade plan", "The business", "Size and valuation", "Who owns it"])
    groups = [report.TRADE_COLUMNS[1:], report.BUSINESS_COLUMNS,
              report.VALUE_COLUMNS, report.OWNER_COLUMNS]
    for tab, columns in zip(tabs, groups):
        tab.dataframe(shortlist[columns], hide_index=True, use_container_width=True)

    st.divider()
    left, right = st.columns([2, 1])
    choice = left.selectbox("See the full picture of a stock", shortlist["symbol"])
    right.write("")
    right.write("")
    if right.button("Open company page"):
        st.session_state["symbol"] = choice
        st.session_state["go_to_page"] = "Company"
        st.rerun()


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
    marks = {True: "✅", False: "❌", None: "➖"}
    left, right = st.columns(2)
    for position, (name, ok) in enumerate(company.scorecard(card, financial)):
        (left if position < 5 else right).markdown(f"{marks[ok]} {name}")
    st.caption("➖ means the figure is not available. The thresholds are rules of "
               "thumb and have not been proven by a backtest.")


def backtest_page():
    st.title("Backtest")
    st.caption("How the current rules would have done in the past, after Zerodha charges.")

    if st.button("Run the backtest again with today's data and settings"):
        st.session_state["fresh_backtest"] = True
    if st.session_state.get("fresh_backtest"):
        equity, trades = run_backtest_now()
    else:
        saved = saved_backtest()
        if saved is None:
            st.info("No saved backtest yet. Press the button above, or run:  "
                    "python run_backtest.py")
            return
        equity, trades = saved

    nifty = load_nifty()
    result = {"capital": float(equity.iloc[0]), "trades": trades, "equity": equity,
              "benchmark": nifty["Close"].reindex(equity.index)}
    summary, by_year = backtest.summarise(result)

    one, two, three, four = st.columns(4)
    one.metric("Growth per year", pct(summary["annual_growth_rate"]),
               f"Nifty {pct(summary['benchmark_annual_growth_rate'])}", delta_color="off")
    two.metric("Worst drawdown", pct(summary["max_drawdown"]),
               f"Nifty {pct(summary['benchmark_max_drawdown'])}", delta_color="off")
    three.metric("Trades", summary["trades"], f"{pct(summary['win_rate'], signed=False)} won",
                 delta_color="off")
    four.metric("Charges paid", f"Rs {summary['total_charges']:,.0f}")

    beat = summary["annual_growth_rate"] > summary["benchmark_annual_growth_rate"]
    safer = summary["max_drawdown"] > summary["benchmark_max_drawdown"]
    if beat and safer:
        st.success("These rules beat Nifty with a smaller drawdown in this test.", icon="✅")
    else:
        st.warning("These rules did not beat Nifty buy-and-hold in this test. "
                   "They are not ready for real money.", icon="⚠️")

    show(charts.growth_chart(equity, result["benchmark"].dropna(), result["capital"]))
    show(charts.drawdown_chart(equity))
    show(charts.yearly_bars(by_year))

    with st.expander("All the numbers"):
        st.text(backtest.format_summary(summary, by_year))
    with st.expander(f"All {len(trades)} trades"):
        st.dataframe(trades, hide_index=True, use_container_width=True)
    st.caption("Past members of the Nifty 500 that were later delisted are missing "
               "from the price data, so real results would be somewhat worse.")


def _what_to_do(plan, trades, money):
    """The action box at the top of the rotation page."""
    prices = plan["last_price"]
    budget = money / config.ROTATION_POSITIONS
    open_rows = journal.open_positions(trades)
    held_quantity = open_rows.groupby("symbol")["quantity"].sum()
    last_day = prices.name
    next_check = (last_day + pd.offsets.MonthBegin(1)).strftime("%B %Y")

    # Fill the free places from the best-ranked stocks, passing over any whose
    # single share costs more than the money per stock (as the tests did).
    buys, too_dear = [], []
    for symbol in plan["candidates"]:
        if len(buys) >= plan["room"]:
            break
        price = float(prices.get(symbol, float("nan")))
        quantity = int(budget // price) if price > 0 else 0
        (buys if quantity >= 1 else too_dear).append((symbol, price, quantity))

    with st.container(border=True):
        st.markdown("#### What to do")
        actions = len(plan["sell"]) + len(buys)
        if actions == 0:
            if plan["keep"]:
                st.markdown("### ✋ Hold. Nothing to change.")
                st.write("Your holdings are the ones the rule wants: " + ", ".join(plan["keep"]) + ".")
            elif not plan["market_ok"]:
                st.markdown("### 💤 Stay in cash. Nothing to buy.")
                st.write(f"Nifty is below its {config.ROTATION_MARKET_SMA}-day average. "
                         "The rule buys nothing until Nifty is back above it.")
            else:
                st.markdown("### 💤 Nothing to do yet.")
                st.write("No scores are available. Update the data.")
        else:
            when = ("at the next market open" if plan["due_next_session"]
                    else f"outstanding from the check on {plan['decided_on'].date()}")
            st.markdown(f"### 📋 {actions} action{'s' if actions != 1 else ''} {when}")
            for symbol in plan["sell"]:
                quantity = int(held_quantity.get(symbol, 0))
                reason = ("Nifty is below its average" if not plan["market_ok"]
                          else f"it fell out of the top {config.ROTATION_KEEP_RANK}")
                st.markdown(f"🔴 **Sell {symbol}**: all {quantity} shares, because {reason}.")
            for symbol, price, quantity in buys:
                st.markdown(f"🟢 **Buy {symbol}**: {quantity} shares at about Rs {price:,.2f} "
                            f"(about Rs {quantity * price:,.0f}).")
            for symbol in plan["keep"]:
                st.markdown(f"✋ **Hold {symbol}**.")
            if too_dear:
                names = ", ".join(f"{symbol} (Rs {price:,.0f} a share)" for symbol, price, _ in too_dear)
                st.caption(f"Passed over because one share costs more than the Rs {budget:,.0f} "
                           f"set aside per stock: {names}.")
            if not plan["due_next_session"] and not len(open_rows):
                st.caption("The rule has held these since the start of the month. In the tests "
                           "it only bought on the first trading day of a month.")
        st.caption(f"The rule is checked once a month. Next check: first trading day of "
                   f"{next_check}. Prices are from {last_day.date()}.")


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


def rotation_page():
    st.title("Ownership rotation")
    st.caption("Hold the 10 stocks where foreign funds and mutual funds raised their holding "
               "last quarter and the price has been strong. Checked once a month. All cash "
               f"while Nifty is below its {config.ROTATION_MARKET_SMA}-day average.")

    prepared, holdings = load_rotation()
    if prepared is None:
        st.info("No shareholding history yet. Tick the box in the sidebar and press "
                "'Update data now'.")
        return
    nifty = load_nifty()
    trades = journal.load()
    held = list(journal.open_positions(trades)["symbol"].unique())
    plan = rotation.decision(prepared, holdings, held)

    money = st.number_input("Money you have set aside for this rule (Rs)", min_value=10_000,
                            value=int(config.CAPITAL), step=5_000,
                            help=f"It is split equally across {config.ROTATION_POSITIONS} stocks.")
    _what_to_do(plan, trades, money)
    _my_trades(trades, plan["last_price"], sorted(load_stocks()))

    # ---- details, folded away ----
    st.subheader("Details")
    ranking = plan["ranking"]
    with st.expander(f"The rule's ranking: top {config.ROTATION_KEEP_RANK}"):
        if len(ranking) == 0:
            st.write("No scores yet.")
        else:
            top = ranking.reset_index(names="symbol")
            st.caption(f"Scored on {plan['scoring_day'].date()}. The top "
                       f"{config.ROTATION_POSITIONS} are bought; a holding is kept while it "
                       f"stays in the top {config.ROTATION_KEEP_RANK}.")
            st.dataframe(pd.DataFrame({
                "rank": range(1, len(top) + 1),
                "symbol": top["symbol"],
                "score": top["score"].round(3),
                "FII holding change": top["fii_change"].round(2),
                "MF holding change": top["mf_change"].round(2),
                "6-month price change %": (top["momentum"] * 100).round(1),
                "price now": [round(float(plan["last_price"].get(s, float("nan"))), 2)
                              for s in top["symbol"]],
            }), hide_index=True, use_container_width=True)

    watched = list(dict.fromkeys(held + list(plan["buy"]) + list(ranking.index[:10])))
    announcements = load_news()
    recent = announcements[announcements["symbol"].isin(watched) & announcements["important"]
                           & (announcements["time"] >= pd.Timestamp.today()
                              - pd.Timedelta(days=14))]
    with st.expander(f"News on your stocks and the rule's top 10, last 14 days ({len(recent)})"):
        if len(announcements) == 0:
            st.write("No announcements yet. Press 'Update data now' in the sidebar.")
        elif len(recent) == 0:
            st.write("Nothing important.")
        else:
            st.caption("Read these before you place an order. The rule itself does not use news.")
            show_news(recent, with_symbol=True)

    with st.expander("Paper portfolio: the rule followed exactly, with no real money"):
        paper_start = pd.Timestamp(config.PAPER_START)
        if nifty.index[-1] <= paper_start:
            st.write(f"Starts on {paper_start.date()} with Rs {config.CAPITAL:,.0f}. "
                     "It fills in as you update the data.")
        else:
            paper = rotation.simulate(prepared, holdings, start=paper_start)
            value = float(paper["equity"].iloc[-1])
            benchmark = nifty["Close"].reindex(paper["equity"].index).dropna()
            one, two, three = st.columns(3)
            one.metric(f"Value since {paper_start.date()}", f"Rs {value:,.0f}",
                       pct(value / paper["capital"] - 1))
            two.metric("Nifty over the same days",
                       pct(benchmark.iloc[-1] / benchmark.iloc[0] - 1))
            three.metric("Cash", f"Rs {paper['cash']:,.0f}")
            if len(paper["positions"]):
                st.dataframe(paper["positions"], hide_index=True, use_container_width=True)
            if len(paper["trades"]):
                st.dataframe(paper["trades"], hide_index=True, use_container_width=True)

    with st.expander("How the rule did in the past"):
        result = rotation.simulate(prepared, holdings)
        summary, by_year = rotation.summarise(result, nifty)
        st.caption(f"{summary['period_start']} to {summary['period_end']}, after charges, "
                   f"starting with Rs {result['capital']:,.0f}.")
        one, two, three, four = st.columns(4)
        one.metric("Growth per year", pct(summary["annual_growth_rate"]),
                   f"Nifty {pct(summary['benchmark_annual_growth_rate'])}", delta_color="off")
        two.metric("Worst drawdown", pct(summary["max_drawdown"]),
                   f"Nifty {pct(summary['benchmark_max_drawdown'])}", delta_color="off")
        three.metric("Trades", summary["trades"],
                     f"{pct(summary['win_rate'], signed=False)} won", delta_color="off")
        four.metric("Charges paid", f"Rs {summary['total_charges']:,.0f}")
        st.warning(
            "A lead, not a proven system. The history is under five years, the three "
            "ingredients were chosen after looking at this same period, and companies "
            "delisted since 2022 are missing from the prices.", icon="⚠️")
        show(charts.growth_chart(result["equity"],
                                 nifty["Close"].reindex(result["equity"].index).dropna(),
                                 result["capital"]))
        show(charts.drawdown_chart(result["equity"]))
        show(charts.yearly_bars(by_year))
        st.dataframe(result["trades"], hide_index=True, use_container_width=True)


# ---------------------------------------------------------------- start -----
PAGES = {"Ownership rotation": rotation_page, "Market": market_page,
         "Company": company_page, "Shortlist": shortlist_page, "Backtest": backtest_page}

if load_nifty() is None or not load_stocks():
    st.title("India Trading System")
    st.error("No data found. In the terminal run:  python update_data.py")
    st.stop()

st.sidebar.title("India Trading System")
if "go_to_page" in st.session_state:          # set by the button on the shortlist page
    st.session_state["page"] = st.session_state.pop("go_to_page")
page = st.sidebar.radio("Page", list(PAGES), key="page")
st.sidebar.divider()
st.sidebar.caption(f"Prices up to **{load_nifty().index[-1].date()}**")
age = update.company_data_age_days()
st.sidebar.caption("Company results: not downloaded yet" if age is None
                   else f"Company results: {age:.0f} days old (refreshed weekly)")

force = st.sidebar.checkbox("Also refresh company results and shareholding now",
                            help="These refresh by themselves once a week. Ticking this "
                                 "adds several minutes.")
if st.sidebar.button("Update data now", type="primary"):
    bar = st.sidebar.progress(0.0, text="Starting ...")

    def show_progress(step, done, total):
        bar.progress(min(1.0, done / total), text=f"{step}: {done} of {total}")

    try:
        summary = update.run_update(include_company_data=True if force else None,
                                    report=show_progress)
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

if st.sidebar.button("Reload data from disk",
                     help="Use this after running update_data.py in the terminal."):
    st.cache_resource.clear()
    st.rerun()

if "update_note" in st.session_state:
    st.sidebar.info(st.session_state.pop("update_note"))
st.sidebar.caption("Updating downloads the latest prices. Do it once a day after the "
                   "market closes. It takes a few minutes.")

PAGES[page]()
