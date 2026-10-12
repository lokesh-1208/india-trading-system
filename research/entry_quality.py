"""Does checking entry quality help? Room above the trend line, and recent spikes.

Run from the project folder:  python research/entry_quality.py
Result (12 Oct 2026): neither check helped. Most settings made growth worse,
especially in 2024-2026. Both stay switched off (min_room, max_spike in rotation.simulate).
"""
import sys; sys.path.insert(0, ".")
import pandas as pd, config
from trading import data, model, rotation
stocks = data.load_all_stocks(); nifty = data.load_market(config.BENCHMARK)
b = model.from_disk(stocks, nifty)
periods = (("all", config.ROTATION_START, None), ("a", "2022-02-01", "2024-03-31"), ("b", "2024-04-01", None))
rows = []
variants = [("now", {})] + [(f"room>={r:.0%}", {"min_room": r}) for r in (0.01, 0.02, 0.03, 0.05)] \
         + [(f"spike<={x:.0%}", {"max_spike": x}) for x in (0.08, 0.10, 0.15, 0.20)]
for name, kw in variants:
    for pos in (4, 5, 6):
        for lab, st, en in periods:
            r = b.simulate(start=st, end=en, style="swing", positions=pos, **kw)
            s, _ = rotation.summarise(r, nifty)
            rows.append((name, pos, lab, round(s["annual_growth_rate"]*100, 1), round(s["max_drawdown"]*100, 1), sum(r["skipped"].values())))
t = pd.DataFrame(rows, columns=["v", "pos", "per", "gr", "dd", "skip"])
order = [v for v, _ in variants]
g = t.pivot_table(index="v", columns=["pos", "per"], values="gr", aggfunc="first").reindex(order)
print(g.to_string())
d = t[t.per == "all"].pivot_table(index="v", columns="pos", values=["dd", "skip"], aggfunc="first").reindex(order)
print(d.to_string())
