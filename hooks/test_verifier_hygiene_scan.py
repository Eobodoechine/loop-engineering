#!/usr/bin/env python3
"""Direct unit tests for hooks/verifier_hygiene_scan.py (AC7,
H-PRETOOLUSE-VERIFIER-HYGIENE-1 -- spec.md Part 1).

This module does not exist yet -- these tests are RED until the Coder
extracts it out of loop_stop_guard.py, per Tier-1 test-writer convention
(tests before implementation). They exercise the shared functions DIRECTLY
(no subprocess, no hook harness) since verifier_hygiene_scan.py is a
stdlib-only, side-effect-free module per its own design (Part 1's docstring:
"safe to import from any hook without triggering stdin reads or sys.exit").

CRITICAL, non-negotiable constraint (spec.md AC7, widened round-2): every
hygiene-marker string used ANYWHERE in this file -- fixtures, docstrings,
comments, assertion messages, all of it -- is built via NON-CONTIGUOUS
string concatenation (matching hyg_markers()'s own "tests " + "passed"
convention), because
hooks/test_pre_tool_use_oga_guard.py::TestNoLiteralMarkersInHooks::
test_hooks_dir_contains_no_contiguous_marker_literals lowercases and
substring-scans the ENTIRE content of every file in hooks/ (including this
one) with no docstring/comment exemption. A bare contiguous literal like
one of the nine marker phrases below (see MK_* constants), written out in
one un-split piece, would itself trip that sweep.

Run: python3 -m pytest hooks/test_verifier_hygiene_scan.py -q

AC7 is not considered satisfied until:
    python3 -m pytest hooks/test_pre_tool_use_oga_guard.py::TestNoLiteralMarkersInHooks -q
has ALSO been run against this real file and passes.
"""
import os
import sys
import tempfile

import pytest

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)
from verifier_hygiene_scan import (  # noqa: E402
    VERIFIER_DETECT,
    STATUS_DOC_DENYLIST,
    hyg_markers,
    hyg_known_lines,
    evaluate_hygiene,
    adj_extract_tokens,
    adj_candidate_paths,
    adj_read_target_dir,
    adj_status_doc_in_dir,
    evaluate_adjacency,
)

REAL_LOOP_TEAM_BASE = os.path.normpath(
    os.path.join(HOOKS, "..", "loop-team"))

# Every marker built the same non-contiguous way hyg_markers() itself
# constructs them -- never write these as bare contiguous literals.
MK_LAST_VERDICT = "last " + "verdict"
MK_TESTS_PASSED = "tests " + "passed"
MK_TESTS_PASSING = "tests are " + "passing"
MK_ALL_GREEN = "all " + "green"
MK_SUITE_GREEN = "suite: " + "green"
MK_HARNESS_GREEN = "harness is " + "green"
MK_DECISION_LOG = "decision " + "log"
MK_SPEC_INTERP = "spec " + "interpretation:"
MK_ALT_REJECTED = "alternatives " + "rejected"

ALL_MARKERS = (
    MK_LAST_VERDICT, MK_TESTS_PASSED, MK_TESTS_PASSING, MK_ALL_GREEN,
    MK_SUITE_GREEN, MK_HARNESS_GREEN, MK_DECISION_LOG, MK_SPEC_INTERP,
    MK_ALT_REJECTED,
)

VERIFIER_PHRASE = "independent " + "verifier"


class TestHygMarkersContract:
    """hyg_markers() itself must return exactly the 9-item, byte-identical
    marker set the real _hyg_markers() in loop_stop_guard.py already ships
    -- this is the single source of truth this whole build exists to
    establish, so its own shape must be pinned directly."""

    def test_returns_all_nine_markers_verbatim(self):
        markers = hyg_markers()
        assert set(markers) == set(ALL_MARKERS), markers

    def test_returns_a_list_not_a_generator_or_set(self):
        markers = hyg_markers()
        assert isinstance(markers, list), type(markers)

    def test_no_duplicate_markers(self):
        markers = hyg_markers()
        assert len(markers) == len(set(markers)), markers


class TestVerifierDetectByteIdentical:
    """VERIFIER_DETECT must match the same 4-alternative pattern as the real
    _VERIFIER_DETECT constant (spec's round-1 regression-audit finding: no
    stray re.I flag, no drift)."""

    def test_matches_independent_verifier_phrase(self):
        assert VERIFIER_DETECT.search("spawn an " + VERIFIER_PHRASE + " now")

    def test_matches_verifier_dot_md(self):
        assert VERIFIER_DETECT.search("read roles/verifier.md before starting")

    def test_matches_plan_check_verifier_hyphenless(self):
        assert VERIFIER_DETECT.search("plan-check verifier for widget spec")

    def test_matches_verifier_plan_check_reversed(self):
        assert VERIFIER_DETECT.search("verifier plan-check on the spec")

    def test_does_not_match_coder_description(self):
        assert not VERIFIER_DETECT.search("coder for the build")

    def test_case_sensitivity_matches_real_constant_no_extra_ignorecase_flag(self):
        """Round-1 regression-audit finding: the real _VERIFIER_DETECT has NO
        re.I flag. A silently-added re.I would be undocumented drift from the
        exact constant this build exists to make a single source of truth
        for. Since callers already lowercase their own text before matching
        (see Part 3's _vh_desc_text = str(...).lower()), the flag itself
        being ABSENT is the behavior-preserving contract -- this test pins
        that VERIFIER_DETECT.flags does not include re.IGNORECASE."""
        import re
        assert not (VERIFIER_DETECT.flags & re.IGNORECASE), (
            "VERIFIER_DETECT must not carry re.IGNORECASE -- byte-identical "
            "to the real _VERIFIER_DETECT constant, callers lowercase "
            "their own input instead")


class TestStatusDocDenylistContract:
    def test_denylist_contains_all_documented_patterns(self):
        expected = [
            "handoff*", "plan_check_log*", "*decision_log*",
            "run_log*", "*run_log*", "summary*", "run_summary*",
        ]
        assert STATUS_DOC_DENYLIST == expected, STATUS_DOC_DENYLIST


class TestHygKnownLinesTakesExplicitRolesBase:
    """Part 1's own design note: hyg_known_lines takes roles_base as a
    parameter (not derived from __file__ internally), so both
    loop_stop_guard.py and pre_tool_use_oga_guard.py can pass their own
    identical derivation without ambiguity."""

    def test_real_roles_base_returns_a_set_of_lowercased_stripped_lines(self):
        if not os.path.isdir(REAL_LOOP_TEAM_BASE):
            pytest.skip("loop-team/ not found at documented sibling path")
        lines = hyg_known_lines(REAL_LOOP_TEAM_BASE)
        assert lines is not None
        assert isinstance(lines, set)
        assert len(lines) > 0
        # every returned line is already lowercased and has no leading/
        # trailing whitespace (the caller's own contract, verified directly).
        for ln in lines:
            assert ln == ln.strip().lower(), ln

    def test_real_roles_base_includes_a_known_verifier_md_line(self):
        """Fixture-tautology guard: pull a real line out of the real
        verifier.md and confirm hyg_known_lines actually picked it up (not
        just that it returns SOME non-empty set)."""
        verifier_md = os.path.join(REAL_LOOP_TEAM_BASE, "roles", "verifier.md")
        if not os.path.isfile(verifier_md):
            pytest.skip("roles/verifier.md not found at documented path")
        with open(verifier_md, encoding="utf-8") as f:
            real_lines = [ln.strip().lower() for ln in f if ln.strip()]
        assert real_lines, "verifier.md unexpectedly has no non-blank lines"
        known = hyg_known_lines(REAL_LOOP_TEAM_BASE)
        assert real_lines[0] in known, (
            "expected the first real non-blank line of verifier.md to be "
            "present in hyg_known_lines' output")

    def test_nonexistent_roles_base_returns_none_not_empty_set(self):
        """A roles_base directory that simply has no roles/*.md files and no
        orchestrator.md -- orchestrator.md is always appended to the files
        list unconditionally (not glob-matched), so a missing orchestrator.md
        makes open() raise FileNotFoundError (an OSError subclass), caught by
        the function's own except OSError clause. The function returns None,
        not an empty set, whenever orchestrator.md is missing from the given
        roles_base."""
        empty_base = tempfile.mkdtemp(prefix="hyg-empty-roles-base-")
        lines = hyg_known_lines(empty_base)
        assert lines is None, lines

    def test_unreadable_role_file_returns_none_fail_open(self):
        """A roles_base whose roles/*.md glob matches a real path, but that
        path is unreadable (a directory masquerading as the expected file,
        so open() raises OSError) -> hyg_known_lines returns None (fail-open
        contract, matching the original inline implementation)."""
        base = tempfile.mkdtemp(prefix="hyg-unreadable-roles-base-")
        roles_dir = os.path.join(base, "roles")
        os.makedirs(roles_dir, exist_ok=True)
        # Create a DIRECTORY named like a .md file -- open() on a directory
        # raises IsADirectoryError, a subclass of OSError.
        os.makedirs(os.path.join(roles_dir, "verifier.md"), exist_ok=True)
        lines = hyg_known_lines(base)
        assert lines is None, lines


class TestEvaluateHygieneMatchesResidueOnly:
    """evaluate_hygiene must scan only the RESIDUE after subtracting known
    role-file lines -- a role file's own marker-shaped prose must never
    trigger a false positive; only Oga-added context does."""

    def test_clean_prompt_with_no_marker_returns_none(self):
        known = {"a known role line already lowercased"}
        prompt = "Read the spec at runs/x/spec.md and review the plan."
        assert evaluate_hygiene(prompt, known) is None

    def test_prompt_containing_a_marker_outside_known_lines_returns_that_marker(self):
        known = {"a known role line already lowercased"}
        prompt = "Read the spec. By the way, " + MK_TESTS_PASSED + " already."
        result = evaluate_hygiene(prompt, known)
        assert result == MK_TESTS_PASSED, result

    def test_marker_appearing_only_inside_a_known_role_line_does_not_trigger(self):
        """The exact residue-subtraction contract: a line that is ITSELF one
        of the known role-file lines (verbatim, after strip+lower) must be
        excluded from the scan entirely, even though it contains a marker
        phrase -- proving role-file content never trips the gate."""
        role_line = "our own output format instruction mentions " + MK_ALL_GREEN + " harness state"
        known = {role_line}
        prompt = role_line + "\nSpec at runs/x/spec.md. Artifact: src/w.py."
        assert evaluate_hygiene(prompt, known) is None

    def test_same_marker_text_added_as_new_line_by_oga_still_triggers(self):
        """Companion to the above: if OGA adds the SAME marker-bearing text
        as a genuinely NEW line (not verbatim-matching any known role
        line), it must still be caught -- proving the exclusion is keyed to
        exact known-line membership, not merely "this marker phrase exists
        somewhere in the role corpus."""
        known = {"our own output format instruction mentions " + MK_ALL_GREEN + " harness state"}
        prompt = "Spec at runs/x/spec.md.\n" + MK_ALL_GREEN + " on my local run, by the way."
        result = evaluate_hygiene(prompt, known)
        assert result == MK_ALL_GREEN, result

    def test_each_of_the_nine_markers_individually_detected(self):
        known = set()
        for mk in ALL_MARKERS:
            prompt = "Some Oga-added context mentioning " + mk + " here."
            result = evaluate_hygiene(prompt, known)
            assert result == mk, (mk, result)

    def test_whitespace_collapsing_still_detects_marker_split_across_irrelevant_spacing(self):
        """evaluate_hygiene collapses runs of whitespace via re.sub before
        matching -- a marker phrase whose OWN internal whitespace survives
        collapsing (e.g. extra spaces before/after, not INSIDE the marker
        itself) must still be found."""
        known = set()
        prompt = "line one has trailing spaces   \n   " + MK_DECISION_LOG + "   \nline three"
        result = evaluate_hygiene(prompt, known)
        assert result == MK_DECISION_LOG, result

    def test_first_matching_marker_in_list_order_is_returned_when_multiple_present(self):
        """Documented contract: iterate hyg_markers() in order, return the
        FIRST one found in the residue -- not necessarily the first one to
        appear positionally in the text."""
        known = set()
        # MK_ALT_REJECTED appears earlier in the text, but MK_LAST_VERDICT
        # is earlier in hyg_markers()' own returned order -- confirm the
        # returned hit matches iteration order over hyg_markers(), not text
        # position.
        markers = hyg_markers()
        assert markers.index(MK_LAST_VERDICT) < markers.index(MK_ALT_REJECTED)
        prompt = MK_ALT_REJECTED + " appears first in the text, then " + MK_LAST_VERDICT + " appears second."
        result = evaluate_hygiene(prompt, known)
        assert result == MK_LAST_VERDICT, result


class TestAdjExtractTokens:
    """adj_extract_tokens: the three token forms (absolute /, ~-paths, bare
    relative containing '/'), with trailing punctuation stripped."""

    def test_extracts_absolute_path_token(self):
        tokens = adj_extract_tokens("Read the spec at /repo/runs/x/spec.md now.")
        assert "/repo/runs/x/spec.md" in tokens, tokens

    def test_extracts_tilde_path_token(self):
        tokens = adj_extract_tokens("Read ~/Claude/loop/runs/x/spec.md please.")
        assert "~/Claude/loop/runs/x/spec.md" in tokens, tokens

    def test_extracts_bare_relative_token_containing_slash(self):
        tokens = adj_extract_tokens("Read the spec at runs/x/spec.md and review.")
        assert "runs/x/spec.md" in tokens, tokens

    def test_strips_trailing_punctuation(self):
        tokens = adj_extract_tokens("See /repo/runs/x/spec.md, then proceed.")
        assert "/repo/runs/x/spec.md" in tokens, tokens
        assert "/repo/runs/x/spec.md," not in tokens, tokens

    def test_plain_prose_with_no_path_shaped_token_returns_empty(self):
        tokens = adj_extract_tokens("Please review the plan and confirm scope.")
        assert tokens == [], tokens

    def test_multiple_tokens_all_extracted_in_order(self):
        text = "First /a/b.md then ~/c/d.md then e/f.md at the end."
        tokens = adj_extract_tokens(text)
        assert tokens == ["/a/b.md", "~/c/d.md", "e/f.md"], tokens


class TestAdjCandidatePaths:
    def test_tilde_token_expands_user_home(self):
        cands = adj_candidate_paths("~/x/spec.md", "/some/cwd", None)
        assert cands == [os.path.expanduser("~/x/spec.md")], cands

    def test_absolute_token_returned_as_is(self):
        cands = adj_candidate_paths("/abs/x/spec.md", "/some/cwd", None)
        assert cands == ["/abs/x/spec.md"], cands

    def test_bare_relative_token_resolves_against_cwd_only_when_no_target_dir(self):
        cands = adj_candidate_paths("x/spec.md", "/some/cwd", None)
        assert cands == [os.path.join("/some/cwd", "x/spec.md")], cands

    def test_bare_relative_token_resolves_against_both_cwd_and_target_dir(self):
        cands = adj_candidate_paths("x/spec.md", "/some/cwd", "/some/target")
        assert cands == [
            os.path.join("/some/cwd", "x/spec.md"),
            os.path.join("/some/target", "x/spec.md"),
        ], cands


class TestAdjReadTargetDir:
    def test_no_session_id_returns_none(self):
        assert adj_read_target_dir("") is None
        assert adj_read_target_dir(None) is None

    def test_missing_target_file_returns_none(self):
        gate_dir = tempfile.mkdtemp(prefix="hyg-adj-gate-")
        assert adj_read_target_dir("nonexistent-session", gate_dir=gate_dir) is None

    def test_existing_target_file_returns_stripped_content(self):
        gate_dir = tempfile.mkdtemp(prefix="hyg-adj-gate-")
        tfile = os.path.join(gate_dir, "real-session_target")
        with open(tfile, "w", encoding="utf-8") as f:
            f.write("  /some/repo/root  \n")
        assert adj_read_target_dir("real-session", gate_dir=gate_dir) == "/some/repo/root"

    def test_empty_target_file_returns_none(self):
        gate_dir = tempfile.mkdtemp(prefix="hyg-adj-gate-")
        tfile = os.path.join(gate_dir, "empty-session_target")
        with open(tfile, "w", encoding="utf-8") as f:
            f.write("   \n")
        assert adj_read_target_dir("empty-session", gate_dir=gate_dir) is None

    def test_unreadable_gate_dir_path_fails_open_to_none(self):
        """gate_dir points at something that will raise OSError on the
        os.path.isfile/open sequence -- e.g. a path with a non-directory
        component in the middle."""
        blocked = tempfile.mkstemp(prefix="hyg-adj-blocked-file-")[1]
        broken_gate_dir = os.path.join(blocked, "subdir")
        result = adj_read_target_dir("any-session", gate_dir=broken_gate_dir)
        assert result is None


class TestAdjStatusDocInDir:
    def test_finds_handoff_shaped_file(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        with open(os.path.join(d, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("prior verdict\n")
        assert adj_status_doc_in_dir(d) == "HANDOFF.md"

    def test_finds_plan_check_log_shaped_file(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        with open(os.path.join(d, "plan_check_log.md"), "w", encoding="utf-8") as f:
            f.write("verdict text\n")
        assert adj_status_doc_in_dir(d) == "plan_check_log.md"

    def test_finds_embedded_decision_log_shaped_file(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        with open(os.path.join(d, "restyle_decision_log.md"), "w", encoding="utf-8") as f:
            f.write("decisions\n")
        assert adj_status_doc_in_dir(d) == "restyle_decision_log.md"

    def test_finds_run_log_prefix_and_suffix_forms(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        with open(os.path.join(d, "restyle_run_log.md"), "w", encoding="utf-8") as f:
            f.write("log\n")
        assert adj_status_doc_in_dir(d) == "restyle_run_log.md"

    def test_finds_summary_and_run_summary_anchored_forms(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        with open(os.path.join(d, "run_summary.md"), "w", encoding="utf-8") as f:
            f.write("summary\n")
        assert adj_status_doc_in_dir(d) == "run_summary.md"

    def test_clean_dir_with_only_spec_returns_none(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        with open(os.path.join(d, "spec.md"), "w", encoding="utf-8") as f:
            f.write("# spec\n")
        assert adj_status_doc_in_dir(d) is None

    def test_case_insensitive_match(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        with open(os.path.join(d, "HaNdOfF.MD"), "w", encoding="utf-8") as f:
            f.write("verdict\n")
        assert adj_status_doc_in_dir(d) == "HaNdOfF.MD"

    def test_unreadable_dirpath_returns_none(self):
        assert adj_status_doc_in_dir("/nonexistent/path/does-not-exist-xyz") is None

    def test_test_file_naming_pattern_run_log_style_does_not_false_positive_narrowly(self):
        """Accepted-residual-risk companion: a file merely containing the
        substring run_log embedded in an unrelated test-runner name (not one
        of the corpus names this repo's own comment calls out as clean) is
        documented as accepted risk in the real gate's own comment -- this
        test instead pins the CLEAN case the comment calls out by name:
        ordinary test-runner filenames with no run_log substring at all must
        not match."""
        d = tempfile.mkdtemp(prefix="hyg-adj-statusdoc-")
        for name in ("test_run_evals.py", "test_runner.py", "test_run_experiment.py"):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write("# test\n")
        assert adj_status_doc_in_dir(d) is None


class TestEvaluateAdjacency:
    """evaluate_adjacency: end-to-end path-extraction + existence-gating +
    parent-dir status-doc scan."""

    def test_clean_path_with_no_status_doc_returns_none(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-eval-")
        spec_path = os.path.join(d, "spec.md")
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write("# spec\n")
        prompt = "Read the spec at %s and review it." % spec_path
        assert evaluate_adjacency(prompt, os.getcwd(), None) is None

    def test_path_beside_status_doc_returns_offending_path_and_doc_name(self):
        d = tempfile.mkdtemp(prefix="hyg-adj-eval-")
        spec_path = os.path.join(d, "spec.md")
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write("# spec\n")
        with open(os.path.join(d, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("prior verdict here\n")
        prompt = "Read the spec at %s and review it." % spec_path
        result = evaluate_adjacency(prompt, os.getcwd(), None)
        assert result == (spec_path, "HANDOFF.md"), result

    def test_hypothetical_nonexistent_path_never_flags(self):
        """Existence-gated: a path-shaped token that does not resolve to a
        real file/dir under any candidate base must be ignored entirely,
        even if its (nonexistent) parent would otherwise have matched."""
        prompt = "For example, /nonexistent/path/does-not-exist/spec.md would be one option."
        assert evaluate_adjacency(prompt, os.getcwd(), None) is None

    def test_bare_relative_token_resolves_against_target_dir(self):
        """A bare relative path (no leading / or ~) resolves against the
        supplied target_dir -- the run's own armed-target convention -- not
        merely the process cwd."""
        d = tempfile.mkdtemp(prefix="hyg-adj-eval-target-")
        os.makedirs(os.path.join(d, "runs", "x"), exist_ok=True)
        spec_path = os.path.join(d, "runs", "x", "spec.md")
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write("# spec\n")
        with open(os.path.join(d, "runs", "x", "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("verdict\n")
        prompt = "Read the spec at runs/x/spec.md and review it."
        result = evaluate_adjacency(prompt, "/some/unrelated/cwd", d)
        resolved = os.path.join(d, "runs/x/spec.md")
        assert result == (resolved, "HANDOFF.md"), result

    def test_directory_token_itself_scanned_as_its_own_parent(self):
        """When the resolved candidate IS a directory (not a file), its own
        listing (not its dirname's listing) is scanned -- per the real
        gate's `_real if os.path.isdir(_real) else os.path.dirname(_real)`
        contract."""
        d = tempfile.mkdtemp(prefix="hyg-adj-eval-dirtoken-")
        with open(os.path.join(d, "plan_check_log.md"), "w", encoding="utf-8") as f:
            f.write("verdict\n")
        prompt = "Review everything under %s carefully." % d
        result = evaluate_adjacency(prompt, os.getcwd(), None)
        assert result == (d, "plan_check_log.md"), result

    def test_first_offending_token_wins_when_multiple_present(self):
        """Documented contract: iterate tokens in extraction order, return
        the FIRST one whose candidate resolves to a status-doc-adjacent
        real path."""
        d1 = tempfile.mkdtemp(prefix="hyg-adj-eval-first-")
        d2 = tempfile.mkdtemp(prefix="hyg-adj-eval-second-")
        spec1 = os.path.join(d1, "spec.md")
        spec2 = os.path.join(d2, "spec.md")
        for p in (spec1, spec2):
            with open(p, "w", encoding="utf-8") as f:
                f.write("# spec\n")
        with open(os.path.join(d1, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("verdict\n")
        with open(os.path.join(d2, "summary.md"), "w", encoding="utf-8") as f:
            f.write("summary\n")
        prompt = "First see %s, then also %s." % (spec1, spec2)
        result = evaluate_adjacency(prompt, os.getcwd(), None)
        assert result == (spec1, "HANDOFF.md"), result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
