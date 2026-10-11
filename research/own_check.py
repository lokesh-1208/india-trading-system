import sys, warnings; warnings.simplefilter("ignore"); sys.path.insert(0, "/".join(__file__.split("/")[:-1]))
from lab import *
import numpy as np, pandas as pd
p = pd.read_pickle("/tmp/panel.pkl"); p.loc[p.form == pd.Timestamp("2022-10-30"), "d_fii"] = np.nan
forms = sorted(p.form.unique())
def frame(v):
    out = pd.DataFrame(np.nan, index=cal, columns=syms)
    for k, f in enumerate(forms):
        i0 = int(cal.searchsorted(f, side="right")); i1 = int(cal.searchsorted(forms[k + 1], side="right")) if k + 1 < len(forms) else len(cal)
        g = v[v.form == f].set_index("symbol")["v"]; out.iloc[i0 - 1:i1 - 1, [syms.index(s) for s in g.index]] = g.values
    return out
r = lambda c: p.groupby("form")[c].rank(pct=True)
p["own"] = pd.concat([r("d_fii"), r("d_mf")], axis=1).mean(axis=1); p["combo"] = pd.concat([r("mom6"), r("d_fii"), r("d_mf")], axis=1).mean(axis=1)
mkt200 = (NC > sma(NC, 200)).reindex(cal).fillna(False); per = ("2022-02-01", "2026-10-09")
# 1. simple check with no simulator: average next-quarter return of the top N each quarter, before costs
print("Average next-quarter return (%), before costs, by how many top names are held")
for col in ("own", "combo", "mom6"):
    line_ = f"  {col:6s}"
    for n in (5, 10, 20, 50):
        top = p.sort_values(col, ascending=False).groupby("form").head(n).groupby("form").fwd.mean()
        line_ += f" | top{n:<2d} {top.mean()*100:+5.1f} (beat universe in {int((top > p.groupby('form').fwd.mean()).sum())}/{len(top)} qtrs)"
    print(line_)
print("  universe average", round(p.groupby("form").fwd.mean().mean() * 100, 1))
# 2. simulator, different N
for n in (5, 10, 20):
    for col in ("own", "combo"):
        eq, tr = sim_rotation(frame(p.assign(v=p[col])[["form", "symbol", "v"]].dropna()).where(LIQ), mkt200, *per, n=n, cash_when_weak=False)
        s = stats(eq, tr); print("  " + line(f"top {n} {col}", s))
        if n == 5 and col == "combo":
            t = pd.DataFrame(tr, columns=["sym", "ein", "eout", "pnl", "chg", "val"]); t["ret%"] = (t.pnl / t.val * 100).round(1); t["in"] = [cal[i].date() for i in t.ein]; t["out"] = [cal[i].date() for i in t.eout]
            print(t.sort_values("pnl", ascending=False).head(8)[["sym", "in", "out", "ret%", "pnl"]].to_string(index=False)); print("  share of profit from top 5 trades:", round(t.pnl.nlargest(5).sum() / t.pnl.sum(), 2)); print("  yearly %:", (s["yearly"] * 100).round(0).to_dict())
# 3. luck check: 300 portfolios of 5 random eligible stocks per quarter, same simple return measure
rng = np.random.default_rng(0); sims = []
for _ in range(300):
    pick = p.groupby("form").sample(5, random_state=int(rng.integers(1e9))).groupby("form").fwd.mean(); sims.append((1 + pick).prod())
real = {c: (1 + p.sort_values(c, ascending=False).groupby("form").head(5).groupby("form").fwd.mean()).prod() for c in ("own", "combo")}
print("growth of 1 over the 19 quarters, before costs: random 5 median", round(np.median(sims), 2), "95th pct", round(np.percentile(sims, 95), 2), "99th", round(np.percentile(sims, 99), 2), "| own", round(real["own"], 2), "combo", round(real["combo"], 2))
print("\nRisk controls (whole period), momentum + ownership:")
df = frame(p.assign(v=p["combo"])[["form", "symbol", "v"]].dropna()).where(LIQ)
for n in (5, 10):
    for weak in (False, True):
        eq, tr = sim_rotation(df, mkt200, *per, n=n, cash_when_weak=weak); s = stats(eq, tr)
        print("  " + line(f"top {n}, cash when Nifty weak={weak}", s), "| final", round(s["final"]))
for sub in (("2022-02-01", "2023-12-31"), ("2024-01-01", "2026-10-09")):
    eq, tr = sim_rotation(df, mkt200, *sub, n=10, cash_when_weak=True); print("  " + line(f"top 10 + cash rule {sub[0][:4]}-{sub[1][:4]}", stats(eq, tr)))
b = bench(*per); print("  benchmarks:", {k: (round(v[0] * 100, 1), round(v[1] * 100, 1)) for k, v in b.items()})
latest = p[p.form == p.form.max()].sort_values("combo", ascending=False).head(10)
print("\nLatest formation", p.form.max().date(), "top 10:"); print(latest[["symbol", "combo", "mom6", "d_fii", "d_mf"]].round(2).to_string(index=False))
