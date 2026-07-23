#!/usr/bin/env python3
"""slop_gate.py — SHADOW-MODE code-erosion metrics on the uncommitted diff.

NEVER blocks (exit 0 always) in v1: emits one JSON line to
$LOOP_GATE_DIR/<session>_slop.jsonl plus a human-readable stderr summary.
Arming a block layer is a later, PACE-gated decision after shadow calibration.

Metrics (SlopCodeBench definitions reimplemented on radon — MIT, arXiv 2603.24755):
  erosion_mass_pct : share of total complexity mass (CC * sqrt(SLOC)) in functions
                     with CC > 10; reported as before/after/delta for the diff.
  lint_flags       : ruff F401,F841,ERA001,E722 counts on changed files (if ruff).
  fn_len_median    : median function NLOC before/after (radon raw fallback: file-level).

Also importable: `erosion_metrics(source_text)` for the evals slop_metrics target.
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

HIGH_CC = 10
_EXCLUDE = re.compile(r'(^|/)(tests?|fixtures?|generated|vendor|node_modules)/|_pb2\.py$')
TIMEOUT = 30


def _have(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def erosion_metrics(source_text):
    """Deterministic erosion metrics for one Python source text (radon required).
    Returns {erosion_mass_pct, n_functions, high_cc_functions, fn_len_median}."""
    from radon.complexity import cc_visit
    from radon.raw import analyze
    blocks = cc_visit(source_text)
    masses, high_mass = [], 0.0
    lengths = []
    for b in blocks:
        sloc = max(1, (b.endline - b.lineno + 1))
        mass = b.complexity * math.sqrt(sloc)
        masses.append(mass)
        lengths.append(sloc)
        if b.complexity > HIGH_CC:
            high_mass += mass
    total = sum(masses)
    lengths.sort()
    return {
        "erosion_mass_pct": (100.0 * high_mass / total) if total else 0.0,
        "n_functions": len(blocks),
        "high_cc_functions": sum(1 for b in blocks if b.complexity > HIGH_CC),
        "fn_len_median": lengths[len(lengths) // 2] if lengths else 0,
        "total_sloc": analyze(source_text).sloc,
    }


def _repo_erosion(target, paths, at_head=False):
    """Aggregate erosion over the given .py paths, worktree or HEAD versions."""
    agg = {"mass": 0.0, "high": 0.0, "lens": []}
    for path in paths:
        try:
            if at_head:
                r = subprocess.run(["git", "-C", target, "show", "HEAD:%s" % path],
                                   capture_output=True, text=True, timeout=TIMEOUT)
                if r.returncode != 0:
                    continue
                src = r.stdout
            else:
                src = open(os.path.join(target, path), encoding="utf-8").read()
            m = erosion_metrics(src)
        except Exception:
            continue
        # re-derive mass components from the single-file metrics
        agg["mass"] += m["total_sloc"] or 1
        agg["high"] += (m["erosion_mass_pct"] / 100.0) * (m["total_sloc"] or 1)
        agg["lens"].append(m["fn_len_median"])
    pct = 100.0 * agg["high"] / agg["mass"] if agg["mass"] else 0.0
    agg["lens"].sort()
    med = agg["lens"][len(agg["lens"]) // 2] if agg["lens"] else 0
    return pct, med


def _changed_py(target):
    r = subprocess.run(["git", "-C", target, "diff", "HEAD", "--name-only"],
                       capture_output=True, text=True, timeout=TIMEOUT)
    out = [x.strip() for x in r.stdout.splitlines() if x.strip().endswith(".py")
           and not _EXCLUDE.search(x.strip())]
    r2 = subprocess.run(["git", "-C", target, "ls-files", "--others",
                         "--exclude-standard"], capture_output=True, text=True,
                        timeout=TIMEOUT)
    out += [x.strip() for x in r2.stdout.splitlines() if x.strip().endswith(".py")
            and not _EXCLUDE.search(x.strip())]
    return sorted(set(out))


def shadow_report(target, session_id=None):
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "target": target,
              "mode": "shadow"}
    missing = [m for m in ("radon",) if not _have(m)]
    have_ruff = subprocess.run(["ruff", "--version"], capture_output=True
                               ).returncode == 0 if _which("ruff") else False
    if missing:
        record.update({"shadow": "tools unavailable", "missing": missing})
        return record
    changed = _changed_py(target)
    record["changed_py"] = changed
    if not changed:
        record["note"] = "no uncommitted python changes"
        return record
    before_pct, before_med = _repo_erosion(target, changed, at_head=True)
    after_pct, after_med = _repo_erosion(target, changed, at_head=False)
    record["erosion_mass_pct"] = {"before": round(before_pct, 2),
                                  "after": round(after_pct, 2),
                                  "delta": round(after_pct - before_pct, 2)}
    record["fn_len_median"] = {"before": before_med, "after": after_med}
    if have_ruff:
        r = subprocess.run(["ruff", "check", "--select", "F401,F841,ERA001,E722",
                            "--output-format", "json", "--isolated"] +
                           [os.path.join(target, c) for c in changed],
                           capture_output=True, text=True, timeout=TIMEOUT)
        try:
            record["lint_flags"] = len(json.loads(r.stdout or "[]"))
        except ValueError:
            record["lint_flags"] = None
    else:
        record["lint_flags"] = None
        record.setdefault("missing", []).append("ruff")
    return record


def _which(prog):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.isfile(os.path.join(d, prog)):
            return True
    return False


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    session_id = sys.argv[2] if len(sys.argv) > 2 else None
    rec = shadow_report(os.path.abspath(os.path.expanduser(target)), session_id)
    if session_id:
        gate_dir = os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
        os.makedirs(gate_dir, exist_ok=True)
        with open(os.path.join(gate_dir, "%s_slop.jsonl" % session_id), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    sys.stderr.write("[slop-gate shadow] %s\n" % json.dumps(rec))
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
