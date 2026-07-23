"""Tests for spec_revision_diff.py (closes H-SPEC-REWRITE-DIFF-1).

Convention matched from this repo's existing harness tests
(test_commit_diff_reread.py): invoke the real CLI as a subprocess against
fixture markdown files and assert on its documented plain-text stdout plus
its exit code.

Extended for the plan-size-governor build (spec:
loop-team/specs/plan_size_governor_spec_v1.md) to additionally cover AC9
(TestExtractAcIdsUnit, the new extract_ac_ids function) and AC10
(TestCheckAcInventory, the new --check-ac-inventory CLI flag) -- both
additive; every pre-existing class above them (AC11's regression
requirement) is unmodified.

Run: python3 -m pytest loop-team/harness/test_spec_revision_diff.py -q
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "spec_revision_diff.py")

sys.path.insert(0, HERE)
import spec_revision_diff as sdiff  # noqa: E402


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _run(args, timeout=30):
    """Invoke the real CLI: python3 spec_revision_diff.py <args...>.

    Returns (exit_code, stdout, stderr).
    """
    p = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, p.stdout, p.stderr


# ---------------------------------------------------------------------------
# Clean case: every OLD heading still present in NEW -> exit 0
# ---------------------------------------------------------------------------

class TestNoDroppedHeadingsExitsZero:
    """A revision that keeps every OLD heading (verbatim) in NEW, even if
    NEW adds brand-new headings or reorders existing ones, reports no
    drops and exits 0."""

    def test_all_headings_retained_exits_zero(self, tmp_path):
        old = tmp_path / "spec_v1.md"
        new = tmp_path / "spec_v2.md"
        _write(old, """\
# Spec v1

## Overview
Some overview.

## record_sigs design
Defines record_sigs precisely.

## AC7
Uses record_sigs as defined above.
""")
        _write(new, """\
# Spec v1

## AC7
Uses record_sigs as defined above, unchanged.

## record_sigs design
Defines record_sigs precisely, unchanged.

## Overview
Some overview.

## New Section
Brand new content added in this revision.
""")
        code, out, err = _run([str(old), str(new)])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "no headings dropped" in out


# ---------------------------------------------------------------------------
# Real drop case: reproduces the actual record_sigs incident
# ---------------------------------------------------------------------------

class TestDroppedHeadingDetected:
    """A full-file rewrite that silently drops a section present in OLD
    exits 1 and names the specific dropped heading -- reproduces this
    project's own real record_sigs-drop incident (H-SUBAGENT-MASKING-1
    spec v2 -> v3)."""

    def test_record_sigs_drop_incident_reproduced(self, tmp_path):
        old = tmp_path / "spec_v2.md"
        new = tmp_path / "spec_v3.md"
        _write(old, """\
# H-SUBAGENT-MASKING-1 full closure spec v2

## Overview
Full closure design.

## record_sigs design
record_sigs is a per-invocation signature list used to detect masking.

## AC7
AC7: the gate must reject any transcript whose record_sigs list is empty.
""")
        _write(new, """\
# H-SUBAGENT-MASKING-1 full closure spec v3

## Overview
Full closure design, revised to incorporate round-2 findings.

## AC7
AC7: the gate must reject any transcript whose record_sigs list is empty.

## AC8
AC8: a brand new criterion added in round 2.
""")
        code, out, err = _run([str(old), str(new)])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        # The top-level `#` title heading also legitimately differs here
        # (its own text literally says "v2" vs "v3"), so it is correctly
        # reported as dropped too under exact match -- the test's core
        # assertion is that the REAL incident's dropped section
        # (record_sigs design) is named specifically among the results.
        assert "2 heading(s)" in out
        assert "DROPPED: ## record_sigs design" in out
        assert "DROPPED: ## AC7" not in out
        assert "DROPPED: ## Overview" not in out

    def test_multiple_dropped_headings_all_named(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        _write(old, """\
## Section A
content

## Section B
content

## Section C
content
""")
        _write(new, """\
## Section A
content
""")
        code, out, err = _run([str(old), str(new)])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "2 heading(s)" in out
        assert "DROPPED: ## Section B" in out
        assert "DROPPED: ## Section C" in out
        assert "Section A" not in out.replace("Section A\ncontent", "")  # sanity: A not dropped
        assert "DROPPED: ## Section A" not in out


# ---------------------------------------------------------------------------
# Edge case: exact-match vs. reworded-but-"same" heading -- decision + test
# ---------------------------------------------------------------------------

class TestExactMatchNotFuzzy:
    """This tool uses EXACT heading-text matching, not a looser/fuzzy match
    (see spec_revision_diff.py's own module docstring for the full
    rationale). A heading whose wording changed even slightly -- while a
    human would recognize it as "the same section, renamed" -- is reported
    as DROPPED. This test documents and locks in that deliberate choice."""

    def test_slightly_reworded_heading_is_reported_as_dropped(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        _write(old, """\
## record_sigs design
Defines record_sigs.
""")
        _write(new, """\
## record_sigs Design (v3)
Defines record_sigs, retitled but content-equivalent.
""")
        code, out, err = _run([str(old), str(new)])

        # Under exact match, this reads as a drop even though a human would
        # likely call it "the same section, renamed" -- intentional, see
        # module docstring's rationale (cheap false-positive vs. expensive
        # missed silent drop).
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "DROPPED: ## record_sigs design" in out

    def test_heading_level_change_is_also_reported_as_dropped(self, tmp_path):
        """A heading demoted/promoted a level (## -> ###) is also flagged
        under this tool's exact hash-run+text match -- see module
        docstring."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        _write(old, "## Design\ncontent\n")
        _write(new, "### Design\ncontent\n")

        code, out, err = _run([str(old), str(new)])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "DROPPED: ## Design" in out

    def test_identical_heading_different_trailing_whitespace_still_matches(self, tmp_path):
        """Whitespace-only differences (trailing spaces) must NOT count as
        a rewording -- normalization strips surrounding whitespace before
        comparing."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        _write(old, "## Design   \ncontent\n")
        _write(new, "##    Design\ncontent\n")

        code, out, err = _run([str(old), str(new)])

        assert code == 0, f"stdout={out!r} stderr={err!r}"


# ---------------------------------------------------------------------------
# Usage / IO edge cases
# ---------------------------------------------------------------------------

class TestUsageErrors:
    def test_missing_old_file_exits_2(self, tmp_path):
        old = tmp_path / "does_not_exist_old.md"
        new = tmp_path / "new.md"
        _write(new, "## A\ncontent\n")
        code, out, err = _run([str(old), str(new)])
        assert code == 2, f"stdout={out!r} stderr={err!r}"

    def test_missing_new_file_exits_2(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "does_not_exist_new.md"
        _write(old, "## A\ncontent\n")
        code, out, err = _run([str(old), str(new)])
        assert code == 2, f"stdout={out!r} stderr={err!r}"

    def test_wrong_arg_count_exits_2(self, tmp_path):
        old = tmp_path / "old.md"
        _write(old, "## A\ncontent\n")
        code, out, err = _run([str(old)])
        assert code == 2, f"stdout={out!r} stderr={err!r}"


# ---------------------------------------------------------------------------
# Unit-level coverage of extract_headings / find_dropped_headings
# ---------------------------------------------------------------------------

class TestExtractHeadingsUnit:
    def test_extract_headings_various_levels(self):
        content = "# Title\n\n## Section\n\n### Subsection\ntext\n#### Deep\n"
        headings = sdiff.extract_headings(content)
        assert headings == ["# Title", "## Section", "### Subsection", "#### Deep"]

    def test_duplicate_old_heading_reported_once(self):
        old = "## Repeated\nfirst\n\n## Repeated\nsecond\n"
        new = "## Something else\n"
        dropped = sdiff.find_dropped_headings(old, new)
        assert dropped == ["## Repeated"]


# ---------------------------------------------------------------------------
# AC9 (plan_size_governor_spec_v1.md) -- extract_ac_ids unit coverage.
#
# Mirrors TestExtractHeadingsUnit's STRUCTURAL shape only (direct function
# calls, isolated from file I/O, no subprocess/CLI -- the same isolation
# TestExtractHeadingsUnit itself uses), NOT its dedup coverage:
# TestExtractHeadingsUnit never itself tests dedup on extract_headings
# (extract_headings does not dedupe at all -- it appends every match
# unconditionally, confirmed by reading the real function above). Its one
# dedup-relevant test, test_duplicate_old_heading_reported_once directly
# above, exercises the sibling find_dropped_headings, not extract_headings.
# extract_ac_ids must dedupe INTERNALLY per its own docstring, so the tests
# below assert that directly as extract_ac_ids's own requirement.
# ---------------------------------------------------------------------------

class TestExtractAcIdsUnit:
    def test_extract_ac_ids_recognizes_various_token_forms(self):
        """Covers a heading-embedded token (AC3), a 1-digit token (AC7), a
        2-digit token (AC19), and a digit+letter-suffix token (AC46b) --
        all inside the SAME extraction, no duplicates."""
        content = (
            "## AC3 recap\n"
            "See AC7 mentioned here in prose, then AC19 and AC46b follow "
            "in this same sentence.\n"
        )
        assert sdiff.extract_ac_ids(content) == ["AC3", "AC7", "AC19", "AC46b"]

    def test_extract_ac_ids_dedupes_and_preserves_first_occurrence_order(self):
        """Distinct tokens in FIRST-occurrence order, duplicates collapsed,
        tokens found both inside heading lines (AC7's heading) and outside
        them (AC19's title-line mention, AC3/AC46b's prose mentions)."""
        content = (
            "# Title mentions AC19 first here\n\n"
            "## AC7 heading\n"
            "Body text referencing AC7 (round 30) again, and introduces "
            "AC46b too.\n\n"
            "## Another section\n"
            "Mentions AC19 again, and a brand new AC3 token, plus AC46b "
            "repeated once more.\n"
        )
        assert sdiff.extract_ac_ids(content) == ["AC19", "AC7", "AC46b", "AC3"]

    def test_extract_ac_ids_is_case_sensitive_uppercase_ac_only(self):
        """[ADVERSARIAL, beyond AC9's literal sub-case list] AC_ID_RE is
        documented as "word-bounded, uppercase AC exact" -- a stray
        re.IGNORECASE would silently widen the match and inflate the
        distinct-AC count evaluate_spec_file (AC6) depends on."""
        content = "ac19 lowercase must not match, but AC19 uppercase must.\n"
        assert sdiff.extract_ac_ids(content) == ["AC19"]


# ---------------------------------------------------------------------------
# Real-file smoke test: must not crash on this project's OWN real files
# ---------------------------------------------------------------------------

class TestRealFilesDoNotCrash:
    """Running the diff against two real files from this repo (fix_plan.md
    against itself, and against orchestrator.md) must never crash --
    finding real drops (comparing genuinely different files) is the tool
    working correctly; a crash would be a bug in the tool itself."""

    def test_real_file_against_itself_has_no_drops(self):
        repo_root = os.path.normpath(os.path.join(HERE, "..", ".."))
        real_fix_plan = os.path.join(repo_root, "fix_plan.md")
        assert os.path.isfile(real_fix_plan)

        code, out, err = _run([real_fix_plan, real_fix_plan])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert err == ""

    def test_real_different_files_do_not_crash(self):
        repo_root = os.path.normpath(os.path.join(HERE, "..", ".."))
        real_fix_plan = os.path.join(repo_root, "fix_plan.md")
        orchestrator = os.path.join(repo_root, "loop-team", "orchestrator.md")
        assert os.path.isfile(real_fix_plan)
        assert os.path.isfile(orchestrator)

        code, out, err = _run([real_fix_plan, orchestrator])

        assert code in (0, 1), f"unexpected exit code {code}; stdout={out!r} stderr={err!r}"
        assert err == ""


# ---------------------------------------------------------------------------
# AC10 (plan_size_governor_spec_v1.md) -- --check-ac-inventory end-to-end,
# via the real CLI (subprocess), sub-cases a-m. All fixtures below that are
# NOT specifically about heading drops keep old/new headings byte-identical
# ("## Overview" / "## Details"), per the spec's own explicit pin on
# sub-cases b/c/d ("with NO heading dropped in the same fixture") -- without
# that pin, a fixture could coincidentally exercise the heading-dropped
# cell sub-case j already owns instead of isolating the cell it's meant to.
#
# Sub-case h covers "deferred_ac_ids present but not a list" via 4 separate
# concrete values (null, a number, a bare string, a dict/object) -- the
# spec's own "THREE distinct sub-values because they exercise different
# failure modes" text, expanded here into 4 test methods since null and
# number are each their own concrete instance of the same "non-iterable
# crash" failure mode.
# ---------------------------------------------------------------------------

class TestCheckAcInventory:
    # -- a: clean case -------------------------------------------------------
    def test_a_clean_case_no_headings_no_acs_dropped_exits_zero(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        text = "## Overview\nDiscusses AC1 and AC2.\n\n## Details\nMore on AC3.\n"
        _write(old, text)
        _write(new, text)
        _write_json(ledger, [])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED:" not in out

    # -- b: dropped AC, deferred, no heading drop -> exit 0 ------------------
    def test_b_ac_dropped_but_deferred_no_heading_dropped_exits_zero(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(ledger, [{"id": "TEST-DEFER-1", "deferred_ac_ids": ["AC9"]}])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "AC9" in out
        assert "UNACCOUNTED:" not in out

    # -- c: dropped AC, NOT in ledger, no heading drop -> exit 3 -------------
    def test_c_ac_dropped_not_in_ledger_no_heading_dropped_exits_3(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(ledger, [])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC9" in out

    # -- d: dropped ACs, partially deferred, no heading drop -> exit 3 -------
    def test_d_ac_dropped_partially_deferred_no_heading_dropped_exits_3(
        self, tmp_path,
    ):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1, AC9, and AC15 in this "
                     "section.\n\n## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in this section now.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(ledger, [{"id": "TEST-DEFER-2", "deferred_ac_ids": ["AC9"]}])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC15" in out
        assert "UNACCOUNTED: AC9" not in out

    # -- e: missing ledger path -> exit 2, never "zero deferred" -------------
    def test_e_missing_ledger_path_exits_2_never_treated_as_zero_deferred(
        self, tmp_path,
    ):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "does_not_exist_ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        # Guards against a false pass today (pre-implementation): argv-length
        # parsing alone already returns exit 2 for this 4-arg invocation, via
        # the pre-existing generic usage line -- so an exit-code-only check
        # would coincidentally "pass" for the wrong reason. This forces the
        # real ledger-specific error path once it exists.
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err

    # -- f: ledger top-level JSON not a list -> exit 2 -----------------------
    def test_f_ledger_top_level_not_a_list_exits_2(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(ledger, {"not": "a list"})
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err

    # -- g: real-shaped entry, no deferred_ac_ids key -> contributes nothing -
    def test_g_ledger_entry_without_deferred_ac_ids_key_contributes_nothing(
        self, tmp_path,
    ):
        """A verbatim copy of a REAL entry from the actual
        hardening_ledger.json (schema fields present, no deferred_ac_ids
        field at all) -- must not crash, and must not silently rescue a
        genuinely dropped, unaccounted AC."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        real_shaped_entry = {
            "id": "TAXAHEAD-FENCE-ENUM-INCOMPLETE-1",
            "repo": "taxahead",
            "kind": "recurring_class",
            "status": "open",
            "basis": "cited",
            "description": (
                "A 'consolidate every write of class X into N fenced "
                "primitives' spec revision missed one call site of that "
                "exact class, twice in a row, across two plan-check rounds "
                "on the same spec (taxahead diagnostics-hardening build, "
                "extract-document's post-claim writes to documents.status)."
            ),
            "citation": "fix_plan.md:7501 H-FENCE-ENUM-INCOMPLETE-1 (OPEN, "
                        "filed 2026-07-08)",
            "opened": "2026-07-08",
            "closed": None,
            "closing_reference": None,
        }
        assert "deferred_ac_ids" not in real_shaped_entry
        _write_json(ledger, [real_shaped_entry])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC9" in out
        assert "Traceback" not in err

    # -- h: deferred_ac_ids present but not a list (4 concrete values) -------
    def test_h1_ledger_deferred_ac_ids_null_does_not_crash(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(ledger, [{"id": "TEST-NULL-1", "deferred_ac_ids": None}])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC9" in out
        assert "Traceback" not in err

    def test_h2_ledger_deferred_ac_ids_number_does_not_crash(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(ledger, [{"id": "TEST-NUM-1", "deferred_ac_ids": 7}])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC9" in out
        assert "Traceback" not in err

    def test_h3_ledger_deferred_ac_ids_bare_string_does_not_rescue_dropped_ac(
        self, tmp_path,
    ):
        """"AC7" as a bare string does NOT crash even unguarded (Python
        iterates it into 'A'/'C'/'7'), and none of those single characters
        can ever collide with a real 3+-character dropped AC id. This does
        NOT claim to prove the isinstance guard prevents wrongful
        accounting (it cannot be at risk here, given this repo's AC-id
        token shape) -- it only confirms the genuinely-dropped, separately
        unaccounted AC9 still surfaces normally, unaffected by this
        malformed entry's presence."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(ledger, [{"id": "TEST-STR-1", "deferred_ac_ids": "AC7"}])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC9" in out
        assert "Traceback" not in err

    def test_h4_ledger_deferred_ac_ids_dict_does_not_rescue_dropped_ac(
        self, tmp_path,
    ):
        """Unlike h3's bare string, a dict is NOT structurally incapable of
        a silent rescue: Python iterates a dict into its own KEYS, and a
        dict's keys are full-length strings -- not single characters -- so
        they CAN collide with a real dropped AC id. This fixture forces
        that exact collision: the ledger entry's dict key ("AC9") is the
        SAME id genuinely dropped and otherwise unaccounted for in the
        fixture text, so a permissive implementation (e.g. one that lets a
        dict leak into set().update(raw) instead of strictly requiring
        isinstance(raw, list)) would wrongly treat AC9 as accounted-for and
        it would NOT appear in UNACCOUNTED output. The strict guard must
        treat this dict value as contributing nothing, same as h1/h2's
        non-list values, so AC9 must still surface here with exit code 3."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(
            ledger, [{"id": "TEST-DICT-1", "deferred_ac_ids": {"AC9": "note"}}]
        )
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC9" in out
        assert "Traceback" not in err

    # -- i: ledger not syntactically valid JSON -> exit 2, no crash ---------
    def test_i_ledger_invalid_json_exits_2_not_a_crash(self, tmp_path):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(ledger, "{ this is not valid JSON at all, [1, 2,}")
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err

    # -- j: heading dropped AND AC unaccounted -> exit 3, not 1 --------------
    def test_j_heading_dropped_and_ac_unaccounted_together_exits_3_not_1(
        self, tmp_path,
    ):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9.\n\n"
                     "## Extra Section\nSome content here, no AC tokens.\n")
        _write(new, "## Overview\nDiscusses AC1 only now.\n")
        _write_json(ledger, [])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC9" in out
        assert "DROPPED: ## Extra Section" in out

    # -- k: heading dropped, all dropped ACs deferred -> exit 1, not 3 -------
    def test_k_heading_dropped_but_all_dropped_acs_deferred_exits_1_not_3(
        self, tmp_path,
    ):
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9.\n\n"
                     "## Extra Section\nSome content here.\n")
        _write(new, "## Overview\nDiscusses AC1 only now.\n")
        _write_json(ledger, [{"id": "TEST-DEFER-K", "deferred_ac_ids": ["AC9"]}])
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "DROPPED: ## Extra Section" in out
        assert "UNACCOUNTED:" not in out

    # -- l: ledger top-level IS a list, but has a non-dict element -----------
    def test_l_ledger_list_contains_non_dict_element_exits_2(self, tmp_path):
        """Same exit code and same reasoning as sub-case f: the ledger
        doesn't have the expected list-of-objects shape, whether the
        non-conformance is at the top level (f) or at an individual element
        (this case). A mostly-well-shaped list with exactly one bad element
        is the realistic failure mode: an implementation that checks only
        isinstance(data, list) without checking each element's type would
        pass sub-case f, then crash uncaught in step 4's
        entry.get("deferred_ac_ids", []) call (a bare str has no .get())."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9 in detail.\n\n"
                     "## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in detail now, narrowed.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(
            ledger,
            [{"id": "H-1", "deferred_ac_ids": ["AC9"]}, "not-a-dict"],
        )
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err

    # -- m: ledger usage-error AND heading dropped together -> exit 2 --------
    def test_m_missing_ledger_and_heading_dropped_together_exits_2_not_1_or_3(
        self, tmp_path,
    ):
        """Reuses sub-case j's own fixture verbatim -- a heading dropped
        (## Extra Section) AND AC9 dropped-and-unaccounted, which, paired
        with a VALID-but-empty ledger as in test_j, produces exit 3 -- except
        the ledger path here is missing/unreadable (test_e's trigger)
        instead of valid. Exit code must be 2, not 1 (what the heading-diff
        alone would produce) and not 3 (what this same heading/AC shape
        produces under a valid ledger, per test_j) -- proving Public
        interface step 3's ledger usage-error check runs FIRST and
        short-circuits before either the heading-diff or the rest of the
        AC-inventory logic (including step 6's own exit-3-vs-exit-0/1
        priority) ever runs."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "does_not_exist_ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9.\n\n"
                     "## Extra Section\nSome content here, no AC tokens.\n")
        _write(new, "## Overview\nDiscusses AC1 only now.\n")
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err
        # Proves the short-circuit actually suppresses the unrelated
        # heading-diff computation, not merely overrides its exit code
        # while still computing and printing it (mirrors test_j/test_k's
        # own discipline of asserting on stdout content, not just the
        # exit code).
        assert "DROPPED:" not in out
        assert "UNACCOUNTED:" not in out

    # -- n: ledger non-list top-level AND heading dropped -> exit 2 ----------
    def test_n_ledger_non_list_top_level_and_heading_dropped_together_exits_2(
        self, tmp_path,
    ):
        """Extends test_m's priority-order proof from trigger e (missing
        ledger) to trigger f (non-list top-level). Reuses sub-case j's own
        fixture verbatim -- a heading dropped (## Extra Section) AND AC9
        dropped-and-unaccounted, which, paired with a VALID-but-empty ledger
        as in test_j, produces exit 3 -- except the ledger here is
        syntactically-valid JSON that IS loadable but whose top-level value
        is not a list (test_f's trigger), not missing/unreadable. Exit code
        must be 2, not 1 (what the heading-diff alone would produce) and not
        3 (what this same heading/AC shape produces under a valid ledger,
        per test_j) -- proving the short-circuit is not specific to a
        missing/unreadable ledger file but holds identically for a
        syntactically-loadable, wrong-shaped top-level value too."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9.\n\n"
                     "## Extra Section\nSome content here, no AC tokens.\n")
        _write(new, "## Overview\nDiscusses AC1 only now.\n")
        _write_json(ledger, {"not": "a list"})
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err
        assert "DROPPED:" not in out
        assert "UNACCOUNTED:" not in out

    # -- o: ledger invalid JSON AND heading dropped -> exit 2 ----------------
    def test_o_ledger_invalid_json_and_heading_dropped_together_exits_2(
        self, tmp_path,
    ):
        """Extends the same proof to trigger i (invalid JSON, which raises
        json.JSONDecodeError -- a ValueError subclass, not an OSError
        subclass; see test_i's own docstring for why an OSError-only guard
        would not catch this). Reuses sub-case j's own fixture verbatim,
        except the ledger here is syntactically invalid JSON (test_i's
        trigger) rather than missing or wrong-shaped. Exit code must be 2,
        not 1, not 3 -- proving this trigger's short-circuit also runs
        before the heading-diff computation, not merely before the final
        exit-code selection: a broad catch-all wrapped around the whole
        invocation, placed AFTER heading-diff has already run and printed,
        would still eventually map to exit 2 but would fail the DROPPED:
        assertion below -- exactly the ordering bug this joint fixture
        exists to catch."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9.\n\n"
                     "## Extra Section\nSome content here, no AC tokens.\n")
        _write(new, "## Overview\nDiscusses AC1 only now.\n")
        _write(ledger, "{ this is not valid JSON at all, [1, 2,}")
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err
        assert "DROPPED:" not in out
        assert "UNACCOUNTED:" not in out

    # -- p: ledger list-with-non-dict-element AND heading dropped -> exit 2 --
    def test_p_ledger_non_dict_element_and_heading_dropped_together_exits_2(
        self, tmp_path,
    ):
        """Extends the same proof to trigger l -- the highest-priority of
        n/o/p, per sub-case l's own realistic divergent-implementation risk:
        a good-faith implementation might check isinstance(data, list)
        early (at step 3, satisfying f/n's ordering requirement trivially,
        since that check is cheap and sits right at the JSON-load step)
        while deferring the per-ELEMENT dict-check into the SAME later loop
        Public interface steps 4-7 already need for deferred_ac_ids
        extraction. If that later loop runs only after the heading-diff
        computation has already produced its DROPPED: output, THIS
        fixture -- unlike test_n's bare top-level-shape violation -- would
        let DROPPED: print before the per-element check's exit-2 path is
        ever reached, even in an implementation that already correctly
        closes test_n's simpler, outer-container-only ordering risk. Reuses
        sub-case j's own fixture verbatim, except the ledger here IS a list
        (passing the outer-container check) but contains a non-dict element
        (test_l's trigger)."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1 and AC9.\n\n"
                     "## Extra Section\nSome content here, no AC tokens.\n")
        _write(new, "## Overview\nDiscusses AC1 only now.\n")
        _write_json(
            ledger,
            [{"id": "H-1", "deferred_ac_ids": ["AC9"]}, "not-a-dict"],
        )
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert err != "usage: spec_revision_diff.py <old_file> <new_file>\n"
        assert "Traceback" not in err
        assert "DROPPED:" not in out
        assert "UNACCOUNTED:" not in out

    # -- q: 2+ ledger entries, EACH independently deferring a different AC --
    def test_q_deferred_ac_ids_union_spans_every_ledger_entry_not_just_one(
        self, tmp_path,
    ):
        """Sub-cases a-p never construct a ledger with 2+ entries EACH
        independently contributing a non-empty deferred_ac_ids -- sub-case d,
        the closest existing case, pins partial-accounting but still with
        only ONE contributing entry. With at most one contributing entry, an
        ACCUMULATING union (deferred_set |= set(raw) / .update(raw), inside
        the per-entry loop) and an ASSIGNING one (deferred_set = set(raw),
        overwritten -- not merged -- on every iteration) are behaviorally
        IDENTICAL, so every sub-case above passes under either
        implementation. This fixture forces the distinction: two entries,
        one deferring AC5, the other deferring AC9. An assigning
        implementation, iterating the ledger in list order, would retain
        only the LAST entry's contribution ({"AC9"}) and silently lose the
        first ({"AC5"}), wrongly reporting "UNACCOUNTED: AC5" even though
        AC5 IS genuinely deferred by the ledger's first entry. AC12 is
        dropped and deferred by neither entry, so it must still surface --
        proving this remains a real, non-vacuous hard-failure gate, not one
        silently satisfied by treating every dropped id as deferred."""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        ledger = tmp_path / "ledger.json"
        _write(old, "## Overview\nDiscusses AC1, AC5, AC9, and AC12 in this "
                     "section.\n\n## Details\nMore on AC2.\n")
        _write(new, "## Overview\nDiscusses AC1 in this section now.\n\n"
                     "## Details\nMore on AC2.\n")
        _write_json(
            ledger,
            [
                {"id": "TEST-DEFER-Q1", "deferred_ac_ids": ["AC5"]},
                {"id": "TEST-DEFER-Q2", "deferred_ac_ids": ["AC9"]},
            ],
        )
        code, out, err = _run(
            [str(old), str(new), "--check-ac-inventory", str(ledger)]
        )
        assert code == 3, f"stdout={out!r} stderr={err!r}"
        assert "UNACCOUNTED: AC12" in out
        assert "UNACCOUNTED: AC5" not in out
        assert "UNACCOUNTED: AC9" not in out


# ---------------------------------------------------------------------------
# AC11 (plan_size_governor_spec_v1.md) -- regression gate, not a new test:
# every pre-existing class in this file above this comment
# (TestNoDroppedHeadingsExitsZero, TestDroppedHeadingDetected,
# TestExactMatchNotFuzzy, TestUsageErrors, TestExtractHeadingsUnit,
# TestRealFilesDoNotCrash) is unmodified by this extension and must still
# pass exactly as before. Confirmed by running the full suite; see the
# Test-writer dispatch's final report for the actual pass/fail counts.
# ---------------------------------------------------------------------------
