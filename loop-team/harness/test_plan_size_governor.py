#!/usr/bin/env python3
"""Tests for plan_size_governor.py (SHIP_NARROW_PLAN / INVALID_PLAN_BOUNDARY).

Spec: loop-team/specs/plan_size_governor_spec_v1.md, Acceptance criteria
AC1-AC8 (the governor module itself; AC9-AC11, the spec_revision_diff.py
--check-ac-inventory extension, live in test_spec_revision_diff.py instead).

Written BEFORE plan_size_governor.py exists -- Test-writer runs before the
Coder, per this repo's standing loop-team convention. Every test below is
expected to fail until the Coder delivers
loop-team/harness/plan_size_governor.py: function-level tests raise a clear
"module not found" AssertionError via _require_module(); CLI-level
(subprocess) tests observe python3's own exit-2 "can't open file" behavior
against the not-yet-existing script path. Neither is a broken-test-logic
failure.

Convention: pytest (not unittest); tmp_path fixtures for file-backed cases;
subprocess-based CLI invocation for AC7 (mirrors test_spec_revision_diff.py's
_run() helper); direct function calls for AC1-AC6/AC8. The defensive
try/except module import + _require_module() guard mirrors
test_plancheck_saturation.py's own pattern for this exact
"written-before-the-module-exists" situation, elsewhere in this same
harness directory -- a closer precedent for this specific problem than
test_spec_revision_diff.py's bare top-level import, since spec_revision_diff.py
already existed when that file was written.

Run: python3 -m pytest loop-team/harness/test_plan_size_governor.py -v
"""
import importlib
import inspect
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "plan_size_governor.py")
sys.path.insert(0, HERE)

try:
    psg = importlib.import_module("plan_size_governor")
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - expected until Coder delivers
    psg = None
    IMPORT_ERROR = exc

import spec_revision_diff as sdiff  # noqa: E402 - already exists in this repo
import plancheck_saturation as pcs  # noqa: E402 - AC4's disjointness target


def _require_module():
    if psg is None:
        raise AssertionError(
            "loop-team/harness/plan_size_governor.py does not exist/import "
            "yet; these tests are expected to fail until the governor is "
            "built: %r" % (IMPORT_ERROR,)
        )


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _run(args, timeout=30):
    """Invoke the real CLI: python3 plan_size_governor.py <args...>.

    Returns (exit_code, stdout, stderr).
    """
    p = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, p.stdout, p.stderr


def _directive_text(*lines):
    """Join literal fixture lines with newlines -- each element is one raw
    line of text (e.g. "MVP_MAX_LINES: not-a-number"), matching
    parse_mvp_boundary's MULTILINE '^MVP_MAX_LINES:...$' anchoring."""
    return "\n".join(lines) + "\n"


def _assert_result_shape(result):
    """Every evaluate_plan_boundary/evaluate_spec_file result has exactly
    this top-level key set; 'exceeded' is always a present dict (Public
    interface section's round-3 fix note -- never omitted/None at the top
    level, only ever {} or populated); 'message' is a non-empty string."""
    assert set(result.keys()) == {
        "verdict", "reason", "actual", "declared", "exceeded", "message",
    }, result
    assert isinstance(result["exceeded"], dict), result
    assert (isinstance(result["actual"], dict)
            and set(result["actual"]) == {"lines", "acs"}), result
    assert (isinstance(result["declared"], dict)
            and set(result["declared"]) == {"max_lines", "max_acs"}), result
    assert isinstance(result["message"], str) and result["message"], result


# ---------------------------------------------------------------------------
# AC1 -- [BEHAVIORAL] importable; exposes count_lines, parse_mvp_boundary,
# evaluate_plan_boundary, evaluate_spec_file with the Public interface
# section's exact signatures; locks the verdict/reason literal strings every
# downstream test below relies on.
# ---------------------------------------------------------------------------

class TestAC1PublicInterface:
    def test_module_imports(self):
        _require_module()

    def test_exposes_all_four_public_functions(self):
        _require_module()
        for name in ("count_lines", "parse_mvp_boundary",
                     "evaluate_plan_boundary", "evaluate_spec_file"):
            assert hasattr(psg, name), "missing public function %r" % name
            assert callable(getattr(psg, name))

    def test_count_lines_signature(self):
        _require_module()
        params = list(inspect.signature(psg.count_lines).parameters)
        assert params == ["text"]

    def test_parse_mvp_boundary_signature(self):
        _require_module()
        params = list(inspect.signature(psg.parse_mvp_boundary).parameters)
        assert params == ["text"]

    def test_evaluate_plan_boundary_signature(self):
        _require_module()
        sig = inspect.signature(psg.evaluate_plan_boundary)
        params = list(sig.parameters)
        assert params == [
            "actual_lines", "actual_acs", "mvp_max_lines", "mvp_max_acs",
            "malformed",
        ]
        assert sig.parameters["malformed"].default is None

    def test_evaluate_spec_file_signature(self):
        _require_module()
        params = list(inspect.signature(psg.evaluate_spec_file).parameters)
        assert params == ["spec_path"]

    def test_verdict_and_reason_constants_match_spec_literal_strings(self):
        """Locks the Public interface section's exact literal strings.
        Every AC2-AC6 test below compares results against
        psg.VERDICT_*/REASON_*, so THIS test is what proves those module
        constants equal the spec's own pinned values, not merely some
        self-consistent-but-wrong string that would pass every downstream
        comparison against itself."""
        _require_module()
        assert psg.VERDICT_SHIP_NARROW == "SHIP_NARROW_PLAN"
        assert psg.VERDICT_WITHIN_BOUNDARY == "WITHIN_MVP_BOUNDARY"
        assert psg.VERDICT_INVALID_BOUNDARY == "INVALID_PLAN_BOUNDARY"
        assert psg.REASON_MISSING == "missing_mvp_boundary"
        assert psg.REASON_MALFORMED == "malformed_mvp_boundary"

    def test_count_lines_behavior(self):
        """count_lines' own documented definition: len(text.splitlines())."""
        _require_module()
        assert psg.count_lines("a\nb\nc") == 3
        assert psg.count_lines("") == 0
        assert psg.count_lines("only one line, no trailing newline") == 1
        assert psg.count_lines("a\nb\n") == 2  # no phantom trailing-newline line


# ---------------------------------------------------------------------------
# AC2 -- [BEHAVIORAL] both directives absent -> INVALID_PLAN_BOUNDARY /
# missing_mvp_boundary, at BOTH a small and a large actual size (proves the
# check never guesses a threshold from the artifact's own size). Grid cell:
# (b) absent x (b) absent -- see AC5 Part 5.B's completeness table.
# ---------------------------------------------------------------------------

class TestAC2MissingBoundary:
    def test_missing_boundary_small_actual_size(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=10, actual_acs=1,
            mvp_max_lines=None, mvp_max_acs=None,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MISSING
        assert result["exceeded"] == {}
        assert result["actual"] == {"lines": 10, "acs": 1}
        assert result["declared"] == {"max_lines": None, "max_acs": None}

    def test_missing_boundary_large_actual_size(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=2000, actual_acs=100,
            mvp_max_lines=None, mvp_max_acs=None, malformed=[],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MISSING
        assert result["exceeded"] == {}
        assert result["actual"] == {"lines": 2000, "acs": 100}
        assert result["declared"] == {"max_lines": None, "max_acs": None}


# ---------------------------------------------------------------------------
# AC3 -- [BEHAVIORAL] full 8-cell grid for the declared-boundary case (8 of
# the 16 cells in AC5 Part 5.B's completeness table; neither dimension
# malformed here). Cells b/d/h each require a comfortably-under test AND an
# exact-equality test, locking '>' (not '>=') as the exceeded operator.
# ---------------------------------------------------------------------------

class TestAC3DeclaredBoundaryGrid:
    # -- a: lines declared only, exceeded ------------------------------------
    def test_a_lines_only_exceeded(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=150, actual_acs=3,
            mvp_max_lines=100, mvp_max_acs=None,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_SHIP_NARROW
        assert result["reason"] is None
        assert result["exceeded"] == {"lines": {"actual": 150, "max": 100}}

    # -- b: lines declared only, not exceeded --------------------------------
    def test_b_lines_only_comfortably_under(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=50, actual_acs=3,
            mvp_max_lines=100, mvp_max_acs=None,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_WITHIN_BOUNDARY
        assert result["reason"] is None
        assert result["exceeded"] == {}

    def test_b_lines_only_exact_equality_is_within_not_exceeded(self):
        """Locks '>' (not '>=') as the exceeded-comparison operator."""
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=100, actual_acs=3,
            mvp_max_lines=100, mvp_max_acs=None,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_WITHIN_BOUNDARY
        assert result["reason"] is None
        assert result["exceeded"] == {}

    # -- c: acs declared only, exceeded --------------------------------------
    def test_c_acs_only_exceeded(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=10, actual_acs=25,
            mvp_max_lines=None, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_SHIP_NARROW
        assert result["reason"] is None
        assert result["exceeded"] == {"acs": {"actual": 25, "max": 20}}

    # -- d: acs declared only, not exceeded ----------------------------------
    def test_d_acs_only_comfortably_under(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=10, actual_acs=15,
            mvp_max_lines=None, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_WITHIN_BOUNDARY
        assert result["reason"] is None
        assert result["exceeded"] == {}

    def test_d_acs_only_exact_equality_is_within_not_exceeded(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=10, actual_acs=20,
            mvp_max_lines=None, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_WITHIN_BOUNDARY
        assert result["reason"] is None
        assert result["exceeded"] == {}

    # -- e: both declared, both exceeded -------------------------------------
    def test_e_both_declared_both_exceeded(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=150, actual_acs=25,
            mvp_max_lines=100, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_SHIP_NARROW
        assert result["reason"] is None
        assert result["exceeded"] == {
            "lines": {"actual": 150, "max": 100},
            "acs": {"actual": 25, "max": 20},
        }

    # -- f: both declared, only lines exceeded -------------------------------
    def test_f_both_declared_only_lines_exceeded(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=150, actual_acs=10,
            mvp_max_lines=100, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_SHIP_NARROW
        assert result["reason"] is None
        assert result["exceeded"] == {"lines": {"actual": 150, "max": 100}}
        assert "acs" not in result["exceeded"]

    # -- g: both declared, only acs exceeded ---------------------------------
    def test_g_both_declared_only_acs_exceeded(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=50, actual_acs=25,
            mvp_max_lines=100, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_SHIP_NARROW
        assert result["reason"] is None
        assert result["exceeded"] == {"acs": {"actual": 25, "max": 20}}
        assert "lines" not in result["exceeded"]

    # -- h: both declared, neither exceeded ----------------------------------
    def test_h_both_declared_comfortably_under(self):
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=50, actual_acs=10,
            mvp_max_lines=100, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_WITHIN_BOUNDARY
        assert result["reason"] is None
        assert result["exceeded"] == {}

    def test_h_both_declared_double_equality_is_within_not_exceeded(self):
        """Strictest test of '>' applied independently on BOTH dimensions in
        the same call -- both actual==max simultaneously."""
        _require_module()
        result = psg.evaluate_plan_boundary(
            actual_lines=100, actual_acs=20,
            mvp_max_lines=100, mvp_max_acs=20,
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_WITHIN_BOUNDARY
        assert result["reason"] is None
        assert result["exceeded"] == {}


# ---------------------------------------------------------------------------
# AC4 -- [BEHAVIORAL] verdict strings are provably disjoint from
# plancheck_saturation.py's own verdict vocabulary -- the source research
# spec's own named collision hazard.
# ---------------------------------------------------------------------------

class TestAC4VerdictStringsDisjointFromPlancheckSaturation:
    def test_within_boundary_differs_from_continue_plan_check(self):
        _require_module()
        assert pcs.CONTINUE_PLAN_CHECK == "CONTINUE_PLAN_CHECK"
        assert psg.VERDICT_WITHIN_BOUNDARY != pcs.CONTINUE_PLAN_CHECK

    def test_invalid_boundary_differs_from_invalid_tagging(self):
        """The most confusable pair of the three -- both share the
        INVALID_-prefix convention."""
        _require_module()
        assert pcs.INVALID_TAGGING == "INVALID_TAGGING"
        assert psg.VERDICT_INVALID_BOUNDARY != pcs.INVALID_TAGGING

    def test_ship_narrow_differs_from_stop_prose_review(self):
        _require_module()
        assert pcs.STOP_PROSE_REVIEW == "STOP_PROSE_REVIEW"
        assert psg.VERDICT_SHIP_NARROW != pcs.STOP_PROSE_REVIEW


# ---------------------------------------------------------------------------
# AC5 Part 5.A -- [BEHAVIORAL] per-directive detection (parse_mvp_boundary):
# does a single dimension resolve to state (a) malformed correctly, including
# under repetition (first-match-wins)? a1-a12 mirror the spec's own lettering
# exactly for direct traceability. Sub-cases a1/a3/a5/a9/a10 ALSO carry the
# downstream evaluate_plan_boundary assertion that Part 5.B's completeness
# table cites as grid cells B4/B5/B1/B2/B3 respectively -- see
# TestAC5PartBMalformedPriorityGrid below for why B1-B5 need no further text.
# ---------------------------------------------------------------------------

class TestAC5PartADirectiveDetection:
    def test_a1_lines_malformed_nonnumeric_acs_valid_not_exceeded(self):
        """Cited as grid cell B4: (a) malformed x (c) valid-not-exceeded."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: not-a-number",
            "MVP_MAX_ACS: 50",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed == {
            "mvp_max_lines": None, "mvp_max_acs": 50,
            "malformed": ["mvp_max_lines"],
        }
        result = psg.evaluate_plan_boundary(
            actual_lines=999, actual_acs=5,
            mvp_max_lines=None, mvp_max_acs=50,
            malformed=["mvp_max_lines"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["exceeded"] == {}

    def test_a2_lines_malformed_negative(self):
        """Parse-level only -- isolates the negative-value guard (distinct
        from a1's numeric-vs-non-numeric guard); no evaluate_plan_boundary
        assertion required, since the downstream priority behavior for ANY
        reason a dimension lands in malformed is already exercised
        end-to-end by a1/a3/a5/a9/a10."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: -5",
            "MVP_MAX_ACS: 50",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["malformed"] == ["mvp_max_lines"]

    def test_a3_acs_malformed_nonnumeric_lines_valid_not_exceeded(self):
        """Cited as grid cell B5 (mirror of a1/B4): (c) valid-not-exceeded x
        (a) malformed."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: 500",
            "MVP_MAX_ACS: not-a-number",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed == {
            "mvp_max_lines": 500, "mvp_max_acs": None,
            "malformed": ["mvp_max_acs"],
        }
        result = psg.evaluate_plan_boundary(
            actual_lines=10, actual_acs=999,
            mvp_max_lines=500, mvp_max_acs=None,
            malformed=["mvp_max_acs"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["exceeded"] == {}

    def test_a4_acs_malformed_negative_lines_pinned_as_a3(self):
        """Mirror of a2 (parse-level only), inheriting a3's pinned
        'MVP_MAX_LINES: 500' fixture state, per this sub-case's own
        cross-reference to a3.

        JUDGMENT CALL (flagged, see final report): the spec's own prose for
        a4 reads "-> same assertions as a3 (mirror of a2)", which is not
        fully self-consistent on its face -- a3's own sub-case carries a
        downstream evaluate_plan_boundary assertion, while a2 (which a4's
        own opening words explicitly call itself a mirror of) explicitly
        does not ("Parse-level only -- no evaluate_plan_boundary assertion
        required here"). This test follows a2's assertion DEPTH (parse-level
        only), reading "same assertions as a3" as referring to a3's fixture
        SETUP (the pinned MVP_MAX_LINES: 500 state), not a3's assertion
        depth -- consistent with a4's own title and rationale ("isolating
        the negative-value guard specifically on the acs dimension", the
        same narrow job a2 states for itself on the lines dimension).
        """
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: 500",
            "MVP_MAX_ACS: -5",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["malformed"] == ["mvp_max_acs"]

    def test_a5_both_directives_simultaneously_malformed(self):
        """Cited as grid cell B1: (a) malformed x (a) malformed. sorted()
        (not a plain membership check) guards against a parse_mvp_boundary
        that early-returns after the first malformed hit and silently drops
        the second."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: not-a-number",
            "MVP_MAX_ACS: -5",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_lines"] is None
        assert parsed["mvp_max_acs"] is None
        assert sorted(parsed["malformed"]) == ["mvp_max_acs", "mvp_max_lines"]
        result = psg.evaluate_plan_boundary(
            actual_lines=42, actual_acs=7,
            mvp_max_lines=None, mvp_max_acs=None,
            malformed=["mvp_max_lines", "mvp_max_acs"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["exceeded"] == {}

    def test_a6_lines_repeated_both_valid_different_values_first_wins(self):
        _require_module()
        text = _directive_text(
            "intro filler line",
            "MVP_MAX_LINES: 500",
            "more filler",
            "MVP_MAX_LINES: 900",
            "trailing filler",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_lines"] == 500
        assert "mvp_max_lines" not in parsed["malformed"]

    def test_a7_lines_malformed_first_valid_later_still_malformed(self):
        """'First match wins' means malformed-first locks malformed, even
        though a syntactically-valid later occurrence exists."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: not-a-number",
            "filler",
            "MVP_MAX_LINES: 500",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["malformed"] == ["mvp_max_lines"]
        result = psg.evaluate_plan_boundary(
            actual_lines=42, actual_acs=7,
            mvp_max_lines=None, mvp_max_acs=None,
            malformed=["mvp_max_lines"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["exceeded"] == {}

    def test_a8_acs_malformed_first_valid_later_still_malformed(self):
        """Mirror of a7, isolating 'first match wins' on the acs dimension."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_ACS: not-a-number",
            "filler",
            "MVP_MAX_ACS: 50",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["malformed"] == ["mvp_max_acs"]
        result = psg.evaluate_plan_boundary(
            actual_lines=42, actual_acs=7,
            mvp_max_lines=None, mvp_max_acs=None,
            malformed=["mvp_max_acs"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["exceeded"] == {}

    def test_a9_lines_malformed_acs_genuinely_absent(self):
        """Cited as grid cell B2: (a) malformed x (b) absent. Must resolve
        malformed_mvp_boundary, NOT missing_mvp_boundary -- the priority
        contract this whole AC exists to pin down."""
        _require_module()
        text = _directive_text("MVP_MAX_LINES: not-a-number")
        parsed = psg.parse_mvp_boundary(text)
        assert parsed == {
            "mvp_max_lines": None, "mvp_max_acs": None,
            "malformed": ["mvp_max_lines"],
        }
        result = psg.evaluate_plan_boundary(
            actual_lines=42, actual_acs=7,
            mvp_max_lines=None, mvp_max_acs=None,
            malformed=["mvp_max_lines"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["reason"] != psg.REASON_MISSING
        assert result["exceeded"] == {}

    def test_a10_acs_malformed_lines_genuinely_absent(self):
        """Cited as grid cell B3 (mirror of a9/B2): (b) absent x (a)
        malformed."""
        _require_module()
        text = _directive_text("MVP_MAX_ACS: -5")
        parsed = psg.parse_mvp_boundary(text)
        assert parsed == {
            "mvp_max_lines": None, "mvp_max_acs": None,
            "malformed": ["mvp_max_acs"],
        }
        result = psg.evaluate_plan_boundary(
            actual_lines=42, actual_acs=7,
            mvp_max_lines=None, mvp_max_acs=None,
            malformed=["mvp_max_acs"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["reason"] != psg.REASON_MISSING
        assert result["exceeded"] == {}

    def test_a11_lines_valid_first_malformed_later_resolves_valid(self):
        """Mirror direction of a7: 'first match wins' also means a VALID
        first occurrence must NOT be overridden by a later malformed one.
        Not redundant with a7: an implementation that takes the first
        match's VALUE correctly but separately scans EVERY occurrence for
        malformed-ness (not only the first) would pass a7 while wrongly
        flagging this fixture too."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: 500",
            "MVP_MAX_ACS: 50",
            "filler",
            "MVP_MAX_LINES: not-a-number",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_lines"] == 500
        assert "mvp_max_lines" not in parsed["malformed"]

    def test_a12_acs_valid_first_malformed_later_resolves_valid(self):
        """Mirror of a11, isolating the acs dimension."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_ACS: 50",
            "MVP_MAX_LINES: 500",
            "filler",
            "MVP_MAX_ACS: not-a-number",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_acs"] == 50
        assert "mvp_max_acs" not in parsed["malformed"]

    def test_a13_lines_zero_valid_not_malformed(self):
        """Parse-level only, same reason as a2: zero is a
        syntactically-valid, non-negative int, so it must parse as VALID,
        not malformed -- the boundary point of the documented "non-negative
        int" contract, left untested by a1-a12's non-numeric (a1/a3/a5/
        a7-a10) and negative-value (a2/a4) coverage alone. Same pinned acs
        state as a1 (MVP_MAX_ACS: 50, validly declared and not exceeded)."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: 0",
            "MVP_MAX_ACS: 50",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_lines"] == 0
        assert "mvp_max_lines" not in parsed["malformed"]

    def test_a14_acs_zero_valid_not_malformed(self):
        """Mirror of a13, isolating the zero-value boundary on the acs
        dimension. Same pinned lines state as a3 (MVP_MAX_LINES: 500,
        validly declared and not exceeded)."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: 500",
            "MVP_MAX_ACS: 0",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_acs"] == 0
        assert "mvp_max_acs" not in parsed["malformed"]

    def test_a15_acs_repeated_both_valid_different_values_first_wins(self):
        """Mirror of a6, isolating 'repeated, both valid, different values,
        first wins' on the acs dimension -- closes an asymmetry a6 itself
        had flagged and left open across multiple prior spec revisions:
        every OTHER Part 5.A property in this class is already mirrored
        across both dimensions (a1/a3, a2/a4, a7/a8, a9/a10, a11/a12,
        a13/a14 above); this was the sole exception until the spec's
        post-round-7 short-circuit completeness sweep added a15."""
        _require_module()
        text = _directive_text(
            "intro filler line",
            "MVP_MAX_ACS: 30",
            "more filler",
            "MVP_MAX_ACS: 80",
            "trailing filler",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_acs"] == 30
        assert "mvp_max_acs" not in parsed["malformed"]


# ---------------------------------------------------------------------------
# AC5 Part 5.B -- [BEHAVIORAL] evaluate_plan_boundary's malformed-priority
# grid. Cells B1-B5 are satisfied entirely by Part 5.A's a5/a9/a10/a1/a3
# above (each already carries the evaluate_plan_boundary assertion) -- no
# further test needed for those five, per the spec's own "no further text
# needed" statement. B6/B7 are the genuinely NEW cells this AC's grid
# restructure added: one dimension malformed, the OTHER validly-declared
# AND EXCEEDED -- the step-1-vs-step-3 race. This is the single
# highest-value regression in the whole spec: a buggy "check exceeded
# before malformed" implementation passes every other test in this file
# and returns SHIP_NARROW_PLAN here instead of INVALID_PLAN_BOUNDARY.
# ---------------------------------------------------------------------------

class TestAC5PartBMalformedPriorityGrid:
    def test_b6_lines_malformed_acs_valid_and_exceeded_not_ship_narrow(self):
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: not-a-number",
            "MVP_MAX_ACS: 2",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed == {
            "mvp_max_lines": None, "mvp_max_acs": 2,
            "malformed": ["mvp_max_lines"],
        }
        result = psg.evaluate_plan_boundary(
            actual_lines=999, actual_acs=5,
            mvp_max_lines=None, mvp_max_acs=2,
            malformed=["mvp_max_lines"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["verdict"] != psg.VERDICT_SHIP_NARROW
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["exceeded"] == {}

    def test_b7_acs_malformed_lines_valid_and_exceeded_not_ship_narrow(self):
        """Mirror of B6, isolating the same step-1-vs-step-3 race on the
        acs dimension."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_ACS: not-a-number",
            "MVP_MAX_LINES: 3",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed == {
            "mvp_max_lines": 3, "mvp_max_acs": None,
            "malformed": ["mvp_max_acs"],
        }
        result = psg.evaluate_plan_boundary(
            actual_lines=10, actual_acs=999,
            mvp_max_lines=3, mvp_max_acs=None,
            malformed=["mvp_max_acs"],
        )
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["verdict"] != psg.VERDICT_SHIP_NARROW
        assert result["reason"] == psg.REASON_MALFORMED
        assert result["exceeded"] == {}


# ---------------------------------------------------------------------------
# Two small, cheap, genuinely load-bearing additions surfaced while writing
# the AC5 tests above:
#   1. parse_mvp_boundary's "non-negative int" contract explicitly includes
#      zero; a naive "value > 0" guard (instead of ">= 0") would wrongly
#      flag a boundary of exactly 0 as malformed -- the same class of
#      off-by-one boundary bug AC3's b/d/h equality locks exist to catch,
#      one level earlier in the pipeline (at parse time, not compare time).
#      Originally written as an adversarial addition beyond the spec's
#      literal AC1-AC15 list; AC5 Part 5.A now formalizes this exact
#      boundary as sub-cases a13 (lines)/a14 (acs), each pairing its
#      dimension-under-test with the OTHER dimension pinned to the same
#      boring valid-not-exceeded state a1/a3 already use, per this AC's own
#      "never left ambiguous" discipline -- the two tests below are updated
#      to match that fixture shape.
#   2. evaluate_plan_boundary's docstring states "Pure, deterministic" --
#      untested by any literal AC. Same inputs must produce equal outputs
#      across repeat calls, and the caller's `malformed` list must not be
#      mutated as a side effect (a plausible bug if an implementation
#      normalizes `malformed` in place, e.g. via .append()/.sort()). Still
#      genuinely beyond the spec's literal AC1-AC15 list -- no AC pins this.
# ---------------------------------------------------------------------------

class TestParseMvpBoundaryZeroValueAdversarial:
    """Corresponds to AC5 Part 5.A's a13 (lines)/a14 (acs) sub-cases -- see
    the class comment above."""

    def test_lines_zero_is_valid_not_malformed(self):
        """= spec a13: MVP_MAX_LINES: 0, with MVP_MAX_ACS: 50 pinned to the
        same validly-declared/not-exceeded state a1 uses."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_LINES: 0",
            "MVP_MAX_ACS: 50",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_lines"] == 0
        assert "mvp_max_lines" not in parsed["malformed"]

    def test_acs_zero_is_valid_not_malformed(self):
        """= spec a14 (mirror of a13): MVP_MAX_ACS: 0, with MVP_MAX_LINES: 500
        pinned to the same validly-declared/not-exceeded state a3 uses."""
        _require_module()
        text = _directive_text(
            "MVP_MAX_ACS: 0",
            "MVP_MAX_LINES: 500",
        )
        parsed = psg.parse_mvp_boundary(text)
        assert parsed["mvp_max_acs"] == 0
        assert "mvp_max_acs" not in parsed["malformed"]


class TestEvaluatePlanBoundaryPurityAdversarial:
    def test_repeated_calls_with_same_inputs_are_deterministic(self):
        _require_module()
        kwargs = dict(actual_lines=150, actual_acs=25,
                      mvp_max_lines=100, mvp_max_acs=20)
        first = psg.evaluate_plan_boundary(**kwargs)
        second = psg.evaluate_plan_boundary(**kwargs)
        assert first == second

    def test_shared_malformed_list_not_mutated_across_repeated_calls(self):
        _require_module()
        shared = ["mvp_max_lines"]
        first = psg.evaluate_plan_boundary(
            actual_lines=1, actual_acs=1,
            mvp_max_lines=None, mvp_max_acs=20, malformed=shared,
        )
        second = psg.evaluate_plan_boundary(
            actual_lines=1, actual_acs=1,
            mvp_max_lines=None, mvp_max_acs=20, malformed=shared,
        )
        assert first == second
        assert shared == ["mvp_max_lines"], "caller's list must not be mutated"


# ---------------------------------------------------------------------------
# AC6 -- [BEHAVIORAL] evaluate_spec_file on a real temp-file fixture returns
# actual counts that exactly match the fixture's constructed N (lines) and M
# (distinct AC<k> tokens). The fixture forces a repeated AC token (AC7,
# 3 occurrences) so the test can actually distinguish a deduping
# implementation from a non-deduping one.
# ---------------------------------------------------------------------------

class TestAC6EvaluateSpecFile:
    def test_actual_counts_match_constructed_fixture_with_forced_ac_repeat(
        self, tmp_path,
    ):
        _require_module()
        lines = [
            "# Fake spec fixture for acceptance-criterion dedup test",
            "",
            "MVP_MAX_LINES: 500",
            "MVP_MAX_ACS: 20",
            "",
            "## AC1",
            "First criterion text mentions AC1 here.",
            "",
            "## AC2",
            "Second criterion mentions AC2 and also references AC7 for context.",
            "",
            "## AC3",
            "Third criterion references AC3.",
            "",
            "## AC7",
            "Seventh criterion, AC7 defined properly here -- a forced repeat.",
            "",
            "End of fixture.",
        ]
        text = "\n".join(lines)
        expected_n = len(lines)
        expected_distinct_acs = {"AC1", "AC2", "AC3", "AC7"}
        total_ac_occurrences = len(re.findall(r"\bAC\d+[a-z]?\b", text))
        assert total_ac_occurrences > len(expected_distinct_acs), (
            "fixture must force at least one repeated AC token, else this "
            "test cannot distinguish a deduping implementation from a "
            "non-deduping one"
        )

        spec_path = tmp_path / "fixture_spec.md"
        _write(spec_path, text)

        result = psg.evaluate_spec_file(str(spec_path))
        _assert_result_shape(result)
        assert result["actual"] == {
            "lines": expected_n, "acs": len(expected_distinct_acs),
        }


# ---------------------------------------------------------------------------
# [ADVERSARIAL, beyond the spec's literal AC1-AC15 sub-case list]
# evaluate_spec_file's own docstring states extract_ac_ids is imported from
# spec_revision_diff.py as "a single source of truth, not a second copy."
# This is directly testable and worth pinning: if plan_size_governor.py
# instead reimplemented its own separate AC-counting regex, this test can
# catch behavior drift between the two copies even where each individually
# looks correct in isolation.
# ---------------------------------------------------------------------------

class TestEvaluateSpecFileSharesExtractAcIdsAdversarial:
    def test_acs_count_matches_sdiff_extract_ac_ids_directly(self, tmp_path):
        _require_module()
        text = (
            "# Fixture\nMVP_MAX_LINES: 500\n"
            "## AC1\n## AC2\nAC2 repeated here.\n## AC46b\n"
        )
        spec_path = tmp_path / "fixture.md"
        _write(spec_path, text)
        result = psg.evaluate_spec_file(str(spec_path))
        expected = len(set(sdiff.extract_ac_ids(text)))
        assert result["actual"]["acs"] == expected


# ---------------------------------------------------------------------------
# [ADVERSARIAL, beyond the spec's literal AC1-AC15 sub-case list] AC5's B6
# race (malformed beats exceeded), proven through evaluate_spec_file's full
# file-read -> parse -> evaluate pipeline rather than a direct
# evaluate_plan_boundary call -- confirms the wiring between
# parse_mvp_boundary's output and evaluate_plan_boundary's malformed-priority
# contract is actually connected end-to-end in evaluate_spec_file, not only
# correct when each piece is exercised in isolation.
# ---------------------------------------------------------------------------

class TestEvaluateSpecFileMalformedPriorityIntegrationAdversarial:
    def test_evaluate_spec_file_malformed_lines_beats_exceeded_acs(
        self, tmp_path,
    ):
        _require_module()
        lines = [
            "# Fixture",
            "MVP_MAX_LINES: not-a-number",
            "MVP_MAX_ACS: 2",
            "## AC1",
            "## AC2",
            "## AC3",
            "## AC4",
            "## AC5",
        ]
        spec_path = tmp_path / "fixture.md"
        _write(spec_path, "\n".join(lines))
        result = psg.evaluate_spec_file(str(spec_path))
        _assert_result_shape(result)
        assert result["verdict"] == psg.VERDICT_INVALID_BOUNDARY
        assert result["verdict"] != psg.VERDICT_SHIP_NARROW
        assert result["reason"] == psg.REASON_MALFORMED


# ---------------------------------------------------------------------------
# AC7 -- [BEHAVIORAL] CLI: prints valid JSON matching evaluate_spec_file's
# shape, exit 0 for EACH of the three verdicts (proving exit code never
# encodes verdict) -- three independent fixtures/tests, not one. Plus 4
# independently-required usage-error cases, each exit 2 with a stderr usage
# message.
#
# Note on the usage-error tests below: right now (pre-implementation) the
# script file itself does not exist, so python3 itself exits 2 with a
# "can't open file" stderr message for EVERY invocation, including the
# usage-error ones -- an exit-code-only assertion would coincidentally
# "pass" today for the wrong reason. Each usage-error test below therefore
# also asserts the word "usage" appears in stderr (the real, not-yet-built
# CLI's documented usage message), which the interpreter's own launch-time
# error text does NOT contain -- so these tests correctly fail today, not
# just after a hypothetical future regression.
# ---------------------------------------------------------------------------

class TestAC7CliVerdicts:
    def test_cli_ship_narrow_plan_exits_zero(self, tmp_path):
        spec_path = tmp_path / "oversized.md"
        _write(spec_path, "\n".join([
            "# Oversized fixture",
            "MVP_MAX_LINES: 3",
            "line four",
            "line five",
            "line six",
        ]))
        code, out, err = _run([str(spec_path)])
        assert code == 0, "stdout=%r stderr=%r" % (out, err)
        payload = json.loads(out)
        assert set(payload.keys()) == {
            "verdict", "reason", "actual", "declared", "exceeded", "message",
        }
        assert payload["verdict"] == "SHIP_NARROW_PLAN"

    def test_cli_within_mvp_boundary_exits_zero(self, tmp_path):
        spec_path = tmp_path / "small.md"
        _write(spec_path, "\n".join([
            "# Small fixture",
            "MVP_MAX_LINES: 500",
            "just a little content",
        ]))
        code, out, err = _run([str(spec_path)])
        assert code == 0, "stdout=%r stderr=%r" % (out, err)
        payload = json.loads(out)
        assert payload["verdict"] == "WITHIN_MVP_BOUNDARY"

    def test_cli_invalid_plan_boundary_exits_zero(self, tmp_path):
        """Exit code 0 even for the INVALID_PLAN_BOUNDARY verdict -- exit
        code never encodes the verdict; only the JSON payload does."""
        spec_path = tmp_path / "no_boundary.md"
        _write(spec_path, "\n".join([
            "# No boundary declared",
            "just some content",
            "more content",
        ]))
        code, out, err = _run([str(spec_path)])
        assert code == 0, "stdout=%r stderr=%r" % (out, err)
        payload = json.loads(out)
        assert payload["verdict"] == "INVALID_PLAN_BOUNDARY"
        assert payload["reason"] == "missing_mvp_boundary"


class TestAC7CliUsageErrors:
    def test_missing_spec_file_exits_2(self, tmp_path):
        missing = tmp_path / "does_not_exist.md"
        code, out, err = _run([str(missing)])
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert "usage" in err.lower()
        assert "Traceback" not in err

    def test_zero_argument_invocation_exits_2(self):
        """A CLI that reads sys.argv[1] before checking argv length, guarded
        only by except OSError around the file-open call, would raise an
        uncaught IndexError here (Python's default exit 1, not the
        documented 2) -- a bug a missing-file-only fixture can never
        expose, since it always supplies a well-formed single argument."""
        code, out, err = _run([])
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert "usage" in err.lower()
        assert "Traceback" not in err

    def test_greater_than_one_argument_invocation_exits_2(self, tmp_path):
        """Distinct failure mode from the zero-arg case: a lower-bound-only
        guard (len(argv) < 2) would correctly reject zero args yet silently
        accept and run on trailing extra arguments."""
        spec_path = tmp_path / "valid.md"
        _write(spec_path, "MVP_MAX_LINES: 500\nsome content\n")
        code, out, err = _run([str(spec_path), "extra_arg"])
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert "usage" in err.lower()
        assert "Traceback" not in err

    def test_non_utf8_spec_file_exits_2_not_uncaught_traceback(self, tmp_path):
        """Exists/readable but non-UTF-8 -- the same "exists/readable but
        fails to parse as the expected format" shape as
        test_spec_revision_diff.py's AC10.i invalid-JSON case, applied here
        to the spec file's own encoding. UnicodeDecodeError is a ValueError
        subclass, not an OSError subclass, so a wrapper that only catches
        OSError would let it propagate uncaught."""
        spec_path = tmp_path / "bad_encoding.md"
        with open(spec_path, "wb") as f:
            f.write(b"MVP_MAX_LINES: 500\n\xff\xfe\x00\x01 invalid utf-8 bytes\n")
        code, out, err = _run([str(spec_path)])
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert "usage" in err.lower()
        assert "Traceback" not in err


# ---------------------------------------------------------------------------
# AC8 -- [DOC] module docstring states the AC-token false-positive risk,
# per-declared-dimension evaluation, and the "cut test, not a stop test"
# contract (SHIP_NARROW_PLAN always requires a fresh plan-check round
# afterward), citing the research spec's Part 4.1 and H-SPEC-REWRITE-DIFF-1.
#
# These checks are necessarily keyword/substring-based, not exact-sentence
# matches: the spec states CONCEPTS the docstring must convey, not verbatim
# prose (unlike the VERDICT_*/REASON_* literal strings AC1 pins exactly).
# The two citation checks (H-SPEC-REWRITE-DIFF-1, "4.1") are the one part of
# this AC that IS a concrete, checkable identifier rather than a paraphrase.
# ---------------------------------------------------------------------------

class TestAC8ModuleDocstring:
    def test_docstring_states_ac_token_false_positive_risk(self):
        _require_module()
        doc = (psg.__doc__ or "").lower()
        assert "ac" in doc
        assert ("false positive" in doc or "false-positive" in doc
                or "over-inclusive" in doc)

    def test_docstring_states_per_declared_dimension_evaluation(self):
        _require_module()
        doc = (psg.__doc__ or "").lower()
        assert "dimension" in doc
        assert ("sufficient" in doc or "one of the two" in doc
                or "either" in doc)

    def test_docstring_states_cut_test_not_stop_test_never_suppresses(self):
        _require_module()
        doc = (psg.__doc__ or "").lower()
        assert "cut test" in doc
        assert "stop test" in doc
        assert "suppress" in doc

    def test_docstring_states_fresh_plan_check_required_after_ship_narrow(self):
        _require_module()
        doc = psg.__doc__ or ""
        assert "SHIP_NARROW_PLAN" in doc
        assert "plan-check" in doc.lower()

    def test_docstring_cites_research_spec_and_h_spec_rewrite_diff_1(self):
        _require_module()
        doc = psg.__doc__ or ""
        assert "H-SPEC-REWRITE-DIFF-1" in doc
        assert "4.1" in doc
