#!/usr/bin/env python3
"""Hermes `kanban_complete` closure gate plugin (P2.2).

Gates the `kanban_complete` tool on a *recomputed* slice-closure verdict from
live GitHub state at the head SHA -- never a worker-written claim.

Loader-independent: this module is a plain stdlib module (also imported
directly by the unit harness without the Hermes loader).

Callback contract (Hermes `pre_tool_call` seam, plugins.py ~2213):
    closure_gate_pre_tool_call(tool_name, args, task_id, ctx, ...)
Return values:
    None                                            -> allow the tool call
    {"action": "block", "message": <non-empty...>}  -> refuse the tool call
A directive without a non-empty `message` is SILENTLY IGNORED by the seam
(plugins.py ~2187-2192 -> FAIL-OPEN), so EVERY refusal carries a message,
and callback exceptions are swallowed by invoke_hook (plugins.py ~1937-1949)
-- so this module wraps everything in a catch-all that converts any
exception/timeout into a block WITH message. Only a GREEN recompute (or a
non-kanban_complete tool) may return None.
"""

import os
import shutil
import signal
import sqlite3
import subprocess

RECOMPUTE_NAME = "recompute_verdict.sh"
RECOMPUTE_TIMEOUT = 30  # hard cap per recompute; harness budget allows ~40s

DEFAULT_CONTEXT = "slice-closure-gate / slice-closure-gate"
DEFAULT_DB = os.path.expanduser("~/.hermes/kanban.db")
DEFAULT_CONF = os.path.expanduser("~/Claude/loop/closure-adapter/branches.conf")

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# config resolution: harness ctx object > environment > defaults
# ---------------------------------------------------------------------------


def _cfg(ctx):
    db = getattr(ctx, "kanban_db_path", None) if ctx is not None else None
    conf = getattr(ctx, "branches_conf_path", None) if ctx is not None else None
    context = getattr(ctx, "required_context", None) if ctx is not None else None
    if not db:
        db = os.environ.get("KANBAN_DB_PATH") or DEFAULT_DB
    if not conf:
        conf = os.environ.get("BRANCHES_CONF_PATH") or DEFAULT_CONF
    if not context:
        context = os.environ.get("CLOSURE_GATE_CONTEXT") or DEFAULT_CONTEXT
    return db, conf, context


def _block(message):
    return {"action": "block", "message": (message or "closure gate blocked").strip()[:200]}


def _task_branch(db_path, task_id):
    """Read `tasks.branch_name` for the task. Any read failure -> None."""
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=2)
        try:
            row = conn.execute(
                "SELECT branch_name FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    return row[0]


def _conf_mapping(conf_path, branch):
    """Look up `codex/<slice-id>` (branch) -> <owner>/<repo> in branches.conf.

    Line format: `codex/slice-x -> NEO-Venturez/wf-fix-test`  ('#' comments).
    """
    if not branch:
        return None
    try:
        with open(conf_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except Exception:
        return None
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or "->" not in line:
            continue
        key, _, value = line.partition("->")
        if key.strip() == branch:
            repo = value.strip()
            return repo or None
    return None


def _recompute_script():
    """Locate recompute_verdict.sh: PATH stub wins, then sibling on disk."""
    found = shutil.which(RECOMPUTE_NAME)
    if found:
        return found
    sibling = os.path.join(_PLUGIN_DIR, RECOMPUTE_NAME)
    return sibling if os.path.isfile(sibling) and os.access(sibling, os.X_OK) else None


def _kill_pg(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _run_recompute(repo, branch, context):
    script = _recompute_script()
    if not script:
        return _block("closure gate: recompute_verdict.sh not found on PATH (fail-closed)")
    try:
        proc = subprocess.Popen(
            [script, repo, branch, context],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=RECOMPUTE_TIMEOUT)
        except subprocess.TimeoutExpired:
            _kill_pg(proc)
            return _block(
                "closure gate: recompute timed out after %ds (fail-closed)"
                % RECOMPUTE_TIMEOUT
            )
    except Exception as exc:  # spool failures, EMFILE, ...
        return _block("closure gate: could not run recompute_verdict.sh: %s" % exc)
    if proc.returncode == 0 and (out or "").lstrip().startswith("GREEN "):
        return None  # allow
    line = next(
        (ln.strip() for ln in ((out or "") + "\n" + (err or "")).splitlines() if ln.strip()),
        "recompute_verdict.sh exited %s" % proc.returncode,
    )
    return _block(line)


def closure_gate_pre_tool_call(tool_name=None, args=None, task_id=None, ctx=None, **kwargs):
    """Hermes `pre_tool_call` callback gating `kanban_complete`.

    Never raises: every failure path returns a block WITH a non-empty
    `message` (seam swallows exceptions and ignores message-less blocks).
    """
    try:
        if (tool_name or "").lstrip() != "kanban_complete":
            return None
        db_path, conf_path, context = _cfg(ctx)
        if not task_id:
            return _block("no contract for this task: task_id unavailable")
        branch = _task_branch(db_path, task_id)
        if not branch:
            return _block(
                "no contract for this task: task %s has no branch_name "
                "(escaped path: owner removes/moves the task or mapping)" % task_id
            )
        repo = _conf_mapping(conf_path, branch)
        if not repo:
            return _block(
                "no contract for this task: branch %s is not mapped in %s"
                % (branch, conf_path)
            )
        verdict = _run_recompute(repo, branch, context)
        if verdict is not None:
            return verdict
        return None
    except BaseException as exc:  # catch-all wrapper: fail closed, never leak
        return _block("closure gate error (fail-closed): %s" % exc)


# alias so a generic loader discovery also finds it
pre_tool_call = closure_gate_pre_tool_call