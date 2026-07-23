"""Tests for loop-team/harness/closure_freshness_sweep.py (Evidence-Gate
Phase 5, spec: loop-team/runs/2026-07-09_evidence-gate-phase5/specs/spec.md,
Item 1 -- ACs 1-4, plus AC13's docstring requirement for this module).

Written BEFORE the implementation exists (closure_freshness_sweep.py is not
yet built) -- importing it below is EXPECTED to fail with
ModuleNotFoundError until the Coder delivers, which fails the collection of
this ENTIRE file (matching hooks/test_closure_touch_scan.py's own identical,
already-established precedent for the same "Tier-1, pre-implementation"
situation). That is correct per roles/test_writer.md's own header.

Self-contained (mirrors hooks/test_closure_touch_scan.py's stated
convention): builds its own minimal fixture-building helpers rather than
importing from loop-team/harness/test_fixplan_closure_lint.py, even though
several of those helpers (`_closed_heading`, `_proof_block`,
`_make_real_snapshot`, `_init_scratch_git_repo`, `_git_add_commit`) are
deliberately styled after that file's own already-proven, real (not
invented) conventions for building genuine Proof-block fixtures (real
snapshot files via the actual run_and_record.py CLI, real scratch git repos
for dirty/clean-worktree scenarios).

`sweep(content, target_path)` is tested UNIT-level, in-process (it is a pure
function of its two string arguments per the spec's own signature) using
pytest's `tmp_path`. The CLI (`main(argv)`) is tested by invoking the real
script as a subprocess, matching fixplan_closure_lint.py's own established
CLI-testing convention in this same directory.

Run: python3 -m pytest loop-team/harness/test_closure_freshness_sweep.py -q
"""
import ast
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fixplan_closure_lint as lint  # noqa: E402 -- existing, real, Phase 1-4 shipped

import closure_freshness_sweep as sweep_mod  # noqa: E402 -- does not exist yet; see module docstring

RUN_AND_RECORD = os.path.join(HERE, "run_and_record.py")
SWEEP_SCRIPT = os.path.join(HERE, "closure_freshness_sweep.py")

STALE_HEADING_SUFFIX_RE_TEMPLATE = r"-- STALE \(auto-flagged \d{4}-\d{2}-\d{2}, .*\)\s*$"


# ---------------------------------------------------------------------------
# Shared fixture-building helpers (self-contained; see module docstring).
# ---------------------------------------------------------------------------

def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _cutover_date():
    return date.fromisoformat(lint.PROOF_REQUIRED_SINCE)


def _on_or_after_cutover(days=0):
    return (_cutover_date() + timedelta(days=days)).isoformat()


def _closed_heading(id_text, date_str, note="some evidence"):
    """Returns the heading LINE text only (no leading '## ') -- matching
    `_iter_blocks`'s own yield convention and `check_single_heading`'s own
    `heading_line` parameter, per hooks/test_closure_touch_scan.py's
    identical convention."""
    return "%s -- some real fix -- CLOSED (%s, %s)" % (id_text, date_str, note)


def _proof_block(command, exit_code, proof_snapshot, verified_at=None, files=None):
    if verified_at is None:
        verified_at = "2026-07-09T00:00:00+00:00"
    lines = [
        "Proof:",
        "- command: %s" % command,
        "- exit_code: %s" % exit_code,
        "- proof_snapshot: %s" % proof_snapshot,
    ]
    if files:
        lines.append("- files: %s" % ", ".join(files))
    lines.append("- verified_at: %s" % verified_at)
    return "\n".join(lines) + "\n"


def _init_scratch_git_repo(repo_dir):
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "phase5-test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Phase5 Test Writer"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "commit.gpgsign", "false"],
        check=True, capture_output=True,
    )


def _git_add_commit(repo_dir, paths, message):
    subprocess.run(
        ["git", "-C", str(repo_dir), "add"] + [str(p) for p in paths],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-q", "-m", message],
        check=True, capture_output=True,
    )


def _extract_proof_block_fields(remainder_text):
    fields = {}
    for m in re.finditer(r"^-\s*(\w+):\s*(.*)$", remainder_text, re.MULTILINE):
        fields[m.group(1)] = m.group(2).strip()
    return fields


def _make_real_snapshot(gate_dir, command_argv):
    """Invoke the REAL run_and_record.py CLI to produce a genuine snapshot
    file + Proof block fields, matching test_fixplan_closure_lint.py's own
    already-proven `_make_real_snapshot` helper."""
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
        "run_and_record.py did not print a proof_snapshot line; "
        "stdout=%r stderr=%r" % (p.stdout, p.stderr)
    )
    return fields


def _run_sweep_cli(args, timeout=30):
    p = subprocess.run(
        [sys.executable, SWEEP_SCRIPT] + [str(a) for a in args],
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, p.stdout, p.stderr


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL]: sweep() on content with 2 CLOSED headings (one with a
# genuinely stale/dirty cited file, one fully fresh) returns exactly 1
# flagged entry, naming the stale heading. Exercises the reused v3
# git-status-based dirty-worktree check specifically (not just hash-based
# freshness), per the spec's own explicit instruction.
# ---------------------------------------------------------------------------

def _stale_and_fresh_heading_fixture(tmp_path):
    """One CLOSED heading whose cited file has a genuine UNCOMMITTED git
    change (the v3 dirty-worktree check), one CLOSED heading whose cited
    file is fully clean/unchanged. Both headings carry a real, v2-passing
    Proof block (a genuine snapshot generated via run_and_record.py).
    Returns (content, target_path, stale_heading, fresh_heading)."""
    repo_dir = tmp_path / "sweep_ac1_repo"
    _init_scratch_git_repo(repo_dir)

    stale_evidence = repo_dir / "stale_evidence.txt"
    stale_evidence.write_text("committed content\n", encoding="utf-8")
    _git_add_commit(repo_dir, [stale_evidence], "initial commit")
    stale_evidence.write_text("dirty, uncommitted content\n", encoding="utf-8")

    fresh_evidence = repo_dir / "fresh_evidence.txt"
    fresh_evidence.write_text("clean content, never touched again\n", encoding="utf-8")
    _git_add_commit(repo_dir, [fresh_evidence], "second commit")

    gate_dir = tmp_path / "gate"
    stale_fields = _make_real_snapshot(gate_dir, ["cat", str(stale_evidence)])
    fresh_fields = _make_real_snapshot(gate_dir, ["cat", str(fresh_evidence)])

    stale_heading = _closed_heading("H-SWEEP-AC1-STALE-1", _on_or_after_cutover(0))
    stale_body = _proof_block(
        stale_fields["command"], stale_fields["exit_code"], stale_fields["proof_snapshot"]
    )
    fresh_heading = _closed_heading("H-SWEEP-AC1-FRESH-1", _on_or_after_cutover(0))
    fresh_body = _proof_block(
        fresh_fields["command"], fresh_fields["exit_code"], fresh_fields["proof_snapshot"]
    )

    content = "## %s\n%s\n## %s\n%s" % (stale_heading, stale_body, fresh_heading, fresh_body)
    target = tmp_path / "fix_plan.md"
    _write(target, content)
    return content, str(target), stale_heading, fresh_heading


class TestAC1SweepFlagsExactlyTheStaleHeading:
    def test_sweep_returns_exactly_one_flagged_entry_naming_the_stale_heading(self, tmp_path):
        content, target, stale_heading, fresh_heading = _stale_and_fresh_heading_fixture(tmp_path)

        result = sweep_mod.sweep(content, target)

        assert len(result) == 1, result
        assert result[0]["heading"] == stale_heading, result
        assert isinstance(result[0]["messages"], list) and result[0]["messages"], result
        assert any(
            "uncommitted changes" in m for m in result[0]["messages"]
        ), result[0]["messages"]
        # The fresh heading must not appear anywhere in the flagged results.
        assert all(entry["heading"] != fresh_heading for entry in result), result


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL]: the CLI appends a new "-- STALE (auto-flagged <date>,
# ...)" heading at the precise insertion point, the ORIGINAL heading's own
# text is byte-unchanged, and its own body (including any Proof: block) is
# byte-identical to what _iter_blocks returned for it BEFORE the append.
# Covers the "flagged heading is the LAST block" (end-of-file insertion)
# case directly.
# ---------------------------------------------------------------------------

def _single_stale_heading_fixture(tmp_path):
    repo_dir = tmp_path / "sweep_ac2_repo"
    _init_scratch_git_repo(repo_dir)
    evidence_file = repo_dir / "evidence.txt"
    evidence_file.write_text("committed content\n", encoding="utf-8")
    _git_add_commit(repo_dir, [evidence_file], "initial commit")
    evidence_file.write_text("dirty, uncommitted content\n", encoding="utf-8")

    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

    heading = _closed_heading("H-SWEEP-AC2-SINGLE-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    content = "## %s\n%s" % (heading, body)
    target = tmp_path / "fix_plan.md"
    _write(target, content)
    return target, heading


class TestAC2CliAppendsStaleHeadingOriginalBodyIntact:
    def test_single_last_block_heading_appended_at_eof_original_body_byte_identical(
        self, tmp_path
    ):
        target, heading = _single_stale_heading_fixture(tmp_path)
        content_before = target.read_text(encoding="utf-8")
        blocks_before = dict(lint._iter_blocks(content_before))
        assert heading in blocks_before, blocks_before
        body_before = blocks_before[heading]

        code, out, err = _run_sweep_cli([str(target)])
        assert code == 1, "stdout=%r stderr=%r" % (out, err)

        content_after = target.read_text(encoding="utf-8")
        # Original heading line itself is still present, byte-unchanged.
        assert ("## %s\n" % heading) in content_after, content_after

        blocks_after = dict(lint._iter_blocks(content_after))
        assert heading in blocks_after, blocks_after
        assert blocks_after[heading] == body_before, (
            "the ORIGINAL heading's own body (including its Proof: block) "
            "must remain fully intact -- byte-identical to what _iter_blocks "
            "returned for it BEFORE the append ran"
        )

        stale_re = re.compile(
            r"^## (%s %s)" % (re.escape(heading), STALE_HEADING_SUFFIX_RE_TEMPLATE),
            re.MULTILINE,
        )
        m = stale_re.search(content_after)
        assert m, content_after
        appended_heading_text = m.group(1)
        # Printed to stdout, per spec ("print each appended heading text to
        # stdout").
        assert appended_heading_text in out, out


# ---------------------------------------------------------------------------
# AC2 + AC3 [BEHAVIORAL]: verified together against a fixture with 2
# SIMULTANEOUSLY flagged headings in ONE invocation -- confirms both
# original headings' own bodies remain intact AND both new STALE headings
# land at their own correct, distinct positions with no corruption,
# cross-contamination, or offset drift between them. Uses 3 headings (A
# stale/not-last, B clean/never flagged, C stale/last) to exercise BOTH the
# "insert before next heading" and "insert at end-of-file" cases in the SAME
# multi-insertion, reverse-position-order pass.
# ---------------------------------------------------------------------------

def _three_heading_dual_stale_fixture(tmp_path):
    repo_dir = tmp_path / "sweep_dual_repo"
    _init_scratch_git_repo(repo_dir)

    evidence_a = repo_dir / "evidence_a.txt"
    evidence_a.write_text("committed a\n", encoding="utf-8")
    _git_add_commit(repo_dir, [evidence_a], "commit a")
    evidence_a.write_text("dirty a, uncommitted\n", encoding="utf-8")

    evidence_b = repo_dir / "evidence_b.txt"
    evidence_b.write_text("clean b, never touched again\n", encoding="utf-8")
    _git_add_commit(repo_dir, [evidence_b], "commit b")

    evidence_c = repo_dir / "evidence_c.txt"
    evidence_c.write_text("committed c\n", encoding="utf-8")
    _git_add_commit(repo_dir, [evidence_c], "commit c")
    evidence_c.write_text("dirty c, uncommitted\n", encoding="utf-8")

    gate_dir = tmp_path / "gate"
    fields_a = _make_real_snapshot(gate_dir, ["cat", str(evidence_a)])
    fields_b = _make_real_snapshot(gate_dir, ["cat", str(evidence_b)])
    fields_c = _make_real_snapshot(gate_dir, ["cat", str(evidence_c)])

    heading_a = _closed_heading("H-SWEEP-DUAL-STALE-A", _on_or_after_cutover(0))
    heading_b = _closed_heading("H-SWEEP-DUAL-CLEAN-B", _on_or_after_cutover(0))
    heading_c = _closed_heading("H-SWEEP-DUAL-STALE-C", _on_or_after_cutover(0))

    body_a = _proof_block(fields_a["command"], fields_a["exit_code"], fields_a["proof_snapshot"])
    body_b = _proof_block(fields_b["command"], fields_b["exit_code"], fields_b["proof_snapshot"])
    body_c = _proof_block(fields_c["command"], fields_c["exit_code"], fields_c["proof_snapshot"])

    content = (
        "## %s\n%s\n## %s\n%s\n## %s\n%s"
        % (heading_a, body_a, heading_b, body_b, heading_c, body_c)
    )
    target = tmp_path / "fix_plan.md"
    _write(target, content)
    return target, heading_a, heading_b, heading_c


class TestAC2AndAC3DualSimultaneousFlaggedHeadingsNoCorruption:
    def test_two_simultaneous_stale_headings_both_appended_no_corruption(self, tmp_path):
        target, heading_a, heading_b, heading_c = _three_heading_dual_stale_fixture(tmp_path)
        content_before = target.read_text(encoding="utf-8")
        blocks_before = dict(lint._iter_blocks(content_before))
        body_a_before = blocks_before[heading_a]
        body_b_before = blocks_before[heading_b]
        body_c_before = blocks_before[heading_c]

        code, out, err = _run_sweep_cli([str(target)])
        assert code == 1, "stdout=%r stderr=%r" % (out, err)

        content_after = target.read_text(encoding="utf-8")
        blocks_after = dict(lint._iter_blocks(content_after))

        # All 3 ORIGINAL headings' own bodies remain byte-identical.
        assert blocks_after[heading_a] == body_a_before, "heading A body corrupted"
        assert blocks_after[heading_b] == body_b_before, "heading B (never flagged) body corrupted"
        assert blocks_after[heading_c] == body_c_before, "heading C body corrupted"

        stale_re = re.compile(
            r"^## (.+ %s)" % STALE_HEADING_SUFFIX_RE_TEMPLATE, re.MULTILINE
        )
        stale_headings = stale_re.findall(content_after)
        assert len(stale_headings) == 2, (
            "expected exactly 2 new STALE follow-up headings (one for A, one "
            "for C -- B was never flagged), got: %r" % stale_headings
        )
        assert any(h.startswith(heading_a) for h in stale_headings), stale_headings
        assert any(h.startswith(heading_c) for h in stale_headings), stale_headings
        assert not any(h.startswith(heading_b) for h in stale_headings), (
            "heading B was never flagged and must never get a STALE follow-up: %r"
            % stale_headings
        )

        stale_a = [h for h in stale_headings if h.startswith(heading_a)][0]
        stale_c = [h for h in stale_headings if h.startswith(heading_c)][0]

        # A's own STALE follow-up lands strictly BEFORE B's own heading line
        # (the "insert immediately before the next ## heading" rule).
        idx_b_heading = content_after.index("## %s" % heading_b)
        idx_stale_a = content_after.index(stale_a)
        assert idx_stale_a < idx_b_heading, (
            "A's STALE follow-up must be inserted before B's own heading, "
            "not after it or interleaved incorrectly"
        )

        # C's own STALE follow-up lands at end-of-file (C was the last block).
        idx_stale_c = content_after.index(stale_c)
        assert idx_stale_c > content_after.index("## %s" % heading_c), (
            "C's STALE follow-up must land after C's own block (end-of-file "
            "insertion, since C was the last block)"
        )


# ---------------------------------------------------------------------------
# AC3 [BEHAVIORAL]: running the sweep CLI TWICE on the same day against the
# same unfixed stale entry does not append a second, duplicate STALE
# heading.
# ---------------------------------------------------------------------------

class TestAC3RunningCliTwiceSameDayDoesNotDuplicate:
    def test_second_same_day_run_appends_no_duplicate_stale_heading(self, tmp_path):
        target, heading = _single_stale_heading_fixture(tmp_path)

        code1, out1, err1 = _run_sweep_cli([str(target)])
        assert code1 == 1, "stdout=%r stderr=%r" % (out1, err1)
        content_after_first = target.read_text(encoding="utf-8")

        stale_re = re.compile(
            r"^## %s %s" % (re.escape(heading), STALE_HEADING_SUFFIX_RE_TEMPLATE),
            re.MULTILINE,
        )
        first_matches = stale_re.findall(content_after_first)
        assert len(first_matches) == 1, content_after_first

        code2, out2, err2 = _run_sweep_cli([str(target)])
        content_after_second = target.read_text(encoding="utf-8")

        assert content_after_second == content_after_first, (
            "running the sweep CLI a second time the same day against the "
            "same unfixed stale entry must not append a second, duplicate "
            "STALE heading -- file content must be unchanged"
        )
        second_matches = stale_re.findall(content_after_second)
        assert len(second_matches) == 1, (
            "expected still exactly 1 STALE follow-up for this heading after "
            "the second run, got: %r" % second_matches
        )


# ---------------------------------------------------------------------------
# AC4 [BEHAVIORAL]: sweep() never re-executes a Proof block's OWN CITED
# COMMAND. A fixture whose Proof block cites a command that would raise/fail
# loudly if actually executed (a nonexistent binary), where BOTH the Proof
# block's own `command` field AND its cited snapshot's own recorded
# `command` field are hand-constructed to be the IDENTICAL nonexistent-
# binary string -- isolating "was the command re-executed" from the
# unrelated, legitimate v2 command-string-mismatch check.
# ---------------------------------------------------------------------------

NONEXISTENT_BINARY = "definitely-not-a-real-binary-xyz123-phase5-ac4"


def _nonexistent_binary_command_fixture(tmp_path):
    gate_dir = tmp_path / "gate"
    proof_dir = gate_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "command": [NONEXISTENT_BINARY],
        "exit_code": 0,
        "output_sha256": "0" * 64,
        "files": {},
        "dirty_at_capture": False,
        "captured_at": "2026-07-09T00:00:00+00:00",
    }
    snapshot_path = proof_dir / "hand-constructed-nonexistent-binary.json"
    snapshot_path.write_text(json.dumps(record), encoding="utf-8")

    heading = _closed_heading("H-SWEEP-AC4-NOEXEC-1", _on_or_after_cutover(0))
    # Both the Proof block's claimed command AND the snapshot's own recorded
    # command are the IDENTICAL nonexistent-binary string, so v2's own
    # snapshot-cross-check (a legitimate, unrelated check) does not fire and
    # mask what this AC actually tests.
    body = _proof_block(NONEXISTENT_BINARY, "0", str(snapshot_path))
    content = "## %s\n%s" % (heading, body)
    target = tmp_path / "fix_plan.md"
    _write(target, content)
    return content, str(target), heading


def _real_successful_noop_command_fixture(tmp_path):
    gate_dir = tmp_path / "gate_control"
    fields = _make_real_snapshot(gate_dir, ["true"])
    heading = _closed_heading("H-SWEEP-AC4-CONTROL-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    content = "## %s\n%s" % (heading, body)
    target = tmp_path / "fix_plan.md"
    _write(target, content)
    return content, str(target), heading


class TestAC4NeverReexecutesProofBlocksCitedCommand:
    def test_nonexistent_binary_genuinely_cannot_be_launched_sanity_check(self):
        """Sanity precondition: confirm the chosen binary name really is not
        launchable in this environment, so if sweep() DID try to actually
        execute it, that would raise/fail loudly rather than silently
        succeed (proving this fixture is a real oracle, not a no-op)."""
        with pytest.raises((FileNotFoundError, OSError)):
            subprocess.run([NONEXISTENT_BINARY], capture_output=True)

    def test_sweep_completes_normally_reports_zero_findings_for_nonexistent_binary_fixture(
        self, tmp_path
    ):
        content, target, heading = _nonexistent_binary_command_fixture(tmp_path)
        result = sweep_mod.sweep(content, target)
        assert result == [], (
            "sweep() must complete normally and report ZERO findings for a "
            "Proof block whose claimed command matches its cited snapshot's "
            "own recorded command (v2 passes cleanly) and cites no files (v3 "
            "has nothing to check) -- if sweep() had tried to actually launch "
            "the nonexistent binary, this would have raised/crashed instead "
            "of returning an empty list"
        )

    def test_nonexistent_binary_and_real_successful_command_produce_same_result_shape(
        self, tmp_path
    ):
        nonexistent_dir = tmp_path / "nonexistent"
        nonexistent_dir.mkdir()
        control_dir = tmp_path / "control"
        control_dir.mkdir()

        content_a, target_a, heading_a = _nonexistent_binary_command_fixture(nonexistent_dir)
        content_b, target_b, heading_b = _real_successful_noop_command_fixture(control_dir)

        result_a = sweep_mod.sweep(content_a, target_a)
        result_b = sweep_mod.sweep(content_b, target_b)

        assert result_a == result_b == [], (
            "the nonexistent-binary fixture and an equivalent fixture citing "
            "a REAL, successful command must produce the SAME result shape "
            "(both empty) -- proving the cited command's own execution "
            "status is never consulted by sweep()"
        )


# ---------------------------------------------------------------------------
# AC13 [DOC]: closure_freshness_sweep.py's own module docstring documents
# its purpose and hash-only/no-re-execution guarantee, and additionally
# notes that hooks/session_start.sh wiring is deferred to a future spec (not
# fail-open behavior that doesn't exist in this build).
# ---------------------------------------------------------------------------

class TestAC13ModuleDocstringDocumentsPurposeAndDeferredWiring:
    def test_docstring_documents_purpose_and_no_reexecution_guarantee(self):
        assert os.path.isfile(SWEEP_SCRIPT), "closure_freshness_sweep.py does not exist yet"
        with open(SWEEP_SCRIPT, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc, "expected closure_freshness_sweep.py to have a module docstring"
        lowered = module_doc.lower()
        assert re.search(r"hash|sha256", lowered), (
            "expected the docstring to document the hash-only re-validation approach"
        )
        assert re.search(
            r"never re-execut|no re-execution|not re-execut|does not re-execute",
            lowered,
        ), (
            "expected the docstring to document the guarantee that a Proof "
            "block's own cited command is never re-executed"
        )

    def test_docstring_documents_session_start_sh_wiring_is_deferred_not_fail_open(self):
        with open(SWEEP_SCRIPT, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc
        assert "session_start.sh" in module_doc, (
            "expected the docstring to explicitly note hooks/session_start.sh "
            "wiring is deferred to a future spec"
        )
        assert re.search(r"defer|future|out of scope|not.*this build", module_doc, re.IGNORECASE), (
            "expected the docstring to explain the session_start.sh "
            "integration is deferred, not fail-open/missing behavior"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
