"""Talking to the NSE website.

NSE only answers data requests from something that looks like a browser and
has first opened one of its normal pages, so every collector starts here.
"""

import config

BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
FIRST_PAGE = "/companies-listing/corporate-filings-shareholding-pattern"


def session():
    """A web session that NSE accepts: browser-like, with NSE's cookies."""
    try:
        from curl_cffi import requests as web    # installed along with yfinance
        browser = web.Session(impersonate="chrome")
    except Exception:
        import requests as web
        browser = web.Session()
    browser.headers.update({"User-Agent": BROWSER, "Accept-Language": "en-US,en;q=0.9"})
    browser.get(config.NSE_SITE + FIRST_PAGE, timeout=30)
    return browser


def get_json(browser, path, **params):
    """Ask one of NSE's data addresses for its answer as Python data."""
    reply = browser.get(
        config.NSE_SITE + path,
        params=params,
        headers={"Accept": "application/json", "Referer": config.NSE_SITE + FIRST_PAGE},
        timeout=60,
    )
    return reply.json()
