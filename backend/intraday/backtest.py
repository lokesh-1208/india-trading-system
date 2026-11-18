"""Backtest the intraday rules on the cached 5-minute candles.

Run from the backend folder:
    python -m intraday.backtest            # refresh data, then test
    python -m intraday.backtest --no-refresh
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd

from . import data, strategy
from . import settings as s


def _trend(daily, date):
    """+1 / -1 / 0 from daily closes BEFORE `date`: close vs 20-day average, and the average's slope."""
    if daily is None:
        return 0
    closes = daily[[d < date for d in daily.index]]
    if len(closes) < 26:
        return 0
    sma = closes.iloc[-20:].mean()
    sma_before = closes.iloc[-25:-5].mean()
    last = closes.iloc[-1]
    if last > sma and sma > sma_before:
        return 1
    if last < sma and sma < sma_before:
        return -1
    return 0


def build_days(symbols):
    """{symbol: {date: (day_df, prev_close, avg_or_volume, trend)}}, finished sessions only."""
    out = {}
    for sym in symbols:
        df = data.load(sym)
        if df is None or df.empty:
            continue
        daily = data.load_daily(sym)
        days, prev_close, or_vols = {}, None, []
        for date, day in df.groupby(df.index.date):
            first3 = [ix.strftime("%H:%M") for ix in day.index[:3]]
            if (len(day) < s.MIN_CANDLES or day.index[-1].strftime("%H:%M") < "15:20"
                    or first3 != ["09:15", "09:20", "09:25"]):
                prev_close = day["Close"].iloc[-1] if len(day) else prev_close
                continue                            # partial or short session
            avg = np.mean(or_vols[-20:]) if len(or_vols) >= 5 else None
            days[date] = (day, prev_close, avg, _trend(daily, date))
            or_vols.append(day["Volume"].iloc[:s.OR_CANDLES].sum())
            prev_close = day["Close"].iloc[-1]
        out[sym] = days
    return out


def run(all_days, top_n=None, mode="orb", use_trend=False, target_r=None, be_at_r=None,
        max_trades=None, min_rel_vol=0.0, rank="rel_vol", long_only=False,
        min_abs_gap=0.0, gap_dir=False, against_gap=False, short_only=False):
    max_trades = max_trades or s.MAX_TRADES_PER_DAY
    dates = sorted({d for v in all_days.values() for d in v})
    trades = []
    for date in dates:
        cands = []
        for sym, days in all_days.items():
            if date not in days:
                continue
            day, prev_close, avg, trend = days[date]
            feat = strategy.day_features(day, prev_close, avg)
            if feat["or_range_pct"] < s.MIN_OR_RANGE_PCT or np.isnan(feat["rel_vol"]):
                continue
            if feat["rel_vol"] < min_rel_vol or abs(feat["gap_pct"]) < min_abs_gap:
                continue
            if (use_trend or mode == "pullback") and trend == 0:
                continue
            cands.append((sym, day, feat, trend))
        key = (lambda c: c[2]["rel_vol"]) if rank == "rel_vol" else (lambda c: abs(c[2]["gap_pct"]))
        cands.sort(key=key, reverse=True)
        if top_n:
            cands = cands[:top_n]
        todays = []
        for sym, day, feat, trend in cands:
            if mode == "pullback":
                t = strategy.find_pullback(day, feat, sym, trend, target_r=target_r or 2.0, be_at_r=be_at_r)
            else:
                side = trend if use_trend else (1 if long_only else None)
                if gap_dir:
                    side = 1 if feat["gap_pct"] > 0 else -1
                if against_gap:
                    side = -1 if feat["gap_pct"] > 0 else 1
                if short_only:
                    side = -1
                t = strategy.find_trade(day, feat, sym, allowed_side=side, target_r=target_r, be_at_r=be_at_r)
            if t:
                todays.append(t)
        todays.sort(key=lambda t: t["entry_time"])
        taken = []
        for t in todays:
            realised = sum(x["net"] for x in taken if x["exit_time"] <= t["entry_time"])
            if len(taken) >= max_trades or realised <= -s.DAILY_LOSS_LIMIT:
                continue
            open_t = [x for x in taken if x["exit_time"] > t["entry_time"]]
            if sum(x["value"] for x in open_t) + t["value"] > s.CAPITAL * s.MARGIN_X:
                continue
            t["date"] = date
            taken.append(t)
        trades += taken
    return pd.DataFrame(trades)


def stats(trades):
    if trades.empty:
        return dict(n=0, net=0.0, pf=0.0, days=0)
    wins, losses = trades[trades.net > 0], trades[trades.net <= 0]
    pf = wins.net.sum() / abs(losses.net.sum()) if len(losses) and losses.net.sum() else float("inf")
    daily = trades.groupby("date")["net"].sum()
    return dict(n=len(trades), net=trades.net.sum(), pf=pf, days=daily.size)


def summarise(trades, label):
    if trades.empty:
        return f"{label}: no trades"
    daily = trades.groupby("date")["net"].sum()
    dd = (daily.cumsum() - daily.cumsum().cummax()).min()
    st = stats(trades)
    wins = (trades.net > 0).mean()
    reasons = trades.reason.value_counts().to_dict()
    return (f"{label}\n"
            f"  trades {st['n']} over {st['days']} days | win rate {wins:.0%} | exits {reasons}\n"
            f"  gross {trades.gross.sum():,.0f} | charges {trades.charges.sum():,.0f}"
            f" | NET {st['net']:,.0f} | avg net/trade {trades.net.mean():,.0f} | profit factor {st['pf']:.2f}\n"
            f"  avg net/day {daily.mean():,.0f} | best {daily.max():,.0f} | worst {daily.min():,.0f}"
            f" | max drawdown {dd:,.0f} | days >=500: {(daily>=500).mean():.0%} | losing days: {(daily<0).mean():.0%}")


# Declared BEFORE running. Pass = net > 0 after charges in BOTH halves, PF >= 1.2, >= 40 trades.
VARIANTS = [
    ("BASE   ORB 1.5R, both sides (first test)", dict(top_n=5)),
    ("A TRAIL  ORB 2R, stop to entry after +1R", dict(top_n=5, target_r=2.0, be_at_r=1.0)),
    ("B TREND  ORB 1.5R, only with daily trend", dict(top_n=5, use_trend=True)),
    ("C PULLBACK  VWAP pullback with trend, 2R", dict(top_n=5, mode="pullback", target_r=2.0)),
    ("D SELECTIVE  trend + 2R + breakeven, max 2 trades, rel vol >= 1.5",
     dict(top_n=5, use_trend=True, target_r=2.0, be_at_r=1.0, max_trades=2, min_rel_vol=1.5)),
]


INPLAY = [
    ("E GAP-AND-GO  in play (gap>=1%, open vol>=2x), trade gap direction, 1.5R",
     dict(top_n=5, min_abs_gap=0.01, min_rel_vol=2.0, gap_dir=True)),
    ("F GAP-AND-GO + breakeven  2R, stop to entry after +1R",
     dict(top_n=5, min_abs_gap=0.01, min_rel_vol=2.0, gap_dir=True, target_r=2.0, be_at_r=1.0)),
    ("G CONTROL  same in-play list, ORB both directions, 1.5R",
     dict(top_n=5, min_abs_gap=0.01, min_rel_vol=2.0)),
    ("H SELL ONLY  same in-play list, shorts only (gap up or down), 1.5R",
     dict(top_n=5, min_abs_gap=0.01, min_rel_vol=2.0, short_only=True)),
    ("I AGAINST THE GAP  same in-play list, fade the gap (gap up -> short, gap down -> buy), 1.5R",
     dict(top_n=5, min_abs_gap=0.01, min_rel_vol=2.0, against_gap=True)),
]


def verdict(trades, mid):
    a, b, tot = stats(trades[trades.date < mid]), stats(trades[trades.date >= mid]), stats(trades)
    ok = tot["n"] >= 40 and a["net"] > 0 and b["net"] > 0 and tot["pf"] >= 1.2
    why = []
    if tot["n"] < 40:
        why.append(f"only {tot['n']} trades (need 40)")
    if a["net"] <= 0:
        why.append("first half not profitable")
    if b["net"] <= 0:
        why.append("second half not profitable")
    if tot["pf"] < 1.2:
        why.append(f"profit factor {tot['pf']:.2f} (need 1.2)")
    return ok, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-refresh", action="store_true")
    ap.add_argument("--inplay", action="store_true", help="'stocks in play' test on a wide list")
    ap.add_argument("--universe", type=int, default=200, choices=[200, 500], help="with --inplay")
    args = ap.parse_args()
    symbols = s.wide_symbols(args.universe) if args.inplay else s.SYMBOLS
    variants, outfile = (INPLAY, "intraday_inplay.txt" if args.universe == 200 else "intraday_inplay_500.txt") if args.inplay else (VARIANTS, "intraday_backtest.txt")
    if args.inplay:
        s.SLIPPAGE = 0.001          # less liquid names: 0.10% each side
        s.MIN_CANDLES = 60          # tolerate a few empty candles in thin stocks
        s.MAX_STOP_PCT = 0.025      # gap stocks open with wide ranges
    if not args.no_refresh:
        print("Downloading 5-minute candles (free, Yahoo)...")
        print(f"  {data.refresh(symbols)} stocks (5-minute)")
        if not args.inplay:
            print(f"  {data.refresh_daily()} stocks (daily)")
    all_days = build_days(symbols)
    dates = sorted({d for v in all_days.values() for d in v})
    mid = dates[len(dates) // 2]
    lines = [f"Intraday backtest | {len(all_days)} stocks | {dates[0]} to {dates[-1]} ({len(dates)} sessions)",
             f"Capital {s.CAPITAL:,}, risk/trade {s.RISK_PER_TRADE}, loss limit {s.DAILY_LOSS_LIMIT}/day, "
             f"slippage {s.SLIPPAGE:.2%}/side, all charges included. Halves split at {mid}.",
             "PASS = net > 0 after charges in BOTH halves, profit factor >= 1.2, at least 40 trades.", ""]
    results = []
    for label, kw in variants:
        t = run(all_days, **kw)
        lines.append(summarise(t, label))
        if t.empty:
            results.append({"name": label, "trades": 0, "net": 0, "profit_factor": 0, "win_rate": 0,
                            "first_half": 0, "second_half": 0, "passed": False, "why": ["no trades"]})
        if not t.empty:
            ok, why = verdict(t, mid)
            tot = stats(t)
            results.append({"name": label, "trades": tot["n"], "net": round(tot["net"]),
                            "profit_factor": round(min(tot["pf"], 99), 2), "win_rate": round(float((t.net > 0).mean()), 3),
                            "first_half": round(stats(t[t.date < mid])["net"]), "second_half": round(stats(t[t.date >= mid])["net"]),
                            "passed": bool(ok), "why": why,
                            "avg_per_day": round(float(t.groupby("date")["net"].sum().sum() / len(dates)))})
            lines.append("  VERDICT: " + ("PASS" if ok else "FAIL - " + "; ".join(why)))
            lines.append(f"  first half net {stats(t[t.date < mid])['net']:,.0f} | "
                         f"second half net {stats(t[t.date >= mid])['net']:,.0f}")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    s.REPORT_DIR.mkdir(exist_ok=True)
    (s.REPORT_DIR / outfile).write_text(text, encoding="utf-8")
    tag = "large" if not args.inplay else ("nifty200" if args.universe == 200 else "nifty500")
    (s.REPORT_DIR / f"intraday_results_{tag}.json").write_text(json.dumps({
        "from": str(dates[0]), "to": str(dates[-1]), "sessions": len(dates), "stocks": len(all_days),
        "pass_rule": "net > 0 after charges in both halves, profit factor >= 1.2, at least 40 trades",
        "variants": results}), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
