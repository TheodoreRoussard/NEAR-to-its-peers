"""Tests for src/thesis.py: THESIS.template.md + metrics.json -> THESIS.md."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from src import thesis
from tests.test_render import fixture_metrics

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "THESIS.template.md").read_text()
REAL = json.loads((ROOT / "data" / "processed" / "metrics.json").read_text())


def with_verdict(metrics, key, verdict, statistic=None, **extra):
    m = copy.deepcopy(metrics)
    m["falsification"][key]["verdict"] = verdict
    if statistic is not None:
        m["falsification"][key]["statistic"] = statistic
    m["falsification"][key].update(extra)
    return m


class TemplateTest(unittest.TestCase):
    def test_template_has_no_digits_outside_placeholders(self):
        self.assertEqual(thesis.digits_outside_placeholders(TEMPLATE), [])

    def test_the_digit_check_catches_a_hand_typed_number(self):
        self.assertEqual(thesis.digits_outside_placeholders("a {{c1}} b\nc 2 d"), ["c 2 d"])

    def test_an_unknown_placeholder_raises(self):
        with self.assertRaises(thesis.UnknownPlaceholder):
            thesis.fill("{{nope}}", {})

    def test_every_placeholder_is_filled(self):
        self.assertNotIn("{{", thesis.generate(REAL, TEMPLATE))

    def test_committed_thesis_matches_a_regeneration(self):
        self.assertEqual((ROOT / "THESIS.md").read_text(), thesis.generate(REAL, TEMPLATE))

    def test_generation_is_deterministic(self):
        self.assertEqual(thesis.generate(REAL, TEMPLATE), thesis.generate(REAL, TEMPLATE))

    def test_write_creates_the_file(self):
        out = Path(tempfile.mkdtemp()) / "THESIS.md"
        thesis.write(REAL, TEMPLATE, out)
        self.assertEqual(out.read_text(), thesis.generate(REAL, TEMPLATE))


class ContentTest(unittest.TestCase):
    def setUp(self):
        self.text = thesis.generate(REAL, TEMPLATE)

    def test_follows_the_track_structure(self):
        for heading in ("## The claim", "## Evidence for", "## Evidence against",
                        "## What would change my mind", "## Limitations"):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.text)

    def test_required_statements(self):
        self.assertIn("Not financial advice", self.text)
        self.assertIn("after these numbers were visible", self.text)
        self.assertIn("base-layer fees only", self.text)   # the like-for-like caveat
        self.assertIn("Not computed", self.text)

    def test_data_providers_are_credited(self):
        self.assertIn("Powered by [CoinGecko](https://www.coingecko.com)", self.text)
        self.assertIn("[DefiLlama](https://defillama.com)", self.text)
        self.assertIn("data/README.md", self.text)

    def test_banned_wording_is_absent(self):
        lowered = self.text.lower()
        self.assertNotIn("cheapest", lowered)
        self.assertNotIn("returned to the token", lowered)

    def test_dollar_signs_are_escaped_for_markdown_math(self):
        self.assertIsNone(re.search(r"(?<!\\)\$", self.text))

    def test_numbers_come_from_the_metrics(self):
        v = thesis.values(REAL)
        for key in ("base_net_multiple", "base_multiple", "peer_median", "c1_statistic",
                    "c2_statistic", "c4_statistic"):
            with self.subTest(key=key):
                self.assertIn(v[key], self.text)

    def test_every_fee_methodology_is_cited(self):
        for chain in REAL["chains"].values():
            self.assertIn(chain["sources"]["fees_methodology"], self.text)

    def test_renders_with_pending_verdicts_and_null_windows(self):
        text = thesis.generate(fixture_metrics(), TEMPLATE)
        self.assertNotIn("{{", text)
        self.assertIn("pending", text)


class ConditionalProseTest(unittest.TestCase):
    """Sentences that assert a verdict or a direction must follow the data."""

    def test_c1_holds_or_fires(self):
        self.assertIn("below k", thesis.values(REAL)["c1_claim"])
        fired = thesis.values(with_verdict(REAL, "c1", "fires", 1.4))["c1_claim"]
        self.assertIn("above k", fired)
        self.assertNotIn("below k", fired)

    def test_c2_direction_and_verdict(self):
        self.assertIn("rose", thesis.values(REAL)["c2_claim"])
        self.assertNotIn("rose +", thesis.values(REAL)["c2_claim"])
        fell = thesis.values(with_verdict(REAL, "c2", "holds", -0.2))["c2_claim"]
        self.assertIn("fell", fell)
        self.assertNotIn("rose", fell)
        fired = thesis.values(with_verdict(REAL, "c2", "fires", -0.6))["c2_claim"]
        self.assertIn("durability condition fails", fired)

    def test_c3_direction_and_verdict(self):
        self.assertIn("rose", thesis.values(REAL)["c3_claim"])
        fired = thesis.values(with_verdict(REAL, "c3", "fires", -0.4))["c3_claim"]
        self.assertIn("fell", fired)
        self.assertIn("capture condition fails", fired)

    def test_c4_without_policy_points_to_the_strict_reading(self):
        claim = thesis.values(REAL)["c4_claim"]
        self.assertIn("not provably held for holders", claim)
        held = thesis.values(with_verdict(REAL, "c4", "holds", policy="burn"))["c4_claim"]
        self.assertNotIn("not provably", held)
        self.assertIn("burn", held)

    def test_evidence_moves_between_for_and_against(self):
        v = thesis.values(REAL)
        self.assertIn("Intents net revenue", v["evidence_for"])
        fired = thesis.values(with_verdict(REAL, "c2", "fires", -0.6))
        self.assertNotIn("Intents net revenue rose", fired["evidence_for"])
        self.assertIn("Intents net revenue fell", fired["evidence_against"])

    def test_bottom_line_follows_the_verdicts(self):
        self.assertIn("do not yet provably capture", thesis.values(REAL)["bottom_line"])
        flipped = thesis.values(with_verdict(REAL, "c1", "fires", 1.4))["bottom_line"]
        self.assertIn("above its typical peer", flipped)
        self.assertNotIn("below its typical peer", flipped)

    def test_verdict_summary(self):
        self.assertEqual(thesis.values(REAL)["verdict_summary"], "C1, C2 and C3 hold; C4 fires.")


if __name__ == "__main__":
    unittest.main()
