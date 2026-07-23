"""Tests for fixplan_closure_lint.py (closes H-FIXPLAN-CLOSURE-CONSISTENCY-1).

Convention matched from this repo's existing harness tests
(test_commit_diff_reread.py): invoke the real CLI as a subprocess against
fixture markdown files and assert on its documented plain-text stdout plus
its exit code -- the actual public interface Oga uses, not internal
function names (though a couple of unit-level tests exercise
find_mismatches() directly for finer-grained edge cases, since the CLI
itself is a thin wrapper around that function -- matching the same
belt-and-suspenders style already used for the sha-reference/heading-match
edge cases in this file's own module docstring).

Run: python3 -m pytest loop-team/harness/test_fixplan_closure_lint.py -q
"""
import ast
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "fixplan_closure_lint.py")

sys.path.insert(0, HERE)
import fixplan_closure_lint as lint  # noqa: E402


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _run(args, timeout=30):
    """Invoke the real CLI: python3 fixplan_closure_lint.py <args...>.

    Returns (exit_code, stdout, stderr).
    """
    p = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, p.stdout, p.stderr


# ---------------------------------------------------------------------------
# Clean case: no mismatch anywhere -> exit 0
# ---------------------------------------------------------------------------

class TestCleanFileExitsZero:
    """A file where every closure-shaped body phrase's heading already
    carries CLOSED, and every still-open heading's body carries no
    closure-shaped phrase, produces no mismatches and exits 0."""

    def test_clean_file_no_mismatches(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, """\
## H-EXAMPLE-1 -- some real fix -- CLOSED (2026-07-03, commit `abcdef1`)
Full loop closed: spec, plan-check, Test-writer, Verifier. PLAN_PASS achieved
and independently re-verified.

## H-EXAMPLE-2 (OPEN, filed 2026-07-03) -- still being worked
Diagnosis in progress. No fix built yet, nothing to claim.
""")
        code, out, err = _run([str(target)])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "no mismatches found" in out


# ---------------------------------------------------------------------------
# Real mismatch case: body claims closure, heading does not say CLOSED
# ---------------------------------------------------------------------------

class TestRealMismatchDetected:
    """A heading with no CLOSED marker whose body contains a closure-shaped
    phrase is flagged by name, and the run exits 1."""

    def test_implementation_complete_without_closed_heading_flagged(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, """\
## H-SUBAGENT-MASKING-1 (OPEN, filed 2026-07-03, medium priority)
IMPLEMENTATION COMPLETE: full closure shipped, PLAN_PASS achieved after two
rounds, see commit `f03ae8f` for the actual diff.
""")
        code, out, err = _run([str(target)])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "1 mismatch" in out
        assert "H-SUBAGENT-MASKING-1" in out
        assert "IMPLEMENTATION COMPLETE" in out
        assert "PLAN_PASS achieved" in out
        assert "commit `<sha>` reference" in out

    def test_verdict_pass_without_closed_heading_flagged(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, """\
## Some build round (2026-07-03, independent Verifier)
VERDICT: PASS -- the independent Verifier confirmed all ACs met.
""")
        code, out, err = _run([str(target)])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "Some build round" in out
        assert "VERDICT: PASS" in out

    def test_multiple_mismatches_all_reported(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, """\
## H-FIRST-1 (OPEN)
IMPLEMENTATION COMPLETE.

## H-SECOND-1 (OPEN)
VERDICT: PASS.

## H-THIRD-1 -- CLOSED (2026-07-03)
IMPLEMENTATION COMPLETE, as expected for a real closure.
""")
        code, out, err = _run([str(target)])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "2 mismatch" in out
        assert "H-FIRST-1" in out
        assert "H-SECOND-1" in out
        assert "H-THIRD-1" not in out


# ---------------------------------------------------------------------------
# Edge case: heading already says CLOSED with closure-shaped body -> no flag
# ---------------------------------------------------------------------------

class TestClosedHeadingWithClosureBodyNotFlagged:
    """A heading that already carries an explicit CLOSED marker must NOT be
    flagged even though its body is full of closure-shaped phrases -- this
    is the expected, consistent case, not a mismatch."""

    def test_closed_heading_various_punctuation_forms_not_flagged(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, """\
## H-A-1 -- some fix -- CLOSED (2026-07-03, commit `1234567`)
IMPLEMENTATION COMPLETE, PLAN_PASS achieved, VERDICT: PASS, commit `abcdef1`.

## H-B-1 (CLOSED 2026-07-03, priority: HIGH)
IMPLEMENTATION COMPLETE here too.

## H-C-1 — CLOSED (2026-07-03, loop-verified, commit 89abcde)
VERDICT: PASS confirmed by an independent Verifier, commit `89abcde`.
""")
        code, out, err = _run([str(target)])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "no mismatches found" in out

    def test_lowercase_closed_in_prose_is_not_treated_as_a_marker(self, tmp_path):
        """Real-file edge case (found against the actual fix_plan.md while
        building this tool): a heading can contain the LOWERCASE word
        "closed" as ordinary prose describing something NOT yet closed
        ("...closed instructionally not structurally..."). This must still
        be flagged if its body has a closure-shaped phrase -- the marker
        check is case-sensitive on the uppercase token CLOSED specifically,
        not a case-insensitive substring check."""
        target = tmp_path / "fix_plan.md"
        _write(target, """\
## H-REVIEW-COMMIT-1 -- gap that is closed instructionally not structurally
Built a deterministic tool: see commit `96693f8` and commit `5884604` for
the two real incidents motivating this build.
- [ ] OPEN. Still instructional-only, not structural.
""")
        code, out, err = _run([str(target)])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "H-REVIEW-COMMIT-1" in out
        assert "commit `<sha>` reference" in out


# ---------------------------------------------------------------------------
# SHA-reference proximity window: unit-level edge cases
# ---------------------------------------------------------------------------

class TestShaReferenceProximityWindow:
    """Unit-level coverage of the SHA-reference detector's documented
    proximity-window design (module docstring): catches a "commits:" list
    lead-in without requiring strict adjacency, but does not fire on an
    unrelated hex-shaped ID with no "commit" context nearby."""

    def test_multi_sha_list_after_commits_lead_in_detected(self):
        body = (
            "3 commits: `1d732d5`, `08053c4`, `8b470dc`. All independently "
            "re-verified."
        )
        assert lint._find_sha_reference(body) is True

    def test_unrelated_hex_id_with_no_commit_context_not_flagged(self):
        body = (
            "marketplace search query doc_id `27835341126073352` (rotates), "
            "vars include count/cursor/params."
        )
        assert lint._find_sha_reference(body) is False

    def test_sha_far_from_the_word_commit_on_a_long_line_not_flagged(self):
        filler = "x" * 60
        body = "commit context way over here " + filler + " then a stray `abcdef1` id"
        assert lint._find_sha_reference(body) is False

    def test_no_backticks_at_all_not_flagged(self):
        body = "we discussed commit history informally, no SHA quoted anywhere"
        assert lint._find_sha_reference(body) is False


# ---------------------------------------------------------------------------
# Usage / IO edge cases
# ---------------------------------------------------------------------------

class TestUsageErrors:
    def test_missing_file_exits_2(self, tmp_path):
        missing = tmp_path / "does_not_exist.md"
        code, out, err = _run([str(missing)])
        assert code == 2, f"stdout={out!r} stderr={err!r}"

    def test_too_many_args_exits_2(self, tmp_path):
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        _write(a, "## H-1 (OPEN)\nsome body\n")
        _write(b, "## H-1 (OPEN)\nsome body\n")
        code, out, err = _run([str(a), str(b)])
        assert code == 2, f"stdout={out!r} stderr={err!r}"


# ---------------------------------------------------------------------------
# Real-file smoke test: must not crash against this project's OWN fix_plan.md
# ---------------------------------------------------------------------------

class TestRealFixPlanDoesNotCrash:
    """Running the linter against this project's real, current fix_plan.md
    must never crash -- finding real issues is the tool working correctly;
    a non-zero, non-parseable failure would be a bug in the linter itself."""

    def test_real_fix_plan_runs_without_crashing(self):
        repo_root = os.path.normpath(os.path.join(HERE, "..", ".."))
        real_fix_plan = os.path.join(repo_root, "fix_plan.md")
        assert os.path.isfile(real_fix_plan), (
            "expected the real fix_plan.md at %s" % real_fix_plan
        )

        code, out, err = _run([real_fix_plan])

        assert code in (0, 1), f"unexpected exit code {code}; stdout={out!r} stderr={err!r}"
        assert err == "", f"expected no stderr on a normal run, got: {err!r}"


# =============================================================================
# Evidence-gate Phase 1 additive tests (spec: loop-team/runs/
# 2026-07-08_evidence-gate-phase1/specs/spec.md, ACs 4-10, 12, 13).
#
# Everything below this banner is NEW and ADDITIVE -- nothing above it (the
# original v1 test classes, or the imports at the top of the file this
# banner's own Edit did not touch beyond adding new `import` lines) has been
# modified. `fixplan_closure_lint.py` v2 (the "proof-block-required check"
# and "snapshot-cross-check") does not exist yet -- these tests are EXPECTED
# to fail (AttributeError on `lint.PROOF_REQUIRED_SINCE`, or a real
# assertion failure once that constant exists but the checks don't) until
# the Coder builds it. That is correct and expected, per
# roles/test_writer.md's own header ("Tier 1 -- spec-only, runs BEFORE
# implementation").
#
# Dates for every fixture below are computed RELATIVE to
# `lint.PROOF_REQUIRED_SINCE` (never hardcoded), since the spec's own
# round-4 fix requires the Coder to set that constant to the actual date of
# implementation (or the day after) -- not any date fixed in the spec text.
# =============================================================================

RUN_AND_RECORD = os.path.join(HERE, "run_and_record.py")

# Pinned to the exact commit where fixplan_closure_lint.py is STILL v1 (no
# proof-block-required / snapshot-cross-check logic at all) -- captured via
# `git rev-parse HEAD` while writing this test suite (2026-07-09), BEFORE
# any v2 code exists, and confirmed via `git diff HEAD -- <this file>` to be
# empty (the on-disk v1 content IS what's committed at this SHA). Used by
# TestAC9SabotageSmokeTests below; see that class's own docstring for why a
# PINNED SHA (not "HEAD") is required for the sabotage mechanism to keep
# working after the Coder's v2 commit(s) land on top of it. This assumes the
# normal, additive-commit loop-team workflow (no history rewrite/rebase/
# squash of this commit) -- flagged explicitly in this dispatch's own
# report as a design decision worth knowing about, not left implicit.
V1_BASELINE_COMMIT = "98ecb27be0a18171fedf4a46f78e4816e2305dae"
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
LINT_REL_PATH = "loop-team/harness/fixplan_closure_lint.py"


def _cutover_date():
    return date.fromisoformat(lint.PROOF_REQUIRED_SINCE)


def _on_or_after_cutover(days=0):
    """An ISO date `days` days on/after PROOF_REQUIRED_SINCE (days=0 is
    exactly the cutover date itself -- the boundary is inclusive per spec:
    "on or after")."""
    return (_cutover_date() + timedelta(days=days)).isoformat()


def _before_cutover(days=1):
    """An ISO date `days` days strictly before PROOF_REQUIRED_SINCE."""
    return (_cutover_date() - timedelta(days=days)).isoformat()


def _closed_heading(id_text, date_str):
    return "## %s -- some real fix -- CLOSED (%s, some evidence)" % (id_text, date_str)


def _proof_block(command, exit_code, proof_snapshot, verified_at=None, files=None, omit_fields=()):
    if verified_at is None:
        verified_at = "2026-07-09T00:00:00+00:00"
    field_values = [
        ("command", command),
        ("exit_code", exit_code),
        ("proof_snapshot", proof_snapshot),
    ]
    if files:
        field_values.append(("files", files))
    field_values.append(("verified_at", verified_at))
    lines = ["Proof:"]
    for name, value in field_values:
        if name in omit_fields:
            continue
        lines.append("- %s: %s" % (name, value))
    return "\n".join(lines) + "\n"


def _extract_proof_block_fields(remainder_text):
    fields = {}
    for m in re.finditer(r"^-\s*(\w+):\s*(.*)$", remainder_text, re.MULTILINE):
        fields[m.group(1)] = m.group(2).strip()
    return fields


def _make_real_snapshot(gate_dir, command_argv):
    """Invoke the REAL run_and_record.py CLI to produce a genuine snapshot
    file + Proof block, exactly as AC5/AC9(b) require ("built the same way
    as AC5's fixture"). Returns a dict of the fields run_and_record.py's OWN
    Proof block printed (command/exit_code/proof_snapshot/verified_at, and
    files if any) -- deliberately reusing the tool's OWN rendering rather
    than reconstructing it independently, so these fixtures stay correct
    even if the exact space-joined-argv rendering convention shifts.
    Fails loudly if run_and_record.py isn't runnable yet -- EXPECTED before
    the Coder builds it (see this section's own banner note)."""
    env = dict(os.environ)
    env["LOOP_GATE_DIR"] = str(gate_dir)
    p = subprocess.run(
        [sys.executable, RUN_AND_RECORD, "--"] + list(command_argv),
        capture_output=True, text=True, timeout=30, env=env,
    )
    stdout = p.stdout.lstrip()
    _record, end = json.JSONDecoder().raw_decode(stdout)
    remainder = stdout[end:]
    fields = _extract_proof_block_fields(remainder)
    assert "proof_snapshot" in fields, (
        f"run_and_record.py did not print a proof_snapshot line; "
        f"stdout={p.stdout!r} stderr={p.stderr!r}"
    )
    return fields


# ---------------------------------------------------------------------------
# AC4 [BEHAVIORAL]: CLOSED heading dated on/after PROOF_REQUIRED_SINCE with
# NO Proof block -> exit 1, stdout contains "missing proof block".
# ---------------------------------------------------------------------------

class TestAC4MissingProofBlockFlagged:
    def test_closed_heading_on_or_after_cutover_with_no_proof_block_flagged(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        heading = _closed_heading("H-AC4-1", _on_or_after_cutover(0))
        _write(target, "%s\nSome closure prose, no Proof block at all.\n" % heading)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" in out


# ---------------------------------------------------------------------------
# AC5 [BEHAVIORAL]: CLOSED heading dated on/after cutover with a Proof block
# referencing a REAL matching snapshot (generated via run_and_record.py) ->
# exit 0, no proof-related flag. This is also the direct regression test for
# round-3's exit_code string-coercion fix (int-on-disk vs string-in-Proof-
# block, e.g. 0 == "0") -- without it, this genuinely-matching fixture would
# wrongly be flagged.
# ---------------------------------------------------------------------------

class TestAC5ValidProofBlockPassesCleanly:
    def test_closed_heading_with_real_matching_snapshot_exits_zero(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ac5-evidence"])
        heading = _closed_heading("H-AC5-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" not in out
        assert "no matching proof snapshot found" not in out


# ---------------------------------------------------------------------------
# AC6 [BEHAVIORAL]: proof_snapshot path does not exist on disk -> exit 1,
# "no matching proof snapshot found".
# ---------------------------------------------------------------------------

class TestAC6MissingSnapshotFileFlagged:
    def test_proof_snapshot_path_does_not_exist_on_disk_flagged(self, tmp_path):
        heading = _closed_heading("H-AC6-1", _on_or_after_cutover(0))
        nonexistent = str(tmp_path / "gate" / "proof" / "does-not-exist.json")
        body = _proof_block("echo hello", "0", nonexistent)
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "no matching proof snapshot found" in out


# ---------------------------------------------------------------------------
# AC7 [BEHAVIORAL]: proof_snapshot DOES exist but its recorded
# command/exit_code do NOT match the Proof block's claim (a fabricated
# mismatch) -> exit 1, same "no matching proof snapshot found" substring.
# Two independent variants: a fabricated `command` mismatch, and a
# fabricated `exit_code` mismatch (the latter also the direct regression
# test for round-3's fix in the OTHER direction -- a real, GENUINE mismatch
# on exit_code must still be caught after coercing both sides to strings).
# ---------------------------------------------------------------------------

class TestAC7MismatchedSnapshotContentFlagged:
    def test_fabricated_command_mismatch_flagged(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ac7-real-evidence"])
        heading = _closed_heading("H-AC7-CMD-1", _on_or_after_cutover(0))
        body = _proof_block(
            "echo a-totally-different-command", fields["exit_code"], fields["proof_snapshot"]
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "no matching proof snapshot found" in out

    def test_fabricated_exit_code_mismatch_flagged(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["false"])  # really exits nonzero
        heading = _closed_heading("H-AC7-EXIT-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], "0", fields["proof_snapshot"])
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "no matching proof snapshot found" in out


# ---------------------------------------------------------------------------
# AC8 [DOC/BEHAVIORAL]: 100% of this file's EXISTING (v1) tests still pass
# UNMODIFIED, confirmed by the cutover-date scoping: every existing
# CLOSED-heading fixture in this file is dated BEFORE PROOF_REQUIRED_SINCE.
# This class mechanically enforces that promise (the spec's own explicit
# ask: "verify this is actually true for each one while implementing -- if
# any existing fixture happens to be dated on/after the cutover, that is
# itself a signal to reconsider the cutover date, not to silently backdate
# the fixture"). The dates below were confirmed by direct read of this
# file's v1 test classes (TestCleanFileExitsZero.test_clean_file_no_
# mismatches's H-EXAMPLE-1, TestRealMismatchDetected.test_multiple_
# mismatches_all_reported's H-THIRD-1, and TestClosedHeadingWithClosureBody
# NotFlagged.test_closed_heading_various_punctuation_forms_not_flagged's
# H-A-1/H-B-1/H-C-1 -- 5 CLOSED-with-date fixtures total, all "2026-07-03").
# Hardcoded (not re-parsed from this file's own source) deliberately, so
# this test cannot accidentally "pass" by scanning ITS OWN new post-cutover
# fixtures below this banner instead of the real pre-existing ones.
# ---------------------------------------------------------------------------

class TestAC8ExistingFixturesPredateCutover:
    EXISTING_CLOSED_FIXTURE_DATES = ["2026-07-03"] * 5

    def test_every_existing_closed_fixture_date_predates_cutover(self):
        cutover = _cutover_date()
        for d in self.EXISTING_CLOSED_FIXTURE_DATES:
            assert date.fromisoformat(d) < cutover, (
                f"existing fixture date {d} is not before PROOF_REQUIRED_SINCE="
                f"{lint.PROOF_REQUIRED_SINCE} -- breaks AC8; per spec, bump the "
                "cutover forward, do not backdate the fixture"
            )


# ---------------------------------------------------------------------------
# AC9 [BEHAVIORAL]: sabotage-smoke-test covering BOTH new guard clauses in
# isolation, per the spec's mandated byte-capture-before-mutation /
# byte-compare-after-restore mechanism (round-1 fix #3) -- NOT
# `git diff --stat`.
# ---------------------------------------------------------------------------

class TestAC9SabotageSmokeTests:
    """DECISION-LOG NOTE (flagged explicitly, not silently picked): a Tier-1
    Test-writer runs BEFORE any v2 implementation exists, so it cannot
    target specific internal function/branch names inside code that has not
    been written yet without inventing/guessing implementation shape (which
    both the Test-writer role brief's "no implementation in the test file"
    rule and this dispatch's own "do not read or reference any
    implementation" constraint forbid -- there IS no implementation to
    read). So the "stub the check" step below cannot be a surgical patch of
    one named function.

    Instead this class stubs BOTH new checks at once, by temporarily
    replacing the WHOLE `fixplan_closure_lint.py` file with its last-known
    v1 git blob (pinned to V1_BASELINE_COMMIT -- see that constant's own
    comment for why a pinned SHA, not "HEAD", is required). This is a valid
    proxy for "stub check (a) alone" / "stub check (b) alone" ONLY because
    of how AC9(a)/(b)'s two fixtures were deliberately, separately designed
    (spec round-2 fix #2): AC7's fixture already, genuinely satisfies the
    proof-block-required check (check b) on its own real merits (complete
    required fields) -- so removing check b changes nothing OBSERVABLE for
    THIS fixture; removing both checks together therefore produces the
    exact same result as stubbing ONLY check (a). Symmetric reasoning
    applies to AC9(b)'s dedicated fixture, whose proof_snapshot is real and
    genuinely matching -- so check (a) has nothing to flag on it either way.
    Each test's "unstubbed" half (run immediately before the sabotage
    mutation, in the SAME test) verifies this precondition holds for real,
    at run time, rather than merely assuming it -- self-validating, not
    just asserted in prose. If a future revision of either fixture stops
    being a genuine, real pass for the OTHER check, this proxy technique
    needs revisiting.

    This is a design decision made under a genuine sequencing constraint
    (mutate code that doesn't exist yet), not a reinterpretation of AC9's
    PASS/FAIL criteria -- both "unstubbed correctly flags" and "stubbed
    wrongly passes cleanly" are asserted exactly as specified, byte-for-byte
    restore included.
    """

    def _v1_blob_bytes(self):
        r = subprocess.run(
            ["git", "-C", REPO_ROOT, "show", "%s:%s" % (V1_BASELINE_COMMIT, LINT_REL_PATH)],
            capture_output=True, timeout=30,
        )
        assert r.returncode == 0, (
            "could not read fixplan_closure_lint.py at the pinned v1 baseline "
            "commit %s -- see this class's docstring for why a pinned SHA is "
            "used; git stderr: %r" % (V1_BASELINE_COMMIT, r.stderr)
        )
        return r.stdout

    def _sabotage_and_restore(self, target_path):
        """Shared mechanism for both AC9(a) and AC9(b): capture the live
        file's bytes, overwrite it with the pinned v1 blob, re-run the given
        fixture, restore the original bytes (even on failure), then assert
        byte-for-byte restoration. Returns (code, out, err) from the
        SABOTAGED run."""
        script_path = os.path.join(HERE, "fixplan_closure_lint.py")
        original_bytes = Path(script_path).read_bytes()
        try:
            Path(script_path).write_bytes(self._v1_blob_bytes())
            result = _run([str(target_path)])
        finally:
            Path(script_path).write_bytes(original_bytes)

        restored_bytes = Path(script_path).read_bytes()
        assert restored_bytes == original_bytes, (
            "fixplan_closure_lint.py was not byte-for-byte restored after "
            "the sabotage mutation"
        )
        return result

    def test_ac9a_snapshot_cross_check_has_teeth(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ac9a-real-evidence"])
        heading = _closed_heading("H-AC9A-1", _on_or_after_cutover(0))
        body = _proof_block(
            "echo totally-different-command", fields["exit_code"], fields["proof_snapshot"]
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        # --- unstubbed: the real (v2) check must catch this ---
        code, out, err = _run([str(target)])
        assert code == 1, f"unstubbed run should be flagged; stdout={out!r} stderr={err!r}"
        assert "no matching proof snapshot found" in out

        # --- sabotage: confirm it WRONGLY now exits 0 ---
        code2, out2, err2 = self._sabotage_and_restore(target)
        assert code2 == 0, (
            "expected the sabotaged (v1, no v2 checks) run to WRONGLY pass "
            f"cleanly; stdout={out2!r} stderr={err2!r}"
        )

    def test_ac9b_proof_block_required_check_has_teeth(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ac9b-real-evidence"])
        heading = _closed_heading("H-AC9B-1", _on_or_after_cutover(0))
        body = _proof_block(
            fields["command"], fields["exit_code"], fields["proof_snapshot"],
            omit_fields=("verified_at",),
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        # --- unstubbed: the real (v2) check must catch the missing field ---
        code, out, err = _run([str(target)])
        assert code == 1, f"unstubbed run should be flagged; stdout={out!r} stderr={err!r}"
        assert "missing proof block" in out

        # --- sabotage: confirm it WRONGLY now exits 0 ---
        code2, out2, err2 = self._sabotage_and_restore(target)
        assert code2 == 0, (
            "expected the sabotaged (v1, no v2 checks) run to WRONGLY pass "
            f"cleanly; stdout={out2!r} stderr={err2!r}"
        )


# ---------------------------------------------------------------------------
# AC10 [BEHAVIORAL]: per the explicit round-5 residual guidance carried into
# this dispatch (NOT the spec's literal wording -- see the dispatch prompt's
# own "One piece of guidance NOT yet folded into the spec text" section),
# TestRealFixPlanDoesNotCrash (v1, above this banner) is left COMPLETELY
# UNCHANGED -- it still only asserts `code in (0, 1)` against the LIVE file,
# with no proof-related content assertion, so it can never become flaky
# against future unrelated edits to that continuously-edited file.
#
# AC10's actual intent (prove the new checks don't wrongly fire against real
# historical data) is instead proven here, against a FROZEN, byte-identical
# copy of the live fix_plan.md captured at test-authoring time:
# loop-team/harness/testdata/frozen_fix_plan_evidence_gate_phase1.md,
# copied verbatim from the real fix_plan.md on 2026-07-09 (confirmed
# byte-identical via `diff` at copy time -- see this dispatch's own report).
# This is stable indefinitely regardless of future edits to the real file.
# ---------------------------------------------------------------------------

class TestAC10FrozenRealFixPlanShowsZeroProofFlags:
    FROZEN_FIXTURE = os.path.join(HERE, "testdata", "frozen_fix_plan_evidence_gate_phase1.md")

    def test_frozen_real_fix_plan_snapshot_shows_zero_proof_related_flags(self):
        assert os.path.isfile(self.FROZEN_FIXTURE), (
            "expected the frozen fix_plan.md fixture at %s" % self.FROZEN_FIXTURE
        )
        code, out, err = _run([self.FROZEN_FIXTURE])

        assert code in (0, 1), f"unexpected crash; stdout={out!r} stderr={err!r}"
        assert "missing proof block" not in out, (
            "the frozen (real, historical) fix_plan.md snapshot must show ZERO "
            "new proof-related flags -- if this fails, PROOF_REQUIRED_SINCE was "
            "set too early relative to this frozen snapshot's own CLOSED-heading "
            "dates; per AC10's fallback language, bump the cutover forward, do "
            "not treat this as a signal to change the frozen fixture"
        )
        assert "no matching proof snapshot found" not in out, (
            "the frozen (real, historical) fix_plan.md snapshot must show ZERO "
            "new proof-related flags (snapshot-cross-check false positive) -- "
            "see note above"
        )


# ---------------------------------------------------------------------------
# AC12 [BEHAVIORAL]: a CLOSED heading dated BEFORE PROOF_REQUIRED_SINCE (or
# with no parseable date at all) and NO Proof block exits 0 -- the new
# proof-required check must NOT fire on pre-cutover / undated entries.
# ---------------------------------------------------------------------------

class TestAC12CutoverGateExemptsPreCutoverHeadings:
    def test_closed_heading_before_cutover_with_no_proof_block_not_flagged(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        heading = _closed_heading("H-AC12-1", _before_cutover(1))
        _write(target, "%s\nClosure prose, no Proof block, dated safely before cutover.\n" % heading)

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" not in out
        assert "no mismatches found" in out

    def test_closed_heading_with_no_parseable_date_exempt_from_proof_required_check(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, (
            "## H-AC12-2 -- some fix -- CLOSED (no date recorded)\n"
            "Closure prose, no Proof block, and the heading carries no "
            "parseable date at all.\n"
        ))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" not in out


# ---------------------------------------------------------------------------
# AC13 [DOC]: run_and_record.py's own docstring/help text documents `-- true`
# (or the platform equivalent) as the canonical no-op proof command for a
# closure with no file-specific evidence to cite. Placed in THIS file per
# the dispatch's explicit AC13-groups-with-lint-v2-ACs assignment, even
# though the artifact under test is run_and_record.py's own documentation
# (AC13's own subject matter is conceptually tied to how a human satisfies
# THIS lint's proof-block-required check, not to run_and_record.py's core
# CLI behavior, which is why it groups here rather than in
# test_run_and_record.py).
# ---------------------------------------------------------------------------

class TestAC13CanonicalNoOpProofCommandDocumented:
    def test_run_and_record_docstring_documents_true_as_canonical_noop_proof_command(self):
        script = os.path.join(HERE, "run_and_record.py")
        assert os.path.isfile(script), "run_and_record.py does not exist yet"
        with open(script, encoding="utf-8") as f:
            source = f.read()

        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc, "expected run_and_record.py to have a module docstring"
        assert "true" in module_doc.lower(), (
            "expected the module docstring to bless a canonical no-op proof "
            "command such as `run_and_record.py -- true` for closures with no "
            "file-specific evidence to cite"
        )
        assert re.search(r"no[- ]op|no file", module_doc, re.IGNORECASE), (
            "expected the docstring to explain this is the canonical choice "
            "for a closure with no file-specific evidence to cite, not just "
            "mention the word 'true' incidentally"
        )


# ---------------------------------------------------------------------------
# Edge case, round-1 fix #4 (extraction step): a Proof block lives inside
# free-text body prose that may ALSO contain unrelated `- field: value`-
# shaped bullets elsewhere -- these must NOT pollute/shadow the isolated
# Proof: span. Not its own numbered AC, but directly required by the Public
# interface #2 extraction-step spec text ("this isolated span -- and ONLY
# this span -- is what gets handed to research_authenticity_check.py's
# field-line parsing logic").
# ---------------------------------------------------------------------------

class TestProofBlockExtractionIsolatesSpanOnly:
    def test_unrelated_field_shaped_bullets_before_proof_block_do_not_pollute_it(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "extraction-isolation-evidence-1"])
        heading = _closed_heading("H-EXTRACT-1", _on_or_after_cutover(0))
        body = (
            "Some prose first.\n"
            "- command: this-is-not-the-real-proof-block-and-should-be-ignored\n"
            "- exit_code: 999\n"
            "\n"
            + _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" not in out
        assert "no matching proof snapshot found" not in out

    def test_unrelated_field_shaped_bullets_after_proof_block_do_not_get_absorbed(self, tmp_path):
        """The extraction step stops at the first line that does not match
        the `- field: value` shape immediately following the contiguous
        Proof-block lines -- a blank line, then MORE unrelated bullets
        further down in the body, must not be treated as part of the same
        Proof block."""
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "extraction-isolation-evidence-2"])
        heading = _closed_heading("H-EXTRACT-2", _on_or_after_cutover(0))
        body = (
            _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
            + "\n"
            "Unrelated follow-up prose.\n"
            "- command: a-totally-different-later-bullet-not-part-of-the-proof-block\n"
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" not in out
        assert "no matching proof snapshot found" not in out


# ---------------------------------------------------------------------------
# Edge case: `files` is documented as optional -- a Proof block citing a
# snapshot with NO files (the AC13 canonical `-- true` no-op case) must
# still pass cleanly with no `files:` line at all.
# ---------------------------------------------------------------------------

class TestFilesFieldOptionalInProofBlock:
    def test_proof_block_with_no_files_line_passes_cleanly(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["true"])
        heading = _closed_heading("H-NOOP-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        assert "- files:" not in body  # sanity: this fixture genuinely has no files line
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"


# ---------------------------------------------------------------------------
# Edge case, directly documented in Public interface #2: "A snapshot file
# that fails to parse as JSON -> same flag, same substring (treat
# unparseable exactly like missing)."
# ---------------------------------------------------------------------------

class TestUnparseableSnapshotTreatedAsMissing:
    def test_snapshot_file_exists_but_is_not_valid_json_flagged(self, tmp_path):
        gate_dir = tmp_path / "gate"
        proof_dir = gate_dir / "proof"
        proof_dir.mkdir(parents=True)
        bad_snapshot = proof_dir / "not-valid-json.json"
        bad_snapshot.write_text("{this is not valid json,,,", encoding="utf-8")

        heading = _closed_heading("H-BADJSON-1", _on_or_after_cutover(0))
        body = _proof_block("echo hello", "0", str(bad_snapshot))
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "no matching proof snapshot found" in out


# ---------------------------------------------------------------------------
# Edge case: "Both new checks are ADDITIVE to whatever exit code the
# existing v1 check already computes for that run ... Never let one check's
# clean result suppress the other's flag." A single file containing BOTH a
# real v1-style mismatch (OPEN heading with a closure-shaped body phrase)
# AND a real v2-style violation (a CLOSED heading dated post-cutover with no
# Proof block) must report BOTH, neither suppressing the other.
# ---------------------------------------------------------------------------

class TestBothV1AndV2ChecksAreAdditiveNotMutuallySuppressing:
    def test_v1_mismatch_and_v2_missing_proof_block_both_reported_in_one_run(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        v2_heading = _closed_heading("H-V2-MISSING-PROOF-1", _on_or_after_cutover(0))
        _write(target, (
            "## H-V1-MISMATCH-1 (OPEN)\n"
            "IMPLEMENTATION COMPLETE, but the heading was never updated.\n"
            "\n"
            "%s\n"
            "No Proof block at all here.\n"
        ) % v2_heading)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "H-V1-MISMATCH-1" in out
        assert "missing proof block" in out
        assert "H-V2-MISSING-PROOF-1" in out


# ---------------------------------------------------------------------------
# Round-2 fix #1 regression coverage: the NEW date-extraction algorithm
# scans the WHOLE heading line for the first \d{4}-\d{2}-\d{2} substring,
# intentionally format-agnostic about where the date sits relative to
# CLOSED -- confirmed against the SAME 3 real punctuation shapes this
# file's own pre-existing (v1) fixtures use (`-- CLOSED (date, ...)`,
# `(CLOSED date, ...)`, `— CLOSED (date, ...)`), but dated ON/AFTER the
# cutover this time, each requiring (and each given) a valid Proof block.
# ---------------------------------------------------------------------------

class TestDateExtractionFormatAgnosticAcrossPunctuationForms:
    def test_date_extracted_correctly_regardless_of_position_relative_to_closed_token(self, tmp_path):
        gate_dir = tmp_path / "gate"
        d = _on_or_after_cutover(0)
        headings = [
            "## H-PUNCT-A-1 -- some fix -- CLOSED (%s, commit `1234567`)" % d,
            "## H-PUNCT-B-1 (CLOSED %s, priority: HIGH)" % d,
            "## H-PUNCT-C-1 — CLOSED (%s, loop-verified, commit 89abcde)" % d,
        ]
        blocks = []
        for i, heading in enumerate(headings):
            fields = _make_real_snapshot(gate_dir, ["echo", "punct-evidence-%d" % i])
            body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
            blocks.append("%s\n%s" % (heading, body))

        target = tmp_path / "fix_plan.md"
        _write(target, "\n".join(blocks))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" not in out
        assert "no matching proof snapshot found" not in out


# =============================================================================
# Evidence-gate Phase 2 additive tests (spec: loop-team/runs/
# 2026-07-09_evidence-gate-phase2/specs/spec.md, ACs 1-14, plus 2 additional
# regression tests closing a round-4-identified coverage gap -- see below).
#
# Everything below this banner is NEW and ADDITIVE -- nothing above it
# (v1's original tests or Phase 1's v2 additions) has been modified.
# `fixplan_closure_lint.py` v3 (the freshness/staleness check and the
# dirty-worktree check) does not exist yet -- these tests are EXPECTED to
# fail (AttributeError, a real assertion failure once the new flags exist
# but aren't wired up yet, or the sabotage tests' own "unstubbed run should
# be flagged" assertion) until the Coder builds it. That is correct and
# expected, per roles/test_writer.md's own header ("Tier 1 -- spec-only,
# runs BEFORE implementation").
#
# ALL 14 spec ACs are tagged [BEHAVIORAL] in the spec text itself (including
# AC13/AC14, retagged from [DOC] in round 2) -- every one of them asserts on
# a REAL subprocess run's actual exit code / stdout against a REAL git repo
# / REAL file-hash state, never a keyword grep of an artifact's prose, so
# that classification is followed as-is throughout this section; no test
# below downgrades a [BEHAVIORAL] claim to a [DOC]-shaped assertion.
#
# Two corrections folded in directly per this dispatch's own explicit
# instruction (NOT the spec's literal-but-wrong text):
#   1. AC12: the spec's literal "run with no args" text is WRONG (confirmed
#      by round 4: the CLI's no-args path resolves to the real, live
#      fix_plan.md, not the frozen fixture). TestPhase2AC12... below passes
#      the frozen fixture path EXPLICITLY instead, exactly matching Phase
#      1's own TestAC10FrozenRealFixPlanShowsZeroProofFlags pattern.
#   2. Two regression tests (TestPhase2RegressionRelativeSnapshotKey
#      DirtyWorktreeAbsPath, TestPhase2RegressionFreshnessOSErrorOn
#      UnreadableCitedFile) go BEYOND the spec's 14 numbered ACs, closing a
#      coverage gap round 4 explicitly found: round 3's two defensive fixes
#      (the dirty-worktree check's `abs_path = os.path.abspath(path)` step;
#      the freshness check's `try/except OSError` wrap) are logically
#      correct but UNEXERCISED by any of AC1-AC3/AC5-AC8 as literally
#      specified -- every spec-mandated fixture already uses an ABSOLUTE
#      cited-file path, and none simulates a permission-denied/TOCTOU read
#      failure. See each regression class's own docstring for the exact
#      construction and why it genuinely exercises the gap (not a
#      same-directory coincidence that would pass either way).
#
# Naming convention: every class below is prefixed `TestPhase2AC<N>...` (or
# `TestPhase2Regression...` for the 2 extra tests) -- DELIBERATELY, to avoid
# colliding with Phase 1's existing `TestAC4...`-`TestAC13...` class names
# immediately above this banner. Phase 2's spec reuses the SAME AC1-AC14
# numeric range for a COMPLETELY DIFFERENT set of criteria (Phase 1's AC4 is
# "missing proof block flagged"; Phase 2's AC4 is "empty files dict, no
# STALE flag, no crash") -- the numbers are spec-local, not globally unique,
# so the `Phase2` prefix is the disambiguator, not the number alone.
#
# AC11 ("100% of Phase 1's existing tests still pass UNMODIFIED") has no
# dedicated test class here by design: it is not a new assertion to encode,
# it is a promise about NOT touching anything above this banner, which is
# structurally guaranteed by every edit in this dispatch being purely
# additive (confirmed by direct re-diff before finalizing) and mechanically
# checked by running this file's full existing test suite standalone
# post-write (see this dispatch's own report for that run's real output).
#
# Companion-file decision (test_writer's own call, per this dispatch's
# instructions): appended to THIS file rather than a new companion file.
# Every Phase 2 fixture below reuses Phase 1's own already-established
# helpers (_run, _write, _closed_heading, _proof_block, _make_real_snapshot,
# _on_or_after_cutover, _before_cutover, RUN_AND_RECORD, REPO_ROOT,
# LINT_REL_PATH, the `lint` module import) verbatim -- forking a companion
# file would mean either re-importing this whole module (awkward, given
# this file is a test module, not a library) or duplicating ~10 shared
# helpers and risking silent drift between two copies. Matches this file's
# own established precedent of appending each new phase's tests onto the
# same file (v1 -> Phase 1 -> Phase 2).
# =============================================================================

# Pinned to the exact commit where fixplan_closure_lint.py is Phase-1-COMPLETE
# (has the proof-block-required + snapshot-cross-check checks) but STILL has
# NO Phase 2 code at all (no freshness check, no dirty-worktree check) --
# captured via `git rev-parse HEAD` while writing THIS test suite
# (2026-07-09), confirmed via `git diff HEAD -- <fixplan_closure_lint.py>`
# (and run_and_record.py, and this test file itself) to be empty (the
# on-disk content IS what's committed at this SHA) immediately before this
# banner's own edit was made. Used by TestPhase2AC13.../TestPhase2AC14...
# below as the "stub both new Phase-2 checks off" sabotage target -- see
# those classes' own docstrings. Same design-decision caveat Phase 1's own
# V1_BASELINE_COMMIT constant already carries: this assumes the normal,
# additive-commit loop-team workflow (no history rewrite/rebase/squash of
# this commit) -- flagged explicitly here too, not left implicit.
PHASE2_BASELINE_COMMIT = "e8ed8b8ec5237d1af6adb66ceb03f2b4d6f36b83"


# ---------------------------------------------------------------------------
# Shared Phase 2 fixture/helper builders.
# ---------------------------------------------------------------------------

def _init_scratch_git_repo(repo_dir):
    """Create a fresh, isolated scratch git repo at `repo_dir` (a pathlib
    Path, need not exist yet) with a fixed LOCAL commit identity and
    gpgsign disabled -- so Phase 2's dirty-worktree tests never depend on,
    and never touch, any global git config on the machine running them."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "phase2-test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Phase2 Test Writer"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "commit.gpgsign", "false"],
        check=True, capture_output=True,
    )


def _git_add_commit(repo_dir, paths, message):
    """git add <paths...> && git commit -m <message> inside `repo_dir`."""
    subprocess.run(
        ["git", "-C", str(repo_dir), "add"] + [str(p) for p in paths],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-q", "-m", message],
        check=True, capture_output=True,
    )


def _make_real_snapshot_with_cwd(gate_dir, command_argv, cwd):
    """Same as `_make_real_snapshot()` above, but invokes the real
    run_and_record.py CLI with its own process `cwd=` overridden to `cwd` (a
    pathlib Path) -- so a RELATIVE token in `command_argv` resolves (and
    gets recorded in the snapshot's `files` dict, keyed by that exact
    literal relative string, per `_detect_files()`'s own documented
    "original argv token string" convention) relative to `cwd`, not to
    whatever directory the test process itself happens to be running from.
    Only used by the relative-snapshot-key regression class below -- every
    spec-mandated AC fixture uses an absolute path instead, per the spec's
    own explicit instruction."""
    env = dict(os.environ)
    env["LOOP_GATE_DIR"] = str(gate_dir)
    p = subprocess.run(
        [sys.executable, RUN_AND_RECORD, "--"] + list(command_argv),
        capture_output=True, text=True, timeout=30, env=env, cwd=str(cwd),
    )
    stdout = p.stdout.lstrip()
    _record, end = json.JSONDecoder().raw_decode(stdout)
    remainder = stdout[end:]
    fields = _extract_proof_block_fields(remainder)
    assert "proof_snapshot" in fields, (
        f"run_and_record.py did not print a proof_snapshot line; "
        f"stdout={p.stdout!r} stderr={p.stderr!r}"
    )
    return fields


def _run_from_cwd(args, cwd, timeout=30):
    """Same as the shared `_run()` helper above, but overrides the lint
    subprocess's own `cwd=`. `_run()` deliberately never does this (per the
    spec's own round-1 fix #2 note: the lint subprocess normally runs from
    wherever pytest itself was invoked, matching real usage) -- only the
    relative-snapshot-key regression class below needs a controlled `cwd=`,
    to make a relative snapshot `files` key resolve deterministically."""
    p = subprocess.run(
        [sys.executable, SCRIPT] + args, cwd=str(cwd),
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, p.stdout, p.stderr


def _ac1_modified_file_fixture(tmp_path):
    """Shared builder for AC1's fixture (also reused by AC13's sabotage
    proxy, see that class's own docstring): an otherwise-valid,
    Phase-1-passing Proof block citing a real, ABSOLUTE-path file (per the
    spec's own path-resolution note) whose content is modified AFTER the
    snapshot is captured. Returns (target_fix_plan_path, evidence_file_path)."""
    gate_dir = tmp_path / "gate"
    evidence_file = tmp_path / "ac1_evidence.txt"
    evidence_file.write_text("original content\n", encoding="utf-8")

    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])
    evidence_file.write_text("MODIFIED content, after the snapshot was captured\n", encoding="utf-8")

    heading = _closed_heading("H-PHASE2-AC1-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    target = tmp_path / "fix_plan.md"
    _write(target, "%s\n%s" % (heading, body))
    return target, evidence_file


def _ac5_dirty_cited_file_fixture(tmp_path, stage_change=False):
    """Shared builder for AC5's fixture (also reused by AC14's sabotage
    proxy, see that class's own docstring): a scratch git repo with a
    committed evidence file that then gets a genuine uncommitted change
    (staged or unstaged, per `stage_change`) BEFORE the snapshot is
    captured -- so the snapshot records the DIRTY content's own hash,
    keeping the freshness check clean (nothing changes on disk AFTER
    capture) while the dirty-worktree check still has a real uncommitted
    diff (vs. the last commit) to find. Returns
    (target_fix_plan_path, evidence_file_path)."""
    repo_dir = tmp_path / "ac5_repo"
    _init_scratch_git_repo(repo_dir)
    evidence_file = repo_dir / "evidence.txt"
    evidence_file.write_text("committed content\n", encoding="utf-8")
    _git_add_commit(repo_dir, [evidence_file], "initial commit")

    evidence_file.write_text("dirty, uncommitted content\n", encoding="utf-8")
    if stage_change:
        subprocess.run(
            ["git", "-C", str(repo_dir), "add", str(evidence_file)],
            check=True, capture_output=True,
        )

    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

    heading = _closed_heading("H-PHASE2-AC5-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    target = tmp_path / "fix_plan.md"
    _write(target, "%s\n%s" % (heading, body))
    return target, evidence_file


def _ac6_clean_cited_file_fixture(tmp_path):
    """Shared builder for AC6's fixture: a scratch git repo whose committed
    evidence file's on-disk state exactly matches HEAD (clean) both before
    AND after the snapshot capture. Returns
    (target_fix_plan_path, evidence_file_path)."""
    repo_dir = tmp_path / "ac6_repo"
    _init_scratch_git_repo(repo_dir)
    evidence_file = repo_dir / "evidence.txt"
    evidence_file.write_text("committed content, never touched again\n", encoding="utf-8")
    _git_add_commit(repo_dir, [evidence_file], "initial commit")

    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

    heading = _closed_heading("H-PHASE2-AC6-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    target = tmp_path / "fix_plan.md"
    _write(target, "%s\n%s" % (heading, body))
    return target, evidence_file


def _scratch_repo_with_dirty_target(tmp_path, repo_name, fix_plan_body):
    """Build a scratch git repo whose OWN fix_plan.md (the file that will be
    linted -- the AC7/AC8 "target file itself" case, distinct from a CITED
    file) is committed with `fix_plan_body`, then modified afterward so it
    genuinely differs from HEAD (uncommitted). Returns the absolute path to
    the dirty fix_plan.md inside the repo."""
    repo_dir = tmp_path / repo_name
    _init_scratch_git_repo(repo_dir)
    target = repo_dir / "fix_plan.md"
    _write(target, fix_plan_body)
    _git_add_commit(repo_dir, [target], "initial commit")

    with open(target, "a", encoding="utf-8") as f:
        f.write("\n<!-- locally modified after commit, uncommitted -->\n")
    return target


def _phase2_baseline_blob_bytes():
    r = subprocess.run(
        ["git", "-C", REPO_ROOT, "show", "%s:%s" % (PHASE2_BASELINE_COMMIT, LINT_REL_PATH)],
        capture_output=True, timeout=30,
    )
    assert r.returncode == 0, (
        "could not read fixplan_closure_lint.py at the pinned Phase-2 "
        "baseline commit %s -- see PHASE2_BASELINE_COMMIT's own comment; "
        "git stderr: %r" % (PHASE2_BASELINE_COMMIT, r.stderr)
    )
    return r.stdout


def _sabotage_with_phase2_baseline_and_restore(run_args, cwd=None):
    """Shared mechanism for AC13/AC14: capture the live fixplan_closure_
    lint.py's bytes, overwrite it with the pinned Phase-2-baseline
    (Phase-1-only, no freshness/dirty-worktree checks) blob, re-run the
    given fixture, restore the original bytes (even on failure), then
    assert byte-for-byte restoration. Matches Phase 1's own
    TestAC9SabotageSmokeTests mechanism exactly (byte-capture-before-
    mutation, byte-compare-after-restore -- NOT `git diff --stat`), applied
    to a DIFFERENT pinned baseline appropriate to Phase 2. Returns
    (code, out, err) from the SABOTAGED run."""
    script_path = os.path.join(HERE, "fixplan_closure_lint.py")
    original_bytes = Path(script_path).read_bytes()
    try:
        Path(script_path).write_bytes(_phase2_baseline_blob_bytes())
        if cwd is not None:
            result = _run_from_cwd(run_args, cwd)
        else:
            result = _run(run_args)
    finally:
        Path(script_path).write_bytes(original_bytes)

    restored_bytes = Path(script_path).read_bytes()
    assert restored_bytes == original_bytes, (
        "fixplan_closure_lint.py was not byte-for-byte restored after the "
        "Phase-2 sabotage mutation"
    )
    return result


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL]: cited file's content modified AFTER capture -> STALE.
# ---------------------------------------------------------------------------

class TestPhase2AC1CitedFileModifiedAfterCaptureFlaggedStale:
    def test_modified_cited_file_flagged_stale(self, tmp_path):
        target, evidence_file = _ac1_modified_file_fixture(tmp_path)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "STALE" in out
        assert "changed since" in out
        assert str(evidence_file) in out


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL]: cited file DELETED (not modified) after capture -> STALE,
# same "(file no longer exists)" message shape.
# ---------------------------------------------------------------------------

class TestPhase2AC2CitedFileDeletedAfterCaptureFlaggedStale:
    def test_deleted_cited_file_flagged_stale_no_longer_exists(self, tmp_path):
        gate_dir = tmp_path / "gate"
        evidence_file = tmp_path / "ac2_evidence.txt"
        evidence_file.write_text("will be deleted\n", encoding="utf-8")
        fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])
        os.remove(evidence_file)

        heading = _closed_heading("H-PHASE2-AC2-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "STALE" in out
        assert "no longer exists" in out
        assert str(evidence_file) in out


# ---------------------------------------------------------------------------
# AC3 [BEHAVIORAL]: cited file unchanged since capture -> clean, no STALE.
# ---------------------------------------------------------------------------

class TestPhase2AC3CitedFileUnchangedNotFlaggedStale:
    def test_cited_file_unchanged_since_capture_not_flagged(self, tmp_path):
        gate_dir = tmp_path / "gate"
        evidence_file = tmp_path / "ac3_evidence.txt"
        evidence_file.write_text("stable content, never touched again\n", encoding="utf-8")
        fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

        heading = _closed_heading("H-PHASE2-AC3-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "STALE" not in out


# ---------------------------------------------------------------------------
# AC4 [BEHAVIORAL]: valid Proof block citing NO files (canonical `-- true`
# no-op, empty files dict) -> no STALE flag, no crash.
# ---------------------------------------------------------------------------

class TestPhase2AC4EmptyFilesDictNoStaleFlagNoCrash:
    def test_no_op_true_proof_block_no_files_no_stale_flag(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["true"])
        heading = _closed_heading("H-PHASE2-AC4-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        assert "- files:" not in body  # sanity: this fixture genuinely cites no files
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "STALE" not in out


# ---------------------------------------------------------------------------
# AC5 [BEHAVIORAL]: cited file has a genuine UNCOMMITTED change (staged OR
# unstaged -- either counts, tested both ways) -> "evidence file has
# uncommitted changes".
# ---------------------------------------------------------------------------

class TestPhase2AC5CitedFileUncommittedChangesFlagged:
    def test_unstaged_uncommitted_change_flagged(self, tmp_path):
        target, evidence_file = _ac5_dirty_cited_file_fixture(tmp_path, stage_change=False)
        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" in out
        assert str(evidence_file) in out

    def test_staged_uncommitted_change_flagged(self, tmp_path):
        target, evidence_file = _ac5_dirty_cited_file_fixture(tmp_path, stage_change=True)
        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" in out
        assert str(evidence_file) in out


# ---------------------------------------------------------------------------
# AC6 [BEHAVIORAL]: cited file's on-disk state exactly matches its last
# commit (clean) -> no dirty-worktree flag for that file.
# ---------------------------------------------------------------------------

class TestPhase2AC6CitedFileMatchesLastCommitNotFlagged:
    def test_clean_cited_file_not_flagged(self, tmp_path):
        target, evidence_file = _ac6_clean_cited_file_fixture(tmp_path)
        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" not in out


# ---------------------------------------------------------------------------
# AC7 [BEHAVIORAL]: the TARGET file itself (fix_plan.md, the file being
# linted) has uncommitted changes, with >=1 in-scope Phase-1-passing CLOSED
# heading present -> flagged referencing the TARGET file, with the
# "(the file being linted)" suffix distinguishing it from AC5's per-cited-
# file variant.
# ---------------------------------------------------------------------------

class TestPhase2AC7TargetFileItselfDirtyFlagged:
    def test_target_file_with_uncommitted_changes_flagged_referencing_itself(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["true"])  # no-op, no cited files at all
        heading = _closed_heading("H-PHASE2-AC7-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        fix_plan_body = "%s\n%s" % (heading, body)

        target = _scratch_repo_with_dirty_target(tmp_path, "ac7_repo", fix_plan_body)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" in out
        assert "(the file being linted)" in out
        assert str(target) in out


# ---------------------------------------------------------------------------
# AC8 [BEHAVIORAL]: the target-file-dirtiness check does NOT fire when there
# are zero in-scope, Phase-1-passing CLOSED headings -- even though the
# target file itself is genuinely dirty. Two sub-cases: (a) zero CLOSED
# headings at all; (b) a CLOSED, in-scope heading IS present but FAILS
# Phase 1's own check (so it doesn't count as "Phase-1-passing" either).
# ---------------------------------------------------------------------------

class TestPhase2AC8TargetFileDirtinessSkippedWhenNothingToProtect:
    def test_no_closed_headings_at_all_target_dirty_not_flagged(self, tmp_path):
        fix_plan_body = (
            "## H-PHASE2-AC8-OPEN-1 (OPEN, filed for this test)\n"
            "Still being worked, no closure claimed.\n"
        )
        target = _scratch_repo_with_dirty_target(tmp_path, "ac8a_repo", fix_plan_body)

        code, out, err = _run([str(target)])
        assert "evidence file has uncommitted changes" not in out, (
            f"target-file dirtiness check must be skipped with zero CLOSED "
            f"headings in the file; stdout={out!r} stderr={err!r}"
        )

    def test_closed_heading_present_but_phase1_failing_target_dirty_not_flagged(self, tmp_path):
        heading = _closed_heading("H-PHASE2-AC8-FAIL-1", _on_or_after_cutover(0))
        # Deliberately NO Proof block at all -- fails Phase 1's own
        # proof-block-required check, so this heading does not count as
        # "Phase-1-passing" even though it IS a CLOSED, in-scope heading.
        fix_plan_body = "%s\nClosure prose, but no Proof block at all.\n" % heading
        target = _scratch_repo_with_dirty_target(tmp_path, "ac8b_repo", fix_plan_body)

        code, out, err = _run([str(target)])
        assert "missing proof block" in out  # sanity: Phase 1 does flag this heading
        assert "evidence file has uncommitted changes" not in out, (
            f"target-file dirtiness check must be skipped when the only "
            f"CLOSED heading present FAILED Phase 1's own check; "
            f"stdout={out!r} stderr={err!r}"
        )


# ---------------------------------------------------------------------------
# AC9 [BEHAVIORAL]: a heading whose Proof block FAILS Phase 1's own checks
# does NOT additionally get a freshness or dirty-worktree flag -- only
# Phase 1's own flag appears. Two sub-cases matching Phase 1's own two
# failure modes: a missing required field, and a fabricated/mismatched
# snapshot -- each constructed so the underlying cited file is ALSO
# genuinely stale and/or dirty in reality, so a Phase 2 double-flag would be
# real and observable if the scoping rule were broken.
# ---------------------------------------------------------------------------

class TestPhase2AC9Phase1FailingHeadingNotDoubleFlagged:
    def test_missing_required_field_not_also_freshness_flagged(self, tmp_path):
        gate_dir = tmp_path / "gate"
        evidence_file = tmp_path / "ac9_evidence_missing_field.txt"
        evidence_file.write_text("original\n", encoding="utf-8")
        fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])
        # Genuinely stale in reality (modified after capture) -- but this
        # heading's Proof block is INCOMPLETE (Phase 1 fails it), so Phase 2
        # must not layer an additional STALE flag on top.
        evidence_file.write_text("genuinely modified after capture\n", encoding="utf-8")

        heading = _closed_heading("H-PHASE2-AC9-MISSING-1", _on_or_after_cutover(0))
        body = _proof_block(
            fields["command"], fields["exit_code"], fields["proof_snapshot"],
            omit_fields=("verified_at",),
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "missing proof block" in out
        assert "STALE" not in out
        assert "evidence file has uncommitted changes" not in out

    def test_fabricated_snapshot_mismatch_not_also_dirty_or_stale_flagged(self, tmp_path):
        repo_dir = tmp_path / "ac9_repo"
        _init_scratch_git_repo(repo_dir)
        evidence_file = repo_dir / "evidence.txt"
        evidence_file.write_text("committed\n", encoding="utf-8")
        _git_add_commit(repo_dir, [evidence_file], "initial")

        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

        # Make the cited file BOTH stale (content changed) AND dirty
        # (uncommitted vs HEAD) after capture -- would trip BOTH new checks
        # if Phase 2 ran on this heading. It must not, because the Proof
        # block below deliberately claims a fabricated command, failing
        # Phase 1's own snapshot-cross-check.
        evidence_file.write_text("genuinely modified AND uncommitted\n", encoding="utf-8")

        heading = _closed_heading("H-PHASE2-AC9-FABRICATED-1", _on_or_after_cutover(0))
        body = _proof_block(
            "cat a-totally-different-fabricated-path", fields["exit_code"], fields["proof_snapshot"]
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "no matching proof snapshot found" in out
        assert "STALE" not in out
        assert "evidence file has uncommitted changes" not in out


# ---------------------------------------------------------------------------
# AC10 [BEHAVIORAL]: both new checks remain scoped to PROOF_REQUIRED_SINCE
# -- a pre-cutover CLOSED heading with no Proof block at all (Phase 1's
# existing exemption) never triggers a Phase 2 flag either.
# ---------------------------------------------------------------------------

class TestPhase2AC10PreCutoverHeadingNoProofBlockNoPhase2Flag:
    def test_pre_cutover_closed_heading_no_proof_block_no_stale_or_dirty_flag(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        heading = _closed_heading("H-PHASE2-AC10-1", _before_cutover(1))
        _write(target, "%s\nClosure prose, no Proof block, dated safely before cutover.\n" % heading)

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "STALE" not in out
        assert "evidence file has uncommitted changes" not in out


# ---------------------------------------------------------------------------
# AC12 [BEHAVIORAL] -- built per the ROUND-4 CORRECTION, not the spec's
# literal "run with no args" text (confirmed WRONG: the CLI's no-args path
# resolves to the real, live fix_plan.md, not the frozen fixture; there is
# no way to target a specific file without passing it as argv[1]). Passes
# the frozen fixture path EXPLICITLY, exactly matching Phase 1's own
# TestAC10FrozenRealFixPlanShowsZeroProofFlags pattern
# (`_run([self.FROZEN_FIXTURE])`), reusing the SAME frozen fixture file
# Phase 1's AC10 already established -- no new fixture created.
# ---------------------------------------------------------------------------

class TestPhase2AC12FrozenFixtureExplicitPathShowsZeroFlags:
    FROZEN_FIXTURE = os.path.join(HERE, "testdata", "frozen_fix_plan_evidence_gate_phase1.md")

    def test_frozen_fixture_scoping_precondition_is_zero_in_scope_headings(self):
        """States explicitly which of AC12's two documented cases applies,
        per the spec's own instruction ("state explicitly in the test which
        case applies once you've inspected the fixture") -- confirmed
        PROGRAMMATICALLY (via Phase 1's own already-existing
        `_proof_required_for_heading` scoping helper, not reimplemented
        here, and not just assumed in prose): the frozen fixture's latest
        CLOSED-heading date is 2026-07-08 (confirmed by direct grep at
        test-authoring time), one day BEFORE PROOF_REQUIRED_SINCE
        ("2026-07-09") -- so it has ZERO in-scope headings. This is AC12's
        documented "plausible" fallback case ("If the frozen fixture happens
        to have zero in-scope CLOSED headings at all ... this AC should
        still pass trivially"), not the "has real in-scope Proof blocks"
        case."""
        with open(self.FROZEN_FIXTURE, encoding="utf-8") as f:
            content = f.read()
        in_scope_headings = [
            heading_line for heading_line, _body in lint._iter_blocks(content)
            if lint._proof_required_for_heading(heading_line)
        ]
        assert in_scope_headings == [], (
            "expected the frozen fixture to have ZERO in-scope (CLOSED, "
            "dated on/after PROOF_REQUIRED_SINCE) headings -- if this now "
            "fails, the frozen fixture DOES exercise real in-scope Proof "
            "blocks and the test below needs re-reading with that in mind, "
            "per AC12's own documented fallback language: %r" % in_scope_headings
        )

    def test_frozen_fixture_explicit_path_no_crash_zero_new_phase2_flags(self):
        assert os.path.isfile(self.FROZEN_FIXTURE), (
            "expected the frozen fix_plan.md fixture at %s" % self.FROZEN_FIXTURE
        )
        code, out, err = _run([self.FROZEN_FIXTURE])

        assert code in (0, 1), f"unexpected crash; stdout={out!r} stderr={err!r}"
        assert "STALE" not in out, (
            "the frozen (real, historical) fix_plan.md snapshot must show "
            "ZERO new freshness flags -- see "
            "test_frozen_fixture_scoping_precondition_is_zero_in_scope_"
            "headings for why this is expected to be trivially true (zero "
            "in-scope headings to check in the first place)"
        )
        assert "evidence file has uncommitted changes" not in out, (
            "the frozen (real, historical) fix_plan.md snapshot must show "
            "ZERO new dirty-worktree flags -- see the scoping-precondition "
            "test above"
        )


# ---------------------------------------------------------------------------
# AC13 [BEHAVIORAL] (round-2 retag): sabotage-smoke-test proving the
# freshness check has teeth.
# ---------------------------------------------------------------------------

class TestPhase2AC13FreshnessCheckSabotageSmokeTest:
    """Reuses the exact byte-capture-before-mutation / byte-compare-after-
    restore mechanism Phase 1's TestAC9SabotageSmokeTests established (NOT
    `git diff --stat`), pinned to PHASE2_BASELINE_COMMIT -- the last commit
    before ANY Phase 2 code exists (see that constant's own comment) --
    since, per this Tier-1 dispatch's own constraint, there is no Phase-2-
    specific function name yet to target a surgical patch against.

    Proxy validity for isolating "freshness check alone": AC1's own fixture
    (reused verbatim via `_ac1_modified_file_fixture`) lives entirely under
    `tmp_path`, outside any git repo, so the sibling dirty-worktree check's
    repo-resolution step always fails silently regardless of whether that
    check exists in the running script at all -- confirmed below, in the
    SAME test, via the unstubbed run's own clean absence of any
    dirty-worktree flag, before sabotaging.
    """

    def test_ac13_freshness_check_has_teeth(self, tmp_path):
        target, evidence_file = _ac1_modified_file_fixture(tmp_path)

        # --- unstubbed: the real (Phase 2) check must catch this ---
        code, out, err = _run([str(target)])
        assert code == 1, f"unstubbed run should be flagged; stdout={out!r} stderr={err!r}"
        assert "STALE" in out
        assert "evidence file has uncommitted changes" not in out  # proxy-validity precondition

        # --- sabotage: confirm it WRONGLY now exits 0 ---
        code2, out2, err2 = _sabotage_with_phase2_baseline_and_restore([str(target)])
        assert code2 == 0, (
            "expected the sabotaged (Phase-1-only, no Phase-2 checks) run to "
            f"WRONGLY pass cleanly; stdout={out2!r} stderr={err2!r}"
        )


# ---------------------------------------------------------------------------
# AC14 [BEHAVIORAL] (round-2 retag): sabotage-smoke-test proving the
# dirty-worktree check (per-cited-file variant, AC5) has teeth.
# ---------------------------------------------------------------------------

class TestPhase2AC14DirtyWorktreeCheckSabotageSmokeTest:
    """Same sabotage mechanism as AC13, targeting the per-cited-file
    dirty-worktree check via AC5's fixture (reused verbatim, unstaged
    variant).

    Proxy validity: AC5's fixture's evidence file is only modified BEFORE
    the snapshot is captured (see `_ac5_dirty_cited_file_fixture`'s own
    docstring), so its content at check time is byte-identical to what the
    snapshot recorded -- the sibling freshness check has nothing to flag
    regardless of whether it exists in the running script at all; confirmed
    below, in the unstubbed run, before sabotaging.
    """

    def test_ac14_dirty_worktree_check_has_teeth(self, tmp_path):
        target, evidence_file = _ac5_dirty_cited_file_fixture(tmp_path, stage_change=False)

        # --- unstubbed: the real (Phase 2) check must catch this ---
        code, out, err = _run([str(target)])
        assert code == 1, f"unstubbed run should be flagged; stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" in out
        assert "STALE" not in out  # proxy-validity precondition

        # --- sabotage: confirm it WRONGLY now exits 0 ---
        code2, out2, err2 = _sabotage_with_phase2_baseline_and_restore([str(target)])
        assert code2 == 0, (
            "expected the sabotaged (Phase-1-only, no Phase-2 checks) run to "
            f"WRONGLY pass cleanly; stdout={out2!r} stderr={err2!r}"
        )


# =============================================================================
# Two additional regression tests, BEYOND the spec's literal 14 ACs, per
# this dispatch's explicit instruction: round 4 found round 3's two
# defensive fixes logically correct but UNEXERCISED by any AC1-AC3/AC5-AC8
# fixture as literally specified. See each class's own docstring.
# =============================================================================

class TestPhase2RegressionRelativeSnapshotKeyDirtyWorktreeAbsPath:
    """Closes the round-4-identified gap around the dirty-worktree check's
    `abs_path = os.path.abspath(path)` normalization step (round-3 fix).

    Without that step, `git -C <repo> status --porcelain -- <path>` resolves
    a RELATIVE `<path>` relative to `<repo>` (the `-C` target), not the
    lint's own CWD -- silently checking the wrong file whenever the
    resolved repo toplevel differs from the lint's own CWD. Every AC1-AC3/
    AC5-AC8 fixture mandated by the spec text uses an ABSOLUTE cited-file
    path (the spec's own explicit fixture requirement), so none of them
    exercises this normalization step at all.

    Design decision (flagged explicitly, not silently picked, per this
    dispatch's own "you decide the exact mechanism" instruction): this class
    invokes `run_and_record.py` with a RELATIVE argv token ("evidence.txt")
    from a controlled `cwd=` that is a SUBDIRECTORY of the git repo's own
    toplevel (`<repo>/subdir/`), not the repo root itself -- a bare
    same-directory-as-repo-root construction would NOT actually distinguish
    correct-vs-buggy behavior (a naive non-abspath implementation would
    coincidentally still resolve the right file when the repo root and the
    lint's CWD happen to be identical). Nesting the cited file one directory
    below the resolved repo toplevel makes `os.path.dirname(<relative
    path>)` (what a naive, non-abspath implementation would feed into repo
    resolution) diverge from the correct behavior, so this test genuinely
    exercises the fix rather than passing by coincidence either way.
    `fixplan_closure_lint.py` itself is also invoked from that SAME
    controlled `cwd=` (mirroring how a real user would naturally invoke both
    commands from one working directory), via the dedicated
    `_run_from_cwd()` helper above -- the shared module-level `_run()`
    helper deliberately never overrides `cwd=` (see the spec's own round-1
    fix #2 note), so this class adds its own.
    """

    def test_relative_snapshot_key_dirty_correctly_flagged(self, tmp_path):
        repo_dir = tmp_path / "relkey_repo_dirty"
        _init_scratch_git_repo(repo_dir)
        subdir = repo_dir / "subdir"
        subdir.mkdir()
        evidence_file = subdir / "evidence.txt"
        evidence_file.write_text("committed content\n", encoding="utf-8")
        _git_add_commit(repo_dir, [evidence_file], "initial commit")

        # Genuine uncommitted change, made BEFORE capture so the freshness
        # check stays clean (isolating this test to the dirty-worktree
        # check specifically -- see this class's own docstring).
        evidence_file.write_text("dirty, uncommitted content\n", encoding="utf-8")

        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot_with_cwd(gate_dir, ["cat", "evidence.txt"], cwd=subdir)
        assert fields.get("files") == "evidence.txt" or "evidence.txt" in fields.get("files", ""), (
            f"sanity check: expected the snapshot's files field to be the "
            f"RAW relative token 'evidence.txt', got {fields.get('files')!r}"
        )

        heading = _closed_heading("H-PHASE2-RELKEY-DIRTY-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        target = tmp_path / "fix_plan.md"  # deliberately OUTSIDE repo_dir/subdir
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run_from_cwd([str(target)], cwd=subdir)
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" in out
        assert "evidence.txt" in out
        assert "STALE" not in out  # isolating this to the dirty-worktree check only

    def test_relative_snapshot_key_clean_correctly_not_flagged(self, tmp_path):
        repo_dir = tmp_path / "relkey_repo_clean"
        _init_scratch_git_repo(repo_dir)
        subdir = repo_dir / "subdir"
        subdir.mkdir()
        evidence_file = subdir / "evidence.txt"
        evidence_file.write_text("committed content, never touched again\n", encoding="utf-8")
        _git_add_commit(repo_dir, [evidence_file], "initial commit")

        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot_with_cwd(gate_dir, ["cat", "evidence.txt"], cwd=subdir)

        heading = _closed_heading("H-PHASE2-RELKEY-CLEAN-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run_from_cwd([str(target)], cwd=subdir)
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" not in out


class TestPhase2RegressionFreshnessOSErrorOnUnreadableCitedFile:
    """Closes the round-4-identified gap around the freshness check's
    `try/except OSError` wrap (round-3 fix) on the current-content hash-read.

    A file that PASSES `os.path.isfile()` can still fail to actually open
    (permission error, or a TOCTOU deletion race between the isfile check
    and the read) -- unhandled, this would crash the whole lint invocation,
    violating the documented 0/1/2-only exit-code contract. None of AC1-AC3/
    AC5-AC8's spec-mandated fixtures simulate a permission-denied read (AC2
    simulates a fully-MISSING file, a DIFFERENT code path, since
    `os.path.isfile()` already returns False there before any read is
    attempted).

    Mechanism: `os.chmod()` strips all permissions from an existing, valid
    cited file AFTER a genuine snapshot is captured, so `os.path.isfile()`
    still returns True (the file exists) but any actual `open()`/read raises
    `PermissionError` (an `OSError` subclass) -- confirmed directly against
    this exact test environment before relying on it (non-root user,
    `chmod 0o000` verified via a standalone probe to raise `PermissionError`
    on open, not silently succeed; this is an environment-dependent
    mechanism -- it would not exercise the gap if ever run as root).
    """

    def test_permission_denied_cited_file_flagged_same_as_missing_no_crash(self, tmp_path):
        gate_dir = tmp_path / "gate"
        evidence_file = tmp_path / "unreadable_evidence.txt"
        evidence_file.write_text("readable at capture time\n", encoding="utf-8")
        fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

        os.chmod(evidence_file, 0o000)
        try:
            heading = _closed_heading("H-PHASE2-OSERROR-1", _on_or_after_cutover(0))
            body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
            target = tmp_path / "fix_plan.md"
            _write(target, "%s\n%s" % (heading, body))

            code, out, err = _run([str(target)])
        finally:
            os.chmod(evidence_file, 0o644)  # restore so tmp_path cleanup succeeds

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "Traceback" not in err, (
            f"an OSError on the current-content hash-read must be CAUGHT and "
            f"flagged, not propagate and crash the lint invocation; "
            f"stderr={err!r}"
        )
        assert "STALE" in out
        assert "no longer exists" in out, (
            "spec: an OSError on the read is treated IDENTICALLY to the "
            "\"file no longer exists\" case, same STALE-shaped message"
        )


# =============================================================================
# Evidence-gate Phase 2b additive tests (spec: loop-team/runs/
# 2026-07-09_evidence-gate-phase2b-gitignore-visibility/specs/spec.md,
# ACs 1-8, plus one non-blocking nice-to-have the plan-check Verifier noted
# in this run's own plan_check_log.md round 1 -- see
# TestPhase2bNiceToHave... below).
#
# Everything below this banner is NEW and ADDITIVE -- nothing above it (v1's
# original tests, Phase 1's v2 additions, or Phase 2's v3 additions) has been
# modified. `fixplan_closure_lint.py` does not yet have the new gitignore-
# visibility check this spec describes (current shipped state is v3, commit
# `3804ec9`) -- every test below is EXPECTED TO FAIL (a real assertion
# failure -- e.g. "durability cannot be verified (gitignored)" never
# appearing in stdout because the check doesn't exist yet, so the empty
# `git status --porcelain` result is still silently treated as clean) until
# the Coder builds it. That is correct and expected, per
# roles/test_writer.md's own header ("Tier 1 -- spec-only, runs BEFORE
# implementation").
#
# All 8 spec ACs are tagged [BEHAVIORAL] in the spec text itself -- every one
# of them asserts on a REAL subprocess run's actual exit code / stdout
# against a REAL scratch git repo's REAL `.gitignore` state (confirmed by a
# direct standalone probe against this machine's real git, not assumed: an
# untracked, gitignored file's `git status --porcelain` is empty, rc=0;
# `git check-ignore --quiet` on it is rc=0; on a genuinely tracked file it is
# rc=1), never a keyword grep of an artifact's prose, so that classification
# is followed as-is throughout this section.
#
# [SECURITY-ORACLE] labeling (LOOP-M3, roles/test_writer.md): none of AC1-8
# is a cross-tenant/cross-actor isolation claim ("actor A cannot affect
# actor B") -- this whole spec is a single-actor evidence-integrity/honesty
# guarantee (a linter accurately reporting "I cannot verify this" instead of
# silently claiming "clean"), not an access-control boundary between two
# parties. AC6's sabotage-smoke-test IS adversarial in the general
# mutation-testing sense (proving the new check "has teeth"), matching this
# project's own established Phase 1 (AC9)/Phase 2 (AC13/AC14) sabotage
# convention, but is deliberately NOT tagged [SECURITY-ORACLE] since it does
# not fit LOOP-M3's specific definition. Flagged explicitly here as a
# classification judgment call, not silently decided either way.
#
# Naming convention: every class below is prefixed `TestPhase2b...`,
# DELIBERATELY disambiguated from both Phase 1's plain `TestAC<N>...` names
# and Phase 2's `TestPhase2AC<N>...` names above -- this spec reuses the
# SAME AC1-AC8 numeric range for a COMPLETELY DIFFERENT set of criteria
# (Phase 2's AC1 is "cited file modified after capture -> STALE"; Phase 2b's
# AC1 is "cited file gitignored -> durability-cannot-be-verified flag") --
# `Phase2b` is the disambiguator, matching how `Phase2` already disambiguated
# itself from Phase 1's plain names.
#
# Fixture-reuse decision (per this dispatch's own explicit instruction to
# reuse/extend Phase 2's established fixture builders rather than inventing
# new ones): AC3 and AC4 -- the two "unchanged from today" regression
# criteria -- reuse Phase 2's OWN `_ac6_clean_cited_file_fixture()` and
# `_ac5_dirty_cited_file_fixture()` verbatim, rather than building new
# near-duplicate fixtures, since those ACs are explicitly about confirming
# the ALREADY-ESTABLISHED clean/dirty cases are untouched by this addition.
# =============================================================================

# Pinned to the exact commit where fixplan_closure_lint.py is v3-COMPLETE
# (Phase 1 + Phase 2, freshness + dirty-worktree checks) but has NO Phase 2b
# code at all (no gitignore-visibility check) -- this is the spec's own
# cited "already shipped" baseline (commit `3804ec9`, confirmed via `git
# rev-parse 3804ec9` == this full SHA, and `git diff HEAD -- <this file's
# path>` == empty at the time this test suite was written, i.e. the on-disk
# v3 content IS what's committed at this SHA). Used by
# TestPhase2bAC6GitignoreVisibilityCheckSabotageSmokeTest below as the
# "stub the gitignore-visibility check off" sabotage target -- same design-
# decision caveat V1_BASELINE_COMMIT/PHASE2_BASELINE_COMMIT already carry
# (assumes the normal, additive-commit loop-team workflow; no history
# rewrite/rebase/squash of this commit).
PHASE2B_BASELINE_COMMIT = "3804ec9e3eb4c2b8526bff09479b080db7e40f43"


# ---------------------------------------------------------------------------
# Shared Phase 2b fixture/helper builders.
# ---------------------------------------------------------------------------

def _init_scratch_git_repo_with_gitignore(repo_dir, ignore_patterns):
    """Like `_init_scratch_git_repo()` above, but also writes and commits a
    `.gitignore` file (one pattern per line, matching the real fix_plan.md's
    own bare-basename convention -- no leading slash) BEFORE any other file
    is added, so any later-created path matching one of these patterns is
    GENUINELY gitignored from git's own perspective (confirmable via a real
    `git check-ignore` call), not merely left untracked -- the distinction
    this whole spec exists to make visible."""
    _init_scratch_git_repo(repo_dir)
    gitignore = repo_dir / ".gitignore"
    gitignore.write_text("\n".join(ignore_patterns) + "\n", encoding="utf-8")
    _git_add_commit(repo_dir, [gitignore], "add .gitignore")


def _phase2b_ac1_gitignored_cited_file_fixture(tmp_path):
    """Shared builder for AC1 (also reused by AC6's sabotage-smoke-test, per
    the spec's own explicit instruction: "stub it ... for AC1's fixture"): a
    cited file that IS gitignored (added to a scratch repo's `.gitignore`,
    committed; the cited file itself is created but NEVER `git add`ed), with
    a real, MATCHING (non-stale) snapshot -- isolating the new gitignore-
    visibility flag from both the freshness check and the existing dirty-
    worktree check. Returns (target_fix_plan_path, evidence_file_path)."""
    repo_dir = tmp_path / "phase2b_ac1_repo"
    _init_scratch_git_repo_with_gitignore(repo_dir, ["ignored_evidence.txt"])
    evidence_file = repo_dir / "ignored_evidence.txt"
    evidence_file.write_text("gitignored content, never committed\n", encoding="utf-8")

    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

    heading = _closed_heading("H-PHASE2B-AC1-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    target = tmp_path / "fix_plan.md"
    _write(target, "%s\n%s" % (heading, body))
    return target, evidence_file


def _phase2b_ac2_gitignored_target_file_fixture(tmp_path):
    """Shared builder for AC2: the file being LINTED is itself gitignored
    (added to its own scratch repo's `.gitignore`, committed; the target
    file itself is written but NEVER `git add`ed), with >=1 in-scope,
    Phase-1-passing CLOSED heading present (a no-op `-- true` Proof block
    citing no files, so the per-cited-file gitignore check has nothing to
    do -- isolates this fixture to the target-file-itself variant only).
    Returns the absolute path to the gitignored fix_plan.md inside the
    repo."""
    repo_dir = tmp_path / "phase2b_ac2_repo"
    _init_scratch_git_repo_with_gitignore(repo_dir, ["fix_plan.md"])
    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["true"])
    heading = _closed_heading("H-PHASE2B-AC2-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    target = repo_dir / "fix_plan.md"
    _write(target, "%s\n%s" % (heading, body))
    return target


def _phase2b_ac5_gitignored_and_stale_fixture(tmp_path):
    """Shared builder for AC5: a cited file that is BOTH gitignored (per
    `_phase2b_ac1_gitignored_cited_file_fixture`'s own mechanism) AND
    genuinely gone stale (content changed on disk AFTER the snapshot was
    captured, exactly like Phase 2's own `_ac1_modified_file_fixture`) --
    confirms the freshness check and this new gitignore-visibility check
    remain fully independent and additive. Returns
    (target_fix_plan_path, evidence_file_path)."""
    repo_dir = tmp_path / "phase2b_ac5_repo"
    _init_scratch_git_repo_with_gitignore(repo_dir, ["ignored_evidence.txt"])
    evidence_file = repo_dir / "ignored_evidence.txt"
    evidence_file.write_text("original content, before snapshot\n", encoding="utf-8")

    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])
    evidence_file.write_text("MODIFIED after the snapshot was captured, genuinely stale\n", encoding="utf-8")

    heading = _closed_heading("H-PHASE2B-AC5-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    target = tmp_path / "fix_plan.md"
    _write(target, "%s\n%s" % (heading, body))
    return target, evidence_file


def _phase2b_baseline_blob_bytes():
    r = subprocess.run(
        ["git", "-C", REPO_ROOT, "show", "%s:%s" % (PHASE2B_BASELINE_COMMIT, LINT_REL_PATH)],
        capture_output=True, timeout=30,
    )
    assert r.returncode == 0, (
        "could not read fixplan_closure_lint.py at the pinned Phase-2b "
        "baseline commit %s -- see PHASE2B_BASELINE_COMMIT's own comment; "
        "git stderr: %r" % (PHASE2B_BASELINE_COMMIT, r.stderr)
    )
    return r.stdout


def _sabotage_with_phase2b_baseline_and_restore(run_args, cwd=None):
    """Shared mechanism for AC6: capture the live fixplan_closure_lint.py's
    bytes, overwrite it with the pinned Phase-2b-baseline (v3-only, no
    gitignore-visibility check at all -- functionally identical to "stub the
    check to always return clean", since with the check entirely absent, an
    empty `git status --porcelain` result falls straight through to
    "clean", exactly as it did before this spec) blob, re-run the given
    fixture, restore the original bytes (even on failure), then assert
    byte-for-byte restoration. Matches Phase 1's `TestAC9SabotageSmokeTests`
    / Phase 2's `_sabotage_with_phase2_baseline_and_restore` mechanism
    exactly (byte-capture-before-mutation, byte-compare-after-restore --
    NOT `git diff --stat`), applied to the Phase-2b-appropriate pinned
    baseline. Returns (code, out, err) from the SABOTAGED run."""
    script_path = os.path.join(HERE, "fixplan_closure_lint.py")
    original_bytes = Path(script_path).read_bytes()
    try:
        Path(script_path).write_bytes(_phase2b_baseline_blob_bytes())
        if cwd is not None:
            result = _run_from_cwd(run_args, cwd)
        else:
            result = _run(run_args)
    finally:
        Path(script_path).write_bytes(original_bytes)

    restored_bytes = Path(script_path).read_bytes()
    assert restored_bytes == original_bytes, (
        "fixplan_closure_lint.py was not byte-for-byte restored after the "
        "Phase-2b sabotage mutation"
    )
    return result


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL]: cited file IS gitignored -> "durability cannot be
# verified (gitignored)", NOT "evidence file has uncommitted changes".
# ---------------------------------------------------------------------------

class TestPhase2bAC1GitignoredCitedFileFlagged:
    def test_gitignored_cited_file_flagged_durability_not_dirty(self, tmp_path):
        target, evidence_file = _phase2b_ac1_gitignored_cited_file_fixture(tmp_path)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "durability cannot be verified (gitignored)" in out
        assert str(evidence_file) in out
        assert "evidence file has uncommitted changes" not in out, (
            "an absence-of-signal (gitignored, empty git status) must never "
            "be misreported as the existing dirty-worktree flag -- that "
            "would be a false, misleading claim per the spec"
        )


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL]: the TARGET file itself IS gitignored, with >=1 in-scope
# Phase-1-passing CLOSED heading present -> flagged, referencing the target
# file, containing "(the file being linted)".
# ---------------------------------------------------------------------------

class TestPhase2bAC2TargetFileItselfGitignoredFlagged:
    def test_gitignored_target_file_with_in_scope_heading_flagged(self, tmp_path):
        target = _phase2b_ac2_gitignored_target_file_fixture(tmp_path)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "durability cannot be verified (gitignored)" in out
        assert "(the file being linted)" in out
        assert str(target) in out
        assert "evidence file has uncommitted changes" not in out


# ---------------------------------------------------------------------------
# AC3 [BEHAVIORAL]: a cited file that is genuinely tracked-and-clean (NOT
# gitignored) -> unchanged from today: no dirty flag, no new gitignored
# flag. Reuses Phase 2's OWN `_ac6_clean_cited_file_fixture()` verbatim --
# this AC is explicitly about confirming the ALREADY-WORKING case is
# untouched, not about exercising new fixture-building logic.
# ---------------------------------------------------------------------------

class TestPhase2bAC3TrackedCleanCitedFileUnchanged:
    def test_tracked_clean_cited_file_no_dirty_no_gitignored_flag(self, tmp_path):
        target, evidence_file = _ac6_clean_cited_file_fixture(tmp_path)

        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" not in out
        assert "durability cannot be verified (gitignored)" not in out


# ---------------------------------------------------------------------------
# AC4 [BEHAVIORAL]: a cited file that is genuinely tracked-and-DIRTY (NOT
# gitignored) -> unchanged from today: the existing dirty flag fires, NOT
# the new gitignored flag. Reuses Phase 2's OWN
# `_ac5_dirty_cited_file_fixture()` verbatim (same reuse rationale as AC3).
# ---------------------------------------------------------------------------

class TestPhase2bAC4TrackedDirtyCitedFileUnchanged:
    def test_tracked_dirty_cited_file_still_flagged_dirty_not_gitignored(self, tmp_path):
        target, evidence_file = _ac5_dirty_cited_file_fixture(tmp_path, stage_change=False)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" in out
        assert str(evidence_file) in out
        assert "durability cannot be verified (gitignored)" not in out, (
            "the two outcomes must be mutually exclusive -- a genuinely "
            "dirty, non-ignored file must never ALSO get the gitignored flag"
        )


# ---------------------------------------------------------------------------
# AC5 [BEHAVIORAL]: a cited file that is BOTH gitignored AND has genuinely
# gone stale -> gets BOTH "STALE" (freshness check) AND "durability cannot
# be verified (gitignored)" (this new check) in the SAME run -- neither
# suppresses the other.
# ---------------------------------------------------------------------------

class TestPhase2bAC5GitignoredAndStaleBothFlagged:
    def test_gitignored_and_stale_cited_file_gets_both_flags(self, tmp_path):
        target, evidence_file = _phase2b_ac5_gitignored_and_stale_fixture(tmp_path)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "STALE" in out
        assert "changed since" in out
        assert "durability cannot be verified (gitignored)" in out
        assert str(evidence_file) in out


# ---------------------------------------------------------------------------
# AC6 [BEHAVIORAL]: sabotage-smoke-test proving the new gitignore-visibility
# check has teeth -- matching this project's established mechanism (byte-
# capture-before-mutation, byte-compare-after-restore, NOT `git diff
# --stat`).
# ---------------------------------------------------------------------------

class TestPhase2bAC6GitignoreVisibilityCheckSabotageSmokeTest:
    """Reuses the exact byte-capture-before-mutation / byte-compare-after-
    restore mechanism Phase 1's `TestAC9SabotageSmokeTests` established (NOT
    `git diff --stat`), pinned to PHASE2B_BASELINE_COMMIT -- the last commit
    before ANY Phase 2b code exists (see that constant's own comment).
    Stubs the check by removing it ENTIRELY (reverting the whole file to the
    pinned pre-Phase-2b blob) rather than patching one named function --
    same sequencing-constraint rationale Phase 1/Phase 2's own sabotage
    classes already documented (no implementation exists yet at Test-writer
    time to target a surgical patch against). This is a valid proxy for
    "stub it to always return clean instead of gitignored" specifically
    (not merely "delete the check and hope"): with the check absent, an
    EMPTY `git status --porcelain` result falls straight through to
    "clean" -- the exact behavior AC1's fixture is built to distinguish
    from "gitignored, so git gave no real signal".

    Proxy validity: AC1's own fixture (reused verbatim) is built so the
    freshness check and the existing dirty-worktree check both stay clean
    on it (confirmed below, in the unstubbed run, before sabotaging) -- so
    stubbing the gitignore-visibility check specifically is what flips this
    fixture's result, not some other check.
    """

    def test_ac6_gitignore_visibility_check_has_teeth(self, tmp_path):
        target, evidence_file = _phase2b_ac1_gitignored_cited_file_fixture(tmp_path)

        # --- unstubbed: the real (Phase 2b) check must catch this ---
        code, out, err = _run([str(target)])
        assert code == 1, f"unstubbed run should be flagged; stdout={out!r} stderr={err!r}"
        assert "durability cannot be verified (gitignored)" in out
        assert "evidence file has uncommitted changes" not in out  # proxy-validity precondition
        assert "STALE" not in out  # proxy-validity precondition

        # --- sabotage: confirm it WRONGLY now shows no flag at all ---
        code2, out2, err2 = _sabotage_with_phase2b_baseline_and_restore([str(target)])
        assert code2 == 0, (
            "expected the sabotaged (pre-Phase-2b, no gitignore-visibility "
            f"check) run to WRONGLY pass cleanly; stdout={out2!r} stderr={err2!r}"
        )
        assert "durability cannot be verified (gitignored)" not in out2


# ---------------------------------------------------------------------------
# AC7 [BEHAVIORAL]: real-file regression -- running the lint against the
# frozen Phase 1 fixture, path passed EXPLICITLY (matching the established
# AC10/AC12 pattern -- NOT "no args"), still shows zero NEW (gitignore-
# visibility) flags of any kind.
# ---------------------------------------------------------------------------

class TestPhase2bAC7FrozenFixtureExplicitPathShowsZeroNewGitignoreFlags:
    FROZEN_FIXTURE = os.path.join(HERE, "testdata", "frozen_fix_plan_evidence_gate_phase1.md")

    def test_frozen_fixture_scoping_precondition_is_zero_in_scope_headings(self):
        """Same precondition Phase 2's own `TestPhase2AC12...` already
        established (re-confirmed independently here, not merely assumed):
        the frozen fixture has ZERO in-scope (CLOSED, dated on/after
        PROOF_REQUIRED_SINCE) headings, so NEITHER the target-file-itself
        check NOR any per-cited-file check (which both require an in-scope,
        Phase-1-passing heading to run at all) can fire regardless of the
        frozen fixture's own real on-disk gitignore status -- this AC is
        trivially, structurally true, exactly like AC12's own equivalent."""
        with open(self.FROZEN_FIXTURE, encoding="utf-8") as f:
            content = f.read()
        in_scope_headings = [
            heading_line for heading_line, _body in lint._iter_blocks(content)
            if lint._proof_required_for_heading(heading_line)
        ]
        assert in_scope_headings == [], (
            "expected the frozen fixture to have ZERO in-scope headings -- "
            "if this now fails, this AC needs re-reading with real in-scope "
            "Proof blocks in mind: %r" % in_scope_headings
        )

    def test_frozen_fixture_explicit_path_no_new_gitignore_flags(self):
        assert os.path.isfile(self.FROZEN_FIXTURE), (
            "expected the frozen fix_plan.md fixture at %s" % self.FROZEN_FIXTURE
        )
        code, out, err = _run([self.FROZEN_FIXTURE])

        assert code in (0, 1), f"unexpected crash; stdout={out!r} stderr={err!r}"
        assert "durability cannot be verified (gitignored)" not in out, (
            "the frozen (real, historical) fix_plan.md snapshot must show "
            "ZERO new gitignore-visibility flags -- see the scoping-"
            "precondition test above for why this is expected to be "
            "trivially true"
        )


# ---------------------------------------------------------------------------
# AC8 [BEHAVIORAL]: 100% of Phase 1 + Phase 2's existing 66 tests still pass
# UNMODIFIED. No dedicated test class here BY DESIGN, matching Phase 2's own
# AC11 precedent (see that AC's own banner note above): this is not a new
# assertion to encode, it is a promise about NOT touching anything above
# this banner -- structurally guaranteed by every edit in this dispatch
# being purely additive (confirmed by direct re-diff before finalizing) and
# mechanically checked by running this file's full existing test suite
# standalone post-write (see this dispatch's own report for that run's real
# output).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Nice-to-have (non-blocking, noted by the plan-check Verifier in this run's
# own plan_check_log.md round 1): the target-file-gitignored case is
# correctly SKIPPED when zero in-scope headings exist -- mirroring Phase 2's
# own `TestPhase2AC8TargetFileDirtinessSkippedWhenNothingToProtect`, applied
# to the NEW gitignored-target-file flag instead of the existing dirty flag.
# Confirms the new check reuses the SAME `any_in_scope_passing_heading` gate
# the existing target-file dirty check already uses (per the plan-check
# log's own "confirmed complete and consistent across both call sites"
# finding), not a separately-computed (and possibly inconsistent) condition.
# ---------------------------------------------------------------------------

class TestPhase2bNiceToHaveTargetFileGitignoredSkippedWhenNothingToProtect:
    def test_no_closed_headings_at_all_gitignored_target_not_flagged(self, tmp_path):
        repo_dir = tmp_path / "phase2b_nth_a_repo"
        _init_scratch_git_repo_with_gitignore(repo_dir, ["fix_plan.md"])
        target = repo_dir / "fix_plan.md"
        _write(target, (
            "## H-PHASE2B-NTH-OPEN-1 (OPEN, filed for this test)\n"
            "Still being worked, no closure claimed.\n"
        ))

        code, out, err = _run([str(target)])
        assert "durability cannot be verified (gitignored)" not in out, (
            f"target-file gitignored-visibility check must be skipped with "
            f"zero CLOSED headings in the file; stdout={out!r} stderr={err!r}"
        )

    def test_closed_heading_present_but_phase1_failing_gitignored_target_not_flagged(self, tmp_path):
        repo_dir = tmp_path / "phase2b_nth_b_repo"
        _init_scratch_git_repo_with_gitignore(repo_dir, ["fix_plan.md"])
        heading = _closed_heading("H-PHASE2B-NTH-FAIL-1", _on_or_after_cutover(0))
        target = repo_dir / "fix_plan.md"
        # Deliberately NO Proof block at all -- fails Phase 1's own
        # proof-block-required check, so this heading does not count as
        # "Phase-1-passing" even though it IS a CLOSED, in-scope heading.
        _write(target, "%s\nClosure prose, but no Proof block at all.\n" % heading)

        code, out, err = _run([str(target)])
        assert "missing proof block" in out  # sanity: Phase 1 does flag this heading
        assert "durability cannot be verified (gitignored)" not in out, (
            f"target-file gitignored-visibility check must be skipped when "
            f"the only CLOSED heading present FAILED Phase 1's own check; "
            f"stdout={out!r} stderr={err!r}"
        )


# =============================================================================
# Evidence-Gate Phase 3 additive tests (spec: loop-team/runs/
# 2026-07-09_evidence-gate-phase3/specs/spec.md, ACs 1-11, "--selftest").
#
# Everything below this banner is NEW and ADDITIVE -- nothing above it has
# been modified. `fixplan_closure_lint.py` has NOT been touched for this
# phase yet (no --selftest flag, no _run_selftest(), no
# _append_selftest_heartbeat(), no _today_iso()) -- these tests are EXPECTED
# to fail (AttributeError on `lint._run_selftest`, or a plain assertion
# failure on exit code / stdout content, since today `--selftest` is silently
# treated as a literal file-path argument by the EXISTING path-mode branch of
# main()) until the Coder builds Phase 3. That is correct and expected, per
# roles/test_writer.md's own header ("Tier 1 -- spec-only, runs BEFORE
# implementation").
#
# ONE explicit exception to "should currently fail": AC7 below is a
# regression guard over ALREADY-SHIPPED, unmodified behavior (find_mismatches,
# find_proof_flags, find_freshness_and_dirty_flags, and main()'s existing
# no-args/single-path branches) -- it does not touch --selftest at all, so it
# is expected to ALREADY PASS today, and must keep passing after the Coder's
# change lands. That is the whole point of a regression guard, not a
# weakening of it.
#
# Per the spec's own explicit instruction, AC8 and AC9 are pytest
# `monkeypatch`-based IN-PROCESS tests (call `lint._run_selftest()` directly,
# not via subprocess) -- the first uses of `monkeypatch` in this file (a
# full-text grep for `monkeypatch` above this banner returns zero matches);
# this differs deliberately from the whole-file git-blob sabotage-smoke-test
# mechanism (`TestAC9SabotageSmokeTests` et al.) used elsewhere in this file,
# because AC8/AC9 sabotage an in-memory IMPORTED DEPENDENCY
# (`run_and_record.run_and_record` / `run_and_record._render_proof_block`),
# not the script file under test itself -- there is no on-disk file to
# swap/restore for these two. All other ACs (1-7, 10) are subprocess-invoked
# CLI tests, matching this file's primary established convention.
#
# AC11 ("full existing suite green") has NO dedicated test class here, by
# design, matching this file's own established precedent for the identical
# situation (see "AC11" / "AC8 [DOC/BEHAVIORAL]" banners above, Phase 1 and
# Phase 2's own "100% of existing tests still pass" ACs): a self-referential
# pytest-invokes-pytest test would recursively re-collect and re-run itself
# inside the child process (this exact test file), which is a genuine
# unbounded-recursion hazard, not merely inconvenient -- so, consistent with
# this file's own prior decisions, AC11 is satisfied by directly running
# `python3 -m pytest loop-team/harness/test_fixplan_closure_lint.py
# loop-team/harness/test_run_and_record.py -q` as a manual verification step
# once the Coder's implementation lands, not by an automated test embedded in
# the suite it would need to reinvoke.
# =============================================================================

import run_and_record as rar  # noqa: E402 -- the whole module, matching the
# spec's own "Import the whole module, not individual names" instruction for
# fixplan_closure_lint.py's own new import; safe to import directly here
# since HERE is already on sys.path (see the top of this file) and this
# module is NOT being modified by this phase, only imported/monkeypatched.


def _run_with_env(args, env, timeout=30):
    """Same as the shared `_run()` helper above, but with a caller-supplied
    `env` dict (used ONLY by AC3's heartbeat-log test, per the spec's own
    explicit carve-out: "the one place a test MAY isolate the gate dir" via
    a `LOOP_GATE_DIR` override, to keep line-count comparisons hermetic)."""
    p = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout, env=env,
    )
    return p.returncode, p.stdout, p.stderr


def _read_lines_or_empty(path):
    """Read `path` as a list of lines, or return [] if it does not exist yet
    (the heartbeat log may not exist at all before the first --selftest
    invocation in a fresh gate dir)."""
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.readlines()


def _find_true_noop_snapshot_path(proof_dir):
    """Scan `proof_dir` for the one JSON snapshot file (if any) whose
    recorded fields match the canonical `true` no-op command with zero
    auto-detected files and a fixed-False (not merely null/"not applicable")
    worktree-dirtiness value: command == ["true"], files == {},
    dirty_at_capture is False -- the exact record `_run_selftest()`'s GOOD
    fixture must produce via `run_and_record.run_and_record(["true"])` (per
    AC4/AC6). Returns the file's absolute path, or None if no such file
    currently exists. `_key_for_record()`'s content-addressing makes this key
    fully deterministic (spec AC4's own text), so there is at most one
    matching file at any given time -- this helper does not assume that on
    the caller's behalf, though; see AC4's own test for the explicit
    at-most-one assertion."""
    if not os.path.isdir(proof_dir):
        return None
    matches = []
    for name in os.listdir(proof_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(proof_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                record = json.load(f)
        except (OSError, ValueError):
            continue
        if (
            record.get("command") == ["true"]
            and record.get("files") == {}
            and record.get("dirty_at_capture") is False
        ):
            matches.append(path)
    assert len(matches) <= 1, (
        "found more than one snapshot matching the deterministic "
        "true/no-files/clean key -- this should be impossible given "
        "_key_for_record()'s content-addressing: %r" % matches
    )
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL]: `--selftest` run as a real subprocess from a clean,
# unmodified checkout exits 0.
# ---------------------------------------------------------------------------

class TestPhase3AC1SelftestExitsZeroOnCleanCheckout:
    def test_selftest_exits_zero(self):
        code, out, err = _run(["--selftest"])
        assert code == 0, f"stdout={out!r} stderr={err!r}"


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL]: stdout contains the literal substring "--selftest PASS",
# plus both expected-outcome lines (good fixture 0 flags; bad fixture
# flagged with "no matching proof snapshot found") -- per the spec's own
# Step D literal print text.
# ---------------------------------------------------------------------------

class TestPhase3AC2SelftestStdoutReportsPassAndBothOutcomeLines:
    def test_selftest_stdout_reports_pass_and_both_fixture_outcomes(self):
        code, out, err = _run(["--selftest"])
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        assert "--selftest PASS" in out
        assert "good fixture: 0 flags (as expected)" in out
        assert (
            'bad fixture: flagged with "no matching proof snapshot found" '
            "(as expected)"
        ) in out


# ---------------------------------------------------------------------------
# AC3 [BEHAVIORAL]: <gate_dir>/closure_lint_selftest.log gains exactly one
# new line per invocation; the new line starts with a parseable ISO-8601
# timestamp and contains "SELFTEST PASS". `LOOP_GATE_DIR` is overridden to a
# tmp_path for THIS test only, per the spec's own explicit carve-out.
# ---------------------------------------------------------------------------

class TestPhase3AC3HeartbeatLogGrowsByExactlyOneLinePerInvocation:
    def test_selftest_log_gains_exactly_one_line_per_invocation(self, tmp_path):
        gate_dir = tmp_path / "gate"
        env = dict(os.environ)
        env["LOOP_GATE_DIR"] = str(gate_dir)
        log_path = gate_dir / "closure_lint_selftest.log"

        # First invocation establishes the "before" state for the SECOND
        # invocation's own before/after comparison (per AC3's own wording:
        # "compare line count before/after" -- a single invocation from an
        # empty/nonexistent log would not distinguish "appends" from
        # "always (re)writes exactly one line", so two invocations are used.
        code1, out1, err1 = _run_with_env(["--selftest"], env)
        assert code1 == 0, f"stdout={out1!r} stderr={err1!r}"
        assert log_path.is_file(), (
            f"expected the heartbeat log to exist at {log_path} after a "
            f"--selftest run; stdout={out1!r} stderr={err1!r}"
        )
        before_lines = _read_lines_or_empty(str(log_path))
        before_count = len(before_lines)

        code2, out2, err2 = _run_with_env(["--selftest"], env)
        assert code2 == 0, f"stdout={out2!r} stderr={err2!r}"
        after_lines = _read_lines_or_empty(str(log_path))
        after_count = len(after_lines)

        assert after_count - before_count == 1, (
            f"expected exactly one new heartbeat line per invocation; "
            f"before={before_count} after={after_count} "
            f"before_lines={before_lines!r} after_lines={after_lines!r}"
        )

        new_line = after_lines[-1]
        assert "SELFTEST PASS" in new_line
        timestamp_token = new_line.split(" ", 1)[0]
        datetime.fromisoformat(timestamp_token)  # raises ValueError if unparseable


# ---------------------------------------------------------------------------
# AC4 [BEHAVIORAL]: after a --selftest run, the real `true`/no-files/clean
# snapshot file under <gate_dir>/proof/ is (a) self-consistent with
# `_key_for_record()` computed from its OWN loaded fields, and (b) freshly
# captured within a wall-clock window bracketing this test's own invocation.
# Deliberately uses the REAL gate dir (no LOOP_GATE_DIR override) -- per the
# spec's Non-goals section, only AC3 above isolates the gate dir.
# ---------------------------------------------------------------------------

class TestPhase3AC4GoodFixtureSnapshotSelfConsistentAndFreshlyCaptured:
    def test_good_fixture_snapshot_matches_its_own_key_and_is_freshly_captured(self):
        before = datetime.now(timezone.utc)
        code, out, err = _run(["--selftest"])
        after = datetime.now(timezone.utc)
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        proof_dir = rar._proof_dir()
        snapshot_path = _find_true_noop_snapshot_path(proof_dir)
        assert snapshot_path is not None, (
            "expected to find a run_and_record snapshot for the canonical "
            "`true` no-op command (command==['true'], files=={}, "
            "dirty_at_capture==False) under %s after a --selftest run" % proof_dir
        )

        with open(snapshot_path, encoding="utf-8") as f:
            record = json.load(f)

        # (a) self-consistency: the file's own name is exactly the key
        # `_key_for_record()` computes from the ACTUAL fields read back out
        # of the file -- not a hand-constructed partial record.
        expected_name = rar._key_for_record(record) + ".json"
        assert expected_name == os.path.basename(snapshot_path), (
            f"snapshot filename {os.path.basename(snapshot_path)!r} does not "
            f"match the key computed from its own loaded record "
            f"({expected_name!r}) -- record={record!r}"
        )

        # (b) freshness: this exact snapshot was captured by THIS invocation,
        # not a stale pre-existing one from unrelated routine use of
        # `run_and_record.py -- true` elsewhere in this project.
        captured_at = datetime.fromisoformat(record["captured_at"])
        assert before <= captured_at <= after, (
            f"expected captured_at={captured_at!r} to fall within the wall-"
            f"clock window [{before!r}, {after!r}] bracketing this test's "
            f"own --selftest invocation -- a value outside this window means "
            f"the found snapshot is a stale pre-existing file, not proof "
            f"this invocation actually ran the good fixture's command"
        )


# ---------------------------------------------------------------------------
# AC5 [BEHAVIORAL]: after a --selftest run,
# SELFTEST-FABRICATED-DO-NOT-CREATE.json does NOT exist under
# <gate_dir>/proof/ -- the bad fixture's fabricated proof_snapshot path must
# never actually get created by --selftest itself. Real gate dir (no
# override), same rationale as AC4.
# ---------------------------------------------------------------------------

class TestPhase3AC5FabricatedSentinelSnapshotNeverCreated:
    def test_fabricated_sentinel_snapshot_file_never_created(self):
        code, out, err = _run(["--selftest"])
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        sentinel = os.path.join(
            rar._proof_dir(), "SELFTEST-FABRICATED-DO-NOT-CREATE.json"
        )
        assert not os.path.isfile(sentinel), (
            f"--selftest must never create a real file at its own bad "
            f"fixture's fabricated (guaranteed-nonexistent) proof_snapshot "
            f"path, but found one at {sentinel}"
        )


# ---------------------------------------------------------------------------
# AC6 [BEHAVIORAL]: `--selftest` present but not the SOLE argument exits 2,
# does NOT touch the heartbeat log, and does NOT create the true-command
# snapshot file if it didn't already exist. Real gate dir (no override), per
# the spec's own "AC3 is the ONE place a test MAY isolate the gate dir" note
# -- and because this AC is specifically about NOTHING changing, the real
# dir is the more meaningful thing to check against.
# ---------------------------------------------------------------------------

class TestPhase3AC6MalformedSelftestInvocationExitsTwoNoSideEffects:
    def _assert_malformed_invocation_has_no_side_effects(self, args):
        gate_dir = rar._gate_dir()
        log_path = os.path.join(gate_dir, "closure_lint_selftest.log")
        proof_dir = rar._proof_dir()

        before_log_lines = _read_lines_or_empty(log_path)
        pre_existing_snapshot = _find_true_noop_snapshot_path(proof_dir)

        code, out, err = _run(args)

        assert code == 2, f"args={args!r} stdout={out!r} stderr={err!r}"
        # A malformed --selftest invocation must produce ITS OWN,
        # selftest-specific usage message (spec: "a SEPARATE,
        # selftest-specific usage line -- do not reuse the path-mode usage
        # string"), not the pre-existing generic path-mode usage text (which
        # never mentions "--selftest" at all) -- this is the concrete
        # discriminator between the new selftest-aware branch and the old
        # generic multi-arg usage check, both of which happen to exit 2.
        assert "--selftest" in err, (
            f"expected a selftest-specific usage message mentioning "
            f"'--selftest' on stderr for args={args!r}; got stderr={err!r}"
        )
        assert "usage" in err.lower()

        after_log_lines = _read_lines_or_empty(log_path)
        assert after_log_lines == before_log_lines, (
            f"a malformed --selftest invocation must never touch the "
            f"heartbeat log; before={before_log_lines!r} "
            f"after={after_log_lines!r}"
        )

        post_snapshot = _find_true_noop_snapshot_path(proof_dir)
        if pre_existing_snapshot is None:
            assert post_snapshot is None, (
                "a malformed --selftest invocation must never create the "
                "true/no-files/clean snapshot file if it did not already "
                "exist"
            )
        else:
            assert post_snapshot == pre_existing_snapshot

    def test_selftest_with_extra_positional_arg_exits_2_no_side_effects(self):
        self._assert_malformed_invocation_has_no_side_effects(["--selftest", "somepath"])

    def test_selftest_doubled_flag_exits_2_no_side_effects(self):
        self._assert_malformed_invocation_has_no_side_effects(["--selftest", "--selftest"])


# ---------------------------------------------------------------------------
# AC7 [BEHAVIORAL]: regression guard -- no-args and single-path invocations
# behave IDENTICALLY to pre-Phase-3 behavior across every existing
# check-flag class: (a) no mismatches, (b) v1 mismatch, (c) v2
# snapshot-cross-check-fail, (d) v3 freshness (STALE), (e) v3/v3b
# dirty-worktree, (f) the real, live fix_plan.md. NOTE: unlike every other
# class in this Phase-3 section, these tests do NOT touch --selftest at all
# and are EXPECTED TO ALREADY PASS today (see this section's own banner) --
# that is the correct, intended state for a regression guard.
# ---------------------------------------------------------------------------

class TestPhase3AC7RegressionGuardNonSelftestInvocationsUnchanged:
    def test_a_fixture_with_no_mismatches_exits_zero(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, (
            "## H-PHASE3-AC7A-1 -- some real fix -- CLOSED (2026-07-03, commit `abcdef1`)\n"
            "Full loop closed: spec, plan-check, Test-writer, Verifier. "
            "PLAN_PASS achieved and independently re-verified.\n\n"
            "## H-PHASE3-AC7A-2 (OPEN, filed 2026-07-03) -- still being worked\n"
            "Diagnosis in progress. No fix built yet, nothing to claim.\n"
        ))
        code, out, err = _run([str(target)])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "no mismatches found" in out

    def test_b_fixture_with_v1_mismatch_exits_one(self, tmp_path):
        target = tmp_path / "fix_plan.md"
        _write(target, (
            "## H-PHASE3-AC7B-1 (OPEN, filed 2026-07-03, medium priority)\n"
            "IMPLEMENTATION COMPLETE: full closure shipped, PLAN_PASS achieved.\n"
        ))
        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "1 mismatch" in out
        assert "H-PHASE3-AC7B-1" in out

    def test_c_fixture_with_v2_snapshot_cross_check_fail_exits_one(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "phase3-ac7c-real-evidence"])
        heading = _closed_heading("H-PHASE3-AC7C-1", _on_or_after_cutover(0))
        body = _proof_block(
            "echo a-totally-different-command", fields["exit_code"], fields["proof_snapshot"]
        )
        target = tmp_path / "fix_plan.md"
        _write(target, "%s\n%s" % (heading, body))

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "no matching proof snapshot found" in out

    def test_d_fixture_with_v3_freshness_stale_flag_exits_one(self, tmp_path):
        target, evidence_file = _ac1_modified_file_fixture(tmp_path)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "STALE" in out
        assert str(evidence_file) in out

    def test_e_fixture_with_v3_v3b_dirty_worktree_flag_exits_one(self, tmp_path):
        target, evidence_file = _ac5_dirty_cited_file_fixture(tmp_path, stage_change=False)

        code, out, err = _run([str(target)])
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "evidence file has uncommitted changes" in out
        assert str(evidence_file) in out

    def test_f_real_live_fix_plan_md_never_crashes(self):
        repo_root = os.path.normpath(os.path.join(HERE, "..", ".."))
        real_fix_plan = os.path.join(repo_root, "fix_plan.md")
        assert os.path.isfile(real_fix_plan), (
            "expected the real fix_plan.md at %s" % real_fix_plan
        )

        code, out, err = _run([real_fix_plan])
        assert code in (0, 1), f"unexpected exit code {code}; stdout={out!r} stderr={err!r}"
        assert err == "", f"expected no stderr on a normal run, got: {err!r}"

    def test_no_args_and_explicit_default_path_produce_identical_output(self):
        default_path = os.path.normpath(os.path.join(HERE, "..", "..", "fix_plan.md"))
        assert os.path.isfile(default_path), (
            "expected the real fix_plan.md at the computed default path %s" % default_path
        )

        code_noargs, out_noargs, err_noargs = _run([])
        code_explicit, out_explicit, err_explicit = _run([default_path])

        assert code_noargs == code_explicit
        assert out_noargs == out_explicit
        assert err_noargs == err_explicit


# ---------------------------------------------------------------------------
# AC8 [BEHAVIORAL]: a forced harness fault -- monkeypatch
# `run_and_record.run_and_record` to a stub returning (2, None, None) for any
# input, call `_run_selftest()` directly in-process -- returns 2, and the
# heartbeat log gains one new line containing "SELFTEST ERROR". Uses
# `monkeypatch` (auto-teardown) per the spec's explicit instruction; no
# `git diff --stat` residual-change check -- nothing on disk is mutated by
# `monkeypatch.setattr` itself (see this section's own banner note).
# ---------------------------------------------------------------------------

class TestPhase3AC8ForcedHarnessFaultReturnsErrorAndHeartbeats:
    def test_run_and_record_returning_none_record_yields_error_exit_and_heartbeat(
        self, tmp_path, monkeypatch
    ):
        gate_dir = tmp_path / "gate"
        monkeypatch.setenv("LOOP_GATE_DIR", str(gate_dir))

        def _stub_run_and_record(command):
            return 2, None, None

        monkeypatch.setattr(rar, "run_and_record", _stub_run_and_record)

        result = lint._run_selftest()

        assert result == 2, "a harness fault (record is None) must return 2"

        log_path = gate_dir / "closure_lint_selftest.log"
        assert log_path.is_file(), (
            "expected the heartbeat log to exist after a forced harness "
            "fault -- the ERROR path must still call "
            "_append_selftest_heartbeat()"
        )
        lines = _read_lines_or_empty(str(log_path))
        assert len(lines) == 1, f"expected exactly one heartbeat line, got {lines!r}"
        assert "SELFTEST ERROR" in lines[0]


# ---------------------------------------------------------------------------
# AC9 [BEHAVIORAL]: a forced unanticipated exception -- monkeypatch
# `run_and_record._render_proof_block` to raise a plain Exception("boom")
# inside the good-fixture-construction path -- `_run_selftest()` still
# returns 2 (no uncaught traceback escapes the function) and the heartbeat
# log gains one new line containing both "SELFTEST ERROR" and "boom".
# ---------------------------------------------------------------------------

class TestPhase3AC9UnanticipatedExceptionCaughtReturnsErrorAndHeartbeats:
    def test_render_proof_block_raising_yields_error_exit_and_heartbeat_with_message(
        self, tmp_path, monkeypatch
    ):
        gate_dir = tmp_path / "gate"
        monkeypatch.setenv("LOOP_GATE_DIR", str(gate_dir))

        def _boom(record, snapshot_path):
            raise Exception("boom")

        monkeypatch.setattr(rar, "_render_proof_block", _boom)

        result = lint._run_selftest()

        assert result == 2, (
            "an unanticipated exception during fixture construction must "
            "still return 2, never propagate out of _run_selftest()"
        )

        log_path = gate_dir / "closure_lint_selftest.log"
        assert log_path.is_file(), (
            "expected the heartbeat log to exist after an unanticipated "
            "exception -- the outer except branch must still call "
            "_append_selftest_heartbeat()"
        )
        lines = _read_lines_or_empty(str(log_path))
        assert len(lines) == 1, f"expected exactly one heartbeat line, got {lines!r}"
        assert "SELFTEST ERROR" in lines[0]
        assert "boom" in lines[0]


# ---------------------------------------------------------------------------
# AC10 [DOC]: the module docstring gains a new "=== v4 additions
# (evidence-gate Phase 3...) ===" section, and the "Usage:" / "Exit codes:"
# sections are updated to mention --selftest.
# ---------------------------------------------------------------------------

class TestPhase3AC10DocstringDocumentsV4SelftestAdditions:
    def test_module_docstring_has_v4_additions_section(self):
        with open(SCRIPT, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc, "expected fixplan_closure_lint.py to have a module docstring"

        assert "=== v4 additions" in module_doc, (
            "expected a new '=== v4 additions (evidence-gate Phase 3...) ===' "
            "docstring section"
        )
        assert "evidence-gate Phase 3" in module_doc
        assert "--selftest" in module_doc

    def test_usage_section_mentions_selftest(self):
        with open(SCRIPT, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc

        usage_idx = module_doc.find("Usage:")
        assert usage_idx != -1, "expected a 'Usage:' section in the module docstring"
        usage_section = module_doc[usage_idx:usage_idx + 400]
        assert "--selftest" in usage_section, (
            f"expected the 'Usage:' section to mention --selftest; "
            f"got: {usage_section!r}"
        )

    def test_exit_codes_section_mentions_selftest_and_synthetic_fixtures(self):
        with open(SCRIPT, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc

        exit_codes_idx = module_doc.find("Exit codes:")
        assert exit_codes_idx != -1, (
            "expected an 'Exit codes:' section in the module docstring"
        )
        exit_codes_section = module_doc[exit_codes_idx:exit_codes_idx + 700]
        assert "--selftest" in exit_codes_section, (
            f"expected the 'Exit codes:' section to document --selftest's "
            f"exit-code meanings; got: {exit_codes_section!r}"
        )
        assert re.search(r"synthetic", exit_codes_section, re.IGNORECASE), (
            f"expected the 'Exit codes:' section to clarify that --selftest's "
            f"0/1/2 codes are evaluated against the two synthetic fixtures, "
            f"not against fix_plan.md; got: {exit_codes_section!r}"
        )


# ---------------------------------------------------------------------------
# Bonus coverage (not one of the 11 numbered ACs, but `_today_iso()` is one
# of the FOUR named public functions this spec's "Public interface summary"
# explicitly calls out as fair game to test directly): `_today_iso()` returns
# today's real UTC date in ISO YYYY-MM-DD form, per its own spec'd
# definition (`datetime.now(timezone.utc).date().isoformat()`). This is what
# actually guarantees AC1/AC2's good fixture heading is always on/after
# PROOF_REQUIRED_SINCE without a hardcoded literal date -- this project's own
# named gotcha to avoid (see spec, "Step A").
# ---------------------------------------------------------------------------

class TestPhase3TodayIsoHelper:
    def test_today_iso_matches_real_utc_date_between_two_wall_clock_reads(self):
        before = datetime.now(timezone.utc).date().isoformat()
        result = lint._today_iso()
        after = datetime.now(timezone.utc).date().isoformat()

        assert result in (before, after), (
            f"expected _today_iso()=={result!r} to equal the real UTC date "
            f"read immediately before ({before!r}) or after ({after!r}) "
            f"calling it (a date rollover mid-test is the only reason these "
            f"would ever legitimately differ)"
        )
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result), (
            f"expected _today_iso() to return an ISO YYYY-MM-DD string, "
            f"got {result!r}"
        )


# =============================================================================
# Evidence-Gate Phase 4 (spec: loop-team/runs/2026-07-09_evidence-gate-
# phase4/specs/spec.md) -- `check_single_heading(content, heading_line,
# target_path, advisory=True)` does not exist yet. AC7-AC10 below test it
# DIRECTLY (unit-level, via `lint.check_single_heading(...)`), matching this
# file's own established convention ("a couple of unit-level tests exercise
# find_mismatches() directly... matching the same belt-and-suspenders style")
# -- `check_single_heading` has no CLI entry point of its own at all (unlike
# find_mismatches/find_proof_flags/find_freshness_and_dirty_flags, which
# main() calls), so direct-import is the ONLY way to exercise it, not merely
# the belt-and-suspenders option.
#
# Every fixture heading below is dated on/after PROOF_REQUIRED_SINCE
# (`_on_or_after_cutover(0)`) -- `check_single_heading` is documented to
# "reuse _proof_required_for_heading directly", and that gate exempts any
# heading dated before the cutover from v1/v2 checking entirely; an
# undated/pre-cutover fixture would make every assertion below pass
# vacuously regardless of whether check_single_heading's own routing logic
# is correct at all.
#
# All 4 classes are Phase4-tagged in their class names so
# `pytest -k "not Phase4"` (AC22's own regression-isolation mechanism, see
# hooks/test_loop_stop_guard.py) cleanly excludes them from the PRE-EXISTING
# suite health check.
# =============================================================================

class TestPhase4AC7CheckSingleHeadingManualModeStaleBlocks:
    """[BEHAVIORAL] AC7: check_single_heading(..., advisory=False) (manual/
    CLI-mode parity): a heading with a STALE cited file lands its STALE
    message in "messages" (blocking) -- proves manual invocation is
    unchanged from Phase 1-3."""

    def test_stale_cited_file_blocks_in_manual_mode(self, tmp_path):
        target, _evidence_file = _ac1_modified_file_fixture(tmp_path)
        content = target.read_text(encoding="utf-8")
        heading_line = next(h for h, _ in lint._iter_blocks(content))

        result = lint.check_single_heading(content, heading_line, str(target), advisory=False)

        assert any("STALE" in m for m in result["messages"]), result
        assert not any("STALE" in w for w in result.get("warnings", [])), result


class TestPhase4AC8CheckSingleHeadingHookPathStaleIsAdvisoryOnly:
    """[BEHAVIORAL] AC8: the SAME STALE-cited-file heading, checked with
    advisory=True (hook-path default), returns it in "warnings", NOT
    "messages" -- proves theme 4's advisory routing."""

    def test_stale_cited_file_is_advisory_only_with_advisory_true(self, tmp_path):
        target, _evidence_file = _ac1_modified_file_fixture(tmp_path)
        content = target.read_text(encoding="utf-8")
        heading_line = next(h for h, _ in lint._iter_blocks(content))

        result = lint.check_single_heading(content, heading_line, str(target), advisory=True)

        assert any("STALE" in w for w in result["warnings"]), result
        assert not any("STALE" in m for m in result["messages"]), result

    def test_advisory_parameter_defaults_to_true(self, tmp_path):
        # Proves the DEFAULT value itself (spec: "advisory=True (hook-path
        # default)"), not just the explicit advisory=True case above.
        target, _evidence_file = _ac1_modified_file_fixture(tmp_path)
        content = target.read_text(encoding="utf-8")
        heading_line = next(h for h, _ in lint._iter_blocks(content))

        result = lint.check_single_heading(content, heading_line, str(target))  # no advisory kwarg

        assert any("STALE" in w for w in result["warnings"]), result
        assert not any("STALE" in m for m in result["messages"]), result


class TestPhase4AC9V1V2ChecksAlwaysBlockingRegardlessOfAdvisory:
    """[BEHAVIORAL] AC9: a missing Proof block, an incomplete Proof block,
    and a fabricated proof_snapshot ALWAYS land in "messages" (never
    "warnings"), regardless of the advisory flag -- proves v1/v2 checks are
    unconditionally blocking in both paths."""

    def test_missing_proof_block_always_blocks(self, tmp_path):
        heading = _closed_heading("H-PHASE4-AC9-MISSING-1", _on_or_after_cutover(0))
        content = "%s\nSome closure prose, no Proof block at all.\n" % heading
        target = tmp_path / "fix_plan.md"
        _write(target, content)
        heading_line = next(h for h, _ in lint._iter_blocks(content))

        for advisory in (True, False):
            result = lint.check_single_heading(content, heading_line, str(target), advisory=advisory)
            assert any("missing proof block" in m for m in result["messages"]), (advisory, result)
            assert not any("missing proof block" in w for w in result.get("warnings", [])), (advisory, result)

    def test_incomplete_proof_block_always_blocks(self, tmp_path):
        heading = _closed_heading("H-PHASE4-AC9-INCOMPLETE-1", _on_or_after_cutover(0))
        body = _proof_block("echo hi", "0", "/tmp/whatever.json", omit_fields=("exit_code",))
        content = "%s\n%s" % (heading, body)
        target = tmp_path / "fix_plan.md"
        _write(target, content)
        heading_line = next(h for h, _ in lint._iter_blocks(content))

        for advisory in (True, False):
            result = lint.check_single_heading(content, heading_line, str(target), advisory=advisory)
            assert any("missing proof block" in m for m in result["messages"]), (advisory, result)
            assert not any("missing proof block" in w for w in result.get("warnings", [])), (advisory, result)

    def test_fabricated_proof_snapshot_always_blocks(self, tmp_path):
        heading = _closed_heading("H-PHASE4-AC9-FABRICATED-1", _on_or_after_cutover(0))
        nonexistent = str(tmp_path / "gate" / "proof" / "does-not-exist.json")
        body = _proof_block("echo hello", "0", nonexistent)
        content = "%s\n%s" % (heading, body)
        target = tmp_path / "fix_plan.md"
        _write(target, content)
        heading_line = next(h for h, _ in lint._iter_blocks(content))

        for advisory in (True, False):
            result = lint.check_single_heading(content, heading_line, str(target), advisory=advisory)
            assert any("no matching proof snapshot found" in m for m in result["messages"]), (advisory, result)
            assert not any("no matching proof snapshot found" in w for w in result.get("warnings", [])), (advisory, result)


class TestPhase4AC10V2FailureSuppressesV3Checks:
    """[BEHAVIORAL] AC10: a heading whose proof_snapshot exists, parses, but
    has a mismatched command/exit_code returns ONLY the v2 mismatch message
    in "messages" and NOTHING in "warnings" -- proves the v2-must-pass-
    before-v3 gate (theme 6) suppresses v3 checks on a v2 failure, not just
    documents it. The fixture pins a genuinely stale cited file into the
    snapshot's `files` dict -- if v3 ran unconditionally, staleness on that
    same cited file WOULD independently produce a warning; this fixture
    forces that would-be signal to exist so its ABSENCE from the result
    means the v2-gate genuinely suppressed v3, not merely that v3 had
    nothing to find regardless."""

    def test_v2_mismatch_with_a_genuinely_stale_cited_file_yields_no_v3_warnings(self, tmp_path):
        gate_dir = tmp_path / "gate"
        evidence_file = tmp_path / "ac10_evidence.txt"
        evidence_file.write_text("original content\n", encoding="utf-8")
        fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])
        # Make the cited file genuinely stale AFTER capture -- if v3 ran
        # unconditionally, this alone would produce a "STALE" warning.
        evidence_file.write_text("MODIFIED after capture\n", encoding="utf-8")

        heading = _closed_heading("H-PHASE4-AC10-1", _on_or_after_cutover(0))
        # Fabricate a command mismatch (v2 failure) while keeping the REAL
        # exit_code/proof_snapshot path from the real snapshot above.
        body = _proof_block("echo a-totally-different-command", fields["exit_code"], fields["proof_snapshot"])
        content = "%s\n%s" % (heading, body)
        target = tmp_path / "fix_plan.md"
        _write(target, content)
        heading_line = next(h for h, _ in lint._iter_blocks(content))

        for advisory in (True, False):
            result = lint.check_single_heading(content, heading_line, str(target), advisory=advisory)
            assert result["warnings"] == [], (advisory, result)
            assert len(result["messages"]) == 1, (advisory, result)
            assert "no matching proof snapshot found" in result["messages"][0], (advisory, result)
            assert "STALE" not in result["messages"][0], (advisory, result)
