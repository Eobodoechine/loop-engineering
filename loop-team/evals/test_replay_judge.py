"""Tests for the free-path judge: export_blind + replay_judge (no API).

Run with: python3 -m pytest loop-team/evals/test_replay_judge.py -q
"""
import json
import os
import sys
import tempfile
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVALS_DIR)
import replay_judge as rj   # noqa: E402
import arithmetic_check as ac  # noqa: E402


class ExportBlind(unittest.TestCase):
    def test_strips_gold_keeps_id_and_artifact(self):
        cases = [{"id": "a", "artifact": "AA", "expected": "PASS", "rubric": "gold",
                  "objective_fact": "x"}]
        out = rj.export_blind(cases)
        self.assertEqual(out, [{"id": "a", "artifact": "AA"}])

    def test_raises_when_gold_leaks_into_artifact(self):
        leak = "this report's rent is a deposit copied into the rent field, clearly wrong"
        cases = [{"id": "a", "artifact": "Report. " + leak + " Approved.",
                  "rubric": leak}]
        with self.assertRaises(ValueError):
            rj.export_blind(cases)

    def test_leak_caught_across_case_and_whitespace_variants(self):
        # The guard normalizes case + whitespace, so a variant-cased leak is still caught.
        gold = "the deposit figure was copied into the rent field"
        cases = [{"id": "a", "artifact": "REPORT.  THE  DEPOSIT FIGURE WAS COPIED INTO THE RENT FIELD.",
                  "objective_fact": gold}]
        with self.assertRaises(ValueError):
            rj.export_blind(cases)

    def test_short_gold_not_treated_as_leak(self):
        # 'expected: PASS' must NOT trip the guard (would match everywhere); strip handles it.
        out = rj.export_blind([{"id": "a", "artifact": "Checklist row: PASS.", "expected": "PASS"}])
        self.assertEqual(out, [{"id": "a", "artifact": "Checklist row: PASS."}])


class ReplayJudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        rj._CACHE["path"] = None
        rj._CACHE["verdicts"] = None
        self._env = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))

    def _write(self, data):
        p = os.path.join(self.tmp, "v_%d.json" % len(os.listdir(self.tmp)))
        json.dump(data, open(p, "w"))
        os.environ["REPLAY_VERDICTS_PATH"] = p
        return p

    def test_returns_recorded_verdict(self):
        self._write([{"id": "a", "verdict": "PASS"}, {"id": "b", "verdict": "FALSE-PASS"}])
        self.assertEqual(rj.judge({"id": "a"}), "PASS")
        self.assertEqual(rj.judge({"id": "b"}), "FALSE-PASS")

    def test_raises_on_unknown_id(self):
        self._write([{"id": "a", "verdict": "PASS"}])
        with self.assertRaises(RuntimeError):
            rj.judge({"id": "missing"})           # gap in the recorded set -> error, not PASS

    def test_raises_without_env(self):
        os.environ.pop("REPLAY_VERDICTS_PATH", None)
        with self.assertRaises(RuntimeError):
            rj.judge({"id": "a"})

    def test_raises_on_missing_file(self):
        os.environ["REPLAY_VERDICTS_PATH"] = os.path.join(self.tmp, "nope.json")
        with self.assertRaises(RuntimeError):
            rj.judge({"id": "a"})

    def test_blank_verdict_is_treated_as_missing(self):
        self._write([{"id": "a", "verdict": None}, {"id": "b", "verdict": "PASS"}])
        self.assertEqual(rj.judge({"id": "b"}), "PASS")
        with self.assertRaises(RuntimeError):
            rj.judge({"id": "a"})                  # blank == not recorded

    def test_multi_model_requires_replay_model(self):
        self._write({"sonnet": [{"id": "a", "verdict": "PASS"}],
                     "opus": [{"id": "a", "verdict": "FALSE-PASS"}]})
        with self.assertRaises(RuntimeError):       # ambiguous without REPLAY_MODEL
            rj.judge({"id": "a"})
        os.environ["REPLAY_MODEL"] = "opus"
        rj._CACHE["verdicts"] = None
        self.assertEqual(rj.judge({"id": "a"}), "FALSE-PASS")

    def test_composes_with_arith_guard(self):
        # Recorded verdict says PASS, but the artifact's math is provably wrong ->
        # the two-layer judge (guard wraps replay) returns FALSE-PASS.
        self._write([{"id": "m", "verdict": "PASS"}])
        guarded = ac.guard_judge(rj.judge)
        self.assertEqual(guarded({"id": "m", "artifact": "$41.10 × 40 × 52 = $85,888, above floor."}),
                         "FALSE-PASS")
        # clean-math case defers to the recorded verdict
        self.assertEqual(guarded({"id": "m", "artifact": "Base $90,500 clears the floor."}), "PASS")


class RunEvalsIntegration(unittest.TestCase):
    """replay_judge plugs into run_evals.run_suite end-to-end."""
    def setUp(self):
        sys.path.insert(0, EVALS_DIR)
        import run_evals
        self.run_evals = run_evals
        self._orig = run_evals.load_cases
        self.case = {"id": "jc-1", "target": "verifier", "requires": "judge",
                     "expected": "FALSE-PASS", "artifact": "A bad artifact."}
        run_evals.load_cases = lambda: [self.case]
        self.tmp = tempfile.mkdtemp()
        rj._CACHE["path"] = None
        rj._CACHE["verdicts"] = None
        self._env = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.addCleanup(lambda: setattr(run_evals, "load_cases", self._orig))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_replayed_verdict_scores(self):
        p = os.path.join(self.tmp, "v.json")
        json.dump([{"id": "jc-1", "verdict": "FALSE-PASS"}], open(p, "w"))
        os.environ["REPLAY_VERDICTS_PATH"] = p
        report = self.run_evals.run_suite(judge=rj.judge)
        self.assertEqual(report["counts"]["caught"], 1)   # trap correctly rejected
        self.assertEqual(report["counts"]["missed"], 0)


if __name__ == "__main__":
    unittest.main()
