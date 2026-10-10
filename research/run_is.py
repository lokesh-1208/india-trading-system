import sys; sys.path.insert(0, "/".join(__file__.split("/")[:-1]))
from lab import *
IS = ("2016-01-01", "2021-12-31")
b = bench(*IS); print("IN-SAMPLE", IS); [print(f"  benchmark {k:13s} cagr {v[0]*100:+.1f}%  dd {v[1]*100:.1f}%") for k, v in b.items()]
mkt200 = (NC > sma(NC, 200)).reindex(cal).fillna(False); always = pd.Series(True, index=cal)
print("A. monthly momentum rotation (top 5)")
for look in (126, 252):
    mom = (C.shift(21) / C.shift(21 + look) - 1).where(LIQ & (AGE >= look + 30))
    for weak in (False, True):
        eq, tr = sim_rotation(mom, mkt200, *IS, cash_when_weak=weak); print("  " + line(f"look {look} cash_when_weak {weak}", stats(eq, tr)))
print("B. pullback in uptrend (RSI2)")
r2 = rsi(C, 2); up = (C > sma(C, 200)) & LIQ & (AGE >= 220); mom6 = C / C.shift(126) - 1
for thr in (5, 10):
    for mh in (5, 10):
        eq, tr = sim_swing(up & (r2 < thr), mom6, C > sma(C, 5), mkt200, *IS, stop_mult=3.0, max_hold=mh); print("  " + line(f"rsi2<{thr} max_hold {mh}", stats(eq, tr)))
print("C. new-high breakout with trailing stop")
for win in (126, 252):
    newhigh = (C >= C.rolling(win, min_periods=win).max()) & LIQ & (AGE >= win + 10)
    for tm in (3.0, 4.0):
        eq, tr = sim_swing(newhigh, C / C.shift(win) - 1, C < sma(C, 50), mkt200, *IS, stop_mult=tm, trail_mult=tm); print("  " + line(f"high {win} trail {tm}xATR", stats(eq, tr)))
