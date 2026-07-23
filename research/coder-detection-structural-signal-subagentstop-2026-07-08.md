# Can `PLAN_CHECK`'s Coder-detection be made structural instead of text-regex? (Mode D research)

**Date:** 2026-07-08
**Dispatched as:** Researcher, Mode D (domain/platform API research), no sub-agents spawned.
**Scope:** `loop_stop_guard.py`'s `_CODER_DETECT` false-positive class
(`H-STOPGUARD-SUBAGENTTYPE-ADJACENCY-SELFMATCH-1`, CLOSED/WON'T-FIX 2026-07-08, and the
still-OPEN `H-GUARD-CODER-DETECT-SELFQUOTE-1`, filed 2026-07-03) — both in
`<HOME>/Claude/loop/fix_plan.md`. Question: is a genuine STRUCTURAL/BEHAVIORAL
signal (what tools a dispatched sub-agent actually called) available to replace or
supplement the current full-text regex scan of the dispatch prompt?

**Bottom line up front:** **Yes — a genuine structural signal exists, is already wired into
this exact codebase for a materially identical problem (`H-SUBAGENT-COMMIT-GATE-1`), and can
be extended to close the self-quote false-positive without reopening the three previously-
defeated bypass classes.** But it has one real, disclosed architectural gap (backgrounded/
still-running sub-agents), and I found one live, unresolved ambiguity in the *existing*
mechanism's own correctness that should be verified empirically before anything is built on
top of it. Both are documented below with evidence, not asserted.

---

## 1. What data does a Claude Code hook actually receive? (official docs + live empirical check)

### 1a. Official docs — common fields, subagent-specific fields

Two different hook systems exist and must not be conflated:
- **Claude Agent SDK hooks** (`code.claude.com/docs/en/agent-sdk/hooks`) — programmatic,
  TypeScript/Python, registered via `ClaudeAgentOptions`. Not what this project uses.
- **Claude Code CLI hooks** (`code.claude.com/docs/en/hooks`) — shell-command hooks
  registered in `~/.claude/settings.json`. **This is what `loop_stop_guard.py` and
  `subagent_stop_gate.py` actually use** — confirmed by direct read of
  `<HOME>/.claude/settings.json` (already quoted in full in this project's own
  `research/loop-stop-guard-misfire-dossier-2026-07-08.md`, section 4):

```json
"SubagentStop": [
  { "hooks": [ { "type": "command", "command": "python3 '<HOME>/Claude/loop/hooks/subagent_stop_gate.py'" } ] }
]
```

Quoted verbatim from `code.claude.com/docs/en/hooks` (fetched directly, not paraphrased):

> **Common fields (all events):** `session_id`, `prompt_id`, `transcript_path` — "Path to
> conversation JSON. The transcript file is written asynchronously and may lag the
> in-memory conversation... Hooks that need the final assistant text of the current turn
> should use `last_assistant_message` on Stop and SubagentStop instead of reading the
> transcript" — `cwd`, `permission_mode`, `effort`, `hook_event_name`.
>
> **Additional fields for subagent contexts** — "When running with `--agent` or inside a
> subagent, two additional fields are included:
> `agent_id` — Unique identifier for the subagent. Present only when the hook fires inside
> a subagent call. Use this to distinguish subagent hook calls from main-thread calls.
> `agent_type` — Agent name... For custom subagents, this is the `name` field from the
> agent's frontmatter, not the filename."

This directly resolves a real, documented ambiguity: **GitHub issue
[anthropics/claude-code#7881](https://github.com/anthropics/claude-code/issues/7881)**
("SubagentStop hook cannot identify which specific subagent finished due to shared session
IDs") shows a payload with only `hook_event_name`/`session_id`/`transcript_path`/
`stop_hook_active` — no `agent_id` at all — and argues this makes per-subagent tracking
impossible. **The current official docs and this project's own live runtime both show
`agent_id` IS present today** (see 1b). Either the issue predates `agent_id`'s addition, or
it was filed against a code path that doesn't populate it; either way, **it is not the
current state of this project's runtime** — treat the issue as historical context, not a
live blocker.

### 1b. Empirical confirmation — real, current-session evidence (not inferred)

Per this Researcher role's data-access rule, reading local transcripts required explicit
authorization; the dispatching prompt explicitly granted it ("look at real transcript files
under `~/.claude/projects/`... to see whether nested/sub-agent tool-use records actually
appear anywhere in a retrievable form"). Findings, quoted from real files:

**`~/.loop-gate/subagent_gate_debug.jsonl`** (written by `subagent_stop_gate.py` on every
real `SubagentStop` firing) has thousands of real lines like:
```
{"ts": 1783513815.5134022, "session_id": "22cbd4f2-9f8e-47a7-b8f3-910ea048d275", "agent_id": "a92e66c77e6019a07", "cwd": "<HOME>", "last_line": "No sub-agents were spawned during this dispatch.", "wrote_flag": false}
```
`agent_id` is populated on every single line — confirmed for dozens of distinct sessions and
timestamps, not a one-off. This is direct, current, on-disk proof that `agent_id` is a real,
reliable field in this project's actual Claude Code runtime (build `1.0.117`, transcript
`"version": "2.1.202"`).

**Per-subagent transcript files exist on disk, separate from the parent session file.**
`~/.claude/projects/-Users-eobodoechine/22cbd4f2-9f8e-47a7-b8f3-910ea048d275/subagents/`
contains one `agent-<agentId>.jsonl` + one `agent-<agentId>.meta.json` per dispatched
sub-agent (34 files present at inspection time). For a real, identifiable dispatch (agent_id
`a92e66c77e6019a07`, a Coder dispatch that did the `H-STOPGUARD-...` round-4 revert):

```
$ cat agent-a92e66c77e6019a07.meta.json
{"agentType":"coder","description":"Revert coder-detection to safe full-text scan","toolUseId":"toolu_01MrSp4nVYVjMD13gy8c7Tea","spawnDepth":1}
```

That `agentType` field is **Claude Code's own ground-truth record of which subagent_type
string the Task/Agent tool call declared** — independent of what the dispatch prompt's text
says. The `toolUseId` field is the **exact correlating ID** back to the parent session's own
tool_use block. Confirmed by grepping the parent session file
(`22cbd4f2-9f8e-47a7-b8f3-910ea048d275.jsonl`) for that literal string:

```python
# found in the PARENT transcript:
tool_use.id == "toolu_01MrSp4nVYVjMD13gy8c7Tea"
tool_use.name == "Agent"
tool_use.input == {"description": "Revert coder-detection to safe full-text scan",
                    "subagent_type": "coder", "run_in_background": ..., "prompt": ...}
```

And the per-agent transcript file itself (`agent-a92e66c77e6019a07.jsonl`, 162 lines)
contains the sub-agent's **own real tool_use blocks** — `type: "tool_use"` entries for
`Read`, `Edit`, `Bash`, etc. — with `isSidechain: true` and an `agentId` field on every
entry, distinguishing them structurally from main-thread entries. **This is exactly the data
the research question asked whether existed: a dispatched sub-agent's own tool-use history,
retrievable from disk/transcript, not just the top-level dispatch's `tool_use.input`
(description/prompt).**

`loop_stop_guard.py` already has the correlating-ID extraction pattern it would need
(`_tu.get("id") or _tu.get("tool_use_id")`, used today at lines 930 and 1102 for a different
gate) — the mechanism to tie a parent-turn `Agent`/`Task` tool_use to its sub-agent's own
record is not new engineering; the pattern is already in this file.

### 1c. One open, unresolved empirical ambiguity — disclosed, not swept under the rug

Not every case I checked was this clean. For a **different** session
(`5976abda-2612-4f62-b897-8c473a5ad5d1`), a `.commit_violation` flag exists on disk
(`~/.loop-gate/5976abda-2612-4f62-b897-8c473a5ad5d1_a47eb9cab33e1a95a.commit_violation`,
content `[{"sha": "b3d7393", "touched": ["loop-team/session_handoff_2026-07-08.md"]}]`) —
i.e. `subagent_stop_gate.py`'s existing `H-SUBAGENT-COMMIT-GATE-1` mechanism fired for real,
for agent_id `a47eb9cab33e1a95a`. I traced the actual `git commit` Bash call that produced
that SHA in the **top-level** session transcript (`5976abda...jsonl`, line 71) — but that
entry is tagged `isSidechain: False` with **no `agentId` field at all**, i.e. it reads as a
**main-thread** action, not a sub-agent's. The debug log's own `cwd` for that firing
(`<HOME>/Claude/Projects/taxahead`) matches the commit's `cd` target, so the
*agent_id* itself is plausibly real and scoped correctly — but I could not find `a47eb9cab33e1a95a`'s own
`subagents/agent-*.jsonl` file anywhere under `~/.claude/projects/` (only 3 sub-agent files
exist under that session, none matching this ID) — consistent with it being a **nested**
sub-agent (`spawnDepth` 2, a sub-agent's own sub-agent) whose transcript lives one level
deeper than I checked, or consistent with a genuine scoping gap in what `transcript_path`
resolves to for that particular `SubagentStop` firing. **I could not conclusively resolve
this** — `subagent_stop_gate.py` does not currently log the raw `transcript_path` value it
received (only `session_id`/`agent_id`/`cwd`/`last_line`/`wrote_flag`), so there is no
retained evidence to settle it after the fact.

**Actionable, cheap recommendation independent of everything else in this dossier:** add
`transcript_path` to the fields `subagent_gate_debug.jsonl` already logs. This turns an
unresolved ambiguity into a one-line, self-instrumenting empirical check on the very next
real `SubagentStop` firing, with zero new mechanism required — directly answers "is the file
`subagent_stop_gate.py` reads always correctly scoped to just the completing sub-agent, or
does it sometimes return the full parent session transcript" before anything new is built on
top of `transcript_content`.

---

## 2. Every hook event type, and which one(s) see inside a dispatched sub-agent's own run

Full table, quoted verbatim from `code.claude.com/docs/en/agent-sdk/hooks`'s "Available
hooks" section (the CLI hooks reference lists the same event set; this table is the clearest
verbatim source):

| Hook Event | What triggers it |
|---|---|
| `PreToolUse` | Tool call request (can block or modify) |
| `PostToolUse` | Tool execution result |
| `PostToolUseFailure` | Tool execution failure |
| `UserPromptSubmit` | User prompt submission |
| `Stop` | Agent execution stop |
| `SubagentStart` | Subagent initialization |
| **`SubagentStop`** | **Subagent completion** |
| `PreCompact` | Conversation compaction request |
| `PermissionRequest` | Permission dialog would be displayed |
| `Notification` | Agent status messages |
| ...(TS-only: `PostToolBatch`, `MessageDisplay`, `SessionStart`, `SessionEnd`, `Setup`, `TeammateIdle`, `TaskCompleted`, `ConfigChange`, `WorktreeCreate`, `WorktreeRemove`) | |

**`SubagentStop` is the answer to research question 2** — it is a hook event distinct from
`Stop`, fires specifically when a dispatched sub-agent finishes, and (per section 1)
delivers `agent_id` + a `transcript_path` that (in the confirmed-good case, section 1b) is
scoped to that sub-agent's own conversation, including its own real tool_use history.

**`PreToolUse`/`PostToolUse` on the Task/Agent tool itself do NOT see inside the
sub-agent's run** — per the docs' own "Recursive hook loops with subagents" troubleshooting
note and this project's own confirmed behavior, a `PreToolUse` firing on an `Agent`/`Task`
tool_use only ever sees that tool_use's OWN `tool_input` (description/prompt/subagent_type)
— the same surface `_tu_dispatch_text()`/`_CODER_DETECT` already scan today. There is no
hook that fires mid-flight, inside a sub-agent's own turns, and reports back to the parent's
`PreToolUse`/`PostToolUse`. The only point of visibility into what the sub-agent actually
did is **after it finishes**, via its own `SubagentStop` firing (or, as this project already
does, by later reading its now-complete per-agent transcript file from disk).

**This is directly analogous to, and already precedented by, H-LT6** (the earlier
"PreToolUse oga-guard blocking Coder sub-agent edits" gate, fixed by finding that
`PreToolUse` payloads carry a real structural `agent_id` field — see
`pretouluse-agent-id-distinguishes-subagents.md` memory) — i.e. this project has *already*
solved a structurally identical "can't tell who really did this" problem once, by finding
and using a real runtime field instead of a text heuristic, for a different gate in the same
file family.

---

## 3. TDD Guard's actual mechanism — a load-bearing correction to this project's own prior-art citation

`fix_plan.md`'s `H-GUARD-6` entry and `research/hguard6-stop-hook-verifier-gate-prior-art-2026-07-02.md`
both cite TDD Guard (`nizos/tdd-guard`) as proof that "structural, file_path glob, never
content" is the state of the art:

> "TDD Guard (nizos/tdd-guard) does candidate (a) via a file_path glob allowlist (never
> content)"

**This is a mischaracterization of TDD Guard's core mechanism, confirmed by reading the
actual source code (not the docs, which are genuinely sparse about this).** I fetched the
repo directly (`github.com/nizos/tdd-guard`, MIT license, 2,247 stars, last push
2026-07-06 — 2 days before this research, actively maintained, though its own README now
says "TDD Guard grew into [Probity]... New projects should start there. TDD Guard remains
maintained" — a maturity/succession flag worth noting).

**The file_path glob (`docs/ignore-patterns.md`) is real, but it is only a pre-filter** —
which files get checked *at all* (skips `*.md`, `*.json`, `*.yml`, etc. entirely). **The
actual TDD-compliance judgment, for files that ARE checked, is made by an LLM call**, quoted
directly from `docs/validation-model.md`:

> "TDD Guard validates changes using AI." Model options include the Claude Agent SDK
> (default, "uses your Claude Code subscription") or the Anthropic API directly, with a
> configurable model (`claude-sonnet-4-6` default, `claude-3-5-haiku-20241022` fastest,
> `claude-opus-4-1` most capable).

And confirmed directly in source, `src/validation/validator.ts` (quoted verbatim):

```ts
export async function validator(
  context: Context,
  modelClient: ModelClient = new ClaudeCli()
): Promise<ValidationResult> {
  try {
    const prompt = generateDynamicContext(context)
    const response = await modelClient.ask(prompt)
    if (!response) {
      return block('No response from model, try again')
    }
    return parseModelResponse(response)
  } ...
```

`response` is parsed for a JSON `{"decision": "block"|null, "reason": "..."}` — i.e. an
actual Claude model call judges the diff/context and returns a structured block/allow
decision. The hook registration itself (`plugin/hooks/hooks.json`, quoted verbatim) confirms
`PreToolUse` scoping by **tool name only** (`"matcher": "Write|Edit|MultiEdit|TodoWrite"`),
not by content — the content-based part is entirely inside the LLM-judged validator step,
reached only for files that pass the ignore-glob and aren't the fast structural
"exactly one test added" auto-allow (`src/hooks/processHookData.ts`'s
`isAllowedTestAddition`/`countAddedTests`, which does deterministically parse the diff for
test-definition counts as a cheap short-circuit — this part genuinely is structural/
content-parsing, but it's a narrow "skip the LLM call" fast path, not the mechanism that
decides violations).

**Correction to carry forward:** TDD Guard is not evidence that "content-blind, path-only"
detection is sufficient or best-practice for this class of problem. It is, if anything,
evidence of the opposite: **a 2,200+-star, actively-maintained, purpose-built TDD-enforcement
tool for Claude Code, after presumably iterating on simpler heuristics, ships with an actual
LLM-judgment call as its core violation-detection mechanism**, using structural signals
(tool-name matcher, file-path ignore-glob, a narrow diff-based fast path) only to decide
*whether to invoke it*, not to *replace* it. This is directly relevant to this project's own
`H-STOPGUARD-...` closure note, which named "an actual LLM-based semantic classification
step (at real latency/cost, and itself needing its own adversarial hardening)" as the only
remaining untried mechanism after three regex-based rounds failed — TDD Guard is real,
shipped, non-hypothetical proof that this exact pattern is viable in the Claude Code hook
ecosystem, not just a theoretical fallback.

**Transfer-condition check (per this role's standing requirement):**
- (a) Execution context TDD Guard's mechanism requires: a `PreToolUse` hook that can invoke
  a live Claude model call synchronously and block on its structured response, before the
  tool executes.
- (b) Does this project's context satisfy it? Yes — `hooks/loop_stop_guard.py` already runs
  as a synchronous shell-command hook with network/subprocess access; nothing structurally
  prevents an equivalent `ClaudeCli`-style call. The cost is real added latency (an LLM
  round-trip per gated dispatch) and the new adversarial-hardening burden the closure note
  already flagged — this is a genuinely different, heavier mechanism than the one
  recommended in section 5 below, not a drop-in.
- (c) Is the guarantee structural or instructional? For TDD Guard: **the pre-filter (which
  files get checked) is structural** (tool-name matcher, path glob — deterministic, cannot be
  talked around by the diff's content). **The actual violation verdict is instructional
  in the sense that it depends on an LLM correctly judging intent from a prompt** — i.e. it
  is a semantic judgment, not a hard guarantee; TDD Guard itself is therefore not immune to
  the class of failure this project has been fighting (a sufficiently adversarial diff could
  in principle fool the judge model), it has just moved the judgment from a *cheap, static
  regex* to a *more capable, still-fallible model call*.

---

## 4. Other prior art for "verify actual sub-agent behavior vs. self-reported role"

- **This project's own `H-SUBAGENT-COMMIT-GATE-1`** (`subagent_stop_gate.py`, "Fourth
  responsibility") is itself the closest and most relevant prior art, and it is **already
  built, registered, and has fired for real** (section 1c's flag). It reads a completing
  sub-agent's own transcript, extracts its `tool_use`/`tool_result` structurally (same idiom
  as `loop_stop_guard.py`'s own turn-parsing), and calls a shared, importable
  `find_commit_scope_violations()` against the sub-agent's own Bash calls — looking for a
  raw `git commit` that bypassed the required re-diff step. This is precisely "verify actual
  behavior (a real Bash tool_use with `git commit` in it) rather than trust a label," already
  proven out in this exact codebase for a structurally identical class of problem (an
  orchestrator needing to gate a worker's allowed action class based on more than a
  self-reported label).
- **This project's own `H-LT6`** (PreToolUse oga-guard, `agent_id`-based fix) — same lesson,
  different gate: "the eventual fix for a similarly-shaped 'can't tell who really dispatched
  this' problem in this same hooks/ directory *was* to find and use a real structural signal,
  once one was confirmed to exist in the runtime payload" (quoted from this project's own
  `research/loop-stop-guard-misfire-dossier-2026-07-08.md`, section 3).
- **Academic**: "From Agent Traces to Trust: A Survey of Evidence Tracing and Execution
  Provenance in LLM Agents" (arXiv 2606.04990, fetched abstract). Quoted: "Final-answer
  accuracy alone cannot explain how an output was produced, which evidence supported each
  claim, whether tool calls were justified... or where failures originated." The survey
  frames "execution provenance as the typed graph of an agent execution," explicitly
  distinguishing verification grounded in the actual action sequence from verification
  grounded in a claimed/declared role or intent — the same distinction this dossier is
  drawing. This is general framing/validation of the *principle*, not a drop-in mechanism
  for Claude Code specifically — flagged as `RESEARCH_ONLY`/context, not an implementation
  source.
- **Multi-agent orchestration surveys** (MindStudio, Arize, Microsoft Learn — general
  web search, not deeply fetched) describe judge/validator sub-agents scoring worker
  *output* quality (schema conformance, factual consistency), not the specific "did the
  worker's actual tool-call sequence match its declared role" problem this dossier targets.
  No other concrete, fetchable open-source implementation of exactly this pattern (worker
  role-vs-behavior mismatch detection via tool-use auditing) was found outside TDD Guard and
  this project's own `H-SUBAGENT-COMMIT-GATE-1`. Reported honestly as a gap, not padded.

---

## 5. Concrete design sketch — what PLAN_CHECK would need, and whether it's architecturally feasible

**Feasible, with the shared-state-file bridge this project already uses for exactly this
purpose.** Hooks are separate process invocations (confirmed: `loop_stop_guard.py` runs as
a distinct `python3` subprocess per `Stop` event; `subagent_stop_gate.py` runs as a distinct
subprocess per `SubagentStop` event — no shared memory). This project's own `Layer 1`
flag-file bridge (`loop_stop_guard.py` lines 122-296, reading
`{session_id}_{agent_id}.commit_violation` files written by `subagent_stop_gate.py`) is
**exactly this pattern, already shipped**, for a different violation type. Extending it:

1. **`subagent_stop_gate.py` gains a fifth responsibility**: on every `SubagentStop` firing,
   extract this sub-agent's own `tool_use` entries from its `transcript_content` (same
   extraction idiom already used for the commit-scope scan) and check whether any is a
   `Write`/`Edit`/`MultiEdit` call whose `file_path` matches the *already-defined, already-
   hardened* `_RH_CODE_EXT`/`_rh_structural_writes()` "feature code" extension set from
   `loop_stop_guard.py` (realpath-resolved, symlink-safe, with the existing tmp/settings
   exemptions reused verbatim — not reinvented). If any match, write a
   `{session_id}_{agent_id}.coder_behavior` flag (existence-only, mirroring
   `.verifier_pass`'s empty-content convention).
2. **`loop_stop_guard.py`'s PLAN_CHECK gate gains a structural check**, glob-matched exactly
   like the existing `.verifier_pass`/`.commit_violation` flags (session-scoped, TTL-bounded,
   non-consuming).
3. **Timing/ordering — why this works for the common case.** A Task/Agent tool_use is a
   normal synchronous tool call: the parent's turn cannot continue past it until a
   `tool_result` is delivered, and the sub-agent's own completion (including its
   `SubagentStop` firing) happens *inside* that tool call's execution, before the
   `tool_result` returns. This is exactly the ordering guarantee the existing Layer-1 gate's
   own code comments already state and rely on ("the only way Oga... learns a sub-agent's raw
   commit ever happened"). Confirmed circumstantially: the `Agent`/`Task` tool schema itself
   exposes a `run_in_background` boolean (found in the real tool_use input at section 1b) —
   its mere existence as an opt-in flag implies the *default* mode is synchronous/blocking.
4. **Timing gap — the one real, disclosed architectural limitation.** For a
   `run_in_background: true` dispatch, the sub-agent may still be running when the parent's
   own `Stop` hook first fires — no `.coder_behavior` flag exists yet, and (unlike the
   commit-violation gate, which only needs to catch a violation *eventually*, on any later
   `Stop`) a plan-check gate that's supposed to block *this* turn cannot safely infer "no
   flag yet = no Coder work happened" for a still-running background dispatch — that would
   be a genuine, exploitable false-negative (a live "act as Coder, implement this now, and
   background it" dispatch would sail through on the very turn it's issued). **This is why
   the structural signal must be additive, not a replacement**, for backgrounded dispatches:
   keep the existing text-based `_CODER_DETECT` scan as the fail-safe/conservative layer for
   anything not yet structurally confirmed one way or the other, and use the structural flag
   only to **suppress a text-regex match when there is positive, confirmed evidence the
   matched dispatch has *already completed* and demonstrably did NOT write feature code** —
   never to suppress a match for a dispatch whose completion status is unknown. Confirming
   "has completed" needs its own signal (e.g. `subagent_stop_gate.py`'s existing
   `trace.jsonl` `role_dispatch` event, or a new completion marker) correlated by `agent_id`
   to a Task/Agent tool_use's own `id` in the current turn (the exact ID pattern already used
   at `loop_stop_guard.py` lines 930/1102, and empirically confirmed correlatable via the
   `.meta.json` `toolUseId` field in section 1b).
5. **Why this closes the false-positive AND doesn't reopen the three defeated bypasses.**
   Rounds 1-3 (`_NON_CODER_ROLES`, `_coder_detect_live_signal`) all tried to suppress a text
   match using signals available **before** the sub-agent runs — a caller-supplied
   `subagent_type` string, or marker-phrase proximity in the dispatch prompt's *text* — both
   are things a dispatch can construct however it likes, independent of what the sub-agent
   actually does once running. The mechanism above suppresses using a signal available
   **after** the sub-agent has verifiably finished and demonstrably not called Write/Edit on
   a feature file — this cannot be spoofed by prompt phrasing, because it doesn't read the
   prompt at all; it reads what tool calls the completed sub-agent's own session actually
   contains. Symmetrically, the round-3 bypass (claim `subagent_type: "researcher"`, but the
   prompt is a live "implement this now" directive) is *also* caught by this same mechanism,
   for free: if that dispatch actually calls `Edit`/`Write` on a feature file (which is what
   made it a real bypass concern in the first place), the `.coder_behavior` flag fires
   regardless of the claimed `subagent_type` — this is a genuinely different axis from
   anything tried in rounds 1-3, not a fourth iteration of the same regex arms race.

**Complexity/cost, stated honestly:** this is real, non-trivial engineering — a new
`subagent_stop_gate.py` responsibility, a new flag convention, a new completion-tracking
correlation in `loop_stop_guard.py`, and (per section 1c) a pre-flight empirical check on
whether `transcript_path` is reliably sub-agent-scoped before trusting it for a
plan-check-blocking decision (higher stakes than the existing commit-violation gate, which
only needs Oga's *attention*, not a hard block). This is squarely a `TESTABLE`-tier proposal
needing its own mini-spec + plan-check + adversarial round (per this project's own process),
not a same-turn patch.

---

## 6. Honest answer to "is there a lighter-weight targeted text fix instead"

**Not recommended as a standalone fix, and here's the falsifiable reason why**, per the
research brief's own suggested probe ("is the match inside a code-fence/quoted block"):
I checked the actual trigger text from both real false-positive incidents against this idea.

- `H-STOPGUARD-...` Misfire-1's trigger: `"...e.g. \"role: coder for <task>\"...", "including roles/coder.md..."` — **not** inside a markdown code fence (backtick-quoted inline, not a fenced block) in the reported incident text, and the round-3 marker-phrase mechanism (which specifically targeted "is this a future/contextual mention") was *independently, adversarially proven bypassable* using ordinary prose with no code fence involved at all (`"role: coder for the auth-flow fix. Read roles/coder.md. Implement the change directly right now..."` — a live directive, no fence, no quote marks).
- `H-GUARD-CODER-DETECT-SELFQUOTE-1`'s trigger: quoting `orchestrator.md`'s `dispatch_check`
  JSON schema block verbatim, which **is** typically inside a code fence or JSON literal in
  the dispatch prompt — a code-fence heuristic might catch *this specific* incident, but
  round-3's own adversarial finding (a live directive phrased in plain prose, no fence) shows
  the general marker-detection approach — of which "inside a fence" is just one more marker —
  is still gameable by construction, in either direction (a genuine live directive could be
  pasted inside a code fence for a legitimate reason — e.g. "run this exact command block" —
  and get wrongly suppressed; a bypass attempt can simply not use a fence).

**Honest conclusion: a code-fence/quote-proximity heuristic is the same arms race with a
different regex, not a genuinely different signal — it is vulnerable to the identical
"finite text-pattern list vs. adversarial or creative phrasing" failure mode that sank
rounds 1-3**, for the same reason articulated in this project's own closure note: "is this
text a live directive or a future/contextual mention" is a semantic judgment a finite pattern
list cannot reliably make. It is a *marginal* improvement over the marker-phrase list only in
that legitimate live directives are rarer inside code fences than in prose — worth doing as a
narrow, disclosed, best-effort refinement **on top of** the accepted-tradeoff conservative
scan (catches the specific SELFQUOTE-1 incident shape cheaply) — but it should not be sold as
"solving" the false-positive class, and it does nothing for the round-3 bypass direction at
all (a fence-based heuristic only ever *suppresses*, so it cannot also close a bypass the way
the structural signal in section 5 does both directions at once).

**Recommendation, ranked:**
1. **Primary, if the team wants to actually close this class (not just patch one incident):**
   pursue the structural `SubagentStop`-based signal in section 5. It is the only option
   surveyed that is a *genuinely different axis* (post-hoc verified behavior, not pre-hoc
   claimed intent/label) rather than a fourth round of the same text-pattern arms race, and
   it reuses machinery (`subagent_stop_gate.py`, `_RH_CODE_EXT`, the flag-file bridge
   pattern, the `id`/`toolUseId` correlation) already built and partially proven in this
   exact codebase. Needs: the `transcript_path` pre-flight check (section 1c), a completion-
   correlation design for the timing gap (section 5 point 4), and its own mini-spec + PACE-
   style plan-check before landing, per this project's standing process for a change to its
   own gate surface.
2. **Cheap, narrow, honest interim patch for the specific `SELFQUOTE-1` incident shape only**
   (quoting `orchestrator.md`'s own schema block verbatim): a code-fence/JSON-literal-
   proximity exclusion, explicitly documented as "closes this one incident shape, does not
   close the general false-positive class, does not affect the round-3 bypass direction at
   all." Do not present it as a fix for the whole class.
3. **If neither is pursued:** the current, permanent, user-approved tradeoff (full-text scan,
   accepted false positive, `subagent_type == "coder"` as the only additive-safe signal) —
   already CLOSED/WON'T-FIX for `H-STOPGUARD-...` — remains the honest default, and
   `H-GUARD-CODER-DETECT-SELFQUOTE-1` should stay open with this dossier linked as the
   record of what was actually investigated, rather than being closed on a repeat of a
   previously-defeated mechanism.

---

## Sources actually opened/fetched (per this role's honesty bar)

- [Intercept and control agent behavior with hooks — Claude Agent SDK docs](https://code.claude.com/docs/en/agent-sdk/hooks) (fetched in full; "Available hooks" table, `SubagentStop` example code, common-fields description quoted above)
- [Claude Code hooks reference (CLI)](https://code.claude.com/docs/en/hooks) (fetched; common-fields table and "Additional fields for subagent contexts" table quoted verbatim above — this is the doc that governs `~/.claude/settings.json`-registered hooks, which is what this project actually uses)
- [anthropics/claude-code issue #7881](https://github.com/anthropics/claude-code/issues/7881) (fetched; quoted payload example and the "shared session_id" limitation — resolved as not applicable to this project's current runtime, per 1a/1b)
- [nizos/tdd-guard](https://github.com/nizos/tdd-guard) — README (`curl` raw, full text read), `docs/validation-model.md`, `docs/enforcement.md`, `docs/ignore-patterns.md` (all fetched raw, quoted verbatim), `src/validation/validator.ts` and `src/hooks/processHookData.ts` (actual source, fetched raw, quoted verbatim), `plugin/hooks/hooks.json` (fetched raw, quoted verbatim), GitHub API repo metadata (stars 2,247, license MIT, last push 2026-07-06, not archived)
- [From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents](https://arxiv.org/abs/2606.04990) (abstract + framing fetched and quoted)
- Local, session-authorized evidence (per explicit dispatch-prompt grant): `<HOME>/.loop-gate/subagent_gate_debug.jsonl`, `<HOME>/.loop-gate/*.commit_violation`, `<HOME>/.claude/projects/-Users-eobodoechine/22cbd4f2-9f8e-47a7-b8f3-910ea048d275.jsonl` + its `subagents/` directory, `<HOME>/.claude/projects/-Users-eobodoechine/5976abda-2612-4f62-b897-8c473a5ad5d1.jsonl` + its `subagents/` directory — all read structurally (JSON field/schema inspection) for this specific question, not narrated as general conversation content.
- This project's own: `<HOME>/Claude/loop/hooks/loop_stop_guard.py`, `<HOME>/Claude/loop/hooks/subagent_stop_gate.py` (both read in full), `<HOME>/Claude/loop/fix_plan.md` (relevant entries read in full: `H-STOPGUARD-SUBAGENTTYPE-ADJACENCY-SELFMATCH-1` ~line 5537-6189, `H-GUARD-CODER-DETECT-SELFQUOTE-1` ~line 3099-3157, `H-GUARD-6` ~line 1366-1374/1638), `<HOME>/Claude/loop/research/hguard6-stop-hook-verifier-gate-prior-art-2026-07-02.md`, `<HOME>/Claude/loop/research/loop-stop-guard-misfire-dossier-2026-07-08.md`.

## Not found / could not verify

- Whether `data.get("transcript_path")` on a real `SubagentStop` firing is **always** scoped
  to the completing sub-agent's own conversation, or can sometimes resolve to the parent
  session's full transcript (section 1c) — genuinely unresolved, needs the one-line debug-log
  instrumentation fix recommended there before this mechanism is trusted for a blocking gate.
- Any other open-source Claude-Code-specific tool (beyond TDD Guard) implementing "verify a
  sub-agent's actual behavior matches its declared role" — searched broadly, found none
  beyond this project's own `H-SUBAGENT-COMMIT-GATE-1` and `H-LT6`.

---
---

# PART 2 — Implementation-ready design spec

**Follow-up dispatch, same day (2026-07-08), same Researcher (Mode D), no sub-agents
spawned.** The coordinator asked for this to move from "here's what's available" to a
concrete spec a Coder can build against without re-deriving the research. Real field names,
real current line numbers, real file paths throughout — no renamed/invented identifiers.
Two genuinely new, load-bearing findings surfaced during this follow-up (both change the
threat-model answer materially) are called out inline where they land: **(F1)** the five
custom-subagent-type frontmatters already structurally deny `Write`/`Edit` for two of the
four non-Coder roles, and **(F2)** `tool_use_id` is a real, confirmed top-level field on at
least one real Claude Code CLI hook payload shape in this runtime (`PreToolUse`) — strongly
suggesting, but not yet proven, that it is also present on `SubagentStop`.

## 0. Do this first — a five-minute pre-flight check that de-risks everything below

Before building anything in section 3, extend `subagent_stop_gate.py`'s existing
unconditional debug-log write (the block at the end of the file, currently:

```python
try:
    ...
    with open(debug_path, "a", encoding="utf-8") as dbg:
        dbg.write(json.dumps({
            "ts": time.time(),
            "session_id": _dbg_session_id,
            "agent_id": _dbg_agent_id,
            "cwd": _dbg_cwd,
            "last_line": _dbg_last_line,
            "wrote_flag": _dbg_wrote_flag,
        }) + "\n")
except Exception:
    pass
```

to also log `"payload_keys": sorted(data.keys())` and `"transcript_path": data.get("transcript_path")`
— mirroring the **exact, already-established pattern** in the sibling hook
`hooks/pre_tool_use_oga_guard.py`'s own debug writer (`_write_debug_row`, ~line 440-455),
which already logs `"payload_keys": sorted(data.keys())`. I confirmed empirically, from
`~/.loop-gate/oga_guard_debug.jsonl` (869 real occurrences of the dominant shape), that a
real `PreToolUse` payload **fired from inside a sub-agent** has exactly these top-level keys:

```
agent_id, agent_type, cwd, effort, hook_event_name, permission_mode,
prompt_id, session_id, tool_input, tool_name, tool_use_id, transcript_path
```

**`tool_use_id` is a real, confirmed top-level field in this runtime's CLI hook JSON — not
an SDK-only concept.** I could not confirm whether `SubagentStop`'s own payload also carries
it (only `PreToolUse`/`PostToolUse` were empirically checkable via the existing debug log;
`subagent_stop_gate.py`'s own debug log does not currently capture `payload_keys`). The
Agent SDK docs' `SubagentStop` worked example (quoted in Part 1, section 1) does read a
`toolUseID` value and logs it as "Tool use ID," which is suggestive but is the SDK's
callback-argument abstraction, not proof for the CLI JSON-stdin shape. **Run one real Coder
or Researcher dispatch after adding this logging line, then read the new
`subagent_gate_debug.jsonl` row.** Two outcomes, each with a clear next step:

- **If `tool_use_id` is present and equals the parent transcript's `Agent`/`Task` tool_use's
  own `id`** (the value you'd find at `_TOOL_USES` in `loop_stop_guard.py`, e.g.
  `"toolu_01MrSp4nVYVjMD13gy8c7Tea"`, confirmed matching format in Part 1 section 1b): skip
  the `.meta.json`-reading fallback in section 3 entirely — `subagent_stop_gate.py` can
  record `data.get("tool_use_id")` directly into the new flag's content, and
  `loop_stop_guard.py` needs zero directory-listing/JSON-sidecar-reading logic. This is the
  simpler, lower-cost path — check for it first.
- **If absent or doesn't match:** fall back to the `.meta.json` sidecar path (confirmed
  working empirically in Part 1 section 1b — `toolUseId` inside
  `<session_dir>/subagents/agent-<agentId>.meta.json` reliably matched the parent's tool_use
  `id` in every case checked), per section 3 below.

This same logging addition also finally resolves Part 1 section 1c's open ambiguity (whether
`transcript_path` on `SubagentStop` is reliably sub-agent-scoped) — the next real firing's
logged `transcript_path` value can be diffed directly against the known
`<session_dir>/subagents/agent-<agentId>.jsonl` path to confirm or refute it empirically,
rather than continuing to reason about it from a single ambiguous historical incident.

## 1. Exact mechanism, end to end — real field names, quoted, not paraphrased

```
DISPATCH TIME (parent transcript, <session_id>.jsonl, current turn)
  tool_use block:
    "type": "tool_use"
    "id": "toolu_01MrSp4nVYVjMD13gy8c7Tea"      <-- the correlating ID (call this DISPATCH_ID)
    "name": "Agent"                              <-- or "Task"/"Workflow"/"subagent"
    "input": {
      "description": "Revert coder-detection to safe full-text scan",
      "subagent_type": "coder",                  <-- caller-claimed, NOT trusted for the gate
      "run_in_background": <bool>,
      "prompt": "..."
    }
        |
        |  (Task/Agent tool call blocks the parent turn until the sub-agent finishes,
        |   UNLESS run_in_background:true — see section 5's timing caveat)
        v
SUB-AGENT RUNS — its own turns, its own tool calls, written by Claude Code to:
  ~/.claude/projects/<project-slug>/<session_id>/subagents/agent-<agentId>.jsonl
    each line: {"agentId": "a92e66c77e6019a07", "isSidechain": true,
                "message": {"role": "assistant"/"user", "content": [
                   {"type": "tool_use", "name": "Edit"/"Write"/"Bash"/..., "input": {"file_path": ..., ...}},
                   ...]}, ...}
  ~/.claude/projects/<project-slug>/<session_id>/subagents/agent-<agentId>.meta.json
    {"agentType": "coder", "description": "Revert coder-detection to safe full-text scan",
     "toolUseId": "toolu_01MrSp4nVYVjMD13gy8c7Tea",     <-- == DISPATCH_ID, confirmed empirically
     "spawnDepth": 1}
        |
        v
SUB-AGENT COMPLETES -> SubagentStop hook fires (hooks.SubagentStop in ~/.claude/settings.json
  -> `python3 '<HOME>/Claude/loop/hooks/subagent_stop_gate.py'`), receiving on
  stdin (documented + empirically confirmed fields, Part 1 section 1a/1b):
    {"session_id": "22cbd4f2-9f8e-47a7-b8f3-910ea048d275",   <-- PARENT's session_id, same as top-level
     "agent_id": "a92e66c77e6019a07",                        <-- call this AGENT_ID
     "agent_type": "coder",                                  <-- Claude Code's own ground truth for subagent_type
     "transcript_path": "<per-agent OR top-level jsonl — confirm via section 0>",
     "last_assistant_message": "...",
     "cwd": "<HOME>",
     "stop_hook_active": false}
        |
        v
`subagent_stop_gate.py` (this hook, already reads `transcript_content` once at the top of
  the file per H-TRACE-WIRING-1's "REQUIRED FILE RESTRUCTURING") -> NEW Fifth responsibility
  (section 3) scans this sub-agent's own tool_use entries for Write/Edit on a real source
  file -> writes `~/.loop-gate/{session_id}_{agent_id}.subagent_behavior` (NEW flag, always
  written, content encodes both "completed" and "what it wrote").
        |
        v
LATER (same turn if synchronous, a subsequent turn if backgrounded): Oga's own `Stop` hook
  fires -> `loop_stop_guard.py` -> for each dispatch-shaped tool_use in the CURRENT turn,
  resolve DISPATCH_ID -> AGENT_ID (via `tool_use_id` in the new flag's content if section 0
  confirms it's populated, else via the `.meta.json` `toolUseId` match) -> glob for a FRESH
  `{session_id}_{agent_id}.subagent_behavior` flag -> read its `feature_writes` field.
```

## 2. Core design change to `loop_stop_guard.py`'s PLAN_CHECK classification loop

**Today** (lines 747-789, byte-for-byte per the round-4 revert): every dispatch-shaped
`tool_use` in the turn is classified from TEXT alone —
`_VERIFIER_DETECT` first, then `subagent_type == "coder"` (additive-only), then
`_CODER_DETECT` over description+prompt (the accepted-false-positive, round-4-reverted
scan).

**Proposed:** classify PER-DISPATCH, preferring structural evidence when it's available and
falling back to the existing text scan when it is not — this is a **per-tool_use decision**,
not a per-turn one, so a turn with two dispatches (one resolved, one still running) handles
each correctly instead of forcing an all-or-nothing choice.

```python
# NEW helper, called once per dispatch-shaped tool_use, BEFORE the existing
# _VERIFIER_DETECT / subagent_type=="coder" / _CODER_DETECT chain runs for that tool_use.
def _structural_coder_verdict(tu, session_id, gate_dir):
    """Returns True (coder-shaped, block-relevant), False (confirmed clean --
    suppress the text scan for THIS tool_use), or None (unresolved -- caller
    must fall back to the existing text scan, unchanged)."""
    dispatch_id = tu.get("id") or tu.get("tool_use_id")
    if not dispatch_id:
        return None  # can't correlate at all -- conservative fallback

    agent_id = _resolve_agent_id(dispatch_id, session_id)   # section 3
    if not agent_id:
        return None  # sub-agent not found/not yet started -- fallback

    flag_path = os.path.join(gate_dir, f"{session_id}_{agent_id}.subagent_behavior")
    if not _fresh(flag_path):        # mirrors the EXISTING PLAN_PASS_TTL_SECONDS freshness check
        return None                  # not completed yet (or flag write raced/failed) -- fallback

    try:
        content = json.loads(open(flag_path, encoding="utf-8").read())
    except Exception:
        return None                  # malformed -- fail to fallback, not to allow (safe direction)

    return bool(content.get("feature_writes"))
```

Wire it into the existing loop (the `for _tu in _TOOL_USES:` block, current lines ~747-789):

```python
for _tu in _TOOL_USES:
    if _tu.get("name", "").lower() not in ("task", "agent", "subagent", "workflow"):
        continue
    _inp = _tu_dispatch_text(_tu)
    ...  # _tu_raw_input / _tu_subagent_type unchanged

    if _VERIFIER_DETECT.search(_inp):                 # UNCHANGED -- Verifier side untouched
        _seen_verifier_anywhere = True
        continue

    verdict = _structural_coder_verdict(_tu, session_id, gate_dir)   # <-- NEW
    if verdict is True:
        _seen_coder_anywhere = True
        if _first_coder_match_tu is None: _first_coder_match_tu = _tu
        continue
    if verdict is False:
        # Structural evidence says this SPECIFIC dispatch's sub-agent completed
        # and wrote NOTHING feature-shaped -- suppress the text scan for THIS
        # tool_use only. Do NOT `continue` past other tool_uses' own checks;
        # this only skips _CODER_DETECT for this one dispatch.
        continue

    # verdict is None (unresolved: backgrounded / not yet started / correlation
    # failed / malformed flag) -- EXACT existing behavior, byte-for-byte,
    # unchanged from the round-4 revert:
    elif _tu_subagent_type == "coder":
        _seen_coder_anywhere = True
        if _first_coder_match_tu is None: _first_coder_match_tu = _tu
    elif _CODER_DETECT.search(_inp) or _CODER_DETECT.search(_tu_dispatch_prompt_text(_tu).lower()):
        _seen_coder_anywhere = True
        if _first_coder_match_tu is None: _first_coder_match_tu = _tu
```

**Note on scope, explicitly:** this changes classification granularity from "did ANY dispatch
this turn look like a Coder" to "for EACH dispatch this turn, is it coder-shaped" — the
existing `_plan_check_violated = _seen_coder_anywhere and not _seen_verifier_anywhere`
aggregate check downstream is unchanged.

**Lower-risk incremental alternative, if the team wants to ship something before trusting
per-dispatch correlation:** add `verdict is True` as a pure **OR** (never `False`/suppress),
i.e. drop the `if verdict is False: continue` branch and let the text scan always still run.
This closes threat 4b (the bypass) immediately with zero new correlation-reliability risk,
but does **not** close 4a/4c (the false positives) — state this tradeoff explicitly to
whoever decides which to ship first; do not silently ship the weaker version while claiming
the false-positive class is closed.

## 3. Exact new code needed

### 3a. New shared module: `hooks/feature_write_scan.py`

Mirrors the precedent already set twice in this codebase for exactly this reason
(`verifier_hygiene_scan.py` for `H-VERIFIER-REGEX-DUPLICATE-1`; `commit_scope_scan.py` for
`H-SUBAGENT-COMMIT-GATE-1` item 1 — both created specifically so `loop_stop_guard.py` and
`subagent_stop_gate.py` never hand-duplicate the same classification logic). Extract, do not
duplicate, the following **already-hardened** logic currently inline in `loop_stop_guard.py`:

- `_RH_CODE_EXT` (lines 409-413) — the pinned code-extension regex.
- `_rh_temp_roots()` (lines 438-448) — realpath'd tmp/scratch exemption roots.
- `_RH_SETTINGS_FILES` (lines 451-456) — the two exempt `~/.claude/settings*.json` paths.
- `_rh_under()` (lines 433-435) — prefix-containment helper.

New pure function, signature mirroring `commit_scope_scan.find_commit_scope_violations(tool_uses, tool_results, target)`:

```python
def find_feature_writes(tool_uses):
    """Pure function. Returns [{"tool": "Edit", "path": <realpath>}, ...] for every
    Write/Edit/MultiEdit tool_use in `tool_uses` whose file_path realpath (a) has a
    code-extension basename per _RH_CODE_EXT, AND (b) is NOT under a temp root and NOT
    one of the two exempt settings files (same exemption semantics as loop_stop_guard.py's
    _rh_exempt_paths_only -- reused, not reinvented). Symlink-safe (realpath resolved
    before classification, matching every other structural check in this file family)."""
    out = []
    for tu in tool_uses:
        name = tu.get("name", "").lower()
        if name not in ("write", "edit", "multiedit"):
            continue
        inp = tu.get("input")
        if not isinstance(inp, dict):
            continue
        fp = inp.get("file_path") or inp.get("path") or ""
        if not isinstance(fp, str) or not fp:
            continue
        real = os.path.realpath(os.path.expanduser(fp))
        if not _RH_CODE_EXT.search(os.path.basename(real)):
            continue
        if real in _RH_SETTINGS_FILES:
            continue
        if any(_rh_under(real, root) for root in _rh_temp_roots()):
            continue
        out.append({"tool": name, "path": real})
    return out
```

`loop_stop_guard.py` then imports `_RH_CODE_EXT`/`_rh_temp_roots`/`_RH_SETTINGS_FILES`/
`_rh_under`/`find_feature_writes` back from `feature_write_scan.py` (mirroring the exact
import block already at the top of the file, lines 17-42, for
`verifier_hygiene_scan.py`) — **zero behavior change** for `loop_stop_guard.py`'s own
existing `_rh_exempt_paths_only`/FEATURE-gate logic, which keeps calling the same functions,
now imported instead of module-local. Re-run the existing `_rh_*` pytest classes after this
refactor specifically to confirm byte-identical behavior (a pure extraction should not change
any existing test's outcome).

### 3b. `subagent_stop_gate.py` — new Fifth responsibility

Placed alongside the existing Fourth responsibility (commit-scope scan, ~lines 214-296),
reusing the **already-extracted** `_cv_tool_uses` list from that same block (zero additional
transcript parsing/file I/O):

```python
# Fifth responsibility (independent of tiers 1-3, trace-logging, and the Fourth
# responsibility above -- new, this design). Wrapped in its own try/except per this
# file's established per-responsibility isolation discipline.
try:
    from feature_write_scan import find_feature_writes as _fw_find

    _fw_writes = _fw_find(_cv_tool_uses)      # reuses Fourth responsibility's own extraction

    _fw_payload = {
        "tool_use_id": data.get("tool_use_id"),   # None if absent -- see section 0's pre-flight check
        "agent_type": data.get("agent_type"),      # diagnostic only, NEVER trusted for the verdict
        "feature_writes": _fw_writes,              # [] if clean -- flag is written EITHER way
    }
    _write_flag_if_guarded(
        _cv_session_id, _cv_agent_id, ext="subagent_behavior",
        content=json.dumps(_fw_payload))
except Exception:
    pass
```

**Written unconditionally on every `SubagentStop` firing for a scan-eligible sub-agent**
(existence + freshness = "this dispatch has completed and been scanned" — this is what lets
`loop_stop_guard.py` distinguish "confirmed clean" from "not yet resolved," which an
only-written-on-violation flag like `.commit_violation` cannot do). Reuses
`_write_flag_if_guarded` (already defined in this file, already extended once for
`.commit_violation`'s `ext`/`content` parameters per `H-SUBAGENT-COMMIT-GATE-1` — no further
signature change needed, this is a third caller of an already-generalized function).

### 3c. `loop_stop_guard.py` — `_resolve_agent_id(dispatch_id, session_id)`

```python
def _resolve_agent_id(dispatch_id, session_id, gate_dir):
    # Path A (preferred, pending section 0's confirmation): scan fresh
    # .subagent_behavior flags for this session; the first whose OWN content
    # carries a matching tool_use_id IS the match. Cheap -- these flags are
    # already being globbed by _structural_coder_verdict's caller for freshness.
    for f in glob.glob(os.path.join(gate_dir, f"{glob.escape(session_id)}_*.subagent_behavior")):
        try:
            content = json.loads(open(f, encoding="utf-8").read())
        except Exception:
            continue
        if content.get("tool_use_id") == dispatch_id:
            # filename is "{session_id}_{agent_id}.subagent_behavior"
            base = os.path.basename(f)[:-len(".subagent_behavior")]
            return base.split("_", 1)[1] if "_" in base[len(session_id)+1:] else None
            # (use the SAME rsplit/session_id-prefix-strip convention already
            # established at Layer 1, lines 195-202, for parsing agent_id out
            # of a flag filename -- do not reinvent that parsing.)

    # Path B (fallback, only if Path A found nothing -- e.g. tool_use_id was
    # None in every flag, confirming section 0's check came back negative):
    # read transcript_path (already available as a module-level variable in
    # loop_stop_guard.py) to derive <session_dir>, list its subagents/*.meta.json,
    # match toolUseId == dispatch_id, return the agent_id embedded in that
    # filename (agent-<agentId>.meta.json).
    try:
        session_dir = os.path.join(os.path.dirname(tpath), session_id, "subagents")
        for name in os.listdir(session_dir):
            if not name.endswith(".meta.json"):
                continue
            meta = json.loads(open(os.path.join(session_dir, name), encoding="utf-8").read())
            if meta.get("toolUseId") == dispatch_id:
                m = re.match(r"agent-(.+)\.meta\.json$", name)
                if m: return m.group(1)
    except Exception:
        pass
    return None
```

Both paths fail closed (`return None` -> the caller's `verdict is None` -> unchanged
text-scan fallback) on any error — no new exception surface that could crash the hook or
silently over-suppress.

## 4. Precise threat-model coverage check

**(a) Misfire-1 (Researcher quoting `roles/coder.md`/`role: coder` for context; real tool
calls Read/Grep/WebSearch/WebFetch only, per that dossier's own Mode B "no code touched, no
sub-agents spawned" constraint):** `_structural_coder_verdict` resolves `agent_id`, finds a
fresh `.subagent_behavior` flag with `feature_writes: []` (the sub-agent never called
Write/Edit on a code-extension path) -> returns `False` -> `_CODER_DETECT`'s match for this
dispatch is **suppressed**. Does **not** block. **This requires the per-dispatch-correlated
design (section 2's primary proposal); the OR-only incremental alternative does NOT fix
this** — restated here because it's the exact case the coordinator is checking.

**(b) Round-1 bypass (`subagent_type="researcher"` + a live "implement this now,
Edit/Write... right now" prompt):** two genuinely different sub-cases, **and this is where
finding (F1) matters — go read it before assuming this needs the detection mechanism at
all:**

- If the dispatch used the **custom `subagent_type: "researcher"`** path (the convention
  `orchestrator.md` documents, line ~468), its actual frontmatter — read directly from
  `~/.claude/agents/researcher.md`, quoted verbatim —
  is `tools: Read, Grep, Glob, WebSearch, WebFetch, Bash, Write, Edit` /
  `disallowedTools: Agent`. **`Write`/`Edit` ARE available to Researcher** (legitimately —
  needed for the Persistence rule, writing `research/*.md`). So this specific bypass is
  **live and real** for Researcher: a sufficiently direct prompt CAN make it call `Edit` on
  a real source file, and Claude Code's own permission system will not stop it. If it does,
  `find_feature_writes()` (section 3a) picks up the real `Edit` call, `feature_writes` is
  non-empty, `_structural_coder_verdict` returns `True` -> `_seen_coder_anywhere = True`
  regardless of the claimed `subagent_type` -> **blocks**, closing the round-3 bypass shape.
  **But — and this must be stated plainly, per the coordinator's own framing — this is
  DETECTION, not PREVENTION.** The unreviewed source edit has already landed on disk by the
  time this fires; the gate can force Oga to remediate on its *next* `Stop` (dispatch a real
  Verifier, review/revert the diff), but it cannot undo or have stopped the write itself.
  **This is a genuine, disclosed shift in what this specific gate guarantees** — from "no
  unreviewed Coder work can complete a turn" to "no unreviewed Coder work can complete a turn
  *without also being caught and forced into remediation*, after the fact." Whether that's
  an acceptable tradeoff is a product decision, not a technical one — flagging it as the
  honest characterization, not asserting it's fine.
- If the dispatch instead used **`subagent_type: "verifier"` or `"plan-check-verifier"`**
  (the other two roles in the round-3 bypass fixture set): their frontmatters —
  `verifier.md`: `disallowedTools: Agent, Write, Edit, NotebookEdit`;
  `plan-check-verifier.md`: `disallowedTools: Agent, Write, Edit, NotebookEdit, Bash` —
  **already structurally deny `Write`/`Edit` at the Claude Code permission layer, before any
  hook logic runs at all.** A live "Edit this file right now" instruction given to a
  `subagent_type: "verifier"` dispatch cannot actually succeed — the tool call itself would
  be denied by Claude Code, independent of this project's own hooks. **This means the
  round-3 bypass fixtures for these two specific roles were testing a text-classification
  concern only, not an actually-exploitable live bypass** — worth a note back to whoever owns
  `hooks/test_loop_stop_guard.py`'s `SubagentTypeRoleAwareCoderDetectionMisfire3LiveInstructionBypass`
  class: those tests construct a synthetic transcript fixture (a plausible Write/Edit call
  that never actually ran against live tool permissions) rather than proving the tool call
  would truly execute — a reasonable and necessary simplification for a unit test, but it
  means the CLOSED `H-STOPGUARD-...` entry's characterization of this as "a genuine new
  bypass" is, for these two roles specifically, one degree more alarming than the live
  tool-permission reality — the round-4 revert's conservative text-scan remains correct and
  necessary for `researcher`/`test-writer` (where the bypass is real) but was arguably never
  load-bearing for `verifier`/`plan-check-verifier` specifically. **Not yet verified live**
  (no live probe was run this session confirming Claude Code actually denies the tool call
  for a `disallowedTools`-restricted subagent_type) — recommended as a cheap, decisive
  pre-flight probe alongside section 0's.
- **`test-writer`** (`tools: Read, Write, Edit, Bash, Grep, Glob`, `disallowedTools: Agent`)
  is the same live-bypass shape as Researcher — Write/Edit are legitimately available (its
  whole job is writing test files), so a prompt that redirects it to edit a non-test source
  file is not structurally prevented, and `find_feature_writes()` would need a refinement
  (not yet designed) to distinguish "wrote a test file, expected" from "wrote production
  source, not expected" for this role specifically — flagged as residual, not solved here
  (see section 5).

**(c) `H-GUARD-CODER-DETECT-SELFQUOTE-1` (dispatch quoting `orchestrator.md`'s own
`dispatch_check` schema, literal `"role": "<...Coder...>"` placeholder text; actual dispatch
was a general-purpose investigation agent + a Researcher, neither expected to write code):**
identical reasoning to (a) — if the completed sub-agent's `.subagent_behavior` flag shows
`feature_writes: []`, the match is suppressed and it does **not** block. Same caveat as (a):
requires the per-dispatch-correlated design, not the OR-only alternative.

## 5. Honest residual risk list

- **`transcript_path` scoping (Part 1 section 1c), still not conclusively resolved.** If
  `subagent_stop_gate.py`'s `transcript_content` sometimes resolves to the FULL top-level
  session transcript rather than the scoped per-agent file, `find_feature_writes()` could
  pick up **Oga's own** direct Write/Edit calls and misattribute them to the completing
  sub-agent as a false `feature_writes` entry. Consequence is asymmetric and fails in the
  safe direction (over-blocking an innocent dispatch, not under-blocking a real one) — but it
  means the flag's positive (`feature_writes` non-empty) signal should not be treated as
  100% precise until section 0's pre-flight check confirms scoping. The suppression
  direction (`feature_writes: []` -> allow) is comparatively lower-risk from this specific
  ambiguity, since a wrongly-INCLUDED main-thread write can only ever make the flag show
  MORE writes than the sub-agent actually made, never fewer.
- **`tool_use_id` presence on `SubagentStop` is not yet confirmed** — only inferred from (a)
  `PreToolUse`'s confirmed real payload shape and (b) the Agent SDK docs' worked example.
  Section 0's check resolves this before section 3c's Path A is trusted; Path B (`.meta.json`)
  is the proven-working fallback regardless.
- **Nested/grandchild sub-agents.** All five custom subagent types set `disallowedTools:
  Agent`, so a dispatched sub-agent should be structurally unable to spawn its own delegate
  (`H-WF-DELEGATE-1`'s stated guarantee) — but Part 1 section 1c's live incident
  (`a47eb9cab33e1a95a`, `spawnDepth` implied >1, no matching `subagents/agent-*.jsonl` found
  under its parent's own directory) shows nesting **does** occur in practice, likely via the
  `subagent_type: "general-purpose"` fallback path `orchestrator.md` itself documents (no
  `disallowedTools` restriction on that path). A nested grandchild's own Write/Edit would be
  recorded against **its own** `agent_id`, not its parent dispatch's — `_resolve_agent_id`
  as designed above only resolves the DIRECT dispatch named by a current-turn `tool_use.id`,
  so a nested grandchild's coder-shaped behavior would not roll up into blocking the
  top-level turn under this design. Not solved here; flagged as a known gap, same
  "safe-direction over-firing is acceptable, under-firing is the residual risk" framing this
  file already uses elsewhere.
- **`test-writer`'s Write/Edit is legitimately expected** — `find_feature_writes()` as
  designed cannot currently distinguish "test-writer wrote a test file, correct" from
  "test-writer was redirected to edit production source, a real violation." A refinement
  (e.g. requiring the touched path match a test-file heuristic — `test_*`/`*_test.*`/`__tests__/`
  — for `test-writer`-labeled dispatches, mirroring TDD Guard's own `isTestFile()` check cited
  in Part 1 section 3) is a plausible follow-up, not designed in this pass.
- **Workflow-tool dispatches — parity unverified.** `loop_stop_guard.py` already special-cases
  `tool_use.name == "workflow"` for TEXT scanning (`_tu_dispatch_text`/
  `_tu_dispatch_prompt_text`'s dedicated branch, reading the `script` field). I found no
  empirical evidence, positive or negative, that a `Workflow`-tool-embedded lens dispatch
  produces its own `SubagentStop` firing + `subagents/agent-<agentId>.jsonl`/`.meta.json` the
  same way a direct `Agent`/`Task` call does — the real `agentType` values found on disk
  (`general-purpose`, `plan-check-verifier`, `coder`, `verifier`, `test-writer`, `researcher`,
  plus the CLI's own built-in `Explore`/`Plan`/`brand-voice:quality-assurance`) look like
  ordinary `Agent`/`Task` dispatch labels, not a distinct Workflow-lens signature. **Do not
  assume parity — test this specific case live before shipping**, and until confirmed,
  `_resolve_agent_id` returning `None` for a Workflow-originated dispatch (falling back to
  the unchanged text scan) is the correct, safe default, not a bug to "fix" blindly.
- **Cost.** `subagent_stop_gate.py`'s new Fifth responsibility adds no new file I/O (reuses
  the Fourth responsibility's already-extracted `_cv_tool_uses`). `loop_stop_guard.py`'s new
  per-dispatch resolution adds one `glob()` per dispatch-shaped `tool_use` this turn (cheap,
  same pattern as the existing `PLAN_PASS`/Layer-1 globs) on Path A; Path B (fallback) adds a
  `listdir()` + N `.meta.json` reads of a directory that can hold dozens of entries (34
  observed in one real session) — bounded but non-trivial if exercised on every `Stop`. This
  is the concrete reason to prefer confirming Path A (section 0) over shipping Path B as the
  primary route.
- **Timing/backgrounded dispatches** — restated from Part 1 section 5: this is why `verdict
  is None` (unresolved) must fall back to the conservative text scan, never to "allow." A
  `run_in_background: true` Coder dispatch that hasn't finished by the time `Stop` first
  fires gets the SAME (imperfect, false-positive-accepting) protection it gets today — no
  regression, but also no improvement for that specific case from this design.
- **Recommended complementary, independent change (prevention layer, not part of this
  design):** since (F1) shows `Write`/`Edit` genuinely reachable for `researcher`/
  `test-writer`, a `PreToolUse` hook addition — `pre_tool_use_oga_guard.py` already reads
  `data.get("agent_id")`/(confirmed available) `data.get("agent_type")` for its own H-LT6
  fast path (lines 458-468) — could deny `Write`/`Edit`/`MultiEdit` outright when
  `agent_type == "researcher"` and the target `file_path` is not under `research/` (or
  other explicitly-scoped output dirs), using the documented `hookSpecificOutput.
  permissionDecision: "deny"` output shape (Part 1 section 1a). This would be **real
  prevention** (Claude Code denies the tool call before it executes), not detection, and
  would close 4(b)'s Researcher sub-case at the root rather than after the fact. It is a
  genuinely separate, independently-shippable change from everything in this Part 2 — noted
  here because the coordinator asked the question directly, not because it's this design's
  responsibility to implement.
