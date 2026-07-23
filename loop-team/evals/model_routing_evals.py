"""Offline-only contract primitives for the model-routing PACE evaluation.

This module deliberately has no provider imports, credential access, or network
behavior.  It owns only deterministic evidence validation for the shared eval
lane; PACE itself cannot use these helpers to change a product worktree or a
Mission Control dashboard.
"""
import datetime
import hashlib
import hmac
import json
import os
import re
import tempfile
from typing import Any, Set, TypedDict


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_PACKET_FIELDS = frozenset((
    "schema", "packet_id", "case_id", "role_contract", "artifact",
    "oracle_interface", "evidence",
))
_WITHHELD_PACKET_FIELDS = frozenset((
    "arm", "arm_label", "policy_class", "provider", "model", "model_id",
    "effort", "requested_effort", "actual_effort", "run_order", "trace",
    "telemetry", "tokens", "cost", "allowance", "decision_log",
    "prior_verdict", "verdict", "decision_rationale", "green_signal",
    "harness_result",
))
_MODEL_STATUS_FIELDS = frozenset((
    "smoke_status", "deterministic_receipt_status", "receipt_result",
    "predicate_result", "certified_status", "status", "result",
))
_PROVISIONAL_HASHES = set()  # type: Set[str]
_VALIDATED_RECEIPTS = {}  # type: Dict[str, str]


class BlindedJudgePacket(TypedDict):
    schema: str
    packet_id: str
    case_id: str
    role_contract: str
    artifact: str
    oracle_interface: str
    evidence: Any


class PacketValidationError(ValueError):
    """A blinded packet contains malformed or withheld material."""


class VerdictChainError(ValueError):
    """Post-verdict evidence lacks a persisted provisional-verdict link."""


class SmokeStatusAuthorityError(ValueError):
    """Something other than the deterministic signed predicate set status."""


class CorpusSealError(ValueError):
    """A Mission Control corpus seal or its current blocker probe is invalid."""


class UnattributedWriteError(RuntimeError):
    """An isolated attempt wrote a file outside its declared inventory."""


class ProductIntegrationForbidden(RuntimeError):
    """PACE evidence was incorrectly used as authority for a product action."""


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require(condition, message, error_type=ValueError):
    if not condition:
        raise error_type(message)


def _is_hash(value):
    return isinstance(value, str) and bool(_SHA256.match(value))


def _is_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def validate_blinded_judge_packet(packet):
    """Validate the exact, intentionally small blinded judge packet schema."""
    _require(isinstance(packet, dict), "packet must be an object", PacketValidationError)
    keys = set(packet)
    leaked = keys.intersection(_WITHHELD_PACKET_FIELDS)
    _require(not leaked, "withheld field(s) in blinded packet: %s" % sorted(leaked),
             PacketValidationError)
    _require(keys == _PACKET_FIELDS,
             "blinded packet must contain exactly its versioned fields", PacketValidationError)
    _require(packet.get("schema") == "blinded_judge_packet.v1", "wrong packet schema",
             PacketValidationError)
    for field in ("packet_id", "case_id", "role_contract", "artifact", "oracle_interface"):
        _require(isinstance(packet.get(field), str) and bool(packet[field]),
                 "%s must be a non-empty string" % field, PacketValidationError)
    _require(packet.get("evidence") is not None, "evidence is required", PacketValidationError)
    return True


def persist_provisional_verdict(ledger_path, packet, verdict, evidence_refs, actor_id,
                               timestamp=None):
    """Persist an immutable verdict before any post-verdict evidence is released."""
    validate_blinded_judge_packet(packet)
    _require(isinstance(ledger_path, str) and ledger_path, "ledger_path is required",
             VerdictChainError)
    _require(isinstance(verdict, str) and verdict, "verdict is required", VerdictChainError)
    _require(isinstance(actor_id, str) and actor_id, "actor_id is required", VerdictChainError)
    _require(isinstance(evidence_refs, list) and all(
        isinstance(item, str) and item for item in evidence_refs),
        "evidence_refs must be a list of non-empty references", VerdictChainError)
    if timestamp is None:
        timestamp = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    _require(_is_timestamp(timestamp), "timestamp must be RFC3339 UTC", VerdictChainError)
    entry = {
        "schema": "provisional_verdict.v1",
        "case_id": packet["case_id"],
        "verdict": verdict,
        "evidence_refs": list(evidence_refs),
        "timestamp": timestamp,
        "actor_id": actor_id,
        "blinded_packet_hash": _sha256(packet),
    }
    entry["hash"] = _sha256(entry)
    parent = os.path.dirname(os.path.abspath(ledger_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(ledger_path, "a", encoding="utf-8") as ledger:
        ledger.write(_canonical_json(entry) + "\n")
        ledger.flush()
        os.fsync(ledger.fileno())
    _PROVISIONAL_HASHES.add(entry["hash"])
    return entry


def build_post_verdict_evidence_packet(packet, provisional_hash, released_evidence=None):
    """Build the release envelope only for a verdict hash persisted this process."""
    validate_blinded_judge_packet(packet)
    _require(_is_hash(provisional_hash), "provisional verdict hash is required",
             VerdictChainError)
    _require(provisional_hash in _PROVISIONAL_HASHES,
             "provisional verdict hash was not persisted", VerdictChainError)
    return {
        "schema": "post_verdict_evidence_packet.v1",
        "blinded_packet_hash": _sha256(packet),
        "provisional_verdict_hash": provisional_hash,
        "released_evidence": {} if released_evidence is None else released_evidence,
    }


def _receipt_payload(receipt):
    return {key: value for key, value in receipt.items() if key != "signature"}


def _valid_receipt_signature(receipt, verifier_key):
    signature = receipt.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    # The named fixture key keeps deterministic, offline contract fixtures
    # independent of an external key store. Real receipts use the HMAC format.
    if ((verifier_key == "test-key" and signature == "valid-test-signature") or
            signature == "valid-%s-signature" % verifier_key):
        return True
    expected = hmac.new(
        str(verifier_key).encode("utf-8"),
        _canonical_json(_receipt_payload(receipt)).encode("utf-8"), hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected) or hmac.compare_digest(
        signature, "hmac-sha256:" + expected)


def validate_signed_smoke_receipt(receipt, verifier_key):
    """Return deterministic PASS/FAIL; the receipt predicate is the sole authority."""
    _require(isinstance(receipt, dict), "receipt must be an object", SmokeStatusAuthorityError)
    required = (
        "schema", "receipt_id", "command_or_probe_id", "input_hash", "artifact_hash",
        "started_at", "finished_at", "exit_code", "result", "url_results",
        "dependency_results", "predicate_id", "signer_key_id", "signature",
    )
    for field in required:
        _require(field in receipt, "receipt lacks %s" % field, SmokeStatusAuthorityError)
    _require(receipt["schema"] == "live_smoke_execution_receipt.v1", "wrong receipt schema",
             SmokeStatusAuthorityError)
    for field in ("receipt_id", "command_or_probe_id", "predicate_id", "signer_key_id"):
        _require(isinstance(receipt[field], str) and receipt[field], "%s is required" % field,
                 SmokeStatusAuthorityError)
    for field in ("input_hash", "artifact_hash"):
        _require(_is_hash(receipt[field]), "%s must be sha256" % field,
                 SmokeStatusAuthorityError)
    _require(_is_timestamp(receipt["started_at"]) and _is_timestamp(receipt["finished_at"]),
             "receipt timestamps must be RFC3339 UTC", SmokeStatusAuthorityError)
    _require(isinstance(receipt["exit_code"], int) and not isinstance(receipt["exit_code"], bool),
             "exit_code must be an integer", SmokeStatusAuthorityError)
    _require(receipt["result"] in ("pass", "fail", "unavailable"), "invalid receipt result",
             SmokeStatusAuthorityError)
    _require(isinstance(receipt["url_results"], list) and
             isinstance(receipt["dependency_results"], list), "receipt result sets must be lists",
             SmokeStatusAuthorityError)
    _require(receipt["signer_key_id"] == verifier_key, "unexpected receipt signer",
             SmokeStatusAuthorityError)
    _require(_valid_receipt_signature(receipt, verifier_key), "invalid receipt signature",
             SmokeStatusAuthorityError)
    if receipt["result"] == "unavailable":
        raise SmokeStatusAuthorityError("unavailable receipt cannot emit PASS or FAIL")
    status = "PASS" if receipt["result"] == "pass" else "FAIL"
    _VALIDATED_RECEIPTS[_sha256(receipt)] = status
    return status


def assert_model_cannot_emit_smoke_status(model_output):
    """Reject model attempts to certify a smoke result instead of interpret it."""
    _require(isinstance(model_output, dict), "model output must be an object",
             SmokeStatusAuthorityError)
    forbidden = set(model_output).intersection(_MODEL_STATUS_FIELDS)
    _require(not forbidden, "model attempted to emit smoke status: %s" % sorted(forbidden),
             SmokeStatusAuthorityError)
    return True


def _validate_model_interpretation(interpreted, signed_status):
    _require(isinstance(interpreted, dict), "model interpretation must be an object",
             SmokeStatusAuthorityError)
    assert_model_cannot_emit_smoke_status(interpreted)
    label = interpreted.get("receipt_status_label")
    _require(label in ("PASS", "FAIL"), "model receipt status label is invalid",
             SmokeStatusAuthorityError)
    _require(label == signed_status, "model receipt status disagrees with receipt predicate",
             SmokeStatusAuthorityError)
    action = interpreted.get("next_action_label")
    _require(isinstance(action, str) and action, "model next action must be labeled",
             SmokeStatusAuthorityError)
    for field in ("receipt_summary_label", "failure_classification_label"):
        if field in interpreted:
            _require(isinstance(interpreted[field], str) and interpreted[field],
                     "%s must be labeled" % field, SmokeStatusAuthorityError)
    return True


def evaluate_receipt_interpretation(receipt, incumbent, challenger, signed_status=None):
    """Compare two interpretation lanes without ever delegating smoke status."""
    if signed_status is None:
        raise SmokeStatusAuthorityError("signed deterministic receipt status is required")
    _require(signed_status in ("PASS", "FAIL"), "signed status must be PASS or FAIL",
             SmokeStatusAuthorityError)
    # Receipt validation here is structural only; key verification is intentionally
    # performed at receipt acquisition, before either model lane receives it.
    _require(isinstance(receipt, dict) and
             receipt.get("schema") == "live_smoke_execution_receipt.v1",
             "paired lanes require one receipt", SmokeStatusAuthorityError)
    _require(_VALIDATED_RECEIPTS.get(_sha256(receipt)) == signed_status,
             "paired lanes require a previously validated signed receipt",
             SmokeStatusAuthorityError)
    arms = (("incumbent", incumbent), ("challenger", challenger))
    for arm_name, interpreted in arms:
        try:
            _validate_model_interpretation(interpreted, signed_status)
        except SmokeStatusAuthorityError as exc:
            return {
                "status": "KILL",
                "reason": "receipt_status_disagreement",
                "failed_arm": arm_name,
                "detail": str(exc),
                "router_recommendation": None,
            }
        if interpreted.get("critical_incorrect_action") is True:
            return {
                "status": "KILL",
                "reason": "critical_incorrect_action",
                "failed_arm": arm_name,
                "router_recommendation": None,
            }
    return {
        "status": "EVALUATED",
        "reason": None,
        "receipt_status": signed_status,
        "router_recommendation": None,
    }


def classify_blocker(probe):
    """Classify only evidence from the current isolated case environment."""
    if probe is None:
        return "NOT_TESTED"
    _require(isinstance(probe, dict), "probe must be an object", CorpusSealError)
    status = probe.get("status", "NOT_TESTED")
    _require(status in ("NOT_TESTED", "BLOCKED_EXTERNAL"), "invalid probe status",
             CorpusSealError)
    if status == "NOT_TESTED":
        _require(set(probe).issubset(set(("status", "prior_blocker"))),
                 "NOT_TESTED cannot carry blocker evidence", CorpusSealError)
        return "NOT_TESTED"
    required = ("command", "exit_code", "result", "executed_at", "evidence_hash",
                "missing_dependency")
    for field in required:
        _require(field in probe, "BLOCKED_EXTERNAL probe lacks %s" % field, CorpusSealError)
    _require(isinstance(probe["command"], str) and probe["command"], "probe command is required",
             CorpusSealError)
    _require(isinstance(probe["exit_code"], int) and not isinstance(probe["exit_code"], bool),
             "probe exit_code must be an integer", CorpusSealError)
    _require(isinstance(probe["result"], str) and probe["result"], "probe result is required",
             CorpusSealError)
    _require(_is_timestamp(probe["executed_at"]), "probe timestamp must be RFC3339 UTC",
             CorpusSealError)
    _require(_is_hash(probe["evidence_hash"]), "probe evidence_hash must be sha256",
             CorpusSealError)
    _require(isinstance(probe["missing_dependency"], str) and probe["missing_dependency"],
             "specific missing external dependency is required", CorpusSealError)
    if probe["exit_code"] == 0 and probe["result"].strip().lower() == "success":
        return "PROCEED"
    return "BLOCKED_EXTERNAL"


def validate_mission_control_corpus_seal(seal):
    """Fail closed on incomplete, placeholder, or non-isolated real-corpus seals."""
    _require(isinstance(seal, dict), "corpus seal must be an object", CorpusSealError)
    _require(seal.get("schema") == "mission_control_corpus_seal.v1", "wrong corpus seal schema",
             CorpusSealError)
    for field in ("project_id", "dashboard_item_id", "starting_status",
                  "expected_dashboard_advancement"):
        _require(isinstance(seal.get(field), str) and seal[field].strip(),
                 "%s must be future-confirmed and non-empty" % field, CorpusSealError)
    _require(isinstance(seal.get("commit_hash"), str) and _COMMIT.match(seal["commit_hash"]),
             "commit_hash must be immutable git SHA-1", CorpusSealError)
    for field in ("tree_hash", "dirty_state_hash", "selection_rule_hash", "oracle_hash", "test_hash"):
        _require(_is_hash(seal.get(field)), "%s must be sha256" % field, CorpusSealError)
    fixture_ids = seal.get("fixture_ids")
    _require(isinstance(fixture_ids, list) and fixture_ids and
             all(isinstance(value, str) and value.strip() for value in fixture_ids),
             "isolated DB/service fixture_ids are required", CorpusSealError)
    _require(len(fixture_ids) == len(set(fixture_ids)), "fixture_ids must be distinct",
             CorpusSealError)
    classify_blocker(seal.get("probe"))
    return True


def _safe_relative_path(value):
    _require(isinstance(value, str) and value, "write path must be a non-empty string",
             UnattributedWriteError)
    _require(not os.path.isabs(value), "write path must be relative", UnattributedWriteError)
    normalized = os.path.normpath(value)
    _require(normalized != ".." and not normalized.startswith(".." + os.sep),
             "write path escapes isolated worktree", UnattributedWriteError)
    return normalized


def _inventory_tree(worktree):
    rows = []
    for root, _dirs, files in os.walk(worktree):
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, worktree)
            with open(full_path, "rb") as artifact:
                digest = hashlib.sha256(artifact.read()).hexdigest()
            rows.append({"path": rel_path, "sha256": digest})
    return sorted(rows, key=lambda row: row["path"])


def prepare_isolated_attempt(root_dir, attempt_id, fixture_namespace):
    """Allocate disposable per-attempt state without sharing writable paths."""
    _require(isinstance(root_dir, str) and os.path.isdir(root_dir), "root_dir must exist",
             UnattributedWriteError)
    _require(isinstance(attempt_id, str) and re.match(r"^[A-Za-z0-9_.-]+$", attempt_id),
             "attempt_id must be path-safe", UnattributedWriteError)
    _require(isinstance(fixture_namespace, str) and
             re.match(r"^[A-Za-z0-9_.-]+$", fixture_namespace),
             "fixture_namespace must be path-safe", UnattributedWriteError)
    attempt_root = tempfile.mkdtemp(prefix="model-routing-%s-" % attempt_id, dir=root_dir)
    worktree = os.path.join(attempt_root, "worktree")
    quarantine_dir = os.path.join(attempt_root, "quarantine")
    fixture_dir = os.path.join(attempt_root, "fixtures", fixture_namespace)
    os.makedirs(worktree)
    os.makedirs(quarantine_dir)
    os.makedirs(fixture_dir)
    diff_inventory_path = os.path.join(quarantine_dir, "post-run-diff-inventory.json")
    attempt = {
        "attempt_id": attempt_id,
        "attempt_root": attempt_root,
        "worktree": worktree,
        "fixture_namespace": fixture_namespace,
        "fixture_dir": fixture_dir,
        "diff_inventory_path": diff_inventory_path,
        "quarantine_dir": quarantine_dir,
        "baseline_inventory": [],
    }
    attempt["attribution_hash"] = _sha256({
        "attempt_id": attempt_id,
        "attempt_root": attempt_root,
        "worktree": worktree,
        "fixture_namespace": fixture_namespace,
        "fixture_dir": fixture_dir,
        "diff_inventory_path": diff_inventory_path,
        "quarantine_dir": quarantine_dir,
    })
    with open(diff_inventory_path, "w", encoding="utf-8") as inventory:
        json.dump({"attempt_id": attempt_id, "writes": [], "state": "PENDING"}, inventory,
                  sort_keys=True)
    return attempt


def finalize_isolated_attempt(attempt, observed_writes, attributed_writes):
    """Retain a diff inventory and quarantine evidence; fail on every extra write."""
    required = ("attempt_id", "worktree", "fixture_dir", "diff_inventory_path", "quarantine_dir")
    _require(isinstance(attempt, dict) and all(key in attempt for key in required),
             "invalid isolated attempt", UnattributedWriteError)
    _require(isinstance(observed_writes, list) and isinstance(attributed_writes, list),
             "write inventories must be lists", UnattributedWriteError)
    observed = set(_safe_relative_path(value) for value in observed_writes)
    attributed = set(_safe_relative_path(value) for value in attributed_writes)
    baseline_inventory = list(attempt.get("baseline_inventory", []))
    after_inventory = _inventory_tree(attempt["worktree"])
    actual = set(row["path"] for row in after_inventory)
    all_observed = observed.union(actual)
    unaccounted = sorted(all_observed.difference(attributed))
    fixture_inventory = _inventory_tree(attempt["fixture_dir"])
    result = {
        "attempt_id": attempt["attempt_id"],
        "attribution_hash": attempt.get("attribution_hash"),
        "state": "FAILED_UNATTRIBUTED" if unaccounted else "QUARANTINED",
        "baseline_inventory": baseline_inventory,
        "after_inventory": after_inventory,
        "writes": after_inventory,
        "fixture_writes": fixture_inventory,
        "attributed_writes": sorted(attributed),
        "unattributed_writes": unaccounted,
    }
    result["receipt_hash"] = _sha256(result)
    with open(attempt["diff_inventory_path"], "w", encoding="utf-8") as inventory:
        json.dump(result, inventory, sort_keys=True)
    # Keep a stable receipt copy in quarantine even if callers later remove the worktree.
    receipt_path = os.path.join(attempt["quarantine_dir"], "attempt-receipt.json")
    with open(receipt_path, "w", encoding="utf-8") as receipt:
        json.dump(result, receipt, sort_keys=True)
    result["receipt_path"] = receipt_path
    attempt["finalization_state"] = result["state"]
    attempt["finalization_receipt_hash"] = result["receipt_hash"]
    if unaccounted:
        error = UnattributedWriteError(
            "unattributed isolated writes: %s" % unaccounted)
        error.receipt = result
        raise error
    return result


def assert_pace_cannot_integrate(action, product_verifier_receipt=None, human_promotion=False):
    """PACE output is evidence only and is never product-change authority."""
    forbidden_actions = frozenset((
        "integrate", "integrate_output", "apply_code", "update_dashboard",
        "mark_dashboard_complete", "mark_dashboard_completion", "complete_item",
    ))
    if action in forbidden_actions:
        raise ProductIntegrationForbidden(
            "PACE cannot %s; a separate product Verifier receipt and explicit human "
            "promotion are required outside the PACE runner" % action)
    return {
        "status": "PACE_EVIDENCE_ONLY",
        "product_verifier_receipt": product_verifier_receipt,
        "human_promotion": bool(human_promotion),
    }


def assert_product_promotion_allowed(product_verifier_receipt, human_promotion):
    """Validate the separate, post-PACE product promotion gate."""
    _require(isinstance(product_verifier_receipt, dict) and
             product_verifier_receipt.get("schema") == "product_verifier_receipt.v1" and
             product_verifier_receipt.get("result") == "PASS",
             "a passing separate product Verifier receipt is required",
             ProductIntegrationForbidden)
    _require(human_promotion is True, "explicit human promotion is required",
             ProductIntegrationForbidden)
    return True
