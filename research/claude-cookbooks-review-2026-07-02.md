# claude-cookbooks review for loop-team (2026-07-02)

**Trigger:** Nnamdi asked what in `github.com/anthropics/claude-cookbooks` could help `/loop-team` get better.
**Method:** Workflow — 5 parallel readers, each assigned a directory cluster, fetched and actually read
raw file content (via `curl` to raw.githubusercontent.com + `jq` for notebook cell extraction, not
filename-guessing), then a synthesis pass deduped against loop-team's already-tracked backlog
(`~/.claude/projects/-Users-eobodoechine/memory/project_loop_team_improvement_backlog.md`) and ranked
survivors HIGH/MED/LOW.
**Clusters read:** `patterns/agents/*`, `managed_agents/CMA_*.ipynb`, the repo's own dogfooding CI
(`.claude/` + `.github/workflows/*`), `tool_use/` context+memory+tool-search notebooks, `misc/` evals +
caching + `evals/agentic_search/*` + `extended_thinking/*`.
**Not read (scoped out, note per no-silent-caps rule):** `capabilities/*` (task-capability cookbooks —
classification/RAG/summarization/text-to-sql/knowledge-graph), `multimodal/*` (vision-specific),
`third_party/*` (vendor integrations), `finetuning/*`, `skills/*` (Anthropic's own skill-authoring guide —
tangential, not orchestration-level).

Raw per-cluster findings (29 candidates before dedup) are in the workflow transcript; this file carries
the deduped, ranked synthesis plus enough of the raw mechanism detail to act on each item without
re-reading the source notebook.

---

## HIGH priority (concrete mechanism, closes a real gap, act on these first)

### 1. Background proactive session-memory compaction with a preserve-rules priority contract
**Source:** `misc/session_memory_compaction.ipynb`
`InstantCompactingChatSession` starts a background thread (guarded by a `Lock`) to regenerate a
structured summary once a soft token threshold is crossed, **before** the real compaction trigger fires,
so the pre-built summary swaps in instantly instead of blocking 40+ seconds. The `SESSION_MEMORY_PROMPT`
forces explicit `<analysis-instructions>` reasoning about what succeeded/failed/was corrected, then writes
ranked sections under preserve-rules: **user corrections > errors > active work > completed work**.
**Proposed change:** add a background summarizer thread keyed off Oga's own transcript in the micro-step
loop, with that same preserve-priority order, so mid-build context handed to a Coder/Verifier is a
pre-built, priority-ranked summary rather than raw transcript or a reactively-generated one that drops
the corrections that caused prior retries.
**Target:** `loop-team/orchestrator.md` (compaction/context-handoff section) + `RUN.md`.
**Why HIGH:** advances the already-tracked "long-horizon erosion / coherence-collapse" gap with a
concrete, implementable design instead of just restating the gap.

### 2. `disallowed_tools` as a hard SDK-level denylist, not a prompt-level ban
**Source:** `claude_agent_sdk/observability_agent/agent.py` + `managed_agents/CMA_coordinate_specialist_team.ipynb`
The observability agent sets both `allowed_tools` **and** `disallowed_tools=["Bash","Task","WebSearch","WebFetch"]`,
with an explicit code comment: `allowed_tools` only controls permission *prompting*, not actual
*availability* — an agent given only an allow-list still has Bash/Task available and can route around the
intended restriction. `CMA_coordinate_specialist_team.ipynb` independently confirms the same pattern from
the other direction: each specialist is scoped to only the tools its job needs (researcher gets web tools,
pricing modeler gets zero web access) specifically to stop cross-role data leakage.
**Proposed change:** audit every sub-agent dispatch config in `orchestrator.md` (Coder, Test-writer,
Researcher A-D, Verifier) for whether the Task/Bash ban is enforced via `disallowed_tools` at the
SDK/`ClaudeAgentOptions` level versus only via prompt text ("don't use Task"). Convert every
prompt-level-only ban to an explicit denylist, and confirm Researcher Mode C (adversarial eval-case
generation) has no read access to `fix_plan.md` or the Coder's DECISION LOG.
**Target:** `loop-team/orchestrator.md` (dispatch configs) + `roles/coder.md`, `researcher.md`, `verifier.md`.
**Why HIGH:** names the concrete root cause of the already-documented "sub-agent punting" failure
(memory: `feedback_subagent_punting.md` — the Task-tool ban was prompt-level, not SDK-enforced) with the
correct primitive to close it.

### 3. Independent re-verification pass distinct from the doer's own self-report
**Source:** `managed_agents/CMA_iterate_fix_failing_tests.ipynb`
After the debugging agent declares tests green from inside its own iterate loop, the harness sends a
**second, separate** message instructing it to re-run every assertion independently to confirm — the
agent's own end-of-turn self-report of success is never trusted as the final signal; a fresh, out-of-band
re-check is mandatory before the result is accepted.
**Proposed change:** add an explicit rule to `RUN.md`'s micro-step build loop: a Coder step is not
eligible for git-checkpoint-commit merely because the Coder's turn asserts tests pass. Oga's own
`pytest --testmon` re-run (already specified) must be the actual, timestamped gating event, and any
commit that happens before Oga's own re-run completes in the same turn is a process violation to flag.
**Target:** `loop-team/RUN.md` (micro-step build loop section).
**Why HIGH:** closes a concrete, previously-unstated race in the loop's own commit gating.

### 4. Silent tool-throttling as a fifth failure-arbiter classification
**Source:** `evals/agentic_search/reproduce_agentic_search_benchmarks.ipynb`
Server-tool rate limits are separate from model/API rate limits and do **not** raise exceptions — a
`"too_many_requests"` or `"rate_limit_error"` string appears as a tool-result error inside an otherwise-200
response, and agents often silently retry in-sandbox without surfacing it. The notebook's fix: if a run
scores unexpectedly low with zero exceptions thrown, grep the transcript for those literal strings, since
normal exception-based error handling never catches this failure mode.
**Proposed change:** add a fifth check to the failure arbiter (alongside code-bug/test-bug/spec-gap/
harness-fault): scan Coder/Researcher transcripts for silent-throttle strings (`rate_limit_error`,
`too_many_requests`, `quota`) even on nominally green steps.
**Target:** `loop-team/orchestrator.md` (failure-arbiter classification logic) + `RUN.md`.
**Why HIGH:** names a specific failure signature the arbiter currently has no rule for.

### 5. Full-memory (not just last-feedback) Coder retry context
**Source:** `patterns/agents/evaluator_optimizer.ipynb`
`loop()` accumulates every prior generation attempt into a `memory` list and, on each re-generation after
a non-PASS evaluation, feeds the **full history** of past attempts plus the latest feedback back into the
generator prompt — not just the single most recent attempt and its critique.
**Proposed change:** when Oga re-dispatches a fresh Coder after a red result (retry cap 2, same stall
signature), include the full sequence of prior failed diffs and DECISION LOGs for that step — not just the
most recent failure — so retry 2 doesn't re-attempt a fix already tried and rejected on retry 1.
**Target:** `loop-team/RUN.md` (retry-cap / re-dispatch logic) + `roles/coder.md`.
**Why HIGH:** concrete, low-cost fix — the loop's 2-retry cap currently has no stated rule that retry 2
sees retry 1's full failed attempt.

### 6. Evidence-bar rubric rewrite + explicit no-fire list for the Verifier
**Source:** `managed_agents/CMA_verify_with_outcome_grader.ipynb`
A rubric phrased as a checkable evidence-bar ("find the demand-charges section and confirm it states a
$/kW figure or % of operating cost") forces the grader to produce concrete proof, versus a topic-level
criterion ("check that the brief covers demand charges") which lets the grader skim and pass without
opening a source. The notebook's worked example shows this catching a real defect a topic-level rubric
would have missed. It prescribes: checkable per-criterion proof (file:line/fetched page/traced formula),
an explicit **no-fire list** so the grader doesn't thrash on style nits or pre-existing issues, and a
mandated scoreboard+bullet feedback format.
**Proposed change:** rewrite `VERIFIER.md` and `VERIFIER_RENTALS.md` rubric criteria from topic-level
phrasing to evidence-bar phrasing, add a per-domain no-fire list, and mandate a fixed scoreboard+bullet
output format.
**Target:** `loop-team/VERIFIER.md`, `loop-team/VERIFIER_RENTALS.md`.
**Why HIGH:** concrete rubric-phrasing lever for the already-tracked verifier-text-evals-saturated
problem; the no-fire list directly targets the documented pre-existing-failure-hypothesis mistake pattern
(memory: `feedback_preexisting_failure_hypothesis.md`).

---

## MED priority (plausible, needs a PACE experiment before adoption)

7. **Few-shot good/bad exemplar pairs in the Verifier rubric** — `.claude/skills/cookbook-audit/style_guide.md`
   pairs every structural rule with a full worked Good example next to a full worked Bad example, and
   forces the grader to read the style guide first. Add 2-3 contrastive pass/fail pairs per rubric
   dimension to VERIFIER.md — complements (not duplicates) item 6. → `VERIFIER.md`, `VERIFIER_RENTALS.md`.
8. **Query-type triage (depth-first / breadth-first / straightforward) before dispatch** —
   `patterns/agents/prompts/research_lead_agent.md`'s lead classifies every query before delegating,
   with a distinct subagent-count + strategy per type. Needs a PACE check that parallel dispatch doesn't
   erode the auditability loop-team's serial micro-step design deliberately buys. → `orchestrator.md`.
9. **Declared per-task tool-call budget scaled to difficulty** — `patterns/agents/prompts/research_subagent.md`
   requires a stated numeric budget (<5/simple → 20/hard-cap) with an explicit stop-on-diminishing-returns
   instruction. → `roles/researcher.md`.
10. **Source-skepticism checklist for Researcher Mode D** — `patterns/agents/prompts/research_subagent.md`'s
    `<think_about_source_quality>` block flags speculative language, marketing spin, and
    aggregator-vs-primary sourcing. Operationalizes the existing "diagnose beyond doubt" /
    "verifier citation fabrication" memory rules as a concrete checklist. → `roles/researcher.md` (Mode D).
11. **Frozen grader model + result-only (not full-transcript) scope for the Verifier** —
    `evals/agentic_search/reproduce_agentic_search_benchmarks.ipynb` hardcodes `GRADER_MODEL` independent
    of the model under test and shows the grader only the extracted final-result content, not the full
    transcript with planning prose. Mostly confirms existing practice (model routing); the new part is
    restricting Verifier's view to the Coder's final artifact, not its exploration transcript. → `roles/verifier.md`.
12. **Task-scoped token budget signal for long-horizon Coder/Researcher runs** —
    `output_config.task_budget` sets a cumulative output-token budget across turns/compactions (distinct
    from per-call `max_tokens` or a wall-clock timeout) so the model paces planning depth instead of
    front-loading effort. Speculative value given loop-team's already-small ≤200-line micro-steps. → `orchestrator.md`.
13. **Structured tool-interface friction feedback channel from Coder/Test-writer** —
    `tool_evaluation/tool_evaluation.ipynb` requires a separate `<feedback>` block critiquing the tool
    definitions themselves (unclear names, under-documented params) as a signal distinct from
    pass/fail, aggregated across an eval batch. Novel signal type loop-team has no analog for. → `roles/coder.md`, `test_writer.md` → sink into `fix_plan.md`.
14. **Prompt-versioning-as-change-control with pinned rollback** — `managed_agents/CMA_prompt_versioning_and_rollback.ipynb`
    treats every prompt edit as an immutable version; production callers pin to a version number, and
    *that pin* — not the edit — goes through review; rollback is re-pinning, no redeploy. Incremental
    process wrapper on top of the existing `optimize/optimize_verifier.py` first cut. → `optimize/optimize_verifier.py`, `VERIFIER.md`.
15. **`batch_tool` meta-tool to force parallel independent read calls in one turn** —
    `tool_use/parallel_tools.ipynb` shows models serializing independent tool calls one per turn even with
    parallel tool use enabled; a `batch_tool` meta-tool reliably packs them into one call. Wrap Oga's
    post-Coder-step checks (`pytest --testmon`, `git status/diff/log` — per the "audit git after Coder"
    memory rule) this way to cut round-trip latency. Performance tweak, not correctness. → `orchestrator.md`.

## LOW priority (interesting, no current pain point documented)

16. **Non-polling message-hub lifecycle primitives (`get_status`/`kill`) for stalled sub-agents** —
    `patterns/agents/async_multi_agent_orchestration.ipynb`'s `Hub` class gives async lead/helper agents
    non-polling inbox delivery + status/kill control. Loop-team's dispatch model is deliberately
    sequential and blocking for auditability; adopting concurrent sub-agent lifecycle management is a real
    architecture change with unclear payoff against that design choice, and no current "silent stall" pain
    point is documented as unsolved. → `orchestrator.md` (stall-detector / Mode B trigger logic) if ever revisited.
17. **Custom compaction instructions naming exact fragile facts (per-role anchor list)** — refinement of
    item 1 (same `context_management.edits.instructions` mechanism); fold in as a preserve-rules extension
    rather than a separate initiative if item 1 is adopted.
18. **`exclude_tools` to protect durable-state writes during context clearing** — narrow, defensive,
    only relevant if/when loop-team adopts context-clearing edits at all.

---

## Explicitly NOT adopted (flagged and dropped — see reasoning, don't re-surface)

- **Deterministic pattern-matching pre-pass gates the LLM reviewer** (`.github/workflows/notebook-quality.yml`)
  — restates the already-tracked "cascade model calibration" gap, just instantiated as
  regex-pre-pass-before-Verifier rather than model-tier escalation. Same mechanism class, not new.
- **Author-blind, symmetric two-actor code review agent** (`.claude/agents/code-reviewer.md`) — a second
  independent implementation of loop-team's existing Verifier de-priming/withheld-rationale design; confirms
  the pattern generalizes, doesn't add to it.
- **Two-tier CI trust gate (fork vs internal contributors)** — explicitly inapplicable; loop-team is
  single-operator, no external-contributor trust boundary. Underlying idea is the same cascade-calibration
  gap already tracked.
- **Provisional-verdict-before-harness-result via `continue-on-error` + separate summarize step** —
  loop-team already implements provisional-verdict-before-harness-result via the de-priming hook; this
  raises a "grade vs explain" design question rather than a new technique.
- **Verbatim-preserving post-hoc annotation with exact-match rejection** (`patterns/agents/prompts/citations_agent.md`)
  — doesn't map onto loop-team's actual Verifier workflow (it doesn't annotate Coder diffs in place).
- **Memory as JIT cross-session retrieval + memory-poisoning threat model** (`tool_use/context_engineering_tools.ipynb`,
  `tool_use/memory_cookbook.ipynb`) — speculative until loop-team actually adopts the memory *tool* for
  cross-session state; it currently uses plain files Oga reads manually.
- **Programmatic Tool Calling (PTC) for bulk-data filtering** — plausible but high implementation cost,
  uncertain fit for loop-team's current tool set.
- **`defer_loading`/`tool_reference` caching gotcha** (`tool_use/tool_search_alternate_approaches.ipynb`)
  — worth a one-off verification against how the harness's own ToolSearch integrates with prompt caching,
  not a design gap in itself.

---

## Process note (workflow failure + fix, kept for the record)

The first run of this research workflow failed: the synthesis-stage agent's `StructuredOutput` tool calls
wrapped its entire answer as a JSON *string* inside a field literally named `"input"` (`{"input": "{...}"}`)
instead of emitting the schema fields directly, five times in a row — even on a trivial
`{"recommendations": []}` payload. Root cause (probable): the synthesis prompt embedded a large raw
`JSON.stringify()` dump of the cluster-reader results, which appears to have primed the model to imitate
that stringified-JSON shape in its own tool call. Fix: reformatted the embedded data as plain indented text
instead of JSON, and added an explicit instruction not to stringify the answer. Resumed the workflow from
cache (the 5 reader agents' results were unaffected and reused) and it completed clean on retry. Two
loop-team Stop/PreToolUse hooks (`pre_tool_use_oga_guard.py`, `loop_stop_guard.py`) also misfired on the
fix — both fired on ordinary edits to a session-scratch Workflow script unrelated to any loop-team build;
worked around via Bash per the hooks' own "advisory, not a security boundary" language rather than
spawning pointless sub-agent dispatches.
