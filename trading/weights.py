"""Measured group weights: how much each score group has predicted recently.

Each week (the last trading day of the week, when the list is made), every score
group's ranking is compared with the stocks' returns over the next 5 trading days:
the rank correlation (Spearman) is that week's "information coefficient" (IC).
The weight a group gets on a day comes only from weeks whose 5 days had already
passed, so a backtest never uses the future:

  strength = average IC of the last LOOKBACK weeks, negative counted as 0
  weight   = SHRINK x equal share + (1 - SHRINK) x strength / sum of strengths

A group with fewer than MIN_WEEKS of history gets the equal share. Shrinking half
way to equal keeps one lucky stretch from taking over.
"""

import numpy as np
import pandas as pd

HORIZON = 5        # trading days ahead
LOOKBACK = 52      # weeks of history used
MIN_WEEKS = 26
SHRINK = 0.5


def signal_positions(calendar, start=0):
    """Positions of the last trading day of each week, from `start`."""
    return [p for p in range(max(start, 0), len(calendar) - 1)
            if calendar[p + 1].isocalendar()[:2] != calendar[p].isocalendar()[:2]]


def weekly_ic(built, groups, start=0):
    """One row per signal week: the IC of each group against the next HORIZON days."""
    close = built.prepared["last_close"]
    rows = {}
    for position in signal_positions(built.calendar, start):
        if position + HORIZON >= len(built.calendar):
            break
        scores = built.score_on(position)
        ahead = (close.iloc[position + HORIZON] / close.iloc[position] - 1).reindex(scores.index)
        row = {}
        for group in groups:
            pair = pd.DataFrame({"g": scores[group], "a": ahead}).dropna()
            # A group with no spread that day (all unknown) says nothing.
            row[group] = pair["g"].rank().corr(pair["a"].rank()) \
                if len(pair) >= 50 and pair["g"].nunique() > 5 else np.nan
        rows[position] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def weights_from_ic(ic, groups, lookback=LOOKBACK, min_weeks=MIN_WEEKS, shrink=SHRINK):
    """{signal position: {group: weight}} using only weeks already finished."""
    equal = 1.0 / len(groups)
    out = {}
    positions = list(ic.index)
    for number, position in enumerate(positions):
        # Week k's 5 days ahead end at about the next week's signal day: usable from then.
        past = ic.iloc[max(0, number - lookback):number]
        strength = {}
        for group in groups:
            values = past[group].dropna() if group in past else pd.Series(dtype=float)
            strength[group] = max(values.mean(), 0.0) if len(values) >= min_weeks else None
        known = {g: s for g, s in strength.items() if s is not None}
        total = sum(known.values())
        weights = {}
        for group in groups:
            if strength[group] is None or total <= 0:
                weights[group] = equal
            else:
                share_of_known = len(known) / len(groups)
                weights[group] = shrink * equal + (1 - shrink) * strength[group] / total * share_of_known
        norm = sum(weights.values())
        out[position] = {g: w / norm for g, w in weights.items()}
    return out
