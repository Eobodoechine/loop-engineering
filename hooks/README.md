# Hooks — install, verify, and understand the deterministic gates

This directory is the kit's enforcement layer for Claude Code: five hooks that make
the loop's rules *blockable*, not aspirational. The project rule: **a rule only
counts if a check enforces it** — and a hook you have never SEEN firing is not
installed. Every hook below therefore ships with (i) a standalone **logic check**
you can run from a fresh clone with no registration, and (ii) a **registration
check** — the observation that proves it fires in a real Claude Code session.

For other runtimes (Codex CLI, Gemini CLI, Cursor...), see `../PORTABILITY.md`.

## Prerequisites

- Python 3.9+ and git. The hooks themselves are stdlib-only.
- Optional, for the testmon impact gate and the slop metrics
  (`../loop-team/requirements-dev.txt`):
  `pip install pytest-testmon==2.1.4 radon` — the pin matters (2.2.0 drops
  Python 3.9) and the package's import name is `testmon`, not `pytest_testmon`.
  Without them the gates SKIP with a logged warning (fail-open), never a block.

## Register all five hooks (one time)

Merge into `~/.claude/settings.json` (create the `hooks` block if missing), using
the absolute path of your clone:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python3 '/absolute/path/to/loop-engineering/hooks/loop_guard.py'" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 '/absolute/path/to/loop-engineering/hooks/loop_stop_guard.py'" } ] }
    ],
    "SubagentStop": [
      { "hooks": [ { "type": "command", "command": "python3 '/absolute/path/to/loop-engineering/hooks/subagent_stop_gate.py'" } ] }
    ],
    "PreToolUse": [
      { "hooks": [ { "type": "command", "command": "python3 '/absolute/path/to/loop-engineering/hooks/pre_tool_use_oga_guard.py'" } ] }
    ],
    "SessionStart": [
      { "matcher": "startup",
        "hooks": [ { "type": "command", "command": "bash '/absolute/path/to/loop-engineering/hooks/session_start.sh'", "statusMessage": "Loading loop-team constraints..." } ] }
    ]
  }
}
```

Restart Claude Code (or reload settings) after editing.

## Configuration

| Thing | What it is |
|---|---|
| `~/.loop-team-config` | `base_dir=` line pointing at your clone root (copy `../.loop-team-config.example`). Read by the skill boot and the runner. |
| `LOOP_GATE_DIR` | Where gates keep per-session state. Default `~/.loop-gate` (auto-created; files older than 7 days are swept). |
| `$LOOP_GATE_DIR/<session>_target` | ARMS the micro-step gates: the orchestrator (Oga) writes the target repo's path here at run start and deletes it at run close. Stale files are ignored after 24h. Optional sibling `<session>_python` names the target's interpreter. |
| `../.gate/subprocess_tested.globs` | Globs for files exercised only via subprocess (invisible to testmon coverage) — the orphan check warns instead of blocking for these. Committed to git, never gitignored: a fresh clone must keep this protection. |

## The five hooks

### 1. `loop_guard.py` — UserPromptSubmit (the loop trigger)
Injects a mandatory "run the loop" directive on build/edit prompts; silent otherwise.
- **Logic check:** `echo '{"prompt": "build a parser for X"}' | python3 hooks/loop_guard.py`
  → prints the LOOP GUARD directive. A trivial prompt (`"fix a typo"`) prints nothing.
- **Registration check:** type a build-shaped prompt in a real session; the injected
  `[LOOP GUARD]` line appears in the model's context (it will mention running the loop).

### 2. `loop_stop_guard.py` — Stop (the turn-completion gate)
Blocks ending a turn when: a feature was edited without an independent verifier; a
role/harness file changed without a green eval suite; a Coder was dispatched without a
preceding plan-check; research flowed straight into edits; a Verifier dispatch carried
result-shaped context (see the dispatch-hygiene note below); or a micro-step gate
fires (thrash-past-green, step-size over 200 changed lines, retry-cap at the third
same-signature failure, testmon impact gate). Everything is fail-open on internal
errors — a broken gate must never trap a session.
- **Logic check (example — the step-size gate, complete arming sequence):** see the
  step-by-step demo in `../QUICKSTART.md`; it builds a temp repo, arms
  `$LOOP_GATE_DIR/<session>_target`, and pipes synthetic stdin through this hook,
  expecting exit code 2 with a `[MICRO-STEP GATE: step-size]` message.
- **Registration check:** in a real loop-team session, end a turn right after editing
  a role file without re-running the eval suite — the stop is blocked with the
  suite-green requirement quoted.

**Dispatch-hygiene note (sweep-safe wording):** the gate scans Verifier dispatch
prompts for result-shaped phrases like "tests-passed", "all-green", or "decision-log"
content (hyphenated here so this document never trips the marker sweep that guards
this directory — the canonical nine-phrase list lives in `_hyg_markers()` inside
`loop_stop_guard.py`, and the two orchestrator-arming markers live in
`micro_step_gates.py`). Role-file text is subtracted before scanning, so embedding
`roles/verifier.md` in a dispatch is always safe; only orchestrator-ADDED context can
trip it. Remedy when blocked: reference the spec by file path and drop the result
assertions.

### 3. `subagent_stop_gate.py` — SubagentStop
Records plan-check Verifier verdict tokens (the LOOP_GATE line) as flag files the
Stop gate consumes across turns.
- **Logic check:** `LOOP_GATE_DIR=$(mktemp -d) python3 -c "import json,subprocess,sys;
  r=subprocess.run([sys.executable,'hooks/subagent_stop_gate.py'],input=json.dumps({'session_id':'t','agent_id':'a','last_assistant_message':'...\nLOOP_GATE: PLAN_PASS'}),capture_output=True,text=True); print(r.returncode)"`
  → `0`, and a `t_*.verifier_pass` flag appears in that temp dir.
- **Registration check:** after a real plan-check dispatch returns PLAN_PASS, the flag
  file appears under `~/.loop-gate/`.

### 4. `pre_tool_use_oga_guard.py` — PreToolUse
Blocks the ORCHESTRATOR from writing code directly (it must dispatch a Coder) — armed
only when the orchestrator's playbook is genuinely loaded in the transcript, never by
the mere mention of the skill.
- **Logic check** (builds its fixture from the real corpus rather than embedding any
  arming text in this document):
  ```bash
  T=$(mktemp); python3 - "$T" << 'PY'
  import json, sys
  head = open("loop-team/orchestrator.md").read(2000)
  open(sys.argv[1], "w").write(json.dumps(
      {"role": "user", "content": [{"type": "text", "text": head}]}))
  PY
  echo "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"/tmp/x.py\"},\"transcript_path\":\"$T\"}" \
    | python3 hooks/pre_tool_use_oga_guard.py
  ```
  → prints a deny JSON (`"permissionDecision": "deny"`). Re-run with a `.md`
  file_path → no output (docs are never gated).
- **Registration check:** in a real Oga session, a direct code Write without a prior
  Agent dispatch is denied with the OGA GUARD message.

### 5. `session_start.sh` — SessionStart
Injects the orchestrator constraints at session start. Reads **no stdin**.
- **Logic check:** `bash hooks/session_start.sh` → prints the additionalContext JSON
  (or nothing if `orchestrator-constraints.txt` is absent — that silence is its
  documented no-constraints behavior).
- **Registration check:** a new session shows "Loading loop-team constraints..." at
  startup.

## Shadow tools (never block)

`slop_gate.py` computes erosion metrics on the uncommitted diff and appends a JSON
verdict to `$LOOP_GATE_DIR/<session>_slop.jsonl` — shadow mode only; arming a block
layer is a later, calibration-gated decision. `slop_calibrate.py -n 30 [repo]` replays
git history to suggest thresholds (distrust them while most deltas are zero — the
output says so itself).

## Troubleshooting

| Symptom | Meaning / remedy |
|---|---|
| `testmon gate SKIPPED: pytest-testmon not importable` | Optional dep missing in the target's interpreter — install the pinned extras, or accept fail-open. |
| `[MICRO-STEP GATE: orphan-module] no test exercises <f>` | Write a test that imports it, or (subprocess-tested files only) add a glob to `.gate/subprocess_tested.globs` with justification. |
| Freshness block persists after re-running tests | Comment-only edits may not refresh testmon's fingerprints — checkpoint the commit to clear it. |
| Gates silent when expected | Check `$LOOP_GATE_DIR/<session>_target` exists, is <24h old, and names a git repo; check the transcript actually contains the orchestrator's playbook content. |
| `[micro-step-gates] disabled by error (fail-open): ...` | An internal error was swallowed by design; the named exception is your bug report. |
| Hygiene block on a Verifier dispatch | Reference the spec by path; remove result-shaped assertions from the dispatch prompt. |

## Learn the system (reading path)

1. `../loop-team/orchestrator.md` — the whole method: the loop, micro-steps, arbiter.
2. `../loop-team/TEAM_RELATIONS.md` — who gets told what, and what is withheld.
3. `../loop-team/roles/` — the role briefs (verifier.md is the heart).
4. `../loop-team/evals/README.md` — the verifier-for-the-verifier.
5. This file — the enforcement layer.
6. `../PORTABILITY.md` — taking it beyond Claude Code.
