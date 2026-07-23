"""Tests for full_history_scan.py -- the full-git-history PII/private-path
scanner that gates publishing 178 commits of local history to a public
GitHub repo.

THIS IS AC6 OF THE SPEC: the synthetic-repo proof harness. It is written
BEFORE the scanner implementation exists (Test-writer role, Tier 1). Every
test below is EXPECTED TO FAIL right now -- there is no
`harness/full_history_scan.py` yet -- and that failure must be a clear,
attributable assertion per test (see `_require_script` below), not a bare
collection error. The Coder implements `full_history_scan.py` to make these
tests pass; this file is the contract, not the other way around.

Context this test file assumes (from the approved plan-check spec):
  AC1 -- identity audit: every distinct author+committer email/name across
         all commits, cross-referenced against a marker file, producing a
         scan-time marker superset.
  AC4 -- independent tree-enumeration verification that `public/`,
         `loop-team/runs/`, `runs/` paths are absent from every commit
         (regex ^(public|loop-team/runs|runs)(/|$) against
         `git ls-tree -r <sha> --name-only` for every commit in
         `git rev-list --all`).
  AC5 -- binary- and gitlink-inclusive full-history PII scanner: iterates
         every commit via `git rev-list --all`, enumerates the full tree via
         `git ls-tree -r <sha>`, for every blob (mode 100644/100755/120000)
         reads RAW BYTES and regex-scans against a marker pattern set
         (identity strings from AC1 + a macOS home-directory prefix + an
         email + an API-key-shaped pattern like `sk-ant-api...`/
         `sk-proj-...`); for every gitlink entry (mode 160000) flags it
         explicitly for manual review (never auto-clears); explicitly scans
         `.gitmodules` blob content; fails LOUDLY (non-zero exit / raises) on
         any commit it cannot fully process rather than silently reporting 0
         hits.

===============================================================================
ASSUMED SCANNER CLI/INTERFACE CONTRACT (the Coder implements to match this)
===============================================================================

Script location (this test's SCRIPT constant):
    loop-team/harness/full_history_scan.py

Invocation:
    python3 full_history_scan.py \
        --repo <path-to-git-repo> \
        --markers-file <path-to-json-markers-file> \
        [--json-report <path-to-write-json-report>]

--repo <path>
    Path to a git repository (working copy or bare/mirror). The scanner
    must operate against `git rev-list --all` in this repo -- i.e. it must
    cover every ref (all branches), not just HEAD / first-parent history.

--markers-file <path>
    Path to a JSON file with this shape:
        {
          "identity_strings": ["Full Name", "name@example.com", ...],
          "extra_patterns": ["TESTMARKER_SHOULD_BE_FOUND", ...]
        }
    Both "identity_strings" and "extra_patterns" are treated as literal
    substrings OR regex fragments to scan for (implementation may compile
    them as escaped-literal alternation; tests here only rely on the marker
    string appearing verbatim in blob bytes being detected). In addition to
    whatever is supplied in this file, the scanner MUST ALSO always scan,
    unconditionally, for:
      - a macOS home-directory prefix pattern
      - an email-shaped pattern
      - an API-key-shaped pattern, e.g. `sk-ant-api` / `sk-proj-` prefixes
    (these are "always-on" built-in patterns per AC5; the markers file adds
    to, but does not replace, them).

--json-report <path> (optional)
    If given, the scanner writes a JSON report to this path with (at least)
    this shape:
        {
          "hits": [
            {
              "commit": "<full 40-char sha>",
              "path": "<path within tree, e.g. .gitmodules or secret/x.txt>",
              "pattern": "<the pattern/marker string that matched>",
              "mode": "100644"   # git tree entry mode, as a string
            },
            ...
          ],
          "gitlinks": [
            {
              "commit": "<full 40-char sha>",
              "path": "<path>",
              "sha": "<the 40-char gitlink target sha>"
            },
            ...
          ],
          "commits_scanned": <int>,
          "status": "clean" | "hits_found" | "incomplete"
        }
    "gitlinks" is ALWAYS populated (even zero-length list) whenever any
    mode-160000 tree entries exist anywhere in history -- gitlinks are
    reported separately from "hits" and are NEVER used to silently clear/
    downgrade a run to clean; their mere presence forces manual review.

Exit codes (this is the authoritative contract other AC5/AC6 tooling keys
off of):
    0  = clean: scan completed fully, zero PII/private-path/marker hits,
         AND zero gitlink entries encountered anywhere in `--all` history.
         (A gitlink present with zero string hits is NOT exit 0 -- see
         exit 1 case below -- because gitlinks always require manual
         review and must never be silently treated as clean.)
    1  = hits found: scan completed fully but found at least one marker/PII
         hit OR at least one gitlint (mode 160000) tree entry anywhere in
         `--all` history. The scan itself succeeded (did not crash/error);
         it just found something that blocks publishing.
    2  = scan could not complete: the scanner was unable to fully process
         some commit/blob/tree (e.g. `git cat-file` failed, a commit SHA
         could not be read, tree enumeration errored). This must be a loud,
         non-zero, clearly-labeled failure -- NEVER silently reported as
         "0 hits" / exit 0.

Stdout: the scanner should print the JSON report body to stdout (in
addition to optionally writing --json-report to disk) so it can be consumed
without requiring the optional flag. This test suite tolerates either
--json-report-only or stdout-only, but requires the JSON be obtainable via
at least one of the two channels every test needs it from -- concretely,
these tests always pass --json-report and read the file, since that is the
more conservative assumption; if the Coder ALSO prints valid JSON to stdout
that is fine, but not required by this test file.

Corrupted/unreadable commit simulation:
    Tests pass --repo pointing at a directory that IS a git repo but where
    a commit reachable from `git rev-list --all` cannot be fully read (we
    simulate this by pointing --repo at a path where `.git` has been
    corrupted just enough that `git cat-file` / `git ls-tree` on some
    known-reachable sha fails, OR by pointing --repo at a nonexistent /
    non-git directory as the simplest reliable trigger of "cannot process").
    In both cases the scanner must exit 2, not exit 0.

Run this file with:
    python3 -m pytest loop-team/harness/test_full_history_scan.py -q
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "full_history_scan.py")

GIT_CFG = [
    "-c", "user.email=test@example.com",
    "-c", "user.name=Test Writer",
    "-c", "commit.gpgsign=false",
]

EXIT_CLEAN = 0
EXIT_HITS = 1
EXIT_INCOMPLETE = 2

HOME_PREFIX = "/Use" + "rs/"
HOME_PATH_MARKER = HOME_PREFIX + "testuser/secret/path.txt"
MARKER_HISTORICAL = "TESTMARKER_SHOULD_BE_FOUND"
MARKER_SIDEBRANCH = "TESTMARKER_SIDEBRANCH_LEAK"
MARKER_BINARY = "TESTMARKER_BINARY_LEAK"
FAKE_SUBMODULE_URL_LEAK = HOME_PREFIX + "testuser/some/local/repo"
FAKE_GITLINK_SHA = "a" * 40  # syntactically valid 40-hex-char sha, no object needed


def _script_exists():
    return os.path.isfile(SCRIPT)


def _require_script():
    """Fail loudly (not skip) when full_history_scan.py doesn't exist yet.

    Per Test-writer convention in this harness (see test_reconcile_gap_records.py,
    test_commit_diff_reread.py): a missing implementation must fail each test
    with an attributable assertion, not silently skip -- a skip would
    understate how much of AC5/AC6 is currently unmet.
    """
    if not _script_exists():
        raise AssertionError(
            "harness/full_history_scan.py does not exist yet (expected to "
            "fail until the Coder delivers it). Expected CLI: "
            "python3 full_history_scan.py --repo <path> --markers-file "
            "<path> [--json-report <path>]"
        )


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _git(repo_dir, *args, check=True):
    return subprocess.run(
        ["git"] + GIT_CFG + list(args), cwd=str(repo_dir),
        check=check, capture_output=True, text=True,
    )


def _write_text(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _commit_all(repo_dir, message):
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", message)
    return _git(repo_dir, "rev-parse", "HEAD").stdout.strip()


def _init_repo(repo_dir):
    repo_dir = str(repo_dir)
    os.makedirs(repo_dir, exist_ok=True)
    _git(repo_dir, "init")
    return repo_dir


def _write_markers_file(path, identity_strings=None, extra_patterns=None):
    payload = {
        "identity_strings": identity_strings or [],
        "extra_patterns": extra_patterns or [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return str(path)


def _run_scanner(repo, markers_file, json_report_path, timeout=60):
    """Invoke the real CLI. Returns (exit_code, report_dict_or_None, stdout, stderr)."""
    args = [
        sys.executable, SCRIPT,
        "--repo", str(repo),
        "--markers-file", str(markers_file),
        "--json-report", str(json_report_path),
    ]
    p = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout,
    )
    report = None
    if os.path.exists(json_report_path):
        try:
            with open(json_report_path) as f:
                report = json.load(f)
        except (json.JSONDecodeError, ValueError):
            report = None
    if report is None:
        try:
            report = json.loads(p.stdout)
        except (json.JSONDecodeError, ValueError):
            report = None
    return p.returncode, report, p.stdout, p.stderr


def _all_hit_patterns(report):
    return {h.get("pattern") for h in (report or {}).get("hits", [])}


def _all_hit_commits(report):
    return {h.get("commit") for h in (report or {}).get("hits", [])}


# ---------------------------------------------------------------------------
# (a) Historical leak, fixed in a later commit on the same branch --
#     must still be caught because it's in HISTORY, not just HEAD.
# ---------------------------------------------------------------------------

class TestACaHistoricalLeakCaughtEvenAfterFix:
    """[BEHAVIORAL] A fake home path + fake marker string committed, then
    removed ("fixed") in a follow-up commit on the SAME branch. HEAD is
    clean; the scanner must still find the leak somewhere in history."""

    def test_historical_leak_found_despite_later_fix_at_head(self, tmp_path):
        _require_script()
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_text(repo / "README.md", "hello\n")
        _commit_all(repo, "init")

        leak_file = repo / "secret" / "path.txt"
        _write_text(
            leak_file,
            "leaked home path: %s\nmarker: %s\n" % (HOME_PATH_MARKER, MARKER_HISTORICAL),
        )
        leak_sha = _commit_all(repo, "oops, added a secret path")

        # "Fix": remove the leaking content entirely on the same branch.
        _write_text(leak_file, "nothing to see here\n")
        fix_sha = _commit_all(repo, "fix: remove secret path")

        # Sanity: HEAD (the fix commit) must NOT contain the marker string.
        head_show = _git(repo, "show", "HEAD:secret/path.txt").stdout
        assert MARKER_HISTORICAL not in head_show, "fixture setup: HEAD must be clean"

        markers = _write_markers_file(
            tmp_path / "markers.json", extra_patterns=[MARKER_HISTORICAL]
        )
        code, report, out, err = _run_scanner(
            repo, markers, tmp_path / "report.json"
        )

        assert code == EXIT_HITS, (
            f"expected exit {EXIT_HITS} (hits found) since a historical "
            f"commit leaks {MARKER_HISTORICAL!r}; got {code}. "
            f"stdout={out!r} stderr={err!r}"
        )
        assert report is not None, f"stdout={out!r} stderr={err!r}"
        assert MARKER_HISTORICAL in _all_hit_patterns(report), (
            f"scanner must report a hit for {MARKER_HISTORICAL!r}; "
            f"hits={report.get('hits')}"
        )
        assert leak_sha in _all_hit_commits(report), (
            "the hit must be attributed to the ORIGINAL leaking commit "
            f"({leak_sha}), not just HEAD ({fix_sha}); "
            f"hit commits={_all_hit_commits(report)}"
        )
        assert fix_sha != leak_sha  # sanity: these are genuinely different commits


# ---------------------------------------------------------------------------
# (b) Merge-commit topology: side-branch-only leak, merged then deleted on
#     main -- must be found via full --all coverage, not first-parent only.
# ---------------------------------------------------------------------------

class TestACbSideBranchLeakFoundViaFullHistoryCoverage:
    """[BEHAVIORAL] A DIFFERENT marker committed only on a side branch, then
    merged into main, then the leaking file deleted in a later commit on
    main. The scanner must still find the side-branch marker via `--all`
    (every commit reachable from any ref), proving it doesn't rely on
    first-parent-only traversal."""

    def test_sidebranch_marker_found_after_merge_and_deletion(self, tmp_path):
        _require_script()
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_text(repo / "README.md", "hello\n")
        _commit_all(repo, "init")
        _git(repo, "branch", "-M", "main")

        _git(repo, "checkout", "-b", "side-branch")
        side_leak_file = repo / "sidebranch_leak.txt"
        _write_text(side_leak_file, "leak: %s\n" % MARKER_SIDEBRANCH)
        side_sha = _commit_all(repo, "side branch: add leaking file")

        _git(repo, "checkout", "main")
        _git(
            repo, "merge", "--no-ff", "side-branch",
            "-m", "merge side-branch into main",
        )
        merge_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

        # Delete the leaking file in a commit AFTER the merge, on main.
        _git(repo, "rm", "sidebranch_leak.txt")
        _git(repo, "commit", "-m", "remove leaked file post-merge")
        post_delete_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

        # Sanity: HEAD must not contain the file/marker at all.
        ls = _git(repo, "ls-tree", "-r", "HEAD", "--name-only").stdout
        assert "sidebranch_leak.txt" not in ls, "fixture setup: HEAD must not have the file"

        # Sanity: `git log --first-parent main` must NOT include side_sha's
        # own commit as a first-parent ancestor content-check target in the
        # naive sense -- side_sha is only reachable via the merge's second
        # parent. (We don't assert on log output directly; this comment
        # documents WHY --all coverage matters for this fixture.)

        markers = _write_markers_file(
            tmp_path / "markers.json", extra_patterns=[MARKER_SIDEBRANCH]
        )
        code, report, out, err = _run_scanner(
            repo, markers, tmp_path / "report.json"
        )

        assert code == EXIT_HITS, f"stdout={out!r} stderr={err!r}"
        assert report is not None, f"stdout={out!r} stderr={err!r}"
        assert MARKER_SIDEBRANCH in _all_hit_patterns(report), (
            f"scanner must find {MARKER_SIDEBRANCH!r} which only ever "
            f"existed on the side branch; hits={report.get('hits')}"
        )
        hit_commits = _all_hit_commits(report)
        assert side_sha in hit_commits or merge_sha in hit_commits, (
            "the hit must be attributable to the side-branch commit (or "
            f"the merge commit's tree) -- side_sha={side_sha} "
            f"merge_sha={merge_sha} hit_commits={hit_commits}"
        )
        assert post_delete_sha not in hit_commits or True  # deletion commit's tree is clean; not a strict requirement


# ---------------------------------------------------------------------------
# (c) Binary blob with an embedded marker string in raw bytes.
# ---------------------------------------------------------------------------

class TestACcBinaryBlobLeakFoundViaRawByteScan:
    """[BEHAVIORAL] A binary file (non-UTF8 bytes) with an embedded fake
    marker string somewhere in its byte content, committed as a tracked
    blob, must be found by the scanner despite being non-text content --
    proving the scanner reads RAW BYTES, not text-mode-only."""

    def test_binary_blob_with_embedded_marker_is_found(self, tmp_path):
        _require_script()
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_text(repo / "README.md", "hello\n")
        _commit_all(repo, "init")

        # Arbitrary non-UTF8 byte content (all 256 byte values), with the
        # marker string embedded in the middle so a naive text-decode
        # (which would raise/skip on invalid UTF-8) cannot find it, but a
        # raw-byte regex scan can.
        binary_payload = bytes(range(256)) + MARKER_BINARY.encode("ascii") + bytes(range(255, -1, -1))
        binary_path = repo / "assets" / "blob.bin"
        _write_bytes(binary_path, binary_payload)
        bin_sha = _commit_all(repo, "add binary asset with embedded marker")

        # Sanity: confirm this content is NOT valid UTF-8 (i.e. genuinely binary).
        with pytest.raises(UnicodeDecodeError):
            binary_payload.decode("utf-8")

        markers = _write_markers_file(
            tmp_path / "markers.json", extra_patterns=[MARKER_BINARY]
        )
        code, report, out, err = _run_scanner(
            repo, markers, tmp_path / "report.json"
        )

        assert code == EXIT_HITS, f"stdout={out!r} stderr={err!r}"
        assert report is not None, f"stdout={out!r} stderr={err!r}"
        assert MARKER_BINARY in _all_hit_patterns(report), (
            f"scanner must find {MARKER_BINARY!r} embedded in raw binary "
            f"bytes; hits={report.get('hits')}"
        )
        assert bin_sha in _all_hit_commits(report)
        hit_paths = {h.get("path") for h in report.get("hits", [])}
        assert any("blob.bin" in (p or "") for p in hit_paths), (
            f"hit must be attributed to assets/blob.bin; paths={hit_paths}"
        )


# ---------------------------------------------------------------------------
# (d) Gitlink (mode 160000) tree entry + .gitmodules with a leaking URL.
# ---------------------------------------------------------------------------

class TestACdGitlinkFlaggedAndGitmodulesUrlFound:
    """[BEHAVIORAL] A .gitmodules file whose submodule URL contains a fake
    leaking local path, AND an actual gitlink tree entry (mode 160000)
    created via `git update-index --add --cacheinfo 160000,<fake sha>,path`
    (no real submodule needs to exist). The scanner must (i) explicitly
    flag the gitlink for manual review -- never silently skip or auto-clear
    it -- and (ii) find the leaking URL string inside .gitmodules via the
    normal byte-scan."""

    def test_gitlink_is_flagged_and_never_silently_cleared(self, tmp_path):
        _require_script()
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_text(repo / "README.md", "hello\n")
        _commit_all(repo, "init")

        gitmodules_content = (
            '[submodule "fake-submodule"]\n'
            "\tpath = path/to/fake-submodule\n"
            "\turl = %s\n" % FAKE_SUBMODULE_URL_LEAK
        )
        _write_text(repo / ".gitmodules", gitmodules_content)
        _git(repo, "add", ".gitmodules")

        # Create an actual gitlink tree entry (mode 160000) without a real
        # submodule needing to exist -- update-index accepts a syntactically
        # valid 40-hex-char sha directly.
        os.makedirs(str(repo / "path" / "to"), exist_ok=True)
        _git(
            repo, "update-index", "--add", "--cacheinfo",
            "160000,%s,path/to/fake-submodule" % FAKE_GITLINK_SHA,
        )
        _git(repo, "commit", "-m", "add gitlink + leaking .gitmodules")
        gitlink_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

        # Sanity: confirm the gitlink tree entry actually exists with mode 160000.
        ls_full = _git(repo, "ls-tree", "-r", "HEAD").stdout
        assert "160000" in ls_full and "path/to/fake-submodule" in ls_full, (
            f"fixture setup: expected a mode-160000 gitlink entry; "
            f"ls-tree output={ls_full!r}"
        )

        markers = _write_markers_file(
            tmp_path / "markers.json", extra_patterns=[FAKE_SUBMODULE_URL_LEAK]
        )
        code, report, out, err = _run_scanner(
            repo, markers, tmp_path / "report.json"
        )

        # A gitlink present anywhere in --all history is never exit-0-clean.
        assert code == EXIT_HITS, (
            f"a gitlink entry must force a non-clean (exit {EXIT_HITS}) "
            f"result -- never silently exit 0; got {code}. "
            f"stdout={out!r} stderr={err!r}"
        )
        assert report is not None, f"stdout={out!r} stderr={err!r}"

        gitlinks = report.get("gitlinks", [])
        assert gitlinks, (
            "scanner must explicitly list the gitlink entry under "
            f"'gitlinks' for manual review, got: {gitlinks!r}"
        )
        matching = [g for g in gitlinks if g.get("path") == "path/to/fake-submodule"]
        assert matching, (
            "the specific gitlink path 'path/to/fake-submodule' must appear "
            f"in the report's gitlinks list; got: {gitlinks!r}"
        )
        assert matching[0].get("commit") == gitlink_sha
        assert matching[0].get("sha") == FAKE_GITLINK_SHA, (
            "the reported gitlink target sha must be the real target sha "
            f"from the tree entry ({FAKE_GITLINK_SHA}), not blank/omitted"
        )

        # The .gitmodules URL leak must ALSO be found via the normal byte-scan.
        assert FAKE_SUBMODULE_URL_LEAK in _all_hit_patterns(report), (
            "scanner must find the leaking submodule URL string via its "
            f"normal .gitmodules byte-scan; hits={report.get('hits')}"
        )
        gitmodules_hits = [
            h for h in report.get("hits", [])
            if h.get("path") == ".gitmodules"
        ]
        assert gitmodules_hits, (
            ".gitmodules must be explicitly scanned and produce a hit "
            f"entry with path == '.gitmodules'; hits={report.get('hits')}"
        )

    def test_gitlink_alone_with_no_string_hits_is_not_exit_0(self, tmp_path):
        """A gitlink with NO markers-file match anywhere else in the repo
        must still not be exit 0 -- gitlinks always require manual review
        regardless of whether any string pattern also happens to match."""
        _require_script()
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_text(repo / "README.md", "totally benign content\n")
        _commit_all(repo, "init")

        _git(
            repo, "update-index", "--add", "--cacheinfo",
            "160000,%s,vendor/some-lib" % FAKE_GITLINK_SHA,
        )
        _git(repo, "commit", "-m", "add gitlink only, no other leaks")

        markers = _write_markers_file(tmp_path / "markers.json")  # no extra patterns
        code, report, out, err = _run_scanner(
            repo, markers, tmp_path / "report.json"
        )

        assert code != EXIT_CLEAN, (
            "a gitlink entry alone (even with zero string-pattern hits) "
            f"must never yield a clean exit-0 result; got {code}. "
            f"stdout={out!r} stderr={err!r}"
        )
        assert report is not None
        assert report.get("gitlinks"), (
            f"gitlink must still be reported; report={report!r}"
        )


# ---------------------------------------------------------------------------
# Failure mode: a genuinely unreadable/corrupted commit must fail LOUDLY.
# ---------------------------------------------------------------------------

class TestFailureModeUnreadableCommitFailsLoudly:
    """[BEHAVIORAL] A repo the scanner cannot fully process (simulated via a
    corrupted/missing git object reachable from `--all`, or a bogus/
    non-existent --repo path as the simplest reliable trigger) must cause
    the scanner to fail LOUDLY: exit code 2 (per this contract) or a raised
    exception surfaced as a non-zero exit with a clear message. It must
    NEVER print a '0 hits' / clean report and exit 0."""

    def test_nonexistent_repo_path_exits_2_not_0(self, tmp_path):
        _require_script()
        bogus_repo = tmp_path / "this_repo_does_not_exist"
        markers = _write_markers_file(tmp_path / "markers.json")

        code, report, out, err = _run_scanner(
            bogus_repo, markers, tmp_path / "report.json"
        )

        assert code == EXIT_INCOMPLETE, (
            f"a nonexistent --repo path must exit {EXIT_INCOMPLETE} "
            f"(scan could not complete), not silently succeed; got {code}. "
            f"stdout={out!r} stderr={err!r}"
        )
        assert code != EXIT_CLEAN
        if report is not None:
            assert report.get("status") != "clean", (
                f"must not report status=clean for an unreadable repo; "
                f"report={report!r}"
            )

    def test_corrupted_git_object_exits_2_not_0_with_zero_hits(self, tmp_path):
        """Simulate a commit git cannot read: corrupt an object file for a
        commit that IS reachable from `git rev-list --all`, so the scanner
        must fail loudly rather than silently skip it and report clean."""
        _require_script()
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_text(repo / "README.md", "hello\n")
        first_sha = _commit_all(repo, "init")
        _write_text(repo / "file2.txt", "more content\n")
        second_sha = _commit_all(repo, "second commit")

        # Corrupt the loose object file for the commit itself (or its tree),
        # so `git cat-file` / `git ls-tree` on it will error. This directly
        # simulates "a commit it cannot fully process."
        def _object_path(sha):
            return repo / ".git" / "objects" / sha[:2] / sha[2:]

        commit_obj_path = _object_path(second_sha)
        if not commit_obj_path.exists():
            # Some git versions may pack it immediately; force loose storage.
            _git(repo, "repack", "-a", "-d", check=False)
        target_path = commit_obj_path if commit_obj_path.exists() else None

        if target_path is None:
            pytest.skip(
                "could not isolate a loose object file to corrupt on this "
                "git version/config -- fixture environment limitation, not "
                "a scanner behavior question"
            )

        # Truncate/corrupt the zlib-compressed object content.
        # Git creates loose object files read-only (mode 0444) by default;
        # make it writable first so the corruption write below can succeed.
        os.chmod(target_path, 0o644)
        with open(target_path, "wb") as f:
            f.write(b"not a valid git object")

        markers = _write_markers_file(tmp_path / "markers.json")
        code, report, out, err = _run_scanner(
            repo, markers, tmp_path / "report.json"
        )

        assert code == EXIT_INCOMPLETE, (
            f"a corrupted, unreadable commit object reachable from "
            f"`git rev-list --all` must cause exit {EXIT_INCOMPLETE}, "
            f"never a silent success; got {code}. first_sha={first_sha} "
            f"second_sha={second_sha} stdout={out!r} stderr={err!r}"
        )
        if report is not None:
            assert report.get("status") != "clean"
            assert report.get("hits", None) != [] or report.get("status") == "incomplete", (
                "must not silently report an empty hits list with a clean-"
                f"looking status when a commit could not be processed; "
                f"report={report!r}"
            )


# ---------------------------------------------------------------------------
# True-negative control: a clean repo with none of the seeded leaks must
# report zero hits -- guards against an overly-aggressive scanner.
# ---------------------------------------------------------------------------

class TestTrueNegativeCleanRepoReportsZeroHits:
    """[BEHAVIORAL] A synthetic repo with NONE of the seeded leak patterns
    anywhere in its history must report zero hits and exit 0 -- this is the
    control case guarding against a scanner so aggressive it flags
    everything (e.g. matching on substrings of the word 'user', or
    mis-detecting ordinary binary files as leaks)."""

    def test_clean_repo_multi_commit_multi_branch_reports_zero_hits(self, tmp_path):
        _require_script()
        repo = tmp_path / "repo"
        _init_repo(repo)
        _write_text(repo / "README.md", "A perfectly ordinary project.\n")
        _commit_all(repo, "init")
        _git(repo, "branch", "-M", "main")

        _write_text(repo / "src" / "app.py", "def main():\n    return 42\n")
        _commit_all(repo, "add app.py")

        _git(repo, "checkout", "-b", "feature-x")
        _write_text(repo / "src" / "feature.py", "VALUE = 'benign_constant'\n")
        _commit_all(repo, "add feature.py on feature-x")
        _git(repo, "checkout", "main")
        _git(repo, "merge", "--no-ff", "feature-x", "-m", "merge feature-x")

        ordinary_binary = bytes(range(256))  # no marker embedded anywhere
        _write_bytes(repo / "assets" / "ordinary.bin", ordinary_binary)
        _commit_all(repo, "add ordinary binary asset")

        markers = _write_markers_file(
            tmp_path / "markers.json",
            identity_strings=["Nobody Real", "nobody-real@example.invalid"],
            extra_patterns=["TESTMARKER_SHOULD_NEVER_APPEAR_XYZ"],
        )
        code, report, out, err = _run_scanner(
            repo, markers, tmp_path / "report.json"
        )

        assert code == EXIT_CLEAN, (
            f"a genuinely clean repo must exit {EXIT_CLEAN}; got {code}. "
            f"stdout={out!r} stderr={err!r} report={report!r}"
        )
        assert report is not None, f"stdout={out!r} stderr={err!r}"
        assert report.get("hits", None) == [], (
            f"expected zero hits on a clean repo, got: {report.get('hits')}"
        )
        assert report.get("gitlinks", None) == [], (
            f"expected zero gitlinks on a repo with none seeded, got: "
            f"{report.get('gitlinks')}"
        )
        assert report.get("status") == "clean", (
            f"expected status == 'clean', got: {report.get('status')!r}"
        )
        assert report.get("commits_scanned", 0) >= 4, (
            "sanity: the scanner should report having scanned all the "
            f"commits in this multi-branch history; report={report!r}"
        )


# ---------------------------------------------------------------------------
# Interface sanity: the script exists and exposes the documented CLI shape.
# (Kept minimal and last -- the behavioral tests above are the real proof.)
# ---------------------------------------------------------------------------

class TestScannerCliShapeSanity:
    def test_script_file_exists(self):
        assert _script_exists(), (
            f"expected the scanner CLI at {SCRIPT} (per this test file's "
            "documented interface contract); it does not exist yet"
        )

    def test_script_supports_documented_flags_without_crashing_on_help(self):
        _require_script()
        p = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        combined = (p.stdout + p.stderr).lower()
        assert "--repo" in combined
        assert "--markers-file" in combined
