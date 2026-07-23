"""Frozen behavioral tests for canonical Loop -> Mission Control publication.

Spec: <HOME>/Claude/Projects/mission-control/loop-team/runs/
2026-07-16_loop-engineering-status-push/specs/spec.md
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


LOOP_ROOT = Path("<HOME>/Claude/loop")
VERIFY = LOOP_ROOT / "loop-team" / "harness" / "verify.py"
MISSION_CONTROL = Path("<HOME>/Claude/Projects/mission-control")
MC_HARNESS = MISSION_CONTROL / "loop-team" / "harness"
PROJECT_ID = "loop-engineering"


def _run(args, *, env=None, timeout=60):
    return subprocess.run(
        [str(value) for value in args],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _fixture_root(tmp_path):
    root = tmp_path / "mission-control"
    result = _run(
        [
            sys.executable,
            MC_HARNESS / "create_mission_control_fixture.py",
            "--root",
            root,
            "--fixture-mode",
        ]
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return root


def _fake_pytest(tmp_path, returncode):
    binary = tmp_path / "bin" / "pytest"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        "#!{}\n"
        "import sys\n"
        "print({!r})\n"
        "raise SystemExit({})\n".format(
            sys.executable,
            "1 passed in 0.01s" if returncode == 0 else "1 failed in 0.01s",
            returncode,
        ),
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return binary.parent


def _run_verify(tmp_path, root, pytest_returncode, project=LOOP_ROOT, extra_env=None):
    fake_bin = _fake_pytest(tmp_path, pytest_returncode)
    env = dict(
        os.environ,
        PATH=str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        MISSION_CONTROL_ROOT=str(root),
    )
    if extra_env:
        env.update(extra_env)
    return _run([sys.executable, VERIFY, project], env=env)


def _events(root):
    event_dir = root / "control-plane" / "status-events" / PROJECT_ID
    if not event_dir.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in event_dir.glob("*.json")]


def _effective(root):
    path = root / "control-plane" / "effective-projects" / (PROJECT_ID + ".json")
    assert path.is_file(), "missing synchronous loop-engineering projection"
    return json.loads(path.read_text(encoding="utf-8"))


def _only_claim(project):
    claims = project.get("claims", [])
    assert len(claims) == 1
    return claims[0]


def _assert_exact_capture(event, stdout, fixture_root):
    assert len(event["evidence"]) == 1
    evidence = event["evidence"][0]
    path = Path(evidence["path"])
    assert path.is_file() and not path.is_symlink()
    assert path.is_relative_to(fixture_root)
    captured = path.read_bytes()
    assert captured == stdout.encode("utf-8")
    assert hashlib.sha256(captured).hexdigest() == evidence["sha256"]


# [BEHAVIORAL]
def test_canonical_verify_pass_publishes_exactly_once_before_returning_zero(tmp_path):
    root = _fixture_root(tmp_path)

    result = _run_verify(tmp_path, root, 0)

    assert result.returncode == 0, result.stderr or result.stdout
    harness = json.loads(result.stdout)
    assert harness["passed"] is True
    events = _events(root)
    assert len(events) == 1
    event = events[0]
    assert event["project"]["mission_control_project_id"] == PROJECT_ID
    assert event["producer"]["repo_id"] == PROJECT_ID
    assert event["metadata"]["fixture"] is True
    assert event["metadata"]["producer_outcome"] == "harness_passed"
    assert len(event["claim_updates"]) == 1
    assert event["claim_updates"][0]["outcome"] == "PASS"
    assert event["claim_updates"][0].get("failure_type") is None
    _assert_exact_capture(event, result.stdout, root)

    effective = _effective(root)
    assert _only_claim(effective)["outcome"] == "PASS"
    dashboard = json.loads(
        (root / "control-plane" / "status-dashboard.json").read_text(
            encoding="utf-8"
        )
    )
    assert next(project for project in dashboard["projects"] if project["id"] == PROJECT_ID) == effective


# [BEHAVIORAL]
def test_canonical_verify_failure_publishes_only_assertion_proof_and_stays_nonready(
    tmp_path,
):
    root = _fixture_root(tmp_path)

    result = _run_verify(tmp_path, root, 1)

    assert result.returncode != 0
    harness = json.loads(result.stdout)
    assert harness["passed"] is False
    events = _events(root)
    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "proof_failed"
    assert event["metadata"]["producer_outcome"] == "harness_failed"
    assert len(event["claim_updates"]) == 1
    assert event["claim_updates"][0]["outcome"] == "FAIL"
    assert event["claim_updates"][0]["failure_type"] == "ASSERTION"
    _assert_exact_capture(event, result.stdout, root)

    effective = _effective(root)
    claim = _only_claim(effective)
    assert claim["outcome"] == "FAIL"
    assert claim["failure_type"] == "ASSERTION"
    assert effective.get("ready") is not True


# [BEHAVIORAL]
def test_publisher_rejection_keeps_harness_capture_and_forces_verify_nonzero(tmp_path):
    root = _fixture_root(tmp_path)
    rejected_event = tmp_path / "rejected-event.json"
    publisher = root / "loop-team" / "harness" / "publish_status_event.py"
    publisher.parent.mkdir(parents=True)
    publisher.write_text(
        "import os, shutil, sys\n"
        "event = sys.argv[sys.argv.index('--event') + 1]\n"
        "shutil.copyfile(event, os.environ['REJECTED_EVENT_COPY'])\n"
        "print('Mission Control publisher rejected: forced test rejection', file=sys.stderr)\n"
        "raise SystemExit(4)\n",
        encoding="utf-8",
    )

    result = _run_verify(
        tmp_path,
        root,
        0,
        extra_env={"REJECTED_EVENT_COPY": str(rejected_event)},
    )

    assert result.returncode != 0
    harness = json.loads(result.stdout)
    assert "1 passed" in harness["output"]
    assert "publisher reject" in result.stderr.lower()
    assert rejected_event.is_file()
    submitted = json.loads(rejected_event.read_text(encoding="utf-8"))
    evidence = submitted["evidence"]
    assert len(evidence) == 1
    capture = Path(evidence[0]["path"])
    assert capture.is_file() and not capture.is_symlink()
    captured_harness = json.loads(capture.read_text(encoding="utf-8"))
    assert captured_harness["passed"] is True
    assert captured_harness["output"] == harness["output"]
    assert hashlib.sha256(capture.read_bytes()).hexdigest() == evidence[0]["sha256"]
    assert _events(root) == []
    effective = _effective(root)
    assert _only_claim(effective).get("outcome") != "PASS"
    assert effective.get("ready") is not True


# [BEHAVIORAL]
def test_noncanonical_verify_target_does_not_publish_loop_status(tmp_path):
    root = _fixture_root(tmp_path)
    project = tmp_path / "other-project"
    tests = project / "tests"
    tests.mkdir(parents=True)
    (tests / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    state_paths = (
        root / "control-plane" / "status-dashboard.json",
        root / "control-plane" / "effective-projects" / (PROJECT_ID + ".json"),
    )
    before = {path: path.read_bytes() for path in state_paths}

    result = _run_verify(tmp_path, root, 0, project=project)

    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout)["passed"] is True
    assert _events(root) == []
    assert {path: path.read_bytes() for path in state_paths} == before
