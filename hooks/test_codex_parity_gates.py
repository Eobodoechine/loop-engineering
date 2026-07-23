"""Gate-level integration tests for Deliverable A (Codex enforcement parity),
research/spec-codex-parity-and-consent-installer-2026-07-09.md.

Covers AC-4, AC-5, AC-6: proving loop_stop_guard.py's RUNLOG_MISSING gate and
micro_step_gates.py's thrash-past-green gate GENUINELY fire (or correctly
don't) under real-shaped Codex input -- not merely that codex_transcript_
adapter.py exists and has correct unit behavior in isolation (that's
test_codex_transcript_adapter.py's job). Mirrors this repo's existing split:
test_verifier_hygiene_scan.py (shared-module unit tests) vs.
test_verifier_hygiene_gate.py (gate-level consumption tests).

Every test here currently fails (loop_stop_guard.py / micro_step_gates.py
have no Codex-path integration yet) -- expected pre-build.

loop_stop_guard.py executes top-level code on import (it's a Stop-hook
script, not a function-based module), so it MUST be driven via subprocess,
exactly like test_loop_stop_guard.py's own run_guard() helper -- duplicated
here (not imported from that test file, which is test-internal, not a
stable API) rather than shared, matching this repo's existing convention of
each test file owning its own small harness helpers.

micro_step_gates.py IS import-safe (function-based `run(data)` entry point),
so AC-6 drives it via direct import, exactly like test_micro_step_gates.py's
own `env` fixture convention.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HOOKS_DIR, "loop_stop_guard.py")
sys.path.insert(0, HOOKS_DIR)

import _codex_fixture_builders as fb  # noqa: E402
import micro_step_gates as msg  # noqa: E402


# ===========================================================================
# Shared helpers
# ===========================================================================

def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + "Z"


def run_guard(transcript_path, session_id="", stop_hook_active=False, gate_dir=None):
    payload = json.dumps({"transcript_path": transcript_path,
                          "stop_hook_active": stop_hook_active,
                          "session_id": session_id})
    env = dict(os.environ)
    if gate_dir:
        env["LOOP_GATE_DIR"] = gate_dir
    p = subprocess.run([sys.executable, GUARD], input=payload,
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def make_run_dir(tmp_path, name, log_name=None, log_content="done"):
    """A real, on-disk run directory: runs/<name>/specs/spec.md, optionally
    with a run-log file -- mirrors test_loop_stop_guard.py's own
    _rl_make_run_dir() convention (specs/-wrapped, the current convention)."""
    run_dir = tmp_path / name
    specs_dir = run_dir / "specs"
    specs_dir.mkdir(parents=True)
    spec_path = specs_dir / "spec.md"
    spec_path.write_text("# spec\nSome spec content.\n")
    if log_name is not None:
        (run_dir / log_name).write_text(log_content)
    return str(run_dir), str(spec_path)


def codex_runlog_transcript(tmp_path, spec_path, verdict_text,
                             agent_type="verifier", prior_turn_events=None,
                             current_turn=True):
    """A real-shaped Codex transcript for a post-build Verifier."""
    session_id = "019f1000-runlog-0000-0000-000000000000"
    agent_id = "019f1000-runlog-0000-0000-000000000001"
    events = [fb.codex_session_meta(session_id)]
    if prior_turn_events:
        events.extend(prior_turn_events)
    if current_turn:
        events.append(fb.codex_turn_context())
    events.extend(fb.codex_spawn_agent(
        "call_1", "fc_1", agent_id, agent_type,
        "You are the loop-team Verifier for widget build. Read the spec "
        "at %s and verify the implemented widget build. Do all reads "
        "yourself; do NOT dispatch sub-agents." % spec_path))
    events.extend(fb.codex_wait_agent(
        "call_2", "fc_2", [agent_id],
        {agent_id: {"completed": "Reviewed the implemented artifact. %s -- looks good."
                    % verdict_text}}))
    path = str(tmp_path / "rollout.jsonl")
    fb.write_jsonl(path, events)
    return path


def codex_plancheck_runlog_transcript(tmp_path, spec_path, verdict_text):
    session_id = "019f1000-runlog-plan-0000-000000000000"
    agent_id = "019f1000-runlog-plan-0000-000000000001"
    events = [
        fb.codex_session_meta(session_id),
        fb.codex_turn_context(),
        *fb.codex_spawn_agent(
            "call_plan", "fc_plan", agent_id, "plan-check-verifier",
            "You are acting as the loop-team plan-check Verifier for the widget spec. "
            "Read the spec at %s and review it." % spec_path),
        *fb.codex_wait_agent(
            "call_wait_plan", "fc_wait_plan", [agent_id],
            {agent_id: {"completed": "Reviewed the plan only. PLAN_SUPPORT_JSON={} "
                        "REVIEWED_SPEC_SHA256=fixture %s LOOP_GATE: PLAN_PASS"
                        % verdict_text}}),
    ]
    path = str(tmp_path / "rollout_plancheck.jsonl")
    fb.write_jsonl(path, events)
    return path


# ===========================================================================
# AC-4 -- RUNLOG_MISSING fires under a real-shaped Codex fixture -- [BEHAVIORAL]
# ===========================================================================

class TestAC4RunlogMissingFiresUnderCodex:
    def test_codex_verdict_pass_no_runlog_blocks(self, tmp_path):
        run_dir, spec_path = make_run_dir(tmp_path, "run1", log_name=None)
        transcript = codex_runlog_transcript(tmp_path, spec_path,
                                             "VERDICT: PASS")
        code, err = run_guard(transcript)
        assert code == 2, err
        assert "RUNLOG_MISSING" in err or "run_log.md" in err, err
        assert os.path.realpath(run_dir) in err, err


    def test_codex_current_turn_plan_check_pass_no_runlog_allows(self, tmp_path):
        _run_dir, spec_path = make_run_dir(tmp_path, "run_plancheck", log_name=None)
        transcript = codex_plancheck_runlog_transcript(tmp_path, spec_path, "VERDICT: PASS")
        code, err = run_guard(transcript)
        assert code == 0, err

    def test_codex_prior_turn_postbuild_pass_no_runlog_allows(self, tmp_path):
        _run_dir, spec_path = make_run_dir(tmp_path, "run_prior", log_name=None)
        prior_agent_id = "019f1000-prior-0000-0000-000000000001"
        prior_events = []
        prior_events.extend(fb.codex_spawn_agent(
            "call_prior_spawn", "fc_prior_spawn", prior_agent_id, "verifier",
            "You are the loop-team Verifier for widget build. Read the spec at %s."
            % spec_path))
        prior_events.extend(fb.codex_wait_agent(
            "call_prior_wait", "fc_prior_wait", [prior_agent_id],
            {prior_agent_id: {"completed": "Reviewed implementation. VERDICT: PASS."}}))
        transcript = codex_runlog_transcript(
            tmp_path, spec_path, "VERDICT: FAIL", prior_turn_events=prior_events)
        code, err = run_guard(transcript)
        assert code == 0, err

    def test_claude_code_and_codex_produce_the_same_violation_shape(
            self, tmp_path):
        """Parity check (AC-3's own requirement: 'proving parity, not just
        the Codex path exists'). The SAME semantic scenario (Verifier
        VERDICT: PASS, no run_log.md) built once as a Claude-Code-shaped
        transcript and once as a Codex-shaped transcript must BOTH block
        with exit code 2 and both name the same run directory."""
        run_dir_cc, spec_cc = make_run_dir(tmp_path, "run_cc", log_name=None)
        cc_events = [
            fb.cc_user("go build"),
            fb.cc_assistant(fb.cc_tool_use(
                "t1", "Task", description="Verifier for widget build",
                subagent_type="verifier",
                prompt="Review the implemented widget build against the spec at %s." % spec_cc)),
            fb.cc_tool_result_event(
                "t1", "Reviewed the implemented artifact. VERDICT: PASS -- looks good."),
        ]
        cc_path = str(tmp_path / "cc.jsonl")
        fb.write_jsonl(cc_path, cc_events)
        code_cc, err_cc = run_guard(cc_path)

        run_dir_codex, spec_codex = make_run_dir(tmp_path, "run_codex",
                                                 log_name=None)
        codex_path = codex_runlog_transcript(tmp_path, spec_codex,
                                             "VERDICT: PASS")
        code_codex, err_codex = run_guard(codex_path)

        assert code_cc == 2, err_cc
        assert code_codex == 2, err_codex
        assert os.path.realpath(run_dir_cc) in err_cc
        assert os.path.realpath(run_dir_codex) in err_codex


# ===========================================================================
# AC-5 -- false-positive check: run_log.md present -> no fire -- [BEHAVIORAL]
# ===========================================================================

class TestAC5RunlogPresentDoesNotBlockUnderCodex:
    def test_codex_verdict_pass_with_runlog_allows(self, tmp_path):
        run_dir, spec_path = make_run_dir(
            tmp_path, "run2", log_name="run_log.md",
            log_content="Brief, spec, iteration diffs, final summary.\n")
        transcript = codex_runlog_transcript(tmp_path, spec_path,
                                             "VERDICT: PASS")
        code, err = run_guard(transcript)
        assert code == 0, err

    def test_codex_verdict_fail_never_triggers_runlog_check_at_all(
            self, tmp_path):
        """A gate that always fires is as broken as one that never does --
        confirm a VERDICT: FAIL dispatch (no pass, no run_log.md either)
        does not spuriously trip RUNLOG_MISSING (the gate is scoped to
        'a post-build Verifier returned VERDICT: PASS', not any Verifier
        activity at all)."""
        run_dir, spec_path = make_run_dir(tmp_path, "run3", log_name=None)
        transcript = codex_runlog_transcript(tmp_path, spec_path,
                                             "VERDICT: FAIL")
        code, err = run_guard(transcript)
        assert code == 0, err


# ===========================================================================
# AC-6 -- thrash-past-green Codex path -- [BEHAVIORAL]
# ===========================================================================

class TestAC6ThrashPastGreenFiresUnderCodex:
    def _git(self, target, *args):
        subprocess.run(["git", "-C", str(target)] + list(args),
                       capture_output=True, check=False)

    def _repo(self, tmp_path):
        target = tmp_path / "repo"
        target.mkdir()
        self._git(target, "init", "-q")
        self._git(target, "config", "user.email", "t@t")
        self._git(target, "config", "user.name", "t")
        (target / "mod.py").write_text("def f():\n    return 1\n")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-qm", "init")
        return target

    def test_worker_spawned_after_green_verify_uncommitted_blocks(
            self, tmp_path, monkeypatch):
        gate_dir = tmp_path / "gate"
        gate_dir.mkdir()
        monkeypatch.setenv("LOOP_GATE_DIR", str(gate_dir))
        target = self._repo(tmp_path)
        session_id = "sess-codex-thrash-1"

        t_green = time.time() - 120
        t_dispatch = time.time() - 60
        session_meta = fb.codex_session_meta(
            "019f2000-thrash-0000-0000-000000000000",
            cwd="you are **oga** -- orchestrator playbook loaded")
        green_events = fb.codex_exec_command(
            "call_v1", "fc_v1", "python3 -m pytest -q",
            '{"passed": true, "runner": "pytest", "summary": "12 passed"}',
            timestamp=_iso(t_green))
        worker_events = fb.codex_spawn_agent(
            "call_w1", "fc_w1", "019f2000-thrash-0000-0000-000000000001",
            "worker", "Implement the next micro-step for mod.py.",
            timestamp=_iso(t_dispatch))
        events = [session_meta] + green_events + worker_events
        transcript = str(tmp_path / "rollout.jsonl")
        fb.write_jsonl(transcript, events)

        (gate_dir / ("%s_target" % session_id)).write_text(str(target))
        # dirty, uncommitted change AFTER the last (init) commit
        (target / "mod.py").write_text("def f():\n    return 2\n")

        data = {"transcript_path": transcript, "session_id": session_id}
        blocked, text = msg.run(data)
        assert blocked is True, text
        assert "thrash-past-green" in text, text

    def test_worker_spawned_before_green_verify_does_not_block(
            self, tmp_path, monkeypatch):
        """Ordering matters: a worker dispatched BEFORE the green verify
        (i.e. the green run already re-validated post-dispatch) must not
        fire -- proves this isn't a bare 'was a worker ever spawned'
        check."""
        gate_dir = tmp_path / "gate"
        gate_dir.mkdir()
        monkeypatch.setenv("LOOP_GATE_DIR", str(gate_dir))
        target = self._repo(tmp_path)
        session_id = "sess-codex-thrash-2"

        t_dispatch = time.time() - 120
        t_green = time.time() - 60
        session_meta = fb.codex_session_meta(
            "019f2000-thrash-0000-0000-000000000002",
            cwd="you are **oga** -- orchestrator playbook loaded")
        worker_events = fb.codex_spawn_agent(
            "call_w1", "fc_w1", "019f2000-thrash-0000-0000-000000000003",
            "worker", "Implement the next micro-step for mod.py.",
            timestamp=_iso(t_dispatch))
        green_events = fb.codex_exec_command(
            "call_v1", "fc_v1", "python3 -m pytest -q",
            '{"passed": true, "runner": "pytest", "summary": "12 passed"}',
            timestamp=_iso(t_green))
        events = [session_meta] + worker_events + green_events
        transcript = str(tmp_path / "rollout.jsonl")
        fb.write_jsonl(transcript, events)

        (gate_dir / ("%s_target" % session_id)).write_text(str(target))
        (target / "mod.py").write_text("def f():\n    return 2\n")

        data = {"transcript_path": transcript, "session_id": session_id}
        blocked, _text = msg.run(data)
        assert blocked is False

    def test_worker_spawned_after_green_but_already_committed_does_not_block(
            self, tmp_path, monkeypatch):
        gate_dir = tmp_path / "gate"
        gate_dir.mkdir()
        monkeypatch.setenv("LOOP_GATE_DIR", str(gate_dir))
        target = self._repo(tmp_path)
        session_id = "sess-codex-thrash-3"

        t_green = time.time() - 120
        t_dispatch = time.time() - 60
        session_meta = fb.codex_session_meta(
            "019f2000-thrash-0000-0000-000000000004",
            cwd="you are **oga** -- orchestrator playbook loaded")
        green_events = fb.codex_exec_command(
            "call_v1", "fc_v1", "python3 -m pytest -q",
            '{"passed": true, "runner": "pytest", "summary": "12 passed"}',
            timestamp=_iso(t_green))
        worker_events = fb.codex_spawn_agent(
            "call_w1", "fc_w1", "019f2000-thrash-0000-0000-000000000005",
            "worker", "Implement the next micro-step for mod.py.",
            timestamp=_iso(t_dispatch))
        events = [session_meta] + green_events + worker_events
        transcript = str(tmp_path / "rollout.jsonl")
        fb.write_jsonl(transcript, events)

        (gate_dir / ("%s_target" % session_id)).write_text(str(target))
        (target / "mod.py").write_text("def f():\n    return 2\n")
        self._git(target, "add", "-A")
        self._git(target, "commit", "-qm", "checkpoint after green")

        data = {"transcript_path": transcript, "session_id": session_id}
        blocked, _text = msg.run(data)
        assert blocked is False


# ===========================================================================
# AC-7 (end-to-end fail-open slice) -- [BEHAVIORAL]
# ===========================================================================

class TestAC7EndToEndFailOpen:
    def test_malformed_codex_transcript_never_crashes_the_hook(self, tmp_path):
        """A malformed/unexpected Codex transcript shape (schema drift the
        official docs warn about) must be caught by the SAME
        `except Exception: sys.stderr.write(...)` fail-open pattern already
        used by every other gate -- never a hard crash (a raw Python
        traceback / non-{0,2} exit code), never a silent hang."""
        session_id = "019f3000-malformed-000-0000-000000000000"
        events = [
            fb.codex_session_meta(session_id),
            # a function_call whose arguments is garbage, not valid JSON
            {"timestamp": "t", "type": "response_item",
             "payload": {"type": "function_call", "id": "fc1",
                        "name": "spawn_agent", "namespace": "multi_agent_v1",
                        "arguments": "{completely broken", "call_id": "c1"}},
            # a wait_agent output referencing an agent_id that was NEVER
            # spawned (dangling correlation)
            {"timestamp": "t", "type": "response_item",
             "payload": {"type": "function_call_output", "call_id": "c2",
                        "output": json.dumps(
                            {"status": {"ghost-agent-id":
                                        {"completed": "VERDICT: PASS"}},
                             "timed_out": False})}},
        ]
        path = str(tmp_path / "malformed.jsonl")
        fb.write_jsonl(path, events)
        code, err = run_guard(path)
        assert code in (0, 2), (
            "Hook exited with code %r (stderr: %s) -- a malformed Codex "
            "transcript must fail OPEN (0 or the normal block code 2), "
            "never crash with an uncaught exception's exit code." % (code, err))
        assert "Traceback (most recent call last)" not in err, err
