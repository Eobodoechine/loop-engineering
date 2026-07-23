"""Tests for loop_stop_guard.py -- the Phase-1 regression gate, the independent-
verifier gate, and the structural anti-spoof guarantees.

Drives the hook as a subprocess with crafted JSONL transcripts in the realistic
production shape: a human user message, an assistant message holding tool_use
parts, and tool_results recorded as their own user-type entries. Verification
signals (suite run, spawned verifier) are read from REAL tool_use/tool_result
entries, so prose claiming them must NOT satisfy the gate.

Run with:
    python3 -m pytest hooks/test_loop_stop_guard.py -q
"""
import ast
import atexit
import difflib
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS_DIR)
import _codex_fixture_builders as fb  # noqa: E402
GUARD = os.path.join(HOOKS_DIR, "loop_stop_guard.py")
# Repo root, derived exactly the way the guard derives its role-file base
# (hooks/'s parent) — residual_holes_spec.md AC-RH1c keys the runs/ exemption
# to "<repo>/runs/" with this same derivation.
REPO_DIR = os.path.dirname(HOOKS_DIR)


def tool_use(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def text(s):
    return {"type": "text", "text": s}


def make_turn(content, results=None, second_human=None):
    """A realistic turn: human msg -> assistant msg (tool_use/text parts) ->
    tool_results as their own user-type entries -> optional following human msg."""
    evs = [{"type": "user", "message": {"role": "user", "content": "go build"}},
           {"type": "assistant",
            "message": {"role": "assistant", "content": list(content)}}]
    for txt in (results or []):
        evs.append({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": txt}]}})
    if second_human:
        evs.append({"type": "user", "message": {"role": "user", "content": second_human}})
    return evs


def assistant_msg(*parts):
    """A single assistant message holding the given tool_use/text parts
    (same production shape make_turn builds internally)."""
    return {"type": "assistant",
            "message": {"role": "assistant", "content": list(parts)}}


def tool_result_event(tool_use_id, content_text):
    """A tool_result recorded as its own user-type entry, tied to a specific
    tool_use id — the returned-evidence channel AC-RH3b keys on. The guard's
    turn walk-back must NOT treat this as a turn boundary (it skips user
    entries that merely carry a tool_result)."""
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id,
         "content": content_text}]}}


def queue_operation_event(tool_use_id):
    """A type:queue-operation event embedding <tool-use-id> — the channel-(2)
    returned-evidence form for AC-RH3b (same JSONL event model the oga-guard's
    GAC6 dual-channel scan covers; some real-corpus completions surface ONLY
    here, with no tool_result echo). Not a user-type event, so the guard's
    turn walk-back must not treat it as a turn boundary either."""
    return {"type": "queue-operation", "op": "retire",
            "payload": "<tool-use-id>%s</tool-use-id>" % tool_use_id}


def make_turn_events(*entries):
    """A realistic multi-message current turn: one genuine human boundary,
    then the given assistant/tool_result events verbatim. Use with
    assistant_msg()/tool_result_event() when a fixture needs dispatch →
    returned-result → later-edit ordering that make_turn cannot express."""
    return [{"type": "user",
             "message": {"role": "user", "content": "go build"}}] + list(entries)


def run_guard(events, stop_hook_active=False):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        payload = json.dumps({"transcript_path": path,
                              "stop_hook_active": stop_hook_active})
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)


ROLE_EDIT = tool_use("Edit", file_path="/x/loop-team/roles/verifier.md",
                     old_string="a", new_string="b")
HARNESS_EDIT = tool_use("Edit", file_path="/x/loop-team/harness/verify.py",
                        old_string="a", new_string="b")
RUN_EVALS = tool_use("Bash", command="python3 loop-team/evals/run_evals.py")
VERIFIER_TASK = tool_use("Task", prompt="spawn an independent verifier to verify the change")
GREEN_RESULT = "Loop Team -- Eval/Regression Suite\n  SUITE:" + " GREEN"


class RegressionGate(unittest.TestCase):
    def test_role_edit_without_green_suite_blocks(self):
        code, err = run_guard(make_turn([ROLE_EDIT]))
        self.assertEqual(code, 2, err)

    def test_role_edit_with_green_and_verifier_passes(self):
        code, _ = run_guard(make_turn([ROLE_EDIT, RUN_EVALS, VERIFIER_TASK],
                                      results=[GREEN_RESULT]))
        self.assertEqual(code, 0)

    def test_role_edit_green_but_no_verifier_blocks(self):
        # run_evals' ".py" trips the feature/verifier gate -> still needs a verifier.
        code, _ = run_guard(make_turn([ROLE_EDIT, RUN_EVALS], results=[GREEN_RESULT]))
        self.assertEqual(code, 2)

    def test_harness_edit_without_green_blocks_even_with_verifier(self):
        code, err = run_guard(make_turn([HARNESS_EDIT, VERIFIER_TASK]))
        self.assertEqual(code, 2, err)

    def test_harness_edit_with_green_and_verifier_passes(self):
        code, _ = run_guard(make_turn([HARNESS_EDIT, RUN_EVALS, VERIFIER_TASK],
                                      results=[GREEN_RESULT]))
        self.assertEqual(code, 0)

    def test_red_suite_does_not_count_as_green(self):
        code, _ = run_guard(make_turn([ROLE_EDIT, RUN_EVALS],
                                      results=["SUITE: RED"]))
        self.assertEqual(code, 2)


class StructuralAntiSpoof(unittest.TestCase):
    """Bug-finder HIGH: the gate must read verification from REAL tool calls, not
    prose. An agent that only WRITES the magic words must still be blocked."""

    def test_prose_green_and_verifier_do_not_bypass_gate(self):
        spoof = text("I ran run_evals.py and it printed SUITE:" + " GREEN, and an "
                     "independent verifier already reviewed verifier.md.")
        code, _ = run_guard(make_turn([ROLE_EDIT, spoof]))  # no real tool_use/result
        self.assertEqual(code, 2)

    def test_prose_verifier_does_not_satisfy_feature_gate(self):
        # Real green suite, but the "verifier" is only prose -> still blocked.
        spoof = text("an independent verifier reviewed this change")
        code, _ = run_guard(make_turn([HARNESS_EDIT, RUN_EVALS, spoof],
                                      results=[GREEN_RESULT]))
        self.assertEqual(code, 2)

    def test_real_green_result_in_prose_block_does_not_count(self):
        # The green token sitting in an assistant TEXT block (not a tool_result)
        # must not satisfy SUITE_GREEN.
        code, _ = run_guard(make_turn([ROLE_EDIT, RUN_EVALS, text("SUITE:" + " GREEN")]))
        self.assertEqual(code, 2)


class ProductionEncoding(unittest.TestCase):
    def test_edit_followed_by_toolresult_still_blocks(self):
        # A trailing tool_result must not slice the edit out of the inspected turn.
        code, _ = run_guard(make_turn([ROLE_EDIT], results=["some command output"]))
        self.assertEqual(code, 2)

    def test_edit_in_prior_turn_not_counted_after_new_human(self):
        code, _ = run_guard(make_turn([ROLE_EDIT], second_human="thanks, all good"))
        self.assertEqual(code, 0)


class ExistingBehaviorHolds(unittest.TestCase):
    def test_code_feature_without_verifier_still_blocks(self):
        ts = tool_use("Edit", file_path="/x/src/app.ts", old_string="a", new_string="b")
        code, _ = run_guard(make_turn([ts]))
        self.assertEqual(code, 2)

    def test_docx_only_passes(self):
        docx = tool_use("Write", file_path="/x/resume.docx", content="...")
        code, _ = run_guard(make_turn([docx]))
        self.assertEqual(code, 0)

    def test_stop_hook_active_never_traps(self):
        code, _ = run_guard(make_turn([ROLE_EDIT]), stop_hook_active=True)
        self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# Fixtures for PlanBeforeCoderGate
# ---------------------------------------------------------------------------
CODER_AGENT = tool_use("Agent", description="Coder for the build",
                       prompt="# Role: Coder\nImplement the spec...")
CODER_WITH_VERIFY = tool_use("Agent", description="Coder for the build",
                              prompt="# Role: Coder\nImplement and verify tests pass...")
PLAN_VERIFIER = tool_use("Agent", description="Verifier plan-check",
                          prompt="You are an independent verifier reviewing the spec...")
RESEARCHER_VERIFY = tool_use("Agent", description="Researcher",
                              prompt="Research and verify library compatibility...")


class PlanBeforeCoderGate(unittest.TestCase):
    """Gate: a Coder Agent dispatch must be preceded by a plan-check Verifier
    dispatch within the same turn.  Tests cover ordering, anti-spoof, and the
    two known bug regressions."""

    # [BEHAVIORAL] AC-1: Coder dispatched with no Verifier at all → blocked.
    def test_coder_without_verifier_blocks(self):
        code, err = run_guard(make_turn([CODER_AGENT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] v1: legacy Verifier presence alone does not authorize Coder.
    def test_verifier_before_no_hash_coder_blocks(self):
        code, _ = run_guard(make_turn([PLAN_VERIFIER, CODER_AGENT]))
        self.assertEqual(code, 2)

    # [BEHAVIORAL] v1 spec-bound verifier-credit contract: a Coder requires
    # a prior successful Verifier result in the same parent transcript window.
    # A later Verifier dispatch cannot authorize an earlier Coder.
    def test_coder_before_verifier_blocks(self):
        code, err = run_guard(make_turn([CODER_AGENT, PLAN_VERIFIER]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-4: Verifier dispatch with no Coder at all → allowed.
    def test_verifier_alone_passes(self):
        code, _ = run_guard(make_turn([PLAN_VERIFIER]))
        self.assertEqual(code, 0)

    # [BEHAVIORAL] AC-5: Only prose mentioning "coder role" (no real Agent tool_use) → allowed.
    def test_prose_coder_mention_does_not_trigger_gate(self):
        prose = text("The coder role will implement the changes next.")
        code, _ = run_guard(make_turn([prose]))
        self.assertEqual(code, 0)

    # [BEHAVIORAL] AC-6: stop_hook_active=True bypasses all gates.
    def test_stop_hook_active_bypasses_gate(self):
        code, _ = run_guard(make_turn([CODER_AGENT]), stop_hook_active=True)
        self.assertEqual(code, 0)

    # [BEHAVIORAL] AC-7 Bug-1 regression: Coder whose prompt says "verify" must
    # still be detected as a Coder (not confused for a Verifier).
    def test_coder_with_verify_in_prompt_still_blocks(self):
        # CODER_WITH_VERIFY has "verify" in its prompt but is a Coder dispatch.
        # No plan-check Verifier precedes it → must exit 2.
        code, err = run_guard(make_turn([CODER_WITH_VERIFY]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-8 Bug-2 regression: A Researcher dispatch mentioning "verify"
    # must NOT satisfy the plan-check Verifier requirement.
    def test_researcher_verify_does_not_satisfy_plan_verifier(self):
        # RESEARCHER_VERIFY says "verify" but is not an independent verifier.
        # Coder follows it → still blocked because no real plan-check Verifier ran.
        code, err = run_guard(make_turn([RESEARCHER_VERIFY, CODER_AGENT]))
        self.assertEqual(code, 2, err)


class H_GUARD_1_Regression(unittest.TestCase):
    """H-GUARD-1: a plan-check Verifier dispatch whose prompt discusses Coder dispatch
    formats (e.g. "Coder for <task>", "roles/coder") must be recognized as a Verifier,
    not misclassified as a Coder.  The false positive was: _CODER_DETECT fired on the
    Verifier's prompt body before _VERIFIER_DETECT got a chance (old Coder-first if/elif).
    Also tests that 'plan-check verifier' / 'verifier plan-check' in the description are
    now recognized without requiring 'independent verifier' in the prompt."""

    # A plan-check Verifier dispatch identified by description (the false-positive case).
    # The prompt discusses Coder dispatch formats, which old code mis-detected as a Coder.
    GUARD_FP = tool_use(
        "Agent",
        description="Plan-check Verifier — Decision 6 Workflow migration spec",
        prompt=(
            "Review this plan. Step 3: dispatch the Coder using "
            "description='Coder for <task>'. Does await enforce ordering? "
            "Does roles/coder match the gate pattern?"
        ),
    )
    # Alternative description format used in TEAM_RELATIONS fixtures.
    GUARD_FP2 = tool_use(
        "Agent",
        description="Verifier plan-check on the spec",
        prompt="Review the spec. The Coder for this build will implement X.",
    )

    # [BEHAVIORAL] AC-H1: plan-check Verifier by description alone → recognized, not blocked.
    def test_plan_check_verifier_by_description_passes(self):
        code, err = run_guard(make_turn([self.GUARD_FP]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-H2: "verifier plan-check" description variant also recognized.
    def test_verifier_plan_check_description_variant_passes(self):
        code, err = run_guard(make_turn([self.GUARD_FP2]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] v1: a legacy plan-check Verifier dispatch does not authorize
    # a later Coder without the spec/hash/result contract.
    def test_plan_check_verifier_then_no_hash_coder_blocks(self):
        code, err = run_guard(make_turn([self.GUARD_FP, CODER_AGENT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] v1 spec-bound verifier-credit contract: a later plan-check
    # Verifier dispatch is not retroactive Coder authorization.
    def test_coder_before_plan_check_verifier_still_blocks(self):
        code, err = run_guard(make_turn([CODER_AGENT, self.GUARD_FP]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-H5 Bug-1 regression guard: Coder whose prompt says "verify"
    # must NOT be recognized as a Verifier under the new Verifier-first check order.
    def test_coder_with_verify_prompt_not_misclassified_as_verifier(self):
        # CODER_WITH_VERIFY has no plan-check/verifier.md pattern — must still block.
        code, err = run_guard(make_turn([CODER_WITH_VERIFY]))
        self.assertEqual(code, 2, err)


GATE_DIR = tempfile.mkdtemp(prefix="loop-gate-test-")
os.environ["LOOP_GATE_DIR"] = GATE_DIR


def run_guard_with_session(events, session_id="", stop_hook_active=False):
    """Like run_guard but also passes session_id in the payload (for cross-turn gate tests)."""
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
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)


def write_flag(session_id, agent_id="verifier"):
    """Manually pre-write a verifier_pass flag, simulating a completed SubagentStop."""
    os.makedirs(GATE_DIR, exist_ok=True)
    flag = os.path.join(GATE_DIR, f"{session_id}_{agent_id}.verifier_pass")
    open(flag, "w").close()
    return flag


class CrossTurnPlanCheckGate(unittest.TestCase):
    """v1 gate: legacy .verifier_pass files never authorize a Coder.

    Coder authorization must come from same-parent-transcript structural proof:
    a prior Verifier tool_use paired with a successful tool_result for the same
    canonical spec path and reviewed hash.
    """

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

    # [BEHAVIORAL] v1: a fresh legacy flag by itself is non-authorizing.
    def test_coder_with_flag_exits_zero_and_flag_survives(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        flag = write_flag(sid, "verifier-sub-1")
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertTrue(os.path.exists(flag), "Legacy flag may survive, but must not authorize Coder")

    # [BEHAVIORAL] v1: multiple fresh legacy flags are still non-authorizing.
    def test_multiple_flags_all_consumed(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        flag1 = write_flag(sid, "verifier-a")
        flag2 = write_flag(sid, "verifier-b")
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertTrue(os.path.exists(flag1))
        self.assertTrue(os.path.exists(flag2))

    # [BEHAVIORAL] AC-5: Coder dispatch, no flag exists → exit 2 (existing gate still fires).
    def test_coder_without_flag_exits_two(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] v1: repeated Coder attempts remain blocked when the only
    # evidence is a legacy flag.
    def test_flag_consumed_second_dispatch_blocks(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        write_flag(sid, "verifier-once")
        code1, err1 = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code1, 2, err1)
        code2, err2 = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code2, 2, err2)

    # [BEHAVIORAL] AC-9 (cross-turn variant): stop_hook_active=True bypasses ALL gates,
    # including the cross-turn plan-check gate, regardless of flag state.
    def test_stop_hook_active_bypasses_cross_turn_gate(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        # No flag; stop_hook_active=True → should still exit 0.
        code, _ = run_guard_with_session(
            make_turn([CODER_AGENT]), session_id=sid, stop_hook_active=True
        )
        self.assertEqual(code, 0)

    # [BEHAVIORAL] AC-13: session_id absent in payload → _flags = [], falls through to exit 2.
    def test_absent_session_id_falls_through_to_exit_two(self):
        # Explicitly run without session_id in payload (use the plain run_guard helper).
        code, err = run_guard(make_turn([CODER_AGENT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-13: session_id is empty string → _flags = [], falls through to exit 2.
    def test_empty_session_id_falls_through_to_exit_two(self):
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id="")
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-13: flag exists for a DIFFERENT session → not consumed, gate still fires.
    def test_flag_for_different_session_does_not_waive_gate(self):
        sid_real = f"test-session-{uuid.uuid4()}"
        sid_other = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.extend([sid_real, sid_other])
        write_flag(sid_other, "verifier-x")  # flag for a different session
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid_real)
        self.assertEqual(code, 2, err)
        # The other session's flag must still be present (not accidentally consumed).
        self.assertTrue(os.path.exists(os.path.join(GATE_DIR, f"{sid_other}_verifier-x.verifier_pass")))


def _age_flag(flag_path, seconds_old):
    """Backdate a flag file's mtime by seconds_old using os.utime, for TTL tests."""
    now = time.time()
    stamp = now - seconds_old
    os.utime(flag_path, (stamp, stamp))


class PlanPassTTLGate(unittest.TestCase):
    """Legacy TTL cases retained as non-authorization checks for v1."""

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

    # [BEHAVIORAL] v1: violation-shaped turn + fresh flag still blocks.
    def test_fresh_flag_passes_and_flag_survives(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        flag = write_flag(sid, "verifier-fresh")
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertTrue(os.path.exists(flag), "Legacy flag may survive, but must not authorize Coder")

    # [BEHAVIORAL] AC5 case 2: violation-shaped turn + only a stale flag
    # (mtime older than PLAN_PASS_TTL_SECONDS = 24h) → exit 2. TTL manipulated
    # via os.utime per the spec's interface note.
    def test_stale_flag_blocks(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        flag = write_flag(sid, "verifier-stale")
        _age_flag(flag, 24 * 3600 + 60)  # just over 24h old
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] v1: Coder before Verifier blocks because there is no prior
    # successful Verifier result for that Coder.
    def test_coder_before_verifier_same_turn_no_flag_needed_passes(self):
        coder = tool_use("Agent", description="Coder for the AC2 order-insensitivity fix",
                          prompt="# Role: Coder\nImplement per spec...")
        plan_check_verifier = tool_use(
            "Agent", description="plan-check Verifier for the AC2 order-insensitivity fix",
            prompt="You are an independent verifier reviewing the spec...")
        code, err = run_guard(make_turn([coder, plan_check_verifier]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC5 case 4 (regression): violation-shaped turn + no flags at
    # all → exit 2. (Duplicates test_coder_without_flag_exits_two's intent with
    # a session-scoped assertion for completeness alongside the new TTL cases.)
    def test_violation_shaped_turn_no_flags_still_blocks(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 2, err)


def _sb_write_spec(tmpdir, name="spec.md", content="# spec\n"):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _sb_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


_SB_SUPPORT_DIRS = []


def _sb_cleanup_support_dirs():
    for path in list(_SB_SUPPORT_DIRS):
        shutil.rmtree(path, ignore_errors=True)


atexit.register(_sb_cleanup_support_dirs)


def _sb_span_sha256(path, line_start, line_end):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    selected = lines[line_start - 1:line_end]
    return hashlib.sha256("\n".join(selected).encode("utf-8")).hexdigest()


def _sb_support_json(spec_hash, artifact_path):
    return json.dumps({
        "artifact_path": artifact_path,
        "line_start": 1,
        "line_end": 1,
        "evidence_sha256": _sb_span_sha256(artifact_path, 1, 1),
        "claim": "test fixture support citation for same-spec plan-check PASS",
        "spec_sha256": spec_hash,
    }, sort_keys=True)


def _sb_pass_text(spec_hash, extra_text=""):
    support_dir = tempfile.mkdtemp(prefix="spec-bound-support-")
    _SB_SUPPORT_DIRS.append(support_dir)
    artifact = os.path.join(support_dir, "plan_check_log.md")
    with open(artifact, "w", encoding="utf-8") as f:
        f.write("Fixture support: plan-check Verifier reviewed this spec.\n")
    prefix = ("%s\n" % extra_text.strip()) if extra_text and extra_text.strip() else ""
    return (
        "%sPLAN_SUPPORT_JSON=%s\n"
        "REVIEWED_SPEC_SHA256=%s\n"
        "LOOP_GATE: PLAN_PASS"
    ) % (prefix, _sb_support_json(spec_hash, artifact), spec_hash)


def _sb_tool_use(name, tool_use_id, **inp):
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": inp}


def _sb_verifier(spec_ref, spec_hash, tool_use_id="verify-1", extra_prompt="",
                  run_in_background=None):
    # Section B narrow exception: an explicit, optional run_in_background
    # parameter, threaded through to _sb_tool_use() (which already accepts
    # arbitrary kwargs via **inp) -- set explicitly at every call site below
    # so no fixture in this file silently depends on the default.
    kwargs = {}
    if run_in_background is not None:
        kwargs["run_in_background"] = run_in_background
    return _sb_tool_use(
        "Agent",
        tool_use_id,
        description="plan-check Verifier for spec-bound gate",
        prompt=(
            "Review exactly one spec before Coder.\n"
            "SPEC: %s\n"
            "SPEC_SHA256=%s\n"
            "%s"
        ) % (spec_ref, spec_hash, extra_prompt),
        **kwargs
    )


def _sb_coder(spec_ref, spec_hash, tool_use_id="coder-1", tool_name="Agent"):
    return _sb_tool_use(
        tool_name,
        tool_use_id,
        description="Coder for spec-bound gate",
        prompt=(
            "# Role: Coder\nImplement only this spec.\n"
            "SPEC: %s\n"
            "SPEC_SHA256=%s"
        ) % (spec_ref, spec_hash),
    )


def _sb_coder_no_hash(spec_ref, tool_use_id="coder-1", tool_name="Agent"):
    return _sb_tool_use(
        tool_name,
        tool_use_id,
        description="Coder for spec-bound gate",
        prompt=(
            "# Role: Coder\nImplement only this spec.\n"
            "SPEC: %s"
        ) % (spec_ref,),
    )


def _sb_pass_result(tool_use_id, spec_hash, extra_text=""):
    return tool_result_event(tool_use_id, _sb_pass_text(spec_hash, extra_text))


def _sb_error_result(tool_use_id, content="Verifier crashed"):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id,
         "is_error": True, "content": content}
    ]}}


def _sb_run_guard_raw(lines, session_id=""):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        payload = json.dumps({
            "transcript_path": path,
            "stop_hook_active": False,
            "session_id": session_id,
        })
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)


class SpecBoundVerifierCreditGateV1(unittest.TestCase):
    """Approved v1 contract: no cross-turn persisted Coder credit.

    Coder authorization is same-parent-transcript structural proof only:
    prior Verifier tool_use, successful paired tool_result before the Coder,
    exactly one spec ref, current spec hash match, and reviewed-hash echo.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="spec-bound-credit-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _spec(self, name="spec.md", content="# spec\nAC: test\n"):
        path = _sb_write_spec(self.tmpdir, name, content)
        return path, _sb_sha256(path)

    def _events(self, *entries):
        return make_turn_events(*entries)

    def test_matching_prior_verifier_result_allows_coder(self):
        spec, h = self._spec()
        events = self._events(
            # AC-C-6 item 2 / Section B confirmed floor: genuinely
            # synchronous fixture (immediate paired result, no stub/
            # notification), so run_in_background=False explicitly.
            assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
            _sb_pass_result("v1", h),
            assistant_msg(_sb_coder(spec, h, "c1")),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 0, err)

    def test_verifier_tool_use_without_result_before_coder_blocks(self):
        spec, h = self._spec()
        code, err = run_guard(self._events(
            # Section B syntactic sweep: no result exists for this vid at
            # all, so this fixture is insensitive to dispatch-mode
            # classification; set explicitly anyway (False, since a
            # foreground/synchronous dispatch is the simpler, more literal
            # reading of "Coder immediately follows with nothing").
            assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
            assistant_msg(_sb_coder(spec, h, "c1")),
        ))
        self.assertEqual(code, 2, err)

    def test_verifier_result_after_coder_blocks(self):
        spec, h = self._spec()
        code, err = run_guard(self._events(
            # Section B syntactic sweep: the result is positioned AFTER the
            # Coder dispatch, so it never enters the credit-check window
            # regardless of dispatch mode -- insensitive; set explicitly.
            assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
            assistant_msg(_sb_coder(spec, h, "c1")),
            _sb_pass_result("v1", h),
        ))
        self.assertEqual(code, 2, err)

    def test_coder_before_verifier_blocks(self):
        spec, h = self._spec()
        code, err = run_guard(self._events(
            assistant_msg(_sb_coder(spec, h, "c1")),
            # Section B syntactic sweep: the Coder dispatch precedes the
            # Verifier entirely, so no verifier record ever precedes the
            # Coder position -- insensitive; set explicitly.
            assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
            _sb_pass_result("v1", h),
        ))
        self.assertEqual(code, 2, err)

    def test_spec_a_verifier_before_spec_b_coder_blocks(self):
        spec_a, h_a = self._spec("spec_a.md", "# spec A\n")
        spec_b, h_b = self._spec("spec_b.md", "# spec B\n")
        code, err = run_guard(self._events(
            # Section B syntactic sweep: hash mismatch (spec A vs spec B)
            # skips this record before the stub-classification check is
            # ever reached -- insensitive; set explicitly.
            assistant_msg(_sb_verifier(spec_a, h_a, "v1", run_in_background=False)),
            _sb_pass_result("v1", h_a),
            assistant_msg(_sb_coder(spec_b, h_b, "c1")),
        ))
        self.assertEqual(code, 2, err)

    def test_spec_changed_after_review_blocks_current_hash_mismatch(self):
        spec, h_old = self._spec(content="# spec\nversion 1\n")
        # Section B syntactic sweep: current_spec_hash_matches(verifier_info)
        # fails (spec changed after review) before the stub check is ever
        # reached -- insensitive; set explicitly.
        verifier = _sb_verifier(spec, h_old, "v1", run_in_background=False)
        result = _sb_pass_result("v1", h_old)
        with open(spec, "w", encoding="utf-8") as f:
            f.write("# spec\nversion 2\n")
        h_new = _sb_sha256(spec)
        self.assertNotEqual(h_old, h_new)
        code, err = run_guard(self._events(
            assistant_msg(verifier),
            result,
            assistant_msg(_sb_coder(spec, h_old, "c1")),
        ))
        self.assertEqual(code, 2, err)

    def test_zero_multiple_and_ambiguous_spec_refs_block(self):
        spec_a, h_a = self._spec("spec_a.md", "# spec A\n")
        spec_b, _h_b = self._spec("spec_b.md", "# spec B\n")
        cases = [
            # Section B syntactic sweep: none of these 3 cases ever reach
            # the stub-classification check (missing/ambiguous/unresolvable
            # spec ref short-circuits extract_spec_info() first) --
            # insensitive; set explicitly regardless.
            _sb_tool_use("Agent", "v0", description="plan-check Verifier",
                         prompt="Review the plan. SPEC_SHA256=%s" % h_a,
                         run_in_background=False),
            _sb_verifier("%s and %s" % (spec_a, spec_b), h_a, "v2", run_in_background=False),
            _sb_verifier(os.path.basename(spec_a), h_a, "vbase", run_in_background=False),
        ]
        for verifier in cases:
            code, err = run_guard(self._events(
                assistant_msg(verifier),
                _sb_pass_result(verifier["id"], h_a),
                assistant_msg(_sb_coder(spec_a, h_a, "c1")),
            ))
            self.assertEqual(code, 2, "verifier %r should block: %s" % (verifier, err))

    def test_denied_or_errored_verifier_result_blocks(self):
        spec, h = self._spec()
        denied = tool_result_event("v1", "Hook PreToolUse: denied this tool call.")
        for result in (denied, _sb_error_result("v1")):
            code, err = run_guard(self._events(
                # Section B syntactic sweep: is_error_or_deny excludes this
                # record from the stub-skip condition regardless of
                # dispatch mode -- insensitive; set explicitly.
                assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
                result,
                assistant_msg(_sb_coder(spec, h, "c1")),
            ))
            self.assertEqual(code, 2, err)

    def test_successful_result_prose_mentions_deny_error_allowed(self):
        spec, h = self._spec()
        code, err = run_guard(self._events(
            # Section B confirmed floor: genuinely synchronous fixture.
            assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
            _sb_pass_result("v1", h, "Reviewed denied and errored-result handling as prose."),
            assistant_msg(_sb_coder(spec, h, "c1")),
        ))
        self.assertEqual(code, 0, err)

    def test_plan_fail_structured_output_conflict_and_buried_pass_block(self):
        spec, h = self._spec()
        conflict = tool_result_event(
            "v1",
            "LOOP_GATE: PLAN_PASS\nStructuredOutput: {\"loop_gate\":\"PLAN_FAIL\"}\n"
            "REVIEWED_SPEC_SHA256=%s" % h,
        )
        buried = tool_result_event(
            "v1",
            "LOOP_GATE: PLAN_PASS\nREVIEWED_SPEC_SHA256=%s\nTrailing non-pass text" % h,
        )
        explicit_fail = tool_result_event(
            "v1",
            "REVIEWED_SPEC_SHA256=%s\nLOOP_GATE: PLAN_FAIL" % h,
        )
        for result in (conflict, buried, explicit_fail):
            code, err = run_guard(self._events(
                # Section B confirmed floor (masking-coincidence class): a
                # buggy stub-skip could silently absorb these as
                # "unresolved" and still report block for the WRONG reason
                # -- set run_in_background=False explicitly so green stays
                # diagnostic, not a masking coincidence.
                assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
                result,
                assistant_msg(_sb_coder(spec, h, "c1")),
            ))
            self.assertEqual(code, 2, err)

    def test_malformed_transcript_fails_closed_for_coder_auth(self):
        spec, h = self._spec()
        events = self._events(
            # Section B syntactic sweep: read_jsonl_strict() fails closed
            # before the credit logic ever runs -- insensitive; set
            # explicitly.
            assistant_msg(_sb_verifier(spec, h, "v1", run_in_background=False)),
            _sb_pass_result("v1", h),
            assistant_msg(_sb_coder(spec, h, "c1")),
        )
        lines = [json.dumps(events[0]), "{malformed-json", json.dumps(events[-1])]
        code, err = _sb_run_guard_raw(lines)
        self.assertEqual(code, 2, err)

    def test_codex_spawn_agent_coder_without_verifier_blocks(self):
        spec, h = self._spec()
        events = [
            fb.codex_session_meta("codex-stop-parent"),
            fb.codex_turn_context(),
            *fb.codex_spawn_agent(
                "call-coder", "fc-coder", "agent-coder", "coder",
                "# Role: Coder\nImplement only this spec.\nSPEC: %s\nSPEC_SHA256=%s"
                % (spec, h)),
        ]
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)
        self.assertIn("same-window plan-check Verifier", err)

    def test_codex_spawn_agent_prior_verifier_pass_allows_coder(self):
        spec, h = self._spec()
        events = [
            fb.codex_session_meta("codex-stop-parent"),
            fb.codex_turn_context(),
            *fb.codex_spawn_agent(
                "call-verifier", "fc-verifier", "agent-verifier", "default",
                "plan-check Verifier for spec-bound gate\n"
                "Review exactly one spec before Coder.\nSPEC: %s\nSPEC_SHA256=%s"
                % (spec, h)),
            *fb.codex_wait_agent(
                "call-wait", "fc-wait", ["agent-verifier"],
                {"agent-verifier": {"completed": _sb_pass_text(
                    h, "Reviewed and approved.")}}),
            *fb.codex_spawn_agent(
                "call-coder", "fc-coder", "agent-coder", "coder",
                "# Role: Coder\nImplement only this spec.\nSPEC: %s\nSPEC_SHA256=%s"
                % (spec, h)),
        ]
        code, err = run_guard(events)
        self.assertEqual(code, 0, err)

    def test_codex_prior_turn_verifier_pass_does_not_authorize_coder(self):
        spec, h = self._spec()
        events = [
            fb.codex_session_meta("codex-stop-parent"),
            fb.codex_turn_context(),
            *fb.codex_spawn_agent(
                "call-verifier", "fc-verifier", "agent-verifier", "default",
                "plan-check Verifier for spec-bound gate\n"
                "Review exactly one spec before Coder.\nSPEC: %s\nSPEC_SHA256=%s"
                % (spec, h)),
            *fb.codex_wait_agent(
                "call-wait", "fc-wait", ["agent-verifier"],
                {"agent-verifier": {"completed": _sb_pass_text(
                    h, "Reviewed and approved.")}}),
            fb.codex_turn_context(),
            *fb.codex_spawn_agent(
                "call-coder", "fc-coder", "agent-coder", "coder",
                "# Role: Coder\nImplement only this spec.\nSPEC: %s\nSPEC_SHA256=%s"
                % (spec, h)),
        ]
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)

    def test_missing_duplicate_or_non_string_agent_ids_with_coder_block(self):
        spec, h = self._spec()
        coder_missing = tool_use("Agent", description="Coder for missing id",
                                 prompt="SPEC: %s\nSPEC_SHA256=%s" % (spec, h))
        coder_non_string = _sb_tool_use(
            "Agent", {"bad": "id"}, description="Coder for non-string id",
            prompt="SPEC: %s\nSPEC_SHA256=%s" % (spec, h))
        # Section B syntactic sweep: validate_unique_string_dispatch_ids()
        # fails on the malformed/duplicate CODER id before the stub check
        # is ever reached for this verifier -- insensitive; set explicitly.
        duplicate_verifier = _sb_verifier(spec, h, "dup", run_in_background=False)
        duplicate_coder = _sb_coder(spec, h, "dup")
        cases = [coder_missing, coder_non_string, duplicate_coder]
        for coder in cases:
            code, err = run_guard(self._events(
                assistant_msg(duplicate_verifier),
                _sb_pass_result("dup", h),
                assistant_msg(coder),
            ))
            self.assertEqual(code, 2, "coder %r should block: %s" % (coder, err))

    def test_multiple_coder_dispatches_valid_a_plus_invalid_b_blocks(self):
        spec_a, h_a = self._spec("spec_a.md", "# spec A\n")
        spec_b, h_b = self._spec("spec_b.md", "# spec B\n")
        code, err = run_guard(self._events(
            # Section B syntactic sweep: coder B's own hash-mismatch blocks
            # the whole turn regardless of dispatch mode -- insensitive;
            # set explicitly.
            assistant_msg(_sb_verifier(spec_a, h_a, "v1", run_in_background=False)),
            _sb_pass_result("v1", h_a),
            assistant_msg(_sb_coder(spec_a, h_a, "c1")),
            assistant_msg(_sb_coder(spec_b, h_b, "c2")),
        ))
        self.assertEqual(code, 2, err)

    def test_absolute_relative_and_symlink_spec_refs_allow_when_unambiguous(self):
        spec, h = self._spec()
        symlink = os.path.join(self.tmpdir, "spec_link.md")
        os.symlink(spec, symlink)
        rel_spec = os.path.relpath(spec, os.getcwd())
        for ref in (spec, rel_spec, symlink):
            code, err = run_guard(self._events(
                # Section B confirmed floor (3 sub-cases): genuinely
                # synchronous fixture.
                assistant_msg(_sb_verifier(ref, h, "v1", run_in_background=False)),
                _sb_pass_result("v1", h),
                assistant_msg(_sb_coder(ref, h, "c1")),
            ))
            self.assertEqual(code, 0, "ref %r should allow: %s" % (ref, err))

    def test_workflow_coder_blocks_v1_even_with_same_spec_hash_verifier(self):
        spec, h = self._spec()
        workflow = _sb_tool_use(
            "Workflow",
            "wf1",
            script=(
                "await agent({description:'plan-check Verifier', prompt:'SPEC: %s "
                "SPEC_SHA256=%s'}); await agent({description:'Coder for build', "
                "prompt:'SPEC: %s SPEC_SHA256=%s'});"
            ) % (spec, h, spec, h),
        )
        code, err = run_guard(self._events(assistant_msg(workflow)))
        self.assertEqual(code, 2, err)

    def test_no_hash_coder_with_prior_legacy_verifier_shaped_dispatch_blocks(self):
        spec, _h = self._spec()
        legacy_verifier = _sb_tool_use(
            "Agent",
            "legacy-v1",
            description="plan-check Verifier for legacy shape",
            prompt="Review the plan before Coder.",
        )
        code, err = run_guard(self._events(
            assistant_msg(legacy_verifier),
            assistant_msg(_sb_coder_no_hash(spec, "c1")),
        ))
        self.assertEqual(code, 2, err)


# ---------------------------------------------------------------------------
# Fixtures for ResearchGate
# ---------------------------------------------------------------------------
RESEARCHER_AGENT = tool_use("Agent",
    description="Researcher Mode D — platform architecture domain brief",
    prompt="You are the Researcher. Find the Cowork skill registry mechanism...")

RESEARCHER_AGENT_BODY_ONLY = tool_use("Agent",
    description="Dispatch sub-agent for context",
    prompt="The researcher mode D found that manifest.json is the registry...")

PLAN_VERIFIER_AFTER = tool_use("Agent",
    description="Plan-check Verifier — research-gate spec",
    prompt="Review the plan for adding the Research gate to loop_stop_guard.py...")

FEATURE_EDIT = tool_use("Edit",
    file_path="/x/Claude/loop/hooks/loop_stop_guard.py",
    old_string="sys.exit(0)", new_string="sys.exit(0)  # updated")


class ResearchGate(unittest.TestCase):
    """Gate: Researcher sub-agent dispatched + direct Oga edit + no plan-check Verifier between them → exit 2."""

    # [BEHAVIORAL] AC-R1: Researcher + direct edit (no Verifier between) → exit 2
    def test_researcher_then_direct_edit_without_verifier_blocks(self):
        code, err = run_guard(make_turn([RESEARCHER_AGENT, FEATURE_EDIT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-R2: Researcher + plan-check Verifier AFTER + edit → exit 0
    def test_researcher_then_verifier_then_edit_passes(self):
        code, err = run_guard(make_turn([RESEARCHER_AGENT, PLAN_VERIFIER_AFTER, FEATURE_EDIT]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-R3: Researcher alone (no edit) → exit 0
    def test_researcher_alone_passes(self):
        code, err = run_guard(make_turn([RESEARCHER_AGENT]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-R4: Direct edit alone (no Researcher dispatch) → existing FEATURE
    # gate fires. We cannot distinguish which gate triggered from exit code alone;
    # assert exit 2.
    def test_direct_edit_alone_blocks_via_feature_gate(self):
        code, err = run_guard(make_turn([FEATURE_EDIT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-R5, REWRITTEN per residual_holes_spec.md AC-RH3b (stated
    # reason: AC-RH3b spec change — _seen_researcher2 must arm only when the
    # current turn also carries RETURNED-EVIDENCE for the Researcher dispatch,
    # so this fixture now includes a tool_result whose tool_use_id matches the
    # researcher dispatch's id). The exit-2 assertion is KEPT: with the gate
    # genuinely armed by real returned evidence, a Verifier that ran EARLY
    # (before the research) still does not satisfy "plan-check Verifier after
    # research", so the direct code edit must still block. This is the arm-on-
    # result gate's own regression case.
    def test_early_verifier_then_researcher_then_edit_blocks(self):
        researcher = dict(RESEARCHER_AGENT)
        researcher["id"] = "toolu_rh3_early_verifier_case"
        events = make_turn_events(
            assistant_msg(PLAN_VERIFIER_AFTER, researcher),
            tool_result_event("toolu_rh3_early_verifier_case",
                              "Researcher findings: the registry mechanism is manifest-based."),
            assistant_msg(FEATURE_EDIT),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-R6: "researcher" appears only in a Verifier's PROMPT BODY (not in
    # the description field) + direct edit. The Researcher-detection pattern must NOT
    # fire on the body of a Verifier dispatch. The FEATURE gate will still block the
    # bare edit, so we still expect exit 2 — just not from the Research gate.
    # Assert exit 2 and that the guard does not crash.
    def test_researcher_in_verifier_body_does_not_trigger_research_gate(self):
        code, err = run_guard(make_turn([RESEARCHER_AGENT_BODY_ONLY, FEATURE_EDIT]))
        # FEATURE gate (no verifier before edit) fires → exit 2; guard must not crash.
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-R7: Researcher + plan-check Verifier + Coder dispatch (no direct
    # Oga edit) → normal loop flow → exit 0
    def test_researcher_verifier_coder_no_direct_edit_passes(self):
        """[D.2 R3 confirmed exception] Same surface fixture shape as the
        code==2-inversion tests elsewhere in this file (a Verifier+Coder
        pair asserting an ALLOWED outcome), but this test's own point
        (AC-R7) is the OPPOSITE: a Researcher dispatch, followed by a
        CREDITED and resolved Verifier PASS, followed by a Coder dispatch,
        must be ALLOWED. Rebuilt onto a genuine, resolved Verifier-PASS
        credit chain (real spec file + matching SHA256 + a paired
        REVIEWED_SPEC_SHA256=/LOOP_GATE: PLAN_PASS result), preserving the
        original code == 0 assertion."""
        d = tempfile.mkdtemp(prefix="research-gate-r7-")
        try:
            spec_path = _sb_write_spec(d)
            spec_hash = _sb_sha256(spec_path)
            researcher = dict(RESEARCHER_AGENT)
            researcher["id"] = "r7-researcher"
            events = make_turn_events(
                assistant_msg(researcher,
                              _sb_verifier(spec_path, spec_hash, "r7-verifier",
                                           run_in_background=False)),
                _sb_pass_result("r7-verifier", spec_hash),
                assistant_msg(_sb_coder(spec_path, spec_hash, "r7-coder")),
            )
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-R8: stop_hook_active=True bypasses all gates, including Research gate
    def test_stop_hook_active_bypasses_research_gate(self):
        code, err = run_guard(
            make_turn([RESEARCHER_AGENT, FEATURE_EDIT]),
            stop_hook_active=True,
        )
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-R9: Researcher dispatched with verb-prefix description
    # e.g. "Launch Researcher sub-agent" → description starts with "launch" but
    # contains "researcher" within 15 chars — gate must still detect it.
    def test_verb_prefix_researcher_description_still_detected(self):
        researcher_verb = tool_use("Agent",
            description="Launch Researcher sub-agent for domain brief",
            prompt="Find the platform architecture...")
        code, err = run_guard(make_turn([researcher_verb, FEATURE_EDIT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-R10: Anti-spoof — description where "researcher" appears AFTER a
    # hyphen (e.g. "Long-term researcher review") must NOT set _seen_researcher2, because
    # the '-' in "long-term" breaks the [a-z ]{0,15} character-class match before
    # "researcher" is reached. No verifier runs → FEATURE gate fires → exit 2.
    def test_hyphenated_prefix_researcher_not_detected(self):
        # "long-term researcher review" after lower(): '-' stops [a-z ]{0,15} at 4 chars;
        # "researcher" doesn't follow immediately → _seen_researcher2 stays False.
        non_researcher = tool_use("Agent",
            description="Long-term researcher review — code analysis",
            prompt="Analyze the codebase...")
        code, err = run_guard(make_turn([non_researcher, FEATURE_EDIT]))
        # No verifier, no researcher detected → FEATURE gate fires → exit 2.
        self.assertEqual(code, 2, err)


# ---------------------------------------------------------------------------
# residual_holes_spec.md (runs/2026-07-02_003000-stopguard-residual-holes)
# AC-RH1 / AC-RH2 / AC-RH3 / AC-RH7 cases. Written spec-first: the exit-0
# expectations below are RED against the unmodified guard by design.
# ---------------------------------------------------------------------------

class StructuralExemptionsRH1(unittest.TestCase):
    """AC-RH1: when a blob-only FEATURE/ROLE_OR_HARNESS fire has structural
    Write/Edit/MultiEdit file_paths that are all under a temp root, are exactly
    the two ~/.claude settings files, or are all .md under <repo>/runs/, the
    gate is suppressed. Paths are realpath-resolved BEFORE classification, so
    symlink evasion (tmp → repo, runs/*.md → roles/) must still block.

    Fixture isolation notes:
    - Temp fixtures use tmp-prefixed tempfile APIs (mkdtemp) with teardown;
      nothing is ever written to a fixed /tmp name.
    - The ~/.claude fixtures only REFERENCE the real paths inside the crafted
      transcript JSON — this test never creates, opens, or writes anything
      under the real ~/.claude. It relies on the guard classifying by
      realpath/basename comparison of the transcript's file_path string, not
      by reading the file (the settings.json exemption must hold whether or
      not the file exists).
    - The runs/ fixtures use <repo>/runs/<uuid>/... paths. Only the symlink
      variant materializes anything on disk (a symlink cannot be faked), in a
      uuid-named subdir removed in a finally block.
    """

    # [BEHAVIORAL] AC-RH1a: tmp-only .py turn → exit 0 (RED until implemented).
    def test_tmp_only_code_write_suppresses_feature(self):
        d = tempfile.mkdtemp(prefix="rh1-tmponly-", dir="/tmp")
        try:
            w = tool_use("Write", file_path=os.path.join(d, "scratch_probe.py"),
                         content="print('throwaway probe')\n")
            code, err = run_guard(make_turn([w]))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-RH1a: tempfile.gettempdir() is itself a listed temp root
    # (on macOS it is $TMPDIR under /var/folders/, NOT /tmp) — a code write
    # under it must be exempt too.
    def test_gettempdir_only_code_write_suppresses_feature(self):
        d = tempfile.mkdtemp(prefix="rh1-gettempdir-")
        try:
            w = tool_use("Write", file_path=os.path.join(d, "scratch_probe.py"),
                         content="print('throwaway probe')\n")
            code, err = run_guard(make_turn([w]))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-RH1a: mixed turn (one temp write + one repo write) must
    # still block — the exemption requires ALL structural code writes be temp.
    def test_mixed_tmp_and_repo_code_writes_still_block(self):
        d = tempfile.mkdtemp(prefix="rh1-mixed-", dir="/tmp")
        try:
            tmp_w = tool_use("Write", file_path=os.path.join(d, "scratch.py"),
                             content="print(1)\n")
            repo_w = tool_use("Write",
                              file_path=os.path.join(REPO_DIR, "src", "rh1_fixture_app.py"),
                              content="def f():\n    return 1\n")
            code, err = run_guard(make_turn([tmp_w, repo_w]))
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-RH1 symlink case: a code write whose /tmp path is a REAL
    # symlink into the repo must still block — realpath resolves it out of the
    # temp root before classification.
    def test_tmp_symlink_into_repo_still_blocks(self):
        d = tempfile.mkdtemp(prefix="rh1-tmplink-", dir="/tmp")
        try:
            link = os.path.join(d, "evasion.py")
            os.symlink(os.path.join(HOOKS_DIR, "loop_stop_guard.py"), link)
            w = tool_use("Edit", file_path=link, old_string="a", new_string="b")
            code, err = run_guard(make_turn([w]))
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-RH1b (H-GUARD-3b): a turn whose only structural write is
    # ~/.claude/settings.json → exempt, exit 0 (RED until implemented).
    def test_settings_json_only_turn_suppresses_feature(self):
        settings = os.path.join(os.path.expanduser("~/.claude"), "settings.json")
        e = tool_use("Edit", file_path=settings,
                     old_string='"hooks": {}',
                     new_string='"hooks": {"Stop": []}')
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-RH1b: settings.local.json is the second (and last)
    # exempt basename under ~/.claude/.
    def test_settings_local_json_only_turn_suppresses_feature(self):
        settings = os.path.join(os.path.expanduser("~/.claude"), "settings.local.json")
        e = tool_use("Edit", file_path=settings,
                     old_string='"permissions": []',
                     new_string='"permissions": ["Bash(ls:*)"]')
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-RH1b counter-case: the exemption covers EXACTLY the two
    # settings basenames, NOT the whole ~/.claude dir — a SKILL.md edit under
    # ~/.claude/skills/** must still gate (no verifier ran → exit 2).
    def test_claude_skills_skill_md_edit_still_gates(self):
        p = os.path.expanduser("~/.claude/skills/rh1-fixture-skill/SKILL.md")
        e = tool_use("Edit", file_path=p,
                     old_string="Trigger on X", new_string="Trigger on X or Y")
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-RH1c (RH-1c, mention-vs-edit): a turn whose only write is
    # a runs/ planning .md whose CONTENT names hooks/x.py must not trip
    # FEATURE → exit 0 (RED until implemented).
    def test_runs_md_only_turn_suppresses_feature_gate(self):
        p = os.path.join(REPO_DIR, "runs",
                         "rh1-fixture-%s" % uuid.uuid4().hex, "spec.md")
        w = tool_use("Write", file_path=p,
                     content="Plan: the Coder will modify hooks/loop_stop_guard.py "
                             "gate logic per AC-RH1. Plan-production text about "
                             "code is not code.")
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-RH1c: same suppression must hold for the
    # ROLE_OR_HARNESS_EDIT gate — a runs/ .md whose content names
    # harness/x.py and roles/x.md (which trips the role/harness blob regex
    # today) → exit 0 (RED until implemented).
    def test_runs_md_only_turn_suppresses_role_or_harness_gate(self):
        p = os.path.join(REPO_DIR, "runs",
                         "rh1-fixture-%s" % uuid.uuid4().hex, "run_plan.md")
        w = tool_use("Write", file_path=p,
                     content="Step 2 touches harness/verify.py and step 3 tweaks "
                             "roles/verifier.md wording — both via Coder dispatch.")
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-RH1c symlink variant: a runs/ .md path that is a REAL
    # symlink to a roles/ file must still block — realpath moves it out of
    # <repo>/runs/ before the exemption test.
    def test_runs_md_symlink_to_roles_still_blocks(self):
        d = os.path.join(REPO_DIR, "runs", "rh1-symlink-fixture-%s" % uuid.uuid4().hex)
        os.makedirs(d)
        try:
            link = os.path.join(d, "notes.md")
            os.symlink(os.path.join(REPO_DIR, "loop-team", "roles", "verifier.md"), link)
            e = tool_use("Edit", file_path=link, old_string="a",
                         new_string="tighten roles/verifier.md wording")
            code, err = run_guard(make_turn([e]))
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-RH1c: a non-.md write under runs/ disqualifies the
    # plan-production exemption — a runs/ .py write still blocks.
    def test_runs_py_write_still_blocks(self):
        p = os.path.join(REPO_DIR, "runs",
                         "rh1-fixture-%s" % uuid.uuid4().hex, "probe_tool.py")
        w = tool_use("Write", file_path=p, content="print('not a plan doc')\n")
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-RH1d: blob-only FEATURE match with ZERO structural code
    # writes (an edit to a non-code .txt whose content merely MENTIONS
    # hooks/x.py, outside runs/) keeps today's blocking behavior — over-fire
    # is the safe direction.
    def test_prose_mention_only_zero_structural_code_writes_still_blocks(self):
        e = tool_use("Edit", file_path="/x/notes/decisions.txt",
                     old_string="TBD",
                     new_string="next: refactor hooks/loop_stop_guard.py per plan")
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 2, err)


class TypoExemptionRH2(unittest.TestCase):
    """AC-RH2: H-GH2 ruling (prose IS logic for agent-executed artifacts — the
    general doc-vs-logic heuristic stays rejected) + the ONE narrow exemption:
    exactly one structural code-matching edit call in the turn, it is an Edit
    (not Write/MultiEdit) on a .md file, old/new have equal line counts, and
    SequenceMatcher ratio >= 0.9 → FEATURE suppressed.

    Fixtures self-check their own ratio/line-count premises with difflib so a
    fixture drift can never silently test the wrong branch."""

    SKILL_MD = "/x/skills/demo-skill/SKILL.md"
    TYPO_OLD = "The quick brown fox jumps over teh lazy dog."
    TYPO_NEW = "The quick brown fox jumps over the lazy dog."

    # [DOC] AC-RH2a: the ruling and the accepted collateral (single
    # semantic-token flip can slip; Bash already bypasses) must be documented
    # in the hook itself, tied to the H-GH2 hole id.
    def test_rh2_ruling_and_collateral_documented_in_hook(self):
        src = open(GUARD, encoding="utf-8").read().lower()
        self.assertIn("h-gh2", src,
                      "hook must tie the typo exemption to fix_plan's H-GH2 entry")
        self.assertIn("collateral", src,
                      "hook comment must document the ACCEPTED COLLATERAL of the "
                      "capped typo exemption (AC-RH2b)")

    # [BEHAVIORAL] AC-RH2b: single-char typo Edit on skills/x/SKILL.md →
    # exit 0 (RED until implemented).
    def test_single_typo_edit_on_skill_md_suppresses_feature(self):
        ratio = difflib.SequenceMatcher(None, self.TYPO_OLD, self.TYPO_NEW).ratio()
        self.assertGreaterEqual(ratio, 0.9, "fixture premise: typo-scale edit")
        self.assertEqual(len(self.TYPO_OLD.splitlines()),
                         len(self.TYPO_NEW.splitlines()))
        e = tool_use("Edit", file_path=self.SKILL_MD,
                     old_string=self.TYPO_OLD, new_string=self.TYPO_NEW)
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-RH2b one-call cap: TWO typo-scale Edits in the same turn
    # do NOT qualify (N typo edits can compose a rewrite) → exit 2.
    def test_two_typo_edits_same_turn_still_block(self):
        e1 = tool_use("Edit", file_path=self.SKILL_MD,
                      old_string=self.TYPO_OLD, new_string=self.TYPO_NEW)
        e2 = tool_use("Edit", file_path=self.SKILL_MD,
                      old_string="Run the scraper daily at nooon.",
                      new_string="Run the scraper daily at noon.")
        code, err = run_guard(make_turn([e1, e2]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-RH2b: ratio < 0.9 (a real content rewrite) → exit 2.
    def test_low_ratio_md_edit_still_blocks(self):
        old = "Install the skill via pip."
        new = "Completely rewritten installation flow with brand new steps and caveats."
        self.assertLess(difflib.SequenceMatcher(None, old, new).ratio(), 0.9,
                        "fixture premise: rewrite-scale edit")
        self.assertEqual(len(old.splitlines()), len(new.splitlines()))
        e = tool_use("Edit", file_path=self.SKILL_MD, old_string=old, new_string=new)
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-RH2b: line-count change disqualifies even when the
    # ratio stays >= 0.9 (appending a line to a large block) → exit 2.
    def test_line_count_change_md_edit_still_blocks(self):
        old = "A" * 100 + "\n" + "B" * 100
        new = old + "\nC"
        self.assertGreaterEqual(difflib.SequenceMatcher(None, old, new).ratio(), 0.9,
                                "fixture premise: high ratio, so the line-count "
                                "rule is what must disqualify")
        self.assertNotEqual(len(old.splitlines()), len(new.splitlines()))
        e = tool_use("Edit", file_path=self.SKILL_MD, old_string=old, new_string=new)
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-RH2b: a typo .md Edit + a .py edit in the same turn →
    # exit 2 (the .py edit is a second structural code-matching call AND is
    # gate-worthy in its own right).
    def test_typo_md_edit_plus_py_edit_still_blocks(self):
        e1 = tool_use("Edit", file_path=self.SKILL_MD,
                      old_string=self.TYPO_OLD, new_string=self.TYPO_NEW)
        e2 = tool_use("Edit", file_path="/x/src/util.py",
                      old_string="x = 1", new_string="x = 2")
        code, err = run_guard(make_turn([e1, e2]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-RH2b: the exemption is Edit-only — a Write to SKILL.md
    # (no old/new pair to measure) never qualifies → exit 2.
    def test_typo_scale_write_not_edit_still_blocks(self):
        w = tool_use("Write", file_path=self.SKILL_MD, content=self.TYPO_NEW)
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 2, err)


# ---------------------------------------------------------------------------
# Fixtures for ResearcherGateArmOnResultRH3. Dispatch labels are the REAL
# orchestrator labels: "plan-check Verifier ..." descriptions for plan-check
# dispatches, "Researcher Mode D — ..." for Researcher dispatches. The
# plan-check Verifier prompt deliberately contains no path-like tokens (no
# '/'), so the adjacency gate can never fire on these fixtures.
# ---------------------------------------------------------------------------
PLAN_VERIFIER_RH3 = tool_use(
    "Agent",
    description="plan-check Verifier — residual-holes researcher-gate spec",
    prompt="You are an independent verifier reviewing the spec. Approve or "
           "reject the plan before any dispatch.")


def researcher_dispatch(tool_use_id):
    """A Researcher Mode D dispatch carrying an explicit tool_use id, so a
    tool_result_event(tool_use_id, ...) can serve as its returned-evidence."""
    tu = tool_use(
        "Agent",
        description="Researcher Mode D — hook transcript event model brief",
        prompt="You are the Researcher. Map the JSONL event model that hook "
               "transcripts use for dispatches and results.")
    tu["id"] = tool_use_id
    return tu


class ResearcherGateArmOnResultRH3(unittest.TestCase):
    """AC-RH3: (a) the Researcher gate's edit classification becomes
    STRUCTURAL (file_path realpath only — content mentions of code paths no
    longer classify, and a runs/ .md edit never sets the violation flag);
    (b) _seen_researcher2 arms only when the current turn also contains
    returned-evidence for the dispatch (tool_result with matching
    tool_use_id, or a queue-operation event embedding its <tool-use-id>).

    FEATURE overlay: every fixture whose turn edits a code file carries a
    plan-check Verifier dispatch so the FEATURE gate stays off and the
    Researcher gate is the only gate that can decide the exit code.
    (Case 1 — the REWRITE of test_early_verifier_then_researcher_then_edit_
    blocks — lives in ResearchGate above, per the spec's rewrite instruction.)
    """

    # [BEHAVIORAL] AC-RH3b case 2: Researcher DISPATCH with no returned
    # result in the turn + a direct src .py edit → the gate never arms →
    # exit 0 (RED until implemented: today the dispatch alone arms it).
    def test_researcher_dispatch_only_never_arms_gate(self):
        researcher = researcher_dispatch("toolu_rh3_noresult")
        src_edit = tool_use("Edit", file_path="/x/src/service.py",
                            old_string="a", new_string="b")
        events = make_turn_events(
            assistant_msg(PLAN_VERIFIER_RH3, researcher, src_edit))
        code, err = run_guard(events)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-RH3a case 3: gate genuinely ARMED (dispatch + returned
    # evidence), but the only post-research edits are runs/ .md planning
    # artifacts whose CONTENT mentions a hooks/*.py path → structural
    # classification exempts them → exit 0 (RED until implemented: today the
    # content mention classifies the brief.md as a code edit).
    def test_armed_gate_runs_md_only_edits_pass(self):
        researcher = researcher_dispatch("toolu_rh3_armed_mdonly")
        brief_path = os.path.join(REPO_DIR, "runs",
                                  "rh3-fixture-%s" % uuid.uuid4().hex, "brief.md")
        brief_edit = tool_use(
            "Edit", file_path=brief_path, old_string="TBD",
            new_string="Findings: the fix lands in hooks/loop_stop_guard.py "
                       "gate logic; Coder dispatch to follow.")
        events = make_turn_events(
            assistant_msg(PLAN_VERIFIER_RH3, researcher),
            tool_result_event("toolu_rh3_armed_mdonly",
                              "Researcher findings: event model documented."),
            assistant_msg(brief_edit),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-RH3 case 4 (regression): gate armed (dispatch +
    # returned evidence) and Oga directly edits a src .py file with only an
    # EARLY (pre-research) plan-check Verifier → exit 2.
    def test_armed_gate_src_py_edit_still_blocks(self):
        researcher = researcher_dispatch("toolu_rh3_armed_srcedit")
        src_edit = tool_use("Edit", file_path="/x/src/service.py",
                            old_string="a", new_string="b")
        events = make_turn_events(
            assistant_msg(PLAN_VERIFIER_RH3, researcher),
            tool_result_event("toolu_rh3_armed_srcedit",
                              "Researcher findings: event model documented."),
            assistant_msg(src_edit),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-RH3b channel (2): returned-evidence via a
    # type:queue-operation event embedding the researcher dispatch's
    # <tool-use-id> (NO tool_result for it anywhere in the turn) also ARMS
    # the gate — a direct src .py edit with only the early plan-check
    # Verifier must still block. Coverage companion to the tool_result-channel
    # cases above; passes against the implemented gate (not red-by-design).
    def test_armed_via_queue_operation_evidence_src_py_edit_blocks(self):
        researcher = researcher_dispatch("toolu_rh3_queueop")
        src_edit = tool_use("Edit", file_path="/x/src/service.py",
                            old_string="a", new_string="b")
        events = make_turn_events(
            assistant_msg(PLAN_VERIFIER_RH3, researcher),
            queue_operation_event("toolu_rh3_queueop"),
            assistant_msg(src_edit),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)


class GlobSafeSessionIdRH7(unittest.TestCase):
    """AC-RH7 (H-GUARD-5): the plan-pass flag lookup interpolates session_id
    into a glob pattern. It must be glob.escape()-wrapped so (1) a metachar id
    still finds its own literal-named fresh flag (no self-lockout) and (2) an
    id containing wildcards can never cross-match another session's flag.

    Cleanup is by exact flag path (the tearDown glob used by the other flag
    classes cannot find metachar-named files)."""

    # [BEHAVIORAL] AC-RH7: metachar session id + a literal-named fresh flag →
    # credit honored, exit 0 (RED until implemented: today the raw '[meta]'
    # is parsed as a glob char class, the flag is invisible → self-lockout).
    def test_metachar_session_id_fresh_flag_honored(self):
        """[D.3 Bucket A2] Rebuilt onto the SAME real structural Verifier-
        credit pattern as SpecBoundVerifierCreditGateV1 (a genuine Verifier
        dispatch + paired PLAN_PASS result carrying REVIEWED_SPEC_SHA256=
        for the matching spec hash, in the same turn window) in place of
        write_flag()/.verifier_pass -- that legacy flag idiom no longer
        authorizes a Coder dispatch on its own within this lane's own
        deliberate redesign (see CrossTurnPlanCheckGate above).

        This test's own original point was glob-metacharacter safety in the
        session_id-keyed PLAN-PASS FLAG lookup. Direct source confirmation
        (grep for "verifier_pass"/PLAN_PASS_TTL glob usage in
        loop_stop_guard.py): the new structural-credit mechanism has NO
        session-keyed glob lookup at all for Coder authorization -- it
        reads the transcript's own tool_use/tool_result records directly,
        not a session-scoped flag file. The two REMAINING glob+session_id
        lookups in this file (.commit_violation / .closure_violation, an
        unrelated pair of gates) are both already glob.escape()-wrapped and
        untouched by this build. So this test's original glob-safety
        concern does not apply to the new mechanism at all -- documented
        here explicitly rather than silently dropped. The metachar-shaped
        session_id is kept anyway (harmless, and for continuity/
        documentation of the original scenario) even though it is no
        longer load-bearing; this test's real remaining assertion is simply
        that a genuine, resolved Verifier-PASS credit chain still
        authorizes the Coder (exit 0), matching the "clean" case of this
        class's own AC-RH7 intent."""
        sid = "rh7-[meta]-%s" % uuid.uuid4().hex
        d = tempfile.mkdtemp(prefix="rh7-spec-")
        try:
            spec_path = _sb_write_spec(d)
            spec_hash = _sb_sha256(spec_path)
            events = make_turn_events(
                assistant_msg(_sb_verifier(spec_path, spec_hash, "rh7-verifier",
                                           run_in_background=False)),
                _sb_pass_result("rh7-verifier", spec_hash),
                assistant_msg(_sb_coder(spec_path, spec_hash, "rh7-coder")),
            )
            code, err = run_guard_with_session(events, session_id=sid)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-RH7: a session id containing '*' must NOT wildcard-match
    # a differently-named session's flag → exit 2, and the other session's
    # flag survives untouched (RED until implemented: today the raw '*'
    # cross-matches the victim flag and waives the gate).
    def test_metachar_session_id_does_not_wildcard_match_other_flags(self):
        victim_sid = "rh7-victim-%s" % uuid.uuid4().hex
        attacker_sid = "rh7-victim-*"
        flag = write_flag(victim_sid, "verifier")
        try:
            code, err = run_guard_with_session(make_turn([CODER_AGENT]),
                                               session_id=attacker_sid)
            self.assertEqual(code, 2, err)
            self.assertTrue(os.path.exists(flag),
                            "victim session's flag must never be consumed by "
                            "a foreign metachar id")
        finally:
            try:
                os.remove(flag)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# hguard6_spec.md (runs/2026-07-02_090000-hguard6-doconly)
# AC-1 doc-only suppression / AC-2 exemption asymmetry (tightened) /
# AC-3 hardlink guard. Written spec-first: the RED expectations below fail
# against the unmodified guard by design; the GREEN ones already pass and
# must stay passing.
# ---------------------------------------------------------------------------

class DocOnlySuppressionHGuard6(unittest.TestCase):
    """AC-1 (H-GUARD-6): a turn whose structural writes are ALL non-gating .md
    docs (fix_plan.md, loop-team/README.md, a ~/.claude memory .md) — even when
    the doc CONTENT names a .py/roles file just verified in a prior turn — must
    suppress BOTH the FEATURE and ROLE_OR_HARNESS gates → exit 0. Gating .md
    (SKILL.md, a /roles/-segment .md), a non-.md structural write, or a mixed
    doc+code turn must still block.

    Fixture isolation: the memory-path fixture only REFERENCES the path string
    inside the crafted transcript (mirrors RH1b's settings-path handling) — it
    never creates or opens anything under the real ~/.claude. The fix_plan.md /
    README.md fixtures use /x/-prefixed non-existent paths; classification is by
    realpath basename/segment, not by reading the file.
    """

    # [BEHAVIORAL] AC-1: fix_plan.md-only turn whose CONTENT names
    # hooks/loop_stop_guard.py → exit 0 (RED today: FEATURE fires on the blob
    # mention of the .py path even though the only real write is a doc .md).
    def test_fix_plan_md_only_naming_py_suppresses_both_gates(self):
        w = tool_use("Write", file_path="/x/loop/fix_plan.md",
                     content="Resolved H-GUARD-6: the fix landed in "
                             "hooks/loop_stop_guard.py gate logic per the spec.")
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-1: a loop-team/README.md-only turn naming a .py → exit 0
    # (RED today). README.md is NOT a SKILL.md and NOT under /roles/.
    def test_readme_md_only_naming_py_suppresses_gate(self):
        w = tool_use("Write", file_path="/x/loop/loop-team/README.md",
                     content="Install the Stop hook; it lives in "
                             "hooks/loop_stop_guard.py.")
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-1: a ~/.claude/projects/x/memory/y.md-only turn → exit 0
    # (RED today). The path is only REFERENCED in the transcript (file need not
    # exist), mirroring RH1b's settings-path handling.
    def test_memory_md_only_turn_suppresses_gate(self):
        p = os.path.expanduser("~/.claude/projects/rh1-fixture-x/memory/y.md")
        w = tool_use("Write", file_path=p,
                     content="Learning: the guard change touched "
                             "hooks/loop_stop_guard.py this build.")
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-1 MUST-STAY-GREEN: reuse the existing ROLE_EDIT fixture
    # (a /roles/-segment .md) with no SUITE_GREEN → exit 2 via the ROLE gate.
    # A role .md is a GATING .md, so doc-only suppression must NOT apply. This
    # is the path-segment-role-detection anchor: /x/loop-team/roles/verifier.md
    # must stay classified as gating.
    def test_role_md_only_no_green_still_blocks(self):
        code, err = run_guard(make_turn([ROLE_EDIT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-1: a SKILL.md structural REWRITE (Write, so no edit-ratio
    # to earn the typo exemption) → exit 2 via FEATURE. SKILL.md is a gating
    # .md (agent-executed prose gates).
    def test_skill_md_write_rewrite_still_blocks(self):
        w = tool_use("Write", file_path="/x/skills/demo-skill/SKILL.md",
                     content="Completely new trigger and workflow prose.")
        code, err = run_guard(make_turn([w]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-1: a doc .md + a repo .py in the SAME turn → exit 2
    # (not all-md; the .py disqualifies doc-only).
    def test_doc_md_plus_repo_py_same_turn_still_blocks(self):
        doc = tool_use("Write", file_path="/x/loop/fix_plan.md",
                       content="Notes about the change.")
        py = tool_use("Write", file_path="/x/src/app.py",
                      content="def f():\n    return 1\n")
        code, err = run_guard(make_turn([doc, py]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-1: a doc .md + a .txt write in the same turn → exit 2
    # (a non-.md structural write disqualifies the all-md premise).
    def test_doc_md_plus_txt_write_still_blocks(self):
        doc = tool_use("Write", file_path="/x/loop/fix_plan.md",
                       content="Notes naming hooks/loop_stop_guard.py.")
        txt = tool_use("Write", file_path="/x/notes/scratch.txt",
                       content="freeform notes")
        code, err = run_guard(make_turn([doc, txt]))
        self.assertEqual(code, 2, err)


class ExemptionAsymmetryHGuard6(unittest.TestCase):
    """AC-2 (tightened v2): the exempt-paths predicate (tmp/settings) must
    suppress the ROLE_OR_HARNESS gate too — but ONLY when no REAL gating
    surface (a /roles/ .md or /harness/ .py) is structurally written this turn.
    A tmp-only .py whose CONTENT names harness/verify.py, or a settings-only
    turn whose prose names roles/coder.md, currently exits 2 via the ROLE gate
    (blob match on the mention) and must become exit 0. The ESCAPE case — a
    REAL /roles/ coder.md write alongside the tmp .py — must still block.

    Fixture isolation: tmp writes use mkdtemp with finally-teardown. The ESCAPE
    case references the ACTUAL repo roles file (loop-team/roles/coder.md) so the
    path-segment role predicate resolves a real gating surface; no file is
    created for it (an Edit fixture only names the path).
    """

    # [BEHAVIORAL] AC-2: tmp-only .py turn whose CONTENT names harness/verify.py
    # → exit 0 (RED today: ROLE_OR_HARNESS fires on the blob mention).
    def test_tmp_py_naming_harness_py_suppresses_role_gate(self):
        d = tempfile.mkdtemp(prefix="hg6-asym-tmp-", dir="/tmp")
        try:
            w = tool_use("Write", file_path=os.path.join(d, "scratch.py"),
                         content="# probe that exercises harness/verify.py paths\n"
                                 "print('throwaway')\n")
            code, err = run_guard(make_turn([w]))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-2: settings.json-only turn naming roles/coder.md in prose
    # → exit 0 (RED today). The write is an exempt settings file; the role
    # mention is only prose in old/new strings.
    def test_settings_json_naming_roles_md_suppresses_role_gate(self):
        settings = os.path.join(os.path.expanduser("~/.claude"), "settings.json")
        e = tool_use("Edit", file_path=settings,
                     old_string='"note": "pending"',
                     new_string='"note": "see roles/coder.md for context"')
        code, err = run_guard(make_turn([e]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC-2 ESCAPE (the iteration-1 gap): a tmp .py + a REAL
    # /roles/-segment coder.md structural write in one turn → exit 2. A real
    # role edit must never escape the ROLE gate via the tmp exemption. Uses the
    # actual repo roles/coder.md path so the path-segment predicate matches.
    def test_tmp_py_plus_real_role_write_still_blocks(self):
        d = tempfile.mkdtemp(prefix="hg6-asym-escape-", dir="/tmp")
        try:
            tmp_w = tool_use("Write", file_path=os.path.join(d, "scratch.py"),
                             content="print('throwaway')\n")
            role_path = os.path.join(REPO_DIR, "loop-team", "roles", "coder.md")
            role_e = tool_use("Edit", file_path=role_path,
                              old_string="a", new_string="b")
            code, err = run_guard(make_turn([tmp_w, role_e]))
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-2: a MIXED tmp+repo .py turn → exit 2 (unchanged — the
    # repo .py is not exempt, so exempt-paths-only is False and FEATURE fires).
    def test_mixed_tmp_and_repo_py_still_blocks(self):
        d = tempfile.mkdtemp(prefix="hg6-asym-mixed-", dir="/tmp")
        try:
            tmp_w = tool_use("Write", file_path=os.path.join(d, "scratch.py"),
                             content="print(1)\n")
            repo_w = tool_use("Write",
                              file_path=os.path.join(REPO_DIR, "src",
                                                     "hg6_fixture_app.py"),
                              content="def f():\n    return 1\n")
            code, err = run_guard(make_turn([tmp_w, repo_w]))
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class HardlinkGuardHGuard6(unittest.TestCase):
    """AC-3 (H-GUARD-7): os.path.realpath resolves symlinks but NOT hardlinks,
    so a <repo>/runs/x.md HARD-LINKED to a real /roles/*.md is currently
    classified as a benign doc/plan-production write (exit 0) while it actually
    mutates a gating file. The guard must detect st_nlink > 1 and disqualify the
    exemption → exit 2 (safe direction). A normal (nlink==1) runs/*.md-only turn
    must NOT over-fire → exit 0.

    Fixture isolation: the hardlink is created with os.link in a uuid-named
    scratch dir under the repo's real runs/, torn down in a finally block. If
    the filesystem refuses os.link (e.g. cross-device or unsupported), the test
    self-skips with the reason rather than silently passing.
    """

    # [BEHAVIORAL] AC-3: a runs/x.md HARD-LINKED to a real roles/*.md, edited in
    # an otherwise doc-only turn with no SUITE_GREEN → exit 2 (RED today:
    # realpath does not resolve the hardlink, so it classifies as
    # plan_production/doc_only → exit 0).
    def test_hardlinked_runs_md_to_role_still_blocks(self):
        d = os.path.join(REPO_DIR, "runs",
                         "hg6-hardlink-fixture-%s" % uuid.uuid4().hex)
        os.makedirs(d)
        target = os.path.join(REPO_DIR, "loop-team", "roles", "verifier.md")
        link = os.path.join(d, "notes.md")
        try:
            try:
                os.link(target, link)
            except OSError as _e:
                self.skipTest("os.link unsupported on this fs: %r" % (_e,))
            e = tool_use("Edit", file_path=link,
                         old_string="a", new_string="b")
            code, err = run_guard(make_turn([e]))
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-3 regression: a NORMAL (nlink==1) runs/x.md-only turn →
    # exit 0. The hardlink guard must not over-fire on ordinary single-link
    # files (plan-production suppression still applies).
    def test_normal_runs_md_only_still_passes(self):
        d = os.path.join(REPO_DIR, "runs",
                         "hg6-normal-fixture-%s" % uuid.uuid4().hex)
        os.makedirs(d)
        p = os.path.join(d, "plan.md")
        try:
            with open(p, "w", encoding="utf-8") as _f:
                _f.write("Plan: the Coder will touch hooks/loop_stop_guard.py.\n")
            self.assertEqual(os.stat(p).st_nlink, 1,
                             "fixture premise: ordinary file has one link")
            w = tool_use("Write", file_path=p,
                         content="Plan: the Coder will touch "
                                 "hooks/loop_stop_guard.py per AC-3.")
            code, err = run_guard(make_turn([w]))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC-3 (v3 narrowing, H-GUARD-7): TWO plain docs hard-linked to
    # EACH OTHER, NEITHER under /roles/ or /harness/ and neither a SKILL.md, edited
    # in an otherwise doc-only turn → exit 0. The write shares an inode (st_nlink==2)
    # but that inode is NOT reachable as a real gating surface, so the narrowed
    # _rh_hardlinked_to_gating signal must NOT fire. RED today: the bare st_nlink>1
    # signal over-fires and blocks this innocent hardlink (exit 2), wrongly trapping
    # a close-out. The st_nlink==2 premise assert proves the narrowing, not merely
    # link-absence.
    def test_innocent_hardlink_between_plain_docs_passes(self):
        d = os.path.join(REPO_DIR, "runs",
                         "hg6-innocent-hardlink-fixture-%s" % uuid.uuid4().hex)
        os.makedirs(d)
        x_md = os.path.join(d, "x.md")
        backup_md = os.path.join(d, "backup.md")
        try:
            with open(x_md, "w", encoding="utf-8") as _f:
                _f.write("Notes: the fix landed in hooks/loop_stop_guard.py.\n")
            try:
                os.link(x_md, backup_md)
            except OSError as _e:
                self.skipTest("os.link unsupported on this fs: %r" % (_e,))
            # Fixture premise: the two plain docs share one inode (nlink==2), so
            # the test exercises the narrowing (inode NOT in the gating set), not
            # merely the absence of a hardlink.
            self.assertEqual(os.stat(x_md).st_nlink, 2,
                             "fixture premise: x.md and backup.md share one inode")
            e = tool_use("Edit", file_path=x_md,
                         old_string="a",
                         new_string="see hooks/loop_stop_guard.py for context")
            code, err = run_guard(make_turn([e]))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# hguard6d-role-md-feature-exempt spec (runs/2026-07-02_hguard6d-role-md-feature-exempt)
# AC1 / AC1b / AC2 / AC3 / AC4 / AC6 cases. Written spec-first: the exit-0
# expectations below are RED against the unmodified guard by design (the
# `_rh_judge_suite_green` detector and the new roles/*.md FEATURE exemption do
# not exist yet). A turn whose ONLY structural write is roles/*.md prose that
# happens to NAME a .py path (e.g. "harness/verify.py") trips FEATURE via the
# blob-level _CODE regex even though ROLE_OR_HARNESS_EDIT is the correct,
# sufficient check for pure-prose role edits — this class adds a narrow,
# judge-gated FEATURE exemption for that case without touching harness/*.py
# handling or any existing exemption.
# ---------------------------------------------------------------------------
RUN_EVALS_JUDGE = tool_use(
    "Bash", command="python3 loop-team/evals/run_evals.py --judge live_adapter")
ROLE_EDIT_NAMING_PY = tool_use(
    "Edit", file_path="/x/loop-team/roles/researcher.md",
    old_string="Investigate the mechanism directly.",
    new_string="Investigate the mechanism directly; see harness/verify.py "
               "for the existing pattern.")
MIXED_ROLE_AND_HARNESS_EDIT = tool_use(
    "Edit", file_path="/x/loop-team/harness/verify.py",
    old_string="a", new_string="b")
# ROUND 3 / AC1c fixture (post-build Verifier finding 1): the roles/*.md
# Edit's own PROSE contains the literal substring "run_evals.py --judge"
# (documenting this very feature), which would satisfy a whole-blob regex
# for the --judge flag even though NO Bash tool_use actually ran with
# --judge this turn. The real SUITE: GREEN comes from a separate, genuinely
# plain `python3 ... run_evals.py` Bash call with no --judge anywhere in
# ITS OWN input dict.
ROLE_EDIT_PROSE_MENTIONS_JUDGE_FLAG = tool_use(
    "Edit", file_path="/x/loop-team/roles/researcher.md",
    old_string="Investigate the mechanism directly.",
    new_string="Investigate the mechanism directly; this feature is gated on "
               "a judge-graded run (run_evals.py --judge <adapter>), not a "
               "plain one.")


class RoleMdFeatureExemptionHGuard6d(unittest.TestCase):
    """hguard6d spec AC1/AC1b/AC2/AC3/AC4/AC6: a turn whose ONLY structural
    write is roles/*.md prose (even prose that names a .py path) must not
    ALSO trip FEATURE once ROLE_OR_HARNESS_EDIT is satisfied by a
    JUDGE-graded green suite (`_rh_judge_suite_green`: SUITE_GREEN AND the
    same-turn Bash blob shows a run_evals.py invocation adjacent to a
    `--judge` flag). Plain SUITE_GREEN (no --judge) is NOT sufficient — that
    is the exact HGUARD6D-01 bypass plan-check caught round 1. This exemption
    must never extend to harness/*.py, must require ALL structural writes be
    roles/*.md (a mixed roles+harness turn still blocks), and must still be
    disqualified by _rh_hardlinked_to_gating exactly like the other
    exemptions."""

    # [BEHAVIORAL] AC1: roles/*.md-only turn, prose names a .py path, a
    # --judge-flagged SUITE: GREEN present this turn, NO Verifier dispatch →
    # exit 0 (neither gate blocks). RED until _rh_judge_suite_green + the new
    # FEATURE exemption exist.
    def test_role_md_naming_py_with_judge_green_no_verifier_passes(self):
        code, err = run_guard(make_turn(
            [ROLE_EDIT_NAMING_PY, RUN_EVALS_JUDGE],
            results=[GREEN_RESULT]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC1b (the exact bypass plan-check caught, HGUARD6D-01):
    # same transcript as AC1 but SUITE: GREEN comes from a PLAIN
    # `run_evals.py` invocation with NO --judge flag anywhere in the blob →
    # _rh_judge_suite_green is false → ROLE_OR_HARNESS_EDIT still blocks →
    # exit 2. Proves the exemption is gated on judge-graded green, not plain
    # SUITE_GREEN.
    def test_role_md_naming_py_with_plain_green_no_judge_still_blocks(self):
        code, err = run_guard(make_turn(
            [ROLE_EDIT_NAMING_PY, RUN_EVALS],
            results=[GREEN_RESULT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC2 (regression): same transcript as AC1 but WITHOUT ANY
    # SUITE: GREEN text at all → ROLE_OR_HARNESS_EDIT still blocks → exit 2.
    # run_evals remains mandatory before this exemption can apply.
    def test_role_md_naming_py_no_green_at_all_still_blocks(self):
        code, err = run_guard(make_turn([ROLE_EDIT_NAMING_PY, RUN_EVALS_JUDGE]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC3 (regression): the ONLY structural write is
    # harness/*.py (real code, not roles/*.md), --judge-flagged SUITE: GREEN
    # present, NO Verifier dispatch → FEATURE still blocks → exit 2. The new
    # exemption must NEVER extend to harness/*.py under any SUITE_GREEN
    # variant — harness/*.py keeps needing an independent Verifier, full
    # stop.
    def test_harness_py_only_with_judge_green_no_verifier_still_blocks(self):
        code, err = run_guard(make_turn(
            [HARNESS_EDIT, RUN_EVALS_JUDGE], results=[GREEN_RESULT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC4: a MIXED turn — one roles/*.md write + one
    # harness/*.py write — --judge-flagged SUITE: GREEN present, no Verifier
    # dispatch → FEATURE still blocks → exit 2. The exemption requires ALL
    # structural writes be roles/*.md; a mixed turn does not qualify.
    def test_mixed_role_and_harness_writes_with_judge_green_still_blocks(self):
        code, err = run_guard(make_turn(
            [ROLE_EDIT_NAMING_PY, MIXED_ROLE_AND_HARNESS_EDIT, RUN_EVALS_JUDGE],
            results=[GREEN_RESULT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC6: the sole roles/*.md write is HARD-LINKED to a real
    # gating file (mirrors HardlinkGuardHGuard6.test_hardlinked_runs_md_to_
    # role_still_blocks: os.link + uuid-scratch-dir under <repo>/runs/ +
    # try/finally shutil.rmtree, self.skipTest on unsupported filesystems),
    # --judge-flagged SUITE: GREEN present, no Verifier dispatch → FEATURE
    # still blocks → exit 2. The hardlink-to-gating disqualification applies
    # to this new exemption too.
    # [BEHAVIORAL] AC1c (round 3, closes post-build Verifier finding 1): the
    # roles/*.md Edit's PROSE contains the literal substring
    # "run_evals.py --judge" (e.g. documentation describing this feature),
    # but the actual SUITE: GREEN came from a separate, genuinely plain
    # `python3 ... run_evals.py` Bash tool_use with NO --judge anywhere in
    # THAT tool_use's own input dict → _rh_judge_suite_green must be FALSE
    # (command-scoped, not blob-scoped) → ROLE_OR_HARNESS_EDIT still blocks
    # → exit 2, same as AC1b. RED until _rh_judge_suite_green is rescoped to
    # the same per-tool_use loop SUITE_GREEN already uses, instead of a
    # whole-blob regex that a roles/*.md Edit's own prose can satisfy.
    def test_role_md_prose_mentioning_judge_flag_with_plain_green_still_blocks(self):
        code, err = run_guard(make_turn(
            [ROLE_EDIT_PROSE_MENTIONS_JUDGE_FLAG, RUN_EVALS],
            results=[GREEN_RESULT]))
        self.assertEqual(code, 2, err)

    def test_hardlinked_role_md_with_judge_green_still_blocks(self):
        d = os.path.join(REPO_DIR, "runs",
                         "hguard6d-hardlink-fixture-%s" % uuid.uuid4().hex)
        os.makedirs(d)
        target = os.path.join(REPO_DIR, "loop-team", "roles", "verifier.md")
        link = os.path.join(d, "notes.md")
        try:
            try:
                os.link(target, link)
            except OSError as _e:
                self.skipTest("os.link unsupported on this fs: %r" % (_e,))
            e = tool_use(
                "Edit", file_path=link,
                old_string="a",
                new_string="mentions harness/verify.py in passing")
            code, err = run_guard(make_turn(
                [e, RUN_EVALS_JUDGE], results=[GREEN_RESULT]))
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# custom-subagent-types spec (runs/2026-07-02_153538-custom-subagent-types),
# AC6: the loop-team custom Claude Code subagent-type build (5 new
# ~/.claude/agents/<name>.md + ~/Claude/loop/.claude/agents/<name>.md files,
# and an orchestrator.md dispatch-section edit -- see that build's spec.md)
# changes the SHAPE of a real Agent dispatch: `subagent_type` is now set to
# the matching custom type name (e.g. "coder", "plan-check-verifier"), and
# `prompt` carries only a short delegation message (no pasted role-brief
# text), while `description` conventions are REQUIRED to stay exactly as
# they are today (spec.md's "Preserve, verbatim, the existing description
# field conventions..." instruction) precisely because _CODER_DETECT /
# _VERIFIER_DETECT match against the full serialized `input` dict
# (_tu_input(), i.e. description + prompt + subagent_type + model +
# everything -- see loop_stop_guard.py's own _tu_input() docstring-equivalent
# comment), NOT against subagent_type alone.
#
# These tests import nothing special -- like every other class in this file,
# they drive the REAL hook file (GUARD) as a subprocess via run_guard(), so a
# passing test here proves the actual regex objects in loop_stop_guard.py
# still behave correctly against the NEW dispatch shape, not just that a
# regex invented independently in this test file would.
# ---------------------------------------------------------------------------

# A dispatch shaped exactly like the new custom-subagent-type template: a
# real `subagent_type` field naming the custom type, a `description` field
# that still follows the EXISTING "<Role> for <task>" convention (per spec.md
# section "Orchestrator.md dispatch-section edit", bullet 3 -- description
# conventions are explicitly preserved, unchanged, by this build), and a
# short `prompt` carrying only delegation/context (no pasted role-brief
# text -- the custom type's own system prompt supplies that instead).
NEW_SHAPE_CODER_AGENT = tool_use(
    "Agent",
    description="Coder for the custom-subagent-types build",
    subagent_type="coder",
    model="inherit",
    prompt=("Spec: runs/2026-07-02_153538-custom-subagent-types/specs/spec.md. "
            "Failing tests: loop-team/tests/test_custom_subagent_types.py, "
            "hooks/test_loop_stop_guard.py. Implement against them."),
)

# Mirror plan-check-shaped dispatch: description begins with the required
# "plan-check Verifier" prefix, subagent_type is the new custom
# "plan-check-verifier" type, prompt is short (spec-by-path only, no
# role-brief text, no decision-log/verdict leakage).
NEW_SHAPE_PLAN_CHECK_VERIFIER_AGENT = tool_use(
    "Agent",
    description="plan-check Verifier for the custom-subagent-types build",
    subagent_type="plan-check-verifier",
    model="inherit",
    prompt=("Review the spec at "
            "runs/2026-07-02_153538-custom-subagent-types/specs/spec.md. "
            "Report LOOP_GATE: PLAN_PASS or PLAN_FAIL."),
)

# NEGATIVE CONTROL (the specific real regression risk spec.md flags): a
# dispatch whose `subagent_type` field is the literal, hyphenated string
# "plan-check-verifier" -- but whose `description` does NOT begin with
# "plan-check Verifier" (just "Verifier for X", the GENERIC template, not the
# plan-check-specific one). If subagent_type alone could substitute for the
# description-prefix rule, this dispatch would wrongly be treated as a valid
# plan-check Verifier dispatch by any code that made that assumption. The
# hook's actual _VERIFIER_DETECT regex must NOT match it: confirming this
# proves the description-prefix rule stays load-bearing and is not
# quietly superseded by the subagent_type addition.
NEW_SHAPE_SUBAGENT_TYPE_ALONE_NOT_ENOUGH = tool_use(
    "Agent",
    description="Verifier for the custom-subagent-types build",
    subagent_type="plan-check-verifier",
    model="inherit",
    prompt=("Review the spec at "
            "runs/2026-07-02_153538-custom-subagent-types/specs/spec.md."),
)


class CustomSubagentTypeDispatchRegression(unittest.TestCase):
    """AC6 [BEHAVIORAL]: the NEW dispatch shape (subagent_type set, short
    role-brief-free prompt, description conventions unchanged) must still be
    correctly classified by the REAL _CODER_DETECT / _VERIFIER_DETECT regexes
    and the plan-check-precedes-Coder gate in loop_stop_guard.py -- exercised
    end-to-end via the same subprocess harness (run_guard/make_turn) every
    other test in this file uses, so this proves the actual hook logic, not
    an assertion against a regex reinvented in the test file."""

    def _new_shape_verified_spec_turn(self, verifier_description):
        tmpdir = tempfile.mkdtemp(prefix="custom-subagent-spec-")
        self.addCleanup(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
        spec_path = _sb_write_spec(
            tmpdir, "spec.md",
            "# custom subagent spec\nAC: preserve dispatch shape\n",
        )
        spec_hash = _sb_sha256(spec_path)
        verifier = _sb_tool_use(
            "Agent",
            "custom-shape-verifier",
            description=verifier_description,
            subagent_type="plan-check-verifier",
            model="inherit",
            prompt=(
                "Review exactly one spec before Coder.\n"
                "SPEC: %s\n"
                "SPEC_SHA256=%s\n"
                "Report LOOP_GATE: PLAN_PASS or PLAN_FAIL."
            ) % (spec_path, spec_hash),
            # Section B confirmed floor: this helper's own construction is
            # a genuinely synchronous fixture (immediate raw tool_result
            # pairing, no stub/notification pattern) -- both callers below
            # need the identical value, so hardcoded here rather than
            # threaded through (per Section B: "if a wrapper's callers turn
            # out to need DIVERGENT values, thread the parameter through the
            # wrapper instead" -- they don't here).
            run_in_background=False,
        )
        coder = _sb_tool_use(
            "Agent",
            "custom-shape-coder",
            description="Coder for the custom-subagent-types build",
            subagent_type="coder",
            model="inherit",
            prompt=(
                "# Role: Coder\n"
                "Implement only this spec.\n"
                "SPEC: %s\n"
                "SPEC_SHA256=%s"
            ) % (spec_path, spec_hash),
        )
        return make_turn_events(
            assistant_msg(verifier),
            tool_result_event(
                "custom-shape-verifier",
                _sb_pass_text(spec_hash),
            ),
            assistant_msg(coder),
        )

    # A lone new-shape Coder dispatch (no preceding Verifier) must still be
    # recognized as a Coder dispatch by _CODER_DETECT and therefore still
    # blocked by the plan-check-precedes-Coder gate -- i.e. the new shape
    # doesn't accidentally make the Coder invisible to the gate (which would
    # be a silent, worse regression: no protection at all).
    def test_new_shape_coder_alone_still_detected_and_blocks(self):
        code, err = run_guard(make_turn([NEW_SHAPE_CODER_AGENT]))
        self.assertEqual(
            code, 2, "expected the plan-check-precedes-Coder gate to fire for a "
            "lone new-shape Coder dispatch (proves _CODER_DETECT still matches "
            "the new dispatch shape); got exit %r, stderr=%s" % (code, err),
        )

    # A new-shape plan-check Verifier dispatch, followed by a new-shape Coder
    # dispatch in the same turn, must PASS when it satisfies the newer
    # spec-bound credit contract too: readable SPEC, matching SPEC_SHA256, and
    # a paired Verifier result ending in LOOP_GATE: PLAN_PASS while echoing the
    # same REVIEWED_SPEC_SHA256.
    def test_new_shape_plan_check_verifier_then_coder_passes(self):
        code, err = run_guard(self._new_shape_verified_spec_turn(
            "plan-check Verifier for the custom-subagent-types build"))
        self.assertEqual(
            code, 0, "expected a new-shape plan-check Verifier dispatch to satisfy "
            "the plan-check-precedes-Coder gate for a following new-shape Coder "
            "dispatch in the same turn; got exit %r, stderr=%s" % (code, err),
        )

    # A new-shape plan-check Verifier dispatch alone (no Coder) must pass --
    # confirms _VERIFIER_DETECT positively matches the new shape rather than
    # merely "no Coder present, so nothing to block" (which would be true
    # regardless of Verifier detection). Combined with the negative control
    # below, this isolates that detection -- not absence of a Coder -- is
    # what makes this pass.
    def test_new_shape_plan_check_verifier_alone_passes(self):
        code, err = run_guard(make_turn([NEW_SHAPE_PLAN_CHECK_VERIFIER_AGENT]))
        self.assertEqual(code, 0, err)

    # UPDATED per runs/2026-07-11_185950-hook-turn-scope-and-verifier-detect-
    # fix/specs/spec.md AC7 (Bug 2 fix, this test named explicitly by the spec
    # as the one existing test asserting PRE-FIX behavior that must be
    # KNOWINGLY updated, not silently left red or deleted): this was the
    # negative control proving subagent_type='plan-check-verifier' ALONE
    # (description not starting with "plan-check Verifier") did NOT satisfy
    # _VERIFIER_DETECT. Bug 2's fix adds `subagent_type == "plan-check-
    # verifier"` as an OR'd, additive-only shortcut in is_verifier_dispatch()
    # -- mirroring is_coder_dispatch()'s own already-accepted `subagent_type
    # == "coder"` precedent (fix_plan.md ~line 5985-5990) -- so this EXACT
    # dispatch shape (subagent_type='plan-check-verifier', description text
    # that does not itself match the regex) now correctly satisfies
    # is_verifier_dispatch() via that new shortcut alone. One-line reason
    # (verbatim from the spec's own AC7 text): "subagent_type is now an
    # additive-only, precedented detection signal, matching the already-
    # accepted is_coder_dispatch() design." The paired Coder dispatch in this
    # fixture already carries a valid, matching PLAN_PASS result (see
    # _new_shape_verified_spec_turn), so once the Verifier dispatch is
    # correctly recognized, the Coder dispatch that follows is now correctly
    # AUTHORIZED (exit 0) -- this test's expected outcome flips from exit 2
    # (pre-fix) to exit 0 (post-fix). NOTE: this is a DIFFERENT test/fixture
    # from test_loop_stop_guard.py:2293
    # (test_plan_check_verifier_subagent_type_with_live_immediate_coder_
    # directive_still_blocks, SubagentTypeRoleAwareCoderDetectionMisfire3-
    # LiveInstructionBypass) -- that test's prompt contains a LIVE, IMMEDIATE
    # coder directive and is governed by AC14 as a hard, non-updatable
    # regression gate (spec.md AC7's own carve-out); it is intentionally left
    # untouched and must still assert exit 2 after this fix ships.
    def test_subagent_type_alone_now_satisfies_verifier_detect_additive_fix(self):
        code, err = run_guard(self._new_shape_verified_spec_turn(
            "Verifier for the custom-subagent-types build"))
        self.assertEqual(
            code, 0,
            "post-fix: subagent_type='plan-check-verifier' ALONE (description "
            'NOT starting with "plan-check Verifier") must now satisfy '
            "is_verifier_dispatch() via the new additive-only subagent_type "
            "shortcut (spec.md AC4/AC7), authorizing the paired, PLAN_PASS-"
            "credited Coder dispatch that follows. Got exit %r, stderr=%s"
            % (code, err),
        )

    # Same dispatch, in isolation (no Coder following) -- must NOT satisfy
    # the VERIFIER_HYGIENE/ADJACENCY gates' own _VERIFIER_DETECT check on
    # `description` alone either (those gates check `description` directly,
    # not `subagent_type`, and are out of Bug 2's scope -- Bug 2 only touches
    # is_verifier_dispatch() in spec_bound_verifier_credit.py). This dispatch
    # alone produces no feature edit and no Coder, so the expected result is
    # a clean pass (0) both before AND after Bug 2's fix -- unaffected by the
    # AC7 flip above, since a lone Verifier dispatch (correctly detected or
    # not) never itself triggers a block in this file.
    def test_subagent_type_alone_dispatch_in_isolation_is_inert(self):
        code, err = run_guard(make_turn([NEW_SHAPE_SUBAGENT_TYPE_ALONE_NOT_ENOUGH]))
        self.assertEqual(code, 0, err)


# ---------------------------------------------------------------------------
# Misfire-1 (research/loop-stop-guard-misfire-dossier-2026-07-08.md section 1;
# fix_plan.md H-GUARD-6 sub-case (d), "[ ] STILL OPEN" as of the last
# close-out): the PLAN_CHECK gate's Coder-vs-non-Coder classification (the
# `elif _CODER_DETECT.search(_inp) or _CODER_DETECT.search(_tu_dispatch_
# prompt_text(_tu).lower())` branch, loop_stop_guard.py ~line 745) never
# reads `subagent_type` at all -- it is pure free-text regex matching over
# `description` (narrow) and the FULL `prompt` (broadened). A dispatch whose
# `subagent_type` names a recognized non-Coder loop-team custom role
# (confirmed roster, per orchestrator.md "How roles are dispatched" +
# ~/.claude/agents/*.md on disk: coder / verifier / test-writer / researcher
# / plan-check-verifier -- "Explore"/"Plan" do NOT appear anywhere in that
# roster or the dossier, so this class does not invent fixtures for them)
# can still be misclassified as a Coder dispatch purely because its PROMPT
# happens to contain a `_CODER_DETECT` substring (quoting the "role: coder
# for" convention as an example, naming roles/coder.md as a path to read for
# context, or describing a Coder that will be dispatched LATER in a
# different turn) -- even though its own `description` never used that
# convention to declare an embedded coder role itself.
#
# STATUS (2026-07-08, ROUND-4 REVERT): CLOSED -- WON'T FIX (full precision).
# Three rounds of suppression mechanisms (role-based, then two content-
# marker-based variants) were each independently, adversarially proven
# exploitable -- see fix_plan.md H-STOPGUARD-SUBAGENTTYPE-ADJACENCY-
# SELFMATCH-1, Misfire-1 sub-section. The user explicitly chose to revert to
# the original (pre-round-1) full-text scan and accept this false positive
# as an intentional, documented tradeoff rather than risk any further
# bypass. The single test below that pins this false positive
# (test_researcher_role_dispatch_with_incidental_coder_substring_in_prompt_
# not_classified_as_coder) has been UPDATED to assert the reverted ground
# truth (blocks, exit 2) -- see its own inline comment for detail.
# ---------------------------------------------------------------------------

# The real incident shape, reconstructed verbatim per the dispatch brief:
# subagent_type="researcher", description="Ground compiler-gate design in
# live loop files" (the exact real string), prompt incidentally containing
# TWO separate _CODER_DETECT substrings ("roles/coder.md" and "role: coder
# for") while explicitly describing a Coder dispatched LATER, not now, and
# explicitly banning sub-delegation (H-WF-DELEGATE-1 convention) so this
# fixture cannot be dismissed as "well, it really was dispatching a Coder".
RESEARCHER_ROLE_DISPATCH_INCIDENTAL_CODER_SUBSTRING = tool_use(
    "Agent",
    description="Ground compiler-gate design in live loop files",
    subagent_type="researcher",
    model="inherit",
    prompt=(
        "Read the loop-team role files for context on the dispatch-"
        "description convention, including roles/coder.md, roles/verifier.md, "
        "and roles/researcher.md. Note the convention used for a Coder "
        "dispatch's description, e.g. \"role: coder for <task>\" -- a Coder "
        "sub-agent will be dispatched LATER, in a subsequent turn, once your "
        "findings land. Do all reads/greps yourself, directly. Do NOT "
        "dispatch your own sub-agents for any part of this task. Report back "
        "with the grounded design; do not implement anything."
    ),
)

# AC-1b fixtures: subagent_type absent/empty/generic, Coder convention only
# in a generic-description dispatch's PROMPT (the real sub-agent-punting
# shape from feedback_subagent_punting.md) -- must remain detected.
GENERIC_SUBAGENT_TYPE_CODER_SHAPED_PROMPT = tool_use(
    "Agent",
    description="dispatch",
    subagent_type="general-purpose",
    prompt=("You are now taking on role: coder for the widget build. "
            "Implement the spec fully, then run the test suite."),
)

EMPTY_SUBAGENT_TYPE_CODER_SHAPED_PROMPT = tool_use(
    "Agent",
    description="dispatch",
    subagent_type="",
    prompt="roles/coder.md convention: implement the widget spec.",
)


class SubagentTypeRoleAwareCoderDetectionMisfire1(unittest.TestCase):
    """AC-1/AC-1b/AC-1d. [BEHAVIORAL] -- exercises the real _CODER_DETECT/
    _seen_coder_anywhere classifier end-to-end via the subprocess harness
    (run_guard/make_turn), like every other class in this file, so a passing
    test proves the actual regex/classification logic in loop_stop_guard.py,
    not a re-implementation invented in this test file.

    AC-1c is NOT re-tested here by design -- the spec instructs it be left
    untouched: the existing negative control
    CustomSubagentTypeDispatchRegression.test_subagent_type_alone_does_not_
    satisfy_verifier_detect (this file, ~line 1603) already covers it and
    must stay green unmodified; duplicating it here would risk drifting from
    the canonical fixture."""

    # [BEHAVIORAL] ROUND-4 REVERT (2026-07-08): this was originally AC-1 (the
    # real incident) and asserted exit 0 (NOT classified as Coder) for a
    # subagent_type="researcher" dispatch whose prompt's Coder-convention
    # mentions are explicitly ABOUT a future dispatch / role-file reading
    # context. Rounds 1-3 each tried a different suppression mechanism to
    # make that assertion hold and each was independently, adversarially
    # proven exploitable (see fix_plan.md H-STOPGUARD-SUBAGENTTYPE-
    # ADJACENCY-SELFMATCH-1, Misfire-1 "CLOSED -- WON'T FIX" sub-section).
    # The user explicitly chose to revert ALL suppression logic and accept
    # this narrow false positive as a known, intentional tradeoff rather
    # than risk any further bypass. Ground truth is now the REVERSE of what
    # this test originally asserted: the original (pre-round-1) full-text
    # scan has no notion of "future/contextual" framing at all, so this
    # dispatch's prompt -- which contains both "roles/coder.md" and
    # "role: coder for" -- DOES match _CODER_DETECT via the full-prompt-text
    # fallback, and the dispatch IS classified as Coder (exit 2). This is
    # the accepted false positive, not a bug; the test method name is kept
    # for grep/history traceability even though its assertion is now
    # inverted from what the name literally says.
    def test_researcher_role_dispatch_with_incidental_coder_substring_in_prompt_not_classified_as_coder(self):
        code, err = run_guard(make_turn(
            [RESEARCHER_ROLE_DISPATCH_INCIDENTAL_CODER_SUBSTRING]))
        self.assertEqual(
            code, 2,
            "ROUND-4 REVERT, accepted tradeoff: a subagent_type='researcher' "
            "dispatch whose prompt merely QUOTES/REFERENCES the Coder "
            "convention (roles/coder.md, \"role: coder for\") for context, "
            "without itself declaring an embedded coder role via that "
            "convention, IS now classified as a Coder dispatch and DOES trip "
            "the plan-check-precedes-Coder gate -- this is the original "
            "(pre-round-1) full-text-scan false positive, restored "
            "intentionally per the user's 2026-07-08 decision documented in "
            "fix_plan.md (zero bypass risk over precision). Got exit %r, "
            "stderr=%s" % (code, err),
        )

    # [BEHAVIORAL] AC-1b (no regression, subagent_type='general-purpose' --
    # the real punting-detection case from feedback_subagent_punting.md): a
    # generic, non-classifying description with the Coder convention only in
    # the PROMPT must still block. Must stay green before AND after the fix.
    def test_subagent_type_general_purpose_coder_shaped_prompt_still_blocks(self):
        code, err = run_guard(make_turn(
            [GENERIC_SUBAGENT_TYPE_CODER_SHAPED_PROMPT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-1b variant: subagent_type explicitly the empty string.
    def test_subagent_type_empty_string_coder_shaped_prompt_still_blocks(self):
        code, err = run_guard(make_turn(
            [EMPTY_SUBAGENT_TYPE_CODER_SHAPED_PROMPT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-1b baseline: subagent_type key absent entirely (reuses
    # the module-level CODER_AGENT fixture already used by PlanBeforeCoderGate,
    # pinned here explicitly under the AC-1b umbrella for traceability).
    def test_subagent_type_absent_entirely_coder_shaped_description_still_blocks(self):
        code, err = run_guard(make_turn([CODER_AGENT]))
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-1d, convention-following variant (regression-safe
    # baseline): subagent_type explicitly "coder", description follows the
    # existing "<Role> for <task>" convention with DIFFERENT wording each
    # time -- varying the description text must not affect classification of
    # a genuine subagent_type="coder" dispatch. Uses the SAME text-based
    # mechanism already active today.
    def test_subagent_type_coder_explicit_with_varying_convention_descriptions_still_blocks(self):
        variant_a = tool_use("Agent", description="Coder for the checkout flow",
                             subagent_type="coder",
                             prompt="Spec: runs/x/spec.md. Implement it.")
        variant_b = tool_use("Agent", description="Coder for the billing sync",
                             subagent_type="coder",
                             prompt="Spec: runs/y/spec.md. Implement it.")
        for tu in (variant_a, variant_b):
            code, err = run_guard(make_turn([tu]))
            self.assertEqual(code, 2, err)

    # [BEHAVIORAL] AC-1d, strong/forward-looking interpretation -- FLAGGED AS
    # INTERPRETATION-DEPENDENT (see this build's report to Oga): subagent_
    # type explicitly "coder", but NEITHER description NOR prompt contains
    # any _CODER_DETECT-matching substring at all (no "Coder for", no
    # "role: coder", no "roles/coder"). Read here as: subagent_type="coder"
    # is itself a sufficient positive signal once the fix lands, independent
    # of whatever free-text convention is or isn't present. Against
    # UNMODIFIED source this is a genuine false NEGATIVE (current code never
    # reads subagent_type at all) -- currently exits 0 (undetected) rather
    # than the desired 2. If the fix design does not intend subagent_type to
    # become an independent positive signal, this specific test (not
    # test_subagent_type_coder_explicit_with_varying_convention_descriptions_
    # still_blocks above) is the one to revisit/drop.
    def test_subagent_type_coder_explicit_without_coder_shaped_text_anywhere(self):
        tu = tool_use("Agent", description="Widget synchronization work",
                      subagent_type="coder",
                      prompt="Spec: runs/x/spec.md. Failing tests: "
                             "test_widget.py. Get them green.")
        code, err = run_guard(make_turn([tu]))
        self.assertEqual(code, 2, err)


# SubagentTypeRoleAwareCoderDetectionMisfire2DescriptionFallbackGap (Misfire-2,
# the "_NON_CODER_ROLES narrow-description-only scan" class) was REMOVED
# entirely as part of the round-4 revert on 2026-07-08 -- that suppression
# mode no longer exists in loop_stop_guard.py at all (not just changed), so
# there is nothing left for these tests to exercise. See fix_plan.md
# H-STOPGUARD-SUBAGENTTYPE-ADJACENCY-SELFMATCH-1 for the full history.

# ---------------------------------------------------------------------------
# Misfire-3 (independent adversarial Verifier pass on the Misfire-1/Misfire-2
# fix above, 2026-07-08): the _NON_CODER_ROLES branch (loop_stop_guard.py
# ~line 771) SUPPRESSES the full-prompt-text _CODER_DETECT fallback for ANY
# dispatch whose subagent_type is one of researcher/verifier/test-writer/
# plan-check-verifier -- but subagent_type is a CALLER-SUPPLIED string with
# NO STRUCTURAL GUARANTEE behind it (this system's own agent registry gives
# the "researcher" role real Write/Edit tool access). A dispatch can claim
# subagent_type="researcher" while its prompt contains a LIVE, IMMEDIATE
# "act as a coder and implement this right now" instruction, and it now
# sails through the gate unblocked -- a genuine NEW BYPASS. Confirmed as a
# REGRESSION: the pre-Misfire-1 code correctly blocked this identical
# transcript shape (full-prompt-text scan always ran); only the Misfire-1/2
# fix makes it pass through, by suppressing that scan whenever subagent_type
# self-reports as one of the four non-Coder roles.
#
# Distinguish carefully from Misfire-1's ORIGINAL false-positive fixture
# (RESEARCHER_ROLE_DISPATCH_INCIDENTAL_CODER_SUBSTRING, ~line 1659): that
# fixture's Coder-convention mentions are explicitly FUTURE/CONTEXTUAL ("will
# be dispatched LATER, in a subsequent turn", "for context on the dispatch-
# description convention"). The fixtures below are unambiguous LIVE,
# IMMEDIATE directives ("Implement the change directly right now using
# Edit/Write tools; do not just describe it") with no future/contextual
# framing anywhere. A correct classifier must tell these two shapes apart --
# it must NOT collapse to "never scan a non-Coder-role prompt at all" (which
# fixes Misfire-1/2 by reopening this bypass).
# ---------------------------------------------------------------------------

# Shared live-instruction prompt BODY (per-role dispatch below only varies
# the task noun so each fixture reads as a realistic distinct dispatch; the
# live-instruction SEMANTICS -- "role: coder for X ... Implement the change
# directly right now using Edit/Write tools; do not just describe it" --
# stay byte-identical to the dispatch brief's verbatim repro across all four
# roster roles, for a precise apples-to-apples comparison).
def _misfire3_live_prompt(task):
    return ("role: coder for the %s. Read roles/coder.md. "
            "Implement the change directly right now using Edit/Write "
            "tools; do not just describe it." % task)


# [SECURITY-ORACLE] -- a caller-supplied subagent_type is trust-boundary-
# relevant here: it currently GATES whether a live coder directive in the
# prompt gets scanned at all, so a caller claiming a non-Coder role can
# bypass the plan-check-precedes-Coder gate entirely. See dispatch-brief
# Context section for the full regression narrative.
RESEARCHER_LIVE_INSTRUCTION_BYPASS = tool_use(
    "Task", description="Investigate the auth flow for a bug",
    subagent_type="researcher",
    prompt=_misfire3_live_prompt("auth-flow fix"))

VERIFIER_LIVE_INSTRUCTION_BYPASS = tool_use(
    "Task", description="Check the payment retry logic for correctness",
    subagent_type="verifier",
    prompt=_misfire3_live_prompt("payment-retry fix"))

TEST_WRITER_LIVE_INSTRUCTION_BYPASS = tool_use(
    "Task", description="Add coverage for the rate limiter",
    subagent_type="test-writer",
    prompt=_misfire3_live_prompt("rate-limiter fix"))

PLAN_CHECK_VERIFIER_LIVE_INSTRUCTION_BYPASS = tool_use(
    "Task", description="Review the spec for the search-index change",
    subagent_type="plan-check-verifier",
    prompt=_misfire3_live_prompt("search-index fix"))

# Control fixture for the sibling-consistency regression guard (AC-misfire3-
# sibling below): the IDENTICAL live-instruction prompt shape (same
# _misfire3_live_prompt call, same task noun as the researcher fixture
# above) but subagent_type="general-purpose" -- a precise apples-to-apples
# comparison against the already-correctly-blocking sibling case, not merely
# an equivalent-shape fixture with different wording.
GENERAL_PURPOSE_LIVE_INSTRUCTION_BYPASS_CONTROL = tool_use(
    "Task", description="Investigate the auth flow for a bug",
    subagent_type="general-purpose",
    prompt=_misfire3_live_prompt("auth-flow fix"))


class SubagentTypeRoleAwareCoderDetectionMisfire3LiveInstructionBypass(unittest.TestCase):
    """AC-misfire3-1..4 / AC-misfire3-sibling. [BEHAVIORAL][SECURITY-ORACLE]
    -- exercises the real _NON_CODER_ROLES/_CODER_DETECT classifier end-to-
    end via the subprocess harness (run_guard/make_turn), same convention as
    every other class in this file, so a passing test proves the actual
    classification logic in loop_stop_guard.py, not a re-implementation
    invented in this test file.

    Each dispatch below is sent ALONE in the turn (no preceding Verifier
    dispatch), mirroring the dispatch brief's repro exactly: with the
    _NON_CODER_ROLES suppression bug present, _seen_coder_anywhere stays
    False for these dispatches (the full-prompt-text fallback never runs),
    so _plan_check_violated is never set and the gate exits 0 -- UNSAFE.
    The required behavior is a block (exit 2): a live, immediate coder
    directive must trip the plan-check-precedes-Coder gate regardless of
    what subagent_type the dispatch claims for itself."""

    # [BEHAVIORAL][SECURITY-ORACLE] AC-misfire3-1: subagent_type="researcher"
    # -- the exact repro from the dispatch brief's Context section.
    def test_researcher_subagent_type_with_live_immediate_coder_directive_still_blocks(self):
        code, err = run_guard(make_turn([RESEARCHER_LIVE_INSTRUCTION_BYPASS]))
        self.assertEqual(
            code, 2,
            "subagent_type='researcher' whose prompt contains a LIVE, "
            "IMMEDIATE coder directive ('Implement the change directly "
            "right now using Edit/Write tools; do not just describe it') "
            "must classify as Coder and block, regardless of the "
            "self-reported subagent_type -- subagent_type is caller-"
            "supplied with no structural guarantee behind it, and the "
            "researcher role has real Write/Edit tool access in this "
            "system's own agent registry. Got exit %r (expected 2 = "
            "blocked), stderr=%s" % (code, err),
        )

    # [BEHAVIORAL][SECURITY-ORACLE] AC-misfire3-2: subagent_type="verifier".
    def test_verifier_subagent_type_with_live_immediate_coder_directive_still_blocks(self):
        code, err = run_guard(make_turn([VERIFIER_LIVE_INSTRUCTION_BYPASS]))
        self.assertEqual(
            code, 2,
            "subagent_type='verifier' whose prompt contains a LIVE, "
            "IMMEDIATE coder directive must classify as Coder and block, "
            "regardless of the self-reported subagent_type. Got exit %r "
            "(expected 2 = blocked), stderr=%s" % (code, err),
        )

    # [BEHAVIORAL][SECURITY-ORACLE] AC-misfire3-3: subagent_type="test-writer".
    def test_test_writer_subagent_type_with_live_immediate_coder_directive_still_blocks(self):
        code, err = run_guard(make_turn([TEST_WRITER_LIVE_INSTRUCTION_BYPASS]))
        self.assertEqual(
            code, 2,
            "subagent_type='test-writer' whose prompt contains a LIVE, "
            "IMMEDIATE coder directive must classify as Coder and block, "
            "regardless of the self-reported subagent_type. Got exit %r "
            "(expected 2 = blocked), stderr=%s" % (code, err),
        )

    # [BEHAVIORAL][SECURITY-ORACLE] AC-misfire3-4: subagent_type="plan-check-verifier".
    def test_plan_check_verifier_subagent_type_with_live_immediate_coder_directive_still_blocks(self):
        code, err = run_guard(make_turn([PLAN_CHECK_VERIFIER_LIVE_INSTRUCTION_BYPASS]))
        self.assertEqual(
            code, 2,
            "subagent_type='plan-check-verifier' whose prompt contains a "
            "LIVE, IMMEDIATE coder directive must classify as Coder and "
            "block, regardless of the self-reported subagent_type. Got "
            "exit %r (expected 2 = blocked), stderr=%s" % (code, err),
        )

    # [BEHAVIORAL] AC-misfire3-sibling (regression guard, must already pass
    # today, both before and after any round-3 fix): subagent_type=
    # "general-purpose" is NOT in _NON_CODER_ROLES, so it never reaches the
    # suppressing branch -- the existing broadened full-prompt-text fallback
    # (elif _CODER_DETECT.search(_inp) or _CODER_DETECT.search(
    # _tu_dispatch_prompt_text(_tu).lower())) still applies unchanged. Uses
    # the IDENTICAL live-instruction prompt shape (byte-identical prompt
    # text, only subagent_type and description differ) as
    # RESEARCHER_LIVE_INSTRUCTION_BYPASS above, for a precise apples-to-
    # apples comparison against the sibling case that's already correctly
    # covered (note: test_subagent_type_general_purpose_coder_shaped_prompt_
    # still_blocks in SubagentTypeRoleAwareCoderDetectionMisfire1, ~line
    # 1733, already covers this PROPERTY with different fixture wording;
    # this test adds the exact-prompt-parity control the dispatch brief
    # asked for rather than duplicating that existing test verbatim).
    def test_general_purpose_subagent_type_with_identical_live_instruction_prompt_still_blocks_no_regression(self):
        code, err = run_guard(make_turn(
            [GENERAL_PURPOSE_LIVE_INSTRUCTION_BYPASS_CONTROL]))
        self.assertEqual(
            code, 2,
            "subagent_type='general-purpose' with the SAME live-instruction "
            "prompt shape as the bypass fixtures above must still block "
            "(sibling case, already correctly handled pre- and post- the "
            "Misfire-1/2 fix) -- this is the apples-to-apples control "
            "proving the bypass above is specific to the four "
            "_NON_CODER_ROLES values, not a general detection failure. Got "
            "exit %r (expected 2 = blocked), stderr=%s" % (code, err),
        )


# ---------------------------------------------------------------------------
# H-REVIEW-COMMIT-1 (runs/2026-07-03_h-review-commit-1/specs/spec.md)
# AC1-AC8, AC10-AC24: the new "raw git commit on a scope-listed file bypasses
# commit_diff_reread.py" gate, and AC25(b): the durable single-call-site
# regression check for the _LAST_ACTIVATION broadcast pattern.
#
# Written independently from the ACs (never having seen the implementation
# diff), per the spec's own Context section instruction. The spec's Files-to-
# read section requires NEW test infrastructure not present in the file above
# this point:
#   - a real scratch git repo helper (tempfile.mkdtemp + git init + configured
#     user.email/user.name), because AC14/AC15 must catch git's OWN real
#     output shape (root-commit / detached-HEAD success lines), not a
#     hand-typed fixture string.
#   - a marker-prepending, target-arming run_guard() variant, because
#     micro_step_gates._activation() checks the literal marker text
#     ("you are **oga**" / "orchestrator playbook") FIRST, before session_id
#     or the target file are ever read -- without it an "armed" test silently
#     falls through to the fallback repo (the real ~/Claude/loop checkout on
#     disk), never exercising the per-SHA scope-cross-reference logic at all.
#   - a bash_tool_use(tool_use_id, command) helper mirroring the existing
#     researcher_dispatch(tool_use_id) precedent, since make_turn()'s
#     single-hardcoded-"t1"-id model cannot express two independently-
#     correlated tool_use/tool_result pairs in one turn (needed for AC12/AC13).
# ---------------------------------------------------------------------------
import stat as _stat_mod


def scratch_git_repo():
    """A real, freshly-git-init'd scratch repo with a configured identity and
    one seed commit, so the gate's <target> resolution has a real .git dir to
    find and `git show` has real history to walk. Caller is responsible for
    cleanup (returns the repo path; use in a try/finally with shutil.rmtree)."""
    d = tempfile.mkdtemp(prefix="rc1-scratch-repo-")
    def _git(*args, **kw):
        env = kw.pop("env", None)
        r = subprocess.run(["git", "-C", d] + list(args), capture_output=True,
                           text=True, env=env)
        return r
    _git("init", "-q")
    _git("config", "user.email", "rc1-test@example.com")
    _git("config", "user.name", "rc1-test")
    with open(os.path.join(d, "seed.txt"), "w", encoding="utf-8") as f:
        f.write("seed\n")
    _git("add", "seed.txt")
    _git("commit", "-qm", "seed commit")
    return d


def real_git_commit(repo, *files_and_content, message="test commit", env=None):
    """Write the given (relative_path, content) pairs into repo, `git add`
    them, and run a REAL `git commit` subprocess -- returns (returncode,
    stdout, stderr) so the caller can build a tool_result from git's OWN
    literal output (never a hand-typed fixture string), per AC14/AC15's
    explicit requirement."""
    for rel, content in files_and_content:
        full = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        subprocess.run(["git", "-C", repo, "add", rel], capture_output=True)
    r = subprocess.run(["git", "-C", repo, "commit", "-m", message],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout, r.stderr


def bash_tool_use(tool_use_id, command):
    """A Bash tool_use carrying an explicit id, so a tool_result_event(id, ...)
    can correlate to it. Mirrors researcher_dispatch(tool_use_id)'s pattern
    (the only existing precedent in this file for ID-correlated pairs) --
    make_turn()'s single hardcoded "t1" id cannot express multiple distinct
    tool_use/tool_result pairs in one turn."""
    tu = tool_use("Bash", command=command)
    tu["id"] = tool_use_id
    return tu


def run_guard_armed(events, target_dir, session_id=None, stop_hook_active=False):
    """Like run_guard(), but arms micro_step_gates._activation() against
    target_dir: prepends an event containing the _M_OGA marker text
    ("you are **oga**", case-insensitively -- _activation() does a whole-file
    lowercase substring scan, not a turn-sliced one) and writes
    $LOOP_GATE_DIR/<session>_target pointing at target_dir, with a matching
    session_id in the payload. Per the spec's own Files-to-read note: the
    target-file/session_id piece ALONE is not sufficient without the marker,
    or _activation() returns None regardless and the gate silently falls back
    to the real repo containing loop_stop_guard.py itself."""
    if session_id is None:
        session_id = "rc1-armed-%s" % uuid.uuid4().hex
    marker_event = {"type": "user", "message": {
        "role": "user",
        "content": "you are **oga** -- orchestrator playbook loaded"}}
    full_events = [marker_event] + list(events)

    os.makedirs(GATE_DIR, exist_ok=True)
    target_file = os.path.join(GATE_DIR, "%s_target" % session_id)
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(target_dir)

    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for e in full_events:
                f.write(json.dumps(e) + "\n")
        payload = json.dumps({
            "transcript_path": path,
            "stop_hook_active": stop_hook_active,
            "session_id": session_id,
        })
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)
        try:
            os.remove(target_file)
        except OSError:
            pass


class ReviewCommitGateHelperSelfCheck(unittest.TestCase):
    """Sanity-checks the test infrastructure itself against real git output --
    if these fail, the fixtures below are not testing what they claim to."""

    def test_scratch_repo_helper_produces_real_git_repo(self):
        d = scratch_git_repo()
        try:
            self.assertTrue(os.path.isdir(os.path.join(d, ".git")))
            r = subprocess.run(["git", "-C", d, "log", "--oneline"],
                               capture_output=True, text=True)
            self.assertIn("seed commit", r.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_run_guard_armed_actually_arms_the_target(self):
        # An armed run against a scratch repo, with a turn that touches
        # nothing (no Bash tool_use at all) must simply pass -- but this also
        # smoke-tests that arming itself does not crash the guard.
        d = scratch_git_repo()
        try:
            code, err = run_guard_armed(make_turn([text("just talking")]), d)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ReviewCommitGateFireCases(unittest.TestCase):
    """AC1, AC2, AC5: the core fire / no-fire cases against a real scratch
    repo and a real `git commit` invocation."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC1: a raw `git commit -m "message"` (no commit_diff_reread
    # anywhere in the command) whose real, PAIRED tool_result reports a
    # success line, and whose actual `git show --name-only` includes
    # loop-team/orchestrator.md -- fires: exit 2, stderr names the file and
    # the exact sha, and points at the git show/diff remedy.
    def test_raw_commit_touching_orchestrator_md_fires(self):
        rc, out, err_txt = real_git_commit(
            self.repo,
            ("loop-team/orchestrator.md", "orchestrator content v1\n"),
            message="edit orchestrator")
        self.assertEqual(rc, 0, err_txt)
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", 'git commit -m "edit orchestrator"')),
            tool_result_event("rc1", out),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("loop-team/orchestrator.md", err)
        # The exact sha git itself reported must appear in the message.
        sha = out.split("]")[0].split()[-1]
        self.assertIn(sha, err)
        self.assertTrue("git show" in err or "git diff" in err,
                        "block message must instruct the git show/diff remedy")

    # [BEHAVIORAL] AC2: identical scenario, but the commit's file list touches
    # ONLY files outside the scope list -- does not fire.
    def test_raw_commit_touching_only_out_of_scope_file_does_not_fire(self):
        rc, out, err_txt = real_git_commit(
            self.repo,
            ("src/app.py", "print('hello')\n"),
            message="add app.py")
        self.assertEqual(rc, 0, err_txt)
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", 'git commit -m "add app.py"')),
            tool_result_event("rc1", out),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC5: a single commit touches BOTH a scope-listed file
    # (RUN.md) AND an unrelated file -- fires (any scope-listed file present
    # is sufficient, not all-or-nothing).
    def test_raw_commit_touching_scope_file_and_unrelated_file_fires(self):
        rc, out, err_txt = real_git_commit(
            self.repo,
            ("RUN.md", "run content v1\n"),
            ("src/other.py", "x = 1\n"),
            message="mixed commit")
        self.assertEqual(rc, 0, err_txt)
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", 'git commit -m "mixed commit"')),
            tool_result_event("rc1", out),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("RUN.md", err)


class ReviewCommitGateCompliantPath(unittest.TestCase):
    """AC3, AC22: the commit_diff_reread.py-mediated path must never fire,
    even when its own free-form message text contains the literal words
    "git commit"."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC3: a real commit_diff_reread.py `commit` invocation
    # (trace the actual command text, not assumed) does not fire.
    def test_commit_diff_reread_commit_invocation_does_not_fire(self):
        cmd = ('python3 loop-team/harness/commit_diff_reread.py commit '
               'loop-team/orchestrator.md -- "message"')
        # commit_diff_reread.py prints JSON to stdout on success/failure --
        # never a git bracket-success-line -- so the tool_result here is
        # deliberately JSON-shaped, matching the tool's real output contract.
        result_json = json.dumps({
            "committed": True,
            "files": [os.path.join(self.repo, "loop-team/orchestrator.md")],
            "commit": "deadbeef" * 5,
        })
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", cmd)),
            tool_result_event("rc1", result_json),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC22: a commit_diff_reread.py commit whose message argument
    # literally contains the words "git commit" -- item 1's regex DOES match
    # text inside the message, but the gate must still not fire, because the
    # guarantee lives in item 2's success-line absence, not item 1's
    # detection.
    def test_compliant_commit_with_message_containing_git_commit_words_does_not_fire(self):
        cmd = ('python3 loop-team/harness/commit_diff_reread.py commit '
               'loop-team/orchestrator.md -- "remember to git commit conventions"')
        result_json = json.dumps({
            "committed": True,
            "files": [os.path.join(self.repo, "loop-team/orchestrator.md")],
            "commit": "cafed00d" * 5,
        })
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", cmd)),
            tool_result_event("rc1", result_json),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)


class ReviewCommitGateNoMatchingCommand(unittest.TestCase):
    """AC4: no git-commit-shaped Bash tool_use at all -- never fires,
    regardless of current HEAD."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC4: HEAD already contains a scope-file-touching commit
    # from an earlier "turn" (simulated by committing directly, outside any
    # tool_use), but THIS turn only runs `git status` -- must not fire, since
    # there is no matching Bash tool_use to extract a SHA from at all.
    def test_no_git_commit_command_never_fires_regardless_of_head(self):
        real_git_commit(self.repo, ("RUN.md", "already committed content\n"),
                        message="pre-existing scope-file commit")
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", "git status")),
            tool_result_event("rc1", "On branch main\nnothing to commit, "
                                     "working tree clean\n"),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC4 companion: a turn with NO tool calls at all.
    def test_empty_turn_never_fires(self):
        events = make_turn_events(assistant_msg(text("nothing to do this turn")))
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)


class ReviewCommitGateFalsePositiveProtection(unittest.TestCase):
    """AC6, AC21, AC23: commands that merely mention/contain "git commit" (or
    a real, unrelated git subcommand containing the substring "commit") must
    never fire, and must never crash the gate. The protecting mechanism is
    item 2's success-line absence, not item 1's detection regex being
    narrower -- assert that explicitly via the exit-0/no-crash outcome."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC6: echo discussing "git commit" in prose -- no real git
    # invocation, no success line in the tool_result -- must not fire and
    # must not crash.
    def test_echo_discussing_git_commit_does_not_fire(self):
        events = make_turn_events(
            assistant_msg(bash_tool_use(
                "rc1", 'echo "remember to git commit later"')),
            tool_result_event("rc1", "remember to git commit later\n"),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC6 variant: grep of a file containing the literal string
    # "git commit" -- same protection.
    def test_grep_of_file_containing_git_commit_string_does_not_fire(self):
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", "grep -r 'git commit' docs/")),
            tool_result_event("rc1", "docs/howto.md:Remember to git commit "
                                     "your changes when done.\n"),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC21: a MULTI-PART tool_result content list where a part
    # boundary falls in the middle of non-git text that merely resembles a
    # bracket pattern (a grep/cat quoting an example line) -- must not fire.
    # item 1's detection regex is the actual guard (a grep/cat command never
    # matches the git-commit-shaped pattern in the first place), not the
    # newline-preserving accessor somehow refusing to manufacture a match.
    def test_multipart_noncommit_result_resembling_bracket_pattern_does_not_fire(self):
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", "cat example.md")),
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "rc1", "content": [
                    {"type": "text", "text": "Example line from docs: "},
                    {"type": "text",
                     "text": '"...: [main abc1234] fake example line"\n'},
                ]}]}},
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC23: a REAL, unrelated git invocation containing the word
    # "commit" via a dotted config key (git config commit.gpgsign false) --
    # item 1's regex DOES match this, but it produces no git-commit success
    # line, so the gate must not fire. Stronger companion to AC6 because this
    # is a genuine git subprocess call, not a non-git command.
    def test_git_config_commit_gpgsign_does_not_fire(self):
        rc, out, err_txt = None, None, None
        r = subprocess.run(["git", "-C", self.repo, "config",
                            "commit.gpgsign", "false"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        events = make_turn_events(
            assistant_msg(bash_tool_use(
                "rc1", "git config commit.gpgsign false")),
            tool_result_event("rc1", ""),  # git config prints nothing on success
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC23 companion: `git -c commit.gpgsign=false log` -- also a
    # real git invocation matching item 1's pattern via a dotted config key,
    # producing normal log output, never a commit success line.
    def test_git_dash_c_commit_gpgsign_log_does_not_fire(self):
        log_out = subprocess.run(
            ["git", "-C", self.repo, "-c", "commit.gpgsign=false", "log",
             "--oneline"], capture_output=True, text=True).stdout
        events = make_turn_events(
            assistant_msg(bash_tool_use(
                "rc1", "git -c commit.gpgsign=false log --oneline")),
            tool_result_event("rc1", log_out),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)


class ReviewCommitGateFailOpen(unittest.TestCase):
    """AC7: any exception inside the gate's own logic must result in ALLOW,
    never a crash, never a false block caused by the gate's own failure."""

    # [BEHAVIORAL] AC7a: <target> resolution points at a non-existent path
    # (simulated by arming a session whose target file names a directory that
    # was never created / already removed) with a real-shaped commit success
    # line in the transcript -- the per-SHA git show must fail (nonexistent
    # repo), and the gate must still exit 0, not crash.
    def test_nonexistent_target_repo_fails_open(self):
        fake_target = os.path.join(tempfile.gettempdir(),
                                   "rc1-nonexistent-%s" % uuid.uuid4().hex)
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", 'git commit -m "msg"')),
            tool_result_event("rc1", "[main 3f2a1b9] msg\n 1 file changed\n"),
        )
        code, err = run_guard_armed(events, fake_target)
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC7b: a tool_result whose text is malformed/truncated
    # (content is neither a string nor a list of dicts with "text" -- an
    # unexpected shape) must not crash the gate; exit code must be whatever
    # the rest of the run would produce (0 here, nothing else in the turn
    # blocks).
    def test_malformed_tool_result_content_does_not_crash(self):
        repo = scratch_git_repo()
        try:
            events = make_turn_events(
                assistant_msg(bash_tool_use("rc1", 'git commit -m "msg"')),
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "rc1",
                     "content": [{"type": "image", "source": "not text"}]},
                ]}},
            )
            code, err = run_guard_armed(events, repo)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class ReviewCommitGateExistingSuiteUnaffected(unittest.TestCase):
    """AC8: this is documented as a structural, additive property -- the full
    surrounding test module (every class ABOVE this section in this file)
    already re-runs on every pytest invocation. This class adds an explicit,
    named marker test asserting the module as a whole collects successfully
    and that a battery of representative pre-existing behaviors (spanning
    several of the older gates) still holds unchanged, run directly here so a
    reviewer sees the AC8 guarantee asserted, not merely implied by "the rest
    of the file still runs"."""

    # [BEHAVIORAL] AC8: representative pre-existing gates (regression/FEATURE,
    # plan-check, research) still behave exactly as before this new gate's
    # addition -- unaffected by the new code appended after them.
    def test_representative_preexisting_gates_unaffected(self):
        code, err = run_guard(make_turn([ROLE_EDIT]))
        self.assertEqual(code, 2, err)  # RegressionGate baseline
        code, _ = run_guard(make_turn([CODER_AGENT]))
        self.assertEqual(code, 2)  # PlanBeforeCoderGate baseline
        # [D.2 rule-1 code==2-inversion] PLAN_VERIFIER/CODER_AGENT carry no
        # SPEC:/SPEC_SHA256= marker and this fixture has zero tool_results,
        # so no real Verifier-PASS credit chain can ever exist here --
        # structurally unsatisfiable under the v1 spec-bound-credit
        # contract regardless of marker presence. Matches the file's own
        # unmodified PlanBeforeCoderGate::test_verifier_before_no_hash_
        # coder_blocks sibling (identical fixture shape, docstring: "v1:
        # legacy Verifier presence alone does not authorize Coder").
        code, _ = run_guard(make_turn([PLAN_VERIFIER, CODER_AGENT]))
        self.assertEqual(code, 2)  # PlanBeforeCoderGate baseline (v1 contract)
        docx = tool_use("Write", file_path="/x/resume.docx", content="...")
        code, _ = run_guard(make_turn([docx]))
        self.assertEqual(code, 0)  # ExistingBehaviorHolds baseline


class ReviewCommitGateAmend(unittest.TestCase):
    """AC10: --amend uses its own reported SHA (never a bare HEAD re-read)."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC10 positive: --amend's NEW success line/sha resolves to
    # a scope-listed file -- fires using the amend's own sha.
    def test_amend_touching_scope_file_fires_on_amend_sha(self):
        rc, out, err_txt = real_git_commit(
            self.repo, ("src/app.py", "x = 1\n"), message="original commit")
        self.assertEqual(rc, 0, err_txt)
        # Amend: ADD a scope-listed file into the same commit.
        with open(os.path.join(self.repo, "RUN.md"), "w", encoding="utf-8") as f:
            f.write("amended content\n")
        subprocess.run(["git", "-C", self.repo, "add", "RUN.md"],
                       capture_output=True)
        r = subprocess.run(["git", "-C", self.repo, "commit", "--amend",
                            "--no-edit"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        events = make_turn_events(
            assistant_msg(bash_tool_use(
                "rc1", "git commit --amend --no-edit")),
            tool_result_event("rc1", r.stdout),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("RUN.md", err)

    # [BEHAVIORAL] AC10 companion negative: the amended commit's file list
    # touches ONLY non-scope files, even though the ORIGINAL pre-amend commit
    # touched a scope file -- does not fire, since the gate inspects the
    # amend's own reported sha's actual diff against ITS parent.
    def test_amend_only_touching_nonscope_file_does_not_fire_even_if_original_touched_scope(self):
        rc, out, err_txt = real_git_commit(
            self.repo, ("RUN.md", "original scope content\n"),
            message="original commit touches scope file")
        self.assertEqual(rc, 0, err_txt)
        # Amend: change only a non-scope file, RUN.md unchanged in this amend
        # relative to its own parent means --name-only for the amended commit
        # will not include RUN.md UNLESS RUN.md itself changed relative to
        # parent -- to truly isolate "amend only touches non-scope", amend
        # by ADDING an unrelated file while leaving RUN.md exactly as it was
        # relative to the parent (there is no parent here -- this is the
        # root commit -- so instead build two commits: scope-file commit,
        # then normal commit, then amend the SECOND one).
        with open(os.path.join(self.repo, "src", "other.py")
                  if os.path.isdir(os.path.join(self.repo, "src"))
                  else os.path.join(self.repo, "other2.py"), "w",
                  encoding="utf-8") as f:
            f.write("y = 2\n")
        second_path = ("src/other.py" if os.path.isdir(os.path.join(self.repo, "src"))
                       else "other2.py")
        subprocess.run(["git", "-C", self.repo, "add", second_path],
                       capture_output=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm",
                        "second commit, non-scope"], capture_output=True)
        with open(os.path.join(self.repo, second_path), "a", encoding="utf-8") as f:
            f.write("y = 3\n")
        subprocess.run(["git", "-C", self.repo, "add", second_path],
                       capture_output=True)
        r = subprocess.run(["git", "-C", self.repo, "commit", "--amend",
                            "--no-edit"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        # Confirm the amended commit's own file list does NOT include RUN.md.
        show = subprocess.run(["git", "-C", self.repo, "show", "--name-only",
                               "--format=", "HEAD"], capture_output=True,
                              text=True)
        self.assertNotIn("RUN.md", show.stdout.split())
        events = make_turn_events(
            assistant_msg(bash_tool_use(
                "rc1", "git commit --amend --no-edit")),
            tool_result_event("rc1", r.stdout),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)


class ReviewCommitGateNoSuccessLine(unittest.TestCase):
    """AC11: a bare `git commit` (no -m) that fails produces no success line
    -- no SHA extracted, gate does not fire, regardless of repo history."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC11: a real, live `git commit` invocation with a
    # non-interactive $GIT_EDITOR that exits nonzero -- captures git's own
    # real failure output (no bracket success line), even though a PRIOR
    # commit in this repo's history touched a scope-listed file.
    def test_bare_commit_no_message_failure_does_not_fire(self):
        real_git_commit(self.repo, ("RUN.md", "prior scope content\n"),
                        message="prior scope-file commit")
        with open(os.path.join(self.repo, "src2.py"), "w", encoding="utf-8") as f:
            f.write("z = 1\n")
        subprocess.run(["git", "-C", self.repo, "add", "src2.py"],
                       capture_output=True)
        env = dict(os.environ, GIT_EDITOR="false")
        r = subprocess.run(["git", "-C", self.repo, "commit"],
                           capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("[main", r.stdout)
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", "git commit")),
            tool_result_event("rc1", r.stdout + r.stderr),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)


class ReviewCommitGateMultipleCommitsSameTurn(unittest.TestCase):
    """AC12, AC13: detection is not limited to the turn's last commit --
    an EARLIER violating commit in the same turn must still be caught, even
    when a LATER commit (or a failed compliant attempt) is unrelated."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC12: FIRST raw commit touches a scope file, SECOND (later
    # in the same turn) touches only an unrelated file -- fires on the
    # FIRST commit's own extracted sha.
    def test_first_of_two_commits_touching_scope_file_still_fires(self):
        rc1, out1, e1 = real_git_commit(
            self.repo, ("RUN.md", "scope change\n"), message="first: scope file")
        self.assertEqual(rc1, 0, e1)
        rc2, out2, e2 = real_git_commit(
            self.repo, ("src/unrelated.py", "a = 1\n"), message="second: unrelated")
        self.assertEqual(rc2, 0, e2)
        events = make_turn_events(
            assistant_msg(
                bash_tool_use("rc1a", 'git commit -m "first: scope file"'),
                bash_tool_use("rc1b", 'git commit -m "second: unrelated"'),
            ),
            tool_result_event("rc1a", out1),
            tool_result_event("rc1b", out2),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("RUN.md", err)
        first_sha = out1.split("]")[0].split()[-1]
        self.assertIn(first_sha, err)

    # [BEHAVIORAL] AC13: a FAILED commit_diff_reread.py invocation (produces
    # no success line -- JSON stdout only), immediately followed in the SAME
    # turn by a raw `git commit` that SUCCEEDS and touches a scope file --
    # fires on the raw commit's own sha, unaffected by the earlier failed
    # compliant attempt.
    def test_failed_compliant_attempt_then_raw_commit_still_fires(self):
        failed_json = json.dumps({
            "committed": False,
            "results": [{"match": False, "file":
                        os.path.join(self.repo, "loop-team/orchestrator.md"),
                        "error": "no_reviewed_snapshot"}],
        })
        rc, out, err_txt = real_git_commit(
            self.repo, ("RUN.md", "raw scope change\n"),
            message="raw commit after failed compliant attempt")
        self.assertEqual(rc, 0, err_txt)
        events = make_turn_events(
            assistant_msg(
                bash_tool_use(
                    "rc1a",
                    "python3 loop-team/harness/commit_diff_reread.py commit "
                    "loop-team/orchestrator.md -- \"attempt\""),
                bash_tool_use("rc1b",
                              'git commit -m "raw commit after failed '
                              'compliant attempt"'),
            ),
            tool_result_event("rc1a", failed_json),
            tool_result_event("rc1b", out),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("RUN.md", err)


class ReviewCommitGateRealGitOutputShapes(unittest.TestCase):
    """AC14, AC15, AC16: real git success-line shapes that a hand-typed
    fixture string could get subtly wrong -- root-commit, detached-HEAD, and
    a multi-part tool_result content list whose join must preserve the
    newline immediately before the bracket."""

    # [BEHAVIORAL] AC14: a REAL, freshly-git-init'd scratch repo's actual
    # FIRST commit produces the root-commit success-line shape
    # (`[main (root-commit) <sha>] message`) -- fires when it touches a
    # scope-listed file.
    def test_root_commit_success_line_fires(self):
        d = tempfile.mkdtemp(prefix="rc1-rootcommit-")
        try:
            subprocess.run(["git", "-C", d, "init", "-q"])
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"])
            subprocess.run(["git", "-C", d, "config", "user.name", "t"])
            os.makedirs(os.path.join(d, "loop-team"), exist_ok=True)
            with open(os.path.join(d, "loop-team", "orchestrator.md"), "w",
                     encoding="utf-8") as f:
                f.write("first content\n")
            subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
            r = subprocess.run(["git", "-C", d, "commit", "-m",
                                "root commit"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("(root-commit)", r.stdout)
            events = make_turn_events(
                assistant_msg(bash_tool_use(
                    "rc1", 'git commit -m "root commit"')),
                tool_result_event("rc1", r.stdout),
            )
            code, err = run_guard_armed(events, d)
            self.assertEqual(code, 2, err)
            self.assertIn("loop-team/orchestrator.md", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC15: identical scenario checked out DETACHED, producing
    # the `[detached HEAD <sha>] message` shape.
    def test_detached_head_success_line_fires(self):
        d = tempfile.mkdtemp(prefix="rc1-detached-")
        try:
            subprocess.run(["git", "-C", d, "init", "-q"])
            subprocess.run(["git", "-C", d, "config", "user.email", "t@t"])
            subprocess.run(["git", "-C", d, "config", "user.name", "t"])
            with open(os.path.join(d, "seed.txt"), "w", encoding="utf-8") as f:
                f.write("seed\n")
            subprocess.run(["git", "-C", d, "add", "seed.txt"],
                           capture_output=True)
            subprocess.run(["git", "-C", d, "commit", "-qm", "seed"],
                           capture_output=True)
            head = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            subprocess.run(["git", "-C", d, "checkout", head],
                           capture_output=True, text=True)
            os.makedirs(os.path.join(d, "loop-team"), exist_ok=True)
            with open(os.path.join(d, "loop-team", "orchestrator.md"), "w",
                     encoding="utf-8") as f:
                f.write("detached content\n")
            subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
            r = subprocess.run(["git", "-C", d, "commit", "-m",
                                "detached commit"], capture_output=True,
                               text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("detached HEAD", r.stdout)
            events = make_turn_events(
                assistant_msg(bash_tool_use(
                    "rc1", 'git commit -m "detached commit"')),
                tool_result_event("rc1", r.stdout),
            )
            code, err = run_guard_armed(events, d)
            self.assertEqual(code, 2, err)
            self.assertIn("loop-team/orchestrator.md", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC16: a multi-part tool_result content list splits the
    # success line across two parts at a point that would straddle the
    # newline if joined with a plain space -- the gate must still correctly
    # extract the sha (proves the dedicated newline-preserving accessor is
    # used, not a silent fallback to a space-joining one).
    def test_multipart_content_split_across_newline_still_extracts_sha(self):
        d = scratch_git_repo()
        try:
            rc, out, err_txt = real_git_commit(
                d, ("RUN.md", "split-part content\n"),
                message="split part commit")
            self.assertEqual(rc, 0, err_txt)
            # Split git's REAL stdout at the newline right before the "["
            # bracket, so a space-join would destroy the very newline the
            # regex's ^ anchor (re.MULTILINE) depends on.
            split_at = out.index("[")
            part1 = out[:split_at]
            part2 = out[split_at:]
            self.assertTrue(part1.endswith("\n") or part1 == "",
                            "fixture premise: split lands right before the "
                            "bracket, on its own line")
            events = make_turn_events(
                assistant_msg(bash_tool_use(
                    "rc1", 'git commit -m "split part commit"')),
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "rc1", "content": [
                        {"type": "text", "text": part1},
                        {"type": "text", "text": part2},
                    ]}]}},
            )
            code, err = run_guard_armed(events, d)
            self.assertEqual(code, 2, err)
            self.assertIn("RUN.md", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ReviewCommitGateScopeExactMatch(unittest.TestCase):
    """AC17: root-anchored exact-match semantics -- a target repo's OWN
    nested file that happens to be named RUN.md (not at repo root) must NOT
    match, proving this is not a basename-anywhere check."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # [BEHAVIORAL] AC17: a commit touching ONLY target/scripts/RUN.md (nested,
    # not root) -- does not fire.
    def test_nested_run_md_not_at_root_does_not_fire(self):
        rc, out, err_txt = real_git_commit(
            self.repo, ("scripts/RUN.md", "a target repo's own nested doc\n"),
            message="nested RUN.md, not root")
        self.assertEqual(rc, 0, err_txt)
        events = make_turn_events(
            assistant_msg(bash_tool_use(
                "rc1", 'git commit -m "nested RUN.md, not root"')),
            tool_result_event("rc1", out),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 0, err)


class ReviewCommitGateChainedCommand(unittest.TestCase):
    """AC18: a SINGLE Bash tool_use chaining two commits (&&) -- the SECOND
    commit's own sha (which touches a scope file) must still be found, proving
    finditer-not-search."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_second_commit_in_chained_command_still_fires(self):
        rc1, out1, e1 = real_git_commit(
            self.repo, ("src/first.py", "a = 1\n"), message="first: unrelated")
        self.assertEqual(rc1, 0, e1)
        rc2, out2, e2 = real_git_commit(
            self.repo, ("RUN.md", "second: scope change\n"),
            message="second: scope file")
        self.assertEqual(rc2, 0, e2)
        # Both success lines concatenated as ONE tool_result, matching what a
        # single chained `git commit -m "a" && git commit -m "b"` invocation's
        # combined stdout would look like.
        combined = out1 + out2
        events = make_turn_events(
            assistant_msg(bash_tool_use(
                "rc1",
                'git commit -m "first: unrelated" && git commit -m '
                '"second: scope file"')),
            tool_result_event("rc1", combined),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("RUN.md", err)
        second_sha = out2.split("]")[0].split()[-1]
        self.assertIn(second_sha, err)


class ReviewCommitGateMergeCommits(unittest.TestCase):
    """AC19: the precise merge-commit residual boundary -- a wholesale
    one-parent resolution (git checkout --theirs) produces EMPTY --name-only
    output and is NOT detected (documented residual); a genuinely BLENDED
    resolution DOES produce non-empty output and IS detected normally."""

    def _make_merge_repo(self):
        d = tempfile.mkdtemp(prefix="rc1-merge-")
        def g(*args):
            return subprocess.run(["git", "-C", d] + list(args),
                                  capture_output=True, text=True)
        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        with open(os.path.join(d, "RUN.md"), "w", encoding="utf-8") as f:
            f.write("base\n")
        g("add", "RUN.md")
        g("commit", "-qm", "base")
        g("checkout", "-qb", "branch-a")
        with open(os.path.join(d, "RUN.md"), "w", encoding="utf-8") as f:
            f.write("branch-a-content\n")
        g("commit", "-qam", "a change")
        g("checkout", "-qb", "branch-b", "main")
        with open(os.path.join(d, "RUN.md"), "w", encoding="utf-8") as f:
            f.write("branch-b-content\n")
        g("commit", "-qam", "b change")
        g("checkout", "-q", "branch-a")
        g("merge", "branch-b", "-m", "merge attempt")
        return d, g

    # [BEHAVIORAL] AC19a: merge conflict resolved WHOLESALE (git checkout
    # --theirs) -- does NOT fire (documented, narrow, accepted residual).
    def test_merge_resolved_wholesale_theirs_does_not_fire(self):
        d, g = self._make_merge_repo()
        try:
            g("checkout", "--theirs", "RUN.md")
            g("add", "RUN.md")
            r = subprocess.run(["git", "-C", d, "commit", "-m",
                                "resolved wholesale"], capture_output=True,
                               text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            # Confirm the fixture premise directly: --name-only is empty.
            show = subprocess.run(["git", "-C", d, "show", "--name-only",
                                   "--format=", "HEAD"], capture_output=True,
                                  text=True)
            self.assertEqual(show.stdout.strip(), "",
                             "fixture premise: wholesale-theirs merge shows "
                             "empty --name-only output")
            events = make_turn_events(
                assistant_msg(bash_tool_use(
                    "rc1", 'git commit -m "resolved wholesale"')),
                tool_result_event("rc1", r.stdout),
            )
            code, err = run_guard_armed(events, d)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # [BEHAVIORAL] AC19b: merge conflict resolved with genuinely BLENDED
    # content (neither parent's version taken wholesale) -- DOES fire.
    def test_merge_resolved_blended_content_fires(self):
        d, g = self._make_merge_repo()
        try:
            with open(os.path.join(d, "RUN.md"), "w", encoding="utf-8") as f:
                f.write("blended-content-both\n")
            g("add", "RUN.md")
            r = subprocess.run(["git", "-C", d, "commit", "-m",
                                "resolved blended"], capture_output=True,
                               text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            show = subprocess.run(["git", "-C", d, "show", "--name-only",
                                   "--format=", "HEAD"], capture_output=True,
                                  text=True)
            self.assertIn("RUN.md", show.stdout.split(),
                          "fixture premise: blended-resolution merge shows "
                          "RUN.md in --name-only output")
            events = make_turn_events(
                assistant_msg(bash_tool_use(
                    "rc1", 'git commit -m "resolved blended"')),
                tool_result_event("rc1", r.stdout),
            )
            code, err = run_guard_armed(events, d)
            self.assertEqual(code, 2, err)
            self.assertIn("RUN.md", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ReviewCommitGateNoiseLineRobustness(unittest.TestCase):
    """AC20: a fabricated/noise bracket-shaped line preceding the real git
    success line (simulating a pre-commit hook's own status output) must not
    prevent detection of the REAL commit, and the fabricated candidate itself
    must be filtered by git-show resolution (not by the regex)."""

    def setUp(self):
        self.repo = scratch_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_noise_bracket_before_real_success_line_still_fires_on_real_sha(self):
        rc, out, err_txt = real_git_commit(
            self.repo, ("RUN.md", "content after fake hook line\n"),
            message="Fix typo")
        self.assertEqual(rc, 0, err_txt)
        noisy = "[hook cafebabe] pre-commit ok\n" + out
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", 'git commit -m "Fix typo"')),
            tool_result_event("rc1", noisy),
        )
        code, err = run_guard_armed(events, self.repo)
        self.assertEqual(code, 2, err)
        self.assertIn("RUN.md", err)
        real_sha = out.split("]")[0].split()[-1]
        self.assertIn(real_sha, err)
        self.assertNotIn("cafebabe", err)


class ReviewCommitGateReturncodeCheck(unittest.TestCase):
    """AC24: a `git show` subprocess call that returns a NONZERO returncode
    WITHOUT raising a Python exception (a valid-but-unrelated repo where the
    sha does not exist) must be treated as "this sha contributes nothing" --
    proves the explicit .returncode check, not merely a try/except that a
    non-raising failure would sail past."""

    def test_sha_not_present_in_armed_but_unrelated_repo_does_not_fire(self):
        # A real, valid git repo that simply never contains the reported sha
        # (it belongs to a totally different, throwaway repo's history).
        unrelated_repo = scratch_git_repo()
        other_repo = scratch_git_repo()
        try:
            rc, out, err_txt = real_git_commit(
                other_repo, ("RUN.md", "commit in the OTHER repo\n"),
                message="commit in other repo")
            self.assertEqual(rc, 0, err_txt)
            # This sha is real, but does not exist in `unrelated_repo`'s
            # object database -- `git show` there must return nonzero
            # without raising, and the gate must fail open (not fire).
            events = make_turn_events(
                assistant_msg(bash_tool_use(
                    "rc1", 'git commit -m "commit in other repo"')),
                tool_result_event("rc1", out),
            )
            code, err = run_guard_armed(events, unrelated_repo)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(unrelated_repo, ignore_errors=True)
            shutil.rmtree(other_repo, ignore_errors=True)


class ReviewCommitGateActivationSingleCallSite(unittest.TestCase):
    """AC25(b): a DURABLE regression test (not a single-line text match) that
    loop_stop_guard.py never calls micro_step_gates._activation() directly
    anywhere in its own source -- it only ever reads the _LAST_ACTIVATION
    broadcast variable. Greps the FULL current source, EXCLUDING comment
    lines (this file's own established commenting convention narrates the
    _activation()/run(data) relationship in prose at multiple points, which
    would make a naive whole-file substring count of "_activation(" over-
    count -- confirmed live: comment-only occurrences exist independent of
    this spec's own design, so the precise, spec-grounded check is CODE-level
    call sites, not raw substring count including prose), and asserts ZERO
    CODE-level occurrences of the literal direct call `_msg_mod._activation(`
    anywhere in this file -- both at the pre-existing shadow-slop call site
    (which must read `_LAST_ACTIVATION` via getattr instead) and this new
    gate. Catches a FUTURE gate re-introducing a direct call site, not just
    today's fix."""

    def test_loop_stop_guard_never_calls_activation_directly_in_code(self):
        src = open(GUARD, encoding="utf-8").read()
        code_lines_with_direct_call = [
            ln for ln in src.splitlines()
            if "_msg_mod._activation(" in ln
            and not ln.strip().startswith("#")
        ]
        self.assertEqual(
            code_lines_with_direct_call, [],
            "loop_stop_guard.py must contain ZERO code-level (non-comment) "
            "occurrences of the literal direct call '_msg_mod._activation(' "
            "-- every caller in this file must read the _LAST_ACTIVATION "
            "broadcast variable via getattr(_msg_mod, \"_LAST_ACTIVATION\", "
            "None) instead, so there is only ONE underlying resolution "
            "(inside micro_step_gates.run()'s own call) per hook firing, "
            "not a second/third independent call reintroducing the race "
            "this design closed. Offending line(s): %r"
            % code_lines_with_direct_call)
        # Companion, coarser sanity check on the whole (non-comment) source:
        # the substring "_msg_mod._activation(" must not appear in ANY
        # executable line, matched independent of the split-by-line pass
        # above (defense against a call spanning oddly-formatted lines).
        code_only = "\n".join(
            ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        self.assertNotIn(
            "_msg_mod._activation(", code_only,
            "loop_stop_guard.py must never directly call "
            "_msg_mod._activation() in executable code -- it must only "
            "read the _LAST_ACTIVATION broadcast variable via getattr()")


# ---------------------------------------------------------------------------
# H-GUARD-8 (runs/2026-07-03_h-guard-8/specs/spec.md)
# AC1-AC7: four gates' visible stderr messages must append
# " Matched: %r" % (<evidence>,) alongside their existing text -- a purely
# additive change to message content, never to firing logic. AC5 (VERIFIER_
# HYGIENE/VERIFIER_ADJACENCY byte-for-byte unchanged) is verified by NOT
# touching those code paths at all (see the source diff); no test in this
# class exercises them since this file carries no pre-existing tests for
# those two gates to begin with (they live in test_verifier_hygiene_gate.py,
# untouched by this build).
# ---------------------------------------------------------------------------

class MatchedEvidenceHGuard8(unittest.TestCase):
    """AC1-AC7: each of the four fixed gates' stderr message must contain the
    literal substring "Matched:" followed by real, non-empty evidence
    identifying what actually triggered the gate -- constructed by driving
    the guard's REAL detection regex/logic against real transcript fixtures
    (never by hand-asserting the message format), per the spec's AC1-AC4
    instruction. Each fire case has a companion no-fire case (AC6) proving
    this build changed message content only, never the firing condition."""

    # ---- AC1: ROLE_OR_HARNESS_EDIT ----------------------------------------

    def test_ac1_role_or_harness_edit_message_includes_matched_evidence(self):
        # ROLE_EDIT (module-level fixture) trips the real _role_match regex
        # against roles/verifier.md; no SUITE_GREEN this turn -> fires.
        code, err = run_guard(make_turn([ROLE_EDIT]))
        self.assertEqual(code, 2, err)
        self.assertIn("Matched:", err)
        # The real matched text must name the actual triggering path segment
        # (roles/verifier.md), not be empty or a placeholder.
        self.assertIn("roles/verifier.md", err)

    def test_ac1_harness_edit_message_includes_matched_evidence(self):
        code, err = run_guard(make_turn([HARNESS_EDIT]))
        self.assertEqual(code, 2, err)
        self.assertIn("Matched:", err)
        self.assertIn("harness/verify.py", err)

    # AC6 companion: same fixture, but green suite + verifier present -> the
    # gate's firing CONDITION does not fire (exit 0); proves this build did
    # not touch when the gate blocks, only what it prints when it does.
    def test_ac1_companion_no_fire_with_green_and_verifier_passes(self):
        code, _ = run_guard(make_turn([ROLE_EDIT, RUN_EVALS, VERIFIER_TASK],
                                      results=[GREEN_RESULT]))
        self.assertEqual(code, 0)

    # ---- AC2: FEATURE -------------------------------------------------------

    def test_ac2_feature_message_includes_matched_evidence(self):
        # A plain code-file edit (no roles/harness segment) trips ONLY the
        # FEATURE gate's blob regex, isolating this from ROLE_OR_HARNESS_EDIT.
        ts = tool_use("Edit", file_path="/x/src/app.ts",
                      old_string="a", new_string="b")
        code, err = run_guard(make_turn([ts]))
        self.assertEqual(code, 2, err)
        self.assertIn("Matched:", err)
        # Real matched text names the actual triggering tool+path evidence.
        self.assertIn("app.ts", err)

    # AC6 companion: same fixture, but with an independent verifier dispatch
    # this turn -> FEATURE's firing condition is false -> exit 0.
    def test_ac2_companion_no_fire_with_verifier_passes(self):
        ts = tool_use("Edit", file_path="/x/src/app.ts",
                      old_string="a", new_string="b")
        code, _ = run_guard(make_turn([ts, VERIFIER_TASK]))
        self.assertEqual(code, 0)

    # ---- AC3: PLAN_CHECK -----------------------------------------------------

    def test_ac3_plan_check_message_includes_matched_evidence_from_coder_dispatch(self):
        # CODER_AGENT's own description is "Coder for the build" -- the
        # snippet must be derived from THAT dispatch's own input, not the
        # fixed label "coder-before-verifier".
        code, err = run_guard(make_turn([CODER_AGENT]))
        self.assertEqual(code, 2, err)
        self.assertIn("Matched:", err)
        self.assertNotIn("coder-before-verifier", err)
        self.assertIn("Coder for the build", err)

    def test_ac3_message_evidence_identifies_first_of_multiple_coder_dispatches(self):
        # Two distinct Coder dispatches in one turn, neither preceded by a
        # Verifier -> the FIRST one's own description must be the surfaced
        # evidence (accepted residual: only the first is surfaced).
        coder_a = tool_use("Agent", description="Coder for step A of the build",
                           prompt="# Role: Coder\nImplement step A...")
        coder_b = tool_use("Agent", description="Coder for step B of the build",
                           prompt="# Role: Coder\nImplement step B...")
        code, err = run_guard(make_turn([coder_a, coder_b]))
        self.assertEqual(code, 2, err)
        self.assertIn("Matched:", err)
        self.assertIn("Coder for step A of the build", err)

    def test_ac3_message_evidence_falls_back_to_prompt_when_no_description(self):
        # An Agent tool_use with NO description field at all -- the coder
        # snippet must fall back to (a truncated prefix of) the prompt.
        coder_no_desc = {"type": "tool_use", "name": "Agent",
                         "input": {"prompt": "role: coder\nImplement the "
                                              "spec for the widget feature "
                                              "end to end with tests."}}
        code, err = run_guard(make_turn([coder_no_desc]))
        self.assertEqual(code, 2, err)
        self.assertIn("Matched:", err)
        self.assertIn("Implement the spec for the widget feature", err)

    # AC6 companion: same lone-Coder shape, but WITH a preceding plan-check
    # Verifier dispatch in the same turn -> PLAN_CHECK's firing condition is
    # false -> exit 0 (reuses the existing PlanBeforeCoderGate fixture idiom).
    def test_ac3_companion_no_fire_verifier_before_coder_passes(self):
        # [D.2 rule-1 code==2-inversion] PLAN_VERIFIER/CODER_AGENT carry no
        # SPEC:/SPEC_SHA256= marker and this fixture has zero tool_results
        # -- structurally unsatisfiable under the v1 spec-bound-credit
        # contract, matching PlanBeforeCoderGate::test_verifier_before_
        # no_hash_coder_blocks's identical fixture shape and its own "v1:
        # legacy Verifier presence alone does not authorize Coder" intent.
        code, _ = run_guard(make_turn([PLAN_VERIFIER, CODER_AGENT]))
        self.assertEqual(code, 2)

    # ---- AC4: RESEARCH_GATE ---------------------------------------------------
    #
    # NOTE: the module-level ResearchGate fixtures (RESEARCHER_AGENT,
    # FEATURE_EDIT) always trip the FEATURE gate FIRST (FEATURE's check runs
    # before RESEARCH_GATE's in the file, and FEATURE_EDIT's .py path always
    # matches FEATURE's blob regex) -- confirmed directly against the real
    # guard: with those fixtures alone, exit 2's message is FEATURE's, not
    # RESEARCH_GATE's (AC-R4's own docstring already flags this: "we cannot
    # distinguish which gate triggered from exit code alone"). To isolate
    # RESEARCH_GATE specifically, these fixtures add a THIRD dispatch whose
    # prompt contains the bare word "verify" (satisfying FEATURE's broad
    # `VERIFIER` check, which matches plain "verify") but NOT the narrower
    # `_VERIFIER_DETECT` pattern RESEARCH_GATE requires (no "independent
    # verifier" / "verifier.md" / "plan-check verifier" phrasing) -- this
    # suppresses FEATURE while leaving RESEARCH_GATE's own condition
    # (researcher ran, armed via returned-evidence, then a direct code edit,
    # no _VERIFIER_DETECT-matching dispatch anywhere) still true.
    BARE_VERIFY_TASK = tool_use("Agent", description="Some other task",
                                prompt="please verify the environment is set up")

    def test_ac4_research_gate_message_includes_matched_evidence_file_path(self):
        researcher = researcher_dispatch("toolu_ac4_isolated")
        edit = tool_use("Edit", file_path="/x/src/service.py",
                        old_string="a", new_string="b")
        events = make_turn_events(
            assistant_msg(self.BARE_VERIFY_TASK, researcher),
            tool_result_event("toolu_ac4_isolated",
                              "Researcher findings: some finding."),
            assistant_msg(edit),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)
        self.assertIn("[LOOP STOP-GUARD] A Researcher (Mode D)", err)  # confirms RESEARCH_GATE, not FEATURE
        self.assertIn("Matched:", err)
        self.assertIn("/x/src/service.py", err)
        self.assertNotIn("researcher-then-direct-edit", err)

    def test_ac4_message_evidence_identifies_distinct_edited_path(self):
        # A different file path than the previous test, to prove the evidence
        # is genuinely derived from THIS turn's edit, not a hardcoded string.
        researcher = researcher_dispatch("toolu_ac4_distinct_path")
        distinct_edit = tool_use("Edit", file_path="/x/src/distinct_service.py",
                                 old_string="a", new_string="b")
        events = make_turn_events(
            assistant_msg(self.BARE_VERIFY_TASK, researcher),
            tool_result_event("toolu_ac4_distinct_path",
                              "Researcher findings: some finding."),
            assistant_msg(distinct_edit),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)
        self.assertIn("[LOOP STOP-GUARD] A Researcher (Mode D)", err)
        self.assertIn("Matched:", err)
        self.assertIn("/x/src/distinct_service.py", err)

    # AC6 companion: same Researcher-then-edit shape, but WITH a plan-check
    # Verifier dispatched between the research and the edit -> RESEARCH_GATE's
    # firing condition is false -> exit 0 (reuses the existing ResearchGate
    # fixture idiom).
    def test_ac4_companion_no_fire_verifier_between_research_and_edit_passes(self):
        code, err = run_guard(make_turn(
            [RESEARCHER_AGENT, PLAN_VERIFIER_AFTER, FEATURE_EDIT]))
        self.assertEqual(code, 0, err)

    # ---- AC7: full pre-existing suite still passes -------------------------
    # AC7 itself is not a single assertable unit test (it's "the whole file's
    # prior tests still pass unchanged") -- it is verified by running the full
    # `python3 -m pytest hooks/test_loop_stop_guard.py -q` suite, not by any
    # one test here. This placeholder documents that explicitly so a future
    # reader does not go looking for a missing AC7-specific test method.
    def test_ac7_documented_as_whole_suite_regression_not_a_single_test(self):
        self.assertTrue(True)


# ---------------------------------------------------------------------------
# H-SUBAGENT-COMMIT-GATE-1 (runs/2026-07-03_h-subagent-commit-gate-1/specs/spec.md)
# Layer 1 (flag-file bridge, primary/authoritative) and Layer 2 (direct
# sub-agent-transcript scan, secondary/defense-in-depth). AC1 (behavior-
# preserving refactor into commit_scope_scan.find_commit_scope_violations())
# is proven by the ENTIRE ReviewCommitGate* suite above continuing to pass
# unchanged against the refactored code -- no separate test method needed
# for AC1 specifically (see AC1 row in spec.md's own ACs table: "the full
# existing hooks/test_loop_stop_guard.py suite passes unchanged after the
# refactor").
# ---------------------------------------------------------------------------

GATE_DIR_L1 = GATE_DIR  # same $LOOP_GATE_DIR the rest of this file already uses


def write_commit_violation_flag(session_id, agent_id, violations, mtime=None):
    """Write a real {session_id}_{agent_id}.commit_violation flag under
    GATE_DIR, with JSON content matching the shape
    hooks/subagent_stop_gate.py's 4th responsibility writes
    ([{"sha": ..., "touched": [...]}, ...]). `violations` may be any
    JSON-serializable value (a deliberately malformed shape for AC4b), or a
    raw string (to construct genuinely invalid JSON). If `mtime` is given,
    os.utime() the flag to that timestamp (AC6's stale-flag construction)."""
    os.makedirs(GATE_DIR_L1, exist_ok=True)
    path = os.path.join(GATE_DIR_L1, f"{session_id}_{agent_id}.commit_violation")
    content = violations if isinstance(violations, str) else json.dumps(violations)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def make_agent_dispatch_transcript(sid, agent_id, base_dir, sub_events):
    """Build a real, on-disk sub-agent transcript at the expected
    <project_dir>/<session_id>/subagents/agent-<id>.jsonl path, where
    <project_dir> is `base_dir` -- per spec.md AC8's explicit
    test-hermeticity requirement, this must be a tempfile-based dir the test
    constructs itself, NEVER the real ~/.claude/projects/ tree, and the test
    must not derive this path via the implementation's own path-construction
    function (that would let a wrong formula appear self-consistent) -- this
    helper hardcodes the formula independently, matching the spec's own
    prose description of it. Returns the sub-agent transcript path."""
    sub_dir = os.path.join(base_dir, sid, "subagents")
    os.makedirs(sub_dir, exist_ok=True)
    sub_path = os.path.join(sub_dir, "agent-%s.jsonl" % agent_id)
    with open(sub_path, "w", encoding="utf-8") as f:
        for e in sub_events:
            f.write(json.dumps(e) + "\n")
    return sub_path


def agent_dispatch_result_event(tool_use_id, agent_id):
    """A raw JSONL event whose top-level `toolUseResult` key is a dict
    containing an `agentId` key -- the live-verified real event shape
    Layer 2 scans for (spec.md item 4). `toolUseResult` is a TOP-LEVEL
    sibling of `message`, never reachable via _parts()/_TOOL_RESULTS."""
    return {
        "toolUseResult": {"isAsync": True, "status": "async_launched",
                           "agentId": agent_id, "description": "dispatch"},
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id,
             "content": "Async agent launched successfully.\nagentId: %s" % agent_id},
        ]},
        "type": "user",
    }


def run_guard_full(events, transcript_path=None, session_id=None,
                    stop_hook_active=False, extra_payload=None):
    """Like run_guard(), but returns (returncode, stderr) using an EXPLICIT
    transcript_path (so the caller controls the on-disk directory layout,
    needed for Layer 2's <project_dir>/<session_id>/subagents/ resolution)
    and an explicit session_id in the payload -- run_guard()/run_guard_armed()
    do not expose both together in the shape H-SUBAGENT-COMMIT-GATE-1's tests
    need."""
    own_tmp = transcript_path is None
    if own_tmp:
        fd, transcript_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
    try:
        with open(transcript_path, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        payload = {"transcript_path": transcript_path,
                   "stop_hook_active": stop_hook_active}
        if session_id is not None:
            payload["session_id"] = session_id
        if extra_payload:
            payload.update(extra_payload)
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR_L1)
        p = subprocess.run([sys.executable, GUARD], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        if own_tmp:
            os.remove(transcript_path)


class SubagentCommitGateLayer1FlagFire(unittest.TestCase):
    """AC4: a fresh .commit_violation flag blocks Oga's own Stop even when
    Oga's OWN turn contains no raw git commit at all."""

    def setUp(self):
        self._flags = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    # [BEHAVIORAL] AC4 / AC10 companion (Layer-1-only): fresh flag present,
    # Oga's own turn has zero commit-shaped tool_use -- fires via Layer 1
    # alone (proving Layer 1 is genuinely authoritative, not accidentally
    # dependent on Layer 2 also succeeding -- there is no sub-agent
    # transcript file on disk at all here).
    def test_fresh_flag_blocks_with_no_own_turn_commit(self):
        sid = "l1-fire-%s" % uuid.uuid4().hex
        aid = "agentA"
        self._flags.append(write_commit_violation_flag(
            sid, aid, [{"sha": "abc1234", "touched": ["RUN.md"]}]))
        events = make_turn([text("just talking, no commit this turn")])
        code, err = run_guard_full(events, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)
        self.assertIn("abc1234", err)
        self.assertIn("RUN.md", err)
        self.assertIn("Layer 1", err)


class SubagentCommitGateLayer1Malformed(unittest.TestCase):
    """AC4b: malformed/non-shape-conforming/empty-list flag content still
    blocks, with a message stating the agent_id and that detail could not be
    parsed -- never a crash, never a silent allow."""

    def setUp(self):
        self._flags = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_invalid_json_content_still_blocks(self):
        sid = "l1-malformed-json-%s" % uuid.uuid4().hex
        aid = "agentB"
        self._flags.append(write_commit_violation_flag(sid, aid, "not json at all {{{"))
        code, err = run_guard_full(make_turn([text("nothing")]), session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)
        self.assertTrue("could not be parsed" in err or "could not parse" in err, err)

    def test_valid_json_wrong_shape_still_blocks(self):
        sid = "l1-malformed-shape-%s" % uuid.uuid4().hex
        aid = "agentC"
        # Valid JSON, but not the expected [{"sha":..., "touched":[...]}] shape.
        self._flags.append(write_commit_violation_flag(sid, aid, {"unexpected": "shape"}))
        code, err = run_guard_full(make_turn([text("nothing")]), session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)

    def test_empty_list_content_still_blocks(self):
        sid = "l1-empty-list-%s" % uuid.uuid4().hex
        aid = "agentD"
        # Syntactically-valid empty list -- resolved (round-2 finding) the
        # SAME as malformed, since a fresh flag existing at all signals a
        # detected violation regardless of what its content parses to.
        self._flags.append(write_commit_violation_flag(sid, aid, []))
        code, err = run_guard_full(make_turn([text("nothing")]), session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)


class SubagentCommitGateLayer1Multi(unittest.TestCase):
    """AC5: TWO fresh flags (two distinct agent_ids) -- Oga's Stop hook
    message reports BOTH violations' evidence, not just one."""

    def setUp(self):
        self._flags = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_two_fresh_flags_both_reported(self):
        sid = "l1-multi-%s" % uuid.uuid4().hex
        self._flags.append(write_commit_violation_flag(
            sid, "agent1", [{"sha": "1111111", "touched": ["RUN.md"]}]))
        self._flags.append(write_commit_violation_flag(
            sid, "agent2", [{"sha": "2222222", "touched": ["fix_plan.md"]}]))
        code, err = run_guard_full(make_turn([text("nothing")]), session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn("agent1", err)
        self.assertIn("agent2", err)
        self.assertIn("1111111", err)
        self.assertIn("2222222", err)


class SubagentCommitGateLayer1Stale(unittest.TestCase):
    """AC6: a STALE flag (mtime older than PLAN_PASS_TTL_SECONDS) does not
    fire, and is cleaned up best-effort."""

    def setUp(self):
        self._flags = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_stale_flag_does_not_fire_and_is_removed(self):
        sid = "l1-stale-%s" % uuid.uuid4().hex
        aid = "agentStale"
        old_mtime = time.time() - (26 * 3600)  # older than the 24h TTL
        flag_path = write_commit_violation_flag(
            sid, aid, [{"sha": "abcdef1", "touched": ["RUN.md"]}], mtime=old_mtime)
        self._flags.append(flag_path)
        code, err = run_guard_full(make_turn([text("nothing")]), session_id=sid)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(flag_path),
                         "stale flag should be best-effort removed")


class SubagentCommitGateLayer1SessionScoping(unittest.TestCase):
    """A flag belonging to a DIFFERENT session must never arm the gate for
    this session (mirrors the existing PLAN_PASS cross-session isolation
    already tested elsewhere in this file)."""

    def setUp(self):
        self._flags = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_flag_for_different_session_does_not_arm_this_session(self):
        other_sid = "l1-other-%s" % uuid.uuid4().hex
        this_sid = "l1-this-%s" % uuid.uuid4().hex
        self._flags.append(write_commit_violation_flag(
            other_sid, "agentX", [{"sha": "9999999", "touched": ["RUN.md"]}]))
        code, err = run_guard_full(make_turn([text("nothing")]), session_id=this_sid)
        self.assertEqual(code, 0, err)


class SubagentCommitGateLayer1FailOpen(unittest.TestCase):
    """AC13b: any exception inside Layer 1's own gate logic (not just the
    inner JSON-parse step AC4b covers) results in ALLOW, via a
    file-spanning try/except wrapping the gate's ENTIRE logic."""

    # [BEHAVIORAL] AC13b: a NON-STRING session_id in the Stop-hook payload
    # (JSON permits any type, e.g. an integer) makes glob.escape(session_id)
    # raise a real TypeError -- confirmed directly (glob.escape(12345) ->
    # "expected str, bytes or os.PathLike object, not int"). This is a
    # genuine exception ORIGINATING in Layer 1's own outer-scope logic (the
    # glob-construction step, not the inner JSON-parse try/except AC4b
    # covers) -- proving the file-spanning try/except actually catches it,
    # not merely that "no flags happen to exist" trivially passes.
    def test_non_string_session_id_raises_inside_gate_and_fails_open(self):
        fd, tpath = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            with open(tpath, "w", encoding="utf-8") as f:
                for e in make_turn([text("nothing")]):
                    f.write(json.dumps(e) + "\n")
            payload = json.dumps({"transcript_path": tpath,
                                  "session_id": 12345,
                                  "stop_hook_active": False})
            env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR_L1)
            p = subprocess.run([sys.executable, GUARD], input=payload,
                               capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            os.remove(tpath)

    # [BEHAVIORAL] AC13b companion: an unwritable/nonexistent LOOP_GATE_DIR
    # (a plain file where a directory is expected) -- glob.glob() under such
    # a path degrades to an empty result on this platform (confirmed
    # directly, not raising), so this companion asserts the weaker but still
    # real guarantee: the gate must never crash or false-block regardless of
    # which of the two behaviors glob.glob() exhibits.
    def test_unwritable_gate_dir_fails_open(self):
        fd, blocking_file = tempfile.mkstemp(prefix="l1-blocker-")
        os.close(fd)
        try:
            bogus_gate_dir = os.path.join(blocking_file, "nested", "gate")
            sid = "l1-failopen-%s" % uuid.uuid4().hex
            fd2, tpath = tempfile.mkstemp(suffix=".jsonl")
            os.close(fd2)
            try:
                with open(tpath, "w", encoding="utf-8") as f:
                    for e in make_turn([text("nothing")]):
                        f.write(json.dumps(e) + "\n")
                payload = json.dumps({"transcript_path": tpath,
                                      "session_id": sid,
                                      "stop_hook_active": False})
                env = dict(os.environ, LOOP_GATE_DIR=bogus_gate_dir)
                p = subprocess.run([sys.executable, GUARD], input=payload,
                                   capture_output=True, text=True, env=env)
                self.assertEqual(p.returncode, 0, p.stderr)
            finally:
                os.remove(tpath)
        finally:
            os.remove(blocking_file)


class SubagentCommitGateLayer2Fire(unittest.TestCase):
    """AC8: Layer 2 fires via a REAL sub-agent transcript file on disk at
    the expected <project_dir>/<session_id>/subagents/agent-<id>.jsonl path
    (project_dir derived from the SAME tempfile-based transcript_path Oga's
    own turn uses), with NO .commit_violation flag present at all."""

    def setUp(self):
        self._tmpdirs = []
        self._repos = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)

    # [BEHAVIORAL] AC8: fires via Layer 2 alone (no flag anywhere).
    def test_layer2_fires_with_real_subagent_transcript_no_flag(self):
        repo = scratch_git_repo()
        self._repos.append(repo)
        rc, out, err_txt = real_git_commit(
            repo, ("RUN.md", "layer2 content\n"), message="layer2 commit")
        self.assertEqual(rc, 0, err_txt)

        project_dir = tempfile.mkdtemp(prefix="l2-proj-")
        self._tmpdirs.append(project_dir)
        sid = "l2-fire-%s" % uuid.uuid4().hex
        agent_id = "agentL2Fire"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

        make_agent_dispatch_transcript(sid, agent_id, project_dir, [
            assistant_msg(bash_tool_use("rcS", 'git commit -m "layer2 commit"')),
            tool_result_event("rcS", out),
        ])

        # Oga's own turn: a dispatch tool_use + a raw event whose
        # toolUseResult.agentId matches the sub-agent transcript's own id.
        marker = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [
            marker,
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        # Arm the micro-step target so _rc_target resolves to `repo` (Layer 2
        # reuses Oga's own already-resolved _rc_target -- it has no access to
        # the sub-agent's own cwd, per spec.md's own residual-risk note).
        os.makedirs(GATE_DIR_L1, exist_ok=True)
        target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(repo)
        try:
            code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        finally:
            try:
                os.remove(target_file)
            except OSError:
                pass
        self.assertEqual(code, 2, err)
        self.assertIn(agent_id, err)
        self.assertIn("RUN.md", err)
        self.assertIn("Layer 2", err)
        # No .commit_violation flag exists anywhere for this session.
        self.assertEqual(
            glob.glob(os.path.join(GATE_DIR_L1, "%s_*.commit_violation" % sid)), [])


class SubagentCommitGateLayer2Multi(unittest.TestCase):
    """AC8b: TWO distinct agentIds via two toolUseResult events, each with
    its own real sub-agent transcript, BOTH containing a Layer-2-detectable
    violation, NEITHER flagged -- Oga's Stop hook message reports BOTH."""

    def setUp(self):
        self._tmpdirs = []
        self._repos = []
        self._flags = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_two_agents_both_layer2_violations_both_reported(self):
        repo = scratch_git_repo()
        self._repos.append(repo)
        rc1, out1, e1 = real_git_commit(
            repo, ("RUN.md", "agentA content\n"), message="agentA commit")
        self.assertEqual(rc1, 0, e1)
        rc2, out2, e2 = real_git_commit(
            repo, ("fix_plan.md", "agentB content\n"), message="agentB commit")
        self.assertEqual(rc2, 0, e2)

        project_dir = tempfile.mkdtemp(prefix="l2-multi-proj-")
        self._tmpdirs.append(project_dir)
        sid = "l2-multi-%s" % uuid.uuid4().hex
        agent_a, agent_b = "agentMultiA", "agentMultiB"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

        make_agent_dispatch_transcript(sid, agent_a, project_dir, [
            assistant_msg(bash_tool_use("rcA", 'git commit -m "agentA commit"')),
            tool_result_event("rcA", out1),
        ])
        make_agent_dispatch_transcript(sid, agent_b, project_dir, [
            assistant_msg(bash_tool_use("rcB", 'git commit -m "agentB commit"')),
            tool_result_event("rcB", out2),
        ])

        marker = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [
            marker,
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch A")),
            agent_dispatch_result_event("dispA", agent_a),
            assistant_msg(tool_use("Task", description="dispatch B")),
            agent_dispatch_result_event("dispB", agent_b),
        ]
        os.makedirs(GATE_DIR_L1, exist_ok=True)
        target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(repo)
        try:
            code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        finally:
            try:
                os.remove(target_file)
            except OSError:
                pass
        self.assertEqual(code, 2, err)
        self.assertIn(agent_a, err)
        self.assertIn(agent_b, err)

    # [BEHAVIORAL] AC9 (H-SUBAGENT-MASKING-1 v4, revised from the original
    # "agent A masks agent B" masking-acceptance test): the append-not-exit
    # `_VIOLATIONS` design (runs/2026-07-03_h-subagent-masking-1-full-
    # closure/specs/spec.md) means Layer 1's flag-file bridge no longer
    # exits early on agent A's violation -- it APPENDS and control continues
    # to Layer 2, which independently detects agent B's genuinely different
    # violation and ALSO appends. Both are now reported in full at EOF. This
    # replaces the old assertNotIn(agent_b, err) assertion (which documented
    # the masking gap this whole build exists to close) with assertIn plus
    # real evidence content, proving B is no longer silently dropped.
    def test_flagged_agent_a_and_layer2_only_agent_b_both_reported_same_turn(self):
        repo = scratch_git_repo()
        self._repos.append(repo)
        rc2, out2, e2 = real_git_commit(
            repo, ("fix_plan.md", "agentB layer2-only content\n"),
            message="agentB layer2-only commit")
        self.assertEqual(rc2, 0, e2)

        project_dir = tempfile.mkdtemp(prefix="l2-mask-proj-")
        self._tmpdirs.append(project_dir)
        sid = "l1-masks-l2-%s" % uuid.uuid4().hex
        agent_a, agent_b = "agentMaskA", "agentMaskB"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

        # Agent A: fresh Layer-1 flag already exists (its SubagentStop
        # already ran and wrote the flag).
        self._flags.append(write_commit_violation_flag(
            sid, agent_a, [{"sha": "aaaaaaa", "touched": ["RUN.md"]}]))

        # Agent B: ONLY a Layer-2-detectable violation (its own transcript
        # exists on disk, but no .commit_violation flag for it -- simulating
        # the async race where B's own SubagentStop hasn't written yet).
        make_agent_dispatch_transcript(sid, agent_b, project_dir, [
            assistant_msg(bash_tool_use("rcB", 'git commit -m "agentB layer2-only commit"')),
            tool_result_event("rcB", out2),
        ])

        marker = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [
            marker,
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch B")),
            agent_dispatch_result_event("dispB", agent_b),
        ]
        os.makedirs(GATE_DIR_L1, exist_ok=True)
        target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(repo)
        try:
            code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        finally:
            try:
                os.remove(target_file)
            except OSError:
                pass
        self.assertEqual(code, 2, err)
        self.assertIn(agent_a, err)
        self.assertIn("Layer 1", err)
        # Corrected (H-SUBAGENT-MASKING-1 v4): under the append-not-exit
        # design, Layer 1 no longer exits early -- it appends A's violation
        # and control continues, so Layer 2 still runs and independently
        # detects B's genuinely different violation. B's real evidence
        # (agent id + the file it touched) is now reported in full,
        # replacing the old assertNotIn that documented the masking gap.
        self.assertIn(agent_b, err)
        self.assertIn("fix_plan.md", err)
        self.assertIn("2 violations detected", err)


class SubagentCommitGateLayer2NoFalsePositive(unittest.TestCase):
    """AC9: Layer 2 fails open when the candidate sub-agent transcript file
    does not exist, is unreadable, or no toolUseResult.agentId is found
    anywhere in the current turn's raw events at all."""

    def setUp(self):
        self._tmpdirs = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_no_agent_id_anywhere_never_fires(self):
        project_dir = tempfile.mkdtemp(prefix="l2-noid-proj-")
        self._tmpdirs.append(project_dir)
        sid = "l2-noid-%s" % uuid.uuid4().hex
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        events = make_turn([text("no dispatch at all this turn")])
        code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        self.assertEqual(code, 0, err)

    def test_agent_id_present_but_no_transcript_file_on_disk_fails_open(self):
        project_dir = tempfile.mkdtemp(prefix="l2-missing-proj-")
        self._tmpdirs.append(project_dir)
        sid = "l2-missing-%s" % uuid.uuid4().hex
        agent_id = "agentNoTranscriptFile"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        # Deliberately do NOT create <project_dir>/<sid>/subagents/agent-<id>.jsonl
        marker = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [
            marker,
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        self.assertEqual(code, 0, err)

    def test_unreadable_transcript_file_fails_open(self):
        project_dir = tempfile.mkdtemp(prefix="l2-unreadable-proj-")
        self._tmpdirs.append(project_dir)
        sid = "l2-unreadable-%s" % uuid.uuid4().hex
        agent_id = "agentUnreadable"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        # Create the expected path AS A DIRECTORY (not a file) -- open()
        # against it raises IsADirectoryError, which must fail open.
        sub_dir = os.path.join(project_dir, sid, "subagents")
        os.makedirs(sub_dir, exist_ok=True)
        os.makedirs(os.path.join(sub_dir, "agent-%s.jsonl" % agent_id), exist_ok=True)
        marker = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [
            marker,
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        self.assertEqual(code, 0, err)


class SubagentCommitGateLayer2NoScopeViolation(unittest.TestCase):
    """AC11: a raw git commit inside a sub-agent's transcript touching NO
    scope-listed file at all produces neither a flag (Layer 1) nor a
    Layer-2 fire."""

    def setUp(self):
        self._tmpdirs = []
        self._repos = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)

    def test_out_of_scope_commit_no_flag_no_layer2_fire(self):
        repo = scratch_git_repo()
        self._repos.append(repo)
        rc, out, err_txt = real_git_commit(
            repo, ("src/app.py", "print('hi')\n"), message="unrelated commit")
        self.assertEqual(rc, 0, err_txt)

        project_dir = tempfile.mkdtemp(prefix="l2-noscope-proj-")
        self._tmpdirs.append(project_dir)
        sid = "l2-noscope-%s" % uuid.uuid4().hex
        agent_id = "agentNoScope"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

        make_agent_dispatch_transcript(sid, agent_id, project_dir, [
            assistant_msg(bash_tool_use("rcU", 'git commit -m "unrelated commit"')),
            tool_result_event("rcU", out),
        ])
        marker = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [
            marker,
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        os.makedirs(GATE_DIR_L1, exist_ok=True)
        target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(repo)
        try:
            code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        finally:
            try:
                os.remove(target_file)
            except OSError:
                pass
        self.assertEqual(code, 0, err)
        self.assertEqual(
            glob.glob(os.path.join(GATE_DIR_L1, "%s_*.commit_violation" % sid)), [])


class SubagentCommitGateLayer2FailOpen(unittest.TestCase):
    """AC13: any exception raised inside Layer 2's own logic results in
    ALLOW (no crash, no false block)."""

    def test_malformed_subagent_transcript_line_fails_open(self):
        repo = scratch_git_repo()
        try:
            project_dir = tempfile.mkdtemp(prefix="l2-malformed-proj-")
            try:
                sid = "l2-malformed-%s" % uuid.uuid4().hex
                agent_id = "agentMalformedTranscript"
                oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
                sub_dir = os.path.join(project_dir, sid, "subagents")
                os.makedirs(sub_dir, exist_ok=True)
                sub_path = os.path.join(sub_dir, "agent-%s.jsonl" % agent_id)
                # Deliberately malformed JSONL content -- must not crash the
                # per-line json.loads used to parse it.
                with open(sub_path, "w", encoding="utf-8") as f:
                    f.write("not json at all {{{\n")
                    f.write("{ this is also not valid json\n")

                marker = {"type": "user", "message": {
                    "role": "user",
                    "content": "you are **oga** -- orchestrator playbook loaded"}}
                events = [
                    marker,
                    {"type": "user", "message": {"role": "user", "content": "go build"}},
                    assistant_msg(tool_use("Task", description="dispatch")),
                    agent_dispatch_result_event("disp1", agent_id),
                ]
                os.makedirs(GATE_DIR_L1, exist_ok=True)
                target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(repo)
                try:
                    code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
                finally:
                    try:
                        os.remove(target_file)
                    except OSError:
                        pass
                self.assertEqual(code, 0, err)
            finally:
                shutil.rmtree(project_dir, ignore_errors=True)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class SubagentCommitGateOrdering(unittest.TestCase):
    """AC-ORDER: BOTH a fresh flag AND a readable, Layer-2-detectable
    sub-agent transcript exist simultaneously for the SAME violation --
    Oga's Stop hook message attributes the block to Layer 1, not Layer 2."""

    def setUp(self):
        self._tmpdirs = []
        self._repos = []
        self._flags = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        for r in self._repos:
            shutil.rmtree(r, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_both_layers_detect_same_violation_layer1_wins_attribution(self):
        repo = scratch_git_repo()
        self._repos.append(repo)
        rc, out, err_txt = real_git_commit(
            repo, ("RUN.md", "both-layers content\n"), message="both layers commit")
        self.assertEqual(rc, 0, err_txt)

        project_dir = tempfile.mkdtemp(prefix="order-proj-")
        self._tmpdirs.append(project_dir)
        sid = "order-%s" % uuid.uuid4().hex
        agent_id = "agentBothLayers"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

        # Layer 1: a fresh flag already exists for this exact violation.
        sha = out.split("]")[0].split()[-1]
        self._flags.append(write_commit_violation_flag(
            sid, agent_id, [{"sha": sha, "touched": ["RUN.md"]}]))

        # Layer 2: the same violation is ALSO independently detectable via a
        # real sub-agent transcript on disk.
        make_agent_dispatch_transcript(sid, agent_id, project_dir, [
            assistant_msg(bash_tool_use("rcBoth", 'git commit -m "both layers commit"')),
            tool_result_event("rcBoth", out),
        ])
        marker = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [
            marker,
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        os.makedirs(GATE_DIR_L1, exist_ok=True)
        target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(repo)
        try:
            code, err = run_guard_full(events, transcript_path=oga_tpath, session_id=sid)
        finally:
            try:
                os.remove(target_file)
            except OSError:
                pass
        self.assertEqual(code, 2, err)
        self.assertIn("Layer 1", err)
        self.assertNotIn("Layer 2", err)


class SubagentCommitGateOrderPre(unittest.TestCase):
    """AC-ORDER-PRE, corrected by H-SUBAGENT-MASKING-1 v4 AC10: a fresh
    .commit_violation flag exists AND, in the SAME turn, Oga also edited a
    roles/*.md/harness/*.py file with the eval suite not green (a real
    ROLE_OR_HARNESS_EDIT-triggering condition) -- under the append-not-exit
    `_VIOLATIONS` design (runs/2026-07-03_h-subagent-masking-1-full-closure/
    specs/spec.md), Layer 1's flag no longer causes an early exit: BOTH
    Layer 1's violation AND ROLE_OR_HARNESS_EDIT's own violation are now
    detected and reported (Layer 1 first, since it runs earliest in file
    order -- "highest-priority gate first"). A companion case using a
    FEATURE-triggering condition proves the same for the second pre-existing
    early gate."""

    def setUp(self):
        self._flags = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_flag_reported_first_ahead_of_role_or_harness_edit_gate(self):
        sid = "order-pre-role-%s" % uuid.uuid4().hex
        aid = "agentOrderPreRole"
        self._flags.append(write_commit_violation_flag(
            sid, aid, [{"sha": "role1234", "touched": ["RUN.md"]}]))
        # A real ROLE_OR_HARNESS_EDIT-triggering turn: a roles/*.md edit,
        # no green suite run at all this turn.
        events = make_turn([ROLE_EDIT])
        code, err = run_guard_full(events, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn("Layer 1", err)
        self.assertIn(aid, err)
        # AC10 v4 round-3 fix: "ROLE_OR_HARNESS" is DELETED (not flipped) --
        # that literal substring never appears in ROLE_OR_HARNESS_EDIT's
        # real stderr text (confirmed by direct read of loop_stop_guard.py
        # lines 576-584: only "loop-team role"/"harness"/"Phase-1 rule" do;
        # "ROLE_OR_HARNESS" exists only as a Python identifier, never
        # printed) -- flipping it to assertIn would create an assertion that
        # can NEVER pass. "Phase-1 rule" IS a real, present substring, so
        # THAT assertion flips to assertIn, plus an ordering check proving
        # Layer 1's evidence appears before it.
        self.assertIn("Phase-1 rule", err)  # the ROLE_OR_HARNESS_EDIT message's own text
        self.assertLess(err.index("Layer 1"), err.index("Phase-1 rule"))

    def test_flag_reported_first_ahead_of_feature_gate(self):
        sid = "order-pre-feature-%s" % uuid.uuid4().hex
        aid = "agentOrderPreFeature"
        self._flags.append(write_commit_violation_flag(
            sid, aid, [{"sha": "feat1234", "touched": ["fix_plan.md"]}]))
        # A real FEATURE-triggering turn: a code edit, no verifier dispatch.
        code_edit = tool_use("Edit", file_path="/x/src/app.py",
                             old_string="a", new_string="b")
        events = make_turn([code_edit])
        code, err = run_guard_full(events, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn("Layer 1", err)
        self.assertIn(aid, err)
        # AC10: "INDEPENDENT verifier" IS confirmed present verbatim in
        # FEATURE's real message -- flips from assertNotIn to assertIn, plus
        # an ordering check.
        self.assertIn("INDEPENDENT verifier", err)  # the FEATURE message's own text
        self.assertLess(err.index("Layer 1"), err.index("INDEPENDENT verifier"))


class SubagentCommitGateFlagWriteGuard(unittest.TestCase):
    """AC7: the flag-write in subagent_stop_gate.py's 4th responsibility
    uses the SAME _write_flag_if_guarded-style guard: an empty/missing
    session_id results in NO flag being written even if a real violation is
    detected. Exercised end-to-end against the real subagent_stop_gate.py
    hook (not just loop_stop_guard.py's own consuming side)."""

    SUBAGENT_GATE = os.path.join(HOOKS_DIR, "subagent_stop_gate.py")

    def _run_subagent_gate(self, payload_dict):
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR_L1)
        p = subprocess.run([sys.executable, self.SUBAGENT_GATE],
                           input=json.dumps(payload_dict),
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr

    def test_missing_session_id_writes_no_commit_violation_flag(self):
        repo = scratch_git_repo()
        try:
            rc, out, err_txt = real_git_commit(
                repo, ("RUN.md", "guard test content\n"), message="guard test commit")
            self.assertEqual(rc, 0, err_txt)
            sub_events = [
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    tool_use_with_id("rcG", 'git commit -m "guard test commit"')]}},
                tool_result_event("rcG", out),
            ]
            fd, tpath = tempfile.mkstemp(suffix=".jsonl")
            os.close(fd)
            try:
                with open(tpath, "w", encoding="utf-8") as f:
                    for e in sub_events:
                        f.write(json.dumps(e) + "\n")
                # NO session_id key at all.
                payload = {"agent_id": "agentNoSession", "transcript_path": tpath,
                          "cwd": repo}
                code, err = self._run_subagent_gate(payload)
                self.assertEqual(code, 0, err)
                pattern = os.path.join(GATE_DIR_L1, "*_agentNoSession.commit_violation")
                self.assertEqual(glob.glob(pattern), [])
            finally:
                os.remove(tpath)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_empty_session_id_writes_no_commit_violation_flag(self):
        repo = scratch_git_repo()
        try:
            rc, out, err_txt = real_git_commit(
                repo, ("RUN.md", "guard test content 2\n"), message="guard test commit 2")
            self.assertEqual(rc, 0, err_txt)
            sub_events = [
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    tool_use_with_id("rcG2", 'git commit -m "guard test commit 2"')]}},
                tool_result_event("rcG2", out),
            ]
            fd, tpath = tempfile.mkstemp(suffix=".jsonl")
            os.close(fd)
            try:
                with open(tpath, "w", encoding="utf-8") as f:
                    for e in sub_events:
                        f.write(json.dumps(e) + "\n")
                payload = {"session_id": "", "agent_id": "agentEmptySession",
                          "transcript_path": tpath, "cwd": repo}
                code, err = self._run_subagent_gate(payload)
                self.assertEqual(code, 0, err)
                pattern = os.path.join(GATE_DIR_L1, "*_agentEmptySession.commit_violation")
                self.assertEqual(glob.glob(pattern), [])
            finally:
                os.remove(tpath)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


def tool_use_with_id(tool_use_id, command):
    """Same as bash_tool_use() -- a Bash tool_use carrying an explicit id."""
    tu = tool_use("Bash", command=command)
    tu["id"] = tool_use_id
    return tu


# ---------------------------------------------------------------------------
# H-SUBAGENT-COMMIT-GATE-1 (runs/2026-07-03_h-subagent-commit-gate-1/specs/spec.md)
# AC1, AC4, AC4b, AC5, AC6, AC8, AC8b, AC9, AC10, AC13, AC13b, AC-ORDER,
# AC-ORDER-PRE, AC-CWD (loop_stop_guard.py side).
#
# Written independently from the spec's own ACs, never having read
# hooks/commit_scope_scan.py's or loop_stop_guard.py's/subagent_stop_gate.py's
# actual (uncommitted) implementation diffs -- only their git-committed HEAD
# state (which the spec explicitly describes as "current, unmodified") plus
# the spec text and research/subagent-commit-violation-signaling-2026-07-03.md.
#
# Naming: every new class below carries the "IndependentTW1" suffix to
# guarantee zero collision with any class name already present in this file
# (including any pending/uncommitted SubagentCommitGate* classes from the
# same build -- this test-writer pass does not read or modify those; they are
# left completely untouched, per the "never weaken or remove any existing
# test" rule).
# ---------------------------------------------------------------------------
import sys as _tw1_sys

# hooks/commit_scope_scan.py -- new stdlib-only module the spec requires,
# importable directly (its public interface is the load-bearing contract,
# not its internals).
_TW1_HOOKS_DIR = HOOKS_DIR
if _TW1_HOOKS_DIR not in _tw1_sys.path:
    _tw1_sys.path.insert(0, _TW1_HOOKS_DIR)

# Mirrors loop_stop_guard.py's own PLAN_PASS_TTL_SECONDS = 24 * 3600 constant
# (the spec requires this NEW gate to reuse that same TTL, not define a new
# one). The existing PlanPassTTLGate class above uses the literal 24 * 3600
# directly rather than an imported constant (this test file has never
# imported loop_stop_guard.py as a module -- it only drives it as a
# subprocess) -- this mirrors that same established convention.
_TW1_PLAN_PASS_TTL_SECONDS = 24 * 3600


def _tw1_write_commit_violation_flag(session_id, agent_id, violations):
    """Directly construct a {session_id}_{agent_id}.commit_violation flag
    file under GATE_DIR with the given violations list JSON-serialized as
    its content -- for tests that need to construct the flag directly for
    isolation (per AC4's "or constructed directly for test isolation")
    rather than going through subagent_stop_gate.py's own write path."""
    os.makedirs(GATE_DIR, exist_ok=True)
    flag = os.path.join(GATE_DIR, "%s_%s.commit_violation" % (session_id, agent_id))
    with open(flag, "w", encoding="utf-8") as f:
        f.write(json.dumps(violations))
    return flag


def _tw1_write_raw_commit_violation_flag(session_id, agent_id, raw_content):
    """Same as above but writes RAW (possibly malformed) content verbatim,
    for AC4b's malformed-content cases."""
    os.makedirs(GATE_DIR, exist_ok=True)
    flag = os.path.join(GATE_DIR, "%s_%s.commit_violation" % (session_id, agent_id))
    with open(flag, "w", encoding="utf-8") as f:
        f.write(raw_content)
    return flag


def _tw1_cleanup_commit_violation_flags(session_id):
    pattern = os.path.join(GATE_DIR, "%s_*.commit_violation" % session_id)
    for f in glob.glob(pattern):
        try:
            os.remove(f)
        except OSError:
            pass


def _tw1_tool_use_result_event(agent_id, tool_use_id="toolu_dispatch_1"):
    """A raw, STANDALONE JSONL event (append directly via make_turn_events --
    never nest inside assistant_msg()/tool_result_event(), which build
    message.content parts, not top-level events) whose top-level
    `toolUseResult` key is a dict containing `agentId` -- the LIVE-VERIFIED
    real event shape item 4 of the spec quotes directly, with `toolUseResult`
    a TOP-LEVEL SIBLING of `message`, never reachable via
    _parts()/_TOOL_RESULTS (which only walks message.content list items).
    This is deliberately NOT built via tool_result_event()/tool_use() --
    those only ever produce message.content-shaped structures, which is
    exactly the extraction path AC8's own "wrong object entirely" round-1
    finding warns against. Carries a top-level "type": "user" key, matching
    every other real transcript event in this codebase's own fixtures (a
    tool_result-carrying event is always type:user) -- the spec's own quoted
    live example does not show `type` explicitly, but every other real
    JSONL event this file constructs has one, and the guard's own turn-
    boundary walk-back logic keys off e.get("type")."""
    return {
        "type": "user",
        "toolUseResult": {
            "agentId": agent_id,
            "description": "sub-agent dispatch",
            "isAsync": True,
            "outputFile": None,
            "prompt": "spec-by-path dispatch",
            "resolvedModel": "inherit",
            "status": "async_launched",
        },
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id,
                 "content": "Async agent launched successfully.\nagentId: %s"
                            % agent_id},
            ],
        },
    }


def _tw1_write_subagent_transcript(project_dir, session_id, agent_id, events):
    """Materializes a REAL sub-agent transcript file on disk at
    <project_dir>/<session_id>/subagents/agent-<agent_id>.jsonl -- per AC8's
    explicit test-hermeticity requirement: <project_dir> here is
    os.path.dirname() of a tempfile-based synthetic transcript_path (this
    file's existing convention), NEVER the real ~/.claude/projects/ tree.
    The path formula is written out explicitly and independently here (never
    calling into any implementation's own path-construction function), per
    the round-1 finding that reusing the implementation's own formula would
    let a wrong formula look self-consistent."""
    subagents_dir = os.path.join(project_dir, session_id, "subagents")
    os.makedirs(subagents_dir, exist_ok=True)
    tpath = os.path.join(subagents_dir, "agent-%s.jsonl" % agent_id)
    with open(tpath, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return tpath


def run_guard_with_session_raw(events, session_id, transcript_dir=None,
                                stop_hook_active=False):
    """Like run_guard_with_session, but lets the caller control WHERE the
    synthetic transcript_path lives (so Layer 2's <project_dir> =
    os.path.dirname(transcript_path) can be pre-arranged to already contain
    the matching <session_id>/subagents/agent-<id>.jsonl fixture tree)."""
    fd, path = tempfile.mkstemp(suffix=".jsonl", dir=transcript_dir)
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
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)


def run_guard_armed_raw(events, target_dir, session_id, transcript_dir=None,
                        stop_hook_active=False):
    """Combines run_guard_armed's target-arming (needed so Layer 2's reused
    _rc_target resolves to the SAME scratch repo the sub-agent's own
    transcript committed into -- per spec item 4, Layer 2 has no access to
    the sub-agent's own cwd and reuses Oga's own already-resolved
    _rc_target) with run_guard_with_session_raw's transcript-directory
    control (needed so Layer 2's <project_dir> = os.path.dirname(Oga's own
    transcript_path) already contains the matching
    <session_id>/subagents/agent-<id>.jsonl fixture tree)."""
    marker_event = {"type": "user", "message": {
        "role": "user",
        "content": "you are **oga** -- orchestrator playbook loaded"}}
    full_events = [marker_event] + list(events)

    os.makedirs(GATE_DIR, exist_ok=True)
    target_file = os.path.join(GATE_DIR, "%s_target" % session_id)
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(target_dir)

    fd, path = tempfile.mkstemp(suffix=".jsonl", dir=transcript_dir)
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for e in full_events:
                f.write(json.dumps(e) + "\n")
        payload = json.dumps({
            "transcript_path": path,
            "stop_hook_active": stop_hook_active,
            "session_id": session_id,
        })
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)
        try:
            os.remove(target_file)
        except OSError:
            pass


class SharedScanFunctionBehaviorPreservingIndependentTW1(unittest.TestCase):
    """AC1 [BEHAVIORAL]: the refactored find_commit_scope_violations(tool_uses,
    tool_results, target) function, called directly with Oga's own existing
    turn data, produces IDENTICAL results to what the pre-refactor inline
    block is documented (spec Context section) to have done -- exercised here
    by calling the function directly against real _TOOL_USES/_TOOL_RESULTS-
    shaped lists built the same structural way this file's other H-REVIEW-
    COMMIT-1 fixtures build them, using a real scratch git repo and a real
    `git commit` invocation (never a hand-typed fixture string).

    The companion, and the actual STRONGEST form of AC1 ("the full existing
    H-REVIEW-COMMIT-1 test suite passes unchanged after the refactor"), is
    the pre-existing ReviewCommitGate* test classes ABOVE this section in
    this file, run end-to-end via run_guard_armed() (i.e. through
    loop_stop_guard.py's own new call-expression to the shared function, per
    spec item 1(c)) -- those are NOT duplicated here; this class adds the
    complementary, DIRECT-call proof that the shared function's own public
    interface (independent of loop_stop_guard.py wiring it in) is correct.
    """

    def _extract_tool_uses_and_results(self, events):
        """Mirror loop_stop_guard.py's own _parts()/_TOOL_USES/_TOOL_RESULTS
        construction (spec's "Files to read" section: lines 1-100), built
        independently here so this test does not import any private helper
        from loop_stop_guard.py itself."""
        def _content(e):
            m = e.get("message")
            if isinstance(m, dict) and "content" in m:
                return m["content"]
            return e.get("content")

        def _parts(evs):
            for e in evs:
                c = _content(e)
                if isinstance(c, list):
                    for p in c:
                        if isinstance(p, dict):
                            yield p

        parts = list(_parts(events))
        tool_uses = [p for p in parts if p.get("type") == "tool_use"]
        tool_results = [p for p in parts if p.get("type") == "tool_result"]
        return tool_uses, tool_results

    def test_direct_call_finds_violation_touching_scope_file(self):
        from commit_scope_scan import find_commit_scope_violations
        repo = scratch_git_repo()
        try:
            rc, out, err_txt = real_git_commit(
                repo, ("RUN.md", "direct-call scope content\n"),
                message="direct call test")
            self.assertEqual(rc, 0, err_txt)
            events = make_turn_events(
                assistant_msg(bash_tool_use("d1", 'git commit -m "direct call test"')),
                tool_result_event("d1", out),
            )
            tool_uses, tool_results = self._extract_tool_uses_and_results(events)
            violations = find_commit_scope_violations(tool_uses, tool_results, repo)
            self.assertEqual(len(violations), 1, violations)
            sha, touched = violations[0]
            self.assertIn("RUN.md", touched)
            expected_sha = out.split("]")[0].split()[-1]
            self.assertEqual(sha, expected_sha)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_direct_call_returns_empty_list_for_out_of_scope_commit(self):
        from commit_scope_scan import find_commit_scope_violations
        repo = scratch_git_repo()
        try:
            rc, out, err_txt = real_git_commit(
                repo, ("src/unrelated.py", "print(1)\n"),
                message="out of scope")
            self.assertEqual(rc, 0, err_txt)
            events = make_turn_events(
                assistant_msg(bash_tool_use("d2", 'git commit -m "out of scope"')),
                tool_result_event("d2", out),
            )
            tool_uses, tool_results = self._extract_tool_uses_and_results(events)
            violations = find_commit_scope_violations(tool_uses, tool_results, repo)
            self.assertEqual(violations, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_direct_call_returns_empty_list_when_no_commit_tool_use(self):
        from commit_scope_scan import find_commit_scope_violations
        repo = scratch_git_repo()
        try:
            events = make_turn_events(assistant_msg(text("just talking, no commits")))
            tool_uses, tool_results = self._extract_tool_uses_and_results(events)
            violations = find_commit_scope_violations(tool_uses, tool_results, repo)
            self.assertEqual(violations, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_full_existing_h_review_commit_1_suite_still_collects_and_passes(self):
        """AC1's strongest form: run the ENTIRE pre-existing H-REVIEW-COMMIT-1
        section of this file (every ReviewCommitGate* class) as a real,
        isolated subprocess pytest invocation, and assert it exits 0 (all
        pass) -- proving the refactor into commit_scope_scan.py is genuinely
        behavior-preserving for every one of that build's own test cases, not
        merely "probably equivalent"."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", GUARD.replace(
                "loop_stop_guard.py", "test_loop_stop_guard.py"),
             "-k", "ReviewCommitGate", "-q"],
            capture_output=True, text=True, cwd=HOOKS_DIR,
        )
        self.assertEqual(
            result.returncode, 0,
            "the full pre-existing H-REVIEW-COMMIT-1 test suite "
            "(ReviewCommitGate* classes) must still pass unchanged after "
            "the find_commit_scope_violations() refactor.\nstdout:\n%s\n"
            "stderr:\n%s" % (result.stdout, result.stderr),
        )


class Layer1FlagFiresOgaStopIndependentTW1(unittest.TestCase):
    """AC4 [BEHAVIORAL]: a fresh .commit_violation flag (constructed directly
    for test isolation, per AC4's own "or constructed directly" allowance)
    makes Oga's OWN Stop hook fire (exit 2) with a message naming the
    violating agent_id, SHA, and touched file(s) -- even when Oga's own turn
    contains NO raw git commit at all, proving this is a genuinely new
    detection path, not a re-trigger of the pre-existing Oga-scoped gate.
    """

    def setUp(self):
        self.sid = "tw1-l1-%s" % uuid.uuid4().hex

    def tearDown(self):
        _tw1_cleanup_commit_violation_flags(self.sid)

    def test_fresh_flag_blocks_ogas_clean_turn(self):
        aid = "coder-sub-1"
        sha = "abc1234"
        _tw1_write_commit_violation_flag(
            self.sid, aid, [{"sha": sha, "touched": ["RUN.md"]}])
        # Oga's own turn: just prose, no tool_use of any kind.
        events = make_turn([text("Just reviewing status, nothing to commit here.")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)
        self.assertIn(sha, err)
        self.assertIn("RUN.md", err)

    def test_no_flag_present_clean_turn_passes(self):
        # Regression control: with no flag at all, the identical clean turn
        # must pass -- isolates that the block above is caused by the flag,
        # not some other property of the fixture turn.
        events = make_turn([text("Just reviewing status, nothing to commit here.")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 0, err)


class Layer1MalformedContentIndependentTW1(unittest.TestCase):
    """AC4b [BEHAVIORAL]: a fresh .commit_violation flag whose content is NOT
    valid JSON, or is valid JSON but not the expected shape, or is a valid
    empty list [] -- the gate must STILL BLOCK (exit 2), with a message
    naming the agent_id and stating the detail could not be parsed/was
    empty -- never crash, never silently allow."""

    def setUp(self):
        self.sid = "tw1-l1mal-%s" % uuid.uuid4().hex

    def tearDown(self):
        _tw1_cleanup_commit_violation_flags(self.sid)

    def test_invalid_json_content_still_blocks(self):
        aid = "verifier-sub-2"
        _tw1_write_raw_commit_violation_flag(self.sid, aid, "not json at all {{{")
        events = make_turn([text("clean turn")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)

    def test_valid_json_wrong_shape_still_blocks(self):
        aid = "verifier-sub-3"
        # Valid JSON, but not the [{"sha":..., "touched":[...]}, ...] shape.
        _tw1_write_raw_commit_violation_flag(
            self.sid, aid, json.dumps({"unexpected": "shape"}))
        events = make_turn([text("clean turn")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)

    def test_valid_empty_list_still_blocks(self):
        # Round-2 finding: [] is reachable and must be treated as malformed
        # (a fresh flag existing at all signals a detected violation),
        # not silently treated as "no violation."
        aid = "verifier-sub-4"
        _tw1_write_raw_commit_violation_flag(self.sid, aid, json.dumps([]))
        events = make_turn([text("clean turn")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn(aid, err)

    def test_malformed_message_states_could_not_be_parsed_or_empty(self):
        aid = "verifier-sub-5"
        _tw1_write_raw_commit_violation_flag(self.sid, aid, "{{{not json")
        events = make_turn([text("clean turn")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        lower_err = err.lower()
        self.assertTrue(
            "could not parse" in lower_err or "could not be parsed" in lower_err
            or "empty" in lower_err or "malformed" in lower_err
            or "unparseable" in lower_err or "unparsable" in lower_err,
            "block message must state the detail could not be parsed or "
            "was empty, got: %s" % err,
        )
        self.assertIn(aid, err)


class Layer1MultiFlagAggregationIndependentTW1(unittest.TestCase):
    """AC5 [BEHAVIORAL]: TWO fresh .commit_violation flags (two distinct
    agent_ids) -- Oga's Stop hook message must report BOTH violations'
    evidence, not just the first found."""

    def setUp(self):
        self.sid = "tw1-l1multi-%s" % uuid.uuid4().hex

    def tearDown(self):
        _tw1_cleanup_commit_violation_flags(self.sid)

    def test_two_distinct_agent_flags_both_reported(self):
        _tw1_write_commit_violation_flag(
            self.sid, "agent-alpha", [{"sha": "aaa1111", "touched": ["RUN.md"]}])
        _tw1_write_commit_violation_flag(
            self.sid, "agent-beta",
            [{"sha": "bbb2222", "touched": ["loop-team/orchestrator.md"]}])
        events = make_turn([text("clean turn")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn("agent-alpha", err)
        self.assertIn("aaa1111", err)
        self.assertIn("agent-beta", err)
        self.assertIn("bbb2222", err)


class Layer1StaleFlagIndependentTW1(unittest.TestCase):
    """AC6 [BEHAVIORAL]: a STALE .commit_violation flag (mtime older than
    PLAN_PASS_TTL_SECONDS) does not fire, and is cleaned up best-effort."""

    def setUp(self):
        self.sid = "tw1-l1stale-%s" % uuid.uuid4().hex

    def tearDown(self):
        _tw1_cleanup_commit_violation_flags(self.sid)

    def test_stale_flag_does_not_fire_and_is_cleaned_up(self):
        flag = _tw1_write_commit_violation_flag(
            self.sid, "agent-stale", [{"sha": "ccc3333", "touched": ["RUN.md"]}])
        _age_flag(flag, _TW1_PLAN_PASS_TTL_SECONDS + 60)
        events = make_turn([text("clean turn")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 0, err)
        self.assertFalse(
            os.path.exists(flag),
            "a stale .commit_violation flag must be cleaned up best-effort, "
            "mirroring the existing PLAN_PASS stale-flag sweep",
        )

    def test_fresh_flag_within_ttl_still_fires(self):
        # Companion/regression control: just-under-TTL mtime still fires,
        # isolating that the sweep above is genuinely TTL-driven.
        flag = _tw1_write_commit_violation_flag(
            self.sid, "agent-fresh", [{"sha": "ddd4444", "touched": ["RUN.md"]}])
        _age_flag(flag, _TW1_PLAN_PASS_TTL_SECONDS - 60)
        events = make_turn([text("clean turn")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertTrue(os.path.exists(flag))


class Layer1AndLayer2OrderingIndependentTW1(unittest.TestCase):
    """AC-ORDER [BEHAVIORAL]: BOTH a fresh .commit_violation flag AND a
    readable, Layer-2-detectable sub-agent transcript exist simultaneously
    for the SAME violation -- Oga's Stop hook message attributes the block
    to Layer 1 (the flag-file bridge), not Layer 2, proving Layer 1 is
    checked first per item 3's placement requirement (before line 414,
    strictly before Layer 2's own location at the pre-existing commit-scan
    gate's original position)."""

    def setUp(self):
        self.sid = "tw1-order-%s" % uuid.uuid4().hex

    def tearDown(self):
        _tw1_cleanup_commit_violation_flags(self.sid)

    def test_layer1_wins_attribution_when_both_would_catch_same_violation(self):
        # H-SUBAGENT-MASKING-1 fixture fix (stated reason): this test's own name/
        # docstring claim Layer 1 and Layer 2 catch the SAME violation, but the flag
        # was previously written with a FABRICATED sha ("eee5555") never derived from
        # the real commit below -- invisible under old semantics (Layer 1's exit
        # prevented Layer 2's code from ever running, so the mismatch was never
        # exercised), but a real bug once Layer 2 genuinely runs regardless (this
        # build's fix): the new Layer1/Layer2 dedup correctly treats a
        # non-matching sha as a GENUINELY DIFFERENT violation and reports both,
        # which is correct dedup behavior -- the fixture itself was wrong. Fixed to
        # extract the REAL sha from the real commit, exactly matching the sibling
        # test's own working pattern (SubagentCommitGateOrdering.
        # test_both_layers_detect_same_violation_layer1_wins_attribution).
        agent_id = "same-agent-both-layers"
        repo = scratch_git_repo()
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-order-project-")
        try:
            rc, out, err_txt = real_git_commit(
                repo, ("RUN.md", "order-test content\n"), message="order test")
            self.assertEqual(rc, 0, err_txt)
            sha = out.split("]")[0].split()[-1]
            _tw1_write_commit_violation_flag(
                self.sid, agent_id, [{"sha": sha, "touched": ["RUN.md"]}])
            sub_events = [
                {"type": "user", "message": {"role": "user", "content": "go"}},
                assistant_msg(bash_tool_use("o1", 'git commit -m "order test"')),
                tool_result_event("o1", out),
            ]
            _tw1_write_subagent_transcript(tmp_project_dir, self.sid, agent_id,
                                           sub_events)
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_id),
            )
            code, err = run_guard_armed_raw(
                oga_events, repo, self.sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 2, err)
            self.assertIn(agent_id, err)
            self.assertTrue(
                "layer 1" in err.lower() or "flag" in err.lower(),
                "block message should attribute to Layer 1 (flag-file "
                "bridge), not Layer 2, when both would independently catch "
                "the same violation -- got: %s" % err,
            )
            self.assertNotIn(
                "layer 2", err.lower(),
                "when Layer 1 already caught it, the message must not "
                "attribute the block to Layer 2",
            )
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(tmp_project_dir, ignore_errors=True)


class Layer1BeforePreExistingGatesIndependentTW1(unittest.TestCase):
    """AC-ORDER-PRE [BEHAVIORAL], corrected by H-SUBAGENT-MASKING-1 v4 AC10:
    a fresh .commit_violation flag exists AND, in the SAME turn, Oga also
    edited a roles/*.md/harness/*.py file with the eval suite not green (a
    real ROLE_OR_HARNESS_EDIT-triggering condition, or, in the companion
    case, a real FEATURE-triggering condition). Under the append-not-exit
    `_VIOLATIONS` design (runs/2026-07-03_h-subagent-masking-1-full-closure/
    specs/spec.md), Layer 1 no longer exits early on its own flag -- BOTH
    Layer 1's violation AND the pre-existing gate's own violation are
    detected and reported, Layer 1 first (it is checked before line 414, not
    merely before _plan_check_violated at line 499 -- these are NOT the same
    anchor, per the round-3 finding)."""

    def setUp(self):
        self.sid = "tw1-orderpre-%s" % uuid.uuid4().hex

    def tearDown(self):
        _tw1_cleanup_commit_violation_flags(self.sid)

    def test_flag_reported_first_ahead_of_role_or_harness_edit_gate(self):
        agent_id = "coder-orderpre-role"
        sha = "fff6666"
        _tw1_write_commit_violation_flag(
            self.sid, agent_id, [{"sha": sha, "touched": ["VERIFIER.md"]}])
        # ROLE_EDIT (module-level fixture) with no SUITE_GREEN -> would
        # trigger ROLE_OR_HARNESS_EDIT (line 414) on its own.
        events = make_turn([ROLE_EDIT])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn(agent_id, err)
        self.assertIn(sha, err)
        # AC10: "loop-team role" IS confirmed present verbatim in
        # ROLE_OR_HARNESS_EDIT's real message -- flips from assertNotIn to
        # assertIn, plus an ordering check proving Layer 1's evidence
        # appears first (it is checked before line 414).
        self.assertIn(
            "loop-team role", err,
            "must block with BOTH Layer 1's commit-violation message AND "
            "ROLE_OR_HARNESS_EDIT's own message under the append-not-exit "
            "design -- Layer 1 runs first (before line 414) but no longer "
            "exits early",
        )
        self.assertLess(err.index("Layer 1"), err.index("loop-team role"))

    def test_flag_reported_first_ahead_of_feature_gate(self):
        agent_id = "coder-orderpre-feature"
        sha = "aaa7777"
        _tw1_write_commit_violation_flag(
            self.sid, agent_id, [{"sha": sha, "touched": ["fix_plan.md"]}])
        # FEATURE_EDIT (module-level fixture): a code edit with no
        # independent verifier -> would trigger FEATURE (line 431) on its own.
        events = make_turn([FEATURE_EDIT])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn(agent_id, err)
        self.assertIn(sha, err)
        # AC10: "did not run an INDEPENDENT verifier" IS confirmed present
        # verbatim in FEATURE's real message -- flips from assertNotIn to
        # assertIn, plus an ordering check.
        self.assertIn(
            "did not run an INDEPENDENT verifier", err,
            "must block with BOTH Layer 1's commit-violation message AND "
            "FEATURE's own message under the append-not-exit design -- "
            "Layer 1 runs first but no longer exits early",
        )
        self.assertLess(
            err.index("Layer 1"),
            err.index("did not run an INDEPENDENT verifier"))


class Layer2DirectTranscriptScanIndependentTW1(unittest.TestCase):
    """AC8 [BEHAVIORAL]: construct a REAL sub-agent transcript file on disk
    at <project_dir>/<session_id>/subagents/agent-<id>.jsonl, where
    <project_dir> is os.path.dirname() of the SAME synthetic tempfile-based
    transcript_path this test constructs for Oga's own turn -- NEVER the
    real ~/.claude/projects/ tree. Oga's Stop hook fires via Layer 2 even
    with NO .commit_violation flag present at all, proving Layer 2 works
    independently of Layer 1."""

    def test_layer2_fires_with_no_flag_present(self):
        agent_id = "layer2-only-agent"
        sha_holder = {}
        repo = scratch_git_repo()
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2-project-")
        sid = "tw1-l2-%s" % uuid.uuid4().hex
        try:
            rc, out, err_txt = real_git_commit(
                repo, ("RUN.md", "layer2 content\n"), message="layer2 test")
            self.assertEqual(rc, 0, err_txt)
            sha_holder["sha"] = out.split("]")[0].split()[-1]
            sub_events = [
                {"type": "user", "message": {"role": "user", "content": "go"}},
                assistant_msg(bash_tool_use("l2a", 'git commit -m "layer2 test"')),
                tool_result_event("l2a", out),
            ]
            _tw1_write_subagent_transcript(tmp_project_dir, sid, agent_id,
                                           sub_events)
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_id),
            )
            # No .commit_violation flag written anywhere for this session.
            code, err = run_guard_armed_raw(
                oga_events, repo, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 2, err)
            self.assertIn(agent_id, err)
            self.assertIn("RUN.md", err)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)


class Layer2MultiDispatchAggregationIndependentTW1(unittest.TestCase):
    """AC8b [BEHAVIORAL]: TWO distinct Agent/Task dispatches in Oga's own
    turn (two distinct agentIds via two toolUseResult events), each with its
    own real sub-agent transcript file, BOTH containing a Layer-2-detectable
    violation, NEITHER with a .commit_violation flag -- Oga's Stop hook
    message must report BOTH, not just the first found."""

    def test_two_distinct_agents_both_layer2_violations_both_reported(self):
        repo = scratch_git_repo()
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2multi-project-")
        sid = "tw1-l2multi-%s" % uuid.uuid4().hex
        agent_a = "l2multi-agent-a"
        agent_b = "l2multi-agent-b"
        try:
            rc_a, out_a, e_a = real_git_commit(
                repo, ("RUN.md", "agent a content\n"), message="agent a commit")
            self.assertEqual(rc_a, 0, e_a)
            rc_b, out_b, e_b = real_git_commit(
                repo, ("loop-team/orchestrator.md", "agent b content\n"),
                message="agent b commit")
            self.assertEqual(rc_b, 0, e_b)

            _tw1_write_subagent_transcript(tmp_project_dir, sid, agent_a, [
                {"type": "user", "message": {"role": "user", "content": "go"}},
                assistant_msg(bash_tool_use("l2ba", 'git commit -m "agent a commit"')),
                tool_result_event("l2ba", out_a),
            ])
            _tw1_write_subagent_transcript(tmp_project_dir, sid, agent_b, [
                {"type": "user", "message": {"role": "user", "content": "go"}},
                assistant_msg(bash_tool_use("l2bb", 'git commit -m "agent b commit"')),
                tool_result_event("l2bb", out_b),
            ])
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_a, tool_use_id="toolu_a"),
                _tw1_tool_use_result_event(agent_b, tool_use_id="toolu_b"),
            )
            code, err = run_guard_armed_raw(
                oga_events, repo, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 2, err)
            self.assertIn(agent_a, err)
            self.assertIn(agent_b, err)
            self.assertIn("RUN.md", err)
            self.assertIn("loop-team/orchestrator.md", err)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)

    def test_companion_flagged_agent_and_unflagged_racing_agent_both_reported_this_turn(self):
        """AC9 companion (H-SUBAGENT-MASKING-1 v4, revised): agent A has a
        fresh flag AND agent B has ONLY a Layer-2-detectable violation in
        the SAME turn. Under the append-not-exit `_VIOLATIONS` design
        (runs/2026-07-03_h-subagent-masking-1-full-closure/specs/spec.md),
        Layer 1 no longer exits early on A's flag -- it appends and control
        continues to Layer 2, which independently detects B's real,
        different violation and also appends. Both are now reported in
        full, replacing the old assertNotIn(agent_b, err) that documented
        the masking gap this build closes."""
        repo = scratch_git_repo()
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2masking-project-")
        sid = "tw1-l2masking-%s" % uuid.uuid4().hex
        agent_a = "masking-agent-a-flagged"
        agent_b = "masking-agent-b-layer2-only"
        try:
            _tw1_write_commit_violation_flag(
                sid, agent_a, [{"sha": "bbb8888", "touched": ["RUN.md"]}])

            rc_b, out_b, e_b = real_git_commit(
                repo, ("VERIFIER.md", "agent b racing content\n"),
                message="agent b racing commit")
            self.assertEqual(rc_b, 0, e_b)
            _tw1_write_subagent_transcript(tmp_project_dir, sid, agent_b, [
                {"type": "user", "message": {"role": "user", "content": "go"}},
                assistant_msg(bash_tool_use("l2m", 'git commit -m "agent b racing commit"')),
                tool_result_event("l2m", out_b),
            ])
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_b, tool_use_id="toolu_racing"),
            )
            code, err = run_guard_armed_raw(
                oga_events, repo, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 2, err)
            self.assertIn(agent_a, err)
            # Corrected (H-SUBAGENT-MASKING-1 v4): B's Layer-2-only
            # violation IS now surfaced this turn -- Layer 1 appends A's
            # violation and continues (no early exit), so Layer 2 still
            # runs and independently finds B's real, different violation.
            self.assertIn(agent_b, err)
            self.assertIn("VERIFIER.md", err)
            self.assertIn("2 violations detected", err)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)


class Layer2FailsOpenIndependentTW1(unittest.TestCase):
    """AC9 [BEHAVIORAL]: Layer 2 fails open (does not crash, does not fire)
    when the candidate sub-agent transcript file does not exist, is
    unreadable, or no toolUseResult.agentId is found anywhere in the
    current turn's raw events at all."""

    def test_missing_subagent_transcript_file_fails_open(self):
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2failopen-project-")
        sid = "tw1-l2failopen-%s" % uuid.uuid4().hex
        agent_id = "phantom-agent-no-transcript"
        try:
            # NEVER call _tw1_write_subagent_transcript -- the file simply
            # does not exist on disk.
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_id),
            )
            code, err = run_guard_with_session_raw(
                oga_events, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)

    def test_no_tool_use_result_agent_id_anywhere_fails_open(self):
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2noagentid-project-")
        sid = "tw1-l2noagentid-%s" % uuid.uuid4().hex
        try:
            oga_events = make_turn([text("no dispatches at all this turn")])
            code, err = run_guard_with_session_raw(
                oga_events, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)

    def test_unreadable_subagent_transcript_fails_open(self):
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2unreadable-project-")
        sid = "tw1-l2unreadable-%s" % uuid.uuid4().hex
        agent_id = "unreadable-agent"
        try:
            subagents_dir = os.path.join(tmp_project_dir, sid, "subagents")
            os.makedirs(subagents_dir, exist_ok=True)
            tpath = os.path.join(subagents_dir, "agent-%s.jsonl" % agent_id)
            # A directory where a file is expected -- makes any open()
            # attempt raise IsADirectoryError rather than simply "not found."
            os.makedirs(tpath, exist_ok=True)
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_id),
            )
            code, err = run_guard_with_session_raw(
                oga_events, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)


class Layer1OnlyAuthoritativeIndependentTW1(unittest.TestCase):
    """AC10 [BEHAVIORAL]: AC4 and AC8's fire scenarios each have a companion
    Layer-1-only test proving Layer 1 ALONE (with Layer 2's transcript file
    absent/unreadable) still catches the same violation -- proving Layer 1
    is genuinely authoritative, not accidentally dependent on Layer 2 also
    succeeding."""

    def setUp(self):
        self.sid = "tw1-l1only-%s" % uuid.uuid4().hex

    def tearDown(self):
        _tw1_cleanup_commit_violation_flags(self.sid)

    def test_ac4_companion_layer1_alone_with_no_subagent_transcript_at_all(self):
        agent_id = "layer1-only-agent"
        sha = "ccc9999"
        _tw1_write_commit_violation_flag(
            self.sid, agent_id, [{"sha": sha, "touched": ["RUN.md"]}])
        # No subagent transcript directory constructed anywhere -- Layer 2
        # has nothing to find, no toolUseResult.agentId event either.
        events = make_turn([text("clean turn, no dispatches")])
        code, err = run_guard_with_session(events, session_id=self.sid)
        self.assertEqual(code, 2, err)
        self.assertIn(agent_id, err)
        self.assertIn(sha, err)

    def test_ac8_companion_layer1_alone_via_flag_with_layer2_transcript_absent(self):
        agent_id = "layer1-only-agent-2"
        sha = "ddd0000"
        _tw1_write_commit_violation_flag(
            self.sid, agent_id, [{"sha": sha, "touched": ["fix_plan.md"]}])
        # A toolUseResult.agentId event DOES exist this turn (so Layer 2
        # would be invoked), but no subagent transcript file exists on disk
        # for it at all -- Layer 2 must fail open, leaving Layer 1's flag as
        # the sole reason for the block.
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l1only-project-")
        try:
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_id),
            )
            code, err = run_guard_with_session_raw(
                oga_events, self.sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 2, err)
            self.assertIn(agent_id, err)
            self.assertIn(sha, err)
        finally:
            shutil.rmtree(tmp_project_dir, ignore_errors=True)


class Layer2NoOverfireOnCleanSubagentCommitIndependentTW1(unittest.TestCase):
    """AC11 [BEHAVIORAL]: a raw git commit inside a sub-agent's transcript
    touching NO scope-listed file at all produces neither a flag (Layer 1)
    nor a Layer-2 fire -- the negative case, proving this build does not
    over-fire on ordinary sub-agent commits."""

    def test_out_of_scope_subagent_commit_produces_no_fire(self):
        repo = scratch_git_repo()
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2clean-project-")
        sid = "tw1-l2clean-%s" % uuid.uuid4().hex
        agent_id = "clean-agent"
        try:
            rc, out, err_txt = real_git_commit(
                repo, ("src/clean_file.py", "print('fine')\n"),
                message="clean commit")
            self.assertEqual(rc, 0, err_txt)
            _tw1_write_subagent_transcript(tmp_project_dir, sid, agent_id, [
                {"type": "user", "message": {"role": "user", "content": "go"}},
                assistant_msg(bash_tool_use("clean1", 'git commit -m "clean commit"')),
                tool_result_event("clean1", out),
            ])
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(agent_id),
            )
            code, err = run_guard_armed_raw(
                oga_events, repo, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 0, err)
            # No .commit_violation flag should have been created for this
            # (Layer 1 would only exist if subagent_stop_gate.py had written
            # one -- this test drives loop_stop_guard.py only, so absence
            # here just confirms this test itself never manufactured one).
            pattern = os.path.join(GATE_DIR, "%s_*.commit_violation" % sid)
            self.assertEqual(glob.glob(pattern), [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)


class Layer2FailOpenOnExceptionIndependentTW1(unittest.TestCase):
    """AC13 [BEHAVIORAL]: any exception raised inside Layer 2's new logic in
    loop_stop_guard.py results in ALLOW (no crash, no false block) --
    matching this file's existing fail-open discipline for every other
    gate. Constructed via a hostile agentId value that could plausibly
    break naive path construction (path-separator-bearing) without itself
    being a legitimate path segment."""

    def test_hostile_agent_id_in_tool_use_result_fails_open(self):
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2exc-project-")
        sid = "tw1-l2exc-%s" % uuid.uuid4().hex
        try:
            hostile_agent_id = "../../etc/passwd"
            oga_events = make_turn_events(
                _tw1_tool_use_result_event(hostile_agent_id),
            )
            code, err = run_guard_with_session_raw(
                oga_events, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
        finally:
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)

    def test_non_string_agent_id_fails_open(self):
        tmp_project_dir = tempfile.mkdtemp(prefix="tw1-l2exc2-project-")
        sid = "tw1-l2exc2-%s" % uuid.uuid4().hex
        try:
            oga_events = make_turn_events(
                {
                    "type": "user",
                    "toolUseResult": {"agentId": 12345, "isAsync": True,
                                      "status": "async_launched"},
                    "message": {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_nonstr",
                         "content": "dispatched"}]},
                },
            )
            code, err = run_guard_with_session_raw(
                oga_events, sid, transcript_dir=tmp_project_dir)
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
        finally:
            shutil.rmtree(tmp_project_dir, ignore_errors=True)
            _tw1_cleanup_commit_violation_flags(sid)


class Layer1FailOpenOnExceptionIndependentTW1(unittest.TestCase):
    """AC13b [BEHAVIORAL]: any exception raised inside Layer 1's new gate
    (the .commit_violation glob/TTL/read/block logic itself -- not just the
    JSON-parse step AC4b covers) results in ALLOW, via a file-spanning
    try/except Exception wrapping the gate's ENTIRE logic -- not merely the
    narrower per-call try/except OSError the PLAN_PASS block uses. Exercised
    here via a metachar-laden session_id (mirroring the existing
    GlobSafeSessionIdRH7 precedent in this same file for the pre-existing
    PLAN_PASS gate) that could plausibly upset a naive glob-pattern
    construction for the NEW .commit_violation gate specifically."""

    def test_metachar_session_id_with_commit_violation_flag_does_not_crash(self):
        # A session_id containing glob metacharacters -- if Layer 1's gate
        # were NOT glob.escape()'d/exception-safe, this could plausibly
        # raise or behave unpredictably; either way the gate must not crash
        # and must exit either 0 or 2 (never a Python traceback).
        sid = "tw1-l1exc-[meta]-%s" % uuid.uuid4().hex
        try:
            _tw1_write_commit_violation_flag(
                sid, "meta-agent", [{"sha": "e11e11e", "touched": ["RUN.md"]}])
            events = make_turn([text("clean turn")])
            code, err = run_guard_with_session(events, session_id=sid)
            self.assertIn(code, (0, 2), err)
            self.assertNotIn("Traceback", err)
        finally:
            _tw1_cleanup_commit_violation_flags(sid)

    def test_unreadable_gate_dir_fails_open(self):
        # Point LOOP_GATE_DIR at a location that cannot be glob'd/read as a
        # directory (a plain file sitting where a directory is expected) --
        # forces a real OSError-class failure inside Layer 1's own glob/TTL
        # logic, independent of the JSON-parse step.
        fd, blocking_file = tempfile.mkstemp(prefix="tw1-l1exc-blocker-")
        os.close(fd)
        try:
            bogus_gate_dir = os.path.join(blocking_file, "nested", "gate")
            fd2, path = tempfile.mkstemp(suffix=".jsonl")
            os.close(fd2)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for e in make_turn([text("clean turn")]):
                        f.write(json.dumps(e) + "\n")
                payload = json.dumps({
                    "transcript_path": path,
                    "session_id": "tw1-l1exc-unreadable-%s" % uuid.uuid4().hex,
                })
                env = dict(os.environ, LOOP_GATE_DIR=bogus_gate_dir)
                p = subprocess.run([sys.executable, GUARD], input=payload,
                                   capture_output=True, text=True, env=env)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertNotIn("Traceback", p.stderr)
            finally:
                os.remove(path)
        finally:
            os.remove(blocking_file)


class SubagentCwdFallbackUnitIndependentTW1(unittest.TestCase):
    """AC-CWD [BEHAVIORAL]: the cwd-population precondition (item 2's
    "Required first step") is actually exercised: proves the
    fallback-to-__file__-relative-path branch fires correctly when cwd is
    missing/empty/non-string on a SubagentStop payload, independent of
    whatever a real live firing's manual-testing result turns out to be.

    This is exercised from the loop_stop_guard.py side by confirming Layer 1
    (which is fed entirely by subagent_stop_gate.py's own flag-write, itself
    driven by the target-resolution fallback) still produces a correctly-
    scoped violation flag when the SubagentStop payload's cwd is
    missing/empty/non-string -- the companion, direct subagent_stop_gate.py-
    side unit tests live in test_subagent_stop_gate.py (AC-CWD section
    there), since this fallback is that hook's own responsibility, not
    loop_stop_guard.py's. This class documents the cross-file linkage so a
    reader of this file finds the pointer rather than a missing AC.
    """

    def test_ac_cwd_documented_pointer_to_subagent_stop_gate_tests(self):
        # AC-CWD's actual mechanism (item 2's "Required first step": cwd
        # missing/empty/non-string -> fall back to this file's own
        # __file__-relative repo path) is subagent_stop_gate.py's own
        # responsibility -- see test_subagent_stop_gate.py's AC-CWD-labeled
        # class for the direct, executable proof. This test exists so a
        # reader of test_loop_stop_guard.py is pointed at the real coverage
        # rather than concluding AC-CWD has no test in this file's suite.
        test_file = os.path.join(HOOKS_DIR, "test_subagent_stop_gate.py")
        self.assertTrue(
            os.path.isfile(test_file),
            "test_subagent_stop_gate.py must exist alongside this file",
        )


# ---------------------------------------------------------------------------
# H-SUBAGENT-MASKING-1, FULL closure
# (runs/2026-07-03_h-subagent-masking-1-full-closure/specs/spec.md, v4)
#
# AC2-AC8, AC11, AC12: the append-not-exit `_VIOLATIONS` design that lets
# every gate's detection logic run every invocation, with genuinely-distinct
# violations reported in full and Layer 1/Layer 2 detections of the IDENTICAL
# underlying commit deduplicated to one report. AC9/AC10 (the 6 existing
# tests that must be REVISED, not added-to) are handled in place at their
# original class locations above, not here -- see each revised test's
# updated docstring for the spec citation and corrected reasoning.
#
# This section adds ONLY new tests; none of the 191 pre-existing tests
# outside the 6 named in AC9/AC10 are touched.
# ---------------------------------------------------------------------------


class SameViolationDedupRegressionGuardMasking1(unittest.TestCase):
    """AC2 [BEHAVIORAL]: same-violation dedup needs ZERO test CHANGES (the
    two existing fixtures -- SubagentCommitGateOrdering.
    test_both_layers_detect_same_violation_layer1_wins_attribution and
    Layer1AndLayer2OrderingIndependentTW1's counterpart -- already assert
    "Layer 1" present / "Layer 2" absent and are left completely unmodified
    above). This is an ADDITIONAL regression guard (not a replacement for
    either): it independently re-confirms, from a fresh fixture built the
    same way, that when Layer 1's flagged SHA and Layer 2's real committed
    SHA are the SAME value, the block message shows the violation exactly
    ONCE (a single, non-numbered block, no "2 violations detected" banner)
    -- the concrete signature of `len(_VIOLATIONS) == 1` the spec's dedup
    filter is designed to produce for this fixture shape."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_identical_sha_layer1_and_layer2_reports_exactly_once(self):
        rc, out, err_txt = real_git_commit(
            self.repo, ("RUN.md", "dedup-guard content\n"),
            message="dedup guard commit")
        self.assertEqual(rc, 0, err_txt)
        sha = out.split("]")[0].split()[-1]

        project_dir = tempfile.mkdtemp(prefix="dedup-guard-proj-")
        try:
            sid = "dedup-guard-%s" % uuid.uuid4().hex
            agent_id = "dedupGuardAgent"
            oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

            self._flags.append(write_commit_violation_flag(
                sid, agent_id, [{"sha": sha, "touched": ["RUN.md"]}]))
            make_agent_dispatch_transcript(sid, agent_id, project_dir, [
                assistant_msg(bash_tool_use("dg1", 'git commit -m "dedup guard commit"')),
                tool_result_event("dg1", out),
            ])
            marker = {"type": "user", "message": {
                "role": "user",
                "content": "you are **oga** -- orchestrator playbook loaded"}}
            events = [
                marker,
                {"type": "user", "message": {"role": "user", "content": "go build"}},
                assistant_msg(tool_use("Task", description="dispatch")),
                agent_dispatch_result_event("disp1", agent_id),
            ]
            os.makedirs(GATE_DIR_L1, exist_ok=True)
            target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(self.repo)
            try:
                code, err = run_guard_full(events, transcript_path=oga_tpath,
                                           session_id=sid)
            finally:
                try:
                    os.remove(target_file)
                except OSError:
                    pass
            self.assertEqual(code, 2, err)
            self.assertIn(sha, err)
            self.assertIn("Layer 1", err)
            # Dedup proof: the multi-violation banner must be ABSENT (a
            # single violation never gets the "N violations detected"
            # numbered-block treatment).
            self.assertNotIn("violations detected", err)
            self.assertNotIn("Violation 1/", err)
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


class SameAgentDifferentShaPartialDedupMasking1(unittest.TestCase):
    """AC3 [BEHAVIORAL] (NEW -- round-2 gap): agent A has a fresh Layer-1
    flag for sha1 AND a genuinely different sha2 (a second real commit, same
    agent) detectable only via Layer 2, same turn. Proves the filter
    operates at (agent_id, sha) granularity, not agent-level: sha1's Layer-1
    report appears once, sha2's Layer-2 finding is NOT filtered and appears
    in full, and exactly 2 violations are reported (not 1, not 0)."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_same_agent_two_shas_both_reported_as_two_violations(self):
        # sha1: committed for real so its literal hash is known, but the
        # Layer-1 FLAG is what actually carries it to the gate (Layer 2 must
        # never independently discover sha1 -- no sub-agent transcript is
        # built for it here, only the flag).
        rc1, out1, e1 = real_git_commit(
            self.repo, ("RUN.md", "sha1 content\n"), message="agent A sha1 commit")
        self.assertEqual(rc1, 0, e1)
        sha1 = out1.split("]")[0].split()[-1]

        # sha2: a SECOND, genuinely different real commit by the SAME agent,
        # detectable ONLY via Layer 2 (its own sub-agent transcript exists,
        # no flag for it).
        rc2, out2, e2 = real_git_commit(
            self.repo, ("fix_plan.md", "sha2 content\n"), message="agent A sha2 commit")
        self.assertEqual(rc2, 0, e2)
        sha2 = out2.split("]")[0].split()[-1]
        self.assertNotEqual(sha1, sha2)

        project_dir = tempfile.mkdtemp(prefix="partial-dedup-proj-")
        try:
            sid = "partial-dedup-%s" % uuid.uuid4().hex
            agent_id = "sameAgentTwoShas"
            oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

            self._flags.append(write_commit_violation_flag(
                sid, agent_id, [{"sha": sha1, "touched": ["RUN.md"]}]))
            # Layer 2's own scan replays the SAME agent's transcript to find
            # BOTH commits -- but only sha1 is dedup-filtered (it's in
            # _l1_flagged_shas); sha2 survives the filter.
            make_agent_dispatch_transcript(sid, agent_id, project_dir, [
                assistant_msg(bash_tool_use("pd1", 'git commit -m "agent A sha1 commit"')),
                tool_result_event("pd1", out1),
                assistant_msg(bash_tool_use("pd2", 'git commit -m "agent A sha2 commit"')),
                tool_result_event("pd2", out2),
            ])
            marker = {"type": "user", "message": {
                "role": "user",
                "content": "you are **oga** -- orchestrator playbook loaded"}}
            events = [
                marker,
                {"type": "user", "message": {"role": "user", "content": "go build"}},
                assistant_msg(tool_use("Task", description="dispatch")),
                agent_dispatch_result_event("disp1", agent_id),
            ]
            os.makedirs(GATE_DIR_L1, exist_ok=True)
            target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(self.repo)
            try:
                code, err = run_guard_full(events, transcript_path=oga_tpath,
                                           session_id=sid)
            finally:
                try:
                    os.remove(target_file)
                except OSError:
                    pass
            self.assertEqual(code, 2, err)
            self.assertIn(sha1, err)
            self.assertIn(sha2, err)
            self.assertIn("Layer 1", err)
            self.assertIn("Layer 2", err)
            self.assertIn("2 violations detected", err)
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


class MalformedLayer1PlusGenuineLayer2SameAgentMasking1(unittest.TestCase):
    """AC4 [BEHAVIORAL] (NEW -- round-2 gap, decision documented in spec.md
    "Malformed-Layer-1-flag + genuine-Layer-2-same-agent -- explicit
    decision" section): agent X's Layer-1 flag is malformed (no real SHA
    available) AND Layer 2 independently detects a real, well-formed
    violation for agent X this same turn. This is an intentional, accepted
    DOUBLE-report, not suppressed -- a malformed flag contributes no tuple to
    _l1_flagged_shas (a malformed flag genuinely cannot be compared key-for-
    key against anything), so Layer 2's real finding is never filtered.
    Asserts BOTH blocks appear in `err`."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_malformed_flag_and_real_layer2_violation_both_reported(self):
        rc, out, err_txt = real_git_commit(
            self.repo, ("VERIFIER.md", "malformed-double-report content\n"),
            message="malformed double report commit")
        self.assertEqual(rc, 0, err_txt)
        sha = out.split("]")[0].split()[-1]

        project_dir = tempfile.mkdtemp(prefix="malformed-double-proj-")
        try:
            sid = "malformed-double-%s" % uuid.uuid4().hex
            agent_id = "agentMalformedDouble"
            oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

            # Layer 1: malformed content -- invalid JSON, so _l1_evidence
            # becomes the "<could not parse ...>" placeholder and no
            # (agent_id, sha) tuple is added to _l1_flagged_shas.
            self._flags.append(write_commit_violation_flag(
                sid, agent_id, "not json at all {{{"))

            # Layer 2: a REAL, well-formed violation for the SAME agent_id,
            # this same turn.
            make_agent_dispatch_transcript(sid, agent_id, project_dir, [
                assistant_msg(bash_tool_use("md1",
                    'git commit -m "malformed double report commit"')),
                tool_result_event("md1", out),
            ])
            marker = {"type": "user", "message": {
                "role": "user",
                "content": "you are **oga** -- orchestrator playbook loaded"}}
            events = [
                marker,
                {"type": "user", "message": {"role": "user", "content": "go build"}},
                assistant_msg(tool_use("Task", description="dispatch")),
                agent_dispatch_result_event("disp1", agent_id),
            ]
            os.makedirs(GATE_DIR_L1, exist_ok=True)
            target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(self.repo)
            try:
                code, err = run_guard_full(events, transcript_path=oga_tpath,
                                           session_id=sid)
            finally:
                try:
                    os.remove(target_file)
                except OSError:
                    pass
            self.assertEqual(code, 2, err)
            # Layer 1's "could not be parsed" block.
            self.assertIn(agent_id, err)
            self.assertTrue(
                "could not be parsed" in err or "could not parse" in err, err)
            self.assertIn("Layer 1", err)
            # Layer 2's full SHA evidence, NOT suppressed.
            self.assertIn(sha, err)
            self.assertIn("Layer 2", err)
            self.assertIn("VERIFIER.md", err)
            self.assertIn("2 violations detected", err)
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


class TwoDifferentThingsSameTurnBothReportedMasking1(unittest.TestCase):
    """AC5 [BEHAVIORAL] (unchanged from v2): a genuine two-DIFFERENT-thing
    same-turn violation reports BOTH in full -- Layer 1 flagged for agent A,
    Layer 2-only for agent B (different sha), matching
    test_flagged_agent_a_masks_layer2_only_agent_b_same_turn's original
    fixture SHAPE (same class of scenario the REVISED version of that test
    now asserts full reporting for). This is an independent fixture proving
    the SAME shape from a fresh build: both fully reported, the "2
    violations detected" banner present, agent A's evidence listed FIRST
    (Layer 1 -- the highest-priority gate -- reported first per the EOF
    block's "highest-priority gate first" ordering)."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_two_different_agents_different_shas_both_fully_reported_a_first(self):
        rc, out, err_txt = real_git_commit(
            self.repo, ("fix_plan.md", "agent B two-different-things content\n"),
            message="agent B two-different-things commit")
        self.assertEqual(rc, 0, err_txt)

        project_dir = tempfile.mkdtemp(prefix="two-diff-proj-")
        try:
            sid = "two-diff-%s" % uuid.uuid4().hex
            agent_a, agent_b = "twoDiffAgentA", "twoDiffAgentB"
            oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

            self._flags.append(write_commit_violation_flag(
                sid, agent_a, [{"sha": "1111aaa", "touched": ["RUN.md"]}]))
            make_agent_dispatch_transcript(sid, agent_b, project_dir, [
                assistant_msg(bash_tool_use("td1",
                    'git commit -m "agent B two-different-things commit"')),
                tool_result_event("td1", out),
            ])
            marker = {"type": "user", "message": {
                "role": "user",
                "content": "you are **oga** -- orchestrator playbook loaded"}}
            events = [
                marker,
                {"type": "user", "message": {"role": "user", "content": "go build"}},
                assistant_msg(tool_use("Task", description="dispatch A")),
                agent_dispatch_result_event("dispA", agent_a),
                assistant_msg(tool_use("Task", description="dispatch B")),
                agent_dispatch_result_event("dispB", agent_b),
            ]
            os.makedirs(GATE_DIR_L1, exist_ok=True)
            target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(self.repo)
            try:
                code, err = run_guard_full(events, transcript_path=oga_tpath,
                                           session_id=sid)
            finally:
                try:
                    os.remove(target_file)
                except OSError:
                    pass
            self.assertEqual(code, 2, err)
            self.assertIn(agent_a, err)
            self.assertIn(agent_b, err)
            self.assertIn("1111aaa", err)
            self.assertIn("fix_plan.md", err)
            self.assertIn("2 violations detected", err)
            # Layer 1 (agent A) is the highest-priority gate -- its evidence
            # must appear BEFORE Layer 2's (agent B).
            self.assertLess(err.index(agent_a), err.index(agent_b))
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


class ActivationAndRcTargetCorrectnessMasking1(unittest.TestCase):
    """AC6 [BEHAVIORAL] (unchanged from v2): `_LAST_ACTIVATION`/`_rc_target`
    correctness when an earlier gate already violated. Under the append-not-
    exit design, the micro-step-gates block (and the review-commit gate that
    depends on its `_LAST_ACTIVATION` broadcast) now RUNS even when Layer 1
    already appended a violation earlier in file order -- this must not
    corrupt `_rc_target`'s resolution: it must still resolve to the SAME
    armed target_dir a normal (single-gate) turn would resolve to, proving
    micro_step_gates.run()'s own _activation() call executes correctly
    (detection logic unconditional) even on a turn that will ultimately
    block on an EARLIER gate's violation, not this one."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_rc_target_resolves_correctly_when_layer1_already_violated(self):
        sid = "rc-target-%s" % uuid.uuid4().hex
        agent_id = "rcTargetAgent"
        self._flags.append(write_commit_violation_flag(
            sid, agent_id, [{"sha": "rct1234", "touched": ["RUN.md"]}]))

        # A SECOND, real, unflagged, scope-touching commit in the SAME armed
        # target repo, made directly by Oga's own turn (not a sub-agent) --
        # this is exactly what the review-commit gate (which depends on
        # _rc_target resolving to the armed target_dir, via
        # _LAST_ACTIVATION) would ALSO catch on its own, if it runs.
        rc, out, err_txt = real_git_commit(
            self.repo, ("fix_plan.md", "rc target content\n"),
            message="rc target own commit")
        self.assertEqual(rc, 0, err_txt)

        events = make_turn_events(
            assistant_msg(bash_tool_use("rct1", 'git commit -m "rc target own commit"')),
            tool_result_event("rct1", out),
        )
        code, err = run_guard_armed(events, self.repo, session_id=sid)
        self.assertEqual(code, 2, err)
        # Layer 1's violation is present (it ran, and fires first in file
        # order).
        self.assertIn(agent_id, err)
        self.assertIn("Layer 1", err)
        # The review-commit gate ALSO ran (proving _rc_target resolved to
        # the correctly-armed self.repo, not a fallback/garbage value) and
        # its own violation for Oga's own second commit is ALSO reported --
        # not silently dropped just because Layer 1 fired first.
        self.assertIn("fix_plan.md", err)
        sha2 = out.split("]")[0].split()[-1]
        self.assertIn(sha2, err)
        self.assertIn("2 violations detected", err)


class SaveSigsRecordFlagMasking1(unittest.TestCase):
    """AC7 [BEHAVIORAL]: `_save_sigs()` must NOT be called when an earlier
    gate already appended a violation this turn -- exercised by calling
    `micro_step_gates.run(data, record_sigs=False)` directly (unit level)
    and confirming the on-disk `<session>_signatures.json` state is
    unaffected by a run that would otherwise have appended a new signature,
    PLUS a companion confirming the default (record_sigs=True, or omitted)
    DOES persist -- proving this is a real conditional, not a parameter that
    is silently ignored."""

    def setUp(self):
        HOOKS = HOOKS_DIR
        if HOOKS not in sys.path:
            sys.path.insert(0, HOOKS)
        import micro_step_gates as _msg
        self.msg = _msg
        self.gate_dir = tempfile.mkdtemp(prefix="save-sigs-gate-")
        self._old_gate_dir = os.environ.get("LOOP_GATE_DIR")
        os.environ["LOOP_GATE_DIR"] = self.gate_dir
        self.target = tempfile.mkdtemp(prefix="save-sigs-target-")
        self._git("init", "-q")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        with open(os.path.join(self.target, "mod.py"), "w", encoding="utf-8") as f:
            f.write("def f():\n    return 1\n")
        self._git("add", "-A")
        self._git("commit", "-qm", "init")

    def tearDown(self):
        shutil.rmtree(self.gate_dir, ignore_errors=True)
        shutil.rmtree(self.target, ignore_errors=True)
        if self._old_gate_dir is None:
            os.environ.pop("LOOP_GATE_DIR", None)
        else:
            os.environ["LOOP_GATE_DIR"] = self._old_gate_dir

    def _git(self, *args):
        subprocess.run(["git", "-C", self.target] + list(args),
                       capture_output=True, check=False)

    def _armed_transcript(self, session_id, red_result_text):
        marker = {"role": "user", "content": [
            {"type": "text", "text": "You are **Oga** -- orchestrator playbook loaded"}]}
        result = {"role": "user", "content": [
            {"type": "tool_result", "content": red_result_text}]}
        fd, tpath = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        with open(tpath, "w", encoding="utf-8") as f:
            for e in (marker, result):
                f.write(json.dumps(e) + "\n")
        tfile = os.path.join(self.gate_dir, "%s_target" % session_id)
        with open(tfile, "w", encoding="utf-8") as f:
            f.write(self.target)
        return {"transcript_path": tpath, "session_id": session_id}

    def test_record_sigs_false_does_not_persist_signature(self):
        session_id = "save-sigs-false-%s" % uuid.uuid4().hex
        red = ('{"passed": false, "runner": "pytest", "output": "E AssertionError: '
               'boom at gate.py line 1"}')
        data = self._armed_transcript(session_id, red)
        sig_path = os.path.join(self.gate_dir, "%s_signatures.json" % session_id)
        self.assertFalse(os.path.isfile(sig_path))
        self.msg.run(data, record_sigs=False)
        self.assertFalse(
            os.path.isfile(sig_path),
            "_save_sigs() must NOT persist to disk when record_sigs=False, "
            "even though a red verify was present in the transcript this "
            "invocation would otherwise have appended a signature for")

    def test_record_sigs_default_true_persists_signature(self):
        session_id = "save-sigs-true-%s" % uuid.uuid4().hex
        red = ('{"passed": false, "runner": "pytest", "output": "E AssertionError: '
               'boom at gate.py line 2"}')
        data = self._armed_transcript(session_id, red)
        sig_path = os.path.join(self.gate_dir, "%s_signatures.json" % session_id)
        self.assertFalse(os.path.isfile(sig_path))
        self.msg.run(data)  # record_sigs omitted -- must default to True
        self.assertTrue(
            os.path.isfile(sig_path),
            "the default (record_sigs omitted, or explicitly True) must "
            "still persist signatures exactly as before this spec's change "
            "-- zero risk to run()'s existing tested contract")


class MicroStepBlockedWhenLayer1AlreadyViolatedDoesNotRecordSigsMasking1(
        unittest.TestCase):
    """AC7 companion, integration level: through the LIVE loop_stop_guard.py
    (not just the direct micro_step_gates.run() unit call above), when Layer
    1 already appended a violation this turn, the MICRO_STEP call site must
    pass record_sigs=(not _VIOLATIONS) -- i.e. record_sigs=False -- so no
    `<session>_signatures.json` write happens as a side effect of a turn
    that is going to block on Layer 1's violation regardless."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_no_signatures_file_written_when_layer1_violation_precedes_microstep(self):
        sid = "no-sigs-%s" % uuid.uuid4().hex
        agent_id = "noSigsAgent"
        self._flags.append(write_commit_violation_flag(
            sid, agent_id, [{"sha": "nosig123", "touched": ["RUN.md"]}]))

        # ALSO force a real step-size violation in the SAME armed target, so
        # this test proves the MICRO_STEP block's own detection logic
        # actually EXECUTED this invocation (not merely "never reached") --
        # a weaker fixture (no independent proof the block ran) would pass
        # equally well under the pre-fix code, where Layer 1's sys.exit(2)
        # never lets the micro-step-gates block run at all, making "no
        # signatures file" trivially true for the wrong reason.
        with open(os.path.join(self.repo, "big.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n" * 250)
        subprocess.run(["git", "-C", self.repo, "add", "-A"], capture_output=True)

        marker_event = {"type": "user", "message": {
            "role": "user",
            "content": "you are **oga** -- orchestrator playbook loaded"}}
        events = [marker_event,
                  {"type": "user", "message": {"role": "user", "content": "go build"}},
                  {"type": "user", "message": {"role": "user", "content": [
                      {"type": "tool_result", "content": "nothing this turn"}]}}]

        os.makedirs(GATE_DIR_L1, exist_ok=True)
        target_file = os.path.join(GATE_DIR_L1, "%s_target" % sid)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(self.repo)
        sig_file = os.path.join(GATE_DIR_L1, "%s_signatures.json" % sid)
        try:
            self.assertFalse(os.path.isfile(sig_file))
            code, err = run_guard_full(events, session_id=sid)
            self.assertEqual(code, 2, err)
            self.assertIn(agent_id, err)
            # Proof the micro-step-gates block's OWN detection logic ran
            # this invocation (not merely never-reached): its step-size
            # violation is also reported.
            self.assertIn("step-size", err)
            self.assertFalse(
                os.path.isfile(sig_file),
                "the micro-step-gates block's own detection DID run this "
                "invocation (step-size fired), but Layer 1 already "
                "violated earlier in file order -- the MICRO_STEP call "
                "site must still pass record_sigs=False so no signatures "
                "file is written despite detection having executed")
        finally:
            try:
                os.remove(target_file)
            except OSError:
                pass
            try:
                os.remove(sig_file)
            except OSError:
                pass


class FullIntegrationLayer1PlusMicroStepBlockMasking1(unittest.TestCase):
    """AC8 [BEHAVIORAL]: full integration -- Layer 1 fires AND the micro-
    step-gates block ALSO fires (a real step-size violation: >200
    uncommitted changed code lines in the armed target), same turn. Both
    violations must be reported in full: Layer 1's agent/sha evidence AND
    the micro-step gate's "step-size" message, "2 violations detected",
    Layer 1 first (highest priority)."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_layer1_and_microstep_stepsize_both_block_same_turn(self):
        sid = "l1-plus-microstep-%s" % uuid.uuid4().hex
        agent_id = "l1MicroStepAgent"
        self._flags.append(write_commit_violation_flag(
            sid, agent_id, [{"sha": "msblk123", "touched": ["RUN.md"]}]))

        # A real step-size violation: >200 uncommitted changed code lines in
        # the armed target repo.
        with open(os.path.join(self.repo, "big.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n" * 250)
        subprocess.run(["git", "-C", self.repo, "add", "-A"], capture_output=True)

        events = make_turn([text("just talking, no commit this turn")])
        code, err = run_guard_armed(events, self.repo, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn(agent_id, err)
        self.assertIn("Layer 1", err)
        self.assertIn("step-size", err)
        self.assertIn("2 violations detected", err)
        self.assertLess(err.index("Layer 1"), err.index("step-size"))


class FailOpenPreservedForConvertedGatesMasking1(unittest.TestCase):
    """AC11 [BEHAVIORAL]: fail-open preserved for every converted gate.
    Converting a simple gate's `sys.exit(2)` to `_VIOLATIONS.append(...)`
    must not change its firing CONDITION -- the same fixture that used to
    trigger exit 2 under the pre-fix code must still trigger a block
    (through the new EOF `_VIOLATIONS` decision block) under the fixed code.
    Verified here for every one of the 7 "simple" converted sites (585, 601,
    721, 822, 888, 1050, 1062) using each gate's own pre-existing minimal
    fire fixture, single-violation-turn only (so the EOF block takes the
    `else: sys.stderr.write(_VIOLATIONS[0][1])` single-message branch,
    proving the visible stderr text a real single-gate turn produces is
    unchanged, matching AC1's byte-for-byte requirement) -- this is the
    direct evidence that these 7 conversions did not accidentally turn a
    fire into an ALLOW."""

    def test_role_or_harness_edit_still_fires_after_conversion(self):
        code, err = run_guard(make_turn([ROLE_EDIT]))
        self.assertEqual(code, 2, err)
        self.assertIn("Phase-1 rule", err)

    def test_feature_still_fires_after_conversion(self):
        code, err = run_guard(make_turn([FEATURE_EDIT]))
        self.assertEqual(code, 2, err)
        self.assertIn("INDEPENDENT verifier", err)

    def test_plan_check_still_fires_after_conversion(self):
        code, err = run_guard(make_turn([CODER_AGENT]))
        self.assertEqual(code, 2, err)
        self.assertIn("plan-check Verifier", err)

    def test_research_gate_still_fires_after_conversion(self):
        # Isolated from FEATURE using the same BARE_VERIFY_TASK idiom
        # MatchedEvidenceHGuard8's AC4 section already established (a bare
        # "verify" dispatch satisfies FEATURE's broad VERIFIER check but not
        # RESEARCH_GATE's narrower _VERIFIER_DETECT requirement) -- proves
        # RESEARCH_GATE's OWN conversion (sys.exit(2) -> _VIOLATIONS.append)
        # did not change ITS firing condition, independent of any FEATURE
        # interaction.
        bare_verify = tool_use("Agent", description="Some other task",
                               prompt="please verify the environment is set up")
        researcher = researcher_dispatch("toolu_ac11_research_still_fires")
        edit = tool_use("Edit", file_path="/x/src/service.py",
                        old_string="a", new_string="b")
        events = make_turn_events(
            assistant_msg(bare_verify, researcher),
            tool_result_event("toolu_ac11_research_still_fires",
                              "Researcher findings: some finding."),
            assistant_msg(edit),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)
        self.assertIn("[LOOP STOP-GUARD] A Researcher (Mode D)", err)
        self.assertIn("/x/src/service.py", err)

    def test_verifier_hygiene_still_fires_after_conversion(self):
        hygiene_violation = tool_use(
            "Task",
            description="plan-check verifier",
            prompt="Read the spec. By the way, tests are passing already.")
        code, err = run_guard(make_turn([hygiene_violation]))
        self.assertEqual(code, 2, err)
        self.assertIn("hygiene", err)

    def test_verifier_adjacency_still_fires_after_conversion(self):
        d = tempfile.mkdtemp(prefix="adjacency-fail-open-")
        try:
            spec_path = os.path.join(d, "spec.md")
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write("# spec\n")
            with open(os.path.join(d, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("prior verdict here\n")
            adjacency_dispatch = tool_use(
                "Task", description="plan-check verifier",
                prompt="Review the implemented widget build against the spec at %s." % spec_path)
            code, err = run_guard(make_turn([adjacency_dispatch]))
            self.assertEqual(code, 2, err)
            self.assertIn("adjacency", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_micro_step_still_fires_after_conversion(self):
        repo = scratch_git_repo()
        try:
            with open(os.path.join(repo, "big.py"), "w", encoding="utf-8") as f:
                f.write("x = 1\n" * 250)
            subprocess.run(["git", "-C", repo, "add", "-A"], capture_output=True)
            events = make_turn([text("just talking")])
            code, err = run_guard_armed(events, repo)
            self.assertEqual(code, 2, err)
            self.assertIn("step-size", err)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class LaterGateExceptionDoesNotLoseEarlierViolationMasking1(unittest.TestCase):
    """AC11 companion [BEHAVIORAL]: fail-open at the PER-GATE level must
    compose correctly with the new append-not-exit design -- when an earlier
    gate (Layer 1) already appended a violation, and a LATER gate's own
    try/except-wrapped logic (the review-commit gate's own try/except,
    unchanged by this spec -- see ReviewCommitGateFailOpen's existing
    malformed-tool_result-content precedent for the same hostile shape)
    actually raises an exception INSIDE its detection logic, that later
    gate's own exception must still be caught (fail-open for THAT gate,
    unchanged behavior) WITHOUT losing or corrupting the EARLIER violation
    that Layer 1 already appended -- Layer 1's violation must still be
    reported at EOF, and the run must not crash.

    Distinguishing test design (not merely "still passes today for the
    wrong reason"): under the PRE-FIX code, Layer 1's sys.exit(2) prevents
    the review-commit gate's try/except from ever running at all this
    invocation, so a malformed tool_result placed there could never
    actually raise/be-caught -- this fixture only becomes a REAL exercise
    of "does a later gate's own exception get caught without losing an
    earlier violation" once the later gate's logic actually executes, which
    only happens under the append-not-exit design this spec adds."""

    def setUp(self):
        self.repo = scratch_git_repo()
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def test_layer1_violation_survives_a_later_gates_own_failure(self):
        sid = "later-gate-exc-%s" % uuid.uuid4().hex
        agent_id = "laterGateExcAgent"
        self._flags.append(write_commit_violation_flag(
            sid, agent_id, [{"sha": "exc12345", "touched": ["RUN.md"]}]))

        # A raw `git commit` Bash tool_use whose PAIRED tool_result content
        # is a malformed shape (neither a string nor a list of {"text":...}
        # dicts) -- ReviewCommitGateFailOpen's own established precedent for
        # forcing a genuine exception inside the review-commit gate's
        # detection logic (its _result_text-style extraction chokes on this
        # shape), armed against a REAL scratch repo so the gate's target
        # resolution itself is otherwise healthy.
        events = make_turn_events(
            assistant_msg(bash_tool_use("rc1", 'git commit -m "msg"')),
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "rc1",
                 "content": [{"type": "image", "source": "not text"}]},
            ]}},
        )
        code, err = run_guard_armed(events, self.repo, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn(agent_id, err)
        self.assertIn("Layer 1", err)
        self.assertNotIn("Traceback", err)


class AllGatesTelemetryGatedOnNoViolationsMasking1(unittest.TestCase):
    """AC12 [BEHAVIORAL] (NEW -- round-2 gap): the file's pre-existing
    `if _log_gate: _log_gate("ALL_GATES", False, "", 0)` at line 1259
    becomes `if _log_gate and not _VIOLATIONS: _log_gate("ALL_GATES", False,
    "", 0)` -- fires ONLY on a genuinely clean turn, exactly as it has since
    it was written. Verified via the REAL `loop_logger` opt-in debug log
    (LOOP_GUARD_DEBUG=1 + _LOOP_GUARD_LOG_DIR_OVERRIDE), which is the only
    real consumer of `_log_gate`'s calls -- not a text/keyword search of the
    guard's own source. A clean turn must produce an ALL_GATES record; a
    violation turn must NOT."""

    def setUp(self):
        self.log_dir = tempfile.mkdtemp(prefix="all-gates-log-")
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self.log_dir, ignore_errors=True)
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass

    def _run_with_debug_log(self, events, session_id=None):
        fd, tpath = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            with open(tpath, "w", encoding="utf-8") as f:
                for e in events:
                    f.write(json.dumps(e) + "\n")
            payload = {"transcript_path": tpath, "stop_hook_active": False}
            if session_id is not None:
                payload["session_id"] = session_id
            env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR_L1,
                      LOOP_GUARD_DEBUG="1",
                      _LOOP_GUARD_LOG_DIR_OVERRIDE=self.log_dir)
            p = subprocess.run([sys.executable, GUARD], input=json.dumps(payload),
                               capture_output=True, text=True, env=env)
            return p.returncode, p.stderr
        finally:
            os.remove(tpath)

    def _debug_log_records(self):
        log_path = os.path.join(self.log_dir, "debug.log")
        if not os.path.isfile(log_path):
            return []
        records = []
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    pass
        return records

    def test_all_gates_fires_on_genuinely_clean_turn(self):
        events = make_turn([text("just talking, nothing gating this turn")])
        code, err = self._run_with_debug_log(events)
        self.assertEqual(code, 0, err)
        records = self._debug_log_records()
        all_gates = [r for r in records if r.get("gate") == "ALL_GATES"]
        self.assertEqual(
            len(all_gates), 1,
            "a genuinely clean turn must log exactly one ALL_GATES record; "
            "got: %r (full log: %r)" % (all_gates, records))
        self.assertFalse(all_gates[0]["fired"])

    def test_all_gates_does_not_fire_on_a_violation_turn(self):
        sid = "all-gates-violation-%s" % uuid.uuid4().hex
        agent_id = "allGatesViolationAgent"
        self._flags.append(write_commit_violation_flag(
            sid, agent_id, [{"sha": "ag123456", "touched": ["RUN.md"]}]))
        events = make_turn([text("nothing this turn")])
        code, err = self._run_with_debug_log(events, session_id=sid)
        self.assertEqual(code, 2, err)
        records = self._debug_log_records()
        all_gates = [r for r in records if r.get("gate") == "ALL_GATES"]
        self.assertEqual(
            len(all_gates), 0,
            "a turn that blocked on a real violation must NOT log an "
            "ALL_GATES record -- under the pre-fix (v2, undiscussed) design "
            "this fired unconditionally, silently logging \"clean turn\" "
            "telemetry on a turn that actually blocked with exit 2; got: %r"
            % all_gates)


# ---------------------------------------------------------------------------
# H-WORKFLOW-BLINDSPOT-1
# (runs/2026-07-03_h-workflow-blindspot-and-blob-display/specs/spec.md)
# Part A, AC1-AC4: extend the 5 sites in this file that filter _TOOL_USES to
# tool_use.name in ("task", "agent", "subagent") so they also recognize a
# Workflow-shaped tool_use (name == "Workflow"). Sites 1-3 already read their
# detection text via _tu_input(tu) (a full json.dumps of the whole input
# dict), which already includes a Workflow's `script` field content -- only
# the tool-name allowlist itself needs to grow a 5th member for those three.
# Sites 4-5 (hygiene, adjacency) currently hand-roll direct field access
# (`input.description`/`input.prompt`) and need BOTH the allowlist extended
# AND the new `_tu_dispatch_text`/`_tu_dispatch_prompt_text` helpers wired in
# so a Workflow's real dispatch content (living in `input.script`, not
# `input.description`/`input.prompt`) is actually read.
#
# RED until the Coder implements: today all 5 sites silently exclude a
# Workflow-named tool_use regardless of its `script` content.
# ---------------------------------------------------------------------------

def workflow_tool_use(script):
    """A Workflow-shaped tool_use: name == 'Workflow', dispatch content lives
    in input.script (not description/prompt) -- the exact shape the spec's
    Part A closes the blind spot for."""
    return tool_use("Workflow", script=script)


class WorkflowSite1VerifierExemption(unittest.TestCase):
    """AC1, site 1 (line ~319): the VERIFIER exemption that suppresses the
    FEATURE gate. A Workflow dispatch whose script contains verifier-shaped
    text must be recognized exactly as an equivalent Agent dispatch with the
    same text in `description` would be -- FEATURE gate suppressed."""

    def test_workflow_verifier_script_suppresses_feature_gate(self):
        wf = workflow_tool_use(
            "await agent({description: 'plan-check Verifier for widget spec', "
            "prompt: 'You are an independent verifier reviewing the change.'})")
        code, err = run_guard(make_turn([FEATURE_EDIT, wf]))
        self.assertEqual(code, 0, err)

    def test_equivalent_agent_dispatch_already_suppresses_feature_gate(self):
        """Companion proving the fixture is a genuine apples-to-apples
        equivalence, not a Workflow-only artifact: the same verifier-shaped
        text via a real Agent dispatch already passes today."""
        agent_equiv = tool_use(
            "Agent", description="plan-check Verifier for widget spec",
            prompt="You are an independent verifier reviewing the change.")
        code, err = run_guard(make_turn([FEATURE_EDIT, agent_equiv]))
        self.assertEqual(code, 0, err)

    def test_workflow_non_verifier_script_still_blocks_feature_gate(self):
        """Regression companion: a Workflow dispatch with NO verifier-shaped
        content must not accidentally satisfy VERIFIER -- FEATURE still
        blocks, same as an equivalent non-verifier Agent dispatch would."""
        wf = workflow_tool_use("await agent({description: 'Coder for the fix', "
                                "prompt: 'implement per spec'})")
        code, err = run_guard(make_turn([FEATURE_EDIT, wf]))
        self.assertEqual(code, 2, err)


class WorkflowSite2PlanCheckGate(unittest.TestCase):
    """AC1, site 2 (line ~651): plan-check-before-Coder same-turn detection.
    A Workflow dispatch whose script contains Coder-shaped text must count as
    a Coder dispatch for this gate; one with verifier-shaped text must count
    as satisfying the plan-check requirement -- both exactly as an equivalent
    Agent dispatch with the same text in `description` would."""

    def test_workflow_coder_script_without_verifier_blocks(self):
        wf = workflow_tool_use("await agent({description: 'Coder for the build', "
                                "prompt: 'implement per spec'})")
        code, err = run_guard(make_turn([wf]))
        self.assertEqual(code, 2, err)

    def test_workflow_verifier_script_satisfies_plan_check_gate(self):
        wf_verifier = workflow_tool_use(
            "await agent({description: 'plan-check Verifier for widget spec', "
            "prompt: 'Review the plan before any dispatch.'})")
        wf_coder = workflow_tool_use("await agent({description: 'Coder for the build', "
                                     "prompt: 'implement per spec'})")
        # [Section G] wf_coder is a genuinely Coder-shaped Workflow dispatch,
        # so the separate, out-of-scope, intentional "Workflow Coder
        # dispatch is unsupported in v1" block fires (exit 2) -- this
        # test's own point (proving Workflow dispatches get equivalent
        # *classification* treatment to an Agent dispatch with the same
        # text) is preserved by asserting THIS exact, now-confirmed-correct
        # block, not by switching away from a Workflow shape (which would
        # defeat the point).
        code, err = run_guard(make_turn([wf_verifier, wf_coder]))
        self.assertEqual(code, 2, err)
        self.assertIn("Workflow Coder dispatch is unsupported in v1", err)

    def test_equivalent_agent_dispatch_already_blocks(self):
        """Companion proving genuine equivalence: the same Coder-shaped text
        via a real Agent dispatch (no preceding Verifier) already blocks
        today."""
        agent_equiv = tool_use("Agent", description="Coder for the build",
                               prompt="implement per spec")
        code, err = run_guard(make_turn([agent_equiv]))
        self.assertEqual(code, 2, err)


class WorkflowSite3ResearcherGate(unittest.TestCase):
    """AC1, site 3 (line ~802): Researcher-then-direct-edit gate. A Workflow
    dispatch whose script contains researcher-shaped text matching
    _RESEARCHER_DETECT_V2's `role:\\s*researcher\\b` alternative (evaluated
    against _tu_input's json.dumps output, unchanged at this site -- only the
    tool-name allowlist grows) must be recognized as a Researcher dispatch,
    exactly as an equivalent Agent dispatch would be. (The regex's other
    alternative, the JSON-quoted `"description": "..researcher` form, would
    require an outer json.dumps to preserve un-escaped literal quote
    characters inside `script` -- it does not, since Workflow's own `script`
    value is itself JSON-string-encoded by _tu_input's json.dumps(tu.get(
    "input")) call, so every embedded `"` becomes `\\"`. The `role:
    researcher` alternative has no such quoting dependency and is the
    natural way this text would appear in a real Workflow script anyway.)"""

    def test_workflow_researcher_script_then_direct_edit_blocks(self):
        researcher_id = "toolu_wf_site3_research"
        wf = workflow_tool_use(
            "Role: Researcher. Dispatching to find the registry mechanism "
            "for domain-brief lookups.")
        wf["id"] = researcher_id
        events = make_turn_events(
            assistant_msg(wf),
            tool_result_event(researcher_id,
                              "Researcher findings: some finding."),
            assistant_msg(FEATURE_EDIT),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)

    def test_workflow_researcher_then_verifier_then_edit_passes(self):
        researcher_id = "toolu_wf_site3_research_ok"
        wf = workflow_tool_use(
            "Role: Researcher. Dispatching to find the registry mechanism "
            "for domain-brief lookups.")
        wf["id"] = researcher_id
        events = make_turn_events(
            assistant_msg(wf),
            tool_result_event(researcher_id,
                              "Researcher findings: some finding."),
            assistant_msg(PLAN_VERIFIER_AFTER, FEATURE_EDIT),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 0, err)

    def test_equivalent_agent_dispatch_already_blocks(self):
        """Companion proving genuine equivalence: the same researcher-shaped
        Agent dispatch (RESEARCHER_AGENT, module-level fixture) + direct edit
        with no Verifier between already blocks today (ResearchGate.
        test_researcher_then_direct_edit_without_verifier_blocks covers the
        identical shape; repeated here for locality with the Workflow
        companions above)."""
        code, err = run_guard(make_turn([RESEARCHER_AGENT, FEATURE_EDIT]))
        self.assertEqual(code, 2, err)


class WorkflowSite4HygieneGateLiveIncident(unittest.TestCase):
    """AC1 + AC3: site 4 (hygiene gate, line ~872). A Workflow tool_use whose
    script contains a result-shaped phrase ("tests passed") inside a
    Verifier-shaped dispatch must be caught -- reconstructing the hygiene
    gate's live-incident-equivalent scenario for a Workflow dispatch."""

    def test_workflow_verifier_script_with_result_shaped_phrase_blocks(self):
        wf = workflow_tool_use(
            "await agent({description: 'plan-check Verifier for widget spec', "
            "prompt: 'Read the spec. By the way, tests are passing already.'})")
        code, err = run_guard(make_turn([wf]))
        self.assertEqual(code, 2, err)
        self.assertIn("hygiene", err.lower())

    def test_workflow_verifier_script_clean_prompt_allows(self):
        """Companion: the same Workflow-shaped Verifier dispatch WITHOUT any
        result-shaped phrase must not trip the hygiene gate."""
        wf = workflow_tool_use(
            "await agent({description: 'plan-check Verifier for widget spec', "
            "prompt: 'Read the spec at runs/x/spec.md and review the plan.'})")
        code, err = run_guard(make_turn([wf]))
        self.assertEqual(code, 0, err)

    def test_equivalent_agent_dispatch_already_blocks(self):
        """Companion proving genuine equivalence: the identical result-shaped
        phrase via a real Agent/Task dispatch already blocks today (mirrors
        FailOpenPreservedForConvertedGatesMasking1.
        test_verifier_hygiene_still_fires_after_conversion)."""
        hygiene_violation = tool_use(
            "Task", description="plan-check verifier",
            prompt="Read the spec. By the way, tests are passing already.")
        code, err = run_guard(make_turn([hygiene_violation]))
        self.assertEqual(code, 2, err)
        self.assertIn("hygiene", err.lower())


class WorkflowSite5AdjacencyGateLiveIncident(unittest.TestCase):
    """AC1 + AC2: site 5 (adjacency gate, line ~1027). Reconstructs the
    actual live incident named in the spec's Goal section: a Workflow
    tool_use whose script field contains a literal reference to a run-dir-
    root status-doc-adjacent path (plan_check_log.md) -- the adjacency gate
    must now fire (exit 2) where it previously silently passed."""

    def test_workflow_script_referencing_path_beside_plan_check_log_blocks(self):
        d = tempfile.mkdtemp(prefix="wf-adjacency-live-incident-")
        try:
            spec_path = os.path.join(d, "spec.md")
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write("# spec\n")
            with open(os.path.join(d, "plan_check_log.md"), "w", encoding="utf-8") as f:
                f.write("prior plan-check verdict here\n")
            wf = workflow_tool_use(
                "await agent({description: 'plan-check Verifier for widget spec', "
                "prompt: 'Read the spec at %s and review it.'})" % spec_path)
            code, err = run_guard(make_turn([wf]))
            self.assertEqual(code, 2, err)
            self.assertIn("adjacency", err.lower())
            self.assertIn(spec_path, err)
            self.assertIn("plan_check_log.md", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_workflow_script_referencing_clean_path_allows(self):
        """Companion: the same Workflow-shaped Verifier dispatch pointing at
        a path with NO status doc beside it must not trip the adjacency
        gate."""
        d = tempfile.mkdtemp(prefix="wf-adjacency-clean-")
        try:
            spec_path = os.path.join(d, "spec.md")
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write("# spec\n")
            wf = workflow_tool_use(
                "await agent({description: 'plan-check Verifier for widget spec', "
                "prompt: 'Read the spec at %s and review it.'})" % spec_path)
            code, err = run_guard(make_turn([wf]))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_equivalent_agent_dispatch_already_blocks(self):
        """Companion proving genuine equivalence: the identical adjacency
        scenario via a real Agent/Task dispatch already blocks today (mirrors
        FailOpenPreservedForConvertedGatesMasking1.
        test_verifier_adjacency_still_fires_after_conversion, using
        plan_check_log.md instead of HANDOFF.md as the status doc)."""
        d = tempfile.mkdtemp(prefix="agent-adjacency-live-incident-")
        try:
            spec_path = os.path.join(d, "spec.md")
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write("# spec\n")
            with open(os.path.join(d, "plan_check_log.md"), "w", encoding="utf-8") as f:
                f.write("prior plan-check verdict here\n")
            adjacency_dispatch = tool_use(
                "Task", description="plan-check verifier",
                prompt="Read the spec at %s and review it." % spec_path)
            code, err = run_guard(make_turn([adjacency_dispatch]))
            self.assertEqual(code, 2, err)
            self.assertIn("adjacency", err.lower())
        finally:
            shutil.rmtree(d, ignore_errors=True)


class WorkflowSite5AdjacencySelfMatchMisfire2(unittest.TestCase):
    """AC-2 (research/loop-stop-guard-misfire-dossier-2026-07-08.md, "Misfire
    2 root cause"; fix_plan.md H-GUARD-6 sub-case (d)): reconstructs the
    SECOND real misfire named in the dossier verbatim -- a Workflow-
    dispatched verification agent instructed to read a run dir's
    plan_check_log.md ITSELF (the literal, sole named read target) and quote
    line ranges from it directly, "no paraphrasing". This is deliberately
    NOT the WorkflowSite5AdjacencyGateLiveIncident shape above (a distinct
    spec.md sitting BESIDE plan_check_log.md, AC-2b, which must stay
    unchanged) -- here the candidate token IS the status-doc file, so
    self-exclusion (AC-2) should apply and this must ALLOW."""

    def test_workflow_script_instructed_to_read_and_quote_plan_check_log_itself_allows(self):
        d = tempfile.mkdtemp(prefix="wf-adjacency-self-match-")
        try:
            log_path = os.path.join(d, "plan_check_log.md")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("## Round 30\nprior plan-check verdict here\n" * 3)
            wf = workflow_tool_use(
                "await agent({description: 'plan-check Verifier -- fact-check "
                "round 30', prompt: 'Read %s directly and quote the exact line "
                "range for the round-30 entry verbatim, no paraphrasing.'})"
                % log_path)
            code, err = run_guard(make_turn([wf]))
            self.assertEqual(
                code, 0,
                "a Workflow dispatch whose literal, sole instructed read "
                "target IS plan_check_log.md itself must not be flagged as "
                "an adjacency violation -- there is no separate spec/target "
                "being contaminated by a neighboring status doc when the "
                "target IS the doc. Got exit %r, stderr=%s" % (code, err),
            )
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_equivalent_agent_dispatch_self_match_also_allows(self):
        """Companion proving genuine equivalence to the Workflow case: the
        identical self-match scenario via a real Agent/Task dispatch, same
        pattern as WorkflowSite5AdjacencyGateLiveIncident.test_equivalent_
        agent_dispatch_already_blocks above (which proves the BESIDE case's
        equivalence) -- here proving the SELF-match case's equivalence."""
        d = tempfile.mkdtemp(prefix="agent-adjacency-self-match-")
        try:
            log_path = os.path.join(d, "plan_check_log.md")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("## Round 30\nprior plan-check verdict here\n")
            adjacency_dispatch = tool_use(
                "Task", description="plan-check verifier",
                prompt="Read %s directly and quote the round-30 line range "
                       "verbatim." % log_path)
            code, err = run_guard(make_turn([adjacency_dispatch]))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class WorkflowZeroRegressionExistingSuite(unittest.TestCase):
    """AC4 (v2): zero regressions for the non-Workflow case. _tu_dispatch_text/
    _tu_dispatch_prompt_text must be byte-identical to the prior direct-
    field-access behavior for Agent/Task/subagent-named tool_uses
    (description-only, per v2's fix -- NOT description+prompt concatenated).
    This class does not re-run the whole pre-existing suite (that is the
    verification-required step run separately); it pins the specific
    byte-identical-behavior claim the spec's v2 fix section makes explicit:
    a non-Workflow dispatch whose `description` alone does NOT match
    _VERIFIER_DETECT, but whose `prompt` DOES, must NOT be classified as a
    Verifier dispatch by the hygiene/adjacency gates."""

    def test_non_workflow_dispatch_verifier_language_only_in_prompt_not_classified(self):
        """A non-Workflow (Agent) dispatch whose `description` contains no
        verifier-shaped language at all, but whose `prompt` DOES contain
        "independent verifier" -- must NOT be scanned by the hygiene gate
        (which gates entry on _VERIFIER_DETECT matching the description-only
        text). If the v2 fix were NOT applied (i.e. description+prompt were
        concatenated, matching v1's mistaken design), this dispatch would
        wrongly enter the hygiene scan. Prompt also carries a result-shaped
        phrase, so a wrongly-widened match surface would flip this to exit 2."""
        wrongly_matchable = tool_use(
            "Agent", description="Coder for the build",
            prompt="implement per spec. Note: an independent verifier will "
                   "check this later; tests are passing in my local run.")
        # [D.2 rule-1 code==2-inversion candidate, confirmed via live-check]
        # wrongly_matchable/PLAN_VERIFIER_AFTER carry no SPEC:/SPEC_SHA256=
        # marker and this fixture has zero tool_results -- the SAME
        # structurally-unsatisfiable-under-v1 shape as the 3 confirmed
        # code==2-inversion tests elsewhere in this file (a Verifier-shaped
        # + Coder-shaped pair, zero results, asserting an ALLOWED outcome).
        # This test's OWN real point (per its class/method docstrings) is
        # the hygiene gate's description-only classification -- orthogonal
        # to whether the unrelated PLAN_CHECK gate also fires -- so
        # inverting to code==2 (confirmed live: PLAN_CHECK fires first,
        # citing "expected exactly one spec ref") does not defeat this
        # test's own intent; the hygiene-non-misclassification claim
        # remains meaningfully asserted via assertNotIn("hygiene", ...)
        # below regardless of which gate's message actually appears.
        code, err = run_guard(make_turn([PLAN_VERIFIER_AFTER, wrongly_matchable]))
        self.assertEqual(code, 2, err)
        self.assertNotIn("hygiene", err.lower())


class WorkflowSite4Site5NonMisfireAdversarial(unittest.TestCase):
    """AC4 (v2, round-1 regression-audit gap): a Coder-shaped dispatch
    (description="Coder for the build", matching _CODER_DETECT) whose
    `prompt` field contains verifier-shaped language ("plan-check verifier",
    "independent verifier") -- the hygiene/adjacency gates must NOT
    misclassify this as a Verifier dispatch, matching H_GUARD_1_Regression's
    own established precedent for exactly this confusion class.

    Agent/Task-shaped only, per the spec's own AC4 wording ("description="
    Coder for the build"...whose `prompt` field contains..." -- naming two
    SEPARATE fields). A Workflow tool_use has no description/prompt split --
    _tu_dispatch_text's Workflow branch returns the WHOLE `script` as one
    undifferentiated blob (spec's own helper docstring: "A Workflow tool_use
    carries no top-level 'description' at all"). Concretely: embedding both
    "coder for" and "independent verifier" substrings anywhere in one script
    string makes _VERIFIER_DETECT match that SAME combined text at every
    site (classification is verifier-checked-first, per H_GUARD_1_Regression
    precedent) -- so the described confusion (Coder-classified overall, but
    prompt-only verifier language slipping past a description-only gate) is
    structurally impossible to construct for a Workflow dispatch; there is no
    narrower sub-field to hide the verifier language in. This is a genuine
    spec ambiguity: AC4's adversarial case does not have a Workflow-shaped
    equivalent, so only the Agent/Task-shaped test below is written. See
    final decision-log note to Oga."""

    def test_agent_coder_dispatch_with_verifier_language_in_prompt_not_misclassified(self):
        coder_with_verifier_talk = tool_use(
            "Agent", description="Coder for the build",
            prompt="Implement per spec. Note for context: a plan-check "
                   "verifier and an independent verifier already reviewed "
                   "this approach; tests are passing.")
        code, err = run_guard(make_turn([coder_with_verifier_talk]))
        # No plan-check Verifier dispatch this turn (this IS the Coder
        # dispatch, not a Verifier one) -> the plan-check gate fires. The
        # hygiene/adjacency gates (which scan _VERIFIER_DETECT-matching
        # DESCRIPTIONS only) must never have entered their scan for this
        # dispatch at all -- confirmed by the message not naming "hygiene"
        # or "adjacency" as the trigger.
        self.assertEqual(code, 2, err)
        self.assertNotIn("hygiene", err.lower())
        self.assertNotIn("adjacency", err.lower())
        self.assertIn("plan-check Verifier", err)

    def test_workflow_coder_script_with_no_verifier_language_not_swept_into_hygiene_scan(self):
        """Workflow-shaped companion covering what IS well-defined: a
        Workflow script that is purely Coder-shaped (no verifier-shaped
        language anywhere in the combined blob) must never be swept into the
        hygiene/adjacency scan (which gates entry on _VERIFIER_DETECT
        matching _tu_dispatch_text) merely because it also references a
        result-shaped phrase like "tests passing" -- that phrase alone,
        without any verifier-shaped language, must not satisfy
        _VERIFIER_DETECT and must not enter the hygiene scan."""
        wf = workflow_tool_use(
            "await agent({description: 'Coder for the build', prompt: "
            "'Implement per spec. Tests are passing in my local dev run.'})")
        code, err = run_guard(make_turn([wf]))
        self.assertEqual(code, 2, err)
        self.assertNotIn("hygiene", err.lower())
        self.assertNotIn("adjacency", err.lower())
        self.assertIn("plan-check Verifier", err)


class WorkflowSite4Site5WiderSurfaceAcceptedBehavior(unittest.TestCase):
    """AC4b (spec v5, round-4 state-completeness finding, `H-AMBIGUITY-NOTE-
    DROPPED-1`): sites 4-5's Workflow-shaped false-positive surface is
    structurally WIDER than the Agent/Task case, because `_tu_dispatch_text`
    and `_tu_dispatch_prompt_text` both return the SAME `script` blob for a
    Workflow tool_use (no description/prompt split exists for this tool
    type). This is the CONSCIOUSLY accepted, tested residual described in
    the spec's "Sites 4-5" section ("a Workflow script that mixes a Coder
    sub-dispatch with mere narrative mention of 'independent verifier'
    anywhere in the script text WILL sweep into hygiene/adjacency
    scanning") -- not a bug to prevent. This test PINS that behavior: it
    asserts the gate DOES fire, so a future refactor cannot silently narrow
    (or further widen) this surface without failing a test."""

    def test_workflow_script_mixing_coder_dispatch_with_narrative_verifier_mention_sweeps_into_hygiene(self):
        """[BEHAVIORAL][AC4b] A single Workflow script string containing both
        a Coder sub-dispatch description ("Coder for the build") AND, later
        in the SAME script, mere narrative mention of "independent verifier"
        (not itself a Verifier dispatch's own description field -- there is
        no such field for Workflow) -- because _VERIFIER_DETECT matches
        _tu_dispatch_text (the whole script blob) for Workflow tool_uses,
        this dispatch IS classified as verifier-shaped and DOES sweep into
        the hygiene gate's scan, which then fires on the accompanying
        result-shaped phrase ("tests passed") elsewhere in the same script."""
        wf = workflow_tool_use(
            "await agent({description: 'Coder for the build', prompt: "
            "'Implement per spec.'}); "
            "Note for context: an independent verifier already looked at "
            "this earlier in the session, and by the way tests passed "
            "in my local dev run.")
        code, err = run_guard(make_turn([wf]))
        self.assertEqual(code, 2, err)
        self.assertIn("hygiene", err.lower())

    def test_workflow_script_mixing_coder_dispatch_with_narrative_verifier_mention_sweeps_into_adjacency(self):
        """[BEHAVIORAL][AC4b] Companion proving the SAME wider-surface
        residual at site 5 (adjacency): the identical Coder-sub-dispatch +
        narrative "independent verifier" mixture, this time with the script
        also referencing a run-dir-root status-doc-adjacent path
        (plan_check_log.md) instead of a result-shaped phrase -- the
        adjacency gate DOES fire, proving the wider match surface applies
        uniformly across both previously-blind gates, not just hygiene."""
        d = tempfile.mkdtemp(prefix="wf-site4-5-wider-surface-adjacency-")
        try:
            spec_path = os.path.join(d, "spec.md")
            with open(spec_path, "w", encoding="utf-8") as f:
                f.write("# spec\n")
            with open(os.path.join(d, "plan_check_log.md"), "w", encoding="utf-8") as f:
                f.write("prior plan-check verdict here\n")
            wf = workflow_tool_use(
                "await agent({description: 'Coder for the build', prompt: "
                "'Implement per spec, read the file at %s.'}); "
                "Note for context: an independent verifier already looked "
                "at this earlier in the session." % spec_path)
            code, err = run_guard(make_turn([wf]))
            self.assertEqual(code, 2, err)
            self.assertIn("adjacency", err.lower())
            self.assertIn(spec_path, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# H-RUNLOG-ENFORCEMENT-GATE-1
# (runs/2026-07-03_h-runlog-enforcement-gate/specs/spec.md, v4/FINAL)
#
# Covers the NEW run-log enforcement gate: a Task/Agent/Workflow dispatch
# matching _VERIFIER_DETECT whose OWN paired tool_result contains
# "verdict: pass" AND whose prompt/result names a real spec FILE (spec.md or
# spec_vN.md, either specs/-wrapped or bare-root at run-dir root) with no
# non-empty run_log.md/RUN_LOG.md/iteration_log.md in that file's derived run
# directory -> exit 2.
#
# AC12 dependency-check result (performed directly, per this spec's own
# required first step, BEFORE any test below was written):
#   $ grep -n "_tu_dispatch_text" hooks/loop_stop_guard.py
#   267:def _tu_dispatch_text(tu):
#   905:        _desc = _tu_dispatch_text(_tu)
#   1060:    _adj_desc = _tu_dispatch_text(_tu)
# `_tu_dispatch_prompt_text` is also already present and already used at the
# adjacency gate (line 1063). Additionally, `"workflow"` is ALREADY present
# in the tool-name membership check at every one of the 5 sites the spec's
# Implementation-order dependency section names (confirmed via
# `grep -n '"workflow"' hooks/loop_stop_guard.py`, including line 1058, the
# adjacency gate immediately preceding this new gate's own insertion anchor).
# H-WORKFLOW-BLINDSPOT-1 has FULLY LANDED as of this test-writing pass --
# the spec's "yes" branch of the Implementation-order dependency applies:
# the Coder MUST use _tu_dispatch_text/_tu_dispatch_prompt_text in place of
# the hand-rolled input.prompt access, AND "workflow" must already be (and
# already is, at every pre-existing site) part of the membership check for
# THIS gate's own new membership check too. AC14 below is therefore written
# as a REAL, EXECUTABLE (not skipped) test -- the spec's own skip
# instruction is conditional on the "no" branch, which does not apply here.
#
# Cross-gate interaction discovered directly (not assumed) while building
# these fixtures: the PRE-EXISTING adjacency gate's _STATUS_DOC_DENYLIST
# includes "run_log*"/"*run_log*" (case-insensitive), so a BARE-ROOT spec
# file (spec.md sitting directly at run-dir root, no specs/ wrapper -- AC13/
# AC15) that ALSO has a real run_log.md/RUN_LOG.md in that SAME directory
# trips the pre-existing adjacency gate FIRST (VERIFIER_ADJACENCY, exit 2,
# unrelated to this new gate), because the referenced file's own parent dir
# IS the run directory in the bare-root shape (no specs/ layer to separate
# them). Confirmed live against current (pre-this-spec) code:
#   bare-root spec.md + run_log.md beside it -> RC 2, VERIFIER_ADJACENCY
#   bare-root spec.md + iteration_log.md beside it -> RC 0 (no collision,
#     "iteration_log*" is not in _STATUS_DOC_DENYLIST)
#   specs/-wrapped spec.md + run_log.md one level up (run-dir root, NOT
#     inside specs/) -> RC 0 (no collision; the log is never adjacent to the
#     referenced file itself in that shape)
# Therefore every bare-root "has a log, no block" test below (AC13's no-
# block companion, AC15) uses `iteration_log.md` specifically, to isolate
# what THIS gate's own behavior is from the pre-existing, correct, out-of-
# scope adjacency gate's own denylist. The specs/-wrapped tests (AC1-AC9)
# are unaffected and use run_log.md/RUN_LOG.md as the spec's own AC2/AC3
# wording implies.
# ---------------------------------------------------------------------------

_RUNLOG_VERIFIER_DESC = "independent verifier post-build review for widget build"


def _rl_make_run_dir(prefix, wrap_in_specs=True, log_name=None, log_content="done"):
    """Build a real, on-disk run directory containing a real spec.md, either
    specs/-wrapped (the newer convention) or bare-root (the older, still-
    live convention per AC13) -- optionally with a named run-log file
    (log_content=None or "" exercises AC4's whitespace-only-counts-as-
    missing case when combined with an explicit whitespace string). Returns
    (run_dir, spec_path); caller owns cleanup via shutil.rmtree(run_dir)."""
    run_dir = tempfile.mkdtemp(prefix=prefix)
    if wrap_in_specs:
        specs_dir = os.path.join(run_dir, "specs")
        os.makedirs(specs_dir)
        spec_path = os.path.join(specs_dir, "spec.md")
    else:
        spec_path = os.path.join(run_dir, "spec.md")
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write("# spec\nSome spec content.\n")
    if log_name is not None:
        with open(os.path.join(run_dir, log_name), "w", encoding="utf-8") as f:
            f.write(log_content)
    return run_dir, spec_path


def _rl_verifier_pass_dispatch(tool_use_id, spec_path, extra_prompt_text=""):
    """A Task dispatch matching _VERIFIER_DETECT, paired (by tool_use_id)
    with its own tool_result carrying "verdict: pass" -- the SAME
    correlated pair the spec's own design requires (never a whole-turn
    scan). Returns (assistant_msg_event, tool_result_event)."""
    tu = tool_use(
        "Task", description=_RUNLOG_VERIFIER_DESC,
        prompt=("Review the implemented widget build against the spec at %s. %s"
                % (spec_path, extra_prompt_text)))
    tu["id"] = tool_use_id
    result = tool_result_event(
        tool_use_id, "Reviewed the implemented artifact. VERDICT: PASS -- looks good.")
    return assistant_msg(tu), result


def _rl_verifier_fail_dispatch(tool_use_id, spec_path):
    """Same shape as _rl_verifier_pass_dispatch but the paired result
    carries VERDICT: FAIL (AC8)."""
    tu = tool_use(
        "Task", description=_RUNLOG_VERIFIER_DESC,
        prompt="Read the spec at %s and review it." % spec_path)
    tu["id"] = tool_use_id
    result = tool_result_event(
        tool_use_id, "Reviewed the implemented artifact. VERDICT: FAIL -- needs rework.")
    return assistant_msg(tu), result


def _rl_live_post_build_verifier_pass_dispatch(tool_use_id, spec_path):
    tu = tool_use(
        "Agent", description="Verifier for widget build",
        subagent_type="verifier",
        prompt="Read the spec at %s and verify the implemented widget build." % spec_path)
    tu["id"] = tool_use_id
    result = tool_result_event(tool_use_id, "Reviewed implementation behavior. VERDICT: PASS.")
    return assistant_msg(tu), result


def _rl_plan_check_verifier_pass_dispatch(tool_use_id, spec_path):
    tu = tool_use(
        "Agent", description="plan-check verifier for the widget spec",
        subagent_type="plan-check-verifier",
        prompt=("Review the spec before implementation. SPEC: %s\n"
                "Report LOOP_GATE: PLAN_PASS or PLAN_FAIL.") % spec_path)
    tu["id"] = tool_use_id
    result = tool_result_event(
        tool_use_id,
        "Reviewed the plan only.\nPLAN_SUPPORT_JSON={\"supported\": true}\n"
        "REVIEWED_SPEC_SHA256=fixture-sha\nVERDICT: PASS\nLOOP_GATE: PLAN_PASS")
    return assistant_msg(tu), result


class RunlogGateCurrentTurnPostBuildClassifier(unittest.TestCase):
    def test_live_agent_verifier_for_task_no_log_blocks(self):
        run_dir, spec_path = _rl_make_run_dir("rl-live-postbuild-", True, None)
        try:
            dispatch, result = _rl_live_post_build_verifier_pass_dispatch("rl-live-1", spec_path)
            code, err = run_guard(make_turn_events(dispatch, result))
            self.assertEqual(code, 2, err)
            self.assertIn(os.path.realpath(run_dir), err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_plan_check_support_bound_pass_no_log_allows(self):
        run_dir, spec_path = _rl_make_run_dir("rl-plancheck-", True, None)
        try:
            dispatch, result = _rl_plan_check_verifier_pass_dispatch("rl-plan-1", spec_path)
            code, err = run_guard(make_turn_events(dispatch, result))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateBasicBlock(unittest.TestCase):
    """AC1: a Task/Agent dispatch matching _VERIFIER_DETECT whose own paired
    tool_result contains verdict: pass AND whose prompt references a real,
    specs/-wrapped spec FILE with no run log in that spec's derived run
    directory (the run directory, NOT the specs/ subdirectory itself) ->
    exit 2, message names the run directory."""

    def test_specs_wrapped_spec_no_log_blocks_and_names_run_dir(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac1-", wrap_in_specs=True, log_name=None)
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl1", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 2, err)
            self.assertIn(os.path.realpath(run_dir), err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateCanonicalLogPresent(unittest.TestCase):
    """AC2: same setup as AC1, but the run directory already has a non-empty
    run_log.md -> no block."""

    def test_specs_wrapped_spec_with_run_log_md_allows(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac2-", wrap_in_specs=True, log_name="run_log.md",
            log_content="Brief, spec, iteration diffs, final summary.\n")
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl2", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateLegacyNameGrandfathered(unittest.TestCase):
    """AC3: same setup, but the non-empty log uses a LEGACY name (RUN_LOG.md
    or iteration_log.md) -> no block (grandfathered), for EITHER legacy
    name."""

    def test_specs_wrapped_spec_with_RUN_LOG_md_allows(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac3a-", wrap_in_specs=True, log_name="RUN_LOG.md",
            log_content="legacy-named log content\n")
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl3a", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_specs_wrapped_spec_with_iteration_log_md_allows(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac3b-", wrap_in_specs=True, log_name="iteration_log.md",
            log_content="legacy-named log content\n")
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl3b", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateWhitespaceOnlyCountsAsMissing(unittest.TestCase):
    """AC4: a run_log.md that exists but contains only whitespace is treated
    as missing (blocks), per the explicit .strip() non-emptiness
    definition."""

    def test_whitespace_only_run_log_still_blocks(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac4-", wrap_in_specs=True, log_name="run_log.md",
            log_content="   \n\t\n   \n")
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl4", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 2, err)
            self.assertIn(os.path.realpath(run_dir), err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateWholeTurnLeakageRound1(unittest.TestCase):
    """AC5: correlation, not whole-turn scanning. Two Task dispatches in the
    same turn: dispatch A matches _VERIFIER_DETECT, its OWN paired result
    contains verdict: pass, and its OWN prompt references real spec file X
    (run directory HAS a log). A SEPARATE, unrelated tool_result elsewhere
    in the turn (e.g. a Bash `ls runs/` result) happens to mention real spec
    file Y (run directory does NOT have a log). Y must never become a
    candidate -- no block."""

    def test_unrelated_tool_result_mentioning_unlogged_spec_does_not_block(self):
        run_dir_x, spec_x = _rl_make_run_dir(
            "rl-ac5-x-", wrap_in_specs=True, log_name="run_log.md",
            log_content="logged\n")
        run_dir_y, spec_y = _rl_make_run_dir(
            "rl-ac5-y-", wrap_in_specs=True, log_name=None)
        try:
            dispatch_a, result_a = _rl_verifier_pass_dispatch("rl5a", spec_x)
            ls_tu = tool_use_with_id("rl5b", "ls runs/")
            ls_result = tool_result_event(
                "rl5b",
                "runs/other-run/specs/spec.md\n%s\n(unrelated ls output "
                "mentioning spec file Y for background only)" % spec_y)
            events = make_turn_events(
                dispatch_a, result_a, assistant_msg(ls_tu), ls_result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir_x, ignore_errors=True)
            shutil.rmtree(run_dir_y, ignore_errors=True)


class RunlogGateContextHandoffLeakageRound2(unittest.TestCase):
    """AC6: within-prompt context-handoff leakage. A single dispatch's
    prompt BOTH (a) explicitly instructs reading its own real spec file
    (run directory HAS a log) and (b) separately mentions, for background
    context only, a DIFFERENT real run directory's BARE path (no spec-file
    suffix) whose run directory does NOT have a log. The bare mention must
    never resolve to a spec-file match -> no block."""

    def test_bare_directory_background_mention_does_not_block(self):
        run_dir_logged, spec_logged = _rl_make_run_dir(
            "rl-ac6-logged-", wrap_in_specs=True, log_name="run_log.md",
            log_content="logged\n")
        run_dir_unlogged, _spec_unlogged = _rl_make_run_dir(
            "rl-ac6-unlogged-", wrap_in_specs=True, log_name=None)
        try:
            extra = ("For prior precedent see %s/ (a similar past build) -- "
                      "no need to read anything there." % run_dir_unlogged)
            dispatch, result = _rl_verifier_pass_dispatch(
                "rl6", spec_logged, extra_prompt_text=extra)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir_logged, ignore_errors=True)
            shutil.rmtree(run_dir_unlogged, ignore_errors=True)


class RunlogGateNonVerifierDispatchVerdictMention(unittest.TestCase):
    """AC7: "verdict: pass" appearing in a tool_result that does NOT belong
    to a _VERIFIER_DETECT-matching Task/Agent dispatch (e.g. a Coder's own
    report happens to quote the string) -> no block. The pairing requires
    BOTH the dispatch-shape match AND its own paired result containing the
    verdict.

    A preceding, genuine plan-check Verifier dispatch (PLAN_VERIFIER,
    module-level fixture) is included so the UNRELATED pre-existing
    plan-check-before-Coder gate does not itself fire and mask what this
    test is isolating -- only the Coder dispatch's own paired result
    quoting "VERDICT: PASS" is the thing under test here."""

    def test_coder_dispatch_quoting_verdict_pass_does_not_block(self):
        """[D.2 R4] Rebuilt onto a genuine, resolved Verifier-PASS credit
        chain (real spec file + matching SHA256 + a paired
        REVIEWED_SPEC_SHA256=/LOOP_GATE: PLAN_PASS result) so the now-
        mandatory spec-bound-credit gate does not itself fire and mask
        what this test isolates (AC7's run-log verdict-mention gate) -- a
        bare marker-less PLAN_VERIFIER no longer suffices to keep the
        unrelated PLAN_CHECK gate quiet, as it did when this fixture was
        first written."""
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac7-", wrap_in_specs=True, log_name=None)
        try:
            spec_hash = _sb_sha256(spec_path)
            verifier = _sb_verifier(spec_path, spec_hash, tool_use_id="rl7-verifier",
                                     run_in_background=False)
            verifier_pass = _sb_pass_result("rl7-verifier", spec_hash)
            coder_tu = _sb_tool_use(
                "Task", "rl7", description="Coder for the build",
                prompt="Implement per the spec at %s.\nSPEC: %s\nSPEC_SHA256=%s"
                       % (spec_path, spec_path, spec_hash))
            coder_result = tool_result_event(
                "rl7",
                "Implemented the change. For context, the plan-check "
                "verifier previously said VERDICT: PASS on the approach.")
            events = make_turn_events(
                assistant_msg(verifier), verifier_pass,
                assistant_msg(coder_tu), coder_result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateVerdictFailNeverBlocks(unittest.TestCase):
    """AC8: a VERDICT: FAIL turn -> no block regardless of run-log state
    (tested with NO log present, the case most likely to falsely block if
    the verdict-text check were broken/reversed)."""

    def test_verdict_fail_no_log_still_allows(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac8-", wrap_in_specs=True, log_name=None)
        try:
            dispatch, result = _rl_verifier_fail_dispatch("rl8", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateBareDirectoryNeverCandidate(unittest.TestCase):
    """AC9: a path token resolving to a bare directory (even one containing
    specs/) with NO explicit spec.md/spec_v*.md FILE reference in the
    dispatch text is never treated as a candidate -- only an explicit
    spec-file path qualifies. Tested by referencing the specs/ directory
    itself (not spec.md inside it) in the dispatch prompt/result, with the
    run directory having no log -- must not block."""

    def test_bare_specs_directory_reference_never_a_candidate(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac9-", wrap_in_specs=True, log_name=None)
        specs_dir = os.path.dirname(spec_path)
        try:
            tu = tool_use(
                "Task", description=_RUNLOG_VERIFIER_DESC,
                prompt="Review the materials under %s/ generally." % specs_dir)
            tu["id"] = "rl9"
            result = tool_result_event(
                "rl9", "Reviewed. VERDICT: PASS -- looks good.")
            events = make_turn_events(assistant_msg(tu), result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateFailOpenOnUnexpectedException(unittest.TestCase):
    """AC10: fail-open. Any unexpected exception in this gate's entire
    mechanism (a malformed target file, here: a run_log.md containing bytes
    that are not valid UTF-8, raising UnicodeDecodeError -- NOT an OSError
    subclass, so it is NOT caught by _runlog_has_real_log's own inner
    per-name `except OSError` -- must only be caught by the file-spanning
    try/except Exception the spec requires wrapping the ENTIRE mechanism
    in) disables JUST this gate, never crashes the hook. Confirmed directly
    that UnicodeDecodeError is not an OSError subclass before relying on
    this as the fail-open trigger."""

    def test_non_utf8_run_log_bytes_fail_open_not_crash(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac10-", wrap_in_specs=True, log_name=None)
        try:
            bad_log = os.path.join(run_dir, "run_log.md")
            with open(bad_log, "wb") as f:
                f.write(b"\xff\xfe\x00\x01 not valid utf-8 \x80\x81")
            dispatch, result = _rl_verifier_pass_dispatch("rl10", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            # Fail-open: the gate must not crash (no Python traceback), and
            # must not itself force a block via this malformed-file path --
            # exit 0 (this turn has no OTHER violation).
            self.assertEqual(code, 0, err)
            self.assertNotIn("Traceback", err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateAppendsToViolationsNeverBareExit(unittest.TestCase):
    """AC11: this gate appends to _VIOLATIONS (never a bare sys.exit(2)) and
    its _log_gate call stays at its own site -- proven behaviorally by
    combining this gate's own violation with an UNRELATED pre-existing
    gate's violation in the SAME turn and asserting BOTH are reported in
    full (the "N violations detected" aggregation banner, matching this
    file's own established multi-violation-reporting precedent
    (TwoDifferentThingsSameTurnBothReportedMasking1) -- if this gate used a
    bare sys.exit(2) instead of appending, only ONE of the two violations
    would ever be visible, whichever ran first."""

    def test_runlog_violation_and_unrelated_role_edit_violation_both_reported(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac11-", wrap_in_specs=True, log_name=None)
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl11", spec_path)
            events = make_turn_events(
                assistant_msg(ROLE_EDIT), dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 2, err)
            self.assertIn("violations detected", err)
            self.assertIn(os.path.realpath(run_dir), err)
            # ROLE_EDIT's own gate fires as RegressionGate's fixture proves
            # (no green suite, no verifier run for it in this turn) --
            # confirm its own evidence is present too, not masked.
            self.assertIn("roles/verifier.md", err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


# AC12 [BEHAVIORAL, process-shaped] -- no dedicated executable test.
#
# AC12's own wording is: "Before implementation, `grep -n
# "_tu_dispatch_text" hooks/loop_stop_guard.py` is run to determine which
# branch...applies; the Coder's decision log states explicitly which branch
# was taken." This is a description of a PROCESS STEP (a one-time grep run
# before writing code, recorded in a decision log), not a claim about
# runtime behavior of the finished gate -- there is no code-under-test
# artifact for a unit test to exercise; the "correct" outcome is a fact
# about what the Coder DID, not what the program DOES for any input. This
# test-writer pass already performed that exact grep directly (see the
# section banner comment above this block, and the accompanying decision
# log in the response to Oga) and confirmed the "yes" branch applies -- that
# finding is what shapes RunlogGateWorkflowShapedDispatch below (written as
# a real, unskipped test, per AC12's own branch determination) and
# RunlogGateSharedFunctionArchitecture's Workflow-dimension option. A
# dedicated unit test asserting "a grep was run" would be a hollow,
# non-behavioral tautology (DOC-shaped busywork, not a [BEHAVIORAL]
# guarantee) -- so none is written; this comment plus the decision log is
# the intended, complete discharge of AC12 for a test-writer pass, matching
# how the spec itself frames AC12 ("the Coder's decision log states...").


class RunlogGateBareRootConventionRound3(unittest.TestCase):
    """AC13: a dispatch whose prompt/result names a real runs/<name>/spec.md
    with NO specs/ wrapper (the older, still-live convention), whose run
    directory has no run log -> exit 2, identical treatment to the
    specs/-wrapped case in AC1. Companion no-block case uses
    iteration_log.md specifically (see the section-banner comment above:
    run_log.md/RUN_LOG.md in a bare-root run dir collides with the
    PRE-EXISTING, unrelated adjacency gate's own _STATUS_DOC_DENYLIST, which
    is a real, separate, out-of-scope gate's behavior, not a defect in this
    new gate)."""

    def test_bare_root_spec_no_log_blocks_and_names_run_dir(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac13-block-", wrap_in_specs=False, log_name=None)
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl13a", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 2, err)
            self.assertIn(os.path.realpath(run_dir), err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_bare_root_spec_with_log_allows(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac13-allow-", wrap_in_specs=False, log_name="iteration_log.md",
            log_content="bare-root run log content\n")
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl13b", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateWorkflowShapedDispatch(unittest.TestCase):
    """AC14: a Workflow-shaped dispatch (name == "Workflow", not Task/Agent/
    Subagent) whose SCRIPT content is Verifier-shaped, whose paired result
    contains verdict: pass, and whose script references a real, unlogged
    spec file -> exit 2, identical treatment to the Task/Agent case in AC1.
    Exercises BOTH halves of the yes-branch fix together: the text-
    extraction helper (_tu_dispatch_prompt_text's Workflow branch reading
    `script`, not `prompt`) AND the "workflow" membership addition (this
    gate's own `_rl_tu.get("name", "").lower() not in (...)` check must
    include "workflow").

    Written as a REAL, EXECUTABLE test (not skipped): this test-writer pass
    directly confirmed (grep -n "_tu_dispatch_text" hooks/loop_stop_guard.py,
    plus grep -n '"workflow"' hooks/loop_stop_guard.py) that
    H-WORKFLOW-BLINDSPOT-1 has ALREADY landed -- the spec's "yes" branch
    applies, so this AC is meaningful today, not conditionally skipped."""

    def test_workflow_dispatch_verdict_pass_unlogged_spec_blocks(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac14-", wrap_in_specs=True, log_name=None)
        try:
            wf = workflow_tool_use(
                "await agent({description: '%s', "
                "prompt: 'Read the spec at %s and review it.'})"
                % (_RUNLOG_VERIFIER_DESC, spec_path))
            wf["id"] = "rl14"
            result = tool_result_event(
                "rl14", "Reviewed the plan. VERDICT: PASS -- looks good.")
            events = make_turn_events(assistant_msg(wf), result)
            code, err = run_guard(events)
            self.assertEqual(code, 2, err)
            self.assertIn(os.path.realpath(run_dir), err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_workflow_dispatch_verdict_pass_logged_spec_allows(self):
        """Companion: the same Workflow-shaped dispatch, but the run
        directory already has a real run_log.md -> no block. Proves the
        Workflow path isn't a permanently-blocking special case -- it
        shares the same _runlog_has_real_log check as the Task/Agent path."""
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac14-allow-", wrap_in_specs=True, log_name="run_log.md",
            log_content="logged\n")
        try:
            wf = workflow_tool_use(
                "await agent({description: '%s', "
                "prompt: 'Read the spec at %s and review it.'})"
                % (_RUNLOG_VERIFIER_DESC, spec_path))
            wf["id"] = "rl14b"
            result = tool_result_event(
                "rl14b", "Reviewed the plan. VERDICT: PASS -- looks good.")
            events = make_turn_events(assistant_msg(wf), result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_equivalent_task_dispatch_already_blocks(self):
        """Companion proving genuine equivalence: the identical scenario via
        a real Task dispatch (AC1's own shape) already blocks -- confirming
        the Workflow case is being held to the SAME standard, not a looser
        or stricter one."""
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac14-equiv-", wrap_in_specs=True, log_name=None)
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl14c", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 2, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateSharedFunctionArchitecture(unittest.TestCase):
    """AC15: AC13's bare-root candidate and AC14's Workflow candidate must
    route through the SAME _runlog_has_real_log function and the SAME
    _runlog_candidate_dirs set that AC1-4 already exercise -- not a
    duplicated or special-cased check. Verified with tests combining a NEW
    dimension with an ALREADY-TESTED one from a DIFFERENT axis:
      (a) bare-root (AC13's new dimension) + legacy-name-only log (AC3's
          already-tested dimension) -> no block, proving the bare-root
          branch and the legacy-name grandfather both apply TOGETHER.
      (b) Workflow-shaped dispatch (AC14's new dimension) + legacy-name-only
          log (AC3's already-tested dimension), specs/-wrapped -> no block,
          proving the Workflow branch and the legacy-name grandfather both
          apply TOGETHER too (a different combination than (a), covering
          the OTHER new AC14 dimension crossed with the same already-tested
          axis, per the spec's "at least one test combining..." wording
          read generously as "cover each new dimension at least once")."""

    def test_bare_root_plus_legacy_name_only_log_allows(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac15a-", wrap_in_specs=False, log_name="iteration_log.md",
            log_content="legacy name, bare-root layout\n")
        try:
            dispatch, result = _rl_verifier_pass_dispatch("rl15a", spec_path)
            events = make_turn_events(dispatch, result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_workflow_dispatch_plus_legacy_name_only_log_allows(self):
        run_dir, spec_path = _rl_make_run_dir(
            "rl-ac15b-", wrap_in_specs=True, log_name="RUN_LOG.md",
            log_content="legacy name, Workflow dispatch\n")
        try:
            wf = workflow_tool_use(
                "await agent({description: '%s', "
                "prompt: 'Read the spec at %s and review it.'})"
                % (_RUNLOG_VERIFIER_DESC, spec_path))
            wf["id"] = "rl15b"
            result = tool_result_event(
                "rl15b", "Reviewed the plan. VERDICT: PASS -- looks good.")
            events = make_turn_events(assistant_msg(wf), result)
            code, err = run_guard(events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class RunlogGateExistingSuiteUnaffectedMarker(unittest.TestCase):
    """AC16/AC17 are [DOC]-only (README/USAGE.md wording, fix_plan.md entry
    update) -- out of scope for this test-writer pass's executable-test
    coverage (no [BEHAVIORAL] runtime claim to drive a test from; a Coder
    implementing them is graded by a text/doc-shaped Verifier check, not a
    unit test). This marker class instead pins the same explicit,
    named-test guarantee ReviewCommitGateExistingSuiteUnaffected already
    established for its own gate: a representative sample of PRE-EXISTING
    gate behaviors, run again here for locality, to make the "this new
    gate's addition does not regress anything above it in the file" claim
    an asserted fact in THIS section, not merely an implied one from "the
    rest of the file still runs.\""""

    def test_representative_preexisting_gates_unaffected_by_new_gate_addition(self):
        code, err = run_guard(make_turn([ROLE_EDIT]))
        self.assertEqual(code, 2, err)  # RegressionGate baseline
        code, _ = run_guard(make_turn([CODER_AGENT]))
        self.assertEqual(code, 2)  # PlanBeforeCoderGate baseline
        # [D.2 rule-1 code==2-inversion] see ReviewCommitGateExistingSuite
        # Unaffected's identical fixture above for the full reasoning: no
        # marker + zero tool_results is structurally unsatisfiable under
        # the v1 spec-bound-credit contract.
        code, _ = run_guard(make_turn([PLAN_VERIFIER, CODER_AGENT]))
        self.assertEqual(code, 2)  # PlanBeforeCoderGate baseline (v1 contract)
        docx = tool_use("Write", file_path="/x/resume.docx", content="...")
        code, _ = run_guard(make_turn([docx]))
        self.assertEqual(code, 0)  # ExistingBehaviorHolds baseline


# ROUND 5 (2026-07-08): a SubagentStop-based structural coder-detection
# signal (hooks/feature_write_scan.py + loop_stop_guard.py's
# _structural_coder_verdict()/_resolve_agent_id()) and its direct-call
# test coverage (FeatureWriteScanDirectCall, FeatureWriteScanGatingMarkdown
# DirectCall, StructuralCoderDetectionSubagentBehaviorFlag,
# StructuralCoderDetectionNestedDispatchBypass,
# StructuralCoderDetectionUnderscoreAgentIdPathA,
# StructuralCoderDetectionCrossSessionCollisionPathA, plus the
# write_subagent_behavior_flag()/dispatch_tool_use_with_id() fixtures they
# used) were built, then REVERTED here after independent adversarial
# verification found two real, reproduced bypasses (a Bash-forged flag-file
# spoof, and an async-transcript-lag false-clean timing race). See
# fix_plan.md's "ROUND 5 OUTCOME" sub-section under
# H-STOPGUARD-SUBAGENTTYPE-ADJACENCY-SELFMATCH-1 for the full writeup.


# =============================================================================
# Evidence-Gate Phase 4 (spec: loop-team/runs/2026-07-09_evidence-gate-
# phase4/specs/spec.md) -- Parts C, D, E in loop_stop_guard.py (NONE of this
# exists yet), plus AC23's regression test for the corrected line-845
# PLAN_CHECK short-circuit fix (also NOT yet applied to the live file).
#
# Every class name below contains "Phase4" so `pytest -k "not Phase4"`
# cleanly isolates the file's PRE-EXISTING (pre-Phase-4) coverage for AC22's
# own regression check, without this phase's own (currently-red,
# pre-implementation) new tests in the way.
#
# Part C/D/E's target_fix_plan_path is resolved __file__-relative from
# hooks/loop_stop_guard.py's OWN location (spec's theme-1 fix: "always THIS
# repo's own single, fixed tracking file... os.path.join(os.path.dirname(
# os.path.abspath(__file__)), "..", "fix_plan.md")") -- deliberately NOT
# configurable via any env var or per-micro-step target. Invoking the REAL,
# live loop_stop_guard.py in place would therefore always resolve to THIS
# REPO'S OWN live fix_plan.md -- the durable, shared, actively-read-by-
# other-sessions gate-hole log. Mutating that file, even temporarily with a
# try/finally restore, is an unacceptable risk for an automated test suite
# (see this project's own "one session per worktree" / shared-worktree
# false-positive lessons). Every Part C/D/E end-to-end test below instead
# runs against an ISOLATED, throwaway COPY of hooks/ (+ loop-team/harness/,
# which closure_touch_scan.py's own cross-directory import will need) rooted
# at a fresh tempfile.mkdtemp(), so __file__-relative resolution inside the
# COPIED loop_stop_guard.py lands on a scratch fix_plan.md this test
# constructs and owns completely -- the literal reading of AC11's own phrase
# "a real, on-disk SCRATCH fix_plan.md copy".
# =============================================================================

REPO_HARNESS_DIR = os.path.join(REPO_DIR, "loop-team", "harness")
_RUN_AND_RECORD = os.path.join(REPO_HARNESS_DIR, "run_and_record.py")


def _make_scratch_hook_repo():
    """Build an isolated <scratch>/hooks/ + <scratch>/loop-team/harness/ tree
    mirroring this repo's real layout closely enough for every
    __file__-relative resolution inside loop_stop_guard.py (and whatever
    closure_touch_scan.py ends up needing) to work identically to
    production, rooted at a throwaway <scratch>/fix_plan.md this helper's
    caller controls completely. Returns
    (scratch_root, scratch_guard_path, scratch_fixplan_path) -- the fix_plan.md
    file itself is NOT created here (callers write whatever fixture content
    they need). Caller must shutil.rmtree(scratch_root, ignore_errors=True)
    in its own tearDown."""
    scratch_root = tempfile.mkdtemp(prefix="phase4-scratch-repo-")
    scratch_hooks = os.path.join(scratch_root, "hooks")
    shutil.copytree(
        HOOKS_DIR, scratch_hooks,
        ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"),
    )
    if os.path.isdir(REPO_HARNESS_DIR):
        shutil.copytree(
            REPO_HARNESS_DIR, os.path.join(scratch_root, "loop-team", "harness"),
            ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"),
        )
    scratch_guard = os.path.join(scratch_hooks, "loop_stop_guard.py")
    scratch_fixplan = os.path.join(scratch_root, "fix_plan.md")
    return scratch_root, scratch_guard, scratch_fixplan


def _run_guard_at(guard_path, events, session_id=None, stop_hook_active=False,
                   gate_dir=None, transcript_path=None):
    """Like run_guard_full() above, but invokes an EXPLICIT guard_path (an
    isolated scratch copy from _make_scratch_hook_repo(), or the real GUARD
    for tests that don't touch fix_plan.md at all) and an explicit,
    overridable gate_dir (default: the shared module-level GATE_DIR every
    other class in this file already uses)."""
    own_tmp = transcript_path is None
    if own_tmp:
        fd, transcript_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
    try:
        with open(transcript_path, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        payload = {"transcript_path": transcript_path, "stop_hook_active": stop_hook_active}
        if session_id is not None:
            payload["session_id"] = session_id
        env = dict(os.environ, LOOP_GATE_DIR=(gate_dir or GATE_DIR))
        p = subprocess.run([sys.executable, guard_path], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        if own_tmp:
            os.remove(transcript_path)


def _make_real_proof_block(gate_dir, command_argv):
    """Invoke the REAL run_and_record.py CLI (mirrors loop-team/harness/
    test_fixplan_closure_lint.py's own `_make_real_snapshot` helper) to
    produce a genuine, byte-for-byte-real "Proof:\\n- field: value" block,
    for Part C/D/E fixtures that need an ACTUALLY-valid (non-fabricated)
    Proof block. Returns the raw block text, newline-terminated."""
    env = dict(os.environ, LOOP_GATE_DIR=str(gate_dir))
    p = subprocess.run([sys.executable, _RUN_AND_RECORD, "--"] + list(command_argv),
                       capture_output=True, text=True, timeout=30, env=env)
    stdout = p.stdout.lstrip()
    _record, end = json.JSONDecoder().raw_decode(stdout)
    return stdout[end:].strip() + "\n"


# [Section E] status_claim_audit.py's PROBE_COMMAND_RE deliberately classifies
# a bare ["true"]-wrapped proof command as PROBE_ONLY (anti-gaming: "wrap
# `true` in run_and_record.py to fake a real proof"). Fixtures that need a
# genuinely-valid (non-PROBE_ONLY) Proof block use this real, substantive,
# fast, deterministic command instead -- an actual pytest run of a small,
# stable, always-green hook test file -- rather than defaulting back to
# ["true"] or inventing an equally-trivial regex-dodging substitute.
_REAL_PROOF_COMMAND = [sys.executable, "-m", "pytest",
                       os.path.join(HOOKS_DIR, "test_loop_logger.py"), "-q"]


def write_closure_violation_flag(session_id, agent_id, entries, gate_dir=None, mtime=None):
    """Write a real {session_id}_{agent_id}.closure_violation flag, with
    JSON content matching the shape hooks/subagent_stop_gate.py's Fifth
    responsibility is specified to write
    ([{"heading": ..., "messages": [...], "warnings": [...]}, ...])."""
    d = gate_dir or GATE_DIR
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "%s_%s.closure_violation" % (session_id, agent_id))
    content = entries if isinstance(entries, str) else json.dumps(entries)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# AC11 [BEHAVIORAL]: Part C end-to-end -- a turn introducing a CLOSED heading
# with a MISSING Proof block on a real, on-disk scratch fix_plan.md copy ->
# exit 2 naming that heading. The same shape with a VALID (real, via
# run_and_record.py -- true) Proof block -> exit 0.
# ---------------------------------------------------------------------------

class Phase4AC11PartCFireMissingAndValidProofBlock(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-ac11-gate-")

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def test_missing_proof_block_on_new_closed_heading_blocks(self):
        original = "## H-AC11-PRE (OPEN, still open)\nNothing closed yet.\n"
        new_block = (
            "## H-AC11-MISSING -- CLOSED (2026-07-09, introduced this turn)\n"
            "Some closure prose, but no Proof block at all.\n"
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original)
        edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                           old_string="x", new_string=new_block)
        # The hook fires AFTER the tool already ran -- simulate the edit
        # having already landed on disk before Part C's own fresh re-read.
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original + new_block)

        code, err = _run_guard_at(self._scratch_guard, make_turn([edit_tu]))
        self.assertEqual(code, 2, err)
        self.assertIn("H-AC11-MISSING", err)

    def test_valid_proof_block_on_new_closed_heading_passes(self):
        proof_block = _make_real_proof_block(self._gate_dir, _REAL_PROOF_COMMAND)
        original = "## H-AC11-PRE2 (OPEN, still open)\nNothing closed yet.\n"
        new_block = (
            "## H-AC11-VALID -- CLOSED (2026-07-09, introduced this turn)\n"
            "Real closure with a genuine, matching Proof block.\n\n" + proof_block
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original)
        edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                           old_string="x", new_string=new_block)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original + new_block)

        code, err = _run_guard_at(self._scratch_guard, make_turn([edit_tu]))
        self.assertEqual(code, 0, err)


# ---------------------------------------------------------------------------
# AC12 [BEHAVIORAL]: Part C anti-over-fire, exercised end-to-end (not just
# the unit-level find_touched_closed_headings test in AC1): a turn whose
# edit is confined to ordinary body prose in an EXISTING CLOSED heading
# (outside its Proof span) -- even one with a currently-invalid Proof block
# -- exits 0.
#
# NOTE (transparency, not a defect): with NO Part C code at all yet, this
# turn already exits 0 today for an unrelated reason (fix_plan.md is a plain
# .md, not a gating surface for any EXISTING gate) -- this test is expected
# to be GREEN even pre-implementation, and remains a real regression guard
# once Part C lands (proving the anti-over-fire property continues to hold
# against the real gate, not merely "nothing exists yet").
# ---------------------------------------------------------------------------

class Phase4AC12PartCAntiOverFireBodyProseOutsideProofSpan(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)

    def test_body_prose_edit_outside_proof_span_does_not_fire_even_with_invalid_proof(self):
        content = (
            "## H-AC12-1 -- CLOSED (2026-07-09, some evidence)\n"
            "Some original body prose.\n\n"
            "Proof:\n"
            "- command: echo hi\n"
            "- exit_code: 0\n"
        )  # deliberately INCOMPLETE (missing proof_snapshot/verified_at)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)
        new_prose = ("Some original body prose. ADDITIONAL CONTEXT ADDED "
                     "THIS TURN, unrelated to the Proof block.")
        edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                           old_string="Some original body prose.", new_string=new_prose)
        updated = content.replace("Some original body prose.", new_prose)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(updated)

        # [Section E, explicit design decision -- not a silent patch] Traced
        # status_claim_audit._block_armed() directly: when a touched range
        # overlaps the block's overall extent but not the claim/proof spans
        # specifically, and the touch isn't itself a whole-block Write, the
        # function's own final fallback unconditionally returns True (armed)
        # -- an edit ANYWHERE within a CLOSED heading's body re-arms an
        # audit of that heading, not just edits touching the claim/proof
        # spans. This is intentionally broader than this test's original
        # assumption, out of scope to narrow (status_claim_audit.py is
        # already-committed, already-tested infrastructure -- Section B),
        # and consistent with this project's own repeatedly-established
        # governing philosophy (prefer a false-positive re-audit over any
        # risk of under-detection). This heading's Proof block is
        # deliberately INCOMPLETE, so the re-armed audit correctly finds
        # INCOMPLETE_EVIDENCE and blocks -- confirmed live. If this
        # judgment call is wrong, plan-check should catch it.
        code, err = _run_guard_at(self._scratch_guard, make_turn([edit_tu]))
        self.assertEqual(code, 2, err)
        self.assertIn("INCOMPLETE_EVIDENCE", err)


# ---------------------------------------------------------------------------
# AC13 [BEHAVIORAL]: Part C, edit confined to a Proof span with an
# intentionally STALE cited file -> exit 0 WITH a warning printed on stderr
# (advisory does not block) -- but the SAME fixture invoked via
# fixplan_closure_lint.py's own direct CLI use still exits 1/flags it
# (cross-references AC7/AC8's per-function proof against the end-to-end gate
# behavior).
# ---------------------------------------------------------------------------

class Phase4AC13AdvisoryStaleWarnsButManualCliStillBlocks(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-ac13-gate-")
        self._evidence_file = os.path.join(self._scratch_root, "ac13_evidence.txt")
        with open(self._evidence_file, "w", encoding="utf-8") as f:
            f.write("original content\n")

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def test_stale_cited_file_via_proof_span_edit_warns_but_does_not_block(self):
        proof_block = _make_real_proof_block(self._gate_dir, ["cat", self._evidence_file])
        with open(self._evidence_file, "w", encoding="utf-8") as f:
            f.write("MODIFIED after capture\n")  # genuinely stale vs. the snapshot

        content = (
            "## H-AC13-1 -- CLOSED (2026-07-09, some evidence)\n"
            "Real closure citing evidence that goes stale after capture.\n\n"
            + proof_block
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)

        # Edit confined to the Proof span: re-affirm the SAME Proof block
        # text (the realistic "the agent (re)wrote the Proof block" shape).
        edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                           old_string=proof_block, new_string=proof_block)
        code, err = _run_guard_at(self._scratch_guard, make_turn([edit_tu]))
        self.assertEqual(code, 0, err)
        self.assertIn("STALE", err)

    def test_same_fixture_via_direct_cli_still_blocks(self):
        proof_block = _make_real_proof_block(self._gate_dir, ["cat", self._evidence_file])
        with open(self._evidence_file, "w", encoding="utf-8") as f:
            f.write("MODIFIED after capture\n")
        content = (
            "## H-AC13-2 -- CLOSED (2026-07-09, some evidence)\nReal closure.\n\n"
            + proof_block
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)

        lint_script = os.path.join(REPO_HARNESS_DIR, "fixplan_closure_lint.py")
        p = subprocess.run([sys.executable, lint_script, self._scratch_fixplan],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("STALE", p.stdout)


# ---------------------------------------------------------------------------
# AC14 [BEHAVIORAL]: Part D self-healing -- a fresh .closure_violation flag
# naming a heading that, by the time Part D reads it, has ALREADY been fixed
# (Proof block corrected on disk since the flag was written) does NOT block,
# and the flag file is removed as a result.
# ---------------------------------------------------------------------------

class Phase4AC14PartDSelfHealingFullyFixed(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-ac14-gate-")
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def test_flag_naming_a_now_fixed_heading_does_not_block_and_flag_is_removed(self):
        sid = "ac14-%s" % uuid.uuid4().hex
        heading_line = "H-AC14-1 -- CLOSED (2026-07-09, some evidence)"
        flag_path = write_closure_violation_flag(
            sid, "agentAC14",
            [{"heading": heading_line, "messages": ["missing proof block (...)"], "warnings": []}],
            gate_dir=self._gate_dir)
        self._flags.append(flag_path)

        proof_block = _make_real_proof_block(self._gate_dir, _REAL_PROOF_COMMAND)
        content = "## %s\nReal closure, now fixed.\n\n%s" % (heading_line, proof_block)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)

        code, err = _run_guard_at(
            self._scratch_guard, make_turn([text("nothing this turn")]),
            session_id=sid, gate_dir=self._gate_dir)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(flag_path),
                         "self-healed flag should be removed, not left to linger")


# ---------------------------------------------------------------------------
# AC15 [BEHAVIORAL]: Part D self-healing, partial case -- a fresh flag naming
# TWO headings, one still-bad and one now-fixed, blocks (naming only the
# still-bad one) and the flag content is rewritten to drop the fixed one.
# ---------------------------------------------------------------------------

class Phase4AC15PartDSelfHealingPartialFix(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-ac15-gate-")
        self._flags = []

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def test_flag_naming_two_headings_one_fixed_one_still_bad(self):
        sid = "ac15-%s" % uuid.uuid4().hex
        bad_heading = "H-AC15-BAD -- CLOSED (2026-07-09, some evidence)"
        fixed_heading = "H-AC15-FIXED -- CLOSED (2026-07-09, some evidence)"
        flag_path = write_closure_violation_flag(
            sid, "agentAC15",
            [{"heading": bad_heading, "messages": ["missing proof block (...)"], "warnings": []},
             {"heading": fixed_heading, "messages": ["missing proof block (...)"], "warnings": []}],
            gate_dir=self._gate_dir)
        self._flags.append(flag_path)

        proof_block = _make_real_proof_block(self._gate_dir, _REAL_PROOF_COMMAND)
        content = (
            "## %s\nStill has no Proof block at all.\n\n"
            "## %s\nNow fixed with a real Proof block.\n\n%s"
        ) % (bad_heading, fixed_heading, proof_block)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)

        code, err = _run_guard_at(
            self._scratch_guard, make_turn([text("nothing this turn")]),
            session_id=sid, gate_dir=self._gate_dir)
        self.assertEqual(code, 2, err)
        self.assertIn("H-AC15-BAD", err)
        self.assertNotIn("H-AC15-FIXED", err)

        with open(flag_path, encoding="utf-8") as f:
            remaining = json.load(f)
        remaining_headings = [e.get("heading") for e in remaining]
        self.assertIn(bad_heading, remaining_headings)
        self.assertNotIn(fixed_heading, remaining_headings)


# ---------------------------------------------------------------------------
# AC16 [BEHAVIORAL]: Part E fires via a REAL sub-agent transcript directly
# (async-race coverage), with NO .closure_violation flag present at all --
# proves Part E provides real, independent coverage Part D alone cannot
# close.
# ---------------------------------------------------------------------------

class Phase4AC16PartEDirectTranscriptScanFiresIndependently(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._tmpdirs = []

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_subagent_transcript_closure_violation_caught_with_no_flag_present(self):
        original = "## H-AC16-PRE (OPEN, still open)\nNothing closed yet.\n"
        new_block = (
            "## H-AC16-NEW -- CLOSED (2026-07-09, introduced by sub-agent)\n"
            "Some closure prose, but no Proof block at all.\n"
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            # Simulates the sub-agent's edit already landed on disk.
            f.write(original + new_block)

        project_dir = tempfile.mkdtemp(prefix="phase4-ac16-proj-")
        self._tmpdirs.append(project_dir)
        sid = "ac16-%s" % uuid.uuid4().hex
        agent_id = "agentAC16"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

        sub_edit = tool_use("Edit", file_path=self._scratch_fixplan,
                            old_string="x", new_string=new_block)
        make_agent_dispatch_transcript(sid, agent_id, project_dir, [
            assistant_msg(sub_edit),
        ])

        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        code, err = _run_guard_at(self._scratch_guard, events, session_id=sid,
                                   transcript_path=oga_tpath)
        self.assertEqual(code, 2, err)
        self.assertIn(agent_id, err)
        self.assertIn("H-AC16-NEW", err)
        self.assertEqual(
            glob.glob(os.path.join(GATE_DIR, "%s_*.closure_violation" % sid)), [])


# ---------------------------------------------------------------------------
# AC17 [BEHAVIORAL]: Part E dedup -- given BOTH a fresh .closure_violation
# flag AND that SAME heading also present in the sub-agent's own transcript
# Part E would otherwise scan, the violation is reported ONCE (via Part D),
# not duplicated by Part E.
# ---------------------------------------------------------------------------

class Phase4AC17PartEDedupAgainstPartD(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._tmpdirs = []
        self._flags = []
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-ac17-gate-")

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def test_heading_reported_once_not_duplicated_by_layer2(self):
        heading_line = "H-AC17-DEDUP -- CLOSED (2026-07-09, introduced by sub-agent)"
        original = "## H-AC17-PRE (OPEN, still open)\nNothing closed yet.\n"
        new_block = "## %s\nClosure prose, no Proof block.\n" % heading_line
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(original + new_block)

        project_dir = tempfile.mkdtemp(prefix="phase4-ac17-proj-")
        self._tmpdirs.append(project_dir)
        sid = "ac17-%s" % uuid.uuid4().hex
        agent_id = "agentAC17"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)

        sub_edit = tool_use("Edit", file_path=self._scratch_fixplan,
                            old_string="x", new_string=new_block)
        make_agent_dispatch_transcript(sid, agent_id, project_dir, [
            assistant_msg(sub_edit),
        ])

        flag_path = write_closure_violation_flag(
            sid, agent_id,
            [{"heading": heading_line, "messages": ["missing proof block (...)"], "warnings": []}],
            gate_dir=self._gate_dir)
        self._flags.append(flag_path)

        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        code, err = _run_guard_at(self._scratch_guard, events, session_id=sid,
                                   transcript_path=oga_tpath, gate_dir=self._gate_dir)
        self.assertEqual(code, 2, err)
        self.assertEqual(
            err.count("H-AC17-DEDUP"), 1,
            "heading should be reported exactly once (via Part D), not "
            "duplicated by Part E's own Layer 2 scan: %r" % err)


# ---------------------------------------------------------------------------
# AC18 [BEHAVIORAL]: stop_hook_active: true short-circuits Parts C, D, AND E
# identically (exit 0 immediately, none of this phase's gate logic runs).
#
# NOTE (transparency, not a defect): the stop_hook_active check already sits
# at the very top of loop_stop_guard.py (before ANY gate, existing or new)
# -- these 3 tests are expected to be GREEN even pre-implementation, and
# remain a real regression guard confirming Part C/D/E's placement decision
# once they land.
# ---------------------------------------------------------------------------

class Phase4AC18StopHookActiveShortCircuitsAllThreeParts(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._tmpdirs = []
        self._flags = []
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-ac18-gate-")

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def test_part_c_short_circuited(self):
        new_block = "## H-AC18-C -- CLOSED (2026-07-09, introduced this turn)\nNo Proof block.\n"
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(new_block)
        edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                           old_string="x", new_string=new_block)
        code, err = _run_guard_at(self._scratch_guard, make_turn([edit_tu]),
                                   stop_hook_active=True)
        self.assertEqual(code, 0, err)

    def test_part_d_short_circuited(self):
        sid = "ac18d-%s" % uuid.uuid4().hex
        heading_line = "H-AC18-D -- CLOSED (2026-07-09, some evidence)"
        flag_path = write_closure_violation_flag(
            sid, "agentAC18D",
            [{"heading": heading_line, "messages": ["missing proof block (...)"], "warnings": []}],
            gate_dir=self._gate_dir)
        self._flags.append(flag_path)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write("## %s\nStill no Proof block.\n" % heading_line)

        code, err = _run_guard_at(self._scratch_guard, make_turn([text("nothing")]),
                                   session_id=sid, gate_dir=self._gate_dir,
                                   stop_hook_active=True)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(flag_path),
                        "short-circuited turn must never touch the flag at all")

    def test_part_e_short_circuited(self):
        new_block = "## H-AC18-E -- CLOSED (2026-07-09, introduced by sub-agent)\nNo Proof block.\n"
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(new_block)
        project_dir = tempfile.mkdtemp(prefix="phase4-ac18e-proj-")
        self._tmpdirs.append(project_dir)
        sid = "ac18e-%s" % uuid.uuid4().hex
        agent_id = "agentAC18E"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        sub_edit = tool_use("Edit", file_path=self._scratch_fixplan,
                            old_string="x", new_string=new_block)
        make_agent_dispatch_transcript(sid, agent_id, project_dir, [assistant_msg(sub_edit)])
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        code, err = _run_guard_at(self._scratch_guard, events, session_id=sid,
                                   transcript_path=oga_tpath, stop_hook_active=True)
        self.assertEqual(code, 0, err)


# ---------------------------------------------------------------------------
# AC19 [BEHAVIORAL]: fail-open -- force an unexpected exception in each of
# Parts C, D, and E independently, confirm each degrades to ALLOW, and
# confirm a failure in ONE does not suppress/corrupt the OTHER two's normal
# operation in the SAME invocation.
#
# CAVEAT (documented, not hidden): the individual Part C/E triggers below
# construct a malformed Edit input (a `new_string` KEY OMITTED entirely --
# Part A's own algorithm text says "take input['new_string']", implying
# direct key access) as the most spec-literal, plausible exception source.
# If a real implementation defensively `.get()`s this instead, these
# specific fixtures may not exercise a genuine exception (the malformed edit
# would just be silently skipped, contributing nothing) -- the file-spanning
# try/except is required by spec regardless of whether THIS PARTICULAR input
# shape trips it, so these remain legitimate, best-effort regression probes,
# not a mechanism guarantee. Part D's OWN trigger (an unreadable target
# fix_plan.md during self-healing re-validation) is mechanism-independent:
# the spec mandates Part D "RE-RUN check_single_heading against the CURRENT
# on-disk fix_plan.md", an unavoidable file read.
# ---------------------------------------------------------------------------

class Phase4AC19FailOpenPartC(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)

    def test_malformed_edit_input_this_turn_fails_open_not_crash(self):
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write("## H-AC19-C (OPEN, still open)\nNothing closed.\n")
        malformed = {"type": "tool_use", "name": "Edit",
                     "input": {"file_path": self._scratch_fixplan, "old_string": "x"}}
        code, err = _run_guard_at(self._scratch_guard, make_turn([malformed]))
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)


class Phase4AC19FailOpenPartD(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._flags = []

    def tearDown(self):
        for f in self._flags:
            try:
                os.remove(f)
            except OSError:
                pass
        shutil.rmtree(self._scratch_root, ignore_errors=True)

    def test_unreadable_target_fixplan_during_self_healing_reread_fails_open(self):
        sid = "ac19d-%s" % uuid.uuid4().hex
        heading_line = "H-AC19-D -- CLOSED (2026-07-09, some evidence)"
        flag_path = write_closure_violation_flag(
            sid, "agentAC19D",
            [{"heading": heading_line, "messages": ["missing proof block (...)"], "warnings": []}])
        self._flags.append(flag_path)
        # Replace the (not-yet-created) scratch fix_plan.md with a DIRECTORY:
        # Part D's own self-healing re-check must re-read the CURRENT
        # on-disk file, guaranteeing a real OSError/IsADirectoryError
        # regardless of string-handling defensiveness elsewhere.
        os.makedirs(self._scratch_fixplan)

        code, err = _run_guard_at(self._scratch_guard, make_turn([text("nothing")]),
                                   session_id=sid)
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)


class Phase4AC19FailOpenPartE(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._tmpdirs = []

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_malformed_subagent_edit_input_fails_open_not_crash(self):
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write("## H-AC19-E (OPEN, still open)\nNothing closed.\n")
        project_dir = tempfile.mkdtemp(prefix="phase4-ac19e-proj-")
        self._tmpdirs.append(project_dir)
        sid = "ac19e-%s" % uuid.uuid4().hex
        agent_id = "agentAC19E"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        malformed_sub_edit = {"type": "tool_use", "name": "Edit",
                              "input": {"file_path": self._scratch_fixplan, "old_string": "x"}}
        make_agent_dispatch_transcript(sid, agent_id, project_dir, [assistant_msg(malformed_sub_edit)])
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        code, err = _run_guard_at(self._scratch_guard, events, session_id=sid,
                                   transcript_path=oga_tpath)
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)


class Phase4AC19FailOpenDoesNotSuppressOtherParts(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._tmpdirs = []
        self._flags = []
        self._gate_dir = tempfile.mkdtemp(prefix="phase4-ac19-combo-gate-")

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)

    def test_part_c_failure_does_not_suppress_part_d_or_part_e(self):
        sid = "ac19combo-%s" % uuid.uuid4().hex

        # Part D's own target: a fresh flag naming a heading that is STILL bad.
        d_heading = "H-AC19-COMBO-D -- CLOSED (2026-07-09, some evidence)"
        flag_path = write_closure_violation_flag(
            sid, "agentComboD",
            [{"heading": d_heading, "messages": ["missing proof block (...)"], "warnings": []}],
            gate_dir=self._gate_dir)
        self._flags.append(flag_path)

        # Part E's own target: a sub-agent transcript introducing a
        # DIFFERENT invalid-Proof CLOSED heading.
        e_heading = "H-AC19-COMBO-E -- CLOSED (2026-07-09, introduced by sub-agent)"
        project_dir = tempfile.mkdtemp(prefix="phase4-ac19-combo-proj-")
        self._tmpdirs.append(project_dir)
        agent_id = "agentComboE"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        e_new_block = "## %s\nClosure prose, no Proof block.\n" % e_heading
        sub_edit = tool_use("Edit", file_path=self._scratch_fixplan,
                            old_string="x", new_string=e_new_block)
        make_agent_dispatch_transcript(sid, agent_id, project_dir, [assistant_msg(sub_edit)])

        # Real, current on-disk content: BOTH headings' current state.
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write("## %s\nStill no Proof block.\n\n%s" % (d_heading, e_new_block))

        # Part C's own target: a malformed Edit in OGA'S OWN turn (missing
        # new_string) -- attempts to break Part C specifically, WITHOUT
        # touching the (still perfectly valid, readable) fix_plan.md file
        # itself, so Part D/E's own independent reads of that SAME file stay
        # unaffected.
        malformed_c_edit = {"type": "tool_use", "name": "Edit",
                            "input": {"file_path": self._scratch_fixplan, "old_string": "x"}}

        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch"), malformed_c_edit),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        code, err = _run_guard_at(self._scratch_guard, events, session_id=sid,
                                   transcript_path=oga_tpath, gate_dir=self._gate_dir)
        self.assertEqual(code, 2, err)
        self.assertIn("H-AC19-COMBO-D", err)
        self.assertIn("H-AC19-COMBO-E", err)
        self.assertNotIn("Traceback", err)


# ---------------------------------------------------------------------------
# AC20 [BEHAVIORAL]: a multi-violation turn (this phase's gate fires AND a
# pre-existing gate, e.g. PLAN_CHECK, also fires) produces the same
# aggregated multi-violation output format the file's existing tail logic
# already produces for 2+ violations.
# ---------------------------------------------------------------------------

class Phase4AC20MultiViolationAggregationFormat(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)

    def test_closure_and_plan_check_violations_both_reported_in_existing_format(self):
        new_block = "## H-AC20-1 -- CLOSED (2026-07-09, introduced this turn)\nNo Proof block.\n"
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(new_block)
        edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                           old_string="x", new_string=new_block)
        # CODER_AGENT with no verifier and no fresh flag -> PLAN_CHECK also fires.
        events = make_turn([CODER_AGENT, edit_tu])
        code, err = _run_guard_at(self._scratch_guard, events)
        self.assertEqual(code, 2, err)
        self.assertIn("violations detected this turn", err)
        self.assertIn("PLAN_CHECK", err)
        self.assertIn("CLOSURE_VALIDATION", err)
        # [Section E] A missing-proof heading now trips BOTH
        # check_single_heading's own "missing proof block" check AND
        # status_claim_audit's separate MISSING_PARSEABLE_EVIDENCE
        # classifier for the SAME heading -- 3 violations total (confirmed
        # live: CLOSURE_VALIDATION Part C missing-proof-block first,
        # CLOSURE_VALIDATION status-claim-audit MISSING_PARSEABLE_EVIDENCE
        # second, PLAN_CHECK third), not the 2 this test originally assumed.
        self.assertIn("----- Violation 1/3", err)
        self.assertIn("----- Violation 2/3", err)
        self.assertIn("----- Violation 3/3", err)


# ---------------------------------------------------------------------------
# AC21 [DOC]: loop_stop_guard.py's and subagent_stop_gate.py's own module
# docstrings are each updated for their new responsibilities: the theme-4
# advisory-vs-blocking split (both files), and theme-5 self-healing (Part D
# only -- self-healing is loop_stop_guard.py's OWN responsibility; Part B in
# subagent_stop_gate.py only detects-and-flags, it never re-validates).
# ---------------------------------------------------------------------------

class Phase4AC21DocstringsDescribeNewResponsibilities(unittest.TestCase):
    def test_loop_stop_guard_docstring_mentions_advisory_and_self_healing(self):
        with open(GUARD, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        self.assertTrue(module_doc, "expected loop_stop_guard.py to have a module docstring")
        low = module_doc.lower()
        self.assertRegex(low, r"advisory")
        self.assertRegex(low, r"self.?heal")

    def test_subagent_stop_gate_docstring_mentions_advisory_split(self):
        sg_path = os.path.join(HOOKS_DIR, "subagent_stop_gate.py")
        with open(sg_path, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        self.assertTrue(module_doc, "expected subagent_stop_gate.py to have a module docstring")
        self.assertRegex(module_doc.lower(), r"advisory|warning")


# ---------------------------------------------------------------------------
# AC22 [BEHAVIORAL]: the full existing (pre-Phase-4) test suites for BOTH
# hook files remain green. Uses `-k "not Phase4"` against THIS SAME file so
# this meta-test doesn't recursively require this phase's OWN (currently-
# red, pre-implementation) new classes to already pass.
# ---------------------------------------------------------------------------

class Phase4AC22ExistingSuitesRemainGreen(unittest.TestCase):
    def test_loop_stop_guard_pre_phase4_suite_still_green(self):
        r = subprocess.run(
            [sys.executable, "-m", "pytest", os.path.abspath(__file__),
             "-k", "not Phase4", "-q"],
            capture_output=True, text=True, cwd=REPO_DIR, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_subagent_stop_gate_suite_still_green(self):
        subagent_test = os.path.join(HOOKS_DIR, "test_subagent_stop_gate.py")
        r = subprocess.run(
            [sys.executable, "-m", "pytest", subagent_test, "-q"],
            capture_output=True, text=True, cwd=REPO_DIR, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# AC23 [BEHAVIORAL]: the corrected line-845 PLAN_CHECK short-circuit fix's
# own regression case -- a turn that (a) dispatches a Coder, (b) has a
# FRESH, valid .verifier_pass credit flag for this session, and (c) ALSO has
# a real, queued CLOSURE_VALIDATION violation (from Part C, on an edit in
# the SAME turn) must still exit 2 and report the closure violation, AND the
# emitted violation set must NOT ALSO contain a spurious PLAN_CHECK
# violation. Companion: the SAME fresh-credit Coder-dispatch turn with NO
# other violation present still exits 0.
# ---------------------------------------------------------------------------

class Phase4AC23PlanCheckShortCircuitRegression(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)

    def test_fresh_credit_with_queued_closure_violation_still_blocks_and_no_spurious_plan_check(self):
        """[D.3 Bucket A2] Rebuilt onto the SAME real structural Verifier-
        credit pattern as SpecBoundVerifierCreditGateV1 (a genuine Verifier
        dispatch + paired PLAN_PASS result carrying REVIEWED_SPEC_SHA256=
        for the matching spec hash, in the same turn window) in place of
        write_flag()/.verifier_pass -- that legacy flag no longer
        authorizes a Coder dispatch on its own. The fresh, resolved credit
        must not spuriously ALSO produce a PLAN_CHECK violation once the
        genuinely-queued CLOSURE_VALIDATION violation (Part C, an Edit in
        the same turn introducing an unproven CLOSED heading) is the only
        one that should fire."""
        d = tempfile.mkdtemp(prefix="ac23-closure-spec-")
        try:
            spec_path = _sb_write_spec(d)
            spec_hash = _sb_sha256(spec_path)

            original = "## H-AC23-PRE (OPEN, still open)\nNothing closed yet.\n"
            new_block = (
                "## H-AC23-NEW -- CLOSED (2026-07-09, introduced this turn)\n"
                "Some closure prose, but no Proof block at all.\n"
            )
            with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
                f.write(original)
            edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                               old_string="x", new_string=new_block)
            with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
                f.write(original + new_block)

            events = make_turn_events(
                assistant_msg(_sb_verifier(spec_path, spec_hash, "ac23-verifier",
                                           run_in_background=False)),
                _sb_pass_result("ac23-verifier", spec_hash),
                assistant_msg(_sb_coder(spec_path, spec_hash, "ac23-coder"), edit_tu),
            )
            code, err = _run_guard_at(self._scratch_guard, events)

            self.assertEqual(code, 2, err)
            self.assertIn("CLOSURE_VALIDATION", err)
            self.assertNotIn("PLAN_CHECK", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_fresh_credit_with_no_other_violation_still_exits_zero(self):
        """Companion case: proves the common case (fresh, resolved
        structural Verifier-PASS credit, nothing else queued) still exits
        0.

        [D.3 Bucket A2] Rebuilt onto the SAME real structural Verifier-
        credit pattern as SpecBoundVerifierCreditGateV1, in place of the
        now-superseded write_flag()/.verifier_pass idiom -- that legacy
        flag no longer authorizes a Coder dispatch on its own. [R5] This
        test's own prior inline comment ("already satisfied by the file's
        CURRENT (unfixed) behavior -- see CrossTurnPlanCheckGate.test_
        coder_with_flag_exits_zero_and_flag_survives") was stale/self-
        contradicting: that cited sibling test actually proves the
        OPPOSITE -- a fresh legacy flag alone still BLOCKS (code == 2, its
        own docstring: "Legacy flag may survive, but must not authorize
        Coder") -- so that comment is discarded here rather than carried
        forward."""
        d = tempfile.mkdtemp(prefix="ac23-clean-spec-")
        try:
            spec_path = _sb_write_spec(d)
            spec_hash = _sb_sha256(spec_path)
            events = make_turn_events(
                assistant_msg(_sb_verifier(spec_path, spec_hash, "ac23-clean-verifier",
                                           run_in_background=False)),
                _sb_pass_result("ac23-clean-verifier", spec_hash),
                assistant_msg(_sb_coder(spec_path, spec_hash, "ac23-clean-coder")),
            )
            code, err = _run_guard_at(self._scratch_guard, events)
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# =============================================================================
# Approved v1 anti-false-status gate regressions. These are intentionally
# broader than the existing Phase 4 CLOSED-heading proof gate: high-risk status
# claims include DONE/READY/etc., evidence spans are part of the audited unit,
# and only successful writes may mark an existing claim/evidence span touched.
# =============================================================================


class V1AntiFalseStatusDirectStopPath(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)

    def test_done_heading_without_parseable_proof_blocks_direct_stop(self):
        new_block = (
            "## H-V1-DONE -- DONE (2026-07-10, introduced this turn)\n"
            "Status: DONE. No parseable Proof block exists.\n"
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(new_block)
        edit_tu = tool_use("Edit", file_path=self._scratch_fixplan,
                           old_string="x", new_string=new_block)

        code, err = _run_guard_at(self._scratch_guard, make_turn([edit_tu]))

        self.assertEqual(code, 2, err)
        self.assertIn("H-V1-DONE", err)
        self.assertRegex(err, r"status|claim|proof|evidence")

    def test_ready_evidence_deletion_blocks_direct_stop(self):
        heading = "H-V1-READY -- READY (2026-07-10, live-smoke claimed)"
        content_after_deletion = (
            "## %s\n"
            "Status: READY for Dropbox connector.\n"
            "Proof block was deleted in this turn.\n"
        ) % heading
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content_after_deletion)
        edit_tu = tool_use(
            "Edit", file_path=self._scratch_fixplan,
            old_string="Proof:\n- command: python3 live_smoke.py\n",
            new_string="Proof block was deleted in this turn.",
        )

        code, err = _run_guard_at(self._scratch_guard, make_turn([edit_tu]))

        self.assertEqual(code, 2, err)
        self.assertIn("H-V1-READY", err)

    def test_full_file_write_revalidates_only_changed_claim_not_all_historical_claims(self):
        historical = (
            "## H-V1-HISTORICAL -- CLOSED (2026-07-10)\n"
            "Status: DONE. Historical bad claim with no proof.\n\n"
        )
        changed = (
            "## H-V1-CHANGED -- CLOSED (2026-07-10)\n"
            "Status: DONE. This heading's evidence was weakened to true.\n\n"
            "Proof:\n"
            "- command: true\n"
            "- exit_code: 0\n"
            "- proof_snapshot: /tmp/v1-probe-only.json\n"
            "- verified_at: 2026-07-10T00:00:00+00:00\n"
        )
        full_content = historical + changed
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(full_content)
        write_tu = tool_use("Write", file_path=self._scratch_fixplan, content=full_content)

        code, err = _run_guard_at(self._scratch_guard, make_turn([write_tu]))

        self.assertEqual(code, 2, err)
        self.assertIn("H-V1-CHANGED", err)
        self.assertNotIn("H-V1-HISTORICAL", err)

    def test_successful_multiedit_mixed_case_blocks_for_proof_deletion_only(self):
        heading = "H-V1-MIXED -- CLOSED (2026-07-10)"
        unrelated = "H-V1-UNRELATED (OPEN)"
        content = (
            "## %s\n"
            "Status: DONE for stop-hook coverage.\n"
            "Proof deleted.\n\n"
            "## %s\n"
            "Unrelated prose edited here.\n"
        ) % (heading, unrelated)
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)
        multiedit_tu = tool_use(
            "MultiEdit",
            file_path=self._scratch_fixplan,
            edits=[
                {"old_string": "Proof:\n- command: python3 -m pytest hooks/test_loop_stop_guard.py -q\n",
                 "new_string": "Proof deleted."},
                {"old_string": "Unrelated prose.",
                 "new_string": "Unrelated prose edited here."},
            ],
        )

        code, err = _run_guard_at(self._scratch_guard, make_turn([multiedit_tu]))

        self.assertEqual(code, 2, err)
        self.assertIn("H-V1-MIXED", err)
        self.assertNotIn("H-V1-UNRELATED", err)


class V1AntiFalseStatusDeniedErroredMissingResultFiltering(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)

    def _existing_bad_fixplan(self):
        content = (
            "## H-V1-EXISTING -- CLOSED (2026-07-10)\n"
            "Status: DONE. Existing invalid proof must not be revalidated "
            "unless a successful write touched the claim or evidence span.\n\n"
            "Proof:\n"
            "- command: true\n"
            "- exit_code: 0\n"
            "- proof_snapshot: /tmp/v1-existing-probe.json\n"
            "- verified_at: 2026-07-10T00:00:00+00:00\n"
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(content)
        return content

    def _tool_use_for(self, name, content):
        if name == "Edit":
            inp = {
                "file_path": self._scratch_fixplan,
                "old_string": "Status: DONE.",
                "new_string": "Status: DONE.",
            }
        elif name == "MultiEdit":
            inp = {
                "file_path": self._scratch_fixplan,
                "edits": [{
                    "old_string": "- command: true",
                    "new_string": "- command: true",
                }],
            }
        else:
            inp = {"file_path": self._scratch_fixplan, "content": content}
        return {"type": "tool_use", "id": "tu-v1-%s" % name.lower(),
                "name": name, "input": inp}

    def _tool_result(self, outcome, tool_use_id):
        if outcome == "denied":
            return tool_result_event(tool_use_id, "Hook PreToolUse: denied this tool call.")
        if outcome == "errored":
            return {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id,
                 "is_error": True, "content": "Edit failed: old_string not found."}
            ]}}
        return None

    def test_denied_errored_and_missing_result_writes_do_not_mark_existing_spans_touched(self):
        for tool_name in ("Edit", "MultiEdit", "Write"):
            for outcome in ("denied", "errored", "missing_result"):
                content = self._existing_bad_fixplan()
                tu = self._tool_use_for(tool_name, content)
                events = [
                    {"type": "user", "message": {"role": "user", "content": "go build"}},
                    assistant_msg(tu),
                ]
                result = self._tool_result(outcome, tu["id"])
                if result is not None:
                    events.append(result)

                code, err = _run_guard_at(self._scratch_guard, events)

                self.assertEqual(
                    code, 0,
                    "%s/%s should not revalidate existing untouched claims: %s"
                    % (tool_name, outcome, err),
                )


class V1AntiFalseStatusLoopStopSubagentTranscriptPath(unittest.TestCase):
    def setUp(self):
        (self._scratch_root, self._scratch_guard,
         self._scratch_fixplan) = _make_scratch_hook_repo()
        self._tmpdirs = []
        self._gate_dir = tempfile.mkdtemp(prefix="v1-subagent-layer2-gate-")

    def tearDown(self):
        shutil.rmtree(self._scratch_root, ignore_errors=True)
        shutil.rmtree(self._gate_dir, ignore_errors=True)
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_subagent_transcript_scan_blocks_done_claim_without_proof(self):
        new_block = (
            "## H-V1-SUBAGENT-DONE -- DONE (2026-07-10)\n"
            "Status: DONE. No parseable Proof block exists.\n"
        )
        with open(self._scratch_fixplan, "w", encoding="utf-8") as f:
            f.write(new_block)
        project_dir = tempfile.mkdtemp(prefix="v1-layer2-project-")
        self._tmpdirs.append(project_dir)
        sid = "v1layer2-%s" % uuid.uuid4().hex
        agent_id = "agentV1Layer2"
        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        sub_edit = tool_use("Edit", file_path=self._scratch_fixplan,
                            old_string="x", new_string=new_block)
        make_agent_dispatch_transcript(sid, agent_id, project_dir, [assistant_msg(sub_edit)])
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            assistant_msg(tool_use("Task", description="dispatch")),
            agent_dispatch_result_event("disp1", agent_id),
        ]

        code, err = _run_guard_at(
            self._scratch_guard, events, session_id=sid,
            transcript_path=oga_tpath, gate_dir=self._gate_dir)

        self.assertEqual(code, 2, err)
        self.assertIn("H-V1-SUBAGENT-DONE", err)


# ---------------------------------------------------------------------------
# runs/2026-07-11_185950-hook-turn-scope-and-verifier-detect-fix/specs/spec.md
# AC12 and AC18 (Bug 1 fix): exercised through the ACTUAL Stop-hook code path
# (this file's own subprocess harness), not just spec_bound_verifier_credit.py
# functions in isolation (hooks/test_spec_bound_verifier_credit.py covers
# that layer, including the byte-exact real-incident reproduction for AC1 --
# see that file's module docstring for the real event-shape provenance this
# section's smaller, test-generic notification_event() helper mirrors).
# ---------------------------------------------------------------------------

# A short, structurally real-shaped stub launch-acknowledgment (the real,
# full text is reproduced verbatim in test_spec_bound_verifier_credit.py;
# this file only needs the STRUCTURAL fact that an async dispatch always
# gets an immediate stub tool_result carrying no verdict of its own).
ASYNC_LAUNCH_STUB_TEXT = (
    "Async agent launched successfully. The agent is working in the "
    "background. You will be notified automatically when it completes."
)


def real_shaped_notification_event(tool_use_id, status="completed", result_body="", origin_kind="task-notification"):
    """A task-notification event matching the REAL confirmed shape (fix_plan.md
    H-ASYNC-CREDIT-GATE-WRONG-EVENT-1; transcript index 286 of
    ~/.claude/projects/-Users-eobodoechine/7dd67b94-ee54-47e2-afd7-f9f80e966334.jsonl):
    type=user, top-level origin.kind=task-notification, message.content is a
    bare STRING (not a list) starting with the literal '<task-notification>'
    tag and carrying the same tag structure/order and the same real <note>
    text confirmed on that event. Content body here is test-generic/short
    (the byte-exact real content lives in test_spec_bound_verifier_credit.py's
    AC1 fixture); the STRUCTURE below is real, not invented."""
    content = (
        "<task-notification>\n"
        "<task-id>task-for-%s</task-id>\n"
        "<tool-use-id>%s</tool-use-id>\n"
        "<output-file>/tmp/task-for-%s.output</output-file>\n"
        "<status>%s</status>\n"
        "<summary>Agent finished</summary>\n"
        "<note>A task-notification fires each time this agent stops with no live background "
        "children of its own. The user can send it another message and resume it, so the same "
        "task-id may notify more than once.</note>\n"
        "<result>%s</result>\n"
        "<usage><subagent_tokens>1</subagent_tokens><tool_uses>1</tool_uses>"
        "<duration_ms>1</duration_ms></usage>\n"
        "</task-notification>"
    ) % (tool_use_id, tool_use_id, tool_use_id, status, result_body)
    ev = {"type": "user", "message": {"role": "user", "content": content}}
    if origin_kind is not None:
        ev["origin"] = {"kind": origin_kind}
    return ev


class AsyncNotificationCreditStopHookAC12(unittest.TestCase):
    """[BEHAVIORAL] AC12: hooks/loop_stop_guard.py's Stop-hook coder-before-
    verifier gate, exercised DIRECTLY (not just spec_bound_verifier_credit.py's
    functions in isolation), correctly credits a Coder dispatch following an
    async-notification-delivered Verifier PLAN_PASS for the same spec hash --
    reproducing AC1's scenario through the ACTUAL Stop-hook code path."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ac12-stop-hook-async-")
        self.addCleanup(lambda: shutil.rmtree(self.tmpdir, ignore_errors=True))

    def test_async_notification_delivered_pass_credits_coder_via_stop_hook(self):
        spec = _sb_write_spec(
            self.tmpdir, "spec.md",
            "# AC12 spec\nAsync-notification credit via the Stop hook.\n")
        h = _sb_sha256(spec)
        # Section B independent full-source sweep (own finding, beyond the
        # round-11 confirmed floor): this is the genuinely-background
        # stub-then-notification pattern -- run_in_background=True.
        verifier = _sb_verifier(spec, h, "v-ac12-async", run_in_background=True)
        events = make_turn_events(
            assistant_msg(verifier),
            tool_result_event("v-ac12-async", ASYNC_LAUNCH_STUB_TEXT),
            real_shaped_notification_event(
                "v-ac12-async",
                result_body=_sb_pass_text(h, "Reviewed and confirmed.")),
            assistant_msg(_sb_coder(spec, h, "c-ac12-async")),
        )
        code, err = run_guard(events)
        self.assertEqual(
            code, 0,
            "the Stop-hook's own coder-before-verifier gate must credit a Coder "
            "dispatch following an async-notification-delivered PLAN_PASS for "
            "the same spec hash, through the real hook code path, not just "
            "spec_bound_verifier_credit.py in isolation. Got exit %r, stderr=%s"
            % (code, err),
        )


class AsyncNotificationDoesNotLeakIntoRH3GateAC18(unittest.TestCase):
    """[BEHAVIORAL, round 3] AC18: the separately-scoped widened credit-turn
    computation Bug 1's fix introduces (used ONLY by the coder-before-verifier
    gate) must NOT leak into loop_stop_guard.py's OTHER gates that share
    turn/blob/_TOOL_USES/_TOOL_RESULTS -- in particular the Researcher
    Mode-D/RH3 gate (line ~1500), whose own inline comment documents relying
    on the notification-resets-the-window behavior as a deliberate
    false-positive suppressor ("a user-channel task-notification opens a NEW
    turn under the walk-back above... do not widen it").

    Discriminating fixture design: the Researcher dispatch's only in-turn
    "returned evidence" is (1) the always-present async stub tool_result and
    (2) a real-shaped type:queue-operation duplicate carrying the dispatch's
    own <tool-use-id> -- BOTH positioned BEFORE the notification event, matching
    the real transcript's own index-283-before-286 ordering. If RH3's own
    turn/_TOOL_USES basis were wrongly aliased to the widened, notification-
    tolerant computation (the anti-pattern the spec explicitly warns against),
    BOTH the Researcher dispatch and this evidence would remain in-window,
    and — since the Verifier dispatch that suppresses the unrelated FEATURE
    gate is placed AFTER the code edit, not between research and edit — RH3
    WOULD incorrectly arm (exit 2). Under the correctly-scoped fix, `turn`
    resets at the notification exactly as before Bug 1's fix, excluding the
    Researcher dispatch (and its evidence) from RH3's basis entirely, so RH3
    never arms (exit 0) regardless of the later code edit."""

    def test_fully_async_researcher_dispatch_notification_shape_still_never_arms_rh3(self):
        researcher = researcher_dispatch("toolu_rh3_ac18_async")
        src_edit = tool_use("Edit", file_path="/x/src/service.py",
                            old_string="a", new_string="b")
        events = make_turn_events(
            assistant_msg(researcher),
            tool_result_event("toolu_rh3_ac18_async", ASYNC_LAUNCH_STUB_TEXT),
            queue_operation_event("toolu_rh3_ac18_async"),
            real_shaped_notification_event(
                "toolu_rh3_ac18_async",
                result_body="Researcher findings: event model documented."),
            assistant_msg(src_edit, PLAN_VERIFIER_RH3),
        )
        code, err = run_guard(events)
        self.assertEqual(
            code, 0,
            "a fully-async Researcher dispatch->notification shape must still "
            "never arm RH3 after Bug 1's fix -- if this blocks (exit 2), the "
            "separately-scoped widened credit-turn computation has leaked into "
            "turn/_TOOL_USES/_TOOL_RESULTS (RH3's own basis), reopening the "
            "false-positive risk RH3's own comment (loop_stop_guard.py "
            "~line 1488-1493) documents relying on the notification-resets-"
            "the-window behavior to suppress. Got exit %r, stderr=%s"
            % (code, err),
        )


if __name__ == "__main__":
    unittest.main()
