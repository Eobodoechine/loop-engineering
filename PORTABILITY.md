# Portability — running the loop kit beyond Claude Code

_Source of truth: a source-verified research pass (2026-07-01); every specific claim
below carries its primary source; items marked **UNVERIFIED** could not be confirmed
against primary docs and need a short empirical test. The Codex CLI success is a user
report, not a maintained integration._

## The layer split

- **Layer A — prose playbooks** (`loop-team/orchestrator.md`, `loop-team/roles/*.md`):
  runtime-agnostic instructions. Any agent that reads files can follow them.
- **Layer B — CLI tools** (`loop-team/harness/verify.py`, the `loop-team/evals/`
  suite, `hooks/slop_gate.py`, `hooks/slop_calibrate.py`, the stall detector): plain
  Python, runnable anywhere. Layers A+B are what let OpenAI Codex CLI import and use
  the kit (user report).
- **Layer C — deterministic enforcement** (the five hooks): built for Claude Code's
  hook events and transcript JSONL. **The old assumption that this layer is
  Claude-Code-only is outdated** — Codex CLI, Gemini CLI, and Cursor now ship
  Claude-style lifecycle hooks with blocking semantics. Layer C ports as *adapters*
  (payload/transcript normalization), not rewrites.

## Four tiers of enforcement portability

**Tier 1 — git-native (universal, weakest scope).** Repo-state gates map to
[pre-commit](https://pre-commit.com/) + CI: step-size (staged-diff budget), slop gate,
marker sweep, testmon impact gate (pre-push), README freshness (pre-push), full
`verify.py`. **Cannot map**: plan-check-before-coder (fires before any file exists to
commit), thrash-past-green and retry-cap (turn-cadence state, no commit boundary),
independent-verifier dispatch + hygiene (agent topology — git has no concept of "who
verified"). Agents can pass `--no-verify`, so a CI job re-running the identical
scripts is the non-bypassable backstop.

**Tier 2 — hook adapters.** Event mapping for the kit's five hooks:

| Kit hook (Claude Code) | Codex CLI | Gemini CLI | Cursor |
|---|---|---|---|
| UserPromptSubmit (loop trigger) | `UserPromptSubmit` | `BeforeAgent` | `beforeSubmitPrompt` |
| Stop (verify-before-done) | `Stop` (`decision:"block"` continues the turn) | `AfterAgent` (`deny` + reason retries — arguably *stronger*) | `stop` (+`followup_message`) |
| SubagentStop (dispatch hygiene) | `SubagentStop` | **no subagent events** — hygiene not enforceable | `subagentStop` |
| PreToolUse (step/retry/testmon) | `PreToolUse` — see caveats | `BeforeTool` (regex matcher incl. MCP tools) | `preToolUse` / `beforeShellExecution` |
| SessionStart (context injection) | `SessionStart` | `SessionStart` (additionalContext) | `sessionStart` |

Per-runtime notes (primary sources):
- **Codex CLI** — hooks via `hooks.json` / `[hooks]` in `config.toml` (the `[features] hooks`
  flag existed at research time; a 2026-07-01 live check of the doc reads as
  enabled-by-default with the flag as the off-switch — re-check when wiring); all ten events incl. Stop/SubagentStop
  ([hooks docs](https://developers.openai.com/codex/hooks),
  [config reference](https://developers.openai.com/codex/config-reference)). Caveats
  from the issue tracker: PreToolUse historically fired for shell only — `apply_patch`
  edits bypassed hooks ([#16732](https://github.com/openai/codex/issues/16732),
  expansion tracked in [#18491](https://github.com/openai/codex/issues/18491)); silent
  hook failures on large files ([#18067](https://github.com/openai/codex/issues/18067));
  no additionalContext on PreToolUse
  ([#19385](https://github.com/openai/codex/issues/19385)). Until edit-tool coverage
  lands, key the step-size gate off Stop-time diff inspection. Hooks under
  `codex exec` (headless): **UNVERIFIED** — a 10-minute empirical test.
- **Gemini CLI** — hooks in `.gemini/settings.json`; stdin includes `transcript_path`
  (a direct analog of this kit's JSONL parsing); `AfterAgent` deny-with-reason retries
  the turn ([hooks reference](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md),
  [announcement](https://developers.googleblog.com/tailor-gemini-cli-to-your-workflow-with-hooks/)).
  Gap: no subagent events, so verifier-dispatch hygiene is not enforceable there.
- **Cursor** — `hooks.json` with a full event set incl. `stop`/`subagentStop`
  ([docs](https://cursor.com/docs/agent/hooks)); agent-hook coverage in the CLI:
  **partially verified** — treat as best-effort.
- **OpenHands** — no CLI hook config; SDK-level enforcement via custom
  `SecurityAnalyzerBase` analyzers + confirmation policies (per-action veto, no
  turn-completion gate) ([security docs](https://docs.openhands.dev/sdk/guides/security)).
  App users get prose (microagents) only.
- **Aider** — no hooks; wire `--test-cmd "python harness/verify.py ..."` +
  `--auto-test`, `--lint-cmd` → slop gate; its git auto-commits make ordinary
  pre-commit hooks apply ([lint/test docs](https://aider.chat/docs/usage/lint-test.html)).

The hard porting problem is **payload/transcript normalization**: each runtime hands
hooks different stdin JSON and stores turns differently (Codex session-file format:
**UNVERIFIED**). The gate logic itself stays shared.

**Tier 3 — prose templates.** AGENTS.md (Codex and others), GEMINI.md, CONVENTIONS.md
(aider), `.openhands/microagents/repo.md`: instruct the agent to run the Layer-B
tools at the right moments. This is what already worked for Codex — formalizing it is
cheap and honest about being advisory.

**Tier 4 — MCP gate server (future work).** Exposing `plan_check` / `verify_gate` /
`slop_check` as MCP tools would share the *implementation* across runtimes, but MCP is
advisory: the protocol cannot force a client to call a tool before completing a turn.
Correct architecture: MCP server as the shared gate implementation; each runtime's
hooks as the enforcement that requires a fresh gate-verdict token.

## Backlog (effort-marked; not yet built)

| Item | Effort |
|---|---|
| `.pre-commit-hooks.yaml` + CI backstop workflow | 1–2 days |
| Runtime adapter layer (payload/transcript normalizer) | ~1 week |
| `templates/codex/`, `templates/gemini/` (hooks config + AGENTS/GEMINI.md) | 2–3 days each, on top of adapters |
| `templates/cursor/` (best-effort) | 1–2 days |
| `templates/openhands/` (microagent prose + SDK analyzer example) | prose trivial; analyzer 2–3 days |
| `templates/aider/` (CONVENTIONS.md + .aider.conf.yml) | half a day |
| MCP gate server (advisory implementation layer) | ~1 week, deferred |
