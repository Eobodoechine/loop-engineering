"""Tests for the optimizer glue, driven by FakeLLM (no API key needed).

Exercises verdict parsing, role-judge scoring, the reflective ACCEPT and REJECT
paths, and proposal writing. The LLM's prompt-quality is NOT under test here
(that needs a live run); the deterministic plumbing is.

Run with:
    python3 -m pytest loop-team/optimize/test_optimize.py -q
"""
import os
import sys
import tempfile
import unittest

OPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OPT_DIR)
import role_runner  # noqa: E402
import optimize_verifier as ov  # noqa: E402
from llm import FakeLLM, anthropic_llm  # noqa: E402


def trap_cases(n):
    return [{"id": "c%02d" % i, "requires": "judge", "target": "verifier",
             "expected": "FAIL", "artifact": "trap %d" % i,
             "rubric": "must reject"} for i in range(n)]


class ParseVerdict(unittest.TestCase):
    def test_explicit_verdict_line(self):
        self.assertEqual(role_runner.parse_verdict("VERDICT: FALSE-PASS\nbecause"), "FALSE-PASS")
        self.assertEqual(role_runner.parse_verdict("verdict = fail"), "FAIL")

    def test_false_pass_not_misread_as_pass(self):
        self.assertEqual(role_runner.parse_verdict("My verdict: FALSE-PASS here"), "FALSE-PASS")

    def test_fallback_token_scan(self):
        self.assertEqual(role_runner.parse_verdict("I think this should PASS cleanly"), "PASS")

    def test_none_when_absent(self):
        self.assertIsNone(role_runner.parse_verdict("no decision here"))

    def test_last_verdict_wins_on_self_correction(self):
        # Real models think out loud: a tentative verdict then a corrected one.
        # The FINAL verdict is the answer (the old first-match parse recorded
        # Sonnet's tentative FAIL as its verdict when it actually concluded PASS).
        txt = ("VERDICT: FAIL -- wait, $30 x 2080 = 62,400 > 55,000. "
               "Let me redo. VERDICT: PASS -- clears the floor.")
        self.assertEqual(role_runner.parse_verdict(txt), "PASS")
        self.assertEqual(
            role_runner.parse_verdict("VERDICT: PASS ... on reflection VERDICT: FALSE-PASS"),
            "FALSE-PASS")


class RoleJudge(unittest.TestCase):
    def test_judge_returns_parsed_verdict(self):
        llm = FakeLLM(lambda p: "VERDICT: FAIL")
        judge = role_runner.make_role_judge(llm, "ROLE")
        self.assertEqual(judge({"artifact": "x", "rubric": "y"}), "FAIL")


class BuildPrompt(unittest.TestCase):
    def test_artifact_and_role_shown_rubric_hidden(self):
        # The role-under-test must not see gold-side metadata (answer leakage):
        # the rubric states the correct verdict, so it must never reach the role.
        case = {"artifact": "ARTIFACT-XYZ", "rubric": "RUBRIC-SECRET must reject",
                "expected": "FALSE-PASS"}
        p = role_runner.build_prompt("ROLE-BODY-123", case)
        self.assertIn("ARTIFACT-XYZ", p)       # the role sees the artifact
        self.assertIn("ROLE-BODY-123", p)      # and its own instructions
        self.assertNotIn("RUBRIC-SECRET", p)   # but NOT the gold rubric reasoning


def _responder(candidate_correct, incumbent_correct=False):
    """Build a FakeLLM responder. Reflection -> candidate prompt; scoring the
    candidate -> (correct/incorrect) verdict; scoring the incumbent -> likewise."""
    def r(prompt):
        if "improving the Verifier role prompt" in prompt:
            return "CANDIDATE_ROLE improved body"
        scoring_candidate = "CANDIDATE_ROLE" in prompt
        ok = candidate_correct if scoring_candidate else incumbent_correct
        return "VERDICT: FAIL" if ok else "VERDICT: PASS"  # FAIL rejects the trap (correct)
    return r


class OptimizeAccept(unittest.TestCase):
    def test_candidate_that_fixes_all_is_accepted_and_writes_proposal(self):
        cases = trap_cases(20)
        llm = FakeLLM(_responder(candidate_correct=True, incumbent_correct=False))
        out_dir = tempfile.mkdtemp()
        out = ov.optimize(llm, "INCUMBENT_ROLE base", cases=cases, out_dir=out_dir)
        self.assertEqual(out["decision"], "ACCEPT")
        self.assertEqual(sum(out["incumbent_correct"]), 0)
        self.assertEqual(sum(out["candidate_correct"]), 20)
        self.assertTrue(out["proposal_path"] and os.path.isfile(out["proposal_path"]))
        with open(out["proposal_path"]) as f:
            self.assertIn("CANDIDATE_ROLE", f.read())

    def test_proposal_numbering_does_not_overwrite_on_gaps(self):
        # Bug-finder MED: numbering from count (not max) would reuse a gapped
        # index and clobber an existing unreviewed proposal.
        out_dir = tempfile.mkdtemp()
        for name in ("verifier.001.md", "verifier.003.md"):  # gap at 002 (count=2)
            with open(os.path.join(out_dir, name), "w") as f:
                f.write("OLD-" + name)
        cases = trap_cases(20)
        llm = FakeLLM(_responder(candidate_correct=True, incumbent_correct=False))
        out = ov.optimize(llm, "INCUMBENT_ROLE base", cases=cases, out_dir=out_dir)
        self.assertEqual(out["decision"], "ACCEPT")
        self.assertTrue(out["proposal_path"].endswith("verifier.004.md"))  # max+1
        with open(os.path.join(out_dir, "verifier.003.md")) as f:
            self.assertEqual(f.read(), "OLD-verifier.003.md")  # untouched


class OptimizeReject(unittest.TestCase):
    def test_no_improvement_is_rejected(self):
        cases = trap_cases(20)
        # Candidate is just as wrong as incumbent -> all concordant -> REJECT.
        llm = FakeLLM(_responder(candidate_correct=False, incumbent_correct=False))
        out = ov.optimize(llm, "INCUMBENT_ROLE", cases=cases)
        self.assertEqual(out["decision"], "REJECT")
        self.assertIsNone(out["proposal_path"])

    def test_worse_candidate_is_rejected(self):
        cases = trap_cases(20)
        llm = FakeLLM(_responder(candidate_correct=False, incumbent_correct=True))
        out = ov.optimize(llm, "INCUMBENT_ROLE", cases=cases)
        self.assertEqual(out["decision"], "REJECT")

    def test_already_perfect_incumbent_short_circuits(self):
        cases = trap_cases(5)
        # Incumbent already correct on everything -> nothing to propose.
        llm = FakeLLM(lambda p: "VERDICT: FAIL")
        out = ov.optimize(llm, "INCUMBENT_ROLE", cases=cases)
        self.assertEqual(out["decision"], "REJECT")
        self.assertIn("perfect", out["reason"])


class RunRoleExplained(unittest.TestCase):
    """The reasoning-capture affordance: a verdict must travel with its 'why',
    and self-correction must be surfaced (not silently parsed)."""

    def test_all_verdicts_orders_and_detects_self_correction(self):
        self.assertEqual(role_runner.all_verdicts("VERDICT: FAIL then VERDICT: PASS"),
                         ["FAIL", "PASS"])
        self.assertEqual(role_runner.all_verdicts("VERDICT: PASS only"), ["PASS"])
        self.assertEqual(role_runner.all_verdicts("no verdict here"), [])

    def test_explained_retains_reasoning_and_flags_self_correction(self):
        # the exact pattern that caused the multi-hour false "blind spot"
        resp = ("VERDICT: FAIL -- wait, 30x2080=62,400 > 55,000. "
                "Let me redo. VERDICT: PASS -- clears the floor.")
        out = role_runner.run_role_explained(FakeLLM(lambda p: resp), "ROLE",
                                             {"artifact": "x"})
        self.assertEqual(out["verdict"], "PASS")          # final verdict wins
        self.assertIn("62,400", out["raw"])               # reasoning RETAINED
        self.assertEqual(out["all_verdicts"], ["FAIL", "PASS"])
        self.assertTrue(out["self_corrected"])            # surfaced, not hidden

    def test_explained_clean_single_verdict_not_flagged(self):
        out = role_runner.run_role_explained(
            FakeLLM(lambda p: "VERDICT: PASS -- evidence is complete."), "ROLE",
            {"artifact": "x"})
        self.assertEqual(out["verdict"], "PASS")
        self.assertFalse(out["self_corrected"])
        self.assertTrue(out["raw"])


class AnswerBlockFormat(unittest.TestCase):
    """The <answer>-block variant under A/B: verdict parsed only from the block, so
    reasoning-level self-correction can't corrupt it."""

    def test_clean_block(self):
        self.assertEqual(role_runner.parse_answer_block("<answer>VERDICT: PASS</answer>"), "PASS")
        self.assertEqual(role_runner.parse_answer_block(
            "lots of reasoning...\n<answer>VERDICT: FALSE-PASS</answer>"), "FALSE-PASS")

    def test_self_correction_in_reasoning_ignored_block_authoritative(self):
        # the whole point: tentative verdicts in the REASONING are ignored; only
        # the committed <answer> block counts.
        txt = ("I lean VERDICT: FAIL here. Wait, 30x2080=62,400 > 55,000, so it clears.\n"
               "<answer>VERDICT: PASS</answer>")
        self.assertEqual(role_runner.parse_answer_block(txt), "PASS")

    def test_last_block_wins(self):
        self.assertEqual(role_runner.parse_answer_block(
            "<answer>VERDICT: FAIL</answer> ... revised <answer>VERDICT: PASS</answer>"), "PASS")

    def test_fallback_when_no_block(self):
        # non-compliant response (no block) still yields the final verdict
        self.assertEqual(role_runner.parse_answer_block(
            "VERDICT: FAIL ... actually VERDICT: PASS"), "PASS")
        self.assertIsNone(role_runner.parse_answer_block("no verdict at all"))

    def test_builder_includes_artifact_and_block_instruction_no_leak(self):
        case = {"artifact": "the ARTIFACT text", "expected": "PASS", "rubric": "GOLDONLY"}
        p = role_runner.build_prompt_answer_block("ROLE", case)
        self.assertIn("the ARTIFACT text", p)
        self.assertIn("<answer>", p)
        self.assertNotIn("GOLDONLY", p)   # gold-side fields never shown


class AnthropicGuard(unittest.TestCase):
    def test_missing_key_raises_clearly(self):
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as cm:
                anthropic_llm()
            self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved


class _Boom(Exception):
    """An exception carrying an HTTP-ish status_code, like the anthropic SDK's."""
    def __init__(self, status_code=None, msg=""):
        super().__init__(msg or ("status %s" % status_code))
        self.status_code = status_code


class CallWithRetry(unittest.TestCase):
    """The verification-resilience wrapper: bounded retries on transient infra
    errors, immediate re-raise on real bugs, no open-ended spin. Deterministic --
    sleep/clock/jitter are injected so the test runs instantly."""

    def _kw(self, **over):
        # no real sleeping; fixed jitter; a controllable clock
        base = dict(sleep=lambda d: None, rand=lambda: 0.0, now=lambda: 0.0,
                    base_delay=1.0, max_total_seconds=120.0)
        base.update(over)
        return base

    def test_transient_then_success(self):
        from llm import call_with_retry
        calls = {"n": 0}
        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _Boom(529, "Overloaded")
            return "ok"
        self.assertEqual(call_with_retry(fn, attempts=3, **self._kw()), "ok")
        self.assertEqual(calls["n"], 3)  # retried twice, succeeded on the third

    def test_non_transient_reraises_immediately(self):
        from llm import call_with_retry
        calls = {"n": 0}
        def fn():
            calls["n"] += 1
            raise ValueError("a real bug in the prompt")  # NOT infra
        with self.assertRaises(ValueError):
            call_with_retry(fn, attempts=5, **self._kw())
        self.assertEqual(calls["n"], 1)  # never retried a real bug

    def test_exhausts_attempts_then_raises_bounded(self):
        from llm import call_with_retry
        calls = {"n": 0}
        def fn():
            calls["n"] += 1
            raise _Boom(529, "Overloaded")
        with self.assertRaises(RuntimeError) as cm:
            call_with_retry(fn, attempts=4, **self._kw())
        self.assertEqual(calls["n"], 4)            # exactly the cap -- no infinite loop
        self.assertIn("infra unavailable", str(cm.exception))

    def test_wall_clock_budget_stops_early(self):
        from llm import call_with_retry
        calls = {"n": 0}
        clock = {"t": 0.0}
        def advancing_now():
            return clock["t"]
        def fn():
            calls["n"] += 1
            clock["t"] += 100.0  # each attempt "takes" 100s of wall-clock
            raise _Boom(503, "unavailable")
        with self.assertRaises(RuntimeError):
            call_with_retry(fn, attempts=10, sleep=lambda d: None, rand=lambda: 0.0,
                            now=advancing_now, base_delay=1.0, max_total_seconds=120.0)
        self.assertLess(calls["n"], 10)  # budget stopped it well before the attempt cap

    def test_is_transient_classification(self):
        from llm import is_transient_error
        self.assertTrue(is_transient_error(_Boom(529, "Overloaded")))
        self.assertTrue(is_transient_error(_Boom(429, "Rate limit reached, try again")))
        self.assertTrue(is_transient_error(Exception("the server is Overloaded right now")))
        self.assertTrue(is_transient_error(type("APITimeoutError", (Exception,), {})()))
        self.assertFalse(is_transient_error(ValueError("bad argument")))
        self.assertFalse(is_transient_error(_Boom(400, "invalid request")))

    def test_permanent_429_quota_billing_is_not_transient(self):
        # Found in reality: an OpenAI account with no credits returns 429
        # "exceeded your current quota" (insufficient_quota). Retrying is futile --
        # the PERMANENT check must win over the 429-in-transient-set heuristic.
        from llm import is_transient_error
        self.assertFalse(is_transient_error(
            _Boom(429, "You exceeded your current quota, please check your plan and billing.")))
        self.assertFalse(is_transient_error(_Boom(429, "Error: insufficient_quota")))
        self.assertFalse(is_transient_error(_Boom(401, "Incorrect API key provided")))
        # Anthropic credit-balance exhaustion (seen live as a 400) -- permanent
        self.assertFalse(is_transient_error(
            _Boom(400, "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing")))

    def test_permanent_429_is_reraised_immediately_not_retried(self):
        from llm import call_with_retry
        calls = {"n": 0}
        def fn():
            calls["n"] += 1
            raise _Boom(429, "You exceeded your current quota")
        with self.assertRaises(_Boom):     # original re-raised, NOT wrapped/retried
            call_with_retry(fn, attempts=5, **self._kw())
        self.assertEqual(calls["n"], 1)    # one attempt, no futile retries


if __name__ == "__main__":
    unittest.main()
