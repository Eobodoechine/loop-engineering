#!/usr/bin/env python3
"""
closure_touch_scan.py -- shared, importable position-based scanner for
Evidence-Gate Phase 4 Part A (spec: loop-team/runs/
2026-07-09_evidence-gate-phase4/specs/spec.md, "Part A, redesigned --
find_touched_closed_headings (position-based, scope-limited)").

Same placement rationale as `hooks/commit_scope_scan.py` (spec.md's own
"Public interface summary" section, verbatim): a pure, stdlib-only function
shared by BOTH `hooks/loop_stop_guard.py` (Oga's own Stop hook, Part C) and
`hooks/subagent_stop_gate.py` (a sub-agent's SubagentStop hook, Part B/E)
must live OUTSIDE both hook files so neither one imports the other's
internals -- the exact coupling this module's own placement exists to
avoid. This module is stdlib-only and imports NEITHER `loop_stop_guard.py`
NOR `subagent_stop_gate.py`.

Unlike `commit_scope_scan.py` (which is fully self-contained and needs no
cross-directory import at all -- its own module docstring explains it
copies a trivial helper inline rather than importing it), THIS module does
need six names from `loop-team/harness/fixplan_closure_lint.py`
(`_iter_blocks`, `_extract_proof_span`, `PROOF_MARKER_LINE`,
`PROOF_FIELD_LINE_SHAPE_RE`, `CLOSURE_HEADING_RE`, `HEADING_RE`) --
reimplementing the heading-block/Proof-span parsing rules here would
directly violate this project's "reuse, do not modify or reimplement
existing tested functions" convention (spec.md, Part A step 2). The import
mechanism mirrors the SAME try/except-ImportError-then-conditional-
sys.path.insert idiom `fixplan_closure_lint.py` itself already uses for its
own (same-directory) imports of `research_authenticity_check` and
`run_and_record` -- generalized here to the cross-directory case (`hooks/`
importing from the sibling `loop-team/harness/` directory), which is the
same general house convention `hooks/subagent_stop_gate.py` also uses
(inserting a sibling directory onto `sys.path` before importing across the
`hooks/` <-> `loop-team/` boundary) -- see the import block below.

`find_touched_closed_headings(tool_uses, target_fix_plan_path)` is a PURE
function (spec.md Public interface, "Part A, redesigned"): given tool_use
dicts and the resolved fix_plan.md path, it identifies which CLOSED
heading(s) a turn/dispatch genuinely authored or modified the
CLOSURE-RELEVANT portion of (the heading line itself, or its Proof: block
span) -- NOT any edit anywhere in that heading's free-text body.

Algorithm summary (position-based, replaces round-1's rejected
substring-containment approach -- see spec.md theme 2 for the full
rationale): re-read `target_fix_plan_path` FRESH from disk (post-edit state
is authoritative at hook-invocation time); recover each `## ` block's own
character-span boundaries by independently re-running `HEADING_RE.finditer()`
(imported, reused, not reimplemented) alongside `_iter_blocks`'s own
yielded (heading_line, body_text) pairs; for each Write/Edit/MultiEdit
tool_use touching the target file, find every offset its authored text
occupies in the freshly-read content and test whether that offset falls
within the owning block's heading line or Proof: span (armed) versus
ordinary body prose (not armed, per theme 2's over-fire fix); filter the
armed set to headings carrying the literal CLOSED marker; return the
deduplicated list.

`tool_uses` here is the PUBLIC, documented raw tool_use dict shape
(`{"type": "tool_use", "name": ..., "input": {...}}`) -- Part C's own text
floats an OPTIONAL internal adaptation (accepting the
`_rh_structural_writes()` 3-tuple shape instead) purely for ONE caller's
(Part C's) own convenience; that is Part C's own wiring decision to make
when Part C itself is built (a later micro-step), not a change to this
function's documented public contract.
"""
import os
import re
import sys

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
_HARNESS_DIR = os.path.normpath(
    os.path.join(_HOOKS_DIR, "..", "loop-team", "harness")
)

try:
    from fixplan_closure_lint import (
        _iter_blocks,
        _extract_proof_span,
        PROOF_MARKER_LINE,
        PROOF_FIELD_LINE_SHAPE_RE,
        CLOSURE_HEADING_RE,
        HEADING_RE,
    )
except ImportError:
    if _HARNESS_DIR not in sys.path:
        sys.path.insert(0, _HARNESS_DIR)
    from fixplan_closure_lint import (
        _iter_blocks,
        _extract_proof_span,
        PROOF_MARKER_LINE,
        PROOF_FIELD_LINE_SHAPE_RE,
        CLOSURE_HEADING_RE,
        HEADING_RE,
    )


# Tool names (case-insensitive) whose `input` can author fix_plan.md content.
# Matches loop_stop_guard.py's own `_RH_WRITE_TOOLS` set exactly (Write/Edit/
# MultiEdit are the only tool_use kinds that write file content this repo's
# structural-write detection recognizes).
_TOUCH_TOOLS = {"write", "edit", "multiedit"}


def _target_realpath(target_fix_plan_path):
    """Realpath-resolve target_fix_plan_path the SAME way
    `_rh_structural_writes()` resolves each write's own file_path
    (`os.path.realpath(os.path.expanduser(...))`) -- so a tool_use's own
    touched-file comparison uses one consistent resolution rule on both
    sides."""
    return os.path.realpath(os.path.expanduser(target_fix_plan_path))


def _tool_use_targets_file(tool_input, target_real):
    """True iff `tool_input` (a Write/Edit/MultiEdit tool_use's own `input`
    dict) names a file_path/path that realpath-resolves to `target_real`.
    Mirrors `_rh_structural_writes()`'s own `input.get("file_path") or
    input.get("path")` + realpath convention (hooks/loop_stop_guard.py),
    per spec.md Part A step 3's explicit instruction: "realpath match, same
    convention as _rh_structural_writes"."""
    if not isinstance(tool_input, dict):
        return False
    fp = tool_input.get("file_path") or tool_input.get("path") or ""
    if not isinstance(fp, str) or not fp:
        return False
    try:
        return os.path.realpath(os.path.expanduser(fp)) == target_real
    except OSError:
        return False


def _blocks_with_spans(content):
    """Pair `_iter_blocks()`'s own yielded (heading_line, body_text) tuples
    (imported, reused verbatim -- never reimplemented) with each block's own
    character-span boundaries, recovered by independently re-running the
    SAME `HEADING_RE.finditer()` `_iter_blocks` uses internally (spec.md
    Part A step 2's explicit instruction: "this function must independently
    re-run the SAME HEADING_RE.finditer() _iter_blocks uses internally,
    imported and reused, not reimplemented, to recover those spans
    alongside the yielded text"). `_iter_blocks` and this independent
    finditer() call both walk the identical ordered match list over the
    identical `content` string, so zipping the two together is exact -- this
    is the "wrapper, not a modified _iter_blocks" approach spec.md's own
    step 2 explicitly prefers.

    Returns a list of dicts, one per `## ` block, each with:
      heading_line, body_text, block_start (the `##` line's own start
      offset), body_start (== _iter_blocks' own body_start, `m.end()`),
      block_end (== _iter_blocks' own body_end).
    """
    heading_bodies = list(_iter_blocks(content))
    matches = list(HEADING_RE.finditer(content))
    blocks = []
    for (heading_line, body_text), m in zip(heading_bodies, matches):
        block_start = m.start()
        body_start = m.end()
        block_end = body_start + len(body_text)  # == _iter_blocks' own body_end
        blocks.append({
            "heading_line": heading_line,
            "body_text": body_text,
            "block_start": block_start,
            "body_start": body_start,
            "block_end": block_end,
        })
    return blocks


def _proof_span_content_offsets(block):
    """Return (content_relative_start, content_relative_end) of `block`'s
    own Proof: span, or None if it has no Proof: block at all.

    `_extract_proof_span` (imported) is reused as the authoritative "does a
    Proof span exist here at all" check -- its own joined-string return
    value is not otherwise used, since it exposes no character offsets
    (spec.md Part A step 4: "_extract_proof_span(body_text) CANNOT be
    reused directly for this -- it returns a joined STRING ... not a
    character range"). When a span DOES exist, independently walks
    `body_text.splitlines(keepends=True)` (keepends=True, so cumulative
    offsets stay accurate -- unlike `_extract_proof_span`'s own internal
    `splitlines()` walk, which drops line terminators) applying the SAME
    selection rule (`PROOF_MARKER_LINE` + contiguous
    `PROOF_FIELD_LINE_SHAPE_RE` lines, both imported and reused, never
    reimplemented) to recover the span's own character range, then shifts
    it to be content-relative by adding the block's own `body_start`
    offset (spec.md Part A step 4's exact instruction)."""
    body_text = block["body_text"]
    if _extract_proof_span(body_text) is None:
        return None

    lines = body_text.splitlines(keepends=True)
    offset = 0
    for i, line in enumerate(lines):
        if line.strip() == PROOF_MARKER_LINE:
            span_end = offset + len(line)
            j = i + 1
            while j < len(lines) and PROOF_FIELD_LINE_SHAPE_RE.match(lines[j]):
                span_end += len(lines[j])
                j += 1
            return block["body_start"] + offset, block["body_start"] + span_end
        offset += len(line)
    return None  # defensive only -- _extract_proof_span already confirmed a match exists


def _block_containing_offset(blocks, offset):
    """Which block's own [block_start, block_end) span contains `offset`
    (spec.md Part A step 3: "For each found offset, determine which block's
    span contains it"). Returns None if no block contains it (offset falls
    before the first `## ` heading in the file)."""
    for block in blocks:
        if block["block_start"] <= offset < block["block_end"]:
            return block
    return None


def _touch_is_in_scope(block, start_offset, end_offset):
    """SCOPE test (spec.md Part A step 4): a touch is armed only if it lands
    (a) in the heading_line itself, or (b) inside the block's own Proof:
    span -- ordinary body prose is explicitly OUT of scope (theme 2's
    over-fire fix: "an edit that only adds a clarifying note elsewhere in an
    already-closed entry's body must never trigger re-validation")."""
    if start_offset < block["body_start"]:
        return True  # (a) heading line itself -- covers "introducing a new heading" too
    proof_range = _proof_span_content_offsets(block)
    if proof_range is None:
        return False  # no Proof span yet, and not the heading line -> not armed
    proof_start, proof_end = proof_range
    return start_offset < proof_end and end_offset > proof_start  # (b) overlaps Proof span


def find_touched_closed_headings(tool_uses, target_fix_plan_path):
    """Given tool_use dicts (Oga's own turn for Part C, OR a sub-agent's own
    transcript for Part B/E -- caller decides scope) and the resolved
    fix_plan.md path, identify which CLOSED heading(s) this turn/dispatch
    genuinely authored or modified the CLOSURE-RELEVANT portion of (the
    heading line itself, or its Proof: block span) -- NOT any edit anywhere
    in that heading's free-text body. Returns a list of heading_line strings
    (possibly empty, order not significant -- callers needing a stable order
    should sort the result themselves).

    See this module's own docstring for the full position-based algorithm.
    Any tool_use whose own `input.file_path`/`input.path` does not realpath-
    resolve to `target_fix_plan_path` is ignored entirely (this function
    only ever attributes touches to the ONE target file it was asked
    about).
    """
    try:
        with open(target_fix_plan_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    blocks = _blocks_with_spans(content)
    if not blocks:
        return []

    target_real = _target_realpath(target_fix_plan_path)
    armed = []

    def _arm(heading_line):
        if heading_line not in armed:
            armed.append(heading_line)

    for tu in tool_uses:
        name = (tu.get("name") or "").lower()
        if name not in _TOUCH_TOOLS:
            continue
        tool_input = tu.get("input") or {}
        if not _tool_use_targets_file(tool_input, target_real):
            continue

        if name == "write":
            # A full-file overwrite makes "which part did this edit touch"
            # ambiguous. For v1 status-claim gating, avoid pulling every
            # historical no-proof CLOSED heading into a block when a whole
            # file write only changed one later entry: arm Proof-bearing
            # blocks, or the sole block in a one-entry write.
            for block in blocks:
                if _proof_span_content_offsets(block) is not None or len(blocks) == 1:
                    _arm(block["heading_line"])
            continue

        if name == "edit":
            new_strings = [tool_input.get("new_string", "")]
        else:  # multiedit
            new_strings = [
                (edit.get("new_string", "") if isinstance(edit, dict) else "")
                for edit in (tool_input.get("edits") or [])
            ]

        for new_string in new_strings:
            if not new_string:
                continue  # empty/not-found new_string authors nothing findable
            for m in re.finditer(re.escape(new_string), content):
                block = _block_containing_offset(blocks, m.start())
                if block is None:
                    continue
                if _touch_is_in_scope(block, m.start(), m.end()):
                    _arm(block["heading_line"])

    # Step 5: filter the armed set to headings carrying the literal CLOSED
    # marker -- an armed OPEN heading is out of scope (nothing to validate).
    return [h for h in armed if CLOSURE_HEADING_RE.search(h)]
