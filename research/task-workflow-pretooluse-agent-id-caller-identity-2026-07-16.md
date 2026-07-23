# Domain brief — does a "Task"-named (or Workflow-non-Coder) sub-agent's own PreToolUse payload carry a reliable agent_id, the way "Agent" and Codex already do?

**Mode:** D (domain research for a build). **Build:** `fix/oga-guard-caller-identity`
(`loop-team/runs/2026-07-15_oga-guard-caller-identity/specs/spec.md`, Revision 3). **Follow-up
to:** `research/codex-pretooluse-agent-id-caller-identity-2026-07-16.md` (same methodology).
**Date:** 2026-07-16. **Researcher scope note:** all reads/greps/web fetches below were done
directly, no sub-agent dispatched.

**Read this section before the rest — it changes what "the answer" even means right now:**
this exact mechanism is being actively, concurrently rewritten by a different build while this
brief was researched. `hooks/pre_tool_use_oga_guard.py` and `hooks/test_pre_tool_use_oga_guard.py`
are both `git status`-modified (uncommitted) on this exact branch (`fix/oga-guard-caller-identity`,
confirmed via `git branch --show-current`), and the code currently on disk does **not** match
Section C of the very spec this build is executing — it already reflects a **different, sibling
spec's** newly-landed mechanism (`H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`, `fix_plan.md:9299`,
"IMPLEMENTED 2026-07-16"). See Answer §0 for why this matters more than the literal Task/Workflow
question. All file:line citations below are pinned to the exact on-disk content at
`sha256(hooks/pre_tool_use_oga_guard.py) = bd06812ad1723d6e2cc687c37d4e43365f6314d848b745dbfe9cedd33abe063d`
and `sha256(hooks/test_pre_tool_use_oga_guard.py) = b5f5a8f1d9e6dd09f699cbdd9c4e71039dc127825107f7a75baa3162258009ef`,
verified stable across three separate checks during this research session (01:14:55, 01:22:52,
01:28:47 EDT); re-verify before relying on any line number if the file has moved again.

## Question

1. Does a genuinely-dispatched **"Task"-named** sub-agent's own follow-up Write/Edit/NotebookEdit/
   MultiEdit call carry a reliable top-level `agent_id`, the same signal already confirmed for
   "Agent"-named dispatches and for Codex?
2. Same question for a **"Workflow"-dispatched NON-Coder** sub-agent's own follow-up write call
   (Workflow-Coder is separately hard-denied elsewhere in this file, confirmed moot — see §4).

## Answer

### §0 — The finding that matters most: two different mechanisms are live right now, and they give opposite answers

`hooks/pre_tool_use_oga_guard.py`'s **caller-identity section has two candidate implementations
in play simultaneously**, and which one is "true today" depends on which you read:

- **The spec's own account of "today" (Revision 3, Section C, written 00:47:42 EDT today):**
  a simple, two-path mechanism — "Fast path (line 661): `if data.get("agent_id"): allow`" plus an
  Agent-name-only in-flight fallback. Section D **decides to keep this fast path unconditional**
  ("DECIDED: Option A only. Option B is rejected, not deferred" — Option B being exact in-flight
  matching). Under this design, the in-flight collector's blindness to `"Task"`/`"Workflow"` is
  **irrelevant to a sub-agent's own follow-up write**, because that call's own truthy `agent_id`
  allows immediately without ever consulting the collector — structurally identical to the Codex
  finding (spawn_agent's truthy `agent_id` never touches the collector either).
- **What is actually on disk right now** (hash-pinned above, `git status` confirms uncommitted):
  a stricter mechanism (comment header: `"--- Exact worker identity guard (structural PLAN_PASS
  evidence guard) ---"`, `hooks/pre_tool_use_oga_guard.py:653`) that requires the top-level
  `agent_id`/`task_id`/`dispatch_id` to resolve to an **active, same-session, unretired,
  write-capable** dispatch record (`WRITE_CAPABLE_ROLES = {"coder","test-writer","test_writer"}`,
  line 667) collected **exclusively** from transcript `tool_use` entries where
  `p.get("name") == "Agent"` literally (line 758). There is now only **one** occurrence of
  `data.get("agent_id")` in the whole file (line 872; grep-confirmed), and it feeds this exact-match
  resolver, not an unconditional allow.

  I traced this discrepancy to ground truth, not just noticed it: `git log --oneline -- hooks/pre_tool_use_oga_guard.py`
  shows the last **committed** change is `2a4f1b1`; nothing in that history mentions "Exact worker
  identity guard." `fix_plan.md:9299` explains it — `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1
  (IMPLEMENTED 2026-07-16, priority: HIGH)`, a **separate, sibling spec**
  (`loop-team/runs/2026-07-16_structural-planpass-evidence-guard/specs/spec.md`,
  `SPEC_SHA256=98227dc3570273a3f933b8d159942e0bfbfd8564ee32ea3a641f3ad20200df31`, its own 3-round
  plan-check in `loop-team/runs/2026-07-16_structural-planpass-evidence-guard/plan_check_log.md`)
  that closed a **different** gap (a bare `LOOP_GATE: PLAN_PASS` credit, with no evidence binding,
  wrongly authorizing Coder dispatches) by rebuilding this exact function. Its own spec (mtime
  00:40, before the caller-identity spec's 00:47:42 Revision 3) and its own 3-round plan-check
  **never once mention "Task" or "Workflow"** (grep-confirmed against both files) — it reused the
  pre-existing Agent-only collector as a foundation without auditing it for tool-name completeness,
  which is a second, independent instance of the same blind spot this brief was asked to check.
  `loop-team/runs/2026-07-15_oga-guard-caller-identity/trace.jsonl`'s last `role_dispatch` event
  timestamps at `2026-07-16T00:58:49` — 8 seconds before the hook file's own mtime (`00:58:57`) —
  consistent with a Coder dispatch actively working this exact file during this research window
  (`hooks/test_pre_tool_use_oga_guard.py`'s own mtime moved again to `01:12:25`, mid-investigation;
  see Constraints for the exact before/after test-name diff this caused).

  **Net effect on disk right now:** a Task-named or Workflow-non-Coder dispatch's own follow-up
  write is **structurally guaranteed to be denied** by the currently-live code — not because
  `agent_id` is unreliable, but because there is nothing in `dispatched` for
  `_resolve_agent_id`/`_resolve_task_or_dispatch_id` (lines 849, 859) to match against, and the
  legacy escape hatch (`LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1`, line 927) reuses the **same**
  Agent-only `in_flight_ids` set, so it cannot rescue a Task/Workflow dispatch either.

**Bottom line for Oga/the Coder:** the answer to "is the Task/Workflow gap moot?" is **"moot under
the spec you plan-checked; NOT moot under the code that is actually sitting in this worktree right
now, put there by a different, already-closed spec."** AC10's fix (recognize `"Task"` at the
collector) needs to be re-scoped against the version of the function that is actually going to
ship, not the one Section C describes — these are two different functions today.

### §1 — "Task": is it the same runtime mechanism as "Agent"? (yes, confirmed by official docs + this session's own version)

Official Claude Code SDK documentation, fetched live 2026-07-16
(`https://code.claude.com/docs/en/agent-sdk/subagents`, "Detect subagent invocation" section),
states verbatim:

> "The tool name was renamed from `"Task"` to `"Agent"` in Claude Code v2.1.63. Current SDK
> releases emit `"Agent"` in `tool_use` blocks but still use `"Task"` in the `system:init` tools
> list and in `result.permission_denials[].tool_name`. Checking both values in `block.name` ensures
> compatibility across SDK versions."

This directly confirms: **"Task" and "Agent" are the same dispatch primitive**, not two different
mechanisms — a rename, not a fork. The doc's own recommended practice ("check both values") is
exactly what this codebase's OTHER gates already do (lines 140, 278, 334, 355, 405) — the in-flight
collector at line 758 is the one place that never adopted it.

**This session's own installed version, checked directly, not assumed:** every event in this
session's own live transcript (`<HOME>/.claude/projects/-Users-eobodoechine/c9e6db97-7e2f-461f-8223-7474871fbc3d.jsonl`,
207 lines, 100% of them) carries `"version": "2.1.209"` — well past the v2.1.63 rename. `claude
--version` reports the separate CLI package version `1.0.117 (Claude Code)`
(`@anthropic-ai/claude-code@1.0.117` per `npm list -g`) — a different numbering scheme; the
protocol version quoted in transcripts (`2.1.209`) is the one the docs' version notes above use.

**What this means for the actual question:** on this installed runtime, a genuinely-dispatched
sub-agent's own dispatching `tool_use` entry — the thing the in-flight collector scans transcript
history for — is empirically expected to say `"Agent"`, not `"Task"`, in the overwhelming common
case. `"Task"` persists only in `system:init`'s tool listing and in
`result.permission_denials[].tool_name` — **neither of which is a `tool_use` block**, so neither
feeds the collector's `p.get("type") == "tool_use" and p.get("name") == "Agent"` check regardless
of whether that check also allow-listed `"Task"`. This means: **the specific scenario "a live,
current-runtime tool_use block literally named Task" is not the shape a real dispatch takes on
this machine's actual version today** — a materially different (and lower-risk) situation than the
dispatch's framing assumed. I could not find, and did not observe in `~/.loop-gate/oga_guard_debug.jsonl`
(see §3), a single real row structurally attributable to a live `"Task"`-named `tool_use` block.

**Caveat, stated plainly:** this project's own code (the five gates checking `"Agent","Task","Workflow"`
together, plus the existing regression test `test_task_named_dispatch_also_covered_and_never_blocks`,
`hooks/test_pre_tool_use_oga_guard.py:1210-1226`) treats `"Task"` recognition as a deliberate,
standing cross-compatibility policy, matching Anthropic's own documented advice to check both
names. `loop-team/orchestrator.md:577` independently states "In Cowork this is the Agent/Task
tool" — naming a **different product surface** (Cowork, not the Claude Code CLI this session runs
under) that this brief did not separately verify for its live tool-naming behavior. So: low
current bite on this exact CLI version, but not a claim that generalizes to every surface/version
this framework's hooks might ever run under — the policy of checking both names remains
defensible even though this session's own evidence shows `"Agent"` is what actually appears today.

### §2 — "Workflow" (non-Coder): structurally different execution context, not just a different name

Official docs (`https://code.claude.com/docs/en/workflows`, "How a workflow runs") state: "The
workflow runtime executes the script **in an isolated environment, separate from your
conversation**. Intermediate results stay in script variables instead of landing in Claude's
context." And: "No direct filesystem or shell access from the workflow itself | Agents read,
write, and run commands. The script coordinates the agents" — i.e., the actual Write/Edit calls
are made by the **spawned agents**, not the orchestrating script. Separately: "The subagents the
workflow spawns always run in `acceptEdits` mode and inherit your tool allowlist... **File edits
are auto-approved**" (same page, "Approve the plan before it runs").

This project's own prior research (`research/workflow-subdispatch-isolation-design-2026-07-03.md`,
§1f, read in full) independently confirms, from **84 real Workflow scripts extracted directly from
this machine's own session transcripts**: "each `agent()` call inside a `parallel()`/`pipeline()`
spawns a genuinely separate sub-agent process with its own transcript file under
`~/.claude/projects/.../subagents/workflows/wf_<id>/agent-<agentId>.jsonl`" — note the filename
itself embeds `agentId`, consistent with the runtime assigning each Workflow-spawned agent its own
identity, structurally parallel to (but a differently-shaped transcript path than) a plain
Agent/Task dispatch.

**What I could not confirm either way:** whether a Workflow-spawned agent's own tool calls fire the
**same registered PreToolUse hooks** a normal top-level session or Agent/Task sub-agent triggers.
Neither official doc page states this explicitly in either direction. The "isolated
environment... auto-approved" framing is consistent with hooks still firing (Claude Code's own
documented evaluation order has "hooks run first" as a stage logically prior to
accept/ask/deny-mode permission resolution — `https://code.claude.com/docs/en/agent-sdk/hooks`,
via WebSearch summary, not independently re-fetched verbatim — flagged as the one claim in this
brief sourced from a search summary rather than a directly-quoted page, per the honesty bar) — but
is equally consistent with a bulk/background execution path that bypasses session-level hook
registration for performance, since the docs explicitly optimize this path for "dozens to hundreds
of agents."

**Empirically, directly checked:** `~/.loop-gate/oga_guard_debug.jsonl`'s **entire history** (5,445
rows as of this check) contains **zero** rows whose `transcript_basename` matches the
Workflow-sub-agent shape (`^agent-.*\.jsonl$`, or containing `workflow`/`wf_` anywhere) — checked
by direct substring scan, not just the anchored regex, to rule out a shape mismatch. This is a
genuine, thoroughly-checked absence of evidence, not a shallow miss.

**Given the honest state of the evidence, I report this as inconclusive rather than picking a
side:** either (a) Workflow-spawned agents' tool calls never reach this specific
PreToolUse-registered hook at all (a structurally different gap than name-recognition — fixing
line 758 to recognize `"Workflow"` would do nothing), or (b) they do reach it, but no
Workflow-dispatched NON-Coder sub-agent has yet made a WORKER_TOOLS call in this project's
history (plausible: Workflow is documented and observed, per the 84-script survey, to be used
heavily for Verifier/Researcher-shaped fan-out work, which wouldn't hit `WORKER_TOOLS` at all).
I could not distinguish between these from the evidence available to me without either opening
other sessions' transcripts beyond what this dispatch authorized, or running a live, real Workflow
dispatch myself (out of scope for a Researcher — no sub-agent dispatch permitted in this mode).

### §3 — Empirical debug-log counts (same method as the Codex brief; here is what it can and cannot show)

`~/.loop-gate/oga_guard_debug.jsonl`, 5,445 total rows as of this check. Filtering to
Claude-Code-native rows (`tool != "apply_patch"`), with a **real UUID `session_id`** (excludes the
`""`/`test-*` synthetic probes) and a **non-`tmp*.jsonl` `transcript_basename`** (excludes this
session's own and prior pytest-run pollution — confirmed present: my own
`python3 -m pytest hooks/test_pre_tool_use_oga_guard.py -k "..."` run during this research added
220 fresh `tmp*.jsonl` rows under fixture session_ids like `identity-session`/`gac-session`, all
correctly excluded by this filter) leaves **1,882 real rows**, all timestamped **before** the
`H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1` mechanism landed (hook mtime `00:58:57` today) —
**zero real rows exist yet under the new, currently-live mechanism**, so there is no production
evidence at all for how it behaves against real traffic, only its own test suite.

Of those 1,882 (old-mechanism era):

| | count |
|---|---|
| `agent_id` present + `decision: allow` | 1,814 |
| `agent_id` present + `decision` NOT allow | 1 (explained below — not a real exception) |
| `agent_id` absent + `decision: allow` | 46 (the exact "unrelated in-flight agent excuses this edit" gap Section C names as "today's confirmed behavior," now closed by whichever mechanism ships) |
| `agent_id` absent + `decision` NOT allow | 21 |

The one "present but not allow" row (`ts` timestamp maps to `hooks/test_loop_stop_guard.py`,
`session_id: da3b431c-...`) has `agent_id` in its `payload_keys` (key present) but `decision:
"deny"` — consistent with the documented, deliberate empty-string-is-falsy edge case
(`test_empty_string_agent_id_treated_as_absent`, confirmed this exact test exists and passes) —
`payload_keys` records key **names**, not truthiness, so an empty-string `agent_id` still shows up
as "present" in this log by construction. Not a counter-example once traced.

**What this evidence cannot show, and I am not going to overclaim it does:** `_write_debug_row`
(`hooks/pre_tool_use_oga_guard.py:629-650`) logs `{ts, tool, file, decision, in_flight_ids,
session_id, transcript_basename, payload_keys}` — **there is no field recording the name of the
tool_use that originally dispatched the calling sub-agent.** For Codex, this didn't matter: Codex
has exactly one dispatch mechanism (`spawn_agent`), so every `apply_patch` row is unambiguously
attributable. For Claude Code-native rows, **`"Agent"`-dispatched and (if it ever occurred)
`"Task"`-dispatched sub-agents would produce byte-identical debug-log rows** — there is no way to
retroactively split the 1,814 "agent_id present + allow" rows by which literal tool_use name
spawned each one, from this log alone. Per §1, the live-tool-use-name evidence (this session's
own 2.1.209 transcript + the official rename doc) is what closes this gap for "Agent" vs "Task" —
not the debug log, which is name-blind by design.

### §4 — Workflow-Coder is confirmed moot, as the dispatch stated

`hooks/pre_tool_use_oga_guard.py:360-362`: `if _sb.is_coder_dispatch(_sb_tool): if
dispatch_tool_name == "Workflow": _sb_deny("Workflow Coder dispatch is unsupported in v1")` —
confirmed live via `hooks/test_pre_tool_use_oga_guard.py`'s
`test_workflow_coder_fails_closed_v1_even_with_reviewed_hash` and
`test_workflow_no_hash_coder_fails_closed_v1` (both passing, both asserting exactly this deny
reason string). This is a hard, unconditional deny before any agent_id/collector logic is ever
reached for that specific (Workflow, Coder) combination — correctly out of scope, as the dispatch
said.

## Sources (file:line or URL for every claim above)

- `hooks/pre_tool_use_oga_guard.py:140` — `if tool_name in ("Agent", "Task", "Workflow")` (dispatch_check-presence logger)
- `hooks/pre_tool_use_oga_guard.py:278` — `if dispatch_tool_name in ("Agent", "Task")` (repo-health classification; Workflow explicitly unsupported here per its own comment)
- `hooks/pre_tool_use_oga_guard.py:334,355,360-362` — spec-bound Verifier/Coder credit gate; `355`: Verifier hash-check scoped to `("Agent","Task")` only; `360-362`: Workflow-Coder hard deny
- `hooks/pre_tool_use_oga_guard.py:405` — `if tool_name in ("Agent", "Task", "Workflow")` (verifier hygiene/adjacency hard-deny)
- `hooks/pre_tool_use_oga_guard.py:539` — `WORKER_TOOLS = {"Write","Edit","NotebookEdit","MultiEdit","apply_patch"}`
- `hooks/pre_tool_use_oga_guard.py:653-667` — "Exact worker identity guard" comment block + `WRITE_CAPABLE_ROLES`
- `hooks/pre_tool_use_oga_guard.py:752-758` — `dispatched` dict, collector's `p.get("name") == "Agent"` literal-only match
- `hooks/pre_tool_use_oga_guard.py:831-867` — `_same_session`, `_resolve_agent_id`, `_resolve_task_or_dispatch_id`
- `hooks/pre_tool_use_oga_guard.py:872-925` — `top_agent_id`/`top_task_id`/`top_dispatch_id` resolution chain; single occurrence of `data.get("agent_id")` in the whole file is at line 872 (grep-confirmed)
- `hooks/pre_tool_use_oga_guard.py:927-933` — `LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK` escape hatch, reuses the same Agent-only `in_flight_ids`
- `hooks/test_pre_tool_use_oga_guard.py:1210-1226` — `test_task_named_dispatch_also_covered_and_never_blocks` (dispatch_check-presence gate only, NOT the agent_id/collector mechanism — confirmed by reading the test body directly)
- `hooks/test_pre_tool_use_oga_guard.py:2520-2551` — `_identity_dispatch_events` hardcodes `"Agent"` (line 2533) with no Task/Workflow parametrization; confirmed no sibling exists for Task/Workflow in `TestExactWorkerIdentityGuard` (2564+) or `TestInFlightSubAgentDetection` (315+) via direct grep of both class bodies
- `hooks/test_pre_tool_use_oga_guard.py:2425-2452` — `test_workflow_coder_fails_closed_v1_even_with_reviewed_hash`, `test_workflow_no_hash_coder_fails_closed_v1` (both passing; confirms §4)
- `loop-team/runs/2026-07-15_oga-guard-caller-identity/specs/spec.md` — Revision 3, in full; Section C ("confirmed present-day behavior," now stale per §0), Section D ("DECIDED: Option A only. Option B is rejected"), Section E (AC10, the Task-recognition fix), Section I (round-1/2 plan-check record naming the Task gap and the Codex KNOWLEDGE gap)
- `loop-team/runs/2026-07-15_oga-guard-caller-identity/trace.jsonl` — last `role_dispatch` at `2026-07-16T00:58:49`
- `fix_plan.md:9299` — `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1 (IMPLEMENTED 2026-07-16, priority: HIGH)`, the sibling build whose mechanism is what's actually on disk
- `loop-team/runs/2026-07-16_structural-planpass-evidence-guard/specs/spec.md` (mtime 00:40) and `.../plan_check_log.md` (3 rounds, PLAN_PASS at `spec_sha256=98227dc3...`) — read in full; zero mentions of "Task"/"Workflow" in either (grep-confirmed)
- `git log --oneline -- hooks/pre_tool_use_oga_guard.py` (run directly) — last commit `2a4f1b1`; `git status --short` shows the file modified/uncommitted; `git branch --show-current` → `fix/oga-guard-caller-identity`
- `fix_plan.md:833-849` — original H-LT6 "PROPER FIX DONE 2026-07-02" evidence ("57 vs 122 rows... real sub-agent PreToolUse payloads carry top-level agent_id/agent_type"); framed generically ("sub-agent"), not scoped to any specific dispatch-tool name — confirms the ambiguity described in §3
- `loop-team/orchestrator.md:577` — "In Cowork this is the Agent/Task tool"; `:579` — Workflow's `agent()` sub-dispatch primitive
- `research/workflow-subdispatch-isolation-design-2026-07-03.md` §1f (read in full) — 84 real Workflow scripts extracted from this machine's own transcripts; confirms each `agent()` call spawns a separate process with its own `.../subagents/workflows/wf_<id>/agent-<agentId>.jsonl` transcript
- `~/.loop-gate/oga_guard_debug.jsonl` (this machine, read live 2026-07-16; 5,445 total rows) — see §3 for the exact filter and counts; zero rows match the Workflow-sub-agent transcript-path shape (checked via anchored regex AND unanchored substring scan for "agent"/"workflow"/"wf_")
- This session's own live transcript, `<HOME>/.claude/projects/-Users-eobodoechine/c9e6db97-7e2f-461f-8223-7474871fbc3d.jsonl` (207 lines, 100% scanned) — `version: "2.1.209"` on every line; `isSidechain: false` on all `isSidechain`-bearing lines; zero occurrences of snake_case `session_id` anywhere (only camelCase `sessionId`) — this last fact is a separate, adjacent finding not required to answer the assigned question but flagged in Constraints since it bears on whether `_same_session()`/`_event_session_id()` (`hooks/pre_tool_use_oga_guard.py:719-725`) can ever match real transcript data at all
- `claude --version` (direct invocation, 2026-07-16) → `1.0.117 (Claude Code)`; `npm list -g` → `@anthropic-ai/claude-code@1.0.117`
- [`https://code.claude.com/docs/en/agent-sdk/subagents`](https://code.claude.com/docs/en/agent-sdk/subagents) — fetched live 2026-07-16, quoted verbatim in §1 ("Detect subagent invocation" section, the Task→Agent rename note)
- [`https://code.claude.com/docs/en/workflows`](https://code.claude.com/docs/en/workflows) — fetched live 2026-07-16, quoted verbatim in §2 ("How a workflow runs," "Approve the plan before it runs")
- [`https://dev.to/bhaidar/the-task-tool-claude-codes-agent-orchestration-system-4bf2`](https://dev.to/bhaidar/the-task-tool-claude-codes-agent-orchestration-system-4bf2) — fetched live; confirms "Task tool" is common informal naming in third-party writeups but contains no version/rename detail (secondary source, superseded by the official docs page for the actual claim)
- `https://code.claude.com/docs/en/agent-sdk/hooks` — **flagged, not independently re-fetched verbatim**: the "hooks run first, before accept/ask/deny resolution" claim in §2 comes from a WebSearch AI-generated summary of this page, not a directly quoted excerpt. Per this role's honesty bar this is marked as the one under-verified claim in this brief; it is not load-bearing for the bottom-line answer (§0), only for the secondary "could hooks still fire under acceptEdits" discussion in §2.

## Constraints

- **Everything in §0 is a snapshot**, hash-pinned at `bd06812a.../b5f5a8f1...`, stable across three
  checks (01:14:55, 01:22:52, 01:28:47 EDT) but **not committed** — a concurrent Coder session may
  change it again after this brief is saved. Re-verify the hash before treating any line number as
  current.
- The `_event_session_id()` finding (real transcripts use `sessionId`, camelCase; the function
  checks `session_id`, snake_case — `hooks/pre_tool_use_oga_guard.py:719-725`) is reported only as
  a Constraint, not a headline finding, because it is adjacent to (not squarely inside) the
  assigned question — it affects whether `_same_session()` can ever return `True` against a real
  transcript at all, for ANY dispatch-tool name, which is a broader concern than Task/Workflow
  recognition specifically. Confirmed from exactly one real session (this one, 207/207 lines
  camelCase, 0 snake_case) plus the source code itself (which is dispositive regardless of sample
  size — the key literally checked is `"session_id"`, never `"sessionId"`); I did not open any
  other session's transcript to get a second data point, per this role's data-access-scope limits
  (reading other sessions requires separate authorization this dispatch did not grant beyond "this
  session's own transcript").
- The debug-log methodology (§3) is identical to the Codex brief's, with the same scope disclosure:
  `~/.loop-gate/oga_guard_debug.jsonl` lives outside the repo tree but is treated as this
  mechanism's authoritative evidence source elsewhere in this project (`fix_plan.md:838, 5657`;
  `loop-team/learnings.md:591-594`, "harvest the session, don't just endure it").
- Running `python3 -m pytest hooks/test_pre_tool_use_oga_guard.py -k "..."` during this research
  (to establish ground truth per the dispatch's own instruction to check the test suite) added 220
  fresh rows to `~/.loop-gate/oga_guard_debug.jsonl` under synthetic fixture session_ids
  (`identity-session`, `gac-session`, `oga-session`, `session-B`, `message-session`, all
  `tmp*.jsonl` transcripts). These are correctly excluded by the real-row filter in §3 and are
  disclosed here rather than silently left in the log.
- The Workflow "not_found" in §2 is a genuine evidentiary gap, not a shallow one: I checked the
  entire debug-log history (not just recent rows), checked both an anchored and unanchored pattern
  for the expected transcript-path shape, and fetched the one official doc page most likely to
  settle it — none of that closed the question, so I am reporting it open rather than guessing.

## not_found

- Whether a Workflow-spawned agent's own tool calls fire the same registered PreToolUse hooks as a
  normal session/Agent-Task sub-agent — no official doc states this either way, and this
  project's own debug log has zero rows either confirming or ruling it out. A future check: run a
  real, minimal Workflow dispatch (`agent()` call inside a `script`) whose sub-agent attempts a
  `Write`/`Edit` on a `CODE_EXT`-matching path inside a loop-team-armed session, then inspect
  `~/.loop-gate/oga_guard_debug.jsonl` for a fresh row — this would settle it directly, the same
  way the Codex brief's natural experiment settled the Codex question, but requires a live
  dispatch this Researcher mode is not permitted to make itself.
- Whether "Cowork" (the other product surface `loop-team/orchestrator.md:577` names as also using
  "the Agent/Task tool") emits `"Task"` as its live, current `tool_use` name the way pre-v2.1.63
  Claude Code CLI did — not checked; out of scope for this brief's available sources (no Cowork
  session transcript was read, per data-access-scope limits, and no official Cowork tool-naming
  doc was found in the time available).
- Precisely how many, if any, of the 1,814 real "`agent_id` present + allow" rows in §3 were
  produced by a dispatch whose original tool_use was named `"Task"` rather than `"Agent"` —
  structurally unanswerable from `oga_guard_debug.jsonl` alone (the schema never records the
  dispatching tool's name; see §3). Closing this would require opening the specific session
  transcripts behind those rows, which is outside this dispatch's authorized scope (session_id
  correlation was authorized for methodology, not as a license to bulk-open historical
  transcripts — see this role's data-access-scope rule and the Persistence section of
  `researcher.md`).
- Whether `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`'s Coder was aware of the
  `oga-guard-caller-identity` spec's concurrent existence on the same file, or whether these two
  builds are meant to be reconciled by a human/Oga decision before either ships — this is a
  process question for Oga, not something a Researcher's file/log evidence can settle. Flagging it
  is the most actionable thing this brief can do; resolving it is not this brief's job.
