"""The look of the dashboard: colours, CSS and small HTML building blocks.

Modelled on Zerodha Kite's dark mode: near-black background, thin borders,
one blue accent, compact type. As in Kite, buy is blue and sell is
orange-red; green and red are kept for "good" and "bad" (gains, losses,
checks passed or failed).
"""

from html import escape

import pandas as pd

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
    "light": {"BACKGROUND": "#f3f5f8", "PANEL": "#ffffff", "BORDER": "#e2e6ec",
              "TEXT": "#2f363e", "BRIGHT": "#1a1f26", "MUTED": "#6b7480",
              "SIDEBAR": "#ffffff", "LINE": "#edf0f4"},
}
MUTED = PALETTES["dark"]["MUTED"]      # set again by apply()
PANEL_NOW, BRIGHT_NOW = PALETTES["dark"]["PANEL"], PALETTES["dark"]["BRIGHT"]


def current_mode():
    """ "light" or "dark": the theme the person has chosen in the browser."""
    try:
        return "light" if st.context.theme.type == "light" else "dark"
    except Exception:
        return "dark"


def _css(BACKGROUND, PANEL, BORDER, TEXT, BRIGHT, MUTED, SIDEBAR, LINE):
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

.stApp, .stApp p, .stApp label, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] {{
    font-family: 'IBM Plex Sans', 'Segoe UI', Roboto, sans-serif;
}}
.block-container {{ padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1240px; }}
.stApp {{ font-variant-numeric: tabular-nums; }}
header[data-testid="stHeader"] {{ background: transparent; pointer-events: none; }}
[data-testid="stToolbar"] {{ pointer-events: none; }}
[data-testid="stToolbar"] button, [data-testid="stToolbar"] a,
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] {{ pointer-events: auto; }}
.stApp h1 {{ font-size: 1.45rem; font-weight: 700; color: {BRIGHT}; padding: 0.2rem 0 0.1rem; }}
.stApp h2 {{ font-size: 1.15rem; font-weight: 700; color: {BRIGHT}; }}
.stApp h3 {{ font-size: 1.08rem; font-weight: 600; color: {BRIGHT}; padding-top: 1.4rem; }}
[data-testid="stCaptionContainer"] {{ color: {MUTED}; }}

/* number tiles */
[data-testid="stMetric"] {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 12px 14px;
}}
[data-testid="stMetricLabel"] {{ color: {MUTED}; }}
[data-testid="stMetricValue"] {{ font-size: 1.25rem; color: {BRIGHT}; font-variant-numeric: tabular-nums; }}

/* side panel, folds, tables, forms */
section[data-testid="stSidebar"] {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
[data-testid="stExpander"] details {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 6px; }}
[data-testid="stForm"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {BORDER}; }}
.stButton button, .stFormSubmitButton button {{ border-radius: 4px; }}

/* choices in a row in the main area look like tabs: no circle, a blue underline */
[data-testid="stMain"] .stRadio div[role="radiogroup"] {{ gap: 0; border-bottom: 1px solid {BORDER};
    flex-wrap: nowrap; }}
[data-testid="stMain"] .stRadio div[role="radiogroup"] label p {{ white-space: nowrap; }}
[data-testid="stMain"] .stRadio div[role="radiogroup"] label {{
    padding: 7px 16px 8px; margin: 0 0 -1px 0; border-bottom: 2px solid transparent;
    color: {MUTED}; cursor: pointer;
}}
.stRadio div[role="radiogroup"] label > div > div:not([data-testid="stMarkdownContainer"]) {{ display: none; }}
[data-testid="stMain"] .stRadio div[role="radiogroup"] label:hover {{ color: {TEXT}; }}
[data-testid="stMain"] .stRadio div[role="radiogroup"] label:has(input:checked) {{ border-bottom-color: {BLUE}; }}
[data-testid="stMain"] .stRadio div[role="radiogroup"] label:has(input:checked) p {{ color: {BLUE}; font-weight: 600; }}

/* the page tabs at the top: larger */
.st-key-page div[role="radiogroup"] {{ border-bottom: none !important; justify-content: flex-end; gap: 4px !important; }}
.st-key-page div[role="radiogroup"] label {{ padding: 10px 20px 11px !important; border-bottom-width: 3px !important; }}
.st-key-page div[role="radiogroup"] label p {{ font-size: 1.08rem !important; font-weight: 500; }}

/* the left panel */
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding-top: 1.2rem; }}
.side-h {{ color: {BRIGHT}; font-weight: 600; font-size: 0.98rem; margin: 18px 0 8px; }}
.side-h:first-child {{ margin-top: 0; }}
.data-ok {{ display: flex; gap: 10px; align-items: flex-start; background: {BACKGROUND};
            border: 1px solid {BORDER}; border-radius: 10px; padding: 10px 12px; margin-bottom: 10px;
            font-size: 0.86rem; color: {TEXT}; line-height: 1.4; }}
.data-ok i {{ flex: none; width: 9px; height: 9px; border-radius: 50%; background: var(--c);
              margin-top: 5px; box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 22%, transparent); }}
.data-ok b {{ display: block; color: {BRIGHT}; font-weight: 600; }}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {{ gap: 6px; flex-direction: column;
    align-items: stretch; }}
.st-key-today_show_choice, .st-key-today_show_choice .stRadio,
.st-key-today_show_choice [role="radiogroup"], .st-key-today_show_choice [role="radiogroup"] > div {{
    width: 100% !important; }}
[data-testid="stSidebarHeader"] {{ height: 2.4rem; min-height: 0; padding-top: 0.6rem; padding-bottom: 0; }}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {{
    border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 12px; margin: 0; width: 100%;
    background: {BACKGROUND}; cursor: pointer; }}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) {{
    border-color: {BLUE}; background: color-mix(in srgb, {BLUE} 10%, {PANEL}); }}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) p {{
    color: {BLUE}; font-weight: 600; }}

/* sections that open and close */
[data-testid="stMain"] [data-testid="stExpander"] {{ margin-bottom: 12px; }}
[data-testid="stMain"] [data-testid="stExpander"] details {{ background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 12px; }}
[data-testid="stMain"] [data-testid="stExpander"] summary {{ padding: 14px 18px; }}
[data-testid="stMain"] [data-testid="stExpander"] summary p {{ font-size: 1.06rem; font-weight: 600;
    color: {BRIGHT}; }}
[data-testid="stMain"] [data-testid="stExpander"] summary:hover p {{ color: {BLUE}; }}
[data-testid="stMain"] [data-testid="stExpanderDetails"] {{ padding: 0 18px 16px; }}
[data-testid="stExpander"] .rows {{ border-radius: 10px; }}
.sec-note {{ color: {MUTED}; font-size: 0.86rem; margin: -2px 0 10px; }}

/* top bar */
.brand {{ font-size: 1.75rem; font-weight: 700; color: {BRIGHT}; padding-top: 0; white-space: nowrap;
          letter-spacing: -0.01em; line-height: 1.2; }}
.brand i {{ display: inline-block; width: 12px; height: 12px; background: {BLUE}; vertical-align: 3px;
           transform: rotate(45deg); margin-right: 10px; }}
.as-of {{ color: {MUTED}; font-size: 0.85rem; text-align: right; padding-top: 9px; }}

/* the action panel */
.plan {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 16px 18px; }}
.plan-title {{ color: {MUTED}; font-size: 0.85rem; margin-bottom: 2px; }}
.plan-head {{ color: {BRIGHT}; font-size: 1.3rem; font-weight: 700; margin-bottom: 4px; }}
.plan-note {{ color: {TEXT}; margin-bottom: 4px; }}
.plan-foot {{ color: {MUTED}; font-size: 0.82rem; margin-top: 12px; }}
.acts {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(235px, 1fr));
         gap: 10px; margin-top: 12px; }}
.act {{ background: {PANEL}; border: 1px solid {BORDER}; border-left: 3px solid var(--c);
        border-radius: 8px; padding: 10px 12px; }}
.act-top {{ display: flex; justify-content: space-between; align-items: baseline; }}
.act-tag {{ color: var(--c); font-weight: 700; font-size: 0.82rem; }}
.act-score {{ color: {MUTED}; font-size: 0.8rem; }}
.act-symbol {{ color: {BRIGHT}; font-size: 1.08rem; font-weight: 700; margin: 2px 0; }}
.act-line {{ color: {TEXT}; font-size: 0.88rem; font-variant-numeric: tabular-nums; }}
.act-why {{ color: {MUTED}; font-size: 0.8rem; margin-top: 3px; }}

/* event cards */
.evs {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
        gap: 10px; margin: 6px 0 4px; }}
.ev-view {{ color: var(--c); font-size: 0.8rem; font-weight: 600; }}
.ev-hold {{ background: {BLUE}; color: #fff; font-size: 0.7rem; font-weight: 700;
            border-radius: 3px; padding: 1px 6px; margin-left: 6px; vertical-align: middle; }}
.ev {{ border-top: 1px solid {LINE}; margin-top: 7px; padding-top: 6px; font-size: 0.85rem;
       color: {TEXT}; }}
.ev-kind {{ font-weight: 700; color: {BRIGHT}; }}
.ev-when {{ color: {MUTED}; font-size: 0.78rem; margin-left: 6px; }}
.ev-up {{ color: {GOOD}; font-weight: 700; }}
.ev-down {{ color: {BAD}; font-weight: 700; }}
.ev a {{ color: {BLUE}; text-decoration: none; font-size: 0.78rem; margin-left: 4px; }}

/* market strip */
.strip {{ display: flex; gap: 28px; overflow-x: auto; padding: 10px 2px 12px;
          border-bottom: 1px solid {BORDER}; margin-bottom: 18px; }}
.strip div {{ white-space: nowrap; font-size: 0.86rem; color: {MUTED}; }}
.strip b {{ color: {BRIGHT}; font-weight: 600; margin: 0 6px; }}
.up {{ color: {GOOD}; }}  .down {{ color: {BAD}; }}

/* the day's plan */
.dayplan {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 20px;
            flex-wrap: wrap; margin: 4px 0 6px; }}
.dayplan h2 {{ font-size: 1.75rem !important; font-weight: 600 !important; margin: 0;
               padding: 0 !important; letter-spacing: -0.01em; }}
.dayplan p {{ color: {MUTED}; margin: 4px 0 0; font-size: 0.92rem; }}
.mood {{ border-radius: 999px; padding: 6px 14px; font-size: 0.85rem; font-weight: 600;
         background: color-mix(in srgb, var(--c) 14%, transparent); color: var(--c); }}

/* watchlist-style rows */
.rows {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; overflow: hidden; }}
.row {{ display: grid; grid-template-columns: 40px minmax(150px, 1.3fr) 120px minmax(250px, 2fr) 150px;
        gap: 18px; align-items: center; padding: 14px 18px; border-top: 1px solid {LINE}; }}
.row:first-child {{ border-top: none; }}
.avatar {{ width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center;
           font-weight: 700; font-size: 0.8rem; color: var(--c);
           background: color-mix(in srgb, var(--c) 12%, transparent); }}
.who b {{ display: block; color: {BRIGHT}; font-weight: 600; font-size: 0.98rem; }}
.who span {{ color: {MUTED}; font-size: 0.8rem; }}
.pill {{ display: inline-block; border-radius: 4px; padding: 1px 7px; font-size: 0.72rem;
         font-weight: 700; margin-left: 6px; vertical-align: 2px;
         background: color-mix(in srgb, var(--c) 14%, transparent); color: var(--c); }}
.spark svg {{ display: block; }}
.ladder svg {{ display: block; width: 100%; max-width: 340px; height: auto; overflow: visible; }}
.ladder text {{ font-size: 10.5px; fill: {MUTED}; font-family: inherit; }}
.ladder text.k {{ fill: {BRIGHT}; font-weight: 600; }}
.order {{ text-align: right; }}
.order b {{ display: block; color: {BRIGHT}; font-weight: 600; font-size: 0.98rem; }}
.order span {{ color: {MUTED}; font-size: 0.8rem; }}
.rows-head {{ display: flex; justify-content: space-between; align-items: baseline;
              margin: 22px 0 8px; }}
.rows-head h4 {{ margin: 0; font-size: 1.05rem; font-weight: 600; color: {BRIGHT}; padding: 0; }}
.rows-head span {{ color: {MUTED}; font-size: 0.84rem; }}
.empty {{ background: {PANEL}; border: 1px dashed {BORDER}; border-radius: 12px; padding: 18px;
          color: {MUTED}; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.chip {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 999px; padding: 5px 12px;
         font-size: 0.84rem; color: {TEXT}; }}
.chip b {{ color: {BRIGHT}; font-weight: 600; margin-right: 6px; }}
@media (max-width: 900px) {{
  .row {{ grid-template-columns: 40px 1fr 110px; }}
  .ladder, .order {{ grid-column: 1 / -1; text-align: left; }}
}}

/* company header */
.co {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 16px;
       flex-wrap: wrap; margin: 6px 0 14px; }}
.co h2 {{ font-size: 1.9rem !important; font-weight: 600 !important; margin: 0; padding: 0 !important; }}
.co p {{ color: {MUTED}; margin: 4px 0 0; font-size: 0.9rem; }}
.co-price {{ text-align: right; }}
.co-price b {{ display: block; font-size: 1.6rem; font-weight: 600; color: {BRIGHT}; }}
.co-tags {{ display: flex; gap: 8px; justify-content: flex-end; margin-top: 6px; }}

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
    global MUTED, PANEL_NOW, BRIGHT_NOW
    palette = PALETTES[mode or current_mode()]
    MUTED = palette["MUTED"]
    PANEL_NOW, BRIGHT_NOW = palette["PANEL"], palette["BRIGHT"]
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
    html('<div class="brand"><i></i>Kasauti</div>')


def as_of(text):
    html(f'<div class="as-of">{escape(text)}</div>')


def market_banner(level, note):
    """A coloured strip saying how far to trust the market today."""
    colour = {"strong": GOOD, "caution": "#e3a008", "weak": BAD}[level]
    html(f'<div class="plan" style="border-left:4px solid {colour};margin-bottom:12px;'
         f'padding:11px 16px"><span style="color:{colour};font-weight:700">'
         f'{level.capitalize()}</span><span class="plan-note" style="margin-left:12px">'
         f'{escape(note.split(": ", 1)[-1])}</span></div>')


VIEW_COLOURS = {"strong": GOOD, "neutral": NEUTRAL, "below": "#e3a008", "weak": BAD}


def _event_line(event):
    """One event inside an event card."""
    kind = event["kind"]
    when = event["when"]
    if kind == "Results due":
        icon, label, stamp = "📅", "Results due", f"{when:%a %d %b}"
    elif kind == "Results out":
        icon, label, stamp = "📊", "Results out", f"{when:%a %d %b}"
    else:
        icon, label, stamp = "📰", kind, f"{when:%d %b %H:%M}"
    move = event.get("move")
    if move is None or pd.isna(move):
        moved = ""
    else:
        cls = "ev-up" if move >= 0 else "ev-down"
        moved = f' · <span class="{cls}">{move:+.1f}% since</span>'
    text = f'<div>{escape(event["text"])}</div>' if event.get("text") else ""
    link = (f'<a href="{escape(event["link"])}" target="_blank">filing ↗</a>'
            if event.get("link") else "")
    return (f'<div class="ev">{icon} <span class="ev-kind">{escape(label)}</span>'
            f'<span class="ev-when">{stamp}</span>{moved}{link}{text}</div>')


def event_cards(entries):
    """Cards for the Events section: one per stock, coloured by the model's view."""
    cards = []
    for entry in entries:
        view = entry["view"]
        colour = VIEW_COLOURS.get(view.split(":")[0].split(" ")[0], NEUTRAL)
        rank = entry.get("rank")
        facts = []
        if rank is not None and not pd.isna(rank):
            facts.append(f"rank {int(rank)}")
        if entry.get("score") is not None and not pd.isna(entry["score"]):
            facts.append(f"score {entry['score']:.0f}")
        if entry.get("price") is not None and not pd.isna(entry["price"]):
            facts.append(f"Rs {entry['price']:,.2f}")
        hold = '<span class="ev-hold">YOU HOLD</span>' if entry.get("held") else ""
        lines = "".join(_event_line(event) for event in entry["events"])
        cards.append(
            f'<div class="act" style="--c:{colour}">'
            f'<div class="ev-view">{escape(view)}</div>'
            f'<div class="act-symbol">{escape(entry["symbol"])}{hold}</div>'
            f'<div class="act-score">{escape(" · ".join(facts))}</div>{lines}</div>')
    html(f'<div class="evs">{"".join(cards)}</div>')


# ------------------------------------------------------------ Today page --
def _num(value, digits=2):
    return f"{value:,.{digits}f}"


def market_strip(items):
    """The line of index levels at the top. items: (name, last value, change in %)."""
    parts = []
    for name, value, change in items:
        cls = "up" if change >= 0 else "down"
        parts.append(f'<div>{escape(name)}<b>{_num(value)}</b>'
                     f'<span class="{cls}">{change:+.2f}%</span></div>')
    html(f'<div class="strip">{"".join(parts)}</div>')


def day_plan(headline, note, level, level_text):
    """The page's headline: what to do today, and the market mood."""
    colour = {"strong": GOOD, "caution": "#d9930d", "weak": BAD}[level]
    html(f'<div class="dayplan"><div><h2>{escape(headline)}</h2><p>{escape(note)}</p></div>'
         f'<span class="mood" style="--c:{colour}" title="{escape(level_text)}">'
         f'Market: {escape(level)}</span></div>')


def sparkline(closes, trend, width=120, height=36):
    """A small price line (last few months) with the 20-day EMA as a faint line."""
    closes = [float(v) for v in closes if v == v]
    trend = [float(v) for v in trend if v == v][-len(closes):]
    if len(closes) < 2:
        return ""
    low, high = min(closes + trend), max(closes + trend)
    span = (high - low) or 1.0

    def path(values):
        step = width / (len(values) - 1)
        return " ".join(f"{'M' if i == 0 else 'L'}{i * step:.1f},"
                        f"{height - 2 - (v - low) / span * (height - 4):.1f}"
                        for i, v in enumerate(values))
    colour = GOOD if closes[-1] >= closes[0] else BAD
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="price over the last months">'
            f'<path d="{path(trend)}" fill="none" stroke="{NEUTRAL}" stroke-width="1" '
            f'stroke-dasharray="2 2" opacity="0.7"/>'
            f'<path d="{path(closes)}" fill="none" stroke="{colour}" stroke-width="1.6"/></svg>')


def ladder(stop, signal, limit, width=300):
    """Stop-loss, signal close and buy limit on one bar."""
    low, high = stop, limit
    pad = (high - low) * 0.04 or 1.0
    low, high = low - pad, high + pad

    def x(value):
        return 8 + (value - low) / (high - low) * (width - 16)
    xs, xg, xl = x(stop), x(signal), x(limit)
    return (f'<svg viewBox="0 0 {width} 46" role="img" '
            f'aria-label="stop {stop:.2f}, signal {signal:.2f}, buy limit {limit:.2f}">'
            f'<rect x="{xs:.1f}" y="15" width="{xg - xs:.1f}" height="6" rx="3" fill="{BAD}" opacity="0.22"/>'
            f'<rect x="{xg:.1f}" y="15" width="{xl - xg:.1f}" height="6" rx="3" fill="{BLUE}" opacity="0.35"/>'
            f'<rect x="{xs - 1:.1f}" y="10" width="2" height="16" fill="{BAD}"/>'
            f'<rect x="{xl - 1:.1f}" y="10" width="2" height="16" fill="{BLUE}"/>'
            f'<circle cx="{xg:.1f}" cy="18" r="4.5" fill="{PANEL_NOW}" stroke="{BRIGHT_NOW}" stroke-width="1.6"/>'
            f'<text x="{xs:.1f}" y="40" text-anchor="start">Stop {_num(stop)}</text>'
            f'<text x="{xg:.1f}" y="8" text-anchor="middle" class="k">{_num(signal)}</text>'
            f'<text x="{xl:.1f}" y="40" text-anchor="end">Buy up to {_num(limit)}</text></svg>')


def initials(symbol):
    letters = "".join(ch for ch in symbol if ch.isalpha())
    return letters[:2].upper()


def stock_rows(rows):
    """Watchlist-style rows. Each row: symbol, note, tag, colour, chart, middle, right_top, right_bottom."""
    out = []
    for row in rows:
        tag = (f'<span class="pill" style="--c:{row["colour"]}">{escape(row["tag"])}</span>'
               if row.get("tag") else "")
        out.append(
            f'<div class="row"><div class="avatar" style="--c:{row["colour"]}">'
            f'{escape(initials(row["symbol"]))}</div>'
            f'<div class="who"><b>{escape(row["symbol"])}{tag}</b><span>{escape(row["note"])}</span></div>'
            f'<div class="spark">{row.get("chart", "")}</div>'
            f'<div class="ladder">{row.get("middle", "")}</div>'
            f'<div class="order"><b>{escape(row["right_top"])}</b>'
            f'<span>{escape(row["right_bottom"])}</span></div></div>')
    html(f'<div class="rows">{"".join(out)}</div>')


def rows_head(title, note=""):
    html(f'<div class="rows-head"><h4>{escape(title)}</h4><span>{escape(note)}</span></div>')


def empty(text):
    html(f'<div class="empty">{escape(text)}</div>')


def chips(items):
    """Small rounded labels. items: (bold, rest)."""
    html('<div class="chips">' + "".join(
        f'<span class="chip"><b>{escape(bold)}</b>{escape(rest)}</span>' for bold, rest in items)
        + "</div>")


def side_heading(text):
    st.sidebar.markdown(f'<div class="side-h">{escape(text)}</div>', unsafe_allow_html=True)


def data_status(ok, text):
    """A small status card in the left panel: green dot when the prices are current."""
    colour = GOOD if ok else "#d9930d"
    head, _, rest = text.partition(": ")
    rest = rest[:1].upper() + rest[1:]
    st.sidebar.markdown(f'<div class="data-ok" style="--c:{colour}"><i></i><div><b>{escape(head)}</b>'
                        f'{escape(rest)}</div></div>', unsafe_allow_html=True)


def section_note(text):
    html(f'<div class="sec-note">{escape(text)}</div>')


def company_header(symbol, facts, price, change, view, rank, total):
    """Name, price and the model's view at the top of the Company page."""
    colour = VIEW_COLOURS.get(view.split(":")[0].split(" ")[0], NEUTRAL)
    cls = "up" if change >= 0 else "down"
    rank_tag = (f'<span class="mood" style="--c:{BLUE}">Rank {rank} of {total}</span>'
                if rank else "")
    html(f'<div class="co"><div><h2>{escape(symbol)}</h2><p>{escape(facts)}</p></div>'
         f'<div class="co-price"><b>Rs {price:,.2f} <span class="{cls}" style="font-size:1rem">'
         f'{change:+.2f}%</span></b><div class="co-tags">'
         f'<span class="mood" style="--c:{colour}">{escape(view.capitalize())}</span>{rank_tag}'
         f'</div></div></div>')
