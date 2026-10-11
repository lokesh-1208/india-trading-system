"""Charts for the dashboard. Each function takes data and returns one chart.

Colour rules used everywhere:
  - the same thing always has the same colour (price is always blue)
  - one scale per chart: two different measures get two charts, never two axes
  - text is always dark; only the lines and bars carry colour
"""

import pandas as pd
import plotly.graph_objects as go

import config

# Colours, in the fixed order they are handed out to series.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
RED = "#e34948"            # only as the opposite of blue: falls against rises
SURFACE = "#fcfcfb"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e8e7e3"


def _style(figure, title, height=360, y_title=None, legend=True):
    """One look for every chart: quiet grid, dark text, legend on top."""
    figure.update_layout(
        title={"text": title, "font": {"size": 15, "color": TEXT}, "x": 0, "xanchor": "left"},
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font={"color": MUTED, "size": 12},
        margin={"l": 10, "r": 10, "t": 70 if legend else 46, "b": 10},
        showlegend=legend,
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0,
                "font": {"color": TEXT}},
        hovermode="x unified",
        hoverlabel={"bgcolor": SURFACE, "font": {"color": TEXT}},
        bargap=0.35, bargroupgap=0.08, barcornerradius=4,
    )
    figure.update_xaxes(showgrid=False, linecolor=GRID, tickfont={"color": MUTED})
    figure.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=False,
                        tickfont={"color": MUTED},
                        title={"text": y_title, "font": {"color": MUTED}})
    return figure


def _line(x, y, name, colour, fmt=",.2f"):
    return go.Scatter(x=x, y=y, name=name, mode="lines",
                      line={"color": colour, "width": 2},
                      hovertemplate=f"%{{y:{fmt}}}<extra>{name}</extra>")


# ------------------------------------------------------------------ prices --
def price_chart(table, title):
    """Closing price with the fast and slow trend lines (EMAs)."""
    figure = go.Figure([
        _line(table.index, table["Close"], "Close", BLUE),
        _line(table.index, table["ema_fast"], f"{config.EMA_FAST}-day EMA", ORANGE),
        _line(table.index, table["ema_slow"], f"{config.EMA_SLOW}-day EMA", AQUA),
    ])
    return _style(figure, title, height=420, y_title="Rs")


def trend_chart(close, trend, name, trend_name, title):
    """One index with its trend line."""
    figure = go.Figure([
        _line(close.index, close, name, BLUE, ",.0f"),
        _line(trend.index, trend, trend_name, ORANGE, ",.0f"),
    ])
    return _style(figure, title, height=380)


def volume_chart(table, title="Shares traded each day"):
    figure = go.Figure(go.Bar(
        x=table.index, y=table["Volume"], marker={"color": BLUE},
        hovertemplate="%{y:,.0f}<extra>Volume</extra>"))
    return _style(figure, title, height=220, legend=False).update_layout(bargap=0.15)


def rsi_chart(table):
    """RSI with the band the rules look for."""
    figure = go.Figure(_line(table.index, table["rsi"], "RSI", BLUE, ".1f"))
    for level in (config.RSI_MIN, config.RSI_MAX):
        figure.add_hline(y=level, line={"color": MUTED, "width": 1},
                         annotation_text=str(level), annotation_position="right",
                         annotation_font={"color": MUTED})
    figure.update_yaxes(range=[0, 100])
    figure = _style(figure, f"RSI ({config.RSI_PERIOD} days): the rules want it between "
                            f"{config.RSI_MIN} and {config.RSI_MAX}", height=220, legend=False)
    return figure.update_layout(margin={"r": 36})


# ------------------------------------------------------------------ market --
def change_bars(dashboard):
    """One-day change of each market. Blue for a rise, red for a fall."""
    rows = dashboard.sort_values("change_%")
    colours = [BLUE if change >= 0 else RED for change in rows["change_%"]]
    figure = go.Figure(go.Bar(
        x=rows["change_%"], y=rows["market"], orientation="h",
        marker={"color": colours},
        text=[f"{change:+.2f}%" for change in rows["change_%"]],
        textposition="outside", textfont={"color": TEXT}, cliponaxis=False,
        hovertemplate="%{y}: %{x:+.2f}%<extra></extra>"))
    figure.add_vline(x=0, line={"color": MUTED, "width": 1})
    figure.update_xaxes(ticksuffix="%")
    figure = _style(figure, "Change on the last trading day", height=400, legend=False)
    return figure.update_layout(hovermode="closest", margin={"r": 60})


# ----------------------------------------------------------------- company --
def results_bars(rows, title):
    """Sales and profit side by side, in Rs crore, one pair per period."""
    rows = rows.sort_values("period_end")
    labels = [day.strftime("%b %Y") for day in rows["period_end"]]
    figure = go.Figure([
        go.Bar(x=labels, y=rows["revenue"] / 1e7, name="Sales", marker={"color": BLUE},
               hovertemplate="Rs %{y:,.0f} crore<extra>Sales</extra>"),
        go.Bar(x=labels, y=rows["net_income"] / 1e7, name="Profit", marker={"color": ORANGE},
               hovertemplate="Rs %{y:,.0f} crore<extra>Profit</extra>"),
    ])
    figure.update_xaxes(type="category")
    figure = _style(figure, title, height=340, y_title="Rs crore")
    # With only a few periods the bars would become very wide, so leave more air.
    air = min(0.85, max(0.35, 1 - 0.12 * len(rows)))
    return figure.update_layout(barmode="group", bargap=air)


OWNER_GROUPS = [
    ("promoter", "Promoters", BLUE),
    ("fii", "Foreign institutions", ORANGE),
    ("dii", "Indian institutions", AQUA),
    ("public", "Public and others", YELLOW),
]


def ownership_bars(rows):
    """Who owns the company, one bar per quarter, each adding up to 100%."""
    rows = rows.sort_values("quarter_end").tail(8)      # the last two years
    labels = [day.strftime("%b %Y") for day in rows["quarter_end"]]
    figure = go.Figure()
    for column, name, colour in OWNER_GROUPS:
        figure.add_bar(
            y=labels, x=rows[column], name=name, orientation="h",
            marker={"color": colour, "line": {"color": SURFACE, "width": 2}},
            text=[f"{value:.1f}%" if value >= 6 else "" for value in rows[column]],
            textposition="inside", insidetextanchor="middle",
            textfont={"color": TEXT},
            hovertemplate="%{x:.2f}%<extra>" + name + "</extra>")
    figure.update_layout(barmode="stack")
    figure.update_xaxes(range=[0, 100], ticksuffix="%")
    figure.update_yaxes(type="category")
    figure = _style(figure, "Shareholding by quarter", height=190 + 55 * len(rows))
    # Four long names do not fit above a narrow chart, so the legend goes below it.
    return figure.update_layout(
        hovermode="y unified", barcornerradius=0, bargap=0.55,
        margin={"t": 46, "b": 70},
        legend={"traceorder": "normal", "y": -0.28, "yanchor": "top"})


# ---------------------------------------------------------------- backtest --
def growth_chart(equity, benchmark, capital):
    """The account against Nifty, both starting from the same amount."""
    nifty = benchmark / benchmark.iloc[0] * capital
    figure = go.Figure([
        _line(equity.index, equity, "Our rules", BLUE, ",.0f"),
        _line(nifty.index, nifty, "Nifty 50, bought and held", ORANGE, ",.0f"),
    ])
    return _style(figure, f"Value of Rs {capital:,.0f} over time", height=400, y_title="Rs")


def drawdown_chart(equity):
    """How far the account was below its best level so far, in percent."""
    fall = (equity / equity.cummax() - 1) * 100
    figure = go.Figure(go.Scatter(
        x=fall.index, y=fall, mode="lines", line={"color": BLUE, "width": 2},
        fill="tozeroy", fillcolor="rgba(42,120,214,0.10)",
        hovertemplate="%{y:.1f}%<extra>Below the peak</extra>"))
    limit = -config.TOTAL_DRAWDOWN_LIMIT * 100
    figure.add_hline(y=limit, line={"color": MUTED, "width": 1},
                     annotation_text=f"Your limit ({limit:.0f}%)",
                     annotation_position="bottom right", annotation_font={"color": MUTED})
    figure.update_yaxes(ticksuffix="%")
    return _style(figure, "Fall from the highest value reached (drawdown)",
                  height=260, legend=False)


def yearly_bars(by_year):
    """Return of each year: our rules beside Nifty."""
    years = [str(year) for year in by_year.index]
    figure = go.Figure([
        go.Bar(x=years, y=by_year["strategy"] * 100, name="Our rules",
               marker={"color": BLUE}, hovertemplate="%{y:+.1f}%<extra>Our rules</extra>"),
        go.Bar(x=years, y=by_year["nifty"] * 100, name="Nifty 50",
               marker={"color": ORANGE}, hovertemplate="%{y:+.1f}%<extra>Nifty 50</extra>"),
    ])
    figure.update_layout(barmode="group")
    figure.add_hline(y=0, line={"color": MUTED, "width": 1})
    figure.update_xaxes(type="category")
    figure.update_yaxes(ticksuffix="%")
    return _style(figure, "Return in each year", height=340)


def last_days(table, days):
    """The last `days` rows of a table, or all of it when days is None."""
    return table if days is None else table.tail(days)
