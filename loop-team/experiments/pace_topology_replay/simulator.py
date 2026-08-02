"""Deterministic, source-grounded topology replay primitives.

This module does not run agents and does not claim causal wall-clock savings.
It projects immutable Codex JSONL records into auditable action counts and
conservatively marks unsupported timing as unmeasurable.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


POLL_CALLS = frozenset({"wait_agent", "wait_threads", "wait"})
HEARTBEAT_CALLS = frozenset({"list_agents", "list_threads"})
DISPATCH_CALLS = frozenset({"spawn_agent", "create_thread", "followup_task"})


class EvidenceError(ValueError):
    """Raised when a source-backed evidence pointer does not verify."""


_SOURCE_CACHE: dict[str, tuple[tuple[int, int], str, list[dict[str, Any]]]] = {}


def canonical_record_bytes(record: Mapping[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_record_sha(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_record_bytes(record)).hexdigest()


def file_sha256(path: str | Path) -> str:
    source = Path(path).resolve()
    stat = source.stat()
    signature = (stat.st_size, stat.st_mtime_ns)
    cached = _SOURCE_CACHE.get(str(source))
    if cached is not None and cached[0] == signature:
        return cached[1]
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    if cached is not None:
        _SOURCE_CACHE.pop(str(source), None)
    return value


def _native_id(record: Mapping[str, Any]) -> str:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise EvidenceError("record has no payload object")
    native_id = payload.get("call_id") or payload.get("id") or payload.get("turn_id") or payload.get("event_id")
    if not isinstance(native_id, str) or not native_id:
        raise EvidenceError("record has no native call/message id")
    return native_id


def make_pointer(
    source_path: str | Path,
    record_index: int,
    record: Mapping[str, Any],
    source_sha256: str | None = None,
) -> dict[str, Any]:
    source = Path(source_path).resolve()
    if not isinstance(record_index, int) or record_index < 1:
        raise EvidenceError("record_index must be one-based")
    payload = record.get("payload", {})
    return {
        "source_path": str(source),
        "source_sha256": source_sha256 or file_sha256(source),
        "record_index": record_index,
        "record_sha256": canonical_record_sha(record),
        "native_id": _native_id(record),
        "record_kind": payload.get("type", record.get("type", "unknown")),
    }


def seal_binding_sha256(seal: Mapping[str, Any]) -> str:
    payload = {
        "case_id": seal["case_id"],
        "extracted_record_count": seal["extracted_record_count"],
        "manifest_version": seal["manifest_version"],
        "sealed_prefix_raw_sha256": seal["sealed_prefix_raw_sha256"],
        "source_path": str(Path(str(seal["source_path"])).resolve()),
    }
    return hashlib.sha256(canonical_record_bytes(payload)).hexdigest()


def _raw_records(source_path: str | Path) -> list[bytes]:
    return Path(source_path).resolve().read_bytes().splitlines(keepends=True)


def create_source_seal(
    source_path: str | Path,
    case_id: str,
    manifest_version: int,
    record_count: int | None = None,
) -> dict[str, Any]:
    source = Path(source_path).resolve()
    raw_records = _raw_records(source)
    count = len(raw_records) if record_count is None else record_count
    if not isinstance(count, int) or count < 1 or count > len(raw_records):
        raise EvidenceError("invalid extracted_record_count")
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_records[:count], start=1):
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceError(f"malformed sealed source record at index {index}") from exc
        if not isinstance(record, dict):
            raise EvidenceError(f"non-object sealed source record at index {index}")
        records.append(record)
    seal: dict[str, Any] = {
        "case_id": case_id,
        "source_path": str(source),
        "manifest_version": manifest_version,
        "extracted_record_count": count,
        "sealed_prefix_raw_sha256": hashlib.sha256(b"".join(raw_records[:count])).hexdigest(),
        "record_sha256": [canonical_record_sha(record) for record in records],
    }
    seal["seal_binding_sha256"] = seal_binding_sha256(seal)
    return seal


def verify_source_seal(seal: Mapping[str, Any], source_path: str | Path | None = None) -> str:
    required = {
        "case_id", "source_path", "manifest_version", "extracted_record_count",
        "sealed_prefix_raw_sha256", "seal_binding_sha256",
    }
    if not required.issubset(seal):
        raise EvidenceError(f"source seal missing fields: {sorted(required - set(seal))}")
    if seal_binding_sha256(seal) != seal["seal_binding_sha256"]:
        raise EvidenceError("source seal binding mismatch")
    source = Path(source_path or str(seal["source_path"])).resolve()
    if source != Path(str(seal["source_path"])).resolve():
        raise EvidenceError("source seal path mismatch")
    raw_records = _raw_records(source)
    count = seal["extracted_record_count"]
    if not isinstance(count, int) or count < 1:
        raise EvidenceError("invalid extracted_record_count")
    if len(raw_records) < count:
        raise EvidenceError("sealed source was deleted or truncated")
    prefix = raw_records[:count]
    if hashlib.sha256(b"".join(prefix)).hexdigest() != seal["sealed_prefix_raw_sha256"]:
        raise EvidenceError("sealed source prefix mutated or reordered")
    declared_records = seal.get("record_sha256")
    if declared_records is not None:
        if not isinstance(declared_records, list) or len(declared_records) != count:
            raise EvidenceError("per-record seal count mismatch")
        for index, (raw, expected) in enumerate(zip(prefix, declared_records), start=1):
            try:
                record = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise EvidenceError(f"malformed sealed source record at index {index}") from exc
            if canonical_record_sha(record) != expected:
                raise EvidenceError(f"canonical record seal mismatch at index {index}")
    return "APPENDED_AFTER_SEAL" if len(raw_records) > count else "SEALED_EXACT"


def _read_source(source_path: str | Path) -> list[dict[str, Any]]:
    source = Path(source_path).resolve()
    stat = source.stat()
    signature = (stat.st_size, stat.st_mtime_ns)
    cached = _SOURCE_CACHE.get(str(source))
    if cached is not None and cached[0] == signature:
        return cached[2]
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    with source.open("rb") as raw:
        data = raw.read()
    digest.update(data)
    text = data.decode("utf-8")
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise EvidenceError(f"blank source record at index {index}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"malformed source record at index {index}") from exc
        if not isinstance(row, dict):
            raise EvidenceError(f"non-object source record at index {index}")
        rows.append(row)
    _SOURCE_CACHE[str(source)] = (signature, digest.hexdigest(), rows)
    return rows


def verify_pointer(
    pointer: Mapping[str, Any],
    source_path: str | Path | None = None,
    seal: Mapping[str, Any] | None = None,
    _seal_verified: bool = False,
) -> dict[str, Any]:
    required = {"source_path", "source_sha256", "record_index", "record_sha256", "native_id"}
    if not required.issubset(pointer):
        raise EvidenceError(f"pointer missing fields: {sorted(required - set(pointer))}")
    source = Path(source_path or str(pointer["source_path"])).resolve()
    if str(source) != str(Path(str(pointer["source_path"])).resolve()):
        raise EvidenceError("pointer source path mismatch")
    if seal is None:
        if file_sha256(source) != pointer["source_sha256"]:
            raise EvidenceError("source file hash mismatch")
    else:
        if not _seal_verified:
            verify_source_seal(seal, source)
        if pointer["source_sha256"] != seal["sealed_prefix_raw_sha256"]:
            raise EvidenceError("pointer does not reference sealed prefix hash")
    index = pointer["record_index"]
    if not isinstance(index, int) or index < 1:
        raise EvidenceError("record_index must be one-based")
    if seal is not None and index > int(seal["extracted_record_count"]):
        raise EvidenceError("pointer is after sealed prefix")
    rows = _read_source(source)
    if index > len(rows):
        raise EvidenceError("evidence record is missing")
    record = rows[index - 1]
    if canonical_record_sha(record) != pointer["record_sha256"]:
        raise EvidenceError("canonical record hash mismatch")
    if _native_id(record) != pointer["native_id"]:
        raise EvidenceError("native id mismatch")
    return record


def verify_evidence_index(
    pointers: Iterable[Mapping[str, Any]],
    sources: Mapping[str, str | Path] | None = None,
    seals: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    if seals:
        for seal in seals.values():
            verify_source_seal(seal)
    seen: set[tuple[str, int, str]] = set()
    call_starts: dict[tuple[str, str], int] = {}
    outputs: list[tuple[str, str, int]] = []
    for pointer in pointers:
        source_path = str(pointer.get("source_path", ""))
        resolved = sources.get(source_path, source_path) if sources else source_path
        seal = seals.get(source_path) if seals else None
        record = verify_pointer(pointer, resolved, seal=seal, _seal_verified=seal is not None)
        identity = (str(pointer["source_sha256"]), int(pointer["record_index"]), str(pointer["record_sha256"]))
        if identity in seen:
            raise EvidenceError("duplicate evidence pointer identity")
        seen.add(identity)
        kind = record.get("payload", {}).get("type")
        key = (str(Path(source_path).resolve()), str(pointer["native_id"]))
        if kind == "function_call":
            call_starts[key] = int(pointer["record_index"])
        elif kind == "function_call_output":
            outputs.append((key[0], key[1], int(pointer["record_index"])))
    for source, native_id, output_index in outputs:
        start_index = call_starts.get((source, native_id))
        if start_index is None or start_index >= output_index:
            raise EvidenceError("function output lacks an earlier matching start pointer")


def _is_function_call(record: Mapping[str, Any]) -> bool:
    return record.get("type") == "response_item" and record.get("payload", {}).get("type") == "function_call"


def _task_stage(task_path: str) -> str:
    name = task_path.rsplit("/", 1)[-1].lower()
    if any(token in name for token in ("framework", "guard_repair", "failure_arbiter", "loop_framework")):
        return "framework_repair"
    if any(token in name for token in ("plancheck", "plan_check", "plan-check", "plan_verifier")):
        return "preflight"
    if any(token in name for token in ("verifier", "reviewer", "validator", "audit", "critic")):
        return "verifier"
    if any(token in name for token in ("coder", "implement", "execution", "repair")):
        return "coder"
    return "worker"


def _message_text(payload: Mapping[str, Any]) -> str:
    content = payload.get("content", [])
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(item.get("text", ""))
        for item in content
        if isinstance(item, Mapping) and item.get("type") in {"input_text", "output_text"}
    )


def _positive_pass(text: str) -> bool:
    """Recognize only authoritative positive terminals, with no negative verdict."""
    normalized_lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:(?:[-+*])|(?:\d+[.)]))\s+", "", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        normalized_lines.append(line)
    negative_text = "\n".join(normalized_lines)
    separator = r"[\s_-]+"
    key = rf"(?:(?:INDEPENDENT|FINAL|PROVISIONAL){separator})?(?:VERDICT|STATUS|RESULT|SUMMARY|AUDIT|OVERALL)"
    negative_value = rf"(?:FAIL(?:ED)?(?:{separator}OVERALL)?|NOT{separator}PASS|REJECT(?:ED)?(?:{separator}UNSAFE)?)"
    negative_verdicts = (
        r"\bPLAN[\s_-]*FAIL\b",
        r"\bFALSE[\s_-]+PASS\b",
        rf"(?im)^\s*(?:[-*]\s*)?{key}\s*[:=]\s*{negative_value}\b",
        rf"(?im)^\s*(?:[-*]\s*)?FAIL(?:ED)?{separator}OVERALL\b",
        rf"(?im)^\s*(?:[-*]\s*)?REJECT(?:ED)?{separator}UNSAFE\b",
    )
    if any(re.search(pattern, negative_text, flags=re.IGNORECASE | re.MULTILINE) for pattern in negative_verdicts):
        return False
    terminal = text.rstrip()
    return bool(
        re.search(r"(?:^|[|\n])\s*`?LOOP_GATE\s*:\s*PLAN_PASS`?\s*$", terminal, flags=re.IGNORECASE)
        or re.search(r"(?:^|\n)\s*`?VERDICT\s*:\s*PASS`?\s*$", terminal, flags=re.IGNORECASE)
    )


def extract_case(
    source_path: str | Path,
    case_id: str,
    *,
    source_seal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute one replay case directly from its immutable source transcript."""
    source = Path(source_path).resolve()
    rows = _read_source(source)
    source_hash = file_sha256(source)
    if source_seal is not None:
        verify_source_seal(source_seal, source)
        rows = rows[: int(source_seal["extracted_record_count"])]
        source_hash = str(source_seal["sealed_prefix_raw_sha256"])
    calls: list[tuple[int, dict[str, Any]]] = [
        (index, row) for index, row in enumerate(rows, start=1) if _is_function_call(row)
    ]
    outputs_by_call: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, row in enumerate(rows, start=1):
        payload = row.get("payload", {})
        if row.get("type") == "response_item" and payload.get("type") == "function_call_output" and payload.get("call_id"):
            outputs_by_call[str(payload["call_id"])] = (index, row)

    pointers: list[dict[str, Any]] = []
    action_pointers: list[dict[str, Any]] = []
    pointer_by_index: dict[int, dict[str, Any]] = {}
    for index, row in calls:
        start = make_pointer(source, index, row, source_sha256=source_hash)
        pointers.append(start)
        pointer_by_index[index] = start
        action_pointers.append(start)
        paired = outputs_by_call.get(str(row.get("payload", {}).get("call_id", "")))
        if paired is not None:
            output = make_pointer(source, paired[0], paired[1], source_sha256=source_hash)
            pointers.append(output)
            pointer_by_index[paired[0]] = output

    topology_actions: list[dict[str, Any]] = []
    for index, row in calls:
        payload = row.get("payload", {})
        if payload.get("name") not in {"spawn_agent", "create_thread"}:
            continue
        call_id = str(payload.get("call_id", ""))
        paired = outputs_by_call.get(call_id)
        task_path = None
        if paired is not None:
            try:
                output_value = json.loads(str(paired[1].get("payload", {}).get("output", "")))
            except json.JSONDecodeError:
                output_value = None
            if isinstance(output_value, Mapping):
                task_path = output_value.get("task_name") or output_value.get("thread_id")
        action = {
            "kind": "worker_dispatch" if isinstance(task_path, str) and task_path else "unclassified_dispatch",
            "target": task_path,
            "source": "/".join(task_path.split("/")[:-1]) if isinstance(task_path, str) and "/" in task_path else None,
            "stage": _task_stage(task_path) if isinstance(task_path, str) else "unknown",
            "evidence": [pointer_by_index[index]],
        }
        if paired is not None and paired[0] in pointer_by_index:
            action["evidence"].append(pointer_by_index[paired[0]])
        topology_actions.append(action)

    for index, row in enumerate(rows, start=1):
        payload = row.get("payload", {})
        if row.get("type") != "response_item" or payload.get("type") != "agent_message":
            continue
        author = payload.get("author")
        if not isinstance(author, str) or not author.startswith("/root/"):
            continue
        stage = _task_stage(author)
        text = _message_text(payload)
        if stage not in {"preflight", "verifier"} or not _positive_pass(text):
            continue
        pointer = make_pointer(source, index, row, source_sha256=source_hash)
        pointers.append(pointer)
        topology_actions.append({
            "kind": "preflight_pass" if stage == "preflight" else "independent_verification_pass",
            "target": author,
            "source": author,
            "stage": stage,
            "evidence": [pointer],
        })

    names = [str(row.get("payload", {}).get("name", "")) for _, row in calls]
    return {
        "case_id": case_id,
        "source_backed": source_seal is not None,
        "source_path": str(source),
        "source_sha256": source_hash,
        "source_seal": {
            key: source_seal[key]
            for key in (
                "manifest_version", "extracted_record_count", "sealed_prefix_raw_sha256",
                "seal_binding_sha256",
            )
        } if source_seal is not None else None,
        "baseline": {
            "function_calls": len(calls),
            "wait_or_poll_calls": sum(name in POLL_CALLS for name in names),
            "heartbeat_calls": sum(name in HEARTBEAT_CALLS for name in names),
            "dispatch_calls": sum(name in DISPATCH_CALLS for name in names),
        },
        "evidence": pointers,
        "counted_action_evidence": action_pointers,
        "topology_actions": topology_actions,
        "timing": {
            "active_spans": [],
            "variant_overhead_ms": None,
            "status": "unmeasurable_ms",
            "reason": "source lacks labelled baseline-only active critical-path spans and variant overhead",
        },
        "safety": {"status": "PENDING_SOURCE_EVALUATION"} if source_seal is not None else {"passed": False},
    }


def evaluate_topology(
    graph: Mapping[str, Any],
    *,
    preflight_passed: bool | None = True,
    framework_failure: bool = False,
) -> dict[str, Any]:
    nodes = {node["id"]: dict(node) for node in graph.get("nodes", [])}
    violations: list[str] = []
    for edge in graph.get("edges", []):
        if edge.get("kind") != "dispatch":
            continue
        source = nodes.get(edge.get("source"), {})
        if source.get("parent") is not None or source.get("role") != "scheduler":
            violations.append("leaf_nested_dispatch")
    if preflight_passed is False:
        violations.append("failed_preflight")
    reporting_nodes = [dict(node) for node in nodes.values() if node.get("role") != "coder"]
    reporting_ids = {node["id"] for node in reporting_nodes}
    reporting_edges = [
        dict(edge) for edge in graph.get("edges", [])
        if edge.get("source") in reporting_ids and edge.get("target") in reporting_ids
    ]
    return {
        "allowed": not violations,
        "violations": sorted(set(violations)),
        "quarantined": bool(framework_failure),
        "product_failure": False if framework_failure else None,
        "worker_dispatch_blocked": preflight_passed is False,
        "reporting_graph": {"nodes": reporting_nodes, "edges": reporting_edges},
        "independent_verification_retained": any(node.get("role") == "verifier" for node in reporting_nodes),
    }


def _graph_from_topology_actions(actions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {"/root": {"id": "/root", "role": "scheduler", "parent": None}}
    edges: list[dict[str, Any]] = []
    for action in actions:
        if action.get("kind") != "worker_dispatch":
            continue
        target = action.get("target")
        source = action.get("source")
        if not isinstance(target, str) or not isinstance(source, str):
            continue
        stage = action.get("stage")
        role = "verifier" if stage in {"preflight", "verifier"} else ("coder" if stage == "coder" else str(stage))
        nodes.setdefault(source, {"id": source, "role": "scheduler" if source == "/root" else "coder", "parent": "/".join(source.split("/")[:-1]) or None})
        nodes[target] = {"id": target, "role": role, "parent": source}
        edges.append({"source": source, "target": target, "kind": "dispatch"})
    return {"nodes": list(nodes.values()), "edges": edges}


def _union_length(intervals: Iterable[tuple[int, int]]) -> int:
    ordered = sorted(intervals)
    if not ordered:
        return 0
    total = 0
    start, end = ordered[0]
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def active_processing_savings(timing: Mapping[str, Any]) -> int | None:
    """Return conservative critical-path savings, or None when not measurable."""
    spans = list(timing.get("active_spans", []))
    if not spans:
        return None
    overhead = timing.get("variant_overhead_ms")
    if overhead is None or not isinstance(overhead, (int, float)) or overhead < 0:
        return None
    selected: list[tuple[int, int]] = []
    retained: list[tuple[int, int]] = []
    for span in spans:
        if not span.get("critical_path"):
            continue
        start, end = span.get("start_ms"), span.get("end_ms")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end < start:
            return None
        interval = (int(start), int(end))
        if span.get("baseline_only"):
            selected.append(interval)
        if span.get("retained"):
            retained.append(interval)
    if not selected:
        return None
    boundaries = sorted({point for interval in selected + retained for point in interval})
    exclusive = 0
    for start, end in zip(boundaries, boundaries[1:]):
        midpoint = (start + end) / 2
        in_selected = any(left <= midpoint < right for left, right in selected)
        in_retained = any(left <= midpoint < right for left, right in retained)
        if in_selected and not in_retained:
            exclusive += end - start
    return max(0, int(exclusive - overhead))


def simulate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    baseline = case.get("baseline", {})
    removed = int(baseline.get("wait_or_poll_calls", 0)) + int(baseline.get("heartbeat_calls", 0))
    baseline_actions = int(baseline.get("function_calls", 0))
    savings_ms = active_processing_savings(case.get("timing", {}))
    source_backed = bool(case.get("source_backed", False))
    safety_reasons: list[str] = []
    if source_backed:
        actions = list(case.get("topology_actions", []))
        graph = _graph_from_topology_actions(actions)
        preflight_passed = any(action.get("kind") == "preflight_pass" for action in actions)
        verifier_passed = any(action.get("kind") == "independent_verification_pass" for action in actions)
        framework_actions = [action for action in actions if action.get("stage") == "framework_repair"]
        unclassified = any(action.get("kind") == "unclassified_dispatch" for action in actions)
        topology = evaluate_topology(graph, preflight_passed=True if preflight_passed else None, framework_failure=bool(framework_actions))
        if unclassified:
            safety_reasons.append("unclassified_dispatch")
        if not any(action.get("kind") == "worker_dispatch" for action in actions):
            safety_reasons.append("missing_root_dispatch_evidence")
        if not preflight_passed:
            safety_reasons.append("missing_preflight_pass_evidence")
        if not verifier_passed:
            safety_reasons.append("missing_independent_verifier_pass_evidence")
        if not topology["independent_verification_retained"]:
            safety_reasons.append("independent_verifier_not_retained")
        if topology["violations"]:
            safety_status = "FAIL"
            safety_reasons.extend(topology["violations"])
        elif safety_reasons:
            safety_status = "UNMEASURABLE"
        else:
            safety_status = "PASS"
        safe = safety_status == "PASS"
    else:
        safe = bool(case.get("safety", {}).get("passed", False))
        safety_status = "PASS" if safe else "FAIL"
        topology = None
    return {
        "case_id": case.get("case_id"),
        "baseline_actions": baseline_actions,
        "variant_actions": max(0, baseline_actions - removed),
        "action_savings": removed,
        "action_reduction_fraction": (removed / baseline_actions) if baseline_actions else 0.0,
        "poll_block_duration_saved_ms": 0,
        "time_savings_ms": savings_ms,
        "timing_result": "MEASURED" if savings_ms is not None else "INSUFFICIENT_TELEMETRY",
        "simulation_verdict": (
            "SIMULATION_PASS" if safety_status == "PASS"
            else "REJECT_UNSAFE" if safety_status == "FAIL"
            else "INSUFFICIENT_EVIDENCE"
        ),
        "safety_passed": safe,
        "safety_status": safety_status,
        "safety_reasons": sorted(set(safety_reasons)),
        "topology_evaluation": topology,
    }


def score_results(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    baseline_actions = sum(int(row.get("baseline_actions", 0)) for row in rows)
    action_savings = sum(int(row.get("action_savings", 0)) for row in rows)
    measurable = [row for row in rows if row.get("time_savings_ms") is not None]
    verdicts = {row.get("simulation_verdict") for row in rows}
    aggregate_verdict = (
        "REJECT_UNSAFE" if "REJECT_UNSAFE" in verdicts
        else "SIMULATION_PASS" if verdicts == {"SIMULATION_PASS"}
        else "INSUFFICIENT_EVIDENCE"
    )
    return {
        "case_count": len(rows),
        "baseline_actions": baseline_actions,
        "variant_actions": baseline_actions - action_savings,
        "action_savings": action_savings,
        "action_reduction_fraction": (action_savings / baseline_actions) if baseline_actions else 0.0,
        "measurable_timing_cases": len(measurable),
        "timing_result": "MEASURED" if len(measurable) == len(rows) and rows else "INSUFFICIENT_TELEMETRY",
        "simulation_verdict": aggregate_verdict,
        "statistical_verdict": "NOT_APPLICABLE",
        "adoption_verdict": "NOT_APPLICABLE",
        "pace_acceptance": False,
    }
