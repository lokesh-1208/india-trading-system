"""Do ownership changes help? Three pre-chosen portfolios and rule C with an ownership filter."""
import sys, warnings; warnings.simplefilter("ignore"); sys.path.insert(0, "/".join(__file__.split("/")[:-1]))
from lab import *
import numpy as np, pandas as pd
p = pd.read_pickle("/tmp/panel.pkl")
forms = sorted(p.form.unique())
def frame(values_by_form):
    """Daily table: each formation date's values apply from the next trading day until the next formation."""
    out = pd.DataFrame(np.nan, index=cal, columns=syms)
    for k, f in enumerate(forms):
        i0 = int(cal.searchsorted(f, side="right")); i1 = int(cal.searchsorted(forms[k + 1], side="right")) if k + 1 < len(forms) else len(cal)
        g = values_by_form[values_by_form.form == f].set_index("symbol")["v"]
        out.iloc[i0 - 1:i1 - 1, [syms.index(s) for s in g.index]] = g.values      # known at the close before i0
    return out
def rank_by_form(col): return p.groupby("form")[col].rank(pct=True)
p["r_mom"] = rank_by_form("mom6"); p["r_fii"] = rank_by_form("d_fii"); p["r_mf"] = rank_by_form("d_mf")
scores = {"momentum only": p.r_mom, "ownership only (FII + MF change)": (p.r_fii + p.r_mf) / 2, "momentum + ownership": (p.r_mom + p.r_fii + p.r_mf) / 3}
mkt200 = (NC > sma(NC, 200)).reindex(cal).fillna(False)
periods = {"2022-02 to 2023-12": ("2022-02-01", "2023-12-31"), "2024-01 to 2026-10": ("2024-01-01", "2026-10-09"), "whole 2022-02 to 2026-10": ("2022-02-01", "2026-10-09")}
for pname, per in periods.items():
    b = bench(*per); print(f"\n=== {pname}"); [print(f"  benchmark {k:13s} cagr {v[0]*100:+6.1f}%  dd {v[1]*100:6.1f}%") for k, v in b.items()]
    for name, sc in scores.items():
        df = frame(p.assign(v=sc)[["form", "symbol", "v"]].dropna())
        eq, tr = sim_rotation(df.where(LIQ), mkt200, *per, n=5, cash_when_weak=False); print("  " + line("top 5: " + name, stats(eq, tr)))
    newhigh = (C >= C.rolling(126, min_periods=126).max()) & LIQ & (AGE >= 136)
    inst_up = frame(p.assign(v=((p.d_fii > 0) & (p.d_mf > 0)).astype(float))[["form", "symbol", "v"]]) > 0.5
    for name, sig in (("rule C", newhigh), ("rule C + FII and MF both rising", newhigh & inst_up)):
        eq, tr = sim_swing(sig, C / C.shift(126) - 1, C < sma(C, 50), mkt200, *per, stop_mult=4.0, trail_mult=4.0); print("  " + line(name, stats(eq, tr)))
print("\nshare of stock-quarters with FII and MF both rising:", round(float(((p.d_fii > 0) & (p.d_mf > 0)).mean()), 2))
