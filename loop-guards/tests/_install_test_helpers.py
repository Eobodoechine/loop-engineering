"""_install_test_helpers.py -- shared, non-production test-support helpers
for Deliverable B (consent-gated installer), spec-codex-parity-and-consent-
installer-2026-07-09.md.

Contains ONLY fixture construction + subprocess-driving helpers -- zero
installer/detection logic. Deliberately named without a `test_` prefix so
pytest does not try to collect it as its own test module (mirrors
hooks/_codex_fixture_builders.py's own convention in this repo).

Every test in this directory runs `install.py`/`detect_install_state.py`
against a FAKE `$HOME` (a fresh tmp_path per test, containing its own
`.claude/` and `.codex/` subdirectories) -- NEVER the real, machine-global
`~/.claude/settings.json` / `~/.codex/hooks.json` / `~/.codex/config.toml`
this very session's own hooks are wired through. `os.path.expanduser("~")`
and `os.environ["HOME"]` are the same thing on macOS/Linux, so overriding
the `HOME` env var for the subprocess is sufficient and requires no special
override flag on the installer's own CLI.

Consent simulation: AC-11 explicitly forbids any flag/env-var bypass of the
human-facing prompt for a first-time install ("no flag or env var bypasses
the human-facing prompt ... never for a first-time install on a stranger's
machine"). The only LEGITIMATE way for an automated test to simulate a
human's accept/reject is to answer through a REAL controlling terminal via
`_tty_harness.py` (a real pty, separate from the process's plain stdin) --
this exercises the actual `/dev/tty`-reading code path AC-11 requires,
rather than bypassing it. Every helper below that needs to get past the
consent gate uses `_tty_harness.run_with_real_tty_and_separate_stdin`.
"""
import json
import os
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
LOOP_GUARDS_DIR = os.path.dirname(TESTS_DIR)
LOOP_ROOT = os.path.dirname(LOOP_GUARDS_DIR)

INSTALL_PY = os.path.join(LOOP_GUARDS_DIR, "install.py")
DETECT_PY = os.path.join(LOOP_GUARDS_DIR, "detect_install_state.py")

# The 5 real hook events this framework registers today, confirmed via
# direct read of ~/.claude/settings.json and ~/.codex/hooks.json on this
# machine (2026-07-09): UserPromptSubmit -> loop_guard.py, Stop ->
# loop_stop_guard.py (which itself imports/invokes micro_step_gates.py --
# NOT a separately-registered hook event), SessionStart -> session_start.sh,
# SubagentStop -> subagent_stop_gate.py, PreToolUse -> pre_tool_use_oga_guard.py.
HOOK_EVENTS = ("Stop", "SubagentStop", "PreToolUse", "SessionStart",
               "UserPromptSubmit")

sys.path.insert(0, TESTS_DIR)
import _tty_harness as tty_harness  # noqa: E402


def make_home(tmp_path, claude_settings=None, codex_hooks=None,
              codex_config_toml=None):
    """Builds a fake $HOME with `.claude/` and `.codex/` subdirectories
    (matching real layout), optionally pre-seeding settings.json /
    hooks.json / config.toml content. Returns the home path (str). Omitting
    a `*_settings`/`*_hooks` kwarg leaves that file simply ABSENT (the real
    'never installed, never even touched this tool' starting state)."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir(parents=True)
    if claude_settings is not None:
        (home / ".claude" / "settings.json").write_text(
            json.dumps(claude_settings, indent=2))
    if codex_hooks is not None:
        (home / ".codex" / "hooks.json").write_text(
            json.dumps(codex_hooks, indent=2))
    if codex_config_toml is not None:
        (home / ".codex" / "config.toml").write_text(codex_config_toml)
    return str(home)


def env_for(home):
    env = dict(os.environ)
    env["HOME"] = home
    return env


def run_check(home, extra_args=()):
    """`install.py --check [extra_args]` -- must be READ-ONLY (AC-9: 'no
    side effects'). No consent needed; plain subprocess is fine."""
    p = subprocess.run(
        [sys.executable, INSTALL_PY, "--check", *extra_args],
        capture_output=True, text=True, env=env_for(home), timeout=15)
    return p.returncode, p.stdout, p.stderr


def run_detect(home, tool, extra_args=()):
    """`detect_install_state.py --tool <tool> [extra_args]` -- read-only,
    tool-SCOPED (AC-14: 'an explicit, tool-scoped flag, never an
    aggregate/combined boolean')."""
    p = subprocess.run(
        [sys.executable, DETECT_PY, "--tool", tool, *extra_args],
        capture_output=True, text=True, env=env_for(home), timeout=15)
    return p.returncode, p.stdout, p.stderr


def run_install_with_consent(home, tool, accept=True, extra_args=(),
                              timeout=10):
    """Drives `install.py --install --tool <tool> [extra_args]` through a
    REAL pty controlling terminal answering yes/no -- the legitimate,
    non-bypassing way to simulate human consent (see module docstring).
    Returns (exit_status_or_None, combined_stdout_stderr_text). exit_status
    is None if the child had to be force-killed after `timeout` (e.g. it
    hung waiting for a /dev/tty answer that never satisfied it)."""
    answer = b"yes\n" if accept else b"no\n"
    argv = [sys.executable, INSTALL_PY, "--install", "--tool", tool,
            *extra_args]
    status, out = tty_harness.run_with_real_tty_and_separate_stdin(
        argv, tty_input=answer, env=env_for(home), timeout=timeout)
    return status, out.decode("utf-8", errors="replace")


def run_uninstall_with_consent(home, tool, accept=True, extra_args=(),
                                timeout=10):
    answer = b"yes\n" if accept else b"no\n"
    argv = [sys.executable, INSTALL_PY, "--uninstall", "--tool", tool,
            *extra_args]
    status, out = tty_harness.run_with_real_tty_and_separate_stdin(
        argv, tty_input=answer, env=env_for(home), timeout=timeout)
    return status, out.decode("utf-8", errors="replace")


def run_no_tty_at_all(argv_tail, home, stdin_bytes=b"", timeout=10):
    """Runs `[sys.executable, INSTALL_PY] + argv_tail` with a genuinely
    ABSENT controlling terminal -- `start_new_session=True` detaches the
    child from any controlling tty entirely (confirmed live in this sandbox:
    a child so spawned gets OSError/ENXIO 'Device not configured' on
    `open("/dev/tty")`, not merely a non-tty stdin), simulating a real
    CI/non-interactive context per AC-15(c). `stdin` is a plain pipe fed
    `stdin_bytes` (default empty) -- simulates `echo ... | install.py` or a
    bare CI invocation with no input at all."""
    argv = [sys.executable, INSTALL_PY] + list(argv_tail)
    p = subprocess.run(
        argv, input=stdin_bytes, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=env_for(home),
        start_new_session=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", errors="replace")


def read_claude_settings(home):
    p = os.path.join(home, ".claude", "settings.json")
    if not os.path.isfile(p):
        return None
    return json.loads(open(p, encoding="utf-8").read())


def read_codex_hooks(home):
    p = os.path.join(home, ".codex", "hooks.json")
    if not os.path.isfile(p):
        return None
    return json.loads(open(p, encoding="utf-8").read())


def hook_commands(config, event):
    """Flattens every `command` string registered for `event` (Claude-Code-
    /Codex-shaped hooks.json both use the same `{event: [{hooks: [{command,
    ...}]}]}` nesting, confirmed via direct read of both real files on this
    machine)."""
    out = []
    for block in (config or {}).get("hooks", {}).get(event, []):
        for h in block.get("hooks", []):
            cmd = h.get("command")
            if cmd:
                out.append(cmd)
    return out


# A settings.json carrying a genuine, pre-existing, UNRELATED hook plus an
# unrelated top-level key -- simulates "a real user's own machine that
# already has other stuff configured" (AC-12: 'preserving any pre-existing
# unrelated hooks/config in that file -- never a blind overwrite').
UNRELATED_CLAUDE_SETTINGS = {
    "permissions": {"allow": ["Bash(ls)"]},
    "hooks": {
        "PreToolUse": [
            {"hooks": [{"type": "command",
                        "command": "python3 '/opt/some/other/tool/unrelated_hook.py'"}]}
        ]
    },
    "someOtherTopLevelKey": "must-survive-the-merge",
}

UNRELATED_CODEX_HOOKS = {
    "hooks": {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command",
                        "command": "/opt/some/other/codex-hook.sh",
                        "timeout": 5}]}
        ]
    }
}

# A real-shaped [hooks.state] block (mirrors the actual, live
# ~/.codex/config.toml on this machine, H-CODEX-PARITY-2026-07-08) --
# AC-13 requires install.py never touch this file at all.
UNRELATED_CODEX_CONFIG_TOML = (
    '[hooks.state]\n\n'
    '[hooks.state."/opt/some/other/codex-hook.sh:user_prompt_submit:0:0"]\n'
    'trusted_hash = "sha256:preexistingdeadbeef0000000000000000000000000000000000000000"\n'
    'enabled = true\n'
)
