#!/usr/bin/env python3
"""Tests proving the gate's failure behavior (MERGE_GATE_SPEC.md §9).

A gate that has only been observed to pass is not proven. Every row of the
acceptance matrix that the aggregation logic is responsible for gets an
explicit test that it FAILS.

Run: python3 -m pytest gate-defs/scripts/test_gate_defs.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from assert_required_jobs import evaluate  # noqa: E402
from assert_required_jobs import main as assert_main  # noqa: E402
from validate_receipt import derive_signal, validate  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
EXPECTED_JOBS = ["typecheck", "unit", "build", "evidence-preflight"]


def needs(**results):
    return {job: {"result": result} for job, result in results.items()}


def all_success():
    return needs(**{job: "success" for job in EXPECTED_JOBS})


# --------------------------------------------------------------------------
# Aggregation: the only passing case
# --------------------------------------------------------------------------

def test_all_success_passes():
    ok, problems = evaluate(all_success(), EXPECTED_JOBS)
    assert ok, problems
    assert problems == []


# --------------------------------------------------------------------------
# Acceptance matrix rows 2-6, 12: every non-success state must block
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_result", ["failure", "cancelled", "skipped", "timed_out"])
def test_any_non_success_result_blocks(bad_result):
    """Rows 2-5. GitHub reports timeouts as 'failure'; 'timed_out' is covered
    defensively in case a future result value appears."""
    context = all_success()
    context["unit"] = {"result": bad_result}
    ok, problems = evaluate(context, EXPECTED_JOBS)
    assert not ok
    assert "not successful" in " ".join(problems)


def test_skipped_job_does_not_count_as_success():
    """Row 4, called out separately: this is the specific GitHub behavior
    that silently satisfies required checks when a gate is written wrong."""
    context = all_success()
    context["evidence-preflight"] = {"result": "skipped"}
    ok, _ = evaluate(context, EXPECTED_JOBS)
    assert not ok


def test_missing_job_blocks():
    """Row 6/12. A renamed or deleted job vanishes from `needs` entirely."""
    context = all_success()
    del context["typecheck"]
    ok, problems = evaluate(context, EXPECTED_JOBS)
    assert not ok
    assert "absent from needs" in " ".join(problems)


def test_unexpected_job_blocks():
    """Row 12 inverse: a job added to needs but not to EXPECTED."""
    context = all_success()
    context["sneaky-new-job"] = {"result": "success"}
    ok, problems = evaluate(context, EXPECTED_JOBS)
    assert not ok
    assert "not in EXPECTED" in " ".join(problems)


def test_empty_needs_blocks():
    """An adapter whose `needs` resolved to nothing must not pass."""
    ok, _ = evaluate({}, EXPECTED_JOBS)
    assert not ok


def test_null_job_entry_blocks():
    ok, _ = evaluate({**all_success(), "unit": None}, EXPECTED_JOBS)
    assert not ok


# --------------------------------------------------------------------------
# Entry point fails closed on bad configuration
# --------------------------------------------------------------------------

def run_main(monkeypatch, needs_json, expected):
    monkeypatch.setenv("NEEDS_JSON", needs_json)
    monkeypatch.setenv("EXPECTED", expected)
    return assert_main()


def test_main_passes_on_clean_run(monkeypatch):
    assert run_main(monkeypatch, json.dumps(all_success()), " ".join(EXPECTED_JOBS)) == 0


def test_main_fails_on_empty_expected(monkeypatch):
    """A gate with no declared required jobs must never report success."""
    assert run_main(monkeypatch, json.dumps(all_success()), "") == 1


def test_main_fails_on_malformed_needs(monkeypatch):
    assert run_main(monkeypatch, "{not json", " ".join(EXPECTED_JOBS)) == 1


def test_main_fails_on_unset_needs(monkeypatch):
    assert run_main(monkeypatch, "", " ".join(EXPECTED_JOBS)) == 1


def test_main_fails_on_non_object_needs(monkeypatch):
    assert run_main(monkeypatch, "[]", " ".join(EXPECTED_JOBS)) == 1


def test_script_is_executable_end_to_end(tmp_path):
    """The file must actually run as a script, not just import."""
    env = {
        **os.environ,
        "NEEDS_JSON": json.dumps(all_success()),
        "EXPECTED": " ".join(EXPECTED_JOBS),
    }
    done = subprocess.run(
        [sys.executable, str(SCRIPTS / "assert_required_jobs.py")],
        env=env, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr

    env["NEEDS_JSON"] = json.dumps({**all_success(), "unit": {"result": "failure"}})
    done = subprocess.run(
        [sys.executable, str(SCRIPTS / "assert_required_jobs.py")],
        env=env, capture_output=True, text=True,
    )
    assert done.returncode == 1
    assert "::error::" in done.stdout


# --------------------------------------------------------------------------
# Receipt schema
# --------------------------------------------------------------------------

def good_receipt(**overrides):
    receipt = {
        "schema_version": "1.0.0",
        "repository": "NEO-Venturez/taxahead",
        "commit_sha": "a" * 40,
        "parent_sha": "b" * 40,
        "merged_pr": 412,
        "created_at": "2026-08-09T19:04:11Z",
        "producer": {
            "workflow": "record-evidence",
            "run_id": 987654321,
            "run_attempt": 1,
            "run_url": "https://github.com/NEO-Venturez/taxahead/actions/runs/987654321",
            "gate_ref": "v1",
        },
        "required_checks": [
            {"name": "organization-merge-gate", "conclusion": "success",
             "check_run_id": 111, "completed_at": "2026-08-09T19:01:02Z"},
            {"name": "project-required-ci", "conclusion": "success",
             "check_run_id": 112, "completed_at": "2026-08-09T19:03:40Z"},
        ],
        "stage": "BUILD",
        "outcome": "PASS",
        "signal": "BUILD_PASS",
    }
    receipt.update(overrides)
    return receipt


def test_valid_receipt_passes():
    assert validate(good_receipt()) == []


def test_signal_must_match_derivation():
    assert validate(good_receipt(signal="BUILD_FAIL")) != []


def test_derive_signal_shapes():
    assert derive_signal("BUILD", "PASS", None) == "BUILD_PASS"
    assert derive_signal("LIVE_SMOKE", "BLOCKED_EXTERNAL", "AUTH") == \
        "LIVE_SMOKE_AUTH_BLOCKED_EXTERNAL"


def test_fail_outcome_requires_failure_type():
    bad = good_receipt(outcome="FAIL", signal="BUILD_FAIL")
    assert any("requires failure_type" in e for e in validate(bad))


def test_pass_outcome_forbids_failure_type():
    bad = good_receipt(failure_type="COMPILE")
    assert any("must not carry failure_type" in e for e in validate(bad))


def test_blocked_external_requires_failure_type():
    bad = good_receipt(outcome="BLOCKED_EXTERNAL", signal="BUILD_BLOCKED_EXTERNAL")
    assert any("requires failure_type" in e for e in validate(bad))


def test_typed_failure_receipt_is_valid():
    receipt = good_receipt(
        outcome="BLOCKED_EXTERNAL",
        failure_type="ENVIRONMENT",
        stage="LIVE_SMOKE",
        signal="LIVE_SMOKE_ENVIRONMENT_BLOCKED_EXTERNAL",
        required_checks=[
            {"name": "organization-merge-gate", "conclusion": "success",
             "check_run_id": 111, "completed_at": "2026-08-09T19:01:02Z"},
            {"name": "project-required-ci", "conclusion": "failure",
             "check_run_id": 112, "completed_at": "2026-08-09T19:03:40Z"},
        ],
    )
    assert validate(receipt) == []


def test_pass_receipt_cannot_contradict_a_red_check():
    """The core anti-laundering rule: no PASS receipt over a non-success check."""
    bad = good_receipt(required_checks=[
        {"name": "organization-merge-gate", "conclusion": "success",
         "check_run_id": 111, "completed_at": "2026-08-09T19:01:02Z"},
        {"name": "project-required-ci", "conclusion": "failure",
         "check_run_id": 112, "completed_at": "2026-08-09T19:03:40Z"},
    ])
    assert any("contradicts non-success checks" in e for e in validate(bad))


def test_receipt_requires_both_named_checks():
    bad = good_receipt(required_checks=[
        {"name": "project-required-ci", "conclusion": "success",
         "check_run_id": 112, "completed_at": "2026-08-09T19:03:40Z"},
    ])
    assert validate(bad) != []


def test_unknown_check_name_rejected():
    bad = good_receipt(required_checks=[
        {"name": "organization-merge-gate", "conclusion": "success",
         "check_run_id": 111, "completed_at": "2026-08-09T19:01:02Z"},
        {"name": "project-required-ci", "conclusion": "success",
         "check_run_id": 112, "completed_at": "2026-08-09T19:03:40Z"},
        {"name": "some-other-check", "conclusion": "success",
         "check_run_id": 113, "completed_at": "2026-08-09T19:03:40Z"},
    ])
    assert validate(bad) != []


@pytest.mark.parametrize("field,value", [
    ("schema_version", "2.0.0"),
    ("repository", "no-slash"),
    ("commit_sha", "abc"),
    ("commit_sha", "A" * 40),          # uppercase is not canonical
    ("created_at", "yesterday"),
    ("stage", "NOT_A_STAGE"),
    ("outcome", "MAYBE"),
])
def test_field_validation(field, value):
    assert validate(good_receipt(**{field: value})) != []


def test_missing_required_field_rejected():
    receipt = good_receipt()
    del receipt["producer"]
    assert any("producer" in e for e in validate(receipt))


def test_unexpected_top_level_field_rejected():
    assert any("unexpected field" in e
               for e in validate(good_receipt(injected="x")))


def test_non_object_receipt_rejected():
    assert validate([]) != []
    assert validate("nope") != []


def test_spec_example_receipt_validates():
    """The example printed in MERGE_GATE_SPEC.md §5 must actually be valid."""
    spec = (SCRIPTS.parent.parent / "MERGE_GATE_SPEC.md").read_text(encoding="utf-8")
    marker = '"schema_version": "1.0.0",'
    start = spec.index(marker)
    start = spec.rindex("{", 0, start)
    depth, end = 0, None
    for idx in range(start, len(spec)):
        if spec[idx] == "{":
            depth += 1
        elif spec[idx] == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    example = json.loads(spec[start:end])
    assert validate(example) == [], validate(example)
