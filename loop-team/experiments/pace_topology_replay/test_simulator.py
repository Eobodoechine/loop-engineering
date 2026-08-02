"""Regression oracle for the bounded PACE topology replay.

The tests intentionally exercise the public simulator contract rather than the
generated fixtures.  Source transcripts are the authority; generated JSON is
only a reproducible projection of those sources.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _api():
    return importlib.import_module("simulator")


def _write_source(path: Path) -> Path:
    records = [
        {"timestamp": "2026-07-31T00:00:00.000Z", "type": "session_meta", "payload": {"id": "session-1"}},
        {"timestamp": "2026-07-31T00:00:01.000Z", "type": "response_item", "payload": {"type": "function_call", "id": "fc-1", "name": "spawn_agent", "call_id": "call-shared", "arguments": "{}"}},
        {"timestamp": "2026-07-31T00:00:01.100Z", "type": "response_item", "payload": {"type": "function_call_output", "id": "fco-1", "call_id": "call-shared", "output": "{}"}},
        {"timestamp": "2026-07-31T00:00:02.000Z", "type": "response_item", "payload": {"type": "function_call", "id": "fc-2", "name": "wait_agent", "call_id": "call-wait", "arguments": "{\"timeout_ms\":10000}"}},
        {"timestamp": "2026-07-31T00:00:12.000Z", "type": "response_item", "payload": {"type": "function_call_output", "id": "fco-2", "call_id": "call-wait", "output": "{\"timed_out\":true}"}},
    ]
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    return path


def _graph(root_dispatch: bool = True, leaf_dispatch: bool = False):
    edges = [{"source": "root", "target": "worker", "kind": "dispatch"}] if root_dispatch else []
    if leaf_dispatch:
        edges.append({"source": "worker", "target": "nested", "kind": "dispatch"})
    return {
        "nodes": [
            {"id": "root", "role": "scheduler", "parent": None},
            {"id": "worker", "role": "coder", "parent": "root"},
            {"id": "nested", "role": "coder", "parent": "worker"},
            {"id": "verifier", "role": "verifier", "parent": "root"},
        ],
        "edges": edges,
    }


def test_pointer_requires_full_file_hash_index_record_hash_and_native_id(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    record = json.loads(source.read_text().splitlines()[1])
    pointer = api.make_pointer(source, 2, record)
    assert set(("source_sha256", "record_index", "record_sha256", "native_id")) <= set(pointer)
    for key in ("source_sha256", "record_sha256"):
        assert len(pointer[key]) == 64
    for key in ("source_sha256", "record_index", "record_sha256", "native_id"):
        broken = dict(pointer)
        broken.pop(key)
        with pytest.raises(api.EvidenceError):
            api.verify_pointer(broken, source)


def test_record_indexes_are_one_based(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    record = json.loads(source.read_text().splitlines()[0])
    with pytest.raises(api.EvidenceError):
        api.make_pointer(source, 0, record)
    assert api.make_pointer(source, 1, record)["record_index"] == 1


def test_same_call_id_start_and_output_are_distinct_evidence(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    start = api.make_pointer(source, 2, rows[1])
    output = api.make_pointer(source, 3, rows[2])
    assert start["native_id"] == output["native_id"] == "call-shared"
    assert start["record_index"] != output["record_index"]
    assert start["record_sha256"] != output["record_sha256"]
    api.verify_evidence_index([start, output], {str(source): source})


def test_source_file_drift_rejects(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    row = json.loads(source.read_text().splitlines()[1])
    pointer = api.make_pointer(source, 2, row)
    source.write_text(source.read_text() + "{}\n", encoding="utf-8")
    with pytest.raises(api.EvidenceError):
        api.verify_pointer(pointer, source)


def test_hand_edited_pointer_hash_rejects(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    row = json.loads(source.read_text().splitlines()[1])
    pointer = api.make_pointer(source, 2, row)
    pointer["record_sha256"] = "0" * 64
    with pytest.raises(api.EvidenceError):
        api.verify_pointer(pointer, source)


def test_missing_record_rejects(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    row = json.loads(source.read_text().splitlines()[1])
    pointer = api.make_pointer(source, 2, row)
    pointer["record_index"] = 999
    with pytest.raises(api.EvidenceError):
        api.verify_pointer(pointer, source)


def test_duplicate_evidence_pointer_rejects(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    row = json.loads(source.read_text().splitlines()[1])
    pointer = api.make_pointer(source, 2, row)
    with pytest.raises(api.EvidenceError):
        api.verify_evidence_index([pointer, dict(pointer)], {str(source): source})


def test_baseline_counts_are_recomputed_from_source(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    case = api.extract_case(source, "case-1")
    assert case["baseline"]["function_calls"] == 2
    assert case["baseline"]["wait_or_poll_calls"] == 1
    case["baseline"]["function_calls"] = 999
    assert api.extract_case(source, "case-1")["baseline"]["function_calls"] == 2


def test_leaf_nested_dispatch_is_rejected():
    result = _api().evaluate_topology(_graph(leaf_dispatch=True))
    assert result["allowed"] is False
    assert "leaf_nested_dispatch" in result["violations"]


def test_root_dispatch_is_allowed():
    result = _api().evaluate_topology(_graph())
    assert result["allowed"] is True


def test_framework_failure_is_quarantined():
    result = _api().evaluate_topology(_graph(), framework_failure=True)
    assert result["quarantined"] is True
    assert result["product_failure"] is False


def test_failed_preflight_blocks_worker_dispatch():
    result = _api().evaluate_topology(_graph(), preflight_passed=False)
    assert result["worker_dispatch_blocked"] is True
    assert result["allowed"] is False


def test_reporting_graph_has_no_coder():
    result = _api().evaluate_topology(_graph())
    assert all(node["role"] != "coder" for node in result["reporting_graph"]["nodes"])


def test_independent_verification_is_retained():
    result = _api().evaluate_topology(_graph())
    assert any(node["role"] == "verifier" for node in result["reporting_graph"]["nodes"])
    assert result["independent_verification_retained"] is True


def test_poll_and_heartbeat_removal_reduces_actions_not_duration():
    api = _api()
    case = {"baseline": {"function_calls": 10, "wait_or_poll_calls": 3, "heartbeat_calls": 2}, "safety": {"passed": True}, "timing": {"active_spans": []}}
    result = api.simulate_case(case)
    assert result["action_savings"] == 5
    assert result["poll_block_duration_saved_ms"] == 0
    assert result["time_savings_ms"] is None


def test_active_processing_uses_critical_path_union_and_variant_overhead():
    api = _api()
    timing = {
        "active_spans": [
            {"start_ms": 0, "end_ms": 100, "critical_path": True, "baseline_only": True},
            {"start_ms": 50, "end_ms": 150, "critical_path": True, "baseline_only": True},
            {"start_ms": 90, "end_ms": 120, "critical_path": True, "retained": True},
            {"start_ms": 0, "end_ms": 999, "critical_path": False, "baseline_only": True},
        ],
        "variant_overhead_ms": 10,
    }
    assert api.active_processing_savings(timing) == 110


def test_missing_lifecycle_endpoint_is_unmeasurable():
    api = _api()
    timing = {"active_spans": [{"start_ms": 10, "end_ms": None, "critical_path": True, "baseline_only": True}], "variant_overhead_ms": 0}
    assert api.active_processing_savings(timing) is None


def test_faster_but_unsafe_variant_rejects():
    api = _api()
    case = {"baseline": {"function_calls": 10, "wait_or_poll_calls": 1, "heartbeat_calls": 0}, "safety": {"passed": False}, "timing": {"active_spans": [{"start_ms": 0, "end_ms": 1000, "critical_path": True, "baseline_only": True}], "variant_overhead_ms": 0}}
    result = api.simulate_case(case)
    assert result["time_savings_ms"] == 1000
    assert result["simulation_verdict"] == "REJECT_UNSAFE"


def test_simulation_verdict_is_separate_from_timing_result():
    api = _api()
    case = {"baseline": {"function_calls": 5, "wait_or_poll_calls": 1, "heartbeat_calls": 0}, "safety": {"passed": True}, "timing": {"active_spans": []}}
    result = api.simulate_case(case)
    assert result["simulation_verdict"] == "SIMULATION_PASS"
    assert result["timing_result"] == "INSUFFICIENT_TELEMETRY"


def test_five_non_iid_replays_never_produce_statistical_or_adoption_verdict():
    api = _api()
    results = [{"simulation_verdict": "SIMULATION_PASS", "timing_result": "INSUFFICIENT_TELEMETRY", "action_savings": 1}] * 5
    score = api.score_results(results)
    assert score["case_count"] == 5
    assert score["statistical_verdict"] == "NOT_APPLICABLE"
    assert score["adoption_verdict"] == "NOT_APPLICABLE"
    assert score["pace_acceptance"] is False


def test_source_seal_allows_only_append_after_frozen_prefix(tmp_path):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    seal = api.create_source_seal(source, "case-1", 1)
    assert api.verify_source_seal(seal, source) == "SEALED_EXACT"
    source.write_text(source.read_text() + json.dumps({"type": "event_msg", "payload": {"id": "later"}}) + "\n")
    assert api.verify_source_seal(seal, source) == "APPENDED_AFTER_SEAL"


@pytest.mark.parametrize("mode", ["mutate", "reorder", "delete", "truncate"])
def test_source_seal_rejects_prefix_mutation_reorder_delete_and_truncate(tmp_path, mode):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    seal = api.create_source_seal(source, "case-1", 1)
    lines = source.read_bytes().splitlines(keepends=True)
    if mode == "mutate":
        lines[1] = lines[1].replace(b"fc-1", b"fc-X")
    elif mode == "reorder":
        lines[1], lines[2] = lines[2], lines[1]
    elif mode == "delete":
        del lines[1]
    else:
        lines = lines[:-1]
    source.write_bytes(b"".join(lines))
    with pytest.raises(api.EvidenceError):
        api.verify_source_seal(seal, source)


@pytest.mark.parametrize("field,value", [
    ("extracted_record_count", 4),
    ("sealed_prefix_raw_sha256", "0" * 64),
    ("manifest_version", 2),
])
def test_source_seal_rejects_edited_count_hash_or_version(tmp_path, field, value):
    api = _api()
    source = _write_source(tmp_path / "source.jsonl")
    seal = api.create_source_seal(source, "case-1", 1)
    seal[field] = value
    with pytest.raises(api.EvidenceError):
        api.verify_source_seal(seal, source)


def test_wait_only_source_backed_case_cannot_simulation_pass(tmp_path):
    """Historical cases need positive topology proof, not a hardcoded safety flag."""
    api = _api()
    source = tmp_path / "wait-only.jsonl"
    rows = [
        {"timestamp": "2026-08-02T00:00:00Z", "type": "session_meta", "payload": {"id": "wait-session"}},
        {"timestamp": "2026-08-02T00:00:01Z", "type": "response_item", "payload": {"type": "function_call", "id": "fc-wait", "name": "wait_agent", "call_id": "call-wait", "arguments": "{\"timeout_ms\":10000}"}},
        {"timestamp": "2026-08-02T00:00:11Z", "type": "response_item", "payload": {"type": "function_call_output", "id": "fco-wait", "call_id": "call-wait", "output": "{\"timed_out\":true}"}},
    ]
    source.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    seal = api.create_source_seal(source, "wait-only", 1)
    case = api.extract_case(source, "wait-only", source_seal=seal)
    result = api.simulate_case(case)
    assert case["source_backed"] is True
    assert case["topology_actions"] == []
    assert result["safety_status"] == "UNMEASURABLE"
    assert result["simulation_verdict"] != "SIMULATION_PASS"


@pytest.mark.parametrize("text", [
    "Independent verdict: NOT PASS.",
    "FAIL overall",
    "FALSE-PASS",
    "PLAN_FAIL",
    "provisional_verdict: FAIL",
    "Focused-test PASS",
    "LOOP_GATE: PLAN_PASS\nFAIL overall",
    "FAIL overall\nLOOP_GATE: PLAN_PASS",
    "VERDICT: PASS\nprovisional_verdict: FAIL",
])
def test_authoritative_pass_parser_rejects_negative_incidental_and_mixed_text(text):
    assert _api()._positive_pass(text) is False


@pytest.mark.parametrize("text", [
    "LOOP_GATE: PLAN_PASS",
    "Supporting evidence complete.\nLOOP_GATE: PLAN_PASS",
    "VERDICT: PASS",
    "Supporting evidence complete.\nVERDICT: PASS",
])
def test_authoritative_pass_parser_accepts_only_strict_terminal_forms(text):
    assert _api()._positive_pass(text) is True


@pytest.mark.parametrize("text", [
    "VERDICT: FAIL\nVERDICT: PASS",
    "Independent verdict: FAIL\nVERDICT: PASS",
    "Summary: NOT PASS\nVERDICT: PASS",
    "Independent audit: FAIL overall\nLOOP_GATE: PLAN_PASS",
    "REJECT_UNSAFE\nVERDICT: PASS",
    "final-verdict = failed\nVERDICT: PASS",
    "STATUS: NOT_PASS\nLOOP_GATE: PLAN_PASS",
    "overall: fail\nVERDICT: PASS",
    "result: rejected\nLOOP_GATE: PLAN_PASS",
    "reject-unsafe\nVERDICT: PASS",
])
def test_authoritative_pass_parser_rejects_complete_explicit_negative_class(text):
    assert _api()._positive_pass(text) is False


@pytest.mark.parametrize("text", [
    "**VERDICT:** FAIL\nVERDICT: PASS",
    "**STATUS:** NOT PASS\nLOOP_GATE: PLAN_PASS",
    "- **overall:** failed\nVERDICT: PASS",
    "* __VERDICT:__ rejected\nVERDICT: PASS",
    "+ `STATUS:` NOT_PASS\nLOOP_GATE: PLAN_PASS",
    "1. **RESULT:** reject-unsafe\nVERDICT: PASS",
])
def test_authoritative_pass_parser_rejects_markdown_decorated_negative_keys(text):
    assert _api()._positive_pass(text) is False
