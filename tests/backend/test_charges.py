"""Checks the Zerodha delivery charges against a hand calculation."""

import math

from trading import charges


def test_buy_charges_on_25000():
    # exchange 0.7675 + SEBI 0.025 = 0.7925; GST 18% of that = 0.14265
    # STT 25.00; stamp duty 3.75
    assert math.isclose(charges.buy_charges(25_000), 29.68515, abs_tol=0.0001)


def test_sell_charges_on_25000():
    # exchange 0.7675 + SEBI 0.025 + GST 0.14265 + STT 25.00 + DP charge 15.34
    assert math.isclose(charges.sell_charges(25_000), 41.27515, abs_tol=0.0001)


def test_round_trip_costs_about_0_28_percent():
    total = charges.buy_charges(25_000) + charges.sell_charges(25_000)
    assert 0.0027 < total / 25_000 < 0.0030
