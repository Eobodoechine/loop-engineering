#!/usr/bin/env python3
"""Read-only Git checkout manifests and two-root reconciliation.

The module never writes to a checkout.  ``snapshot_repo`` walks the working
tree rather than the Git index, so committed, modified, and untracked files
are all represented.  Files matching ``DEFAULT_EXCLUDE_PATTERNS`` are not
opened; every excluded path and matching pattern is recorded in the manifest.

Public API::

    snapshot = snapshot_repo("/path/to/checkout")
    diff = compare_manifests(local_snapshot, remote_snapshot)
    diff = reconcile_roots("/path/to/local", "/path/to/remote")

The CLI prints a snapshot as JSON, or a JSON diff when ``--compare-root`` is
provided.  Binary files with different hashes are classified as ``binary``
instead of ``modified``.  Identical files, including identical binary files,
are classified as ``identical``.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
GIT_TIMEOUT = 30

# These are deliberately explicit rather than inherited from .gitignore:
# ignored files can contain credentials, while generated files are not useful
# for source reconciliation.  Callers can provide a narrower policy when
# needed, or use --no-default-excludes with the CLI.
DEFAULT_EXCLUDE_PATTERNS: Tuple[str, ...] = (
    ".git",
    ".git/**",
    ".env",
    ".env.*",
    "secrets",
    "secrets/**",
    "**/secrets",
    "**/secrets/**",
    "**/*secret*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "__pycache__",
    "__pycache__/**",
    "*.pyc",
    ".pytest_cache",
    ".pytest_cache/**",
    "node_modules",
    "node_modules/**",
    "dist",
    "dist/**",
    "build",
    "build/**",
    "coverage",
    "coverage/**",
    ".next",
    ".next/**",
    "target",
    "target/**",
)
GIT_EXCLUDE_PATTERNS: Tuple[str, ...] = (".git", ".git/**")


class ManifestError(RuntimeError):
    """Raised when a checkout or its Git metadata cannot be read."""


def _run_git(root: Path, args: Sequence[str]) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ManifestError("git invocation failed: %s" % exc) from exc
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise ManifestError(
            "git command failed (exit %d): git -C %s %s%s"
            % (process.returncode, root, " ".join(args),
               (": " + detail) if detail else "")
        )
    return process.stdout


def _optional_git(root: Path, args: Sequence[str]) -> Optional[str]:
    try:
        return _run_git(root, args).strip() or None
    except ManifestError:
        return None


def _git_metadata(root: Path) -> Dict[str, Any]:
    _run_git(root, ["rev-parse", "--show-toplevel"])
    head = _optional_git(root, ["rev-parse", "--verify", "HEAD"])
    branch = _optional_git(root, ["symbolic-ref", "--quiet", "--short", "HEAD"])

    remote_names = [
        line.strip()
        for line in _run_git(root, ["remote"]).splitlines()
        if line.strip()
    ]
    remotes = []
    for name in remote_names:
        fetch_urls = [
            line.strip()
            for line in _run_git(root, ["config", "--get-all", "remote.%s.url" % name])
            .splitlines()
            if line.strip()
        ]
        push_output = _optional_git(root, ["config", "--get-all", "remote.%s.pushurl" % name])
        push_urls = [line.strip() for line in (push_output or "").splitlines() if line.strip()]
        remotes.append({"name": name, "fetch": fetch_urls, "push": push_urls})

    status = [
        line
        for line in _run_git(root, ["status", "--porcelain=v1", "--untracked-files=all"])
        .splitlines()
        if line
    ]
    return {
        "head": head,
        "branch": branch,
        "remotes": remotes,
        "status": status,
    }


def _matches(path: str, pattern: str) -> bool:
    """Match a POSIX relative path against an explicit exclusion glob."""
    normalized = path.strip("/")
    normalized_pattern = pattern.strip("/")
    if not normalized_pattern:
        return False
    if normalized == normalized_pattern:
        return True
    if fnmatch.fnmatchcase(normalized, normalized_pattern):
        return True
    if PurePosixPath(normalized).match(normalized_pattern):
        return True
    # A basename pattern such as ``*.pyc`` applies at every tree depth.
    if "/" not in normalized_pattern:
        return any(fnmatch.fnmatchcase(part, normalized_pattern)
                   for part in PurePosixPath(normalized).parts)
    # Make directory policies explicit and intuitive for callers that pass
    # ``generated/**``: the directory entry itself is excluded too.
    if normalized_pattern.endswith("/**"):
        base = normalized_pattern[:-3].rstrip("/")
        return normalized == base or normalized.startswith(base + "/")
    return False


def _matching_patterns(path: str, patterns: Sequence[str]) -> List[str]:
    return [pattern for pattern in patterns if _matches(path, pattern)]


def _is_binary(prefix: bytes) -> bool:
    if b"\x00" in prefix:
        return True
    try:
        prefix.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _hash_file(path: Path) -> Tuple[str, int, str]:
    digest = hashlib.sha256()
    total = 0
    prefix = bytearray()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
                if len(prefix) < 8192:
                    prefix.extend(chunk[:8192 - len(prefix)])
    except OSError as exc:
        raise ManifestError("could not read %s: %s" % (path, exc)) from exc
    return digest.hexdigest(), total, "binary" if _is_binary(bytes(prefix)) else "text"


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def snapshot_repo(
    root: os.PathLike[str] | str,
    exclude_patterns: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Read a checkout into a deterministic, content-addressed manifest.

    ``root`` must be a Git checkout.  The walk does not consult Git's ignore
    rules, so ignored files are included unless an explicit exclusion pattern
    matches them.  Symlinks are recorded as exclusions and never followed.
    """
    checkout = Path(root).expanduser().resolve()
    if not checkout.is_dir():
        raise ManifestError("checkout is not a directory: %s" % checkout)
    requested_patterns = DEFAULT_EXCLUDE_PATTERNS if exclude_patterns is None else exclude_patterns
    patterns = tuple(dict.fromkeys(GIT_EXCLUDE_PATTERNS + tuple(requested_patterns)))
    git = _git_metadata(checkout)
    files: Dict[str, Dict[str, Any]] = {}
    exclusions: List[Dict[str, str]] = []
    seen_exclusions = set()

    def record_exclusion(path: str, pattern: str, reason: str = "explicit-pattern") -> None:
        key = (path, pattern, reason)
        if key not in seen_exclusions:
            seen_exclusions.add(key)
            exclusions.append({"path": path, "pattern": pattern, "reason": reason})

    for dirpath, dirnames, filenames in os.walk(checkout, topdown=True, followlinks=False):
        current = Path(dirpath)
        kept_dirs = []
        for dirname in sorted(dirnames):
            candidate = current / dirname
            relative = _relative(checkout, candidate)
            if candidate.is_symlink():
                record_exclusion(relative, "<symlink>", "symlink-not-followed")
                continue
            matches = _matching_patterns(relative, patterns)
            if matches:
                for pattern in matches:
                    record_exclusion(relative, pattern)
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            candidate = current / filename
            relative = _relative(checkout, candidate)
            if candidate.is_symlink():
                record_exclusion(relative, "<symlink>", "symlink-not-followed")
                continue
            matches = _matching_patterns(relative, patterns)
            if matches:
                for pattern in matches:
                    record_exclusion(relative, pattern)
                continue
            sha256, size, kind = _hash_file(candidate)
            files[relative] = {"sha256": sha256, "size": size, "kind": kind}

    exclusions.sort(key=lambda item: (item["path"], item["pattern"], item["reason"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "root": str(checkout),
        "git": git,
        "exclude_patterns": list(patterns),
        "files": {path: files[path] for path in sorted(files)},
        "exclusions": exclusions,
    }


def _exclusion_map(manifest: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}
    for exclusion in manifest.get("exclusions", []):
        if isinstance(exclusion, str):
            result.setdefault(exclusion, []).append({"path": exclusion})
        else:
            path = str(exclusion.get("path", ""))
            if path:
                result.setdefault(path, []).append(dict(exclusion))
    return result


def compare_manifests(
    local: Mapping[str, Any],
    remote: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare two manifests and return path buckets plus detailed entries."""
    local_files = dict(local.get("files", {}))
    remote_files = dict(remote.get("files", {}))
    local_excluded = _exclusion_map(local)
    remote_excluded = _exclusion_map(remote)

    buckets: Dict[str, List[str]] = {
        "only_local": [],
        "only_remote": [],
        "modified": [],
        "identical": [],
        "binary": [],
        "excluded": [],
    }
    entries: List[Dict[str, Any]] = []

    for path in sorted(set(local_files) | set(remote_files) | set(local_excluded) | set(remote_excluded)):
        if path in local_excluded or path in remote_excluded:
            buckets["excluded"].append(path)
            entries.append({
                "path": path,
                "classification": "excluded",
                "local": local_excluded.get(path, []),
                "remote": remote_excluded.get(path, []),
            })
            continue

        left = local_files.get(path)
        right = remote_files.get(path)
        if left is None:
            buckets["only_remote"].append(path)
            classification = "only_remote"
        elif right is None:
            buckets["only_local"].append(path)
            classification = "only_local"
        elif left.get("sha256") == right.get("sha256"):
            buckets["identical"].append(path)
            classification = "identical"
        elif left.get("kind") == "binary" or right.get("kind") == "binary":
            buckets["binary"].append(path)
            classification = "binary"
        else:
            buckets["modified"].append(path)
            classification = "modified"
        entries.append({
            "path": path,
            "classification": classification,
            "local": left,
            "remote": right,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "local": {"root": local.get("root"), "git": local.get("git", {})},
        "remote": {"root": remote.get("root"), "git": remote.get("git", {})},
        **buckets,
        "counts": {name: len(paths) for name, paths in buckets.items()},
        "entries": entries,
    }


def reconcile_roots(
    local_root: os.PathLike[str] | str,
    remote_root: os.PathLike[str] | str,
    exclude_patterns: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Snapshot two checkouts without copying or mutating either one."""
    return compare_manifests(
        snapshot_repo(local_root, exclude_patterns),
        snapshot_repo(remote_root, exclude_patterns),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Git checkout to snapshot")
    parser.add_argument("--compare-root", help="second Git checkout to compare")
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB",
        help="additional explicit exclusion glob; may be repeated",
    )
    parser.add_argument(
        "--no-default-excludes", action="store_true",
        help="use only patterns supplied with --exclude",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    patterns: Sequence[str]
    if args.no_default_excludes:
        patterns = tuple(args.exclude)
    else:
        patterns = tuple(DEFAULT_EXCLUDE_PATTERNS) + tuple(args.exclude)
    try:
        if args.compare_root:
            result = reconcile_roots(args.root, args.compare_root, patterns)
        else:
            result = snapshot_repo(args.root, patterns)
    except ManifestError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
