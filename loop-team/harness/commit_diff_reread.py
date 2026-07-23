#!/usr/bin/env python3
"""commit_diff_reread.py -- closes the review-to-commit gap (H-REVIEW-COMMIT-1).

Deterministic, dependency-free CLI Oga invokes directly via Bash before ever
running `git commit` on a shared loop-team framework file (orchestrator.md,
role briefs, RUN.md, VERIFIER.md, VERIFIER_RENTALS.md, fix_plan.md,
search_playbook.md, and other loop-team/repo-root prose/config files -- see
spec's Scope list). Content on disk that lands in a `git commit` diff can
silently include text that was never reviewed -- confirmed twice in this
repo on 2026-07-02 (commit `96693f8`, reverted; commit `5884604`, an
unrelated ~230-word paragraph rode along undetected). This tool closes the
gap directly and mechanically, independent of root cause, by re-diffing the
exact bytes immediately before every commit against what was actually
reviewed.

Convention matched from `research_authenticity_check.py`: stdlib-only,
manual `sys.argv` CLI, `json.dumps` to stdout, documented exit codes.
`LOOP_GATE_DIR` env var + `~/.loop-gate` default + TTL-sweep pattern reused
from `hooks/micro_step_gates.py`'s `_gate_dir()` / `_sweep_stale()`.

Subcommands:
  record <file>                          -- snapshot the file's current
                                             on-disk bytes as "reviewed".
  check <file>                           -- compare current bytes against
                                             the last recorded snapshot.
  commit <file> [<file2> ...] -- <msg>   -- re-check ALL listed files inside
                                             this single invocation (closes
                                             the TOCTOU window), then git add
                                             + commit iff every file matches;
                                             all-or-nothing.

Exit codes:
  record: 0 success, 2 file missing/unreadable.
  check:  0 match, 1 mismatch (including "no prior snapshot").
  commit: 0 committed, 1 blocked (a file mismatched or had no snapshot),
          2 usage error (bad args, or listed files span different repos).

Usage:
    python3 commit_diff_reread.py record <file>
    python3 commit_diff_reread.py check <file>
    python3 commit_diff_reread.py commit <file> [<file2> ...] -- <message>
"""
import difflib
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

SWEEP_TTL_S = 7 * 24 * 3600  # matches micro_step_gates.py's SWEEP_TTL_S
GIT_TIMEOUT = 30


def _gate_dir():
    """Same env var + default convention as micro_step_gates.py's _gate_dir()."""
    return os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))


def _reviewed_dir():
    return os.path.join(_gate_dir(), "reviewed")


def _sweep_stale(reviewed_dir):
    """Opportunistically remove snapshots older than SWEEP_TTL_S. Hygiene
    only -- not a correctness dependency (mirrors micro_step_gates.py's
    _sweep_stale, scoped to the reviewed/ subdirectory)."""
    now = time.time()
    try:
        for name in os.listdir(reviewed_dir):
            p = os.path.join(reviewed_dir, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > SWEEP_TTL_S:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def _snapshot_path(abs_path):
    key = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:16]
    return os.path.join(_reviewed_dir(), "%s.json" % key)


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load_snapshot(abs_path):
    """Return the parsed snapshot dict for abs_path, or None if absent/corrupt."""
    snap_path = _snapshot_path(abs_path)
    if not os.path.isfile(snap_path):
        return None
    try:
        with open(snap_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cmd_record(abs_path):
    """record <file>: snapshot the file's current on-disk bytes as reviewed."""
    reviewed_dir = _reviewed_dir()
    _sweep_stale(reviewed_dir)

    try:
        with open(abs_path, "rb") as f:
            data = f.read()
    except OSError as e:
        print(json.dumps({
            "recorded": False,
            "file": abs_path,
            "error": "could not read file: %s" % e,
        }))
        return 2

    sha256 = _sha256_bytes(data)
    reviewed_at = _now_iso()
    try:
        text_content = data.decode("utf-8")
    except UnicodeDecodeError:
        text_content = data.decode("utf-8", errors="replace")

    snapshot = {
        "file": abs_path,
        "sha256": sha256,
        "reviewed_at": reviewed_at,
        "content": text_content,
    }

    os.makedirs(reviewed_dir, exist_ok=True)
    snap_path = _snapshot_path(abs_path)
    tmp_path = snap_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f)
    os.replace(tmp_path, snap_path)

    print(json.dumps({
        "recorded": True,
        "file": abs_path,
        "sha256": sha256,
        "reviewed_at": reviewed_at,
    }))
    return 0


def _check_result(abs_path):
    """Shared check logic used by both `check` and `commit`. Returns
    (exit_code, result_dict) where result_dict matches the documented
    per-file `check` JSON shape (used directly for `check`, and nested
    inside `commit`'s `results` array)."""
    _sweep_stale(_reviewed_dir())

    snapshot = _load_snapshot(abs_path)
    if snapshot is None:
        return 1, {
            "match": False,
            "file": abs_path,
            "error": "no_reviewed_snapshot",
        }

    try:
        with open(abs_path, "rb") as f:
            current_bytes = f.read()
    except OSError as e:
        return 1, {
            "match": False,
            "file": abs_path,
            "error": "could not read file: %s" % e,
        }

    current_sha256 = _sha256_bytes(current_bytes)
    if current_sha256 == snapshot.get("sha256"):
        return 0, {
            "match": True,
            "file": abs_path,
            "reviewed_at": snapshot.get("reviewed_at"),
        }

    reviewed_content = snapshot.get("content", "")
    try:
        current_content = current_bytes.decode("utf-8")
    except UnicodeDecodeError:
        current_content = current_bytes.decode("utf-8", errors="replace")

    diff = "".join(difflib.unified_diff(
        reviewed_content.splitlines(keepends=True),
        current_content.splitlines(keepends=True),
        fromfile="reviewed (%s)" % snapshot.get("reviewed_at", ""),
        tofile="current (%s)" % abs_path,
    ))

    return 1, {
        "match": False,
        "file": abs_path,
        "reviewed_at": snapshot.get("reviewed_at"),
        "diff": diff,
    }


def cmd_check(abs_path):
    """check <file>: compare current on-disk bytes against the last recorded
    snapshot for that exact absolute path."""
    code, result = _check_result(abs_path)
    print(json.dumps(result))
    return code


def _git(repo_dir, *args, timeout=GIT_TIMEOUT):
    return subprocess.run(["git", "-C", repo_dir] + list(args),
                           capture_output=True, text=True, timeout=timeout)


def _resolve_repo(abs_path):
    """Resolve the git repo toplevel for abs_path's own directory (not CWD).
    Returns the toplevel path, or None if abs_path is not inside a git repo."""
    directory = os.path.dirname(abs_path)
    r = subprocess.run(
        ["git", "-C", directory, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=GIT_TIMEOUT,
    )
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def cmd_commit(files, message):
    """commit <file> [<file2> ...] -- <message>: re-check EVERY listed file's
    current on-disk hash against its last recorded snapshot, all within this
    single invocation, immediately before touching git. All-or-nothing."""
    abs_paths = [os.path.abspath(f) for f in files]

    # Resolve each file's repo from its OWN directory, not CWD. All listed
    # files must resolve to the same repo, or this is a usage error.
    repos = []
    for abs_path in abs_paths:
        repo = _resolve_repo(abs_path)
        if repo is None:
            print(json.dumps({
                "committed": False,
                "error": "usage_error",
                "message": "could not resolve a git repo for %s" % abs_path,
            }))
            return 2
        repos.append(repo)

    distinct_repos = set(repos)
    if len(distinct_repos) > 1:
        print(json.dumps({
            "committed": False,
            "error": "usage_error",
            "message": (
                "listed files resolve to different git repos: %s"
                % sorted(distinct_repos)
            ),
        }))
        return 2

    repo = repos[0]

    # Re-check EVERY file within this single invocation (closes the TOCTOU
    # window separate `check` calls across turns would leave open).
    results = []
    all_match = True
    for abs_path in abs_paths:
        code, result = _check_result(abs_path)
        results.append(result)
        if code != 0:
            all_match = False

    if not all_match:
        print(json.dumps({
            "committed": False,
            "results": results,
        }))
        return 1

    add_result = _git(repo, "add", *abs_paths)
    if add_result.returncode != 0:
        print(json.dumps({
            "committed": False,
            "error": "git_add_failed",
            "message": add_result.stderr.strip(),
            "results": results,
        }))
        return 1

    commit_result = _git(repo, "commit", "-m", message)
    if commit_result.returncode != 0:
        print(json.dumps({
            "committed": False,
            "error": "git_commit_failed",
            "message": commit_result.stderr.strip(),
            "results": results,
        }))
        return 1

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    print(json.dumps({
        "committed": True,
        "files": abs_paths,
        "commit": head,
    }))
    return 0


def _split_commit_args(args):
    """Split `<file> [<file2> ...] -- <message...>` into (files, message).
    Returns (None, None) if the literal `--` separator is missing or there
    is no message after it."""
    if "--" not in args:
        return None, None
    sep = args.index("--")
    files = args[:sep]
    message_parts = args[sep + 1:]
    if not files or not message_parts:
        return None, None
    return files, " ".join(message_parts)


def main(argv):
    args = argv[1:]
    if not args:
        print(json.dumps({"error": "usage: commit_diff_reread.py <record|check|commit> ..."}))
        return 2

    subcommand = args[0]
    rest = args[1:]

    if subcommand == "record":
        if len(rest) != 1:
            print(json.dumps({"error": "usage: commit_diff_reread.py record <file>"}))
            return 2
        return cmd_record(os.path.abspath(rest[0]))

    if subcommand == "check":
        if len(rest) != 1:
            print(json.dumps({"error": "usage: commit_diff_reread.py check <file>"}))
            return 2
        return cmd_check(os.path.abspath(rest[0]))

    if subcommand == "commit":
        files, message = _split_commit_args(rest)
        if files is None:
            print(json.dumps({
                "error": (
                    "usage: commit_diff_reread.py commit <file> [<file2> ...] "
                    "-- <message>"
                ),
            }))
            return 2
        return cmd_commit(files, message)

    print(json.dumps({"error": "unknown subcommand: %s" % subcommand}))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
