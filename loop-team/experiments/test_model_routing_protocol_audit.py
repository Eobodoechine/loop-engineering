"""[BEHAVIORAL] Regressions from the final model-routing protocol audit.

These tests exercise only the deterministic-offline experiment entrypoint. They
never construct a provider client, read credentials, make a network request, or
open a browser.
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
EVALS_DIR = os.path.join(LOOP_TEAM_DIR, "evals")
for _path in (EXPERIMENTS_DIR, RUNNER_DIR, EVALS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _entrypoint():
    return importlib.import_module("run_experiment")


def _execution():
    return importlib.import_module("experiment_execution")


def _evals():
    return importlib.import_module("model_routing_evals")


def _trace():
    return importlib.import_module("run_trace")


def _manifest():
    hypotheses = []
    for number in range(1, 11):
        hypothesis_id = "H%02d" % number
        hypotheses.append({
            "hypothesis_id": hypothesis_id,
            "incumbent_policy_class": "INCUMBENT_%s" % hypothesis_id,
            "challenger_policy_class": "CHALLENGER_%s" % hypothesis_id,
            "scalar_endpoint": (
                "receipt_interpretation_success" if number >= 9 else "case_success"
            ),
            "held_out_effect_threshold": "pre_registered_%s" % hypothesis_id,
            "evaluation_case_ids": [
                "%s-eval-%02d" % (hypothesis_id, index) for index in range(24)
            ],
            "held_out_case_ids": [
                "%s-held-%02d" % (hypothesis_id, index) for index in range(12)
            ],
            "case_hashes": {"%s-case" % hypothesis_id: "a" * 64},
            "fixture_hashes": {"%s-fixture" % hypothesis_id: "b" * 64},
            "oracle_hash": "c" * 64,
        })
    return {
        "schema": "pace_manifest.v1",
        "manifest_hash": "d" * 64,
        "corpus_seal_hash": "e" * 64,
        "resolved_model_ids": {},
        "execution_modes": ["deterministic_offline"],
        "caps": {
            "requests": 0,
            "tokens": 0,
            "seconds": 0,
            "cost_usd": 0,
            "allowance_units": 0,
        },
        "stop_rules": {"no_real_promotion": True},
        "alpha": 0.005,
        "lambda": 0.5,
        "min_discordant": 16,
        "max_pace_units": 24,
        "hypotheses": hypotheses,
    }


def _corpus_seal(manifest, complete=False):
    seal = {
        "schema": "mission_control_corpus_seal.v1",
        "manifest_hash": manifest["manifest_hash"],
        "corpus_seal_hash": manifest["corpus_seal_hash"],
        "sealed_case_ids": {
            item["hypothesis_id"]: list(item["evaluation_case_ids"])
            for item in manifest["hypotheses"]
        },
        "sealed_held_out_case_ids": {
            item["hypothesis_id"]: list(item["held_out_case_ids"])
            for item in manifest["hypotheses"]
        },
    }
    if complete:
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
            "probe": {
                "status": "BLOCKED_EXTERNAL",
                "command": "current-isolated-probe",
                "exit_code": 0,
                "result": "success",
                "executed_at": "2026-07-16T00:00:00Z",
                "evidence_hash": "6" * 64,
                "missing_dependency": "refuted-prior-blocker",
            },
            "attempt_isolation": {
                "shared_writable_state": False,
                "quarantine_dir": "quarantine/by-attempt",
                "diff_inventory_path": "quarantine/post-run-diff-inventory.json",
            },
        })
    return seal


def _run(api, run_dir, manifest, seal, **overrides):
    options = {
        "execution_mode": "deterministic_offline",
        "manifest": manifest,
        "corpus_seal": seal,
        "run_dir": str(run_dir),
        "cap_ledger_path": str(run_dir / "cap-ledger.sqlite3"),
        "pace_ledger_path": str(run_dir / "pace-ledger.sqlite3"),
    }
    options.update(overrides)
    return api.run_model_routing_experiment(**options)


def _arm_objective_result(*, arm, **_kwargs):
    """One callback result is evidence for one arm, never a manufactured pair."""
    return {"endpoint": 0 if arm == "incumbent" else 1}


def test_default_offline_path_is_fail_closed_or_persists_the_complete_protocol(tmp_path):
    """[BEHAVIORAL] A public default cannot call a one-row run complete."""
    api = _entrypoint()
    manifest = _manifest()
    try:
        result = _run(api, tmp_path, manifest, _corpus_seal(manifest))
    except _execution().ExperimentBlockedError:
        return

    connection = sqlite3.connect(str(tmp_path / "pace-ledger.sqlite3"))
    try:
        for hypothesis in manifest["hypotheses"]:
            hypothesis_id = hypothesis["hypothesis_id"]
            assert connection.execute(
                "SELECT COUNT(*) FROM pace_pairs WHERE hypothesis_id=?",
                (hypothesis_id,),
            ).fetchone()[0] == 24
            assert connection.execute(
                "SELECT COUNT(*) FROM held_out_pairs WHERE hypothesis_id=?",
                (hypothesis_id,),
            ).fetchone()[0] == 12
            assert result["hypotheses"][hypothesis_id]["pace_row_persisted"] is True
    finally:
        connection.close()

    events = _trace().read_trace(tmp_path)
    usage_events = [event for event in events if event["event_type"] == "usage.v1"]
    attempt_events = [event for event in events if event["event_type"] == "experiment_attempt"]
    assert len(usage_events) == 720
    assert len(attempt_events) == 720


def test_complete_assignment_run_invokes_each_arm_and_binds_720_unique_receipts(tmp_path):
    """[BEHAVIORAL] Each frozen assignment executes both arms in separate contexts."""
    api = _entrypoint()
    manifest = _manifest()
    callback_calls = []

    def case_executor(*, hypothesis_id, case_id, phase, scalar_endpoint, arm,
                      attempt_id, isolation_context):
        assert isolation_context["attempt_id"] == attempt_id
        assert attempt_id in isolation_context["worktree"]
        assert isolation_context["fixture_namespace"].startswith("fixture-%s-" % arm)
        callback_calls.append({
            "hypothesis_id": hypothesis_id,
            "case_id": case_id,
            "phase": phase,
            "scalar_endpoint": scalar_endpoint,
            "arm": arm,
            "attempt_id": attempt_id,
            "isolation_context": isolation_context,
        })
        return _arm_objective_result(
            arm=arm, hypothesis_id=hypothesis_id, case_id=case_id,
            phase=phase, scalar_endpoint=scalar_endpoint,
            attempt_id=attempt_id, isolation_context=isolation_context,
        )

    _run(
        api, tmp_path, manifest, _corpus_seal(manifest, complete=True),
        case_executor=case_executor,
    )

    assert len(callback_calls) == 720
    assert {call["arm"] for call in callback_calls} == {"incumbent", "challenger"}
    assert sum(call["arm"] == "incumbent" for call in callback_calls) == 360
    assert sum(call["arm"] == "challenger" for call in callback_calls) == 360
    by_assignment = {}
    for call in callback_calls:
        assignment = (call["hypothesis_id"], call["case_id"], call["phase"])
        by_assignment.setdefault(assignment, {})[call["arm"]] = call["isolation_context"]
    assert len(by_assignment) == 360
    assert all(set(arms) == {"incumbent", "challenger"}
               for arms in by_assignment.values())
    for arms in by_assignment.values():
        incumbent = arms["incumbent"]
        challenger = arms["challenger"]
        for field in ("attempt_id", "worktree", "fixture_namespace", "fixture_dir",
                      "quarantine_dir", "diff_inventory_path", "attribution_hash"):
            assert incumbent[field] != challenger[field]
    events = _trace().read_trace(tmp_path)
    usage_events = [event for event in events if event["event_type"] == "usage.v1"]
    assert len(usage_events) == 720

    attempt_ids = []
    bindings = set()
    for event in usage_events:
        usage = event["usage"]
        attempt_ids.append(usage["attempt_id"]["value"])
        bindings.add((
            usage["hypothesis_id"]["value"],
            usage["case_id"]["value"],
            usage["split"]["value"],
            usage["arm"]["value"],
        ))
    assert len(set(attempt_ids)) == 720
    assert len(bindings) == 720


def test_each_arm_attempt_gets_unique_isolation_and_finalizes(tmp_path, monkeypatch):
    """[BEHAVIORAL] Isolation is per arm attempt and cannot be a one-time preflight."""
    api = _entrypoint()
    evals = _evals()
    manifest = _manifest()
    prepared = []
    finalized = []
    original_prepare = evals.prepare_isolated_attempt
    original_finalize = evals.finalize_isolated_attempt

    def track_prepare(*args, **kwargs):
        context = original_prepare(*args, **kwargs)
        prepared.append(context)
        return context

    def track_finalize(*args, **kwargs):
        receipt = original_finalize(*args, **kwargs)
        finalized.append((args[0], receipt))
        return receipt

    monkeypatch.setattr(evals, "prepare_isolated_attempt", track_prepare)
    monkeypatch.setattr(evals, "finalize_isolated_attempt", track_finalize)
    _run(
        api, tmp_path / "complete", manifest, _corpus_seal(manifest, complete=True),
        case_executor=_arm_objective_result,
    )

    case_contexts = [
        context for context in prepared
        if not context["attempt_id"].startswith("preflight-")
    ]
    finalized_contexts = [
        context for context, _receipt in finalized
        if not context["attempt_id"].startswith("preflight-")
    ]
    assert len(case_contexts) == 720
    assert len(finalized_contexts) == 720
    assert len({context["worktree"] for context in case_contexts}) == 720
    assert len({context["fixture_namespace"] for context in case_contexts}) == 720
    assert len({context["fixture_dir"] for context in case_contexts}) == 720
    assert len({context["quarantine_dir"] for context in case_contexts}) == 720
    assert all(os.path.exists(context["diff_inventory_path"]) for context in case_contexts)
    assert all(context.get("attribution_hash") for context in case_contexts)


@pytest.mark.parametrize("failing_arm", ("incumbent", "challenger"))
def test_arm_failure_finalizes_every_allocated_context_and_fails_closed(
        tmp_path, monkeypatch, failing_arm):
    """[BEHAVIORAL] Failed arms cannot synthesize a pair or bypass finalization."""
    api = _entrypoint()
    evals = _evals()
    manifest = _manifest()
    failed_prepared = []
    failed_finalized = []
    original_prepare = evals.prepare_isolated_attempt
    original_finalize = evals.finalize_isolated_attempt

    def track_failed_prepare(*args, **kwargs):
        context = original_prepare(*args, **kwargs)
        failed_prepared.append(context)
        return context

    def track_failed_finalize(*args, **kwargs):
        receipt = original_finalize(*args, **kwargs)
        failed_finalized.append((args[0], receipt))
        return receipt

    monkeypatch.setattr(evals, "prepare_isolated_attempt", track_failed_prepare)
    monkeypatch.setattr(evals, "finalize_isolated_attempt", track_failed_finalize)

    class ExpectedCaseFailure(RuntimeError):
        pass

    callback_calls = []

    def fail_one_arm(*, arm, **kwargs):
        callback_calls.append((arm, kwargs["isolation_context"]))
        if arm == failing_arm:
            raise ExpectedCaseFailure()
        return _arm_objective_result(arm=arm, **kwargs)

    with pytest.raises(ExpectedCaseFailure):
        _run(
            api, tmp_path / failing_arm, manifest, _corpus_seal(manifest, complete=True),
            case_executor=fail_one_arm,
        )

    failed_case_contexts = [
        context for context in failed_prepared
        if not context["attempt_id"].startswith("preflight-")
    ]
    failed_finalized_contexts = [
        context for context, _receipt in failed_finalized
        if not context["attempt_id"].startswith("preflight-")
    ]
    expected_arms = ["incumbent"] if failing_arm == "incumbent" else [
        "incumbent", "challenger"]
    assert [arm for arm, _context in callback_calls] == expected_arms
    assert len(failed_case_contexts) == len(expected_arms)
    assert failed_finalized_contexts == failed_case_contexts


def test_reused_isolation_context_blocks_before_any_case_callback(tmp_path, monkeypatch):
    """[BEHAVIORAL] A repeated writable context is terminal before execution starts."""
    api = _entrypoint()
    evals = _evals()
    manifest = _manifest()
    original_prepare = evals.prepare_isolated_attempt
    allocated = []
    callback_calls = []

    def reused_prepare(*args, **kwargs):
        if allocated:
            return allocated[0]
        context = original_prepare(*args, **kwargs)
        allocated.append(context)
        return context

    monkeypatch.setattr(evals, "prepare_isolated_attempt", reused_prepare)

    def case_executor(**kwargs):
        callback_calls.append(kwargs)
        return _arm_objective_result(**kwargs)

    with pytest.raises(_execution().ExperimentBlockedError):
        _run(
            api, tmp_path, manifest, _corpus_seal(manifest, complete=True),
            case_executor=case_executor,
        )
    assert callback_calls == []


@pytest.mark.parametrize("mutate", (
    lambda seal, hypothesis: seal.pop("sealed_held_out_case_ids"),
    lambda seal, hypothesis: seal["sealed_held_out_case_ids"].pop(
        hypothesis["hypothesis_id"]),
    lambda seal, hypothesis: seal["sealed_held_out_case_ids"].__setitem__(
        hypothesis["hypothesis_id"],
        list(seal["sealed_held_out_case_ids"]["H02"]),
    ),
    lambda seal, hypothesis: seal["sealed_held_out_case_ids"].__setitem__(
        hypothesis["hypothesis_id"],
        list(reversed(hypothesis["held_out_case_ids"])),
    ),
    lambda seal, hypothesis: seal["sealed_held_out_case_ids"].__setitem__(
        hypothesis["hypothesis_id"],
        list(hypothesis["held_out_case_ids"]) + ["extra-held-out-id"],
    ),
))
def test_corpus_seal_rejects_missing_swapped_extra_or_reordered_held_out_ids_before_callbacks(
        tmp_path, mutate):
    """[BEHAVIORAL] The seal binds the evaluation and held-out union before execution."""
    api = _entrypoint()
    manifest = _manifest()
    seal = _corpus_seal(manifest, complete=True)
    mutate(seal, manifest["hypotheses"][0])
    callback_calls = []

    def case_executor(**kwargs):
        callback_calls.append(kwargs)
        raise AssertionError("callback reached before held-out seal validation")

    with pytest.raises(_execution().ExperimentBlockedError):
        _run(api, tmp_path, manifest, seal, case_executor=case_executor)
    assert callback_calls == []
