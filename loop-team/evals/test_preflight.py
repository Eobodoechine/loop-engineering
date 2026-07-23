"""Tests for the preflight gate + its wiring into resumable_runner (no API).

Prove: a permanent blocker (out of credits / bad key / bad model) is classified
and the runner STOPS before sweeping; a transient one does not short-circuit.

Run with: python3 -m pytest loop-team/evals/test_preflight.py -q
"""
import os
import sys
import tempfile
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVALS_DIR)
import preflight as pf            # noqa: E402
import resumable_runner as rr     # noqa: E402


class StatusErr(Exception):
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class Classify(unittest.TestCase):
    def test_credits(self):
        for m in ["Error 400 ... or purchase credits.",
                  "Your credit balance is too low",
                  "insufficient_quota", "check your plan and billing"]:
            self.assertEqual(pf.classify_error(StatusErr(m)), "credits", m)

    def test_auth(self):
        for m in ["invalid_api_key", "authentication_error", "incorrect api key",
                  "ANTHROPIC_API_KEY not set -- needs a key",  # the no-key CLI case
                  "OPENAI_API_KEY not set"]:
            self.assertEqual(pf.classify_error(StatusErr(m)), "auth", m)

    def test_bad_model(self):
        self.assertEqual(pf.classify_error(StatusErr("model not found: claude-x")), "bad_model")

    def test_transient_overloaded_vs_rate_limit(self):
        self.assertEqual(pf.classify_error(StatusErr("Overloaded", status_code=529)), "overloaded")
        self.assertEqual(pf.classify_error(StatusErr("Rate limit reached", status_code=429)), "rate_limit")

    def test_unknown(self):
        self.assertEqual(pf.classify_error(StatusErr("some unrelated boom")), "unknown")

    def test_credits_checked_before_transient(self):
        # A billing error can arrive as a 429 — must NOT be read as a retryable rate limit.
        self.assertEqual(pf.classify_error(StatusErr("purchase credits", status_code=429)), "credits")

    def test_status_code_signals_when_message_is_novel(self):
        # Novel wording but a permanent HTTP status — must still be caught as permanent.
        self.assertEqual(pf.classify_error(StatusErr("Payment Required", status_code=402)), "credits")
        self.assertEqual(pf.classify_error(StatusErr("Unauthorized", status_code=401)), "auth")
        self.assertEqual(pf.classify_error(StatusErr("Forbidden", status_code=403)), "auth")

    def test_account_policy_blocks_are_permanent(self):
        for m in ["Your account has been suspended", "organization deactivated",
                  "API access revoked"]:
            self.assertTrue(pf.is_permanent(pf.classify_error(StatusErr(m))), m)

    def test_is_permanent(self):
        for c in ("credits", "auth", "bad_model"):
            self.assertTrue(pf.is_permanent(c))
        for c in ("overloaded", "rate_limit", "ok", "unknown"):
            self.assertFalse(pf.is_permanent(c))


class Preflight(unittest.TestCase):
    def test_ok_probe(self):
        r = pf.preflight(lambda: "fine")
        self.assertTrue(r["ok"])
        self.assertEqual(r["category"], "ok")

    def test_credit_probe_surfaces_action(self):
        def probe():
            raise StatusErr("400 ... or purchase credits.")
        r = pf.preflight(probe)
        self.assertFalse(r["ok"])
        self.assertEqual(r["category"], "credits")
        self.assertIn("credits", r["action"].lower())
        self.assertIn("subscription", r["action"].lower())  # points at the cheaper path

    def test_transient_probe_not_permanent(self):
        def probe():
            raise StatusErr("Overloaded", status_code=529)
        r = pf.preflight(probe)
        self.assertFalse(r["ok"])
        self.assertFalse(pf.is_permanent(r["category"]))


CASES = [{"id": "a", "artifact": "AA"}, {"id": "b", "artifact": "BB"}]
RENDER = lambda c: c["artifact"]   # noqa: E731
PARSE = lambda raw: raw            # noqa: E731
NOSLEEP = lambda *_a, **_k: None   # noqa: E731


class RunnerProbeWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "res.json")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_permanent_block_stops_before_any_judge_call(self):
        calls = []

        def judge(_p):
            calls.append(_p)         # must never be called
            return "PASS"

        def probe():
            raise StatusErr("400 ... purchase credits.")
        logs = []
        res = rr.run_resumable(CASES, {"m": judge}, RENDER, PARSE, self.out,
                               probe=probe, sleep=NOSLEEP, log=logs.append)
        self.assertEqual(calls, [])                       # no sweep, no judge calls
        self.assertEqual(res["m"], {})
        self.assertTrue(any("BLOCKED" in s and "credits" in s for s in logs))

    def test_ok_probe_proceeds(self):
        res = rr.run_resumable(CASES, {"m": lambda _p: "PASS"}, RENDER, PARSE, self.out,
                               probe=lambda: "fine", sleep=NOSLEEP)
        self.assertEqual(set(res["m"]), {"a", "b"})

    def test_transient_probe_does_not_short_circuit(self):
        # A 529 at probe time must NOT abort — the sweep should still run and fill.
        def probe():
            raise StatusErr("Overloaded", status_code=529)
        res = rr.run_resumable(CASES, {"m": lambda _p: "PASS"}, RENDER, PARSE, self.out,
                               probe=probe, sleep=NOSLEEP)
        self.assertEqual(set(res["m"]), {"a", "b"})

    def test_no_probe_is_backward_compatible(self):
        res = rr.run_resumable(CASES, {"m": lambda _p: "PASS"}, RENDER, PARSE, self.out,
                               sleep=NOSLEEP)  # no probe arg at all
        self.assertEqual(set(res["m"]), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
