from __future__ import annotations

import copy
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "loop-team/harness/gate_contract_registry.py"
FIXTURE_ROOT = REPO_ROOT / "loop-team/harness/testdata/gate_contract_registry"

spec = importlib.util.spec_from_file_location("gate_contract_registry_under_test", MODULE_PATH)
assert spec and spec.loader
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


def _copy_live_registry_repo(destination: Path) -> Path:
    for directory in ("hooks", "loop-team/harness", "loop-team/roles", "loop-team/contract_registry"):
        source = REPO_ROOT / directory
        target = destination / directory
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
    for document in (
        "RUN.md",
        "VERIFIER.md",
        "loop-team/orchestrator.md",
        "loop-team/TEAM_RELATIONS.md",
        "research/spec-bound-verifier-coder-credit-gate-marker-2026-07-29.md",
    ):
        target = destination / document
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / document, target)
    return destination


def _generate_copy(tmp_path: Path) -> Path:
    root = _copy_live_registry_repo(tmp_path / "repo")
    assert registry.run_cli(["--repo-root", str(root), "--generate"]) == 0
    return root


def test_v1_manifest_classifies_live_source_tree_and_preserves_baseline() -> None:
    manifest, _raw = registry.load_manifest(REPO_ROOT)
    classifications = registry.classify_sources(REPO_ROOT, manifest)
    included = [entry for entry in classifications if entry["classification"] == "included"]
    path_exclusions = [
        entry for entry in classifications if entry.get("exclude_reason") not in (None, "registry_substrate", "test_module")
    ]
    assert len(included) == 30
    assert len(path_exclusions) == 21
    assert len(included) + len(path_exclusions) == 51
    assert [entry for entry in classifications if entry.get("exclude_reason") == "registry_substrate"] == [
        {
            "path": "loop-team/harness/gate_contract_registry.py",
            "classification": "excluded",
            "exclude_reason": "registry_substrate",
        }
    ]
    assert {
        entry["path"]
        for entry in classifications
        if entry.get("exclude_reason") == "test_module"
    } >= {"loop-team/harness/test_gate_contract_registry.py"}


def test_static_extraction_covers_literal_types_and_does_not_import_fixture(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic.py"
    synthetic.write_text((FIXTURE_ROOT / "synthetic_contract.py.txt").read_text(encoding="utf-8"), encoding="utf-8")
    record = registry.extract_record(tmp_path, "synthetic.py", "fixture", "advisory")
    kinds = {element["kind"] for element in record["elements"]}
    values = {element["value"] for element in record["elements"]}
    assert {"input_literal", "input_field", "output_field", "exit_semantics", "input_path", "rejection_reason"} <= kinds
    assert {"--spec", "spec", "missing spec", "3", "loop-team/specs/example.md"} <= values
    assert any(site["kind"] == "f_string" for site in record["unresolved_dynamic_sites"])

    side_effect = tmp_path / "side_effect.py"
    side_effect.write_text((FIXTURE_ROOT / "import_side_effect.py.txt").read_text(encoding="utf-8"), encoding="utf-8")
    registry.extract_record(tmp_path, "side_effect.py", "fixture", "advisory")


def test_canonical_generation_hashes_and_credit_overlay() -> None:
    first, _coverage = registry.build_registry(REPO_ROOT)
    second, _coverage_again = registry.build_registry(REPO_ROOT)
    encoded = registry.canonical_json_bytes(first)
    assert encoded == registry.canonical_json_bytes(second)
    assert not encoded.endswith(b"\n")
    assert first["registry_sha256"] == registry.sha256_bytes(
        registry.canonical_json_bytes({key: value for key, value in first.items() if key != "registry_sha256"})
    )
    for record in first["records"]:
        assert record["record_sha256"] == registry.sha256_bytes(
            registry.canonical_json_bytes({key: value for key, value in record.items() if key != "record_sha256"})
        )
    credit = next(record for record in first["records"] if record["relative_path"] == "hooks/spec_bound_verifier_credit.py")
    reasons = [element["value"] for element in credit["elements"] if element["kind"] == "rejection_reason"]
    assert len(reasons) == len(set(reasons)) == 30
    assert "missing spec info" in reasons
    assert "a qualifying Verifier dispatch for this spec hash returned a non-PASS/invalid result: %s" in reasons
    assert "" not in reasons
    assert not any("authorized by a valid evidence-bound PLAN_PASS" in reason for reason in reasons)
    assert "authorized by cross-turn verifier_pass flag" not in reasons
    assert credit["manual_overlay"]["reason_count"] == 30
    coverage = registry.coverage_for_record(REPO_ROOT, first["documentation_sources"], credit)
    assert coverage["documentation_status"] == "PARTIALLY_DOCUMENTED"


def test_check_detects_source_manifest_document_and_output_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _generate_copy(tmp_path)
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 0

    source = root / "hooks/loop_guard.py"
    source.write_bytes(source.read_bytes() + b"\n# one-byte semantic-neutral source drift\n")
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 2
    assert "STALE_GENERATED_REGISTRY" in capsys.readouterr().err
    assert registry.run_cli(["--repo-root", str(root), "--generate"]) == 0

    manifest = root / registry.SCOPE_MANIFEST_V1
    manifest.write_bytes(manifest.read_bytes() + b" ")
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 2
    assert "STALE_GENERATED_REGISTRY" in capsys.readouterr().err
    manifest.write_bytes(manifest.read_bytes().rstrip())
    assert registry.run_cli(["--repo-root", str(root), "--generate"]) == 0

    document = root / "RUN.md"
    document.write_bytes(document.read_bytes() + b"\nregistry documentation drift\n")
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 2
    assert "STALE_GENERATED_REGISTRY" in capsys.readouterr().err
    assert registry.run_cli(["--repo-root", str(root), "--generate"]) == 0

    generated = root / registry.DEFAULT_JSON_OUTPUT
    generated.write_bytes(generated.read_bytes() + b" ")
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 2
    assert "STALE_GENERATED_REGISTRY" in capsys.readouterr().err


def test_overlay_drift_and_unclassified_source_fail_before_projection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _generate_copy(tmp_path)
    credit_source = root / "hooks/spec_bound_verifier_credit.py"
    credit_source.write_bytes(credit_source.read_bytes() + b"\n# drift\n")
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 2
    assert "MANUAL_OVERLAY_SOURCE_DRIFT" in capsys.readouterr().err

    root = _generate_copy(tmp_path / "second")
    dossier = root / "research/spec-bound-verifier-coder-credit-gate-marker-2026-07-29.md"
    dossier.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "research/spec-bound-verifier-coder-credit-gate-marker-2026-07-29.md", dossier)
    dossier.write_bytes(dossier.read_bytes() + b"\nprovenance drift\n")
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 2
    assert "MANUAL_OVERLAY_DOSSIER_DRIFT" in capsys.readouterr().err

    root = _generate_copy(tmp_path / "third")
    (root / "hooks/unclassified_new_gate.py").write_text("pass\n", encoding="utf-8")
    assert registry.run_cli(["--repo-root", str(root), "--check"]) == 2
    assert "UNCLASSIFIED_SOURCE:hooks/unclassified_new_gate.py" in capsys.readouterr().err


def test_coverage_keeps_generic_mentions_separate_from_element_exactness(tmp_path: Path) -> None:
    document = tmp_path / "docs.md"
    document.write_text("fake_gate is mentioned here.\n--spec is required.\n", encoding="utf-8")
    docs = [{"relative_path": "docs.md", "source_sha256": registry.sha256_bytes(document.read_bytes())}]
    record = {
        "relative_path": "hooks/fake_gate.py",
        "elements": [
            {"element_id": "hooks/fake_gate.py::input_literal::0001", "kind": "input_literal", "value": "--spec"},
            {"element_id": "hooks/fake_gate.py::input_literal::0002", "kind": "input_literal", "value": "--hash"},
        ],
        "unresolved_dynamic_sites": [],
    }
    coverage = registry.coverage_for_record(tmp_path, docs, record)
    assert [row["status"] for row in coverage["elements"]] == ["DOCUMENTED_EXACT", "REFERENCED_NOT_DOCUMENTED"]
    assert coverage["documentation_status"] == "PARTIALLY_DOCUMENTED"


def test_live_shared_component_lifecycle_is_source_grounded_and_rendered() -> None:
    manifest, _raw = registry.load_manifest(REPO_ROOT)
    classifications = registry.classify_sources(REPO_ROOT, manifest)
    included = [entry for entry in classifications if entry["classification"] == "included"]
    lifecycle_callers = [entry for entry in included if entry["category"] in registry.HOOK_LIFECYCLE_CATEGORIES]
    projection, coverage = registry.build_registry(REPO_ROOT)
    records = {record["relative_path"]: record for record in projection["records"]}
    manifest_entries = {entry["path"]: entry for entry in manifest["included"]}

    cod_state = records["hooks/cod_state.py"]
    assert cod_state["lifecycle_status"] == "UNINSTALLED_ORPHANED"
    assert cod_state["enforcement_mode"] == "uninstalled"
    assert cod_state["owning_callers"] == []
    assert cod_state["caller_evidence"] == []
    assert "Zero current" in cod_state["lifecycle_reason"]
    assert "**INSTALLATION GAP:**" in coverage

    slop = records["hooks/slop_gate.py"]
    assert slop["lifecycle_status"] == "ACTIVE"
    assert slop["allowed_ownership_evidence_types"] == ["subprocess_entrypoint"]
    assert slop["owning_callers"] == ["hooks/loop_stop_guard.py"]
    assert slop["caller_evidence"] == [
        {
            "type": "subprocess_entrypoint",
            "caller_relative_path": "hooks/loop_stop_guard.py",
            "caller_source_sha256": registry.sha256_bytes((REPO_ROOT / "hooks/loop_stop_guard.py").read_bytes()),
            "subprocess_call_line_start": 1930,
            "subprocess_call_line_end": 1934,
            "entrypoint_relative_path": "hooks/slop_gate.py",
            "command_literal": "slop_gate.py",
            "command_literal_line": 1932,
        }
    ]
    assert "`hooks/loop_stop_guard.py:1930-1934` command literal `slop_gate.py`" in coverage

    for path, record in records.items():
        if record["category"] != registry.SHARED_POLICY_COMPONENT_CATEGORY or path in {"hooks/cod_state.py", "hooks/slop_gate.py"}:
            continue
        assert record["lifecycle_status"] == "ACTIVE"
        assert record["allowed_ownership_evidence_types"] == ["direct_python_reference"]
        assert record["owning_callers"]
        assert record["caller_evidence"]
        assert {item["type"] for item in record["caller_evidence"]} == {"direct_python_reference"}
        registry.validate_shared_component_lifecycle(record, manifest_entries[path], lifecycle_callers)

    invalid = copy.deepcopy(records["hooks/micro_step_gates.py"])
    invalid["owning_callers"] = []
    with pytest.raises(registry.RegistryError, match="INVALID_ACTIVE_OWNERSHIP"):
        registry.validate_shared_component_lifecycle(invalid, manifest_entries[invalid["relative_path"]], lifecycle_callers)
    invalid = copy.deepcopy(records["hooks/micro_step_gates.py"])
    invalid["caller_evidence"] = []
    with pytest.raises(registry.RegistryError, match="INVALID_ACTIVE_OWNERSHIP"):
        registry.validate_shared_component_lifecycle(invalid, manifest_entries[invalid["relative_path"]], lifecycle_callers)
    invalid = copy.deepcopy(records["hooks/micro_step_gates.py"])
    invalid["caller_evidence"] = copy.deepcopy(slop["caller_evidence"])
    invalid["owning_callers"] = ["hooks/loop_stop_guard.py"]
    with pytest.raises(registry.RegistryError, match="INVALID_ACTIVE_OWNERSHIP"):
        registry.validate_shared_component_lifecycle(invalid, manifest_entries[invalid["relative_path"]], lifecycle_callers)


def test_lifecycle_scanners_reject_bare_and_dynamic_ownership_shapes(tmp_path: Path) -> None:
    caller = tmp_path / "hooks/loop_stop_guard.py"
    caller.parent.mkdir(parents=True)
    caller_entry = {"path": "hooks/loop_stop_guard.py"}
    direct_target = "hooks/shared_component.py"

    caller.write_text("from shared_component import check\n", encoding="utf-8")
    assert registry.find_direct_python_reference_evidence(tmp_path, direct_target, [caller_entry]) == []
    caller.write_text('"""from shared_component import check; check()"""\n', encoding="utf-8")
    assert registry.find_direct_python_reference_evidence(tmp_path, direct_target, [caller_entry]) == []
    caller.write_text("from shared_component import check\ncheck()\n", encoding="utf-8")
    direct = registry.find_direct_python_reference_evidence(tmp_path, direct_target, [caller_entry])
    assert len(direct) == 1
    assert direct[0]["import_reference_source_span"] == {"line_start": 1, "line_end": 1}
    assert direct[0]["use_source_span"] == {"line_start": 2, "line_end": 2}

    slop_target = "hooks/slop_gate.py"
    caller.write_text(
        "import os as path_os\nimport subprocess as runner\n"
        'runner.run(["python", path_os.path.join(path_os.path.dirname(path_os.path.abspath(__file__)), "slop_gate.py")])\n',
        encoding="utf-8",
    )
    evidence = registry.find_subprocess_entrypoint_evidence(tmp_path, slop_target, [caller_entry])
    assert len(evidence) == 1
    assert evidence[0]["entrypoint_relative_path"] == slop_target

    for source in (
        'import subprocess\nsubprocess.run(["slop_gate.py"])\n',
        'import os\nimport subprocess\np = os.path.join("hooks", "slop_gate.py")\nsubprocess.run([p])\n',
        'import os\nimport subprocess\nsubprocess.Popen([os.path.join("hooks", "slop_gate.py")])\n',
    ):
        caller.write_text(source, encoding="utf-8")
        assert registry.find_subprocess_entrypoint_evidence(tmp_path, slop_target, [caller_entry]) == []

    caller.write_text(
        'import importlib\ncomponent = importlib.import_module("shared_component")\n', encoding="utf-8"
    )
    dynamic_entry = {
        "path": direct_target,
        "category": registry.SHARED_POLICY_COMPONENT_CATEGORY,
        "enforcement_mode": "unknown",
        "allowed_ownership_evidence_types": ["direct_python_reference"],
    }
    metadata = registry.lifecycle_metadata_for_component(tmp_path, dynamic_entry, [caller_entry])
    assert metadata["lifecycle_status"] == "WIRING_UNRESOLVED"
    assert metadata["owning_callers"] == []
    assert metadata["caller_evidence"] == []
    assert metadata["unresolved_wiring_sites"]
