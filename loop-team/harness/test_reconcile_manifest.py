"""Focused tests for the read-only reconciliation manifest utility."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from reconcile_manifest import compare_manifests, snapshot_repo


SCRIPT = Path(__file__).with_name("reconcile_manifest.py")
GIT_CONFIG = [
    "-c", "user.email=test@example.com",
    "-c", "user.name=Manifest Test",
    "-c", "commit.gpgsign=false",
]


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *GIT_CONFIG, *args], cwd=repo, check=check,
        capture_output=True, text=True,
    )


def _init_repo(repo: Path, remote: str = "") -> None:
    repo.mkdir()
    _git(repo, "init")
    if remote:
        _git(repo, "remote", "add", "origin", remote)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_snapshot_includes_tracked_modified_and_untracked_files_and_git_identity(tmp_path):
    repo = tmp_path / "checkout"
    _init_repo(repo, "https://example.com/acme/project.git")
    (repo / "tracked.txt").write_text("modified\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    before = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    manifest = snapshot_repo(repo)
    after = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout

    assert before == after
    assert manifest["files"]["tracked.txt"]["sha256"] == _sha256(b"modified\n")
    assert manifest["files"]["untracked.txt"]["sha256"] == _sha256(b"untracked\n")
    assert manifest["git"]["head"]
    assert manifest["git"]["branch"]
    assert manifest["git"]["remotes"] == [{
        "name": "origin",
        "fetch": ["https://example.com/acme/project.git"],
        "push": [],
    }]
    assert any("tracked.txt" in status for status in manifest["git"]["status"])


def test_snapshot_records_ignored_secret_and_generated_exclusions_without_opening_them(tmp_path):
    repo = tmp_path / "checkout"
    _init_repo(repo)
    (repo / ".gitignore").write_text(".env\nbuild/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "ignore generated and secret files")
    (repo / ".env").write_text("TOKEN=do-not-manifest\n", encoding="utf-8")
    _write_bytes(repo / "build" / "bundle.js", b"generated\n")

    manifest = snapshot_repo(repo)
    excluded = {(item["path"], item["pattern"]) for item in manifest["exclusions"]}

    assert ".env" not in manifest["files"]
    assert "build/bundle.js" not in manifest["files"]
    assert (".env", ".env") in excluded
    assert ("build", "build") in excluded or ("build", "build/**") in excluded
    assert all("do-not-manifest" not in json.dumps(item) for item in manifest["exclusions"])


def test_compare_classifies_text_binary_identical_only_local_only_remote_and_excluded(tmp_path):
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _init_repo(local)
    _init_repo(remote)

    for repo in (local, remote):
        (repo / "same.txt").write_text("same\n", encoding="utf-8")
        (repo / "changed.txt").write_text(
            "local\n" if repo == local else "remote\n", encoding="utf-8"
        )
        _write_bytes(repo / "asset.bin", b"\x00local" if repo == local else b"\x00remote")
        (repo / ".env").write_text(
            "TOKEN=local\n" if repo == local else "TOKEN=remote\n", encoding="utf-8"
        )
    (local / "only-local.txt").write_text("left\n", encoding="utf-8")
    (remote / "only-remote.txt").write_text("right\n", encoding="utf-8")

    diff = compare_manifests(snapshot_repo(local), snapshot_repo(remote))

    assert diff["only_local"] == ["only-local.txt"]
    assert diff["only_remote"] == ["only-remote.txt"]
    assert "changed.txt" in diff["modified"]
    assert "asset.bin" in diff["binary"]
    assert "same.txt" in diff["identical"]
    assert ".env" in diff["excluded"]
    assert diff["counts"]["binary"] == 1
    asset_entry = next(item for item in diff["entries"] if item["path"] == "asset.bin")
    assert asset_entry["classification"] == "binary"


def test_custom_exclusion_pattern_is_recorded_and_applies_to_untracked_files(tmp_path):
    repo = tmp_path / "checkout"
    _init_repo(repo)
    _write_bytes(repo / "artifacts" / "report.dat", b"generated")

    manifest = snapshot_repo(repo, exclude_patterns=("artifacts/**",))

    assert "artifacts/report.dat" not in manifest["files"]
    assert "artifacts/**" in {item["pattern"] for item in manifest["exclusions"]}
    assert any(item["path"] == ".git" for item in manifest["exclusions"])


def test_cli_emits_json_snapshot_and_compare_without_mutating_repos(tmp_path):
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _init_repo(local)
    _init_repo(remote)
    (local / "dirty.txt").write_text("left\n", encoding="utf-8")
    (remote / "dirty.txt").write_text("right\n", encoding="utf-8")
    before_local = _git(local, "status", "--porcelain=v1", "--untracked-files=all").stdout
    before_remote = _git(remote, "status", "--porcelain=v1", "--untracked-files=all").stdout

    process = subprocess.run(
        [sys.executable, str(SCRIPT), str(local), "--compare-root", str(remote)],
        capture_output=True, text=True, check=False,
    )
    result = json.loads(process.stdout)

    assert process.returncode == 0
    assert "dirty.txt" in result["modified"]
    assert _git(local, "status", "--porcelain=v1", "--untracked-files=all").stdout == before_local
    assert _git(remote, "status", "--porcelain=v1", "--untracked-files=all").stdout == before_remote
