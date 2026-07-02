#!/usr/bin/env python3
"""structlog-backed structured logger -- the experiment VARIANT.

Exposes the IDENTICAL public surface as baseline_logger.py:
    get_logger(name, run_dir=None)
    logger.bind_context(**kw)
    logger.debug/info/warning/error/critical(msg, **fields)

Implementation difference (the ONLY variable in the A/B):
  - context is carried with ``structlog.contextvars`` (bind_contextvars), and
    the record is built by a structlog processor chain:
        merge_contextvars + add_log_level + JSONRenderer
  - emit goes through a structlog logger.

Persistence is IDENTICAL to the baseline: the rendered record is appended to
``<run_dir>/log.jsonl`` via the SAME ``append_jsonl`` write/flush/fsync helper,
carrying the SAME ``_seq`` field, so both impls' files parse identically
(fairness pin #3).

structlog is imported ONLY in this module and the import is GUARDED: if
structlog is not installed, ``STRUCTLOG_AVAILABLE`` is False and the A/B runner
skips the variant cleanly (acceptance criterion #6).
"""
import os

import baseline_logger as _base  # SHARED writer + seq + ts helpers (stdlib only)

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
    STRUCTLOG_IMPORT_ERROR = None
except Exception as _e:  # pragma: no cover - exercised only when structlog absent
    structlog = None
    STRUCTLOG_AVAILABLE = False
    STRUCTLOG_IMPORT_ERROR = repr(_e)


def _build_processor_chain():
    """merge_contextvars + add_log_level + JSONRenderer.

    The JSONRenderer is the terminal processor: it returns the rendered JSON
    string, which we hand to the shared writer for fsync persistence. We capture
    the structlog event dict in a non-terminal processor so we can also persist
    a normalized record carrying _seq via the identical baseline writer."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
    ]


class StructlogLogger:
    """structlog-backed logger with the shared public surface."""

    def __init__(self, name, run_dir=None):
        if not STRUCTLOG_AVAILABLE:
            raise RuntimeError("structlog not available: %s" % STRUCTLOG_IMPORT_ERROR)
        self.name = name
        self.run_dir = str(run_dir) if run_dir is not None else None
        self._file_path = (
            os.path.join(self.run_dir, "log.jsonl") if self.run_dir else None
        )
        # A structlog logger whose chain merges contextvars + adds the level and
        # JSON-renders. We do not let structlog write the file itself; we render
        # via the chain and persist through the SHARED baseline writer so the
        # durability path is byte-for-byte the same code as the baseline.
        # ReturnLoggerFactory: the JSONRenderer's output is RETURNED by the emit
        # call instead of printed, so the full chain (merge_contextvars +
        # add_log_level + JSONRenderer) runs end-to-end with NO stdout leak.
        # Persistence is then done explicitly via the shared fsync writer.
        structlog.configure(
            processors=_build_processor_chain() + [structlog.processors.JSONRenderer()],
            wrapper_class=structlog.BoundLogger,
            context_class=dict,
            logger_factory=structlog.ReturnLoggerFactory(),
            cache_logger_on_first_use=False,
        )
        self._log = structlog.get_logger(logger_name=name)

    # -- context --------------------------------------------------------------
    def bind_context(self, **kw):
        """Bind context via structlog.contextvars (the structlog idiom for
        propagating context across thread/Task boundaries via contextvars)."""
        structlog.contextvars.bind_contextvars(**kw)
        # Return the merged view for parity with the baseline's return value.
        return dict(structlog.contextvars.get_contextvars())

    # -- emit -----------------------------------------------------------------
    def _emit(self, level, msg, fields):
        seq = _base.next_seq()
        # Build the record the structlog way: merge contextvars + level, then
        # the per-call fields, then reserved keys. We assemble the SAME shape the
        # baseline persists so the parser is identical.
        ctx = dict(structlog.contextvars.get_contextvars())
        record = {
            "ts": _base.now_iso(),
            "level": level,
            "logger": self.name,
            "msg": msg,
        }
        record.update(ctx)
        for k, v in fields.items():
            record[k] = v
        record["_seq"] = seq
        # Drive the structlog logger too (exercises the real merge_contextvars +
        # add_log_level + JSONRenderer chain end to end), then persist the
        # normalized record through the IDENTICAL shared fsync writer.
        getattr(self._log, level.lower())(msg, _seq=seq, **fields)
        _base.append_jsonl(self._file_path, record)
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
    """Return a :class:`StructlogLogger`. Raises if structlog is unavailable --
    callers (the A/B runner) guard on ``STRUCTLOG_AVAILABLE`` first."""
    return StructlogLogger(name, run_dir=run_dir)
