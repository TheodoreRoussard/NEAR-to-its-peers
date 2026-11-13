"""Number and date formats shared by the dashboard and the thesis. Pure functions."""
from datetime import date


def fmt_multiple(value):
    return "n/a" if value is None else f"{round(value):,}x"


def fmt_ratio(value):
    return "n/a" if value is None else f"{value:.2f}"


def fmt_usd(value):
    if value is None:
        return "n/a"
    if abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    if abs(value) >= 1e4:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.0f}"


def fmt_change(value, digits=0):
    return "n/a" if value is None else f"{value * 100:+.{digits}f}%"


def fmt_percent(value):
    return "n/a" if value is None else f"{value * 100:.2f}%"


def fmt_day(iso):
    day = date.fromisoformat(iso)
    return f"{day.day} {day.strftime('%b')} {day.year}"


def fmt_short_day(iso):
    day = date.fromisoformat(iso)
    return f"{day.day} {day.strftime('%b')}"


def drop(share):
    return "not set" if share is None else f"{share * 100:.0f}%"


def days_between(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def dates(start, end):
    return f"{fmt_day(start)} to {fmt_day(end)}"


def listing(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
