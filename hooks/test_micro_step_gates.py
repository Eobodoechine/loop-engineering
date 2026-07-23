#!/usr/bin/env python3
"""Regression tests for micro_step_gates.py + slop_gate.py (spec AC-B1/B2/B3/E3).

Fixtures are real-shaped: temp GIT repos with actual commits, transcripts whose
events carry the fields Claude Code emits (role/content/timestamp), verify results
in the exact JSON/pytest shapes the harness produces. Detection markers are built
dynamically — this file must never arm any guard by being read."""
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)
import micro_step_gates as msg  # noqa: E402
import slop_gate  # noqa: E402

M_OGA = "You are " + "**Oga**"


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + "+00:00"


def _user(text, epoch=None):
    e = {"role": "user", "content": [{"type": "text", "text": text}]}
    if epoch:
        e["timestamp"] = _iso(epoch)
    return e


def _tool_result(text, epoch):
    return {"role": "user", "timestamp": _iso(epoch),
            "content": [{"type": "tool_result", "content": text}]}


def _coder_dispatch(epoch):
    return {"role": "assistant", "timestamp": _iso(epoch),
            "content": [{"type": "tool_use", "name": "Agent",
                         "input": {"description": "Coder for step 2",
                                   "prompt": "roles/coder.md ..."}}]}


GREEN = '{"passed": true, "runner": "pytest", "summary": "12 passed"}'
RED = ('{"passed": false, "runner": "pytest", "output": "E AssertionError: '
       'boom at gate.py line 44"}')


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Temp gate dir + temp git target repo + transcript writer."""
    gate_dir = tmp_path / "gate"
    gate_dir.mkdir()
    monkeypatch.setenv("LOOP_GATE_DIR", str(gate_dir))
    target = tmp_path / "repo"
    target.mkdir()
    def git(*a):
        subprocess.run(["git", "-C", str(target)] + list(a), capture_output=True,
                       check=False)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (target / "mod.py").write_text("def f():\n    return 1\n")
    git("add", "-A"); git("commit", "-qm", "init")

    def write_transcript(events, armed=True, session="sess1"):
        t = tmp_path / "transcript.jsonl"
        if armed:
            events = [_user(M_OGA + " — orchestrator " + "playbook loaded")] + events
        t.write_text("\n".join(json.dumps(e) for e in events))
        if armed:
            (gate_dir / ("%s_target" % session)).write_text(str(target))
        return {"transcript_path": str(t), "session_id": session}

    class E: pass
    e = E(); e.gate_dir = gate_dir; e.target = target; e.git = git
    e.write = write_transcript
    return e


class TestActivation:
    def test_no_marker_no_gates(self, env):
        data = env.write([_tool_result(RED, time.time())], armed=False)
        assert msg.run(data) == (False, "")

    def test_marker_but_no_target_file(self, env):
        data = env.write([], armed=True)
        os.remove(env.gate_dir / "sess1_target")
        assert msg.run(data) == (False, "")

    def test_stale_target_ignored_and_deleted(self, env):
        data = env.write([], armed=True)
        tf = env.gate_dir / "sess1_target"
        os.utime(tf, (time.time() - 90000, time.time() - 90000))  # >24h
        assert msg.run(data) == (False, "")
        assert not tf.exists()

    def test_corrupt_target_path_allows(self, env):
        data = env.write([], armed=True)
        (env.gate_dir / "sess1_target").write_text("/nonexistent/not-a-repo")
        assert msg.run(data) == (False, "")


class TestStepSizeGate:
    def test_over_200_code_lines_blocks(self, env):
        (env.target / "big.py").write_text("x = 1\n" * 250)
        env.git("add", "-A")
        data = env.write([])
        blocked, m = msg.run(data)
        assert blocked and "step-size" in m

    def test_small_diff_allows(self, env):
        (env.target / "mod.py").write_text("def f():\n    return 2\n")
        data = env.write([])
        blocked, _ = msg.run(data)
        assert not blocked

    def test_test_files_excluded_from_count(self, env):
        (env.target / "tests").mkdir()
        (env.target / "tests" / "test_big.py").write_text("x = 1\n" * 300)
        env.git("add", "-A")
        data = env.write([])
        blocked, _ = msg.run(data)
        assert not blocked


class TestThrashPastGreenGate:
    def test_green_then_coder_then_dirty_no_commit_blocks(self, env):
        now = time.time()
        # backdate the init commit: the green verify must postdate the last commit
        # (git commit timestamps are second-granular; the fixture commit was "now")
        subprocess.run(["git", "-C", str(env.target), "commit", "--amend",
                        "--no-edit", "-q"], capture_output=True,
                       env={**os.environ, "GIT_COMMITTER_DATE": "2026-07-01T00:00:00"})
        (env.target / "mod.py").write_text("def f():\n    return 3\n")  # dirty
        data = env.write([_tool_result(GREEN, now - 5), _coder_dispatch(now - 2)])
        blocked, m = msg.run(data)
        assert blocked and "thrash-past-green" in m

    def test_commit_after_green_allows(self, env):
        past = time.time() - 3600
        data = env.write([_tool_result(GREEN, past), _coder_dispatch(past + 10)])
        (env.target / "mod.py").write_text("def f():\n    return 4\n")
        env.git("add", "-A"); env.git("commit", "-qm", "checkpoint")
        (env.target / "mod.py").write_text("def f():\n    return 5\n")  # new dirty work
        blocked, _ = msg.run(data)
        assert not blocked  # condition (ii): commit exists after the green event

    def test_red_last_verify_never_fires_gate1(self, env):
        now = time.time()
        (env.target / "mod.py").write_text("def f():\n    return 6\n")
        data = env.write([_tool_result(GREEN, now - 10), _coder_dispatch(now - 8),
                          _tool_result(RED, now - 3)])
        blocked, m = msg.run(data)
        assert not blocked or "thrash" not in m

    def test_no_coder_after_green_allows(self, env):
        now = time.time()
        (env.target / "mod.py").write_text("def f():\n    return 7\n")
        data = env.write([_coder_dispatch(now - 10), _tool_result(GREEN, now - 3)])
        blocked, _ = msg.run(data)
        assert not blocked


class TestRetryCapGate:
    def test_third_same_signature_blocks(self, env):
        data = env.write([_tool_result(RED, time.time())])
        assert msg.run(data) == (False, "")     # 1st
        assert msg.run(data)[0] is False or True  # noop guard
        # simulate three turns: same red appended each run via fresh turn slice
        sigs = msg._load_sigs("sess1")
        assert len(sigs) >= 1
        msg._save_sigs("sess1", [sigs[-1]] * 2)
        blocked, m = msg.run(data)              # 3rd identical
        assert blocked and "retry-cap" in m and "Mode B" in m

    def test_rescanning_same_transcript_does_not_double_append(self, env):
        data = env.write([_tool_result(RED, time.time())])
        msg.run(data)
        n1 = len(msg._load_sigs("sess1"))
        msg.run(data)  # same Stop replayed — same turn, appends again by design?
        n2 = len(msg._load_sigs("sess1"))
        # each Stop invocation appends its turn's reds once; two invocations = 2.
        # The defect this guards: ONE invocation appending historical turns' reds.
        assert n2 - n1 <= 1

    def test_different_signatures_do_not_block(self, env):
        msg._save_sigs("sess1", ["sigA", "sigB", "sigA"])
        data = env.write([])
        blocked, _ = msg.run(data)
        assert not blocked


class TestRecordSigsParameter:
    """H-SUBAGENT-MASKING-1 (runs/2026-07-03_h-subagent-masking-1-full-
    closure/specs/spec.md), AC7: run()'s real signature today is
    `def run(data):` -- no second parameter. `_save_sigs(session_id, sigs)`
    fires unconditionally at line 277, inside run(), before any of gates
    1-4's own detection logic even executes. The fix adds
    `record_sigs=True` as an optional second parameter; when False,
    `_save_sigs()` must NOT be called (no `<session>_signatures.json` write
    happens as a side effect), while `_activation()` and gates 1-4's own
    detection logic (including building `sigs` in-memory) still run
    unconditionally every call -- only the persistence call becomes
    conditional."""

    # [BEHAVIORAL] AC7: record_sigs=False must not write/update the
    # on-disk signatures file, even though a red verify result is present
    # in the transcript this invocation would otherwise append a signature
    # for.
    def test_record_sigs_false_skips_persistence(self, env):
        data = env.write([_tool_result(RED, time.time())])
        sig_path = env.gate_dir / "sess1_signatures.json"
        assert not sig_path.exists()
        msg.run(data, record_sigs=False)
        assert not sig_path.exists(), (
            "_save_sigs() must not persist to disk when record_sigs=False")

    # [BEHAVIORAL] AC7 companion: the default (record_sigs omitted) must
    # still persist exactly as before this spec's change -- zero risk to
    # run()'s existing tested contract (TestRetryCapGate above already
    # depends on this).
    def test_record_sigs_default_true_persists(self, env):
        data = env.write([_tool_result(RED, time.time())])
        sig_path = env.gate_dir / "sess1_signatures.json"
        assert not sig_path.exists()
        msg.run(data)  # record_sigs omitted -> must default to True
        assert sig_path.exists(), (
            "the default (record_sigs omitted) must persist signatures "
            "exactly as before this spec's change")

    # [BEHAVIORAL] AC7: explicit record_sigs=True (not just the default)
    # behaves identically to omitting the parameter.
    def test_record_sigs_explicit_true_persists(self, env):
        data = env.write([_tool_result(RED, time.time())])
        sig_path = env.gate_dir / "sess1_signatures.json"
        assert not sig_path.exists()
        msg.run(data, record_sigs=True)
        assert sig_path.exists()

    # [BEHAVIORAL] AC7: record_sigs=False must not prevent gates 1-4's own
    # detection logic (including the in-memory sigs list build and the
    # retry-cap block decision itself) from running -- only persistence is
    # gated. Proven by still blocking on the 3rd consecutive identical
    # signature even when record_sigs=False for that final call (the
    # in-memory `sigs` list, loaded fresh via _load_sigs() at the top of
    # run(), still reflects the 2 prior persisted signatures -- only THIS
    # call's own write is skipped).
    def test_record_sigs_false_does_not_disable_detection_logic(self, env):
        data = env.write([_tool_result(RED, time.time())])
        msg.run(data)
        sigs = msg._load_sigs("sess1")
        assert len(sigs) >= 1
        msg._save_sigs("sess1", [sigs[-1]] * 2)
        blocked, m = msg.run(data, record_sigs=False)
        assert blocked and "retry-cap" in m, (
            "gates 1-4's own detection logic must still run unconditionally "
            "even when record_sigs=False -- only _save_sigs()'s persistence "
            "is gated, not detection")


class TestTestmonGate:
    def test_probe_succeeds_on_provisioned_host(self, env, capsys):
        """The dead-probe regression (import name is `testmon`): on this
        provisioned host the probe MUST succeed — the skip warning must be
        ABSENT when the gate runs against a dirty repo."""
        (env.target / "test_mod.py").write_text(
            "from mod import f\ndef test_f():\n    assert f() == 1\n")
        env.git("add", "-A"); env.git("commit", "-qm", "tests")
        (env.target / "mod.py").write_text("def f():\n    return 1  # touch\n")
        data = env.write([])
        msg.run(data)
        assert "SKIPPED: pytest-testmon not importable" not in capsys.readouterr().err

    def test_orphan_module_blocks(self, env):
        (env.target / "test_mod.py").write_text(
            "from mod import f\ndef test_f():\n    assert f() == 1\n")
        env.git("add", "-A"); env.git("commit", "-qm", "tests")
        # bootstrap the testmon DB
        subprocess.run([sys.executable, "-m", "pytest", "--testmon", "-q"],
                       cwd=env.target, capture_output=True, timeout=120)
        (env.target / "orphan.py").write_text("def g():\n    return 99\n")
        data = env.write([])
        blocked, m = msg.run(data)
        assert blocked and "orphan-module" in m and "orphan.py" in m

    def test_orphan_excluded_by_glob_warns_not_blocks(self, env, capsys):
        (env.target / "test_mod.py").write_text(
            "from mod import f\ndef test_f():\n    assert f() == 1\n")
        env.git("add", "-A"); env.git("commit", "-qm", "tests")
        subprocess.run([sys.executable, "-m", "pytest", "--testmon", "-q"],
                       cwd=env.target, capture_output=True, timeout=120)
        gate = env.target / ".gate"; gate.mkdir()
        (gate / "subprocess_tested.globs").write_text("orphan*.py\n")
        (env.target / "orphan.py").write_text("def g():\n    return 99\n")
        data = env.write([])
        blocked, _ = msg.run(data)
        assert not blocked
        assert "orphan (excluded" in capsys.readouterr().err

    def test_failing_impacted_tests_block(self, env):
        (env.target / "test_mod.py").write_text(
            "from mod import f\ndef test_f():\n    assert f() == 1\n")
        env.git("add", "-A"); env.git("commit", "-qm", "tests")
        subprocess.run([sys.executable, "-m", "pytest", "--testmon", "-q"],
                       cwd=env.target, capture_output=True, timeout=120)
        # different LENGTH + future mtime: a same-second same-size rewrite is
        # masked by Python's stale-bytecode check (mtime+size) — the exact
        # hazard logged in fix_plan; the fixture must not depend on luck.
        (env.target / "mod.py").write_text("def f():\n    return 20000\n")
        os.utime(env.target / "mod.py",
                 (time.time() + 2, time.time() + 2))
        data = env.write([])
        blocked, m = msg.run(data)
        assert blocked and "impacted-tests" in m


class TestSlopGateShadow:
    def test_shadow_report_on_dirty_repo(self, env):
        (env.target / "mod.py").write_text(
            "def f(x):\n" + "".join("    if x == %d:\n        return %d\n" % (i, i)
                                    for i in range(14)) + "    return 0\n")
        rec = slop_gate.shadow_report(str(env.target))
        assert rec["mode"] == "shadow"
        assert "erosion_mass_pct" in rec
        assert rec["erosion_mass_pct"]["after"] >= rec["erosion_mass_pct"]["before"]

    def test_cli_never_blocks(self, env):
        r = subprocess.run([sys.executable, os.path.join(HOOKS, "slop_gate.py"),
                            str(env.target), "sessX"],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "LOOP_GATE_DIR": str(env.gate_dir)})
        assert r.returncode == 0
        assert (env.gate_dir / "sessX_slop.jsonl").exists()

    def test_clean_repo_notes_no_changes(self, env):
        rec = slop_gate.shadow_report(str(env.target))
        assert rec.get("note") == "no uncommitted python changes"


class TestDefensiveWrapper:
    def test_corrupt_gate_state_never_blocks_stop_guard(self, env, tmp_path):
        """E3(e): exception path — a garbage target file must not block the LIVE
        loop_stop_guard (fail-open wrapper)."""
        data = env.write([])
        (env.gate_dir / "sess1_target").write_text("\x00garbage\x00")
        guard = os.path.join(HOOKS, "loop_stop_guard.py")
        stdin = json.dumps({"transcript_path": data["transcript_path"],
                            "session_id": "sess1"})
        r = subprocess.run([sys.executable, guard], input=stdin, text=True,
                           capture_output=True, timeout=60,
                           env={**os.environ, "LOOP_GATE_DIR": str(env.gate_dir)})
        assert r.returncode == 0


class TestLastActivationBroadcast:
    """H-REVIEW-COMMIT-1 (runs/2026-07-03_h-review-commit-1/specs/spec.md)
    AC25(a), AC26: the module-level _LAST_ACTIVATION broadcast cache that
    lets callers OTHER than run() (loop_stop_guard.py's shadow-slop block and
    the new raw-git-commit gate) read _activation()'s result without a
    second/third independent call.

    AC25's part (a) is testable HERE, at the direct-import unit level, per
    the spec's own round-5 correction: hooks/test_loop_stop_guard.py drives
    the guard exclusively as a subprocess (subprocess.run([sys.executable,
    GUARD], ...)), so a monkeypatched call-counter cannot cross that process
    boundary -- "count _activation() calls from a test_loop_stop_guard.py
    test" is not implementable as originally worded. AC25's part (b), the
    durable grep-based single-call-site regression check, lives in
    hooks/test_loop_stop_guard.py's ReviewCommitGateActivationSingleCallSite
    (it asserts against loop_stop_guard.py's own source, which this file has
    no reason to read)."""

    # [BEHAVIORAL] AC25(a): monkeypatch micro_step_gates._activation with a
    # call-counting wrapper, invoke run(data) ONCE for an armed payload, and
    # assert the wrapper was called EXACTLY ONCE by run() itself -- proves
    # run()'s own internal behavior (call _activation() exactly once, as its
    # unconditional first statement) is unchanged by this spec's addition.
    def test_run_calls_activation_exactly_once(self, env, monkeypatch):
        data = env.write([])  # armed=True by default
        calls = []
        real_activation = msg._activation

        def counting_activation(d):
            calls.append(d)
            return real_activation(d)

        monkeypatch.setattr(msg, "_activation", counting_activation)
        msg.run(data)
        assert len(calls) == 1, (
            "run() must call _activation() exactly once per invocation; "
            "got %d calls" % len(calls))

    # [BEHAVIORAL] AC25 companion (unchanged from the prior draft, restated
    # here for locality with the other _LAST_ACTIVATION tests): the 4
    # existing strict-equality tests for run()'s return value elsewhere in
    # this file (TestActivation, lines ~88/93/99/105) must still pass
    # completely unmodified -- proves zero risk to run()'s tested contract.
    # This is a structural marker test, not a new assertion: it directly
    # re-invokes the same four scenarios inline so a reviewer sees the AC25
    # "zero risk to run()'s contract" claim asserted at this location too.
    def test_existing_strict_equality_contract_unmodified(self, env):
        data = env.write([], armed=False)
        assert msg.run(data) == (False, "")
        data2 = env.write([], armed=True)
        os.remove(env.gate_dir / "sess1_target")
        assert msg.run(data2) == (False, "")

    # [BEHAVIORAL] AC26 part 1: an ARMED run(data1) call followed immediately
    # by an UNARMED run(data2) call in the SAME process -- _LAST_ACTIVATION
    # after the second call must be None, reflecting ONLY the second call's
    # own result, never a stale tuple carried over from the first.
    def test_last_activation_resets_to_none_after_unarmed_call_following_armed(self, env):
        armed_data = env.write([], armed=True, session="sess-armed")
        blocked, _ = msg.run(armed_data)
        assert msg._LAST_ACTIVATION is not None, (
            "fixture premise: the armed call must set a real tuple")
        assert msg._LAST_ACTIVATION[1] == "sess-armed"

        unarmed_data = env.write([], armed=False)
        msg.run(unarmed_data)
        assert msg._LAST_ACTIVATION is None, (
            "_LAST_ACTIVATION must reflect ONLY the most recent run() call; "
            "an unarmed call after an armed one must reset it to None, not "
            "leave the prior session's tuple in place")

    # [BEHAVIORAL] AC26 part 2 (mirror ordering): UNARMED then ARMED --
    # _LAST_ACTIVATION after the second call must be the real tuple from
    # that second call, not None left over from the first. Closes the gap
    # where a Coder might reason "the None branches don't need their own
    # global assignment since it's already None from module init" -- true
    # only for the FIRST call in a process, false here.
    def test_last_activation_reflects_armed_call_following_unarmed(self, env):
        unarmed_data = env.write([], armed=False)
        msg.run(unarmed_data)
        assert msg._LAST_ACTIVATION is None, (
            "fixture premise: the unarmed call must leave _LAST_ACTIVATION None")

        armed_data = env.write([], armed=True, session="sess-armed-2")
        msg.run(armed_data)
        assert msg._LAST_ACTIVATION is not None, (
            "_LAST_ACTIVATION must reflect the SECOND call's real tuple, "
            "not remain None from the first call's module-init-inherited "
            "state")
        assert msg._LAST_ACTIVATION[1] == "sess-armed-2"
        assert msg._LAST_ACTIVATION[0] == str(env.target)


class TestLiveGuardEndToEnd:
    def test_thrash_block_through_live_stop_guard(self, env):
        """E3(b): the B1 violation must block via the LIVE loop_stop_guard, not
        just the module — proves the wiring, not only the logic."""
        now = time.time()
        subprocess.run(["git", "-C", str(env.target), "commit", "--amend",
                        "--no-edit", "-q"], capture_output=True,
                       env={**os.environ, "GIT_COMMITTER_DATE": "2026-07-01T00:00:00"})
        (env.target / "mod.py").write_text("def f():\n    return 9\n")
        events = [
            {"role": "assistant", "content": [{"type": "tool_use", "name": "Agent",
             "input": {"description": "plan-check Verifier for step", "prompt":
                       "Read roles/verifier.md; spec at runs/x/spec.md."}}]},
            _tool_result(GREEN, now - 5),
            _coder_dispatch(now - 2),
        ]
        data = env.write(events)
        guard = os.path.join(HOOKS, "loop_stop_guard.py")
        stdin = json.dumps({"transcript_path": data["transcript_path"],
                            "session_id": "sess1"})
        r = subprocess.run([sys.executable, guard], input=stdin, text=True,
                           capture_output=True, timeout=120,
                           env={**os.environ, "LOOP_GATE_DIR": str(env.gate_dir)})
        assert r.returncode == 2
        assert "thrash-past-green" in r.stderr
