#!/usr/bin/env python3
"""Validate an evidence receipt against schema v1.0.0.

Canonical implementation of MERGE_GATE_SPEC.md section 5. Pure stdlib on
purpose: the post-merge receipt job must not depend on a package install
succeeding, because a registry outage would then look like an evidence
failure and open a spurious recovery issue.

Usage:
    python3 validate_receipt.py receipt.json
"""

from __future__ import annotations

import json
import re
import sys

SCHEMA_VERSION = "1.0.0"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[^/]+/[^/]+$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

REQUIRED_CHECK_NAMES = {"organization-merge-gate", "project-required-ci"}
CONCLUSIONS = {
    "success", "failure", "cancelled", "skipped",
    "timed_out", "action_required", "neutral", "stale",
}
STAGES = {
    "SPEC", "PLAN_CHECK", "BUILD", "UNIT_TEST", "E2E", "INTEGRATION",
    "LIVE_SMOKE", "SECURITY", "DATA_INTEGRITY", "VERIFIER",
}
OUTCOMES = {"PASS", "FAIL", "BLOCKED_EXTERNAL", "IN_PROGRESS", "NOT_RUN", "RETIRED"}
FAILURE_TYPES = {
    "REQUIREMENTS", "COMPILE", "ASSERTION", "AUTH", "SYNC",
    "CLEANUP", "RLS", "NAVIGATION", "ENVIRONMENT", "HARNESS",
}
# Only these two outcomes carry a failure_type (control-plane/README.md).
OUTCOMES_WITH_FAILURE_TYPE = {"FAIL", "BLOCKED_EXTERNAL"}

TOP_LEVEL_REQUIRED = [
    "schema_version", "repository", "commit_sha", "created_at",
    "producer", "required_checks", "stage", "outcome", "signal",
]
TOP_LEVEL_ALLOWED = set(TOP_LEVEL_REQUIRED) | {
    "parent_sha", "merged_pr", "failure_type",
}
PRODUCER_REQUIRED = ["workflow", "run_id", "run_attempt", "run_url", "gate_ref"]
CHECK_REQUIRED = ["name", "conclusion", "check_run_id", "completed_at"]


def derive_signal(stage: str, outcome: str, failure_type: str | None) -> str:
    """<STAGE>_<OUTCOME>, or <STAGE>_<FAILURE_TYPE>_<OUTCOME> when typed."""
    if failure_type:
        return f"{stage}_{failure_type}_{outcome}"
    return f"{stage}_{outcome}"


def validate(receipt) -> list[str]:
    """Return a list of error strings; empty means valid."""
    errors: list[str] = []

    if not isinstance(receipt, dict):
        return ["receipt must be a JSON object"]

    for key in TOP_LEVEL_REQUIRED:
        if key not in receipt:
            errors.append(f"missing required field: {key}")
    for key in sorted(set(receipt) - TOP_LEVEL_ALLOWED):
        errors.append(f"unexpected field: {key}")

    if receipt.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION!r}, "
            f"got {receipt.get('schema_version')!r}"
        )
    if not REPO_RE.match(str(receipt.get("repository", ""))):
        errors.append("repository must be 'owner/name'")
    if not SHA_RE.match(str(receipt.get("commit_sha", ""))):
        errors.append("commit_sha must be a 40-character lowercase hex SHA")
    parent = receipt.get("parent_sha")
    if parent is not None and not SHA_RE.match(str(parent)):
        errors.append("parent_sha must be null or a 40-character lowercase hex SHA")
    if not RFC3339_RE.match(str(receipt.get("created_at", ""))):
        errors.append("created_at must be an RFC3339 timestamp")
    merged_pr = receipt.get("merged_pr")
    if merged_pr is not None and not isinstance(merged_pr, int):
        errors.append("merged_pr must be an integer or null")

    producer = receipt.get("producer")
    if not isinstance(producer, dict):
        errors.append("producer must be an object")
    else:
        for key in PRODUCER_REQUIRED:
            if key not in producer:
                errors.append(f"producer missing required field: {key}")
        for key in ("run_id", "run_attempt"):
            if key in producer and not isinstance(producer[key], int):
                errors.append(f"producer.{key} must be an integer")

    checks = receipt.get("required_checks")
    if not isinstance(checks, list):
        errors.append("required_checks must be an array")
    else:
        if len(checks) < 2:
            errors.append("required_checks must contain both required check names")
        seen = set()
        for idx, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"required_checks[{idx}] must be an object")
                continue
            for key in CHECK_REQUIRED:
                if key not in check:
                    errors.append(f"required_checks[{idx}] missing: {key}")
            name = check.get("name")
            if name not in REQUIRED_CHECK_NAMES:
                errors.append(
                    f"required_checks[{idx}].name must be one of "
                    f"{sorted(REQUIRED_CHECK_NAMES)}, got {name!r}"
                )
            else:
                seen.add(name)
            if check.get("conclusion") not in CONCLUSIONS:
                errors.append(
                    f"required_checks[{idx}].conclusion invalid: "
                    f"{check.get('conclusion')!r}"
                )
            if "check_run_id" in check and not isinstance(check["check_run_id"], int):
                errors.append(f"required_checks[{idx}].check_run_id must be an integer")
        missing_names = REQUIRED_CHECK_NAMES - seen
        if missing_names:
            errors.append(f"required_checks missing entries for: {sorted(missing_names)}")

    stage = receipt.get("stage")
    outcome = receipt.get("outcome")
    failure_type = receipt.get("failure_type")

    if stage not in STAGES:
        errors.append(f"stage invalid: {stage!r}")
    if outcome not in OUTCOMES:
        errors.append(f"outcome invalid: {outcome!r}")
    if failure_type is not None and failure_type not in FAILURE_TYPES:
        errors.append(f"failure_type invalid: {failure_type!r}")

    # failure_type is required iff outcome is FAIL or BLOCKED_EXTERNAL.
    if outcome in OUTCOMES_WITH_FAILURE_TYPE and not failure_type:
        errors.append(f"outcome {outcome} requires failure_type")
    if outcome not in OUTCOMES_WITH_FAILURE_TYPE and failure_type:
        errors.append(f"outcome {outcome} must not carry failure_type")

    # A PASS receipt may never be recorded over a non-success check.
    if outcome == "PASS" and isinstance(checks, list):
        bad = [
            c.get("name") for c in checks
            if isinstance(c, dict) and c.get("conclusion") != "success"
        ]
        if bad:
            errors.append(f"outcome PASS contradicts non-success checks: {bad}")

    if stage in STAGES and outcome in OUTCOMES:
        expected_signal = derive_signal(stage, outcome, failure_type)
        if receipt.get("signal") != expected_signal:
            errors.append(
                f"signal must be {expected_signal!r}, got {receipt.get('signal')!r}"
            )

    return errors


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: validate_receipt.py <receipt.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[0], encoding="utf-8") as fh:
            receipt = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::cannot read receipt: {exc}")
        return 1

    errors = validate(receipt)
    for error in errors:
        print(f"::error::{error}")
    if not errors:
        print(f"receipt valid: {receipt['signal']} for {receipt['commit_sha']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
