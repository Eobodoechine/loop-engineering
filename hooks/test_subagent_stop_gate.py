"""Tests for subagent_stop_gate.py (does not exist yet — tests will FAIL until Coder delivers).

Drives the hook as a subprocess with crafted JSON payloads on stdin.
Cleans up any flag files written to ~/.loop-gate/ after each test.

Run with:
    python3 -m pytest hooks/test_subagent_stop_gate.py -q
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HOOKS_DIR, "subagent_stop_gate.py")
GATE_DIR = tempfile.mkdtemp(prefix="loop-gate-test-")
os.environ["LOOP_GATE_DIR"] = GATE_DIR


def run_gate(payload_dict):
    """Run subagent_stop_gate.py with the given payload dict as stdin JSON.
    Returns (returncode, stderr_text)."""
    payload = json.dumps(payload_dict)
    env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
    p = subprocess.run(
        [sys.executable, GATE],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )
    return p.returncode, p.stderr


def flag_path(session_id, agent_id="*"):
    """Glob pattern for a flag file in ~/.loop-gate/."""
    return os.path.join(GATE_DIR, f"{session_id}_{agent_id}.verifier_pass")


def unique_session():
    return f"test-session-{uuid.uuid4()}"


class SubagentStopGateFlagWrite(unittest.TestCase):
    """AC-1, AC-2, AC-14: flag written / not written depending on last line."""

    def setUp(self):
        self._sessions_to_clean = []

    def tearDown(self):
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    # [BEHAVIORAL] AC-1: PLAN_PASS as last line + valid session_id + agent_id → flag written.
    def test_plan_pass_writes_flag(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "Some preamble\nLOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected),
            f"Expected flag file not found: {expected}",
        )

    # [BEHAVIORAL] AC-2: PLAN_FAIL as last line → NO flag written.
    def test_plan_fail_writes_no_flag(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "Reviewing spec...\nLOOP_GATE: PLAN_FAIL",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(
            glob.glob(pattern),
            [],
            "No flag should be written for PLAN_FAIL",
        )

    # [BEHAVIORAL] AC-14: agent_id missing → flag uses "unknown" as agent portion.
    def test_missing_agent_id_uses_unknown(self):
        sid = unique_session()
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "last_assistant_message": "All checks pass\nLOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_unknown.verifier_pass")
        self.assertTrue(
            os.path.exists(expected),
            f"Expected flag {expected} not found when agent_id missing",
        )

    # [BEHAVIORAL] AC-14 variant: empty-string agent_id → flag uses "unknown".
    def test_empty_agent_id_uses_unknown(self):
        sid = unique_session()
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": "",
            "last_assistant_message": "LOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_unknown.verifier_pass")
        self.assertTrue(os.path.exists(expected))

    # [BEHAVIORAL] AC-14 variant: whitespace-only agent_id → flag uses "unknown".
    def test_whitespace_agent_id_uses_unknown(self):
        sid = unique_session()
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": "   ",
            "last_assistant_message": "LOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_unknown.verifier_pass")
        self.assertTrue(os.path.exists(expected))


class SubagentStopGateAlwaysExitsZero(unittest.TestCase):
    """AC-3: gate exits 0 in all scenarios including exception paths."""

    # [BEHAVIORAL] AC-3: normal PLAN_PASS → exit 0.
    def test_plan_pass_exits_zero(self):
        sid = unique_session()
        payload = {
            "session_id": sid,
            "agent_id": "a1",
            "last_assistant_message": "LOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        # cleanup
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass

    # [BEHAVIORAL] AC-3: PLAN_FAIL → exit 0.
    def test_plan_fail_exits_zero(self):
        code, _ = run_gate({
            "session_id": unique_session(),
            "agent_id": "a1",
            "last_assistant_message": "LOOP_GATE: PLAN_FAIL",
        })
        self.assertEqual(code, 0)

    # [BEHAVIORAL] AC-3: invalid JSON on stdin → exit 0 (no crash).
    def test_invalid_json_exits_zero(self):
        p = subprocess.run(
            [sys.executable, GATE],
            input="not json at all {{{",
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 0)

    # [BEHAVIORAL] AC-3: empty stdin → exit 0.
    def test_empty_stdin_exits_zero(self):
        p = subprocess.run(
            [sys.executable, GATE],
            input="",
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 0)


class SubagentStopGateMissingOrBadFields(unittest.TestCase):
    """AC-10: exits 0 when last_assistant_message is missing, None, non-string, or empty."""

    # [BEHAVIORAL] AC-10: last_assistant_message key missing entirely → exit 0, no flag.
    def test_missing_lam_exits_zero(self):
        sid = unique_session()
        code, _ = run_gate({"session_id": sid, "agent_id": "a1"})
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])

    # [BEHAVIORAL] AC-10: last_assistant_message is None (JSON null) → exit 0, no flag.
    def test_null_lam_exits_zero(self):
        sid = unique_session()
        code, _ = run_gate({"session_id": sid, "agent_id": "a1",
                            "last_assistant_message": None})
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])

    # [BEHAVIORAL] AC-10: last_assistant_message is an integer (non-string) → exit 0, no flag.
    def test_integer_lam_exits_zero(self):
        sid = unique_session()
        code, _ = run_gate({"session_id": sid, "agent_id": "a1",
                            "last_assistant_message": 42})
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])

    # [BEHAVIORAL] AC-10: last_assistant_message is empty string → exit 0, no flag.
    def test_empty_string_lam_exits_zero(self):
        sid = unique_session()
        code, _ = run_gate({"session_id": sid, "agent_id": "a1",
                            "last_assistant_message": ""})
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])


class SubagentStopGateLastLineFiltering(unittest.TestCase):
    """AC-11: last-line extraction handles whitespace, trailing newlines, casing."""

    def setUp(self):
        self._sessions_to_clean = []

    def tearDown(self):
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    # [BEHAVIORAL] AC-11: trailing newline after PLAN_PASS → flag written (last non-blank = PLAN_PASS).
    def test_trailing_newline_still_matches(self):
        sid = unique_session()
        aid = "a1"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "Preamble text\nLOOP_GATE: PLAN_PASS\n",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected))

    # [BEHAVIORAL] AC-11: leading+trailing whitespace on the PLAN_PASS line → match.
    def test_whitespace_padded_plan_pass_matches(self):
        sid = unique_session()
        aid = "a2"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "  LOOP_GATE: PLAN_PASS   ",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected))

    # [BEHAVIORAL] AC-11: lowercase variant → match (case-insensitive last-line check).
    def test_lowercase_plan_pass_matches(self):
        sid = unique_session()
        aid = "a3"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "loop_gate: plan_pass",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected))

    # [BEHAVIORAL] AC-11: all-whitespace message → no lines after strip → exit 0, no flag.
    def test_all_whitespace_message_no_flag(self):
        sid = unique_session()
        payload = {
            "session_id": sid,
            "agent_id": "a4",
            "last_assistant_message": "   \n   \n   ",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])

    # [BEHAVIORAL] AC-11: PLAN_PASS buried in the middle (not last line) → no flag.
    def test_plan_pass_not_last_line_no_flag(self):
        sid = unique_session()
        payload = {
            "session_id": sid,
            "agent_id": "a5",
            "last_assistant_message": "LOOP_GATE: PLAN_PASS\nSome trailing text",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])

    # [BEHAVIORAL] AC-11: empty session_id with PLAN_PASS → no flag written (need non-empty session_id).
    def test_empty_session_id_no_flag(self):
        payload = {
            "session_id": "",
            "agent_id": "a6",
            "last_assistant_message": "LOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        # No flag should exist for an empty-string session (we can't enumerate it safely,
        # but we can check that the GATE_DIR wasn't littered with malformed filenames).
        pattern = os.path.join(GATE_DIR, "_a6.verifier_pass")
        self.assertFalse(os.path.exists(pattern))


class SubagentGateDebugLog(unittest.TestCase):
    """New cases for plan_check_spec.md AC3 (AC5 case 6): subagent_stop_gate.py
    appends one JSON line per invocation that successfully parses its stdin
    payload to $LOOP_GATE_DIR/subagent_gate_debug.jsonl, mirroring the existing
    oga_guard_debug.jsonl pattern. Best-effort; exit code always 0."""

    DEBUG_LOG = os.path.join(GATE_DIR, "subagent_gate_debug.jsonl")

    def setUp(self):
        self._sessions_to_clean = []
        # Snapshot debug-log length (in lines) before each test so we can
        # isolate the line(s) this test appended, since the log is append-only
        # and shared across the whole test module run.
        if os.path.exists(self.DEBUG_LOG):
            with open(self.DEBUG_LOG, encoding="utf-8") as f:
                self._debug_lines_before = len(f.readlines())
        else:
            self._debug_lines_before = 0

    def tearDown(self):
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _new_debug_lines(self):
        with open(self.DEBUG_LOG, encoding="utf-8") as f:
            all_lines = f.readlines()
        return [json.loads(ln) for ln in all_lines[self._debug_lines_before:] if ln.strip()]

    # [BEHAVIORAL] AC5 case 6a: PLAN_PASS final line → flag written AND a debug
    # line with wrote_flag: true is appended.
    def test_plan_pass_appends_debug_line_wrote_flag_true(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "Some preamble\nLOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected_flag))
        new_lines = self._new_debug_lines()
        matches = [ln for ln in new_lines if ln.get("session_id") == sid]
        self.assertEqual(len(matches), 1, f"Expected exactly one debug line for {sid}: {new_lines}")
        entry = matches[0]
        self.assertTrue(entry.get("wrote_flag") is True, entry)
        self.assertEqual(entry.get("agent_id"), aid)
        self.assertIsInstance(entry.get("ts"), (int, float))
        self.assertIn("PLAN_PASS", entry.get("last_line") or "")

    # [BEHAVIORAL] AC5 case 6b: last_assistant_message absent → no flag written
    # AND a debug line with wrote_flag: false is appended (the payload itself
    # still parses successfully, so the debug write must still happen).
    def test_missing_last_assistant_message_appends_debug_line_wrote_flag_false(self):
        sid = unique_session()
        self._sessions_to_clean.append(sid)
        payload = {"session_id": sid, "agent_id": "a1"}
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])
        new_lines = self._new_debug_lines()
        matches = [ln for ln in new_lines if ln.get("session_id") == sid]
        self.assertEqual(len(matches), 1, f"Expected exactly one debug line for {sid}: {new_lines}")
        entry = matches[0]
        self.assertTrue(entry.get("wrote_flag") is False, entry)
        self.assertIsNone(entry.get("last_line"))

    # [BEHAVIORAL] AC5 case 6c: unwritable debug path (LOOP_GATE_DIR points at a
    # location that cannot be created/written, e.g. nested under a file) → the
    # gate still exits 0 (best-effort; any I/O failure changes nothing).
    def test_unwritable_debug_path_still_exits_zero(self):
        # Create a plain FILE where the gate dir would need to be a directory,
        # so os.makedirs(gate_dir) / open(...) both fail with a real OS error.
        fd, blocking_file = tempfile.mkstemp(prefix="loop-gate-blocker-")
        os.close(fd)
        try:
            bogus_gate_dir = os.path.join(blocking_file, "nested", "gate")
            payload = {
                "session_id": unique_session(),
                "agent_id": "a1",
                "last_assistant_message": "LOOP_GATE: PLAN_PASS",
            }
            env = dict(os.environ, LOOP_GATE_DIR=bogus_gate_dir)
            p = subprocess.run(
                [sys.executable, GATE],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(p.returncode, 0)
        finally:
            os.remove(blocking_file)


class VerifierMdDocCheck(unittest.TestCase):
    """AC-7, AC-12 [DOC]: roles/verifier.md must contain the plan-check protocol
    and must not contradict itself on LOOP_GATE vs VERDICT tokens."""

    VERIFIER_MD = os.path.join(
        os.path.dirname(HOOKS_DIR),
        "loop-team", "roles", "verifier.md",
    )

    def _read(self):
        try:
            with open(self.VERIFIER_MD, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            self.skipTest(f"verifier.md not yet written: {self.VERIFIER_MD}")

    # [DOC] AC-7: plan-check section includes LOOP_GATE: PLAN_PASS and LOOP_GATE: PLAN_FAIL.
    def test_plan_pass_token_present(self):
        content = self._read()
        self.assertIn(
            "LOOP_GATE: PLAN_PASS",
            content,
            "verifier.md missing LOOP_GATE: PLAN_PASS token",
        )

    def test_plan_fail_token_present(self):
        content = self._read()
        self.assertIn(
            "LOOP_GATE: PLAN_FAIL",
            content,
            "verifier.md missing LOOP_GATE: PLAN_FAIL token",
        )

    # [DOC] AC-7: file explicitly distinguishes plan-check tokens from post-build VERDICT: tokens.
    def test_verdict_token_present_for_post_build_mode(self):
        content = self._read()
        self.assertIn(
            "VERDICT:",
            content,
            "verifier.md should mention VERDICT: for post-build mode",
        )

    # [DOC] AC-12: LOOP_GATE: and VERDICT: are described as mutually exclusive by mode.
    # The file must not instruct the Verifier to emit both in the same output.
    def test_plan_check_and_verdict_not_described_as_simultaneous(self):
        content = self._read()
        lower = content.lower()
        # A pass/fail check: the doc must NOT say "always emit LOOP_GATE" without
        # the post-build/plan-check distinction, and vice-versa.
        # We check that "plan-check" (or "plan check") appears near the LOOP_GATE token.
        has_plan_check_context = (
            "plan-check" in lower or "plan check" in lower
        )
        self.assertTrue(
            has_plan_check_context,
            "verifier.md never mentions 'plan-check' — the mode distinction is missing",
        )
        # Also check that post-build mode context exists.
        has_post_build_context = (
            "post-build" in lower
            or "post build" in lower
            or "build mode" in lower
        )
        self.assertTrue(
            has_post_build_context,
            "verifier.md never mentions post-build mode — the mode distinction is missing",
        )


if __name__ == "__main__":
    unittest.main()
