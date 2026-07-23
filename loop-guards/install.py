#!/usr/bin/env python3
"""install.py -- portable, consent-gated installer for the loop-team
enforcement hooks (Deliverable B,
research/spec-codex-parity-and-consent-installer-2026-07-09.md).

    python3 loop-guards/install.py --check
    python3 loop-guards/install.py --install   --tool claude_code|codex
    python3 loop-guards/install.py --uninstall --tool claude_code|codex

Design constraints this file exists to satisfy (see the spec's own AC
numbers for the full reasoning -- this docstring only summarizes):

  AC-9/AC-10: --check is read-only (never writes); --install is a silent
    no-op ("already installed, nothing to do") when the target tool is
    already fully INSTALLED -- and that no-op check happens BEFORE any
    consent prompt, so a repeat install never needs a controlling terminal
    at all.

  AC-11/AC-15(c): consent for a FIRST-time install/uninstall is read from
    /dev/tty directly, never sys.stdin (a piped `echo yes | ...` must NOT
    satisfy it) -- and if /dev/tty cannot be opened at all (no controlling
    terminal, e.g. a real CI/non-interactive context), this script fails
    CLOSED: non-zero exit, zero writes, regardless of any flag. No flag or
    env var bypasses this prompt -- this script deliberately does not
    implement any such bypass (see this Coder's own decision log for why).

  AC-12: on accept, the hook registration block is JSON-MERGED into the
    target file (never a blind overwrite) -- any pre-existing, unrelated
    content is preserved. The pending diff is printed BEFORE the consent
    prompt is even asked, so a human sees exactly what would change either
    way. A pre-existing file that fails to parse as JSON aborts loudly
    (non-zero exit, names the file), with ZERO writes attempted.

  AC-13: for Codex, this script writes ONLY ~/.codex/hooks.json -- it never
    reads or writes ~/.codex/config.toml (the [hooks.state]/trusted_hash
    file) at all. Its post-install message for Codex explicitly tells the
    human to open Codex and approve the new/changed hooks via /hooks --
    this script cannot do that step for them.

  AC-15: ships a documented, tested --uninstall path in this same build.
"""
import argparse
import copy
import json
import os
import sys

LOOP_GUARDS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LOOP_GUARDS_DIR)
import detect_install_state as dis  # noqa: E402


def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-loop-guards-install"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _read_consent(prompt):
    """Reads a y/n answer from the REAL controlling terminal via /dev/tty
    directly (AC-11) -- NEVER sys.stdin, which a piped `echo yes | ...`
    could satisfy without any genuine human present. Returns True (accept),
    False (decline), or None (no controlling terminal could be opened at
    all -- caller must fail closed, per AC-15(c)).

    Opens /dev/tty as TWO separate handles (one write-only, one read-only)
    rather than a single combined "r+" handle: a tty/pty special file is
    not seekable, and a single buffered read+write TextIOWrapper over it
    raises `io.UnsupportedOperation: File or stream is not seekable` the
    moment it needs to reconcile read/write buffer state (confirmed live
    while building this) -- two independent handles avoid that entirely."""
    try:
        tty_out = open("/dev/tty", "w", encoding="utf-8")
    except OSError:
        return None
    try:
        tty_in = open("/dev/tty", "r", encoding="utf-8")
    except OSError:
        tty_out.close()
        return None
    try:
        tty_out.write(prompt)
        tty_out.flush()
        line = tty_in.readline()
    finally:
        tty_out.close()
        tty_in.close()
    answer = line.strip().lower()
    return answer in ("y", "yes")


def build_merged_config(config):
    """Returns (new_config, added_lines). added_lines: human-readable
    "<event> -> <command>" strings, ONE PER HOOK EVENT NOT ALREADY
    canonically registered -- this doubles as both the diff-preview text
    (AC-12) and the "how many events were newly registered" count. Adds a
    NEW block per missing event (never rewrites/merges INTO an existing
    block) -- this is the real, confirmed shape both ~/.claude/settings.json
    and ~/.codex/hooks.json already use on this machine for multiple
    independent hook registrations on the same event (e.g. Codex's own
    UserPromptSubmit carries two separate blocks today), and it is what
    keeps a pre-existing unrelated block byte-for-byte untouched."""
    new_config = copy.deepcopy(config) if config else {}
    new_config.setdefault("hooks", {})
    added = []
    for event, runner, script, matcher in dis.HOOK_REGISTRATIONS:
        canonical = dis.canonical_command(runner, script)
        if canonical in dis.registered_commands(new_config, event):
            continue
        block = {"hooks": [{"type": "command", "command": canonical}]}
        if matcher:
            block["matcher"] = matcher
        new_config["hooks"].setdefault(event, [])
        new_config["hooks"][event].append(block)
        added.append("%s -> %s" % (event, canonical))
    return new_config, added


def build_unmerged_config(config):
    """Returns (new_config, removed_lines). Removes ONLY hook entries whose
    `command` exactly matches one of THIS framework's own canonical
    commands -- a block that still has other (unrelated) entries after
    removal is kept with just its own entry dropped; a block that becomes
    fully empty is dropped entirely; an event whose block list becomes
    empty is removed from "hooks" -- everything else (other events, other
    top-level keys) is untouched."""
    new_config = copy.deepcopy(config) if config else {}
    hooks = new_config.setdefault("hooks", {})
    removed = []
    for event, runner, script, _matcher in dis.HOOK_REGISTRATIONS:
        canonical = dis.canonical_command(runner, script)
        blocks = hooks.get(event, [])
        if not blocks:
            continue
        new_blocks = []
        event_removed = False
        for block in blocks:
            if not isinstance(block, dict):
                new_blocks.append(block)
                continue
            block_hooks = block.get("hooks", []) or []
            kept_hooks = [h for h in block_hooks
                          if not (isinstance(h, dict) and h.get("command") == canonical)]
            if len(kept_hooks) != len(block_hooks):
                event_removed = True
            if kept_hooks:
                new_block = dict(block)
                new_block["hooks"] = kept_hooks
                new_blocks.append(new_block)
            # else: block held ONLY our own entry -- drop the whole block.
        if event_removed:
            removed.append("%s -> %s" % (event, canonical))
        if new_blocks:
            hooks[event] = new_blocks
        elif event in hooks:
            del hooks[event]
    return new_config, removed


def _print_diff(path, lines, verb):
    print("Pending %s at %s:" % (verb, path))
    for line in lines:
        print("  %s %s" % ("+" if verb == "changes" else "-", line))


def do_check(_args=None):
    for tool in dis.TOOLS:
        print("%s: %s" % (tool, dis.state_for_tool(tool)))
    return 0


def do_install(tool):
    path = dis.config_path_for(tool)
    config, err = dis.load_config(path)

    # AC-10: the already-installed no-op check happens FIRST, before any
    # consent prompt is even attempted -- a repeat install on an
    # already-provisioned machine must succeed even with zero controlling
    # terminal available.
    if err is None and dis.detect_state(config) == "INSTALLED":
        print("%s: already installed, nothing to do." % tool)
        return 0

    # AC-12: malformed pre-existing JSON aborts loudly, ZERO writes
    # attempted -- never silently overwritten, never tolerated as "empty".
    if err is not None:
        sys.stderr.write(
            "ERROR: %s exists but is not valid JSON (%s). Aborting -- zero "
            "writes attempted. Fix or remove the file by hand and re-run.\n"
            % (path, err))
        return 1

    new_config, added = build_merged_config(config)
    if not added:
        print("%s: already installed, nothing to do." % tool)
        return 0

    _print_diff(path, added, "changes")

    consent = _read_consent(
        "\nInstall loop-team guards for %s? These hooks can BLOCK certain "
        "Stop/sub-agent turns until a run-log exists (RUNLOG_MISSING) and "
        "green work is committed (thrash-past-green/step-size). Proceed? "
        "[y/N]: " % tool)
    if consent is None:
        sys.stderr.write(
            "ERROR: no controlling terminal (/dev/tty) available -- "
            "refusing to install in a non-interactive context. Re-run this "
            "from a real interactive terminal.\n")
        return 1
    if not consent:
        print("Declined -- no changes written.")
        return 0

    _atomic_write_json(path, new_config)
    print("%s: installed (%d hook event(s) registered) at %s."
          % (tool, len(added), path))
    if tool == "codex":
        print(
            "IMPORTANT: this script writes ONLY ~/.codex/hooks.json -- open "
            "Codex and approve the new/changed hooks via the /hooks "
            "command; this install script cannot do that step for you.")
    return 0


def do_uninstall(tool):
    path = dis.config_path_for(tool)
    config, err = dis.load_config(path)
    if err is not None:
        sys.stderr.write(
            "ERROR: %s exists but is not valid JSON (%s). Aborting -- zero "
            "writes attempted.\n" % (path, err))
        return 1

    new_config, removed = build_unmerged_config(config)
    if not removed:
        print("%s: not installed, nothing to uninstall." % tool)
        return 0

    _print_diff(path, removed, "removal")

    consent = _read_consent(
        "\nUninstall loop-team guards for %s from %s? [y/N]: " % (tool, path))
    if consent is None:
        sys.stderr.write(
            "ERROR: no controlling terminal (/dev/tty) available -- "
            "refusing to uninstall in a non-interactive context.\n")
        return 1
    if not consent:
        print("Declined -- no changes written.")
        return 0

    _atomic_write_json(path, new_config)
    print("%s: uninstalled (%d hook event(s) removed) from %s."
          % (tool, len(removed), path))
    return 0


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="install.py",
        description="Consent-gated installer for the loop-team enforcement "
                     "hooks (Claude Code + Codex).")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                       help="Report per-tool install state for BOTH tools. "
                            "Read-only, no side effects.")
    mode.add_argument("--install", action="store_true",
                       help="Install (JSON-merge) for the tool named by "
                            "--tool. Requires explicit /dev/tty consent.")
    mode.add_argument("--uninstall", action="store_true",
                       help="Remove this framework's own hook entries for "
                            "the tool named by --tool, preserving "
                            "everything else. Requires explicit /dev/tty "
                            "consent.")
    p.add_argument("--tool", choices=dis.TOOLS,
                    help="Required for --install/--uninstall.")
    return p


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.check:
        return do_check()

    if not args.tool:
        parser.error("--install/--uninstall require --tool "
                      "<claude_code|codex>")

    if args.install:
        return do_install(args.tool)
    return do_uninstall(args.tool)


if __name__ == "__main__":
    sys.exit(main())
