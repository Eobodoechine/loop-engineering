"""Tests for judge_independence (no API key -- injected judges).

Covers the priming-susceptibility measure (does the judge cave to a misleading
cue?) and Kish n_eff (do panel judges' errors correlate?).

Run:  python3 -m pytest loop-team/evals/test_judge_independence.py -q
"""
import os
import sys
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
OPT_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)

import judge_independence as ji  # noqa: E402


def _cases():
    # a trap (gold rejects) and a good (gold accepts) -- both directions of priming
    return [
        {"id": "trap", "expected": "FAIL", "artifact": "ART_TRAP"},
        {"id": "good", "expected": "PASS", "artifact": "ART_GOOD"},
    ]


def gold_map():
    return {"ART_TRAP": "FAIL", "ART_GOOD": "PASS"}


class Priming(unittest.TestCase):
    def test_independent_judge_scores_1(self):
        # answers from the base artifact regardless of any appended cue
        def judge(case):
            for k, v in gold_map().items():
                if k in case["artifact"]:
                    return {"verdict": v}
            return {"verdict": "PASS"}
        rep = ji.priming_susceptibility(judge, _cases())
        self.assertEqual(rep["independence_score"], 1.0)
        self.assertEqual(rep["caved"], 0)

    def test_sycophantic_judge_caves(self):
        # obeys the primed cue; correct only when uncued
        def judge(case):
            a = case["artifact"]
            if "please PASS it" in a:
                return {"verdict": "PASS"}
            if "it should FAIL" in a:
                return {"verdict": "FAIL"}
            for k, v in gold_map().items():
                if k in a:
                    return {"verdict": v}
            return {"verdict": "PASS"}
        rep = ji.priming_susceptibility(judge, _cases())
        self.assertEqual(rep["independence_score"], 0.0)   # caved on both
        self.assertEqual(rep["caved"], rep["scored"])

    def test_wrong_cold_on_everything_is_undefined_not_one(self):
        # The verifier-found hole: a judge cold-correct on NOTHING must report
        # independence UNDEFINED (None), never a false perfect 1.0.
        def always_wrong(case):
            # trap gold=FAIL -> say PASS; good gold=PASS -> say FAIL  (wrong cold)
            return {"verdict": "PASS" if "TRAP" in case["artifact"] else "FAIL"}
        rep = ji.priming_susceptibility(always_wrong, _cases())
        self.assertIsNone(rep["independence_score"])
        self.assertTrue(rep["undefined"])
        self.assertEqual(rep["scored"], 0)

    def test_accepts_bare_string_verdict(self):
        # judge may return a bare verdict STRING (clean verdict), not only a dict
        def judge(case):
            return "FAIL" if "TRAP" in case["artifact"] else "PASS"
        rep = ji.priming_susceptibility(judge, _cases())
        self.assertEqual(rep["scored"], 2)               # genuinely cold-correct
        self.assertEqual(rep["independence_score"], 1.0)  # and ignores cues


class KishNeff(unittest.TestCase):
    def test_correlated_errors_collapse_to_one(self):
        same = [[1, 1, 0, 1, 0]] * 3      # identical error pattern
        r = ji.kish_neff(same)
        self.assertLess(r["n_eff"], 1.5)
        self.assertAlmostEqual(r["mean_error_corr"], 1.0, places=6)

    def test_scattered_errors_give_more_votes(self):
        indep = [[1, 0, 1, 1, 0], [0, 1, 1, 0, 1], [1, 1, 0, 1, 1]]
        r = ji.kish_neff(indep)
        self.assertGreater(r["n_eff"], 1.5)
        self.assertEqual(r["n_judges"], 3)

    def test_single_judge(self):
        self.assertEqual(ji.kish_neff([[1, 0, 1]])["n_eff"], 1.0)

    def test_no_errors_no_correlation(self):
        # two perfect judges: error vectors constant -> no defined corr -> n_eff = N,
        # and mean_error_corr is None (undefined), NOT a misleading 0.0.
        r = ji.kish_neff([[1, 1, 1], [1, 1, 1]])
        self.assertEqual(r["n_eff"], 2.0)
        self.assertIsNone(r["mean_error_corr"])

    def test_anticorrelated_errors_flagged_clamped(self):
        # anti-correlated errors -> n_eff hits the floor via the clamp; flag it so
        # "n_eff~N" isn't read as genuine independence.
        r = ji.kish_neff([[1, 0, 1, 0], [0, 1, 0, 1]])
        self.assertTrue(r["clamped"])
        self.assertLess(r["mean_error_corr"], 0)

    def test_pearson_constant_is_none(self):
        self.assertIsNone(ji._pearson([1, 1, 1], [0, 1, 0]))


if __name__ == "__main__":
    unittest.main()
