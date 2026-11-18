"""Zerodha intraday (MIS) equity charges for one round trip."""

from . import settings as s


def _brokerage(value):
    return min(s.BROKERAGE_CAP, value * s.BROKERAGE_PCT)


def round_trip(buy_value, sell_value):
    """Total charges in rupees for one buy and one sell."""
    brokerage = _brokerage(buy_value) + _brokerage(sell_value)
    exchange = (buy_value + sell_value) * s.EXCHANGE_TXN
    sebi = (buy_value + sell_value) * s.SEBI_FEE
    gst = (brokerage + exchange + sebi) * s.GST
    stt = sell_value * s.STT_SELL
    stamp = buy_value * s.STAMP_BUY
    return brokerage + exchange + sebi + gst + stt + stamp
