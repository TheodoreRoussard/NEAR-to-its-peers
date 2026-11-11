"""Judging runs after the last push, so nothing but fetch.py may read the clock."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLOCK = re.compile(r"datetime\.now|datetime\.today|date\.today|time\.time\(|utcnow")
ALLOWED = {ROOT / "src" / "fetch.py"}


class NoWallClockTest(unittest.TestCase):
    def test_build_code_and_tests_never_read_the_clock(self):
        files = list((ROOT / "src").glob("*.py")) + list((ROOT / "tests").glob("*.py"))
        self.assertTrue(any(f.parent.name == "src" for f in files), "src/ has no code yet")
        offenders = [
            str(f.relative_to(ROOT))
            for f in files
            if f not in ALLOWED and f.name != Path(__file__).name
            and CLOCK.search(f.read_text())
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
