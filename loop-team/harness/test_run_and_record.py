"""Tests for run_and_record.py (spec: loop-team/runs/2026-07-08_evidence-gate-phase1
/specs/spec.md, ACs 1/2/3/11).

Convention matched from this repo's existing harness tests
(test_fixplan_closure_lint.py / test_commit_diff_reread.py): invoke the real
CLI as a subprocess against real command argv and real tmp_path-scoped gate
directories (via LOOP_GATE_DIR), and assert on its documented stdout/exit
code -- the actual public interface, not private internal function names.
The spec's own "Public interface" section for this script declares NO
python function signatures beyond the CLI itself, so these tests do not
assume or require any -- every test below drives the tool exactly the way
the spec's own AC1/AC2/AC3 examples do
(`python3 loop-team/harness/run_and_record.py -- <command...>`).

`run_and_record.py` does not exist yet (Test-writer runs BEFORE the Coder,
per roles/test_writer.md's own header). This file uses `pytest.importorskip`
(NOT a bare top-level `import run_and_record`, despite that being
test_fixplan_closure_lint.py's own convention for a module that already
exists) deliberately: a bare import would raise ModuleNotFoundError at
COLLECTION time, which -- confirmed by direct read of
loop-team/evals/verify_build.py's `pytest_sweep()` -- runs
`pytest evals optimize harness -q` with no `--continue-on-collection-errors`
flag, so a single collection ERROR in this one new file would ABORT the
entire sweep before it collects or runs any of harness/'s other ~700
pre-existing tests, masking them for everyone else (any other in-flight
dispatch, or the repo's own operational_invariants gate) for the whole
window between this dispatch and whenever the Coder finishes. A SKIP is
non-fatal to that sweep (still returncode 0, tests obviously and honestly
reported as skipped, never silently counted as passed) and gives the exact
same "nothing built yet" signal without that collateral side effect. Once
the Coder builds run_and_record.py, this import resolves normally and every
test below runs for real, exactly as if it were a bare import.

Every subprocess invocation below is scoped to an isolated tmp_path-based
LOOP_GATE_DIR (never the real `~/.loop-gate`) and an isolated tmp_path-based
cwd, so these tests are hermetic and never touch the real machine's gate
directory or collide with any file that happens to be named "hello"/
"false"/"true" in whatever directory pytest itself is invoked from.

Run: python3 -m pytest loop-team/harness/test_run_and_record.py -q
"""
import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "run_and_record.py")

sys.path.insert(0, HERE)
run_and_record = pytest.importorskip("run_and_record")  # noqa: F841 -- see module docstring


def _run(args, env=None, cwd=None, timeout=30):
    """Invoke the real CLI: python3 run_and_record.py <args...>.

    Returns (exit_code, stdout, stderr). `env` is MERGED on top of a copy of
    the current environment (so PATH etc. remain intact); `cwd` defaults to
    None but every test below that cares about argv-token file-auto-
    detection passes an isolated tmp_path-based cwd explicitly, to avoid any
    accidental collision with a real file named "hello"/"false"/"true"
    wherever pytest happens to be invoked from.
    """
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    p = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout, env=run_env, cwd=cwd,
    )
    return p.returncode, p.stdout, p.stderr


def _parse_record_and_snapshot_path(stdout):
    """Parse the LEADING JSON record off `stdout` (there is free-text Proof
    block content printed after it, per the spec's documented print order --
    "the full JSON record ... FOLLOWED BY a ready-to-paste Proof block" --
    so a bare `json.loads(stdout)` would fail) and pull the `proof_snapshot:`
    path out of the Proof block text that follows. Returns (record_dict,
    snapshot_path_str). Uses json.JSONDecoder().raw_decode so this works
    regardless of whether the JSON is printed compact or pretty-printed.
    """
    text = stdout.lstrip()
    record, end = json.JSONDecoder().raw_decode(text)
    remainder = text[end:]
    m = re.search(r"^-\s*proof_snapshot:\s*(.+)$", remainder, re.MULTILINE)
    assert m, f"could not find a 'proof_snapshot:' line in stdout: {stdout!r}"
    return record, m.group(1).strip()


def _proof_block_fields(stdout):
    """Parse ALL `- field: value` lines out of the Proof block portion of
    `stdout` (everything after the leading JSON record) into a dict."""
    text = stdout.lstrip()
    _record, end = json.JSONDecoder().raw_decode(text)
    remainder = text[end:]
    fields = {}
    for m in re.finditer(r"^-\s*(\w+):\s*(.*)$", remainder, re.MULTILINE):
        fields[m.group(1)] = m.group(2).strip()
    return fields


def _git(cwd, *args, timeout=30):
    return subprocess.run(
        ["git", "-C", str(cwd)] + list(args),
        capture_output=True, text=True, timeout=timeout,
    )


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL]: `echo hello` exits 0, prints valid JSON containing
# output_sha256, and creates a real file under <gate_dir>/proof/<key>.json.
# ---------------------------------------------------------------------------

class TestAC1EchoHelloCreatesRealSnapshot:
    def test_exits_zero_and_prints_valid_json_with_output_sha256(self, tmp_path):
        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "echo", "hello"], env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        record, _snapshot_path = _parse_record_and_snapshot_path(out)
        assert "output_sha256" in record
        assert isinstance(record["output_sha256"], str)
        assert len(record["output_sha256"]) == 64  # sha256 hex digest length
        assert all(c in "0123456789abcdef" for c in record["output_sha256"])

    def test_creates_a_real_snapshot_file_on_disk_matching_stdout(self, tmp_path):
        """AC1: '...creates a real file under <gate_dir>/proof/<key>.json
        (verify with `ls` after running).' The proof_snapshot path is taken
        directly from the tool's OWN printed Proof block (not recomputed by
        this test), so this exercises the real, documented path -- not an
        assumption about the internal key algorithm."""
        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "echo", "hello"], env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        record, snapshot_path = _parse_record_and_snapshot_path(out)
        assert os.path.isfile(snapshot_path), f"expected a real snapshot file at {snapshot_path}"
        # sanity: the snapshot really did land under <gate_dir>/proof/
        assert os.path.commonpath(
            [os.path.abspath(snapshot_path), str(gate_dir)]
        ) == str(gate_dir)

        with open(snapshot_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        assert on_disk == record, (
            "the JSON printed to stdout must match the JSON snapshot written to disk"
        )

    def test_zero_files_auto_detected_gives_fixed_false_dirty_at_capture(self, tmp_path):
        """Round-4 fix, explicitly traced by the spec's own round-5 note:
        'echo hello' has no file-path-shaped argv tokens, so zero files are
        auto-detected -- dirty_at_capture must be the FIXED value False (not
        null, and not derived from an unscoped whole-repo `git status`)."""
        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "echo", "hello"], env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        record, _ = _parse_record_and_snapshot_path(out)
        assert record["files"] == {}
        assert record["dirty_at_capture"] is False, (
            f"expected dirty_at_capture to be the fixed value False (got "
            f"{record['dirty_at_capture']!r}) when zero files are auto-detected"
        )

    def test_ready_to_paste_proof_block_has_the_documented_fields(self, tmp_path):
        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "echo", "hello"], env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert "Proof:" in out
        record, _snapshot_path = _parse_record_and_snapshot_path(out)
        fields = _proof_block_fields(out)
        for required in (
            "proof_schema_version",
            "proof_producer",
            "proof_key_algorithm",
            "command",
            "exit_code",
            "proof_snapshot",
            "output_sha256",
            "verified_at",
        ):
            assert required in fields, f"Proof block missing '{required}:' line"
        assert fields["proof_schema_version"] == str(record["proof_schema_version"])
        assert fields["proof_producer"] == record["proof_producer"]
        assert fields["proof_key_algorithm"] == record["proof_key_algorithm"]
        assert fields["output_sha256"] == record["output_sha256"]
        # no files were auto-detected -- the `files:` line must be OMITTED
        # entirely, per spec ("...or omit the line if empty")
        assert "files" not in fields


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL]: same command/output run twice -> SAME key/snapshot path,
# idempotent overwrite (not a duplicate, not an error), despite captured_at
# differing between the two calls (round-1 fix #2: key excludes captured_at).
# ---------------------------------------------------------------------------

class TestAC2DeterministicKeyAcrossRepeatedInvocations:
    def test_same_command_twice_maps_to_same_snapshot_path_despite_different_captured_at(self, tmp_path):
        gate_dir = tmp_path / "gate"
        env = {"LOOP_GATE_DIR": str(gate_dir)}
        code1, out1, err1 = _run(["--", "echo", "hello"], env=env, cwd=str(tmp_path))
        time.sleep(0.05)  # pragmatic margin against clock coarseness
        code2, out2, err2 = _run(["--", "echo", "hello"], env=env, cwd=str(tmp_path))

        assert code1 == 0, f"stdout={out1!r} stderr={err1!r}"
        assert code2 == 0, f"stdout={out2!r} stderr={err2!r}"

        record1, snapshot_path1 = _parse_record_and_snapshot_path(out1)
        record2, snapshot_path2 = _parse_record_and_snapshot_path(out2)

        assert record1["captured_at"] != record2["captured_at"], (
            "test setup invalid: captured_at did not differ between the two "
            "calls -- cannot prove the key excludes captured_at without "
            "genuinely distinct timestamps to exclude"
        )
        assert snapshot_path1 == snapshot_path2, (
            "the SAME command with identical output must map to the SAME "
            "key/snapshot path (AC2) -- got two different paths, meaning "
            "captured_at (or some other volatile field) leaked into the key"
        )

        proof_files = list((gate_dir / "proof").glob("*.json"))
        assert len(proof_files) == 1, (
            f"expected exactly ONE snapshot file (idempotent overwrite, not a "
            f"duplicate) for two identical invocations, found: {proof_files}"
        )

    def test_repeat_invocation_overwrites_captured_at_on_disk(self, tmp_path):
        """The FULL record (including captured_at) is what's written to
        disk; a repeat invocation must OVERWRITE it with the new
        captured_at, not silently skip the write because a snapshot already
        exists at that path."""
        gate_dir = tmp_path / "gate"
        env = {"LOOP_GATE_DIR": str(gate_dir)}
        code1, out1, err1 = _run(["--", "echo", "hello"], env=env, cwd=str(tmp_path))
        time.sleep(0.05)
        code2, out2, err2 = _run(["--", "echo", "hello"], env=env, cwd=str(tmp_path))
        assert code1 == 0, f"stdout={out1!r} stderr={err1!r}"
        assert code2 == 0, f"stdout={out2!r} stderr={err2!r}"

        _record1, snapshot_path = _parse_record_and_snapshot_path(out1)
        record2, _ = _parse_record_and_snapshot_path(out2)
        with open(snapshot_path, encoding="utf-8") as f:
            on_disk_after_second_call = json.load(f)
        assert on_disk_after_second_call["captured_at"] == record2["captured_at"], (
            "expected the on-disk snapshot to reflect the SECOND call's "
            "captured_at (an overwrite happened), not a stale first-call value"
        )


# ---------------------------------------------------------------------------
# AC3 [BEHAVIORAL]: a nonzero-exit wrapped command -> run_and_record.py
# itself exits nonzero (mirrors it), and still writes a valid snapshot.
# ---------------------------------------------------------------------------

class TestAC3NonzeroExitCommandMirroredAndStillRecorded:
    def test_false_command_mirrors_nonzero_exit_and_writes_snapshot(self, tmp_path):
        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "false"], env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code != 0, (
            f"expected run_and_record.py to mirror a failing wrapped command's "
            f"own nonzero exit code; stdout={out!r} stderr={err!r}"
        )

        record, snapshot_path = _parse_record_and_snapshot_path(out)
        assert str(record["exit_code"]) == str(code), (
            "run_and_record.py's own process exit code must equal the "
            "wrapped command's recorded exit_code"
        )
        assert record["exit_code"] != 0
        assert os.path.isfile(snapshot_path), (
            "a failing command's evidence must still be recorded as a real "
            "snapshot file -- 'a failing command's evidence is still real "
            "evidence of the failure'"
        )
        with open(snapshot_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        assert on_disk == record


# ---------------------------------------------------------------------------
# Public interface #1, file auto-detection: any argv token that resolves to
# a real on-disk file gets sha256-hashed under `files`. Not its own numbered
# AC, but directly documented, load-bearing behavior (AC5/AC7's fixtures in
# test_fixplan_closure_lint.py depend on `files` being correctly populated
# when files ARE cited) -- edge-case coverage per the Test-writer role
# brief's "boundary/edge cases" instruction.
# ---------------------------------------------------------------------------

class TestFileAutoDetectionFromArgv:
    def test_argv_file_path_token_gets_hashed_under_files(self, tmp_path):
        gate_dir = tmp_path / "gate"
        evidence = tmp_path / "evidence.txt"
        evidence.write_text("hello evidence\n", encoding="utf-8")

        code, out, err = _run(
            ["--", "cat", str(evidence)],
            env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        record, _ = _parse_record_and_snapshot_path(out)

        expected_sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
        assert record["files"].get(str(evidence)) == expected_sha, (
            f"expected files[{str(evidence)!r}] == {expected_sha!r}, got "
            f"{record['files']!r}"
        )

    def test_argv_token_that_is_not_an_existing_file_is_not_recorded(self, tmp_path):
        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "echo", "not-a-real-path-on-disk-xyz"],
            env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        record, _ = _parse_record_and_snapshot_path(out)
        assert record["files"] == {}


# ---------------------------------------------------------------------------
# Public interface #1, dirty_at_capture: true / null outcomes when one or
# more files ARE auto-detected (the empty-files fixed-False case is covered
# directly against AC1's own echo-hello fixture above, per the round-4 fix /
# round-5 trace note "(a)"). Not tied to a single numbered AC, but explicit,
# testable, documented public-interface behavior.
# ---------------------------------------------------------------------------

class TestDirtyAtCaptureWithRealAutoDetectedFiles:
    def _init_repo_with_committed_file(self, repo_dir):
        repo_dir.mkdir()
        assert _git(repo_dir, "init", "-q").returncode == 0
        assert _git(repo_dir, "config", "user.email", "test@example.com").returncode == 0
        assert _git(repo_dir, "config", "user.name", "Test").returncode == 0
        target = repo_dir / "evidence.txt"
        target.write_text("clean content\n", encoding="utf-8")
        assert _git(repo_dir, "add", "evidence.txt").returncode == 0
        commit = _git(repo_dir, "commit", "-q", "-m", "initial")
        assert commit.returncode == 0, commit.stderr
        return target

    def test_false_for_clean_tracked_file_in_git_repo(self, tmp_path):
        repo = tmp_path / "repo"
        target = self._init_repo_with_committed_file(repo)

        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "cat", str(target)],
            env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        record, _ = _parse_record_and_snapshot_path(out)
        assert record["dirty_at_capture"] is False

    def test_true_for_uncommitted_change_to_a_detected_file(self, tmp_path):
        repo = tmp_path / "repo"
        target = self._init_repo_with_committed_file(repo)
        target.write_text("clean content\nmodified, not committed\n", encoding="utf-8")

        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "cat", str(target)],
            env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        record, _ = _parse_record_and_snapshot_path(out)
        assert record["dirty_at_capture"] is True

    def test_null_when_detected_file_is_not_inside_a_git_repo(self, tmp_path):
        outside = tmp_path / "not_a_repo"
        outside.mkdir()
        probe = subprocess.run(
            ["git", "-C", str(outside), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode == 0:
            pytest.skip(
                "tmp_path is unexpectedly inside a git repo (%s); cannot "
                "exercise the not-a-git-repo branch here" % probe.stdout.strip()
            )

        target = outside / "evidence.txt"
        target.write_text("standalone content\n", encoding="utf-8")

        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", "cat", str(target)],
            env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        record, _ = _parse_record_and_snapshot_path(out)
        assert record["dirty_at_capture"] is None


# ---------------------------------------------------------------------------
# Public interface #1, stale-entry sweep: documented startup behavior, not
# its own numbered AC.
# ---------------------------------------------------------------------------

class TestStaleEntrySweep:
    def test_stale_snapshot_file_removed_on_next_invocation(self, tmp_path):
        gate_dir = tmp_path / "gate"
        proof_dir = gate_dir / "proof"
        proof_dir.mkdir(parents=True)
        stale_file = proof_dir / "some-old-key.json"
        stale_file.write_text('{"stale": true}', encoding="utf-8")
        far_past = time.time() - 400 * 24 * 3600  # well beyond any plausible TTL
        os.utime(stale_file, (far_past, far_past))

        code, out, err = _run(
            ["--", "echo", "hello"], env={"LOOP_GATE_DIR": str(gate_dir)}, cwd=str(tmp_path),
        )
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert not stale_file.exists(), (
            "expected the startup stale-entry sweep to remove a snapshot "
            "file far older than any plausible TTL"
        )


# ---------------------------------------------------------------------------
# AC2 (spec: 2026-07-10_run-and-record-timeout-fix) [BEHAVIORAL]: a wrapped
# command that hangs past the (test-overridden, via RUN_AND_RECORD_TIMEOUT_S)
# timeout must not hang run_and_record.py forever or crash it with an
# uncaught traceback -- it must exit 2, print a JSON error object (not a
# traceback) to stdout, and write NO snapshot file. This is a REAL hang and a
# REAL subprocess.TimeoutExpired (not mocked): the wrapped command is a
# freshly spawned `python3 -c "import time; time.sleep(...)"` that genuinely
# sleeps well past a short override timeout, exercised through the same
# real-CLI-subprocess `_run()` helper every other test in this file uses.
# ---------------------------------------------------------------------------

class TestTimeoutPathRealHangIsCaughtNotCrashed:
    def test_hung_command_exceeds_override_timeout_exits_2_json_error_no_snapshot(self, tmp_path):
        gate_dir = tmp_path / "gate"
        code, out, err = _run(
            ["--", sys.executable, "-c", "import time; time.sleep(30)"],
            env={
                "LOOP_GATE_DIR": str(gate_dir),
                # Short override -- proves the timeout is genuinely
                # reachable/overridable per-invocation without waiting out
                # a minutes-scale production default.
                "RUN_AND_RECORD_TIMEOUT_S": "0.5",
            },
            cwd=str(tmp_path),
            # Generous outer bound for THIS test-helper's own subprocess
            # call -- the real assertion is that run_and_record.py itself
            # returns promptly once its internal 0.5s timeout fires.
            timeout=15,
        )
        assert code == 2, f"expected exit code 2 on timeout; stdout={out!r} stderr={err!r}"

        # A JSON error object was printed to stdout -- not a Python
        # traceback (an uncaught TimeoutExpired would print one instead).
        parsed = json.loads(out.strip())
        assert "error" in parsed
        assert "timed out" in parsed["error"].lower(), (
            f"expected the error message to clearly identify a timeout "
            f"(distinct from the could-not-run-at-all OSError branch), got: "
            f"{parsed['error']!r}"
        )
        assert "Traceback (most recent call last)" not in out
        assert "Traceback (most recent call last)" not in err

        # No snapshot file was written anywhere under the gate dir.
        proof_dir = gate_dir / "proof"
        written = list(proof_dir.glob("*.json")) if proof_dir.exists() else []
        assert written == [], (
            f"expected no snapshot file written on a timed-out command, "
            f"found: {written}"
        )


# ---------------------------------------------------------------------------
# AC11 [DOC]: neither run_and_record.py nor the lint v2 changes introduce a
# new pip dependency -- every top-level import in BOTH files must resolve to
# a stdlib/builtin module, not a site-packages-installed third-party
# package.
# ---------------------------------------------------------------------------

def _imported_top_level_names(pyfile_path):
    with open(pyfile_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=pyfile_path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # skip relative imports
                names.add(node.module.split(".")[0])
    return names


def _is_stdlib_or_builtin(module_name):
    if module_name in sys.builtin_module_names:
        return True
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return False
    if spec is None:
        return False
    origin = spec.origin or ""
    return "site-packages" not in origin and "dist-packages" not in origin


class TestAC11NoNewPipDependency:
    def test_run_and_record_imports_are_stdlib_only(self):
        assert os.path.isfile(SCRIPT), "run_and_record.py does not exist yet"
        names = _imported_top_level_names(SCRIPT)
        non_stdlib = sorted(n for n in names if not _is_stdlib_or_builtin(n))
        assert not non_stdlib, (
            f"run_and_record.py imports non-stdlib module(s): {non_stdlib}"
        )

    def test_fixplan_closure_lint_v2_imports_remain_stdlib_only(self):
        lint_script = os.path.join(HERE, "fixplan_closure_lint.py")
        names = _imported_top_level_names(lint_script)
        non_stdlib = sorted(n for n in names if not _is_stdlib_or_builtin(n))
        assert not non_stdlib, (
            f"fixplan_closure_lint.py imports non-stdlib module(s): {non_stdlib}"
        )
