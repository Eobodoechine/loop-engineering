#!/usr/bin/env python3
"""Static, deterministic projection of Loop Team producer-contract sources.

This module deliberately parses source with ``ast`` only.  It never imports a
candidate module, calls a hook, runs a subprocess, or reads a transcript.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "gate-contract-registry.v1"
SCOPE_MANIFEST_V1 = "loop-team/contract_registry/v1/scope_manifest.v1.json"
OVERLAY_DIRECTORY_V1 = "loop-team/contract_registry/v1/manual_overlays"
DEFAULT_JSON_OUTPUT = "loop-team/contract_registry/v1/gate_contracts.v1.json"
DEFAULT_COVERAGE_OUTPUT = "loop-team/contract_registry/v1/gate_contract_coverage.v1.md"
DOCUMENTATION_CORPUS = (
    "RUN.md",
    "VERIFIER.md",
    "loop-team/orchestrator.md",
    "loop-team/TEAM_RELATIONS.md",
)
SCANNED_DIRECTORIES = ("hooks", "loop-team/harness")
EXCLUSION_REASONS = frozenset(
    {
        "fixture_only",
        "normalization_or_logging",
        "producer_helper_or_calibration",
        "worker_or_dashboard_runtime",
        "read_only_audit_or_reconciliation_utility",
        "external_smoke_executor",
        "registry_substrate",
        "test_module",
    }
)
OWNERSHIP_EVIDENCE_TYPES = frozenset({"direct_python_reference", "subprocess_entrypoint"})
SHARED_POLICY_COMPONENT_CATEGORY = "hook_shared_policy_component"
HOOK_LIFECYCLE_CATEGORIES = frozenset({"hook_entry_policy", SHARED_POLICY_COMPONENT_CATEGORY})
SLOP_GATE_PATH = "hooks/slop_gate.py"
COD_STATE_PATH = "hooks/cod_state.py"


class RegistryError(RuntimeError):
    """A deterministic, user-actionable fail-closed registry error."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the V1 canonical JSON encoding, intentionally without a newline."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _relative_path(root: Path, candidate: Path) -> str:
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise RegistryError("PATH_OUTSIDE_REPOSITORY") from error


def _resolve_under_root(root: Path, supplied: str | Path) -> Path:
    candidate = Path(supplied)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    _relative_path(root, resolved)
    return resolved


def _read_raw(root: Path, relative_path: str) -> bytes:
    path = _resolve_under_root(root, relative_path)
    try:
        return path.read_bytes()
    except OSError as error:
        raise RegistryError("MISSING_REQUIRED_SOURCE:%s" % relative_path) from error


def _read_json(root: Path, relative_path: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_raw(root, relative_path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryError("INVALID_JSON:%s" % relative_path) from error
    if not isinstance(value, dict):
        raise RegistryError("INVALID_JSON_OBJECT:%s" % relative_path)
    return value, raw


def _role_document_paths(root: Path) -> list[str]:
    roles = _resolve_under_root(root, "loop-team/roles")
    return [
        _relative_path(root, path)
        for path in sorted(roles.glob("*.md"), key=lambda item: item.as_posix())
    ]


def documentation_paths(root: Path) -> list[str]:
    paths = list(DOCUMENTATION_CORPUS) + _role_document_paths(root)
    for relative_path in paths:
        _read_raw(root, relative_path)
    return paths


def load_manifest(root: Path) -> tuple[dict[str, Any], bytes]:
    manifest, raw = _read_json(root, SCOPE_MANIFEST_V1)
    if manifest.get("schema_version") != "gate-contract-registry-scope-manifest.v1":
        raise RegistryError("INVALID_SCOPE_MANIFEST_VERSION")
    if manifest.get("scope_id") != "SCOPE_MANIFEST_V1":
        raise RegistryError("INVALID_SCOPE_MANIFEST_ID")
    included = manifest.get("included")
    excluded = manifest.get("excluded")
    if not isinstance(included, list) or not isinstance(excluded, list):
        raise RegistryError("INVALID_SCOPE_MANIFEST_SHAPE")
    if len(included) != 30 or len(excluded) != 22:
        raise RegistryError("INVALID_SCOPE_MANIFEST_COUNTS")
    paths: set[str] = set()
    for entry in included:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RegistryError("INVALID_SCOPE_MANIFEST_INCLUDED_ENTRY")
        if entry["path"] in paths or not isinstance(entry.get("category"), str):
            raise RegistryError("DUPLICATE_OR_INVALID_SCOPE_PATH")
        if entry.get("enforcement_mode") not in {
            "blocking",
            "advisory",
            "mixed",
            "uninstalled",
            "unknown",
        }:
            raise RegistryError("INVALID_ENFORCEMENT_MODE")
        if entry["category"] == SHARED_POLICY_COMPONENT_CATEGORY:
            allowed_types = entry.get("allowed_ownership_evidence_types")
            expected_types = (
                ["subprocess_entrypoint"]
                if entry["path"] == SLOP_GATE_PATH
                else ["direct_python_reference"]
            )
            if allowed_types != expected_types:
                raise RegistryError("INVALID_OWNERSHIP_EVIDENCE_ALLOWLIST:%s" % entry["path"])
        elif "allowed_ownership_evidence_types" in entry:
            raise RegistryError("INVALID_OWNERSHIP_EVIDENCE_ALLOWLIST:%s" % entry["path"])
        paths.add(entry["path"])
    registry_substrate_count = 0
    for entry in excluded:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RegistryError("INVALID_SCOPE_MANIFEST_EXCLUDED_ENTRY")
        reason = entry.get("exclude_reason")
        if entry["path"] in paths or reason not in EXCLUSION_REASONS - {"test_module"}:
            raise RegistryError("DUPLICATE_OR_INVALID_SCOPE_PATH")
        if reason == "registry_substrate":
            registry_substrate_count += 1
            if entry["path"] != "loop-team/harness/gate_contract_registry.py":
                raise RegistryError("INVALID_REGISTRY_SUBSTRATE_EXCLUSION")
        paths.add(entry["path"])
    if registry_substrate_count != 1:
        raise RegistryError("INVALID_REGISTRY_SUBSTRATE_EXCLUSION")
    return manifest, raw


def enumerate_scanned_sources(root: Path) -> list[str]:
    paths: list[str] = []
    for directory in SCANNED_DIRECTORIES:
        absolute_directory = _resolve_under_root(root, directory)
        paths.extend(
            _relative_path(root, path)
            for path in absolute_directory.rglob("*.py")
            if path.is_file()
        )
    return sorted(paths)


def classify_sources(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    included = {entry["path"]: entry for entry in manifest["included"]}
    excluded = {entry["path"]: entry for entry in manifest["excluded"]}
    classifications: list[dict[str, Any]] = []
    for relative_path in enumerate_scanned_sources(root):
        if relative_path in included:
            classifications.append({"path": relative_path, "classification": "included", **included[relative_path]})
        elif relative_path in excluded:
            classifications.append({"path": relative_path, "classification": "excluded", **excluded[relative_path]})
        elif Path(relative_path).name.startswith("test_"):
            classifications.append(
                {"path": relative_path, "classification": "excluded", "exclude_reason": "test_module"}
            )
        else:
            raise RegistryError("UNCLASSIFIED_SOURCE:%s" % relative_path)
    expected = set(included) | set(excluded)
    present = {entry["path"] for entry in classifications}
    missing = sorted(expected - present)
    if missing:
        raise RegistryError("MISSING_MANIFEST_SOURCE:%s" % ",".join(missing))
    return classifications


def _is_shared_policy_component(entry: dict[str, Any]) -> bool:
    return entry.get("category") == SHARED_POLICY_COMPONENT_CATEGORY


def _source_tree(root: Path, relative_path: str) -> ast.AST:
    try:
        return ast.parse(_read_raw(root, relative_path).decode("utf-8"), filename=relative_path)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise RegistryError("AST_PARSE_ERROR:%s" % relative_path) from error


def _module_matches(module_name: str | None, target_relative_path: str) -> bool:
    if not module_name:
        return False
    target_module = Path(target_relative_path).stem
    normalized = module_name.lstrip(".")
    return normalized == target_module or normalized.endswith("." + target_module)


def _direct_import_bindings(tree: ast.AST, target_relative_path: str) -> list[tuple[str, dict[str, int]]]:
    bindings: list[tuple[str, dict[str, int]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_matches(alias.name, target_relative_path):
                    bindings.append((alias.asname or alias.name.split(".", 1)[0], _span(node)))
        elif isinstance(node, ast.ImportFrom) and _module_matches(node.module, target_relative_path):
            for alias in node.names:
                if alias.name != "*":
                    bindings.append((alias.asname or alias.name, _span(node)))
    return sorted(bindings, key=lambda item: (item[1]["line_start"], item[0]))


def _later_binding_uses(tree: ast.AST, binding: str, after_line: int) -> list[dict[str, int]]:
    uses = [
        _span(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == binding
        and getattr(node, "lineno", 0) > after_line
    ]
    return sorted(uses, key=lambda span: (span["line_start"], span["line_end"]))


def find_direct_python_reference_evidence(
    root: Path, target_relative_path: str, caller_entries: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return only static import/reference + later use pairs in eligible callers."""
    evidence: list[dict[str, Any]] = []
    for caller in sorted(caller_entries, key=lambda entry: entry["path"]):
        caller_path = caller["path"]
        if caller_path == target_relative_path:
            continue
        tree = _source_tree(root, caller_path)
        for binding, import_span in _direct_import_bindings(tree, target_relative_path):
            uses = _later_binding_uses(tree, binding, import_span["line_end"])
            if uses:
                evidence.append(
                    {
                        "type": "direct_python_reference",
                        "caller_relative_path": caller_path,
                        "import_reference_source_span": import_span,
                        "use_source_span": uses[0],
                    }
                )
    return sorted(
        evidence,
        key=lambda item: (
            item["caller_relative_path"],
            item["import_reference_source_span"]["line_start"],
            item["use_source_span"]["line_start"],
        ),
    )


def _module_import_aliases(tree: ast.AST, module_name: str) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module_name:
                    aliases.add(alias.asname or module_name)
    return aliases


def _is_module_method_call(call: ast.Call, module_aliases: set[str], method: str) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == method
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id in module_aliases
    )


def _is_os_path_join(call: ast.Call, os_aliases: set[str]) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "join"
        and isinstance(call.func.value, ast.Attribute)
        and call.func.value.attr == "path"
        and isinstance(call.func.value.value, ast.Name)
        and call.func.value.value.id in os_aliases
    )


def find_subprocess_entrypoint_evidence(
    root: Path, target_relative_path: str, caller_entries: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Find the V1-approved static subprocess launcher shape, never broad strings."""
    evidence: list[dict[str, Any]] = []
    command_literal = Path(target_relative_path).name
    for caller in sorted(caller_entries, key=lambda entry: entry["path"]):
        caller_path = caller["path"]
        tree = _source_tree(root, caller_path)
        subprocess_aliases = _module_import_aliases(tree, "subprocess")
        os_aliases = _module_import_aliases(tree, "os")
        if not subprocess_aliases or not os_aliases:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_module_method_call(node, subprocess_aliases, "run"):
                continue
            if not node.args or not isinstance(node.args[0], (ast.List, ast.Tuple)):
                continue
            for candidate in ast.walk(node.args[0]):
                if not isinstance(candidate, ast.Call) or not _is_os_path_join(candidate, os_aliases):
                    continue
                if not candidate.args:
                    continue
                final_literal = _literal_string(candidate.args[-1])
                if final_literal != command_literal:
                    continue
                resolved_entrypoint = (Path(caller_path).parent / final_literal).as_posix()
                if resolved_entrypoint != target_relative_path:
                    continue
                evidence.append(
                    {
                        "type": "subprocess_entrypoint",
                        "caller_relative_path": caller_path,
                        "caller_source_sha256": sha256_bytes(_read_raw(root, caller_path)),
                        "subprocess_call_line_start": _span(node)["line_start"],
                        "subprocess_call_line_end": _span(node)["line_end"],
                        "entrypoint_relative_path": resolved_entrypoint,
                        "command_literal": final_literal,
                        "command_literal_line": _span(candidate.args[-1])["line_start"],
                    }
                )
    return sorted(
        evidence,
        key=lambda item: (
            item["caller_relative_path"],
            item["subprocess_call_line_start"],
            item["command_literal_line"],
        ),
    )


def find_dynamic_wiring_sites(
    root: Path, target_relative_path: str, caller_entries: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Record only target-naming dynamic imports; no string grep is treated as ownership."""
    sites: list[dict[str, Any]] = []
    for caller in sorted(caller_entries, key=lambda entry: entry["path"]):
        caller_path = caller["path"]
        tree = _source_tree(root, caller_path)
        importlib_aliases = _module_import_aliases(tree, "importlib")
        imported_import_module = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "importlib"
            for alias in node.names
            if alias.name == "import_module"
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            is_dynamic_import = (
                isinstance(node.func, ast.Name)
                and node.func.id in ({"__import__"} | imported_import_module)
            ) or _is_module_method_call(node, importlib_aliases, "import_module")
            if not is_dynamic_import or not _module_matches(_literal_string(node.args[0]), target_relative_path):
                continue
            sites.append(
                {
                    "caller_relative_path": caller_path,
                    "source_spans": [_span(node)],
                    "kind": "dynamic_import_reference",
                }
            )
    return sorted(
        sites,
        key=lambda item: (item["caller_relative_path"], item["source_spans"][0]["line_start"]),
    )


def validate_shared_component_lifecycle(
    record: dict[str, Any], manifest_entry: dict[str, Any], caller_entries: Iterable[dict[str, Any]]
) -> None:
    """Enforce the closed V1 lifecycle/ownership model on generated records."""
    target = manifest_entry["path"]
    allowed = manifest_entry.get("allowed_ownership_evidence_types")
    expected_allowed = ["subprocess_entrypoint"] if target == SLOP_GATE_PATH else ["direct_python_reference"]
    if allowed != expected_allowed:
        raise RegistryError("INVALID_OWNERSHIP_EVIDENCE_ALLOWLIST:%s" % target)
    lifecycle = record.get("lifecycle_status")
    owners = record.get("owning_callers")
    evidence = record.get("caller_evidence")
    reason = record.get("lifecycle_reason")
    unresolved_wiring = record.get("unresolved_wiring_sites")
    if not isinstance(owners, list) or not isinstance(evidence, list) or not isinstance(unresolved_wiring, list):
        raise RegistryError("INVALID_LIFECYCLE_METADATA:%s" % target)
    if lifecycle == "ACTIVE":
        if not owners or not evidence or reason is not None or unresolved_wiring:
            raise RegistryError("INVALID_ACTIVE_OWNERSHIP:%s" % target)
        if owners != sorted(set(item.get("caller_relative_path") for item in evidence)):
            raise RegistryError("INVALID_ACTIVE_OWNERSHIP:%s" % target)
        eligible_callers = {entry["path"] for entry in caller_entries}
        for item in evidence:
            if item.get("type") not in allowed or item.get("caller_relative_path") not in eligible_callers:
                raise RegistryError("INVALID_ACTIVE_OWNERSHIP:%s" % target)
            if item["type"] == "direct_python_reference":
                import_span = item.get("import_reference_source_span")
                use_span = item.get("use_source_span")
                if not isinstance(import_span, dict) or not isinstance(use_span, dict) or import_span.get("line_end", 0) >= use_span.get("line_start", 0):
                    raise RegistryError("INVALID_ACTIVE_OWNERSHIP:%s" % target)
            elif item["type"] == "subprocess_entrypoint":
                required = {
                    "caller_relative_path",
                    "caller_source_sha256",
                    "subprocess_call_line_start",
                    "subprocess_call_line_end",
                    "entrypoint_relative_path",
                    "command_literal",
                    "command_literal_line",
                }
                if target != SLOP_GATE_PATH or set(item) != required | {"type"}:
                    raise RegistryError("INVALID_ACTIVE_OWNERSHIP:%s" % target)
                if (
                    item["entrypoint_relative_path"] != SLOP_GATE_PATH
                    or item["command_literal"] != "slop_gate.py"
                    or item["subprocess_call_line_start"] > item["subprocess_call_line_end"]
                ):
                    raise RegistryError("INVALID_ACTIVE_OWNERSHIP:%s" % target)
        if target == SLOP_GATE_PATH and len(evidence) != 1:
            raise RegistryError("INVALID_ACTIVE_OWNERSHIP:%s" % target)
        return
    if lifecycle == "UNINSTALLED_ORPHANED":
        if target != COD_STATE_PATH or owners or evidence or record.get("enforcement_mode") != "uninstalled" or not isinstance(reason, str) or not reason or unresolved_wiring:
            raise RegistryError("INVALID_UNINSTALLED_ORPHANED:%s" % target)
        return
    if lifecycle == "WIRING_UNRESOLVED":
        if owners or evidence or record.get("enforcement_mode") != "unknown" or not isinstance(reason, str) or not reason or not unresolved_wiring:
            raise RegistryError("INVALID_WIRING_UNRESOLVED:%s" % target)
        return
    raise RegistryError("INVALID_LIFECYCLE_STATUS:%s" % target)


def lifecycle_metadata_for_component(
    root: Path, manifest_entry: dict[str, Any], caller_entries: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Derive lifecycle claims from current AST sources only, then validate them."""
    target = manifest_entry["path"]
    direct_evidence = find_direct_python_reference_evidence(root, target, caller_entries)
    subprocess_evidence = (
        find_subprocess_entrypoint_evidence(root, target, caller_entries)
        if manifest_entry.get("allowed_ownership_evidence_types") == ["subprocess_entrypoint"]
        else []
    )
    dynamic_sites = find_dynamic_wiring_sites(root, target, caller_entries)
    if direct_evidence:
        metadata = {
            "lifecycle_status": "ACTIVE",
            "owning_callers": sorted({item["caller_relative_path"] for item in direct_evidence}),
            "caller_evidence": direct_evidence,
            "allowed_ownership_evidence_types": manifest_entry["allowed_ownership_evidence_types"],
            "lifecycle_reason": None,
            "unresolved_wiring_sites": [],
        }
    elif subprocess_evidence:
        metadata = {
            "lifecycle_status": "ACTIVE",
            "owning_callers": sorted({item["caller_relative_path"] for item in subprocess_evidence}),
            "caller_evidence": subprocess_evidence,
            "allowed_ownership_evidence_types": manifest_entry["allowed_ownership_evidence_types"],
            "lifecycle_reason": None,
            "unresolved_wiring_sites": [],
        }
    elif dynamic_sites:
        metadata = {
            "lifecycle_status": "WIRING_UNRESOLVED",
            "owning_callers": [],
            "caller_evidence": [],
            "allowed_ownership_evidence_types": manifest_entry["allowed_ownership_evidence_types"],
            "lifecycle_reason": "Dynamic import/reference wiring prevents a sound zero-current-caller conclusion.",
            "unresolved_wiring_sites": dynamic_sites,
        }
    else:
        metadata = {
            "lifecycle_status": "UNINSTALLED_ORPHANED",
            "owning_callers": [],
            "caller_evidence": [],
            "allowed_ownership_evidence_types": manifest_entry["allowed_ownership_evidence_types"],
            "lifecycle_reason": "Zero current direct Python import/reference-and-use caller edges were found in included hook entry/component sources.",
            "unresolved_wiring_sites": [],
        }
    record = {
        "relative_path": target,
        "enforcement_mode": manifest_entry["enforcement_mode"],
        **metadata,
    }
    validate_shared_component_lifecycle(record, manifest_entry, caller_entries)
    return metadata


def _literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _literal_scalar(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return str(node.value).lower() if isinstance(node.value, bool) or node.value is None else str(node.value)
    return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        chain = [node.func.attr]
        base: ast.AST = node.func.value
        while isinstance(base, ast.Attribute):
            chain.append(base.attr)
            base = base.value
        if isinstance(base, ast.Name):
            chain.append(base.id)
        return ".".join(reversed(chain))
    return ""


def _span(node: ast.AST) -> dict[str, int]:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return {"line_start": start, "line_end": end}


def _normalize(value: str) -> str:
    return " ".join(value.split())


class StaticContractVisitor(ast.NodeVisitor):
    """Extract only syntactic facts; uncertainty is recorded, never interpreted."""

    def __init__(self) -> None:
        self.elements: list[dict[str, Any]] = []
        self.unresolved_dynamic_sites: list[dict[str, Any]] = []
        self._failure_depth = 0

    def _add(self, kind: str, value: str, node: ast.AST) -> None:
        self.elements.append(
            {
                "kind": kind,
                "value": _normalize(value),
                "source_spans": [_span(node)],
                "extraction": "ast_literal",
                "completeness": "observed",
            }
        )

    def _dynamic(self, kind: str, node: ast.AST) -> None:
        self.unresolved_dynamic_sites.append({"kind": kind, "source_spans": [_span(node)]})

    def visit_If(self, node: ast.If) -> None:
        self._failure_depth += 1
        self.generic_visit(node)
        self._failure_depth -= 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._failure_depth += 1
        self.generic_visit(node)
        self._failure_depth -= 1

    def visit_Subscript(self, node: ast.Subscript) -> None:
        value = _literal_string(node.slice)
        if value is not None:
            self._add("input_field", value, node)
        elif not isinstance(node.slice, ast.Slice):
            self._dynamic("computed_subscript_key", node)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self._failure_depth and node.value is not None:
            values: Iterable[ast.AST]
            if isinstance(node.value, (ast.Tuple, ast.List)):
                values = node.value.elts
            else:
                values = (node.value,)
            for value in values:
                literal = _literal_string(value)
                if literal:
                    self._add("rejection_reason", literal, value)
        if isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                literal = _literal_string(key) if key is not None else None
                if literal:
                    self._add("output_field", literal, key)
                returned_path = _literal_string(value)
                if returned_path and ("/" in returned_path or returned_path.startswith(".")):
                    self._add("input_path", returned_path, value)
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self._dynamic("f_string", node)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, (ast.Add, ast.Mod)) and not (
            isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant)
        ):
            self._dynamic("computed_string", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        first = node.args[0] if node.args else None
        first_string = _literal_string(first) if first is not None else None
        if name.endswith(".add_argument") and first_string is not None:
            self._add("input_literal", first_string, first)
        if name.endswith(".get") and first_string is not None:
            self._add("input_field", first_string, first)
        if name in {"re.compile", "re.match", "re.search", "re.findall", "re.fullmatch"}:
            if first_string is None and first is not None:
                self._dynamic("computed_regex", first)
            elif first_string is not None:
                self._add("input_literal", first_string, first)
        if name in {"sys.exit", "exit", "quit"}:
            if first is None:
                self._add("exit_semantics", "0", node)
            else:
                scalar = _literal_scalar(first)
                if scalar is None:
                    self._dynamic("computed_exit_status", first)
                else:
                    self._add("exit_semantics", scalar, first)
        if name in {"open", "Path", "pathlib.Path", "os.path.join", "os.path.abspath", "os.path.realpath"}:
            for argument in node.args:
                literal = _literal_string(argument)
                if literal and ("/" in literal or literal.startswith(".")):
                    self._add("input_path", literal, argument)
        if name in {"getattr", "setattr", "hasattr", "globals", "locals", "eval", "exec"}:
            self._dynamic("reflection_or_dynamic_execution", node)
        self.generic_visit(node)


def _deduplicate_elements(relative_path: str, elements: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for element in elements:
        spans = tuple((span["line_start"], span["line_end"]) for span in element["source_spans"])
        key = (element["kind"], element["value"], element["extraction"], element["completeness"], spans)
        unique.setdefault(key, copy.deepcopy(element))
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            item["kind"],
            item["value"],
            item["extraction"],
            item["source_spans"][0]["line_start"],
            item["source_spans"][0]["line_end"],
        ),
    )
    for index, element in enumerate(ordered, start=1):
        element["element_id"] = "%s::%s::%04d" % (relative_path, element["kind"], index)
    return ordered


def _deduplicate_dynamic(sites: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for site in sites:
        span = site["source_spans"][0]
        unique.setdefault((site["kind"], span["line_start"], span["line_end"]), copy.deepcopy(site))
    return sorted(
        unique.values(),
        key=lambda item: (item["kind"], item["source_spans"][0]["line_start"], item["source_spans"][0]["line_end"]),
    )


def load_manual_overlays(root: Path) -> dict[str, dict[str, Any]]:
    directory = _resolve_under_root(root, OVERLAY_DIRECTORY_V1)
    overlays: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json"), key=lambda item: item.as_posix()):
        relative_path = _relative_path(root, path)
        overlay, _raw = _read_json(root, relative_path)
        target = overlay.get("target_relative_path")
        dossier = overlay.get("dossier_relative_path")
        if not isinstance(target, str) or not isinstance(dossier, str):
            raise RegistryError("INVALID_MANUAL_OVERLAY:%s" % relative_path)
        if overlay.get("schema_version") != "gate-contract-registry-manual-overlay.v1":
            raise RegistryError("INVALID_MANUAL_OVERLAY:%s" % relative_path)
        if sha256_bytes(_read_raw(root, target)) != overlay.get("target_source_sha256"):
            raise RegistryError("MANUAL_OVERLAY_SOURCE_DRIFT:%s" % target)
        if sha256_bytes(_read_raw(root, dossier)) != overlay.get("dossier_sha256"):
            raise RegistryError("MANUAL_OVERLAY_DOSSIER_DRIFT:%s" % dossier)
        reasons = overlay.get("reason_strings")
        if not isinstance(reasons, list) or not reasons:
            raise RegistryError("INVALID_MANUAL_OVERLAY:%s" % relative_path)
        seen: set[str] = set()
        for reason in reasons:
            if not isinstance(reason, dict) or not isinstance(reason.get("value"), str):
                raise RegistryError("INVALID_MANUAL_OVERLAY:%s" % relative_path)
            if reason["value"] in seen or not isinstance(reason.get("source_spans"), list):
                raise RegistryError("INVALID_MANUAL_OVERLAY:%s" % relative_path)
            seen.add(reason["value"])
        if target in overlays:
            raise RegistryError("DUPLICATE_MANUAL_OVERLAY:%s" % target)
        overlay = copy.deepcopy(overlay)
        overlay["overlay_relative_path"] = relative_path
        overlays[target] = overlay
    return overlays


def extract_record(
    root: Path,
    relative_path: str,
    category: str,
    enforcement_mode: str,
    manual_overlay: dict[str, Any] | None = None,
    lifecycle_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = _read_raw(root, relative_path)
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=relative_path)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise RegistryError("AST_PARSE_ERROR:%s" % relative_path) from error
    visitor = StaticContractVisitor()
    visitor.visit(tree)
    elements = visitor.elements
    overlay_metadata = None
    if manual_overlay is not None:
        elements = [element for element in elements if element["kind"] != "rejection_reason"]
        for reason in manual_overlay["reason_strings"]:
            elements.append(
                {
                    "kind": "rejection_reason",
                    "value": reason["value"],
                    "source_spans": copy.deepcopy(reason["source_spans"]),
                    "extraction": "manual_overlay",
                    "completeness": "manual_exhaustive",
                }
            )
        overlay_metadata = {
            "overlay_relative_path": manual_overlay["overlay_relative_path"],
            "target_source_sha256": manual_overlay["target_source_sha256"],
            "dossier_relative_path": manual_overlay["dossier_relative_path"],
            "dossier_sha256": manual_overlay["dossier_sha256"],
            "scope": manual_overlay["scope"],
            "reason_count": len(manual_overlay["reason_strings"]),
        }
    record = {
        "schema_version": SCHEMA_VERSION,
        "relative_path": relative_path,
        "category": category,
        "enforcement_mode": enforcement_mode,
        "lifecycle_status": "ACTIVE",
        "owning_callers": [],
        "caller_evidence": [],
        "allowed_ownership_evidence_types": [],
        "lifecycle_reason": None,
        "unresolved_wiring_sites": [],
        "source_sha256": sha256_bytes(raw),
        "elements": _deduplicate_elements(relative_path, elements),
        "unresolved_dynamic_sites": _deduplicate_dynamic(visitor.unresolved_dynamic_sites),
        "manual_overlay": overlay_metadata,
    }
    if lifecycle_metadata is not None:
        record.update(copy.deepcopy(lifecycle_metadata))
    record["record_sha256"] = sha256_bytes(canonical_json_bytes(record))
    return record


def build_registry(root: Path) -> tuple[dict[str, Any], str]:
    root = root.resolve()
    manifest, manifest_raw = load_manifest(root)
    classifications = classify_sources(root, manifest)
    overlays = load_manual_overlays(root)
    included = [entry for entry in classifications if entry["classification"] == "included"]
    lifecycle_callers = [
        entry for entry in included if entry["category"] in HOOK_LIFECYCLE_CATEGORIES
    ]
    records = []
    for entry in included:
        lifecycle_metadata = (
            lifecycle_metadata_for_component(root, entry, lifecycle_callers)
            if _is_shared_policy_component(entry)
            else None
        )
        records.append(
            extract_record(
                root,
                entry["path"],
                entry["category"],
                entry["enforcement_mode"],
                overlays.get(entry["path"]),
                lifecycle_metadata,
            )
        )
    docs: list[dict[str, str]] = []
    for relative_path in documentation_paths(root):
        docs.append({"relative_path": relative_path, "source_sha256": sha256_bytes(_read_raw(root, relative_path))})
    registry = {
        "schema_version": SCHEMA_VERSION,
        "scope_manifest_relative_path": SCOPE_MANIFEST_V1,
        "scope_manifest_source_sha256": sha256_bytes(manifest_raw),
        "inventory_sha256": sha256_bytes(canonical_json_bytes(manifest)),
        "documentation_sources": docs,
        "records": records,
    }
    registry["registry_sha256"] = sha256_bytes(canonical_json_bytes(registry))
    return registry, render_coverage(root, registry)


def _line_ranges(text: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    return [(index, index) for index, line in enumerate(text.splitlines(), start=1) if needle in line]


def _documentation_hits(root: Path, docs: list[dict[str, str]], value: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for document in docs:
        raw = _read_raw(root, document["relative_path"])
        text = raw.decode("utf-8")
        for start, end in _line_ranges(text, value):
            hits.append(
                {
                    "relative_path": document["relative_path"],
                    "line_start": start,
                    "line_end": end,
                    "source_sha256": document["source_sha256"],
                }
            )
    return hits


def _gate_reference_hits(root: Path, docs: list[dict[str, str]], relative_path: str) -> list[dict[str, Any]]:
    module_name = Path(relative_path).stem
    return _documentation_hits(root, docs, module_name)


def coverage_for_record(root: Path, docs: list[dict[str, str]], record: dict[str, Any]) -> dict[str, Any]:
    element_rows: list[dict[str, Any]] = []
    for element in record["elements"]:
        hits = _documentation_hits(root, docs, element["value"])
        if hits:
            status = "DOCUMENTED_EXACT"
        elif _gate_reference_hits(root, docs, record["relative_path"]):
            status = "REFERENCED_NOT_DOCUMENTED"
        else:
            status = "UNDOCUMENTED"
        element_rows.append({"element_id": element["element_id"], "status": status, "hits": hits})
    referenced = _gate_reference_hits(root, docs, record["relative_path"])
    has_exact = any(row["status"] == "DOCUMENTED_EXACT" for row in element_rows)
    has_unknown = bool(record["unresolved_dynamic_sites"])
    all_exact = bool(element_rows) and all(row["status"] == "DOCUMENTED_EXACT" for row in element_rows)
    if not element_rows and not has_unknown:
        aggregate = "NO_EXTRACTABLE_CONTRACT"
    elif all_exact and not has_unknown:
        aggregate = "DOCUMENTED"
    elif has_exact:
        aggregate = "PARTIALLY_DOCUMENTED"
    elif referenced:
        aggregate = "REFERENCED_ONLY"
    else:
        aggregate = "UNDOCUMENTED"
    return {
        "relative_path": record["relative_path"],
        "documentation_status": aggregate,
        "gate_reference_hits": referenced,
        "elements": element_rows,
        "unknown_dynamic_sites": copy.deepcopy(record["unresolved_dynamic_sites"]),
    }


def render_coverage(root: Path, registry: dict[str, Any]) -> str:
    lines = [
        "# Gate Contract Coverage (v1)",
        "",
        "This is a generated static projection. It does not prove runtime conformance or semantic reachability.",
        "",
        "- inventory_sha256: `%s`" % registry["inventory_sha256"],
        "- registry_sha256: `%s`" % registry["registry_sha256"],
        "",
    ]
    docs = registry["documentation_sources"]
    for record in registry["records"]:
        coverage = coverage_for_record(root, docs, record)
        lines.extend(
            (
                "## %s" % record["relative_path"],
                "",
                "Gate status: `%s`" % coverage["documentation_status"],
                "",
                "| Lifecycle field | Value |",
                "| --- | --- |",
                "| Lifecycle status | `%s` |" % record["lifecycle_status"],
                "| Owning callers | %s |"
                % (
                    ", ".join("`%s`" % caller for caller in record["owning_callers"])
                    if record["owning_callers"]
                    else "`[]`"
                ),
                "| Lifecycle reason | %s |"
                % (record["lifecycle_reason"] if record["lifecycle_reason"] else "—"),
                "",
            )
        )
        if record["lifecycle_status"] == "UNINSTALLED_ORPHANED":
            lines.extend(("**INSTALLATION GAP:** %s" % record["lifecycle_reason"], ""))
        if record["caller_evidence"]:
            lines.append("Ownership evidence:")
            for evidence in record["caller_evidence"]:
                if evidence["type"] == "direct_python_reference":
                    import_span = evidence["import_reference_source_span"]
                    use_span = evidence["use_source_span"]
                    lines.append(
                        "- `direct_python_reference`: `%s` import/reference %s-%s; use/call %s-%s"
                        % (
                            evidence["caller_relative_path"],
                            import_span["line_start"],
                            import_span["line_end"],
                            use_span["line_start"],
                            use_span["line_end"],
                        )
                    )
                else:
                    lines.append(
                        "- `subprocess_entrypoint`: `%s:%s-%s` command literal `%s` at line %s; resolves to `%s`; caller sha256 `%s`"
                        % (
                            evidence["caller_relative_path"],
                            evidence["subprocess_call_line_start"],
                            evidence["subprocess_call_line_end"],
                            evidence["command_literal"],
                            evidence["command_literal_line"],
                            evidence["entrypoint_relative_path"],
                            evidence["caller_source_sha256"],
                        )
                    )
            lines.append("")
        if record["unresolved_wiring_sites"]:
            lines.append("Unresolved wiring sites:")
            for site in record["unresolved_wiring_sites"]:
                span = site["source_spans"][0]
                lines.append(
                    "- `%s` at `%s:%s-%s`"
                    % (site["kind"], site["caller_relative_path"], span["line_start"], span["line_end"])
                )
            lines.append("")
        if coverage["gate_reference_hits"]:
            lines.append("Gate references:")
            for hit in coverage["gate_reference_hits"]:
                lines.append("- `%s:%s-%s` sha256 `%s`" % (hit["relative_path"], hit["line_start"], hit["line_end"], hit["source_sha256"]))
            lines.append("")
        lines.extend(("| Element | Kind | Documentation status | Evidence |", "| --- | --- | --- | --- |"))
        statuses = {row["element_id"]: row for row in coverage["elements"]}
        for element in record["elements"]:
            row = statuses[element["element_id"]]
            evidence = "; ".join(
                "%s:%s-%s@%s" % (hit["relative_path"], hit["line_start"], hit["line_end"], hit["source_sha256"])
                for hit in row["hits"]
            ) or "—"
            lines.append("| `%s` | `%s` | `%s` | %s |" % (element["element_id"], element["kind"], row["status"], evidence))
        if coverage["unknown_dynamic_sites"]:
            lines.extend(("", "Unknown dynamic sites (not coverage claims):"))
            for site in coverage["unknown_dynamic_sites"]:
                span = site["source_spans"][0]
                lines.append("- `%s` at `%s:%s-%s`" % (site["kind"], record["relative_path"], span["line_start"], span["line_end"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _output_paths(root: Path, args: argparse.Namespace) -> tuple[Path, Path]:
    json_path = _resolve_under_root(root, args.out_json or DEFAULT_JSON_OUTPUT)
    coverage_path = _resolve_under_root(root, args.out_coverage or DEFAULT_COVERAGE_OUTPUT)
    return json_path, coverage_path


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root; output paths must stay beneath it")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--generate", action="store_true", help="write the two generated projections")
    action.add_argument("--check", action="store_true", help="verify projections without writing")
    parser.add_argument("--out-json", help="test-only JSON output path beneath --repo-root")
    parser.add_argument("--out-coverage", help="test-only coverage output path beneath --repo-root")
    args = parser.parse_args(argv)
    try:
        root = Path(args.repo_root).resolve()
        if not root.is_dir():
            raise RegistryError("INVALID_REPOSITORY_ROOT")
        registry, coverage = build_registry(root)
        json_path, coverage_path = _output_paths(root, args)
        json_bytes = canonical_json_bytes(registry)
        coverage_bytes = coverage.encode("utf-8")
        if args.check:
            try:
                current_json = json_path.read_bytes()
                current_coverage = coverage_path.read_bytes()
            except OSError:
                raise RegistryError("STALE_GENERATED_REGISTRY")
            if current_json != json_bytes or current_coverage != coverage_bytes:
                raise RegistryError("STALE_GENERATED_REGISTRY")
            return 0
        json_path.parent.mkdir(parents=True, exist_ok=True)
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_bytes(json_bytes)
        coverage_path.write_bytes(coverage_bytes)
        return 0
    except RegistryError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
