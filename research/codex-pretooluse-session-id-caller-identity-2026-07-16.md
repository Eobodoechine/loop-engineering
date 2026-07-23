# Domain brief — does Codex's own session_id propagation make `_same_session()` a valid dispatch-record match for a genuine Codex sub-agent?

**Mode:** D (domain research for a build). **Build:** `fix/oga-guard-codex-worker-identity`
(`loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md`) — the fix for the
"confirmed Codex-worker regression" in `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`. **Follow-up
to:** `research/codex-pretooluse-agent-id-caller-identity-2026-07-16.md` (same methodology; that
brief's own honesty-bar section explicitly left session_id under-verified — see "What the prior
brief already established vs. left open" below). **Date:** 2026-07-16. **Researcher scope note:**
all reads/greps/web fetches below were done directly, no sub-agent dispatched. Reading real Codex
session transcripts under `~/.codex/sessions/` was explicitly authorized by this dispatch's own
text ("find the corresponding real Codex session transcript file," "read the actual Codex
transcript files it points to") — the same category of access the cited prior brief already used.

**A live misfire happened during this research, worth stating up front:** partway through this
task, my own `Write` call to my scratchpad (a genuine dispatched Researcher sub-agent's own
follow-up tool call) was blocked by the exact mechanism under study — `[OGA GUARD] Write(...)
blocked... Identity check failed: top-level agent_id does not match an active same-session
worker.` Per the guard's own printed instructions ("If you are seeing this message as a DISPATCHED
SUB-AGENT... this block is a known misfire... note the misfire... complete the assigned work using
your permitted tools"), I switched to Bash (not gated by `WORKER_TOOLS`) for all scratch work and
continued. This is a real, live, first-hand, Claude-Code-shaped instance of the same class of
false-positive this brief investigates for Codex — reported as direct corroborating evidence, not
hearsay.

## Question

Does a genuine Codex sub-agent's own PreToolUse payload's top-level `session_id` field equal the
session_id the PARENT transcript's own dispatch-related entries would be associated with — i.e., is
"same session_id" a valid way to confirm a Codex sub-agent's dispatch record belongs to the same
session as its own later tool calls? Or does Codex's actual session_id propagation behave
differently?

## What the prior brief already established vs. left open (so this one doesn't duplicate it)

`research/codex-pretooluse-agent-id-caller-identity-2026-07-16.md` established, with full empirical
rigor, that Codex's `agent_id` field is reliable on `PreToolUse` (1,039/1,039 real historical rows).
On session_id specifically, it only went as far as: quoting the official docs' "Subagent hooks use
the parent session id" line, and noting a "directly-paired same-session natural experiment" table
where the *same* session_id appeared on both a parent's own row and its child's row — but that table
was built and cited **to explain the agent_id finding**, not as a dedicated session_id
investigation. Its own `not_found` section is explicit that it did not independently verify this:
it never opened a child transcript's own `session_meta` to check the session_id value *at the
source*, and never asked whether the mechanism that would need this fact (`_same_session()`) could
actually use it. That is the exact gap this brief closes, using fresh evidence (the old fast path
this file gated is gone; a different, live mechanism — `_same_session()` — has since replaced it,
per `hooks/pre_tool_use_oga_guard.py:653-940`, landed via `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`,
committed `4ace7a9`, 2026-07-16T01:40:10-04:00).

## Answer

### Part 1 — YES, confirmed at full rigor: a genuine Codex sub-agent's session_id is its PARENT's session_id, not a fresh one

This is now independently confirmed at four levels, not one:

**(a) Official, documented contract (not an inferred behavior).** Fetched live 2026-07-16,
`https://developers.openai.com/codex/hooks` → redirects to `https://learn.chatgpt.com/docs/hooks`.
The "Common input fields" table states verbatim:

> "Field: `session_id`, Type: `string`, Meaning: Current Codex session id. **Subagent hooks use the
> parent session id.**"

This sits under **Common input fields** — the fields shared by every hook event type, including
PreToolUse — not under a PreToolUse-specific list. The PreToolUse-specific field list adds only
`turn_id`, `tool_name`, `tool_use_id`, `tool_input` on top of the common fields; it does not
re-specify or override `session_id`. **This is a materially stronger evidentiary status than the
`agent_id` finding**, which the prior brief found undocumented for PreToolUse (present only in the
`SubagentStart`/`SubagentStop` tables). Session_id-equals-parent is a stated, general contract;
`agent_id`-on-PreToolUse is an empirically-observed-but-undocumented implementation detail. This
asymmetry matters for how much weight each fact can bear in a fix.

**(b) Debug-log field correlation, freshly re-derived (5,492 total rows as of this check, up from
the prior brief's 5,176 — the log is still live-growing).** Filtering to real Codex rows
(`transcript_basename` matches `rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-[0-9a-f-]+\.jsonl`,
`session_id` non-empty, not `test-`-prefixed — identical filter to the prior brief) gives **1,098
real rows, 1,056 with `agent_id` in `payload_keys`, 42 without**. Of the 1,056: **1,054 classify as
"child"** (the row's `session_id` differs from its own transcript file's trailing UUID — i.e. this
call's `transcript_path` is a separate file from "session_id"'s own file) **and all 1,054 correlate
their `session_id` to the value logged on their own real parent's rows** (directly verified for two
concrete parent session_ids spanning 5 distinct child transcript files — Section (c) below opens
those exact files). Of the 42 without `agent_id`: all 42 classify as **"own"** (their `session_id`
IS their own file's trailing UUID) and all 42 are correctly `deny` (Oga's own direct call, correctly
blocked). This is a 100%-clean split, unchanged from the prior brief's methodology, now re-run fresh.

**(c) Direct, raw-JSONL inspection of real child transcript files — the step the prior brief did
not do.** I opened four real files under `~/.codex/sessions/2026/07/16/` (the actual on-disk
sub-agent transcripts a "child"-classified debug-log row points to) and read their own
`session_meta` event directly:

| child file (basename) | `payload.session_id` | `payload.id` (own) | `payload.parent_thread_id` | `payload.thread_source` |
|---|---|---|---|---|
| `rollout-2026-07-16T00-45-17-019f693e-4ade-72e0-b381-aebfbca4d849.jsonl` | `019f68b3-acea-7540-8466-b7f96524e784` | `019f693e-4ade-72e0-b381-aebfbca4d849` | `019f68b3-acea-7540-8466-b7f96524e784` | `subagent` |
| `rollout-2026-07-16T00-47-08-019f693f-fa33-7950-9a7d-ab8405458426.jsonl` | `019f692a-c0ad-75c3-bd81-2d2f6fa31f9d` | `019f693f-fa33-7950-9a7d-ab8405458426` | `019f692a-c0ad-75c3-bd81-2d2f6fa31f9d` | `subagent` |
| `rollout-2026-07-16T00-52-34-019f6944-f508-7a41-9e3f-a46c2ac6d530.jsonl` | `019f68b3-acea-7540-8466-b7f96524e784` | `019f6944-f508-7a41-9e3f-a46c2ac6d530` | `019f68b3-acea-7540-8466-b7f96524e784` | `subagent` |
| `rollout-2026-07-16T01-03-43-019f694f-2b1a-7670-b516-66cf0cb053f0.jsonl` | `019f68b3-acea-7540-8466-b7f96524e784` | `019f694f-2b1a-7670-b516-66cf0cb053f0` | `019f68b3-acea-7540-8466-b7f96524e784` | `subagent` |

**This settles it directly, at the source, not by correlation:** each child's OWN `session_meta`
declares `session_id` = its **parent's** id, `id` = its **own** distinct identity (matching its own
filename), `parent_thread_id` = its parent's id again (an even more explicit, purpose-built link
than session_id equality), and `thread_source` = the literal string `"subagent"` — an unambiguous,
first-class marker Codex itself writes. The corresponding parent file
(`rollout-2026-07-15T22-13-53-019f68b3-acea-7540-8466-b7f96524e784.jsonl`, 1,152 lines, real,
dated 2026-07-15/16, `cli_version:"0.144.2"`, `originator:"Codex Desktop"`) has `thread_source:"user"`
on its own `session_meta` (line 0) — the parent/child distinction is structural and explicit, not
inferred.

**(d) A real, previously-captured hook payload independently shows the identical pattern at the
top-level hook-stdin shape** (not just inside transcript file content):
`hooks/fixtures/ac1_captured_codex_stop_stdin.json` (a genuine captured `SubagentStop` event, dated
2026-07-10):
```json
{"session_id":"019f4b4a-939e-7842-8a95-af61a5bccd00", ...,
 "transcript_path":".../rollout-2026-07-10T05-10-06-019f4b4a-939e-7842-8a95-af61a5bccd00.jsonl",
 "agent_transcript_path":".../rollout-2026-07-10T22-08-03-019f4eee-8924-76c2-999c-0d0b1f81fd59.jsonl",
 "hook_event_name":"SubagentStop","agent_id":"019f4eee-8924-76c2-999c-0d0b1f81fd59", ...}
```
`session_id` matches `transcript_path`'s own trailing UUID (the **parent's** transcript);
`agent_id` matches `agent_transcript_path`'s trailing UUID (the **child's own, separate**
transcript) — the same parent-id/child-id split as (c), and confirmation that Codex's real hook
payload schema can carry both a parent-scoped `transcript_path` and a child-scoped
`agent_transcript_path` side by side. (This is a `SubagentStop` event, not `PreToolUse` — flagged
honestly in Constraints below.)

**Conclusion on Part 1:** the fact itself — a genuine Codex sub-agent's own hook payload session_id
equals its parent/dispatching session's session_id — is real, documented, and now confirmed at
every level this method has for confirming anything (doc quote, log correlation, raw transcript
inspection, and a captured real payload). It is not an assumption; it does not need further
verification. **This is the part of the question that has a clean "yes."**

### Part 2 — But this fact does NOT make `_same_session()` a working mechanism for Codex, for reasons independent of whether session_id matches

`_same_session()` (`hooks/pre_tool_use_oga_guard.py:831-832`) only ever gets called on entries
already present in `dispatched` (built at lines 750-768) and only matters for entries that survive
into `active_dispatches` (lines 835-838, requiring `tid in in_flight_ids` — itself built from
`dispatched`, lines 823-826). **For a genuine Codex session, `dispatched` is unconditionally empty,
regardless of session_id, for three independent, compounding, and now directly-confirmed reasons:**

1. **`transcript_path` for a Codex sub-agent's own tool call points at the CHILD's own separate
   file, never the parent's.** Confirmed twice: the debug log's `transcript_basename` field for
   every "child" row names the child's own file (table above); and I opened those exact files
   directly and confirmed their `session_meta.id` matches. The `dispatched`-collection loop
   (`hooks/pre_tool_use_oga_guard.py:753`, `for i, e in enumerate(events)`) only ever scans `events`
   loaded from **this call's own** `transcript_path` (line 601, 606) — so even in principle, the
   parent's own `spawn_agent` dispatch record (which lives in a **different file**) is never in
   scope for a child's own call.
2. **Even if it were scanning the right file, the collector's shape-match never fires for any real
   Codex event.** `_content(e)` (`hooks/pre_tool_use_oga_guard.py:670-674`) checks
   `e.get("message",{}).get("content",[])` or `e.get("content",[])`; the collector then requires
   `p.get("type")=="tool_use" and p.get("name")=="Agent"` (line 758). I enumerated **every**
   `payload.type` actually present in both real files I opened (1,152 + 218 lines): `session_meta`,
   `event_msg` (`task_started`/`task_complete`/`agent_message`), `response_item` wrapping
   `message`, `function_call` (incl. `spawn_agent`), `function_call_output`, `custom_tool_call`
   (incl. `apply_patch`, confirmed by direct grep — see Part 3), `custom_tool_call_output`,
   `agent_reasoning`/`reasoning`, `token_count`, `patch_apply_end`, `update_plan`. **None of these
   is `{"type":"tool_use","name":"Agent"}` inside a `.message.content`/`.content` list** — that
   shape is exclusively Claude Code's. `_content(e)` returns `[]` for every one of them, so
   `dispatched` never gains an entry from a real Codex transcript, full stop — independent of file
   choice.
3. **Even if (1) and (2) were both fixed, the `spawn_agent` dispatch record itself carries no
   `session_id` anywhere in its own payload.** I extracted all 14 real `spawn_agent` `function_call`
   entries in the parent transcript; every one has `payload` keys exactly
   `{arguments, call_id, id, internal_chat_message_metadata_passthrough, name, namespace, type}` —
   no `session_id` key. Session_id lives **only** on the enclosing/nearby `session_meta` event (a
   structurally different event, re-emitted periodically — 3 times in the 1,152-line parent file, all
   3 with the identical `session_id`), never on the dispatch call itself. `_event_session_id()`
   (`hooks/pre_tool_use_oga_guard.py:719-725`) checks `e.get("session_id")` / `e.get("message",{}).get("session_id")`
   — neither path exists on any real Codex event (Codex nests everything under `payload`), so even
   where reached this function returns `""` for Codex, always.

**Net, confirmed both structurally and live:** genuine Codex sub-agents' own worker-tool calls are
**unconditionally denied** under the code as it exists right now, independent of session_id
matching, because the dispatch record the comparison needs is never found in the first place. This
is not a theoretical extrapolation — it is exactly what
`loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md` (Section C, the spec this
research directly feeds) already states from its own independent diagnosis, and I now have **live,
production evidence of it actually happening**, traced end-to-end below.

### Part 3 — Live, real, POST-deployment confirmation: two genuine Codex sub-agent denials, fully traced

The hook file's own mtime (`hooks/pre_tool_use_oga_guard.py`, confirmed via `stat`, still
`2026-07-16 00:58:57 EDT` at the time of this check) is when the new "Exact worker identity guard"
replaced the old fast path **on disk** — this is the real code-change boundary (code executes the
moment the file is written, regardless of when `git commit` happens 41 minutes later at `4ace7a9`,
`2026-07-16T01:40:10-04:00`; using the commit timestamp as the cutoff, as I initially tried, wrongly
hides live evidence that exists between the two). Re-bucketing the 1,056 real "child + agent_id"
rows against the **file-mtime** boundary: **1,053 fall before it (all `allow` — old fast path), and
3 fall after it**:

```
ts=1784177937.479891 (2026-07-16T00:58:57 EDT, the exact mtime second) — file=hooks/pre_tool_use_oga_guard.py, decision=allow (ambiguous: same-second write race)
ts=1784178037.701364 (2026-07-16T01:00:37 EDT, +100s)               — file=hooks/pre_tool_use_oga_guard.py, decision=DENY
ts=1784178433.887048 (2026-07-16T01:07:13 EDT, +6.5min)             — file=hooks/test_spec_bound_verifier_credit.py, decision=DENY
```

Both `deny` rows are unambiguously after the boundary and both are traced to real, identifiable
dispatches, not anonymous noise:

- The first `deny` row's `session_id`/`transcript_basename`
  (`019f68b3-...` / `rollout-2026-07-16T00-52-34-019f6944-f508-7a41-9e3f-a46c2ac6d530.jsonl`) matches
  **exactly** the parent transcript's own `spawn_agent` call at line 804
  (`task_name:"coder_structural_guard"`, dispatched at `2026-07-16T04:52:34.271Z` UTC =
  `00:52:34` EDT — the same second as the child file's own name) — i.e., this is the **Coder
  sub-agent actively building the Exact Worker Identity Guard feature itself**, whose own follow-up
  `apply_patch` to `hooks/pre_tool_use_oga_guard.py` (the same file it had just edited, per the
  `allow` row 100 seconds earlier, same file target) was denied by the very guard it had just
  finished writing.
- The second `deny` row's transcript (`rollout-2026-07-16T01-03-43-019f694f-2b1a-7670-b516-66cf0cb053f0.jsonl`)
  matches the parent's `spawn_agent` call at line 880 (`task_name:"test_writer_reconcile_broad_suite"`,
  dispatched `2026-07-16T05:03:43.758Z` UTC = `01:03:43` EDT, same second as the child filename) —
  a Test-writer sub-agent's own `apply_patch` to `hooks/test_spec_bound_verifier_credit.py`, also
  denied.

**This is not a hypothetical risk or a static-analysis prediction — it is two directly observed,
fully-traced, real production denials of genuine, currently-dispatched Codex sub-agents' own
follow-up edits, on this exact machine, within the hour before this research.**

### Part 4 — The "self-consistent-but-wrong fixture" risk is concretely, independently real — found in code already shipped, not hypothesized

Looking for whether this codebase's *existing* Codex-parsing infrastructure could already encode
this exact class of wrong assumption (the risk the dispatch named), I found that it does, in two
places, both stale against today's real Codex Desktop (`cli_version 0.144.2`,
`multi_agent_version:"v2"`) transcripts:

- **`hooks/_codex_fixture_builders.py`'s `codex_spawn_agent()` (lines 157-169)** models `spawn_agent`
  arguments as `{"agent_type": agent_type, "message": message}` and its docstring asserts the
  paired `function_call_output` is "the ONLY channel that reveals agent_id — confirmed real shape:
  `output: {"agent_id": "<uuid>", "nickname": "<name>"}`." **Neither half matches what I directly
  read in today's real transcript:** all 14 real `spawn_agent` calls have arguments
  `{"task_name": ..., "fork_turns": ..., "message": "<encrypted>"}` (no `agent_type` key at all),
  and their paired `function_call_output` is `{"task_name": "/root/<task_name>"}` (no `agent_id`
  key at all). The default `cli_version` this fixture builder hardcodes is `"0.144.0-alpha.4"` — an
  earlier point-release than the `0.144.2` I observed live, consistent with a shape that changed
  between those versions.
- **`hooks/codex_transcript_adapter.py`** — the actual, already-shipped, canonical production
  module (used by `loop_stop_guard.py` and the spec-bound-credit gate) — has the identical
  assumption baked in: `extract_spec_credit_records()` (line 459) does
  `agent_id = out.get("agent_id")` and (line 463) `agent_type = args.get("agent_type", "")`, both of
  which would silently come back empty/falsy against today's real transcript shape. **More
  specifically relevant to this brief's question:** `_find_child_verdict()` (lines 219-272), whose
  own docstring states its matching rule as "locates the sub-agent's OWN, separate rollout-\*.jsonl
  file (`session_meta.payload.session_id == agent_id`)" (line 221) — **this is precisely the wrong
  assumption Part 1/Part 2 above disprove with direct evidence**: a real child's
  `session_meta.session_id` is its **parent's** id, never its own distinct `agent_id`/thread
  identity (that's `payload.id`, a different field). Grepping the whole 506-line adapter module for
  any version-branching (`"0.144"`, `cli_version`, `multi_agent_version`, `task_name`,
  `fork_turns`) returns **zero hits** — there is no newer-shape-aware code path anywhere in this
  module today.

**This is directly relevant to the Verifier's stated worry, with hard evidence rather than
speculation:** the exact class of error flagged ("a Test-writer could build self-consistent-but-wrong
fixtures... both sides using the same made-up session_id string") is not a hypothetical failure mode
this codebase is merely at risk of — it is a pattern this codebase's *existing, already-shipped*
Codex-parsing infrastructure already contains, confirmed by direct comparison against real,
dated-today transcripts. Any fixture the new build's Test-writer authors by copying
`codex_spawn_agent()`'s existing convention (which `loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md`
Section B explicitly instructs: "read the existing Codex test fixtures... to build new fixtures
consistently with the established shape") would be shaped like the **stale** convention, not
today's real one, unless corrected first.

### Direct answer to Section D's open question in the active spec

`loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md` Section D asks, verbatim:
"Confirm what a genuine Codex PreToolUse payload's own `session_id` field looks like and whether it
matches what `_event_session_id()` would extract from the transcript's own dispatch/session_meta
entries — do not assume parity with Claude Code's session_id semantics without checking."

**Answer:** the payload's `session_id` is the parent/dispatching session's own id (Part 1, confirmed
four ways). It does **not** match what `_event_session_id()` extracts today, for two independent
reasons: (i) `_event_session_id()` reads the wrong key path (`e["session_id"]`/`e["message"]["session_id"]`;
real Codex events nest it at `e["payload"]["session_id"]`, present only on `session_meta` events);
and (ii) it is never reached at all for a real Codex event, because the outer shape gate
(`p.get("type")=="tool_use" and p.get("name")=="Agent"`) never passes first. A correct fix needs to
extend `codex_transcript_adapter.py` (per the spec's own Section D option (a)) with logic that (1)
recognizes `response_item`/`function_call`/`name=="spawn_agent"` as a dispatch record — using
**today's real argument shape** (`task_name`/`fork_turns`, not `agent_type`), (2) resolves the
dispatched agent's own identity via the **child's own separate transcript's** `session_meta.id` /
`parent_thread_id` fields (confirmed reliable, Part 1c) rather than via the `spawn_agent`
call's own output (confirmed empty of any such id today, Part 2.3), and (3) reads the session_id
that is invariant per-file from any `session_meta.payload.session_id` in the relevant transcript
(confirmed invariant across 3 re-emissions in the one parent file I read in full) — not by
assuming the existing `_find_child_verdict()` matching rule already does this correctly, because it
does not (Part 4).

## Sources (file:line, transcript:line, or URL for every claim above)

- `hooks/pre_tool_use_oga_guard.py:601-608` — `transcript_path = data.get("transcript_path")`; `events` loaded from that exact path
- `hooks/pre_tool_use_oga_guard.py:653-667` — "Exact worker identity guard" comment header, `WRITE_CAPABLE_ROLES`
- `hooks/pre_tool_use_oga_guard.py:670-674` — `_content(e)`, Claude-Code-message-shaped
- `hooks/pre_tool_use_oga_guard.py:719-725` — `_event_session_id(e)`, checks `session_id`/`message.session_id` only
- `hooks/pre_tool_use_oga_guard.py:750-768` — `dispatched` collection loop, `p.get("type")=="tool_use" and p.get("name")=="Agent"` (line 758)
- `hooks/pre_tool_use_oga_guard.py:823-838` — `in_flight_ids`, `payload_session_id`, `_same_session()` (831-832), `active_dispatches`
- `hooks/pre_tool_use_oga_guard.py:872-925` — identity resolution chain (`top_agent_id`/`top_task_id`/`top_dispatch_id`)
- `hooks/pre_tool_use_oga_guard.py:927-937` — legacy fallback (also empty for Codex) and final unconditional deny
- `hooks/pre_tool_use_oga_guard.py:629-650` — `_write_debug_row()`, the debug log schema
- `~/.loop-gate/oga_guard_debug.jsonl` (this machine, read live 2026-07-16; 5,492 rows as of the last check, growing during this research) — real-Codex filter identical to the prior brief's; 1,098 real rows, 1,056 with `agent_id`, 42 without; re-bucketed against the hook file's own mtime (`2026-07-16T00:58:57-04:00`, confirmed via `stat`) rather than the later git-commit timestamp: 1,053 pre-change (all allow), 3 post-change (1 ambiguous same-second allow, 2 clean denies) — exact rows quoted in Part 3
- `<HOME>/.codex/sessions/2026/07/15/rollout-2026-07-15T22-13-53-019f68b3-acea-7540-8466-b7f96524e784.jsonl` — real parent transcript, 1,152 lines, read in full for event-type distribution (line 0/392/447 `session_meta`, `thread_source:"user"`); 14 `spawn_agent` `function_call` entries at lines 35,41,151,251,516,583,620,674,725,752,804,880,960,1033, none carrying `session_id`; matching `function_call_output` for each at lines 37,43,153,253,518,585,622,676,727,754,806,882,962,1035, all `{"task_name":"/root/<task_name>"}`, none carrying `agent_id`
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-45-17-019f693e-4ade-72e0-b381-aebfbca4d849.jsonl` — child transcript (line 0 `session_meta`: `session_id`=parent, `id`/`parent_thread_id`/`thread_source`/`agent_nickname`/`agent_path` as quoted in Part 1c's table); 218 lines, read in full for `payload.type`/`payload.name` distribution (`function_call`:50, `function_call_output`:50, `custom_tool_call`:5 all `name=="apply_patch"`, `custom_tool_call_output`:5, plus `message`/`agent_message`/`reasoning`/`token_count`/`update_plan`/`patch_apply_end`/`task_started`/`task_complete`) — zero `"type":"tool_use"` blocks anywhere
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-47-08-019f693f-fa33-7950-9a7d-ab8405458426.jsonl`, `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-52-34-019f6944-f508-7a41-9e3f-a46c2ac6d530.jsonl`, `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T01-03-43-019f694f-2b1a-7670-b516-66cf0cb053f0.jsonl` — three more real child transcripts, `session_meta` (line 0) read directly for each, values in Part 1c's table
- `hooks/fixtures/ac1_captured_codex_stop_stdin.json` — real captured `SubagentStop` payload (2026-07-10), quoted verbatim in Part 1d
- `hooks/_codex_fixture_builders.py:96-101` (module docstring), `:105-116` (`codex_session_meta`), `:157-169` (`codex_spawn_agent`, quoted docstring "the ONLY channel that reveals agent_id... `{"agent_id":..., "nickname":...}`"), default `cli_version="0.144.0-alpha.4"` — grepped whole file for `task_name`/`fork_turns`/`multi_agent_version`/`parent_thread_id`: zero hits
- `hooks/codex_transcript_adapter.py:219-272` (`_find_child_verdict`, docstring quoted line 221), `:342-357` and `:459-475` (`agent_id = out.get("agent_id")`, `agent_type = args.get("agent_type", "")`) — grepped whole 506-line file for `"0.144"`/`cli_version`/`multi_agent_version`/`task_name`/`fork_turns`: zero hits
- `loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md` — the active spec this brief directly feeds; Section C (the confirmed regression, independently diagnosed), Section D (the exact session_id question quoted and answered above), Section E (AC1-AC6)
- `loop-team/runs/2026-07-16_structural-planpass-evidence-guard/plan_check_log.md` — 3 rounds, `PLAN_PASS` at `spec_sha256=98227dc3...`; the mechanism this brief investigates was plan-checked without ever mentioning Codex
- `loop-team/runs/2026-07-15_oga-guard-caller-identity/specs/spec.md:1-11` — superseded-notice header: "A third, more severe finding — a confirmed Codex-worker regression in the new code, not something either session's plan-check caught — was found afterward and is tracked separately," and Section D/Section E AC1 (the now-superseded assumption that the old fast path made Codex support "complete")
- `fix_plan.md:9299` — `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1 (IMPLEMENTED 2026-07-16, priority: HIGH)`
- `fix_plan.md:7314-7361` — `H-CODEX-SPAWN-PRETOOLUSE-DISPATCH-GAP-1`, the related-but-different, already-tracked gap
- `research/task-workflow-pretooluse-agent-id-caller-identity-2026-07-16.md` — sibling brief; §0 (the "two mechanisms live simultaneously" finding, now resolved — the new one shipped) and Constraints (the analogous snake_case/camelCase `session_id` finding for Claude Code, cited for method-parity, not re-derived here)
- `git log -1 --format="%H %cI %s" -- hooks/pre_tool_use_oga_guard.py` → `4ace7a9c... 2026-07-16T01:40:10-04:00 Harden plan-check evidence and worker identity guards`
- `stat -f "%Sm" hooks/pre_tool_use_oga_guard.py` (run live, twice, at the start and end of this research) → `Thu Jul 16 00:58:57 EDT 2026`, unchanged — confirms the code-change boundary used in Part 3
- [`https://developers.openai.com/codex/hooks`](https://developers.openai.com/codex/hooks) (redirects to [`https://learn.chatgpt.com/docs/hooks`](https://learn.chatgpt.com/docs/hooks)) — fetched live 2026-07-16; "Common input fields" table, `session_id` row, quoted verbatim in Part 1a
- `codex --version` (direct invocation, 2026-07-16) → `codex-cli 0.41.0` — **a different version string than the `0.144.2` recorded inside the real transcripts** (see Constraints — these appear to be two different Codex distributions/channels on this machine, "Codex Desktop" vs. the `codex` CLI binary; flagged, not resolved)

## Constraints

- **Two different Codex identifiers on this machine, not reconciled.** Direct `codex --version`
  invocation returns `codex-cli 0.41.0`; every real transcript under `~/.codex/sessions/` records
  `"originator":"Codex Desktop"` and `"cli_version":"0.144.2"` (or `"0.144.0-alpha.4"` in the
  fixture builder's hardcoded default). These do not look like the same version-numbering scheme,
  and I did not establish whether "Codex Desktop" and the `codex` CLI binary are the same product
  under different version schemes or two genuinely separate installations. All empirical findings
  in this brief describe the "Codex Desktop" / `cli_version 0.144.2` transcripts specifically
  (since that is what every real row in `oga_guard_debug.jsonl` and every real file under
  `~/.codex/sessions/` actually is) — re-verify if the team's production hook-firing Codex runtime
  turns out to be the other one.
- **Scope disclosure, as in the prior briefs:** `~/.loop-gate/oga_guard_debug.jsonl` lives outside
  the repo tree; treated as this mechanism's authoritative evidence source elsewhere in this project
  (`fix_plan.md:838, 5657`; `loop-team/learnings.md:591-594`). Reading real files under
  `~/.codex/sessions/` (outside the repo tree and outside `~/Claude/loop/`) was explicitly
  authorized by this dispatch's own text, mirroring the prior Codex brief's precedent — I extracted
  only structural fields (event types, ids, timestamps, task names, argument key names) and did not
  quote or rely on any decrypted conversational content (the `message` field inside every real
  `spawn_agent` call is itself encrypted — a Fernet-style token I made no attempt to decrypt or
  needed to).
- **The one ambiguous row (Part 3, `ts=1784177937.479891`, `allow`, exactly at the file-mtime
  second) is reported as ambiguous, not resolved** — it is consistent with either "last row under
  the old code" or a same-second race with the new code; I did not find a way to disambiguate it
  further from the evidence available (the debug log does not record which code version executed).
  It does not affect the conclusion, since the two subsequent rows are unambiguous.
- **Version-pinned finding, as in the prior brief:** the session_id-equals-parent behavior is
  confirmed for real transcripts dated 2026-07-15/16 on this machine (`cli_version 0.144.2`,
  `multi_agent_version v2`). The official doc quote (Part 1a) is a general, dated-2026-07-16 live
  fetch of the current published contract, not tied to a specific Codex version — but Codex hooks
  remain an explicitly evolving surface per the prior brief's own finding; re-verify after any
  upgrade.
- **The `_find_child_verdict()`/fixture-builder staleness finding (Part 4) is adjacent to, not
  squarely inside, the literal session_id question asked** — it is reported because it directly and
  concretely substantiates the "self-consistent-but-wrong fixture" risk the dispatch named, with
  hard evidence from already-shipped code, not because it was the primary target of this brief.
  I did not audit the rest of `codex_transcript_adapter.py` or every other consumer of
  `extract_spec_credit_records()`/`_find_child_verdict()` for the full blast radius of this
  staleness — that would be a separate, wider investigation than this dispatch asked for.

## not_found

- I could not directly prove, byte-for-byte, that the `agent_id` value Codex's runtime attaches to a
  real **PreToolUse** hook payload is identical to the child's own `session_meta.id`/
  `parent_thread_id`-linked identity — the debug log redacts values (`payload_keys` only), so I
  cannot cross-check the row's actual `agent_id` string against the child file's `id` field for the
  *same* call. This equivalence is directly proven for **SubagentStop** (Part 1d, the captured
  fixture) and is a well-grounded structural inference for PreToolUse (same runtime, same
  multi-agent architecture, same "Common input fields" contract governing both event types) — but
  it is an inference for PreToolUse specifically, not an independently re-proven fact at that exact
  event type. A future check: capture one real, unredacted PreToolUse stdin payload for a Codex
  sub-agent's own call (mirroring how `hooks/fixtures/ac1_captured_codex_stop_stdin.json` was
  captured for SubagentStop) and diff its `agent_id` value against that same sub-agent's own
  transcript `session_meta.id`.
- I could not determine **why** Codex's `spawn_agent` calling convention differs between the
  fixture-builder/adapter's modeled shape (`agent_type`/`message` in, `{"agent_id","nickname"}` out,
  default `cli_version "0.144.0-alpha.4"`) and today's real, live shape
  (`task_name`/`fork_turns`/`message` in, `{"task_name"}` out, `cli_version "0.144.2"`) — whether
  this is a version-to-version protocol change between those two point releases, a
  `multi_agent_version` v1-vs-v2 branch (the real session_meta explicitly carries
  `"multi_agent_version":"v2"`; I found no v1 example to compare), or something else. No OpenAI
  changelog/release-note check was done to settle this (out of scope for the time available on this
  dispatch); a future search should look for Codex CLI/Desktop release notes spanning
  `0.144.0-alpha.4` → `0.144.2` and any `multi_agent_version` migration notes.
- Whether "Codex Desktop" (what every real transcript on this machine says `originator`) and the
  `codex-cli 0.41.0` binary directly invocable via `codex --version` are the same product on
  different version schemes, or two separate Codex distributions — not established (Constraints).
  If they are genuinely different runtimes, it is not yet confirmed which one is what actually fires
  this repo's hooks in production (the debug log's real rows are the only direct evidence, and they
  are consistent with "Codex Desktop" throughout, but I did not find a way to independently confirm
  the CLI binary never also fires these hooks).
