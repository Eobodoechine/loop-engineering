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
