# Prior Art — How to Rank Which Candidate to Implement First

*Researcher survey, 2026-06-23. Question: when the radar surfaces candidate tools/techniques/experiments, how do we **rank which to dive into / test / implement first**? Two parallel passes (algorithmic + practical/agentic) under the honesty bar — every source opened and quoted; flags noted. Conclusion drives the priority rubric now in `loop-team/orchestrator.md` and `roles/researcher.md`.*

---

## TL;DR — the recommendation

There is a near-exact precedent in a *self-improving coding agent*: **SICA** ranks the next iteration with an explicit weighted, normalized, capped utility. Wrap that with the **RICE confidence multiplier** (encode the honesty bar: paper vs shipped), **WSJF's phase-fit + risk-reduction** terms, and a **UCB exploration bonus** (don't starve under-tested candidates); gate the *experiment decision* with **value-of-information**; keep **diversity** (GEPA/MAP-Elites — don't collapse to the single #1). The ranking orders the dive-in queue; the existing experiment + PACE gate makes the actual adoption call.

The five recurring principles (both passes converged):
1. **Effect ÷ cost is the backbone** — rank by benefit-per-unit-cost, never raw benefit.
2. **Discount by confidence/maturity as a multiplier** — where the honesty bar (paper-only vs shipped repo) enters the score.
3. **Triage cheaply, then gate the expensive test** — ranking and adoption are deliberately separate stages.
4. **Rank against an archive and protect diversity** — don't collapse to the top scorer (GEPA's ablation proves greedy-#1 hits a local optimum).
5. **Phase-fit + risk-reduction + ignore sunk cost**; value the information when deciding whether to test.

---

## A. The closest precedents (self-improving / agentic systems)

**SICA — Self-Improving Coding Agent** · [arXiv 2504.15228](https://arxiv.org/abs/2504.15228) · NeurIPS 2025 preprint, code `MaximeRobeyns/self_improving_coding_agent`.
The strongest match — an agent that edits its own code, ranking the next iteration with an explicit utility:
> `U = w_score·p_score + w_cost·(1 − min(1, p_cost/$10)) + w_time·(1 − min(1, p_time/300s))`, with `w_score=0.5, w_cost=0.25, w_time=0.25`, hard caps, and a timeout penalty `τ=0.5`. *"this numerical score is only used to pick the next meta agent, as well as the base agent for the next iteration."*
Ranking rule: weighted, normalized, capped blend of benchmark-effect + cost-cheapness + speed. **Directly portable to the radar.**

**AgentSquare** · [arXiv 2410.06153](https://arxiv.org/abs/2410.06153) · code `tsinghua-fib-lab/AgentSquare`.
> *"we further introduce a performance predictor that implements an in-context surrogate model for newly proposed LLM agents, enabling us to skip unpromising candidates and significantly accelerate the search process."*
Ranking rule: predict each candidate's effect with a cheap LLM surrogate; spend real test budget only on the top predictions. **The two-stage (predict → gate the expensive test) pattern.**

**The AI Scientist** (Sakana) · [arXiv 2408.06292](https://arxiv.org/abs/2408.06292) · `SakanaAI/AI-Scientist`.
Scores each candidate idea on **Interestingness + Feasibility + Novelty (1–10)**, hard-checks novelty against the literature (Semantic Scholar), then gates execution with an automated LLM reviewer (Accept/Reject). *Flag: exact 1–10 rubric prompt is in code not opened; three criteria confirmed from README + abstract.* Maps to: an LLM rubric over radar candidates + a "have we already built this?" novelty/dedupe check + a downstream gate.

**Darwin-Gödel Machine** · [arXiv 2505.22954](https://arxiv.org/abs/2505.22954), App. A.2 · reference impl [`jennyzzt/dgm`](https://github.com/jennyzzt/dgm) `DGM_outer.py` (verified in source).
Parent selection: `s = sigmoid(λ(perf−α₀))`, novelty `h = 1/(1+#children)`, weight `w = s·h`, sample parent ∝ `w`. *"favors agents with high performance and fewer existing children, thereby promoting both exploitation and exploration."* λ=10, α₀=0.5 — confirmed VERBATIM in the reference implementation (`DGM_outer.py`, `choose_selfimproves`): `scores = [1/(1+math.exp(-10*(score-0.5))) for score in scores]`; `children_counts = [1/(1+count) for count in children_counts]`; `random.choices(commits, [s*c for s,c in zip(...)], k=...)`. (The arXiv appendix renders the equation as truncated HTML — the code is the openable, quotable source.)
Ranking rule: pick which past success to expand ∝ `sigmoid(performance) × 1/(1+#times-already-mined)`.

**ADAS / Meta Agent Search** · [arXiv 2408.08435](https://arxiv.org/abs/2408.08435) · `ShengranHu/ADAS`.
Keeps an archive of evaluated agents; the meta-agent proposes the next candidate it judges most "interesting" given prior measured results. *No closed-form score for what to try next — qualitative, conditioned on the archive.* Maps to: rank relative to an archive of what's already been tried, not in a vacuum.

**AlphaEvolve / OpenEvolve** · DeepMind white paper · `algorithmicsuperintelligence/openevolve` (README).
> *"the evolutionary database implements an algorithm that is inspired by a combination of the MAP elites algorithm and island-based population models."* Sample a parent to evolve + diverse "inspiration" set (always including the current best). *Flag: exact exploit/explore split is in code/appendix, not the opened body.*
Maps to: combine exploit (resurface the best) + diversity (varied elites) when generating the next candidate.

---

## B. Formal selection rules (bandits / Bayesian optimization / racing)

**Bayesian-optimization acquisition functions** (Frazier tutorial [arXiv 1807.02811](https://arxiv.org/abs/1807.02811); GP-UCB [arXiv 0912.3995](https://arxiv.org/abs/0912.3995); Shahriari et al. 2016):
- **Expected Improvement**: `argmax E[max(f(x) − f*, 0)]` — expected amount it beats current best (rises with both gap and uncertainty).
- **GP-UCB**: `argmax μ(x) + √β·σ(x)` — *"prefers both points where f is uncertain (large σ) and where we expect high reward (large μ)."* The explicit, tunable exploration knob. **The single most defensible radar score: effect + β·uncertainty.**
- **Probability of Improvement**: `argmax Φ((μ−τ)/σ)` — probability of beating incumbent (exploitation-heavy; ignores magnitude).
- **Thompson Sampling**: draw one effect from each candidate's posterior, pick the argmax — self-balances explore/exploit, parallelizes well.

**Multi-armed bandits**:
- **UCB1** (Auer et al. 2002): `argmax x̄ⱼ + √(2 ln n / nⱼ)` — mean reward + bonus that grows for arms tried fewer times.
- **Knowledge Gradient / Value-of-Information** (Frazier §4.2): `argmax E[improvement in best posterior mean after one more measurement]` — *value the information*; can favor testing a candidate that won't itself win because the result sharpens the decision. Cost-aware variants (KG-per-cost) exist.

**Race-and-prune** (Successive Halving; Hyperband [arXiv 1603.06560](https://arxiv.org/abs/1603.06560); ASHA [arXiv 1810.05934](https://arxiv.org/abs/1810.05934)):
> SHA: *"evaluate all configurations, throw out the worst half, and repeat."* ASHA: *"promotes configurations to the next rung whenever possible instead of waiting."*
Pattern: cheap trial for all candidates, promote the top 1/η to a deeper test, kill losers early. ASHA's asynchronous "promote the moment it's top-1/η" is the practical pattern for **parallel dives**.

**Quality-diversity / Pareto** (don't collapse to one winner):
- **MAP-Elites** ([arXiv 1504.04909](https://arxiv.org/abs/1504.04909)): grid of niches; keep the single best per cell; a candidate is kept iff it beats its cell's elite.
- **FunSearch** (Nature 2024): independent islands + score-and-length-weighted sampling + periodic worst-island reset.
- **GEPA** ([arXiv 2507.19457](https://arxiv.org/abs/2507.19457)): keep candidates best on ≥1 task (per-instance Pareto front); sample ∝ #tasks led. **Ablation: always picking the single best collapses to a local optimum (+6 pts for Pareto sampling) — the load-bearing evidence for diversity.**

---

## C. Practical product/research rubrics

- **RICE** (Intercom, canonical): `(Reach × Impact × Confidence) ÷ Effort` — *"total impact per time worked."* The **Confidence multiplier** exists to demote high-claimed-effect, low-evidence ideas → our maturity/honesty term.
- **ICE** (Sean Ellis): `Impact × Confidence × Ease` — lighter, fast triage of the raw feed.
- **WSJF** (SAFe): `Cost of Delay ÷ Job Size`, CoD = value + **time-criticality** + **risk-reduction/opportunity-enablement**. Adds the two terms RICE/ICE lack (phase-fit + de-risking); explicitly ignores sunk cost.
- **Value of Information / EVSI** (decision theory): run the experiment with highest `ENBS = EVSI − cost`. The principled answer to *"is this test worth running"* — values reducing uncertainty, so a high-uncertainty/high-stakes candidate can outrank a high-confidence one with little left to learn.

---

## The rubric we adopted (see orchestrator.md → "Prioritizing radar candidates")

A SICA-shaped weighted score per candidate, all sub-terms normalized to 0–1:

```
priority = w_eff·(effect × confidence)      # RICE: effect discounted by maturity/evidence
         + w_phase·phase_fit                # WSJF time-criticality (current/next phase = 1)
         + w_risk·risk_reduction            # WSJF: de-risks the roadmap
         + w_explore·uncertainty            # UCB/Thompson exploration bonus (under-tested → higher)
         − w_cost·cost_to_test              # SICA/RICE: benefit per unit cost
```
Defaults: `w_eff 0.40 · w_phase 0.20 · w_risk 0.15 · w_explore 0.10 · w_cost 0.15`.

Plus three structural rules from the prior art:
- **Decay interrupt**: any ADOPTED/CANDIDATE tool flagged DECAYING jumps the queue — it's risk, not opportunity (skip the score).
- **Diversity**: pick the top candidate **per active-phase bucket**, not the global top-N (MAP-Elites/GEPA); use probabilistic, not greedy, selection so nothing is permanently starved.
- **Two-stage gate**: `priority` only orders the **dive-in queue**; whether to actually run a given experiment is a value-of-information check (`expected decision-improvement > test cost`), and adoption is decided by the existing **PACE gate** + human diff-review — never by the score alone.

---

## Flags / not fully opened
- UCB1's exact formula is a figure-image in the 2002 paper (quoted equivalent prose + proof term).
- SHA mechanism quoted from Hyperband/ASHA restatements (PMLR page rendered abstract only).
- AlphaEvolve's specific exploit/explore probabilities and OpenEvolve's exact parent-selection formula live in appendix/code not opened — documented heuristics reported only.
- The AI Scientist's exact 1–10 rubric prompt is in code not opened; criteria confirmed from README + abstract. Independent eval arXiv 2502.14297 surfaced via search only (secondary corroboration).
