#!/usr/bin/env python3
"""Loop Team -- identity audit for the "publish full git history" pipeline
(AC1 of the spec).

Walks EVERY commit reachable from ANY ref (`git log --all
--format='%ae|%an|%ce|%cn'`) in a target repo and lists every distinct
identity string (author email, author name, committer email, committer
name) that appears anywhere in history. Cross-references that list against
an existing local marker file (e.g. `scripts/.pii-markers.local` -- one
regex-alternative per line, `#`-comments and blank lines ignored, per that
file's own documented format) to see which identity strings are ALREADY
covered vs. NOT yet covered by the existing markers.

Also scans `git log --all --format=%B` (every commit message body, across
all refs) for hostname-shaped strings -- `*.local` suffixes and `user@host`
patterns -- that are not already covered by the existing marker file, since
a leaked local hostname is a distinct PII shape from an email address.

Output: a JSON "scan-time marker superset" on stdout (and optionally to
--out-file) shaped exactly like `full_history_scan.py --markers-file`
expects:
    {"identity_strings": [...], "extra_patterns": [...]}
`identity_strings` holds every distinct author/committer email + name found
in history (the full superset, whether or not already covered by the
existing marker file -- feeding a superset into the scanner costs nothing
and is strictly safer than under-covering). `extra_patterns` holds the
newly-discovered hostname-shaped strings from commit messages that are not
already covered by an existing marker-file line.

This script does not mutate the target repo in any way -- read-only `git
log` invocations only.

Usage:
    python3 identity_audit.py --repo <path> \\
        [--existing-markers <path-to-.pii-markers.local>] \\
        [--out-file <path-to-write-json>]

Exit codes: 0 success, 2 usage/read error (repo unreadable, etc).
"""
import argparse
import json
import re
import subprocess
import sys

GIT_TIMEOUT = 60

# Hostname-shaped patterns to look for in commit message bodies:
#   - a `*.local` mDNS-style hostname (e.g. "Enos-MacBook-Pro.local")
#   - a `user@host` pattern that is NOT a normal email (no TLD-shaped
#     suffix) -- e.g. "eobodoechine@Enos-MacBook-Pro" from a shell prompt
#     pasted into a commit message.
_DOTLOCAL_RE = re.compile(r"\b[\w.\-]+\.local\b")
_USER_AT_HOST_RE = re.compile(r"\b[\w.\-]+@[\w\-]+(?:\.[A-Za-z]{2,})?\b")
_EMAIL_TLD_RE = re.compile(r"^[\w.\-]+@[\w.\-]+\.[A-Za-z]{2,}$")


class IdentityAuditError(Exception):
    pass


def _run_git(repo, args, timeout=GIT_TIMEOUT):
    try:
        p = subprocess.run(
            ["git", "-C", repo] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise IdentityAuditError(
            "git invocation failed: git -C %s %s (%s)" % (repo, " ".join(args), e)
        )
    if p.returncode != 0:
        raise IdentityAuditError(
            "git command failed (exit %d): git -C %s %s\nstderr: %s"
            % (p.returncode, repo, " ".join(args), p.stderr)
        )
    return p.stdout


def collect_identity_strings(repo):
    """Return a sorted list of every distinct author/committer email+name
    string across every commit reachable from any ref."""
    out = _run_git(repo, ["log", "--all", "--format=%ae|%an|%ce|%cn"])
    identities = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        # Tolerate names containing literal '|' by only splitting on the
        # first 3 pipes (ae, an, ce all have no pipe realistically, but be
        # defensive): if there are more than 4 parts, re-join the middle.
        if len(parts) < 4:
            continue
        ae, an, ce, cn = parts[0], parts[1], parts[2], "|".join(parts[3:])
        for value in (ae, an, ce, cn):
            value = value.strip()
            if value:
                identities.add(value)
    return sorted(identities)


def _load_existing_markers(existing_markers_path):
    """Parse a `.pii-markers.local`-format file: one regex-alternative per
    line, '#'-comments and blank lines ignored. Returns a list of compiled
    patterns (each line as a regex, matching that file's own documented
    convention of "one regex alternative per line")."""
    if not existing_markers_path:
        return []
    try:
        with open(existing_markers_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise IdentityAuditError(
            "could not read --existing-markers %s: %s" % (existing_markers_path, e)
        )
    patterns = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line, re.IGNORECASE))
        except re.error:
            # Fall back to a literal match if a marker line isn't valid
            # regex syntax -- never let a bad line crash the audit.
            patterns.append(re.compile(re.escape(line), re.IGNORECASE))
    return patterns


def _already_covered(value, existing_patterns):
    return any(p.search(value) for p in existing_patterns)


def collect_hostname_like_strings(repo, existing_patterns):
    """Scan every commit message body (`git log --all --format=%B`) for
    hostname-shaped strings (*.local suffixes, user@host patterns not
    already shaped like a normal email) not already covered by
    existing_patterns. Returns a sorted list of newly-discovered strings."""
    out = _run_git(repo, ["log", "--all", "--format=%B%x00"])
    bodies = out.split("\x00")

    found = set()
    for body in bodies:
        for m in _DOTLOCAL_RE.finditer(body):
            found.add(m.group(0))
        for m in _USER_AT_HOST_RE.finditer(body):
            candidate = m.group(0)
            if _EMAIL_TLD_RE.match(candidate):
                # Looks like a normal email (user@domain.tld) -- that's
                # already covered by the scanner's built-in email pattern
                # and by collect_identity_strings(); not a "new" hostname
                # shape worth adding as an extra_pattern.
                continue
            found.add(candidate)

    new_findings = sorted(
        s for s in found if not _already_covered(s, existing_patterns)
    )
    return new_findings


def run_audit(repo, existing_markers_path=None):
    """Full AC1 audit. Returns the marker-superset dict."""
    identity_strings = collect_identity_strings(repo)
    existing_patterns = _load_existing_markers(existing_markers_path)
    hostname_like = collect_hostname_like_strings(repo, existing_patterns)

    covered = [s for s in identity_strings if _already_covered(s, existing_patterns)]
    uncovered = [s for s in identity_strings if s not in covered]

    return {
        "identity_strings": identity_strings,
        "extra_patterns": hostname_like,
        "_meta": {
            "existing_markers_file": existing_markers_path,
            "identity_strings_already_covered_by_existing_markers": covered,
            "identity_strings_not_covered_by_existing_markers": uncovered,
            "hostname_like_findings_in_commit_messages": hostname_like,
        },
    }


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Identity audit across full git history (AC1).",
    )
    p.add_argument("--repo", required=True, help="path to the git repo to audit")
    p.add_argument("--existing-markers", default=None,
                    help="path to an existing .pii-markers.local-format file")
    p.add_argument("--out-file", default=None,
                    help="optional path to also write the JSON output to")
    return p


def main(argv):
    parser = build_arg_parser()
    args = parser.parse_args(argv[1:])

    try:
        result = run_audit(args.repo, args.existing_markers)
    except IdentityAuditError as e:
        sys.stderr.write("identity_audit.py: ERROR: %s\n" % e)
        return 2

    print(json.dumps(result, indent=2))
    if args.out_file:
        with open(args.out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
