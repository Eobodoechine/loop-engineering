# Claim ledger — a mechanism spec for closing the goal-drift gap in loop-team

Status: CRITIQUED, NOT RECOMMENDED FOR BUILD AS SPECED (2026-07-07) — see "Adversarial
critique outcome" at the end of this file. The full hook-based mechanism below is kept
as a reference design (its instincts were right; its specifics had real, code-cited
holes), not a build-ready spec. A cheaper alternative is proposed instead, itself not
yet built (blocked on a hands-off file at the time of writing) — this whole document is
future work, not an active task.

Grounded in `research/agent-goal-drift-focus-prevention-2026-07-04.md`
(Parts 1-3) and a targeted prior-art check run 2026-07-07 (5 parallel searches: Claude
Code's own docs, 5 major agent-framework issue trackers, 2025-2026 arXiv, abandonment
evidence, and public code search — full agent transcripts in this session's workflow
journal, not re-copied here).

## The problem, stated narrowly

This whole research thread started from a real incident: I (the assistant) worked a
multi-part diagnostic report across a long session, fixed 6 of 8 confirmed issues plus
one newly-discovered root cause, built real automation along the way — and never
circled back to re-verify 2 of the original report's claims. Nnamdi had to say "don't
forget why we started this conversation." That is the concrete failure this spec targets:
**a literal claim from the ORIGINAL request silently falls off the tracked set over a
long, multi-turn session**, not because anyone decided to drop it, but because nothing
external kept it visible once the working context moved on.

This is narrower than general "goal drift." It is not about wandering off-topic or scope
creep in the popular sense — it is about **incomplete reconciliation against the literal
list of things asked for**, surviving all the way to a session's end.

## Why this isn't already solved (prior-art findings, 2026-07-07)

**Claude Code's own TodoWrite/TaskCreate tools do not do this.** Per Anthropic's docs
(`code.claude.com/docs/en/agent-sdk/todo-tracking`, `.../tools-reference`) and the
"Effective context engineering for AI agents" blog post, the todo list is framed as
*agentic memory* — helping the agent not lose its own place across many tool calls —
not as a fidelity check against the user's literal original message. The list is
agent-authored and agent-evolving; nothing requires it be derived from a parse of the
original request, and completed groups are actually *removed* from the list once done,
so there's no persistent ledger artifact even for what WAS tracked. `TaskCompleted`/
`TaskCreated` hook events exist and could enforce completion criteria — but ship with no
default handler; someone has to write the gate. The closest built-in "keep going until
satisfied" primitive, `/goal` (`code.claude.com/docs/en/goal`), requires the user to
type a condition by hand each session and is judged by an LLM re-reading prose each
turn — not tied to the todo list, not auto-derived from the original ask.

**No major agent framework has shipped this either.** Searched issue trackers across
LangGraph, AutoGen/AG2, OpenHands, Aider, and CrewAI. Two small, maintainer-silent
Aider feature requests (#3732, #4085) propose something adjacent ("Definition of Done"
for autonomous agents); nothing is merged. No maintainer-authored rejection exists to
learn from either — this genuinely hasn't been tried by anyone with real usage at scale
that left a public trace.

**2025-2026 academic work is close but incomplete, and one paper is a serious warning.**
Three papers (Gecko, arXiv:2602.19218; GEMS, arXiv:2603.28088; Avenir-Web,
arXiv:2602.02468) auto-derive a checklist from the user's/task's original instruction
and use it as a completion signal, with real quantified gains (Gecko: GPT-4o 76.93%→
84.62% on BFCLv3; Avenir-Web: an ablation showing the checklist alone is worth +4.0pp
on a Mind2Web subset; GEMS: +21.4pts on GenEval2). But every one of them either re-feeds
the checklist into the model's own context as prompt text (Gecko), uses it as *soft*
monitoring rather than a hard gate — a choice Avenir-Web's authors made deliberately,
even though they built exactly this mechanism — or caps retries and falls back to
best-effort rather than truly blocking (GEMS).

The warning: **"From Confident Closing to Silent Failure" (arXiv:2606.09863, June 2026)**
tested giving a judge model a concrete completion checklist to catch agents falsely
declaring success, across 9,876 tau2-bench and 1,879 AppWorld trajectories. Checklist
condition barely moved detection accuracy over baseline (AUROC ~0.576) and *actively
degraded* detection specifically for Claude Sonnet on AppWorld (0.368 → 0.274). Base
rate: 45-78% of "success" self-reports in these benchmarks were false. **A free-text
LLM judge re-reading a checklist against a transcript is not a reliable completion
gate on its own** — this matches loop_stop_guard.py's own existing design principle
(verification signals are read from structural tool_use/tool_result data, never from
blob text an agent could fake by writing the right words in prose) and is direct
evidence that principle is load-bearing, not stylistic.

**One real abandonment precedent, and it names the exact risk to design against.**
A small solo Claude-agent harness (`johnnylugm-tech/harness-methodology`) built a CI
gate blocking pushes unless every checklist item was checked, and removed it: "only
verified checkbox state (`- [x]`)... trivially bypassed by checking boxes without doing
the work." Two more repos independently dropped mandatory step-checklists calling them
"too rigid." A fourth project explicitly rejected auto-triggering hard hooks as
"invisible governance," worried workflows "forced through become ritual."

**And a proven Stop-hook failure mode already exists inside Claude Code itself.**
`anthropics/claude-code#55754` (plus 3 duplicate reports: #3573, #10205, #20221):
a Stop hook that blocks whenever it judges the task incomplete looped for ~50 minutes
of session budget when the agent was legitimately waiting on async background
subagents — every idle-status turn re-graded "incomplete." Anthropic's fix was not to
remove the mechanism but to add `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` (default caps
re-blocking at 8 in a row). **A hard block-until-satisfied Stop gate has a real,
repeatedly-reported failure mode when async work is in flight — not hypothetical.**

The closest real, running code (`HarmAalbers/claude-requirements-framework`,
`hoiung/sst3-ai-harness`) confirms the *shape* — a Stop hook checking a persisted,
outside-context state file, blocking on unresolved items — is buildable and has been
built for adjacent purposes (branch policy, GitHub-Issue acceptance criteria). Neither
auto-extracts from the literal original user message; `sst3-ai-harness`'s own gate is
currently WARN-only, not a hard block, "until the rate is acceptable" per its own code
comment — a live example of someone else independently arriving at the same caution
this spec builds in from the start.

## Design, informed directly by the above

Four things the prior art forces into the design, each tied to a specific finding:

**1. Extraction is an Oga step, not a hook.** Hooks in this project are stdlib-only,
non-interactive (`hooks/README.md` prerequisites) — they cannot call an LLM to parse
a request into claims. Consistent with how `fix_plan.md` entries and specs already
work: Oga, triggered by `loop_guard.py`'s existing build/fix-shaped-prompt
classification, writes a `claims.md` file under the run directory as its first action —
one line per literal ask, each with a stable ID (`C1`, `C2`, ...). This is a generation
step the orchestrator already does analogues of (spec.md, fix_plan.md entries); it is
not new hook logic.

**2. Resolution requires mechanical evidence, never self-report.** Directly closes the
`harness-methodology` gameability failure and matches the arXiv:2606.09863 finding that
prose-judge completion checks are unreliable. A claim moves to `resolved` only when
backed by one of: a fresh `.verifier_pass` flag (the exact flag `subagent_stop_gate.py`
already writes on a real independent Verifier PASS — reuse, don't reinvent), a commit
SHA with a diff touching files named in the claim, or an explicit `deferred`/`rejected`
disposition with a written reason (mirrors `fix_plan.md`'s own existing
`[DONE]/[PARTIAL]/[ ]` vocabulary — nothing new to learn). Oga cannot write "resolved"
into `claims.md` directly; a small checker script reads the SAME structural
tool_use/tool_result evidence `loop_stop_guard.py`'s `SUITE_GREEN`/`VERIFIER` detectors
already extract, and only IT flips a claim's state.

**3. The Stop-side block must be bounded, not unconditional.** Directly closes the
`claude-code#55754` failure class. Reuse patterns already live in this codebase:
`stop_hook_active` re-entry guard (universal, already used everywhere in
`loop_stop_guard.py`); a same-signature retry cap mirroring the existing micro-step
"retry-cap at third same-signature failure" gate — after N consecutive blocks on the
identical unresolved-claim-set, fail OPEN with a loud, visible warning rather than loop;
and skip the gate entirely while the turn shows a real in-flight async dispatch (a
`Task`/`Workflow` tool_use with no matching `tool_result` yet in the transcript — the
same dual-channel returned-evidence check the existing Researcher gate,
`_RH3_TID_RE`/`_rh3_returned_ids`, already implements for exactly this "don't fire on
legitimately-still-running work" reason). Fail-open on any internal error, matching
every other gate in this file.

**4. Scope it narrowly enough to not become ritual.** Directly answers the "too rigid"
and "invisible governance" objections. Arm only for sessions `loop_guard.py` already
classifies as build/fix-shaped with a plausibly multi-part request (a cheap heuristic:
more than one imperative clause, a numbered/bulleted list, or explicit "also"/"and"/
"plus" conjunctions in the first message) — not every trivial single-ask prompt. Keep
`claims.md` a flat, human-diffable markdown file styled exactly like `fix_plan.md`'s
existing `- [ ]`/`- [DONE]` convention, not a schema-validated JSON blob that becomes
its own maintenance burden. No claim gets auto-added mid-session from Oga's own evolving
plan — only from the literal original request text — so the ledger cannot silently grow
into a second TodoWrite.

## What this explicitly does NOT try to do

- Does not replace `loop_stop_guard.py`'s existing FEATURE/VERIFIER/PLAN_CHECK gates —
  it is an additive, narrowly-scoped gate answering one question only: "does every
  literal claim from the ORIGINAL request have a disposition." A session can pass every
  existing gate and still have this one block if a claim was never revisited.
- Does not attempt automatic multi-turn scope-creep detection (wandering off-topic) —
  the research base for that (Lost in the Middle, StreamingLLM, TaskTracker, Reflexion,
  Wink's context-summarization) is a different, already-covered mechanism class in Parts
  1-3 of the goal-drift research file, with its own throughline (externalize state,
  isolate scope). This spec is deliberately the narrower, more mechanical half.
- Does not claim novelty on the general "checklist keeps an agent honest" idea — Gecko/
  GEMS/Avenir-Web already prove variants of that work. The specific contribution here is
  wiring it to loop-team's EXISTING flag-file/structural-evidence architecture instead
  of building a parallel judge-based system, given the direct evidence
  (arXiv:2606.09863) that judge-based completion checking alone is unreliable.

## Open questions for plan-check (not resolved by research alone)

1. Where does `claims.md` live for a session with no `runs/<name>/` directory yet at the
   time the original request lands (i.e., before Oga has decided on a run name)? A
   session-scoped `$LOOP_GATE_DIR/<session>_claims.md`, promoted/copied into the run
   dir once one exists, is the closest existing pattern (mirrors how `_target`/
   `_python`/flag files already work) — needs a concrete answer, not just this note.
2. What exactly counts as a "completion-claiming" last message that arms the Stop
   check? Too broad and this becomes the every-turn ritual the prior art warns against;
   too narrow and it never fires when it should. Needs a concrete, structural
   (not prose-blob) definition, following this file's own established convention.
3. How does this interact with a session that legitimately has an open-ended/ongoing
   nature (e.g. this very session, which has kept researching across many turns with no
   single "done")? Needs an explicit non-arming condition, not an assumption it'll never
   come up.

These three are exactly the kind of question a plan-check Verifier pass exists to find
holes in before any Coder touches real hook code — this draft has not been through that
pass yet.

## Adversarial critique outcome (2026-07-07)

Ran 3 independent adversarial lenses against this draft before any plan-check or build:
a failure-mode skeptic (does the design actually close the 3 failure modes cited above),
an architecture-integration check (are the "reuse, don't reinvent" code references real,
read directly against `hooks/subagent_stop_gate.py` and `hooks/loop_stop_guard.py`), and
a worth-building-at-all steelman. All 3 returned `has_real_gaps`. Full structured
findings: this session's workflow journal (run `wf_8a220dfd-b93`); summarized below.

**The 3 failure-mode closures don't actually hold as drafted:**
- Gameability is not closed, only relocated. The `.verifier_pass` flag proposed as
  "mechanical evidence" is empty-content and session-scoped, not claim-scoped — a real,
  non-faked Verifier PASS on unrelated work is structurally indistinguishable from one
  that checked the specific claim. Worse, it's the wrong flag: it fires on plan
  *approval* (pre-build), not deliverable *verification* (post-build) — a real
  distinction in this codebase between the PLAN_CHECK gate and the separate FEATURE
  gate. And the `deferred`/`rejected`-with-reason escape hatch is written unilaterally
  by Oga with no independent check at all — the same self-report failure the mechanism
  exists to close, reopened exactly at the point (an inconvenient original claim under
  context pressure) where it matters most.
- The async-in-flight-skip logic doesn't hold either. The dual-channel check it
  proposed reusing (`_RH3_TID_RE`/`_rh3_returned_ids`) has a documented blind spot in
  its own source comments: when a background dispatch's completion surfaces as a new
  turn boundary rather than a same-turn tool_result, the check silently fails to detect
  "in flight." In the Researcher gate this lives in today, that's declared the *safe*
  direction (failing to arm just defers to other gates). Repurposed as an in-flight
  SKIP for a Stop-BLOCK gate, the polarity inverts — failing to detect in-flight means
  failing to skip, i.e. blocking anyway, reproducing the exact `claude-code#55754`
  shape this was meant to prevent, in the normal case for slow background work.
- The "fail-open retry-cap backstop" doesn't fail open. Two lenses independently caught
  this: the actual precedent cited (`micro_step_gates.py` gate 3, retry-cap at 3
  same-signature failures) BLOCKS and demands escalation — it does not fail open at
  all. The new gate's safety property was asserted by analogy to a gate that does the
  opposite of what was claimed.
- The arming heuristic is simultaneously too loose (any two-clause build/fix ask likely
  arms it, risking the exact "ritual"/"invisible governance" objection the prior-art
  survey itself surfaced) and too narrow in the way that matters most: it likely would
  not have fired on the actual incident that motivated this whole document, since that
  incident's claims lived in a referenced diagnostic report worked across a long
  session, not a bulleted first-message list with explicit connectors — and per this
  design, a missed arm at message 1 is permanent for the whole session.

**The steelman-against-building lens landed the hardest hit:** the entire justification
is n=1 — one incident, recovered same-session, at zero tooling cost, by one human
sentence plus the agent re-reading its own history. No second occurrence is cited
anywhere (checked against this file's own gate-hole history — no comparable entry).
Read straight, the prior-art survey earlier in this document is arguably *stronger*
evidence against building the heavy version than for it: nobody has shipped this exact
mechanism anywhere (not Claude Code, not 5 major frameworks); the one paper with the
technical capability to hard-gate on a checklist (Avenir-Web) deliberately chose soft
monitoring instead, having already built the harder option; multiple real repos
abandoned adjacent mandatory-checklist enforcement citing gameability and rigidity; and
Claude Code's own Stop-hook-until-satisfied pattern produced a real, four-times-reported
failure needing Anthropic's own follow-up cap.

**Cheaper alternative proposed by that same lens, not yet built:** skip the new
`claims.md` file and the new Stop-hook gate entirely. Seed literal claims into
`fix_plan.md`'s existing `Open` section as Oga's first action on a qualifying request,
and add one line to the existing plan-check/post-build Verifier role brief
(`loop-team/roles/verifier.md`) requiring it to check every claim seeded that session
has a disposition before returning PASS. This reuses a dispatch pattern that is already
independent-context by construction (a fresh sub-agent grading, not the same agent
self-certifying) and already wired into the loop's own tick-reading behavior — no new
file format, no fourth hook surface, no need to re-derive `stop_hook_active`/retry-cap/
async-skip bounding logic borrowed piecemeal from three other places in the codebase.

**Why this is not yet built either:** the second half (the `roles/verifier.md` edit)
touches a file that was on this session's hands-off list at the time of writing (owned
by a concurrent session working in the same shared git tree). Nothing here has been
implemented. This is recorded as future work, pointed to from `fix_plan.md`, not as an
in-flight task.

**Explicit escalation criteria — what would flip the recommendation toward building the
fuller mechanism:** either (1) a second real incident of this shape, especially one in
an unattended or background-dispatched run with no human present to catch it — loop-
team's own trajectory (more background Workflow dispatches, longer autonomous runs) makes
this more likely over time even though it hasn't happened yet, or (2) evidence that the
cheap `fix_plan.md`-plus-Verifier-checklist version, once tried, still misses a drop —
a real empirical demonstration that reasoning-based checking isn't enough. Absent either,
the recommendation is: build the small thing when the hands-off file is free, watch,
escalate only on evidence — not preemptively.
