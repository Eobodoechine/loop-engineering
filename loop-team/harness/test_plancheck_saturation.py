"""Tests for plancheck_saturation.py.

Spec source: DESIGN_CHECKLIST.md gate 10 plus the approved spec summary for
the deterministic plan-check saturation checker.

Run with:
    python3 -m pytest loop-team/harness/test_plancheck_saturation.py -q

Written before `plancheck_saturation.py` exists. Until the Coder delivers that
module, the function-level tests intentionally fail with a clear missing-module
message and the CLI test fails because the script path is absent.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "plancheck_saturation.py")
sys.path.insert(0, HERE)

try:
    pcs = importlib.import_module("plancheck_saturation")
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - expected until Coder delivers
    pcs = None
    IMPORT_ERROR = exc


def _require_module():
    if pcs is None:
        raise AssertionError(
            "loop-team/harness/plancheck_saturation.py does not exist/import "
            "yet; these tests are expected to fail until the checker is built: "
            "%r" % (IMPORT_ERROR,)
        )


def _record(round_number, tag, signature, compiler_catchable=True,
            exclusion="none", note=None):
    return {
        "round": round_number,
        "tag": tag,
        "signature": signature,
        "compiler_catchable": compiler_catchable,
        "exclusion": exclusion,
        "note": note or ("%s note for %s" % (tag, signature)),
    }


def _round(round_number, records):
    return {"round": round_number, "records": records}


def _binding(round_number, signature="missing_import:CalendarPanel",
             compiler_catchable=True, exclusion="none", note=None):
    return _record(round_number, "BINDING", signature, compiler_catchable,
                   exclusion, note)


def _strict_record(round_number, tag="BINDING",
                   signature="binding:missing-import:CalendarPanel",
                   compiler_catchable=True, exclusion="none"):
    return {
        "schema_version": 1,
        "record_type": "plan_check_gap",
        "run_id": "strict-mode-test",
        "round": round_number,
        "lens": "regression-audit",
        "tag": tag,
        "gap_type": "DESIGN",
        "signature": signature,
        "broken_assumption": "Compiler-visible binding defect recurred.",
        "why_it_fails": "The app cannot compile while this binding is missing.",
        "proposed_fix": "Restore the missing binding.",
        "touches": ["AC1"],
        "mechanism_refs": [],
        "compiler_catchable": compiler_catchable,
        "exclusion": exclusion,
        "note": "strict note %s" % round_number,
    }


def _logic(round_number, signature="logic:unguarded_exception"):
    return _record(round_number, "LOGIC", signature, compiler_catchable=False)


def _evaluate(rounds):
    _require_module()
    if not hasattr(pcs, "evaluate_records"):
        raise AssertionError(
            "plancheck_saturation.py must expose evaluate_records(rounds)"
        )
    result = pcs.evaluate_records(rounds)
    assert isinstance(result, dict), "evaluate_records must return a dict"
    assert "verdict" in result, "result must include verdict"
    assert "reasons" in result, "result must include reasons"
    assert "coder_notes" in result, "result must include coder_notes"
    return result


def _assert_verdict(result, expected):
    assert result["verdict"] == expected, json.dumps(result, sort_keys=True)


def test_stop_only_on_last_three_consecutive_same_binding_signature():
    rounds = [
        _round(1, [_binding(1)]),
        _round(2, [_binding(2)]),
        _round(3, [_binding(3)]),
    ]

    result = _evaluate(rounds)

    _assert_verdict(result, "STOP_PROSE_REVIEW")
    assert "CalendarPanel" in " ".join(result["coder_notes"])


@pytest.mark.parametrize("tag", ["LOGIC", "CONCURRENCY", "SECURITY"])
def test_any_non_binding_tag_in_three_round_window_continues(tag):
    rounds = [
        _round(1, [_binding(1)]),
        _round(2, [
            _binding(2),
            _record(2, tag, "%s:real_bug" % tag.lower(),
                    compiler_catchable=False),
        ]),
        _round(3, [_binding(3)]),
    ]

    result = _evaluate(rounds)

    _assert_verdict(result, "CONTINUE_PLAN_CHECK")


@pytest.mark.parametrize(
    "exclusion",
    ["exception_handling", "data_wiring", "ui_default"],
)
def test_gate10_exclusions_make_binding_tagging_invalid(exclusion):
    rounds = [
        _round(1, [_binding(1)]),
        _round(2, [_binding(2, exclusion=exclusion)]),
        _round(3, [_binding(3)]),
    ]

    result = _evaluate(rounds)

    _assert_verdict(result, "INVALID_TAGGING")


def test_unrelated_binding_signatures_do_not_combine_to_stop():
    rounds = [
        _round(1, [_binding(1, "missing_import:CalendarPanel")]),
        _round(2, [_binding(2, "missing_use_client:DashboardShell")]),
        _round(3, [_binding(3, "undeclared_identifier:propertyId")]),
    ]

    result = _evaluate(rounds)

    _assert_verdict(result, "CONTINUE_PLAN_CHECK")


def test_extra_binding_signature_in_stop_window_not_silently_dropped():
    extra_note = "carry forward missing_use_client DashboardShell"
    rounds = [
        _round(1, [_binding(1)]),
        _round(2, [
            _binding(2),
            _binding(2, "missing_use_client:DashboardShell",
                     note=extra_note),
        ]),
        _round(3, [_binding(3)]),
    ]

    result = _evaluate(rounds)

    if result["verdict"] == "STOP_PROSE_REVIEW":
        coder_notes = "\n".join(result["coder_notes"])
        assert extra_note in coder_notes
        assert "missing_use_client:DashboardShell" in coder_notes
    else:
        _assert_verdict(result, "CONTINUE_PLAN_CHECK")


def test_non_compiler_catchable_binding_does_not_stop():
    rounds = [
        _round(1, [_binding(1)]),
        _round(2, [_binding(2, compiler_catchable=False)]),
        _round(3, [_binding(3)]),
    ]

    result = _evaluate(rounds)

    _assert_verdict(result, "INVALID_TAGGING")


def test_cli_accepts_jsonl_path_and_prints_machine_readable_json(tmp_path):
    path = tmp_path / "plancheck.jsonl"
    rounds = [
        _round(1, [_binding(1)]),
        _round(2, [_binding(2)]),
        _round(3, [_binding(3)]),
    ]
    path.write_text(
        "".join(json.dumps(round_) + "\n" for round_ in rounds),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, SCRIPT, str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0, (
        "stdout=%r stderr=%r" % (proc.stdout, proc.stderr)
    )
    payload = json.loads(proc.stdout)
    assert payload["verdict"] == "STOP_PROSE_REVIEW"
    assert isinstance(payload.get("reasons"), list)
    assert isinstance(payload.get("coder_notes"), list)


def test_cli_strict_records_validates_schema_and_evaluates(tmp_path):
    path = tmp_path / "plan_check_records.jsonl"
    records = [_strict_record(1), _strict_record(2), _strict_record(3)]
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, SCRIPT, "--strict-records", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0, (
        "stdout=%r stderr=%r" % (proc.stdout, proc.stderr)
    )
    payload = json.loads(proc.stdout)
    assert payload["verdict"] == "STOP_PROSE_REVIEW"
    assert "strict note 3" in "\n".join(payload["coder_notes"])


def test_cli_strict_records_rejects_legacy_round_summary_shape(tmp_path):
    path = tmp_path / "plan_check_records.jsonl"
    path.write_text(json.dumps(_round(1, [_binding(1)])) + "\n",
                    encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, SCRIPT, "--strict-records", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 2
    assert "UNSUPPORTED_ROUND_SUMMARY_SHAPE" in proc.stderr
