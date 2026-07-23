#!/usr/bin/env python3
"""closure_freshness_sweep.py -- Evidence-Gate Phase 5, Item 1 (spec:
loop-team/runs/2026-07-09_evidence-gate-phase5/specs/spec.md).

Purpose: a periodic (NOT per-turn, NOT hook-wired), manually-invocable
re-validation sweep of EVERY EXISTING `CLOSED` heading in `fix_plan.md` --
not just the ones a single prior gate invocation happened to touch. This
closes the residual gap Phase 4's own Non-goals section named explicitly:
that build only ever checked a heading a caller had already identified in
the SAME turn it was closed; nothing periodically re-validated the FULL
existing corpus for evidence that has silently gone stale (a cited file
edited/deleted after closure, or left with uncommitted changes) since the
original closure ran. `sweep()` reuses Phase 1-4's own already-shipped,
frozen functions (`_iter_blocks`, `_proof_required_for_heading`,
`check_single_heading`) directly -- nothing in Phase 1-4 is modified or
reimplemented here.

Hash-only / no-re-execution guarantee: `sweep()` NEVER re-executes a Proof
block's OWN CITED COMMAND (the value of that block's `command` field).
Re-validation is hash-only: the reused v3 freshness check re-computes a
sha256 hash of each cited file's CURRENT on-disk content and compares it
against the sha256 recorded at capture time -- it never launches or
inspects the outcome of running the cited command again, which is exactly
the expensive/dangerous re-execution the source dossier's "Do NOT build"
section warns against. This does NOT mean `sweep()` avoids `subprocess`
entirely: the reused v3 dirty-worktree check legitimately shells out to
`git status` / `git check-ignore` for a heading's CITED FILES (not its
Proof block's command) -- that is existing, already-shipped Phase 2/2b
behavior being reused unchanged, not new re-execution risk this phase
introduces.

Cascade-prevention: before checking any heading, `sweep()` skips any
heading whose own heading-line text ends with this tool's OWN generated
trailing shape (`-- STALE (auto-flagged <date>, <finding>)`), matched as
an ANCHORED SUFFIX, never a bare substring match. Without this exclusion,
a previously-appended STALE follow-up heading (which itself carries the
`CLOSED` marker and a date, per real fix_plan.md convention, but has no
`Proof:` block of its own by design) would re-enter scope on the very
next sweep invocation, get flagged "missing proof block", and cause an
unbounded, self-referential cascade of ever-more STALE wrappers.

CLI (`main(argv)`): reads `fix_plan.md`, runs `sweep()`, and appends one
new, wholly separate `## ... -- STALE (auto-flagged <date>, ...)` heading
per flagged entry -- it never edits an existing heading's own text in
place, and never disturbs an existing heading's own body (including any
`Proof:` block it has). Idempotent-safe: a second same-day run against an
unfixed stale entry does not append a duplicate.

Deferred (NOT this build): `hooks/session_start.sh` wiring is explicitly
OUT OF SCOPE for this build -- Nnamdi's decision after round 4 plan-check
found this one integration point alone caused most of this spec's failed
plan-check rounds (a `__file__` resolving to the literal string
`"<stdin>"`, not a real filesystem path, when piped via `python3 -`,
silently breaking a sys.path-based import). `sweep()` and this module's
own CLI (`main(argv)`) are independently correct and fully usable
standalone today; hook integration is deferred to its own future,
narrowly-scoped follow-up spec. This is a scoping deferral, not fail-open
behavior that exists in this build -- there is no hook code path here at
all to fail open or closed.

Usage:
    python3 closure_freshness_sweep.py [<path/to/fix_plan.md>]

Exit codes:
    0 -- nothing appended (no new STALE follow-up headings were written).
    1 -- one or more STALE follow-up headings were appended.
    2 -- usage/read error.
"""
import os
import re
import sys
from datetime import datetime, timezone

# Reuse fixplan_closure_lint.py's already-shipped, frozen Phase 1-4 scan
# machinery directly (`_iter_blocks`, `_proof_required_for_heading`,
# `check_single_heading`, `CLOSURE_HEADING_RE`, `_default_path`-style
# resolution). Same import-with-fallback convention this project already
# uses elsewhere (run_and_record.py, fixplan_closure_lint.py itself), so
# this module still works standalone if it's ever invoked from a context
# whose sys.path doesn't already include this directory.
try:
    import fixplan_closure_lint as _lint
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import fixplan_closure_lint as _lint

# Cascade-prevention: an ANCHORED SUFFIX pattern matching this tool's own
# generated trailing shape -- requires the ISO-date-and-parenthetical shape
# at the END of the heading text, not a bare substring match anywhere in
# it, so an unrelated, original heading that merely QUOTES the phrase
# "STALE (auto-flagged" in its own prose is never wrongly, permanently
# exempted from being checked.
_STALE_SUFFIX_RE = re.compile(r"-- STALE \(auto-flagged \d{4}-\d{2}-\d{2}, .*\)\s*$")


def sweep(content, target_path):
    """For every CLOSED heading in `content` in-scope per
    `_proof_required_for_heading` (reused directly from
    fixplan_closure_lint.py), run `check_single_heading(content,
    heading_line, target_path, advisory=False)` -- advisory=False because
    this is a periodic health-check, not a live blocking gate, so
    staleness/dirty-worktree findings ARE real findings here, not just
    warnings. Returns a list of `{"heading": ..., "messages": [...]}`
    dicts for every heading with >=1 real finding.

    Never re-executes a Proof block's OWN CITED COMMAND (the value of
    that block's `command` field) -- see module docstring for the full
    hash-only guarantee. This does not mean `subprocess` is never
    invoked: `check_single_heading`'s own reused v3 dirty-worktree check
    legitimately shells out to `git status`/`git check-ignore` for a
    heading's CITED FILES (not its Proof block's command), which is
    existing, already-shipped Phase 2/2b behavior being reused unchanged.

    Cascade-prevention (mandatory): any heading whose own heading-line
    text matches `_STALE_SUFFIX_RE` as an anchored suffix is skipped
    entirely -- excluded from scope before `_proof_required_for_heading`
    is even consulted -- so a previously-appended STALE follow-up heading
    (which has no Proof: block of its own by design) never re-enters
    scope and triggers an unbounded, self-referential cascade.
    """
    flagged = []
    for heading_line, _body_text in _lint._iter_blocks(content):
        if _STALE_SUFFIX_RE.search(heading_line):
            continue  # cascade-prevention: never re-check our own output
        if not _lint._proof_required_for_heading(heading_line):
            continue

        outcome = _lint.check_single_heading(
            content, heading_line, target_path, advisory=False
        )
        messages = outcome.get("messages") or []
        if messages:
            flagged.append({"heading": heading_line, "messages": list(messages)})

    return flagged


def _today_iso():
    """Today's real UTC date as an ISO `YYYY-MM-DD` string -- never a
    hardcoded literal (same gotcha this project's own Phase 3 build
    already paid for once)."""
    return datetime.now(timezone.utc).date().isoformat()


def _stale_prefix(original_heading, today):
    """The text prefix common to every STALE follow-up heading for
    `original_heading` dated exactly `today`, regardless of the specific
    finding text that follows -- used both to detect an already-existing
    same-day follow-up (idempotency) and to build a fresh one."""
    return "%s -- STALE (auto-flagged %s," % (original_heading, today)


def _stale_heading_text(original_heading, today, finding_text):
    """The full new heading LINE text (no leading `## `) for a STALE
    follow-up: `<original heading text> -- STALE (auto-flagged <today's
    ISO date>, <finding text>)`."""
    return "%s -- STALE (auto-flagged %s, %s)" % (original_heading, today, finding_text)


def _insertion_offset(matches, heading_line, content_len):
    """The PRECISE insertion point for a flagged heading: the start
    position of the next `## ` heading match (matching `_iter_blocks`'s
    own internal block-boundary computation exactly), or `content_len` if
    it's the last block. Resolves `heading_line` by TEXT, taking the
    FIRST matching `## ` block in scan order -- same text-keyed lookup
    convention `check_single_heading` itself already uses (see this
    phase's spec Non-goals section for the documented, accepted residual
    risk of two blocks sharing byte-identical heading text)."""
    for i, m in enumerate(matches):
        if m.group(1) == heading_line:
            return matches[i + 1].start() if i + 1 < len(matches) else content_len
    return content_len  # defensive only -- heading_line came from this same content


def main(argv):
    args = argv[1:]
    if len(args) > 1:
        sys.stderr.write("usage: closure_freshness_sweep.py [<path/to/fix_plan.md>]\n")
        return 2

    path = args[0] if args else _lint._default_path()

    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        sys.stderr.write("could not read %s: %s\n" % (path, e))
        return 2

    flagged = sweep(content, path)
    if not flagged:
        print("closure_freshness_sweep: no stale/flagged closures found in %s" % path)
        return 0

    today = _today_iso()
    existing_headings = [h for h, _ in _lint._iter_blocks(content)]
    matches = list(_lint.HEADING_RE.finditer(content))
    content_len = len(content)

    # Collect (offset, new_heading_text) pairs for THIS invocation, per the
    # spec's mandatory multi-insertion algorithm (see module docstring).
    pending = []
    appended_texts = []

    for entry in flagged:
        original_heading = entry["heading"]
        prefix = _stale_prefix(original_heading, today)
        if any(h.startswith(prefix) for h in existing_headings):
            # Idempotent-safe: a STALE follow-up for this EXACT original
            # heading + this EXACT date already exists -- do not append a
            # byte-identical duplicate on a second run the same day.
            continue

        finding_text = "; ".join(entry["messages"])
        new_heading_text = _stale_heading_text(original_heading, today, finding_text)
        offset = _insertion_offset(matches, original_heading, content_len)
        pending.append((offset, "## %s\n" % new_heading_text))
        appended_texts.append(new_heading_text)

    if not pending:
        return 0

    # MANDATORY multi-insertion algorithm -- raw string-offset insertion,
    # processed in REVERSE (descending) offset order, never block-list
    # reconstruction (a naive block-reconstruction approach silently drops
    # any content before the first `## ` heading match, which the real,
    # live fix_plan.md genuinely has). Sorting highest-offset-first means
    # no earlier (lower-offset) insertion's own position is ever
    # invalidated by a later one -- every byte of the original content
    # that isn't an explicit insertion point is preserved automatically,
    # because it is never touched, only sliced around.
    pending.sort(key=lambda pair: pair[0], reverse=True)
    for offset, new_heading_text in pending:
        content = content[:offset] + new_heading_text + content[offset:]

    # Write the final, fully-mutated content back in ONE single write,
    # never one write per insertion.
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        sys.stderr.write("could not write %s: %s\n" % (path, e))
        return 2

    for text in appended_texts:
        print(text)

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
