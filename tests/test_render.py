"""Tests for src/render.py: the static dashboard (docs/index.html)."""
import json
import re
import tempfile
import unittest
from pathlib import Path

import copy

from src import build, narrative, render
from tests.test_build import CAPS, CONFIG, write_snapshot

ROOT = Path(__file__).resolve().parent.parent
REAL = json.loads((ROOT / "data" / "processed" / "metrics.json").read_text())


def fixture_metrics():
    """The tiny build fixture: pending verdicts, null Intents windows, no buckets."""
    tmp = Path(tempfile.mkdtemp())
    write_snapshot(tmp / "raw", CAPS)
    return build.build(tmp / "raw", tmp / "out", CONFIG)


def chart_sections(html):
    return re.findall(r'<section class="chart".*?</section>', html, flags=re.S)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.html = render.render(REAL)

    def test_render_is_deterministic(self):
        self.assertEqual(render.render(REAL), self.html)

    def test_page_is_self_contained(self):
        # Works offline and over file://: no scripts, stylesheets or images to load.
        for pattern in (r"<script", r"<link", r"\ssrc=", r"@import", r"url\("):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.html))

    def test_banned_wording_is_absent(self):
        lowered = self.html.lower()
        self.assertNotIn("cheapest", lowered)
        self.assertNotIn("returned to the token", lowered)

    def test_required_statements_are_present(self):
        self.assertIn("Not financial advice", self.html)
        self.assertIn("upper bound only", self.html)
        self.assertIn("after these numbers were visible", self.html)
        self.assertIn("base-layer fees only", self.html)   # the like-for-like caveat
        self.assertIn("THESIS.md", self.html)

    def test_judge_fixes_show_on_the_dashboard(self):
        self.assertIn("not a separate test", self.html)          # BASE+HOLDERS explained
        self.assertIn("depends on the perimeter", self.html)      # robustness scope
        self.assertIn("after these numbers were visible and before the thesis", self.html)

    def test_data_providers_are_credited(self):
        # CoinGecko API terms (4.3) require "Powered by CoinGecko", displayed prominently.
        self.assertIn('Powered by <a href="https://www.coingecko.com">CoinGecko</a>', self.html)
        self.assertIn('<a href="https://defillama.com">DefiLlama</a>', self.html)
        self.assertIn(REAL["as_of"], self.html)

    def test_every_chart_has_a_source_a_method_and_a_takeaway(self):
        sections = chart_sections(self.html)
        self.assertGreaterEqual(len(sections), 6)
        for section in sections:
            with self.subTest(section=section[:80]):
                self.assertRegex(section, r'class="source".*?href="https://')
                self.assertIn('class="method"', section)
                self.assertIn('class="takeaway"', section)

    def test_numbers_come_from_metrics(self):
        near = REAL["near_perimeters"]
        for name, perimeter in near.items():
            with self.subTest(perimeter=name):
                self.assertIn(name, self.html)
                self.assertIn(render.fmt_multiple(perimeter["multiple"]), self.html)
        for name, chain in REAL["chains"].items():
            with self.subTest(chain=name):
                self.assertIn(render.fmt_multiple(chain["multiple"]), self.html)
        for variant in REAL["panel_variants"]:
            self.assertIn(render.fmt_ratio(variant["near_base_net_ratio"]), self.html)

    def test_every_criterion_shows_its_verdict(self):
        for key, criterion in REAL["falsification"].items():
            with self.subTest(criterion=key):
                self.assertIn(f'data-criterion="{key}" data-verdict="{criterion["verdict"]}"',
                              self.html)

    def test_every_fee_definition_cites_its_methodology(self):
        for chain in REAL["chains"].values():
            self.assertIn(chain["sources"]["fees_methodology"], self.html)
        self.assertIn(REAL["intents"]["sources"]["methodology"], self.html)
        self.assertIn(REAL["falsification"]["c4"]["source"], self.html)

    def test_text_from_the_data_is_escaped(self):
        metrics = json.loads(json.dumps(REAL))
        metrics["falsification"]["c1"]["formula"] = "a < b & c > d"
        html = render.render(metrics)
        self.assertIn("a &lt; b &amp; c &gt; d", html)
        self.assertNotIn("a < b", html)

    def test_renders_pending_verdicts_and_null_windows(self):
        html = render.render(fixture_metrics())
        self.assertIn('data-verdict="pending"', html)
        self.assertIn("not enough data", html)

    def test_write_creates_the_page(self):
        out = Path(tempfile.mkdtemp()) / "docs" / "index.html"
        render.write(REAL, out)
        self.assertEqual(out.read_text(), self.html)


class ExplainerTest(unittest.TestCase):
    """The page states the 'what' and the 'how' of the thesis before the evidence."""

    def setUp(self):
        self.html = render.render(REAL)

    def test_the_thesis_comes_first_and_matches_thesis_md(self):
        v = narrative.basics(REAL)
        bottom = render.e(narrative.bottom_line(REAL, v))
        self.assertIn(bottom, self.html)
        self.assertLess(self.html.index('id="thesis"'), self.html.index('id="key-points"'))
        self.assertLess(self.html.index('id="key-points"'), self.html.index('id="how"'))
        self.assertLess(self.html.index('id="how"'), self.html.index('id="scorecard"'))

    def test_hero_shows_both_readings(self):
        hero = self.html[self.html.index('id="thesis"'):self.html.index('id="key-points"')]
        near = REAL["near_perimeters"]
        self.assertIn(render.fmt_ratio(near["BASE+NET"]["ratio_to_peer_median"]), hero)
        self.assertIn(render.fmt_ratio(near["BASE"]["ratio_to_peer_median"]), hero)
        for key, criterion in REAL["falsification"].items():
            self.assertIn(f'class="verdict {criterion["verdict"]}"', hero)

    def test_key_points_link_to_their_evidence(self):
        points = self.html[self.html.index('id="key-points"'):self.html.index('id="how"')]
        self.assertGreaterEqual(points.count("<li"), 5)
        self.assertGreaterEqual(points.count('href="#'), 5)

    def test_every_internal_link_resolves(self):
        ids = set(re.findall(r'id="([^"]+)"', self.html))
        for target in re.findall(r'href="#([^"]+)"', self.html):
            with self.subTest(target=target):
                self.assertIn(target, ids)

    def test_how_it_works_explains_the_method_and_terms(self):
        how = self.html[self.html.index('id="how"'):self.html.index('id="scorecard"')]
        for term in ("Multiple", "Peer median", "Perimeter", "Tripwire", "Regime break"):
            with self.subTest(term=term):
                self.assertIn(term, how)
        self.assertIn("make judge-demo", how)

    def test_explanatory_copy_has_no_hand_typed_numbers(self):
        for name in ("HOW_STEPS", "GLOSSARY", "KEY_POINT_TITLES"):
            text = repr(getattr(render, name))
            with self.subTest(constant=name):
                self.assertIsNone(re.search(r"\d", text.replace("C1", "").replace("C2", "")
                                            .replace("C3", "").replace("C4", "")))
        for consequence in narrative.CONSEQUENCES.values():
            self.assertIsNone(re.search(r"\d", consequence))

    def test_scorecard_says_what_happens_if_each_criterion_fires(self):
        card = self.html[self.html.index('id="scorecard"'):self.html.index('id="multiples"')]
        self.assertIn("If it fires", card)
        for consequence in narrative.CONSEQUENCES.values():
            self.assertIn(render.e(consequence), card)

    def test_hero_follows_a_flipped_verdict(self):
        m = copy.deepcopy(REAL)
        m["falsification"]["c4"].update(verdict="holds", policy="burn")
        html = render.render(m)
        hero = html[html.index('id="thesis"'):html.index('id="key-points"')]
        self.assertNotIn("not yet provably", hero)
        self.assertIn('class="verdict holds"', hero)
        self.assertNotIn('class="verdict fires"', hero)


class FormatTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(render.fmt_multiple(451.588), "452x")
        self.assertEqual(render.fmt_multiple(4080.1), "4,080x")
        self.assertEqual(render.fmt_multiple(None), "n/a")
        self.assertEqual(render.fmt_ratio(0.3350), "0.34")
        self.assertEqual(render.fmt_usd(5077609), "$5.08M")
        self.assertEqual(render.fmt_usd(30169779106), "$30.17B")
        self.assertEqual(render.fmt_usd(940765), "$0.94M")
        self.assertEqual(render.fmt_change(1.9111), "+191%")
        self.assertEqual(render.fmt_change(-0.5), "-50%")
        self.assertEqual(render.fmt_change(0.0253, 1), "+2.5%")
        self.assertEqual(render.fmt_percent(0.005333), "0.53%")

    def test_log_position_is_monotonic_and_clamped(self):
        positions = [render.log_position(v, 10, 10_000, 100) for v in (10, 100, 1000, 10_000)]
        for got, expected in zip(positions, [0, 100 / 3, 200 / 3, 100]):
            self.assertAlmostEqual(got, expected)
        self.assertEqual(render.log_position(1, 10, 10_000, 100), 0)


if __name__ == "__main__":
    unittest.main()
