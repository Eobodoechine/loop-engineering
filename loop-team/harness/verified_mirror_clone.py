#!/usr/bin/env python3
"""Loop Team -- verified-complete disposable mirror clone helper (AC2).

Clones a source repo with `git clone --mirror` into a disposable
destination directory, then VERIFIES ref-completeness by independently
running `git for-each-ref` against BOTH the original source repo and the
freshly-made mirror, diffing the two ref lists. If they don't match exactly,
this fails LOUDLY (raises / non-zero exit) rather than silently proceeding
with a possibly-incomplete clone -- a mirror clone that dropped a ref would
mean history published to the public repo is silently incomplete in the
other direction (worse: it could mean the scanner never even sees a ref
that has a leak on it).

This module never mutates the SOURCE repo -- `git clone --mirror` and
`git for-each-ref` are both read-only against the source.

Usage:
    python3 verified_mirror_clone.py --source <path> --dest <path>

Exit codes:
    0  mirror clone created and ref-for-ref verified complete.
    1  ref mismatch detected between source and mirror (verification
       failed) -- the mirror directory is left in place for inspection,
       but callers must NOT treat it as trustworthy.
    2  usage/execution error (source unreadable, clone command failed,
       dest already exists, etc).
"""
import argparse
import json
import os
import subprocess
import sys

GIT_TIMEOUT = 300


class MirrorCloneError(Exception):
    pass


class RefMismatchError(Exception):
    def __init__(self, message, source_only, mirror_only):
        super().__init__(message)
        self.source_only = source_only
        self.mirror_only = mirror_only


def _run_git(args, cwd=None, timeout=GIT_TIMEOUT):
    try:
        p = subprocess.run(
            ["git"] + list(args), cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MirrorCloneError("git invocation failed: git %s (%s)" % (" ".join(args), e))
    if p.returncode != 0:
        raise MirrorCloneError(
            "git command failed (exit %d): git %s\nstderr: %s"
            % (p.returncode, " ".join(args), p.stderr)
        )
    return p.stdout


def _for_each_ref(repo):
    """Return a dict {ref_name: sha} for every ref in repo."""
    out = _run_git(["for-each-ref", "--format=%(objectname) %(refname)"], cwd=repo)
    refs = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, refname = line.split(" ", 1)
        refs[refname] = sha
    return refs


def clone_mirror(source, dest):
    """git clone --mirror <source> <dest>. Raises MirrorCloneError on failure."""
    if os.path.exists(dest):
        raise MirrorCloneError("destination already exists: %s" % dest)
    _run_git(["clone", "--mirror", source, dest])


def verify_ref_completeness(source, mirror):
    """Independently diff `git for-each-ref` of source vs mirror. Raises
    RefMismatchError if they don't match exactly (same ref names AND same
    SHAs for each). Returns the matching ref dict on success."""
    source_refs = _for_each_ref(source)
    mirror_refs = _for_each_ref(mirror)

    source_ref_names = set(source_refs)
    mirror_ref_names = set(mirror_refs)

    source_only = sorted(source_ref_names - mirror_ref_names)
    mirror_only = sorted(mirror_ref_names - source_ref_names)

    sha_mismatches = sorted(
        name for name in (source_ref_names & mirror_ref_names)
        if source_refs[name] != mirror_refs[name]
    )

    if source_only or mirror_only or sha_mismatches:
        raise RefMismatchError(
            "ref completeness check FAILED: source_only=%r mirror_only=%r "
            "sha_mismatches=%r"
            % (source_only, mirror_only, sha_mismatches),
            source_only=source_only,
            mirror_only=mirror_only,
        )

    return source_refs


def make_verified_mirror_clone(source, dest):
    """Full AC2 pipeline: clone --mirror, then verify ref completeness.
    Returns the matching ref dict on success. Raises MirrorCloneError or
    RefMismatchError on any failure -- callers must never proceed past this
    function silently."""
    clone_mirror(source, dest)
    return verify_ref_completeness(source, dest)


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Verified-complete disposable mirror clone (AC2).",
    )
    p.add_argument("--source", required=True, help="path to the source repo")
    p.add_argument("--dest", required=True,
                    help="path to create the disposable mirror clone at (must not exist)")
    return p


def main(argv):
    parser = build_arg_parser()
    args = parser.parse_args(argv[1:])

    try:
        refs = make_verified_mirror_clone(args.source, args.dest)
    except RefMismatchError as e:
        result = {
            "verified": False,
            "error": "ref_mismatch",
            "message": str(e),
            "source_only_refs": e.source_only,
            "mirror_only_refs": e.mirror_only,
            "dest": args.dest,
        }
        print(json.dumps(result, indent=2))
        sys.stderr.write("verified_mirror_clone.py: REF MISMATCH: %s\n" % e)
        return 1
    except MirrorCloneError as e:
        result = {
            "verified": False,
            "error": "clone_failed",
            "message": str(e),
        }
        print(json.dumps(result, indent=2))
        sys.stderr.write("verified_mirror_clone.py: ERROR: %s\n" % e)
        return 2

    result = {
        "verified": True,
        "dest": args.dest,
        "ref_count": len(refs),
        "refs": sorted(refs.keys()),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
