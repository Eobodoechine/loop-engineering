"""Tests for the adversarial hard-case loop (no API key -- injected judge/verifier).

Exercises bucketing (kept_confirmed / kept_provisional / verifier_correct /
gold_unconfirmed), the trustworthy-gold recall/precision computation, adversarial
yield, and the Path-B trigger / half-life logic.

Run:  python3 -m pytest loop-team/evals/test_adversarial_loop.py -q
"""
import os
import sys
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
OPT_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)

import adversarial_loop as al  # noqa: E402


def mapped(mapping):
    """A judge/verifier callable that returns mapping[<artifact substring>]."""
    def fn(case):
        for k, v in mapping.items():
            if k in case["artifact"]:
                return v
        return None
    return fn


class Bucketing(unittest.TestCase):
    def setUp(self):
        self.cases = [
            {"id": "A", "expected": "FAIL", "artifact": "ART_A", "objective_fact": "x"},
            {"id": "B", "expected": "PASS", "artifact": "ART_B", "objective_fact": "y"},
            {"id": "C", "expected": "FAIL", "artifact": "ART_C", "objective_fact": "z"},
            {"id": "D", "expected": "FAIL", "artifact": "ART_D"},          # provisional
            {"id": "E", "expected": "FAIL", "artifact": "ART_E", "objective_fact": "w"},
        ]
        self.judge = mapped({"ART_A": "FAIL", "ART_B": "PASS", "ART_C": "FAIL",
                             "ART_D": "FAIL", "ART_E": "PASS"})  # E gold suspect
        self.verifier = mapped({"ART_A": "PASS", "ART_B": "FAIL", "ART_C": "FAIL",
                                "ART_D": "PASS", "ART_E": "PASS"})

    def test_buckets(self):
        rep = al.run_round(self.cases, self.judge, self.verifier)
        b = {r["id"]: r["bucket"] for r in rep["rows"]}
        self.assertEqual(b["A"], "kept_confirmed")    # trap verifier missed, gold confirmed
        self.assertEqual(b["B"], "kept_confirmed")    # good verifier over-rejected
        self.assertEqual(b["C"], "verifier_correct")  # verifier nailed it -> not hard
        self.assertEqual(b["D"], "kept_provisional")  # no objective_fact -> needs spot-check
        self.assertEqual(b["E"], "gold_unconfirmed")  # judge rejects proposed label

    def test_counts_and_yield(self):
        rep = al.run_round(self.cases, self.judge, self.verifier)
        self.assertEqual(rep["kept"], 3)
        self.assertEqual(rep["kept_confirmed"], 2)
        self.assertEqual(rep["kept_provisional"], 1)
        self.assertEqual(rep["verifier_correct"], 1)
        self.assertEqual(rep["gold_unconfirmed"], 1)
        self.assertAlmostEqual(rep["adversarial_yield"], 3 / 5)

    def test_recall_precision_use_only_trustworthy_gold(self):
        rep = al.run_round(self.cases, self.judge, self.verifier)
        # confirmed+fact traps = {A, C}: verifier right only on C -> recall 0.5.
        # Provisional D must NOT inflate the denominator even though the judge agreed.
        self.assertEqual(rep["verifier_recall_on_confirmed_traps"], 0.5)
        # confirmed+fact goods = {B}: verifier wrong -> precision 0.0
        self.assertEqual(rep["verifier_precision_on_confirmed_goods"], 0.0)


class GoldGuard(unittest.TestCase):
    def test_verifier_wrong_but_gold_unconfirmed_is_not_kept(self):
        # The verifier disagrees, but the gold judge ALSO disagrees with the
        # proposed label -> the case is suspect, never silently kept.
        cases = [{"id": "X", "expected": "FAIL", "artifact": "Q", "objective_fact": "1"}]
        judge = mapped({"Q": "PASS"})       # judge says the proposed FAIL is wrong
        verifier = mapped({"Q": "PASS"})    # verifier also "wrong" vs proposed
        rep = al.run_round(cases, judge, verifier)
        self.assertEqual(rep["rows"][0]["bucket"], "gold_unconfirmed")
        self.assertEqual(rep["kept"], 0)

    def test_unparsed_judge_does_not_confirm(self):
        cases = [{"id": "Y", "expected": "FAIL", "artifact": "Q", "objective_fact": "1"}]
        judge = mapped({})                  # returns None (unparsed)
        verifier = mapped({"Q": "PASS"})
        rep = al.run_round(cases, judge, verifier)
        self.assertFalse(rep["rows"][0]["gold_confirmed"])
        self.assertEqual(rep["rows"][0]["bucket"], "gold_unconfirmed")


class PathBTrigger(unittest.TestCase):
    def test_triggers_after_n_failed_rounds(self):
        self.assertTrue(al.pathb_triggered([False, False, False]))
        self.assertTrue(al.pathb_triggered([True, False, False, False]))

    def test_does_not_trigger_with_a_recent_green(self):
        self.assertFalse(al.pathb_triggered([True, False, False]))
        self.assertFalse(al.pathb_triggered([False, True, False]))

    def test_needs_enough_rounds(self):
        self.assertFalse(al.pathb_triggered([False, False]))   # < n
        self.assertFalse(al.pathb_triggered([]))

    def test_half_life(self):
        self.assertEqual(al.hand_edit_half_life([True, True, False]), 0)
        self.assertEqual(al.hand_edit_half_life([False, True, True]), 2)
        self.assertEqual(al.hand_edit_half_life([True, True, True]), 3)


class FALSEPASScollapses(unittest.TestCase):
    def test_false_pass_counts_as_reject_like_fail(self):
        # A trap whose proposed gold is FAIL; verifier says FALSE-PASS == still a
        # rejection, so the verifier is NOT wrong -> not kept.
        cases = [{"id": "T", "expected": "FAIL", "artifact": "Q", "objective_fact": "1"}]
        judge = mapped({"Q": "FAIL"})
        verifier = mapped({"Q": "FALSE-PASS"})
        rep = al.run_round(cases, judge, verifier)
        self.assertFalse(rep["rows"][0]["verifier_wrong"])
        self.assertEqual(rep["rows"][0]["bucket"], "verifier_correct")


class MalformedCli(unittest.TestCase):
    """A malformed `--live` invocation (a flag given with no following value)
    used to raise an unhandled IndexError from sys.argv[sys.argv.index(flag)
    + 1]; main()'s CLI parsing now goes through _flag_value, which must exit
    cleanly with a usage message instead."""

    def test_flag_value_missing_value_exits_cleanly_not_indexerror(self):
        with self.assertRaises(SystemExit) as ctx:
            al._flag_value(["--candidates"], "--candidates")
        self.assertIsInstance(ctx.exception.code, str)
        self.assertIn("--candidates", ctx.exception.code)

    def test_flag_value_missing_value_for_verifier_model_exits_cleanly(self):
        with self.assertRaises(SystemExit) as ctx:
            al._flag_value(["--live", "--verifier-model"], "--verifier-model")
        self.assertIsInstance(ctx.exception.code, str)
        self.assertIn("--verifier-model", ctx.exception.code)

    def test_flag_value_returns_value_when_present(self):
        self.assertEqual(
            al._flag_value(["--candidates", "some/dir", "--live"], "--candidates"),
            "some/dir")


if __name__ == "__main__":
    unittest.main()
