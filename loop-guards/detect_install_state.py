#!/usr/bin/env python3
"""detect_install_state.py -- "already installed?" check for the loop-team
enforcement hooks (loop_stop_guard.py's RUNLOG_MISSING gate,
micro_step_gates.py's thrash-past-green/step-size gates, and their sibling
guards), Deliverable B of
research/spec-codex-parity-and-consent-installer-2026-07-09.md.

Importable (the canonical hook registry + detection logic other code in
this package, e.g. install.py, imports directly) AND a standalone CLI:

    python3 loop-guards/detect_install_state.py --tool claude_code
    python3 loop-guards/detect_install_state.py --tool codex

AC-14 (tool-scoped, never an aggregate/combined boolean): `--tool` is
REQUIRED and reports ONLY the state of the ONE tool asked about -- the
other tool's config is never even read, so a caller can never mistake one
tool's INSTALLED state for the other's (the exact aggregate-boolean-masking
risk plan-check flagged).

Per-tool state is one of INSTALLED / NOT_INSTALLED / PARTIAL (AC-9): PARTIAL
means some, but not all, of the 5 real hook events this framework registers
today are present with their expected canonical `command` string.
"""
import argparse
import json
import os
import sys

LOOP_GUARDS_DIR = os.path.dirname(os.path.abspath(__file__))
LOOP_ROOT = os.path.dirname(LOOP_GUARDS_DIR)

# The 5 real hook events this framework registers today (confirmed via
# direct read of ~/.claude/settings.json and ~/.codex/hooks.json on this
# machine, 2026-07-09 -- see loop-guards/tests/_install_test_helpers.py's
# own HOOK_EVENTS tuple, independently confirmed against the same two real
# files). Each entry: (event_name, runner, script_basename, matcher).
# `matcher` is only meaningful for SessionStart today (real files use
# matcher: "startup" there); None elsewhere.
HOOK_REGISTRATIONS = (
    ("UserPromptSubmit", "python3", "loop_guard.py", None),
    ("Stop", "python3", "loop_stop_guard.py", None),
    ("SessionStart", "bash", "session_start.sh", "startup"),
    ("SubagentStop", "python3", "subagent_stop_gate.py", None),
    ("PreToolUse", "python3", "pre_tool_use_oga_guard.py", None),
)

TOOLS = ("claude_code", "codex")


def hooks_dir():
    return os.path.join(LOOP_ROOT, "hooks")


def canonical_command(runner, script):
    return "%s '%s'" % (runner, os.path.join(hooks_dir(), script))


def config_path_for(tool):
    home = os.path.expanduser("~")
    if tool == "claude_code":
        return os.path.join(home, ".claude", "settings.json")
    if tool == "codex":
        return os.path.join(home, ".codex", "hooks.json")
    raise ValueError("unknown tool: %r" % (tool,))


def load_config(path):
    """Returns (config_dict, error). config_dict is {} (not None) when the
    file simply doesn't exist yet (the real 'never installed' starting
    state, not an error). error is the exception when the file EXISTS but
    fails to parse as JSON -- callers that are about to WRITE must abort
    loudly on a non-None error (AC-12); callers that only READ (--check /
    detect_install_state.py) treat it as NOT_INSTALLED, fail-open, never
    crashing a read-only diagnostic."""
    if not os.path.isfile(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (ValueError, OSError) as e:
        return None, e


def registered_commands(config, event):
    """Every `command` string registered for `event`, flattened across all
    hook blocks (a real settings.json/hooks.json's "hooks"."<event>" value
    is a LIST of blocks, each carrying its own "hooks" list -- confirmed via
    direct read of both real files on this machine)."""
    out = []
    for block in (config or {}).get("hooks", {}).get(event, []) or []:
        if not isinstance(block, dict):
            continue
        for h in block.get("hooks", []) or []:
            if isinstance(h, dict):
                cmd = h.get("command")
                if cmd:
                    out.append(cmd)
    return out


def detect_state(config):
    """config -> "INSTALLED" | "NOT_INSTALLED" | "PARTIAL", by comparing
    each of the 5 real hook events' registered command string(s) against
    the expected canonical path (AC-9)."""
    registered = 0
    for event, runner, script, _matcher in HOOK_REGISTRATIONS:
        if canonical_command(runner, script) in registered_commands(config, event):
            registered += 1
    if registered == 0:
        return "NOT_INSTALLED"
    if registered == len(HOOK_REGISTRATIONS):
        return "INSTALLED"
    return "PARTIAL"


def state_for_tool(tool):
    config, err = load_config(config_path_for(tool))
    if err is not None:
        # Fail-open for a READ-ONLY diagnostic: an unparseable pre-existing
        # file can never be reported as INSTALLED (that would be a false
        # "everything's fine"); --install/--uninstall's own write path
        # (install.py) separately aborts loudly instead of silently
        # tolerating this, per AC-12.
        return "NOT_INSTALLED"
    return detect_state(config)


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="detect_install_state.py",
        description="Report per-tool loop-team guard install state "
                     "(INSTALLED / NOT_INSTALLED / PARTIAL). Always "
                     "tool-scoped -- never an aggregate/combined check.")
    p.add_argument("--tool", required=True, choices=TOOLS,
                    help="Which tool's config to inspect.")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    state = state_for_tool(args.tool)
    print("%s: %s" % (args.tool, state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
