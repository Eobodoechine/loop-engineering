"""[BEHAVIORAL] Fail-closed fake-only contract for direct Codex execution.

These tests never resolve the real Codex binary.  Every process, containment,
and ledger collaborator is injected so a failure proves a policy boundary, not
an environment setup detail.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import pickle
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest


LOOP_TEAM_DIR = Path(__file__).resolve().parents[2]
if str(LOOP_TEAM_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_TEAM_DIR))


SPEC_SHA256 = "eab8f4f80758beaf2ea3326df4a176e091778a0f9dbea23dbf5cccea633d06e8"
CAPS = {
    "combined_calls": 10,
    "combined_timeout_seconds": 9000,
    "aggregate_observed_tokens_max_when_telemetry_exists": 1500000,
    "subscription_allowance_units_max": 10,
}


def _api():
    return importlib.import_module("runner.codex_exec_adapter")


@dataclass
class FakeProcess:
    stdout: str
    stderr: str = "Authorization: Bearer sk-live-secret"
    returncode: int = 0
    pid: int = 991

    def communicate(self, input=None, timeout=None):
        return self.stdout, self.stderr

    def wait(self, timeout=None):
        return self.returncode


class FakePopen:
    def __init__(self, process):
        self.process = process
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.process


class FakeSeatbeltPopen:
    """Scripted no-provider subprocess boundary for production-preflight tests."""

    def __init__(self, *, seatbelt_stdout, seatbelt_stderr="", seatbelt_returncode=0):
        self.seatbelt_stdout = seatbelt_stdout
        self.seatbelt_stderr = seatbelt_stderr
        self.seatbelt_returncode = seatbelt_returncode
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        if argv == ["/opt/homebrew/bin/codex", "--version"]:
            return FakeProcess("codex-cli 0.41.0\n")
        return FakeProcess(
            self.seatbelt_stdout,
            stderr=self.seatbelt_stderr,
            returncode=self.seatbelt_returncode,
        )


def _passing_concrete_preflight(api, tmp_path):
    model_cache = tmp_path / "models_cache.json"
    model_cache.write_text(json.dumps({
        "etag": '"fresh-model-cache-etag"',
        "models": [
            {"slug": "gpt-5.6-sol"},
            {"slug": "gpt-5.6-terra"},
            {"slug": "gpt-5.6-luna"},
        ],
    }), encoding="utf-8")
    denied = {
        "exit_code": 1, "stdout": "", "stderr": "Operation not permitted",
        "errno": "EPERM",
    }
    allowed = {"exit_code": 0, "stdout": "WRITE_ALLOWED", "stderr": ""}

    class SandboxAwarePopen(FakeSeatbeltPopen):
        def __call__(self, argv, **kwargs):
            self.calls.append((list(argv), dict(kwargs)))
            if argv == ["/opt/homebrew/bin/codex", "--version"]:
                return FakeProcess("codex-cli 0.41.0\n")
            workspace_write = "--full-auto" in argv
            payload = {
                "allowed_cwd_write": allowed if workspace_write else dict(denied),
                "denied_protected_write": dict(denied),
                "denied_protected_writes": [
                    dict(denied)
                    for _ in api.ProductionSeatbeltPreflight.DEFAULT_PROTECTED_ROOTS
                ],
                "denied_network": dict(denied),
            }
            return FakeProcess(json.dumps(payload) + "\n")

    fake = SandboxAwarePopen(seatbelt_stdout="")
    cwd = tmp_path / "preflight-cwd"
    cwd.mkdir()
    preflight = api.ProductionSeatbeltPreflight(
        popen_factory=fake,
        test_mode=True,
        artifact_dir=tmp_path / "preflight-artifacts",
        model_cache_path=model_cache,
    )
    receipt = preflight.run(
        cwd=str(cwd),
        protected_root="<HOME>/Claude/Projects/taxahead",
    )
    assert receipt["status"] == "PASS"
    return preflight, receipt, fake


def _slot_contract(*, sandbox="read-only"):
    return {
        "slot_id": "smoke-0" if sandbox == "read-only" else "coder-0",
        "cwd": "/private/tmp/codex-product-pilot-smoke-slot",
        "writable_roots": [
            "/private/tmp/codex-product-pilot-smoke-slot", "/artifact/slot",
        ],
        "protected_roots": [
            "<HOME>/Claude/Projects/taxahead",
            "<HOME>/Claude/Projects/taxahead-integration",
            "<HOME>/Claude/Projects/padsplit-reverification/pms",
        ],
        "model": "gpt-5.6-sol" if sandbox == "read-only" else "gpt-5.6-terra",
        "effort": "high",
        "sandbox": sandbox,
        "policy_sha256": "a" * 64,
    }


def _smoke_file_request(api, tmp_path, *, output_bytes=None, preexisting=False,
                        jsonl_final="CODEX_SMOKE_OK"):
    clone = Path("/private/tmp") / ("codex-product-pilot-smoke-files-" + tmp_path.name)
    clone.mkdir(exist_ok=True)
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    request = _direct_smoke_request(api, "valid")
    packet = json.loads(json.dumps(request.frozen_packet))
    packet["cwd"] = str(clone)
    packet["artifact_root"] = str(artifact)
    packet["writable_roots"] = [str(clone), str(artifact)]
    packet["stdout_path"] = str(artifact / "stdout.jsonl")
    packet["stderr_path"] = str(artifact / "stderr.txt")
    packet["final_path"] = str(artifact / "provider-final.txt")
    packet["events_path"] = str(artifact / "raw-observation.json")
    packet["allowed_write_targets"] = []
    packet["ordered_argv"] = [["python3", "-m", "pytest", "tests/test_focus.py", "-q"]]
    packet["packet_hash"] = api.canonical_packet_hash(packet)
    packet["reverified_packet_hash"] = packet["packet_hash"]
    packet["immutable_authority"]["packet_hash"] = packet["packet_hash"]
    output_path = artifact / "provider-final.txt"
    if preexisting:
        output_path.write_bytes(b"CODEX_SMOKE_OK")
    smoke_request = replace(
        request,
        clone_path=str(clone),
        artifact_dir=str(artifact),
        output_last_message_path=str(output_path),
        frozen_packet=packet,
    )
    stdout = _jsonl(
        {"type": "session.started", "session_id": "smoke-session"},
        {
            "type": "session_configured",
            "session_id": "smoke-session",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "sandbox_mode_evidence": {"mode": "read-only", "os_enforced": True},
            "no_escalation_approval_evidence": {"mode": "never", "accepted": True},
        },
        {
            "type": "turn.completed",
            "final_output": jsonl_final,
            "usage": {
                "input_tokens": 10, "cached_input_tokens": 2,
                "output_tokens": 2, "reasoning_output_tokens": 1,
            },
        },
    )

    class OutputProcess(FakeProcess):
        def communicate(self, input=None, timeout=None):
            if output_bytes is not None:
                output_path.write_bytes(output_bytes)
            return super().communicate(input=input, timeout=timeout)

    return smoke_request, OutputProcess(stdout), output_path


class FakeLedger:
    def __init__(self, *, reconcile_error=False):
        self.reconcile_error = reconcile_error
        self.calls = []

    def reserve(self, key, requested):
        self.calls.append(("reserve", key, requested))
        return {"reservation_id": "r-1"}

    def start(self, reservation_id):
        self.calls.append(("start", reservation_id))

    def reconcile(self, reservation_id, observation_id, actual):
        self.calls.append(("reconcile", reservation_id, observation_id, actual))
        if self.reconcile_error:
            raise RuntimeError("fake reconciliation outage")
        return {"state": "RECONCILED"}


class FakeContainment:
    def __init__(self, *, receipt=None):
        self.receipt = receipt
        self.calls = []

    def probe(self, **kwargs):
        self.calls.append(kwargs)
        policy_bytes = b"fake-policy"
        return self.receipt or {
            "mechanism": "fake-os-policy",
            "version": "1",
            "policy_hash": hashlib.sha256(policy_bytes).hexdigest(),
            "policy_bytes": policy_bytes,
            "os_enforced": True,
            "writable_roots": kwargs["writable_roots"],
            "bound_request_writable_roots": kwargs["writable_roots"],
            "filesystem_violations": [],
            "network_attempts": [],
            "protected_root_changes": [],
        }


class FakeTree:
    def receipt(self, **kwargs):
        return {"pid": kwargs["pid"], "pgid": kwargs["pgid"],
                "process_tree": [kwargs["pid"]], "descendants_exited": True}

    def audit_empty(self, pgid):
        return True

    def signal_group(self, pgid, sig):
        return None


def _jsonl(*records):
    return "".join(json.dumps(record) + "\n" for record in records)


def _terminal(*, model="gpt-5.6-sol", effort="high", sandbox="workspace-write",
              approval="never", usage=None, final="completed"):
    return {
        "type": "turn.completed",
        "final_output": final,
        "resolved_model_id": model,
        "actual_effort": effort,
        "sandbox_mode_evidence": {"mode": sandbox, "os_enforced": True},
        "no_escalation_approval_evidence": {"mode": approval, "accepted": True},
        "usage": usage or {
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 20,
            "reasoning_output_tokens": 10,
            "total_tokens": 120,
        },
    }


def _packet(*, clone="/clone", artifact="/artifact", command=None):
    command = command or ["python3", "-m", "pytest", "tests/test_focus.py", "-q"]
    contents = {
        "prompt": "make the sealed local edit only",
        "plan": "sealed plan\n", "oracle": "sealed oracle\n",
        "test": "sealed test\n", "dependency": "sealed dependency\n",
        "preprobe": "sealed preprobe\n",
    }
    clone_entries = [{"path": "baseline.txt", "content_sha256": hashlib.sha256(
        b"baseline\n").hexdigest()}]
    source_entries = [{"path": "source.txt", "content_sha256": hashlib.sha256(
        b"source\n").hexdigest()}]
    canonical = lambda value: hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    clone_hash = canonical(clone_entries)
    source_hash = canonical(source_entries)
    packet = {
        "packet_hash": "0" * 64,
        "clone_tree_hash": clone_hash,
        "reverified_packet_hash": "0" * 64,
        "reverified_clone_tree_hash": clone_hash,
        "baseline_tree_hash": clone_hash,
        "source_tree_hash": source_hash,
        "clone_tree_entries": clone_entries,
        "source_tree_entries": source_entries,
        "source_root": "/sealed/source",
        "task_identity": {"ordinal": 1, "case_id": "P1", "role": "planner"},
        "sealed_materials": {
            name: {"path": "/sealed/" + name, "content": content,
                   "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
            for name, content in contents.items()
        },
        "cwd": clone,
        "artifact_root": artifact,
        "stdout_path": artifact + "/stdout.jsonl",
        "stderr_path": artifact + "/stderr.txt",
        "final_path": artifact + "/final.txt",
        "events_path": artifact + "/raw-observation.json",
        "writable_roots": [clone, artifact],
        "environment": {"LANG": "C", "PATH": "/usr/bin"},
        "ordered_argv": [command],
        "allowed_write_targets": [clone + "/allowed.py"],
        "immutable_authority": {
            "schema": "user_confirmation.v1",
            "spec_sha256": SPEC_SHA256,
            "approval_hash": "a" * 64,
            "manifest_hash": "d" * 64,
            "packet_hash": "0" * 64,
            "caps": CAPS,
            "requested_model": "gpt-5.6-sol",
            "requested_effort": "high",
            "baseline_hashes": {"source": source_hash, "clone_tree": clone_hash},
            "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
            "confirmed": True,
        },
    }
    payload = json.loads(json.dumps(packet))
    payload.pop("packet_hash")
    payload.pop("reverified_packet_hash")
    payload["immutable_authority"].pop("packet_hash")
    sealed_hash = canonical(payload)
    packet["packet_hash"] = sealed_hash
    packet["reverified_packet_hash"] = sealed_hash
    packet["immutable_authority"]["packet_hash"] = sealed_hash
    return packet


def _request(api, *, clone="/clone", artifact="/artifact", packet=None):
    packet = packet or _packet(clone=clone, artifact=artifact)
    return api.CodexExecRequest(
        prompt="make the sealed local edit only",
        clone_path=clone,
        artifact_dir=artifact,
        output_last_message_path=artifact + "/final.txt",
        requested_model="gpt-5.6-sol",
        requested_effort="high",
        timeout_seconds=900,
        grace_seconds=1,
        approval_hash="a" * 64,
        manifest_hash="d" * 64,
        protected_roots=["/baseline"],
        frozen_packet=packet,
    )


def _direct_smoke_request(api, violation):
    clone = (
        "/private/tmp/codex-product-pilot-not-smoke-unit"
        if violation == "cwd"
        else "/private/tmp/codex-product-pilot-smoke-unit"
    )
    packet = _packet(clone=clone, artifact="/artifact")
    prompt = (
        "Return exactly CODEX_SMOKE_OK. Do not use tools, run commands, edit files, "
        "or contact external services.\n"
    )
    prompt_material = packet["sealed_materials"]["prompt"]
    prompt_material["content"] = prompt
    prompt_material["sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    packet["task_identity"] = {"ordinal": 0, "case_id": "smoke", "role": "smoke"}
    packet["allowed_write_targets"] = []
    packet.update({
        "execution_sandbox": "read-only",
        "approval_policy": "never",
        "expected_final_output": "CODEX_SMOKE_OK",
        "forbid_tool_events": True,
        "forbid_edits": True,
        "smoke_prompt_policy": "read-only-no-tools-no-edits-exact-output",
    })
    if violation == "sandbox":
        packet["execution_sandbox"] = "workspace-write"
    elif violation == "approval":
        packet["approval_policy"] = "on-request"
    elif violation == "output":
        packet["expected_final_output"] = "CODEX_SMOKE_ALMOST"
    elif violation == "tools":
        packet["forbid_tool_events"] = False
    elif violation == "edits":
        packet["forbid_edits"] = False
        packet["allowed_write_targets"] = [clone + "/edit.py"]
    packet["packet_hash"] = api.canonical_packet_hash(packet)
    packet["reverified_packet_hash"] = packet["packet_hash"]
    packet["immutable_authority"]["packet_hash"] = packet["packet_hash"]
    return replace(
        _request(api, clone=clone, artifact="/artifact", packet=packet),
        prompt=prompt,
    )


def _transcript(request, *, event=None, terminal=None):
    packet = request.frozen_packet
    terminal = terminal or _terminal()
    event = event or {
        "type": "local_command",
        "effective_argv": packet["ordered_argv"][0],
        "cwd": packet["cwd"],
        "env": packet["environment"],
        "write_targets": packet["allowed_write_targets"],
    }
    return _jsonl(
        {"type": "session.started", "session_id": "s-1"},
        {
            "type": "session_configured",
            "session_id": "s-1",
            "model": terminal["resolved_model_id"],
            "reasoning_effort": terminal["actual_effort"],
            "sandbox_mode_evidence": terminal["sandbox_mode_evidence"],
            "no_escalation_approval_evidence": terminal[
                "no_escalation_approval_evidence"
            ],
        },
        event,
        terminal,
    )


def _adapter(api, request, *, transcript=None, containment=None, ledger=None):
    popen = FakePopen(FakeProcess(transcript or _transcript(request)))
    adapter = api.CodexExecAdapter(
        cli_path="/fake/codex", popen_factory=popen, ledger=ledger or FakeLedger(),
        containment_probe=containment or FakeContainment(), process_tree=FakeTree(),
        test_mode=True,
    )
    return adapter, popen


@pytest.mark.parametrize("mutate", [
    lambda authority: authority.pop("confirmed"),
    lambda authority: authority.update({"packet_hash": "wrong" * 13}),
    lambda authority: authority.update({"requested_model": "gpt-5.6-luna"}),
    lambda authority: authority.update({"baseline_hashes": {"source": "wrong" * 13}}),
    lambda authority: authority.update({"promotion_boundary": "PROMOTION_ALLOWED"}),
])
def test_direct_execution_requires_exact_immutable_human_authority_before_popen(mutate):
    """[BEHAVIORAL] Confirmation binds the spec, seal, caps, baseline, and pilot-only boundary."""
    api = _api()
    packet = _packet()
    mutate(packet["immutable_authority"])
    request = _request(api, packet=packet)
    adapter, popen = _adapter(api, request)

    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)

    assert popen.calls == []


def test_injected_fake_cli_cannot_bypass_authority_or_canonical_roots_before_popen():
    """[BEHAVIORAL] Injection changes collaborators, never the pre-Popen authority gate."""
    api = _api()
    packet = _packet()
    packet.pop("immutable_authority")
    packet["cwd"] = "/clone/../forged-clone"
    request = _request(api, packet=packet)
    popen = FakePopen(FakeProcess(_transcript(request)))
    adapter = api.CodexExecAdapter(
        cli_path="/fake/bin/codex",
        popen_factory=popen,
        ledger=FakeLedger(),
        containment_probe=FakeContainment(),
        process_tree=FakeTree(),
        test_mode=True,
    )

    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)

    assert popen.calls == []


def test_punctuation_and_repeated_character_packet_hashes_cannot_self_attest_before_popen():
    """[BEHAVIORAL] A 64-byte label is not a SHA-256 identity or proof of packet bytes."""
    api = _api()
    packet = _packet()
    packet.update({
        "packet_hash": "!" * 64,
        "reverified_packet_hash": "!" * 64,
        "clone_tree_hash": "c" * 64,
        "reverified_clone_tree_hash": "c" * 64,
    })
    packet["immutable_authority"].update({
        "packet_hash": "!" * 64,
        "baseline_hashes": {"source": "b" * 64, "clone_tree": "c" * 64},
    })
    request = _request(api, packet=packet)
    adapter, popen = _adapter(api, request)

    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)

    assert popen.calls == []


def test_hex_looking_single_character_packet_and_tree_identities_are_not_content_proof_before_popen():
    """[BEHAVIORAL] Valid hash syntax still cannot replace recomputing packet and tree bytes."""
    api = _api()
    packet = _packet()
    packet.update({
        "packet_hash": "a" * 64,
        "reverified_packet_hash": "a" * 64,
        "clone_tree_hash": "b" * 64,
        "reverified_clone_tree_hash": "b" * 64,
    })
    packet["immutable_authority"].update({
        "packet_hash": "a" * 64,
        "baseline_hashes": {"source": "c" * 64, "clone_tree": "b" * 64},
    })
    request = _request(api, packet=packet)
    adapter, popen = _adapter(api, request)

    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)

    assert popen.calls == []


def test_declared_material_hashes_are_recomputed_from_files_and_tree_not_compared_to_themselves(tmp_path):
    """[BEHAVIORAL] Packet hashes bind actual prompt/plan/oracle/test/dependency/preprobe bytes."""
    api = _api()
    clone = tmp_path / "clone"
    artifact = tmp_path / "artifact"
    clone.mkdir()
    artifact.mkdir()
    materials = {}
    for name in ("prompt", "plan", "oracle", "test", "dependency", "preprobe"):
        path = clone / (name + ".txt")
        path.write_text(name + " original\n", encoding="utf-8")
        materials[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (clone / "test.txt").write_text("tampered after sealing\n", encoding="utf-8")

    packet = _packet(clone=str(clone), artifact=str(artifact))
    packet["sealed_materials"] = materials
    packet["baseline_tree_hash"] = "d" * 64
    request = _request(api, clone=str(clone), artifact=str(artifact), packet=packet)
    containment = FakeContainment(receipt={
        "mechanism": "fake-os-policy",
        "version": "1",
        "policy_hash": hashlib.sha256(b"fake-policy").hexdigest(),
        "policy_bytes": b"fake-policy",
        "os_enforced": True,
        "writable_roots": [str(clone), str(artifact)],
        "bound_request_writable_roots": [str(clone), str(artifact)],
        "filesystem_violations": [],
        "network_attempts": [],
        "protected_root_changes": [],
    })
    adapter, popen = _adapter(api, request, containment=containment)

    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)

    assert popen.calls == []


def test_production_execution_rejects_arbitrary_injected_containment_receipts_before_popen():
    """[BEHAVIORAL] Only the trusted production containment identity may authorize a real boundary."""
    api = _api()
    request = _request(api)
    popen = FakePopen(FakeProcess(_transcript(request)))
    adapter = api.CodexExecAdapter(
        cli_path="/opt/homebrew/bin/codex",
        popen_factory=popen,
        ledger=FakeLedger(),
        containment_probe=FakeContainment(),
        process_tree=FakeTree(),
    )

    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)

    assert popen.calls == []


@pytest.mark.parametrize("kind", ["packet_cwd", "outside_output", "extra_root", "dotdot", "symlink"])
def test_canonical_root_and_exact_writable_root_policy_block_before_popen(tmp_path, kind):
    """[BEHAVIORAL] Paths are canonical sealed identities, not string containment hints."""
    api = _api()
    clone, artifact = "/clone", "/artifact"
    packet = _packet(clone=clone, artifact=artifact)
    containment = FakeContainment()
    if kind == "packet_cwd":
        packet["cwd"] = "/other-clone"
    elif kind == "outside_output":
        packet["final_path"] = "/outside/final.txt"
    elif kind == "extra_root":
        containment = FakeContainment(receipt={
            "mechanism": "fake-os-policy", "version": "1", "policy_hash": "p" * 64,
            "os_enforced": True, "writable_roots": [clone, artifact, "/outside"],
            "filesystem_violations": [], "network_attempts": [], "protected_root_changes": [],
        })
    elif kind == "dotdot":
        clone = "/clone/../other-clone"
        packet = _packet(clone=clone, artifact=artifact)
        containment = FakeContainment(receipt={
            "mechanism": "fake-os-policy", "version": "1", "policy_hash": "p" * 64,
            "os_enforced": True, "writable_roots": [clone, artifact],
            "bound_request_writable_roots": [clone, artifact],
            "filesystem_violations": [], "network_attempts": [], "protected_root_changes": [],
        })
    else:
        real_clone = tmp_path / "clone"
        real_clone.mkdir()
        link_clone = tmp_path / "clone-link"
        link_clone.symlink_to(real_clone, target_is_directory=True)
        clone = str(link_clone)
        artifact = str(tmp_path / "artifact")
        Path(artifact).mkdir()
        packet = _packet(clone=clone, artifact=artifact)
        containment = FakeContainment(receipt={
            "mechanism": "fake-os-policy", "version": "1", "policy_hash": "p" * 64,
            "os_enforced": True, "writable_roots": [clone, artifact],
            "bound_request_writable_roots": [clone, artifact],
            "filesystem_violations": [], "network_attempts": [], "protected_root_changes": [],
        })

    request = _request(api, clone=clone, artifact=artifact, packet=packet)
    adapter, popen = _adapter(api, request, containment=containment)
    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)
    assert popen.calls == []


@pytest.mark.parametrize("terminal", [
    _terminal(model="gpt-5.6-luna"),
    _terminal(effort="low"),
    _terminal(sandbox="read-only"),
    _terminal(approval="on-request"),
])
def test_terminal_evidence_must_exactly_equal_the_sealed_model_effort_sandbox_and_no_escalation(terminal):
    """[BEHAVIORAL] Terminal fields are equality checks, never mere presence checks."""
    api = _api()
    request = _request(api)
    adapter, _ = _adapter(api, request, transcript=_transcript(request, terminal=terminal))
    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)


@pytest.mark.parametrize("command", [
    ["curl", "https://example.invalid/telemetry"],
    ["pytest", "--upload-results", "https://example.invalid"],
    ["python3", "-m", "runner.agent", "delegate"],
    ["mcp", "call", "remote-tool"],
    ["sh", "-c", "pytest -q"],
    ["sudo", "pytest", "-q"],
])
def test_sealed_local_command_classifier_rejects_network_delegation_remote_shell_and_privilege_argv(command):
    """[BEHAVIORAL] A packet label cannot whitelist an unsafe executable or option."""
    api = _api()
    packet = _packet(command=command)
    request = _request(api, packet=packet)
    adapter, _ = _adapter(api, request)
    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)


def test_reconciliation_error_is_terminal_and_cannot_return_a_success_result():
    """[BEHAVIORAL] An unreconciled reservation is a failed direct execution."""
    api = _api()
    request = _request(api)
    ledger = FakeLedger(reconcile_error=True)
    adapter, _ = _adapter(api, request, ledger=ledger)
    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)
    assert [call[0] for call in ledger.calls] == ["reserve", "start", "reconcile"]


@pytest.mark.parametrize("usage", [
    {"input_tokens": True, "cached_input_tokens": 20, "output_tokens": 20,
     "reasoning_output_tokens": 10, "total_tokens": 120},
    {"input_tokens": "100", "cached_input_tokens": 20, "output_tokens": 20,
     "reasoning_output_tokens": 10, "total_tokens": 120},
    {"input_tokens": 100.0, "cached_input_tokens": 20, "output_tokens": 20,
     "reasoning_output_tokens": 10, "total_tokens": 120},
    {"input_tokens": 100, "cached_input_tokens": 101, "output_tokens": 20,
     "reasoning_output_tokens": 10, "total_tokens": 120},
    {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 20,
     "reasoning_output_tokens": 21, "total_tokens": 120},
    {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 20,
     "reasoning_output_tokens": 10, "total_tokens": 119},
])
def test_usage_requires_exact_nonnegative_ints_component_bounds_and_total_arithmetic(usage):
    """[BEHAVIORAL] Subscription telemetry cannot be coerced or arithmetically inconsistent."""
    api = _api()
    request = _request(api)
    adapter, _ = _adapter(api, request, transcript=_transcript(
        request, terminal=_terminal(usage=usage)))
    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)


@pytest.mark.parametrize("effort", ["ultra", "xhigh", "max"])
def test_installed_cli_rejects_unsupported_reasoning_effort_before_reservation_or_popen(effort):
    """[RED][COMPAT] Only minimal/low/medium/high are legal under Codex CLI 0.41.0."""
    api = _api()
    packet = _packet()
    packet["immutable_authority"]["requested_effort"] = effort
    packet["packet_hash"] = api.canonical_packet_hash(packet)
    packet["reverified_packet_hash"] = packet["packet_hash"]
    packet["immutable_authority"]["packet_hash"] = packet["packet_hash"]
    request = replace(_request(api, packet=packet), requested_effort=effort)
    adapter, popen = _adapter(
        api, request, transcript=_transcript(request, terminal=_terminal(effort=effort)),
    )

    with pytest.raises(api.CodexAdapterBlockedError, match="reasoning effort"):
        adapter.execute(request)

    assert popen.calls == []
    assert adapter.ledger.calls == []


def test_trusted_production_containment_cannot_be_minted_from_an_arbitrary_callable():
    """[RED][PRODUCTION-PREFLIGHT] A callback cannot self-attest production Seatbelt trust."""
    api = _api()

    def self_attesting_callback(**kwargs):
        return {
            "self_verifies": True,
            "trusted_identity": api.TrustedProductionContainment.IDENTITY,
            "os_enforced": True,
            "mechanism": "claimed-seatbelt",
            "version": "claimed",
            "writable_roots": kwargs.get("writable_roots"),
        }

    with pytest.raises(TypeError, match="concrete.*production|callback"):
        api.TrustedProductionContainment(
            probe=self_attesting_callback,
            policy_bytes=b"self-generated policy bytes",
        )


def test_production_seatbelt_preflight_rejects_subprocess_injection_outside_explicit_test_mode():
    """[RED][PRODUCTION-PREFLIGHT] Production construction owns its subprocess boundary."""
    api = _api()
    fake = FakeSeatbeltPopen(seatbelt_stdout="{}\n")

    with pytest.raises(TypeError, match="test mode|dependency injection"):
        api.ProductionSeatbeltPreflight(popen_factory=fake, test_mode=False)


def test_concrete_seatbelt_preflight_executes_exact_no_provider_argv_and_hashes_executed_bytes(
        tmp_path):
    """[RED][PRODUCTION-PREFLIGHT] PASS comes from concrete allow/deny subprocess evidence."""
    api = _api()
    probe_result = {
        "allowed_cwd_write": {
            "exit_code": 1, "stdout": "", "stderr": "Operation not permitted",
            "errno": "EPERM",
        },
        "denied_protected_write": {
            "exit_code": 1, "stdout": "", "stderr": "Operation not permitted",
            "errno": "EPERM",
        },
        "denied_network": {
            "exit_code": 1, "stdout": "", "stderr": "Operation not permitted",
            "errno": "EPERM",
        },
        "forged_policy_sha256": "0" * 64,
        "forged_probe_sha256": "1" * 64,
    }
    fake = FakeSeatbeltPopen(seatbelt_stdout=json.dumps(probe_result) + "\n")
    preflight = api.ProductionSeatbeltPreflight(
        popen_factory=fake,
        test_mode=True,
        artifact_dir=tmp_path,
    )

    receipt = preflight.run_probe(
        model="gpt-5.6-sol",
        effort="high",
        sandbox="read-only",
        cwd="/private/tmp/codex-product-pilot-preflight",
        protected_root="<HOME>/Claude/Projects/taxahead",
    )

    seatbelt_call = next(call for call in fake.calls if "seatbelt" in call[0])
    argv, kwargs = seatbelt_call
    assert argv[:7] == [
        "/opt/homebrew/bin/codex", "--model", "gpt-5.6-sol",
        "-c", "model_reasoning_effort=high",
        "debug", "seatbelt",
    ]
    assert argv[7:10] == ["--", "/usr/bin/python3", "-c"]
    assert "--full-auto" not in argv
    assert "--sandbox" not in argv
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert receipt["status"] == "PASS"
    assert receipt["provider_process_starts"] == 0
    assert receipt["allowed_cwd_write"]["exit_code"] == 1
    assert receipt["allowed_cwd_write"]["errno"] == "EPERM"
    assert receipt["sandbox"] == "read-only"
    assert json.loads(receipt["policy_bytes"])["sandbox"] == "read-only"
    assert receipt["denied_protected_write"]["errno"] == "EPERM"
    assert receipt["denied_network"]["errno"] == "EPERM"
    assert receipt["probe_sha256"] == hashlib.sha256(
        receipt["probe_bytes"].encode("utf-8")
    ).hexdigest()
    assert receipt["policy_sha256"] == hashlib.sha256(
        receipt["policy_bytes"].encode("utf-8")
    ).hexdigest()
    assert receipt["probe_sha256"] != probe_result["forged_probe_sha256"]
    assert receipt["policy_sha256"] != probe_result["forged_policy_sha256"]


def test_preflight_forbids_unsupported_sandbox_option_and_records_parser_exit_two(tmp_path):
    """[RED][PREFLIGHT-ARGV] Installed debug seatbelt rejects the --sandbox option locally."""
    api = _api()
    denied = {
        "exit_code": 1, "stdout": "", "stderr": "Operation not permitted", "errno": "EPERM",
    }

    class InstalledParserPopen(FakeSeatbeltPopen):
        def __call__(self, argv, **kwargs):
            self.calls.append((list(argv), dict(kwargs)))
            if "--sandbox" in argv:
                return FakeProcess(
                    "", stderr="error: unexpected argument '--sandbox' found\n", returncode=2,
                )
            return FakeProcess(json.dumps({
                "allowed_cwd_write": denied,
                "denied_protected_write": denied,
                "denied_protected_writes": [denied],
                "denied_network": denied,
            }) + "\n")

    fake = InstalledParserPopen(seatbelt_stdout="")
    preflight = api.ProductionSeatbeltPreflight(
        popen_factory=fake, test_mode=True, artifact_dir=tmp_path,
    )
    receipt = preflight.run_probe(
        model="gpt-5.6-sol", effort="high", sandbox="read-only",
        cwd="/private/tmp/codex-product-pilot-preflight",
        protected_root="<HOME>/Claude/Projects/taxahead",
    )
    argv = fake.calls[0][0]

    if "--sandbox" in argv:
        assert receipt["status"] == "PRECHECK_FAILED"
        assert receipt["failure_code"] == "SEATBELT_PROBE_FAILED"
        assert receipt["blocker_class"] == "local_compatibility_precheck"
        assert receipt["process_exit_code"] == 2
        assert "unexpected argument '--sandbox'" in receipt["stderr"]
    assert receipt["provider_process_starts"] == 0
    assert "--sandbox" not in argv


def test_nested_app_sandbox_seatbelt_failure_is_precheck_failed_with_zero_provider_starts(
        tmp_path):
    """[RED][PRODUCTION-PREFLIGHT] sandbox_apply denial is local PRECHECK_FAILED evidence."""
    api = _api()
    fake = FakeSeatbeltPopen(
        seatbelt_stdout="",
        seatbelt_stderr="sandbox_apply: Operation not permitted\n",
        seatbelt_returncode=70,
    )
    preflight = api.ProductionSeatbeltPreflight(
        popen_factory=fake,
        test_mode=True,
        artifact_dir=tmp_path,
    )

    receipt = preflight.run_probe(
        model="gpt-5.6-sol",
        effort="high",
        sandbox="read-only",
        cwd="/private/tmp/codex-product-pilot-preflight",
        protected_root="<HOME>/Claude/Projects/taxahead",
    )

    assert receipt["status"] == "PRECHECK_FAILED"
    assert receipt["failure_code"] == "NESTED_APP_SANDBOX_DENIED"
    assert receipt["blocker_class"] == "local_compatibility_precheck"
    assert receipt["provider_process_starts"] == 0
    assert receipt["process_exit_code"] == 70
    assert "sandbox_apply" in receipt["stderr"]


def test_in_memory_pass_receipt_cannot_call_private_factory_to_mint_trusted_containment():
    """[RED][CAPABILITY] Only the concrete completed preflight owns capability minting."""
    api = _api()
    forged = {
        "status": "PASS",
        "provider_process_starts": 0,
        "policy_bytes": "forged in-memory policy",
        "binary": {"version": "codex-cli 0.41.0"},
        "checks": [],
    }

    with pytest.raises((AttributeError, TypeError)):
        api.TrustedProductionContainment._from_preflight_receipt(forged)


def test_completed_preflight_mints_one_use_capability_bound_to_exact_request(tmp_path):
    """[RED][CAPABILITY] A trusted containment capability cannot authorize two starts."""
    api = _api()
    preflight, receipt, _ = _passing_concrete_preflight(api, tmp_path)
    capability = preflight.trusted_containment()
    kwargs = {
        "argv": ["/opt/homebrew/bin/codex", "exec", "-"],
        "cwd": "/private/tmp/codex-product-pilot-smoke-unit",
        "writable_roots": [
            "/private/tmp/codex-product-pilot-smoke-unit", "/artifact",
        ],
        "protected_roots": ["<HOME>/Claude/Projects/taxahead"],
        "environment": {"LANG": "C", "PATH": "/usr/bin"},
    }

    attestation = capability.probe(**kwargs)

    assert attestation["preflight_receipt_sha256"] == api.canonical_hash(receipt)
    assert api.TrustedProductionContainment.verify(attestation, **kwargs) is True
    with pytest.raises((TypeError, RuntimeError), match="used|consumed|capability"):
        capability.probe(**kwargs)


def test_preflight_capability_fails_when_its_persisted_receipt_artifact_is_mutated(tmp_path):
    """[RED][CAPABILITY] Capability validity is bound to retained receipt artifact bytes."""
    api = _api()
    preflight, receipt, _ = _passing_concrete_preflight(api, tmp_path)
    artifact_path = Path(receipt["artifact_path"])
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == receipt["artifact_sha256"]
    capability = preflight.trusted_containment()
    artifact_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises((TypeError, RuntimeError), match="artifact|mutated|receipt"):
        capability.probe(
            argv=["/opt/homebrew/bin/codex", "exec", "-"],
            cwd="/private/tmp/codex-product-pilot-smoke-unit",
            writable_roots=["/private/tmp/codex-product-pilot-smoke-unit", "/artifact"],
            protected_roots=["<HOME>/Claude/Projects/taxahead"],
            environment={"LANG": "C", "PATH": "/usr/bin"},
        )


def test_preflight_fails_when_any_canonical_protected_root_write_is_not_denied_with_eperm(
        tmp_path):
    """[RED][SEATBELT] TaxAhead and PMS writes must each independently fail with EPERM."""
    api = _api()
    denied = {
        "exit_code": 1, "stdout": "", "stderr": "Operation not permitted", "errno": "EPERM",
    }
    allowed = {"exit_code": 0, "stdout": "WRITE_ALLOWED", "stderr": ""}
    fake = FakeSeatbeltPopen(seatbelt_stdout=json.dumps({
        "allowed_cwd_write": allowed,
        "denied_protected_write": denied,
        "denied_protected_writes": [denied, allowed],
        "denied_network": denied,
    }) + "\n")
    cwd = tmp_path / "preflight-cwd"
    cwd.mkdir()
    preflight = api.ProductionSeatbeltPreflight(
        popen_factory=fake, test_mode=True, artifact_dir=tmp_path,
    )

    receipt = preflight.run_probe(
        model="gpt-5.6-sol",
        effort="high",
        sandbox="workspace-write",
        cwd=str(cwd),
        protected_root="<HOME>/Claude/Projects/taxahead",
        additional_protected_roots=(
            "<HOME>/Claude/Projects/padsplit-reverification/pms",
        ),
    )

    assert receipt["status"] == "PRECHECK_FAILED"
    assert receipt["failure_code"] == "PROTECTED_ROOT_WRITE_NOT_DENIED"
    assert receipt["provider_process_starts"] == 0
    assert receipt["failed_protected_root"] == (
        "<HOME>/Claude/Projects/padsplit-reverification/pms"
    )
    assert [entry["exit_code"] for entry in receipt["denied_protected_writes"]] == [1, 0]


@pytest.mark.parametrize("violation", ["cwd", "sandbox", "approval", "output", "tools", "edits"])
def test_direct_adapter_rejects_invalid_smoke_contract_before_reservation_or_popen(violation):
    """[RED][DIRECT-SMOKE] Adapter enforces smoke kind independently of pilot validation."""
    api = _api()
    request = _direct_smoke_request(api, violation)
    ledger = FakeLedger()
    adapter, popen = _adapter(api, request, ledger=ledger)

    with pytest.raises(api.CodexAdapterBlockedError, match="smoke"):
        adapter.execute(request)

    assert ledger.calls == []
    assert popen.calls == []


@pytest.mark.parametrize("mutation", [
    "cwd", "writable_roots", "protected_roots", "model", "effort", "sandbox", "policy",
])
def test_containment_capability_is_bound_to_exact_preflight_slot_and_request(tmp_path, mutation):
    """[RED][SLOT-CAPABILITY] probe cannot substitute any request or policy dimension."""
    api = _api()
    preflight, _, _ = _passing_concrete_preflight(api, tmp_path)
    slot = _slot_contract()
    capability = preflight.trusted_containment(slot=slot)
    request = json.loads(json.dumps(slot))
    if mutation == "cwd":
        request["cwd"] += "-other"
    elif mutation == "writable_roots":
        request["writable_roots"] = [request["cwd"], "/artifact/other"]
    elif mutation == "protected_roots":
        request["protected_roots"] = request["protected_roots"][:-1]
    elif mutation == "model":
        request["model"] = "gpt-5.6-luna"
    elif mutation == "effort":
        request["effort"] = "medium"
    elif mutation == "sandbox":
        request["sandbox"] = "workspace-write"
    else:
        request["policy_sha256"] = "b" * 64

    with pytest.raises((TypeError, RuntimeError), match="slot|request|capability|policy"):
        capability.probe(slot=request)


@pytest.mark.parametrize("operation", ["copy", "deepcopy", "pickle"])
def test_containment_capability_cannot_be_copied_or_reconstructed(tmp_path, operation):
    """[RED][SLOT-CAPABILITY] Opaque one-use authority cannot be duplicated."""
    api = _api()
    preflight, _, _ = _passing_concrete_preflight(api, tmp_path)
    capability = preflight.trusted_containment(slot=_slot_contract())

    with pytest.raises((TypeError, RuntimeError, pickle.PickleError), match="capability|copy|pickle"):
        if operation == "copy":
            copy.copy(capability)
        elif operation == "deepcopy":
            copy.deepcopy(capability)
        else:
            pickle.loads(pickle.dumps(capability))


def test_containment_capability_state_is_immutable(tmp_path):
    """[RED][SLOT-CAPABILITY] Callers cannot reset consumed state or replace the bound seed."""
    api = _api()
    preflight, _, _ = _passing_concrete_preflight(api, tmp_path)
    capability = preflight.trusted_containment(slot=_slot_contract())

    with pytest.raises((AttributeError, TypeError), match="immutable|attribute|capability"):
        capability._consumed = False
    with pytest.raises((AttributeError, TypeError), match="immutable|attribute|capability"):
        capability._seed = object()


def test_read_only_and_workspace_write_preflight_use_distinct_hashed_profiles(tmp_path):
    """[RED][SEATBELT-MODE] Read-only denies cwd writes; workspace-write permits them."""
    api = _api()
    denied = {
        "exit_code": 1, "stdout": "", "stderr": "Operation not permitted", "errno": "EPERM",
    }
    allowed = {"exit_code": 0, "stdout": "WRITE_ALLOWED", "stderr": ""}

    class ModePopen(FakeSeatbeltPopen):
        def __call__(self, argv, **kwargs):
            self.calls.append((list(argv), dict(kwargs)))
            cwd_result = allowed if "--full-auto" in argv else denied
            protected = [dict(denied), dict(denied), dict(denied)]
            return FakeProcess(json.dumps({
                "allowed_cwd_write": cwd_result,
                "denied_protected_write": protected[0],
                "denied_protected_writes": protected,
                "denied_network": denied,
            }) + "\n")

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    preflight = api.ProductionSeatbeltPreflight(
        popen_factory=ModePopen(seatbelt_stdout=""), test_mode=True, artifact_dir=tmp_path,
    )
    roots = _slot_contract()["protected_roots"]
    read_only = preflight.run_probe(
        model="gpt-5.6-sol", effort="high", sandbox="read-only", cwd=str(cwd),
        protected_root=roots[0], additional_protected_roots=roots[1:],
    )
    workspace = preflight.run_probe(
        model="gpt-5.6-sol", effort="high", sandbox="workspace-write", cwd=str(cwd),
        protected_root=roots[0], additional_protected_roots=roots[1:],
    )

    assert read_only["status"] == workspace["status"] == "PASS"
    assert read_only["cwd_write_expectation"] == "DENIED_EPERM"
    assert workspace["cwd_write_expectation"] == "ALLOWED"
    assert read_only["argv"] != workspace["argv"]
    assert "--full-auto" not in read_only["argv"]
    assert "--full-auto" in workspace["argv"]
    assert "--sandbox" not in read_only["argv"]
    assert "--sandbox" not in workspace["argv"]
    assert read_only["argv_sha256"] != workspace["argv_sha256"]
    assert read_only["policy_sha256"] != workspace["policy_sha256"]
    assert read_only["sandbox"] == "read-only"
    assert workspace["sandbox"] == "workspace-write"
    assert json.loads(read_only["policy_bytes"])["sandbox"] == "read-only"
    assert json.loads(workspace["policy_bytes"])["sandbox"] == "workspace-write"


def test_production_preflight_protects_every_canonical_taxahead_and_pms_root():
    """[RED][PROTECTED-ROOTS] The integration checkout is protected alongside canonical roots."""
    api = _api()
    assert set(api.ProductionSeatbeltPreflight.DEFAULT_PROTECTED_ROOTS) == {
        "<HOME>/Claude/Projects/taxahead",
        "<HOME>/Claude/Projects/taxahead-integration",
        "<HOME>/Claude/Projects/padsplit-reverification/pms",
    }


@pytest.mark.parametrize("command", [
    ["python3", "-c", "__import__('so'+'cket').socket().connect(('127.0.0.1',9))"],
    ["node", "-e", "require(['n','et'].join('')).connect(9,'127.0.0.1')"],
    ["python3", "-c", "__import__('pathlib').Path.home().joinpath('.codex','auth.json').read_text()"],
    ["node", "-e", "require('fs').readFileSync(require('os').homedir()+'/.codex/auth.json')"],
    ["ruby", "-e", "eval(ARGV[0])", "TCPSocket.new('127.0.0.1',9)"],
    ["perl", "-e", "do $ENV{HOME}.'/.codex/auth.json'"],
])
def test_source_or_eval_commands_are_not_authorized_by_lexical_allowlisting(command):
    """[RED][COMMAND-AUTHORITY] Source strings cannot become ALLOWED_LOCAL by token spelling."""
    api = _api()
    assert api.CodexExecAdapter._is_semantically_local_argv(command) is False


def test_protected_root_mutation_is_detected_by_adapter_pre_post_snapshots(tmp_path):
    """[RED][PROTECTED-SNAPSHOT] Every protected root hash is compared after the process."""
    api = _api()
    protected = tmp_path / "protected"
    protected.mkdir()
    protected_file = protected / "state.txt"
    protected_file.write_text("before\n", encoding="utf-8")
    request = replace(_request(api), protected_roots=[str(protected)])

    class MutatingProcess(FakeProcess):
        def communicate(self, input=None, timeout=None):
            protected_file.write_text("after\n", encoding="utf-8")
            return super().communicate(input=input, timeout=timeout)

    adapter, _ = _adapter(api, request, transcript=None)
    adapter.popen_factory = FakePopen(MutatingProcess(_transcript(request)))

    with pytest.raises(api.CodexAdapterBlockedError, match="protected.*snapshot|protected.*changed") as exc:
        adapter.execute(request)
    snapshots = exc.value.observation["protected_root_snapshots"]
    assert snapshots["before"][str(protected)]["root_hash"] != snapshots["after"][str(protected)][
        "root_hash"]


@pytest.mark.parametrize("scenario", ["preexisting", "missing", "mismatch", "jsonl_mismatch"])
def test_smoke_requires_provider_created_output_last_message_file(tmp_path, scenario):
    """[RED][SMOKE-FILE] Local output file is fresh, exact, in-root, and JSONL-consistent."""
    api = _api()
    output_bytes = b"CODEX_SMOKE_OK"
    preexisting = scenario == "preexisting"
    jsonl_final = "CODEX_SMOKE_DIFFERENT" if scenario == "jsonl_mismatch" else "CODEX_SMOKE_OK"
    if scenario == "missing":
        output_bytes = None
    elif scenario == "mismatch":
        output_bytes = b"CODEX_SMOKE_BAD"
    request, process, _ = _smoke_file_request(
        api, tmp_path, output_bytes=output_bytes, preexisting=preexisting,
        jsonl_final=jsonl_final,
    )
    adapter, _ = _adapter(api, request, transcript=process.stdout)
    adapter.popen_factory = FakePopen(process)

    with pytest.raises(
            api.CodexAdapterBlockedError,
            match="output-last-message|smoke.*file|final.*file|exact-output"):
        adapter.execute(request)


def test_smoke_success_receipt_binds_provider_output_file_bytes_and_jsonl(tmp_path):
    """[RED][SMOKE-FILE] Success records exact provider-created file hash and consistency proof."""
    api = _api()
    request, process, output_path = _smoke_file_request(
        api, tmp_path, output_bytes=b"CODEX_SMOKE_OK",
    )
    adapter, _ = _adapter(api, request, transcript=process.stdout)
    adapter.popen_factory = FakePopen(process)

    result = adapter.execute(request)

    expected_hash = hashlib.sha256(b"CODEX_SMOKE_OK").hexdigest()
    assert output_path.read_bytes() == b"CODEX_SMOKE_OK"
    assert result.raw_observation["output_last_message"] == {
        "path": str(output_path),
        "existed_before": False,
        "created_by_process": True,
        "bytes_sha256": expected_hash,
        "exact_bytes": True,
        "matches_jsonl_final": True,
    }


def test_installed_cli_041_uses_explicit_no_escalation_argv_for_the_sealed_model_matrix():
    """[RED][COMPAT] The installed CLI gets exact model/effort bytes, never --full-auto."""
    api = _api()
    expected = {
        ("smoke", "gpt-5.6-sol", "high"): [
            "/fake/codex", "--ask-for-approval", "never", "exec", "--cd", "/clone", "--model", "gpt-5.6-sol",
            "--sandbox", "read-only",
            "-c", "model_reasoning_effort=high", "--skip-git-repo-check", "--json",
            "--output-last-message", "/artifact/final.txt", "-",
        ],
        ("planner", "gpt-5.6-sol", "high"): [
            "/fake/codex", "--ask-for-approval", "never", "exec", "--cd", "/clone", "--model", "gpt-5.6-sol",
            "--sandbox", "read-only",
            "-c", "model_reasoning_effort=high", "--json",
            "--output-last-message", "/artifact/final.txt", "-",
        ],
        ("incumbent_coder", "gpt-5.6-terra", "high"): [
            "/fake/codex", "--ask-for-approval", "never", "exec", "--cd", "/clone", "--model", "gpt-5.6-terra",
            "--sandbox", "workspace-write",
            "-c", "model_reasoning_effort=high", "--json",
            "--output-last-message", "/artifact/final.txt", "-",
        ],
        ("challenger_coder", "gpt-5.6-luna", "medium"): [
            "/fake/codex", "--ask-for-approval", "never", "exec", "--cd", "/clone", "--model", "gpt-5.6-luna",
            "--sandbox", "workspace-write",
            "-c", "model_reasoning_effort=medium", "--json",
            "--output-last-message", "/artifact/final.txt", "-",
        ],
    }
    for (role, model, effort), argv in expected.items():
        packet = _packet()
        packet["task_identity"]["role"] = role
        packet["immutable_authority"]["requested_model"] = model
        packet["immutable_authority"]["requested_effort"] = effort
        packet["packet_hash"] = api.canonical_packet_hash(packet)
        packet["reverified_packet_hash"] = packet["packet_hash"]
        packet["immutable_authority"]["packet_hash"] = packet["packet_hash"]
        request = replace(
            _request(api, packet=packet), requested_model=model, requested_effort=effort,
        )
        adapter, _ = _adapter(api, request)

        assert adapter._argv(request) == argv


def test_smoke_contract_requires_a_fresh_private_tmp_cwd_exact_output_and_state_disclosure():
    """[RED][COMPAT] Smoke is read-only/no-tools and honestly discloses possible ~/.codex state."""
    api = _api()
    packet = _packet(clone="/private/tmp/codex-product-pilot-smoke-fixed", artifact="/artifact")
    packet["task_identity"] = {"ordinal": 0, "case_id": "smoke", "role": "smoke"}
    request = _request(
        api,
        clone="/private/tmp/codex-product-pilot-smoke-fixed",
        artifact="/artifact",
        packet=packet,
    )
    adapter, _ = _adapter(api, request)

    contract = adapter.smoke_contract(request)

    assert contract["cwd"].startswith("/private/tmp/codex-product-pilot-smoke-")
    assert contract["sandbox"] == "read-only"
    assert contract["approval"] == "never"
    assert contract["skip_git_repo_check"] is True
    assert contract["forbid_tool_events"] is True
    assert contract["expected_final_output"] == "CODEX_SMOKE_OK"
    assert contract["possible_codex_state_disclosure"] == (
        "codex-cli-0.41.0-has-no-ephemeral-and-may-write-under-~/.codex"
    )


@pytest.mark.parametrize("outcome", ["invalid_jsonl", "nonzero", "timeout"])
def test_all_outcomes_retain_redacted_raw_artifacts_with_default_secret_patterns(tmp_path, outcome):
    """[BEHAVIORAL] Abort evidence is retained and redacted even when parsing never succeeds."""
    api = _api()
    clone = tmp_path / "clone"
    artifact = tmp_path / "artifact"
    clone.mkdir()
    artifact.mkdir()
    request = _request(api, clone=str(clone), artifact=str(artifact),
                       packet=_packet(clone=str(clone), artifact=str(artifact)))
    process = FakeProcess("not-json API_KEY=sk-live-secret\n")
    if outcome == "nonzero":
        process.stdout = _transcript(request, terminal=_terminal(final="token=sk-live-secret"))
        process.returncode = 9
    elif outcome == "timeout":
        def timeout(*args, **kwargs):
            raise TimeoutError("fake timeout")
        process.communicate = timeout
    popen = FakePopen(process)
    adapter = api.CodexExecAdapter(
        cli_path="/fake/codex", popen_factory=popen, ledger=FakeLedger(),
        containment_probe=FakeContainment(receipt={
            "mechanism": "fake-os-policy", "version": "1",
            "policy_hash": hashlib.sha256(b"fake-policy").hexdigest(),
            "policy_bytes": b"fake-policy",
            "os_enforced": True, "writable_roots": [str(clone), str(artifact)],
            "bound_request_writable_roots": [str(clone), str(artifact)],
            "filesystem_violations": [], "network_attempts": [], "protected_root_changes": [],
        }), process_tree=FakeTree(), test_mode=True,
    )

    with pytest.raises(api.CodexAdapterBlockedError):
        adapter.execute(request)

    retained = {path.name: path.read_text() for path in artifact.iterdir() if path.is_file()}
    assert {"stdout.jsonl", "stderr.txt", "final.txt", "raw-observation.json"} <= set(retained)
    serialized = json.dumps(retained)
    assert "sk-live-secret" not in serialized
    assert "[REDACTED]" in serialized


@pytest.mark.product_mandatory
def test_product_mandatory_codex_exec_adapter_rejects_legacy_spec_in_test_mode():
    """[BEHAVIORAL][RED][SECURITY-ORACLE] Test injection never authorizes a legacy spec."""
    api = _api()
    packet = _packet()
    packet["immutable_authority"]["spec_sha256"] = api.LEGACY_TEST_SPEC_SHA256
    packet["packet_hash"] = api.canonical_packet_hash(packet)
    packet["reverified_packet_hash"] = packet["packet_hash"]
    packet["immutable_authority"]["packet_hash"] = packet["packet_hash"]
    request = _request(api, packet=packet)
    adapter, popen = _adapter(api, request)

    with pytest.raises(api.CodexAdapterBlockedError, match="spec|authority|pinned"):
        adapter.execute(request)

    assert popen.calls == []


def test_codex_exec_adapter_argv_complete_real_argv_is_accepted_by_the_installed_codex_binary(
        tmp_path):
    """[BEHAVIORAL] Regression test for the AC1/AC2 --ask-for-approval-after-exec bug.

    Builds CodexExecAdapter._argv()'s REAL, complete, current output shape -- read
    directly from the method body, not inferred from spec prose or a stripped-down
    subset -- for the "smoke" role (read-only sandbox), which is the combination that
    makes this builder emit every flag it produces, including the conditional
    --skip-git-repo-check. execute() calls `argv = self._argv(request)` then
    `self.popen_factory(argv, ...)` (~line 717/733), making this the ACTUAL
    real-execution call site (unlike _effective_codex_argv, which is bookkeeping only)
    -- see spec Context. The trailing bare "-" this builder always appends is the
    stdin-prompt/task marker (`codex exec --help` describes [PROMPT] as: "If not
    provided as an argument (or if `-` is used), instructions are read from stdin"), so
    per AC4 it is replaced with --help rather than appended after it (empirically
    confirmed equivalent either way against the real binary, but replacing is the more
    literal "substitute the prompt/task argument" reading). The resulting argv is
    executed via subprocess.run against the REAL installed codex binary -- never the
    fake/mock CLI (FakePopen/FakeProcess) the rest of this suite uses; those fakes are
    still passed to the constructor below only because they are required constructor
    arguments -- they are never invoked, since this test calls `_argv()` and then
    `subprocess.run(...)` directly, never `adapter.execute()`.

    This MUST currently fail: --ask-for-approval is still placed after the `exec` token
    in this builder's output, and the real codex-cli 0.41.0 binary rejects that argv
    with exit code 2. It MUST pass once AC2's fix moves the pair to precede `exec`.

    The assertions below use index()-based adjacency checks (never an absolute-position
    index past argv[0] / argv[-1]) precisely so this test does not itself become a third
    "hardcodes the buggy token order" test like the two AC2 already names for the Coder
    to fix -- the subprocess exit-code assertion is the one thing that must flip
    red -> green when the reorder lands, not a frozen positional snapshot of the bug.
    """
    api = _api()
    codex_path = shutil.which("codex")
    assert codex_path, "codex binary must be resolvable on PATH for this real-binary test"
    clone = str(tmp_path / "clone")
    artifact = str(tmp_path / "artifact")
    Path(clone).mkdir()
    Path(artifact).mkdir()
    packet = _packet(clone=clone, artifact=artifact)
    packet["task_identity"] = {"ordinal": 0, "case_id": "smoke", "role": "smoke"}
    packet["packet_hash"] = api.canonical_packet_hash(packet)
    packet["reverified_packet_hash"] = packet["packet_hash"]
    packet["immutable_authority"]["packet_hash"] = packet["packet_hash"]
    request = _request(api, clone=clone, artifact=artifact, packet=packet)
    adapter = api.CodexExecAdapter(
        cli_path=codex_path,
        popen_factory=FakePopen(FakeProcess("unused")),
        ledger=FakeLedger(), containment_probe=FakeContainment(), process_tree=FakeTree(),
        test_mode=True,
    )

    argv = adapter._argv(request)

    assert len(argv) == 17, "unexpected flag count -- builder's real shape has changed: %r" % (argv,)
    assert argv[0] == codex_path
    assert argv[argv.index("--cd") + 1] == clone
    assert argv[argv.index("--model") + 1] == request.requested_model
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[argv.index("--ask-for-approval") + 1] == "never"
    assert argv[argv.index("-c") + 1] == "model_reasoning_effort=" + request.requested_effort
    assert "--skip-git-repo-check" in argv
    assert "--json" in argv
    assert argv[argv.index("--output-last-message") + 1] == request.output_last_message_path
    assert argv[-1] == "-"

    probe_argv = argv[:-1] + ["--help"]

    result = subprocess.run(
        probe_argv, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 0, (
        "expected the REAL codex binary to accept CodexExecAdapter._argv()'s complete, "
        "current frozen argv (trailing stdin-prompt marker '-' replaced with --help) "
        "once --ask-for-approval correctly precedes exec; got exit code %r, "
        "stdout=%r, stderr=%r" % (result.returncode, result.stdout, result.stderr)
    )
