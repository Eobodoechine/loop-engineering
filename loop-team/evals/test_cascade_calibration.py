#!/usr/bin/env python3
"""AC-D1 tests: the cascade report must reflect the recorded data honestly."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cascade_calibration as cc  # noqa: E402


class HonestReport(unittest.TestCase):
    def setUp(self):
        self.report = cc.analyze()

    def test_zero_accept_reject_flips_recorded_faithfully(self):
        for tier, t in self.report["tiers"].items():
            self.assertEqual(t["accept_reject_flips"], 0, tier)

    def test_haiku_sublabel_noise_quantified(self):
        h = self.report["tiers"]["haiku"]
        self.assertGreater(h["sublabel_disagreements"], 0)
        self.assertIsNotNone(h["sublabel_rate"])

    def test_verdict_is_defer_not_invented(self):
        con = self.report["conclusion"]
        self.assertIn("DEFER", con["cascade_verdict"])
        self.assertTrue(con["saturated"])
        # no fabricated economics anywhere in the report
        import json
        blob = json.dumps(self.report).lower()
        self.assertNotIn("token_cost", blob)
        self.assertNotIn("$", blob)

    def test_render_contains_prerequisites(self):
        out = cc.render(self.report)
        self.assertIn("DEFER", out)
        self.assertIn("token usage", out)


if __name__ == "__main__":
    unittest.main()
