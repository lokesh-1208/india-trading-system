"""NSE trading holidays, so the app knows which weekdays the market is shut.

Source: NSE circular for the 2026 equity segment holidays (checked 16 Oct 2026 on
cleartax.in and upstox.com). NSE publishes the next year's list each December: add
it here then. For a year that is not listed, only weekends are skipped.
"""

import pandas as pd

NSE_HOLIDAYS = {pd.Timestamp(day) for day in [
    # 2026
    "2026-01-15",   # Maharashtra municipal elections
    "2026-01-26",   # Republic Day
    "2026-03-03",   # Holi
    "2026-03-26",   # Shri Ram Navami
    "2026-03-31",   # Shri Mahavir Jayanti
    "2026-04-03",   # Good Friday
    "2026-04-14",   # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",   # Maharashtra Day
    "2026-05-28",   # Bakri Id
    "2026-06-26",   # Muharram
    "2026-09-14",   # Ganesh Chaturthi
    "2026-10-02",   # Mahatma Gandhi Jayanti
    "2026-10-20",   # Dussehra
    "2026-11-10",   # Diwali Balipratipada
    "2026-11-24",   # Prakash Gurpurb Sri Guru Nanak Dev
    "2026-12-25",   # Christmas
]}


def is_trading_day(day):
    """True on a weekday that is not an NSE holiday."""
    day = pd.Timestamp(day).normalize()
    return day.weekday() < 5 and day not in NSE_HOLIDAYS


def next_trading_day(day):
    """The first trading day after `day`."""
    day = pd.Timestamp(day).normalize() + pd.Timedelta(days=1)
    while not is_trading_day(day):
        day += pd.Timedelta(days=1)
    return day


def this_or_next_trading_day(day):
    """`day` itself if the market opens on it, else the next trading day."""
    day = pd.Timestamp(day).normalize()
    return day if is_trading_day(day) else next_trading_day(day)


def previous_trading_day(day):
    """The last trading day before `day`."""
    day = pd.Timestamp(day).normalize() - pd.Timedelta(days=1)
    while not is_trading_day(day):
        day -= pd.Timedelta(days=1)
    return day


def first_trading_day_of_week(day):
    """The first trading day in the week (Monday to Friday) that contains `day`."""
    monday = pd.Timestamp(day).normalize() - pd.Timedelta(days=pd.Timestamp(day).weekday())
    return this_or_next_trading_day(monday)
