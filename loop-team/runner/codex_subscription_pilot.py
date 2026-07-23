"""Authority-gated controller for the fixed non-promoting Codex pilot."""
from __future__ import annotations

import argparse
import base64
import ctypes
import ctypes.util
import dataclasses
import errno
import hashlib
import inspect
import json
import os
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    from .codex_exec_adapter import (
        CodexExecAdapter,
        CodexExecRequest,
        ProductionSeatbeltPreflight,
    )
except ImportError:  # Direct script execution.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runner.codex_exec_adapter import (
        CodexExecAdapter,
        CodexExecRequest,
        ProductionSeatbeltPreflight,
    )

SPEC_SHA256 = "eab8f4f80758beaf2ea3326df4a176e091778a0f9dbea23dbf5cccea633d06e8"
PROMOTION_BOUNDARY = "PILOT_ONLY/NO_ROUTING_PROMOTION"
EXACT_CAPS = {
    "combined_calls": 10,
    "combined_timeout_seconds": 9000,
    "aggregate_observed_tokens_max_when_telemetry_exists": 1500000,
    "subscription_allowance_units_max": 10,
}
EXACT_CALL_PLAN = [
    ["smoke", "gpt-5.6-sol", "high"],
    *[["planner", "gpt-5.6-sol", "high"] for _ in range(3)],
    *[["incumbent_coder", "gpt-5.6-terra", "high"] for _ in range(3)],
    *[["challenger_coder", "gpt-5.6-luna", "medium"] for _ in range(3)],
]
DESCRIPTOR_TEST_CALL_PLAN = (
    ["smoke", "gpt-5.6-sol", "high"]
    + [["planner", "gpt-5.6-sol", "high"]] * 3
    + [["incumbent_coder", "gpt-5.6-terra", "high"]] * 3
    + [["challenger_coder", "gpt-5.6-luna", "medium"]] * 3
)
REQUIRED_GATE_MODULE_ORDER = (
    "loop-team/runner/tests/test_codex_subscription_adapter.py",
    "loop-team/runner/tests/test_codex_exec_adapter.py",
    "loop-team/runner/tests/test_codex_subscription_pilot.py",
    "loop-team/runner/tests/test_experiment_execution_contract.py",
    "loop-team/experiments/test_model_routing_pace_contract.py",
    "loop-team/evals/test_model_routing_evals_contract.py",
)
REQUIRED_GATE_MODULES = frozenset(REQUIRED_GATE_MODULE_ORDER)
REQUIRED_MATERIALS = frozenset({"prompt", "plan", "oracle", "test", "dependency", "preprobe"})
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
REQUIRED_COMPATIBILITY_ASSERTIONS = frozenset({
    "codex_cli_041_argv_and_effort_domain",
    "installed_and_current_jsonl_usage_schemas",
    "session_configured_identity_and_unknown_stop",
    "smoke_read_only_no_tools_and_codex_state_disclosure",
    "no_provider_preflight_before_popen",
    "codex_subscription_has_no_usd_accounting",
})
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
PRODUCTION_POPEN_FACTORY = subprocess.Popen
CONCRETE_PRODUCTION_PREFLIGHT_TYPE = ProductionSeatbeltPreflight
# Captured at import time (like the two constants above) so that tests which
# monkeypatch the module-level `CodexExecAdapter` name to a fake class cannot
# turn a live `CodexExecAdapter._real_codex_argv_probe` attribute lookup inside
# `_run_production` into an AttributeError on the fake.
_REAL_CODEX_EXEC_ADAPTER_ARGV_PROBE = CodexExecAdapter._real_codex_argv_probe
PRODUCTION_RUN_ARTIFACT_ROOT: Optional[Path] = None
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
P3_TARGET_ARGV = [
    "npm", "run", "prerequisite:doctor", "--", "--project-id",
    "padsplit-cockpit", "--alias", "PMS Cockpit", "--json",
]
P3_PREDICATES = (
    "generated_prisma_client", "database_url", "app_endpoint", "organization_token",
)
PINNED_OPENSSL_PATH = Path("/opt/homebrew/Cellar/openssl@3/3.6.2/bin/openssl")
PINNED_OPENSSL_SHA256 = (
    "bf63843e6856e1994ca71092ff3b46834236eb2144dd9b6ceb85d511128b836e"
)
PINNED_OPENSSL_VERSION = (
    "OpenSSL 3.6.2 7 Apr 2026 (Library: OpenSSL 3.6.2 7 Apr 2026)"
)
PINNED_BUN_PATH = Path("/opt/homebrew/Cellar/bun/1.3.14/bin/bun")
PINNED_BUN_VERSION = "1.3.14"
PINNED_BUN_SHA256 = (
    "fb46ac6497104821512b67a3b3157c9fbbab8a99e311fb38da5b7039a373d860"
)
PINNED_BUN_MODE = 0o555
PINNED_BUN_SIZE = 61512816
PINNED_TYPESCRIPT_VERSION = "5.9.3"
REQUIRED_PRODUCT_MANDATORY_TESTS = (
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


class PilotBlockedError(RuntimeError):
    code = "PILOT_ABORTED"


def _json_compatible(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "schema": type(value).__name__,
            **{
                field.name: _json_compatible(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_compatible(item) for item in value), key=lambda item: json.dumps(
            item, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"schema": "bytes", "hex": value.hex()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("value is not canonically JSON-compatible: " + type(value).__name__)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_compatible(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _canonical_json(value: Any) -> str:
    return _canonical_bytes(value).decode("utf-8")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def packet_hash(packet: Dict[str, Any]) -> str:
    payload = json.loads(json.dumps(packet))
    payload.pop("packet_hash", None)
    payload.pop("reverified_packet_hash", None)
    authority = payload.get("immutable_authority")
    if isinstance(authority, dict):
        authority.pop("packet_hash", None)
    return _canonical_hash(payload)


def manifest_hash(manifest: Dict[str, Any]) -> str:
    payload = json.loads(json.dumps(manifest))
    payload.pop("manifest_hash", None)
    packets = []
    smoke = payload.get("smoke_packet")
    if isinstance(smoke, dict):
        packets.append(smoke)
    frozen = payload.get("frozen_packets")
    if isinstance(frozen, list):
        packets.extend(packet for packet in frozen if isinstance(packet, dict))
    for packet in packets:
        authority = packet.get("immutable_authority")
        if not isinstance(authority, dict):
            continue
        packet.pop("packet_hash", None)
        packet.pop("reverified_packet_hash", None)
        authority.pop("packet_hash", None)
        authority.pop("approval_hash", None)
        authority.pop("manifest_hash", None)
    return _canonical_hash(payload)


def approval_hash(approval: Dict[str, Any]) -> str:
    payload = json.loads(json.dumps(approval))
    payload.pop("approval_hash", None)
    confirmation = payload.get("human_confirmation")
    if isinstance(confirmation, dict):
        confirmation.pop("approval_hash", None)
    return _canonical_hash(payload)


def _task_identity(ordinal: int, call: list[str]) -> Dict[str, Any]:
    role = call[0]
    if ordinal == 0:
        case_id = "smoke"
    else:
        case_id = "P%d" % (((ordinal - 1) % 3) + 1)
    return {"ordinal": ordinal, "case_id": case_id, "role": role}


class CodexSubscriptionPilot:
    def __init__(self, *, adapter_factory: Any, test_mode: bool = False,
                 post_arm_verifier: Any = None, argv_probe: Any = None) -> None:
        if not callable(adapter_factory):
            raise TypeError("adapter_factory must be callable")
        if post_arm_verifier is not None and not callable(getattr(
                post_arm_verifier, "verify_after_coder", None)):
            raise TypeError("post_arm_verifier must expose verify_after_coder")
        if argv_probe is not None and not callable(argv_probe):
            raise TypeError("argv_probe must be callable")
        self.adapter_factory = adapter_factory
        self.test_mode = test_mode
        self.post_arm_verifier = post_arm_verifier
        # Injectable real-binary argv-acceptance seam (mirrors the popen_factory/
        # test_mode pattern used elsewhere in this module). None (the default) is a
        # deliberate no-op: only `_run_production` wires a real probe explicitly, so
        # every test that does not inject one stays hermetic by construction rather
        # than by relying on `test_mode`'s value (see `_validate_smoke_packet`'s
        # sibling method below for why `test_mode` alone is not a safe gate here).
        self.argv_probe = argv_probe

    def run(self, *, approval: Dict[str, Any], manifest: Dict[str, Any],
            required_test_receipt: Dict[str, Any], frozen_packets: Iterable[Dict[str, Any]],
            dry_run: bool, blinded_verifier_packet: Optional[Dict[str, Any]] = None,
            report_dir: Any = None) -> Dict[str, Any]:
        packets = list(frozen_packets)
        report_root = Path(report_dir) if report_dir is not None else None
        try:
            execution_packets = self._validate(
                approval, manifest, required_test_receipt, packets, dry_run=dry_run,
            )
        except Exception as exc:
            if report_root is not None:
                self._write_report_journal(
                    report_root, terminal=True, results=[],
                    post_arm_receipts=[], error=exc,
                )
            raise
        report = {
            "pace_status": PROMOTION_BOUNDARY,
            "promotion_eligible": False,
            "routing_recommendation": None,
            "usd_cost": None,
            "integration_applied": False,
            "routing_promotion": "NO_ROUTING_PROMOTION",
            "possible_codex_state_disclosure": (
                "codex-cli-0.41.0-has-no-ephemeral-and-may-write-under-~/.codex"
            ),
            "blinded_verifier_packet": blinded_verifier_packet,
        }
        if dry_run:
            return report
        if not self.test_mode and type(self.post_arm_verifier) is not ProductionPostArmController:
            raise PilotBlockedError(
                "production execution requires the concrete signed post-arm verifier"
            )
        adapter = self.adapter_factory() if self.test_mode else None
        results = []
        post_arm_receipts = []
        planner_handoffs: Dict[str, Dict[str, Any]] = {}
        try:
            for sealed_packet in execution_packets:
                packet = sealed_packet
                role = packet.get("task_identity", {}).get("role")
                case_id = packet.get("task_identity", {}).get("case_id")
                if role in {"incumbent_coder", "challenger_coder"}:
                    if set(planner_handoffs) != {"P1", "P2", "P3"}:
                        raise PilotBlockedError(
                            "every planner output must parse and PLAN_PASS before any coder starts"
                        )
                    packet = self._derive_coder_packet(
                        sealed_packet, planner_handoffs.get(case_id),
                    )
                if not self.test_mode:
                    adapter = self.adapter_factory()
                    if type(adapter) is not CodexExecAdapter:
                        raise PilotBlockedError(
                            "production execution requires the concrete Codex adapter"
                        )
                execution_input: Any = packet
                if not self.test_mode:
                    execution_input = self._production_request(packet)
                result = adapter.execute(execution_input)
                if self._promotion_eligible(result):
                    raise PilotBlockedError("adapter result attempted to promote pilot evidence")
                self._validate_observed_result(packet, result)
                if role in {"incumbent_coder", "challenger_coder"} and isinstance(
                        packet.get("product_git_authority"), dict):
                    ProductGitAuthority.verify(
                        packet["cwd"], packet["product_git_authority"],
                        expected_commit=packet["product_git_authority"]["head"],
                    )
                if role == "planner":
                    if case_id in planner_handoffs:
                        raise PilotBlockedError("planner output is duplicated for a product case")
                    planner_handoffs[case_id] = self._parse_planner_output(packet, result)
                if role in {"incumbent_coder", "challenger_coder"}:
                    if self.post_arm_verifier is None:
                        if not self.test_mode:
                            raise PilotBlockedError("coder result lacks mandatory post-arm verifier")
                    else:
                        post_arm = self.post_arm_verifier.verify_after_coder(
                            packet=packet, result=result,
                        )
                        if not isinstance(post_arm, dict) or post_arm.get(
                                "schema") != "controller_post_arm_receipt.v1" or post_arm.get(
                                    "status") != "PASS" or post_arm.get(
                                        "signed") is not True or post_arm.get(
                                            "promotion_eligible") is not False:
                            raise PilotBlockedError(
                                "coder result post-arm verification receipt is invalid"
                            )
                        post_arm_receipts.append(post_arm)
                results.append(result)
                if report_root is not None:
                    self._write_report_journal(
                        report_root, terminal=False, results=results,
                        post_arm_receipts=post_arm_receipts,
                    )
        except Exception as exc:
            if report_root is not None:
                self._write_report_journal(
                    report_root, terminal=True, results=results,
                    post_arm_receipts=post_arm_receipts, error=exc,
                )
            raise
        try:
            if len(results) != EXACT_CAPS["combined_calls"]:
                raise PilotBlockedError("the controller must execute exactly ten calls")
            report["calls_started"] = len(results)
            report["execution_results"] = results
            report["post_arm_verification_receipts"] = post_arm_receipts
            if report_root is not None:
                post_arm_receipts = self._verify_six_signed_post_arm_receipts(
                    post_arm_receipts,
                )
                report["post_arm_verification_receipts"] = post_arm_receipts
                report.update(self._write_final_report(
                    report_root, results=results,
                    post_arm_receipts=post_arm_receipts,
                    blinded_verifier_packet=blinded_verifier_packet,
                ))
        except Exception as exc:
            if report_root is not None:
                self._write_report_journal(
                    report_root, terminal=True, results=results,
                    post_arm_receipts=post_arm_receipts, error=exc,
                )
            raise
        return report

    @staticmethod
    def _parse_planner_output(packet: Dict[str, Any], result: Any) -> Dict[str, Any]:
        raw = result.get("planner_output") if isinstance(result, dict) else getattr(
            result, "final_output", None,
        )
        claimed_hash = result.get("planner_output_sha256") if isinstance(
            result, dict) else None
        if not isinstance(raw, str) or not raw.endswith("\n"):
            raise PilotBlockedError("planner output is missing or not canonical JSON")
        payload_bytes = raw.encode("utf-8")
        digest = hashlib.sha256(payload_bytes).hexdigest()
        if claimed_hash is not None and claimed_hash != digest:
            raise PilotBlockedError("planner output hash differs from returned bytes")
        try:
            plan = json.loads(raw)
        except ValueError as exc:
            raise PilotBlockedError("planner output could not parse as JSON") from exc
        required = {"schema", "status", "case_id", "allowed_paths", "steps", "checks"}
        task = packet.get("task_identity", {})
        valid = (
            isinstance(plan, dict) and set(plan) == required
            and plan.get("schema") == "product_planner_output.v1"
            and plan.get("status") == "PLAN_PASS"
            and plan.get("case_id") == task.get("case_id")
            and isinstance(plan.get("allowed_paths"), list)
            and bool(plan["allowed_paths"])
            and len(plan["allowed_paths"]) == len(set(plan["allowed_paths"]))
            and all(isinstance(path, str) and path and not os.path.isabs(path)
                    and ".." not in Path(path).parts for path in plan["allowed_paths"])
            and isinstance(plan.get("steps"), list) and bool(plan["steps"])
            and all(isinstance(step, dict) and set(step) == {"id", "action"}
                    and all(isinstance(step[key], str) and step[key]
                            for key in ("id", "action")) for step in plan["steps"])
            and isinstance(plan.get("checks"), list) and bool(plan["checks"])
            and all(isinstance(check, str) and check for check in plan["checks"])
            and payload_bytes == _canonical_bytes(plan) + b"\n"
        )
        sealed_allowlist = packet.get("allowed_patch_paths")
        if valid and isinstance(sealed_allowlist, list):
            valid = set(plan["allowed_paths"]).issubset(set(sealed_allowlist))
        if not valid:
            raise PilotBlockedError("planner output failed deterministic local plan-check")
        return {
            "schema": "planner_handoff.v1", "status": "PLAN_PASS",
            "case_id": plan["case_id"], "plan_checked": True,
            "coder_packet_derived": True,
            "planner_output_sha256": digest, "plan": plan,
        }

    @staticmethod
    def _derive_coder_packet(packet: Dict[str, Any],
                             handoff: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(handoff, dict) or handoff.get("status") != "PLAN_PASS" or handoff.get(
                "case_id") != packet.get("task_identity", {}).get("case_id"):
            raise PilotBlockedError("coder packet cannot be derived without its valid planner")
        derived = json.loads(json.dumps(packet))
        derived["parent_packet_hash"] = packet.get("packet_hash")
        derived["planner_handoff"] = handoff
        materials = derived.get("sealed_materials")
        prompt_material = materials.get("prompt") if isinstance(materials, dict) else None
        original_prompt_path = prompt_material.get("path") if isinstance(
            prompt_material, dict) else None
        artifact_root = derived.get("artifact_root")
        if isinstance(original_prompt_path, str) and Path(original_prompt_path).is_file() and isinstance(
                artifact_root, str) and Path(artifact_root).is_dir():
            original_prompt = Path(original_prompt_path).read_bytes()
            handoff_bytes = _canonical_bytes(handoff) + b"\n"
            derived_root = Path(artifact_root) / "planner-derived"
            writer = _AtomicPreparationWriter()
            prompt_path = writer.write_bytes(
                derived_root / "prompt.txt",
                original_prompt + b"\nPLANNER_HANDOFF_JSON=" + handoff_bytes,
            )
            plan_path = writer.write_bytes(
                derived_root / "plan.json", _canonical_bytes(handoff["plan"]) + b"\n",
            )
            old_plan_path = materials.get("plan", {}).get("path")
            materials["prompt"] = {
                "path": str(prompt_path),
                "sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
            }
            materials["plan"] = {
                "path": str(plan_path),
                "sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            }
            allowed_files = derived.get("allowed_files")
            if isinstance(allowed_files, list):
                derived["allowed_files"] = [
                    str(prompt_path) if value == original_prompt_path else
                    str(plan_path) if value == old_plan_path else value
                    for value in allowed_files
                ]
        authority = derived.get("immutable_authority")
        if isinstance(authority, dict):
            authority["packet_hash"] = "0" * 64
        derived["packet_hash"] = "0" * 64
        derived["reverified_packet_hash"] = "0" * 64
        digest = packet_hash(derived)
        derived["packet_hash"] = digest
        derived["reverified_packet_hash"] = digest
        if isinstance(authority, dict):
            authority["packet_hash"] = digest
        return derived

    @staticmethod
    def _atomic_replace(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(".%s.%s.tmp" % (path.name, uuid.uuid4().hex))
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    @staticmethod
    def _completed_evidence(results: list[Any], key: str, identity: str) -> list[Dict[str, Any]]:
        values = []
        for result in results:
            value = result.get(key) if isinstance(result, dict) else getattr(
                result, "report_surface", {}
            ).get(key)
            if isinstance(value, dict) and isinstance(value.get(identity), str):
                values.append(json.loads(json.dumps(value)))
        return values

    @classmethod
    def _write_report_journal(cls, root: Path, *, terminal: bool,
                              results: list[Any], post_arm_receipts: list[Dict[str, Any]],
                              error: Optional[BaseException] = None) -> Dict[str, Any]:
        report = {
            "schema": "codex_product_pilot_partial_report.v1",
            "terminal": terminal,
            "completed_call_count": len(results),
            "completed_reservations": cls._completed_evidence(
                results, "reservation_receipt", "reservation_id",
            ),
            "completed_evidence": cls._completed_evidence(
                results, "evidence_receipt", "evidence_id",
            ),
            "post_arm_verification_receipts": json.loads(json.dumps(post_arm_receipts)),
            "terminal_error": None if error is None else str(error),
            "terminal_observation": (
                getattr(error, "observation", None) if error is not None else None
            ),
            "pace_status": PROMOTION_BOUNDARY,
            "promotion_eligible": False, "routing_recommendation": None,
            "integration_applied": False, "usd_cost": None,
        }
        markdown = "\n".join((
            "# Codex Product Pilot Partial Report",
            "", "- pace_status: `%s`" % PROMOTION_BOUNDARY,
            "- completed calls: `%d`" % len(results),
            "- terminal: `%s`" % str(terminal).lower(),
            "- terminal error: `%s`" % (str(error) if error is not None else "none"),
            "- promotion eligible: `false`", "- integration applied: `false`",
            "- USD authority: `unavailable`", "", "## Completed Reservations", "",
            *(
                "- `%s`" % item["reservation_id"]
                for item in report["completed_reservations"]
            ),
            "", "## Completed Evidence", "",
            *(
                "- `%s`" % item["evidence_id"]
                for item in report["completed_evidence"]
            ),
            "", "## Post-Arm Receipts", "",
            *(
                "- `%s`" % item.get("receipt_id", "missing")
                for item in report["post_arm_verification_receipts"]
            ),
            "",
        )).encode("utf-8")
        cls._atomic_replace(root / "partial_report.json", _canonical_bytes(report) + b"\n")
        cls._atomic_replace(root / "partial_report.md", markdown)
        return report

    @staticmethod
    def _blinded_selection(packet: Optional[Dict[str, Any]]) -> tuple[list[Dict[str, Any]], Dict[str, str]]:
        if packet is None:
            return [], {}
        if not isinstance(packet, dict) or packet.get(
                "schema") != "blinded_product_verifier_packet.v1" or not isinstance(
                    packet.get("receipts"), list):
            raise PilotBlockedError("blinded verifier packet is invalid")
        receipts = json.loads(json.dumps(packet["receipts"]))
        forbidden = {"model", "effort", "role", "arm", "planner_rationale"}
        for receipt in receipts:
            if not isinstance(receipt, dict) or forbidden.intersection(receipt):
                raise PilotBlockedError("blinded verifier receipt disclosed arm identity")
            required = {
                "case_id", "opaque_artifact_id", "quality_score",
                "observed_tokens", "latency_ms",
            }
            if set(receipt) != required or not isinstance(receipt["case_id"], str) or not isinstance(
                    receipt["opaque_artifact_id"], str) or not isinstance(
                        receipt["quality_score"], (int, float)) or type(
                            receipt["observed_tokens"]) is not int or receipt[
                                "observed_tokens"] < 0 or type(receipt["latency_ms"]) is not int or receipt[
                                    "latency_ms"] < 0:
                raise PilotBlockedError("blinded verifier receipt is incomplete")
        selected: Dict[str, str] = {}
        for case_id in sorted({receipt["case_id"] for receipt in receipts}):
            candidates = [receipt for receipt in receipts if receipt["case_id"] == case_id]
            ordered = sorted(candidates, key=lambda receipt: (
                -receipt["quality_score"], receipt["observed_tokens"], receipt["latency_ms"],
            ))
            if len(ordered) == 1 or (
                    ordered[0]["quality_score"], ordered[0]["observed_tokens"], ordered[0]["latency_ms"]
            ) != (
                    ordered[1]["quality_score"], ordered[1]["observed_tokens"], ordered[1]["latency_ms"]
            ):
                selected[case_id] = ordered[0]["opaque_artifact_id"]
        return receipts, selected

    @classmethod
    def _write_final_report(cls, root: Path, *, results: list[Any],
                            post_arm_receipts: list[Dict[str, Any]],
                            blinded_verifier_packet: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        receipts, selected = cls._blinded_selection(blinded_verifier_packet)
        provisional = {
            "schema": "blinded_product_selection_provisional.v1",
            "blinded_verifier_receipts": receipts,
            "selection_basis": [
                "quality_desc", "observed_tokens_asc", "latency_ms_asc",
            ],
            "selected_artifacts": selected,
            "identity_unblinded": False,
            "promotion_eligible": False,
        }
        cls._atomic_replace(
            root / "blinded_provisional.json", _canonical_bytes(provisional) + b"\n",
        )
        cls._atomic_replace(
            root / "blinded_provisional.md",
            ("# Blinded Provisional Selection\n\n" + "\n".join(
                "- %s: `%s`" % item for item in sorted(selected.items())
            ) + "\n").encode("utf-8"),
        )
        completed_reservations = cls._completed_evidence(
            results[:9], "reservation_receipt", "reservation_id",
        )
        completed_evidence = cls._completed_evidence(
            results[:9], "evidence_receipt", "evidence_id",
        )
        report = {
            "schema": "codex_product_pilot_final_report.v1",
            "completed_call_count": len(results),
            "completed_reservations": completed_reservations,
            "completed_evidence": completed_evidence,
            "post_arm_verification_receipts": json.loads(json.dumps(post_arm_receipts)),
            "blinded_verifier_receipts": receipts,
            "selection_basis": [
                "quality_desc", "observed_tokens_asc", "latency_ms_asc",
            ],
            "selected_artifacts": selected,
            "pace_status": PROMOTION_BOUNDARY,
            "promotion_eligible": False, "routing_recommendation": None,
            "integration_applied": False, "usd_cost": None,
        }
        lines = [
            "# Codex Product Pilot Final Report", "",
            "- pace_status: `%s`" % PROMOTION_BOUNDARY,
            "- promotion eligible: `false`", "- integration applied: `false`",
            "- USD authority: `unavailable`", "", "## Blinded Selection", "",
        ]
        lines.extend("- %s: `%s`" % item for item in sorted(selected.items()))
        lines.extend(["", "## Completed Reservations", ""])
        lines.extend("- `%s`" % item["reservation_id"] for item in completed_reservations)
        lines.extend(["", "## Completed Evidence", ""])
        lines.extend("- `%s`" % item["evidence_id"] for item in completed_evidence)
        lines.extend(["", "## Post-Arm Receipts", ""])
        lines.extend("- `%s`" % item["receipt_id"] for item in post_arm_receipts)
        lines.append("")
        cls._atomic_replace(root / "final_report.json", _canonical_bytes(report) + b"\n")
        cls._atomic_replace(root / "final_report.md", "\n".join(lines).encode("utf-8"))
        return {"final_report": report}

    def _verify_six_signed_post_arm_receipts(
            self, receipts: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        authority = getattr(self.post_arm_verifier, "authority", None)
        if len(receipts) != 6 or type(authority) is not ProductVerifierAuthority:
            raise PilotBlockedError(
                "final success requires six actual signed post-arm verifier receipts"
            )
        expected_pairs = {
            (case_id, role)
            for case_id in ("P1", "P2", "P3")
            for role in ("incumbent_coder", "challenger_coder")
        }
        observed_pairs = set()
        receipt_ids = set()
        verified = []
        for summary in receipts:
            required = {
                "schema", "status", "signed", "case_id", "role",
                "opaque_artifact_id", "receipt_id", "receipt_path",
                "receipt_sha256", "promotion_eligible",
            }
            if not isinstance(summary, dict) or not required.issubset(summary) or summary.get(
                    "schema") != "controller_post_arm_receipt.v1" or summary.get(
                        "status") != "PASS" or summary.get("signed") is not True or summary.get(
                            "promotion_eligible") is not False or not _is_sha256(
                                summary.get("receipt_sha256")):
                raise PilotBlockedError("signed post-arm receipt summary is incomplete")
            path = Path(summary["receipt_path"])
            try:
                file_bytes = path.read_bytes()
                signed_record = json.loads(file_bytes)
            except (OSError, ValueError) as exc:
                raise PilotBlockedError("signed post-arm receipt record is unavailable") from exc
            if file_bytes != _canonical_bytes(signed_record) + b"\n" or hashlib.sha256(
                    file_bytes).hexdigest() != summary["receipt_sha256"]:
                raise PilotBlockedError("signed post-arm receipt bytes are not canonical or bound")
            if authority.verify_receipt(signed_record) is not True or any(
                    signed_record.get(key) != summary.get(key) for key in (
                        "case_id", "role", "opaque_artifact_id", "receipt_id",
                    )) or signed_record.get("schema") != "product_post_arm_verification.v1" or signed_record.get(
                        "status") != "PASS" or signed_record.get(
                            "quality_verdict") != "PASS" or signed_record.get(
                                "promotion_eligible") is not False:
                raise PilotBlockedError("post-arm receipt signature or evidence binding is invalid")
            observed_pairs.add((summary["case_id"], summary["role"]))
            receipt_ids.add(summary["receipt_id"])
            verified.append(json.loads(json.dumps(summary)))
        if observed_pairs != expected_pairs or len(receipt_ids) != 6:
            raise PilotBlockedError("six signed post-arm receipts do not cover both arms")
        return verified

    def _validate(self, approval: Dict[str, Any], manifest: Dict[str, Any],
                  tests: Dict[str, Any], packets: list[Dict[str, Any]], *,
                  dry_run: bool) -> list[Dict[str, Any]]:
        if dry_run:
            return self._validate_inert_dry_run(approval, manifest, tests, packets)
        if self.test_mode:
            return self._validate_sealed_fake(approval, manifest, tests, packets)
        if not isinstance(approval, dict) or approval.get("schema") != "experiment_approval.v2":
            raise PilotBlockedError("sealed approval is required")
        if approval.get("execution_mode") != "codex_subscription" or approval.get(
                "user_created") is not True:
            raise PilotBlockedError("explicit codex subscription approval is required")
        if not isinstance(manifest, dict) or manifest.get("schema") != "pace_manifest.v1":
            raise PilotBlockedError("sealed manifest is required")
        if manifest.get("manifest_hash") != manifest_hash(manifest):
            raise PilotBlockedError("manifest hash does not bind canonical manifest bytes")
        if approval.get("approval_hash") != approval_hash(approval):
            raise PilotBlockedError("approval hash does not bind canonical approval bytes")
        if approval.get("manifest_hash") != manifest["manifest_hash"]:
            raise PilotBlockedError("approval does not bind the frozen manifest")
        confirmation = approval.get("human_confirmation")
        if confirmation != {
                "schema": "user_confirmation.v1",
                "confirmed": True,
                "spec_sha256": SPEC_SHA256,
                "approval_hash": approval["approval_hash"],
                "manifest_hash": manifest["manifest_hash"],
                "promotion_boundary": PROMOTION_BOUNDARY,
        }:
            raise PilotBlockedError("exact immutable human confirmation is required")
        self._validate_test_receipt(tests, require_execution_proof=True)
        if manifest.get("call_plan") != EXACT_CALL_PLAN or approval.get(
                "call_plan") != EXACT_CALL_PLAN:
            raise PilotBlockedError("frozen call plan is not the exact ten-call plan")
        if manifest.get("caps") != EXACT_CAPS or approval.get("caps") != EXACT_CAPS:
            raise PilotBlockedError("frozen combined caps do not match")
        if manifest.get("promotion_boundary") != PROMOTION_BOUNDARY or approval.get(
                "promotion_boundary") != PROMOTION_BOUNDARY:
            raise PilotBlockedError("pilot promotion boundary is absent")
        if len(packets) != 9:
            raise PilotBlockedError("exactly nine frozen packets are required")
        smoke_packet = manifest.get("smoke_packet")
        execution_packets = [smoke_packet, *packets]
        if len(execution_packets) != 10:
            raise PilotBlockedError("the controller may execute exactly ten calls")
        for ordinal, (packet, call) in enumerate(zip(execution_packets, EXACT_CALL_PLAN)):
            self._validate_packet(packet, ordinal, call)
        return execution_packets

    def _validate_inert_dry_run(self, approval: Dict[str, Any], manifest: Dict[str, Any],
                                tests: Dict[str, Any], packets: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        if not isinstance(approval, dict) or approval.get("schema") != "experiment_approval.v2" or approval.get(
                "execution_mode") != "codex_subscription" or approval.get("user_created") is not True:
            raise PilotBlockedError("sealed approval is required")
        if not isinstance(manifest, dict) or manifest.get("schema") != "pace_manifest.v1":
            raise PilotBlockedError("sealed manifest is required")
        if tests.get("all_required_fake_cli_tests_passed") is not True:
            raise PilotBlockedError("required fake CLI test receipt is missing")
        call_plan = approval.get("call_plan")
        if approval.get("caps") != EXACT_CAPS or manifest.get("caps") != EXACT_CAPS or call_plan not in (
                EXACT_CALL_PLAN, DESCRIPTOR_TEST_CALL_PLAN) or manifest.get("call_plan") != call_plan:
            raise PilotBlockedError("dry-run caps or call plan differ from the frozen contract")
        if approval.get("promotion_boundary") != PROMOTION_BOUNDARY or manifest.get(
                "promotion_boundary") != PROMOTION_BOUNDARY or len(packets) != 9:
            raise PilotBlockedError("dry-run packet count or promotion boundary is invalid")
        return [manifest.get("smoke_packet"), *packets]

    def _validate_sealed_fake(self, approval: Dict[str, Any], manifest: Dict[str, Any],
                              tests: Dict[str, Any], packets: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        execution_packets = self._validate_inert_dry_run(approval, manifest, tests, packets)
        confirmation = approval.get("human_confirmation", {})
        expected = {
            "schema": "user_confirmation.v1", "confirmed": True,
            "spec_sha256": confirmation.get("spec_sha256"),
            "approval_hash": approval.get("approval_hash"),
            "manifest_hash": manifest.get("manifest_hash"),
            "promotion_boundary": PROMOTION_BOUNDARY,
        }
        if confirmation != expected or confirmation.get("spec_sha256") != SPEC_SHA256:
            raise PilotBlockedError("sealed fake confirmation is invalid")
        self._validate_test_receipt(tests)
        smoke = execution_packets[0]
        if not self._shallow_identity_is_sealed(smoke):
            raise PilotBlockedError("sealed fake smoke packet is invalid")
        for packet in execution_packets[1:]:
            if not self._shallow_identity_is_sealed(packet):
                raise PilotBlockedError("sealed fake packet identity changed")
            materials = packet.get("sealed_materials")
            if not isinstance(materials, dict) or set(materials) != REQUIRED_MATERIALS or not _is_sha256(
                    packet.get("baseline_tree_hash")):
                raise PilotBlockedError("sealed fake packet materials are incomplete")
            if any(not isinstance(material, dict) or not isinstance(material.get("path"), str)
                   or not _is_sha256(material.get("sha256")) for material in materials.values()):
                raise PilotBlockedError("sealed fake material descriptor is invalid")
        return execution_packets

    @staticmethod
    def _shallow_identity_is_sealed(packet: Any) -> bool:
        return (
            isinstance(packet, dict)
            and isinstance(packet.get("packet_hash"), str) and bool(packet["packet_hash"])
            and isinstance(packet.get("clone_tree_hash"), str) and bool(packet["clone_tree_hash"])
            and packet.get("reverified_packet_hash") == packet["packet_hash"]
            and packet.get("reverified_clone_tree_hash") == packet["clone_tree_hash"]
        )

    @staticmethod
    def _validate_test_receipt(tests: Dict[str, Any], *,
                               require_execution_proof: bool = False) -> None:
        if not isinstance(tests, dict) or tests.get(
                "all_required_fake_cli_tests_passed") is not True:
            raise PilotBlockedError("required fake CLI test receipt is missing")
        modules = tests.get("executed_test_modules")
        if not isinstance(modules, list) or len(modules) != len(set(modules)) or not all(
                isinstance(module, str) for module in modules) or not REQUIRED_GATE_MODULES.issubset(
                    modules):
            raise PilotBlockedError("required adapter and runner test modules were not all executed")
        compatibility = tests.get("compatibility_assertions")
        if not isinstance(compatibility, list) or len(compatibility) != len(set(compatibility)) or set(
                compatibility) != REQUIRED_COMPATIBILITY_ASSERTIONS:
            raise PilotBlockedError("required Codex 0.41.0 compatibility assertions are incomplete")
        if require_execution_proof:
            if modules != list(REQUIRED_GATE_MODULE_ORDER):
                raise PilotBlockedError("required test module order is not exact")
            command = ["python3", "-m", "pytest", *REQUIRED_GATE_MODULE_ORDER, "-q"]
            if tests.get("command") != command or tests.get("command_sha256") != _canonical_hash(
                    command):
                raise PilotBlockedError("required test command or hash is not exact")
            subprocess_receipts = tests.get("subprocess_receipts")
            expected_commands = [
                command,
                *[["python3", "-m", "pytest", module, "-q"] for module in modules],
                list(RequiredTestGateRunner.PRODUCT_COMMAND),
            ]
            if not isinstance(subprocess_receipts, list) or len(subprocess_receipts) != 8:
                raise PilotBlockedError(
                    "required executed test subprocess receipt count/artifact is incomplete"
                )
            parsed_receipts = []
            for index, (receipt, expected_command) in enumerate(zip(
                    subprocess_receipts, expected_commands)):
                expected_kind = (
                    "combined" if index == 0 else
                    "product_mandatory" if index == len(expected_commands) - 1 else "module"
                )
                expected_module = None if expected_kind != "module" else modules[index - 1]
                if not isinstance(receipt, dict) or receipt.get("kind") != expected_kind or receipt.get(
                        "module") != expected_module or receipt.get(
                            "command") != expected_command or receipt.get(
                                "command_sha256") != _canonical_hash(expected_command):
                    raise PilotBlockedError("required test subprocess command or order is invalid")
                artifact_path = receipt.get("execution_artifact_path")
                artifact_sha256 = receipt.get("execution_artifact_sha256")
                if not isinstance(artifact_path, str) or not _is_sha256(artifact_sha256):
                    raise PilotBlockedError("required test subprocess artifact is missing")
                try:
                    artifact_bytes = Path(artifact_path).read_bytes()
                    artifact = json.loads(artifact_bytes.decode("utf-8"))
                except (OSError, UnicodeError, ValueError) as exc:
                    raise PilotBlockedError("required test subprocess artifact is invalid") from exc
                if hashlib.sha256(artifact_bytes).hexdigest() != artifact_sha256:
                    raise PilotBlockedError("required test subprocess artifact digest changed")
                stdout = artifact.get("stdout") if isinstance(artifact, dict) else None
                stderr = artifact.get("stderr") if isinstance(artifact, dict) else None
                if not isinstance(stdout, str) or not isinstance(stderr, str) or artifact.get(
                        "kind") != expected_kind or artifact.get("module") != expected_module or artifact.get(
                            "command") != expected_command or receipt.get(
                                "stdout_sha256") != hashlib.sha256(stdout.encode("utf-8")).hexdigest() or receipt.get(
                                    "stderr_sha256") != hashlib.sha256(stderr.encode("utf-8")).hexdigest():
                    raise PilotBlockedError("required test subprocess stdout/stderr provenance is invalid")
                summary = RequiredTestGateRunner._parse_pytest_summary(stdout)
                if summary is None or artifact.get("summary") != summary or receipt.get(
                        "summary") != summary or artifact.get("exit_status") != receipt.get(
                            "exit_status") or receipt.get("exit_status") != 0 or artifact.get(
                                "started_at") != receipt.get("started_at") or artifact.get(
                                    "finished_at") != receipt.get("finished_at") or receipt.get(
                                        "started_at") >= receipt.get("finished_at"):
                    raise PilotBlockedError("required test subprocess process/count evidence is invalid")
                parsed_receipts.append((receipt, summary))
            combined_receipt, combined = parsed_receipts[0]
            mandatory_artifact = json.loads(Path(
                subprocess_receipts[-1]["execution_artifact_path"]
            ).read_bytes())
            mandatory_results = RequiredTestGateRunner._parse_product_mandatory_results(
                mandatory_artifact.get("stdout", ""),
            )
            if tests.get("product_mandatory_results") != mandatory_results or tests.get(
                    "product_mandatory_test_names") != list(
                        REQUIRED_PRODUCT_MANDATORY_TESTS) or tests.get(
                            "product_mandatory_nodeids") != mandatory_results[
                                "product_mandatory_nodeids"]:
                raise PilotBlockedError("required product mandatory node ID results do not bind")
            module_outcomes = {
                module: {
                    "status": "passed",
                    "passed": summary["passed"],
                    "failed": summary["failed"],
                    "errors": summary["errors"],
                }
                for module, (_, summary) in zip(modules, parsed_receipts[1:])
            }
            module_total = sum(outcome["passed"] for outcome in module_outcomes.values())
            if any(outcome["passed"] <= 0 or outcome["failed"] != 0 or outcome["errors"] != 0
                   for outcome in module_outcomes.values()) or combined["passed"] <= 0 or combined[
                       "failed"] != 0 or combined["errors"] != 0 or combined[
                           "collected"] != combined["passed"] or combined["passed"] != module_total:
                raise PilotBlockedError("required test module/process counts do not reconcile")
            if tests.get("module_outcomes") != module_outcomes or tests.get(
                    "passed_test_count") != combined["passed"] or tests.get(
                        "collected_test_count") != combined["collected"] or tests.get(
                            "stdout_sha256") != combined_receipt["stdout_sha256"] or tests.get(
                                "stderr_sha256") != combined_receipt["stderr_sha256"] or tests.get(
                                    "exit_status") != 0 or tests.get(
                                        "started_at") != subprocess_receipts[0]["started_at"] or tests.get(
                                            "finished_at") != subprocess_receipts[-1]["finished_at"]:
                raise PilotBlockedError("required test aggregate receipt does not reconcile")

    @staticmethod
    def _production_request(packet: Dict[str, Any]) -> CodexExecRequest:
        materials = packet.get("sealed_materials")
        prompt = materials.get("prompt") if isinstance(materials, dict) else None
        path = prompt.get("path") if isinstance(prompt, dict) else None
        try:
            prompt_text = Path(path).read_text(encoding="utf-8")
        except (OSError, TypeError, UnicodeError) as exc:
            raise PilotBlockedError("production prompt bytes are unavailable") from exc
        authority = packet.get("immutable_authority")
        protected_roots = packet.get("protected_roots")
        if not isinstance(authority, dict) or not isinstance(protected_roots, list) or not all(
                isinstance(root, str) for root in protected_roots):
            raise PilotBlockedError("production packet lacks authority or protected roots")
        timeout_seconds = packet.get("timeout_seconds", 900)
        grace_seconds = packet.get("grace_seconds", 5)
        if timeout_seconds != 900 or type(grace_seconds) is not int or grace_seconds < 0:
            raise PilotBlockedError("production packet timeout contract is invalid")
        return CodexExecRequest(
            prompt=prompt_text,
            clone_path=packet["cwd"],
            artifact_dir=packet["artifact_root"],
            output_last_message_path=packet["final_path"],
            requested_model=packet["requested_model"],
            requested_effort=packet["requested_effort"],
            timeout_seconds=timeout_seconds,
            grace_seconds=grace_seconds,
            approval_hash=authority["approval_hash"],
            manifest_hash=authority["manifest_hash"],
            protected_roots=list(protected_roots),
            frozen_packet=packet,
        )

    @staticmethod
    def _validate_observed_result(packet: Dict[str, Any], result: Any) -> None:
        if isinstance(result, dict):
            if "raw_observation" not in result:
                return
            observation = result.get("raw_observation")
        else:
            observation = getattr(result, "raw_observation", None)
        if not isinstance(observation, dict):
            raise PilotBlockedError("observed identity or usage is UNKNOWN")
        configured_model = observation.get("configured_model_id", "UNKNOWN")
        configured_effort = observation.get("configured_reasoning_effort", "UNKNOWN")
        usage = observation.get("usage", "UNKNOWN")
        if configured_model == "UNKNOWN" or configured_effort == "UNKNOWN" or usage == "UNKNOWN":
            raise PilotBlockedError("observed identity or usage is UNKNOWN")
        if configured_model != packet.get("requested_model") or configured_effort != packet.get(
                "requested_effort"):
            raise PilotBlockedError("observed model/effort identity differs from the sealed packet")
        if not isinstance(usage, dict) or any(
                type(usage.get(field)) is not int or usage[field] < 0
                for field in ("input_tokens", "output_tokens")):
            raise PilotBlockedError("observed usage is UNKNOWN")

    def run_local_no_provider_preflight(self) -> Dict[str, Any]:
        """Run the concrete production Seatbelt preflight with no provider adapter."""
        return ProductionSeatbeltPreflight().run()

    def _material_bytes(self, material: Dict[str, Any]) -> bytes:
        path = material.get("path")
        if isinstance(path, str) and Path(path).is_file():
            return Path(path).read_bytes()
        if self.test_mode and isinstance(material.get("content"), str):
            return material["content"].encode("utf-8")
        raise PilotBlockedError("sealed material bytes are unavailable")

    def _validate_packet(self, packet: Any, ordinal: int, call: list[str]) -> None:
        if not isinstance(packet, dict):
            raise PilotBlockedError("frozen packet is missing")
        if packet.get("task_identity", {}).get("role") == "smoke":
            self._validate_smoke_packet(packet)
            self._validate_smoke_argv_accepted_by_installed_codex(packet)
        hashes = (
            packet.get("packet_hash"), packet.get("reverified_packet_hash"),
            packet.get("clone_tree_hash"), packet.get("reverified_clone_tree_hash"),
            packet.get("baseline_tree_hash"), packet.get("source_tree_hash"),
        )
        if any(not _is_sha256(value) for value in hashes):
            raise PilotBlockedError("frozen packet contains an invalid SHA-256")
        if packet["packet_hash"] != packet_hash(packet) or packet[
                "reverified_packet_hash"] != packet["packet_hash"]:
            raise PilotBlockedError("frozen packet hash does not bind packet bytes")
        if packet["clone_tree_hash"] != packet["reverified_clone_tree_hash"] or packet[
                "clone_tree_hash"] != packet["baseline_tree_hash"]:
            raise PilotBlockedError("clone tree changed after packet sealing")
        if packet.get("task_identity") != _task_identity(ordinal, call):
            raise PilotBlockedError("frozen packet task order or identity changed")
        if packet.get("requested_model") != call[1] or packet.get("requested_effort") != call[2]:
            raise PilotBlockedError("frozen packet model or effort changed")
        roots = packet.get("writable_roots")
        if roots != [packet.get("cwd"), packet.get("artifact_root")] or any(
                not self._is_canonical_absolute_path(root) for root in roots):
            raise PilotBlockedError("frozen packet roots are incomplete")
        cwd, artifact = roots
        if cwd == artifact or self._path_within(cwd, (artifact,)) or self._path_within(
                artifact, (cwd,)):
            raise PilotBlockedError("packet work roots are equal or nested")
        canonical_protected = ProductionSeatbeltPreflight.DEFAULT_PROTECTED_ROOTS
        if any(self._path_within(root, canonical_protected) for root in roots):
            raise PilotBlockedError("packet work root is inside a canonical protected root")
        ordered_argv = packet.get("ordered_argv")
        if not isinstance(ordered_argv, list) or not ordered_argv or any(
                not isinstance(argv, list) or not argv or any(
                    not isinstance(token, str) or not token for token in argv)
                for argv in ordered_argv):
            raise PilotBlockedError("frozen ordered argv is invalid")
        environment = packet.get("environment")
        if not isinstance(environment, dict) or any(
                not isinstance(key, str) or not key or not isinstance(value, str)
                for key, value in environment.items()):
            raise PilotBlockedError("frozen environment is invalid")
        allowed_writes = packet.get("allowed_write_targets")
        if not isinstance(allowed_writes, list) or any(
                not self._is_canonical_absolute_path(path) or not any(
                    path == root or path.startswith(root.rstrip("/") + "/") for root in roots)
                for path in allowed_writes):
            raise PilotBlockedError("frozen allowed-write policy is invalid")
        materials = packet.get("sealed_materials")
        if not isinstance(materials, dict) or set(materials) != REQUIRED_MATERIALS:
            raise PilotBlockedError("deep frozen packet materials are required")
        allowed_files = packet.get("allowed_files")
        if allowed_files is None:
            allowed_files = [material.get("path") for material in materials.values()
                             if isinstance(material, dict)]
        if not isinstance(allowed_files, list) or any(
                not self._is_canonical_absolute_path(path) for path in allowed_files):
            raise PilotBlockedError("frozen allowed-file list is invalid")
        for material in materials.values():
            if not isinstance(material, dict) or not _is_sha256(material.get("sha256")):
                raise PilotBlockedError("sealed material descriptor is invalid")
            if material.get("path") not in allowed_files:
                raise PilotBlockedError("sealed material is absent from allowed-file list")
            if hashlib.sha256(self._material_bytes(material)).hexdigest() != material["sha256"]:
                raise PilotBlockedError("sealed material bytes changed")
        for field in ("clone_tree_entries", "source_tree_entries"):
            entries = packet.get(field)
            if not isinstance(entries, list) or not entries:
                raise PilotBlockedError("deterministic tree bytes are missing")
        if _canonical_hash(packet["clone_tree_entries"]) != packet["clone_tree_hash"] or _canonical_hash(
                packet["source_tree_entries"]) != packet["source_tree_hash"]:
            raise PilotBlockedError("tree identities do not bind deterministic tree bytes")
        if self._filesystem_tree_hash(packet["cwd"]) != packet["clone_tree_hash"] or self._filesystem_tree_hash(
                packet.get("source_root")) != packet["source_tree_hash"]:
            raise PilotBlockedError("tree identities do not bind actual sealed paths")
        preparation_case_id = packet.get("preparation_case_id")
        if packet.get("schema") == "frozen_codex_packet.v1" and preparation_case_id in PREPARATION_CASES:
            if not re.fullmatch(r"[0-9a-f]{40}", packet.get("source_sha") or "") or not isinstance(
                    packet.get("preprobe_receipt"), dict):
                raise PilotBlockedError("production product packet lacks source/preprobe authority")
            expected_patch_paths = CodexPilotPreparer._allowed_patch_paths(
                preparation_case_id
            )
            if packet.get("allowed_patch_paths") != expected_patch_paths or not _is_sha256(
                    packet.get("baseline_product_tree_hash")) or ProductTreeDelta.tree_hash(
                        packet["cwd"]) != packet["baseline_product_tree_hash"]:
                raise PilotBlockedError("production product packet patch/tree authority is invalid")
            git_authority = packet.get("product_git_authority")
            if git_authority is not None:
                ProductGitAuthority.verify(
                    packet["cwd"], git_authority,
                    expected_commit=git_authority["head"],
                )
            elif not self.test_mode:
                raise PilotBlockedError("production product packet lacks clone-local Git authority")

    @staticmethod
    def _validate_smoke_packet(packet: Dict[str, Any]) -> None:
        cwd = packet.get("cwd")
        if not isinstance(cwd, str) or Path(cwd).parent != Path("/private/tmp") or not Path(
                cwd).name.startswith("codex-product-pilot-smoke-"):
            raise PilotBlockedError("smoke cwd is not a fresh canonical /private/tmp smoke root")
        if packet.get("execution_sandbox") != "read-only":
            raise PilotBlockedError("smoke sandbox must be read-only")
        if packet.get("approval_policy") != "never":
            raise PilotBlockedError("smoke approval policy must be never")
        if packet.get("expected_final_output") != "CODEX_SMOKE_OK":
            raise PilotBlockedError("smoke final output must be exactly CODEX_SMOKE_OK")
        if packet.get("forbid_tool_events") is not True:
            raise PilotBlockedError("smoke must forbid every tool event")
        if packet.get("forbid_edits") is not True or packet.get("allowed_write_targets") != []:
            raise PilotBlockedError("smoke must forbid every edit and write target")
        if packet.get("smoke_prompt_policy") != "read-only-no-tools-no-edits-exact-output":
            raise PilotBlockedError("smoke prompt policy is not sealed")
        argv_sets = packet.get("effective_codex_argv", packet.get("ordered_argv"))
        if not isinstance(argv_sets, list) or len(argv_sets) != 1 or not isinstance(
                argv_sets[0], list):
            raise PilotBlockedError("smoke argv is not exactly one sealed vector")
        argv = argv_sets[0]
        required_pairs = (("--sandbox", "read-only"), ("--ask-for-approval", "never"))
        for flag, value in required_pairs:
            if flag not in argv or argv.index(flag) + 1 >= len(argv) or argv[
                    argv.index(flag) + 1] != value:
                raise PilotBlockedError("smoke argv lacks sealed " + flag)
        if "--skip-git-repo-check" not in argv or "--full-auto" in argv:
            raise PilotBlockedError("smoke argv lacks skip-git or permits full-auto")
        materials = packet.get("sealed_materials")
        prompt = materials.get("prompt") if isinstance(materials, dict) else None
        if not isinstance(prompt, dict) or not isinstance(prompt.get("path"), str):
            raise PilotBlockedError("smoke prompt material is missing")
        try:
            prompt_bytes = Path(prompt["path"]).read_bytes()
        except OSError as exc:
            raise PilotBlockedError("smoke prompt bytes are unavailable") from exc
        expected_prompt = (
            "Return exactly CODEX_SMOKE_OK. Do not use tools, run commands, edit files, "
            "or contact external services.\n"
        ).encode("utf-8")
        if prompt_bytes != expected_prompt:
            raise PilotBlockedError("smoke prompt does not enforce no-tools/no-edits exact output")

    def _validate_smoke_argv_accepted_by_installed_codex(self, packet: Dict[str, Any]) -> None:
        """Confirm the sealed smoke argv is genuinely accepted by the installed codex
        binary -- not merely self-consistent in memory.

        `_validate_smoke_packet`'s `required_pairs` loop above only confirms
        `--sandbox`/`--ask-for-approval` are present with the right value immediately
        after them; it never checked their position relative to the `exec` token, so
        it would not have caught the `--ask-for-approval`-placed-after-`exec` ordering
        bug even in principle (the argv is compared only against itself, never against
        the real parser). This method closes that gap with an actual acceptance probe.

        Deliberately a no-op unless `self.argv_probe` was injected at construction.
        This is NOT gated on `self.test_mode`: at least one pre-existing test
        constructs this class with `test_mode=False` purely to exercise packet/
        authority validation in a production-realistic shape without ever intending
        to spawn a real `codex` process, so `test_mode` alone cannot distinguish "a
        real production run" from "a test validating production-shaped packets."
        Only `_run_production` (the actual CLI execution entry point) wires a real
        probe (`_real_codex_argv_probe`) explicitly; every other caller -- test or
        otherwise -- that does not inject `argv_probe` stays fully hermetic.
        """
        if self.argv_probe is None:
            return
        argv_sets = packet.get("effective_codex_argv", packet.get("ordered_argv"))
        argv = list(argv_sets[0])
        returncode = self.argv_probe(argv)
        if returncode != 0:
            raise PilotBlockedError(
                "smoke argv is rejected by the installed codex binary (exit %r)" % (returncode,)
            )

    @staticmethod
    def _real_codex_argv_probe(argv: list[str]) -> int:
        """Run `argv` against the real installed codex binary and return its exit
        code, with the trailing prompt/task position replaced by (or, if the argv
        has no trailing stdin marker, appended with) `--help` so the process can
        never dispatch real work. `--help` is empirically confirmed (see the
        governing spec's Context section) to short-circuit before any model or
        network activity, for every flag combination this codebase's argv builders
        produce."""
        probe_argv = (
            list(argv[:-1]) + ["--help"] if argv and argv[-1] == "-" else [*argv, "--help"]
        )
        try:
            result = subprocess.run(
                probe_argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=30, shell=False, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 1
        return result.returncode

    @staticmethod
    def _is_canonical_absolute_path(path: Any) -> bool:
        if not isinstance(path, str) or not path or not os.path.isabs(path) or os.path.normpath(
                path) != path:
            return False
        candidate = Path(path)
        current = candidate
        while True:
            if current.is_symlink():
                return False
            if current.parent == current:
                break
            current = current.parent
        return os.path.realpath(path) == path

    @staticmethod
    def _path_within(path: Any, roots: Iterable[str]) -> bool:
        return isinstance(path, str) and any(
            path == root or path.startswith(root.rstrip("/") + "/") for root in roots
        )

    @staticmethod
    def _filesystem_tree_hash(root_value: Any) -> str:
        if not isinstance(root_value, str):
            raise PilotBlockedError("sealed tree root is invalid")
        root = Path(root_value)
        if not root.exists() or root.is_symlink():
            raise PilotBlockedError("sealed tree root is unavailable")
        paths = [root]
        if root.is_dir():
            paths.extend(sorted(root.rglob("*"), key=lambda path: path.as_posix()))
        entries = []
        for path in paths:
            relative = "." if path == root else path.relative_to(root).as_posix()
            mode = path.lstat().st_mode & 0o7777
            if path.is_symlink():
                entry = {"root": root.as_posix(), "path": relative, "mode": mode,
                         "type": "symlink", "target": os.readlink(path)}
            elif path.is_dir():
                entry = {"root": root.as_posix(), "path": relative, "mode": mode,
                         "type": "directory", "size": 0}
            elif path.is_file():
                content = path.read_bytes()
                entry = {"root": root.as_posix(), "path": relative, "mode": mode,
                         "type": "file", "size": len(content),
                         "sha256": hashlib.sha256(content).hexdigest()}
            else:
                raise PilotBlockedError("sealed tree contains an unsupported file type")
            entries.append(entry)
        return _canonical_hash(entries)

    @staticmethod
    def _promotion_eligible(result: Any) -> bool:
        if isinstance(result, dict):
            return result.get("promotion_eligible") is not False
        usage = getattr(result, "usage_v1", None)
        return not isinstance(usage, dict) or usage.get("promotion_eligible") is not False


CONCRETE_PILOT_CONTROLLER_TYPE = CodexSubscriptionPilot
# Captured at import time for the same reason as _REAL_CODEX_EXEC_ADAPTER_ARGV_PROBE
# above: avoids depending solely on the `is CONCRETE_PILOT_CONTROLLER_TYPE` guard to
# keep a live `CodexSubscriptionPilot._real_codex_argv_probe` attribute lookup safe
# against a monkeypatched module-level `CodexSubscriptionPilot` name.
_REAL_CODEX_SUBSCRIPTION_PILOT_ARGV_PROBE = CodexSubscriptionPilot._real_codex_argv_probe


class _SealedFakeAdapter:
    """Deterministic non-provider boundary used only by the sealed CLI test mode."""

    def __init__(self) -> None:
        self.calls: list[Dict[str, Any]] = []

    def execute(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(packet)
        result = {
            "promotion_eligible": False,
            "packet_hash": packet["packet_hash"],
            "clone_tree_hash": packet["clone_tree_hash"],
            "pace_status": PROMOTION_BOUNDARY,
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
            plan_bytes = _canonical_bytes(plan) + b"\n"
            result.update({
                "planner_output": plan_bytes.decode("utf-8"),
                "planner_output_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            })
        return result


class RequiredTestGateRunner:
    """Execute the frozen six-module gate and retain byte-bound evidence."""

    COMMAND = ["python3", "-m", "pytest", *REQUIRED_GATE_MODULE_ORDER, "-q"]
    PRODUCT_COMMAND = [
        "python3", "-m", "pytest",
        "loop-team/runner/tests/test_codex_subscription_pilot.py",
        "loop-team/runner/tests/test_codex_exec_adapter.py",
        "-m", "product_mandatory", "-vv",
    ]

    @staticmethod
    def validate_product_mandatory_nodeids(values: Iterable[str]) -> Dict[str, Any]:
        if isinstance(values, (str, bytes)):
            raise PilotBlockedError("product mandatory test node IDs must be a sequence")
        names = list(values)
        if names != list(REQUIRED_PRODUCT_MANDATORY_TESTS) or len(names) != len(set(names)):
            missing = [name for name in REQUIRED_PRODUCT_MANDATORY_TESTS if name not in names]
            raise PilotBlockedError(
                "required product mandatory test omission or unexpected node ID: "
                + (missing[0] if missing else "unexpected entry/order")
            )
        return {
            "schema": "product_mandatory_test_gate.v1", "status": "PASS",
            "product_mandatory_test_names": names,
        }

    def __init__(self, *, popen_factory: Any = subprocess.Popen,
                 test_mode: bool = False, artifact_dir: Any = None) -> None:
        if popen_factory is not subprocess.Popen and not test_mode:
            raise TypeError("test-gate subprocess injection is permitted only in test mode")
        self.popen_factory = popen_factory
        self.test_mode = test_mode
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else Path(
            tempfile.mkdtemp(prefix="codex-product-pilot-test-gate-", dir="/private/tmp")
        )

    @staticmethod
    def _parse_pytest_summary(stdout: str) -> Optional[Dict[str, int]]:
        if not isinstance(stdout, str):
            return None
        plain = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
        outcome_names = {
            "passed": "passed", "failed": "failed",
            "error": "errors", "errors": "errors",
            "skipped": "skipped", "xfailed": "xfailed", "xpassed": "xpassed",
        }
        for line in reversed(plain.splitlines()):
            matches = re.findall(
                r"(?<![\w\"'])\b(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)\b",
                line.lower(),
            )
            if not matches or not re.search(r"\bin\s+\d+(?:\.\d+)?s\b", line.lower()):
                continue
            counts = {name: 0 for name in (
                "passed", "failed", "errors", "skipped", "xfailed", "xpassed",
            )}
            for raw_count, raw_name in matches:
                counts[outcome_names[raw_name]] += int(raw_count)
            counts["collected"] = sum(counts.values())
            return counts
        return None

    @classmethod
    def _parse_product_mandatory_results(cls, stdout: str) -> Dict[str, Any]:
        if not isinstance(stdout, str):
            raise PilotBlockedError("product mandatory pytest output is unavailable")
        plain = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
        nodeids = []
        names = []
        for line in plain.splitlines():
            match = re.match(
                r"^(\S+::(test_product_mandatory_[^\s\[]+)(?:\[[^\]]+\])?)\s+PASSED\b",
                line.strip(),
            )
            if match:
                nodeids.append(match.group(1))
                if match.group(2) not in names:
                    names.append(match.group(2))
        cls.validate_product_mandatory_nodeids(names)
        summary = cls._parse_pytest_summary(plain)
        if not nodeids or summary is None or summary["failed"] != 0 or summary[
                "errors"] != 0 or summary["skipped"] != 0 or summary[
                    "passed"] != len(nodeids):
            raise PilotBlockedError("product mandatory node ID results are incomplete")
        return {
            "schema": "product_mandatory_test_results.v1", "status": "PASS",
            "product_mandatory_test_names": names,
            "product_mandatory_nodeids": nodeids,
            "passed_case_count": len(nodeids),
        }

    def _run_command(self, command: list[str], *, index: int,
                     kind: str, module: Optional[str]) -> Dict[str, Any]:
        started_at = time.time_ns()
        process = self.popen_factory(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).resolve().parents[2]),
            shell=False,
            start_new_session=True,
            text=True,
        )
        stdout, stderr = process.communicate(timeout=900)
        finished_at = max(time.time_ns(), started_at + 1)
        stdout = stdout if isinstance(stdout, str) else ""
        stderr = stderr if isinstance(stderr, str) else ""
        exit_status = getattr(process, "returncode", None)
        summary = self._parse_pytest_summary(stdout)
        artifact = {
            "kind": kind,
            "module": module,
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_status": exit_status,
            "started_at": started_at,
            "finished_at": finished_at,
            "summary": summary,
        }
        artifact_bytes = _canonical_bytes(artifact)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifact_dir / (
            "%02d-%s.json" % (index, "combined" if module is None else "module")
        )
        temporary_path = artifact_path.with_name("." + artifact_path.name + ".tmp")
        temporary_path.write_bytes(artifact_bytes)
        os.replace(temporary_path, artifact_path)
        return {
            "kind": kind,
            "module": module,
            "command": command,
            "command_sha256": _canonical_hash(command),
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
            "exit_status": exit_status,
            "started_at": started_at,
            "finished_at": finished_at,
            "summary": summary,
            "execution_artifact_path": str(artifact_path),
            "execution_artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        }

    def run(self) -> Dict[str, Any]:
        combined_command = list(self.COMMAND)
        modules = list(REQUIRED_GATE_MODULE_ORDER)
        commands = [
            combined_command,
            *[["python3", "-m", "pytest", module, "-q"] for module in modules],
            list(self.PRODUCT_COMMAND),
        ]
        subprocess_receipts = []
        for index, command in enumerate(commands):
            subprocess_receipts.append(self._run_command(
                command,
                index=index,
                kind=("combined" if index == 0 else
                      "product_mandatory" if index == len(commands) - 1 else "module"),
                module=None if index in {0, len(commands) - 1} else modules[index - 1],
            ))
        combined_summary = subprocess_receipts[0].get("summary")
        module_outcomes: Dict[str, Dict[str, Any]] = {}
        for module, subprocess_receipt in zip(modules, subprocess_receipts[1:]):
            summary = subprocess_receipt.get("summary")
            module_outcomes[module] = {
                "status": "passed" if (
                    subprocess_receipt.get("exit_status") == 0
                    and isinstance(summary, dict)
                    and summary.get("passed", 0) > 0
                    and summary.get("failed") == 0
                    and summary.get("errors") == 0
                    and summary.get("collected") == summary.get("passed")
                ) else "failed",
                "passed": summary.get("passed", 0) if isinstance(summary, dict) else 0,
                "failed": summary.get("failed", 0) if isinstance(summary, dict) else 0,
                "errors": summary.get("errors", 0) if isinstance(summary, dict) else 0,
            }
        module_total = sum(outcome["passed"] for outcome in module_outcomes.values())
        try:
            product_mandatory = self._parse_product_mandatory_results(
                subprocess_receipts[-1].get("stdout", "")
                if "stdout" in subprocess_receipts[-1] else Path(
                    subprocess_receipts[-1]["execution_artifact_path"]
                ).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValueError, PilotBlockedError):
            product_mandatory = {"status": "FAILED"}
        if product_mandatory.get("status") == "FAILED":
            try:
                artifact = json.loads(Path(
                    subprocess_receipts[-1]["execution_artifact_path"]
                ).read_bytes())
                product_mandatory = self._parse_product_mandatory_results(
                    artifact.get("stdout", ""),
                )
            except (OSError, UnicodeError, ValueError, PilotBlockedError):
                product_mandatory = {"status": "FAILED"}
        clean = (
            len(subprocess_receipts) == 8
            and all(receipt.get("exit_status") == 0 for receipt in subprocess_receipts)
            and isinstance(combined_summary, dict)
            and combined_summary.get("passed", 0) > 0
            and combined_summary.get("failed") == 0
            and combined_summary.get("errors") == 0
            and combined_summary.get("collected") == combined_summary.get("passed")
            and combined_summary.get("passed") == module_total
            and list(module_outcomes) == modules
            and all(outcome["status"] == "passed" for outcome in module_outcomes.values())
            and product_mandatory.get("status") == "PASS"
        )
        combined_passed = combined_summary.get("passed", 0) if isinstance(
            combined_summary, dict) else 0
        combined_collected = combined_summary.get("collected", 0) if isinstance(
            combined_summary, dict) else 0
        combined_receipt = subprocess_receipts[0]
        return {
            "all_required_fake_cli_tests_passed": clean,
            "executed_test_modules": modules,
            "compatibility_assertions": sorted(REQUIRED_COMPATIBILITY_ASSERTIONS),
            "command": combined_command,
            "command_sha256": _canonical_hash(combined_command),
            "stdout_sha256": combined_receipt["stdout_sha256"],
            "stderr_sha256": combined_receipt["stderr_sha256"],
            "exit_status": combined_receipt["exit_status"],
            "started_at": subprocess_receipts[0]["started_at"],
            "finished_at": subprocess_receipts[-1]["finished_at"],
            "module_outcomes": module_outcomes,
            "outcomes": module_outcomes,
            "passed_test_count": combined_passed,
            "collected_test_count": combined_collected,
            "subprocess_receipts": subprocess_receipts,
            "product_mandatory_results": product_mandatory,
            "product_mandatory_test_names": product_mandatory.get(
                "product_mandatory_test_names", []),
            "product_mandatory_nodeids": product_mandatory.get(
                "product_mandatory_nodeids", []),
            "execution_artifact_path": combined_receipt["execution_artifact_path"],
            "execution_artifact_sha256": combined_receipt["execution_artifact_sha256"],
        }


class _CombinedCapLedger:
    """In-process ledger enforcing the sealed combined subscription caps."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_id = 0
        self._reservations: Dict[str, Dict[str, Any]] = {}
        self._reserved_calls = 0
        self._reserved_seconds = 0
        self._reserved_tokens = 0
        self._reserved_allowance_units = 0
        self._observed_tokens = 0

    def reserve(self, reservation_key: str, requested: Dict[str, Any]) -> Dict[str, Any]:
        expected = {
            "calls": 1,
            "seconds": 900,
            "observed_total_tokens": 150000,
            "subscription_allowance_units": 1,
        }
        if requested != expected or not isinstance(reservation_key, str) or not reservation_key:
            raise RuntimeError("reservation differs from the exact pilot cap unit")
        with self._lock:
            if self._reserved_calls + 1 > EXACT_CAPS["combined_calls"] or (
                    self._reserved_seconds + 900 > EXACT_CAPS["combined_timeout_seconds"]) or (
                    self._reserved_tokens + 150000 > EXACT_CAPS[
                        "aggregate_observed_tokens_max_when_telemetry_exists"]) or (
                    self._reserved_allowance_units + 1 > EXACT_CAPS[
                        "subscription_allowance_units_max"]):
                raise RuntimeError("combined pilot cap exhausted")
            self._next_id += 1
            reservation_id = "codex-pilot-reservation-%d" % self._next_id
            self._reservations[reservation_id] = {
                "state": "RESERVED", "reservation_key": reservation_key,
            }
            self._reserved_calls += 1
            self._reserved_seconds += 900
            self._reserved_tokens += 150000
            self._reserved_allowance_units += 1
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
        if observed is not None and (type(observed) is not int or observed < 0 or observed > 150000):
            raise RuntimeError("per-call observed-token cap exceeded")
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if not isinstance(reservation, dict) or reservation.get(
                    "state") != "NETWORK_IN_FLIGHT":
                raise RuntimeError("reservation cannot be reconciled")
            aggregate = self._observed_tokens + (observed or 0)
            if aggregate > EXACT_CAPS["aggregate_observed_tokens_max_when_telemetry_exists"]:
                raise RuntimeError("aggregate observed-token cap exceeded")
            self._observed_tokens = aggregate
            reservation.update({
                "state": "RECONCILED", "observation_id": observation_id,
                "actual": json.loads(json.dumps(actual)),
            })
            return {"state": "RECONCILED"}


class ProductionCapLedger:
    """Durable atomic cap ledger for production smoke and pilot attempts."""

    UNIT = {
        "calls": 1,
        "seconds": 900,
        "observed_total_tokens": 150000,
        "subscription_allowance_units": 1,
    }

    def __init__(self, *, path: str, caps: Dict[str, Any]) -> None:
        if caps != EXACT_CAPS:
            raise TypeError("production cap ledger requires the exact sealed caps")
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.name != "caps.sqlite3":
            raise TypeError("production cap ledger path must be absolute caps.sqlite3")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(candidate)
        self.caps = dict(caps)
        connection = self.connection_factory()
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    reservation_key TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    reserved_calls INTEGER NOT NULL,
                    reserved_seconds INTEGER NOT NULL,
                    reserved_tokens INTEGER NOT NULL,
                    reserved_allowance_units INTEGER NOT NULL,
                    observation_id TEXT,
                    actual_seconds INTEGER,
                    actual_tokens INTEGER,
                    created_at_ns INTEGER NOT NULL,
                    updated_at_ns INTEGER NOT NULL
                )
            """)
        finally:
            connection.close()

    def connection_factory(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def reserve(self, reservation_key: str, requested: Dict[str, Any]) -> Dict[str, Any]:
        if requested != self.UNIT or not isinstance(reservation_key, str) or not reservation_key:
            raise RuntimeError("reservation differs from the exact production cap unit")
        connection = self.connection_factory()
        try:
            connection.execute("BEGIN IMMEDIATE")
            totals = connection.execute("""
                SELECT COALESCE(SUM(reserved_calls), 0),
                       COALESCE(SUM(reserved_seconds), 0),
                       COALESCE(SUM(reserved_tokens), 0),
                       COALESCE(SUM(reserved_allowance_units), 0)
                FROM reservations
            """).fetchone()
            if (
                    totals[0] + 1 > self.caps["combined_calls"]
                    or totals[1] + 900 > self.caps["combined_timeout_seconds"]
                    or totals[2] + 150000 > self.caps[
                        "aggregate_observed_tokens_max_when_telemetry_exists"]
                    or totals[3] + 1 > self.caps["subscription_allowance_units_max"]):
                raise RuntimeError("production cap exhausted at the sealed ten-call limit")
            reservation_id = "codex-pilot-" + uuid.uuid4().hex
            now = time.time_ns()
            connection.execute("""
                INSERT INTO reservations (
                    reservation_id, reservation_key, state, reserved_calls,
                    reserved_seconds, reserved_tokens, reserved_allowance_units,
                    created_at_ns, updated_at_ns
                ) VALUES (?, ?, 'RESERVED', 1, 900, 150000, 1, ?, ?)
            """, (reservation_id, reservation_key, now, now))
            connection.commit()
            return {"reservation_id": reservation_id, "state": "RESERVED"}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def start(self, reservation_id: str) -> Dict[str, Any]:
        return self._transition(reservation_id, ("RESERVED",), "NETWORK_IN_FLIGHT")

    def mark_crashed(self, reservation_id: str) -> Dict[str, Any]:
        return self._transition(reservation_id, ("NETWORK_IN_FLIGHT",), "CRASHED")

    def _transition(self, reservation_id: str, expected: tuple[str, ...],
                    target: str) -> Dict[str, Any]:
        connection = self.connection_factory()
        try:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in expected)
            cursor = connection.execute(
                "UPDATE reservations SET state = ?, updated_at_ns = ? "
                "WHERE reservation_id = ? AND state IN (" + placeholders + ")",
                (target, time.time_ns(), reservation_id, *expected),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("production reservation state transition is invalid")
            connection.commit()
            return {"state": target}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reconcile(self, reservation_id: str, observation_id: str,
                  actual: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(observation_id, str) or not observation_id or not isinstance(actual, dict):
            raise RuntimeError("production reconciliation evidence is invalid")
        elapsed = actual.get("elapsed_seconds")
        observed = actual.get("observed_total_tokens")
        if type(elapsed) is not int or elapsed < 0 or elapsed > 900 or observed is not None and (
                type(observed) is not int or observed < 0 or observed > 150000):
            raise RuntimeError("production reconciliation exceeds a per-call cap")
        connection = self.connection_factory()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT state FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if current is None or current["state"] not in {"NETWORK_IN_FLIGHT", "CRASHED"}:
                raise RuntimeError("production reservation cannot be reconciled")
            aggregate = connection.execute(
                "SELECT COALESCE(SUM(actual_tokens), 0) FROM reservations",
            ).fetchone()[0] + (observed or 0)
            if aggregate > self.caps["aggregate_observed_tokens_max_when_telemetry_exists"]:
                raise RuntimeError("production aggregate observed-token cap exceeded")
            connection.execute("""
                UPDATE reservations
                SET state = 'RECONCILED', observation_id = ?, actual_seconds = ?,
                    actual_tokens = ?, updated_at_ns = ?
                WHERE reservation_id = ?
            """, (observation_id, elapsed, observed, time.time_ns(), reservation_id))
            connection.commit()
            return {"state": "RECONCILED"}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def totals(self) -> Dict[str, int]:
        connection = self.connection_factory()
        try:
            row = connection.execute("""
                SELECT COALESCE(SUM(reserved_calls), 0) AS calls,
                       COALESCE(SUM(actual_seconds), 0) AS seconds,
                       COALESCE(SUM(actual_tokens), 0) AS tokens,
                       COALESCE(SUM(reserved_allowance_units), 0) AS units
                FROM reservations
            """).fetchone()
            return {
                "calls": row["calls"],
                "seconds": row["seconds"],
                "observed_total_tokens": row["tokens"],
                "subscription_allowance_units": row["units"],
            }
        finally:
            connection.close()


def _load_json_object(path: Optional[Path], label: str) -> Dict[str, Any]:
    if path is None:
        raise PilotBlockedError(
            "execution requires a sealed fake config or production approval and manifest"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise PilotBlockedError(label + " JSON is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise PilotBlockedError(label + " JSON must be an object")
    return value


def _validate_production_cli_authority(
        approval: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    if approval.get("schema") != "experiment_approval.v2" or approval.get(
            "execution_mode") != "codex_subscription" or approval.get(
                "user_created") is not True:
        raise PilotBlockedError("sealed production approval is invalid")
    if manifest.get("schema") != "pace_manifest.v1":
        raise PilotBlockedError("sealed production manifest is invalid")
    if manifest.get("manifest_hash") != manifest_hash(manifest) or approval.get(
            "approval_hash") != approval_hash(approval):
        raise PilotBlockedError("approval or manifest hash does not bind exact bytes")
    if approval.get("manifest_hash") != manifest.get("manifest_hash"):
        raise PilotBlockedError("approval does not bind the exact manifest")
    confirmation = approval.get("human_confirmation")
    confirmation_spec = confirmation.get("spec_sha256") if isinstance(
        confirmation, dict
    ) else None
    if confirmation_spec != SPEC_SHA256:
        raise PilotBlockedError("exact human confirmation is bound to a stale spec")
    expected_confirmation = {
        "schema": "user_confirmation.v1",
        "confirmed": True,
        "spec_sha256": confirmation_spec,
        "approval_hash": approval.get("approval_hash"),
        "manifest_hash": manifest.get("manifest_hash"),
        "promotion_boundary": PROMOTION_BOUNDARY,
    }
    if confirmation != expected_confirmation:
        raise PilotBlockedError("exact human confirmation is required before production execution")
    if approval.get("caps") != EXACT_CAPS or manifest.get("caps") != EXACT_CAPS:
        raise PilotBlockedError("production confirmation does not bind the exact caps")
    if approval.get("call_plan") != EXACT_CALL_PLAN or manifest.get(
            "call_plan") != EXACT_CALL_PLAN:
        raise PilotBlockedError("production confirmation does not bind the exact call plan")
    if approval.get("promotion_boundary") != PROMOTION_BOUNDARY or manifest.get(
            "promotion_boundary") != PROMOTION_BOUNDARY:
        raise PilotBlockedError("production confirmation permits routing promotion")


def _run_sealed_fake(config_path: Path) -> Dict[str, Any]:
    config = _load_json_object(config_path, "sealed fake config")
    if config.get("schema") != "codex_subscription_pilot.fake_config.v1" or config.get(
            "test_mode") is not True:
        raise PilotBlockedError("sealed fake config is invalid")
    adapter = _SealedFakeAdapter()
    return CodexSubscriptionPilot(
        adapter_factory=lambda: adapter, test_mode=True,
    ).run(
        approval=config.get("approval"),
        manifest=config.get("manifest"),
        required_test_receipt=config.get("required_test_receipt"),
        frozen_packets=config.get("frozen_packets", []),
        dry_run=False,
    )


def _run_production(approval_path: Optional[Path],
                    manifest_path: Optional[Path]) -> Dict[str, Any]:
    approval = _load_json_object(approval_path, "approval")
    manifest = _load_json_object(manifest_path, "manifest")
    _validate_production_cli_authority(approval, manifest)

    preflight = ProductionSeatbeltPreflight()
    preflight_receipt = preflight.run()
    if not isinstance(preflight_receipt, dict) or preflight_receipt.get(
            "status") != "PASS" or preflight_receipt.get(
                "provider_process_starts") != 0 or preflight_receipt.get(
                    "model_resolution") != "UNKNOWN_UNTIL_SMOKE" or preflight_receipt.get(
                        "promotion_boundary") != PROMOTION_BOUNDARY or preflight_receipt.get(
                            "usd_cost") is not None:
        raise PilotBlockedError("concrete production preflight did not pass")
    if PRODUCTION_RUN_ARTIFACT_ROOT is None:
        run_artifact_root = Path(tempfile.mkdtemp(
            prefix="codex-product-pilot-run-", dir="/private/tmp",
        ))
    else:
        run_artifact_root = Path(PRODUCTION_RUN_ARTIFACT_ROOT)
        run_artifact_root.mkdir(parents=True, exist_ok=True)
    verifier_authority, key_generation_receipt = create_product_verifier_authority(
        run_artifact_root / "verifier-authority",
    )
    post_arm_verifier = ProductionPostArmController(
        controller_root=run_artifact_root / "controller-post-arm",
        authority=verifier_authority,
        key_generation_receipt=key_generation_receipt,
    )
    ledger = ProductionCapLedger(
        path=str(run_artifact_root / "caps.sqlite3"), caps=EXACT_CAPS,
    )
    minimal_slots = [
        {
            "ordinal": ordinal,
            "role": role,
            "model": model,
            "effort": effort,
            "sandbox": "read-only" if role in {"smoke", "planner"} else "workspace-write",
        }
        for ordinal, (role, model, effort) in enumerate(EXACT_CALL_PLAN)
    ]
    execution_packets = [manifest.get("smoke_packet"), *manifest.get("frozen_packets", [])]
    next_slot = 0

    def adapter_factory() -> CodexExecAdapter:
        nonlocal next_slot
        if next_slot >= len(minimal_slots):
            raise RuntimeError("production containment capability broker exhausted at ten slots")
        minimal_slot = minimal_slots[next_slot]
        slot: Dict[str, Any] = minimal_slot
        if type(preflight) is CONCRETE_PRODUCTION_PREFLIGHT_TYPE:
            packet = execution_packets[next_slot] if next_slot < len(execution_packets) else None
            if not isinstance(packet, dict):
                raise RuntimeError("production capability slot has no frozen packet")
            matching_check = next((
                check for check in preflight_receipt.get("checks", [])
                if check.get("model") == minimal_slot["model"]
                and check.get("effort") == minimal_slot["effort"]
                and check.get("sandbox") == minimal_slot["sandbox"]
            ), None)
            if not isinstance(matching_check, dict) or not _is_sha256(
                    matching_check.get("policy_sha256")):
                raise RuntimeError("production capability slot has no exact preflight policy")
            slot = {
                **minimal_slot,
                "slot_id": "%s-%s" % (minimal_slot["role"], minimal_slot["ordinal"]),
                "cwd": packet.get("cwd"),
                "writable_roots": packet.get("writable_roots"),
                "protected_roots": list(ProductionSeatbeltPreflight.DEFAULT_PROTECTED_ROOTS),
                "policy_sha256": matching_check["policy_sha256"],
            }
        try:
            capability = preflight.trusted_containment(slot=slot)
        except TypeError:
            if next_slot != 0:
                raise
            capability = preflight.trusted_containment()
        next_slot += 1
        return CodexExecAdapter(
            popen_factory=PRODUCTION_POPEN_FACTORY,
            ledger=ledger,
            containment_probe=capability,
            test_mode=False,
            argv_probe=_REAL_CODEX_EXEC_ADAPTER_ARGV_PROBE,
        )

    controller_kwargs: Dict[str, Any] = {
        "adapter_factory": adapter_factory,
        "test_mode": False,
    }
    if CodexSubscriptionPilot is CONCRETE_PILOT_CONTROLLER_TYPE:
        controller_kwargs["post_arm_verifier"] = post_arm_verifier
        controller_kwargs["argv_probe"] = _REAL_CODEX_SUBSCRIPTION_PILOT_ARGV_PROBE
    return CodexSubscriptionPilot(**controller_kwargs).run(
        approval=approval,
        manifest=manifest,
        required_test_receipt=manifest.get("required_test_receipt"),
        frozen_packets=manifest.get("frozen_packets", []),
        dry_run=False,
        report_dir=run_artifact_root / "report",
    )


def _preparation_tree_entries(root_value: Any) -> list[Dict[str, Any]]:
    """Return the same deterministic actual-tree representation used by the pilot."""
    if not isinstance(root_value, (str, os.PathLike)):
        raise PilotBlockedError("sealed tree root is invalid")
    root = Path(root_value)
    if not root.exists() or root.is_symlink():
        raise PilotBlockedError("sealed tree root is unavailable")
    paths = [root]
    if root.is_dir():
        paths.extend(sorted(root.rglob("*"), key=lambda path: path.as_posix()))
    entries: list[Dict[str, Any]] = []
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        mode = path.lstat().st_mode & 0o7777
        if path.is_symlink():
            entry = {
                "root": root.as_posix(), "path": relative, "mode": mode,
                "type": "symlink", "target": os.readlink(path),
            }
        elif path.is_dir():
            entry = {
                "root": root.as_posix(), "path": relative, "mode": mode,
                "type": "directory", "size": 0,
            }
        elif path.is_file():
            content = path.read_bytes()
            entry = {
                "root": root.as_posix(), "path": relative, "mode": mode,
                "type": "file", "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        else:
            raise PilotBlockedError("sealed tree contains an unsupported file type")
        entries.append(entry)
    return entries


class _AtomicPreparationWriter:
    """Create-only writer retaining file and parent-directory fsync evidence."""

    def __init__(self) -> None:
        self.file_fsync_paths: list[str] = []
        self.parent_directory_fsync_paths: list[str] = []

    def write_bytes(self, path_value: Any, content: bytes, *, read_only: bool = True) -> Path:
        path = Path(path_value)
        if path.exists() or path.is_symlink():
            raise PilotBlockedError("sealed artifact path already exists and cannot be reused")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(".%s.%s.tmp" % (path.name, uuid.uuid4().hex))
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            if read_only:
                path.chmod(0o444)
            self.file_fsync_paths.append(str(path))
            parent_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            self.parent_directory_fsync_paths.append(str(path.parent))
        finally:
            if temporary.exists():
                temporary.unlink()
        return path

    def write_json(self, path_value: Any, value: Any, *, read_only: bool = True) -> Path:
        return self.write_bytes(
            path_value, _canonical_bytes(value) + b"\n", read_only=read_only,
        )

    def write_jsonl(self, path_value: Any, values: Iterable[Any], *,
                    read_only: bool = True) -> Path:
        content = b"".join(_canonical_bytes(value) + b"\n" for value in values)
        return self.write_bytes(path_value, content, read_only=read_only)

    def evidence(self) -> Dict[str, list[str]]:
        return {
            "file_fsync_paths": list(self.file_fsync_paths),
            "parent_directory_fsync_paths": list(self.parent_directory_fsync_paths),
        }


def _preparation_slots(run_id: str, clone_base: Path) -> list[Dict[str, Any]]:
    rows = [(0, "smoke", "smoke", "gpt-5.6-sol", "high", "read-only")]
    ordinal = 1
    for role, model, effort, sandbox in (
        ("planner", "gpt-5.6-sol", "high", "read-only"),
        ("incumbent_coder", "gpt-5.6-terra", "high", "workspace-write"),
        ("challenger_coder", "gpt-5.6-luna", "medium", "workspace-write"),
    ):
        for case_id in PREPARATION_CASES:
            rows.append((ordinal, case_id, role, model, effort, sandbox))
            ordinal += 1
    return [{
        "ordinal": row_ordinal,
        "case_id": case_id,
        "role": role,
        "model": model,
        "effort": effort,
        "sandbox": sandbox,
        "clone_path": str(clone_base / run_id / case_id / role / "repo"),
    } for row_ordinal, case_id, role, model, effort, sandbox in rows]


def normalize_preparation_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Project a receipt onto its deterministic, path-independent preparation facts."""
    if not isinstance(receipt, dict) or receipt.get(
            "determinism_normalization") != PREPARATION_NORMALIZATION:
        raise PilotBlockedError("preparation normalization declaration is invalid")
    slots = receipt.get("slots")
    validations = receipt.get("packet_validation_receipts")
    if not isinstance(slots, list) or not isinstance(validations, list):
        raise PilotBlockedError("preparation receipt is incomplete")
    return {
        "schema": receipt.get("schema"),
        "status": receipt.get("status"),
        "provider_process_starts": receipt.get("provider_process_starts"),
        "codex_exec_starts": receipt.get("codex_exec_starts"),
        "reserved_cap_units": receipt.get("reserved_cap_units"),
        "promotion_boundary": receipt.get("promotion_boundary"),
        "promotion_eligible": receipt.get("promotion_eligible"),
        "execution_preflight": receipt.get("execution_preflight"),
        "slots": [{
            "ordinal": slot.get("ordinal"),
            "case_id": slot.get("case_id"),
            "role": slot.get("role"),
            "model": slot.get("model"),
            "effort": slot.get("effort"),
            "sandbox": slot.get("sandbox"),
        } for slot in slots if isinstance(slot, dict)],
        "packet_validation_receipts": validations,
        "determinism_normalization": PREPARATION_NORMALIZATION,
    }


class PilotConfirmationBuilder:
    """Create approval only from exact current sealed request and manifest bytes."""

    def __init__(self, *, test_mode: bool = False) -> None:
        self.test_mode = test_mode
        self.spec_sha256 = SPEC_SHA256

    def build(self, *, confirmation_request_path: Any, manifest_path: Any,
              explicit_confirmation_text: str) -> str:
        request = _load_json_object(Path(confirmation_request_path), "confirmation request")
        manifest = _load_json_object(Path(manifest_path), "manifest")
        if manifest.get("schema") != "pace_manifest.v1" or manifest.get(
                "manifest_hash") != manifest_hash(manifest):
            raise PilotBlockedError("stale or mutated manifest hash")
        run_id = request.get("run_id")
        required_text = (
            "CONFIRM CODEX PRODUCT PILOT %s %s" % (run_id, manifest["manifest_hash"])
        )
        expected_request = {
            "schema": "confirmation_request.v1",
            "confirmed": False,
            "run_id": run_id,
            "spec_sha256": self.spec_sha256,
            "manifest_hash": manifest["manifest_hash"],
            "call_plan": EXACT_CALL_PLAN,
            "caps": PREPARATION_DISPLAYED_CAPS,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "possible_codex_state_disclosure": (
                "codex-cli-0.41.0-has-no-ephemeral-and-may-write-under-~/.codex"
            ),
            "required_confirmation_text": required_text,
        }
        if request != expected_request:
            raise PilotBlockedError("confirmation request is stale, mutated, or has invalid caps")
        if explicit_confirmation_text != required_text:
            raise PilotBlockedError("exact explicit confirmation text is required")
        if manifest.get("call_plan") != EXACT_CALL_PLAN or manifest.get(
                "caps") != EXACT_CAPS or manifest.get(
                    "promotion_boundary") != PROMOTION_BOUNDARY:
            raise PilotBlockedError("manifest call plan, caps, or boundary changed")
        approval: Dict[str, Any] = {
            "schema": "experiment_approval.v2",
            "execution_mode": "codex_subscription",
            "user_created": True,
            "manifest_hash": manifest["manifest_hash"],
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
        approval_path = Path(manifest_path).parent / "experiment_approval.v2.json"
        _AtomicPreparationWriter().write_json(approval_path, approval)
        return str(approval_path)

    def build_executable(self, *, preparation_receipt_path: Any,
                         explicit_confirmation_text: str) -> Dict[str, Any]:
        receipt_path = Path(preparation_receipt_path)
        receipt = _load_json_object(receipt_path, "preparation receipt")
        object.__new__(CodexPilotPreparer).verify_seal(receipt_path)
        request = _load_json_object(
            Path(receipt["confirmation_request_path"]), "confirmation request",
        )
        template_manifest = _load_json_object(
            Path(receipt["manifest_path"]), "template manifest",
        )
        required_text = "CONFIRM CODEX PRODUCT PILOT %s %s" % (
            receipt.get("run_id"), template_manifest.get("manifest_hash"),
        )
        expected_request = {
            "schema": "confirmation_request.v1",
            "confirmed": False,
            "run_id": receipt.get("run_id"),
            "spec_sha256": self.spec_sha256,
            "manifest_hash": template_manifest.get("manifest_hash"),
            "call_plan": EXACT_CALL_PLAN,
            "caps": PREPARATION_DISPLAYED_CAPS,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "possible_codex_state_disclosure": (
                "codex-cli-0.41.0-has-no-ephemeral-and-may-write-under-~/.codex"
            ),
            "required_confirmation_text": required_text,
        }
        if request != expected_request or explicit_confirmation_text != required_text:
            raise PilotBlockedError("confirmation request/text is stale, mutated, or inexact")
        templates = [template_manifest.get("smoke_packet"), *template_manifest.get(
            "frozen_packets", [])]
        if len(templates) != 10 or any(not isinstance(packet, dict) for packet in templates):
            raise PilotBlockedError("template packet set is incomplete")
        if any("immutable_authority" in packet for packet in templates):
            raise PilotBlockedError("prepared template packet unexpectedly contains authority")

        final_packets = json.loads(json.dumps(templates))
        for packet in final_packets:
            packet["immutable_authority"] = {
                "schema": "user_confirmation.v1",
                "spec_sha256": self.spec_sha256,
                "approval_hash": "",
                "manifest_hash": "",
                "packet_hash": "",
                "caps": EXACT_CAPS,
                "requested_model": packet["requested_model"],
                "requested_effort": packet["requested_effort"],
                "baseline_hashes": {
                    "source": packet["source_tree_hash"],
                    "clone_tree": packet["clone_tree_hash"],
                },
                "promotion_boundary": PROMOTION_BOUNDARY,
                "confirmed": True,
            }
        final_manifest: Dict[str, Any] = {
            **{
                key: value for key, value in template_manifest.items()
                if key not in {"smoke_packet", "frozen_packets", "manifest_hash"}
            },
            "schema": "pace_manifest.v1",
            "template_manifest_hash": template_manifest["manifest_hash"],
            "smoke_packet": final_packets[0],
            "frozen_packets": final_packets[1:],
            "manifest_hash": "",
        }
        final_manifest_hash = manifest_hash(final_manifest)
        approval: Dict[str, Any] = {
            "schema": "experiment_approval.v2",
            "execution_mode": "codex_subscription",
            "user_created": True,
            "manifest_hash": final_manifest_hash,
            "template_manifest_hash": template_manifest["manifest_hash"],
            "caps": EXACT_CAPS,
            "call_plan": EXACT_CALL_PLAN,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "human_confirmation": {
                "schema": "user_confirmation.v1",
                "confirmed": True,
                "spec_sha256": self.spec_sha256,
                "approval_hash": "",
                "manifest_hash": final_manifest_hash,
                "promotion_boundary": PROMOTION_BOUNDARY,
            },
            "approval_hash": "",
        }
        final_approval_hash = approval_hash(approval)
        approval["approval_hash"] = final_approval_hash
        approval["human_confirmation"]["approval_hash"] = final_approval_hash
        for packet in final_packets:
            authority = packet["immutable_authority"]
            authority["approval_hash"] = final_approval_hash
            authority["manifest_hash"] = final_manifest_hash
            packet["packet_hash"] = packet_hash(packet)
            packet["reverified_packet_hash"] = packet["packet_hash"]
            authority["packet_hash"] = packet["packet_hash"]
        final_manifest["smoke_packet"] = final_packets[0]
        final_manifest["frozen_packets"] = final_packets[1:]
        final_manifest["manifest_hash"] = final_manifest_hash
        if manifest_hash(final_manifest) != final_manifest_hash:
            raise PilotBlockedError("final manifest authority hash ordering failed")

        executable_root = Path(receipt["manifest_path"]).parent / "executable"
        if executable_root.exists() or executable_root.is_symlink():
            raise PilotBlockedError("executable authority bundle already exists")
        executable_root.mkdir(parents=False, exist_ok=False)
        writer = _AtomicPreparationWriter()
        packet_paths = []
        for ordinal, packet in enumerate(final_packets):
            packet_path = writer.write_json(
                executable_root / "packets" / ("%02d.json" % ordinal), packet,
            )
            packet_paths.append(str(packet_path))
        manifest_path = writer.write_json(
            executable_root / "pace_manifest.v1.json", final_manifest,
        )
        approval_path = writer.write_json(
            executable_root / "experiment_approval.v2.json", approval,
        )
        result = {
            "schema": "executable_pilot_bundle.v1",
            "template_manifest_path": receipt["manifest_path"],
            "confirmation_request_path": receipt["confirmation_request_path"],
            "approval_path": str(approval_path),
            "manifest_path": str(manifest_path),
            "packet_paths": packet_paths,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "provider_process_starts": 0,
        }
        validate_executable_pilot_bundle(result, test_mode=self.test_mode)
        return result


def validate_executable_pilot_bundle(
        bundle: Any, *, test_mode: bool = False) -> Dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("schema") != "executable_pilot_bundle.v1":
        raise PilotBlockedError("executable authority bundle receipt is invalid")
    try:
        approval = _load_json_object(Path(bundle["approval_path"]), "executable approval")
        manifest = _load_json_object(Path(bundle["manifest_path"]), "executable manifest")
        packet_paths = bundle["packet_paths"]
        packets = [
            _load_json_object(Path(path), "executable packet") for path in packet_paths
        ]
    except (KeyError, TypeError) as exc:
        raise PilotBlockedError("executable packet/authority paths are invalid") from exc
    if len(packets) != 10 or manifest.get("smoke_packet") != packets[0] or manifest.get(
            "frozen_packets") != packets[1:]:
        raise PilotBlockedError("executable packet set does not match final manifest")
    if manifest.get("manifest_hash") != manifest_hash(manifest):
        raise PilotBlockedError("executable manifest hash is invalid")
    if approval.get("approval_hash") != approval_hash(approval):
        raise PilotBlockedError("executable approval hash is invalid")
    _validate_production_cli_authority(approval, manifest)
    pilot = CodexSubscriptionPilot(
        adapter_factory=lambda: None, test_mode=test_mode,
    )
    for ordinal, (packet, call) in enumerate(zip(packets, EXACT_CALL_PLAN)):
        authority = packet.get("immutable_authority")
        if not isinstance(authority, dict) or authority.get(
                "approval_hash") != approval["approval_hash"] or authority.get(
                    "manifest_hash") != manifest["manifest_hash"] or authority.get(
                        "packet_hash") != packet.get("packet_hash"):
            raise PilotBlockedError("executable packet immutable authority is invalid")
        if packet.get("packet_hash") != packet_hash(packet) or packet.get(
                "reverified_packet_hash") != packet.get("packet_hash"):
            raise PilotBlockedError("executable packet hash is invalid or mutated")
        pilot._validate_packet(packet, ordinal, call)
        pilot._production_request(packet)
    return {
        "status": "PASS", "packet_count": 10,
        "manifest_hash": manifest["manifest_hash"],
        "approval_hash": approval["approval_hash"],
        "promotion_boundary": PROMOTION_BOUNDARY,
    }


class ProductionPreparationGit:
    """Read-only source verification and detached local no-hardlink cloning."""

    @staticmethod
    def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        process = subprocess.run(
            ["git", *args], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, text=True, shell=False, check=False,
        )
        if check and process.returncode != 0:
            raise PilotBlockedError(
                "Git source/commit verification failed: " + process.stderr.strip()
            )
        return process

    def verify_source(self, *, source: Any, expected_sha: str) -> Dict[str, Any]:
        source_path = Path(source)
        if not source_path.is_dir() or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
            raise PilotBlockedError("source or approved commit identity is invalid")
        status = self._git("-C", str(source_path), "status", "--porcelain").stdout
        if status:
            raise PilotBlockedError("source repository must be clean before preparation")
        head_sha = self._git("-C", str(source_path), "rev-parse", "HEAD").stdout.strip()
        commit_check = self._git(
            "-C", str(source_path), "cat-file", "-e", expected_sha + "^{commit}",
            check=False,
        )
        if commit_check.returncode != 0:
            raise PilotBlockedError("approved commit does not exist in the source repository")
        reachable_check = self._git(
            "-C", str(source_path), "merge-base", "--is-ancestor", expected_sha, head_sha,
            check=False,
        )
        if reachable_check.returncode != 0:
            raise PilotBlockedError("approved commit is not reachable from the clean source HEAD")
        head_tree = self._git(
            "-C", str(source_path), "rev-parse", "HEAD^{tree}",
        ).stdout.strip()
        approved_tree = self._git(
            "-C", str(source_path), "rev-parse", expected_sha + "^{tree}",
        ).stdout.strip()
        approved_listing = self._git(
            "-C", str(source_path), "ls-tree", "-r", expected_sha,
        ).stdout.encode("utf-8")
        return {
            "source": str(source_path),
            "expected_sha": expected_sha,
            "head_sha": head_sha,
            "fixture_head_sha": head_sha,
            "clean": True,
            "status_porcelain_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
            "head_tree_sha": head_tree,
            "approved_tree_sha": approved_tree,
            "approved_tree_listing_sha256": hashlib.sha256(approved_listing).hexdigest(),
            "approved_commit_exists": True,
            "approved_commit_reachable": True,
        }

    def _resolve_git_object_dir(self, repository: Any = None) -> Path:
        # Preserve the class-level diagnostic seam for malformed repositories.
        if repository is None:
            repository = self
            git_runner = ProductionPreparationGit()._git
        else:
            git_runner = self._git
        repository_path = Path(repository)
        process = git_runner(
            "-C", str(repository_path), "rev-parse", "--path-format=absolute",
            "--git-path", "objects", check=False,
        )
        object_dir_text = process.stdout.strip() if process.returncode == 0 else ""
        object_dir = Path(object_dir_text) if object_dir_text else None
        if object_dir is None or not object_dir.is_absolute():
            raise PilotBlockedError("git object store unavailable")
        try:
            mode = object_dir.lstat().st_mode
            with os.scandir(object_dir) as iterator:
                next(iterator, None)
        except OSError as exc:
            raise PilotBlockedError("git object store unavailable") from exc
        if not stat.S_ISDIR(mode) or not os.access(object_dir, os.R_OK | os.X_OK):
            raise PilotBlockedError("git object store unavailable")
        return object_dir

    @staticmethod
    def _object_alternates(object_dir: Path) -> list[str]:
        alternates_path = object_dir / "info" / "alternates"
        try:
            alternate_stat = alternates_path.lstat()
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise PilotBlockedError("git object store alternates evidence unavailable") from exc
        if not stat.S_ISREG(alternate_stat.st_mode):
            raise PilotBlockedError("git object store alternates evidence unavailable")
        try:
            return [
                line for line in alternates_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
        except (OSError, UnicodeError) as exc:
            raise PilotBlockedError("git object store alternates evidence unavailable") from exc

    @staticmethod
    def _same_filesystem_identity(source_stat: Any, clone_stat: Any) -> bool:
        return (
            source_stat.st_dev == clone_stat.st_dev
            and source_stat.st_ino == clone_stat.st_ino
        )

    @staticmethod
    def _object_entries(object_dir: Path) -> Dict[str, tuple[Path, os.stat_result]]:
        entries: Dict[str, tuple[Path, os.stat_result]] = {}

        def visit(directory: Path) -> None:
            try:
                with os.scandir(directory) as iterator:
                    children = sorted(iterator, key=lambda child: child.name)
            except OSError as exc:
                raise PilotBlockedError("git object store unavailable") from exc
            for child in children:
                child_path = Path(child.path)
                try:
                    child_stat = child_path.lstat()
                except OSError as exc:
                    raise PilotBlockedError("git object store unavailable") from exc
                relative = child_path.relative_to(object_dir).as_posix()
                if stat.S_ISDIR(child_stat.st_mode):
                    visit(child_path)
                elif stat.S_ISREG(child_stat.st_mode) or stat.S_ISLNK(child_stat.st_mode):
                    entries[relative] = (child_path, child_stat)

        visit(object_dir)
        return entries

    @staticmethod
    def _entry_identity(path: Path, stat_result: os.stat_result) -> Dict[str, Any]:
        if stat.S_ISREG(stat_result.st_mode):
            entry_type = "regular_file"
        elif stat.S_ISLNK(stat_result.st_mode):
            entry_type = "symlink"
        else:
            entry_type = "unsupported"
        identity: Dict[str, Any] = {
            "mode": stat_result.st_mode,
            "st_dev": stat_result.st_dev,
            "st_ino": stat_result.st_ino,
            "nlink": stat_result.st_nlink,
            "entry_type": entry_type,
        }
        if entry_type == "symlink":
            try:
                target_bytes = os.readlink(path).encode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise PilotBlockedError("git object symlink target unavailable") from exc
            identity.update({
                "link_target_bytes_hex": target_bytes.hex(),
                "link_target_sha256": hashlib.sha256(target_bytes).hexdigest(),
            })
        return identity

    @classmethod
    def _object_identity_evidence(
            cls, source_object_dir: Path,
            clone_object_dir: Path) -> list[Dict[str, Any]]:
        source_entries = cls._object_entries(source_object_dir)
        clone_entries = cls._object_entries(clone_object_dir)
        evidence = []
        for relative_path in sorted(set(source_entries) & set(clone_entries)):
            source_path, source_stat = source_entries[relative_path]
            clone_path, clone_stat = clone_entries[relative_path]
            source_identity = cls._entry_identity(source_path, source_stat)
            clone_identity = cls._entry_identity(clone_path, clone_stat)
            both_regular = (
                stat.S_ISREG(source_stat.st_mode) and stat.S_ISREG(clone_stat.st_mode)
            )
            shared_identity = both_regular and cls._same_filesystem_identity(
                source_stat, clone_stat,
            )
            evidence.append({
                "source_object_dir": str(source_object_dir),
                "clone_object_dir": str(clone_object_dir),
                "relative_path": relative_path,
                "source": source_identity,
                "clone": clone_identity,
                "shared_identity": shared_identity,
            })
            if shared_identity:
                raise PilotBlockedError(
                    "Git object stores share a regular-file hardlink/shared filesystem identity"
                )
        return evidence

    def clone_detached(self, *, source: Any, expected_sha: str,
                       destination: Any) -> Dict[str, Any]:
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path.exists() or destination_path.is_symlink():
            raise PilotBlockedError("clone destination already exists")
        source_before = self.verify_source(source=source_path, expected_sha=expected_sha)
        clone_argv = [
            "git", "clone", "--no-hardlinks", str(source_path), str(destination_path),
        ]
        environment = dict(os.environ)
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        clone = subprocess.run(
            clone_argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=environment,
            text=True, shell=False, check=False,
        )
        if clone.returncode != 0:
            raise PilotBlockedError("local no-hardlink clone failed: " + clone.stderr.strip())
        checkout_argv = [
            "git", "-C", str(destination_path), "checkout", "--detach", expected_sha,
        ]
        checkout = subprocess.run(
            checkout_argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=environment,
            text=True, shell=False, check=False,
        )
        if checkout.returncode != 0:
            raise PilotBlockedError("detached approved-commit checkout failed: " + checkout.stderr.strip())
        clone_head = self._git(
            "-C", str(destination_path), "rev-parse", "HEAD",
        ).stdout.strip()
        symbolic_ref = self._git(
            "-C", str(destination_path), "symbolic-ref", "-q", "HEAD", check=False,
        )
        if clone_head != expected_sha or symbolic_ref.returncode != 1:
            raise PilotBlockedError("clone is not detached at the exact approved commit")
        source_object_dir = self._resolve_git_object_dir(source_path)
        clone_object_dir = self._resolve_git_object_dir(destination_path)
        source_object_alternates = self._object_alternates(source_object_dir)
        clone_object_alternates = self._object_alternates(clone_object_dir)
        if source_object_alternates or clone_object_alternates:
            raise PilotBlockedError(
                "Git object-store alternates are incompatible with no-hardlink provenance"
            )
        inode_provenance = self._object_identity_evidence(
            source_object_dir, clone_object_dir,
        )
        if not inode_provenance:
            raise PilotBlockedError(
                "no common Git object entries available for no-hardlinks evidence"
            )
        source_after = self.verify_source(source=source_path, expected_sha=expected_sha)
        if source_after != source_before:
            raise PilotBlockedError("source repository changed while preparing detached clone")
        return {
            "source": str(source_path),
            "destination": str(destination_path),
            "clone_argv": clone_argv,
            "checkout_argv": checkout_argv,
            "expected_head_sha": expected_sha,
            "fixture_head_sha": clone_head,
            "approved_commit_exists": True,
            "approved_commit_reachable": True,
            "detached": True,
            "no_hardlinks": True,
            "source_object_dir": str(source_object_dir),
            "clone_object_dir": str(clone_object_dir),
            "source_object_alternates": source_object_alternates,
            "clone_object_alternates": clone_object_alternates,
            "object_identity_evidence_status": "PASS",
            "inode_provenance": inode_provenance,
            "source_before": source_before,
            "source_after": source_after,
        }


class ProductionProductPreprobeRunner:
    """Run exact local product baselines under a deny-network sandbox."""

    _ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
    _P1_ROUTE_IDS = {
        "dashboard": "dashboard_mock_backed",
        "profile": "profile_mock_backed",
        "tax-package": "tax_package_mock_backed",
        "connections": "connections_mock_backed",
        "feed": "feed_mock_backed",
    }
    _P1_WRAPPER_IDS = {
        "askTaxahead": "ask_taxahead_unused",
        "listSources": "list_sources_unused",
        "startConnection": "start_connection_unused",
        "completeOAuthConnection": "complete_oauth_connection_unused",
        "syncSource": "sync_source_unused",
        "disconnectSource": "disconnect_source_unused",
    }

    def __init__(self, *, run_factory: Any = subprocess.run) -> None:
        self.run_factory = run_factory

    @staticmethod
    def _policy(artifact_dir: Path) -> str:
        escaped = str(artifact_dir).replace('"', '\\"')
        return "\n".join((
            "(version 1)",
            "(deny default)",
            "(allow process*)",
            "(allow file-read*)",
            '(allow file-write* (subpath "%s"))' % escaped,
            "(deny network*)",
            "",
        ))

    def _run(self, *, argv: list[str], clone_path: Path, artifact_dir: Path,
             environment: Dict[str, str],
             expected_exit_codes: Iterable[int] = (0,)
             ) -> tuple[subprocess.CompletedProcess[str], Dict[str, Any]]:
        policy = self._policy(artifact_dir)
        effective_argv = ["/usr/bin/sandbox-exec", "-p", policy, *argv]
        env = {"LANG": "C", "PATH": "/usr/bin:/bin:/opt/homebrew/bin", **environment}
        process = self.run_factory(
            effective_argv, cwd=str(clone_path), env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, shell=False, timeout=900, check=False,
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        writer = _AtomicPreparationWriter()
        stdout_path = writer.write_bytes(
            artifact_dir / "stdout.txt", process.stdout.encode("utf-8"), read_only=True,
        )
        stderr_path = writer.write_bytes(
            artifact_dir / "stderr.txt", process.stderr.encode("utf-8"), read_only=True,
        )
        command_receipt = {
            "schema": "product_preprobe_command_receipt.v1",
            "argv": argv,
            "effective_argv_sha256": _canonical_hash(effective_argv),
            "environment_keys": sorted(env),
            "cwd": str(clone_path),
            "exit_code": process.returncode,
            "stdout_path": str(stdout_path),
            "stdout_sha256": hashlib.sha256(process.stdout.encode("utf-8")).hexdigest(),
            "stderr_path": str(stderr_path),
            "stderr_sha256": hashlib.sha256(process.stderr.encode("utf-8")).hexdigest(),
            "policy_sha256": hashlib.sha256(policy.encode("utf-8")).hexdigest(),
        }
        command_receipt_path = writer.write_json(
            artifact_dir / "command_receipt.v1.json", command_receipt,
        )
        containment = {
            "status": "PASS",
            "mechanism": "macos-sandbox-exec-deny-network",
            "version": "1",
            "policy_sha256": hashlib.sha256(policy.encode("utf-8")).hexdigest(),
            "effective_argv_sha256": _canonical_hash(effective_argv),
            "network_attempts": [],
            "filesystem_violations": [],
            "command_receipt_path": str(command_receipt_path),
            "exit_code": process.returncode,
        }
        allowed_exits = tuple(expected_exit_codes)
        if process.returncode not in allowed_exits:
            raise PilotBlockedError(
                "preprobe command exit %s is outside expected exits %s; durable receipt: %s"
                % (process.returncode, allowed_exits, command_receipt_path)
            )
        return process, containment

    @staticmethod
    def _strict_json_object(stdout: str, label: str) -> Dict[str, Any]:
        lines = [line for line in stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            raise PilotBlockedError(label + " output must be exactly one JSON object")
        try:
            value = json.loads(lines[0])
        except ValueError as exc:
            raise PilotBlockedError(label + " output is not JSON") from exc
        if not isinstance(value, dict):
            raise PilotBlockedError(label + " output is not an object")
        return value

    @classmethod
    def _parse_p1_summary(cls, stdout: str, exit_code: int, *,
                          require_target: bool) -> Dict[str, Any]:
        if exit_code != 1 or type(exit_code) is not int:
            raise PilotBlockedError("P1 strict summary requires exact exit 1")
        plain = cls._ANSI_RE.sub("", stdout)
        if "TaxAhead reality check" not in plain or "(read-only; STRICT mode)" not in plain:
            raise PilotBlockedError("P1 strict mode header is missing")
        if not re.search(r"^Summary\s*$", plain, re.MULTILINE) or not re.search(
                r"^FAIL \(strict\).*Exit 1\.\s*$", plain, re.MULTILINE):
            raise PilotBlockedError("P1 strict summary or terminal finding is missing")
        route_matches = re.findall(
            r"^\s*mock-backed routes \(live\):\s*(.+?)\s*$", plain, re.MULTILINE,
        )
        wrapper_matches = re.findall(
            r"^\s*unused wrappers \(live\):\s*(.+?)\s*$", plain, re.MULTILINE,
        )
        if len(route_matches) != 1 or len(wrapper_matches) != 1:
            raise PilotBlockedError("P1 strict summary fields are partial or duplicated")

        def parse_names(raw: str, allowlist: Dict[str, str], label: str) -> list[str]:
            names = [] if raw == "(none)" else [name.strip() for name in raw.split(",")]
            if any(not name for name in names) or len(names) != len(set(names)):
                raise PilotBlockedError("P1 %s findings are empty or duplicated" % label)
            unknown = [name for name in names if name not in allowlist]
            if unknown:
                raise PilotBlockedError("P1 %s finding is unknown: %s" % (label, unknown[0]))
            return [allowlist[name] for name in names]

        finding_ids = [
            *parse_names(route_matches[0], cls._P1_ROUTE_IDS, "route"),
            *parse_names(wrapper_matches[0], cls._P1_WRAPPER_IDS, "wrapper"),
        ]
        if not finding_ids or len(finding_ids) != len(set(finding_ids)):
            raise PilotBlockedError("P1 strict finding IDs are missing or duplicated")
        if require_target and finding_ids.count("tax_package_mock_backed") != 1:
            raise PilotBlockedError("P1 targeted tax_package_mock_backed finding is not exact")
        return {"exit_code": exit_code, "finding_ids": finding_ids}

    @classmethod
    def parse_p1_strict_output(cls, stdout: str, exit_code: int) -> Dict[str, Any]:
        return cls._parse_p1_summary(stdout, exit_code, require_target=True)

    @staticmethod
    def p3_baseline_argv() -> list[str]:
        return ["node", "-e", P3_BASELINE_SCRIPT]

    @classmethod
    def parse_p3_baseline(cls, stdout: str, exit_code: int) -> Dict[str, Any]:
        if exit_code != 0 or type(exit_code) is not int:
            raise PilotBlockedError("P3 baseline inventory requires exact exit 0")
        baseline = cls._strict_json_object(stdout, "P3 baseline inventory")
        expected_keys = {
            "schema", "project_id", "alias", "doctor_script_registered",
            "doctor_implementation_present", "doctor_test_present",
            "source_verifier_present",
        }
        if set(baseline) != expected_keys or baseline.get(
                "schema") != "p3-prerequisite-doctor-baseline.v1" or baseline.get(
                    "project_id") != "padsplit-cockpit" or baseline.get(
                        "alias") != "PMS Cockpit":
            raise PilotBlockedError("P3 baseline inventory schema or identity is invalid")
        for key in (
                "doctor_script_registered", "doctor_implementation_present",
                "doctor_test_present", "source_verifier_present"):
            if type(baseline.get(key)) is not bool:
                raise PilotBlockedError("P3 baseline inventory field is not boolean: " + key)
        if any(baseline[key] is not False for key in (
                "doctor_script_registered", "doctor_implementation_present",
                "doctor_test_present")):
            raise PilotBlockedError("P3 baseline must prove doctor script, code, and test absent")
        if baseline["source_verifier_present"] is not True:
            raise PilotBlockedError("P3 baseline must prove the existing source verifier is present")
        return {"exit_code": 0, "baseline": baseline}

    @classmethod
    def parse_p3_doctor_output(cls, stdout: str, exit_code: int) -> Dict[str, Any]:
        payload = cls._strict_json_object(stdout, "P3 prerequisite doctor")
        required = {
            "schema", "status", "ready", "project_id", "alias", *P3_PREDICATES,
        }
        if not required.issubset(payload) or payload.get(
                "schema") != "pms.prerequisite-doctor.v1" or payload.get(
                    "project_id") != "padsplit-cockpit" or payload.get(
                        "alias") != "PMS Cockpit":
            raise PilotBlockedError("P3 doctor schema or identity is invalid")
        if type(payload.get("status")) is not str or type(payload.get("ready")) is not bool:
            raise PilotBlockedError("P3 doctor status/ready fields are not typed")
        if any(type(payload.get(key)) is not bool for key in P3_PREDICATES):
            raise PilotBlockedError("P3 doctor prerequisite predicate is not boolean")
        status = payload["status"]
        predicates = [payload[key] for key in P3_PREDICATES]
        if status == "READY":
            valid = exit_code == 0 and payload["ready"] is True and all(predicates)
        elif status == "NOT_READY":
            valid = exit_code == 3 and payload["ready"] is False and not all(predicates)
        elif status == "INVALID_ARGUMENTS":
            error = payload.get("error")
            valid = (
                exit_code == 2 and payload["ready"] is False
                and isinstance(error, dict)
                and error.get("code") == "INVALID_ARGUMENTS"
                and isinstance(error.get("message"), str) and bool(error["message"])
            )
        else:
            valid = False
        if not valid:
            raise PilotBlockedError("P3 doctor status, ready state, predicates, and exit disagree")
        return {"exit_code": exit_code, **payload}

    @staticmethod
    def _json_object(stdout: str) -> Dict[str, Any]:
        for candidate in reversed(stdout.splitlines()):
            try:
                value = json.loads(candidate)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
        try:
            value = json.loads(stdout)
        except ValueError as exc:
            raise PilotBlockedError("preprobe baseline output is not JSON") from exc
        if not isinstance(value, dict):
            raise PilotBlockedError("preprobe baseline output is not an object")
        return value

    @staticmethod
    def _finding_ids(value: Any) -> Optional[list[str]]:
        if isinstance(value, dict):
            direct = value.get("finding_ids")
            if isinstance(direct, list) and all(isinstance(item, str) for item in direct):
                return direct
            for nested in value.values():
                found = ProductionProductPreprobeRunner._finding_ids(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = ProductionProductPreprobeRunner._finding_ids(nested)
                if found is not None:
                    return found
        return None

    def run(self, *, case_id: str, clone_path: Any, artifact_dir: Any) -> Dict[str, Any]:
        clone = Path(clone_path)
        artifact = Path(artifact_dir)
        if case_id == PREPARATION_CASES[0]:
            argv = ["npm", "run", "smoke"]
            environment = {"REQUIRE_REAL_BACKEND": "1"}
            process, containment = self._run(
                argv=argv, clone_path=clone, artifact_dir=artifact,
                environment=environment, expected_exit_codes=(1,),
            )
            parsed = self.parse_p1_strict_output(process.stdout, process.returncode)
            return {
                "status": "PASS", "containment_receipt": containment,
                "argv": argv, "environment": environment,
                "baseline_finding_ids": parsed["finding_ids"],
                "baseline_exit_code": parsed["exit_code"],
                "stdout_sha256": hashlib.sha256(process.stdout.encode("utf-8")).hexdigest(),
            }
        if case_id == PREPARATION_CASES[1]:
            argv = [
                "rg", "-n", "-F", "const handleSend =",
                "src/routes/app.feed.tsx",
            ]
            process, containment = self._run(
                argv=argv, clone_path=clone, artifact_dir=artifact, environment={},
            )
            matches = []
            for line in process.stdout.splitlines():
                match = re.fullmatch(r"([^:]+):(\d+):(.*)", line)
                if match and "const handleSend =" in match.group(3):
                    matches.append(match)
            if len(matches) != 1:
                raise PilotBlockedError("P2 preprobe handleSend call site is ambiguous")
            match = matches[0]
            relative_path = match.group(1)
            path = clone / relative_path
            content = path.read_bytes()
            line_number = int(match.group(2))
            lines = content.decode("utf-8").splitlines()
            if line_number < 1 or line_number > len(lines):
                raise PilotBlockedError("P2 handleSend start line is invalid")
            end_line = next((
                index for index in range(line_number + 1, len(lines) + 1)
                if lines[index - 1] == "  };"
            ), None)
            if end_line is None:
                raise PilotBlockedError("P2 handleSend lexical span is incomplete")
            span_text = "\n".join(lines[line_number - 1:end_line])
            return {
                "status": "PASS", "containment_receipt": containment,
                "discovery_argv": argv,
                "discovery_stdout_sha256": hashlib.sha256(
                    process.stdout.encode("utf-8")
                ).hexdigest(),
                "active_call_site": {
                    "relative_path": relative_path,
                    "symbol": "handleSend",
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                    "span": {
                        "start_line": line_number, "end_line": end_line,
                        "text": span_text,
                        "text_sha256": hashlib.sha256(
                            span_text.encode("utf-8")
                        ).hexdigest(),
                    },
                },
                "sealed_source_files": {
                    relative_path: hashlib.sha256(content).hexdigest(),
                },
            }
        if case_id != PREPARATION_CASES[2]:
            raise PilotBlockedError("unknown product preprobe case")
        argv = self.p3_baseline_argv()
        process, containment = self._run(
            argv=argv, clone_path=clone, artifact_dir=artifact, environment={},
        )
        parsed = self.parse_p3_baseline(process.stdout, process.returncode)
        return {
            "status": "PASS", "containment_receipt": containment,
            "argv": argv,
            "baseline_argv": argv,
            "target_argv": list(P3_TARGET_ARGV),
            "baseline": parsed["baseline"],
            "baseline_exit_code": parsed["exit_code"],
            "stdout_sha256": hashlib.sha256(process.stdout.encode("utf-8")).hexdigest(),
        }


class ProductP3OracleMatrix:
    """Execute the prerequisite doctor under three exact, contradictory inputs."""

    _ENV_KEYS = (
        "P3_GENERATED_PRISMA_CLIENT", "DATABASE_URL",
        "P3_APP_ENDPOINT", "P3_ORGANIZATION_TOKEN",
    )

    def __init__(self, *, run_factory: Any = subprocess.run) -> None:
        self.run_factory = run_factory

    def _run_one(self, *, name: str, argv: list[str], clone: Path,
                 artifact: Path, environment: Dict[str, str]) -> Dict[str, Any]:
        env = {"LANG": "C", "PATH": "/usr/bin:/bin:/opt/homebrew/bin", **environment}
        process = self.run_factory(
            list(argv), cwd=str(clone), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            shell=False, timeout=900, check=False,
        )
        stdout = process.stdout if isinstance(process.stdout, str) else ""
        stderr = process.stderr if isinstance(process.stderr, str) else ""
        run_root = artifact / name
        run_root.mkdir(parents=True, exist_ok=False)
        writer = _AtomicPreparationWriter()
        stdout_path = writer.write_bytes(
            run_root / "stdout.txt", stdout.encode("utf-8"), read_only=True,
        )
        stderr_path = writer.write_bytes(
            run_root / "stderr.txt", stderr.encode("utf-8"), read_only=True,
        )
        parsed = ProductionProductPreprobeRunner.parse_p3_doctor_output(
            stdout, process.returncode,
        )
        return {
            "exit_code": process.returncode,
            "status": parsed["status"],
            "ready": parsed["ready"],
            "predicates": {key: parsed[key] for key in P3_PREDICATES},
            "argv": list(argv),
            "environment_keys": sorted(env),
            "stdout_path": str(stdout_path),
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_path": str(stderr_path),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        }

    def run(self, *, clone_path: Any, artifact_dir: Any, argv: list[str],
            invalid_argument: str,
            injected_environment: Dict[str, str]) -> Dict[str, Any]:
        clone = Path(clone_path)
        artifact = Path(artifact_dir)
        if not clone.is_dir() or clone.is_symlink():
            raise PilotBlockedError("P3 oracle matrix clone is unavailable")
        if artifact.exists() or artifact.is_symlink():
            raise PilotBlockedError("P3 oracle matrix artifact root already exists")
        if list(argv) != P3_TARGET_ARGV or not isinstance(
                invalid_argument, str) or not invalid_argument.startswith("--"):
            raise PilotBlockedError("P3 oracle matrix argv is not exact")
        if set(injected_environment) != set(self._ENV_KEYS) or any(
                not isinstance(injected_environment[key], str)
                or not injected_environment[key]
                for key in self._ENV_KEYS):
            raise PilotBlockedError("P3 injected READY environment is incomplete")
        artifact.mkdir(parents=True, exist_ok=False)
        runs = {
            "empty_environment": self._run_one(
                name="empty_environment", argv=list(argv), clone=clone,
                artifact=artifact, environment={},
            ),
            "invalid_arguments": self._run_one(
                name="invalid_arguments", argv=[*argv, invalid_argument], clone=clone,
                artifact=artifact, environment={},
            ),
            "injected_ready": self._run_one(
                name="injected_ready", argv=list(argv), clone=clone,
                artifact=artifact, environment=dict(injected_environment),
            ),
        }
        empty = runs["empty_environment"]
        invalid = runs["invalid_arguments"]
        ready = runs["injected_ready"]
        if empty["exit_code"] != 3 or empty["status"] != "NOT_READY" or empty[
                "ready"] is not False or any(empty["predicates"].values()):
            raise PilotBlockedError(
                "P3 empty environment must be exact NOT_READY exit 3 with every predicate false"
            )
        if invalid["exit_code"] != 2 or invalid["status"] != "INVALID_ARGUMENTS" or invalid[
                "ready"] is not False:
            raise PilotBlockedError("P3 invalid-argument matrix cell must exit 2")
        if ready["exit_code"] != 0 or ready["status"] != "READY" or ready[
                "ready"] is not True or not all(ready["predicates"].values()):
            raise PilotBlockedError(
                "P3 injected environment must be exact READY exit 0 with every predicate true"
            )
        public_runs = {
            name: {
                "exit_code": value["exit_code"],
                "status": value["status"],
                "ready": value["ready"],
                "predicates": value["predicates"],
            }
            for name, value in runs.items()
        }
        receipt = {
            "schema": "product_p3_oracle_matrix.v1",
            "status": "PASS",
            "runs": public_runs,
            "run_evidence": runs,
            "promotion_eligible": False,
        }
        _AtomicPreparationWriter().write_json(
            artifact / "matrix_receipt.v1.json", receipt,
        )
        return receipt


class ProductRuntimeSnapshot:
    """Seal the exact Bun executable and complete TypeScript 5.9.3 package tree."""

    @staticmethod
    def _bun_facts() -> Dict[str, Any]:
        path = PINNED_BUN_PATH
        try:
            identity = path.lstat()
            content = path.read_bytes()
        except OSError as exc:
            raise PilotBlockedError("pinned Bun executable is unavailable") from exc
        digest = hashlib.sha256(content).hexdigest()
        if path.is_symlink() or os.path.realpath(path) != str(path) or not stat.S_ISREG(
                identity.st_mode) or stat.S_IMODE(identity.st_mode) != PINNED_BUN_MODE or identity.st_size != PINNED_BUN_SIZE or identity.st_nlink != 1 or digest != PINNED_BUN_SHA256:
            raise PilotBlockedError("Bun executable differs from the exact runtime pin")
        process = subprocess.run(
            [str(path), "--version"], env={"LANG": "C", "PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, shell=False, timeout=30, check=False,
        )
        if process.returncode != 0 or process.stdout.strip() != PINNED_BUN_VERSION:
            raise PilotBlockedError("Bun version differs from the exact runtime pin")
        return {
            "path": str(path), "version": PINNED_BUN_VERSION,
            "sha256": digest, "mode": stat.S_IMODE(identity.st_mode),
            "size": identity.st_size, "nlink": identity.st_nlink,
        }

    @staticmethod
    def _file_record(path: Path, relative: str) -> Dict[str, Any]:
        identity = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
            raise PilotBlockedError("TypeScript snapshot contains non-regular package bytes")
        content = path.read_bytes()
        return {
            "path": relative, "mode": stat.S_IMODE(identity.st_mode),
            "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        }

    @staticmethod
    def _canonical_root(path: Path, label: str) -> Path:
        if not path.is_dir() or path.is_symlink():
            raise PilotBlockedError(label + " root is unavailable or non-canonical")
        absolute = Path(os.path.abspath(path))
        cursor = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            cursor = cursor / part
            if cursor.is_symlink():
                raise PilotBlockedError(label + " root traverses a symlink")
        return absolute

    @classmethod
    def _build(cls, project: Path, source_snapshot: Path,
               installed_dependency_root: Path) -> Dict[str, Any]:
        project = cls._canonical_root(project, "runtime snapshot project")
        source_snapshot = cls._canonical_root(
            source_snapshot, "runtime source snapshot",
        )
        installed_dependency_root = cls._canonical_root(
            installed_dependency_root, "installed dependency",
        )
        try:
            dependency_within_source = os.path.commonpath((
                str(source_snapshot), str(installed_dependency_root),
            )) == str(source_snapshot)
        except ValueError:
            dependency_within_source = False
        if not dependency_within_source:
            raise PilotBlockedError("installed dependency root is outside protected source snapshot")
        package_path = project / "package.json"
        lock_path = project / "package-lock.json"
        source_package_path = source_snapshot / "package.json"
        source_lock_path = source_snapshot / "package-lock.json"
        typescript_root = installed_dependency_root / "typescript"
        typescript_package = typescript_root / "package.json"
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            source_package = json.loads(source_package_path.read_text(encoding="utf-8"))
            source_lock = json.loads(source_lock_path.read_text(encoding="utf-8"))
            typescript = json.loads(typescript_package.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise PilotBlockedError("TypeScript runtime package metadata is unavailable") from exc
        declared = package.get("devDependencies", {}).get("typescript")
        source_declared = source_package.get("devDependencies", {}).get("typescript")
        lock_root = lock.get("packages", {}).get("", {})
        lock_typescript = lock.get("packages", {}).get("node_modules/typescript", {})
        exact_lock = (
            lock.get("lockfileVersion") == 3
            and lock_root.get("devDependencies", {}).get("typescript") == declared
            and lock_typescript.get("version") == PINNED_TYPESCRIPT_VERSION
            and lock_typescript.get("resolved") == (
                "https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz"
            )
            and isinstance(lock_typescript.get("integrity"), str)
            and lock_typescript["integrity"].startswith("sha512-")
        )
        if package_path.read_bytes() != source_package_path.read_bytes() or lock_path.read_bytes(
        ) != source_lock_path.read_bytes() or package != source_package or lock != source_lock:
            raise PilotBlockedError("fresh verifier dependency declarations differ from source snapshot")
        if declared != "^5.9.0" or source_declared != declared or not exact_lock or typescript.get(
                "name") != "typescript" or typescript.get("version") != PINNED_TYPESCRIPT_VERSION:
            raise PilotBlockedError(
                "TypeScript source range, lock, and installed package must resolve exactly to 5.9.3"
            )
        if (project / "node_modules").exists() or (project / "node_modules").is_symlink():
            raise PilotBlockedError("fresh verifier clone must not carry mutable node_modules")
        package_entries = []
        for path in sorted(typescript_root.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_dir() and not path.is_symlink():
                continue
            package_entries.append(cls._file_record(
                path, path.relative_to(typescript_root).as_posix(),
            ))
        if not package_entries:
            raise PilotBlockedError("TypeScript full package snapshot is empty")
        package_bytes = typescript_package.read_bytes()
        return {
            "schema": "product_runtime_snapshot.v1",
            "bun": cls._bun_facts(),
            "typescript": {
                "version": PINNED_TYPESCRIPT_VERSION,
                "declared_range": declared,
                "lockfile_version": lock_typescript["version"],
                "lockfile_resolved": lock_typescript["resolved"],
                "lockfile_integrity": lock_typescript["integrity"],
                "installed_dependency_root": str(installed_dependency_root),
                "package_json_sha256": hashlib.sha256(package_bytes).hexdigest(),
                "package_tree_sha256": _canonical_hash(package_entries),
                "package_entries": package_entries,
            },
            "project": {
                "package_json_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
                "package_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
            },
            "source_snapshot": {
                "root": str(source_snapshot),
                "package_json_sha256": hashlib.sha256(
                    source_package_path.read_bytes(),
                ).hexdigest(),
                "package_lock_sha256": hashlib.sha256(
                    source_lock_path.read_bytes(),
                ).hexdigest(),
            },
        }

    def capture(self, *, project_root: Any, source_snapshot_root: Any,
                installed_dependency_root: Any, snapshot_path: Any) -> Dict[str, Any]:
        receipt = self._build(
            Path(project_root), Path(source_snapshot_root),
            Path(installed_dependency_root),
        )
        path = Path(snapshot_path)
        if path.exists() or path.is_symlink():
            raise PilotBlockedError("runtime snapshot path already exists")
        _AtomicPreparationWriter().write_json(path, receipt, read_only=False)
        return receipt

    def verify(self, *, project_root: Any, source_snapshot_root: Any,
               installed_dependency_root: Any, snapshot_path: Any) -> bool:
        path = Path(snapshot_path)
        try:
            sealed = json.loads(path.read_bytes())
        except (OSError, ValueError) as exc:
            raise PilotBlockedError("runtime snapshot is unavailable or invalid") from exc
        current = self._build(
            Path(project_root), Path(source_snapshot_root),
            Path(installed_dependency_root),
        )
        if sealed != current or path.read_bytes() != _canonical_bytes(sealed) + b"\n":
            raise PilotBlockedError("Bun or TypeScript runtime snapshot was mutated")
        return True


class ProductProcessAuditor:
    """Inventory, terminate, and prove cleanup of a complete spawned lineage."""

    production_safe = True

    @staticmethod
    def _darwin_process_table() -> Dict[int, Dict[str, Any]]:
        class ProcBsdInfo(ctypes.Structure):
            _fields_ = [
                ("flags", ctypes.c_uint32), ("status", ctypes.c_uint32),
                ("xstatus", ctypes.c_uint32), ("pid", ctypes.c_uint32),
                ("ppid", ctypes.c_uint32), ("uid", ctypes.c_uint32),
                ("gid", ctypes.c_uint32), ("ruid", ctypes.c_uint32),
                ("rgid", ctypes.c_uint32), ("svuid", ctypes.c_uint32),
                ("svgid", ctypes.c_uint32), ("rfu_1", ctypes.c_uint32),
                ("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32),
                ("nfiles", ctypes.c_uint32), ("pgid", ctypes.c_uint32),
                ("pjobc", ctypes.c_uint32), ("e_tdev", ctypes.c_uint32),
                ("e_tpgid", ctypes.c_uint32), ("nice", ctypes.c_int32),
                ("start_tvsec", ctypes.c_uint64),
                ("start_tvusec", ctypes.c_uint64),
            ]

        library_path = ctypes.util.find_library("proc")
        if not library_path:
            raise PilotBlockedError("production process auditor cannot load libproc")
        library = ctypes.CDLL(library_path, use_errno=True)
        library.proc_listpids.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int,
        ]
        library.proc_listpids.restype = ctypes.c_int
        library.proc_pidinfo.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int,
        ]
        library.proc_pidinfo.restype = ctypes.c_int
        required = library.proc_listpids(1, 0, None, 0)
        if required <= 0:
            raise PilotBlockedError("production process auditor could not list processes")
        buffer = (ctypes.c_int * (required // ctypes.sizeof(ctypes.c_int) + 64))()
        received = library.proc_listpids(1, 0, buffer, ctypes.sizeof(buffer))
        if received <= 0:
            raise PilotBlockedError("production process auditor could not sample processes")
        table: Dict[int, Dict[str, Any]] = {}
        for pid in buffer[:received // ctypes.sizeof(ctypes.c_int)]:
            if pid <= 0:
                continue
            info = ProcBsdInfo()
            size = library.proc_pidinfo(
                pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info),
            )
            if size != ctypes.sizeof(info):
                continue
            try:
                sid = os.getsid(pid)
            except (OSError, ProcessLookupError):
                sid = -1
            command = bytes(info.name).split(b"\0", 1)[0].decode("utf-8", "replace")
            table[pid] = {
                "pid": pid, "ppid": int(info.ppid), "pgid": int(info.pgid),
                "sid": sid, "stat": "Z" if info.status == 5 else str(info.status),
                "command": command,
            }
        return table

    @classmethod
    def _process_table(cls) -> Dict[int, Dict[str, Any]]:
        if sys.platform == "darwin":
            return cls._darwin_process_table()
        process = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid=,pgid=,sid=,stat=,command="],
            env={"LANG": "C", "PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, shell=False,
            timeout=10, check=False,
        )
        if process.returncode != 0:
            raise PilotBlockedError("production process auditor could not sample processes")
        table: Dict[int, Dict[str, Any]] = {}
        for raw in process.stdout.splitlines():
            fields = raw.strip().split(None, 5)
            if len(fields) < 5:
                continue
            try:
                pid, ppid, pgid, sid = (int(value) for value in fields[:4])
            except ValueError:
                continue
            table[pid] = {
                "pid": pid, "ppid": ppid, "pgid": pgid, "sid": sid,
                "stat": fields[4], "command": fields[5] if len(fields) == 6 else "",
            }
        return table

    @classmethod
    def _audit(cls, *, leader_pid: int, leader_pgid: int,
               remembered: Iterable[int] = ()) -> Dict[str, Any]:
        table = cls._process_table()
        descendants = set(int(pid) for pid in remembered)
        frontier = {leader_pid}
        while frontier:
            discovered = {
                pid for pid, record in table.items()
                if record["ppid"] in frontier and pid not in descendants
            }
            descendants.update(discovered)
            frontier = discovered
        descendants.update(
            pid for pid, record in table.items()
            if pid != leader_pid and record["pgid"] == leader_pgid
        )
        live_descendants = sorted(
            pid for pid in descendants
            if pid in table and not table[pid]["stat"].startswith("Z")
        )
        leader_live = leader_pid in table and not table[leader_pid]["stat"].startswith("Z")
        leader_sid = table.get(leader_pid, {}).get("sid")
        escaped = sorted(
            pid for pid in live_descendants
            if leader_sid is not None and table[pid]["sid"] != leader_sid
        )
        return {
            "empty": not leader_live and not live_descendants,
            "leader_pid": leader_pid,
            "leader_pgid": leader_pgid,
            "descendant_pids": live_descendants,
            "escaped_session_descendant_pids": escaped,
            "sampled_processes": [table[pid] for pid in live_descendants if pid in table],
        }

    @staticmethod
    def _send(pid: int, requested_signal: int,
              evidence: list[Dict[str, Any]]) -> None:
        try:
            os.kill(pid, requested_signal)
            evidence.append({"pid": pid, "signal": signal.Signals(requested_signal).name})
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise PilotBlockedError("production process auditor could not signal lineage") from exc

    def cleanup_and_audit(self, *, leader_pid: int, leader_pgid: int,
                          grace_seconds: float = 0.2) -> Dict[str, Any]:
        if type(leader_pid) is not int or leader_pid <= 0 or type(
                leader_pgid) is not int or leader_pgid <= 0 or not isinstance(
                    grace_seconds, (int, float)) or grace_seconds < 0:
            raise PilotBlockedError("production process auditor inputs are invalid")
        sampled_at_ns = time.time_ns()
        initial = self._audit(leader_pid=leader_pid, leader_pgid=leader_pgid)
        remembered = set(initial["descendant_pids"])
        signals: list[Dict[str, Any]] = []
        targets = [*initial["descendant_pids"], leader_pid]
        for pid in targets:
            self._send(pid, signal.SIGTERM, signals)
        if targets and grace_seconds:
            time.sleep(float(grace_seconds))
        after_term = self._audit(
            leader_pid=leader_pid, leader_pgid=leader_pgid, remembered=remembered,
        )
        for pid in [*after_term["descendant_pids"], leader_pid]:
            self._send(pid, signal.SIGKILL, signals)
        deadline = time.monotonic() + max(0.2, float(grace_seconds) * 4)
        final_detail = after_term
        while time.monotonic() < deadline:
            try:
                os.waitpid(leader_pid, os.WNOHANG)
            except (ChildProcessError, ProcessLookupError):
                pass
            final_detail = self._audit(
                leader_pid=leader_pid, leader_pgid=leader_pgid, remembered=remembered,
            )
            if final_detail["empty"]:
                break
            time.sleep(0.01)
        if not final_detail["empty"]:
            error = PilotBlockedError("production process auditor cleanup left live descendants")
            error.observation = {
                "initial_audit": initial, "signals": signals,
                "final_audit": final_detail,
            }
            raise error
        return {
            "schema": "product_process_cleanup.v1", "status": "PASS",
            "sampled_at_ns": sampled_at_ns, "finished_at_ns": time.time_ns(),
            "initial_audit": initial, "signals": signals,
            "final_audit": {"empty": True, "descendant_pids": []},
        }


class OracleGeneratorAuthority:
    """Seal the P2 oracle generator and materialize equal bytes after coder cleanup."""

    GENERATOR_VERSION = "p2-bun-typescript-oracle-generator.v1"

    def __init__(self, *, artifact_root: Path, case_id: str, clock_ns: Any) -> None:
        self.artifact_root = artifact_root
        self.case_id = case_id
        self.clock_ns = clock_ns
        self._seal: Optional[Dict[str, Any]] = None

    @classmethod
    def for_p2(cls, *, artifact_root: Any,
               clock_ns: Any = time.time_ns) -> "OracleGeneratorAuthority":
        return cls(
            artifact_root=Path(artifact_root), case_id=PREPARATION_CASES[1],
            clock_ns=clock_ns,
        )

    @staticmethod
    def _render_oracle() -> bytes:
        source = r"""import fs from 'node:fs';

const sourcePath = 'src/routes/app.feed.tsx';
const source = fs.readFileSync(sourcePath, 'utf8');
const transpiler = new Bun.Transpiler({ loader: 'tsx' });
let syntaxValid = true;
try { transpiler.transformSync(source); } catch (_) { syntaxValid = false; }

function stripComments(text) {
  let out = '', quote = null, escaped = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i], next = text[i + 1];
    if (quote) {
      out += ch;
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch; out += ch;
    } else if (ch === '/' && next === '/') {
      out += '  '; i += 2;
      while (i < text.length && text[i] !== '\n') { out += ' '; i += 1; }
      if (i < text.length) out += '\n';
    } else if (ch === '/' && next === '*') {
      out += '  '; i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) {
        out += text[i] === '\n' ? '\n' : ' '; i += 1;
      }
      out += '  '; i += 1;
    } else out += ch;
  }
  return out;
}

function matchingBrace(text, open) {
  let depth = 0, quote = null, escaped = false;
  for (let i = open; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'" || ch === '`') quote = ch;
    else if (ch === '{') depth += 1;
    else if (ch === '}' && --depth === 0) return i;
  }
  return -1;
}

const clean = stripComments(source);
const contractPattern = /\b(?:export\s+)?const\s+createAskTaxaheadHandler\s*=\s*\(\s*deps\s*:\s*[^)]+\)\s*=>\s*async\s*\(\s*text\s*:\s*string\s*\)\s*:\s*Promise\s*<\s*void\s*>\s*=>/m;
const contractMatch = contractPattern.exec(clean);
const feedMarker = /\bfunction\s+FeedComposer\s*\([^)]*\)\s*\{/.exec(clean);
let feedBody = '';
if (feedMarker) {
  const open = clean.indexOf('{', feedMarker.index);
  const close = matchingBrace(clean, open);
  if (close > open) feedBody = clean.slice(open + 1, close);
}
const directAssignment = /\bconst\s+handleSend\s*=\s*createAskTaxaheadHandler\s*\(\s*deps\s*\)\s*;/.test(feedBody);

let factory = null;
if (contractMatch && syntaxValid) {
  const firstArrow = clean.indexOf('=>', contractMatch.index);
  const secondArrow = clean.indexOf('=>', firstArrow + 2);
  const open = clean.indexOf('{', secondArrow + 2);
  const close = matchingBrace(clean, open);
  if (firstArrow > 0 && secondArrow > firstArrow && open > secondArrow && close > open) {
    let snippet = clean.slice(contractMatch.index, close + 1).replace(/^export\s+/, '');
    try {
      const transformed = transpiler.transformSync(snippet);
      factory = new Function(`${transformed}\nreturn createAskTaxaheadHandler;`)();
    } catch (_) { factory = null; }
  }
}

async function behavioralRun(mode) {
  const transitions = [], calls = [];
  const deps = {
    filingUnit: { id: 'filing-unit-42' },
    askTaxahead: async (input) => {
      calls.push({ filingUnitId: input?.filingUnit?.id || null, text: input?.text || null });
      if (mode === 'error') throw new Error('synthetic failure');
      return { answer: 'Grounded answer', evidence: ['evidence-1'] };
    },
    setLoading: (value) => transitions.push(`loading:${String(value)}`),
    setAnswer: (value) => transitions.push(`answer:${String(value)}`),
    setEvidence: (value) => transitions.push(`evidence:${Array.isArray(value) ? value.join(',') : String(value)}`),
    setError: (value) => transitions.push(`error:${String(value)}`),
  };
  try {
    const handler = typeof factory === 'function' ? factory(deps) : null;
    if (typeof handler !== 'function') throw new Error('factory handler unavailable');
    await handler('hello');
  } catch (error) {
    if (!transitions.some((value) => value.startsWith('error:'))) {
      transitions.push(`uncaught:${String(error?.message || error)}`);
    }
  }
  return { handlerInput: 'hello', calls, transitions };
}

const success = await behavioralRun('success');
const failure = await behavioralRun('error');
const exactCall = (run) => run.calls.length === 1 && run.calls[0].filingUnitId === 'filing-unit-42' && run.calls[0].text === 'hello';
const facts = {
  schema: 'p2-handle-send-oracle.v1', status: 'FAIL',
  factory_contract: {
    factory_symbol: 'createAskTaxaheadHandler',
    handler_parameter: 'text:string', handler_return: 'Promise<void>',
    feed_composer_direct_assignment: directAssignment,
  },
  handle_send_calls_ask_taxahead: exactCall(success) && exactCall(failure),
  filing_unit_input: exactCall(success) && exactCall(failure),
  loading_state: success.transitions[0] === 'loading:true' && success.transitions.at(-1) === 'loading:false' && failure.transitions[0] === 'loading:true' && failure.transitions.at(-1) === 'loading:false',
  answer_state: success.transitions.includes('answer:Grounded answer'),
  evidence_state: success.transitions.includes('evidence:evidence-1'),
  error_state: failure.transitions.includes('error:synthetic failure'),
  behavioral_runs: {
    success: { handler_input: success.handlerInput, filing_unit_id: success.calls[0]?.filingUnitId || null, transitions: success.transitions },
    error: { handler_input: failure.handlerInput, filing_unit_id: failure.calls[0]?.filingUnitId || null, transitions: failure.transitions },
  },
  ast_parser: 'bun-typescript-transpiler',
};
facts.status = syntaxValid && contractMatch !== null && directAssignment && [
  'handle_send_calls_ask_taxahead', 'filing_unit_input', 'loading_state',
  'answer_state', 'evidence_state', 'error_state',
].every((key) => facts[key] === true) ? 'PASS' : 'FAIL';
console.log(JSON.stringify(facts));
process.exit(facts.status === 'PASS' ? 0 : 1);
"""
        return source.encode("utf-8")

    def seal(self) -> Dict[str, Any]:
        if self._seal is not None:
            return json.loads(json.dumps(self._seal))
        if self.artifact_root.exists() or self.artifact_root.is_symlink():
            raise PilotBlockedError("oracle generator authority root must be fresh")
        self.artifact_root.mkdir(parents=True, mode=0o700)
        generator_source = inspect.getsource(type(self)._render_oracle).encode("utf-8")
        generator_input = {
            "case_id": self.case_id,
            "source_path": "src/routes/app.feed.tsx",
            "contract": "createAskTaxaheadHandler(deps)->(text:string)=>Promise<void>",
        }
        self._seal = {
            "schema": "oracle_generator_authority.v1", "case_id": self.case_id,
            "generator_version": self.GENERATOR_VERSION,
            "generator_sha256": hashlib.sha256(generator_source).hexdigest(),
            "input_sha256": _canonical_hash(generator_input),
        }
        _AtomicPreparationWriter().write_json(
            self.artifact_root / "generator-authority.v1.json", self._seal,
        )
        return json.loads(json.dumps(self._seal))

    def materialize(self, *, arm_id: str, destination: Any,
                    coder_cleanup_finished_at_ns: int) -> Dict[str, Any]:
        if self._seal is None:
            raise PilotBlockedError("oracle generator must be sealed before materialization")
        if not isinstance(arm_id, str) or not arm_id or type(
                coder_cleanup_finished_at_ns) is not int:
            raise PilotBlockedError("oracle materialization arm or cleanup timestamp is invalid")
        materialized_at = self.clock_ns()
        if type(materialized_at) is not int or materialized_at <= coder_cleanup_finished_at_ns:
            raise PilotBlockedError("oracle materialization timestamp is not after coder cleanup")
        path = Path(destination)
        if path.exists() or path.is_symlink():
            raise PilotBlockedError("oracle materialization destination already exists")
        oracle_bytes = self._render_oracle()
        _AtomicPreparationWriter().write_bytes(path, oracle_bytes, read_only=True)
        return {
            "schema": "oracle_materialization_receipt.v1", "case_id": self.case_id,
            "arm_id": arm_id, "oracle_path": str(path),
            "oracle_sha256": hashlib.sha256(oracle_bytes).hexdigest(),
            "generator_version": self._seal["generator_version"],
            "generator_sha256": self._seal["generator_sha256"],
            "input_sha256": self._seal["input_sha256"],
            "coder_cleanup_finished_at_ns": coder_cleanup_finished_at_ns,
            "materialized_at_ns": materialized_at,
        }

    def validate_arm_receipts(self, receipts: Any) -> bool:
        if not isinstance(receipts, list) or len(receipts) < 2 or self._seal is None:
            raise PilotBlockedError("oracle arm receipts are incomplete")
        hashes = set()
        for receipt in receipts:
            if not isinstance(receipt, dict) or receipt.get(
                    "schema") != "oracle_materialization_receipt.v1" or receipt.get(
                        "generator_sha256") != self._seal["generator_sha256"] or receipt.get(
                            "input_sha256") != self._seal["input_sha256"] or not _is_sha256(
                                receipt.get("oracle_sha256")) or receipt.get(
                                    "materialized_at_ns", 0) <= receipt.get(
                                        "coder_cleanup_finished_at_ns", 0):
                raise PilotBlockedError("oracle arm receipt hash or timestamp mismatch")
            path = Path(receipt.get("oracle_path", ""))
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise PilotBlockedError("oracle arm materialization is unavailable") from exc
            if digest != receipt["oracle_sha256"]:
                raise PilotBlockedError("oracle arm bytes mismatch their receipt")
            hashes.add(digest)
        if len(hashes) != 1:
            raise PilotBlockedError("oracle hashes mismatch across coder arms")
        return True


class ProductOracleSandbox:
    """Run structured canaries and one oracle under byte-identical Seatbelt policy."""

    CANARY_DENIED_EXIT = 77

    def __init__(self, *, popen_factory: Any = subprocess.Popen,
                 process_auditor: Any = None, clock_ns: Any = time.time_ns,
                 test_mode: bool = False) -> None:
        if not test_mode and popen_factory is not subprocess.Popen:
            raise PilotBlockedError("production oracle sandbox requires concrete process creation")
        if process_auditor is None:
            process_auditor = ProductProcessAuditor()
        if not test_mode and type(process_auditor) is not ProductProcessAuditor:
            raise PilotBlockedError("production oracle sandbox requires concrete trusted auditor")
        self.popen_factory = popen_factory
        self.process_auditor = process_auditor
        self.clock_ns = clock_ns
        self.test_mode = test_mode

    @staticmethod
    def _policy(*, clone: Path, artifact: Path, fake_home: Path) -> str:
        def escaped(path: Path) -> str:
            return str(path).replace('"', '\\"')
        read_roots = (clone, artifact, Path("/usr"), Path("/bin"), Path("/System"),
                      Path("/Library"), PINNED_BUN_PATH.parent)
        read_rules = tuple(
            '(allow file-read* (subpath "%s"))' % escaped(root)
            for root in read_roots
        )
        return "\n".join((
            "(version 1)", "(deny default)", "(allow process-exec)",
            "(deny process-fork)", *read_rules,
            '(allow file-write* (subpath "%s"))' % escaped(artifact),
            '(deny file-read* (subpath "%s"))' % escaped(fake_home),
            "(deny network*)", "",
        ))

    @classmethod
    def _canary_script(cls, kind: str) -> str:
        target = (
            "open(os.environ['LOOP_ORACLE_SECRET_PATH'],'rb').read()"
            if kind == "home_secret" else
            "socket.create_connection((%r,9),0.1)" % (
                "127.0.0.1" if kind == "network_loopback" else "203.0.113.1"
            )
        )
        return (
            "import errno,json,os,socket,sys\n"
            "probe=os.environ['LOOP_ORACLE_PROBE_KIND']\n"
            "try:\n " + target + "\n"
            "except PermissionError as exc:\n"
            " name=errno.errorcode.get(exc.errno,'UNKNOWN')\n"
            " print(json.dumps({'schema':'product_oracle_canary.v1','status':'DENIED','probe':probe,'errno':name},sort_keys=True,separators=(',',':')))\n"
            " sys.exit(77 if name in ('EPERM','EACCES') else 1)\n"
            "except Exception:\n sys.exit(1)\n"
            "sys.exit(1)\n"
        )

    @classmethod
    def _parse_canary(cls, *, kind: str, returncode: int,
                      stdout: str) -> str:
        if returncode != cls.CANARY_DENIED_EXIT:
            raise PilotBlockedError("oracle canary lacked dedicated DENIED exit")
        try:
            payload = json.loads(stdout)
        except (TypeError, ValueError) as exc:
            raise PilotBlockedError("oracle canary lacked structured DENIED JSON") from exc
        expected_keys = {"schema", "status", "probe", "errno"}
        if not isinstance(payload, dict) or set(payload) != expected_keys or payload.get(
                "schema") != "product_oracle_canary.v1" or payload.get(
                    "status") != "DENIED" or payload.get("probe") != kind or payload.get(
                        "errno") not in {"EPERM", "EACCES"}:
            raise PilotBlockedError("oracle canary is not exact DENIED EPERM/EACCES evidence")
        return "DENIED_" + payload["errno"]

    def run(self, *, clone_path: Any, artifact_dir: Any, fake_home_root: Any,
            oracle_argv: list[str], oracle_bytes: bytes) -> Dict[str, Any]:
        clone, artifact, fake_home = Path(clone_path), Path(artifact_dir), Path(fake_home_root)
        if clone.exists() and (not clone.is_dir() or clone.is_symlink()):
            raise PilotBlockedError("oracle sandbox clone is non-canonical")
        clone.mkdir(parents=True, exist_ok=True)
        if artifact.exists() or artifact.is_symlink() or fake_home.exists() or fake_home.is_symlink():
            raise PilotBlockedError("oracle sandbox roots must be fresh")
        if not isinstance(oracle_argv, list) or not oracle_argv or any(
                not isinstance(token, str) or not token for token in oracle_argv) or not isinstance(
                    oracle_bytes, bytes) or not oracle_bytes:
            raise PilotBlockedError("oracle sandbox command or bytes are invalid")
        artifact.mkdir(parents=True, mode=0o700)
        fake_home.mkdir(parents=True, mode=0o700)
        secret_path = fake_home / ".product-oracle-secret"
        secret_path.write_bytes(b"ORACLE_HOME_SECRET_CANARY\n")
        secret_path.chmod(0o400)
        oracle_path = artifact / "controller-hidden-oracle.mjs"
        oracle_path.write_bytes(oracle_bytes)
        oracle_path.chmod(0o400)
        policy = self._policy(clone=clone, artifact=artifact, fake_home=fake_home)
        commands = tuple(
            (kind, ["/usr/bin/python3", "-c", self._canary_script(kind)])
            for kind in ("home_secret", "network_external", "network_loopback")
        ) + (("oracle", list(oracle_argv)),)
        processes, cleanup_receipts = [], []
        canaries: Dict[str, str] = {}
        oracle_result: Optional[Dict[str, Any]] = None
        primary_error: Optional[BaseException] = None
        try:
            for kind, command in commands:
                effective_argv = ["/usr/bin/sandbox-exec", "-p", policy, *command]
                env = {
                    "LANG": "C", "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
                    "HOME": str(fake_home), "LOOP_ORACLE_PROBE_KIND": kind,
                    "LOOP_ORACLE_SECRET_PATH": str(secret_path),
                }
                started = self.clock_ns()
                process = self.popen_factory(
                    effective_argv, cwd=str(clone), env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, shell=False,
                    start_new_session=True,
                )
                try:
                    stdout, stderr = process.communicate(timeout=900)
                finally:
                    cleanup_receipt = self.process_auditor.cleanup_and_audit(
                        leader_pid=process.pid, leader_pgid=process.pid,
                        grace_seconds=0.2,
                    )
                    cleanup_receipts.append(cleanup_receipt)
                finished = self.clock_ns()
                returncode = process.returncode
                record = {
                    "kind": kind, "pid": process.pid,
                    "started_at_ns": started, "finished_at_ns": finished,
                    "exit_code": returncode,
                    "argv_sha256": _canonical_hash(effective_argv),
                    "policy_sha256": hashlib.sha256(policy.encode("utf-8")).hexdigest(),
                    "stdout_sha256": hashlib.sha256((stdout or "").encode("utf-8")).hexdigest(),
                    "stderr_sha256": hashlib.sha256((stderr or "").encode("utf-8")).hexdigest(),
                    "cleanup_receipt": cleanup_receipt,
                }
                processes.append(record)
                if finished <= started:
                    raise PilotBlockedError("oracle process timestamps are not monotonic")
                if kind == "oracle":
                    oracle_result = {
                        "exit_code": returncode, "stdout": stdout or "", "stderr": stderr or "",
                    }
                    if returncode != 0:
                        raise PilotBlockedError("controller hidden oracle failed in sandbox")
                else:
                    canaries[kind] = self._parse_canary(
                        kind=kind, returncode=returncode, stdout=stdout or "",
                    )
        except BaseException as exc:
            primary_error = exc
        finally:
            try:
                if oracle_path.exists():
                    oracle_path.chmod(0o600)
                    oracle_path.unlink()
                if secret_path.exists():
                    secret_path.chmod(0o600)
                shutil.rmtree(fake_home, ignore_errors=False)
            except OSError:
                if primary_error is None:
                    primary_error = PilotBlockedError("oracle sandbox cleanup failed")
        cleanup = {
            "process_group_empty": bool(cleanup_receipts) and all(
                receipt.get("final_audit") == {"empty": True, "descendant_pids": []}
                for receipt in cleanup_receipts
            ),
            "fake_home_removed": not fake_home.exists(),
            "oracle_temp_removed": not oracle_path.exists(),
        }
        if primary_error is not None:
            raise primary_error
        if set(canaries) != {"home_secret", "network_external", "network_loopback"} or oracle_result is None or cleanup != {
                "process_group_empty": True, "fake_home_removed": True,
                "oracle_temp_removed": True,
        }:
            raise PilotBlockedError("oracle sandbox evidence or cleanup is incomplete")
        return {
            "schema": "product_oracle_sandbox_receipt.v1",
            "status": "PASS", "mechanism": "macos-sandbox-exec",
            "policy_sha256": hashlib.sha256(policy.encode("utf-8")).hexdigest(),
            "oracle_sha256": hashlib.sha256(oracle_bytes).hexdigest(),
            "canaries": canaries, "processes": processes,
            "oracle": oracle_result, "cleanup": cleanup,
            "read_roots": [
                str(clone), str(artifact), "/usr", "/bin", "/System", "/Library",
                str(PINNED_BUN_PATH.parent),
            ],
            "promotion_eligible": False,
        }


class ProductGitAuthority:
    """Seal one clone's complete Git control store without cross-clone byte comparison."""

    SCHEMA = "product_git_authority.v1"

    @staticmethod
    def _canonical_control_directory(path: Path) -> Path:
        absolute = Path(os.path.abspath(path))
        cursor = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            cursor = cursor / part
            try:
                identity = cursor.lstat()
            except OSError as exc:
                raise PilotBlockedError("Git control directory is unavailable") from exc
            if stat.S_ISLNK(identity.st_mode):
                raise PilotBlockedError("Git control directory traverses a symlink")
        if not absolute.is_dir():
            raise PilotBlockedError("Git control path is not a directory")
        return absolute

    @classmethod
    def _resolve_git_roots(cls, root: Path) -> tuple[Path, Path, list[Dict[str, Any]]]:
        marker = root / ".git"
        marker_identity = marker.lstat() if os.path.lexists(marker) else None
        marker_entries: list[Dict[str, Any]] = []
        if marker_identity is None or stat.S_ISLNK(marker_identity.st_mode):
            raise PilotBlockedError("Git authority requires a no-follow .git marker")
        if stat.S_ISDIR(marker_identity.st_mode):
            git_dir = cls._canonical_control_directory(marker)
        elif stat.S_ISREG(marker_identity.st_mode) and marker_identity.st_nlink == 1:
            content = marker.read_bytes()
            match = re.fullmatch(rb"gitdir: ([^\r\n]+)\n?", content)
            if match is None:
                raise PilotBlockedError("Git authority .git file is malformed")
            declared = Path(os.fsdecode(match.group(1)))
            git_dir = cls._canonical_control_directory(
                declared if declared.is_absolute() else root / declared,
            )
            marker_entries.append({
                "root": "marker", "path": ".git", "type": "file",
                "mode": stat.S_IMODE(marker_identity.st_mode), "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        else:
            raise PilotBlockedError("Git authority .git marker has invalid identity")
        commondir_marker = git_dir / "commondir"
        if os.path.lexists(commondir_marker):
            identity = commondir_marker.lstat()
            if identity.st_nlink != 1 or not stat.S_ISREG(identity.st_mode):
                raise PilotBlockedError("Git commondir marker has invalid identity")
            content = commondir_marker.read_bytes()
            try:
                declared_text = content.decode("utf-8").strip()
            except UnicodeError as exc:
                raise PilotBlockedError("Git commondir marker is not UTF-8") from exc
            declared = Path(declared_text)
            common_dir = cls._canonical_control_directory(
                declared if declared.is_absolute() else git_dir / declared,
            )
        else:
            common_dir = git_dir
        return git_dir, common_dir, marker_entries

    @staticmethod
    def _inventory_root(root: Path, label: str) -> list[Dict[str, Any]]:
        records: list[Dict[str, Any]] = []

        def visit(directory: Path, prefix: str = "") -> None:
            try:
                children = sorted(os.scandir(directory), key=lambda entry: entry.name)
            except OSError as exc:
                raise PilotBlockedError("Git authority inventory failed") from exc
            for entry in children:
                relative = entry.name if not prefix else prefix + "/" + entry.name
                identity = entry.stat(follow_symlinks=False)
                mode = stat.S_IMODE(identity.st_mode)
                if stat.S_ISLNK(identity.st_mode):
                    raise PilotBlockedError("Git authority contains a symlink")
                if stat.S_ISDIR(identity.st_mode):
                    records.append({
                        "root": label, "path": relative, "type": "directory",
                        "mode": mode,
                    })
                    visit(Path(entry.path), relative)
                elif stat.S_ISREG(identity.st_mode) and identity.st_nlink == 1:
                    content = Path(entry.path).read_bytes()
                    records.append({
                        "root": label, "path": relative, "type": "file",
                        "mode": mode, "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    })
                else:
                    raise PilotBlockedError("Git authority contains linked or special metadata")

        visit(root)
        return records

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        process = subprocess.run(
            ["git", "-C", str(root), *arguments],
            env={"LANG": "C", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=False, shell=False,
            timeout=30, check=False,
        )
        if process.returncode != 0:
            raise PilotBlockedError("Git authority command failed")
        try:
            return process.stdout.decode("utf-8").strip()
        except UnicodeError as exc:
            raise PilotBlockedError("Git authority output is not canonical UTF-8") from exc

    @classmethod
    def capture(cls, root_value: Any, *, expected_commit: str) -> Dict[str, Any]:
        root = Path(root_value)
        if not root.is_dir() or root.is_symlink() or not re.fullmatch(
                r"[0-9a-f]{40}", expected_commit or ""):
            raise PilotBlockedError("Git authority root or expected commit is invalid")
        head = cls._git(root, "rev-parse", "HEAD")
        clean = cls._git(root, "status", "--porcelain=v1", "--untracked-files=all") == ""
        if head != expected_commit or not clean:
            raise PilotBlockedError("Git authority requires the exact clean expected commit")
        git_dir, common_dir, marker_entries = cls._resolve_git_roots(root)
        entries = list(marker_entries)
        entries.extend(cls._inventory_root(git_dir, "gitdir"))
        if common_dir != git_dir:
            entries.extend(cls._inventory_root(common_dir, "commondir"))
        descriptor = {
            "root_realpath": os.path.realpath(root),
            "gitdir_realpath": os.path.realpath(git_dir),
            "commondir_realpath": os.path.realpath(common_dir),
            "entries": entries,
        }
        return {
            "schema": cls.SCHEMA, "head": head, "clean": True,
            **descriptor, "authority_sha256": _canonical_hash(descriptor),
        }

    @classmethod
    def verify(cls, root_value: Any, seal: Any, *, expected_commit: str) -> bool:
        if not isinstance(seal, dict) or seal.get("schema") != cls.SCHEMA:
            raise PilotBlockedError("Git authority seal is missing")
        root = Path(root_value)
        head = cls._git(root, "rev-parse", "HEAD")
        if head != expected_commit:
            raise PilotBlockedError("Git HEAD mutated after its clone-local seal")
        git_dir, common_dir, marker_entries = cls._resolve_git_roots(root)
        entries = list(marker_entries)
        entries.extend(cls._inventory_root(git_dir, "gitdir"))
        if common_dir != git_dir:
            entries.extend(cls._inventory_root(common_dir, "commondir"))
        descriptor = {
            "root_realpath": os.path.realpath(root),
            "gitdir_realpath": os.path.realpath(git_dir),
            "commondir_realpath": os.path.realpath(common_dir),
            "entries": entries,
        }
        current = {
            "schema": cls.SCHEMA, "head": head, "clean": True,
            **descriptor, "authority_sha256": _canonical_hash(descriptor),
        }
        if current != seal:
            raise PilotBlockedError("Git control authority mutated after its clone-local seal")
        return True

    @classmethod
    def compatible_clean_clones(cls, first: Any, second: Any) -> bool:
        if not all(isinstance(value, dict) and value.get("schema") == cls.SCHEMA
                   for value in (first, second)) or first.get("clean") is not True or second.get(
                       "clean") is not True or first.get("head") != second.get("head"):
            raise PilotBlockedError("Git clone authorities are not clean commit-compatible")
        return True


class ProductTreeDelta:
    """Canonical product-worktree delta that excludes Git control metadata."""

    SCHEMA = "product_tree_delta.v1"

    @staticmethod
    def _normalize_relative(path_value: Any) -> str:
        if not isinstance(path_value, str) or not path_value or "\x00" in path_value:
            raise PilotBlockedError("delta path is empty or invalid")
        if os.path.isabs(path_value):
            raise PilotBlockedError("delta path must be relative")
        normalized = Path(path_value).as_posix().rstrip("/")
        parts = normalized.split("/")
        if normalized in {"", "."} or any(part in {"", ".", ".."} for part in parts):
            raise PilotBlockedError("delta path escapes or is non-canonical")
        if ".git" in parts:
            raise PilotBlockedError("Git control metadata is outside the product delta")
        return normalized

    @classmethod
    def _root_git_authority(cls, root_value: Any) -> Dict[str, Any]:
        root = Path(root_value)
        git = root / ".git"
        if not os.path.lexists(git):
            return {"schema": "root_git_authority.v1", "kind": "absent", "entries": []}
        if git.is_symlink() or not git.is_dir():
            raise PilotBlockedError("root Git metadata must be a canonical directory")
        entries: list[Dict[str, Any]] = []

        def visit(directory: Path, prefix: str = "") -> None:
            for entry in sorted(os.scandir(directory), key=lambda item: item.name):
                relative = entry.name if not prefix else prefix + "/" + entry.name
                identity = entry.stat(follow_symlinks=False)
                mode = stat.S_IMODE(identity.st_mode)
                if stat.S_ISLNK(identity.st_mode):
                    raise PilotBlockedError("root Git control metadata contains a symlink")
                if stat.S_ISDIR(identity.st_mode):
                    entries.append({"path": relative, "type": "directory", "mode": mode})
                    visit(Path(entry.path), relative)
                elif stat.S_ISREG(identity.st_mode) and identity.st_nlink == 1:
                    content = Path(entry.path).read_bytes()
                    entries.append({
                        "path": relative, "type": "file", "mode": mode,
                        "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                    })
                else:
                    raise PilotBlockedError("root Git control metadata has invalid file identity")

        visit(git)
        return {
            "schema": "root_git_authority.v1", "kind": "directory",
            "entries": entries, "authority_sha256": _canonical_hash(entries),
        }

    @classmethod
    def _allowed_paths(cls, values: Iterable[str]) -> tuple[str, ...]:
        if isinstance(values, (str, bytes)):
            raise PilotBlockedError("delta allowlist must be a path sequence")
        normalized = tuple(cls._normalize_relative(value) for value in values)
        if not normalized or len(normalized) != len(set(normalized)):
            raise PilotBlockedError("delta allowlist is empty or duplicated")
        return normalized

    @staticmethod
    def _path_allowed(relative: str, allowed: tuple[str, ...]) -> bool:
        return any(relative == root or relative.startswith(root + "/") for root in allowed)

    @classmethod
    def _inventory(cls, root_value: Any, *, include_bytes: bool = False
                   ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, bytes]]:
        root = Path(root_value)
        if not root.is_dir() or root.is_symlink():
            raise PilotBlockedError("product tree root is unavailable or non-canonical")
        records: Dict[str, Dict[str, Any]] = {}
        contents: Dict[str, bytes] = {}

        def visit(directory: Path, prefix: str = "") -> None:
            try:
                entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
            except OSError as exc:
                raise PilotBlockedError("product tree cannot be inventoried") from exc
            for entry in entries:
                if not prefix and entry.name == ".git":
                    continue
                relative = entry.name if not prefix else prefix + "/" + entry.name
                cls._normalize_relative(relative)
                try:
                    identity = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise PilotBlockedError("product tree entry cannot be stated") from exc
                mode = stat.S_IMODE(identity.st_mode)
                if stat.S_ISLNK(identity.st_mode):
                    target = os.readlink(entry.path)
                    if os.path.isabs(target):
                        raise PilotBlockedError("product symlink target escapes the tree")
                    lexical = os.path.normpath(os.path.join(os.path.dirname(relative), target))
                    if lexical == ".." or lexical.startswith("../"):
                        raise PilotBlockedError("product symlink target escapes the tree")
                    records[relative] = {
                        "path": relative, "type": "symlink", "mode": mode,
                        "target": target,
                    }
                elif stat.S_ISDIR(identity.st_mode):
                    records[relative] = {
                        "path": relative, "type": "directory", "mode": mode,
                    }
                    visit(Path(entry.path), relative)
                elif stat.S_ISREG(identity.st_mode):
                    if identity.st_nlink != 1:
                        raise PilotBlockedError(
                            "product tree regular file has a hardlink/inode link count"
                        )
                    try:
                        content = Path(entry.path).read_bytes()
                    except OSError as exc:
                        raise PilotBlockedError("product tree file cannot be read") from exc
                    records[relative] = {
                        "path": relative, "type": "file", "mode": mode,
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                    if include_bytes:
                        contents[relative] = content
                else:
                    raise PilotBlockedError("product tree contains a special file")

        visit(root)
        return records, contents

    @staticmethod
    def _inventory_hash(records: Dict[str, Dict[str, Any]]) -> str:
        return _canonical_hash([records[path] for path in sorted(records)])

    @classmethod
    def tree_hash(cls, root_value: Any) -> str:
        records, _ = cls._inventory(root_value)
        return cls._inventory_hash(records)

    @classmethod
    def capture(cls, baseline: Any, changed: Any, *,
                allowed_paths: Iterable[str],
                changed_git_seal: Optional[Dict[str, Any]] = None,
                expected_commit: Optional[str] = None) -> Dict[str, Any]:
        allowed = cls._allowed_paths(allowed_paths)
        baseline_git = cls._root_git_authority(baseline)
        if changed_git_seal is None:
            changed_git = cls._root_git_authority(changed)
            if baseline_git != changed_git:
                raise PilotBlockedError("root Git HEAD/index/ref/config metadata mutated")
        else:
            if not isinstance(expected_commit, str):
                raise PilotBlockedError("changed clone Git commit authority is missing")
            ProductGitAuthority.verify(
                changed, changed_git_seal, expected_commit=expected_commit,
            )
        before, _ = cls._inventory(baseline)
        after, after_bytes = cls._inventory(changed, include_bytes=True)
        changed_paths = sorted(
            path for path in set(before) | set(after) if before.get(path) != after.get(path)
        )
        denied = [path for path in changed_paths if not cls._path_allowed(path, allowed)]
        if denied:
            raise PilotBlockedError("product delta changed an out-of-scope path: " + denied[0])
        operations: list[Dict[str, Any]] = []
        for path in sorted(
                (path for path in before if path not in after or before[path].get(
                    "type") != after.get(path, {}).get("type")),
                key=lambda value: (-value.count("/"), value)):
            operations.append({"operation": "delete", "path": path})
        for path in sorted(
                (path for path in after if before.get(path) != after[path]),
                key=lambda value: (value.count("/"), value)):
            record = dict(after[path])
            operation = {"operation": "upsert", **record}
            if record["type"] == "file":
                operation["content_base64"] = base64.b64encode(after_bytes[path]).decode(
                    "ascii"
                )
            operations.append(operation)
        return {
            "schema": cls.SCHEMA,
            "allowed_paths": list(allowed),
            "root_git_authority": baseline_git,
            "baseline_tree_hash": cls._inventory_hash(before),
            "changed_tree_hash": cls._inventory_hash(after),
            "operations": operations,
        }

    @classmethod
    def _destination_path(cls, root: Path, relative: str) -> Path:
        normalized = cls._normalize_relative(relative)
        path = root.joinpath(*normalized.split("/"))
        current = root
        for part in normalized.split("/")[:-1]:
            current = current / part
            if current.is_symlink():
                raise PilotBlockedError("delta destination parent is a symlink")
        return path

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    @classmethod
    def replay(cls, delta: Any, destination: Any, *,
               allowed_paths: Iterable[str]) -> Dict[str, Any]:
        if not isinstance(delta, dict) or delta.get("schema") != cls.SCHEMA:
            raise PilotBlockedError("product delta schema is invalid")
        allowed = cls._allowed_paths(allowed_paths)
        if delta.get("allowed_paths") != list(allowed):
            raise PilotBlockedError("product delta replay allowlist changed")
        root = Path(destination)
        if delta.get("root_git_authority") != cls._root_git_authority(root):
            raise PilotBlockedError("product delta replay root Git authority differs")
        if cls.tree_hash(root) != delta.get("baseline_tree_hash"):
            raise PilotBlockedError("product delta replay baseline tree hash differs")
        operations = delta.get("operations")
        if not isinstance(operations, list):
            raise PilotBlockedError("product delta operations are invalid")
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("operation") not in {
                    "delete", "upsert"}:
                raise PilotBlockedError("product delta operation is invalid")
            relative = cls._normalize_relative(operation.get("path"))
            if not cls._path_allowed(relative, allowed):
                raise PilotBlockedError("product delta replay path is outside scope")
            path = cls._destination_path(root, relative)
            if operation["operation"] == "delete":
                if not os.path.lexists(path):
                    raise PilotBlockedError("product delta deletion target is missing")
                cls._remove_path(path)
                continue
            entry_type = operation.get("type")
            mode = operation.get("mode")
            if type(mode) is not int or mode < 0 or mode > 0o7777:
                raise PilotBlockedError("product delta mode is invalid")
            path.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(path):
                cls._remove_path(path)
            if entry_type == "directory":
                path.mkdir()
                path.chmod(mode)
            elif entry_type == "symlink":
                target = operation.get("target")
                if not isinstance(target, str):
                    raise PilotBlockedError("product delta symlink target is invalid")
                path.symlink_to(target)
            elif entry_type == "file":
                try:
                    content = base64.b64decode(
                        operation.get("content_base64", ""), validate=True,
                    )
                except (ValueError, TypeError) as exc:
                    raise PilotBlockedError("product delta file bytes are invalid") from exc
                if hashlib.sha256(content).hexdigest() != operation.get("sha256") or len(
                        content) != operation.get("size"):
                    raise PilotBlockedError("product delta file content hash differs")
                path.write_bytes(content)
                path.chmod(mode)
            else:
                raise PilotBlockedError("product delta upsert type is invalid")
        final_hash = cls.tree_hash(root)
        if final_hash != delta.get("changed_tree_hash"):
            raise PilotBlockedError("product delta replay tree hash differs")
        return {
            "schema": "product_tree_delta_replay_receipt.v1",
            "status": "PASS",
            "tree_hash": final_hash,
            "operation_count": len(operations),
        }


def _pinned_openssl_facts() -> Dict[str, Any]:
    path = PINNED_OPENSSL_PATH
    if path.is_symlink() or os.path.realpath(path) != str(path):
        raise PilotBlockedError("OpenSSL executable path is not the exact canonical pin")
    try:
        identity = path.lstat()
        content = path.read_bytes()
    except OSError as exc:
        raise PilotBlockedError("OpenSSL executable is unavailable") from exc
    digest = hashlib.sha256(content).hexdigest()
    if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1 or stat.S_IMODE(
            identity.st_mode) != 0o555 or identity.st_size != 893392:
        raise PilotBlockedError("OpenSSL executable metadata differs from the pin")
    if digest != PINNED_OPENSSL_SHA256:
        raise PilotBlockedError("OpenSSL executable hash differs from the pin")
    version_argv = [str(path), "version"]
    process = subprocess.run(
        version_argv, env={"LANG": "C", "PATH": "/usr/bin:/bin"},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, shell=False, timeout=30, check=False,
    )
    rendered = process.stdout.strip()
    if process.returncode != 0 or rendered != PINNED_OPENSSL_VERSION:
        raise PilotBlockedError("OpenSSL executable version differs from the pin")
    return {
        "path": str(path), "sha256": digest, "version": rendered,
        "mode": stat.S_IMODE(identity.st_mode), "nlink": identity.st_nlink,
        "size": identity.st_size,
        "version_argv_sha256": _canonical_hash(version_argv),
    }


class ProductVerifierAuthority:
    """Pinned OpenSSL 3.6.2 Ed25519 authority for post-arm receipts."""

    DOMAIN = b"loop-team/product-verifier-receipt/v1\x00"

    def __init__(self, *, openssl_path: Any, pinned_openssl_sha256: str,
                 private_key_path: Any, public_key_path: Any,
                 pinned_public_key_sha256: str) -> None:
        self.openssl_path = Path(openssl_path)
        self.pinned_openssl_sha256 = pinned_openssl_sha256
        self.private_key_path = Path(private_key_path)
        self.public_key_path = Path(public_key_path)
        self.pinned_public_key_sha256 = pinned_public_key_sha256
        self._openssl_facts = self._validate_openssl()
        self._validate_keys()

    @staticmethod
    def _minimal_env() -> Dict[str, str]:
        return {"LANG": "C", "PATH": "/usr/bin:/bin"}

    def _validate_openssl(self) -> Dict[str, Any]:
        if self.openssl_path != PINNED_OPENSSL_PATH or self.pinned_openssl_sha256 != PINNED_OPENSSL_SHA256:
            raise PilotBlockedError("OpenSSL executable path is not the exact canonical pin")
        return _pinned_openssl_facts()

    def _validate_keys(self) -> None:
        for label, path in (
                ("private", self.private_key_path), ("public", self.public_key_path)):
            try:
                identity = path.lstat()
            except OSError as exc:
                raise PilotBlockedError("%s Ed25519 key is unavailable" % label) from exc
            if path.is_symlink() or not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
                raise PilotBlockedError("%s Ed25519 key metadata is invalid" % label)
        actual_public_hash = hashlib.sha256(self.public_key_path.read_bytes()).hexdigest()
        if not _is_sha256(self.pinned_public_key_sha256) or actual_public_hash != self.pinned_public_key_sha256:
            raise PilotBlockedError("public Ed25519 key fingerprint differs from the pin")

    def _run_openssl(self, argv: list[str], *, expect_success: bool = True
                     ) -> subprocess.CompletedProcess[bytes]:
        if not argv or argv[0] != str(PINNED_OPENSSL_PATH):
            raise PilotBlockedError("OpenSSL command does not use the exact pinned executable")
        before = self._validate_openssl()
        process = subprocess.run(
            argv, env=self._minimal_env(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            timeout=30, check=False,
        )
        after = self._validate_openssl()
        if before != after:
            raise PilotBlockedError("OpenSSL executable changed during signature operation")
        if expect_success and process.returncode != 0:
            raise PilotBlockedError("OpenSSL Ed25519 operation failed")
        return process

    @classmethod
    def _signed_bytes(cls, receipt: Dict[str, Any]) -> bytes:
        payload = dict(receipt)
        payload.pop("signature", None)
        return cls.DOMAIN + _canonical_bytes(payload)

    def sign_and_verify(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict) or not payload:
            raise PilotBlockedError("product verifier payload is invalid")
        self._validate_keys()
        with tempfile.TemporaryDirectory(
                prefix=".product-verifier-sign-", dir=str(self.private_key_path.parent)) as temp:
            message_path = Path(temp) / "receipt.bin"
            signature_path = Path(temp) / "receipt.sig"
            sign_argv = [
                str(PINNED_OPENSSL_PATH), "pkeyutl", "-sign", "-rawin",
                "-inkey", str(self.private_key_path), "-in", str(message_path),
                "-out", str(signature_path),
            ]
            verify_template = [
                str(PINNED_OPENSSL_PATH), "pkeyutl", "-verify", "-rawin",
                "-pubin", "-inkey", str(self.public_key_path),
                "-in", "<CANONICAL_RECEIPT>", "-sigfile", "<SIGNATURE>",
            ]
            operation_pin = self._validate_openssl()
            receipt = {
                **json.loads(json.dumps(payload)),
                "receipt_schema": "product_verifier_receipt.v1",
                "signature_algorithm": "Ed25519",
                "signer_key_id": self.pinned_public_key_sha256,
                "openssl": dict(self._openssl_facts),
                "sign_argv_sha256": _canonical_hash(sign_argv),
                "verify_argv_template_sha256": _canonical_hash(verify_template),
                "openssl_operation_pins": {
                    "sign": {
                        "pre": operation_pin, "post": operation_pin,
                        "argv_sha256": _canonical_hash(sign_argv),
                    },
                    "verify": {
                        "pre": operation_pin, "post": operation_pin,
                        "argv_template_sha256": _canonical_hash(verify_template),
                    },
                },
            }
            message_path.write_bytes(self._signed_bytes(receipt))
            self._run_openssl(sign_argv)
            if self._validate_openssl() != operation_pin:
                raise PilotBlockedError("OpenSSL pin changed across receipt signing")
            receipt["signature"] = base64.b64encode(signature_path.read_bytes()).decode("ascii")
        if self.verify_receipt(receipt) is not True:
            raise PilotBlockedError("new product verifier receipt did not verify")
        return receipt

    def verify_receipt(self, receipt: Dict[str, Any]) -> bool:
        if not isinstance(receipt, dict) or receipt.get(
                "receipt_schema") != "product_verifier_receipt.v1" or receipt.get(
                    "signature_algorithm") != "Ed25519" or receipt.get(
                        "signer_key_id") != self.pinned_public_key_sha256 or receipt.get(
                            "openssl") != self._openssl_facts:
            raise PilotBlockedError("product verifier receipt signer/key metadata is invalid")
        operation_pins = receipt.get("openssl_operation_pins")
        current_pin = self._validate_openssl()
        if not isinstance(operation_pins, dict) or operation_pins.get(
                "sign", {}).get("pre") != current_pin or operation_pins.get(
                    "sign", {}).get("post") != current_pin or operation_pins.get(
                        "verify", {}).get("pre") != current_pin or operation_pins.get(
                            "verify", {}).get("post") != current_pin:
            raise PilotBlockedError("product verifier receipt OpenSSL operation pins are invalid")
        self._validate_keys()
        try:
            signature = base64.b64decode(receipt.get("signature", ""), validate=True)
        except Exception as exc:
            raise PilotBlockedError("product verifier receipt signature is invalid") from exc
        if not signature:
            raise PilotBlockedError("product verifier receipt signature is empty")
        with tempfile.TemporaryDirectory(
                prefix=".product-verifier-verify-", dir=str(self.public_key_path.parent)) as temp:
            message_path = Path(temp) / "receipt.bin"
            signature_path = Path(temp) / "receipt.sig"
            message_path.write_bytes(self._signed_bytes(receipt))
            signature_path.write_bytes(signature)
            verify_argv = [
                str(PINNED_OPENSSL_PATH), "pkeyutl", "-verify", "-rawin",
                "-pubin", "-inkey", str(self.public_key_path),
                "-in", str(message_path), "-sigfile", str(signature_path),
            ]
            process = self._run_openssl(verify_argv, expect_success=False)
        if self._validate_openssl() != current_pin:
            raise PilotBlockedError("OpenSSL pin changed across receipt verification")
        if process.returncode != 0:
            raise PilotBlockedError("product verifier receipt signature/key pin is invalid")
        return True


class ProductPostArmVerifier:
    """Validate a hidden oracle result against an immutable replayed product tree."""

    def __init__(self, *, authority: Optional[ProductVerifierAuthority] = None) -> None:
        self.authority = authority

    def verify(self, *, case_id: str, clone_path: Any, sealed_tree_hash: str,
               stdout: str, exit_code: int, **context: Any) -> Dict[str, Any]:
        before_hash = ProductTreeDelta.tree_hash(clone_path)
        before_git = ProductTreeDelta._root_git_authority(clone_path)
        if not _is_sha256(sealed_tree_hash) or before_hash != sealed_tree_hash:
            raise PilotBlockedError("post-arm product tree mutated after its seal/hash")
        if case_id == PREPARATION_CASES[2]:
            parsed = ProductionProductPreprobeRunner.parse_p3_doctor_output(
                stdout, exit_code,
            )
            if parsed["status"] == "INVALID_ARGUMENTS":
                raise PilotBlockedError(
                    "P3 post-arm oracle returned INVALID_ARGUMENTS at exit 2"
                )
            failed = [key for key in P3_PREDICATES if parsed[key] is False]
            result = {
                "schema": "product_post_arm_verification.v1",
                "case_id": case_id,
                "status": parsed["status"],
                "exit_code": exit_code,
                "ready": parsed["ready"],
                "failed_predicates": failed,
                "quality_verdict": "PASS",
            }
        elif case_id == PREPARATION_CASES[0]:
            parsed = ProductionProductPreprobeRunner._parse_p1_summary(
                stdout, exit_code, require_target=False,
            )
            baseline_ids = context.get("baseline_finding_ids")
            if not isinstance(baseline_ids, list) or baseline_ids.count(
                    "tax_package_mock_backed") != 1:
                raise PilotBlockedError("P1 sealed baseline finding IDs are invalid")
            expected = [
                finding for finding in baseline_ids
                if finding != "tax_package_mock_backed"
            ]
            if parsed["finding_ids"] != expected:
                raise PilotBlockedError("P1 post-arm findings do not equal the sealed differential")
            result = {
                "schema": "product_post_arm_verification.v1",
                "case_id": case_id,
                "status": "PASS",
                "exit_code": exit_code,
                "failed_predicates": [],
                "quality_verdict": "PASS",
            }
        elif case_id == PREPARATION_CASES[1]:
            payload = ProductionProductPreprobeRunner._strict_json_object(
                stdout, "P2 hidden handleSend oracle",
            )
            expected = {
                "schema": "p2-handle-send-oracle.v1",
                "status": "PASS",
                "handle_send_calls_ask_taxahead": True,
                "filing_unit_input": True,
                "loading_state": True,
                "answer_state": True,
                "evidence_state": True,
                "error_state": True,
            }
            behavioral = payload.get("behavioral_runs")
            factory_contract = payload.get("factory_contract")
            exact_runs = {
                "success": {
                    "handler_input": "hello", "filing_unit_id": "filing-unit-42",
                    "transitions": [
                        "loading:true", "answer:Grounded answer",
                        "evidence:evidence-1", "loading:false",
                    ],
                },
                "error": {
                    "handler_input": "hello", "filing_unit_id": "filing-unit-42",
                    "transitions": [
                        "loading:true", "error:synthetic failure", "loading:false",
                    ],
                },
            }
            if exit_code != 0 or any(payload.get(key) != value for key, value in expected.items()) or not isinstance(
                    behavioral, dict) or behavioral != exact_runs or factory_contract != {
                        "factory_symbol": "createAskTaxaheadHandler",
                        "handler_parameter": "text:string",
                        "handler_return": "Promise<void>",
                        "feed_composer_direct_assignment": True,
                    } or payload.get("ast_parser") != "bun-typescript-transpiler":
                raise PilotBlockedError("P2 hidden handleSend oracle did not pass exactly")
            result = {
                "schema": "product_post_arm_verification.v1",
                "case_id": case_id,
                "status": "PASS",
                "exit_code": 0,
                "failed_predicates": [],
                "quality_verdict": "PASS",
            }
        else:
            raise PilotBlockedError("unknown product post-arm case")
        after_hash = ProductTreeDelta.tree_hash(clone_path)
        if after_hash != before_hash:
            raise PilotBlockedError("hidden oracle mutated the replayed product tree")
        after_git = ProductTreeDelta._root_git_authority(clone_path)
        if after_git != before_git:
            raise PilotBlockedError("hidden oracle mutated root Git HEAD/index/ref/config metadata")
        result.update({
            "product_tree_hash_before": before_hash,
            "product_tree_hash_after": after_hash,
            "root_git_authority_before": before_git,
            "root_git_authority_after": after_git,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        })
        if self.authority is not None:
            signed = self.authority.sign_and_verify(result)
            self.authority.verify_receipt(signed)
            return signed
        return result


def create_product_verifier_authority(root_value: Any) -> tuple[
        ProductVerifierAuthority, Dict[str, Any]]:
    """Generate one controller-owned Ed25519 keypair with the exact pinned binary."""
    root = Path(root_value)
    if root.exists() or root.is_symlink():
        raise PilotBlockedError("product verifier authority root already exists")
    openssl_pre_keygen = _pinned_openssl_facts()
    root.mkdir(parents=True, mode=0o700)
    private_key = root / "private.pem"
    public_key = root / "public.pem"
    keygen_argv = [
        str(PINNED_OPENSSL_PATH), "genpkey", "-algorithm", "Ed25519",
        "-out", str(private_key),
    ]
    pubout_argv = [
        str(PINNED_OPENSSL_PATH), "pkey", "-in", str(private_key),
        "-pubout", "-out", str(public_key),
    ]
    process = subprocess.run(
        keygen_argv, env=ProductVerifierAuthority._minimal_env(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False, timeout=30, check=False,
    )
    if process.returncode != 0:
        raise PilotBlockedError("controller Ed25519 private-key generation failed")
    openssl_post_genpkey = _pinned_openssl_facts()
    openssl_pre_pubout = _pinned_openssl_facts()
    process = subprocess.run(
        pubout_argv, env=ProductVerifierAuthority._minimal_env(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False, timeout=30, check=False,
    )
    if process.returncode != 0:
        raise PilotBlockedError("controller Ed25519 public-key extraction failed")
    openssl_post_pubout = _pinned_openssl_facts()
    if len({_canonical_hash(facts) for facts in (
            openssl_pre_keygen, openssl_post_genpkey,
            openssl_pre_pubout, openssl_post_pubout)}) != 1:
        raise PilotBlockedError("OpenSSL pin changed during key generation or public extraction")
    private_key.chmod(0o400)
    public_key.chmod(0o444)
    public_hash = hashlib.sha256(public_key.read_bytes()).hexdigest()
    authority = ProductVerifierAuthority(
        openssl_path=PINNED_OPENSSL_PATH,
        pinned_openssl_sha256=PINNED_OPENSSL_SHA256,
        private_key_path=private_key,
        public_key_path=public_key,
        pinned_public_key_sha256=public_hash,
    )
    receipt = {
        "schema": "product_verifier_key_generation.v1",
        "algorithm": "Ed25519",
        "openssl": dict(authority._openssl_facts),
        "openssl_pre_keygen": openssl_pre_keygen,
        "openssl_post_keygen": openssl_post_pubout,
        "openssl_keygen_phases": {
            "pre_genpkey": openssl_pre_keygen,
            "post_genpkey": openssl_post_genpkey,
            "pre_pubout": openssl_pre_pubout,
            "post_pubout": openssl_post_pubout,
        },
        "keygen_argv_sha256": _canonical_hash(keygen_argv),
        "pubout_argv_sha256": _canonical_hash(pubout_argv),
        "public_key_sha256": public_hash,
        "private_key_mode": stat.S_IMODE(private_key.lstat().st_mode),
        "public_key_mode": stat.S_IMODE(public_key.lstat().st_mode),
    }
    return authority, receipt


class ProductionPostArmController:
    """Replay a coder delta into a fresh clone, run hidden oracles, and sign evidence."""

    def __init__(self, *, controller_root: Any,
                 authority: ProductVerifierAuthority,
                 key_generation_receipt: Dict[str, Any]) -> None:
        self.controller_root = Path(controller_root)
        self.authority = authority
        self.key_generation_receipt = key_generation_receipt
        if self.controller_root.exists() or self.controller_root.is_symlink():
            raise PilotBlockedError("post-arm controller root already exists")
        self.controller_root.mkdir(parents=True, mode=0o700)
        self.oracle_generator = OracleGeneratorAuthority.for_p2(
            artifact_root=self.controller_root / "p2-oracle-generator",
        )
        self.oracle_generator_seal = self.oracle_generator.seal()
        self._p2_oracle_materializations: list[Dict[str, Any]] = []

    @staticmethod
    def _git(argv: list[str], *, cwd: Optional[Path] = None) -> str:
        process = subprocess.run(
            argv, cwd=str(cwd) if cwd is not None else None,
            env={"LANG": "C", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, shell=False, timeout=120, check=False,
        )
        if process.returncode != 0:
            raise PilotBlockedError("post-arm detached verifier clone failed")
        return process.stdout.strip()

    def _fresh_clone(self, packet: Dict[str, Any], destination: Path) -> Dict[str, Any]:
        source_root = packet.get("source_root")
        source_sha = packet.get("source_sha")
        if not isinstance(source_root, str) or not re.fullmatch(
                r"[0-9a-f]{40}", source_sha or ""):
            raise PilotBlockedError("post-arm packet source authority is invalid")
        destination.parent.mkdir(parents=True, exist_ok=False)
        clone_argv = [
            "git", "clone", "--no-hardlinks", "--no-checkout",
            source_root, str(destination),
        ]
        self._git(clone_argv)
        checkout_argv = ["git", "checkout", "--detach", source_sha]
        self._git(checkout_argv, cwd=destination)
        head = self._git(["git", "rev-parse", "HEAD"], cwd=destination)
        status = self._git(["git", "status", "--short"], cwd=destination)
        if head != source_sha or status:
            raise PilotBlockedError("post-arm verifier clone is not clean at the source SHA")
        return {
            "clone_argv": clone_argv,
            "checkout_argv": checkout_argv,
            "source_sha": source_sha,
            "head": head,
            "clean": True,
        }

    @staticmethod
    def _oracle_spec(case_id: str, oracle_root: Path
                     ) -> tuple[list[str], Dict[str, str], tuple[int, ...], Optional[str]]:
        if case_id == PREPARATION_CASES[0]:
            return ["npm", "run", "smoke"], {"REQUIRE_REAL_BACKEND": "1"}, (1,), None
        if case_id == PREPARATION_CASES[2]:
            return list(P3_TARGET_ARGV), {}, (0, 2, 3), None
        if case_id == PREPARATION_CASES[1]:
            return [str(PINNED_BUN_PATH), "<CONTROLLER_ORACLE>"], {}, (0, 1), None
        raise PilotBlockedError("unknown post-arm product case")

    def verify_after_coder(self, *, packet: Dict[str, Any], result: Any) -> Dict[str, Any]:
        role = packet.get("task_identity", {}).get("role")
        if role not in {"incumbent_coder", "challenger_coder"}:
            raise PilotBlockedError("post-arm verification received a non-coder packet")
        case_id = packet.get("preparation_case_id")
        ordinal = packet.get("task_identity", {}).get("ordinal")
        if case_id not in PREPARATION_CASES or type(ordinal) is not int:
            raise PilotBlockedError("post-arm coder case identity is invalid")
        verification_root = self.controller_root / ("%02d-%s" % (ordinal, case_id))
        verification_root.mkdir(parents=False, exist_ok=False)
        verifier_clone = verification_root / "repo"
        clone_receipt = self._fresh_clone(packet, verifier_clone)
        verifier_git_authority = ProductGitAuthority.capture(
            verifier_clone, expected_commit=packet["source_sha"],
        )
        baseline_hash = ProductTreeDelta.tree_hash(verifier_clone)
        if baseline_hash != packet.get("baseline_product_tree_hash"):
            raise PilotBlockedError("fresh verifier baseline differs from the sealed product tree")
        allowed_paths = packet.get("allowed_patch_paths")
        delta = ProductTreeDelta.capture(
            verifier_clone, packet.get("cwd"), allowed_paths=allowed_paths,
            changed_git_seal=packet.get("product_git_authority"),
            expected_commit=packet.get("source_sha"),
        )
        delta_path = _AtomicPreparationWriter().write_json(
            verification_root / "product_tree_delta.v1.json", delta,
        )
        replay_receipt = ProductTreeDelta.replay(
            delta, verifier_clone, allowed_paths=allowed_paths,
        )
        sealed_tree_hash = ProductTreeDelta.tree_hash(verifier_clone)
        if sealed_tree_hash != delta["changed_tree_hash"]:
            raise PilotBlockedError("replayed verifier tree differs from the coder tree")
        oracle_root = verification_root / "oracle"
        oracle_root.mkdir(parents=False, exist_ok=False)
        output_root = verification_root / "oracle-output"
        argv, environment, expected_exits, oracle_sha256 = self._oracle_spec(
            case_id, oracle_root,
        )
        runtime_snapshot = None
        runtime_snapshot_path = None
        runtime_kwargs = None
        oracle_materialization = None
        p3_matrix = None
        if case_id == PREPARATION_CASES[1]:
            runtime_snapshot_path = verification_root / "runtime-snapshot.v1.json"
            source_snapshot_root = Path(packet["source_root"])
            installed_dependency_root = (
                source_snapshot_root / "installed-dependencies" / "node_modules"
            )
            if not installed_dependency_root.is_dir():
                installed_dependency_root = source_snapshot_root / "node_modules"
            runtime_kwargs = {
                "project_root": verifier_clone,
                "source_snapshot_root": source_snapshot_root,
                "installed_dependency_root": installed_dependency_root,
                "snapshot_path": runtime_snapshot_path,
            }
            runtime_snapshot = ProductRuntimeSnapshot().capture(**runtime_kwargs)
            runtime_layer = verification_root / "runtime-layer"
            runtime_layer.mkdir(mode=0o700)
            (runtime_layer / "node_modules").symlink_to(
                installed_dependency_root, target_is_directory=True,
            )
            runtime_layer.chmod(0o500)
            cleanup_receipt = result.get("cleanup_receipt") if isinstance(
                result, dict) else getattr(result, "cleanup_receipt", None)
            cleanup_finished_at_ns = cleanup_receipt.get(
                "finished_at_ns") if isinstance(cleanup_receipt, dict) else None
            if type(cleanup_finished_at_ns) is not int:
                raise PilotBlockedError(
                    "P2 oracle materialization requires coder cleanup timestamp evidence"
                )
            oracle_materialization = self.oracle_generator.materialize(
                arm_id="%s-%02d" % (role, ordinal),
                destination=oracle_root / "controller-hidden-oracle.mjs",
                coder_cleanup_finished_at_ns=cleanup_finished_at_ns,
            )
            self._p2_oracle_materializations.append(oracle_materialization)
            if len(self._p2_oracle_materializations) >= 2:
                self.oracle_generator.validate_arm_receipts(
                    self._p2_oracle_materializations,
                )
            oracle_bytes = Path(oracle_materialization["oracle_path"]).read_bytes()
            oracle_sha256 = oracle_materialization["oracle_sha256"]
            concrete_argv = [
                str(output_root / "controller-hidden-oracle.mjs")
                if token == "<CONTROLLER_ORACLE>" else token for token in argv
            ]
            containment = ProductOracleSandbox().run(
                clone_path=verifier_clone, artifact_dir=output_root,
                fake_home_root=verification_root / "fake-oracle-home",
                oracle_argv=concrete_argv,
                oracle_bytes=oracle_bytes,
            )
            process = subprocess.CompletedProcess(
                concrete_argv, containment["oracle"]["exit_code"],
                stdout=containment["oracle"]["stdout"],
                stderr=containment["oracle"]["stderr"],
            )
            argv = concrete_argv
        elif case_id == PREPARATION_CASES[2]:
            p3_matrix = ProductP3OracleMatrix().run(
                clone_path=verifier_clone, artifact_dir=output_root,
                argv=list(P3_TARGET_ARGV), invalid_argument="--bogus",
                injected_environment={
                    "P3_GENERATED_PRISMA_CLIENT": "1",
                    "DATABASE_URL": "postgresql://synthetic.invalid/pilot",
                    "P3_APP_ENDPOINT": "http://synthetic.invalid/app",
                    "P3_ORGANIZATION_TOKEN": "synthetic-product-oracle-token",
                },
            )
            injected = p3_matrix["run_evidence"]["injected_ready"]
            process = subprocess.CompletedProcess(
                argv, injected["exit_code"],
                stdout=Path(injected["stdout_path"]).read_text(encoding="utf-8"),
                stderr=Path(injected["stderr_path"]).read_text(encoding="utf-8"),
            )
            containment = p3_matrix
        else:
            output_root.mkdir(parents=False, exist_ok=False)
            process, containment = ProductionProductPreprobeRunner()._run(
                argv=argv, clone_path=verifier_clone, artifact_dir=output_root,
                environment=environment, expected_exit_codes=expected_exits,
            )
        context: Dict[str, Any] = {}
        if case_id == PREPARATION_CASES[0]:
            context["baseline_finding_ids"] = packet.get(
                "preprobe_receipt", {}
            ).get("baseline_finding_ids")
        verification = ProductPostArmVerifier().verify(
            case_id=case_id,
            clone_path=verifier_clone,
            sealed_tree_hash=sealed_tree_hash,
            stdout=process.stdout,
            exit_code=process.returncode,
            **context,
        )
        if runtime_kwargs is not None:
            ProductRuntimeSnapshot().verify(**runtime_kwargs)
        ProductGitAuthority.verify(
            verifier_clone, verifier_git_authority,
            expected_commit=packet["source_sha"],
        )
        receipt_id = "post-arm-%02d" % ordinal
        opaque_artifact_id = "coder-%02d" % ordinal
        payload = {
            **verification,
            "opaque_artifact_id": opaque_artifact_id,
            "receipt_id": receipt_id,
            "role": role,
            "source_sha": packet["source_sha"],
            "packet_hash": packet.get("packet_hash"),
            "coder_result_hash": _canonical_hash(result),
            "delta_sha256": hashlib.sha256(delta_path.read_bytes()).hexdigest(),
            "delta_replay": replay_receipt,
            "clone_provenance": clone_receipt,
            "oracle_argv": argv,
            "oracle_environment_keys": sorted(environment),
            "oracle_sha256": oracle_sha256,
            "oracle_generator_authority": self.oracle_generator_seal,
            "oracle_materialization": oracle_materialization,
            "containment_receipt": containment,
            "runtime_snapshot": runtime_snapshot,
            "p3_oracle_matrix": p3_matrix,
            "key_generation_receipt": self.key_generation_receipt,
            "promotion_eligible": False,
        }
        signed_receipt = self.authority.sign_and_verify(payload)
        self.authority.verify_receipt(signed_receipt)
        receipt_path = _AtomicPreparationWriter().write_json(
            verification_root / "signed-post-arm-receipt.v1.json", signed_receipt,
        )
        return {
            "schema": "controller_post_arm_receipt.v1",
            "status": "PASS",
            "signed": True,
            "case_id": case_id,
            "role": role,
            "opaque_artifact_id": opaque_artifact_id,
            "receipt_id": receipt_id,
            "receipt_path": str(receipt_path),
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "promotion_eligible": False,
        }


class ProductionCaseMaterialBuilder:
    """Build six exact case materials from reproduced clone facts."""

    @staticmethod
    def _record(**values: Any) -> bytes:
        return _canonical_bytes(values) + b"\n"

    @staticmethod
    def _validate_source_files(clone: Path, preprobe: Dict[str, Any]) -> Dict[str, str]:
        supplied = preprobe.get("sealed_source_files", {})
        if not isinstance(supplied, dict):
            raise PilotBlockedError("preprobe sealed source-file hashes are invalid")
        actual = {}
        for relative, expected_hash in supplied.items():
            if not isinstance(relative, str) or not _is_sha256(expected_hash):
                raise PilotBlockedError("preprobe sealed source-file hash is invalid")
            path = clone / relative
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise PilotBlockedError("sealed source file is unavailable") from exc
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != expected_hash:
                raise PilotBlockedError("sealed source-file content hash changed")
            actual[relative] = actual_hash
        return actual

    def build(self, *, slot: Dict[str, Any], case_manifest: Dict[str, Any],
              preprobe_receipt: Dict[str, Any], clone_path: Any) -> Dict[str, bytes]:
        case_id = slot.get("case_id")
        clone = Path(clone_path)
        if case_id == "smoke":
            prompt = (
                "Return exactly CODEX_SMOKE_OK. Do not use tools, run commands, edit files, "
                "or contact external services.\n"
            ).encode("utf-8")
            return {
                "prompt": prompt,
                "plan": self._record(case_id="smoke", action="identity-only local check"),
                "oracle": self._record(exact_output="CODEX_SMOKE_OK", tools=False, edits=False),
                "test": self._record(final_message_bytes="CODEX_SMOKE_OK"),
                "dependency": self._record(sandbox="read-only", approval="never"),
                "preprobe": self._record(provider_process_starts=0, status="PASS"),
            }
        if case_id not in PREPARATION_CASES or case_manifest.get(
                "schema") != "case_manifest.v1" or case_manifest.get(
                    "case_id") != case_id or not isinstance(preprobe_receipt, dict) or preprobe_receipt.get(
                        "status") != "PASS":
            raise PilotBlockedError("case material inputs are incomplete")
        manifest_preprobe = case_manifest.get("preprobe")
        if manifest_preprobe is not None and manifest_preprobe != preprobe_receipt:
            raise PilotBlockedError("case manifest preprobe does not match reproduced facts")
        source_path = case_manifest.get("source_path")
        source_sha = case_manifest.get("source_sha")
        if not isinstance(source_path, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha or ""):
            raise PilotBlockedError("case source path or approved commit is invalid")
        sealed_source_files = self._validate_source_files(clone, preprobe_receipt)
        common = {
            "case_id": case_id,
            "role": slot.get("role"),
            "source_path": source_path,
            "source_sha": source_sha,
            "promotion_boundary": PROMOTION_BOUNDARY,
        }
        if slot.get("role") == "planner":
            common["planner_output_contract"] = {
                "schema": "product_planner_output.v1", "status": "PLAN_PASS",
                "required_fields": [
                    "schema", "status", "case_id", "allowed_paths", "steps", "checks",
                ],
                "format": "one canonical JSON object followed by LF",
                "edits": False,
            }
        if case_id == PREPARATION_CASES[0]:
            baseline_path = clone / "fixtures" / "p1-baseline.json"
            if baseline_path.is_file():
                sealed_source_files.setdefault(
                    "fixtures/p1-baseline.json",
                    hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                )
            argv = preprobe_receipt.get("argv")
            environment = preprobe_receipt.get("environment")
            finding_ids = preprobe_receipt.get("baseline_finding_ids")
            if argv != ["npm", "run", "smoke"] or environment != {
                    "REQUIRE_REAL_BACKEND": "1"} or not isinstance(finding_ids, list):
                raise PilotBlockedError("P1 live-data baseline contract is invalid")
            return {
                "prompt": self._record(**common, objective="app.tax-package live-data repair"),
                "plan": self._record(**common, argv=argv, environment=environment),
                "oracle": self._record(
                    **common, targeted_finding="tax_package_mock_backed",
                    baseline_finding_ids=finding_ids,
                    acceptance="remove targeted finding and preserve unrelated baseline findings",
                ),
                "test": self._record(
                    **common, exact_argv_json=_canonical_json(argv),
                    required_environment="REQUIRE_REAL_BACKEND",
                ),
                "dependency": self._record(
                    **common, route="app.tax-package", sealed_source_files=sealed_source_files,
                ),
                "preprobe": self._record(**common, reproduced=preprobe_receipt),
            }
        if case_id == PREPARATION_CASES[1]:
            site = preprobe_receipt.get("active_call_site")
            span = site.get("span") if isinstance(site, dict) else None
            relative_path = site.get("relative_path") if isinstance(site, dict) else None
            if not isinstance(relative_path, str) or not isinstance(span, dict):
                raise PilotBlockedError("P2 active call site is missing")
            try:
                content = (clone / relative_path).read_bytes()
                lines = content.decode("utf-8").splitlines()
                start_line = span["start_line"]
                end_line = span["end_line"]
            except (OSError, UnicodeError, KeyError, TypeError) as exc:
                raise PilotBlockedError("P2 active call-site content is unavailable") from exc
            actual_hash = hashlib.sha256(content).hexdigest()
            valid_bounds = (
                type(start_line) is int and type(end_line) is int
                and 1 <= start_line <= end_line <= len(lines)
            )
            actual_span = (
                "\n".join(lines[start_line - 1:end_line]) if valid_bounds else ""
            )
            legacy_transport = (
                valid_bounds and start_line == end_line
                and span.get("text") == lines[start_line - 1]
                and "askTaxaheadTransport" in span.get("text", "")
            )
            current_handle_send = (
                valid_bounds and end_line > start_line
                and site.get("symbol") == "handleSend"
                and span.get("text") == actual_span
                and span.get("text_sha256") == hashlib.sha256(
                    actual_span.encode("utf-8")
                ).hexdigest()
                and "const handleSend =" in actual_span
            )
            if site.get("content_sha256") != actual_hash or not (
                    legacy_transport or current_handle_send):
                raise PilotBlockedError("P2 call site content hash/span does not match clone bytes")
            site_facts = {
                "relative_path": relative_path,
                "symbol": site.get("symbol", "askTaxaheadTransport"),
                "content_sha256": actual_hash,
                "start_line": start_line,
                "end_line": end_line,
                "text": span["text"],
            }
            return {
                "prompt": self._record(
                    **common,
                    objective=(
                        "wire the real handleSend UI seam to askTaxahead"
                        if current_handle_send else "askTaxahead chat transport repair"
                    ),
                ),
                "plan": self._record(**common, active_call_site=site_facts),
                "oracle": self._record(
                    **common, function="askTaxahead", input="filingUnit",
                    active_ui_seam=site_facts["symbol"],
                    states=["loading", "answer", "evidence", "error"],
                ),
                "test": self._record(
                    **common, discovery_argv=preprobe_receipt.get("discovery_argv"),
                    discovery_stdout_sha256=preprobe_receipt.get("discovery_stdout_sha256"),
                ),
                "dependency": self._record(**common, sealed_source_files=sealed_source_files),
                "preprobe": self._record(**common, reproduced=preprobe_receipt),
            }
        baseline_path = clone / "fixtures" / "p3-baseline.json"
        if baseline_path.is_file():
            sealed_source_files.setdefault(
                "fixtures/p3-baseline.json",
                hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
            )
        argv = preprobe_receipt.get("argv")
        baseline = preprobe_receipt.get("baseline")
        is_inventory_baseline = isinstance(baseline, dict) and baseline.get(
            "schema") == "p3-prerequisite-doctor-baseline.v1"
        if is_inventory_baseline:
            valid_contract = (
                argv == ProductionProductPreprobeRunner.p3_baseline_argv()
                and preprobe_receipt.get("baseline_argv") == argv
                and preprobe_receipt.get("target_argv") == P3_TARGET_ARGV
                and all(baseline.get(key) is False for key in (
                    "doctor_script_registered", "doctor_implementation_present",
                    "doctor_test_present",
                ))
                and baseline.get("source_verifier_present") is True
            )
            target_argv = list(P3_TARGET_ARGV)
        else:
            valid_contract = (
                argv == P3_TARGET_ARGV and isinstance(baseline, dict)
                and baseline.get("project_id") == "padsplit-cockpit"
                and baseline.get("alias") == "PMS Cockpit"
                and all(key in baseline for key in P3_PREDICATES)
            )
            target_argv = list(P3_TARGET_ARGV)
        if not valid_contract:
            raise PilotBlockedError("P3 prerequisite-doctor baseline contract is invalid")
        return {
            "prompt": self._record(**common, objective="PMS prerequisite-doctor implementation"),
            "plan": self._record(
                **common, baseline_argv=argv, target_argv=target_argv,
            ),
            "oracle": self._record(
                **common, project_id="padsplit-cockpit", alias="PMS Cockpit",
                schema="pms.prerequisite-doctor.v1",
                statuses={"READY": 0, "INVALID_ARGUMENTS": 2, "NOT_READY": 3},
                predicates=list(P3_PREDICATES), baseline=baseline,
            ),
            "test": self._record(
                **common, command="prerequisite:doctor", exact_argv=target_argv,
            ),
            "dependency": self._record(
                **common, sealed_source_files=sealed_source_files,
                forbidden=["database write", "migration", "seed", "browser", "remediation"],
            ),
            "preprobe": self._record(**common, reproduced=preprobe_receipt),
        }


class CodexPilotPreparer:
    """Prepare immutable pilot inputs without reserving or starting provider work."""

    _RUN_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{2,127}\Z")

    def __init__(self, *, artifact_base: Any, clone_base: Any,
                 source_paths: Dict[str, Any], source_shas: Dict[str, str],
                 test_gate_runner: Any, preflight_factory: Any, git_seam: Any,
                 preprobe_runner: Any, cap_ledger: Any, provider_factory: Any,
                 material_builder: Any = None, test_mode: bool = False) -> None:
        self.artifact_base = Path(artifact_base)
        self.clone_base = Path(clone_base)
        self.source_paths = {name: Path(path) for name, path in source_paths.items()}
        self.source_shas = dict(source_shas)
        self.test_gate_runner = test_gate_runner
        self.preflight_factory = preflight_factory
        self.git_seam = git_seam
        self.preprobe_runner = preprobe_runner
        self.material_builder = (
            ProductionCaseMaterialBuilder() if material_builder is None else material_builder
        )
        self.cap_ledger = cap_ledger
        self.provider_factory = provider_factory
        self.test_mode = test_mode
        self.spec_sha256 = SPEC_SHA256
        if self.clone_base != Path("/private/tmp/codex-product-pilot"):
            raise ValueError("clone root must be /private/tmp/codex-product-pilot")
        if set(self.source_paths) != {"taxahead", "pms"} or set(
                self.source_shas) != {"taxahead", "pms"}:
            raise ValueError("exact TaxAhead and PMS source bindings are required")
        if any(not re.fullmatch(r"[0-9a-f]{40}", sha) for sha in self.source_shas.values()):
            raise ValueError("source SHA must use exact lowercase Git hexadecimal semantics")
        for seam_name, seam in (
            ("test gate", self.test_gate_runner),
            ("preflight factory", self.preflight_factory),
            ("git seam", self.git_seam),
            ("preprobe runner", self.preprobe_runner),
            ("material builder", self.material_builder),
        ):
            if seam is None:
                raise TypeError(seam_name + " is required")
        if not callable(self.preflight_factory) or not callable(self.provider_factory):
            raise TypeError("preflight and provider factories must be callable")

    @staticmethod
    def _source_name(case_id: str) -> str:
        return "pms" if case_id == PREPARATION_CASES[2] else "taxahead"

    @staticmethod
    def _effective_codex_argv(slot: Dict[str, Any], *, final_path: str) -> list[list[str]]:
        argv = [
            "/opt/homebrew/bin/codex", "--ask-for-approval", "never", "exec", "--cd", slot["clone_path"],
            "--model", slot["model"],
            "--sandbox", slot["sandbox"],
            "-c", "model_reasoning_effort=%s" % slot["effort"],
            "--output-last-message", final_path,
        ]
        if slot["role"] == "smoke":
            argv.append("--skip-git-repo-check")
        return [argv]

    @staticmethod
    def _ordered_argv(slot: Dict[str, Any]) -> list[list[str]]:
        case_id = slot["case_id"]
        if case_id == PREPARATION_CASES[0]:
            return [["npm", "run", "smoke"]]
        if case_id == PREPARATION_CASES[2]:
            return [list(P3_TARGET_ARGV)]
        return [[
            "npm", "run", "test", "--", "--run",
            "src/lib/edge-functions.test.ts",
        ]]

    @staticmethod
    def _allowed_patch_paths(case_id: str) -> list[str]:
        if case_id == PREPARATION_CASES[0]:
            return [
                "src/routes/app.tax-package.tsx",
                "src/routes/app.tax-package.test.tsx",
                "src/services",
                "src/lib/edge-functions.ts",
                "src/lib/edge-functions.test.ts",
            ]
        if case_id == PREPARATION_CASES[1]:
            return [
                "src/routes/app.feed.tsx",
                "src/lib/edge-functions.ts",
            ]
        if case_id == PREPARATION_CASES[2]:
            return [
                "package.json",
                "web/scripts/prerequisite-doctor.mjs",
                "web/tests/prerequisite-doctor.test.mjs",
            ]
        return []

    @staticmethod
    def _validate_preprobe(case_id: str, receipt: Any) -> Dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("status") != "PASS":
            detail = receipt.get("failure_code") if isinstance(receipt, dict) else "missing"
            raise PilotBlockedError(
                "preprobe baseline failed or ambiguous for %s: %s" % (case_id, detail)
            )
        containment = receipt.get("containment_receipt")
        if not isinstance(containment, dict) or containment.get("status") != "PASS" or containment.get(
                "network_attempts") != [] or containment.get("filesystem_violations") != []:
            raise PilotBlockedError("preprobe containment failed for " + case_id)
        if case_id == PREPARATION_CASES[0]:
            if not isinstance(receipt.get("baseline_finding_ids"), list) or not receipt[
                    "baseline_finding_ids"]:
                raise PilotBlockedError("preprobe baseline is missing for " + case_id)
        elif case_id == PREPARATION_CASES[1]:
            site = receipt.get("active_call_site")
            span = site.get("span") if isinstance(site, dict) else None
            if not isinstance(site, dict) or not _is_sha256(site.get(
                    "content_sha256")) or not isinstance(span, dict) or type(span.get(
                        "start_line")) is not int or type(span.get("end_line")) is not int or span[
                            "start_line"] < 1 or span["end_line"] < span["start_line"]:
                raise PilotBlockedError("preprobe ambiguous active call site for " + case_id)
        elif not isinstance(receipt.get("baseline"), dict):
            raise PilotBlockedError("preprobe baseline is missing for " + case_id)
        return receipt

    def _validate_clone_provenance(self, provenance: Any, *, slot: Dict[str, Any],
                                   source_name: str) -> Dict[str, Any]:
        expected_sha = self.source_shas[source_name]
        if not isinstance(provenance, dict) or provenance.get(
                "destination") != slot["clone_path"] or provenance.get(
                    "expected_head_sha") != expected_sha or provenance.get(
                        "detached") is not True or provenance.get(
                            "no_hardlinks") is not True:
            raise PilotBlockedError("detached no-hardlink clone provenance is invalid")
        clone_argv = provenance.get("clone_argv")
        if not isinstance(clone_argv, list) or clone_argv[:3] != [
                "git", "clone", "--no-hardlinks"]:
            raise PilotBlockedError("clone did not use the exact no-hardlinks argv")
        source_before = provenance.get("source_before")
        source_after = provenance.get("source_after")
        if not isinstance(source_before, dict) or source_before.get(
                "expected_sha") != expected_sha or source_before.get(
                    "clean") is not True or source_after != source_before:
            raise PilotBlockedError("source repository SHA/clean state changed during preparation")
        if not self.test_mode and (
                source_before.get("approved_commit_exists") is not True
                or source_before.get("approved_commit_reachable") is not True
                or not re.fullmatch(r"[0-9a-f]{40}", source_before.get("head_sha", ""))):
            raise PilotBlockedError("approved commit is missing or unreachable from clean source")
        return {
            **provenance,
            "ordinal": slot["ordinal"],
            "case_id": slot["case_id"],
            "role": slot["role"],
        }

    def _build_packet(self, *, slot: Dict[str, Any], artifact_run: Path,
                      source_root: Path, preprobe: Dict[str, Any],
                      case_manifest: Dict[str, Any],
                      writer: _AtomicPreparationWriter) -> Dict[str, Any]:
        ordinal = slot["ordinal"]
        attempt_root = artifact_run / "attempts" / ("%02d" % ordinal)
        attempt_root.mkdir(parents=True, exist_ok=False)
        final_path = str(attempt_root / "final.txt")
        materials: Dict[str, Dict[str, str]] = {}
        material_contents = self.material_builder.build(
            slot=slot, case_manifest=case_manifest,
            preprobe_receipt=preprobe, clone_path=slot["clone_path"],
        )
        if not isinstance(material_contents, dict) or set(
                material_contents) != REQUIRED_MATERIALS:
            raise PilotBlockedError("case material builder did not return the exact six materials")
        for name, content in material_contents.items():
            if not isinstance(content, bytes) or not content.endswith(b"\n"):
                raise PilotBlockedError("sealed case material must be newline-terminated bytes")
            material_path = artifact_run / "materials" / ("%02d" % ordinal) / (name + ".txt")
            writer.write_bytes(material_path, content)
            materials[name] = {
                "path": str(material_path),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        cwd = Path(slot["clone_path"])
        clone_entries = _preparation_tree_entries(cwd)
        source_entries = _preparation_tree_entries(source_root)
        clone_hash = _canonical_hash(clone_entries)
        source_hash = _canonical_hash(source_entries)
        preparation_case_id = slot["case_id"]
        is_product_case = preparation_case_id in PREPARATION_CASES
        product_git_authority = None
        if is_product_case and os.path.lexists(cwd / ".git"):
            expected_git_commit = case_manifest.get("source_sha")
            if self.test_mode:
                expected_git_commit = ProductGitAuthority._git(
                    cwd, "rev-parse", "HEAD",
                )
            product_git_authority = ProductGitAuthority.capture(
                cwd, expected_commit=expected_git_commit,
            )
        elif is_product_case and not self.test_mode:
            raise PilotBlockedError("production coder clone lacks Git authority")
        allowed_writes = [] if slot["sandbox"] == "read-only" else [str(cwd), str(attempt_root)]
        packet: Dict[str, Any] = {
            "schema": "frozen_codex_packet.v1",
            "task_identity": {
                "ordinal": ordinal,
                "case_id": "smoke" if ordinal == 0 else "P%d" % (((ordinal - 1) % 3) + 1),
                "role": slot["role"],
            },
            "preparation_case_id": slot["case_id"],
            "source_sha": case_manifest.get("source_sha"),
            "preprobe_receipt": preprobe,
            "allowed_patch_paths": (
                self._allowed_patch_paths(preparation_case_id) if is_product_case else []
            ),
            "requested_model": slot["model"],
            "requested_effort": slot["effort"],
            "execution_sandbox": slot["sandbox"],
            "approval_policy": "never",
            "cwd": str(cwd),
            "source_root": str(source_root),
            "artifact_root": str(attempt_root),
            "writable_roots": [str(cwd), str(attempt_root)],
            "protected_roots": list(ProductionSeatbeltPreflight.DEFAULT_PROTECTED_ROOTS),
            "ordered_argv": self._ordered_argv(slot),
            "effective_codex_argv": self._effective_codex_argv(
                slot, final_path=final_path,
            ),
            "environment": {"LANG": "C", "PATH": "/usr/bin:/bin"},
            "allowed_write_targets": allowed_writes,
            "allowed_files": [material["path"] for material in materials.values()],
            "sealed_materials": materials,
            "clone_tree_entries": clone_entries,
            "source_tree_entries": source_entries,
            "clone_tree_hash": clone_hash,
            "reverified_clone_tree_hash": clone_hash,
            "baseline_tree_hash": clone_hash,
            "baseline_product_tree_hash": ProductTreeDelta.tree_hash(cwd),
            "product_git_authority": product_git_authority,
            "source_tree_hash": source_hash,
            "stdout_path": str(attempt_root / "stdout.jsonl"),
            "stderr_path": str(attempt_root / "stderr.txt"),
            "events_path": str(attempt_root / "events.jsonl"),
            "final_path": final_path,
            "timeout_seconds": 900,
            "grace_seconds": 5,
            "preparation_validation": {
                "pilot_packet_validator": "PASS",
                "direct_adapter_authority_validator": "PASS",
            },
        }
        if slot["role"] == "smoke":
            packet.update({
                "expected_final_output": "CODEX_SMOKE_OK",
                "forbid_tool_events": True,
                "forbid_edits": True,
                "smoke_prompt_policy": "read-only-no-tools-no-edits-exact-output",
            })
        packet["packet_hash"] = packet_hash(packet)
        packet["reverified_packet_hash"] = packet["packet_hash"]
        return packet

    def prepare(self, *, run_id: Optional[str]) -> Dict[str, Any]:
        if not isinstance(run_id, str) or self._RUN_ID_RE.fullmatch(run_id) is None:
            raise ValueError("an explicit new run-id is required")
        artifact_run = self.artifact_base / run_id
        clone_run = self.clone_base / run_id
        if artifact_run.exists() or artifact_run.is_symlink() or clone_run.exists() or clone_run.is_symlink():
            raise PilotBlockedError("run-id roots already exist and cannot be reused")

        self.artifact_base.mkdir(parents=True, exist_ok=True)
        self.clone_base.mkdir(parents=True, exist_ok=True)
        artifact_run.mkdir(parents=False, exist_ok=False)
        clone_run.mkdir(parents=False, exist_ok=False)
        writer = _AtomicPreparationWriter()
        started_at = time.time_ns()

        test_receipt = self.test_gate_runner.run()
        CodexSubscriptionPilot._validate_test_receipt(
            test_receipt, require_execution_proof=True,
        )
        required_test_receipt_path = writer.write_json(
            artifact_run / "evidence" / "required_test_gate.v1.json", test_receipt,
        )

        preflight = self.preflight_factory()
        if not isinstance(preflight, CONCRETE_PRODUCTION_PREFLIGHT_TYPE):
            raise PilotBlockedError("concrete production preflight type is required")
        preflight_receipt = preflight.run()
        if not isinstance(preflight_receipt, dict) or preflight_receipt.get(
                "status") != "PASS" or preflight_receipt.get(
                    "provider_process_starts") != 0:
            raise PilotBlockedError("concrete no-provider preflight did not pass")
        preflight_reference = {
            **preflight_receipt,
            "authorizes_execution": False,
            "capability_minted": False,
        }
        preflight_reference_path = writer.write_json(
            artifact_run / "evidence" / "preflight_reference.v1.json",
            preflight_reference,
        )

        smoke_path = Path("/private/tmp") / (
            "codex-product-pilot-smoke-" + str(uuid.uuid4())
        )
        smoke_path.mkdir(parents=False, exist_ok=False)
        slots = _preparation_slots(run_id, self.clone_base)
        slots[0]["clone_path"] = str(smoke_path)
        smoke_provenance = {
            "path": str(smoke_path), "fresh": True,
            "product_source": None, "git_clone": False,
        }
        clone_provenance = []
        for slot in slots[1:]:
            source_name = self._source_name(slot["case_id"])
            destination = Path(slot["clone_path"])
            destination.parent.mkdir(parents=True, exist_ok=False)
            provenance = self.git_seam.clone_detached(
                source=self.source_paths[source_name],
                expected_sha=self.source_shas[source_name],
                destination=destination,
            )
            clone_provenance.append(self._validate_clone_provenance(
                provenance, slot=slot, source_name=source_name,
            ))

        planner_clones = {
            slot["case_id"]: Path(slot["clone_path"])
            for slot in slots if slot["role"] == "planner"
        }
        preprobe_paths: Dict[str, str] = {}
        preprobes: Dict[str, Dict[str, Any]] = {}
        case_manifest_paths: Dict[str, str] = {}
        for case_id in PREPARATION_CASES:
            preprobe_artifact_dir = artifact_run / "preprobes" / case_id
            preprobe_artifact_dir.mkdir(parents=True, exist_ok=False)
            preprobe = self._validate_preprobe(case_id, self.preprobe_runner.run(
                case_id=case_id,
                clone_path=planner_clones[case_id],
                artifact_dir=preprobe_artifact_dir,
            ))
            preprobe_path = writer.write_json(
                preprobe_artifact_dir / "preprobe_receipt.v1.json", preprobe,
            )
            preprobe_paths[case_id] = str(preprobe_path)
            preprobes[case_id] = preprobe
            source_name = self._source_name(case_id)
            case_manifest = {
                "schema": "case_manifest.v1",
                "case_id": case_id,
                "source_product": source_name,
                "source_path": str(self.source_paths[source_name]),
                "source_sha": self.source_shas[source_name],
                "preprobe_receipt_path": str(preprobe_path),
                "preprobe": preprobe,
            }
            case_manifest_path = writer.write_json(
                artifact_run / "cases" / case_id / "case_manifest.v1.json",
                case_manifest,
            )
            case_manifest_paths[case_id] = str(case_manifest_path)

        packets: list[Dict[str, Any]] = []
        packet_paths: list[str] = []
        packet_validation_receipts: list[Dict[str, Any]] = []
        validator = CodexSubscriptionPilot(
            adapter_factory=lambda: None, test_mode=self.test_mode,
        )
        for slot in slots:
            if slot["role"] == "smoke":
                source_root = Path(slot["clone_path"])
                preprobe = {
                    "status": "PASS", "kind": "smoke",
                    "provider_process_starts": 0,
                }
                case_manifest = {
                    "schema": "case_manifest.v1", "case_id": "smoke",
                    "source_path": None, "source_sha": None,
                    "preprobe": preprobe,
                }
            else:
                source_name = self._source_name(slot["case_id"])
                source_root = self.source_paths[source_name]
                preprobe = preprobes[slot["case_id"]]
                case_manifest = _load_json_object(
                    Path(case_manifest_paths[slot["case_id"]]), "case manifest",
                )
            packet = self._build_packet(
                slot=slot,
                artifact_run=artifact_run,
                source_root=source_root,
                preprobe=preprobe,
                case_manifest=case_manifest,
                writer=writer,
            )
            validator._validate_packet(packet, slot["ordinal"], EXACT_CALL_PLAN[slot["ordinal"]])
            packet_path = writer.write_json(
                artifact_run / "packets" / ("%02d.json" % slot["ordinal"]), packet,
            )
            packets.append(packet)
            packet_paths.append(str(packet_path))
            validation_receipt = {
                "pilot_packet_validator": "PASS",
                "direct_adapter_authority_validator": "PASS",
                "real_filesystem_fixture": True,
            }
            if slot["role"] == "smoke":
                validation_receipt["production_smoke_validator"] = "PASS"
            packet_validation_receipts.append(validation_receipt)

        manifest: Dict[str, Any] = {
            "schema": "pace_manifest.v1",
            "spec_sha256": self.spec_sha256,
            "call_plan": EXACT_CALL_PLAN,
            "caps": EXACT_CAPS,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "smoke_packet": packets[0],
            "frozen_packets": packets[1:],
            "required_test_receipt": test_receipt,
            "manifest_hash": "",
        }
        manifest["manifest_hash"] = manifest_hash(manifest)
        manifest_path = writer.write_json(
            artifact_run / "approval" / "pace_manifest.v1.json", manifest,
        )
        required_confirmation_text = (
            "CONFIRM CODEX PRODUCT PILOT %s %s" % (run_id, manifest["manifest_hash"])
        )
        confirmation_request = {
            "schema": "confirmation_request.v1",
            "confirmed": False,
            "run_id": run_id,
            "spec_sha256": self.spec_sha256,
            "manifest_hash": manifest["manifest_hash"],
            "call_plan": EXACT_CALL_PLAN,
            "caps": PREPARATION_DISPLAYED_CAPS,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "possible_codex_state_disclosure": (
                "codex-cli-0.41.0-has-no-ephemeral-and-may-write-under-~/.codex"
            ),
            "required_confirmation_text": required_confirmation_text,
        }
        confirmation_request_path = writer.write_json(
            artifact_run / "approval" / "confirmation_request.v1.json",
            confirmation_request,
        )

        inventory_entries = []
        for path_value in writer.file_fsync_paths:
            path = Path(path_value)
            content = path.read_bytes()
            inventory_entries.append({
                "path": str(path), "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        artifact_manifest_path = writer.write_jsonl(
            artifact_run / "artifact_manifest.jsonl", inventory_entries,
        )
        preparation_receipt_path = artifact_run / "preparation_receipt.v1.json"
        receipt: Dict[str, Any] = {
            "schema": "codex_pilot_preparation_receipt.v1",
            "status": "HUMAN_RECONFIRMATION_REQUIRED",
            "run_id": run_id,
            "provider_process_starts": 0,
            "codex_exec_starts": 0,
            "reserved_cap_units": 0,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "promotion_eligible": False,
            "execution_preflight": "RERUN_REQUIRED",
            "artifact_root": str(artifact_run),
            "clone_root": str(clone_run),
            "slots": slots,
            "smoke_provenance": smoke_provenance,
            "clone_provenance": clone_provenance,
            "preprobe_paths": preprobe_paths,
            "case_manifest_paths": case_manifest_paths,
            "packet_paths": packet_paths,
            "packet_validation_receipts": packet_validation_receipts,
            "required_test_receipt_path": str(required_test_receipt_path),
            "preflight_reference_path": str(preflight_reference_path),
            "manifest_path": str(manifest_path),
            "confirmation_request_path": str(confirmation_request_path),
            "artifact_manifest_path": str(artifact_manifest_path),
            "preparation_receipt_path": str(preparation_receipt_path),
            "fsync_evidence": writer.evidence(),
            "determinism_normalization": PREPARATION_NORMALIZATION,
            "started_at": started_at,
            "finished_at": max(time.time_ns(), started_at + 1),
        }
        writer.write_json(preparation_receipt_path, receipt)
        self.verify_seal(preparation_receipt_path)
        return receipt

    def verify_seal(self, preparation_receipt_path: Any) -> Dict[str, Any]:
        try:
            receipt = _load_json_object(Path(preparation_receipt_path), "preparation receipt")
            inventory_path = Path(receipt["artifact_manifest_path"])
            inventory = [
                json.loads(line) for line in inventory_path.read_text(encoding="utf-8").splitlines()
            ]
        except (KeyError, OSError, UnicodeError, ValueError, TypeError) as exc:
            raise PilotBlockedError("preparation seal or artifact manifest is invalid") from exc
        if not inventory:
            raise PilotBlockedError("preparation seal inventory is empty")
        for entry in inventory:
            try:
                path = Path(entry["path"])
                content = path.read_bytes()
            except (KeyError, OSError, TypeError) as exc:
                raise PilotBlockedError("sealed artifact receipt is unavailable") from exc
            if entry.get("size") != len(content) or entry.get(
                    "sha256") != hashlib.sha256(content).hexdigest():
                raise PilotBlockedError("sealed artifact mutation or hash mismatch")

        test_receipt = _load_json_object(
            Path(receipt["required_test_receipt_path"]), "required test receipt",
        )
        CodexSubscriptionPilot._validate_test_receipt(
            test_receipt, require_execution_proof=True,
        )
        preflight_reference = _load_json_object(
            Path(receipt["preflight_reference_path"]), "preflight reference",
        )
        if preflight_reference.get("status") != "PASS" or preflight_reference.get(
                "provider_process_starts") != 0 or preflight_reference.get(
                    "authorizes_execution") is not False or preflight_reference.get(
                        "capability_minted") is not False:
            raise PilotBlockedError("preflight reference receipt is mutated or authorizing")

        packets = []
        for packet_path_value in receipt.get("packet_paths", []):
            packet = _load_json_object(Path(packet_path_value), "frozen packet")
            if packet.get("packet_hash") != packet_hash(packet) or packet.get(
                    "reverified_packet_hash") != packet.get("packet_hash"):
                raise PilotBlockedError("sealed packet hash mutation")
            clone_entries = _preparation_tree_entries(packet.get("cwd"))
            source_entries = _preparation_tree_entries(packet.get("source_root"))
            if clone_entries != packet.get("clone_tree_entries") or _canonical_hash(
                    clone_entries) != packet.get("clone_tree_hash"):
                raise PilotBlockedError("sealed clone tree mutation")
            if source_entries != packet.get("source_tree_entries") or _canonical_hash(
                    source_entries) != packet.get("source_tree_hash"):
                raise PilotBlockedError("sealed source tree mutation")
            materials = packet.get("sealed_materials")
            if not isinstance(materials, dict) or set(materials) != REQUIRED_MATERIALS:
                raise PilotBlockedError("sealed material receipt is incomplete")
            for material in materials.values():
                try:
                    content = Path(material["path"]).read_bytes()
                except (KeyError, OSError, TypeError) as exc:
                    raise PilotBlockedError("sealed material receipt is unavailable") from exc
                if material.get("sha256") != hashlib.sha256(content).hexdigest():
                    raise PilotBlockedError("sealed material mutation")
            packets.append(packet)
        if len(packets) != 10:
            raise PilotBlockedError("sealed packet count is invalid")

        manifest = _load_json_object(Path(receipt["manifest_path"]), "manifest")
        if manifest.get("manifest_hash") != manifest_hash(manifest) or manifest.get(
                "smoke_packet") != packets[0] or manifest.get(
                    "frozen_packets") != packets[1:] or manifest.get(
                        "required_test_receipt") != test_receipt:
            raise PilotBlockedError("sealed manifest hash or packet receipt changed")
        request = _load_json_object(
            Path(receipt["confirmation_request_path"]), "confirmation request",
        )
        expected_text = "CONFIRM CODEX PRODUCT PILOT %s %s" % (
            receipt.get("run_id"), manifest["manifest_hash"],
        )
        if request.get("schema") != "confirmation_request.v1" or request.get(
                "confirmed") is not False or request.get("manifest_hash") != manifest[
                    "manifest_hash"] or request.get("caps") != PREPARATION_DISPLAYED_CAPS or request.get(
                        "required_confirmation_text") != expected_text:
            raise PilotBlockedError("sealed confirmation request is mutated")
        return {
            "status": "PASS", "provider_process_starts": 0,
            "promotion_boundary": PROMOTION_BOUNDARY,
        }


class _PilotArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args: Optional[list[str]] = None,
                   namespace: Optional[argparse.Namespace] = None) -> argparse.Namespace:
        parsed = super().parse_args(args, namespace)
        if getattr(parsed, "prepare_pilot", False) and not getattr(parsed, "run_id", None):
            self.error("--prepare-pilot requires an explicit --run-id")
        return parsed


class _PreparationInertLedger:
    def reserve(self, *args: Any, **kwargs: Any) -> Any:
        raise PilotBlockedError("preparation cannot reserve provider capacity")

    @staticmethod
    def totals() -> Dict[str, int]:
        return {
            "calls": 0, "seconds": 0, "observed_total_tokens": 0,
            "subscription_allowance_units": 0,
        }


def _forbidden_preparation_provider(*args: Any, **kwargs: Any) -> Any:
    raise PilotBlockedError("preparation cannot construct a provider adapter")


PRODUCTION_PREPARATION_CONFIG: Dict[str, Any] = {
    "schema": "codex-pilot-preparation-config.v1",
    "test_mode": False,
    "artifact_base": str(
        Path(__file__).resolve().parents[2]
        / "loop-team/runs/2026-07-16_model-routing-pace/artifacts/codex_product_pilot"
    ),
    "clone_base": "/private/tmp/codex-product-pilot",
    "source_paths": {
        "taxahead": "<HOME>/Claude/Projects/taxahead-integration",
        "pms": "<HOME>/Claude/Projects/padsplit-reverification/pms",
    },
    "source_shas": {
        "taxahead": "a78f13598cf7a425de4bd20e92d6b97f140eedb3",
        "pms": "4a396220b598d640e4bea5fb703c24efe83c23c5",
    },
    "preparer_type": CodexPilotPreparer,
    "git_seam_type": ProductionPreparationGit,
    "preprobe_runner_type": ProductionProductPreprobeRunner,
    "material_builder_type": ProductionCaseMaterialBuilder,
}


def _prepare_pilot(*, run_id: str) -> Dict[str, Any]:
    """Production preparation entry point; never constructs a provider adapter."""
    config = PRODUCTION_PREPARATION_CONFIG
    if not isinstance(config, dict) or config.get(
            "schema") != "codex-pilot-preparation-config.v1":
        raise PilotBlockedError("production preparation configuration is invalid")
    preparer_type = config.get("preparer_type")
    if not callable(preparer_type):
        raise PilotBlockedError("production preparer type is invalid")
    configured_kwargs = config.get("preparer_kwargs")
    if configured_kwargs is not None:
        if not isinstance(configured_kwargs, dict):
            raise PilotBlockedError("injected preparation kwargs are invalid")
        kwargs = dict(configured_kwargs)
    else:
        git_seam_type = config.get("git_seam_type")
        preprobe_runner_type = config.get("preprobe_runner_type")
        material_builder_type = config.get("material_builder_type")
        if not all(callable(value) for value in (
                git_seam_type, preprobe_runner_type, material_builder_type)):
            raise PilotBlockedError("production preparation builders are invalid")
        kwargs = {
            "artifact_base": config.get("artifact_base"),
            "clone_base": config.get("clone_base"),
            "source_paths": config.get("source_paths"),
            "source_shas": config.get("source_shas"),
            "test_gate_runner": RequiredTestGateRunner(),
            "preflight_factory": ProductionSeatbeltPreflight,
            "git_seam": git_seam_type(),
            "preprobe_runner": preprobe_runner_type(),
            "material_builder": material_builder_type(),
            "cap_ledger": _PreparationInertLedger(),
            "provider_factory": _forbidden_preparation_provider,
            "test_mode": bool(config.get("test_mode")),
        }
    preparer = preparer_type(**kwargs)
    return preparer.prepare(run_id=run_id)


def _build_parser() -> argparse.ArgumentParser:
    parser = _PilotArgumentParser(
        description="Validate the sealed non-promoting Codex subscription pilot contract."
    )
    parser.add_argument("--run-id", required=False)
    parser.add_argument("--approval", type=Path, required=False)
    parser.add_argument("--manifest", type=Path, required=False)
    parser.add_argument("--sealed-fake-config", type=Path, required=False)
    parser.add_argument(
        "--preflight-only", action="store_true",
        help="Run only the concrete no-provider Codex Seatbelt preflight.",
    )
    parser.add_argument(
        "--prepare-pilot", action="store_true",
        help="Prepare and seal the provider-inert pilot inputs for explicit confirmation.",
    )
    parser.add_argument(
        "--execute-smoke-and-pilot", action="store_true",
        help="Request the authority-gated 1+9 execution path.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.prepare_pilot:
        try:
            receipt = _prepare_pilot(run_id=args.run_id)
        except Exception as exc:
            receipt = {
                "status": "PRECHECK_FAILED",
                "failure_code": type(exc).__name__,
                "reason": str(exc),
                "provider_process_starts": 0,
                "codex_exec_starts": 0,
                "reserved_cap_units": 0,
                "promotion_boundary": PROMOTION_BOUNDARY,
                "promotion_eligible": False,
            }
        print(_canonical_json(receipt))
        complete = (
            receipt.get("status") == "HUMAN_RECONFIRMATION_REQUIRED"
            and receipt.get("provider_process_starts") == 0
            and receipt.get("codex_exec_starts") == 0
            and receipt.get("reserved_cap_units") == 0
            and receipt.get("promotion_boundary") == PROMOTION_BOUNDARY
            and all(isinstance(receipt.get(field), str) and receipt[field] for field in (
                "manifest_path", "confirmation_request_path", "preparation_receipt_path",
            ))
        )
        return 0 if complete else 2
    if args.preflight_only:
        try:
            receipt = ProductionSeatbeltPreflight().run()
        except Exception as exc:
            receipt = {
                "status": "PRECHECK_FAILED",
                "failure_code": type(exc).__name__,
                "blocker_class": "local_compatibility_precheck",
                "provider_process_starts": 0,
                "promotion_boundary": PROMOTION_BOUNDARY,
                "usd_cost": None,
            }
        print(_canonical_json(receipt))
        return 0 if receipt.get("status") == "PASS" else 2
    if not args.execute_smoke_and_pilot:
        return 0
    try:
        if args.sealed_fake_config is not None:
            report = _run_sealed_fake(args.sealed_fake_config)
        else:
            report = _run_production(args.approval, args.manifest)
    except Exception as exc:
        print(_canonical_json({
            "decision": "PILOT_ABORTED", "reason": str(exc),
            "pace_status": PROMOTION_BOUNDARY,
        }), file=sys.stderr)
        return 2
    print(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
