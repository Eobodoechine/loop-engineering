"""test_run_trace.py — real tests for runner.run_trace + the traced run loop.

Unit tests cover the crash-survivable trace + atomic checkpoint properties.
The integration tests prove that LoopTeam.run(run_dir=...) actually emits
trace.jsonl / checkpoint.json / run_log.md, and that run_dir=None leaves the
existing (untraced) behaviour completely unchanged.
"""
import json
import os
import subprocess
import sys

import pytest

from runner import run_trace as T
from runner import LoopTeam


# loop-team dir (parent of the `runner` package) — needed so a spawned child
# process can `from runner import run_trace`.
_LOOP_TEAM_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# 1. Event append survives a crash: every line is valid JSON.
# ---------------------------------------------------------------------------

def test_events_are_valid_jsonl(tmp_path):
    tr = T.Tracer(tmp_path)
    tr.event("role_dispatch", role="coder", model="claude-sonnet-4-5",
             iteration=1, tokens_in=1000, tokens_out=200)
    tr.event("verdict", role="verifier", model="claude-haiku-4-5",
             iteration=1, tokens_in=500, tokens_out=50, verdict="PASS")
    path = os.path.join(str(tmp_path), "trace.jsonl")
    with open(path) as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        rec = json.loads(ln)
        assert set(rec) >= {
            "ts", "event_type", "role", "model", "iteration",
            "tokens_in", "tokens_out", "cum_tokens", "cum_cost_usd",
            "outcome", "verdict", "note",
        }


def test_append_survives_torn_final_line(tmp_path):
    tr = T.Tracer(tmp_path)
    tr.event("role_dispatch", role="coder", model="claude-sonnet-4-5",
             tokens_in=100, tokens_out=10)
    tr.event("verify", role="verifier", model="claude-haiku-4-5",
             tokens_in=80, tokens_out=8)
    path = os.path.join(str(tmp_path), "trace.jsonl")
    with open(path, "a") as fh:
        fh.write('{"ts": "2026-06-29T00:00:00", "event_type": "verdi')  # torn
    events = T.read_trace(tmp_path)
    assert len(events) == 2
    assert events[0]["event_type"] == "role_dispatch"
    assert events[1]["event_type"] == "verify"


def test_crash_in_separate_process_leaves_valid_prefix(tmp_path):
    script = (
        "import sys, os; sys.path.insert(0, %r);"
        "from runner import run_trace as T;"
        "tr = T.Tracer(%r);"
        "tr.event('role_dispatch', role='coder', model='claude-sonnet-4-5', tokens_in=100, tokens_out=10);"
        "tr.event('verify', role='verifier', model='claude-haiku-4-5', tokens_in=50, tokens_out=5);"
        "tr.event('verdict', role='verifier', verdict='PASS');"
        "os._exit(1)"
    ) % (_LOOP_TEAM_DIR, str(tmp_path))
    proc = subprocess.run([sys.executable, "-c", script])
    assert proc.returncode == 1
    events = T.read_trace(tmp_path)
    assert [e["event_type"] for e in events] == ["role_dispatch", "verify", "verdict"]


# ---------------------------------------------------------------------------
# 2. Cumulative totals + cost honesty.
# ---------------------------------------------------------------------------

def test_cum_tokens_accumulate(tmp_path):
    tr = T.Tracer(tmp_path)
    r1 = tr.event("role_dispatch", model="claude-sonnet-4-5", tokens_in=1000, tokens_out=200)
    r2 = tr.event("role_dispatch", model="claude-sonnet-4-5", tokens_in=500, tokens_out=100)
    assert r1["cum_tokens"] == 1200
    assert r2["cum_tokens"] == 1800
    assert T.read_trace(tmp_path)[-1]["cum_tokens"] == 1800


def test_cum_cost_matches_rate_table(tmp_path):
    tr = T.Tracer(tmp_path)
    r1 = tr.event("role_dispatch", model="claude-sonnet-4-5",
                  tokens_in=1_000_000, tokens_out=1_000_000)
    assert r1["cost_usd"] == pytest.approx(18.0)
    r2 = tr.event("verdict", model="claude-haiku-4-5",
                  tokens_in=1_000_000, tokens_out=1_000_000, verdict="PASS")
    assert r2["cum_cost_usd"] == pytest.approx(22.8)


def test_unknown_model_cost_null_and_poisons(tmp_path):
    tr = T.Tracer(tmp_path)
    tr.event("role_dispatch", model="claude-sonnet-4-5", tokens_in=1000, tokens_out=200)
    tr.event("role_dispatch", model="mystery-model", tokens_in=1000, tokens_out=200)
    r3 = tr.event("verdict", model="claude-haiku-4-5", tokens_in=100, tokens_out=10, verdict="PASS")
    assert r3["cum_cost_usd"] is None


def test_no_model_event_does_not_poison_cost(tmp_path):
    tr = T.Tracer(tmp_path)
    tr.event("role_dispatch", model="claude-sonnet-4-5", tokens_in=1000, tokens_out=200)
    tr.event("lesson", note="no model -> cost neutral")
    r3 = tr.event("verdict", model="claude-haiku-4-5", tokens_in=100, tokens_out=10, verdict="PASS")
    assert r3["cum_cost_usd"] is not None


# ---------------------------------------------------------------------------
# 3. Checkpoint atomicity + resume.
# ---------------------------------------------------------------------------

def test_resume_none_when_absent(tmp_path):
    assert T.resume(tmp_path) is None


def test_resume_returns_last_checkpoint(tmp_path):
    T.checkpoint(tmp_path, {"iteration": 1, "phase": "coder"})
    T.checkpoint(tmp_path, {"iteration": 3, "phase": "done", "verdict": "PASS"})
    last = T.resume(tmp_path)
    assert last["iteration"] == 3 and last["verdict"] == "PASS"


def test_checkpoint_never_torn_under_interrupted_write(tmp_path, monkeypatch):
    T.checkpoint(tmp_path, {"iteration": 1, "good": True})

    def boom(src, dst):
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(T.os, "replace", boom)
    with pytest.raises(OSError):
        T.checkpoint(tmp_path, {"iteration": 2, "good": False})
    monkeypatch.undo()
    assert T.resume(tmp_path) == {"iteration": 1, "good": True}
    assert [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")] == []


def test_resume_none_on_corrupt_checkpoint(tmp_path):
    with open(os.path.join(str(tmp_path), "checkpoint.json"), "w") as fh:
        fh.write("{ not valid json")
    assert T.resume(tmp_path) is None


# ---------------------------------------------------------------------------
# 4. Integration: the traced run loop actually emits the artifacts, and
#    run_dir=None is unchanged (non-breaking).
# ---------------------------------------------------------------------------

def _factory_pass_first():
    """Injected llm_factory: coder returns impl, verifier passes on iter 1.

    dispatch_role builds prompts as "Role: {name}\\n\\n{context}" in injection
    mode, so we route on that.
    """
    def factory(provider=None, model=None):
        def llm(prompt):
            if prompt.startswith("Role: verifier"):
                return "passed: true\nLooks correct."
            return "def f():\n    return 42"
        return llm
    return factory


def test_traced_run_emits_artifacts(tmp_path):
    team = LoopTeam(llm_factory=_factory_pass_first())
    run_dir = tmp_path / "run1"
    result = team.run("Build a function f that returns 42.", run_dir=str(run_dir))
    assert result.success is True
    assert result.iterations == 1
    # The three observability artifacts exist.
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "checkpoint.json").exists()
    assert (run_dir / "run_log.md").exists()
    # Trace has the expected event shape: a run_started, two role_dispatches, a verdict.
    events = T.read_trace(run_dir)
    types = [e["event_type"] for e in events]
    assert "role_dispatch" in types and "verdict" in types
    assert events[-1]["verdict"] == "PASS"
    # Checkpoint reflects the terminal state.
    cp = T.resume(run_dir)
    assert cp["done"] is True and cp["last_verdict"] == "PASS"
    # run_log.md is dashboard-parseable.
    log = (run_dir / "run_log.md").read_text()
    assert "Outcome: PASS" in log


def test_run_without_run_dir_writes_nothing(tmp_path, monkeypatch):
    """run_dir=None must be byte-for-byte the old behaviour: no files, same result."""
    monkeypatch.chdir(tmp_path)
    team = LoopTeam(llm_factory=_factory_pass_first())
    result = team.run("Build a function f that returns 42.")  # no run_dir
    assert result.success is True and result.iterations == 1
    # Nothing was written anywhere under cwd.
    assert list(tmp_path.iterdir()) == []
