"""test_log.py — tests for harness/log.py (shared structured logging module)
and its wiring into live_smoke.py and evals/verify_build.py.

Written BEFORE implementation (TDD). Every test here will FAIL until
harness/log.py exists and the wiring lands. That is intentional and correct:
this file is the executable form of the spec's acceptance criteria.

Each test is labelled [DOC] or [BEHAVIORAL] in its docstring and names the
acceptance criterion (AC#) it encodes. Behavioral tests EXECUTE the real thing
(import + call the logger, read the file it wrote, run the tool via subprocess);
they never grep an artifact for keywords.

Run:  python3 -m pytest loop-team/harness/test_log.py -q
      (or, from loop-team/:  python3 -m pytest harness/test_log.py -q)

The runner-wiring criterion (AC13) lives in
loop-team/runner/tests/test_log_wiring.py so it runs under the runner suite.
"""
import ast
import importlib
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout

import pytest

# --- make `from harness.log import ...` work regardless of pytest invocation ---
# harness/ is an implicit namespace package; putting loop-team/ on sys.path lets
# `harness.log` resolve whether pytest is run from loop-team/ or from the repo root.
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))          # .../loop-team/harness
LOOPTEAM_DIR = os.path.dirname(HARNESS_DIR)                        # .../loop-team
REPO_DIR = os.path.dirname(LOOPTEAM_DIR)                           # repo root (has hooks/)
for _p in (LOOPTEAM_DIR, REPO_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LIVE_SMOKE_PY = os.path.join(HARNESS_DIR, "live_smoke.py")
LOG_PY = os.path.join(HARNESS_DIR, "log.py")

# An RFC-2606 / RFC-6761 guaranteed-invalid host: never resolves, so the failure
# verdict is deterministic and needs zero network egress.
INVALID_URL = "https://nonexistent.invalid/some/path"


def _read_jsonl(path):
    """Read a .jsonl file into a list of dicts (skip blank lines)."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))   # raises if any line is not valid JSON
    return out


def _fresh_log_module():
    """Import (or reimport) harness.log fresh, so the per-process logger cache
    from a previous test does not bleed into this one."""
    for key in ("harness.log",):
        sys.modules.pop(key, None)
    return importlib.import_module("harness.log")


# ===========================================================================
# AC1 — import + public surface
# ===========================================================================

class TestImportAndSurface:
    def test_get_logger_importable_and_has_methods(self):
        """[BEHAVIORAL] AC1: `from harness.log import get_logger` works and the
        returned object exposes debug/info/warning/error/critical/log."""
        from harness.log import get_logger
        lg = get_logger("ac1")
        for m in ("debug", "info", "warning", "error", "critical", "log"):
            assert callable(getattr(lg, m, None)), f"logger missing callable .{m}()"


# ===========================================================================
# AC2 — run_dir set: one valid JSON line per call, keys + round-trip
# ===========================================================================

class TestPerRunFile:
    def test_one_json_line_with_required_keys_and_fields(self, tmp_path):
        """[BEHAVIORAL] AC2: with run_dir set, a single call writes exactly ONE
        valid JSON line to <run_dir>/log.jsonl carrying ts/level/logger/msg plus
        any **fields; the file is created if missing; fields round-trip."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"   # does not exist yet -> must be created
        lg = log.get_logger("ac2", run_dir=str(run_dir))

        lg.info("hello world", url="https://x.example", count=3, ok=True)

        path = run_dir / "log.jsonl"
        assert path.exists(), "log.jsonl was not created under run_dir"
        records = _read_jsonl(str(path))
        assert len(records) == 1, f"expected exactly 1 line, got {len(records)}"
        rec = records[0]
        for k in ("ts", "level", "logger", "msg"):
            assert k in rec, f"record missing required key {k!r}: {rec}"
        assert rec["msg"] == "hello world"
        assert rec["level"].upper() == "INFO"
        assert rec["logger"] == "ac2"
        # fields round-trip exactly
        assert rec["url"] == "https://x.example"
        assert rec["count"] == 3
        assert rec["ok"] is True

    def test_ts_is_iso8601_seconds(self, tmp_path):
        """[BEHAVIORAL] AC2: ts is an ISO-8601 timestamp at seconds resolution
        (parseable by datetime.fromisoformat; no microseconds), matching the
        run_trace._now_iso convention."""
        import datetime
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        lg = log.get_logger("ac2ts", run_dir=str(run_dir))
        lg.warning("tick")
        rec = _read_jsonl(str(run_dir / "log.jsonl"))[0]
        dt = datetime.datetime.fromisoformat(rec["ts"])  # raises if not ISO-8601
        assert dt.microsecond == 0, f"ts must be seconds-resolution, got {rec['ts']!r}"


# ===========================================================================
# AC3 — console_level gating (file always captures, stderr is gated)
# ===========================================================================

class TestConsoleLevelGating:
    def test_info_below_console_level_not_on_stderr_but_in_file(self, tmp_path, capsys):
        """[BEHAVIORAL] AC3: console_level=WARNING -> .info() emits NO stderr line
        but STILL writes to the file; .error() DOES emit a stderr line."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        lg = log.get_logger("ac3", run_dir=str(run_dir), console_level="WARNING")

        lg.info("quiet-on-console")
        mid = capsys.readouterr()
        assert mid.err == "" or "quiet-on-console" not in mid.err, (
            "INFO must NOT appear on stderr when console_level=WARNING"
        )

        lg.error("loud-on-console")
        after = capsys.readouterr()
        assert "loud-on-console" in after.err, (
            "ERROR must appear on stderr when console_level=WARNING"
        )

        # The file (file_level defaults to DEBUG) captured BOTH records.
        records = _read_jsonl(str(run_dir / "log.jsonl"))
        msgs = [r["msg"] for r in records]
        assert "quiet-on-console" in msgs, "INFO must still be written to the file"
        assert "loud-on-console" in msgs, "ERROR must be written to the file"


# ===========================================================================
# AC4 — flush per call: N records -> N parseable complete lines
# ===========================================================================

class TestFlushPerCall:
    def test_n_records_n_parseable_lines(self, tmp_path):
        """[BEHAVIORAL] AC4: writing N records yields N complete, parseable lines
        when read back (flush-as-you-go, like run_trace)."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        lg = log.get_logger("ac4", run_dir=str(run_dir))
        N = 25
        for i in range(N):
            lg.info("line", i=i)
        records = _read_jsonl(str(run_dir / "log.jsonl"))
        assert len(records) == N, f"expected {N} lines, got {len(records)}"
        assert [r["i"] for r in records] == list(range(N)), "lines out of order/incomplete"


# ===========================================================================
# AC5 — never raises (un-writable path; non-serializable field)
# ===========================================================================

class TestNeverRaises:
    def test_uncreatable_run_dir_does_not_raise(self, tmp_path):
        """[BEHAVIORAL] AC5a: a run_dir that cannot be created/written must not
        cause the logging call to raise — the call returns normally."""
        log = _fresh_log_module()
        # Put a regular FILE where run_dir's parent path component is, so makedirs
        # of run_dir cannot succeed (a file is not a directory).
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a directory")
        bad_run_dir = blocker / "cannot" / "exist"
        lg = log.get_logger("ac5a", run_dir=str(bad_run_dir))
        # Must not raise:
        lg.error("should not raise even though the path is un-creatable")

    def test_non_serializable_field_does_not_raise(self, tmp_path):
        """[BEHAVIORAL] AC5b: a non-JSON-serializable field value (a raw object())
        must not cause the call to raise."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        lg = log.get_logger("ac5b", run_dir=str(run_dir))
        # Must not raise:
        lg.info("has a weird field", weird=object())


# ===========================================================================
# AC6 — idempotent (no duplicate handlers)
# ===========================================================================

class TestIdempotent:
    def test_same_args_no_duplicate_lines(self, tmp_path):
        """[BEHAVIORAL] AC6: get_logger twice with the SAME (name, run_dir) ->
        a single .info() yields exactly ONE line, not two (no duplicate handlers)."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        lg1 = log.get_logger("ac6", run_dir=str(run_dir))
        lg2 = log.get_logger("ac6", run_dir=str(run_dir))
        lg2.info("once")
        records = _read_jsonl(str(run_dir / "log.jsonl"))
        assert len(records) == 1, (
            f"expected exactly 1 line (idempotent), got {len(records)} — "
            "duplicate handlers attached"
        )
        # lg1 and lg2 should be the same cached logger keyed by (name, run_dir).
        assert lg1 is lg2, "get_logger must be idempotent for identical (name, run_dir)"


# ===========================================================================
# AC7 — never writes stdout
# ===========================================================================

class TestNeverStdout:
    def test_no_stdout_for_any_level(self, tmp_path):
        """[BEHAVIORAL] AC7: capturing stdout around debug/info/warning/error
        calls yields an EMPTY stdout — the logger never touches stdout."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        # console_level=DEBUG so every level WOULD emit on the console channel
        lg = log.get_logger("ac7", run_dir=str(run_dir), console_level="DEBUG")
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            lg.debug("d")
            lg.info("i")
            lg.warning("w")
            lg.error("e")
        assert buf_out.getvalue() == "", (
            f"logger wrote to stdout: {buf_out.getvalue()!r} — it must use stderr/file only"
        )
        # sanity: the console channel did go somewhere (stderr), proving emission happened
        assert buf_err.getvalue() != "", "expected console output on stderr (sanity)"


# ===========================================================================
# AC11 — stdlib-only + module docstring (DOC criterion)
# ===========================================================================

def _classify_import_roots(source):
    """Parse Python ``source`` and classify every import's top-level root by
    whether the import statement is UNCONDITIONAL (module-level, not inside a
    try/except) or GUARDED (somewhere inside an ``ast.Try`` body).

    Returns ``(unconditional_roots, guarded_roots)`` as two sets of root module
    names. A root that appears in both is reported in BOTH sets (it has at least
    one unconditional occurrence, which is what the stdlib-only rule cares about).

    Guardedness is determined by parent-tracking: we annotate each node with its
    parent, then for each Import/ImportFrom we walk up the ancestor chain looking
    for an ``ast.Try`` we sit inside (its ``body``/``handlers``/``orelse``, NOT
    its ``finalbody`` — a finally always runs, so it is not a guard).
    """
    tree = ast.parse(source)
    # Annotate parent pointers so we can walk up from any import node.
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child._classify_parent = parent  # type: ignore[attr-defined]

    def _is_guarded(node):
        cur = node
        child = None
        while cur is not None:
            if isinstance(cur, ast.Try) and child is not None:
                # Guarded only if we descended through a guarded region of the
                # Try (its body/handlers/orelse), not its finalbody.
                if (child in cur.body
                        or any(child in h.body for h in cur.handlers)
                        or child in cur.orelse):
                    return True
            child = cur
            cur = getattr(cur, "_classify_parent", None)
        return False

    unconditional, guarded = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or not node.module:   # skip relative imports
                continue
            roots = [node.module.split(".")[0]]
        else:
            continue
        bucket = guarded if _is_guarded(node) else unconditional
        bucket.update(roots)
    return unconditional, guarded


class TestStdlibOnlyAndDocstring:
    _STDLIB = {
        "json", "logging", "os", "sys", "datetime", "io", "threading", "pathlib",
        "logging.handlers", "time", "typing", "collections", "contextlib",
        "functools", "tempfile", "errno", "traceback", "__future__",
        "contextvars", "importlib",
    }

    def _stdlib_roots(self):
        return {m.split(".")[0] for m in self._STDLIB}

    def test_imports_are_stdlib_only(self):
        """[DOC] AC11: every UNCONDITIONAL (module-level, not inside try/except)
        import in log.py is stdlib-only. A third-party dependency (e.g. structlog)
        is permitted ONLY as a GUARDED optional import inside a try/except (with a
        stdlib fallback) — never as an unconditional import."""
        assert os.path.exists(LOG_PY), f"{LOG_PY} does not exist yet"
        unconditional, guarded = _classify_import_roots(
            open(LOG_PY, encoding="utf-8").read()
        )
        stdlib_roots = self._stdlib_roots()

        # Every UNCONDITIONAL import root must be stdlib.
        bad_unconditional = {r for r in unconditional if r not in stdlib_roots}
        assert not bad_unconditional, (
            f"log.py UNCONDITIONALLY imports non-stdlib module(s): "
            f"{sorted(bad_unconditional)} — a third-party dep must be a GUARDED "
            "optional import inside try/except, not an unconditional import"
        )

        # structlog must be present, and present ONLY as a guarded optional import
        # (this is the sanctioned optional-dependency path) — never unconditional.
        assert "structlog" in guarded, (
            "expected structlog to be imported as a GUARDED optional dependency "
            "(inside a try/except) in log.py"
        )
        assert "structlog" not in unconditional, (
            "structlog must NOT be imported unconditionally — it is a third-party "
            "optional dependency and must stay inside a try/except guard"
        )

    def test_checker_flags_unguarded_third_party(self):
        """[DOC] Self-test: the import classifier is not a rubber stamp. Run the
        SAME classification used by test_imports_are_stdlib_only against inline
        AST snippets and assert it (a) FLAGS an unconditional third-party import,
        (b) ALLOWS a guarded one, and (c) ALLOWS unconditional stdlib."""
        stdlib_roots = self._stdlib_roots()

        # (a) Unconditional `import requests` -> flagged (non-stdlib, unconditional).
        uncond, guarded = _classify_import_roots("import requests\n")
        assert "requests" in uncond and "requests" not in guarded
        bad = {r for r in uncond if r not in stdlib_roots}
        assert "requests" in bad, "checker must FLAG an unconditional third-party import"

        # (b) `import requests` inside try/except -> allowed (guarded, not unconditional).
        guarded_src = (
            "try:\n"
            "    import requests\n"
            "except Exception:\n"
            "    requests = None\n"
        )
        uncond, guarded = _classify_import_roots(guarded_src)
        assert "requests" in guarded, "checker must classify a try-guarded import as guarded"
        assert "requests" not in uncond, "a guarded import must NOT count as unconditional"
        bad = {r for r in uncond if r not in stdlib_roots}
        assert not bad, "checker must ALLOW a guarded third-party import"

        # (c) Sanity: unconditional `import os` -> allowed (stdlib).
        uncond, guarded = _classify_import_roots("import os\n")
        assert "os" in uncond
        bad = {r for r in uncond if r not in stdlib_roots}
        assert not bad, "checker must ALLOW unconditional stdlib imports"

    def test_module_docstring_mentions_contract(self):
        """[DOC] AC11: log.py has a module docstring mentioning levels,
        destinations, and the never-raise / crash-safe posture."""
        assert os.path.exists(LOG_PY), f"{LOG_PY} does not exist yet"
        tree = ast.parse(open(LOG_PY, encoding="utf-8").read())
        doc = (ast.get_docstring(tree) or "").lower()
        assert doc, "log.py must have a module docstring"
        assert "level" in doc, "docstring must mention levels"
        assert any(w in doc for w in ("stderr", "file", "destination", "run_dir", "run dir")), \
            "docstring must mention destinations (stderr / file / run_dir)"
        assert any(w in doc for w in ("never raise", "never-raise", "crash-safe",
                                      "crash safe", "does not raise", "fsync")), \
            "docstring must mention never-raise / crash-safe posture"


# ===========================================================================
# AC8 — regression: live_smoke main() stdout stays json.loads-able with logging on
# ===========================================================================

class TestLiveSmokeStdoutRegression:
    def test_live_smoke_stdout_is_pure_json_with_logging(self, tmp_path):
        """[BEHAVIORAL] AC8: running live_smoke via subprocess on an invalid URL
        WITH a run/log dir still prints pure json.loads-able JSON to stdout.
        (The existing test_live_smoke.py stays unmodified; this is separate.)"""
        out = subprocess.run(
            [sys.executable, LIVE_SMOKE_PY, "--run-dir", str(tmp_path / "run"), INVALID_URL],
            capture_output=True, text=True, timeout=90,
        )
        assert out.stdout.strip(), (
            "live_smoke produced empty stdout — it must always print its JSON summary.\n"
            f"stderr tail: {out.stderr.strip()[-500:]}"
        )
        data = json.loads(out.stdout)   # raises if stdout is not pure JSON
        assert isinstance(data, dict), f"expected a JSON object on stdout, got {type(data)}"


# ===========================================================================
# AC12 — live_smoke wiring: failure-LEVEL line naming the URL + valid stdout
# ===========================================================================

class TestLiveSmokeWiring:
    def test_run_dir_writes_failure_level_line_naming_url(self, tmp_path):
        """[BEHAVIORAL] AC12: live_smoke --run-dir <dir> against an RFC-invalid URL
        writes >=1 line at level WARNING or ERROR to <dir>/log.jsonl whose fields
        include the URL and its verdict; AND stdout stays json.loads-able.

        The verdict is NOT hard-coded to NAV_FAILED: the failure layer
        (LAUNCH/PROXY/NAV/...) varies by environment; any of them is a real
        failure and must be logged at WARNING/ERROR. We assert only that SOME
        failure-level line names the URL.
        """
        run_dir = tmp_path / "run"
        out = subprocess.run(
            [sys.executable, LIVE_SMOKE_PY, "--run-dir", str(run_dir), INVALID_URL],
            capture_output=True, text=True, timeout=90,
        )
        # stdout contract still holds
        assert out.stdout.strip(), (
            "live_smoke produced empty stdout.\n"
            f"stderr tail: {out.stderr.strip()[-500:]}"
        )
        json.loads(out.stdout)   # must parse

        log_path = run_dir / "log.jsonl"
        assert log_path.exists(), (
            "live_smoke did not write log.jsonl under --run-dir.\n"
            f"stderr tail: {out.stderr.strip()[-500:]}"
        )
        records = _read_jsonl(str(log_path))
        failure_lines = [
            r for r in records
            if r.get("level", "").upper() in ("WARNING", "ERROR", "CRITICAL")
        ]
        assert failure_lines, (
            "expected >=1 WARNING/ERROR/CRITICAL line for a failed URL, "
            f"got levels {[r.get('level') for r in records]}"
        )
        # At least one failure line must name the URL somewhere in its fields.
        def names_url(rec):
            return INVALID_URL in json.dumps(rec)
        named = [r for r in failure_lines if names_url(r)]
        assert named, (
            f"no failure-level line names the URL {INVALID_URL!r}; "
            f"failure records were: {failure_lines}"
        )
        # And a verdict field is present on a failure line (value not pinned).
        assert any("verdict" in r for r in failure_lines), (
            "expected a 'verdict' field on a failure-level line"
        )


# ===========================================================================
# AC9 + AC14 — verify_build: report to stdout, exit code unchanged, level logging
# ===========================================================================

class TestVerifyBuildWiring:
    def _import_verify_build(self):
        evals_dir = os.path.join(LOOPTEAM_DIR, "evals")
        if evals_dir not in sys.path:
            sys.path.insert(0, evals_dir)
        sys.modules.pop("verify_build", None)
        return importlib.import_module("verify_build")

    def test_failing_check_emits_warning_to_stderr_and_logdir(self, tmp_path, capsys, monkeypatch):
        """[BEHAVIORAL] AC14: force one check to FAIL -> a line at level >= WARNING
        is emitted to stderr AND to <LOOP_LOG_DIR>/log.jsonl when that env is set.
        stdout report + exit code unchanged."""
        log_dir = tmp_path / "logs"
        monkeypatch.setenv("LOOP_LOG_DIR", str(log_dir))
        vb = self._import_verify_build()

        # A synthetic failing checks list, in verify_build's (name, ok, detail) shape.
        checks = [
            ("case-lint", True, {"problems": [], "per_dir": {}}),
            ("operational invariants", False, {"problems": ["x.py: boom"], "scanned": 1}),
        ]
        overall = all(ok for _, ok, _ in checks)

        out = io.StringIO()
        with redirect_stdout(out):
            vb.print_report(overall, checks)
        # STDOUT report unchanged: still prints the per-check report + verdict.
        report = out.getvalue()
        assert "operational invariants" in report, "stdout report must still list the checks"
        assert "FAIL" in report, "an all-not-pass run must report FAIL on stdout"

        captured = capsys.readouterr()
        # A WARNING/ERROR line for the failing check must land on stderr.
        assert any(
            tok in captured.err
            for tok in ('"level": "WARNING"', '"level":"WARNING"',
                        '"level": "ERROR"', '"level":"ERROR"')
        ), (
            "expected a WARNING/ERROR structured line on stderr for the failing check; "
            f"stderr was:\n{captured.err[:800]}"
        )
        # ... and the same to <LOOP_LOG_DIR>/log.jsonl.
        log_path = log_dir / "log.jsonl"
        assert log_path.exists(), "expected <LOOP_LOG_DIR>/log.jsonl to be written"
        records = _read_jsonl(str(log_path))
        assert any(r.get("level", "").upper() in ("WARNING", "ERROR", "CRITICAL")
                   for r in records), \
            "expected a >=WARNING line in <LOOP_LOG_DIR>/log.jsonl for the failing check"

    def test_all_pass_emits_no_warning_line(self, tmp_path, capsys, monkeypatch):
        """[BEHAVIORAL] AC14: on an all-pass run NO WARNING/ERROR line is emitted."""
        log_dir = tmp_path / "logs"
        monkeypatch.setenv("LOOP_LOG_DIR", str(log_dir))
        vb = self._import_verify_build()

        checks = [
            ("case-lint", True, {"problems": [], "per_dir": {}}),
            ("operational invariants", True, {"problems": [], "scanned": 3}),
        ]
        out = io.StringIO()
        with redirect_stdout(out):
            vb.print_report(True, checks)
        report = out.getvalue()
        assert "PASS" in report, "an all-pass run must report PASS on stdout"

        captured = capsys.readouterr()
        for tok in ('"level": "WARNING"', '"level":"WARNING"',
                    '"level": "ERROR"', '"level":"ERROR"'):
            assert tok not in captured.err, (
                f"unexpected failure-level line on an all-pass run: stderr had {tok}"
            )
        # The wiring must still RUN on an all-pass report: each passing check is
        # logged at INFO to <LOOP_LOG_DIR>/log.jsonl. Requiring this turns the
        # negative criterion ("no WARNING/ERROR") into one that actually exercises
        # the wiring (it fails before the Coder wires logging in), rather than a
        # vacuous pass. The records that ARE written must carry no >=WARNING level.
        log_path = log_dir / "log.jsonl"
        assert log_path.exists(), (
            "verify_build must log per-check results to <LOOP_LOG_DIR>/log.jsonl "
            "even on an all-pass run (each pass logged at INFO)"
        )
        records = _read_jsonl(str(log_path))
        assert records, "expected per-check INFO lines for the passing checks"
        assert not any(
            r.get("level", "").upper() in ("WARNING", "ERROR", "CRITICAL")
            for r in records
        ), "all-pass run must not write any >=WARNING line to the log dir"

    def test_verify_build_subprocess_stdout_and_exit_code(self, tmp_path):
        """[BEHAVIORAL] AC9: verify_build run as a subprocess WITH logging enabled
        (LOOP_LOG_DIR set) still prints its parseable text report to stdout and
        exits with its normal code (0 iff all checks pass). We run --no-pytest to
        keep it fast and avoid the recursive pytest sweep, and assert structure,
        not pass/fail. We additionally assert the logging path actually ran by
        requiring <LOOP_LOG_DIR>/log.jsonl to be produced (so this is not a
        vacuous regression that ignores the new wiring)."""
        evals_dir = os.path.join(LOOPTEAM_DIR, "evals")
        log_dir = tmp_path / "logs"
        env = os.environ.copy()
        env["LOOP_LOG_DIR"] = str(log_dir)
        out = subprocess.run(
            [sys.executable, os.path.join(evals_dir, "verify_build.py"), "--no-pytest"],
            capture_output=True, text=True, timeout=300, cwd=LOOPTEAM_DIR, env=env,
        )
        # Logging path exercised: per-check lines persisted to <LOOP_LOG_DIR>.
        assert (log_dir / "log.jsonl").exists(), (
            "verify_build with LOOP_LOG_DIR set must persist per-check log lines to "
            "<LOOP_LOG_DIR>/log.jsonl.\n"
            f"stderr tail:\n{out.stderr[-500:]}"
        )
        assert "LAYER-1 VERDICT" in out.stdout, (
            "verify_build stdout report missing its verdict line.\n"
            f"stdout:\n{out.stdout[:800]}\nstderr tail:\n{out.stderr[-500:]}"
        )
        # Exit code semantics unchanged: 0 iff the report says PASS, else 1.
        verdict_pass = "LAYER-1 VERDICT: PASS" in out.stdout
        assert out.returncode == (0 if verdict_pass else 1), (
            f"exit code {out.returncode} inconsistent with verdict on stdout"
        )


# ===========================================================================
# AC10 — loop_logger.py back-compat (the module log.py generalizes)
# ===========================================================================

class TestLoopLoggerBackCompat:
    def test_loop_logger_public_funcs_still_work(self, tmp_path, monkeypatch):
        """[BEHAVIORAL] AC10: hooks/loop_logger.py keeps its public surface —
        get_loop_logger + log_gate remain importable, and a log_gate() call with
        LOOP_GUARD_DEBUG set writes to the override dir (its documented behavior).
        We do not modify loop_logger's own tests."""
        # Import from the repo's hooks/ package directory.
        hooks_dir = os.path.join(REPO_DIR, "hooks")
        assert os.path.isdir(hooks_dir), f"hooks dir not found at {hooks_dir}"
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        sys.modules.pop("loop_logger", None)
        ll = importlib.import_module("loop_logger")

        assert hasattr(ll, "get_loop_logger") and callable(ll.get_loop_logger)
        assert hasattr(ll, "log_gate") and callable(ll.log_gate)

        # Reset its internal cache so the override dir takes effect this call.
        if hasattr(ll, "_logger_cache"):
            ll._logger_cache.clear()
        override = tmp_path / "guard-logs"
        monkeypatch.setenv("LOOP_GUARD_DEBUG", "1")
        monkeypatch.setenv("_LOOP_GUARD_LOG_DIR_OVERRIDE", str(override))

        ll.log_gate("some-gate", fired=True, matched="x", exit_code=2)

        debug_log = override / "debug.log"
        assert debug_log.exists(), "log_gate did not write to the override dir"
        body = debug_log.read_text(encoding="utf-8")
        assert "some-gate" in body, "log_gate record missing the gate name"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
