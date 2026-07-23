#!/usr/bin/env python3
"""One-shot raw Codex hook stdin capture for AC-1 verification.

This module is intentionally dormant unless hooks/fixtures/ac1_capture_once.marker
exists. When armed, the next real Stop/SubagentStop hook invocation writes the
raw stdin JSON payload verbatim to hooks/fixtures/ac1_captured_codex_stop_stdin.json
and removes the marker best-effort.
"""
import json
import os
import tempfile


_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
_FIXTURES_DIR = os.path.join(_HOOKS_DIR, "fixtures")
MARKER_PATH = os.path.join(_FIXTURES_DIR, "ac1_capture_once.marker")
FIXTURE_PATH = os.path.join(_FIXTURES_DIR, "ac1_captured_codex_stop_stdin.json")
META_PATH = os.path.join(_FIXTURES_DIR, "ac1_captured_codex_stop_stdin.meta.json")


def capture_once(raw_stdin, source_hook):
    """Best-effort one-shot capture of real hook stdin; never affects gates."""
    try:
        if not os.path.exists(MARKER_PATH):
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            return
        hook_event = payload.get("hook_event_name")
        if hook_event not in ("Stop", "SubagentStop"):
            return
        os.makedirs(_FIXTURES_DIR, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".ac1_capture.", suffix=".json", dir=_FIXTURES_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(raw_stdin)
                if raw_stdin and not raw_stdin.endswith("\n"):
                    f.write("\n")
            os.replace(tmp_path, FIXTURE_PATH)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        meta = {
            "source_hook": source_hook,
            "hook_event_name": hook_event,
            "captured_from_real_hook_process": True,
            "fixture_path": FIXTURE_PATH,
        }
        fd, tmp_meta = tempfile.mkstemp(
            prefix=".ac1_capture.", suffix=".meta.json", dir=_FIXTURES_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(meta, f, sort_keys=True, indent=2)
                f.write("\n")
            os.replace(tmp_meta, META_PATH)
        finally:
            if os.path.exists(tmp_meta):
                os.unlink(tmp_meta)
        try:
            os.unlink(MARKER_PATH)
        except OSError:
            pass
    except Exception:
        return
