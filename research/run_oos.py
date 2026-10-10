import sys, warnings; warnings.simplefilter("ignore"); sys.path.insert(0, "/".join(__file__.split("/")[:-1]))
from lab import *
IS = ("2016-01-01", "2021-12-31"); OOS = ("2022-01-01", "2026-10-09")
mkt200 = (NC > sma(NC, 200)).reindex(cal).fillna(False)
mom = (C.shift(21) / C.shift(21 + 126) - 1).where(LIQ & (AGE >= 156))
r2 = rsi(C, 2); up = (C > sma(C, 200)) & LIQ & (AGE >= 220); mom6 = C / C.shift(126) - 1
newhigh = (C >= C.rolling(126, min_periods=126).max()) & LIQ & (AGE >= 136)
ind = {s: strategy.add_indicators(t, NC, MEMBER[s].reindex(t.index)) for s, t in stocks.items()}
rng = np.random.default_rng(1)
rand = pd.DataFrame(rng.random(C.shape), index=cal, columns=syms).where(LIQ & (AGE >= 282))
for name, per in (("IN-SAMPLE", IS), ("OUT-OF-SAMPLE", OOS)):
    print(name, per); b = bench(*per)
    for k, v in b.items(): print(f"  benchmark {k:13s} cagr {v[0]*100:+.1f}%  dd {v[1]*100:.1f}%")
    res = backtest.run_backtest(ind, nifty, start=per[0], end=per[1]); s, _ = backtest.summarise(res)
    print(f"  v1 swing breakout                  cagr {s['annual_growth_rate']*100:+6.1f}%  dd {s['max_drawdown']*100:6.1f}%  trades {s['trades']}")
    out = {}
    eq, tr = sim_rotation(mom, mkt200, *per, cash_when_weak=False); out["A momentum rotation"] = stats(eq, tr)
    eq, tr = sim_swing(up & (r2 < 5), mom6, C > sma(C, 5), mkt200, *per, stop_mult=3.0, max_hold=10); out["B pullback rsi2"] = stats(eq, tr)
    eq, tr = sim_swing(newhigh, C / C.shift(126) - 1, C < sma(C, 50), mkt200, *per, stop_mult=4.0, trail_mult=4.0); out["C new-high trailing"] = stats(eq, tr)
    eq, tr = sim_rotation(rand, mkt200, *per, cash_when_weak=False); out["(check) random picks, no filter"] = stats(eq, tr)
    for k, s in out.items(): print("  " + line(k, s))
    if name == "OUT-OF-SAMPLE":
        ny = NC.groupby(NC.index.year).last().pct_change()
        print(pd.DataFrame({"A": out["A momentum rotation"]["yearly"], "C": out["C new-high trailing"]["yearly"], "nifty": ny}).dropna().mul(100).round(1).to_string())
        print("A final", round(out["A momentum rotation"]["final"]), "C final", round(out["C new-high trailing"]["final"]))
