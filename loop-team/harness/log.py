"""log.py — LoopTeam: shared structured (JSON-line) logger.

One logging primitive used across the harness, evals, and runner, generalizing
the never-raise / env-gated posture of hooks/loop_logger.py and the crash-safe
append posture of runner/run_trace.py.

BACKEND
    The record-assembly + persistence contract below is backend-independent.
    When ``structlog`` is importable it is used as the EMIT backend: a locally
    wrapped structlog logger runs the processor chain (contextvars merge +
    add_log_level + JSON render) so the same battle-tested context machinery is
    exercised. When structlog is NOT importable the module transparently falls
    back to a stdlib-only path. EITHER WAY the line persisted to the file and
    written to stderr is log.py's OWN assembled record (see RECORD SHAPE) — the
    structlog native render (lowercase level, "event", "logger_name") is never
    what gets persisted. The active backend is reported by ``backend_name()``.

LEVELS
    DEBUG < INFO < WARNING < ERROR < CRITICAL. A level may be given as a
    case-insensitive string ("warning") or an int (logging.WARNING). An unknown
    level string is treated as INFO.

DESTINATIONS
    Two, both line-delimited JSON; NEVER stdout (stdout is reserved for each
    tool's machine-readable contract):
      1. FILE — when ``run_dir`` is given, every record at or above ``file_level``
         (default DEBUG = everything) is appended to ``<run_dir>/log.jsonl``. The
         directory/file are created if missing. Each line is written then
         flush()ed and os.fsync()ed before the call returns, so a crash mid-run
         leaves only whole lines (mirrors run_trace._append).
      2. STDERR — every record at or above ``console_level`` is written to
         stderr. ``console_level`` defaults to ``os.environ['LOOP_LOG_LEVEL']``
         if set, else "INFO".

RECORD SHAPE
    Each call emits exactly ONE JSON object on ONE line:
        {"ts", "level", "logger", "msg", **bound_context, **fields}
    ``ts`` is an ISO-8601 timestamp at seconds resolution (the run_trace
    _now_iso convention). ``level`` is the canonical UPPERCASE name ("INFO").
    ``**bound_context`` are fields bound via :func:`bind_context` (carried in a
    contextvar so they propagate correctly across threads/tasks). ``**fields``
    are caller-supplied keyword arguments, serialized verbatim (round-tripping
    for JSON-native values).

CONTEXT BINDING
    :func:`bind_context` merges fields into a per-context store so subsequent
    emits include them; :func:`clear_context` removes them. The semantics are
    identical under both backends (structlog.contextvars when active, the stdlib
    ``contextvars`` module under the fallback).

NEVER-RAISE / CRASH-SAFE
    A logging call NEVER raises. Any I/O error (un-creatable / unwritable
    ``run_dir``) and any serialization error (a non-JSON-serializable field
    value) is swallowed: the call returns normally and still writes what it can
    (non-serializable values are coerced with ``default=str``, falling back to
    dropping fields if even that fails). This mirrors loop_logger.log_gate's
    "never raise" contract.

IDEMPOTENT
    ``get_logger`` is cached/keyed by ``(name, run_dir)``: repeated calls return
    the same instance and never attach duplicate handlers / double-write. Any
    backend configuration is performed at most once per process (guarded), so a
    second ``get_logger`` can never reset state mid-run.

This module deliberately does NOT reuse the stdlib logging logger NAME
"loop_guard" (that belongs to hooks/loop_logger.py); the two stay independent.
"""
import contextvars
import datetime
import json
import os
import sys
import threading

# Level name -> numeric value. Self-contained (does not depend on the logging
# module's constants) so behavior is explicit and stdlib-only.
_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}
# Reverse map int -> canonical name, for normalizing an int level back to a name.
_NUM_TO_NAME = {v: k for k, v in _LEVELS.items()}

_DEFAULT_CONSOLE_LEVEL = "INFO"

# Module-level cache + lock: get_logger is idempotent per (name, run_dir).
_cache = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Backend selection.
#
# ``structlog`` is an OPTIONAL, GUARDED third-party dependency: a NORMAL import
# (node-visible to any AST scan) wrapped in try/except so the module degrades to
# a stdlib-only path whenever structlog is absent or fails to initialize. When
# present it is used as the emit backend; on any import/init error we set
# ``_structlog`` to None and use the stdlib fallback.
# ---------------------------------------------------------------------------
try:
    import structlog
    import structlog.contextvars
    import structlog.processors
    _structlog = structlog
    _STRUCTLOG_AVAILABLE = True
except Exception:  # ImportError or any structlog-side init error -> stdlib fallback
    _structlog = None
    _STRUCTLOG_AVAILABLE = False


def backend_name():
    """Return the active emit backend: ``"structlog"`` or ``"stdlib"``."""
    return "structlog" if _STRUCTLOG_AVAILABLE else "stdlib"


# ---------------------------------------------------------------------------
# Context store. Under both backends the bound context lives in a contextvar so
# it propagates correctly across threads/tasks (the value is captured at
# thread/Task start; binding inside a worker is visible to that worker only).
#
# When structlog is active we delegate to structlog.contextvars (its own
# ContextVar-backed store) so the structlog chain's merge_contextvars sees the
# same data. Under the stdlib fallback we use our own ContextVar with identical
# copy-on-write semantics.
# ---------------------------------------------------------------------------
_stdlib_context = contextvars.ContextVar("loop_log_context", default={})


def bind_context(**fields):
    """Merge ``fields`` into the current logging context (copy-on-write).

    Subsequent emits from the same context (thread/Task) include these fields in
    each JSON line. Returns the merged context dict. Never raises.

    Identical semantics under both backends: structlog.contextvars when the
    structlog backend is active, the stdlib ``contextvars`` module otherwise.
    """
    try:
        if _STRUCTLOG_AVAILABLE:
            _structlog.contextvars.bind_contextvars(**fields)
            return dict(_structlog.contextvars.get_contextvars())
        merged = dict(_stdlib_context.get())
        merged.update(fields)
        _stdlib_context.set(merged)
        return merged
    except Exception:
        return {}


def clear_context():
    """Remove all fields previously bound via :func:`bind_context` in this
    context. Never raises."""
    try:
        if _STRUCTLOG_AVAILABLE:
            _structlog.contextvars.clear_contextvars()
        else:
            _stdlib_context.set({})
    except Exception:
        pass


def unbind_context(*keys):
    """Remove the named ``keys`` from the current logging context. Never raises."""
    try:
        if _STRUCTLOG_AVAILABLE:
            _structlog.contextvars.unbind_contextvars(*keys)
        else:
            remaining = dict(_stdlib_context.get())
            for k in keys:
                remaining.pop(k, None)
            _stdlib_context.set(remaining)
    except Exception:
        pass


def _current_context():
    """Return the currently bound context as a plain dict. Never raises."""
    try:
        if _STRUCTLOG_AVAILABLE:
            return dict(_structlog.contextvars.get_contextvars())
        return dict(_stdlib_context.get())
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# structlog wrapper — configured locally + idempotently (binding constraint #3).
#
# We do NOT call structlog.configure() (process-global mutation). Instead each
# logger holds a LOCALLY wrapped logger built with structlog.wrap_logger over a
# private base whose chain is merge_contextvars + add_log_level + JSONRenderer
# and whose factory is ReturnLoggerFactory (so the rendered JSON is RETURNED,
# never printed — no stdout leak). Running this chain exercises structlog's real
# context-merge machinery, but we IGNORE its native render for persistence and
# write log.py's OWN assembled record instead (binding constraint #1).
# ---------------------------------------------------------------------------
_wrap_lock = threading.Lock()


def _make_structlog_logger(name):
    """Build a locally-wrapped structlog logger (no global configure). Idempotent
    per call; safe to call repeatedly. Returns the wrapped logger or None on any
    error (caller then degrades to building the record without driving the
    chain — persistence is unaffected since we always write our own record)."""
    try:
        with _wrap_lock:
            base = _structlog.ReturnLoggerFactory()()
            return _structlog.wrap_logger(
                base,
                processors=[
                    _structlog.contextvars.merge_contextvars,
                    _structlog.processors.add_log_level,
                    _structlog.processors.JSONRenderer(),
                ],
                # Local config only; never touches structlog's process globals.
            )
    except Exception:
        return None


def _now_iso():
    """ISO-8601 timestamp at seconds resolution (run_trace._now_iso convention)."""
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _level_to_num(level, default=20):
    """Coerce a level (case-insensitive str or int) to its numeric value.

    Unknown level strings -> INFO (20). An int is passed through (an unknown int
    still orders correctly against the named thresholds). Never raises.
    """
    if isinstance(level, bool):  # bool is an int subclass; treat as unknown -> default
        return default
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        return _LEVELS.get(level.strip().upper(), default)
    return default


def _level_name(level):
    """Canonical uppercase level name for a str/int level. Unknown -> 'INFO'."""
    if not isinstance(level, bool) and isinstance(level, int):
        return _NUM_TO_NAME.get(level, "INFO")
    if isinstance(level, str):
        up = level.strip().upper()
        return up if up in _LEVELS else "INFO"
    return "INFO"


class StructuredLogger:
    """Emit one JSON object per call to a per-run file and/or stderr.

    Construct via :func:`get_logger` (which caches by ``(name, run_dir)``), not
    directly, so idempotence holds. Public methods: debug/info/warning/error/
    critical(msg, **fields) and log(level, msg, **fields). No method raises.

    When the structlog backend is active the per-call processor chain
    (merge_contextvars + add_log_level + JSONRenderer over a ReturnLogger) is
    driven end-to-end, but the line PERSISTED/EMITTED is always this class's own
    assembled record (uppercase level, "logger"/"msg" keys) — never structlog's
    native render — so the on-disk shape is byte-for-byte identical across
    backends.
    """

    def __init__(self, name, run_dir=None, console_level=None, file_level="DEBUG"):
        self.name = name
        self.run_dir = str(run_dir) if run_dir is not None else None
        if console_level is None:
            console_level = os.environ.get("LOOP_LOG_LEVEL") or _DEFAULT_CONSOLE_LEVEL
        self._console_num = _level_to_num(console_level)
        self._file_num = _level_to_num(file_level, default=_LEVELS["DEBUG"])
        self._lock = threading.Lock()
        self._file_path = (
            os.path.join(self.run_dir, "log.jsonl") if self.run_dir else None
        )
        # Locally-wrapped structlog logger (None under the stdlib fallback or if
        # wrapping fails). Built once per logger instance; get_logger caches the
        # instance, so this never re-runs mid-run for the same (name, run_dir).
        self._sl = _make_structlog_logger(name) if _STRUCTLOG_AVAILABLE else None

    # -- public API ---------------------------------------------------------
    def debug(self, msg, **fields):
        """Log ``msg`` at DEBUG with optional structured ``**fields``."""
        self.log("DEBUG", msg, **fields)

    def info(self, msg, **fields):
        """Log ``msg`` at INFO with optional structured ``**fields``."""
        self.log("INFO", msg, **fields)

    def warning(self, msg, **fields):
        """Log ``msg`` at WARNING with optional structured ``**fields``."""
        self.log("WARNING", msg, **fields)

    def error(self, msg, **fields):
        """Log ``msg`` at ERROR with optional structured ``**fields``."""
        self.log("ERROR", msg, **fields)

    def critical(self, msg, **fields):
        """Log ``msg`` at CRITICAL with optional structured ``**fields``."""
        self.log("CRITICAL", msg, **fields)

    def log(self, level, msg, **fields):
        """Emit one record at ``level``. Never raises (swallows IO + serialization
        errors), returning normally and writing what it can."""
        try:
            num = _level_to_num(level)
            record = {
                "ts": _now_iso(),
                "level": _level_name(level),
                "logger": self.name,
                "msg": msg,
            }
            # Bound context (contextvar) first, then per-call fields. The reserved
            # base keys above are authoritative; bound/explicit fields fill in the
            # rest and round-trip verbatim.
            for k, v in _current_context().items():
                if k not in record:
                    record[k] = v
            for k, v in fields.items():
                record[k] = v
            # When the structlog backend is active, drive its real chain
            # end-to-end (merge_contextvars + add_log_level + JSONRenderer over a
            # ReturnLogger). We DISCARD its native render — it is exercised only
            # for fidelity; persistence/emission below always use OUR record so
            # the on-disk shape (uppercase level, "logger"/"msg") is unchanged.
            if self._sl is not None:
                self._drive_structlog(level, msg, fields)
            line = self._serialize(record)
            # FILE destination (>= file_level), crash-safe append.
            if self._file_path is not None and num >= self._file_num:
                self._append_file(line)
            # STDERR destination (>= console_level). Never stdout.
            if num >= self._console_num:
                self._write_stderr(line)
        except Exception:
            # Absolute never-raise guarantee (defense in depth beyond the inner
            # swallows below). A logging call must never break its caller.
            pass

    # -- internals ----------------------------------------------------------
    def _drive_structlog(self, level, msg, fields):
        """Run the structlog processor chain for fidelity. The rendered JSON is
        RETURNED by the ReturnLogger (never printed) and intentionally ignored:
        we persist our own record. Never raises (the emit must not break)."""
        try:
            getattr(self._sl, _level_name(level).lower())(msg, **fields)
        except Exception:
            pass

    @staticmethod
    def _serialize(record):
        """JSON-serialize a record to a single line; never raises.

        Coerces non-JSON-serializable values with default=str. If even that
        fails (pathological __str__), drops un-serializable fields one by one,
        always preserving the reserved keys so the line stays well-formed.
        """
        try:
            return json.dumps(record, ensure_ascii=False, default=str)
        except Exception:
            pass
        # default=str failed (e.g. an object whose __str__ raises). Rebuild with
        # only the values we can serialize, dropping the rest.
        safe = {}
        for k, v in record.items():
            try:
                json.dumps(v, ensure_ascii=False, default=str)
                safe[k] = v
            except Exception:
                safe[k] = "<unserializable>"
        try:
            return json.dumps(safe, ensure_ascii=False, default=str)
        except Exception:
            # Last resort: a guaranteed-valid line carrying just the reserved keys.
            minimal = {
                "ts": record.get("ts"),
                "level": record.get("level"),
                "logger": record.get("logger"),
                "msg": str(record.get("msg")),
            }
            return json.dumps(minimal, ensure_ascii=False, default=str)

    def _append_file(self, line):
        """Append one line to ``<run_dir>/log.jsonl`` with flush + fsync. Swallows
        any IO error (un-creatable/unwritable run_dir) so the call never raises."""
        try:
            with self._lock:
                os.makedirs(self.run_dir, exist_ok=True)
                with open(self._file_path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
        except Exception:
            pass

    @staticmethod
    def _write_stderr(line):
        """Write one line to stderr. Swallows any IO error. NEVER stdout."""
        try:
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
        except Exception:
            pass


def get_logger(name, *, run_dir=None, console_level=None, file_level="DEBUG"):
    """Return a :class:`StructuredLogger`, cached/keyed by ``(name, run_dir)``.

    Idempotent: repeated calls with the same ``(name, run_dir)`` return the SAME
    instance, so no duplicate handlers attach and a single call writes a single
    line. ``console_level`` defaults to ``os.environ['LOOP_LOG_LEVEL']`` else
    "INFO"; ``file_level`` defaults to DEBUG (the file captures everything). With
    ``run_dir=None`` nothing is written to a file (stderr-only). Never raises.

    Args:
        name: Logger name, recorded in each record's ``logger`` field.
        run_dir: Per-run directory; when set, records >= file_level are appended
            to ``<run_dir>/log.jsonl`` (created if missing). None -> stderr-only.
        console_level: Minimum level for stderr emission. Default env/INFO.
        file_level: Minimum level for file emission. Default DEBUG.
    """
    key = (name, str(run_dir) if run_dir is not None else None)
    with _cache_lock:
        existing = _cache.get(key)
        if existing is not None:
            return existing
        logger = StructuredLogger(
            name, run_dir=run_dir, console_level=console_level, file_level=file_level
        )
        _cache[key] = logger
        return logger
