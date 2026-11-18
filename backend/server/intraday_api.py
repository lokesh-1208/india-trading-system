"""Intraday tab: the web addresses the page uses. Kept apart from the swing model's addresses."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from intraday import guard, journal, scan, zerodha
from intraday import settings as s

router = APIRouter()
REPORTS = Path(s.REPORT_DIR)


# ---- the day's rules --------------------------------------------------------
@router.get("/api/intraday/guard")
def day_guard():
    return guard.day_status()


# ---- the 9:30 scan ------------------------------------------------------------
class ScanRequest(BaseModel):
    full: bool = True


@router.get("/api/intraday/scan")
def scan_state():
    return {"run": scan.RUNNER.snapshot(), "result": scan.latest()}


@router.post("/api/intraday/scan")
def scan_start(request: ScanRequest):
    if not scan.RUNNER.start(full=request.full):
        raise HTTPException(409, "A scan is already running.")
    return {"run": scan.RUNNER.snapshot(), "result": scan.latest()}


# ---- your intraday journal --------------------------------------------------------
class OpenTrade(BaseModel):
    symbol: str
    side: str
    qty: int
    entry: float
    stop: float
    target: float | None = None
    rule: str = "own"
    note: str = ""


class CloseTrade(BaseModel):
    id: int
    exit: float


class TradeId(BaseModel):
    id: int


@router.get("/api/intraday/journal")
def journal_page():
    return journal.page()


@router.post("/api/intraday/journal/open")
def journal_open(trade: OpenTrade):
    status = guard.day_status()
    if not status["entries_allowed"]:
        raise HTTPException(409, "Not now: " + "; ".join(status["blockers"]) + ".")
    try:
        journal.open_trade(trade.symbol, trade.side, trade.qty, trade.entry, trade.stop,
                           trade.target, trade.rule, trade.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return journal.page()


@router.post("/api/intraday/journal/close")
def journal_close(trade: CloseTrade):
    try:
        journal.close_trade(trade.id, trade.exit)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return journal.page()


@router.post("/api/intraday/journal/delete")
def journal_delete(trade: TradeId):
    try:
        journal.delete_trade(trade.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return journal.page()


# ---- what the backtests found ---------------------------------------------------------
@router.get("/api/intraday/evidence")
def evidence():
    out = []
    for name, label in [("large", "Large caps (59 stocks)"), ("nifty200", "Nifty 200, stocks in play"),
                        ("nifty500", "Nifty 500, stocks in play")]:
        try:
            out.append({"universe": label, **json.loads((REPORTS / f"intraday_results_{name}.json").read_text("utf-8"))})
        except (OSError, ValueError):
            continue
    return out


# ---- Zerodha ---------------------------------------------------------------------------
class Keys(BaseModel):
    api_key: str
    api_secret: str


@router.get("/api/zerodha/status")
def zerodha_status():
    return zerodha.status()


@router.post("/api/zerodha/keys")
def zerodha_keys(pair: Keys):
    try:
        zerodha.save_keys(pair.api_key, pair.api_secret)
    except zerodha.ZerodhaError as exc:
        raise HTTPException(400, str(exc))
    return zerodha.status()


@router.get("/api/zerodha/callback")
def zerodha_callback(request_token: str = "", status: str = "", action: str = ""):
    """Zerodha sends the browser here after you log in."""
    if status != "success" or not request_token:
        return RedirectResponse("/settings?zerodha=failed", status_code=302)
    try:
        zerodha.exchange_token(request_token)
    except zerodha.ZerodhaError:
        return RedirectResponse("/settings?zerodha=failed", status_code=302)
    return RedirectResponse("/settings?zerodha=connected", status_code=302)


@router.get("/api/zerodha/account")
def zerodha_account():
    try:
        return zerodha.account()
    except zerodha.ZerodhaError as exc:
        raise HTTPException(502, str(exc))


@router.post("/api/zerodha/forget-keys")
def zerodha_forget_keys():
    zerodha.forget_keys()
    return zerodha.status()


@router.post("/api/zerodha/disconnect")
def zerodha_disconnect():
    zerodha.forget_token()
    return zerodha.status()
