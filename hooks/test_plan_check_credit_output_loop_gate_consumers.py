"""Consumer/integration tests for hooks/plan_check_credit_output.py's
LOOP_GATE verdict-line format fix.

Spec: loop-team/runs/20260721_115722_plancheck-credit-output-loop-gate-format/
specs/spec.md (PLAN_PASS on hash
641dcac9d19021ad334baf354c38eff0a080aebaa3c98a2f1546ef1f7040fd51).

hooks/test_plan_check_credit_output.py already freezes the helper script's
OWN output shape (3 lines, JSON fields, hash algorithm) and, per this spec's
AC5, now also pins the exact literal LOOP_GATE line via direct equality
(AC1/AC2/AC6). What that file does NOT cover is whether the REAL downstream
consumers named in this spec's Context section actually accept the fixed
output — `_validate_plan_support_json()` (exercised by that file's
`test_passes_actual_validator`) never reads the LOOP_GATE line at all, so a
fix/test that only keeps it passing is vacuous for this exact bug (see the
spec's Context section and AC3).

This file supplies that missing coverage for the two ACs that concern
`hooks/`-local consumers:

- AC3: `classify_plan_result_for_hash()` / `result_plan_pass_status_for_hash()`
  in spec_bound_verifier_credit.py, run against the helper script's REAL,
  actually-executed stdout (never a same-file string-literal echo of the
  expected text).
- AC4: the two prose call sites (orchestrator.md, roles/verifier.md) that
  document a `--verdict FAIL` CLI invocation are exercised as documented,
  proving the CLI contract they rely on still works after the fix (the
  spec's Design section pins Option B: `--verdict` choices stay
  `PASS`/`FAIL`; only the script's print format changes).

(subagent_stop_gate.py's tier-1/tier-2 precedence check (AC9) and
claude_role_runner.py's validate_final_token() (AC10) are covered in their
own established test files — hooks/test_subagent_stop_gate.py and
loop-team/harness/test_claude_role_runner.py respectively — per this spec's
own file-to-extend guidance.)

Written before the fix lands: every test below is expected to FAIL red
against the CURRENT (buggy, bare `LOOP_GATE: PASS`/`LOOP_GATE: FAIL`) script
output, and to turn green once the Coder's fix makes the script emit the
literal `LOOP_GATE: PLAN_PASS` / `LOOP_GATE: PLAN_FAIL` line.
"""
import os
import re
import subprocess
import sys

import pytest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HOOKS_DIR)
HELPER = os.path.join(HOOKS_DIR, "plan_check_credit_output.py")
ORCHESTRATOR_MD = os.path.join(REPO_ROOT, "loop-team", "orchestrator.md")
VERIFIER_MD = os.path.join(REPO_ROOT, "loop-team", "roles", "verifier.md")

sys.path.insert(0, HOOKS_DIR)


@pytest.fixture
def spec_file(tmp_path):
    """Create a minimal spec file with known content (same shape as
    hooks/test_plan_check_credit_output.py's own fixture, so the evidence
    span [7, 9] is valid in both)."""
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


def run_helper(spec_path, verdict=None):
    """Actually execute the real helper script and return its 3 output
    lines. Never hand-construct the expected text -- AC3's own wording
    explicitly requires an executing integration test, "not a same-file
    string-literal echo"."""
    cmd = [sys.executable, HELPER, spec_path, "7", "9"]
    if verdict is not None:
        cmd += ["--verdict", verdict]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"helper exited nonzero: {result.stderr}"
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 3, f"expected 3 lines, got {lines!r}"
    return lines


def reviewed_hash_from(lines):
    assert lines[1].startswith("REVIEWED_SPEC_SHA256=")
    return lines[1][len("REVIEWED_SPEC_SHA256="):]


class TestClassifyPlanResultForHashAgainstRealOutput:
    """AC3: classify_plan_result_for_hash()/result_plan_pass_status_for_hash()
    exercised against the FIXED script's real output (lines 433-604 of
    spec_bound_verifier_credit.py) -- the actual LOOP_GATE consumer, as
    opposed to _validate_plan_support_json() (lines 389-430), which never
    reads the LOOP_GATE line and is necessary but NOT sufficient for this
    bug."""

    def test_real_pass_output_classifies_as_valid_pass(self, spec_file):
        from spec_bound_verifier_credit import (
            PlanResultOutcome,
            classify_plan_result_for_hash,
            result_plan_pass_status_for_hash,
        )

        lines = run_helper(spec_file)
        tool_result = {"content": "\n".join(lines)}
        reviewed_hash = reviewed_hash_from(lines)

        outcome, reason = classify_plan_result_for_hash(tool_result, reviewed_hash)
        assert outcome is PlanResultOutcome.VALID_PASS, (
            f"expected VALID_PASS for the real PASS-path output, got "
            f"{outcome} ({reason}); real output was {lines!r}"
        )

        ok, ok_reason = result_plan_pass_status_for_hash(tool_result, reviewed_hash)
        assert ok is True, (
            f"result_plan_pass_status_for_hash must credit the real PASS-path "
            f"output, got ok={ok} ({ok_reason})"
        )

    def test_real_fail_output_classifies_as_explicit_plan_fail(self, spec_file):
        from spec_bound_verifier_credit import (
            PlanResultOutcome,
            classify_plan_result_for_hash,
            result_plan_pass_status_for_hash,
        )

        lines = run_helper(spec_file, verdict="FAIL")
        tool_result = {"content": "\n".join(lines)}
        reviewed_hash = reviewed_hash_from(lines)

        outcome, reason = classify_plan_result_for_hash(tool_result, reviewed_hash)
        assert outcome is PlanResultOutcome.EXPLICIT_PLAN_FAIL, (
            f"expected EXPLICIT_PLAN_FAIL for the real FAIL-path output, got "
            f"{outcome} ({reason}); real output was {lines!r}"
        )

        ok, ok_reason = result_plan_pass_status_for_hash(tool_result, reviewed_hash)
        assert ok is False, (
            f"a FAIL-path result must never be credited as PASS (ok={ok})"
        )

    def test_real_pass_and_real_fail_outputs_never_both_classify_the_same(self, spec_file):
        """A minimal, explicit anti-vacuity check: the two real outputs must
        not collapse to the same outcome (e.g. both silently falling into
        OTHER_INVALID_OR_AMBIGUOUS, which would make the two tests above
        pass for the wrong reason if PlanResultOutcome identity comparison
        were ever weakened to a truthiness check)."""
        from spec_bound_verifier_credit import classify_plan_result_for_hash

        pass_lines = run_helper(spec_file)
        pass_result = {"content": "\n".join(pass_lines)}
        pass_outcome, _ = classify_plan_result_for_hash(
            pass_result, reviewed_hash_from(pass_lines))

        fail_lines = run_helper(spec_file, verdict="FAIL")
        fail_result = {"content": "\n".join(fail_lines)}
        fail_outcome, _ = classify_plan_result_for_hash(
            fail_result, reviewed_hash_from(fail_lines))

        assert pass_outcome != fail_outcome


def _documented_verdict_value(doc_text):
    """Extract the CLI value documented for a FAIL verdict, e.g. the `FAIL`
    in "add `--verdict FAIL`.". Both orchestrator.md and roles/verifier.md
    currently document this exact invocation pattern -- this helper reads
    whatever value is LIVE in the doc at test time (not a hardcoded
    expectation) rather than assuming it can never drift. The spec's Design
    section pins Option B, so this value stays literal `FAIL` (the
    `--verdict` CLI contract, and these docs, are unchanged by the fix) --
    see spec Design space / AC4."""
    match = re.search(r"--verdict\s+([A-Za-z_]+)", doc_text)
    assert match, "no --verdict invocation found in doc text"
    return match.group(1)


class TestDocumentedCallSitesStillWork:
    """AC4: the 4 call sites found by the spec's own
    `grep -rn "plan_check_credit_output" ...` grep still work after the fix.

    orchestrator.md:656 and roles/verifier.md:128-135 are prose, not
    executable code, so "still works" is checked here by actually running
    the script the way each doc instructs an agent to run it (including the
    documented `--verdict FAIL` flag value) and confirming the real script
    accepts it and emits the new-format verdict line. The other 2 hits
    (hooks/test_plan_check_credit_output.py, plan_check_credit_output.py's
    own docstring) are the script's own test file (AC5's subject, handled
    there) and a non-executable docstring — see this suite's module
    docstring for why those two need no separate executing test here.
    """

    def test_orchestrator_md_documented_fail_invocation_still_works(self, spec_file):
        with open(ORCHESTRATOR_MD, encoding="utf-8") as f:
            doc_text = f.read()
        verdict_value = _documented_verdict_value(doc_text)

        lines = run_helper(spec_file, verdict=verdict_value)

        assert lines[2] == "LOOP_GATE: PLAN_FAIL", (
            f"orchestrator.md documents `--verdict {verdict_value}` for FAIL "
            f"verdicts; running the real script with that exact flag value "
            f"must still produce the new-format FAIL verdict line, got "
            f"{lines[2]!r}"
        )

    def test_verifier_md_documented_fail_invocation_still_works(self, spec_file):
        with open(VERIFIER_MD, encoding="utf-8") as f:
            doc_text = f.read()
        verdict_value = _documented_verdict_value(doc_text)

        lines = run_helper(spec_file, verdict=verdict_value)

        assert lines[2] == "LOOP_GATE: PLAN_FAIL", (
            f"roles/verifier.md documents `--verdict {verdict_value}` for FAIL "
            f"verdicts; running the real script with that exact flag value "
            f"must still produce the new-format FAIL verdict line, got "
            f"{lines[2]!r}"
        )

    def test_default_invocation_documented_by_both_prose_call_sites_still_works(self, spec_file):
        """Both orchestrator.md and roles/verifier.md document the PASS-path
        invocation with NO --verdict flag at all (relying on the default).
        This must still print the new-format PASS line regardless of which
        design option the Coder picks -- if Option A is chosen, the
        script's own --verdict default (not just its choices list) must be
        updated too, or this silently regresses to the pre-fix bug on every
        default invocation."""
        lines = run_helper(spec_file)
        assert lines[2] == "LOOP_GATE: PLAN_PASS"
