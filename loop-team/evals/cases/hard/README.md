# Hard-case hunt — staged corpus + a NEGATIVE result (2026-06-23)

This directory is a **staging area**, NOT part of the regression suite.
`run_evals.load_cases()` reads only top-level `cases/*.json`, so nothing here is
auto-loaded or scored by `run_evals`. (Verified: 0 `hard-` ids reach the 45-case
suite; SUITE stays GREEN.)

## What this is
The next step toward measuring judge-prompt improvements (RRD / C9) was to build a
suite a *strong* flat-prompt judge genuinely fails — the **39-case balanced
verifier-target suite used by `ab_rrd`** (30 traps + 9 goods; distinct from the
45-case top-level `run_evals` suite, which also includes harness cases) is SATURATED
(39/39 on Sonnet AND Haiku; see fix_plan.md "C2 RRD" + the hard-case-discrimination
dossier). Target: flat-judge accuracy **60–80%** (the discrimination band). This was
the first hard-case generation + judging pass.

## What happened — the batch did NOT discriminate
- **`_candidates.json`** (16 COMPOUND cases: 5 row-level buried-disqualifier, 5
  two-stage-math, 6 cross-section; 6 of 16 goods). Judged by **two** independent
  Sonnet sub-agents on the bare `roles/verifier.md` (no fix-hints, blind artifacts).
  **Both runs: 16/16 correct** on accept/reject (test-retest agreement 1.000).
- **`_candidates_v2.json`** (6 "decidable-but-counterintuitive" cases: a
  semi-monthly=24-vs-biweekly=26 knowledge trap both directions, a past-deadline
  date trap, a percentage-points-vs-relative unit trap, two over-rejection goods —
  an ADU "private suite" that is a whole unit, and a one-time move-in premium with
  an in-cap standing rent). One Sonnet judge: **6/6 correct**.
- **Total: 38 scored judgements (16 + 16 + 6) across 22 distinct cases, 0
  accept/reject errors.** Recorded in `recorded_verdicts.json`. (3-label agreement
  is also high; the one prior label gap — the OTE case — was a gold-label fix:
  `expected` corrected from FAIL to FALSE-PASS, which both judge runs already
  returned, so gold and judge now agree at the label level too.)

## The finding (durable)
For a **Sonnet-class judge invoked with reasoning room**, the hardened `verifier.md`
is at ceiling on **objective-gold** cases — including compound (multi-row, two-stage,
cross-section) and counterintuitive (semi-monthly periods, percentage points,
deadlines) ones — and shows **zero over-rejection** on hard goods. The reason is
structural: a case with an **incontestable objective gold** is, almost by
definition, **reachable by a careful per-row / per-number / per-unit read** — the
same property that makes the gold defensible makes the case easy for a strong
reasoner. The earlier over-rejection was an *invocation* artifact (terse one-line
verdicts), re-confirmed here; it is not a reasoning deficit.

So the 60–80% discrimination band for a frontier judge is **not reachable with
artifact-alone incontestable gold**. It would require either (a) genuinely
ambiguous/subjective gold (forbidden by the project's honesty bar), or (b)
information not in the artifact (violates artifact-alone judging). [UPDATE: we expected
the band to exist for a weaker judge — a prior C2 RRD run saw Haiku over-reject 2/39 —
but the Phase-0 probe below shows Haiku ALSO saturates these 22 when given a reasoning
invocation, so the band isn't reachable here even on Haiku.]

## UPDATE 2026-06-23 — the Haiku probe was RUN: Haiku ALSO saturates
Phase-0 probe (same bare verifier.md + same 22 blind artifacts, judged by **Haiku**
Agent sub-agents, 2 runs, $0): **both runs 22/22 correct on accept/reject (test-retest
1.000), zero over-rejection on the 9 goods** (recorded in `recorded_verdicts.json`
`haiku_run_A/B`). Haiku nailed semi-monthly=24 both directions, the two-stage fee
rollup, biweekly annualization, percentage-points-vs-relative, and the past-deadline
trap. So the discrimination band does NOT exist on these 22 even for Haiku **when Haiku
is given the same reasoning-room invocation** (full verifier.md + "reason then commit" +
generous tokens). This is CONSISTENT with (not proof of) the through-line that
over-rejection is an invocation artifact rather than a capability floor: on THESE 22
cases under THIS reasoning invocation, over-rejection vanishes for BOTH tiers (Sonnet and
Haiku). It is NOT shown that reasoning room would fix Haiku's prior over-rejection on the
ab_rrd 39-case set (different invocation AND cases — see the confound below); that needs
its own run before any cross-tier generalization.
- SCOPE/CONFOUND (honest): this tests a *reasoning-invoked bare-verifier* Haiku, not the
  `ab_rrd` `build_prompt` invocation where a prior run saw Haiku over-reject 2/39. Those
  differ in both cases AND framing. What this probe settles: these 22 are not a
  Haiku-discrimination set under a reasoning invocation.
- IMPLICATION: the existing **cross-section** (address, wrong-role) and **row-level**
  (gmail-among-8, fabricated-bullet-among-6) cases already saturated on BOTH tiers →
  strong signal the artifact-text regime is broadly saturated for reasoning judges. More
  pure-text cross-source cases will likely saturate too. The surest remaining
  discriminator is **true execution (Lane C)**; the one untested text shape is
  **high-cardinality cross-source** (a long ~15–20-row export/page-text block with one
  laundered row buried) — cheap to probe before committing to a big text batch or the
  Lane-C harness build.

## How to USE this corpus (point 1 superseded by the update above)
1. ~~**Haiku discrimination set.**~~ DONE — Haiku saturates (22/22 ×2); not a
   discrimination set under a reasoning invocation.
2. **Robustness corpus (not regression).** Evidence the hardened verifier handles
   compounding + counterintuitive objective defects. Do NOT fold into the certified
   κ=1.0 baseline — that would add saturated cases and overstate coverage.
3. **NOT frozen as "verifier-FAILS."** The hunt's freeze rule keeps cases the
   verifier gets WRONG; it got none wrong, so nothing here is promoted into
   `cases/`. The negative result IS the deliverable.

## Implication for the project
For Sonnet-class judging the prompt is at ceiling — marginal prompt-tuning value
≈ 0. Durable, model- and invocation-independent gains come from **deterministic /
execution-grounded checks** (the `arithmetic_check.py` pattern: code computes the
number, the LLM judges soundness), not prompt elaboration. This corroborates the
session through-line.
