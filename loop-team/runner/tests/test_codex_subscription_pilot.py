"""[BEHAVIORAL] Fake-only pilot controller contract.

The controller must keep dry runs inert and allow exactly the sealed ten-call
pilot after every authority, test, packet, and cap gate has passed.
"""
from __future__ import annotations

import importlib
import hashlib
import inspect
import json
import os
import signal
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
LOOP_TEAM_DIR = REPO_ROOT / "loop-team"
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
    return importlib.import_module("runner.codex_subscription_pilot")


def _materials():
    api = _api()
    call_plan = api.EXACT_CALL_PLAN
    def make_packet(ordinal, call):
        contents = {name: "%s-%s\n" % (ordinal, name) for name in (
            "prompt", "plan", "oracle", "test", "dependency", "preprobe")}
        clone_entries = [{"path": "baseline.txt", "sha256": hashlib.sha256(
            ("clone-%s" % ordinal).encode()).hexdigest()}]
        source_entries = [{"path": "source.txt", "sha256": hashlib.sha256(
            ("source-%s" % ordinal).encode()).hexdigest()}]
        packet = {
            "packet_hash": "0" * 64, "reverified_packet_hash": "0" * 64,
            "clone_tree_hash": api._canonical_hash(clone_entries),
            "reverified_clone_tree_hash": api._canonical_hash(clone_entries),
            "baseline_tree_hash": api._canonical_hash(clone_entries),
            "source_tree_hash": api._canonical_hash(source_entries),
            "clone_tree_entries": clone_entries, "source_tree_entries": source_entries,
            "task_identity": api._task_identity(ordinal, call),
            "requested_model": call[1], "requested_effort": call[2],
            "cwd": "/sealed/clone/%s" % ordinal,
            "artifact_root": "/sealed/artifact/%s" % ordinal,
            "writable_roots": ["/sealed/clone/%s" % ordinal,
                               "/sealed/artifact/%s" % ordinal],
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
        "schema": "pace_manifest.v1", "manifest_hash": "0" * 64,
        "call_plan": call_plan, "caps": CAPS,
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
        "smoke_packet": execution_packets[0],
    }
    manifest["manifest_hash"] = api.manifest_hash(manifest)
    approval = {
        "schema": "experiment_approval.v2", "execution_mode": "codex_subscription",
        "manifest_hash": manifest["manifest_hash"], "user_created": True,
        "approval_hash": "0" * 64,
        "human_confirmation": {
            "schema": "user_confirmation.v1", "confirmed": True,
            "spec_sha256": SPEC_SHA256, "approval_hash": "0" * 64,
            "manifest_hash": manifest["manifest_hash"],
            "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
        },
        "caps": CAPS, "call_plan": call_plan,
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
    }
    approval["approval_hash"] = api.approval_hash(approval)
    approval["human_confirmation"]["approval_hash"] = approval["approval_hash"]
    return approval, manifest, execution_packets[1:]


def _tree_entries(root):
    root = Path(root)
    paths = [root, *sorted(root.rglob("*"), key=lambda path: path.as_posix())]
    entries = []
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        mode = path.lstat().st_mode & 0o7777
        if path.is_dir():
            entries.append({
                "root": root.as_posix(), "path": relative, "mode": mode,
                "type": "directory", "size": 0,
            })
        else:
            content = path.read_bytes()
            entries.append({
                "root": root.as_posix(), "path": relative, "mode": mode,
                "type": "file", "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
    return entries


def _deep_smoke_packet(api, smoke_root, artifact_root, source_root):
    smoke_root = Path(smoke_root)
    artifact_root = Path(artifact_root)
    source_root = Path(source_root)
    smoke_root.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    (smoke_root / "sealed-input.txt").write_text("smoke input\n", encoding="utf-8")
    (source_root / "source.txt").write_text("sealed source\n", encoding="utf-8")
    prompt = (
        "Return exactly CODEX_SMOKE_OK. Do not use tools, run commands, edit files, "
        "or contact external services.\n"
    )
    contents = {
        "prompt": prompt, "plan": "read-only smoke plan\n",
        "oracle": "exact CODEX_SMOKE_OK\n", "test": "no tools or edits\n",
        "dependency": "codex-cli 0.41.0\n", "preprobe": "seatbelt PASS\n",
    }
    material_root = artifact_root / "materials"
    material_root.mkdir()
    materials = {}
    for name, content in contents.items():
        path = material_root / (name + ".txt")
        path.write_text(content, encoding="utf-8")
        materials[name] = {
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    clone_entries = _tree_entries(smoke_root)
    source_entries = _tree_entries(source_root)
    cwd = str(smoke_root)
    artifact = str(artifact_root)
    packet = {
        "packet_hash": "0" * 64,
        "reverified_packet_hash": "0" * 64,
        "clone_tree_hash": api._canonical_hash(clone_entries),
        "reverified_clone_tree_hash": api._canonical_hash(clone_entries),
        "baseline_tree_hash": api._canonical_hash(clone_entries),
        "source_tree_hash": api._canonical_hash(source_entries),
        "clone_tree_entries": clone_entries,
        "source_tree_entries": source_entries,
        "source_root": str(source_root),
        "task_identity": {"ordinal": 0, "case_id": "smoke", "role": "smoke"},
        "requested_model": "gpt-5.6-sol",
        "requested_effort": "high",
        "cwd": cwd,
        "artifact_root": artifact,
        "writable_roots": [cwd, artifact],
        "ordered_argv": [[
            "/opt/homebrew/bin/codex", "exec", "--cd", cwd,
            "--model", "gpt-5.6-sol", "--sandbox", "read-only",
            "--ask-for-approval", "never", "-c", "model_reasoning_effort=high",
            "--skip-git-repo-check", "--json", "--output-last-message",
            artifact + "/final.txt", "-",
        ]],
        "environment": {"LANG": "C", "PATH": "/usr/bin"},
        "allowed_write_targets": [],
        "allowed_files": [material["path"] for material in materials.values()],
        "sealed_materials": materials,
        "execution_sandbox": "read-only",
        "approval_policy": "never",
        "expected_final_output": "CODEX_SMOKE_OK",
        "forbid_tool_events": True,
        "forbid_edits": True,
        "smoke_prompt_policy": "read-only-no-tools-no-edits-exact-output",
    }
    sealed = api.packet_hash(packet)
    packet["packet_hash"] = packet["reverified_packet_hash"] = sealed
    return packet


class FakeProductionPreflightPopen:
    def __init__(self, seatbelt_payload):
        self.seatbelt_payload = seatbelt_payload
        self.calls = []

    def __call__(self, argv, **kwargs):
        from runner.tests.test_codex_exec_adapter import FakeProcess

        self.calls.append((list(argv), dict(kwargs)))
        if argv == ["/opt/homebrew/bin/codex", "--version"]:
            return FakeProcess("codex-cli 0.41.0\n")
        payload = json.loads(json.dumps(self.seatbelt_payload))
        if "--full-auto" not in argv:
            payload["allowed_cwd_write"] = {
                "exit_code": 1,
                "stdout": "",
                "stderr": "Operation not permitted",
                "errno": "EPERM",
            }
        return FakeProcess(json.dumps(payload) + "\n")


def _passing_production_preflight(tmp_path):
    adapter_api = importlib.import_module("runner.codex_exec_adapter")
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
    fake = FakeProductionPreflightPopen({
        "allowed_cwd_write": {"exit_code": 0, "stdout": "WRITE_ALLOWED", "stderr": ""},
        "denied_protected_write": denied,
        "denied_protected_writes": [dict(denied), dict(denied), dict(denied)],
        "denied_network": denied,
    })
    cwd = tmp_path / "preflight-cwd"
    cwd.mkdir()
    preflight = adapter_api.ProductionSeatbeltPreflight(
        popen_factory=fake,
        test_mode=True,
        artifact_dir=tmp_path / "preflight-artifacts",
        model_cache_path=model_cache,
    )
    return preflight, fake, cwd


def _write_production_cli_authority(api, tmp_path, *, confirmed):
    approval, manifest, packets = _materials()
    manifest["frozen_packets"] = packets
    manifest["required_test_receipt"] = _required_test_receipt()
    manifest["manifest_hash"] = api.manifest_hash(manifest)
    approval["manifest_hash"] = manifest["manifest_hash"]
    approval["human_confirmation"]["manifest_hash"] = manifest["manifest_hash"]
    approval["human_confirmation"]["confirmed"] = confirmed
    approval["approval_hash"] = api.approval_hash(approval)
    approval["human_confirmation"]["approval_hash"] = approval["approval_hash"]
    approval_path = tmp_path / "approval.json"
    manifest_path = tmp_path / "manifest.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return approval, manifest, approval_path, manifest_path


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def execute(self, packet):
        self.calls.append(packet)
        result = {"promotion_eligible": False}
        task = packet.get("task_identity", {})
        if task.get("role") == "planner":
            plan = {
                "schema": "product_planner_output.v1",
                "status": "PLAN_PASS",
                "case_id": task["case_id"],
                "allowed_paths": ["src/%s.ts" % task["case_id"].lower()],
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


REQUIRED_GATE_MODULES = [
    "loop-team/runner/tests/test_codex_subscription_adapter.py",
    "loop-team/runner/tests/test_codex_exec_adapter.py",
    "loop-team/runner/tests/test_codex_subscription_pilot.py",
    "loop-team/runner/tests/test_experiment_execution_contract.py",
    "loop-team/experiments/test_model_routing_pace_contract.py",
    "loop-team/evals/test_model_routing_evals_contract.py",
]

REQUIRED_COMPATIBILITY_ASSERTIONS = [
    "codex_cli_041_argv_and_effort_domain",
    "installed_and_current_jsonl_usage_schemas",
    "session_configured_identity_and_unknown_stop",
    "smoke_read_only_no_tools_and_codex_state_disclosure",
    "no_provider_preflight_before_popen",
    "codex_subscription_has_no_usd_accounting",
]


def _required_test_receipt():
    return {
        "all_required_fake_cli_tests_passed": True,
        "executed_test_modules": REQUIRED_GATE_MODULES,
        "compatibility_assertions": REQUIRED_COMPATIBILITY_ASSERTIONS,
    }


def test_non_dry_run_constructs_the_adapter_only_after_exact_confirmation_tests_packets_and_caps_pass():
    """[BEHAVIORAL] Valid authority starts the exact sealed ten-call pilot, never a promotion."""
    api = _api()
    approval, manifest, packets = _materials()
    constructed = []

    def factory():
        adapter = FakeAdapter()
        constructed.append(adapter)
        return adapter

    pilot = api.CodexSubscriptionPilot(adapter_factory=factory, test_mode=True)
    blocked_inputs = [
        ({**approval, "human_confirmation": {**approval["human_confirmation"], "confirmed": False}}, manifest,
         _required_test_receipt(), packets),
        ({**approval, "caps": {**CAPS, "combined_calls": 9}}, manifest,
         _required_test_receipt(), packets),
        (approval, manifest, {"all_required_fake_cli_tests_passed": False}, packets),
        (approval, manifest, _required_test_receipt(), packets[:-1]),
    ]
    for bad_approval, bad_manifest, receipt, bad_packets in blocked_inputs:
        with pytest.raises(api.PilotBlockedError):
            pilot.run(approval=bad_approval, manifest=bad_manifest,
                      required_test_receipt=receipt, frozen_packets=bad_packets, dry_run=False)
    assert constructed == []

    report = pilot.run(approval=approval, manifest=manifest,
                       required_test_receipt=_required_test_receipt(),
                       frozen_packets=packets, dry_run=False)
    assert len(constructed) == 1
    assert len(constructed[0].calls) == 10
    assert report["pace_status"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert report["promotion_eligible"] is False
    assert report["routing_recommendation"] is None


def test_non_dry_controller_rejects_shallow_packet_strings_before_constructing_an_adapter():
    """[BEHAVIORAL] Controller callables accept byte-sealed packets, not identity strings alone."""
    api = _api()
    approval, manifest, packets = _materials()
    constructed = []
    pilot = api.CodexSubscriptionPilot(
        adapter_factory=lambda: constructed.append(FakeAdapter()) or constructed[-1],
        test_mode=True,
    )
    shallow_packets = [{key: value for key, value in packet.items() if key in {
        "packet_hash", "clone_tree_hash", "reverified_packet_hash",
        "reverified_clone_tree_hash"}} for packet in packets]

    with pytest.raises(api.PilotBlockedError):
        pilot.run(
            approval=approval,
            manifest=manifest,
            required_test_receipt=_required_test_receipt(),
            frozen_packets=shallow_packets,
            dry_run=False,
    )
    assert constructed == []


def test_non_dry_controller_requires_every_adapter_and_affected_runner_test_module():
    """[BEHAVIORAL] A boolean test receipt cannot hide a skipped adapter contract module."""
    api = _api()
    approval, manifest, packets = _materials()
    constructed = []
    pilot = api.CodexSubscriptionPilot(
        adapter_factory=lambda: constructed.append(FakeAdapter()) or constructed[-1],
        test_mode=True,
    )
    with pytest.raises(api.PilotBlockedError):
        pilot.run(
            approval=approval,
            manifest=manifest,
            required_test_receipt={
                "all_required_fake_cli_tests_passed": True,
                "executed_test_modules": REQUIRED_GATE_MODULES[1:],
            },
            frozen_packets=packets,
            dry_run=False,
        )
    assert constructed == []


def test_dry_run_does_not_construct_an_adapter_or_launch_a_fake_process():
    """[BEHAVIORAL] Dry-run can validate sealed materials but has no execution boundary."""
    api = _api()
    approval, manifest, packets = _materials()
    constructed = []
    pilot = api.CodexSubscriptionPilot(
        adapter_factory=lambda: constructed.append(FakeAdapter()), test_mode=True,
    )

    report = pilot.run(approval=approval, manifest=manifest,
                       required_test_receipt=_required_test_receipt(),
                       frozen_packets=packets, dry_run=True)

    assert constructed == []
    assert report["pace_status"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert report["promotion_eligible"] is False


def test_spec_required_pilot_command_path_exposes_the_authorized_execution_contract():
    """[BEHAVIORAL] The specified runner path is an executable command, not an import-only module."""
    command = [sys.executable, str(REPO_ROOT / "loop-team/runner/codex_subscription_pilot.py"), "--help"]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert "--run-id" in completed.stdout
    assert "--approval" in completed.stdout
    assert "--manifest" in completed.stdout
    assert "--execute-smoke-and-pilot" in completed.stdout


def test_cli_executes_the_sealed_fake_ten_call_pilot_through_its_factory_and_aborts_without_config(tmp_path):
    """[BEHAVIORAL] The CLI owns concrete boundary construction; fake injection is explicit test mode."""
    approval, manifest, packets = _materials()
    sealed_fake = tmp_path / "sealed-fake-config.json"
    sealed_fake.write_text(json.dumps({
        "schema": "codex_subscription_pilot.fake_config.v1",
        "test_mode": True,
        "approval": approval,
        "manifest": manifest,
        "required_test_receipt": _required_test_receipt(),
        "frozen_packets": packets,
    }), encoding="utf-8")
    command = [
        sys.executable,
        str(REPO_ROOT / "loop-team/runner/codex_subscription_pilot.py"),
        "--execute-smoke-and-pilot",
        "--sealed-fake-config", str(sealed_fake),
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["calls_started"] == 10

    missing = subprocess.run(
        command[:3], cwd=REPO_ROOT, text=True, capture_output=True, check=False,
    )
    assert missing.returncode == 2
    assert "sealed fake" in missing.stderr.lower()


def test_exact_041_matrix_replaces_ultra_while_retaining_the_fixed_ten_call_controller():
    """[RED][COMPAT] The one smoke, three planners, and six coder slots remain unchanged."""
    api = _api()
    assert api.EXACT_CALL_PLAN == [
        ["smoke", "gpt-5.6-sol", "high"],
        *[["planner", "gpt-5.6-sol", "high"] for _ in range(3)],
        *[["incumbent_coder", "gpt-5.6-terra", "high"] for _ in range(3)],
        *[["challenger_coder", "gpt-5.6-luna", "medium"] for _ in range(3)],
    ]
    assert len(api.EXACT_CALL_PLAN) == 10


def test_missing_identity_or_usage_stops_after_the_started_call_without_substituting_zero():
    """[RED][COMPAT] UNKNOWN observations abort the pilot before another comparative call."""
    api = _api()
    approval, manifest, packets = _materials()

    class UnknownFirstAdapter:
        def __init__(self):
            self.calls = []

        def execute(self, packet):
            self.calls.append(packet)
            return {
                "promotion_eligible": False,
                "raw_observation": {
                    "configured_model_id": "UNKNOWN",
                    "configured_reasoning_effort": "UNKNOWN",
                    "usage": "UNKNOWN",
                },
            }

    adapter = UnknownFirstAdapter()
    pilot = api.CodexSubscriptionPilot(adapter_factory=lambda: adapter, test_mode=True)
    with pytest.raises(api.PilotBlockedError, match="UNKNOWN"):
        pilot.run(
            approval=approval,
            manifest=manifest,
            required_test_receipt=_required_test_receipt(),
            frozen_packets=packets,
            dry_run=False,
        )
    assert len(adapter.calls) == 1


def test_observed_identity_mismatch_aborts_comparative_scoring_before_the_next_call():
    """[RED][COMPAT] Requested identity is never copied into an observed identity field."""
    api = _api()
    approval, manifest, packets = _materials()

    class MismatchAdapter:
        def __init__(self):
            self.calls = []

        def execute(self, packet):
            self.calls.append(packet)
            return {
                "promotion_eligible": False,
                "raw_observation": {
                    "configured_model_id": "gpt-5.6-terra",
                    "configured_reasoning_effort": "high",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            }

    adapter = MismatchAdapter()
    pilot = api.CodexSubscriptionPilot(adapter_factory=lambda: adapter, test_mode=True)
    with pytest.raises(api.PilotBlockedError, match="observed.*identity"):
        pilot.run(
            approval=approval,
            manifest=manifest,
            required_test_receipt=_required_test_receipt(),
            frozen_packets=packets,
            dry_run=False,
        )
    assert len(adapter.calls) == 1


def test_no_provider_preflight_executes_all_requested_modes_and_blocks_before_adapter_factory(
        monkeypatch, tmp_path):
    """[BEHAVIORAL][COMPAT] Concrete local Seatbelt rejection blocks every provider start."""
    api = _api()
    adapter_api = importlib.import_module("runner.codex_exec_adapter")
    constructed = []
    model_cache = tmp_path / "models_cache.json"
    model_cache.write_text(json.dumps({
        "etag": '"fresh-model-cache-etag"',
        "models": [
            {"slug": "gpt-5.6-sol"},
            {"slug": "gpt-5.6-terra"},
            {"slug": "gpt-5.6-luna"},
        ],
    }), encoding="utf-8")

    class FakeProcess:
        def __init__(self, stdout, stderr="", returncode=0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

        def communicate(self, timeout=None):
            return self.stdout, self.stderr

    class NestedSandboxPopen:
        def __init__(self):
            self.calls = []

        def __call__(self, argv, **kwargs):
            self.calls.append((list(argv), dict(kwargs)))
            if argv == ["/opt/homebrew/bin/codex", "--version"]:
                return FakeProcess("codex-cli 0.41.0\n")
            return FakeProcess(
                "",
                stderr="sandbox_apply: Operation not permitted\n",
                returncode=70,
            )

    fake_popen = NestedSandboxPopen()
    concrete_preflight = adapter_api.ProductionSeatbeltPreflight(
        popen_factory=fake_popen,
        test_mode=True,
        artifact_dir=tmp_path / "preflight-artifacts",
        model_cache_path=model_cache,
    )
    monkeypatch.setattr(api, "ProductionSeatbeltPreflight", lambda: concrete_preflight)

    pilot = api.CodexSubscriptionPilot(
        adapter_factory=lambda: constructed.append(object()), test_mode=True,
    )
    with pytest.raises(TypeError):
        pilot.run_local_no_provider_preflight(lambda: {"status": "PASS"})

    report = pilot.run_local_no_provider_preflight()

    assert report["status"] == "PRECHECK_FAILED"
    assert report["failure_code"] == "PRODUCTION_PREFLIGHT_FAILED"
    assert report["blocker_class"] == "local_compatibility_precheck"
    assert report["provider_process_starts"] == 0
    assert constructed == []
    assert {
        ("gpt-5.6-sol", "high", "read-only"),
        ("gpt-5.6-sol", "high", "workspace-write"),
        ("gpt-5.6-terra", "high", "workspace-write"),
        ("gpt-5.6-luna", "medium", "workspace-write"),
    } == {(check["model"], check["effort"], check["sandbox"])
          for check in report["checks"]}
    assert all(check["argv_config_syntax"] == "PRECHECK_FAILED"
               for check in report["checks"])
    assert all(check["seatbelt_containment"] == "PRECHECK_FAILED"
               for check in report["checks"])
    assert all(len(check["probe_receipt_sha256"]) == 64 for check in report["checks"])

    seatbelt_calls = [call for call in fake_popen.calls if "seatbelt" in call[0]]
    assert len(seatbelt_calls) == 4
    for check, (argv, kwargs) in zip(report["checks"], seatbelt_calls):
        assert check["argv"] == argv
        assert argv[:7] == [
            "/opt/homebrew/bin/codex", "--model", check["model"], "-c",
            "model_reasoning_effort=" + check["effort"],
            "debug", "seatbelt",
        ]
        assert "--sandbox" not in argv
        if check["sandbox"] == "read-only":
            assert "--full-auto" not in argv
            assert argv[7] == "--"
        else:
            assert argv[7:9] == ["--full-auto", "--"]
        assert kwargs["shell"] is False
        assert kwargs["start_new_session"] is True


def test_test_gate_rejects_missing_041_compatibility_assertions_before_constructing_the_adapter():
    """[RED][COMPAT] A green boolean cannot conceal skipped installed-CLI assertions."""
    api = _api()
    approval, manifest, packets = _materials()
    constructed = []
    pilot = api.CodexSubscriptionPilot(
        adapter_factory=lambda: constructed.append(FakeAdapter()) or constructed[-1],
        test_mode=True,
    )
    receipt = _required_test_receipt()
    receipt.pop("compatibility_assertions")

    with pytest.raises(api.PilotBlockedError, match="compatibility assertions"):
        pilot.run(
            approval=approval,
            manifest=manifest,
            required_test_receipt=receipt,
            frozen_packets=packets,
            dry_run=False,
        )

    assert constructed == []


def test_callback_driven_preflight_api_is_not_a_production_authority_surface():
    """[RED][PRODUCTION-PREFLIGHT] Callers cannot return booleans that self-authorize Seatbelt."""
    api = _api()
    signature = inspect.signature(api.CodexSubscriptionPilot.run_local_no_provider_preflight)

    assert "local_runner" not in signature.parameters


def test_production_preflight_receipt_checks_binary_cache_matrix_and_defers_model_resolution(
        tmp_path):
    """[RED][PRODUCTION-PREFLIGHT] Local compatibility PASS is complete but not smoke identity."""
    api = _api()
    adapter_api = importlib.import_module("runner.codex_exec_adapter")
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
    fake = FakeProductionPreflightPopen({
        "allowed_cwd_write": {"exit_code": 0, "stdout": "WRITE_ALLOWED", "stderr": ""},
        "denied_protected_write": denied,
        "denied_protected_writes": [dict(denied), dict(denied), dict(denied)],
        "denied_network": {
            "exit_code": 1, "stdout": "", "stderr": "Operation not permitted",
            "errno": "EPERM",
        },
    })
    preflight = adapter_api.ProductionSeatbeltPreflight(
        popen_factory=fake,
        test_mode=True,
        artifact_dir=tmp_path / "preflight-artifacts",
        model_cache_path=model_cache,
    )

    receipt = preflight.run(
        cwd="/private/tmp/codex-product-pilot-preflight",
        protected_root="<HOME>/Claude/Projects/taxahead",
    )

    assert receipt["status"] == "PASS"
    assert receipt["provider_process_starts"] == 0
    assert receipt["binary"] == {
        "path": "/opt/homebrew/bin/codex",
        "version": "codex-cli 0.41.0",
        "status": "PASS",
    }
    assert receipt["accepted_reasoning_efforts"] == ["minimal", "low", "medium", "high"]
    assert receipt["model_cache"]["etag"] == '"fresh-model-cache-etag"'
    assert receipt["model_cache"]["fresh"] is True
    assert receipt["model_cache"]["target_slugs"] == {
        "gpt-5.6-sol": True, "gpt-5.6-terra": True, "gpt-5.6-luna": True,
    }
    assert receipt["model_resolution"] == "UNKNOWN_UNTIL_SMOKE"
    assert len(receipt["checks"]) == 4
    assert all(check["argv_config_syntax"] == "PASS" for check in receipt["checks"])
    assert all(check["seatbelt_containment"] == "PASS" for check in receipt["checks"])
    assert {
        (check["model"], check["effort"], check["sandbox"])
        for check in receipt["checks"]
    } == {
        ("gpt-5.6-sol", "high", "read-only"),
        ("gpt-5.6-sol", "high", "workspace-write"),
        ("gpt-5.6-terra", "high", "workspace-write"),
        ("gpt-5.6-luna", "medium", "workspace-write"),
    }
    seatbelt_argv = [argv for argv, _ in fake.calls if "seatbelt" in argv]
    for argv in seatbelt_argv:
        check = next(check for check in receipt["checks"] if check["argv"] == argv)
        assert argv[:7] == [
            "/opt/homebrew/bin/codex", "--model", check["model"], "-c",
            "model_reasoning_effort=" + check["effort"], "debug", "seatbelt",
        ]
        assert "--sandbox" not in argv
        if check["sandbox"] == "read-only":
            assert "--full-auto" not in argv
            assert argv[7] == "--"
        else:
            assert argv[7:9] == ["--full-auto", "--"]
    assert receipt["promotion_boundary"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert receipt["usd_cost"] is None


def test_preflight_only_cli_constructs_concrete_preflight_and_emits_json_without_an_adapter(
        monkeypatch, capsys):
    """[RED][PRODUCTION-PREFLIGHT] CLI preflight is executable, local, and provider-inert."""
    api = _api()
    constructed = []
    receipt = {
        "status": "PASS",
        "provider_process_starts": 0,
        "model_resolution": "UNKNOWN_UNTIL_SMOKE",
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
        "usd_cost": None,
    }

    class FakeConcretePreflight:
        def __init__(self):
            constructed.append("preflight")

        def run(self):
            return receipt

    def forbidden_adapter(*args, **kwargs):
        raise AssertionError("--preflight-only constructed a provider adapter")

    monkeypatch.setattr(api, "ProductionSeatbeltPreflight", FakeConcretePreflight, raising=False)
    monkeypatch.setattr(api, "_SealedFakeAdapter", forbidden_adapter)

    assert list(inspect.signature(api.main).parameters) == ["argv"]
    assert api.main(["--preflight-only"]) == 0
    assert constructed == ["preflight"]
    assert json.loads(capsys.readouterr().out) == receipt


@pytest.mark.parametrize("violation", [
    "cwd_prefix",
    "sandbox",
    "approval",
    "exact_output",
    "tool_events",
    "edits",
    "argv",
    "prompt_policy",
])
def test_smoke_packet_contract_is_unconditional_and_rejected_before_execution(tmp_path, violation):
    """[RED][SMOKE-PACKET] Smoke kind alone activates every read-only/no-tools invariant."""
    api = _api()
    prefix = (
        "codex-product-pilot-not-smoke-" if violation == "cwd_prefix"
        else "codex-product-pilot-smoke-"
    )
    with tempfile.TemporaryDirectory(prefix=prefix, dir="/private/tmp") as smoke_root:
        packet = _deep_smoke_packet(
            api,
            smoke_root,
            tmp_path / "artifact",
            tmp_path / "source",
        )
        if violation == "sandbox":
            packet["execution_sandbox"] = "workspace-write"
        elif violation == "approval":
            packet["approval_policy"] = "on-request"
        elif violation == "exact_output":
            packet["expected_final_output"] = "CODEX_SMOKE_ALMOST"
        elif violation == "tool_events":
            packet["forbid_tool_events"] = False
        elif violation == "edits":
            packet["forbid_edits"] = False
            packet["allowed_write_targets"] = [str(Path(smoke_root) / "edit.py")]
        elif violation == "argv":
            packet["ordered_argv"][0].remove("--skip-git-repo-check")
        elif violation == "prompt_policy":
            prompt = packet["sealed_materials"]["prompt"]
            Path(prompt["path"]).write_text("Return CODEX_SMOKE_OK.\n", encoding="utf-8")
            prompt["sha256"] = hashlib.sha256(Path(prompt["path"]).read_bytes()).hexdigest()
        packet["packet_hash"] = packet["reverified_packet_hash"] = api.packet_hash(packet)
        pilot = api.CodexSubscriptionPilot(adapter_factory=lambda: FakeAdapter(), test_mode=True)

        with pytest.raises(api.PilotBlockedError, match="smoke"):
            pilot._validate_packet(packet, 0, api.EXACT_CALL_PLAN[0])


def test_preflight_matrix_argv_binds_requested_model_and_effort_before_debug_seatbelt(tmp_path):
    """[RED][PREFLIGHT-ARGV] Cache catalogs models; argv binds each requested local probe."""
    api = _api()
    preflight, _, cwd = _passing_production_preflight(tmp_path)

    receipt = preflight.run(
        cwd=str(cwd),
        protected_root="<HOME>/Claude/Projects/taxahead",
    )

    assert receipt["status"] == "PASS"
    assert receipt["model_cache"]["target_slugs"] == {
        "gpt-5.6-sol": True, "gpt-5.6-terra": True, "gpt-5.6-luna": True,
    }
    assert receipt["model_resolution"] == "UNKNOWN_UNTIL_SMOKE"
    for check in receipt["checks"]:
        argv = check["argv"]
        debug_index = argv.index("debug")
        model_flags = [flag for flag in ("-m", "--model") if flag in argv[:debug_index]]
        assert len(model_flags) == 1
        model_flag = model_flags[0]
        assert argv[argv.index(model_flag) + 1] == check["model"]
        assert argv.index("-c") < debug_index
        assert argv[argv.index("-c") + 1] == "model_reasoning_effort=" + check["effort"]
        assert "--sandbox" not in argv
        assert ("--full-auto" in argv) is (check["sandbox"] == "workspace-write")
        policy = json.loads(check["policy_bytes"])
        assert policy["sandbox"] == check["sandbox"]


def _normal_pytest_output(passed, *, duration="0.25"):
    return "." * min(passed, 72) + f" [100%]\n{passed} passed in {duration}s\n"


def _normal_gate_fake(api, *, combined_passed, module_counts, overrides=None):
    modules = list(api.REQUIRED_GATE_MODULE_ORDER)
    combined_command = ["python3", "-m", "pytest", *modules, "-q"]
    commands = [
        combined_command,
        *[["python3", "-m", "pytest", module, "-q"] for module in modules],
        list(api.RequiredTestGateRunner.PRODUCT_COMMAND),
    ]
    responses = [(_normal_pytest_output(combined_passed), "", 0)] + [
        (_normal_pytest_output(module_counts[module]), "", 0) for module in modules
    ] + [(
        "\n".join(
            "loop-team/runner/tests/test_codex_subscription_pilot.py::%s PASSED [100%%]" % name
            for name in api.REQUIRED_PRODUCT_MANDATORY_TESTS
        ) + "\n%d passed in 0.25s\n" % len(api.REQUIRED_PRODUCT_MANDATORY_TESTS),
        "", 0,
    )]
    for index, response in (overrides or {}).items():
        responses[index] = response
    calls = []

    class Process:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

        def communicate(self, timeout=None):
            return self.stdout, self.stderr

    def fake_popen(argv, **kwargs):
        index = len(calls)
        assert index < len(commands), "test-gate runner started a ninth subprocess"
        assert list(argv) == commands[index]
        calls.append((list(argv), dict(kwargs)))
        return Process(*responses[index])

    return fake_popen, calls, commands, responses


def test_required_test_gate_accepts_normal_combined_and_per_module_pytest_output(tmp_path):
    """[RED][TEST-GATE] Genuine pytest summaries produce seven byte-bound receipts."""
    api = _api()
    modules = list(api.REQUIRED_GATE_MODULE_ORDER)
    assert modules == REQUIRED_GATE_MODULES
    module_counts = {
        module: count for module, count in zip(modules, (11, 17, 23, 29, 37, 55))
    }
    combined_passed = sum(module_counts.values())
    fake_popen, calls, commands, responses = _normal_gate_fake(
        api, combined_passed=combined_passed, module_counts=module_counts,
    )

    receipt = api.RequiredTestGateRunner(
        popen_factory=fake_popen, test_mode=True, artifact_dir=tmp_path,
    ).run()

    assert [call[0] for call in calls] == commands
    assert all(call[1]["shell"] is False for call in calls)
    assert receipt["all_required_fake_cli_tests_passed"] is True
    assert receipt["command"] == commands[0]
    assert receipt["command_sha256"] == api._canonical_hash(commands[0])
    assert receipt["stdout_sha256"] == hashlib.sha256(responses[0][0].encode()).hexdigest()
    assert receipt["stderr_sha256"] == hashlib.sha256(responses[0][1].encode()).hexdigest()
    assert receipt["exit_status"] == responses[0][2] == 0
    assert receipt["passed_test_count"] == receipt["collected_test_count"] == combined_passed
    assert receipt["module_outcomes"] == {
        module: {"status": "passed", "passed": count, "failed": 0, "errors": 0}
        for module, count in module_counts.items()
    }
    assert sum(
        outcome["passed"] for outcome in receipt["module_outcomes"].values()
    ) == combined_passed
    assert receipt["started_at"] < receipt["finished_at"]

    subprocess_receipts = receipt["subprocess_receipts"]
    assert len(subprocess_receipts) == 8
    for index, (subprocess_receipt, command, response) in enumerate(zip(
            subprocess_receipts, commands, responses)):
        expected_kind = (
            "combined" if index == 0 else
            "product_mandatory" if index == len(commands) - 1 else "module"
        )
        assert subprocess_receipt["kind"] == expected_kind
        assert subprocess_receipt.get("module") == (
            None if expected_kind != "module" else modules[index - 1]
        )
        assert subprocess_receipt["command"] == command
        assert subprocess_receipt["command_sha256"] == api._canonical_hash(command)
        assert subprocess_receipt["stdout_sha256"] == hashlib.sha256(
            response[0].encode()).hexdigest()
        assert subprocess_receipt["stderr_sha256"] == hashlib.sha256(
            response[1].encode()).hexdigest()
        assert subprocess_receipt["exit_status"] == response[2]
        assert subprocess_receipt["started_at"] < subprocess_receipt["finished_at"]
        artifact_bytes = Path(subprocess_receipt["execution_artifact_path"]).read_bytes()
        assert hashlib.sha256(artifact_bytes).hexdigest() == subprocess_receipt[
            "execution_artifact_sha256"]
        artifact = json.loads(artifact_bytes)
        assert artifact["command"] == command
        assert artifact["stdout"] == response[0]
        assert artifact["stderr"] == response[1]
        assert artifact["exit_status"] == response[2]

    api.CodexSubscriptionPilot._validate_test_receipt(
        receipt, require_execution_proof=True,
    )


def test_preflight_only_json_exposes_each_probe_hash_and_process_exit(monkeypatch, capsys, tmp_path):
    """[RED][PREFLIGHT-RECEIPT] CLI emits auditable per-probe bytes, output, and exit evidence."""
    api = _api()
    preflight, _, _ = _passing_production_preflight(tmp_path)
    monkeypatch.setattr(api, "ProductionSeatbeltPreflight", lambda: preflight)

    assert api.main(["--preflight-only"]) == 0
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["provider_process_starts"] == 0
    assert len(receipt["checks"]) == 4
    required = {
        "argv_sha256", "probe_sha256", "policy_sha256",
        "stdout_sha256", "stderr_sha256", "process_exit_code",
    }
    for check in receipt["checks"]:
        assert required <= set(check)
        assert all(len(check[field]) == 64 for field in required - {"process_exit_code"})
        assert check["process_exit_code"] == 0


def test_production_execution_cli_rejects_unconfirmed_authority_before_preflight_or_adapter(
        monkeypatch, capsys, tmp_path):
    """[RED][PRODUCTION-CLI] Exact human confirmation gates preflight and adapter construction."""
    api = _api()
    _, _, approval_path, manifest_path = _write_production_cli_authority(
        api, tmp_path, confirmed=False,
    )
    constructed = []

    class ForbiddenPreflight:
        def __init__(self):
            constructed.append("preflight")
            raise AssertionError("preflight ran before exact human confirmation")

    class ForbiddenAdapter:
        def __init__(self, *args, **kwargs):
            constructed.append("adapter")
            raise AssertionError("adapter constructed before exact human confirmation")

    monkeypatch.setattr(api, "ProductionSeatbeltPreflight", ForbiddenPreflight)
    monkeypatch.setattr(api, "CodexExecAdapter", ForbiddenAdapter, raising=False)

    assert api.main([
        "--execute-smoke-and-pilot",
        "--approval", str(approval_path),
        "--manifest", str(manifest_path),
    ]) == 2
    error = json.loads(capsys.readouterr().err)
    assert "human confirmation" in error["reason"].lower()
    assert constructed == []


def test_production_execution_cli_constructs_real_adapter_identity_with_fake_process_seam(
        monkeypatch, capsys, tmp_path):
    """[RED][PRODUCTION-CLI] Confirmed production path uses CodexExecAdapter, never fake adapter."""
    api = _api()
    adapter_api = importlib.import_module("runner.codex_exec_adapter")
    approval, manifest, approval_path, manifest_path = _write_production_cli_authority(
        api, tmp_path, confirmed=True,
    )
    adapter_instances = []
    capability = object()

    def fake_provider_popen(*args, **kwargs):
        raise AssertionError("unit production CLI test attempted a real provider process")

    class CompletedPreflight:
        def run(self):
            return {
                "status": "PASS", "provider_process_starts": 0,
                "model_resolution": "UNKNOWN_UNTIL_SMOKE",
                "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION", "usd_cost": None,
            }

        def trusted_containment(self):
            return capability

    def fake_adapter_init(self, **kwargs):
        adapter_instances.append(self)
        assert kwargs["popen_factory"] is fake_provider_popen
        assert kwargs["containment_probe"] is capability

    class ControllerSpy:
        def __init__(self, *, adapter_factory, test_mode=False):
            assert test_mode is False
            self.adapter_factory = adapter_factory

        def run(self, **kwargs):
            assert kwargs["approval"]["human_confirmation"]["confirmed"] is True
            assert kwargs["approval"]["caps"] == CAPS
            assert kwargs["manifest"]["manifest_hash"] == api.manifest_hash(kwargs["manifest"])
            adapter = self.adapter_factory()
            assert type(adapter) is adapter_api.CodexExecAdapter
            return {
                "calls_started": 10,
                "pace_status": "PILOT_ONLY/NO_ROUTING_PROMOTION",
                "promotion_eligible": False,
                "usd_cost": None,
            }

    monkeypatch.setattr(api, "ProductionSeatbeltPreflight", CompletedPreflight)
    monkeypatch.setattr(api, "CodexExecAdapter", adapter_api.CodexExecAdapter, raising=False)
    monkeypatch.setattr(api, "PRODUCTION_POPEN_FACTORY", fake_provider_popen, raising=False)
    monkeypatch.setattr(adapter_api.CodexExecAdapter, "__init__", fake_adapter_init)
    monkeypatch.setattr(api, "CodexSubscriptionPilot", ControllerSpy)

    assert api.main([
        "--execute-smoke-and-pilot",
        "--approval", str(approval_path),
        "--manifest", str(manifest_path),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(adapter_instances) == 1
    assert type(adapter_instances[0]) is adapter_api.CodexExecAdapter
    assert report == {
        "calls_started": 10,
        "pace_status": "PILOT_ONLY/NO_ROUTING_PROMOTION",
        "promotion_eligible": False,
        "usd_cost": None,
    }


def test_planner_adapter_argv_is_read_only_like_smoke_without_smoke_git_flag():
    """[RED][SLOT-SANDBOX] Output-only planners are read-only; only smoke skips Git checks."""
    adapter_api = importlib.import_module("runner.codex_exec_adapter")
    from runner.tests.test_codex_exec_adapter import _adapter, _packet, _request

    packet = _packet()
    packet["task_identity"] = {"ordinal": 1, "case_id": "P1", "role": "planner"}
    packet["packet_hash"] = adapter_api.canonical_packet_hash(packet)
    packet["reverified_packet_hash"] = packet["packet_hash"]
    packet["immutable_authority"]["packet_hash"] = packet["packet_hash"]
    request = _request(adapter_api, packet=packet)
    adapter, _ = _adapter(adapter_api, request)

    argv = adapter._argv(request)

    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--skip-git-repo-check" not in argv


def test_production_path_consumes_ten_distinct_slot_capabilities_and_rejects_eleventh(
        monkeypatch, tmp_path):
    """[RED][CAPABILITY-BROKER] Each scheduled call owns exactly one matching authority slot."""
    api = _api()
    approval, manifest, approval_path, manifest_path = _write_production_cli_authority(
        api, tmp_path, confirmed=True,
    )
    expected_slots = [
        {
            "ordinal": ordinal,
            "role": role,
            "model": model,
            "effort": effort,
            "sandbox": "read-only" if role in {"smoke", "planner"} else "workspace-write",
        }
        for ordinal, (role, model, effort) in enumerate(api.EXACT_CALL_PLAN)
    ]
    minted = []

    class Capability:
        def __init__(self, slot):
            self.slot = json.loads(json.dumps(slot))

    class CompletedPreflight:
        def run(self):
            return {
                "status": "PASS", "provider_process_starts": 0,
                "model_resolution": "UNKNOWN_UNTIL_SMOKE",
                "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION", "usd_cost": None,
            }

        def trusted_containment(self, *, slot):
            if len(minted) >= 10:
                raise RuntimeError("capability broker exhausted")
            assert slot == expected_slots[len(minted)]
            capability = Capability(slot)
            minted.append(capability)
            return capability

    adapters = []

    class Adapter:
        def __init__(self, **kwargs):
            self.capability = kwargs["containment_probe"]
            adapters.append(self)

    class Controller:
        def __init__(self, *, adapter_factory, test_mode):
            assert test_mode is False
            self.adapter_factory = adapter_factory

        def run(self, **kwargs):
            for expected in expected_slots:
                adapter = self.adapter_factory()
                assert adapter.capability.slot == expected
            with pytest.raises(RuntimeError, match="exhausted|eleventh|cap"):
                self.adapter_factory()
            return {"pace_status": "PILOT_ONLY/NO_ROUTING_PROMOTION", "promotion_eligible": False}

    monkeypatch.setattr(api, "ProductionSeatbeltPreflight", CompletedPreflight)
    monkeypatch.setattr(api, "CodexExecAdapter", Adapter)
    monkeypatch.setattr(api, "CodexSubscriptionPilot", Controller)

    report = api._run_production(approval_path, manifest_path)

    assert len(minted) == len(adapters) == 10
    assert len({id(capability) for capability in minted}) == 10
    assert report["pace_status"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"


@pytest.mark.parametrize("canonical_root", [
    "<HOME>/Claude/Projects/taxahead",
    "<HOME>/Claude/Projects/taxahead-integration",
    "<HOME>/Claude/Projects/padsplit-reverification/pms",
])
def test_packet_work_roots_cannot_equal_or_descend_from_canonical_protected_root(
        canonical_root):
    """[RED][PROTECTED-ROOTS] Product attempts cannot run inside canonical repositories."""
    api = _api()
    _, _, packets = _materials()
    packet = json.loads(json.dumps(packets[0]))
    packet["cwd"] = canonical_root + "/attempt"
    packet["artifact_root"] = canonical_root + "/attempt-artifacts"
    packet["writable_roots"] = [packet["cwd"], packet["artifact_root"]]
    packet["ordered_argv"] = [[
        "/opt/homebrew/bin/codex", "exec", "--cd", packet["cwd"],
        "--model", "gpt-5.6-sol", "--sandbox", "read-only",
        "--ask-for-approval", "never", "-c", "model_reasoning_effort=high",
        "--json", "--output-last-message", packet["artifact_root"] + "/final.txt", "-",
    ]]
    packet["environment"] = {"LANG": "C", "PATH": "/usr/bin"}
    packet["allowed_write_targets"] = [packet["artifact_root"] + "/final.txt"]
    packet["allowed_files"] = [
        material["path"] for material in packet["sealed_materials"].values()
    ]
    packet["packet_hash"] = packet["reverified_packet_hash"] = api.packet_hash(packet)
    pilot = api.CodexSubscriptionPilot(adapter_factory=lambda: FakeAdapter(), test_mode=True)

    with pytest.raises(api.PilotBlockedError, match="canonical.*protected|protected.*root"):
        pilot._validate_packet(packet, 1, api.EXACT_CALL_PLAN[1])


@pytest.mark.parametrize("scenario", [
    "module_nonzero", "module_summary_missing", "module_count_mismatch", "combined_mismatch",
])
def test_required_test_gate_normal_output_fails_closed_on_any_process_or_count_mismatch(
        tmp_path, scenario):
    """[RED][TEST-RECEIPT] Every normal-output subprocess and count must agree."""
    api = _api()
    modules = list(api.REQUIRED_GATE_MODULE_ORDER)
    module_counts = {module: count for module, count in zip(modules, (2, 3, 5, 7, 11, 13))}
    combined_passed = sum(module_counts.values())
    overrides = {}
    if scenario == "module_nonzero":
        overrides[3] = ("1 failed, 4 passed in 0.10s\n", "assertion failed\n", 1)
    elif scenario == "module_summary_missing":
        overrides[4] = ("no tests ran in 0.01s\n", "", 0)
    elif scenario == "module_count_mismatch":
        overrides[5] = (_normal_pytest_output(module_counts[modules[4]] + 1), "", 0)
    else:
        overrides[0] = (_normal_pytest_output(combined_passed + 1), "", 0)
    fake_popen, calls, commands, _ = _normal_gate_fake(
        api, combined_passed=combined_passed, module_counts=module_counts,
        overrides=overrides,
    )

    receipt = api.RequiredTestGateRunner(
        popen_factory=fake_popen,
        test_mode=True,
        artifact_dir=tmp_path / scenario,
    ).run()

    assert [call[0] for call in calls] == commands
    assert receipt["all_required_fake_cli_tests_passed"] is False
    assert len(receipt["subprocess_receipts"]) == 8
    with pytest.raises(api.PilotBlockedError, match="test|module|count|process|receipt"):
        api.CodexSubscriptionPilot._validate_test_receipt(
            receipt, require_execution_proof=True,
        )


def test_synthetic_json_module_lines_cannot_replace_normal_pytest_subprocess_evidence(tmp_path):
    """[RED][TEST-RECEIPT] Caller-shaped JSON in combined stdout is not module execution proof."""
    api = _api()
    modules = list(api.REQUIRED_GATE_MODULE_ORDER)
    synthetic = "\n".join(
        json.dumps({
            "module": module, "status": "passed", "passed": 1, "failed": 0, "errors": 0,
        }) for module in modules
    ) + "\n6 passed in 0.01s\n"
    module_counts = {module: 1 for module in modules}
    overrides = {
        0: (synthetic, "", 0),
        **{index: ("no tests ran in 0.01s\n", "", 0) for index in range(1, 7)},
    }
    fake_popen, calls, commands, _ = _normal_gate_fake(
        api, combined_passed=6, module_counts=module_counts, overrides=overrides,
    )

    receipt = api.RequiredTestGateRunner(
        popen_factory=fake_popen,
        test_mode=True,
        artifact_dir=tmp_path,
    ).run()

    assert [call[0] for call in calls] == commands
    assert receipt["all_required_fake_cli_tests_passed"] is False
    with pytest.raises(api.PilotBlockedError, match="test|module|count|process|receipt"):
        api.CodexSubscriptionPilot._validate_test_receipt(
            receipt, require_execution_proof=True,
        )


def test_caller_fabricated_required_test_outcomes_are_rejected():
    """[RED][TEST-RECEIPT] Structurally plausible caller data is not execution evidence."""
    api = _api()
    modules = list(api.REQUIRED_GATE_MODULE_ORDER)
    command = ["python3", "-m", "pytest", *modules, "-q"]
    fabricated = {
        "all_required_fake_cli_tests_passed": True,
        "executed_test_modules": modules,
        "compatibility_assertions": REQUIRED_COMPATIBILITY_ASSERTIONS,
        "command": command,
        "command_sha256": api._canonical_hash(command),
        "outcomes": {
            module: {"status": "passed", "passed": 1, "failed": 0, "errors": 0}
            for module in modules
        },
        "passed_test_count": len(modules),
    }

    with pytest.raises(api.PilotBlockedError, match="executed|artifact|provenance|stdout"):
        api.CodexSubscriptionPilot._validate_test_receipt(
            fabricated, require_execution_proof=True,
        )


def test_zero_executed_required_test_receipt_fails_closed():
    """[RED][TEST-RECEIPT] Zero collected/executed tests can never satisfy the gate."""
    api = _api()
    modules = list(api.REQUIRED_GATE_MODULE_ORDER)
    command = ["python3", "-m", "pytest", *modules, "-q"]
    receipt = {
        "all_required_fake_cli_tests_passed": True,
        "executed_test_modules": modules,
        "compatibility_assertions": REQUIRED_COMPATIBILITY_ASSERTIONS,
        "command": command,
        "command_sha256": api._canonical_hash(command),
        "outcomes": {module: {"status": "passed", "passed": 0, "failed": 0, "errors": 0}
                     for module in modules},
        "passed_test_count": 0,
        "collected_test_count": 0,
    }

    with pytest.raises(api.PilotBlockedError, match="zero|executed|count"):
        api.CodexSubscriptionPilot._validate_test_receipt(
            receipt, require_execution_proof=True,
        )


def test_production_cap_ledger_is_durable_sqlite_and_recovers_crashed_attempt(tmp_path):
    """[RED][CAP-LEDGER] Ten exact units survive reopen; eleventh cannot reserve."""
    api = _api()
    ledger_path = tmp_path / "caps.sqlite3"
    ledger = api.ProductionCapLedger(path=str(ledger_path), caps=api.EXACT_CAPS)
    unit = {
        "calls": 1, "seconds": 900, "observed_total_tokens": 150000,
        "subscription_allowance_units": 1,
    }
    reservations = []
    for ordinal in range(10):
        reservation = ledger.reserve("slot-%d" % ordinal, unit)
        ledger.start(reservation["reservation_id"])
        if ordinal == 4:
            ledger.mark_crashed(reservation["reservation_id"])
            ledger = api.ProductionCapLedger(path=str(ledger_path), caps=api.EXACT_CAPS)
        ledger.reconcile(
            reservation["reservation_id"], "observation-%d" % ordinal,
            {"elapsed_seconds": 1, "observed_total_tokens": 10},
        )
        reservations.append(reservation)

    with pytest.raises(RuntimeError, match="cap|exhausted|ten"):
        ledger.reserve("slot-10", unit)
    assert ledger.totals() == {
        "calls": 10, "seconds": 10, "observed_total_tokens": 100,
        "subscription_allowance_units": 10,
    }
    with sqlite3.connect(ledger_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 10


def test_production_adapter_factory_never_receives_in_memory_cap_ledger(monkeypatch, tmp_path):
    """[RED][CAP-LEDGER] Production authority is backed by run-local caps.sqlite3."""
    api = _api()
    _, _, approval_path, manifest_path = _write_production_cli_authority(
        api, tmp_path, confirmed=True,
    )

    class Preflight:
        def run(self):
            return {
                "status": "PASS", "provider_process_starts": 0,
                "model_resolution": "UNKNOWN_UNTIL_SMOKE",
                "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION", "usd_cost": None,
            }

        def trusted_containment(self):
            return object()

    class Adapter:
        def __init__(self, **kwargs):
            ledger = kwargs["ledger"]
            assert Path(ledger.path).name == "caps.sqlite3"
            assert isinstance(ledger.connection_factory(), sqlite3.Connection)

    class Controller:
        def __init__(self, *, adapter_factory, test_mode):
            self.adapter_factory = adapter_factory

        def run(self, **kwargs):
            self.adapter_factory()
            return {"pace_status": "PILOT_ONLY/NO_ROUTING_PROMOTION", "promotion_eligible": False}

    monkeypatch.setattr(api, "ProductionSeatbeltPreflight", Preflight)
    monkeypatch.setattr(api, "CodexExecAdapter", Adapter)
    monkeypatch.setattr(api, "CodexSubscriptionPilot", Controller)
    monkeypatch.setattr(api, "PRODUCTION_RUN_ARTIFACT_ROOT", tmp_path, raising=False)

    api._run_production(approval_path, manifest_path)


def test_main_serializes_provider_adapter_dataclasses_to_canonical_json(monkeypatch, capsys):
    """[RED][REPORT-JSON] Typed adapter results serialize without repr or lossy coercion."""
    api = _api()
    execution_api = importlib.import_module("runner.experiment_execution")
    provider = execution_api.ProviderAdapterResult(
        response_text="CODEX_SMOKE_OK",
        canonical_sdk_response_id="resp-1",
        canonical_sdk_request_id="req-1",
        raw_usage={"input_tokens": 1, "output_tokens": 1},
        raw_response_payload_hash="a" * 64,
        raw_observation_id="obs-1",
    )
    monkeypatch.setattr(api, "_run_production", lambda approval, manifest: {
        "pace_status": "PILOT_ONLY/NO_ROUTING_PROMOTION",
        "promotion_eligible": False,
        "usd_cost": None,
        "execution_results": [provider],
    })

    assert api.main([
        "--execute-smoke-and-pilot", "--approval", "/fake/approval.json",
        "--manifest", "/fake/manifest.json",
    ]) == 0
    rendered = capsys.readouterr().out
    assert rendered == json.dumps(json.loads(rendered), sort_keys=True, separators=(",", ":")) + "\n"
    result = json.loads(rendered)["execution_results"][0]
    assert result["schema"] == "ProviderAdapterResult"
    assert result["response_text"] == "CODEX_SMOKE_OK"
    assert result["raw_usage"] == {"input_tokens": 1, "output_tokens": 1}


PREPARATION_TAXAHEAD_SHA = "a78f13598cf7a425de4bd20e92d6b97f140eedb3"
PREPARATION_PMS_SHA = "4a396220b598d640e4bea5fb703c24efe83c23c5"
PREPARATION_CASES = (
    "P1-tax-package-live-data",
    "P2-ask-taxahead-chat-transport",
    "P3-pms-prerequisite-doctor",
)
PREPARATION_DISPLAYED_CAPS = {
    "combined_calls": 10,
    "per_call_timeout_seconds": 900,
    "combined_timeout_seconds": 9000,
    "per_call_observed_tokens_max": 150000,
    "aggregate_observed_tokens_max_when_telemetry_exists": 1500000,
    "subscription_allowance_units_max": 10,
}
PREPARATION_NORMALIZATION = {
    "schema": "pilot-preparation-normalization.v1",
    "replace_path_roots": {
        "artifact_root": "<ARTIFACT_ROOT>",
        "clone_root": "<CLONE_ROOT>",
    },
    "excluded_field_names": [
        "started_at", "finished_at", "started_at_ns", "finished_at_ns",
    ],
}


def _run_local_git(*argv, cwd=None):
    environment = dict(os.environ)
    environment.update({
        "GIT_AUTHOR_NAME": "Codex Pilot Fixture",
        "GIT_AUTHOR_EMAIL": "pilot-fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Codex Pilot Fixture",
        "GIT_COMMITTER_EMAIL": "pilot-fixture@example.invalid",
        "GIT_AUTHOR_DATE": "2026-07-16T12:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-07-16T12:00:00+00:00",
    })
    return subprocess.run(
        list(argv), cwd=cwd, env=environment, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()


def _make_preparation_source(root, *, product):
    root.mkdir(parents=True)
    _run_local_git("git", "init", "-q", str(root))
    if product == "taxahead":
        files = {
            "src/support/feed.ts": (
                "export async function activeSupportFeed(filingUnit: string) {\n"
                "  return askTaxaheadTransport({ filingUnit });\n"
                "}\n"
            ),
            "fixtures/p1-baseline.json": json.dumps({
                "finding_ids": ["tax_package_mock_backed", "unrelated_baseline"],
            }, sort_keys=True) + "\n",
            "package.json": json.dumps({"scripts": {"smoke": "node smoke.js"}}, sort_keys=True) + "\n",
        }
    else:
        files = {
            "src/prerequisite-doctor.ts": "export const projectId = 'padsplit-cockpit';\n",
            "fixtures/p3-baseline.json": json.dumps({
                "project_id": "padsplit-cockpit",
                "alias": "PMS Cockpit",
                "generated_prisma_client": False,
                "database_url": False,
                "app_endpoint": False,
                "organization_token": False,
            }, sort_keys=True) + "\n",
            "package.json": json.dumps({
                "scripts": {"prerequisite:doctor": "node doctor.js"},
            }, sort_keys=True) + "\n",
        }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _run_local_git("git", "-C", str(root), "add", ".")
    _run_local_git("git", "-C", str(root), "commit", "-q", "-m", "fixture baseline")
    return root


@pytest.fixture
def pilot_preparation_fixture(tmp_path):
    run_id = "unit-" + hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
    clone_base = Path("/private/tmp/codex-product-pilot")
    clone_run_root = clone_base / run_id
    if clone_run_root.exists():
        pytest.fail("unique preparation clone root unexpectedly already exists")
    fixture = {
        "run_id": run_id,
        "artifact_base": tmp_path / "artifacts" / "codex_product_pilot",
        "clone_base": clone_base,
        "taxahead_source": _make_preparation_source(
            tmp_path / "sources" / "taxahead", product="taxahead",
        ),
        "pms_source": _make_preparation_source(
            tmp_path / "sources" / "pms", product="pms",
        ),
    }
    yield fixture
    for receipt_path in fixture["artifact_base"].glob("*/preparation_receipt.v1.json"):
        try:
            receipt = json.loads(receipt_path.read_bytes())
            smoke_path = Path(receipt["slots"][0]["clone_path"])
        except (OSError, KeyError, IndexError, TypeError, ValueError):
            continue
        if smoke_path.parent == Path("/private/tmp") and smoke_path.name.startswith(
                "codex-product-pilot-smoke-"):
            shutil.rmtree(smoke_path, ignore_errors=True)
    shutil.rmtree(clone_run_root, ignore_errors=True)


class FakePreparationGit:
    def __init__(self, fixture):
        self.fixture = fixture
        self.calls = []

    @staticmethod
    def _clean(source):
        return _run_local_git("git", "-C", str(source), "status", "--porcelain") == ""

    def verify_source(self, *, source, expected_sha):
        source = Path(source)
        self.calls.append(("verify_source", str(source), expected_sha))
        fixture_head = _run_local_git("git", "-C", str(source), "rev-parse", "HEAD")
        return {
            "source": str(source),
            "expected_sha": expected_sha,
            "fixture_head_sha": fixture_head,
            "clean": self._clean(source),
            "tree_sha256": hashlib.sha256(
                _run_local_git("git", "-C", str(source), "ls-tree", "-r", "HEAD").encode()
            ).hexdigest(),
        }

    def clone_detached(self, *, source, expected_sha, destination):
        source = Path(source)
        destination = Path(destination)
        if destination.exists():
            raise RuntimeError("clone destination already exists")
        source_before = self.verify_source(source=source, expected_sha=expected_sha)
        clone_argv = ["git", "clone", "--no-hardlinks", str(source), str(destination)]
        self.calls.append(("clone", clone_argv))
        _run_local_git(*clone_argv)
        fixture_head = source_before["fixture_head_sha"]
        checkout_argv = ["git", "-C", str(destination), "checkout", "--detach", fixture_head]
        self.calls.append(("checkout", checkout_argv))
        _run_local_git(*checkout_argv)
        source_object = next(path for path in (source / ".git" / "objects").glob("??/*"))
        clone_object = destination / ".git" / "objects" / source_object.relative_to(
            source / ".git" / "objects")
        source_after = self.verify_source(source=source, expected_sha=expected_sha)
        symbolic_ref = subprocess.run(
            ["git", "-C", str(destination), "symbolic-ref", "-q", "HEAD"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return {
            "source": str(source),
            "destination": str(destination),
            "clone_argv": clone_argv,
            "checkout_argv": checkout_argv,
            "expected_head_sha": expected_sha,
            "fixture_head_sha": fixture_head,
            "detached": symbolic_ref.returncode == 1,
            "no_hardlinks": source_object.stat().st_ino != clone_object.stat().st_ino,
            "source_before": source_before,
            "source_after": source_after,
        }


class FakePreparationPreprobe:
    def __init__(self, *, fail_case=None, ambiguous_case=None):
        self.fail_case = fail_case
        self.ambiguous_case = ambiguous_case
        self.calls = []

    def run(self, *, case_id, clone_path, artifact_dir):
        clone_path = Path(clone_path)
        self.calls.append((case_id, str(clone_path), str(artifact_dir)))
        if case_id == self.fail_case:
            return {"status": "PRECHECK_FAILED", "failure_code": "BASELINE_NOT_REPRODUCED"}
        if case_id == self.ambiguous_case:
            return {
                "status": "PRECHECK_FAILED", "failure_code": "AMBIGUOUS_ACTIVE_CALL_SITE",
                "matches": ["src/support/feed.ts:1", "src/support/feed.ts:2"],
            }
        containment = {
            "status": "PASS", "mechanism": "fake-no-network-root-policy",
            "version": "1", "policy_sha256": "f" * 64,
            "network_attempts": [], "filesystem_violations": [],
        }
        if case_id == PREPARATION_CASES[0]:
            return {
                "status": "PASS",
                "containment_receipt": containment,
                "argv": ["npm", "run", "smoke"],
                "environment": {"REQUIRE_REAL_BACKEND": "1"},
                "baseline_finding_ids": ["tax_package_mock_backed", "unrelated_baseline"],
                "stdout_sha256": "1" * 64,
            }
        if case_id == PREPARATION_CASES[1]:
            path = clone_path / "src" / "support" / "feed.ts"
            lines = path.read_text(encoding="utf-8").splitlines()
            return {
                "status": "PASS",
                "containment_receipt": containment,
                "discovery_argv": ["rg", "-n", "askTaxaheadTransport", "src"],
                "discovery_stdout_sha256": "2" * 64,
                "active_call_site": {
                    "relative_path": "src/support/feed.ts",
                    "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "span": {"start_line": 2, "end_line": 2, "text": lines[1]},
                },
            }
        return {
            "status": "PASS",
            "containment_receipt": containment,
            "argv": [
                "npm", "run", "prerequisite:doctor", "--", "--project-id",
                "padsplit-cockpit", "--alias", "PMS Cockpit", "--json",
            ],
            "baseline": {
                "project_id": "padsplit-cockpit", "alias": "PMS Cockpit",
                "generated_prisma_client": False, "database_url": False,
                "app_endpoint": False, "organization_token": False,
            },
        }


class ForbiddenPreparationLedger:
    def __init__(self):
        self.calls = []

    def reserve(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("preparation reserved provider capacity")

    def totals(self):
        return {"calls": 0, "seconds": 0, "observed_total_tokens": 0,
                "subscription_allowance_units": 0}


def _preparation_harness(api, fixture, *, label="default", fail_case=None,
                         ambiguous_case=None):
    module_counts = {
        module: count for module, count in zip(api.REQUIRED_GATE_MODULE_ORDER, (11, 17, 23, 29, 37, 55))
    }
    fake_gate_popen, gate_calls, _, _ = _normal_gate_fake(
        api, combined_passed=sum(module_counts.values()), module_counts=module_counts,
    )
    test_gate = api.RequiredTestGateRunner(
        popen_factory=fake_gate_popen,
        test_mode=True,
        artifact_dir=fixture["artifact_base"] / ("gate-" + label),
    )
    preflight_fixture_root = fixture["artifact_base"] / ("preflight-fixture-" + label)
    preflight_fixture_root.mkdir(parents=True, exist_ok=True)
    preflight, preflight_popen, _ = _passing_production_preflight(preflight_fixture_root)
    git = FakePreparationGit(fixture)
    preprobe = FakePreparationPreprobe(
        fail_case=fail_case, ambiguous_case=ambiguous_case,
    )
    ledger = ForbiddenPreparationLedger()
    provider_calls = []

    def forbidden_provider(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("preparation constructed or started a provider adapter")

    preparer = api.CodexPilotPreparer(
        artifact_base=fixture["artifact_base"],
        clone_base=fixture["clone_base"],
        source_paths={
            "taxahead": fixture["taxahead_source"],
            "pms": fixture["pms_source"],
        },
        source_shas={
            "taxahead": PREPARATION_TAXAHEAD_SHA,
            "pms": PREPARATION_PMS_SHA,
        },
        test_gate_runner=test_gate,
        preflight_factory=lambda: preflight,
        git_seam=git,
        preprobe_runner=preprobe,
        cap_ledger=ledger,
        provider_factory=forbidden_provider,
        test_mode=True,
    )
    return {
        "preparer": preparer,
        "git": git,
        "preprobe": preprobe,
        "ledger": ledger,
        "provider_calls": provider_calls,
        "gate_calls": gate_calls,
        "preflight_popen": preflight_popen,
    }


@pytest.mark.parametrize("violation", ["missing_run_id", "artifact_root_exists", "clone_root_exists"])
def test_pilot_preparation_requires_new_explicit_run_id_and_never_reuses_roots(
        pilot_preparation_fixture, violation):
    """[RED][PREPARE] Existing evidence or clone roots are immutable and never deleted."""
    api = _api()
    fixture = pilot_preparation_fixture
    harness = _preparation_harness(api, fixture, label=violation)
    run_id = None if violation == "missing_run_id" else fixture["run_id"]
    sentinel = None
    if violation == "artifact_root_exists":
        existing = fixture["artifact_base"] / fixture["run_id"]
        existing.mkdir(parents=True)
        sentinel = existing / "keep.txt"
        sentinel.write_text("do not destroy\n", encoding="utf-8")
    elif violation == "clone_root_exists":
        existing = fixture["clone_base"] / fixture["run_id"]
        existing.mkdir(parents=True)
        sentinel = existing / "keep.txt"
        sentinel.write_text("do not destroy\n", encoding="utf-8")

    with pytest.raises((api.PilotBlockedError, ValueError), match="run.id|exists|reuse"):
        harness["preparer"].prepare(run_id=run_id)

    assert harness["git"].calls == []
    assert harness["provider_calls"] == []
    assert harness["ledger"].calls == []
    if sentinel is not None:
        assert sentinel.read_text(encoding="utf-8") == "do not destroy\n"


def test_pilot_preparation_is_provider_inert_and_retains_non_authorizing_preflight_reference(
        pilot_preparation_fixture):
    """[RED][PREPARE] Preparation proves prerequisites but cannot authorize execution."""
    api = _api()
    harness = _preparation_harness(api, pilot_preparation_fixture)

    receipt = harness["preparer"].prepare(run_id=pilot_preparation_fixture["run_id"])

    assert receipt["status"] == "HUMAN_RECONFIRMATION_REQUIRED"
    assert receipt["provider_process_starts"] == 0
    assert receipt["codex_exec_starts"] == 0
    assert receipt["reserved_cap_units"] == 0
    assert receipt["promotion_boundary"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert receipt["promotion_eligible"] is False
    assert "usd_cost" not in receipt
    assert harness["provider_calls"] == []
    assert harness["ledger"].calls == []
    assert harness["ledger"].totals()["calls"] == 0
    assert len(harness["gate_calls"]) == 8
    assert harness["preflight_popen"].calls
    test_receipt = json.loads(Path(receipt["required_test_receipt_path"]).read_bytes())
    assert test_receipt["all_required_fake_cli_tests_passed"] is True
    preflight_reference = json.loads(Path(receipt["preflight_reference_path"]).read_bytes())
    assert preflight_reference["status"] == "PASS"
    assert preflight_reference["provider_process_starts"] == 0
    assert preflight_reference["authorizes_execution"] is False
    assert preflight_reference["capability_minted"] is False
    assert receipt["execution_preflight"] == "RERUN_REQUIRED"
    assert "capability" not in receipt
    with pytest.raises((AttributeError, TypeError, RuntimeError)):
        api.TrustedProductionContainment.from_preparation_reference(
            receipt["preflight_reference_path"],
        )


def _expected_preparation_slots(run_id, *, smoke_path):
    rows = [(0, "smoke", "smoke", "gpt-5.6-sol", "high", "read-only", smoke_path)]
    ordinal = 1
    for role, model, effort, sandbox in (
        ("planner", "gpt-5.6-sol", "high", "read-only"),
        ("incumbent_coder", "gpt-5.6-terra", "high", "workspace-write"),
        ("challenger_coder", "gpt-5.6-luna", "medium", "workspace-write"),
    ):
        for case in PREPARATION_CASES:
            rows.append((ordinal, case, role, model, effort, sandbox, str(
                Path("/private/tmp/codex-product-pilot") / run_id / case / role / "repo"
            )))
            ordinal += 1
    return [{
        "ordinal": ordinal,
        "case_id": case,
        "role": role,
        "model": model,
        "effort": effort,
        "sandbox": sandbox,
        "clone_path": clone_path,
    } for ordinal, case, role, model, effort, sandbox, clone_path in rows]


def test_pilot_preparation_creates_exact_detached_no_hardlink_clone_slots(
        pilot_preparation_fixture):
    """[RED][PREPARE-CLONES] Ten isolated slots bind exact sources, SHAs, and sandbox modes."""
    api = _api()
    fixture = pilot_preparation_fixture
    harness = _preparation_harness(api, fixture)

    receipt = harness["preparer"].prepare(run_id=fixture["run_id"])

    smoke_path = receipt["slots"][0]["clone_path"]
    assert receipt["slots"] == _expected_preparation_slots(
        fixture["run_id"], smoke_path=smoke_path,
    )
    assert len(receipt["clone_provenance"]) == 9
    assert receipt["smoke_provenance"] == {
        "path": smoke_path,
        "fresh": True,
        "product_source": None,
        "git_clone": False,
    }
    assert Path(receipt["smoke_provenance"]["path"]).is_dir()
    for provenance in receipt["clone_provenance"]:
        destination = Path(provenance["destination"])
        assert destination == Path(
            "/private/tmp/codex-product-pilot", fixture["run_id"],
            provenance["case_id"], provenance["role"], "repo",
        )
        assert provenance["clone_argv"][:3] == ["git", "clone", "--no-hardlinks"]
        assert provenance["detached"] is True
        assert provenance["no_hardlinks"] is True
        assert provenance["source_before"]["clean"] is True
        assert provenance["source_after"] == provenance["source_before"]
        expected_sha = (
            PREPARATION_PMS_SHA if provenance["case_id"] == PREPARATION_CASES[2]
            else PREPARATION_TAXAHEAD_SHA
        )
        assert provenance["expected_head_sha"] == expected_sha
    assert _run_local_git(
        "git", "-C", str(fixture["taxahead_source"]), "status", "--porcelain",
    ) == ""
    assert _run_local_git(
        "git", "-C", str(fixture["pms_source"]), "status", "--porcelain",
    ) == ""


def test_pilot_preparation_seals_materials_preprobes_packets_and_real_tree_evidence(
        pilot_preparation_fixture):
    """[RED][PREPARE-PACKETS] Prepared packets are complete and validator-ready on disk."""
    api = _api()
    fixture = pilot_preparation_fixture
    harness = _preparation_harness(api, fixture)

    receipt = harness["preparer"].prepare(run_id=fixture["run_id"])

    assert len(receipt["packet_paths"]) == 10
    assert set(receipt["case_manifest_paths"]) == set(PREPARATION_CASES)
    for case_id, manifest_path in receipt["case_manifest_paths"].items():
        case_manifest = json.loads(Path(manifest_path).read_bytes())
        assert case_manifest["schema"] == "case_manifest.v1"
        assert case_manifest["case_id"] == case_id
        assert case_manifest["source_sha"] == (
            PREPARATION_PMS_SHA if case_id == PREPARATION_CASES[2]
            else PREPARATION_TAXAHEAD_SHA
        )
        assert case_manifest["preprobe_receipt_path"] == receipt["preprobe_paths"][case_id]
    for packet_path in receipt["packet_paths"]:
        packet_path = Path(packet_path)
        packet = json.loads(packet_path.read_bytes())
        assert set(packet["sealed_materials"]) == set(api.REQUIRED_MATERIALS)
        for material in packet["sealed_materials"].values():
            path = Path(material["path"])
            assert path.read_bytes().endswith(b"\n")
            assert hashlib.sha256(path.read_bytes()).hexdigest() == material["sha256"]
            assert stat.S_IMODE(path.stat().st_mode) & 0o222 == 0
        assert packet["packet_hash"] == packet["reverified_packet_hash"] == api.packet_hash(packet)
        assert packet["clone_tree_hash"] == api._canonical_hash(packet["clone_tree_entries"])
        assert packet["source_tree_hash"] == api._canonical_hash(packet["source_tree_entries"])
        assert packet["ordered_argv"] and all(isinstance(argv, list) for argv in packet["ordered_argv"])
        assert packet["environment"] == {"LANG": "C", "PATH": "/usr/bin:/bin"}
        assert packet["writable_roots"] == [packet["cwd"], packet["artifact_root"]]
        assert packet["preparation_validation"] == {
            "pilot_packet_validator": "PASS",
            "direct_adapter_authority_validator": "PASS",
        }
        assert stat.S_IMODE(packet_path.stat().st_mode) & 0o222 == 0

    assert len(receipt["packet_validation_receipts"]) == 10
    required_validation = {
        "pilot_packet_validator": "PASS",
        "direct_adapter_authority_validator": "PASS",
        "real_filesystem_fixture": True,
    }
    assert all(
        all(validation.get(field) == value for field, value in required_validation.items())
        for validation in receipt["packet_validation_receipts"]
    )
    assert receipt["packet_validation_receipts"][0].get(
        "production_smoke_validator") == "PASS"

    preprobes = {
        case_id: json.loads(Path(path).read_bytes())
        for case_id, path in receipt["preprobe_paths"].items()
    }
    assert preprobes[PREPARATION_CASES[0]]["baseline_finding_ids"] == [
        "tax_package_mock_backed", "unrelated_baseline",
    ]
    p2 = preprobes[PREPARATION_CASES[1]]["active_call_site"]
    assert p2["relative_path"] == "src/support/feed.ts"
    assert p2["span"]["start_line"] == p2["span"]["end_line"] == 2
    assert len(p2["content_sha256"]) == 64
    assert preprobes[PREPARATION_CASES[2]]["baseline"]["project_id"] == "padsplit-cockpit"
    assert all(
        preprobe["containment_receipt"]["status"] == "PASS"
        and preprobe["containment_receipt"]["network_attempts"] == []
        for preprobe in preprobes.values()
    )


@pytest.mark.parametrize("mode", ["failed", "ambiguous"])
def test_pilot_preparation_stops_on_failed_or_ambiguous_preprobe(
        pilot_preparation_fixture, mode):
    """[RED][PREPARE-PREPROBE] P2 ambiguity and any failed reproduction abort before sealing."""
    api = _api()
    kwargs = ({"fail_case": PREPARATION_CASES[0]} if mode == "failed"
              else {"ambiguous_case": PREPARATION_CASES[1]})
    harness = _preparation_harness(api, pilot_preparation_fixture, label=mode, **kwargs)

    with pytest.raises(api.PilotBlockedError, match="preprobe|ambiguous|baseline"):
        harness["preparer"].prepare(run_id=pilot_preparation_fixture["run_id"])

    artifact_run = pilot_preparation_fixture["artifact_base"] / pilot_preparation_fixture["run_id"]
    assert not (artifact_run / "approval" / "pace_manifest.v1.json").exists()
    assert harness["provider_calls"] == []
    assert harness["ledger"].calls == []


def test_pilot_preparation_writes_atomic_manifest_inventory_and_unconfirmed_request(
        pilot_preparation_fixture):
    """[RED][PREPARE-SEAL] Manifest and confirmation request are complete, fsynced, and inert."""
    api = _api()
    fixture = pilot_preparation_fixture
    harness = _preparation_harness(api, fixture)

    receipt = harness["preparer"].prepare(run_id=fixture["run_id"])
    manifest_path = Path(receipt["manifest_path"])
    manifest = json.loads(manifest_path.read_bytes())

    assert manifest["schema"] == "pace_manifest.v1"
    assert manifest["manifest_hash"] == api.manifest_hash(manifest)
    assert manifest["call_plan"] == api.EXACT_CALL_PLAN
    assert manifest["caps"] == api.EXACT_CAPS
    assert manifest["promotion_boundary"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert manifest["smoke_packet"] == json.loads(Path(receipt["packet_paths"][0]).read_bytes())
    assert manifest["frozen_packets"] == [
        json.loads(Path(path).read_bytes()) for path in receipt["packet_paths"][1:]
    ]
    assert manifest["required_test_receipt"] == json.loads(
        Path(receipt["required_test_receipt_path"]).read_bytes())
    assert stat.S_IMODE(manifest_path.stat().st_mode) & 0o222 == 0

    request_path = Path(receipt["confirmation_request_path"])
    request = json.loads(request_path.read_bytes())
    assert request == {
        "schema": "confirmation_request.v1",
        "confirmed": False,
        "run_id": fixture["run_id"],
        "spec_sha256": SPEC_SHA256,
        "manifest_hash": manifest["manifest_hash"],
        "call_plan": api.EXACT_CALL_PLAN,
        "caps": PREPARATION_DISPLAYED_CAPS,
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
        "possible_codex_state_disclosure": (
            "codex-cli-0.41.0-has-no-ephemeral-and-may-write-under-~/.codex"
        ),
        "required_confirmation_text": request["required_confirmation_text"],
    }
    assert request["required_confirmation_text"] == (
        "CONFIRM CODEX PRODUCT PILOT " + fixture["run_id"] + " " + manifest["manifest_hash"]
    )
    assert "usd_cost" not in request
    approval_dir = manifest_path.parent
    assert not (approval_dir / "experiment_approval.v2.json").exists()
    assert not any(
        value.get("user_created") is True for value in (manifest, request)
        if isinstance(value, dict)
    )

    inventory_path = Path(receipt["artifact_manifest_path"])
    inventory = [json.loads(line) for line in inventory_path.read_text(encoding="utf-8").splitlines()]
    assert inventory
    for entry in inventory:
        path = Path(entry["path"])
        assert path.is_file()
        assert entry["size"] == path.stat().st_size
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert set(receipt["fsync_evidence"]) == {
        "file_fsync_paths", "parent_directory_fsync_paths",
    }
    assert set(receipt["fsync_evidence"]["file_fsync_paths"]) >= {
        str(manifest_path), str(request_path), str(inventory_path),
    }
    assert set(receipt["fsync_evidence"]["parent_directory_fsync_paths"]) >= {
        str(manifest_path.parent), str(request_path.parent), str(inventory_path.parent),
    }


@pytest.mark.parametrize("target", [
    "material", "clone_tree", "test_receipt", "preflight_reference", "packet", "manifest",
])
def test_pilot_preparation_detects_every_sealed_artifact_mutation(
        pilot_preparation_fixture, target):
    """[RED][PREPARE-MUTATION] Every authority or evidence byte is rehashed before use."""
    api = _api()
    harness = _preparation_harness(api, pilot_preparation_fixture, label=target)
    receipt = harness["preparer"].prepare(run_id=pilot_preparation_fixture["run_id"])
    packet = json.loads(Path(receipt["packet_paths"][1]).read_bytes())
    targets = {
        "material": Path(next(iter(packet["sealed_materials"].values()))["path"]),
        "clone_tree": Path(packet["cwd"]) / "src" / "support" / "feed.ts",
        "test_receipt": Path(receipt["required_test_receipt_path"]),
        "preflight_reference": Path(receipt["preflight_reference_path"]),
        "packet": Path(receipt["packet_paths"][1]),
        "manifest": Path(receipt["manifest_path"]),
    }
    mutation_path = targets[target]
    mutation_path.chmod(stat.S_IMODE(mutation_path.stat().st_mode) | stat.S_IWUSR)
    mutation_path.write_bytes(mutation_path.read_bytes() + b"MUTATED\n")

    with pytest.raises(api.PilotBlockedError, match="mutat|hash|seal|tree|receipt|manifest"):
        harness["preparer"].verify_seal(receipt["preparation_receipt_path"])


def test_confirmation_builder_requires_exact_explicit_text_before_creating_approval(
        pilot_preparation_fixture):
    """[RED][CONFIRMATION] Only exact user text creates experiment_approval.v2."""
    api = _api()
    fixture = pilot_preparation_fixture
    harness = _preparation_harness(api, fixture)
    receipt = harness["preparer"].prepare(run_id=fixture["run_id"])
    request = json.loads(Path(receipt["confirmation_request_path"]).read_bytes())
    builder = api.PilotConfirmationBuilder(test_mode=True)

    approval_path = builder.build(
        confirmation_request_path=receipt["confirmation_request_path"],
        manifest_path=receipt["manifest_path"],
        explicit_confirmation_text=request["required_confirmation_text"],
    )
    approval = json.loads(Path(approval_path).read_bytes())

    assert approval["schema"] == "experiment_approval.v2"
    assert approval["user_created"] is True
    assert approval["manifest_hash"] == request["manifest_hash"]
    assert approval["caps"] == api.EXACT_CAPS
    assert approval["call_plan"] == api.EXACT_CALL_PLAN
    assert approval["promotion_boundary"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert approval["approval_hash"] == api.approval_hash(approval)
    assert approval["human_confirmation"]["confirmed"] is True
    assert approval["human_confirmation"]["spec_sha256"] == SPEC_SHA256


@pytest.mark.parametrize("violation", ["wrong_text", "stale_manifest", "mutated_request"])
def test_confirmation_builder_rejects_wrong_stale_or_mutated_confirmation(
        pilot_preparation_fixture, violation):
    """[RED][CONFIRMATION] Confirmation binds exact request, manifest, caps, and bytes."""
    api = _api()
    harness = _preparation_harness(api, pilot_preparation_fixture, label=violation)
    receipt = harness["preparer"].prepare(run_id=pilot_preparation_fixture["run_id"])
    request_path = Path(receipt["confirmation_request_path"])
    manifest_path = Path(receipt["manifest_path"])
    request = json.loads(request_path.read_bytes())
    text = request["required_confirmation_text"]
    if violation == "wrong_text":
        text += " WRONG"
    elif violation == "stale_manifest":
        stale = json.loads(manifest_path.read_bytes())
        stale["manifest_hash"] = "0" * 64
        manifest_path.chmod(0o644)
        manifest_path.write_text(json.dumps(stale), encoding="utf-8")
    else:
        mutated = json.loads(request_path.read_bytes())
        mutated["caps"]["combined_calls"] = 9
        request_path.chmod(0o644)
        request_path.write_text(json.dumps(mutated), encoding="utf-8")

    with pytest.raises(api.PilotBlockedError, match="confirm|stale|mutat|manifest|caps|hash"):
        api.PilotConfirmationBuilder(test_mode=True).build(
            confirmation_request_path=request_path,
            manifest_path=manifest_path,
            explicit_confirmation_text=text,
        )


def test_pilot_preparation_is_deterministic_under_exact_declared_normalization(
        pilot_preparation_fixture):
    """[RED][PREPARE-DETERMINISM] Only declared paths and timestamps may differ."""
    api = _api()
    fixture = pilot_preparation_fixture
    first = _preparation_harness(api, fixture, label="determinism-a")
    first_receipt = first["preparer"].prepare(run_id=fixture["run_id"])
    second_run_id = fixture["run_id"] + "-second"
    second = _preparation_harness(api, fixture, label="determinism-b")
    try:
        second_receipt = second["preparer"].prepare(run_id=second_run_id)
        assert first_receipt["determinism_normalization"] == PREPARATION_NORMALIZATION
        assert second_receipt["determinism_normalization"] == PREPARATION_NORMALIZATION
        first_normalized = api.normalize_preparation_receipt(first_receipt)
        second_normalized = api.normalize_preparation_receipt(second_receipt)
        assert first_normalized == second_normalized
        assert hashlib.sha256(api._canonical_bytes(first_normalized)).hexdigest() == hashlib.sha256(
            api._canonical_bytes(second_normalized)
        ).hexdigest()
    finally:
        shutil.rmtree(fixture["clone_base"] / second_run_id, ignore_errors=True)


def test_prepare_pilot_cli_requires_run_id_and_emits_complete_provider_inert_receipt(
        monkeypatch, capsys):
    """[RED][PREPARE-CLI] CLI exposes preparation without constructing a provider adapter."""
    api = _api()
    run_id = "unit-cli-preparation"
    calls = []
    expected = {
        "status": "HUMAN_RECONFIRMATION_REQUIRED",
        "run_id": run_id,
        "provider_process_starts": 0,
        "codex_exec_starts": 0,
        "reserved_cap_units": 0,
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
        "manifest_path": "/tmp/manifest.json",
        "confirmation_request_path": "/tmp/confirmation-request.json",
        "preparation_receipt_path": "/tmp/preparation-receipt.json",
    }

    def fake_prepare(*, run_id):
        calls.append(run_id)
        return expected

    monkeypatch.setattr(api, "_prepare_pilot", fake_prepare, raising=False)

    assert api.main(["--prepare-pilot", "--run-id", run_id]) == 0
    assert calls == [run_id]
    assert json.loads(capsys.readouterr().out) == expected

    parser = api._build_parser()
    prepare_action = next(action for action in parser._actions if action.dest == "prepare_pilot")
    assert prepare_action.const is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--prepare-pilot"])


def test_prepare_pilot_cli_exits_nonzero_and_emits_no_paths_for_incomplete_seal(
        monkeypatch, capsys):
    """[RED][PREPARE-CLI] Partial test, preflight, preprobe, or seal evidence is never success."""
    api = _api()
    run_id = "unit-cli-incomplete"
    incomplete = {
        "status": "PRECHECK_FAILED",
        "failure_code": "P2_PREPROBE_AMBIGUOUS",
        "provider_process_starts": 0,
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
    }
    monkeypatch.setattr(
        api, "_prepare_pilot", lambda *, run_id: incomplete, raising=False,
    )

    assert api.main(["--prepare-pilot", "--run-id", run_id]) == 2
    rendered = json.loads(capsys.readouterr().out)
    assert rendered == incomplete
    assert "manifest_path" not in rendered
    assert "confirmation_request_path" not in rendered


LIVE_TAXAHEAD_SOURCE = Path("<HOME>/Claude/Projects/taxahead-integration")
LIVE_PMS_SOURCE = Path("<HOME>/Claude/Projects/padsplit-reverification/pms")
LIVE_PREPARATION_ARTIFACT_BASE = REPO_ROOT / (
    "loop-team/runs/2026-07-16_model-routing-pace/artifacts/codex_product_pilot"
)


def _git_source_state(source):
    source = Path(source)
    return {
        "head": _run_local_git("git", "-C", str(source), "rev-parse", "HEAD"),
        "status": _run_local_git("git", "-C", str(source), "status", "--porcelain"),
        "tree": _run_local_git("git", "-C", str(source), "rev-parse", "HEAD^{tree}"),
    }


def _commit_fixture_change(source, relative_path, content, message):
    path = Path(source) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _run_local_git("git", "-C", str(source), "add", relative_path)
    _run_local_git("git", "-C", str(source), "commit", "-q", "-m", message)
    return _run_local_git("git", "-C", str(source), "rev-parse", "HEAD")


def _injected_live_preparation_config(api, harness):
    preparer = harness["preparer"]
    kwargs = {
        "artifact_base": preparer.artifact_base,
        "clone_base": preparer.clone_base,
        "source_paths": preparer.source_paths,
        "source_shas": preparer.source_shas,
        "test_gate_runner": preparer.test_gate_runner,
        "preflight_factory": preparer.preflight_factory,
        "git_seam": preparer.git_seam,
        "preprobe_runner": preparer.preprobe_runner,
        "cap_ledger": preparer.cap_ledger,
        "provider_factory": preparer.provider_factory,
        "test_mode": True,
    }
    material_builder_type = getattr(api, "ProductionCaseMaterialBuilder", None)
    if material_builder_type is not None:
        kwargs["material_builder"] = material_builder_type()
    return {
        "schema": "codex-pilot-preparation-config.v1",
        "test_mode": True,
        "preparer_type": api.CodexPilotPreparer,
        "preparer_kwargs": kwargs,
    }


def test_live_wiring_default_config_binds_exact_sources_shas_and_concrete_builder_types():
    """[RED][LIVE-WIRING] Production defaults identify real local sources and builders."""
    api = _api()
    config = api.PRODUCTION_PREPARATION_CONFIG

    assert config["schema"] == "codex-pilot-preparation-config.v1"
    assert config["test_mode"] is False
    assert Path(config["artifact_base"]) == LIVE_PREPARATION_ARTIFACT_BASE
    assert Path(config["clone_base"]) == Path("/private/tmp/codex-product-pilot")
    assert {name: Path(path) for name, path in config["source_paths"].items()} == {
        "taxahead": LIVE_TAXAHEAD_SOURCE,
        "pms": LIVE_PMS_SOURCE,
    }
    assert config["source_shas"] == {
        "taxahead": PREPARATION_TAXAHEAD_SHA,
        "pms": PREPARATION_PMS_SHA,
    }
    assert config["preparer_type"] is api.CodexPilotPreparer
    assert config["git_seam_type"] is api.ProductionPreparationGit
    assert config["preprobe_runner_type"] is api.ProductionProductPreprobeRunner
    assert config["material_builder_type"] is api.ProductionCaseMaterialBuilder
    for key in ("git_seam_type", "preprobe_runner_type", "material_builder_type"):
        implementation = config[key]
        assert implementation.__module__ == api.__name__
        assert "fake" not in implementation.__name__.lower()


def test_live_wiring_real_prepare_entrypoint_constructs_configured_preparer(monkeypatch, tmp_path):
    """[RED][LIVE-WIRING] _prepare_pilot is an implementation entrypoint, not a blocking stub."""
    api = _api()
    constructed = []
    expected = {
        "status": "HUMAN_RECONFIRMATION_REQUIRED",
        "provider_process_starts": 0,
        "codex_exec_starts": 0,
        "reserved_cap_units": 0,
        "promotion_boundary": "PILOT_ONLY/NO_ROUTING_PROMOTION",
    }

    class PreparerSpy:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

        def prepare(self, *, run_id):
            assert run_id == "live-wiring-construction"
            return expected

    config = {
        "schema": "codex-pilot-preparation-config.v1",
        "test_mode": True,
        "preparer_type": PreparerSpy,
        "preparer_kwargs": {
            "artifact_base": tmp_path / "artifacts",
            "clone_base": Path("/private/tmp/codex-product-pilot"),
            "source_paths": {
                "taxahead": LIVE_TAXAHEAD_SOURCE,
                "pms": LIVE_PMS_SOURCE,
            },
            "source_shas": {
                "taxahead": PREPARATION_TAXAHEAD_SHA,
                "pms": PREPARATION_PMS_SHA,
            },
        },
    }
    monkeypatch.setattr(api, "PRODUCTION_PREPARATION_CONFIG", config, raising=False)

    assert api._prepare_pilot(run_id="live-wiring-construction") == expected
    assert len(constructed) == 1
    assert constructed[0]["source_paths"] == config["preparer_kwargs"]["source_paths"]
    assert constructed[0]["source_shas"] == config["preparer_kwargs"]["source_shas"]


def test_live_wiring_historical_clean_source_clones_exact_approved_ancestor_without_checkout(
        tmp_path):
    """[RED][LIVE-GIT] A clean advanced HEAD may clone an exact reachable approved ancestor."""
    api = _api()
    source = _make_preparation_source(tmp_path / "source", product="taxahead")
    approved_sha = _git_source_state(source)["head"]
    advanced_sha = _commit_fixture_change(
        source, "src/advanced.ts", "export const advanced = true;\n", "advanced head",
    )
    before = _git_source_state(source)
    destination = tmp_path / "clone"

    provenance = api.ProductionPreparationGit().clone_detached(
        source=source, expected_sha=approved_sha, destination=destination,
    )

    assert before["head"] == advanced_sha != approved_sha
    assert _git_source_state(source) == before
    assert _run_local_git("git", "-C", str(destination), "rev-parse", "HEAD") == approved_sha
    assert provenance["expected_head_sha"] == approved_sha
    assert provenance["source_before"] == provenance["source_after"]
    assert provenance["source_before"]["head_sha"] == advanced_sha
    assert provenance["approved_commit_exists"] is True
    assert provenance["approved_commit_reachable"] is True
    assert provenance["detached"] is True
    assert provenance["no_hardlinks"] is True

    validator = object.__new__(api.CodexPilotPreparer)
    validator.source_shas = {"taxahead": approved_sha}
    validator.test_mode = False
    validated = validator._validate_clone_provenance(
        provenance,
        slot={
            "ordinal": 1, "case_id": PREPARATION_CASES[0], "role": "planner",
            "clone_path": str(destination),
        },
        source_name="taxahead",
    )
    assert validated["expected_head_sha"] == approved_sha


@pytest.mark.parametrize("violation", ["missing_commit", "unreachable_commit", "dirty_source"])
def test_live_wiring_historical_source_rejects_missing_unreachable_or_dirty_without_checkout(
        tmp_path, violation):
    """[RED][LIVE-GIT] Invalid historical provenance never checks out or modifies the source."""
    api = _api()
    source = _make_preparation_source(tmp_path / "source", product="taxahead")
    approved_sha = _git_source_state(source)["head"]
    main_branch = _run_local_git("git", "-C", str(source), "branch", "--show-current")
    _commit_fixture_change(source, "src/main.ts", "export const main = true;\n", "main head")
    expected_sha = "f" * 40
    if violation == "unreachable_commit":
        _run_local_git("git", "-C", str(source), "checkout", "-q", "-b", "side", approved_sha)
        expected_sha = _commit_fixture_change(
            source, "src/side.ts", "export const side = true;\n", "side commit",
        )
        _run_local_git("git", "-C", str(source), "checkout", "-q", main_branch)
    elif violation == "dirty_source":
        expected_sha = approved_sha
        (source / "DIRTY.txt").write_text("dirty\n", encoding="utf-8")
    before = _git_source_state(source)
    destination = tmp_path / "clone"

    with pytest.raises((api.PilotBlockedError, RuntimeError), match="commit|reachable|dirty|clean"):
        api.ProductionPreparationGit().clone_detached(
            source=source, expected_sha=expected_sha, destination=destination,
        )

    assert _git_source_state(source) == before
    assert not destination.exists()


def test_live_wiring_smoke_uses_fresh_canonical_uuid_root_and_runs_production_validator(
        monkeypatch, pilot_preparation_fixture):
    """[RED][LIVE-SMOKE] Preparation validates one standalone canonical smoke root."""
    api = _api()
    harness = _preparation_harness(api, pilot_preparation_fixture, label="live-smoke")
    validated = []
    original = api.CodexSubscriptionPilot._validate_smoke_packet

    def validating_spy(packet):
        validated.append(json.loads(json.dumps(packet)))
        return original(packet)

    monkeypatch.setattr(
        api.CodexSubscriptionPilot, "_validate_smoke_packet", staticmethod(validating_spy),
    )

    receipt = harness["preparer"].prepare(run_id=pilot_preparation_fixture["run_id"])
    smoke_path = Path(receipt["slots"][0]["clone_path"])
    prefix = "codex-product-pilot-smoke-"

    assert smoke_path.parent == Path("/private/tmp")
    assert smoke_path.name.startswith(prefix)
    assert str(uuid.UUID(smoke_path.name[len(prefix):])) == smoke_path.name[len(prefix):]
    assert str(smoke_path).startswith("/private/tmp/codex-product-pilot-smoke-")
    assert not str(smoke_path).startswith("/private/tmp/codex-product-pilot/")
    assert len(validated) == 1
    assert validated[0] == json.loads(Path(receipt["packet_paths"][0]).read_bytes())
    assert receipt["packet_validation_receipts"][0]["production_smoke_validator"] == "PASS"


def _live_material_input(case_id, pilot_preparation_fixture):
    tax_source = pilot_preparation_fixture["taxahead_source"]
    pms_source = pilot_preparation_fixture["pms_source"]
    containment = {
        "status": "PASS", "mechanism": "fake-no-network-root-policy", "version": "1",
        "policy_sha256": "e" * 64, "network_attempts": [], "filesystem_violations": [],
    }
    if case_id == PREPARATION_CASES[0]:
        baseline = tax_source / "fixtures" / "p1-baseline.json"
        preprobe = {
            "status": "PASS", "containment_receipt": containment,
            "argv": ["npm", "run", "smoke"],
            "environment": {"REQUIRE_REAL_BACKEND": "1"},
            "baseline_finding_ids": ["tax_package_mock_backed", "unrelated_baseline"],
            "sealed_source_files": {
                "fixtures/p1-baseline.json": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            },
        }
        specifics = (
            str(LIVE_TAXAHEAD_SOURCE), PREPARATION_TAXAHEAD_SHA, "app.tax-package",
            "tax_package_mock_backed", '["npm","run","smoke"]', "REQUIRE_REAL_BACKEND",
        )
    elif case_id == PREPARATION_CASES[1]:
        site = tax_source / "src" / "support" / "feed.ts"
        preprobe = {
            "status": "PASS", "containment_receipt": containment,
            "discovery_argv": ["rg", "-n", "askTaxaheadTransport", "src"],
            "discovery_stdout_sha256": "2" * 64,
            "active_call_site": {
                "relative_path": "src/support/feed.ts",
                "content_sha256": hashlib.sha256(site.read_bytes()).hexdigest(),
                "span": {
                    "start_line": 2, "end_line": 2,
                    "text": "  return askTaxaheadTransport({ filingUnit });",
                },
            },
        }
        specifics = (
            str(LIVE_TAXAHEAD_SOURCE), PREPARATION_TAXAHEAD_SHA,
            "src/support/feed.ts", hashlib.sha256(site.read_bytes()).hexdigest(),
            "askTaxaheadTransport", "start_line", "filingUnit",
        )
    else:
        baseline = pms_source / "fixtures" / "p3-baseline.json"
        preprobe = {
            "status": "PASS", "containment_receipt": containment,
            "argv": [
                "npm", "run", "prerequisite:doctor", "--", "--project-id",
                "padsplit-cockpit", "--alias", "PMS Cockpit", "--json",
            ],
            "baseline": {
                "project_id": "padsplit-cockpit", "alias": "PMS Cockpit",
                "generated_prisma_client": False, "database_url": False,
                "app_endpoint": False, "organization_token": False,
            },
            "sealed_source_files": {
                "fixtures/p3-baseline.json": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            },
        }
        specifics = (
            str(LIVE_PMS_SOURCE), PREPARATION_PMS_SHA, "prerequisite:doctor",
            "padsplit-cockpit", "PMS Cockpit", "generated_prisma_client",
            "database_url", "app_endpoint", "organization_token",
        )
    source_path = LIVE_PMS_SOURCE if case_id == PREPARATION_CASES[2] else LIVE_TAXAHEAD_SOURCE
    source_sha = PREPARATION_PMS_SHA if case_id == PREPARATION_CASES[2] else PREPARATION_TAXAHEAD_SHA
    case_manifest = {
        "schema": "case_manifest.v1", "case_id": case_id,
        "source_path": str(source_path), "source_sha": source_sha,
        "preprobe": preprobe,
    }
    slot = {
        "ordinal": PREPARATION_CASES.index(case_id) + 1,
        "case_id": case_id, "role": "planner", "model": "gpt-5.6-sol",
        "effort": "high", "sandbox": "read-only",
    }
    return slot, case_manifest, preprobe, specifics


@pytest.mark.parametrize("case_id", PREPARATION_CASES)
def test_live_wiring_case_material_builder_seals_exact_case_specific_reproduced_facts(
        pilot_preparation_fixture, case_id):
    """[RED][LIVE-MATERIALS] Six materials carry exact P1/P2/P3 facts, never placeholders."""
    api = _api()
    slot, case_manifest, preprobe, specifics = _live_material_input(
        case_id, pilot_preparation_fixture,
    )

    materials = api.ProductionCaseMaterialBuilder().build(
        slot=slot,
        case_manifest=case_manifest,
        preprobe_receipt=preprobe,
        clone_path=(pilot_preparation_fixture["pms_source"] if case_id == PREPARATION_CASES[2]
                    else pilot_preparation_fixture["taxahead_source"]),
    )

    assert set(materials) == set(api.REQUIRED_MATERIALS)
    assert all(isinstance(content, bytes) and content.endswith(b"\n")
               for content in materials.values())
    combined = b"\n".join(materials.values()).decode("utf-8")
    for expected in specifics:
        assert expected in combined
    for placeholder in (
        "Execute the sealed", "sealed-role=", "sealed-case=",
        "required-test-gate=PASS; case-preprobe=PASS",
        "provider=codex-subscription",
    ):
        assert placeholder not in combined
    assert "PILOT_ONLY/NO_ROUTING_PROMOTION" in combined


def test_live_wiring_p2_material_builder_rejects_claimed_call_site_not_matching_clone(
        pilot_preparation_fixture):
    """[RED][LIVE-P2] P2's sealed path, span, and hash come from actual clone bytes."""
    api = _api()
    slot, case_manifest, preprobe, _ = _live_material_input(
        PREPARATION_CASES[1], pilot_preparation_fixture,
    )
    preprobe["active_call_site"]["content_sha256"] = "0" * 64
    case_manifest["preprobe"] = preprobe

    with pytest.raises(api.PilotBlockedError, match="call site|content|hash|span|discover"):
        api.ProductionCaseMaterialBuilder().build(
            slot=slot,
            case_manifest=case_manifest,
            preprobe_receipt=preprobe,
            clone_path=pilot_preparation_fixture["taxahead_source"],
        )


def _build_live_executable_bundle(api, receipt):
    request = json.loads(Path(receipt["confirmation_request_path"]).read_bytes())
    return api.PilotConfirmationBuilder(test_mode=True).build_executable(
        preparation_receipt_path=receipt["preparation_receipt_path"],
        explicit_confirmation_text=request["required_confirmation_text"],
    )


def test_live_wiring_confirmation_finalizes_authority_without_hash_self_reference(
        pilot_preparation_fixture):
    """[RED][LIVE-CONFIRM] Final packets bind approval/manifest/packet hashes and validate."""
    api = _api()
    adapter_api = importlib.import_module("runner.codex_exec_adapter")
    from runner.tests.test_codex_exec_adapter import _adapter as make_adapter

    harness = _preparation_harness(api, pilot_preparation_fixture, label="live-confirm")
    receipt = harness["preparer"].prepare(run_id=pilot_preparation_fixture["run_id"])
    templates = [json.loads(Path(path).read_bytes()) for path in receipt["packet_paths"]]
    assert all("immutable_authority" not in packet for packet in templates)
    for packet in templates:
        with pytest.raises(api.PilotBlockedError, match="authority"):
            api.CodexSubscriptionPilot._production_request(packet)

    result = _build_live_executable_bundle(api, receipt)
    approval = json.loads(Path(result["approval_path"]).read_bytes())
    manifest = json.loads(Path(result["manifest_path"]).read_bytes())
    packets = [json.loads(Path(path).read_bytes()) for path in result["packet_paths"]]

    assert result["template_manifest_path"] == receipt["manifest_path"]
    assert result["manifest_path"] != receipt["manifest_path"]
    assert result["packet_paths"] != receipt["packet_paths"]
    assert approval["approval_hash"] == api.approval_hash(approval)
    assert manifest["manifest_hash"] == api.manifest_hash(manifest)
    assert approval["manifest_hash"] == manifest["manifest_hash"]
    assert manifest["smoke_packet"] == packets[0]
    assert manifest["frozen_packets"] == packets[1:]
    api._validate_production_cli_authority(approval, manifest)

    pilot = api.CodexSubscriptionPilot(adapter_factory=lambda: None, test_mode=False)
    for ordinal, (packet, call) in enumerate(zip(packets, api.EXACT_CALL_PLAN)):
        authority = packet["immutable_authority"]
        assert set(authority) == {
            "schema", "spec_sha256", "approval_hash", "manifest_hash", "packet_hash",
            "caps", "requested_model", "requested_effort", "baseline_hashes",
            "promotion_boundary", "confirmed",
        }
        assert authority["schema"] == "user_confirmation.v1"
        assert authority["spec_sha256"] == SPEC_SHA256
        assert authority["approval_hash"] == approval["approval_hash"]
        assert authority["manifest_hash"] == manifest["manifest_hash"]
        assert authority["packet_hash"] == packet["packet_hash"]
        assert authority["caps"] == api.EXACT_CAPS
        assert authority["requested_model"] == packet["requested_model"]
        assert authority["requested_effort"] == packet["requested_effort"]
        assert authority["baseline_hashes"] == {
            "source": packet["source_tree_hash"],
            "clone_tree": packet["clone_tree_hash"],
        }
        assert authority["promotion_boundary"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
        assert authority["confirmed"] is True
        assert packet["packet_hash"] == packet["reverified_packet_hash"]
        assert packet["packet_hash"] == api.packet_hash(packet)
        assert packet["packet_hash"] == adapter_api.canonical_packet_hash(packet)
        pilot._validate_packet(packet, ordinal, call)
        request = api.CodexSubscriptionPilot._production_request(packet)
        adapter, popen = make_adapter(adapter_api, request)
        adapter._validate_request(request, {})
        assert popen.calls == []


@pytest.mark.parametrize("target", ["request", "template_packet", "final_packet"])
def test_live_wiring_confirmation_binding_detects_request_template_or_final_packet_mutation(
        pilot_preparation_fixture, target):
    """[RED][LIVE-CONFIRM] Every pre- and post-confirmation byte remains in the authority chain."""
    api = _api()
    harness = _preparation_harness(api, pilot_preparation_fixture, label="binding-" + target)
    receipt = harness["preparer"].prepare(run_id=pilot_preparation_fixture["run_id"])
    confirmation_text = json.loads(
        Path(receipt["confirmation_request_path"]).read_bytes()
    )["required_confirmation_text"]
    if target == "request":
        mutation_path = Path(receipt["confirmation_request_path"])
    elif target == "template_packet":
        mutation_path = Path(receipt["packet_paths"][1])
    else:
        result = _build_live_executable_bundle(api, receipt)
        mutation_path = Path(result["packet_paths"][1])
    mutation_path.chmod(0o644)
    mutation_path.write_bytes(mutation_path.read_bytes() + b"MUTATED\n")

    if target == "final_packet":
        with pytest.raises(api.PilotBlockedError, match="authority|hash|packet|mutat|seal"):
            api.validate_executable_pilot_bundle(result)
    else:
        with pytest.raises(api.PilotBlockedError, match="confirm|hash|packet|mutat|seal"):
            api.PilotConfirmationBuilder(test_mode=True).build_executable(
                preparation_receipt_path=receipt["preparation_receipt_path"],
                explicit_confirmation_text=confirmation_text,
            )


def test_live_wiring_prepare_cli_calls_real_entrypoint_with_injected_local_config_only(
        monkeypatch, capsys, pilot_preparation_fixture):
    """[RED][LIVE-CLI] CLI uses real _prepare_pilot while all unit inputs remain local and inert."""
    api = _api()
    harness = _preparation_harness(api, pilot_preparation_fixture, label="live-cli")
    config = _injected_live_preparation_config(api, harness)
    monkeypatch.setattr(api, "PRODUCTION_PREPARATION_CONFIG", config, raising=False)
    source_before = {
        "taxahead": _git_source_state(pilot_preparation_fixture["taxahead_source"]),
        "pms": _git_source_state(pilot_preparation_fixture["pms_source"]),
    }

    assert api.main([
        "--prepare-pilot", "--run-id", pilot_preparation_fixture["run_id"],
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["status"] == "HUMAN_RECONFIRMATION_REQUIRED"
    assert receipt["provider_process_starts"] == 0
    assert receipt["codex_exec_starts"] == 0
    assert receipt["reserved_cap_units"] == 0
    assert receipt["promotion_boundary"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert harness["provider_calls"] == []
    assert harness["ledger"].calls == []
    assert len(harness["gate_calls"]) == 8
    assert harness["preflight_popen"].calls
    assert _git_source_state(pilot_preparation_fixture["taxahead_source"]) == source_before[
        "taxahead"]
    assert _git_source_state(pilot_preparation_fixture["pms_source"]) == source_before["pms"]


def _git_object_identity_evidence(api, source_object_dir, clone_object_dir):
    return api.ProductionPreparationGit._object_identity_evidence(
        Path(source_object_dir), Path(clone_object_dir),
    )


def _git_object_identity_field(record, side, field):
    nested = record.get(side)
    if isinstance(nested, dict):
        return nested[field]
    return record[f"{side}_{field}"]


def test_git_object_identity_linked_worktree_resolves_absolute_object_store_and_passes(
        tmp_path):
    """[RED][GIT-OBJECTS] Linked-worktree .git files resolve through Git, not path guessing."""
    api = _api()
    primary = _make_preparation_source(tmp_path / "primary", product="pms")
    approved_sha = _git_source_state(primary)["head"]
    linked_source = tmp_path / "linked-source"
    destination = tmp_path / "detached-clone"
    _run_local_git(
        "git", "-C", str(primary), "worktree", "add", "--detach",
        str(linked_source), approved_sha,
    )
    assert (linked_source / ".git").is_file()
    git_calls = []

    class RecordingPreparationGit(api.ProductionPreparationGit):
        def _git(self, *args, check=True):
            git_calls.append(tuple(args))
            return super()._git(*args, check=check)

    provenance = RecordingPreparationGit().clone_detached(
        source=linked_source, expected_sha=approved_sha, destination=destination,
    )
    expected_source_objects = _run_local_git(
        "git", "-C", str(linked_source), "rev-parse", "--path-format=absolute",
        "--git-path", "objects",
    )
    expected_clone_objects = _run_local_git(
        "git", "-C", str(destination), "rev-parse", "--path-format=absolute",
        "--git-path", "objects",
    )

    assert (
        "-C", str(linked_source), "rev-parse", "--path-format=absolute",
        "--git-path", "objects",
    ) in git_calls
    assert provenance["source_object_dir"] == expected_source_objects
    assert provenance["clone_object_dir"] == expected_clone_objects
    assert provenance["source_object_alternates"] == []
    assert provenance["clone_object_alternates"] == []
    assert provenance["no_hardlinks"] is True
    assert provenance["inode_provenance"]
    assert all(not item["shared_identity"] for item in provenance["inode_provenance"])


def test_git_object_identity_true_regular_file_hardlink_is_rejected(tmp_path):
    """[RED][GIT-OBJECTS] A regular file sharing device and inode is a real hardlink."""
    api = _api()
    source_objects = tmp_path / "source-objects"
    clone_objects = tmp_path / "clone-objects"
    source_object = source_objects / "ab" / "object"
    clone_object = clone_objects / "ab" / "object"
    source_object.parent.mkdir(parents=True)
    clone_object.parent.mkdir(parents=True)
    source_object.write_bytes(b"fixture object bytes")
    os.link(source_object, clone_object)
    assert source_object.stat().st_dev == clone_object.stat().st_dev
    assert source_object.stat().st_ino == clone_object.stat().st_ino

    with pytest.raises(api.PilotBlockedError, match="hardlink|shared filesystem identity"):
        _git_object_identity_evidence(api, source_objects, clone_objects)


@pytest.mark.parametrize(
    ("source_dev", "source_ino", "clone_dev", "clone_ino", "expected"),
    [
        (41, 9001, 41, 9001, True),
        (41, 9001, 42, 9001, False),
        (41, 9001, 41, 9002, False),
    ],
)
def test_git_object_identity_requires_matching_device_and_inode(
        source_dev, source_ino, clone_dev, clone_ino, expected):
    """[RED][GIT-OBJECTS] Equal inode numbers on different devices are not one file."""
    api = _api()

    class FakeStat:
        def __init__(self, device, inode):
            self.st_dev = device
            self.st_ino = inode

    assert api.ProductionPreparationGit._same_filesystem_identity(
        FakeStat(source_dev, source_ino), FakeStat(clone_dev, clone_ino),
    ) is expected


@pytest.mark.parametrize("same_target", [True, False])
def test_git_object_identity_symlinks_use_lstat_and_hash_readlink_target_bytes(
        tmp_path, same_target):
    """[RED][GIT-OBJECTS] Symlink identity records the link itself and its target bytes."""
    api = _api()
    source_objects = tmp_path / "source-objects"
    clone_objects = tmp_path / "clone-objects"
    source_link = source_objects / "ab" / "object"
    clone_link = clone_objects / "ab" / "object"
    source_link.parent.mkdir(parents=True)
    clone_link.parent.mkdir(parents=True)
    source_target = "../../unresolved-source-target"
    clone_target = source_target if same_target else "../../unresolved-clone-target"
    source_link.symlink_to(source_target)
    clone_link.symlink_to(clone_target)
    assert not source_link.exists() and source_link.is_symlink()
    assert not clone_link.exists() and clone_link.is_symlink()

    evidence = _git_object_identity_evidence(api, source_objects, clone_objects)

    assert len(evidence) == 1
    record = evidence[0]
    assert record["relative_path"] == "ab/object"
    assert stat.S_ISLNK(_git_object_identity_field(record, "source", "mode"))
    assert stat.S_ISLNK(_git_object_identity_field(record, "clone", "mode"))
    assert _git_object_identity_field(record, "source", "link_target_sha256") == (
        hashlib.sha256(os.readlink(source_link).encode("utf-8")).hexdigest()
    )
    assert _git_object_identity_field(record, "clone", "link_target_sha256") == (
        hashlib.sha256(os.readlink(clone_link).encode("utf-8")).hexdigest()
    )
    assert (
        _git_object_identity_field(record, "source", "link_target_sha256")
        == _git_object_identity_field(record, "clone", "link_target_sha256")
    ) is same_target
    assert record["shared_identity"] is False


def test_git_object_identity_unresolved_store_fails_precisely_without_hardlink_claim(
        tmp_path):
    """[RED][GIT-OBJECTS] Missing object-store evidence is distinct from shared identity."""
    api = _api()
    malformed_repository = tmp_path / "malformed-repository"
    malformed_repository.mkdir()
    (malformed_repository / ".git").write_text(
        "gitdir: /definitely/missing/common-git-dir\n", encoding="utf-8",
    )

    with pytest.raises(api.PilotBlockedError) as blocked:
        api.ProductionPreparationGit._resolve_git_object_dir(malformed_repository)

    assert "git object store unavailable" in str(blocked.value).lower()
    assert "hardlink" not in str(blocked.value).lower()


def test_git_object_identity_standalone_receipt_records_auditable_stat_evidence(
        tmp_path):
    """[RED][GIT-OBJECTS] Clone provenance binds both stores and every identity component."""
    api = _api()
    source = _make_preparation_source(tmp_path / "source", product="taxahead")
    approved_sha = _git_source_state(source)["head"]
    destination = tmp_path / "clone"

    provenance = api.ProductionPreparationGit().clone_detached(
        source=source, expected_sha=approved_sha, destination=destination,
    )

    assert Path(provenance["source_object_dir"]).is_absolute()
    assert Path(provenance["clone_object_dir"]).is_absolute()
    assert provenance["source_object_alternates"] == []
    assert provenance["clone_object_alternates"] == []
    evidence = provenance["inode_provenance"]
    assert evidence
    for record in evidence:
        assert record["relative_path"]
        for side in ("source", "clone"):
            assert isinstance(_git_object_identity_field(record, side, "st_dev"), int)
            assert isinstance(_git_object_identity_field(record, side, "st_ino"), int)
            assert isinstance(_git_object_identity_field(record, side, "mode"), int)
            assert isinstance(_git_object_identity_field(record, side, "nlink"), int)
        assert record["shared_identity"] is False


def _p1_strict_stdout(*, routes=None, wrappers=None):
    routes = routes or [
        "dashboard", "profile", "tax-package", "connections", "feed",
    ]
    wrappers = wrappers or [
        "askTaxahead", "listSources", "startConnection",
        "completeOAuthConnection", "syncSource", "disconnectSource",
    ]
    return (
        "\x1b[1mTaxAhead reality check\x1b[0m "
        "\x1b[2m(read-only; STRICT mode)\x1b[0m\n\n"
        "\x1b[1m\x1b[36mSummary\x1b[0m\n"
        f"  mock-backed routes (live):   {', '.join(routes)}\n"
        f"  unused wrappers (live):      {', '.join(wrappers)}\n\n"
        "\x1b[31m\x1b[1mFAIL (strict)\x1b[0m \u2014 "
        "REQUIRE_REAL_BACKEND=1 and mock/unused findings remain. Exit 1.\n"
    )


P3_BASELINE_SCRIPT = (
    "const fs=require('node:fs');"
    "const p=JSON.parse(fs.readFileSync('package.json','utf8'));"
    "console.log(JSON.stringify({"
    "schema:'p3-prerequisite-doctor-baseline.v1',"
    "project_id:'padsplit-cockpit',alias:'PMS Cockpit',"
    "doctor_script_registered:Object.hasOwn(p.scripts||{},'prerequisite:doctor'),"
    "doctor_implementation_present:fs.existsSync('web/scripts/prerequisite-doctor.mjs'),"
    "doctor_test_present:fs.existsSync('web/tests/prerequisite-doctor.test.mjs'),"
    "source_verifier_present:fs.existsSync('web/scripts/verify-unpacked-extension.mjs')"
    "}))"
)


def _p3_baseline_payload():
    return {
        "schema": "p3-prerequisite-doctor-baseline.v1",
        "project_id": "padsplit-cockpit",
        "alias": "PMS Cockpit",
        "doctor_script_registered": False,
        "doctor_implementation_present": False,
        "doctor_test_present": False,
        "source_verifier_present": True,
    }


def _p3_doctor_payload(*, status="READY", ready=True, **overrides):
    payload = {
        "schema": "pms.prerequisite-doctor.v1",
        "status": status,
        "ready": ready,
        "project_id": "padsplit-cockpit",
        "alias": "PMS Cockpit",
        "generated_prisma_client": True,
        "database_url": True,
        "app_endpoint": True,
        "organization_token": True,
    }
    payload.update(overrides)
    return payload


def _copy_product_tree(source, target):
    return shutil.copytree(source, target, symlinks=True)


def _capture_and_replay_product_delta(api, baseline, changed, replay, allowed_paths):
    delta = api.ProductTreeDelta.capture(
        baseline, changed, allowed_paths=allowed_paths,
    )
    api.ProductTreeDelta.replay(delta, replay, allowed_paths=allowed_paths)
    return delta


OPENSSL_SIGNING_BINARY = Path(
    "/opt/homebrew/Cellar/openssl@3/3.6.2/bin/openssl"
)
OPENSSL_SIGNING_SHA256 = (
    "bf63843e6856e1994ca71092ff3b46834236eb2144dd9b6ceb85d511128b836e"
)


def _product_verifier_authority(api, root, label, *, pinned_openssl_sha256=None):
    if not OPENSSL_SIGNING_BINARY.is_file() or not os.access(
            OPENSSL_SIGNING_BINARY, os.X_OK):
        pytest.skip("exact pinned OpenSSL 3.6.2 binary is unavailable")
    executable_hash = hashlib.sha256(OPENSSL_SIGNING_BINARY.read_bytes()).hexdigest()
    if executable_hash != OPENSSL_SIGNING_SHA256:
        pytest.skip("exact pinned OpenSSL 3.6.2 binary hash is unavailable")
    key_root = root / label
    key_root.mkdir()
    private_key = key_root / "private.pem"
    public_key = key_root / "public.pem"
    subprocess.run(
        [str(OPENSSL_SIGNING_BINARY), "genpkey", "-algorithm", "Ed25519",
         "-out", str(private_key)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    subprocess.run(
        [str(OPENSSL_SIGNING_BINARY), "pkey", "-in", str(private_key),
         "-pubout", "-out", str(public_key)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    probe = key_root / "probe.bin"
    signature = key_root / "probe.sig"
    probe.write_bytes(b"product-verifier-ed25519-probe\n")
    subprocess.run(
        [str(OPENSSL_SIGNING_BINARY), "pkeyutl", "-sign", "-rawin",
         "-inkey", str(private_key), "-in", str(probe), "-out", str(signature)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    subprocess.run(
        [str(OPENSSL_SIGNING_BINARY), "pkeyutl", "-verify", "-rawin",
         "-pubin", "-inkey", str(public_key), "-in", str(probe),
         "-sigfile", str(signature)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    key_id = hashlib.sha256(public_key.read_bytes()).hexdigest()
    return api.ProductVerifierAuthority(
        openssl_path=OPENSSL_SIGNING_BINARY,
        pinned_openssl_sha256=pinned_openssl_sha256 or OPENSSL_SIGNING_SHA256,
        private_key_path=private_key,
        public_key_path=public_key,
        pinned_public_key_sha256=key_id,
    ), key_id


def _product_verifier_payload(artifact_id="opaque-arm-a"):
    return {
        "schema": "product_verifier_payload.v1",
        "case_id": PREPARATION_CASES[2],
        "opaque_artifact_id": artifact_id,
        "quality_verdict": "PASS",
        "failed_oracle_predicates": [],
        "evidence_hashes": {"oracle": "a" * 64, "tests": "b" * 64},
    }


def test_product_contract_p1_strict_parser_accepts_expected_failure_as_baseline():
    """[RED][PRODUCT-P1] Strict exit 1 is a parseable finding baseline, not a runner crash."""
    api = _api()
    finding_ids = [
        "dashboard_mock_backed",
        "profile_mock_backed",
        "tax_package_mock_backed",
        "connections_mock_backed",
        "feed_mock_backed",
        "ask_taxahead_unused",
        "list_sources_unused",
        "start_connection_unused",
        "complete_oauth_connection_unused",
        "sync_source_unused",
        "disconnect_source_unused",
    ]

    parsed = api.ProductionProductPreprobeRunner.parse_p1_strict_output(
        _p1_strict_stdout(), 1,
    )

    assert parsed == {
        "exit_code": 1,
        "finding_ids": finding_ids,
    }


def test_product_contract_p1_strict_parser_rejects_malformed_or_mismatched_summary():
    """[RED][PRODUCT-P1] Partial, duplicate, unknown, or wrong-exit summaries are not facts."""
    api = _api()
    mismatches = [
        (_p1_strict_stdout(), 0),
        (_p1_strict_stdout().replace("  unused wrappers (live):", "  wrappers:"), 1),
        (_p1_strict_stdout(routes=["tax-package", "tax-package"]), 1),
        (_p1_strict_stdout(wrappers=["unknownWrapper"]), 1),
    ]
    for stdout, exit_code in mismatches:
        with pytest.raises(api.PilotBlockedError, match="P1|strict|exit|summary|finding"):
            api.ProductionProductPreprobeRunner.parse_p1_strict_output(
                stdout, exit_code,
            )


def test_product_contract_p3_baseline_argv_is_one_exact_non_shell_vector():
    """[RED][PRODUCT-P3] Preparation inventories the absent doctor without invoking it."""
    api = _api()

    assert api.ProductionProductPreprobeRunner.p3_baseline_argv() == [
        "node", "-e", P3_BASELINE_SCRIPT,
    ]


def test_product_contract_p3_baseline_parser_accepts_absent_doctor_inventory():
    """[RED][PRODUCT-P3] The dependency-free baseline proves script, code, and test absent."""
    api = _api()
    baseline = _p3_baseline_payload()

    parsed = api.ProductionProductPreprobeRunner.parse_p3_baseline(
        json.dumps(baseline) + "\n", 0,
    )

    assert parsed == {
        "exit_code": 0,
        "baseline": baseline,
    }


def test_product_contract_p3_doctor_parser_accepts_ready_only_with_all_true():
    """[RED][PRODUCT-P3] READY is typed JSON and exit 0 only when every predicate is true."""
    api = _api()
    payload = _p3_doctor_payload()

    parsed = api.ProductionProductPreprobeRunner.parse_p3_doctor_output(
        json.dumps(payload) + "\n", 0,
    )

    assert parsed == {"exit_code": 0, **payload}


def test_product_contract_p3_doctor_parser_accepts_invalid_arguments_exit_2():
    """[RED][PRODUCT-P3] Argument errors are structured INVALID_ARGUMENTS, never readiness."""
    api = _api()
    payload = _p3_doctor_payload(
        status="INVALID_ARGUMENTS", ready=False,
        generated_prisma_client=False, database_url=False,
        app_endpoint=False, organization_token=False,
        error={"code": "INVALID_ARGUMENTS", "message": "unknown argument: --bogus"},
    )

    parsed = api.ProductionProductPreprobeRunner.parse_p3_doctor_output(
        json.dumps(payload) + "\n", 2,
    )

    assert parsed == {"exit_code": 2, **payload}


def test_product_contract_p3_doctor_parser_accepts_not_ready_exit_3():
    """[RED][PRODUCT-P3] One or more false prerequisites produce NOT_READY and exit 3."""
    api = _api()
    payload = _p3_doctor_payload(
        status="NOT_READY", ready=False,
        database_url=False, organization_token=False,
    )

    parsed = api.ProductionProductPreprobeRunner.parse_p3_doctor_output(
        json.dumps(payload) + "\n", 3,
    )

    assert parsed == {"exit_code": 3, **payload}


def test_product_contract_p3_doctor_parser_rejects_untyped_or_inconsistent_result():
    """[RED][PRODUCT-P3] Schema, status, ready, predicates, and exit code must agree."""
    api = _api()
    invalid = [
        (_p3_doctor_payload(schema=1), 0),
        (_p3_doctor_payload(status=True), 0),
        (_p3_doctor_payload(ready="true"), 0),
        (_p3_doctor_payload(database_url=False), 0),
        (_p3_doctor_payload(status="NOT_READY", ready=False, database_url=False), 2),
    ]
    for payload, exit_code in invalid:
        with pytest.raises(api.PilotBlockedError, match="P3|schema|status|ready|exit|predicate"):
            api.ProductionProductPreprobeRunner.parse_p3_doctor_output(
                json.dumps(payload) + "\n", exit_code,
            )


def test_product_contract_tree_delta_replays_binary_change_and_untracked_file(tmp_path):
    """[RED][PRODUCT-DELTA] Binary bytes and untracked additions survive quarantine replay."""
    api = _api()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "blob.bin").write_bytes(b"\x00baseline\xff")
    changed = _copy_product_tree(baseline, tmp_path / "changed")
    (changed / "blob.bin").write_bytes(b"\x00changed\xfe")
    (changed / "new.bin").write_bytes(b"\xff\x00new")
    replay = _copy_product_tree(baseline, tmp_path / "replay")

    _capture_and_replay_product_delta(
        api, baseline, changed, replay, ["blob.bin", "new.bin"],
    )

    assert (replay / "blob.bin").read_bytes() == b"\x00changed\xfe"
    assert (replay / "new.bin").read_bytes() == b"\xff\x00new"
    assert api.ProductTreeDelta.tree_hash(replay) == api.ProductTreeDelta.tree_hash(changed)


def test_product_contract_tree_delta_replays_delete_and_executable_mode(tmp_path):
    """[RED][PRODUCT-DELTA] Deletions and chmod changes are first-class delta operations."""
    api = _api()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    script = baseline / "verify.sh"
    script.write_bytes(b"#!/bin/sh\nexit 0\n")
    script.chmod(0o644)
    (baseline / "obsolete.txt").write_text("remove me\n", encoding="utf-8")
    changed = _copy_product_tree(baseline, tmp_path / "changed")
    (changed / "verify.sh").chmod(0o755)
    (changed / "obsolete.txt").unlink()
    replay = _copy_product_tree(baseline, tmp_path / "replay")

    _capture_and_replay_product_delta(
        api, baseline, changed, replay, ["verify.sh", "obsolete.txt"],
    )

    assert not (replay / "obsolete.txt").exists()
    assert stat.S_IMODE((replay / "verify.sh").lstat().st_mode) == 0o755
    assert api.ProductTreeDelta.tree_hash(replay) == api.ProductTreeDelta.tree_hash(changed)


def test_product_contract_tree_delta_replays_symlink_without_following_it(tmp_path):
    """[RED][PRODUCT-DELTA] Symlink target bytes are replayed and hashed as links."""
    api = _api()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "target-a").write_text("a\n", encoding="utf-8")
    (baseline / "target-b").write_text("b\n", encoding="utf-8")
    (baseline / "current").symlink_to("target-a")
    changed = _copy_product_tree(baseline, tmp_path / "changed")
    (changed / "current").unlink()
    (changed / "current").symlink_to("target-b")
    replay = _copy_product_tree(baseline, tmp_path / "replay")

    _capture_and_replay_product_delta(api, baseline, changed, replay, ["current"])

    assert (replay / "current").is_symlink()
    assert os.readlink(replay / "current") == "target-b"
    assert api.ProductTreeDelta.tree_hash(replay) == api.ProductTreeDelta.tree_hash(changed)


def test_product_contract_tree_delta_rejects_hardlinked_payload(tmp_path):
    """[RED][PRODUCT-DELTA] A delta cannot smuggle shared-inode payload files."""
    api = _api()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    changed = _copy_product_tree(baseline, tmp_path / "changed")
    (changed / "left.bin").write_bytes(b"shared bytes")
    os.link(changed / "left.bin", changed / "right.bin")

    with pytest.raises(api.PilotBlockedError, match="hardlink|inode|link count"):
        api.ProductTreeDelta.capture(
            baseline, changed, allowed_paths=["left.bin", "right.bin"],
        )


def test_product_contract_tree_delta_rejects_any_out_of_scope_change(tmp_path):
    """[RED][PRODUCT-DELTA] One allowed edit cannot conceal a second denied edit."""
    api = _api()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "allowed.txt").write_text("old\n", encoding="utf-8")
    (baseline / "sealed.txt").write_text("sealed\n", encoding="utf-8")
    changed = _copy_product_tree(baseline, tmp_path / "changed")
    (changed / "allowed.txt").write_text("new\n", encoding="utf-8")
    (changed / "sealed.txt").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(api.PilotBlockedError, match="scope|allow|sealed|path"):
        api.ProductTreeDelta.capture(
            baseline, changed, allowed_paths=["allowed.txt"],
        )


def test_product_contract_verifier_authority_signs_and_verifies_valid_receipt(tmp_path):
    """[RED][PRODUCT-AUTH] Local OpenSSL signs canonical verifier bytes under the pinned key."""
    api = _api()
    authority, key_id = _product_verifier_authority(api, tmp_path, "valid")
    payload = _product_verifier_payload()

    receipt = authority.sign_and_verify(payload)

    assert {key: receipt[key] for key in payload} == payload
    assert receipt["signer_key_id"] == key_id
    assert authority.verify_receipt(receipt) is True


def test_product_contract_verifier_authority_rejects_alternate_key_substitution(tmp_path):
    """[RED][PRODUCT-AUTH] A valid signature from an unpinned alternate key has no authority."""
    api = _api()
    authority, _ = _product_verifier_authority(api, tmp_path, "primary")
    alternate, _ = _product_verifier_authority(api, tmp_path, "alternate")
    receipt = alternate.sign_and_verify(_product_verifier_payload("opaque-arm-b"))

    with pytest.raises(api.PilotBlockedError, match="key|signer|signature|pin"):
        authority.verify_receipt(receipt)


def test_product_contract_verifier_authority_rejects_pinned_openssl_mismatch(tmp_path):
    """[RED][PRODUCT-AUTH] Signing stops when the exact OpenSSL binary hash is not pinned."""
    api = _api()

    with pytest.raises(api.PilotBlockedError, match="OpenSSL|binary|executable|pin|hash"):
        authority, _ = _product_verifier_authority(
            api, tmp_path, "mismatch", pinned_openssl_sha256="0" * 64,
        )
        authority.sign_and_verify(_product_verifier_payload())


def test_product_contract_post_arm_verifier_rejects_tree_mutation(tmp_path):
    """[RED][PRODUCT-POST] Oracle output cannot certify a tree changed after its arm seal."""
    api = _api()
    clone = tmp_path / "clone"
    clone.mkdir()
    source = clone / "doctor.ts"
    source.write_text("export const ready = true\n", encoding="utf-8")
    sealed_tree_hash = api.ProductTreeDelta.tree_hash(clone)
    source.write_text("export const ready = false\n", encoding="utf-8")

    with pytest.raises(api.PilotBlockedError, match="tree|mutat|seal|hash"):
        api.ProductPostArmVerifier().verify(
            case_id=PREPARATION_CASES[2],
            clone_path=clone,
            sealed_tree_hash=sealed_tree_hash,
            stdout=json.dumps(_p3_doctor_payload()) + "\n",
            exit_code=0,
        )


def test_product_contract_post_arm_verifier_enforces_p3_exit_0_2_3_semantics(tmp_path):
    """[RED][PRODUCT-POST] P3 uses 0=READY, 3=NOT_READY, and 2=argument error."""
    api = _api()
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "doctor.ts").write_text("export const doctor = true\n", encoding="utf-8")
    sealed_tree_hash = api.ProductTreeDelta.tree_hash(clone)
    verifier = api.ProductPostArmVerifier()

    passed = verifier.verify(
        case_id=PREPARATION_CASES[2], clone_path=clone,
        sealed_tree_hash=sealed_tree_hash,
        stdout=json.dumps(_p3_doctor_payload()) + "\n", exit_code=0,
    )
    not_ready = verifier.verify(
        case_id=PREPARATION_CASES[2], clone_path=clone,
        sealed_tree_hash=sealed_tree_hash,
        stdout=json.dumps(_p3_doctor_payload(
            status="NOT_READY", ready=False,
            database_url=False, organization_token=False,
        )) + "\n", exit_code=3,
    )

    assert passed["status"] == "READY"
    assert passed["exit_code"] == 0
    assert passed["failed_predicates"] == []
    assert not_ready["status"] == "NOT_READY"
    assert not_ready["exit_code"] == 3
    assert set(not_ready["failed_predicates"]) == {
        "database_url", "organization_token",
    }
    with pytest.raises(api.PilotBlockedError, match="P3|argument|INVALID_ARGUMENTS|exit 2"):
        verifier.verify(
            case_id=PREPARATION_CASES[2], clone_path=clone,
            sealed_tree_hash=sealed_tree_hash,
            stdout=json.dumps(_p3_doctor_payload(
                status="INVALID_ARGUMENTS", ready=False,
                generated_prisma_client=False, database_url=False,
                app_endpoint=False, organization_token=False,
                error={
                    "code": "INVALID_ARGUMENTS",
                    "message": "unknown argument: --bogus",
                },
            )) + "\n", exit_code=2,
        )


PRODUCT_MANDATORY_TEST_NAMES = (
    "test_product_mandatory_p2_oracle_rejects_dead_branch_comments_and_import_only",
    "test_product_mandatory_p2_oracle_executes_filing_unit_and_state_transitions",
    "test_product_mandatory_p2_oracle_rejects_object_argument_callback_false_pass",
    "test_product_mandatory_p3_empty_environment_rejects_hardcoded_ready",
    "test_product_mandatory_p3_matrix_catches_hardcoded_false_and_validates_all_modes",
    "test_product_mandatory_oracle_sandbox_captures_identical_policy_canaries_and_cleanup",
    "test_product_mandatory_oracle_canary_requires_structured_permission_denial",
    "test_product_mandatory_oracle_concrete_auditor_kills_detached_descendant",
    "test_product_mandatory_hidden_oracle_bytes_are_absent_before_coder",
    "test_product_mandatory_oracle_generator_seals_and_materializes_after_cleanup",
    "test_product_mandatory_valid_planner_output_derives_coder_packet_with_hash",
    "test_product_mandatory_invalid_or_missing_planner_output_blocks_all_coders",
    "test_product_mandatory_product_delta_rejects_nested_git_metadata",
    "test_product_mandatory_product_delta_rejects_root_git_metadata_mutation",
    "test_product_mandatory_product_git_authority_is_clone_local_and_detects_control_mutation",
    "test_product_mandatory_bun_and_typescript_snapshot_is_exact_and_mutation_aborts",
    "test_product_mandatory_p2_allowlist_excludes_tests_and_sandbox_denies_fork",
    "test_product_mandatory_openssl_keygen_records_full_pre_and_post_pin",
    "test_product_mandatory_required_gate_rejects_every_named_test_omission",
    "test_product_mandatory_partial_reports_exist_before_terminal_exception",
    "test_product_mandatory_final_report_blinds_receipts_and_selects_quality_tokens_latency",
    "test_product_mandatory_final_report_requires_six_verified_signed_receipts",
    "test_product_mandatory_codex_exec_adapter_rejects_legacy_spec_in_test_mode",
)


def _run_p2_hidden_oracle(api, tmp_path, source):
    clone = tmp_path / "p2-clone"
    route = clone / "src" / "routes" / "app.feed.tsx"
    route.parent.mkdir(parents=True)
    route.write_text(source, encoding="utf-8")
    oracle = tmp_path / "p2-hidden-oracle.mjs"
    authority = api.OracleGeneratorAuthority.for_p2(
        artifact_root=tmp_path / "p2-oracle-authority",
        clock_ns=lambda: 200,
    )
    authority.seal()
    materialization = authority.materialize(
        arm_id="fixture-arm",
        destination=oracle,
        coder_cleanup_finished_at_ns=100,
    )
    assert materialization["oracle_path"] == str(oracle)
    process = subprocess.run(
        [str(api.PINNED_BUN_PATH), str(oracle)], cwd=str(clone),
        env={"LANG": "C", "PATH": "/opt/homebrew/bin:/usr/bin:/bin"},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, shell=False, timeout=30, check=False,
    )
    payload = json.loads(process.stdout)
    return process, payload


@pytest.mark.product_mandatory
@pytest.mark.parametrize("source", [
    pytest.param(
        """const handleSend = async () => {
  if (false) {
    await askTaxahead({ filingUnit });
  }
  // loading answer evidence error
  };
""",
        id="dead-branch-plus-comment-state-words",
    ),
    pytest.param(
        """import { askTaxahead } from '../lib/edge-functions';
const handleSend = async () => {
  const filingUnit = { id: 'filing-unit-42' };
  setLoading(true);
  setAnswer('answer');
  setEvidence(['evidence']);
  setError('error');
  };
""",
        id="import-only",
    ),
])
def test_product_mandatory_p2_oracle_rejects_dead_branch_comments_and_import_only(
        tmp_path, source):
    """[BEHAVIORAL][RED][PRODUCT-P2] Lexical decoys cannot satisfy the hidden oracle."""
    api = _api()

    process, payload = _run_p2_hidden_oracle(api, tmp_path, source)

    assert process.returncode == 1
    assert payload["status"] == "FAIL"
    assert payload["handle_send_calls_ask_taxahead"] is False


@pytest.mark.product_mandatory
def test_product_mandatory_p2_oracle_executes_filing_unit_and_state_transitions(tmp_path):
    """[BEHAVIORAL][RED][PRODUCT-P2] The real factory handler runs hello in both arms."""
    api = _api()
    source = """type AskTaxaheadDeps = {
  askTaxahead: (input: { filingUnit: { id: string }, text: string }) => Promise<{
    answer: string, evidence: string[]
  }>;
  filingUnit: { id: string };
  setLoading: (value: boolean) => void;
  setAnswer: (value: string) => void;
  setEvidence: (value: string[]) => void;
  setError: (value: string) => void;
};

export const createAskTaxaheadHandler = (deps: AskTaxaheadDeps) =>
  async (text: string): Promise<void> => {
  deps.setLoading(true);
  try {
    const response = await deps.askTaxahead({ filingUnit: deps.filingUnit, text });
    deps.setAnswer(response.answer);
    deps.setEvidence(response.evidence);
  } catch (error) {
    deps.setError((error as Error).message);
  } finally {
    deps.setLoading(false);
  }
  };

export function FeedComposer() {
  const deps = {} as AskTaxaheadDeps;
  const handleSend = createAskTaxaheadHandler(deps);
  return handleSend;
}
"""

    process, payload = _run_p2_hidden_oracle(api, tmp_path, source)

    assert process.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["factory_contract"] == {
        "factory_symbol": "createAskTaxaheadHandler",
        "handler_parameter": "text:string",
        "handler_return": "Promise<void>",
        "feed_composer_direct_assignment": True,
    }
    assert payload["behavioral_runs"] == {
        "success": {
            "handler_input": "hello",
            "filing_unit_id": "filing-unit-42",
            "transitions": [
                "loading:true",
                "answer:Grounded answer",
                "evidence:evidence-1",
                "loading:false",
            ],
        },
        "error": {
            "handler_input": "hello",
            "filing_unit_id": "filing-unit-42",
            "transitions": [
                "loading:true",
                "error:synthetic failure",
                "loading:false",
            ],
        },
    }


@pytest.mark.product_mandatory
def test_product_mandatory_p2_oracle_rejects_object_argument_callback_false_pass(
        tmp_path):
    """[BEHAVIORAL][RED][PRODUCT-P2] The former context-object callback cannot pass."""
    api = _api()
    source = """const createAskTaxaheadHandler = () => null;
function FeedComposer() {
  const handleSend = async ({
    askTaxahead, filingUnit, setLoading, setAnswer, setEvidence, setError,
  }) => {
    setLoading(true);
    try {
      const response = await askTaxahead({ filingUnit });
      setAnswer(response.answer);
      setEvidence(response.evidence);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };
  return handleSend;
}
"""

    process, payload = _run_p2_hidden_oracle(api, tmp_path, source)

    assert process.returncode == 1
    assert payload["status"] == "FAIL"
    assert payload["factory_contract"]["feed_composer_direct_assignment"] is False


class _FakeP3MatrixRunFactory:
    def __init__(self, mode):
        self.mode = mode
        self.calls = []

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        environment = dict(kwargs.get("env", {}))
        self.calls.append((argv, kwargs))
        invalid = "--bogus" in argv
        injected = all(environment.get(key) for key in (
            "P3_GENERATED_PRISMA_CLIENT", "DATABASE_URL",
            "P3_APP_ENDPOINT", "P3_ORGANIZATION_TOKEN",
        ))
        if invalid:
            payload = _p3_doctor_payload(
                status="INVALID_ARGUMENTS", ready=False,
                generated_prisma_client=False, database_url=False,
                app_endpoint=False, organization_token=False,
                error={"code": "INVALID_ARGUMENTS", "message": "unknown argument: --bogus"},
            )
            exit_code = 2
        elif self.mode == "hardcoded_ready":
            payload = _p3_doctor_payload()
            exit_code = 0
        elif self.mode == "hardcoded_false" or not injected:
            payload = _p3_doctor_payload(
                status="NOT_READY", ready=False,
                generated_prisma_client=False, database_url=False,
                app_endpoint=False, organization_token=False,
            )
            exit_code = 3
        else:
            payload = _p3_doctor_payload()
            exit_code = 0
        return subprocess.CompletedProcess(
            argv, exit_code, stdout=json.dumps(payload) + "\n", stderr="",
        )


def _run_p3_matrix(api, tmp_path, mode):
    clone = tmp_path / ("p3-" + mode)
    clone.mkdir()
    artifact = tmp_path / ("p3-artifact-" + mode)
    fake = _FakeP3MatrixRunFactory(mode)
    oracle = api.ProductP3OracleMatrix(run_factory=fake)
    receipt = oracle.run(
        clone_path=clone,
        artifact_dir=artifact,
        argv=list(api.P3_TARGET_ARGV),
        invalid_argument="--bogus",
        injected_environment={
            "P3_GENERATED_PRISMA_CLIENT": "1",
            "DATABASE_URL": "postgresql://synthetic.invalid/test",
            "P3_APP_ENDPOINT": "http://synthetic.invalid/app",
            "P3_ORGANIZATION_TOKEN": "synthetic-token",
        },
    )
    return receipt, fake


@pytest.mark.product_mandatory
def test_product_mandatory_p3_empty_environment_rejects_hardcoded_ready(tmp_path):
    """[BEHAVIORAL][RED][PRODUCT-P3] Empty env is exactly NOT_READY/3 with four false."""
    api = _api()

    with pytest.raises(api.PilotBlockedError, match="P3|empty|NOT_READY|predicate|matrix"):
        _run_p3_matrix(api, tmp_path, "hardcoded_ready")


@pytest.mark.product_mandatory
def test_product_mandatory_p3_matrix_catches_hardcoded_false_and_validates_all_modes(tmp_path):
    """[BEHAVIORAL][RED][PRODUCT-P3] Invalid/2 and injected READY/0 defeat false constants."""
    api = _api()
    with pytest.raises(api.PilotBlockedError, match="P3|READY|inject|predicate|matrix"):
        _run_p3_matrix(api, tmp_path, "hardcoded_false")

    receipt, fake = _run_p3_matrix(api, tmp_path, "valid")

    assert receipt["schema"] == "product_p3_oracle_matrix.v1"
    assert receipt["status"] == "PASS"
    assert set(receipt["runs"]) == {
        "empty_environment", "invalid_arguments", "injected_ready",
    }
    assert receipt["runs"]["empty_environment"] == {
        "exit_code": 3,
        "status": "NOT_READY",
        "ready": False,
        "predicates": {key: False for key in (
            "generated_prisma_client", "database_url",
            "app_endpoint", "organization_token",
        )},
    }
    assert receipt["runs"]["invalid_arguments"]["exit_code"] == 2
    assert receipt["runs"]["invalid_arguments"]["status"] == "INVALID_ARGUMENTS"
    assert receipt["runs"]["injected_ready"]["exit_code"] == 0
    assert receipt["runs"]["injected_ready"]["status"] == "READY"
    assert all(receipt["runs"]["injected_ready"]["predicates"].values())
    assert len(fake.calls) == 3
    assert all(call[1]["shell"] is False for call in fake.calls)


class _FakeOracleProcessAuditor:
    production_safe = False

    def __init__(self):
        self.calls = []

    def cleanup_and_audit(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "schema": "product_process_cleanup.v1",
            "status": "PASS",
            "initial_audit": {"empty": True, "descendant_pids": []},
            "signals": [],
            "final_audit": {"empty": True, "descendant_pids": []},
        }


class _FakeOracleSandboxPopen:
    def __init__(self, *, denied_errno="EPERM", invalid_kind=None, invalid_stderr=""):
        self.calls = []
        self.denied_errno = denied_errno
        self.invalid_kind = invalid_kind
        self.invalid_stderr = invalid_stderr

    def __call__(self, argv, **kwargs):
        kind = kwargs["env"]["LOOP_ORACLE_PROBE_KIND"]
        self.calls.append((list(argv), dict(kwargs)))
        if kind == "home_secret":
            secret_path = Path(kwargs["env"]["LOOP_ORACLE_SECRET_PATH"])
            assert secret_path.read_bytes() == b"ORACLE_HOME_SECRET_CANARY\n"

        class Process:
            pid = 7000 + len(self.calls)
            returncode = 0 if kind == "oracle" else 77

            def communicate(inner_self, input=None, timeout=None):
                if kind == "oracle":
                    return '{"status":"PASS"}\n', ""
                if kind == self.invalid_kind:
                    inner_self.returncode = 1
                    return "", self.invalid_stderr
                return json.dumps({
                    "schema": "product_oracle_canary.v1",
                    "status": "DENIED",
                    "probe": kind,
                    "errno": self.denied_errno,
                }) + "\n", "Operation not permitted"

        return Process()


@pytest.mark.product_mandatory
@pytest.mark.parametrize("denied_errno", ["EPERM", "EACCES"])
def test_product_mandatory_oracle_sandbox_captures_identical_policy_canaries_and_cleanup(
        tmp_path, denied_errno):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] One policy denies home, WAN, and loopback."""
    api = _api()
    fake = _FakeOracleSandboxPopen(denied_errno=denied_errno)
    auditor = _FakeOracleProcessAuditor()
    ticks = iter(range(10_000, 11_000))
    fake_home = tmp_path / "fake-home"
    oracle_bytes = b"console.log(JSON.stringify({status:'PASS'}));\n"
    runner = api.ProductOracleSandbox(
        popen_factory=fake, process_auditor=auditor,
        clock_ns=lambda: next(ticks), test_mode=True,
    )

    receipt = runner.run(
        clone_path=tmp_path / "clone",
        artifact_dir=tmp_path / "artifact",
        fake_home_root=fake_home,
        oracle_argv=["/fake/runtime", "/controller/oracle.mjs"],
        oracle_bytes=oracle_bytes,
    )

    assert [call[1]["env"]["LOOP_ORACLE_PROBE_KIND"] for call in fake.calls] == [
        "home_secret", "network_external", "network_loopback", "oracle",
    ]
    policies = [call[0][call[0].index("-p") + 1] for call in fake.calls]
    assert len(set(policies)) == 1
    assert receipt["policy_sha256"] == hashlib.sha256(policies[0].encode()).hexdigest()
    assert receipt["canaries"] == {
        "home_secret": "DENIED_" + denied_errno,
        "network_external": "DENIED_" + denied_errno,
        "network_loopback": "DENIED_" + denied_errno,
    }
    assert receipt["oracle_sha256"] == hashlib.sha256(oracle_bytes).hexdigest()
    assert len(receipt["processes"]) == 4
    assert all(process["pid"] > 0 for process in receipt["processes"])
    assert all(process["started_at_ns"] < process["finished_at_ns"]
               for process in receipt["processes"])
    assert receipt["cleanup"] == {
        "process_group_empty": True,
        "fake_home_removed": True,
        "oracle_temp_removed": True,
    }
    assert len(auditor.calls) == 4
    assert not fake_home.exists()


@pytest.mark.product_mandatory
@pytest.mark.parametrize("stderr", [
    pytest.param("Connection refused", id="connection-refused"),
    pytest.param("timed out", id="timeout"),
])
def test_product_mandatory_oracle_canary_requires_structured_permission_denial(
        tmp_path, stderr):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] Nonzero transport failures are not denial proof."""
    api = _api()
    fake = _FakeOracleSandboxPopen(
        invalid_kind="network_loopback", invalid_stderr=stderr,
    )
    runner = api.ProductOracleSandbox(
        popen_factory=fake,
        process_auditor=_FakeOracleProcessAuditor(),
        clock_ns=iter(range(20_000, 21_000)).__next__,
        test_mode=True,
    )

    with pytest.raises(api.PilotBlockedError, match="canary|DENIED|EPERM|EACCES|exit"):
        runner.run(
            clone_path=tmp_path / "clone",
            artifact_dir=tmp_path / "artifact",
            fake_home_root=tmp_path / "fake-home",
            oracle_argv=["/fake/runtime", "/controller/oracle.mjs"],
            oracle_bytes=b"console.log(JSON.stringify({status:'PASS'}));\n",
        )

    assert api.ProductOracleSandbox.CANARY_DENIED_EXIT == 77


@pytest.mark.product_mandatory
def test_product_mandatory_oracle_concrete_auditor_kills_detached_descendant(
        tmp_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] A fork+setsid escape is found and killed."""
    api = _api()
    auditor = api.ProductProcessAuditor()
    with pytest.raises(api.PilotBlockedError, match="auditor|production|concrete|trusted"):
        api.ProductOracleSandbox(
            process_auditor=_FakeOracleProcessAuditor(), test_mode=False,
        )

    child_pid_path = tmp_path / "detached-child.pid"
    script = (
        "import os,signal,time,pathlib\n"
        "child=os.fork()\n"
        "if child == 0:\n"
        " os.setsid()\n"
        " signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        " pathlib.Path(%r).write_text(str(os.getpid()))\n"
        " time.sleep(60)\n"
        "else:\n"
        " signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        " time.sleep(60)\n"
    ) % str(child_pid_path)
    leader = subprocess.Popen(
        [sys.executable, "-c", script], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child_pid = None
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not child_pid_path.is_file():
            time.sleep(0.01)
        assert child_pid_path.is_file(), "fork+setsid fixture did not expose its child PID"
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))

        receipt = auditor.cleanup_and_audit(
            leader_pid=leader.pid,
            leader_pgid=os.getpgid(leader.pid),
            grace_seconds=0.05,
        )

        assert receipt["schema"] == "product_process_cleanup.v1"
        assert receipt["initial_audit"]["empty"] is False
        assert child_pid in receipt["initial_audit"]["descendant_pids"]
        assert any(item["signal"] == "SIGKILL" for item in receipt["signals"])
        assert any(item.get("pid") == child_pid for item in receipt["signals"])
        assert receipt["final_audit"] == {"empty": True, "descendant_pids": []}
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if leader.poll() is None:
            leader.kill()
        leader.wait(timeout=3)


@pytest.mark.product_mandatory
def test_product_mandatory_hidden_oracle_bytes_are_absent_before_coder(
        pilot_preparation_fixture, tmp_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] Preparation cannot disclose hidden oracle bytes."""
    api = _api()
    slot, case_manifest, preprobe, _ = _live_material_input(
        PREPARATION_CASES[1], pilot_preparation_fixture,
    )

    materials = api.ProductionCaseMaterialBuilder().build(
        slot=slot,
        case_manifest=case_manifest,
        preprobe_receipt=preprobe,
        clone_path=pilot_preparation_fixture["taxahead_source"],
    )

    prepared_bytes = b"\n".join(materials.values())
    assert "_P2_ORACLE" not in vars(api.ProductionPostArmController)
    assert not any(
        isinstance(value, bytes) and b"p2-handle-send-oracle" in value
        for owner in (api, api.ProductionPostArmController)
        for value in vars(owner).values()
    )
    authority_root = tmp_path / "oracle-authority"
    authority = api.OracleGeneratorAuthority.for_p2(
        artifact_root=authority_root, clock_ns=lambda: 200,
    )
    authority.seal()
    assert not list(authority_root.rglob("*.mjs"))
    materialized = authority.materialize(
        arm_id="post-cleanup-proof",
        destination=tmp_path / "post-cleanup-oracle.mjs",
        coder_cleanup_finished_at_ns=100,
    )
    hidden_bytes = Path(materialized["oracle_path"]).read_bytes()
    assert hidden_bytes not in prepared_bytes
    assert materialized["oracle_sha256"].encode() not in prepared_bytes


@pytest.mark.product_mandatory
def test_product_mandatory_oracle_generator_seals_and_materializes_after_cleanup(
        tmp_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] P2 bytes appear post-cleanup and match arms."""
    api = _api()
    authority = api.OracleGeneratorAuthority.for_p2(
        artifact_root=tmp_path / "authority", clock_ns=lambda: 200,
    )
    seal = authority.seal()
    assert seal["schema"] == "oracle_generator_authority.v1"
    assert seal["case_id"] == PREPARATION_CASES[1]
    assert isinstance(seal["generator_version"], str) and seal["generator_version"]
    assert all(len(seal[key]) == 64 for key in ("generator_sha256", "input_sha256"))
    assert not list((tmp_path / "authority").rglob("*.mjs"))

    with pytest.raises(api.PilotBlockedError, match="cleanup|timestamp|materializ"):
        authority.materialize(
            arm_id="too-early", destination=tmp_path / "too-early.mjs",
            coder_cleanup_finished_at_ns=201,
        )

    arm_receipts = [
        authority.materialize(
            arm_id=arm_id, destination=tmp_path / (arm_id + ".mjs"),
            coder_cleanup_finished_at_ns=100,
        )
        for arm_id in ("incumbent", "challenger")
    ]
    assert arm_receipts[0]["oracle_sha256"] == arm_receipts[1]["oracle_sha256"]
    for receipt in arm_receipts:
        oracle_path = Path(receipt["oracle_path"])
        assert receipt["materialized_at_ns"] > receipt["coder_cleanup_finished_at_ns"]
        assert hashlib.sha256(oracle_path.read_bytes()).hexdigest() == receipt["oracle_sha256"]
        assert receipt["generator_sha256"] == seal["generator_sha256"]
        assert receipt["input_sha256"] == seal["input_sha256"]
    assert authority.validate_arm_receipts(arm_receipts) is True

    mismatched = [dict(arm_receipts[0]), dict(arm_receipts[1])]
    mismatched[1]["oracle_sha256"] = "0" * 64
    with pytest.raises(api.PilotBlockedError, match="oracle|arm|hash|mismatch"):
        authority.validate_arm_receipts(mismatched)


def _planner_result(api, packet):
    task = packet["task_identity"]
    plan = {
        "schema": "product_planner_output.v1",
        "status": "PLAN_PASS",
        "case_id": task["case_id"],
        "allowed_paths": ["src/" + task["case_id"].lower() + ".ts"],
        "steps": [{"id": "step-1", "action": "implement the sealed product repair"}],
        "checks": ["run the hidden product oracle"],
    }
    plan_bytes = json.dumps(
        plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode() + b"\n"
    return {
        "promotion_eligible": False,
        "planner_output": plan_bytes.decode(),
        "planner_output_sha256": hashlib.sha256(plan_bytes).hexdigest(),
    }


class _PlannerAwareAdapter:
    def __init__(self, api, *, invalid_case=None, missing=False):
        self.api = api
        self.invalid_case = invalid_case
        self.missing = missing
        self.calls = []
        self.coder_handoffs = []

    def execute(self, packet):
        self.calls.append(packet)
        task = packet["task_identity"]
        if task["role"] == "planner":
            if task["case_id"] == self.invalid_case:
                if self.missing:
                    return {"promotion_eligible": False}
                return {"promotion_eligible": False, "planner_output": "not-json\n"}
            return _planner_result(self.api, packet)
        if task["role"] in {"incumbent_coder", "challenger_coder"}:
            self.coder_handoffs.append(packet.get("planner_handoff"))
        return {"promotion_eligible": False}


@pytest.mark.product_mandatory
def test_product_mandatory_valid_planner_output_derives_coder_packet_with_hash():
    """[BEHAVIORAL][RED][PLANNER] Every coder receives the parsed, checked planner hash."""
    api = _api()
    approval, manifest, packets = _materials()
    adapter = _PlannerAwareAdapter(api)

    api.CodexSubscriptionPilot(
        adapter_factory=lambda: adapter, test_mode=True,
    ).run(
        approval=approval, manifest=manifest,
        required_test_receipt=_required_test_receipt(),
        frozen_packets=packets, dry_run=False,
    )

    assert len(adapter.coder_handoffs) == 6
    for handoff in adapter.coder_handoffs:
        assert handoff["schema"] == "planner_handoff.v1"
        assert handoff["status"] == "PLAN_PASS"
        assert handoff["plan_checked"] is True
        assert handoff["coder_packet_derived"] is True
        assert len(handoff["planner_output_sha256"]) == 64


@pytest.mark.product_mandatory
@pytest.mark.parametrize("missing", [True, False], ids=["missing", "invalid"])
def test_product_mandatory_invalid_or_missing_planner_output_blocks_all_coders(missing):
    """[BEHAVIORAL][RED][PLANNER] No coder starts until all three plans parse and pass."""
    api = _api()
    approval, manifest, packets = _materials()
    adapter = _PlannerAwareAdapter(api, invalid_case="P2", missing=missing)

    with pytest.raises(api.PilotBlockedError, match="planner|plan|PLAN_PASS|parse"):
        api.CodexSubscriptionPilot(
            adapter_factory=lambda: adapter, test_mode=True,
        ).run(
            approval=approval, manifest=manifest,
            required_test_receipt=_required_test_receipt(),
            frozen_packets=packets, dry_run=False,
        )

    assert all(packet["task_identity"]["role"] not in {
        "incumbent_coder", "challenger_coder",
    } for packet in adapter.calls)


@pytest.mark.product_mandatory
def test_product_mandatory_product_delta_rejects_nested_git_metadata(tmp_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] Nested .git control data is never product payload."""
    api = _api()
    baseline = tmp_path / "baseline"
    (baseline / "src" / "vendor").mkdir(parents=True)
    changed = _copy_product_tree(baseline, tmp_path / "changed")
    nested_git = changed / "src" / "vendor" / ".git"
    nested_git.mkdir()
    (nested_git / "config").write_text("[core]\nrepositoryformatversion = 0\n")

    with pytest.raises(api.PilotBlockedError, match="Git|git|metadata|control"):
        api.ProductTreeDelta.capture(
            baseline, changed, allowed_paths=["src/vendor"],
        )


@pytest.mark.product_mandatory
@pytest.mark.parametrize("metadata_path", [
    ".git/HEAD", ".git/index", ".git/refs/heads/main", ".git/config",
    ".git/objects/aa/fixture-object", ".git/logs/HEAD",
])
def test_product_mandatory_product_delta_rejects_root_git_metadata_mutation(
        tmp_path, metadata_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] All root Git control changes abort capture."""
    api = _api()
    baseline = tmp_path / "baseline"
    (baseline / "src").mkdir(parents=True)
    (baseline / "src" / "app.ts").write_text("export const ok = true;\n")
    for relative, content in {
        ".git/HEAD": "ref: refs/heads/main\n",
        ".git/index": "index-v1\n",
        ".git/refs/heads/main": "a" * 40 + "\n",
        ".git/config": "[core]\nrepositoryformatversion = 0\n",
        ".git/objects/aa/fixture-object": "sealed-object-bytes\n",
        ".git/logs/HEAD": "sealed reflog bytes\n",
    }.items():
        path = baseline / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    changed = _copy_product_tree(baseline, tmp_path / "changed")
    target = changed / metadata_path
    target.write_bytes(target.read_bytes() + b"MUTATED\n")

    with pytest.raises(api.PilotBlockedError, match="Git|git|metadata|control|mutat"):
        api.ProductTreeDelta.capture(
            baseline, changed, allowed_paths=["src/app.ts"],
        )


@pytest.mark.product_mandatory
@pytest.mark.parametrize("metadata_kind", [
    "HEAD", "index", "ref", "config", "object", "log",
])
def test_product_mandatory_product_git_authority_is_clone_local_and_detects_control_mutation(
        tmp_path, metadata_kind):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] Git seals compare each clone only to itself."""
    api = _api()
    source = tmp_path / "source"
    source.mkdir()
    _run_local_git("git", "init", "-q", "-b", "main", str(source))
    app = source / "src" / "app.ts"
    app.parent.mkdir()
    app.write_text("export const sealed = true;\n", encoding="utf-8")
    _run_local_git("git", "-C", str(source), "add", ".")
    _run_local_git("git", "-C", str(source), "commit", "-q", "-m", "sealed source")
    commit = _run_local_git("git", "-C", str(source), "rev-parse", "HEAD")
    coder = tmp_path / "coder-clone"
    verifier = tmp_path / "verifier-clone"
    _run_local_git("git", "clone", "-q", "--no-hardlinks", str(source), str(coder))
    _run_local_git("git", "clone", "-q", "--no-hardlinks", str(source), str(verifier))
    _run_local_git("git", "-C", str(coder), "config", "pilot.clone", "coder")
    _run_local_git("git", "-C", str(verifier), "config", "pilot.clone", "verifier")

    coder_seal = api.ProductGitAuthority.capture(coder, expected_commit=commit)
    verifier_seal = api.ProductGitAuthority.capture(verifier, expected_commit=commit)

    assert coder_seal["head"] == verifier_seal["head"] == commit
    assert coder_seal["clean"] is verifier_seal["clean"] is True
    assert coder_seal["authority_sha256"] != verifier_seal["authority_sha256"]
    assert api.ProductGitAuthority.compatible_clean_clones(
        coder_seal, verifier_seal,
    ) is True
    assert api.ProductGitAuthority.verify(
        coder, coder_seal, expected_commit=commit,
    ) is True

    git_root = coder / ".git"
    if metadata_kind in {"HEAD", "index", "config"}:
        target = git_root / metadata_kind
    elif metadata_kind == "ref":
        target = next(path for path in (git_root / "refs").rglob("*") if path.is_file())
    elif metadata_kind == "object":
        target = next(path for path in (git_root / "objects").glob("??/*") if path.is_file())
    else:
        target = git_root / "logs" / "HEAD"
    target.write_bytes(target.read_bytes() + b"MUTATED\n")

    with pytest.raises(api.PilotBlockedError, match="Git|git|authority|mutat|control"):
        api.ProductGitAuthority.verify(
            coder, coder_seal, expected_commit=commit,
        )


@pytest.mark.product_mandatory
def test_product_mandatory_bun_and_typescript_snapshot_is_exact_and_mutation_aborts(tmp_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] Fresh clones use sealed external TS 5.9.3."""
    api = _api()
    source_snapshot = tmp_path / "protected-source-snapshot"
    source_snapshot.mkdir()
    project = tmp_path / "fresh-verifier-clone"
    project.mkdir()
    installed_dependency_root = source_snapshot / "installed-dependencies" / "node_modules"
    typescript_package = installed_dependency_root / "typescript" / "package.json"
    typescript_package.parent.mkdir(parents=True)
    package_bytes = json.dumps({
        "devDependencies": {"typescript": "^5.9.0"},
    }, sort_keys=True).encode() + b"\n"
    lock = {
        "name": "taxahead-fixture",
        "lockfileVersion": 3,
        "packages": {
            "": {"devDependencies": {"typescript": "^5.9.0"}},
            "node_modules/typescript": {
                "version": "5.9.3",
                "resolved": "https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz",
                "integrity": "sha512-sealed-typescript-5.9.3-fixture",
            },
        },
    }
    lock_bytes = json.dumps(lock, sort_keys=True).encode() + b"\n"
    for root in (source_snapshot, project):
        (root / "package.json").write_bytes(package_bytes)
        (root / "package-lock.json").write_bytes(lock_bytes)
    typescript_package.write_text(json.dumps({
        "name": "typescript", "version": "5.9.3",
    }, sort_keys=True) + "\n", encoding="utf-8")
    (typescript_package.parent / "lib.typescript.js").write_text(
        "export const version = '5.9.3';\n", encoding="utf-8",
    )
    assert not (project / "node_modules").exists()
    snapshot_path = tmp_path / "runtime-snapshot.v1.json"
    runtime = api.ProductRuntimeSnapshot()

    runtime_kwargs = {
        "project_root": project,
        "source_snapshot_root": source_snapshot,
        "installed_dependency_root": installed_dependency_root,
        "snapshot_path": snapshot_path,
    }
    receipt = runtime.capture(**runtime_kwargs)

    assert receipt["bun"] == {
        "path": "/opt/homebrew/Cellar/bun/1.3.14/bin/bun",
        "version": "1.3.14",
        "sha256": "fb46ac6497104821512b67a3b3157c9fbbab8a99e311fb38da5b7039a373d860",
        "mode": 0o555,
        "size": 61512816,
        "nlink": 1,
    }
    assert receipt["typescript"]["version"] == "5.9.3"
    assert receipt["typescript"]["declared_range"] == "^5.9.0"
    assert receipt["typescript"]["lockfile_version"] == "5.9.3"
    assert receipt["typescript"]["installed_dependency_root"] == str(
        installed_dependency_root,
    )
    assert receipt["typescript"]["package_json_sha256"] == hashlib.sha256(
        typescript_package.read_bytes(),
    ).hexdigest()
    assert receipt["project"]["package_lock_sha256"] == hashlib.sha256(
        lock_bytes,
    ).hexdigest()
    original_snapshot = snapshot_path.read_bytes()
    mutated_snapshot = json.loads(original_snapshot)
    mutated_snapshot["bun"]["sha256"] = "0" * 64
    snapshot_path.write_text(json.dumps(mutated_snapshot), encoding="utf-8")
    with pytest.raises(api.PilotBlockedError, match="Bun|runtime|snapshot|hash|mutat"):
        runtime.verify(**runtime_kwargs)

    snapshot_path.write_bytes(original_snapshot)
    typescript_package.write_text(json.dumps({
        "name": "typescript", "version": "5.9.4",
    }), encoding="utf-8")
    with pytest.raises(api.PilotBlockedError, match="TypeScript|5.9.3|snapshot|mutat"):
        runtime.verify(**runtime_kwargs)


@pytest.mark.product_mandatory
def test_product_mandatory_p2_allowlist_excludes_tests_and_sandbox_denies_fork(
        tmp_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] P2 permits only route/helper and no forks."""
    api = _api()
    assert api.CodexPilotPreparer._allowed_patch_paths(PREPARATION_CASES[1]) == [
        "src/routes/app.feed.tsx",
        "src/lib/edge-functions.ts",
    ]
    policy = api.ProductOracleSandbox._policy(
        clone=tmp_path / "clone",
        artifact=tmp_path / "artifact",
        fake_home=tmp_path / "fake-home",
    )
    assert "(deny process-fork)" in policy
    assert "(allow process*)" not in policy


def _install_fake_pinned_openssl(api, monkeypatch, tmp_path, *, mutate_after_keygen=False):
    binary = tmp_path / ("openssl-mutating" if mutate_after_keygen else "openssl-stable")
    original = (b"fake-openssl-3.6.2\n" * 50_000)[:893392]
    if len(original) < 893392:
        original += b"x" * (893392 - len(original))
    binary.write_bytes(original)
    binary.chmod(0o555)
    digest = hashlib.sha256(original).hexdigest()
    version = "OpenSSL 3.6.2 test-pin (Library: OpenSSL 3.6.2 test-pin)"
    monkeypatch.setattr(api, "PINNED_OPENSSL_PATH", binary)
    monkeypatch.setattr(api, "PINNED_OPENSSL_SHA256", digest)
    monkeypatch.setattr(api, "PINNED_OPENSSL_VERSION", version)

    def fake_run(argv, **kwargs):
        argv = list(argv)
        if argv[1:] == ["version"]:
            stdout = version + "\n" if kwargs.get("text") else (version + "\n").encode()
            stderr = "" if kwargs.get("text") else b""
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=stderr)
        if argv[1] == "genpkey":
            output = Path(argv[argv.index("-out") + 1])
            output.write_bytes(b"FAKE PRIVATE KEY\n")
            if mutate_after_keygen:
                binary.chmod(0o755)
                binary.write_bytes(b"M" * 893392)
                binary.chmod(0o555)
        elif argv[1] == "pkey" and "-pubout" in argv:
            output = Path(argv[argv.index("-out") + 1])
            output.write_bytes(b"FAKE PUBLIC KEY\n")
        elif argv[1] == "pkeyutl" and "-sign" in argv:
            message = Path(argv[argv.index("-in") + 1]).read_bytes()
            output = Path(argv[argv.index("-out") + 1])
            output.write_bytes(hashlib.sha256(message).digest())
        elif argv[1] == "pkeyutl" and "-verify" in argv:
            message = Path(argv[argv.index("-in") + 1]).read_bytes()
            signature = Path(argv[argv.index("-sigfile") + 1]).read_bytes()
            return subprocess.CompletedProcess(
                argv, 0 if signature == hashlib.sha256(message).digest() else 1,
                stdout=b"", stderr=b"",
            )
        else:
            raise AssertionError("unexpected fake OpenSSL argv: " + repr(argv))
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(api.subprocess, "run", fake_run)
    return binary, digest


@pytest.mark.product_mandatory
def test_product_mandatory_openssl_keygen_records_full_pre_and_post_pin(
        monkeypatch, tmp_path):
    """[BEHAVIORAL][RED][SECURITY-ORACLE] Keygen records and rechecks the full pin."""
    api = _api()
    binary, digest = _install_fake_pinned_openssl(api, monkeypatch, tmp_path)

    authority, receipt = api.create_product_verifier_authority(tmp_path / "authority")

    assert receipt["openssl_pre_keygen"] == receipt["openssl_post_keygen"]
    assert receipt["openssl_pre_keygen"] == {
        "path": str(binary),
        "sha256": digest,
        "version": api.PINNED_OPENSSL_VERSION,
        "mode": 0o555,
        "nlink": 1,
        "size": 893392,
        "version_argv_sha256": api._canonical_hash([str(binary), "version"]),
    }
    assert receipt["openssl_post_keygen"] == authority._openssl_facts

    _install_fake_pinned_openssl(
        api, monkeypatch, tmp_path, mutate_after_keygen=True,
    )
    with pytest.raises(api.PilotBlockedError, match="OpenSSL|pin|hash|changed|mutat"):
        api.create_product_verifier_authority(tmp_path / "mutated-authority")


@pytest.mark.product_mandatory
def test_product_mandatory_required_gate_rejects_every_named_test_omission():
    """[BEHAVIORAL][RED][TEST-GATE] Every named mandatory test is marker-bound and required."""
    api = _api()
    adapter_tests = importlib.import_module("runner.tests.test_codex_exec_adapter")
    assert tuple(api.REQUIRED_PRODUCT_MANDATORY_TESTS) == PRODUCT_MANDATORY_TEST_NAMES
    for name in PRODUCT_MANDATORY_TEST_NAMES:
        owner = adapter_tests if name.endswith("legacy_spec_in_test_mode") else sys.modules[__name__]
        markers = getattr(getattr(owner, name), "pytestmark", [])
        assert any(marker.name == "product_mandatory" for marker in markers), name

    validator = api.RequiredTestGateRunner.validate_product_mandatory_nodeids
    complete = list(PRODUCT_MANDATORY_TEST_NAMES)
    accepted = validator(complete)
    assert accepted["status"] == "PASS"
    assert accepted["product_mandatory_test_names"] == complete
    for omitted in complete:
        with pytest.raises(api.PilotBlockedError, match="mandatory|test|omission|missing"):
            validator([name for name in complete if name != omitted])


class _SignedPostArmFake:
    def __init__(self):
        self.receipts = []

    def verify_after_coder(self, *, packet, result):
        receipt = {
            "schema": "controller_post_arm_receipt.v1",
            "status": "PASS",
            "signed": True,
            "case_id": packet["task_identity"]["case_id"],
            "opaque_artifact_id": "opaque-%02d" % packet["task_identity"]["ordinal"],
            "receipt_sha256": hashlib.sha256(json.dumps(
                packet["task_identity"], sort_keys=True,
            ).encode()).hexdigest(),
            "promotion_eligible": False,
        }
        self.receipts.append(receipt)
        return receipt


class _ActualSignedPostArm:
    def __init__(self, api, authority, root):
        self.api = api
        self.authority = authority
        self.root = Path(root)
        self.root.mkdir()
        self.receipts = []

    def verify_after_coder(self, *, packet, result):
        task = packet["task_identity"]
        receipt_id = "post-arm-%02d" % task["ordinal"]
        signed = self.authority.sign_and_verify({
            "schema": "product_post_arm_verification.v1",
            "status": "PASS",
            "quality_verdict": "PASS",
            "case_id": task["case_id"],
            "role": task["role"],
            "opaque_artifact_id": "opaque-%02d" % task["ordinal"],
            "receipt_id": receipt_id,
            "promotion_eligible": False,
        })
        path = self.root / (receipt_id + ".json")
        path.write_bytes(self.api._canonical_bytes(signed) + b"\n")
        summary = {
            "schema": "controller_post_arm_receipt.v1",
            "status": "PASS",
            "signed": True,
            "case_id": task["case_id"],
            "role": task["role"],
            "opaque_artifact_id": signed["opaque_artifact_id"],
            "receipt_id": receipt_id,
            "receipt_path": str(path),
            "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "promotion_eligible": False,
        }
        self.receipts.append(summary)
        return summary


class _ReportAdapter(_PlannerAwareAdapter):
    def __init__(self, api, *, fail_on_call=None):
        super().__init__(api)
        self.fail_on_call = fail_on_call

    def execute(self, packet):
        ordinal = len(self.calls) + 1
        if ordinal == self.fail_on_call:
            raise RuntimeError("terminal fake failure")
        result = super().execute(packet)
        result.update({
            "reservation_receipt": {
                "reservation_id": "reservation-%02d" % ordinal,
                "status": "RECONCILED",
            },
            "evidence_receipt": {
                "evidence_id": "evidence-%02d" % ordinal,
                "sha256": hashlib.sha256(("evidence-%02d" % ordinal).encode()).hexdigest(),
            },
            "report_surface": {
                "observed_total_tokens": ordinal * 10,
                "latency_ms": ordinal * 5,
                "promotion_eligible": False,
            },
        })
        return result


@pytest.mark.product_mandatory
def test_product_mandatory_partial_reports_exist_before_terminal_exception(tmp_path):
    """[BEHAVIORAL][RED][REPORT] JSON and MD survive a terminal call failure."""
    api = _api()
    approval, manifest, packets = _materials()
    adapter = _ReportAdapter(api, fail_on_call=7)
    post_arm = _SignedPostArmFake()

    with pytest.raises((RuntimeError, api.PilotBlockedError), match="terminal fake failure"):
        api.CodexSubscriptionPilot(
            adapter_factory=lambda: adapter, test_mode=True,
            post_arm_verifier=post_arm,
        ).run(
            approval=approval, manifest=manifest,
            required_test_receipt=_required_test_receipt(),
            frozen_packets=packets, dry_run=False,
            report_dir=tmp_path,
        )

    json_path = tmp_path / "partial_report.json"
    markdown_path = tmp_path / "partial_report.md"
    assert json_path.is_file() and markdown_path.is_file()
    partial = json.loads(json_path.read_bytes())
    assert partial["schema"] == "codex_product_pilot_partial_report.v1"
    assert partial["terminal"] is True
    assert partial["completed_call_count"] == 6
    assert [item["reservation_id"] for item in partial["completed_reservations"]] == [
        "reservation-%02d" % ordinal for ordinal in range(1, 7)
    ]
    assert [item["evidence_id"] for item in partial["completed_evidence"]] == [
        "evidence-%02d" % ordinal for ordinal in range(1, 7)
    ]
    assert len(partial["post_arm_verification_receipts"]) == 2
    assert partial["pace_status"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert partial["promotion_eligible"] is False
    assert partial["routing_recommendation"] is None
    rendered = markdown_path.read_text(encoding="utf-8")
    assert "PILOT_ONLY/NO_ROUTING_PROMOTION" in rendered
    assert "6" in rendered
    assert "terminal fake failure" in rendered


@pytest.mark.product_mandatory
def test_product_mandatory_final_report_blinds_receipts_and_selects_quality_tokens_latency(
        monkeypatch, tmp_path):
    """[BEHAVIORAL][RED][REPORT] Blinded selection is quality, then tokens, then latency."""
    api = _api()
    approval, manifest, packets = _materials()
    adapter = _ReportAdapter(api)
    _install_fake_pinned_openssl(api, monkeypatch, tmp_path)
    authority, _ = api.create_product_verifier_authority(tmp_path / "report-authority")
    post_arm = _ActualSignedPostArm(
        api, authority, tmp_path / "signed-post-arm-receipts",
    )
    receipts = [
        {"case_id": "P1", "opaque_artifact_id": "opaque-p1-a",
         "quality_score": 0.9, "observed_tokens": 100, "latency_ms": 20},
        {"case_id": "P1", "opaque_artifact_id": "opaque-p1-b",
         "quality_score": 0.9, "observed_tokens": 90, "latency_ms": 30},
        {"case_id": "P2", "opaque_artifact_id": "opaque-p2-a",
         "quality_score": 0.95, "observed_tokens": 120, "latency_ms": 40},
        {"case_id": "P2", "opaque_artifact_id": "opaque-p2-b",
         "quality_score": 0.9, "observed_tokens": 80, "latency_ms": 10},
        {"case_id": "P3", "opaque_artifact_id": "opaque-p3-a",
         "quality_score": 0.9, "observed_tokens": 100, "latency_ms": 30},
        {"case_id": "P3", "opaque_artifact_id": "opaque-p3-b",
         "quality_score": 0.9, "observed_tokens": 100, "latency_ms": 20},
    ]

    api.CodexSubscriptionPilot(
        adapter_factory=lambda: adapter, test_mode=True,
        post_arm_verifier=post_arm,
    ).run(
        approval=approval, manifest=manifest,
        required_test_receipt=_required_test_receipt(),
        frozen_packets=packets, dry_run=False,
        blinded_verifier_packet={
            "schema": "blinded_product_verifier_packet.v1",
            "receipts": receipts,
        },
        report_dir=tmp_path,
    )

    final_json = tmp_path / "final_report.json"
    final_markdown = tmp_path / "final_report.md"
    assert final_json.is_file() and final_markdown.is_file()
    report = json.loads(final_json.read_bytes())
    assert report["schema"] == "codex_product_pilot_final_report.v1"
    assert report["selection_basis"] == [
        "quality_desc", "observed_tokens_asc", "latency_ms_asc",
    ]
    assert report["selected_artifacts"] == {
        "P1": "opaque-p1-b",
        "P2": "opaque-p2-a",
        "P3": "opaque-p3-b",
    }
    assert report["blinded_verifier_receipts"] == receipts
    assert len(report["post_arm_verification_receipts"]) == 6
    assert [item["reservation_id"] for item in report["completed_reservations"]] == [
        "reservation-%02d" % ordinal for ordinal in range(1, 10)
    ]
    assert [item["evidence_id"] for item in report["completed_evidence"]] == [
        "evidence-%02d" % ordinal for ordinal in range(1, 10)
    ]
    blinded = json.dumps(report["blinded_verifier_receipts"], sort_keys=True)
    for forbidden in (
        "gpt-5.6-terra", "gpt-5.6-luna", "incumbent_coder", "challenger_coder",
    ):
        assert forbidden not in blinded
    assert report["pace_status"] == "PILOT_ONLY/NO_ROUTING_PROMOTION"
    assert report["promotion_eligible"] is False
    markdown = final_markdown.read_text(encoding="utf-8")
    for artifact_id in report["selected_artifacts"].values():
        assert artifact_id in markdown
    for field, identity in (
            ("completed_reservations", "reservation_id"),
            ("completed_evidence", "evidence_id"),
            ("post_arm_verification_receipts", "receipt_id")):
        for item in report[field]:
            assert item[identity] in markdown


@pytest.mark.product_mandatory
@pytest.mark.parametrize("receipt_mode", [
    pytest.param("missing", id="zero-receipts"),
    pytest.param("summary-only", id="six-unverified-summaries"),
])
def test_product_mandatory_final_report_requires_six_verified_signed_receipts(
        tmp_path, receipt_mode):
    """[BEHAVIORAL][RED][REPORT] Success requires six real verified post-arm records."""
    api = _api()
    approval, manifest, packets = _materials()
    adapter = _ReportAdapter(api)
    post_arm = None if receipt_mode == "missing" else _SignedPostArmFake()

    with pytest.raises(
            api.PilotBlockedError, match="six|6|signed|receipt|post-arm|verify"):
        api.CodexSubscriptionPilot(
            adapter_factory=lambda: adapter, test_mode=True,
            post_arm_verifier=post_arm,
        ).run(
            approval=approval, manifest=manifest,
            required_test_receipt=_required_test_receipt(),
            frozen_packets=packets, dry_run=False,
            report_dir=tmp_path,
        )

    assert not (tmp_path / "final_report.json").exists()
    assert not (tmp_path / "final_report.md").exists()


def test_effective_codex_argv_complete_real_argv_is_accepted_by_the_installed_codex_binary(
        tmp_path):
    """[BEHAVIORAL] Regression test for the AC1/AC2 --ask-for-approval-after-exec bug.

    Builds CodexPilotPreparer._effective_codex_argv's REAL, complete, current output
    shape -- read directly from the function body, not inferred from spec prose or a
    stripped-down subset -- for the "smoke" role, which is the role that makes this
    builder emit every flag it produces, including the conditional
    --skip-git-repo-check. This builder's own return value never contains a bare
    prompt/task token (per the spec Context, it only records a value for packet
    bookkeeping and never itself drives a live process), so per AC4's "or appends
    --help" branch, --help is appended rather than substituted for a token that does not
    exist here. The resulting argv is executed via subprocess.run against the REAL
    installed codex binary -- never the fake/mock CLI the rest of this suite uses.

    This MUST currently fail: --ask-for-approval is still placed after the `exec` token
    in this builder's output, and the real codex-cli 0.41.0 binary rejects that argv
    with exit code 2 (clap requires this global flag to precede `exec`, not follow it).
    It MUST pass once AC2's fix moves the pair to precede `exec`.

    The assertions below use index()-based adjacency checks (never an absolute-position
    index past argv[0]) precisely so this test does not itself become a third
    "hardcodes the buggy token order" test like the two AC2 already names for the Coder
    to fix -- the subprocess exit-code assertion is the one thing that must flip
    red -> green when the reorder lands, not a frozen positional snapshot of the bug.
    """
    api = _api()
    codex_path = shutil.which("codex")
    assert codex_path == "/opt/homebrew/bin/codex", (
        "_effective_codex_argv hardcodes /opt/homebrew/bin/codex as argv[0]; this "
        "environment's installed codex resolves to %r instead, so this real-binary "
        "regression test cannot validly run here" % (codex_path,)
    )
    clone_path = str(tmp_path / "clone")
    Path(clone_path).mkdir()
    final_path = str(tmp_path / "final.txt")
    slot = {
        "ordinal": 0,
        "case_id": "smoke",
        "role": "smoke",
        "model": "gpt-5.6-sol",
        "effort": "high",
        "sandbox": "read-only",
        "clone_path": clone_path,
    }

    argv_lists = api.CodexPilotPreparer._effective_codex_argv(slot, final_path=final_path)

    assert isinstance(argv_lists, list) and len(argv_lists) == 1
    argv = list(argv_lists[0])
    assert len(argv) == 15, "unexpected flag count -- builder's real shape has changed: %r" % (argv,)
    assert argv[0] == "/opt/homebrew/bin/codex"
    assert argv[argv.index("--cd") + 1] == clone_path
    assert argv[argv.index("--model") + 1] == "gpt-5.6-sol"
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[argv.index("--ask-for-approval") + 1] == "never"
    assert argv[argv.index("-c") + 1] == "model_reasoning_effort=high"
    assert argv[argv.index("--output-last-message") + 1] == final_path
    assert "--skip-git-repo-check" in argv
    assert "--json" not in argv  # confirmed unique to CodexExecAdapter._argv(), not this builder
    assert "-" not in argv  # ditto for the trailing bare stdin-prompt marker

    probe_argv = argv + ["--help"]

    result = subprocess.run(
        probe_argv, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 0, (
        "expected the REAL codex binary to accept _effective_codex_argv's complete, "
        "current frozen argv (with --help appended in place of the absent prompt/task "
        "token) once --ask-for-approval correctly precedes exec; got exit code %r, "
        "stdout=%r, stderr=%r" % (result.returncode, result.stdout, result.stderr)
    )
