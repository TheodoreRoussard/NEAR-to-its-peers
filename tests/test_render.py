"""Tests for src/render.py: the static dashboard (docs/index.html)."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from src import build, render
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
