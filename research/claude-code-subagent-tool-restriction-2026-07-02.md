# Claude Code custom subagent types + tool restriction — feasibility for loop-team

Date: 2026-07-02
Mode: D (domain research for a build; feeds cookbook-review item 2)
Question source: `research/claude-cookbooks-review-2026-07-02.md` item 2

## Bottom line

**Both mechanisms the dossier proposed are real, officially documented, and available to
loop-team today — with one important scoping caveat on the "restrict which subagent types
Oga can spawn" angle.** No fabrication needed; no fallback to hook-interception required as
a *replacement* (though the hook layer is still valuable as defense-in-depth and is already
partially built).

1. **Custom subagent types with restricted tool lists: YES, fully supported.** Markdown
   files with YAML frontmatter in `.claude/agents/` (project) or `~/.claude/agents/` (user),
   with a `tools` allowlist and/or `disallowedTools` denylist field. Confirmed against
   `https://code.claude.com/docs/en/sub-agents` (fetched verbatim 2026-07-02).
2. **Excluding Agent/Task from a subagent's own tool list: YES, and this is the exact
   mechanism that closes the punting failure.** `disallowedTools: Agent` (or simply omitting
   `Agent` from a `tools` allowlist) makes that subagent structurally unable to spawn ANY
   nested subagent — not just told not to in the prompt.
3. **Caveat that matters for loop-team specifically**: the `Agent(agent_type)` *allowlist*
   syntax (restricting WHICH types can be spawned, e.g. `Agent(worker, researcher)`) only
   applies when an agent runs as **the main thread** via `claude --agent <name>`. Oga is
   *not* invoked that way today — Oga runs as the main interactive CLI session and dispatches
   sub-agents itself via the plain `Agent` tool call (with `subagent_type` currently always a
   built-in like `general-purpose`, with the role brief pasted into `prompt`). So the
   "5 custom types with correct types selectable at dispatch time" part of the dossier's
   proposal needs one additional step (below) beyond just creating the files.

---

## 1. Does Claude Code support user/project-defined custom subagent types with restricted tool lists?

**Yes.** Verbatim from `https://code.claude.com/docs/en/sub-agents` (section "Choose the
subagent scope"):

> Subagents are Markdown files with YAML frontmatter. Store them in different locations
> depending on scope. When multiple subagents share the same name, Claude Code uses the one
> from the higher-priority location.

| Location | Scope | Priority | How to create |
|---|---|---|---|
| Managed settings | Organization-wide | 1 (highest) | Deployed via managed settings |
| `--agents` CLI flag | Current session | 2 | Pass JSON when launching Claude Code |
| `.claude/agents/` | Current project | 3 | Interactive or manual |
| `~/.claude/agents/` | All your projects | 4 | Interactive or manual |
| Plugin's `agents/` directory | Where plugin is enabled | 5 (lowest) | Installed with plugins |

This session confirmed via `ls -la ~/.claude/agents/` and a project-tree search under
`~/Claude/loop` that **neither directory currently exists** — the dossier's premise that
"this session found NO existing `~/.claude/agents/` directory" is correct and the mechanism
would need to be created from scratch (not discovered pre-configured elsewhere).

### Exact frontmatter schema (verbatim table from the docs)

> The following fields can be used in the YAML frontmatter. Only `name` and `description`
> are required.

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Unique identifier using lowercase letters and hyphens. Hooks receive this value as `agent_type`. The filename doesn't have to match |
| `description` | Yes | When Claude should delegate to this subagent |
| `tools` | No | Tools the subagent can use. Inherits all tools if omitted. To preload Skills into context, use the `skills` field rather than listing `Skill` here |
| `disallowedTools` | No | Tools to deny, removed from inherited or specified list |
| `model` | No | `sonnet`, `opus`, `haiku`, `fable`, a full model ID, or `inherit`. Defaults to `inherit` |
| `permissionMode` | No | `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, or `plan`. Ignored for plugin subagents |
| `maxTurns` | No | Maximum number of agentic turns before the subagent stops |
| `skills` | No | Skills to preload into the subagent's context at startup |
| `mcpServers` | No | MCP servers available to this subagent (inline or by-name reference). Ignored for plugin subagents |
| `hooks` | No | Lifecycle hooks scoped to this subagent. Ignored for plugin subagents |
| `memory` | No | Persistent memory scope: `user`, `project`, or `local` |
| `background` | No | Always run as a background task. Default `false` |
| `effort` | No | Effort level override |
| `isolation` | No | `worktree` for an isolated git worktree copy |
| `color` | No | Display color |
| `initialPrompt` | No | Auto-submitted first user turn when this agent runs as the main session agent |

Basic example (verbatim):

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a code reviewer. When invoked, analyze the code and provide
specific, actionable feedback on quality, security, and best practices.
```

### The tool-restriction mechanism itself (verbatim)

> To restrict tools, use either the `tools` field (allowlist) or the `disallowedTools`
> field (denylist). This example uses `tools` to exclusively allow Read, Grep, Glob, and
> Bash. The subagent can't edit files, write files, or use any MCP tools:

```yaml
---
name: safe-researcher
description: Research agent with restricted capabilities
tools: Read, Grep, Glob, Bash
---
```

> This example uses `disallowedTools` to inherit every tool from the main conversation
> except Write and Edit. The subagent keeps Bash, MCP tools, and everything else:

```yaml
---
name: no-writes
description: Inherits every tool except file writes
disallowedTools: Write, Edit
---
```

> If both are set, `disallowedTools` is applied first, then `tools` is resolved against the
> remaining pool. A tool listed in both is removed.

Both fields also accept MCP server-level patterns (`mcp__<server>` or `mcp__<server>__*`).

### The Agent/Task exclusion mechanism specifically (this is the load-bearing part for the cookbook's fix)

Verbatim, section "Restrict which subagents can be spawned":

> When an agent runs as the main thread with `claude --agent`, it can spawn subagents using
> the Agent tool. To restrict which subagent types it can spawn, use `Agent(agent_type)`
> syntax in the `tools` field.
>
> ```yaml
> ---
> name: coordinator
> description: Coordinates work across specialized agents
> tools: Agent(worker, researcher), Read, Bash
> ---
> ```
>
> This is an allowlist: only the `worker` and `researcher` subagents can be spawned. If the
> agent tries to spawn any other type, the request fails and the agent sees only the allowed
> types in its prompt. To block specific agents while allowing all others, use
> `permissions.deny` instead.
>
> To allow spawning any subagent without restrictions, use `Agent` without parentheses:
> `tools: Agent, Read, Bash`
>
> **If `Agent` is omitted from the `tools` list entirely, the agent can't spawn any
> subagents.**
>
> The `Agent(agent_type)` allowlist syntax applies only to an agent running as the main
> thread with `claude --agent`. **In a subagent definition, listing `Agent` in `tools` lets
> that subagent spawn nested subagents, but any type list inside the parentheses is
> ignored.**

This last paragraph is the critical scoping detail: for a subagent (which is what
Coder/Verifier/Test-writer/Researcher all are, dispatched by Oga), the fine-grained
`Agent(type1, type2)` allowlist syntax does not apply — only the main-thread agent gets that
granularity. But the **binary** control — omit `Agent`/`Task` from `tools`, or add it to
`disallowedTools` — works identically for subagent definitions and is exactly what's needed:
it makes the subagent **structurally unable to call the Agent tool at all**, which is a
strictly stronger guarantee than the binary "can it delegate" question the cookbook's fix is
actually trying to solve (none of loop-team's four worker roles need selective
sub-delegation to *specific* other types — they need zero delegation, period).

Also confirmed: `Task(...)` still works as a deprecated alias for `Agent(...)` (renamed in
v2.1.63).

### Registration: does creating the file make it dispatchable as a `subagent_type`?

Yes, automatically, once the file exists in a scanned location — no separate registration
step, plugin manifest, or `settings.json` entry required. Verbatim:

> Subagents are loaded at session start. If you add or edit a subagent file directly on
> disk, restart your session to load it. Subagents created through the `/agents` interface
> take effect immediately without a restart.

A subagent becomes selectable via: natural-language mention, `@`-mention
(`@agent-<name>`), or — most relevant for Oga — the ordinary `Agent` tool call. The docs
don't show the exact JSON Oga's `Agent` tool call would carry, but the mechanism by which
Claude Code exposes custom subagents to the dispatching model is the same one that already
surfaces `Explore`, `Plan`, `general-purpose`, and `statusline-setup` as options in Oga's own
system prompt (see "Available agent types for the Agent tool" block visible at the top of
this very session) — i.e., once `.claude/agents/coder.md` (etc.) exists, `Coder` would appear
in that same list with its own `(Tools: ...)` annotation, alongside the built-ins.

**This session cannot execute a live round-trip test** (create the file, restart, and watch
`Coder` appear as a selectable `subagent_type`) within a single non-interactive research
turn, since subagent files load at session start and a restart is required per the docs
above. That verification step is deferred to the Coder that implements this — see
Recommendation section.

---

## 2. Official documentation — sources

Primary sources, fetched verbatim 2026-07-02:

- **https://code.claude.com/docs/en/sub-agents** — "Create custom subagents." Full page
  fetched (1122-line cached copy). Sections used: "Built-in subagents," "Choose the subagent
  scope," "Write subagent files" → "Supported frontmatter fields," "Available tools,"
  "Restrict which subagents can be spawned," "Disable specific subagents," "Spawn nested
  subagents."
- **https://code.claude.com/docs/en/hooks** — Claude Code CLI hooks reference (shell-command
  hooks configured via `.claude/settings.json`, as distinct from the Agent SDK's
  `ClaudeAgentOptions` hooks). Confirms the `agent_id`/`agent_type` PreToolUse fields at the
  CLI-hooks layer specifically (see section 4 below).
- **https://code.claude.com/docs/en/agent-sdk/hooks** — Agent SDK hooks doc (raw
  `claude-agent-sdk` package, Python/TypeScript). Fetched for comparison; confirms the same
  `agent_id`/`agent_type` fields exist in the SDK's `HookInput` shape too, but this is NOT
  the surface loop-team runs on (loop-team runs inside interactive Claude Code CLI, not a
  custom SDK harness) — included only to rule out "maybe it's SDK-only."

Both `agent_id`/`agent_type` and the subagent frontmatter mechanism are confirmed **at the
Claude Code CLI layer**, which is the layer loop-team actually operates on. This directly
answers the dossier's implicit worry that `disallowed_tools`/`ClaudeAgentOptions` might be an
SDK-only feature not reachable from a CLI session — it is not SDK-only; the CLI has its own
equivalent (`tools`/`disallowedTools` frontmatter) that does the same job at the same
strength.

---

## 3. Could loop-team define 4-5 custom types (Coder, Verifier, Test-writer, Researcher, plan-check-Verifier), each tool-restricted, with Agent/Task excluded where appropriate?

**Yes.** Concrete, ready-to-use file contents below (not theory — these follow the exact
documented schema above and can be dropped into `~/Claude/loop/.claude/agents/` or
`~/.claude/agents/` as-is, modulo pasting each role's real system prompt body from
`~/Claude/loop/loop-team/roles/*.md`).

Design principle applied: **every worker role gets `disallowedTools: Agent` (blocking
delegation entirely), since none of loop-team's four dispatched roles are supposed to spawn
their own sub-agents** — this is precisely the punting failure mode in
`feedback_subagent_punting.md`. Only Oga itself (the main thread) needs `Agent` access, and
Oga is not itself a custom-subagent-type file — it's the interactive session.

### `~/Claude/loop/.claude/agents/coder.md`

```markdown
---
name: coder
description: Implements a spec against the loop-team writer/verifier loop. Dispatched by Oga; never spawns its own sub-agents.
tools: Read, Write, Edit, NotebookEdit, Bash, Grep, Glob
disallowedTools: Agent
model: inherit
---

<paste ~/Claude/loop/loop-team/roles/coder.md body here as the system prompt>
```

### `~/Claude/loop/.claude/agents/verifier.md`

```markdown
---
name: verifier
description: Independently verifies a Coder's implementation against the spec and acceptance criteria. Read-only plus test execution; never edits source and never spawns sub-agents.
tools: Read, Bash, Grep, Glob
disallowedTools: Agent, Write, Edit, NotebookEdit
model: inherit
---

<paste ~/Claude/loop/loop-team/roles/verifier.md body here>
```

### `~/Claude/loop/.claude/agents/test-writer.md`

```markdown
---
name: test-writer
description: Writes the test suite (including adversarial cases) for a spec before implementation exists. Never spawns sub-agents.
tools: Read, Write, Edit, Bash, Grep, Glob
disallowedTools: Agent
model: inherit
---

<paste ~/Claude/loop/loop-team/roles/test_writer.md (and/or adversarial_test_writer.md) body here>
```

### `~/Claude/loop/.claude/agents/researcher.md`

```markdown
---
name: researcher
description: Domain/platform/API research producing a cited brief or radar entry. Read/search/web only; never spawns sub-agents.
tools: Read, Grep, Glob, WebSearch, WebFetch, Bash
disallowedTools: Agent, Write, Edit, NotebookEdit
model: inherit
---

<paste ~/Claude/loop/loop-team/roles/researcher.md body here>
```

*(Note: this file gives Researcher `Write` for its Persistence rule — writing findings to
`~/Claude/loop/research/`. If the tool-restriction is meant to be strict read-only, swap in a
narrow allowlist instead of a denylist, e.g. `tools: Read, Grep, Glob, WebSearch, WebFetch,
Write` with no `Bash`/`Edit`/`Agent` at all — allowlist form is safer than denylist form when
the goal is minimum-necessary-privilege, since a denylist only blocks what's named while an
allowlist blocks everything not named.)*

### `~/Claude/loop/.claude/agents/plan-check-verifier.md`

```markdown
---
name: plan-check-verifier
description: Reviews a spec/plan BEFORE the Coder implements it, catching spec-level bugs (e.g. ordering, regex, edge-case gaps) that a post-hoc test suite would encode rather than catch. Read-only.
tools: Read, Grep, Glob
disallowedTools: Agent, Write, Edit, NotebookEdit, Bash
model: inherit
---

<paste plan-check role brief here — see feedback_plan_check_catches_spec_bugs.md for what this role does>
```

### Dispatch-time change required in `orchestrator.md`

Today (confirmed by grep above) Oga's dispatch pattern is: call `Agent` with
`subagent_type` left at a built-in default (or omitted, defaulting to `general-purpose`) and
paste the role brief into `prompt`. To actually make custom types take effect, Oga's
dispatch instructions need to additionally pass `subagent_type: "coder"` /
`"verifier"` / `"test-writer"` / `"researcher"` / `"plan-check-verifier"` — matching the
frontmatter `name` field — instead of (or in addition to) pasting the full role-brief text
into `prompt`, since the file's own body already becomes that subagent's system prompt. The
`prompt` field would then only need the task-specific delegation message (spec path, run
dir, context), not the entire role-brief boilerplate — which also shrinks Oga's per-dispatch
prompt size.

This is a real, scoped change to `orchestrator.md`'s "Dispatching means one thing" section
(lines ~233-255) plus each role's Agent-call template — not a fundamental rearchitecture. It
does NOT require touching `pre_tool_use_oga_guard.py` or any other hook; the two mechanisms
are complementary (tool-restriction prevents the call from ever succeeding; the hook is
a second, independent check already keyed on `agent_id`).

---

## 4. Hook-based interception (available today, already partially proven) — as a complement, not a substitute

Even though custom-agent-type tool-restriction is confirmed viable and is the *stronger*
mechanism (compile-time-equivalent: the tool literally isn't offered to the model, vs. a
hook that reactively denies an attempted call), the hook layer described in the question is
also real and already partly built, and should stay as defense-in-depth (it also covers
Bash-based workarounds and any future built-in role that isn't yet migrated to a custom
type).

Verbatim confirmation, `https://code.claude.com/docs/en/hooks`, on the exact schema
`pre_tool_use_oga_guard.py` (lines 179-181) already keys off empirically:

> **When running with `--agent` or inside a subagent, two additional fields are included:**
>
> | Field | Description |
> |---|---|
> | `agent_id` | Unique identifier for the subagent. Present only when the hook fires inside a subagent call. Use this to distinguish subagent hook calls from main-thread calls. |
> | `agent_type` | Agent name (for example, `"Explore"` or `"security-reviewer"`). Present when the session uses `--agent` or the hook fires inside a subagent. For subagents, the subagent's type takes precedence over the session's `--agent` value. For custom subagents, this is the `name` field from the agent's frontmatter, not the filename. For subagents shipped by a plugin, this is the plugin-scoped identifier such as `my-plugin:reviewer`, not the bare frontmatter name. |

This is an **exact, official confirmation** of the mechanism the memory
`pretooluse-agent-id-distinguishes-subagents` already proved empirically on 2026-07-02 (a
truthy `agent_id` in the PreToolUse payload identifies the caller as a dispatched
sub-agent). The two are now doubly verified: once by the guard script's own live behavior,
once by the docs.

A second, more targeted hook is also documented and directly applicable: a **`PreToolUse`
hook scoped in the subagent's own frontmatter**, matched on `Agent`, would fire specifically
when that subagent itself tries to call the Agent tool — belt-and-suspenders even if
`disallowedTools: Agent` were ever accidentally dropped from a future edit:

```yaml
---
name: coder
tools: Read, Write, Edit, Bash, Grep, Glob
disallowedTools: Agent
hooks:
  PreToolUse:
    - matcher: "Agent"
      hooks:
        - type: command
          command: "./scripts/deny_subagent_delegation.sh"
---
```

(This would be redundant with `disallowedTools: Agent` under normal operation — the tool
wouldn't be offered to the model at all — but a hook is a second, independent enforcement
layer if the frontmatter is ever misconfigured, matching this project's general
defense-in-depth pattern already used for `pre_tool_use_oga_guard.py`.)

**Project-level `SubagentStart`/`SubagentStop` hooks** (in `settings.json`, matched on agent
type name) are also documented and could log or gate on which custom subagent types actually
ran, for audit purposes — not needed for the core fix but worth knowing about for future
observability work.

---

## 5. Recommendation

**Custom-agent-type route — adopt it. It is the correct, load-bearing fix**, not the
hook-interception route, for the specific failure the cookbook flagged (a sub-agent using
Task/Agent despite a prompt-level instruction not to). Rationale:

- It is a **structural** guarantee (the tool is never in the model's available-tools list
  for that subagent), not a **reactive** one (a hook catching an attempted call after the
  model already decided to try it). This matches the same "prevent, don't just block"
  philosophy already used for `pre_tool_use_oga_guard.py`'s WORKER_TOOLS gate on Oga itself.
- It requires **no new hook code** — just 5 markdown files (following the concrete templates
  above) plus a scoped edit to `orchestrator.md`'s dispatch instructions to pass
  `subagent_type` matching each file's `name`.
- The existing `agent_id` hook mechanism (already built, already proven) stays in place
  unchanged as a second, independent layer — it doesn't need to change at all for this fix,
  since it already correctly identifies sub-agent-originated calls regardless of which
  subagent type made them.

**Estimated scope**: small. Creating 5 files (~15-30 min once role-brief bodies are pasted
in) + one edit to `orchestrator.md`'s dispatch section to add `subagent_type` to each Agent
call template (~15 min) + a live round-trip verification (dispatch each custom type once,
confirm via transcript/`agent_type` in a debug hook log that the right type and tool
restriction actually took effect — do NOT trust the docs alone here, per this project's
"verify against reality" standing rule). Total: well under an hour of Coder+Verifier time,
not a rearchitecture.

**One open item for the Coder who implements this**: confirm live (not just from docs)
that when Oga's `Agent` tool call sets `subagent_type: "coder"` matching a custom
`.claude/agents/coder.md`, the file's own frontmatter `tools`/`disallowedTools` is what
actually governs that invocation — the docs are unambiguous on this, but this research
session had no way to execute a session restart + live dispatch round-trip within one
non-interactive turn. This is the one claim in this brief that rests on documentation
alone rather than this session's own reproduction.

---

## Sources

- [Create custom subagents](https://code.claude.com/docs/en/sub-agents) — Claude Code Docs (primary; frontmatter schema, tool-restriction mechanism, `Agent(agent_type)` scoping caveat)
- [Intercept and control agent behavior with hooks](https://code.claude.com/docs/en/hooks) — Claude Code Docs (CLI shell-command hooks; `agent_id`/`agent_type` PreToolUse fields)
- [Intercept and control agent behavior with hooks](https://code.claude.com/docs/en/agent-sdk/hooks) — Claude Agent SDK docs (Python/TypeScript SDK hooks; used only for comparison, confirms same fields exist at SDK layer but this is not loop-team's runtime)
- `~/Claude/loop/hooks/pre_tool_use_oga_guard.py` (this repo) — existing, live implementation already keying off `agent_id` (lines 179-181)
- `~/Claude/loop/loop-team/orchestrator.md` (this repo) — current dispatch pattern (built-in `subagent_type` only, role brief pasted into `prompt`)
- Memory: `pretooluse-agent-id-distinguishes-subagents` — this project's own prior empirical proof, now corroborated by official docs
- Memory: `feedback_subagent_punting.md` — the failure mode this fix closes
