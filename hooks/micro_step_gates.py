#!/usr/bin/env python3
"""micro_step_gates.py — deterministic micro-step build gates (Stop-hook layer).

Called by loop_stop_guard.py inside a defensive wrapper: ANY exception here must
result in ALLOW (the module may be mid-build in the very session whose Stop hook
loads it). This module therefore never calls sys.exit; it returns verdicts.

Gates (spec: runs/2026-07-01_micro-step-loop/spec.md AC-B1/B2):
  1. thrash-past-green  — a green checkpoint verify must be committed before the
     turn ends, when a Coder was dispatched after it and the tree is dirty.
  2. step-size          — uncommitted code diff vs HEAD > MAX_STEP_LINES.
  3. retry-cap          — third consecutive same-signature failing verify.
  4. testmon impact gate — impacted tests must run green for uncommitted changes;
     orphan modules (no test exercises them) block unless glob-excluded.

Activation requires BOTH the loop-team orchestrator marker in the transcript and a
fresh $LOOP_GATE_DIR/<session>_target file naming a git repo. Everything else is a
silent allow. Detection markers are built dynamically so reading this file never
arms any guard.
"""
import fnmatch
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

MAX_STEP_LINES = 200
TARGET_TTL_S = 24 * 3600
SWEEP_TTL_S = 7 * 24 * 3600
GIT_TIMEOUT = 15
PYTEST_TIMEOUT = 180

# Dynamic markers (never contiguous in source; see test sweep).
_M_OGA = "you are " + "**oga**"
_M_PLAYBOOK = "orchestrator " + "playbook"

_CODE_EXT = re.compile(
    r'\.(py|ts|tsx|js|jsx|go|rs|java|rb|sh|php|cpp|cc|c|h|swift|kt|css|vue|ya?ml|json|sql)$',
    re.I)
_STEP_EXCLUDE = re.compile(r'(^|/)(tests?|fixtures?|generated|vendor|node_modules)/|_pb2\.py$')
_CODER_PAT = re.compile(r'role:\s*coder\b|\bcoder for\b|roles/coder')
_CONFIG_FILES = ("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")


def _gate_dir():
    return os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))


def _sweep_stale(gate_dir):
    now = time.time()
    try:
        for name in os.listdir(gate_dir):
            p = os.path.join(gate_dir, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > SWEEP_TTL_S:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def _git(target, *args, timeout=GIT_TIMEOUT):
    return subprocess.run(["git", "-C", target] + list(args),
                          capture_output=True, text=True, timeout=timeout)


def _read_events(tpath):
    events = []
    with open(tpath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
    return events


def _content(e):
    m = e.get("message")
    if isinstance(m, dict):
        return m.get("content", [])
    return e.get("content", [])


def _parts(events, ptype):
    for i, e in enumerate(events):
        c = _content(e)
        if isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == ptype:
                    yield i, e, p


def _result_text(part):
    c = part.get("content", "")
    if isinstance(c, list):
        c = " ".join((x.get("text", "") if isinstance(x, dict) else str(x)) for x in c)
    return str(c)


def _is_verify_result(text):
    """Classify a tool_result as a verify/pytest run: returns 'green'/'red'/None."""
    t = text.lower()
    if '"passed": true' in t:
        return "green"
    if '"passed": false' in t:
        return "red"
    if re.search(r'\b\d+ passed\b', t) and not re.search(r'\b\d+ (failed|error)', t):
        # pytest summary with no failures
        if "collected" in t or "passed" in t:
            return "green"
    if re.search(r'\b\d+ (failed|error)', t) or "= failures =" in t:
        return "red"
    return None


def _event_epoch(e):
    ts = e.get("timestamp") or (e.get("message", {}) or {}).get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _dirty_code_files(target):
    r = _git(target, "status", "--porcelain")
    out = []
    for line in r.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if _CODE_EXT.search(path) and not _STEP_EXCLUDE.search(path):
            out.append(path)
    return out


def _changed_since_head(target):
    """All uncommitted changed paths (tracked modified + untracked), excluding
    hidden files/dirs — tool artifacts like .testmondata/.pytest_cache/.gate
    must never flip the full-suite classification or read as changed code."""
    paths = set()
    r = _git(target, "diff", "HEAD", "--name-only")
    paths.update(x.strip() for x in r.stdout.splitlines() if x.strip())
    r = _git(target, "ls-files", "--others", "--exclude-standard")
    paths.update(x.strip() for x in r.stdout.splitlines() if x.strip())
    return sorted(x for x in paths
                  if not any(part.startswith(".") for part in x.split("/")))


def _activation(data):
    """Return (target, session_id) when gates are armed, else None."""
    tpath = data.get("transcript_path")
    if not tpath or not os.path.exists(tpath):
        return None
    blob = open(tpath, encoding="utf-8", errors="ignore").read().lower()
    if _M_OGA not in blob and _M_PLAYBOOK not in blob:
        return None
    gate_dir = _gate_dir()
    _sweep_stale(gate_dir)
    session_id = data.get("session_id", "") or ""
    if not session_id:
        return None
    tfile = os.path.join(gate_dir, "%s_target" % session_id)
    if not os.path.isfile(tfile):
        return None
    if time.time() - os.path.getmtime(tfile) > TARGET_TTL_S:
        try:
            os.remove(tfile)
        except OSError:
            pass
        return None
    target = os.path.expanduser(open(tfile, encoding="utf-8").read().strip())
    if not os.path.isdir(os.path.join(target, ".git")):
        return None
    return target, session_id


# ── gate 3 helper: signature persistence ─────────────────────────────────────
def _load_sigs(session_id):
    p = os.path.join(_gate_dir(), "%s_signatures.json" % session_id)
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except ValueError:
            return []
    return []


def _save_sigs(session_id, sigs):
    p = os.path.join(_gate_dir(), "%s_signatures.json" % session_id)
    json.dump(sigs[-20:], open(p, "w", encoding="utf-8"))


def _signature(text):
    import sys as _s
    _s.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "loop-team"))
    try:
        from harness.stall_detector import error_signature
        return error_signature(text)
    except Exception:
        # degraded: normalized tail
        return re.sub(r'\d+', 'N', text.strip().lower())[-200:]


# ── the gates ────────────────────────────────────────────────────────────────
def run(data):
    """Entry point. Returns (blocked: bool, message: str). Never raises to caller
    contract — loop_stop_guard still wraps us defensively."""
    act = _activation(data)
    if not act:
        return (False, "")
    target, session_id = act

    events = _read_events(data["transcript_path"])

    # Current-turn slice (same semantics as loop_stop_guard): gate 3 must consume
    # each red verify exactly ONCE — the transcript is re-scanned on every Stop,
    # so appending from the full history would double-count earlier turns.
    turn_start = 0
    for i in range(len(events) - 1, -1, -1):
        e = events[i]
        role = e.get("role") or (e.get("message", {}) or {}).get("role", "")
        c = _content(e)
        is_tool_result = isinstance(c, list) and any(
            isinstance(x, dict) and x.get("type") == "tool_result" for x in c)
        if role == "user" and not is_tool_result:
            turn_start = i
            break

    # Collect verify tool_results in order (full transcript for gate 1's
    # cross-turn thrash view; per-turn subset for gate 3 appends)
    verifies = []  # (index, epoch, verdict, text)
    for i, e, p in _parts(events, "tool_result"):
        text = _result_text(p)
        v = _is_verify_result(text)
        if v:
            verifies.append((i, _event_epoch(e), v, text))

    # Gate 3 state: append ONLY this turn's failing signatures
    sigs = _load_sigs(session_id)
    for (i, _, v, t) in verifies:
        if v == "red" and i >= turn_start:
            sigs.append(_signature(t))
    _save_sigs(session_id, sigs)
    stall_now = len(sigs) >= 2 and sigs[-1] == sigs[-2]
    if len(sigs) >= 3 and sigs[-1] == sigs[-2] == sigs[-3]:
        return (True,
                "[MICRO-STEP GATE: retry-cap] The same failure signature has now recurred "
                "on 3 consecutive verify runs. Do NOT dispatch the Coder again on this "
                "error. Escalate: dispatch the Researcher (Mode B) with the failing test, "
                "full traceback, diffs tried, dep versions, and the stall signature — or "
                "escalate to the human with the dossier. (orchestrator.md micro-step rule 4)")

    # Gate 2: step-size on uncommitted code diff
    r = _git(target, "diff", "HEAD", "--numstat")
    changed_lines = 0
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            add, dele, path = parts
            if _CODE_EXT.search(path) and not _STEP_EXCLUDE.search(path):
                try:
                    changed_lines += int(add) + int(dele)
                except ValueError:
                    pass
    if changed_lines > MAX_STEP_LINES:
        return (True,
                "[MICRO-STEP GATE: step-size] %d uncommitted changed code lines in %s "
                "(max %d per micro-step). Commit what you have (a WIP commit if red) "
                "before ending the turn — an uncheckpointed pile is how verified work "
                "gets destroyed. (orchestrator.md micro-step rule 1)"
                % (changed_lines, target, MAX_STEP_LINES))

    # Gate 1: thrash-past-green (recoverable slice only)
    if verifies and not stall_now:
        gi, gepoch, gv, _ = verifies[-1]
        if gv == "green" and gepoch is not None:
            # (iii) Coder dispatch after the green event
            coder_after = any(
                i > gi and p.get("name", "").lower() in ("task", "agent", "subagent")
                and _CODER_PAT.search(json.dumps(p.get("input", "")).lower())
                for i, e, p in _parts(events, "tool_use"))
            if coder_after:
                # (ii) zero commits since the green event
                r = _git(target, "log", "-1", "--format=%ct")
                try:
                    last_commit = int(r.stdout.strip() or 0)
                except ValueError:
                    last_commit = 0
                if last_commit < gepoch and _dirty_code_files(target):
                    return (True,
                            "[MICRO-STEP GATE: thrash-past-green] The last verify was GREEN, "
                            "a Coder was dispatched after it, and %s still has uncommitted "
                            "code changes with no commit since the green run. Commit the "
                            "green state (git checkpoint) before ending the turn. "
                            "(orchestrator.md micro-step rule 2/5)" % target)

    # Gate 4: testmon impact gate on uncommitted changes
    dirty = _dirty_code_files(target)
    if dirty:
        blocked, msg = _testmon_gate(target, session_id)
        if blocked:
            return (True, msg)

    return (False, "")


def _resolve_python(target, session_id):
    pfile = os.path.join(_gate_dir(), "%s_python" % session_id)
    if os.path.isfile(pfile):
        p = os.path.expanduser(open(pfile, encoding="utf-8").read().strip())
        if p:
            return p
    venv = os.path.join(target, ".venv", "bin", "python")
    if os.path.isfile(venv):
        return venv
    return "python3"


def _load_exclusions(target):
    p = os.path.join(target, ".gate", "subprocess_tested.globs")
    if os.path.isfile(p):
        return [l.strip() for l in open(p, encoding="utf-8") if l.strip()
                and not l.startswith("#")]
    return []


def _testmon_gate(target, session_id):
    py = _resolve_python(target, session_id)
    probe = subprocess.run([py, "-c", "import testmon"], capture_output=True,
                           timeout=GIT_TIMEOUT)
    if probe.returncode != 0:
        import sys
        sys.stderr.write("[micro-step-gates] testmon gate SKIPPED: "
                         "pytest-testmon not importable via %s\n" % py)
        return (False, "")

    changed = _changed_since_head(target)
    full_suite = any((not c.endswith(".py")) or os.path.basename(c) in _CONFIG_FILES
                     or c.startswith("requirements") for c in changed)
    cmd = [py, "-m", "pytest", "-q"] + ([] if full_suite else ["--testmon"])
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # same-second same-size edits can be
    # masked by a stale .pyc (mtime+size check) — gate runs must not seed pycs
    run = subprocess.run(cmd, cwd=target, capture_output=True, text=True,
                         timeout=PYTEST_TIMEOUT, env=env)
    if run.returncode not in (0, 5):  # 5 = no tests collected (testmon: nothing impacted)
        tail = (run.stdout + run.stderr)[-600:]
        return (True,
                "[MICRO-STEP GATE: impacted-tests] %s failed for the uncommitted "
                "changes in %s. Fix before checkpointing.\n%s"
                % ("Full suite" if full_suite else "Impacted tests (testmon)", target, tail))

    if full_suite:
        return (False, "")

    # Orphan + freshness checks against .testmondata
    db = os.path.join(target, ".testmondata")
    if not os.path.isfile(db):
        return (False, "")  # cold cache: the --testmon run above just bootstrapped it
    excl = _load_exclusions(target)
    changed_py = [c for c in changed if c.endswith(".py")
                  and not _STEP_EXCLUDE.search(c) and os.path.isfile(os.path.join(target, c))]
    try:
        con = sqlite3.connect(db)
        cur = con.cursor()
        # A repo whose DB recorded zero test executions has no impact map at all —
        # "everything is an orphan" is verify.py's zero-test problem, not this
        # gate's. Skip orphan/freshness rather than block every file.
        n_tests = cur.execute("SELECT COUNT(*) FROM test_execution").fetchone()[0]
        if n_tests == 0:
            con.close()
            return (False, "")
        for f in changed_py:
            n = cur.execute("SELECT COUNT(*) FROM file_fp WHERE filename=?", (f,)).fetchone()[0]
            if n == 0:
                if any(fnmatch.fnmatch(f, g) for g in excl):
                    import sys
                    sys.stderr.write("[micro-step-gates] orphan (excluded, subprocess-"
                                     "tested): %s\n" % f)
                    continue
                return (True,
                        "[MICRO-STEP GATE: orphan-module] No test exercises %s — testmon "
                        "selected nothing for it. Write a test that imports/executes it "
                        "before checkpointing (or, if it is only exercised via subprocess, "
                        "add it to .gate/subprocess_tested.globs with justification)." % f)
            cur2 = cur.execute("SELECT fsha FROM file_fp WHERE filename=?", (f,)).fetchall()
            blob = _git(target, "hash-object", f).stdout.strip()
            if blob and cur2 and not any(row[0] == blob for row in cur2):
                return (True,
                        "[MICRO-STEP GATE: stale-testmon] .testmondata does not reflect the "
                        "current contents of %s — rerun the impacted tests (pytest "
                        "--testmon); if only comments/whitespace changed the DB "
                        "may not refresh — checkpoint the commit to clear this "
                        "gate." % f)
        con.close()
    except sqlite3.Error:
        return (False, "")  # degraded DB: fail-open (the test run above already passed)
    return (False, "")
