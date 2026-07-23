"""test_log_structlog.py — tests for the structlog backend of harness/log.py.

These tests are ADDITIVE. They do NOT modify or replace test_log.py (the 17
frozen contract tests). They assert that:
  1. with structlog present, the structlog backend is active AND a persisted line
     has the IDENTICAL record shape (keys + UPPERCASE level) as the stdlib record;
  2. the structlog backend never writes to stdout for any level;
  3. forcing the structlog import to fail selects the stdlib fallback, which
     still produces the correct record shape, one line per call, never stdout,
     and never raises;
  4. bind_context carries fields into subsequent emits, with per-thread
     isolation under concurrency (mirroring the exp1 contextvars check);
  5. never-raise + idempotent hold under the structlog backend.

Run:  python3 -m pytest harness/test_log_structlog.py -q
"""
import builtins
import importlib
import io
import json
import os
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout

import pytest

pytest.importorskip("structlog")  # this module tests the structlog backend; the stdlib fallback is covered by test_log.py

# --- make `from harness.log import ...` work regardless of pytest invocation ---
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
LOOPTEAM_DIR = os.path.dirname(HARNESS_DIR)
REPO_DIR = os.path.dirname(LOOPTEAM_DIR)
for _p in (LOOPTEAM_DIR, REPO_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _read_jsonl(path):
    """Read a .jsonl file into a list of dicts (skip blank lines)."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))  # raises if any line is not valid JSON
    return out


def _fresh_log_module():
    """Import (or reimport) harness.log fresh so the per-process logger cache and
    backend flag from another test do not bleed in. Returns the module."""
    sys.modules.pop("harness.log", None)
    return importlib.import_module("harness.log")


def _reload_log_with_structlog_blocked():
    """Reimport harness.log with `structlog` import forced to fail, so the
    module selects its stdlib fallback. Returns (module, restore_callable).

    We monkeypatch builtins.__import__ to raise ImportError for structlog (the
    module imports it via importlib.import_module, which ultimately calls
    __import__), drop the cached module, and reimport. The caller MUST invoke
    the returned restore() in a finally to undo both patches."""
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "structlog" or name.startswith("structlog."):
            raise ImportError("structlog blocked for fallback test")
        return real_import(name, *args, **kwargs)

    # Also drop any already-imported structlog so import_module re-resolves it.
    saved_structlog_mods = {
        k: v for k, v in sys.modules.items()
        if k == "structlog" or k.startswith("structlog.")
    }
    for k in list(saved_structlog_mods):
        sys.modules.pop(k, None)

    builtins.__import__ = _blocking_import
    sys.modules.pop("harness.log", None)
    mod = importlib.import_module("harness.log")

    def restore():
        builtins.__import__ = real_import
        sys.modules.update(saved_structlog_mods)
        # Reimport a clean module so later tests get the normal backend back.
        sys.modules.pop("harness.log", None)
        importlib.import_module("harness.log")

    return mod, restore


# ===========================================================================
# TEST 1 — structlog backend active + identical record shape
# ===========================================================================

class TestStructlogBackendActiveAndShape:
    def test_backend_is_structlog_and_shape_matches_stdlib(self, tmp_path):
        """[BEHAVIORAL] With structlog importable, the structlog backend is active
        (marker flag True / backend_name() == 'structlog') AND a persisted line
        has the identical keys and UPPERCASE level casing as the stdlib record
        shape (ts/level/logger/msg + round-tripped fields)."""
        log = _fresh_log_module()
        # Marker: the module reports the structlog backend.
        assert log._STRUCTLOG_AVAILABLE is True, "structlog should be importable here"
        assert log.backend_name() == "structlog"

        run_dir = tmp_path / "run"
        lg = log.get_logger("sl1", run_dir=str(run_dir))
        lg.info("hello world", url="https://x.example", count=3, ok=True)

        records = _read_jsonl(str(run_dir / "log.jsonl"))
        assert len(records) == 1
        rec = records[0]
        # exact key set: reserved keys + the three supplied fields, nothing else.
        assert set(rec) == {"ts", "level", "logger", "msg", "url", "count", "ok"}, rec
        assert rec["level"] == "INFO", f"level must be UPPERCASE 'INFO', got {rec['level']!r}"
        assert rec["logger"] == "sl1"
        assert rec["msg"] == "hello world"
        # structlog's native render uses 'event'/'logger_name'/lowercase level —
        # none of those must leak into the persisted record.
        assert "event" not in rec and "logger_name" not in rec, rec
        # fields round-trip exactly
        assert rec["url"] == "https://x.example"
        assert rec["count"] == 3
        assert rec["ok"] is True


# ===========================================================================
# TEST 2 — never stdout under the structlog backend
# ===========================================================================

class TestNeverStdoutStructlog:
    def test_no_stdout_for_any_level(self, tmp_path):
        """[BEHAVIORAL] Capturing stdout around all 5 levels under the structlog
        backend yields EMPTY stdout (the ReturnLogger render is returned, never
        printed); the console channel still emits on stderr."""
        log = _fresh_log_module()
        assert log.backend_name() == "structlog"
        run_dir = tmp_path / "run"
        lg = log.get_logger("sl2", run_dir=str(run_dir), console_level="DEBUG")
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            lg.debug("d")
            lg.info("i")
            lg.warning("w")
            lg.error("e")
            lg.critical("c")
        assert buf_out.getvalue() == "", (
            f"structlog backend wrote to stdout: {buf_out.getvalue()!r}"
        )
        # sanity: emission happened on the (non-stdout) console channel = stderr
        assert buf_err.getvalue().count("\n") == 5, (
            "expected exactly 5 stderr lines (one per level), got: "
            f"{buf_err.getvalue()!r}"
        )


# ===========================================================================
# TEST 3 — stdlib FALLBACK path is selected and remains correct
# ===========================================================================

class TestStdlibFallback:
    def test_fallback_active_and_contract_holds(self, tmp_path):
        """[BEHAVIORAL] Force the structlog import to fail -> the stdlib path is
        active (backend_name() == 'stdlib') and a line still has the correct
        shape; one-line-per-call, never-stdout, and never-raise all hold on the
        fallback path."""
        log, restore = _reload_log_with_structlog_blocked()
        try:
            assert log._STRUCTLOG_AVAILABLE is False, "structlog should be blocked"
            assert log.backend_name() == "stdlib"

            # shape + one line per call
            run_dir = tmp_path / "run"
            lg = log.get_logger("fb", run_dir=str(run_dir), console_level="DEBUG")
            lg.info("fallback line", k="v", n=7)
            recs = _read_jsonl(str(run_dir / "log.jsonl"))
            assert len(recs) == 1
            rec = recs[0]
            assert set(rec) == {"ts", "level", "logger", "msg", "k", "n"}, rec
            assert rec["level"] == "INFO"
            assert rec["logger"] == "fb"
            assert rec["k"] == "v" and rec["n"] == 7

            # never stdout on the fallback path
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                lg.debug("d"); lg.info("i"); lg.warning("w"); lg.error("e")
            assert buf_out.getvalue() == "", buf_out.getvalue()
            assert buf_err.getvalue() != "", "expected stderr emission on fallback"

            # never-raise on the fallback path: bad dir + non-serializable field
            blocker = tmp_path / "blocker"
            blocker.write_text("not a dir")
            bad = log.get_logger("fb-bad", run_dir=str(blocker / "x" / "y"))
            bad.error("must not raise on un-creatable dir")
            lg.info("weird field", weird=object())  # must not raise

            # bind_context works under fallback too (stdlib contextvars)
            log.bind_context(run_id="RFB")
            lg.info("ctx-fallback")
            recs = _read_jsonl(str(run_dir / "log.jsonl"))
            assert recs[-1].get("run_id") == "RFB", recs[-1]
            log.clear_context()
        finally:
            restore()

    def test_backend_restored_after_fallback(self):
        """[BEHAVIORAL] After the fallback test restores the import, a fresh
        import gets the structlog backend back (no leaked global state)."""
        log = _fresh_log_module()
        assert log.backend_name() == "structlog"


# ===========================================================================
# TEST 4 — bind_context + per-thread isolation under concurrency
# ===========================================================================

class TestBindContextConcurrency:
    def test_bound_fields_appear_in_subsequent_emits(self, tmp_path):
        """[BEHAVIORAL] bind_context(run_id=, role=) -> subsequent emits carry
        run_id + role in the JSON line."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        lg = log.get_logger("sl4", run_dir=str(run_dir))
        log.bind_context(run_id="R-main", role="coder")
        try:
            lg.info("bound")
            rec = _read_jsonl(str(run_dir / "log.jsonl"))[-1]
            assert rec["run_id"] == "R-main"
            assert rec["role"] == "coder"
        finally:
            log.clear_context()

    def test_no_cross_thread_leak_under_concurrency(self, tmp_path):
        """[BEHAVIORAL] >=4 concurrent threads each bind a DISTINCT (run_id, role)
        INSIDE the thread and emit many lines; every persisted line must carry
        the binding of the thread that wrote it — no cross-thread leak (mirrors
        exp1's per-thread contextvars isolation). We correlate each line to its
        owning thread by a unique per-emit ``tag`` field (file order interleaves
        under concurrent appends, so we never rely on position)."""
        log = _fresh_log_module()
        run_dir = tmp_path / "run"
        lg = log.get_logger("sl4c", run_dir=str(run_dir))

        N_WORKERS = 6
        K_LINES = 40
        barrier = threading.Barrier(N_WORKERS)
        # expected[tag] = (run_id, role) the writing thread had bound
        expected = {}
        exp_lock = threading.Lock()

        def worker(w):
            run_id = "run-%d" % w
            role = "role-%d" % w
            # Bind INSIDE the worker thread -> visible only to this thread's
            # subsequent emits if isolation holds.
            log.bind_context(run_id=run_id, role=role)
            local = {}
            barrier.wait()  # release together -> maximal interleave of appends
            for i in range(K_LINES):
                tag = "%d:%d" % (w, i)
                lg.info("emit", tag=tag)
                local[tag] = (run_id, role)
            with exp_lock:
                expected.update(local)

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(N_WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        records = _read_jsonl(str(run_dir / "log.jsonl"))
        assert len(records) == N_WORKERS * K_LINES, (
            f"expected {N_WORKERS * K_LINES} lines, got {len(records)}"
        )
        seen = set()
        for rec in records:
            tag = rec.get("tag")
            assert tag in expected, f"unexpected/missing tag in {rec}"
            exp_run, exp_role = expected[tag]
            assert rec.get("run_id") == exp_run and rec.get("role") == exp_role, (
                f"cross-thread context leak: line {rec} should carry "
                f"({exp_run}, {exp_role})"
            )
            seen.add(tag)
        assert seen == set(expected), "some emitted lines were lost"


# ===========================================================================
# TEST 5 — never-raise + idempotent under the structlog backend
# ===========================================================================

class TestNeverRaiseAndIdempotentStructlog:
    def test_never_raises_bad_dir_and_bad_field(self, tmp_path):
        """[BEHAVIORAL] Under the structlog backend, an un-creatable run_dir and a
        non-JSON-serializable field both leave the call returning normally."""
        log = _fresh_log_module()
        assert log.backend_name() == "structlog"
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a directory")
        bad_run_dir = blocker / "cannot" / "exist"
        lg_bad = log.get_logger("sl5a", run_dir=str(bad_run_dir))
        lg_bad.error("must not raise — un-creatable path")  # must not raise

        run_dir = tmp_path / "run"
        lg = log.get_logger("sl5b", run_dir=str(run_dir))
        lg.info("weird field", weird=object())  # must not raise
        # and a line was still written (with the field coerced, not dropped-as-crash)
        recs = _read_jsonl(str(run_dir / "log.jsonl"))
        assert len(recs) == 1 and recs[0]["msg"] == "weird field"

    def test_idempotent_one_line_per_call(self, tmp_path):
        """[BEHAVIORAL] Under the structlog backend, get_logger twice with the same
        (name, run_dir) returns the SAME instance and a single emit writes exactly
        ONE line (no duplicate handler / double-write)."""
        log = _fresh_log_module()
        assert log.backend_name() == "structlog"
        run_dir = tmp_path / "run"
        lg1 = log.get_logger("sl5c", run_dir=str(run_dir))
        lg2 = log.get_logger("sl5c", run_dir=str(run_dir))
        assert lg1 is lg2, "get_logger must be idempotent for identical (name, run_dir)"
        lg2.info("once")
        recs = _read_jsonl(str(run_dir / "log.jsonl"))
        assert len(recs) == 1, f"expected exactly 1 line, got {len(recs)}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
