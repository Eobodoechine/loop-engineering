#!/usr/bin/env python3
"""evidence_ledger.py -- Evidence-Gate Phase 5, Item 3 (spec: loop-team/runs/
2026-07-09_evidence-gate-phase5/specs/spec.md, "Item 3").

Generates a machine-derived index (`evidence_ledger.jsonl`) of every CLOSED
`fix_plan.md` heading that carries a complete, v2-passing `Proof:` block.
This exists to satisfy an explicit "Do NOT build" guard from the source
research dossier: "A separate, hand-maintained JSON/YAML evidence ledger
file kept in sync with fix_plan.md's prose by a human/agent remembering to
update both... If a ledger file exists at all, it must be machine-derived
from the inline Proof blocks, never a second hand-authored source of the
same fact." Every field in every ledger entry is read directly, verbatim,
from that heading's own already-parsed Proof block -- nothing here is
inferred, computed, or invented; `build_ledger()` is a pure read/transform
over `fix_plan.md`'s own text, so the ledger is always fully disposable and
reproducible from `fix_plan.md` alone, never a second hand-authored source
that can silently drift out of sync with it.

HASH-ONLY / NO-RE-EXECUTION GUARANTEE: this module never re-executes a
Proof block's own cited `command`, and never shells out to anything at all.
It only reads (a) `fix_plan.md`'s text, via the frozen Phase 1-4 scanning
functions in `fixplan_closure_lint.py` (`_iter_blocks`,
`_proof_required_for_heading`, `_proof_block_status`,
`_snapshot_cross_check` -- reused directly here, never re-derived), and (b)
the already-recorded `proof_snapshot` JSON files those functions load and
hash-compare against on-disk file content. Whether a cited command was ever
actually re-run is simply not a question this file asks or answers -- it
only reports what a Proof block already claims and what its own snapshot
already recorded.

CLI `main(argv)`: reads `fix_plan.md` (same default-path convention as
`fixplan_closure_lint.py`'s own `_default_path()`, optionally overridable
via a single path argument), calls `build_ledger()`, and ALWAYS fully
regenerates `<gate_dir>/evidence_ledger.jsonl` from the current file content
on every invocation (never an incremental append-if-new-since-last-run) --
one JSON object per line, written atomically (temp file + `os.replace`,
matching `run_and_record.py`'s own atomic-write convention for its snapshot
files) so a reader never observes a partially-written file. Running the CLI
twice with no change to `fix_plan.md` produces byte-identical output, since
`build_ledger()` is a pure function of its input content and every entry's
field order is fixed.

Usage:
    python3 evidence_ledger.py [<path/to/fix_plan.md>]
"""
import json
import os
import sys

# Reuse fixplan_closure_lint.py's own scanning primitives directly -- never
# re-derive this scan (spec: "reuse _iter_blocks + _proof_required_for_heading
# + _proof_block_status + _snapshot_cross_check directly"). Same
# reuse-with-fallback convention used throughout this project's harness
# scripts (see fixplan_closure_lint.py's own imports from
# research_authenticity_check.py / run_and_record.py, and run_and_record.py's
# own _gate_dir() import below): a script run directly gets its own
# directory on sys.path[0] automatically, so the plain import normally
# succeeds; the except branch is a defensive fallback for the rarer case
# where this module is imported from a process whose sys.path doesn't
# already include this directory.
try:
    from fixplan_closure_lint import (
        _iter_blocks,
        _proof_required_for_heading,
        _proof_block_status,
        _snapshot_cross_check,
    )
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from fixplan_closure_lint import (
        _iter_blocks,
        _proof_required_for_heading,
        _proof_block_status,
        _snapshot_cross_check,
    )

# _gate_dir(): reuse commit_diff_reread.py's real implementation if it's
# importable, otherwise fall back to a duplicate of its exact logic -- same
# reuse-with-fallback convention run_and_record.py itself uses for this same
# function (matched exactly per this build's spec: "same `_gate_dir()`
# reuse-with-fallback convention as `run_and_record.py`").
try:
    from commit_diff_reread import _gate_dir as _reused_gate_dir

    def _gate_dir():
        return _reused_gate_dir()
except ImportError:
    def _gate_dir():
        """Duplicated from commit_diff_reread.py's _gate_dir() (import
        fallback -- see comment above). Keep in sync with that file's own
        definition if it ever changes."""
        return os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))


def _parse_files_field(files_value):
    """Split a Proof block's own human-readable `files:` value (a
    comma-joined string like "path1, path2", matching the exact format
    `run_and_record._render_proof_block()` writes) into a list of individual
    path strings. Returns [] if the field is absent/empty -- never invented
    from the proof_snapshot's own separately-recorded `files` dict; the
    ledger's `files` entry reflects the Proof block's OWN cited text only,
    per spec ("fields read directly from the parsed Proof block, never
    inferred/invented")."""
    if not files_value:
        return []
    return [f.strip() for f in files_value.split(",") if f.strip()]


def build_ledger(content):
    """For every CLOSED heading in `content` carrying a complete, v2-passing
    Proof: block, emit one dict: {"heading": ..., "command": ...,
    "exit_code": ..., "proof_snapshot": ..., "verified_at": ..., "files":
    [...]} -- every field read directly from that heading's own parsed Proof
    block, never inferred/invented. Returns a list of these dicts, in the
    same order the headings appear in `content`.

    Scoping reuses fixplan_closure_lint.py's own established gating
    combination exactly (the same combination find_freshness_and_dirty_flags()
    and check_single_heading() already use to decide "does this heading have
    a Proof block that genuinely v2-passes"): a heading is in scope only if
    (a) _proof_required_for_heading() confirms it's a CLOSED heading dated
    on/after the proof-required cutover, (b) _proof_block_status() finds a
    COMPLETE Proof block (status "ok", not "missing" or "incomplete"), and
    (c) _snapshot_cross_check() finds no mismatch against the real, on-disk
    proof_snapshot (returns None, not a flag message) -- i.e. the Proof
    block genuinely v2-passes, not merely present."""
    entries = []
    for heading_line, body_text in _iter_blocks(content):
        if not _proof_required_for_heading(heading_line):
            continue

        status, info = _proof_block_status(body_text)
        if status != "ok":
            continue  # missing/incomplete -- not a complete Proof block

        mismatch_message = _snapshot_cross_check(info)
        if mismatch_message is not None:
            continue  # fabricated/mismatched -- not a v2-passing Proof block

        entries.append({
            "heading": heading_line,
            "command": info.get("command", ""),
            "exit_code": info.get("exit_code", ""),
            "proof_snapshot": info.get("proof_snapshot", ""),
            "verified_at": info.get("verified_at", ""),
            "files": _parse_files_field(info.get("files", "")),
        })
    return entries


def _default_path():
    """Same default-path convention as fixplan_closure_lint.py's own
    _default_path(): fix_plan.md at the repo root, relative to this script's
    own location (loop-team/harness/../../fix_plan.md)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "fix_plan.md"))


def _write_ledger_atomic(entries, ledger_path):
    """Write `entries` to `ledger_path` as one JSON object per line, via an
    atomic temp-file-then-`os.replace` write (matching `run_and_record.py`'s
    own atomic-write convention for its snapshot files) -- a reader never
    observes a partially-written file. Always a full, from-scratch
    regeneration (the caller passes the complete, freshly-built entries list
    every time); this is what keeps the output reproducible rather than
    accumulating/drifting."""
    gate_dir = os.path.dirname(ledger_path)
    os.makedirs(gate_dir, exist_ok=True)
    tmp_path = ledger_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry))
            f.write("\n")
    os.replace(tmp_path, ledger_path)


def main(argv):
    args = argv[1:]
    if len(args) > 1:
        sys.stderr.write("usage: evidence_ledger.py [<path/to/fix_plan.md>]\n")
        return 2

    path = args[0] if args else _default_path()

    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        sys.stderr.write("could not read %s: %s\n" % (path, e))
        return 2

    entries = build_ledger(content)

    ledger_path = os.path.join(_gate_dir(), "evidence_ledger.jsonl")
    _write_ledger_atomic(entries, ledger_path)

    print(
        "evidence_ledger: %d entr%s written to %s"
        % (len(entries), "y" if len(entries) == 1 else "ies", ledger_path)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
