"""Behavioral tests for scripts/snapshot-publish.sh.

Every test runs snapshot-publish.sh via subprocess against TEMP FIXTURE git
repos — never the real ~/Claude/loop tree, never a real network remote. The
fixture PUBLIC clone's `origin` is a LOCAL BARE repo, so --incremental/default
pushes target a local bare repo on disk, never the network.

The safety invariant under test: it is impossible to publish a private /
untracked / gitignored / PII-bearing file, and any gate miss is transient +
recoverable (the default snapshot is always a single fresh commit).
"""

from __future__ import annotations
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
PUBLISH_SH = SCRIPTS_DIR / "snapshot-publish.sh"
BRANCH = "main"

# Synthetic personal markers written into the fixture MAIN's .pii-markers.local.
# These are made-up strings, NOT the real user's markers.
MARKER_A = "acme-secret-slug"
MARKER_B = "zzpersonalname"

# A REAL-format key the gate's real-key regex catches (sk-ant-api / sk-proj-...).
# NOT a real secret — just the format the gate flags.
REAL_KEY = "sk-ant-api-SYNTHETIC0000000000000-not-real"
# A bare prefix that should NOT trip the real-key regex (used to prove tooling
# exclusion doesn't create a blind spot: bare 'sk-ant' in a tooling file is OK).
BARE_PREFIX = "sk-ant"

FIX_EMAIL = "fixtureuser@example.com"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )


def _stamped_readme(date: str | None = None) -> str:
    import time as _t
    return "# Fixture repo\n\n_Status as of %s._\n" % (
        date or _t.strftime("%Y-%m-%d"))


def _init_repo(repo: Path, branch: str | None = None) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", FIX_EMAIL)
    _git(repo, "config", "user.name", "Fixture")
    if branch:
        _git(repo, "checkout", "-q", "-b", branch)
    # The freshness gate reads HEAD:README.md — every fixture MAIN (and PUBLIC,
    # harmlessly) starts with a committed, current-date-stamped README.
    (repo / "README.md").write_text(_stamped_readme())
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "fixture readme")


@pytest.fixture
def repos(tmp_path):
    """Build fixture MAIN, PUBLIC clone (origin -> local bare repo), and run().

    MAIN: a git repo with
      - tracked  loop-team/harness/log.py          (publishes)
      - tracked  scripts/pii-guard.sh (tooling)     (holds bare 'sk-ant' — must
                                                      NOT trip real-key gate)
      - tracked  scripts/.pii-markers.local? NO — .pii-markers.local is gitignored
                 but present on disk so the gate can read it.
      - tracked  public/leak.txt + loop-team/runs/keep.txt? excluded subtrees
      - gitignored loop-team/runs/x                 (never publishes)
      - untracked loop-team/scratch_secret.md       (positive control)
    PUBLIC: git repo on branch main whose 'origin' is a local BARE repo.
    """
    main = tmp_path / "main"
    public = tmp_path / "public"
    bare = tmp_path / "origin.git"

    # ── MAIN ────────────────────────────────────────────────────────────────
    _init_repo(main)
    (main / "loop-team" / "harness").mkdir(parents=True)
    (main / "loop-team" / "harness" / "log.py").write_text("# framework log helper\n")

    # tooling file that legitimately contains a bare key prefix — proves the
    # real-key regex (sk-ant-api / sk-proj-...) does NOT match bare 'sk-ant',
    # AND that even if it did, tooling files are excluded from the real-key gate.
    (main / "scripts").mkdir(parents=True)
    (main / "scripts" / "pii-guard.sh").write_text(
        f"#!/bin/bash\n# guard checks the prefix {BARE_PREFIX} and sk-proj\nPATTERN='sk-ant|sk-proj'\n"
    )

    # excluded subtrees: public/ and loop-team/runs/ (tracked, but pruned by sync)
    (main / "public").mkdir(parents=True)
    (main / "public" / "site.txt").write_text("published-site placeholder\n")

    # .gitignore: runs/ and the local markers file
    (main / ".gitignore").write_text(
        "loop-team/runs/\n__pycache__/\nscripts/.pii-markers.local\n"
    )

    # local markers file (gitignored, present on disk — the gate reads it)
    (main / "scripts" / ".pii-markers.local").write_text(
        f"# personal markers\n{MARKER_A}\n{MARKER_B}\n"
    )

    _git(main, "add", ".gitignore",
         "loop-team/harness/log.py", "scripts/pii-guard.sh", "public/site.txt")
    _git(main, "commit", "-qm", "init main")

    # gitignored content on disk in MAIN
    (main / "loop-team" / "runs").mkdir()
    (main / "loop-team" / "runs" / "x").write_text("private run artifact\n")
    # untracked private scratch (POSITIVE CONTROL) — never git-added
    (main / "loop-team" / "scratch_secret.md").write_text("private scratch — must not leak\n")

    # ── BARE origin + PUBLIC clone ───────────────────────────────────────────
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _init_repo(public, branch=BRANCH)
    _git(public, "remote", "add", "origin", str(bare))
    (public / "README.md").write_text("public repo\n")
    _git(public, "add", "README.md")
    _git(public, "commit", "-qm", "init public")
    # seed the bare origin so it has a main ref (mirrors a real cloned repo)
    _git(public, "push", "-q", "origin", BRANCH)

    def run(*args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["LOOP_MAIN_DIR"] = str(main)
        env["LOOP_PUBLIC_CLONE"] = str(public)
        env["LOOP_SCAN_EMAIL"] = FIX_EMAIL
        return subprocess.run(
            ["bash", str(PUBLISH_SH), *args],
            capture_output=True, text=True, env=env,
        )

    return main, public, bare, run


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _count(repo: Path, ref: str = "HEAD") -> int:
    return int(_git(repo, "rev-list", "--count", ref).stdout.strip())


# ── AC1 tracked file IS published ────────────────────────────────────────────
def test_tracked_file_published(repos):
    main, public, bare, run = repos
    r = run()
    assert r.returncode == 0, r.stderr
    assert (public / "loop-team" / "harness" / "log.py").is_file()


# ── AC2 untracked scratch_secret.md NOT present ──────────────────────────────
def test_untracked_not_published(repos):
    main, public, bare, run = repos
    assert (main / "loop-team" / "scratch_secret.md").is_file()  # sanity
    r = run()
    assert r.returncode == 0, r.stderr
    assert not (public / "loop-team" / "scratch_secret.md").exists(), \
        "untracked private file leaked into PUBLIC"


# ── AC3 gitignored runs/x NOT present ────────────────────────────────────────
def test_gitignored_not_published(repos):
    main, public, bare, run = repos
    assert (main / "loop-team" / "runs" / "x").is_file()  # sanity
    r = run()
    assert r.returncode == 0, r.stderr
    assert not (public / "loop-team" / "runs" / "x").exists(), \
        "gitignored file leaked into PUBLIC"


# ── AC4 public/ and loop-team/runs excluded ──────────────────────────────────
def test_excluded_subtrees_removed(repos):
    main, public, bare, run = repos
    r = run()
    assert r.returncode == 0, r.stderr
    assert not (public / "public").exists(), "public/ was not excluded"
    assert not (public / "loop-team" / "runs").exists(), "loop-team/runs not excluded"


# ── AC5 personal marker in a tracked file -> abort, no new commit ────────────
def test_marker_aborts_no_commit(repos):
    main, public, bare, run = repos
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text(f"# note about {MARKER_A} project\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "plant marker")

    before = _head(public)
    r = run()
    assert r.returncode != 0, "should ABORT on personal marker"
    assert _head(public) == before, "a commit was created despite marker hit"


# ── AC6 email OR macOS home path in a tracked file -> abort ──────────────────
def test_email_aborts(repos):
    main, public, bare, run = repos
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text(f"contact = '{FIX_EMAIL}'\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "plant email")
    before = _head(public)
    r = run()
    assert r.returncode != 0, "should ABORT on user email"
    assert _head(public) == before


def test_home_path_aborts(repos):
    main, public, bare, run = repos
    f = main / "loop-team" / "harness" / "log.py"
    home_prefix = "/Use" + "rs/"   # built at runtime; see gate self-match note
    f.write_text(f"path = '{home_prefix}someone/private/thing'\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "plant home path")
    before = _head(public)
    r = run()
    assert r.returncode != 0, "should ABORT on a macOS home path"
    assert _head(public) == before


# ── AC7 real key in normal file -> abort; bare prefix in tooling file -> OK ──
def test_real_key_in_normal_file_aborts(repos):
    main, public, bare, run = repos
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text(f"KEY = '{REAL_KEY}'\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "plant real key")
    before = _head(public)
    r = run()
    assert r.returncode != 0, "should ABORT on real key in a normal tracked file"
    assert _head(public) == before


def test_bare_prefix_in_tooling_file_ok(repos):
    main, public, bare, run = repos
    # scripts/pii-guard.sh (a tooling-exclusion file) already contains bare
    # 'sk-ant' from the fixture. A clean run must NOT abort on it.
    r = run()
    assert r.returncode == 0, \
        f"bare prefix in tooling file wrongly tripped the gate:\n{r.stderr}"
    assert (public / "scripts" / "pii-guard.sh").is_file()


def test_real_key_in_tooling_file_excluded(repos):
    main, public, bare, run = repos
    # Even a REAL-format key inside a tooling-exclusion file must be exempted
    # from the real-key portion (it's the detection regex itself). Add it to
    # scripts/pii-guard.sh which is in TOOLING_EXCLUDE.
    tf = main / "scripts" / "pii-guard.sh"
    tf.write_text(tf.read_text() + f"# example only: {REAL_KEY}\n")
    _git(main, "add", str(tf))
    _git(main, "commit", "-qm", "add example key to tooling")
    r = run()
    assert r.returncode == 0, \
        f"real key in TOOLING file wrongly tripped the gate:\n{r.stderr}"


# ── AC8 missing/empty .pii-markers.local -> abort before publish ─────────────
def test_missing_markers_aborts(repos):
    main, public, bare, run = repos
    (main / "scripts" / ".pii-markers.local").unlink()
    before = _head(public)
    r = run()
    assert r.returncode != 0, "should ABORT when marker file is missing"
    assert _head(public) == before


def test_empty_markers_aborts(repos):
    main, public, bare, run = repos
    # only comments + blanks -> yields no pattern -> fail-closed
    (main / "scripts" / ".pii-markers.local").write_text("# only a comment\n\n   \n")
    before = _head(public)
    r = run()
    assert r.returncode != 0, "should ABORT when marker file yields no patterns"
    assert _head(public) == before


# ── AC9 deletion propagates ──────────────────────────────────────────────────
def test_deletion_propagates(repos):
    main, public, bare, run = repos
    r = run()
    assert r.returncode == 0, r.stderr
    assert (public / "loop-team" / "harness" / "log.py").is_file()

    # remove the tracked file from MAIN and commit the deletion
    _git(main, "rm", "-q", "loop-team/harness/log.py")
    _git(main, "commit", "-qm", "remove log.py")

    r2 = run()
    assert r2.returncode == 0, r2.stderr
    assert not (public / "loop-team" / "harness" / "log.py").exists(), \
        "deletion in MAIN did not propagate to PUBLIC"


# ── AC10 --dry-run -> no new commit in PUBLIC, no push ───────────────────────
def test_dry_run_no_commit_no_push(repos):
    main, public, bare, run = repos
    before = _head(public)
    bare_before = _head(bare)
    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    # sync happened
    assert (public / "loop-team" / "harness" / "log.py").is_file()
    # no commit locally, no push to origin
    assert _head(public) == before, "dry-run created a commit"
    assert _head(bare) == bare_before, "dry-run pushed to origin"


# ── AC11 snapshot default keeps PUBLIC at a SINGLE commit across two runs ─────
def test_snapshot_single_commit(repos):
    main, public, bare, run = repos
    r1 = run()
    assert r1.returncode == 0, r1.stderr
    assert _count(public) == 1, "public not a single commit after first snapshot"
    assert _count(bare, BRANCH) == 1, "origin not a single commit after first snapshot"

    # second run — change a tracked file so there's something to publish
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text("# framework log helper v2\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "update log.py")

    r2 = run()
    assert r2.returncode == 0, r2.stderr
    assert _count(public) == 1, "public not a single commit after second snapshot"
    assert _count(bare, BRANCH) == 1, "origin not a single commit after second snapshot"


# ── AC12 MAIN HEAD + porcelain status unchanged after a run ──────────────────
def test_main_never_written(repos):
    main, public, bare, run = repos
    head_before = _head(main)
    status_before = _git(main, "status", "--porcelain").stdout
    run("--dry-run")
    run()             # full snapshot path
    run("--incremental")  # incremental path too
    head_after = _head(main)
    status_after = _git(main, "status", "--porcelain").stdout
    assert head_after == head_before, "MAIN HEAD changed — publish wrote to main"
    assert status_after == status_before, "MAIN working tree/index changed"


# ── AC7b real key in tooling file with TRAILING-SLASH PUBLIC dir -> OK ───────
def test_real_key_in_tooling_file_trailing_slash_public_ok(repos):
    """Regression: a trailing slash on LOOP_PUBLIC_CLONE must not break the
    tooling-exclusion path strip. Before the fix, "$PUBLIC"/ became a double
    slash so the grep hit's single-slash rel path never matched TOOLING_EXCLUDE,
    _is_tooling never fired, and a real-key literal in an EXCLUDED tooling file
    (scripts/pii-guard.sh) wrongly ABORTED the publish. After normalizing the
    trailing slash, the exclusion matches and the publish succeeds (rc 0)."""
    main, public, bare, run = repos
    tf = main / "scripts" / "pii-guard.sh"
    tf.write_text(tf.read_text() + f"# example only: {REAL_KEY}\n")
    _git(main, "add", str(tf))
    _git(main, "commit", "-qm", "add example key to tooling")

    # Run with LOOP_PUBLIC_CLONE carrying a TRAILING SLASH (the non-default env
    # override that exposed the bug).
    env = dict(os.environ)
    env["LOOP_MAIN_DIR"] = str(main)
    env["LOOP_PUBLIC_CLONE"] = str(public) + "/"
    env["LOOP_SCAN_EMAIL"] = FIX_EMAIL
    r = subprocess.run(
        ["bash", str(PUBLISH_SH)],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, (
        "trailing-slash PUBLIC dir broke tooling exclusion — real key in an "
        f"EXCLUDED tooling file wrongly aborted the publish:\n{r.stderr}"
    )


# ── DOC: usage comment covers the required contracts ─────────────────────────
def test_usage_documented():
    text = PUBLISH_SH.read_text()
    lower = text.lower()
    assert "--dry-run" in text
    assert "--incremental" in text
    assert "git add -f" in lower                 # force-add warning
    assert "tracked" in lower                     # tracked-only contract
    assert "commit it to main first" in lower
    assert "snapshot" in lower and "force-with-lease" in lower


# ── AC (2026-07-01): README-freshness gate ────────────────────────────────────
def _restamp(main: Path, date: str) -> None:
    (main / "README.md").write_text(_stamped_readme(date))
    _git(main, "add", "README.md")
    _git(main, "commit", "-qm", "restamp")


def test_freshness_stale_stamp_aborts(repos):
    main, public, bare, run = repos
    _restamp(main, "2020-01-01")           # committed, but stamped in the past
    before = _head(public)
    r = run()
    assert r.returncode != 0, "stale README stamp must abort the publish"
    assert "stale" in (r.stdout + r.stderr).lower() or "older than" in (r.stdout + r.stderr)
    assert _head(public) == before, "nothing may be committed on a freshness abort"


def test_freshness_missing_stamp_aborts(repos):
    main, public, bare, run = repos
    (main / "README.md").write_text("# No stamp here\n")
    _git(main, "add", "README.md")
    _git(main, "commit", "-qm", "remove stamp")
    r = run()
    assert r.returncode != 0, "missing stamp must abort"
    assert "no 'Status as of" in (r.stdout + r.stderr) or "stamp" in (r.stdout + r.stderr)


def test_freshness_fresh_stamp_passes(repos):
    main, public, bare, run = repos
    r = run()                               # fixture README is stamped today
    assert r.returncode == 0, r.stderr


def test_freshness_uncommitted_stamp_does_not_count(repos):
    """The gate reads HEAD, not the working tree: an updated-but-uncommitted
    stamp over a stale committed one must still abort (the forgot-to-commit
    case — the exact hole plan-check caught in the spec)."""
    main, public, bare, run = repos
    _restamp(main, "2020-01-01")
    (main / "README.md").write_text(_stamped_readme())   # fresh, NOT committed
    r = run()
    assert r.returncode != 0, "working-tree stamp must not satisfy the gate"


def test_freshness_override_warns_and_proceeds(repos, monkeypatch):
    main, public, bare, run = repos
    _restamp(main, "2020-01-01")
    monkeypatch.setenv("LOOP_README_STALE_OK", "1")
    r = run()
    assert r.returncode == 0, r.stderr
    assert "OVERRIDDEN" in (r.stdout + r.stderr)
