"""Tests for H-LOOPSTOPGUARD-DUAL-TURN-WINDOW-FALSEDENY-1: the credit-gate's
PLAN_CHECK loop walks the WIDE `_TURN_RECORDS` window (turn-boundary-aware,
recognizes "Stop hook feedback:" events as non-boundaries) but, pre-fix,
checked membership in the NARROW `_blocked_tool_use_ids` set (built from the
file's own independent, non-"Stop hook feedback:"-aware local `turn` walk).
An earlier, already PreToolUse-denied Coder `tool_use` that falls INSIDE the
wide window but OUTSIDE the narrow one was therefore invisible to
`_blocked_tool_use_ids`, so the credit-gate loop treated it as a live,
unauthorized dispatch and fired a false PLAN_CHECK violation before ever
reaching a later, correctly-credited, actually-successful Coder dispatch.
See runs/2026-07-15_loop-stop-guard-dual-window/spec.md for the full root-
cause writeup and the fix (a separate `_CREDIT_GATE_BLOCKED_IDS` set, sourced
from the wide `_TURN_RECORDS` window, used only at the two credit-gate call
sites).

This is a NEW, separate file from hooks/test_loop_stop_guard.py (which
contains a large, unrelated, uncommitted rewrite -- not touched by this
build, per the spec's Section B/E). The helpers below are deliberately
self-contained duplicates of that file's own construction conventions
(tool_use/assistant_msg/tool_result_event/make_turn_events/run_guard,
_sb_verifier/_sb_coder/_sb_pass_result-shaped fixtures) rather than imports,
so this file has zero dependency on that file's in-flux state.

Covers:
  - AC-1 [BEHAVIORAL]: the false-denial reproduction -- must now exit 0.
  - AC-2 [BEHAVIORAL, negative control]: a genuinely-unauthorized Coder
    dispatch (no prior Verifier credit at all) must still exit 2.
  - AC-3 [BEHAVIORAL, negative control]: a Coder dispatch legitimately
    PreToolUse-denied AND inside the OLD narrow window too (the case
    `_blocked_tool_use_ids` already handled correctly) must still be
    recognized as blocked.

Run with:
    python3 -m pytest hooks/test_loop_stop_guard_dual_window_fix.py -q
"""
import atexit
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HOOKS_DIR, "loop_stop_guard.py")


def tool_use(name, tool_use_id, **inp):
    """A tool_use content-part dict carrying an explicit string id -- real
    Claude Code transcripts always tag a tool_use with an id, and the
    dual-window credit-gate logic under test is keyed on tool_use_id
    membership in a set."""
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": inp}


def assistant_msg(*parts):
    """A single assistant message holding the given tool_use parts (the same
    production shape real transcripts use)."""
    return {"type": "assistant", "message": {"role": "assistant", "content": list(parts)}}


def tool_result_event(tool_use_id, content_text):
    """A tool_result recorded as its own user-type entry, tied to a specific
    tool_use id -- the real production shape (tool_results are user-type
    entries in a Claude Code transcript, not assistant-type)."""
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": content_text}]}}


def human_event(text="please continue the build"):
    """The genuine human turn boundary: a user-type event whose content is a
    bare STRING (not a tool_result-carrying list, not a "Stop hook
    feedback:"-prefixed string)."""
    return {"type": "user", "message": {"role": "user", "content": text}}


def stop_hook_feedback_event(inner_text="[LOOP STOP-GUARD] prior turn's violation text"):
    """Mirrors the real event Claude Code injects into the transcript when a
    Stop hook exits 2 and the agent is forced to continue in the same
    logical turn: a user-type entry whose content is a bare STRING prefixed
    with "Stop hook feedback:". The shared
    spec_bound_verifier_credit.is_tool_result_turn() (which
    loop_stop_guard.py's own _TURN_RECORDS construction uses, via
    _spec_credit.current_turn()) recognizes this prefix as a NON-boundary,
    so the WIDE walk continues past it to the real human boundary. This
    file's own OLD, independent _is_tool_result_turn() (which the narrow
    `turn`/`_TOOL_USES`/`_TOOL_RESULTS`/`_blocked_tool_use_ids` walk uses)
    does NOT recognize this prefix -- for ANY string-content event it always
    returns False, so the narrow walk treats this event AS the turn boundary
    and stops here. This asymmetry is the exact root cause this fix
    addresses."""
    return {"type": "user", "message": {
        "role": "user", "content": "Stop hook feedback:\n%s" % inner_text}}


def make_events(*entries):
    """A real human boundary followed by the given events verbatim."""
    return [human_event()] + list(entries)


def run_guard(events, gate_dir, session_id="", stop_hook_active=False):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        payload = json.dumps({
            "transcript_path": path,
            "stop_hook_active": stop_hook_active,
            "session_id": session_id,
        })
        env = dict(os.environ, LOOP_GATE_DIR=gate_dir)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)


def write_spec(tmpdir, name, content):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def coder_tool_use(tool_use_id, spec_path, spec_hash):
    return tool_use(
        "Agent", tool_use_id,
        description="Coder for the dual-window fix repro",
        prompt=(
            "# Role: Coder\nImplement only this spec.\n"
            "SPEC: %s\nSPEC_SHA256=%s"
        ) % (spec_path, spec_hash),
    )


def verifier_tool_use(tool_use_id, spec_path, spec_hash):
    return tool_use(
        "Agent", tool_use_id,
        description="plan-check Verifier for the dual-window fix repro",
        prompt=(
            "Review exactly one spec before Coder.\n"
            "SPEC: %s\nSPEC_SHA256=%s\n"
        ) % (spec_path, spec_hash),
        # Genuinely synchronous fixture (immediate paired result, no
        # launch-ack stub involved) -- set explicitly per this codebase's
        # own established convention (see hooks/test_loop_stop_guard.py's
        # _sb_verifier call sites), not left to the module default.
        run_in_background=False,
    )


# Self-contained duplicates of hooks/test_loop_stop_guard.py's own
# _SB_SUPPORT_DIRS/_sb_cleanup_support_dirs/_sb_span_sha256/_sb_support_json
# construction conventions (see that file's lines ~527-567) -- duplicated
# rather than imported, per this file's own module docstring philosophy of
# zero dependency on that file's in-flux state. Names deliberately differ
# (_SUPPORT_DIRS/_cleanup_support_dirs vs. that file's _SB_-prefixed names)
# so no symbol would collide if this file were ever imported alongside it.
_SUPPORT_DIRS = []


def _cleanup_support_dirs():
    for path in list(_SUPPORT_DIRS):
        shutil.rmtree(path, ignore_errors=True)


atexit.register(_cleanup_support_dirs)


def _span_sha256(path, line_start, line_end):
    """Sha256 of a real 1-indexed, inclusive line span of a real file --
    duplicates _sb_span_sha256's exact logic, which itself exactly matches
    hooks/spec_bound_verifier_credit.py's own _support_span_digest
    convention (the function that mechanically re-validates a
    PLAN_SUPPORT_JSON claim's evidence_sha256)."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    selected = lines[line_start - 1:line_end]
    return hashlib.sha256("\n".join(selected).encode("utf-8")).hexdigest()


def _support_json(spec_hash, artifact_path):
    """Duplicates _sb_support_json's exact logic/shape."""
    return json.dumps({
        "artifact_path": artifact_path,
        "line_start": 1,
        "line_end": 1,
        "evidence_sha256": _span_sha256(artifact_path, 1, 1),
        "claim": "test fixture support citation for same-spec plan-check PASS",
        "spec_sha256": spec_hash,
    }, sort_keys=True)


def plan_pass_result(tool_use_id, spec_hash):
    """Builds a credit-gate-valid PLAN_PASS tool_result: a real, non-empty
    temp support artifact plus a PLAN_SUPPORT_JSON= line whose
    evidence_sha256 is genuinely re-derivable from that artifact (per
    H-LOOPSTOPGUARD-DUAL-TURN-WINDOW-FALSEDENY-1's credit-gate hardening),
    exactly matching hooks/test_loop_stop_guard.py's own _sb_pass_text
    shape."""
    support_dir = tempfile.mkdtemp(prefix="dual-window-fix-support-")
    _SUPPORT_DIRS.append(support_dir)
    artifact = os.path.join(support_dir, "plan_check_log.md")
    with open(artifact, "w", encoding="utf-8") as f:
        f.write("Fixture support: plan-check Verifier reviewed this spec.\n")
    return tool_result_event(
        tool_use_id,
        "PLAN_SUPPORT_JSON=%s\nREVIEWED_SPEC_SHA256=%s\nLOOP_GATE: PLAN_PASS" % (
            _support_json(spec_hash, artifact), spec_hash),
    )


def pretooluse_deny_result(tool_use_id):
    return tool_result_event(tool_use_id, "Hook PreToolUse: denied this tool call.")


class DualTurnWindowCreditGateFix(unittest.TestCase):
    """AC-1/AC-2/AC-3 for H-LOOPSTOPGUARD-DUAL-TURN-WINDOW-FALSEDENY-1."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="dual-window-fix-spec-")
        self.gate_dir = tempfile.mkdtemp(prefix="dual-window-fix-gate-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        shutil.rmtree(self.gate_dir, ignore_errors=True)

    def _spec(self, name, content):
        path = write_spec(self.tmpdir, name, content)
        return path, sha256_of(path)

    def _run(self, events):
        return run_guard(events, self.gate_dir, session_id="dwf-%s" % uuid.uuid4())

    # ------------------------------------------------------------------
    # AC-1 [BEHAVIORAL]
    # ------------------------------------------------------------------
    def test_ac1_earlier_denied_coder_outside_narrow_window_no_longer_false_denies(self):
        """An earlier PreToolUse-denied Coder dispatch, separated from the
        current position by a "Stop hook feedback:" event (so it falls
        inside the WIDE _TURN_RECORDS window -- reachable only because of
        the turn-boundary-widening for "Stop hook feedback:" events -- but
        OUTSIDE the OLD narrow `turn` window), followed by a real, later,
        genuinely-authorized Coder dispatch (real prior Verifier PLAN_PASS
        for the matching spec hash) -- must exit 0 (no false PLAN_CHECK
        violation). Pre-fix, this exact fixture exits 2 (see Section F's
        live reproduction for the direct before/after confirmation against
        the actual source file)."""
        old_spec, old_hash = self._spec("spec_old.md", "# old spec\nAC: old\n")
        new_spec, new_hash = self._spec("spec_new.md", "# new spec\nAC: new\n")

        events = make_events(
            assistant_msg(coder_tool_use("c-early", old_spec, old_hash)),
            pretooluse_deny_result("c-early"),
            stop_hook_feedback_event(),
            assistant_msg(verifier_tool_use("v1", new_spec, new_hash)),
            plan_pass_result("v1", new_hash),
            assistant_msg(coder_tool_use("c2", new_spec, new_hash)),
        )
        code, err = self._run(events)
        self.assertEqual(code, 0, err)

    def test_ac1_holds_with_multiple_stop_hook_feedback_events(self):
        """AC-1 variant: the spec's own wording is "one or more" Stop hook
        feedback events between the denied dispatch and the rest of the
        turn -- confirm two such events (e.g. two separate prior blocked
        Stop attempts) still resolve to exit 0."""
        old_spec, old_hash = self._spec("spec_old_multi.md", "# old spec multi\n")
        new_spec, new_hash = self._spec("spec_new_multi.md", "# new spec multi\n")

        events = make_events(
            assistant_msg(coder_tool_use("c-early-m", old_spec, old_hash)),
            pretooluse_deny_result("c-early-m"),
            stop_hook_feedback_event("[LOOP STOP-GUARD] first blocked attempt"),
            stop_hook_feedback_event("[LOOP STOP-GUARD] second blocked attempt"),
            assistant_msg(verifier_tool_use("v1m", new_spec, new_hash)),
            plan_pass_result("v1m", new_hash),
            assistant_msg(coder_tool_use("c2m", new_spec, new_hash)),
        )
        code, err = self._run(events)
        self.assertEqual(code, 0, err)

    # ------------------------------------------------------------------
    # AC-2 [BEHAVIORAL, negative control]
    # ------------------------------------------------------------------
    def test_ac2_genuinely_unauthorized_coder_still_blocks(self):
        """Negative control: a Coder dispatch with NO prior Verifier credit
        at all (still inside BOTH windows -- no Stop-hook-feedback widening
        event involved) must still exit 2. This fix must not create a new
        bypass."""
        spec, h = self._spec("spec_plain.md", "# plain spec\nAC: plain\n")
        events = make_events(
            assistant_msg(coder_tool_use("c-solo", spec, h)),
        )
        code, err = self._run(events)
        self.assertEqual(code, 2, err)

    # ------------------------------------------------------------------
    # AC-3 [BEHAVIORAL, negative control]
    # ------------------------------------------------------------------
    def test_ac3_denied_coder_inside_old_narrow_window_still_recognized_as_blocked(self):
        """Negative control: a Coder dispatch that was legitimately
        PreToolUse-denied AND falls inside the OLD narrow `turn` window too
        (no "Stop hook feedback:" widening event involved -- the case
        `_blocked_tool_use_ids` already handled correctly) must still be
        recognized as blocked and not re-evaluated -- confirms
        `_CREDIT_GATE_BLOCKED_IDS` is a strict superset of what
        `_blocked_tool_use_ids` would have caught for this in-window case,
        not a different/narrower set that regresses it. The overall turn
        still exits 0 because the later Coder dispatch IS properly
        authorized by a real prior Verifier PLAN_PASS."""
        spec, h = self._spec("spec_inwindow.md", "# in-window spec\nAC: iw\n")
        events = make_events(
            assistant_msg(coder_tool_use("c-denied", spec, h)),
            pretooluse_deny_result("c-denied"),
            assistant_msg(verifier_tool_use("v2", spec, h)),
            plan_pass_result("v2", h),
            assistant_msg(coder_tool_use("c-ok", spec, h)),
        )
        code, err = self._run(events)
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
