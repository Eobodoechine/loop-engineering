"""Tests for loop-guards/install.py's write path (merge/no-op/abort/
uninstall safety) -- Deliverable B of
spec-codex-parity-and-consent-installer-2026-07-09.md.

Written BEFORE any implementation exists. Every test here MUST currently
fail (FileNotFoundError -- install.py does not exist on disk yet) -- correct
and expected at this stage.

Covers:
  AC-10 (silent no-op on repeat installs, no consent prompt needed for the
         no-op path)
  AC-12 (JSON-merge preserving pre-existing unrelated hooks/config, never a
         blind overwrite; diff preview shown before any write; malformed
         pre-existing JSON aborts loudly with ZERO writes attempted)
  AC-13 (Codex-specific: install.py never touches ~/.codex/config.toml's
         [hooks.state]/trusted_hash; post-install message tells the human
         to approve via /hooks)
  AC-15 (diff-preview mandatory; documented+tested uninstall path ships in
         the same build, preserving unrelated hooks)
"""
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


# ===========================================================================
# AC-10 -- silent no-op on repeat installs -- [BEHAVIORAL]
# ===========================================================================

class TestAC10SilentNoOpOnRepeat:
    def test_second_install_prints_already_installed_and_writes_nothing(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        status1, out1 = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status1 == 0, out1
        before = helpers.read_claude_settings(home)
        status2, out2 = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status2 == 0, out2
        assert re.search(r'already installed', out2, re.I), out2
        after = helpers.read_claude_settings(home)
        assert after == before

    def test_second_install_needs_no_tty_at_all_because_it_short_circuits_first(
            self, tmp_path):
        """AC-10's no-op must trigger BEFORE the consent prompt would ever
        be reached (a repeat run on a script's own already-provisioned
        machine should never hang/fail on a missing tty) -- distinct from a
        genuinely fresh install, which AC-15(c) requires to fail closed
        with no tty. Proves the ordering: check-installed-state happens
        first, prompt only if not already installed."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status1, out1 = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status1 == 0, out1
        before = helpers.read_claude_settings(home)
        code, text = helpers.run_no_tty_at_all(
            ["--install", "--tool", "claude_code"], home)
        assert code == 0, (
            "a repeat install (already INSTALLED) must succeed as a silent "
            "no-op even with zero controlling terminal available -- it "
            "must never reach the consent prompt at all on this path. "
            "output=%r" % text)
        assert re.search(r'already installed', text, re.I), text
        after = helpers.read_claude_settings(home)
        assert after == before


# ===========================================================================
# AC-12 -- JSON-merge, diff preview, malformed-JSON abort -- [BEHAVIORAL]
# ===========================================================================

class TestAC12MergeNeverBlindOverwrite:
    def test_preserves_pre_existing_unrelated_hook_and_top_level_key(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(
            tmp_path, claude_settings=helpers.UNRELATED_CLAUDE_SETTINGS)
        status, out = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0, out
        data = helpers.read_claude_settings(home)
        assert data.get("someOtherTopLevelKey") == "must-survive-the-merge", data
        pretooluse = helpers.hook_commands(data, "PreToolUse")
        assert any("unrelated_hook.py" in c for c in pretooluse), (
            "pre-existing unrelated PreToolUse hook was dropped by the "
            "merge -- AC-12 requires 'preserving any pre-existing "
            "unrelated hooks/config in that file'. Registered PreToolUse "
            "commands after install: %r" % pretooluse)

    def test_new_stop_hook_is_actually_added_alongside_unrelated_content(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(
            tmp_path, claude_settings=helpers.UNRELATED_CLAUDE_SETTINGS)
        status, out = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0, out
        data = helpers.read_claude_settings(home)
        stop_cmds = helpers.hook_commands(data, "Stop")
        assert any("loop_stop_guard.py" in c for c in stop_cmds), (
            "Stop hook was never actually registered by --install. "
            "Registered Stop commands: %r" % stop_cmds)

    def test_diff_preview_shown_even_when_consent_is_declined(self, tmp_path):
        """AC-12: 'prints a diff of exactly what changed before writing
        it.' If the diff is shown BEFORE the accept/reject decision, it
        must still appear in the output even on a DECLINED run (the human
        needs to see it in order to decide) -- combined with the following
        test (zero writes on decline), this pins down the required
        ordering (diff, then prompt, then write-iff-accepted) without
        needing to instrument the process's internal timing."""
        _require_cli()
        home = helpers.make_home(
            tmp_path, claude_settings=helpers.UNRELATED_CLAUDE_SETTINGS)
        before = helpers.read_claude_settings(home)
        status, out = helpers.run_install_with_consent(
            home, "claude_code", accept=False)
        assert re.search(r'loop_stop_guard|Stop', out), (
            "no diff/preview of the pending change was shown before the "
            "consent prompt -- output=%r" % out)
        after = helpers.read_claude_settings(home)
        assert after == before, (
            "file was modified despite consent being DECLINED -- zero "
            "writes are permitted on decline.")

    def test_malformed_pre_existing_claude_settings_aborts_with_zero_writes(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        settings_path = os.path.join(home, ".claude", "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write("{ this is not : valid json, at all ][")
        before_bytes = open(settings_path, "rb").read()
        before_mtime = os.path.getmtime(settings_path)
        status, out = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status not in (0, None), (
            "install.py must abort with a non-zero exit on unparseable "
            "pre-existing settings.json -- got status=%r out=%r"
            % (status, out))
        assert "settings.json" in out, out
        assert re.search(r'json|pars', out, re.I), out
        after_bytes = open(settings_path, "rb").read()
        assert after_bytes == before_bytes, (
            "malformed settings.json was modified/overwritten -- AC-12 "
            "requires ZERO writes attempted on an unparseable pre-existing "
            "file.")
        assert os.path.getmtime(settings_path) == before_mtime

    def test_malformed_pre_existing_codex_hooks_json_aborts_with_zero_writes(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        hooks_path = os.path.join(home, ".codex", "hooks.json")
        with open(hooks_path, "w", encoding="utf-8") as f:
            f.write("not json at all {{{")
        before_bytes = open(hooks_path, "rb").read()
        status, out = helpers.run_install_with_consent(
            home, "codex", accept=True)
        assert status not in (0, None), (status, out)
        assert "hooks.json" in out, out
        after_bytes = open(hooks_path, "rb").read()
        assert after_bytes == before_bytes


# ===========================================================================
# AC-13 -- Codex: never touch config.toml's [hooks.state]; post-install
# message points at /hooks -- [BEHAVIORAL] + [DOC]
# ===========================================================================

class TestAC13CodexNeverFabricatesTrustedHash:
    def test_config_toml_hooks_state_untouched_by_install(self, tmp_path):
        _require_cli()
        home = helpers.make_home(
            tmp_path, codex_hooks=helpers.UNRELATED_CODEX_HOOKS,
            codex_config_toml=helpers.UNRELATED_CODEX_CONFIG_TOML)
        toml_path = os.path.join(home, ".codex", "config.toml")
        before = open(toml_path, "rb").read()
        status, out = helpers.run_install_with_consent(
            home, "codex", accept=True)
        assert status == 0, out
        after = open(toml_path, "rb").read()
        assert after == before, (
            "install.py wrote to config.toml -- AC-13 requires it write "
            "ONLY ~/.codex/hooks.json, never fabricate/pre-approve a "
            "trusted_hash entry in config.toml's [hooks.state].")

    def test_config_toml_not_even_created_when_absent(self, tmp_path):
        """If config.toml doesn't exist at all before install, it must
        still not exist after -- install.py has no legitimate reason to
        create it."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        toml_path = os.path.join(home, ".codex", "config.toml")
        assert not os.path.isfile(toml_path)
        status, out = helpers.run_install_with_consent(
            home, "codex", accept=True)
        assert status == 0, out
        assert not os.path.isfile(toml_path), (
            "install.py created ~/.codex/config.toml where none existed "
            "before -- it must only ever write ~/.codex/hooks.json.")

    def test_post_install_message_tells_human_to_approve_via_hooks_command(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, out = helpers.run_install_with_consent(
            home, "codex", accept=True)
        assert status == 0, out
        assert "/hooks" in out, (
            "post-install message for Codex must explicitly tell the "
            "human to open Codex and approve the new/changed hooks via "
            "/hooks -- H-CODEX-PARITY-2026-07-08. output=%r" % out)
        assert re.search(r'approve', out, re.I), out


# ===========================================================================
# AC-15 -- documented + tested uninstall path -- [BEHAVIORAL]
# ===========================================================================

class TestAC15UninstallPath:
    def test_uninstall_removes_loop_guards_hooks_preserving_unrelated(
            self, tmp_path):
        _require_cli()
        home = helpers.make_home(
            tmp_path, claude_settings=helpers.UNRELATED_CLAUDE_SETTINGS)
        status1, out1 = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status1 == 0, out1
        status2, out2 = helpers.run_uninstall_with_consent(
            home, "claude_code", accept=True)
        assert status2 == 0, out2
        data = helpers.read_claude_settings(home)
        assert data.get("someOtherTopLevelKey") == "must-survive-the-merge", data
        pretooluse = helpers.hook_commands(data, "PreToolUse")
        assert any("unrelated_hook.py" in c for c in pretooluse), (
            "uninstall dropped a pre-existing unrelated hook -- must only "
            "remove THIS framework's own entries. PreToolUse commands "
            "after uninstall: %r" % pretooluse)
        stop_cmds = helpers.hook_commands(data, "Stop")
        assert not any("loop_stop_guard.py" in c for c in stop_cmds), (
            "loop-guards' own Stop hook is still registered after "
            "uninstall: %r" % stop_cmds)

    def test_check_reports_not_installed_again_after_uninstall(self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        status1, out1 = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status1 == 0, out1
        status2, out2 = helpers.run_uninstall_with_consent(
            home, "claude_code", accept=True)
        assert status2 == 0, out2
        code, out3, err3 = helpers.run_check(home)
        text = out3 + err3
        assert re.search(r'claude_code.{0,80}?NOT_INSTALLED', text, re.S) or (
            "NOT_INSTALLED" in text and "INSTALLED" not in text.replace(
                "NOT_INSTALLED", "")), text

    def test_uninstall_declined_leaves_everything_installed(self, tmp_path):
        _require_cli()
        home = helpers.make_home(tmp_path)
        status1, out1 = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status1 == 0, out1
        before = helpers.read_claude_settings(home)
        status2, out2 = helpers.run_uninstall_with_consent(
            home, "claude_code", accept=False)
        after = helpers.read_claude_settings(home)
        assert after == before, (
            "uninstall proceeded despite consent being declined. out=%r"
            % out2)
