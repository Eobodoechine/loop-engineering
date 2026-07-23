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


def test_public_prune_paths_remove_tracked_main_files(repos):
    """PUBLIC_PRUNE_PATHS is an explicit publish-only denylist: these paths can
    exist as committed MAIN files, but must be absent from the synced PUBLIC tree.
    The fixture remote is local, so this exercises the real script without a real
    public publish."""
    main, public, bare, run = repos
    pruned_files = [
        main / "artifacts" / "cockpit-feature-plan-source-audit.md",
        main / "fix_plan_migration_2026-07-15_backup" / "notes.md",
    ]
    for path in pruned_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private generated evidence should not publish\n")
    control = main / "artifacts" / "public-control.md"
    control.write_text("ordinary tracked artifact publishes\n")
    _git(main, "add", *(str(path.relative_to(main)) for path in [*pruned_files, control]))
    _git(main, "commit", "-qm", "add prune path fixtures")

    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    assert not (public / "artifacts" / "cockpit-feature-plan-source-audit.md").exists()
    assert not (public / "fix_plan_migration_2026-07-15_backup").exists()
    assert (public / "artifacts" / "public-control.md").is_file()


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


def test_research_home_path_redacted_in_public_output_source_unchanged(repos):
    """[BEHAVIORAL] Private research may cite exact local evidence paths,
    but the generated public snapshot must redact them before the privacy
    scan. This exercises the real dry-run sync path and then inspects both
    source and public output."""
    main, public, bare, run = repos
    source_path = "/Use" + "rs/eobodoechine/Claude/loop/foo.md"
    research = main / "research" / "path-evidence.md"
    research.parent.mkdir(parents=True)
    research.write_text(
        f"# Evidence\n\nSource file: {source_path}\n",
        encoding="utf-8",
    )
    _git(main, "add", str(research))
    _git(main, "commit", "-qm", "add research evidence path")

    r = run("--dry-run")
    assert r.returncode == 0, (
        "research-like home paths should be redacted in PUBLIC before the "
        f"privacy scan, not block the publish:\n{r.stderr}"
    )

    assert source_path in research.read_text(encoding="utf-8"), (
        "snapshot redaction must not mutate the private MAIN source file"
    )
    public_text = (public / "research" / "path-evidence.md").read_text(encoding="utf-8")
    assert source_path not in public_text
    assert "/Use" + "rs/" not in public_text
    assert "foo.md" in public_text


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


def test_real_key_in_research_file_still_fails_after_redaction(repos):
    """[BEHAVIORAL] Home-path redaction must not turn the final privacy
    scan into a broad pass: a real-key-shaped leak in an ordinary
    research/non-tooling file still fails closed."""
    main, public, bare, run = repos
    research = main / "research" / "normal-leak.md"
    research.parent.mkdir(parents=True)
    research.write_text(
        "This normal research file leaks a key-shaped string:\n"
        f"{REAL_KEY}\n",
        encoding="utf-8",
    )
    _git(main, "add", str(research))
    _git(main, "commit", "-qm", "plant real key in research")

    before = _head(public)
    r = run("--dry-run")
    assert r.returncode != 0, "real key in a normal/non-tooling file must block"
    assert "research/normal-leak.md" in (r.stdout + r.stderr)
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


def test_detector_tooling_examples_redacted_and_exempted_without_blocking(repos):
    """[BEHAVIORAL] Detector tooling may document its own key/home-path
    examples without creating a publish-blocking false positive. The public
    copy must still avoid contiguous home paths."""
    main, public, bare, run = repos
    tooling = main / "loop-team" / "harness" / "full_history_scan.py"
    tooling.parent.mkdir(parents=True, exist_ok=True)
    home_example = "/Use" + "rs/testuser/secret/path.txt"
    tooling.write_text(
        '"""Detector examples for documentation."""\n'
        f"HOME_EXAMPLE = {home_example!r}\n"
        f"KEY_PATTERN_EXAMPLE = {REAL_KEY!r}\n",
        encoding="utf-8",
    )
    _git(main, "add", str(tooling))
    _git(main, "commit", "-qm", "add detector tooling examples")

    r = run("--dry-run")
    assert r.returncode == 0, (
        "detector tooling examples should be handled as tooling examples, "
        f"not publish-blocking leaks:\n{r.stderr}"
    )

    assert home_example in tooling.read_text(encoding="utf-8")
    public_text = (public / "loop-team" / "harness" / "full_history_scan.py").read_text(
        encoding="utf-8"
    )
    assert home_example not in public_text
    assert "/Use" + "rs/" not in public_text
    assert REAL_KEY in public_text


def test_tooling_key_exemption_does_not_broad_exempt_normal_files(repos):
    """[BEHAVIORAL] The detector-tooling exception must stay path-scoped:
    the same key-shaped example that is acceptable in detector tooling must
    still block an ordinary file."""
    main, public, bare, run = repos
    tooling = main / "loop-team" / "harness" / "full_history_scan.py"
    tooling.parent.mkdir(parents=True, exist_ok=True)
    tooling.write_text(f"KEY_PATTERN_EXAMPLE = {REAL_KEY!r}\n", encoding="utf-8")

    ordinary = main / "research" / "ordinary-key-example.md"
    ordinary.parent.mkdir(parents=True)
    ordinary.write_text(f"ordinary file has {REAL_KEY}\n", encoding="utf-8")

    _git(main, "add", str(tooling), str(ordinary))
    _git(main, "commit", "-qm", "add tooling and ordinary key examples")

    before = _head(public)
    r = run("--dry-run")
    assert r.returncode != 0, (
        "ordinary files must not inherit detector-tooling key exemptions"
    )
    combined = r.stdout + r.stderr
    assert "research/ordinary-key-example.md" in combined
    assert _head(public) == before


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

    # remove the tracked file from MAIN and commit the deletion. Also give
    # README.md a real, non-stamp-only content change (same pattern as
    # test_pass_case_real_readme_change_proceeds) so this second publish
    # satisfies the since-last-publish freshness gate — this test is about
    # deletion propagation, not about the freshness gate, so the fixture must
    # not spuriously trip it.
    import time as _t
    (main / "README.md").write_text(
        "# Fixture repo\n\nNow with real new content describing what changed.\n\n"
        "_Status as of %s._\n" % _t.strftime("%Y-%m-%d")
    )
    _git(main, "add", "README.md")
    _git(main, "rm", "-q", "loop-team/harness/log.py")
    _git(main, "commit", "-qm", "remove log.py, update readme")

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

    # second run — change a tracked file so there's something to publish. Also
    # give README.md a real, non-stamp-only content change (same pattern as
    # test_pass_case_real_readme_change_proceeds) so this second publish
    # satisfies the since-last-publish freshness gate — this test is about
    # single-commit snapshot behavior, not the freshness gate, so the fixture
    # must not spuriously trip it.
    import time as _t
    (main / "README.md").write_text(
        "# Fixture repo\n\nNow with real new content describing what changed.\n\n"
        "_Status as of %s._\n" % _t.strftime("%Y-%m-%d")
    )
    _git(main, "add", "README.md")
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text("# framework log helper v2\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "update log.py, update readme")

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


def _tomorrow() -> str:
    """A date string one day after 'today', used where a since-last-publish
    test needs the README stamp text to differ from the fixture's initial
    today-stamped README (a same-day restamp would produce byte-identical
    content and stage nothing), while still satisfying the EXISTING
    date-stamp gate (stamp >= HEAD commit date, and a future date always is)."""
    import datetime
    return (datetime.date.today() + datetime.timedelta(days=1)).isoformat()


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


# ── AC5 (spec 2026-07-02): mechanical since-last-publish freshness gate ──────
#
# Marker file: PUBLIC's tracked tree carries `.loop-publish-meta.json`
# ({"main_sha": "<hash>"}) recording the MAIN commit sha published last time.
# Read from PUBLIC's CURRENT HEAD before the tree is wiped/resynced. See
# spec Part 2 for the full mechanism; these tests exercise it via the public
# subprocess interface only (never by asserting on the script's internals).

import json


def _marker(public: Path, ref: str = "HEAD") -> dict | None:
    """Read .loop-publish-meta.json out of a PUBLIC ref via git show, or None
    if it doesn't exist at that ref (mirrors how the gate itself must read
    it — from the committed tree, not the working copy). Deliberately does
    NOT use the module's `_git` helper (which passes check=True and would
    raise CalledProcessError on a missing path) since "doesn't exist yet" is
    an expected, in-band outcome here, not a fixture-setup error."""
    r = subprocess.run(
        ["git", "-C", str(public), "show", f"{ref}:.loop-publish-meta.json"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def _main_sha(main: Path) -> str:
    return _head(main)


def _seed_public_marker(public: Path, main_sha: str) -> None:
    (public / ".loop-publish-meta.json").write_text(
        json.dumps({"main_sha": main_sha}) + "\n",
        encoding="utf-8",
    )
    _git(public, "add", ".loop-publish-meta.json")
    _git(public, "commit", "-qm", "seed publish marker")
    _git(public, "push", "-q", "origin", BRANCH)


def test_bootstrap_no_marker_publishes_and_writes_marker(repos):
    """(a) Bootstrap case: PUBLIC's current HEAD carries no marker file yet
    (first run under this gate). Publish must NOT hard-block, and the
    resulting PUBLIC commit must carry the marker recording MAIN's HEAD sha
    at publish time."""
    main, public, bare, run = repos
    assert _marker(public) is None, "fixture PUBLIC must start with no marker (sanity)"

    sha_at_publish = _main_sha(main)
    r = run()
    assert r.returncode == 0, r.stderr

    m = _marker(public)
    assert m is not None, "marker file was not written on the bootstrap publish"
    assert m.get("main_sha") == sha_at_publish, (
        f"marker recorded main_sha={m.get('main_sha')!r}, "
        f"expected the published MAIN HEAD sha {sha_at_publish!r}"
    )


def test_bootstrap_prints_gate_armed_notice(repos):
    """(a) Bootstrap case: the script prints a one-line notice that the gate
    is now armed starting from this publish (per spec, distinct from silent
    pass-through)."""
    main, public, bare, run = repos
    r = run()
    assert r.returncode == 0, r.stderr
    out = (r.stdout + r.stderr).lower()
    assert "armed" in out, (
        "expected a notice that the since-last-publish gate is now armed "
        f"starting from this bootstrap publish; got:\n{r.stdout}\n{r.stderr}"
    )


def test_block_other_files_changed_readme_untouched_fails_closed(repos):
    """(b) Block case: a marker exists recording a prior MAIN sha. Since that
    sha, some OTHER tracked file changed but README.md did not. The publish
    must fail closed with a message identifying this specific case (README
    untouched since last publish) — and must not create a new PUBLIC commit
    or push."""
    main, public, bare, run = repos

    r1 = run()  # establishes the marker at MAIN's current HEAD
    assert r1.returncode == 0, r1.stderr
    published_sha = _marker(public)["main_sha"]
    assert published_sha == _main_sha(main)

    # change a non-README tracked file only
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text("# framework log helper v2 (non-readme change)\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "unrelated change, README untouched")

    before = _head(public)
    before_bare = _head(bare)
    r2 = run()
    assert r2.returncode != 0, "README untouched since last publish must fail closed"
    combined = (r2.stdout + r2.stderr).lower()
    assert "untouched" in combined or "not touched" in combined or "unchanged" in combined, (
        f"expected the gate to name the untouched-README case explicitly; got:\n"
        f"{r2.stdout}\n{r2.stderr}"
    )
    assert _head(public) == before, "a commit was created despite the block-case gate firing"
    assert _head(bare) == before_bare, "a push happened despite the block-case gate firing"


def test_stamp_only_bump_fails_closed_with_distinct_message(repos):
    """(c) Stamp-only-bump case: a marker exists; since that sha, README.md's
    ONLY change is the `Status as of` line. Must fail closed with a message
    DISTINCT from the block case (b), per spec: "so the user knows exactly
    which case they hit"."""
    main, public, bare, run = repos

    r1 = run()
    assert r1.returncode == 0, r1.stderr

    # bump ONLY the stamp, to a date that still satisfies the EXISTING
    # date-stamp gate (>= HEAD commit date) so this failure is attributable
    # to the NEW gate, not the old one. Use TOMORROW (not "today") so the
    # stamp text actually differs from the fixture's initial today-stamped
    # README — an identical restamp would leave nothing to commit.
    _restamp(main, _tomorrow())

    before = _head(public)
    r2 = run()
    assert r2.returncode != 0, "stamp-only README bump must fail closed"

    stamp_only_msg = (r2.stdout + r2.stderr)
    assert "status as of" in stamp_only_msg.lower() or "stamp" in stamp_only_msg.lower(), (
        f"expected the stamp-only-bump message to reference the stamp; got:\n{stamp_only_msg}"
    )
    assert _head(public) == before, "a commit was created despite the stamp-only-bump gate firing"


def test_block_and_stamp_only_messages_are_distinct(repos):
    """(b) vs (c): the two failure messages must differ so a user can tell
    which case they hit (spec's explicit requirement)."""
    main, public, bare, run = repos

    r1 = run()
    assert r1.returncode == 0, r1.stderr

    # Branch A: other file changes, README untouched (case b)
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text("# v2\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "other file changed")
    r_block = run()
    assert r_block.returncode != 0

    # Reset MAIN back to the published sha's tree state for a clean second
    # branch, then apply a stamp-only change instead (case c).
    published_sha = _marker(public)["main_sha"]
    _git(main, "reset", "-q", "--hard", published_sha)
    _restamp(main, _tomorrow())
    r_stamp = run()
    assert r_stamp.returncode != 0

    msg_block = (r_block.stdout + r_block.stderr).strip()
    msg_stamp = (r_stamp.stdout + r_stamp.stderr).strip()
    assert msg_block != msg_stamp, (
        "block-case and stamp-only-bump-case messages must be distinct so the "
        f"user knows which case they hit.\nblock:\n{msg_block}\nstamp-only:\n{msg_stamp}"
    )


def test_pass_case_real_readme_change_proceeds(repos):
    """(d) Pass case: a marker exists; since that sha, README.md has a real,
    non-stamp-only change (plus possibly other files too). The gate must
    proceed normally (not block), and the marker must be updated to the new
    MAIN sha on this publish."""
    main, public, bare, run = repos

    r1 = run()
    assert r1.returncode == 0, r1.stderr

    # real content change to README (not just the stamp), plus an unrelated
    # file change too, to prove "plus possibly other files" doesn't confuse
    # the gate.
    import time as _t
    (main / "README.md").write_text(
        "# Fixture repo\n\nNow with real new content describing what changed.\n\n"
        "_Status as of %s._\n" % _t.strftime("%Y-%m-%d")
    )
    _git(main, "add", "README.md")
    f = main / "loop-team" / "harness" / "log.py"
    f.write_text("# v2, alongside real readme content\n")
    _git(main, "add", str(f))
    _git(main, "commit", "-qm", "real readme content update + unrelated change")

    new_sha = _main_sha(main)
    r2 = run()
    assert r2.returncode == 0, (
        f"a real, non-stamp-only README change must pass the gate:\n{r2.stdout}\n{r2.stderr}"
    )
    m = _marker(public)
    assert m is not None and m.get("main_sha") == new_sha, (
        "marker was not advanced to the newly-published MAIN sha on a passing publish"
    )


def test_existing_datestamp_gate_still_fires_independently_of_new_gate(repos):
    """(e) Regression: the EXISTING date-stamp freshness gate (README stamp
    date must be >= HEAD commit date) still works, independently of the new
    since-last-publish gate — even when the new gate WOULD pass (a real,
    non-stamp-only README content change), a stale stamp must still block."""
    main, public, bare, run = repos

    r1 = run()
    assert r1.returncode == 0, r1.stderr

    # Real, non-stamp-only README content change (satisfies the NEW gate)...
    # but stamped with a stale (past) date, which must still trip the OLD gate.
    (main / "README.md").write_text(
        "# Fixture repo\n\nReal new content, but stamped stale.\n\n"
        "_Status as of 2020-01-01._\n"
    )
    _git(main, "add", "README.md")
    _git(main, "commit", "-qm", "real content, stale stamp")

    before = _head(public)
    r2 = run()
    assert r2.returncode != 0, (
        "a stale date stamp must still fail the publish even though the "
        "since-last-publish content gate would itself pass"
    )
    assert "stale" in (r2.stdout + r2.stderr).lower() or "older than" in (r2.stdout + r2.stderr)
    assert _head(public) == before


def test_existing_datestamp_gate_and_new_gate_both_checked_on_a_clean_pass(repos):
    """(e) Regression, positive direction: on a clean pass (marker present,
    real non-stamp README change, fresh stamp), BOTH gates are satisfied —
    proves the new gate composes with (does not silently supersede) the old
    one, per spec: "composes with (does not replace) the EXISTING date-stamp
    freshness check — both must pass"."""
    main, public, bare, run = repos

    r1 = run()
    assert r1.returncode == 0, r1.stderr

    import time as _t
    today = _t.strftime("%Y-%m-%d")
    (main / "README.md").write_text(
        "# Fixture repo\n\nReal new content, fresh stamp.\n\n"
        "_Status as of %s._\n" % today
    )
    _git(main, "add", "README.md")
    _git(main, "commit", "-qm", "real content, fresh stamp")

    r2 = run()
    assert r2.returncode == 0, (
        f"expected BOTH gates to pass on a genuinely fresh, substantive README update:\n"
        f"{r2.stdout}\n{r2.stderr}"
    )


def test_diff_aware_nonkey_scan_allows_unchanged_legacy_marker_on_clean_diff(repos):
    """[BEHAVIORAL] A legacy personal-marker hit that predates the last
    published MAIN sha must not fail every later clean publish closed. The
    non-key privacy scan is diff-aware: unchanged legacy hits are surfaced as
    suppressed baseline debt, while changed files remain fail-closed."""
    main, public, bare, run = repos

    legacy = main / "research" / "legacy-marker.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(f"Legacy note mentioning {MARKER_A}\n", encoding="utf-8")
    _git(main, "add", str(legacy))
    _git(main, "commit", "-qm", "legacy marker already published")
    _seed_public_marker(public, _main_sha(main))

    (main / "README.md").write_text(
        "# Fixture repo\n\nClean change after the legacy baseline.\n\n"
        "_Status as of %s._\n" % _tomorrow(),
        encoding="utf-8",
    )
    _git(main, "add", "README.md")
    _git(main, "commit", "-qm", "clean readme change")

    r = run("--dry-run")
    assert r.returncode == 0, r.stderr
    combined = r.stdout + r.stderr
    assert "suppressed" in combined.lower(), combined
    assert "unchanged legacy non-key" in combined.lower(), combined


def test_diff_aware_nonkey_scan_blocks_marker_in_changed_file(repos):
    """[BEHAVIORAL] Diff-awareness must not become a broad PII bypass: a
    personal marker introduced after the recorded publish baseline still
    blocks before commit/push."""
    main, public, bare, run = repos

    _seed_public_marker(public, _main_sha(main))

    leak = main / "research" / "new-marker.md"
    leak.parent.mkdir(parents=True)
    leak.write_text(f"New leak mentioning {MARKER_A}\n", encoding="utf-8")
    (main / "README.md").write_text(
        "# Fixture repo\n\nReal content accompanying a new file.\n\n"
        "_Status as of %s._\n" % _tomorrow(),
        encoding="utf-8",
    )
    _git(main, "add", "README.md", str(leak))
    _git(main, "commit", "-qm", "new marker leak")

    before = _head(public)
    r = run("--dry-run")
    assert r.returncode != 0, "changed file containing a marker must fail closed"
    combined = r.stdout + r.stderr
    assert "research/new-marker.md" in combined, combined
    assert _head(public) == before


def test_marker_written_in_snapshot_mode(repos):
    """Marker-write-location regression guard, snapshot-mode half: the script
    has TWO distinct commit paths (INCREMENTAL's `add -A` and SNAPSHOT's
    `add -A`). The marker must be written ONCE, at the SYNC step (right after
    the exclusion `rm -rf`, before the branch split) so BOTH modes pick it up
    identically via their own `git add -A`. This directly guards against the
    design gap plan-check found: writing the marker before only one path
    would leave the other mode silently never recording state, defeating the
    gate on that path forever.

    Tested practically here across TWO successive default-mode (snapshot)
    publishes — bootstrap, then a real content update — so the marker is
    proven to be both WRITTEN (bootstrap) and ADVANCED (second publish) on
    this path. See test_marker_written_in_incremental_mode for the other
    path, run from an independent fixture instance under identical starting
    conditions so neither run's state leaks into the other.
    """
    main, public, bare, run = repos

    # bootstrap publish
    sha1 = _main_sha(main)
    r1 = run()  # default snapshot mode
    assert r1.returncode == 0, r1.stderr
    m1 = _marker(public)
    assert m1 is not None and m1.get("main_sha") == sha1, (
        "snapshot (default) mode did not write the marker on the bootstrap publish"
    )

    # second publish, with a real README content change, still in snapshot mode
    (main / "README.md").write_text(
        "# Fixture repo\n\nReal content, snapshot-mode second publish.\n\n"
        "_Status as of %s._\n" % _tomorrow()
    )
    _git(main, "add", "README.md")
    _git(main, "commit", "-qm", "second publish content")
    sha2 = _main_sha(main)
    r2 = run()
    assert r2.returncode == 0, r2.stderr
    m2 = _marker(public)
    assert m2 is not None and m2.get("main_sha") == sha2, (
        "snapshot (default) mode did not ADVANCE the marker on a second publish"
    )


def test_marker_written_in_incremental_mode(repos_incremental):
    """Marker-write-location regression guard, incremental-mode half —
    companion to test_marker_written_in_snapshot_mode above, using a SEPARATE
    fixture instance (identical starting topology) so both modes' bootstrap
    AND second (advancing) publish are exercised independently. Together
    these two tests prove the marker is written at the shared SYNC-step
    location rather than inside only one of the two branch-specific commit
    paths — the exact regression plan-check flagged (marker written before
    only one path would leave the OTHER mode's second run never advancing
    its recorded state)."""
    main, public, bare, run = repos_incremental

    sha1 = _main_sha(main)
    r1 = run("--incremental")
    assert r1.returncode == 0, r1.stderr
    m1 = _marker(public)
    assert m1 is not None and m1.get("main_sha") == sha1, (
        "incremental mode did not write the marker on the bootstrap publish"
    )

    (main / "README.md").write_text(
        "# Fixture repo\n\nReal content, incremental-mode second publish.\n\n"
        "_Status as of %s._\n" % _tomorrow()
    )
    _git(main, "add", "README.md")
    _git(main, "commit", "-qm", "second publish content")
    sha2 = _main_sha(main)
    r2 = run("--incremental")
    assert r2.returncode == 0, r2.stderr
    m2 = _marker(public)
    assert m2 is not None and m2.get("main_sha") == sha2, (
        "incremental mode did not ADVANCE the marker on a second publish"
    )


# ── D.1.1 wrong-destination-branch guard aborts BEFORE any PUBLIC mutation ───
def test_wrong_destination_branch_aborts_before_mutation(repos):
    """[BEHAVIORAL] [SECURITY-ORACLE] When PUBLIC is checked out on a branch
    other than PUBLISH_BRANCH ('main'), the guard at snapshot-publish.sh:98-100
    must abort BEFORE the destination wipe at line 171 ever runs. The oracle
    is deliberately content-independent: an UNTRACKED, top-level sentinel file
    in PUBLIC (explicitly NOT under public/, loop-team/runs/, or runs/ — those
    three are separately removed by the line-182 rm -rf regardless of line
    171's state) must survive byte-for-byte. This is NOT checked via a
    tracked-content/tree comparison, because that comparison is provably
    circumventable: line 171's wipe rebuilds PUBLIC from `git archive HEAD`
    (tracked content only), so a wrong-branch fixture that happens to share
    MAIN's HEAD tree would pass a tracked-content diff whether or not the wipe
    actually ran (see spec Revision 2, [G-A])."""
    main, public, bare, run = repos
    other_branch = "not-the-publish-branch"
    _git(public, "checkout", "-q", "-b", other_branch)

    sentinel = public / "sentinel_survives.txt"
    sentinel_content = "sentinel content — must survive a wrong-branch abort\n"
    sentinel.write_text(sentinel_content)  # untracked, top-level, non-excluded-subtree

    r = run()
    assert r.returncode != 0, "publish must ABORT when PUBLIC is on the wrong branch"
    combined = r.stdout + r.stderr
    assert "PUBLIC clone is on" in combined
    assert f"'{other_branch}'" in combined
    assert f"expected '{BRANCH}'" in combined, (
        f"expected the die message to name PUBLISH_BRANCH '{BRANCH}'; got:\n{combined}"
    )

    assert sentinel.is_file(), (
        "untracked top-level sentinel was removed even though the branch "
        "guard should have aborted BEFORE the destination wipe ever ran — "
        "this is the content-independent proof line 171 did not execute"
    )
    assert sentinel.read_text() == sentinel_content, (
        "sentinel content changed on a wrong-branch abort — the destination "
        "wipe/resync must not have run, but the file is no longer byte-identical"
    )


# ── D.1.2 stale untracked top-level PUBLIC output is purged by the line-171
# wipe, isolated from the separate line-182 excluded-subtree removal ─────────
def test_stale_untracked_destination_output_is_purged(repos):
    """[BEHAVIORAL] [SECURITY-ORACLE] A stale, untracked, top-level file already sitting in
    PUBLIC before a normal (correct-branch) publish must be gone afterward —
    proof that the destination wipe at snapshot-publish.sh:171 (`find
    "$PUBLIC" -mindepth 1 -maxdepth 1 ... -exec rm -rf {} +`) actually clears
    PUBLIC's working tree. Deliberately placed OUTSIDE public/, loop-team/runs/,
    and runs/ so this assertion cannot be satisfied by the SEPARATE
    excluded-subtree `rm -rf` at line 182 instead — per spec [G-A], a file
    planted inside one of those three subtrees would be removed by line 182
    regardless of line 171's state, making the test unable to distinguish
    which mechanism did the work. Distinct from test_deletion_propagates
    (tracked-file deletion propagating from MAIN) and test_untracked_not_published
    (source-side untracked exclusion in MAIN): neither of those proves
    DESTINATION-side purge of a pre-existing stale PUBLIC file."""
    main, public, bare, run = repos
    stale = public / "stale_junk.txt"
    stale.write_text("stale leftover output from a prior run\n")
    assert stale.is_file()  # sanity: planted before running, correct branch

    r = run()
    assert r.returncode == 0, r.stderr
    assert not stale.exists(), (
        "stale untracked top-level file in PUBLIC survived the publish — "
        "the destination wipe (line 171) did not purge it"
    )


@pytest.fixture
def repos_incremental(tmp_path):
    """A second, independent instance of the same fixture topology as `repos`,
    so incremental-mode and snapshot-mode marker-writing can be tested from
    identical starting conditions without one run's state leaking into the
    other (each pytest test already gets a fresh `tmp_path`, but a distinct
    fixture name makes the intent — "same shape, independent instance" —
    explicit at the call site)."""
    main = tmp_path / "main"
    public = tmp_path / "public"
    bare = tmp_path / "origin.git"

    _init_repo(main)
    (main / "loop-team" / "harness").mkdir(parents=True)
    (main / "loop-team" / "harness" / "log.py").write_text("# framework log helper\n")
    (main / "scripts").mkdir(parents=True)
    (main / "scripts" / "pii-guard.sh").write_text(
        f"#!/bin/bash\n# guard checks the prefix {BARE_PREFIX} and sk-proj\nPATTERN='sk-ant|sk-proj'\n"
    )
    (main / "public").mkdir(parents=True)
    (main / "public" / "site.txt").write_text("published-site placeholder\n")
    (main / ".gitignore").write_text(
        "loop-team/runs/\n__pycache__/\nscripts/.pii-markers.local\n"
    )
    (main / "scripts" / ".pii-markers.local").write_text(
        f"# personal markers\n{MARKER_A}\n{MARKER_B}\n"
    )
    _git(main, "add", ".gitignore",
         "loop-team/harness/log.py", "scripts/pii-guard.sh", "public/site.txt")
    _git(main, "commit", "-qm", "init main")
    (main / "loop-team" / "runs").mkdir()
    (main / "loop-team" / "runs" / "x").write_text("private run artifact\n")
    (main / "loop-team" / "scratch_secret.md").write_text("private scratch — must not leak\n")

    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _init_repo(public, branch=BRANCH)
    _git(public, "remote", "add", "origin", str(bare))
    (public / "README.md").write_text("public repo\n")
    _git(public, "add", "README.md")
    _git(public, "commit", "-qm", "init public")
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
