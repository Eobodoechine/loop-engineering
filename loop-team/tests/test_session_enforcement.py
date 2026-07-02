"""
Tests for loop-team session enforcement interventions.

Covers:
  AC1  - session_start.sh exits 0 when constraints file exists
  AC2  - session_start.sh outputs valid JSON with hookSpecificOutput.additionalContext
  AC3  - additionalContext is a non-empty string containing "dispatch"
  AC4  - session_start.sh exits 0 silently when constraints file does not exist
  AC5  - orchestrator-constraints.txt exists, is non-empty, and contains all four key rules
  AC6  - ~/.claude/settings.json contains SessionStart with matcher "startup"
  AC7  - orchestrator.md contains dispatch_check JSON structure with all four fields
  AC8  - dispatch_check structure appears BEFORE "If you are not invoking the Agent tool"
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths under test
# ---------------------------------------------------------------------------

LOOP_ROOT = Path.home() / "Claude" / "loop"
HOOKS_DIR = LOOP_ROOT / "hooks"
SESSION_SCRIPT = HOOKS_DIR / "session_start.sh"
CONSTRAINTS_FILE = HOOKS_DIR / "orchestrator-constraints.txt"
ORCHESTRATOR_MD = LOOP_ROOT / "loop-team" / "orchestrator.md"
SETTINGS_JSON = Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_script(env_override=None) -> subprocess.CompletedProcess:
    """Run session_start.sh and capture stdout/stderr/returncode."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    return subprocess.run(
        ["bash", str(SESSION_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )


def run_script_with_fake_constraints(constraints_path: str) -> subprocess.CompletedProcess:
    """
    Run session_start.sh with LOOP_CONSTRAINTS_FILE overridden so the script
    reads from an arbitrary path.  The script must honour this env-var (or
    accept it as a positional arg) — the Coder decides the exact mechanism;
    we try the env-var convention first and fall back to positional arg.
    """
    env = os.environ.copy()
    env["LOOP_CONSTRAINTS_FILE"] = constraints_path
    result = subprocess.run(
        ["bash", str(SESSION_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    # Fallback: try passing path as first positional argument
    if result.returncode != 0 and "LOOP_CONSTRAINTS_FILE" not in open(SESSION_SCRIPT).read():
        result = subprocess.run(
            ["bash", str(SESSION_SCRIPT), constraints_path],
            capture_output=True,
            text=True,
        )
    return result


# ---------------------------------------------------------------------------
# AC1 — script exits 0 when constraints file exists
# ---------------------------------------------------------------------------


class TestAC1_ScriptExitsZeroWithConstraints:
    def test_exits_zero_when_constraints_file_present(self):
        """session_start.sh must exit 0 when orchestrator-constraints.txt exists."""
        assert SESSION_SCRIPT.exists(), (
            f"session_start.sh not found at {SESSION_SCRIPT} — Coder must create it"
        )
        assert CONSTRAINTS_FILE.exists(), (
            f"orchestrator-constraints.txt not found at {CONSTRAINTS_FILE} — Coder must create it"
        )
        result = run_script()
        assert result.returncode == 0, (
            f"session_start.sh exited {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# AC2 — output is valid JSON with hookSpecificOutput.additionalContext
# ---------------------------------------------------------------------------


class TestAC2_ValidJsonOutput:
    def test_stdout_is_valid_json(self):
        """session_start.sh stdout must be parseable as JSON."""
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        assert result.stdout.strip(), (
            "session_start.sh produced no stdout — expected a JSON object"
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"stdout is not valid JSON: {exc}\nRaw stdout: {result.stdout!r}"
            )
        assert isinstance(payload, dict), (
            f"Expected JSON object at top level, got {type(payload).__name__}"
        )

    def test_hookSpecificOutput_key_present(self):
        """Top-level JSON must contain 'hookSpecificOutput' key."""
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        payload = json.loads(result.stdout)
        assert "hookSpecificOutput" in payload, (
            f"'hookSpecificOutput' key missing from JSON output.\nGot keys: {list(payload.keys())}"
        )

    def test_additionalContext_key_present(self):
        """hookSpecificOutput must contain 'additionalContext' key."""
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        payload = json.loads(result.stdout)
        hook_output = payload.get("hookSpecificOutput", {})
        assert "additionalContext" in hook_output, (
            f"'additionalContext' key missing from hookSpecificOutput.\n"
            f"hookSpecificOutput contents: {hook_output}"
        )


# ---------------------------------------------------------------------------
# AC3 — additionalContext is non-empty and contains "dispatch"
# ---------------------------------------------------------------------------


class TestAC3_AdditionalContextContent:
    def _get_additional_context(self) -> str:
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        payload = json.loads(result.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]

    def test_additionalContext_is_string(self):
        ctx = self._get_additional_context()
        assert isinstance(ctx, str), (
            f"additionalContext must be a string, got {type(ctx).__name__}"
        )

    def test_additionalContext_is_non_empty(self):
        ctx = self._get_additional_context()
        assert ctx.strip(), "additionalContext must not be empty"

    def test_additionalContext_contains_dispatch(self):
        ctx = self._get_additional_context()
        assert "dispatch" in ctx.lower(), (
            f"additionalContext does not contain the word 'dispatch'.\n"
            f"Value: {ctx!r}"
        )


# ---------------------------------------------------------------------------
# AC4 — script exits 0 silently when constraints file does not exist
# ---------------------------------------------------------------------------


class TestAC4_SilentExitWhenNoConstraints:
    def test_exits_zero_without_output_when_file_missing(self):
        """
        When the constraints file is absent, session_start.sh must:
          - exit 0
          - produce no stdout
        """
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, "nonexistent_constraints.txt")
            # Ensure the file really does not exist
            assert not os.path.exists(missing_path)
            result = run_script_with_fake_constraints(missing_path)
        assert result.returncode == 0, (
            f"script should exit 0 when constraints file is absent, "
            f"got {result.returncode}.\nstderr: {result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"script should produce no output when constraints file is absent.\n"
            f"Got stdout: {result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# AC5 — orchestrator-constraints.txt exists, non-empty, contains four key rules
# ---------------------------------------------------------------------------


_REQUIRED_PHRASES = [
    "permitted outputs",
    "Agent tool call",
    "routing rationale",
    "self-check",
]


class TestAC5_ConstraintsFileContent:
    def test_constraints_file_exists(self):
        assert CONSTRAINTS_FILE.exists(), (
            f"orchestrator-constraints.txt not found at {CONSTRAINTS_FILE}"
        )

    def test_constraints_file_non_empty(self):
        assert CONSTRAINTS_FILE.exists(), f"orchestrator-constraints.txt missing"
        content = CONSTRAINTS_FILE.read_text(encoding="utf-8")
        assert content.strip(), "orchestrator-constraints.txt must not be empty"

    @pytest.mark.parametrize("phrase", _REQUIRED_PHRASES)
    def test_constraints_file_contains_required_phrase(self, phrase: str):
        assert CONSTRAINTS_FILE.exists(), f"orchestrator-constraints.txt missing"
        content = CONSTRAINTS_FILE.read_text(encoding="utf-8")
        assert phrase.lower() in content.lower(), (
            f"Required phrase {phrase!r} not found in orchestrator-constraints.txt.\n"
            f"(Case-insensitive search over {len(content)} chars.)"
        )


# ---------------------------------------------------------------------------
# AC6 — ~/.claude/settings.json has SessionStart with matcher "startup"
# ---------------------------------------------------------------------------


class TestAC6_SettingsJsonSessionStart:
    def test_settings_json_exists(self):
        assert SETTINGS_JSON.exists(), (
            f"~/.claude/settings.json not found at {SETTINGS_JSON}"
        )

    def test_settings_json_valid(self):
        assert SETTINGS_JSON.exists(), f"settings.json missing"
        try:
            json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(f"settings.json is not valid JSON: {exc}")

    def test_session_start_key_present(self):
        assert SETTINGS_JSON.exists(), f"settings.json missing"
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {})
        assert "SessionStart" in hooks, (
            f"'SessionStart' key missing from settings.json hooks.\n"
            f"hooks keys: {list(hooks.keys())}"
        )

    def test_session_start_has_startup_matcher(self):
        """
        settings.json hooks.SessionStart must contain an entry with matcher: "startup".
        Claude Code reads SessionStart from inside the hooks object, not at top level.
        """
        assert SETTINGS_JSON.exists(), f"settings.json missing"
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {}).get("SessionStart", [])
        if isinstance(hooks, dict):
            hooks = [hooks]
        matchers = [h.get("matcher", "") for h in hooks if isinstance(h, dict)]
        assert "startup" in matchers, (
            f"No SessionStart hook entry with matcher 'startup' found.\n"
            f"Found matchers: {matchers}"
        )


# ---------------------------------------------------------------------------
# AC7 — orchestrator.md contains dispatch_check JSON structure with all four fields
# ---------------------------------------------------------------------------


_DISPATCH_FIELDS = ["task", "role", "why_this_role", "why_not_other"]


class TestAC7_OrchestratorDispatchCheck:
    def test_orchestrator_md_exists(self):
        assert ORCHESTRATOR_MD.exists(), (
            f"orchestrator.md not found at {ORCHESTRATOR_MD}"
        )

    def test_dispatch_check_key_present(self):
        assert ORCHESTRATOR_MD.exists(), f"orchestrator.md missing"
        content = ORCHESTRATOR_MD.read_text(encoding="utf-8")
        assert "dispatch_check" in content, (
            "'dispatch_check' not found in orchestrator.md"
        )

    @pytest.mark.parametrize("field", _DISPATCH_FIELDS)
    def test_dispatch_check_contains_field(self, field: str):
        assert ORCHESTRATOR_MD.exists(), f"orchestrator.md missing"
        content = ORCHESTRATOR_MD.read_text(encoding="utf-8")
        # Field should appear as a JSON key: "field"
        assert f'"{field}"' in content, (
            f"dispatch_check field {field!r} (as JSON key) not found in orchestrator.md"
        )


# ---------------------------------------------------------------------------
# AC8 — dispatch_check structure appears BEFORE "If you are not invoking the Agent tool"
# ---------------------------------------------------------------------------


class TestAC8_DispatchCheckOrderInOrchestrator:
    _SENTINEL = "If you are not invoking the Agent tool"

    def test_dispatch_check_before_sentinel(self):
        assert ORCHESTRATOR_MD.exists(), f"orchestrator.md missing"
        content = ORCHESTRATOR_MD.read_text(encoding="utf-8")

        dc_pos = content.find("dispatch_check")
        sentinel_pos = content.find(self._SENTINEL)

        assert dc_pos != -1, "'dispatch_check' not found in orchestrator.md"
        assert sentinel_pos != -1, (
            f"Sentinel text {self._SENTINEL!r} not found in orchestrator.md — "
            "cannot verify ordering"
        )
        assert dc_pos < sentinel_pos, (
            f"'dispatch_check' appears at char {dc_pos} but sentinel "
            f"{repr(self._SENTINEL)} appears at char {sentinel_pos}. "
            "'dispatch_check' must come FIRST."
        )
