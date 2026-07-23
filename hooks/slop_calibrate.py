#!/usr/bin/env python3
"""slop_calibrate.py — walk this repo's git history computing the slop-gate
metrics per commit transition; print CSV + suggested p75 (warn) / p95 (block)
thresholds. Calibration only — arming the block layer is a separate, PACE-gated
decision. Usage: python3 hooks/slop_calibrate.py [N_commits] [repo_path]"""
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slop_gate import erosion_metrics  # noqa: E402

TIMEOUT = 30


def _git(repo, *a):
    return subprocess.run(["git", "-C", repo] + list(a), capture_output=True,
                          text=True, timeout=TIMEOUT)


def commit_metrics(repo, sha):
    """Aggregate erosion over all tracked .py files at a commit."""
    files = [f for f in _git(repo, "ls-tree", "-r", "--name-only", sha).stdout.splitlines()
             if f.endswith(".py") and "/fixtures/" not in f and "/tests/" not in f]
    mass = high = 0.0
    for f in files:
        r = _git(repo, "show", "%s:%s" % (sha, f))
        if r.returncode != 0:
            continue
        try:
            m = erosion_metrics(r.stdout)
        except Exception:
            continue
        w = m["total_sloc"] or 1
        mass += w
        high += (m["erosion_mass_pct"] / 100.0) * w
    return (100.0 * high / mass) if mass else 0.0


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--commits", type=int, default=30)
    ap.add_argument("repo", nargs="?", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()
    n = args.commits
    repo = os.path.abspath(args.repo)
    shas = _git(repo, "log", "--format=%h", "-n", str(n)).stdout.split()
    shas.reverse()
    print("commit,erosion_mass_pct,delta")
    deltas, prev = [], None
    for sha in shas:
        pct = commit_metrics(repo, sha)
        d = (pct - prev) if prev is not None else 0.0
        print("%s,%.2f,%.2f" % (sha, pct, d))
        if prev is not None:
            deltas.append(d)
        prev = pct
    if deltas:
        deltas.sort()
        p75 = deltas[int(0.75 * (len(deltas) - 1))]
        p95 = deltas[int(0.95 * (len(deltas) - 1))]
        pos = [d for d in deltas if d > 0]
        sys.stderr.write(
            "# transitions=%d positive=%d  suggested: warn>=%.2fpp (p75) block>=%.2fpp (p95)\n"
            "# NOTE: docs/tests-heavy history yields many zero deltas — if most deltas are 0,\n"
            "# these percentiles are degenerate; do NOT arm thresholds on them (spec caveat).\n"
            % (len(deltas), len(pos), p75, p95))
    return 0


if __name__ == "__main__":
    sys.exit(main())
