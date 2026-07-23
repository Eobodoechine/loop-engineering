"""Tests for loop-guards/install.py --check and loop-guards/detect_install_state.py
-- Deliverable B of spec-codex-parity-and-consent-installer-2026-07-09.md.

Written BEFORE any implementation exists (Test-writer, Tier 1). Every test
here MUST currently fail (FileNotFoundError from subprocess.run -- neither
install.py nor detect_install_state.py exist on disk yet) -- correct and
expected at this stage.

Covers:
  AC-9  (per-tool INSTALLED/NOT_INSTALLED/PARTIAL detection, install.py --check,
         no side effects)
  AC-14 (tool-scoped detect_install_state.py --tool <tool>, never an
         aggregate/combined boolean -- the specific plan-check finding that
         an aggregate check could mask a genuinely-absent tool's guards)

Design note (judgment call, flagged in the test-writer's final report): the
spec does not pin an exact machine-readable output FORMAT for either CLI
(JSON vs. plain text) -- only that each of the two tools' state is reported
per-tool. These tests therefore assert on (tool_name, STATE_WORD) co-
occurring in the combined stdout/stderr text via regex, which is compatible
with either a JSON or human-readable text implementation, rather than
pinning one. They deliberately do NOT hardcode a guessed "canonical hook
command path" string (also unpinned by the spec -- AC-9 says only that
install.py compares against "the expected canonical paths", an installer-
internal detail) -- instead, the INSTALLED/PARTIAL fixtures are built via a
real install.py --install round-trip (self-referential: the installer's own
real output is used as ground truth for what "canonical" means), then
mutated to prove the tri-state boundary. This keeps these tests testing the
PUBLIC contract (three-way per-tool state discrimination), not a private
implementation constant.
"""
import copy
import json
import os
import re
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
import _install_test_helpers as helpers  # noqa: E402


def _require_cli():
    if not os.path.isfile(helpers.INSTALL_PY):
        pytest.fail("loop-guards/install.py does not exist yet (expected "
                     "pre-build).")
    if not os.path.isfile(helpers.DETECT_PY):
        pytest.fail("loop-guards/detect_install_state.py does not exist yet "
                     "(expected pre-build).")


def _state_for_tool(text, tool):
    """Best-effort extraction: find a STATE word co-occurring with `tool`
    within a short window of text (tolerant of either JSON or plain-text
    output). Returns the state word or None."""
    m = re.search(
        re.escape(tool) + r'.{0,80}?\b(INSTALLED|NOT_INSTALLED|PARTIAL)\b',
        text, re.S)
    if m:
        return m.group(1)
    # try the other order (state word before tool name)
    m = re.search(
        r'\b(INSTALLED|NOT_INSTALLED|PARTIAL)\b.{0,80}?' + re.escape(tool),
        text, re.S)
    return m.group(1) if m else None


# ===========================================================================
# AC-9 -- install.py --check, per-tool, no side effects -- [BEHAVIORAL]
# ===========================================================================

class TestAC9PerToolInstallState:
    def test_not_installed_when_no_config_files_exist_at_all(self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)  # no settings.json/hooks.json at all
        code, out, err = helpers.run_check(home)
        text = out + err
        assert _state_for_tool(text, "claude_code") == "NOT_INSTALLED", text
        assert _state_for_tool(text, "codex") == "NOT_INSTALLED", text

    def test_not_installed_when_settings_exist_but_carry_zero_loop_guards_hooks(
            self, tmp_path):
        """A settings.json that exists and has hooks -- just none of THIS
        framework's -- must report NOT_INSTALLED, not PARTIAL/INSTALLED
        (0 of 5 registered)."""
        _require_cli()
        home = helpers.make_home(
            tmp_path, claude_settings=helpers.UNRELATED_CLAUDE_SETTINGS,
            codex_hooks=helpers.UNRELATED_CODEX_HOOKS)
        code, out, err = helpers.run_check(home)
        text = out + err
        assert _state_for_tool(text, "claude_code") == "NOT_INSTALLED", text
        assert _state_for_tool(text, "codex") == "NOT_INSTALLED", text

    def test_check_has_zero_side_effects(self, tmp_path):
        """AC-9: 'install.py --check (no side effects)'. Even against a
        state that WOULD need writing if this were --install, --check must
        never touch the file."""
        _require_cli()
        home = helpers.make_home(
            tmp_path, claude_settings=helpers.UNRELATED_CLAUDE_SETTINGS)
        settings_path = os.path.join(home, ".claude", "settings.json")
        before_bytes = open(settings_path, "rb").read()
        before_mtime = os.path.getmtime(settings_path)
        helpers.run_check(home)
        after_bytes = open(settings_path, "rb").read()
        assert after_bytes == before_bytes
        assert os.path.getmtime(settings_path) == before_mtime

    def test_installed_after_real_install_round_trip(self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, install_out = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0, install_out
        code, out, err = helpers.run_check(home)
        text = out + err
        assert _state_for_tool(text, "claude_code") == "INSTALLED", text

    def test_partial_when_one_of_five_hook_events_missing(self, tmp_path):
        """PARTIAL = 'some but not all of the 5 hook events registered'
        (AC-9's own parenthetical). Installs cleanly, then deletes exactly
        ONE of the 5 registered hook-event entries and re-checks."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, install_out = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0, install_out
        data = helpers.read_claude_settings(home)
        present_events = [e for e in helpers.HOOK_EVENTS
                           if helpers.hook_commands(data, e)]
        assert len(present_events) == 5, (
            "a clean install must register all 5 hook events; found only "
            "%r -- cannot exercise the PARTIAL boundary without a genuine "
            "5-of-5 starting point" % (present_events,))
        del data["hooks"][present_events[0]]
        settings_path = os.path.join(home, ".claude", "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        code, out, err = helpers.run_check(home)
        text = out + err
        assert _state_for_tool(text, "claude_code") == "PARTIAL", (
            "removed hook event %r post-install; --check text: %r"
            % (present_events[0], text))

    def test_partial_when_one_hook_command_path_is_wrong_but_all_five_events_present(
            self, tmp_path):
        """A stricter PARTIAL trigger: all 5 EVENT KEYS still present, but
        ONE event's registered `command` string has been altered to point
        somewhere else entirely. Forces the implementation to compare the
        actual command STRING per event against the expected canonical
        path, not merely check for key presence."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, install_out = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0, install_out
        data = helpers.read_claude_settings(home)
        target_event = helpers.HOOK_EVENTS[0]
        data["hooks"][target_event][0]["hooks"][0]["command"] = (
            "python3 '/completely/wrong/path/not_the_real_hook.py'")
        settings_path = os.path.join(home, ".claude", "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        code, out, err = helpers.run_check(home)
        text = out + err
        assert _state_for_tool(text, "claude_code") == "PARTIAL", text

    def test_claude_code_and_codex_states_are_independent(self, tmp_path):
        """Direct AC-9 + AC-14 cross-check: Claude Code fully installed,
        Codex completely untouched -- both must be reported per-tool,
        independently, in the SAME --check invocation."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, install_out = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0, install_out
        code, out, err = helpers.run_check(home)
        text = out + err
        assert _state_for_tool(text, "claude_code") == "INSTALLED", text
        assert _state_for_tool(text, "codex") == "NOT_INSTALLED", text


# ===========================================================================
# AC-14 -- detect_install_state.py --tool <tool>, tool-scoped, never
# aggregate -- [BEHAVIORAL] [SECURITY-ORACLE]
# (labeled SECURITY-ORACLE: this is the exact plan-check-flagged risk of an
# aggregate check silently masking one tool's genuinely-absent guards --
# a "one actor's [tool's] state must not be affected/hidden by the other's"
# isolation claim.)
# ===========================================================================

class TestAC14ToolScopedDetection:
    def test_tool_flag_reports_only_the_requested_tool_claude_code_installed(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, _ = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0
        code, out, err = helpers.run_detect(home, "claude_code")
        text = out + err
        assert re.search(r'\bINSTALLED\b', text) and not re.search(
            r'\bNOT_INSTALLED\b', text), (
            "detect_install_state.py --tool claude_code output: %r" % text)

    def test_tool_flag_does_not_mask_codex_absence_behind_claude_code_installed(
            self, tmp_path):
        """THE adversarial case AC-14 exists to prevent: Claude Code is
        fully installed, Codex is completely absent. Querying --tool codex
        specifically must report NOT_INSTALLED for Codex -- an aggregate
        (OR-across-tools) implementation would wrongly report INSTALLED
        here because Claude Code's half is installed."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, _ = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0
        code, out, err = helpers.run_detect(home, "codex")
        text = out + err
        assert re.search(r'\bNOT_INSTALLED\b', text), (
            "detect_install_state.py --tool codex wrongly failed to report "
            "NOT_INSTALLED while Claude Code alone is installed -- this is "
            "the aggregate-boolean-masking bug AC-14 explicitly names. "
            "Output: %r" % text)

    def test_tool_flag_does_not_mask_claude_code_absence_behind_codex_installed(
            self, tmp_path):
        """Symmetric direction of the same adversarial case."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, _ = helpers.run_install_with_consent(home, "codex", accept=True)
        assert status == 0
        code, out, err = helpers.run_detect(home, "claude_code")
        text = out + err
        assert re.search(r'\bNOT_INSTALLED\b', text), (
            "detect_install_state.py --tool claude_code wrongly failed to "
            "report NOT_INSTALLED while only Codex is installed. Output: %r"
            % text)

    def test_unknown_tool_value_is_rejected_not_silently_misparsed(self, tmp_path):
        """Defensive coverage: --tool is the entire trust boundary for
        AC-14's tool-scoping guarantee -- an unrecognized value must error
        loudly, never silently fall through to some default tool's state."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        code, out, err = helpers.run_detect(home, "not_a_real_tool_xyz")
        assert code != 0, (out, err)
