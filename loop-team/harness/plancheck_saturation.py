#!/usr/bin/env python3
"""Deterministic plan-check saturation checker for DESIGN_CHECKLIST gate 10.

This module mechanizes the narrow stop condition for repeated plan-check
findings that are only compiler-catchable binding defects. It has no model,
network, or third-party dependency: callers provide structured round records,
and the checker returns one of three verdicts:

  - CONTINUE_PLAN_CHECK
  - STOP_PROSE_REVIEW
  - INVALID_TAGGING

Input shape is intentionally plain JSON-compatible data. The canonical shape is
one round object per JSONL line:

    {"round": 3, "records": [{"tag": "BINDING", "signature": "..."}]}

For convenience, JSONL files may also contain flat record objects with their
own `round` field; the CLI groups those by round before evaluating.
"""
from __future__ import print_function

import json
import sys
from collections import OrderedDict


CONTINUE_PLAN_CHECK = "CONTINUE_PLAN_CHECK"
STOP_PROSE_REVIEW = "STOP_PROSE_REVIEW"
INVALID_TAGGING = "INVALID_TAGGING"

BINDING = "BINDING"
NON_BINDING_TAGS = frozenset(["LOGIC", "CONCURRENCY", "SECURITY"])
INVALID_BINDING_EXCLUSIONS = frozenset([
    "exception_handling",
    "data_wiring",
    "ui_default",
])


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y")
    return bool(value)


def _round_number(round_obj):
    if isinstance(round_obj, dict):
        return round_obj.get("round")
    return getattr(round_obj, "round", None)


def _records(round_obj):
    if isinstance(round_obj, dict):
        return list(round_obj.get("records") or [])
    return list(getattr(round_obj, "records", None) or [])


def _record_field(record, name, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _record_summary(record):
    tag = _record_field(record, "tag", "<missing tag>")
    signature = _record_field(record, "signature", "<missing signature>")
    return "%s:%s" % (tag, signature)


def _normalize_rounds(rounds):
    """Return rounds sorted by round number with records copied into lists.

    The public function accepts either canonical round objects or a flat list
    of record dicts. Flat records are grouped by their `round` field while
    preserving first-seen round order for equal/non-numeric values.
    """
    if rounds is None:
        return []

    rounds = list(rounds)
    if not rounds:
        return []

    has_canonical_round = any(
        isinstance(item, dict) and "records" in item for item in rounds
    )
    if has_canonical_round:
        normalized = [
            {"round": _round_number(item), "records": _records(item)}
            for item in rounds
        ]
    else:
        grouped = OrderedDict()
        for record in rounds:
            number = _record_field(record, "round")
            grouped.setdefault(number, []).append(record)
        normalized = [
            {"round": number, "records": records}
            for number, records in grouped.items()
        ]

    def sort_key(item):
        number = item.get("round")
        if isinstance(number, int):
            return (0, number)
        try:
            return (0, int(number))
        except (TypeError, ValueError):
            return (1, str(number))

    return sorted(normalized, key=sort_key)


def _validate_binding_tags(rounds):
    invalid = []
    for round_obj in rounds:
        number = round_obj.get("round")
        for record in round_obj.get("records", []):
            if _record_field(record, "tag") != BINDING:
                continue

            signature = _record_field(record, "signature")
            compiler_catchable = _as_bool(
                _record_field(record, "compiler_catchable", False)
            )
            exclusion = _record_field(record, "exclusion", "none")
            if exclusion is None:
                exclusion = "none"

            if not signature:
                invalid.append(
                    "round %s BINDING record is missing signature" % (number,)
                )
            if not compiler_catchable:
                invalid.append(
                    "round %s BINDING %r is not compiler_catchable"
                    % (number, signature)
                )
            if exclusion in INVALID_BINDING_EXCLUSIONS:
                invalid.append(
                    "round %s BINDING %r uses compiler-invisible exclusion %r"
                    % (number, signature, exclusion)
                )

    return invalid


def _last_three_rounds(rounds):
    if len(rounds) < 3:
        return []
    return rounds[-3:]


def _rounds_are_consecutive(window):
    numbers = []
    for round_obj in window:
        number = round_obj.get("round")
        try:
            numbers.append(int(number))
        except (TypeError, ValueError):
            return False
    return numbers[1] == numbers[0] + 1 and numbers[2] == numbers[1] + 1


def _binding_record_is_stop_eligible(record):
    if _record_field(record, "tag") != BINDING:
        return False
    if not _as_bool(_record_field(record, "compiler_catchable", False)):
        return False
    exclusion = _record_field(record, "exclusion", "none")
    return exclusion in (None, "none")


def _notes_for_records(records):
    notes = []
    for record in records:
        note = _record_field(record, "note")
        signature = _record_field(record, "signature")
        if note:
            notes.append("%s: %s" % (signature, note))
        elif signature:
            notes.append(str(signature))
    return notes


def evaluate_records(rounds):
    """Evaluate structured plan-check records.

    Returns a dict with `verdict`, `reasons`, and `coder_notes`. The function is
    deterministic and side-effect free.
    """
    normalized = _normalize_rounds(rounds)
    reasons = []
    coder_notes = []

    invalid_reasons = _validate_binding_tags(normalized)
    if invalid_reasons:
        return {
            "verdict": INVALID_TAGGING,
            "reasons": invalid_reasons,
            "coder_notes": [],
        }

    window = _last_three_rounds(normalized)
    if len(window) < 3:
        return {
            "verdict": CONTINUE_PLAN_CHECK,
            "reasons": ["fewer than 3 plan-check rounds recorded"],
            "coder_notes": [],
        }

    if not _rounds_are_consecutive(window):
        return {
            "verdict": CONTINUE_PLAN_CHECK,
            "reasons": ["last 3 rounds are not consecutive"],
            "coder_notes": [],
        }

    window_records = []
    for round_obj in window:
        records = round_obj.get("records", [])
        if not records:
            reasons.append("round %s has no records" % (round_obj.get("round"),))
        window_records.extend(records)

    non_binding = [
        record for record in window_records
        if _record_field(record, "tag") in NON_BINDING_TAGS
    ]
    if non_binding:
        return {
            "verdict": CONTINUE_PLAN_CHECK,
            "reasons": [
                "last 3-round window contains non-binding records: %s"
                % ", ".join(_record_summary(record) for record in non_binding)
            ],
            "coder_notes": _notes_for_records(window_records),
        }

    all_tags = [_record_field(record, "tag") for record in window_records]
    if any(tag != BINDING for tag in all_tags):
        return {
            "verdict": CONTINUE_PLAN_CHECK,
            "reasons": [
                "last 3-round window is not binding-only: %s"
                % ", ".join(str(tag) for tag in all_tags)
            ],
            "coder_notes": _notes_for_records(window_records),
        }

    ineligible = [
        record for record in window_records
        if not _binding_record_is_stop_eligible(record)
    ]
    if ineligible:
        # This is normally unreachable after _validate_binding_tags, but keeps
        # the stop condition explicit if new exclusion values appear later.
        return {
            "verdict": CONTINUE_PLAN_CHECK,
            "reasons": [
                "binding records are not all stop-eligible: %s"
                % ", ".join(_record_summary(record) for record in ineligible)
            ],
            "coder_notes": _notes_for_records(window_records),
        }

    signatures = [
        _record_field(record, "signature") for record in window_records
    ]
    unique_signatures = sorted(set(str(signature) for signature in signatures))
    if len(unique_signatures) != 1:
        return {
            "verdict": CONTINUE_PLAN_CHECK,
            "reasons": [
                "binding signatures do not collapse to one recurring signature: %s"
                % ", ".join(unique_signatures)
            ],
            "coder_notes": _notes_for_records(window_records),
        }

    signature = unique_signatures[0]
    coder_notes = [
        "Stop prose review for recurring compiler-catchable binding signature %r."
        % signature,
        "Carry the binding finding forward verbatim as Coder implementation notes; "
        "the real build/compile gate should catch this class.",
    ]
    coder_notes.extend(_notes_for_records(window_records))
    return {
        "verdict": STOP_PROSE_REVIEW,
        "reasons": [
            "last 3 consecutive rounds contain only stop-eligible BINDING records",
            "all records share recurring signature %r" % signature,
            "no LOGIC/CONCURRENCY/SECURITY records appear in the window",
        ],
        "coder_notes": coder_notes,
    }


def load_jsonl(path):
    """Load a JSONL file containing round objects or flat records."""
    items = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(json.loads(stripped))
            except ValueError as exc:
                raise ValueError(
                    "%s:%s invalid JSON: %s" % (path, line_number, exc)
                )
    return items


def main(argv):
    args = argv[1:]
    strict_records = False
    if args and args[0] == "--strict-records":
        strict_records = True
        args = args[1:]

    if len(args) != 1:
        sys.stderr.write(
            "usage: plancheck_saturation.py [--strict-records] "
            "<plancheck-records.jsonl>\n"
        )
        return 2

    try:
        if strict_records:
            from plan_check_records import (  # noqa: PLC0415
                load_jsonl as load_strict_jsonl,
                to_saturation_records,
            )
            records, errors = load_strict_jsonl(args[0])
            if errors:
                raise ValueError("; ".join(errors))
            rounds = to_saturation_records(records)
        else:
            rounds = load_jsonl(args[0])
        result = evaluate_records(rounds)
    except (IOError, OSError, ValueError) as exc:
        sys.stderr.write("plancheck_saturation.py: %s\n" % (exc,))
        return 2

    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
