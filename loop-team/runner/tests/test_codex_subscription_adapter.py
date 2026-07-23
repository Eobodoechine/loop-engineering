"""[BEHAVIORAL] Fake-only contract for the non-promoting Codex pilot.

These tests deliberately describe an injectable boundary.  ``CodexExecAdapter``
must accept fake ``popen_factory``, ``ledger``, ``containment_probe``, and
``process_tree`` collaborators; production may supply real implementations,
but this suite must never resolve or execute the real Codex binary.
"""
from __future__ import annotations

import importlib
import hashlib
import json
import os
import signal
import sys
from dataclasses import dataclass

import pytest


LOOP_TEAM_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if LOOP_TEAM_DIR not in sys.path:
    sys.path.insert(0, LOOP_TEAM_DIR)


def _adapter_api():
    return importlib.import_module("runner.codex_exec_adapter")


def _pilot_api():
    return importlib.import_module("runner.codex_subscription_pilot")


def _execution_api():
    return importlib.import_module("runner.experiment_execution")


def _jsonl(*records):
    return "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)


def _valid_jsonl(*, event=None, secret="TOP-SECRET-DO-NOT-RETAIN"):
    """A fake CLI transcript with direct model/effort/containment evidence."""
    event = event or {
        "type": "local_command",
        "argv": ["python3", "-m", "pytest", "tests/test_focus.py", "-q"],
        "cwd": "/clone",
        "env": {"LANG": "C", "PATH": "/usr/bin"},
        "write_targets": ["/clone/allowed.py"],
    }
    return _jsonl(
        {"type": "session.started", "session_id": "sess-1"},
        {
            "type": "session_configured",
            "session_id": "sess-1",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "sandbox_mode_evidence": {
                "mode": "workspace-write", "os_enforced": True,
            },
            "no_escalation_approval_evidence": {
                "mode": "never", "accepted": True,
            },
        },
        event,
        {
            "type": "turn.completed",
            "response_id": "resp-1",
            "request_id": "req-1",
            "final_output": "done " + secret,
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 30,
                "output_tokens": 20,
                "reasoning_output_tokens": 10,
            },
        },
    )


@dataclass
class FakeProcess:
    stdout: str
    stderr: str = "fake stderr TOP-SECRET-DO-NOT-RETAIN"
    returncode: int = 0
    pid: int = 4242

    def __post_init__(self):
        self.communicate_inputs = []
        self.wait_calls = []

    def communicate(self, input=None, timeout=None):
        self.communicate_inputs.append(input)
        self.wait_calls.append(timeout)
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode


class FakePopenFactory:
    def __init__(self, process):
        self.process = process
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, "kwargs": kwargs})
        return self.process


class FakeLedger:
    def __init__(self, allow=True):
        self.allow = allow
        self.calls = []

    def reserve(self, reservation_key, requested):
        self.calls.append(("reserve", reservation_key, requested))
        if not self.allow:
            raise RuntimeError("cap exhausted")
        return {"reservation_id": "reservation-1", "state": "RESERVED"}

    def start(self, reservation_id):
        self.calls.append(("start", reservation_id))
        return {"state": "NETWORK_IN_FLIGHT"}

    def reconcile(self, reservation_id, raw_observation_id, actual):
        self.calls.append(("reconcile", reservation_id, raw_observation_id, actual))
        return {"state": "RECONCILED"}


class FakeContainment:
    def __init__(self, available=True, *, violations=None, network_attempts=None,
                 protected_root_changes=None):
        self.available = available
        self.violations = list(violations or [])
        self.network_attempts = list(network_attempts or [])
        self.protected_root_changes = list(protected_root_changes or [])
        self.calls = []

    def probe(self, **kwargs):
        self.calls.append(kwargs)
        if not self.available:
            return None
        policy_bytes = b"fake-policy"
        return {
            "mechanism": "fake-os-sandbox",
            "version": "1.0",
            "policy_hash": hashlib.sha256(policy_bytes).hexdigest(),
            "policy_bytes": policy_bytes,
            "os_enforced": True,
            "writable_roots": kwargs["writable_roots"],
            "bound_request_writable_roots": kwargs["writable_roots"],
            "filesystem_violations": self.violations,
            "network_attempts": self.network_attempts,
            "protected_root_changes": self.protected_root_changes,
        }


class FakeProcessTree:
    def __init__(self, *, descendants=None, empty_after_cleanup=True):
        self.descendants = list(descendants or [4243])
        self.empty_after_cleanup = empty_after_cleanup
        self.actions = []

    def receipt(self, **kwargs):
        self.actions.append(("receipt", kwargs))
        return {
            "pid": 4242,
            "pgid": 4242,
            "process_tree": [4242] + self.descendants,
            "descendants_exited": self.empty_after_cleanup,
            "signals": [],
        }

    def signal_group(self, pgid, sig):
        self.actions.append(("signal_group", pgid, sig))

    def audit_empty(self, pgid):
        self.actions.append(("audit_empty", pgid))
        return self.empty_after_cleanup


def _request(api, **overrides):
    data = {
        "prompt": "write only allowed.py; never delegate",
        "clone_path": "/clone",
        "artifact_dir": "/artifact",
        "output_last_message_path": "/artifact/final.txt",
        "requested_model": "gpt-5.6-sol",
        "requested_effort": "high",
        "timeout_seconds": 900,
        "grace_seconds": 3,
        "approval_hash": "a" * 64,
        "manifest_hash": "d" * 64,
        "protected_roots": ["/baseline", "/other-clone"],
    }
    data.update(overrides)
    if "frozen_packet" not in data:
        contents = {
            "prompt": data["prompt"], "plan": "sealed plan\n",
            "oracle": "sealed oracle\n", "test": "sealed test\n",
            "dependency": "sealed dependency\n", "preprobe": "sealed preprobe\n",
        }
        canonical = lambda value: hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")).hexdigest()
        clone_entries = [{"path": "baseline.txt", "sha256": hashlib.sha256(
            b"baseline\n").hexdigest()}]
        source_entries = [{"path": "source.txt", "sha256": hashlib.sha256(
            b"source\n").hexdigest()}]
        clone_hash = canonical(clone_entries)
        source_hash = canonical(source_entries)
        clone = data["clone_path"]
        artifact = data["artifact_dir"]
        packet = {
            "ordered_argv": [["python3", "-m", "pytest", "tests/test_focus.py", "-q"]],
            "cwd": clone, "artifact_root": artifact,
            "stdout_path": artifact + "/stdout.jsonl",
            "stderr_path": artifact + "/stderr.txt",
            "final_path": data["output_last_message_path"],
            "events_path": artifact + "/raw-observation.json",
            "writable_roots": [clone, artifact],
            "environment": {"LANG": "C", "PATH": "/usr/bin"},
            "allowed_write_targets": [clone + "/allowed.py"],
            "clone_tree_hash": clone_hash, "reverified_clone_tree_hash": clone_hash,
            "baseline_tree_hash": clone_hash, "source_tree_hash": source_hash,
            "clone_tree_entries": clone_entries, "source_tree_entries": source_entries,
            "source_root": "/sealed/source",
            "task_identity": {"ordinal": 1, "case_id": "P1", "role": "planner"},
            "sealed_materials": {
                name: {"path": "/sealed/" + name, "content": content,
                       "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
                for name, content in contents.items()
            },
            "packet_hash": "0" * 64, "reverified_packet_hash": "0" * 64,
            "immutable_authority": {
                "schema": "user_confirmation.v1",
                "spec_sha256": "eab8f4f80758beaf2ea3326df4a176e091778a0f9dbea23dbf5cccea633d06e8",
                "approval_hash": data["approval_hash"], "manifest_hash": data["manifest_hash"],
                "packet_hash": "0" * 64,
                "caps": {"combined_calls": 10, "combined_timeout_seconds": 9000,
                         "aggregate_observed_tokens_max_when_telemetry_exists": 1500000,
                         "subscription_allowance_units_max": 10},
                "requested_model": data["requested_model"],
                "requested_effort": data["requested_effort"],
                "baseline_hashes": {"source": source_hash, "clone_tree": clone_hash},
                "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION", "confirmed": True,
            },
        }
        payload = json.loads(json.dumps(packet))
        payload.pop("packet_hash")
        payload.pop("reverified_packet_hash")
        payload["immutable_authority"].pop("packet_hash")
        sealed_hash = canonical(payload)
        packet["packet_hash"] = packet["reverified_packet_hash"] = sealed_hash
        packet["immutable_authority"]["packet_hash"] = sealed_hash
        data["frozen_packet"] = packet
    return api.CodexExecRequest(**data)


def _adapter(api, *, process=None, ledger=None, containment=None, tree=None):
    return api.CodexExecAdapter(
        cli_path="/fake/bin/codex",
        popen_factory=FakePopenFactory(process or FakeProcess(_valid_jsonl())),
        ledger=ledger or FakeLedger(),
        containment_probe=containment or FakeContainment(),
        process_tree=tree or FakeProcessTree(),
        redaction_patterns=["TOP-SECRET-DO-NOT-RETAIN"],
        test_mode=True,
    )


def test_fake_cli_uses_an_exact_argv_array_stdin_and_no_shell_interpolation():
    """[BEHAVIORAL][AC3] Hostile input remains one argv/stdin value."""
    api = _adapter_api()
    hostile = _request(
        api,
        prompt="$(touch /tmp/nope); 'quoted' && curl example.invalid",
        requested_effort="high",
    )
    event = {
        "type": "local_command",
        "argv": hostile.frozen_packet["ordered_argv"][0],
        "cwd": hostile.clone_path,
        "env": hostile.frozen_packet["environment"],
        "write_targets": hostile.frozen_packet["allowed_write_targets"],
    }
    process = FakeProcess(_valid_jsonl(event=event))
    adapter = _adapter(api, process=process)

    adapter.execute(hostile)

    call = adapter.popen_factory.calls[0]
    assert call["argv"] == [
        "/fake/bin/codex", "--ask-for-approval", "never", "exec", "--cd", hostile.clone_path, "--model",
        hostile.requested_model, "--sandbox", "read-only",
        "-c", "model_reasoning_effort=" + hostile.requested_effort, "--json",
        "--output-last-message", hostile.output_last_message_path, "-",
    ]
    assert call["kwargs"]["shell"] is False
    assert call["kwargs"]["start_new_session"] is True
    assert call["kwargs"]["cwd"] == hostile.clone_path
    assert process.communicate_inputs == [hostile.prompt]
    assert all(isinstance(value, str) for value in call["argv"])


def test_valid_fake_jsonl_returns_typed_result_direct_non_additive_usage_and_redacted_artifacts():
    """[BEHAVIORAL][AC3,AC6] Direct observed fields survive without synthetic totals."""
    adapter_api = _adapter_api()
    execution_api = _execution_api()
    result = _adapter(adapter_api).execute(_request(adapter_api))

    assert isinstance(result.provider_result, execution_api.ProviderAdapterResult)
    assert result.provider_result.response_text == "done [REDACTED]"
    assert result.provider_result.raw_usage == {
        "input_tokens": 100,
        "cached_input_tokens": 30,
        "output_tokens": 20,
        "reasoning_output_tokens": 10,
    }
    assert result.raw_observation["resolved_model_id"] == "gpt-5.6-sol"
    assert result.raw_observation["actual_effort"] == "high"
    assert result.raw_observation["sandbox_mode_evidence"]["os_enforced"] is True
    assert result.raw_observation["no_escalation_approval_evidence"]["accepted"] is True
    assert result.usage_v1["execution_mode"]["value"] == "codex_subscription"
    assert result.usage_v1["provider"]["value"] == "openai"
    assert result.usage_v1["token_fields"]["total_tokens_reported"]["value"] is None
    assert result.usage_v1["derived_total_tokens"]["value"] == 120
    assert result.usage_v1["billing_authority"]["value"] == (
        "unavailable_subscription_no_usd_billing_authority"
    )
    cleanup_receipt = dict(result.cleanup_receipt)
    finished_at_ns = cleanup_receipt.pop("finished_at_ns", None)
    assert type(finished_at_ns) is int and finished_at_ns > 0
    assert cleanup_receipt == {
        "pid": 4242,
        "pgid": 4242,
        "process_tree": [4242, 4243],
        "descendants_exited": True,
        "signals": [],
        "mechanism": "fake-os-sandbox",
        "mechanism_version": "1.0",
        "policy_hash": hashlib.sha256(b"fake-policy").hexdigest(),
        "effective_argv": result.argv,
        "effective_env": {"LANG": "C", "PATH": "/usr/bin"},
        "cwd": "/clone",
        "filesystem_violations": [],
        "network_attempts": [],
        "exit_status": 0,
        "input_hashes": result.provider_result.input_hashes,
        "input_receipt_hash": result.provider_result.input_receipt_hash,
    }
    execution_api.validate_usage_v1(result.usage_v1)
    retained = json.dumps({
        "stdout": result.stdout, "stderr": result.stderr,
        "final": result.final_output, "report": result.report_surface,
    })
    assert "TOP-SECRET-DO-NOT-RETAIN" not in retained


@pytest.mark.parametrize("field", [
    "session_configured", "sandbox_mode_evidence", "no_escalation_approval_evidence", "usage",
])
def test_missing_required_jsonl_evidence_fails_closed_before_a_result(field):
    """[BEHAVIORAL][AC3] Unavailable evidence is fatal, never defaulted."""
    api = _adapter_api()
    records = [json.loads(line) for line in _valid_jsonl().splitlines()]
    if field == "session_configured":
        records.pop(1)
    elif field == "usage":
        records[-1].pop(field)
    else:
        records[1].pop(field)
    with pytest.raises(api.CodexAdapterBlockedError):
        _adapter(api, process=FakeProcess(_jsonl(*records))).execute(_request(api))


@pytest.mark.parametrize("stdout, returncode", [
    ("not json\n", 0),
    (_valid_jsonl() + '{"type":"turn.completed","usage":{}}\n', 0),
    (_valid_jsonl(), 23),
])
def test_invalid_or_conflicting_jsonl_and_nonzero_exit_fail_closed(stdout, returncode):
    """[BEHAVIORAL][AC3] Malformed/conflicting output and process failure are terminal."""
    api = _adapter_api()
    with pytest.raises(api.CodexAdapterBlockedError):
        _adapter(api, process=FakeProcess(stdout, returncode=returncode)).execute(_request(api))


@pytest.mark.parametrize("event_type", [
    "child_agent", "delegation", "remote_mcp", "remote_tool", "network_tool",
    "approval_request", "escalation_request", "privilege_change", "sandbox_change",
    "unrecognized_future_tool",
])
def test_terminal_and_unknown_events_abort_but_are_persisted_with_classification(event_type):
    """[BEHAVIORAL][AC3] The parser records a terminal decision before aborting."""
    api = _adapter_api()
    event = {"type": event_type, "argv": ["bad"], "cwd": "/clone", "write_targets": []}
    with pytest.raises(api.CodexAdapterBlockedError) as exc_info:
        _adapter(api, process=FakeProcess(_valid_jsonl(event=event))).execute(_request(api))
    persisted = exc_info.value.observation["events"]
    assert persisted[0]["class"] == "TERMINAL"
    assert persisted[0]["reason"]
    assert persisted[0]["effective_argv"] == ["bad"]
    assert persisted[0]["cwd"] == "/clone"
    assert persisted[0]["write_targets"] == []


@pytest.mark.parametrize("mutation", [
    {"argv": ["git", "status"]},
    {"cwd": "/other-clone"},
    {"env": {"LANG": "C", "PATH": "/usr/bin", "EXTRA": "1"}},
    {"write_targets": ["/clone/not-allowed.py"]},
])
def test_only_frozen_packet_local_events_are_allowed(mutation):
    """[BEHAVIORAL][AC3] Local-looking events still fail when the seal differs."""
    api = _adapter_api()
    event = {
        "type": "local_command",
        "argv": ["python3", "-m", "pytest", "tests/test_focus.py", "-q"],
        "cwd": "/clone",
        "env": {"LANG": "C", "PATH": "/usr/bin"},
        "write_targets": ["/clone/allowed.py"],
    }
    event.update(mutation)
    with pytest.raises(api.CodexAdapterBlockedError):
        _adapter(api, process=FakeProcess(_valid_jsonl(event=event))).execute(_request(api))


def test_cap_reservation_precedes_popen_and_exit_reconciles_without_releasing_missing_telemetry():
    """[BEHAVIORAL][AC2] One reservation charges call/seconds/tokens/allowance first."""
    api = _adapter_api()
    ledger = FakeLedger()
    adapter = _adapter(api, ledger=ledger)
    adapter.execute(_request(api))
    assert [call[0] for call in ledger.calls] == ["reserve", "start", "reconcile"]
    assert ledger.calls[0][2] == {
        "calls": 1, "seconds": 900, "observed_total_tokens": 150000,
        "subscription_allowance_units": 1,
    }
    assert ledger.calls[-1][-1]["observed_total_tokens"] == 120

    blocked = _adapter(api, ledger=FakeLedger(allow=False))
    with pytest.raises(api.CodexAdapterBlockedError):
        blocked.execute(_request(api))
    assert blocked.popen_factory.calls == []


def test_timeout_uses_process_group_term_grace_kill_and_requires_empty_descendant_receipt():
    """[BEHAVIORAL][AC3] A timeout has auditable group cleanup or remains terminal."""
    api = _adapter_api()
    process = FakeProcess(_valid_jsonl())

    def timeouting_communicate(input=None, timeout=None):
        process.communicate_inputs.append(input)
        raise TimeoutError("fake timeout")

    process.communicate = timeouting_communicate
    tree = FakeProcessTree(empty_after_cleanup=True)
    with pytest.raises(api.CodexAdapterBlockedError):
        _adapter(api, process=process, tree=tree).execute(_request(api))
    signals = [action for action in tree.actions if action[0] == "signal_group"]
    assert signals == [
        ("signal_group", 4242, signal.SIGTERM),
        ("signal_group", 4242, signal.SIGKILL),
    ]
    assert ("audit_empty", 4242) in tree.actions

    unproven_tree = FakeProcessTree(empty_after_cleanup=False)
    with pytest.raises(api.CodexAdapterBlockedError):
        _adapter(api, process=FakeProcess(_valid_jsonl()), tree=unproven_tree).execute(_request(api))


@pytest.mark.parametrize("containment", [
    FakeContainment(available=False),
    FakeContainment(violations=[{"path": "/baseline/file", "kind": "write"}]),
    FakeContainment(network_attempts=[{"pid": 4243, "destination": "example.invalid:443"}]),
    FakeContainment(violations=[{"path": "/Use" "rs/test/.codex/auth.json", "kind": "read"}]),
    FakeContainment(protected_root_changes=[{"root": "/baseline", "hash_before": "a", "hash_after": "b"}]),
])
def test_os_enforcement_evidence_and_containment_receipt_are_mandatory(containment):
    """[BEHAVIORAL][AC3,AC4] Snapshots alone cannot substitute for enforcement proof."""
    api = _adapter_api()
    adapter = _adapter(api, containment=containment)
    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(_request(api))
    if not containment.available:
        assert adapter.popen_factory.calls == []


def _pilot_materials():
    manifest_hash = "m" * 64
    call_plan = (["smoke", "gpt-5.6-sol", "high"] +
                 [["planner", "gpt-5.6-sol", "high"]] * 3 +
                 [["incumbent_coder", "gpt-5.6-terra", "high"]] * 3 +
                 [["challenger_coder", "gpt-5.6-luna", "medium"]] * 3)
    manifest = {
        "schema": "pace_manifest.v1",
        "manifest_hash": manifest_hash,
        "call_plan": call_plan,
        "caps": {"combined_calls": 10, "combined_timeout_seconds": 9000,
                 "aggregate_observed_tokens_max_when_telemetry_exists": 1500000,
                 "subscription_allowance_units_max": 10},
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
    }
    approval = {
        "schema": "experiment_approval.v2", "execution_mode": "codex_subscription",
        "manifest_hash": manifest_hash, "user_created": True,
        "human_confirmation": {"manifest_hash": manifest_hash},
        "caps": manifest["caps"], "call_plan": call_plan,
        "promotion_boundary": manifest["promotion_boundary"],
    }
    packets = [{"packet_hash": chr(97 + index) * 64, "clone_tree_hash": chr(107 + index) * 64,
                "reverified_packet_hash": chr(97 + index) * 64,
                "reverified_clone_tree_hash": chr(107 + index) * 64}
               for index in range(9)]
    return approval, manifest, packets


def test_pilot_authority_requires_hash_bound_confirmation_test_gate_exact_caps_and_identical_packets():
    """[BEHAVIORAL][AC1,AC2,AC5] Any pre-start mismatch blocks adapter construction."""
    api = _pilot_api()
    approval, manifest, packets = _pilot_materials()
    constructed = []

    def forbidden_adapter_factory(*args, **kwargs):
        constructed.append((args, kwargs))
        raise AssertionError("authority failure constructed an adapter")

    runner = api.CodexSubscriptionPilot(adapter_factory=forbidden_adapter_factory)
    invalids = [
        ({**approval, "user_created": False}, manifest, packets),
        ({**approval, "human_confirmation": {"manifest_hash": "wrong" * 16}}, manifest, packets),
        ({**approval, "caps": {**approval["caps"], "combined_calls": 9}}, manifest, packets),
        (approval, {**manifest, "call_plan": manifest["call_plan"][:-1]}, packets),
        (approval, {**manifest, "call_plan": [
            ["smoke", "wrong-model", "high"], *manifest["call_plan"][1:]
        ]}, packets),
        (approval, manifest, packets[:-1]),
        (approval, manifest, [{**packets[0], "reverified_packet_hash": "z" * 64}] + packets[1:]),
    ]
    for bad_approval, bad_manifest, bad_packets in invalids:
        with pytest.raises(api.PilotBlockedError):
            runner.run(approval=bad_approval, manifest=bad_manifest,
                       required_test_receipt={"all_required_fake_cli_tests_passed": True},
                       frozen_packets=bad_packets, dry_run=False)
    assert constructed == []


def test_pilot_report_is_non_promoting_and_blinded_and_dry_run_cannot_reserve_or_launch():
    """[BEHAVIORAL][AC1,AC6] Validated artifacts never become routing authority."""
    api = _pilot_api()
    from runner.tests.test_codex_subscription_pilot import (
        _materials as valid_materials, _required_test_receipt,
    )
    approval, manifest, packets = valid_materials()
    starts = []
    runner = api.CodexSubscriptionPilot(
        adapter_factory=lambda: starts.append("adapter"), test_mode=True,
    )
    report = runner.run(
        approval=approval, manifest=manifest,
        required_test_receipt=_required_test_receipt(),
        frozen_packets=packets, dry_run=True,
        blinded_verifier_packet={"case_id": "P1", "opaque_artifact_id": "opaque-1",
                                 "excluded_fields": ["model", "effort", "usage", "latency", "arm"]},
    )
    assert starts == []
    assert report["pace_status"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert report["promotion_eligible"] is False
    assert report["routing_recommendation"] is None
    assert report["usd_cost"] is None
    assert report["blinded_verifier_packet"]["excluded_fields"] == [
        "model", "effort", "usage", "latency", "arm"
    ]


def test_pilot_verifies_each_coder_immediately_before_accepting_or_continuing():
    """[BEHAVIORAL][POST-ARM] Six coder outputs require ordered signed verification."""
    api = _pilot_api()
    from runner.tests.test_codex_subscription_pilot import (
        _materials as valid_materials, _required_test_receipt,
    )
    approval, manifest, packets = valid_materials()
    events = []

    class Adapter:
        def execute(self, packet):
            task = packet["task_identity"]
            role = task["role"]
            events.append(("execute", role))
            result = {"promotion_eligible": False, "role": role}
            if role == "planner":
                plan = {
                    "schema": "product_planner_output.v1",
                    "status": "PLAN_PASS",
                    "case_id": task["case_id"],
                    "allowed_paths": packet.get("allowed_patch_paths") or [
                        "src/%s.ts" % task["case_id"].lower()
                    ],
                    "steps": [{"id": "step-1", "action": "implement sealed repair"}],
                    "checks": ["run hidden product oracle"],
                }
                plan_bytes = json.dumps(
                    plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                ).encode() + b"\n"
                result.update({
                    "planner_output": plan_bytes.decode(),
                    "planner_output_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                })
            return result

    class PostArm:
        def verify_after_coder(self, *, packet, result):
            role = packet["task_identity"]["role"]
            events.append(("verify", role))
            assert result == {"promotion_eligible": False, "role": role}
            return {
                "schema": "controller_post_arm_receipt.v1",
                "status": "PASS", "signed": True,
                "promotion_eligible": False, "role": role,
            }

    report = api.CodexSubscriptionPilot(
        adapter_factory=Adapter, test_mode=True, post_arm_verifier=PostArm(),
    ).run(
        approval=approval, manifest=manifest,
        required_test_receipt=_required_test_receipt(),
        frozen_packets=packets, dry_run=False,
    )

    assert len(report["post_arm_verification_receipts"]) == 6
    assert len([event for event in events if event[0] == "verify"]) == 6
    for index, event in enumerate(events):
        if event[0] == "execute" and event[1] in {
                "incumbent_coder", "challenger_coder"}:
            assert events[index + 1] == ("verify", event[1])


def test_pilot_aborts_remaining_calls_on_first_invalid_post_arm_receipt():
    """[BEHAVIORAL][POST-ARM] An unsigned coder result cannot reach later calls."""
    api = _pilot_api()
    from runner.tests.test_codex_subscription_pilot import (
        _materials as valid_materials, _required_test_receipt,
    )
    approval, manifest, packets = valid_materials()
    starts = []

    class Adapter:
        def execute(self, packet):
            task = packet["task_identity"]
            starts.append(task["role"])
            result = {"promotion_eligible": False}
            if task["role"] == "planner":
                plan = {
                    "schema": "product_planner_output.v1",
                    "status": "PLAN_PASS",
                    "case_id": task["case_id"],
                    "allowed_paths": packet.get("allowed_patch_paths") or [
                        "src/%s.ts" % task["case_id"].lower()
                    ],
                    "steps": [{"id": "step-1", "action": "implement sealed repair"}],
                    "checks": ["run hidden product oracle"],
                }
                plan_bytes = json.dumps(
                    plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                ).encode() + b"\n"
                result.update({
                    "planner_output": plan_bytes.decode(),
                    "planner_output_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                })
            return result

    class InvalidPostArm:
        def verify_after_coder(self, **kwargs):
            return {
                "schema": "controller_post_arm_receipt.v1",
                "status": "PASS", "signed": False,
                "promotion_eligible": False,
            }

    runner = api.CodexSubscriptionPilot(
        adapter_factory=Adapter, test_mode=True,
        post_arm_verifier=InvalidPostArm(),
    )
    with pytest.raises(api.PilotBlockedError, match="post-arm|verification|receipt"):
        runner.run(
            approval=approval, manifest=manifest,
            required_test_receipt=_required_test_receipt(),
            frozen_packets=packets, dry_run=False,
        )

    assert starts == [
        "smoke", "planner", "planner", "planner", "incumbent_coder",
    ]


def test_installed_token_count_uses_cumulative_total_once_and_keeps_rate_limits_context_only():
    """[RED][COMPAT] Installed 0.41 telemetry maps total_token_usage without adding last usage."""
    api = _adapter_api()
    request = _request(api, requested_effort="high")
    stdout = _jsonl(
        {
            "type": "session_configured",
            "session_id": "installed-session",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "sandbox_mode_evidence": {"mode": "workspace-write", "os_enforced": True},
            "no_escalation_approval_evidence": {"mode": "never", "accepted": True},
        },
        {
            "msg": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 30,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 10,
                        "total_tokens": 120,
                    },
                    "last_token_usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 3,
                        "output_tokens": 2,
                        "reasoning_output_tokens": 1,
                        "total_tokens": 12,
                    },
                },
                "rate_limits": {"primary": {"used_percent": 1}, "secondary": {"used_percent": 2}},
            },
            "final_output": "done",
        },
    )

    result = _adapter(api, process=FakeProcess(stdout)).execute(request)

    assert result.provider_result.raw_usage == {
        "input_tokens": 100,
        "cached_input_tokens": 30,
        "output_tokens": 20,
        "reasoning_output_tokens": 10,
        "total_tokens": 120,
    }
    assert result.usage_v1["token_fields"]["total_tokens_reported"]["value"] == 120
    assert result.raw_observation["rate_limit_observation"] == {
        "primary": {"used_percent": 1}, "secondary": {"used_percent": 2},
    }
    assert "usd" not in json.dumps(result.raw_observation).lower()


def test_current_turn_completed_usage_has_no_provider_total_and_requires_session_configured_identity():
    """[RED][COMPAT] Current schema derives observed accounting from input plus output only."""
    api = _adapter_api()
    request = _request(api, requested_effort="high")
    stdout = _jsonl(
        {
            "type": "session_configured",
            "session_id": "current-session",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "sandbox_mode_evidence": {"mode": "workspace-write", "os_enforced": True},
            "no_escalation_approval_evidence": {"mode": "never", "accepted": True},
        },
        {
            "type": "turn.completed",
            "response_id": "resp-current",
            "request_id": "req-current",
            "final_output": "done",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 30,
                "output_tokens": 20,
                "reasoning_output_tokens": 10,
            },
        },
    )

    result = _adapter(api, process=FakeProcess(stdout)).execute(request)

    assert "total_tokens" not in result.provider_result.raw_usage
    assert result.usage_v1["token_fields"]["total_tokens_reported"]["value"] is None
    assert result.usage_v1["derived_total_tokens"]["value"] == 120
    assert result.raw_observation["configured_model_id"] == "gpt-5.6-sol"
    assert result.raw_observation["configured_reasoning_effort"] == "high"
