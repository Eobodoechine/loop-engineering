"""Tests for the MVVP judge validator.

Run with:
    python3 -m pytest loop-team/evals/test_judge_validate.py -q
"""
import os
import sys
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVALS_DIR)
import judge_validate as jv  # noqa: E402


class Kappa(unittest.TestCase):
    def test_perfect_agreement_is_one(self):
        a = ["PASS", "FAIL", "FALSE-PASS", "PASS"]
        self.assertAlmostEqual(jv.cohen_kappa(a, a), 1.0)

    def test_constant_judge_is_chance_level(self):
        gold = ["PASS", "FAIL", "FALSE-PASS"] * 5
        const = ["PASS"] * len(gold)
        self.assertAlmostEqual(jv.cohen_kappa(gold, const), 0.0, places=6)
        # exact-match looks decent while kappa is 0 -- the inflation MVVP warns about.
        self.assertGreater(jv.exact_match(gold, const), 0.30)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            jv.cohen_kappa([1, 2], [1])

    def test_matches_sklearn_when_available(self):
        try:
            from sklearn.metrics import cohen_kappa_score
        except Exception:  # noqa: BLE001
            self.skipTest("scikit-learn not installed")
        gold = ["PASS", "FAIL", "FALSE-PASS", "PASS", "FAIL", "PASS", "FALSE-PASS"]
        judge = ["PASS", "FAIL", "PASS", "PASS", "FALSE-PASS", "PASS", "FALSE-PASS"]
        self.assertAlmostEqual(jv.cohen_kappa(gold, judge),
                               cohen_kappa_score(gold, judge), places=10)


class GwetAC1(unittest.TestCase):
    def test_perfect_agreement_is_one(self):
        a = ["PASS", "FAIL", "PASS", "FAIL"]
        self.assertAlmostEqual(jv.gwet_ac1(a, a), 1.0)

    def test_kappa_paradox_ac1_more_stable_under_imbalance(self):
        # Highly imbalanced: 18 PASS + 2 FAIL gold; judge agrees on all but 1.
        # Cohen's kappa is depressed by the skew; Gwet's AC1 stays high (the fix).
        gold = ["PASS"] * 18 + ["FAIL", "FAIL"]
        judge = ["PASS"] * 18 + ["FAIL", "PASS"]   # 19/20 agree
        k = jv.cohen_kappa(gold, judge)
        ac1 = jv.gwet_ac1(gold, judge)
        self.assertGreater(ac1, k + 0.10)          # AC1 materially higher under imbalance
        self.assertGreater(ac1, 0.85)              # AC1 reflects the 95% agreement

    def test_balanced_set_ac1_close_to_kappa(self):
        gold = ["PASS", "FAIL"] * 10
        judge = list(gold); judge[0] = "FAIL"      # one slip on a balanced set
        self.assertLess(abs(jv.gwet_ac1(gold, judge) - jv.cohen_kappa(gold, judge)), 0.05)

    def test_validate_report_includes_ac1_and_confusion(self):
        gold = ["PASS", "FAIL"] * 6
        r = jv.validate_judge(gold, list(gold))
        self.assertIn("ac1", r)
        self.assertAlmostEqual(r["ac1"], 1.0)
        self.assertEqual(r["confusion"].get(("PASS", "PASS")), 6)


class PositionFlip(unittest.TestCase):
    def test_order_invariant_is_zero(self):
        winners = ["a", "b", "c"]
        self.assertEqual(jv.position_flip_rate(winners, winners), 0.0)

    def test_always_flips_is_one(self):
        self.assertEqual(jv.position_flip_rate(["a", "b"], ["x", "y"]), 1.0)


class Validate(unittest.TestCase):
    def _gold(self):
        return ["PASS", "FAIL", "FALSE-PASS"] * 10

    def test_certifies_good_judge(self):
        gold = self._gold()
        judge = list(gold)
        judge[3] = "PASS"  # one slip, kappa still well above 0.6
        n = len(gold)
        swap = (["i%d" % i for i in range(n)], ["i%d" % i for i in range(n)])
        r = jv.validate_judge(gold, judge, retest=judge, swap=swap)
        self.assertTrue(r["certified"])
        self.assertTrue(r["complete"])

    def test_rejects_low_kappa(self):
        gold = self._gold()
        const = ["PASS"] * len(gold)
        r = jv.validate_judge(gold, const)
        self.assertFalse(r["certified"])
        self.assertFalse(r["kappa_pass"])

    def test_rejects_position_bias_even_with_high_kappa(self):
        gold = self._gold()
        judge = list(gold)
        n = len(gold)
        biased = (["i%d" % i for i in range(n)], ["j%d" % i for i in range(n)])
        r = jv.validate_judge(gold, judge, retest=judge, swap=biased)
        self.assertTrue(r["kappa_pass"])      # judgments agree with gold
        self.assertFalse(r["flip_pass"])      # but it's position-biased
        self.assertFalse(r["certified"])

    def test_incomplete_without_all_three_checks(self):
        gold = self._gold()
        r = jv.validate_judge(gold, list(gold))   # kappa only
        self.assertFalse(r["complete"])

    def test_accepts_generator_inputs(self):
        # Bug-finder LOW: generators must not be exhausted by the first metric.
        g = (x for x in ["PASS", "FAIL"] * 5)
        j = (x for x in ["PASS", "FAIL"] * 5)
        r = jv.validate_judge(g, j)
        self.assertEqual(r["n"], 10)
        self.assertAlmostEqual(r["kappa"], 1.0)


class SelfTest(unittest.TestCase):
    def test_selftest_passes(self):
        self.assertTrue(jv._selftest())


if __name__ == "__main__":
    unittest.main()
