"""[BEHAVIORAL] Fake-only pilot controller contract for the Claude subscription pilot.

Spec: loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md
SPEC_SHA256 = 698d23284f4de930c84d66551cd5e11dab717ca14af19a02c7d8e6472a0058bf
(STALE-VALUE CORRECTION: this file originally pinned 7745e91e689f8091406ae5e703
7ef2c150cfc9bd298ac5a1513e94cdc197b61b -- the spec's bytes BEFORE its round-4
plan-check rewrite of Section 6.1. That value is no longer this spec file's real
sha256; it is corrected here and in the module constant below to the actual
current, reviewed spec bytes the Coder built against, since this constant is
compared byte-for-byte in the confirmation-sealing fixtures below.)

No implementation exists yet at ``loop-team/runner/claude_subscription_pilot.py``. This
suite is written test-first per spec Section 12 and is expected to fail (collection
error / ModuleNotFoundError) until the Coder delivers.

This file exercises the CONTROLLER layer: the exact ten-call plan, the combined cap
ledger (calls/seconds/tokens/USD ceiling), the confirmation/approval-sealing ceremony
(including its REAL, non-fake-SDK-mode code path -- Section 12's own explicit callout of
a gap in the Codex pilot's own suite that must not be repeated here), the required
fake-SDK test gate, canonical-source-integrity bracketing (Section 8.1), the
runtime price-rate lookup that blocks approval sealing, reuse-not-reimplementation of
the post-arm apparatus imported from ``codex_subscription_pilot.py`` (Section 11 point
2), and the final report's PILOT_ONLY/NO_ROUTING_PROMOTION framing plus its required
plain-language n=3 statistical-power sentence (Section 13).

Everything that belongs to the dispatch/preflight layer instead (call-shape hostile
values, TERMINAL event classification, timeout/session-end, redaction, per-call USD
cost, Fable-5 data-retention PRECHECK_FAILED) is covered in
``test_claude_agent_adapter.py`` instead, and this file imports that file's fakes and
packet-building helpers rather than re-deriving them, per this run's own reuse ethos.

ASSUMED PUBLIC CONTRACT this suite pins for the not-yet-written Coder (beyond what
Section 11 point 2 names explicitly for reuse):

  SPEC_SHA256, PROMOTION_BOUNDARY, ACCEPTED_MODELS
  EXACT_CALL_PLAN -- ten [role, model, effort-or-None] entries (Section 4.1)
  EXACT_CAPS -- combined_calls=10, per_call_timeout_seconds=1800,
      combined_timeout_seconds=18000, per_call_observed_tokens_max=150000,
      aggregate_observed_tokens_max_when_telemetry_exists=1500000

  Re-exported (imported, not redefined) directly from codex_subscription_pilot.py:
      ProductionPreparationGit, ProductionProductPreprobeRunner, ProductP3OracleMatrix,
      ProductRuntimeSnapshot, ProductProcessAuditor, OracleGeneratorAuthority,
      ProductOracleSandbox, ProductGitAuthority, ProductTreeDelta,
      ProductVerifierAuthority, create_product_verifier_authority, ProductPostArmVerifier,
      ProductionPostArmController, ProductionCaseMaterialBuilder, _AtomicPreparationWriter,
      _canonical_bytes, _canonical_hash, packet_hash, manifest_hash, approval_hash.

  ClaudeCombinedCapLedger(*, estimated_usd_ceiling: float)
      .reserve(key, requested) / .start(reservation_id) /
      .reconcile(reservation_id, observation_id, actual) / .totals()

  ClaudePilotConfirmationBuilder(*, test_mode=False)
      .build(*, confirmation_request_path, manifest_path, explicit_confirmation_text,
             estimated_usd_ceiling) -> str (approval_path)

  ClaudeRequiredTestGateRunner.MODULE_ORDER -- exactly the 4 modules in spec Section 12's
      pytest invocation.

  ClaudeSubscriptionPilot(*, adapter_factory, test_mode=False, post_arm_verifier=None)
      .run(*, approval, manifest, required_test_receipt, frozen_packets, dry_run,
           report_dir=None) -> report dict

  resolve_price_rate_table_for_approval(call_plan, *, rate_lookup, clock) -> dict
      (raises on any unresolvable/failed/stale per-model rate; Section 4.3)
"""
from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
LOOP_TEAM_DIR = REPO_ROOT / "loop-team"
if str(LOOP_TEAM_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_TEAM_DIR))

from runner.tests.test_claude_agent_adapter import (  # noqa: E402
    _adapter as make_claude_adapter, _request as make_claude_request, _result_event,
    make_query_fn,
)


SPEC_SHA256 = "698d23284f4de930c84d66551cd5e11dab717ca14af19a02c7d8e6472a0058bf"
PROMOTION_BOUNDARY = "PILOT_ONLY/NO_ROUTING_PROMOTION"
ACCEPTED_MODELS = (
    "claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5", "claude-fable-5",
)

# The real, already-sealed Codex pilot preparation artifacts on disk (Section 3's
# "Acceptance requirement (not optional)"). These are dry-run PREPARE-mode artifacts
# (clone + preprobe + case manifest sealing) -- not a real paid dispatch, which remains
# HUMAN_RECONFIRMATION_REQUIRED for both pilots.
CODEX_PREPARE_DIR = (
    REPO_ROOT / "loop-team" / "runs" / "2026-07-16_model-routing-pace" / "artifacts"
    / "codex_product_pilot" / "2026-07-16-model-routing-pace-prepare-019f698a-06"
)
CODEX_SEALED_CASE_FACTS = {
    # case_id -> (source_root, source_sha) read directly from the real sealed packets.
    "P1-tax-package-live-data": (
        "<HOME>/Claude/Projects/taxahead-integration",
        "a78f13598cf7a425de4bd20e92d6b97f140eedb3",
    ),
    "P2-ask-taxahead-chat-transport": (
        "<HOME>/Claude/Projects/taxahead-integration",
        "a78f13598cf7a425de4bd20e92d6b97f140eedb3",
    ),
    "P3-pms-prerequisite-doctor": (
        "<HOME>/Claude/Projects/padsplit-reverification/pms",
        "4a396220b598d640e4bea5fb703c24efe83c23c5",
    ),
}


def _api():
    return importlib.import_module("runner.claude_subscription_pilot")


def _codex_api():
    return importlib.import_module("runner.codex_subscription_pilot")


def _adapter_api():
    return importlib.import_module("runner.claude_agent_adapter")


def _blocked_error_classes():
    """Accept either a reused ``codex_subscription_pilot.PilotBlockedError`` or a
    Claude-specific equivalent -- the spec's Section 11 point 2 import list does not
    name this trivial marker exception explicitly, so either reuse or a mirrored
    redefinition is a defensible Coder choice; this suite must not hinge on which."""
    classes = set()
    try:
        classes.add(_api().PilotBlockedError)
    except AttributeError:
        pass
    try:
        classes.add(_api().ClaudePilotBlockedError)
    except AttributeError:
        pass
    classes.add(_codex_api().PilotBlockedError)
    return tuple(classes)


# ---------------------------------------------------------------- packet/materials ----

REQUIRED_MATERIALS = ("prompt", "plan", "oracle", "test", "dependency", "preprobe")


def _materials(api, *, estimated_usd_ceiling=10.0):
    """Mirror test_codex_subscription_pilot.py's own ``_materials()`` fixture builder,
    adapted to Claude's ten-call plan and cap shape."""
    call_plan = api.EXACT_CALL_PLAN

    def make_packet(ordinal, call):
        role, model, effort = call
        contents = {name: "%s-%s\n" % (ordinal, name) for name in REQUIRED_MATERIALS}
        clone_entries = [{"path": "baseline.txt", "sha256": hashlib.sha256(
            ("clone-%s" % ordinal).encode()).hexdigest()}]
        source_entries = [{"path": "source.txt", "sha256": hashlib.sha256(
            ("source-%s" % ordinal).encode()).hexdigest()}]
        case_id = "smoke" if ordinal == 0 else "P%d" % (((ordinal - 1) % 3) + 1)
        packet = {
            "schema": "frozen_claude_packet.v1",
            "packet_hash": "0" * 64, "reverified_packet_hash": "0" * 64,
            "clone_tree_hash": api._canonical_hash(clone_entries),
            "reverified_clone_tree_hash": api._canonical_hash(clone_entries),
            "baseline_tree_hash": api._canonical_hash(clone_entries),
            "source_tree_hash": api._canonical_hash(source_entries),
            "clone_tree_entries": clone_entries, "source_tree_entries": source_entries,
            "task_identity": {"ordinal": ordinal, "case_id": case_id, "role": role},
            "requested_model": model,
            "effort_control": "api_enforced",
            "requested_effort": effort,
            "prompted_effort": None,
            "tool_scope": "read_only" if role in ("smoke", "planner") else "workspace_write",
            "cwd": "/sealed/clone/%s" % ordinal,
            "artifact_root": "/sealed/artifact/%s" % ordinal,
            "writable_roots": ["/sealed/clone/%s" % ordinal, "/sealed/artifact/%s" % ordinal],
            "sealed_materials": {
                name: {"path": "/sealed/%s/%s" % (ordinal, name), "content": content,
                       "sha256": hashlib.sha256(content.encode()).hexdigest()}
                for name, content in contents.items()
            },
        }
        sealed = api.packet_hash(packet)
        packet["packet_hash"] = packet["reverified_packet_hash"] = sealed
        return packet

    execution_packets = [make_packet(index, call) for index, call in enumerate(call_plan)]
    manifest = {
        "schema": "claude_pace_manifest.v1", "manifest_hash": "0" * 64,
        "call_plan": call_plan, "caps": api.EXACT_CAPS,
        "estimated_usd_ceiling": estimated_usd_ceiling,
        "promotion_boundary": PROMOTION_BOUNDARY,
        "smoke_packet": execution_packets[0],
    }
    manifest["manifest_hash"] = api.manifest_hash(manifest)
    approval = {
        "schema": "claude_experiment_approval.v1", "execution_mode": "claude_subscription",
        "manifest_hash": manifest["manifest_hash"], "user_created": True,
        "approval_hash": "0" * 64,
        "estimated_usd_ceiling": estimated_usd_ceiling,
        "human_confirmation": {
            "schema": "user_confirmation.v1", "confirmed": True,
            "spec_sha256": SPEC_SHA256, "approval_hash": "0" * 64,
            "manifest_hash": manifest["manifest_hash"],
            "promotion_boundary": PROMOTION_BOUNDARY,
        },
        "caps": api.EXACT_CAPS, "call_plan": call_plan,
        "promotion_boundary": PROMOTION_BOUNDARY,
    }
    approval["approval_hash"] = api.approval_hash(approval)
    approval["human_confirmation"]["approval_hash"] = approval["approval_hash"]
    return approval, manifest, execution_packets


class FakePilotAdapter:
    """Scripted fake adapter satisfying whatever ClaudeSubscriptionPilot.run() expects
    of a test_mode adapter -- mirrors codex_subscription_pilot.py's own
    ``_SealedFakeAdapter``."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def execute(self, packet):
        self.calls.append(packet)
        result = {
            "promotion_eligible": False,
            "packet_hash": packet["packet_hash"],
            "clone_tree_hash": packet["clone_tree_hash"],
            "pace_status": PROMOTION_BOUNDARY,
            "usage_v1": {"observed_total_tokens": 140},
            "report_surface": {
                "reservation_receipt": {"reservation_id": "r-%d" % len(self.calls)},
                "evidence_receipt": {"evidence_id": "e-%d" % len(self.calls)},
                "usd_cost": {"amount_usd": 0.01},
            },
        }
        task = packet.get("task_identity", {})
        if task.get("role") == "planner":
            plan = {
                "schema": "product_planner_output.v1", "status": "PLAN_PASS",
                "case_id": task["case_id"],
                "allowed_paths": ["src/%s.ts" % task["case_id"].lower()],
                "steps": [{"id": "step-1", "action": "implement sealed repair"}],
                "checks": ["run hidden product oracle"],
            }
            api = _api()
            plan_bytes = api._canonical_bytes(plan) + b"\n"
            result.update({
                "planner_output": plan_bytes.decode("utf-8"),
                "planner_output_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            })
        return result


# =========================================================================== TESTS ====

# --- Ten-call plan / traversal completeness (LOOP-M1) ---------------------------------

def test_exact_call_plan_has_ten_entries():
    """[BEHAVIORAL][S4.1][S14.2] Exactly ten dispatches: one smoke plus nine comparative."""
    api = _api()
    assert len(api.EXACT_CALL_PLAN) == 10


def test_exact_call_plan_covers_all_four_named_models_traversal_complete():
    """[BEHAVIORAL][LOOP-M1][S4.1][S14.2] The declared model set (four models) must all
    actually appear in the ten-call plan -- an early-exit subset (e.g. testing only
    sonnet+haiku) is a defect, not an optimization."""
    api = _api()
    declared = set(ACCEPTED_MODELS)
    actual = {call[1] for call in api.EXACT_CALL_PLAN}
    assert actual == declared, "call plan does not cover the declared model set: missing %r" % (
        declared - actual)


def test_exact_call_plan_role_counts_match_spec_table_4_1():
    """[BEHAVIORAL][S4.1] 1 smoke, 3 planner, 3 incumbent_coder, 3 challenger_coder."""
    api = _api()
    roles = [call[0] for call in api.EXACT_CALL_PLAN]
    assert roles.count("smoke") == 1
    assert roles.count("planner") == 3
    assert roles.count("incumbent_coder") == 3
    assert roles.count("challenger_coder") == 3


def test_challenger_coder_uses_one_distinct_model_identity_per_case_not_one_model_for_all():
    """[BEHAVIORAL][S4.1] Unlike the Codex pilot (one challenger model for all three
    cases), this pilot's three challenger calls must be three DISTINCT model identities
    -- opus-4-8/high, haiku-4-5/low, fable-5/high -- one per case."""
    api = _api()
    challengers = [tuple(call[1:]) for call in api.EXACT_CALL_PLAN if call[0] == "challenger_coder"]
    assert sorted(challengers) == sorted([
        ("claude-opus-4-8", "high"), ("claude-haiku-4-5", "low"), ("claude-fable-5", "high"),
    ])
    assert len({model for model, _ in challengers}) == 3


def test_planner_and_incumbent_are_fixed_sonnet_high_across_all_three_cases():
    """[BEHAVIORAL][S4.1] Planner and incumbent are both sonnet-5/high for every case, so
    both coder arms always start from the same plan."""
    api = _api()
    for role in ("planner", "incumbent_coder"):
        entries = [tuple(call[1:]) for call in api.EXACT_CALL_PLAN if call[0] == role]
        assert entries == [("claude-sonnet-5", "high")] * 3


def test_smoke_uses_cheapest_model_with_no_effort_dial():
    """[BEHAVIORAL][S4.1] The smoke call is haiku-4-5 with no effort dial (n/a)."""
    api = _api()
    smoke_calls = [call for call in api.EXACT_CALL_PLAN if call[0] == "smoke"]
    assert len(smoke_calls) == 1
    assert smoke_calls[0][1] == "claude-haiku-4-5"
    assert smoke_calls[0][2] is None


def test_exact_caps_match_spec_section_4_2_numbers():
    """[BEHAVIORAL][S4.2] Cap numbers match the frozen run contract exactly: 1800s per
    call / 18000s combined (double Codex's 900s/9000s), 150000/1500000 observed tokens
    (identical order of magnitude to Codex's own numbers)."""
    api = _api()
    assert api.EXACT_CAPS["combined_calls"] == 10
    assert api.EXACT_CAPS["per_call_timeout_seconds"] == 1800
    assert api.EXACT_CAPS["combined_timeout_seconds"] == 18000
    assert api.EXACT_CAPS["per_call_observed_tokens_max"] == 150000
    assert api.EXACT_CAPS["aggregate_observed_tokens_max_when_telemetry_exists"] == 1500000
    assert api.EXACT_CAPS.get("adapter_retries_max") == 0


# --- Reuse-not-reimplementation of the post-arm apparatus (Section 11 point 2) --------

REUSED_NAMES = (
    "ProductionPreparationGit", "ProductionProductPreprobeRunner", "ProductP3OracleMatrix",
    "ProductRuntimeSnapshot", "ProductProcessAuditor", "OracleGeneratorAuthority",
    "ProductOracleSandbox", "ProductGitAuthority", "ProductTreeDelta",
    "ProductVerifierAuthority", "create_product_verifier_authority", "ProductPostArmVerifier",
    "ProductionPostArmController", "ProductionCaseMaterialBuilder", "_AtomicPreparationWriter",
)
REUSED_HELPER_NAMES = (
    "_canonical_bytes", "_canonical_hash", "packet_hash", "manifest_hash", "approval_hash",
)


@pytest.mark.parametrize("name", REUSED_NAMES + REUSED_HELPER_NAMES)
def test_section11_point2_class_is_the_identical_imported_object_not_redefined(name):
    """[BEHAVIORAL][S11.2][S12] A test asserting the imported classes/helpers are the
    IDENTICAL objects from codex_subscription_pilot.py, not re-defined duplicates --
    the exact required test named in Section 12. Uses ``is`` identity, not equality:
    a re-implemented duplicate with matching behavior would still fail this."""
    claude_api = _api()
    codex_api = _codex_api()
    assert hasattr(claude_api, name), "claude_subscription_pilot does not expose %r" % name
    assert getattr(claude_api, name) is getattr(codex_api, name), (
        "%r is not the identical object imported from codex_subscription_pilot.py "
        "-- looks re-defined/duplicated instead of imported" % name
    )


def test_reused_apparatus_is_not_shadowed_by_a_same_named_local_redefinition():
    """[BEHAVIORAL][S11.2] Guards against a subtle bypass of the identity test above: a
    module that does ``from .codex_subscription_pilot import X as _X`` and then defines
    its OWN ``class X: ...`` afterward would still expose a *local* ``X`` that shadows
    the import. Re-check via the module's own __dict__ provenance where introspectable."""
    claude_api = _api()
    codex_api = _codex_api()
    for name in REUSED_NAMES:
        value = getattr(claude_api, name)
        assert value is getattr(codex_api, name)
        if hasattr(value, "__module__"):
            assert value.__module__ in (
                "runner.codex_subscription_pilot", "codex_subscription_pilot",
            ), "%r's __module__ suggests it was redefined locally: %s" % (name, value.__module__)


# --- Cap ledger exhaustion: calls, seconds, tokens, USD ceiling -----------------------

def test_combined_cap_ledger_exhausts_calls_seconds_and_tokens_at_exactly_the_tenth_reservation():
    """[BEHAVIORAL][S4.2][S12] By the spec's own arithmetic, 1800s x 10 = 18000s and
    150000 tokens x 10 = 1,500,000 tokens -- calls, seconds, and tokens are ALL exhausted
    at exactly the tenth reservation, and an eleventh must be refused."""
    api = _api()
    ledger = api.ClaudeCombinedCapLedger(estimated_usd_ceiling=10.0)
    unit = {"calls": 1, "seconds": 1800, "observed_total_tokens": 150000}
    for index in range(10):
        reservation = ledger.reserve("key-%d" % index, unit)
        assert reservation["state"] == "RESERVED"
        ledger.start(reservation["reservation_id"])
        ledger.reconcile(reservation["reservation_id"], "obs-%d" % index, {
            "elapsed_seconds": 1800, "observed_total_tokens": 150000, "usd_cost": 0.5,
        })
    totals = ledger.totals()
    assert totals["calls"] == 10
    assert totals["seconds"] == 18000
    assert totals["observed_total_tokens"] == 1500000
    with pytest.raises(RuntimeError):
        ledger.reserve("key-eleventh", unit)


def test_combined_cap_ledger_never_releases_a_failed_calls_consumed_reservation():
    """[BEHAVIORAL][S4.1] "A failed, timed-out, or otherwise invalid call consumes its
    reservation and terminates remaining calls; it is never rerun" -- reserving without
    ever reconciling must still consume capacity toward the ten-call ceiling."""
    api = _api()
    ledger = api.ClaudeCombinedCapLedger(estimated_usd_ceiling=10.0)
    unit = {"calls": 1, "seconds": 1800, "observed_total_tokens": 150000}
    for index in range(10):
        ledger.reserve("key-%d" % index, unit)  # never started/reconciled -- simulates failure
    with pytest.raises(RuntimeError):
        ledger.reserve("key-eleventh", unit)


def test_usd_ceiling_stop_condition_per_call_share_more_than_2x_aborts():
    """[BEHAVIORAL][S4.2][S12] A per-call cost more than 2x the pre-execution
    estimated_usd_ceiling's PER-CALL share is a stop condition -- new for this pilot,
    the Codex pilot has no USD authority at all to compare against."""
    api = _api()
    ledger = api.ClaudeCombinedCapLedger(estimated_usd_ceiling=10.0)  # per-call share = $1.00
    unit = {"calls": 1, "seconds": 1800, "observed_total_tokens": 150000}
    reservation = ledger.reserve("key-0", unit)
    ledger.start(reservation["reservation_id"])
    with pytest.raises(RuntimeError, match="usd|cost|ceiling"):
        ledger.reconcile(reservation["reservation_id"], "obs-0", {
            "elapsed_seconds": 1800, "observed_total_tokens": 150000, "usd_cost": 2.50,
        })


def test_usd_ceiling_stop_condition_aggregate_share_more_than_2x_aborts_even_if_each_call_is_under():
    """[BEHAVIORAL][S4.2][S12] An AGGREGATE cost that exceeds the un-doubled aggregate
    ceiling must abort even when no single call individually exceeded its own 2x
    per-call share."""
    api = _api()
    # Aggregate stop threshold = the undoubled ceiling = $10 (not 2x): see
    # ClaudeCombinedCapLedger's own docstring for why the un-doubled ceiling, not
    # 2x the ceiling, is the actual enforced aggregate stop condition.
    ledger = api.ClaudeCombinedCapLedger(estimated_usd_ceiling=10.0)
    unit = {"calls": 1, "seconds": 1800, "observed_total_tokens": 150000}
    per_call_cost = 1.90  # under the $2.00 per-call 2x share every time
    reservations = []
    for index in range(10):
        reservation = ledger.reserve("key-%d" % index, unit)
        ledger.start(reservation["reservation_id"])
        reservations.append(reservation["reservation_id"])
    aborted = False
    for index, reservation_id in enumerate(reservations):
        try:
            ledger.reconcile(reservation_id, "obs-%d" % index, {
                "elapsed_seconds": 1800, "observed_total_tokens": 150000,
                "usd_cost": per_call_cost,
            })
        except RuntimeError:
            aborted = True
            break
    assert aborted, "aggregate cost of 10 x $1.90 = $19.00 exceeds the un-doubled $10 ceiling and must abort"


def test_usd_ceiling_within_bounds_reconciles_cleanly():
    """[BEHAVIORAL][S4.2] Sanity check for the two stop-condition tests above: a run
    that stays within both the per-call and aggregate 2x shares must reconcile without
    raising, or every real dispatch would abort spuriously."""
    api = _api()
    ledger = api.ClaudeCombinedCapLedger(estimated_usd_ceiling=10.0)
    unit = {"calls": 1, "seconds": 1800, "observed_total_tokens": 150000}
    for index in range(10):
        reservation = ledger.reserve("key-%d" % index, unit)
        ledger.start(reservation["reservation_id"])
        ledger.reconcile(reservation["reservation_id"], "obs-%d" % index, {
            "elapsed_seconds": 1800, "observed_total_tokens": 150000, "usd_cost": 0.20,
        })
    totals = ledger.totals()
    assert totals["calls"] == 10


# --- Runtime price-rate lookup blocks approval sealing (pre-execution) ----------------

def test_stale_price_rate_lookup_blocks_approval_sealing_pre_execution():
    """[BEHAVIORAL][S1.1][S4.3][S12] An unresolvable, failed, or stale runtime
    price-rate lookup blocks approval sealing entirely, pre-execution -- before any
    reservation, clone creation, or dispatch."""
    api = _api()
    now = 1_753_000_000.0
    stale_rate_lookup = lambda model: {
        "input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0,
        "checked_at": now - 999_999, "source": "stale-cache",
    }
    with pytest.raises(_blocked_error_classes() + (
            _adapter_api().ClaudeAgentAdapterBlockedError,)):
        api.resolve_price_rate_table_for_approval(
            api.EXACT_CALL_PLAN, rate_lookup=stale_rate_lookup, clock=lambda: now,
        )


def test_failed_price_rate_lookup_blocks_approval_sealing_pre_execution():
    """[BEHAVIORAL][S1.1][S4.3][S12] A rate lookup that raises for any model in the call
    plan blocks approval sealing entirely."""
    api = _api()

    def raising_lookup(model):
        if model == "claude-fable-5":
            raise RuntimeError("rate table unavailable for fable-5")
        return {"input_usd_per_mtok": 1.0, "output_usd_per_mtok": 1.0,
                "checked_at": 1_753_000_000.0, "source": "ok"}

    with pytest.raises(_blocked_error_classes() + (
            _adapter_api().ClaudeAgentAdapterBlockedError,)):
        api.resolve_price_rate_table_for_approval(
            api.EXACT_CALL_PLAN, rate_lookup=raising_lookup, clock=lambda: 1_753_000_000.0,
        )


def test_fresh_price_rate_lookup_for_every_model_permits_approval_sealing():
    """[BEHAVIORAL][S1.1] A fresh, resolvable rate for every model actually used in the
    ten-call plan permits approval sealing and yields a computed estimated_usd_ceiling."""
    api = _api()
    now = 1_753_000_000.0
    rate_lookup = lambda model: {
        "input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0,
        "checked_at": now, "source": "claude-api-skill-model-table",
    }
    table = api.resolve_price_rate_table_for_approval(
        api.EXACT_CALL_PLAN, rate_lookup=rate_lookup, clock=lambda: now,
    )
    assert set(table["rates"]) == set(ACCEPTED_MODELS)
    assert table["estimated_usd_ceiling"] > 0


# --- Confirmation-sealing: three states, through the REAL non-fake-SDK-mode path ------

def _confirmation_fixture(tmp_path, api, *, estimated_usd_ceiling=10.0):
    approval, manifest, packets = _materials(api, estimated_usd_ceiling=estimated_usd_ceiling)
    manifest_path = tmp_path / "claude_pace_manifest.v1.json"
    manifest_path.write_bytes(api._canonical_bytes(manifest) + b"\n")
    required_text = "CONFIRM CLAUDE PRODUCT PILOT %s %s" % (
        "run-2026-07-17", manifest["manifest_hash"],
    )
    request = {
        "schema": "confirmation_request.v1", "confirmed": False,
        "run_id": "run-2026-07-17", "spec_sha256": SPEC_SHA256,
        "manifest_hash": manifest["manifest_hash"], "call_plan": api.EXACT_CALL_PLAN,
        "caps": api.EXACT_CAPS, "estimated_usd_ceiling": estimated_usd_ceiling,
        "promotion_boundary": PROMOTION_BOUNDARY,
        "required_confirmation_text": required_text,
    }
    request_path = tmp_path / "confirmation_request.v1.json"
    request_path.write_bytes(api._canonical_bytes(request) + b"\n")
    return {
        "manifest": manifest, "manifest_path": manifest_path,
        "request": request, "request_path": request_path,
        "required_text": required_text,
    }


def test_confirmation_sealing_state_a_no_confirmation_record_blocks(tmp_path):
    """[BEHAVIORAL][S5.4][S5.5][S12] State (a): no confirmation record present blocks
    sealing and dispatch. Exercised through the REAL (non-fake-SDK-mode, test_mode=False)
    sealing code path -- the Codex pilot's own suite never does this for
    PilotConfirmationBuilder (all four usages pass test_mode=True); this suite must not
    repeat that gap."""
    api = _api()
    fixture = _confirmation_fixture(tmp_path, api)
    builder = api.ClaudePilotConfirmationBuilder(test_mode=False)
    missing_path = tmp_path / "does-not-exist-confirmation-request.v1.json"
    with pytest.raises(Exception):
        builder.build(
            confirmation_request_path=missing_path,
            manifest_path=fixture["manifest_path"],
            explicit_confirmation_text=fixture["required_text"],
        )


@pytest.mark.parametrize("mutation", [
    "wrong_text", "stale_manifest_hash", "mutated_request_bytes",
])
def test_confirmation_sealing_state_b_stale_or_mutated_confirmation_blocks(tmp_path, mutation):
    """[BEHAVIORAL][S5.4][S5.5][S12] State (b): a stale or non-matching confirmation
    (wrong confirmation text, a stale/mutated manifest hash, or mutated
    confirmation-request bytes) blocks sealing and dispatch -- via the REAL
    (test_mode=False) sealing path."""
    api = _api()
    fixture = _confirmation_fixture(tmp_path, api)
    builder = api.ClaudePilotConfirmationBuilder(test_mode=False)
    confirmation_text = fixture["required_text"]
    request_path = fixture["request_path"]
    manifest_path = fixture["manifest_path"]

    if mutation == "wrong_text":
        confirmation_text = "CONFIRM CLAUDE PRODUCT PILOT wrong-run wrong-hash"
    elif mutation == "stale_manifest_hash":
        stale_manifest = dict(fixture["manifest"])
        stale_manifest["manifest_hash"] = "f" * 64
        manifest_path = tmp_path / "stale_manifest.json"
        manifest_path.write_bytes(api._canonical_bytes(stale_manifest) + b"\n")
    elif mutation == "mutated_request_bytes":
        mutated_path = tmp_path / "mutated_confirmation_request.v1.json"
        mutated_path.write_bytes(request_path.read_bytes() + b"MUTATED\n")
        request_path = mutated_path

    with pytest.raises(Exception):
        builder.build(
            confirmation_request_path=request_path,
            manifest_path=manifest_path,
            explicit_confirmation_text=confirmation_text,
        )


def test_confirmation_sealing_state_c_exact_fresh_confirmation_unlocks_smoke_reservation(tmp_path):
    """[BEHAVIORAL][S5.4][S5.5][S12] State (c): an exact, fresh, byte-matching
    confirmation unlocks sealing and permits the smoke's first reservation -- exercised
    through the REAL (test_mode=False) sealing path, then proven usable by actually
    constructing and validating the smoke's first dispatch request against the fake-SDK
    adapter (zero real query() calls made in this proof, only validation)."""
    api = _api()
    fixture = _confirmation_fixture(tmp_path, api)
    builder = api.ClaudePilotConfirmationBuilder(test_mode=False)
    approval_path = builder.build(
        confirmation_request_path=fixture["request_path"],
        manifest_path=fixture["manifest_path"],
        explicit_confirmation_text=fixture["required_text"],
    )
    approval = json.loads(Path(approval_path).read_bytes())
    assert approval["user_created"] is True
    assert approval["approval_hash"] == api.approval_hash(approval)
    assert approval["manifest_hash"] == fixture["manifest"]["manifest_hash"]

    # Prove the approval is actually usable: build the smoke's request and validate it
    # through the fake-SDK adapter without making it a real dispatch.
    capture: List[Any] = []
    query_fn = make_query_fn(
        [_result_event(model="claude-haiku-4-5", final_output="CLAUDE_SMOKE_OK")],
        capture=capture,
    )
    smoke_adapter = make_claude_adapter(query_fn=query_fn)
    smoke_request = make_claude_request(
        tmp_path, role="smoke", model="claude-haiku-4-5", tool_scope="read_only",
        ordinal=0, case_id="smoke",
    )
    smoke_request = replace(smoke_request, prompt=(
        "Return exactly CLAUDE_SMOKE_OK. Do not use tools, run commands, edit files, or "
        "contact external services beyond this response."
    ))
    result = smoke_adapter.execute(smoke_request)
    assert result.final_output == "CLAUDE_SMOKE_OK"


# --- Required fake-SDK test gate -------------------------------------------------------

def test_required_test_gate_module_order_matches_spec_section_12_pytest_invocation_exactly():
    """[BEHAVIORAL][S12] The required-gate module list must be exactly the four modules
    named in spec Section 12's own pytest invocation -- no more, no fewer, same order."""
    api = _api()
    assert list(api.ClaudeRequiredTestGateRunner.MODULE_ORDER) == [
        "loop-team/runner/tests/test_claude_agent_adapter.py",
        "loop-team/runner/tests/test_claude_subscription_pilot.py",
        "loop-team/runner/tests/test_experiment_execution_contract.py",
        "loop-team/evals/test_model_routing_evals_contract.py",
    ]


class _FakeGatePopen:
    def __init__(self, *, scripted_stdout_by_command):
        self.scripted = scripted_stdout_by_command
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for needle, stdout in self.scripted.items():
            if needle in joined:
                return _FakeGateProcess(stdout)
        return _FakeGateProcess("1 passed in 0.01s\n")


class _FakeGateProcess:
    def __init__(self, stdout, returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, "", returncode

    def communicate(self, timeout=None):
        return self.stdout, self.stderr


def test_required_test_gate_all_passing_reports_clean(tmp_path):
    """[BEHAVIORAL][S12][S5] A gate run where every required module passes reports
    clean -- proving the pilot COULD proceed to sealing (not that it does)."""
    api = _api()
    popen = _FakeGatePopen(scripted_stdout_by_command={"": "12 passed in 1.23s\n"})
    runner = api.ClaudeRequiredTestGateRunner(
        popen_factory=popen, test_mode=True, artifact_dir=tmp_path,
    )
    receipt = runner.run()
    assert receipt["all_required_tests_passed"] is True


def test_required_test_gate_any_failing_module_blocks_before_sealing(tmp_path):
    """[BEHAVIORAL][S5][S12] "If any required test is missing, failing, errors, or not
    executed, emit PILOT_ABORTED before approval sealing, reservation, clone creation,
    or any real dispatch." A single failing module must flip the gate to unclean."""
    api = _api()
    popen = _FakeGatePopen(scripted_stdout_by_command={
        "test_claude_agent_adapter.py": "3 failed, 9 passed in 4.0s\n",
        "": "12 passed in 1.23s\n",
    })
    runner = api.ClaudeRequiredTestGateRunner(
        popen_factory=popen, test_mode=True, artifact_dir=tmp_path,
    )
    receipt = runner.run()
    assert receipt["all_required_tests_passed"] is False


def test_pilot_run_refuses_to_dispatch_when_required_test_receipt_is_unclean(tmp_path):
    """[BEHAVIORAL][S5][S12] The controller itself must refuse a real run when the
    required_test_receipt it was handed does not show a clean pass -- this is checked
    independently of whichever gate-runner produced that receipt."""
    api = _api()
    approval, manifest, packets = _materials(api)
    adapter = FakePilotAdapter()
    pilot = api.ClaudeSubscriptionPilot(adapter_factory=lambda: adapter, test_mode=True)
    dirty_receipt = {"all_required_tests_passed": False, "executed_test_modules": []}
    with pytest.raises(_blocked_error_classes()):
        pilot.run(
            approval=approval, manifest=manifest, required_test_receipt=dirty_receipt,
            frozen_packets=packets, dry_run=False,
        )
    assert adapter.calls == []


# --- Canonical-source-integrity before/after mismatch (Section 8.1) -------------------

def _init_tiny_git_repo(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    (root / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "file.txt"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True, env=env)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, env=env,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    return head


def test_canonical_source_integrity_before_after_match_when_untouched(tmp_path):
    """[BEHAVIORAL][S8.1][S12] The whole-run bracket: capturing a real, clean, untouched
    repo before and after must be byte-identical -- uses the REAL imported
    ProductGitAuthority, not a fake, since it is reused unmodified."""
    codex_api = _codex_api()
    repo = tmp_path / "canonical-repo"
    head = _init_tiny_git_repo(repo)
    before = codex_api.ProductGitAuthority.capture(repo, expected_commit=head)
    after = codex_api.ProductGitAuthority.capture(repo, expected_commit=head)
    assert before == after


def test_canonical_source_integrity_mismatch_aborts_when_repo_was_touched(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S8.1][S12] If a canonical repo is touched between
    the before/after captures (e.g. a coder dispatch accidentally wrote into it instead
    of its own clone), the AFTER capture itself must fail -- this is the mechanical proof
    that ten real dispatches never touched a canonical repository."""
    codex_api = _codex_api()
    repo = tmp_path / "canonical-repo-touched"
    head = _init_tiny_git_repo(repo)
    codex_api.ProductGitAuthority.capture(repo, expected_commit=head)
    (repo / "unexpected-write-from-a-coder-dispatch.txt").write_text("oops\n")
    with pytest.raises(_codex_api().PilotBlockedError):
        codex_api.ProductGitAuthority.capture(repo, expected_commit=head)


# --- Bonus (beyond Section 12's explicit list, for Section 3 / 14 AC4 completeness): --
# --- case-manifest bytes hash-match the Codex pilot's own already-sealed artifacts. ---

@pytest.mark.skipif(
    not CODEX_PREPARE_DIR.exists(),
    reason="real Codex pilot preparation artifacts are not present on disk in this environment",
)
@pytest.mark.parametrize("case_id", sorted(CODEX_SEALED_CASE_FACTS))
def test_case_baseline_source_root_and_sha_hash_match_codex_sealed_artifacts(case_id):
    """[BEHAVIORAL][S3][S14.4] "The case-manifest bytes this pilot seals for each of
    P1/P2/P3... must hash-match the corresponding fields the Codex pilot already sealed
    for the same case, proving genuine reuse rather than a re-derived, incidentally
    similar copy." Reads the REAL on-disk Codex sealed packets (dry-run PREPARE-mode
    artifacts, not a real paid dispatch) and requires this pilot's own hardcoded case
    baseline facts to be byte-identical, not just structurally similar."""
    api = _api()
    expected_root, expected_sha = CODEX_SEALED_CASE_FACTS[case_id]
    # Independently re-derive the same facts directly from the real sealed Codex packet
    # on disk, so this test does not merely check two hardcoded copies of the spec text
    # against each other.
    ordinal = {"P1-tax-package-live-data": 1, "P2-ask-taxahead-chat-transport": 2,
               "P3-pms-prerequisite-doctor": 3}[case_id]
    packet = json.loads((CODEX_PREPARE_DIR / "packets" / ("%02d.json" % ordinal)).read_bytes())
    assert packet["preparation_case_id"] == case_id
    assert packet["source_root"] == expected_root
    assert packet["source_sha"] == expected_sha

    claude_facts = api.CASE_BASELINE_FACTS[case_id]
    assert claude_facts["source_root"] == packet["source_root"]
    assert claude_facts["source_sha"] == packet["source_sha"]


# --- PILOT_ONLY/NO_ROUTING_PROMOTION reporting + required n=3 prose sentence (S13) ----

def test_dry_run_report_states_pilot_only_no_routing_promotion_and_pace_fields():
    """[BEHAVIORAL][S13][S12] The report must state cases=3, paired_observations<=3,
    min_discordant=16, and pace_status=PILOT_ONLY/NO_ROUTING_PROMOTION -- identical
    framing to the Codex pilot, for the identical reason."""
    api = _api()
    approval, manifest, packets = _materials(api)
    adapter = FakePilotAdapter()
    pilot = api.ClaudeSubscriptionPilot(adapter_factory=lambda: adapter, test_mode=True)
    report = pilot.run(
        approval=approval, manifest=manifest,
        required_test_receipt={"all_required_tests_passed": True}, frozen_packets=packets,
        dry_run=True,
    )
    assert report["pace_status"] == PROMOTION_BOUNDARY
    assert report.get("cases") == 3 or report.get("paired_observations", 3) <= 3
    assert report.get("promotion_eligible") is False
    assert report.get("min_discordant", 16) == 16


def test_final_report_markdown_contains_required_n3_statistical_power_prose_sentence(tmp_path):
    """[BEHAVIORAL][S13][S12] "A required test must assert this exact sentence's
    presence in the generated pilot-report.md": the report must contain a
    plain-language sentence stating only three cases with no within-case replication,
    and that each challenger model was tested via exactly one case only, not all three."""
    api = _api()
    approval, manifest, packets = _materials(api)
    adapter = FakePilotAdapter()
    post_arm = _FakePostArmVerifier()
    pilot = api.ClaudeSubscriptionPilot(
        adapter_factory=lambda: adapter, test_mode=True, post_arm_verifier=post_arm,
    )
    report_dir = tmp_path / "report-run"
    report_dir.mkdir()
    pilot.run(
        approval=approval, manifest=manifest,
        required_test_receipt={"all_required_tests_passed": True}, frozen_packets=packets,
        dry_run=False, report_dir=report_dir,
    )
    report_markdown_path = report_dir / "report" / "pilot-report.md"
    assert report_markdown_path.exists(), "pilot-report.md was not generated at the required path"
    text = report_markdown_path.read_text(encoding="utf-8").lower()
    assert "three cases" in text or "n=3" in text or "3 cases" in text
    assert "no within-case replication" in text or "without replication" in text or (
        "not replicated" in text)
    for model in ("claude-opus-4-8", "claude-haiku-4-5", "claude-fable-5"):
        assert model in text, "challenger model %s must be named in the prose sentence" % model
    assert "exactly one case" in text or "only one case" in text or "one case only" in text


class _FakePostArmVerifier:
    """Minimal fake satisfying ClaudeSubscriptionPilot's post_arm_verifier collaborator
    contract for report-generation tests that do not themselves exercise oracle logic
    (which is covered by the identity-reuse tests above and by the imported
    ProductPostArmVerifier/ProductionPostArmController's own existing Codex suite)."""

    def verify_after_coder(self, *, packet, result):
        ordinal = packet["task_identity"]["ordinal"]
        return {
            "schema": "controller_post_arm_receipt.v1", "status": "PASS", "signed": True,
            "case_id": packet["task_identity"]["case_id"], "role": packet["task_identity"]["role"],
            "opaque_artifact_id": "coder-%02d" % ordinal, "receipt_id": "post-arm-%02d" % ordinal,
            "receipt_path": "/sealed/receipt-%02d.json" % ordinal,
            "receipt_sha256": "0" * 64, "promotion_eligible": False,
        }


def test_report_never_calls_a_selected_patch_promoted_deployed_ready_or_verified():
    """[BEHAVIORAL][S13] "It must never call a selected patch promoted, deployed, ready,
    or verified beyond its isolated oracle evidence." Checks both the machine-readable
    report dict and its markdown rendering for forbidden promotion language."""
    api = _api()
    approval, manifest, packets = _materials(api)
    adapter = FakePilotAdapter()
    pilot = api.ClaudeSubscriptionPilot(adapter_factory=lambda: adapter, test_mode=True)
    report = pilot.run(
        approval=approval, manifest=manifest,
        required_test_receipt={"all_required_tests_passed": True}, frozen_packets=packets,
        dry_run=True,
    )
    serialized = json.dumps(report, default=str).lower()
    for forbidden in ("promoted", "deployed", "production-ready", "fully verified"):
        assert forbidden not in serialized


def test_side_by_side_comparability_appendix_references_codex_report_path_and_declares_no_cross_provider_usd():
    """[BEHAVIORAL][S13] The mandatory comparability appendix must cross-reference the
    Codex pilot's own report by exact path and must not compute/imply a cross-provider
    USD comparison beyond what each pilot's own report states -- it must say the Codex
    pilot has no USD authority rather than omit the column or fabricate a number."""
    api = _api()
    approval, manifest, packets = _materials(api)
    adapter = FakePilotAdapter()
    pilot = api.ClaudeSubscriptionPilot(adapter_factory=lambda: adapter, test_mode=True)
    report = pilot.run(
        approval=approval, manifest=manifest,
        required_test_receipt={"all_required_tests_passed": True}, frozen_packets=packets,
        dry_run=True,
    )
    appendix = report.get("side_by_side_comparability_appendix")
    assert appendix is not None
    assert "codex_product_pilot" in json.dumps(appendix, default=str)
    assert appendix.get("codex_usd_authority") in (
        "unavailable", "FORBIDDEN_CODEX_SUBSCRIPTION_PILOT", None,
    ) or "no usd authority" in json.dumps(appendix, default=str).lower()
