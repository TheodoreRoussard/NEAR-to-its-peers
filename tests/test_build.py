"""Tests for src/build.py on a tiny hand-computed snapshot."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src import build

AS_OF = "2026-11-10"
CONFIG = {
    "chains": [
        {"name": "NEAR", "defillama_slug": "near", "coingecko_id": "near"},
        {"name": "A", "defillama_slug": "a", "coingecko_id": "a"},
        {"name": "B", "defillama_slug": "b", "coingecko_id": "b"},
    ],
    "candidates": [
        {"name": "C", "defillama_slug": "c", "coingecko_id": "c"},
        {"name": "D", "defillama_slug": "d", "coingecko_id": "d"},
    ],
    "intents": {"defillama_slug": "near-intents", "regime_break": "2026-11-01",
                "buyback_holdings_near": 2000, "buyback_outflows_near": 500,
                "buyback_policy": "none published",
                "buyback_outflows_period": "cumulative, from the first buyback to buyback_checked_on",
                "buyback_checked_on": "2026-11-10", "buyback_source": "https://example.test/acct"},
    "falsification": {"c1": "F1", "c2": "F2", "c3": "F3", "c4": "F4", "thresholds": {}},
    "windows": {"trailing_days": 365, "max_missing_days": 3},
}

# Fees are 1/day (365 a year) everywhere, so multiple = market cap / 365.
# Candidates: C = 500 (above the peers), D = 50 (below them).
CAPS = {"near": 3650, "a": 36500, "b": 109500, "c": 182500, "d": 18250}


def ts(day):
    return int(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).timestamp())


def daily(value_on, days=400):
    """Daily rows ending one day AFTER as_of (a partial day that must be ignored)."""
    end = date.fromisoformat(AS_OF) + timedelta(days=1)
    return [[ts(end - timedelta(days=i)), value_on(end - timedelta(days=i))]
            for i in reversed(range(days))]


def write_snapshot(raw, market_caps):
    raw.mkdir(parents=True)
    files = {
        "defillama_near_dailyFees.json": daily(lambda d: 1),
        "defillama_a_dailyFees.json": daily(lambda d: 1),
        "defillama_b_dailyFees.json": daily(lambda d: 1),
        "defillama_c_dailyFees.json": daily(lambda d: 1),
        "defillama_d_dailyFees.json": daily(lambda d: 1),
        "defillama_near-intents_dailyRevenue.json": daily(lambda d: 1),
        "defillama_near-intents_dailyFees.json": daily(lambda d: 4),
        "defillama_near-intents_dailyHoldersRevenue.json":
            daily(lambda d: 2 if d >= date(2026, 11, 1) else 0),
    }
    for name, rows in files.items():
        rows[-1][1] = 10_000  # the partial day after as_of: must never be counted
        (raw / name).write_text(json.dumps({"totalDataChart": rows}))
    for cg, cap in market_caps.items():
        caps = [[ts(date.fromisoformat(AS_OF)) * 1000, cap],
                [ts(date.fromisoformat(AS_OF) + timedelta(days=1)) * 1000, cap * 99]]
        start = ts(date.fromisoformat(AS_OF) - timedelta(days=100)) * 1000
        caps.insert(0, [start, cap / 2])  # price is 2 throughout: float doubles in 100 days
        prices = [[row[0], 2] for row in caps]
        (raw / f"coingecko_{cg}_market_chart.json").write_text(
            json.dumps({"prices": prices, "market_caps": caps}))
    (raw / "MANIFEST.json").write_text(json.dumps({"as_of": AS_OF}))


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.out = self.tmp / "processed"

    def build(self):
        write_snapshot(self.raw, CAPS)
        build.build(self.raw, self.out, CONFIG)
        return json.loads((self.out / "metrics.json").read_text())

    def test_metrics_carry_the_snapshot_as_of_date(self):
        self.assertEqual(self.build()["as_of"], AS_OF)

    def test_every_chain_carries_its_float_growth(self):
        for chain in self.build()["chains"].values():
            fg = chain["float_growth"]
            self.assertEqual((fg["start"], fg["end"], fg["days"]), ("2026-08-02", AS_OF, 100))
            self.assertEqual(fg["growth"], 1.0)
            self.assertAlmostEqual(fg["annualized"], 2 ** 3.65 - 1)

    def test_add_one_ratio_uses_the_median_of_the_peers_plus_that_candidate(self):
        add_one = {row["name"]: row for row in self.build()["add_one"]}
        self.assertEqual(list(add_one), ["C", "D"])
        c = add_one["C"]
        self.assertEqual((c["market_cap"], c["fees_trailing"], c["multiple"], c["missing_days"]),
                         (182500, 365, 500, []))
        # BASE+NET multiple is 5. Median(100, 300, 500) = 300, median(50, 100, 300) = 100.
        self.assertAlmostEqual(c["near_base_net_ratio_to_median_with_candidate"], 5 / 300)
        self.assertAlmostEqual(add_one["D"]["multiple"], 50)
        self.assertAlmostEqual(add_one["D"]["near_base_net_ratio_to_median_with_candidate"], 5 / 100)

    def test_candidates_never_enter_the_peer_median_or_the_chains(self):
        m = self.build()
        self.assertEqual(m["peer_median_multiple"], 200)          # median(100, 300) only
        self.assertEqual(set(m["chains"]), {"NEAR", "A", "B"})
        self.assertAlmostEqual(m["near_perimeters"]["BASE+NET"]["ratio_to_peer_median"], 5 / 200)

    def test_chain_multiples_use_the_as_of_market_cap_and_trailing_fees(self):
        chains = self.build()["chains"]
        self.assertEqual(chains["A"]["fees_trailing"], 365)
        self.assertEqual(chains["A"]["market_cap"], 36500)
        self.assertEqual(chains["A"]["multiple"], 100)
        self.assertEqual(chains["B"]["multiple"], 300)
        self.assertEqual(chains["NEAR"]["multiple"], 10)

    def test_near_perimeters_and_ratios_to_the_peer_median(self):
        m = self.build()
        p = m["near_perimeters"]
        self.assertEqual(m["peer_median_multiple"], 200)          # median(100, 300)
        self.assertEqual(p["BASE"]["multiple"], 10)               # 3650 / 365
        self.assertEqual(p["BASE+NET"]["multiple"], 5)            # 3650 / (365 + 365)
        self.assertEqual(p["BASE+GROSS"]["multiple"], 2)          # 3650 / (365 + 1460)
        self.assertAlmostEqual(p["BASE+NET"]["ratio_to_peer_median"], 5 / 200)

    def test_every_near_perimeter_is_a_trailing_365_day_sum(self):
        for name, perimeter in self.build()["near_perimeters"].items():
            with self.subTest(perimeter=name):
                self.assertEqual(perimeter["basis"], "trailing_365")

    def test_holders_perimeter_adds_the_full_trailing_holders_sum(self):
        p = self.build()["near_perimeters"]
        # Holders are 2/day from 1 Nov (10 days) and 0 before: trailing-365 sum = 20.
        self.assertEqual(p["BASE+HOLDERS"]["denominator"], 365 + 20)
        self.assertEqual(p["BASE+HOLDERS"]["multiple"], 3650 / 385)
        self.assertEqual(p["BASE+NET"]["denominator"], 365 + 365)
        self.assertEqual(p["BASE+GROSS"]["denominator"], 365 + 1460)

    def test_holders_run_rate_since_the_regime_break_is_informational(self):
        p = self.build()["near_perimeters"]
        # 10 days x 2 since 1 Nov -> 20, annualized 20 * 365 / 10 = 730
        self.assertEqual(p["BASE+HOLDERS"]["holders_annualized_since_regime_break"], 730)
        self.assertEqual(p["BASE+HOLDERS"]["holders_days"], 10)
        for name in ("BASE", "BASE+NET", "BASE+GROSS"):
            self.assertNotIn("holders_days", p[name])
            self.assertNotIn("holders_annualized_since_regime_break", p[name])

    def test_a_missing_day_is_scaled_and_reported(self):
        write_snapshot(self.raw, CAPS)
        path = self.raw / "defillama_a_dailyFees.json"
        rows = json.loads(path.read_text())["totalDataChart"]
        gap_ts = ts(date(2026, 11, 5))
        path.write_text(json.dumps({"totalDataChart": [r for r in rows if r[0] != gap_ts]}))

        build.build(self.raw, self.out, CONFIG)
        a = json.loads((self.out / "metrics.json").read_text())["chains"]["A"]

        self.assertEqual(a["missing_days"], ["2026-11-05"])
        self.assertAlmostEqual(a["fees_trailing"], 365)  # 364 days of 1, scaled to 365

    def test_intents_windows_are_null_when_they_start_before_the_regime_break(self):
        intents = self.build()["intents"]
        w = intents["windows"]
        self.assertEqual(intents["regime_break"], "2026-11-01")
        self.assertEqual(w["last_90d"]["start"], "2026-08-13")
        self.assertEqual(w["last_90d"]["end"], AS_OF)
        self.assertEqual(w["prior_90d"]["start"], "2026-05-15")
        self.assertEqual(w["prior_90d"]["end"], "2026-08-12")
        for window in w.values():
            for key in ("net", "gross", "holders", "net_over_gross"):
                self.assertIsNone(window[key])
        self.assertEqual(intents["run_rate_90d"],
                         {"net": None, "gross": None, "holders": None})

    def test_intents_windows_and_run_rates_after_the_regime_break(self):
        write_snapshot(self.raw, CAPS)
        path = self.raw / "defillama_near-intents_dailyHoldersRevenue.json"
        rows = daily(lambda d: 2)
        rows[-1][1] = 10_000
        path.write_text(json.dumps({"totalDataChart": rows}))
        config = {**CONFIG, "intents": {**CONFIG["intents"], "regime_break": "2025-01-01"}}
        build.build(self.raw, self.out, config)
        intents = json.loads((self.out / "metrics.json").read_text())["intents"]
        last, prior = intents["windows"]["last_90d"], intents["windows"]["prior_90d"]
        self.assertEqual((last["net"], last["gross"], last["holders"]), (90, 360, 180))
        self.assertEqual(last["net_over_gross"], 0.25)
        self.assertEqual((prior["net"], prior["gross"], prior["holders"]), (90, 360, 180))
        self.assertEqual(intents["run_rate_90d"],
                         {"net": 90 * 365 / 90, "gross": 360 * 365 / 90, "holders": 180 * 365 / 90})
        self.assertEqual(intents["run_rate_90d"]["net"], 365)

    def test_falsification_is_pending_without_thresholds_but_c4_fires_on_policy(self):
        f = self.build()["falsification"]
        # NEAR BASE+NET: multiple 3650 / (365 + 365) = 5; peer multiples 100 and 300, median 200.
        self.assertEqual(f["c1"], {"formula": "F1", "statistic": 5 / 200,
                                   "threshold": None, "verdict": "pending"})
        for key in ("c2", "c3"):  # windows start before the regime break: null
            self.assertEqual(f[key]["statistic"], None)
            self.assertEqual(f[key]["verdict"], "pending")
        self.assertEqual(f["c2"]["formula"], "F2")
        self.assertEqual(f["c4"], {"formula": "F4", "statistic": 0.25, "threshold": None,
                                   "verdict": "fires", "policy": "none published",
                                   "holdings_near": 2000, "outflows_near": 500,
                                   "checked_on": "2026-11-10",
                                   "outflows_period": "cumulative, from the first buyback to buyback_checked_on",
                                   "source": "https://example.test/acct"})

    def _falsification(self, thresholds, last_net=1, policy="burn"):
        write_snapshot(self.raw, CAPS)
        rows = daily(lambda d: last_net if d > date(2026, 8, 12) else 2)
        rows[-1][1] = 10_000
        (self.raw / "defillama_near-intents_dailyRevenue.json").write_text(
            json.dumps({"totalDataChart": rows}))
        config = {**CONFIG,
                  "intents": {**CONFIG["intents"], "regime_break": "2025-01-01",
                              "buyback_policy": policy},
                  "falsification": {**CONFIG["falsification"], "thresholds": thresholds}}
        build.build(self.raw, self.out, config)
        return json.loads((self.out / "metrics.json").read_text())["falsification"]

    def test_c2_and_c3_compare_the_last_90_days_with_the_prior_90(self):
        # last net 90 (1/day) vs prior net 180 (2/day): -50%. Gross is 360 in both
        # windows, so net/gross goes 0.25 vs 0.5: also -50%.
        f = self._falsification({"x": 0.4, "y": 0.6})
        self.assertEqual(f["c2"]["statistic"], -0.5)
        self.assertEqual(f["c2"]["verdict"], "fires")
        self.assertEqual(f["c3"]["statistic"], -0.5)
        self.assertEqual(f["c3"]["verdict"], "holds")

    def test_c1_and_c4_use_their_thresholds_when_set(self):
        f = self._falsification({"k": 0.01, "z": 30})
        self.assertEqual(f["c1"]["verdict"], "fires")  # 0.025 > 0.01
        self.assertEqual(f["c4"]["verdict"], "holds")  # policy exists, 0.25 <= 0.30
        self.assertEqual(f["c4"]["threshold"], 30)

    def test_c4_fires_when_the_outflow_share_exceeds_z_percent(self):
        f = self._falsification({"z": 20})
        self.assertEqual(f["c4"]["verdict"], "fires")  # 0.25 > 0.20

    def test_missing_snapshot_fails_with_a_clear_message(self):
        with self.assertRaises(build.MissingSnapshot) as ctx:
            build.build(self.raw, self.out, CONFIG)
        self.assertIn("make all", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
