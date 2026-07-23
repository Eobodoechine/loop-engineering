"""Tests for hooks/plan_check_credit_output.py — the helper script that
mechanically produces correctly-formatted plan-check credit output.

These tests freeze the exact format the validator expects, so a regression
in the helper (wrong hash algorithm, multi-line JSON, code fences) is caught
before it blocks another Coder dispatch.

2026-07-21 (spec: runs/20260721_115722_plancheck-credit-output-loop-gate-format):
the LOOP_GATE verdict line must be the exact literal `LOOP_GATE: PLAN_PASS` /
`LOOP_GATE: PLAN_FAIL` — every real downstream consumer (spec_bound_verifier_
credit.py's classify_plan_result_for_hash(), subagent_stop_gate.py's tier-1/
tier-2 precedence check, claude_role_runner.py's validate_final_token())
parses that exact string, never the bare `PASS`/`FAIL` this script printed
before this fix. `test_loop_gate_line_pass`/`test_loop_gate_line_fail` below
were updated (Test-writer, per this spec's AC5) because they asserted that
old, bare format as correct — the pre-fix bug itself. The other 13 tests in
this file are format-agnostic (JSON fields, hash algorithm, line count,
whitespace, code-fence absence) or already exercise the LOOP_GATE-independent
`_validate_plan_support_json()` path, so none of them encode the wrong
format and none were changed. Additional integration coverage against the
three real downstream consumers (necessary because `_validate_plan_support_
json()` alone never reads the LOOP_GATE line, per this spec's Context
section) lives in `test_plan_check_credit_output_loop_gate_consumers.py`,
`test_subagent_stop_gate.py`, and `loop-team/harness/test_claude_role_runner.py`.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import pytest

HELPER = os.path.join(os.path.dirname(__file__), "plan_check_credit_output.py")


@pytest.fixture
def spec_file(tmp_path):
    """Create a minimal spec file with known content."""
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


def compute_expected_span_digest(path, start, end):
    """Compute the expected span digest using the validator's exact algorithm."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    selected = lines[start - 1:end]
    return hashlib.sha256("\n".join(selected).encode("utf-8")).hexdigest()


def compute_expected_file_sha256(path):
    """Compute the expected file SHA256."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class TestHelperOutput:
    """Tests for the credit output helper script."""

    def test_produces_three_lines(self, spec_file):
        """Output is exactly 3 lines: PLAN_SUPPORT_JSON, REVIEWED_SPEC_SHA256, LOOP_GATE."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        lines = result.stdout.strip().split("\n")
        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}: {lines}"

    def test_plan_support_json_is_single_line(self, spec_file):
        """PLAN_SUPPORT_JSON must be a single line (no multi-line JSON, no code fences)."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        line = result.stdout.strip().split("\n")[0]
        assert line.startswith("PLAN_SUPPORT_JSON="), f"Line doesn't start with prefix: {line}"
        # The JSON part must parse
        json_str = line[len("PLAN_SUPPORT_JSON="):]
        obj = json.loads(json_str)
        assert isinstance(obj, dict)

    def test_evidence_hash_matches_validator_algorithm(self, spec_file):
        """evidence_sha256 must match Python's '\\n'.join() with NO trailing newline."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        line = result.stdout.strip().split("\n")[0]
        obj = json.loads(line[len("PLAN_SUPPORT_JSON="):])

        expected = compute_expected_span_digest(spec_file, 7, 9)
        assert obj["evidence_sha256"] == expected, (
            f"Hash mismatch: helper={obj['evidence_sha256']}, expected={expected}"
        )

    def test_spec_sha256_matches_file_hash(self, spec_file):
        """spec_sha256 must match the full-file SHA256."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        line = result.stdout.strip().split("\n")[0]
        obj = json.loads(line[len("PLAN_SUPPORT_JSON="):])

        expected = compute_expected_file_sha256(spec_file)
        assert obj["spec_sha256"] == expected

    def test_reviewed_spec_sha256_matches_spec_sha256(self, spec_file):
        """REVIEWED_SPEC_SHA256 line must equal the spec_sha256 in the JSON."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")

        obj = json.loads(lines[0][len("PLAN_SUPPORT_JSON="):])
        reviewed_line = lines[1]
        assert reviewed_line.startswith("REVIEWED_SPEC_SHA256=")
        reviewed_hash = reviewed_line[len("REVIEWED_SPEC_SHA256="):]
        assert reviewed_hash == obj["spec_sha256"]

    def test_loop_gate_line_pass(self, spec_file):
        """Default verdict is PASS, printed as the exact literal
        `LOOP_GATE: PLAN_PASS` (AC1/AC6: direct equality, not a loose regex
        or `.startswith("LOOP_GATE")` — updated by the Test-writer per this
        spec; this test asserted the bare pre-fix `LOOP_GATE: PASS` string
        as correct before this revision)."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[2] == "LOOP_GATE: PLAN_PASS"

    def test_loop_gate_line_fail(self, spec_file):
        """--verdict FAIL produces the exact literal `LOOP_GATE: PLAN_FAIL`
        (AC2/AC6: direct equality — updated by the Test-writer per this spec;
        this test asserted the bare pre-fix `LOOP_GATE: FAIL` string as
        correct before this revision)."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9", "--verdict", "FAIL"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[2] == "LOOP_GATE: PLAN_FAIL"

    def test_custom_claim(self, spec_file):
        """--claim flag sets the claim field."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9", "--claim", "Custom claim text"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        obj = json.loads(result.stdout.strip().split("\n")[0][len("PLAN_SUPPORT_JSON="):])
        assert obj["claim"] == "Custom claim text"

    def test_all_required_fields_present(self, spec_file):
        """JSON contains exactly the required fields."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        obj = json.loads(result.stdout.strip().split("\n")[0][len("PLAN_SUPPORT_JSON="):])
        required = {"artifact_path", "line_start", "line_end", "evidence_sha256", "claim", "spec_sha256"}
        assert set(obj.keys()) == required

    def test_artifact_path_is_absolute(self, spec_file):
        """artifact_path must be absolute."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        obj = json.loads(result.stdout.strip().split("\n")[0][len("PLAN_SUPPORT_JSON="):])
        assert os.path.isabs(obj["artifact_path"])

    def test_invalid_span_exits_nonzero(self, spec_file):
        """Invalid line range exits with error."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "1", "999"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_missing_file_exits_nonzero(self, tmp_path):
        """Missing spec file exits with error."""
        result = subprocess.run(
            [sys.executable, HELPER, str(tmp_path / "nonexistent.md"), "1", "5"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_no_trailing_whitespace_on_lines(self, spec_file):
        """Output lines must not have trailing whitespace (validator is strict)."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        for line in result.stdout.strip().split("\n"):
            assert line == line.rstrip(), f"Trailing whitespace on: {line!r}"

    def test_no_code_fences(self, spec_file):
        """Output must NOT be wrapped in markdown code fences."""
        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "```" not in result.stdout, "Output contains code fences"

    def test_passes_actual_validator(self, spec_file):
        """End-to-end: helper output passes _validate_plan_support_json."""
        # Import the actual validator function
        sys.path.insert(0, os.path.dirname(__file__))
        try:
            from spec_bound_verifier_credit import _validate_plan_support_json
        except ImportError:
            pytest.skip("spec_bound_verifier_credit not importable")
        finally:
            sys.path.pop(0)

        result = subprocess.run(
            [sys.executable, HELPER, spec_file, "7", "9"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")

        support_line = lines[0]
        reviewed_hash = lines[1].split("=")[1]

        ok, reason = _validate_plan_support_json(support_line, reviewed_hash)
        assert ok, f"Validator rejected helper output: {reason}"
