#!/usr/bin/env python3
"""
loop_logger.py — Debug logging for loop stop-guard gates.

Enable by setting LOOP_GUARD_DEBUG=1 in the environment.
Writes JSON-line records to ~/.loop-guard/debug.log (RotatingFileHandler, 5MB × 3).

Override the log directory with _LOOP_GUARD_LOG_DIR_OVERRIDE (used in tests).
"""
import json
import logging
import logging.handlers
import os

_logger_cache = {}


def get_loop_logger():
    """Return a configured Logger, or None if debug is disabled or setup fails."""
    if not os.environ.get("LOOP_GUARD_DEBUG"):
        return None
    if "_logger" in _logger_cache:
        return _logger_cache["_logger"]
    try:
        log_dir = (
            os.environ.get("_LOOP_GUARD_LOG_DIR_OVERRIDE")
            or os.path.expanduser("~/.loop-guard")
        )
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "debug.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        lgr = logging.getLogger("loop_guard")
        lgr.setLevel(logging.DEBUG)
        if not lgr.handlers:
            lgr.addHandler(handler)
        lgr.propagate = False
        _logger_cache["_logger"] = lgr
        return lgr
    except Exception:
        _logger_cache["_logger"] = None
        return None


def log_gate(gate, fired, matched, exit_code):
    """Log a gate check result. Never raises."""
    try:
        lgr = get_loop_logger()
        if lgr:
            lgr.info(
                json.dumps(
                    {
                        "gate": gate,
                        "fired": bool(fired),
                        "matched": (matched or "")[:200],
                        "exit_code": exit_code,
                    }
                )
            )
    except Exception:
        pass
