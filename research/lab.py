"""Research lab: flexible simulators for comparing rule sets. Not part of the product."""
import sys, math, numpy as np, pandas as pd
sys.path.insert(0, ".")
import config
from trading import data, charges, strategy, backtest

nifty = data.load_market("NIFTY50")
stocks = data.load_all_stocks()
cal = nifty.index
syms = list(stocks)
def wide(col): return pd.DataFrame({s: t[col] for s, t in stocks.items()}).reindex(cal)
O, H, L, C, V = [wide(c) for c in ["Open", "High", "Low", "Close", "Volume"]]
prevC = C.shift(1)
TR = pd.concat([(H - L).stack(future_stack=True), (H - prevC).abs().stack(future_stack=True), (L - prevC).abs().stack(future_stack=True)], axis=1).max(axis=1).unstack()[syms]
ATR = TR.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
TURN = (C * V).rolling(20).mean() / 1e7
membership = data.load_membership()
MEMBER = pd.DataFrame({s_: data.membership_mask(s_, cal, membership) for s_ in syms})
LIQ = (TURN >= config.MIN_TURNOVER_CRORE) & MEMBER
AGE = C.notna().cumsum()
NC = nifty["Close"]
def sma(x, n): return x.rolling(n, min_periods=n).mean()
def rsi(x, n):
    d = x.diff(); g = d.clip(lower=0); l = -d.clip(upper=0)
    ag = g.ewm(alpha=1/n, adjust=False, min_periods=n).mean(); al = l.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + ag / al)
A = lambda df: df.to_numpy(dtype=float)
Oa, Ha, La, Ca, ATRa = A(O), A(H), A(L), A(C), A(ATR)
LCa = A(C.ffill())
SL = config.SLIPPAGE

def span(start, end):
    i0 = cal.searchsorted(pd.Timestamp(start)); i1 = cal.searchsorted(pd.Timestamp(end), side="right") - 1
    return i0, i1

def stats(eq, trades, cap=100000.0):
    days = (eq.index[-1] - eq.index[0]).days
    cagr = (eq.iloc[-1] / cap) ** (365.25 / days) - 1
    dd = float((eq / eq.cummax() - 1).min())
    t = pd.DataFrame(trades, columns=["sym", "ein", "eout", "pnl", "chg", "val"])
    w = t[t.pnl > 0]; l = t[t.pnl <= 0]
    return dict(cagr=cagr, dd=dd, mar=cagr / abs(dd) if dd < 0 else float("nan"), n=len(t),
                win=len(w) / len(t) if len(t) else float("nan"),
                pf=w.pnl.sum() / -l.pnl.sum() if len(l) and l.pnl.sum() < 0 else float("nan"),
                chg=t.chg.sum(), final=eq.iloc[-1], hold=(t.eout - t.ein).mean() if len(t) else float("nan"),
                yearly=(eq.groupby(eq.index.year).last() / eq.groupby(eq.index.year).last().shift(1).fillna(cap) - 1))

def sim_swing(entry, rank, exit_sig, mkt, start, end, stop_mult=3.0, trail_mult=None, max_hold=None,
              max_pos=config.MAX_POSITIONS, cap=100000.0):
    """Entry at next open. Stop (optionally trailing on closes). Exit signal at close -> next open."""
    E, R, X, M = entry.to_numpy(dtype=bool), A(rank), exit_sig.to_numpy(dtype=bool), mkt.to_numpy(dtype=bool)
    i0, i1 = span(start, end); cash = cap; pos = {}; trades = []; eqs = [cap]
    def sell(j, i, px):
        nonlocal cash
        p = pos.pop(j); px = px * (1 - SL); val = p["q"] * px; sc = charges.sell_charges(val); cash += val - sc
        trades.append((syms[j], p["i"], i, val - sc - p["q"] * p["e"] - p["bc"], p["bc"] + sc, p["q"] * p["e"]))
    for i in range(i0 + 1, i1 + 1):
        y = i - 1
        for j in list(pos):
            if pos[j]["x"] and not np.isnan(Oa[i, j]): sell(j, i, Oa[i, j])
        before = set(pos)
        free = max_pos - len(pos)
        if M[y] and free > 0:
            c = np.flatnonzero(E[y]); c = sorted(c, key=lambda j: -(R[y, j] if not np.isnan(R[y, j]) else -1e18))
            eq = eqs[-1]
            for j in c:
                if free == 0: break
                if j in pos or np.isnan(Oa[i, j]) or np.isnan(ATRa[y, j]): continue
                e = Oa[i, j] * (1 + SL); stop = Oa[i, j] - stop_mult * ATRa[y, j]
                if stop <= 0: continue
                q = math.floor(min(eq * config.RISK_PER_TRADE / (e - stop), eq * (1.0 / max_pos) / e, cash / (e * 1.002)))
                if q < 1: continue
                bc = charges.buy_charges(q * e); cash -= q * e + bc
                pos[j] = dict(i=i, e=e, q=q, s=stop, bc=bc, x=False); free -= 1
        for j in list(pos):
            p = pos[j]
            if np.isnan(La[i, j]): continue
            if j not in before:
                if La[i, j] <= p["s"]: sell(j, i, p["s"])
                continue
            if Oa[i, j] <= p["s"]: sell(j, i, Oa[i, j])
            elif La[i, j] <= p["s"]: sell(j, i, p["s"])
        for j, p in pos.items():
            if np.isnan(Ca[i, j]): continue
            if trail_mult is not None and not np.isnan(ATRa[i, j]):
                p["s"] = max(p["s"], Ca[i, j] - trail_mult * ATRa[i, j])
            if X[i, j] or (max_hold is not None and i - p["i"] >= max_hold): p["x"] = True
        eqs.append(cash + sum(p["q"] * LCa[i, j] for j, p in pos.items()))
    for j in list(pos): sell(j, i1, LCa[i1, j])
    eqs[-1] = cash
    return pd.Series(eqs, index=cal[i0:i1 + 1]), trades

def sim_rotation(score, mkt, start, end, n=5, keep_mult=2, cash_when_weak=True, cap=100000.0):
    """Monthly: hold the top n by score. Keep a holding while it stays in the top n*keep_mult."""
    S, M = A(score), mkt.to_numpy(dtype=bool)
    i0, i1 = span(start, end); cash = cap; pos = {}; trades = []; eqs = [cap]
    def sell(j, i, px):
        nonlocal cash
        p = pos.pop(j); px = px * (1 - SL); val = p["q"] * px; sc = charges.sell_charges(val); cash += val - sc
        trades.append((syms[j], p["i"], i, val - sc - p["q"] * p["e"] - p["bc"], p["bc"] + sc, p["q"] * p["e"]))
    for i in range(i0 + 1, i1 + 1):
        y = i - 1
        if cal[i].month != cal[y].month:
            order = [j for j in np.argsort(-np.nan_to_num(S[y], nan=-1e18)) if not np.isnan(S[y, j])]
            rankpos = {j: k for k, j in enumerate(order)}
            weak = cash_when_weak and not M[y]
            for j in list(pos):
                if np.isnan(Oa[i, j]): continue
                if weak or rankpos.get(j, 10**9) >= n * keep_mult: sell(j, i, Oa[i, j])
            if not weak:
                eq = eqs[-1]
                for j in order[:n * keep_mult]:
                    if len(pos) >= n: break
                    if j in pos or np.isnan(Oa[i, j]) or rankpos[j] >= n and len(pos) >= n: continue
                    e = Oa[i, j] * (1 + SL); q = math.floor(min(eq / n, cash / 1.002) / e)
                    if q < 1: continue
                    bc = charges.buy_charges(q * e); cash -= q * e + bc
                    pos[j] = dict(i=i, e=e, q=q, bc=bc)
        eqs.append(cash + sum(p["q"] * LCa[i, j] for j, p in pos.items()))
    for j in list(pos): sell(j, i1, LCa[i1, j])
    eqs[-1] = cash
    return pd.Series(eqs, index=cal[i0:i1 + 1]), trades

def bench(start, end):
    i0, i1 = span(start, end); days = (cal[i1] - cal[i0]).days
    n = NC.iloc[i0:i1 + 1]; out = {}
    out["nifty"] = ((n.iloc[-1] / n.iloc[0]) ** (365.25 / days) - 1, float((n / n.cummax() - 1).min()))
    r = C.pct_change(fill_method=None).where(LIQ.shift(1).fillna(False)).iloc[i0 + 1:i1 + 1].mean(axis=1).fillna(0)
    ew = (1 + r).cumprod()
    out["equal_weight"] = (ew.iloc[-1] ** (365.25 / days) - 1, float((ew / ew.cummax() - 1).min()))
    return out

def line(name, s):
    return f"{name:34s} cagr {s['cagr']*100:+6.1f}%  dd {s['dd']*100:6.1f}%  mar {s['mar']:5.2f}  trades {s['n']:4d}  win {s['win']*100:4.0f}%  pf {s['pf']:.2f}  hold {s['hold']:5.1f}d  charges {s['chg']:6.0f}"
