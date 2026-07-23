"""Tests for strict plan_check_records.jsonl schema helper."""

import importlib
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "plan_check_records.py")
sys.path.insert(0, HERE)

pcr = importlib.import_module("plan_check_records")


def _record(**overrides):
    record = {
        "schema_version": 1,
        "record_type": "plan_check_gap",
        "run_id": "2026-07-11-example",
        "round": 2,
        "lens": "regression-audit",
        "tag": "LOGIC",
        "gap_type": "DESIGN",
        "signature": "logic:filtered-count-after-drop",
        "broken_assumption": "AC7 checks the count before filtering.",
        "why_it_fails": "The check runs after filtering drops rows.",
        "proposed_fix": "Assert source count before applying filters.",
        "touches": ["AC7"],
        "mechanism_refs": [],
    }
    record.update(overrides)
    return record


def test_valid_strict_record_has_stable_record_id_despite_key_order():
    a = _record(touches=[" AC7 ", "AC7"])
    b = {
        "signature": "logic:filtered-count-after-drop",
        "gap_type": "design",
        "tag": "logic",
        "lens": " regression-audit ",
        "round": "2",
        "run_id": "2026-07-11-example",
        "record_type": "plan_check_gap",
        "schema_version": 1,
        "broken_assumption": "AC7 checks the count before filtering.",
        "why_it_fails": "The check runs after filtering drops rows.",
        "proposed_fix": "Assert source count before applying filters.",
        "mechanism_refs": [],
        "touches": ["AC7"],
    }

    assert pcr.validate_record(a) == []
    assert pcr.validate_record(b) == []
    assert pcr.record_id(a) == pcr.record_id(b)


@pytest.mark.parametrize(
    "bad_record,expected",
    [
        ({"round": 1, "records": []}, "UNSUPPORTED_ROUND_SUMMARY_SHAPE"),
        (
            {
                "round": 1,
                "tag": "LOGIC",
                "signature": "logic:x",
            },
            "missing required field schema_version",
        ),
        (_record(signature=""), "signature must be non-empty"),
        (_record(tag="PERFORMANCE"), "tag must be one of"),
        (_record(gap_type="MAYBE"), "gap_type must be one of"),
        (_record(round=0), "round must be an integer >= 1"),
    ],
)
def test_invalid_shapes_are_rejected(bad_record, expected):
    errors = pcr.validate_record(bad_record)

    assert any(expected in error for error in errors), errors


def test_binding_requires_compiler_catchable_and_rejects_invisible_exclusion():
    missing_compiler = _record(
        tag="BINDING",
        signature="binding:missing-import:CalendarPanel",
    )
    invisible = _record(
        tag="BINDING",
        signature="binding:data-wiring",
        compiler_catchable=True,
        exclusion="data_wiring",
    )

    assert any(
        "compiler_catchable=true" in error
        for error in pcr.validate_record(missing_compiler)
    )
    assert any(
        "compiler-invisible" in error
        for error in pcr.validate_record(invisible)
    )


def test_load_jsonl_rejects_mixed_legacy_shapes(tmp_path):
    path = tmp_path / "plan_check_records.jsonl"
    path.write_text(
        json.dumps(_record()) + "\n" +
        json.dumps({"round": 2, "records": []}) + "\n",
        encoding="utf-8",
    )

    records, errors = pcr.load_jsonl(str(path))

    assert len(records) == 1
    assert any("UNSUPPORTED_ROUND_SUMMARY_SHAPE" in error for error in errors)


def test_to_saturation_records_converts_strict_shape():
    record = _record(
        tag="BINDING",
        signature="binding:missing-import:CalendarPanel",
        compiler_catchable=True,
        exclusion="none",
        note="carry forward missing import",
    )

    converted = pcr.to_saturation_records([record])

    assert converted == [{
        "round": 2,
        "tag": "BINDING",
        "signature": "binding:missing-import:CalendarPanel",
        "compiler_catchable": True,
        "exclusion": "none",
        "note": "carry forward missing import",
    }]


def test_cli_validate_exits_zero_for_valid_jsonl(tmp_path):
    path = tmp_path / "plan_check_records.jsonl"
    path.write_text(json.dumps(_record()) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, SCRIPT, "validate", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(proc.stdout)

    assert proc.returncode == 0
    assert payload["valid"] is True
    assert payload["record_count"] == 1
    assert len(payload["record_ids"]) == 1


def test_cli_validate_exits_nonzero_for_legacy_shape(tmp_path):
    path = tmp_path / "plan_check_records.jsonl"
    path.write_text(json.dumps({"round": 1, "records": []}) + "\n",
                    encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, SCRIPT, "validate", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(proc.stdout)

    assert proc.returncode == 2
    assert payload["valid"] is False
    assert any("UNSUPPORTED_ROUND_SUMMARY_SHAPE" in e for e in payload["errors"])


def test_cli_saturation_records_outputs_flat_records_for_existing_checker(tmp_path):
    path = tmp_path / "plan_check_records.jsonl"
    path.write_text(
        json.dumps(_record(
            tag="BINDING",
            signature="binding:missing-import:CalendarPanel",
            compiler_catchable=True,
        )) + "\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, SCRIPT, "saturation-records", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(proc.stdout)

    assert proc.returncode == 0
    assert payload[0]["tag"] == "BINDING"
    assert payload[0]["signature"] == "binding:missing-import:CalendarPanel"
