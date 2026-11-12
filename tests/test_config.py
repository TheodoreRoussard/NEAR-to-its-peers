"""Sanity checks on config/panel.toml."""
import tomllib
import unittest
from pathlib import Path

from src import metrics

CONFIG = Path(__file__).resolve().parent.parent / "config" / "panel.toml"


class PanelConfigTest(unittest.TestCase):
    def setUp(self):
        with CONFIG.open("rb") as f:
            self.config = tomllib.load(f)

    def test_panel_contains_near_and_the_five_peers(self):
        names = {c["name"] for c in self.config["chains"]}
        self.assertEqual(
            names, {"NEAR", "Solana", "Ethereum", "Avalanche", "Sui", "Aptos"}
        )

    def test_every_chain_has_ids_and_a_reason(self):
        for chain in self.config["chains"]:
            with self.subTest(chain=chain["name"]):
                self.assertTrue(chain["defillama_slug"])
                self.assertTrue(chain["coingecko_id"])
                self.assertTrue(chain["reason"])

    def test_candidates_are_tron_and_cardano_with_a_reason(self):
        candidates = {c["name"]: c for c in self.config["candidates"]}
        self.assertEqual(set(candidates), {"Tron", "Cardano"})
        for candidate in candidates.values():
            self.assertTrue(candidate["reason"])
        self.assertEqual(candidates["Tron"]["defillama_slug"], "tron")
        self.assertEqual(candidates["Cardano"]["coingecko_id"], "cardano")

    def test_all_four_falsification_criteria_are_defined(self):
        self.assertEqual(
            set(self.config["falsification"]) - {"thresholds"}, {"c1", "c2", "c3", "c4"}
        )

    def test_thresholds_table_exists_and_only_holds_known_keys(self):
        thresholds = self.config["falsification"]["thresholds"]
        self.assertLessEqual(set(thresholds), {"k", "x", "y", "z"})

    def test_thresholds_are_numbers(self):
        # bool is an int subclass in Python, so it is excluded explicitly; the empty table passes.
        for key, value in self.config["falsification"]["thresholds"].items():
            with self.subTest(threshold=key):
                self.assertIsInstance(value, (int, float))
                self.assertNotIsInstance(value, bool)

    def test_buyback_policy_is_a_known_value(self):
        self.assertIn(self.config["intents"]["buyback_policy"],
                      {metrics.NO_POLICY, "burn", "lock"})

    def test_buyback_constants_are_sourced(self):
        intents = self.config["intents"]
        self.assertEqual(intents["buyback_holdings_near"], 2250000)
        self.assertEqual(intents["buyback_outflows_near"], 12000)
        self.assertEqual(intents["buyback_policy"], "none published")
        self.assertEqual(intents["buyback_outflows_period"],
                         "cumulative, from the first buyback to buyback_checked_on")
        self.assertEqual(intents["buyback_checked_on"], "2026-11-11")
        self.assertTrue(intents["buyback_source"].startswith("https://nearblocks.io/address/"))


if __name__ == "__main__":
    unittest.main()
