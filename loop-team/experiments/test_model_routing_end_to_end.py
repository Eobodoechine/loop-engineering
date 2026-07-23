"""[BEHAVIORAL] End-to-end contracts for the bounded model-routing experiment.

The isolated contract tests cover validators, reservations, and normalization.
These tests deliberately require the production entrypoint
``run_experiment.run_model_routing_experiment`` to join those pieces without
calling a real provider.  The entrypoint is expected to write the durable
ledgers and a trace under ``run_dir``; returned summaries are conveniences for
the caller, not substitutes for those persisted records.
"""
from __future__ import print_function

import copy
import importlib
import os
import sqlite3
import sys

import pytest


LOOP_TEAM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERIMENTS_DIR = os.path.join(LOOP_TEAM_DIR, "experiments")
RUNNER_DIR = os.path.join(LOOP_TEAM_DIR, "runner")
HARNESS_DIR = os.path.join(LOOP_TEAM_DIR, "harness")
for _path in (EXPERIMENTS_DIR, RUNNER_DIR, HARNESS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _entrypoint():
    return importlib.import_module("run_experiment")


def _execution():
    return importlib.import_module("experiment_execution")


def _routing():
    return importlib.import_module("model_routing")


def _dashboard():
    return importlib.import_module("dashboard")


def _receipt():
    """Valid deterministic signed-receipt fixture shared with H09/H10 tests."""
    return {
        "schema": "live_smoke_execution_receipt.v1",
        "receipt_id": "receipt-1",
        "command_or_probe_id": "sha256:probe",
        "input_hash": "a" * 64,
        "artifact_hash": "b" * 64,
        "started_at": "2026-07-16T00:00:00Z",
        "finished_at": "2026-07-16T00:00:01Z",
        "exit_code": 0,
        "result": "pass",
        "url_results": [],
        "dependency_results": [],
        "predicate_id": "signed-predicate.v1",
        "signer_key_id": "test-key",
        "signature": "valid-test-signature",
    }


def _manifest(caps=None):
    """Create the complete, fixed H01-H10 authority fixture."""
    hypotheses = []
    for index in range(1, 11):
        hypothesis_id = "H%02d" % index
        hypotheses.append({
            "hypothesis_id": hypothesis_id,
            "incumbent_policy_class": "INCUMBENT_%s" % hypothesis_id,
            "challenger_policy_class": "CHALLENGER_%s" % hypothesis_id,
            "scalar_endpoint": (
                "receipt_interpretation_success" if index >= 9 else "case_success"
            ),
            "held_out_effect_threshold": "pre_registered_%s" % hypothesis_id,
            "evaluation_case_ids": [
                "%s-eval-%02d" % (hypothesis_id, number)
                for number in range(24)
            ],
            "held_out_case_ids": [
                "%s-held-%02d" % (hypothesis_id, number)
                for number in range(12)
            ],
            "case_hashes": {"%s-case" % hypothesis_id: "a" * 64},
            "fixture_hashes": {"%s-fixture" % hypothesis_id: "b" * 64},
            "oracle_hash": "c" * 64,
        })
    return {
        "schema": "pace_manifest.v1",
        "manifest_hash": "d" * 64,
        "corpus_seal_hash": "e" * 64,
        "resolved_model_ids": {
            "INCUMBENT_H01": "fake-model-incumbent-2026-07-16",
            "CHALLENGER_H01": "fake-model-challenger-2026-07-16",
        },
        "execution_modes": ["openai_api"],
        "caps": caps or {
            "requests": 4, "tokens": 1000, "seconds": 60,
            "cost_usd": 5, "allowance_units": 0,
        },
        "stop_rules": {"no_real_promotion": True, "max_retries": 1},
        "alpha": 0.005,
        "lambda": 0.5,
        "min_discordant": 16,
        "max_pace_units": 24,
        "hypotheses": hypotheses,
    }


def _corpus_seal(manifest):
    return {
        "schema": "mission_control_corpus_seal.v1",
        "manifest_hash": manifest["manifest_hash"],
        "corpus_seal_hash": manifest["corpus_seal_hash"],
        "sealed_case_ids": {
            item["hypothesis_id"]: item["evaluation_case_ids"]
            for item in manifest["hypotheses"]
        },
        "sealed_held_out_case_ids": {
            item["hypothesis_id"]: item["held_out_case_ids"]
            for item in manifest["hypotheses"]
        },
    }


def _sealed_corpus(manifest, probe=None, isolation=None):
    """A complete real-corpus-shaped seal for entrypoint preflight tests."""
    seal = _corpus_seal(manifest)
    seal.update({
        "project_id": "future-confirmed-project",
        "dashboard_item_id": "future-confirmed-dashboard-item",
        "starting_status": "IN_PROGRESS",
        "commit_hash": "c" * 40,
        "tree_hash": "1" * 64,
        "dirty_state_hash": "2" * 64,
        "selection_rule_hash": "3" * 64,
        "oracle_hash": "4" * 64,
        "test_hash": "5" * 64,
        "fixture_ids": ["isolated-fixture-a", "isolated-fixture-b"],
        "expected_dashboard_advancement": "sealed-comparison-only",
        "probe": probe or {
            "status": "BLOCKED_EXTERNAL",
            "command": "current-isolated-probe",
            "exit_code": 0,
            "result": "success",
            "executed_at": "2026-07-16T00:00:00Z",
            "evidence_hash": "6" * 64,
            "missing_dependency": "refuted-prior-blocker",
        },
        "attempt_isolation": isolation or {
            "shared_writable_state": False,
            "quarantine_dir": "quarantine/by-attempt",
            "diff_inventory_path": "quarantine/post-run-diff-inventory.json",
        },
    })
    return seal


def _approval(manifest):
    return {
        "schema": "experiment_approval.v1",
        "user_created": True,
        "approval_hash": "f" * 64,
        "expires_at": "2036-07-16T00:00:00Z",
        "manifest_hash": manifest["manifest_hash"],
        "corpus_seal_hash": manifest["corpus_seal_hash"],
        "resolved_model_ids": manifest["resolved_model_ids"],
        "execution_modes": manifest["execution_modes"],
        "caps": manifest["caps"],
        "stop_rules": manifest["stop_rules"],
    }


def _typed_result():
    execution = _execution()
    return execution.ProviderAdapterResult(
        response_text="synthetic provider response",
        canonical_sdk_response_id="resp-synthetic-1",
        canonical_sdk_request_id="req-synthetic-1",
        raw_usage={
            "input_tokens": 100,
            "cache_read_input_tokens": 20,
            "output_tokens": 40,
            "output_tokens_details": {"reasoning_tokens": 15},
            "total_tokens": 140,
        },
        raw_response_payload_hash="1" * 64,
        raw_observation_id="raw-synthetic-1",
    )


def _run(api, run_dir, manifest, corpus_seal, approval=None, **overrides):
    """Invoke the one public experiment seam with explicit test-only hooks."""
    options = {
        "execution_mode": "deterministic_offline",
        "manifest": manifest,
        "corpus_seal": corpus_seal,
        "approval": approval,
        "run_dir": str(run_dir),
        "cap_ledger_path": str(run_dir / "cap-ledger.sqlite3"),
        "pace_ledger_path": str(run_dir / "pace-ledger.sqlite3"),
    }
    options.update(overrides)
    return api.run_model_routing_experiment(**options)


def test_offline_experiment_seals_corpus_records_all_hypotheses_and_cannot_integrate(tmp_path):
    """[BEHAVIORAL][AC10,AC13,AC15] Offline evidence is complete but non-promoting."""
    api = _entrypoint()
    manifest = _manifest()
    corpus_seal = _corpus_seal(manifest)
    touched = []

    def forbidden(name):
        touched.append(name)
        raise AssertionError("deterministic_offline reached %s" % name)

    result = _run(
        api, tmp_path, manifest, corpus_seal,
        provider_import=lambda: forbidden("provider import"),
        provider_factory=lambda: forbidden("provider factory"),
        credential_reader=lambda: forbidden("credential reader"),
        client_constructor=lambda: forbidden("client constructor"),
        network_call=lambda: forbidden("network"),
    )

    assert touched == []
    assert result["manifest_hash"] == manifest["manifest_hash"]
    assert result["corpus_seal_hash"] == manifest["corpus_seal_hash"]
    assert set(result["hypotheses"]) == set(
        "H%02d" % index for index in range(1, 11)
    )
    assert all(row["pace_row_persisted"] for row in result["hypotheses"].values())
    assert all(row["pace_finalized"] for row in result["hypotheses"].values())
    assert all(row["pace_status"] == "NO_PROMOTION"
               for row in result["hypotheses"].values())
    assert result["integration"] == {"allowed": False, "performed": False}

    trace = importlib.import_module("run_trace").read_trace(tmp_path)
    event_types = [event["event_type"] for event in trace]
    assert "experiment_attempt" in event_types
    assert "usage.v1" in event_types
    assert "evaluation_result" in event_types
    assert "pace_pair" in event_types
    assert "pace_finalized" in event_types
    assert "provisional_verdict" in event_types
    assert "evidence_release" in event_types
    assert all(event.get("integration") is not True for event in trace)


def test_synthetic_provider_requires_reserve_claim_retry_reconciliation_and_post_verdict_release(tmp_path):
    """[BEHAVIORAL][AC4,AC6,AC12,AC17] The fake boundary obeys real ordering rules."""
    api = _entrypoint()
    manifest = _manifest()
    corpus_seal = _corpus_seal(manifest)
    approval = _approval(manifest)
    callback_calls = []
    lifecycle = []

    def network_call():
        callback_calls.append("network")
        if len(callback_calls) == 1:
            raise TimeoutError("synthetic transient failure")
        return _typed_result()

    result = _run(
        api, tmp_path, manifest, corpus_seal, approval,
        execution_mode="openai_api",
        provider_import=lambda: lifecycle.append("provider_import"),
        provider_factory=lambda: lifecycle.append("provider_factory"),
        credential_reader=lambda: lifecycle.append("credential_reader"),
        client_constructor=lambda: lifecycle.append("client_constructor"),
        network_call=network_call,
        lifecycle_event_sink=lifecycle.append,
        max_retries=1,
    )

    assert callback_calls == ["network", "network"]
    attempts = result["attempts"]
    assert [attempt["retry_attempt"] for attempt in attempts] == [0, 1]
    assert attempts[0]["reservation_id"] != attempts[1]["reservation_id"]
    assert attempts[0]["retry_owner"] == attempts[1]["retry_owner"]
    assert all(attempt["reservation_claimed"] for attempt in attempts)
    assert attempts[-1]["reconciled"] is True
    assert result["usage"]["schema"] == "usage.v1"
    assert result["usage"]["token_fields"]["cache_read_input_tokens"]["value"] == 20
    assert result["usage"]["token_fields"]["reasoning_output_tokens"]["value"] == 15

    reserve = lifecycle.index("cap_reserved")
    claim = lifecycle.index("cap_claimed")
    first_network = lifecycle.index("network_attempt")
    provisional = lifecycle.index("provisional_verdict_persisted")
    release = lifecycle.index("post_verdict_evidence_released")
    assert reserve < claim < first_network < provisional < release
    assert lifecycle.count("provider_factory") == 1


def test_authority_mismatch_and_exhausted_caps_leave_fake_provider_untouched(tmp_path):
    """[BEHAVIORAL][AC12,AC17] No fallback or callback can cross either gate."""
    api = _entrypoint()
    manifest = _manifest()
    corpus_seal = _corpus_seal(manifest)
    approval = _approval(manifest)
    touched = []

    def touched_callback():
        touched.append("provider")
        return _typed_result()

    bad_approval = copy.deepcopy(approval)
    bad_approval["corpus_seal_hash"] = "mismatch"
    with pytest.raises(_execution().ExperimentBlockedError):
        _run(
            api, tmp_path / "mismatch", manifest, corpus_seal, bad_approval,
            execution_mode="openai_api", provider_factory=touched_callback,
            network_call=touched_callback,
        )
    assert touched == []

    exhausted_manifest = _manifest(caps={
        "requests": 0, "tokens": 0, "seconds": 0,
        "cost_usd": 0, "allowance_units": 0,
    })
    with pytest.raises(_routing().CapReservationError):
        _run(
            api, tmp_path / "exhausted", exhausted_manifest,
            _corpus_seal(exhausted_manifest), _approval(exhausted_manifest),
            execution_mode="openai_api", provider_factory=touched_callback,
            network_call=touched_callback,
        )
    assert touched == []


def test_trace_and_dashboard_use_typed_usage_provenance_and_cost_states(tmp_path):
    """[BEHAVIORAL][AC4,AC5] Typed totals replace placeholders without double-counting."""
    api = _entrypoint()
    manifest = _manifest()
    corpus_seal = _corpus_seal(manifest)
    result = _run(
        api, tmp_path, manifest, corpus_seal, _approval(manifest),
        execution_mode="openai_api",
        provider_factory=lambda: None,
        network_call=_typed_result,
        billing_observation={
            "observation_id": "billing-synthetic-1",
            "source_kind": "billing_surface",
            "authoritative_cost_usd": 0.019,
        },
        static_rate_observation={
            "observation_id": "rate-synthetic-1",
            "source_kind": "local_static_rate",
            "estimated_cost_usd": 0.020,
        },
    )

    usage = result["usage"]
    assert usage["token_fields"]["input_tokens"]["value"] == 100
    assert usage["token_fields"]["cache_read_input_tokens"]["value"] == 20
    assert usage["token_fields"]["output_tokens"]["value"] == 40
    assert usage["token_fields"]["reasoning_output_tokens"]["value"] == 15
    assert usage["token_fields"]["total_tokens_reported"]["value"] == 140
    assert usage["requested_model"]["value"] is not None
    assert usage["resolved_model_id"]["value"] is not None
    assert usage["requested_effort"]["value"] is not None
    assert usage["actual_effort"]["value"] is not None
    assert usage["estimated_cost_usd"]["value"] == pytest.approx(0.020)
    assert usage["authoritative_cost_usd"]["value"] == pytest.approx(0.019)
    assert usage["estimated_cost_usd"]["field_provenance"]["kind"] == "raw"
    assert usage["authoritative_cost_usd"]["field_provenance"]["kind"] == "raw"
    assert usage["token_fields"]["reasoning_output_tokens"]["value"] != 55

    dashboard = _dashboard()
    parsed = dashboard.parse_run(str(tmp_path))
    typed = parsed["trace"]["usage_totals"]
    assert typed["input_tokens"] == 100
    assert typed["cached_input_tokens"] == 20
    assert typed["output_tokens"] == 40
    assert typed["reasoning_output_tokens"] == 15
    assert typed["authoritative_cost_usd"] == pytest.approx(0.019)
    assert typed["estimated_cost_usd"] == pytest.approx(0.020)
    assert typed["unavailable_fields"] == []
    html = dashboard.render_html([parsed], [str(tmp_path)])
    assert "authoritative $0.02" in html
    assert "estimated $0.02" in html
    assert "unavailable" in html


def test_offline_entrypoint_executes_exact_frozen_cases_with_injected_objective_outcomes(
        tmp_path):
    """[BEHAVIORAL][AC1,AC10,AC13] Every frozen PACE and held-out case is durable evidence."""
    api = _entrypoint()
    manifest = _manifest()
    calls = []

    def case_executor(*, hypothesis_id, case_id, phase, scalar_endpoint, arm,
                      attempt_id, isolation_context):
        calls.append({
            "hypothesis_id": hypothesis_id,
            "case_id": case_id,
            "phase": phase,
            "scalar_endpoint": scalar_endpoint,
            "arm": arm,
            "attempt_id": attempt_id,
            "isolation_context": isolation_context,
        })
        assert scalar_endpoint == (
            "receipt_interpretation_success"
            if hypothesis_id in ("H09", "H10") else "case_success"
        )
        assert isolation_context["attempt_id"] == attempt_id
        assert isolation_context["fixture_namespace"].startswith("fixture-%s-" % arm)
        return {"endpoint": 0 if arm == "incumbent" else 1}

    result = _run(
        api, tmp_path, manifest, _sealed_corpus(manifest),
        case_executor=case_executor,
    )

    assert result["integration"] == {"allowed": False, "performed": False}
    assert set(result["hypotheses"]) == set("H%02d" % index for index in range(1, 11))

    connection = sqlite3.connect(str(tmp_path / "pace-ledger.sqlite3"))
    try:
        for hypothesis in manifest["hypotheses"]:
            hypothesis_id = hypothesis["hypothesis_id"]
            pace_rows = connection.execute(
                "SELECT case_id, incumbent_endpoint, challenger_endpoint, outcome, wealth_after "
                "FROM pace_pairs WHERE hypothesis_id=? ORDER BY case_id",
                (hypothesis_id,),
            ).fetchall()
            held_out_rows = connection.execute(
                "SELECT case_id, incumbent_endpoint, challenger_endpoint "
                "FROM held_out_pairs WHERE hypothesis_id=? ORDER BY case_id",
                (hypothesis_id,),
            ).fetchall()
            assert len(pace_rows) == 24
            assert {row[0] for row in pace_rows} == set(hypothesis["evaluation_case_ids"])
            assert {(row[1], row[2], row[3]) for row in pace_rows} == {(0, 1, "win")}
            assert sorted(row[4] for row in pace_rows) == pytest.approx(
                sorted(1.5 ** (number + 1) for number in range(24))
            )
            assert len(held_out_rows) == 12
            assert {row[0] for row in held_out_rows} == set(hypothesis["held_out_case_ids"])
            assert {(row[1], row[2]) for row in held_out_rows} == {(0, 1)}

            # Held-out confirmation cannot create a PACE unit or mutate its wealth.
            terminal = connection.execute(
                "SELECT status, reason FROM pace_terminal WHERE hypothesis_id=?",
                (hypothesis_id,),
            ).fetchone()
            assert terminal[0] == "NO_PROMOTION"
            assert "deterministic_offline" in terminal[1]
    finally:
        connection.close()

    for hypothesis in manifest["hypotheses"]:
        hypothesis_calls = [
            call for call in calls if call["hypothesis_id"] == hypothesis["hypothesis_id"]
        ]
        evaluation_calls = [call for call in hypothesis_calls if call["phase"] == "evaluation"]
        held_out_calls = [call for call in hypothesis_calls if call["phase"] == "held_out"]
        assert [call["case_id"] for call in evaluation_calls] == [
            case_id for case_id in hypothesis["evaluation_case_ids"] for _arm in
            ("incumbent", "challenger")
        ]
        assert [call["case_id"] for call in held_out_calls] == [
            case_id for case_id in hypothesis["held_out_case_ids"] for _arm in
            ("incumbent", "challenger")
        ]
        assert all(call["arm"] == expected_arm for call, expected_arm in zip(
            hypothesis_calls,
            [arm for _case in range(36) for arm in ("incumbent", "challenger")],
        ))
        assert hypothesis_calls.index(held_out_calls[0]) > hypothesis_calls.index(evaluation_calls[-1])


@pytest.mark.parametrize("target_hypothesis_id", ("H09", "H10"))
def test_receipt_disagreement_kills_before_later_rows_or_selection(
        tmp_path, target_hypothesis_id):
    """[BEHAVIORAL][AC7,AC8] Each receipt arm supplies independent evidence."""
    api = _entrypoint()
    manifest = _manifest()
    calls = []

    def case_executor(*, hypothesis_id, case_id, phase, scalar_endpoint, arm,
                      attempt_id, isolation_context):
        calls.append((hypothesis_id, case_id, phase, arm))
        if hypothesis_id != target_hypothesis_id:
            return {"endpoint": 0 if arm == "incumbent" else 1}
        assert phase == "evaluation"
        return {
            "endpoint": 1,
            "signed_receipt": _receipt(),
            "verifier_key": "test-key",
            "interpretation": {
                "receipt_status_label": "PASS" if arm == "incumbent" else "FAIL",
                "next_action_label": "retry",
            },
        }

    result = _run(
        api, tmp_path, manifest, _sealed_corpus(manifest),
        case_executor=case_executor,
    )

    connection = sqlite3.connect(str(tmp_path / "pace-ledger.sqlite3"))
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM pace_pairs WHERE hypothesis_id=?",
            (target_hypothesis_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM held_out_pairs WHERE hypothesis_id=?",
            (target_hypothesis_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT status, reason FROM pace_terminal WHERE hypothesis_id=?",
            (target_hypothesis_id,),
        ).fetchone() == ("KILL", "receipt_status_disagreement")
    finally:
        connection.close()
    assert result["hypotheses"][target_hypothesis_id]["router_recommendation"] is None
    hypothesis_index = int(target_hypothesis_id[1:]) - 1
    assert [call for call in calls if call[0] == target_hypothesis_id] == [
        (target_hypothesis_id, manifest["hypotheses"][hypothesis_index]["evaluation_case_ids"][0],
         "evaluation", "incumbent"),
        (target_hypothesis_id, manifest["hypotheses"][hypothesis_index]["evaluation_case_ids"][0],
         "evaluation", "challenger"),
    ]


@pytest.mark.parametrize("seal_mutation", (
    lambda seal: seal.update({"project_id": ""}),
    lambda seal: seal.update({"probe": {"status": "NOT_TESTED"}}),
    lambda seal: seal["attempt_isolation"].update({"shared_writable_state": True}),
    lambda seal: seal["attempt_isolation"].pop("quarantine_dir"),
    lambda seal: seal["attempt_isolation"].pop("diff_inventory_path"),
))
def test_complete_seal_and_current_probe_gate_every_arm_callback(tmp_path, seal_mutation):
    """[BEHAVIORAL][AC14,AC15] Invalid/isolation-incomplete seals fail before executor use."""
    api = _entrypoint()
    manifest = _manifest()
    seal = _sealed_corpus(manifest)
    seal_mutation(seal)
    calls = []

    def case_executor(**_kwargs):
        calls.append("executor")
        return {"endpoint": 0}

    with pytest.raises(_execution().ExperimentBlockedError):
        _run(api, tmp_path, manifest, seal, case_executor=case_executor)
    assert calls == []


def test_current_probe_records_external_blocker_or_allows_objective_execution(tmp_path):
    """[BEHAVIORAL][AC14] A current probe either records its dependency or refutes the blocker."""
    api = _entrypoint()
    manifest = _manifest()
    blocked_seal = _sealed_corpus(manifest, probe={
        "status": "BLOCKED_EXTERNAL",
        "command": "current-isolated-probe",
        "exit_code": 1,
        "result": "required service unavailable",
        "executed_at": "2026-07-16T00:00:00Z",
        "evidence_hash": "7" * 64,
        "missing_dependency": "sealed external service fixture",
    })
    blocked_calls = []

    def blocked_executor(**_kwargs):
        blocked_calls.append("executor")
        return {"endpoint": 0}

    blocked = _run(
        api, tmp_path / "blocked", manifest, blocked_seal,
        case_executor=blocked_executor,
    )
    assert blocked_calls == []
    assert blocked["blocker"] == {
        "status": "BLOCKED_EXTERNAL",
        "missing_dependency": "sealed external service fixture",
    }

    allowed_calls = []

    def allowed_executor(*, arm, **_kwargs):
        allowed_calls.append("executor")
        return {"endpoint": 0 if arm == "incumbent" else 1}

    allowed = _run(
        api, tmp_path / "allowed", manifest, _sealed_corpus(manifest),
        case_executor=allowed_executor,
    )
    assert allowed["blocker"] == {"status": "PROCEED"}
    assert len(allowed_calls) == 2 * 10 * (24 + 12)
