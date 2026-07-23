#!/usr/bin/env python3
"""Strict JSONL schema for persisted plan-check gap records.

This is the single-shape successor path for `plan_check_records.jsonl`.
It intentionally does not replace `plancheck_saturation.py`'s legacy,
permissive loader yet; instead it gives Oga and future tooling a fail-closed
validator/converter to use when writing new records.

Every JSONL line is one gap record object with:
  schema_version: 1
  record_type: "plan_check_gap"

The `signature` field is required for every Gate-10 tag. For non-BINDING
records this enforces that a signature exists, but does not prove the signature
is semantically stable across paraphrases. That harder fingerprinting problem
remains open.
"""

import hashlib
import json
import sys


SCHEMA_VERSION = 1
RECORD_TYPE = "plan_check_gap"

VALID_TAGS = frozenset(["BINDING", "LOGIC", "CONCURRENCY", "SECURITY"])
VALID_GAP_TYPES = frozenset(["DESIGN", "KNOWLEDGE"])
INVALID_BINDING_EXCLUSIONS = frozenset([
    "exception_handling",
    "data_wiring",
    "ui_default",
])

REQUIRED_FIELDS = (
    "schema_version",
    "record_type",
    "run_id",
    "round",
    "lens",
    "tag",
    "gap_type",
    "signature",
    "broken_assumption",
    "why_it_fails",
    "proposed_fix",
    "touches",
    "mechanism_refs",
)


def normalize_text(value):
    return str(value or "").strip()


def normalize_tag(value):
    return normalize_text(value).upper()


def normalize_list(value):
    if not isinstance(value, list):
        raise ValueError("expected a JSON list")
    normalized = []
    for item in value:
        text = normalize_text(item)
        if not text:
            raise ValueError("list contains blank string")
        normalized.append(text)
    return sorted(dict.fromkeys(normalized))


def canonical_record(record):
    """Return a normalized copy used for validation, IDs, and conversion."""
    if not isinstance(record, dict):
        raise ValueError("record must be a JSON object")

    out = dict(record)
    out["schema_version"] = record.get("schema_version")
    out["record_type"] = normalize_text(record.get("record_type"))
    out["run_id"] = normalize_text(record.get("run_id"))
    out["lens"] = normalize_text(record.get("lens"))
    out["tag"] = normalize_tag(record.get("tag"))
    out["gap_type"] = normalize_tag(record.get("gap_type"))
    out["signature"] = normalize_text(record.get("signature"))
    out["broken_assumption"] = normalize_text(record.get("broken_assumption"))
    out["why_it_fails"] = normalize_text(record.get("why_it_fails"))
    out["proposed_fix"] = normalize_text(record.get("proposed_fix"))
    out["touches"] = normalize_list(record.get("touches", []))
    out["mechanism_refs"] = normalize_list(record.get("mechanism_refs", []))

    try:
        out["round"] = int(record.get("round"))
    except (TypeError, ValueError):
        out["round"] = record.get("round")

    if "compiler_catchable" in record:
        out["compiler_catchable"] = _as_bool(record.get("compiler_catchable"))
    if "exclusion" in record:
        out["exclusion"] = normalize_text(record.get("exclusion")) or "none"
    if "note" in record:
        out["note"] = normalize_text(record.get("note"))
    return out


def validate_record(record, line_number=None):
    """Return a list of machine-readable validation errors for one record."""
    prefix = "line %s: " % line_number if line_number is not None else ""
    errors = []

    if not isinstance(record, dict):
        return [prefix + "record must be a JSON object"]

    if "records" in record:
        errors.append(prefix + "UNSUPPORTED_ROUND_SUMMARY_SHAPE")

    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(prefix + "missing required field %s" % field)

    try:
        normalized = canonical_record(record)
    except ValueError as exc:
        errors.append(prefix + str(exc))
        return errors

    if normalized.get("schema_version") != SCHEMA_VERSION:
        errors.append(prefix + "schema_version must be %s" % SCHEMA_VERSION)
    if normalized.get("record_type") != RECORD_TYPE:
        errors.append(prefix + "record_type must be %r" % RECORD_TYPE)
    if not normalized.get("run_id"):
        errors.append(prefix + "run_id must be non-empty")
    if not isinstance(normalized.get("round"), int) or normalized.get("round") < 1:
        errors.append(prefix + "round must be an integer >= 1")
    if not normalized.get("lens"):
        errors.append(prefix + "lens must be non-empty")
    if normalized.get("tag") not in VALID_TAGS:
        errors.append(prefix + "tag must be one of %s" % ", ".join(sorted(VALID_TAGS)))
    if normalized.get("gap_type") not in VALID_GAP_TYPES:
        errors.append(prefix + "gap_type must be one of %s" %
                      ", ".join(sorted(VALID_GAP_TYPES)))

    for field in ("signature", "broken_assumption", "why_it_fails", "proposed_fix"):
        if not normalized.get(field):
            errors.append(prefix + "%s must be non-empty" % field)

    if normalized.get("tag") == "BINDING":
        if not normalized.get("compiler_catchable"):
            errors.append(prefix + "BINDING requires compiler_catchable=true")
        exclusion = normalized.get("exclusion", "none")
        if exclusion in INVALID_BINDING_EXCLUSIONS:
            errors.append(prefix + "BINDING exclusion %r is compiler-invisible" %
                          exclusion)

    return errors


def record_id(record):
    """Stable ID for the normalized record identity, not a semantic proof."""
    normalized = canonical_record(record)
    key = {
        "schema_version": normalized.get("schema_version"),
        "record_type": normalized.get("record_type"),
        "run_id": normalized.get("run_id"),
        "round": normalized.get("round"),
        "lens": normalized.get("lens"),
        "tag": normalized.get("tag"),
        "signature": normalized.get("signature"),
    }
    payload = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_jsonl(path):
    records = []
    errors = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                errors.append("line %s: invalid JSON: %s" % (line_number, exc))
                continue
            record_errors = validate_record(record, line_number=line_number)
            if record_errors:
                errors.extend(record_errors)
                continue
            records.append(canonical_record(record))
    return records, errors


def to_saturation_records(records):
    """Convert strict records to plancheck_saturation.py's flat input shape."""
    converted = []
    for record in records:
        normalized = canonical_record(record)
        converted.append({
            "round": normalized["round"],
            "tag": normalized["tag"],
            "signature": normalized["signature"],
            "compiler_catchable": normalized.get("compiler_catchable", False),
            "exclusion": normalized.get("exclusion", "none"),
            "note": normalized.get("note") or normalized.get("broken_assumption"),
        })
    return converted


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y")
    return bool(value)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in ("validate", "saturation-records"):
        print(
            "usage: plan_check_records.py validate PATH | "
            "saturation-records PATH",
            file=sys.stderr,
        )
        return 2

    mode, path = argv
    try:
        records, errors = load_jsonl(path)
    except OSError as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, sort_keys=True))
        return 2

    if errors:
        print(json.dumps({
            "valid": False,
            "record_count": len(records),
            "errors": errors,
        }, sort_keys=True))
        return 2

    if mode == "saturation-records":
        print(json.dumps(to_saturation_records(records), sort_keys=True))
        return 0

    print(json.dumps({
        "valid": True,
        "record_count": len(records),
        "record_ids": [record_id(record) for record in records],
        "errors": [],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
