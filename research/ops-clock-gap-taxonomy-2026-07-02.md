# Ops-clock plan-check: gap taxonomy across all 32 findings (2026-07-02)

**Mode:** A (improve the loop), extending `research/loop-team-process-retrospective-review-2026-07-02.md`
(which ground-truthed gaps 1-21 across iterations 1-14) to the full set through iteration 17 (gaps 22-32),
plus a direct answer to "is there an existing bug-metric/defect-classification tool for this."

**Prompted by:** Nnamdi pushing back on an "diminishing returns" framing (iterations 14-17 found 3,4,3,4
real gaps — flat, not falling) and asking whether the volume means the original spec draft was lazy.
This doc answers that with an actual category breakdown instead of a vibe.

---

## Part 1 — Is there an existing bug/defect classification tool for this?

Short answer: **no complete off-the-shelf tool does this exact job**, and that's already been
rigorously established — see `research/plan-check-reconciliation-prior-art-2026-07-02.md` (plus two
deeper follow-up passes) for the full search. Summary of what's real and what isn't:

| Tool/technique | Real? | Does it solve OUR problem? |
|---|---|---|
| `ai-code-reviewer` (calimero-network, OSS, MIT) | Yes — verified by direct source read | Partial: real clustering + consensus + "never silently drop a CRITICAL finding" severity-bypass pattern. **No cross-agent or cross-round contradiction detection** (confirmed absent on direct read of its architecture doc). |
| CodeRabbit merge-conflict agent | Yes, production | Different problem (git branch merges, not reviewer-finding reconciliation) — but its **fail-closed, name-the-reason, abort-rather-than-guess** decision pattern is directly reusable. |
| DefectDojo (OWASP, SARIF dedup) | Yes, mature, industry-standard | Proves **dedup is the solved problem industry-wide; conflict-detection between independent findings is not** — it doesn't even attempt it. |
| NLI requirements-conflict detection (academic) | Yes, real paper+data | Closest real match for pairwise contradiction-checking on free-text spec statements — but **F1 22–55%**, and its own documented blind spot (compositional/3-way conflicts) is *exactly* the shape of our gap #28 (see Part 3). |
| Mixture-of-Agents / JudgeBlender / "Nine Judges" ensembling | Yes, real, mature | Wrong problem shape entirely — these blend/vote on competing answers to the *same* question; our lenses answer *different* questions and produce non-competing findings. |
| SAT/SMT unsat-core analysis | Real technique | No bridge from free-text `proposed_fix` strings to formal clauses — dead end for "existing tool," though the *concept* (localize which two things conflict, not just that they do) is worth keeping. |

**What we already built in response:** `loop-team/harness/reconcile_gap_records.py` — a deterministic
reconciliation harness (no LLM calls of its own) that: (1) marks two gap records `INDEPENDENT` for free
if their `touches`/`mechanism_refs` are disjoint; (2) **mandatorily** triggers a fresh mechanism-trace
dispatch whenever two records share ALL `mechanism_refs` — this is the direct, named fix for gap #28
(see its own docstring: *"the gap-28 incident, where two conflicting ACs were never cross-checked
because nothing forced a shared-mechanism trace"*); (3) clusters near-duplicates using
`ai-code-reviewer`'s tuned `SequenceMatcher >= 0.85` threshold; (4) never silently drops a `DESIGN`-type
finding; (5) fails closed on any unresolved contradiction (CodeRabbit's pattern) rather than
auto-picking a fix. It exists, has a docstring-documented v1 scope cut (no cheap NLI pre-screen yet —
"fail toward more checking, not less"), and is ready to actually run against a real multi-lens round.

**Net:** the research already happened, same day, directly triggered by our own gap #28. Nothing here
warrants a fresh deep-research pass — the honest move is to *use* what's already built (see Part 4).

---

## Part 2 — Taxonomy: all 32 gaps, categorized

Eight categories emerged from re-reading every gap's `broken_assumption`/`why_it_fails` text directly
(not from vibes):

| Category | Definition | Gaps | Count |
|---|---|---|---|
| **Sibling-inconsistency** | An established fix/pattern applied to one call site, not proactively swept to a structurally-identical sibling | 7, 9, 15, 22, 29, 30, 32b | **7** |
| **Precision/ambiguity** | An instruction admits ≥2 readings, ≥1 wrong, and existing ACs wouldn't catch the wrong one | 3, 5, 8, 17, 18, 25, 32a | **7** |
| **Regression-risk** | The new design silently breaks an existing green test or safety net (fixture, sweep-table, etc.) | 10, 19, 23, 24, 27, 31 | **6** |
| **Missing-detail (original conception)** | An edge case/interaction never considered in the first draft at all | 1, 2, 4, 12 | **4** |
| **Concurrency/isolation** | A race condition, transaction-boundary, or lock-ordering hazard under real Postgres semantics | 6, 16, 20, 26 | **4** |
| **State-machine/enum completeness** | A specific enum value or Task-type combination left unmapped/unfiltered | 13, 14, 21 | **3** |
| **Mechanical/schema-validity** | A Prisma schema correctness issue, not a behavioral bug | 11 | **1** |
| **Cross-round contradiction** | Two independently-verified ACs from *different* rounds turn out mutually unsatisfiable | 28 | **1** |

(33 findings across 32 gap-numbers — gap 32 bundled two distinct findings.)

## Part 3 — What this actually shows

**"Was the initial build lazy?" — partially true, but concentrated almost entirely in the first two
rounds and then it stops.** Every single "missing-detail-in-original-conception" gap (category F: 1, 2,
4, 12) traces to iterations 1–2 of this 17-round thread. **Zero gaps in that category appear anywhere
from iteration 3 onward** — every one of the other 28 findings is a refinement-quality issue (precision,
sibling-sweep, regression-risk, concurrency, or the one true contradiction) on a spec that had already
absorbed real detail, not a "we never thought about this at all" miss. That's a meaningfully different
story than "the whole thing was underbaked" — the first draft was thin specifically about the
Task-dismiss interaction (a real, fair critique), and essentially nothing else.

**The two largest categories (sibling-inconsistency and precision-ambiguity, 7 each, 42% of all findings
combined) are exactly the two classes a *process* change can compress, not evidence of authorial
carelessness on each individual instance.** Sibling-inconsistency in particular is almost definitionally
a *reactive* discovery problem: gap 7 found flagPaymentDispute missing a guard COLLECTIONS/FLIP already
had; gap 9 found completeTask reopening a bug dismissAlert had already been fixed for; gap 15 found the
identical pattern again on flagPaymentDispute's guard; gap 22 found completeTask under-specified for
FLIP/dual-open; gaps 29/30 found the SAME atomic-update and P2002-catch patterns missing on two more
sibling closers; gap 32b found FLIP's creation guard un-scoped like every sibling guard. **Six separate
rounds, one recurring root cause: nothing forced an explicit sweep the moment a pattern got established.**
This is exactly what orchestrator.md's new "name the complete class" rule (added today, citing this
exact thread) targets — and it's also exactly what I flagged as my own process gap two turns ago, now
independently confirmed by the data rather than just self-diagnosed.

**Regression-risk (6 gaps, 18%) is a structurally different category worth naming separately:** every
one of these (10, 19, 23, 24, 27, 31) is something a real CI run against the actual test suite would
catch in one red/green signal, cheaply, the moment code actually exists — dashboard-adversarial.test.ts's
GROUP 7 failing, rls-source-sweep.test.ts flagging an unclassified call site, AC10/AC11 silently
no-opping. Pure plan-check (0 code, by design) has to catch these by *manual tracing* against the real
repo instead, which is exactly what the regression-audit lens has been doing — effective, but arguably
more expensive per-gap than letting the Test-writer/Coder loop's own test run surface the same
information for free once code exists. This is real evidence for the "some remaining risk is more
efficiently caught by the build loop's own gates than by more plan-check rounds" side of the question we
were discussing, even though it doesn't apply to concurrency/enum-completeness gaps (those need
adversarial *design* review — a green test suite doesn't reliably exercise a true concurrent-transaction
race or an unmodeled state combination without deliberately-written adversarial tests for it).

**Cross-round contradiction (gap 28) is its own thing, and it's the most concerning of the eight
categories precisely because it's the hardest to catch structurally** — two ACs, each individually
correct when verified in isolation in their own round, turned out incompatible only once traced against
a shared mechanism. This is the ONE category where "more plan-check rounds with the same method" doesn't
obviously help — it needs the mechanism-trace step `reconcile_gap_records.py` now provides, not just
another adversarial read.

## Part 4 — What this changes about the plan for iteration 18+

1. **Actually invoke `reconcile_gap_records.py`** on the next parallel-lens round's output, rather than
   reading all N gap records by eye and applying fixes in sequence (what's been done through iteration
   17). It exists, it's built for exactly this, and gap 28 is its own motivating incident.
2. **Apply the "name the complete class" rule (orchestrator.md, added today)** proactively when fixing
   any sibling-inconsistency-shaped gap: the moment a pattern is established at one call site, sweep
   every structurally-identical sibling in the SAME revision, rather than waiting for a future round's
   lens to rediscover it one at a time. This directly targets the largest category (7/33 findings).
3. **The parallel-lens dispatch is now conditional in orchestrator.md, not a standing default** — ops-clock
   still qualifies (concurrency-sensitive + finite enumerable state space + already non-converging after
   1+ round), so continuing with parallel lenses here remains correct under the new rule; it just isn't
   automatically the right call for a future, simpler spec.
4. **Regression-risk gaps are a signal to consider transitioning to the micro-step build loop sooner
   rather than later** — once the concurrency/enum-completeness/contradiction classes stop producing new
   findings, the remaining regression-risk-shaped residual risk may be more cheaply caught by an actual
   Coder + real test run than by continued manual plan-check tracing.

## Sources

- `research/loop-team-process-retrospective-review-2026-07-02.md` — ground-truthed gaps 1-21, scored 3
  proposed playbook changes (this doc extends its Part 2/3 to the full 32-gap set).
- `research/plan-check-reconciliation-prior-art-2026-07-02.md` (+ two deeper-pass follow-ups) — the tool
  research summarized in Part 1.
- `loop-team/harness/reconcile_gap_records.py` — the reconciliation harness this thread's gap #28
  directly motivated.
- `runs/2026-07-02_ops-clock/plan_check_log.md` — the 32-gap source log this taxonomy is built from.
- `runs/2026-07-02_ops-clock/specs/spec.md` — Context section, consolidated 1-32 gap list.
- `research/ops-clock-alt-method-experiment-2026-07-02.md` — follow-up: deep research on debugging methodologies in general, plus a real head-to-head experiment (structured state-transition-table enumeration) that found 2 more genuinely new gaps (39, 40) beyond this taxonomy's original 32-gap count.
- `research/defect-taxonomy-standards-prior-art-2026-07-02.md` — follow-up research checking this taxonomy
  against formal defect-classification standards (IBM ODC, IEEE 1044, HP Origin/Type/Mode, ISO/IEC 5055):
  confirms both ODC and IEEE 1044 are real, have primary-sourced precedent for pre-code/requirements-phase
  classification, but 4/8 of our categories (including our largest, sibling-inconsistency) have no home in
  either framework — a wholesale remap would lose information; only the Missing/Incorrect/Extraneous
  qualifier triad (independently present in all three frameworks) is worth adopting as a cross-cutting tag.
