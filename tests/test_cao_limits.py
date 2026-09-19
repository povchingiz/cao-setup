"""Unit tests for cao_limits dataclasses using standard unittest."""
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE.parent / "run"
if str(RUN_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DIR))

from cao_limits import WindowInfo, ClaudeLimits, EngineSpend, LimitReport


class TestCaoLimits(unittest.TestCase):
    def test_window_info(self):
        now_unix = int(time.time())
        w = WindowInfo(utilization=0.85, resets_at=now_unix + 3600, status="allowed_warning")
        self.assertEqual(w.utilization, 0.85)
        self.assertGreater(w.resets_in_seconds, 0)
        self.assertIn("T", w.resets_at_iso)

    def test_claude_limits_near_limit(self):
        cl_safe = ClaudeLimits(
            five_hour=WindowInfo(utilization=0.30, resets_at=int(time.time()) + 3600),
            seven_day=WindowInfo(utilization=0.50, resets_at=int(time.time()) + 86400),
            blocked=False
        )
        self.assertFalse(cl_safe.is_near_limit())
        self.assertFalse(cl_safe.is_blocked())

        cl_warn = ClaudeLimits(
            five_hour=WindowInfo(utilization=0.89, resets_at=int(time.time()) + 3600),
            seven_day=WindowInfo(utilization=0.50, resets_at=int(time.time()) + 86400),
            blocked=False
        )
        self.assertTrue(cl_warn.is_near_limit())

    def test_limit_report_structure(self):
        rep = LimitReport(
            claude=None,
            codex=EngineSpend(tokens_combined=1000),
            opencode=EngineSpend(tokens_in=500, tokens_out=500, cost=0.01),
            agy=None
        )
        self.assertEqual(rep.codex.tokens_combined, 1000)
        self.assertEqual(rep.opencode.cost, 0.01)
        self.assertIsNone(rep.claude)
        self.assertIsNone(rep.agy)


if __name__ == "__main__":
    unittest.main()
