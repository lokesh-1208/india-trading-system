"""Reading the news: is an announcement good or bad for the share price?

This is NOT part of the tested model. It reads each company announcement with
simple rules (an order win is good, a fraud or an auditor quitting is bad, a
credit rating upgrade is good, and so on), checks the results numbers when a
company declares results, and puts that next to the model's view of the stock
and how the price has reacted.

From that it makes two idea lists:
  - possible buys:  good news, and the model does not dislike the stock
  - possible exits: bad news on a stock you hold, on this week's list, or that
                    the model already rates weak

It also measures how stocks moved in the past after each kind of news, from
the saved announcements and prices (a year of them). Where there are enough
past cases, that history decides whether a kind of news counts as good or bad,
not the rule: for example, if order wins have not moved prices on average,
an order win alone does not make an idea. Every idea shows "what usually
happened next". These are ideas, not tested rules.
"""

import hashlib
import io
import logging
import re

import numpy as np
import pandas as pd

import config

# (category or None for any, words to look for, lean, label). The first match wins.
# Lean: +2 clearly good, +1 good, 0 neutral, -1 bad, -2 clearly bad.
RULES = [
    # These two are only found in the filing PDF, which is opened for serious labels:
    # a bank telling RBI that a BORROWER's account is a fraud is routine for banks,
    # and a supplier's insolvency claim is a dispute, not the company going bust.
    ("Legal and regulatory", r"declared as fraud|classified as fraud|reported to rbi|"
                             r"borrower account", 0, "Bank reported a borrower's fraud (routine)"),
    ("Legal and regulatory", r"operational creditor", -1,
     "Insolvency claim by a supplier (a dispute)"),
    ("Legal and regulatory", r"fraud|default|arrest|insolvency|cirp|nclt|winding up|"
                             r"search|seizure|raid|forensic", -2, "Fraud, default or insolvency"),
    ("Legal and regulatory", r"penalt|fine\b|show cause|tax demand|demand order|"
                             r"suspension|cancellation|withdrawal of licen", -1,
     "Penalty, tax demand or licence problem"),
    ("Legal and regulatory", r"news verification|rumour|clarification|spurt in volume", 0,
     "Exchange asked about news or a volume spike"),
    ("Legal and regulatory", r"litigation|dispute", -1, "Court case or dispute"),
    ("Management change", r"auditor.*(resign|cessation)|(resign|cessation).*auditor", -2,
     "Auditor quit"),
    ("Management change", r"(resign|cessation).*(managing director|ceo|chief executive|"
                          r"\bmd\b|cfo|chief financial)|(managing director|ceo|chief executive|"
                          r"\bmd\b|cfo|chief financial).*(resign|cessation)", -1,
     "Top manager (MD, CEO or CFO) quit"),
    ("Management change", r"resign|cessation", 0, "Director or officer left"),
    ("Management change", r"appoint", 0, "New appointment"),
    ("Credit rating", r"upgrade|positive outlook|outlook.*positive|raised", 1,
     "Credit rating upgraded"),
    ("Credit rating", r"downgrade|negative outlook|outlook.*negative|watch.*negative|"
                      r"lowered|suspended", -1, "Credit rating downgraded"),
    ("Credit rating", r"", 0, "Credit rating update"),
    ("Orders and contracts", r"", 1, "Order or contract win"),
    ("Dividend and bonus", r"bonus|split|sub-division", 1, "Bonus or share split"),
    ("Dividend and bonus", r"", 0, "Dividend"),
    ("Raising money", r"buy ?back", 1, "Share buyback"),
    ("Raising money", r"commercial paper|debenture|\bncd|bond", 0,
     "Raising money by loans or bonds"),
    ("Raising money", r"qualified institution|qip|preferential|rights issue|"
                      r"issue of (equity|securities)", -1, "Raising money by new shares (dilution)"),
    ("Raising money", r"", 0, "Raising money by loans or bonds"),
    ("Deals", r"open offer|takeover", 1, "Open offer or takeover"),
    ("Deals", r"sale or disposal|disinvest|slump sale", 0, "Selling a business"),
    ("Deals", r"", 0, "Acquisition, merger or tie-up"),
    ("Business update", r"capacity|expansion|commenc|new plant|commission|launch", 1,
     "New capacity or launch"),
]

RESULT_GROUPS = {2: "Results: much better than a year ago", 1: "Results: better than a year ago",
                 0: "Results: about the same as a year ago", -1: "Results: worse than a year ago",
                 -2: "Results: much worse, or a loss"}


def lean_word(lean):
    return "good" if lean > 0 else "bad" if lean < 0 else "neutral"


def read(category, text):
    """(lean, label) for one announcement from its category and text."""
    text = str(text or "").lower()
    for rule_category, words, lean, label in RULES:
        if rule_category is not None and rule_category != category:
            continue
        if not words or re.search(words, text):
            return lean, label
    return 0, ""


# ------------------------------------------------------------ results -------
def results_lean(symbol, when, quarterly):
    """(lean, label) from the newest quarter that ended in the 100 days before `when`.

    Profit up more than config.NEWS_RESULTS_GOOD over the same quarter a year
    earlier counts as good, down more than that as bad.
    """
    if quarterly is None or len(quarterly) == 0:
        return 0, "Results declared (numbers not read yet)"
    rows = quarterly[quarterly["symbol"] == symbol].sort_values("period_end")
    recent = rows[(rows["period_end"] < when)
                  & (rows["period_end"] > when - pd.Timedelta(days=100))]
    if len(recent) == 0:
        return 0, "Results declared (numbers not read yet)"
    latest = recent.iloc[-1]
    year_ago = rows[(rows["period_end"] - (latest["period_end"] - pd.DateOffset(years=1)))
                    .abs() <= pd.Timedelta(days=10)]
    if len(year_ago) == 0 or pd.isna(latest["net_income"]):
        return 0, "Results declared (no year-ago quarter to compare)"
    before = float(year_ago.iloc[-1]["net_income"])
    now = float(latest["net_income"])
    if before == 0:
        return 0, "Results declared"
    growth = (now - before) / abs(before)
    sales = ""
    if pd.notna(latest.get("revenue")) and pd.notna(year_ago.iloc[-1].get("revenue")) \
            and year_ago.iloc[-1]["revenue"] > 0:
        sales = f", sales {latest['revenue'] / year_ago.iloc[-1]['revenue'] - 1:+.0%}"
    text = f"Results: profit {growth:+.0%} on a year ago{sales}"
    good = config.NEWS_RESULTS_GOOD
    if before < 0 < now:
        return 2, f"Results: back to profit{sales}"
    if now < 0 <= before:
        return -2, f"Results: fell into a loss{sales}"
    if growth >= 2 * good:
        return 2, text
    if growth >= good:
        return 1, text
    if growth <= -2 * good:
        return -2, text
    if growth <= -good:
        return -1, text
    return 0, text


# ------------------------------------------------------------- the PDF ------
def pdf_text(link, browser=None, folder=None, pages=2, download=True):
    """Text of the first pages of a filing PDF, saved so it is read only once.

    Returns "" when the PDF cannot be downloaded or read (pypdf missing, scanned
    image, network problem), or when download is False and it was not saved before.
    """
    if not link or not str(link).lower().endswith(".pdf"):
        return ""
    folder = config.NEWS_PDF_DIR if folder is None else folder
    saved = folder / (hashlib.md5(str(link).encode()).hexdigest() + ".txt")
    if saved.exists():
        return saved.read_text(encoding="utf-8")
    if not download:
        return ""
    try:
        from pypdf import PdfReader
        logging.getLogger("pypdf").setLevel(logging.ERROR)     # damaged PDFs are common
        if browser is None:
            from trading import nse
            browser = nse.session()
        answer = browser.get(link, timeout=30)
        if answer.status_code != 200:
            return ""
        reader = PdfReader(io.BytesIO(answer.content))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:pages])
        text = " ".join(text.split())[:6000]
    except Exception:
        return ""
    folder.mkdir(parents=True, exist_ok=True)
    saved.write_text(text, encoding="utf-8")
    return text


# Only these kinds are worth opening the PDF for: the title rarely says which way it went.
READ_PDF_FOR = {"Credit rating", "Legal and regulatory", "Management change"}
# The PDF is also opened for the most serious label, which titles often overstate.
CHECK_PDF_LABELS = {"Fraud, default or insolvency"}


def needs_pdf(category, text):
    """Is the filing PDF worth opening for this announcement?"""
    if category not in READ_PDF_FOR:
        return False
    lean, label = read(category, text)
    return lean == 0 or label in CHECK_PDF_LABELS


def fetch_pdfs(news_table, days=10, browser=None, limit=60):
    """Save the PDFs of recent announcements whose title is unclear or overstated.

    Run by the updates, so the pages can read the saved text without waiting for
    downloads. Returns how many were read.
    """
    if news_table is None or len(news_table) == 0:
        return 0
    since = news_table["time"].max() - pd.Timedelta(days=days)
    recent = news_table[news_table["time"] >= since].sort_values("time", ascending=False)
    count = 0
    for row in recent.itertuples():
        if count >= limit:
            break
        if needs_pdf(row.category, f"{row.subject} {row.detail}"):
            if pdf_text(row.link, browser):
                count += 1
    return count


# ------------------------------------------------------------ all news -------
def read_all(news_table, deals=None, quarterly=None, since=None, read_pdfs=False,
             browser=None):
    """Every important announcement (and bulk/block deal) since `since`, read.

    Returns a table: time, symbol, kind, lean, group (the kind of news, for the
    history), label (what it says, in a few words), what, link.
    """
    columns = ["time", "symbol", "kind", "lean", "group", "label", "what", "link"]
    rows = []
    if news_table is not None and len(news_table) > 0:
        table = news_table[news_table["category"] != "Routine"]
        if since is not None:
            table = table[table["time"] >= since]
        for row in table.itertuples():
            text = f"{row.subject} {row.detail}"
            if row.category == "Results":
                if not re.search(r"result", text, re.IGNORECASE):
                    continue                     # a board meeting about something else
                if re.search(r"intimation|to be held|will be held|to consider", text,
                             re.IGNORECASE):
                    continue                     # only announces the date
                lean, label = results_lean(row.symbol, row.time, quarterly)
                group = RESULT_GROUPS[lean] if "numbers" not in label and "compare" not in label \
                    else "Results declared"
            else:
                lean, label = read(row.category, text)
                if read_pdfs and row.category in READ_PDF_FOR and (
                        lean == 0 or label in CHECK_PDF_LABELS):
                    # read_pdfs="saved": only PDFs an update already saved (no waiting)
                    extra = pdf_text(row.link, browser, download=read_pdfs != "saved")
                    if extra:
                        lean, label = read(row.category, text + " " + extra)
                group = label
            if not label:
                continue
            rows.append({"time": row.time, "symbol": row.symbol, "kind": row.category,
                         "lean": lean, "group": group, "label": label,
                         "what": row.detail or row.subject, "link": row.link})
    if deals is not None and len(deals) > 0:
        table = deals if since is None else deals[deals["date"] >= since.normalize()]
        for row in table.itertuples():
            value = row.quantity * row.price / 1e7
            if value < config.NEWS_DEAL_MIN_CRORE:
                continue
            buy = str(row.side).lower() == "buy"
            label = f"{row.kind} deal: big {'buyer' if buy else 'seller'}"
            rows.append({"time": row.date + pd.Timedelta(hours=16), "symbol": row.symbol,
                         "kind": "Bulk or block deal", "lean": 1 if buy else -1,
                         "group": label, "label": label,
                         "what": f"{row.client} {'bought' if buy else 'sold'} "
                                 f"Rs {value:,.0f} cr at Rs {row.price:,.2f}",
                         "link": ""})
    table = pd.DataFrame(rows, columns=columns)
    return table.sort_values("time", ascending=False).reset_index(drop=True)


# ------------------------------------------------------ what happened next ---
def base_day(moment, calendar):
    """The last trading day whose close came before the news was public."""
    moment = pd.Timestamp(moment)
    cutoff = moment.normalize() if moment.hour * 60 + moment.minute >= 15 * 60 + 30 \
        else moment.normalize() - pd.Timedelta(days=1)
    before = calendar[calendar <= cutoff]
    return before[-1] if len(before) else None


def past_reactions(read_table, closes, benchmark, days=None):
    """How stocks moved after each kind of news: from the close before the news to
    `days` trading days later, minus Nifty over the same days.

    closes: wide table of closing prices (date x symbol). Returns a table per
    kind of news (group): cases, average move %, share of cases that beat Nifty.
    """
    days = config.NEWS_REACTION_DAYS if days is None else days
    columns = ["group", "lean", "cases", "average_%", "beat_nifty_%"]
    if read_table is None or len(read_table) == 0:
        return pd.DataFrame(columns=columns)
    calendar = closes.index
    moves = []
    for row in read_table.itertuples():
        if row.symbol not in closes:
            continue
        start = base_day(row.time, calendar)
        if start is None:
            continue
        position = calendar.get_loc(start)
        if position + days >= len(calendar):
            continue                                  # too recent to know yet
        end = calendar[position + days]
        series = closes[row.symbol]
        first, last = series.get(start), series.get(end)
        if pd.isna(first) or pd.isna(last) or first <= 0:
            continue
        nifty = benchmark.get(end) / benchmark.get(start) - 1 \
            if start in benchmark.index and end in benchmark.index else 0.0
        moves.append({"group": row.group, "lean": row.lean,
                      "excess": (last / first - 1 - nifty) * 100})
    if not moves:
        return pd.DataFrame(columns=columns)
    table = pd.DataFrame(moves)
    grouped = table.groupby("group").agg(lean=("lean", "first"), cases=("excess", "size"),
                                         average=("excess", "mean"),
                                         beat=("excess", lambda v: (v > 0).mean() * 100))
    grouped = grouped.reset_index().rename(columns={"average": "average_%",
                                                    "beat": "beat_nifty_%"})
    grouped["average_%"] = grouped["average_%"].round(1)
    grouped["beat_nifty_%"] = grouped["beat_nifty_%"].round(0)
    return grouped[columns].sort_values("average_%", ascending=False).reset_index(drop=True)


def history_text(group, reactions):
    """One line: what usually happened after this kind of news."""
    if reactions is None or len(reactions) == 0:
        return "Not enough saved history yet"
    found = reactions[reactions["group"] == group]
    if len(found) == 0 or found.iloc[0]["cases"] < config.NEWS_MIN_CASES:
        cases = 0 if len(found) == 0 else int(found.iloc[0]["cases"])
        return f"Not enough past cases yet ({cases})"
    row = found.iloc[0]
    return (f"In the past: {row['average_%']:+.1f}% against Nifty over "
            f"{config.NEWS_REACTION_DAYS} days, beat Nifty {row['beat_nifty_%']:.0f}% of the "
            f"time ({int(row['cases'])} cases)")


def learned_lean(group, rule_lean, reactions):
    """The lean the past says this kind of news has, when there are enough cases.

    With at least 2 x config.NEWS_MIN_CASES past cases, the measured average move
    against Nifty decides: +/-0.5% or more is good/bad, +/-1.5% or more clearly
    so, anything smaller means this kind of news has not moved prices. With
    fewer cases the rule's own lean is kept.
    """
    if reactions is None or len(reactions) == 0:
        return rule_lean
    found = reactions[reactions["group"] == group]
    if len(found) == 0 or found.iloc[0]["cases"] < 2 * config.NEWS_MIN_CASES:
        return rule_lean
    average = float(found.iloc[0]["average_%"])
    if average >= 1.5:
        return 2
    if average >= 0.5:
        return 1
    if average <= -1.5:
        return -2
    if average <= -0.5:
        return -1
    return 0


# ---------------------------------------------------------------- ideas -----
def _move_since(closes, symbol, moment):
    if symbol not in closes:
        return np.nan
    series = closes[symbol].dropna()
    start = base_day(moment, series.index)
    if start is None or start == series.index[-1]:
        return np.nan
    return (series.iloc[-1] / series.loc[start] - 1) * 100


def ideas(read_table, ranking, in_trend, closes, trend_line, held=(), weekly=(),
          reactions=None, last_day=None, days=None):
    """Possible buys and possible exits from the news of the last few days.

    ranking: the model's score table for the latest day (index = symbol, has 'score').
    in_trend / trend_line: the latest day's values per symbol.
    Returns (buys, exits): tables with one row per stock.
    """
    days = config.NEWS_IDEA_DAYS if days is None else days
    columns = ["symbol", "time", "label", "lean", "what", "link", "move_since_%", "rank",
               "score", "view", "history", "idea", "agree"]
    empty = pd.DataFrame(columns=columns)
    if read_table is None or len(read_table) == 0:
        return empty, empty
    last_day = closes.index[-1] if last_day is None else pd.Timestamp(last_day)
    since = last_day - pd.Timedelta(days=days)
    recent = read_table[read_table["time"] > since].copy()
    recent["rule_lean"] = recent["lean"]
    # The past decides where it has enough cases: "what usually happened" beats a rule.
    recent["lean"] = [learned_lean(group, lean, reactions)
                      for group, lean in zip(recent["group"], recent["lean"])]
    recent = recent[recent["lean"] != 0]
    held, weekly = set(held), set(weekly)
    buys, exits = [], []
    for symbol, group in recent.groupby("symbol"):
        if symbol not in ranking.index:
            continue                       # only stocks the model scores (Nifty 500, traded)
        net = group["lean"].sum()
        main = group.reindex(group["lean"].abs().sort_values(ascending=False).index).iloc[0]
        if net == 0:
            continue
        rank = int(ranking.index.get_loc(symbol)) + 1 if symbol in ranking.index else None
        score = float(ranking.loc[symbol, "score"]) if symbol in ranking.index else np.nan
        trend_ok = bool(in_trend.get(symbol, False))
        line = float(trend_line.get(symbol, np.nan))
        if pd.isna(score):
            view = "not scored"
        elif score >= 60 and trend_ok:
            view = "strong"
        elif score <= 40:
            view = "weak"
        elif not trend_ok:
            view = "below trend"
        else:
            view = "neutral"
        move = _move_since(closes, symbol, main["time"])
        row = {"symbol": symbol, "time": main["time"], "label": main["label"],
               "lean": int(net), "what": main["what"], "link": main["link"],
               "move_since_%": None if pd.isna(move) else round(move, 1),
               "rank": rank, "score": None if pd.isna(score) else round(score),
               "view": view, "history": history_text(main["group"], reactions)}
        if main["rule_lean"] != 0 and (main["rule_lean"] > 0) != (main["lean"] > 0):
            row["history"] = ("Usually read as " + ("good" if main["rule_lean"] > 0 else "bad")
                              + " news, but the past says otherwise. " + row["history"])
        elif main["rule_lean"] == 0 and main["lean"] != 0:
            # Looks neutral (for example profit up only a little), but the past disagrees.
            row["history"] = ("Looks neutral, but in the past this kind of news was usually "
                              "followed by a " + ("rise" if main["lean"] > 0 else "fall")
                              + ". " + row["history"])
        if net > 0:
            if view == "weak":
                continue
            if not pd.isna(move) and move > config.NEWS_MAX_RUN_PCT:
                row["idea"] = f"Already up {move:.0f}% since the news: chasing is risky"
                row["agree"] = "late"
            elif view == "strong":
                row["idea"] = (f"Good news and the model likes it. If you want to enter: "
                               f"while it stays above Rs {line:,.2f} (20-day EMA)")
                row["agree"] = "yes"
            elif view == "below trend":
                row["idea"] = (f"Good news but the price is below its trend line. Wait for "
                               f"a close above Rs {line:,.2f}")
                row["agree"] = "wait"
            else:
                row["idea"] = (f"Good news, model neutral. Possible entry above "
                               f"Rs {line:,.2f} (20-day EMA)")
                row["agree"] = "partly"
            buys.append(row)
        else:
            mine = symbol in held
            listed = symbol in weekly
            if not (mine or listed or view in ("weak", "below trend")):
                if not (pd.notna(move) and move < -3):
                    continue
            who = ("You hold it: consider exiting" if mine else
                   "On this week's list: think twice before buying" if listed else
                   "Avoid for now")
            reason = ("the model already rates it weak" if view == "weak" else
                      "it is below its trend line" if view == "below trend" else
                      f"the price fell {abs(move):.0f}% since" if pd.notna(move) and move < 0
                      else "the model still rates it well, so watch the price")
            row["idea"] = f"{who}. Bad news and {reason}"
            row["agree"] = "yes" if view in ("weak", "below trend") else "partly"
            exits.append(row)

    def order(rows, best_first):
        if not rows:
            return empty
        table = pd.DataFrame(rows, columns=columns)
        rank_agree = {"yes": 0, "partly": 1, "wait": 2, "late": 3}
        table["_a"] = table["agree"].map(rank_agree)
        table["_l"] = table["lean"].abs()
        table = table.sort_values(["_a", "_l", "time"], ascending=[True, False, False])
        return table.drop(columns=["_a", "_l"]).reset_index(drop=True)

    return order(buys, True), order(exits, False)


# ------------------------------------------------------------- the test -----
# Result of research/news_ideas_test.py, run on 13 Oct 2026 over the year of saved
# announcements (20 Oct 2025 to 13 Oct 2026), with the model's exits and real charges.
IDEA_TEST_NOTE = (
    "Tested on one year (Oct 2025 to Oct 2026): buying these ideas lost 9.6% after charges "
    "(Nifty fell 12.1%), and only 23% of the trades made money. The weekly list made 55% in "
    "the same year. Selling a holding on bad news made no difference. So news ideas help you "
    "understand a move; they are not a reason to buy on their own.")

def idea_scorer(built, read_table, require_model=True):
    """A scorer for rotation.simulate that ranks only the news buy ideas of each day.

    The news is read with the fixed rules only (not with the history-based
    lean, which would use the future). An idea on a day: good news in the
    last config.NEWS_IDEA_DAYS days, up to that day's evening; the price not
    already up more than config.NEWS_MAX_RUN_PCT since; and, with
    require_model, a model score of 60 or more with the price above its
    20-day average.
    """
    calendar = built.calendar
    closes = built.prepared["last_close"]
    in_trend = built.trading["in_trend"]
    reading = read_table[read_table["lean"] != 0].copy()
    reading["time"] = pd.to_datetime(reading["time"])

    def scorer(position):
        day = calendar[position]
        since = day - pd.Timedelta(days=config.NEWS_IDEA_DAYS)
        recent = reading[(reading["time"] > since) & (reading["time"] < day + pd.Timedelta(days=1))]
        ranking = built.score_on(position)
        rows = []
        for symbol, group in recent.groupby("symbol"):
            net = int(group["lean"].sum())
            if net <= 0 or symbol not in ranking.index:
                continue
            score = float(ranking.loc[symbol, "score"])
            trend_ok = bool(in_trend.iloc[position].get(symbol, False))
            if require_model and not (score >= 60 and trend_ok):
                continue
            series = closes[symbol].iloc[:position + 1].dropna()
            first = group["time"].min()
            start = base_day(first, series.index)
            if start is not None and series.iloc[-1] / series.loc[start] - 1 \
                    > config.NEWS_MAX_RUN_PCT / 100:
                continue
            rows.append({"symbol": symbol, "score": score, "lean": net,
                         "no_new_buy": bool(ranking.loc[symbol].get("no_new_buy", False))})
        table = pd.DataFrame(rows, columns=["symbol", "score", "lean", "no_new_buy"])
        return table.sort_values(["lean", "score"], ascending=False).set_index("symbol")

    return scorer


def backtest_ideas(built, read_table, start, require_model=True, capital=None):
    """Trade the news buy ideas with the model's own exits and charges.

    Checked every day; up to the model's number of positions; bought at the
    next open (skipped if it opens more than the model's gap above the
    signal close); sold the day after a close below the 20-day average or
    at the stop-loss. Returns rotation.simulate's result.
    """
    from trading import rotation
    rules = config.MODEL_STYLES[config.MODEL_STYLE]
    return rotation.simulate(
        built.trading, None, start=start, capital=capital,
        scorer=idea_scorer(built, read_table, require_model), check="day",
        positions_wanted=rules["positions"], keep_rank=10 ** 9 + 1,
        stop_loss=rules["stop_loss"], trend_exit=True, buy_rank=rules["positions"] * 4,
        max_gap=rules.get("max_gap"))
