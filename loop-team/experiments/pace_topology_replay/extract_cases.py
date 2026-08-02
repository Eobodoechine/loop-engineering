#!/usr/bin/env python3
"""Generate frozen cases and evidence index from immutable source rollouts."""
from __future__ import annotations

import json
import argparse
from pathlib import Path

from simulator import EvidenceError, create_source_seal, extract_case, verify_evidence_index, verify_source_seal


HERE = Path(__file__).resolve().parent


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace-derived", action="store_true", help="replace projections only when source seals are unchanged")
    args = parser.parse_args()
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    frozen_path = HERE / "fixtures" / "frozen_cases.json"
    evidence_path = HERE / "fixtures" / "evidence_index.json"
    seals_path = HERE / "fixtures" / "source_seals.json"
    if any("extracted_record_count" not in item for item in manifest["cases"]):
        if frozen_path.exists() or evidence_path.exists() or seals_path.exists():
            raise EvidenceError("refusing to bootstrap seals over existing generated artifacts")
        version = int(manifest.setdefault("manifest_version", 1))
        for item in manifest["cases"]:
            seal = create_source_seal(item["source_path"], item["case_id"], version)
            item.update({key: seal[key] for key in (
                "manifest_version", "extracted_record_count", "sealed_prefix_raw_sha256",
                "seal_binding_sha256",
            )})
            item["source_sha256"] = seal["sealed_prefix_raw_sha256"]
        write_json(HERE / "manifest.json", manifest)

    seals = []
    for item in manifest["cases"]:
        seal = create_source_seal(
            item["source_path"], item["case_id"], int(item["manifest_version"]),
            int(item["extracted_record_count"]),
        )
        for key in ("sealed_prefix_raw_sha256", "seal_binding_sha256"):
            if seal[key] != item[key]:
                raise EvidenceError(f"manifest seal mismatch for {item['case_id']}: {key}")
        seals.append(seal)
    cases = [extract_case(item["source_path"], item["case_id"], source_seal=seal) for item, seal in zip(manifest["cases"], seals)]
    pointers = [pointer for case in cases for pointer in case["evidence"]]
    seals_by_path = {seal["source_path"]: seal for seal in seals}
    verify_evidence_index(pointers, seals=seals_by_path)
    outputs = {
        frozen_path: {"schema": "pace_topology_cases.v1", "cases": cases},
        evidence_path: {"schema": "pace_evidence_index.v1", "pointers": pointers},
        seals_path: {"schema": "pace_source_seals.v1", "seals": seals},
    }
    rendered = {path: json.dumps(value, indent=2, sort_keys=True) + "\n" for path, value in outputs.items()}
    existing = [path for path in outputs if path.exists()]
    if existing and len(existing) != len(outputs):
        raise EvidenceError("partial generated artifact set; refusing silent regeneration")
    if existing:
        drifted = [path.name for path in existing if path.read_text(encoding="utf-8") != rendered[path]]
        if drifted:
            if not args.replace_derived:
                raise EvidenceError(f"generated artifacts differ; refusing silent regeneration: {drifted}")
            existing_seals = json.loads(seals_path.read_text(encoding="utf-8"))
            if existing_seals != outputs[seals_path]:
                raise EvidenceError("source seals changed; refusing derived replacement")
            for path, text in rendered.items():
                path.write_text(text, encoding="utf-8")
    else:
        for path, text in rendered.items():
            path.write_text(text, encoding="utf-8")
    statuses = [verify_source_seal(seal) for seal in seals]
    print(f"EXTRACT_PASS cases={len(cases)} pointers={len(pointers)} source_statuses={','.join(statuses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
