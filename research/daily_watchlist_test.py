"""Daily buying, the growing weekly watchlist, and a "leader" check (5 Nov 2026).

Asked by Lokesh after the first month of live lists trailed Nifty: buy on any day
instead of only Monday, from a watchlist that grows through the week, and make the
model pick stocks that are actually leading the market.

Variants (all E swing rules otherwise: 5 stocks, buy up to 2% above the signal close,
no buys within 5 days of results, 2 closes below the 20-day EMA or 8% down to sell,
75% amounts in a caution market, risk sizing):
  weekly      the rule in use: buy only on the first trading day of the week, top 10
  daily       every day, from that day's top 10
  watchlist   every day, from the week's watchlist: each day's top 10 added as the week
              goes on, plus last week's 10 best (re-ranked on Friday's close), bought in
              order of the latest score
  + leader    only stocks beating Nifty over the last 3 months (63 trading days)
  + 7/3       the list is the model's best 7 plus the 3 strongest leaders (also 8/2, 6/4)

Run from the project folder:  python research/daily_watchlist_test.py
Output: reports/daily_watchlist_test.txt (rows also in reports/daily_watchlist_test.csv)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import numpy as np
import pandas as pd

import config
from trading import data, model, rotation

LEAD_DAYS = 63
PERIODS = [("2018-22", "2018-02-01", "2022-01-31"),
           ("2022-24", "2022-02-01", "2024-03-31"),
           ("2024-26", "2024-04-01", None)]
OUT = Path(__file__).resolve().parent.parent / "reports" / "daily_watchlist_test.txt"

started = time.time()
ARGS = sys.argv[1:]
CACHE = ARGS[ARGS.index("--cache") + 1] if "--cache" in ARGS else None
if CACHE:
    # A model built and scored earlier (pickle files), to run the test in short pieces.
    import glob
    import pickle
    built, nifty_cut = pickle.load(open(Path(CACHE) / "built.pkl", "rb"))
    for shard in sorted(glob.glob(str(Path(CACHE) / "s*.pkl"))):
        built._cache.update(pickle.load(open(shard, "rb")))
    nifty = data.load_market(config.BENCHMARK)
else:
    stocks = data.load_all_stocks()
    nifty = data.load_market(config.BENCHMARK)
    built = model.from_disk(stocks, nifty)
    nifty_cut = model.up_to_last_close(nifty, stocks)
calendar = built.calendar
close = built.prepared["last_close"]
index = nifty_cut["Close"].reindex(calendar).ffill()
# Lead: the stock's 3-month change minus Nifty's 3-month change.
lead = (close / close.shift(LEAD_DAYS) - 1).sub(index / index.shift(LEAD_DAYS) - 1, axis=0)
in_trend = built.trading["in_trend"]
liquid = built.prepared["liquid"]
week_of = [tuple(day.isocalendar()[:2]) for day in calendar]
print(f"Model prepared in {time.time() - started:.0f} s", flush=True)


def eligible(position, ranked, scores):
    """Ranked stocks that the daily list would show: above the line, no results due."""
    blocked = rotation._blocked(scores)
    trend = in_trend.iloc[position]
    return [s for s in ranked if s not in blocked and bool(trend.get(s, False))]


def leaders(position, scores, count, skip=()):
    """The strongest stocks against Nifty that pass the daily-list checks."""
    blocked = rotation._blocked(scores)
    row = lead.iloc[position]
    ok = liquid.iloc[position] & in_trend.iloc[position]
    pool = row[ok.reindex(row.index).fillna(False).astype(bool)].dropna()
    pool = pool[[s for s in pool.index if s in scores.index and s not in blocked
                 and s not in skip]]
    return list(pool.sort_values(ascending=False).index[:count])


def leading(position, symbols):
    row = lead.iloc[position]
    return [s for s in symbols if row.get(s, np.nan) > 0]


def day_list(position, ranked, scores, model_count=10, leader_count=0, lead_filter=False):
    """One day's list of up to 10, the way the variant builds it."""
    names = eligible(position, ranked, scores)
    if lead_filter:
        names = leading(position, names)
    names = names[:model_count]
    if leader_count:
        names = names + leaders(position, scores, leader_count, skip=names)
    return names


def blended(position, ranked, scores, weight):
    """Re-rank: weight x the model's score rank + (1 - weight) x the lead rank."""
    row = lead.iloc[position].reindex(ranked)
    model_rank = pd.Series(np.linspace(1, 0, len(ranked)), index=ranked)
    lead_rank = row.rank(pct=True).fillna(0.5)
    mixed = weight * model_rank + (1 - weight) * lead_rank
    return list(mixed.sort_values(ascending=False, kind="stable").index)


def interleaved(position, ranked, scores, model_count, leader_count):
    """Model and leaders taking turns, so leaders get real places (e.g. 7/3: M M L M M L ...)."""
    picks = day_list(position, ranked, scores, model_count, 0)
    lead_names = leaders(position, scores, leader_count, skip=picks)
    out, step = [], max(1, round(model_count / max(leader_count, 1)))
    while picks or lead_names:
        out += picks[:step]
        picks = picks[step:]
        if lead_names:
            out.append(lead_names.pop(0))
    return out


def make_picker(mode, model_count=10, leader_count=0, lead_filter=False, weight=None,
                turns=False):
    """A pick_list function for rotation.simulate."""
    state = {"week": None, "carry": [], "pool": []}

    def pick(position, ranked, scores):
        if weight is not None:
            ranked = blended(position, ranked, scores, weight)
        if turns:
            today = interleaved(position, ranked, scores, model_count, leader_count)
        else:
            today = day_list(position, ranked, scores, model_count, leader_count, lead_filter)
        if mode in ("daily", "weekly"):
            return today
        week = week_of[position + 1] if position + 1 < len(calendar) else None
        if week != state["week"]:
            # A new week: re-rank last week's pool on this close, keep the best 10.
            order = {s: i for i, s in enumerate(ranked)}
            ranked_pool = sorted(state["pool"], key=lambda s: order.get(s, 10 ** 9))
            state["carry"] = [s for s in ranked_pool if s in order][:10]
            state["pool"] = list(state["carry"])
            state["week"] = week
        for symbol in today:
            if symbol not in state["pool"]:
                state["pool"].append(symbol)
        # Buy in order of the latest score; the checks in simulate do the rest.
        order = {s: i for i, s in enumerate(ranked)}
        pool = sorted(state["pool"], key=lambda s: order.get(s, 10 ** 9))
        if lead_filter:
            pool = leading(position, pool)
        return pool

    pick.weekly = mode == "weekly"
    return pick


def run(name, start, end, picker=None):
    entry = {} if picker is None else {"pick_list": picker}
    if picker is not None and not getattr(picker, "weekly", False):
        entry["check"] = "day"
    result = built.simulate(start=start, end=end, style="swing", **entry)
    summary, _ = rotation.summarise(result, nifty)
    trades = result["trades"]
    held = ((pd.to_datetime(trades["exit_date"]) - pd.to_datetime(trades["entry_date"]))
            .dt.days.median() if len(trades) else np.nan)
    return {"variant": name, "growth": summary["annual_growth_rate"],
            "worst": summary["max_drawdown"], "trades": summary["trades"],
            "won": summary["win_rate"], "charges": summary["total_charges"],
            "held_days": held, "nifty": summary["benchmark_annual_growth_rate"],
            "nifty_worst": summary["benchmark_max_drawdown"]}


VARIANTS = [
    ("weekly (now)", None),
    ("daily", lambda: make_picker("daily")),
    ("watchlist", lambda: make_picker("watchlist")),
    ("daily + leader", lambda: make_picker("daily", lead_filter=True)),
    ("watchlist + leader", lambda: make_picker("watchlist", lead_filter=True)),
    ("daily 7/3", lambda: make_picker("daily", 7, 3)),
    ("watchlist 7/3", lambda: make_picker("watchlist", 7, 3)),
    ("watchlist 8/2", lambda: make_picker("watchlist", 8, 2)),
    ("watchlist 6/4", lambda: make_picker("watchlist", 6, 4)),
    ("watchlist 7/3 + leader", lambda: make_picker("watchlist", 7, 3, lead_filter=True)),
    # Leaders that really get places: taking turns with the model's picks, or blended
    # into the ranking (the model's rank and the lead rank, weighted).
    ("weekly + leader", lambda: make_picker("weekly", lead_filter=True)),
    ("weekly 7/3 turns", lambda: make_picker("weekly", 7, 3, turns=True)),
    ("daily 7/3 turns", lambda: make_picker("daily", 7, 3, turns=True)),
    ("watchlist 7/3 turns", lambda: make_picker("watchlist", 7, 3, turns=True)),
    ("weekly blend 80/20", lambda: make_picker("weekly", weight=0.8)),
    ("weekly blend 70/30", lambda: make_picker("weekly", weight=0.7)),
    ("weekly blend 60/40", lambda: make_picker("weekly", weight=0.6)),
    ("daily blend 70/30", lambda: make_picker("daily", weight=0.7)),
    ("watchlist blend 70/30", lambda: make_picker("watchlist", weight=0.7)),
    ("weekly (picker check)", lambda: make_picker("weekly")),
]

ROWS = OUT.with_suffix(".csv")


def report():
    table = pd.read_csv(ROWS).drop_duplicates(["period", "variant"], keep="last")
    lines = [f"Daily watchlist test, run {pd.Timestamp.now():%d %b %Y %H:%M}, data to "
             f"{calendar[-1]:%d %b %Y}. Growth a year / worst fall, after charges.", ""]
    lines.append(f"{'':24s} " + "   ".join(f"{p:^17s}" for p, _, _ in PERIODS))
    cell = {(r.period, r.variant): r for r in table.itertuples()}
    for name, _ in VARIANTS:
        parts = []
        for p, _, _ in PERIODS:
            r = cell.get((p, name))
            parts.append(f"{r.growth:+6.1%} / {r.worst:6.1%}" if r else f"{'-':^17s}")
        lines.append(f"{name:24s} " + "   ".join(parts))
    nif = table.groupby("period")[["nifty", "nifty_worst"]].first()
    lines.append(f"{'Nifty 50':24s} " + "   ".join(
        f"{nif.loc[p, 'nifty']:+6.1%} / {nif.loc[p, 'nifty_worst']:6.1%}"
        if p in nif.index else f"{'-':^17s}" for p, _, _ in PERIODS))
    lines += ["", "Trades, win rate, median days held, charges (Rs):", ""]
    order = {name: i for i, (name, _) in enumerate(VARIANTS)}
    table["o"] = table["variant"].map(order)
    table = table.sort_values(["period", "o"])
    lines.append(table[["period", "variant", "trades", "won", "held_days", "charges"]]
                 .round({"won": 2, "held_days": 0, "charges": 0}).to_string(index=False))
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if "--report" in ARGS:
    report()
    sys.exit()
periods = ARGS[ARGS.index("--period") + 1].split(",") if "--period" in ARGS else \
    [p for p, _, _ in PERIODS]
names = ARGS[ARGS.index("--variants") + 1].split(",") if "--variants" in ARGS else None
for label, start, end in PERIODS:
    if label not in periods:
        continue
    for number, (name, factory) in enumerate(VARIANTS):
        if names is not None and str(number) not in names:
            continue
        t = time.time()
        row = run(name, start, end, None if factory is None else factory())
        row["period"] = label
        pd.DataFrame([row]).to_csv(ROWS, mode="a", header=not ROWS.exists(), index=False)
        print(f"{label} {name:24s} {row['growth']:+.1%} / {row['worst']:.1%} "
              f"trades {row['trades']} ({time.time() - t:.0f} s)", flush=True)
if not CACHE:
    report()
