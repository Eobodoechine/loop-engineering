#!/usr/bin/env python3
"""Fail-closed verifier for generated cases and immutable evidence sources."""
from __future__ import annotations

import json
from pathlib import Path

from simulator import EvidenceError, extract_case, seal_binding_sha256, verify_evidence_index, verify_source_seal


HERE = Path(__file__).resolve().parent


def main() -> int:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    frozen = json.loads((HERE / "fixtures" / "frozen_cases.json").read_text(encoding="utf-8"))
    evidence = json.loads((HERE / "fixtures" / "evidence_index.json").read_text(encoding="utf-8"))
    source_seals = json.loads((HERE / "fixtures" / "source_seals.json").read_text(encoding="utf-8"))
    try:
        manifest_by_id = {item["case_id"]: item for item in manifest["cases"]}
        seals_by_id = {item["case_id"]: item for item in source_seals["seals"]}
        if set(manifest_by_id) != {case["case_id"] for case in frozen["cases"]}:
            raise EvidenceError("case ids do not match manifest")
        if set(seals_by_id) != set(manifest_by_id):
            raise EvidenceError("source seal ids do not match manifest")
        statuses = []
        for case in frozen["cases"]:
            declared = manifest_by_id[case["case_id"]]
            seal = seals_by_id[case["case_id"]]
            for key in (
                "case_id", "source_path", "manifest_version", "extracted_record_count",
                "sealed_prefix_raw_sha256", "seal_binding_sha256",
            ):
                if declared[key] != seal[key]:
                    raise EvidenceError(f"manifest/source-seal mismatch: {case['case_id']} {key}")
            if seal_binding_sha256(declared) != declared["seal_binding_sha256"]:
                raise EvidenceError(f"manifest seal binding mismatch: {case['case_id']}")
            statuses.append(verify_source_seal(seal, declared["source_path"]))
            recomputed = extract_case(declared["source_path"], declared["case_id"], source_seal=seal)
            if recomputed != case:
                raise EvidenceError(f"frozen case drift: {case['case_id']}")
        flattened = [pointer for case in frozen["cases"] for pointer in case["evidence"]]
        if flattened != evidence["pointers"]:
            raise EvidenceError("evidence index differs from frozen cases")
        verify_evidence_index(
            evidence["pointers"],
            seals={seal["source_path"]: seal for seal in source_seals["seals"]},
        )
    except (EvidenceError, KeyError, TypeError) as exc:
        print(f"SOURCE_VERIFY_FAIL {exc}")
        return 1
    print(f"SOURCE_VERIFY_PASS cases={len(frozen['cases'])} pointers={len(evidence['pointers'])} source_statuses={','.join(statuses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
