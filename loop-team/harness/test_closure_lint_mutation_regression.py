"""Standing mutation-test regression (Evidence-Gate Phase 5, spec:
loop-team/runs/2026-07-09_evidence-gate-phase5/specs/spec.md, Item 2 --
AC6). THIS FILE IS ITSELF THE DELIVERABLE for Item 2/AC6, not a test of some
other new module.

Formalizes the ad hoc sabotage-smoke-test pattern already used across Phase
1-4's own test rounds (see loop-team/harness/test_fixplan_closure_lint.py's
TestAC9SabotageSmokeTests class) into a PERMANENT, always-collected pytest
file, per the H-AC-ORACLE-TARGET-1 / DESIGN_CHECKLIST.md gate-9 mutation-
check precedent this phase's Item 2 reuses.

IMPORTANT DIFFERENCE FROM THIS FILE'S TITLE, AND FROM EVERY OTHER NEW TEST
FILE IN THIS PHASE-5 DISPATCH: every one of this file's 4 targets is
ALREADY-SHIPPED, already-tested Phase 1-4 code (`_snapshot_cross_check`,
`_freshness_flags_for_snapshot`, `_dirty_cited_file_flags` in
fixplan_closure_lint.py; `CLOSURE_HEADING_RE` as re-bound in
hooks/closure_touch_scan.py) -- nothing here is new implementation the Coder
still needs to build. This file is therefore expected to be GREEN
IMMEDIATELY on creation (the one explicit exception to "should currently
fail" among this dispatch's test files, matching
test_fixplan_closure_lint.py's own AC9/AC13 precedent for the identical
situation) and must STAY green after Item 1 (closure_freshness_sweep.py) and
Item 3 (evidence_ledger.py) land on top of it (both reuse these same 4
targets, unmodified, per this whole phase's Non-goals: "No change to any
Phase 1-4 function's own logic").

MECHANISM (per spec's own explicit instruction -- DO NOT conflate with
test_fixplan_closure_lint.py's own, separate, EXISTING file-blob-swap-and-
subprocess sabotage convention, e.g. its TestAC9SabotageSmokeTests class):
ONE IN-PROCESS `monkeypatch.setattr()`-based test per target, a SINGLE
consistent mechanism throughout this file, simpler and faster, in-process
only. Each of the 4 tests below does all 4 steps in ONE test function (the
spec explicitly permits either "a SEPARATE, unpatched test" or "a second
assertion after monkeypatch's automatic per-test teardown" for the
"restored" half -- this file uses the latter, calling `monkeypatch.undo()`
explicitly mid-test, which IS pytest's own built-in automatic-teardown
mechanism, just invoked early rather than only at the end of the test):
  (a) construct a known-bad fixture the REAL, unpatched function/constant
      correctly flags;
  (b) apply the `monkeypatch.setattr` stub;
  (c) confirm the SAME fixture now WRONGLY passes under the stub (proving
      the stub genuinely disables the check, so this test has real teeth);
  (d) confirm the real, restored function/constant flags the same fixture
      again, after `monkeypatch.undo()`.

Targets 1-3 (`fixplan_closure_lint._snapshot_cross_check`,
`_freshness_flags_for_snapshot`, `_dirty_cited_file_flags`): all three live
in and are called via bare names from sibling functions WITHIN
fixplan_closure_lint.py itself, so `monkeypatch.setattr(fixplan_closure_lint,
"<func_name>", <stub>)` correctly intercepts those calls (Python resolves a
bare-name call inside a module against that module's own global namespace AT
CALL TIME).

Target 4 (`closure_touch_scan.CLOSURE_HEADING_RE`): this is the REAL
cross-module `from X import Y` monkeypatch case -- the patch is applied to
`closure_touch_scan`'s OWN already-re-bound namespace
(`monkeypatch.setattr(closure_touch_scan, "CLOSURE_HEADING_RE", <stub>)`),
NEVER `fixplan_closure_lint.CLOSURE_HEADING_RE` (patching the origin
module's own attribute would NOT affect closure_touch_scan's already-
imported, separately-bound local reference).

Run: python3 -m pytest loop-team/harness/test_closure_lint_mutation_regression.py -q
"""
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fixplan_closure_lint as lint  # noqa: E402 -- existing, real, Phase 1-4 shipped

REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
HOOKS_DIR = os.path.join(REPO_ROOT, "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

import closure_touch_scan  # noqa: E402 -- existing, real, Phase 4 shipped

RUN_AND_RECORD = os.path.join(HERE, "run_and_record.py")


# ---------------------------------------------------------------------------
# Shared fixture-building helpers (self-contained; see module docstring on
# why this file duplicates, rather than imports, small builder helpers).
# ---------------------------------------------------------------------------

def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _cutover_date():
    return date.fromisoformat(lint.PROOF_REQUIRED_SINCE)


def _on_or_after_cutover(days=0):
    return (_cutover_date() + timedelta(days=days)).isoformat()


def _closed_heading(id_text, date_str, note="some evidence"):
    return "%s -- some real fix -- CLOSED (%s, %s)" % (id_text, date_str, note)


def _proof_block(command, exit_code, proof_snapshot, verified_at=None):
    if verified_at is None:
        verified_at = "2026-07-09T00:00:00+00:00"
    lines = [
        "Proof:",
        "- command: %s" % command,
        "- exit_code: %s" % exit_code,
        "- proof_snapshot: %s" % proof_snapshot,
        "- verified_at: %s" % verified_at,
    ]
    return "\n".join(lines) + "\n"


def _init_scratch_git_repo(repo_dir):
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "mutreg-test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Mutation Regression Test Writer"],
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


# ---------------------------------------------------------------------------
# Target 1/4: fixplan_closure_lint._snapshot_cross_check
# ---------------------------------------------------------------------------

def test_snapshot_cross_check_mutation_regression_has_teeth(tmp_path, monkeypatch):
    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["echo", "mutreg-snapshot-cross-check-real-evidence"])
    heading = _closed_heading("H-MUTREG-SNAPCHECK-1", _on_or_after_cutover(0))
    # A fabricated command mismatch: the Proof block's claimed `command` does
    # NOT match what the real, genuine snapshot actually recorded.
    body = _proof_block(
        "echo a-totally-different-fabricated-command", fields["exit_code"], fields["proof_snapshot"]
    )
    content = "## %s\n%s" % (heading, body)

    # (a) real, unpatched function correctly flags this known-bad fixture.
    real_flags = lint.find_proof_flags(content)
    assert any(
        "no matching proof snapshot found" in f["message"] for f in real_flags
    ), real_flags

    # (b) apply the vacuous always-pass stub.
    monkeypatch.setattr(lint, "_snapshot_cross_check", lambda fields: None)

    # (c) confirm the SAME fixture now WRONGLY passes cleanly under the stub.
    stubbed_flags = lint.find_proof_flags(content)
    assert not any(
        "no matching proof snapshot found" in f["message"] for f in stubbed_flags
    ), stubbed_flags

    # (d) confirm the real, restored function re-flags the same fixture again
    # (pytest monkeypatch's own automatic teardown mechanism, invoked here
    # explicitly mid-test via .undo() -- no manual save/restore needed).
    monkeypatch.undo()
    restored_flags = lint.find_proof_flags(content)
    assert any(
        "no matching proof snapshot found" in f["message"] for f in restored_flags
    ), restored_flags


# ---------------------------------------------------------------------------
# Target 2/4: fixplan_closure_lint._freshness_flags_for_snapshot
# ---------------------------------------------------------------------------

def test_freshness_flags_for_snapshot_mutation_regression_has_teeth(tmp_path, monkeypatch):
    gate_dir = tmp_path / "gate"
    evidence_file = tmp_path / "mutreg_freshness_evidence.txt"
    evidence_file.write_text("original content\n", encoding="utf-8")
    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])
    evidence_file.write_text("MODIFIED after the snapshot was captured\n", encoding="utf-8")

    heading = _closed_heading("H-MUTREG-FRESHNESS-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    content = "## %s\n%s" % (heading, body)
    target_path = str(tmp_path / "fix_plan.md")  # need not exist; only passed through

    # (a) real, unpatched function correctly flags this known-bad fixture.
    real_flags = lint.find_freshness_and_dirty_flags(content, target_path)
    assert any("STALE" in f["message"] for f in real_flags), real_flags

    # (b) apply the vacuous always-pass stub.
    monkeypatch.setattr(lint, "_freshness_flags_for_snapshot", lambda snapshot_record: [])

    # (c) confirm the SAME fixture now WRONGLY passes cleanly under the stub.
    stubbed_flags = lint.find_freshness_and_dirty_flags(content, target_path)
    assert not any("STALE" in f["message"] for f in stubbed_flags), stubbed_flags

    # (d) confirm the real, restored function re-flags the same fixture again.
    monkeypatch.undo()
    restored_flags = lint.find_freshness_and_dirty_flags(content, target_path)
    assert any("STALE" in f["message"] for f in restored_flags), restored_flags


# ---------------------------------------------------------------------------
# Target 3/4: fixplan_closure_lint._dirty_cited_file_flags
# ---------------------------------------------------------------------------

def test_dirty_cited_file_flags_mutation_regression_has_teeth(tmp_path, monkeypatch):
    repo_dir = tmp_path / "mutreg_dirty_repo"
    _init_scratch_git_repo(repo_dir)
    evidence_file = repo_dir / "evidence.txt"
    evidence_file.write_text("committed content\n", encoding="utf-8")
    _git_add_commit(repo_dir, [evidence_file], "initial commit")
    evidence_file.write_text("dirty, uncommitted content\n", encoding="utf-8")

    gate_dir = tmp_path / "gate"
    fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])
    heading = _closed_heading("H-MUTREG-DIRTY-1", _on_or_after_cutover(0))
    body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
    content = "## %s\n%s" % (heading, body)
    target_path = str(tmp_path / "fix_plan.md")

    # (a) real, unpatched function correctly flags this known-bad fixture.
    real_flags = lint.find_freshness_and_dirty_flags(content, target_path)
    assert any(
        "evidence file has uncommitted changes" in f["message"] for f in real_flags
    ), real_flags

    # (b) apply the vacuous always-pass stub.
    monkeypatch.setattr(lint, "_dirty_cited_file_flags", lambda snapshot_record: [])

    # (c) confirm the SAME fixture now WRONGLY passes cleanly under the stub.
    stubbed_flags = lint.find_freshness_and_dirty_flags(content, target_path)
    assert not any(
        "evidence file has uncommitted changes" in f["message"] for f in stubbed_flags
    ), stubbed_flags

    # (d) confirm the real, restored function re-flags the same fixture again.
    monkeypatch.undo()
    restored_flags = lint.find_freshness_and_dirty_flags(content, target_path)
    assert any(
        "evidence file has uncommitted changes" in f["message"] for f in restored_flags
    ), restored_flags


# ---------------------------------------------------------------------------
# Target 4/4: closure_touch_scan.CLOSURE_HEADING_RE (re-bound namespace --
# patch closure_touch_scan's OWN attribute, never fixplan_closure_lint's).
# ---------------------------------------------------------------------------

def test_closure_touch_scan_closure_heading_re_mutation_regression_has_teeth(tmp_path, monkeypatch):
    heading_line = "H-MUTREG-TOUCHSCAN-1 -- CLOSED (2026-07-09, some evidence)"
    original_snapshot_path = "/tmp/mutreg-touchscan-original.json"
    edited_snapshot_path = "/tmp/mutreg-touchscan-edited.json"
    proof = (
        "Proof:\n"
        "- command: python3 run_and_record.py -- true\n"
        "- exit_code: 0\n"
        "- proof_snapshot: %s\n"
        "- verified_at: 2026-07-09T00:00:00+00:00\n"
    ) % original_snapshot_path
    content = "## %s\nSome body text.\n\n%s" % (heading_line, proof)
    target = tmp_path / "fix_plan.md"
    target.write_text(content, encoding="utf-8")

    # Apply the edit to the on-disk file too -- find_touched_closed_headings
    # re-reads target_fix_plan_path fresh from disk (post-edit state is
    # authoritative), matching real hook-path usage.
    edited_content = content.replace(
        "- proof_snapshot: %s" % original_snapshot_path,
        "- proof_snapshot: %s" % edited_snapshot_path,
    )
    target.write_text(edited_content, encoding="utf-8")

    edit_tu = {
        "type": "tool_use",
        "name": "Edit",
        "input": {
            "file_path": str(target),
            "old_string": "- proof_snapshot: %s" % original_snapshot_path,
            "new_string": "- proof_snapshot: %s" % edited_snapshot_path,
        },
    }

    # (a) real, unpatched CLOSURE_HEADING_RE correctly identifies this as an
    # armed, CLOSED heading (a genuine Proof-span edit on a CLOSED heading).
    real_result = closure_touch_scan.find_touched_closed_headings([edit_tu], str(target))
    assert real_result == [heading_line], real_result

    # (b) apply the stub to closure_touch_scan's OWN already-imported,
    # separately-bound namespace -- NOT fixplan_closure_lint.CLOSURE_HEADING_RE.
    monkeypatch.setattr(
        closure_touch_scan, "CLOSURE_HEADING_RE", re.compile(r"THIS_PATTERN_NEVER_MATCHES_XYZ")
    )

    # (c) confirm the SAME fixture now WRONGLY returns nothing under the stub
    # (step 5's own filter, `[h for h in armed if CLOSURE_HEADING_RE.search(h)]`,
    # now excludes every heading, even a genuinely-armed CLOSED one).
    stubbed_result = closure_touch_scan.find_touched_closed_headings([edit_tu], str(target))
    assert stubbed_result == [], stubbed_result

    # (d) confirm the real, restored constant re-arms/re-flags it again.
    monkeypatch.undo()
    restored_result = closure_touch_scan.find_touched_closed_headings([edit_tu], str(target))
    assert restored_result == [heading_line], restored_result


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
