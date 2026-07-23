"""Tests for the RRD A/B harness (ab_rrd.py).

No-key tests with FakeLLM judges (deterministic on the prompt string). They prove:
  - the RRD builder is a real, distinct prompt that keeps the baseline parser/labels;
  - scoring is the gate-as-rejector binary, matching run_evals;
  - the harness DISCRIMINATES (RRD beats baseline when the fake judge over-rejects
    goods on the flat prompt) -- so a live tie is a real tie, not a blind harness;
  - and it does NOT manufacture a win when both arms are equally accurate.

Run with:
    python3 -m pytest loop-team/experiments/test_ab_rrd.py -q
"""
import os
import sys
import unittest

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "evals"))
OPT_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)
sys.path.insert(0, EXP_DIR)

import ab_rrd                    # noqa: E402
import meta_validate as mv       # noqa: E402
import optimize_verifier as ov   # noqa: E402
import role_runner               # noqa: E402
from llm import FakeLLM          # noqa: E402


class RrdBuilder(unittest.TestCase):
    def test_rrd_prompt_is_distinct_and_decomposes(self):
        case = {"artifact": "SOME-UNIQUE-ARTIFACT-XYZ"}
        flat = role_runner.build_prompt("ROLE", case)
        rrd = role_runner.build_prompt_rrd("ROLE", case)
        self.assertNotEqual(flat, rrd)
        self.assertIn("DECOMPOSE", rrd)
        self.assertIn("AGGREGATE", rrd)
        # Both still embed the artifact and ask for the SAME verdict label set.
        for p in (flat, rrd):
            self.assertIn("SOME-UNIQUE-ARTIFACT-XYZ", p)
            self.assertIn("VERDICT: FALSE-PASS", p)

    def test_no_gold_side_leakage(self):
        # The builder must never surface gold-side grading fields to the judge.
        case = {"artifact": "A", "rubric": "GOLD-RUBRIC-LEAK",
                "expected": "FAIL", "origin": "ORIGIN-LEAK"}
        rrd = role_runner.build_prompt_rrd("ROLE", case)
        self.assertNotIn("GOLD-RUBRIC-LEAK", rrd)
        self.assertNotIn("ORIGIN-LEAK", rrd)
        self.assertNotIn("expected", rrd.replace("VERDICT", ""))  # no 'expected' field

    def test_final_verdict_parses_last_wins_past_subcriteria(self):
        # A realistic RRD response: per-criterion lines, then one aggregate VERDICT.
        resp = ("- [whole unit]: fails because 'shared bathroom'\n"
                "- [in budget]: meets, $1200 < cap\n"
                "VERDICT: FALSE-PASS")
        self.assertEqual(role_runner.parse_verdict(resp), "FALSE-PASS")


class HarnessScoring(unittest.TestCase):
    def setUp(self):
        self.cases = ov.verifier_cases()
        self.role = mv.load_role("verifier.md")
        self.assertTrue(self.cases, "need verifier-target cases to test against")

    def test_both_accurate_zero_discordant_rejects(self):
        def judge(prompt):
            for c in self.cases:
                if c["artifact"] in prompt:
                    return "VERDICT: %s" % c["expected"]
            return "VERDICT: PASS"
        results, decision = ab_rrd.run_ab(FakeLLM(judge), self.role, self.cases)
        self.assertEqual(ab_rrd._diag(results["baseline"])["correct"], len(self.cases))
        self.assertEqual(ab_rrd._diag(results["rrd"])["correct"], len(self.cases))
        # equal accuracy -> 0 discordant -> no manufactured winner
        self.assertEqual(decision["results"]["rrd"].decision, "REJECT")
        self.assertIsNone(decision["winner"])

    def test_harness_discriminates_rrd_recovers_over_rejected_goods(self):
        goods = [c for c in self.cases if c["expected"] == "PASS"]
        self.assertGreaterEqual(len(goods), 5, "need enough goods for a real signal")

        def paranoid(prompt):
            is_rrd = "DECOMPOSE" in prompt
            for c in self.cases:
                if c["artifact"] in prompt:
                    if c["expected"] == "PASS" and not is_rrd:
                        return "VERDICT: FALSE-PASS"  # flat arm over-rejects goods
                    return "VERDICT: %s" % c["expected"]
            return "VERDICT: PASS"
        results, decision = ab_rrd.run_ab(FakeLLM(paranoid), self.role, self.cases)
        base = ab_rrd._diag(results["baseline"])
        rrd = ab_rrd._diag(results["rrd"])
        self.assertEqual(base["good_correct"], 0)             # flat lost every good
        self.assertEqual(rrd["good_correct"], rrd["good_n"])  # rrd recovered them all
        self.assertGreater(rrd["correct"], base["correct"])
        # With >=5 discordant good cases recovered, PACE should ACCEPT rrd.
        self.assertEqual(decision["results"]["rrd"].decision, "ACCEPT")
        self.assertEqual(decision["winner"], "rrd")

    def test_scoring_is_gate_as_rejector_binary(self):
        # A trap labeled FALSE-PASS is 'correct' on a plain FAIL too (both reject).
        def fail_everything(prompt):
            return "VERDICT: FAIL"
        results, _ = ab_rrd.run_ab(FakeLLM(fail_everything), self.role, self.cases)
        for r in results["rrd"]:
            if r["gold"] in ("FAIL", "FALSE-PASS"):
                self.assertTrue(r["correct"])   # rejecting a trap is correct
            else:
                self.assertFalse(r["correct"])  # rejecting a good case is wrong

    def test_selftest_passes(self):
        self.assertTrue(ab_rrd._selftest())


if __name__ == "__main__":
    unittest.main()
