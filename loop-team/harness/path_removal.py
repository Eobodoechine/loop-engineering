#!/usr/bin/env python3
"""Loop Team -- path removal wiring for the "publish full git history"
pipeline (AC3).

Thin wrapper around the exact `git filter-repo` invocation that
`test_path_removal.py` already proves works against a synthetic fixture:

    git filter-repo --path public/ --path runs/ --path loop-team/runs/ \\
        --invert-paths --force

Run this ONLY against a verified-complete disposable mirror clone (see
`verified_mirror_clone.py`, AC2) -- never against a working copy, and never
against the original source repo. `git filter-repo` rewrites history
in-place in whatever repo it is pointed at, so the caller is responsible
for pointing this at a disposable mirror, not the source.

Also documents (per AC3 -- documentation only, no corrective action) whether
the source repo had any tags, before and after filtering, for the final
report: `git tag -l` is run against both the pre-filter mirror and the
post-filter result, and both lists are included in the returned/printed
report. This script does not add, remove, or otherwise act on tags itself.

--- GITLINK DROP (added after real-repo run against ~/Claude/loop) ---------
`--path`/`--invert-paths` operates on directory-tree prefix semantics and
does not reliably strip a bare gitlink LEAF entry (mode 160000, a "naked"
submodule reference never backed by a `.gitmodules` entry) the same way it
strips ordinary blob paths under a removed directory root. Confirmed
empirically against ~/Claude/loop: `public` is exactly this shape (7 commits,
gitlink, no .gitmodules ever declaring it) and survived the plain
--path/--invert-paths invocation.

Per git-filter-repo's own documented Python callback API
(https://github.com/newren/git-filter-repo/blob/main/Documentation/git-filter-repo.txt,
CALLBACKS section), `--commit-callback FUNCTION_BODY_OR_FILE` compiles and
calls `def commit_callback(commit, metadata): BODY`, where `commit.
file_changes` is a list of `FileChange` objects and `FileChange.mode` is a
bytestring (`b"160000"` for a gitlink/submodule tree entry -- confirmed by
reading git_filter_repo.py's `FileChange` class directly: "mode is one of
b'100644', b'100755', b'120000', or b'160000'"). This module now ALWAYS
additionally passes a `--commit-callback` (written out to a temp file and
passed as FUNCTION_BODY_OR_FILE, since filter-repo treats a callback arg
that resolves to an existing file's path as "read the body from that file")
that rewrites every commit's `file_changes` to drop any entry whose `mode ==
b"160000"` -- i.e. every gitlink is unconditionally stripped repo-wide, not
just ones under the `--path` roots. This matches the project's design intent
that gitlinks must never be silently kept (see `full_history_scan.py`'s
"gitlinks never auto-clear a run" rule) and this specific one is confirmed
junk with no `.gitmodules` ever backing it.

Usage:
    python3 path_removal.py --repo <path-to-mirror-clone> \\
        [--path public/ --path runs/ --path loop-team/runs/]

    (if --path is omitted, defaults to the three roots from the spec:
     public/, runs/, loop-team/runs/)

Exit codes:
    0  filter-repo completed successfully (returncode 0).
    1  filter-repo failed (non-zero exit) -- printed stdout/stderr included
       in the JSON report for diagnosis.
    2  usage error (repo path missing/not a git repo, etc).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

GIT_TIMEOUT = 600
DEFAULT_PATHS = ["public/", "runs/", "loop-team/runs/"]

# --commit-callback body: drop every mode-160000 (gitlink) file_change from
# every commit, unconditionally, repo-wide. Written to a temp file and passed
# to filter-repo as FUNCTION_BODY_OR_FILE (filter-repo reads the body from a
# path if the argument resolves to an existing file).
DROP_GITLINKS_CALLBACK_BODY = (
    "commit.file_changes = [\n"
    "    change for change in commit.file_changes\n"
    "    if change.mode != b\"160000\"\n"
    "]\n"
)


class PathRemovalError(Exception):
    pass


def _run_git(repo, args, timeout=GIT_TIMEOUT, check=True):
    try:
        p = subprocess.run(
            ["git"] + list(args), cwd=repo,
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PathRemovalError("git invocation failed: git %s (%s)" % (" ".join(args), e))
    if check and p.returncode != 0:
        raise PathRemovalError(
            "git command failed (exit %d): git %s\nstderr: %s"
            % (p.returncode, " ".join(args), p.stderr)
        )
    return p


def list_tags(repo):
    """git tag -l against repo. Documentation only -- no corrective action."""
    p = _run_git(repo, ["tag", "-l"])
    return [line for line in p.stdout.splitlines() if line.strip()]


def run_filter_repo(repo, paths_to_remove, drop_gitlinks=True):
    """The invocation test_path_removal.py documents/drives, PLUS (when
    drop_gitlinks=True, the default) a --commit-callback that unconditionally
    strips every mode-160000 (gitlink) file_change from every commit --
    `--path`/`--invert-paths` alone does not reliably strip a naked gitlink
    leaf entry (see module docstring). Returns the completed
    subprocess.CompletedProcess (does not raise on non-zero exit -- caller
    inspects returncode)."""
    args = ["filter-repo"]
    for p in paths_to_remove:
        args += ["--path", p]
    args += ["--invert-paths", "--force"]

    callback_path = None
    try:
        if drop_gitlinks:
            fd, callback_path = tempfile.mkstemp(
                prefix="drop_gitlinks_callback_", suffix=".py"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(DROP_GITLINKS_CALLBACK_BODY)
            args += ["--commit-callback", callback_path]
        return _run_git(repo, args, check=False)
    finally:
        if callback_path and os.path.exists(callback_path):
            os.remove(callback_path)


def remove_paths(repo, paths_to_remove=None, drop_gitlinks=True):
    """Full AC3 pipeline against an already-verified mirror clone: document
    tags before, run filter-repo (path removal + unconditional gitlink drop),
    document tags after. Returns a report dict. Raises PathRemovalError only
    for usage-level problems (e.g. repo not found) -- a filter-repo failure
    is reported in the dict, not raised, so callers can inspect the full
    diagnostic output."""
    if not os.path.isdir(repo):
        raise PathRemovalError("--repo path does not exist or is not a directory: %s" % repo)

    paths_to_remove = paths_to_remove or list(DEFAULT_PATHS)

    tags_before = list_tags(repo)
    result = run_filter_repo(repo, paths_to_remove, drop_gitlinks=drop_gitlinks)
    tags_after = list_tags(repo) if result.returncode == 0 else tags_before

    return {
        "repo": repo,
        "paths_removed": paths_to_remove,
        "gitlinks_dropped": drop_gitlinks,
        "filter_repo_returncode": result.returncode,
        "filter_repo_stdout": result.stdout,
        "filter_repo_stderr": result.stderr,
        "success": result.returncode == 0,
        "tags_before": tags_before,
        "tags_after": tags_after,
        "tags_present": bool(tags_before) or bool(tags_after),
    }


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Path removal wiring via git filter-repo (AC3).",
    )
    p.add_argument("--repo", required=True,
                    help="path to a VERIFIED-COMPLETE disposable mirror clone "
                         "(never the source repo, never a working copy)")
    p.add_argument("--path", action="append", dest="paths", default=None,
                    help="a path root to remove (repeatable); defaults to "
                         "public/, runs/, loop-team/runs/ if omitted")
    return p


def main(argv):
    parser = build_arg_parser()
    args = parser.parse_args(argv[1:])

    try:
        report = remove_paths(args.repo, args.paths)
    except PathRemovalError as e:
        print(json.dumps({"success": False, "error": str(e)}, indent=2))
        sys.stderr.write("path_removal.py: ERROR: %s\n" % e)
        return 2

    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
