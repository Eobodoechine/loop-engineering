#!/usr/bin/env python3
"""Deterministic completion barrier for parallel plan-check lenses.

This module does not dispatch agents and does not read transcripts. It is the
small, testable fan-in check that Oga can run after dispatch has fixed an
expected lens set and after terminal state has been read from direct artifacts
(not from notification counts).

Design source:
    research/async-completion-barrier-prior-art-2026-07-09.md
    research/gate10-concurrency-fingerprint-inventory-2026-07-09.md

The core rule is set equality, not a counter: normal reconciliation is allowed
only when completed == expected. A partial fallback is explicit and separate:
completed plus terminal failures/abandonments may account for expected, but the
verdict is PARTIAL_COMPLETION, never READY_TO_RECONCILE.
"""

import json
import sys


READY_TO_RECONCILE = "READY_TO_RECONCILE"
WAITING_FOR_RESULTS = "WAITING_FOR_RESULTS"
WAITING_FOR_RETRY = "WAITING_FOR_RETRY"
PARTIAL_COMPLETION = "PARTIAL_COMPLETION"
INVALID_BARRIER = "INVALID_BARRIER"

COMPLETE_RECONCILIATION = "complete"
PARTIAL_RECONCILIATION = "partial"
BLOCKED_RECONCILIATION = "blocked"
INVALID_RECONCILIATION = "invalid"

DEFAULT_RETRY_LIMIT = 1
EXIT_READY = 0
EXIT_WAITING = 1
EXIT_INVALID = 2
EXIT_PARTIAL = 3


class BarrierNotReady(AssertionError):
    """Raised when a caller tries to run complete reconciliation too early."""


def normalize_lens_id(value):
    text = str(value).strip()
    if not text:
        raise ValueError("lens id must be non-empty after stripping")
    return text


def build_expected_set(lens_ids):
    """Return a deterministic tuple of expected lens ids.

    The dispatch site should call this before any work can complete and keep
    the returned tuple as the fixed expected set for the barrier check.
    """
    normalized = []
    seen = set()
    duplicates = set()
    for value in lens_ids or []:
        lens_id = normalize_lens_id(value)
        if lens_id in seen:
            duplicates.add(lens_id)
        seen.add(lens_id)
        normalized.append(lens_id)

    if not normalized:
        raise ValueError("expected lens set must not be empty")
    if duplicates:
        raise ValueError(
            "duplicate expected lens id(s): %s" % ", ".join(sorted(duplicates))
        )
    return tuple(sorted(normalized))


def evaluate_lens_completion(expected, completed=None, failed=None,
                             timed_out=None, abandoned=None,
                             retry_counts=None,
                             retry_limit=DEFAULT_RETRY_LIMIT):
    """Evaluate whether an N-lens fan-in is ready, partial, waiting, or invalid.

    Args:
        expected: fixed lens ids captured at dispatch time.
        completed: ids with successful terminal records.
        failed: ids with failed terminal reads/agent outcomes.
        timed_out: ids that exceeded the caller's liveness bound.
        abandoned: ids explicitly marked as abandoned after retry/fallback.
        retry_counts: mapping lens id -> number of retries already attempted.
        retry_limit: retries allowed before failed/timed-out ids become partial
            terminal state instead of WAITING_FOR_RETRY.

    Returns:
        A plain dict with sorted lists for stable proof/log output.
    """
    errors = []
    retry_counts = retry_counts or {}

    expected_list, expected_errors = _normalize_state_values(
        expected, "expected", allow_empty=False, detect_duplicates=True
    )
    expected_set = set(expected_list)
    errors.extend(expected_errors)

    completed_set, completed_errors = _state_set(completed, "completed")
    failed_set, failed_errors = _state_set(failed, "failed")
    timed_out_set, timed_out_errors = _state_set(timed_out, "timed_out")
    abandoned_set, abandoned_errors = _state_set(abandoned, "abandoned")
    errors.extend(completed_errors)
    errors.extend(failed_errors)
    errors.extend(timed_out_errors)
    errors.extend(abandoned_errors)

    normalized_retry_counts = {}
    for raw_key, raw_count in retry_counts.items():
        try:
            lens_id = normalize_lens_id(raw_key)
            count = int(raw_count)
        except (TypeError, ValueError):
            errors.append("retry_counts contains invalid entry %r=%r" %
                          (raw_key, raw_count))
            continue
        if count < 0:
            errors.append("retry_counts for %s is negative" % lens_id)
        normalized_retry_counts[lens_id] = count

    state_sets = {
        "completed": completed_set,
        "failed": failed_set,
        "timed_out": timed_out_set,
        "abandoned": abandoned_set,
    }

    unexpected = set()
    for values in state_sets.values():
        unexpected.update(values - expected_set)
    unexpected.update(set(normalized_retry_counts) - expected_set)
    if unexpected:
        errors.append("state includes unexpected lens id(s): %s" %
                      ", ".join(sorted(unexpected)))

    conflicts = _state_conflicts(state_sets)
    if conflicts:
        errors.append("lens id(s) appear in multiple states: %s" %
                      ", ".join(conflicts))

    if errors:
        return _result(
            INVALID_BARRIER,
            expected_set,
            completed_set,
            failed_set,
            timed_out_set,
            abandoned_set,
            retryable=set(),
            terminal=set(),
            reasons=errors,
            reconciliation_mode=INVALID_RECONCILIATION,
            unexpected=unexpected,
        )

    retryable = set()
    exhausted = set()
    for lens_id in sorted(failed_set | timed_out_set):
        retries_used = normalized_retry_counts.get(lens_id, 0)
        if retries_used < retry_limit:
            retryable.add(lens_id)
        else:
            exhausted.add(lens_id)

    accounted = completed_set | abandoned_set | exhausted
    missing = expected_set - accounted - retryable

    if retryable:
        return _result(
            WAITING_FOR_RETRY,
            expected_set,
            completed_set,
            failed_set,
            timed_out_set,
            abandoned_set,
            retryable=retryable,
            terminal=completed_set | abandoned_set | exhausted,
            reasons=[
                "retryable lens id(s) remain: %s" %
                ", ".join(sorted(retryable))
            ],
            reconciliation_mode=BLOCKED_RECONCILIATION,
            unexpected=set(),
        )

    if missing:
        return _result(
            WAITING_FOR_RESULTS,
            expected_set,
            completed_set,
            failed_set,
            timed_out_set,
            abandoned_set,
            retryable=set(),
            terminal=completed_set | abandoned_set | exhausted,
            reasons=[
                "missing lens id(s): %s" % ", ".join(sorted(missing))
            ],
            reconciliation_mode=BLOCKED_RECONCILIATION,
            unexpected=set(),
        )

    if abandoned_set or exhausted:
        reasons = []
        if abandoned_set:
            reasons.append(
                "abandoned lens id(s): %s" %
                ", ".join(sorted(abandoned_set))
            )
        if exhausted:
            reasons.append(
                "retry-exhausted lens id(s): %s" %
                ", ".join(sorted(exhausted))
            )
        return _result(
            PARTIAL_COMPLETION,
            expected_set,
            completed_set,
            failed_set,
            timed_out_set,
            abandoned_set,
            retryable=set(),
            terminal=accounted,
            reasons=reasons,
            reconciliation_mode=PARTIAL_RECONCILIATION,
            unexpected=set(),
        )

    return _result(
        READY_TO_RECONCILE,
        expected_set,
        completed_set,
        failed_set,
        timed_out_set,
        abandoned_set,
        retryable=set(),
        terminal=completed_set,
        reasons=[],
        reconciliation_mode=COMPLETE_RECONCILIATION,
        unexpected=set(),
    )


def assert_ready_for_reconcile(result):
    """Return True only for complete, non-partial reconciliation readiness."""
    if result.get("verdict") == READY_TO_RECONCILE:
        return True
    raise BarrierNotReady(
        "lens completion barrier is %s, not %s: %s" %
        (
            result.get("verdict"),
            READY_TO_RECONCILE,
            "; ".join(result.get("reasons") or []),
        )
    )


def evaluate_state_file(path, retry_limit=DEFAULT_RETRY_LIMIT):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return _result(
            INVALID_BARRIER,
            expected=set(),
            completed=set(),
            failed=set(),
            timed_out=set(),
            abandoned=set(),
            retryable=set(),
            terminal=set(),
            reasons=["state file root must be a JSON object"],
            reconciliation_mode=INVALID_RECONCILIATION,
            unexpected=set(),
        )
    return evaluate_lens_completion(
        expected=data.get("expected"),
        completed=data.get("completed"),
        failed=data.get("failed"),
        timed_out=data.get("timed_out"),
        abandoned=data.get("abandoned"),
        retry_counts=data.get("retry_counts") or {},
        retry_limit=retry_limit,
    )


def exit_code_for_result(result, allow_partial=False):
    verdict = result.get("verdict")
    if verdict == READY_TO_RECONCILE:
        return EXIT_READY
    if verdict == PARTIAL_COMPLETION:
        return EXIT_READY if allow_partial else EXIT_PARTIAL
    if verdict == INVALID_BARRIER:
        return EXIT_INVALID
    return EXIT_WAITING


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    state_path = None
    allow_partial = False
    retry_limit = DEFAULT_RETRY_LIMIT

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--state":
            i += 1
            if i >= len(argv):
                print("missing value for --state", file=sys.stderr)
                return EXIT_INVALID
            state_path = argv[i]
        elif arg == "--allow-partial":
            allow_partial = True
        elif arg == "--retry-limit":
            i += 1
            if i >= len(argv):
                print("missing value for --retry-limit", file=sys.stderr)
                return EXIT_INVALID
            try:
                retry_limit = int(argv[i])
            except ValueError:
                print("--retry-limit must be an integer", file=sys.stderr)
                return EXIT_INVALID
            if retry_limit < 0:
                print("--retry-limit must be >= 0", file=sys.stderr)
                return EXIT_INVALID
        elif arg in ("-h", "--help"):
            print(
                "usage: lens_completion_barrier.py --state STATE.json "
                "[--retry-limit N] [--allow-partial]"
            )
            return EXIT_READY
        else:
            print("unknown argument: %s" % arg, file=sys.stderr)
            return EXIT_INVALID
        i += 1

    if not state_path:
        print("missing required --state STATE.json", file=sys.stderr)
        return EXIT_INVALID

    try:
        result = evaluate_state_file(state_path, retry_limit=retry_limit)
    except (OSError, ValueError) as exc:
        result = _result(
            INVALID_BARRIER,
            expected=set(),
            completed=set(),
            failed=set(),
            timed_out=set(),
            abandoned=set(),
            retryable=set(),
            terminal=set(),
            reasons=["could not read state file: %s" % exc],
            reconciliation_mode=INVALID_RECONCILIATION,
            unexpected=set(),
        )
    print(json.dumps(result, sort_keys=True))
    return exit_code_for_result(result, allow_partial=allow_partial)


def _state_set(values, field_name):
    normalized, errors = _normalize_state_values(
        values, field_name, allow_empty=True, detect_duplicates=True
    )
    return set(normalized), errors


def _normalize_state_values(values, field_name, allow_empty, detect_duplicates):
    if values is None:
        values = []
    normalized = []
    errors = []
    seen = set()
    for raw in values:
        try:
            lens_id = normalize_lens_id(raw)
        except ValueError as exc:
            errors.append("%s contains invalid lens id %r: %s" %
                          (field_name, raw, exc))
            continue
        if detect_duplicates and lens_id in seen:
            errors.append("%s contains duplicate lens id %s" %
                          (field_name, lens_id))
        seen.add(lens_id)
        normalized.append(lens_id)
    if not allow_empty and not normalized:
        errors.append("%s must not be empty" % field_name)
    return normalized, errors


def _state_conflicts(state_sets):
    by_lens = {}
    for state_name, values in state_sets.items():
        for lens_id in values:
            by_lens.setdefault(lens_id, []).append(state_name)
    conflicts = []
    for lens_id, states in by_lens.items():
        if len(states) > 1:
            conflicts.append("%s (%s)" % (lens_id, "/".join(sorted(states))))
    return sorted(conflicts)


def _result(verdict, expected, completed, failed, timed_out, abandoned,
            retryable, terminal, reasons, reconciliation_mode, unexpected):
    missing = expected - terminal - retryable
    if verdict == WAITING_FOR_RESULTS:
        missing = expected - terminal
    return {
        "verdict": verdict,
        "reconciliation_mode": reconciliation_mode,
        "can_reconcile_complete": verdict == READY_TO_RECONCILE,
        "can_reconcile_partial": verdict == PARTIAL_COMPLETION,
        "expected": sorted(expected),
        "completed": sorted(completed),
        "failed": sorted(failed),
        "timed_out": sorted(timed_out),
        "abandoned": sorted(abandoned),
        "retryable": sorted(retryable),
        "terminal": sorted(terminal),
        "missing": sorted(missing),
        "unexpected": sorted(unexpected),
        "reasons": list(reasons),
    }


if __name__ == "__main__":
    sys.exit(main())
