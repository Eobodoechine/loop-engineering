"""Tests for the meta-verifier MVVP wiring, driven by FakeLLM (no API key).

Exercises the deterministic glue: objective-case loading, the three-pass judge
run (forward/retest/swap), per-judge MVVP certification, the EPC monitor, and
panel aggregation. The LLM's actual judgment quality is NOT under test here
(that needs the live run); the plumbing is.

Run:  python3 -m pytest loop-team/evals/test_meta_validate.py -q
"""
import os
import sys
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
OPT_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)

import meta_validate as mv  # noqa: E402
from llm import FakeLLM      # noqa: E402

CASES = mv.load_objective_cases()
GOLD_PROMPT = mv.load_role("gold_judge.md")


def perfect_llm():
    """A judge that maps the artifact (forward or swapped) back to its case and
    answers that case's gold verdict -- correct AND order-invariant."""
    def r(prompt):
        for c in CASES:
            if c["artifact"] in prompt or c.get("artifact_swapped", "\0") in prompt:
                return "VERDICT: %s" % c["expected"]
        return "VERDICT: PASS"
    return FakeLLM(r)


def biased_llm():
    """PASS in forward framing, FAIL in swapped -> flips on every case."""
    def r(prompt):
        for c in CASES:
            if c["artifact"] in prompt:
                return "VERDICT: PASS"
            if c.get("artifact_swapped", "\0") in prompt:
                return "VERDICT: FAIL"
        return "VERDICT: PASS"
    return FakeLLM(r)


class ObjectiveCases(unittest.TestCase):
    def test_cases_loaded_and_balanced(self):
        self.assertGreaterEqual(len(CASES), 8, "need a meaningful calibration set")
        labels = {c["expected"] for c in CASES}
        # Must contain BOTH traps and goods or kappa is degenerate and an
        # always-reject judge would falsely certify.
        self.assertIn("FAIL", labels)
        self.assertIn("PASS", labels)

    def test_every_case_is_well_formed(self):
        for c in CASES:
            self.assertEqual(c.get("gold"), "objective-fact", c["id"])
            self.assertIn(c["expected"], ("PASS", "FAIL", "FALSE-PASS"), c["id"])
            self.assertTrue(c.get("artifact"), c["id"])
            self.assertTrue(c.get("artifact_swapped"), c["id"])
            # swapped framing must differ from forward, else the flip audit is vacuous
            self.assertNotEqual(c["artifact"], c["artifact_swapped"], c["id"])
            # gold-side REASONING must never leak into the artifact the judge sees.
            # (The word "PASS" can appear -- the scenario says a role was "marked
            # PASS"; the judge rules on that. What must NOT appear is the
            # answer/justification the grader uses: `fact` and `why_objective`.)
            self.assertNotIn(c["fact"], c["artifact"], c["id"])
            self.assertNotIn(c["why_objective"], c["artifact"], c["id"])


class PerfectJudgeCertifies(unittest.TestCase):
    def test_certifies_with_all_three_checks(self):
        panel = mv.validate_panel({"oracle": (perfect_llm(), GOLD_PROMPT)}, CASES)
        self.assertTrue(panel["certified"])
        r = panel["judges"]["oracle"]["report"]
        self.assertEqual(r["kappa"], 1.0)
        self.assertEqual(r["retest_kappa"], 1.0)
        self.assertEqual(r["flip_rate"], 0.0)
        self.assertTrue(r["complete"])
        self.assertEqual(panel["certified_judges"], ["oracle"])

    def test_majority_matches_gold(self):
        panel = mv.validate_panel({"oracle": (perfect_llm(), GOLD_PROMPT)}, CASES)
        gold = [c["expected"] for c in CASES]
        self.assertEqual(panel["majority"], gold)


class PositionBiasedJudgeRejected(unittest.TestCase):
    def test_flip_check_fails_and_epc_flags_it(self):
        panel = mv.validate_panel({"biased": (biased_llm(), GOLD_PROMPT)}, CASES)
        self.assertFalse(panel["certified"])
        self.assertEqual(panel["judges"]["biased"]["report"]["flip_rate"], 1.0)
        self.assertFalse(panel["judges"]["biased"]["report"]["flip_pass"])
        self.assertTrue(panel["epc"]["panel_order_biased"])


class ChanceJudgeRejected(unittest.TestCase):
    def test_constant_verdict_fails_kappa(self):
        const = FakeLLM(lambda p: "VERDICT: PASS")
        panel = mv.validate_panel({"chance": (const, GOLD_PROMPT)}, CASES)
        self.assertFalse(panel["certified"])
        # constant PASS -> high exact-match but ~0 kappa (the MVVP whole point)
        r = panel["judges"]["chance"]["report"]
        self.assertEqual(r["kappa"], 0.0)
        self.assertGreater(r["exact_match"], r["kappa"])


class Panel(unittest.TestCase):
    def test_two_judges_aggregate_and_epc_reports(self):
        panel = mv.validate_panel(
            {"a": (perfect_llm(), GOLD_PROMPT), "b": (perfect_llm(), GOLD_PROMPT)},
            CASES)
        self.assertEqual(set(panel["certified_judges"]), {"a", "b"})
        # two perfect judges fully agree -> mean inter-judge agreement 1.0
        self.assertEqual(panel["epc"]["mean_interjudge_agreement"], 1.0)
        self.assertIsNotNone(panel["epc"]["verdict_hhi"])

    def test_majority_breaks_to_none_on_tie(self):
        # one always-PASS, one always-FAIL -> 1-1 tie every case -> majority None
        a = FakeLLM(lambda p: "VERDICT: PASS")
        b = FakeLLM(lambda p: "VERDICT: FAIL")
        panel = mv.validate_panel({"a": (a, GOLD_PROMPT), "b": (b, GOLD_PROMPT)}, CASES)
        self.assertTrue(all(m is None for m in panel["majority"]))


class HHI(unittest.TestCase):
    def test_hhi_extremes(self):
        self.assertEqual(mv._hhi(["X", "X", "X"]), 1.0)             # full concentration
        self.assertAlmostEqual(mv._hhi(["A", "B"]), 0.5)            # even split of 2
        self.assertEqual(mv._hhi([]), 0.0)
        self.assertEqual(mv._hhi([None, None]), 0.0)               # None ignored


if __name__ == "__main__":
    unittest.main()
