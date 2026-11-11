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
    "intents": {"defillama_slug": "near-intents", "regime_break": "2026-11-01"},
    "windows": {"trailing_days": 365, "run_rate_days": 90, "max_missing_days": 3},
}


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
        (raw / f"coingecko_{cg}_market_chart.json").write_text(json.dumps({"market_caps": caps}))
    (raw / "MANIFEST.json").write_text(json.dumps({"as_of": AS_OF}))


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.out = self.tmp / "processed"

    def build(self):
        write_snapshot(self.raw, {"near": 3650, "a": 36500, "b": 109500})
        build.build(self.raw, self.out, CONFIG)
        return json.loads((self.out / "metrics.json").read_text())

    def test_metrics_carry_the_snapshot_as_of_date(self):
        self.assertEqual(self.build()["as_of"], AS_OF)

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

    def test_holders_revenue_is_annualized_from_the_regime_break(self):
        p = self.build()["near_perimeters"]["BASE+HOLDERS"]
        # 10 days x 2 since 1 Nov -> 20, annualized 20 * 365 / 10 = 730
        self.assertEqual(p["denominator"], 365 + 730)
        self.assertEqual(p["holders_days"], 10)

    def test_a_missing_day_is_scaled_and_reported(self):
        write_snapshot(self.raw, {"near": 3650, "a": 36500, "b": 109500})
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
        write_snapshot(self.raw, {"near": 3650, "a": 36500, "b": 109500})
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

    def test_missing_snapshot_fails_with_a_clear_message(self):
        with self.assertRaises(build.MissingSnapshot) as ctx:
            build.build(self.raw, self.out, CONFIG)
        self.assertIn("make all", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
