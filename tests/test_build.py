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

    def test_intents_report_their_missing_days_over_the_trailing_window(self):
        write_snapshot(self.raw, CAPS)
        for name, gap in (("dailyRevenue", date(2026, 11, 5)), ("dailyHoldersRevenue", date(2026, 11, 7))):
            path = self.raw / f"defillama_near-intents_{name}.json"
            rows = json.loads(path.read_text())["totalDataChart"]
            path.write_text(json.dumps({"totalDataChart": [r for r in rows if r[0] != ts(gap)]}))
        build.build(self.raw, self.out, CONFIG)
        intents = json.loads((self.out / "metrics.json").read_text())["intents"]
        self.assertEqual(intents["missing_days"],
                         {"net": ["2026-11-05"], "gross": [], "holders": ["2026-11-07"]})

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

    def test_panel_variants_add_one_candidate_or_leave_one_peer_out(self):
        m = self.build()
        variants = {v["label"]: v for v in m["panel_variants"]}
        # NEAR BASE+NET = 5; peers A = 100, B = 300; candidates C = 500, D = 50.
        expected = {"Panel": 200, "+ C": 300, "+ D": 100, "- A": 300, "- B": 100}
        self.assertEqual(list(variants), list(expected))
        for label, peer_median in expected.items():
            with self.subTest(variant=label):
                self.assertEqual(variants[label]["peer_median"], peer_median)
                self.assertAlmostEqual(variants[label]["near_base_net_ratio"], 5 / peer_median)
                self.assertEqual(variants[label]["c1_verdict"], "pending")  # no k in CONFIG

    def test_c1_verdict_stability_across_panel_variants(self):
        f = self._falsification({"k": 0.03})  # 5/200 = 0.025 holds, 5/100 = 0.05 fires
        metrics_json = json.loads((self.out / "metrics.json").read_text())
        verdicts = {v["label"]: v["c1_verdict"] for v in metrics_json["panel_variants"]}
        self.assertEqual(verdicts["Panel"], f["c1"]["verdict"])
        self.assertEqual(verdicts["+ D"], "fires")
        self.assertFalse(metrics_json["c1_verdict_same_in_all_variants"])

    def test_intents_30_day_buckets_since_the_regime_break(self):
        write_snapshot(self.raw, CAPS)
        config = {**CONFIG, "intents": {**CONFIG["intents"], "regime_break": "2026-09-12"}}
        build.build(self.raw, self.out, config)
        buckets = json.loads((self.out / "metrics.json").read_text())["intents"]["buckets_30d"]
        self.assertEqual(buckets, [
            {"start": "2026-09-12", "end": "2026-10-11", "net": 30, "gross": 120},
            {"start": "2026-10-12", "end": "2026-11-10", "net": 30, "gross": 120},
        ])

    def test_sources_come_from_the_manifest_and_the_fee_methodology(self):
        write_snapshot(self.raw, CAPS)
        manifest = {"as_of": AS_OF, "sources": {
            "defillama_a_dailyFees.json": "https://fees.test/a",
            "coingecko_a_market_chart.json": "https://caps.test/a",
            "defillama_near-intents_dailyRevenue.json": "https://fees.test/intents-net"}}
        (self.raw / "MANIFEST.json").write_text(json.dumps(manifest))
        fees = json.loads((self.raw / "defillama_a_dailyFees.json").read_text())
        fees["methodologyURL"] = "https://method.test/a"
        (self.raw / "defillama_a_dailyFees.json").write_text(json.dumps(fees))
        build.build(self.raw, self.out, CONFIG)
        m = json.loads((self.out / "metrics.json").read_text())
        self.assertEqual(m["chains"]["A"]["sources"], {
            "fees": "https://fees.test/a", "fees_methodology": "https://method.test/a",
            "market_cap": "https://caps.test/a"})
        self.assertEqual(m["chains"]["B"]["sources"],
                         {"fees": None, "fees_methodology": None, "market_cap": None})
        self.assertEqual(m["intents"]["sources"]["net"], "https://fees.test/intents-net")

    def test_panel_rule_and_reasons_are_carried_into_the_metrics(self):
        write_snapshot(self.raw, CAPS)
        config = {**CONFIG,
                  "panel_rule": {"description": "Rule R.", "fee_definition": "base fees"},
                  "chains": [{**c, "reason": f"Why {c['name']}."} for c in CONFIG["chains"]],
                  "candidates": [{**c, "reason": f"Why {c['name']}."}
                                 for c in CONFIG["candidates"]]}
        build.build(self.raw, self.out, config)
        panel = json.loads((self.out / "metrics.json").read_text())["panel"]
        self.assertEqual(panel["rule"], "Rule R.")
        self.assertEqual(panel["fee_definition"], "base fees")
        self.assertEqual(panel["reasons"], {"NEAR": "Why NEAR.", "A": "Why A.", "B": "Why B."})
        self.assertEqual(panel["candidate_reasons"], {"C": "Why C.", "D": "Why D."})

    def test_margins_say_how_far_each_criterion_is_from_firing(self):
        write_snapshot(self.raw, CAPS)
        config = {**CONFIG, "falsification": {**CONFIG["falsification"],
                                              "thresholds": {"k": 0.1, "x": 0.5, "y": 0.25, "z": 30}}}
        build.build(self.raw, self.out, config)
        margins = json.loads((self.out / "metrics.json").read_text())["margins"]
        # Market cap 3650, peer median 200, k 0.1: C1 fires below a denominator of 182.5.
        # BASE fees 365 already exceed it, so no fall in Intents revenue can make C1 fire.
        self.assertEqual(margins["c1"]["intents_net_breakeven"], 182.5 - 365)
        self.assertIsNone(margins["c1"]["intents_net_drop_to_fire"])
        self.assertEqual(margins["c4"], {"policy_test": "fires", "outflow_test": "holds"})
        self.assertIsNone(margins["c2"]["last_net_fires_below"])   # windows before the break

    def test_holders_against_net_since_the_regime_break(self):
        hv = self.build()["intents"]["holders_vs_net"]
        # Net is 1/day all year; holders is 2/day from 1 Nov (the break), 0 before.
        self.assertEqual(hv["net_before_break_in_trailing"], 365 - 10)
        self.assertFalse(hv["holders_equals_net_since_break"])

    def test_post_break_reading_annualizes_net_since_the_break(self):
        pb = self.build()["post_break_reading"]
        self.assertEqual(pb["intents_net_annualized"], 365)        # 1/day
        self.assertEqual(pb["multiple"], 5)                        # 3650 / (365 + 365)
        self.assertEqual(pb["c1_verdict"], "pending")

    def test_rank_rule_is_checked_against_coingecko(self):
        write_snapshot(self.raw, CAPS)
        (self.raw / "coingecko_markets.json").write_text(json.dumps([
            {"id": "near", "market_cap_rank": 20}, {"id": "a", "market_cap_rank": 3},
            {"id": "b", "market_cap_rank": 50}]))
        config = {**CONFIG, "panel_rule": {"max_coingecko_rank": 30}}
        build.build(self.raw, self.out, config)
        m = json.loads((self.out / "metrics.json").read_text())
        self.assertEqual(m["chains"]["B"]["market_cap_rank"], 50)
        self.assertEqual(m["panel"]["max_rank"], 30)
        self.assertEqual(m["panel"]["rank_rule_failures"], ["B"])

    def test_rank_check_is_empty_without_market_data(self):
        m = self.build()
        self.assertIsNone(m["chains"]["A"]["market_cap_rank"])
        self.assertEqual(m["panel"]["rank_rule_failures"], [])

    def test_missing_snapshot_fails_with_a_clear_message(self):
        with self.assertRaises(build.MissingSnapshot) as ctx:
            build.build(self.raw, self.out, CONFIG)
        self.assertIn("make all", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
