# Root cause: parallel `agent()` + `schema` failures in H-REVIEW-COMMIT-1 plan-check rounds

**Date:** 2026-07-03
**Mode:** A (loop-improvement, root-cause investigation)
**Trigger:** Round 2 (`state-transition-table` lens) and round 6 (`state-completeness`,
`regression-audit` lenses) StructuredOutput failures during H-REVIEW-COMMIT-1 plan-check,
despite the two mitigations from `feedback_workflow_structured_output_fragility.md`
(array-shaped schemas; explicit "put content in the array not the summary field" prompt
instruction) already being applied.

## TL;DR — the actual mechanism

This is **a third, distinct root cause**, not a recurrence of the two previously documented
ones. It is a **known, open bug in the Claude Agent SDK's `StructuredOutput` tool**: the
model intermittently emits the tool call's arguments **double-wrapped** —
`{"input": "<the-entire-JSON-payload-as-a-string>"}` — instead of passing the schema's
fields (`pass`, `summary`, `gaps`) as **top-level tool-call parameters**. The SDK validates
the *root* of the tool-call arguments against the schema, so it sees only a key named
`input` (or a JSON string that was never parsed as an object) and reports
`"root: must have required property 'pass', root: must have required property 'summary'"`
— even though `pass` and `summary` are both present, just nested one level too deep. This
is a tool-invocation-shape bug, not a schema-design or "ran out of room" problem, and it is
**independently reproduced by all three failure symptoms** in this session plus two other
open GitHub issues describing the identical signature in unrelated projects.

This is upstream of loop-team entirely — nothing in the Workflow script's schema
construction, prompt wording, or the lenses' own reasoning caused it.

## Evidence: real transcript quotes

### Round 6, `state-completeness` lens (total failure, retry cap exceeded)

Agent ID `a220d5d59c3ce9fad`, transcript:
`~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_c730034f-60a/agent-a220d5d59c3ce9fad.jsonl`

All 5 StructuredOutput attempts (lines 102, 104, 107, 110, 113 of the JSONL), verbatim
`input` field shape on every single attempt:

```
attempt 1: {'input': '{\n  "pass": false,\n  "summary": "STATE-COMPLETENESS lens, round 6. ...'}
attempt 2: {'input': '{"pass": false, "summary": "STATE-COMPLETENESS lens, round 6. ...'}
attempt 3: {'input': '{\n  "pass": false,\n  "summary": "STATE-COMPLETENESS lens, round 6, fully live-verified. ...'}
attempt 4: {'input': '{"pass": false, "summary": "test"}'}     <- minimal probe, still wrapped
attempt 5: {'input': '{"pass": false, "summary": "STATE-COMPLETENESS lens, round 6, fully live-verified. ...'}
```

Every attempt returned the identical tool_result:
```
Output does not match required schema: root: must have required property 'pass', root: must have required property 'summary'
```

The model's own diagnostic reasoning at line 109 ("Even the minimal call fails, indicating
a tool-calling issue rather than a schema content issue") correctly diagnosed the *class*
of bug but never landed on the fix (drop the `input` wrapper key) within its 5-attempt
budget. All 5 attempts used real, substantive, non-degenerate content (attempt 4's `"test"`
was an isolated minimal-repro probe, not the final answer) — this agent simply ran out of
retries while still wrapped incorrectly. This matches the SDK's documented
`error_max_structured_output_retries` subtype exactly (see Sources).

### Round 6, `regression-audit` lens (degenerate "test" output — schema-valid, content-empty)

Agent ID `a739ccdd64896b2f0`, same workflow dir,
`agent-a739ccdd64896b2f0.jsonl`.

```
attempt 1 (line 118): {'input': '{\n  "pass": true, ...REGRESSION-AUDIT lens, round 6. Live-verified against the real hooks/loop_stop_guard.py...'}  -> rejected
attempt 2 (line 120): {'input': '{"pass": true, "summary": "REGRESSION-AUDIT lens, round 6. Live-verified...'}   -> rejected
attempt 3 (line 123): {'input': '{\n  "pass": true, ...round 6, live-verified. All re-checked numeric/structural claims hold...'}  -> rejected
attempt 4 (line 126): {'input': '{"pass": true, "summary": "test"}'}   -> rejected (minimal probe)
attempt 5 (line 129): {'pass': True, 'summary': 'test'}   -> "Structured output provided successfully"
```

This is the mechanism for the "degenerate output" symptom, fully explained: the agent
correctly self-diagnosed on its 4th attempt to strip down to a minimal reproduction case
(`{"pass": true, "summary": "test"}`, still wrapped in `input` — still rejected). On its
5th and FINAL retry it discovered the real fix (drop the `input` wrapper, pass fields at
top level) — but by then its only remaining attempt carried forward the **literal minimal
probe payload** (`"test"`) rather than its real, substantive review content from attempts
1–3. It had one shot left and spent it confirming the fix worked, at the cost of the actual
content. This is not "abandoned a real review and substituted a placeholder" in the sense
of giving up — it's "spent all retry budget on tool-shape debugging, had zero budget left
to re-attempt with both the correct shape AND the real content in the same call."

This is a different, sharper mechanism than the general `H-DEGENERATE-OUTPUT-1` class
documented in `fix_plan.md` (which describes unexplained content-empty-but-schema-valid
output with no evidence of *why*). Here we have the exact turn-by-turn why: a retry-budget
collision between "fix the tool-call shape" and "carry the real payload," where the model
spent 4 of 5 attempts on shape-diagnosis using content it kept trying to preserve, then
degraded to a minimal probe on attempt 4, and had no budget left to restore full content
once attempt 5 finally worked.

### Round 6, other 3 lenses (comparison — same bug, different luck)

| Agent (lens) | Attempts wrapped in `input` | Attempt that used top-level keys | Outcome |
|---|---|---|---|
| `ac7228afcbe9cc177` (state-transition-table) | 0 | 1st (immediate) | PASS, full real content |
| `a3aeeef99c519966c` (precision-of-instruction) | 2 | 3rd | PASS, full real content |
| `a6fdbe96e9b1da287` (concurrency-isolation) | 4 | 5th (last try) | PASS, full real content (survived — got lucky landing the fix with content still intact on the final attempt) |
| `a739ccdd64896b2f0` (regression-audit) | 4 | 5th (last try) | PASS but degenerate ("test") — same as above but the 5th attempt's content had already been reduced to the minimal probe |
| `a220d5d59c3ce9fad` (state-completeness) | 5 (all) | never | **Total failure**, retry cap exceeded |

This table is the clearest evidence of the mechanism: **whether a lens survives is a race
between "attempts remaining" and "does the model happen to try unwrapping `input` before
attempt 5," not anything about how much real work the lens did or how complex its
findings were.** `a6fdbe96e9b1da287` and `a739ccdd64896b2f0` both landed the fix on their
literal last allowed attempt — one got lucky (content was still the real payload in that
attempt's draft), the other didn't (content had degraded to the minimal probe by then).

### Round 2, `state-transition-table` lens (total failure, retry cap exceeded)

Agent ID `a2eaed8f3a3b4e70c`,
`~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_eff6d9c8-510/agent-a2eaed8f3a3b4e70c.jsonl`

Same exact signature, 5/5 attempts wrapped:
```
attempt 1 (line 21): {"input": "{\n\"pass\": false,\n\"summary\": \"Built the full state-transition grid...\...
attempt 2 (line 24): {"input": "{\n\"pass\": false,\n\"summary\": \"Built the full state-transition grid...\...  (removed a nonexistent key, still wrapped)
attempt 3 (line 27): {"input": "{\"pass\": false, \"summary\": \"test\"}"}   (minimal probe, still wrapped)
attempt 4 (line 30): {"input": "{\"pass\": false, \"summary\": \"Round-2 STATE TRANSITION TABLE lens: PLAN_FAIL. See gaps array for full detail.\"}"}   (still wrapped)
attempt 5 (line 32): {"input": "\n{\n  \"pass\": false,\n  \"summary\": \"Round-2 STATE TRANSITION TABLE lens: PLAN_FAIL.\"\n}\n"}   (still wrapped, now input is a bare string not even a dict)
```

Critically, this agent's transcript is only 34 lines total (vs 115 for the round-6
state-completeness failure) — it had done comparatively little work (one spec read, 3
targeted greps/reads of source files) before its first StructuredOutput call. This directly
falsifies the "deep-reasoning tasks running out of room" hypothesis from the earlier
memory as the explanation for *this* failure class: the round-2 agent failed on its very
first structured-output attempt, with plenty of context budget left, for a reason
completely unrelated to reasoning depth or tool-call count. The bug is present from the
first StructuredOutput call regardless of how much prior work was done — "amount of real
work before the schema call" is not correlated with triggering the bug (it IS correlated,
independently, with whether the agent has *time/attempts* to discover the fix before
running out of retries, and with whether it still has the *original* content on the
attempt that lands the fix).

## Confirmed: this is a known, open Claude Agent SDK bug, not a loop-team-specific issue

Three GitHub issues on `anthropics/claude-agent-sdk-python` describe the identical
mechanism:

- **[Issue #571](https://github.com/anthropics/claude-agent-sdk-python/issues/571)**
  ("StructuredOutput tool fails when agent wraps output in `{\"output\": {...}}`"),
  closed as duplicate of #502. Exact quote of the failing case:
  ```json
  {"output": {"as": 4, "xs": "xzy"}}
  ```
  producing:
  ```
  Output does not match required schema: root: must have required property 'as', root: must have required property 'xs', ...
  ```
  vs the succeeding case, fields at top level:
  ```json
  {"as": 2, "xs": "zxa"}
  ```
  This is the exact same shape of bug we observed (our wrapper key was literally named
  `input` rather than `output`, but the mechanism — an extra nesting level around the
  payload that the SDK validates at the root — is identical). The issue also links **PR
  #532**, described as addressing "wrapper key issues and stringified JSON in structured
  output," noted as possibly not fully covering this case.

- **[Issue #502](https://github.com/anthropics/claude-agent-sdk-python/issues/502)**
  ("StructuredOutput tool wraps data in 'output' field causing schema validation to
  fail"), still **open** at last check. Confirms the bug is **intermittent/non-deterministic
  — "the same prompt can produce either format"** — exactly matching what we observed
  (4 of 5 lenses in round 6 eventually escaped the wrapping bug on a later attempt; 1 did
  not). Also documents a second-order effect: *"Agent confusion — Claude sees conflicting
  validation errors and may simplify output (e.g., 47 items → 1 item)"* — this is the
  documented mechanism for exactly the content-degradation we observed in the
  `regression-audit` lens (47→1 items in their repro is the same shape of degradation as
  our real-review→`"test"` degradation: the model, faced with a validation error it
  doesn't understand, starts shedding content rather than fixing the actual (invisible to
  it) structural problem).

- **[Issue #374](https://github.com/anthropics/claude-agent-sdk-python/issues/374)**
  ("Structured outputs seems to be flaky"), closed as duplicate of #502. Reporter's exact
  words: *"it seems that Claude is sometimes calling its internal tool `StructuredOutput`
  with a string that contains the object instead of the actual object. It then keeps
  looping to try to understand why the tool call is failing."* — this is a precise
  description of what all 5 of our failing/near-failing transcripts show turn-by-turn.

- **Official docs**
  ([code.claude.com/docs/en/agent-sdk/structured-outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs))
  confirm the default retry cap and the two failure subtypes:
  > "Structured output generation can fail when the agent cannot produce valid JSON
  > matching your schema. This typically happens when the schema is too complex for the
  > task, the task itself is ambiguous, or the agent hits its retry limit trying to fix
  > validation errors. It can also happen without any validation failure: a model fallback
  > can retract an already-completed output mid-stream..."
  and the retry-exhaustion subtype is literally named `error_max_structured_output_retries`
  — matching this session's own error message verbatim ("StructuredOutput retry cap (5)
  exceeded"). The docs' "Tips for avoiding errors" section (keep schemas focused, match
  schema to task, use clear prompts) does **not** mention the wrapper-key bug at all —
  confirming this is an undocumented SDK defect, not a documented usage constraint we're
  violating.

## Why this is a genuinely different root cause from the two already in memory

`feedback_workflow_structured_output_fragility.md` documents:
1. Fragile string-keyed schemas (e.g. free-form address keys) — not applicable here; this
   session's schemas are `pass`/`summary`/`gaps` (array), already the fixed shape.
2. Deep-reasoning tasks running out of "room" and dumping malformed text into a free-text
   field instead of properly invoking the schema — falsified by the round-2 case (34-line
   transcript, first StructuredOutput call, plenty of budget remaining, still wrapped).

Neither prior root cause explains: (a) the model successfully constructing valid,
well-formed JSON with all required fields, in the right shapes, every single time — the
JSON is never malformed — but placing it one key too deep; (b) this happening on the
very first attempt with minimal prior work; (c) an already-known upstream GitHub issue
with the identical reproduction shape existing independently of this project. This is a
**third, distinct root cause**: an SDK-level tool-call-argument-shape bug in how the model
invokes `StructuredOutput` when tool_choice is forced, unrelated to schema complexity or
context pressure.

## Mitigation — evidence-backed, not a generic restatement

The existing two mitigations (array schemas, prompt discipline about summary vs gaps) are
correctly targeted at the two *previously* documented root causes and should stay, but
they cannot fix this one because this bug occurs after the model has already correctly
composed the payload — the wrapping happens at the tool-call-argument level, which prompt
instructions about *content* placement cannot reach reliably (as proven: several lenses
in this very session followed the "put content in the array, not summary" instruction
correctly and STILL got wrapped in `input` on their first tries).

**Recommended fix, ranked:**

1. **(Best, structural) Post-process/unwrap centrally rather than rely on the model.**
   Per PR #532 and the open issues, the SDK does not yet reliably self-correct. Loop-team's
   own Workflow-dispatch wrapper (wherever `agent()` + `.catch()` is called per-lens) should
   inspect a captured raw tool-call payload for the `{"input": "<json-string>"}` shape and
   unwrap+re-validate before treating a `pass:null`/thrown result as unrecoverable. This
   requires access to the raw StructuredOutput tool-call arguments, not just the final
   `ResultMessage.structured_output` — check whether the Workflow tool's `agent()` wrapper
   exposes intermediate tool calls or only the final result; if only the final result is
   exposed, this mitigation is not implementable from the caller's side and the real fix
   has to happen upstream (see #2).
   - **Falsifiable test:** re-run a batch of N lens dispatches with this unwrap-and-retry
     shim in place vs without; measure `error_max_structured_output_retries` rate and
     degenerate-content rate (via the existing `research_authenticity_check.py` scan,
     since it already flags identical-values/short-field content) before vs after.

2. **(Upstream, out of our control) Track/upvote the open SDK issues.** Issue #502 is open
   with a linked PR (#532) already in flight; a version bump once that PR merges may
   resolve this at the source. Until then, this is a known, intermittent, unfixed defect —
   not something a prompt or schema change on our side can close, because the bug fires
   even on trivial minimal-content probes (`{"pass": true, "summary": "test"}`) that no
   reasonable schema simplification would improve.

3. **(Partial mitigation, budget-shape) Raise effective retry survivability by keeping the
   FIRST attempt's payload byte-for-byte identical to later attempts.** Every failing/
   near-failing transcript shows the model **changing content between retries** while also
   fighting the wrapping bug (removing keys it guessed were the problem, shortening the
   summary, eventually substituting `"test"` as a debug probe) — conflating two different
   debugging problems (content validity vs call shape) burns through the fixed 5-attempt
   budget faster than necessary. A stronger prompt instruction — "if a StructuredOutput
   call is rejected with a 'must have required property' error despite your having
   included that property, the problem is very likely that your call's arguments got
   wrapped in an extra outer key (e.g. `input` or `output`) — retry with the EXACT SAME
   field values but remove any outer wrapping key so `pass`, `summary`, and `gaps` are
   direct top-level tool-call parameters, do not change the content" — is not a
   restatement of "make schemas simpler"; it targets the SPECIFIC, now-evidenced failure
   signature and would let a model that hits this bug spend its retry budget on the actual
   fix (unwrap) instead of on content-guessing, which is what let 3 of 5 round-6 lenses
   survive by luck alone. This is a real mitigation grounded in the transcript evidence
   (none of the 5 self-diagnosed the *exact* fix from the error message alone; the
   fastest self-correction, `ac7228afcbe9cc177`, got it right on attempt 1 essentially by
   chance, not by reasoning about the error).
   - **Falsifiable test:** A/B the prompt addition across a batch of forced-retry
     StructuredOutput scenarios (can synthetically induce via a schema with a
     deliberately-similar-shaped nested `input`/`output` field name to bait the same model
     behavior) and measure attempts-to-success and degenerate-content rate.

**What NOT to do:** do not simplify the `gaps` array schema further, do not add more
prompt instructions about content placement (summary vs gaps) — those already work and
are not implicated by any of the 5 transcripts examined. That would be re-treating the
already-fixed root causes while leaving the actual (SDK tool-call-shape) bug untouched.

## Sources

- [Issue #571 — StructuredOutput tool fails when agent wraps output in `{"output": {...}}`](https://github.com/anthropics/claude-agent-sdk-python/issues/571) (closed as duplicate of #502)
- [Issue #502 — StructuredOutput tool wraps data in 'output' field causing schema validation to fail](https://github.com/anthropics/claude-agent-sdk-python/issues/502) (open; PR #532 referenced as related fix)
- [Issue #374 — Structured outputs seems to be flaky](https://github.com/anthropics/claude-agent-sdk-python/issues/374) (closed as duplicate of #502)
- [Claude Agent SDK docs — Get structured output from agents](https://code.claude.com/docs/en/agent-sdk/structured-outputs) (retry-cap behavior, `error_max_structured_output_retries` subtype, no mention of the wrapper-key bug in "Tips for avoiding errors")
- Local transcripts (primary evidence, this investigation):
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_c730034f-60a/agent-a220d5d59c3ce9fad.jsonl` (round 6, state-completeness, total failure)
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_c730034f-60a/agent-a739ccdd64896b2f0.jsonl` (round 6, regression-audit, degenerate "test" output)
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_c730034f-60a/agent-a6fdbe96e9b1da287.jsonl` (round 6, concurrency-isolation, survived by landing the fix on its final attempt)
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_c730034f-60a/agent-a3aeeef99c519966c.jsonl` (round 6, precision-of-instruction, self-corrected on attempt 3)
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_c730034f-60a/agent-ac7228afcbe9cc177.jsonl` (round 6, state-transition-table, correct on attempt 1)
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_c730034f-60a/journal.jsonl` (round 6 workflow-level event log — 5 started, 4 results, confirming the total-failure agent)
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_eff6d9c8-510/agent-a2eaed8f3a3b4e70c.jsonl` (round 2, state-transition-table, total failure — matching signature with minimal prior work)
  - `~/.claude/projects/-Users-eobodoechine/e9c9c498-8820-425f-9b27-307933e76b2e/subagents/workflows/wf_eff6d9c8-510/journal.jsonl` (round 2 workflow-level event log — 5 started, 4 results, confirming the total-failure agent)
- `~/Claude/loop/fix_plan.md` — `H-DEGENERATE-OUTPUT-1` entry (2026-07-02 prior instance of degenerate schema-valid-but-empty content; this investigation supplies the first turn-by-turn causal mechanism for that failure class, at least for this trigger — the retry-budget collision between fixing tool-call shape and preserving real content)
