"""The look of the dashboard: colours, CSS and small HTML building blocks.

Modelled on Zerodha Kite's dark mode: near-black background, thin borders,
one blue accent, compact type. As in Kite, buy is blue and sell is
orange-red; green and red are kept for "good" and "bad" (gains, losses,
checks passed or failed).
"""

from html import escape

import streamlit as st

# The same in both modes: buy, sell, good, bad.
BLUE, SELL = "#4184f3", "#ff5722"
GOOD, BAD, NEUTRAL = "#4caf50", "#e5534b", "#7b8390"

# Background and text colours for each mode. The matching Streamlit colours
# are in .streamlit/config.toml. Switch mode from the menu at the top right:
# Settings > Choose app theme.
PALETTES = {
    "dark": {"BACKGROUND": "#15171b", "PANEL": "#1e2126", "BORDER": "#2b2f37",
             "TEXT": "#d5d8dd", "BRIGHT": "#f1f3f5", "MUTED": "#8b9099",
             "SIDEBAR": "#111317", "LINE": "#23262c"},
    "light": {"BACKGROUND": "#ffffff", "PANEL": "#f6f7f9", "BORDER": "#e1e4e9",
              "TEXT": "#3b4048", "BRIGHT": "#16191d", "MUTED": "#6b7280",
              "SIDEBAR": "#f6f7f9", "LINE": "#eceef2"},
}
MUTED = PALETTES["dark"]["MUTED"]      # set again by apply()


def current_mode():
    """ "light" or "dark": the theme the person has chosen in the browser."""
    try:
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


def _css(BACKGROUND, PANEL, BORDER, TEXT, BRIGHT, MUTED, SIDEBAR, LINE):
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Lato:wght@400;700&display=swap');

.stApp, .stApp p, .stApp label, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] {{
    font-family: 'Lato', 'Segoe UI', Roboto, sans-serif;
}}
.block-container {{ padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1380px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.stApp h1 {{ font-size: 1.45rem; font-weight: 700; color: {BRIGHT}; padding: 0.2rem 0 0.1rem; }}
.stApp h2 {{ font-size: 1.15rem; font-weight: 700; color: {BRIGHT}; }}
.stApp h3 {{ font-size: 1.02rem; font-weight: 700; color: {BRIGHT}; padding-top: 0.9rem; }}
[data-testid="stCaptionContainer"] {{ color: {MUTED}; }}

/* number tiles */
[data-testid="stMetric"] {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 12px 14px;
}}
[data-testid="stMetricLabel"] {{ color: {MUTED}; }}
[data-testid="stMetricValue"] {{ font-size: 1.35rem; color: {BRIGHT}; font-variant-numeric: tabular-nums; }}

/* side panel, folds, tables, forms */
section[data-testid="stSidebar"] {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
[data-testid="stExpander"] details {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 6px; }}
[data-testid="stForm"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {BORDER}; }}
.stButton button, .stFormSubmitButton button {{ border-radius: 4px; }}

/* choices in a row look like Kite's tabs: no circle, a blue underline on the chosen one */
.stRadio div[role="radiogroup"] {{ gap: 0; border-bottom: 1px solid {BORDER}; flex-wrap: nowrap; }}
.stRadio div[role="radiogroup"] label p {{ white-space: nowrap; }}
.stRadio div[role="radiogroup"] label {{
    padding: 7px 16px 8px; margin: 0 0 -1px 0; border-bottom: 2px solid transparent;
    color: {MUTED}; cursor: pointer;
}}
.stRadio div[role="radiogroup"] label > div > div:not([data-testid="stMarkdownContainer"]) {{ display: none; }}
.stRadio div[role="radiogroup"] label:hover {{ color: {TEXT}; }}
.stRadio div[role="radiogroup"] label[data-selected="true"],
.stRadio div[role="radiogroup"] label:has(input:checked) {{ border-bottom-color: {BLUE}; }}
.stRadio div[role="radiogroup"] label[data-selected="true"] p,
.stRadio div[role="radiogroup"] label:has(input:checked) p {{ color: {BLUE}; font-weight: 700; }}

/* top bar */
.brand {{ font-size: 1.05rem; font-weight: 700; color: {BRIGHT}; padding-top: 6px; white-space: nowrap; }}
.brand i {{ display: inline-block; width: 9px; height: 9px; background: {BLUE};
           transform: rotate(45deg); margin-right: 10px; }}
.as-of {{ color: {MUTED}; font-size: 0.85rem; text-align: right; padding-top: 9px; }}

/* the action panel */
.plan {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 16px 18px; }}
.plan-title {{ color: {MUTED}; font-size: 0.85rem; margin-bottom: 2px; }}
.plan-head {{ color: {BRIGHT}; font-size: 1.3rem; font-weight: 700; margin-bottom: 4px; }}
.plan-note {{ color: {TEXT}; margin-bottom: 4px; }}
.plan-foot {{ color: {MUTED}; font-size: 0.82rem; margin-top: 12px; }}
.acts {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(235px, 1fr));
         gap: 10px; margin-top: 12px; }}
.act {{ background: {BACKGROUND}; border: 1px solid {BORDER}; border-left: 3px solid var(--c);
        border-radius: 4px; padding: 10px 12px; }}
.act-top {{ display: flex; justify-content: space-between; align-items: baseline; }}
.act-tag {{ color: var(--c); font-weight: 700; font-size: 0.82rem; }}
.act-score {{ color: {MUTED}; font-size: 0.8rem; }}
.act-symbol {{ color: {BRIGHT}; font-size: 1.08rem; font-weight: 700; margin: 2px 0; }}
.act-line {{ color: {TEXT}; font-size: 0.88rem; font-variant-numeric: tabular-nums; }}
.act-why {{ color: {MUTED}; font-size: 0.8rem; margin-top: 3px; }}

/* yes / no checks */
.checks {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
           column-gap: 28px; }}
.check {{ display: flex; gap: 10px; padding: 7px 0; border-bottom: 1px solid {LINE}; color: {TEXT}; }}
.check b {{ width: 14px; text-align: center; }}

/* score bars */
.bars {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
         column-gap: 32px; row-gap: 8px; margin: 6px 0 4px; }}
.bar-row {{ display: grid; grid-template-columns: 92px 1fr 30px; align-items: center; gap: 10px;
            color: {TEXT}; font-size: 0.9rem; }}
.bar {{ height: 7px; background: {BORDER}; border-radius: 4px; overflow: hidden; }}
.bar i {{ display: block; height: 100%; border-radius: 4px; }}
.bar-row span:last-child {{ text-align: right; font-variant-numeric: tabular-nums; color: {BRIGHT}; }}
.big-score {{ font-size: 1.9rem; font-weight: 700; color: {BRIGHT}; line-height: 1.1; }}
.big-score small {{ font-size: 0.9rem; font-weight: 400; color: {MUTED}; margin-left: 8px; }}
</style>
"""


def apply(mode=None):
    """Add the styling to the page. Call once, near the top of dashboard.py."""
    global MUTED
    palette = PALETTES[mode or current_mode()]
    MUTED = palette["MUTED"]
    st.markdown(_css(**palette), unsafe_allow_html=True)


def html(text):
    st.markdown(text, unsafe_allow_html=True)


def level_colour(value):
    """Green for a strong score, red for a weak one, grey in between."""
    if value >= 60:
        return GOOD
    return BAD if value <= 40 else NEUTRAL


def action_card(kind, symbol, line, why="", score=None):
    """One instruction. kind is "Buy", "Sell" or "Hold"."""
    colour = {"Buy": BLUE, "Sell": SELL}.get(kind, NEUTRAL)
    side = "" if score is None else f'<span class="act-score">score {score:.0f}</span>'
    reason = f'<div class="act-why">{escape(why)}</div>' if why else ""
    return (f'<div class="act" style="--c:{colour}"><div class="act-top">'
            f'<span class="act-tag">{kind}</span>{side}</div>'
            f'<div class="act-symbol">{escape(symbol)}</div>'
            f'<div class="act-line">{escape(line)}</div>{reason}</div>')


def plan_panel(head, notes=(), cards=(), foot=()):
    """The "What to do" panel: a headline, optional cards and small print."""
    body = "".join(f'<div class="plan-note">{escape(note)}</div>' for note in notes)
    grid = f'<div class="acts">{"".join(cards)}</div>' if cards else ""
    small = "".join(f'<div class="plan-foot">{escape(note)}</div>' for note in foot)
    html(f'<div class="plan"><div class="plan-title">What to do</div>'
         f'<div class="plan-head">{escape(head)}</div>{body}{grid}{small}</div>')


def checks(items):
    """A list of (text, passed). passed is True, False or None (not known)."""
    rows = []
    for text, passed in items:
        mark, colour = {True: ("✓", GOOD), False: ("✕", BAD)}.get(passed, ("–", MUTED))
        rows.append(f'<div class="check"><b style="color:{colour}">{mark}</b>'
                    f'<span>{escape(str(text))}</span></div>')
    html(f'<div class="checks">{"".join(rows)}</div>')


def score_bars(parts):
    """Bars for a list of (name, value from 0 to 100)."""
    rows = "".join(
        f'<div class="bar-row"><span>{escape(name)}</span><div class="bar">'
        f'<i style="width:{max(0, min(100, value)):.0f}%;background:{level_colour(value)}"></i>'
        f'</div><span>{value:.0f}</span></div>' for name, value in parts)
    html(f'<div class="bars">{rows}</div>')


def big_score(value, note):
    html(f'<div class="big-score">{value:.0f}<small>{escape(note)}</small></div>')


def top_bar_brand():
    html('<div class="brand"><i></i>India Trading System</div>')


def as_of(text):
    html(f'<div class="as-of">{escape(text)}</div>')


def market_banner(level, note):
    """A coloured strip saying how far to trust the market today."""
    colour = {"strong": GOOD, "caution": "#e3a008", "weak": BAD}[level]
    html(f'<div class="plan" style="border-left:4px solid {colour};margin-bottom:12px;'
         f'padding:11px 16px"><span style="color:{colour};font-weight:700">'
         f'{level.capitalize()}</span><span class="plan-note" style="margin-left:12px">'
         f'{escape(note.split(": ", 1)[-1])}</span></div>')
