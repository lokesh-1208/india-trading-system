"""Daily report: market dashboard, account status and the shortlist.

Run it after the market closes (or before it opens). It tells you which
stocks passed the rules at the last close and gives, for each one, the price
to buy above, the stop-loss, the target and the exact quantity.
"""

import pandas as pd

import config
from trading import data, fundamentals, indicators, strategy
from trading.screens import Screens

JOURNAL_COLUMNS = [
    "symbol", "entry_date", "entry_price", "quantity", "stop", "target",
    "exit_date", "exit_price",
]


# --------------------------------------------------------------- dashboard --
def market_dashboard():
    """Last close and one-day change for Nifty, India VIX and global markets."""
    rows = []
    for name in config.MARKET_SYMBOLS:
        table = data.load_market(name)
        if table is None or len(table) < 2:
            continue
        last, previous = table["Close"].iloc[-1], table["Close"].iloc[-2]
        rows.append({
            "market": name,
            "date": table.index[-1].date(),
            "close": round(float(last), 2),
            "change_%": round(float(last / previous - 1) * 100, 2),
        })
    return pd.DataFrame(rows, columns=["market", "date", "close", "change_%"])


# ----------------------------------------------------------------- journal --
def load_journal():
    """Read your trade journal. Creates an empty one the first time."""
    path = config.JOURNAL_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=JOURNAL_COLUMNS).to_csv(path, index=False)
    journal = pd.read_csv(path)
    for column in ["entry_price", "quantity", "exit_price"]:
        journal[column] = pd.to_numeric(journal[column], errors="coerce")
    return journal


def account_status(journal, capital=None):
    """Work out equity, cash, open positions and whether trading is allowed."""
    capital = config.CAPITAL if capital is None else capital
    closed = journal[journal["exit_price"].notna()].copy()
    open_trades = journal[journal["exit_price"].isna() & journal["entry_price"].notna()]

    closed["profit"] = (closed["exit_price"] - closed["entry_price"]) * closed["quantity"]
    closed = closed.sort_values("exit_date")
    equity_after_each_trade = capital + closed["profit"].cumsum()

    equity = float(equity_after_each_trade.iloc[-1]) if len(closed) else float(capital)
    peak = max(float(capital), float(equity_after_each_trade.max())) if len(closed) else float(capital)
    drawdown = equity / peak - 1

    invested = float((open_trades["entry_price"] * open_trades["quantity"]).sum())
    return {
        "equity": equity,
        "cash": equity - invested,
        "drawdown": drawdown,
        "open_symbols": list(open_trades["symbol"]),
        "free_slots": max(0, config.MAX_POSITIONS - len(open_trades)),
        "blocked_by_drawdown": drawdown <= -config.TOTAL_DRAWDOWN_LIMIT,
    }


# --------------------------------------------------------------- shortlist --
def _percent(value):
    """0.123 -> 12.3, and nothing for a missing value."""
    return None if value is None or pd.isna(value) else round(float(value) * 100, 1)


def _number(value, digits=1):
    return None if value is None or pd.isna(value) else round(float(value), digits)


def build_shortlist(stocks, nifty, account, screens):
    """Every stock that gave a signal at the last close, strongest first.

    Returns (shortlist table, counts of stocks removed by each check).
    """
    last_day = nifty.index[-1]
    results_dates = screens.results or {}

    rows = []
    removed = {"quality": 0, "results": 0}
    for symbol, prices in stocks.items():
        if prices.index[-1] != last_day or symbol in account["open_symbols"]:
            continue  # no fresh data for this stock, or you already hold it
        table = screens.add_indicators(symbol, prices, nifty["Close"])
        today = table.iloc[-1]
        if not bool(today["price_signal"]):
            continue
        if not bool(today["quality_ok"]):
            removed["quality"] += 1
            continue
        if bool(today["near_results"]):
            removed["results"] += 1
            continue

        buy_above = float(today["High"])
        stop, target = strategy.stop_and_target(buy_above, float(today["atr"]))
        quantity = strategy.position_size(
            account["equity"], buy_above, stop, account["cash"]
        )
        if quantity < 1:
            continue  # one share already costs or risks more than the limits allow

        company = fundamentals.latest_snapshot(
            screens.company_rows(symbol), close=float(today["Close"]), as_of=last_day
        ) or {}
        upcoming = [day for day in results_dates.get(symbol, []) if day > last_day]
        rows.append({
            "symbol": symbol,
            "industry": screens.industry.get(symbol, ""),
            "close": round(float(today["Close"]), 2),
            "buy_above": round(buy_above, 2),
            "stop_loss": round(stop, 2),
            "target": round(target, 2),
            "quantity": quantity,
            "capital_needed": round(quantity * buy_above),
            "risk_rupees": round(quantity * (buy_above - stop)),
            "rsi": round(float(today["rsi"]), 1),
            "volume_x": round(float(today["volume_ratio"]), 2),
            "vs_nifty_3m_%": round(float(today["relative_strength"]) * 100, 1),
            "sales_growth_%": _percent(company.get("sales_growth")),
            "profit_growth_%": _percent(company.get("profit_growth")),
            "roe_%": _percent(company.get("return_on_equity")),
            "debt_to_equity": _number(company.get("debt_to_equity"), 2),
            "pe": _number(company.get("pe")),
            "next_results": min(upcoming).date() if upcoming else None,
        })

    columns = [
        "symbol", "industry", "close", "buy_above", "stop_loss", "target",
        "quantity", "capital_needed", "risk_rupees", "rsi", "volume_x",
        "vs_nifty_3m_%", "sales_growth_%", "profit_growth_%", "roe_%",
        "debt_to_equity", "pe", "next_results",
    ]
    shortlist = pd.DataFrame(rows, columns=columns)
    shortlist = shortlist.sort_values("vs_nifty_3m_%", ascending=False)
    return shortlist.reset_index(drop=True), removed


# ------------------------------------------------------------------- report -
def build_report(today=None):
    """Assemble the whole report. Returns (text, shortlist table)."""
    nifty = data.load_market(config.BENCHMARK)
    if nifty is None or len(nifty) == 0:
        raise SystemExit("No Nifty data found. Run:  python update_data.py")
    stocks = data.load_all_stocks()
    if not stocks:
        raise SystemExit("No stock data found. Run:  python update_data.py")

    today = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today)
    last_day = nifty.index[-1]
    age_days = (today - last_day).days

    nifty_trend = indicators.ema(nifty["Close"], config.MARKET_EMA).iloc[-1]
    nifty_close = nifty["Close"].iloc[-1]
    market_ok = bool(nifty_close > nifty_trend)

    account = account_status(load_journal())
    screens = Screens()
    shortlist, removed = build_shortlist(stocks, nifty, account, screens)

    allowed = market_ok and not account["blocked_by_drawdown"]
    slots = account["free_slots"] if allowed else 0
    shortlist.insert(0, "action", ["TRADE" if i < slots else "watch"
                                   for i in range(len(shortlist))])

    lines = [f"DAILY REPORT - signals from the close of {last_day.date()}", ""]
    if age_days > 4:
        lines += [f"WARNING: the data is {age_days} days old. Run:  python update_data.py", ""]

    lines += ["MARKET DASHBOARD", market_dashboard().to_string(index=False), ""]
    lines.append(
        f"Market filter: Nifty {nifty_close:,.0f} is "
        f"{'ABOVE' if market_ok else 'BELOW'} its {config.MARKET_EMA}-day EMA "
        f"({nifty_trend:,.0f}) -> new trades {'ALLOWED' if market_ok else 'NOT ALLOWED'}"
    )
    lines += [
        "",
        "ACCOUNT (from journal/trades.csv)",
        f"Equity Rs {account['equity']:,.0f} | cash Rs {account['cash']:,.0f} | "
        f"drawdown {account['drawdown'] * 100:.1f}% | "
        f"open positions {len(account['open_symbols'])} of {config.MAX_POSITIONS}",
    ]
    if account["open_symbols"]:
        lines.append("Holding: " + ", ".join(account["open_symbols"]))
    if account["blocked_by_drawdown"]:
        lines.append(
            f"STOP: drawdown limit of {config.TOTAL_DRAWDOWN_LIMIT:.0%} reached. "
            f"No new trades. Go back to testing."
        )

    lines += ["", f"SHORTLIST ({len(shortlist)} stocks passed the rules)"]
    if screens.annual is None:
        lines.append("Company fundamentals not downloaded, so the quality filter is off.")
    else:
        lines.append(
            f"Removed after passing the price rules: {removed['quality']} by the "
            f"quality filter, {removed['results']} because results are due within "
            f"{config.RESULTS_BLOCK_DAYS} days."
        )
    if len(shortlist) == 0:
        lines.append("Nothing passed the rules. No trade is also a decision.")
    else:
        trade_columns = list(shortlist.columns[:13])
        company_columns = ["symbol"] + list(shortlist.columns[13:])
        lines += ["", "Trade plan", shortlist[trade_columns].to_string(index=False)]
        lines += ["", "The business behind each stock (last full financial year)",
                  shortlist[company_columns].to_string(index=False, na_rep="-")]
        lines += [
            "",
            "How to use: for a TRADE row, place a buy only if price goes above",
            "buy_above. Use the quantity shown. Place the stop-loss immediately.",
            "'watch' rows are for information only (no free slot, or trading is",
            "not allowed today).",
        ]
    return "\n".join(lines), shortlist


def save_report(text, shortlist, last_day_label):
    """Save the report as a text file and the shortlist as a CSV."""
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    text_path = config.REPORTS_DIR / f"daily_{last_day_label}.txt"
    csv_path = config.REPORTS_DIR / f"daily_{last_day_label}.csv"
    text_path.write_text(text + "\n", encoding="utf-8")
    shortlist.to_csv(csv_path, index=False)
    return text_path, csv_path
