"""Fail-closed, injectable dispatch adapter for the Claude Agent SDK product pilot.

Spec: loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md

This module is the Claude-side sibling of ``codex_exec_adapter.py`` -- same
injectable-collaborator discipline (every process/tool-scope/ledger/session/transcript
collaborator is a constructor argument, never a hidden global), same fail-closed
philosophy (a policy violation raises a single blocked-error type carrying a redacted
evidence surface), same canonical-hash/byte-mismatch rigor -- adapted to the Claude
Agent SDK's Python-native ``query(prompt, options) -> events`` call shape instead of
Codex CLI argv/JSONL.

Two collaborators in this module deliberately do NOT behave like a normal "fake vs
real" seam:

* ``ClaudeAgentCompatibilityPreflight``'s ``query_fn`` default (used only when the
  caller does not inject one, i.e. real non-test use) is a **local, offline
  construction prober** -- it builds the real ``claude_agent_sdk.ClaudeAgentOptions``
  dataclass for each probed (model, tool_scope) combination and never calls
  ``claude_agent_sdk.query()`` at all. This is a deliberate design consequence of the
  spec's Section 6.1 rewrite (plan-check round 4): the preflight must make "zero real
  Claude Agent SDK dispatches and zero cost-incurring calls of any kind" -- so, unlike
  ``ClaudeAgentAdapter.query_fn`` (whose production default really does dispatch),
  this preflight's production default is intentionally inert. Whether the
  tool-restriction mechanism is actually *honored*, and whether a parseable
  transcript/session log is produced, cannot be proven this way -- the spec explicitly
  defers both to the adapter smoke (the first real, ledgered dispatch), which this
  module's ``ClaudeAgentAdapter.execute()`` handles like any other dispatch.
* The Fable-5 data-retention precheck (Section 4.3) is *not* something the inert
  preflight can observe either (no free/offline signal exists for an org's retention
  configuration) -- its real signal is a live 400 ``invalid_request_error`` on an
  actual Fable-5 dispatch. ``classify_dispatch_error()`` below is the single place that
  turns that signature into a distinctly-coded ``PRECHECK_FAILED`` (never a generic
  call failure, never a claim about Fable 5's own capability); the preflight receipt
  only documents that this is pending, deferred to whichever real dispatch first uses
  ``claude-fable-5`` (the P3 challenger call, per the frozen run contract).

Fake-SDK injection is explicit for tests (Section 11 point 1: "production imports the
real claude-agent-sdk package"); this module never imports ``claude_agent_sdk`` at
module scope, only lazily inside the production-default callables that a real,
non-test-mode caller would actually reach.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from . import experiment_execution as _execution
from .codex_subscription_pilot import _preparation_tree_entries


# --------------------------------------------------------------------- module constants

ACCEPTED_MODELS = (
    "claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5", "claude-fable-5",
)
ACCEPTED_TOOL_SCOPES = ("read_only", "workspace_write")
ACCEPTED_PROMPTED_EFFORTS = frozenset({"low", "high"})
ACCEPTED_EFFORT_CONTROLS = ("api_enforced", "prompted_proxy")
PROMOTION_BOUNDARY = "PILOT_ONLY/NO_ROUTING_PROMOTION"

# A "minimal environment" allowlist independent of packet self-consistency: a packet
# can be internally hash-consistent while still smuggling an unexpected/leaked
# variable into what actually reaches the dispatch, so this is enforced regardless of
# whether the packet's own hash was recomputed to match.
_ALLOWED_ENVIRONMENT_KEYS = frozenset({"LANG", "LC_ALL", "PATH", "TZ", "HOME"})

_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")

_DEFAULT_REDACTION_PATTERNS = (
    r"(?i)authorization\s*:\s*(?:bearer\s+)?[^\s,;\"']+",
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;\"']+",
    r"\bsk-[A-Za-z0-9._-]+\b",
)


# --------------------------------------------------------------------- canonical helpers

def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_packet_hash(packet: Dict[str, Any]) -> str:
    """Hash packet bytes while excluding only circular packet-hash fields."""
    payload = json.loads(json.dumps(packet))
    payload.pop("packet_hash", None)
    payload.pop("reverified_packet_hash", None)
    authority = payload.get("immutable_authority")
    if isinstance(authority, dict):
        authority.pop("packet_hash", None)
    return canonical_hash(payload)


def deterministic_tree_hash(entries: Any) -> str:
    if not isinstance(entries, list) or not entries:
        raise ValueError("non-empty deterministic tree entries are required")
    return canonical_hash(entries)


# ------------------------------------------------------------------------- blocked error

class ClaudeAgentAdapterBlockedError(RuntimeError):
    """A Claude Agent SDK attempt was blocked; only a redacted observation is retained."""

    code = "PILOT_ABORTED"

    def __init__(self, message: str, observation: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.observation = observation if observation is not None else {}


def _redact(value: Any, patterns: Iterable[Any]) -> Any:
    if isinstance(value, str):
        for pattern in patterns:
            value = pattern.sub("[REDACTED]", value)
        return value
    if isinstance(value, list):
        return [_redact(item, patterns) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, patterns) for item in value]
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]" if re.search(
                    r"(?i)(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?"
                    r"token|auth[_-]?token|secret)",
                    str(key),
                ) else _redact(item, patterns)
            )
            for key, item in value.items()
        }
    return value


# ------------------------------------------------------------------ Fable-5 error signal

def classify_dispatch_error(model: str, exc: BaseException) -> Dict[str, Any]:
    """Classify one dispatch-time exception raised by ``query_fn``.

    The one condition requiring distinct, non-generic classification is Section 4.3's
    Fable-5 data-retention precheck: a live ``400 invalid_request_error`` on a
    ``claude-fable-5`` call is the org's data-retention configuration not meeting
    Fable 5's 30-day minimum -- this can only ever be observed on a real dispatch
    (never inertly in the preflight, never generically as "the call failed"), and it
    must never be phrased as a claim about Fable 5's own capability. Every other
    exception -- including any other status/error-type combination on Fable 5 itself
    -- is a generic call failure.
    """
    status_code = getattr(exc, "status_code", None)
    error_type = getattr(exc, "error_type", None) or getattr(exc, "type", None)
    if model == "claude-fable-5" and status_code == 400 and error_type == "invalid_request_error":
        return {
            "failure_code": "FABLE5_DATA_RETENTION_PRECHECK_FAILED",
            "category": "PRECHECK_FAILED",
            "data_retention_ok_fable5": False,
            "detail": (
                "org data-retention configuration does not meet Fable 5's 30-day "
                "minimum, observed at this real dispatch per Section 4.3 -- this is a "
                "configuration precheck outcome, not a claim about the model's own "
                "capability"
            ),
        }
    return {
        "failure_code": "GENERIC_DISPATCH_FAILURE",
        "category": "CALL_FAILED",
        "data_retention_ok_fable5": None,
        "detail": "%s: %s" % (type(exc).__name__, exc),
    }


# ------------------------------------------------------------------------- USD rate lookup

def resolve_current_usd_rate(model: str, *, rate_lookup: Callable[[str], Any],
                              clock: Callable[[], float],
                              max_age_seconds: float = 86400) -> Dict[str, Any]:
    """Resolve the current published per-token USD rate for ``model``.

    Never returns a hardcoded/stale rate silently (Section 1.1, Section 4.3): an
    unresolvable, failed, or stale lookup raises ``ClaudeAgentAdapterBlockedError``.
    """
    try:
        rate = rate_lookup(model)
    except Exception as exc:
        raise ClaudeAgentAdapterBlockedError(
            "usd per-token rate lookup failed for model %r: %s" % (model, exc),
            {"model": model, "reason": "rate_lookup_raised"},
        ) from exc
    if not isinstance(rate, dict) or not isinstance(
            rate.get("input_usd_per_mtok"), (int, float)) or not isinstance(
                rate.get("output_usd_per_mtok"), (int, float)):
        raise ClaudeAgentAdapterBlockedError(
            "usd per-token rate is unresolvable for model %r" % model,
            {"model": model, "reason": "rate_unresolvable"},
        )
    checked_at = rate.get("checked_at")
    if not isinstance(checked_at, (int, float)) or isinstance(checked_at, bool):
        raise ClaudeAgentAdapterBlockedError(
            "usd per-token rate has no usable freshness timestamp for model %r" % model,
            {"model": model, "reason": "rate_missing_checked_at"},
        )
    now = clock()
    age = now - checked_at
    if age < 0 or age > max_age_seconds:
        raise ClaudeAgentAdapterBlockedError(
            "usd per-token rate is stale (not fresh) for model %r: age=%.1fs exceeds "
            "max_age_seconds=%.1fs" % (model, age, max_age_seconds),
            {"model": model, "reason": "rate_stale", "age_seconds": age},
        )
    return {
        "model": model,
        "input_usd_per_mtok": float(rate["input_usd_per_mtok"]),
        "output_usd_per_mtok": float(rate["output_usd_per_mtok"]),
        "checked_at": checked_at,
        "source": rate.get("source"),
    }


# --------------------------------------------------------------------------- dataclasses

@dataclass(frozen=True)
class ClaudeAgentDispatchRequest:
    prompt: str
    clone_path: str
    artifact_dir: str
    requested_model: str
    tool_scope: str
    effort_control: str
    requested_effort: Optional[str]
    prompted_effort: Optional[str]
    timeout_seconds: int
    approval_hash: str
    manifest_hash: str
    protected_roots: List[str]
    frozen_packet: Dict[str, Any]


@dataclass(frozen=True)
class ClaudeAgentDispatchResult:
    provider_result: Any
    usage_v1: Dict[str, Any]
    raw_observation: Dict[str, Any]
    cleanup_receipt: Dict[str, Any]
    final_output: str
    report_surface: Dict[str, Any]


# ------------------------------------------------------------- compatibility preflight

class ClaudeAgentCompatibilityPreflight:
    """Inert, zero-real-dispatch compatibility check (spec Section 6.1, redesigned).

    Proves, entirely before any real dispatch and at zero cost: the installed SDK
    package/version (item 1); local, offline call-shape acceptance for all four
    requested models crossed with both tool-scope configurations (item 2a); a free,
    non-generation Models-API identity lookup per requested model (item 2b); whether a
    native effort/thinking option exists (item 3); the tool-restriction option's
    existence/call-shape (item 4, existence/shape half only). It explicitly does NOT
    (and per the spec cannot) prove item 4's honored-ness half, item 5 (whether a
    parseable transcript/session log is actually produced), or item 6 (Fable-5 data
    retention) -- all three require observing a live agent turn and are deferred to
    real, already-ledgered dispatches (item 4-honored/5 to the smoke; item 6 to the
    real Fable-5 dispatch), never resolved here.
    """

    MATRIX = tuple(
        (model, scope) for model in ACCEPTED_MODELS for scope in ACCEPTED_TOOL_SCOPES
    )

    def __init__(self, *, query_fn: Optional[Callable[..., Any]] = None,
                 rate_lookup: Optional[Callable[[str], Any]] = None,
                 clock: Optional[Callable[[], float]] = None,
                 test_mode: bool = False, artifact_dir: Any = None) -> None:
        self._probe_fn = query_fn if query_fn is not None else self._default_local_prober
        self._injected_probe = query_fn is not None
        self.rate_lookup = rate_lookup
        self.clock = clock if clock is not None else time.time
        self.test_mode = test_mode
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else None

    @staticmethod
    def _default_local_prober(prompt: str, options: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Zero-network production default: constructs the real
        ``claude_agent_sdk.ClaudeAgentOptions`` dataclass locally to prove call-shape
        acceptance. This never calls ``claude_agent_sdk.query()`` -- it is not a
        dispatch. Lazily imported so module import never requires the real package
        (Section 11 point 1)."""
        from claude_agent_sdk import ClaudeAgentOptions  # local: no import-time dependency

        kwargs: Dict[str, Any] = {"model": options["model"], "cwd": options["cwd"]}
        if options.get("tool_scope") == "read_only":
            kwargs["allowed_tools"] = ["Read", "Grep", "Glob"]
        elif options.get("tool_scope") == "workspace_write":
            kwargs["allowed_tools"] = ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
        if "effort" in options:
            kwargs["effort"] = options["effort"]
        ClaudeAgentOptions(**kwargs)  # raises if a field/kwarg is unsupported
        return [{"type": "result", "configured_model": options.get("model"),
                 "final_output": "PROBE_OK"}]

    def _probe_sdk_package_identity(self) -> Dict[str, Any]:
        if self.test_mode and not self._injected_probe:
            # Genuinely production-default behaviour is only reachable outside tests;
            # a bare test_mode run with no injected probe still should not require the
            # real package to be installed just to exercise this identity check.
            try:
                import claude_agent_sdk  # noqa: F401
            except ImportError:
                return {"name": "claude-agent-sdk", "version": "test-mode", "proven": True}
            return {
                "name": "claude-agent-sdk",
                "version": getattr(claude_agent_sdk, "__version__", "unknown"),
                "proven": True,
            }
        if self._injected_probe:
            return {"name": "claude-agent-sdk", "version": "test-mode-fake", "proven": True}
        try:
            import claude_agent_sdk
        except ImportError as exc:
            return {
                "name": "claude-agent-sdk", "version": None, "proven": False,
                "error": "claude-agent-sdk is not installed: %s" % exc,
            }
        return {
            "name": "claude-agent-sdk",
            "version": getattr(claude_agent_sdk, "__version__", "unknown"),
            "proven": True,
        }

    def _probe_effort_control(self, probe_cwd: str) -> tuple:
        representative_model = ACCEPTED_MODELS[0]
        options = {
            "model": representative_model, "cwd": probe_cwd,
            "tool_scope": "read_only", "effort": "high",
        }
        try:
            list(self._probe_fn("PROBE: confirm effort field acceptance.", options))
        except TypeError:
            return "prompted_proxy", {"proven": True}
        except Exception as exc:
            return "prompted_proxy", {"proven": False, "error": str(exc)}
        return "api_enforced", {"proven": True}

    def _probe_combo(self, model: str, tool_scope: str, *, cwd: str) -> Dict[str, Any]:
        options = {"model": model, "cwd": cwd, "tool_scope": tool_scope}
        try:
            events = list(self._probe_fn(
                "PROBE: confirm local call-shape acceptance.", options,
            ))
        except Exception as exc:
            return {
                "model": model, "tool_scope": tool_scope, "call_shape_accepted": False,
                "error": "%s: %s" % (type(exc).__name__, exc),
            }
        return {
            "model": model, "tool_scope": tool_scope, "call_shape_accepted": True,
            "sample_event_count": len(events),
        }

    def _probe_model_identity(self, model: str) -> Dict[str, Any]:
        """Free, non-generation Models-API identity lookup (item 2b). Real network,
        real package (``anthropic``, not ``claude_agent_sdk``); never billed, never
        reserved against the pilot ledger. Bypassed under test_mode since no fake-SDK
        test in this suite injects a dedicated collaborator for it -- exercising it for
        real is a production/live-session-only concern (Section 6.1 item 2b)."""
        if self.test_mode:
            return {"model": model, "proven": True, "source": "test_mode_bypassed"}
        try:
            import anthropic
        except ImportError as exc:
            return {"model": model, "proven": False, "error": "anthropic package missing: %s" % exc}
        try:
            # max_retries=0: this pilot never silently spins on a transient error for
            # a free metadata lookup (repo-wide operational invariant, verify_build.py).
            client = anthropic.Anthropic(max_retries=0)
            info = client.models.retrieve(model)
        except Exception as exc:  # AuthenticationError, NotFoundError, etc.
            return {"model": model, "proven": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        return {"model": model, "proven": True, "resolved_id": getattr(info, "id", None)}

    def run(self, *, cwd: Optional[str] = None) -> Dict[str, Any]:
        probe_cwd = cwd or "/private/tmp"
        failure_codes: List[str] = []

        sdk_package = self._probe_sdk_package_identity()
        if not sdk_package["proven"]:
            failure_codes.append("SDK_PACKAGE_NOT_INSTALLED")

        effort_control, effort_finding = self._probe_effort_control(probe_cwd)
        if not effort_finding.get("proven", True):
            failure_codes.append("EFFORT_PROBE_UNRESOLVED")

        checks: List[Dict[str, Any]] = []
        tool_scope_ok = True
        for model, tool_scope in self.MATRIX:
            check = self._probe_combo(model, tool_scope, cwd=probe_cwd)
            checks.append(check)
            if not check["call_shape_accepted"]:
                tool_scope_ok = False
                failure_codes.append(
                    "CALL_SHAPE_REJECTED:%s:%s" % (model, tool_scope)
                )

        model_identity_checks = [self._probe_model_identity(model) for model in ACCEPTED_MODELS]
        model_identity_ok = all(check["proven"] for check in model_identity_checks)
        if not model_identity_ok:
            failure_codes.append("MODEL_IDENTITY_UNRESOLVED")

        status = "PASS" if (
            sdk_package["proven"] and tool_scope_ok
            and effort_finding.get("proven", True) and model_identity_ok
        ) else "PRECHECK_FAILED"

        receipt = {
            "schema": "claude-sdk-compatibility.v1",
            "status": status,
            "sdk_package": sdk_package,
            "checks": checks,
            "model_identity_checks": model_identity_checks,
            "effort_control": effort_control,
            "tool_scope_mechanism_confirmed": tool_scope_ok,
            # Deferred findings -- see module docstring. Neither is resolvable inertly;
            # both are settled once, by the adapter smoke (the first real, ledgered
            # dispatch), never re-checked per subsequent dispatch.
            "transcript_writes_parseable": None,
            "tool_scope_honored": None,
            # Fable-5 data retention: no free/offline signal exists for this at all;
            # deferred to the real P3 challenger (Fable-5) dispatch. See
            # classify_dispatch_error() for where the live 400 signature is actually
            # caught, at dispatch time.
            "data_retention_ok_fable5": None,
            "data_retention_note": (
                "cannot be verified inertly; resolved only by observing the real "
                "claude-fable-5 dispatch (Section 4.3); a 400 invalid_request_error "
                "there is PRECHECK_FAILED via classify_dispatch_error(), never a "
                "generic call failure"
            ),
            "failure_code": "; ".join(failure_codes) if failure_codes else None,
        }
        if self.artifact_dir is not None:
            self._persist_receipt(receipt)
        return receipt

    def _persist_receipt(self, receipt: Dict[str, Any]) -> None:
        try:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            path = self.artifact_dir / "claude-sdk-compatibility.json"
            path.write_text(
                json.dumps(receipt, sort_keys=True, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
        except OSError:
            # Persisting the receipt is a convenience for artifact-layout compliance
            # (Section 10); a filesystem failure here must never be mistaken for a
            # compatibility failure of the checks themselves.
            pass


# --------------------------------------------------------------------------- the adapter

class ClaudeAgentAdapter:
    """Execute one frozen Claude Agent SDK dispatch request (spec Section 6.2)."""

    def __init__(self, *, query_fn: Optional[Callable[..., Any]] = None,
                 ledger: Any, tool_scope_prover: Any, session_auditor: Any = None,
                 transcript_reader: Optional[Callable[[str], Any]] = None,
                 rate_lookup: Optional[Callable[[str], Any]] = None,
                 clock: Optional[Callable[[], float]] = None,
                 redaction_patterns: Optional[Iterable[str]] = None,
                 test_mode: bool = False) -> None:
        self.query_fn = query_fn if query_fn is not None else self._default_production_query_fn
        self.ledger = ledger
        self.tool_scope_prover = tool_scope_prover
        self.session_auditor = session_auditor or _DefaultSessionAuditor()
        self.transcript_reader = transcript_reader
        self.rate_lookup = rate_lookup
        self.clock = clock if clock is not None else time.time
        self.test_mode = test_mode
        self.redaction_patterns = [
            re.compile(pattern)
            for pattern in (*_DEFAULT_REDACTION_PATTERNS, *(redaction_patterns or ()))
        ]

    @staticmethod
    def _default_production_query_fn(prompt: str, options: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Real production dispatch: the real Claude Agent SDK, called directly (never
        a shell string / subprocess -- this is a direct Python SDK call). Lazily
        imported so module import never requires the real package installed (Section
        11 point 1); only a genuine non-test-mode dispatch reaches this function."""
        import asyncio

        from claude_agent_sdk import ClaudeAgentOptions, query

        sdk_kwargs: Dict[str, Any] = {"model": options["model"], "cwd": options["cwd"]}
        if options.get("tool_scope") == "read_only":
            sdk_kwargs["allowed_tools"] = ["Read", "Grep", "Glob"]
        elif options.get("tool_scope") == "workspace_write":
            sdk_kwargs["allowed_tools"] = ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
        if "effort" in options:
            sdk_kwargs["effort"] = options["effort"]
        if options.get("environment"):
            sdk_kwargs["env"] = dict(options["environment"])
        sdk_options = ClaudeAgentOptions(**sdk_kwargs)

        async def _run() -> List[Any]:
            collected: List[Any] = []
            async for message in query(prompt=prompt, options=sdk_options):
                collected.append(message)
            return collected

        return asyncio.run(_run())

    def _redact(self, value: Any) -> Any:
        return _redact(value, self.redaction_patterns)

    def _block(self, message: str, observation: Dict[str, Any]) -> None:
        raise ClaudeAgentAdapterBlockedError(message, self._redact(observation))

    # ----------------------------------------------------------------- static validation

    @staticmethod
    def _is_canonical_absolute_path(path: Any) -> bool:
        if not isinstance(path, str) or not path or not path.startswith("/"):
            return False
        return ".." not in Path(path).parts

    @staticmethod
    def _within(path: Any, roots: Iterable[str]) -> bool:
        if not isinstance(path, str):
            return False
        return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)

    def _real_filesystem_clone_tree_hash(self, clone_path: str,
                                         observation: Dict[str, Any]) -> str:
        """Real, on-disk re-hash of the active clone (production only: ``test_mode is
        False``).

        Mirrors ``codex_exec_adapter.py``'s own ``test_mode``-gated
        ``_resolve_tree_hash``/``_canonical_tree_hash`` pattern (spec Sections 6.2/8,
        AC5): this is the one check that actually walks real bytes on disk at
        ``request.clone_path`` (a real ``Path(root).rglob("*")`` walk), rather than
        merely confirming the packet's own in-memory ``clone_tree_entries`` are
        self-consistent with its own ``clone_tree_hash`` -- the weaker, wrong-entity
        property the pre-existing checks above this method's call site already prove.
        Reuses ``_preparation_tree_entries`` verbatim, imported directly from
        ``codex_subscription_pilot.py`` per the spec's own explicit "reuse verbatim"
        instruction; this method never reimplements the entry-gathering logic itself,
        only applies this module's own existing canonical hashing helper
        (``deterministic_tree_hash``) to the entries it returns.
        """
        try:
            entries = _preparation_tree_entries(clone_path)
        except Exception as exc:
            self._block(
                "real on-disk clone tree bytes are unavailable for re-hash: %s" % exc,
                observation,
            )
            raise  # unreachable, _block always raises
        return deterministic_tree_hash(entries)

    def _validate_request(self, request: ClaudeAgentDispatchRequest,
                          observation: Dict[str, Any]) -> Dict[str, Any]:
        packet = request.frozen_packet
        if not isinstance(packet, dict):
            self._block("frozen packet is missing", observation)
        if request.requested_model not in ACCEPTED_MODELS:
            self._block("requested model is outside the accepted model set", observation)
        if request.tool_scope not in ACCEPTED_TOOL_SCOPES:
            self._block("requested tool scope is outside the accepted set", observation)
        if request.effort_control not in ACCEPTED_EFFORT_CONTROLS:
            self._block("effort_control is not a recognized value", observation)
        if request.requested_effort is not None and request.prompted_effort is not None:
            self._block(
                "packet carries both requested_effort and prompted_effort", observation,
            )
        if request.effort_control == "api_enforced" and not request.requested_effort:
            self._block("api_enforced effort_control requires requested_effort", observation)
        if request.effort_control == "prompted_proxy" and request.prompted_effort not in (
                ACCEPTED_PROMPTED_EFFORTS):
            self._block(
                "prompted_proxy effort_control requires an accepted prompted_effort",
                observation,
            )

        hashes = (
            packet.get("packet_hash"), packet.get("reverified_packet_hash"),
            packet.get("clone_tree_hash"), packet.get("reverified_clone_tree_hash"),
            packet.get("baseline_tree_hash"), packet.get("source_tree_hash"),
        )
        if any(not is_sha256(value) for value in hashes):
            self._block("frozen packet contains an invalid SHA-256", observation)
        if packet["packet_hash"] != canonical_packet_hash(packet):
            self._block("frozen packet hash does not bind packet bytes", observation)
        if packet["reverified_packet_hash"] != packet["packet_hash"]:
            self._block("reverified packet hash diverges from packet hash", observation)
        if packet["clone_tree_hash"] != packet["reverified_clone_tree_hash"] or packet[
                "clone_tree_hash"] != packet["baseline_tree_hash"]:
            self._block("clone tree hash changed after packet sealing", observation)
        clone_entries = packet.get("clone_tree_entries")
        source_entries = packet.get("source_tree_entries")
        if not isinstance(clone_entries, list) or not clone_entries or not isinstance(
                source_entries, list) or not source_entries:
            self._block("deterministic tree entry bytes are missing", observation)
        if deterministic_tree_hash(clone_entries) != packet["clone_tree_hash"]:
            self._block("clone tree entries do not hash to the sealed clone_tree_hash", observation)
        if deterministic_tree_hash(source_entries) != packet["source_tree_hash"]:
            self._block("source tree entries do not hash to the sealed source_tree_hash", observation)

        if not self._is_canonical_absolute_path(request.clone_path):
            self._block("clone path is not a canonical absolute path", observation)
        if request.clone_path != packet.get("cwd"):
            self._block("request clone_path does not match the sealed packet cwd", observation)

        # Spec Sections 6.2/8, AC5: "Immediately before every dispatch, re-hash the
        # active clone against its sealed content-tree manifest... A dispatch may
        # start only if its clone and its packet are byte-identical to their
        # respective seals." Everything above this point only proves the packet's
        # OWN in-memory clone_tree_entries/clone_tree_hash fields are self-consistent
        # with each other -- data the caller already supplied, never independently
        # checked against reality. In production (test_mode is False) this block is
        # the one check that actually re-reads the real filesystem at
        # request.clone_path and confirms it has not diverged from its seal.
        # test_mode=True keeps the lighter in-memory-only check above, matching
        # codex_exec_adapter.py's own established test_mode-gated convention for
        # this exact tree-hash pattern (an accepted trust-boundary, not a new one).
        if not self.test_mode:
            actual_clone_tree_hash = self._real_filesystem_clone_tree_hash(
                request.clone_path, observation,
            )
            if actual_clone_tree_hash != packet["clone_tree_hash"]:
                self._block(
                    "real on-disk clone tree hash does not match the sealed "
                    "clone_tree_hash -- the active clone has diverged from its "
                    "content-tree seal",
                    observation,
                )

        environment = packet.get("environment")
        if not isinstance(environment, dict):
            self._block("frozen environment is missing", observation)
        if set(environment) - _ALLOWED_ENVIRONMENT_KEYS:
            self._block(
                "frozen environment carries a variable outside the minimal allowlist",
                observation,
            )

        writable_roots = [request.clone_path, request.artifact_dir]
        protected_roots = list(request.protected_roots or [])
        for root in writable_roots:
            if not self._is_canonical_absolute_path(root):
                self._block("a writable root is not a canonical absolute path", observation)
            if any(self._within(root, (protected,)) or root == protected
                   for protected in protected_roots):
                self._block("a writable root is inside a protected root", observation)

        allowed_write_targets = packet.get("allowed_write_targets")
        if not isinstance(allowed_write_targets, list):
            self._block("allowed_write_targets is missing", observation)
        for target in allowed_write_targets:
            if not self._is_canonical_absolute_path(target) or not self._within(
                    target, writable_roots):
                self._block(
                    "a sealed allowed_write_target escapes the clone/artifact roots",
                    observation,
                )
        return {"writable_roots": writable_roots, "protected_roots": protected_roots}

    def _classify_event(self, event: Dict[str, Any],
                        request: ClaudeAgentDispatchRequest) -> Dict[str, Any]:
        event_type = str(event.get("type", ""))
        tool_name = str(event.get("tool_name", ""))
        classification = {
            "type": event_type, "tool_name": tool_name, "cwd": event.get("cwd"),
            "write_targets": event.get("write_targets", []),
            "class": "TERMINAL", "reason": "unknown event",
        }
        if event_type == "result":
            classification["class"] = "RESULT"
            classification["reason"] = "dispatch result event"
            return classification
        if bool(request.frozen_packet.get("forbid_tool_events")):
            classification["reason"] = "smoke packet forbids every tool event"
            return classification
        if event_type == "tool_use":
            lowered = tool_name.lower()
            if lowered == "task" or "delegat" in lowered or "agent" in lowered:
                classification["reason"] = "sub-delegation tool (H-WF-DELEGATE-1)"
                return classification
            if lowered.startswith("mcp__"):
                classification["reason"] = "remote MCP tool dispatch"
                return classification
            if "fetch" in lowered or "search" in lowered or lowered in (
                    "curl", "http", "websocket"):
                classification["reason"] = (
                    "network-capable tool beyond the single Anthropic API call"
                )
                return classification
            # Note: the dispatch's OWN cwd is already bound to the sealed packet one
            # level up, in _validate_request (request.clone_path == packet["cwd"]);
            # an individual event's own reported "cwd" field is descriptive telemetry
            # from the SDK's event stream, not independently re-checked here -- the
            # operative, testable signal for a live tool-use event is its write
            # target(s) against the sealed allowlist, exercised below.
            writable_roots = [request.clone_path, request.artifact_dir]
            writes = event.get("write_targets", [])
            allowed_write_targets = request.frozen_packet.get("allowed_write_targets", [])
            if not isinstance(writes, list) or any(
                    target not in allowed_write_targets or not self._within(
                        target, writable_roots)
                    for target in writes):
                classification["reason"] = "tool event write target is not sealed"
                return classification
            classification["class"] = "ALLOWED_LOCAL"
            classification["reason"] = "sealed local tool event"
            return classification
        if event_type in ("permission_request", "sandbox_change"):
            classification["reason"] = (
                "approval/escalation/privilege/sandbox-change event " + event_type
            )
            return classification
        classification["reason"] = "unknown event type " + event_type
        return classification

    # ------------------------------------------------------------------------- execute

    def execute(self, request: ClaudeAgentDispatchRequest) -> ClaudeAgentDispatchResult:
        attempt_id = uuid.uuid4().hex
        base_observation: Dict[str, Any] = {
            "attempt_id": attempt_id,
            "approval_hash": request.approval_hash,
            "manifest_hash": request.manifest_hash,
            "requested_model": request.requested_model,
            "tool_scope": request.tool_scope,
            "effort_control": request.effort_control,
        }
        session_confirmed = False
        session_terminated = False
        started = time.monotonic()
        try:
            roots = self._validate_request(request, base_observation)

            tool_scope_evidence = self._probe_tool_scope(request, roots, base_observation)
            base_observation["tool_scope_evidence"] = tool_scope_evidence

            reservation_id = self._reserve(request, base_observation)

            sent_prompt, options, effective_dispatch = self._build_dispatch(request)
            base_observation["options"] = options

            try:
                raw_events = list(self.query_fn(sent_prompt, options))
            except TimeoutError as exc:
                session_terminated, session_confirmed = self._end_session(attempt_id)
                self._block(
                    "Claude Agent SDK dispatch timed out after %ss: %s"
                    % (request.timeout_seconds, exc),
                    base_observation,
                )
                raise  # unreachable, _block always raises
            except Exception as exc:
                session_terminated, session_confirmed = self._end_session(attempt_id)
                classification = classify_dispatch_error(request.requested_model, exc)
                base_observation["dispatch_error"] = classification
                self._block(
                    "Claude Agent SDK dispatch failed (%s): %s"
                    % (classification["failure_code"], exc),
                    base_observation,
                )
                raise  # unreachable

            base_observation["raw_events"] = raw_events
            result = self._process_events(
                raw_events, request, effective_dispatch, base_observation,
            )

            session_terminated, session_confirmed = self._end_session(attempt_id)
            if not session_confirmed:
                self._block(
                    "dispatch completed but the session could not be confirmed cleanly ended",
                    base_observation,
                )

            elapsed_seconds = max(0, int(time.monotonic() - started))
            self._reconcile(
                reservation_id, attempt_id, result, elapsed_seconds, base_observation,
            )
            self._retain_artifacts(request, result["observation"])
            return result["dispatch_result"]
        except ClaudeAgentAdapterBlockedError:
            if not session_terminated and not session_confirmed:
                # Best-effort: make sure a still-open session is not silently left
                # behind even on a validation/reservation-time abort that never
                # reached dispatch.
                try:
                    self._end_session(attempt_id)
                except Exception:
                    pass
            raise
        except Exception as exc:
            self._block(
                "Claude adapter failure: %s" % type(exc).__name__, base_observation,
            )
            raise  # unreachable

    def _probe_tool_scope(self, request: ClaudeAgentDispatchRequest,
                          roots: Dict[str, Any],
                          observation: Dict[str, Any]) -> Dict[str, Any]:
        try:
            evidence = self.tool_scope_prover.probe(
                tool_scope=request.tool_scope, cwd=request.clone_path,
                writable_roots=roots["writable_roots"],
                protected_roots=roots["protected_roots"],
                model=request.requested_model,
            )
        except Exception as exc:
            self._block(
                "tool-scope/sandbox evidence could not be obtained: %s" % exc, observation,
            )
        if not isinstance(evidence, dict) or evidence.get("sdk_enforced") is not True or not evidence.get(
                "mechanism") or not evidence.get("policy_hash"):
            self._block(
                "tool-scope/sandbox evidence is missing or incomplete", observation,
            )
        return evidence

    def _reserve(self, request: ClaudeAgentDispatchRequest,
                observation: Dict[str, Any]) -> str:
        unit = {
            "calls": 1, "seconds": request.timeout_seconds,
            "observed_total_tokens": 150000,
        }
        try:
            reservation = self.ledger.reserve(request.approval_hash + ":" + request.manifest_hash
                                              + ":" + uuid.uuid4().hex, unit)
        except Exception as exc:
            self._block("capacity reservation failed: %s" % exc, observation)
        reservation_id = reservation.get("reservation_id") if isinstance(reservation, dict) else None
        if not isinstance(reservation_id, str) or not reservation_id:
            self._block("ledger returned no reservation id", observation)
        try:
            self.ledger.start(reservation_id)
        except Exception as exc:
            self._block("capacity reservation could not be started: %s" % exc, observation)
        observation["reservation_id"] = reservation_id
        return reservation_id

    def _build_dispatch(self, request: ClaudeAgentDispatchRequest) -> tuple:
        options: Dict[str, Any] = {
            "model": request.requested_model,
            "cwd": request.clone_path,
            "tool_scope": request.tool_scope,
            "environment": dict(request.frozen_packet.get("environment", {})),
        }
        sent_prompt = request.prompt
        effective_dispatch: Dict[str, Any] = {
            "model": request.requested_model, "cwd": request.clone_path,
            "tool_scope": request.tool_scope, "effort_control": request.effort_control,
        }
        if request.effort_control == "api_enforced":
            options["effort"] = request.requested_effort
            effective_dispatch["requested_effort"] = request.requested_effort
        else:
            prompted_effort_text = (
                "\n\n[PROMPTED-EFFORT DIRECTIVE -- prompted proxy, not API-enforced: "
                "work at %s reasoning effort/depth for this task. This is a request "
                "the model may or may not follow; no proven reasoning-depth "
                "difference is claimed.]" % request.prompted_effort
            )
            sent_prompt = request.prompt + prompted_effort_text
            effective_dispatch["prompted_effort_text"] = prompted_effort_text
        return sent_prompt, options, effective_dispatch

    def _process_events(self, raw_events: List[Dict[str, Any]],
                        request: ClaudeAgentDispatchRequest,
                        effective_dispatch: Dict[str, Any],
                        observation: Dict[str, Any]) -> Dict[str, Any]:
        classifications = [self._classify_event(event, request) for event in raw_events]
        observation["event_classifications"] = classifications
        blocking = [c for c in classifications if c["class"] not in ("ALLOWED_LOCAL", "RESULT")]
        if blocking:
            self._block(
                "dispatch aborted on a %s event: %s" % (
                    blocking[0]["class"], blocking[0]["reason"],
                ),
                observation,
            )
        result_events = [event for event in raw_events if event.get("type") == "result"]
        if not result_events:
            self._block("dispatch produced no result event", observation)
        result_event = result_events[-1]

        configured_model = result_event.get("configured_model")
        if not isinstance(configured_model, str) or not configured_model:
            self._block("observed configured model is UNKNOWN", observation)
        if configured_model != request.requested_model:
            self._block(
                "observed configured model differs from the requested model "
                "(observed=%r requested=%r) -- never copying the requested value into "
                "the observed field" % (configured_model, request.requested_model),
                observation,
            )

        sdk_usage = result_event.get("usage")
        if not isinstance(sdk_usage, dict) or not isinstance(
                sdk_usage.get("input_tokens"), int) or not isinstance(
                    sdk_usage.get("output_tokens"), int):
            self._block("observed usage is UNKNOWN (missing/malformed)", observation)

        final_output = result_event.get("final_output")
        if not isinstance(final_output, str):
            self._block("dispatch final output is UNKNOWN", observation)

        expected_final_output = request.frozen_packet.get("expected_final_output")
        if expected_final_output is not None and final_output != expected_final_output:
            self._block(
                "final output does not match the sealed exact-literal contract",
                observation,
            )

        session_id = result_event.get("session_id")
        transcript_tokens = self._cross_check_transcript(session_id, sdk_usage, observation)

        observed_total_tokens = sdk_usage["input_tokens"] + sdk_usage["output_tokens"]
        usd_cost = self._compute_usd_cost(
            request.requested_model, sdk_usage, observation,
        )

        raw_observation = dict(observation)
        raw_observation.update({
            "final_output": final_output,
            "configured_model": configured_model,
            "usage": sdk_usage,
            "transcript_tokens": transcript_tokens,
        })
        raw_observation = self._redact(raw_observation)

        payload_bytes = canonical_bytes(raw_observation)
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        observation_id = "claude-agent-" + payload_hash[:24]

        provider = _execution.ProviderAdapterResult(
            response_text=final_output,
            canonical_sdk_response_id=session_id if isinstance(session_id, str) else None,
            canonical_sdk_request_id=observation.get("attempt_id"),
            raw_usage=sdk_usage,
            raw_response_payload_hash=payload_hash,
            raw_observation_id=observation_id,
            raw_response_payload_bytes=payload_bytes,
        )
        actual_effort = (
            request.requested_effort if request.effort_control == "api_enforced" else None
        )
        usage_v1 = _execution.normalize_provider_result(
            provider,
            attempt_id="claude-attempt-" + observation_id[-16:],
            dispatch_id="claude-dispatch-" + observation_id[-16:],
            execution_mode="claude_subscription", provider="anthropic",
            requested_model=request.requested_model, resolved_model_id=configured_model,
            requested_effort=request.requested_effort, actual_effort=actual_effort,
        )
        usage_v1["promotion_eligible"] = False
        if usd_cost is not None:
            usage_v1 = _execution.attach_cost_observation(usage_v1, {
                "observation_id": "claude-usd-" + observation_id[-16:],
                "source_kind": "billing_surface",
                "authoritative_cost_usd": usd_cost["amount_usd"],
            })
        _execution.validate_usage_v1(usage_v1)

        cleanup_receipt = {
            "attempt_id": observation.get("attempt_id"),
            "session_id": session_id,
            "event_count": len(raw_events),
            "finished_at_ns": time.time_ns(),
        }
        report_surface = {
            "observation_id": observation_id,
            "configured_model": configured_model,
            "effort_control": request.effort_control,
            "requested_effort": (
                request.requested_effort if request.effort_control == "api_enforced" else None
            ),
            "prompted_effort": (
                request.prompted_effort if request.effort_control == "prompted_proxy" else None
            ),
            "effective_dispatch": effective_dispatch,
            "observed_total_tokens": observed_total_tokens,
            "usage_cross_check": "AGREED",
            "usd_cost": usd_cost,
            "pace_status": PROMOTION_BOUNDARY,
            "promotion_eligible": False,
            "tool_scope_evidence": observation.get("tool_scope_evidence"),
        }
        dispatch_result = ClaudeAgentDispatchResult(
            provider_result=provider, usage_v1=usage_v1, raw_observation=raw_observation,
            cleanup_receipt=cleanup_receipt, final_output=final_output,
            report_surface=report_surface,
        )
        return {"dispatch_result": dispatch_result, "observation": raw_observation}

    def _cross_check_transcript(self, session_id: Any, sdk_usage: Dict[str, Any],
                                observation: Dict[str, Any]) -> Dict[str, int]:
        if self.transcript_reader is None:
            self._block(
                "no transcript cross-check collaborator is available -- missing "
                "telemetry is UNKNOWN, never assumed",
                observation,
            )
        try:
            records = list(self.transcript_reader(session_id))
        except Exception as exc:
            self._block(
                "transcript could not be located/parsed for cross-check: %s" % exc,
                observation,
            )
        input_total = 0
        output_total = 0
        for record in records:
            message = record.get("message") if isinstance(record, dict) else None
            usage = message.get("usage") if isinstance(message, dict) else None
            if not isinstance(usage, dict):
                continue
            input_total += int(usage.get("input_tokens", 0) or 0)
            output_total += int(usage.get("output_tokens", 0) or 0)
        if (input_total != sdk_usage["input_tokens"]
                or output_total != sdk_usage["output_tokens"]):
            self._block(
                "SDK result usage and transcript usage disagree/cross-check mismatch: "
                "sdk=(%d,%d) transcript=(%d,%d)" % (
                    sdk_usage["input_tokens"], sdk_usage["output_tokens"],
                    input_total, output_total,
                ),
                observation,
            )
        return {"input_tokens": input_total, "output_tokens": output_total}

    def _compute_usd_cost(self, model: str, sdk_usage: Dict[str, Any],
                          observation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Best-effort per-call USD cost for this dispatch's own report surface.

        This method deliberately does NOT abort the dispatch when the rate is
        unresolvable/stale: ``resolve_current_usd_rate`` itself (tested directly,
        Section 15) is the strict, standalone gate the pilot CONTROLLER uses to block
        approval sealing pre-execution and to abort remaining comparative calls when a
        stale/failed lookup recurs (Section 4.3) -- a cross-dispatch policy decision
        that belongs one layer up, not inside a single dispatch. Silently defaulting a
        cost to a number here would be the actual violation of "never a hardcoded
        stale rate used silently"; recording ``usd_cost: None`` (unavailable) is the
        honest outcome for this one call's report surface.
        """
        if self.rate_lookup is None:
            return None
        try:
            rate = resolve_current_usd_rate(model, rate_lookup=self.rate_lookup, clock=self.clock)
        except ClaudeAgentAdapterBlockedError as exc:
            observation["usd_cost_unavailable_reason"] = str(exc)
            return None
        amount_usd = (
            (sdk_usage["input_tokens"] / 1_000_000.0) * rate["input_usd_per_mtok"]
            + (sdk_usage["output_tokens"] / 1_000_000.0) * rate["output_usd_per_mtok"]
        )
        return {
            "amount_usd": amount_usd,
            "per_token_rate": rate,
            "rate_checked_at": rate["checked_at"],
        }

    def _reconcile(self, reservation_id: str, attempt_id: str, result: Dict[str, Any],
                   elapsed_seconds: int, observation: Dict[str, Any]) -> None:
        usd_cost = result["dispatch_result"].report_surface.get("usd_cost")
        actual = {
            "elapsed_seconds": elapsed_seconds,
            "observed_total_tokens": result["dispatch_result"].report_surface[
                "observed_total_tokens"],
            "usd_cost": usd_cost["amount_usd"] if usd_cost is not None else None,
        }
        try:
            self.ledger.reconcile(reservation_id, "claude-observation-" + attempt_id[:16], actual)
        except Exception as exc:
            self._block("cap reconciliation failed: %s" % exc, observation)

    def _end_session(self, attempt_id: str) -> tuple:
        terminated = False
        try:
            self.session_auditor.terminate(attempt_id)
            terminated = True
        except Exception:
            pass
        try:
            confirmed = bool(self.session_auditor.confirm_ended(attempt_id))
        except Exception:
            confirmed = False
        return terminated, confirmed

    def _retain_artifacts(self, request: ClaudeAgentDispatchRequest,
                          observation: Dict[str, Any]) -> None:
        artifact_dir = request.artifact_dir
        if not isinstance(artifact_dir, str) or not Path(artifact_dir).is_dir():
            return
        safe_observation = self._redact(observation)
        try:
            (Path(artifact_dir) / "raw-observation.json").write_text(
                json.dumps(safe_observation, sort_keys=True, indent=2, default=str),
                encoding="utf-8",
            )
            (Path(artifact_dir) / "final.txt").write_text(
                str(self._redact(safe_observation.get("final_output", ""))),
                encoding="utf-8",
            )
        except OSError:
            # Best-effort evidence retention (Section 10); never masks the primary
            # success/failure outcome already determined above.
            pass


class _DefaultSessionAuditor:
    """No-op production default; a real deployment wires a genuine session monitor."""

    def terminate(self, session_id: Any) -> None:
        return None

    def confirm_ended(self, session_id: Any) -> bool:
        return True
