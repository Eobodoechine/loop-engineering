#!/usr/bin/env python3
"""STEELMAN stdlib structured logger -- the experiment BASELINE.

Public surface (the IDENTICAL contract both impls expose; the only variable
between baseline and variant is the emit/context-propagation path):

    get_logger(name, run_dir=None)        -> logger
    logger.bind_context(**kw)             -> merges kw into the per-context dict
    logger.debug/info/warning/error/critical(msg, **fields)

Each emit writes exactly ONE JSON line to ``<run_dir>/log.jsonl``:
    {"ts", "level", "logger", "msg", **bound_context, **fields, "_seq"}
with write -> flush() -> os.fsync() under a lock, mirroring harness/log.py's
crash-safe append (whole lines survive a crash mid-run).

Context is carried with the stdlib ``contextvars`` module: a single ContextVar
holds a dict, and ``bind_context`` MERGES into a fresh copy of the current dict
and re-sets the var. Because contextvars propagate the value captured at
thread/Task start, binding INSIDE a worker thread or asyncio task is visible to
that worker's own subsequent emits -- this is a correctly-scoped logger, NOT a
broken process-global. That correctness is the whole point: a steelman stdlib
impl that genuinely associates the right (run_id, role) with each line.

This module imports NO third-party package (stdlib only), by design and by test.
"""
import contextvars
import datetime
import itertools
import json
import os
import threading

# ---------------------------------------------------------------------------
# Shared persistence helper -- the SINGLE write/flush/fsync path. The structlog
# variant imports and uses THIS SAME helper so both impls persist identically
# and are parsed identically (fairness pin #3).
# ---------------------------------------------------------------------------

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

# Process-wide monotonic sequence source. Every emit (either impl) draws a unique
# id from here, so _seq is globally unique and the scorer can match an emitted
# line to its expected tuple BY _seq regardless of interleaved write order
# (fairness pin #1).
_seq_counter = itertools.count()
_seq_lock = threading.Lock()


def next_seq():
    """Return the next globally-unique, monotonic sequence id (thread-safe)."""
    with _seq_lock:
        return next(_seq_counter)


def now_iso():
    """ISO-8601 timestamp at seconds resolution (harness/log.py _now_iso)."""
    return datetime.datetime.now().replace(microsecond=0).isoformat()


# One lock per file path, so two loggers pointed at the same log.jsonl serialize
# their appends. Mirrors harness/log.py's per-logger lock but keyed by path so
# the shared writer is correct even across logger instances.
_file_locks = {}
_file_locks_guard = threading.Lock()


def _lock_for(path):
    with _file_locks_guard:
        lk = _file_locks.get(path)
        if lk is None:
            lk = threading.Lock()
            _file_locks[path] = lk
        return lk


def append_jsonl(file_path, record):
    """Serialize ``record`` and append ONE line to ``file_path`` with
    flush + os.fsync under a per-path lock. Never raises (mirrors harness/log.py
    durability + never-raise posture). This is the SHARED writer for both impls."""
    if file_path is None:
        return
    try:
        line = json.dumps(record, ensure_ascii=False, default=str)
    except Exception:
        line = json.dumps({"ts": record.get("ts"), "level": record.get("level"),
                           "logger": record.get("logger"),
                           "msg": str(record.get("msg")),
                           "_seq": record.get("_seq")}, default=str)
    try:
        lock = _lock_for(file_path)
        with lock:
            d = os.path.dirname(file_path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(file_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Stdlib baseline logger
# ---------------------------------------------------------------------------

# A single ContextVar holding the bound-context dict. Default is an empty dict;
# bind_context never mutates the dict in place (it sets a NEW dict) so the value
# captured by a thread/Task at start is never aliased across contexts.
_context = contextvars.ContextVar("loop_log_context", default={})


class StdlibLogger:
    """Steelman stdlib structured logger. Construct via :func:`get_logger`."""

    def __init__(self, name, run_dir=None):
        self.name = name
        self.run_dir = str(run_dir) if run_dir is not None else None
        self._file_path = (
            os.path.join(self.run_dir, "log.jsonl") if self.run_dir else None
        )

    # -- context --------------------------------------------------------------
    def bind_context(self, **kw):
        """Merge ``kw`` into the current context dict (copy-on-write).

        Uses the stdlib contextvars ContextVar: read the current dict, build a
        NEW dict that is {current ** kw}, and set it. Binding inside a worker
        thread/Task thus affects only that worker's context and is seen by that
        worker's later emits -- correct propagation, not a global."""
        merged = dict(_context.get())
        merged.update(kw)
        _context.set(merged)
        return merged

    # -- emit -----------------------------------------------------------------
    def _emit(self, level, msg, fields):
        seq = next_seq()
        record = {
            "ts": now_iso(),
            "level": level,
            "logger": self.name,
            "msg": msg,
        }
        # bound context first, then per-call fields, then the reserved _seq.
        record.update(_context.get())
        for k, v in fields.items():
            record[k] = v
        record["_seq"] = seq
        append_jsonl(self._file_path, record)
        return seq

    def debug(self, msg, **fields):
        return self._emit("DEBUG", msg, fields)

    def info(self, msg, **fields):
        return self._emit("INFO", msg, fields)

    def warning(self, msg, **fields):
        return self._emit("WARNING", msg, fields)

    def error(self, msg, **fields):
        return self._emit("ERROR", msg, fields)

    def critical(self, msg, **fields):
        return self._emit("CRITICAL", msg, fields)


def get_logger(name, run_dir=None):
    """Return a :class:`StdlibLogger` writing to ``<run_dir>/log.jsonl``.

    A fresh instance each call (the experiment runs are independent and we do
    not want cross-run handler caching to confound the A/B). Never raises."""
    return StdlibLogger(name, run_dir=run_dir)
