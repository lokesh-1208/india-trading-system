"""Read-only Zerodha connection (Kite Connect "Personal" plan, free).

What it gives Kasauti: your funds, today's positions and today's orders. It does NOT place
orders and it gives no market data (that needs the paid plan). Talks to Kite's REST API
directly; no extra library needed.

Daily login: Kite's access token ends every morning, so each day you click "Connect Zerodha",
log in on Zerodha's own page, and Kite sends the browser back to Kasauti with a one-time
request token. Your password never touches Kasauti. Your API key and secret are kept in
journal/zerodha_app.json and the day's token in data/zerodha_token.json; neither is uploaded.
"""

import hashlib
import json

import httpx
import pandas as pd

from . import settings as s

API = "https://api.kite.trade"
LOGIN = "https://kite.zerodha.com/connect/login"
REDIRECT_URL = "http://127.0.0.1:8765/api/zerodha/callback"
IST = "Asia/Kolkata"


class ZerodhaError(Exception):
    pass


def _today():
    return pd.Timestamp.now(tz=IST).strftime("%Y-%m-%d")


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")


def keys():
    found = _read(s.ZERODHA_APP_FILE)
    if found and found.get("api_key") and found.get("api_secret"):
        return found["api_key"], found["api_secret"]
    return None


def save_keys(api_key, api_secret):
    api_key, api_secret = (api_key or "").strip(), (api_secret or "").strip()
    if len(api_key) < 6 or len(api_secret) < 6:
        raise ZerodhaError("Enter both the API key and the API secret from developers.kite.trade.")
    _write(s.ZERODHA_APP_FILE, {"api_key": api_key, "api_secret": api_secret})
    forget_token()


def forget_keys():
    """Remove the saved API key and secret, and today's login."""
    try:
        s.ZERODHA_APP_FILE.unlink()
    except OSError:
        pass
    forget_token()


def forget_token():
    try:
        s.ZERODHA_TOKEN_FILE.unlink()
    except OSError:
        pass


def token_today():
    found = _read(s.ZERODHA_TOKEN_FILE)
    return found if found and found.get("date") == _today() and found.get("access_token") else None


def login_url():
    pair = keys()
    return f"{LOGIN}?v=3&api_key={pair[0]}" if pair else None


def status():
    token = token_today()
    pair = keys()
    return {"configured": bool(pair), "connected": bool(token and pair),
            "user": token.get("user") if token else None,
            "login_url": login_url(), "redirect_url": REDIRECT_URL,
            "key_hint": (pair[0][:3] + "…" + pair[0][-2:]) if pair else None}


def _fail(response):
    try:
        body = response.json()
    except ValueError:
        body = {}
    message = body.get("message") or f"Zerodha answered {response.status_code}."
    if body.get("error_type") == "TokenException" or response.status_code == 403:
        forget_token()
        message = "Today's Zerodha login has ended. Click Connect Zerodha again. (" + message + ")"
    raise ZerodhaError(message)


def exchange_token(request_token, client=None):
    """Swap the one-time request token (from the login redirect) for today's access token."""
    pair = keys()
    if not pair:
        raise ZerodhaError("Save your API key and secret first.")
    api_key, secret = pair
    checksum = hashlib.sha256((api_key + request_token + secret).encode()).hexdigest()
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        response = client.post(f"{API}/session/token", headers={"X-Kite-Version": "3"},
                               data={"api_key": api_key, "request_token": request_token, "checksum": checksum})
    except httpx.HTTPError as exc:
        raise ZerodhaError(f"Could not reach Zerodha: {exc}")
    finally:
        if own:
            client.close()
    if response.status_code != 200:
        _fail(response)
    info = response.json()["data"]
    _write(s.ZERODHA_TOKEN_FILE, {"date": _today(), "access_token": info["access_token"],
                                  "user": info.get("user_name") or info.get("user_id")})
    return status()


def _get(path, client=None):
    pair, token = keys(), token_today()
    if not pair or not token:
        raise ZerodhaError("Not connected to Zerodha today.")
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        response = client.get(f"{API}{path}", headers={
            "X-Kite-Version": "3", "Authorization": f"token {pair[0]}:{token['access_token']}"})
    except httpx.HTTPError as exc:
        raise ZerodhaError(f"Could not reach Zerodha: {exc}")
    finally:
        if own:
            client.close()
    if response.status_code != 200:
        _fail(response)
    return response.json()["data"]


def account(client=None):
    """Funds, today's positions and today's orders, in plain numbers."""
    margin = _get("/user/margins/equity", client)
    positions = _get("/portfolio/positions", client)
    orders = _get("/orders", client)
    available = margin.get("available", {})
    used = margin.get("utilised", {})
    day = positions.get("day", [])
    return {
        "funds": {"available": round(float(available.get("live_balance", available.get("cash", 0))), 2),
                  "used": round(float(used.get("debits", 0)), 2), "net": round(float(margin.get("net", 0)), 2)},
        "positions": [{"symbol": p["tradingsymbol"], "product": p.get("product"), "qty": p["quantity"],
                       "average": p.get("average_price"), "last": p.get("last_price"), "pnl": p.get("pnl")}
                      for p in day],
        "pnl": round(sum(float(p.get("pnl") or 0) for p in day), 2),
        "orders": [{"time": str(o.get("order_timestamp", ""))[-8:-3], "symbol": o["tradingsymbol"],
                    "side": o["transaction_type"], "qty": o["quantity"], "filled": o.get("filled_quantity"),
                    "type": o.get("order_type"), "price": o.get("price"), "trigger": o.get("trigger_price"),
                    "average": o.get("average_price"), "status": o["status"], "product": o.get("product")}
                   for o in sorted(orders, key=lambda o: str(o.get("order_timestamp", "")), reverse=True)[:40]],
    }
