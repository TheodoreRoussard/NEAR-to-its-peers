"""Tests for src/summary.py: the X post and form text, generated from metrics.json."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from src import summary

ROOT = Path(__file__).resolve().parent.parent
REAL = json.loads((ROOT / "data" / "processed" / "metrics.json").read_text())


def x_length(text):
    """Characters as X counts them: every URL counts as 23."""
    return len(re.sub(r"https?://\S+", "x" * 23, text))


class SummaryTest(unittest.TestCase):
    def test_post_fits_on_x_and_says_where_it_was_built(self):
        post = summary.x_post(REAL)
        self.assertLessEqual(x_length(post), 280)
        for required in ("NEAR HACKATHON", "@NEARProtocol", "#NEARHackathon",
                         summary.DASHBOARD_URL, "Not financial advice"):
            self.assertIn(required, post)

    def test_reply_links_the_repo_and_asks_for_specific_feedback(self):
        reply = summary.x_reply(REAL)
        self.assertLessEqual(x_length(reply), 280)
        self.assertIn(summary.REPO_URL, reply)
        self.assertIn("?", reply)

    def test_no_surface_claims_the_thresholds_were_set_in_advance(self):
        # The thresholds were frozen after the numbers were visible; never claim otherwise.
        for name, text in (("form", summary.form_text(REAL)),
                           ("README", (ROOT / "README.md").read_text())):
            with self.subTest(surface=name):
                self.assertNotIn("in advance", text)
        self.assertIn("frozen in a tagged commit", summary.form_text(REAL))

    def test_readme_says_to_clone_before_running_anything(self):
        readme = (ROOT / "README.md").read_text()
        try_it = readme[readme.index("## Try it"):readme.index("## How it works")]
        clone = try_it.index(f"git clone {summary.REPO_URL}.git")
        self.assertLess(clone, try_it.index("make judge-demo"))
        self.assertIn("cd NEAR-to-its-peers", try_it)
        self.assertIn("published page does not change", try_it)

    def test_form_text_fits_the_form(self):
        text = summary.form_text(REAL)
        self.assertGreaterEqual(len(text), 20)
        self.assertLessEqual(len(text), 2000)

    def test_numbers_come_from_the_metrics(self):
        near = REAL["near_perimeters"]
        post = summary.x_post(REAL)
        self.assertIn(f'{near["BASE+NET"]["ratio_to_peer_median"]:.2f}', post)
        self.assertIn(f'{near["BASE"]["ratio_to_peer_median"]:.2f}', post)

    def test_banned_wording_is_absent(self):
        text = summary.render_summary(REAL).lower()
        self.assertNotIn("cheapest", text)
        self.assertNotIn("returned to the token", text)

    def test_holder_sentence_follows_c4(self):
        self.assertIn("not provably", summary.x_post(REAL))
        m = copy.deepcopy(REAL)
        m["falsification"]["c4"].update(verdict="holds", policy="burn")
        self.assertNotIn("not provably", summary.x_post(m))

    def test_committed_summary_matches_a_regeneration(self):
        self.assertEqual((ROOT / "summary.txt").read_text(), summary.render_summary(REAL))

    def test_write_creates_the_file(self):
        out = Path(tempfile.mkdtemp()) / "summary.txt"
        summary.write(REAL, out)
        self.assertEqual(out.read_text(), summary.render_summary(REAL))


if __name__ == "__main__":
    unittest.main()
