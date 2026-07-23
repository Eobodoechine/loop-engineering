#!/usr/bin/env python3
"""run_and_record.py -- Phase 1 evidence-capture wrapper (spec:
loop-team/runs/2026-07-08_evidence-gate-phase1/specs/spec.md, "Public
interface #1").

Wraps an arbitrary command, executes it as a real subprocess, and records a
machine-checkable "proof snapshot" of what actually happened: the exact
argv, exit code, a hash of the combined stdout+stderr, sha256 hashes of any
argv token that resolves to a real on-disk file, and whether the git
worktree was dirty (for any auto-detected files) at capture time. This is
the mechanism `fixplan_closure_lint.py` v2's Proof-block-required /
snapshot-cross-check logic (Public interface #2 of the same spec) verifies
a `CLOSED` heading's cited evidence against -- it turns a hand-typed,
unverifiable closure claim into something a script can independently
re-check.

CANONICAL NO-OP FORM (AC13): for a closure with nothing file-specific to
cite -- e.g. a pure-prose/documentation fix with no command whose output is
itself the evidence -- the blessed canonical proof command is:

    python3 run_and_record.py -- true

`true` always exits 0 and produces no output, so this records a minimal,
honest "I ran something and it succeeded" snapshot without inventing
evidence that doesn't exist. Use this instead of improvising an unrelated
command just to have something to cite.

Convention matched from `commit_diff_reread.py` (read directly per this
spec's "Files to read" section): stdlib-only, manual `sys.argv` CLI,
`json.dumps` to stdout, `LOOP_GATE_DIR` env var + `~/.loop-gate` default,
TTL-sweep of stale gate-dir entries. Content-addressing here follows that
same file's REAL convention (confirmed by direct read, not assumed): the
hash-derived `key` is computed over a stable subset of the record that
excludes the volatile `captured_at` timestamp, while the timestamp is still
stored as a plain field in the record written to disk. This makes two
invocations of the identical command with identical output map to the same
key/snapshot path (idempotent overwrite), matching `commit_diff_reread.py`'s
own separation of content-hash vs. recorded-timestamp.

Exit codes:
    Mirrors the wrapped command's own exit code exactly (this script is a
    transparent wrapper, not a pass/fail judge) -- so
    `run_and_record.py -- false` itself exits nonzero, and
    `run_and_record.py -- true` itself exits 0.
    A usage error (missing `--` separator or no command given) exits 2.

Usage:
    python3 run_and_record.py -- <command...>

Example:
    python3 run_and_record.py -- echo hello
    python3 run_and_record.py -- true
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# Matches commit_diff_reread.py's SWEEP_TTL_S exactly, per this spec's
# instruction to match that file's TTL value and sweep style for
# consistency across the repo's gate-dir tooling.
SWEEP_TTL_S = 7 * 24 * 3600
GIT_TIMEOUT = 30

# COMMAND_TIMEOUT_S: default timeout (seconds) for the WRAPPED command --
# distinct from GIT_TIMEOUT above, which is scoped ONLY to this file's own
# internal, always-fast `git` calls (_resolve_repo_for_path,
# _compute_dirty_at_capture). The wrapped command is arbitrary and, by this
# script's own documented usage (module docstring / research/false-status-
# mechanical-verification-2026-07-08.md), can legitimately be a real test-
# suite run taking well over 30s -- so this default is minutes-scale, not
# seconds-scale. Overridable per-invocation via the RUN_AND_RECORD_TIMEOUT_S
# env var (read once at call time by _command_timeout_s()) so a test can
# exercise the timeout path in bounded time without changing this
# production default and without an in-process monkeypatch (every test in
# test_run_and_record.py invokes this script as a real subprocess, so only
# an env-var/CLI-flag-style override crosses that process boundary).
COMMAND_TIMEOUT_S = 600  # 10 minutes
PROOF_SCHEMA_VERSION = 1
PROOF_PRODUCER = "loop-team/harness/run_and_record.py"
PROOF_KEY_ALGORITHM = "run_and_record.v1"

# --- _gate_dir(): reuse commit_diff_reread.py's real implementation if it's
# importable (this script lives in the same directory, and Python puts a
# script's own directory on sys.path[0] when it's run directly, so this
# normally succeeds); otherwise fall back to a duplicate of its exact logic.
# Duplication reason: this script must still work standalone (e.g. if it's
# ever copied/invoked from a context where commit_diff_reread.py isn't on
# sys.path) without hard-crashing on import.
try:
    from commit_diff_reread import _gate_dir as _reused_gate_dir

    def _gate_dir():
        return _reused_gate_dir()
except ImportError:
    def _gate_dir():
        """Duplicated from commit_diff_reread.py's _gate_dir() (import
        fallback -- see comment above). Keep in sync with that file's own
        definition if it ever changes."""
        return os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))


def _proof_dir():
    return os.path.join(_gate_dir(), "proof")


def _sweep_stale(proof_dir):
    """Opportunistically remove snapshot files older than SWEEP_TTL_S.
    Hygiene only -- not a correctness dependency. Mirrors
    commit_diff_reread.py's own _sweep_stale, scoped to the proof/
    subdirectory."""
    now = time.time()
    try:
        for name in os.listdir(proof_dir):
            p = os.path.join(proof_dir, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > SWEEP_TTL_S:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _detect_files(command):
    """Auto-detect file paths: any token in `command`'s own argv (including
    the executable name itself) that resolves to an existing file on disk
    -- checked exactly as given, resolved against this process's own
    working directory, matching what the wrapped subprocess itself would
    see -- gets its current content sha256-hashed. Returns a dict keyed by
    the ORIGINAL argv token string (not a normalized/absolute form), so a
    caller can match a token back to exactly what it typed."""
    files = {}
    for token in command:
        if not os.path.isfile(token):
            continue
        try:
            with open(token, "rb") as f:
                data = f.read()
        except OSError:
            continue
        files[token] = hashlib.sha256(data).hexdigest()
    return files


def _resolve_repo_for_path(abs_path):
    """Resolve the git repo toplevel for abs_path's own directory. Returns
    the toplevel path, or None if abs_path is not inside a git repo.
    Mirrors commit_diff_reread.py's _resolve_repo convention (resolve from
    the file's own directory, not the process's cwd)."""
    directory = os.path.dirname(abs_path) or "."
    try:
        r = subprocess.run(
            ["git", "-C", directory, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def _compute_dirty_at_capture(files):
    """Round-4 plan-check fix: if zero files were auto-detected, return the
    FIXED value False directly, WITHOUT running `git status` at all -- an
    unscoped `git status --porcelain --` with no pathspec reports
    whole-working-tree dirtiness, which would wrongly entangle unrelated
    concurrent repo activity into this value. If one or more files WERE
    auto-detected, resolve the git repo from the first file's own
    directory: if not inside a git repo at all, return None (null -- "not
    applicable", distinct from the empty-files case's fixed False); if
    inside a repo, return True iff `git status --porcelain -- <files>`
    (naming those specific files, as absolute paths so the pathspec doesn't
    depend on which directory `git -C` puts the child process in) shows any
    output."""
    if not files:
        return False

    abs_paths = [os.path.abspath(p) for p in files]
    repo = _resolve_repo_for_path(abs_paths[0])
    if repo is None:
        return None

    try:
        r = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain", "--"] + abs_paths,
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(r.stdout.strip())


def _command_timeout_s():
    """Read RUN_AND_RECORD_TIMEOUT_S once at call time; fall back to
    COMMAND_TIMEOUT_S if unset or not a valid positive number. This is the
    override mechanism a test (or an unusual caller) uses to change the
    wrapped-command timeout without touching the production default."""
    raw = os.environ.get("RUN_AND_RECORD_TIMEOUT_S")
    if raw is None:
        return COMMAND_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return COMMAND_TIMEOUT_S
    if value <= 0:
        return COMMAND_TIMEOUT_S
    return value


def _key_for_record(record):
    """Round-1 plan-check fix #2: compute the content-addressing key over a
    `key_material` subset of the record that explicitly EXCLUDES
    `captured_at` (the only volatile field), matching
    commit_diff_reread.py's real convention of keeping timestamps out of
    the key. This makes two invocations of the identical command with
    identical output map to the SAME key (AC2), regardless of when each was
    run."""
    key_material = {
        "command": record["command"],
        "exit_code": record["exit_code"],
        "output_sha256": record["output_sha256"],
        "files": record["files"],
        "dirty_at_capture": record["dirty_at_capture"],
    }
    serialized = json.dumps(key_material, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _render_proof_block(record, snapshot_path):
    """Render the ready-to-paste `Proof:` block in the exact field order and
    format documented in the spec's Public interface #1."""
    lines = ["Proof:"]
    lines.append("- proof_schema_version: %s" % record["proof_schema_version"])
    lines.append("- proof_producer: %s" % record["proof_producer"])
    lines.append("- proof_key_algorithm: %s" % record["proof_key_algorithm"])
    lines.append("- command: %s" % " ".join(record["command"]))
    lines.append("- exit_code: %s" % record["exit_code"])
    lines.append("- proof_snapshot: %s" % snapshot_path)
    lines.append("- output_sha256: %s" % record["output_sha256"])
    if record["files"]:
        lines.append("- files: %s" % ", ".join(record["files"].keys()))
    lines.append("- verified_at: %s" % record["captured_at"])
    return "\n".join(lines)


def run_and_record(command):
    """Execute `command` as a real subprocess, build the full evidence
    record, write it to the gate dir's proof/ subdirectory, and return
    (exit_code, record, snapshot_path)."""
    timeout_s = _command_timeout_s()
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        # The wrapped command ran but did not finish within timeout_s --
        # distinct from the OSError branch below (which means the command
        # never started at all). subprocess.TimeoutExpired does NOT inherit
        # from OSError, so it needs its own except clause or it would crash
        # this process with an uncaught traceback instead of following the
        # script's normal error-reporting convention.
        print(json.dumps({
            "error": "command timed out after %s seconds" % timeout_s,
            "command": command,
            "timeout_s": timeout_s,
        }))
        return 2, None, None
    except OSError as e:
        # Wrapped command's own executable could not be found/run at all --
        # not a "wrapped command failed with an exit code" case, so there is
        # no meaningful exit code to mirror. Surface this as a usage/runtime
        # error distinct from a mirrored wrapped-command exit code.
        print(json.dumps({
            "error": "could not run command: %s" % e,
            "command": command,
        }))
        return 2, None, None

    stdout_bytes = result.stdout or b""
    stderr_bytes = result.stderr or b""
    # output_sha256 is defined as: sha256 of the raw stdout bytes,
    # immediately followed by the raw stderr bytes, with no separator
    # in between (stdout first, then stderr, concatenated directly).
    output_sha256 = hashlib.sha256(stdout_bytes + stderr_bytes).hexdigest()

    files = _detect_files(command)
    dirty_at_capture = _compute_dirty_at_capture(files)
    captured_at = _now_iso()

    record = {
        "proof_schema_version": PROOF_SCHEMA_VERSION,
        "proof_producer": PROOF_PRODUCER,
        "proof_key_algorithm": PROOF_KEY_ALGORITHM,
        "command": list(command),
        "exit_code": result.returncode,
        "output_sha256": output_sha256,
        "files": files,
        "dirty_at_capture": dirty_at_capture,
        "captured_at": captured_at,
    }

    key = _key_for_record(record)
    proof_dir = _proof_dir()
    os.makedirs(proof_dir, exist_ok=True)
    snapshot_path = os.path.join(proof_dir, "%s.json" % key)

    # Atomic write (write to a tmp file, then os.replace) -- a repeat
    # invocation with the same key_material safely overwrites the previous
    # snapshot's captured_at (AC2's idempotent-overwrite requirement), never
    # errors or skips because a file already exists at that path.
    tmp_path = snapshot_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(record, f)
    os.replace(tmp_path, snapshot_path)

    return result.returncode, record, snapshot_path


def main(argv):
    args = argv[1:]
    if not args or args[0] != "--":
        sys.stderr.write("usage: run_and_record.py -- <command...>\n")
        return 2

    command = args[1:]
    if not command:
        sys.stderr.write("usage: run_and_record.py -- <command...>\n")
        return 2

    _sweep_stale(_proof_dir())

    exit_code, record, snapshot_path = run_and_record(command)
    if record is None:
        # run_and_record() already printed its own error JSON.
        return exit_code

    print(json.dumps(record))
    print()
    print(_render_proof_block(record, snapshot_path))

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
