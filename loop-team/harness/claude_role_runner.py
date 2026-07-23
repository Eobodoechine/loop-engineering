#!/usr/bin/env python3
"""Run non-Coder loop-team roles through the local Claude Code CLI.

This is the Codex-hosted bridge: Codex can keep ownership of the main build in
this chat while asking Claude Code for independent plan-check, verification,
research, and test-writing roles through `claude -p`.

The runner is deliberately narrow. It does not dispatch Claude as Coder, because
two writers in one checkout are the highest-collision path. If Claude should
write code, use a separate worktree and a separate handoff.
"""

from __future__ import print_function

import argparse
import json
import os
import subprocess
import sys


DEFAULT_BASE_DIR = "~/Claude/loop"
DEFAULT_CONFIG = "~/.loop-team-config"


ROLE_CONFIGS = {
    "plan-check-verifier": {
        "role_file": "loop-team/roles/verifier.md",
        "mode": "PLAN-CHECK",
        "final_tokens": ("LOOP_GATE: PLAN_PASS", "LOOP_GATE: PLAN_FAIL"),
    },
    "post-build-verifier": {
        "role_file": "loop-team/roles/verifier.md",
        "mode": "POST-BUILD",
        "final_tokens": ("VERDICT: PASS", "VERDICT: FAIL", "VERDICT: FALSE-PASS"),
    },
    "test-writer": {
        "role_file": "loop-team/roles/test_writer.md",
        "mode": "TEST-WRITER",
        "final_tokens": (),
    },
    "researcher": {
        "role_file": "loop-team/roles/researcher.md",
        "mode": "RESEARCHER",
        "final_tokens": (),
    },
    "gold-judge": {
        "role_file": "loop-team/roles/gold_judge.md",
        "mode": "GOLD-JUDGE",
        "final_tokens": ("VERDICT: PASS", "VERDICT: FAIL", "VERDICT: FALSE-PASS"),
    },
    "live-smoke": {
        "role_file": "loop-team/roles/live_smoke.md",
        "mode": "LIVE-SMOKE",
        "final_tokens": (),
    },
}


def _expand(path):
    return os.path.abspath(os.path.expanduser(path))


def load_base_dir(config_path=None):
    """Read ~/.loop-team-config's base_dir= line, defaulting to ~/Claude/loop."""
    path = _expand(config_path or DEFAULT_CONFIG)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("base_dir="):
                    value = stripped.split("=", 1)[1].strip()
                    if value:
                        return _expand(value)
    except OSError:
        pass
    return _expand(DEFAULT_BASE_DIR)


def role_file_path(base_dir, role):
    if role not in ROLE_CONFIGS:
        raise ValueError("unsupported role: %s" % role)
    return os.path.join(base_dir, ROLE_CONFIGS[role]["role_file"])


def last_non_empty_line(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def validate_final_token(role, text):
    tokens = ROLE_CONFIGS[role]["final_tokens"]
    if not tokens:
        return True, last_non_empty_line(text)
    final_line = last_non_empty_line(text)
    return final_line in tokens, final_line


def read_prompt(prompt, prompt_file):
    if prompt_file:
        with open(prompt_file, encoding="utf-8") as f:
            return f.read()
    return prompt or ""


def build_role_prompt(base_dir, role, delegation):
    cfg = ROLE_CONFIGS[role]
    role_path = role_file_path(base_dir, role)
    final_tokens = cfg["final_tokens"]
    token_note = (
        "Final line requirement: the last non-empty line MUST be exactly one "
        "of: %s" % ", ".join(final_tokens)
        if final_tokens else
        "No special final token is required for this role unless the role file says so."
    )
    return "\n".join([
        "You are acting as a loop-team %s for Codex/Oga." % role,
        "Mode: %s." % cfg["mode"],
        "",
        "Before doing role work, read this canonical role file in full:",
        role_path,
        "",
        "Base loop-team directory:",
        base_dir,
        "",
        "Constraints:",
        "- Do not spawn sub-agents.",
        "- Do not edit files unless the role explicitly requires test artifacts.",
        "- If the delegation conflicts with the role file, follow the role file.",
        "- Report exact commands/files you read or ran.",
        "- %s" % token_note,
        "",
        "Delegation from Codex/Oga:",
        delegation.strip(),
        "",
    ])


def build_claude_command(args, base_dir, prompt_text):
    cmd = [
        args.claude_bin,
        "-p",
        "--output-format", "text",
        "--permission-mode", args.permission_mode,
        "--add-dir", base_dir,
    ]
    if args.max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(args.max_budget_usd)])
    if args.model:
        cmd.extend(["--model", args.model])
    cmd.append(prompt_text)
    return cmd


def claude_auth_status(claude_bin="claude", run=subprocess.run):
    proc = run(
        [claude_bin, "auth", "status"],
        capture_output=True,
        text=True,
    )
    payload = {}
    try:
        payload = json.loads(proc.stdout or "{}")
    except ValueError:
        payload = {"raw_stdout": proc.stdout}
    payload["exit_code"] = proc.returncode
    payload["stderr"] = proc.stderr
    return payload


def run_role(args, run=subprocess.run):
    base_dir = load_base_dir(args.config)
    delegation = read_prompt(args.prompt, args.prompt_file)
    role_prompt = build_role_prompt(base_dir, args.role, delegation)

    if not args.skip_auth_check:
        auth = claude_auth_status(args.claude_bin, run=run)
        if not auth.get("loggedIn"):
            return 3, {
                "ok": False,
                "error": "claude_not_logged_in",
                "message": "Claude Code CLI is not logged in; run `claude auth login` before using Claude-backed loop-team roles.",
                "auth": auth,
            }

    cmd = build_claude_command(args, base_dir, role_prompt)
    proc = run(
        cmd,
        capture_output=True,
        text=True,
        cwd=args.cwd or base_dir,
        timeout=args.timeout,
    )
    output = proc.stdout or ""
    valid, final_line = validate_final_token(args.role, output)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    return (0 if proc.returncode == 0 and valid else 2), {
        "ok": proc.returncode == 0 and valid,
        "role": args.role,
        "exit_code": proc.returncode,
        "final_line": final_line,
        "final_token_valid": valid,
        "output_path": args.output,
        "stdout": output,
        "stderr": proc.stderr,
    }


def make_parser():
    parser = argparse.ArgumentParser(
        description="Run non-Coder loop-team roles via the local Claude Code CLI."
    )
    parser.add_argument("--check", action="store_true",
                        help="Check Claude CLI auth and exit without spending tokens.")
    parser.add_argument("--role", choices=sorted(ROLE_CONFIGS.keys()),
                        help="Loop-team role to run. Claude-as-Coder is intentionally unsupported.")
    parser.add_argument("--prompt", default="", help="Delegation prompt text.")
    parser.add_argument("--prompt-file", help="Read delegation prompt from this file.")
    parser.add_argument("--output", help="Write Claude's raw final text to this file.")
    parser.add_argument("--cwd", help="Working directory for the Claude CLI run.")
    parser.add_argument("--config", help="Path to loop-team config file.")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--permission-mode", default="dontAsk",
                        choices=("acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"))
    parser.add_argument("--model", help="Optional Claude model alias/name.")
    parser.add_argument("--max-budget-usd", type=float, default=0.50)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--skip-auth-check", action="store_true",
                        help="Skip auth preflight. Intended for tests only.")
    return parser


def main(argv=None, run=subprocess.run):
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.check:
        status = claude_auth_status(args.claude_bin, run=run)
        ok = bool(status.get("loggedIn"))
        print(json.dumps({"ok": ok, "auth": status}, sort_keys=True))
        return 0 if ok else 1
    if not args.role:
        parser.error("--role is required unless --check is used")
    code, payload = run_role(args, run=run)
    print(json.dumps(payload, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
