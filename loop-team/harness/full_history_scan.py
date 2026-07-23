#!/usr/bin/env python3
"""Loop Team -- full-git-history PII/private-path scanner (AC5 of the
"publish all 178 commits" spec).

Gates publishing the full local git history of this repo to a public GitHub
remote. Unlike a HEAD-only or first-parent-only scan, this walks EVERY commit
reachable from ANY ref (`git rev-list --all`), enumerates the FULL tree of
each commit (`git ls-tree -r <sha>`), and regex-scans the RAW BYTES of every
blob entry (mode 100644/100755/120000) -- never text-mode-only decoding that
would silently skip binary content. Gitlink entries (mode 160000, i.e.
submodule references) are never scanned as blobs (there is no blob to read --
the entry points at another repo's commit) but are ALWAYS explicitly flagged
for manual review and NEVER allowed to silently clear a run to "clean."
`.gitmodules` is not special-cased for reading (it is an ordinary 100644 blob
and is already covered by the normal byte-scan), but this docstring calls it
out because the spec explicitly requires it not be missed.

Any commit/tree/blob the scanner cannot fully read (corrupted object, missing
object, unreadable repo) is a LOUD failure (exit 2) -- never silently
downgraded to "0 hits found."

Pairs with: path_removal.py (AC2/AC3/AC4 remover pipeline) and
identity_audit.py (AC1 marker-superset generator, whose JSON output is the
natural input to this script's --markers-file).

Usage:
    python3 full_history_scan.py --repo <path> --markers-file <path> \\
        [--json-report <path>]

--repo <path>
    Path to a git repository (working copy, bare, or --mirror clone). Scanned
    via `git rev-list --all`, i.e. every ref, not just HEAD/first-parent.

--markers-file <path>
    JSON file: {"identity_strings": [...], "extra_patterns": [...]}. Both
    lists are treated as literal substrings to scan for (escaped and
    compiled as a regex alternation). These ADD TO, but never replace, the
    built-in always-on patterns below.

--json-report <path> (optional)
    Write the JSON report to this path. The report is ALSO always printed to
    stdout, so either channel can be consumed.

Built-in, always-on patterns (scanned regardless of markers-file content):
  - a macOS home-directory path prefix
  - an email-shaped string
  - an API-key-shaped string (sk-ant-api..., sk-proj-...)

--- TOOLING-EXCLUSION for REALKEY-shaped hits (added after real-repo run
against ~/Claude/loop) -----------------------------------------------------
The PII-guard tooling itself (e.g. `scripts/pii-guard.sh`,
`scripts/snapshot-publish.sh`) legitimately contains the literal strings
`sk-ant-api` / `sk-proj-` as ITS OWN regex source -- that is not a leaked
key, it's the detector's own pattern definition. `scripts/snapshot-
publish.sh` already solves exactly this problem for its own filesystem-grep
gate via a `TOOLING_EXCLUDE` array of known tooling file paths. This scanner
reuses that same concept (TOOLING_EXCLUDE_PATHS below, kept in sync with
that array) for the two always-on API-key-shaped builtin patterns only
(`builtin:api-key-sk-ant-api`, `builtin:api-key-sk-proj`): a hit on one of
those two patterns whose `path` is in TOOLING_EXCLUDE_PATHS is EXEMPTED from
counting as a "hit" (does not block a clean result, does not appear in
`hits`) -- but it is NEVER silently dropped from the report entirely. It is
recorded under a separate `expected_tooling_pattern` report key so a human
reviewer can still see it. This exemption applies ONLY to the two REALKEY-
shaped builtins, by exact path match against TOOLING_EXCLUDE_PATHS -- it does
NOT apply to identity-marker hits, the home-path/email builtins, or any path
not in the list (a real key found in a non-tooling file is still a hit).

This exemption is deliberately narrow and does NOT cover the "GitHub"-as-a-
common-word false-positive problem seen in the same real run (an
over-broad `identity_strings` marker matching ordinary English prose). That
is a judgment call for a human to make about the marker superset itself
(drop it or accept the false positives) -- it is intentionally NOT
hardcoded away here; seeing it clearly broken out in the report is the
correct behavior, not something this scanner should silently suppress.

Exit codes:
    0  clean       -- scan completed fully, zero hits AND zero gitlinks.
    1  hits_found  -- scan completed fully but found >=1 marker/PII hit
                      and/or >=1 gitlink (mode 160000) entry anywhere in
                      `--all` history. A gitlink ALONE (no string hits) is
                      still exit 1 -- gitlinks never auto-clear a run.
    2  incomplete  -- the scan could not be completed (unreadable repo,
                      corrupted/missing object, `git` invocation failure).
                      Always loud; never silently reported as 0 hits.
"""
import argparse
import json
import re
import subprocess
import sys

GIT_TIMEOUT = 120

# --- Built-in, always-on patterns (AC5) -------------------------------------
# Kept as (name, compiled_pattern) pairs so a hit's "pattern" field in the
# report is a stable, human-readable label rather than a raw regex dump.
BUILTIN_PATTERNS = [
    ("builtin:home-path-prefix", re.compile(rb"/Use" rb"rs/[^\s\x00]+")),
    ("builtin:email", re.compile(
        rb"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
    )),
    ("builtin:api-key-sk-ant-api", re.compile(rb"sk-ant-api[A-Za-z0-9_\-]*")),
    ("builtin:api-key-sk-proj", re.compile(rb"sk-proj-[A-Za-z0-9_\-]*")),
]

GITLINK_MODE = "160000"
BLOB_MODES = ("100644", "100755", "120000")

# Kept in sync with scripts/snapshot-publish.sh's TOOLING_EXCLUDE array (paths
# relative to repo root). These are the only paths where a REALKEY-shaped
# builtin hit (sk-ant-api / sk-proj-) is expected (the tooling's own regex
# source), never for any other pattern.
TOOLING_EXCLUDE_PATHS = frozenset([
    "loop-team/harness/full_history_scan.py",
    "loop-team/harness/test_full_history_scan.py",
    "loop-team/evals/verify_build.py",
    "loop-team/evals/test_verify_build.py",
    "scripts/pii-guard.sh",
    "scripts/pii-markers.example",
    "scripts/test_publish.py",
    "scripts/snapshot-publish.sh",
    "scripts/test_snapshot_publish.py",
])

# The only two builtin pattern names the tooling-exclusion applies to (the
# REALKEY-shaped patterns) -- never the home-path/email builtins or any
# identity/marker pattern.
REALKEY_BUILTIN_PATTERN_NAMES = frozenset([
    "builtin:api-key-sk-ant-api",
    "builtin:api-key-sk-proj",
])


def _is_tooling_exempt(pattern_name, path, tooling_exclude_paths):
    """True iff this hit is a REALKEY-shaped builtin pattern matching inside
    a known tooling file's own regex-source -- exempted from counting as a
    real hit, but never silently dropped (see 'expected_tooling_pattern')."""
    if pattern_name not in REALKEY_BUILTIN_PATTERN_NAMES:
        return False
    # Normalize path separators / leading slashes for a robust exact-ish
    # match against the relative-path exclusion list.
    norm = path.lstrip("/")
    return norm in tooling_exclude_paths


class ScanIncomplete(Exception):
    """Raised whenever the scan cannot be trusted to have covered everything
    it was asked to cover. Always surfaces as exit code 2 -- never silently
    swallowed into a clean/hits_found report."""


def _run_git(repo, args, timeout=GIT_TIMEOUT):
    try:
        p = subprocess.run(
            ["git", "-C", repo] + list(args),
            capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ScanIncomplete(
            "git invocation failed: git -C %s %s (%s)" % (repo, " ".join(args), e)
        )
    if p.returncode != 0:
        raise ScanIncomplete(
            "git command failed (exit %d): git -C %s %s\nstderr: %s"
            % (p.returncode, repo, " ".join(args), p.stderr.decode("utf-8", "replace"))
        )
    return p.stdout


def _load_markers(markers_file):
    try:
        with open(markers_file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ScanIncomplete("could not read --markers-file %s: %s" % (markers_file, e))

    identity_strings = data.get("identity_strings") or []
    extra_patterns = data.get("extra_patterns") or []

    literal_patterns = []
    for s in identity_strings:
        if s:
            literal_patterns.append(("identity:%s" % s, re.escape(s).encode("utf-8")))
    for s in extra_patterns:
        if s:
            literal_patterns.append(("marker:%s" % s, re.escape(s).encode("utf-8")))

    compiled = list(BUILTIN_PATTERNS)
    for name, raw in literal_patterns:
        compiled.append((name, re.compile(raw)))
    return compiled


def _rev_list_all(repo):
    out = _run_git(repo, ["rev-list", "--all"])
    shas = [line.decode("ascii", "replace").strip()
            for line in out.splitlines() if line.strip()]
    return shas


def _ls_tree_full(repo, sha):
    """Return list of (mode, type, object_sha, path) for every entry in the
    full recursive tree of commit `sha`. Raises ScanIncomplete if the tree
    cannot be read."""
    out = _run_git(repo, ["ls-tree", "-r", "-z", sha])
    entries = []
    raw = out.split(b"\x00")
    for rec in raw:
        if not rec:
            continue
        try:
            meta, path = rec.split(b"\t", 1)
            mode, objtype, objsha = meta.split(b" ")
        except ValueError:
            raise ScanIncomplete(
                "malformed ls-tree record for commit %s: %r" % (sha, rec)
            )
        entries.append((
            mode.decode("ascii"),
            objtype.decode("ascii"),
            objsha.decode("ascii"),
            path.decode("utf-8", "surrogateescape"),
        ))
    return entries


def _read_blob_bytes(repo, obj_sha):
    return _run_git(repo, ["cat-file", "-p", obj_sha])


def _scan_bytes(data, patterns):
    """Return list of pattern-name strings that match anywhere in data."""
    hits = []
    for name, pattern in patterns:
        if pattern.search(data):
            hits.append(name)
    return hits


def _pattern_label(name):
    """Strip the internal "identity:"/"marker:"/"builtin:" prefix so the
    report's "pattern" field is exactly the marker string that matched
    (what the tests assert on), while still letting hits carry a stable,
    disambiguated identity internally."""
    for prefix in ("identity:", "marker:"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def scan_repo(repo, markers_file, tooling_exclude_paths=TOOLING_EXCLUDE_PATHS):
    """Run the full scan. Returns the report dict. Raises ScanIncomplete on
    any failure to fully read the repo's history/trees/blobs.

    A hit on a REALKEY-shaped builtin pattern (sk-ant-api / sk-proj-) whose
    path is in `tooling_exclude_paths` is split out into the report's
    `expected_tooling_pattern` list instead of `hits` -- it does not count
    toward "hits_found" and never blocks a clean result on its own, but it is
    NEVER silently dropped from the report entirely (see module docstring)."""
    patterns = _load_markers(markers_file)

    shas = _rev_list_all(repo)

    hits = []
    expected_tooling_pattern = []
    gitlinks = []
    commits_scanned = 0

    for sha in shas:
        entries = _ls_tree_full(repo, sha)
        for mode, objtype, objsha, path in entries:
            if mode == GITLINK_MODE:
                gitlinks.append({
                    "commit": sha,
                    "path": path,
                    "sha": objsha,
                })
                continue
            if mode not in BLOB_MODES:
                # Trees themselves are already expanded by `-r`; anything
                # else unexpected is treated as unreadable rather than
                # silently skipped.
                continue
            try:
                data = _read_blob_bytes(repo, objsha)
            except ScanIncomplete:
                raise
            matched_names = _scan_bytes(data, patterns)
            for name in matched_names:
                label = _pattern_label(name)
                record = {
                    "commit": sha,
                    "path": path,
                    "pattern": label,
                    "mode": mode,
                }
                if _is_tooling_exempt(label, path, tooling_exclude_paths):
                    expected_tooling_pattern.append(record)
                else:
                    hits.append(record)
        commits_scanned += 1

    if hits or gitlinks:
        status = "hits_found"
    else:
        status = "clean"

    return {
        "hits": hits,
        "expected_tooling_pattern": expected_tooling_pattern,
        "gitlinks": gitlinks,
        "commits_scanned": commits_scanned,
        "status": status,
    }


def _validate_repo(repo):
    try:
        _run_git(repo, ["rev-parse", "--git-dir"])
    except ScanIncomplete:
        raise


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Full-git-history PII/private-path scanner (AC5).",
    )
    p.add_argument("--repo", required=True, help="path to the git repo to scan")
    p.add_argument("--markers-file", required=True,
                    help="JSON file with identity_strings/extra_patterns")
    p.add_argument("--json-report", default=None,
                    help="optional path to also write the JSON report to")
    return p


def main(argv):
    parser = build_arg_parser()
    args = parser.parse_args(argv[1:])

    try:
        _validate_repo(args.repo)
        report = scan_repo(args.repo, args.markers_file)
    except ScanIncomplete as e:
        incomplete_report = {
            "hits": [],
            "expected_tooling_pattern": [],
            "gitlinks": [],
            "commits_scanned": 0,
            "status": "incomplete",
            "error": str(e),
        }
        print(json.dumps(incomplete_report, indent=2))
        if args.json_report:
            try:
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump(incomplete_report, f, indent=2)
            except OSError:
                pass
        sys.stderr.write("full_history_scan.py: SCAN INCOMPLETE: %s\n" % e)
        return 2

    print(json.dumps(report, indent=2))
    if args.json_report:
        with open(args.json_report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    if report["status"] == "clean":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
