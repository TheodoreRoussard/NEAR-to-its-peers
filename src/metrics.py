"""Pure functions: trailing sums, annualization, multiples, perimeters, ratios.

Series are lists of [unix_seconds, value] daily rows (DefiLlama format).
Dates are ISO strings. Nothing here reads files, the network or the clock.
"""
from datetime import date, datetime, timedelta, timezone
from statistics import median


class IncompleteSeries(Exception):
    """A required day is missing from a series."""


def _day(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date()


def _window(rows, as_of, days, allow_late_start=False):
    """(values present keyed by date, missing ISO dates, window length) for the
    `days` days ending on as_of (inclusive)."""
    end = date.fromisoformat(as_of)
    start = end - timedelta(days=days - 1)
    by_day = {_day(t): v for t, v in rows}
    first = min(by_day) if by_day else end
    if allow_late_start and first > start:
        start = first
    present, missing = {}, []
    day = start
    while day <= end:
        if day in by_day:
            present[day] = by_day[day]
        else:
            missing.append(day.isoformat())
        day += timedelta(days=1)
    return present, missing, (end - start).days + 1


def missing_days(rows, as_of, days, allow_late_start=False):
    """ISO dates with no value in the window."""
    return _window(rows, as_of, days, allow_late_start)[1]


def trailing_sum(rows, as_of, days, allow_late_start=False, max_missing=0):
    """Sum of the `days` daily values ending on as_of. Zeros count as data.

    Up to `max_missing` missing days are filled by scaling the sum of the days
    present to the full window; more than that raises IncompleteSeries.
    """
    present, missing, length = _window(rows, as_of, days, allow_late_start)
    if len(missing) > max_missing:
        raise IncompleteSeries(f"{len(missing)} missing days, first {missing[0]}")
    return sum(present.values()) * length / len(present)


def annualized(rows, as_of, days, max_missing=0):
    """Run-rate: the sum over the available part of the window, scaled to 365 days."""
    present, missing, length = _window(rows, as_of, days, allow_late_start=True)
    return trailing_sum(rows, as_of, days, True, max_missing) * 365 / length


def multiple(market_cap, denominator):
    """Market cap / denominator; None when the denominator is zero or negative."""
    if denominator is None or denominator <= 0:
        return None
    return market_cap / denominator


def ratio_to_median(value, peer_values):
    """value / median of the peers that have a value."""
    peers = [v for v in peer_values if v is not None]
    return value / median(peers)


def perimeters(base, intents_net, intents_holders, intents_gross):
    """NEAR denominators: BASE plus each Intents flow."""
    return {
        "BASE": base,
        "BASE+NET": base + intents_net,
        "BASE+HOLDERS": base + intents_holders,
        "BASE+GROSS": base + intents_gross,
    }


def market_cap_on(market_caps, as_of):
    """Market cap dated as_of from CoinGecko [unix_ms, value] rows."""
    target = date.fromisoformat(as_of)
    for t_ms, value in market_caps:
        if _day(t_ms / 1000) == target:
            return value
    raise IncompleteSeries(f"no market cap on {as_of}")
