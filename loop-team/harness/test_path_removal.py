"""Tests for the history-rewrite ("remover") step that strips `public/` and
`runs/` paths from every commit before the 178-commit history is published,
using `git filter-repo`.

SCOPE NOTE: AC6 (this dispatch's assignment) is specifically about the
SCANNER's synthetic-repo proof (see test_full_history_scan.py). This file is
a SEPARATE, second test file for the companion remover step (AC2/AC3/AC4:
clone --mirror, filter-repo --invert-paths, then independent tree-
enumeration verification) -- written because that remover deserves its own
proof independent of the scanner, per the dispatch instructions' explicit
"scope check" callout. It reuses the same AC4 tree-enumeration regex the
scanner harness documents, applied here as a POST-CONDITION check on the
filtered repo rather than as the thing under test in test_full_history_scan.py.

===============================================================================
ASSUMED REMOVER INTERFACE / EXACT COMMAND SEQUENCE (the Coder wires to this)
===============================================================================

This test does not assume a bespoke CLI for the remover step -- it directly
documents and drives the exact `git` + `git filter-repo` command sequence
the real remover tooling must reproduce, since AC2/AC3/AC4 describe a
clone -> filter-repo -> verify pipeline built on standard tools rather than
a new bespoke script. If the Coder DOES wrap this in a script (e.g.
`loop-team/harness/path_removal.py --repo <src> --dest <dest>`), that
script's behavior must still satisfy the assertions below when driven via
the same three-stage pipeline; this test drives the pipeline directly via
subprocess so it has no dependency on that wrapper existing.

Stage 1 -- mirror clone (AC2):
    git clone --mirror <source-repo> <mirror-dest>

Stage 2 -- filter-repo invocation (AC3), run inside the mirror clone:
    git filter-repo --path public/ --path runs/ --invert-paths --force
  (--force is required because filter-repo refuses to run on a repo it
  doesn't recognize as a fresh clone by default when re-run; a mirror
  clone made fresh in a tmp_path fixture does not strictly require --force,
  but tests here pass it for robustness across filter-repo versions.)

  NOTE ON PATH SEMANTICS: the spec's regex target is
      ^(public|loop-team/runs|runs)(/|+)$
  i.e. THREE distinct path roots: `public/`, `loop-team/runs/`, and a
  top-level `runs/`. This test file's fixture repo seeds paths under all
  three roots (`public/foo.html`, `runs/bar.log`, and
  `loop-team/runs/baz.txt`) and the filter-repo invocation documented here
  passes all three as separate --path arguments:
      git filter-repo --path public/ --path runs/ --path loop-team/runs/ \\
          --invert-paths --force

Stage 3 -- independent tree-enumeration verification (AC4), run against the
filtered result for EVERY commit in `git rev-list --all`:
    for sha in $(git rev-list --all):
        git ls-tree -r <sha> --name-only
        assert no line matches ^(public|loop-team/runs|runs)(/|$)

This test file implements stage 3 itself in Python (see `_paths_matching_
removed_roots`) as the "independent" check -- i.e. it does NOT trust
filter-repo's own exit code alone; it re-walks history and re-greps paths.

Run with:
    python3 -m pytest loop-team/harness/test_path_removal.py -q
"""
import os
import re
import shutil
import subprocess

import pytest

GIT_CFG = [
    "-c", "user.email=test@example.com",
    "-c", "user.name=Test Writer",
    "-c", "commit.gpgsign=false",
]

REMOVED_ROOTS_RE = re.compile(r"^(public|loop-team/runs|runs)(/|$)")


def _filter_repo_available():
    return shutil.which("git-filter-repo") is not None or _has_filter_repo_subcommand()


def _has_filter_repo_subcommand():
    p = subprocess.run(
        ["git", "filter-repo", "--help"],
        capture_output=True, text=True,
    )
    return p.returncode == 0


def _require_filter_repo():
    if not _filter_repo_available():
        pytest.skip(
            "git-filter-repo is not installed in this environment; the "
            "remover step depends on it. This is an environment "
            "precondition, not a scanner/remover behavior question -- "
            "install with `pip install git-filter-repo` or "
            "`brew install git-filter-repo` to run this suite."
        )


def _git(repo_dir, *args, check=True):
    return subprocess.run(
        ["git"] + GIT_CFG + list(args), cwd=str(repo_dir),
        check=check, capture_output=True, text=True,
    )


def _write_text(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _commit_all(repo_dir, message):
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", message)
    return _git(repo_dir, "rev-parse", "HEAD").stdout.strip()


def _init_repo(repo_dir):
    repo_dir = str(repo_dir)
    os.makedirs(repo_dir, exist_ok=True)
    _git(repo_dir, "init")
    return repo_dir


def _rev_list_all(repo_dir):
    out = _git(repo_dir, "rev-list", "--all").stdout.strip()
    return [line for line in out.splitlines() if line]


def _ls_tree_paths(repo_dir, sha):
    out = _git(repo_dir, "ls-tree", "-r", sha, "--name-only").stdout
    return [line for line in out.splitlines() if line]


def _paths_matching_removed_roots(repo_dir, sha):
    """The independent AC4 check: re-walk this commit's tree and re-grep it
    against the removed-roots regex, rather than trusting filter-repo's own
    reported success."""
    return [p for p in _ls_tree_paths(repo_dir, sha) if REMOVED_ROOTS_RE.match(p)]


def _seed_repo_with_public_and_runs_paths(repo_dir):
    """Seed a synthetic repo across multiple commits with content under all
    three path roots the spec's regex targets: `public/`, top-level `runs/`,
    and `loop-team/runs/` -- plus ordinary content that must SURVIVE the
    filter (a negative control against over-aggressive removal)."""
    _init_repo(repo_dir)

    _write_text(repo_dir / "README.md", "an ordinary project\n")
    _write_text(repo_dir / "src" / "main.py", "print('hello')\n")
    first_sha = _commit_all(repo_dir, "init with ordinary content")

    _write_text(repo_dir / "public" / "foo.html", "<html>leak-ish public asset</html>\n")
    _write_text(repo_dir / "runs" / "bar.log", "top-level runs/ log leak\n")
    second_sha = _commit_all(repo_dir, "add public/ and runs/ content")

    _write_text(
        repo_dir / "loop-team" / "runs" / "baz.txt",
        "loop-team/runs/ nested content, also must be removed\n",
    )
    _write_text(repo_dir / "docs" / "guide.md", "ordinary docs, must survive\n")
    third_sha = _commit_all(repo_dir, "add loop-team/runs/ and more ordinary docs")

    # A LATER commit that itself deletes public/foo.html on its own -- this
    # proves the remover must scrub HISTORY (earlier commits' trees), not
    # just rely on a later deletion already having happened at HEAD.
    _git(repo_dir, "rm", "public/foo.html")
    _commit_all(repo_dir, "author already deleted public/foo.html at head")

    return {
        "first_sha": first_sha,
        "second_sha": second_sha,
        "third_sha": third_sha,
    }


def _clone_mirror(source_repo, dest_dir):
    subprocess.run(
        ["git", "clone", "--mirror", str(source_repo), str(dest_dir)],
        check=True, capture_output=True, text=True,
    )
    return str(dest_dir)


def _run_filter_repo(mirror_repo_dir, paths_to_remove):
    args = ["git", "filter-repo"]
    for p in paths_to_remove:
        args += ["--path", p]
    args += ["--invert-paths", "--force"]
    return subprocess.run(
        args, cwd=str(mirror_repo_dir),
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# AC2 -- mirror clone succeeds and preserves full --all history up front
# ---------------------------------------------------------------------------

class TestAC2MirrorCloneCapturesFullHistory:
    """[BEHAVIORAL] `git clone --mirror` of the synthetic source repo
    produces a destination repo whose `git rev-list --all` contains every
    commit from the source (nothing silently dropped before filtering even
    begins)."""

    def test_mirror_clone_has_same_commit_set_as_source(self, tmp_path):
        source = tmp_path / "source"
        _seed_repo_with_public_and_runs_paths(source)
        source_commits = set(_rev_list_all(source))

        mirror = tmp_path / "mirror.git"
        _clone_mirror(source, mirror)
        mirror_commits = set(_rev_list_all(mirror))

        assert mirror_commits == source_commits, (
            "mirror clone must preserve the exact same commit set as the "
            f"source; source={source_commits} mirror={mirror_commits}"
        )
        assert len(mirror_commits) >= 4


# ---------------------------------------------------------------------------
# AC3 -- filter-repo --invert-paths actually removes the targeted paths
# ---------------------------------------------------------------------------

class TestAC3FilterRepoInvertPathsRemovesTargetedRoots:
    """[BEHAVIORAL] Running the documented `git filter-repo --path public/
    --path runs/ --path loop-team/runs/ --invert-paths --force` against the
    mirrored clone removes those paths from EVERY commit's tree (not just
    HEAD), while leaving ordinary/unrelated content intact."""

    def test_filter_repo_runs_successfully(self, tmp_path):
        _require_filter_repo()
        source = tmp_path / "source"
        _seed_repo_with_public_and_runs_paths(source)
        mirror = tmp_path / "mirror.git"
        _clone_mirror(source, mirror)

        result = _run_filter_repo(mirror, ["public/", "runs/", "loop-team/runs/"])
        assert result.returncode == 0, (
            f"git filter-repo must exit 0 on this fixture; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_ordinary_unrelated_content_survives_in_every_commit(self, tmp_path):
        """Negative control: filtering must not be so aggressive that it
        drops unrelated content (e.g. README.md, src/main.py, docs/guide.md)
        anywhere it validly appears."""
        _require_filter_repo()
        source = tmp_path / "source"
        _seed_repo_with_public_and_runs_paths(source)
        mirror = tmp_path / "mirror.git"
        _clone_mirror(source, mirror)
        _run_filter_repo(mirror, ["public/", "runs/", "loop-team/runs/"])

        all_commits = _rev_list_all(mirror)
        assert all_commits, "filtered repo must still have commits"

        head_paths = set(_ls_tree_paths(mirror, all_commits[0]))
        assert "README.md" in head_paths or any(
            "README.md" in _ls_tree_paths(mirror, sha) for sha in all_commits
        ), "README.md must survive filtering somewhere in history"

        found_main_py = any(
            "src/main.py" in _ls_tree_paths(mirror, sha) for sha in all_commits
        )
        found_guide_md = any(
            "docs/guide.md" in _ls_tree_paths(mirror, sha) for sha in all_commits
        )
        assert found_main_py, "src/main.py must survive filtering somewhere in history"
        assert found_guide_md, "docs/guide.md must survive filtering somewhere in history"


# ---------------------------------------------------------------------------
# AC4 -- independent tree-enumeration verification: zero matches, every commit
# ---------------------------------------------------------------------------

class TestAC4IndependentTreeEnumerationVerification:
    """[BEHAVIORAL] After filter-repo, an INDEPENDENT re-walk of every commit
    in `git rev-list --all` via `git ls-tree -r <sha> --name-only`, re-grepped
    against ^(public|loop-team/runs|runs)(/|$), must show ZERO matches --
    across every commit, not just HEAD. This re-implements the check from
    scratch rather than trusting filter-repo's own success/failure signal."""

    def test_zero_matches_for_removed_roots_across_all_history(self, tmp_path):
        _require_filter_repo()
        source = tmp_path / "source"
        shas = _seed_repo_with_public_and_runs_paths(source)
        mirror = tmp_path / "mirror.git"
        _clone_mirror(source, mirror)

        # Sanity: BEFORE filtering, the offending paths really are present
        # somewhere in history (guards against a vacuously-true test).
        pre_filter_matches = []
        for sha in _rev_list_all(mirror):
            pre_filter_matches.extend(_paths_matching_removed_roots(mirror, sha))
        assert pre_filter_matches, (
            "fixture setup: expected at least one public/ or runs/ path "
            "somewhere in pre-filter history"
        )

        result = _run_filter_repo(mirror, ["public/", "runs/", "loop-team/runs/"])
        assert result.returncode == 0, (
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        all_matches = []
        all_commits = _rev_list_all(mirror)
        assert all_commits, "filtered repo must still have a non-empty history"
        for sha in all_commits:
            matches = _paths_matching_removed_roots(mirror, sha)
            if matches:
                all_matches.append((sha, matches))

        assert all_matches == [], (
            "independent tree-enumeration verification found leftover "
            f"public/runs paths after filtering: {all_matches!r}"
        )

    def test_rewritten_history_commit_that_predeleted_public_is_also_clean(self, tmp_path):
        """The commit that itself already deleted public/foo.html BEFORE
        filtering must also be clean afterward (it should have been clean
        of public/ already at that point, but this guards against
        filter-repo somehow reintroducing/mismapping paths across rewritten
        history)."""
        _require_filter_repo()
        source = tmp_path / "source"
        _seed_repo_with_public_and_runs_paths(source)
        mirror = tmp_path / "mirror.git"
        _clone_mirror(source, mirror)
        _run_filter_repo(mirror, ["public/", "runs/", "loop-team/runs/"])

        all_commits = _rev_list_all(mirror)
        head_matches = _paths_matching_removed_roots(mirror, all_commits[0])
        assert head_matches == [], (
            f"HEAD-equivalent commit must have zero removed-root matches; "
            f"got {head_matches!r}"
        )

    def test_partial_path_name_collision_is_not_falsely_removed(self, tmp_path):
        """Negative control for the regex anchoring itself: a path like
        `runsomething/file.txt` or `public-assets/file.txt` (NOT actually
        under the `runs/` or `public/` root) must NOT be caught by the
        ^(public|loop-team/runs|runs)(/|$) regex, proving the anchor is
        exact-segment, not a loose substring match. This test checks the
        regex directly (the same one AC4's independent verification uses)
        since filter-repo path matching is itself path-segment-exact by
        design -- this guards the TEST's own regex fidelity to the spec."""
        assert REMOVED_ROOTS_RE.match("runsomething/file.txt") is None
        assert REMOVED_ROOTS_RE.match("public-assets/file.txt") is None
        assert REMOVED_ROOTS_RE.match("not-loop-team/runs/file.txt") is None
        assert REMOVED_ROOTS_RE.match("public/file.txt") is not None
        assert REMOVED_ROOTS_RE.match("runs/file.txt") is not None
        assert REMOVED_ROOTS_RE.match("loop-team/runs/file.txt") is not None
        assert REMOVED_ROOTS_RE.match("runs") is not None  # exact top-level match, no trailing slash
