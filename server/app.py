"""The Kasauti web app: a small local web server.

It answers the page's questions at /api/... with data from the trading
package, and serves the built page (web/dist) at /. Started by
start_kasauti.bat; it only listens on this computer (127.0.0.1).
"""

import threading
from pathlib import Path

import pandas  # noqa: F401  (load pandas before FastAPI: the other order can crash)
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import views
from server.jobs import JOBS
from server.store import STORE

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "web" / "dist"

app = FastAPI(title="Kasauti", docs_url="/api/docs", openapi_url="/api/openapi.json")


def _warm_up():
    """Load the data and the slow pages once at start, so the first clicks are quick."""
    for build in (views.today_page, views.news_page, views.movers_page,
                  lambda: views.stock_page("RELIANCE"), views.before_open, views.market_page):
        try:
            build()
        except Exception:
            pass                       # the page shows its own error when opened


@app.on_event("startup")
def _start():
    if not getattr(app.state, "testing", False):
        threading.Thread(target=_warm_up, daemon=True).start()


@app.exception_handler(Exception)
async def _problem(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


@app.get("/api/status")
def status():
    return {**views.status(), "job": JOBS.snapshot()}


@app.get("/api/today")
def today(money: float | None = None):
    return views.today_page(money)


@app.get("/api/live")
def live(symbols: str = ""):
    """Live prices for a few stocks (comma separated), for the Today page."""
    return views.live_prices(symbols.split(","))


@app.get("/api/before-open")
def before_open():
    return views.before_open()


@app.get("/api/news")
def news_ideas():
    return views.news_page()


@app.get("/api/movers")
def movers():
    return views.movers_page()


@app.get("/api/market")
def market():
    return views.market_page()


@app.get("/api/stocks")
def stocks():
    return views.stock_list()


@app.get("/api/stocks/{symbol}")
def stock(symbol: str):
    found = views.stock_page(symbol.upper())
    if found is None:
        raise HTTPException(404, f"No prices for {symbol}")
    return found


@app.get("/api/stocks/{symbol}/prices")
def stock_prices(symbol: str, days: int | None = None):
    found = views.stock_prices(symbol.upper(), days)
    if found is None:
        raise HTTPException(404, f"No prices for {symbol}")
    return found


@app.get("/api/stocks/{symbol}/reports")
def stock_reports(symbol: str):
    return views.documents(symbol.upper())


@app.get("/api/trades")
def trades():
    return views.trades_page()


class Buy(BaseModel):
    symbol: str
    date: str
    price: float
    quantity: int
    note: str = ""


class Sell(BaseModel):
    row: int
    date: str
    price: float


@app.post("/api/trades/buy")
def buy(order: Buy):
    try:
        return views.record_buy(order.symbol.upper(), order.date, order.price, order.quantity,
                                order.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/trades/sell")
def sell(order: Sell):
    try:
        return views.record_sell(order.row, order.date, order.price)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class Job(BaseModel):
    kind: str


@app.post("/api/jobs")
def start_job(job: Job):
    try:
        started = JOBS.start(job.kind)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not started:
        raise HTTPException(409, "Another update is still running.")
    return JOBS.snapshot()


@app.get("/api/jobs")
def job_status():
    return JOBS.snapshot()


@app.post("/api/reload")
def reload():
    STORE.clear()
    return {"ok": True}


# ---- the page itself: every other address gets the app (it does its own routing) ----
if (PAGE / "assets").exists():
    app.mount("/assets", StaticFiles(directory=PAGE / "assets"), name="assets")


@app.get("/{path:path}")
def page(path: str):
    target = PAGE / path
    if path and target.is_file() and PAGE in target.resolve().parents:
        return FileResponse(target)
    index = PAGE / "index.html"
    if not index.exists():
        raise HTTPException(404, "The page is not built yet (web/dist is missing).")
    return FileResponse(index)
