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


class WindowDaysTest(unittest.TestCase):
    def test_a_full_window_has_the_requested_length(self):
        rows = daily("2026-08-13", [1] * 90)
        self.assertEqual(metrics.window_days(rows, "2026-11-10", days=90), 90)

    def test_a_late_start_shortens_the_window_to_the_first_row(self):
        rows = daily("2026-11-09", [2, 3])  # first row 9 Nov, as_of 10 Nov
        self.assertEqual(metrics.window_days(rows, "2026-11-10", days=90, allow_late_start=True), 2)
        self.assertEqual(metrics.window_days(rows, "2026-11-10", days=90), 90)


class NoPolicyTest(unittest.TestCase):
    def test_the_no_policy_marker_is_one_named_constant(self):
        self.assertEqual(metrics.NO_POLICY, "none published")
        self.assertEqual(metrics.buyback_criterion(0.01, 5, metrics.NO_POLICY)["verdict"], "fires")


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


class ShiftDateTest(unittest.TestCase):
    def test_shifts_back_and_forward(self):
        self.assertEqual(metrics.shift_date("2026-11-10", -90), "2026-08-12")
        self.assertEqual(metrics.shift_date("2026-08-12", 90), "2026-11-10")


class FloatGrowthTest(unittest.TestCase):
    @staticmethod
    def rows(day_values):
        return [[ts(d) * 1000, v] for d, v in day_values]

    def test_growth_and_annualized_over_100_days(self):
        prices = self.rows([("2026-08-02", 2.0), ("2026-11-10", 2.0)])
        caps = self.rows([("2026-08-02", 200.0), ("2026-11-10", 220.0)])
        out = metrics.float_growth(prices, caps, "2026-11-10")
        self.assertEqual((out["start"], out["end"], out["days"]),
                         ("2026-08-02", "2026-11-10", 100))
        self.assertAlmostEqual(out["growth"], 0.10)
        self.assertAlmostEqual(out["annualized"], 1.1 ** 3.65 - 1)

    def test_short_history_starts_at_earliest_date_present(self):
        prices = self.rows([("2026-06-01", 2.0), ("2026-11-10", 2.0)])
        caps = self.rows([("2026-06-01", 100.0), ("2026-11-10", 100.0)])
        out = metrics.float_growth(prices, caps, "2026-11-10")
        self.assertEqual(out["start"], "2026-06-01")

    def test_start_is_never_older_than_max_days(self):
        prices = self.rows([("2025-01-01", 2.0), ("2025-11-10", 2.0), ("2026-11-10", 2.0)])
        caps = self.rows([("2025-01-01", 100.0), ("2025-11-10", 100.0), ("2026-11-10", 100.0)])
        out = metrics.float_growth(prices, caps, "2026-11-10")
        self.assertEqual((out["start"], out["days"]), ("2025-11-10", 365))

    def test_missing_as_of_raises(self):
        prices = self.rows([("2026-08-02", 2.0)])
        caps = self.rows([("2026-08-02", 200.0)])
        with self.assertRaises(metrics.IncompleteSeries):
            metrics.float_growth(prices, caps, "2026-11-10")


class CriterionTest(unittest.TestCase):
    def test_fires_when_the_statistic_is_above_the_threshold(self):
        self.assertEqual(metrics.criterion(3.0, 2.0, metrics.ABOVE)["verdict"], "fires")

    def test_holds_when_the_statistic_is_at_or_below_the_threshold(self):
        self.assertEqual(metrics.criterion(2.0, 2.0, metrics.ABOVE)["verdict"], "holds")
        self.assertEqual(metrics.criterion(1.0, 2.0, metrics.ABOVE)["verdict"], "holds")

    def test_drop_criteria_fire_below_minus_threshold(self):
        self.assertEqual(metrics.criterion(-0.5, 0.3, metrics.DROP)["verdict"], "fires")
        self.assertEqual(metrics.criterion(-0.3, 0.3, metrics.DROP)["verdict"], "holds")
        self.assertEqual(metrics.criterion(0.1, 0.3, metrics.DROP)["verdict"], "holds")

    def test_percent_criteria_compare_with_threshold_over_100(self):
        self.assertEqual(metrics.criterion(0.06, 5, metrics.ABOVE_PERCENT)["verdict"], "fires")
        self.assertEqual(metrics.criterion(0.04, 5, metrics.ABOVE_PERCENT)["verdict"], "holds")

    def test_a_null_statistic_is_pending(self):
        self.assertEqual(metrics.criterion(None, 2.0, metrics.ABOVE)["verdict"], "pending")

    def test_a_missing_threshold_is_pending(self):
        out = metrics.criterion(3.0, None, metrics.ABOVE)
        self.assertEqual(out, {"statistic": 3.0, "threshold": None, "verdict": "pending"})

    def test_zero_threshold_is_a_real_threshold(self):
        self.assertEqual(metrics.criterion(0.1, 0, metrics.ABOVE)["verdict"], "fires")

    def test_result_carries_statistic_and_threshold(self):
        self.assertEqual(metrics.criterion(1.0, 2.0, metrics.ABOVE),
                         {"statistic": 1.0, "threshold": 2.0, "verdict": "holds"})


class ChangeTest(unittest.TestCase):
    def test_change_is_last_over_prior_minus_one(self):
        self.assertEqual(metrics.change(150, 100), 0.5)
        self.assertEqual(metrics.change(50, 100), -0.5)

    def test_change_is_none_when_a_side_is_missing_or_prior_is_zero(self):
        self.assertIsNone(metrics.change(None, 100))
        self.assertIsNone(metrics.change(100, None))
        self.assertIsNone(metrics.change(100, 0))


class BuybackCriterionTest(unittest.TestCase):
    def test_no_published_policy_fires_even_without_a_threshold(self):
        out = metrics.buyback_criterion(0.25, None, "none published")
        self.assertEqual(out["verdict"], "fires")

    def test_no_published_policy_fires_even_when_outflows_are_small(self):
        self.assertEqual(metrics.buyback_criterion(0.01, 5, "none published")["verdict"], "fires")

    def test_with_a_policy_the_outflow_share_decides(self):
        self.assertEqual(metrics.buyback_criterion(0.06, 5, "burn")["verdict"], "fires")
        self.assertEqual(metrics.buyback_criterion(0.04, 5, "burn")["verdict"], "holds")

    def test_with_a_policy_and_no_threshold_it_is_pending(self):
        self.assertEqual(metrics.buyback_criterion(0.04, None, "burn")["verdict"], "pending")

    def test_outflow_share_is_outflows_over_holdings(self):
        self.assertEqual(metrics.outflow_share(500, 2000), 0.25)
        self.assertIsNone(metrics.outflow_share(500, 0))
