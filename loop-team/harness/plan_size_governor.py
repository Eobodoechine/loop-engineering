#!/usr/bin/env python3
"""plan_size_governor.py -- mechanical artifact-size governor for
SHIP_NARROW_PLAN / WITHIN_MVP_BOUNDARY / INVALID_PLAN_BOUNDARY.

Implements the recommendation of the source research spec
(research/2026-07-16-planning-stop-governor-internal-grounding-redteam.md):
a plan-check spec that has grown past its OWN explicitly-declared MVP
boundary should be CUT, not endlessly re-reviewed -- the same move as the
TaxAhead 782->97-line spec rewrite (learnings.md) that resolved 5 rounds of
escalating scrutiny by shrinking the artifact and re-verifying the smaller
one. This module answers exactly one mechanical question -- "given what was
actually declared, does the artifact exceed it, and was anything declared
at all" -- and invents no magic-number "is this big enough to need a
boundary" threshold of its own.

Key rule 1 (from the source research spec, operationalized here, not
re-derived): an oversized artifact with NO declared MVP_MAX_LINES /
MVP_MAX_ACS boundary returns INVALID_PLAN_BOUNDARY/missing_mvp_boundary,
never SHIP_NARROW_PLAN -- SHIP_NARROW_PLAN is only ever legal once an
explicit boundary exists.

Per-dimension evaluation: MVP_MAX_LINES and MVP_MAX_ACS are each
independently optional. Declaring only ONE of the two is valid and
sufficient to authorize a verdict on that one declared dimension; a spec
need not declare both to escape INVALID_PLAN_BOUNDARY/missing_mvp_boundary.

Known, accepted false-positive risk (stated candidly, matching this
harness's own house style of naming residual risk rather than hiding it):
`actual_acs` is computed via `extract_ac_ids` (imported from
spec_revision_diff.py -- the single source of truth for this repo's AC-id
extraction, not a second copy), which treats ANY exact `AC\\d+[a-z]?` token
as an acceptance-criterion reference, including a literal "AC123"-shaped
substring that happens to appear in unrelated prose. No threshold avoids
this without inventing a structural AC-declaration syntax this repo does
not have; exact-token match, deliberately over-inclusive, is the same
trade-off spec_revision_diff.py's own module docstring already argues for
heading matches.

This governor NEVER suppresses or substitutes for a plan-check round -- it
is a CUT test, not a stop test. A SHIP_NARROW_PLAN verdict always requires
a FRESH plan-check round on the narrowed artifact afterward (see the
research spec's Part 4.1 "Also required" clause, and
H-SPEC-REWRITE-DIFF-1's full-rewrite-risk note documented in this same
harness's spec_revision_diff.py -- a SHIP_NARROW_PLAN cut is exactly that
kind of rewrite).

Exit codes (CLI):
  0 -- a verdict was successfully computed, REGARDLESS of which verdict --
       including INVALID_PLAN_BOUNDARY. The verdict is communicated through
       the JSON payload's "verdict" field, never through the exit code
       (mirrors plancheck_saturation.py's own CLI contract exactly).
  2 -- usage error: wrong argument count, or a missing/unreadable/non-UTF-8
       spec file.

Usage:
    python3 plan_size_governor.py <spec_file>
"""
import json
import re
import sys

from spec_revision_diff import extract_ac_ids

VERDICT_SHIP_NARROW = "SHIP_NARROW_PLAN"
VERDICT_WITHIN_BOUNDARY = "WITHIN_MVP_BOUNDARY"
VERDICT_INVALID_BOUNDARY = "INVALID_PLAN_BOUNDARY"

REASON_MISSING = "missing_mvp_boundary"
REASON_MALFORMED = "malformed_mvp_boundary"

MVP_MAX_LINES_RE = re.compile(r"^MVP_MAX_LINES:\s*(.+?)\s*$", re.MULTILINE)
MVP_MAX_ACS_RE = re.compile(r"^MVP_MAX_ACS:\s*(.+?)\s*$", re.MULTILINE)


def count_lines(text):
    """len(text.splitlines()) -- the same mechanical line-count convention
    used elsewhere in this repo (e.g. roles/verifier.md's PLAN_SUPPORT_JSON
    span-digest)."""
    return len(text.splitlines())


def _first_directive_value(text, pattern):
    """Return the captured value of the FIRST match of `pattern` in `text`,
    or None if the directive does not appear at all. `re.search` on a
    MULTILINE pattern already returns the leftmost (first-occurring) match
    in the string, which is exactly the "first match wins" contract this
    needs -- no separate first-vs-later bookkeeping required."""
    m = pattern.search(text)
    if m is None:
        return None
    return m.group(1)


def _parse_nonneg_int(raw):
    """Return int(raw) if `raw` parses as a non-negative integer, else
    None. A syntactically-valid negative integer (e.g. "-5") parses fine as
    a Python int but is still rejected here -- non-negative is part of the
    contract, not just "parses as int"."""
    try:
        value = int(raw)
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def parse_mvp_boundary(text):
    """Scan `text` for directive lines '^MVP_MAX_LINES:\\s*(.+?)\\s*$' and
    '^MVP_MAX_ACS:\\s*(.+?)\\s*$' (MULTILINE). First match wins if a
    directive appears more than once. Returns:
        {"mvp_max_lines": int|None, "mvp_max_acs": int|None,
         "malformed": [<"mvp_max_lines"|"mvp_max_acs"> for any directive
                       line that matched but whose captured value did not
                       parse as a non-negative int]}
    A directive that matched but failed int-parsing is NOT silently treated
    as absent -- it lands in `malformed`, and `evaluate_plan_boundary` must
    surface REASON_MALFORMED for it (see AC5's full malformed-priority
    grid), never fall through to REASON_MISSING, SHIP_NARROW_PLAN, or
    WITHIN_MVP_BOUNDARY -- malformed takes priority over every other
    outcome, not only the missing-boundary one.
    """
    malformed = []

    lines_raw = _first_directive_value(text, MVP_MAX_LINES_RE)
    mvp_max_lines = None
    if lines_raw is not None:
        mvp_max_lines = _parse_nonneg_int(lines_raw)
        if mvp_max_lines is None:
            malformed.append("mvp_max_lines")

    acs_raw = _first_directive_value(text, MVP_MAX_ACS_RE)
    mvp_max_acs = None
    if acs_raw is not None:
        mvp_max_acs = _parse_nonneg_int(acs_raw)
        if mvp_max_acs is None:
            malformed.append("mvp_max_acs")

    return {
        "mvp_max_lines": mvp_max_lines,
        "mvp_max_acs": mvp_max_acs,
        "malformed": malformed,
    }


def evaluate_plan_boundary(actual_lines, actual_acs, mvp_max_lines, mvp_max_acs, malformed=None):
    """Pure, deterministic. Returns:
        {"verdict": SHIP_NARROW_PLAN | WITHIN_MVP_BOUNDARY | INVALID_PLAN_BOUNDARY,
         "reason": REASON_MISSING | REASON_MALFORMED | None,
         "actual": {"lines": actual_lines, "acs": actual_acs},
         "declared": {"max_lines": mvp_max_lines, "max_acs": mvp_max_acs},
         "exceeded": {...},  # only the dimension(s) that actually exceeded;
             ALWAYS a dict, present in every returned result regardless of
             verdict -- only ever EMPTY ({}) or POPULATED, never absent,
             None, or any other type.
         "message": "<one-sentence human-readable summary>"}

    Logic (mechanical, no invented magic-number threshold -- the ONLY
    question this function answers is "given what was actually declared,
    does the artifact exceed it, and was anything declared at all"). This is
    a genuine if/elif/elif/else SHORT-CIRCUIT, not an independently-evaluated
    priority ranking:
      1. If `malformed` is non-empty -> INVALID_PLAN_BOUNDARY / REASON_MALFORMED.
         Takes priority over EVERY later step -- 2 (missing-boundary), 3
         (exceeded/SHIP_NARROW_PLAN), and 4 (within-boundary) alike -- once
         this step's own condition is true, steps 2-4 are never reached at
         all, regardless of what any of them would separately have
         evaluated to. `exceeded` is `{}`.
      2. Elif mvp_max_lines is None AND mvp_max_acs is None ->
         INVALID_PLAN_BOUNDARY / REASON_MISSING, REGARDLESS of
         actual_lines/actual_acs (a tiny spec with no declared boundary is
         STILL INVALID_PLAN_BOUNDARY under this contract -- the
         caller/orchestrator.md decides WHEN it's worth invoking this tool
         at all, this function never guesses). `exceeded` is `{}`.
      3. Else (at least one dimension declared): for each declared
         dimension, actual > declared is "exceeded". If ANY declared
         dimension exceeded -> SHIP_NARROW_PLAN, reason=None, `exceeded`
         populated for every dimension that exceeded (declared-but-not-
         exceeded dimensions omitted from `exceeded`).
      4. Else (declared, nothing exceeded) -> WITHIN_MVP_BOUNDARY,
         reason=None, `exceeded` is `{}`.
    """
    if malformed is None:
        malformed = []

    actual = {"lines": actual_lines, "acs": actual_acs}
    declared = {"max_lines": mvp_max_lines, "max_acs": mvp_max_acs}

    if malformed:
        return {
            "verdict": VERDICT_INVALID_BOUNDARY,
            "reason": REASON_MALFORMED,
            "actual": actual,
            "declared": declared,
            "exceeded": {},
            "message": (
                "Malformed MVP boundary directive(s): %s -- fix the "
                "directive value(s) before this governor can evaluate the "
                "plan." % ", ".join(malformed)
            ),
        }

    if mvp_max_lines is None and mvp_max_acs is None:
        return {
            "verdict": VERDICT_INVALID_BOUNDARY,
            "reason": REASON_MISSING,
            "actual": actual,
            "declared": declared,
            "exceeded": {},
            "message": (
                "No MVP_MAX_LINES or MVP_MAX_ACS boundary declared -- an "
                "explicit boundary is required before SHIP_NARROW_PLAN can "
                "ever apply."
            ),
        }

    exceeded = {}
    if mvp_max_lines is not None and actual_lines > mvp_max_lines:
        exceeded["lines"] = {"actual": actual_lines, "max": mvp_max_lines}
    if mvp_max_acs is not None and actual_acs > mvp_max_acs:
        exceeded["acs"] = {"actual": actual_acs, "max": mvp_max_acs}

    if exceeded:
        return {
            "verdict": VERDICT_SHIP_NARROW,
            "reason": None,
            "actual": actual,
            "declared": declared,
            "exceeded": exceeded,
            "message": (
                "Declared MVP boundary exceeded on: %s -- cut the plan to "
                "its declared boundary, defer the cut ACs, then re-run "
                "plan-check on the narrowed spec." % ", ".join(sorted(exceeded))
            ),
        }

    return {
        "verdict": VERDICT_WITHIN_BOUNDARY,
        "reason": None,
        "actual": actual,
        "declared": declared,
        "exceeded": {},
        "message": "Declared MVP boundary(ies) not exceeded.",
    }


def evaluate_spec_file(spec_path):
    """Read spec_path (utf-8), compute actual_lines=count_lines(text),
    actual_acs=len(set(extract_ac_ids(text))) (extract_ac_ids imported from
    spec_revision_diff.py -- single source of truth, not a second copy),
    parse_mvp_boundary(text), then evaluate_plan_boundary(...). Raises the
    same OSError a plain `open()` would on a missing/unreadable file, AND
    the same UnicodeDecodeError a plain
    `open(spec_path, encoding="utf-8").read()` would on a file that
    exists/is readable but contains non-UTF-8 bytes -- the CLI wrapper (not
    this function) turns EITHER into the documented exit-2 usage error.
    """
    with open(spec_path, encoding="utf-8") as f:
        text = f.read()

    actual_lines = count_lines(text)
    actual_acs = len(set(extract_ac_ids(text)))
    parsed = parse_mvp_boundary(text)

    return evaluate_plan_boundary(
        actual_lines,
        actual_acs,
        parsed["mvp_max_lines"],
        parsed["mvp_max_acs"],
        malformed=parsed["malformed"],
    )


def main(argv):
    args = argv[1:]
    if len(args) != 1:
        sys.stderr.write("usage: plan_size_governor.py <spec_file>\n")
        return 2

    spec_path = args[0]
    try:
        result = evaluate_spec_file(spec_path)
    except (OSError, UnicodeDecodeError) as e:
        sys.stderr.write(
            "usage: plan_size_governor.py <spec_file>: could not read %s: %s\n"
            % (spec_path, e)
        )
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
