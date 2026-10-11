"""Factor study: after each quarter's shareholding filings are public, do stocks
with a given characteristic do better or worse than the rest over the next quarter?"""
import sys, warnings; warnings.simplefilter("ignore"); sys.path.insert(0, "/".join(__file__.split("/")[:-1]))
from lab import *
from trading import shareholding as sh, fundamentals as fu
import numpy as np, pandas as pd

d = sh.load_shareholding()
d = d[~((d.promoter == 0) & (d.fii == 0) & (d.dii == 0))].copy()
counts = d.groupby("quarter_end").size(); quarters = [q for q in sorted(counts.index) if counts[q] >= 300]
annual = fu.load_annual(); ann = dict(tuple(annual.groupby("symbol")))
metrics_cache = {s: fu.yearly_metrics(rows) for s, rows in ann.items()}
col = {s: j for j, s in enumerate(syms)}
LIQa = LIQ.to_numpy(dtype=bool)
C6 = (C / C.shift(126) - 1).to_numpy(dtype=float)

def first_after(day): return int(cal.searchsorted(pd.Timestamp(day), side="right"))

rows = []
for k in range(1, len(quarters)):
    q, prev = quarters[k], quarters[k - 1]
    form = q + pd.Timedelta(days=30)
    i0 = first_after(form)
    nxt = quarters[k + 1] + pd.Timedelta(days=30) if k + 1 < len(quarters) else None
    i1 = first_after(nxt) if nxt is not None else len(cal) - 1
    if i0 >= len(cal) - 5 or i1 >= len(cal): i1 = len(cal) - 1
    if i1 - i0 < 20: continue
    now = d[(d.quarter_end == q) & (d.filed_on <= form)].set_index("symbol")
    before = d[d.quarter_end == prev].set_index("symbol")
    for s in now.index.intersection(before.index):
        if s not in col: continue
        j = col[s]
        if not LIQa[i0 - 1, j] or np.isnan(Oa[i0, j]) or np.isnan(Oa[i1, j]): continue
        a, b = now.loc[s], before.loc[s]
        m = metrics_cache.get(s); fm = None
        if m is not None:
            ok = m[m.period_end + pd.Timedelta(days=75) <= form]
            if len(ok): fm = ok.iloc[-1]
        rows.append(dict(form=form, symbol=s, fwd=Oa[i1, j] / Oa[i0, j] - 1,
            d_fii=a.fii - b.fii, d_dii=a.dii - b.dii, d_mf=a.mutual_funds - b.mutual_funds,
            d_inst=(a.fii + a.dii) - (b.fii + b.dii), d_promoter=a.promoter - b.promoter,
            mf_level=a.mutual_funds, fii_level=a.fii, promoter_level=a.promoter,
            pledged=float(bool(a.promoters_pledged)) if pd.notna(a.promoters_pledged) else np.nan,
            mom6=C6[i0 - 1, j],
            roe=fm.return_on_equity if fm is not None else np.nan,
            sales_growth=fm.sales_growth if fm is not None else np.nan,
            profit_growth=fm.profit_growth if fm is not None else np.nan,
            net_margin=fm.net_margin if fm is not None else np.nan,
            debt_to_equity=fm.debt_to_equity if fm is not None else np.nan,
            quality_ok=float(fu.passes_quality(fm)) if fm is not None else np.nan))
p = pd.DataFrame(rows).astype({c: float for c in ["roe", "sales_growth", "profit_growth", "net_margin", "debt_to_equity"]})
p["excess"] = p.fwd - p.groupby("form").fwd.transform("mean")
p.to_pickle("/tmp/panel.pkl")
print("panel rows", len(p), "quarters", p.form.nunique(), "stocks per quarter", int(p.groupby("form").size().median()))
print("formation dates:", [str(x.date()) for x in sorted(p.form.unique())])

def study(factor, sub):
    ics, spreads = [], []
    for form, g in sub.groupby("form"):
        g = g.dropna(subset=[factor])
        if len(g) < 50 or g[factor].nunique() < 2: continue
        if factor in BOUNDARY and form == pd.Timestamp("2022-10-30"): continue   # filing format changed
        ics.append(g[factor].rank().corr(g.excess.rank()))
        if g[factor].nunique() == 2:
            hi = g[factor] == g[factor].max(); spreads.append(g.excess[hi].mean() - g.excess[~hi].mean())
        else:
            r = g[factor].rank(pct=True); spreads.append(g.excess[r > 0.8].mean() - g.excess[r <= 0.2].mean())
    n = len(ics)
    if n < 3: return n, np.nan, np.nan, np.nan, np.nan
    t = lambda x: np.mean(x) / (np.std(x, ddof=1) / np.sqrt(len(x)))
    return n, np.mean(ics), t(ics), np.mean(spreads) * 100, t(spreads)

BOUNDARY = {"d_fii", "d_dii", "d_inst"}
split = pd.Timestamp("2024-01-01")
print("pledged share:", round(p.pledged.mean(), 2), "quality_ok share:", round(p.quality_ok.mean(), 2))
print(f"\n{'factor':16s} | {'IN-SAMPLE (to 2023)':^34s} | {'OUT-OF-SAMPLE (2024 on)':^34s}")
print(f"{'':16s} | {'n':>2s} {'IC':>6s} {'t':>5s} {'top-bot%':>8s} {'t':>5s} | {'n':>2s} {'IC':>6s} {'t':>5s} {'top-bot%':>8s} {'t':>5s}")
for f in ["d_fii", "d_dii", "d_mf", "d_inst", "d_promoter", "mf_level", "fii_level", "promoter_level", "pledged", "mom6", "roe", "sales_growth", "profit_growth", "net_margin", "debt_to_equity", "quality_ok"]:
    a = study(f, p[p.form < split]); b = study(f, p[p.form >= split])
    fmt = lambda x: f"{x[0]:2d} {x[1]:+6.3f} {x[2]:+5.1f} {x[3]:+8.2f} {x[4]:+5.1f}"
    print(f"{f:16s} | {fmt(a)} | {fmt(b)}")
print("\nuniverse mean forward return per quarter (%):", (p.groupby("form").fwd.mean() * 100).round(1).tolist())
