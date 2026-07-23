"""Tests for commit_diff_reread.py (closes the review-to-commit gap).

Spec: loop-team/runs/2026-07-02_review-to-commit-gap/specs/spec.md (PLAN_PASS,
two rounds). Covers AC1-12 (BEHAVIORAL). AC13-14 are [DOC] criteria (prose in
orchestrator.md / fix_plan.md) checked by direct file read at Verifier time,
NOT by pytest -- intentionally out of scope for this file.

Written BEFORE the implementation exists (harness/commit_diff_reread.py is not
yet built) -- these tests are expected to fail with a subprocess failure
naming the missing script (a real, diagnosable non-zero exit + traceback, not
a silent no-op) until the Coder delivers. That is correct per the test-writer
role brief.

Convention matched from this repo's existing harness tests
(test_research_authenticity_check.py, test_verify_harness.py): invoke the
real CLI as a subprocess against fixture inputs and assert on its documented
JSON verdict on stdout plus its exit code -- the actual public interface Oga
uses, not internal function names.

Isolation (mandatory per dispatch instructions):
  - Every git repo used by these tests is a throwaway `git init` inside a
    pytest tmp_path fixture. Never the real ~/Claude/loop repo.
  - `LOOP_GATE_DIR` is set per-test to a tmp_path subdirectory via the
    subprocess env, so tests never read/write the real ~/.loop-gate.
  - Git commits in fixture repos pin `-c user.email=/-c user.name=` and
    `-c commit.gpgsign=false` on every git invocation so tests never depend
    on (or contaminate) the host machine's global git config.

Run: python3 -m pytest loop-team/harness/test_commit_diff_reread.py -q
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "commit_diff_reread.py")

SWEEP_TTL_S = 7 * 24 * 3600  # matches micro_step_gates.py's SWEEP_TTL_S

GIT_CFG = [
    "-c", "user.email=test@example.com",
    "-c", "user.name=Test Writer",
    "-c", "commit.gpgsign=false",
]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def gate_dir(tmp_path):
    """A throwaway LOOP_GATE_DIR, isolated from the real ~/.loop-gate."""
    d = tmp_path / "loop-gate"
    d.mkdir()
    return str(d)


@pytest.fixture
def env(gate_dir):
    """Subprocess env with LOOP_GATE_DIR pinned to the isolated tmp dir."""
    e = os.environ.copy()
    e["LOOP_GATE_DIR"] = gate_dir
    return e


def _init_repo(repo_dir):
    """git init a throwaway repo at repo_dir (a pathlib.Path or str)."""
    repo_dir = str(repo_dir)
    os.makedirs(repo_dir, exist_ok=True)
    subprocess.run(["git", "init"] + [], cwd=repo_dir, check=True,
                    capture_output=True, text=True)
    subprocess.run(["git"] + GIT_CFG + ["commit", "--allow-empty", "-m", "init"],
                    cwd=repo_dir, check=True, capture_output=True, text=True)
    return repo_dir


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _run(args, env, cwd=None, timeout=30):
    """Invoke the real CLI: python3 commit_diff_reread.py <args...>.

    Returns (exit_code, parsed_json_or_None, raw_stdout, raw_stderr).
    """
    p = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd,
    )
    try:
        data = json.loads(p.stdout)
    except (json.JSONDecodeError, ValueError):
        data = None
    return p.returncode, data, p.stdout, p.stderr


def _git(repo_dir, *args, check=True):
    return subprocess.run(["git"] + GIT_CFG + list(args), cwd=str(repo_dir),
                           check=check, capture_output=True, text=True)


def _head(repo_dir):
    return _git(repo_dir, "rev-parse", "HEAD").stdout.strip()


def _sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _snapshot_path(gate_dir, abs_path):
    key = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:16]
    return os.path.join(gate_dir, "reviewed", "%s.json" % key)


# ---------------------------------------------------------------------------
# AC1 -- record on an existing file writes a correct snapshot + prints JSON
# ---------------------------------------------------------------------------

class TestAC1RecordWritesSnapshot:
    """[BEHAVIORAL] record <file> on a file that exists writes a snapshot to
    $LOOP_GATE_DIR/reviewed/<hash>.json containing the correct sha256 of the
    file's current bytes, and prints the documented JSON with exit 0."""

    def test_record_creates_snapshot_file_with_correct_hash(self, tmp_path, env, gate_dir):
        target = tmp_path / "orchestrator.md"
        content = "# Orchestrator\n\nSome real reviewed content.\n"
        _write(target, content)
        abs_path = str(target)

        code, data, out, err = _run(["record", abs_path], env)

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert data["recorded"] is True
        assert data["file"] == abs_path
        expected_hash = _sha256_file(abs_path)
        assert data["sha256"] == expected_hash
        assert "reviewed_at" in data and data["reviewed_at"]

        snap_path = _snapshot_path(gate_dir, abs_path)
        assert os.path.exists(snap_path), (
            f"expected snapshot at {snap_path}, gate_dir contents: "
            f"{list(os.walk(gate_dir))}"
        )
        with open(snap_path) as f:
            snap = json.load(f)
        assert snap["sha256"] == expected_hash

    def test_record_overwrites_prior_snapshot_for_same_path(self, tmp_path, env, gate_dir):
        target = tmp_path / "role.md"
        _write(target, "version one\n")
        abs_path = str(target)

        _run(["record", abs_path], env)
        snap_path = _snapshot_path(gate_dir, abs_path)
        with open(snap_path) as f:
            first_snap = json.load(f)

        _write(target, "version two, changed\n")
        code, data, out, err = _run(["record", abs_path], env)
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        with open(snap_path) as f:
            second_snap = json.load(f)
        assert second_snap["sha256"] != first_snap["sha256"]
        assert second_snap["sha256"] == _sha256_file(abs_path)


# ---------------------------------------------------------------------------
# AC2 -- record on a nonexistent file fails loudly, writes nothing
# ---------------------------------------------------------------------------

class TestAC2RecordNonexistentFile:
    """[BEHAVIORAL] record on a nonexistent file prints an error JSON and
    exits 2 (no snapshot file is written)."""

    def test_record_missing_file_exits_2_no_snapshot_written(self, tmp_path, env, gate_dir):
        abs_path = str(tmp_path / "does_not_exist.md")

        code, data, out, err = _run(["record", abs_path], env)

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert data is not None, f"stdout={out!r} stderr={err!r}"

        reviewed_dir = os.path.join(gate_dir, "reviewed")
        if os.path.isdir(reviewed_dir):
            assert os.listdir(reviewed_dir) == [], (
                "no snapshot should be written for a nonexistent file, got: "
                f"{os.listdir(reviewed_dir)}"
            )
        snap_path = _snapshot_path(gate_dir, abs_path)
        assert not os.path.exists(snap_path)


# ---------------------------------------------------------------------------
# AC3 -- check immediately after record (unchanged) -> match: true, exit 0
# ---------------------------------------------------------------------------

class TestAC3CheckMatchesAfterRecord:
    """[BEHAVIORAL] check <file> immediately after record <file> (file
    unchanged in between) prints {"match": true, ...} and exits 0."""

    def test_check_matches_when_file_unchanged_since_record(self, tmp_path, env):
        target = tmp_path / "fix_plan.md"
        _write(target, "## H-SOMETHING-1\nsome real content\n")
        abs_path = str(target)

        rec_code, rec_data, *_ = _run(["record", abs_path], env)
        assert rec_code == 0

        code, data, out, err = _run(["check", abs_path], env)

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert data["match"] is True
        assert data["file"] == abs_path
        assert "reviewed_at" in data


# ---------------------------------------------------------------------------
# AC4 -- check after the file changed since record -> mismatch + real diff
# ---------------------------------------------------------------------------

class TestAC4CheckMismatchAfterEdit:
    """[BEHAVIORAL] check <file> after the file's content changed since the
    last record prints {"match": false, ...} with a non-empty diff field
    showing the actual textual change, and exits 1."""

    def test_check_reports_mismatch_with_real_diff_after_edit(self, tmp_path, env):
        target = tmp_path / "search_playbook.md"
        _write(target, "line one\nline two\nline three\n")
        abs_path = str(target)

        _run(["record", abs_path], env)

        _write(target, "line one\nline two CHANGED\nline three\nline four appended\n")

        code, data, out, err = _run(["check", abs_path], env)

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data["match"] is False
        assert data["file"] == abs_path
        assert "diff" in data and data["diff"], (
            f"expected a non-empty unified diff, got: {data.get('diff')!r}"
        )
        # The diff must show the real textual change, not a generic message.
        assert "CHANGED" in data["diff"] or "line four appended" in data["diff"], (
            f"diff does not reflect the actual edit: {data['diff']!r}"
        )


# ---------------------------------------------------------------------------
# AC5 -- check with no prior record -> loud fail, never a silent pass
# ---------------------------------------------------------------------------

class TestAC5CheckNoPriorSnapshot:
    """[BEHAVIORAL] check <file> with NO prior record for that path prints
    {"match": false, "error": "no_reviewed_snapshot", ...} and exits 1 --
    never a silent/implicit pass."""

    def test_check_with_no_snapshot_fails_loudly(self, tmp_path, env):
        target = tmp_path / "never_recorded.md"
        _write(target, "content nobody reviewed via this tool\n")
        abs_path = str(target)

        code, data, out, err = _run(["check", abs_path], env)

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data["match"] is False
        assert data.get("error") == "no_reviewed_snapshot"


# ---------------------------------------------------------------------------
# AC6 -- commit (single file) after matching record creates a real commit
# ---------------------------------------------------------------------------

class TestAC6CommitSingleFileSuccess:
    """[BEHAVIORAL] commit <file> -- <message> (single file) after a
    matching record actually creates a real git commit containing exactly
    that file's currently-staged change, in the correct repo (resolved from
    the file's own directory, not the CWD), and the new HEAD's commit
    message equals <message>."""

    def test_commit_creates_real_commit_with_matching_message(self, tmp_path, env):
        repo = tmp_path / "repo"
        _init_repo(repo)
        target = repo / "orchestrator.md"
        _write(target, "original tracked content\n")
        _git(repo, "add", "orchestrator.md")
        _git(repo, "commit", "-m", "seed orchestrator.md")

        _write(target, "reviewed edit to orchestrator.md\n")
        abs_path = str(target)

        _run(["record", abs_path], env)

        head_before = _head(repo)

        # Run from a different CWD than the repo to prove repo resolution
        # comes from the file's own directory, not the CWD.
        other_cwd = str(tmp_path)
        code, data, out, err = _run(
            ["commit", abs_path, "--", "Reviewed edit to orchestrator.md"],
            env, cwd=other_cwd,
        )

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert data["committed"] is True
        assert abs_path in data["files"]

        head_after = _head(repo)
        assert head_after != head_before
        assert data["commit"] == head_after

        log = _git(repo, "log", "-1", "--pretty=%B").stdout.strip()
        assert log == "Reviewed edit to orchestrator.md"

        show = _git(repo, "show", "--stat", "HEAD").stdout
        assert "orchestrator.md" in show

        status = _git(repo, "status", "--porcelain").stdout.strip()
        assert status == "", f"working tree should be clean after commit, got: {status!r}"


# ---------------------------------------------------------------------------
# AC7 -- commit after mismatched/missing record: no commit, no staging
# ---------------------------------------------------------------------------

class TestAC7CommitBlockedOnMismatch:
    """[BEHAVIORAL] commit <file> -- <message> after a MISMATCHED (or
    missing) record does NOT create a commit and does NOT stage the file
    (git status unchanged before/after) -- verify by diffing
    git rev-parse HEAD before and after (must be identical) and confirming
    the file shows as still modified/untracked in git status --porcelain
    afterward if it was before."""

    def test_commit_blocked_when_record_stale(self, tmp_path, env):
        repo = tmp_path / "repo"
        _init_repo(repo)
        target = repo / "VERIFIER.md"
        _write(target, "original content\n")
        _git(repo, "add", "VERIFIER.md")
        _git(repo, "commit", "-m", "seed VERIFIER.md")

        _write(target, "reviewed version\n")
        abs_path = str(target)
        _run(["record", abs_path], env)

        # Content changes AGAIN after record -> the record is now stale.
        _write(target, "reviewed version PLUS an unreviewed extra line\n")

        head_before = _head(repo)
        status_before = _git(repo, "status", "--porcelain").stdout.strip()
        assert status_before != "", "fixture setup: file must show as modified before commit attempt"

        code, data, out, err = _run(
            ["commit", abs_path, "--", "Should not land"], env,
        )

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data["committed"] is False

        head_after = _head(repo)
        assert head_after == head_before, "HEAD must be unchanged when commit is blocked"

        status_after = _git(repo, "status", "--porcelain").stdout.strip()
        assert status_after == status_before, (
            f"working tree/index must be untouched; before={status_before!r} "
            f"after={status_after!r}"
        )
        # Not staged: the porcelain entry must not show an index (staged) state.
        # Use the RAW (non-stripped) porcelain line here: git's fixed-width XY
        # code puts the index-status in column X. A staged mod is "M  f.txt"
        # (X='M'); an unstaged-only mod is " M f.txt" (X=' '). Stripping the
        # leading space (as status_after does above) destroys that distinction,
        # so re-fetch the raw line for this specific check.
        status_after_raw = _git(repo, "status", "--porcelain").stdout
        assert not status_after_raw.startswith("M "), (
            f"file must not be staged (index-modified), got status: {status_after_raw!r}"
        )

    def test_commit_blocked_when_no_record_at_all(self, tmp_path, env):
        repo = tmp_path / "repo"
        _init_repo(repo)
        target = repo / "fix_plan.md"
        _write(target, "tracked baseline\n")
        _git(repo, "add", "fix_plan.md")
        _git(repo, "commit", "-m", "seed fix_plan.md")

        _write(target, "unreviewed edit, never recorded\n")
        abs_path = str(target)

        head_before = _head(repo)

        code, data, out, err = _run(
            ["commit", abs_path, "--", "Should not land either"], env,
        )

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data["committed"] is False

        head_after = _head(repo)
        assert head_after == head_before

        status = _git(repo, "status", "--porcelain").stdout.strip()
        assert status != "", "file must still show as modified/untracked after blocked commit"


# ---------------------------------------------------------------------------
# AC8 -- two different files tracked independently, no cross-file bleed
# ---------------------------------------------------------------------------

class TestAC8NoCrossFileBleed:
    """[BEHAVIORAL] Two DIFFERENT files tracked independently: recording
    file A does not affect a check on file B (no cross-file bleed in the
    hash keying)."""

    def test_recording_file_a_does_not_satisfy_check_on_file_b(self, tmp_path, env):
        file_a = tmp_path / "a.md"
        file_b = tmp_path / "b.md"
        _write(file_a, "content of file A\n")
        _write(file_b, "content of file B, never recorded\n")

        _run(["record", str(file_a)], env)

        code_a, data_a, *_ = _run(["check", str(file_a)], env)
        assert code_a == 0
        assert data_a["match"] is True

        code_b, data_b, out_b, err_b = _run(["check", str(file_b)], env)
        assert code_b == 1, f"stdout={out_b!r} stderr={err_b!r}"
        assert data_b["match"] is False
        assert data_b.get("error") == "no_reviewed_snapshot", (
            "file B must NOT inherit file A's snapshot -- got: %r" % data_b
        )

    def test_recording_both_then_editing_only_one_flags_only_that_one(self, tmp_path, env):
        file_a = tmp_path / "a.md"
        file_b = tmp_path / "b.md"
        _write(file_a, "content of file A, stable\n")
        _write(file_b, "content of file B, stable\n")

        _run(["record", str(file_a)], env)
        _run(["record", str(file_b)], env)

        # Only file B changes after both were recorded.
        _write(file_b, "content of file B, EDITED after record\n")

        code_a, data_a, *_ = _run(["check", str(file_a)], env)
        assert code_a == 0
        assert data_a["match"] is True, "file A must still match; untouched by file B's edit"

        code_b, data_b, *_ = _run(["check", str(file_b)], env)
        assert code_b == 1
        assert data_b["match"] is False


# ---------------------------------------------------------------------------
# AC9 -- multi-file commit, both matching, creates exactly ONE commit
# ---------------------------------------------------------------------------

class TestAC9MultiFileCommitBothMatch:
    """[BEHAVIORAL] commit <fileA> <fileB> -- <message> (multi-file) where
    BOTH have matching records creates exactly ONE real git commit
    containing both files' staged changes, message equals <message>;
    git show --stat on the new commit lists both files."""

    def test_multi_file_commit_creates_one_commit_with_both_files(self, tmp_path, env):
        repo = tmp_path / "repo"
        _init_repo(repo)
        file_a = repo / "orchestrator.md"
        file_b = repo / "fix_plan.md"
        _write(file_a, "baseline A\n")
        _write(file_b, "baseline B\n")
        _git(repo, "add", "orchestrator.md", "fix_plan.md")
        _git(repo, "commit", "-m", "seed both files")

        _write(file_a, "reviewed edit A\n")
        _write(file_b, "reviewed edit B\n")

        _run(["record", str(file_a)], env)
        _run(["record", str(file_b)], env)

        commit_count_before = len(
            _git(repo, "log", "--oneline").stdout.strip().splitlines()
        )
        head_before = _head(repo)

        code, data, out, err = _run(
            ["commit", str(file_a), str(file_b), "--", "Two-file reviewed commit"],
            env,
        )

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert data["committed"] is True
        assert set(data["files"]) == {str(file_a), str(file_b)}

        head_after = _head(repo)
        assert head_after != head_before
        assert data["commit"] == head_after

        commit_count_after = len(
            _git(repo, "log", "--oneline").stdout.strip().splitlines()
        )
        assert commit_count_after == commit_count_before + 1, (
            "exactly one new commit must be created, not two"
        )

        log_msg = _git(repo, "log", "-1", "--pretty=%B").stdout.strip()
        assert log_msg == "Two-file reviewed commit"

        show = _git(repo, "show", "--stat", "HEAD").stdout
        assert "orchestrator.md" in show
        assert "fix_plan.md" in show

        status = _git(repo, "status", "--porcelain").stdout.strip()
        assert status == "", f"working tree must be clean after commit, got {status!r}"


# ---------------------------------------------------------------------------
# AC10 -- multi-file commit, one mismatches: NO commit, NEITHER staged
# ---------------------------------------------------------------------------

class TestAC10MultiFileCommitPartialMismatchAllOrNothing:
    """[BEHAVIORAL] commit <fileA> <fileB> -- <message> where fileA matches
    its record but fileB does NOT (or has no snapshot) creates NO commit at
    all and stages NEITHER file -- fileA is not partially committed on its
    own. git rev-parse HEAD unchanged; both files' working-tree state
    unchanged. The printed results array contains an entry for both files,
    with fileB's entry carrying the mismatch diff/error."""

    def test_matching_file_not_partially_committed_when_sibling_mismatches(self, tmp_path, env):
        repo = tmp_path / "repo"
        _init_repo(repo)
        file_a = repo / "orchestrator.md"
        file_b = repo / "VERIFIER.md"
        _write(file_a, "baseline A\n")
        _write(file_b, "baseline B\n")
        _git(repo, "add", "orchestrator.md", "VERIFIER.md")
        _git(repo, "commit", "-m", "seed both")

        # fileA: reviewed and unchanged since -> would match.
        _write(file_a, "properly reviewed edit A\n")
        _run(["record", str(file_a)], env)

        # fileB: reviewed, then changed AGAIN afterward -> stale record.
        _write(file_b, "reviewed edit B\n")
        _run(["record", str(file_b)], env)
        _write(file_b, "reviewed edit B PLUS unreviewed extra content\n")

        head_before = _head(repo)
        status_before = _git(repo, "status", "--porcelain").stdout.strip()

        code, data, out, err = _run(
            ["commit", str(file_a), str(file_b), "--", "Should not land"], env,
        )

        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data["committed"] is False

        head_after = _head(repo)
        assert head_after == head_before, "no commit must be created (all-or-nothing)"

        status_after = _git(repo, "status", "--porcelain").stdout.strip()
        assert status_after == status_before, (
            "neither file may be staged, including the one that DID match; "
            f"before={status_before!r} after={status_after!r}"
        )
        assert "orchestrator.md" not in [
            line.split()[-1] for line in status_after.splitlines()
            if line.startswith("M ") or line.startswith("A ")
        ], "fileA (the matching one) must not show as staged"

        results = data["results"]
        assert len(results) == 2
        result_files = {r["file"] for r in results}
        assert result_files == {str(file_a), str(file_b)}

        b_result = next(r for r in results if r["file"] == str(file_b))
        assert b_result["match"] is False
        assert b_result.get("diff") or b_result.get("error"), (
            f"fileB's result entry must carry a diff or error, got: {b_result}"
        )

        a_result = next(r for r in results if r["file"] == str(file_a))
        assert a_result["match"] is True, (
            "fileA's own check result should still report match=true even "
            f"though the overall commit was blocked, got: {a_result}"
        )

    def test_missing_snapshot_on_second_file_blocks_entire_multi_file_commit(self, tmp_path, env):
        repo = tmp_path / "repo"
        _init_repo(repo)
        file_a = repo / "orchestrator.md"
        file_b = repo / "search_playbook.md"
        _write(file_a, "baseline A\n")
        _write(file_b, "baseline B\n")
        _git(repo, "add", "orchestrator.md", "search_playbook.md")
        _git(repo, "commit", "-m", "seed both")

        _write(file_a, "reviewed edit A\n")
        _run(["record", str(file_a)], env)

        _write(file_b, "edit B, never recorded at all\n")
        # fileB intentionally has NO record call.

        head_before = _head(repo)

        code, data, out, err = _run(
            ["commit", str(file_a), str(file_b), "--", "Should not land"], env,
        )

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data["committed"] is False
        assert _head(repo) == head_before

        status = _git(repo, "status", "--porcelain").stdout.strip()
        assert status != "", "both files must remain unstaged/modified"

        results = data["results"]
        b_result = next(r for r in results if r["file"] == str(file_b))
        assert b_result["match"] is False
        assert b_result.get("error") == "no_reviewed_snapshot"


# ---------------------------------------------------------------------------
# AC11 -- multi-file commit spanning two DIFFERENT repos: usage error, exit 2
# ---------------------------------------------------------------------------

class TestAC11DifferentReposUsageError:
    """[BEHAVIORAL] commit <fileA> <fileB> -- <message> where fileA and
    fileB resolve to DIFFERENT git repos (construct two separate throwaway
    repos as fixtures) exits 2 with a usage-error message and performs no
    git operations in either repo."""

    def test_files_in_two_different_repos_exits_2_no_git_ops(self, tmp_path, env):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        _init_repo(repo_a)
        _init_repo(repo_b)

        file_a = repo_a / "orchestrator.md"
        file_b = repo_b / "orchestrator.md"
        _write(file_a, "repo A content\n")
        _write(file_b, "repo B content\n")
        _git(repo_a, "add", "orchestrator.md")
        _git(repo_a, "commit", "-m", "seed A")
        _git(repo_b, "add", "orchestrator.md")
        _git(repo_b, "commit", "-m", "seed B")

        _write(file_a, "reviewed edit in repo A\n")
        _write(file_b, "reviewed edit in repo B\n")
        _run(["record", str(file_a)], env)
        _run(["record", str(file_b)], env)

        head_a_before = _head(repo_a)
        head_b_before = _head(repo_b)

        code, data, out, err = _run(
            ["commit", str(file_a), str(file_b), "--", "Cross-repo, should fail"],
            env,
        )

        assert code == 2, f"stdout={out!r} stderr={err!r}"

        assert _head(repo_a) == head_a_before, "no git op should touch repo A"
        assert _head(repo_b) == head_b_before, "no git op should touch repo B"

        status_a = _git(repo_a, "status", "--porcelain").stdout.strip()
        status_b = _git(repo_b, "status", "--porcelain").stdout.strip()
        assert status_a != "", "repo A file must remain modified/unstaged"
        assert status_b != "", "repo B file must remain modified/unstaged"
        # No staging in either repo (index unaffected -- a staged modification
        # shows as "M  f.txt" (X='M'); an untouched worktree edit shows as
        # " M f.txt" (X=' '). Use the RAW (non-stripped) porcelain line for
        # this check -- .strip() removes the leading space that carries the
        # staged-vs-unstaged signal, which would spuriously match "M " even
        # for a correct, unstaged-only edit.
        status_a_raw = _git(repo_a, "status", "--porcelain").stdout
        status_b_raw = _git(repo_b, "status", "--porcelain").stdout
        assert not status_a_raw.startswith("M "), status_a_raw
        assert not status_b_raw.startswith("M "), status_b_raw


# ---------------------------------------------------------------------------
# AC12 -- stale (>7d) snapshots are swept on the next record/check call
# ---------------------------------------------------------------------------

class TestAC12StaleSnapshotSweep:
    """[BEHAVIORAL] Snapshots older than 7 days are removed by the sweep on
    the next record/check call (construct a fixture with a mtime older than
    SWEEP_TTL_S and confirm it's gone after the next invocation touches the
    sweep path) -- sweep timing itself does not affect match/mismatch
    correctness, only directory hygiene; only assert "eventually swept on
    next invocation," not a specific cadence."""

    def test_stale_snapshot_removed_after_next_record_call(self, tmp_path, env, gate_dir):
        # Seed an unrelated file's snapshot directly (bypassing the CLI) so
        # we control its mtime precisely, then age it past the TTL.
        stale_file = tmp_path / "stale_target.md"
        _write(stale_file, "some old content\n")
        stale_abs = str(stale_file)

        code, data, *_ = _run(["record", stale_abs], env)
        assert code == 0
        stale_snap = _snapshot_path(gate_dir, stale_abs)
        assert os.path.exists(stale_snap)

        old_time = time.time() - SWEEP_TTL_S - 3600  # 1 hour past the TTL
        os.utime(stale_snap, (old_time, old_time))
        assert os.path.exists(stale_snap), "fixture setup sanity check"

        # A completely unrelated record call should trigger the opportunistic
        # sweep and remove the stale snapshot.
        other_file = tmp_path / "other_target.md"
        _write(other_file, "unrelated fresh content\n")
        code2, data2, out2, err2 = _run(["record", str(other_file)], env)
        assert code2 == 0, f"stdout={out2!r} stderr={err2!r}"

        assert not os.path.exists(stale_snap), (
            "a snapshot older than SWEEP_TTL_S must be swept by the next "
            "record/check invocation touching the sweep path"
        )

    def test_fresh_snapshot_survives_sweep(self, tmp_path, env, gate_dir):
        """Companion negative case: a snapshot well within the TTL must NOT
        be removed by the same sweep pass (guards against an over-eager
        sweep that deletes everything)."""
        fresh_file = tmp_path / "fresh_target.md"
        _write(fresh_file, "recently reviewed content\n")
        fresh_abs = str(fresh_file)
        _run(["record", fresh_abs], env)
        fresh_snap = _snapshot_path(gate_dir, fresh_abs)
        assert os.path.exists(fresh_snap)

        other_file = tmp_path / "trigger_sweep.md"
        _write(other_file, "trigger content\n")
        _run(["record", str(other_file)], env)

        assert os.path.exists(fresh_snap), (
            "a fresh (well within TTL) snapshot must survive the sweep pass"
        )

    def test_stale_snapshot_removed_after_next_check_call(self, tmp_path, env, gate_dir):
        """The sweep is documented to run on 'record/check' invocations --
        confirm a check call also triggers it, not only record."""
        stale_file = tmp_path / "stale_via_check.md"
        _write(stale_file, "old content for check-triggered sweep\n")
        stale_abs = str(stale_file)
        _run(["record", stale_abs], env)
        stale_snap = _snapshot_path(gate_dir, stale_abs)
        assert os.path.exists(stale_snap)

        old_time = time.time() - SWEEP_TTL_S - 3600
        os.utime(stale_snap, (old_time, old_time))

        # A check call on a DIFFERENT, unrelated file should still trigger
        # the opportunistic sweep pass over the whole reviewed/ dir.
        other_file = tmp_path / "unrelated_for_check_sweep.md"
        _write(other_file, "unrelated\n")
        _run(["record", str(other_file)], env)
        _run(["check", str(other_file)], env)

        assert not os.path.exists(stale_snap), (
            "check invocations must also trigger the opportunistic sweep"
        )
