"""Authority-gated controller for the fixed non-promoting Claude subscription pilot.

Spec: loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md

Structurally mirrors ``codex_subscription_pilot.py``'s ``CodexSubscriptionPilot`` (same
validate -> ten-call loop -> report shape), but this module never reimplements the
Codex pilot's own post-arm apparatus, canonical-hash helpers, or preparation/oracle
machinery -- Section 11 point 2 requires importing those objects directly (identity,
not structural resemblance) since two separate concurrent sessions are actively
patching ``codex_subscription_pilot.py`` and ``codex_exec_adapter.py`` right now for an
unrelated argv-ordering bug fix. This module only ever reads those two files.

What is genuinely new here (not reused from Codex, because the Codex pilot has no
equivalent): the four-distinct-challenger-model ten-call plan (Section 4.1), the USD
ceiling stop condition on the combined cap ledger (Section 4.2/4.3 -- the Codex pilot
has no USD authority at all), the runtime price-rate lookup gate on approval sealing
(Section 4.3), and the mandatory side-by-side comparability appendix plus the n=3
statistical-power prose sentence (Section 13).
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from .codex_subscription_pilot import (
        PilotBlockedError,
        _canonical_bytes,
        _canonical_hash,
        packet_hash,
        manifest_hash,
        approval_hash,
        _AtomicPreparationWriter,
        ProductionPreparationGit,
        ProductionProductPreprobeRunner,
        ProductP3OracleMatrix,
        ProductRuntimeSnapshot,
        ProductProcessAuditor,
        OracleGeneratorAuthority,
        ProductOracleSandbox,
        ProductGitAuthority,
        ProductTreeDelta,
        ProductVerifierAuthority,
        create_product_verifier_authority,
        ProductPostArmVerifier,
        ProductionPostArmController,
        ProductionCaseMaterialBuilder,
    )
    from .claude_agent_adapter import (
        ClaudeAgentAdapterBlockedError,
        resolve_current_usd_rate,
    )
except ImportError:  # Direct script execution.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runner.codex_subscription_pilot import (  # type: ignore[no-redef]
        PilotBlockedError,
        _canonical_bytes,
        _canonical_hash,
        packet_hash,
        manifest_hash,
        approval_hash,
        _AtomicPreparationWriter,
        ProductionPreparationGit,
        ProductionProductPreprobeRunner,
        ProductP3OracleMatrix,
        ProductRuntimeSnapshot,
        ProductProcessAuditor,
        OracleGeneratorAuthority,
        ProductOracleSandbox,
        ProductGitAuthority,
        ProductTreeDelta,
        ProductVerifierAuthority,
        create_product_verifier_authority,
        ProductPostArmVerifier,
        ProductionPostArmController,
        ProductionCaseMaterialBuilder,
    )
    from runner.claude_agent_adapter import (  # type: ignore[no-redef]
        ClaudeAgentAdapterBlockedError,
        resolve_current_usd_rate,
    )


# --------------------------------------------------------------------------- constants

# The real, current, reviewed spec's own sha256 -- this pilot's fifth plan-check round
# fully rewrote Section 6.1 (the compatibility preflight), which changed the spec
# file's bytes; this constant binds to that reviewed final version, never a draft.
SPEC_SHA256 = "698d23284f4de930c84d66551cd5e11dab717ca14af19a02c7d8e6472a0058bf"
PROMOTION_BOUNDARY = "PILOT_ONLY/NO_ROUTING_PROMOTION"
ACCEPTED_MODELS = (
    "claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5", "claude-fable-5",
)

# Section 4.1's frozen ten-call plan: [role, model, effort-or-None]. Unlike the Codex
# pilot (one challenger model for all three cases), the three challenger_coder calls
# here are three DISTINCT model identities, one per case.
EXACT_CALL_PLAN = [
    ["smoke", "claude-haiku-4-5", None],
    ["planner", "claude-sonnet-5", "high"],
    ["planner", "claude-sonnet-5", "high"],
    ["planner", "claude-sonnet-5", "high"],
    ["incumbent_coder", "claude-sonnet-5", "high"],
    ["incumbent_coder", "claude-sonnet-5", "high"],
    ["incumbent_coder", "claude-sonnet-5", "high"],
    ["challenger_coder", "claude-opus-4-8", "high"],
    ["challenger_coder", "claude-haiku-4-5", "low"],
    ["challenger_coder", "claude-fable-5", "high"],
]

# Section 4.2's frozen cap numbers.
EXACT_CAPS = {
    "combined_calls": 10,
    "per_call_timeout_seconds": 1800,
    "combined_timeout_seconds": 18000,
    "per_call_observed_tokens_max": 150000,
    "aggregate_observed_tokens_max_when_telemetry_exists": 1500000,
    "adapter_retries_max": 0,
}

# Section 3's table -- reused, byte-for-byte, from the Codex pilot's own sealed case
# facts (source repository path + pinned SHA per case). This pilot does not get to
# redefine P1/P2/P3's ground truth; it inherits it.
CASE_BASELINE_FACTS = {
    "P1-tax-package-live-data": {
        "source_root": "<HOME>/Claude/Projects/taxahead-integration",
        "source_sha": "a78f13598cf7a425de4bd20e92d6b97f140eedb3",
    },
    "P2-ask-taxahead-chat-transport": {
        "source_root": "<HOME>/Claude/Projects/taxahead-integration",
        "source_sha": "a78f13598cf7a425de4bd20e92d6b97f140eedb3",
    },
    "P3-pms-prerequisite-doctor": {
        "source_root": "<HOME>/Claude/Projects/padsplit-reverification/pms",
        "source_sha": "4a396220b598d640e4bea5fb703c24efe83c23c5",
    },
}

REQUIRED_MATERIALS = frozenset({"prompt", "plan", "oracle", "test", "dependency", "preprobe"})

# The n=3 statistical-power sentence Section 13 requires verbatim in pilot-report.md --
# a required test asserts this exact prose is present, not merely the machine fields.
N3_STATISTICAL_POWER_SENTENCE = (
    "This pilot has three cases with no within-case replication; each challenger "
    "model (claude-opus-4-8, claude-haiku-4-5, claude-fable-5) was tested via exactly "
    "one case only, not all three."
)


class ClaudePilotBlockedError(PilotBlockedError):
    """Claude-pilot-specific marker subclass of the reused ``PilotBlockedError``.

    Section 11 point 2's import list does not name a trivial blocked-error marker
    exception explicitly for this controller, so either reusing ``PilotBlockedError``
    directly or defining a mirrored subclass is a defensible choice (this suite's own
    ``_blocked_error_classes()`` helper accepts either). A subclass is used here -- not
    a duplicate/unrelated class -- so ``isinstance``/``except PilotBlockedError`` checks
    written against the reused Codex type still work uniformly, while call sites in
    this module can be identified as Claude-specific in a traceback.
    """


def _wall_clock() -> float:
    return time.time()


# ------------------------------------------------------------------- combined cap ledger

class ClaudeCombinedCapLedger:
    """In-process ledger enforcing the sealed combined Claude-pilot caps.

    Mirrors ``codex_subscription_pilot._CombinedCapLedger`` (reserve -> start ->
    reconcile, atomic, never releasing a failed call's consumed reservation) with new
    cap values (Section 4.2) plus the one dimension the Codex ledger has no equivalent
    for at all: a real USD ceiling stop condition (Section 4.2/4.3), since only this
    pilot has USD billing authority (Section 1.1).

    USD ceiling interpretation (a judgment call, documented for review): Section 4.2's
    prose -- "a per-call or aggregate cost more than 2x the pre-execution
    estimated_usd_ceiling's per-call/aggregate share is a stop condition" -- is
    ambiguous about what the "aggregate ... share" actually equals. Read fully
    literally and symmetrically (aggregate share = the whole ceiling, so the aggregate
    stop is "2x the ceiling"), the aggregate check becomes mathematically unable to
    ever catch anything the per-call check does not already catch on its own: since
    per_call_share = ceiling / combined_calls by construction, combined_calls x
    (2 x per_call_share) == 2 x ceiling exactly -- so if no individual call exceeds its
    own 2x per-call share, the sum of exactly ``combined_calls`` such calls can never
    exceed 2x the ceiling either. That would make the aggregate check pure redundant
    dead code, which contradicts the spec's own framing of it as an independent
    backstop ("an honest budget backstop the Codex pilot has no equivalent for"). This
    implementation instead treats the un-doubled ceiling itself as the aggregate stop
    threshold (exceeding what was disclosed to the user AT ALL is unacceptable, with
    zero slack at the aggregate level, while individual calls get 2x slack since
    per-call variance is expected to exceed aggregate variance) -- the only reading
    that makes the aggregate check meaningfully stricter than N independent per-call
    checks, consistent with the spec's own "honest budget backstop" framing.
    """

    def __init__(self, *, estimated_usd_ceiling: float) -> None:
        if not isinstance(estimated_usd_ceiling, (int, float)) or isinstance(
                estimated_usd_ceiling, bool) or estimated_usd_ceiling <= 0:
            raise ValueError("estimated_usd_ceiling must be a positive number")
        self.estimated_usd_ceiling = float(estimated_usd_ceiling)
        self._per_call_usd_share = self.estimated_usd_ceiling / EXACT_CAPS["combined_calls"]
        self._lock = threading.Lock()
        self._next_id = 0
        self._reservations: Dict[str, Dict[str, Any]] = {}
        self._reserved_calls = 0
        self._reserved_seconds = 0
        self._reserved_tokens = 0
        self._observed_tokens = 0
        self._observed_usd_cost = 0.0

    def reserve(self, reservation_key: str, requested: Dict[str, Any]) -> Dict[str, Any]:
        expected = {
            "calls": 1,
            "seconds": EXACT_CAPS["per_call_timeout_seconds"],
            "observed_total_tokens": EXACT_CAPS["per_call_observed_tokens_max"],
        }
        if requested != expected or not isinstance(reservation_key, str) or not reservation_key:
            raise RuntimeError("reservation differs from the exact pilot cap unit")
        with self._lock:
            if (self._reserved_calls + 1 > EXACT_CAPS["combined_calls"]
                    or self._reserved_seconds + expected["seconds"]
                    > EXACT_CAPS["combined_timeout_seconds"]
                    or self._reserved_tokens + expected["observed_total_tokens"]
                    > EXACT_CAPS["aggregate_observed_tokens_max_when_telemetry_exists"]):
                raise RuntimeError("combined pilot cap exhausted")
            self._next_id += 1
            reservation_id = "claude-pilot-reservation-%d" % self._next_id
            self._reservations[reservation_id] = {
                "state": "RESERVED", "reservation_key": reservation_key,
            }
            self._reserved_calls += 1
            self._reserved_seconds += expected["seconds"]
            self._reserved_tokens += expected["observed_total_tokens"]
            return {"reservation_id": reservation_id, "state": "RESERVED"}

    def start(self, reservation_id: str) -> Dict[str, Any]:
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not isinstance(reservation, dict) or reservation.get("state") != "RESERVED":
                raise RuntimeError("reservation is unavailable or already started")
            reservation["state"] = "NETWORK_IN_FLIGHT"
            return {"state": "NETWORK_IN_FLIGHT"}

    def reconcile(self, reservation_id: str, observation_id: str,
                 actual: Dict[str, Any]) -> Dict[str, Any]:
        observed = actual.get("observed_total_tokens") if isinstance(actual, dict) else None
        if observed is not None and (
                type(observed) is not int or observed < 0
                or observed > EXACT_CAPS["per_call_observed_tokens_max"]):
            raise RuntimeError("per-call observed-token cap exceeded")
        usd_cost = actual.get("usd_cost") if isinstance(actual, dict) else None
        if usd_cost is not None:
            if isinstance(usd_cost, bool) or not isinstance(usd_cost, (int, float)) or usd_cost < 0:
                raise RuntimeError("observed usd cost is invalid")
            if usd_cost > 2 * self._per_call_usd_share:
                raise RuntimeError(
                    "per-call usd cost %.6f exceeds 2x the per-call usd ceiling share "
                    "%.6f" % (usd_cost, 2 * self._per_call_usd_share)
                )
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not isinstance(reservation, dict) or reservation.get("state") != "NETWORK_IN_FLIGHT":
                raise RuntimeError("reservation cannot be reconciled")
            aggregate_tokens = self._observed_tokens + (observed or 0)
            if aggregate_tokens > EXACT_CAPS["aggregate_observed_tokens_max_when_telemetry_exists"]:
                raise RuntimeError("aggregate observed-token cap exceeded")
            aggregate_usd = self._observed_usd_cost + (usd_cost or 0.0)
            if aggregate_usd > self.estimated_usd_ceiling:
                raise RuntimeError(
                    "aggregate usd cost %.6f exceeds the pre-execution estimated usd "
                    "ceiling %.6f" % (aggregate_usd, self.estimated_usd_ceiling)
                )
            self._observed_tokens = aggregate_tokens
            self._observed_usd_cost = aggregate_usd
            reservation.update({
                "state": "RECONCILED", "observation_id": observation_id,
                "actual": json.loads(json.dumps(actual)),
            })
            return {"state": "RECONCILED"}

    def totals(self) -> Dict[str, Any]:
        return {
            "calls": self._reserved_calls,
            "seconds": self._reserved_seconds,
            "observed_total_tokens": self._observed_tokens,
            "observed_usd_cost": self._observed_usd_cost,
        }


# ------------------------------------------------------------- runtime price-rate table

def resolve_price_rate_table_for_approval(call_plan: Iterable[List[Any]], *,
                                          rate_lookup: Any, clock: Any) -> Dict[str, Any]:
    """Resolve a fresh, per-model USD rate table for every model in ``call_plan``.

    Blocks approval sealing entirely, pre-execution (Section 4.3), on any
    unresolvable, failed, or stale rate for ANY model actually used in the ten-call
    plan -- never a hardcoded stale table (Section 1.1).
    """
    models = sorted({call[1] for call in call_plan})
    rates: Dict[str, Dict[str, Any]] = {}
    for model in models:
        try:
            rates[model] = resolve_current_usd_rate(model, rate_lookup=rate_lookup, clock=clock)
        except ClaudeAgentAdapterBlockedError as exc:
            raise ClaudePilotBlockedError(
                "runtime price-rate lookup failed pre-execution for model %r: %s"
                % (model, exc)
            ) from exc
    max_tokens_per_call = EXACT_CAPS["per_call_observed_tokens_max"]
    per_model_share_counts: Dict[str, int] = {}
    for call in call_plan:
        per_model_share_counts[call[1]] = per_model_share_counts.get(call[1], 0) + 1
    estimated_usd_ceiling = 0.0
    for model, count in per_model_share_counts.items():
        rate = rates[model]
        # Conservative (never underestimates): treat every reserved token as an
        # output token, the more expensive side of the rate for every model in this
        # matrix, and use the full per-call cap for every call of that model.
        per_call_estimate = (max_tokens_per_call / 1_000_000.0) * max(
            rate["input_usd_per_mtok"], rate["output_usd_per_mtok"],
        )
        estimated_usd_ceiling += per_call_estimate * count
    return {"rates": rates, "estimated_usd_ceiling": estimated_usd_ceiling}


# --------------------------------------------------------------- confirmation ceremony

class ClaudePilotConfirmationBuilder:
    """Seal one immutable approval only from exact current confirmation-request and
    manifest bytes (Section 5 points 4-5). Mirrors
    ``codex_subscription_pilot.PilotConfirmationBuilder.build`` -- unconditionally
    strict regardless of ``test_mode`` (``test_mode`` in the Codex analog only ever
    gates ``build_executable``'s own downstream validation, never ``build`` itself);
    this is deliberately tested through its real, non-fake-SDK-mode code path (Section
    12), covering exactly three states: no confirmation record present blocks sealing;
    a stale/mutated confirmation blocks sealing; an exact, fresh, byte-matching
    confirmation unlocks sealing.
    """

    def __init__(self, *, test_mode: bool = False) -> None:
        self.test_mode = test_mode
        self.spec_sha256 = SPEC_SHA256

    def build(self, *, confirmation_request_path: Any, manifest_path: Any,
              explicit_confirmation_text: str) -> str:
        request = _load_json_object(Path(confirmation_request_path), "confirmation request")
        manifest = _load_json_object(Path(manifest_path), "manifest")
        if manifest.get("schema") != "claude_pace_manifest.v1" or manifest.get(
                "manifest_hash") != manifest_hash(manifest):
            raise ClaudePilotBlockedError("stale or mutated manifest hash")
        run_id = request.get("run_id")
        required_text = "CONFIRM CLAUDE PRODUCT PILOT %s %s" % (
            run_id, manifest["manifest_hash"],
        )
        expected_request = {
            "schema": "confirmation_request.v1",
            "confirmed": False,
            "run_id": run_id,
            "spec_sha256": self.spec_sha256,
            "manifest_hash": manifest["manifest_hash"],
            "call_plan": EXACT_CALL_PLAN,
            "caps": EXACT_CAPS,
            "estimated_usd_ceiling": manifest.get("estimated_usd_ceiling"),
            "promotion_boundary": PROMOTION_BOUNDARY,
            "required_confirmation_text": required_text,
        }
        if request != expected_request:
            raise ClaudePilotBlockedError(
                "confirmation request is stale, mutated, or has invalid caps"
            )
        if explicit_confirmation_text != required_text:
            raise ClaudePilotBlockedError("exact explicit confirmation text is required")
        if manifest.get("call_plan") != EXACT_CALL_PLAN or manifest.get(
                "caps") != EXACT_CAPS or manifest.get(
                    "promotion_boundary") != PROMOTION_BOUNDARY:
            raise ClaudePilotBlockedError("manifest call plan, caps, or boundary changed")
        approval: Dict[str, Any] = {
            "schema": "claude_experiment_approval.v1",
            "execution_mode": "claude_subscription",
            "user_created": True,
            "manifest_hash": manifest["manifest_hash"],
            "estimated_usd_ceiling": manifest.get("estimated_usd_ceiling"),
            "caps": EXACT_CAPS,
            "call_plan": EXACT_CALL_PLAN,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "human_confirmation": {
                "schema": "user_confirmation.v1",
                "confirmed": True,
                "spec_sha256": self.spec_sha256,
                "approval_hash": "",
                "manifest_hash": manifest["manifest_hash"],
                "promotion_boundary": PROMOTION_BOUNDARY,
            },
            "approval_hash": "",
        }
        computed_approval_hash = approval_hash(approval)
        approval["approval_hash"] = computed_approval_hash
        approval["human_confirmation"]["approval_hash"] = computed_approval_hash
        approval_path = Path(manifest_path).parent / "claude_experiment_approval.v1.json"
        _AtomicPreparationWriter().write_json(approval_path, approval)
        return str(approval_path)


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ClaudePilotBlockedError("%s could not be read/parsed" % label) from exc
    if not isinstance(payload, dict):
        raise ClaudePilotBlockedError("%s must be a JSON object" % label)
    return payload


# ------------------------------------------------------------------ required test gate

class ClaudeRequiredTestGateRunner:
    """Execute the exact four required modules named in spec Section 12's own pytest
    invocation and retain byte-bound evidence. Mirrors
    ``codex_subscription_pilot.RequiredTestGateRunner``'s subprocess-receipt discipline,
    scaled down to this pilot's own (shorter, four-module) required gate list.
    """

    MODULE_ORDER = (
        "loop-team/runner/tests/test_claude_agent_adapter.py",
        "loop-team/runner/tests/test_claude_subscription_pilot.py",
        "loop-team/runner/tests/test_experiment_execution_contract.py",
        "loop-team/evals/test_model_routing_evals_contract.py",
    )

    def __init__(self, *, popen_factory: Any = None, test_mode: bool = False,
                 artifact_dir: Any = None) -> None:
        import subprocess
        default_popen = subprocess.Popen
        if popen_factory is not None and popen_factory is not default_popen and not test_mode:
            raise TypeError("test-gate subprocess injection is permitted only in test mode")
        self.popen_factory = popen_factory or default_popen
        self.test_mode = test_mode
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else Path(
            "/private/tmp/claude-product-pilot-test-gate"
        )

    @staticmethod
    def _parse_pytest_summary(stdout: str) -> Optional[Dict[str, int]]:
        import re as _re
        if not isinstance(stdout, str):
            return None
        plain = _re.sub(r"\x1b\[[0-9;]*m", "", stdout)
        outcome_names = {
            "passed": "passed", "failed": "failed", "error": "errors", "errors": "errors",
            "skipped": "skipped", "xfailed": "xfailed", "xpassed": "xpassed",
        }
        for line in reversed(plain.splitlines()):
            matches = _re.findall(
                r"(?<![\w\"'])\b(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)\b",
                line.lower(),
            )
            if not matches or not _re.search(r"\bin\s+\d+(?:\.\d+)?s\b", line.lower()):
                continue
            counts = {name: 0 for name in (
                "passed", "failed", "errors", "skipped", "xfailed", "xpassed",
            )}
            for raw_count, raw_name in matches:
                counts[outcome_names[raw_name]] += int(raw_count)
            counts["collected"] = sum(counts.values())
            return counts
        return None

    def _run_command(self, command: List[str], *, index: int) -> Dict[str, Any]:
        import subprocess
        started_at = time.time_ns()
        process = self.popen_factory(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        stdout, stderr = process.communicate()
        finished_at = max(time.time_ns(), started_at + 1)
        stdout = stdout if isinstance(stdout, str) else ""
        summary = self._parse_pytest_summary(stdout)
        return {
            "index": index, "command": command,
            "exit_status": getattr(process, "returncode", None),
            "summary": summary, "started_at": started_at, "finished_at": finished_at,
        }

    def run(self) -> Dict[str, Any]:
        modules = list(self.MODULE_ORDER)
        combined_command = ["python3", "-m", "pytest", *modules, "-q"]
        commands = [
            combined_command,
            *[["python3", "-m", "pytest", module, "-q"] for module in modules],
        ]
        receipts = [self._run_command(command, index=index)
                   for index, command in enumerate(commands)]
        combined = receipts[0]
        combined_summary = combined.get("summary")
        module_outcomes = {}
        for module, receipt in zip(modules, receipts[1:]):
            summary = receipt.get("summary")
            module_outcomes[module] = {
                "status": "passed" if (
                    receipt.get("exit_status") == 0 and isinstance(summary, dict)
                    and summary.get("passed", 0) > 0 and summary.get("failed") == 0
                    and summary.get("errors") == 0
                ) else "failed",
                "passed": summary.get("passed", 0) if isinstance(summary, dict) else 0,
                "failed": summary.get("failed", 0) if isinstance(summary, dict) else 0,
                "errors": summary.get("errors", 0) if isinstance(summary, dict) else 0,
            }
        clean = (
            combined.get("exit_status") == 0
            and isinstance(combined_summary, dict)
            and combined_summary.get("passed", 0) > 0
            and combined_summary.get("failed") == 0
            and combined_summary.get("errors") == 0
            and all(outcome["status"] == "passed" for outcome in module_outcomes.values())
        )
        return {
            "schema": "claude_required_test_gate.v1",
            "all_required_tests_passed": clean,
            "executed_test_modules": modules,
            "module_outcomes": module_outcomes,
            "passed_test_count": combined_summary.get("passed", 0) if isinstance(
                combined_summary, dict) else 0,
            "collected_test_count": combined_summary.get("collected", 0) if isinstance(
                combined_summary, dict) else 0,
        }


# ---------------------------------------------------------------------- side-by-side

def _side_by_side_comparability_appendix() -> Dict[str, Any]:
    """Section 13's mandatory appendix: cross-references the Codex pilot's own report
    by exact path (never fabricating a concrete run-id this module cannot know), and
    states -- rather than omits or fabricates -- that the Codex pilot has no USD
    authority at all (its own spec, Section 2.2: usd_accounting is
    FORBIDDEN_CODEX_SUBSCRIPTION_PILOT).
    """
    return {
        "schema": "claude_vs_codex_comparability_appendix.v1",
        "codex_report_path_template": (
            "loop-team/runs/2026-07-16_model-routing-pace/artifacts/"
            "codex_product_pilot/<run-id>/report/pilot-report.json"
        ),
        "codex_usd_authority": "FORBIDDEN_CODEX_SUBSCRIPTION_PILOT",
        "note": (
            "the Codex pilot has no USD authority at all -- this appendix states that "
            "explicitly rather than omitting the column or fabricating a number"
        ),
        "per_case": {
            case_id: {
                "claude": {"quality_verdict": None, "observed_tokens": None, "latency_ms": None},
                "codex": {"quality_verdict": None, "observed_tokens": None, "latency_ms": None},
            }
            for case_id in sorted(CASE_BASELINE_FACTS)
        },
    }


def _pilot_report_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Claude Subscription Product Pilot -- Report", "",
        "- pace_status: `%s`" % report["pace_status"],
        "- cases: `%s`" % report.get("cases"),
        "- paired_observations: `%s`" % report.get("paired_observations"),
        "- min_discordant: `%s`" % report.get("min_discordant"),
        "- promotion eligible: `false`", "",
        "## Statistical power", "",
        N3_STATISTICAL_POWER_SENTENCE, "",
        "## Side-by-side comparability appendix (Claude vs Codex)", "",
        "Codex pilot report path template: `%s`" % report[
            "side_by_side_comparability_appendix"]["codex_report_path_template"],
        "Codex USD authority: `%s`" % report[
            "side_by_side_comparability_appendix"]["codex_usd_authority"],
        "",
        "## Boundary", "",
        "This report never calls a selected quarantined patch promoted, deployed, "
        "ready, or verified beyond its isolated oracle evidence.",
        "",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- controller

class ClaudeSubscriptionPilot:
    """Top-level controller for the ten-call Claude subscription pilot (Section 4.1)."""

    def __init__(self, *, adapter_factory: Any, test_mode: bool = False,
                 post_arm_verifier: Any = None) -> None:
        if not callable(adapter_factory):
            raise TypeError("adapter_factory must be callable")
        if post_arm_verifier is not None and not callable(
                getattr(post_arm_verifier, "verify_after_coder", None)):
            raise TypeError("post_arm_verifier must expose verify_after_coder")
        self.adapter_factory = adapter_factory
        self.test_mode = test_mode
        self.post_arm_verifier = post_arm_verifier

    def run(self, *, approval: Dict[str, Any], manifest: Dict[str, Any],
            required_test_receipt: Dict[str, Any], frozen_packets: Iterable[Dict[str, Any]],
            dry_run: bool, report_dir: Any = None) -> Dict[str, Any]:
        packets = list(frozen_packets)
        report_root = Path(report_dir) if report_dir is not None else None
        execution_packets = self._validate(
            approval, manifest, required_test_receipt, packets, dry_run=dry_run,
        )
        report: Dict[str, Any] = {
            "pace_status": PROMOTION_BOUNDARY,
            "promotion_eligible": False,
            "cases": 3,
            "paired_observations": 3,
            "min_discordant": 16,
            "routing_recommendation": None,
            "integration_applied": False,
            "side_by_side_comparability_appendix": _side_by_side_comparability_appendix(),
        }
        if dry_run:
            return report

        adapter = self.adapter_factory()
        results: List[Any] = []
        post_arm_receipts: List[Dict[str, Any]] = []
        planner_handoffs: Dict[str, Dict[str, Any]] = {}
        for sealed_packet in execution_packets:
            packet = sealed_packet
            task = packet.get("task_identity", {})
            role = task.get("role")
            case_id = task.get("case_id")
            if role in ("incumbent_coder", "challenger_coder"):
                if case_id not in planner_handoffs:
                    raise ClaudePilotBlockedError(
                        "every planner output must PLAN_PASS before its case's coders start"
                    )
                packet = self._derive_coder_packet(sealed_packet, planner_handoffs[case_id])
            result = adapter.execute(packet)
            if not isinstance(result, dict) or result.get("promotion_eligible") is not False:
                raise ClaudePilotBlockedError(
                    "adapter result is missing or attempted to promote pilot evidence"
                )
            if role == "planner":
                planner_handoffs[case_id] = self._parse_planner_output(packet, result)
            if role in ("incumbent_coder", "challenger_coder"):
                if self.post_arm_verifier is None:
                    if not self.test_mode:
                        raise ClaudePilotBlockedError(
                            "coder result lacks a mandatory post-arm verifier"
                        )
                else:
                    post_arm = self.post_arm_verifier.verify_after_coder(
                        packet=packet, result=result,
                    )
                    if not isinstance(post_arm, dict) or post_arm.get(
                            "schema") != "controller_post_arm_receipt.v1" or post_arm.get(
                                "status") != "PASS" or post_arm.get(
                                    "signed") is not True or post_arm.get(
                                        "promotion_eligible") is not False:
                        raise ClaudePilotBlockedError(
                            "coder result post-arm verification receipt is invalid"
                        )
                    post_arm_receipts.append(post_arm)
            results.append(result)

        if len(results) != EXACT_CAPS["combined_calls"]:
            raise ClaudePilotBlockedError("the controller must execute exactly ten calls")
        report["calls_started"] = len(results)
        report["post_arm_verification_receipts"] = post_arm_receipts
        if report_root is not None:
            report.update(self._write_report(report_root, report, post_arm_receipts))
        return report

    @staticmethod
    def _parse_planner_output(packet: Dict[str, Any], result: Any) -> Dict[str, Any]:
        raw = result.get("planner_output") if isinstance(result, dict) else None
        claimed_hash = result.get("planner_output_sha256") if isinstance(result, dict) else None
        if not isinstance(raw, str) or not raw.endswith("\n"):
            raise ClaudePilotBlockedError("planner output is missing or not canonical JSON")
        payload_bytes = raw.encode("utf-8")
        digest = hashlib.sha256(payload_bytes).hexdigest()
        if claimed_hash is not None and claimed_hash != digest:
            raise ClaudePilotBlockedError("planner output hash differs from returned bytes")
        try:
            plan = json.loads(raw)
        except ValueError as exc:
            raise ClaudePilotBlockedError("planner output could not parse as JSON") from exc
        task = packet.get("task_identity", {})
        valid = (
            isinstance(plan, dict)
            and plan.get("schema") == "product_planner_output.v1"
            and plan.get("status") == "PLAN_PASS"
            and plan.get("case_id") == task.get("case_id")
            and isinstance(plan.get("allowed_paths"), list) and bool(plan.get("allowed_paths"))
            and isinstance(plan.get("steps"), list) and bool(plan.get("steps"))
            and isinstance(plan.get("checks"), list) and bool(plan.get("checks"))
        )
        if not valid:
            raise ClaudePilotBlockedError("planner output failed deterministic local plan-check")
        return {
            "schema": "planner_handoff.v1", "status": "PLAN_PASS",
            "case_id": plan["case_id"], "plan": plan,
        }

    @staticmethod
    def _derive_coder_packet(packet: Dict[str, Any], handoff: Dict[str, Any]) -> Dict[str, Any]:
        if handoff.get("status") != "PLAN_PASS" or handoff.get(
                "case_id") != packet.get("task_identity", {}).get("case_id"):
            raise ClaudePilotBlockedError("coder packet cannot be derived without its valid planner")
        derived = json.loads(json.dumps(packet))
        derived["planner_handoff"] = handoff
        return derived

    def _validate(self, approval: Dict[str, Any], manifest: Dict[str, Any],
                 tests: Dict[str, Any], packets: List[Dict[str, Any]], *,
                 dry_run: bool) -> List[Dict[str, Any]]:
        if not isinstance(tests, dict) or tests.get("all_required_tests_passed") is not True:
            raise ClaudePilotBlockedError("required fake-SDK test receipt is missing or unclean")
        if not isinstance(approval, dict) or approval.get(
                "schema") != "claude_experiment_approval.v1" or approval.get(
                    "execution_mode") != "claude_subscription" or approval.get(
                        "user_created") is not True:
            raise ClaudePilotBlockedError("sealed approval is required")
        if not isinstance(manifest, dict) or manifest.get("schema") != "claude_pace_manifest.v1":
            raise ClaudePilotBlockedError("sealed manifest is required")
        if manifest.get("call_plan") != EXACT_CALL_PLAN or approval.get(
                "call_plan") != EXACT_CALL_PLAN:
            raise ClaudePilotBlockedError("frozen call plan is not the exact ten-call plan")
        if manifest.get("caps") != EXACT_CAPS or approval.get("caps") != EXACT_CAPS:
            raise ClaudePilotBlockedError("frozen combined caps do not match")
        if manifest.get("promotion_boundary") != PROMOTION_BOUNDARY or approval.get(
                "promotion_boundary") != PROMOTION_BOUNDARY:
            raise ClaudePilotBlockedError("pilot promotion boundary is absent")
        if len(packets) != EXACT_CAPS["combined_calls"]:
            raise ClaudePilotBlockedError("exactly ten frozen packets are required")
        smoke_packet = manifest.get("smoke_packet")
        if not isinstance(smoke_packet, dict) or smoke_packet.get(
                "packet_hash") != packets[0].get("packet_hash"):
            raise ClaudePilotBlockedError("manifest smoke packet does not match the first frozen packet")
        for ordinal, (packet, call) in enumerate(zip(packets, EXACT_CALL_PLAN)):
            self._validate_packet(packet, ordinal, call)
        if not dry_run and not self.test_mode:
            confirmation = approval.get("human_confirmation")
            expected_confirmation = {
                "schema": "user_confirmation.v1", "confirmed": True,
                "spec_sha256": SPEC_SHA256, "approval_hash": approval.get("approval_hash"),
                "manifest_hash": manifest.get("manifest_hash"),
                "promotion_boundary": PROMOTION_BOUNDARY,
            }
            if confirmation != expected_confirmation:
                raise ClaudePilotBlockedError("exact immutable human confirmation is required")
        return packets

    @staticmethod
    def _validate_packet(packet: Any, ordinal: int, call: List[Any]) -> None:
        if not isinstance(packet, dict):
            raise ClaudePilotBlockedError("frozen packet is missing")
        task = packet.get("task_identity")
        expected_role = call[0]
        if not isinstance(task, dict) or task.get("ordinal") != ordinal or task.get(
                "role") != expected_role:
            raise ClaudePilotBlockedError("frozen packet task order or identity changed")
        if packet.get("requested_model") != call[1] or packet.get("requested_effort") != call[2]:
            raise ClaudePilotBlockedError("frozen packet model or effort changed")
        for field_name in ("packet_hash", "reverified_packet_hash", "clone_tree_hash",
                          "reverified_clone_tree_hash"):
            if not isinstance(packet.get(field_name), str) or not packet[field_name]:
                raise ClaudePilotBlockedError("frozen packet is missing a required hash field")
        if packet["packet_hash"] != packet_hash(packet) or packet[
                "reverified_packet_hash"] != packet["packet_hash"]:
            raise ClaudePilotBlockedError("frozen packet hash does not bind packet bytes")
        if packet["clone_tree_hash"] != packet["reverified_clone_tree_hash"]:
            raise ClaudePilotBlockedError("clone tree changed after packet sealing")

    @staticmethod
    def _write_report(root: Path, report: Dict[str, Any],
                      post_arm_receipts: List[Dict[str, Any]]) -> Dict[str, Any]:
        report_dir = root / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        json_path = report_dir / "pilot-report.json"
        json_path.write_text(
            json.dumps(report, sort_keys=True, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        markdown_path = report_dir / "pilot-report.md"
        markdown_path.write_text(_pilot_report_markdown(report), encoding="utf-8")
        return {
            "report_json_path": str(json_path),
            "report_markdown_path": str(markdown_path),
        }
