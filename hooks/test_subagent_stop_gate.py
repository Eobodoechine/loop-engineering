"""Tests for subagent_stop_gate.py (does not exist yet — tests will FAIL until Coder delivers).

Drives the hook as a subprocess with crafted JSON payloads on stdin.
Cleans up any flag files written to ~/.loop-gate/ after each test.

Run with:
    python3 -m pytest hooks/test_subagent_stop_gate.py -q
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HOOKS_DIR, "subagent_stop_gate.py")
GATE_DIR = tempfile.mkdtemp(prefix="loop-gate-test-")
os.environ["LOOP_GATE_DIR"] = GATE_DIR

# Repo root, derived the same way the hook itself must derive it (relative to
# __file__, never cwd) — mirrors hooks/micro_step_gates.py's _signature()
# pattern and VerifierMdDocCheck.VERIFIER_MD below.
REPO_ROOT = os.path.dirname(HOOKS_DIR)
RUNS_DIR = os.path.join(REPO_ROOT, "loop-team", "runs")

# spec.md H-TRACE-WIRING-1: the repo-root bare `runs/<name>` convention,
# sibling to `loop-team/runs/`. Both are real, valid write targets depending
# on which form a transcript's first run-dir-shaped reference uses.
BARE_RUNS_DIR = os.path.join(REPO_ROOT, "runs")


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


def unique_run_name(prefix="trace-test"):
    """A run-dir name under the REAL loop-team/runs/ tree, uniquely suffixed
    so parallel test runs never collide and tearDown can safely rm -rf it.
    The spec requires run_dir resolution to be anchored to the hook's own
    __file__ (repo root), not cwd — so tests exercise the real repo-root path
    rather than a fabricated fake tree, and clean up afterward."""
    return f"{prefix}-{uuid.uuid4()}"


def run_dir_for(name):
    return os.path.join(RUNS_DIR, name)


def trace_path_for(name):
    return os.path.join(run_dir_for(name), "trace.jsonl")


def bare_run_dir_for(name):
    """<repo_root>/runs/<name> — the bare-form (non loop-team/-prefixed)
    run-dir convention that spec.md H-TRACE-WIRING-1 requires the hook to
    ALSO resolve to (AC1, AC6, AC23-25)."""
    return os.path.join(BARE_RUNS_DIR, name)


def bare_trace_path_for(name):
    return os.path.join(bare_run_dir_for(name), "trace.jsonl")


def read_bare_trace_lines(name):
    """Read trace.jsonl for a BARE-form run <name> (under <repo_root>/runs/,
    not <repo_root>/loop-team/runs/) as a list of parsed JSON dicts. Returns
    [] if the file doesn't exist."""
    p = bare_trace_path_for(name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def structured_output_event(name_hint, loop_gate_value, extra_input=None):
    """Build one real Claude-Code-transcript-shaped JSONL event dict
    representing an assistant turn whose content includes a `tool_use` block
    named `StructuredOutput`, per hooks/loop_stop_guard.py's own documented
    parsing idiom (message.content -> list of parts -> type == 'tool_use').
    `loop_gate_value` may be None to omit the key entirely (AC18)."""
    input_dict = dict(extra_input or {})
    if loop_gate_value is not None:
        input_dict["loop_gate"] = loop_gate_value
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": f"Plan-check verdict for {name_hint}."},
                {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4()}",
                    "name": "StructuredOutput",
                    "input": input_dict,
                },
            ],
        },
    }


def write_jsonl_transcript(tmpdir, lines, trailing_newline=True, extra_raw_tail=None):
    """Write a synthetic JSONL transcript file from a list of event dicts (or
    raw pre-serialized strings, for deliberately malformed-line tests) and
    return its path.

    lines: list where each element is either a dict (json.dumps'd) or a str
    (written verbatim as one line — used to inject malformed JSON).
    trailing_newline: whether the file ends with \\n after the last line
    (False simulates a live/mid-write transcript for the truncation-guard
    tests, AC25).
    extra_raw_tail: if given, a raw string appended with NO trailing newline
    after all `lines` — used to simulate a torn/incomplete final line.
    """
    path = os.path.join(tmpdir, f"transcript-{uuid.uuid4()}.txt")
    serialized = []
    for item in lines:
        if isinstance(item, str):
            serialized.append(item)
        else:
            serialized.append(json.dumps(item))
    body = "\n".join(serialized)
    if lines:
        body += "\n"
    if extra_raw_tail is not None:
        body += extra_raw_tail
    elif not trailing_newline and body.endswith("\n"):
        body = body[:-1]
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def read_debug_lines_for_session(debug_log_path, before_count, sid):
    """Read all NEW subagent_gate_debug.jsonl lines appended since
    `before_count` and return those matching session_id == sid."""
    if not os.path.exists(debug_log_path):
        return []
    with open(debug_log_path, encoding="utf-8") as f:
        all_lines = f.readlines()
    new_lines = [json.loads(ln) for ln in all_lines[before_count:] if ln.strip()]
    return [ln for ln in new_lines if ln.get("session_id") == sid]


def write_transcript(tmpdir, body_text):
    """Write a synthetic transcript file (the content SubagentStop's
    transcript_path would point at) and return its path."""
    path = os.path.join(tmpdir, f"transcript-{uuid.uuid4()}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body_text)
    return path


def read_trace_lines(name):
    """Read trace.jsonl for run <name> as a list of parsed JSON dicts.
    Returns [] if the file doesn't exist."""
    p = trace_path_for(name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


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


class SubagentStopLegacyCreditV1(unittest.TestCase):
    """v1 keeps SubagentStop legacy flags non-authorizing.

    Coder authorization is validated by PreToolUse/Stop against same-parent
    transcript structure; SubagentStop must not be treated as a persisted
    cross-turn credit mint.
    """

    def setUp(self):
        self._sessions_to_clean = []

    def tearDown(self):
        for sid in self._sessions_to_clean:
            for path in glob.glob(os.path.join(GATE_DIR, f"{sid}_*")):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_plan_pass_writes_no_json_credit_artifact(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        code, _ = run_gate({
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "REVIEWED_SPEC_SHA256=%s\nLOOP_GATE: PLAN_PASS" % ("a" * 64),
        })
        self.assertEqual(code, 0)
        self.assertEqual(
            glob.glob(os.path.join(GATE_DIR, f"{sid}_*.verifier_credit.json")),
            [],
            "v1 must not mint persisted JSON Coder credit from SubagentStop",
        )


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


class TraceLoggingRunDirExtraction(unittest.TestCase):
    """spec.md AC1: transcript_path -> run_dir/role extraction and a single
    appended trace.jsonl line per SubagentStop completion.

    Uses REAL loop-team/runs/<name> directories (uniquely suffixed) because
    the spec anchors run_dir resolution to the hook's own __file__ (repo
    root), not cwd — a fabricated fake tree elsewhere would not exercise the
    actual algorithm. Every run dir created here is removed in tearDown."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-transcript-")
        self._run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._run_names:
            shutil.rmtree(run_dir_for(name), ignore_errors=True)

    def _track(self, name):
        self._run_names.append(name)
        return name

    # [BEHAVIORAL] AC1: a Coder dispatch transcript (bare "# Role: Coder"
    # header + a loop-team/runs/<name>/specs/spec.md path reference) yields
    # exactly one new trace.jsonl line with role="Coder".
    def test_coder_transcript_appends_one_trace_line_with_role_coder(self):
        name = self._track(unique_run_name("coder"))
        transcript_body = (
            "# Role: Coder\n\n"
            "You are implementing the spec at "
            f"loop-team/runs/{name}/specs/spec.md.\n\n"
            "I've read the spec and implemented the change as described.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        sid = unique_session()
        payload = {
            "session_id": sid,
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Implementation complete.",
        }
        before = read_trace_lines(name)
        self.assertEqual(before, [], "trace.jsonl should not pre-exist")
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        after = read_trace_lines(name)
        self.assertEqual(
            len(after), 1,
            f"expected exactly one new trace.jsonl line, got {after}",
        )
        self.assertEqual(after[0].get("role"), "Coder")
        self.assertTrue(
            after[0].get("event_type"),
            f"trace event missing event_type: {after[0]}",
        )

    # [BEHAVIORAL] AC1: a Test-writer dispatch transcript whose role header
    # carries the parenthetical suffix ("# Role: Test-writer (Tier 1 —
    # spec-only, runs BEFORE implementation)") must still classify as
    # role="Test-writer" — the regex must strip the parenthetical, not choke
    # on it or capture the whole trailing clause.
    def test_test_writer_transcript_with_parenthetical_header_classifies_correctly(self):
        name = self._track(unique_run_name("testwriter"))
        transcript_body = (
            "# Role: Test-writer (Tier 1 — spec-only, runs BEFORE implementation)\n\n"
            "You convert acceptance criteria into executable tests.\n\n"
            "The spec is at "
            f"loop-team/runs/{name}/specs/spec.md.\n\n"
            "I've written the new tests; they fail as expected (red-by-design).\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        sid = unique_session()
        payload = {
            "session_id": sid,
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Tests written, red as expected.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        after = read_trace_lines(name)
        self.assertEqual(
            len(after), 1,
            f"expected exactly one new trace.jsonl line, got {after}",
        )
        self.assertEqual(after[0].get("role"), "Test-writer")


class TraceLoggingExtractionAlgorithmSpecifics(unittest.TestCase):
    """spec.md AC1 (regex specifics) / AC4 overlap: multi-match-takes-first
    and no-match-anywhere behavior for the loop-team/runs/([^/\\s"'\\)]+)
    extraction regex, exercised directly through the hook's behavior rather
    than by re-implementing the regex in the test."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-transcript-")
        self._run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._run_names:
            shutil.rmtree(run_dir_for(name), ignore_errors=True)

    def _track(self, name):
        self._run_names.append(name)
        return name

    # [BEHAVIORAL] AC1: transcript references TWO different run-dir paths;
    # the FIRST match's <name> wins and gets the trace line, the second's
    # run dir is untouched.
    def test_multiple_run_dir_matches_takes_first(self):
        first = self._track(unique_run_name("first"))
        second = self._track(unique_run_name("second"))
        transcript_body = (
            "# Role: Coder\n\n"
            f"Primary spec: loop-team/runs/{first}/specs/spec.md\n"
            f"Unrelated earlier run mentioned in passing: loop-team/runs/{second}/specs/spec.md\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertEqual(
            len(read_trace_lines(first)), 1,
            "the FIRST-matched run's trace.jsonl should get the new line",
        )
        self.assertEqual(
            read_trace_lines(second), [],
            "the SECOND-matched run's trace.jsonl must remain untouched",
        )

    # [BEHAVIORAL] AC1/AC4: transcript contains no loop-team/runs/ path at
    # all -> no trace file is created anywhere reachable, hook still exits 0.
    def test_no_run_dir_match_anywhere_writes_no_trace_and_exits_zero(self):
        transcript_body = (
            "# Role: Coder\n\n"
            "This transcript has no run-dir-shaped path in it whatsoever.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        before_listing = set(os.listdir(RUNS_DIR)) if os.path.isdir(RUNS_DIR) else set()
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        after_listing = set(os.listdir(RUNS_DIR)) if os.path.isdir(RUNS_DIR) else set()
        self.assertEqual(
            after_listing, before_listing,
            "no new directory should appear under loop-team/runs/ when there's no match",
        )


class TraceLoggingVerdictAndFlagCoexistence(unittest.TestCase):
    """spec.md AC2: a VERDICT: PASS completion writes a trace event carrying
    that verdict; a LOOP_GATE: PLAN_PASS completion writes BOTH the existing
    .verifier_pass flag AND a trace event — the two mechanisms coexist."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-transcript-")
        self._run_names = []
        self._sessions_to_clean = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._run_names:
            shutil.rmtree(run_dir_for(name), ignore_errors=True)
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _track(self, name):
        self._run_names.append(name)
        return name

    # [BEHAVIORAL] AC2: last_assistant_message ends with "VERDICT: PASS" ->
    # trace event is written carrying that verdict.
    def test_verdict_pass_completion_writes_trace_event_with_verdict(self):
        name = self._track(unique_run_name("verdict"))
        transcript_body = (
            "# Role: Verifier\n\n"
            f"Reviewing loop-team/runs/{name}/specs/spec.md against the build.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        sid = unique_session()
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "All checks pass.\nVERDICT: PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        lines = read_trace_lines(name)
        self.assertEqual(len(lines), 1, f"expected exactly one trace line, got {lines}")
        self.assertEqual(lines[0].get("verdict"), "PASS")

    # [BEHAVIORAL] AC2: a LOOP_GATE: PLAN_PASS completion writes BOTH the
    # existing .verifier_pass flag file AND a trace.jsonl event — neither
    # mechanism replaces the other.
    def test_plan_pass_completion_writes_both_flag_and_trace_event(self):
        name = self._track(unique_run_name("planpass"))
        transcript_body = (
            "# Role: Verifier\n\n"
            f"Plan-check for loop-team/runs/{name}/specs/spec.md.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": "Spec reviewed, no gaps.\nLOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)

        # Existing flag-write mechanism must still fire (regression guard,
        # duplicated intentionally at the point of the new interaction so a
        # future change to trace-logging can't silently swallow this path).
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected_flag),
            f"Expected .verifier_pass flag not found: {expected_flag}",
        )

        # New trace-logging mechanism must ALSO fire for the same completion.
        lines = read_trace_lines(name)
        self.assertEqual(len(lines), 1, f"expected exactly one trace line, got {lines}")


class TraceLoggingNoRunDirFailsOpen(unittest.TestCase):
    """spec.md AC4: when no loop-team/runs/<...> path can be resolved at all
    (transcript_path missing, unreadable, or present-but-pathless), the hook
    must not crash, must not block, and must simply skip trace-writing."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-transcript-")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # [BEHAVIORAL] AC4: no transcript_path key at all in the payload -> exit
    # 0, no exception, nothing written anywhere reachable.
    def test_no_transcript_path_key_exits_zero_no_crash(self):
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "last_assistant_message": "Done.\nVERDICT: PASS",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)

    # [BEHAVIORAL] AC4: transcript_path points at a file that does not exist
    # on disk -> exit 0, no exception surfaces.
    def test_nonexistent_transcript_path_exits_zero_no_crash(self):
        bogus_path = os.path.join(self._tmpdir, f"does-not-exist-{uuid.uuid4()}.txt")
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": bogus_path,
            "last_assistant_message": "Done.\nVERDICT: PASS",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)

    # [BEHAVIORAL] AC4: transcript_path is valid and readable but contains no
    # loop-team/runs/ path anywhere -> exit 0, no trace write, no crash.
    def test_transcript_with_no_run_dir_path_skips_trace_write(self):
        tpath = write_transcript(
            self._tmpdir,
            "# Role: Coder\n\nJust some ordinary conversation with no run-dir path.\n",
        )
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.\nVERDICT: PASS",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)

    # [BEHAVIORAL] AC4: transcript_path is non-string (e.g. an integer,
    # malformed payload) -> exit 0, no exception.
    def test_non_string_transcript_path_exits_zero_no_crash(self):
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": 12345,
            "last_assistant_message": "Done.\nVERDICT: PASS",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)


class TraceLoggingExceptionSafetyDoesNotBreakFlagWrite(unittest.TestCase):
    """spec.md AC5: any exception anywhere in the new trace-logging code path
    (malformed run_dir, unwritable path, corrupt transcript_path) must be
    caught and swallowed WITHOUT affecting the existing flag-write logic or
    the hook's overall exit code — same defensive try/except style as the
    two existing top-level blocks in this file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-transcript-")
        self._sessions_to_clean = []
        self._run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass
        for name in self._run_names:
            shutil.rmtree(run_dir_for(name), ignore_errors=True)

    def _track(self, name):
        self._run_names.append(name)
        return name

    # [BEHAVIORAL] AC5: transcript_path resolves to a DIRECTORY (not a file)
    # -> reading it raises (IsADirectoryError); the existing PLAN_PASS
    # flag-write must still succeed and the hook must still exit 0.
    def test_directory_as_transcript_path_does_not_break_flag_write(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": self._tmpdir,  # a directory, not a file
            "last_assistant_message": "Reviewed.\nLOOP_GATE: PLAN_PASS",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected_flag),
            "existing flag-write must survive a corrupt transcript_path",
        )

    # [BEHAVIORAL] AC5: transcript resolves a run_dir name containing path
    # traversal / separator-hostile characters that could make the derived
    # trace path invalid or land outside loop-team/runs/; the hook must not
    # crash and the existing flag-write must still succeed. (The regex
    # excludes '/', so this exercises characters it does NOT exclude, e.g. a
    # null byte, which is invalid in a POSIX path.)
    def test_hostile_run_dir_name_does_not_break_flag_write(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        hostile_name = "bad\x00name"
        transcript_body = (
            "# Role: Coder\n\n"
            f"loop-team/runs/{hostile_name}/specs/spec.md\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": "Done.\nLOOP_GATE: PLAN_PASS",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected_flag),
            "existing flag-write must survive a hostile/invalid derived run_dir name",
        )

    # [BEHAVIORAL] AC5: Tracer import failure is simulated by pointing
    # PYTHONPATH-sensitive resolution at a broken environment: we can't
    # rename run_trace.py from a test (out of scope / too invasive), so
    # instead we assert the general contract this AC requires — an
    # unwritable run_dir (a FILE sitting where the run directory needs to be
    # a directory) must not break the flag-write or the exit code.
    def test_unwritable_run_dir_does_not_break_flag_write(self):
        name = self._track(unique_run_name("unwritable"))
        # Pre-create a plain FILE at the run_dir path, so the hook's own
        # os.makedirs(run_dir, exist_ok=True) (or equivalent) fails with a
        # real OSError/NotADirectoryError when it tries to create/use it as
        # a directory.
        os.makedirs(RUNS_DIR, exist_ok=True)
        blocking_path = run_dir_for(name)
        with open(blocking_path, "w", encoding="utf-8") as f:
            f.write("this is a file, not a directory\n")
        try:
            transcript_body = (
                "# Role: Coder\n\n"
                f"loop-team/runs/{name}/specs/spec.md\n"
            )
            tpath = write_transcript(self._tmpdir, transcript_body)
            sid = unique_session()
            aid = f"agent-{uuid.uuid4()}"
            self._sessions_to_clean.append(sid)
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": tpath,
                "last_assistant_message": "Done.\nLOOP_GATE: PLAN_PASS",
            }
            code, stderr = run_gate(payload)
            self.assertEqual(code, 0)
            self.assertNotIn("Traceback", stderr)
            expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
            self.assertTrue(
                os.path.exists(expected_flag),
                "existing flag-write must survive an unwritable/blocked run_dir path",
            )
        finally:
            if os.path.isfile(blocking_path):
                os.remove(blocking_path)
            elif os.path.isdir(blocking_path):
                shutil.rmtree(blocking_path, ignore_errors=True)


class BareRunDirFormResolution(unittest.TestCase):
    """spec.md H-TRACE-WIRING-1, AC1/AC2/AC22: the trace-logging responsibility
    must recognize BOTH the bare `runs/<name>/...` form and the
    `loop-team/runs/<name>/...` form, writing trace.jsonl under the matching
    tree — never a single hardcoded location."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-bare-")
        self._run_names = []
        self._bare_run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._run_names:
            shutil.rmtree(run_dir_for(name), ignore_errors=True)
        for name in self._bare_run_names:
            shutil.rmtree(bare_run_dir_for(name), ignore_errors=True)

    def _track_loopteam(self, name):
        self._run_names.append(name)
        return name

    def _track_bare(self, name):
        self._bare_run_names.append(name)
        return name

    # [BEHAVIORAL] AC1: a transcript whose FIRST run-dir-shaped reference is
    # bare `runs/<name>/...` (no loop-team/ prefix) produces exactly one
    # trace.jsonl event under <repo_root>/runs/<name>/trace.jsonl.
    def test_bare_form_writes_under_repo_root_runs(self):
        name = self._track_bare(unique_run_name("bare"))
        transcript_body = (
            "# Role: Coder\n\n"
            f"The spec is at runs/{name}/specs/spec.md.\n"
            "I've implemented the change as described.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Implementation complete.",
        }
        before = read_bare_trace_lines(name)
        self.assertEqual(before, [])
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        after = read_bare_trace_lines(name)
        self.assertEqual(
            len(after), 1,
            f"expected exactly one new bare-form trace.jsonl line, got {after}",
        )
        # Must NOT also land under loop-team/runs/<name>/trace.jsonl.
        self.assertEqual(
            read_trace_lines(name), [],
            "bare-form reference must not ALSO write to loop-team/runs/",
        )

    # [BEHAVIORAL] AC2 (regression guard): a transcript whose first reference
    # is loop-team/runs/<name>/... continues to resolve under
    # <repo_root>/loop-team/runs/<name>/trace.jsonl unchanged, reusing the
    # existing real-directory fixture convention.
    def test_loop_team_form_still_writes_under_loop_team_runs(self):
        name = self._track_loopteam(unique_run_name("lt"))
        transcript_body = (
            "# Role: Coder\n\n"
            f"The spec is at loop-team/runs/{name}/specs/spec.md.\n"
            "I've implemented the change as described.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Implementation complete.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        after = read_trace_lines(name)
        self.assertEqual(len(after), 1, f"expected one loop-team/-form trace line, got {after}")

    # [BEHAVIORAL] AC22: a loop-team/runs/<name>/... reference immediately
    # preceded by ordinary prose text (the real fixture shape) resolves to
    # the loop-team/-prefixed path, NOT the bare-form path — the primary
    # regression check on the two-pass finditer + shadow-exclusion design.
    def test_prose_preceded_loop_team_form_resolves_to_loop_team_path_not_bare(self):
        name = self._track_loopteam(unique_run_name("prose-lt"))
        transcript_body = (
            "# Role: Coder\n\n"
            f"You are implementing the spec at loop-team/runs/{name}/specs/spec.md.\n"
            "Please proceed.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertEqual(len(read_trace_lines(name)), 1)
        self.assertEqual(
            read_bare_trace_lines(name), [],
            "shadow-exclusion must prevent the embedded bare 'runs/<name>' "
            "substring from ALSO writing to <repo_root>/runs/<name>/",
        )


class NoFalsePositiveRunDirMatches(unittest.TestCase):
    """spec.md AC3/AC4/AC5: prose uses of 'runs' and hyphen/word-boundary-
    adjacent 'runs' substrings must never be misparsed as a run-dir
    reference, via the (?<![\\w-]) negative-lookbehind boundary rule."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-negative-")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        # AC24's fixture uses a short literal name ("X") that the CURRENT,
        # unmodified hook's unanchored regex actually matches and writes to
        # (the bug this AC exists to close) — clean it up unconditionally so
        # a red run doesn't leak a real directory into loop-team/runs/.
        shutil.rmtree(run_dir_for("X"), ignore_errors=True)
        shutil.rmtree(bare_run_dir_for("X"), ignore_errors=True)

    # [BEHAVIORAL] AC3: prose phrase "many runs of the eval suite" (no path)
    # produces NO trace.jsonl write anywhere, exit 0, no crash.
    def test_prose_many_runs_produces_no_trace_write(self):
        name_would_be = "of"  # if buggy, "runs/of" could be captured -> "of"
        transcript_body = (
            "# Role: Coder\n\n"
            "We did many runs of the eval suite this week and it stayed green.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(read_bare_trace_lines(name_would_be), [])

    # [BEHAVIORAL] AC4: path `test-runs/foo/bar.md` (hyphen immediately
    # before "runs") produces NO trace.jsonl write under runs/foo or
    # test-runs/foo, exit 0, no crash — must use (?<![\w-]), not a plain \b.
    def test_hyphen_prefixed_test_runs_produces_no_trace_write(self):
        transcript_body = (
            "# Role: Coder\n\n"
            "See test-runs/foo/bar.md for the fixture data.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(read_bare_trace_lines("foo"), [])
        self.assertEqual(
            read_bare_trace_lines("test-runs"), [],
            "must not misparse 'test-runs' itself as a run name either",
        )

    # [BEHAVIORAL] AC5: literal substring `underruns/foo` (word char
    # immediately before "runs") produces NO trace.jsonl write, exit 0, no
    # crash.
    def test_word_char_prefixed_underruns_produces_no_trace_write(self):
        transcript_body = (
            "# Role: Coder\n\n"
            "The path underruns/foo does not exist and is not a run dir.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(read_bare_trace_lines("foo"), [])

    # [BEHAVIORAL] AC23: bare `runs/` reference preceded by a SPACE in
    # ordinary prose narration (exactly orchestrator.md's own documented
    # shape) DOES match and produces trace.jsonl under the bare form — the
    # positive case closing the revision-4 boundary-rule narrowness gap.
    def test_space_preceded_bare_form_in_prose_resolves_correctly(self):
        name = f"2026-07-03_foo-{uuid.uuid4()}"
        try:
            transcript_body = (
                "# Role: Coder\n\n"
                f"the spec is at runs/{name}/specs/spec.md\n"
                "Proceeding with implementation.\n"
            )
            tpath = write_transcript(self._tmpdir, transcript_body)
            payload = {
                "session_id": unique_session(),
                "agent_id": "a1",
                "transcript_path": tpath,
                "last_assistant_message": "Done.",
            }
            code, _ = run_gate(payload)
            self.assertEqual(code, 0)
            after = read_bare_trace_lines(name)
            self.assertEqual(
                len(after), 1,
                f"space-preceded bare 'runs/' prose reference must match, got {after}",
            )
        finally:
            shutil.rmtree(bare_run_dir_for(name), ignore_errors=True)

    # [BEHAVIORAL] AC24: "xloop-team/runs/X/specs/spec.md" (loop-team/runs/
    # reference immediately preceded by a letter) produces NO trace.jsonl
    # write anywhere — neither the loop-team/-form NOR the bare-form
    # location (closes both the internal-inconsistency gap and the
    # orphaned-bare-match gap).
    def test_letter_prefixed_loop_team_form_produces_no_trace_write_either_location(self):
        name = "X"
        transcript_body = (
            "# Role: Coder\n\n"
            "See xloop-team/runs/X/specs/spec.md for unrelated context.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(
            read_trace_lines(name), [],
            "must not write to loop-team/runs/X/trace.jsonl",
        )
        self.assertEqual(
            read_bare_trace_lines(name), [],
            "must not write to runs/X/trace.jsonl either (orphaned bare-match gap)",
        )


class PlaceholderTemplateTextNotCapturedAsRunDir(unittest.TestCase):
    """Regression guard for the angle-bracket placeholder bug: this project's
    own onboarding/skill docs use the literal template form
    `runs/<YYYY-MM-DD_HHMMSS>-<slug>/` (and sibling forms like `runs/<ts>/`,
    `runs/<name>/`) as human-facing documentation placeholders — NOT real
    run-directory names. Before the `<`/`>` exclusion fix, the capture class
    `[^/\\s"'\\)]+` happily matched into and through `<`/`>`, so a transcript
    containing this exact boilerplate (e.g. quoted from README.md/
    orchestrator.md during boot/skill context) would capture the literal
    placeholder text `<YYYY-MM-DD_HHMMSS>-<slug>` as if it were a real run
    name — and because `candidates.sort(key=lambda c: c[1])` picks the
    EARLIEST match, a placeholder appearing early in a transcript would win
    over a real, later `runs/`-prefixed reference almost every time.

    Confirmed independently (see decision-log): real slugs on disk under
    both `<repo_root>/runs/` and `<repo_root>/loop-team/runs/` use only
    alphanumerics, `-`, and `_` — never `<` or `>` — so excluding those two
    characters from the capture class cannot reject any legitimate name."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-placeholder-")
        self._bare_run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._bare_run_names:
            shutil.rmtree(bare_run_dir_for(name), ignore_errors=True)
        # NOTE: deliberately NOT deleting bare_run_dir_for(
        # "<YYYY-MM-DD_HHMMSS>-<slug>") here, even defensively: that exact
        # directory already exists on disk as a real, pre-existing artifact
        # of the bug this class regression-tests (133 real trace.jsonl
        # events from unrelated prior builds, predating this fix). Deciding
        # what to do with that already-corrupted data is out of scope for
        # this fix (Oga's call) — this test suite must never delete it,
        # regardless of red/green outcome.

    # [BEHAVIORAL] placeholder boilerplate appears EARLY in the transcript
    # (as it would in real boot/skill context quoting the docs), followed
    # LATER by a real, well-formed runs/<real-name>/ reference. After the
    # fix, the resolved run directory must be the REAL one — never the
    # placeholder text — proving the fix closes the "earliest-match wins"
    # failure mode, not just a standalone-placeholder case.
    def test_placeholder_boilerplate_then_real_reference_resolves_to_real_one(self):
        real_name = f"2026-07-03_a-real-build-{uuid.uuid4()}"
        self._bare_run_names.append(real_name)
        transcript_body = (
            "# Role: Coder\n\n"
            "Onboarding context quoted from this project's own docs: each "
            "build's run log lives at runs/<YYYY-MM-DD_HHMMSS>-<slug>/ "
            "alongside its trace.jsonl.\n\n"
            f"Your actual assignment: the spec is at runs/{real_name}/specs/spec.md.\n"
            "Proceeding with implementation.\n"
        )
        # NOTE: a pre-existing, already-corrupted directory literally named
        # "<YYYY-MM-DD_HHMMSS>-<slug>" (with a real, actively-growing
        # trace.jsonl inside it) already exists on disk from BEFORE this fix
        # — deciding what to do with that already-corrupted data is out of
        # this task's scope (Oga's call). Snapshot its line count before
        # running the gate so the post-run assertion can prove THIS
        # invocation appended nothing new, without asserting the file is
        # empty/absent or touching its pre-existing contents.
        placeholder_lines_before = read_bare_trace_lines("<YYYY-MM-DD_HHMMSS>-<slug>")

        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Implementation complete.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)

        after = read_bare_trace_lines(real_name)
        self.assertEqual(
            len(after), 1,
            f"expected the REAL run reference to win and get exactly one "
            f"trace.jsonl line, got {after}",
        )

        # The placeholder text itself must never have been treated as a
        # valid run name for THIS invocation — no NEW line should have been
        # appended to its (pre-existing) trace.jsonl.
        placeholder_lines_after = read_bare_trace_lines("<YYYY-MM-DD_HHMMSS>-<slug>")
        self.assertEqual(
            len(placeholder_lines_after), len(placeholder_lines_before),
            "the literal placeholder text must never be captured as a "
            "run-dir name, even though it appears earlier in the transcript "
            "than the real reference — no new trace.jsonl line should have "
            "been appended to the placeholder-named directory",
        )

    # [BEHAVIORAL] companion case: ONLY the placeholder text is present in
    # the transcript, no real runs/ reference anywhere else. The hook must
    # find NO valid candidate at all — fail open / write nothing — rather
    # than falling back to the placeholder text as if it were real.
    def test_placeholder_boilerplate_alone_produces_no_trace_write(self):
        transcript_body = (
            "# Role: Coder\n\n"
            "Onboarding context quoted from this project's own docs: each "
            "build's run log lives at runs/<YYYY-MM-DD_HHMMSS>-<slug>/ "
            "alongside its trace.jsonl. There is no other runs/ reference "
            "anywhere in this transcript.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        before_listing = (
            set(os.listdir(BARE_RUNS_DIR)) if os.path.isdir(BARE_RUNS_DIR) else set()
        )
        # NOTE: a pre-existing, already-corrupted directory literally named
        # "<YYYY-MM-DD_HHMMSS>-<slug>" (with a real, actively-growing
        # trace.jsonl inside it) already exists on disk from BEFORE this fix
        # — deciding what to do with that already-corrupted data is out of
        # this task's scope (Oga's call, not this fix's). So this assertion
        # uses a before/after LINE-COUNT diff on that pre-existing file
        # rather than asserting it's empty/absent — proving this invocation
        # appended NO new line to it, without asserting anything about (or
        # touching) its pre-existing contents.
        placeholder_lines_before = read_bare_trace_lines("<YYYY-MM-DD_HHMMSS>-<slug>")
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)

        after_listing = (
            set(os.listdir(BARE_RUNS_DIR)) if os.path.isdir(BARE_RUNS_DIR) else set()
        )
        self.assertEqual(
            after_listing, before_listing,
            "no new directory should appear under <repo_root>/runs/ when "
            "the ONLY 'runs/'-shaped reference is placeholder template text",
        )
        placeholder_lines_after = read_bare_trace_lines("<YYYY-MM-DD_HHMMSS>-<slug>")
        self.assertEqual(
            len(placeholder_lines_after), len(placeholder_lines_before),
            "this invocation must not append a new trace.jsonl line to the "
            "placeholder-named directory, even though it pre-exists on disk "
            "from before this fix",
        )


class BacktickBackslashSourceEmbedNotCapturedAsRunDir(unittest.TestCase):
    """Regression guard for H-MALFORMED-RUN-DIRS-1: this hook's OWN source
    comments and fix_plan.md's own prose describe the `runs/<name>/...`
    convention using Markdown-code-span backticks (e.g. this file's own line
    "recognize BOTH the bare `runs/<name>/...` form", or fix_plan.md text
    like "loop-team/runs/`<name>`/" and "loop-team/runs/\\`` "). Before the
    backtick/backslash exclusion fix, the capture class
    `[^/\\s"'\\)<>]+` happily matched into and through a lone backtick or a
    backslash-backtick pair, so a sub-agent transcript that happened to quote
    that documentation/source (e.g. it read this hook's own file, or read
    fix_plan.md's entry describing this exact bug) would have that
    placeholder/example text mistaken for a literal run-dir name and a
    garbage directory created — confirmed live: three such directories
    (named "`", "<name>`", and "\\`` ") were found on disk, one containing
    trace entries whose `note` field was a real sub-agent's agentId.

    Companion positive case (test_genuine_dispatch_reference_still_resolves)
    proves the fix does not regress legitimate detection: a transcript
    containing ordinary, real dispatch text (no backticks/backslashes in the
    captured name) must still resolve and create that real run_dir."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-backtick-")
        self._bare_run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._bare_run_names:
            shutil.rmtree(bare_run_dir_for(name), ignore_errors=True)

    # [BEHAVIORAL] a transcript containing this hook's OWN line-337-shaped
    # comment text ("the bare `runs/<name>/...` form") must produce NO trace
    # write anywhere reachable — the backtick-wrapped placeholder must never
    # be captured as a run-dir name.
    def test_hook_own_source_comment_shaped_text_produces_no_trace_write(self):
        transcript_body = (
            "# Role: Coder\n\n"
            "I read hooks/subagent_stop_gate.py and found this comment: "
            "\"recognize BOTH the bare `runs/<name>/...` form and the "
            "`loop-team/runs/<name>/...` form.\" This documents the "
            "existing convention.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        before_listing = (
            set(os.listdir(BARE_RUNS_DIR)) if os.path.isdir(BARE_RUNS_DIR) else set()
        )
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Investigated the bug.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        after_listing = (
            set(os.listdir(BARE_RUNS_DIR)) if os.path.isdir(BARE_RUNS_DIR) else set()
        )
        self.assertEqual(
            after_listing, before_listing,
            "no new directory should appear under <repo_root>/runs/ when the "
            "only 'runs/'-shaped reference is this hook's own backtick-"
            "wrapped source-comment placeholder text",
        )

    # [BEHAVIORAL] a transcript containing fix_plan.md-shaped prose
    # describing THIS exact bug (backtick-wrapped `<name>` placeholder AND
    # the literal backslash-backtick form "loop-team/runs/\`` ") must
    # produce NO trace write anywhere reachable, for either form/location.
    #
    # NOTE on assertion style: this exact prose is engineered to reproduce
    # the live bug (confirmed independently: on unmodified pre-fix code, the
    # LT_PATTERN's leftmost match here captures the bare literal backtick
    # "`", which resolves to the REAL, ALREADY-EXISTING garbage directory
    # `loop-team/runs/`` ` `` on this repo's disk — see H-MALFORMED-RUN-DIRS-1
    # in fix_plan.md). A directory-listing set-equality check would therefore
    # be a false negative here (the malformed dir already exists, so no NEW
    # entry appears in the listing even when the bug fires and APPENDS a new
    # line to its trace.jsonl) — so this asserts a before/after LINE-COUNT
    # diff on that specific pre-existing path instead, exactly the pattern
    # PlaceholderTemplateTextNotCapturedAsRunDir already established for the
    # analogous already-corrupted `<YYYY-MM-DD_HHMMSS>-<slug>` fixture.
    def test_fix_plan_shaped_prose_produces_no_trace_write(self):
        backtick_dir_lines_before = read_trace_lines("`")
        transcript_body = (
            "# Role: Coder\n\n"
            "Root cause, confirmed by reading the code: "
            "hooks/subagent_stop_gate.py's LT_PATTERN/BARE_PATTERN regexes "
            "scan a completing sub-agent's own transcript for text matching "
            "loop-team/runs/`<name>`/ or `runs/<something>` to detect which "
            "run directory a dispatch belongs to. A THIRD malformed "
            "directory, loop-team/runs/\\`` (literal backslash + backtick "
            "chars), was found freshly created today.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Investigated the bug.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        backtick_dir_lines_after = read_trace_lines("`")
        self.assertEqual(
            len(backtick_dir_lines_after), len(backtick_dir_lines_before),
            "fix_plan.md-shaped backtick/backslash prose must not append a "
            "new trace.jsonl line to the pre-existing "
            "loop-team/runs/`<literal backtick>` garbage directory — the "
            "captured name must be rejected outright, not silently written "
            "into whatever it happens to resolve to",
        )

    # [BEHAVIORAL] companion positive case: a synthetic transcript containing
    # genuine dispatch text (an ordinary, real run-dir reference with no
    # backtick/backslash in the captured name) must still resolve correctly
    # and create that real run_dir — proving the fix does not regress
    # legitimate detection.
    def test_genuine_dispatch_reference_still_resolves(self):
        name = unique_run_name("genuine")
        self._bare_run_names.append(name)
        transcript_body = (
            "# Role: Coder\n\n"
            f"...your run directory is runs/{name}/... — proceed with the "
            "implementation as described in the spec.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        before = read_bare_trace_lines(name)
        self.assertEqual(before, [])
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Implementation complete.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        after = read_bare_trace_lines(name)
        self.assertEqual(
            len(after), 1,
            f"expected the genuine dispatch reference to resolve and create "
            f"exactly one new trace.jsonl line, got {after}",
        )

    # [BEHAVIORAL] companion positive case for the loop-team/-prefixed form:
    # same genuine-reference proof, using the loop-team/runs/<name> form
    # instead of the bare form.
    def test_genuine_loop_team_form_dispatch_reference_still_resolves(self):
        name = unique_run_name("genuine-lt")
        run_dir = run_dir_for(name)
        transcript_body = (
            "# Role: Coder\n\n"
            f"...your run directory is loop-team/runs/{name}/... — proceed "
            "with the implementation as described in the spec.\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        before = read_trace_lines(name)
        self.assertEqual(before, [])
        payload = {
            "session_id": unique_session(),
            "agent_id": f"agent-{uuid.uuid4()}",
            "transcript_path": tpath,
            "last_assistant_message": "Implementation complete.",
        }
        try:
            code, stderr = run_gate(payload)
            self.assertEqual(code, 0)
            self.assertNotIn("Traceback", stderr)
            after = read_trace_lines(name)
            self.assertEqual(
                len(after), 1,
                f"expected the genuine loop-team/-form dispatch reference to "
                f"resolve and create exactly one new trace.jsonl line, got {after}",
            )
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class CrossFormFirstMatchWins(unittest.TestCase):
    """spec.md AC6: when both a bare `runs/B/...` and a `loop-team/runs/A/...`
    reference appear in the same transcript, whichever occurs FIRST
    left-to-right wins, regardless of form — in BOTH orderings."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-crossform-")
        self._run_names = []
        self._bare_run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._run_names:
            shutil.rmtree(run_dir_for(name), ignore_errors=True)
        for name in self._bare_run_names:
            shutil.rmtree(bare_run_dir_for(name), ignore_errors=True)

    # [BEHAVIORAL] AC6 case 1: bare runs/B/... appears EARLIER, loop-team/
    # runs/A/... appears LATER -> resolves to the bare form (B), not A.
    def test_bare_form_first_wins_over_later_loop_team_form(self):
        b = unique_run_name("crossB")
        a = unique_run_name("crossA")
        self._bare_run_names.append(b)
        self._run_names.append(a)
        transcript_body = (
            "# Role: Coder\n\n"
            f"Primary spec: runs/{b}/specs/spec.md\n"
            f"Also referenced later: loop-team/runs/{a}/specs/spec.md\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertEqual(len(read_bare_trace_lines(b)), 1)
        self.assertEqual(read_trace_lines(a), [])

    # [BEHAVIORAL] AC6 case 2 (order swapped): loop-team/runs/A/... appears
    # EARLIER, bare runs/B/... appears LATER -> resolves to the loop-team/
    # form (A), not B — proving the rule is position-based, not form-based.
    def test_loop_team_form_first_wins_over_later_bare_form(self):
        a = unique_run_name("swapA")
        b = unique_run_name("swapB")
        self._run_names.append(a)
        self._bare_run_names.append(b)
        transcript_body = (
            "# Role: Coder\n\n"
            f"Primary spec: loop-team/runs/{a}/specs/spec.md\n"
            f"Also referenced later: runs/{b}/specs/spec.md\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertEqual(len(read_trace_lines(a)), 1)
        self.assertEqual(read_bare_trace_lines(b), [])


class PathContainmentTraversalGuard(unittest.TestCase):
    """spec.md AC7: a captured run-dir name of literal '..' (path traversal,
    exploiting that the capture class excludes '/' but not '.') must be
    rejected by a real containment check — no trace write outside the
    intended runs/ tree, for EITHER form. This is NEW required behavior.

    Precise escape targets (verified by hand against the CURRENT, unmodified
    hook): a captured name of '..' under the loop-team/ form makes
    os.path.join(repo_root, 'loop-team', 'runs', '..') resolve to
    <repo_root>/loop-team/ itself (NOT one level above BARE_RUNS_DIR/RUNS_DIR
    as a naive off-by-one check would assume) — os.path.join only appends
    ONE '..' segment, so the escape lands exactly one directory above the
    'runs' component, at the 'loop-team' directory. The bare form's
    equivalent escape lands at <repo_root> itself. Both targets are asserted
    directly (a trace.jsonl file must never appear there) rather than via a
    directory-listing diff one level too high, which would silently miss
    the real, single-level escape this AC targets."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-traversal-")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # [BEHAVIORAL] AC7: bare-form `runs/../escape-marker/...` traversal:
    # the captured name '..' must be rejected by containment, so
    # <repo_root>/trace.jsonl (the resolved os.path.join(repo_root, 'runs',
    # '..') escape target) is never created, and no 'escape-marker'
    # directory appears at <repo_root> either.
    def test_bare_form_dotdot_traversal_is_rejected(self):
        escape_trace = os.path.join(REPO_ROOT, "trace.jsonl")
        escape_marker_dir = os.path.join(REPO_ROOT, "escape-marker")
        self.assertFalse(
            os.path.exists(escape_trace),
            "precondition: no stray trace.jsonl should already exist at repo root",
        )
        transcript_body = (
            "# Role: Coder\n\n"
            "Malicious path reference: runs/../escape-marker/specs/spec.md\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        try:
            self.assertEqual(code, 0)
            self.assertNotIn("Traceback", stderr)
            self.assertFalse(
                os.path.exists(escape_trace),
                "path-containment check must prevent a trace.jsonl write "
                "at <repo_root>/trace.jsonl via a '..' captured name",
            )
            self.assertFalse(os.path.exists(escape_marker_dir))
        finally:
            if os.path.exists(escape_trace):
                os.remove(escape_trace)
            if os.path.isdir(escape_marker_dir):
                shutil.rmtree(escape_marker_dir, ignore_errors=True)

    # [BEHAVIORAL] AC7: loop-team/runs/ form of the same traversal: the
    # captured name '..' resolves os.path.join(repo_root, 'loop-team',
    # 'runs', '..') to <repo_root>/loop-team/ itself — so
    # <repo_root>/loop-team/trace.jsonl must never be created.
    def test_loop_team_form_dotdot_traversal_is_rejected(self):
        loop_team_dir = os.path.join(REPO_ROOT, "loop-team")
        escape_trace = os.path.join(loop_team_dir, "trace.jsonl")
        self.assertFalse(
            os.path.exists(escape_trace),
            "precondition: no stray trace.jsonl should already exist at loop-team/",
        )
        transcript_body = (
            "# Role: Coder\n\n"
            "Malicious path reference: loop-team/runs/../x/specs/spec.md\n"
        )
        tpath = write_transcript(self._tmpdir, transcript_body)
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        try:
            self.assertEqual(code, 0)
            self.assertNotIn("Traceback", stderr)
            self.assertFalse(
                os.path.exists(escape_trace),
                "path-containment check must prevent a trace.jsonl write "
                "at <repo_root>/loop-team/trace.jsonl via a '..' captured name",
            )
        finally:
            if os.path.exists(escape_trace):
                os.remove(escape_trace)


class TruncationGuardForLiveTranscripts(unittest.TestCase):
    """spec.md AC25: a transcript_content that does not end with a newline,
    whose final (incomplete) line contains a run-dir-shaped reference that
    would otherwise match, must exclude that dangling reference from the
    scan — while an earlier, complete reference in the same transcript still
    resolves normally."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-trace-truncation-")
        self._bare_run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for name in self._bare_run_names:
            shutil.rmtree(bare_run_dir_for(name), ignore_errors=True)

    # [BEHAVIORAL] AC25: a lone truncated trailing reference (no complete
    # earlier one) produces NO trace write anywhere reachable.
    def test_truncated_trailing_reference_alone_produces_no_trace_write(self):
        # Deliberately incomplete: the name is cut off mid-word and the file
        # does NOT end with a newline, simulating a read landing mid-write.
        path = os.path.join(self._tmpdir, f"transcript-{uuid.uuid4()}.txt")
        body = "# Role: Coder\n\nThe spec is at runs/2026-07-03_h-trace-"
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)  # no trailing \n on purpose
        # Snapshot BEFORE running the gate: a real, legitimate, pre-existing
        # directory (e.g. this very build's own run dir) can share the
        # literal "2026-07-03_h-trace-" prefix with this deliberately-
        # truncated fixture name, so a static prefix filter against
        # everything currently in BARE_RUNS_DIR would false-positive on it.
        # Comparing a before/after diff instead isolates only a NEW leak
        # produced by this invocation.
        before = set(os.listdir(BARE_RUNS_DIR)) if os.path.isdir(BARE_RUNS_DIR) else set()
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": path,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        # No NEW directory beginning with this truncated prefix should appear.
        if os.path.isdir(BARE_RUNS_DIR):
            after = set(os.listdir(BARE_RUNS_DIR))
            leaked = [
                d for d in (after - before)
                if d.startswith("2026-07-03_h-trace-")
            ]
            self.assertEqual(
                leaked, [],
                f"truncated trailing reference must not produce a run dir: {leaked}",
            )

    # [BEHAVIORAL] AC25: an EARLIER complete reference still resolves
    # normally even when the transcript's final line is truncated/dangling.
    def test_earlier_complete_reference_still_resolves_despite_trailing_truncation(self):
        complete_name = unique_run_name("complete")
        self._bare_run_names.append(complete_name)
        path = os.path.join(self._tmpdir, f"transcript-{uuid.uuid4()}.txt")
        body = (
            "# Role: Coder\n\n"
            f"The complete spec is at runs/{complete_name}/specs/spec.md\n\n"
            "A later, still-being-written truncated reference: runs/2026-07-03_h-trace-"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)  # no trailing \n — final line is incomplete
        payload = {
            "session_id": unique_session(),
            "agent_id": "a1",
            "transcript_path": path,
            "last_assistant_message": "Done.",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        after = read_bare_trace_lines(complete_name)
        self.assertEqual(
            len(after), 1,
            f"earlier complete reference must still resolve, got {after}",
        )


class StructuredOutputFlagWriteDetection(unittest.TestCase):
    """spec.md AC8/AC9/AC16/AC18/AC19/AC20/AC21: the new, second flag-write
    detection path for Workflow+schema plan-check-verifier dispatches whose
    final turn is a forced StructuredOutput tool_use block instead of free
    text."""

    DEBUG_LOG = os.path.join(GATE_DIR, "subagent_gate_debug.jsonl")

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-structured-output-")
        self._sessions_to_clean = []
        if os.path.exists(self.DEBUG_LOG):
            with open(self.DEBUG_LOG, encoding="utf-8") as f:
                self._debug_lines_before = len(f.readlines())
        else:
            self._debug_lines_before = 0

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _new_debug_lines_for(self, sid):
        return read_debug_lines_for_session(self.DEBUG_LOG, self._debug_lines_before, sid)

    # [BEHAVIORAL] AC8: last StructuredOutput block has loop_gate: PLAN_PASS
    # and last_assistant_message is None/empty (real Workflow+schema shape)
    # -> flag file IS written using the same {session_id}_{agent_id}
    # convention, AND the debug-log entry's wrote_flag field is true (not
    # false) — the write-ordering requirement.
    def test_structured_output_plan_pass_with_no_free_text_writes_flag_and_debug_true(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            {"type": "user", "message": {"role": "user", "content": "Review this plan."}},
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected_flag), expected_flag)
        matches = self._new_debug_lines_for(sid)
        self.assertEqual(len(matches), 1, matches)
        self.assertTrue(matches[0].get("wrote_flag") is True, matches[0])

    # [BEHAVIORAL] AC9: last StructuredOutput block has loop_gate: PLAN_FAIL
    # -> flag file is NOT written.
    def test_structured_output_plan_fail_writes_no_flag(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_FAIL"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])

    # [BEHAVIORAL] AC16: TWO StructuredOutput blocks for the same completion
    # — an earlier PLAN_FAIL, a later (in event order) PLAN_PASS, no
    # free-text conclusion — resolves per "keep the LAST one": flag IS
    # written.
    def test_two_structured_output_blocks_keeps_last_one(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_FAIL"),
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": "",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected_flag))

    # [BEHAVIORAL] AC18: a StructuredOutput block whose input dict has NO
    # loop_gate key at all (unrelated Workflow+schema shape) and no matching
    # free-text line -> flag is NOT written. Distinguished from AC11 (no
    # StructuredOutput block at all) by exercising input.get('loop_gate')'s
    # absence-handling on a REAL block, not the absence of a block.
    def test_structured_output_block_without_loop_gate_key_writes_no_flag(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", None, extra_input={"some_other_field": "value"}),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(glob.glob(pattern), [])

    # [BEHAVIORAL] AC19: a well-formed, complete StructuredOutput/PLAN_PASS
    # block on an early line, followed by a deliberately malformed JSON line
    # later, no free-text conclusion -> flag IS still written (per-line
    # isolation) AND the debug-log entry's wrote_flag field is true. Both
    # outcomes asserted by the same test (highest-risk compound cell).
    def test_malformed_trailing_line_does_not_discard_earlier_valid_structured_output(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_PASS"),
            '{"type": "assistant", "message": {"content": [BROKEN JSON HERE',
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected_flag),
            "an earlier valid StructuredOutput/PLAN_PASS must survive a later malformed line",
        )
        matches = self._new_debug_lines_for(sid)
        self.assertEqual(len(matches), 1, matches)
        self.assertTrue(matches[0].get("wrote_flag") is True, matches[0])

    # [BEHAVIORAL] AC20: a StructuredOutput-only PLAN_PASS completion
    # (last_assistant_message is None) produces EXACTLY ONE
    # subagent_gate_debug.jsonl entry for that invocation, and that entry's
    # wrote_flag field is true. (Restates AC8's debug requirement as its own
    # explicit assertion.)
    def test_structured_output_only_completion_produces_exactly_one_debug_entry_true(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        matches = self._new_debug_lines_for(sid)
        self.assertEqual(
            len(matches), 1,
            f"expected exactly one debug entry for this invocation, got {matches}",
        )
        self.assertTrue(matches[0].get("wrote_flag") is True, matches[0])

    # [BEHAVIORAL] AC21: StructuredOutput PLAN_PASS, no free-text conclusion,
    # AND an empty session_id -> NO flag file written (tier-3 write path
    # must go through the same session_id guard as tier 1).
    def test_structured_output_plan_pass_with_empty_session_id_writes_no_flag(self):
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "session_id": "",
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        # Can't enumerate an empty-session flag safely; assert the specific
        # malformed-filename shape never appears (mirrors
        # test_empty_session_id_no_flag's existing check style).
        pattern = os.path.join(GATE_DIR, "_a1.verifier_pass")
        self.assertFalse(os.path.exists(pattern))

    # [BEHAVIORAL] AC21 variant: missing session_id key entirely (not just
    # empty string) with a StructuredOutput PLAN_PASS -> no flag written.
    def test_structured_output_plan_pass_with_missing_session_id_writes_no_flag(self):
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, "_a1.verifier_pass")
        self.assertFalse(os.path.exists(pattern))


class PrecedenceRuleBetweenFreeTextAndStructuredOutput(unittest.TestCase):
    """spec.md AC10/AC17/AC26: the 3-tier precedence rule between the
    free-text last-line check (tiers 1/2) and the StructuredOutput fallback
    (tier 3) when both signals are present, agreeing or disagreeing."""

    DEBUG_LOG = os.path.join(GATE_DIR, "subagent_gate_debug.jsonl")

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-precedence-")
        self._sessions_to_clean = []
        if os.path.exists(self.DEBUG_LOG):
            with open(self.DEBUG_LOG, encoding="utf-8") as f:
                self._debug_lines_before = len(f.readlines())
        else:
            self._debug_lines_before = 0

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _new_debug_lines_for(self, sid):
        return read_debug_lines_for_session(self.DEBUG_LOG, self._debug_lines_before, sid)

    # [BEHAVIORAL] AC10: BOTH a valid free-text "LOOP_GATE: PLAN_PASS" last
    # line AND a StructuredOutput block present, agreeing (both PASS) ->
    # exactly one flag file written (idempotent overwrite acceptable, not an
    # error); debug log records no fault / no duplicate-attempt entry.
    def test_agreeing_free_text_and_structured_output_both_pass_writes_one_flag(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": "All good.\nLOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected_flag))
        matches = self._new_debug_lines_for(sid)
        self.assertEqual(
            len(matches), 1,
            f"expected exactly one debug entry (no duplicate-attempt fault logged), got {matches}",
        )
        self.assertTrue(matches[0].get("wrote_flag") is True, matches[0])

    # [BEHAVIORAL] AC17: free-text last line explicitly reads
    # "LOOP_GATE: PLAN_FAIL" (case-insensitive) WHILE a StructuredOutput
    # block elsewhere has loop_gate: PLAN_PASS -> flag is NOT written (tier 2
    # suppresses tier 3; explicit free-text FAIL is authoritative).
    def test_free_text_plan_fail_suppresses_disagreeing_structured_output_pass(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": "Found a real gap.\nLOOP_GATE: PLAN_FAIL",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(
            glob.glob(pattern), [],
            "explicit free-text PLAN_FAIL must suppress a disagreeing StructuredOutput PASS",
        )

    # [BEHAVIORAL] AC26 (mirror of AC17): free-text last line explicitly
    # reads "LOOP_GATE: PLAN_PASS" WHILE a StructuredOutput block elsewhere
    # has loop_gate: PLAN_FAIL -> flag IS written (tier 1 wins over a
    # DISAGREEING tier 3), and the debug-log wrote_flag field is true and
    # reflects tier-1's outcome. Distinguishes "tier 1 wins because tier 3 is
    # irrelevant" from "tier 1 happens to agree with tier 3" (AC10 can't).
    def test_free_text_plan_pass_wins_over_disagreeing_structured_output_fail(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            structured_output_event("run-x", "PLAN_FAIL"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": "No gaps found.\nLOOP_GATE: PLAN_PASS",
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected_flag),
            "tier 1 (explicit free-text PLAN_PASS) must win over a disagreeing tier 3",
        )
        matches = self._new_debug_lines_for(sid)
        self.assertEqual(len(matches), 1, matches)
        self.assertTrue(matches[0].get("wrote_flag") is True, matches[0])


class StructuredOutputPerLineExceptionIsolation(unittest.TestCase):
    """spec.md AC12: any exception raised while parsing an INDIVIDUAL line
    during the StructuredOutput JSONL walk must be swallowed for THAT LINE
    ONLY, never abort the walk of other well-formed lines, and never affect
    the trace-logging responsibility's own success/failure."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-per-line-isolation-")
        self._sessions_to_clean = []
        self._bare_run_names = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass
        for name in self._bare_run_names:
            shutil.rmtree(bare_run_dir_for(name), ignore_errors=True)

    # [BEHAVIORAL] AC12: a malformed line BEFORE a well-formed
    # StructuredOutput/PLAN_PASS line does not prevent that later line from
    # being read and honored — proving per-line (not whole-block) isolation
    # from the opposite direction of AC19's after-the-fact case.
    def test_malformed_leading_line_does_not_prevent_later_valid_structured_output(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            '{"type": "assistant", "message": broken not json',
            structured_output_event("run-x", "PLAN_PASS"),
        ])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": None,
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected_flag),
            "a malformed EARLIER line must not abort the walk of later valid lines",
        )

    # [BEHAVIORAL] AC12: a malformed StructuredOutput-walk line coexists with
    # Problem 1's independent trace-logging responsibility in the SAME
    # transcript — the malformed line must not affect trace-logging's own
    # success (both responsibilities parse the same pre-read
    # transcript_content independently; a failure in one must never bleed
    # into the other).
    def test_malformed_structured_output_line_does_not_affect_trace_logging(self):
        name = unique_run_name("isolation")
        self._bare_run_names.append(name)
        sid = unique_session()
        self._sessions_to_clean.append(sid)
        tpath = write_jsonl_transcript(self._tmpdir, [
            f'{{"type": "user", "message": "The spec is at runs/{name}/specs/spec.md"}}',
            '{"type": "assistant", "message": TOTALLY BROKEN JSON [[[',
        ])
        payload = {
            "session_id": sid,
            "agent_id": "a1",
            "transcript_path": tpath,
            "last_assistant_message": "Done.",
        }
        code, stderr = run_gate(payload)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        after = read_bare_trace_lines(name)
        self.assertEqual(
            len(after), 1,
            "trace-logging (Problem 1) must succeed independently of a "
            "malformed line in the StructuredOutput (Problem 2) walk",
        )


class NoStructuredOutputAndNoFreeTextMatch(unittest.TestCase):
    """spec.md AC11: no StructuredOutput block AND no matching free-text
    last line writes no flag — existing behavior (regression guard), now
    exercised via a real JSONL transcript_path rather than only via the
    last_assistant_message-only payloads in SubagentStopGateFlagWrite."""

    # [BEHAVIORAL] AC11: a transcript with ordinary assistant turns, no
    # StructuredOutput tool_use block anywhere, and a last_assistant_message
    # that doesn't match PLAN_PASS/PLAN_FAIL -> no flag written.
    def test_no_structured_output_block_and_no_free_text_match_writes_no_flag(self):
        tmpdir = tempfile.mkdtemp(prefix="loop-no-match-")
        try:
            sid = unique_session()
            tpath = write_jsonl_transcript(tmpdir, [
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "Still reviewing the plan, not done yet."},
                ]}},
            ])
            payload = {
                "session_id": sid,
                "agent_id": "a1",
                "transcript_path": tpath,
                "last_assistant_message": "Still reviewing, no conclusion yet.",
            }
            code, _ = run_gate(payload)
            self.assertEqual(code, 0)
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            self.assertEqual(glob.glob(pattern), [])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class FullExistingSuiteContinuesToPass(unittest.TestCase):
    """spec.md AC14: the full existing hooks/test_subagent_stop_gate.py
    suite (all pre-existing tests, unmodified in behavior) continues to
    pass unchanged once this fix lands — this fix is additive/corrective to
    detection logic, not a rewrite of the file's existing contract.

    This is asserted structurally here (every pre-existing TestCase class
    name is still present and still collects at least one test) rather than
    literally re-running the whole module inside itself (which would be
    redundant with just running the suite directly) — the real enforcement
    of AC14 is that this file, unmodified in its pre-existing classes, is
    run as-is by the test runner; this class exists so AC14 has an explicit,
    named, executable anchor a Verifier can point to."""

    PRE_EXISTING_CLASS_NAMES = [
        "SubagentStopGateFlagWrite",
        "SubagentStopGateAlwaysExitsZero",
        "SubagentStopGateMissingOrBadFields",
        "SubagentStopGateLastLineFiltering",
        "SubagentGateDebugLog",
        "VerifierMdDocCheck",
        "TraceLoggingRunDirExtraction",
        "TraceLoggingExtractionAlgorithmSpecifics",
        "TraceLoggingVerdictAndFlagCoexistence",
        "TraceLoggingNoRunDirFailsOpen",
        "TraceLoggingExceptionSafetyDoesNotBreakFlagWrite",
    ]

    # [BEHAVIORAL] AC14: every pre-existing TestCase class from before this
    # spec's changes is still defined in this module and still has at least
    # one collectible test method — i.e. nothing was deleted or weakened to
    # zero-test-methods in the course of extending this file.
    def test_all_pre_existing_test_classes_still_present_with_tests(self):
        this_module = sys.modules[__name__]
        for cls_name in self.PRE_EXISTING_CLASS_NAMES:
            cls = getattr(this_module, cls_name, None)
            self.assertIsNotNone(cls, f"pre-existing test class {cls_name} was removed")
            test_methods = [
                m for m in dir(cls)
                if m.startswith("test_") and callable(getattr(cls, m))
            ]
            self.assertGreater(
                len(test_methods), 0,
                f"pre-existing test class {cls_name} has zero test methods",
            )


class OrchestratorMdDocumentsStructuredOutputSchemaRequirement(unittest.TestCase):
    """spec.md AC13 [DOC]: loop-team/orchestrator.md's parallel adversarial-
    lens plan-check section states the loop_gate schema-field requirement
    for Workflow-dispatched lenses, in prose."""

    ORCHESTRATOR_MD = os.path.join(REPO_ROOT, "loop-team", "orchestrator.md")

    def _read(self):
        try:
            with open(self.ORCHESTRATOR_MD, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            self.skipTest(f"orchestrator.md not found: {self.ORCHESTRATOR_MD}")

    # [DOC] AC13: orchestrator.md documents, in ONE localized passage (not
    # merely as scattered/unrelated occurrences elsewhere in the file), that
    # a Workflow-script dispatch of a plan-check-verifier lens via
    # agent(..., {schema: ...}) MUST include a top-level loop_gate field with
    # allowed values PLAN_PASS / PLAN_FAIL. A prior draft of this test used
    # independent whole-file assertIn checks for each term, which passed
    # vacuously against the UNMODIFIED file: "schema" already appears (in an
    # unrelated section, ~line 228, about schema/format-valid empty-content
    # detection) and "loop_gate"/"plan_pass"/"plan_fail" already appear (in
    # the PRE-EXISTING free-text Cowork-gate convention, ~lines 65-67) —
    # neither is the NEW sentence AC13 actually requires. This version
    # requires all four terms to co-occur within one proximity window
    # (a single paragraph-sized chunk of the file), which the unmodified
    # file cannot satisfy since no single passage ties "schema" to
    # "loop_gate"/"plan_pass"/"plan_fail" together today.
    def test_orchestrator_md_documents_loop_gate_schema_field_requirement(self):
        content = self._read()
        lower = content.lower()
        self.assertIn(
            "loop_gate",
            lower,
            "orchestrator.md must document the required 'loop_gate' schema field",
        )
        self.assertIn("schema", lower)

        # Proximity check: find a window (fixed-size slice of the lowercased
        # text) that contains ALL FOUR required terms together — this is what
        # actually distinguishes "a single new passage ties these concepts
        # together" from "these four words happen to exist somewhere, in
        # unrelated sections, in this large file".
        WINDOW = 1200  # chars; generous enough for one paragraph/subsection
        required_terms = ["loop_gate", "schema", "plan_pass", "plan_fail"]

        def _window_has_all_terms(start):
            chunk = lower[start:start + WINDOW]
            return all(term in chunk for term in required_terms)

        found_proximate_window = any(
            _window_has_all_terms(i) for i in range(0, len(lower), 200)
        )
        self.assertTrue(
            found_proximate_window,
            "orchestrator.md must contain ONE localized passage where "
            "'loop_gate', 'schema', 'plan_pass', and 'plan_fail' all "
            "co-occur (within ~1200 chars of each other) — documenting the "
            "Workflow+schema dispatch's required loop_gate field in a single "
            "place, not scattered unrelated mentions across the file",
        )

        # Also require the passage to sit near the "parallel adversarial-lens
        # plan-check" section this AC's location is anchored to (per
        # Required-fix Problem 2 item 2: "around line 50-64").
        self.assertIn(
            "adversarial-lens",
            lower,
            "the parallel adversarial-lens plan-check section header must "
            "still exist for AC13's new subsection to be anchored near",
        )


# ---------------------------------------------------------------------------
# H-SUBAGENT-COMMIT-GATE-1 (runs/2026-07-03_h-subagent-commit-gate-1/specs/spec.md)
# subagent_stop_gate.py's 4th responsibility: scan THIS sub-agent's own
# transcript for a raw `git commit` scope violation and write a
# {session_id}_{agent_id}.commit_violation flag on a hit.
# ---------------------------------------------------------------------------


def scratch_git_repo_for_subagent_gate():
    """A real, freshly-git-init'd scratch repo with a configured identity and
    one seed commit — mirrors hooks/test_loop_stop_guard.py's own
    scratch_git_repo() helper (this file has no such helper pre-existing, so
    it is added here rather than imported cross-file, per this project's
    standing rule that test modules do not import each other)."""
    d = tempfile.mkdtemp(prefix="rc1-subagent-scratch-repo-")
    def _git(*args):
        return subprocess.run(["git", "-C", d] + list(args),
                              capture_output=True, text=True)
    _git("init", "-q")
    _git("config", "user.email", "rc1-subagent-test@example.com")
    _git("config", "user.name", "rc1-subagent-test")
    with open(os.path.join(d, "seed.txt"), "w", encoding="utf-8") as f:
        f.write("seed\n")
    _git("add", "seed.txt")
    _git("commit", "-qm", "seed commit")
    return d


def real_git_commit_for_subagent_gate(repo, *files_and_content, message="test commit"):
    """Write the given (relative_path, content) pairs into repo, `git add`
    them, and run a REAL `git commit` subprocess — returns (returncode,
    stdout, stderr) so the fixture is built from git's OWN literal output,
    never a hand-typed string, matching test_loop_stop_guard.py's own
    real_git_commit() convention (H-REVIEW-COMMIT-1's own AC14/AC15
    requirement, reused here since this build shares the same underlying
    scan function)."""
    for rel, content in files_and_content:
        full = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        subprocess.run(["git", "-C", repo, "add", rel], capture_output=True)
    r = subprocess.run(["git", "-C", repo, "commit", "-m", message],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def commit_bash_tool_use_event(tool_use_id, command):
    """A single assistant-message JSONL event holding one Bash tool_use
    (matching hooks/loop_stop_guard.py's _parts()-compatible shape) with an
    explicit id, so a following tool_result_for_commit() can correlate."""
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_use_id, "name": "Bash",
             "input": {"command": command}},
        ]},
    }


def tool_result_for_commit(tool_use_id, content_text):
    """A tool_result recorded as its own user-type entry, tied to a specific
    tool_use id — matches hooks/test_loop_stop_guard.py's
    tool_result_event() shape (message.content -> list containing one
    tool_result part)."""
    return {
        "type": "user",
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id,
             "content": content_text},
        ]},
    }


def commit_violation_flag_path(session_id, agent_id):
    return os.path.join(GATE_DIR, f"{session_id}_{agent_id}.commit_violation")


class FourthResponsibilityFlagWrite(unittest.TestCase):
    """AC2: a real raw `git commit` (real scratch-git-repo, real success
    line) touching a scope-listed file, inside a sub-agent's OWN transcript,
    writes a {session_id}_{agent_id}.commit_violation flag with JSON content
    naming the real SHA and touched file(s)."""

    def setUp(self):
        self._repos = []
        self._flags = []

    def tearDown(self):
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_scope_file_commit_writes_commit_violation_flag(self):
        repo = scratch_git_repo_for_subagent_gate()
        self._repos.append(repo)
        rc, out, err_txt = real_git_commit_for_subagent_gate(
            repo, ("loop-team/orchestrator.md", "orchestrator v1\n"),
            message="edit orchestrator")
        self.assertEqual(rc, 0, err_txt)

        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._flags.append(commit_violation_flag_path(sid, aid))
        transcript_events = [
            commit_bash_tool_use_event("rc1", 'git commit -m "edit orchestrator"'),
            tool_result_for_commit("rc1", out),
        ]
        tpath = write_transcript(
            tempfile.mkdtemp(),
            "\n".join(json.dumps(e) for e in transcript_events) + "\n",
        )
        payload = {"session_id": sid, "agent_id": aid,
                  "transcript_path": tpath, "cwd": repo}
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        flag_path = commit_violation_flag_path(sid, aid)
        self.assertTrue(os.path.exists(flag_path),
                        f"expected commit_violation flag not found: {flag_path}")
        with open(flag_path, encoding="utf-8") as f:
            content = json.load(f)
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 1)
        sha = out.split("]")[0].split()[-1]
        self.assertEqual(content[0]["sha"], sha)
        self.assertIn("loop-team/orchestrator.md", content[0]["touched"])


class FourthResponsibilityNoScopeViolation(unittest.TestCase):
    """AC3: identical scenario, but the sub-agent's commit touches ONLY
    files outside the scope list — no flag is written."""

    def setUp(self):
        self._repos = []
        self._flags = []

    def tearDown(self):
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_out_of_scope_commit_writes_no_flag(self):
        repo = scratch_git_repo_for_subagent_gate()
        self._repos.append(repo)
        rc, out, err_txt = real_git_commit_for_subagent_gate(
            repo, ("src/app.py", "print('hello')\n"), message="add app.py")
        self.assertEqual(rc, 0, err_txt)

        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._flags.append(commit_violation_flag_path(sid, aid))
        transcript_events = [
            commit_bash_tool_use_event("rc1", 'git commit -m "add app.py"'),
            tool_result_for_commit("rc1", out),
        ]
        tpath = write_transcript(
            tempfile.mkdtemp(),
            "\n".join(json.dumps(e) for e in transcript_events) + "\n",
        )
        payload = {"session_id": sid, "agent_id": aid,
                  "transcript_path": tpath, "cwd": repo}
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(commit_violation_flag_path(sid, aid)))


class FourthResponsibilityAgentTranscriptPathScoping(unittest.TestCase):
    """Regression for H-COMMIT-VIOLATION-FLAG-MISATTRIBUTION-1.

    Real Codex SubagentStop payloads carry parent `transcript_path` plus
    child `agent_transcript_path`. The commit gate must scan the child path
    when present, otherwise Oga's parent transcript can poison a read-only
    sub-agent with commits it never performed.
    """

    def setUp(self):
        self._repos = []
        self._flags = []
        self._tmpdirs = []

    def tearDown(self):
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def _tmpdir(self):
        d = tempfile.mkdtemp()
        self._tmpdirs.append(d)
        return d

    def _parent_transcript_with_scope_commit(self, repo):
        rc, out, err_txt = real_git_commit_for_subagent_gate(
            repo, ("loop-team/orchestrator.md", "parent commit\n"),
            message="parent commit")
        self.assertEqual(rc, 0, err_txt)
        events = [
            commit_bash_tool_use_event("parent-commit", 'git commit -m "parent commit"'),
            tool_result_for_commit("parent-commit", out),
        ]
        return write_transcript(
            self._tmpdir(),
            "\n".join(json.dumps(e) for e in events) + "\n",
        )

    def _child_transcript_without_bash(self):
        event = {
            "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "text", "text": "read-only verifier complete"},
            ]},
        }
        return write_transcript(self._tmpdir(), json.dumps(event) + "\n")

    def test_agent_transcript_path_prevents_parent_commit_poisoning(self):
        repo = scratch_git_repo_for_subagent_gate()
        self._repos.append(repo)
        parent_tpath = self._parent_transcript_with_scope_commit(repo)
        child_tpath = self._child_transcript_without_bash()

        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._flags.append(commit_violation_flag_path(sid, aid))
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": parent_tpath,
            "agent_transcript_path": child_tpath,
            "cwd": repo,
            "hook_event_name": "SubagentStop",
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        self.assertFalse(
            os.path.exists(commit_violation_flag_path(sid, aid)),
            "parent transcript commit must not create a flag for a clean child transcript",
        )

    def test_agent_transcript_path_still_flags_child_commit(self):
        repo = scratch_git_repo_for_subagent_gate()
        self._repos.append(repo)
        parent_tpath = self._child_transcript_without_bash()
        rc, out, err_txt = real_git_commit_for_subagent_gate(
            repo, ("RUN.md", "child commit\n"), message="child commit")
        self.assertEqual(rc, 0, err_txt)
        child_events = [
            commit_bash_tool_use_event("child-commit", 'git commit -m "child commit"'),
            tool_result_for_commit("child-commit", out),
        ]
        child_tpath = write_transcript(
            self._tmpdir(),
            "\n".join(json.dumps(e) for e in child_events) + "\n",
        )

        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._flags.append(commit_violation_flag_path(sid, aid))
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": parent_tpath,
            "agent_transcript_path": child_tpath,
            "cwd": repo,
            "hook_event_name": "SubagentStop",
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        flag_path = commit_violation_flag_path(sid, aid)
        self.assertTrue(os.path.exists(flag_path))
        with open(flag_path, encoding="utf-8") as f:
            content = json.load(f)
        self.assertEqual(len(content), 1)
        self.assertIn("RUN.md", content[0]["touched"])


class FourthResponsibilityFlagWriteGuard(unittest.TestCase):
    """AC7: an empty/missing session_id on the SubagentStop payload results
    in NO commit_violation flag being written, even when a real violation is
    detected — mirroring the existing _write_flag_if_guarded guard's exact
    semantics for .verifier_pass, not a new/looser rule."""

    def setUp(self):
        self._repos = []

    def tearDown(self):
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)

    def _fixture(self):
        repo = scratch_git_repo_for_subagent_gate()
        self._repos.append(repo)
        rc, out, err_txt = real_git_commit_for_subagent_gate(
            repo, ("RUN.md", "guarded content\n"), message="guarded commit")
        self.assertEqual(rc, 0, err_txt)
        transcript_events = [
            commit_bash_tool_use_event("rc1", 'git commit -m "guarded commit"'),
            tool_result_for_commit("rc1", out),
        ]
        tpath = write_transcript(
            tempfile.mkdtemp(),
            "\n".join(json.dumps(e) for e in transcript_events) + "\n",
        )
        return repo, tpath

    def test_missing_session_id_writes_no_flag(self):
        repo, tpath = self._fixture()
        payload = {"agent_id": "agentNoSession", "transcript_path": tpath, "cwd": repo}
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        pattern = os.path.join(GATE_DIR, "*_agentNoSession.commit_violation")
        self.assertEqual(glob.glob(pattern), [])

    def test_empty_session_id_writes_no_flag(self):
        repo, tpath = self._fixture()
        payload = {"session_id": "", "agent_id": "agentEmptySession",
                  "transcript_path": tpath, "cwd": repo}
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        pattern = os.path.join(GATE_DIR, "*_agentEmptySession.commit_violation")
        self.assertEqual(glob.glob(pattern), [])


class FourthResponsibilityFlagWriteGuardExtension(unittest.TestCase):
    """AC7b: after _write_flag_if_guarded's signature is extended with
    optional ext/content parameters, the EXISTING tier-1 and tier-3 call
    sites (unmodified, passing no extra arguments) still write an EMPTY
    .verifier_pass file exactly as before — byte-for-byte unchanged
    behavior, proving the signature extension is additive, not a
    regression."""

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

    # [BEHAVIORAL] AC7b: tier-1 (free-text PLAN_PASS) call site still writes
    # an EMPTY .verifier_pass file.
    def test_tier1_still_writes_empty_verifier_pass_file(self):
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
        self.assertTrue(os.path.exists(expected))
        with open(expected, encoding="utf-8") as f:
            self.assertEqual(f.read(), "", "tier-1 flag must still be EMPTY, byte-for-byte")

    # [BEHAVIORAL] AC7b: tier-3 (StructuredOutput fallback) call site still
    # writes an EMPTY .verifier_pass file.
    def test_tier3_still_writes_empty_verifier_pass_file(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tmpdir = tempfile.mkdtemp()
        tpath = write_jsonl_transcript(
            tmpdir, [structured_output_event("t7b", "PLAN_PASS")])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            # No last_assistant_message at all -> falls through to tier 3.
        }
        code, _ = run_gate(payload)
        self.assertEqual(code, 0)
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected))
        with open(expected, encoding="utf-8") as f:
            self.assertEqual(f.read(), "", "tier-3 flag must still be EMPTY, byte-for-byte")


class FourthResponsibilityExceptionSafety(unittest.TestCase):
    """AC12: any exception raised inside the new 4th responsibility (a
    malformed transcript, an unreadable path) results in the hook still
    exiting 0, with tiers 1-3's existing flag-write/debug-log/trace-log
    behavior completely unaffected."""

    def setUp(self):
        self._sessions_to_clean = []

    def tearDown(self):
        for sid in self._sessions_to_clean:
            for ext in ("verifier_pass", "commit_violation"):
                pattern = os.path.join(GATE_DIR, f"{sid}_*.{ext}")
                for f in glob.glob(pattern):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    # [BEHAVIORAL] AC12: a deliberately malformed transcript (garbage JSONL
    # content) must not crash the hook, and tier-1's OWN flag-write (driven
    # by last_assistant_message, independent of transcript_content) must
    # still succeed unaffected.
    def test_malformed_transcript_does_not_break_tier1_flag_write(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        tmpdir = tempfile.mkdtemp()
        tpath = write_jsonl_transcript(
            tmpdir, ["not json at all {{{", "{ also not valid json"])
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "last_assistant_message": "Some preamble\nLOOP_GATE: PLAN_PASS",
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        expected_verifier_pass = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected_verifier_pass),
                        "tier-1's flag-write must be unaffected by a malformed "
                        "transcript breaking the 4th responsibility's own scan")
        # No commit_violation flag should exist (nothing valid to detect).
        self.assertFalse(os.path.exists(commit_violation_flag_path(sid, aid)))

    # [BEHAVIORAL] AC12 companion: an unreadable transcript_path (points at a
    # directory, not a file) must not crash the hook either.
    def test_unreadable_transcript_path_does_not_crash(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        bogus_path = tempfile.mkdtemp()  # a directory, not a file
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": bogus_path,
            "last_assistant_message": "LOOP_GATE: PLAN_PASS",
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        expected_verifier_pass = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected_verifier_pass))
        self.assertFalse(os.path.exists(commit_violation_flag_path(sid, aid)))


class FourthResponsibilityCwdFallback(unittest.TestCase):
    """AC-CWD: a unit test proves the fallback-to-__file__-relative-path
    branch fires correctly when cwd is missing/empty/non-string on a
    SubagentStop payload, independent of whatever a real live firing's
    manual-testing result turns out to be."""

    def setUp(self):
        self._flags = []
        self._sessions_to_clean = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _run_with_cwd(self, cwd_value):
        """Runs the gate with a transcript containing a raw commit-shaped
        Bash tool_use but NO paired tool_result (so no SHA is ever
        extracted, and therefore no commit_violation flag can possibly be
        written regardless of which target directory resolution is used) --
        this isolates "did the hook crash / fail to run the scan at all"
        (which the cwd resolution branch could cause) from "did it detect a
        violation" (not the point of this test, which is about the fallback
        branch not crashing / still being reachable)."""
        sid = unique_session()
        self._sessions_to_clean.append(sid)
        aid = f"agent-{uuid.uuid4()}"
        tmpdir = tempfile.mkdtemp()
        transcript_events = [commit_bash_tool_use_event("rcX", "git commit -m \"x\"")]
        tpath = write_transcript(
            tmpdir, "\n".join(json.dumps(e) for e in transcript_events) + "\n")
        payload = {"session_id": sid, "agent_id": aid, "transcript_path": tpath,
                  "last_assistant_message": "LOOP_GATE: PLAN_PASS"}
        if cwd_value is not _SENTINEL:
            payload["cwd"] = cwd_value
        code, err = run_gate(payload)
        return code, err, sid, aid

    def test_missing_cwd_key_falls_back_without_crashing(self):
        code, err, sid, aid = self._run_with_cwd(_SENTINEL)
        self.assertEqual(code, 0, err)
        # tier-1's own flag-write (independent of the 4th responsibility)
        # must still succeed, proving the hook did not crash before reaching
        # the debug-log write.
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected))

    def test_empty_string_cwd_falls_back_without_crashing(self):
        code, err, sid, aid = self._run_with_cwd("")
        self.assertEqual(code, 0, err)
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected))

    def test_non_string_cwd_falls_back_without_crashing(self):
        code, err, sid, aid = self._run_with_cwd(12345)
        self.assertEqual(code, 0, err)
        expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(os.path.exists(expected))

    # [BEHAVIORAL] AC-CWD companion: subagent_gate_debug.jsonl's own `cwd`
    # field reflects None when the payload's cwd is missing/non-string --
    # proves the debug-log addition (item 2's "Required first step") is
    # actually wired, not just present as an unused variable.
    def test_debug_log_cwd_field_is_none_when_missing(self):
        debug_log_path = os.path.join(GATE_DIR, "subagent_gate_debug.jsonl")
        before_count = 0
        if os.path.exists(debug_log_path):
            with open(debug_log_path, encoding="utf-8") as f:
                before_count = len(f.readlines())
        code, err, sid, aid = self._run_with_cwd(_SENTINEL)
        self.assertEqual(code, 0, err)
        matches = read_debug_lines_for_session(debug_log_path, before_count, sid)
        self.assertEqual(len(matches), 1)
        self.assertIsNone(matches[0].get("cwd"))

    def test_debug_log_cwd_field_reflects_real_string_value(self):
        debug_log_path = os.path.join(GATE_DIR, "subagent_gate_debug.jsonl")
        before_count = 0
        if os.path.exists(debug_log_path):
            with open(debug_log_path, encoding="utf-8") as f:
                before_count = len(f.readlines())
        code, err, sid, aid = self._run_with_cwd("/tmp/some/real/cwd")
        self.assertEqual(code, 0, err)
        matches = read_debug_lines_for_session(debug_log_path, before_count, sid)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].get("cwd"), "/tmp/some/real/cwd")


_SENTINEL = object()


# ---------------------------------------------------------------------------
# H-SUBAGENT-COMMIT-GATE-1 (runs/2026-07-03_h-subagent-commit-gate-1/specs/spec.md)
# AC2, AC3, AC7, AC7b, AC12, AC-CWD (subagent_stop_gate.py 4th-responsibility
# side).
#
# Written independently from the spec's own ACs, never having read
# hooks/subagent_stop_gate.py's or hooks/commit_scope_scan.py's actual
# (uncommitted) implementation diffs -- only their git-committed HEAD state
# (which the spec explicitly describes as "current, unmodified") plus the
# spec text and research/subagent-commit-violation-signaling-2026-07-03.md.
#
# Naming: every new class below carries the "IndependentTW1" suffix to
# guarantee zero collision with any class already present in this file
# (including any pending/uncommitted FourthResponsibility* classes from the
# same build -- this test-writer pass does not read or modify those; they
# are left completely untouched, per "never weaken or remove any existing
# test").
# ---------------------------------------------------------------------------
import subprocess as _tw1_subprocess


def _tw1_scratch_git_repo():
    """A real, freshly-git-init'd scratch repo with a configured identity
    and one seed commit -- mirrors test_loop_stop_guard.py's own
    scratch_git_repo() helper (H-REVIEW-COMMIT-1 precedent), rebuilt here
    independently since this file has never needed real git fixtures before
    this build. Caller is responsible for cleanup (shutil.rmtree)."""
    d = tempfile.mkdtemp(prefix="tw1-sub-scratch-repo-")

    def _git(*args):
        return _tw1_subprocess.run(
            ["git", "-C", d] + list(args), capture_output=True, text=True)

    _git("init", "-q")
    _git("config", "user.email", "tw1-sub-test@example.com")
    _git("config", "user.name", "tw1-sub-test")
    with open(os.path.join(d, "seed.txt"), "w", encoding="utf-8") as f:
        f.write("seed\n")
    _git("add", "seed.txt")
    _git("commit", "-qm", "seed commit")
    return d


def _tw1_real_git_commit(repo, *files_and_content, message="test commit"):
    """Write the given (relative_path, content) pairs into repo, `git add`
    them, and run a REAL `git commit` subprocess -- returns (returncode,
    stdout, stderr), mirroring test_loop_stop_guard.py's own
    real_git_commit() helper, so the tool_result fixture below is built from
    git's OWN literal output, never a hand-typed fixture string."""
    for rel, content in files_and_content:
        full = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        _tw1_subprocess.run(["git", "-C", repo, "add", rel], capture_output=True)
    r = _tw1_subprocess.run(["git", "-C", repo, "commit", "-m", message],
                            capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _tw1_subagent_transcript_with_commit(tmpdir, bash_tool_use_id, command,
                                          result_text, role_header="# Role: Coder"):
    """A flat (not turn-sliced) sub-agent transcript containing a Bash
    tool_use (the raw `git commit` invocation) paired with its own
    tool_result -- per spec item 2's "the SAME structural way" instruction
    (flat, not turn-sliced, since a sub-agent's whole transcript IS the
    relevant unit)."""
    events = [
        {"type": "user", "message": {"role": "user", "content": "go build"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": role_header},
            {"type": "tool_use", "id": bash_tool_use_id, "name": "Bash",
             "input": {"command": command}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": bash_tool_use_id,
             "content": result_text},
        ]}},
    ]
    path = os.path.join(tmpdir, f"subagent-transcript-{uuid.uuid4()}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return path


def _tw1_commit_violation_flag_path(session_id, agent_id):
    return os.path.join(GATE_DIR, f"{session_id}_{agent_id}.commit_violation")


def _tw1_cleanup_commit_violation(session_id):
    pattern = os.path.join(GATE_DIR, f"{session_id}_*.commit_violation")
    for f in glob.glob(pattern):
        try:
            os.remove(f)
        except OSError:
            pass


def _tw1_cleanup_verifier_pass(session_id):
    pattern = os.path.join(GATE_DIR, f"{session_id}_*.verifier_pass")
    for f in glob.glob(pattern):
        try:
            os.remove(f)
        except OSError:
            pass


class FourthResponsibilityWritesCommitViolationFlagIndependentTW1(unittest.TestCase):
    """AC2 [BEHAVIORAL]: a SubagentStop payload whose sub-agent's own
    transcript contains a raw `git commit` (real success-line, real
    scratch-git-repo construction -- no hand-typed fixture strings, matching
    H-REVIEW-COMMIT-1's own testing convention) touching a scope-listed file
    writes a {session_id}_{agent_id}.commit_violation flag under
    $LOOP_GATE_DIR, with JSON content naming the real SHA and touched
    file(s)."""

    def setUp(self):
        self.repo = _tw1_scratch_git_repo()
        self.tmpdir = tempfile.mkdtemp(prefix="tw1-sub-transcripts-")
        self.sid = unique_session()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        _tw1_cleanup_commit_violation(self.sid)
        _tw1_cleanup_verifier_pass(self.sid)

    def test_scope_violating_commit_writes_flag_with_sha_and_touched_files(self):
        aid = f"agent-{uuid.uuid4()}"
        rc, out, err_txt = _tw1_real_git_commit(
            self.repo, ("RUN.md", "scope content\n"), message="scope commit")
        self.assertEqual(rc, 0, err_txt)
        tpath = _tw1_subagent_transcript_with_commit(
            self.tmpdir, "bt1", 'git commit -m "scope commit"', out)
        payload = {
            "session_id": self.sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "cwd": self.repo,
            "last_assistant_message": "Committed the change.",
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        flag = _tw1_commit_violation_flag_path(self.sid, aid)
        self.assertTrue(os.path.exists(flag), f"expected flag not found: {flag}")
        with open(flag, encoding="utf-8") as f:
            content = json.load(f)
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 1, content)
        entry = content[0]
        expected_sha = out.split("]")[0].split()[-1]
        self.assertEqual(entry.get("sha"), expected_sha)
        self.assertIn("RUN.md", entry.get("touched", []))


class FourthResponsibilityNoFlagForOutOfScopeCommitIndependentTW1(unittest.TestCase):
    """AC3 [BEHAVIORAL]: the identical scenario as AC2, but the sub-agent's
    commit touches ONLY files outside the scope list -- no flag is
    written."""

    def setUp(self):
        self.repo = _tw1_scratch_git_repo()
        self.tmpdir = tempfile.mkdtemp(prefix="tw1-sub-transcripts-")
        self.sid = unique_session()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        _tw1_cleanup_commit_violation(self.sid)
        _tw1_cleanup_verifier_pass(self.sid)

    def test_out_of_scope_commit_writes_no_flag(self):
        aid = f"agent-{uuid.uuid4()}"
        rc, out, err_txt = _tw1_real_git_commit(
            self.repo, ("src/unrelated.py", "print('hi')\n"),
            message="unrelated commit")
        self.assertEqual(rc, 0, err_txt)
        tpath = _tw1_subagent_transcript_with_commit(
            self.tmpdir, "bt2", 'git commit -m "unrelated commit"', out)
        payload = {
            "session_id": self.sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "cwd": self.repo,
            "last_assistant_message": "Committed the change.",
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        pattern = os.path.join(GATE_DIR, f"{self.sid}_*.commit_violation")
        self.assertEqual(glob.glob(pattern), [])


class FourthResponsibilitySessionIdGuardIndependentTW1(unittest.TestCase):
    """AC7 [BEHAVIORAL]: the flag-write in AC2 uses the SAME
    _write_flag_if_guarded-style guard: an empty/missing session_id on the
    SubagentStop payload results in NO flag being written (even if a real
    violation is detected) -- mirroring the existing guard's exact
    semantics, not a new, looser rule."""

    def setUp(self):
        self.repo = _tw1_scratch_git_repo()
        self.tmpdir = tempfile.mkdtemp(prefix="tw1-sub-transcripts-")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_with_session_id(self, session_id_value):
        aid = f"agent-{uuid.uuid4()}"
        rc, out, err_txt = _tw1_real_git_commit(
            self.repo, ("fix_plan.md", "scope content\n"),
            message="scope commit for session guard test")
        self.assertEqual(rc, 0, err_txt)
        tpath = _tw1_subagent_transcript_with_commit(
            self.tmpdir, "bt3", 'git commit -m "scope commit for session guard test"', out)
        payload = {
            "agent_id": aid,
            "transcript_path": tpath,
            "cwd": self.repo,
            "last_assistant_message": "Committed the change.",
        }
        if session_id_value is not _SENTINEL:
            payload["session_id"] = session_id_value
        code, err = run_gate(payload)
        return code, err, aid

    def test_empty_session_id_writes_no_flag_despite_real_violation(self):
        code, err, aid = self._run_with_session_id("")
        self.assertEqual(code, 0, err)
        # Cannot enumerate an empty-session flag pattern safely (a bare
        # "_<aid>.commit_violation" would be a valid glob), so assert the
        # specific malformed-filename shape never appears, mirroring this
        # file's OWN established empty-session-id check-style precedent
        # (test_empty_session_id_no_flag for .verifier_pass).
        pattern = os.path.join(GATE_DIR, f"_{aid}.commit_violation")
        self.assertFalse(os.path.exists(pattern))

    def test_missing_session_id_key_writes_no_flag_despite_real_violation(self):
        code, err, aid = self._run_with_session_id(_SENTINEL)
        self.assertEqual(code, 0, err)
        pattern = os.path.join(GATE_DIR, f"_{aid}.commit_violation")
        self.assertFalse(os.path.exists(pattern))

    def test_whitespace_only_session_id_writes_no_flag_despite_real_violation(self):
        code, err, aid = self._run_with_session_id("   ")
        self.assertEqual(code, 0, err)
        # Whitespace session_id: glob for any commit_violation flag at all
        # under this exact whitespace-prefixed name -- none should exist.
        pattern = os.path.join(GATE_DIR, f"   _{aid}.commit_violation")
        self.assertFalse(os.path.exists(pattern))

    def test_valid_session_id_control_case_does_write_flag(self):
        # Regression control isolating that the guard above is genuinely
        # session_id-driven: an otherwise-identical real violation WITH a
        # valid, non-empty session_id must still write the flag normally.
        sid = unique_session()
        try:
            code, err, aid = self._run_with_session_id(sid)
            self.assertEqual(code, 0, err)
            flag = _tw1_commit_violation_flag_path(sid, aid)
            self.assertTrue(os.path.exists(flag), flag)
        finally:
            _tw1_cleanup_commit_violation(sid)


class WriteFlagIfGuardedSignatureExtensionIndependentTW1(unittest.TestCase):
    """AC7b [BEHAVIORAL]: after _write_flag_if_guarded's signature is
    extended with optional ext/content parameters, the EXISTING tier-1 and
    tier-3 call sites (unmodified, passing no extra arguments) still write
    an EMPTY .verifier_pass file exactly as before -- byte-for-byte
    unchanged behavior, proving the signature extension is additive, not a
    regression to the pre-existing plan-check-credit mechanism."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="tw1-ac7b-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_tier1_plan_pass_still_writes_empty_verifier_pass_file(self):
        # Tier 1: explicit free-text "LOOP_GATE: PLAN_PASS" last line.
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "last_assistant_message": "Reviewed, no gaps.\nLOOP_GATE: PLAN_PASS",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
            self.assertTrue(os.path.exists(expected))
            # Byte-for-byte unchanged: the pre-existing tier-1 call site
            # passes NO extra ext/content arguments, so the written file
            # must still be exactly empty (0 bytes), not carrying any
            # commit_violation-style JSON content.
            self.assertEqual(os.path.getsize(expected), 0,
                             "tier-1 .verifier_pass file must remain byte-for-byte "
                             "empty after the _write_flag_if_guarded signature "
                             "extension")
        finally:
            _tw1_cleanup_verifier_pass(sid)

    def test_tier3_structured_output_plan_pass_still_writes_empty_verifier_pass_file(self):
        # Tier 3: StructuredOutput fallback path (no free-text conclusion).
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            events = [
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "Plan-check verdict."},
                    {"type": "tool_use", "id": f"toolu_{uuid.uuid4()}",
                     "name": "StructuredOutput",
                     "input": {"loop_gate": "PLAN_PASS"}},
                ]}},
            ]
            path = os.path.join(self.tmpdir, f"transcript-{uuid.uuid4()}.txt")
            with open(path, "w", encoding="utf-8") as f:
                for e in events:
                    f.write(json.dumps(e) + "\n")
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": path,
                "last_assistant_message": None,
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
            self.assertTrue(os.path.exists(expected))
            self.assertEqual(os.path.getsize(expected), 0,
                             "tier-3 .verifier_pass file must remain byte-for-byte "
                             "empty after the _write_flag_if_guarded signature "
                             "extension")
        finally:
            _tw1_cleanup_verifier_pass(sid)

    def test_missing_agent_id_still_uses_unknown_after_signature_extension(self):
        # Regression companion: the pre-existing "unknown" agent_id fallback
        # (unrelated to ext/content) must still work unchanged too.
        sid = unique_session()
        try:
            payload = {
                "session_id": sid,
                "last_assistant_message": "All good.\nLOOP_GATE: PLAN_PASS",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            expected = os.path.join(GATE_DIR, f"{sid}_unknown.verifier_pass")
            self.assertTrue(os.path.exists(expected))
            self.assertEqual(os.path.getsize(expected), 0)
        finally:
            _tw1_cleanup_verifier_pass(sid)


class FourthResponsibilityExceptionIsolationIndependentTW1(unittest.TestCase):
    """AC12 [BEHAVIORAL]: any exception raised inside the new 4th
    responsibility (a malformed transcript, an unreadable path) results in
    the hook still exiting 0, with tiers 1-3's existing flag-write/debug-log/
    trace-log behavior completely unaffected -- constructed by pointing the
    scan at a deliberately malformed transcript fixture, WHILE tier 1's
    own PLAN_PASS free-text completion is present in the SAME payload, so a
    genuine cross-responsibility isolation failure would be directly
    observable (tier 1's flag would simply not appear)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="tw1-ac12-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_directory_as_transcript_path_does_not_break_tier1_flag_write(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": self.tmpdir,  # a directory, not a file
                "cwd": self.tmpdir,
                "last_assistant_message": "Reviewed.\nLOOP_GATE: PLAN_PASS",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
            self.assertTrue(
                os.path.exists(expected),
                "tier-1 .verifier_pass write must survive a directory-shaped "
                "transcript_path breaking the 4th responsibility's own scan",
            )
            # No commit_violation flag should exist either (the malformed
            # transcript could not have been scanned for a violation).
            pattern = os.path.join(GATE_DIR, f"{sid}_*.commit_violation")
            self.assertEqual(glob.glob(pattern), [])
        finally:
            _tw1_cleanup_verifier_pass(sid)
            _tw1_cleanup_commit_violation(sid)

    def test_malformed_jsonl_transcript_does_not_break_tier1_flag_write(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            path = os.path.join(self.tmpdir, f"malformed-{uuid.uuid4()}.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("this is not valid JSON at all {{{\n")
                f.write("neither is this [[[\n")
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": path,
                "cwd": "/nonexistent/hostile/cwd/path",
                "last_assistant_message": "Reviewed.\nLOOP_GATE: PLAN_PASS",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
            self.assertTrue(
                os.path.exists(expected),
                "tier-1 .verifier_pass write must survive a malformed JSONL "
                "transcript and a nonexistent cwd breaking the 4th "
                "responsibility's own scan",
            )
        finally:
            _tw1_cleanup_verifier_pass(sid)
            _tw1_cleanup_commit_violation(sid)

    def test_unreadable_cwd_repo_does_not_crash_or_affect_exit_code(self):
        # cwd points at a path that is not a git repo at all (git show will
        # fail with a nonzero returncode, not raise) -- must still exit 0
        # and never surface a Python traceback on stderr.
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        not_a_repo = tempfile.mkdtemp(prefix="tw1-ac12-notarepo-")
        try:
            tpath = _tw1_subagent_transcript_with_commit(
                self.tmpdir, "bt-notarepo", 'git commit -m "msg"',
                "[main 1234567] msg\n 1 file changed\n")
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": tpath,
                "cwd": not_a_repo,
                "last_assistant_message": "Done.",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
        finally:
            shutil.rmtree(not_a_repo, ignore_errors=True)
            _tw1_cleanup_verifier_pass(sid)
            _tw1_cleanup_commit_violation(sid)


class CwdFallbackTargetResolutionIndependentTW1(unittest.TestCase):
    """AC-CWD [BEHAVIORAL]: a unit test proves the
    fallback-to-__file__-relative-path branch fires correctly when cwd is
    missing/empty/non-string on a SubagentStop payload, independent of
    whatever a real live firing's manual-testing result turns out to be.

    Mechanism: with a VALID cwd pointing at a scratch repo containing the
    violating SHA, the flag must be written (positive control, proving the
    scratch repo IS resolvable when cwd is honored). With cwd
    missing/empty/non-string, the SAME sha (which exists ONLY in that
    scratch repo, not in the real hooks-file-relative repo) must NOT
    resolve a violation -- proving the hook genuinely fell back away from
    the scratch repo (to this file's own __file__-relative repo path)
    rather than "coincidentally still finding" the scratch repo's SHA some
    other way. This isolates genuine fallback-branch execution from a
    vacuous pass that would occur if cwd were silently ignored entirely
    (i.e. always using SOME repo) without ever actually failing open to the
    real target when cwd is honored."""

    def setUp(self):
        self.repo = _tw1_scratch_git_repo()
        self.tmpdir = tempfile.mkdtemp(prefix="tw1-accwd-")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _commit_and_transcript(self):
        rc, out, err_txt = _tw1_real_git_commit(
            self.repo, ("search_playbook.md", "scope content\n"),
            message="ac-cwd scope commit")
        self.assertEqual(rc, 0, err_txt)
        tpath = _tw1_subagent_transcript_with_commit(
            self.tmpdir, "btcwd", 'git commit -m "ac-cwd scope commit"', out)
        return tpath

    def test_valid_cwd_resolves_scratch_repo_and_writes_flag(self):
        # Positive control: cwd IS honored when valid.
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            tpath = self._commit_and_transcript()
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": tpath,
                "cwd": self.repo,
                "last_assistant_message": "Done.",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            flag = _tw1_commit_violation_flag_path(sid, aid)
            self.assertTrue(
                os.path.exists(flag),
                "positive control: a VALID cwd pointing at the scratch repo "
                "must resolve the violation and write the flag",
            )
        finally:
            _tw1_cleanup_commit_violation(sid)

    def test_missing_cwd_falls_back_and_does_not_resolve_scratch_repo_sha(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            tpath = self._commit_and_transcript()
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": tpath,
                # No "cwd" key at all.
                "last_assistant_message": "Done.",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            flag = _tw1_commit_violation_flag_path(sid, aid)
            self.assertFalse(
                os.path.exists(flag),
                "with cwd missing entirely, the hook must fall back to its "
                "own __file__-relative repo path, NOT resolve the scratch "
                "repo's SHA -- a flag here would mean cwd was silently "
                "ignored rather than genuinely falling back",
            )
        finally:
            _tw1_cleanup_commit_violation(sid)

    def test_empty_string_cwd_falls_back_and_does_not_resolve_scratch_repo_sha(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            tpath = self._commit_and_transcript()
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": tpath,
                "cwd": "",
                "last_assistant_message": "Done.",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            flag = _tw1_commit_violation_flag_path(sid, aid)
            self.assertFalse(os.path.exists(flag))
        finally:
            _tw1_cleanup_commit_violation(sid)

    def test_non_string_cwd_falls_back_and_does_not_resolve_scratch_repo_sha(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            tpath = self._commit_and_transcript()
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": tpath,
                "cwd": 12345,
                "last_assistant_message": "Done.",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            flag = _tw1_commit_violation_flag_path(sid, aid)
            self.assertFalse(os.path.exists(flag))
        finally:
            _tw1_cleanup_commit_violation(sid)

    def test_fallback_does_not_crash_and_tier1_still_works_alongside_it(self):
        # Companion: cwd missing + a genuine tier-1 PLAN_PASS completion in
        # the SAME payload -- the 4th responsibility's fallback path must
        # coexist cleanly with tier 1, neither breaking the other.
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        try:
            tpath = self._commit_and_transcript()
            payload = {
                "session_id": sid,
                "agent_id": aid,
                "transcript_path": tpath,
                "last_assistant_message": "Reviewed.\nLOOP_GATE: PLAN_PASS",
            }
            code, err = run_gate(payload)
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
            expected = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
            self.assertTrue(os.path.exists(expected))
        finally:
            _tw1_cleanup_verifier_pass(sid)
            _tw1_cleanup_commit_violation(sid)

# ROUND 5 (2026-07-08): a "Fifth responsibility" (SubagentStop-based
# .subagent_behavior flag write, via hooks/feature_write_scan.py's
# find_feature_writes()) and its test coverage
# (FifthResponsibilityFeatureWriteFlag,
# FifthResponsibilityUnreadableTranscriptWritesNoFlag,
# FifthResponsibilityCodexShapedTranscriptWritesNoFlag,
# FifthResponsibilitySpawnedNestedAgentField,
# FifthResponsibilityRealisticParentSiblingTranscriptLayout,
# FifthResponsibilityAgentTranscriptPathNativeFieldPreferred, plus the
# subagent_behavior_flag_path()/edit_tool_use_event()/read_tool_use_event()
# fixtures they used) were built, then REVERTED here after independent
# adversarial verification found two real, reproduced bypasses (a
# Bash-forged flag-file spoof, and an async-transcript-lag false-clean
# timing race). See fix_plan.md's "ROUND 5 OUTCOME" sub-section under
# H-STOPGUARD-SUBAGENTTYPE-ADJACENCY-SELFMATCH-1 for the full writeup.


# =============================================================================
# Evidence-Gate Phase 4 (round 2) follow-up dispatch, 2026-07-09 (spec:
# loop-team/runs/2026-07-09_evidence-gate-phase4/specs/spec.md) --
# Test-writer self-reported coverage gap: AC14/15/16/17 all construct the
# .closure_violation flag DIRECTLY via a test helper
# (write_closure_violation_flag()-equivalent in hooks/test_loop_stop_guard.py),
# bypassing subagent_stop_gate.py's own new Fifth responsibility (Part B,
# spec.md "Part B -- sub-agent-authored closure detection") detection/write
# logic entirely. Part B is the exact mechanism meant to close the
# sub-agent-authored-closure blind spot (round-1's theme 3) -- if IT is
# broken, nothing currently catches it. This class drives a REAL
# SubagentStop invocation of subagent_stop_gate.py end-to-end so Part B's
# OWN closure_touch_scan.find_touched_closed_headings +
# fixplan_closure_lint.check_single_heading detection logic is what decides
# whether the flag gets written -- not a stand-in.
#
# NOTE on the "Fifth responsibility" name collision: a DIFFERENT, unrelated
# "Fifth responsibility" (a .subagent_behavior flag via
# hooks/feature_write_scan.py) was built and then REVERTED earlier in this
# repo's history (see the ROUND 5 comment immediately above this section) --
# that responsibility does not exist in the live subagent_stop_gate.py
# today. THIS class targets spec.md's OWN, currently-undelivered Fifth
# responsibility (the .closure_violation flag write, Evidence-Gate Phase 4),
# a completely different mechanism that happens to share an ordinal name.
# None of this class's new helper names collide with the reverted round-5
# names (confirmed by grep before writing this).
#
# Part B's target_fix_plan_path is resolved __file__-relative from
# hooks/subagent_stop_gate.py's OWN location (spec.md's theme-1 fix, the
# SAME rule stated for loop_stop_guard.py's Part C: "fix_plan.md's location
# is not a per-micro-step-target question -- it is always THIS repo's own
# single, fixed tracking file"), so invoking the REAL, live
# subagent_stop_gate.py (GATE, module-level above) in place would always
# resolve to THIS repo's OWN live fix_plan.md -- mutating that shared,
# actively-read-by-other-sessions file, even temporarily, is unacceptable
# (this project's "one session per worktree" / shared-worktree
# false-positive lesson, and matches hooks/test_loop_stop_guard.py's own
# stated rationale for its Part C/D/E scratch-repo tests). Every test below
# instead runs against an ISOLATED, throwaway COPY of hooks/ (+
# loop-team/harness/, which closure_touch_scan.py's own cross-directory
# import needs) rooted at a fresh tempfile.mkdtemp() -- built independently
# here (NOT imported from hooks/test_loop_stop_guard.py), per this project's
# "test modules do not import each other" standing rule (see this file's own
# scratch_git_repo_for_subagent_gate() docstring above, and
# hooks/test_closure_touch_scan.py's own module docstring, both already
# stating the same rule).
#
# EXPECTED TO FAIL pre-implementation: subagent_stop_gate.py has no Fifth
# responsibility yet (confirmed by direct read of the live file -- it stops
# at the Fourth responsibility + trace-logging), so the positive case below
# must currently find no .closure_violation flag at all -- a FAILED
# assertion for the right reason (nothing writes the flag yet), not a bug
# in this test.
# =============================================================================

_PHASE4_REPO_HARNESS_DIR = os.path.join(REPO_ROOT, "loop-team", "harness")
_PHASE4_RUN_AND_RECORD = os.path.join(_PHASE4_REPO_HARNESS_DIR, "run_and_record.py")


def _make_scratch_subagent_gate_repo():
    """Build an isolated <scratch>/hooks/ + <scratch>/loop-team/harness/ tree
    mirroring this repo's real layout closely enough for every
    __file__-relative resolution inside the COPIED subagent_stop_gate.py
    (Part B's own target_fix_plan_path resolution, and closure_touch_scan.py's
    own cross-directory import of loop-team/harness/fixplan_closure_lint.py)
    to work identically to production, rooted at a throwaway
    <scratch>/fix_plan.md this helper's caller controls completely. Returns
    (scratch_root, scratch_gate_path, scratch_fixplan_path) -- the
    fix_plan.md file itself is NOT created here (callers write whatever
    fixture content they need). Caller must
    shutil.rmtree(scratch_root, ignore_errors=True) in its own tearDown."""
    scratch_root = tempfile.mkdtemp(prefix="phase4-subagent-scratch-repo-")
    scratch_hooks = os.path.join(scratch_root, "hooks")
    shutil.copytree(
        HOOKS_DIR, scratch_hooks,
        ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"),
    )
    if os.path.isdir(_PHASE4_REPO_HARNESS_DIR):
        shutil.copytree(
            _PHASE4_REPO_HARNESS_DIR,
            os.path.join(scratch_root, "loop-team", "harness"),
            ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"),
        )
    scratch_gate = os.path.join(scratch_hooks, "subagent_stop_gate.py")
    scratch_fixplan = os.path.join(scratch_root, "fix_plan.md")
    return scratch_root, scratch_gate, scratch_fixplan


def _phase4_make_real_proof_block(gate_dir, command_argv):
    """Invoke the REAL run_and_record.py CLI (mirrors
    hooks/test_loop_stop_guard.py's own _make_real_proof_block() /
    loop-team/harness/test_fixplan_closure_lint.py's own
    _make_real_snapshot() helper) to produce a genuine, byte-for-byte-real
    "Proof:\\n- field: value" block for the negative-case fixture below,
    which needs an ACTUALLY-valid (non-fabricated) Proof block, per this
    dispatch's own instruction ("built via a real run_and_record.py --
    true call"). Returns the raw block text, newline-terminated."""
    env = dict(os.environ, LOOP_GATE_DIR=str(gate_dir))
    p = subprocess.run(
        [sys.executable, _PHASE4_RUN_AND_RECORD, "--"] + list(command_argv),
        capture_output=True, text=True, timeout=30, env=env,
    )
    stdout = p.stdout.lstrip()
    _record, end = json.JSONDecoder().raw_decode(stdout)
    return stdout[end:].strip() + "\n"


# [Section E] status_claim_audit.py's PROBE_COMMAND_RE deliberately classifies
# a bare ["true"]-wrapped proof command as PROBE_ONLY (anti-gaming: "wrap
# `true` in run_and_record.py to fake a real proof"). Fixtures that need a
# genuinely-valid (non-PROBE_ONLY) Proof block use this real, substantive,
# fast, deterministic command instead -- an actual pytest run of a small,
# stable, always-green hook test file -- rather than defaulting back to
# ["true"] or inventing an equally-trivial regex-dodging substitute. Mirrors
# hooks/test_loop_stop_guard.py's own _REAL_PROOF_COMMAND constant.
_REAL_PROOF_COMMAND = [sys.executable, "-m", "pytest",
                       os.path.join(HOOKS_DIR, "test_loop_logger.py"), "-q"]


def _phase4_edit_tool_use_event(tool_use_id, file_path, old_string, new_string):
    """One real Claude-Code-transcript-shaped JSONL event dict representing
    a sub-agent's OWN assistant turn whose content includes an Edit
    tool_use block -- the SAME structural shape subagent_stop_gate.py's
    existing Fourth responsibility already parses via its
    _cv_content_of()/_cv_parts() helpers (message.content -> list of parts,
    type == 'tool_use'), and the SAME public tool_use dict shape
    hooks/test_closure_touch_scan.py's own tool_use() helper documents as
    closure_touch_scan.find_touched_closed_headings' literal public
    contract (`{"type": "tool_use", "name": ..., "input": {...}}`)."""
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_use_id, "name": "Edit",
             "input": {"file_path": file_path, "old_string": old_string,
                       "new_string": new_string}},
        ]},
    }


def _run_scratch_subagent_gate(gate_path, payload_dict, gate_dir):
    """Like run_gate() (module-level, top of this file) but targets an
    explicit scratch gate_path (an isolated copy from
    _make_scratch_subagent_gate_repo()) and an explicit, overridable
    LOOP_GATE_DIR -- mirrors hooks/test_loop_stop_guard.py's own
    _run_guard_at() convention for ITS OWN Part C/D/E scratch-repo tests
    (independently reproduced here rather than imported cross-file, per
    this project's "test modules do not import each other" rule)."""
    payload = json.dumps(payload_dict)
    env = dict(os.environ, LOOP_GATE_DIR=gate_dir)
    p = subprocess.run(
        [sys.executable, gate_path],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )
    return p.returncode, p.stderr


def _phase4_closure_violation_flag_path(gate_dir, session_id, agent_id):
    return os.path.join(gate_dir, f"{session_id}_{agent_id}.closure_violation")


class Phase4PartBRealSubagentStopClosureViolationFlagWrite(unittest.TestCase):
    """Evidence-Gate Phase 4 follow-up: a REAL SubagentStop invocation of
    subagent_stop_gate.py must exercise Part B's OWN detection logic
    (closure_touch_scan.find_touched_closed_headings +
    fixplan_closure_lint.check_single_heading), proving the actual write
    path works end-to-end -- not a test helper standing in for it (the gap
    AC14/15/16/17 left, per this dispatch's own framing)."""

    def setUp(self):
        (self._scratch_root, self._scratch_gate,
         self._scratch_fixplan) = _make_scratch_subagent_gate_repo()
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-partb-gate-")

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def _flag_path(self, sid, aid):
        return _phase4_closure_violation_flag_path(self._gate_dir, sid, aid)

    # [BEHAVIORAL] Part B, positive case: a sub-agent transcript whose own
    # Edit tool_use introduces a CLOSED heading with NO Proof block at all
    # (an invalid closure -- the archetypal "sub-agent authored a false
    # closure" scenario this Fifth responsibility exists to catch) -> a
    # REAL .closure_violation flag is written under $LOOP_GATE_DIR, named
    # by session_id/agent_id, with the documented
    # [{"heading":..., "messages":[...], "warnings":[...]}] JSON shape,
    # naming the touched, invalid heading in "messages" (a missing Proof
    # block is a v1/v2 check, unconditionally blocking per theme 4,
    # regardless of the advisory flag Part B passes internally).
    def test_missing_proof_closed_heading_in_subagent_transcript_writes_flag(self):
        heading_line = "H-PARTB-MISSING -- CLOSED (2026-07-09, introduced by sub-agent)"
        original = "## H-PARTB-PRE (OPEN, still open)\nNothing closed yet.\n"
        new_block = (
            "## %s\n"
            "Some closure prose, but no Proof block at all -- a fabricated "
            "closure this Fifth responsibility must catch.\n" % heading_line
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original)
        # The hook fires AFTER the tool already ran -- simulate the edit
        # having already landed on disk before Part B's own fresh re-read
        # (Part A's docstring step 1: "Read target_fix_plan_path FRESH...
        # disk state is authoritative at hook-invocation time").
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original + new_block)

        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        transcript_events = [
            _phase4_edit_tool_use_event("tu1", self._scratch_fixplan, "x", new_block),
        ]
        tpath = write_transcript(
            tempfile.mkdtemp(),
            "\n".join(json.dumps(e) for e in transcript_events) + "\n",
        )
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "cwd": os.path.dirname(self._scratch_fixplan),
            "last_assistant_message": "Closed the heading.",
        }
        code, err = _run_scratch_subagent_gate(self._scratch_gate, payload, self._gate_dir)
        self.assertEqual(code, 0, err)  # SubagentStop hooks always exit 0

        flag_path = self._flag_path(sid, aid)
        self.assertTrue(
            os.path.exists(flag_path),
            f"expected .closure_violation flag not found: {flag_path} (stderr: {err})",
        )
        with open(flag_path, encoding="utf-8") as f:
            content = json.load(f)
        self.assertIsInstance(content, list)
        matching = [e for e in content if e.get("heading") == heading_line]
        # [Section E] A genuinely-invalid heading (missing Proof block
        # entirely) now trips BOTH check_single_heading's own "missing
        # proof block" detector AND status_claim_audit's separate
        # MISSING_PARSEABLE_EVIDENCE classifier for the SAME heading --
        # confirmed live: 2 true-positive entries, not 1. Loosened to
        # len(matching) >= 1 plus an assertion that at least one message
        # (across however many entries actually fired) mentions "proof" --
        # both detections are correct; this test was only ever checking
        # "was this caught at all," not "by exactly one mechanism."
        self.assertGreaterEqual(
            len(matching), 1,
            f"expected at least one flag entry for {heading_line!r}: {content}",
        )
        all_messages = []
        for entry in matching:
            self.assertIn("messages", entry)
            self.assertIn("warnings", entry)
            self.assertIsInstance(entry["messages"], list)
            self.assertIsInstance(entry["warnings"], list)
            all_messages.extend(entry["messages"])
        self.assertTrue(
            any("proof" in m.lower() for m in all_messages),
            f"expected a blocking message naming the missing Proof block, got {all_messages}",
        )

    # [BEHAVIORAL] Part B, companion negative case: the SAME transcript
    # shape (a sub-agent's own Edit tool_use introducing a CLOSED heading),
    # but with a VALID Proof block built via a real
    # `run_and_record.py -- true` call -- Part B's own detection logic must
    # find nothing to flag, so NO .closure_violation flag is written.
    def test_valid_proof_closed_heading_in_subagent_transcript_writes_no_flag(self):
        proof_block = _phase4_make_real_proof_block(self._gate_dir, _REAL_PROOF_COMMAND)
        heading_line = "H-PARTB-VALID -- CLOSED (2026-07-09, introduced by sub-agent)"
        original = "## H-PARTB-PRE2 (OPEN, still open)\nNothing closed yet.\n"
        new_block = (
            "## %s\n"
            "Real closure with a genuine, matching Proof block.\n\n%s"
            % (heading_line, proof_block)
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original + new_block)

        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        transcript_events = [
            _phase4_edit_tool_use_event("tu1", self._scratch_fixplan, "x", new_block),
        ]
        tpath = write_transcript(
            tempfile.mkdtemp(),
            "\n".join(json.dumps(e) for e in transcript_events) + "\n",
        )
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "cwd": os.path.dirname(self._scratch_fixplan),
            "last_assistant_message": "Closed the heading with real proof.",
        }
        code, err = _run_scratch_subagent_gate(self._scratch_gate, payload, self._gate_dir)
        self.assertEqual(code, 0, err)
        flag_path = self._flag_path(sid, aid)
        self.assertFalse(
            os.path.exists(flag_path),
            f"no .closure_violation flag should be written for a valid Proof block, found: {flag_path}",
        )


class V1AntiFalseStatusSubagentStopPath(unittest.TestCase):
    """Approved v1 anti-false-status coverage for the SubagentStop path.

    Unlike the older Phase 4 closure gate, this must catch high-risk DONE /
    READY / PASS-style status claims, not only headings containing CLOSED.
    """

    def setUp(self):
        (self._scratch_root, self._scratch_gate,
         self._scratch_fixplan) = _make_scratch_subagent_gate_repo()
        self._gate_dir = tempfile.mkdtemp(prefix="v1-subagent-stop-gate-")
        self._tmpdirs = []

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def _flag_path(self, sid, aid):
        return _phase4_closure_violation_flag_path(self._gate_dir, sid, aid)

    def _run_with_events(self, sid, aid, events):
        tmpdir = tempfile.mkdtemp(prefix="v1-subagent-transcript-")
        self._tmpdirs.append(tmpdir)
        tpath = write_transcript(
            tmpdir,
            "\n".join(json.dumps(e) for e in events) + "\n",
        )
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "transcript_path": tpath,
            "cwd": os.path.dirname(self._scratch_fixplan),
            "last_assistant_message": "Updated fix_plan.md.",
        }
        return _run_scratch_subagent_gate(self._scratch_gate, payload, self._gate_dir)

    def test_subagent_stop_writes_flag_for_done_claim_without_parseable_proof(self):
        sid = unique_session()
        aid = "agent-v1-done"
        new_block = (
            "## H-V1-SUBSTOP-DONE -- DONE (2026-07-10)\n"
            "Status: DONE. No parseable Proof block exists.\n"
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(new_block)
        events = [_phase4_edit_tool_use_event("tu1", self._scratch_fixplan, "x", new_block)]

        code, err = self._run_with_events(sid, aid, events)

        self.assertEqual(code, 0, err)
        flag_path = self._flag_path(sid, aid)
        self.assertTrue(os.path.exists(flag_path), "expected .closure_violation flag")
        with open(flag_path, encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload[0]["heading"], "H-V1-SUBSTOP-DONE -- DONE (2026-07-10)")

    def test_subagent_stop_writes_flag_for_ready_evidence_deletion(self):
        sid = unique_session()
        aid = "agent-v1-ready"
        heading = "H-V1-SUBSTOP-READY -- READY (2026-07-10)"
        current = (
            "## %s\n"
            "Status: READY for live connector use.\n"
            "Proof deleted.\n"
        ) % heading
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(current)
        events = [_phase4_edit_tool_use_event(
            "tu1", self._scratch_fixplan,
            "Proof:\n- command: python3 live_smoke.py\n",
            "Proof deleted.",
        )]

        code, err = self._run_with_events(sid, aid, events)

        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(self._flag_path(sid, aid)))

    def _existing_bad_content(self):
        content = (
            "## H-V1-SUBSTOP-EXISTING -- CLOSED (2026-07-10)\n"
            "Status: DONE. Existing bad evidence should not be revalidated "
            "without a successful write result.\n\n"
            "Proof:\n"
            "- command: true\n"
            "- exit_code: 0\n"
            "- proof_snapshot: /tmp/v1-substop-probe.json\n"
            "- verified_at: 2026-07-10T00:00:00+00:00\n"
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)
        return content

    def _tool_event(self, name, content):
        if name == "Write":
            input_dict = {"file_path": self._scratch_fixplan, "content": content}
        elif name == "MultiEdit":
            input_dict = {"file_path": self._scratch_fixplan,
                          "edits": [{"old_string": "- command: true",
                                     "new_string": "- command: true"}]}
        else:
            input_dict = {"file_path": self._scratch_fixplan,
                          "old_string": "H-V1-SUBSTOP-EXISTING",
                          "new_string": "H-V1-SUBSTOP-EXISTING"}
        return {
            "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu-v1-%s" % name.lower(),
                 "name": name, "input": input_dict},
            ]},
        }

    def _result_event(self, outcome, tool_use_id):
        if outcome == "missing_result":
            return None
        if outcome == "denied":
            content = "Hook PreToolUse: denied this tool call."
            is_error = False
        else:
            content = "Edit failed: old_string not found."
            is_error = True
        return {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id,
             "is_error": is_error, "content": content}
        ]}}

    def test_denied_errored_and_missing_result_writes_do_not_mark_existing_spans_touched(self):
        for tool_name in ("Edit", "MultiEdit", "Write"):
            for outcome in ("denied", "errored", "missing_result"):
                sid = unique_session()
                aid = "agent-v1-filter-%s-%s" % (tool_name.lower(), outcome)
                content = self._existing_bad_content()
                tool_event = self._tool_event(tool_name, content)
                events = [tool_event]
                result = self._result_event(outcome, "tu-v1-%s" % tool_name.lower())
                if result is not None:
                    events.append(result)

                code, err = self._run_with_events(sid, aid, events)

                self.assertEqual(code, 0, err)
                self.assertFalse(
                    os.path.exists(self._flag_path(sid, aid)),
                    "%s/%s should not write a closure_violation flag"
                    % (tool_name, outcome),
                )


class LoopGateFormatFixTierPrecedenceRealScriptOutput(unittest.TestCase):
    """spec: loop-team/runs/20260721_115722_plancheck-credit-output-loop-gate-format
    (PLAN_PASS on hash 641dcac9d19021ad334baf354c38eff0a080aebaa3c98a2f1546ef1f7040fd51),
    AC9.

    Exercises the SAME tier-1/tier-2 precedence check as
    PrecedenceRuleBetweenFreeTextAndStructuredOutput above (subagent_stop_gate.py
    lines ~234-253: lowercase equality against 'loop_gate: plan_pass'/
    'plan_fail'), but against `hooks/plan_check_credit_output.py`'s REAL,
    actually-executed stdout instead of a hand-typed string literal -- mirroring
    how a real plan-check-verifier dispatch pastes the helper script's exact
    3-line output as the tail of its own last_assistant_message (orchestrator.md
    "credit output helper instruction", roles/verifier.md:122-135).

    Written before the LOOP_GATE-format fix lands: the PASS-path test is
    expected to be RED against the CURRENT bare `LOOP_GATE: PASS` output --
    'loop_gate: pass' matches neither tier 1's 'loop_gate: plan_pass' nor tier
    2's 'loop_gate: plan_fail', so it falls through to tier 3, finds no
    StructuredOutput block (none is provided here), and writes no flag -- and
    GREEN once the fix makes the script emit the literal `LOOP_GATE: PLAN_PASS`
    line. The FAIL-path test asserts the invariant "FAIL must never write the
    flag", which already holds pre-fix (nothing matches either tier), so it is
    not itself a red/green regression signal, but it guards the same invariant
    going forward once the PASS path starts working.
    """

    HELPER = os.path.join(HOOKS_DIR, "plan_check_credit_output.py")

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="loop-gate-format-fix-")
        self._sessions_to_clean = []

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        for sid in self._sessions_to_clean:
            pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _spec_fixture(self):
        path = os.path.join(self._tmpdir, "spec.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join([
                "# Test Spec",
                "",
                "## Context",
                "Pre-implementation review.",
                "",
                "## Acceptance Criteria",
                "**AC1** [BEHAVIORAL] First criterion",
                "**AC2** [BEHAVIORAL] Second criterion",
                "**AC3** [BEHAVIORAL] Third criterion",
                "",
                "## Non-Goals",
                "Deferred items.",
            ]) + "\n")
        return path

    def _run_helper(self, verdict=None):
        cmd = [sys.executable, self.HELPER, self._spec_fixture(), "7", "9"]
        if verdict is not None:
            cmd += ["--verdict", verdict]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    # [BEHAVIORAL] AC9: real PASS-path helper output pasted as the tail of a
    # sub-agent's last_assistant_message -> the .verifier_pass flag IS written.
    def test_real_pass_output_pasted_as_tail_writes_verifier_pass_flag(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        real_output = self._run_helper()
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "Reviewed the spec, all ACs sound.\n" + real_output,
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        expected_flag = os.path.join(GATE_DIR, f"{sid}_{aid}.verifier_pass")
        self.assertTrue(
            os.path.exists(expected_flag),
            f"expected {expected_flag} to exist after pasting the real "
            f"helper script's PASS output as the last_assistant_message "
            f"tail: {real_output!r}",
        )

    # [BEHAVIORAL] AC9: real FAIL-path helper output pasted as the tail of a
    # sub-agent's last_assistant_message -> NO .verifier_pass flag is written.
    def test_real_fail_output_pasted_as_tail_writes_no_flag(self):
        sid = unique_session()
        aid = f"agent-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        real_output = self._run_helper(verdict="FAIL")
        payload = {
            "session_id": sid,
            "agent_id": aid,
            "last_assistant_message": "Reviewed the spec, found a real gap.\n" + real_output,
        }
        code, err = run_gate(payload)
        self.assertEqual(code, 0, err)
        pattern = os.path.join(GATE_DIR, f"{sid}_*.verifier_pass")
        self.assertEqual(
            glob.glob(pattern), [],
            f"no flag should be written after pasting the real helper "
            f"script's FAIL output as the last_assistant_message tail: "
            f"{real_output!r}",
        )


if __name__ == "__main__":
    unittest.main()
