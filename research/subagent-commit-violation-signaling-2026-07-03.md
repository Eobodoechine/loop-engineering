# Surfacing a sub-agent's raw-`git commit` violation to Oga's own Stop hook

Date: 2026-07-03
Mode: D (domain research for a build), single research pass, no sub-dispatch
Question source: Oga design work on closing the gap where a dispatched sub-agent
(Coder/Verifier/Test-writer/Researcher) runs a raw `git commit` touching a
scope-listed shared file inside its OWN Bash tool_use — invisible to
`hooks/loop_stop_guard.py`'s existing Stop-hook `H-REVIEW-COMMIT-1` gate, which only
scans **Oga's own turn's transcript**.

## Bottom line / recommendation

**Adopt the flag-file bridge (Oga's candidate design), refined into a slightly
richer payload than a bare touch-file — reusing `subagent_stop_gate.py`'s existing
`_write_flag_if_guarded` pattern and naming convention, with the violation detail
written as a small JSON body rather than an empty file.** This is the strongest of
the three real candidates evaluated below. The alternative I went in expecting to
possibly be better — Oga's Stop hook directly locating and scanning the sub-agent's
own transcript file, no bridge file needed — **turned out to be genuinely viable
and lower-latency**, and is a legitimate second candidate; I recommend it as a
**secondary, defense-in-depth detection path layered under the same Stop-hook call
site**, not as a replacement, because it depends on an **undocumented, internal
on-disk layout** that carries real drift risk across Claude Code versions. The
flag-file bridge is the one that should be treated as authoritative; the
direct-transcript-scan path is a bonus early/redundant signal.

The trace.jsonl-extension idea (question 3) is **not competitive** with either —
it is strictly worse than the flag-file bridge for this specific job (see Finding 3).

---

## Finding 1 — Is a sub-agent's own `transcript_path` discoverable/derivable by the parent (Oga)? YES, empirically confirmed, but via an UNDOCUMENTED internal layout.

This was the open question in the task (item 2). I did not just read docs for
this — I directly inspected live transcript files on this machine to settle it
empirically, per this project's "verify against reality" standing rule.

**The mechanism, confirmed live:**

1. Oga's own Stop-hook payload's `transcript_path` field points at
   `~/.claude/projects/<cwd-slug>/<session_id>.jsonl` — this is Oga's own
   transcript, already read today by `loop_stop_guard.py` line 41
   (`open(tpath, ...)`).
2. When Oga dispatches a sub-agent asynchronously via the `Agent` tool, **Oga's
   own transcript records the dispatch's `toolUseResult` with an explicit
   `agentId` field**. Direct quote from a live transcript on this machine
   (`~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e.jsonl`,
   fetched via direct `Read`/`grep`, 2026-07-03):

   ```
   ,"content":[{"type":"text","text":"Async agent launched successfully.\nagentId: aa47f9f7e2c959b3a (internal ID - do not mention to user. Use SendMessage with to: 'aa47f9f7e2c959...
   ...
   "toolUseResult":{"isAsync":true,"status":"async_launched","agentId":"aa47f9f7e2c959b3a","description":"Research designs for cross-hook sub-agent violation signaling", ...
   ```

3. That same `agentId` is **exactly** the identifier used to name the sub-agent's
   own transcript file on disk, confirmed by directory listing:

   ```
   ~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/agent-aa47f9f7e2c959b3a.jsonl
   ~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/agent-aa47f9f7e2c959b3a.meta.json
   ```

4. The `.meta.json` sidecar even names the role and the originating
   `tool_use_id` directly (fetched, this repo's own logs, 2026-07-03):

   ```json
   {"agentType":"researcher","description":"Research designs for cross-hook sub-agent violation signaling","toolUseId":"toolu_01UVH8Y2A29576VqB4dDv2mT","spawnDepth":1}
   ```

5. The project-directory slug is a deterministic transform of `cwd`
   (`~/Claude/loop` -> `-Users-eobodoechine-Claude-loop`),
   confirmed by direct string transform + `ls`.

**So, concretely: yes.** Oga's Stop hook — reasoning purely from data already on
its own hook payload (`transcript_path`, `cwd`, `session_id`) plus a scan of its
own transcript for `agentId` tokens in `Agent`/`Task` tool_use results (a
structural extraction very close to what `pre_tool_use_oga_guard.py`'s
`in_flight_ids` logic already does at lines ~230-234, and what
`loop_stop_guard.py` already does for `tool_use_id` correlation at lines
~596-601) — **can derive every dispatched sub-agent's own transcript path this
turn**, without any new coordination file, and then directly apply
`loop_stop_guard.py`'s own existing SHA-extraction/scope-check logic (lines
928-1105) to that file.

**The load-bearing caveat (why this is NOT simply "adopt this instead"):** this
on-disk directory layout (`<session>/subagents/agent-<id>.jsonl` +
`.meta.json`) is **not documented anywhere in the official Claude Code hooks or
Agent SDK reference docs** I could find (`code.claude.com/docs/en/hooks`,
`code.claude.com/docs/en/agent-sdk/hooks`, `code.claude.com/docs/en/sub-agents`
— none of these mention a `subagents/` directory, an `agent-<id>.jsonl` naming
convention, or a `.meta.json` sidecar). It is an **implementation detail of the
CLI's session-storage format**, observed only by direct filesystem inspection.
Two independent third-party sources corroborate the same layout exists (not
just something local to this machine) — see Finding 2's sources — but neither is
an official spec, and nothing prevents Anthropic from changing this layout in a
future release without a deprecation notice, since it was never a public
contract. Contrast with the flag-file mechanism, whose contract (`session_id`,
`transcript_path`, `agent_id` on the SubagentStop hook's OWN stdin payload) IS
officially documented — see Finding 2 below for exact citations — and is what
`subagent_stop_gate.py` already keys off today, live-proven across many real
sessions (this machine's own `~/.loop-gate/*.verifier_pass` files, tens of them,
already exist as evidence this mechanism works in production).

## Finding 2 — Official docs on the Stop/SubagentStop schemas, and what does/doesn't cross the parent/child boundary

Fetched directly, 2026-07-03:

- **`https://code.claude.com/docs/en/hooks`** — the CLI hooks reference (the
  layer loop-team actually runs on, per the prior research file
  `research/claude-code-subagent-tool-restriction-2026-07-02.md`'s own finding
  that SDK-only docs are not this project's runtime). Confirmed common input
  fields for every hook: `session_id`, `prompt_id`, `transcript_path`, `cwd`,
  `permission_mode`, `effort`, `hook_event_name` — plus, **only present "when
  running with `--agent` or inside a subagent"**: `agent_id`, `agent_type`.
  Verbatim: *"`agent_id` — Unique identifier for the subagent. Present only
  when the hook fires inside a subagent call."* This is the exact mechanism
  `subagent_stop_gate.py` already uses (`data.get("agent_id")`) and that
  `pre_tool_use_oga_guard.py` already empirically validated (memory
  `pretooluse-agent-id-distinguishes-subagents`).
- **Decision-control table, same page, confirmed by direct follow-up fetch**:
  *"SubagentStop | Top-level `decision` | `decision: "block"`, `reason`. Stop
  and SubagentStop also accept `hookSpecificOutput.additionalContext` for
  non-error feedback that continues the conversation"* — **but** this
  `additionalContext` is injected into **the subagent's own conversation**,
  never the parent's. No `additionalParentContext` or equivalent field exists
  for `SubagentStop` in the documented schema.
- **`https://code.claude.com/docs/en/agent-sdk/hooks`** (Agent SDK docs, for
  comparison — confirms the same fields exist at the SDK layer too): the
  worked "Track subagent activity" example explicitly shows the field name
  **`agent_transcript_path`** (not `transcript_path`) being read off a
  `SubagentStop` hook's `input_data` in the SDK's own sample code:

  ```python
  async def subagent_tracker(input_data, tool_use_id, context):
      print(f"[SUBAGENT] Completed: {input_data['agent_id']}")
      print(f"  Transcript: {input_data['agent_transcript_path']}")
  ```

  This is worth flagging precisely because it means the SDK's own
  `SubagentStop` payload shape uses a **different field name**
  (`agent_transcript_path`) than what `subagent_stop_gate.py` currently reads
  (`transcript_path`, per the CLI-hooks doc table and per this repo's live
  debug logs at `~/.loop-gate/subagent_gate_debug.jsonl`, which show the hook
  successfully extracting content via `data.get("transcript_path")` today).
  **This project runs on the CLI hooks layer, not the raw SDK**, so
  `transcript_path` is confirmed correct for `subagent_stop_gate.py` as-is
  (live logs prove it works); but any future code that also has to run under
  the raw Agent SDK (as opposed to CLI `settings.json` shell hooks) would need
  to check for both field names — a portability gotcha worth recording, not an
  action item for this fix.

**Net for the parent-visibility question (task item 2):** the *documented*
answer is negative — no official field bridges a `SubagentStop` result back to
the parent's `Stop` hook, and the parent's own `Stop`-hook payload has no
sub-agent-specific field at all (it only gets `agent_id`/`agent_type` when the
*hook itself* is firing inside a subagent, i.e., never for Oga's own Stop
hook). The *empirical* answer (Finding 1) is that a determined scan of Oga's
own transcript, cross-referenced against an undocumented on-disk layout, CAN
reconstruct the same information — but that is reverse-engineering an
implementation detail, not using a contract.

### Real prior art (task item 4) — this is a confirmed, named problem upstream

- **[GitHub issue #5812](https://github.com/anthropics/claude-code/issues/5812)
  — "Feature Request: Allow Hooks to Bridge Context Between Sub-Agents and
  Parent Agents."** Fetched directly. **Status: closed as not planned.** This
  is Anthropic's own acknowledgment of exactly this class of problem (there
  described for a different payload — a sub-agent's file-write content, not a
  policy violation — but the underlying mechanism gap is identical: *"There is
  currently a significant context isolation problem between a parent agent and
  its sub-agents. When a sub-agent performs an action that creates new
  information..., the parent agent remains unaware of that information."* The
  issue explicitly proposes the same shape of fix a violation-flag would need
  (a `SubagentStop` -> parent-context channel via
  `additionalParentContext`) and it was **rejected/not planned**, and the
  issue's own "Alternatives Considered" section names exactly the workaround
  class this project already uses: *"Writing changes to temporary state
  files"* / *"Committing to Git and having the parent run `git status`"* —
  i.e., Anthropic's own closed-issue thread independently arrives at
  "state-file bridge" as the accepted workaround for this exact gap, which is
  a real, if indirect, external validation of Oga's candidate design.
- **[GitHub issue #7881](https://github.com/anthropics/claude-code/issues/7881)
  — "SubagentStop hook cannot identify which specific subagent finished due to
  shared session IDs."** Fetched directly. Opened 2025-09-19, filed against an
  OLDER runtime where `SubagentStop` payloads did NOT yet include an `agent_id`
  field (only `session_id` + `transcript_path`, both identical across
  concurrent sub-agents) — the issue's own reproduction snippet shows exactly
  that shape. **This confirms `agent_id` was added to the SubagentStop payload
  at some point after Sept 2025**, which is exactly the mechanism
  `subagent_stop_gate.py` relies on today and this project's own memory
  `pretooluse-agent-id-distinguishes-subagents` already proved empirically —
  i.e., the gap this older issue describes is **already fixed** in the runtime
  this project runs on (confirmed live via this session's own debug logs
  showing populated `agent_id` values). Still open on GitHub as of the fetch
  (no maintainer reply recorded), likely because the issue's specific proposed
  field names (`subagent_id`/`subagent_session`) weren't what shipped, but the
  underlying identifiability problem it raised has been addressed via
  `agent_id`.
- I did **not** find any GitHub issue, discussion, or blog post specifically
  matching "sub-agent detected a policy violation, needs to surface it to a
  blocking parent-level Stop hook" as a named pattern with a shipped solution.
  The closest real prior art is #5812 (generalized parent-context-blindness,
  closed not-planned) and this project's own already-fetched TDD Guard /
  claudefa.st marker-file precedent (see
  `research/hguard6-stop-hook-verifier-gate-prior-art-2026-07-02.md` Finding 2,
  already catalogued — the sanctioned pattern for ANY cross-turn/cross-process
  state in this hook ecosystem is a `$session_id`-keyed marker file, e.g.
  official docs' own worked example: *"`$HOME/.claude/hooks/state/$session_id.json`"*
  and claudefa.st's `.claude/incomplete-task` block-while-exists pattern). I
  report this honestly as "no named community pattern for this exact
  scenario" rather than force a citation — the two issues above are real and
  relevant but neither is a direct hit.

## Finding 3 — Could the existing `trace.jsonl` `role_dispatch` logging be extended with a `commit_violation` event type instead of a new flag-file type? (task item 3)

Reused mechanism, but **worse fit** than the flag-file bridge for this specific
job. Concretely, from reading `hooks/subagent_stop_gate.py` end to end:

- The trace-logging block (lines 198-336) is explicitly documented as
  **best-effort, fail-open, and independent of the flag-write's exit-code
  guarantee** (line 21: *"fully fail-open, never affects the flag-write logic
  or this hook's exit code"*). It is designed for **observability**, not as a
  gate signal — nothing in `loop_stop_guard.py` today reads `trace.jsonl` at
  all (confirmed: no `trace.jsonl`/`Tracer` reference anywhere in
  `loop_stop_guard.py`'s 1113 lines). Wiring a NEW consumer (Oga's own Stop
  hook) to depend on this file for a BLOCKING decision would silently change
  its risk class from "nice-to-have log" to "load-bearing gate input" without
  any of the existing hardening the flag-write path already has (the
  `_write_flag_if_guarded` non-empty-session-id guard, the 3-tier precedence
  rule, the debug-log corroboration).
- `Tracer(run_dir).event(...)` (line 329) is **only reachable when a run-dir
  reference is found in the transcript** via the `LT_PATTERN`/`BARE_PATTERN`
  regex scan (lines 232-296) — i.e., it depends on the sub-agent's own
  transcript happening to mention a `runs/<name>/` path. A Coder/Verifier
  dispatch that never mentions its own run directory (plausible — many
  dispatches reference a `spec.md` path directly, not a bare run-dir token)
  would produce **no trace event at all**, silently. The flag-file mechanism
  has no such dependency — it fires unconditionally off `session_id`+`agent_id`,
  which are ALWAYS present per the official schema (Finding 2), not
  content-dependent.
  - Path-containment/traversal guards on `run_dir` (lines 282-294) exist
    specifically for the trace-write's own safety — additional machinery a
    `commit_violation` event would inherit for free, but which does nothing to
    solve item (2)'s "where does the file even live" problem when there IS no
    run-dir reference.
- Even if a `commit_violation` event were added and successfully written,
  Oga's Stop hook would then need to (a) resolve which `run_dir` the CURRENT
  session's dispatches are using (non-trivial — multiple roles/turns can
  reference different run dirs across a long session), (b) open that
  `trace.jsonl`, (c) filter for a `commit_violation` event with a timestamp
  after Oga's last Stop-hook check — essentially reinventing the flag-file
  bridge's freshness/TTL logic (already solved, tested, and battle-hardened in
  `loop_stop_guard.py` lines 500-536 for the PLAN_PASS credit) on top of a
  file whose location is conditional rather than fixed
  (`~/.loop-gate/<session_id>_*` is always resolvable from `session_id` alone;
  a run-dir-scoped `trace.jsonl` is not).

**Verdict: worse than the flag-file bridge for this job.** It reuses an
existing mechanism, but the mechanism's own design assumptions (best-effort,
run-dir-conditional, observability-only) actively fight the "must reliably gate
a Stop-hook decision" requirement. It would need real, additional
hardening work to become gate-safe — at which point it has converged on
reinventing the flag-file's own guarantees, just with a strictly less reliable
discovery path (conditional on transcript content) than the flag-file's
(unconditional on `session_id`).

## Finding 4 — Could a `PreToolUse` hook on Oga's own `Agent`/`Task` dispatch call help? (task item 5)

**No — confirmed, not just assumed.** This is a pure timing-model question, and
the timing model is unambiguous from both the docs and this repo's own code:

- `PreToolUse` fires **before** the tool call executes — per
  `code.claude.com/docs/en/agent-sdk/hooks`'s own step-by-step model: *"An
  event fires... a tool is about to be called (`PreToolUse`)... Callback
  functions execute... Your callback returns a decision."* For an `Agent`/`Task`
  dispatch, "before the tool call executes" means **before the sub-agent has
  even started running** — there is no possible violation to detect yet, by
  definition, since the sub-agent's own Bash `git commit` tool_use is a *later*
  event nested inside a process that hasn't started.
- Confirmed against this repo's own `pre_tool_use_oga_guard.py`: its whole
  design (the `in_flight_ids` dispatch-tracking logic, lines 230-288) is built
  around exactly this constraint — it can only ever answer "is a sub-agent
  currently outstanding" (for a *different* purpose — licensing Oga's OWN
  direct Write/Edit calls while a sub-agent is in flight), never "what did that
  sub-agent's Bash calls do," because at `PreToolUse`-on-dispatch time none of
  that has happened yet.
- The only Claude Code hook type that fires with visibility into a completed
  sub-agent's own tool calls is `SubagentStop` (fires after the sub-agent's
  entire turn, including all its Bash calls, per the "Available hooks" table:
  *"`SubagentStop` | ... | Subagent completion"*) or a `PreToolUse`/`PostToolUse`
  hook **scoped to run inside the subagent itself** (via the subagent's own
  frontmatter `hooks:` field, confirmed real and documented in
  `research/claude-code-subagent-tool-restriction-2026-07-02.md`'s Finding —
  but that would need to be authored into every custom subagent type's own
  frontmatter, and per Finding 2/#5812 above, still has no channel back to the
  parent regardless of when it fires).

**Confirmed: PreToolUse on the parent's dispatch call cannot do this job.** It
is ruled out on timing grounds alone, independent of any data-availability
question.

---

## Candidate designs — comparison

### Candidate A (Oga's original, refined) — SubagentStop flag-file bridge, reusing `_write_flag_if_guarded`

**Mechanism:** `subagent_stop_gate.py` gains a 4th responsibility (parallel to
its existing 3): on every `SubagentStop`, re-run `loop_stop_guard.py`'s own
raw-`git-commit`-detection + scope-check logic (lines 928-1105) against
`transcript_content` (already read once at the top of the file — reuse, don't
re-open) scoped to the sub-agent's OWN turn (the whole sub-agent transcript,
since a sub-agent's transcript IS one turn's worth of tool calls in the
relevant sense). On a hit, write a marker via the SAME guarded helper pattern
already used for `.verifier_pass` (`_write_flag_if_guarded`), naming it
`{session_id}_{agent_id}.commit_violation`, with the violated SHA(s) + touched
scope file(s) written as its content (not an empty touch-file, so Oga doesn't
have to re-derive them — small refinement over a bare flag). `loop_stop_guard.py`
gains a NEW gate (mirroring its existing PLAN_PASS-credit glob-and-TTL logic at
lines 508-536) that globs `~/.loop-gate/<session_id>_*.commit_violation`, and on
any fresh hit, blocks Oga's own Stop with the violation detail read straight out
of the marker's content.

**Reuses:** the entire tested SHA-extraction/scope-check block already in
`loop_stop_guard.py` (lines 928-1105) — call it as a shared function instead of
duplicating it; `_write_flag_if_guarded`'s exact guard semantics (non-empty
`session_id` required, `agent_id` falls back to `"unknown"`); the
glob-escape + TTL-freshness pattern already proven for `.verifier_pass`
(lines 508-536); the `LOOP_GATE_DIR` env-var convention.

**Invents:** one new flag-file extension (`.commit_violation` instead of
`.verifier_pass`) and one new glob/read site in `loop_stop_guard.py`. This is
the ONLY genuinely new surface — everything else is direct reuse.

**Implementation cost:** LOW. The heaviest lift is refactoring
`loop_stop_guard.py`'s existing commit-scan block (currently written as an
inline `try` block operating on the CURRENT turn's `_TOOL_USES`/`_TOOL_RESULTS`)
into a callable function parameterized on "which transcript/turn to scan" so
`subagent_stop_gate.py` can import and reuse it without duplicating ~180 lines
of regex/SHA logic. That refactor is mechanical (no behavior change to the
existing Oga-side check) but must be done carefully — see Risks below.

**Reliability / race risk:** LOW-MEDIUM. Same TTL/staleness class of risk the
existing PLAN_PASS credit already carries and has already been hardened for
(H-GUARD-3/H-LT7b's non-consuming, TTL-bounded design, per
`loop_stop_guard.py` lines 500-507) — i.e., this is a KNOWN, already-solved
risk shape, not a new one. The one real new risk: if TWO sub-agents in the same
session both raw-commit a scope file, and Oga's Stop hook only checks "any
fresh flag exists" rather than resolving per-agent, Oga could clear the block
after addressing only one violation while a second (different SHA, different
agent_id) flag sits unaddressed. Mitigation: don't just check flag EXISTENCE —
read and surface the CONTENT of every fresh matching flag (this is why the
refined design writes SHA+file content into the flag body, not a bare touch),
and delete/rename a flag only once Oga's remedy step (the same "re-diff via
`git show <sha>`" flow the existing gate message already prescribes) actually
runs — mirroring the existing gate's own "keep/revert/route" remedy language
(`loop_stop_guard.py` lines 1096-1104) rather than inventing new remedy UX.

**Race condition analysis:** the flag write happens in `SubagentStop` (after
the sub-agent's turn fully ends, so the commit has already landed in git
history — same "cannot prevent, can only force remediation" timing model the
existing H-REVIEW-COMMIT-1 gate already documents and accepts, lines 930-939).
The read happens in Oga's own `Stop` hook, which fires strictly after
`SubagentStop` for a synchronously-awaited dispatch. For an ASYNC dispatch
(Oga's `Agent` tool supports `isAsync`, confirmed in Finding 1's transcript
quote), there IS a real ordering risk: Oga could reach its own Stop hook
BEFORE the async sub-agent's `SubagentStop` has fired at all, if Oga's own turn
ends without waiting on the dispatch. This is a genuine gap — but it's the
SAME gap the existing PLAN_PASS credit mechanism already has and has already
chosen to accept (a flag not yet written simply means "not yet credited," which
is the safe-direction failure for a gate — no flag defaults to "does not
license," never the reverse). No new failure mode introduced; inherits an
already-accepted one.

### Candidate B — direct transcript-scan (Oga's Stop hook locates and scans the sub-agent's own transcript itself, no bridge file)

**Mechanism:** In `loop_stop_guard.py`'s Stop-hook handler, after the existing
per-turn `_TOOL_USES` extraction, additionally scan for `Agent`/`Task`
tool_use blocks whose paired `tool_result` contains an `agentId` field
(matching the JSON shape confirmed live in Finding 1). For each such
`agentId`, construct the candidate sub-agent transcript path as
`os.path.join(os.path.dirname(tpath_derived_project_dir), <session_id>,
"subagents", "agent-%s.jsonl" % agent_id)` (deriving the project dir from
Oga's OWN already-available `transcript_path`, which sits at
`<project_dir>/<session_id>.jsonl` — no NEW field needed, purely a path
transform of data already on the Stop-hook payload), and if that file exists,
run the SAME reused commit-scan function (see Candidate A) against it directly
— zero flag files, zero SubagentStop involvement at all.

**Reuses:** the exact same commit-scan function Candidate A needs anyway
(so building A first makes B nearly free to add as a second call site); the
`tool_use_id`/tool_result correlation idiom already present in
`loop_stop_guard.py` (`_rc_tool_result_for`, lines 986-996) and
`pre_tool_use_oga_guard.py` (`in_flight_ids`, lines 230-249) — this is
genuinely the SAME pattern, just walking `agentId` instead of `tool_use_id`.

**Invents:** a path-construction routine against an **undocumented directory
layout** (Finding 1) — this is the one real net-new, unhardened surface, and
it is exactly the surface that's fragile across Claude Code versions.

**Implementation cost:** LOW-MEDIUM. Slightly higher than Candidate A because
of the path-derivation logic (project-dir slug transform + subagents/
subdirectory), and because it needs its own defensive fallback (file-not-found
must fail open, silently — the sub-agent may not have started, may be a
synchronous dispatch with a differently-shaped result, or the layout may have
changed).

**Reliability / race-condition risk:** LOW on timing (no cross-hook race at
all — everything happens inside Oga's own single Stop-hook invocation, reading
files that are guaranteed to already exist by the time Oga's turn ends,
whether the dispatch was sync or async, PROVIDED Oga's own turn didn't end
before the sub-agent's transcript file was flushed to disk — a subtly
different but real risk from Candidate A's cross-hook race). **MEDIUM-HIGH on
version-drift**: this entire mechanism silently breaks (fails open, since a
missing file is handled defensively) the moment Anthropic changes the
`subagents/agent-<id>.jsonl` naming convention, the `agentId` field name in
`toolUseResult`, or the project-dir slug algorithm — none of which carry any
stability guarantee, unlike the officially documented `SubagentStop` payload
fields Candidate A depends on. A silent fail-open on a security/discipline
gate is a worse failure mode than a loud break, because nobody would notice
the gate had gone dark.

**Verdict on B: real, and I recommend keeping it as a SECOND, redundant
detection path layered under Candidate A** — it costs little extra once
Candidate A's scan function exists, and it has a nice property Candidate A
doesn't: it works even in the async-ordering edge case where Oga's Stop hook
fires before the sub-agent's own `SubagentStop` flag would have been written
(Finding on Candidate A's race risk), IF the transcript file has already been
flushed by then. But it should never be the ONLY path, given the version-drift
risk on an undocumented format.

### Candidate C — extend `trace.jsonl`'s `role_dispatch` event (task item 3)

Covered in Finding 3 above. **Not competitive** — inherits real reuse (the
`Tracer` class, the run-dir resolution/traversal-guard logic) but that reuse
is fighting the job (best-effort/observability design assumptions vs. a
gate's need for unconditional reliability), and its trigger condition (a
run-dir reference must appear in the transcript) is strictly less reliable
than Candidate A's (fires unconditionally off always-present `session_id` +
`agent_id`). Documented here per the task's explicit ask, not recommended.

---

## Recommendation, ranked

1. **Build Candidate A (flag-file bridge) as the authoritative mechanism.**
   It is the only one of the three whose triggering condition depends solely
   on OFFICIALLY DOCUMENTED, version-stable fields (`session_id`, `agent_id`,
   `transcript_content` on `SubagentStop`'s own payload — Finding 2), it
   directly reuses the most-tested existing code in this file family (the
   H-REVIEW-COMMIT-1 SHA-extraction logic, plus the exact
   `_write_flag_if_guarded`/TTL-glob pattern already proven live across dozens
   of real sessions on this machine), and its known race-condition class
   (async-dispatch ordering) is the SAME accepted risk the PLAN_PASS credit
   mechanism already lives with successfully — not a new unknown.
2. **Layer Candidate B (direct transcript-scan) underneath it as a bonus early
   / redundant signal, not a replacement.** Cheap to add once A's scan
   function exists (same function, two call sites), catches the same class of
   violation with zero cross-hook latency, but must be explicitly documented
   as "best-effort, silently degrades if the on-disk layout changes" so a
   future maintainer doesn't mistake it for the load-bearing path.
3. **Do not build Candidate C.** The existing `trace.jsonl` mechanism is fine
   for what it already does (observability); bending it into a gate input
   would require re-deriving guarantees Candidate A already has for free, on a
   strictly weaker trigger condition.

**Why not "just B, since it needs no new SubagentStop hook logic at all"?**
Because the flag write in A is unconditional (fires from data every
`SubagentStop` invocation always has), while B's discovery depends on an
undocumented directory structure I could not find in ANY official doc — it
is a real, reproducible, empirically-confirmed mechanism (Finding 1), but
"reproducible today" is not the same bar as "documented, stable interface,"
and a security/discipline gate silently going dark on a Claude Code version
bump is exactly the kind of instructional-not-structural failure this
project's Researcher role brief flags as the worst category (a compliance
failure that would not surface as a detectable error). A carries none of that
risk.

---

## Transfer-condition check (per researcher.md's mandatory closing section)

For Candidate A (the recommended primary mechanism):
- **(a) Execution context required:** Claude Code CLI hook infrastructure
  specifically — a `SubagentStop` entry in `~/.claude/settings.json` (already
  present, since `subagent_stop_gate.py` is already installed there per its
  own docstring) and a `Stop` entry (already present, `loop_stop_guard.py`).
  Requires filesystem write access to `$LOOP_GATE_DIR` (already granted;
  the existing `.verifier_pass` mechanism already proves this works).
- **(b) Does the target context satisfy it?** Yes — this is the exact
  environment `subagent_stop_gate.py` and `loop_stop_guard.py` already run in
  today, live-proven by the dozens of real `.verifier_pass` flags and
  `subagent_gate_debug.jsonl`/`oga_guard_debug.jsonl` entries already on this
  machine.
- **(c) Structural or instructional guarantee?** **Structural.** The
  `SubagentStop` hook's `sys.exit()` behavior and stdin payload are enforced by
  the Claude Code runtime itself, not by asking the sub-agent to self-report —
  the sub-agent has no way to suppress or falsify the flag-write (it doesn't
  even know the hook ran; this is identical in kind to the existing
  `.verifier_pass` mechanism's own guarantee, which nothing in this design
  changes). The ONE instructional link in the whole chain is Oga's own
  post-block remedy step ("re-diff via `git show <sha>`, decide
  keep/revert/route") — same as the existing H-REVIEW-COMMIT-1 gate already
  requires today, not a new instructional surface introduced by this fix.

For Candidate B (the secondary path): the structural/instructional split is
the same, EXCEPT the discovery step itself (constructing the candidate path
from `agentId` + project-dir slug) rests on an unenforced, undocumented
convention — a version bump changing that convention would silently disable
detection with no error surfaced (a silent, load-bearing compliance failure of
exactly the kind the role brief flags as worst-case) — which is precisely why
it must stay secondary to A, never load-bearing alone.

---

## Sources

- `~/Claude/loop/hooks/subagent_stop_gate.py` (this repo) — read in full;
  existing flag-write mechanism, 3-tier precedence rule, trace.jsonl logging
  responsibility.
- `~/Claude/loop/hooks/loop_stop_guard.py` (this repo) — read in full;
  existing H-REVIEW-COMMIT-1 gate (lines 928-1105), PLAN_PASS TTL-credit
  mechanism (lines 500-536), `_TOOL_USES`/`_TOOL_RESULTS` structural
  extraction idioms.
- `~/Claude/loop/hooks/pre_tool_use_oga_guard.py` (this repo) — read relevant
  sections; `in_flight_ids` dispatch-tracking logic (lines 230-288), live
  `agent_id`-based caller-identity check (lines 172-179).
- Live debug logs on this machine (`~/.loop-gate/subagent_gate_debug.jsonl`,
  `~/.loop-gate/oga_guard_debug.jsonl`) — empirical confirmation of actual
  runtime `payload_keys` (`agent_id, agent_type, cwd, effort, hook_event_name,
  permission_mode, prompt_id, session_id, tool_input, tool_name, tool_use_id,
  transcript_path`) and dozens of real `.verifier_pass` flags proving the
  mechanism works live.
- Live transcript files on this machine
  (`~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e.jsonl`
  and its `subagents/agent-<id>.jsonl` + `.meta.json` siblings) — direct
  inspection proving the `agentId`-to-transcript-path linkage (Finding 1).
- [Intercept and control agent behavior with hooks (CLI)](https://code.claude.com/docs/en/hooks) —
  fetched twice, 2026-07-03: common input fields table, `agent_id`/`agent_type`
  scoping, `SubagentStop`/`Stop` decision-control table
  (`decision: "block"`, `reason`, `hookSpecificOutput.additionalContext`
  scoped to the firing agent's OWN conversation only).
- [Intercept and control agent behavior with hooks (Agent SDK)](https://code.claude.com/docs/en/agent-sdk/hooks) —
  fetched 2026-07-03: full hook-event table, the "Track subagent activity"
  worked example showing the SDK-layer field name `agent_transcript_path`
  (distinct from the CLI layer's `transcript_path`), confirmation that
  `additionalContext` never crosses to the parent.
- [GitHub issue #5812 — "Feature Request: Allow Hooks to Bridge Context
  Between Sub-Agents and Parent Agents"](https://github.com/anthropics/claude-code/issues/5812) —
  fetched 2026-07-03. Closed as not planned; Anthropic's own acknowledgment of
  the parent-child context-isolation gap; "Alternatives Considered" names the
  same state-file-bridge workaround class this design uses.
- [GitHub issue #7881 — "SubagentStop hook cannot identify which specific
  subagent finished due to shared session IDs"](https://github.com/anthropics/claude-code/issues/7881) —
  fetched 2026-07-03. Filed against an older runtime lacking `agent_id` on
  `SubagentStop`; confirms `agent_id` was added later, matching this project's
  own already-proven live behavior.
- `~/Claude/loop/research/hguard6-stop-hook-verifier-gate-prior-art-2026-07-02.md`
  (already catalogued in this repo) — the sanctioned marker-file-as-cross-turn-
  state pattern (official docs' `$HOME/.claude/hooks/state/$session_id.json`
  worked example; claudefa.st's `.claude/incomplete-task` pattern), cited here
  rather than re-fetched, per this task's instruction to check
  `research/SOURCES_INDEX.md` first.
- `~/Claude/loop/research/claude-code-subagent-tool-restriction-2026-07-02.md`
  (already catalogued in this repo) — prior confirmation that the CLI hooks
  layer (not just the SDK) carries `agent_id`/`agent_type`; cited rather than
  re-derived.
