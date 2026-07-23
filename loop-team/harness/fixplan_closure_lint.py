#!/usr/bin/env python3
"""fixplan_closure_lint.py -- closes H-FIXPLAN-CLOSURE-CONSISTENCY-1.

Deterministic, dependency-free scan of `fix_plan.md` (or any file matching
its `## <heading>` block structure) that catches an entry whose BODY text
claims closure ("PLAN_PASS achieved", "IMPLEMENTATION COMPLETE",
"VERDICT: PASS", or a real git commit SHA reference) while its own HEADING
line does not carry an explicit closure marker. Confirmed live this project
on `H-SUBAGENT-MASKING-1`: Oga appended "IMPLEMENTATION COMPLETE" content
without ever updating the heading from `(OPEN, ...)` to a closed form,
caught only because an independent post-build Verifier happened to grep the
heading directly rather than trust the prose. This script makes that check
repeatable and cheap instead of relying on a Verifier noticing by luck.

Closure-marker convention (matched against this project's OWN real
fix_plan.md, not invented): every genuinely-closed heading in this file
today contains the literal, UPPERCASE token `CLOSED` somewhere in the
heading line, in one of several punctuation shapes: `-- CLOSED`,
`— CLOSED`, `(CLOSED ...)`, or a bare `CLOSED (...)`. There is no single
fixed template -- headings are free text with `CLOSED` appearing somewhere
in them. The marker check is deliberately CASE-SENSITIVE on this uppercase
token, not case-insensitive: a direct grep of the real fix_plan.md found
two real headings that contain lowercase "closed" as ordinary prose,
never as a status marker (e.g. "...content that lands in a git commit
diff can be unreviewed, closed instructionally not structurally..." --
describing something that is explicitly NOT yet closed). A
case-insensitive check would silently treat that prose as a closure
marker and suppress a real mismatch in exactly the entry this whole tool
exists to catch (that block's body separately contains two real
`` commit `<sha>` `` references). So: the heading is only considered
"marked closed" if it contains the exact substring `CLOSED` (all
uppercase); this matches every real closure heading in this project's
fix_plan.md today with zero false suppressions from lowercase prose.

Heading-block convention: a "block" is bounded by an `^## ` line (inclusive
of that heading line) up to -- but not including -- the next `^## ` line,
or end of file. `### `-level and deeper subheadings are NOT block
boundaries; their text is part of the enclosing `## ` block's body. This
project's real fix_plan.md does not use a strict `## H-<ID> ...` heading
convention for every entry (many blocks are free-text titles with no
formal ID at all) -- this script does not require an ID pattern; it treats
every `## ` line as a heading block boundary, matching real practice.

Closure-shaped phrases detected in the BODY (case-insensitive):
  - "PLAN_PASS achieved"
  - "IMPLEMENTATION COMPLETE"
  - "VERDICT: PASS"
  - a real git SHA reference: a backtick-wrapped 7-40 char hex token
    (`` `[0-9a-f]{7,40}` ``) that appears within ~40 characters of the
    word "commit" (case-insensitive, either side, on the same line) --
    checked against the RAW body text (the heading line itself is
    excluded from this scan; a SHA mentioned only in the heading is not
    evidence found in the body).

    This is intentionally a WINDOWED proximity match, not the literal
    `` commit `[0-9a-f]{7,40}` `` string this project's own fix_plan.md
    entry proposing this tool used as its illustrative example. A strict
    "commit" immediately followed by a backtick-SHA misses this project's
    own real usage pattern of listing several SHAs after one "commit(s):"
    lead-in (e.g. "3 commits: `1d732d5`, `08053c4`, `8b470dc`") -- checked
    directly: 39 real backtick-wrapped hex tokens exist in the current
    fix_plan.md, only 16 are immediately preceded by the literal word
    "commit". A bare backtick-hex scan with NO context requirement was
    also tried and rejected: it produces a real false positive on this
    project's own file (a Facebook GraphQL `doc_id` value,
    `` `27835341126073352` ``, which happens to be a 17-digit all-numeric
    token inside the 7-40 length range, with no commit anywhere nearby).
    The proximity window is the middle ground: catches the real multi-SHA
    list usage without matching an unrelated hex-shaped ID.

A body match on the SHA pattern is treated the same as any other
closure-shaped phrase: a real historical commit reference in an entry that
is legitimately still open (e.g. "built X in commit abc1234, but Y is not
yet fixed") IS flagged -- this is intentional per spec ("a pattern matching
a real git SHA reference" is explicitly listed as a trigger phrase, with no
carve-out for a SHA appearing alongside still-open follow-up text). This
tool is deliberately over-inclusive: a false-positive flag costs a human a
few seconds of judgment; a missed closure-mismatch is the exact class of
bug this tool exists to catch. Do not suppress a hit just because the body
also contains hedging language elsewhere in the same block.

Convention matched from `commit_diff_reread.py` / `research_authenticity_check.py`:
stdlib-only, manual `sys.argv` CLI, documented exit codes, plain-text
findings printed to stdout (one per mismatch) rather than JSON -- this tool
is meant for direct human/Oga reading at the end of a build session, per
the spec's own "print each mismatch found" instruction, not for
machine-chained consumption like the other two tools' JSON verdicts.

=== v2 additions (evidence-gate Phase 1, spec: loop-team/runs/
2026-07-08_evidence-gate-phase1/specs/spec.md, "Public interface #2") ===

Everything above this point describes the ORIGINAL v1 heading/body closure-
phrase consistency check, unchanged. v2 ADDS two new checks to the same scan
loop, additive only -- v1's own check is never rewritten, weakened, or
suppressed by these:

  - Proof-block-required check: any `CLOSED` heading dated (per a new,
    standalone ISO-date (YYYY-MM-DD) whole-line date scan -- v1 had no
    date-parsing at all) on or after the module-level cutover constant
    `PROOF_REQUIRED_SINCE` must carry a machine-checkable `Proof:` block in
    its body with `command`, `exit_code`, `proof_snapshot`, and
    `verified_at` fields (`files` optional). Missing/incomplete -> a flag
    containing the substring "missing proof block".
  - Snapshot-cross-check: if a complete Proof block IS found, the
    `proof_snapshot` file it names must exist, parse as JSON, and its
    recorded `command`/`exit_code` must match the Proof block's own claimed
    values (both compared as strings). Any failure -> a flag containing the
    substring "no matching proof snapshot found".

`PROOF_REQUIRED_SINCE` is a "going forward" cutover, not retroactive: a
heading with no parseable date, or a date before the cutover, is exempt from
both new checks (still runs unchanged through the v1 check above). See the
constant's own definition below for the value chosen and why.

The canonical no-op proof command for a closure with no file-specific
evidence to cite (e.g. a pure-prose/documentation fix) is
`python3 run_and_record.py -- true` -- see run_and_record.py's own
docstring for the full rationale (AC13).

=== v3 additions (evidence-gate Phase 2, spec: loop-team/runs/
2026-07-09_evidence-gate-phase2/specs/spec.md, "Public interface") ===

Everything above this point (v1's heading/body check, v2's proof-block-
required check and snapshot-cross-check) is unchanged. v3 ADDS two more
checks, additive only, run ONLY for a heading whose Proof block already
PASSED both v2 checks (complete required fields, snapshot found and
matching) -- a heading v2 already flagged (missing/incomplete block,
fabricated snapshot) never also gets a v3 flag; there is no trustworthy
`files` data to check freshness/dirtiness against in that case.

  - Freshness (staleness) check: for each `path -> recorded_sha256` pair in
    the loaded proof_snapshot JSON's own `files` dict (the real captured
    data, not the Proof block's human-readable `files:` text line), re-hash
    `path`'s CURRENT on-disk content and compare. A mismatch, a missing
    file, or a read failure (`OSError` -- permission denied, or a TOCTOU
    deletion race) all produce the same flag shape: a message containing
    the substring "STALE". `path` is resolved relative to the lint
    process's own CWD at check time (matching `run_and_record.py`'s
    `_detect_files()` convention on the read side) -- callers/fixtures must
    cite files by ABSOLUTE path for this to be CWD-independent.
  - Dirty-worktree check: two parts sharing one resolution rule (compute
    `abs_path = os.path.abspath(path)` first, since `git -C <repo> status
    --porcelain -- <path>` resolves a relative `<path>` against `<repo>`,
    not the lint's own CWD; then resolve `abs_path`'s git repo toplevel,
    reusing `run_and_record.py`'s own `_resolve_repo_for_path()`; skip
    silently -- no flag -- on any resolution or `git status` failure,
    matching v1's `dirty_at_capture: null` "not applicable is never a flag"
    philosophy): (a) per-cited-file, one git invocation sequence per path in
    the snapshot's `files` dict, flagging "evidence file has uncommitted
    changes: <path>"; (b) the file being linted itself, checked ONCE per
    invocation and only if at least one in-scope, v2-passing CLOSED heading
    exists, flagging "evidence file has uncommitted changes: <path> (the
    file being linted)".

=== v3b additions (evidence-gate Phase 2b, spec: loop-team/runs/
2026-07-09_evidence-gate-phase2b-gitignore-visibility/specs/spec.md) ===

Everything above this point (v1, v2, v3) is unchanged. v3b extends v3's own
dirty-worktree resolution logic (`_has_uncommitted_changes()`) ONLY: `git
status --porcelain` silently omits gitignored paths, so an EMPTY status
result does not, by itself, mean "clean" -- it may also mean "git gave zero
signal either way". After an empty `status` result, one more call --
`git -C <repo> check-ignore --quiet -- <abs_path>` -- distinguishes the two:
rc 0 (path matches a gitignore rule) means the empty status result is
UNTRUSTWORTHY, producing a NEW, distinct outcome ("gitignored", not "dirty",
not "clean") flagged with the substring "durability cannot be verified
(gitignored)"; rc 1 (not ignored) means the empty result genuinely is clean,
exactly as v3 already behaved. Any other `check-ignore` outcome (nonzero rc
other than 1, or the subprocess itself failing) fails toward "clean" -- v3b's
own failure mode must never newly introduce a flag v3 didn't already have.
Applies to both dirty-worktree sub-checks (per-cited-file and target-file-
itself), additive to everything else: never suppresses, and is never
suppressed by, STALE or any other existing flag.

=== v4 additions (evidence-gate Phase 3, spec: loop-team/runs/
2026-07-09_evidence-gate-phase3/specs/spec.md) ===

Everything above this point (v1, v2, v3, v3b) is unchanged. v4 ADDS a new
CLI mode, `--selftest`, that does not touch `fix_plan.md` (or any other
real file) at all -- it is a manually-invocable diagnostic mode that guards
against the exact failure this repo already suffered once: a gate whose
config looks right but silently doesn't fire (dossier section 4.6,
"Configured vs fired").

`--selftest` constructs two synthetic, in-memory `## ... CLOSED (...)`
fixtures -- a GOOD one (a real, freshly-generated Proof block, built via
`run_and_record.run_and_record(["true"])` and `run_and_record._render_proof_block`,
so it is byte-for-byte identical in format to what real usage produces) and
a BAD one (all four required Proof fields present, but its `proof_snapshot`
points at a path guaranteed not to exist) -- and runs them through the SAME
`find_mismatches`, `find_proof_flags`, and `find_freshness_and_dirty_flags`
functions real invocations use, unchanged. It asserts the GOOD fixture
produces zero flags and the BAD fixture is flagged with "no matching proof
snapshot found" (the v2 snapshot-cross-check's fabricated-evidence
detection -- the core promise of the whole evidence-gate mechanism).

Every `--selftest` outcome (PASS, FAIL, or an unanticipated ERROR) appends
one heartbeat line to `<gate_dir>/closure_lint_selftest.log` (`_gate_dir()`
resolves `LOOP_GATE_DIR`, default `~/.loop-gate`, same as `run_and_record.py`).
This heartbeat is written on EVERY code path, including a crash, so the
log's own growth (or lack of it) is itself the "configured vs fired"
signal: a stale/non-growing log is visible proof the self-test stopped
running, independent of what it would have found.

`--selftest` does NOT wire into any hook (`hooks/session_start.sh`,
`hooks/loop_stop_guard.py`, `hooks/subagent_stop_gate.py`) -- it is a
standalone diagnostic mode only, invoked manually. Wiring into a hook is
Phase 4/5 territory.

=== v5 addition (Evidence-Gate Phase 4, spec: loop-team/runs/
2026-07-09_evidence-gate-phase4/specs/spec.md) ===

Everything above this point (v1, v2, v3, v3b, v4) is unchanged. v5 adds one
new public function, `check_single_heading(content, heading_line,
target_path, advisory=True)`, that runs the SAME v1/v2/v3 proof-related
checks already defined above against a SINGLE heading rather than the
whole file, for use by the (separately built, later micro-step) automated
hook-path gates in `hooks/loop_stop_guard.py` and
`hooks/subagent_stop_gate.py`. Its one new behavior not present anywhere
above: the LIVE-git-worktree-reading v3 checks (`_freshness_flags_for_snapshot`,
`_dirty_cited_file_flags`) are routed to a separate `warnings` list instead
of the blocking `messages` list when its `advisory` parameter is True (the
hook-path default) -- missing/incomplete/fabricated Proof blocks (v1/v2)
are UNAFFECTED by this and remain unconditionally blocking in every path.
Manual/CLI callers passing `advisory=False` get the fully-blocking,
unchanged Phase 1-3 behavior. See `check_single_heading`'s own docstring
for the full contract.

Exit codes:
  0 -- no mismatches found (neither the v1 check, nor either v2 check, nor
       any v3/v3b check flagged anything).
  1 -- one or more mismatches/flags found, from ANY of the v1, v2, v3, or
       v3b checks (additive -- a clean result from one check never
       suppresses a flag from another).
  2 -- usage error (missing/unreadable file argument).

  `--selftest` mode uses the SAME 0/1/2 exit-code meanings, but evaluated
  against the two synthetic fixtures described above, not against
  `fix_plan.md`: 0 = self-test passed (the mechanism has teeth -- the good
  fixture was clean and the bad, fabricated-evidence fixture was flagged),
  1 = self-test failed (the mechanism regressed -- either fixture behaved
  unexpectedly), 2 = usage error (a malformed `--selftest` invocation) or a
  self-test harness fault (an unanticipated exception during fixture
  construction/evaluation).

Usage:
    python3 fixplan_closure_lint.py [<path/to/fix_plan.md>]
    python3 fixplan_closure_lint.py --selftest

If no path is given, defaults to `fix_plan.md` at the repo root relative to
this script's own location (`../../fix_plan.md` from
`loop-team/harness/`). `--selftest` takes no path argument -- it evaluates
two synthetic, in-memory fixtures instead of reading `fix_plan.md` at all.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

# Reuse research_authenticity_check.py's `- field: value` block/field parser
# for the isolated Proof: span (spec: "import and reuse it for parsing
# `- field: value` lines within this isolated span; do not reimplement that
# parsing"). A script run directly (`python3 fixplan_closure_lint.py ...`)
# gets its own directory on sys.path[0] automatically, so the plain import
# normally succeeds; the except branch is a defensive fallback for the rarer
# case where this module is imported from a process whose sys.path doesn't
# already include this directory (mirrors run_and_record.py's own
# reuse-with-fallback convention for _gate_dir()).
try:
    from research_authenticity_check import parse_blocks as _rac_parse_blocks
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from research_authenticity_check import parse_blocks as _rac_parse_blocks

# v3 (Phase 2) reuse: the dirty-worktree check's git-repo-toplevel resolution
# reuses run_and_record.py's OWN `_resolve_repo_for_path()` directly (spec:
# "reuse `run_and_record.py`'s existing repo-resolution convention") rather
# than reimplementing it -- same import-with-fallback convention as the
# research_authenticity_check import immediately above.
try:
    from run_and_record import _resolve_repo_for_path as _rar_resolve_repo_for_path
    from run_and_record import GIT_TIMEOUT as _RAR_GIT_TIMEOUT
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from run_and_record import _resolve_repo_for_path as _rar_resolve_repo_for_path
    from run_and_record import GIT_TIMEOUT as _RAR_GIT_TIMEOUT

# Phase 3 (evidence-gate Phase 3, spec: loop-team/runs/
# 2026-07-09_evidence-gate-phase3/specs/spec.md) reuse: `_run_selftest()`
# below needs `run_and_record.run_and_record`, `run_and_record._render_proof_block`,
# `run_and_record._proof_dir`, AND `run_and_record._gate_dir`, so a bare
# module import is simpler than a long `from ... import` list. This is a
# DIFFERENT import statement from the existing `from run_and_record import
# _resolve_repo_for_path as _rar_resolve_repo_for_path` block above -- both
# are kept, since `_rar_resolve_repo_for_path` is used by unrelated v3 code
# with its own name.
try:
    import run_and_record
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import run_and_record

HEADING_RE = re.compile(r"^## (.*)$", re.MULTILINE)

# Deliberately case-SENSITIVE: only the uppercase token `CLOSED` counts as
# an explicit closure marker (see module docstring for the real-file
# false-suppression this avoids).
CLOSURE_HEADING_RE = re.compile(r"CLOSED")

# Closure-shaped phrases to look for in a block's BODY text (the heading
# line itself is excluded before this scan runs -- see _find_mismatches).
# Simple literal/regex phrases (the SHA-reference check is handled
# separately by _find_sha_reference below, since it needs a proximity
# window rather than a single fixed regex -- see module docstring).
CLOSURE_PHRASE_PATTERNS = [
    ("PLAN_PASS achieved", re.compile(re.escape("PLAN_PASS achieved"), re.IGNORECASE)),
    ("IMPLEMENTATION COMPLETE", re.compile(re.escape("IMPLEMENTATION COMPLETE"), re.IGNORECASE)),
    ("VERDICT: PASS", re.compile(re.escape("VERDICT: PASS"), re.IGNORECASE)),
]

BACKTICK_SHA_RE = re.compile(r"`([0-9a-fA-F]{7,40})`")
COMMIT_WORD_RE = re.compile(r"commit", re.IGNORECASE)
SHA_PROXIMITY_WINDOW = 40  # characters, either side, same line


def _find_sha_reference(body_text):
    """Return True if `body_text` contains a backtick-wrapped 7-40 char hex
    token within SHA_PROXIMITY_WINDOW characters of the word "commit" on
    the same line (case-insensitive). See module docstring for why this is
    a windowed proximity check rather than strict adjacency or a
    context-free bare-backtick scan."""
    for line in body_text.splitlines():
        sha_matches = list(BACKTICK_SHA_RE.finditer(line))
        if not sha_matches:
            continue
        commit_matches = list(COMMIT_WORD_RE.finditer(line))
        if not commit_matches:
            continue
        for sha_m in sha_matches:
            for commit_m in commit_matches:
                # Distance between the nearer edges of the two spans.
                if sha_m.start() >= commit_m.end():
                    gap = sha_m.start() - commit_m.end()
                else:
                    gap = commit_m.start() - sha_m.end()
                if gap <= SHA_PROXIMITY_WINDOW:
                    return True
    return False


TITLE_TRUNCATE_LEN = 100


def _truncate(text, limit=TITLE_TRUNCATE_LEN):
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _iter_blocks(content):
    """Yield (heading_line, body_text) for every `## ` block in content.

    A block spans from one `^## ` line up to (not including) the next
    `^## ` line, or end of file. The heading_line is the full text after
    `## ` on that line; body_text is everything after the heading line's
    own newline, up to the next block boundary.
    """
    matches = list(HEADING_RE.finditer(content))
    for i, m in enumerate(matches):
        heading_line = m.group(1)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body_text = content[body_start:body_end]
        yield heading_line, body_text


def find_mismatches(content):
    """Return a list of dicts describing every heading/body closure
    mismatch found in `content`. Each dict has:
      {"heading": <full heading text>, "phrases": [<matched phrase names>]}
    """
    mismatches = []
    for heading_line, body_text in _iter_blocks(content):
        if CLOSURE_HEADING_RE.search(heading_line):
            continue  # heading already carries an explicit closure marker

        matched_phrases = [
            name for name, pattern in CLOSURE_PHRASE_PATTERNS
            if pattern.search(body_text)
        ]
        if _find_sha_reference(body_text):
            matched_phrases.append("commit `<sha>` reference")

        if matched_phrases:
            mismatches.append({
                "heading": heading_line,
                "phrases": matched_phrases,
            })
    return mismatches


# =============================================================================
# v2 additions: proof-block-required check + snapshot-cross-check.
# See module docstring's "v2 additions" section for the full design summary.
# =============================================================================

# The "going-forward" cutover date (ISO YYYY-MM-DD): any `CLOSED` heading
# dated ON/AFTER this date must carry a machine-checkable Proof block (see
# module docstring). Set at BUILD time to the actual implementation date
# (2026-07-09), per the spec's explicit instruction NOT to freeze any date
# copied from the spec text itself (a date that looked safely-future when
# the spec was drafted/reviewed across several days could become "today" or
# "the past" by the time this is actually built). Verified against the real,
# live fix_plan.md at build time: the latest existing `CLOSED`-heading date
# in that file is 2026-07-08, one full day before this cutover -- so every
# historical entry (and every v1 test fixture, all dated 2026-07-03) is
# exempt by construction, matching AC8/AC10's requirements. See this
# script's DECISION LOG (build report) for the full reasoning.
PROOF_REQUIRED_SINCE = "2026-07-09"

# New, standalone date-extraction algorithm (v1 has no existing date-parsing
# to reuse -- confirmed by direct read; see spec round-2 fix #1). Scans the
# FULL heading line (not just text after the word CLOSED) for the first
# substring shaped like an ISO date, so it is format-agnostic about where
# the date sits relative to CLOSED (`-- CLOSED (date, ...)`,
# `(CLOSED date, ...)`, `— CLOSED (date, ...)` all parse the same way).
HEADING_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# A Proof block's required fields (spec: "files" is optional).
PROOF_REQUIRED_FIELDS = ("command", "exit_code", "proof_snapshot", "verified_at")

# Extraction-step helpers (spec round-1 fix #4): isolate ONLY the "Proof:"
# line and the contiguous `- field: value` lines immediately following it,
# stopping at the first non-matching line -- so unrelated `- field: value`-
# shaped bullets elsewhere in a heading's free-text body can never pollute
# or shadow the real Proof block.
PROOF_MARKER_LINE = "Proof:"
PROOF_FIELD_LINE_SHAPE_RE = re.compile(r"^\s*-\s*[A-Za-z0-9_]+\s*:\s*.*$")


def _parse_heading_date(heading_line):
    """Return the first `\\d{4}-\\d{2}-\\d{2}`-shaped substring found
    anywhere in `heading_line`, or None if no such substring exists. Known,
    accepted residual (not fixed in Phase 1, per spec): a non-date numeric
    substring shaped exactly like an ISO date elsewhere in a heading's free
    text could false-positive as a date."""
    m = HEADING_DATE_RE.search(heading_line)
    return m.group(0) if m else None


def _proof_required_for_heading(heading_line):
    """True iff `heading_line` carries the explicit `CLOSED` marker (same
    case-sensitive check v1 already uses) AND its parsed date is on/after
    PROOF_REQUIRED_SINCE. A heading with no parseable date, or a date before
    the cutover, is exempt from the new v2 checks entirely (this is a
    deliberate "going forward" cutover, not retroactive -- see module
    docstring)."""
    if not CLOSURE_HEADING_RE.search(heading_line):
        return False
    heading_date = _parse_heading_date(heading_line)
    if heading_date is None:
        return False
    return heading_date >= PROOF_REQUIRED_SINCE  # lexical == chronological for ISO dates


def _extract_proof_span(body_text):
    """Find the line matching (after stripping) exactly "Proof:" within
    `body_text`, then take that line plus every immediately-following line
    that matches the `- field: value` shape, stopping at the first line
    that does not match (a blank line, a new sub-heading, or unrelated
    prose). Returns the isolated span as a single string, or None if no
    "Proof:" line is found in the body at all (treated identically to "no
    parseable Proof block" by the caller)."""
    lines = body_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == PROOF_MARKER_LINE:
            span_lines = [line]
            for follow in lines[i + 1:]:
                if PROOF_FIELD_LINE_SHAPE_RE.match(follow):
                    span_lines.append(follow)
                else:
                    break
            return "\n".join(span_lines)
    return None


def _parse_proof_fields(proof_span):
    """Parse the isolated Proof: span's `- field: value` lines using
    research_authenticity_check.py's own field-line parser (parse_blocks),
    reused rather than reimplemented per spec. The span has no `## ` header
    of its own, so parse_blocks treats it as a single implicit block; we
    just pull that block's parsed fields dict back out."""
    blocks = _rac_parse_blocks(proof_span)
    if not blocks:
        return {}
    return blocks[0]["_fields"]


def _proof_block_status(body_text):
    """Run the proof-block-required check (extraction + required-fields)
    against a single heading's body text. Returns (status, info):
      "missing"    -- no parseable Proof: block at all. info = None.
      "incomplete" -- a Proof: block was found but is missing one or more
                      required fields. info = list of missing field names,
                      in PROOF_REQUIRED_FIELDS declaration order.
      "ok"         -- a complete Proof: block was found. info = the parsed
                      fields dict (ready for the snapshot-cross-check).
    """
    span = _extract_proof_span(body_text)
    if span is None:
        return "missing", None
    fields = _parse_proof_fields(span)
    missing_fields = [f for f in PROOF_REQUIRED_FIELDS if not fields.get(f)]
    if missing_fields:
        return "incomplete", missing_fields
    return "ok", fields


def _snapshot_cross_check(fields):
    """Given a COMPLETE Proof block's parsed fields dict, resolve its
    `proof_snapshot` path and confirm it matches what the Proof block
    claims. Returns None if it matches cleanly, or a flag message
    (containing the substring "no matching proof snapshot found") if it
    does not -- covering: path does not exist, file is not valid JSON, or
    the loaded record's `command`/`exit_code` do not match the Proof
    block's own stated `command`/`exit_code` (both sides compared as
    strings -- round-3 fix: the snapshot JSON stores `exit_code` as a
    Python int, so it must be str()-coerced the same way `command` already
    is, to avoid a false mismatch like `0 == "0"` -> False)."""
    snapshot_path = fields.get("proof_snapshot", "")
    if not snapshot_path or not os.path.isfile(snapshot_path):
        return (
            "no matching proof snapshot found "
            "(proof_snapshot path does not exist: %s)" % snapshot_path
        )

    try:
        with open(snapshot_path, encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return (
            "no matching proof snapshot found "
            "(proof_snapshot could not be parsed as JSON: %s)" % snapshot_path
        )

    # Rendered the same way run_and_record.py renders these fields in its
    # own printed Proof block (space-joined argv; exit_code as a string).
    recorded_command = " ".join(record.get("command") or [])
    recorded_exit_code = str(record.get("exit_code"))
    claimed_command = fields.get("command", "")
    claimed_exit_code = fields.get("exit_code", "")

    if recorded_command != claimed_command or recorded_exit_code != claimed_exit_code:
        return (
            "no matching proof snapshot found "
            "(recorded command/exit_code do not match the Proof block's claim)"
        )

    return None


def find_proof_flags(content):
    """Return a list of dicts describing every v2 proof-related flag found
    in `content` (proof-block-required + snapshot-cross-check), scoped to
    `CLOSED` headings dated on/after PROOF_REQUIRED_SINCE only. Each dict
    has: {"heading": <full heading text>, "message": <flag text>}. Purely
    additive to find_mismatches() -- never suppresses, and is never
    suppressed by, that function's own results."""
    flags = []
    for heading_line, body_text in _iter_blocks(content):
        if not _proof_required_for_heading(heading_line):
            continue

        status, info = _proof_block_status(body_text)
        if status == "missing":
            flags.append({
                "heading": heading_line,
                "message": "missing proof block (no 'Proof:' block found in heading body)",
            })
            continue
        if status == "incomplete":
            flags.append({
                "heading": heading_line,
                "message": (
                    "missing proof block (required field(s) missing: %s)"
                    % ", ".join(info)
                ),
            })
            continue

        # status == "ok": a complete Proof block was found -- cross-check it
        # against the real snapshot it cites.
        mismatch_message = _snapshot_cross_check(info)
        if mismatch_message:
            flags.append({"heading": heading_line, "message": mismatch_message})

    return flags


# =============================================================================
# v3 additions: freshness (staleness) check + dirty-worktree check.
# See module docstring's "v3 additions" section for the full design summary.
# =============================================================================

# A descriptive stand-in for the "heading" field on the ONE-per-invocation
# target-file-itself dirty-worktree flag (spec part (b)) -- that flag is a
# property of the file being linted as a whole, not of any individual
# heading, so there is no real heading text to attach it to.
TARGET_FILE_FLAG_LABEL = "(fix_plan.md itself)"


def _current_content_sha256(path):
    """Compute `path`'s CURRENT content sha256, resolved relative to the
    lint process's own CWD (spec: "Path resolution" -- matches
    `run_and_record.py`'s `_detect_files()` read-side convention). Returns
    None if `path` does not exist, OR if it exists but the read itself fails
    with an `OSError` (permission denied, or a TOCTOU deletion race between
    the `os.path.isfile()` check and the read -- round-3 fix: both cases are
    treated identically by the caller, as "can't confirm this hasn't
    changed", never left to crash the lint invocation uncaught)."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _freshness_flags_for_snapshot(snapshot_record):
    """Given a loaded proof_snapshot JSON record (the real `{path:
    recorded_sha256}` data in its own `files` dict, plus its own
    `captured_at` -- NOT the Proof block's human-readable `files:` text
    line), return a list of "STALE: ..." messages, one per cited file whose
    CURRENT content no longer matches what was recorded. An empty `files`
    dict (the canonical `-- true` no-op case) yields an empty list -- there
    is nothing to freshness-check."""
    flags = []
    verified_at = snapshot_record.get("captured_at", "")
    for path, recorded_sha256 in (snapshot_record.get("files") or {}).items():
        current_sha256 = _current_content_sha256(path)
        if current_sha256 is None:
            flags.append(
                "STALE: %s changed since %s (file no longer exists)" % (path, verified_at)
            )
        elif current_sha256 != recorded_sha256:
            flags.append("STALE: %s changed since %s" % (path, verified_at))
    return flags


def _has_uncommitted_changes(path):
    """Shared resolution rule for BOTH dirty-worktree sub-checks (spec:
    "Shared resolution rule for BOTH parts below" -- round-3 fix): compute
    `abs_path = os.path.abspath(path)` FIRST (matching
    `_compute_dirty_at_capture()`'s own literal first line), since `git -C
    <repo> status --porcelain -- <path>` resolves a RELATIVE `<path>`
    relative to `<repo>` (the `-C` target), not the lint's own CWD -- using
    the raw, possibly-relative snapshot `files` key directly here (as the
    sibling freshness check does, by design, for its CWD-relative
    `os.path.isfile` check) would risk silently checking the wrong file.

    Resolves `abs_path`'s git repo toplevel by reusing
    `run_and_record.py`'s own `_resolve_repo_for_path()`. Skips SILENTLY
    (returns "clean", no flag) on any resolution failure (not inside a git
    repo) or any `git status` subprocess failure (nonzero return code, or
    the subprocess itself erroring) -- matches v1/v2's "not applicable is
    never a flag" philosophy; this is a check for uncommitted evidence, not
    a git health check. A SUCCESSFUL `status` call's stdout is checked for
    emptiness by trimming only the trailing newline (`.rstrip("\\n")`),
    never a full `.strip()` on line content, and never parses/interprets the
    X/Y status columns (this is what actually avoids the leading-space
    staged-vs-unstaged parsing pitfall documented in learnings.md --
    checking emptiness of the whole non-line-stripped output, not by
    skipping repo resolution).

    v3b addition (Phase 2b): a SUCCESSFUL `status` call with EMPTY stdout is
    no longer immediately treated as "clean" -- git silently omits
    gitignored paths from `status` output by default, so an empty result
    alone gives ZERO signal for a gitignored path. One more call, `git -C
    <repo> check-ignore --quiet -- <abs_path>`, disambiguates: rc 0 (matches
    a gitignore rule) means the empty status result is untrustworthy, so
    this returns the new "gitignored" outcome instead of silently claiming
    clean; rc 1 (not ignored) means the empty result genuinely is clean, as
    before. Any other `check-ignore` outcome (unexpected nonzero rc, or the
    subprocess itself failing/timing out) fails toward "clean" -- this
    addition's own failure mode must never newly introduce a flag that
    didn't exist before Phase 2b.

    Returns one of three string outcomes: "dirty", "gitignored", "clean".
    """
    abs_path = os.path.abspath(path)
    repo = _rar_resolve_repo_for_path(abs_path)
    if repo is None:
        return "clean"

    try:
        r = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain", "--", abs_path],
            capture_output=True, text=True, timeout=_RAR_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return "clean"
    if r.returncode != 0:
        return "clean"
    if r.stdout.rstrip("\n"):
        return "dirty"

    # Empty, successful status output -- disambiguate "genuinely clean" from
    # "gitignored, so git gave no real signal" (see docstring above).
    try:
        r2 = subprocess.run(
            ["git", "-C", repo, "check-ignore", "--quiet", "--", abs_path],
            capture_output=True, text=True, timeout=_RAR_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return "clean"
    if r2.returncode == 0:
        return "gitignored"
    return "clean"  # rc 1 (not ignored), or any other rc, fails toward clean


def _dirty_cited_file_flags(snapshot_record):
    """Part (a) of the dirty-worktree check: for each path in the loaded
    snapshot's `files` dict (the same set the freshness check iterates),
    apply `_has_uncommitted_changes()` as a SEPARATE git invocation sequence
    per path (not batched -- keeps "which file is dirty" attribution
    unambiguous). Returns a list of messages, one per cited file that is
    either genuinely dirty ("evidence file has uncommitted changes: <path>")
    or gitignored (v3b addition: "durability cannot be verified
    (gitignored): <path>" -- git gave no dirty-vs-clean signal at all for
    this path). The two outcomes are mutually exclusive per invocation (see
    `_has_uncommitted_changes()`'s own three-way return contract); a
    genuinely clean, non-ignored path produces no message at all."""
    flags = []
    for path in (snapshot_record.get("files") or {}):
        outcome = _has_uncommitted_changes(path)
        if outcome == "dirty":
            flags.append("evidence file has uncommitted changes: %s" % path)
        elif outcome == "gitignored":
            flags.append("durability cannot be verified (gitignored): %s" % path)
    return flags


def _load_snapshot_record(snapshot_path):
    """Load and parse a proof_snapshot JSON file for v3's own use. Returns
    the parsed dict, or None if the path is empty/missing or fails to parse
    (mirrors `_snapshot_cross_check()`'s own OSError/ValueError handling, but
    kept as a separate helper rather than refactoring that function itself
    -- v2's existing checks must remain completely unchanged, per spec).
    In normal operation this is only ever called for a heading whose Proof
    block already passed v2's own snapshot-cross-check moments earlier in
    the same run, so a load failure here is not an expected path -- kept
    defensive (return None, caller skips) rather than assumed unreachable."""
    if not snapshot_path or not os.path.isfile(snapshot_path):
        return None
    try:
        with open(snapshot_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def find_freshness_and_dirty_flags(content, target_path):
    """Return a list of dicts describing every v3 (freshness + dirty-
    worktree) flag found in `content`, scoped ONLY to headings that (a) are
    in-scope per `_proof_required_for_heading()` (unchanged from v2), AND
    (b) already have a Proof block that PASSED both of v2's own checks
    (`_proof_block_status()` returns "ok", AND `_snapshot_cross_check()`
    returns None) -- reusing those existing functions directly rather than
    reimplementing their scoping/check-result logic, per spec. A heading v2
    already flagged (missing/incomplete block, fabricated snapshot) never
    also gets a v3 flag here -- there is no trustworthy `files` data to
    check freshness/dirtiness against in that case.

    Each dict has: {"heading": <full heading text, or TARGET_FILE_FLAG_LABEL
    for the one-per-invocation target-file-itself flag>, "message": <flag
    text>}. Purely additive to find_mismatches() and find_proof_flags() --
    never suppresses, and is never suppressed by, either of those functions'
    own results.

    The target-file-itself dirty-worktree check (spec part (b)) runs ONCE
    per invocation (not once per heading), and ONLY if at least one
    in-scope, v2-passing CLOSED heading was found above -- "nothing to
    protect, skip" per spec."""
    flags = []
    any_in_scope_passing_heading = False

    for heading_line, body_text in _iter_blocks(content):
        if not _proof_required_for_heading(heading_line):
            continue

        status, info = _proof_block_status(body_text)
        if status != "ok":
            continue  # v2's own missing/incomplete flag already covers this heading

        mismatch_message = _snapshot_cross_check(info)
        if mismatch_message is not None:
            continue  # v2's own snapshot-cross-check flag already covers this heading

        # This heading passed BOTH v2 checks -- eligible for v3 checking.
        any_in_scope_passing_heading = True

        snapshot_record = _load_snapshot_record(info.get("proof_snapshot", ""))
        if snapshot_record is None:
            continue  # defensive only -- see _load_snapshot_record's own docstring

        for message in _freshness_flags_for_snapshot(snapshot_record):
            flags.append({"heading": heading_line, "message": message})
        for message in _dirty_cited_file_flags(snapshot_record):
            flags.append({"heading": heading_line, "message": message})

    if any_in_scope_passing_heading:
        target_outcome = _has_uncommitted_changes(target_path)
        if target_outcome == "dirty":
            flags.append({
                "heading": TARGET_FILE_FLAG_LABEL,
                "message": (
                    "evidence file has uncommitted changes: %s (the file being linted)"
                    % target_path
                ),
            })
        elif target_outcome == "gitignored":  # v3b addition
            flags.append({
                "heading": TARGET_FILE_FLAG_LABEL,
                "message": (
                    "durability cannot be verified (gitignored): %s (the file being linted)"
                    % target_path
                ),
            })

    return flags


# =============================================================================
# v4 additions: `--selftest` diagnostic mode.
# See module docstring's "v4 additions" section for the full design summary.
# =============================================================================


def _today_iso():
    """Return today's real UTC date as an ISO `YYYY-MM-DD` string. Used by
    `_run_selftest()` to build synthetic heading dates that are always
    on/after PROOF_REQUIRED_SINCE at run time -- deliberately NOT a
    hardcoded literal date, per this build's own known gotcha (a literal
    date copied from spec-drafting time would eventually fall behind
    "today")."""
    return datetime.now(timezone.utc).date().isoformat()


def _append_selftest_heartbeat(status, detail):
    """Append one line to <gate_dir>/closure_lint_selftest.log recording
    that --selftest fired and what it found. Called on EVERY --selftest
    invocation outcome (PASS, FAIL, or an unanticipated ERROR) -- never
    skipped -- so the log's own growth is itself the "configured vs fired"
    signal (dossier section 4.6): a stale/non-growing log is visible proof
    the self-test stopped running, independent of what it would have found."""
    gate_dir = run_and_record._gate_dir()
    os.makedirs(gate_dir, exist_ok=True)
    log_path = os.path.join(gate_dir, "closure_lint_selftest.log")
    line = "%s SELFTEST %s%s\n" % (
        datetime.now(timezone.utc).isoformat(),
        status,
        (" detail=%r" % detail) if detail else "",
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def _run_selftest():
    """Session-start self-test (dossier section 4.6): construct one
    synthetic GOOD fixture (a real, freshly-generated Proof block) and one
    synthetic BAD fixture (a complete-but-fabricated Proof block whose
    `proof_snapshot` is guaranteed not to exist), run both through the same
    `find_mismatches`/`find_proof_flags`/`find_freshness_and_dirty_flags`
    checks real invocations use, and assert the good one is clean and the
    bad one is flagged with "no matching proof snapshot found". Appends a
    heartbeat line to `<gate_dir>/closure_lint_selftest.log` on every
    outcome, including an unanticipated crash, so the log's own growth is
    itself a "did the self-test actually fire" signal. Returns an int exit
    code: 0 (PASS), 1 (FAIL -- the mechanism regressed), or 2 (usage error
    or a self-test harness fault)."""
    try:
        # --- Step A: build the GOOD fixture. ---------------------------
        good_heading = (
            "SELFTEST-GOOD -- CLOSED (synthetic self-test fixture, generated "
            "%s; not a real fix_plan.md entry)" % _today_iso()
        )
        exit_code, record, snapshot_path = run_and_record.run_and_record(["true"])
        if record is None:
            raise RuntimeError(
                "could not construct good fixture: run_and_record "
                "failed to execute 'true' (exit_code=%s)" % exit_code
            )
        good_body = (
            "\nSynthetic self-test fixture. Not a real closure. Generated by "
            "fixplan_closure_lint.py --selftest.\n\n"
            + run_and_record._render_proof_block(record, snapshot_path)
            + "\n"
        )

        # --- Step B: build the BAD fixture. -----------------------------
        bad_heading = (
            "SELFTEST-BAD -- CLOSED (synthetic self-test fixture, generated "
            "%s; not a real fix_plan.md entry)" % _today_iso()
        )
        fabricated_snapshot_path = os.path.join(
            run_and_record._proof_dir(), "SELFTEST-FABRICATED-DO-NOT-CREATE.json"
        )
        if os.path.isfile(fabricated_snapshot_path):
            raise RuntimeError(
                "selftest sentinel path unexpectedly exists: %s"
                % fabricated_snapshot_path
            )
        bad_body = (
            "\nSynthetic self-test fixture. Not a real closure. Generated by "
            "fixplan_closure_lint.py --selftest.\n\n"
            "Proof:\n"
            "- command: true\n"
            "- exit_code: 0\n"
            "- proof_snapshot: %s\n"
            "- verified_at: %s\n"
            % (fabricated_snapshot_path, datetime.now(timezone.utc).isoformat())
        )

        # --- Step C: assemble and evaluate. -----------------------------
        content = "## %s\n%s\n## %s\n%s\n" % (
            good_heading, good_body, bad_heading, bad_body,
        )
        target_path = os.path.join(
            tempfile.gettempdir(), "fixplan_closure_lint_selftest_target.md"
        )

        mismatches = find_mismatches(content)
        proof_flags = find_proof_flags(content)
        phase2_flags = find_freshness_and_dirty_flags(content, target_path)

        def _for_heading(entries, heading):
            return [e for e in entries if e["heading"] == heading]

        mismatches_total = len(mismatches)

        good_flags = (
            _for_heading(mismatches, good_heading)
            + _for_heading(proof_flags, good_heading)
            + _for_heading(phase2_flags, good_heading)
        )
        good_ok = len(good_flags) == 0

        bad_proof_flags = _for_heading(proof_flags, bad_heading)
        bad_ok = any(
            "no matching proof snapshot found" in f["message"]
            for f in bad_proof_flags
        )

        selftest_pass = good_ok and bad_ok and (mismatches_total == 0)

        # --- Step D: print, log, return. ---------------------------------
        if selftest_pass:
            print("fixplan_closure_lint: --selftest PASS")
            print("  good fixture: 0 flags (as expected)")
            print(
                '  bad fixture: flagged with "no matching proof snapshot found" '
                "(as expected)"
            )
            _append_selftest_heartbeat("PASS", "")
            return 0

        print(
            "fixplan_closure_lint: --selftest FAIL -- the closure-lint "
            "mechanism is not behaving as expected"
        )
        fail_reasons = []
        if not good_ok:
            fail_reasons.append("good")
            print(
                "  good fixture: %d unexpected flag(s): %s"
                % (
                    len(good_flags),
                    "; ".join(
                        f["message"] if "message" in f else ", ".join(f.get("phrases", []))
                        for f in good_flags
                    ),
                )
            )
        if not bad_ok:
            fail_reasons.append("bad")
            print(
                '  bad fixture: NOT flagged with "no matching proof snapshot found" '
                "(got: %s)"
                % (
                    "; ".join(f["message"] for f in bad_proof_flags)
                    if bad_proof_flags
                    else "no proof flags at all"
                )
            )
        if mismatches_total != 0:
            fail_reasons.append("harness")
            print(
                "  harness fixture construction error: find_mismatches() "
                "unexpectedly fired %d time(s) on synthetic CLOSED headings"
                % mismatches_total
            )

        _append_selftest_heartbeat("FAIL", ", ".join(fail_reasons))
        return 1
    except Exception as e:
        _append_selftest_heartbeat("ERROR", str(e))
        sys.stderr.write("fixplan_closure_lint: --selftest ERROR -- %s\n" % e)
        return 2


# =============================================================================
# v5 addition (Evidence-Gate Phase 4, spec: loop-team/runs/
# 2026-07-09_evidence-gate-phase4/specs/spec.md, "check_single_heading,
# redesigned contract") -- check_single_heading(). See module docstring's
# "v5 addition" section for the full design summary.
# =============================================================================


def check_single_heading(content, heading_line, target_path, advisory=True):
    """Run v1/v2/v3 proof-related checks against ONE heading (not the whole
    file), for use by Evidence-Gate Phase 4's automated hook path (Parts
    C/D/E in `hooks/loop_stop_guard.py`, the Fifth responsibility in
    `hooks/subagent_stop_gate.py`) as well as manual/CLI callers.

    Reuses `_proof_required_for_heading`, `_proof_block_status`, and
    `_snapshot_cross_check` directly -- these ALWAYS contribute to
    "messages" (never "warnings"), regardless of `advisory`: a
    missing/incomplete/fabricated Proof block stays unconditionally
    blocking in every path (spec theme 4's explicit scope -- only the
    LIVE-git-worktree-reading v3 checks become advisory-only, never these).

    v3 checks (`_freshness_flags_for_snapshot`, `_dirty_cited_file_flags`)
    run ONLY when `_proof_block_status` returns "ok" AND
    `_snapshot_cross_check` returns None (spec theme 6's explicit v2-gate,
    mirroring `find_freshness_and_dirty_flags`'s own real gating exactly --
    a heading v2 already flagged never also gets a v3 flag, since there is
    no trustworthy `files` data to check freshness/dirtiness against in
    that case). When they DO run, their messages go into "warnings" if
    `advisory` is True (the hook-path default -- theme 4's advisory-vs-
    blocking split), or into "messages" if `advisory` is False (manual/
    `--selftest`/CLI callers, fully blocking, unchanged Phase 1-3 behavior).

    Deliberately excludes `find_freshness_and_dirty_flags`'s OWN separate
    "target file itself" dirty-worktree flag (that check is a once-per-
    invocation, whole-file-level concern by design -- see that function's
    own docstring -- not a per-heading one; running it here too would
    re-fire it once per armed heading in the same turn instead of once per
    invocation). Callers that need that whole-file check still get it from
    `find_freshness_and_dirty_flags` directly, unaffected by this addition.

    `target_path` is accepted for interface symmetry with
    `find_freshness_and_dirty_flags(content, target_path)` and for any
    future per-heading, target-relative check; the v3 checks reused here
    operate only on the snapshot's own cited `files`, never on the file
    being linted itself, so `target_path` is not otherwise read by this
    function today.

    Returns `{"messages": [...blocking...], "warnings": [...advisory...]}`.
    If `heading_line` is not found in `content`'s `_iter_blocks()` output,
    returns `{"messages": [], "warnings": []}`.
    """
    body_text = None
    for h, b in _iter_blocks(content):
        if h == heading_line:
            body_text = b
            break
    if body_text is None:
        return {"messages": [], "warnings": []}

    messages = []
    warnings = []

    if not _proof_required_for_heading(heading_line):
        return {"messages": messages, "warnings": warnings}

    status, info = _proof_block_status(body_text)
    if status == "missing":
        messages.append("missing proof block (no 'Proof:' block found in heading body)")
        return {"messages": messages, "warnings": warnings}
    if status == "incomplete":
        messages.append(
            "missing proof block (required field(s) missing: %s)" % ", ".join(info)
        )
        return {"messages": messages, "warnings": warnings}

    # status == "ok": a complete Proof block was found -- cross-check it
    # against the real snapshot it cites (v2's own check, unconditionally
    # blocking regardless of `advisory`).
    mismatch_message = _snapshot_cross_check(info)
    if mismatch_message:
        messages.append(mismatch_message)
        return {"messages": messages, "warnings": warnings}

    # v2 passed both checks -- eligible for v3 (theme 6's explicit gate).
    v3_messages = []
    snapshot_record = _load_snapshot_record(info.get("proof_snapshot", ""))
    if snapshot_record is not None:
        v3_messages.extend(_freshness_flags_for_snapshot(snapshot_record))
        v3_messages.extend(_dirty_cited_file_flags(snapshot_record))

    if advisory:
        warnings.extend(v3_messages)
    else:
        messages.extend(v3_messages)

    return {"messages": messages, "warnings": warnings}


def _default_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "fix_plan.md"))


def main(argv):
    args = argv[1:]

    # v4 addition (evidence-gate Phase 3): --selftest is a distinct CLI
    # mode with its own invocation shape, checked BEFORE the existing
    # multi-arg usage check below -- so a malformed --selftest invocation
    # (e.g. `--selftest somepath`) produces a clear, selftest-specific
    # usage error instead of being silently absorbed as a literal file
    # path by the pre-existing single-path branch.
    if args == ["--selftest"]:
        return _run_selftest()
    if args and args[0] == "--selftest":
        sys.stderr.write("usage: fixplan_closure_lint.py --selftest\n")
        return 2

    if len(args) > 1:
        sys.stderr.write("usage: fixplan_closure_lint.py [<path/to/fix_plan.md>]\n")
        return 2

    path = args[0] if args else _default_path()

    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        sys.stderr.write("could not read %s: %s\n" % (path, e))
        return 2

    mismatches = find_mismatches(content)
    proof_flags = find_proof_flags(content)  # v2 addition, additive only
    phase2_flags = find_freshness_and_dirty_flags(content, path)  # v3 addition, additive only

    if not mismatches and not proof_flags and not phase2_flags:
        print("fixplan_closure_lint: no mismatches found in %s" % path)
        return 0

    if mismatches:
        print("fixplan_closure_lint: %d mismatch(es) found in %s" % (len(mismatches), path))
        for m in mismatches:
            print("")
            print("  HEADING: %s" % _truncate(m["heading"]))
            print("  TRIGGERED BY: %s" % ", ".join(m["phrases"]))

    if proof_flags:
        if mismatches:
            print("")
        print("fixplan_closure_lint: %d proof issue(s) found in %s" % (len(proof_flags), path))
        for f in proof_flags:
            print("")
            print("  HEADING: %s" % _truncate(f["heading"]))
            print("  PROOF ISSUE: %s" % f["message"])

    if phase2_flags:
        if mismatches or proof_flags:
            print("")
        print(
            "fixplan_closure_lint: %d freshness/dirty-worktree issue(s) found in %s"
            % (len(phase2_flags), path)
        )
        for f in phase2_flags:
            print("")
            print("  HEADING: %s" % _truncate(f["heading"]))
            print("  ISSUE: %s" % f["message"])

    # Additive: any check's flags alone are enough to force exit 1 -- a clean
    # result from one check must never suppress another check's flag.
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
