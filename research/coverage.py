import sys, warnings; warnings.simplefilter("ignore"); sys.path.insert(0, "/".join(__file__.split("/")[:-1]))
from lab import *
print("stocks loaded", len(syms))
print(data.coverage_by_year(membership, set(syms), 2015, 2026).to_string(index=False))
el = LIQ.sum(axis=1); print("eligible (member + liquid) per day, by year:"); print(el.groupby(el.index.year).mean().round(0).astype(int).to_dict())
r = C.pct_change(fill_method=None).where(LIQ.shift(1).fillna(False)); bad = (r > 1.0) | (r < -0.6)
print("suspicious daily moves among eligible:", int(bad.sum().sum())); st = bad.stack(); print([(d.date(), s, round(float(r.loc[d, s]), 2)) for d, s in st[st].index][:15])
nodata = open("data/nodata.txt").read().split(); m = membership[membership.symbol.isin(nodata)]; print("no-data symbols:", len(nodata)); print(sorted(nodata))
