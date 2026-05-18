"""
app/utils/formatting.py
Date / time serialisation helpers used before JSON responses.
"""

from datetime import date, time


def format_time(t) -> str:
    if isinstance(t, time):
        return t.strftime("%H:%M")
    return str(t)


def format_date(d) -> str:
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    return str(d)
