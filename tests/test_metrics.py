"""Tests for src/metrics.py: pure functions, hand-computed expectations."""
import unittest
from datetime import date, datetime, timedelta, timezone

from src import metrics


def ts(iso):
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp())


def daily(start_iso, values):
    start = date.fromisoformat(start_iso)
    return [[ts((start + timedelta(days=i)).isoformat()), v] for i, v in enumerate(values)]


class TrailingSumTest(unittest.TestCase):
    def test_sums_the_last_n_days_up_to_and_including_as_of(self):
        rows = daily("2026-11-06", [1, 2, 3, 4, 5])  # 06..10 Nov
        self.assertEqual(metrics.trailing_sum(rows, "2026-11-10", days=3), 3 + 4 + 5)

    def test_ignores_days_after_as_of(self):
        rows = daily("2026-11-09", [1, 2, 1000])  # 11 Nov is a partial day
        self.assertEqual(metrics.trailing_sum(rows, "2026-11-10", days=2), 1 + 2)

    def test_missing_days_inside_the_window_raise(self):
        rows = daily("2026-11-08", [1]) + daily("2026-11-10", [3])  # 9 Nov missing
        with self.assertRaises(metrics.IncompleteSeries):
            metrics.trailing_sum(rows, "2026-11-10", days=3)

    def test_a_few_missing_days_are_filled_by_scaling_when_allowed(self):
        rows = daily("2026-11-06", [2, 2]) + daily("2026-11-09", [2, 2])  # 8 Nov missing
        # 4 days present sum to 8; scaled to the 5-day window: 8 * 5 / 4 = 10
        self.assertEqual(metrics.trailing_sum(rows, "2026-11-10", days=5, max_missing=1), 10)

    def test_more_missing_days_than_allowed_raise(self):
        rows = daily("2026-11-06", [2]) + daily("2026-11-10", [2])  # 3 days missing
        with self.assertRaises(metrics.IncompleteSeries):
            metrics.trailing_sum(rows, "2026-11-10", days=5, max_missing=2)

    def test_missing_days_are_listed(self):
        rows = daily("2026-11-06", [2, 2]) + daily("2026-11-09", [2, 2])
        self.assertEqual(metrics.missing_days(rows, "2026-11-10", days=5), ["2026-11-08"])

    def test_zero_values_are_data_not_gaps(self):
        rows = daily("2026-11-08", [0, 0, 0])
        self.assertEqual(metrics.trailing_sum(rows, "2026-11-10", days=3), 0)

    def test_a_series_that_starts_late_counts_only_its_days_when_allowed(self):
        rows = daily("2026-11-09", [2, 3])
        self.assertEqual(
            metrics.trailing_sum(rows, "2026-11-10", days=5, allow_late_start=True), 5
        )


class AnnualizeTest(unittest.TestCase):
    def test_scales_a_partial_window_to_365_days(self):
        rows = daily("2026-11-09", [2, 3])  # 2 days, total 5
        self.assertAlmostEqual(metrics.annualized(rows, "2026-11-10", days=90), 5 * 365 / 2)

    def test_a_full_window_scales_by_365_over_window(self):
        rows = daily("2026-08-13", [1] * 90)  # 13 Aug .. 10 Nov
        self.assertAlmostEqual(metrics.annualized(rows, "2026-11-10", days=90), 365)


class MultipleTest(unittest.TestCase):
    def test_market_cap_over_denominator(self):
        self.assertEqual(metrics.multiple(1000, 4), 250)

    def test_zero_or_negative_denominator_gives_none(self):
        self.assertIsNone(metrics.multiple(1000, 0))
        self.assertIsNone(metrics.multiple(1000, -5))

    def test_ratio_to_median_of_peers(self):
        self.assertAlmostEqual(metrics.ratio_to_median(300, [100, 200, 400]), 1.5)

    def test_ratio_to_median_ignores_missing_peers(self):
        self.assertAlmostEqual(metrics.ratio_to_median(300, [100, None, 500]), 1.0)


class PerimetersTest(unittest.TestCase):
    def test_four_perimeters_add_the_right_intents_flow(self):
        p = metrics.perimeters(base=10, intents_net=5, intents_holders=4, intents_gross=30)
        self.assertEqual(
            p, {"BASE": 10, "BASE+NET": 15, "BASE+HOLDERS": 14, "BASE+GROSS": 40}
        )


class MarketCapOnTest(unittest.TestCase):
    def test_takes_the_market_cap_dated_as_of(self):
        caps = [[ts("2026-11-09") * 1000, 9.0], [ts("2026-11-10") * 1000, 10.0],
                [ts("2026-11-11") * 1000, 11.0]]
        self.assertEqual(metrics.market_cap_on(caps, "2026-11-10"), 10.0)

    def test_missing_date_raises(self):
        caps = [[ts("2026-11-09") * 1000, 9.0]]
        with self.assertRaises(metrics.IncompleteSeries):
            metrics.market_cap_on(caps, "2026-11-10")


if __name__ == "__main__":
    unittest.main()
