"""Tests for the eval suite runner -- including the suite-validity ('test the
tests') check that Phase-1 acceptance criterion #1 demands.

Run with:
    python3 -m pytest loop-team/evals/test_run_evals.py -q
    (or) python3 -m unittest loop-team.evals.test_run_evals
"""
import os
import re
import sys
import tempfile
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVALS_DIR)
import run_evals  # noqa: E402


def _row(report, case_id):
    return next(r for r in report["rows"] if r["id"] == case_id)


class SuiteOnRealHarness(unittest.TestCase):
    def setUp(self):
        self.report = run_evals.run_suite()

    def test_suite_is_green(self):
        self.assertTrue(self.report["green"], "real harness must yield a GREEN suite")

    def test_every_trap_is_caught(self):
        self.assertEqual(self.report["counts"]["missed"], 0)
        self.assertEqual(self.report["counts"]["caught"], self.report["traps"])

    def test_no_good_case_regression(self):
        self.assertEqual(self.report["counts"]["regression"], 0)

    def test_judge_cases_pending_without_adapter(self):
        # The role-level cases require a judge; with none supplied they must be
        # listed as pending, never silently counted as passing.
        self.assertGreaterEqual(self.report["counts"]["pending"], 4)


class SuiteValidity(unittest.TestCase):
    """Criterion #1 -- each frozen case must FAIL on a deliberately-broken
    target and PASS on the good one. Here: disable verify.py's zero-test guard
    and confirm `zero-test-green` flips to MISSED and the suite goes RED."""

    def _broken_harness(self):
        src = os.path.join(EVALS_DIR, "..", "harness", "verify.py")
        with open(src, encoding="utf-8") as f:
            code = f.read()
        broken = code.replace(
            "def _zero_tests(output, code):",
            "def _zero_tests(output, code):\n    return False  # GUARD DISABLED (suite-validity mutation)")
        self.assertIn("GUARD DISABLED", broken, "mutation must apply")
        fd, path = tempfile.mkstemp(suffix="_verify_broken.py")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(broken)
        self.addCleanup(os.remove, path)
        return path

    def test_zero_test_case_misses_on_broken_harness(self):
        report = run_evals.run_suite(harness=self._broken_harness())
        self.assertEqual(_row(report, "zero-test-green")["bucket"], "missed",
                         "a guard-removed harness must let the false-green through")
        self.assertFalse(report["green"], "broken harness must yield a RED suite")
        self.assertGreater(report["false_pass_rate"], 0.0)


class Classify(unittest.TestCase):
    def test_trap_rejected_is_caught(self):
        self.assertEqual(run_evals.classify("FAIL", "FAIL"), "caught")
        self.assertEqual(run_evals.classify("FALSE-PASS", "FAIL"), "caught")

    def test_trap_passed_is_missed(self):
        self.assertEqual(run_evals.classify("FAIL", "PASS"), "missed")

    def test_good_passed_is_ok(self):
        self.assertEqual(run_evals.classify("PASS", "PASS"), "ok")

    def test_good_failed_is_regression(self):
        self.assertEqual(run_evals.classify("PASS", "FAIL"), "regression")

    def test_unknown_label_raises_not_silent_pass(self):
        # Bug-finder MED: a typo'd label must not silently bucket a missed trap as ok.
        for bad in ("false-pass", "Fail", "FALSE_PASS", None):
            with self.assertRaises(ValueError):
                run_evals.classify(bad, "PASS")


class SuiteRobustness(unittest.TestCase):
    def _patch_cases(self, cases):
        orig = run_evals.load_cases
        run_evals.load_cases = lambda: cases
        self.addCleanup(setattr, run_evals, "load_cases", orig)

    def test_malformed_case_isolated_as_error_not_crash(self):
        self._patch_cases([
            {"id": "good", "target": "harness", "fixture": "passing_project",
             "expected": "PASS"},
            {"id": "typo", "target": "verifier", "requires": "judge",
             "expected": "FALSE_PASS", "artifact": "a", "rubric": "b"},  # bad label
            {"id": "nokey", "requires": "judge"},                        # missing keys
        ])
        rep = run_evals.run_suite(judge=lambda c: "FAIL")
        buckets = {r["id"]: r["bucket"] for r in rep["rows"]}
        self.assertEqual(buckets["good"], "ok")
        self.assertEqual(buckets["typo"], "error")
        self.assertEqual(buckets["nokey"], "error")
        self.assertFalse(rep["green"])   # any error -> not green

    def test_empty_suite_not_green(self):
        self._patch_cases([])
        self.assertFalse(run_evals.run_suite()["green"])

    def test_all_pending_suite_not_green(self):
        self._patch_cases([{"id": "j", "target": "verifier", "requires": "judge",
                            "expected": "FAIL", "artifact": "a", "rubric": "b"}])
        rep = run_evals.run_suite()  # no judge -> the only case is pending
        self.assertFalse(rep["green"])

    def test_judge_returning_none_is_error_not_missed(self):
        """A judge that returns None is BROKEN, not lenient: the trap must
        bucket as 'error' (never 'missed'/false-pass) and the suite must not
        be GREEN. Regression for the None-verdict misclassification bug."""
        self._patch_cases([{"id": "trap", "target": "verifier", "requires": "judge",
                            "expected": "FAIL", "artifact": "a", "rubric": "b"}])
        rep = run_evals.run_suite(judge=lambda c: None)
        row = {r["id"]: r for r in rep["rows"]}["trap"]
        self.assertEqual(row["bucket"], "error")
        self.assertNotEqual(row["bucket"], "missed")
        self.assertIn("judge returned None", row["detail"])
        self.assertFalse(rep["green"])


if __name__ == "__main__":
    unittest.main()


def _slop_metrics_available():
    """Real availability check for the erosion lane. radon is imported LAZILY
    inside slop_gate.erosion_metrics() (not at module import time), so merely
    importing slop_gate cannot detect absence -- the ImportError only surfaces
    on a real call. Reuse run_evals.run_slop_metrics_case itself (the exact
    function test_pending_when_metrics_unavailable exercises) on a throwaway
    case and check its own `pending` flag: that IS the project's real
    availability check, not a reimplementation of one."""
    probe = {"id": "_availability_probe", "target": "slop_metrics",
              "expected": "PASS", "code_before": "def a():\n    return 1\n",
              "code_after": "def a():\n    return 1\n"}
    return not run_evals.run_slop_metrics_case(probe).get("pending")


class SlopMetricsLane(unittest.TestCase):
    """AC-C1: deterministic erosion lane. On this provisioned host (radon
    installed) the frozen traps must be CAUGHT, the hard-good must PASS, and a
    radon-less environment must bucket pending (never error)."""

    @unittest.skipUnless(
        _slop_metrics_available(),
        "radon/slop_gate not available in this environment -- erosion lane "
        "buckets pending (see test_pending_when_metrics_unavailable); "
        "install loop-team/requirements-dev.txt's radon>=6,<7 for this test",
    )
    def test_frozen_erosion_traps_caught_and_good_passes(self):
        rep = run_evals.run_suite()
        buckets = {r["id"]: r["bucket"] for r in rep["rows"]}
        self.assertEqual(buckets.get("erosion-cc-heavy-rewrite"), "caught")
        self.assertEqual(buckets.get("erosion-dup-dead-bloat"), "caught")
        self.assertEqual(buckets.get("erosion-legit-refactor-good"), "ok")

    def test_pending_when_metrics_unavailable(self):
        import unittest.mock as mock
        case = {"id": "x", "target": "slop_metrics", "expected": "FALSE-PASS",
                "code_before": "def a():\n    return 1\n",
                "code_after": "def a():\n    return 2\n"}
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") \
            else __import__
        def no_radon(name, *a, **k):
            if name == "slop_gate" or name.startswith("radon"):
                raise ImportError("simulated absence")
            return real_import(name, *a, **k)
        import sys as _s
        _s.modules.pop("slop_gate", None)
        with mock.patch("builtins.__import__", side_effect=no_radon):
            res = run_evals.run_slop_metrics_case(case)
        self.assertTrue(res.get("pending"), res)
        self.assertIsNone(res["verdict"])
