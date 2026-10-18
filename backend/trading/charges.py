"""Zerodha equity delivery charges. Rates are in config.py."""

import config


def buy_charges(value):
    """Charges in rupees for buying shares worth `value` rupees."""
    brokerage = value * config.BROKERAGE
    exchange = value * config.EXCHANGE_TXN
    sebi = value * config.SEBI_FEE
    gst = (brokerage + exchange + sebi) * config.GST
    return (brokerage + exchange + sebi + gst
            + value * config.STT + value * config.STAMP_DUTY)


def sell_charges(value):
    """Charges in rupees for selling shares worth `value` rupees."""
    brokerage = value * config.BROKERAGE
    exchange = value * config.EXCHANGE_TXN
    sebi = value * config.SEBI_FEE
    gst = (brokerage + exchange + sebi) * config.GST
    return (brokerage + exchange + sebi + gst
            + value * config.STT + config.DP_CHARGE)
