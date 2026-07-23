"""Tests for loop-guards/install.py's consent gate -- Deliverable B of
spec-codex-parity-and-consent-installer-2026-07-09.md.

Written BEFORE any implementation exists. Every test here MUST currently
fail (FileNotFoundError -- install.py does not exist on disk yet) -- correct
and expected at this stage.

Covers:
  AC-11 (the adversarial /dev/tty-vs-stdin collision test, explicitly
         required by the spec's own wording: "write an adversarial test
         proving a piped `echo yes | script` with a redirected stdin but a
         real tty available elsewhere does NOT satisfy consent unless read
         via /dev/tty")
  AC-15(c) (installer refuses to run at all in a non-interactive/CI context
         -- no TTY -- regardless of flags)

Uses `_tty_harness.py` (pre-built test-support module, gives a subprocess a
REAL pty as its controlling terminal while separately controlling plain
stdin via an ordinary pipe) to reproduce the exact adversarial shape without
relying on OS-level timing.
"""
import os
import re
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
import _install_test_helpers as helpers  # noqa: E402
import _tty_harness as tty_harness  # noqa: E402


def _require_cli():
    if not os.path.isfile(helpers.INSTALL_PY):
        pytest.fail("loop-guards/install.py does not exist yet (expected "
                     "pre-build).")


# ===========================================================================
# AC-11 -- the /dev/tty-vs-stdin adversarial pair -- [BEHAVIORAL]
# [SECURITY-ORACLE] (a consent-gate bypass is a real "unauthorized actor
# proceeds without genuine consent" isolation failure)
# ===========================================================================

class TestAC11DevTtyVsStdinAdversarialPair:
    def test_piped_stdin_saying_yes_does_not_satisfy_consent_when_real_tty_says_no(
            self, tmp_path):
        """The exact scenario AC-11 names: 'a piped `echo yes | script`
        with a redirected stdin but a real tty available elsewhere.' Plain
        stdin (a redirected pipe) is fed "yes", but the REAL controlling
        terminal answers "no". A compliant implementation reads consent
        from /dev/tty, so this must NOT install."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        argv = [sys.executable, helpers.INSTALL_PY, "--install",
                "--tool", "claude_code"]
        status, out = tty_harness.run_with_real_tty_and_separate_stdin(
            argv, tty_input=b"no\n", stdin_input=b"yes\n",
            env=helpers.env_for(home), timeout=10)
        after = helpers.read_claude_settings(home)
        assert after is None or not helpers.hook_commands(after, "Stop"), (
            "install proceeded despite the REAL controlling terminal "
            "answering 'no' -- a naive `sys.stdin.isatty()`/plain-stdin-"
            "read implementation is satisfiable by a piped 'yes' even "
            "though no genuine human consented. status=%r out=%r"
            % (status, out))

    def test_real_tty_saying_yes_is_honored_even_when_piped_stdin_says_no(
            self, tmp_path):
        """The symmetric direction -- proves the implementation genuinely
        READS AND ACTS ON /dev/tty (not merely 'ignores everything and
        always refuses', which would vacuously pass the test above for the
        wrong reason). The real terminal says yes; the irrelevant piped
        stdin says no. Consent must be honored."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        argv = [sys.executable, helpers.INSTALL_PY, "--install",
                "--tool", "claude_code"]
        status, out = tty_harness.run_with_real_tty_and_separate_stdin(
            argv, tty_input=b"yes\n", stdin_input=b"no\n",
            env=helpers.env_for(home), timeout=10)
        after = helpers.read_claude_settings(home)
        assert after is not None and helpers.hook_commands(after, "Stop"), (
            "install did NOT proceed even though the REAL controlling "
            "terminal answered 'yes' -- if this test and the one above "
            "BOTH show 'did not install', the implementation is not "
            "reading /dev/tty at all (e.g. it always refuses regardless of "
            "input), which is a different bug than the stdin-bypass this "
            "test pair targets. status=%r out=%r" % (status, out))

    def test_plain_decline_at_real_tty_leaves_file_untouched(self, tmp_path):
        """Baseline (non-adversarial) sanity check: a real 'no' answered at
        the real terminal, no stdin trickery at all, must not install."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, out = helpers.run_install_with_consent(
            home, "claude_code", accept=False)
        after = helpers.read_claude_settings(home)
        assert after is None or not helpers.hook_commands(after, "Stop"), out


# ===========================================================================
# AC-15(c) -- refuses in a genuinely non-interactive/CI context (no TTY at
# all), regardless of flags -- [BEHAVIORAL]
# ===========================================================================

class TestAC15NoTtyContextRefusesRegardlessOfFlags:
    def test_no_controlling_terminal_at_all_fails_closed_zero_writes(
            self, tmp_path):
        """A genuinely absent controlling terminal (start_new_session=True
        detaches the child from any tty -- confirmed live in this sandbox
        to raise OSError/ENXIO on open("/dev/tty"), the real CI shape, not
        merely 'stdin is a pipe'). Must abort: non-zero exit, zero writes."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        code, text = helpers.run_no_tty_at_all(
            ["--install", "--tool", "claude_code"], home,
            stdin_bytes=b"yes\n")
        assert code != 0, text
        after = helpers.read_claude_settings(home)
        assert after is None or not helpers.hook_commands(after, "Stop"), (
            "install proceeded with NO controlling terminal available at "
            "all -- must fail closed unconditionally. output=%r" % text)

    def test_no_tty_refuses_even_with_a_yes_style_flag(self, tmp_path):
        """AC-15(c): 'refuses to run at all in a non-interactive/CI context
        (no TTY) regardless of flags.' Even a `--yes` flag (permitted ONLY
        for a human's own scripted re-install per AC-11) must not override
        a genuinely-absent controlling terminal. Judgment call: the spec
        does not mandate a `--yes` flag exist at all -- if the Coder chose
        not to implement one, argparse rejecting it as an unrecognized
        argument is an equally acceptable 'did not install' outcome, so
        this test only asserts the SAFE result (nonzero exit, zero
        writes), not a specific error message about the flag itself."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        code, text = helpers.run_no_tty_at_all(
            ["--install", "--tool", "claude_code", "--yes"], home)
        assert code != 0, text
        after = helpers.read_claude_settings(home)
        assert after is None or not helpers.hook_commands(after, "Stop"), (
            "install proceeded with --yes and NO controlling terminal -- "
            "AC-15(c) requires refusal 'regardless of flags'. output=%r"
            % text)

    def test_no_tty_context_also_refuses_uninstall(self, tmp_path):
        """AC-15(c)'s 'regardless of flags' / non-interactive refusal is
        not scoped to --install alone -- an uninstall is also a state-
        changing operation that needs genuine human sign-off (AC-15's own
        'explicit human sign-off gate' framing covers the whole installer,
        not just first-time install)."""
        _require_cli()
        home = helpers.make_home(tmp_path)
        status, _ = helpers.run_install_with_consent(
            home, "claude_code", accept=True)
        assert status == 0
        before = helpers.read_claude_settings(home)
        code, text = helpers.run_no_tty_at_all(
            ["--uninstall", "--tool", "claude_code"], home,
            stdin_bytes=b"yes\n")
        assert code != 0, text
        after = helpers.read_claude_settings(home)
        assert after == before, (
            "uninstall proceeded with no controlling terminal available. "
            "output=%r" % text)
