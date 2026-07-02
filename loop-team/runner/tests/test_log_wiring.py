"""test_log_wiring.py — runner wiring for the shared structured logger (AC13).

Written BEFORE implementation (TDD). Will FAIL until the runner emits structured
log lines to <run_dir>/log.jsonl (alongside trace.jsonl) on a FAIL verdict, and
remains a full no-op when run_dir is None.

Reuses the TestLoopCycle scripted_llm injection pattern from test_runner.py:
inject an llm_factory whose verifier ALWAYS returns "passed: false", forcing a
deterministic FAIL with NO API key required. The loop runs MAX_ITERS and returns
success=False; the wiring must record the failing verdict at level >= WARNING.

Runs under the runner suite:
    python3 -m pytest loop-team/runner/tests/test_log_wiring.py -q
"""
import importlib
import os
import sys
import textwrap

import pytest

RUNNER_PACKAGE = "runner"


def _reload_runner():
    for key in list(sys.modules.keys()):
        if key == RUNNER_PACKAGE or key.startswith(RUNNER_PACKAGE + "."):
            del sys.modules[key]
    return importlib.import_module(RUNNER_PACKAGE)


def _always_fail_llm(prompt):
    """Verifier always returns passed:false -> deterministic FAIL, no API key.

    Mirrors the scripted_llm contract from test_runner.TestLoopCycle: route on
    verifier/verify/passed keywords, return a failing verdict for the verifier
    and a stub implementation for the coder.
    """
    pl = prompt.lower()
    if "verifier" in pl or "verify" in pl or "passed" in pl:
        return "passed: false\nreason: deterministically failing for the wiring test."
    return "def stub():\n    return None\n"


def _read_jsonl(path):
    import json
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


BRIEF = textwrap.dedent("""\
    # Brief: Deterministic FAIL
    Implement something the (scripted) verifier always rejects.
    ## Acceptance criteria
    - This run is forced to FAIL so we can observe the failure log line.
""")


class TestRunnerLogWiring:
    def test_run_dir_writes_failure_line_alongside_trace(self, sample_config, tmp_path):
        """[BEHAVIORAL] AC13: team.run(brief, run_dir=<dir>) with a verifier that
        always returns passed:false writes a line at level >= WARNING recording
        the failing verdict to <dir>/log.jsonl, which COEXISTS with trace.jsonl."""
        _reload_runner()
        runner = sys.modules[RUNNER_PACKAGE]
        LoopTeam = runner.LoopTeam

        team = LoopTeam(
            config_path=sample_config,
            llm_factory=lambda *a, **kw: _always_fail_llm,
        )

        run_dir = tmp_path / "run"
        result = team.run(BRIEF, run_dir=str(run_dir))

        # The injected verifier forces a FAIL.
        success = result.success if hasattr(result, "success") else result.get("success")
        assert success is False, f"expected a FAIL run, got success={success!r}"

        # trace.jsonl is the existing artifact; log.jsonl must coexist with it.
        trace_path = run_dir / "trace.jsonl"
        log_path = run_dir / "log.jsonl"
        assert trace_path.exists(), "runner did not write trace.jsonl (existing contract)"
        assert log_path.exists(), (
            "runner did not write log.jsonl under run_dir (the new wiring)"
        )

        records = _read_jsonl(str(log_path))
        failure_lines = [
            r for r in records
            if r.get("level", "").upper() in ("WARNING", "ERROR", "CRITICAL")
        ]
        assert failure_lines, (
            "expected >=1 WARNING/ERROR/CRITICAL line recording the FAIL verdict; "
            f"levels seen: {[r.get('level') for r in records]}"
        )
        # The failing verdict must be recorded somewhere in a failure line.
        import json as _json
        assert any("FAIL" in _json.dumps(r).upper() for r in failure_lines), (
            "expected the failing verdict (FAIL) recorded on a failure-level line; "
            f"failure records: {failure_lines}"
        )

    def test_run_dir_none_writes_no_log_jsonl(self, sample_config, tmp_path, monkeypatch):
        """[BEHAVIORAL] AC13: team.run(brief, run_dir=None) writes NO log.jsonl
        anywhere (full no-op logging path)."""
        _reload_runner()
        runner = sys.modules[RUNNER_PACKAGE]
        LoopTeam = runner.LoopTeam

        # Run from an empty cwd so a stray relative log.jsonl would be detectable here.
        workdir = tmp_path / "cwd"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        team = LoopTeam(
            config_path=sample_config,
            llm_factory=lambda *a, **kw: _always_fail_llm,
        )
        result = team.run(BRIEF, run_dir=None)
        success = result.success if hasattr(result, "success") else result.get("success")
        assert success is False, f"expected a FAIL run, got success={success!r}"

        # No log.jsonl in the cwd, and none under tmp_path at all.
        for root, _dirs, files in os.walk(tmp_path):
            assert "log.jsonl" not in files, (
                f"run_dir=None must not write log.jsonl, but found one in {root}"
            )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
