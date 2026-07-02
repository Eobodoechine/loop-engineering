#!/usr/bin/env python3
"""Tests for loop_logger.py — gate debug logging."""
import json
import logging
import os
import sys
import pytest

# Ensure hooks/ is on sys.path
sys.path.insert(0, os.path.dirname(__file__))
import loop_logger as _ll


@pytest.fixture(autouse=True)
def isolate_logger(tmp_path, monkeypatch):
    """Each test gets a fresh cache and isolated log directory."""
    _ll._logger_cache.clear()
    logging.getLogger("loop_guard").handlers.clear()
    monkeypatch.setenv("_LOOP_GUARD_LOG_DIR_OVERRIDE", str(tmp_path))
    yield
    _ll._logger_cache.clear()
    logging.getLogger("loop_guard").handlers.clear()


class TestLogGate:
    def test_writes_json_when_debug_enabled(self, tmp_path, monkeypatch):
        """AC 1: log_gate writes a parseable JSON record when LOOP_GUARD_DEBUG=1."""
        monkeypatch.setenv("LOOP_GUARD_DEBUG", "1")
        _ll.log_gate("TEST_GATE", True, "matched text", 2)
        log_file = tmp_path / "debug.log"
        assert log_file.exists(), "debug.log should be created when debug enabled"
        data = json.loads(log_file.read_text().strip())
        assert data["gate"] == "TEST_GATE"
        assert data["fired"] is True
        assert data["matched"] == "matched text"
        assert data["exit_code"] == 2

    def test_no_file_without_debug_flag(self, tmp_path, monkeypatch):
        """AC 2: no file created when LOOP_GUARD_DEBUG is absent."""
        monkeypatch.delenv("LOOP_GUARD_DEBUG", raising=False)
        _ll.log_gate("TEST_GATE", False, "", 0)
        log_file = tmp_path / "debug.log"
        assert not log_file.exists(), "debug.log must NOT be created without LOOP_GUARD_DEBUG"

    def test_no_duplicate_handlers(self, monkeypatch):
        """AC 3: calling get_loop_logger() twice adds at most one handler."""
        monkeypatch.setenv("LOOP_GUARD_DEBUG", "1")
        _ll.get_loop_logger()
        _ll._logger_cache.clear()  # force re-entry
        _ll.get_loop_logger()
        assert len(logging.getLogger("loop_guard").handlers) <= 1
