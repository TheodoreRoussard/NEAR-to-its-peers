"""Smoke tests for src/build.py."""
import json
import tempfile
import unittest
from pathlib import Path

from src import build


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.out = self.tmp / "processed"
        self.raw.mkdir()

    def test_metrics_carry_the_snapshot_as_of_date(self):
        (self.raw / "MANIFEST.json").write_text(json.dumps({"as_of": "2026-11-11"}))

        build.build(self.raw, self.out)

        metrics = json.loads((self.out / "metrics.json").read_text())
        self.assertEqual(metrics["as_of"], "2026-11-11")

    def test_missing_snapshot_fails_with_a_clear_message(self):
        with self.assertRaises(build.MissingSnapshot) as ctx:
            build.build(self.raw, self.out)
        self.assertIn("make all", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
