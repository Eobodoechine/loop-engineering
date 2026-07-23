# loop-guards

Portable, consent-gated installer for the loop-team enforcement hooks --
Deliverable B/C of
`research/spec-codex-parity-and-consent-installer-2026-07-09.md` ("Codex
enforcement parity + consent-gated installer").

## What these guards do

Two real, active enforcement gates, for BOTH Claude Code and Codex:

- **The run-log gate (`RUNLOG_MISSING`)**, in `hooks/loop_stop_guard.py`:
  blocks a turn from ending when a post-build Verifier sub-agent returned
  `VERDICT: PASS` for a build, but no non-empty `run_log.md` (or
  `RUN_LOG.md` / `iteration_log.md`) exists in that build's run directory.
- **The checkpoint gate (`thrash-past-green` / `step-size`)**, in
  `hooks/micro_step_gates.py`: blocks a turn from ending when the last
  verify was green, a Coder/worker sub-agent was dispatched after it, and
  the target repo still has uncommitted code changes with no commit since
  that green run (or when an uncommitted diff has simply grown too large).

These are the "something that can say no" enforcement this framework
depends on -- see `## What breaks without these guards` below for what
happens if they aren't installed.

## Quick install

```
# Check current state for both tools (read-only, no side effects):
python3 loop-guards/install.py --check

# Install for whichever tool(s) you use -- each asks for explicit consent
# at a real terminal before writing anything:
python3 loop-guards/install.py --install --tool claude_code
python3 loop-guards/install.py --install --tool codex
```

A repeat install is a silent no-op ("already installed, nothing to do") --
safe to re-run at any time. `python3 loop-guards/detect_install_state.py
--tool <claude_code|codex>` is the tool-scoped version of the same check,
used by the bootstrap snippets below.

## Manual install

If you declined the automatic prompt, or you're viewing/using this repo
somewhere the bootstrap check in `bootstrap/CLAUDE_MD_SNIPPET.md` /
`bootstrap/AGENTS_MD_SNIPPET.md` never ran (e.g. browsing the repo on
GitHub, or a tool with no `AGENTS.md`/`CLAUDE.md` auto-read at all), add
the hooks by hand. Replace `/path/to/loop` below with wherever you cloned
this repo.

### Claude Code

1. Open `~/.claude/settings.json` (create it, e.g. `{}`, if it does not
   exist yet).
2. Merge the block below into its top-level `"hooks"` key -- ADD to, never
   replace, anything you already have registered there.

```
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/loop_guard.py'"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/loop_stop_guard.py'"}]}
    ],
    "SessionStart": [
      {"matcher": "startup", "hooks": [{"type": "command", "command": "bash '/path/to/loop/hooks/session_start.sh'"}]}
    ],
    "SubagentStop": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/subagent_stop_gate.py'"}]}
    ],
    "PreToolUse": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/pre_tool_use_oga_guard.py'"}]}
    ]
  }
}
```

3. Start a new Claude Code session (or restart the current one) so it
   re-reads `settings.json`.

### Codex

1. Open `~/.codex/hooks.json` (create it, e.g. `{}`, if it does not exist
   yet).
2. Merge the block below into its top-level `"hooks"` key -- ADD to, never
   replace, anything you already have registered there.

```
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/loop_guard.py'"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/loop_stop_guard.py'"}]}
    ],
    "SessionStart": [
      {"matcher": "startup", "hooks": [{"type": "command", "command": "bash '/path/to/loop/hooks/session_start.sh'"}]}
    ],
    "SubagentStop": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/subagent_stop_gate.py'"}]}
    ],
    "PreToolUse": [
      {"hooks": [{"type": "command", "command": "python3 '/path/to/loop/hooks/pre_tool_use_oga_guard.py'"}]}
    ]
  }
}
```

3. Open Codex and run `/hooks` to review and **APPROVE** the new/changed
   hooks. Codex will not trust a hook it hasn't seen a human explicitly
   approve -- this is a human-only step; neither `install.py` nor a manual
   `hooks.json` edit can do it for you. `install.py` deliberately never
   writes to `~/.codex/config.toml` (the file that records that trust,
   `[hooks.state]`/`trusted_hash`) for exactly this reason -- it is not
   something a script should ever fabricate or pre-approve on your behalf.

## Uninstalling

```
python3 loop-guards/install.py --uninstall --tool claude_code
python3 loop-guards/install.py --uninstall --tool codex
```

Removes only this framework's own registered hook entries (matched by
their exact `command` string), preserving every other hook/setting already
in the file untouched. Also asks for explicit consent at a real terminal
before writing anything, and shows the pending removal first.

## What breaks without these guards installed

Without the hooks above actually registered with Claude Code / Codex, the
run-log gate and the checkpoint gate become **purely advisory prose
again** -- nothing will actually block a turn. Concretely:

- A build can be declared done (`VERDICT: PASS`) with no `run_log.md` ever
  written, and nothing stops it.
- Green, verified work can sit uncommitted indefinitely (or be silently
  lost/overwritten), because the checkpoint/thrash-past-green gate is no
  longer enforced -- it's just a convention in `orchestrator.md` that
  nothing is actively checking.

Installing (or manually adding, per `## Manual install` above) these hooks
is what turns those two rules from prose into something that can actually
say no. If you decline, that's an informed choice, not a silent gap.
