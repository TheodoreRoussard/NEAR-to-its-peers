"""Sanity checks on config/panel.toml."""
import tomllib
import unittest
from pathlib import Path

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

    def test_all_four_falsification_criteria_are_defined(self):
        self.assertEqual(
            set(self.config["falsification"]), {"c1", "c2", "c3", "c4"}
        )


if __name__ == "__main__":
    unittest.main()
