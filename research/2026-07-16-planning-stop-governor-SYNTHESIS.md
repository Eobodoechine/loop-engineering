# Planning-Stop Governor — Research Synthesis

**Date:** 2026-07-16
**Question:** Should we build a planning-continuation governor (`planning_decision.py` / `EXPECTED_PLAN_CHANGE`) to stop the loop turning certification into the deliverable?
**Answer: NO. Five independent lines of evidence converge on a different fix.**

## Source dossiers

| Leg | File |
|---|---|
| Internal grounding + red-team | `2026-07-16-planning-stop-governor-internal-grounding-redteam.md` |
| Formal theory (metareasoning) | `2026-07-16-rational-metareasoning-stopping-theory.md` |
| LLM overthinking evidence | `2026-07-16-llm-overthinking-deliberation-stopping-evidence.md` |
| Shipped-framework prior art | `2026-07-16-agent-framework-termination-prior-art.md` |
| Defect-discovery saturation | `2026-07-16-defect-discovery-saturation-scope-freeze.md` |

---

## 1. The verdict: DO NOT BUILD as proposed

Five independent kills. Each is sufficient alone.

1. **Already forbidden by name.** `fix_plan.md:4353` — *"any naive 'stop after N rounds of a repeated pattern' rule risks silently cutting off exactly the findings this adversarial process most exists to catch, unless the stop condition is explicitly guarded by a zero-new-finding clause."* The proposal has no such clause.
2. **Reinstates a revoked rule.** `orchestrator.md:76` — *"No exception based on Oga's own assessment of triviality, urgency, or risk determines WHETHER a Verifier dispatch happens — only HOW MUCH scrutiny it gets."* Revoked because Oga's own judgment was "directly, adversarially wrong twice in one session."
3. **Pre-registered as an automatic kill.** `plancheck-nonbinding-saturation-2026-07-09.md:390` — a stop signal firing on the round-19-21 or round-30/31 airbnb instances is "an automatic kill, regardless of what the aggregate says." The proposal fires ~10 rounds early.
4. **Formally known-broken.** It is the meta-greedy algorithm under the single-step assumption. Russell & Wefald killed it in the founding paper (IJCAI-89): *"untenable in general"*; *"the single-step assumption will predict that certain search steps can have no value, whereas often those steps enable other steps to become valuable."*
5. **Empirically refuted on our own logs.** The precondition for any myopic stop rule is diminishing returns (Hansen & Zilberstein, Corollary 1). Measured across 59 `plan_check_log.md` files, the hazard is **flat**, not decaying.

### The backtest: 15 : 0

Fifteen recorded cases where a round ≥3 or an added lens found a real named defect. Zero cases of a late round producing only noise.

### The measured hazard (59 logs)

| round k | 1 | 2 | **3** | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| h(k) | 0.81 | 0.67 | **0.84** | 0.73 | 0.60 | 0.50 |
| n at risk | 52 | 33 | 19 | 11 | 5 | 2 |

After two consecutive failed rounds, round 3 finds another defect **84%** of the time.

*Caveat (flagged by the researcher):* selection bias inflates the **level** (`Pr(defect | round was run)`), but the claim rests on **flatness in k**, which the bias would have to be constant in k to explain away.

### Why the rule is structurally self-defeating

Its guarantee covers the wrong direction. Hay et al. **Theorem 7**: myopic-says-compute ⟹ optimal-says-compute; **the converse is false**. That yields a **zero false-continue rate and an unbounded false-stop rate** — the guarantee covers the behavior we are not trying to control, and the failure lands entirely on the one we are.

Two independent derivations of the same defect:
- **From history:** the rule asks Oga to name a finding it has not yet made — impossible for unknown-unknowns, which is what late rounds catch.
- **From theory:** Heckerman/Horvitz/Middleton (UAI-91) — *"Because the myopic procedure allows for the gathering of additional evidence, the procedure is inconsistent with its own assumptions."*

**Corollary: the test's sensitivity is anti-correlated with need.** If the orchestrator could name the finding, it would already be fixed.

**It degrades as artifacts grow** (R&W §8, measured): *"the single-step assumption eventually begins to bar almost all nodes from being expanded as the tree grows larger."* Any pilot on small specs produces a false positive.

---

## 2. The real diagnosis: a ratchet, not excess rounds

The mechanism behind 1,452 lines / 107 criteria, assembled from three dossiers:

1. **The reviewer has an intrinsic false-positive floor.** CriticGPT (OpenAI): *"models which hallucinate bugs more often are also more likely to catch human inserted and previously detected bugs."* Recall and hallucination are **coupled on a Pareto curve** — not separately tunable. Their own limitation: the absolute rate *"is still quite high."*
2. **This is not an LLM artifact.** Porter/Siy/Toman/Votta (IEEE TSE 1997), human reviewers: ~50% outright false positives, 35–40% style/maintenance — ***"only 13 percent concern defects that will compromise the functionality of the delivered system."*** **87% of raw review findings are not real defects.**
3. **The plan-holder capitulates rather than defends.** Sharma et al. (Anthropic): Claude 1.3 *"wrongly admits mistakes on 98% of questions"* — **holding even when highly confident.** (2023-era model; direction replicates, magnitude is dated.)
4. **Capitulation ADDS a criterion. Nothing ever REMOVES one.**
5. **A longer plan is more surface for the next objection.** Repeat.

**1,452 lines is this loop's fixed point, not an anomaly.**

### The premise that was wrong

"The plan got long, therefore length hurt us" is a confusion s1 explicitly diagnoses: *"shorter generations tend to be the ones where the model was on the right track from the start."* **Length is a symptom of being lost, not a cause.**

The paper titled *"The Danger of Overthinking"* reports the **opposite** of its popular reading: o1 at **high** reasoning effort has a **lower** overthinking score (2.426 vs 2.774) **and** scores better (29.1% vs 21.0%). Authors: *"having more reasoning tokens can effectively curb overthinking."*

### The multi-lens illusion

Kohli (arXiv:2605.29800), 9 frontier LLMs across **7 different families**: φ̄ = 0.391, **n_eff = 2.18**, independence ratio **24.2%**. *"the best single judge matches or outperforms the full panel across all conditions."*

**N lenses do not give N looks. They give ~2.** Lenses sharing a base model are worse than this 7-family measurement.

---

## 3. Why no statistical stop rule can work here

### Capture-recapture: the ceiling is below the floor

- **Estimator:** Mh-JK — `N̂ = D + ((k−1)/k)·f₁`, residual = `((k−1)/k)·f₁`, where f₁ = findings exactly one lens found.
- **Direction of failure:** Chao et al. (Stat. Med. 2001) — *"Petersen's estimator **underestimates** the true size if both samples are positively dependent... a negative bias exists for **any** estimator which assumes independence."* **It fails toward premature STOP** — the exact failure we are trying to prevent.
- **The kill shot:** Kish ceiling = `1/φ̄` = **2.56** effective lenses. Validity requires **≥4** (Briand: *"below 4, no model is sufficiently accurate"*), **>5** per Otis/Chao. **2.56 < 4 ⇒ no lens count ever reaches validity.** (Verified: 1/0.391 = 2.558.)

> ⚠️ **CONTESTED — added 2026-07-16 after the PACE power analysis.** This kill rests on **φ̄ = 0.391 borrowed from Kohli** (different task, 7 model families). **Our own corpus measures cross-lens overlap = 0** (2,491 pairs, 0 merges). Those are in **direct tension**: if our overlap is genuinely 0, our lenses are independent, the Kish ceiling does not apply, and this kill is **overturned**. We cannot currently tell which is right, because the instrument that would measure our φ̄ has a ~100% false-negative rate (see §8). **Do not treat §3 as settled.** The Phase-1 duplicate-labelling test resolves it.
- **Gameable:** f₁ is directly manipulable — pad unique findings → "keep going"; copy → "stop".
- **The inventor's own field verdict:** Lawrence Votta co-authored Eick et al. 1992, *which invented capture-recapture for inspections*. In the 1997 field experiment he wrote: ***"our attempts to use statistical methods to estimate the original defect content were unsuccessful."***

**This generalizes beyond capture-recapture.** The Kish-ceiling arithmetic is a general result about **any aggregation over correlated LLM lenses**.

### Sole surviving statistical candidate

**Goel-Okumoto** `a(1−e^(−bt))` — the only residual estimator found that does **not** assume inter-lens independence (`a` = total defects). Its own assumption (perfect/immediate debugging) is suspect for a *static* artifact. **Musa-Okumoto is the wrong model** — infinite-failure, no asymptote, yields no residual estimate.

---

## 4. What shipped frameworks actually do

Surveyed 14 systems from raw source. The regularity holds **without exception**:

> **Semantic signals REDIRECT. Only counters and cost caps TERMINATE.**

No shipped framework lets a model's judgment about its own progress **end a run**.

- **Magentic-One:** `is_progress_being_made=False` → increments `stall_count` → `_reset_and_replan()`. Only `max_round_count`/`max_reset_count` terminate.
- **SWE-agent:** the value-based `ScoreRetryLoop` ships in code, used by **zero** configs. Model judgment runs only at the **end**, to *select*, never to stop.
- **CrewAI:** repeat-detection injects feedback as the tool result; `max_iter` forces a final answer. Both redirects.

**The asymmetry:** the only semantic signal trusted to terminate is `is_request_satisfied` — the **success** direction. **Nobody trusts a model in the give-up direction.**

**Two independent reasons, both attested:** (a) gameability; (b) **noise** — both frameworks that shipped a value signal built expensive de-noising around it (SWE-agent samples its reviewer **5×** and subtracts `std * reduce_by_std`; Magentic-One uses a leaky bucket that *decrements on progress*, `max(0, n-1)`). Counters need none of that.

**The trust gradient:** saturation advice lives only in the **prompt layer** (`open_deep_research/prompts.py:170-173`, under a heading literally called "Hard Limits": *"Stop Immediately When: … Your last 2 searches returned similar information"* — **nothing measures it**). Every actually-enforced bound lives in code the model cannot reach.

**Defaults span 10 → ∞** (LangGraph 25 · OpenAI SDK 10 · CrewAI 25 · AG2 100 · OpenHands 500 · SWE-agent $3.00 · Swarm `inf` · Auto-GPT `math.inf`). **Nobody derives their number.** Don't agonize over the constant.

**Two findings not asked for:**
- **AutoGen is in maintenance mode.** Its successor **deleted** the 11-condition termination taxonomy, keeping `max_rounds` + a bare callable. Given a clean sheet, Microsoft did *not* add semantic stops.
- **Auto-GPT demoted its counter to Ctrl+C handling** and moved governance to a **permission manager** (per-action human approval). The field's worst runaway concluded the fix wasn't a better counter — it was **authority**.

---

## 5. The convergence

Five legs, no shared path, same answer.

| Finding | Legs agreeing |
|---|---|
| **Change the ORACLE, not the round count** | all 5 |
| **Persistent yield ⇒ rewrite the artifact, don't review harder** | red-team (TaxAhead 782→97), defect (Petersson A1), overthinking (Huang §5) |
| **The rule is anti-correlated with need** | red-team (from history), theory (from Heckerman) |
| **A prompt-layer governor fails silently** | framework (trust gradient), theory (instructional guarantee) |
| **Add detector KIND, not detector COUNT** | defect (Porter/Chao/Kohli), red-team (Nnamdi's own round-31 diagnosis), overthinking (execution grounding) |

### The oracle result

Huang et al. (ICLR 2024) isolates the variable — same loop, same benchmark:
- **With** an oracle stop signal: 75.9 → **84.3**
- **Without** one: 75.9 → **74.7**

**The oracle does all the work.** Absent it, GPT-4 goes 95.5 → 91.5 → 89.0 across two review rounds.

Nnamdi reached this independently at airbnb round 31: *"we were hand-simulating a compiler."* His diagnosis was **wrong-oracle routing**, not excess rounds. Grounding the loop in execution is the largest single effect in the entire corpus: **29.1% → 47.7%, while simultaneously cutting overthinking 2.43 → 1.05.**

### The most uncomfortable result

Huang §5: adding **one clarifying line to the initial prompt** moved the baseline 53.0 → **81.8**. The refinement loop then dragged it **down to 75.1**. Self-Refine's entire published gain was an artifact of an under-specified initial prompt.

**A 107-criteria review apparatus is itself evidence the brief was under-specified. The fix is the brief, not the loop.**

### Economics, not epistemics

Reinertsen: **a loop that never stops has implicitly set its cost of delay to zero.**

The theory leg found the same hole independently: the proposal's `Q^m(s,E) = E[−c + max_i μ_i(S_1)]` has three ingredients, and the proposal **omitted the cost term `c` entirely** while keeping the damaging single-step assumption. Two literatures, one missing variable.

---

## 6. Recommendations (ranked)

1. **Make cost of delay explicit and non-zero.** Probably resolves the symptom alone. Fixes the objective, not the estimator.
2. **Persistent yield ⇒ A1 (rewrite the artifact), never A3 (review harder).** Petersson: persistent yield means *"the artefact was not really ready for inspection."* In the literature a plan that keeps yielding defects is a **rejected** plan, not an under-reviewed one. Precedent: TaxAhead 782→97 lines, then re-verify the **smaller** artifact. The review never stopped; it got cheaper because the artifact shrank.
   - **Guard:** a rewrite must never suppress a round. `H-SPEC-REWRITE-DIFF-1` — a rewrite silently dropped a whole design section, caught only by round 3.
3. **Spend budget on KIND-diversity, not count.** 1 LLM lens + 1 **mechanical** detector (tests/types/schema/compiler) > N LLM lenses. Chao: *"the CCV is zero if the capture probabilities for one sample are constant"* — a mechanical detector has flat detection probability and **kills the correlation bias**. Porter: *"significant improvements... will depend on the development of new defect detection techniques"*, not process reorganization.
4. **k=2 lenses of different kind, one pass, freeze.** Porter/Votta 1997 (18-month randomized industrial experiment, 1/2/4 reviewers): *"no difference in the interval or effectiveness of inspections of two- or four-person teams."* **The plateau is at 2, not 4** — the "2–4 reviewers" folklore misstates a result saying 4 is no better than 2.
5. **Fix the quantifier if the rule is kept at all** (~free, converts unsound → sound). Not *"would one finding change the plan?"* but *"is there **any reachable state** in which a finding would change the plan?"* — Hay Thm 9 / H&Z Thm 1 cond. 2.
6. **Ship the BEST snapshot, never the last.** Without selection, **38%** of correct work is destroyed by the refinement loop.
7. **Build the finding-identity function** — **PROMOTED 2026-07-16 from "gap in prior art" to "live, measured bug in our own harness."** `reconcile_gap_records.py:65` sets `CLUSTER_SIMILARITY_THRESHOLD = 0.85` over char-level `SequenceMatcher.ratio()` on free prose. **Measured: 2,491 cross-lens pairs, max similarity 0.338, ZERO merges (0.000%).** A confirmed true duplicate (two lenses, same contradiction, 3 shared `touches`) scored **0.338** — under half the threshold. So `f₁ = 613/613 = 100%` is a **structural artifact of a detector that never fires**, not a property of the lenses.
   - **This is the ratchet's mechanical cause.** When lens B re-finds lens A's defect in different words, the reconciler scores 0.338, rules it novel, and **adds it**. The plan grows because a string comparison cannot distinguish paraphrase from novelty. Not judgment failure — `difflib` on prose.
   - Prior art confirms the shape: OpenHands' StuckDetector requires **exact** content equality (`thought == thought`). Normalized **claim** identity (not normalized text) is unsolved by every framework surveyed — and it is exactly what `fix_plan.md:4353`'s mandatory zero-new-finding clause needs to become mechanically computable beyond the compiler-catchable class.
8. **If anyone insists on a number: measure φ̄.** Per El Emam's RDA, **any stop rule must beat the *default* policy**, not merely be "principled."
   - ⚠️ **CORRECTED 2026-07-16 — this is NOT independent of #7, as originally written.** **φ̄ is unmeasurable today**: the only instrument that could measure our cross-lens overlap is the reconciler, and it has a ~100% false-negative rate. **#8 is sequentially dependent on #7.** The original text ("measure φ̄ first — it's cheap and decisive") was wrong on both counts: it is not first, and it is not currently possible.

### Tamper-proofing constraint (binding on anything built)

Every code-enforced bound in the surveyed field lives in a **loop the model cannot reach** — that is *why* they hold. A governor written into `orchestrator.md` sits in the **prompt layer**, exactly where the field puts advice and nowhere near where it puts bounds it needs to hold. **The failure is silent and load-bearing:** an orchestrator ignoring a prompt-level stop doesn't raise or log — it dispatches another review, indistinguishable from real work.

Requires a **hook + durable on-disk counter outside the orchestrator's context**.

**Failure behavior:** "throw" is wrong for us — it discards every review finding. Copy CrewAI's forced-verdict + OpenHands' `STUCK` as a terminal state distinct from `ERROR`.

### Recommended shape, if a bound is built

Magentic-One's **three-tier** structure — semantic signal → leaky-bucket integrator (`max(0, n-1)` decrement) → hard counter holding **sole terminal authority**. It survived a ground-up framework rewrite unchanged.

---

## 7. Mis-citation audit — 3 of 4 folklore numbers are corrupt

Traced to primary sources. **Do not cite these:**

- **"200–400 LOC/hour"** → **MIS-CITED.** The Cisco study *quotes it as folklore* (*"Industry experts say..."*). Its own measured numbers: reviewers slower than **400** LOC/hr were above average; faster than **450** LOC/hr, defect density is below average in **87%** of cases.
- **"60-minute effectiveness collapse"** → **UNVERIFIED.** Asserted as *"well-established fact"*, footnoted to another essay in the same book. Never measured. The famous "300–400 LOC" is a downstream inference from this unverified premise.
- **"70–90% defect discovery"** → **MIS-ATTRIBUTED.** SmartBear's marketing credits it to the Cisco study; **the claim is absent from that study**, which never establishes a total-defect denominator. Real numbers: **32 defects/kLOC, 61% of reviews found nothing.**
- **"Analysis paralysis"** → **empirically hollow.** Its basis (choice overload) fails meta-analysis: Scheibehenne et al. (JCR 2010), 63 conditions, N=5,036 — *"a mean effect size of virtually zero."*

---

## 7b. PACE testability — ADDED 2026-07-16

Full analysis: `2026-07-16-pace-testability-power-analysis.md`.

**None of the recommendations are PACE-testable as backtests.** Real counts:

| candidate | verdict | n |
|---|---|---|
| Oracle routing | **NOT-BACKTESTABLE** — oracle undefined | 9 BINDING / 1,053 |
| Kind-diversity | **NEEDS LIVE PILOT** | **0** |
| Artifact-size cap | **WRONG INSTRUMENT** (regression, not paired) | 48 |
| Persistent-yield → rewrite | **UNDERPOWERED** (n=1, need 8) | **1** |

- **Oracle routing has no oracle.** `gap_type` is 93.4% the single value `DESIGN`, free-text, no controlled vocabulary (`[LOGIC]` and `LOGIC` coexist in the same field). But tagging isn't the real problem: **100% of 398 `source_file` values are `.md`** — there is no code at plan-check time, so "would a compiler have caught this?" is **undefined, not merely hard**. All 9 BINDING records are *absence-of-specification* ("no base64 escape supplied") — a class a compiler cannot catch by definition.
- **The corpus is conditioned on `incumbent_found=1`**, so every pair is `(1,0)` → guaranteed REJECT, zero information. **You cannot measure a candidate's recall advantage from a sample of the incumbent's successes.**
- **The stop-rule test is MIS-SPECIFIED, not underpowered — no n rescues it.** Under recall scoring every pair is discordant by construction, so `W = (1−h)·n` exactly: **the statistic is an algebraic re-encoding of h(3)**, already on disk. And the round/defect exchange rate is **set by fiat in the scoring rule — PACE cannot discover it, it is an input.**

**`min_discordant=5` is dead code.** At `alpha=0.05`, `lam=0.5` (the default), all-wins wealth is `1.5^D`; `1.5^7 = 17.09 < 20 ≤ 25.63 = 1.5^8`. **No ACCEPT is possible before D=8**, at any win rate. Asymptotic win rate required: **63.09%**. *(Correction to the source dossier, verified independently: its claim that D≥8 holds "at every legal `lam`" is **false** — at `lam=0.9`, D=5 is binding. The claim holds at the default.)*

**Retrospective PACE is order-exploitable.** At round 1 (n=52, W=10) a wins-first sort yields **ACCEPT for a stop rule wrong 81% of the time**; random order accepts 0.000%. Round 3 is order-robust (W=3 < 8), so the verdict stands — but **any backtest requires pre-registered ordering.**

### The one test worth running (Phase 1)

Human same/different labels on a stratified sample of the **927** pairs the reconciler's own `orthogonality_filter` declines to certify independent. Extraction is already done (~0 tokens). **The oracle is objective and decidable — the only real oracle in this entire analysis.**

- true-duplicate rate ≈ 0 → **overturns §3's Kish-ceiling kill** (lenses genuinely independent)
- true-duplicate rate > 0 → **confirms the reconciler is broken** and gives the ratchet its mechanical cause

Phase 2 (PACE) only if Phase 1 lands in the ambiguous middle — n=927 is 116× the floor, but you don't need an anytime-valid test to beat a ~100%-false-negative detector.

## 8. Open items

- **`research_sources_index.py` is broken two ways** — (a) the documented regenerate command omits `--out`, so it silently only prints; (b) `collect_sources()` scans `SOURCES_INDEX.md` itself, re-ingesting its own output each pass (proven on isolated fixtures by two researchers independently; live artifact grew 2 → 6 AlphaZero repetitions). Fix: skip the out-file in `collect_sources()`. **Not yet fixed — must go through the loop.**
- **Concurrent-write incident (2026-07-16):** three parallel researchers wrote `SOURCES_INDEX.md`; last-writer-wins produced a 416/80 uncommitted diff entangled with a prior session's work. **Cause: the read-only constraint was placed on only 1 of 5 dispatches.** Left untouched pending decision.
- **🩸 BLEEDING NOW — free fix.** `.gitignore:40-42` untracks `runs/`, `loop-team/runs/`, and `public/loop-team/runs/`. Round-0 spec size is never recorded and run dirs never enter git, so **historical spec sizes are unrecoverable and every day costs a permanent data point.** Also collapse `gap_type`/`tag`/`tags` to one enum. Neither needs an experiment.
- **The missing measurement:** nobody has measured `Pr(defect exists | orchestrator cannot name one)` — the false-stop rate, the rule's only failure mode per theory. **Shadow-mode is ~free** (log the verdict, run the round anyway, score it) and yields the H&Z performance profile as a byproduct. One experiment, two deliverables.
- **`UNVERIFIED-FULL-TEXT`:** "Using a Reliability Growth Model to Control Software Inspection" (DOI 10.1023/A:1016396232448) — the one paper directly targeting "defects findable by re-inspection." Paywalled. Best follow-up target.
- **`UNVERIFIED`:** Chao Mh closed form `f₁²/(2f₂)` — do not cite.
- **Not researched:** CCB / DoD / DoR; secretary problem (flagged rather than given an ungrounded verdict).
- **Scope limit on all LLM evidence:** every number comes from tasks with a **verifiable answer** (GSM8K, SWE-bench, HumanEval, AIME). *"Is this plan good enough"* has no ground truth, and **no paper measures iterated-review degradation on open-ended planning artifacts.** Flagged as inference: this cuts *against* the loop — planning is the no-oracle condition **by construction**.
- **Dated magnitudes:** Sharma/Huang/Zheng/Madaan numbers are 2023-era models. Directions replicate; magnitudes do not (do not quote 98% as current).
