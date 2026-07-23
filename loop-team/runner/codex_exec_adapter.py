"""Fail-closed, injectable adapter for a sealed Codex CLI attempt.

The adapter deliberately has no convenience path for starting an unsealed run.
Tests provide every process and containment collaborator; callers that use the
production defaults must still pass the same packet and containment evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import experiment_execution as _execution


SPEC_SHA256 = "eab8f4f80758beaf2ea3326df4a176e091778a0f9dbea23dbf5cccea633d06e8"
# Rejection-only fixture used to prove that no historical spec hash is authoritative.
LEGACY_TEST_SPEC_SHA256 = "9b447ac464b8a9f6b2952846cefbb54aef8bbe7b1837e91d1823fc7731c727b3"
PROMOTION_BOUNDARY = "PILOT_ONLY/NO_ROUTING_PROMOTION"
EXACT_CAPS = {
    "combined_calls": 10,
    "combined_timeout_seconds": 9000,
    "aggregate_observed_tokens_max_when_telemetry_exists": 1500000,
    "subscription_allowance_units_max": 10,
}
REQUIRED_MATERIALS = ("prompt", "plan", "oracle", "test", "dependency", "preprobe")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
SUPPORTED_REASONING_EFFORTS = frozenset({"minimal", "low", "medium", "high"})


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


class CodexAdapterBlockedError(RuntimeError):
    """A Codex attempt was blocked, with only a redacted observation retained."""

    code = "PILOT_ABORTED"

    def __init__(self, message: str, observation: Dict[str, Any]):
        super().__init__(message)
        self.observation = observation


_PRODUCTION_CONTAINMENT_FACTORY_TOKEN = object()


class _TrustedContainmentSeed:
    """Internal immutable seed created only by a completed concrete preflight."""

    __slots__ = (
        "artifact_path", "artifact_sha256", "policy_bytes", "receipt_bytes",
        "receipt_sha256", "slot_bytes", "version",
    )

    def __init__(self, *, factory_token: object, artifact_path: str,
                 artifact_sha256: str, policy_bytes: bytes,
                 receipt_bytes: bytes, receipt_sha256: str,
                 slot_bytes: Optional[bytes], version: str) -> None:
        if factory_token is not _PRODUCTION_CONTAINMENT_FACTORY_TOKEN:
            raise TypeError("trusted containment seeds are internal preflight artifacts")
        self.artifact_path = artifact_path
        self.artifact_sha256 = artifact_sha256
        self.policy_bytes = policy_bytes
        self.receipt_bytes = receipt_bytes
        self.receipt_sha256 = receipt_sha256
        self.slot_bytes = slot_bytes
        self.version = version


class TrustedProductionContainment:
    """Opaque one-use capability backed by a retained Seatbelt receipt."""

    IDENTITY = "runner.codex_exec_adapter.TrustedProductionContainment.v1"
    VERSION = "1"
    __slots__ = ("__seed", "__consumed", "__lock")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        token = kwargs.pop("_factory_token", None)
        seed = kwargs.pop("_seed", None)
        if args or kwargs or token is not _PRODUCTION_CONTAINMENT_FACTORY_TOKEN:
            raise TypeError(
                "concrete production containment cannot be constructed from a callback"
            )
        if type(seed) is not _TrustedContainmentSeed:
            raise TypeError("concrete production containment requires a preflight capability")
        object.__setattr__(self, "_TrustedProductionContainment__seed", seed)
        object.__setattr__(self, "_TrustedProductionContainment__consumed", False)
        object.__setattr__(self, "_TrustedProductionContainment__lock", threading.Lock())

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("trusted production containment capability is immutable")

    def __copy__(self) -> "TrustedProductionContainment":
        raise TypeError("trusted production containment capability cannot be copied")

    def __deepcopy__(self, memo: Dict[int, Any]) -> "TrustedProductionContainment":
        raise TypeError("trusted production containment capability cannot be deep-copied")

    def __reduce__(self) -> Any:
        raise TypeError("trusted production containment capability cannot be pickled")

    def __reduce_ex__(self, protocol: int) -> Any:
        raise TypeError("trusted production containment capability cannot be pickled")

    def probe(self, **kwargs: Any) -> Dict[str, Any]:
        seed = self.__seed
        with self.__lock:
            if self.__consumed:
                raise RuntimeError("trusted production containment capability was already consumed")
            object.__setattr__(self, "_TrustedProductionContainment__consumed", True)
        supplied_slot = kwargs.get("slot")
        if seed.slot_bytes is not None:
            if supplied_slot is not None:
                if set(kwargs) != {"slot"} or canonical_bytes(supplied_slot) != seed.slot_bytes:
                    raise RuntimeError("containment capability request does not match its slot")
            else:
                bound_slot = json.loads(seed.slot_bytes.decode("utf-8"))
                supplied_slot = dict(bound_slot)
                supplied_slot.update({
                    "cwd": kwargs.get("cwd"),
                    "writable_roots": kwargs.get("writable_roots"),
                    "protected_roots": kwargs.get("protected_roots"),
                    "model": kwargs.get("model"),
                    "effort": kwargs.get("effort"),
                    "sandbox": kwargs.get("sandbox"),
                })
                if kwargs.get("slot_id") is not None:
                    supplied_slot["slot_id"] = kwargs["slot_id"]
                if canonical_bytes(supplied_slot) != seed.slot_bytes:
                    raise RuntimeError("containment capability request does not match its slot")
        try:
            artifact_bytes = Path(seed.artifact_path).read_bytes()
        except OSError as exc:
            raise RuntimeError("trusted preflight receipt artifact is unavailable") from exc
        if hashlib.sha256(artifact_bytes).hexdigest() != seed.artifact_sha256:
            raise RuntimeError("trusted preflight receipt artifact was mutated")
        if hashlib.sha256(seed.receipt_bytes).hexdigest() != seed.receipt_sha256:
            raise RuntimeError("trusted preflight receipt capability is invalid")
        policy_bytes = seed.policy_bytes
        if not policy_bytes:
            raise TypeError("trusted Seatbelt receipt has no policy bytes")
        attested = {
            "mechanism": "codex-seatbelt",
            "version": seed.version,
            "os_enforced": True,
            "writable_roots": list(kwargs.get("writable_roots", [])),
            "bound_request_writable_roots": list(kwargs.get("writable_roots", [])),
            "filesystem_violations": [],
            "network_attempts": [],
            "protected_root_changes": [],
            "preflight_receipt_sha256": canonical_hash(
                json.loads(seed.receipt_bytes.decode("utf-8"))
            ),
            "preflight_artifact_sha256": seed.artifact_sha256,
        }
        attested["trusted_identity"] = self.IDENTITY
        attested["policy_hash"] = hashlib.sha256(policy_bytes).hexdigest()
        attested["policy_bytes"] = policy_bytes
        attested["containment_attestation"] = canonical_hash({
            "identity": self.IDENTITY,
            "version": self.VERSION,
            "policy_hash": attested["policy_hash"],
            "argv": kwargs.get("argv"),
            "cwd": kwargs.get("cwd"),
            "writable_roots": kwargs.get("writable_roots"),
            "protected_roots": kwargs.get("protected_roots"),
            "environment": kwargs.get("environment"),
        })
        return attested

    @classmethod
    def verify(cls, receipt: Dict[str, Any], **kwargs: Any) -> bool:
        expected = canonical_hash({
            "identity": cls.IDENTITY,
            "version": cls.VERSION,
            "policy_hash": receipt.get("policy_hash"),
            "argv": kwargs.get("argv"),
            "cwd": kwargs.get("cwd"),
            "writable_roots": kwargs.get("writable_roots"),
            "protected_roots": kwargs.get("protected_roots"),
            "environment": kwargs.get("environment"),
        })
        return (
            receipt.get("trusted_identity") == cls.IDENTITY
            and receipt.get("containment_attestation") == expected
        )


# Kept as a symbol alias only; authorization checks require the production type above.
TrustedContainmentProbe = TrustedProductionContainment


class ProductionSeatbeltPreflight:
    """Concrete, provider-inert Codex Seatbelt compatibility preflight."""

    CODEX_BINARY = "/opt/homebrew/bin/codex"
    CODEX_VERSION = "codex-cli 0.41.0"
    TARGET_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
    MATRIX = (
        ("gpt-5.6-sol", "high", "read-only"),
        ("gpt-5.6-sol", "high", "workspace-write"),
        ("gpt-5.6-terra", "high", "workspace-write"),
        ("gpt-5.6-luna", "medium", "workspace-write"),
    )
    DEFAULT_PROTECTED_ROOTS = (
        "<HOME>/Claude/Projects/taxahead",
        "<HOME>/Claude/Projects/taxahead-integration",
        "<HOME>/Claude/Projects/padsplit-reverification/pms",
    )

    def __init__(self, *, popen_factory: Any = subprocess.Popen,
                 test_mode: bool = False, artifact_dir: Any = None,
                 model_cache_path: Any = None) -> None:
        if popen_factory is not subprocess.Popen and not test_mode:
            raise TypeError("subprocess dependency injection is permitted only in test mode")
        self._popen_factory = popen_factory
        self.test_mode = test_mode
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
        self.model_cache_path = Path(model_cache_path).expanduser() if model_cache_path is not None else (
            Path.home() / ".codex" / "models_cache.json"
        )
        self._last_receipt: Optional[Dict[str, Any]] = None
        self._last_receipt_bytes: Optional[bytes] = None
        self._minted_slot_hashes: set[str] = set()
        self._capability_count = 0

    @staticmethod
    def _policy_bytes(cwd: str, protected_roots: Iterable[str],
                      sandbox: Optional[str] = None) -> str:
        policy = {
            "schema": "codex-seatbelt-preflight-policy.v1",
            "cwd_write": cwd,
            "protected_roots": list(protected_roots),
            "network": "deny-all-including-localhost",
            "approval": "never",
        }
        if sandbox is not None:
            policy.update({
                "sandbox": sandbox,
                "cwd_write_expectation": (
                    "DENIED_EPERM" if sandbox == "read-only" else "ALLOWED"
                ),
            })
        return json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _probe_bytes(cwd: str, protected_roots: Iterable[str]) -> str:
        protected_json = json.dumps(list(protected_roots), separators=(",", ":"))
        cwd_json = json.dumps(cwd)
        return (
            "import errno,json,pathlib,socket\n"
            f"cwd=pathlib.Path({cwd_json})\n"
            f"protected={protected_json}\n"
            "def result(fn):\n"
            " try:\n"
            "  value=fn(); return {'exit_code':0,'stdout':value,'stderr':''}\n"
            " except OSError as exc:\n"
            "  return {'exit_code':1,'stdout':'','stderr':str(exc),'errno':errno.errorcode.get(exc.errno,str(exc.errno))}\n"
            "allowed=result(lambda:(cwd/'seatbelt-allowed.txt').write_text('WRITE_ALLOWED',encoding='utf-8') and 'WRITE_ALLOWED')\n"
            "denied=[]\n"
            "for root in protected:\n"
            " denied.append(result(lambda root=root:pathlib.Path(root,'codex-seatbelt-denied.txt').write_text('DENIED',encoding='utf-8')))\n"
            "def network():\n"
            " sock=socket.socket(); sock.settimeout(0.2); sock.connect(('127.0.0.1',9)); return 'NETWORK_ALLOWED'\n"
            "network_result=result(network)\n"
            "print(json.dumps({'allowed_cwd_write':allowed,'denied_protected_write':denied[0],'denied_protected_writes':denied,'denied_network':network_result},sort_keys=True))\n"
        )

    def _invoke(self, argv: List[str], *, cwd: Optional[str] = None) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
            "start_new_session": True,
            "text": True,
        }
        if cwd is not None:
            kwargs["cwd"] = cwd
        process = self._popen_factory(list(argv), **kwargs)
        stdout, stderr = process.communicate(timeout=30)
        return {
            "stdout": stdout if isinstance(stdout, str) else "",
            "stderr": stderr if isinstance(stderr, str) else "",
            "returncode": getattr(process, "returncode", None),
            "argv": list(argv),
        }

    def run_probe(self, *, model: str, effort: str, cwd: str,
                  protected_root: str,
                  additional_protected_roots: Iterable[str] = (),
                  sandbox: Optional[str] = None) -> Dict[str, Any]:
        if model not in self.TARGET_MODELS or effort not in SUPPORTED_REASONING_EFFORTS:
            raise ValueError("preflight model or reasoning effort is outside the sealed matrix")
        if sandbox not in (None, "read-only", "workspace-write"):
            raise ValueError("preflight sandbox is outside the sealed matrix")
        effective_sandbox = sandbox or "read-only"
        protected_roots = [protected_root, *list(additional_protected_roots)]
        policy_bytes = self._policy_bytes(cwd, protected_roots, effective_sandbox)
        probe_bytes = self._probe_bytes(cwd, protected_roots)
        argv = [
            self.CODEX_BINARY, "--model", model,
            "-c", "model_reasoning_effort=" + effort,
            "debug", "seatbelt",
        ]
        if effective_sandbox == "workspace-write":
            argv.append("--full-auto")
        argv.extend([
            "--", "/usr/bin/python3", "-c", probe_bytes,
        ])
        process_result = self._invoke(argv, cwd=cwd if Path(cwd).is_dir() else None)
        stdout = process_result["stdout"]
        stderr = process_result["stderr"]
        receipt: Dict[str, Any] = {
            "status": "PRECHECK_FAILED",
            "failure_code": "SEATBELT_PROBE_FAILED",
            "blocker_class": "local_compatibility_precheck",
            "provider_process_starts": 0,
            "model": model,
            "effort": effort,
            "sandbox": effective_sandbox,
            "cwd_write_expectation": (
                "DENIED_EPERM" if effective_sandbox == "read-only" else "ALLOWED"
            ),
            "cwd": cwd,
            "protected_roots": protected_roots,
            "argv": argv,
            "argv_sha256": hashlib.sha256(canonical_bytes(argv)).hexdigest(),
            "probe_bytes": probe_bytes,
            "probe_sha256": hashlib.sha256(probe_bytes.encode("utf-8")).hexdigest(),
            "policy_bytes": policy_bytes,
            "policy_sha256": hashlib.sha256(policy_bytes.encode("utf-8")).hexdigest(),
            "stdout": stdout,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr": stderr,
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
            "process_exit_code": process_result["returncode"],
        }
        if "sandbox_apply" in stderr and "Operation not permitted" in stderr:
            receipt["failure_code"] = "NESTED_APP_SANDBOX_DENIED"
            return receipt
        if process_result["returncode"] != 0:
            return receipt
        try:
            payload = json.loads(stdout.strip())
        except (TypeError, ValueError):
            receipt["failure_code"] = "INVALID_SEATBELT_PROBE_OUTPUT"
            return receipt
        if not isinstance(payload, dict):
            return receipt
        allowed = payload.get("allowed_cwd_write")
        protected = payload.get("denied_protected_write")
        protected_results = payload.get("denied_protected_writes", [protected])
        network = payload.get("denied_network")
        receipt.update({
            "allowed_cwd_write": allowed,
            "denied_protected_write": protected,
            "denied_protected_writes": protected_results,
            "denied_network": network,
        })
        failed_root: Optional[str] = None
        if not isinstance(protected_results, list) or len(
                protected_results) != len(protected_roots):
            failed_root = protected_roots[min(
                len(protected_results) if isinstance(protected_results, list) else 0,
                len(protected_roots) - 1,
            )]
        else:
            for root, result in zip(protected_roots, protected_results):
                if not isinstance(result, dict) or result.get(
                        "exit_code") == 0 or result.get("errno") != "EPERM":
                    failed_root = root
                    break
        if failed_root is not None:
            receipt["failure_code"] = "PROTECTED_ROOT_WRITE_NOT_DENIED"
            receipt["failed_protected_root"] = failed_root
            return receipt
        if effective_sandbox == "read-only":
            cwd_passed = (
                isinstance(allowed, dict) and allowed.get("exit_code") != 0
                and allowed.get("errno") == "EPERM"
            )
        else:
            cwd_passed = (
                isinstance(allowed, dict) and allowed.get("exit_code") == 0
                and allowed.get("stdout") == "WRITE_ALLOWED"
            )
        evidence_passed = cwd_passed and isinstance(network, dict) and network.get(
            "exit_code") != 0 and network.get("errno") == "EPERM"
        if evidence_passed:
            receipt["status"] = "PASS"
            receipt["failure_code"] = None
        return receipt

    def _read_model_cache(self) -> Dict[str, Any]:
        try:
            payload = json.loads(self.model_cache_path.read_text(encoding="utf-8"))
            age_seconds = max(0.0, time.time() - self.model_cache_path.stat().st_mtime)
        except (OSError, TypeError, ValueError):
            payload = {}
            age_seconds = float("inf")
        models = payload.get("models") if isinstance(payload, dict) else None
        slugs = {
            item.get("slug") for item in models
            if isinstance(item, dict) and isinstance(item.get("slug"), str)
        } if isinstance(models, list) else set()
        etag = payload.get("etag") if isinstance(payload, dict) else None
        targets = {slug: slug in slugs for slug in self.TARGET_MODELS}
        return {
            "path": str(self.model_cache_path),
            "etag": etag,
            "fresh": isinstance(etag, str) and bool(etag) and age_seconds <= 86400,
            "age_seconds": None if age_seconds == float("inf") else age_seconds,
            "target_slugs": targets,
            "sha256": hashlib.sha256(self.model_cache_path.read_bytes()).hexdigest()
            if self.model_cache_path.is_file() else None,
        }

    def _persist_receipt(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        persisted = json.loads(json.dumps(receipt))
        persisted["aggregate_receipt_sha256"] = canonical_hash(persisted)
        artifact_root = self.artifact_dir
        if artifact_root is None:
            artifact_root = Path(tempfile.mkdtemp(
                prefix="codex-product-pilot-preflight-artifacts-", dir="/private/tmp",
            ))
        artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_root / ("seatbelt-preflight-" + uuid.uuid4().hex + ".json")
        artifact_bytes = canonical_bytes(persisted) + b"\n"
        temporary_path = artifact_path.with_name("." + artifact_path.name + ".tmp")
        temporary_path.write_bytes(artifact_bytes)
        os.replace(temporary_path, artifact_path)
        completed = json.loads(json.dumps(persisted))
        completed.update({
            "artifact_path": str(artifact_path),
            "artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        })
        return completed

    def run(self, *, cwd: Optional[str] = None,
            protected_root: Optional[str] = None) -> Dict[str, Any]:
        self._last_receipt = None
        self._last_receipt_bytes = None
        self._minted_slot_hashes = set()
        self._capability_count = 0
        if cwd is None:
            cwd = tempfile.mkdtemp(prefix="codex-product-pilot-preflight-", dir="/private/tmp")
        if protected_root is None:
            protected_root = self.DEFAULT_PROTECTED_ROOTS[0]
        version_result = self._invoke([self.CODEX_BINARY, "--version"])
        version = version_result["stdout"].strip()
        binary_ok = version_result["returncode"] == 0 and version == self.CODEX_VERSION
        cache = self._read_model_cache()
        cache_ok = cache["fresh"] is True and all(cache["target_slugs"].values())
        checks = []
        for model, effort, sandbox in self.MATRIX:
            extra_roots = self.DEFAULT_PROTECTED_ROOTS[1:] if protected_root == self.DEFAULT_PROTECTED_ROOTS[0] else ()
            probe = self.run_probe(
                model=model, effort=effort, cwd=cwd, protected_root=protected_root,
                additional_protected_roots=extra_roots,
                sandbox=sandbox,
            )
            check = {
                "model": model,
                "effort": effort,
                "sandbox": sandbox,
                "argv": probe["argv"],
                "policy_bytes": probe["policy_bytes"],
                "argv_config_syntax": "PASS" if probe["status"] == "PASS" else "PRECHECK_FAILED",
                "seatbelt_containment": probe["status"],
                "probe_receipt_sha256": canonical_hash(probe),
            }
            for field in (
                    "argv_sha256", "probe_sha256", "policy_sha256",
                    "stdout_sha256", "stderr_sha256", "process_exit_code"):
                check[field] = probe[field]
            checks.append(check)
        passed = binary_ok and cache_ok and all(
            check["seatbelt_containment"] == "PASS" for check in checks
        )
        aggregate_protected_roots = [
            protected_root,
            *(self.DEFAULT_PROTECTED_ROOTS[1:]
              if protected_root == self.DEFAULT_PROTECTED_ROOTS[0] else ()),
        ]
        receipt = {
            "status": "PASS" if passed else "PRECHECK_FAILED",
            "failure_code": None if passed else "PRODUCTION_PREFLIGHT_FAILED",
            "blocker_class": None if passed else "local_compatibility_precheck",
            "provider_process_starts": 0,
            "binary": {
                "path": self.CODEX_BINARY,
                "version": version,
                "status": "PASS" if binary_ok else "PRECHECK_FAILED",
            },
            "accepted_reasoning_efforts": ["minimal", "low", "medium", "high"],
            "model_cache": cache,
            "model_resolution": "UNKNOWN_UNTIL_SMOKE",
            "checks": checks,
            "promotion_boundary": PROMOTION_BOUNDARY,
            "usd_cost": None,
            "policy_bytes": self._policy_bytes(cwd, aggregate_protected_roots),
        }
        completed = self._persist_receipt(receipt)
        self._last_receipt = json.loads(json.dumps(completed))
        self._last_receipt_bytes = canonical_bytes(self._last_receipt)
        return json.loads(json.dumps(completed))

    def trusted_containment(self, *, slot: Optional[Dict[str, Any]] = None
                            ) -> TrustedProductionContainment:
        if self._last_receipt is None or self._last_receipt.get("status") != "PASS" or (
                self._last_receipt_bytes is None):
            raise TypeError("production Seatbelt preflight has not run")
        if self._capability_count >= 10:
            raise RuntimeError("trusted production containment capability broker is exhausted")
        slot_bytes: Optional[bytes] = None
        if slot is not None:
            required = {
                "slot_id", "cwd", "writable_roots", "protected_roots",
                "model", "effort", "sandbox", "policy_sha256",
            }
            if not isinstance(slot, dict) or not required.issubset(slot) or not isinstance(
                    slot.get("slot_id"), str) or not slot["slot_id"] or not isinstance(
                        slot.get("cwd"), str) or not isinstance(
                            slot.get("writable_roots"), list) or not isinstance(
                                slot.get("protected_roots"), list) or slot.get(
                                    "model") not in self.TARGET_MODELS or slot.get(
                                        "effort") not in SUPPORTED_REASONING_EFFORTS or slot.get(
                                            "sandbox") not in {"read-only", "workspace-write"} or not is_sha256(
                                                slot.get("policy_sha256")):
                raise TypeError("trusted containment slot contract is invalid")
            slot_bytes = canonical_bytes(slot)
            slot_hash = hashlib.sha256(slot_bytes).hexdigest()
            if slot_hash in self._minted_slot_hashes:
                raise RuntimeError("trusted containment capability slot was already minted")
        else:
            slot_hash = "unbound-test-capability"
            if slot_hash in self._minted_slot_hashes:
                raise RuntimeError("trusted production containment capability was already minted")
        artifact_path = self._last_receipt.get("artifact_path")
        artifact_sha256 = self._last_receipt.get("artifact_sha256")
        policy_text = self._last_receipt.get("policy_bytes")
        if not isinstance(artifact_path, str) or not is_sha256(artifact_sha256) or not isinstance(
                policy_text, str):
            raise TypeError("production Seatbelt preflight receipt is incomplete")
        try:
            artifact_bytes = Path(artifact_path).read_bytes()
        except OSError as exc:
            raise RuntimeError("production preflight receipt artifact is unavailable") from exc
        if hashlib.sha256(artifact_bytes).hexdigest() != artifact_sha256:
            raise RuntimeError("production preflight receipt artifact was mutated")
        seed = _TrustedContainmentSeed(
            factory_token=_PRODUCTION_CONTAINMENT_FACTORY_TOKEN,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha256,
            policy_bytes=policy_text.encode("utf-8"),
            receipt_bytes=self._last_receipt_bytes,
            receipt_sha256=hashlib.sha256(self._last_receipt_bytes).hexdigest(),
            slot_bytes=slot_bytes,
            version=self._last_receipt.get("binary", {}).get("version", self.CODEX_VERSION),
        )
        capability = TrustedProductionContainment(
            _factory_token=_PRODUCTION_CONTAINMENT_FACTORY_TOKEN,
            _seed=seed,
        )
        self._minted_slot_hashes.add(slot_hash)
        self._capability_count += 1
        return capability


@dataclass(frozen=True)
class CodexExecRequest:
    prompt: str
    clone_path: str
    artifact_dir: str
    output_last_message_path: str
    requested_model: str
    requested_effort: str
    timeout_seconds: int
    grace_seconds: int
    approval_hash: str
    manifest_hash: str
    protected_roots: List[str]
    frozen_packet: Dict[str, Any]


@dataclass(frozen=True)
class CodexExecResult:
    provider_result: _execution.ProviderAdapterResult
    usage_v1: Dict[str, Any]
    raw_observation: Dict[str, Any]
    cleanup_receipt: Dict[str, Any]
    argv: List[str]
    stdout: str
    stderr: str
    final_output: str
    report_surface: Dict[str, Any]


class _DefaultProcessTree:
    """Small process-group helper used only outside fake-process tests."""

    def signal_group(self, pgid: int, sig: int) -> None:
        os.killpg(pgid, sig)

    def audit_empty(self, pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def receipt(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "pid": kwargs["pid"],
            "pgid": kwargs["pgid"],
            "process_tree": [kwargs["pid"]],
            "descendants_exited": self.audit_empty(kwargs["pgid"]),
            "signals": [],
        }


class CodexExecAdapter:
    """Execute one frozen Codex request through an argv-only boundary."""

    def __init__(self, *, cli_path: str = "/opt/homebrew/bin/codex",
                 popen_factory: Any = subprocess.Popen, ledger: Any,
                 containment_probe: Any, process_tree: Any = None,
                 redaction_patterns: Optional[Iterable[str]] = None,
                 test_mode: bool = False, argv_probe: Any = None) -> None:
        self.cli_path = cli_path
        self.popen_factory = popen_factory
        self.ledger = ledger
        self.containment_probe = containment_probe
        self.process_tree = process_tree or _DefaultProcessTree()
        self.test_mode = test_mode
        # Injectable real-binary argv-acceptance seam, independent of popen_factory
        # (deliberately NOT reused: popen_factory's fakes are call-count/side-effect
        # sensitive -- e.g. a smoke fake process that writes the output-last-message
        # file as a side effect of .communicate() -- so probing through it here would
        # spuriously trip the "file preexisted the provider process" smoke check and
        # break currently-passing tests). None (the default) is a no-op; only
        # `_run_production` (in codex_subscription_pilot.py) wires a real probe.
        self.argv_probe = argv_probe
        default_patterns = (
            r"(?i)authorization\s*:\s*(?:bearer\s+)?[^\s,;\"']+",
            r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token)"
            r"\s*[:=]\s*(?:bearer\s+)?[^\s,;\"']+",
            r"\bsk-[A-Za-z0-9._-]+\b",
        )
        self.redaction_patterns = [
            re.compile(pattern) for pattern in (*default_patterns, *(redaction_patterns or ()))
        ]

    def execute(self, request: CodexExecRequest) -> CodexExecResult:
        argv: List[str] = []
        base_observation: Dict[str, Any] = {
            "approval_hash": request.approval_hash,
            "manifest_hash": request.manifest_hash,
            "requested_model": request.requested_model,
            "requested_effort": request.requested_effort,
            "argv": [],
            "events": [],
        }
        reservation_id: Optional[str] = None
        process = None
        cleanup: Optional[Dict[str, Any]] = None
        started = time.monotonic()
        observed_total: Optional[int] = None
        stdout: Any = ""
        stderr: Any = ""
        final_output = ""
        pending_result: Optional[CodexExecResult] = None
        primary_error: Optional[BaseException] = None
        input_receipt: Dict[str, Any] = {}
        reservation_receipt: Optional[Dict[str, Any]] = None
        try:
            input_receipt = self._validate_request(request, base_observation)
            base_observation["input_receipt"] = input_receipt
            self._validate_smoke_output_precondition(request, base_observation)
            base_observation["protected_root_snapshots"] = {
                "before": self._snapshot_protected_roots(request.protected_roots),
            }
            argv = self._argv(request)
            base_observation["argv"] = argv
            containment = self._probe_containment(request, argv, base_observation)
            reservation = self._reserve(request, base_observation)
            reservation_id = reservation.get("reservation_id")
            if not isinstance(reservation_id, str) or not reservation_id:
                self._block("ledger returned no reservation id", base_observation)

            started_reservation = self.ledger.start(reservation_id)
            reservation_receipt = {
                "reservation_id": reservation_id,
                "reserve": reservation,
                "start": started_reservation,
                "status": "NETWORK_IN_FLIGHT",
            }
            base_observation["reservation_receipt"] = reservation_receipt
            process = self.popen_factory(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=request.clone_path, shell=False,
                start_new_session=True, text=True,
                env=dict(request.frozen_packet["environment"]),
            )
            try:
                stdout, stderr = process.communicate(
                    input=request.prompt, timeout=request.timeout_seconds)
            except (subprocess.TimeoutExpired, TimeoutError):
                stdout = getattr(process, "stdout", "")
                stderr = getattr(process, "stderr", "")
                cleanup = self._timeout_cleanup(process, request, containment, argv)
                cleanup.update({
                    "input_hashes": input_receipt["input_hashes"],
                    "input_receipt_hash": input_receipt["receipt_hash"],
                })
                base_observation["cleanup"] = cleanup
                self._validate_protected_root_snapshots(request, base_observation)
                self._block("Codex process timed out", base_observation)

            cleanup = self._normal_cleanup(process, containment, argv, request)
            cleanup.update({
                "input_hashes": input_receipt["input_hashes"],
                "input_receipt_hash": input_receipt["receipt_hash"],
            })
            base_observation["cleanup"] = cleanup
            self._validate_protected_root_snapshots(request, base_observation)
            if getattr(process, "returncode", None) != 0:
                self._block("Codex process exited nonzero", base_observation)
            parsed = self._parse_jsonl(stdout, request, base_observation)
            output_last_message = self._validate_smoke_output_file(
                request, parsed["final_output"], base_observation,
            )
            if output_last_message is not None:
                parsed["output_last_message"] = output_last_message
            observed_total = parsed["observed_total_tokens"]
            final_output = parsed["final_output"]
            observation = dict(base_observation)
            observation.update(parsed)
            observation.update({
                "stdout": stdout,
                "stderr": stderr,
                "final_output_hash": self._hash(parsed["final_output"]),
            })
            observation = self._redact(observation)
            observation_id = "codex-jsonl-" + self._hash(observation)[:24]
            payload_bytes = self._canonical_bytes(observation)
            payload_hash = hashlib.sha256(payload_bytes).hexdigest()
            provider = _execution.ProviderAdapterResult(
                response_text=observation["final_output"],
                canonical_sdk_response_id=observation.get("response_id"),
                canonical_sdk_request_id=observation.get("request_id"),
                raw_usage=observation["usage"],
                raw_response_payload_hash=payload_hash,
                raw_observation_id=observation_id,
                input_hashes=input_receipt["input_hashes"],
                input_receipt_hash=input_receipt["receipt_hash"],
                raw_response_payload_bytes=payload_bytes,
            )
            usage = _execution.normalize_provider_result(
                provider, "codex-exec-" + observation_id[-12:],
                "codex-dispatch-" + observation_id[-12:], "codex_subscription",
                provider="openai", requested_model=request.requested_model,
                resolved_model_id=observation["configured_model_id"],
                requested_effort=request.requested_effort,
                actual_effort=observation["configured_reasoning_effort"],
            )
            _execution._set_envelope_field(
                usage, "billing_authority",
                "unavailable_subscription_no_usd_billing_authority",
            )
            usage["promotion_eligible"] = False
            _execution.validate_usage_v1(usage)
            pending_result = CodexExecResult(
                provider_result=provider, usage_v1=usage, raw_observation=observation,
                cleanup_receipt=cleanup, argv=argv, stdout=self._redact(stdout),
                stderr=self._redact(stderr), final_output=observation["final_output"],
                report_surface={
                    "observation_id": observation_id,
                    "final_output_hash": observation["final_output_hash"],
                    "configured_model_id": observation["configured_model_id"],
                    "configured_reasoning_effort": observation["configured_reasoning_effort"],
                    "observed_total_tokens": observation["observed_total_tokens"],
                    "provider_reported_total_tokens": observation[
                        "provider_reported_total_tokens"],
                    "input_hashes": input_receipt["input_hashes"],
                    "input_receipt_hash": input_receipt["receipt_hash"],
                    "pace_status": PROMOTION_BOUNDARY,
                    "promotion_eligible": False,
                    "integration_applied": False,
                    "usd_cost": None,
                    "reservation_receipt": reservation_receipt,
                },
            )
        except CodexAdapterBlockedError as exc:
            primary_error = exc
        except Exception as exc:
            primary_error = CodexAdapterBlockedError(
                "Codex adapter failure: %s" % type(exc).__name__, self._redact(base_observation)
            )
        finally:
            if process is not None:
                if not stdout:
                    stdout = getattr(process, "stdout", "")
                if not stderr:
                    stderr = getattr(process, "stderr", "")
            reconcile_error: Optional[BaseException] = None
            if reservation_id:
                actual = {
                    "elapsed_seconds": max(0, int(time.monotonic() - started)),
                    "observed_total_tokens": observed_total,
                }
                try:
                    reconciled = self.ledger.reconcile(
                        reservation_id, "codex-observation", actual,
                    )
                    if reservation_receipt is not None:
                        reservation_receipt["reconcile"] = reconciled
                        reservation_receipt["actual"] = actual
                        reservation_receipt["status"] = "RECONCILED"
                        base_observation["reservation_receipt"] = reservation_receipt
                        if pending_result is not None:
                            pending_result.report_surface[
                                "reservation_receipt"] = reservation_receipt
                except Exception as exc:
                    reconcile_error = CodexAdapterBlockedError(
                        "cap reconciliation failed: %s" % type(exc).__name__,
                        self._redact(base_observation),
                    )
            retention_observation = dict(base_observation)
            if pending_result is not None:
                retention_observation = pending_result.raw_observation
                final_output = pending_result.final_output
            elif isinstance(primary_error, CodexAdapterBlockedError):
                retention_observation.update(primary_error.observation)
            retention_observation.setdefault("final_output", final_output)
            retention_observation.setdefault("stdout", stdout)
            retention_observation.setdefault("stderr", stderr)
            try:
                self._retain_artifacts(
                    request, self._redact(retention_observation), stdout, stderr,
                    final_output=final_output,
                )
            except Exception as exc:
                if primary_error is None and reconcile_error is None:
                    primary_error = CodexAdapterBlockedError(
                        "artifact retention failed: %s" % type(exc).__name__,
                        self._redact(retention_observation),
                    )
            if reconcile_error is not None:
                primary_error = reconcile_error
        if primary_error is not None:
            raise primary_error
        if pending_result is None:
            raise CodexAdapterBlockedError(
                "Codex adapter produced no result", self._redact(base_observation)
            )
        return pending_result

    def _validate_request(self, request: CodexExecRequest,
                          observation: Dict[str, Any]) -> Dict[str, Any]:
        if request.requested_effort not in SUPPORTED_REASONING_EFFORTS:
            self._block("unsupported Codex 0.41.0 reasoning effort", observation)
        strings = (request.prompt, request.clone_path, request.artifact_dir,
                   request.output_last_message_path, request.requested_model,
                   request.requested_effort, request.approval_hash,
                   request.manifest_hash)
        if any(not isinstance(value, str) or not value for value in strings):
            self._block("invalid sealed request", observation)
        packet = request.frozen_packet
        if not isinstance(packet, dict) or not isinstance(packet.get("packet_hash"), str) or not isinstance(
                packet.get("clone_tree_hash"), str):
            self._block("missing frozen packet identity", observation)
        self._validate_smoke_request(request, observation)
        hash_values = (
            request.approval_hash, request.manifest_hash,
            packet.get("packet_hash"), packet.get("reverified_packet_hash"),
            packet.get("clone_tree_hash"), packet.get("reverified_clone_tree_hash"),
        )
        if any(not self._is_sha256(value) for value in hash_values):
            self._block("request or packet contains an invalid SHA-256", observation)
        authority = packet.get("immutable_authority")
        if not isinstance(authority, dict) or authority.get("schema") != "user_confirmation.v1":
            self._block("exact immutable human authority is required", observation)
        authority_fields = {
            "schema", "spec_sha256", "approval_hash", "manifest_hash", "packet_hash",
            "caps", "requested_model", "requested_effort", "baseline_hashes",
            "promotion_boundary", "confirmed",
        }
        if set(authority) != authority_fields:
            self._block("immutable authority fields differ from the exact contract", observation)
        hash_fields = ("spec_sha256", "approval_hash", "manifest_hash", "packet_hash")
        if any(not self._is_sha256(authority.get(field)) for field in hash_fields):
            self._block("immutable authority contains an invalid hash", observation)
        if authority.get("confirmed") is not True or authority.get(
                "spec_sha256") != SPEC_SHA256:
            self._block("immutable authority is not the confirmed pinned spec", observation)
        if authority.get("approval_hash") != request.approval_hash or authority.get(
                "manifest_hash") != request.manifest_hash or authority.get(
                    "packet_hash") != packet.get("packet_hash"):
            self._block("immutable authority does not bind request seals", observation)
        if authority.get("caps") != EXACT_CAPS or authority.get(
                "requested_model") != request.requested_model or authority.get(
                    "requested_effort") != request.requested_effort:
            self._block("immutable authority does not bind caps/model/effort", observation)
        baselines = authority.get("baseline_hashes")
        if not isinstance(baselines, dict) or set(baselines) != {"source", "clone_tree"} or any(
                not self._is_sha256(value) for value in baselines.values()) or baselines.get(
                    "clone_tree") != packet.get("clone_tree_hash"):
            self._block("immutable authority does not bind exact baseline hashes", observation)
        if authority.get("promotion_boundary") != PROMOTION_BOUNDARY:
            self._block("immutable authority permits promotion", observation)
        self._validate_canonical_paths(request, observation)
        input_receipt = self._validate_materials_and_trees(request, observation)
        actual_packet_hash = canonical_packet_hash(packet)
        if packet["packet_hash"] != actual_packet_hash or packet[
                "reverified_packet_hash"] != actual_packet_hash:
            self._block("frozen packet hash is not bound to canonical packet bytes", observation)
        input_receipt["input_hashes"]["packet"] = actual_packet_hash
        input_receipt["receipt_hash"] = canonical_hash(input_receipt["input_hashes"])
        return input_receipt

    def _validate_smoke_request(self, request: CodexExecRequest,
                                observation: Dict[str, Any]) -> None:
        packet = request.frozen_packet
        identity = packet.get("task_identity")
        if not isinstance(identity, dict) or identity.get("role") != "smoke":
            return
        cwd = request.clone_path
        if identity != {"ordinal": 0, "case_id": "smoke", "role": "smoke"} or not isinstance(
                cwd, str) or Path(cwd).parent != Path("/private/tmp") or not Path(
                    cwd).name.startswith("codex-product-pilot-smoke-"):
            self._block("smoke cwd or task identity is not the sealed fresh contract", observation)
        expected_prompt = (
            "Return exactly CODEX_SMOKE_OK. Do not use tools, run commands, edit files, "
            "or contact external services.\n"
        )
        if request.prompt != expected_prompt:
            self._block("smoke prompt is not the sealed no-tools exact-output prompt", observation)
        if packet.get("execution_sandbox") != "read-only":
            self._block("smoke sandbox must be read-only", observation)
        if packet.get("approval_policy") != "never":
            self._block("smoke approval must be never", observation)
        if packet.get("expected_final_output") != "CODEX_SMOKE_OK":
            self._block("smoke output must be exactly CODEX_SMOKE_OK", observation)
        if packet.get("forbid_tool_events") is not True:
            self._block("smoke must forbid every tool event", observation)
        if packet.get("forbid_edits") is not True or packet.get(
                "allowed_write_targets") != []:
            self._block("smoke must forbid every edit and write target", observation)
        if packet.get("smoke_prompt_policy") != "read-only-no-tools-no-edits-exact-output":
            self._block("smoke policy is not the sealed exact contract", observation)
        argv = self._argv(request)
        if "--skip-git-repo-check" not in argv or "--full-auto" in argv:
            self._block("smoke argv must skip git without enabling full-auto", observation)
        for flag, expected in (("--sandbox", "read-only"),
                               ("--ask-for-approval", "never")):
            if flag not in argv or argv.index(flag) + 1 >= len(argv) or argv[
                    argv.index(flag) + 1] != expected:
                self._block("smoke argv differs from the sealed contract", observation)
        self._validate_smoke_argv_accepted_by_installed_codex(argv, observation)

    def _validate_smoke_argv_accepted_by_installed_codex(
            self, argv: List[str], observation: Dict[str, Any]) -> None:
        """Confirm the frozen smoke argv this request would actually spawn is
        genuinely accepted by the installed codex binary -- not merely self-
        consistent with the `--sandbox`/`--ask-for-approval` presence-and-position
        check just above (that check never verified position relative to `exec`, so
        it would not have caught the `--ask-for-approval`-after-`exec` ordering bug
        even in principle).

        Deliberately a no-op unless `self.argv_probe` was injected at construction.
        Not gated on `self.test_mode` -- kept symmetric with the sibling check in
        `CodexSubscriptionPilot._validate_smoke_argv_accepted_by_installed_codex`
        (see that method's docstring for why `test_mode` alone is not a safe gate)
        and, independently, deliberately NOT threaded through `self.popen_factory`
        (see `__init__`'s comment) to avoid any risk of a double-invocation side
        effect on fakes designed for exactly one call. Only `_run_production` wires
        a real probe (`_real_codex_argv_probe`) explicitly.
        """
        if self.argv_probe is None:
            return
        returncode = self.argv_probe(list(argv))
        if returncode != 0:
            self._block(
                "smoke argv is rejected by the installed codex binary (exit %r)" % (returncode,),
                observation,
            )

    @staticmethod
    def _real_codex_argv_probe(argv: List[str]) -> int:
        """Run `argv` against the real installed codex binary and return its exit
        code, with the trailing stdin-prompt marker ("-") replaced by `--help` (or,
        if absent, `--help` appended) so the process can never dispatch real work.
        Empirically confirmed (see the governing spec's Context section and AC4's
        dedicated regression test) that `--help` short-circuits before any model or
        network activity for this builder's complete real flag set."""
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

    def _validate_smoke_output_precondition(
            self, request: CodexExecRequest, observation: Dict[str, Any]) -> None:
        if request.frozen_packet.get("task_identity", {}).get("role") != "smoke":
            return
        output_path = Path(request.output_last_message_path)
        if not self._within(str(output_path), (request.artifact_dir,)):
            self._block("smoke output-last-message file escaped its artifact root", observation)
        if output_path.exists() or output_path.is_symlink():
            self._block("smoke output-last-message file preexisted the provider process", observation)

    def _validate_smoke_output_file(
            self, request: CodexExecRequest, jsonl_final: str,
            observation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if request.frozen_packet.get("task_identity", {}).get("role") != "smoke":
            return None
        output_path = Path(request.output_last_message_path)
        try:
            if output_path.is_symlink() or not output_path.is_file():
                raise OSError("provider output is missing")
            output_bytes = output_path.read_bytes()
        except OSError:
            self._block("smoke output-last-message file was not created", observation)
        exact = output_bytes == b"CODEX_SMOKE_OK"
        matches_jsonl = exact and jsonl_final == "CODEX_SMOKE_OK"
        receipt = {
            "path": str(output_path),
            "existed_before": False,
            "created_by_process": True,
            "bytes_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "exact_bytes": exact,
            "matches_jsonl_final": matches_jsonl,
        }
        if not exact or not matches_jsonl:
            observation["output_last_message"] = receipt
            self._block("smoke final file violates the exact-output contract", observation)
        return receipt

    @staticmethod
    def _is_sha256(value: Any) -> bool:
        return is_sha256(value)

    @staticmethod
    def _canonical_bytes(value: Any) -> bytes:
        return canonical_bytes(value)

    @classmethod
    def _canonical_packet_hash(cls, packet: Dict[str, Any]) -> str:
        return canonical_packet_hash(packet)

    def _validate_materials_and_trees(self, request: CodexExecRequest,
                                      observation: Dict[str, Any]) -> Dict[str, Any]:
        packet = request.frozen_packet
        materials = packet.get("sealed_materials")
        if not isinstance(materials, dict) or set(materials) != set(REQUIRED_MATERIALS):
            self._block("deep frozen packet materials are required", observation)
        allowed_files = packet.get("allowed_files")
        if allowed_files is None:
            allowed_files = [material.get("path") for material in materials.values()
                             if isinstance(material, dict)]
        if not isinstance(allowed_files, list) or any(
                not isinstance(path, str) for path in allowed_files):
            self._block("sealed allowed-file list is invalid", observation)
        actual_material_hashes: Dict[str, str] = {}
        for name in REQUIRED_MATERIALS:
            material = materials[name]
            valid_fields = ({"path", "sha256"}, {"path", "sha256", "content"})
            if not isinstance(material, dict) or set(material) not in valid_fields or (
                    "content" in material and not self.test_mode):
                self._block("sealed material descriptor is invalid", observation)
            path = material.get("path")
            claimed = material.get("sha256")
            if not self._is_canonical_absolute_path(path) or not self._is_sha256(claimed):
                self._block("sealed material path or hash is invalid", observation)
            try:
                if Path(path).is_file():
                    material_bytes = Path(path).read_bytes()
                elif self.test_mode and isinstance(material.get("content"), str):
                    material_bytes = material["content"].encode("utf-8")
                else:
                    raise OSError("material unavailable")
            except OSError:
                self._block("sealed material bytes are unavailable", observation)
            actual = hashlib.sha256(material_bytes).hexdigest()
            if actual != claimed:
                self._block("sealed material bytes changed: " + name, observation)
            if path not in allowed_files:
                self._block("sealed material is absent from allowed-file list", observation)
            if name == "prompt" and material_bytes != request.prompt.encode("utf-8"):
                self._block("request prompt differs from sealed prompt bytes", observation)
            actual_material_hashes[name] = actual

        baseline_hash = packet.get("baseline_tree_hash")
        source_hash = packet.get("source_tree_hash")
        if not self._is_sha256(baseline_hash) or not self._is_sha256(source_hash):
            self._block("baseline/source tree hash is invalid", observation)
        actual_tree_hash = self._resolve_tree_hash(
            request.clone_path, packet.get("clone_tree_entries"), observation,
        )
        actual_source_hash = self._resolve_tree_hash(
            packet.get("source_root"), packet.get("source_tree_entries"), observation,
        )
        authority_hashes = packet["immutable_authority"]["baseline_hashes"]
        if (
                packet["clone_tree_hash"] != actual_tree_hash
                or packet["reverified_clone_tree_hash"] != actual_tree_hash
                or baseline_hash != actual_tree_hash
                or authority_hashes.get("clone_tree") != actual_tree_hash
                or source_hash != actual_source_hash
                or authority_hashes.get("source") != actual_source_hash):
            self._block("baseline or clone tree identity is not bound to sealed paths", observation)
        task = packet.get("task_identity")
        if not isinstance(task, dict) or set(task) != {"ordinal", "case_id", "role"} or type(
                task.get("ordinal")) is not int or task["ordinal"] < 0 or any(
                    not isinstance(task.get(field), str) or not task[field]
                    for field in ("case_id", "role")):
            self._block("ordered task identity is missing", observation)
        input_hashes = dict(actual_material_hashes)
        input_hashes.update({"clone_tree": actual_tree_hash, "source_tree": actual_source_hash})
        return {"input_hashes": input_hashes}

    def _resolve_tree_hash(self, root: Any, deterministic_entries: Any,
                           observation: Dict[str, Any]) -> str:
        try:
            if self.test_mode:
                return deterministic_tree_hash(deterministic_entries)
            if isinstance(root, str) and Path(root).exists():
                return self._canonical_tree_hash([root])
        except (OSError, ValueError):
            pass
        self._block("sealed tree bytes are unavailable", observation)

    @classmethod
    def _canonical_tree_hash(cls, roots: Iterable[str]) -> str:
        entries: List[Dict[str, Any]] = []
        for root_text in sorted(set(roots)):
            root = Path(root_text)
            if not root.exists() or root.is_symlink():
                raise ValueError("sealed tree root is unavailable or symlinked")
            paths = [root]
            if root.is_dir():
                paths.extend(sorted(root.rglob("*"), key=lambda item: item.as_posix()))
            for path in paths:
                relative = "." if path == root else path.relative_to(root).as_posix()
                stat_result = path.lstat()
                entry: Dict[str, Any] = {
                    "root": root.as_posix(), "path": relative,
                    "mode": stat_result.st_mode & 0o7777,
                }
                if path.is_symlink():
                    entry.update({"type": "symlink", "target": os.readlink(path)})
                elif path.is_dir():
                    entry.update({"type": "directory", "size": 0})
                elif path.is_file():
                    content = path.read_bytes()
                    entry.update({
                        "type": "file", "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    })
                else:
                    raise ValueError("sealed tree contains unsupported file type")
                entries.append(entry)
        return hashlib.sha256(cls._canonical_bytes(entries)).hexdigest()

    def _validate_canonical_paths(self, request: CodexExecRequest,
                                  observation: Dict[str, Any]) -> None:
        packet = request.frozen_packet
        clone = request.clone_path
        artifact = request.artifact_dir
        roots = [clone, artifact]
        if packet.get("cwd") != clone or packet.get("artifact_root") != artifact:
            self._block("request cwd/artifact root differs from frozen packet", observation)
        if packet.get("writable_roots") != roots:
            self._block("packet writable roots are not exactly clone and artifact", observation)
        paths = {
            "clone": clone,
            "artifact": artifact,
            "request_final": request.output_last_message_path,
            "stdout": packet.get("stdout_path"),
            "stderr": packet.get("stderr_path"),
            "final": packet.get("final_path"),
            "events": packet.get("events_path"),
        }
        if packet.get("final_path") != request.output_last_message_path:
            self._block("request final path differs from frozen packet", observation)
        for label, path in paths.items():
            if not self._is_canonical_absolute_path(path):
                self._block(label + " path is not canonical", observation)
        if clone == artifact or self._within(clone, (artifact,)) or self._within(artifact, (clone,)):
            self._block("clone and artifact roots must be distinct", observation)
        for work_root in roots:
            if self._within(work_root, ProductionSeatbeltPreflight.DEFAULT_PROTECTED_ROOTS):
                self._block("work root is equal to or inside a canonical protected root", observation)
        for label in ("request_final", "stdout", "stderr", "final", "events"):
            if not self._within(paths[label], (artifact,)):
                self._block(label + " path escaped artifact root", observation)
        for target in packet.get("allowed_write_targets", []):
            if not self._is_canonical_absolute_path(target) or not self._within(target, roots):
                self._block("allowed write target escaped canonical roots", observation)
        environment = packet.get("environment")
        if not isinstance(environment, dict) or any(
                not isinstance(key, str) or not key or not isinstance(value, str)
                for key, value in environment.items()):
            self._block("frozen environment is invalid", observation)
        ordered_argv = packet.get("ordered_argv")
        if not isinstance(ordered_argv, list) or not ordered_argv or any(
                not self._is_semantically_local_argv(argv) for argv in ordered_argv):
            self._block("frozen ordered argv policy is invalid", observation)

    @staticmethod
    def _is_canonical_absolute_path(path: Any) -> bool:
        if not isinstance(path, str) or not path or not os.path.isabs(path):
            return False
        if Path(path).parts.count("..") or os.path.normpath(path) != path:
            return False
        current = Path(path)
        while True:
            if current.is_symlink():
                return False
            if current.parent == current:
                break
            current = current.parent
        return os.path.realpath(path) == path

    def _argv(self, request: CodexExecRequest) -> List[str]:
        role = request.frozen_packet.get("task_identity", {}).get("role")
        smoke = role == "smoke"
        read_only = role in {"smoke", "planner"}
        argv = [
            self.cli_path, "--ask-for-approval", "never", "exec", "--cd", request.clone_path, "--model",
            request.requested_model, "--sandbox", "read-only" if read_only else "workspace-write",
            "-c",
            "model_reasoning_effort=" + request.requested_effort,
        ]
        if smoke:
            argv.append("--skip-git-repo-check")
        argv.extend([
            "--json", "--output-last-message", request.output_last_message_path, "-",
        ])
        return argv

    @staticmethod
    def smoke_contract(request: CodexExecRequest) -> Dict[str, Any]:
        """Return the sealed read-only/no-tools contract for the pilot smoke."""
        return {
            "cwd": "/private/tmp/codex-product-pilot-smoke-" + str(uuid.uuid4()),
            "sandbox": "read-only",
            "approval": "never",
            "skip_git_repo_check": True,
            "forbid_tool_events": True,
            "expected_final_output": "CODEX_SMOKE_OK",
            "possible_codex_state_disclosure": (
                "codex-cli-0.41.0-has-no-ephemeral-and-may-write-under-~/.codex"
            ),
            "requested_model": request.requested_model,
            "requested_effort": request.requested_effort,
        }

    def _probe_containment(self, request: CodexExecRequest, argv: List[str],
                           observation: Dict[str, Any]) -> Dict[str, Any]:
        trusted_production = type(self.containment_probe) is TrustedProductionContainment
        if not trusted_production and not self.test_mode:
            self._block("untrusted injected containment cannot authorize execution", observation)
        if self.test_mode and (
                self.popen_factory is subprocess.Popen
                or self.cli_path == "/opt/homebrew/bin/codex"):
            self._block("test mode cannot authorize a provider process", observation)
        probe_kwargs = {
            "argv": argv,
            "cwd": request.clone_path,
            "writable_roots": [request.clone_path, request.artifact_dir],
            "protected_roots": list(request.protected_roots),
            "environment": request.frozen_packet.get("environment", {}),
            "slot_id": "%s-%s" % (
                request.frozen_packet.get("task_identity", {}).get("role"),
                request.frozen_packet.get("task_identity", {}).get("ordinal"),
            ),
            "model": request.requested_model,
            "effort": request.requested_effort,
            "sandbox": argv[argv.index("--sandbox") + 1],
        }
        try:
            receipt = self.containment_probe.probe(**probe_kwargs)
        except Exception:
            receipt = None
        if not isinstance(receipt, dict) or receipt.get("os_enforced") is not True or not receipt.get(
                "mechanism") or not receipt.get("version") or not self._is_sha256(
                    receipt.get("policy_hash")):
            self._block("OS-enforced containment receipt is required", observation)
        if trusted_production and not TrustedProductionContainment.verify(receipt, **probe_kwargs):
            self._block("containment identity attestation is invalid", observation)
        policy_bytes = receipt.get("policy_bytes")
        policy_path = receipt.get("policy_path")
        if policy_bytes is None and isinstance(policy_path, str):
            try:
                policy_bytes = Path(policy_path).read_bytes()
            except OSError:
                policy_bytes = None
        if isinstance(policy_bytes, str):
            policy_bytes = policy_bytes.encode("utf-8")
        if not isinstance(policy_bytes, bytes) or hashlib.sha256(policy_bytes).hexdigest() != receipt[
                "policy_hash"]:
            self._block("containment policy hash does not bind actual policy bytes", observation)
        roots = receipt.get("writable_roots")
        if not isinstance(roots, list) or not roots or not all(isinstance(root, str) for root in roots):
            self._block("containment receipt has no writable-root evidence", observation)
        bound_roots = receipt.get("bound_request_writable_roots")
        expected_roots = [request.clone_path, request.artifact_dir]
        if request.frozen_packet.get("immutable_authority") is not None:
            if roots != expected_roots or bound_roots != expected_roots:
                self._block("containment roots differ from exact canonical sealed roots", observation)
        elif bound_roots is not None and set(bound_roots) != set(expected_roots):
            self._block("containment request-bound roots differ from the sealed roots", observation)
        if receipt.get("filesystem_violations") or receipt.get("network_attempts") or receipt.get(
                "protected_root_changes"):
            self._block("containment reported a policy violation", observation)
        return receipt

    def _reserve(self, request: CodexExecRequest, observation: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.ledger.reserve(
                request.manifest_hash + ":" + request.approval_hash,
                {"calls": 1, "seconds": request.timeout_seconds,
                 "observed_total_tokens": 150000,
                 "subscription_allowance_units": 1},
            )
        except Exception as exc:
            self._block("cap reservation failed: %s" % type(exc).__name__, observation)

    def _parse_jsonl(self, stdout: Any, request: CodexExecRequest,
                     observation: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "strict")
        if not isinstance(stdout, str):
            self._block("Codex stdout is not text JSONL", observation)
        completed: List[Dict[str, Any]] = []
        configured: Optional[Dict[str, Any]] = None
        session_id = None
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (TypeError, ValueError):
                self._block("Codex stdout contains invalid JSONL", observation)
            if not isinstance(record, dict):
                self._block("Codex JSONL event is structurally invalid", observation)
            msg = record.get("msg")
            if isinstance(msg, dict) and msg.get("type") == "token_count":
                completed.append({"schema": "installed_token_count", "record": record})
                continue
            event_type = record.get("type")
            if not isinstance(event_type, str):
                self._block("Codex JSONL event is structurally invalid", observation)
            if event_type == "session.started":
                session_id = record.get("session_id")
                continue
            if event_type == "session_configured":
                if configured is not None and configured != record:
                    self._block("Codex JSONL has conflicting session identity", observation)
                configured = record
                session_id = record.get("session_id", session_id)
                continue
            if event_type == "turn.completed":
                completed.append({"schema": "turn_completed", "record": record})
                continue
            event = self._classify_event(record, request)
            observation["events"].append(event)
            if event["class"] != "ALLOWED_LOCAL":
                self._block("terminal Codex event: " + event["reason"], observation)
        if len(completed) != 1:
            self._block("Codex JSONL needs exactly one terminal usage record", observation)
        completion = completed[0]
        terminal = completion["record"]
        schema = completion["schema"]
        if schema == "installed_token_count":
            msg = terminal["msg"]
            info = msg.get("info")
            if not isinstance(info, dict) or not isinstance(info.get("total_token_usage"), dict):
                observation.update({
                    "configured_model_id": "UNKNOWN",
                    "configured_reasoning_effort": "UNKNOWN",
                    "usage": "UNKNOWN",
                })
                self._block("Codex installed telemetry is UNKNOWN", observation)
            usage = dict(info["total_token_usage"])
            last_usage = info.get("last_token_usage")
            if last_usage is not None and not isinstance(last_usage, dict):
                self._block("Codex last-token usage is malformed", observation)
            rate_limits = msg.get("rate_limits")
            final_output = terminal.get("final_output")
            response_id = terminal.get("response_id")
            request_id = terminal.get("request_id")
        else:
            usage = terminal.get("usage")
            last_usage = None
            rate_limits = terminal.get("rate_limit_observation")
            final_output = terminal.get("final_output")
            response_id = terminal.get("response_id")
            request_id = terminal.get("request_id")

        configured_model = configured.get("model") if configured else terminal.get(
            "resolved_model_id")
        configured_effort = configured.get("reasoning_effort") if configured else terminal.get(
            "actual_effort")
        if configured is not None:
            terminal_model = terminal.get("resolved_model_id")
            terminal_effort = terminal.get("actual_effort")
            if terminal_model is not None and terminal_model != configured_model:
                self._block("terminal model conflicts with session_configured identity", observation)
            if terminal_effort is not None and terminal_effort != configured_effort:
                self._block("terminal effort conflicts with session_configured identity", observation)
        sandbox = (configured or terminal).get("sandbox_mode_evidence")
        approval = (configured or terminal).get("no_escalation_approval_evidence")
        if not isinstance(configured_model, str) or not configured_model or not isinstance(
                configured_effort, str) or not configured_effort:
            observation.update({
                "configured_model_id": "UNKNOWN",
                "configured_reasoning_effort": "UNKNOWN",
                "usage": usage if isinstance(usage, dict) else "UNKNOWN",
            })
            self._block("Codex configured identity is UNKNOWN", observation)
        if not isinstance(sandbox, dict) or sandbox.get("os_enforced") is not True or not isinstance(
                approval, dict) or approval.get("accepted") is not True:
            self._block("Codex terminal containment evidence is insufficient", observation)
        if not isinstance(usage, dict) or not isinstance(final_output, str):
            observation["usage"] = "UNKNOWN"
            self._block("Codex terminal usage or final output is invalid", observation)
        observed_total = self._validate_usage(usage, observation)
        strict = request.frozen_packet.get("immutable_authority") is not None
        role = request.frozen_packet.get("task_identity", {}).get("role")
        actual_smoke = role == "smoke" and request.clone_path.startswith(
            "/private/tmp/codex-product-pilot-smoke-"
        )
        expected_sandbox = request.frozen_packet.get(
            "execution_sandbox", "read-only" if actual_smoke else "workspace-write",
        )
        if strict and (
                configured_model != request.requested_model
                or configured_effort != request.requested_effort
                or sandbox != {"mode": expected_sandbox, "os_enforced": True}
                or approval != {"mode": "never", "accepted": True}
                or ("cwd" in terminal and terminal.get("cwd") != request.clone_path)
                or any(event.get("cwd") != request.clone_path for event in observation["events"])):
            self._block("Codex terminal evidence differs from the sealed request", observation)
        if actual_smoke and (observation["events"] or final_output != "CODEX_SMOKE_OK"):
            self._block("Codex smoke violated its no-tools or exact-output contract", observation)
        provider_total = usage.get("total_tokens")
        return {
            "session_id": session_id,
            "response_id": response_id,
            "request_id": request_id,
            "configured_model_id": configured_model,
            "configured_reasoning_effort": configured_effort,
            "resolved_model_id": configured_model,
            "actual_effort": configured_effort,
            "identity_sources": {
                "model": "$.session_configured.model" if configured else "$.turn.completed.resolved_model_id",
                "effort": "$.session_configured.reasoning_effort" if configured else "$.turn.completed.actual_effort",
            },
            "sandbox_mode_evidence": sandbox,
            "no_escalation_approval_evidence": approval,
            "rate_limit_observation": rate_limits,
            "usage": usage,
            "last_token_usage": last_usage,
            "usage_schema": schema,
            "observed_total_tokens": observed_total,
            "provider_reported_total_tokens": provider_total,
            "final_output": final_output,
        }

    def _validate_usage(self, usage: Dict[str, Any],
                        observation: Dict[str, Any]) -> int:
        component_fields = {
            "input_tokens", "cached_input_tokens", "output_tokens",
            "reasoning_output_tokens",
        }
        allowed_fields = component_fields | {"total_tokens"}
        if set(usage) not in (component_fields, allowed_fields) or any(
                type(usage.get(field)) is not int or usage[field] < 0 for field in usage):
            self._block("Codex usage requires exact nonnegative integer fields", observation)
        if usage["cached_input_tokens"] > usage["input_tokens"]:
            self._block("cached input tokens exceed input tokens", observation)
        if usage["reasoning_output_tokens"] > usage["output_tokens"]:
            self._block("reasoning output tokens exceed output tokens", observation)
        observed_total = usage["input_tokens"] + usage["output_tokens"]
        if "total_tokens" in usage and usage["total_tokens"] != observed_total:
            self._block("provider total tokens fail direct arithmetic", observation)
        return observed_total

    def _classify_event(self, record: Dict[str, Any], request: CodexExecRequest) -> Dict[str, Any]:
        event_type = record["type"]
        argv = record.get("effective_argv", record.get("argv", []))
        cwd = record.get("cwd")
        writes = record.get("write_targets", [])
        event = {"type": event_type, "effective_argv": argv, "cwd": cwd,
                 "write_targets": writes, "class": "TERMINAL", "reason": "unknown event"}
        if request.frozen_packet.get("task_identity", {}).get("role") == "smoke" and request.clone_path.startswith(
                "/private/tmp/codex-product-pilot-smoke-"):
            event["reason"] = "smoke forbids every tool event"
            return event
        terminal_words = ("child", "delegat", "remote", "network", "approval", "escalation",
                          "privilege", "sandbox")
        if any(word in event_type.lower() for word in terminal_words):
            event["reason"] = "terminal event type " + event_type
            return event
        if event_type not in ("local_command", "local_file_read", "local_file_write", "local_test"):
            return event
        packet = request.frozen_packet
        if not isinstance(argv, list) or argv not in packet.get("ordered_argv", []):
            event["reason"] = "event argv is not in frozen packet"
            return event
        if cwd != packet.get("cwd"):
            event["reason"] = "event cwd differs from frozen packet"
            return event
        if record.get("env") != packet.get("environment"):
            event["reason"] = "event environment differs from frozen packet"
            return event
        if not isinstance(writes, list) or any(
                target not in packet.get("allowed_write_targets", []) for target in writes):
            event["reason"] = "event write target is not sealed"
            return event
        if not self._is_semantically_local_argv(argv):
            event["reason"] = "sealed argv is not semantically local"
            return event
        roots = (request.clone_path, request.artifact_dir)
        if request.frozen_packet.get("immutable_authority") is not None and any(
                not self._is_canonical_absolute_path(target) or not self._within(
                    target, roots) for target in writes):
            event["reason"] = "event write target escaped canonical roots"
            return event
        event["class"] = "ALLOWED_LOCAL"
        event["reason"] = "sealed local event"
        return event

    @staticmethod
    def _is_semantically_local_argv(argv: Any) -> bool:
        if not isinstance(argv, list) or not argv or any(
                not isinstance(token, str) or not token for token in argv):
            return False
        executable = os.path.basename(argv[0]).lower()
        lowered = [token.lower() for token in argv]
        if executable.startswith("python"):
            if len(lowered) < 3 or lowered[1:3] != ["-m", "pytest"]:
                return False
        elif executable == "pytest":
            pass
        elif executable == "npm":
            if len(lowered) < 2 or lowered[1] not in {"test", "run"}:
                return False
            if lowered[1] == "run" and (len(lowered) < 3 or not re.fullmatch(
                    r"[a-z0-9][a-z0-9:_-]*", lowered[2])):
                return False
        elif executable == "git":
            if len(lowered) < 2 or lowered[1] not in {"status", "diff"}:
                return False
        else:
            return False
        joined = "\x00".join(argv).lower()
        if re.search(r"(?:https?|ftp|ssh)://", joined):
            return False
        if any(token in {"|", "||", "&&", ";", ">", ">>", "<", "2>", "&"}
               for token in argv):
            return False
        if any(re.search(r"(?:\$\(|`|\|\||&&|(?<!\\);)", token) for token in argv):
            return False
        forbidden_options = (
            "--upload", "--publish", "--remote", "--network", "--proxy",
            "--approve", "--approval", "--escalat", "--privileg", "--sandbox",
        )
        if any(token.lower().startswith(forbidden_options) for token in argv[1:]):
            return False
        return True

    @classmethod
    def _snapshot_protected_roots(cls, roots: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        snapshots: Dict[str, Dict[str, Any]] = {}
        for root_text in roots:
            root = Path(root_text)
            entries: List[Dict[str, Any]] = []
            if not root.exists() or root.is_symlink():
                entries.append({
                    "root": root_text,
                    "exists": root.exists(),
                    "type": "symlink" if root.is_symlink() else "missing",
                    "target": os.readlink(root) if root.is_symlink() else None,
                })
            else:
                paths = [root]
                if root.is_dir():
                    paths.extend(sorted(root.rglob("*"), key=lambda path: path.as_posix()))
                for path in paths:
                    relative = "." if path == root else path.relative_to(root).as_posix()
                    entry: Dict[str, Any] = {
                        "root": root_text, "path": relative,
                        "mode": path.lstat().st_mode & 0o7777,
                    }
                    if path.is_symlink():
                        entry.update({"type": "symlink", "target": os.readlink(path)})
                    elif path.is_dir():
                        entry.update({"type": "directory", "size": 0})
                    elif path.is_file():
                        content = path.read_bytes()
                        entry.update({
                            "type": "file", "size": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        })
                    else:
                        entry.update({"type": "unsupported"})
                    entries.append(entry)
            snapshots[root_text] = {
                "entries": entries,
                "root_hash": canonical_hash(entries),
            }
        return snapshots

    def _validate_protected_root_snapshots(
            self, request: CodexExecRequest, observation: Dict[str, Any]) -> None:
        snapshots = observation.setdefault("protected_root_snapshots", {})
        before = snapshots.get("before")
        after = self._snapshot_protected_roots(request.protected_roots)
        snapshots["after"] = after
        if not isinstance(before, dict) or any(
                before.get(root, {}).get("root_hash") != after.get(root, {}).get("root_hash")
                for root in request.protected_roots):
            self._block("protected root snapshot changed during execution", observation)

    def _normal_cleanup(self, process: Any, containment: Dict[str, Any], argv: List[str],
                        request: CodexExecRequest) -> Dict[str, Any]:
        pgid = process.pid
        receipt = self.process_tree.receipt(pid=process.pid, pgid=pgid)
        if not self.process_tree.audit_empty(pgid) or receipt.get("descendants_exited") is not True:
            self._block("descendant cleanup could not be proved", {"cleanup": receipt})
        return self._cleanup_receipt(receipt, containment, argv, request,
                                     getattr(process, "returncode", None))

    def _timeout_cleanup(self, process: Any, request: CodexExecRequest,
                         containment: Dict[str, Any], argv: List[str]) -> Dict[str, Any]:
        pgid = process.pid
        self.process_tree.signal_group(pgid, signal.SIGTERM)
        try:
            process.wait(timeout=request.grace_seconds)
        except Exception:
            pass
        self.process_tree.signal_group(pgid, signal.SIGKILL)
        try:
            process.wait(timeout=request.grace_seconds)
        except Exception:
            pass
        receipt = self.process_tree.receipt(pid=process.pid, pgid=pgid)
        if not self.process_tree.audit_empty(pgid) or receipt.get("descendants_exited") is not True:
            self._block("timeout descendant cleanup could not be proved", {"cleanup": receipt})
        return self._cleanup_receipt(receipt, containment, argv, request,
                                     getattr(process, "returncode", None))

    @staticmethod
    def _within(path: Any, roots: Iterable[str]) -> bool:
        if not isinstance(path, str):
            return False
        return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)

    def _cleanup_receipt(self, receipt: Dict[str, Any], containment: Dict[str, Any],
                         argv: List[str], request: CodexExecRequest,
                         exit_status: Any) -> Dict[str, Any]:
        result = dict(receipt)
        result.update({
            "mechanism": containment["mechanism"], "mechanism_version": containment["version"],
            "policy_hash": containment["policy_hash"], "effective_argv": argv,
            "effective_env": request.frozen_packet.get("environment", {}),
            "cwd": request.clone_path,
            "filesystem_violations": containment.get("filesystem_violations", []),
            "network_attempts": containment.get("network_attempts", []),
            "exit_status": exit_status,
            "finished_at_ns": time.time_ns(),
        })
        return result

    def _retain_artifacts(self, request: CodexExecRequest, observation: Dict[str, Any],
                          stdout: Any, stderr: Any, *, final_output: str = "") -> None:
        """Retain a redacted evidence surface for success and abort outcomes."""
        if not os.path.isdir(request.artifact_dir):
            return
        safe_observation = self._redact(observation)
        retained = {
            "stdout.jsonl": self._redact(stdout),
            "stderr.txt": self._redact(stderr),
            "final.txt": self._redact(final_output),
            "raw-observation.json": json.dumps(safe_observation, sort_keys=True, indent=2),
        }
        for name, content in retained.items():
            path = os.path.join(request.artifact_dir, name)
            if not self._within(path, (request.artifact_dir,)):
                self._block("artifact path escaped its sealed root", observation)
            is_smoke_provider_output = (
                request.frozen_packet.get("task_identity", {}).get("role") == "smoke"
                and os.path.normpath(path) == os.path.normpath(
                    request.output_last_message_path)
            )
            if not is_smoke_provider_output:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(content if isinstance(content, str) else str(content))
        output_path = request.output_last_message_path
        final_path = os.path.join(request.artifact_dir, "final.txt")
        if request.frozen_packet.get("task_identity", {}).get("role") != "smoke" and os.path.normpath(
                output_path) != os.path.normpath(final_path):
            if not self._within(output_path, (request.artifact_dir,)):
                self._block("Codex final-output path escaped its sealed root", observation)
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.write(self._redact(final_output))

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            for pattern in self.redaction_patterns:
                value = pattern.sub("[REDACTED]", value)
            return value
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): (
                    "[REDACTED]" if re.search(
                        r"(?i)(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token)",
                        str(key),
                    ) else self._redact(item)
                )
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _hash(value: Any) -> str:
        if not isinstance(value, str):
            value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _block(self, message: str, observation: Dict[str, Any]) -> None:
        raise CodexAdapterBlockedError(message, self._redact(observation))
