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
import difflib
import glob
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

    # [BEHAVIORAL] AC-2: Verifier appears before Coder → allowed.
    def test_verifier_before_coder_passes(self):
        code, _ = run_guard(make_turn([PLAN_VERIFIER, CODER_AGENT]))
        self.assertEqual(code, 0)

    # [BEHAVIORAL] Rewritten per plan_check_spec.md AC2 (H-LT7a): the within-turn
    # check is now order-insensitive -- a paired same-turn dispatch with Coder
    # listed before the plan-check Verifier must PASS as long as a Verifier
    # dispatch is present anywhere in the turn. Superseded the old order-
    # sensitive assertion (was: blocks). The no-verifier-anywhere case still
    # blocks and is covered separately (see PlanCheckOrderInsensitivity AC5-case-4).
    def test_coder_before_verifier_blocks(self):
        code, err = run_guard(make_turn([CODER_AGENT, PLAN_VERIFIER]))
        self.assertEqual(code, 0, err)

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

    # [BEHAVIORAL] AC-H3: plan-check Verifier (with Coder prose in prompt) followed by
    # a real Coder dispatch → both in same turn → should pass (ordering is correct).
    def test_plan_check_verifier_then_coder_passes(self):
        code, err = run_guard(make_turn([self.GUARD_FP, CODER_AGENT]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] Rewritten per plan_check_spec.md AC2 (H-LT7a): order-insensitive
    # within-turn scan means real Coder-before-plan-check-Verifier (with a genuine
    # _VERIFIER_DETECT match) now PASSES too -- same pattern as
    # test_coder_before_verifier_blocks above. Superseded the old "still blocks"
    # assertion; renamed intent preserved via docstring/comment, name kept so the
    # regression class stays discoverable in this file.
    def test_coder_before_plan_check_verifier_still_blocks(self):
        code, err = run_guard(make_turn([CODER_AGENT, self.GUARD_FP]))
        self.assertEqual(code, 0, err)

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
    """Gate: when a flag file from a previous SubagentStop exists, the plan-check
    violation is waived and all flags for that session are consumed on exit 0.

    Covers AC-4, AC-5, AC-6, AC-9 (cross-turn stop_hook_active variant), AC-13.
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

    # [BEHAVIORAL] Rewritten per plan_check_spec.md AC1 (H-GUARD-3/H-LT7b): a fresh
    # flag now licenses the dispatch via a READ-ONLY freshness check and is NOT
    # deleted -- non-consuming credit lets a micro-step run reuse one PLAN_PASS
    # across many Coder-dispatch turns within the TTL window. Superseded the old
    # delete-on-consume assertion; renamed to drop "_and_consumes_flag" per spec.
    def test_coder_with_flag_exits_zero_and_flag_survives(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        flag = write_flag(sid, "verifier-sub-1")
        code, _ = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 0)
        # Flag must survive (non-consuming credit).
        self.assertTrue(os.path.exists(flag), "Flag was deleted; AC1 requires non-consuming credit")

    # [BEHAVIORAL] Rewritten per plan_check_spec.md AC1 (H-LT7b): multiple flags
    # for the same session must ALL survive a fresh-flag pass -- the old
    # delete-all-on-consume behavior broke micro-step continuation turns that
    # rely on the flag(s) persisting across many turns. Superseded the old
    # all-consumed assertion.
    def test_multiple_flags_all_consumed(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        flag1 = write_flag(sid, "verifier-a")
        flag2 = write_flag(sid, "verifier-b")
        code, _ = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(flag1))
        self.assertTrue(os.path.exists(flag2))

    # [BEHAVIORAL] AC-5: Coder dispatch, no flag exists → exit 2 (existing gate still fires).
    def test_coder_without_flag_exits_two(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 2, err)

    # [BEHAVIORAL] Rewritten per plan_check_spec.md AC1 (H-GUARD-3/H-GUARD-MICROSTEP):
    # non-consuming credit means a fresh flag licenses EVERY subsequent Coder
    # dispatch in the session within the TTL window, not just the first -- this
    # is exactly what a micro-step run (one Coder dispatch per step, many turns,
    # one plan-check) needs. Superseded the old consume-then-block assertion.
    def test_flag_consumed_second_dispatch_blocks(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        write_flag(sid, "verifier-once")
        # First Coder dispatch: flag present → should pass.
        code1, _ = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code1, 0)
        # Second Coder dispatch: flag still fresh (non-consuming) → should ALSO pass.
        code2, err2 = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code2, 0, f"Expected exit 0 on second dispatch (non-consuming credit); got {code2}. stderr: {err2}")

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
    """New cases for plan_check_spec.md AC1/AC2 (AC5 cases 1-4). Uses the same
    GATE_DIR temp-dir pattern and write_flag/run_guard_with_session helpers as
    CrossTurnPlanCheckGate above."""

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

    # [BEHAVIORAL] AC5 case 1: violation-shaped turn + fresh flag → exit 0 AND
    # the flag file still exists afterward (non-consuming credit, AC1).
    def test_fresh_flag_passes_and_flag_survives(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        flag = write_flag(sid, "verifier-fresh")
        # Violation-shaped turn: Coder listed with no plan-check Verifier at all.
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(flag), "Fresh flag must survive a non-consuming pass")

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

    # [BEHAVIORAL] AC5 case 3: paired same-turn dispatch with the Coder tool_use
    # listed BEFORE the plan-check Verifier tool_use → exit 0 with no flag
    # needed (AC2 order-insensitive scan). Fixtures use REAL orchestrator
    # dispatch labels: "Coder for <task>" and a "plan-check Verifier" prefix.
    def test_coder_before_verifier_same_turn_no_flag_needed_passes(self):
        coder = tool_use("Agent", description="Coder for the AC2 order-insensitivity fix",
                          prompt="# Role: Coder\nImplement per spec...")
        plan_check_verifier = tool_use(
            "Agent", description="plan-check Verifier for the AC2 order-insensitivity fix",
            prompt="You are an independent verifier reviewing the spec...")
        code, err = run_guard(make_turn([coder, plan_check_verifier]))
        self.assertEqual(code, 0, err)

    # [BEHAVIORAL] AC5 case 4 (regression): violation-shaped turn + no flags at
    # all → exit 2. (Duplicates test_coder_without_flag_exits_two's intent with
    # a session-scoped assertion for completeness alongside the new TTL cases.)
    def test_violation_shaped_turn_no_flags_still_blocks(self):
        sid = f"test-session-{uuid.uuid4()}"
        self._sessions_to_clean.append(sid)
        code, err = run_guard_with_session(make_turn([CODER_AGENT]), session_id=sid)
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
        code, err = run_guard(make_turn([RESEARCHER_AGENT, PLAN_VERIFIER_AFTER, CODER_AGENT]))
        self.assertEqual(code, 0, err)

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
        sid = "rh7-[meta]-%s" % uuid.uuid4().hex
        flag = write_flag(sid, "verifier")
        try:
            code, err = run_guard_with_session(make_turn([CODER_AGENT]),
                                               session_id=sid)
            self.assertEqual(code, 0, err)
        finally:
            try:
                os.remove(flag)
            except OSError:
                pass

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


if __name__ == "__main__":
    unittest.main()
