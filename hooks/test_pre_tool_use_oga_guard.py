#!/usr/bin/env python3
"""Regression tests for pre_tool_use_oga_guard.py (H-GUARD-SUBAGENT fix).

The guard must arm ONLY when the loop-team orchestrator's playbook is actually
loaded in the transcript -- NOT when the injected available-skills list merely
mentions the skill (which happens in EVERY session, including Coder
sub-agents; that false-arm produced runaway delegation chains).

Fixture-tautology guard: the "armed" fixtures embed the head of the REAL
orchestrator.md read from disk, so the tests prove the detector matches what
the orchestrator actually injects -- not strings crafted to match the regex.
All marker phrases are built dynamically so THIS file can never arm the guard
in a session that reads it.

Run: python3 -m pytest hooks/test_pre_tool_use_oga_guard.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pre_tool_use_oga_guard.py")
ORCH = os.path.expanduser("~/Claude/loop/loop-team/orchestrator.md")

# Built dynamically -- never write these as contiguous literals anywhere.
M_OGA = "You are " + "**Oga**"
M_PLAYBOOK = "Orchestrator " + "Playbook"

# Real wording of the injected available-skills list (the false-arm vector
# recorded in fix_plan.md H-GUARD-SUBAGENT): mentions the skill + 'oga build'.
SKILLS_LIST_TEXT = (
    "The following skills are available for use with the Skill tool:\n"
    "- anthropic-skills:loop-team: Orchestrates a structured build team "
    "(Oga -> Test-writer -> Coder -> Verifier -> Researcher)... Also triggers on "
    "'loop-team', 'run the loop', 'oga build', 'dispatch the team'."
)


def _user_event(text, timestamp=None):
    e = {"role": "user", "content": [{"type": "text", "text": text}]}
    if timestamp is not None:
        e["timestamp"] = timestamp
    return e


def _assistant_tool_use(name, tool_input, tool_use_id=None, timestamp=None):
    e = {"role": "assistant",
         "content": [{"type": "tool_use", "name": name, "input": tool_input,
                      "id": tool_use_id or (name.lower() + "-toolu-1")}]}
    if timestamp is not None:
        e["timestamp"] = timestamp
    return e


def _notification_event(tool_use_id, status="completed", timestamp=None):
    """A role:user task-notification event embedding <tool-use-id>."""
    text = (f"<task-notification status=\"{status}\">"
            f"<tool-use-id>{tool_use_id}</tool-use-id></task-notification>")
    e = {"role": "user", "content": [{"type": "text", "text": text}]}
    if timestamp is not None:
        e["timestamp"] = timestamp
    return e


def _queue_operation_event(tool_use_id, timestamp=None):
    """A type:queue-operation event embedding <tool-use-id> (the channel-b
    completion path -- 5/47 real-corpus completions surfaced ONLY here)."""
    e = {"type": "queue-operation", "op": "retire",
         "payload": f"<tool-use-id>{tool_use_id}</tool-use-id>"}
    if timestamp is not None:
        e["timestamp"] = timestamp
    return e


def _stop_hook_feedback_event(timestamp=None):
    """A text-only boundary event with no tool-use-id -- the kind of
    interleaved turn boundary that broke the old turn-lookback approach."""
    e = {"role": "user", "content": [{"type": "text", "text": "[stop-hook feedback] continue"}]}
    if timestamp is not None:
        e["timestamp"] = timestamp
    return e


def _run_hook(events, tool_name="Edit", file_path="/tmp/x/impl.py"):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
        transcript = f.name
    try:
        data = json.dumps({
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path},
            "transcript_path": transcript,
        })
        proc = subprocess.run(
            [sys.executable, HOOK], input=data, capture_output=True,
            text=True, timeout=30,
        )
        return proc
    finally:
        os.unlink(transcript)


def _denied(proc):
    if not proc.stdout.strip():
        return False
    out = json.loads(proc.stdout)
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def _deny_reason(proc):
    """Return the permissionDecisionReason text, or '' if not denied/no output."""
    if not proc.stdout.strip():
        return ""
    out = json.loads(proc.stdout)
    return out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "") or ""


def _orchestrator_head():
    """Head of the REAL orchestrator.md -- what STEP 0 injects into an Oga session."""
    if not os.path.exists(ORCH):
        pytest.skip("orchestrator.md not found at documented root path")
    with open(ORCH, encoding="utf-8") as f:
        head = f.read(2000)
    # Sanity: the real playbook must still carry both detection markers.
    assert M_OGA in head, "orchestrator.md no longer contains the Oga marker"
    assert M_PLAYBOOK in head, "orchestrator.md no longer contains the Playbook marker"
    return head


class TestSkillsListDoesNotArm:
    def test_skills_list_only_transcript_allows_code_edit(self):
        """[BEHAVIORAL] The always-injected skills list (mentions oga/loop-team)
        must NOT arm the guard -- the H-GUARD-SUBAGENT false-arm vector."""
        proc = _run_hook([_user_event(SKILLS_LIST_TEXT)])
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout


class TestOrchestratorSessionArms:
    def test_real_playbook_content_blocks_direct_code_edit(self):
        """[BEHAVIORAL] A transcript carrying the REAL orchestrator.md head
        (what an Oga session actually contains) + a direct code Edit with no
        Agent dispatch this turn -> deny."""
        proc = _run_hook([_user_event(_orchestrator_head())])
        assert proc.returncode == 0
        assert _denied(proc), "guard failed to arm on real orchestrator.md content"

    def test_agent_dispatch_this_turn_allows_edit(self):
        """[BEHAVIORAL] Same armed session, but an Agent tool_use happened this
        turn (Oga dispatched a sub-agent) -> the Write/Edit is allowed."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder for the fix",
                                          "prompt": "implement per spec"}),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout

    def test_non_code_file_is_never_gated(self):
        """[BEHAVIORAL] Armed session, but the edit targets a non-code file
        (run log / notes) -> allowed without an Agent dispatch."""
        proc = _run_hook([_user_event(_orchestrator_head())],
                         file_path="/tmp/x/run_log_notes.rst")
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout


class TestNoLiteralMarkersInHooks:
    def test_hooks_dir_contains_no_contiguous_marker_literals(self):
        """[BEHAVIORAL] Reading any hooks/ file (guards or tests) must never arm
        ANY detector: no file may contain any detection marker — the oga-guard
        pair OR the verifier-hygiene set — as a contiguous literal. (The hygiene
        set is rebuilt here non-contiguously; it must match loop_stop_guard's
        _hyg_markers, whose presence the companion test asserts.)"""
        hooks_dir = os.path.dirname(HOOK)
        hyg = (
            "last " + "verdict", "tests " + "passed", "tests are " + "passing",
            "all " + "green", "suite: " + "green", "harness is " + "green",
            "decision " + "log", "spec " + "interpretation:",
            "alternatives " + "rejected",
        )
        needles = (M_OGA.lower(), M_PLAYBOOK.lower()) + hyg
        for name in os.listdir(hooks_dir):
            path = os.path.join(hooks_dir, name)
            if not os.path.isfile(path) or name.endswith(".pyc"):
                continue
            try:
                blob = open(path, encoding="utf-8", errors="ignore").read().lower()
            except OSError:
                continue
            for needle in needles:
                assert needle not in blob, f"{name} contains contiguous marker {needle!r}"


    def test_hyg_marker_source_still_exists(self):
        """Companion to the sweep: if _hyg_markers is renamed/moved in
        loop_stop_guard, this fails visibly so the duplicated sweep list above
        gets re-synced instead of silently drifting."""
        guard_src = open(os.path.join(os.path.dirname(HOOK),
                                      "loop_stop_guard.py"), encoding="utf-8").read()
        assert "def _hyg_markers" in guard_src


class TestInFlightSubAgentDetection:
    """H-LT6: replaces turn-lookback with in-flight retirement tracking.
    GAC1-GAC4c per runs/2026-07-01_hlt6-oga-guard-subagent/specs/guard_fix_spec.md."""

    def test_gac1_cold_oga_edit_still_blocked(self):
        """[BEHAVIORAL][GAC1] Armed transcript, all past Agent tool_use ids have
        matching task-notifications (nothing in flight) -> deny (core purpose)."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A"),
            _notification_event("toolu_A", status="completed"),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout

    def test_gac2_fresh_dispatch_allowed(self):
        """[BEHAVIORAL][GAC2] Agent tool_use in the current turn, no notification
        for it yet -> allow (existing behavior preserved)."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder for the fix",
                                          "prompt": "implement per spec"},
                                 tool_use_id="toolu_fresh"),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout

    def test_gac3_burst_of_interleaved_boundaries_still_allows(self):
        """[BEHAVIORAL][GAC3] Agent A dispatched, then >=5 interleaved boundaries
        (notifications for OTHER completed agents across BOTH channels, a
        stop-hook-feedback-style text event, and a non-Agent notification) with
        A still unretired -> allow. This is the exact race the old turn-lookback
        approach lost: any one of these boundary events used to open a fresh
        Agent-less turn and re-block A mid-flight."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A"),
            # >=5 interleaved boundaries, none of which retire A:
            _notification_event("toolu_B", status="completed"),        # channel a
            _queue_operation_event("toolu_C"),                          # channel b
            _stop_hook_feedback_event(),                                 # text-only boundary
            _notification_event("toolu_D", status="killed"),            # channel a, killed
            _notification_event("bash_monitor_1", status="completed"),  # non-Agent id
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout

    def test_gac4_user_channel_completion_retires_allowance(self):
        """[BEHAVIORAL][GAC4] After A's user-channel task-notification appears
        (and nothing else in flight) -> deny."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A"),
            _notification_event("toolu_A", status="completed"),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout

    def test_gac4_killed_notification_also_retires(self):
        """[BEHAVIORAL][GAC4] A `status: killed` notification retires the
        allowance the same way a completion does."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A"),
            _notification_event("toolu_A", status="killed"),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout

    def test_gac4b_staleness_cap_via_timestamp(self):
        """[BEHAVIORAL][GAC4b] A dispatch with no notification but older than
        the 60-minute cap (via timestamp) -> deny."""
        stale_ts = time.time() - (2 * 60 * 60)  # 2 hours ago
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A", timestamp=stale_ts),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout

    def test_gac4b_staleness_cap_via_event_count_fallback(self):
        """[BEHAVIORAL][GAC4b] No timestamps anywhere -> falls back to the
        400-event window; a dispatch buried more than 400 events back with no
        retirement -> deny."""
        events = [_user_event(_orchestrator_head())]
        events.append(_assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                           tool_use_id="toolu_A"))
        # Pad with >400 plain events and no timestamps anywhere.
        for i in range(410):
            events.append(_user_event(f"padding event {i}"))
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout

    def test_gac4b_within_staleness_cap_still_allowed(self):
        """[BEHAVIORAL][GAC4b] Sanity inverse: a recent, unretired dispatch
        (well within the cap) -> allow."""
        recent_ts = time.time() - 60  # 1 minute ago
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A", timestamp=recent_ts),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout

    def test_gac4c_queue_operation_only_retirement(self):
        """[BEHAVIORAL][GAC4c] Agent A's completion appears ONLY as a
        type:queue-operation event embedding A's <tool-use-id> (no user-role
        echo, matching the 5/47 real-corpus pattern) -> deny."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A"),
            _queue_operation_event("toolu_A"),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout

    def test_gac4c_queue_operation_non_agent_id_does_not_retire(self):
        """[BEHAVIORAL][GAC4c] Inverse filter test: a queue-operation event
        referencing a NON-Agent id (background-Bash) while A is unretired ->
        still allow."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder A", "prompt": "..."},
                                 tool_use_id="toolu_A"),
            _queue_operation_event("bash_monitor_xyz"),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout


class TestDenyMessageMisfireGuidance:
    """New cases for plan_check_spec.md AC4 (AC5 case 7): the deny message must
    contain the sub-agent-misfire guidance (fix_plan.md H-GUARD-4 / H-LT6 --
    note the misfire and complete the assigned work with permitted tools) and
    the no-further-dispatch instruction (do NOT dispatch another sub-agent in
    response). No logic change to the allow/deny decision -- the allow path
    (in-flight ids present) must remain untouched."""

    def test_deny_message_contains_misfire_and_no_further_dispatch_guidance(self):
        """[BEHAVIORAL] Cold armed session, no in-flight dispatch -> denied, and
        the deny message must guide a MISFIRED sub-agent: (a) reference the
        misfire/H-GUARD-4/H-LT6 possibility, and (b) instruct it not to dispatch
        another sub-agent in response."""
        proc = _run_hook([_user_event(_orchestrator_head())])
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout
        reason = _deny_reason(proc).lower()
        # (a) misfire guidance: the blocked actor may itself be a dispatched
        # sub-agent, and this is a known misfire class.
        assert "misfire" in reason, reason
        assert ("h-guard-4" in reason) or ("h-lt6" in reason), reason
        # (b) no-further-dispatch instruction: must not tell the (possibly
        # already-a-subagent) actor to dispatch yet another sub-agent -- the
        # historical failure mode this AC exists to prevent (runaway chains).
        assert "do not dispatch" in reason or "don't dispatch" in reason, reason
        # (c) still states the underlying purpose (dispatch a Coder rather than
        # edit code inline) for the normal Oga-direct-edit case.
        assert "coder" in reason, reason
        # (d) honest about advisory scope, not a security boundary.
        assert "advisory" in reason, reason

    def test_allow_path_with_in_flight_dispatch_unchanged(self):
        """[BEHAVIORAL] Sanity companion: the allow path (Agent dispatch this
        turn, in-flight ids present) is untouched by the AC4 message rewrite --
        still returns allow (no deny payload) exactly as before."""
        events = [
            _user_event(_orchestrator_head()),
            _assistant_tool_use("Agent", {"description": "Coder for the fix",
                                          "prompt": "implement per spec"}),
        ]
        proc = _run_hook(events)
        assert proc.returncode == 0
        assert not _denied(proc), proc.stdout


# ---------------------------------------------------------------------------
# AC-RH5 (residual_holes_spec.md, runs/2026-07-02_003000-stopguard-residual-
# holes): caller-identity evidence capture in the debug log. The allow/deny
# outcome must stay byte-identical; only the debug rows gain fields.
# (Wording note: this file must never spell any hygiene-marker phrase
# contiguously -- see TestNoLiteralMarkersInHooks above.)
# ---------------------------------------------------------------------------

def _run_hook_with_payload(events, payload_extras=None, env_extras=None,
                           tool_name="Edit", file_path="/tmp/x/impl.py"):
    """Like _run_hook, but (a) allows extra top-level stdin payload keys,
    (b) allows env overrides (LOOP_GATE_DIR isolation for debug-log reads),
    and (c) also returns the transcript path so the caller can assert
    basename-only logging. The transcript file itself is deleted before
    returning -- only its (former) path/basename is needed."""
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
        transcript = f.name
    try:
        payload = {
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path},
            "transcript_path": transcript,
        }
        if payload_extras:
            payload.update(payload_extras)
        env = os.environ.copy()
        if env_extras:
            env.update(env_extras)
        proc = subprocess.run(
            [sys.executable, HOOK], input=json.dumps(payload),
            capture_output=True, text=True, timeout=30, env=env,
        )
        return proc, transcript
    finally:
        os.unlink(transcript)


def _last_debug_row_raw(gate_dir):
    path = os.path.join(gate_dir, "oga_guard_debug.jsonl")
    assert os.path.exists(path), "guard wrote no debug log under %s" % gate_dir
    lines = [l for l in open(path, encoding="utf-8").read().splitlines() if l.strip()]
    assert lines, "debug log is empty"
    return lines[-1]


class TestCallerIdentityEvidenceRH5:
    """AC-RH5: debug rows gain session_id, transcript_basename (basename only,
    no home paths in the log), and payload_keys (sorted top-level stdin keys,
    values redacted). The allow/deny decision itself is UNCHANGED."""

    def test_rh5_debug_row_contains_caller_identity_fields(self):
        """[BEHAVIORAL] Cold armed session with a full stdin payload -> the
        appended debug row carries the three new fields with correct values,
        and leaks neither the transcript's directory nor any payload VALUE."""
        gate_dir = tempfile.mkdtemp(prefix="rh5-gate-")
        proc, transcript = _run_hook_with_payload(
            [_user_event(_orchestrator_head())],
            payload_extras={"session_id": "rh5-session-abc123",
                            "cwd": "/rh5-DO-NOT-LOG-VALUES/workdir"},
            env_extras={"LOOP_GATE_DIR": gate_dir},
        )
        assert proc.returncode == 0, proc.stderr
        raw = _last_debug_row_raw(gate_dir)
        row = json.loads(raw)
        # New field 1: session_id, verbatim from the stdin payload.
        assert row.get("session_id") == "rh5-session-abc123", row
        # New field 2: transcript basename ONLY -- no home/tmp paths in the log.
        assert row.get("transcript_basename") == os.path.basename(transcript), row
        assert os.sep not in row.get("transcript_basename", os.sep), row
        assert os.path.dirname(transcript) not in raw, (
            "transcript directory leaked into the debug log: %r" % raw)
        # New field 3: sorted top-level stdin keys, values redacted.
        expected_keys = sorted(["tool_name", "tool_input", "transcript_path",
                                "session_id", "cwd"])
        assert row.get("payload_keys") == expected_keys, row
        assert "/rh5-DO-NOT-LOG-VALUES/workdir" not in raw, (
            "payload VALUE leaked into the debug log: %r" % raw)
        # Pre-existing fields must survive alongside the new ones.
        assert row.get("decision") in ("allow", "deny"), row
        assert "tool" in row and "file" in row and "in_flight_ids" in row, row

    def test_rh5_decision_outcomes_unchanged_on_existing_fixtures(self):
        """[BEHAVIORAL] Allow/deny outcomes byte-identical on the two
        canonical fixtures, with the enriched stdin payload present: cold
        armed session -> deny; armed session with an in-flight dispatch ->
        allow."""
        extras = {"session_id": "rh5-session-decisions", "cwd": "/rh5/wd"}
        gate_dir = tempfile.mkdtemp(prefix="rh5-gate-")
        # Cold armed session -> deny (unchanged).
        proc, _ = _run_hook_with_payload(
            [_user_event(_orchestrator_head())],
            payload_extras=extras, env_extras={"LOOP_GATE_DIR": gate_dir})
        assert proc.returncode == 0
        assert _denied(proc), proc.stdout
        # Armed session, fresh un-retired dispatch -> allow (unchanged).
        proc2, _ = _run_hook_with_payload(
            [_user_event(_orchestrator_head()),
             _assistant_tool_use("Agent", {"description": "Coder for the fix",
                                           "prompt": "implement per spec"},
                                 tool_use_id="toolu_rh5")],
            payload_extras=extras, env_extras={"LOOP_GATE_DIR": gate_dir})
        assert proc2.returncode == 0
        assert not _denied(proc2), proc2.stdout
