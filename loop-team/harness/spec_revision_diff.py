#!/usr/bin/env python3
"""spec_revision_diff.py -- closes H-SPEC-REWRITE-DIFF-1.

USAGE NOTE (read this before running): Oga must run this BEFORE dispatching
ANY plan-check round on a spec that was revised via a full-file `Write`
rewrite (as opposed to targeted `Edit` calls). This is the standing check
adopted after the `record_sigs`-drop incident: a full-file `Write` rewrite
of the `H-SUBAGENT-MASKING-1` spec (v2 -> v3) silently dropped an entire
already-correct `record_sigs` design subsection, which then let v3's own
AC7 reference an undefined parameter -- survived Oga's own self-review and
was only caught because round 3's plan-check lenses happened to re-verify
that specific AC against the real code instead of trusting the prose claim
"unchanged from v2." If a spec revision used ONLY targeted `Edit` calls
(never a full-file `Write` rewrite of the whole document), this check is
not required for that revision -- targeted edits cannot silently drop an
untouched section the way a full rewrite can.

Given an OLD spec file and a NEW spec file, extracts every markdown heading
(`^#+\\s+.*$`) from each and prints any heading present in the OLD version
but ABSENT from the NEW version -- a potential silent content drop worth a
human's explicit review before the next round dispatches. This does not
judge whether a drop was intentional; it only surfaces it. "This section
existed and no longer does: intentional deletion, or an accidental drop?"
is a question for Oga to answer, not this script.

Heading match convention (EXACT match, not fuzzy/looser matching --
decision explained below): a heading from OLD is considered "still
present" in NEW only if its text (after stripping the leading `#`
characters and surrounding whitespace) appears character-for-character
identical among NEW's own extracted headings. A heading whose wording
changed even slightly (e.g. "## record_sigs design" retitled to
"## record_sigs Design (v3)") is reported as DROPPED under this exact-match
rule, even though a human would likely recognize it as "the same section,
renamed." This is a deliberate choice, not an oversight:
  - The entire incident this tool exists to catch was a heading (and its
    whole subsection) being silently REMOVED, not renamed -- exact match
    catches that case with zero ambiguity or tuning.
  - A "looser" match (e.g. fuzzy string similarity, substring overlap, or
    stripping numbers/parentheticals before comparing) requires picking an
    arbitrary similarity threshold. Too loose, and a genuine content drop
    where the replacement heading happens to share a few words (e.g. "##
    Design" replacing an unrelated deleted "## Data Model Design") gets
    silently treated as "still present" -- exactly the silent-drop failure
    this tool exists to prevent. Too strict defeats the point of loosening
    it at all. There is no threshold that is obviously correct, and a
    wrong threshold fails silently (the worst failure mode for a gate).
  - Exact match's own false-positive cost (flagging a heading that was
    merely reworded, not dropped) is cheap: a human reads one extra line
    and immediately recognizes "oh, that's just a rename" in a few
    seconds. A missed silent drop is the expensive failure this tool
    exists to prevent. So: exact match, deliberately over-inclusive, same
    trade-off philosophy as fixplan_closure_lint.py's SHA-reference check.

Convention matched from `commit_diff_reread.py` / `research_authenticity_check.py`:
stdlib-only, manual `sys.argv` CLI, documented exit codes, plain-text
findings printed to stdout (one per dropped heading) for direct human/Oga
reading before a plan-check dispatch decision.

ADDITIVE EXTENSION (plan_size_governor spec): `extract_ac_ids` plus an
optional `--check-ac-inventory <hardening_ledger.json>` CLI flag, closing
that spec's Key rule 2 ("every old AC from the pre-shrink spec must appear
either in the narrowed spec or in hardening_ledger.json's deferred_ac_ids --
silent drops are a hard failure"). `extract_ac_ids` mirrors this file's own
exact-match-not-fuzzy philosophy above: it extracts distinct `AC\\d+[a-z]?`
tokens, in first-occurrence order, scanned across the WHOLE text (not
scoped to headings -- real specs in this repo reference ACs inline, e.g.
"AC19 (round 30)", not only in heading lines). When `--check-ac-inventory`
is present, every AC id dropped between OLD and NEW is cross-checked
against the union of every ledger entry's `deferred_ac_ids` list; any
dropped AC neither retained in NEW nor deferred in the ledger is an
UNACCOUNTED hard failure (exit 3), which takes priority over the plain
heading-diff's own exit 0/1 from the same invocation.

Known scoping limitation of `--check-ac-inventory` (stated candidly, not
hidden, same disclosure discipline as the exact-match rationale above):
`deferred_ac_ids` is checked as a flat, ledger-wide set, not scoped
per-spec/per-build. If two unrelated specs coincidentally reuse the same
literal AC id (e.g. both happen to define an "AC7"), a deferral recorded
against one could mask a genuine silent drop in the other. Mitigation is a
documentation note (use build-unique AC ids, or manually cross-check the
ledger entry's `citation`), not a code fix in this pass.

Exit codes:
  0 -- no headings from OLD are missing in NEW (and, with
       --check-ac-inventory, every dropped AC is accounted for).
  1 -- one or more headings from OLD are missing in NEW, and (if
       --check-ac-inventory was given) every dropped AC is accounted for.
  2 -- usage error: wrong arg count, missing/unreadable old/new file, or --
       when --check-ac-inventory is given -- a missing/unreadable/invalid
       ledger file, a non-list ledger top-level, or a ledger list
       containing an element that is not itself a JSON object.
  3 -- ONLY reachable with --check-ac-inventory: at least one AC id was
       dropped between OLD and NEW and is not accounted for in the
       ledger's deferred_ac_ids. Takes priority over exit 0/1 from the
       same invocation's heading-diff part.

Usage:
    python3 spec_revision_diff.py <old_file> <new_file>
    python3 spec_revision_diff.py <old_file> <new_file> \\
        --check-ac-inventory <hardening_ledger.json>
"""
import json
import re
import sys

HEADING_RE = re.compile(r"^(#+)\s+(.*?)\s*$", re.MULTILINE)
AC_ID_RE = re.compile(r"\bAC\d+[a-z]?\b")


def extract_headings(content):
    """Return an ordered list of normalized heading strings from `content`.

    Each heading is normalized as "<hashes> <text>" with the hash-run and
    text both stripped of surrounding whitespace -- e.g. "##   Design  "
    normalizes to "## Design". Keeping the hash-run (heading level) as part
    of the comparison key means a heading that was demoted/promoted a level
    (e.g. "## Design" -> "### Design") is ALSO reported as dropped, on the
    same "flag it, let a human judge" philosophy as the exact-text-match
    decision above -- a level change is itself a structural edit worth a
    second look, not something this tool should silently treat as a match.
    """
    headings = []
    for m in HEADING_RE.finditer(content):
        hashes = m.group(1)
        text = m.group(2).strip()
        headings.append("%s %s" % (hashes, text))
    return headings


def find_dropped_headings(old_content, new_content):
    """Return the list of headings (in their original OLD-file order) that
    appear in old_content but not in new_content, under exact-match
    comparison. Duplicate headings in OLD are only reported once."""
    old_headings = extract_headings(old_content)
    new_headings_set = set(extract_headings(new_content))

    dropped = []
    seen = set()
    for heading in old_headings:
        if heading in seen:
            continue
        seen.add(heading)
        if heading not in new_headings_set:
            dropped.append(heading)
    return dropped


def extract_ac_ids(content):
    """Distinct AC\\d+[a-z]? tokens, in first-occurrence order, scanned
    across the WHOLE text (not scoped to headings -- real specs in this
    repo reference ACs inline, e.g. "AC19 (round 30)", not only in heading
    lines). Mirrors the dedupe-on-first-seen, ordered-list contract
    `find_dropped_headings` applies to `extract_headings`'s output --
    `extract_headings` itself does not dedupe (it appends every match
    unconditionally); the dedupe/ordering precedent this function mirrors
    lives in `find_dropped_headings`'s own `seen`-set logic above
    (exercised by `test_duplicate_old_heading_reported_once`).

    Known, accepted risk (documented candidly, same trade-off class as this
    module's exact-heading-match philosophy in the module docstring, and as
    verify.py's own tsc-fingerprint-collision note): a literal
    "AC123"-shaped substring inside unrelated prose (not actually an
    acceptance-criterion reference) would be picked up. No threshold avoids
    this without inventing a structural AC-declaration syntax this repo
    does not have; exact-token-match, deliberately over-inclusive, is the
    same philosophy this file's own module docstring already argues for
    headings.
    """
    ac_ids = []
    seen = set()
    for m in AC_ID_RE.finditer(content):
        token = m.group(0)
        if token in seen:
            continue
        seen.add(token)
        ac_ids.append(token)
    return ac_ids


class _LedgerError(Exception):
    """Internal-only: raised by `_load_deferred_ac_ids` on any
    usage-error-shaped ledger-load problem. `main` catches this and turns
    it into the documented exit-2 usage error -- it never propagates as an
    uncaught traceback, and it never lets a raw
    OSError/ValueError/AttributeError collide with this tool's own
    pre-existing, differently-scoped exit-1 meaning ("headings dropped,
    advisory")."""


def _load_deferred_ac_ids(ledger_path):
    """Load `ledger_path` as JSON and return the union of every entry's
    `deferred_ac_ids` list -- an entry missing the field, or where the
    field is present but not a list, contributes nothing (never an error;
    the field is optional per-entry, and a non-list value is treated as
    contributing nothing rather than crashing: a bare `set().update(None)`
    or `set().update(7)` would raise `TypeError` without this guard).

    Raises `_LedgerError` (never a raw OSError/ValueError/AttributeError)
    on any of: a missing/unreadable/non-UTF-8 file, a file that is not
    valid JSON, a top-level JSON value that is not a list, or a list
    containing any element that is not itself a JSON object (a dict) --
    every one of these is a usage error, never silently treated as "zero
    deferred ACs" (Public interface step 3). The per-entry
    `isinstance(entry, dict)` check is what stops a malformed list element
    from reaching `entry.get(...)` and raising an uncaught
    `AttributeError` (which would default to exit 1, colliding with this
    same tool's pre-existing, differently-scoped exit-1 meaning) -- by the
    time the union step below runs, every entry is already confirmed a
    dict, so `.get` itself cannot raise.
    """
    try:
        with open(ledger_path, encoding="utf-8") as f:
            raw_text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise _LedgerError("could not read ledger %s: %s" % (ledger_path, e))

    try:
        data = json.loads(raw_text)
    except ValueError as e:  # json.JSONDecodeError is a ValueError subclass
        raise _LedgerError("ledger %s is not valid JSON: %s" % (ledger_path, e))

    if not isinstance(data, list):
        raise _LedgerError(
            "ledger %s: top-level JSON value must be a list, got %s"
            % (ledger_path, type(data).__name__)
        )

    deferred = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise _LedgerError(
                "ledger %s: every list element must be a JSON object "
                "(dict), found %r" % (ledger_path, entry)
            )
        raw = entry.get("deferred_ac_ids", [])
        if isinstance(raw, list):
            deferred.update(raw)

    return deferred


def main(argv):
    args = argv[1:]

    # Additive --check-ac-inventory extraction. Strictly optional: when
    # absent, `args` is untouched and every following code path is byte-
    # for-byte identical to the pre-extension behavior.
    ledger_path = None
    if "--check-ac-inventory" in args:
        flag_index = args.index("--check-ac-inventory")
        if flag_index + 1 >= len(args):
            sys.stderr.write(
                "usage: spec_revision_diff.py <old_file> <new_file> "
                "[--check-ac-inventory <hardening_ledger.json>]\n"
            )
            return 2
        ledger_path = args[flag_index + 1]
        args = args[:flag_index] + args[flag_index + 2:]

    if len(args) != 2:
        sys.stderr.write("usage: spec_revision_diff.py <old_file> <new_file>\n")
        return 2

    old_path, new_path = args

    try:
        with open(old_path, encoding="utf-8") as f:
            old_content = f.read()
    except OSError as e:
        sys.stderr.write("could not read %s: %s\n" % (old_path, e))
        return 2

    try:
        with open(new_path, encoding="utf-8") as f:
            new_content = f.read()
    except OSError as e:
        sys.stderr.write("could not read %s: %s\n" % (new_path, e))
        return 2

    # Ledger validated BEFORE any stdout is printed, so a usage-error exit
    # never trails a "success"-looking heading-diff message.
    deferred_set = None
    if ledger_path is not None:
        try:
            deferred_set = _load_deferred_ac_ids(ledger_path)
        except _LedgerError as e:
            sys.stderr.write("%s\n" % (e,))
            return 2

    dropped = find_dropped_headings(old_content, new_content)

    if not dropped:
        print(
            "spec_revision_diff: no headings dropped -- every heading in "
            "%s is also present in %s" % (old_path, new_path)
        )
        heading_exit_code = 0
    else:
        print(
            "spec_revision_diff: %d heading(s) present in %s but ABSENT from %s "
            "-- review before dispatching plan-check:"
            % (len(dropped), old_path, new_path)
        )
        for heading in dropped:
            print("  DROPPED: %s" % heading)
        heading_exit_code = 1

    if ledger_path is None:
        return heading_exit_code

    # --check-ac-inventory extension (AC9-11): cross-check every AC id
    # dropped between OLD and NEW against the ledger's deferred_ac_ids.
    old_acs = extract_ac_ids(old_content)
    new_acs_set = set(extract_ac_ids(new_content))
    dropped_acs = []
    seen_acs = set()
    for ac_id in old_acs:
        if ac_id in seen_acs:
            continue
        seen_acs.add(ac_id)
        if ac_id not in new_acs_set:
            dropped_acs.append(ac_id)

    unaccounted = [ac_id for ac_id in dropped_acs if ac_id not in deferred_set]

    if unaccounted:
        for ac_id in unaccounted:
            print("UNACCOUNTED: %s" % ac_id)
        print(
            "spec_revision_diff: %d AC id(s) dropped between %s and %s are "
            "NOT accounted for in %s's deferred_ac_ids -- resolve before "
            "proceeding" % (len(unaccounted), old_path, new_path, ledger_path)
        )
        return 3

    if dropped_acs:
        print(
            "spec_revision_diff: %d dropped AC id(s) retained as deferred "
            "in %s: %s" % (len(dropped_acs), ledger_path, ", ".join(dropped_acs))
        )
    else:
        print(
            "spec_revision_diff: no AC ids dropped between %s and %s"
            % (old_path, new_path)
        )

    return heading_exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
