"""_tty_harness.py -- shared, non-production test-support helper for
AC-11's adversarial consent-flow tests (spec-codex-parity-and-consent-
installer-2026-07-09.md).

Gives a subprocess a REAL controlling terminal (so `open("/dev/tty", ...)`
genuinely succeeds, exactly like a real interactive session) via a pty,
while SEPARATELY controlling the subprocess's plain stdin (fd 0) via an
ordinary pipe -- this reproduces the exact adversarial shape AC-11 names
("a piped `echo yes | script` with a redirected stdin but a real tty
available elsewhere"): fd 0 is a redirected pipe (non-tty), while the
process's controlling terminal (what `/dev/tty` resolves to) is a real,
independently-scriptable pty.

This lets a test assert, with full determinism (no reliance on timing-
sensitive OS-level pty-relay behavior): the installer's actual accept/
reject decision must track whatever was typed at the REAL controlling
terminal, and must completely IGNORE whatever arrives on plain stdin --
proving it reads consent via `/dev/tty` specifically, not `sys.stdin`
(even when `sys.stdin` is deliberately fed the literal string "yes").

Bounded by an internal SIGALRM-based timeout with a forced SIGKILL + reap
in every code path (never leaves a zombie / hung child behind, per this
framework's own standing "process-leak lessons" -- never let a spawned
process hang a test run).

Not a test_*.py file itself, so pytest does not try to collect it.
"""
import os
import pty
import signal
import sys


class _Timeout(Exception):
    pass


def run_with_real_tty_and_separate_stdin(
        argv, tty_input=b"", stdin_input=b"", env=None, timeout=8):
    """Spawns `argv` (a full command list, e.g. [sys.executable,
    install_py_path, "--install", "--tool", "claude_code"]) with:
      - a REAL pty as its controlling terminal, fed `tty_input` (simulates
        an actual human typing at the real terminal);
      - a SEPARATE plain os.pipe() as fd 0, fed `stdin_input` (simulates
        `echo <stdin_input> | ...` -- redirected, non-tty).
    stdout+stderr are merged (both dup2'd to the pty slave, so ordinary
    program output round-trips through the master read below; a pty always
    reports isatty()==True for fd 1/2 too, which is realistic and does not
    affect what this harness is testing -- consent-reading via /dev/tty).

    Returns (exit_status_or_none, combined_output_bytes). exit_status is
    None if the child had to be force-killed after `timeout` seconds
    (e.g. it hung reading /dev/tty because tty_input was empty/no
    affirmative answer was ever provided) -- callers should treat that as
    "did not proceed" and additionally assert on real, independently-
    observable side effects (file contents unchanged), not on exit code
    alone, in that scenario.
    """
    stdin_r, stdin_w = os.pipe()
    pid, master_fd = pty.fork()
    if pid == 0:
        # Child: pty.fork() already made the pty our controlling terminal
        # and wired it to fd 0/1/2. Override JUST fd 0 with the separate
        # plain pipe -- the controlling terminal (and therefore /dev/tty)
        # stays the pty, untouched.
        os.dup2(stdin_r, 0)
        os.close(stdin_r)
        os.close(stdin_w)
        if env is not None:
            os.execvpe(argv[0], argv, env)
        else:
            os.execvp(argv[0], argv)
        os._exit(127)  # only reached if exec itself fails

    # Parent
    os.close(stdin_r)
    if tty_input:
        os.write(master_fd, tty_input)
    if stdin_input:
        os.write(stdin_w, stdin_input)
    os.close(stdin_w)

    def _handler(signum, frame):
        raise _Timeout()

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout)
    out = b""
    timed_out = False
    try:
        while True:
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    except _Timeout:
        timed_out = True
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

    status = None
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        _wpid, raw_status = os.waitpid(pid, 0)
        if not timed_out and os.WIFEXITED(raw_status):
            status = os.WEXITSTATUS(raw_status)
    except ChildProcessError:
        pass
    try:
        os.close(master_fd)
    except OSError:
        pass
    return status, out


def real_tty_available():
    """True iff THIS process (not a spawned pty child) has a real,
    open-able controlling terminal. Used to skip a redundant assertion
    path when the ambient test environment already has none (in which
    case the plain no-tty-at-all test in test_install_consent.py already
    covers the fail-closed contract without needing a pty at all)."""
    try:
        fd = os.open("/dev/tty", os.O_RDONLY | os.O_NONBLOCK)
        os.close(fd)
        return True
    except OSError:
        return False
