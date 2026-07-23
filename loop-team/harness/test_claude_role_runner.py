import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import claude_role_runner as runner

# AC10 (spec: loop-team/runs/20260721_115722_plancheck-credit-output-loop-gate-format,
# PLAN_PASS on hash 641dcac9d19021ad334baf354c38eff0a080aebaa3c98a2f1546ef1f7040fd51):
# this file is loop-team/harness/test_claude_role_runner.py, so the repo root
# (containing hooks/) is two directories up from this file's own directory.
_HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HARNESS_DIR))
PLAN_CHECK_HELPER = os.path.join(_REPO_ROOT, "hooks", "plan_check_credit_output.py")


class FakeRun:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if not self.responses:
            raise AssertionError("unexpected subprocess call: %r" % (cmd,))
        return self.responses.pop(0)


def proc(code=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


def test_load_base_dir_reads_config(tmp_path):
    cfg = tmp_path / "config"
    cfg.write_text("# comment\nbase_dir=%s\n" % (tmp_path / "loop"), encoding="utf-8")

    assert runner.load_base_dir(str(cfg)) == os.path.abspath(str(tmp_path / "loop"))


def test_check_reports_not_logged_in_without_role_dispatch(capsys):
    fake = FakeRun([
        proc(1, '{"loggedIn": false, "authMethod": "none", "apiProvider": "firstParty"}\n'),
    ])

    code = runner.main(["--check"], run=fake)

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["auth"]["loggedIn"] is False
    assert fake.calls[0][0] == ["claude", "auth", "status"]


def test_run_role_stops_before_claude_p_when_auth_is_missing(tmp_path):
    fake = FakeRun([
        proc(1, '{"loggedIn": false, "authMethod": "none"}\n'),
    ])
    cfg = tmp_path / "config"
    cfg.write_text("base_dir=%s\n" % tmp_path, encoding="utf-8")
    args = runner.make_parser().parse_args([
        "--role", "plan-check-verifier",
        "--prompt", "review the spec",
        "--config", str(cfg),
    ])

    code, payload = runner.run_role(args, run=fake)

    assert code == 3
    assert payload["error"] == "claude_not_logged_in"
    assert len(fake.calls) == 1


def test_build_role_prompt_points_to_canonical_role_file(tmp_path):
    text = runner.build_role_prompt(str(tmp_path), "plan-check-verifier", "Read spec.md")

    assert "loop-team/roles/verifier.md" in text
    assert "LOOP_GATE: PLAN_PASS" in text
    assert "Delegation from Codex/Oga:" in text
    assert "Read spec.md" in text


def test_build_claude_command_uses_print_mode_and_adds_base_dir(tmp_path):
    args = runner.make_parser().parse_args([
        "--role", "post-build-verifier",
        "--prompt", "verify artifact",
        "--skip-auth-check",
        "--config", str(tmp_path / "missing"),
        "--max-budget-usd", "0.25",
    ])
    cmd = runner.build_claude_command(args, str(tmp_path), "PROMPT")

    assert cmd[:2] == ["claude", "-p"]
    assert "--output-format" in cmd
    assert "text" in cmd
    assert "--add-dir" in cmd
    assert str(tmp_path) in cmd
    assert "--max-budget-usd" in cmd
    assert "PROMPT" == cmd[-1]


def test_validate_final_token_for_plan_check():
    ok, final_line = runner.validate_final_token(
        "plan-check-verifier",
        "analysis\n\nLOOP_GATE: PLAN_PASS\n",
    )

    assert ok is True
    assert final_line == "LOOP_GATE: PLAN_PASS"


def test_validate_final_token_rejects_trailing_sentence():
    ok, final_line = runner.validate_final_token(
        "plan-check-verifier",
        "LOOP_GATE: PLAN_PASS\nextra text\n",
    )

    assert ok is False
    assert final_line == "extra text"


def test_successful_run_writes_output_and_reports_token_valid(tmp_path):
    cfg = tmp_path / "config"
    cfg.write_text("base_dir=%s\n" % tmp_path, encoding="utf-8")
    output = tmp_path / "plan_check.txt"
    fake = FakeRun([
        proc(0, "Looks sound.\nLOOP_GATE: PLAN_PASS\n", ""),
    ])
    args = runner.make_parser().parse_args([
        "--role", "plan-check-verifier",
        "--prompt", "review the spec",
        "--config", str(cfg),
        "--output", str(output),
        "--skip-auth-check",
    ])

    code, payload = runner.run_role(args, run=fake)

    assert code == 0
    assert payload["ok"] is True
    assert payload["final_token_valid"] is True
    assert output.read_text(encoding="utf-8").endswith("LOOP_GATE: PLAN_PASS\n")
    assert fake.calls[0][0][0:2] == ["claude", "-p"]


def test_coder_role_is_not_supported():
    assert "coder" not in runner.ROLE_CONFIGS
    with pytest.raises(SystemExit):
        runner.make_parser().parse_args(["--role", "coder", "--prompt", "write code"])


def _plan_check_spec_fixture(tmp_path):
    """Same minimal spec shape hooks/test_plan_check_credit_output.py uses,
    so the [7, 9] evidence span is valid."""
    lines = [
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
    ]
    path = tmp_path / "spec.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _run_plan_check_helper(spec_path, verdict=None):
    """Actually execute hooks/plan_check_credit_output.py and return its
    real stdout, stripped. AC10 requires this be exercised against the
    FIXED script's real output, not a hand-typed string literal."""
    cmd = [sys.executable, PLAN_CHECK_HELPER, spec_path, "7", "9"]
    if verdict is not None:
        cmd += ["--verdict", verdict]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"helper exited nonzero: {result.stderr}"
    return result.stdout.strip()


# AC10 (spec: 20260721_115722_plancheck-credit-output-loop-gate-format):
# validate_final_token() exercised against hooks/plan_check_credit_output.py's
# REAL, actually-executed stdout for the "plan-check-verifier" role, mirroring
# how a real dispatch pastes the helper script's 3-line output as the tail of
# its own response (orchestrator.md's credit output helper instruction,
# roles/verifier.md:122-135). Written before the fix lands: expected to FAIL
# red against the CURRENT bare `LOOP_GATE: PASS`/`LOOP_GATE: FAIL` output
# (neither bare line is a member of ROLE_CONFIGS["plan-check-verifier"]
# ["final_tokens"], so validate_final_token returns valid=False), and to pass
# once the fix makes the script emit the literal `LOOP_GATE: PLAN_PASS` /
# `LOOP_GATE: PLAN_FAIL` line.
def test_validate_final_token_accepts_real_helper_pass_output(tmp_path):
    spec_path = _plan_check_spec_fixture(tmp_path)
    real_output = _run_plan_check_helper(spec_path)
    response_text = "Reviewed the spec, all ACs sound.\n" + real_output

    result = runner.validate_final_token("plan-check-verifier", response_text)

    assert result == (True, "LOOP_GATE: PLAN_PASS"), (
        f"expected (True, 'LOOP_GATE: PLAN_PASS') for the real helper "
        f"script's PASS output, got {result!r}; real output was "
        f"{real_output!r}"
    )


def test_validate_final_token_accepts_real_helper_fail_output(tmp_path):
    spec_path = _plan_check_spec_fixture(tmp_path)
    real_output = _run_plan_check_helper(spec_path, verdict="FAIL")
    response_text = "Reviewed the spec, found a real gap.\n" + real_output

    result = runner.validate_final_token("plan-check-verifier", response_text)

    assert result == (True, "LOOP_GATE: PLAN_FAIL"), (
        f"expected (True, 'LOOP_GATE: PLAN_FAIL') for the real helper "
        f"script's FAIL output, got {result!r}; real output was "
        f"{real_output!r}"
    )
