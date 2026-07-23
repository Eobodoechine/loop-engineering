# Planning stop-governor (EXPECTED_PLAN_CHANGE test) — internal grounding + adversarial red-team

**Date:** 2026-07-16
**Mode:** A (loop-improvement radar) + adversarial red-team
**Dispatch:** Ground the proposed stop-governor against the real loop repo and its history, then try to kill it with evidence.
**Scope:** internal only (this repo + its own history). No external sources fetched this pass — the dispatch scoped this to internal grounding + a fix_plan.md backtest. Prior external prior-art is cited from the on-disk dossiers, not re-researched.

---

## VERDICT (up front)

**DO NOT BUILD AS PROPOSED. BUILD DIFFERENT — and build only 1 of the 6 verdicts.**

The `EXPECTED_PLAN_CHANGE` stop test must not be built in any form. It fails on three independent grounds, each individually sufficient:

1. **Backtest: 15 : 0.** Fifteen recorded cases where a round ≥3, or an added lens, found a real named defect. **Zero** recorded cases of a late round producing only noise. The proposal's governing hypothesis ("late rounds only add confidence") is refuted by this repo's own history, not merely unsupported.
2. **It reinstates a rule this repo explicitly revoked.** `orchestrator.md:76` forbids, by name, exactly the mechanism the proposal is: *Oga's own assessment determining WHETHER a Verifier dispatch happens*. That rule exists because Oga's judgment "was directly, adversarially wrong twice in one session" (`orchestrator.md:83`).
3. **It is anti-correlated with its own target.** It asks Oga to *predict the class of a finding it has not yet made*. For unknown-unknowns — precisely the class late rounds catch — the honest answer is always "I can't name it." The test therefore fires STOP with maximum confidence exactly when the remaining defects are most severe.

**Build instead:** `SHIP_NARROW_PLAN` only — an artifact-size governor that cuts the *plan*, not the *review*. It is the one verdict in the proposal that is genuinely new and has real historical support (the 782→97 precedent). The problem in the screenshot is **scope expansion**, not too many rounds, and those need opposite fixes.

---

## PART 1 — GROUNDING: what already exists

### 1.1 The existing saturation gate is deliberately, structurally bias-to-continue

`loop-team/harness/plancheck_saturation.py` — the `[BINDING]` saturation gate. Entry point `evaluate_records` at **line 189**. It emits exactly three verdicts (**lines 28-30**):

```python
CONTINUE_PLAN_CHECK = "CONTINUE_PLAN_CHECK"
STOP_PROSE_REVIEW = "STOP_PROSE_REVIEW"
INVALID_TAGGING = "INVALID_TAGGING"
```

To return `STOP_PROSE_REVIEW`, **every one** of these must hold:

| Condition | Code | Fails → |
|---|---|---|
| ≥3 rounds recorded | `_last_three_rounds`, lines 207-213 | `CONTINUE_PLAN_CHECK` |
| Last 3 rounds consecutive (N, N+1, N+2) | `_rounds_are_consecutive`, lines 215-220 | `CONTINUE_PLAN_CHECK` |
| **Zero** LOGIC/CONCURRENCY/SECURITY records in the window | lines 229-241 | `CONTINUE_PLAN_CHECK` |
| All records `tag == BINDING` | lines 243-252 | `CONTINUE_PLAN_CHECK` |
| All BINDING records `compiler_catchable=True`, `exclusion in (None,"none")` | lines 254-268 | `CONTINUE_PLAN_CHECK` |
| All signatures collapse to exactly **one** recurring signature | lines 270-282 | `CONTINUE_PLAN_CHECK` |

Every branch defaults to CONTINUE. The gate stops the loop **only** when it can prove the loop is grinding on one identical, compiler-catchable defect for 3 consecutive rounds with nothing else alive. It never stops on "diminishing returns," never on "more confidence," never on Oga's judgment.

**This is not an oversight — it is the design.** `DESIGN_CHECKLIST.md` gate 10, **lines 152-155**:

> "The zero-new-finding clause is load-bearing, not optional — it stands the counter down the instant a lens is still finding a real bug, so a stretch that is ALSO producing new non-binding findings never triggers a stop no matter how many binding recurrences pile up next to it."

And **lines 178-182** state that safety against a premature stop is carried *entirely* by the zero-new-finding clause, **not** by counting rounds:

> "safety against a premature stop is carried entirely by the zero-new-finding clause, not by counting higher."

### 1.2 What the existing gate covers vs. what is genuinely NOT covered

**COVERED:** exactly one narrow case — a recurring, compiler-catchable `[BINDING]` signature (undeclared identifier, missing import/export, missing `'use client'`/`'use server'`, naming collision, prose-describes-an-edit-without-showing-code) that a real `tsc --noEmit`/`next build` would reject with zero code executed (`DESIGN_CHECKLIST.md:113-121`).

**NOT COVERED (the honest gap list):**
- **No stop rule for LOGIC/CONCURRENCY/SECURITY saturation.** Deliberately excluded — these have no compiler-equivalent oracle to defer to.
- **No artifact-size governor.** Nothing anywhere in the repo reacts to a spec growing to 1,452 lines / 107 ACs. `H-SPEC-XREF-1` (`orchestrator.md:122-124`) explicitly chose **round count, not spec length**, as its trigger — and grounded that choice in real data (the first cross-reference defect fired on a 15-AC spec). So spec size is a *deliberately unused* signal, not a forgotten one. **This is the real hole.**
- **No per-section convergence freeze.** Convergence is demonstrably detectable per-section (see §4.2) but nothing tracks or acts on it.
- **No mechanism-change trigger.** When N rounds re-confirm the same reasoning, nothing says "switch the lens."

**Is the proposal duplicating something already built? Yes — 5 of its 6 verdicts.**

| Proposed verdict | Already exists at |
|---|---|
| `CONTINUE_PLAN_CHECK` | **`plancheck_saturation.py:28` — same literal string.** A second module emitting this name with *judgment-based* semantics against the existing *deterministic* semantics is a live collision hazard. |
| `REVISE_PLAN` | `orchestrator.md:86` (`DESIGN` branch, max 2 direct revisions) + memory `feedback_ac_recurring_gap_signals_design_not_bug` |
| `ASK_USER` | `orchestrator.md:88` ("Still `PLAN_FAIL` after max retries: escalate to human… Stop — do not loop further") |
| `DEFER_HARDENING` | `orchestrator.md:647-703` — repo-health gate + `hardening_ledger.json` |
| `BLOCKED` | `orchestrator.md:668-672` — `repo_health_gate.py` FROZEN verdict |
| `SHIP_NARROW_PLAN` | **Genuinely new.** The only one. |

### 1.3 Grounding correction: RUN.md is not the governing stop contract

The dispatch pointed at `RUN.md` "budget/stop contract ~line 16 and ~64." Read fresh:

- `RUN.md:22-24` — `BUDGET → cap per run (career-finder: 15 listings; apply-for-job: 10 apps)` / `STOP → queue empty, cap hit, or verifier overturns writer on the SAME dimension 2 ticks running`.
- `RUN.md:64` — "**Split PLAN from IMPLEMENT (biggest reliability upgrade).** A separate one-shot PLANNER pass… The loop then ONLY implements one item per tick — it never re-plans mid-implement."
- `RUN.md:70` — "**BUDGET = hard enforcement, not alerts.**"

**These do not govern plan-check rounds.** RUN.md's STOP is about a verifier overturning a writer on a *job listing*, and per the standing decision in `~/Claude/CLAUDE.md` ("RUN.md is career-loop-specific — only load it for job/career tasks"), RUN.md is out of scope for a grounded-RAG MVP entirely. Note also that `RUN.md:64` cuts *against* the proposal: it says the loop "never re-plans mid-implement" — the PLAN/IMPLEMENT split is already the mechanism that bounds planning, and it bounds it by *phase*, not by Oga's confidence estimate.

The real stop machinery lives in `hooks/micro_step_gates.py` — and it is worth noting what those gates actually count (module docstring, **lines 8-14**): `thrash-past-green`, `step-size` (`MAX_STEP_LINES = 200`, line 51), `retry-cap` (third consecutive **same-signature** failing verify, line 361). **Every one is keyed to a repeated identical signature or a hard size cap — never to a judgment about expected value.** The repo's entire stop-gate vocabulary is mechanical. The proposal would be the first judgment-based stop in it.

### 1.4 The rule the proposal directly violates

`orchestrator.md:70-83`, "**Unconditional plan-check-before-Coder, scaled by risk, not skipped by judgment**":

> **Line 74:** "The pre-existing ≤2-DOC-AC self-review escape … is **REVOKED, not narrowed.** Self-review is Oga judging its own spec sufficient without independent review — structurally the same failure mode this rule exists to close."
>
> **Line 76:** "No exception based on Oga's own assessment of triviality, urgency, or risk determines **WHETHER** a Verifier dispatch happens — only **HOW MUCH** scrutiny it gets."
>
> **Line 83:** "This rule exists because Oga's own 'this is safe/trivial enough to skip' judgment was directly, adversarially wrong twice in one session (2026-07-08)."

The proposal is: *Oga states whether a further plan-check would change anything; if not, stop.* That is Oga's own assessment determining WHETHER a dispatch happens. **The proposal is the revoked escape, re-issued under a new name.** Line 76's "only HOW MUCH scrutiny" is the sanctioned lever — and it is the lever the real fix should pull.

### 1.5 Prior research already on disk (read, not redone)

**`research/plancheck-nonbinding-saturation-2026-07-09.md`** — a dedicated prior pass on this exact question. Findings that bind here:

- **Headline (lines 29-31):** "**No existing tool or paper solves this problem directly**… (repeated independent LLM review of a STATIC, unchanged spec, hunting for LOGIC/CONCURRENCY/SECURITY defects with no compiler-equivalent oracle)."
- **The static-artifact confound (lines 40-45):** every production tool with a "N rounds, no new findings → stop" rule (ai-code-reviewer, optimus-claude, ralphreview, gopher-ai) protects an artifact that **changed between rounds**. For a static spec, Biffl/Halling/Kohle reinspection data shows detection *degrades* round-over-round (45.2%→36.5%, 46%→21%) — so a quiet streak "is confounded with reviewer fatigue/satisfaction-of-search, not just genuine exhaustion — and none of the found tools has any mechanism to tell the two apart."
- **Every formal stopping rule found requires an oracle** (lines 63-66): DSPy `Refine`, Self-Refine's `delta_score`, GEPA, the Wald-SPRT and KS-stability debate papers. Two papers *explicitly disclaim* applicability to logic-bug-finding.
- **A pre-registered kill criterion for any stop signal in this repo (lines 390-396):**
  > "**a single hit on the round-19-21 or round-30/31 airbnb-calendar-sync instances is an automatic kill**, regardless of what the aggregate false-accept rate says — a stop signal that would have muted this run's own two most important findings is disqualifying on its own, independent of the statistical aggregate."

  **The proposal fires long before round 19. It is killed by this repo's own pre-registered criterion without needing a new experiment.**

**`research/claim-ledger-goal-drift-mechanism-spec-2026-07-07.md`** — status line 3: "**CRITIQUED, NOT RECOMMENDED FOR BUILD AS SPECED**." Its most relevant finding (lines 65-75), *"From Confident Closing to Silent Failure"* (arXiv:2606.09863, 9,876 tau2-bench + 1,879 AppWorld trajectories):

> "Checklist condition barely moved detection accuracy over baseline (AUROC ~0.576) and *actively degraded* detection specifically for Claude Sonnet on AppWorld (0.368 → 0.274)… **A free-text LLM judge re-reading a checklist against a transcript is not a reliable completion gate on its own** — this matches loop_stop_guard.py's own existing design principle (verification signals are read from structural tool_use/tool_result data, **never from blob text an agent could fake by writing the right words in prose**)."

The proposal's core artifact is *Oga writing a sentence about what would change its mind*. That is blob text an agent can fake by writing the right words in prose — the exact input class this repo's hooks are architected to never trust.

**`research/agent-goal-drift-focus-prevention-2026-07-04.md`** — the AutoGPT precedent (lines 498-503) names "perfectionism bias… kept 'improving' already-finished work" as a real failure. But its named root causes are "**no termination criteria, no repeated-action detection**" — both of which this loop already has (`MAX_ITERS`, retry-cap, thrash-gate, gate 10). And line 479-481 is the throughline: *"System prompts are weighted inputs to a probabilistic reasoning engine, not deterministic enforcement mechanisms."*

---

## PART 2 — THE BACKTEST (the number that decides it)

Mined `fix_plan.md` (858KB, 183 `##` entries) plus `loop-team/learnings.md` and the on-disk plan-check logs.

### 2.1 CASES WHERE A LATE ROUND / ADDED LENS FOUND A REAL DEFECT — **15**

Each is a named artifact with a real citation. Every one would have been suppressed by a governor that stops when Oga can only claim "more confidence."

| # | Case | Round | What it found |
|---|---|---|---|
| 1 | **`H-AC-ORACLE-TARGET-1` / AC19** (`fix_plan.md:4230-4259`) | **30 of 31** | A structurally unfalsifiable cross-org security AC |
| 2 | **`H-AC-ORACLE-TARGET-1` / AC16** (`fix_plan.md:4256-4259`) | **31** | A second, structurally identical security-oracle gap |
| 3 | **ops-clock STT lens** (`ops-clock-alt-method-experiment-2026-07-02.md:44-49`) | **after 20 rounds** | 2 genuinely new gaps → AC46b, AC55, AC56 |
| 4 | **verifier-no-fire-list STT lens** (`orchestrator.md:59`) | **after 3 converged rounds** | An entire unaddressed state ("CLOSED-then-recurred") with no defined behavior at all |
| 5 | **`H-AMBIGUITY-NOTE-DROPPED-1`** (`fix_plan.md:2912-2929`) | **4** | A Test-writer's self-flagged decision-request that sat through an entire build cycle *and a commit* |
| 6 | **`H-SUBAGENT-COMMIT-GATE-1`** (`fix_plan.md:2188-2191`) | **3** | "before line ~499" ≠ "before every early-exiting gate" — two gates sit between them |
| 7 | **`H-REVIEW-COMMIT-1`** (`fix_plan.md:2214, 2231-2232`) | **6** | The sub-agent-commit blind spot → became `H-SUBAGENT-COMMIT-GATE-1` |
| 8 | **`H-SPEC-REWRITE-DIFF-1`** (`fix_plan.md:2704-2711`) | **3** | A full rewrite silently dropped the `record_sigs` design section |
| 9 | **Fenced-write enumeration** (`fix_plan.md:9040-9048`) | **3** | Rounds 1 and 2 both missed the dedupe-MATCH write; round 3 caught the claim still false |
| 10 | **Hook-gate v3** (`fix_plan.md:4061-4063`) | **3** | 4/5 lenses PLAN_FAIL — verb vocabulary has no tense/negation awareness |
| 11 | **`_rh_judge_suite_green`** (`fix_plan.md:1081-1086`) | **3** | Blob-scoped not command-scoped → prose mentioning `run_evals.py --judge` satisfied it without a real judge run |
| 12 | **`H-SPEC-XREF-1`** (`fix_plan.md:4663`) | **29** | Fixing a prior instance *introduced 3 brand-new backwards pointers in the very fixes just applied* |
| 13 | **`H-SPEC-XREF-1`** (`fix_plan.md:4663`) | **31** | A final mechanical sweep of ~90 pointers "still turned up 2 more" |
| 14 | **control-plane AC7** (memory `feedback_ac_recurring_gap_signals_design_not_bug`) | **3** | 3 consecutive rounds, "each finding a genuinely NEW, real, code-grounded gap" |
| 15 | **Spec C1** (`learnings.md:2640-2647`) | **3, 4, 5** | R3: structural PID-reuse flaw; R4: the `start_time` gap R3's fix left; R5 clean |

**Supporting (multi-round runs where every round was productive):** taxahead/mission-control — "**8 rounds** of genuine, independent plan-check (each finding real, live-execution-confirmed spec bugs, converging correctly)" (`learnings.md:2755-2756`); guard-hooks-async i1+i2 "both real" (`fix_plan.md:873`); Decision-4 — "3 plan-check Verifier rounds before PLAN_PASS (**all found genuine gaps**)" (`fix_plan.md:540`); Spec C2 "followed the identical shape one round later" (`learnings.md:2645`).

### 2.2 CASES WHERE A LATE ROUND FOUND ONLY NOISE — **0**

A direct grep across `fix_plan.md` + `learnings.md` for any round recorded as finding nothing / noise / wasted returned **empty**.

**Honest caveat, stated plainly:** `fix_plan.md` is a gate-hole log, so it is structurally biased toward recording "the gate missed something" over "the gate cost too much." That bias is real. **But it does not explain the 15:0 result**, because the log demonstrably *does* record process-cost holes — `H-PLANCHECK-BINDING-SATURATION-1` and `H-SPEC-XREF-1` are both entries about plan-check costing too much. The log has both categories. The late-round-found-real-defect category simply dominates 15:0.

The two closest things to counter-evidence, characterized honestly — **neither is noise**:

**(a) Slice 6b binding recurrence** (`fix_plan.md:4349-4353`) — the same compiler-catchable signature recurred **9 times across rounds 17-30**. Genuine waste. But *every recurrence was a real bug* (a real undeclared identifier, a real missing import) — of a class `tsc` catches free. This is **real-but-mis-routed, not noise**. The fix was to route the class to a cheaper oracle (gate 10 + `H-TYPECHECK-GATE-1`, `fix_plan.md:4428-4430`), **not** to stop reviewing.

**(b) TaxAhead safe-resume-plan** (`learnings.md:2725-2734`) — 5 rounds of escalating scrutiny on the SAME unchanged mechanism (git-ref leases/**CAS**/epochs); spec bloated to 782 lines. This is the single strongest pro-proposal case in the corpus and it is worth taking seriously. But look at what round 5 actually produced (`learnings.md:2714-2716`): "round 5's own reconciliation summary showed **6 unresolved DESIGN gaps** (concurrency/security/logic tags…), 5 of 6 lens-pairs still `NEEDS_HUMAN`, zero contradictions resolved." Round 5 was still emitting real, tagged DESIGN findings — **nobody was resolving them**. And the fix that worked was **rewriting the spec 782→97 lines**, then finding 3 real gaps in the simpler doc and closing them with "4 short additions plus one narrow single-lens confirmation dispatch."

**Even the best pro-proposal case resolves to "cut the artifact," not "stop the review."**

### 2.3 The single most important quote in the corpus

`fix_plan.md:4353` — the repo's own analysis, written when it built the *existing* saturation gate:

> "the run's two most consequential findings of the entire 31-round process — AC19 (round 30) and AC16 (round 31)… landed in the very same stretch the binding-class bug was still recurring… so **any naive 'stop after N rounds of a repeated pattern' rule risks silently cutting off exactly the findings this adversarial process most exists to catch**, unless the stop condition is explicitly guarded by a zero-new-finding clause."

The proposal has **no zero-new-finding clause**. It stops on a *prediction*, not on evidence of exhaustion. It is the exact rule this sentence was written to forbid.

### 2.4 The mechanism the proposal cannot see (why it's anti-correlated with its target)

`H-AC-ORACLE-TARGET-1` (`fix_plan.md:4250-4259`) is the decisive mechanistic evidence:

> "**Ten separate plan-check rounds (20 through 29) re-walked the identical cross-org scenario and confirmed the REASONING was sound every time** — the scenario really was correctly blocked by the real guard — without anyone asking 'which org's table would a wrongly-created row actually land in?' **Round 30's ordinary re-verification dispatch (no special ownership-tracing instruction** — just 're-verify the now-revision-31 spec.md against all 5 lenses simultaneously') **is what finally caught it**; round 31's dispatch, written AFTER the fix landed, was the one explicitly instructed to re-walk every adversarial AC with maximum skepticism as a reaction to this exact incident, **not its cause**."

Read that last clause carefully. **The instruction that would have named the finding could only be written *after* the finding existed.** That is the structural refutation:

- At rounds 20-29, an honest `EXPECTED_PLAN_CHANGE` answer was necessarily **"more confidence"** — ten rounds had confirmed the same reasoning sound, and nobody had yet conceived of the question that would break it.
- The proposal would have returned `SHIP_NARROW_PLAN` or `CONTINUE→STOP` at round ~21-22 with **maximum justified confidence**.
- A real cross-org security defect ships.

**The test asks Oga to name the class of a finding it has not yet made. For unknown-unknowns, that is definitionally impossible — and unknown-unknowns are exactly what rounds 30/31, the ops-clock enumeration lens, and `H-AMBIGUITY-NOTE-DROPPED-1` all caught.** The test's confidence is *highest* precisely when its error is *worst*. It is not merely unhelpful; it is inverted.

`DESIGN_CHECKLIST.md:217-221` states the same lesson as settled doctrine:

> "Ten separate plan-check rounds re-walked the identical cross-org scenario and confirmed the REASONING was sound every time, **because the bug lived in the CHECK, not the scenario**, and no round asked 'which org's table would the wrong row actually land in?' until round 30."

---

## PART 3 — THE STANDING CONSTRAINT, AND THE RECONCILIATION

### 3.1 The constraint, in the owner's own words at the exact decision point

The standing preference is recorded in memory as `feedback_accuracy_over_speed_loop_team` — "not in a rush; keep running plan-check rounds as long as they find real gaps." It is not an abstract preference. Nnamdi stated it *at round 31 of the exact scenario the proposal targets* — a bloated spec, 30+ findings, a plan that had ground for 31 rounds (`plan_check_log.md:2523-2536`, quoted in `research/compiler-gate-internal-grounding-2026-07-08.md:120-129`):

> "**Process pivot decision (Nnamdi, this round):** 31 rounds is a lot. Reviewing the pattern across rounds 24-31: ~30+ findings, almost all concentrated in one ~700-line UI wiring section, and the large majority of them (missing imports, missing `export`/`'use client'`/`'use server'` directives, variable-naming collisions, un-shown literal code) are exactly what `next build`/`tsc` catches in seconds, for free — **we were hand-simulating a compiler by reading prose very carefully**… The backend (§B.2/§B.3 concurrency/locking logic) converged genuinely early and stayed clean (7 consecutive rounds). **The two real, non-mechanical findings this run's process caught that a compiler never could — AC19 (round 30) and AC16 (round 31), both cross-org test-assertion traps — are exactly what this adversarial process is FOR, and neither would have surfaced without it.**"

This is the owner, looking at a 31-round plan-check, **blessing the late rounds** and diagnosing the actual problem as **wrong-oracle routing**, not excess rounds. The proposal's premise ("if the answer is only 'more confidence', stop planning") contradicts the owner's own recorded finding on this exact data.

The discriminator is already written down, and it is not the proposal's. `learnings.md:2648-2656`:

> "a converging fix-then-narrower-gap sequence is exactly what correct iterative plan-check is supposed to look like on a genuinely subtle mechanism, **not a signal to stop or redesign from scratch. Keep iterating (per `feedback_accuracy_over_speed_loop_team`) as long as each round's finding is new and the scope is shrinking**; only treat a stalled/repeating finding, or duplication across rounds, as the actual stop-and-escalate signal."

| | Existing (blessed) discriminator | Proposal's discriminator |
|---|---|---|
| Question | Was each round's finding **new**, and is scope **shrinking**? | Can Oga **name** a result that would change the plan? |
| Direction | **Retrospective** — reads what rounds actually produced | **Prospective** — predicts what a round might produce |
| Basis | **Evidence** on disk | **Speculation** by the actor being governed |
| Fails on | Nothing observed | **Unknown-unknowns — the whole point of the exercise** |

### 3.2 The reconciliation: "too many rounds" vs "scope expansion" — these are opposite failures

**Answer: the real problem is scope EXPANSION. It is not too many rounds. The proposal misdiagnoses one as the other, and prescribes a treatment that makes the real disease worse.**

The screenshot's own facts prove it:

- **1,452 lines / 107 criteria for a narrow grounded-RAG MVP** — that is the disease. A plan 15× the size of the MVP it describes.
- **The late lenses found a PostgreSQL column-level SELECT privilege flaw and a CAS idempotency gap** — those are *real bugs*. That is the immune response working.

**The lenses were not malfunctioning. They were correctly reporting that a 1,452-line plan has 1,452 lines' worth of defects in it.** A plan that large *genuinely contains* more real defects — that is not a review pathology, it is arithmetic. Suppressing the report does not remove the defects; it ships them.

Cutting the review to fix a bloated plan is treating a fever by breaking the thermometer. The fever is the signal that the plan is too big.

**The historical precedent for the correct treatment is exact and on disk.** The TaxAhead case (§2.2b) is the same shape as the screenshot — an over-scoped spec (782 lines) on a mechanism (git-ref leases/**CAS**/epochs — note the screenshot's CAS gap is the *same mechanism family*) grinding through 5 rounds of escalating scrutiny. What actually resolved it (`learnings.md:2717, 2729-2734`):

1. **Rewrite the spec 782 → 97 lines** (cut the artifact).
2. Re-verify the *simpler* artifact — which surfaced 3 real, concrete gaps.
3. Close them with "4 short additions plus one narrow single-lens confirmation dispatch, **not another 2-5-lens round**."

Note step 2: the review did **not** stop. It got *cheaper*, because the artifact got *smaller*. Reviewing a 97-line spec costs a fraction of reviewing a 782-line one — and it finds the *right* defects, because the surface is now the MVP's actual surface.

`learnings.md:2743-2745` states the balance as doctrine, and it indicts the proposal directly:

> "Treating every fresh finding as grounds for another full adversarial panel, and **treating 'we already did a round of that' as grounds to skip verification, are the same mistake in opposite directions.**"

The proposal is the second mistake, mechanized.

### 3.3 Why the two failures need opposite fixes

| | **Scope expansion** (the real problem) | **Too many rounds** (the misdiagnosis) |
|---|---|---|
| Symptom | 1,452 lines / 107 ACs for an MVP | 31 rounds |
| Cause | The plan grew past the goal | The plan has real defects in it |
| Correct fix | **Cut the artifact** (782→97 precedent); freeze scope at the MVP boundary | **Route defect classes to cheaper oracles** (gate 10 → `tsc`); switch lens on non-convergence |
| Proposal's fix | Doesn't address it — a frozen 1,452-line plan is still 1,452 lines | Stop reviewing |
| Effect of proposal's fix | **None on the real disease** | **Ships the PG privilege flaw and the CAS gap** |

The proposal freezes *scope* only as a side effect of stopping *planning*. But a frozen 1,452-line plan is still a 1,452-line plan — the ACs don't disappear; they just go to the Coder unreviewed. **The proposal's stated goal ("freeze scope") and its mechanism ("stop plan-checking") are not connected.** It would deliver the bloat *and* remove the only thing catching the bloat's bugs.

---

## PART 4 — WHAT TO BUILD INSTEAD

### 4.1 BUILD: `SHIP_NARROW_PLAN` as an artifact-size governor (the one salvageable piece)

The one genuinely new verdict, retargeted at the actual disease. Not a stop test — a **cut test**.

- **Trigger (mechanical, not judgment):** spec line count and/or AC count exceeds a stated multiple of the MVP boundary. Fires on the *artifact*, which is deterministically measurable — never on Oga's expectation.
- **Action:** `SHIP_NARROW_PLAN` = **cut the spec to the MVP boundary and re-plan-check the smaller artifact**. Explicitly NOT "stop plan-checking." Defer the cut ACs to the hardening ledger (`hardening_ledger.json`) — which already exists and is exactly the right home (`orchestrator.md:680-695`).
- **Precedent:** the 782→97 rewrite (`learnings.md:2717`), which worked, and the round-31 pivot's own logic.
- **Honest risk to design around:** `H-SPEC-XREF-1` (`orchestrator.md:122-124`) deliberately **rejected** spec length as a trigger, grounded in real data — the first cross-reference defect fired on a 15-AC spec. So size is a valid trigger for *"this plan is over-scoped"* but is **not** a valid trigger for *"this plan is defect-free."* Keep those strictly separate. This governor must never suppress a round; it may only shrink what a round reads.
- **Also required:** a full rewrite is itself a known defect vector — `H-SPEC-REWRITE-DIFF-1` (`fix_plan.md:2704-2711`) records a v2→v3 rewrite silently dropping a whole design section, caught only because round 3 happened to re-verify. So a `SHIP_NARROW_PLAN` cut **must** be followed by a plan-check round, not treated as a terminal state. This is a second, independent reason the verdict cannot mean "stop."

### 4.2 CONSIDER: per-section convergence freeze (evidence-based, retrospective)

The signal the proposal *wanted* exists and is real — but it is per-section and evidence-based, not per-plan and predictive. `research/compiler-gate-internal-grounding-2026-07-08.md:139-143`:

> "the backend concurrency/locking logic (§B.2/§B.3) genuinely DID converge early and stay clean — concurrency-isolation **passed 7 consecutive rounds** by the end… So there IS a real 'the design-sensitive core stabilized earlier than the UI-wiring layer' pattern in this data."

Slice 6b's waste was not "31 rounds." It was **re-reviewing §B.2/§B.3 for 7 rounds after it had demonstrably converged**, while the UI-wiring section still needed every one of those rounds. A per-section clean-streak tracker would have cut real cost without touching rounds 30/31 — because AC19/AC16 lived in the *un*-converged section.

Wire it as **advisory only**, per the standing conclusion in `research/plancheck-nonbinding-saturation-2026-07-09.md:300-305` (the estimator may be structural, the *signal* stays advisory) and given the static-artifact fatigue confound (§1.5). Backtest it against the pre-registered kill criterion (`plancheck-nonbinding-saturation:390-396`) before it goes near the critical path.

### 4.3 CONSIDER: non-convergence → change the MECHANISM, never stop

Three independent incidents converge on one rule: when N rounds re-confirm the same reasoning, **the next dispatch should be a structurally different lens, not a stop and not another identical round.**

- ops-clock: 20 rounds of narrative review → STT lens found 2 new gaps (`ops-clock-alt-method-experiment:44-49, 55`).
- verifier-no-fire-list: 3 converged narrative rounds → STT lens found an entirely unaddressed state (`orchestrator.md:59`).
- Slice 6b: 10 rounds re-walking one scenario → the fix was a *mutation check* (an executable oracle, gate 9), not more walking (`fix_plan.md:4282-4287`).

`orchestrator.md:58` already names the mechanism: narrative lenses "catch a flawed sentence (something present in the spec but wrong); enumeration catches a missing row (something the spec never addresses at all — **structurally invisible to a method that only reacts to what's already written**)." Repeating a method that is structurally blind to a defect class cannot find that class no matter how many rounds you run — **and cannot know it's blind, which is exactly why "I'd only gain confidence" is an unreliable self-report.** The existing trigger (`orchestrator.md:62`: ≥1 prior non-converging round) already covers this; it may just need to be enforced rather than optional.

### 4.4 DO NOT BUILD: the `EXPECTED_PLAN_CHANGE` test, in any form

Reasons, each independently sufficient:

1. **15 : 0 backtest.** Refuted by this repo's own history.
2. **Killed by a pre-registered criterion** (`plancheck-nonbinding-saturation-2026-07-09.md:390-396`) it fails by ~10 rounds.
3. **Reinstates a revoked rule** — `orchestrator.md:74-76`, revoked because Oga's judgment was "directly, adversarially wrong twice in one session."
4. **Anti-correlated with its target** — cannot see unknown-unknowns, which is the class late rounds catch (§2.4).
5. **Prose self-report as a gate signal** — the failure mode `loop_stop_guard.py` is architected against, with external evidence it *degrades* detection for Claude Sonnet specifically (AUROC 0.368→0.274, arXiv:2606.09863).
6. **Verdict-name collision** — `CONTINUE_PLAN_CHECK` is already `plancheck_saturation.py:28` with incompatible semantics.
7. **No zero-new-finding clause** — the one guard `DESIGN_CHECKLIST.md:152-155` calls "load-bearing, not optional."
8. **Contradicts the owner's explicit standing preference**, stated on this exact scenario.

### 4.5 Transfer-condition check (required by the role brief)

The proposal borrows the "diminishing-returns → stop" pattern from production review tools (ai-code-reviewer, optimus-claude, ralphreview, gopher-ai — all verified in the 2026-07-09 dossier).

- **(a) Context the mechanism requires:** every one of those tools protects an artifact that **changes between rounds** (a fixed diff, a fresh commit). Their streak signal is meaningful only because something genuinely different is examined each round.
- **(b) Does the target context satisfy it? NO.** Plan-check re-reads a **static, unchanged spec**. The prior dossier (lines 40-45, 216-221) established this is not pedantic — it is the confound: on an unchanged artifact, a quiet streak is indistinguishable from reviewer fatigue, and reinspection effectiveness measurably falls (45.2%→36.5%, 46%→21%). **The transfer condition fails.**
- **(c) Structural or instructional? INSTRUCTIONAL — and silently load-bearing.** Oga must honestly self-report its own expected information gain. A compliance failure produces no error: the plan simply ships under-reviewed and passes every downstream check (the Coder implements it, the tests go green — `fix_plan.md:8913-8917` records exactly this shape: "676/676 green, real-world bug still fully live"). **This is the precise pattern the role brief requires me to flag: the guarantee is instructional, and a failure would be silent, load-bearing, and produce wrong outputs that pass downstream checks.**

---

## Sources (all internal; every file opened and quoted this pass)

**Repo files read directly:**
- `RUN.md` (full — lines 22-24 budget/stop, 64 PLAN/IMPLEMENT split, 70 budget enforcement)
- `loop-team/orchestrator.md` (full, 731 lines — 48-176 plan-check routing, 51-66 lens scaling, 58-64 STT lens, 70-83 unconditional plan-check, 86-88 DESIGN/KNOWLEDGE branches, 647-703 repo-health gate)
- `loop-team/harness/plancheck_saturation.py` (full, 357 lines — 28-30 verdicts, 189 `evaluate_records`, 207-300 the stop conditions)
- `loop-team/DESIGN_CHECKLIST.md` (full, 222 lines — gate 9 at 83-102, gate 10 at 104-206, provenance at 208-221)
- `hooks/micro_step_gates.py` (docstring 1-20, constants 51-55, gate greps)
- `fix_plan.md` (858KB — mined by grep; entries at lines 540, 873, 1081, 1185, 2188, 2214, 2704, 2912, 4061, 4230, 4349, 4428, 4663, 8904, 9040)
- `loop-team/learnings.md` (2640-2656 C1/C2 convergence, 2706-2751 TaxAhead over-analysis, 2753-2782 8-round credit-gate)

**Prior research on disk (read, not redone):**
- `research/plancheck-nonbinding-saturation-2026-07-09.md` (full, 475 lines) — the pre-registered kill criterion at 390-396; static-artifact confound at 40-45
- `research/agent-goal-drift-focus-prevention-2026-07-04.md` (headings + 118-176, 453-542)
- `research/claim-ledger-goal-drift-mechanism-spec-2026-07-07.md` (1-80) — status: CRITIQUED, NOT RECOMMENDED FOR BUILD
- `research/compiler-gate-internal-grounding-2026-07-08.md` (88-145) — the round-by-round Slice 6b backtest + Nnamdi's round-31 pivot quote
- `research/ops-clock-alt-method-experiment-2026-07-02.md` (30-69) — the 20-rounds-then-2-new-gaps experiment

**Memory files:**
- `feedback_ac_recurring_gap_signals_design_not_bug`, `feedback_plan_check_conflicting_test_gap`, `feedback_rls_cutover_both_directions`, `feedback_accuracy_over_speed_loop_team`

**Explicitly NOT found (honesty note):**
- **Zero** recorded cases of a plan-check round producing only noise, across `fix_plan.md` + `learnings.md`. Caveat on recording bias stated in §2.2.
- No evidence on disk for the screenshot's 1,452-line / 107-AC plan. Treated as **reported by the dispatch, not independently verified** — the argument in §3.2 does not depend on the exact numbers, only on the shape (over-scoped plan + productive late lenses), which the TaxAhead 782-line case independently corroborates.
- The **conflicting-test gap** (`feedback_plan_check_conflicting_test_gap`) is **not** a late-round-found-it case, contrary to the dispatch's framing. Read fresh, it is the opposite: *two* plan-check rounds **missed** it and it was "caught only because Oga ran a broader test sweep post-build, not by plan-check itself, in either round." Likewise the **RLS cutover** case is a one-directional-audit miss (40 test failures at cutover), not a round-count case. Both are evidence that plan-check **under**-detects — which cuts against the proposal, but by a different route than the dispatch supposed. Recording this correction because a fabricated or mis-framed case would be a critical failure.
