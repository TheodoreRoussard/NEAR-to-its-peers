"""Tests for src/fetch.py. No network: get_json is a fake keyed by URL."""
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from src import fetch

ROOT = Path(__file__).resolve().parent.parent
DAY = 86400
T0 = 1794268800  # a midnight-UTC timestamp


def defillama_payload(last_ts):
    return {
        "name": "X",
        "methodology": {"Fees": "gas"},
        "methodologyURL": "https://example.org/m",
        "parentProtocol": None,
        "totalDataChart": [[last_ts - DAY, 1], [last_ts, 2]],
        "totalDataChartBreakdown": [[last_ts, {"big": {"nested": 2}}]],
    }


def fake_get_json(fail_on=None):
    """Answers every planned URL with a tiny valid payload."""
    def get_json(url):
        if fail_on and fail_on in url:
            raise OSError(f"network down for {url}")
        if "llama.fi" in url:
            return defillama_payload(T0 + DAY if "ethereum" in url else T0)
        if "/coins/markets" in url:
            return [{"id": "near", "market_cap": 1, "fully_diluted_valuation": 1}]
        return {"prices": [[T0 * 1000, 1.0]], "market_caps": [[T0 * 1000, 2.0]]}
    return get_json


class FetchTest(unittest.TestCase):
    def setUp(self):
        with (ROOT / "config" / "panel.toml").open("rb") as f:
            self.config = tomllib.load(f)
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.staging = self.tmp / "staging"

    def run_fetch(self, get_json):
        return fetch.fetch_and_swap(
            self.config, get_json, self.staging, self.raw,
            fetched_at="2026-11-11T15:00:00Z", pause=0,
        )

    def test_as_of_is_the_last_date_common_to_all_series(self):
        series = {"a": [[T0, 1]], "b": [[T0 + DAY, 1]]}
        self.assertEqual(fetch.last_common_date(series), "2026-11-10")

    def test_snapshot_has_one_file_per_request_and_a_manifest(self):
        self.run_fetch(fake_get_json())

        manifest = json.loads((self.raw / "MANIFEST.json").read_text())
        self.assertEqual(manifest["as_of"], "2026-11-10")  # Ethereum ends a day later
        self.assertEqual(manifest["fetched_at"], "2026-11-11T15:00:00Z")
        for filename, url in manifest["sources"].items():
            with self.subTest(filename=filename):
                self.assertTrue((self.raw / filename).exists())
                self.assertTrue(url.startswith("https://"))

    def test_intents_has_fees_revenue_and_holders_revenue(self):
        self.run_fetch(fake_get_json())
        manifest = json.loads((self.raw / "MANIFEST.json").read_text())
        intents_files = {f for f in manifest["sources"] if f.startswith("defillama_near-intents_")}
        self.assertEqual(intents_files, {
            "defillama_near-intents_dailyFees.json",
            "defillama_near-intents_dailyRevenue.json",
            "defillama_near-intents_dailyHoldersRevenue.json",
        })

    def test_stored_defillama_files_drop_the_heavy_breakdown(self):
        self.run_fetch(fake_get_json())
        stored = json.loads((self.raw / "defillama_near_dailyFees.json").read_text())
        self.assertNotIn("totalDataChartBreakdown", stored)
        self.assertEqual(stored["totalDataChart"][-1], [T0, 2])

    def test_rate_limited_requests_are_retried_with_backoff(self):
        calls, waits = [], []

        def flaky(url):
            calls.append(url)
            if len(calls) < 3:
                raise fetch.RateLimited(url)
            return {"ok": True}

        get_json = fetch.with_retries(flaky, sleep=waits.append, attempts=4, backoff=10)

        self.assertEqual(get_json("u"), {"ok": True})
        self.assertEqual(waits, [10, 20])

    def test_retries_give_up_after_the_last_attempt(self):
        def always_limited(url):
            raise fetch.RateLimited(url)

        get_json = fetch.with_retries(always_limited, sleep=lambda s: None, attempts=3, backoff=1)
        with self.assertRaises(fetch.RateLimited):
            get_json("u")

    def test_a_failed_request_leaves_the_existing_snapshot_untouched(self):
        self.raw.mkdir()
        (self.raw / "MANIFEST.json").write_text('{"as_of": "old"}')

        with self.assertRaises(OSError):
            self.run_fetch(fake_get_json(fail_on="aptos"))

        self.assertEqual(json.loads((self.raw / "MANIFEST.json").read_text())["as_of"], "old")


if __name__ == "__main__":
    unittest.main()
