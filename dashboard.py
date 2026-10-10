"""The dashboard: everything the system knows, as charts in your browser.

Run:  streamlit run dashboard.py
It reads the files that update_data.py downloaded, so run that first.
"""

import pandas as pd
import streamlit as st

import config
from trading import backtest, charts, company, data, indicators, report
from trading.screens import Screens

st.set_page_config(page_title="India Trading System", layout="wide")

PERIODS = {"6 months": 126, "1 year": 252, "3 years": 756, "All": None}


# ------------------------------------------------------------ loading -------
# Streamlit re-runs this file on every click. The cache keeps the slow steps
# (reading 800 files, working out the shortlist) from being repeated.
@st.cache_data(show_spinner="Reading price files ...")
def load_stocks():
    return data.load_all_stocks()


@st.cache_data
def load_nifty():
    return data.load_market(config.BENCHMARK)


@st.cache_resource(show_spinner="Reading company data ...")
def load_screens():
    screens = Screens()
    screens.learn_industry_pe(load_stocks())
    return screens


@st.cache_data(show_spinner="Working out today's shortlist ...")
def load_shortlist():
    account = report.account_status(report.load_journal())
    shortlist, removed = report.build_shortlist(
        load_stocks(), load_nifty(), account, load_screens()
    )
    return shortlist, removed, account


@st.cache_data(show_spinner="Running the backtest, about half a minute ...")
def run_backtest_now():
    nifty, screens = load_nifty(), load_screens()
    stocks = {symbol: screens.add_indicators(symbol, prices, nifty["Close"])
              for symbol, prices in load_stocks().items()}
    result = backtest.run_backtest(stocks, nifty)
    return result["equity"], result["trades"]


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


# ---------------------------------------------------------------- start -----
PAGES = {"Market": market_page, "Shortlist": shortlist_page,
         "Company": company_page, "Backtest": backtest_page}

if load_nifty() is None or not load_stocks():
    st.title("India Trading System")
    st.error("No data found. In the terminal run:  python update_data.py")
    st.stop()

st.sidebar.title("India Trading System")
if "go_to_page" in st.session_state:          # set by the button on the shortlist page
    st.session_state["page"] = st.session_state.pop("go_to_page")
page = st.sidebar.radio("Page", list(PAGES), key="page")
st.sidebar.caption("To refresh the data, run `python update_data.py` in the terminal, "
                   "then press R here.")
if st.sidebar.button("Reload data from disk"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()
PAGES[page]()
