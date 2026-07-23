# Acceptance & Verification — implementation notes

*How to make the loop's accept/verify steps statistically honest. Four mechanisms, each with the source paper, whether a repo exists, the real libraries to use, a minimal recipe, and a build-vs-buy call. All repos below were verified against their live GitHub/CRAN pages (June 2026). Papers verified against their arXiv abstract pages.*

The project's throughline is "something must be able to say **no**." These four make the "no" trustworthy at the points where the loop commits, evaluates, retries, and judges.

---

## 1. The acceptor — anytime-valid commit test (PACE)

**Problem.** "Keep the candidate if it scores higher on the reused eval set" is adaptive multiple testing — over many rounds the loop p-hacks itself into committing changes that aren't real improvements.

**Source.** PACE — *Anytime-Valid Acceptance Tests for Self-Evolving Agents*, [arXiv 2606.08106](https://arxiv.org/abs/2606.08106). **No public code** (verified — no link on the arXiv page, none found on GitHub). It's a method to reimplement; the math is standard safe-anytime-valid inference (SAVI).

**Libraries (use as primitives / references):**
| Library | Gives you | Lang | License | Maturity |
|---|---|---|---|---|
| [`expectation`](https://github.com/jakorostami/expectation) | e-values, e-processes, testing-by-betting | Python (+Rust) | GPL-3.0 | pre-release, ~87★ |
| [`confseq`](https://github.com/gostevehoward/confseq) | confidence sequences, always-valid p-values, betting CS | C++/Python | MIT | canonical (Howard/Ramdas) but stale (2023) |
| [`safestats`](https://cran.r-project.org/web/packages/safestats/) | safe (e-value) t/contingency/z tests | R | GPL | mature (Grünwald/CWI) |
| [`onlineFDR`](https://github.com/dsrobertson/onlineFDR) | online FDR/FWER over a *stream* of tests (LORD/SAFFRON/ADDIS) | R | Artistic-2.0 | maintained (Bioconductor) |

**Minimal recipe — paired testing-by-betting acceptance gate (~15 lines):**
```python
# Accept candidate over incumbent only if significantly better, with
# anytime-valid control of false-accept prob <= alpha (peek as often as you like).
E = 1.0                                 # betting wealth (test martingale, starts at 1)
threshold = 1.0 / alpha                 # alpha=0.05 -> 20
for x in shared_instances:              # SAME instances for both (paired)
    s_inc, s_cand = score_incumbent(x), score_candidate(x)
    if s_cand == s_inc:                 # discard ties
        continue
    w = 1 if s_cand > s_inc else 0      # candidate wins this discordant pair?
    E *= (1 + lam * (2*w - 1))          # lam=0.1; wealth up on win, down on loss
    if E >= threshold:
        return ACCEPT                    # commit; guarantee holds at this stop time
    if budget_exhausted():
        return REJECT                    # fail-safe default = keep incumbent
return REJECT
```
**Guarantee (Ville's inequality):** under H0 "candidate no better," `E` is a non-negative supermartingale from 1, so `P(E ever ≥ 1/α) ≤ α` — at *every* stopping time. That is what defeats dev-set p-hacking. Harden by requiring a minimum number of discordant pairs before ACCEPT, and consider a mixture/ONS bet instead of a fixed `λ` to avoid tuning.

**Build vs buy.** *Build the gate (no repo exists), borrow the primitives.* The loop is ~15 lines; validate your wealth update against `expectation`/`confseq`. Once the loop runs many accept-tests over a campaign, add `onlineFDR` (or feed your e-values to an e-value online-FDR procedure) to bound the *cumulative* false-commit rate.

**Where it wires in:** Phase 1 (`run_evals.py` accept logic + `loop_stop_guard.py` gate), Phase 4 ("keep the best"), Phase 5 (self-edit "net improvement"). **Highest-leverage single addition** — it is the literal "something that can say no" at the commit step.

---

## 2. The judge-collapse guard (EPC)

**Problem.** When the loop's evaluator is an LLM judging its own candidates, its preference can collapse onto one strategy; cross-model judges amplify it; verifiable signals largely prevent it.

**Source.** *Multimodal Evaluator Preference Collapse: Cross-Modal Contagion in Self-Evolving Agents*, [arXiv 2606.16682](https://arxiv.org/abs/2606.16682). **Has a repo:** [`aidless/mm-epc`](https://github.com/aidless/mm-epc) (MIT) — a reproducibility artifact (~0★, single author), not a library. **Correction:** the paper has **no metric called "PCI"** — it quantifies collapse as raw weight concentration (one strategy absorbed 48.4%), Jensen-Shannon divergence between per-modality strategy distributions, contagion coefficients, and Cohen's d.

**Judge/jury libraries:**
| Library | Mitigation | License | Maturity |
|---|---|---|---|
| [`inspect_ai`](https://github.com/UKGovernmentBEIS/inspect_ai) | multiple scorers, ensembles, `epochs` repeats, bootstrap CIs | MIT | mature (UK AISI) |
| [`promptfoo`](https://github.com/promptfoo/promptfoo) | multi-judge voting, order-swap, CI-native | MIT | mature |
| [`deepeval`](https://github.com/confident-ai/deepeval) | G-Eval rubric judge, swappable judge families | Apache-2.0 | mature |
| [`judges`](https://github.com/quotient-ai/judges) | PoLL/jury `.vote()` (Replacing Judges with Juries, [2404.18796](https://arxiv.org/abs/2404.18796)) | Apache-2.0 | **archived 2026** — vendor it |
| [RewardBench](https://github.com/allenai/reward-bench) / [JudgeBench](https://github.com/ScalerLab/JudgeBench) | vet/validate a judge before trusting it | Apache-2.0 / MIT | maintained / research |

**Collapse-monitoring metric (implementable; defined here, not from the paper).** Over a sliding window of the last N rounds, with `p_i` = win-share of strategy `i` across K strategies:
```
strategy-win entropy   H_norm = (-Σ p_i log p_i) / log K   ∈ [0,1]   trip if < 0.5
concentration (HHI)    HHI    = Σ p_i²                      ∈ [1/K,1] trip if > 0.5
position-flip rate     (verdict changes when A/B swapped)/rounds      trip if > 0.15
```
HHI maps cleanly onto the paper's "48.4% of weight" framing. Position-flip guards the cross-model amplification risk.

**Guardrail wiring (Phase 4/5 "race methods, keep best"):** (1) prefer verifiable signal — LLM judge only breaks ties among candidates that already passed deterministic checks; (2) PoLL of ≥3 judges from disjoint model families, swap A/B order and average; (3) monitor the three metrics, auto-halt on any trip and fall back to verifiable-only ranking; (4) cap rounds + early-stop on no verifiable improvement.

**Build vs buy.** Buy the harness (`inspect_ai` or `promptfoo`) + the jury pattern (`judges`, vendored); build the ~30 lines of concentration monitoring.

---

## 3. The worker pre-check — should we even enable retry? (EIR/ECR)

**Problem.** Naked self-correction degrades many models; you want to know *before* enabling a retry loop whether it helps for a given worker.

**Source.** *Self-Correction as Feedback Control*, [arXiv 2604.22273](https://arxiv.org/abs/2604.22273). **No public repo.** Build the measurement (it's ~20 lines). Iterate-mechanism repos to borrow: [`madaan/self-refine`](https://github.com/madaan/self-refine) (Apache-2.0), [`noahshinn/reflexion`](https://github.com/noahshinn/reflexion) (MIT). Alternative to retry: self-consistency (sample-and-vote).

**Minimal recipe — measure EIR/ECR on a labeled calibration set:**
```python
# worker(p) -> answer ; correct(a, gold) -> bool ; calib = [(prompt, gold), ...]
n_corr = n_wrong = eir_num = ecr_num = 0
for prompt, gold in calib:
    a1 = worker(prompt)
    a2 = worker(prompt, prior=a1, mode="self_correct")       # one correction pass
    ok1, ok2 = correct(a1, gold), correct(a2, gold)
    if ok1: n_corr  += 1; eir_num += (not ok2)   # right -> wrong (error INTRODUCED)
    else:   n_wrong += 1; ecr_num += ok2          # wrong -> right (error CORRECTED)
EIR = eir_num / max(n_corr, 1)
ECR = ecr_num / max(n_wrong, 1)
acc = n_corr / len(calib)
enable_retry = (ECR / max(EIR, 1e-9) > acc / (1 - acc)) and (EIR <= 0.005)
```
**Rule:** enable retry only if **ECR/EIR > Acc/(1−Acc)** *and* **EIR ≲ 0.5%**. If EIR fails, re-run with a **verify-first** prompt ("first check whether the existing answer is already correct; only change it if you find a concrete error") — the paper shows this suppresses EIR (flipped a −6.2pp model to +0.2pp). Use ~200–500 calibration items; recompute per (model, task, prompt).

**Build vs buy.** Build the ~20-line pre-check (no framework gates retries on a measured EIR/ECR threshold); borrow the iterate loop from self-refine/reflexion and a max-attempts conditional (LangGraph-style) for runtime termination. **Where it wires in:** Phase 2 swap criteria ("prove the swap doesn't regress" → also "prove retry helps this worker").

---

## 4. The judge validator — trust the gate before you use it (MVVP)

**Problem.** Raw exact-match agreement overstates an LLM judge's skill (by 33–41 points vs chance-corrected κ); a judge can be perfectly self-consistent yet badly position-biased.

**Source.** *Reliability without Validity*, [arXiv 2606.19544](https://arxiv.org/abs/2606.19544) — the Minimum Viable Validation Protocol. **No public repo;** assemble from standard libs.

**Tools:** [`inspect_ai`](https://github.com/UKGovernmentBEIS/inspect_ai) (`epochs` gives test-retest free) + κ from [`scikit-learn`](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html) `cohen_kappa_score` / [`statsmodels`](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.fleiss_kappa.html) `fleiss_kappa` / [`krippendorff`](https://pypi.org/project/krippendorff/) / [`irrCAC`](https://pypi.org/project/irrCAC/) (Gwet's AC1). No single tool bundles all three checks.

**MVVP recipe — run before trusting any judge as a gate:**
1. **Chance-corrected agreement:** `kappa = cohen_kappa_score(human, judge)`. Gate on **κ, never exact-match** (expect exact-match to read ~33–41 pp higher — that gap is the inflation). Pass: κ ≥ 0.6 substantial, ≥ 0.8 near-gold.
2. **Position-swap audit (pairwise judges):** judge each pair (A,B) then (B,A); flip rate = fraction where the verdict isn't order-invariant. **Fail if > 0.10.**
3. **Test–retest:** re-judge identical inputs (or Inspect `epochs=N`), compute κ across passes. Target **> 0.95**. (High test-retest does *not* excuse failing the position audit — both must pass: the "consistency–bias paradox.")

**Build vs buy.** Assemble: one harness (`inspect_ai`) + one stats lib (`scikit-learn`/`krippendorff`) + ~30 lines of glue for the swap audit. **Where it wires in:** Phase 1, before any LLM judge is trusted in the suite; re-validate periodically.

---

## Summary — what's a build vs a buy

| Mechanism | Paper | Repo exists? | Verdict |
|---|---|---|---|
| Anytime-valid acceptor | PACE 2606.08106 | no | **build** ~15 lines; primitives `expectation`/`confseq`; `onlineFDR` for campaign FDR |
| Judge-collapse guard | EPC 2606.16682 | yes (`mm-epc`, artifact) | **buy** harness+jury (`inspect_ai`+`judges`); build ~30-line monitor |
| Worker retry pre-check | Feedback-Control 2604.22273 | no | **build** ~20-line calib; borrow iterate loop (self-refine/reflexion) |
| Judge validation (MVVP) | Reliability-without-Validity 2606.19544 | no | **assemble** `inspect_ai` + `scikit-learn`/`krippendorff` + ~30 lines |

The recurring pattern: the *infrastructure* (e-process math, κ, juries, iterate loops) is borrowable, but the *gate logic that says no* is a small, deliberate build — which is exactly where this project already invests.
