#!/usr/bin/env python3
"""Loop Team -- independent tree-enumeration verifier (AC4).

Deliberately SEPARATE from `git filter-repo`'s own internal path-matching
logic and from `full_history_scan.py`'s blob-scanning logic: this module
re-walks `git rev-list --all` and, for every commit, re-lists the FULL tree
via `git ls-tree -r <sha> --name-only`, re-checking each path against
    ^(public|loop-team/runs|runs)(/|$)
Zero matches are required across every commit for a rewritten mirror to
pass. This exists so that a bug in filter-repo's own path-matching (or in
the scanner's blob enumeration, which this module does NOT share any code
with) cannot silently mask a leftover public/runs path -- an independent,
from-scratch re-implementation of "is this path root really gone
everywhere" is the actual proof, not filter-repo's exit code alone.

This module does not mutate the target repo -- `git rev-list` / `git
ls-tree` are read-only.

Usage:
    python3 tree_verify.py --repo <path>

Exit codes:
    0  zero matches across every commit -- verified clean.
    1  at least one match found -- NOT clean; details printed.
    2  usage/execution error (repo unreadable, git command failed, etc).
"""
import argparse
import json
import re
import subprocess
import sys

GIT_TIMEOUT = 300

# Exactly the regex the spec and test_path_removal.py document: three
# distinct path roots -- public/, loop-team/runs/, and top-level runs/ --
# anchored to a full path SEGMENT (not a loose substring), matching either
# the bare root name itself (e.g. "runs" with no trailing slash) or the
# root followed by a slash.
REMOVED_ROOTS_RE = re.compile(r"^(public|loop-team/runs|runs)(/|$)")


class TreeVerifyError(Exception):
    pass


def _run_git(repo, args, timeout=GIT_TIMEOUT):
    try:
        p = subprocess.run(
            ["git", "-C", repo] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise TreeVerifyError("git invocation failed: git -C %s %s (%s)" % (repo, " ".join(args), e))
    if p.returncode != 0:
        raise TreeVerifyError(
            "git command failed (exit %d): git -C %s %s\nstderr: %s"
            % (p.returncode, repo, " ".join(args), p.stderr)
        )
    return p.stdout


def rev_list_all(repo):
    out = _run_git(repo, ["rev-list", "--all"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def ls_tree_paths(repo, sha):
    out = _run_git(repo, ["ls-tree", "-r", sha, "--name-only"])
    return [line for line in out.splitlines() if line]


def paths_matching_removed_roots(repo, sha):
    """The independent AC4 check for a single commit: re-list its tree and
    re-grep every path against REMOVED_ROOTS_RE from scratch."""
    return [p for p in ls_tree_paths(repo, sha) if REMOVED_ROOTS_RE.match(p)]


def verify_tree(repo):
    """Full AC4 pipeline: walk every commit in `git rev-list --all` and
    re-check its full tree. Returns a report dict:
        {"clean": bool, "commits_scanned": int,
         "matches": [{"commit": sha, "paths": [...]}]}
    Raises TreeVerifyError if the repo/commits/trees cannot be read."""
    shas = rev_list_all(repo)
    matches = []
    for sha in shas:
        bad_paths = paths_matching_removed_roots(repo, sha)
        if bad_paths:
            matches.append({"commit": sha, "paths": bad_paths})

    return {
        "clean": len(matches) == 0,
        "commits_scanned": len(shas),
        "matches": matches,
    }


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Independent tree-enumeration verifier (AC4).",
    )
    p.add_argument("--repo", required=True, help="path to the git repo to verify")
    return p


def main(argv):
    parser = build_arg_parser()
    args = parser.parse_args(argv[1:])

    try:
        report = verify_tree(args.repo)
    except TreeVerifyError as e:
        print(json.dumps({"clean": False, "error": str(e)}, indent=2))
        sys.stderr.write("tree_verify.py: ERROR: %s\n" % e)
        return 2

    print(json.dumps(report, indent=2))
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
