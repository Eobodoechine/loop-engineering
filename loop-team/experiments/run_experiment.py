#!/usr/bin/env python3
"""Loop Team -- Experiment harness ("does it really help?").

Given a baseline and one or more variants, score each on the SAME instances and
accept a variant over the baseline only if the PACE acceptor says it is
significantly better (anytime-valid, false-accept <= alpha). This is the engine
the Researcher's experiment specs feed into: it turns "we should try X" into a
measured ACCEPT/REJECT, and it refuses to adopt a variant just because it scored
higher on the reused suite (that is the dev-set p-hacking the acceptor stops).

Scoring is pluggable. The built-in `harness_scorer` scores a verify.py
implementation by the suite's per-case correctness, so you can A/B two harness
versions today. A task-success scorer over a held coding set (Phase 2+) drops in
the same way: any callable returning a per-instance correctness vector works,
as long as baseline and variants are scored on the SAME ordered instances.

No third-party dependencies. Reuses evals/acceptor.py + evals/run_evals.py.

CLI:
    python run_experiment.py --baseline path/to/verify.py \\
        --variant improved=path/to/verify_v2.py --variant other=path/to/v3.py
"""
import argparse
import hashlib
import inspect
import json
import os
import sys
import uuid

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "evals"))
RUNNER_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "runner"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, RUNNER_DIR)
import acceptor  # noqa: E402
import experiment_execution  # noqa: E402
import model_routing  # noqa: E402
import model_routing_evals  # noqa: E402
import run_trace  # noqa: E402
import run_evals  # noqa: E402


def harness_scorer(harness_path):
    """Per-case correctness of a verify.py implementation on the eval suite.

    1 if the gate handled the case correctly (a trap caught, a good case passed),
    0 otherwise. Pending judge cases are excluded so the vector is deterministic
    and comparable across harnesses.
    """
    report = run_evals.run_suite(harness=harness_path)
    return [1 if r["bucket"] in ("caught", "ok") else 0
            for r in report["rows"] if r["bucket"] != "pending"]


def decide(baseline_correct, variant_corrects, alpha=0.05, lam=0.5, min_discordant=5):
    """Pure decision step: PACE each variant against the baseline (paired).

    baseline_correct: list[int] per-instance correctness of the incumbent.
    variant_corrects: dict name -> list[int] (same length / order as baseline).
    Returns {winner, results}. winner is the accepted variant with the highest
    betting wealth, or None (keep baseline) if none cleared the bar.
    """
    results = {}
    for name, vc in variant_corrects.items():
        pairs = acceptor.pairs_from_correctness(baseline_correct, vc)
        results[name] = acceptor.pace_accept(pairs, alpha=alpha, lam=lam,
                                             min_discordant=min_discordant)
    accepted = {n: r for n, r in results.items() if r.decision == "ACCEPT"}
    winner = max(accepted, key=lambda n: accepted[n].wealth) if accepted else None
    return {"winner": winner, "results": results}


def run_experiment(baseline, variants, scorer=harness_scorer,
                   alpha=0.05, lam=0.5, min_discordant=5):
    """Score baseline + variants with `scorer`, then decide. `baseline` and the
    values of `variants` are whatever the scorer accepts (e.g. harness paths)."""
    base = scorer(baseline)
    variant_corrects = {name: scorer(v) for name, v in variants.items()}
    out = decide(base, variant_corrects, alpha=alpha, lam=lam,
                 min_discordant=min_discordant)
    out["baseline_score"] = sum(base)
    out["n_instances"] = len(base)
    out["variant_scores"] = {n: sum(v) for n, v in variant_corrects.items()}
    return out


def _validate_experiment_corpus(manifest, corpus_seal):
    model_routing.validate_pace_manifest(manifest)
    if not isinstance(corpus_seal, dict) or corpus_seal.get(
            "schema") != "mission_control_corpus_seal.v1":
        raise experiment_execution.ExperimentBlockedError("sealed corpus is required")
    for field in ("manifest_hash", "corpus_seal_hash"):
        if not manifest.get(field) or corpus_seal.get(field) != manifest.get(field):
            raise experiment_execution.ExperimentBlockedError(
                "corpus seal does not match manifest %s" % field)
    sealed = corpus_seal.get("sealed_case_ids")
    if not isinstance(sealed, dict):
        raise experiment_execution.ExperimentBlockedError("sealed case map is required")
    hypothesis_ids = [item["hypothesis_id"] for item in manifest["hypotheses"]]
    if set(sealed) != set(hypothesis_ids):
        raise experiment_execution.ExperimentBlockedError(
            "sealed evaluation hypothesis keys do not match manifest")
    for hypothesis in manifest["hypotheses"]:
        if sealed.get(hypothesis["hypothesis_id"]) != hypothesis["evaluation_case_ids"]:
            raise experiment_execution.ExperimentBlockedError("sealed cases do not match manifest")
    sealed_held_out = corpus_seal.get("sealed_held_out_case_ids")
    if (not isinstance(sealed_held_out, dict) or
            list(sealed_held_out) != hypothesis_ids):
        raise experiment_execution.ExperimentBlockedError(
            "sealed held-out hypothesis keys do not match manifest")
    for hypothesis in manifest["hypotheses"]:
        if sealed_held_out.get(hypothesis["hypothesis_id"]) != hypothesis[
                "held_out_case_ids"]:
            raise experiment_execution.ExperimentBlockedError(
                "sealed held-out cases do not match manifest")


def _validate_case_execution_preflight(run_dir, corpus_seal):
    """Validate a real-corpus-shaped seal and prove isolated evidence paths work."""
    try:
        model_routing_evals.validate_mission_control_corpus_seal(corpus_seal)
    except (model_routing_evals.CorpusSealError, ValueError) as exc:
        raise experiment_execution.ExperimentBlockedError(str(exc)) from exc
    probe_status = model_routing_evals.classify_blocker(corpus_seal.get("probe"))
    if probe_status == "NOT_TESTED":
        raise experiment_execution.ExperimentBlockedError(
            "current isolated corpus probe is NOT_TESTED")

    isolation = corpus_seal.get("attempt_isolation")
    if not isinstance(isolation, dict) or isolation.get("shared_writable_state") is not False:
        raise experiment_execution.ExperimentBlockedError(
            "attempt isolation must prohibit shared writable state")
    for field in ("quarantine_dir", "diff_inventory_path"):
        value = isolation.get(field)
        if (not isinstance(value, str) or not value or os.path.isabs(value) or
                os.path.normpath(value).startswith("..")):
            raise experiment_execution.ExperimentBlockedError(
                "attempt isolation requires a safe %s" % field)

    preflight = model_routing_evals.prepare_isolated_attempt(
        run_dir, "preflight-" + uuid.uuid4().hex,
        "sealed-preflight-fixture-" + uuid.uuid4().hex,
    )
    receipt = model_routing_evals.finalize_isolated_attempt(
        preflight, observed_writes=[], attributed_writes=[])
    if receipt.get("state") != "QUARANTINED" or not os.path.exists(
            preflight["diff_inventory_path"]):
        raise experiment_execution.ExperimentBlockedError(
            "isolation quarantine/diff inventory preflight failed")
    return probe_status, receipt, preflight


def _emit(tracer, lifecycle, event_type, **fields):
    if lifecycle is not None:
        lifecycle(event_type)
    return tracer.event(event_type, **fields)


def _reservation_amounts(caps):
    requested = {}
    for field, value in caps.items():
        if field == "requests":
            requested[field] = 1
        elif field == "tokens":
            requested[field] = min(value, 500)
        elif field == "seconds":
            requested[field] = min(value, 30)
        elif field == "cost_usd":
            requested[field] = min(value, 1)
        else:
            requested[field] = 0
    return requested


def _attach_costs(usage, billing_observation, static_rate_observation):
    if static_rate_observation is not None:
        experiment_execution.attach_cost_observation(usage, static_rate_observation)
    if billing_observation is not None:
        experiment_execution.attach_cost_observation(usage, billing_observation)
    return usage


def _record_evaluation_chain(run_dir, tracer, usage, case_id):
    packet = {
        "schema": "blinded_judge_packet.v1",
        "packet_id": "packet-" + uuid.uuid4().hex,
        "case_id": case_id,
        "role_contract": "sha256:sealed-role-contract",
        "artifact": "sha256:sealed-artifact",
        "oracle_interface": "sha256:sealed-oracle",
        "evidence": {"source": "deterministic experiment oracle"},
    }
    provisional = model_routing_evals.persist_provisional_verdict(
        os.path.join(run_dir, "provisional-verdicts.jsonl"), packet, "PASS",
        ["sha256:deterministic-evidence"], "model-routing-oracle",
    )
    tracer.event("provisional_verdict", verdict="PASS",
                 note=provisional["hash"])
    post = model_routing_evals.build_post_verdict_evidence_packet(
        packet, provisional["hash"], {"usage": usage})
    tracer.event("evidence_release", verdict="PASS",
                 note=post["provisional_verdict_hash"])
    tracer.event("evaluation_result", outcome="PASS", verdict="PASS")


def _record_pace_rows(manifest, pace_ledger_path, tracer, execution_mode):
    ledger = model_routing.PaceLedger(pace_ledger_path, manifest)
    summaries = {}
    for hypothesis in manifest["hypotheses"]:
        hypothesis_id = hypothesis["hypothesis_id"]
        pair = ledger.record_pair(
            hypothesis_id, hypothesis["evaluation_case_ids"][0], 1, 1,
            hypothesis["fixture_hashes"], [],
        )
        tracer.event("pace_pair", outcome=pair.get("outcome", "tie"),
                     note=hypothesis_id)
        terminal = ledger.finalize(hypothesis_id, execution_mode=execution_mode)
        tracer.event("pace_finalized", outcome=terminal["status"],
                     note=hypothesis_id)
        summaries[hypothesis_id] = {
            "pace_row_persisted": pair["created"],
            "pace_finalized": True,
            "pace_status": terminal["status"],
            "pace_reason": terminal["reason"],
        }
    return summaries


def _objective_endpoint(result, arm):
    if not isinstance(result, dict):
        raise ValueError("case_executor must return a per-arm objective result object")
    if "incumbent_endpoint" in result or "challenger_endpoint" in result:
        raise ValueError("case_executor cannot return a synthesized endpoint pair")
    endpoint = result.get("endpoint")
    if endpoint not in (0, 1):
        raise ValueError("case_executor must return a binary per-arm endpoint")
    return endpoint


def _assemble_assignment_result(incumbent_result, challenger_result):
    result = {
        "incumbent_endpoint": _objective_endpoint(
            incumbent_result, "incumbent"),
        "challenger_endpoint": _objective_endpoint(
            challenger_result, "challenger"),
    }
    receipt_fields = ("signed_receipt", "verifier_key", "interpretation")
    has_receipt_evidence = any(
        field in arm_result
        for arm_result in (incumbent_result, challenger_result)
        for field in receipt_fields
    )
    if not has_receipt_evidence:
        return result
    if any(
            not all(field in arm_result for field in receipt_fields)
            for arm_result in (incumbent_result, challenger_result)):
        raise ValueError("per-arm receipt interpretation evidence is incomplete")
    if (incumbent_result["signed_receipt"] != challenger_result["signed_receipt"] or
            incumbent_result["verifier_key"] != challenger_result["verifier_key"]):
        raise ValueError("receipt interpretation arms must use the same signed receipt")
    result.update({
        "signed_receipt": incumbent_result["signed_receipt"],
        "verifier_key": incumbent_result["verifier_key"],
        "incumbent_interpretation": incumbent_result["interpretation"],
        "challenger_interpretation": challenger_result["interpretation"],
    })
    return result


def _objective_endpoints(result):
    if not isinstance(result, dict):
        raise ValueError("assembled assignment result is required")
    incumbent = result.get("incumbent_endpoint")
    challenger = result.get("challenger_endpoint")
    if incumbent not in (0, 1) or challenger not in (0, 1):
        raise ValueError("assembled assignment must contain binary endpoints")
    return incumbent, challenger


def _receipt_terminal(result):
    required = (
        "signed_receipt", "verifier_key", "incumbent_interpretation",
        "challenger_interpretation",
    )
    if not isinstance(result, dict) or not any(field in result for field in required):
        return None
    if not all(field in result for field in required):
        raise ValueError("receipt interpretation result is incomplete")
    signed_status = model_routing_evals.validate_signed_smoke_receipt(
        result["signed_receipt"], result["verifier_key"])
    evaluated = model_routing_evals.evaluate_receipt_interpretation(
        result["signed_receipt"], result["incumbent_interpretation"],
        result["challenger_interpretation"], signed_status=signed_status,
    )
    return evaluated if evaluated.get("status") == "KILL" else None


def _canonical_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _register_isolation_context(context, seen):
    fields = (
        "attempt_id", "attempt_root", "worktree", "fixture_namespace",
        "fixture_dir", "quarantine_dir", "diff_inventory_path",
        "attribution_hash",
    )
    if not isinstance(context, dict) or any(
            not isinstance(context.get(field), str) or not context[field]
            for field in fields):
        raise experiment_execution.ExperimentBlockedError(
            "isolated attempt descriptor is incomplete")
    for field in fields:
        value = context[field]
        values = seen.setdefault(field, set())
        if value in values:
            raise experiment_execution.ExperimentBlockedError(
                "reused isolated attempt %s is terminal" % field)
    for field in fields:
        seen[field].add(context[field])


def _call_case_executor(case_executor, arguments):
    """Pass isolation metadata when supported without breaking strict callbacks."""
    try:
        signature = inspect.signature(case_executor)
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        selected = dict((key, arguments[key]) for key in (
            "hypothesis_id", "case_id", "phase", "scalar_endpoint"))
    elif any(parameter.kind == inspect.Parameter.VAR_KEYWORD
             for parameter in signature.parameters.values()):
        selected = arguments
    else:
        selected = dict((key, value) for key, value in arguments.items()
                        if key in signature.parameters)
    return case_executor(**selected)


def _attempt_writes(result, arm, field):
    if not isinstance(result, dict):
        return []
    value = result.get(field)
    if isinstance(value, list):
        return value
    by_arm = result.get("attempt_writes")
    if isinstance(by_arm, dict) and isinstance(by_arm.get(arm), dict):
        value = by_arm[arm].get(field)
        return value if isinstance(value, list) else []
    return []


def _prepare_arm_attempt(run_dir, hypothesis_id, case_id, split, arm,
                         tracer, seen):
    attempt_id = "attempt-%s" % uuid.uuid4().hex
    fixture_namespace = "fixture-%s-%s" % (arm, uuid.uuid4().hex)
    context = model_routing_evals.prepare_isolated_attempt(
        run_dir, attempt_id, fixture_namespace)
    _register_isolation_context(context, seen)
    bindings = {
        "attempt_id": attempt_id,
        "hypothesis_id": hypothesis_id,
        "case_id": case_id,
        "split": split,
        "arm": arm,
        "isolation_attribution_hash": context["attribution_hash"],
    }
    tracer.event("attempt_isolation_prepared", outcome="PREPARED",
                 bindings=bindings)
    return context, bindings


def _finalize_arm_attempt(context, bindings, result, execution_mode, tracer,
                          attempts, usages):
    arm = bindings["arm"]
    finalization_error = None
    try:
        receipt = model_routing_evals.finalize_isolated_attempt(
            context,
            observed_writes=_attempt_writes(result, arm, "observed_writes"),
            attributed_writes=_attempt_writes(result, arm, "attributed_writes"),
        )
    except model_routing_evals.UnattributedWriteError as exc:
        receipt = getattr(exc, "receipt", None)
        finalization_error = exc
    if not isinstance(receipt, dict):
        raise experiment_execution.ExperimentBlockedError(
            "attempt finalization did not persist a receipt")

    final_bindings = dict(bindings)
    final_bindings.update({
        "finalization_state": receipt["state"],
        "finalization_receipt_hash": receipt["receipt_hash"],
    })
    usage = experiment_execution.empty_usage_v1(
        execution_mode, bindings["attempt_id"],
        "dispatch-%s" % uuid.uuid4().hex)
    experiment_execution.bind_attempt_assignment(
        usage,
        hypothesis_id=bindings["hypothesis_id"],
        case_id=bindings["case_id"],
        split=bindings["split"],
        arm=bindings["arm"],
        isolation_context=context,
        finalization_receipt=receipt,
    )
    tracer.event("attempt_isolation_finalized", outcome=receipt["state"],
                 bindings=final_bindings)
    tracer.event("experiment_attempt", outcome=receipt["state"],
                 bindings=final_bindings)
    tracer.usage_event(usage, outcome=receipt["state"], bindings=final_bindings)
    attempts.append({
        "attempt_id": bindings["attempt_id"],
        "dispatch_id": usage["dispatch_id"]["value"],
        "hypothesis_id": bindings["hypothesis_id"],
        "case_id": bindings["case_id"],
        "split": bindings["split"],
        "arm": bindings["arm"],
        "isolation_attribution_hash": context["attribution_hash"],
        "finalization_receipt_hash": receipt["receipt_hash"],
        "finalization_state": receipt["state"],
    })
    usages.append(usage)
    if finalization_error is not None:
        raise finalization_error


def _execute_arm(run_dir, hypothesis, case_id, split, arm, case_executor,
                 execution_mode, tracer, seen, attempts, usages):
    hypothesis_id = hypothesis["hypothesis_id"]
    context, bindings = _prepare_arm_attempt(
        run_dir, hypothesis_id, case_id, split, arm, tracer, seen)
    result = None
    callback_error = None
    try:
        try:
            result = _call_case_executor(case_executor, {
                "hypothesis_id": hypothesis_id,
                "case_id": case_id,
                "phase": split,
                "scalar_endpoint": hypothesis["scalar_endpoint"],
                "arm": arm,
                "attempt_id": context["attempt_id"],
                "attempt_context": context,
                "isolation_context": context,
            })
        except Exception as exc:
            callback_error = exc
    finally:
        try:
            _finalize_arm_attempt(
                context, bindings, result, execution_mode,
                tracer, attempts, usages)
        except Exception as exc:
            if callback_error is None:
                callback_error = exc
    if callback_error is not None:
        raise callback_error
    _objective_endpoint(result, arm)
    return result


def _execute_assignment(run_dir, hypothesis, case_id, split, case_executor,
                        execution_mode, tracer, seen, attempts, usages):
    incumbent_result = _execute_arm(
        run_dir, hypothesis, case_id, split, "incumbent", case_executor,
        execution_mode, tracer, seen, attempts, usages)
    challenger_result = _execute_arm(
        run_dir, hypothesis, case_id, split, "challenger", case_executor,
        execution_mode, tracer, seen, attempts, usages)
    return _assemble_assignment_result(incumbent_result, challenger_result)


def _default_offline_case_executor(**_kwargs):
    """Complete the dry-run matrix with explicit deterministic tie fixtures."""
    return {"endpoint": 1}


def _verify_attempt_completion(manifest, killed, attempts, usages, tracer):
    bindings = [(
        item["hypothesis_id"], item["case_id"], item["split"], item["arm"])
        for item in attempts
    ]
    attempt_ids = [item["attempt_id"] for item in attempts]
    receipt_hashes = [item["finalization_receipt_hash"] for item in attempts]
    if (len(attempts) != len(usages) or len(set(bindings)) != len(bindings) or
            len(set(attempt_ids)) != len(attempt_ids) or
            len(set(receipt_hashes)) != len(receipt_hashes)):
        raise experiment_execution.ExperimentBlockedError(
            "attempt usage/isolation/finalization bindings are incomplete or reused")
    expected = sum(
        2 * (len(item["evaluation_case_ids"]) + len(item["held_out_case_ids"]))
        for item in manifest["hypotheses"]
    )
    if not killed and len(usages) != expected:
        raise experiment_execution.ExperimentBlockedError(
            "complete experiment requires %d attempt receipts, found %d" % (
                expected, len(usages)))
    tracer.event("attempt_receipts_verified", outcome="COMPLETE", bindings={
        "expected_receipt_count": expected,
        "actual_receipt_count": len(usages),
        "terminal_kill_hypotheses": sorted(killed),
        "binding_inventory_hash": _canonical_hash(bindings),
    })


def _run_objective_cases(manifest, pace_ledger_path, tracer, execution_mode,
                         case_executor, run_dir, seen):
    """Run frozen evaluation cases, finalize, then run held-out confirmation."""
    ledger = model_routing.PaceLedger(pace_ledger_path, manifest)
    summaries = {}
    killed = set()
    attempts = []
    usages = []

    for hypothesis in manifest["hypotheses"]:
        hypothesis_id = hypothesis["hypothesis_id"]
        for case_id in hypothesis["evaluation_case_ids"]:
            result = _execute_assignment(
                run_dir, hypothesis, case_id, "evaluation", case_executor,
                execution_mode, tracer, seen, attempts, usages)
            if hypothesis_id in ("H09", "H10"):
                terminal = _receipt_terminal(result)
                if terminal is not None:
                    killed.add(hypothesis_id)
                    outcome = ledger.kill(hypothesis_id, terminal["reason"])
                    tracer.event("pace_finalized", outcome="KILL",
                                 note="%s:%s" % (hypothesis_id, terminal["reason"]))
                    summaries[hypothesis_id] = {
                        "pace_row_persisted": False,
                        "pace_finalized": True,
                        "pace_status": outcome["status"],
                        "pace_reason": outcome["reason"],
                        "router_recommendation": None,
                    }
                    break
            incumbent, challenger = _objective_endpoints(result)
            pair = ledger.record_pair(
                hypothesis_id, case_id, incumbent, challenger,
                hypothesis["fixture_hashes"], [],
            )
            tracer.event("pace_pair", outcome=pair["outcome"],
                         note="%s:%s" % (hypothesis_id, case_id))
        if hypothesis_id in killed:
            continue
        terminal = ledger.finalize(hypothesis_id, execution_mode=execution_mode)
        tracer.event("pace_finalized", outcome=terminal["status"],
                     note=hypothesis_id)
        summaries[hypothesis_id] = {
            "pace_row_persisted": ledger.row_count(hypothesis_id) == 24,
            "pace_finalized": True,
            "pace_status": terminal["status"],
            "pace_reason": terminal["reason"],
            "router_recommendation": None,
        }

    # Confirmation is deliberately a second stage and has no wealth columns.
    for hypothesis in manifest["hypotheses"]:
        hypothesis_id = hypothesis["hypothesis_id"]
        if hypothesis_id in killed:
            continue
        for case_id in hypothesis["held_out_case_ids"]:
            result = _execute_assignment(
                run_dir, hypothesis, case_id, "held_out", case_executor,
                execution_mode, tracer, seen, attempts, usages)
            if hypothesis_id in ("H09", "H10"):
                terminal = _receipt_terminal(result)
                if terminal is not None:
                    killed_outcome = ledger.kill(hypothesis_id, terminal["reason"])
                    summaries[hypothesis_id]["pace_status"] = killed_outcome["status"]
                    summaries[hypothesis_id]["pace_reason"] = killed_outcome["reason"]
                    summaries[hypothesis_id]["held_out_terminal_reason"] = terminal["reason"]
                    tracer.event("pace_finalized", outcome="KILL",
                                 note="%s:%s" % (hypothesis_id, terminal["reason"]))
                    break
            incumbent, challenger = _objective_endpoints(result)
            held_out = ledger.record_held_out_pair(
                hypothesis_id, case_id, incumbent, challenger,
                hypothesis["fixture_hashes"],
            )
            tracer.event("held_out_pair", outcome=held_out["outcome"],
                         note="%s:%s" % (hypothesis_id, case_id))
        summaries[hypothesis_id]["held_out_rows_persisted"] = ledger.held_out_row_count(
            hypothesis_id)
    _verify_attempt_completion(manifest, killed, attempts, usages, tracer)
    return summaries, attempts, usages


def run_model_routing_experiment(
        *, execution_mode, manifest, corpus_seal, run_dir, cap_ledger_path,
        pace_ledger_path, approval=None, provider_import=None,
        provider_factory=None, credential_reader=None, client_constructor=None,
        network_call=None, lifecycle_event_sink=None, max_retries=0,
        billing_observation=None, static_rate_observation=None,
        case_executor=None):
    """Run the bounded experiment path without granting integration authority."""
    os.makedirs(run_dir, exist_ok=True)
    _validate_experiment_corpus(manifest, corpus_seal)
    tracer = run_trace.Tracer(run_dir, rates={})
    blocker = None
    isolation_receipt = None
    preflight_context = None
    real_corpus_fields = (
        "project_id", "dashboard_item_id", "attempt_isolation", "probe",
    )
    requires_corpus_preflight = case_executor is not None or any(
        field in corpus_seal for field in real_corpus_fields)
    if requires_corpus_preflight:
        probe_status, isolation_receipt, preflight_context = (
            _validate_case_execution_preflight(run_dir, corpus_seal))
        blocker = {"status": probe_status}
        if probe_status == "BLOCKED_EXTERNAL":
            blocker["missing_dependency"] = corpus_seal["probe"]["missing_dependency"]
            tracer.event("corpus_blocked", outcome="BLOCKED_EXTERNAL",
                         note=blocker["missing_dependency"])
            with open(os.path.join(run_dir, "corpus-blocker.json"), "w",
                      encoding="utf-8") as blocker_file:
                json.dump(blocker, blocker_file, sort_keys=True)
            return {
                "manifest_hash": manifest["manifest_hash"],
                "corpus_seal_hash": manifest["corpus_seal_hash"],
                "hypotheses": {}, "attempts": [], "usage": None,
                "blocker": blocker,
                "integration": {"allowed": False, "performed": False},
            }
    attempts = []

    if execution_mode in experiment_execution.OFFLINE_MODES:
        seen = {}
        if preflight_context is not None:
            _register_isolation_context(preflight_context, seen)
        objective_executor = case_executor or _default_offline_case_executor
        hypotheses, attempts, usages = _run_objective_cases(
            manifest, pace_ledger_path, tracer, execution_mode,
            objective_executor, run_dir, seen)
        usage = usages[-1]
    else:
        if case_executor is not None:
            raise experiment_execution.ExperimentBlockedError(
                "provider assignment sweeps require the dedicated arm executor")
        attempt_id = "attempt-" + uuid.uuid4().hex
        dispatch_id = "dispatch-" + uuid.uuid4().hex
        experiment_execution.validate_experiment_authority(
            approval, manifest, corpus_seal, execution_mode)
        cap_ledger = model_routing.CapLedger(cap_ledger_path, caps=manifest["caps"])
        reservation_request = _reservation_amounts(manifest["caps"])
        initialized = False
        usage = None
        for retry_attempt in range(max_retries + 1):
            key = {
                "approval_hash": approval["approval_hash"],
                "manifest_hash": manifest["manifest_hash"],
                "hypothesis_id": "H01", "attempt_id": attempt_id,
                "dispatch_id": dispatch_id, "retry_attempt": retry_attempt,
                "idempotency_key": "%s-%d" % (attempt_id, retry_attempt),
            }
            reservation = cap_ledger.reserve(key, reservation_request)
            _emit(tracer, lifecycle_event_sink, "cap_reserved", note=reservation["reservation_id"])
            owner = reservation["owner"]
            cap_ledger.claim_network_attempt(reservation["reservation_id"], owner)
            _emit(tracer, lifecycle_event_sink, "cap_claimed", note=reservation["reservation_id"])
            attempt_summary = {
                "retry_attempt": retry_attempt,
                "reservation_id": reservation["reservation_id"],
                "retry_owner": owner, "reservation_claimed": True,
                "reconciled": False,
            }
            attempts.append(attempt_summary)
            if not initialized:
                for callback in (provider_import, provider_factory,
                                 credential_reader, client_constructor):
                    if callback is not None:
                        callback()
                initialized = True
            experiment_execution.validate_experiment_authority(
                approval, manifest, corpus_seal, execution_mode)
            _emit(tracer, lifecycle_event_sink, "network_attempt",
                  iteration=retry_attempt)
            try:
                raw_result = network_call()
            except Exception:
                cap_ledger.mark_crashed(reservation["reservation_id"])
                cap_ledger.cancel(
                    reservation["reservation_id"],
                    "retry-after-failure-%d" % retry_attempt,
                )
                if retry_attempt >= max_retries:
                    raise
                continue
            if not isinstance(raw_result, experiment_execution.ProviderAdapterResult):
                raise TypeError("provider experiment requires ProviderAdapterResult")
            policy = manifest["hypotheses"][0]["challenger_policy_class"]
            resolved = manifest["resolved_model_ids"][policy]
            usage = experiment_execution.normalize_provider_result(
                raw_result, attempt_id, dispatch_id, execution_mode,
                policy_class=policy, requested_model=policy,
                resolved_model_id=resolved, requested_effort="high",
                actual_effort="high",
            )
            _attach_costs(usage, billing_observation, static_rate_observation)
            actual = dict(reservation_request)
            total = usage["token_fields"]["total_tokens_reported"]["value"]
            if total is not None and "tokens" in actual:
                actual["tokens"] = min(total, actual["tokens"])
            cap_ledger.reconcile(
                reservation["reservation_id"], raw_result.raw_observation_id,
                actual=actual,
            )
            attempt_summary["reconciled"] = True
            break
        if usage is None:
            raise RuntimeError("experiment produced no usage record")
        tracer.event("experiment_attempt", outcome="PROVIDER_SYNTHETIC")
        tracer.usage_event(usage)
        hypotheses = _record_pace_rows(
            manifest, pace_ledger_path, tracer, execution_mode)

    _record_evaluation_chain(
        run_dir, tracer, usage,
        manifest["hypotheses"][0]["evaluation_case_ids"][0],
    )
    if lifecycle_event_sink is not None:
        lifecycle_event_sink("provisional_verdict_persisted")
        lifecycle_event_sink("post_verdict_evidence_released")
    result = {
        "manifest_hash": manifest["manifest_hash"],
        "corpus_seal_hash": manifest["corpus_seal_hash"],
        "hypotheses": hypotheses,
        "attempts": attempts,
        "usage": usage,
        "integration": {"allowed": False, "performed": False},
    }
    if blocker is not None:
        result["blocker"] = blocker
        result["isolation_receipt"] = isolation_receipt
    return result


def print_report(out):
    print("Experiment -- PACE-gated A/B  (n_instances=%d)" % out["n_instances"])
    print("  baseline correct: %d" % out["baseline_score"])
    for name, r in out["results"].items():
        print("  variant %-16s correct=%d  %s  (wealth=%.2f, discordant=%d) -- %s"
              % (name, out["variant_scores"][name], r.decision, r.wealth,
                 r.discordant, r.reason))
    print("  WINNER: %s" % (out["winner"] or "baseline (no variant cleared the bar)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="baseline verify.py path")
    ap.add_argument("--variant", action="append", default=[], metavar="name=PATH",
                    help="a variant verify.py as name=path (repeatable)")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--min-discordant", type=int, default=5)
    args = ap.parse_args()
    variants = {}
    for spec in args.variant:
        if "=" not in spec:
            ap.error("--variant must be name=PATH, got %r" % spec)
        name, path = spec.split("=", 1)
        variants[name] = path
    out = run_experiment(args.baseline, variants, alpha=args.alpha, lam=args.lam,
                         min_discordant=args.min_discordant)
    print_report(out)
    sys.exit(0)


if __name__ == "__main__":
    main()
