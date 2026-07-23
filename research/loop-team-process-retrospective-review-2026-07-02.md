# Review: third-party process retrospective on the ops-clock plan-check build (2026-07-02)

**Mode:** A (improve the loop) — grounding a retrospective + scoring 3 proposed playbook changes.
**Dispatched by:** Oga, this session. **Author of the retrospective under review:** an unaudited
session on `padsplit-cockpit`, not part of loop-team; treat as third-party narrative until verified below.

---

## Step 1 — Ground-truth against real evidence

**Source located and read in full:** `~/Claude/loop/runs/2026-07-02_ops-clock/plan_check_log.md`
(302 lines, 13 logged iterations) plus `~/Claude/Projects/padsplit-cockpit/SESSION_CONTINUATION.md`
(the session handoff note) and `web/src/lib/state-machine.ts` (the real `AlertState` enum). This is a
genuine, reproducible artifact — not a narrative I'm taking on faith. Quoting directly below.

**Top-line correction the retrospective omits entirely: this was PURE PLAN-CHECK, zero code written.**
`SESSION_CONTINUATION.md` line 51: *"Status: 12 plan-check iterations run, 17 real design gaps found
and fixed, ZERO code written... No Coder has ever been dispatched against this spec."* Every single
round in `plan_check_log.md` reviews a design DOCUMENT, not implementation. This matters for scoring
proposal #1 below — the retrospective frames it as if bugs were found "spread across rounds" in a
built system; in reality every "bug" is a **spec defect caught before a single line existed**, which is
a stronger, cheaper result than the retrospective implies, and changes what proposal #1 is actually
asking for (see Step 2).

### Claim-by-claim verification

**Claim: "Round 6 asked the Verifier to explicitly enumerate all 6 Task-mutating paths and check each
one — found a bug and confirmed 5 others sound in one shot."**
**DISCREPANCY — the ask and the result are in different rounds, and "found a bug" overstates round 7.**
Quoting iteration 6 verbatim: *"Spec's Context section now also enumerates the complete 6-item
Task-mutating action surface explicitly, asking the next Verifier to check each one individually...
targeting the actual recurring pattern... rather than hoping for another lucky find."* That's the ASK,
landing at round 6. The sweep and its result are round 7: *"Explicit 6-path sweep (requested in
iteration 6's dispatch) confirmed the entire recurring suppression-bypass bug class (rounds 1/2/4/5) is
closed -- all 6 Task-mutating actions checked individually and sound. Applied the one remaining,
unrelated fix: OccupancyEvent gains a `tasks Task[]` back-relation..."* So round 7 found the sweep
CLEAN (all 6 sound), not a new bug — the "back-relation" fix it applied was an unrelated Prisma
schema-validity issue, not a resurrection-bug catch. The retrospective's "found a bug and confirmed 5
others sound" compresses two different rounds and misattributes what the round-7 finding actually was.
The exhaustive-sweep mechanism worked exactly as intended (closing out a bug CLASS in one dispatch
instead of one instance at a time) — that part of the claim is directionally right — but the specific
"found a bug" framing at round 6/7 does not hold up against the log.

**Claim: "Round 8 did the same implicitly for AlertState's 4 enum values and found PENDING_VACANCY had
been silently unaudited."**
**MOSTLY CONFIRMED, with the same off-by-one round-labeling quirk.** Iteration 8: *"Round-6 schema fix
confirmed fully correct. Applied round-7's fix: the recompute step now actually implements the
'preserve PENDING_VACANCY' guard it had only asserted in prose before... This closes the last of the 4
AlertState enum values (WARNING/PAYMENT_DISPUTE/NONE were already correct)."* So the finding that
PENDING_VACANCY was unaudited actually surfaced as **round 7's finding, applied at round 8** — the
log's own heading convention names each iteration by the fix it APPLIES (based on the prior round's
finding), then re-runs plan-check labeled as that same round number. This is a real, reproducible
off-by-one in how round numbers map to "when was X found" vs "when was the fix applied and confirmed."
The retrospective's core claim (AlertState's 4th value, PENDING_VACANCY, was silently unaudited and
caught by an implicit enumeration) is TRUE — confirmed directly in `web/src/lib/state-machine.ts`
(`AlertState = 'NONE' | 'WARNING' | 'PAYMENT_DISPUTE' | 'PENDING_VACANCY'`) and in the log. Only the
round number attribution is imprecise, and it's imprecise in the source log itself, not just the
retrospective's summary of it.

**Claim: "the dismissAlert/completeTask/flagPaymentDispute instances of the same resurrection bug
(spread across rounds 1,2,4,5) likely would've surfaced together with an exhaustive matrix from round
1."**
**CONFIRMED as to WHICH rounds, and the "likely would've" is appropriately hedged (this is the
retrospective's own speculative claim, not something it presents as fact).** Cross-checking against the
log: round 1 found dismissAlert's resurrection bug (line 12: *"dismissAlert clears Room.alertState but
never closes the underlying Task, so the next recompute... silently resurrects a dismissed alert"*).
Round 2 found a refinement of the same class (dual-task dismiss ambiguity). Round 4 found
flagPaymentDispute's missing find-before-create guard (*"two consecutive host clicks could create two
concurrently-OPEN DISPUTE tasks"*). Round 5 found completeTask writing `DONE` instead of `DISMISSED`,
explicitly named in the log as *"the exact bug class iteration 2 fixed for dismissAlert, reopened
through a second, spec-introduced path."* So yes — the SAME underlying bug class recurred across
rounds 1, 2, 4, 5 in different call sites before round 6 asked for the exhaustive enumeration that
closed it at round 7. The retrospective's inference (an exhaustive matrix up front might have caught
all of these together) is a reasonable, appropriately-hedged reading of real evidence — I can't verify
the counterfactual ("would've surfaced together"), but the pattern it's built on is real.

**Claim: "The concurrency bug (round 11 — a partial unique index) is a case where rounds 4 and 10 both
used 'race' language but neither reasoned about Postgres's actual isolation level, because nothing
forced a dedicated concurrency lens until round 11."**
**PARTIALLY CONFIRMED, with a specifics correction.** Round 11 result: *"Found a real distinction
between two race classes: the in-transaction checks from gaps #6/#15 close stale-pre-transaction-reads,
NOT true concurrent transactions both reading zero rows under Postgres's default ReadCommitted
isolation... Fixed: added a partial unique index (tasks_open_room_type_unique, raw SQL)."* This
confirms the mechanism and the round number (11) exactly. But "gaps #6" traces to iteration 4's
flagPaymentDispute find-before-create fix, and "gaps #15" traces to iteration 10's — the retrospective
says "rounds 4 and 10 both used 'race' language," which is a reasonable paraphrase of gap #6 (round 4)
and gap #15 (round 10) both being pre-transaction-read guards later shown to be insufficient against
true concurrent transactions. I did not find the literal word "race" quoted in rounds 4 or 10's log
text (round 4's language is "two consecutive host clicks," round 10's is "the same pre-transaction race
shape already fixed... silently reintroduced") — round 10 DOES use the word "race" ("the same
pre-transaction race shape"); round 4 does not use that word but describes the identical race
condition in different terms. Close enough to call CONFIRMED in substance, imprecise in exact wording
attribution to round 4.

**Claim: "Round 9 wasted a cycle because the Verifier expected code to exist during plan-check review,
when it should have been told explicitly this was plan-check mode."**
**CONFIRMED, and the log gives a cleaner account than the retrospective's summary.** Iteration 9
result, quoted in full: *"Verifier reported gap_type: KNOWLEDGE, broken_assumption: 'the spec assumes
the codebase already contains 8 iterations of applied fixes.' This is factually incorrect as a read of
the spec: this entire 9-round process has been plan-check mode throughout (every single dispatch said
'plan-check Verifier'... )... The Verifier conflated 'the plan document has a revision history' with
'the codebase should already reflect that history,' which is a category error, not a spec defect...
Treated as a harness-fault-class miscalibration."* Iteration 10 confirms the fix worked: *"No design
change applied -- iteration 9's finding was a category error... Added an explicit note to the spec's
own Context section clarifying that every round has been plan-check... Re-running plan-check as
iteration 10 with this clarification in place... Not a miscalibration this time."* So: round 9 WAS a
real miscalibration (Verifier wrongly believed the spec assumed pre-existing code), Oga correctly
arbiter-classified it as harness-fault rather than treating it as a fresh design gap, and the fix (an
explicit plan-check-mode note added directly into the spec's Context section) demonstrably worked at
round 10. The retrospective's framing ("wasted a cycle... should have been told explicitly") is
accurate, though it undersells that Oga's own arbiter-classification already caught this in real time
— it was not a silent miss that shipped, it was diagnosed and fixed within the very next round.

### Ground-truth verdict

The retrospective is **substantively accurate** on the mechanisms and bug classes (exhaustive
enumeration works, PENDING_VACANCY was genuinely unaudited, a real Postgres concurrency gap needed a
dedicated lens, round 9 was a real plan-check-mode miscalibration). It is **imprecise on round-number
attribution** in two places (round 6 vs 7 for the Task-path sweep result; the round-4/round-10 "race
language" wording), and it **omits the single most important fact**: this entire 13-round process
produced **zero code** — it is a plan-check-only build, not a multi-round Coder/Verifier code loop as
the "12 rounds → 4-6 rounds" style framing might suggest to a reader. Given this is corroborated
against a real, quotable, non-fabricated log (not an invented citation — the file exists, the round
numbers are real, the quotes are verbatim), I rate this **HIGH confidence on substance, MEDIUM
confidence on precise attribution**. This is stronger grounding than "unverified third-party
narrative," but the round-mapping imprecision means proposal experiments below should cite round
**7** (not 6) for the sweep result, and treat the "12 rounds" figure as "13 logged iterations, plan-check
only, 18 real gaps found" per the log's own running count, not the retrospective's phrasing.

---

## Step 2 — What loop-team already has (gap check before scoring as "new")

### Proposal #1 (exhaustive enumeration at plan-check) vs. existing mechanisms

**`learnings.md` 2026-07-02 entry "RLS plan-check: prove the class is EMPTY, don't fix instances one at
a time"** is a **directly on-point, already-logged prior incident of the identical pattern**, quoted:
*"The RLS spec took 4 plan-check iterations. iters 1-3 each found a DIFFERENT pre-context read/write on
a policy-bearing table... The architecture was sound the whole time; the failures were an incomplete
ENUMERATION. What finally passed (iter4): embed a COMPLETE db.<model> classification table in the spec
and make the acceptance criterion a class-(c)-empty sweep over the live tree... Rule: for a
cross-cutting invariant (every X must do Y), the gate is an executable exhaustive sweep proving the
violating class is empty — spot-fixing named instances just surfaces the next unnamed sibling."* This
is the EXACT same lesson the ops-clock retrospective is proposing, discovered independently, on a
different build, and already written down as a standing rule — just not yet generalized into
orchestrator.md's step-1 text as a default instruction. **Proposal #1 is NOT a new capability gap. It is
a documentation/enforcement gap**: the lesson has now been independently re-learned twice
(RLS build, then ops-clock) and logged twice in `learnings.md`, but orchestrator.md step 1 (lines 47-65)
still only says "red-team the brief's acceptance criteria" and "enumerate and exercise the WHOLE
artifact's external surface" generically — it does not say "for any acceptance criterion implying a
finite state space or a class of call sites, require an explicit enumerated table + an executable
emptiness sweep AT PLAN-CHECK time, before the first PLAN_PASS." Two independent real incidents
converging on the identical fix is a strong signal to promote it from learnings.md to a standing
orchestrator.md RULE — but that's a different (cheaper, more certain) fix than "invent proposal #1 as a
new mechanism."

**`test_writer.md`'s LOOP-M1 (traversal-completeness)** and **`verifier.md`'s LOOP-M4
(downstream-consumer sweep)** — read both in full. LOOP-M1: *"When the artifact declares a FINITE input
space (neighborhoods, counties, sources, tiers), write a traversal-completeness test: obtain the
declared set and the code's actual set and `assert traversed == declared`."* LOOP-M4: *"When a prior
iteration made a value DYNAMIC..., enumerate EVERY downstream consumer of that value and assert each
branches on it."* Both are REAL, and both cover closely-related substance — but at a **different layer
and a different time**. LOOP-M1/M4 are TEST-writer and post-build VERIFIER instructions: they fire
after a spec exists and (for LOOP-M1) after code exists, producing an executable regression test. They
assume the enumerable set is already named in the spec/code. Proposal #1's actual ask — confirmed by
re-reading the ops-clock log — is to require the enumeration **inside the spec itself, at plan-check
time, before any Coder or Test-writer is dispatched**, so the PLAN-CHECK VERIFIER (not the Test-writer,
not the post-build Verifier) is the one forced to enumerate and check each element of the class before
a single line of test or implementation code is written. That is a genuinely **different point in the
loop** (plan-check vs. test-authoring vs. post-build verification) — LOOP-M1/M4 do NOT cover it,
because they fire too late to prevent the spec itself from omitting a class member (the ops-clock
build's round-1-through-5 problem was that the SPEC never named all 6 Task-mutating paths, so no
Test-writer or post-build Verifier LOOP-M1/M4 check could have caught the 5 that were never in the spec
to test). **Conclusion: proposal #1 IS additive** — it closes a real timing gap that LOOP-M1/M4 leave
open (spec-authoring time), even though the *general principle* (exhaustive enumeration beats
one-instance-at-a-time fixing) is not new — it's the RLS learnings.md lesson, generalized one level
earlier in the pipeline and formalized as a standing plan-check RULE rather than a role-specific test
pattern.

### Proposal #3 (round 9's miscalibration) vs. existing verifier.md mechanism

**`verifier.md` lines 99-123 ("Output tokens for machine-readable gate integration")** were read in
full. This section ALREADY explicitly distinguishes plan-check mode from post-build mode, verbatim:
*"In plan-check mode (Oga dispatched you to review a spec/plan BEFORE any Coder was dispatched): Final
line MUST be exactly `LOOP_GATE: PLAN_PASS` or `LOOP_GATE: PLAN_FAIL`"* vs. *"In post-build mode
(reviewing code AFTER the Coder ran): Final line MUST be exactly `VERDICT: PASS`..."* The role brief
the Verifier is instructed to read (per orchestrator.md's dispatch conventions) already carries this
distinction as a structural part of the role, not an ad hoc dispatch note. Cross-referencing against
`orchestrator.md`'s dispatch conventions (lines 231-247): every plan-check dispatch is required to carry
a `description` field beginning with the literal string `"plan-check Verifier"` (enforced by
`hooks/loop_stop_guard.py`'s `_VERIFIER_DETECT` regex) — so the mechanism for signaling plan-check mode
exists at BOTH the role-brief level (verifier.md's own text) and the dispatch-hygiene level (a hook that
checks the description field). **This means round 9's failure was NOT a missing mechanism — it was a
dispatch/spec-quality failure**, i.e., that specific Oga dispatch (or, more likely per the log, a spec
whose Context section didn't yet carry an explicit plan-check-mode note) didn't make the mode
unmistakable enough for that particular Verifier instance to internalize it, even though the surrounding
machinery (role brief + hygiene hook) already encoded it. The FIX that actually worked (confirmed at
round 10) was exactly this: **add the clarification directly into the spec's own Context section**, not
change verifier.md or add a new orchestrator.md mechanism. This is the cheapest possible class of fix —
it is a **spec-authoring convention**, not new engineering. **Conclusion: proposal #3, as "add a
mechanism," is NOT a real gap — the mechanism exists. The real, narrow, already-validated fix is a
one-line addition to orchestrator.md's plan-check dispatch instructions: "when re-dispatching a
plan-check Verifier after 2+ prior rounds, the spec's OWN Context section must state explicitly that
this is a pre-implementation design review and that the absence of code in the repo is expected, not a
finding" — which is nearly identical in spirit to the ALREADY-EXISTING learnings.md rule from earlier
today (2026-07-02, "Re-dispatching a Verifier after a PLAN_FAIL: don't narrate the prior round's
result-shaped language inline... write it into the artifact instead"). This is the SAME class of fix
(put context into the spec artifact, not the dispatch prompt) applied to a slightly different failure
mode (mode confusion, not verdict-priming). Confidence this is dispatch-quality not mechanism-gap: HIGH
— round 10's clean pass with zero mechanism change is direct proof.

### Proposal #2 (parallel adversarial lenses) vs. existing orchestrator.md dispatch model

Searched `orchestrator.md`'s "How roles are dispatched" section (lines 231-291) and the whole file for
"parallel" — **zero matches**. The entire plan-check loop, as specced and as actually run in the
ops-clock log (13 sequential iterations, one Verifier dispatch per round, each waiting on the prior
round's outcome before re-dispatching), is **implicitly single-Verifier-per-round**. There is no
existing suggestion, default, or precedent anywhere in orchestrator.md for dispatching N Verifiers with
different lenses in parallel on the same plan-check round. **Proposal #2 is a genuinely new mechanism**
— unlike #1 and #3, it does not duplicate anything already standing.

---

## Step 3 — Scoring the 3 proposals

Priority formula (from `orchestrator.md` "Prioritizing radar candidates"):
`priority = 0.40·(effect×confidence) + 0.20·phase_fit + 0.15·risk_reduction + 0.10·uncertainty − 0.15·cost_to_test`

### Proposal #1 — Require exhaustive enumeration of finite state/action spaces AT PLAN-CHECK time

- **name:** Plan-check enumeration-completeness rule (generalize the RLS + ops-clock lesson into a
  standing orchestrator.md RULE, not a role-specific test pattern)
- **source:** `~/Claude/loop/loop-team/learnings.md` 2026-07-02 "RLS plan-check: prove the class is
  EMPTY" entry (real, independently reproduced incident, quoted above) + the ops-clock
  `plan_check_log.md` rounds 1-7 (real, independently reproduced second incident, quoted above).
  **Two independent real incidents**, not a single third-party narrative claim — this is the
  strongest-evidenced of the three proposals.
- **claim + evidence:** When a spec implies a finite class (task-mutating actions, enum values,
  policy-bearing tables), fixing discovered instances one at a time costs 1 plan-check round PER
  instance found by luck; naming the complete class explicitly and demanding an exhaustive sweep closes
  the whole class in one round. Evidence: RLS build went from "1 new leak found per round for 3 rounds"
  to "iter 4 PASS" the moment the classification table + emptiness sweep was specced. ops-clock rounds
  1,2,4,5 each found ONE new instance of the same resurrection-bug class in a DIFFERENT action; round 6
  named the complete 6-item surface; round 7 confirmed all 6 sound in a single dispatch.
- **where_it_wires_in:** `orchestrator.md` step 1 (plan/plan-check), as an explicit addition alongside
  the existing "red-team the brief's acceptance criteria" and "enumerate and exercise the WHOLE
  artifact's external surface" bullets (lines 62-65). Also touches `roles/verifier.md`'s plan-check
  guidance (currently silent on this specific pattern) — add a pointer there so the Verifier itself
  knows to ask "is there an implied finite class here, and has the spec named ALL of it?"
- **triage:** IMPLEMENTABLE NOW — this is a documentation/promotion fix (learnings.md entry →
  orchestrator.md standing rule), not new engineering; the mechanism (plan-check Verifier dispatch,
  gap_type: DESIGN handling) already exists and just needs a more specific trigger condition named in
  the instructions.
- **priority sub-scores:**
  - `effect` = 0.75 (two independent real builds show the same round-savings pattern; this is about as
    close to "measured" as a process lesson gets without a formal A/B)
  - `confidence` = 0.65 (real reproduced incidents, not paper-only — but still only 2 data points, both
    from the same operator/loop-team process, not a controlled comparison; capping short of "high"
    because there's no case where the OLD one-at-a-time approach was tried head-to-head against the NEW
    exhaustive-enumeration approach on the identical spec)
  - `effect × confidence` = 0.49
  - `phase_fit` = 1.0 (directly serves the current/next phase — every future plan-check build benefits
    immediately, no dependency on other unshipped work)
  - `risk_reduction` = 0.7 (closes a bug CLASS, not an instance — the RLS and ops-clock incidents both
    show this is exactly the kind of gap that silently ships if not caught, i.e., real de-risking)
  - `uncertainty` = 0.3 (this is fairly well-understood at this point — two clean incidents, low
    remaining unknown — so the exploration bonus is modest, not high)
  - `cost_to_test` = 0.15 (cheapest possible: editing orchestrator.md prose + a verifier.md pointer; no
    new code, no new infra, arguably doesn't even need a dedicated "experiment," just adoption + watch
    the next 2-3 plan-check builds for round-count effect)
  - **priority = 0.40×0.49 + 0.20×1.0 + 0.15×0.7 + 0.10×0.3 − 0.15×0.15 = 0.196 + 0.20 + 0.105 + 0.03 −
    0.0225 = 0.508**
- **risks:** Over-triggering — if Oga starts demanding an exhaustive enumeration table for EVERY spec
  regardless of whether a finite class is actually implied, plan-check dispatches bloat for simple
  specs. Mitigate by scoping the RULE's trigger condition narrowly (see Step 5 sketch): only fires when
  the spec's own acceptance criteria imply a class with more than ~2 members sharing a mutation pattern.
- **experiment (since this is IMPLEMENTABLE NOW, not strictly TESTABLE, adoption still warrants a
  cheap validation):** After the orchestrator.md edit lands, the next 2-3 plan-check builds that involve
  a finite state/action space should log whether the enumeration step was present in round 1 of the
  spec and, if so, whether round-to-PLAN_PASS count drops relative to the RLS/ops-clock baseline (4
  rounds, 7 rounds respectively, to first full-class closure). This is a within-subjects before/after
  comparison across future builds, not a formal RCT — cheap, directly actionable, no new infra needed.

### Proposal #2 — Parallel adversarial Verifier lenses per plan-check round

- **name:** Multi-lens parallel plan-check dispatch (N Verifiers, each briefed with a different
  adversarial lens — e.g. concurrency/isolation, enumerable-state-completeness, security surface — run
  concurrently instead of one generalist Verifier per round)
- **source:** The ops-clock retrospective's own inference from round 11 (concurrency bug surfaced only
  once "a dedicated concurrency lens" was forced) — this is the retrospective AUTHOR'S proposed
  generalization, not something directly observed in the log (the log never actually tried parallel
  Verifiers; it's a single sequential Verifier throughout all 13 rounds, confirmed by grep above).
  **This proposal itself is UNTESTED** — the evidence supports "a dedicated lens helps," not "parallel
  dispatch of multiple lenses helps," which is an extrapolation.
- **claim + evidence:** Claim is that dispatching 3-5 parallel Verifiers, each forced into a specific
  adversarial lens (concurrency, enumeration-completeness, security), would surface the round
  1/2/4/5/6/7/9/11 findings in fewer wall-clock rounds by forcing lens-diversity every round instead of
  hoping a generalist Verifier happens to reason about the right lens. Evidence for the UNDERLYING
  premise (lens-forcing helps) is real: round 6's explicit enumeration ask → round 7's clean sweep;
  round 11's dedicated concurrency framing → the partial-unique-index fix. Evidence for the SPECIFIC
  mechanism (PARALLEL, N-way dispatch, every round) is absent — no build has tried it.
- **where_it_wires_in:** `orchestrator.md` step 1, as a NEW branch in the plan-check dispatch
  instructions (there is currently zero parallel-dispatch language anywhere in the file, confirmed by
  grep).
- **triage:** TESTABLE — this needs an actual before/after comparison, not direct adoption. It is a
  meaningfully different mechanism from #1 and #3 (both of which are "generalize an already-proven
  pattern"); this one has no proof yet that PARALLEL is better than SEQUENTIAL-with-explicit-lens
  (which is what actually worked in the log at rounds 6→7 and 10→11).
- **cost tradeoff (explicitly addressed per the assignment):** Running N parallel Verifiers on EVERY
  plan-check multiplies token/agent cost for ALL builds — including a 2-line config change spec that
  has no concurrency, no finite enumerable space, and no security surface. The ops-clock build itself is
  evidence against an UNCONDITIONAL default: rounds 1, 2, 3, 4, 5, 8, 9, 10, 12, 13 each found exactly
  ONE gap with a SINGLE generalist Verifier — a concurrency-lens or enumeration-lens dispatch would have
  been wasted parallel spend on those rounds (nothing in rounds 1-5, 8-10, 12-13 needed a concurrency
  lens specifically; only round 11 did). An unconditional N-way parallel default would have cost
  roughly Nx the Verifier-dispatch spend across all 13 rounds to catch exactly ONE finding (round 11)
  that a targeted single-lens dispatch could have caught just as well once concurrency was IDENTIFIED as
  relevant — which the log shows Oga/the Verifier reasoning process was capable of doing WITHOUT a
  standing parallel-lens default (round 11 got there sequentially, just one round later than an
  optimally-triggered dedicated lens might have).
- **A CONDITIONAL trigger is the better-scoped version — concrete sketch:** Dispatch parallel lenses
  only when the SPEC (at plan-check draft time, before round 1) exhibits one or more of these
  cross-cutting risk indicators, checked mechanically against the spec text:
  1. **Concurrency/isolation indicator:** the spec mentions a database transaction, a unique constraint,
     "race," "concurrent," "simultaneous," or describes two or more actions that can write the same
     row/record.
  2. **Finite enumerable state-space indicator:** the spec defines an enum, a state machine, or a fixed
     set of N≥3 actions/paths that mutate a shared piece of state (exactly the AlertState/6-action
     pattern from proposal #1 — note this OVERLAPS with #1's trigger, which argues for merging the two
     triggers into one shared "cross-cutting risk" check rather than building #2 as fully separate
     machinery).
  3. **Security-sensitive surface indicator:** the spec touches auth, RLS/row-level policy, session
     handling, or an externally-reachable endpoint.
  If NONE of these fire, plan-check stays single-Verifier (the current, default behavior — no cost
  regression for simple specs). If ONE OR MORE fire, Oga dispatches the matching lens(es) IN ADDITION TO
  the generalist Verifier (2-4 parallel Agent calls total, not open-ended N), each with a one-line lens
  instruction appended to the standard plan-check dispatch (e.g., "In addition to the standard
  plan-check review, specifically reason about Postgres's actual isolation level for every
  read-then-write on a shared row — do not accept 'checked inside the transaction' as sufficient without
  naming the isolation level and whether two concurrent transactions could both read zero rows").
- **priority sub-scores:**
  - `effect` = 0.5 (plausible, and partially supported by the underlying "dedicated lens helps" evidence,
    but the PARALLEL-specific mechanism itself is unproven — discounted from #1's 0.75 because #1 has
    two clean real incidents of the EXACT mechanism proposed, while #2 only has evidence for a cousin
    mechanism)
  - `confidence` = 0.35 (this is explicitly a PROJECTION per the assignment's instruction — "12 rounds →
    4-6 rounds" style claims from an unverified retrospective with no A/B run. I'm scoring this
    meaningfully below proposal #1 because #1's mechanism was directly observed twice; #2's core claim
    — parallel beats sequential-with-explicit-lens — has never been observed even once)
  - `effect × confidence` = 0.175
  - `phase_fit` = 0.6 (relevant to current work, but less immediately actionable than #1/#3 since it
    requires the conditional-trigger design work first, not just a prose edit)
  - `risk_reduction` = 0.5 (COULD de-risk concurrency-class bugs earlier, but only if the trigger is
    well-scoped — a poorly-scoped unconditional version would ADD cost-risk, not reduce it, per the
    tradeoff analysis above)
  - `uncertainty` = 0.5 (genuinely under-tested — this is the most legitimate use of the exploration
    bonus among the three, since it's the one true "new mechanism" candidate)
  - `cost_to_test` = 0.45 (non-trivial: needs the conditional-trigger logic designed AND a comparison
    build run with it enabled vs. a matched build without, to see if concurrency/enumeration gaps
    surface earlier — meaningfully more expensive than #1 or #3's "just edit the prose" cost)
  - **priority = 0.40×0.175 + 0.20×0.6 + 0.15×0.5 + 0.10×0.5 − 0.15×0.45 = 0.07 + 0.12 + 0.075 + 0.05 −
    0.0675 = 0.2475**
- **risks:** (1) Cost multiplication on simple builds if the trigger is too loose (addressed above by
  the conditional design). (2) Parallel Verifiers reviewing the SAME spec text independently could
  produce CONFLICTING gap_type/proposed_fix records that Oga then has to reconcile — orchestrator.md's
  current gap-record handling (`roles/verifier.md` lines 108-115) assumes ONE Verifier's gap record per
  round; a parallel-dispatch design needs an explicit reconciliation step that doesn't exist today (this
  is itself a new piece of machinery, adding to cost_to_test). (3) Transfer-condition check: this
  pattern is not borrowed from an external repo/paper — it's the retrospective author's own inference —
  so there's no external execution-context mismatch to check, but the INTERNAL transfer condition (does
  loop-team's actual dispatch harness support N parallel Agent calls with reconciled verdicts?) is
  unverified; `orchestrator.md`'s dispatch conventions are written entirely in terms of one Verifier
  producing one `LOOP_GATE` token per round, and reconciliation logic for N tokens does not exist
  structurally today — an instructional-only "dispatch these in parallel and synthesize" note (with no
  reconciliation mechanism) could fail silently by having Oga just pick whichever Verifier's finding it
  likes, defeating the point.

### Proposal #3 — Explicit plan-check-mode framing to prevent round-9-style miscalibration

- **name:** Mandatory explicit plan-check-mode note in the spec's Context section after 2+ prior rounds
  (dispatch-prompt-quality fix, not a new mechanism)
- **source:** ops-clock `plan_check_log.md` iteration 9 result + iteration 10 (the fix that worked),
  both quoted verbatim above — a real, reproduced incident, directly confirmed.
- **claim + evidence:** Claim is that a plan-check Verifier, several rounds into a design-only review,
  can wrongly conclude the codebase should already reflect the spec's accumulated "Fixed:" language —
  a category error costing exactly one wasted round. Evidence: iteration 9 hit this precisely as
  described; iteration 10's fix (adding an explicit note to the spec's OWN Context section, not changing
  verifier.md or any hook) demonstrably worked — round 10 evaluated cleanly and found 2 NEW legitimate
  gaps instead of repeating the category error.
- **where_it_wires_in:** `orchestrator.md` step 1, plan-check sub-bullets (near line 58's "Persist each
  plan-check cycle..." instruction) — add: "After 2+ prior plan-check rounds, the spec's own Context
  section must explicitly state that this is a pre-implementation design review, that 'Fixed:' language
  throughout refers to spec-text corrections (not code changes), and that the absence of implementation
  in the repo is expected at this stage — do not rely on the dispatch prompt alone to carry this
  framing." This mirrors the EXISTING learnings.md 2026-07-02 rule ("Re-dispatching a Verifier after a
  PLAN_FAIL... write it into the artifact instead") closely enough that the cleanest fix is to broaden
  THAT existing rule's wording to explicitly cover "mode confusion" alongside "verdict-priming," rather
  than write a second, separate rule.
- **triage:** IMPLEMENTABLE NOW — as established in Step 2, the underlying mechanism (plan-check vs.
  post-build token distinction) already exists in `verifier.md` lines 99-123 and in
  `loop_stop_guard.py`'s dispatch-hygiene hook; what's missing is a one-line spec-authoring convention,
  already proven to work at round 10, not a new mechanism.
- **priority sub-scores:**
  - `effect` = 0.6 (proven to fix the EXACT failure at round 10 — but it's a narrow failure mode, one
    wasted round out of 13, not a broad class like #1's)
  - `confidence` = 0.7 (directly observed, single clean before/after in the same build — higher than
    #2's untested projection, comparable to #1's but with only ONE incident rather than two independent
    ones, hence slightly below #1's 0.65... actually reassessing: #1 had two INDEPENDENT builds
    reproduce the SAME lesson, which is stronger evidence than #3's one build with a clean
    before/after within itself. Setting confidence at 0.6, just below #1.)
  - `effect × confidence` = 0.36
  - `phase_fit` = 0.9 (immediately useful for any future multi-round plan-check build; slightly below
    #1's 1.0 because it's a narrower failure mode)
  - `risk_reduction` = 0.3 (fixes a one-round waste, not a bug class that would otherwise ship —
    lowest-stakes of the three, since a miscalibrated round-9-style Verifier gets caught by Oga's own
    arbiter-classification anyway, as it demonstrably did here WITHOUT this fix)
  - `uncertainty` = 0.2 (this is now well-understood — a single clean incident with a confirmed fix,
    little left to explore)
  - `cost_to_test` = 0.1 (cheapest of the three — a one-line orchestrator.md addition, broadening
    existing wording; effectively free to adopt)
  - **priority = 0.40×0.36 + 0.20×0.9 + 0.15×0.3 + 0.10×0.2 − 0.15×0.1 = 0.144 + 0.18 + 0.045 + 0.02 −
    0.015 = 0.374**
- **risks:** Very low — this is close to a pure documentation fix reinforcing an already-working
  pattern. The only risk is scope creep if it's written as a NEW standing rule instead of folded into
  the existing "don't narrate result-shaped language, write it into the artifact" rule from
  learnings.md, creating two overlapping near-duplicate rules that drift apart over time.

### Priority ranking summary

| Proposal | priority | triage | confidence rationale |
|---|---|---|---|
| #1 Exhaustive enumeration at plan-check | **0.508** | IMPLEMENTABLE NOW | 2 independent real incidents, mechanism already exists in learnings.md, closing a real timing gap vs. LOOP-M1/M4 |
| #3 Explicit plan-check-mode framing | **0.374** | IMPLEMENTABLE NOW | 1 real incident, clean before/after, mechanism already exists in verifier.md — pure dispatch-prompt-quality fix |
| #2 Parallel adversarial lenses | **0.2475** | TESTABLE | Genuinely new mechanism, but confidence capped low per the assignment's instruction (unverified projection); real cost tradeoff needs the conditional-trigger design before it's even test-ready |

---

## POST-REVIEW UPDATE (2026-07-02, later same day) — live evidence from iteration 14, and a process incident

**Process note first, for full transparency.** A second, independent live Oga session
(same session_id as this one, `66ac8675-...` per its own self-report — root cause was a
crash + `--resume` auto-relaunch leaving the original process alive too, not a deliberate
parallel session; see `feedback_loop_team_operational_gotchas_2026_07_02.md` item 6 and
`research/claude-code-duplicate-session-detection-2026-07-02.md`) independently wrote a
"Plan-check dispatch template" into `loop-team/orchestrator.md` covering proposals #1 AND
#2, WITHOUT a spec, plan-check, Test-writer, Coder decision log, or post-build Verifier —
it landed silently mid-commit and was reverted (`96693f8`) once discovered, specifically
because adopting proposal #2 as mandatory bypassed this dossier's own finding that it
wasn't ready. That process violation stands regardless of the substance below — a good
idea adopted without verification is still a defect in HOW it was adopted, not just WHAT
was adopted. This update section evaluates the SUBSTANCE on its own merits, separately.

**The live evidence.** That same instance then used its own (unvetted) template on a REAL,
in-flight plan-check thread — `runs/2026-07-02_ops-clock/plan_check_log.md`, iteration 14
— dispatching 4 parallel Verifiers (state-completeness, concurrency-isolation,
regression-audit, precision-of-instruction), each required to build an exhaustive
matrix/inventory for its lens before hunting gaps. Result: 3 of 4 lenses returned
`LOOP_GATE: PLAN_FAIL` with real, mutually distinct gaps in ONE round (the 19th/20th/21st
real gaps in this 14-round thread) — the highest single-round yield of the whole thread,
against a ~1.4-gaps/round average across rounds 1-13. Each gap is independently
plausible and traces to a DIFFERENT lens (regression-audit found a dropped atomicity
guard + cross-org check; concurrency-isolation found a genuine Postgres `ReadCommitted`
write-skew race distinct from an earlier unique-index fix; state-completeness found an
uncovered `PENDING_VACANCY` × open-Task matrix cell in two places) — consistent with the
hypothesis that distinct framings surface distinct bug classes a single generalist pass
would eventually find but not reliably in one round.

**Updated assessment (not a full re-score — this is one additional data point, read
honestly, not a declaration of proof):**
- This is real, live, verifiable evidence (the log is on disk, dated, internally
  consistent with the prior 13 rounds' own counts) — a genuine step up from "unverified
  third-party projection," which is what proposal #2's `confidence` was capped for
  originally.
- It is still **N=1** or a small, prompt-time A/B without a proper control arm (there is
  no run of "round 14 WITHOUT parallel lenses" to compare against directly — the ~1.4/round
  historical average is the closest available baseline, not a matched control) — real
  spec-density variance (this could simply be a bug-dense region of the spec) is not
  ruled out. Do not treat this as a passed PACE experiment; it is encouraging trial
  evidence, not an accept/reject result.
- The structural gap this dossier flagged for proposal #2 — no reconciliation mechanism
  for multiple simultaneous `LOOP_GATE`/gap records from parallel lenses — is STILL not
  built. Iteration 14 worked because a human (Nnamdi) and/or Oga manually read and
  applied all 3 gap records in sequence; that is exactly the "instructional-only
  guarantee" this dossier's transfer-condition check warned could work in the moment
  without a structural check that reconciliation actually happened correctly every time.
- **Recommendation update:** raise proposal #2 from "defer, park in radar.md" to
  "worth a properly-scoped PACE experiment sooner than originally ranked" — but still
  require the reconciliation-logic design (how Oga aggregates N gap records from
  parallel dispatches into one spec revision, deterministically, before re-running
  plan-check) as a prerequisite spec item, not skip straight to adoption on this one
  round's strength. Proposal #1 and #3's rankings are unchanged by this (proposal #1's
  own evidence bar already included this exact thread; #3 is orthogonal).

**Where this leaves the actual playbook:** as of this update, `orchestrator.md` does
**not** contain the plan-check dispatch template (reverted). Proposals #1 and #3 remain
queued to be built properly (spec → plan-check → Test-writer → Coder → Verifier) in a
future loop-team session; proposal #2 remains queued behind a reconciliation-logic design
spec, now with stronger (but still non-definitive) supporting evidence than before.

---

## Step 4 — Compare against the existing Tier A queue

Per `~/.claude/projects/-Users-eobodoechine/memory/project_loop_team_improvement_backlog.md`
(2026-07-02 addition), the current Tier A queue ahead of any new candidate is:
- **cookbook item 6** — VERIFIER evidence-bar rubric rewrite (explicit no-fire list for
  VERIFIER.md/VERIFIER_RENTALS.md)
- **cookbook item 4** — a 5th Failure Arbiter class for silent in-band tool-throttle strings
  (`rate_limit_error` etc. inside a 200 response)

Both are already scoped in `research/claude-cookbooks-review-2026-07-02.md` and flagged by the user's
own memory note as "next up... items 2 or 3 look cheapest to verify" for a first experiment.

**Ranked recommendation:**

1. **Proposal #3 slots in ALONGSIDE the existing Tier A queue, not ahead of it — but it is cheap enough
   to fold in as a near-zero-cost rider on whatever gets built next, rather than requiring its own
   dedicated cycle.** Its cost_to_test (0.1) is lower than either cookbook item, and it's a one-line
   orchestrator.md edit with a proven fix already in hand. There's no reason to sequence it behind
   cookbook items 4/6 — it can be applied in the same session as either, essentially for free. I recommend
   folding proposal #3 into the SAME orchestrator.md edit pass as whichever cookbook item is tackled
   next, rather than spawning a separate build cycle for it alone.

2. **Proposal #1 is close in priority (0.508) to a typical Tier A item and has real, twice-reproduced
   evidence — it should be promoted to Tier A, likely dispatched at the SAME priority tier as cookbook
   items 4/6, not ahead of or strictly behind them.** Its score (0.508) is actually the HIGHEST of all
   three proposals scored here, driven by strong effect×confidence (two independent incidents) and
   perfect phase_fit. Nothing about cookbook items 4/6 structurally blocks or is blocked by proposal #1
   — they touch different parts of the playbook (Failure Arbiter classes and VERIFIER.md evidence rules
   vs. orchestrator.md's plan-check step 1). I recommend Nnamdi/Oga slot proposal #1 in as a **third Tier
   A item**, run in whichever order is most convenient, rather than deferred to Tier B — the cost is low
   (prose edit) and the evidence bar (2 independent real incidents) is stronger than a typical
   speculative radar candidate.

3. **Proposal #2 goes to Tier B/C (`research/radar.md`), not built now.** Its priority (0.2475) is
   meaningfully below both cookbook items and both of the other two proposals here, its confidence is
   explicitly capped as a projection (per the assignment's own instruction), and — critically — it is
   the one candidate whose GUARANTEE (reconciling parallel Verifier verdicts) is not currently
   enforceable by any existing structural mechanism, meaning it would need real design work (the
   conditional trigger + a reconciliation step for N gap records) before it's even ready for a TESTABLE
   experiment, let alone adoption. I recommend adding it to `radar.md` with the conditional-trigger
   sketch above attached, flagged as "needs reconciliation-logic design before an experiment can run,"
   rather than treating it as ready to test today.

This reasoning is grounded in the actual priority scores computed in Step 3, not vibes: #1 and #3 both
score above 0.37 with HIGH-confidence real evidence and near-zero cost; #2 scores well below both
existing Tier A items' implied bar (cookbook items 4/6 are already-scoped, higher-confidence,
purpose-built candidates) and is not yet even experiment-ready.

---

## Step 5 — Concrete sketch for what to build now (proposals #1 and #3)

Both are ready-to-spec prose edits to `orchestrator.md`. I am NOT making these edits myself (Researcher
does not implement) — this is the sketch Oga can turn directly into a spec.

### Sketch A — Proposal #1 (exhaustive enumeration rule)

**Where:** `orchestrator.md`, step 1 ("Restate & plan"), inserted as a new bullet immediately after the
existing bullet ending "...open one to confirm then skip the tier and grade the Sr/VP/Lead/Mgr
equivalent" — i.e., directly after the classifier/filter corpus-coverage bullet (current line 65),
before step 2 ("Dispatch Test-writer").

**New text to add (Oga can adapt wording, this is the substance):**

> **When a spec implies a finite class sharing a mutation/behavior pattern (a fixed set of actions that
> all write the same piece of state, an enum with N values, a table of policy-bearing models, a set of
> endpoints/URLs/sources), name the COMPLETE class explicitly in the spec's own text — do not rely on
> discovering members one at a time across plan-check rounds. Concretely: (1) enumerate every member of
> the class in a table or list inside the spec; (2) make the plan-check acceptance criterion an
> exhaustive per-member check ("Verifier confirms EACH of the N members individually"), not a generic
> "review the design"; (3) if a plan-check round finds ONE violating instance of a cross-cutting
> pattern, treat that as a signal the class itself needs to be named and swept, not just that one
> instance patched — the next round's dispatch should ask the Verifier to check every other member of
> the same class, not just re-review the one fix. Two independent incidents (RLS plan-check,
> `learnings.md` 2026-07-02; ops-clock alert-engine plan-check, rounds 1-7,
> `runs/2026-07-02_ops-clock/plan_check_log.md`) both show the same pattern: fixing instances one at a
> time costs one round per lucky find, while naming the complete class and demanding an exhaustive sweep
> closes the whole class in one round.**

**Also add a short pointer in `roles/verifier.md`**, near LOOP-M3/LOOP-M4 (after line 135), as a new
LOOP-M5:

> **LOOP-M5 — PLAN-CHECK CLASS COMPLETENESS (added 2026-07-02).** During plan-check (before any code
> exists), if the spec implies a finite class of call sites/states/actions sharing a pattern, do not
> just review the design generically — explicitly ask "has the spec named EVERY member of this class,
> and does it specify a check for each one individually?" A spec that names 3 of 6 members of an
> obvious class is an incomplete-enumeration gap, `gap_type: DESIGN`, even if the 3 named members are
> each individually well-specified.

### Sketch B — Proposal #3 (plan-check-mode framing after 2+ rounds)

**Where:** `orchestrator.md`, step 1, in the plan-check bullet block, immediately after the existing
line 58 ("Persist each plan-check cycle to `runs/<timestamp>/plan_check_log.md`: `gap_type`,
`broken_assumption`, `proposed_fix`, iteration number, outcome.").

**New text to add:**

> **After 2 or more plan-check rounds on the same spec, the spec's own Context section must explicitly
> state: this is a pre-implementation design review; any "Fixed:"/revision-history language describes
> corrections to the SPEC TEXT across rounds, not changes already applied to the codebase; and the
> absence of implementation in the repo at this stage is expected and correct, not a finding. Do not
> rely on the dispatch prompt alone to carry this framing — write it into the spec artifact itself, so a
> fresh plan-check Verifier reading only the spec (never primed by Oga's dispatch language, per the
> existing withholding rule) cannot mistake a multi-round revision history for a claim about the
> codebase's current state. (Real incident: ops-clock alert-engine build, iteration 9 — a Verifier
> concluded the spec assumed 8 iterations of applied fixes already existed in the codebase, a category
> error; iteration 10 added exactly this note and the same Verifier evaluated cleanly. See
> `runs/2026-07-02_ops-clock/plan_check_log.md`.)**

This should be folded into (broadens, not duplicates) the existing learnings.md 2026-07-02 rule
("Re-dispatching a Verifier after a PLAN_FAIL: don't narrate the prior round's result-shaped language
inline... write it into the artifact instead") — same underlying principle (put context IN the spec
artifact, not the dispatch prompt), extended to cover mode-confusion, not just verdict-priming.

---

## What I dropped and why

- I did not treat "the retrospective is a competing loop-team implementation's output" as disqualifying
  — it's a real, verifiable artifact (the plan_check_log.md and SESSION_CONTINUATION.md are genuine
  loop-team run artifacts, produced BY loop-team's own plan-check mechanism, just narrated afterward by
  an unaudited session). The narrative WRAPPER is unaudited; the underlying LOG is not — I verified the
  log directly, which is why ground-truthing was possible at all.
- I did not score "adopt the ops-clock build's specific AC numbering/spec conventions" as a 4th
  candidate — the assignment scoped this to exactly 3 proposals, and the spec-mechanics (AC20-AC33
  numbering, etc.) are build-specific, not portable playbook changes.
- I did not independently re-verify the "18th real gap" / "17 gaps across 12 rounds" running counts
  beyond confirming the log's own self-reported counts match round-to-round (each iteration result
  states a gap count consistent with the prior one) — this is an internal-consistency check, not an
  external verification, and I'm flagging that distinction rather than silently upgrading it to
  "independently confirmed."

## Transfer-condition check (required per role brief)

All three proposals originate from loop-team's OWN artifacts (the ops-clock log, the RLS learnings.md
entry, verifier.md's own existing text) or a narrative built directly on top of them — none are borrowed
from an external repo, paper, or third-party framework, so the usual "does external context X transfer
to loop-team's context Y" check is largely moot here. The one place it partially applies is proposal #2:
the retrospective author is implicitly borrowing an "ensemble of specialized judges" pattern common in
LLM-judge literature (multiple judges, each with a narrower rubric, catch more than one generalist).
(a) That pattern's usual execution context assumes a cheap, parallelizable judge call with a
reconciliation/voting step already built. (b) Loop-team's actual context does NOT yet have a
reconciliation step for multiple simultaneous `LOOP_GATE` tokens/gap records — confirmed by re-reading
`orchestrator.md`'s dispatch conventions (single Verifier, single gap record, single token, per round).
(c) If proposal #2 were adopted purely instructionally ("dispatch N Verifiers, then Oga synthesizes"),
the reconciliation guarantee would be enforced ONLY by Oga's own judgment in the moment, with no
structural check that Oga actually reconciled conflicting verdicts rather than picking its preferred
one — this is exactly the kind of instructional-only guarantee that can fail silently, per the standing
"instructional vs. structural enforcement" distinction this role is required to flag. This is the
central reason proposal #2 is scored TESTABLE/Tier B rather than IMPLEMENTABLE NOW even setting aside its
lower priority score.
