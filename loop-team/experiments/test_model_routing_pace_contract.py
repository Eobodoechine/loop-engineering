"""[BEHAVIORAL] Contract tests for the bounded model-routing experiment layer.

The production seam is intentionally named ``model_routing`` and belongs beside
``run_experiment.py``.  These tests use only deterministic fixtures and a local
SQLite path; none authorizes or invokes a provider.
"""
import importlib
import os
import sys

import pytest


EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
if EXPERIMENTS_DIR not in sys.path:
    sys.path.insert(0, EXPERIMENTS_DIR)


def _routing():
    """Load the future bounded experiment implementation at test execution time."""
    return importlib.import_module("model_routing")


def _manifest():
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
            "evaluation_case_ids": ["%s-eval-%02d" % (hypothesis_id, n) for n in range(24)],
            "held_out_case_ids": ["%s-held-%02d" % (hypothesis_id, n) for n in range(12)],
            "case_hashes": {"%s-case" % hypothesis_id: "a" * 64},
            "fixture_hashes": {"%s-fixture" % hypothesis_id: "b" * 64},
            "oracle_hash": "c" * 64,
        })
    return {
        "schema": "pace_manifest.v1",
        "manifest_hash": "d" * 64,
        "alpha": 0.005,
        "lambda": 0.5,
        "min_discordant": 16,
        "max_pace_units": 24,
        "hypotheses": hypotheses,
    }


def _reservation_key(retry_attempt=0, idempotency_key="idem-1"):
    return {
        "approval_hash": "approval-hash",
        "manifest_hash": "manifest-hash",
        "hypothesis_id": "H01",
        "attempt_id": "attempt-1",
        "dispatch_id": "dispatch-1",
        "retry_attempt": retry_attempt,
        "idempotency_key": idempotency_key,
    }


def test_manifest_requires_exact_h01_through_h10_and_disjoint_24_12_splits():
    """[BEHAVIORAL][AC1,AC2,AC11] Frozen PACE manifests reject structural drift."""
    api = _routing()
    manifest = _manifest()
    api.validate_pace_manifest(manifest)

    missing = _manifest()
    missing["hypotheses"].pop()
    with pytest.raises(api.ManifestValidationError):
        api.validate_pace_manifest(missing)

    overlap = _manifest()
    overlap["hypotheses"][0]["held_out_case_ids"][0] = "H01-eval-00"
    with pytest.raises(api.ManifestValidationError):
        api.validate_pace_manifest(overlap)


def test_pace_ledger_persists_one_row_per_case_and_terminal_precedes_selection(tmp_path):
    """[BEHAVIORAL][AC2,AC10,AC11] Repeats cannot add PACE wealth or bypass KILL."""
    api = _routing()
    ledger_path = tmp_path / "pace.sqlite3"
    ledger = api.PaceLedger(str(ledger_path), manifest=_manifest())

    first = ledger.record_pair(
        hypothesis_id="H01", case_id="H01-eval-00", incumbent_endpoint=0,
        challenger_endpoint=1, fixture_hashes={"fixture": "f" * 64},
        reliability_repeat_refs=["repeat-0"],
    )
    repeated = ledger.record_pair(
        hypothesis_id="H01", case_id="H01-eval-00", incumbent_endpoint=0,
        challenger_endpoint=1, fixture_hashes={"fixture": "f" * 64},
        reliability_repeat_refs=["repeat-1"],
    )
    assert repeated["created"] is False
    assert repeated["wealth_after"] == first["wealth_after"]
    assert ledger.row_count("H01") == 1

    outcome = ledger.finalize("H01", terminal_reason="critical_false_pass")
    assert outcome["status"] == "KILL"
    assert outcome["router_recommendation"] is None


def test_sqlite_cap_ledger_is_idempotent_fail_closed_and_gives_retry_one_owner(tmp_path):
    """[BEHAVIORAL][AC17] Reservations are pre-network, durable, and per retry."""
    api = _routing()
    ledger = api.CapLedger(str(tmp_path / "caps.sqlite3"), caps={"requests": 2, "tokens": 20})

    original = ledger.reserve(_reservation_key(), requested={"requests": 1, "tokens": 10})
    duplicate = ledger.reserve(_reservation_key(), requested={"requests": 1, "tokens": 10})
    assert original["reservation_id"] == duplicate["reservation_id"]
    assert ledger.remaining()["requests"] == 1

    retry = ledger.reserve(_reservation_key(retry_attempt=1), requested={"requests": 1, "tokens": 10})
    assert retry["reservation_id"] != original["reservation_id"]
    assert retry["owner"] == ledger.retry_owner(_reservation_key(retry_attempt=1))

    crashed = ledger.mark_crashed(original["reservation_id"])
    assert crashed["state"] == "PENDING_RECONCILIATION"
    with pytest.raises(api.CapReservationError):
        ledger.reserve(_reservation_key(2, "idem-2"), requested={"requests": 1, "tokens": 1})
    ledger.reconcile(original["reservation_id"], raw_observation_id="raw-observation-1")


def test_final_cap_unit_has_exactly_one_multiprocess_winner(tmp_path):
    """[BEHAVIORAL][AC17] BEGIN IMMEDIATE prevents two processes reserving one unit."""
    api = _routing()
    db_path = str(tmp_path / "final-unit.sqlite3")
    api.CapLedger(db_path, caps={"requests": 1, "tokens": 10})

    outcomes = api.reserve_final_unit_concurrently(
        db_path,
        [_reservation_key(0, "contender-a"), _reservation_key(0, "contender-b")],
        requested={"requests": 1, "tokens": 1},
    )
    assert [item["state"] for item in outcomes].count("RESERVED") == 1
    assert [item["state"] for item in outcomes].count("BLOCKED_CAP") == 1
    assert all(item["network_called"] is False for item in outcomes)


def test_compatibility_reports_only_interpreters_that_were_actually_executed():
    """[BEHAVIORAL][AC19] Missing Python versions remain unverified, never passed."""
    api = _routing()
    report = api.compatibility_report(required_shared=[(3, 9), (3, 10), (3, 11), (3, 12)])
    current = "%d.%d" % sys.version_info[:2]
    assert current in report["executed_versions"]
    assert current in report["verified_versions"]
    assert set(report["verified_versions"]).issubset(set(report["executed_versions"]))
    for version in report["missing_versions"]:
        assert version not in report["verified_versions"]
