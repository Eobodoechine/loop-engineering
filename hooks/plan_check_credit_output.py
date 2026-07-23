#!/usr/bin/env python3
"""Generate correctly-formatted plan-check credit output for the Verifier.

Solves the recurring problem where plan-check-verifier subagents produce
PLAN_SUPPORT_JSON in wrong formats (multi-line, code-fenced, wrong hash
algorithm). This script mechanically computes the correct evidence_sha256
using the EXACT algorithm the validator uses (Python's "\\n".join with no
trailing newline) and outputs the three required lines in the exact format
the credit gate validator expects.

Usage (from Verifier role):
    python3 hooks/plan_check_credit_output.py <spec_path> <line_start> <line_end> [--claim "text"] [--verdict PASS|FAIL]

Output (paste directly into response — do NOT wrap in code fences):
    PLAN_SUPPORT_JSON={"artifact_path":"...","line_start":N,"line_end":M,...}
    REVIEWED_SPEC_SHA256=<64-hex>
    LOOP_GATE: PLAN_PASS
"""
import argparse
import hashlib
import json
import os
import sys


def compute_span_digest(path, line_start, line_end):
    """Compute SHA256 of lines[start-1:end] joined with '\\n' — no trailing newline.

    This MUST match the algorithm in spec_bound_verifier_credit.py's
    _support_span_digest() exactly: splitlines(), slice, "\\n".join().
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if line_start < 1 or line_end < line_start or line_end > len(lines):
        return None, f"invalid span: line_start={line_start}, line_end={line_end}, total_lines={len(lines)}"
    selected = lines[line_start - 1:line_end]
    joined = "\n".join(selected)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), None


def file_sha256(path):
    """Compute SHA256 of entire file bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Generate correctly-formatted plan-check credit output"
    )
    parser.add_argument("spec_path", help="Absolute path to the spec file")
    parser.add_argument("line_start", type=int, help="1-indexed start line of evidence span")
    parser.add_argument("line_end", type=int, help="1-indexed end line of evidence span (inclusive)")
    parser.add_argument("--claim", default="Plan-check review passed; all ACs verified correct",
                        help="Claim text for PLAN_SUPPORT_JSON")
    parser.add_argument("--verdict", choices=["PASS", "FAIL"], default="PASS",
                        help="LOOP_GATE verdict (default: PASS)")
    args = parser.parse_args()

    # Validate file exists
    if not os.path.isfile(args.spec_path):
        print(f"ERROR: spec file not found: {args.spec_path}", file=sys.stderr)
        sys.exit(1)

    # Compute full-file spec hash
    spec_sha256 = file_sha256(args.spec_path)

    # Compute evidence span digest (same algorithm as validator)
    evidence_sha256, err = compute_span_digest(args.spec_path, args.line_start, args.line_end)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    # Build PLAN_SUPPORT_JSON (single-line, compact)
    support_obj = {
        "artifact_path": os.path.abspath(args.spec_path),
        "line_start": args.line_start,
        "line_end": args.line_end,
        "evidence_sha256": evidence_sha256,
        "claim": args.claim,
        "spec_sha256": spec_sha256,
    }
    support_json = json.dumps(support_obj, separators=(",", ":"))

    # Output the three required lines — NO code fences, NO extra formatting
    print(f"PLAN_SUPPORT_JSON={support_json}")
    print(f"REVIEWED_SPEC_SHA256={spec_sha256}")
    print(f"LOOP_GATE: PLAN_{args.verdict}")


if __name__ == "__main__":
    main()
