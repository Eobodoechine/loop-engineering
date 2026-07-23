"""[BEHAVIORAL] Eval contracts for withholding, signed smoke, and case seals."""
import importlib
import os
import sys

import pytest


EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
if EVALS_DIR not in sys.path:
    sys.path.insert(0, EVALS_DIR)


def _evals():
    return importlib.import_module("model_routing_evals")


def _packet():
    return {
        "schema": "blinded_judge_packet.v1",
        "packet_id": "packet-1",
        "case_id": "case-1",
        "role_contract": "sha256:role",
        "artifact": "sha256:artifact",
        "oracle_interface": "sha256:oracle",
        "evidence": {"allowed": "task evidence"},
    }


def _receipt():
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


def test_blinded_packet_excludes_withheld_fields_and_provisional_hash_precedes_release(tmp_path):
    """[BEHAVIORAL][AC6] No arm/model/verdict/telemetry leaks before provisional verdict."""
    api = _evals()
    api.validate_blinded_judge_packet(_packet())

    leaked = _packet()
    leaked["model"] = "provider-model-id"
    with pytest.raises(api.PacketValidationError):
        api.validate_blinded_judge_packet(leaked)

    with pytest.raises(api.VerdictChainError):
        api.build_post_verdict_evidence_packet(_packet(), provisional_hash=None)
    provisional = api.persist_provisional_verdict(
        ledger_path=str(tmp_path / "verdict-ledger.jsonl"), packet=_packet(),
        verdict="PASS", evidence_refs=["sha256:evidence"], actor_id="blind-judge",
    )
    post = api.build_post_verdict_evidence_packet(_packet(), provisional_hash=provisional["hash"])
    assert post["blinded_packet_hash"] == provisional["blinded_packet_hash"]
    assert post["provisional_verdict_hash"] == provisional["hash"]


def test_signed_receipt_predicate_is_the_only_smoke_status_authority_and_h09_h10_kill():
    """[BEHAVIORAL][AC7,AC8] An LLM cannot alter smoke status or survive disagreement."""
    api = _evals()
    receipt = _receipt()
    signed_status = api.validate_signed_smoke_receipt(receipt, verifier_key="test-key")
    assert signed_status == "PASS"

    paired = api.evaluate_receipt_interpretation(
        receipt=receipt,
        incumbent={"receipt_status_label": "PASS", "next_action_label": "retry"},
        challenger={"receipt_status_label": "FAIL", "next_action_label": "retry"},
        signed_status=signed_status,
    )
    assert paired["status"] == "KILL"
    assert paired["reason"] == "receipt_status_disagreement"
    assert paired["router_recommendation"] is None

    with pytest.raises(api.SmokeStatusAuthorityError):
        api.assert_model_cannot_emit_smoke_status(model_output={"smoke_status": "PASS"})


def test_case_seal_requires_current_probe_and_isolation_blocks_product_integration(tmp_path):
    """[BEHAVIORAL][AC14,AC15,AC21] Blockers need probes; PACE never changes product state."""
    api = _evals()
    seal = {
        "schema": "mission_control_corpus_seal.v1",
        "project_id": "",  # Real future IDs are supplied only in a future frozen manifest.
        "dashboard_item_id": "",
        "starting_status": "",
        "commit_hash": "c" * 40,
        "tree_hash": "d" * 64,
        "dirty_state_hash": "e" * 64,
        "selection_rule_hash": "f" * 64,
        "oracle_hash": "a" * 64,
        "test_hash": "b" * 64,
        "fixture_ids": [],
        "expected_dashboard_advancement": "",
        "probe": {"status": "NOT_TESTED"},
    }
    with pytest.raises(api.CorpusSealError):
        api.validate_mission_control_corpus_seal(seal)

    probe = {
        "status": "BLOCKED_EXTERNAL",
        "command": "probe-current-isolated-case",
        "exit_code": 1,
        "result": "dependency unavailable",
        "executed_at": "2026-07-16T00:00:00Z",
        "evidence_hash": "c" * 64,
        "missing_dependency": "named external fixture",
    }
    assert api.classify_blocker(probe) == "BLOCKED_EXTERNAL"
    probe["exit_code"] = 0
    probe["result"] = "success"
    assert api.classify_blocker(probe) == "PROCEED"

    isolated = api.prepare_isolated_attempt(
        str(tmp_path), attempt_id="attempt-1", fixture_namespace="sealed-fixture-attempt-1",
    )
    assert isolated["worktree"] != isolated["fixture_namespace"]
    assert isolated["diff_inventory_path"]
    assert isolated["quarantine_dir"]
    with pytest.raises(api.UnattributedWriteError):
        api.finalize_isolated_attempt(
            isolated, observed_writes=["unattributed-output.txt"], attributed_writes=[],
        )
    with pytest.raises(api.ProductIntegrationForbidden):
        api.assert_pace_cannot_integrate(
            action="mark_dashboard_complete", product_verifier_receipt=None, human_promotion=False,
        )
