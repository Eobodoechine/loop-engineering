#!/usr/bin/env python3
"""Tests for hooks/closure_touch_scan.py -- Evidence-Gate Phase 4, Part A
(spec: loop-team/runs/2026-07-09_evidence-gate-phase4/specs/spec.md,
"Part A, redesigned -- find_touched_closed_headings (position-based,
scope-limited)").

Self-contained (mirrors hooks/test_adversarial_loop_stop_guard.py's own
stated convention: builds its own minimal fixtures rather than importing
helpers from a sibling test file) -- this module does not exist yet at
dispatch time, so this ENTIRE file is expected to fail collection with
ModuleNotFoundError until the Coder builds hooks/closure_touch_scan.py.

`find_touched_closed_headings(tool_uses, target_fix_plan_path)` is tested
directly (unit-level, tmp-dir-based real on-disk fixture files), matching
this project's "hooks/ tests are unittest.TestCase + manual tempfile, not
pytest tmp_path" directory-wide convention (loop-team/harness/'s own
test_fixplan_closure_lint.py uses pytest tmp_path instead -- that is THAT
directory's own convention, not this one's).

`tool_uses` is tested as the PUBLIC, literally-documented shape from Part
A's own docstring: raw tool_use dicts (`{"type": "tool_use", "name": ...,
"input": {...}}`), the SAME shape `_parts()`/`_TOOL_USES` already produce
throughout hooks/loop_stop_guard.py and every existing hooks/ test file
that constructs one (see `tool_use()` below, byte-for-byte the same helper
hooks/test_loop_stop_guard.py already defines). Part C's OWN text floats an
OPTIONAL internal adaptation (accepting the `_rh_structural_writes()`
3-tuple shape instead, explicitly left as "Coder's call") purely for Part
C's OWN calling convenience -- that is a note about ONE caller's internal
wiring, not a change to the function's documented public contract, so it is
NOT what these unit tests target.

Run with:
    python3 -m pytest hooks/test_closure_touch_scan.py -q
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS_DIR)

import closure_touch_scan  # noqa: E402  -- does not exist yet; see module docstring


def tool_use(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


PROOF_BLOCK = (
    "Proof:\n"
    "- command: python3 run_and_record.py -- true\n"
    "- exit_code: 0\n"
    "- proof_snapshot: %s\n"
    "- verified_at: 2026-07-03T00:00:00+00:00\n"
)


class ClosureTouchScanTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="closure-touch-scan-test-")
        self._target = os.path.join(self._tmpdir, "fix_plan.md")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL]: an Edit whose new_string is entirely new prose inserted
# into an EXISTING CLOSED heading's body, OUTSIDE any Proof: span, returns []
# for that heading -- the core anti-over-fire test (theme 2's scope-limiting
# fix).
# ---------------------------------------------------------------------------

class Phase4AC1BodyProseOutsideProofSpanNotArmed(ClosureTouchScanTestCase):
    def test_new_prose_outside_proof_span_returns_empty(self):
        proof = PROOF_BLOCK % "/tmp/ac1-whatever.json"
        original_prose = "Some original body text."
        post_edit = (
            "## H-AC1-1 -- CLOSED (2026-07-03, some evidence)\n"
            "%s\n\n%s\n%s NEW SENTENCE INSERTED HERE, unrelated context.\n"
            % (original_prose, proof, original_prose)
        )
        _write(self._target, post_edit)
        edit_tu = tool_use(
            "Edit", file_path=self._target, old_string=original_prose,
            new_string="%s NEW SENTENCE INSERTED HERE, unrelated context." % original_prose,
        )
        result = closure_touch_scan.find_touched_closed_headings([edit_tu], self._target)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL]: an Edit whose new_string IS a complete new
# `## ... CLOSED ...` heading block (heading + Proof:) being introduced
# returns that heading's heading_line.
# ---------------------------------------------------------------------------

class Phase4AC2NewClosedHeadingIntroducedIsArmed(ClosureTouchScanTestCase):
    def test_new_heading_block_returns_that_heading(self):
        proof = PROOF_BLOCK % "/tmp/ac2-new.json"
        new_block = (
            "## H-AC2-NEW -- CLOSED (2026-07-09, brand new)\n\n%s" % proof
        )
        original = "## H-AC2-EXISTING-OPEN (OPEN, still working)\nNothing closed here.\n\n"
        _write(self._target, original + new_block)
        edit_tu = tool_use(
            "Edit", file_path=self._target, old_string="",
            new_string=new_block,
        )
        result = closure_touch_scan.find_touched_closed_headings([edit_tu], self._target)
        self.assertEqual(result, ["H-AC2-NEW -- CLOSED (2026-07-09, brand new)"])


# ---------------------------------------------------------------------------
# AC3 [BEHAVIORAL]: an Edit whose new_string falls within an EXISTING
# heading's Proof: span (e.g. editing/fabricating a proof_snapshot value)
# returns that heading.
# ---------------------------------------------------------------------------

class Phase4AC3ProofSpanEditIsArmed(ClosureTouchScanTestCase):
    def test_proof_span_edit_returns_heading(self):
        heading_line = "H-AC3-1 -- CLOSED (2026-07-03, some evidence)"
        proof = PROOF_BLOCK % "/tmp/fabricated-edited-path.json"
        content = "## %s\nSome body text.\n\n%s" % (heading_line, proof)
        _write(self._target, content)
        edit_tu = tool_use(
            "Edit", file_path=self._target, old_string="- proof_snapshot: /tmp/original.json",
            new_string="- proof_snapshot: /tmp/fabricated-edited-path.json",
        )
        result = closure_touch_scan.find_touched_closed_headings([edit_tu], self._target)
        self.assertEqual(result, [heading_line])


# ---------------------------------------------------------------------------
# AC4 [BEHAVIORAL]: a MultiEdit with two independent edits -- one inside a
# CLOSED heading's Proof span, one inside an OPEN heading's body -- returns
# exactly the one CLOSED heading.
# ---------------------------------------------------------------------------

class Phase4AC4MultiEditReturnsOnlyClosedHeading(ClosureTouchScanTestCase):
    def test_multiedit_closed_proof_and_open_body_returns_only_closed(self):
        closed_heading = "H-AC4-CLOSED -- CLOSED (2026-07-03, some evidence)"
        open_heading = "H-AC4-OPEN (OPEN, still working)"
        proof = PROOF_BLOCK % "/tmp/ac4-closed3.json"
        content = (
            "## %s\nBody text.\n\n%s\n## %s\nSome open body text, UPDATED NOTE HERE.\n"
            % (closed_heading, proof, open_heading)
        )
        _write(self._target, content)
        multiedit_tu = tool_use(
            "MultiEdit", file_path=self._target,
            edits=[
                {"old_string": "- proof_snapshot: /tmp/ac4-orig.json",
                 "new_string": "- proof_snapshot: /tmp/ac4-closed3.json"},
                {"old_string": "Some open body text.",
                 "new_string": "Some open body text, UPDATED NOTE HERE."},
            ],
        )
        result = closure_touch_scan.find_touched_closed_headings([multiedit_tu], self._target)
        self.assertEqual(result, [closed_heading])


# ---------------------------------------------------------------------------
# AC5 [BEHAVIORAL]: a Write tool_use (whole-file content) returns every
# CLOSED heading present in that content.
# ---------------------------------------------------------------------------

class Phase4AC5WriteReturnsEveryClosedHeading(ClosureTouchScanTestCase):
    def test_write_returns_all_closed_headings(self):
        heading_a = "H-AC5-A -- CLOSED (2026-07-03, some evidence)"
        heading_b = "H-AC5-B -- CLOSED (2026-07-04, some evidence)"
        heading_open = "H-AC5-OPEN (OPEN, still working)"
        proof = PROOF_BLOCK % "/tmp/ac5-shared.json"
        content = (
            "## %s\nBody A.\n\n%s\n## %s\nBody Open.\n\n"
            "## %s\nBody B.\n\n%s"
            % (heading_a, proof, heading_open, heading_b, proof)
        )
        _write(self._target, content)
        write_tu = tool_use("Write", file_path=self._target, content=content)
        result = closure_touch_scan.find_touched_closed_headings([write_tu], self._target)
        self.assertEqual(sorted(result), sorted([heading_a, heading_b]))


# ---------------------------------------------------------------------------
# AC6 [BEHAVIORAL]: a new_string that legitimately occurs in TWO different
# CLOSED headings' Proof spans (a real, if rare, coincidence -- e.g. the
# shared canonical no-op proof command line) returns BOTH.
# ---------------------------------------------------------------------------

class Phase4AC6CoincidentalDoubleOccurrenceReturnsBoth(ClosureTouchScanTestCase):
    def test_shared_proof_line_across_two_headings_returns_both(self):
        heading_a = "H-AC6-COINCIDENCE-A -- CLOSED (2026-07-03, some evidence)"
        heading_b = "H-AC6-COINCIDENCE-B -- CLOSED (2026-07-04, some evidence)"
        proof_a = PROOF_BLOCK % "/tmp/ac6-a.json"
        proof_b = PROOF_BLOCK % "/tmp/ac6-b.json"
        content = (
            "## %s\nBody A.\n\n%s\n## %s\nBody B.\n\n%s"
            % (heading_a, proof_a, heading_b, proof_b)
        )
        _write(self._target, content)
        # The canonical no-op command line is genuinely identical (byte for
        # byte) across both Proof blocks above -- a real, common recurrence,
        # not a contrived one.
        edit_tu = tool_use(
            "Edit", file_path=self._target,
            old_string="- command: something else",
            new_string="- command: python3 run_and_record.py -- true",
        )
        result = closure_touch_scan.find_touched_closed_headings([edit_tu], self._target)
        self.assertEqual(sorted(result), sorted([heading_a, heading_b]))


if __name__ == "__main__":
    unittest.main()
