"""Tests for the resumable live-judge runner (no API, injected clock).

Prove the contract: persist-by-id, skip-already-done, ride an outage without
losing work, stay bounded, and resume from a partial file.

Run with: python3 -m pytest loop-team/evals/test_resumable_runner.py -q
"""
import json
import os
import sys
import tempfile
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVALS_DIR)
import resumable_runner as rr  # noqa: E402

CASES = [{"id": "a", "artifact": "AA", "expected": "PASS"},
         {"id": "b", "artifact": "BB", "expected": "FAIL"},
         {"id": "c", "artifact": "CC", "expected": "PASS"}]
RENDER = lambda c: c["artifact"]            # noqa: E731
PARSE = lambda raw: raw.split(":")[1]       # "verdict:PASS" -> "PASS"  # noqa: E731
NOSLEEP = lambda *_a, **_k: None            # noqa: E731


def good_judge(calls=None):
    """A judge that always answers; optionally records every prompt it saw."""
    def j(prompt):
        if calls is not None:
            calls.append(prompt)
        return "verdict:PASS"
    return j


class Resumable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "res.json")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_fills_all_and_persists_by_id(self):
        res = rr.run_resumable(CASES, {"m1": good_judge()}, RENDER, PARSE, self.out, sleep=NOSLEEP)
        self.assertEqual(set(res["m1"]), {"a", "b", "c"})
        saved = json.load(open(self.out))
        self.assertEqual([r["id"] for r in saved["m1"]], ["a", "b", "c"])
        # carries through expected, captures raw reasoning
        self.assertEqual(saved["m1"][0]["expected"], "PASS")
        self.assertEqual(saved["m1"][0]["raw"], "verdict:PASS")
        self.assertEqual(saved["m1"][0]["verdict"], "PASS")

    def test_skips_already_done_on_resume(self):
        # Pre-seed two of three as done.
        seed = {"m1": [{"id": "a", "verdict": "PASS", "raw": "x"},
                       {"id": "b", "verdict": "FAIL", "raw": "y"}]}
        json.dump(seed, open(self.out, "w"))
        calls = []
        rr.run_resumable(CASES, {"m1": good_judge(calls)}, RENDER, PARSE, self.out, sleep=NOSLEEP)
        # Only the missing 'c' should be called — a and b are skipped.
        self.assertEqual(calls, ["CC"])
        saved = json.load(open(self.out))
        self.assertEqual({r["id"] for r in saved["m1"]}, {"a", "b", "c"})

    def test_idempotent_rerun_makes_no_calls(self):
        rr.run_resumable(CASES, {"m1": good_judge()}, RENDER, PARSE, self.out, sleep=NOSLEEP)
        before = open(self.out).read()
        calls = []

        def boom(_p):
            calls.append(_p)
            raise RuntimeError("must not be called")
        rr.run_resumable(CASES, {"m1": boom}, RENDER, PARSE, self.out, sleep=NOSLEEP)
        self.assertEqual(calls, [])              # nothing re-attempted
        self.assertEqual(open(self.out).read(), before)  # file unchanged

    def test_rides_an_outage_without_losing_work(self):
        # Judge raises for the first 4 attempts (simulating a 529 burst), then works.
        state = {"n": 0}

        def flaky(_p):
            state["n"] += 1
            if state["n"] <= 4:
                raise RuntimeError("529 Overloaded")
            return "verdict:PASS"
        res = rr.run_resumable(CASES, {"m1": flaky}, RENDER, PARSE, self.out,
                               per_call_retries=1, sleep=NOSLEEP)
        # All three eventually fill; none recorded as a blank/None.
        self.assertEqual(set(res["m1"]), {"a", "b", "c"})
        self.assertTrue(all(r["verdict"] == "PASS" for r in res["m1"].values()))

    def test_permanent_failure_stays_missing_then_resumes(self):
        # 'b' permanently fails; a and c succeed. b must NOT become a None row.
        def partial(prompt):
            if prompt == "BB":
                raise RuntimeError("down")
            return "verdict:PASS"
        res = rr.run_resumable(CASES, {"m1": partial}, RENDER, PARSE, self.out,
                               max_sweeps=3, per_call_retries=1, sleep=NOSLEEP)
        self.assertEqual(set(res["m1"]), {"a", "c"})    # b missing, not blank
        saved = json.load(open(self.out))
        self.assertNotIn("b", {r["id"] for r in saved["m1"]})
        # Now the API "recovers" — re-run fills only b.
        calls = []
        rr.run_resumable(CASES, {"m1": good_judge(calls)}, RENDER, PARSE, self.out, sleep=NOSLEEP)
        self.assertEqual(calls, ["BB"])                 # only the gap retried
        self.assertEqual({r["id"] for r in json.load(open(self.out))["m1"]}, {"a", "b", "c"})

    def test_bounded_terminates_when_fully_down(self):
        sweeps = {"n": 0}
        orig = rr._missing

        def counting(res, cases, models):
            sweeps["n"] += 1
            return orig(res, cases, models)
        rr._missing = counting
        self.addCleanup(lambda: setattr(rr, "_missing", orig))

        def always_down(_p):
            raise RuntimeError("down")
        res = rr.run_resumable(CASES, {"m1": always_down}, RENDER, PARSE, self.out,
                               max_sweeps=3, per_call_retries=1, sleep=NOSLEEP)
        self.assertEqual(res["m1"], {})          # nothing filled
        # Did NOT loop forever: _missing is called a bounded number of times.
        self.assertLessEqual(sweeps["n"], 3 * 3 + 5)

    def test_two_models_independent(self):
        def m2(_p):
            return "verdict:FAIL"
        res = rr.run_resumable(CASES, {"m1": good_judge(), "m2": m2}, RENDER, PARSE,
                               self.out, sleep=NOSLEEP)
        self.assertEqual(set(res["m1"]), {"a", "b", "c"})
        self.assertEqual(set(res["m2"]), {"a", "b", "c"})
        self.assertTrue(all(r["verdict"] == "PASS" for r in res["m1"].values()))
        self.assertTrue(all(r["verdict"] == "FAIL" for r in res["m2"].values()))


if __name__ == "__main__":
    unittest.main()
