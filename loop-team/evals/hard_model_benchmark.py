#!/usr/bin/env python3
"""Hard-case benchmark packet builder and deterministic scorer.

This module intentionally has no provider adapter code. It mines local Loop Team
artifacts into sanitized packets, then scores response rows from any provider
against the same packet/oracle matrix.
"""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from pathlib import Path


SCHEMA = "loop_team_hard_model_case.v1"
SUBSCRIPTION_RESULT_SCHEMA = "loop_team_subscription_benchmark_attempt.v1"
SUBSCRIPTION_RUN_SCHEMA = "loop_team_subscription_benchmark_run.v1"
ALLOWED_SUBSCRIPTION_ARMS = frozenset({
    "codex_subscription",
    "claude_code_subscription",
})
EXPECTED_AUTH_MODES = {
    "codex_subscription": "chatgpt_subscription",
    "claude_code_subscription": "claude_subscription",
}
TERMINAL_ATTEMPT_STATUSES = frozenset({
    "succeeded",
    "failed",
    "subscription_limited",
    "auth_unavailable",
})
_FORBIDDEN_ROUTE_TERMS = (
    "openai_api",
    "anthropic_api",
    "api_key",
    "paid_credit",
    "pay_as_you_go",
    "pay-as-you-go",
    "automatic_recharge",
    "recharge",
    "purchase",
    "billing",
    "credit",
)
_SUBSCRIPTION_LIMIT_RE = re.compile(
    r"(usage cap|rate.?limit|too many requests|throttl|quota|cooldown|seat limit|"
    r"subscription limit|subscription_limited|capacity|temporar(?:y|ily) unavailable)",
    re.IGNORECASE,
)
_SECRETISH_RE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{20,})")
_GAP_LANE = "plan_check_gap"
_EVAL_LANE = "active_eval_case"
_FORBIDDEN_GAP_KEYS = {
    "broken_assumption",
    "why_it_fails",
    "proposed_fix",
    "mechanism_refs",
}
_BOUNDARY_KEYS = _FORBIDDEN_GAP_KEYS | {
    "oracle",
    "expected",
    "source_path",
    "source_sha256",
    "payload_sha256",
    "lane",
    "origin",
    "id",
    "fixture",
}
_BOUNDARY_WORDS = (
    "gap_records",
    "plan_check",
    "false-pass",
    "false pass",
    "expected",
    "trap",
    "good",
    "pass",
    "fail",
)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{2,}")
_HOME_RE = re.compile(r"/Use" r"rs/[^/\s]+")


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value):
    return _sha256_bytes(_canonical_bytes(value))


def _repo_relative(path, root):
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path):
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except ValueError:
                continue
    return records


@dataclass(frozen=True)
class SubscriptionBenchmarkLimits:
    max_cases: int
    enabled_arms: tuple
    max_attempts_per_case: int
    max_retries_per_failure: int
    max_concurrency: int
    max_runtime_seconds: float


class SubscriptionBenchmarkError(RuntimeError):
    """Base error for subscription benchmark control-plane failures."""


class SubscriptionOnlyViolation(SubscriptionBenchmarkError):
    """Raised when config or an adapter exposes a non-subscription route."""


class SubscriptionLimitError(SubscriptionBenchmarkError):
    def __init__(self, message, category="subscription_limited"):
        super().__init__(message)
        self.category = category


class SubscriptionAuthUnavailableError(SubscriptionBenchmarkError):
    pass


class TransientBenchmarkError(SubscriptionBenchmarkError):
    pass


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_message(value):
    text = str(value or "").replace("\n", " ").strip()
    text = _SECRETISH_RE.sub("[redacted]", text)
    return text[:240]


def classify_subscription_limit(value):
    """Return a subscription-limit category when a provider response should stop an arm."""
    if isinstance(value, dict):
        fields = [
            value.get("status"), value.get("error"), value.get("error_code"),
            value.get("failure_category"), value.get("message"), value.get("stderr"),
        ]
        nested = value.get("raw")
        if isinstance(nested, dict):
            fields.extend([nested.get("error"), nested.get("code"), nested.get("message")])
        text = " ".join(str(field) for field in fields if field is not None)
    else:
        text = str(value or "")
    if _SUBSCRIPTION_LIMIT_RE.search(text):
        lowered = text.lower()
        if "rate" in lowered or "too many requests" in lowered or "throttl" in lowered:
            return "rate_limited"
        if "seat" in lowered:
            return "seat_limited"
        if "cooldown" in lowered:
            return "cooldown"
        if "quota" in lowered:
            return "quota_exhausted"
        return "usage_cap"
    return None


def _normalize_usage(usage):
    if usage is None:
        return None
    if not isinstance(usage, dict):
        return {"raw": _safe_message(usage)}
    normalized = {}
    for key, value in usage.items():
        if value is None:
            normalized[key] = None
        elif isinstance(value, bool):
            normalized[key] = value
        elif isinstance(value, (int, float, str)):
            normalized[key] = value
        elif isinstance(value, dict):
            normalized[key] = _normalize_usage(value)
        elif isinstance(value, list):
            normalized[key] = [item if isinstance(item, (int, float, str, bool)) or item is None
                               else _safe_message(item) for item in value]
        else:
            normalized[key] = _safe_message(value)
    return normalized or None


def _adapter_attr(adapter, name):
    if isinstance(adapter, dict):
        return adapter.get(name)
    return getattr(adapter, name, None)


def _invoke_adapter(adapter, packet, arm_id_value):
    if isinstance(adapter, dict) and callable(adapter.get("execute")):
        return adapter["execute"](packet)
    if hasattr(adapter, "execute") and callable(adapter.execute):
        return adapter.execute(packet)
    if callable(adapter):
        return adapter(packet)
    raise SubscriptionOnlyViolation("adapter for %s is not callable" % arm_id_value)


def validate_subscription_limits(limits):
    if not isinstance(limits, SubscriptionBenchmarkLimits):
        raise TypeError("limits must be SubscriptionBenchmarkLimits")
    numeric = {
        "max_cases": limits.max_cases,
        "max_attempts_per_case": limits.max_attempts_per_case,
        "max_retries_per_failure": limits.max_retries_per_failure,
        "max_concurrency": limits.max_concurrency,
        "max_runtime_seconds": limits.max_runtime_seconds,
    }
    for name, value in numeric.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError("%s must be a non-negative number" % name)
    if limits.max_cases < 1:
        raise ValueError("max_cases must be at least 1")
    if limits.max_attempts_per_case < 1:
        raise ValueError("max_attempts_per_case must be at least 1")
    if limits.max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1")
    if limits.max_runtime_seconds <= 0:
        raise ValueError("max_runtime_seconds must be positive")
    if not limits.enabled_arms:
        raise ValueError("enabled_arms must be non-empty")
    seen = set()
    for arm in limits.enabled_arms:
        if arm in seen:
            raise ValueError("enabled_arms must not contain duplicates")
        seen.add(arm)
        if arm not in ALLOWED_SUBSCRIPTION_ARMS:
            raise SubscriptionOnlyViolation("invalid benchmark arm %r" % (arm,))
        lowered = str(arm).lower()
        if any(term in lowered for term in _FORBIDDEN_ROUTE_TERMS):
            raise SubscriptionOnlyViolation("non-subscription arm is forbidden: %s" % arm)


def validate_subscription_adapters(enabled_arms, adapters):
    if not isinstance(adapters, dict):
        raise TypeError("adapters must be a dict keyed by enabled arm id")
    for arm in enabled_arms:
        if arm not in adapters:
            raise SubscriptionOnlyViolation("missing subscription adapter for %s" % arm)
        adapter = adapters[arm]
        route_type = _adapter_attr(adapter, "route_type") or _adapter_attr(adapter, "execution_route")
        if route_type and any(term in str(route_type).lower() for term in _FORBIDDEN_ROUTE_TERMS):
            raise SubscriptionOnlyViolation("adapter for %s exposes forbidden route %s" % (arm, route_type))
        auth_mode = _adapter_attr(adapter, "auth_mode")
        if auth_mode is not None and auth_mode != EXPECTED_AUTH_MODES[arm]:
            raise SubscriptionOnlyViolation(
                "adapter for %s must use %s auth, got %s" % (arm, EXPECTED_AUTH_MODES[arm], auth_mode)
            )
        if _adapter_attr(adapter, "allows_paid_fallback") is True:
            raise SubscriptionOnlyViolation("paid-credit fallback is forbidden for %s" % arm)
        for name in ("purchase_credits", "enable_recharge", "pay_as_you_go", "billing_client"):
            if _adapter_attr(adapter, name) is not None:
                raise SubscriptionOnlyViolation("%s is forbidden for %s" % (name, arm))


class JsonlSubscriptionResultStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read_records(self):
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
        return records

    def append(self, record):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
            f.write("\n")


def _completed_attempt_keys(records, run_id):
    out = set()
    for record in records:
        if record.get("run_id") != run_id:
            continue
        if record.get("status") not in TERMINAL_ATTEMPT_STATUSES:
            continue
        out.add((record.get("case_id"), record.get("arm_id"), record.get("attempt_number")))
    return out


def _limited_arms(records, run_id):
    return {
        record.get("arm_id") for record in records
        if record.get("run_id") == run_id and record.get("status") == "subscription_limited"
    }


def _result_record(run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                   status, response=None, usage=None, failure_category=None,
                   sanitized_message=None, retry_count=0, failures=None):
    ended_mono = time.monotonic()
    return {
        "schema": SUBSCRIPTION_RESULT_SCHEMA,
        "run_id": run_id,
        "matrix": matrix,
        "case_id": packet.get("case_id"),
        "arm_id": arm,
        "attempt_number": attempt_number,
        "retry_count": retry_count,
        "adapter_attempts": retry_count + 1,
        "start_time": started_at,
        "end_time": _utc_now_iso(),
        "latency_ms": int(round((ended_mono - started_mono) * 1000)),
        "status": status,
        "failure_category": failure_category,
        "sanitized_message": sanitized_message,
        "failures": failures or [],
        "usage": _normalize_usage(usage),
        "response": response,
    }


def _execute_subscription_attempt(run_id, matrix, packet, arm, adapter, attempt_number,
                                  max_retries_per_failure):
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    failures = []
    retry_count = 0
    while True:
        try:
            result = _invoke_adapter(adapter, packet, arm)
            limit_category = classify_subscription_limit(result)
            if limit_category:
                return _result_record(
                    run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                    "subscription_limited", failure_category=limit_category,
                    sanitized_message=_safe_message(result), retry_count=retry_count,
                    failures=failures,
                )
            if not isinstance(result, dict):
                result = {"response": result}
            status = result.get("status") or "succeeded"
            if status in ("ok", "success"):
                status = "succeeded"
            if status == "auth_unavailable":
                return _result_record(
                    run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                    "auth_unavailable", failure_category="subscription_auth_unavailable",
                    sanitized_message=_safe_message(result.get("message") or result),
                    retry_count=retry_count, failures=failures,
                )
            if status != "succeeded":
                category = result.get("failure_category") or "provider_failure"
                return _result_record(
                    run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                    "failed", response=result.get("response"), usage=result.get("usage"),
                    failure_category=category,
                    sanitized_message=_safe_message(result.get("message") or result.get("error") or result),
                    retry_count=retry_count, failures=failures,
                )
            return _result_record(
                run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                "succeeded", response=result.get("response"), usage=result.get("usage"),
                retry_count=retry_count, failures=failures,
            )
        except SubscriptionLimitError as exc:
            return _result_record(
                run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                "subscription_limited", failure_category=exc.category,
                sanitized_message=_safe_message(exc), retry_count=retry_count,
                failures=failures,
            )
        except SubscriptionAuthUnavailableError as exc:
            return _result_record(
                run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                "auth_unavailable", failure_category="subscription_auth_unavailable",
                sanitized_message=_safe_message(exc), retry_count=retry_count,
                failures=failures,
            )
        except TransientBenchmarkError as exc:
            failures.append({"category": "transient_failure", "message": _safe_message(exc)})
            if retry_count >= max_retries_per_failure:
                return _result_record(
                    run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                    "failed", failure_category="transient_failure",
                    sanitized_message=_safe_message(exc), retry_count=retry_count,
                    failures=failures,
                )
            retry_count += 1
        except Exception as exc:
            failures.append({"category": "provider_exception", "message": _safe_message(exc)})
            if retry_count >= max_retries_per_failure:
                return _result_record(
                    run_id, matrix, packet, arm, attempt_number, started_at, started_mono,
                    "failed", failure_category="provider_exception",
                    sanitized_message=_safe_message(exc), retry_count=retry_count,
                    failures=failures,
                )
            retry_count += 1


def run_subscription_scheduler(cases, limits, adapters, result_path, run_id=None, matrix="full"):
    """Run bounded subscription-only benchmark work with incremental JSONL results."""
    validate_subscription_limits(limits)
    validate_subscription_adapters(limits.enabled_arms, adapters)
    run_id = run_id or ("subscription-benchmark-%d" % int(time.time()))
    store = JsonlSubscriptionResultStore(result_path)
    existing = store.read_records()
    completed = _completed_attempt_keys(existing, run_id)
    limited = set(_limited_arms(existing, run_id))
    selected_cases = list(cases)[:limits.max_cases]
    started_mono = time.monotonic()
    stop_reasons = []
    scheduled = 0
    persisted = 0

    work = []
    for packet in selected_cases:
        for arm in limits.enabled_arms:
            for attempt_number in range(1, limits.max_attempts_per_case + 1):
                key = (packet.get("case_id"), arm, attempt_number)
                if key not in completed:
                    work.append((packet, arm, attempt_number))

    def runtime_exceeded():
        return time.monotonic() - started_mono >= limits.max_runtime_seconds

    next_index = 0
    pending = {}
    with ThreadPoolExecutor(max_workers=limits.max_concurrency) as executor:
        while next_index < len(work) or pending:
            while (next_index < len(work)
                   and len(pending) < limits.max_concurrency
                   and not runtime_exceeded()):
                packet, arm, attempt_number = work[next_index]
                next_index += 1
                if arm in limited:
                    continue
                future = executor.submit(
                    _execute_subscription_attempt, run_id, matrix, packet, arm, adapters[arm],
                    attempt_number, limits.max_retries_per_failure,
                )
                pending[future] = (packet, arm, attempt_number)
                scheduled += 1
            if runtime_exceeded() and "max_runtime_seconds" not in stop_reasons:
                stop_reasons.append("max_runtime_seconds")
            if not pending:
                break
            done, _not_done = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
            if not done:
                continue
            for future in done:
                _packet, arm, _attempt_number = pending.pop(future)
                record = future.result()
                store.append(record)
                persisted += 1
                if record.get("status") == "subscription_limited":
                    limited.add(arm)
                    if "subscription_limited:%s" % arm not in stop_reasons:
                        stop_reasons.append("subscription_limited:%s" % arm)
        if runtime_exceeded():
            for future in pending:
                future.cancel()

    records = store.read_records()
    current_records = [r for r in records if r.get("run_id") == run_id]
    return {
        "schema": SUBSCRIPTION_RUN_SCHEMA,
        "run_id": run_id,
        "matrix": matrix,
        "result_path": str(store.path),
        "selected_cases": [packet.get("case_id") for packet in selected_cases],
        "enabled_arms": list(limits.enabled_arms),
        "scheduled_calls": scheduled,
        "persisted_records": persisted,
        "total_records_for_run": len(current_records),
        "limited_arms": sorted(limited),
        "stop_reasons": stop_reasons,
        "max_concurrency": limits.max_concurrency,
        "max_runtime_seconds": limits.max_runtime_seconds,
    }


def smoke_limits_from(limits):
    return SubscriptionBenchmarkLimits(
        max_cases=1,
        enabled_arms=limits.enabled_arms,
        max_attempts_per_case=1,
        max_retries_per_failure=limits.max_retries_per_failure,
        max_concurrency=limits.max_concurrency,
        max_runtime_seconds=limits.max_runtime_seconds,
    )


def _smoke_passed(summary, result_path, run_id, enabled_arms):
    records = JsonlSubscriptionResultStore(result_path).read_records()
    smoke_success = {
        record.get("arm_id") for record in records
        if record.get("run_id") == run_id
        and record.get("matrix") == "smoke"
        and record.get("status") == "succeeded"
        and record.get("latency_ms") is not None
        and "usage" in record
    }
    return set(enabled_arms).issubset(smoke_success) and summary.get("scheduled_calls") >= len(enabled_arms)


def launch_subscription_benchmark(cases, limits, adapters, result_path, run_id=None):
    """Run the required smoke matrix, then launch the full subscription benchmark."""
    validate_subscription_limits(limits)
    run_id = run_id or ("subscription-benchmark-%d" % int(time.time()))
    smoke_summary = run_subscription_scheduler(
        cases, smoke_limits_from(limits), adapters, result_path, run_id=run_id, matrix="smoke",
    )
    if not _smoke_passed(smoke_summary, result_path, run_id, limits.enabled_arms):
        return {
            "schema": SUBSCRIPTION_RUN_SCHEMA,
            "run_id": run_id,
            "full_launched": False,
            "blocked_reason": "smoke_matrix_not_passed",
            "smoke": smoke_summary,
        }
    full_summary = run_subscription_scheduler(
        cases, limits, adapters, result_path, run_id=run_id, matrix="full",
    )
    return {
        "schema": SUBSCRIPTION_RUN_SCHEMA,
        "run_id": run_id,
        "full_launched": True,
        "smoke": smoke_summary,
        "full": full_summary,
    }


def _looks_like_record(value):
    if not isinstance(value, dict):
        return False
    if any(k in value for k in ("gap_type", "broken_assumption", "why_it_fails", "proposed_fix", "gap_id")):
        return True
    return bool(value)


def _extract_gap_records(value):
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_extract_gap_records(item))
        return out
    if not isinstance(value, dict):
        return []
    out = []
    for key in ("merged_items", "records"):
        nested = value.get(key)
        if isinstance(nested, list):
            out.extend(_extract_gap_records(nested))
    if out:
        return out
    return [value] if _looks_like_record(value) else []


def _load_gap_records(path):
    try:
        if path.suffix == ".jsonl":
            return _extract_gap_records(_read_jsonl(path))
        return _extract_gap_records(_read_json(path))
    except (OSError, ValueError, TypeError):
        return []


def _normalize_token(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _tokens_from_text(value):
    return [_normalize_token(x) for x in _TOKEN_RE.findall(str(value)) if len(_normalize_token(x)) >= 3]


def _collect_terms(value, skip_keys=None):
    skip_keys = set(skip_keys or ())
    terms = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in skip_keys:
                continue
            terms.extend(_collect_terms(item, skip_keys))
    elif isinstance(value, list):
        for item in value:
            terms.extend(_collect_terms(item, skip_keys))
    elif isinstance(value, (str, int, float)):
        terms.extend(_tokens_from_text(value))
    seen = set()
    out = []
    for term in terms:
        if term and term not in seen and term not in {"design", "logic", "round", "open", "pass", "fail"}:
            seen.add(term)
            out.append(term)
    return out[:20]


def _scrub_text(value, extra_forbidden=None):
    text = str(value)
    text = _HOME_RE.sub("[home]", text)
    for forbidden in extra_forbidden or ():
        if forbidden:
            text = text.replace(str(forbidden), "[redacted]")
    for word in _BOUNDARY_WORDS:
        text = re.sub(re.escape(word), "[label]", text, flags=re.IGNORECASE)
    return text


def _safe_gap_context(record):
    context = {}
    for key in ("gap_type", "tag", "category", "status", "blocking_for_completeness", "round", "lens"):
        if key in record:
            context[key] = _scrub_text(record[key])
    if record.get("touches"):
        context["referenced_sections"] = copy.deepcopy(record["touches"])
    if record.get("affected_rows") is not None:
        context["affected_rows"] = record.get("affected_rows")
    if record.get("unresolved_targets") is not None:
        context["unresolved_targets"] = record.get("unresolved_targets")
    if not context:
        context["record_shape"] = sorted(str(k) for k in record.keys() if k not in _FORBIDDEN_GAP_KEYS)[:8]
    return context


def _sanitize_json(value, extra_forbidden=None):
    if isinstance(value, dict):
        return {
            _scrub_text(k, extra_forbidden): _sanitize_json(v, extra_forbidden)
            for k, v in value.items()
            if k not in _BOUNDARY_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_json(x, extra_forbidden) for x in value]
    if isinstance(value, str):
        return _scrub_text(value, extra_forbidden)
    return value


def _sanitize_eval_case(case, source_name):
    blocked = {str(case.get("id", "")), source_name}
    payload = {}
    for key in ("type", "target", "requires", "artifact", "rubric", "note", "snapshot", "model_output", "artifacts"):
        if key not in case:
            continue
        if key in ("artifact", "rubric", "note"):
            payload[key] = _scrub_text(case[key], blocked)
        else:
            payload[key] = _sanitize_json(case[key], blocked)
    if not payload:
        payload["available_fields"] = sorted(k for k in case.keys() if k not in {"id", "origin", "expected", "fixture"})
    return payload


def _with_payload_hash(packet):
    payload = copy.deepcopy(packet)
    payload.pop("payload_sha256", None)
    packet["payload_sha256"] = _sha256_json(payload)
    return packet


def _make_gap_packet(root, path, source_bytes, record, ordinal):
    case_id = "case-%06d" % ordinal
    terms = _collect_terms(record, skip_keys=_FORBIDDEN_GAP_KEYS)
    forbidden_terms = _collect_terms({k: record.get(k) for k in _FORBIDDEN_GAP_KEYS})
    packet = {
        "schema": SCHEMA,
        "case_id": case_id,
        "lane": _GAP_LANE,
        "source_path": _repo_relative(path, root),
        "source_sha256": _sha256_bytes(source_bytes),
        "role_targets": ["verifier", "orchestrator"],
        "model_input": {
            "case_id": case_id,
            "task": "Review the sanitized planning context and decide whether a material planning gap exists. Return structured JSON with case_id, verdict, summary, and source_grounding.",
            "return_contract": {
                "case_id": case_id,
                "verdict": "GAP_FOUND",
                "summary": "non-empty string",
                "source_grounding": ["non-empty evidence strings"],
            },
            "context": _safe_gap_context(record),
        },
        "oracle": {
            "expected_verdict": "GAP_FOUND",
            "expected_source_terms": terms,
            "forbidden_grounding_terms": forbidden_terms,
        },
    }
    return _with_payload_hash(packet)


def _make_eval_packet(root, path, source_bytes, case, ordinal):
    case_id = "case-%06d" % ordinal
    packet = {
        "schema": SCHEMA,
        "case_id": case_id,
        "lane": _EVAL_LANE,
        "source_path": _repo_relative(path, root),
        "source_sha256": _sha256_bytes(source_bytes),
        "role_targets": ["verifier"],
        "source_id": case.get("id"),
        "model_input": {
            "case_id": case_id,
            "task": "Evaluate the sanitized frozen case. Return structured JSON with case_id, verdict, and summary using the benchmark verdict vocabulary.",
            "case_material": _sanitize_eval_case(case, path.name),
        },
        "oracle": {
            "expected_verdict": str(case.get("expected", "")).upper(),
        },
    }
    return _with_payload_hash(packet)


def build_cases(root, max_gap_cases=20, max_eval_cases=20):
    """Build deterministic benchmark packets from local loop-team artifacts."""
    root = Path(root).expanduser().resolve()
    packets = []
    ordinal = 1

    runs_dir = root / "loop-team" / "runs"
    gap_paths = []
    if runs_dir.is_dir():
        gap_paths = sorted(
            [p for p in runs_dir.rglob("gap_records*.json") if p.is_file()]
            + [p for p in runs_dir.rglob("gap_records*.jsonl") if p.is_file()],
            key=lambda p: _repo_relative(p, root),
        )
    gap_count = 0
    for path in gap_paths:
        if gap_count >= max_gap_cases:
            break
        try:
            source_bytes = path.read_bytes()
        except OSError:
            continue
        for record in _load_gap_records(path):
            if gap_count >= max_gap_cases:
                break
            if not isinstance(record, dict):
                continue
            packets.append(_make_gap_packet(root, path, source_bytes, record, ordinal))
            ordinal += 1
            gap_count += 1

    cases_dir = root / "loop-team" / "evals" / "cases"
    eval_count = 0
    if cases_dir.is_dir():
        for path in sorted(cases_dir.iterdir(), key=lambda p: p.name):
            if eval_count >= max_eval_cases:
                break
            if not path.is_file() or path.suffix != ".json":
                continue
            try:
                source_bytes = path.read_bytes()
                case = json.loads(source_bytes.decode("utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(case, dict) or not case.get("expected"):
                continue
            packets.append(_make_eval_packet(root, path, source_bytes, case, ordinal))
            ordinal += 1
            eval_count += 1
    return packets


def _parse_response(response):
    if isinstance(response, dict):
        return response, None
    if isinstance(response, str):
        try:
            parsed = json.loads(response)
        except ValueError as exc:
            return None, "invalid JSON response: %s" % exc
        if not isinstance(parsed, dict):
            return None, "JSON response is not an object"
        return parsed, None
    return None, "response must be a dict or JSON object string"


def _score_fail(packet, verdict, reasons):
    return {
        "passed": False,
        "case_id": packet.get("case_id"),
        "verdict": verdict,
        "reasons": reasons,
    }


def _response_text(response):
    parts = []
    if response.get("summary"):
        parts.append(str(response.get("summary")))
    grounding = response.get("source_grounding")
    if isinstance(grounding, list):
        parts.extend(str(x) for x in grounding)
    elif grounding is not None:
        parts.append(str(grounding))
    return " ".join(parts)


def score_response(packet, response):
    """Score one structured response against a packet's deterministic oracle."""
    parsed, error = _parse_response(response)
    if error:
        return _score_fail(packet, None, [error])
    reasons = []
    verdict = parsed.get("verdict")
    if parsed.get("case_id") != packet.get("case_id"):
        reasons.append("wrong case_id: expected %r got %r" % (packet.get("case_id"), parsed.get("case_id")))
    if not verdict:
        reasons.append("missing verdict")
    expected = packet.get("oracle", {}).get("expected_verdict")
    if verdict != expected:
        reasons.append("wrong verdict: expected %r got %r" % (expected, verdict))

    lane = packet.get("lane")
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        reasons.append("missing non-empty summary")
    if lane == _GAP_LANE:
        grounding = parsed.get("source_grounding")
        if not isinstance(grounding, list) or not any(str(x).strip() for x in grounding):
            reasons.append("missing source_grounding evidence")
        expected_terms = set(packet.get("oracle", {}).get("expected_source_terms") or [])
        response_terms = set(_tokens_from_text(_response_text(parsed)))
        overlap = expected_terms & response_terms
        if expected_terms and not overlap:
            forbidden = set(packet.get("oracle", {}).get("forbidden_grounding_terms") or [])
            if forbidden & response_terms:
                reasons.append("bare forbidden mechanism text is not sufficient grounding")
            reasons.append("missing expected source-term overlap")
    elif lane == _EVAL_LANE:
        pass
    else:
        reasons.append("unknown packet lane %r" % lane)

    if reasons:
        return _score_fail(packet, verdict, reasons)
    return {
        "passed": True,
        "case_id": packet.get("case_id"),
        "verdict": verdict,
        "reasons": ["matched oracle"],
    }


def arm_id(arm):
    effort = arm.get("effort")
    if effort is None or effort == "":
        effort = "none"
    return "%s:%s:%s" % (arm.get("provider"), arm.get("model"), effort)


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _empty_arm(provider, model, effort):
    return {
        "provider": provider,
        "model": model,
        "effort": "none" if effort is None or effort == "" else effort,
        "attempted_cases": 0,
        "passed_cases": 0,
        "failed_cases": 0,
        "accuracy": 0.0,
        "mean_latency_ms": None,
        "total_observed_tokens": None,
        "usage_totals": {},
        "estimated_cost_usd": None,
        "authoritative_cost_usd": None,
        "cost_authorities": [],
        "missing_telemetry_dimensions": [],
    }


def _update_telemetry(aggregate, row, scratch):
    latency = _number(row.get("latency_ms"))
    if latency is None:
        scratch["missing"].add("latency_ms")
    else:
        scratch["latencies"].append(latency)

    usage = row.get("usage")
    if not isinstance(usage, dict):
        scratch["missing"].add("usage")
    else:
        row_token_total = 0.0
        saw_token = False
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "reasoning_output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            value = _number(usage.get(key))
            if value is not None:
                aggregate["usage_totals"][key] = aggregate["usage_totals"].get(key, 0) + int(value)
                saw_token = True
        total = _number(usage.get("total_tokens"))
        if total is not None:
            row_token_total = total
        else:
            for key in ("input_tokens", "output_tokens", "reasoning_output_tokens"):
                value = _number(usage.get(key))
                if value is not None:
                    row_token_total += value
        if saw_token:
            scratch["token_total"] += row_token_total
            scratch["saw_tokens"] = True
        else:
            scratch["missing"].add("usage")

    estimated = _number(row.get("estimated_cost_usd"))
    if estimated is None:
        scratch["missing"].add("estimated_cost_usd")
    else:
        scratch["estimated_cost"] += estimated
        scratch["saw_estimated_cost"] = True

    authoritative = _number(row.get("authoritative_cost_usd"))
    if authoritative is None:
        scratch["missing"].add("authoritative_cost_usd")
    else:
        scratch["authoritative_cost"] += authoritative
        scratch["saw_authoritative_cost"] = True

    authority = row.get("cost_authority")
    if authority:
        if authority not in aggregate["cost_authorities"]:
            aggregate["cost_authorities"].append(authority)
        if str(authority).startswith("unavailable"):
            scratch["missing"].add("cost_authority")
    else:
        scratch["missing"].add("cost_authority")


def score_matrix(packets, response_rows):
    """Score provider/model/effort rows side-by-side against the same packets."""
    packet_by_id = {p["case_id"]: p for p in packets}
    arms = {}
    scratch_by_arm = {}
    cases = {p["case_id"]: {} for p in packets}

    for row in response_rows:
        aid = arm_id(row)
        if aid not in arms:
            arms[aid] = _empty_arm(row.get("provider"), row.get("model"), row.get("effort"))
            scratch_by_arm[aid] = {
                "latencies": [],
                "missing": set(),
                "token_total": 0.0,
                "saw_tokens": False,
                "estimated_cost": 0.0,
                "saw_estimated_cost": False,
                "authoritative_cost": 0.0,
                "saw_authoritative_cost": False,
            }
        arm = arms[aid]
        scratch = scratch_by_arm[aid]
        case_id = row.get("case_id")
        packet = packet_by_id.get(case_id)
        if packet is None:
            result = {"passed": False, "case_id": case_id, "verdict": None, "reasons": ["unknown case_id"]}
        else:
            result = score_response(packet, row.get("response"))
        arm["attempted_cases"] += 1
        if result["passed"]:
            arm["passed_cases"] += 1
        else:
            arm["failed_cases"] += 1
        cases.setdefault(case_id, {})[aid] = result
        _update_telemetry(arm, row, scratch)

    for aid, arm in arms.items():
        scratch = scratch_by_arm[aid]
        attempted = arm["attempted_cases"]
        arm["accuracy"] = (float(arm["passed_cases"]) / attempted) if attempted else 0.0
        if scratch["latencies"]:
            arm["mean_latency_ms"] = sum(scratch["latencies"]) / len(scratch["latencies"])
        if scratch["saw_tokens"]:
            arm["total_observed_tokens"] = int(scratch["token_total"])
        if scratch["saw_estimated_cost"]:
            arm["estimated_cost_usd"] = scratch["estimated_cost"]
        if scratch["saw_authoritative_cost"]:
            arm["authoritative_cost_usd"] = scratch["authoritative_cost"]
        arm["missing_telemetry_dimensions"] = sorted(scratch["missing"])
        arm["cost_authorities"] = sorted(arm["cost_authorities"])

    ranking = sorted(
        arms,
        key=lambda aid: (-arms[aid]["accuracy"], -arms[aid]["passed_cases"], -arms[aid]["attempted_cases"], aid),
    )
    return {
        "schema": "loop_team_hard_model_score_matrix.v1",
        "quality_ranking": ranking,
        "arms": arms,
        "cases": cases,
    }


def _load_json_argument(value):
    path = Path(value)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(value)


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Build and score Loop Team hard-model benchmark packets.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build")
    build.add_argument("--root", required=True)
    build.add_argument("--json", action="store_true")
    build.add_argument("--max-gap-cases", type=int, default=20)
    build.add_argument("--max-eval-cases", type=int, default=20)
    score = sub.add_parser("score")
    score.add_argument("--cases", required=True)
    score.add_argument("--responses", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "build":
        packets = build_cases(args.root, max_gap_cases=args.max_gap_cases, max_eval_cases=args.max_eval_cases)
        print(json.dumps(packets, indent=2, sort_keys=True))
        return 0
    if args.cmd == "score":
        packets = _load_json_argument(args.cases)
        responses = _load_json_argument(args.responses)
        print(json.dumps(score_matrix(packets, responses), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
