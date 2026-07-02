# Researcher dossier — building a HARD, discriminating verifier-case suite (2026-06-23)

**Mode A + C. Produced by an independent Researcher sub-agent (Sonnet, WebSearch), honesty
bar enforced (every cited source opened + quoted; unverified ones listed in Part 8).**

## Why this exists
The RRD A/B (see fix_plan.md "C2 RRD rubric experiment") could not measure a gain because
the 39-case balanced verifier suite is **SATURATED**: the flat verifier.md prompt scores
**39/39 on both Sonnet and Haiku**. Zero headroom → no prompt change (RRD or any other) is
measurable. This dossier is the methodology to fix the EVAL, not the prompt: generate cases a
*strong* flat-prompt judge genuinely fails, so improvement becomes measurable.

## Verified sources (opened + quoted)
- **JudgeBench** (arXiv 2410.12784) — "converting existing difficult datasets into challenging
  response pairs with preference labels reflecting objective correctness"; "many strong models
  (e.g. GPT-4o) performing just slightly better than random guessing." Hardness axis = objective
  correctness on hard reasoning, not preference/tone.
- **RewardBench 2** (arXiv 2506.01937; repo allenai/reward-bench, 722★, MIT) — "~20 points lower
  than the first RewardBench"; decontamination via "new human prompts." "Chat-Hard" = compressed
  good-vs-slightly-better gap.
- **LLMBar** (princeton-nlp/LLMBar, 138★, MIT, ICLR 2024) — adversarial subsets (Neighbor/GPTInst/
  GPTOut/Manual): "outputs that deviate from instructions yet may possess deceptive qualities"
  (more engaging tone, higher apparent quality, broken on one constraint). The template for the
  "buried disqualifier" tactic.
- **RULERS** (arXiv 2601.08654) — "QWK 0.7122 vs 0.3500 for Direct Holistic Scoring." Holistic
  judges suffer *criterion conflation*; evidence-anchored decomposed rubrics double QWK. Direct
  empirical grounding for the RRD mechanism.
- **CALM bias framework** (arXiv 2410.02736) — position robustness 0.566–0.832, verbosity
  0.884–0.977, self-enhancement 1.16–8.91%; authority bias constructed by "injecting fake citation
  types (URLs, quotes, book references)."
- **AutoRubric** (arXiv 2603.00077) — "holistic scores cannot drive targeted improvement because
  they collapse the criterion-level signal"; decomposed feedback raised a score 0.47→0.85.
- **Self-preference** (arXiv 2604.22891) — multi-dimensional/decomposed evaluation "reduces SPB by
  31.5%"; "equal-quality pairs … negligible quality differences" construction.
- **Benchmark saturation** (arXiv 2602.16763) — "48% of 60 benchmarks exhibit high saturation … 
  repeated optimization compresses performance differences"; fix = "dynamic/adversarial data
  collection." Our 39/39 = S_index 1.0.
- **ATLAS / IRT** (arXiv 2511.04689) — item "discrimination parameter … differentiates stronger
  from weaker"; target difficulty where the model under test is ~60–75% for max Fisher information.

## Could NOT verify (do not over-cite) — Part 8
- JudgeBench per-model table (Sonnet 64% etc.) — abstract didn't render tables; directional only.
- RRD paper (arXiv 2602.05125) "+17.7pp": paper/topic confirmed to exist; the NUMBER is carried
  from the prior Researcher session's full-paper fetch (fix_plan.md C2 entry is the durable cite),
  abstract-only re-confirmed this run.
- CoBBLEr — no verifiable URL opened; not a primary cite.
- FLAMe-24B weight status — still unverified, RESEARCH_ONLY.

## The hardness target
**Flat-prompt accuracy 60–80% on the new suite** (not 0, not 39/39). Below ~50% gold reliability
degrades; above ~85% re-saturates. 60–80% is the discrimination window. The structural shape that
gives a DECOMPOSITION method (RRD) a fair chance: a multi-criteria artifact that satisfies N−1
criteria visibly with ONE buried/derived/mis-attributed disqualifier — the flat holistic read
averages it away (criterion conflation); per-criterion decomposition reaches it.

## Hardness-by-construction tactics (each keeps an INCONTESTABLE objective gold)
- **H1 Multi-criteria + buried disqualifier** (RRD edge HIGH) — N−1 rows pass with clean evidence,
  1 row fails; gold = arithmetic/field-identity. Source: fix_plan H6, RULERS, AutoRubric.
- **H2 Plausible-but-wrong derived number** (HIGH) — confident stated annualization that's wrong;
  gold judge must RECOMPUTE. Source: `cand-hourly-annualize-miscalc`.
- **H3 Authority-injection / mis-attributed evidence** (MOD-HIGH) — real quoted evidence that
  doesn't support the claim (deposit quoted as rent; summary-blurb comp vs real comp row). Source:
  CALM authority bias; fix_plan OTE-masks-subfloor, dead-link-self-tagged.
- **H4 Near-threshold value** (HIGH) — just on the wrong side of a floor/cap, needs exact compute.
  Source: fix_plan H6/H11.
- **H5 Plausible quality, required step NOT performed** (MOD-HIGH) — well-written report that
  *describes* opening a URL / doing a check but quotes no page content. Source: LLMBar Neighbor.
- **H6 Hard GOODs that expose over-rejection** (MOD) — every criterion explicitly satisfied; a
  paranoid holistic judge over-rejects. ≥40% of the suite MUST be goods. Source:
  `cand-substituted-live-equivalent`.
- **H7 Recall-failure trap** (MOD) — precision-only certification, drops never audited. Source:
  `verifier-recall-precision-only-pass`.

## The experiment (PACE-gated, one variable) — ready to wire
- metric: flat false-pass rate on traps + flat false-rejection rate on goods (both target 20–40%)
  + flat-vs-RRD discordant pairs (target ≥15).
- baseline `build_prompt` vs variant `build_prompt_rrd`; everything else held (same model, parser,
  cases, FAIR_MAX_TOKENS=2000 — the truncation lesson).
- instances: the new hard suite, filtered through `adversarial_loop.py` (kept_confirmed only:
  gold-confirmed AND flat-verifier-wrong AND objective_fact present), ≥40% goods, ≥80% objective.
- decision: `run_experiment.decide(..., min_discordant=5)` → PACE ACCEPT only.
- predicted: flat 60–80%, RRD higher on H1/H2/H4 traps + H6 goods → ACCEPT.
- KILL: flat still >90% on both arms → cases too easy, regenerate (do NOT run the A/B). flat <50%
  → too hard for defensible gold, stop. PACE REJECT with discordant≥15 → RRD genuinely doesn't
  help even on hard cases → refute the RRD hypothesis, pivot to C9 (criteria-explicit rubric).

## Implementation sequence (for Oga)
1. Generate ~100–120 candidates (patterns P1–P7 in this dossier; each with `objective_fact`,
   no answer-leakage). No API.
2. Calibration: run the FLAT arm alone → keep where flat is WRONG; target 60–80% flat accuracy.
3. `adversarial_loop.py --live` → keep_confirmed only (~15–20% yield → 2 rounds ≈ 36–50 cases).
4. Balance to ≥40% goods.
5. `ab_rrd.py --live` on the hard suite (FAIR_MAX_TOKENS=2000). Report flat accuracy FIRST (did
   the suite hit the discrimination band?), then the PACE verdict.
6. Human: ACCEPT → diff-review RRD into verifier.md. REJECT@discordant≥15 → refute RRD, try C9.

Triage: tactics H1–H7 all IMPLEMENTABLE_NOW; IRT discrimination filter TESTABLE; SEAL/FLAMe
RESEARCH_ONLY. Full pattern JSON templates (P1–P7) are in the sub-agent transcript; reproduce on
build. Nothing adopts into the critical path without a passed PACE experiment.
