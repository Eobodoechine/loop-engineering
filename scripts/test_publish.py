"""Behavioral tests for scripts/publish.sh.

Every test runs publish.sh via subprocess against TEMP FIXTURE git repos —
never the real ~/Claude/loop tree, never a real remote. The fixture PUBLIC
repo has NO 'origin' remote, so an accidental push would fail loudly rather
than hitting the network; behavioral tests assert pre-push state or use
--dry-run.

The safety invariant under test: it is impossible to publish a private /
untracked / gitignored / PII-bearing file, or to push an unguarded tree.
"""

from __future__ import annotations

import pytest

pytest.skip(
    "publish.sh is DEPRECATED (2026-07-01): it mirrored into the removed public/ "
    "submodule. The live publishing path is snapshot-publish.sh, covered by "
    "test_snapshot_publish.py. These behavioral tests never ran on this machine "
    "before today (Py3.9 collection crash) and 4 were latently failing against "
    "the retired script -- documented in fix_plan.md. Retired with the script.",
    allow_module_level=True,
)
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
PUBLISH_SH = SCRIPTS_DIR / "publish.sh"
SUBTREE = "loop-team"
BRANCH = "phase1-eval-harness"

# A synthetic token the canonical pii-guard.sh flags via its builtin PATTERN
# (sk-ant|sk-proj). NOT a real secret — just the prefix the guard catches.
PII_TOKEN = "sk-ant-SYNTHETIC-TEST-TOKEN-not-real"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )


def _init_repo(repo: Path, branch: str | None = None) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    if branch:
        _git(repo, "checkout", "-q", "-b", branch)


@pytest.fixture
def repos(tmp_path):
    """Build fixture MAIN and PUBLIC repos.

    MAIN: loop-team/ with
      - tracked framework file  loop-team/harness/log.py   (publishes)
      - gitignored file         loop-team/runs/x           (never publishes)
      - untracked file          loop-team/scratch_secret.md(positive control)
      - .gitignore
    PUBLIC: empty git repo on phase1-eval-harness, NO remote.
    Returns (main, public, run) where run() invokes publish.sh.
    """
    main = tmp_path / "main"
    public = tmp_path / "public"

    _init_repo(main)
    (main / SUBTREE / "harness").mkdir(parents=True)
    (main / SUBTREE / "harness" / "log.py").write_text("# framework log helper\n")
    (main / ".gitignore").write_text(f"{SUBTREE}/runs/\n__pycache__/\n")
    # gitignored content present on disk in MAIN
    (main / SUBTREE / "runs").mkdir()
    (main / SUBTREE / "runs" / "x").write_text("private run artifact\n")
    _git(main, "add", ".gitignore", f"{SUBTREE}/harness/log.py")
    _git(main, "commit", "-qm", "init main")
    # untracked private scratch file — never git-added (POSITIVE CONTROL)
    (main / SUBTREE / "scratch_secret.md").write_text("private scratch — must not leak\n")

    _init_repo(public, branch=BRANCH)
    (public / "README.md").write_text("public repo\n")
    _git(public, "add", "README.md")
    _git(public, "commit", "-qm", "init public")
    # explicitly NO remote on public

    def run(*args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["LOOP_MAIN_DIR"] = str(main)
        env["LOOP_PUBLIC_DIR"] = str(public)
        return subprocess.run(
            ["bash", str(PUBLISH_SH), *args],
            capture_output=True, text=True, env=env,
        )

    return main, public, run


def _public_head(public: Path) -> str:
    return _git(public, "rev-parse", "HEAD").stdout.strip()


def _staged_files(public: Path) -> list[str]:
    out = _git(public, "diff", "--cached", "--name-only").stdout
    return [l for l in out.splitlines() if l]


# ── 1 BEHAVIORAL: tracked framework file IS copied ──────────────────────────
def test_tracked_file_is_copied(repos):
    main, public, run = repos
    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    assert (public / SUBTREE / "harness" / "log.py").is_file()


# ── 2 BEHAVIORAL: POSITIVE CONTROL — untracked file NEVER copied ────────────-
def test_untracked_file_never_copied(repos):
    main, public, run = repos
    # sanity: it exists in MAIN but is untracked
    assert (main / SUBTREE / "scratch_secret.md").is_file()
    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    assert not (public / SUBTREE / "scratch_secret.md").exists(), \
        "untracked private file leaked into PUBLIC"


# ── 3 BEHAVIORAL: gitignored file never copied ───────────────────────────────
def test_gitignored_file_never_copied(repos):
    main, public, run = repos
    assert (main / SUBTREE / "runs" / "x").is_file()  # present in MAIN
    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    assert not (public / SUBTREE / "runs" / "x").exists(), \
        "gitignored file leaked into PUBLIC"


# ── 4 BEHAVIORAL: PII in a TRACKED file -> abort, no commit, index reset ─────-
def test_pii_aborts_with_no_commit_and_reset(repos):
    main, public, run = repos
    # plant a synthetic token in a TRACKED main file so it propagates
    f = main / SUBTREE / "harness" / "log.py"
    f.write_text(f"API_KEY = '{PII_TOKEN}'\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "add synthetic token")

    before = _public_head(public)
    r = run()  # full run (not dry); guard must abort BEFORE commit/push
    assert r.returncode != 0, "publish should ABORT on PII"
    # no commit created
    assert _public_head(public) == before, "a commit was created despite PII"
    # index reset — nothing staged
    assert _staged_files(public) == [], f"index not reset: {_staged_files(public)}"


# ── 5 BEHAVIORAL: PRUNE — stale file in PUBLIC (FS-based) is deleted ─────────-
def test_prune_removes_stale_public_file(repos):
    main, public, run = repos
    # pre-seed PUBLIC with a file NOT in publish_set, incl. a gitignored-in-main
    # path to prove the prune is FILESYSTEM-based, not git-based.
    (public / SUBTREE / "runs").mkdir(parents=True, exist_ok=True)
    stale_ignored = public / SUBTREE / "runs" / "x"          # gitignored-in-main path
    stale_other = public / SUBTREE / "old_removed.py"        # plain stale file
    stale_ignored.write_text("stale leaked artifact\n")
    stale_other.write_text("# removed upstream\n")
    assert stale_ignored.is_file() and stale_other.is_file()

    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    assert not stale_ignored.exists(), "FS-based prune failed for gitignored-path stale file"
    assert not stale_other.exists(), "FS-based prune failed for stale file"
    # and the legit tracked file is still there
    assert (public / SUBTREE / "harness" / "log.py").is_file()


# ── 6 BEHAVIORAL: --dry-run syncs+guards but makes NO commit, NO push ────────-
def test_dry_run_no_commit_no_push(repos):
    main, public, run = repos
    before = _public_head(public)
    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    # sync happened
    assert (public / SUBTREE / "harness" / "log.py").is_file()
    # no commit
    assert _public_head(public) == before, "dry-run created a commit"
    # no push possible/attempted: public has no remote; if a push had run it
    # would error. returncode 0 + unchanged HEAD proves no push path taken.
    assert "push" not in r.stdout.lower()


# ── 7 BEHAVIORAL: PUBLIC not on publish branch -> abort non-zero ─────────────-
def test_wrong_branch_aborts(repos):
    main, public, run = repos
    _git(public, "checkout", "-q", "-b", "some-other-branch")
    before = _public_head(public)
    r = run("--dry-run")
    assert r.returncode != 0, "should abort when PUBLIC is on the wrong branch"
    assert _public_head(public) == before
    # nothing should have been synced (abort before mutation)
    assert not (public / SUBTREE).exists() or \
        not (public / SUBTREE / "harness" / "log.py").exists()


# ── 8 BEHAVIORAL: MAIN HEAD and index UNCHANGED after a run ──────────────────-
def test_main_repo_never_written(repos):
    main, public, run = repos
    head_before = _git(main, "rev-parse", "HEAD").stdout.strip()
    status_before = _git(main, "status", "--porcelain").stdout
    run("--dry-run")
    run()  # also exercise the full path
    head_after = _git(main, "rev-parse", "HEAD").stdout.strip()
    status_after = _git(main, "status", "--porcelain").stdout
    assert head_after == head_before, "MAIN HEAD changed — publish wrote to main"
    assert status_after == status_before, "MAIN working tree/index changed — publish wrote to main"


# ── 9 DOC: usage incl. tracked-only + `git add -f` warning ───────────────────-
def test_publish_sh_documents_usage_and_warnings():
    text = PUBLISH_SH.read_text()
    lower = text.lower()
    assert "--dry-run" in text
    assert BRANCH in text                       # branch requirement documented
    assert "git add -f" in lower                # the force-add warning
    assert "tracked" in lower                   # tracked-only contract
    assert "commit it to main first" in lower or "commit to main first" in lower
