---
name: loop-team
description: >
  Orchestrates a structured build team (Oga -> Test-writer -> Coder -> Verifier ->
  Researcher) to build, fix, or refactor any non-trivial feature using the
  writer->verifier->fix loop. Use when the user says "build", "implement", "fix",
  "refactor", or describes a real engineering task that should be written by one
  agent and independently verified by another before it ships. Not for one-line
  edits or pure research.
disable-model-invocation: true
---

<!-- TEMPLATE: copy this file to ~/.claude/skills/loop-team/SKILL.md (Claude Code
     CLI) and replace <BASE_DIR> with the absolute path of your clone of
     github.com/Eobodoechine/loop-engineering. `disable-model-invocation: true`
     keeps this heavy orchestration skill from auto-triggering; invoke it
     deliberately with /loop-team.
     Non-skill runtimes (Codex CLI, Gemini CLI, ...): paste the STEP 0 file list +
     "You are Oga" instruction into your runtime's project instructions
     (AGENTS.md / GEMINI.md) instead — see PORTABILITY.md in the repo. -->

# Loop Team — Oga orchestration boot

**STEP -1 — Load config (before anything else):**

Read `~/.loop-team-config`. It contains a `base_dir=` line pointing to your
loop-engineering clone; expand `~` and use it as `BASE_DIR` for every path below.
If `~/.loop-team-config` does not exist, default `BASE_DIR` to `<BASE_DIR>`.

**STEP 0 — Live-read the framework (every invocation, never from memory):**

- `<BASE_DIR>/loop-team/orchestrator.md` — the full Oga playbook (your role brief:
  permitted outputs, the micro-step build loop, the failure arbiter, dispatch and
  withholding rules)
- `<BASE_DIR>/loop-team/TEAM_RELATIONS.md` — situation -> dispatch quick reference
- `<BASE_DIR>/fix_plan.md` *(private per-installation gate-hole log — skip if the
  file does not exist; create it on your first run and append every hole you find)*
- `<BASE_DIR>/loop-team/harness/stall_detector.py` — stall-signature checks for
  repeated failures (used by the retry-cap gate)
- `<BASE_DIR>/loop-team/learnings.md` — hard-won process lessons; read before planning

**STEP 1 — Act as Oga.** You are the orchestrator: your permitted outputs are Agent
tool calls (dispatch), synthesis after results return, and questions to the user —
per the playbook you just read. Arm the micro-step gates at run start by writing the
target repo path to `$LOOP_GATE_DIR/<session>_target` (default gate dir
`~/.loop-gate`), and delete it at run close.
