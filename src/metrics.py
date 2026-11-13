"""Pure functions: trailing sums, annualization, multiples, perimeters, ratios.

Series are lists of [unix_seconds, value] daily rows (DefiLlama format).
Dates are ISO strings. Nothing here reads files, the network or the clock.
"""
import math
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


def window_days(rows, as_of, days, allow_late_start=False):
    """Length in days of the window `trailing_sum` / `annualized` actually use."""
    return _window(rows, as_of, days, allow_late_start)[2]


def trailing_sum(rows, as_of, days, allow_late_start=False, max_missing=0):
    """Sum of the `days` daily values ending on as_of. Zeros count as data.

    Up to `max_missing` missing days are filled by scaling the sum of the days
    present to the full window; more than that raises IncompleteSeries.
    """
    present, missing, length = _window(rows, as_of, days, allow_late_start)
    if len(missing) > max_missing:
        raise IncompleteSeries(f"{len(missing)} missing days, first {missing[0]}")
    return math.fsum(present.values()) * length / len(present)


def annualized(rows, as_of, days, max_missing=0):
    """Run-rate: the sum over the available part of the window, scaled to 365 days."""
    length = window_days(rows, as_of, days, allow_late_start=True)
    return trailing_sum(rows, as_of, days, True, max_missing) * 365 / length


def buckets(rows, as_of, size, earliest, max_missing=0):
    """Consecutive `size`-day sums ending on as_of, oldest first, going back as long as a
    whole bucket starts on or after both `earliest` and the first day of data (a partial
    bucket would read as a drop)."""
    if rows:
        earliest = max(earliest, min(_day(t) for t, _ in rows).isoformat())
    out = []
    end = as_of
    while shift_date(end, -(size - 1)) >= earliest:
        start = shift_date(end, -(size - 1))
        out.append({"start": start, "end": end,
                    "sum": trailing_sum(rows, end, size, max_missing=max_missing)})
        end = shift_date(start, -1)
    return out[::-1]


def sum_between(rows, start, end):
    """Sum of the values dated from start to end inclusive (ISO dates); absent days count 0."""
    lo, hi = date.fromisoformat(start), date.fromisoformat(end)
    return math.fsum(v for t, v in rows if lo <= _day(t) <= hi)


def equal_between(a_rows, b_rows, start, end):
    """True when two series hold the same value on every day from start to end inclusive."""
    lo, hi = date.fromisoformat(start), date.fromisoformat(end)
    a = {_day(t): v for t, v in a_rows if lo <= _day(t) <= hi}
    b = {_day(t): v for t, v in b_rows if lo <= _day(t) <= hi}
    return a == b


def shift_date(iso, days):
    """The ISO date `days` after `iso` (negative `days` goes back)."""
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


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


def float_growth(prices, market_caps, as_of, max_days=365):
    """Growth of the circulating-supply proxy (market cap / price) up to as_of.

    Starts at the earliest date present in both series that is not older than
    `as_of - max_days`. Context only: it never enters a multiple.
    """
    end = date.fromisoformat(as_of)
    oldest = end - timedelta(days=max_days)
    price_by_day = {_day(t / 1000): v for t, v in prices}
    cap_by_day = {_day(t / 1000): v for t, v in market_caps}
    both = sorted(d for d in price_by_day.keys() & cap_by_day.keys() if oldest <= d <= end)
    if not both or both[-1] != end:
        raise IncompleteSeries(f"no price and market cap on {as_of}")
    start = both[0]
    days = (end - start).days
    if days == 0:
        raise IncompleteSeries(f"no history before {as_of}")
    s_start = cap_by_day[start] / price_by_day[start]
    s_end = cap_by_day[end] / price_by_day[end]
    return {"start": start.isoformat(), "end": as_of, "days": days,
            "growth": s_end / s_start - 1,
            "annualized": (s_end / s_start) ** (365 / days) - 1}


# How a criterion compares its statistic with its threshold.
ABOVE = "above"                  # fires if statistic > threshold
DROP = "drop"                    # fires if statistic < -threshold
ABOVE_PERCENT = "above_percent"  # fires if statistic > threshold / 100


def criterion(statistic, threshold, fires_if):
    """Statistic, threshold and verdict of one falsification criterion.

    The verdict is "pending" when the statistic is None or the threshold is
    missing (None); otherwise "fires" or "holds" according to `fires_if`.
    """
    result = {"statistic": statistic, "threshold": threshold, "verdict": "pending"}
    if statistic is None or threshold is None:
        return result
    fires = {ABOVE: statistic > threshold,
             DROP: statistic < -threshold,
             ABOVE_PERCENT: statistic > threshold / 100}[fires_if]
    result["verdict"] = "fires" if fires else "holds"
    return result


def change(last, prior):
    """last / prior - 1; None when a side is missing or the prior is zero."""
    if last is None or prior is None or prior == 0:
        return None
    return last / prior - 1


# The buyback_policy value meaning no burn or lock policy is published (C4 fires on it).
def c1_breakeven(market_cap, peer_median, k, base_fees, intents_net):
    """Intents net revenue below which C1 would fire, holding NEAR's market cap and the peer
    median fixed, and the share of current Intents net revenue that would have to disappear.

    The share is None when no fall can make C1 fire (base fees alone suffice) or when C1
    already fires.
    """
    if k is None or None in (market_cap, peer_median, base_fees, intents_net):
        return None, None
    breakeven = market_cap / (k * peer_median) - base_fees
    if breakeven <= 0 or breakeven >= intents_net:
        return breakeven, None
    return breakeven, 1 - breakeven / intents_net


NO_POLICY = "none published"


def outflow_share(outflows, holdings):
    """outflows / holdings; None when holdings are zero."""
    return None if holdings == 0 else outflows / holdings


def buyback_criterion(statistic, threshold, policy):
    """C4: fires on an outflow share above threshold/100, or whenever no policy is published."""
    result = criterion(statistic, threshold, ABOVE_PERCENT)
    if policy == NO_POLICY:
        result["verdict"] = "fires"
    return result

