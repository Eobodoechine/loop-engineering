"""Typed, approval-gated experiment execution helpers.

This module is deliberately separate from ordinary ``LoopTeam`` dispatch.  The
ordinary runner still accepts string-returning callables; an explicit experiment
attempt must use this module and cannot initialize a real provider until its
authority material has been validated.
"""
from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional


OFFLINE_MODES = frozenset(("deterministic_offline", "synthetic_test"))
REAL_PROVIDER_MODES = frozenset((
    "anthropic_api", "openai_api", "claude_subscription",
    "codex_subscription", "cloud_or_gateway",
))
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


class UsageValidationError(ValueError):
    """Raised when a usage.v1 record has unverifiable telemetry."""


class ExperimentBlockedError(RuntimeError):
    """A real experiment failed closed before reaching a provider boundary."""

    code = "BLOCKED_APPROVAL_OR_SEAL"

    def __init__(self, message: str):
        super().__init__(message)


@dataclass(frozen=True)
class ProviderAdapterResult:
    """The only provider-result shape accepted for experiment telemetry."""

    response_text: str
    canonical_sdk_response_id: Optional[str]
    canonical_sdk_request_id: Optional[str]
    raw_usage: Optional[Dict[str, Any]]
    raw_response_payload_hash: str
    raw_observation_id: str
    input_hashes: Optional[Dict[str, str]] = None
    input_receipt_hash: Optional[str] = None
    raw_response_payload_bytes: Optional[bytes] = None

    def __post_init__(self) -> None:
        if not isinstance(self.response_text, str):
            raise TypeError("response_text must be a string")
        if not isinstance(self.raw_response_payload_hash, str) or not _SHA256_RE.fullmatch(
                self.raw_response_payload_hash):
            raise ValueError("raw_response_payload_hash must be a sha256 hex string")
        if not isinstance(self.raw_observation_id, str) or not self.raw_observation_id:
            raise ValueError("raw_observation_id is required")
        if self.raw_usage is not None and not isinstance(self.raw_usage, dict):
            raise TypeError("raw_usage must be an object or null")
        if self.input_hashes is not None:
            if not isinstance(self.input_hashes, dict) or not self.input_hashes or any(
                    not isinstance(name, str) or not name or not isinstance(value, str)
                    or not _SHA256_RE.fullmatch(value)
                    for name, value in self.input_hashes.items()):
                raise ValueError("input_hashes must contain exact sha256 hex values")
        if self.input_receipt_hash is not None and (
                not isinstance(self.input_receipt_hash, str)
                or not _SHA256_RE.fullmatch(self.input_receipt_hash)):
            raise ValueError("input_receipt_hash must be a sha256 hex string")
        if self.raw_response_payload_bytes is not None:
            if not isinstance(self.raw_response_payload_bytes, bytes):
                raise TypeError("raw_response_payload_bytes must be bytes or null")
            actual_hash = hashlib.sha256(self.raw_response_payload_bytes).hexdigest()
            if actual_hash != self.raw_response_payload_hash:
                raise ValueError("raw_response_payload_hash does not bind payload bytes")


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _unavailable(reason: str) -> Dict[str, Any]:
    return {
        "kind": "unavailable",
        "observation_id": None,
        "path": None,
        "source_observation_ids": [],
        "algorithm": None,
        "algorithm_version": None,
        "unavailable_reason": reason,
    }


def _raw(observation_id: str, path: str) -> Dict[str, Any]:
    return {
        "kind": "raw",
        "observation_id": observation_id,
        "path": path,
        "source_observation_ids": [],
        "algorithm": None,
        "algorithm_version": None,
        "unavailable_reason": None,
    }


def _derivation(observation_ids: Iterable[str], algorithm: str,
                version: str = "v1") -> Dict[str, Any]:
    return {
        "kind": "derivation",
        "observation_id": None,
        "path": None,
        "source_observation_ids": list(observation_ids),
        "algorithm": algorithm,
        "algorithm_version": version,
        "unavailable_reason": None,
    }


def _field(value: Any, provenance: Dict[str, Any]) -> Dict[str, Any]:
    return {"value": value, "field_provenance": provenance}


def _missing(reason: str) -> Dict[str, Any]:
    return _field(None, _unavailable(reason))


def _mode_reason(execution_mode: str, field_name: str) -> str:
    return "%s does not emit provider %s" % (execution_mode, field_name)


def _envelope_observation(attempt_id: str, dispatch_id: str,
                          execution_mode: str) -> Dict[str, Any]:
    observation_id = "harness-" + str(uuid.uuid4())
    payload = {
        "attempt_id": attempt_id,
        "dispatch_id": dispatch_id,
        "execution_mode": execution_mode,
    }
    return {
        "observation_id": observation_id,
        "source_kind": "harness_envelope",
        "collected_at": _datetime.datetime.now(
            _datetime.timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"),
        "request_or_record_id": None,
        "payload_hash": _canonical_hash(payload),
        "redacted_payload": payload,
    }


def _base_record(execution_mode: str, attempt_id: str,
                 dispatch_id: str) -> Dict[str, Any]:
    envelope = _envelope_observation(attempt_id, dispatch_id, execution_mode)
    envelope_id = envelope["observation_id"]
    unavailable = lambda name: _missing(_mode_reason(execution_mode, name))
    token_fields = {
        name: unavailable(name)
        for name in (
            "input_tokens", "output_tokens", "cache_read_input_tokens",
            "cache_creation_input_tokens", "reasoning_output_tokens",
            "total_tokens_reported",
        )
    }
    record = {
        "schema": "usage.v1",
        "response_text": None,
        "attempt_id": _field(attempt_id, _raw(envelope_id, "$.attempt_id")),
        "dispatch_id": _field(dispatch_id, _raw(envelope_id, "$.dispatch_id")),
        "execution_mode": _field(
            execution_mode, _raw(envelope_id, "$.execution_mode")),
        "provider": unavailable("provider"),
        "policy_class": unavailable("policy_class"),
        "requested_model": unavailable("requested_model"),
        "resolved_model_id": unavailable("resolved_model_id"),
        "requested_effort": unavailable("requested_effort"),
        "actual_effort": unavailable("actual_effort"),
        "canonical_sdk_response_id": unavailable("canonical_sdk_response_id"),
        "canonical_sdk_request_id": unavailable("canonical_sdk_request_id"),
        "raw_usage": unavailable("raw_usage"),
        "token_fields": token_fields,
        "attempt_payload_hash": _field(
            _canonical_hash({"attempt_id": attempt_id}),
            _derivation((envelope_id,), "sha256")),
        "dispatch_payload_hash": _field(
            _canonical_hash({"dispatch_id": dispatch_id}),
            _derivation((envelope_id,), "sha256")),
        "latency_ms": unavailable("latency_ms"),
        "ttft_ms": unavailable("ttft_ms"),
        "monotonic_started_ns": unavailable("monotonic_started_ns"),
        "monotonic_finished_ns": unavailable("monotonic_finished_ns"),
        "wall_started_at": unavailable("wall_started_at"),
        "wall_finished_at": unavailable("wall_finished_at"),
        "retry_attempt": unavailable("retry_attempt"),
        "retry_count": unavailable("retry_count"),
        "escalation_count": unavailable("escalation_count"),
        "request_ids": unavailable("request_ids"),
        "rate_limits_observed": unavailable("rate_limits_observed"),
        "estimated_cost_usd": unavailable("estimated_cost_usd"),
        "authoritative_cost_usd": unavailable("authoritative_cost_usd"),
        "billing_authority": unavailable("billing_authority"),
        "billing_record_id": unavailable("billing_record_id"),
        "billing_period": unavailable("billing_period"),
        "reconciled_at": unavailable("reconciled_at"),
        "subscription_allowance_observation": {
            "window_kind": unavailable("subscription_allowance.window_kind"),
            "used_percentage": unavailable("subscription_allowance.used_percentage"),
            "resets_at": unavailable("subscription_allowance.resets_at"),
        },
        "raw_observations": [envelope],
        "derived_total_tokens": None,
        "experiment_eligible": execution_mode not in OFFLINE_MODES,
        "promotion_eligible": execution_mode not in OFFLINE_MODES,
    }
    return record


def empty_usage_v1(execution_mode: str, attempt_id: str,
                   dispatch_id: str) -> Dict[str, Any]:
    """Return a no-provider usage record for an offline or synthetic attempt."""
    if execution_mode not in OFFLINE_MODES:
        raise ValueError("empty_usage_v1 is only valid for offline/synthetic modes")
    record = _base_record(execution_mode, attempt_id, dispatch_id)
    record["experiment_eligible"] = False
    record["promotion_eligible"] = False
    return record


def bind_attempt_assignment(record: Dict[str, Any], *, hypothesis_id: str,
                            case_id: str, split: str, arm: str,
                            isolation_context: Dict[str, Any],
                            finalization_receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Bind one normalized receipt to its frozen assignment and local isolation."""
    if split not in ("evaluation", "held_out"):
        raise UsageValidationError("attempt split must be evaluation or held_out")
    if arm not in ("incumbent", "challenger"):
        raise UsageValidationError("attempt arm must be incumbent or challenger")
    if not isinstance(isolation_context, dict) or not isinstance(
            finalization_receipt, dict):
        raise UsageValidationError("attempt isolation and finalization are required")
    bindings = {
        "hypothesis_id": hypothesis_id,
        "case_id": case_id,
        "split": split,
        "arm": arm,
        "isolation_attribution_hash": isolation_context.get("attribution_hash"),
        "worktree_path": isolation_context.get("worktree"),
        "fixture_namespace": isolation_context.get("fixture_namespace"),
        "fixture_path": isolation_context.get("fixture_dir"),
        "quarantine_path": isolation_context.get("quarantine_dir"),
        "diff_inventory_path": isolation_context.get("diff_inventory_path"),
        "finalization_state": finalization_receipt.get("state"),
        "finalization_receipt_hash": finalization_receipt.get("receipt_hash"),
        "finalization_receipt_path": finalization_receipt.get("receipt_path"),
    }
    if any(not isinstance(value, str) or not value for value in bindings.values()):
        raise UsageValidationError("attempt assignment binding is incomplete")
    for field_name, value in bindings.items():
        _set_envelope_field(record, field_name, value)
    validate_usage_v1(record)
    return record


def _provider_for_mode(execution_mode: str) -> Optional[str]:
    return {
        "anthropic_api": "anthropic",
        "openai_api": "openai",
        "codex_subscription": "openai",
    }.get(execution_mode)


def _set_raw_field(record: Dict[str, Any], field_name: str, value: Any,
                   observation_id: str, path: str) -> None:
    record[field_name] = _field(value, _raw(observation_id, path))


def _set_envelope_field(record: Dict[str, Any], field_name: str,
                        value: Any) -> None:
    """Bind validated dispatch metadata to the local harness observation."""
    envelope = next(
        observation for observation in record["raw_observations"]
        if observation.get("source_kind") == "harness_envelope"
    )
    envelope["redacted_payload"][field_name] = value
    envelope["payload_hash"] = _canonical_hash(envelope["redacted_payload"])
    _set_raw_field(record, field_name, value, envelope["observation_id"],
                   "$." + field_name)


def _usage_value(raw_usage: Dict[str, Any], path: str) -> Any:
    current: Any = raw_usage
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            return None
        current = current[component]
    return current


def normalize_provider_result(result: ProviderAdapterResult, attempt_id: str,
                              dispatch_id: str, execution_mode: str,
                              provider: Optional[str] = None,
                              policy_class: Optional[str] = None,
                              requested_model: Optional[str] = None,
                              resolved_model_id: Optional[str] = None,
                              requested_effort: Optional[str] = None,
                              actual_effort: Optional[str] = None) -> Dict[str, Any]:
    """Normalize a typed provider boundary result without inventing totals."""
    if execution_mode not in REAL_PROVIDER_MODES:
        raise ValueError("typed provider results require a provider execution mode")
    if not isinstance(result, ProviderAdapterResult):
        raise TypeError("provider telemetry requires ProviderAdapterResult")

    record = _base_record(execution_mode, attempt_id, dispatch_id)
    record["response_text"] = result.response_text
    record["experiment_eligible"] = True
    record["promotion_eligible"] = True
    provider_payload = {
        "attempt_id": attempt_id,
        "dispatch_id": dispatch_id,
        "canonical_sdk_response_id": result.canonical_sdk_response_id,
        "canonical_sdk_request_id": result.canonical_sdk_request_id,
        "usage": result.raw_usage,
        "input_hashes": result.input_hashes,
        "input_receipt_hash": result.input_receipt_hash,
    }
    provider_observation = {
        "observation_id": result.raw_observation_id,
        "source_kind": {
            "anthropic_api": "anthropic_messages_response",
            "openai_api": "openai_responses_object",
            "codex_subscription": "codex_jsonl_observed",
        }.get(execution_mode, "provider_response"),
        "collected_at": _datetime.datetime.now(
            _datetime.timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"),
        "request_or_record_id": result.canonical_sdk_request_id,
        "payload_hash": result.raw_response_payload_hash,
        "redacted_payload": provider_payload,
    }
    # The provider observation is first so consumers can directly retain the
    # adapter's immutable raw payload hash.
    record["raw_observations"] = [provider_observation] + record["raw_observations"]
    provider_value = provider if provider is not None else _provider_for_mode(execution_mode)
    if provider_value is not None:
        _set_envelope_field(record, "provider", provider_value)
    if policy_class is not None:
        _set_envelope_field(record, "policy_class", policy_class)
    if requested_model is not None:
        _set_envelope_field(record, "requested_model", requested_model)
    if resolved_model_id is not None:
        # Model/effort are supplied by a validated experiment context, not inferred
        # from the text response.
        _set_envelope_field(record, "resolved_model_id", resolved_model_id)
    if requested_effort is not None:
        _set_envelope_field(record, "requested_effort", requested_effort)
    if actual_effort is not None:
        _set_envelope_field(record, "actual_effort", actual_effort)

    if result.canonical_sdk_response_id is not None:
        _set_raw_field(record, "canonical_sdk_response_id",
                       result.canonical_sdk_response_id, result.raw_observation_id,
                       "$.canonical_sdk_response_id")
    if result.canonical_sdk_request_id is not None:
        _set_raw_field(record, "canonical_sdk_request_id",
                       result.canonical_sdk_request_id, result.raw_observation_id,
                       "$.canonical_sdk_request_id")
        _set_raw_field(record, "request_ids", [result.canonical_sdk_request_id],
                       result.raw_observation_id, "$.canonical_sdk_request_id")

    if result.raw_usage is not None:
        _set_raw_field(record, "raw_usage", result.raw_usage,
                       result.raw_observation_id, "$.usage")
        source_fields = {
            "input_tokens": ("input_tokens",),
            "output_tokens": ("output_tokens",),
            "cache_read_input_tokens": ("cache_read_input_tokens", "cached_input_tokens"),
            "cache_creation_input_tokens": ("cache_creation_input_tokens",),
            "total_tokens_reported": ("total_tokens",),
            "reasoning_output_tokens": (
                "output_tokens_details.reasoning_tokens", "reasoning_output_tokens"),
        }
        for normalized_name, raw_names in source_fields.items():
            for raw_name in raw_names:
                value = _usage_value(result.raw_usage, raw_name)
                if value is not None:
                    record["token_fields"][normalized_name] = _field(
                        value, _raw(result.raw_observation_id, "$.usage." + raw_name))
                    break
        if execution_mode == "codex_subscription" and _usage_value(
                result.raw_usage, "total_tokens") is None:
            input_tokens = _usage_value(result.raw_usage, "input_tokens")
            output_tokens = _usage_value(result.raw_usage, "output_tokens")
            if type(input_tokens) is int and input_tokens >= 0 and type(
                    output_tokens) is int and output_tokens >= 0:
                record["derived_total_tokens"] = _field(
                    input_tokens + output_tokens,
                    _derivation(
                        (result.raw_observation_id,),
                        "input_tokens_plus_output_tokens",
                    ),
                )
    if execution_mode == "codex_subscription":
        _set_envelope_field(
            record, "billing_authority",
            "unavailable_subscription_no_usd_billing_authority",
        )
        record["promotion_eligible"] = False
    validate_usage_v1(record)
    return record


def attach_cost_observation(record: Dict[str, Any],
                            observation: Dict[str, Any]) -> Dict[str, Any]:
    """Attach one explicit cost observation without collapsing its authority."""
    validate_usage_v1(record)
    if record.get("execution_mode", {}).get("value") == "codex_subscription":
        raise UsageValidationError("codex subscription execution has no USD authority")
    if not isinstance(observation, dict):
        raise UsageValidationError("cost observation must be an object")
    observation_id = observation.get("observation_id")
    source_kind = observation.get("source_kind")
    if not isinstance(observation_id, str) or not observation_id:
        raise UsageValidationError("cost observation id is required")
    if source_kind == "billing_surface":
        field_name = "authoritative_cost_usd"
    elif source_kind == "local_static_rate":
        field_name = "estimated_cost_usd"
    else:
        raise UsageValidationError("cost observation has an invalid source kind")
    value = observation.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise UsageValidationError("cost observation value must be non-negative")
    raw_observation = {
        "observation_id": observation_id,
        "source_kind": source_kind,
        "collected_at": _datetime.datetime.now(
            _datetime.timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"),
        "request_or_record_id": observation.get("request_or_record_id"),
        "payload_hash": _canonical_hash({field_name: value}),
        "redacted_payload": {field_name: value},
    }
    record["raw_observations"].append(raw_observation)
    _set_raw_field(record, field_name, value, observation_id,
                   "$." + field_name)
    validate_usage_v1(record)
    return record


def normalize_legacy_string(response_text: str, attempt_id: str,
                            dispatch_id: str) -> Dict[str, Any]:
    """Serialize legacy output without pretending its text contains telemetry."""
    if not isinstance(response_text, str):
        raise TypeError("legacy response must be a string")
    record = _base_record("legacy_string", attempt_id, dispatch_id)
    record["response_text"] = response_text
    record["experiment_eligible"] = False
    record["promotion_eligible"] = False
    return record


def _path_exists(payload: Any, path: str) -> bool:
    if not isinstance(path, str) or not path.startswith("$."):
        return False
    current = payload
    for component in path[2:].split("."):
        if not isinstance(current, dict) or component not in current:
            return False
        current = current[component]
    return True


def _iter_field_values(value: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(value, dict):
        return
    if set(("value", "field_provenance")).issubset(value):
        yield value
        return
    for key, child in value.items():
        if key in ("raw_observations", "field_provenance"):
            continue
        yield from _iter_field_values(child)


def validate_usage_v1(record: Dict[str, Any]) -> None:
    """Validate uniform field provenance and billing-source boundaries."""
    if not isinstance(record, dict) or record.get("schema") != "usage.v1":
        raise UsageValidationError("record must declare schema usage.v1")
    observations = record.get("raw_observations")
    if not isinstance(observations, list) or not observations:
        raise UsageValidationError("usage.v1 requires raw observations")
    observation_by_id: Dict[str, Dict[str, Any]] = {}
    for observation in observations:
        if not isinstance(observation, dict):
            raise UsageValidationError("raw observation must be an object")
        observation_id = observation.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id:
            raise UsageValidationError("raw observation id is required")
        if observation_id in observation_by_id:
            raise UsageValidationError("raw observation ids must be unique")
        if not isinstance(observation.get("redacted_payload"), dict):
            raise UsageValidationError("raw observation needs a redacted payload")
        observation_by_id[observation_id] = observation

    for field_value in _iter_field_values(record):
        value = field_value.get("value")
        provenance = field_value.get("field_provenance")
        if not isinstance(provenance, dict):
            raise UsageValidationError("every FieldValue needs field_provenance")
        kind = provenance.get("kind")
        if kind == "unavailable":
            if value is not None or not isinstance(
                    provenance.get("unavailable_reason"), str) or not provenance.get(
                        "unavailable_reason").strip():
                raise UsageValidationError("unavailable fields must be null with a reason")
            if provenance.get("observation_id") is not None or provenance.get(
                    "path") is not None or provenance.get("source_observation_ids"):
                raise UsageValidationError("unavailable fields cannot cite observations")
        elif kind == "raw":
            observation_id = provenance.get("observation_id")
            observation = observation_by_id.get(observation_id)
            if value is None or observation is None or not _path_exists(
                    observation["redacted_payload"], provenance.get("path")):
                raise UsageValidationError("raw field has no exact observed path")
        elif kind == "derivation":
            source_ids = provenance.get("source_observation_ids")
            if value is None or not isinstance(source_ids, list) or not source_ids or any(
                    source_id not in observation_by_id for source_id in source_ids) or not isinstance(
                        provenance.get("algorithm"), str) or not provenance.get(
                            "algorithm") or not isinstance(
                                provenance.get("algorithm_version"), str) or not provenance.get(
                                    "algorithm_version"):
                raise UsageValidationError("derivation needs observed inputs and versioned algorithm")
        else:
            raise UsageValidationError("unknown provenance kind")

    estimated = record.get("estimated_cost_usd")
    authoritative = record.get("authoritative_cost_usd")
    if isinstance(estimated, dict) and estimated.get("value") is not None:
        source_id = estimated["field_provenance"].get("observation_id")
        if estimated["field_provenance"].get("kind") != "raw" or observation_by_id[
                source_id].get("source_kind") != "local_static_rate":
            raise UsageValidationError("estimated cost requires local_static_rate")
    if isinstance(authoritative, dict) and authoritative.get("value") is not None:
        source_id = authoritative["field_provenance"].get("observation_id")
        if authoritative["field_provenance"].get("kind") != "raw" or observation_by_id[
                source_id].get("source_kind") != "billing_surface":
            raise UsageValidationError("authoritative cost requires billing_surface")


def _parse_expiry(value: Any) -> _datetime.datetime:
    if not isinstance(value, str):
        raise ExperimentBlockedError("approval expiry is required")
    try:
        parsed = _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExperimentBlockedError("approval expiry is invalid") from exc
    if parsed.tzinfo is None:
        raise ExperimentBlockedError("approval expiry must include timezone")
    return parsed.astimezone(_datetime.timezone.utc)


def validate_experiment_authority(approval: Optional[Dict[str, Any]],
                                  manifest: Optional[Dict[str, Any]],
                                  corpus_seal: Optional[Dict[str, Any]],
                                  execution_mode: str) -> None:
    """Fail closed before imports, factories, credential reads, or clients."""
    if execution_mode not in REAL_PROVIDER_MODES:
        return
    if not isinstance(approval, dict) or approval.get("schema") != "experiment_approval.v1":
        raise ExperimentBlockedError("matching experiment approval is required")
    if not isinstance(manifest, dict) or manifest.get("schema") != "pace_manifest.v1":
        raise ExperimentBlockedError("sealed pace manifest is required")
    if not isinstance(corpus_seal, dict) or corpus_seal.get(
            "schema") != "mission_control_corpus_seal.v1":
        raise ExperimentBlockedError("matching corpus seal is required")
    if _parse_expiry(approval.get("expires_at")) <= _datetime.datetime.now(
            _datetime.timezone.utc):
        raise ExperimentBlockedError("experiment approval has expired")
    if approval.get("user_created") is not True:
        raise ExperimentBlockedError("approval must be explicitly user-created")
    manifest_hash = manifest.get("manifest_hash")
    if not isinstance(manifest_hash, str) or not manifest_hash or approval.get(
            "manifest_hash") != manifest_hash:
        raise ExperimentBlockedError("approval does not bind the frozen manifest")
    for key in ("corpus_seal_hash", "resolved_model_ids", "execution_modes",
                "caps", "stop_rules"):
        manifest_value = manifest.get(key)
        approval_value = approval.get(key)
        if manifest_value is None or approval_value != manifest_value:
            raise ExperimentBlockedError("approval does not match manifest %s" % key)
    if execution_mode not in approval["execution_modes"]:
        raise ExperimentBlockedError("approval does not authorize this execution mode")


def run_experiment_attempt(execution_mode: str, *, approval: Optional[Dict[str, Any]] = None,
                           manifest: Optional[Dict[str, Any]] = None,
                           corpus_seal: Optional[Dict[str, Any]] = None,
                           provider_import: Optional[Callable[[], Any]] = None,
                           provider_factory: Optional[Callable[[], Any]] = None,
                           credential_reader: Optional[Callable[[], Any]] = None,
                           client_constructor: Optional[Callable[[], Any]] = None,
                           network_call: Optional[Callable[[], Any]] = None,
                           attempt_id: str = "experiment-attempt",
                           dispatch_id: str = "experiment-dispatch") -> Dict[str, Any]:
    """Execute one explicitly authorized attempt; offline modes touch no hooks."""
    if execution_mode in OFFLINE_MODES:
        return empty_usage_v1(execution_mode, attempt_id, dispatch_id)
    if execution_mode not in REAL_PROVIDER_MODES:
        raise ValueError("unknown execution mode: %r" % (execution_mode,))

    # This is intentionally before every supplied callback.  A caller cannot use
    # a rejected approval to import an SDK, inspect credentials, or build a client.
    validate_experiment_authority(approval, manifest, corpus_seal, execution_mode)
    if provider_import is not None:
        provider_import()
    if provider_factory is not None:
        provider_factory()
    if credential_reader is not None:
        credential_reader()
    if client_constructor is not None:
        client_constructor()
    if network_call is None:
        raise ValueError("real experiment execution requires a network_call")
    # Dispatch repeats the same fail-closed check at the final network boundary.
    # This prevents a caller from treating an earlier validation as a durable
    # authorization after a mutable approval object has changed in memory.
    validate_experiment_authority(approval, manifest, corpus_seal, execution_mode)
    result = network_call()
    if isinstance(result, ProviderAdapterResult):
        return normalize_provider_result(result, attempt_id, dispatch_id, execution_mode)
    if isinstance(result, str):
        return normalize_legacy_string(result, attempt_id, dispatch_id)
    raise TypeError("experiment network call must return ProviderAdapterResult")
