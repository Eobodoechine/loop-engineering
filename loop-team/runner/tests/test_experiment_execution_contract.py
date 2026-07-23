"""[BEHAVIORAL] Runner contracts for typed usage and experiment-only dispatch.

The future implementation lives in ``runner.experiment_execution``.  Tests keep
ordinary runner behavior separate from the explicit experiment execution context.
"""
import importlib
import hashlib
import os
import sys
from pathlib import Path

import pytest


LOOP_TEAM_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if LOOP_TEAM_DIR not in sys.path:
    sys.path.insert(0, LOOP_TEAM_DIR)


def _execution():
    return importlib.import_module("runner.experiment_execution")


def _raw_provenance(observation_id, path):
    return {
        "kind": "raw",
        "observation_id": observation_id,
        "path": path,
        "source_observation_ids": [],
        "algorithm": None,
        "algorithm_version": None,
        "unavailable_reason": None,
    }


def test_typed_provider_result_preserves_canonical_ids_usage_hashes_and_non_additive_breakdowns():
    """[BEHAVIORAL][AC4,AC5,AC16] Usage comes from a typed boundary result."""
    api = _execution()
    result = api.ProviderAdapterResult(
        response_text="typed response",
        canonical_sdk_response_id="resp-canonical",
        canonical_sdk_request_id="req-canonical",
        raw_usage={
            "input_tokens": 100,
            "output_tokens": 40,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 20,
            "output_tokens_details": {"reasoning_tokens": 30},
            "total_tokens": 140,
        },
        raw_response_payload_hash="a" * 64,
        raw_observation_id="raw-observation-1",
    )
    record = api.normalize_provider_result(
        result=result, attempt_id="attempt-1", dispatch_id="dispatch-1",
        execution_mode="openai_api",
    )
    assert record["canonical_sdk_response_id"]["value"] == "resp-canonical"
    assert record["canonical_sdk_request_id"]["value"] == "req-canonical"
    assert record["token_fields"]["reasoning_output_tokens"]["value"] == 30
    assert record["token_fields"]["total_tokens_reported"]["value"] == 140
    assert record["derived_total_tokens"] is None
    assert record["raw_observations"][0]["payload_hash"] == "a" * 64
    assert record["attempt_payload_hash"]["value"]
    assert record["dispatch_payload_hash"]["value"]
    api.validate_usage_v1(record)


@pytest.mark.parametrize("forged_hash", ["!" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_typed_provider_result_requires_exact_hex_sha256_not_a_same_length_label(forged_hash):
    """[BEHAVIORAL] Payload identities are strict SHA-256 values, never self-attested labels."""
    api = _execution()
    with pytest.raises(ValueError):
        api.ProviderAdapterResult(
            response_text="typed response",
            canonical_sdk_response_id="resp-canonical",
            canonical_sdk_request_id="req-canonical",
            raw_usage=None,
            raw_response_payload_hash=forged_hash,
            raw_observation_id="raw-observation-1",
        )


def test_usage_provenance_rejects_fabricated_values_and_keeps_cost_authority_separate():
    """[BEHAVIORAL][AC4,AC5] Nulls are explicit and billing is not static-rate usage."""
    api = _execution()
    record = api.empty_usage_v1("deterministic_offline", attempt_id="a", dispatch_id="d")
    assert record["provider"]["value"] is None
    assert record["provider"]["field_provenance"]["kind"] == "unavailable"
    assert "deterministic_offline" in record["provider"]["field_provenance"]["unavailable_reason"]

    record["estimated_cost_usd"] = {
        "value": 0.12,
        "field_provenance": _raw_provenance("rate-observation", "$.rates.estimated"),
    }
    record["authoritative_cost_usd"] = {
        "value": 0.12,
        "field_provenance": _raw_provenance("rate-observation", "$.rates.estimated"),
    }
    with pytest.raises(api.UsageValidationError):
        api.validate_usage_v1(record)


def test_legacy_string_stays_ordinary_loop_compatible_but_is_experiment_ineligible():
    """[BEHAVIORAL][AC16,AC18] No string parser fabricates provider telemetry."""
    api = _execution()
    record = api.normalize_legacy_string("ordinary Loop Team response", attempt_id="a", dispatch_id="d")
    assert record["response_text"] == "ordinary Loop Team response"
    assert record["provider"]["value"] is None
    assert record["resolved_model_id"]["value"] is None
    assert record["actual_effort"]["value"] is None
    assert record["experiment_eligible"] is False
    assert record["promotion_eligible"] is False


def test_offline_and_synthetic_execution_never_touch_provider_or_credentials():
    """[BEHAVIORAL][AC13,AC18] Offline paths fail the test if any provider hook runs."""
    api = _execution()

    def forbidden(*args, **kwargs):
        raise AssertionError("offline/synthetic execution touched a provider boundary")

    for mode in ("deterministic_offline", "synthetic_test"):
        attempt = api.run_experiment_attempt(
            execution_mode=mode,
            provider_import=forbidden,
            provider_factory=forbidden,
            credential_reader=forbidden,
            client_constructor=forbidden,
            network_call=forbidden,
        )
        assert attempt["provider"]["value"] is None
        assert attempt["resolved_model_id"]["value"] is None
        assert attempt["actual_effort"]["value"] is None
        assert attempt["promotion_eligible"] is False


def test_real_experiment_rejects_bad_approval_before_import_factory_or_credentials():
    """[BEHAVIORAL][AC12,AC18] Approval/seal validation is pre-provider and fail closed."""
    api = _execution()
    calls = []

    def forbidden(name):
        calls.append(name)
        raise AssertionError("provider boundary was reached after rejected approval")

    with pytest.raises(api.ExperimentBlockedError) as exc_info:
        api.run_experiment_attempt(
            execution_mode="openai_api",
            approval={"schema": "experiment_approval.v1", "expires_at": "2000-01-01T00:00:00Z"},
            manifest={"schema": "pace_manifest.v1", "manifest_hash": "mismatch"},
            corpus_seal={"schema": "mission_control_corpus_seal.v1"},
            provider_import=lambda: forbidden("import"),
            provider_factory=lambda: forbidden("factory"),
            credential_reader=lambda: forbidden("credential"),
            client_constructor=lambda: forbidden("client"),
            network_call=lambda: forbidden("network"),
        )
    assert exc_info.value.code == "BLOCKED_APPROVAL_OR_SEAL"
    assert calls == []


def test_codex_subscription_current_usage_derives_observed_total_without_inventing_provider_total():
    """[RED][COMPAT] Current JSONL has no provider total and keeps every breakdown non-additive."""
    api = _execution()
    result = api.ProviderAdapterResult(
        response_text="done",
        canonical_sdk_response_id="resp-current",
        canonical_sdk_request_id="req-current",
        raw_usage={
            "input_tokens": 100,
            "cached_input_tokens": 30,
            "output_tokens": 20,
            "reasoning_output_tokens": 10,
        },
        raw_response_payload_hash="b" * 64,
        raw_observation_id="current-jsonl-observation",
    )

    record = api.normalize_provider_result(
        result=result,
        attempt_id="attempt-current",
        dispatch_id="dispatch-current",
        execution_mode="codex_subscription",
    )

    assert record["token_fields"]["input_tokens"]["value"] == 100
    assert record["token_fields"]["cache_read_input_tokens"]["value"] == 30
    assert record["token_fields"]["output_tokens"]["value"] == 20
    assert record["token_fields"]["reasoning_output_tokens"]["value"] == 10
    assert record["token_fields"]["total_tokens_reported"]["value"] is None
    assert record["derived_total_tokens"]["value"] == 120
    assert record["derived_total_tokens"]["field_provenance"]["kind"] == "derivation"
    assert record["derived_total_tokens"]["field_provenance"]["algorithm"] == (
        "input_tokens_plus_output_tokens"
    )


def test_codex_subscription_usage_rejects_every_usd_observation_source():
    """[RED][COMPAT] Subscription telemetry has no USD authority, including a billing-like payload."""
    api = _execution()
    result = api.ProviderAdapterResult(
        response_text="done",
        canonical_sdk_response_id="resp-subscription",
        canonical_sdk_request_id="req-subscription",
        raw_usage={"input_tokens": 1, "output_tokens": 1},
        raw_response_payload_hash="c" * 64,
        raw_observation_id="subscription-observation",
    )
    record = api.normalize_provider_result(
        result=result,
        attempt_id="attempt-subscription",
        dispatch_id="dispatch-subscription",
        execution_mode="codex_subscription",
    )

    with pytest.raises(api.UsageValidationError, match="codex subscription.*USD"):
        api.attach_cost_observation(record, {
            "observation_id": "forbidden-usd",
            "source_kind": "billing_surface",
            "authoritative_cost_usd": 0.01,
        })


@pytest.mark.parametrize("module_name", [
    "runner.codex_exec_adapter",
    "runner.codex_subscription_pilot",
])
def test_production_constants_bind_the_reviewed_current_spec_bytes(module_name):
    """[RED][PRODUCTION-PREFLIGHT] Production authority uses the reviewed final spec."""
    module = importlib.import_module(module_name)
    spec_path = Path(LOOP_TEAM_DIR) / (
        "runs/2026-07-16_model-routing-pace/specs/codex_product_pilot.md"
    )
    reviewed_digest = hashlib.sha256(spec_path.read_bytes()).hexdigest()

    assert reviewed_digest == "eab8f4f80758beaf2ea3326df4a176e091778a0f9dbea23dbf5cccea633d06e8"
    assert module.SPEC_SHA256 == reviewed_digest
