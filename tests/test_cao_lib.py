"""Unit tests for cao_lib helpers using standard unittest."""
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE.parent / "run"
if str(RUN_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DIR))

from cao_lib import hn, cutoff_ts


class TestCaoLib(unittest.TestCase):
    def test_hn_formatting(self):
        self.assertEqual(hn(0), "0")
        self.assertEqual(hn(500), "500")
        self.assertEqual(hn(1000), "1.0k")
        self.assertEqual(hn(1500), "1.5k")
        self.assertEqual(hn(1_000_000), "1.0M")
        self.assertEqual(hn(2_500_000), "2.5M")

    def test_cutoff_ts(self):
        now = time.time()
        self.assertEqual(cutoff_ts(""), 0.0)
        ts_24h = cutoff_ts("24h")
        self.assertLess(abs((now - 86400) - ts_24h), 2)
        ts_7d = cutoff_ts("7d")
        self.assertLess(abs((now - 7 * 86400) - ts_7d), 2)


if __name__ == "__main__":
    unittest.main()
