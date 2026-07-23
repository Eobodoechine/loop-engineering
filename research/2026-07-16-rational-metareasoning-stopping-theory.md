# Rational metareasoning and the stopping problem: what EXPECTED_PLAN_CHANGE actually is, and where it is known to break

**Date:** 2026-07-16
**Mode:** D (domain research for a build)
**Question:** Is `EXPECTED_PLAN_CHANGE` — "before dispatching another round of plan-review, the orchestrator must state the smallest plausible finding that would change the implementation plan; if the only answer is *more confidence*, stop planning and freeze scope" — a sound decision procedure? What is the real theory it instantiates, and what are that theory's **known failure modes**?
**Verdict in one line:** It is the **meta-greedy algorithm under the single-step assumption** (Russell & Wefald, 1989), whose originators wrote in the same paper that it is **"untenable in general"** and that it **"will predict that certain search steps can have no value, whereas often those steps enable other steps to become valuable."** It is sound in the *continue* direction and unsound in the *stop* direction — and stopping is the only direction this proposal is used for.

> **Reading note on epistemic status.** Every claim below is tagged. **[PROVES]** = the cited paper states/proves it and I opened the paper and quoted it. **[SECONDARY]** = a paper I opened attributes it to a source I did not open. **[INFER]** = my reasoning, not a paper's claim. **[MEASURED]** = I computed it from this repo's data; method and caveats given. Full source-provenance table at the end, including what I could **not** open.

---

## 0. TL;DR for the orchestrator

1. **The proposal has a correct kernel and a fatal implementation.** The kernel — "information that cannot change a decision has zero value" — is the central theorem of value-of-information and is *right*. The implementation — "can you name a *single* finding that would flip the plan?" — is the one approximation the entire literature identifies as the standard way to get this wrong.
2. **The error has a name and a proof.** It is the *single-step assumption*. Hay et al. (2012) formalize the resulting myopic policy and prove (Thm 7) a **one-directional** guarantee: myopic-says-compute ⟹ optimal-says-compute. **The converse is not claimed and is false.** So the rule has a **zero false-continue rate and an unbounded false-stop rate.** It can only fail by stopping too early. That is the exact direction you plan to use it in.
3. **Weitzman/Pandora is REFUTED as the model** — but for a sharp and useful reason (§3.6). Weitzman needs *obligatory inspection* (you may only accept a box you opened). Plan-review is *non-obligatory* (you can ship an unreviewed plan). That variant is Doval (2018), and Beyhaghi & Kleinberg (EC 2019) prove it **"cannot be solved optimally by any simple ranking-based policy."** No reservation-value rule is available to you.
4. **The condition that would license the rule is diminishing returns — and this repo violates it.** [MEASURED] Across 59 real `plan_check_log.md` files, the per-round defect hazard is **flat, not decaying**: h(1)=0.81, h(2)=0.67, **h(3)=0.84**, h(4)=0.73. Round 3 is as productive as round 1. Hansen & Zilberstein's Corollary 1 precondition (non-increasing marginal value) fails on the actual process, so their Theorem 1 does not license myopic stopping here.
5. **Do not enforce it. Shadow-run it.** The one number that decides this — Pr(a defect exists | the orchestrator could not name one) — has never been measured and is cheap to measure (§5.4). Log the verdict, run the round anyway, score the false-stop rate.
6. **The cheap sound fix is a two-word edit** (§4.1): replace "would *one more finding* change the plan?" with "is there *any reachable state of this review process* in which a finding would change the plan?" That is Hay et al. Theorem 9 + Hansen & Zilberstein Theorem 1 condition (2), and it converts an unsound rule into a sound one at ~zero cost.

---

## 1. What EXPECTED_PLAN_CHANGE actually IS, in formal terms

### 1.1 The exact formalism

The proposal is an instance of **rational metareasoning** over a **metalevel MDP**, specifically the **meta-greedy algorithm under the single-step assumption** — equivalently, the **myopic policy** π^m.

Three literatures name the same object:

| Name | Source | Verified |
|---|---|---|
| "meta-greedy algorithm" + "single-step assumption" | Russell & Wefald, IJCAI-89, §"Meta-greedy algorithms" / §"Single-step assumption" | [PROVES] full text opened |
| "the myopic policy π^m … known [as] the metalevel greedy approximation with single-step assumption in Russell and Wefald (1991a)" | Hay et al., UAI-12, Definition 6 | [PROVES] full text opened |
| "myopic estimate of the expected value of computation (MEVC)" / "the myopic monitoring approach" | Hansen & Zilberstein, AIJ 126 (2001), Definitions 6–7 | [PROVES] full text opened |
| "a myopic policy" (the naming) | Pearl (1988), per Russell & Wefald: *"These are related to what Pearl [1988] has called a 'myopic policy'."* | [SECONDARY] — R&W's attribution verified; Pearl 1988 not opened |

### 1.2 The metalevel MDP, stated precisely

Hay et al. (2012), **Definition 3** [PROVES] — verbatim structure:

```
S  = {⊥} ∪ {⟨e1,…,en⟩ : ei ∈ Ei, finite n ≥ 0, distinct Ei ∈ E}   (states = sequences of computation outcomes)
s0 = ⟨⟩                                                            (initial state)
As = {⊥} ∪ Es                                                      (actions: stop, or a computation)
T(s, E, s′) = P(E = e | E1=e1, …, En=en)
T(s, ⊥, ⊥)  = 1
R(s, E, s′) = −c                                                   (each computation costs c)
R(s, ⊥, ⊥)  = max_i μi(s)                                          (stopping pays the best action's expected utility)
    where  μi(s) = E[Ui | E1=e1, …, En=en]
```

**Mapping to loop-team:**

| Formal object | Loop-team referent |
|---|---|
| object-level actions `i`, utilities `U_i` | candidate implementation plans (in practice: "current plan" vs. "some revision") |
| computation `E ∈ E` | one plan-review round / one review lens dispatch |
| cost `c` | credits + latency + context burned by one plan-check round |
| `μ_i(s)` | expected quality of plan `i` given review findings so far |
| stop action `⊥` | freeze scope, dispatch the Coder |
| `max_i μ_i(s)` | the plan you'd ship right now |

### 1.3 The myopic policy — this is the proposal

Hay et al., **Definition 6** [PROVES]:

> π^m(s) = argmax_{a∈As} Q^m(s,a), where
> **Q^m(s, ⊥) = max_i μ_i(s)**
> **Q^m(s, E) = E_M[ −c + max_i μ_i(S_1) | S_0 = s, A_0 = E ]**

> *"The myopic policy (known the metalevel greedy approximation with single-step assumption in Russell and Wefald (1991a)) takes the best action, to either stop or perform a computation, **under the assumption that at most one further computation can be performed**."*

The proposal's stop test — *"is there a plausible finding that would change the plan? if not, stop"* — is precisely the test `Q^m(s,E) ≤ Q^m(s,⊥)`, i.e. **"does one more computation change `argmax_i μ_i`?"**

Russell & Wefald state the underlying identity directly (IJCAI-89, p.336) [PROVES]:

> *"a complete computation has no value unless it changes the choice of move"*

That sentence **is** EXPECTED_PLAN_CHANGE, with "move" = "implementation plan."

### 1.4 The precise formal identification — and why the proposal is *weaker* than myopic VOI

This matters and should not be glossed. EXPECTED_PLAN_CHANGE is **not** textbook myopic VOI. It is myopic VOI **with two of its three ingredients deleted**: [INFER — this is my formal reading of the proposal text against the definitions above, not a claim any paper makes about this specific proposal]

| Ingredient of Q^m(s,E) | Present in EXPECTED_PLAN_CHANGE? |
|---|---|
| **Single-step assumption** (evaluate as if at most one more computation) | ✅ **Inherited in full** — this is the source of every failure mode in §3 |
| **The expectation `E[·]`** over a calibrated posterior on computation outcomes | ❌ **Replaced** by an existence/plausibility check ("state the smallest plausible finding"). No probability weighting: a 1%-likely finding and a 90%-likely finding both license continuing. |
| **The cost term `−c`** | ❌ **Absent.** The rule has no `c`. It continues iff a plan-changing outcome is *nameable at all*, not iff expected gain exceeds cost. |

So the rule **inherits 100% of the single-step blindness while discarding the two elements (probability and cost) that make myopic VOI a decision rule at all.**

And there is a third substitution, which is the largest unstated assumption in the whole proposal: **the expectation is computed by the orchestrator's introspection.** `Q^m(s,E)` requires `P(E = e | evidence)` — a distribution over what the next review round will find. The proposal supplies this by asking the orchestrator to imagine it. That substitution is unvalidated (§5.3).

**Name to use in the spec:** *meta-greedy stopping under the single-step assumption, with a nameability oracle substituted for the VOI expectation.*

---

## 2. The strongest theoretical SUPPORT

I am not strawmanning this. The proposal has real theory behind it, and one of the results below is a genuinely strong argument *for* shipping it.

### 2.1 The kernel is correct: zero-decision-relevance ⟹ zero value

Russell & Wefald (IJCAI-89, p.336) [PROVES]: *"a complete computation has no value unless it changes the choice of move."*

The clause **"if the only answer is 'more confidence,' stop"** is a correct application of this. Review that cannot change the plan has zero value *by definition*, no matter how reassuring. This is the decision-analytic core (Howard 1966 [SECONDARY — citation verified, full text not opened]) and the proposal deserves credit for targeting a real pathology: reviewing for reassurance rather than for decision-relevance.

**This is the part to keep.** Every criticism in §3 is about the *single-step* quantifier, not this kernel.

### 2.2 [STRONGEST SUPPORT] Myopic stopping has a **zero false-continue rate** — Hay et al. Theorem 7

**Theorem 7** [PROVES] — verbatim:

> *"Given a metalevel decision problem M = (S, s0, As, T, R) if the myopic policy performs some computation in state s ∈ S, then the optimal policy does too, i.e., if π^m(s) ≠ ⊥ then π\*(s) ≠ ⊥."*

**Read this carefully — it is the best argument for the proposal.** It says: *every review round that EXPECTED_PLAN_CHANGE authorizes is a round the optimal policy would also authorize.* The rule **never** tells you to review when you shouldn't. It has a **provably zero false-continue rate.**

If your problem is over-planning — and per the framing, it is — this is exactly the guarantee you want. A rule that can only err by stopping early is a rule that structurally cannot cause the pathology you're trying to kill.

**[INFER]** This is why the proposal *feels* right, and it is a legitimate reason to want it. The entire question is whether the price (§3) is acceptable.

### 2.3 Myopic stopping IS optimal under a closure condition — Hay et al. Theorem 9

**Definition 8** [PROVES]: *"a subset S′ ⊆ S of states is closed under transitions if whenever s′ ∈ S′, a ∈ As′, s″ ∈ S, and T(s′,a,s″) > 0, we have s″ ∈ S′."*

**Theorem 9** [PROVES] — verbatim:

> *"Given a metalevel decision problem M = (S, s0, As, T, R) and a subset S′ ⊆ S of states closed under transitions, **if the myopic policy stops in all states s′ ∈ S′ then the optimal policy does too**."*

This is the rescue. Myopic stopping *is* optimal — **provided the "no value" verdict holds not just here, but across every reachable state.** This is the basis of the cheap fix in §4.1.

### 2.4 Sufficient conditions for myopic optimality — Hansen & Zilberstein Theorem 1 + Corollary 1

**Theorem 1** [PROVES] — verbatim:

> *"Given a time-dependent utility function, the myopic monitoring approach is optimal when:*
> *(1) evaluating the MEVC takes a negligible amount of time; and*
> *(2) for every time t and quality level q for which MEVC is non-positive, MEVC is also non-positive for every time t + Δt and quality level q + Δq."*

**Corollary 1** [PROVES] — verbatim:

> *"The second condition in Theorem 1 is met when **the expected marginal increase in the intrinsic value of a solution is a non-increasing function of quality** and **the marginal cost of time is a non-decreasing function of time**."*

**Translation: myopic stopping is optimal iff deliberation has diminishing returns and delay gets costlier.** Note condition (2) is the same idea as Hay et al.'s "closed under transitions" — once value goes non-positive, it must *stay* non-positive.

The authors are optimistic [PROVES]:

> *"Because the assumptions on which they rest are reasonably intuitive, Theorem 1 and its corollary suggest that **there is a large class of applications for which the myopic approach to meta-level control is optimal**."*

**This is the strongest general defense of the proposal — and §3.5 is where it dies for our specific process.**

### 2.5 A myopically-defined index can be exactly optimal — Weitzman's Pandora's Rule

Weitzman [PROVES — from the MIT working-paper version; see provenance caveat] defines the reservation price `z_i` of box `i` by equation (7), which with no discounting reduces to `c_i = ∫_{z_i}^{∞} (x_i − z_i) dF_i(x_i)` — i.e. `E[(x_i − z_i)^+] = c_i`. Then:

> *"**Pandora's Rule** … **Selection Rule:** If a box is to be opened, it should be that closed box with highest reservation price. **Stopping Rule:** Terminate search whenever the maximum sampled reward exceeds the reservation price of every closed box."*

And crucially [PROVES]:

> *"the reservation price of each box is calculated by equating a hypothetical gain of stopping (5) not with the full gain of opening the box and continuing on in an optimal manner, but rather **with the myopic gain of opening the box and terminating (6)**. In other words, the reservation price of a box depends only on the properties of that box and is independent of all other search opportunities."*

**This is an existence proof that myopia in an index definition does not imply suboptimality.** Weitzman's rule is built from a *myopic* comparison and is *exactly optimal* for his problem. Anyone arguing "myopic ⟹ broken" as a general principle is wrong, and this is the counterexample. (§3.6 explains why it nonetheless does not rescue us.)

### 2.6 A greedy index rule is optimal for sequential diagnosis — Kalagnanam & Henrion

Kalagnanam & Henrion (1990) [PROVES] — in their setting (system failed, exactly one component faulty, each test *"will tell us for certain whether it is working"*, cost `c_i` independent of sequence):

> *"It turns out that the optimal strategy is extremely simple: Select as the next element to test the one that has the smallest value of the ratio C/Pi, and continue testing until the faulty element is identified. We will call this the C/P algorithm."*

Heckerman, Horvitz & Middleton summarize the general condition [PROVES that they say it; the underlying result is [SECONDARY] to K&H, whose paper I opened and which is consistent]:

> *"Kalagnanam and Henrion, 1990, showed that **a myopic policy is optimal, when the decision maker's utility function U(·) is linear, and the relationship between hypotheses and evidence is deterministic**."*

**The sufficient condition for myopic optimality is therefore: linear/additive utility + deterministic evidence.** Worth checking against our domain — and it fails (§5.2): plan-review findings are emphatically *not* deterministic evidence.

### 2.7 Empirical: myopia has been survivable in practice

Heckerman et al. [PROVES that they report it; the study itself is [SECONDARY] — Gorry 1968 not opened]:

> *"In an empirical study, Gorry, 1968, demonstrated that the use of a myopic analysis does not diminish significantly the diagnostic accuracy of an expert system for congenital heart disease."*

### 2.8 Satisficing is a legitimate, cheaper target — Simon & Kadane

Simon & Kadane (1975) [PROVES] — abstract, verbatim:

> *"Optimal algorithms are derived for satisficing problem-solving search, that is, search where the goal is to reach any solution, no distinction being made among different solutions. **This task is quite different from search for best solutions or shortest path solutions.**"*

**This matters for framing:** satisficing search is *its own problem with its own optimal algorithms*, not a degraded approximation of optimizing search. "Satisfice the stop" is not "give up on rigor." (§4.5.)

---

## 3. The strongest theoretical REFUTATION and known failure modes

### 3.1 [LEAD] The originators of the theory declared this assumption untenable — in the paper that introduced it

Russell & Wefald, **IJCAI-89, §"Single-step assumption"**, p.336 [PROVES] — verbatim, and this is the single most important quote in this dossier:

> *"We call this the **single-step assumption**. **The assumption sometimes fails.** Recall that a complete computation has no value unless it changes the choice of move; thus **the single-step assumption will predict that certain search steps can have no value, whereas often those steps enable other steps to become valuable.** We will see that, although it makes the expected-value computation tractable, this assumption also places certain limitations on the depth of search in some domains, including game-playing."*

From the **abstract** of the same paper [PROVES]:

> *"We develop a formula for the expected value of a search step in a game-playing context using the single-step assumption, namely that a computation step can be evaluated as it was the last to be taken. … **Although we show that the single-step assumption is untenable in general**, a program …"*

From the **conclusions** [PROVES]:

> *"**The most serious theoretical problem is the need for the single-step assumption.**"*

**There is no ambiguity here.** The people who invented the formalism EXPECTED_PLAN_CHANGE instantiates identified this exact approximation as its most serious theoretical problem, in the founding paper, and said it *"will predict that certain search steps can have no value, whereas often those steps enable other steps to become valuable."*

Applied to us: **a review lens that finds nothing plan-changing on its own may be exactly the lens that makes the next lens's finding possible.** ("The auth model is per-tenant" is not plan-changing. "The auth model is per-tenant *and* the cache is global" is.)

There is one important nuance R&W add, which is a genuine subtlety and should not be misread as an escape hatch [PROVES]:

> *"It is worth emphasizing here that **if either the meta-greedy or single-step assumptions were completely relaxed, the other would become completely true.** … Thus, the simplification lies in employing the two assumptions **jointly**; neither alone would be a restriction."*

**[INFER]** The proposal employs both jointly (depth-limit-1 on the metalevel *and* evaluate-as-if-last). So it sits squarely in the restrictive regime, not the benign one.

### 3.2 The failure is one-directional — and points exactly where you plan to use it

Hay et al. **Theorem 7** [PROVES] gives `π^m(s) ≠ ⊥ ⟹ π*(s) ≠ ⊥`.

The **converse is not stated, not proven, and is false** — that is the entire reason Theorem 9 needs its extra closure hypothesis. If myopic-stops ⟹ optimal-stops held unconditionally, Theorem 9 would be vacuous.

| | Optimal says CONTINUE | Optimal says STOP |
|---|---|---|
| **Myopic says CONTINUE** | ✅ correct | **impossible** (Thm 7) |
| **Myopic says STOP** | ❌ **FALSE STOP — unbounded** | ✅ correct |

**The rule's only possible error is premature stopping, and stopping is the only thing you want to use it for.** [INFER, but directly from Thm 7's structure] The guarantee you get (§2.2) is a guarantee on the behavior you are not trying to control; the failure you get is on the behavior you are.

Hay et al. state the mechanism plainly, Definition 6 note [PROVES]:

> *"**It has a tendency to stop too early**, because **changing one's mind about which real action to take often takes more than one computation.**"*

### 3.3 Measured: the myopic policy plateaus at exactly the proposal's stop condition

Hay et al., §4, describing Figure 2 (Bernoulli selection, k=25 arms, wide range of step costs c) [PROVES]:

> *"The blinkered policy significantly outperforms all others. **The myopic policy plateaus as it quickly reaches a position where no single computation can change the final action choice.**"*

**"No single computation can change the final action choice" is a verbatim restatement of the EXPECTED_PLAN_CHANGE stop condition.** Hay et al. ran the experiment. The policy that stops there plateaus and is beaten by the alternative in §4.2.

Also [PROVES]: *"The myopic policy is an extreme approximation, **often stopping far too early**."*

### 3.4 Measured: the failure gets *worse* as the problem gets bigger

This is the most operationally alarming result and it is easy to miss. Russell & Wefald, IJCAI-89 §8 [PROVES] — verbatim:

> *"Although MGSS\* seems extremely effective for small time allocations, **the single-step assumption eventually begins to bar almost all nodes from being expanded as the tree grows larger.** Hence comparisons against a much deeper-searching alpha-beta are unfavourable. Preliminary results indicate that MGSS\* plays a slightly better than even game against depth-5 alpha-beta, while generating about 1/6 as many nodes of search. **Against depth-6 alpha-beta, MGSS\* appears to be incapable of generating large enough search trees to play effectively.**"*

**This is a scaling failure, not a constant-factor one.** The rule does not degrade uniformly; it progressively **bars all further deliberation** as the problem grows. On small problems it is excellent and 6× cheaper. On big problems it becomes *incapable*.

**[INFER — the mapping is mine, the result is theirs]** The predicted analogue: EXPECTED_PLAN_CHANGE will look terrific on small specs (fast, cheap, no quality loss — which will read as validation) and will bite hardest on large, novel, multi-subsystem specs — **precisely the specs where plan review is load-bearing.** Any pilot that tests it on small specs will produce a false positive.

### 3.5 The cleanest statement of the failure — and the internal inconsistency

Heckerman, Horvitz & Middleton (UAI-91), §"NONMYOPIC ANALYSIS" [PROVES] — verbatim:

> *"the myopic procedure for identifying cost-effective observations includes **the incorrect assumption that the decision maker will act after observing only one piece of evidence.** This myopic assumption can affect the diagnostic accuracy of an expert system because **information gathering might be halted even though there exists some set of features whose value of information is greater that the cost of its observation.** For example, **a myopic analysis may indicate that no feature is cost effective for observation, yet the value of information for one or more feature pairs (were they computed) could exceed the cost of their observation.**"*

That is the target failure mode in one paragraph: **zero value individually, positive value jointly.**

And then the knife [PROVES] — verbatim:

> *"**Because the myopic procedure allows for the gathering of additional evidence, the procedure is inconsistent with its own assumptions.**"*

**[INFER]** This applies to EXPECTED_PLAN_CHANGE without modification. The governor asks *"would **one** more round change the plan?"* while governing a process that demonstrably runs **many** rounds (this repo has runs reaching round 6, 7, 8, and one reaching 31). The rule assumes a world in which it is not deployed.

### 3.6 [THE FAILURE SHAPE THAT IS OURS] Flat near-term, substantial later

Hansen & Zilberstein, immediately after their optimism in §2.4 [PROVES] — verbatim:

> *"Nevertheless, **there are cases in which reliance on MEVC can lead to a sub-optimal stopping decision.** Horvitz and Breese [3,17] describe a bounded conditioning algorithm for probabilistic inference in belief networks for which **MEVC can mislead because expected improvement is "flat" in the near term but substantial after some number of time steps. Because this can lead to a premature stopping decision**, Horvitz suggests various degrees of lookahead to compute EVC more reliably. Horsch and Poole [12] address a similar problem in considering meta-level control of an anytime algorithm for influence diagram evaluation. To counter it, they describe a non-myopic approach to estimating the EVC based on a linear model constructed from empirical data."*

**The named failure geometry: plateau-then-jump.** A real algorithm (bounded conditioning — Horvitz, Suermondt & Cooper, UAI-89) exhibits it, and it defeats MEVC.

**[INFER]** This is the shape of plan review. Three lenses find nothing quotable; the fourth finds the tenancy model is wrong and the whole plan changes. A rule that stops at the first flat stretch never reaches the jump.

### 3.7 [MEASURED — the empirical kill shot] This repo's plan-check hazard is FLAT, violating the licensing condition

§2.4 established that the myopic approach is licensed by **Corollary 1**: *"the expected marginal increase in the intrinsic value of a solution is a non-increasing function of quality."* That is an empirical claim about a process. **It is testable, and I tested it.**

**Method.** Parsed all `plan_check_log.md` under `<HOME>/Claude/loop` (92 found; 59 had parseable `## Round N` headers). For each round section, classified the verdict as PLAN_FAIL / PLAN_PASS / UNK by first-occurrence of the token. Computed the hazard
`h(k) = Pr(round k = PLAN_FAIL | rounds 1..k−1 all PLAN_FAIL)`.
Script (re-runnable): `/private/tmp/claude-501/-Users-eobodoechine/92b560fb-4598-4d57-abdc-37b2f6872c8e/scratchpad/profile.py`

**Result:**

| k | at risk | failed | **h(k)** |
|---|---|---|---|
| 1 | 52 | 42 | **0.81** |
| 2 | 33 | 22 | **0.67** |
| 3 | 19 | 16 | **0.84** |
| 4 | 11 | 8 | **0.73** |
| 5 | 5 | 3 | 0.60 |
| 6 | 2 | 1 | 0.50 |

Per-round marginals (all runs): round 1 → 44 FAIL / 10 PASS; round 2 → 29/14; round 3 → 25/13; round 4 → 16/6; round 5 → 8/3; round 6 → 6/2. Runs reaching ≥4 rounds: 23. Observed verdict strings include `FFFFF`, `FFFF`, `FFFFFP`.

**The hazard is flat. It does not decay.** Conditional on a spec having already failed two rounds, the third round finds *another* defect **84%** of the time — as high as round 1.

**Therefore:** the precondition of Hansen & Zilberstein's Corollary 1 (non-increasing marginal value) is **violated** by loop-team's actual plan-check process. Condition (2) of Theorem 1 fails. **Theorem 1 does not license myopic stopping for this process.** The one general result that would have justified the proposal does not apply here — measured, not argued.

**Caveats — stated honestly, because they matter:**
- **Survivorship/selection bias (the big one).** These rounds exist only because an orchestrator *chose* to run them. So `h(k)` estimates `Pr(defect | a round was run)`, not `Pr(defect | a round would be run under EXPECTED_PLAN_CHANGE)`. This biases `h` **upward**. This is a real limitation and it means the table is **not** a direct measurement of the proposal's false-stop rate.
- **But the load-bearing observation survives it.** The claim I am making is about **flatness in k**, not level. A selection-bias story must explain why the bias is *constant across k* — and the natural prior runs the other way: later rounds should be *more* selected (only the genuinely worrying specs get a round 4), which would inflate late h and understate decay… but there *is* no decay to understate. The flat shape is what Corollary 1 forbids.
- **PLAN_FAIL is coarse.** It conflates "found a typo" with "found the architecture is wrong." There is no severity weighting. (The logs *do* carry `gap_type:` — see §5.2.)
- **Parse noise.** 59/92 files parsed; 35/241 round-sections UNK; heterogeneous `outcome:` formats.
- **Not independent.** Rounds within a run are correlated; n is small at k ≥ 5.
- Round counts include some runs whose later rounds were human-directed rather than autonomous.

**A concrete instance of the failure mode, from this repo** [MEASURED — `<HOME>/Claude/loop/runs/2026-07-08_taxahead-wiring/plan_check_log.md`]: rounds 1, 2, and 3 each returned PLAN_FAIL with a *new, substantial, previously-unnameable* design defect — round 3's finding was that round 2's fix had *relocated* the problem (`readinessFor` called 6×, not the 4 the round-2 revision assumed; plus an entirely un-named third fabrication component). No orchestrator could have named round 3's finding at round 1. EXPECTED_PLAN_CHANGE at round 1 would have shipped a plan with three live defects.

### 3.8 [REFUTED] Weitzman / Pandora's box is the WRONG model — and the reason is precise

The dispatch hypothesized Weitzman's reservation-value rule is the closest match. **Refuted.** It fails on exactly one assumption, that assumption's failure is well-studied, and it has a name.

**The assumption.** Weitzman [PROVES] — verbatim:

> *"Sources are sampled sequentially, in whatever order is desired. **When it has been decided to stop searching, only one opportunity is accepted, the maximum sampled reward.**"*

**You may only accept a box you have opened.** Obligatory inspection. That is what makes the index rule work.

**Our structure violates it.** In the metalevel MDP (Hay et al., Def. 3), stopping pays `R(s,⊥,⊥) = max_i μ_i(s)` — the max over **all** actions `i`, *including ones no computation ever touched*, valued at their prior mean. **You can ship a plan you never reviewed.** That is the whole point of a stop rule for plan review.

**The variant has a name and a verdict.** Doval (2018), *Journal of Economic Theory* 175:127–158 [PROVES — abstract opened] — verbatim:

> *"I study a single-agent sequential search problem as in Weitzman (1979). **Contrary to Weitzman, conditional on stopping, the agent may take any uninspected box without first inspecting its contents.** … I identify sufficient conditions on the parameters of the environment under which I characterize the optimal policy. **Both the order in which boxes are inspected and the stopping rule may differ from that in Weitzman's model.**"*

**The computational verdict.** Beyhaghi & Kleinberg, *Pandora's Problem with Nonobligatory Inspection*, EC 2019, arXiv:1905.01428 [PROVES — abstract opened] — verbatim:

> *"**Unlike the original Pandora's problem, the version with nonobligatory inspection cannot be solved optimally by any simple ranking-based policy, and it is unknown whether there exists any polynomial-time algorithm to compute the optimal policy.**"*

**Independently corroborated inside the metareasoning literature.** Hay et al., **Example 4 (Non-indexability)** [PROVES] — a 3-action metalevel model (`U1 ∈ {−1.5,1.5}` hi-var, `U2 ∈ {0.25,1.75}` lo-var, `U3 = λ` known; each computation reveals one `U_i` exactly at cost 0.2; 9 states, solved exactly):

> *"Note the inversion where for low λ observing action 1 is strictly optimal, while for medium λ observing action 2 is strictly optimal." … "**Inversions like this are impossible for index policies.**"*

and from the paper's own summary of contributions:

> *"We also show by counterexample that **optimal index policies (Gittins, 1989) may not exist for selection problems.**"*

**So:** Weitzman's rule is optimal for obligatory-inspection search. Plan-review is **non-obligatory-inspection** search. Therefore **no reservation-value / index / ranking rule is optimal for it**, and computing the optimal policy may not even be polynomial. **REFUTED — do not build a reservation-value rule.**

**The irony worth internalizing** [INFER]: Weitzman's rule is a *myopically-defined index* that is *exactly optimal* (§2.5). The single feature that destroys that guarantee is **the option to act without inspecting** — which is the very feature that makes EXPECTED_PLAN_CHANGE feel natural ("we can always just ship"). The domain property that motivates the proposal is the same property that voids the theory that would have justified it.

**Salvage:** Beyhaghi & Kleinberg do give a usable fallback [PROVES]: *"We introduce a family of 'committing policies' such that it is computationally easy to find and implement the optimal committing policy. We prove that the optimal committing policy is guaranteed to approximate the fully optimal policy within a 1−1/e = 0.63… factor."*

### 3.9 [REFUTED] SPRT and the secretary problem are also the wrong models

**Wald's SPRT** — optimal (Wald & Wolfowitz, 1948) for deciding between **two simple hypotheses** from **i.i.d.** observations with **known likelihoods** [SECONDARY — neither Wald 1945 nor Wald & Wolfowitz 1948 opened; Wald 1945 verified only via Hay et al.'s reference list].

**[INFER]** Plan-review lenses are neither i.i.d. nor exchangeable: each lens examines a *different facet*, and re-running a lens yields ≈ nothing new. Hay et al. encode exactly this in Definition 3 — the state space ranges over sequences of **distinct** `E_i ∈ E`, i.e. sampling **without replacement from a finite heterogeneous pool**. SPRT models repeated draws from one distribution. Wrong model.

One SPRT-flavored result *is* relevant, though — Hay et al. **Example 3** [PROVES], *"inspired by the sequential probability ratio test (Wald, 1945)"*, exhibits a metalevel problem giving *"finite, although exponentially decreasing, probability to arbitrarily long sequences of computations."* **The optimal policy's *actual* computation count can be unbounded** even though its expectation is finite (Thm 5). So "the optimal policy always terminates promptly" is false, and Hay et al. flag the broader point in their abstract [PROVES]: *"we also provide a simple counterexample to the intuitive conjecture that an optimal policy will necessarily reach a decision in all cases"* — and in the intro, *"in fact, it is possible for an optimal policy to compute forever."*

**Secretary problem** — [INFER, structural; I did not research this one deeply and cite no result for it] requires no-recall, an exogenous arriving stream of candidates, and observability of relative ranks only. Plan review has full recall (the plan doesn't walk away) and no arriving stream. Wrong model. Flagging as **not researched to citation depth** rather than asserting a verdict I didn't ground.

---

## 4. Which formalism we should ACTUALLY use, and what it needs as input

Ranked by cost-to-correctness. **Tier 1 is the recommendation.**

### 4.1 [TIER 1 — DO THIS] Keep the rule, fix the quantifier: add the closure test

The unsound rule and the sound rule differ by one quantifier.

| | Test |
|---|---|
| ❌ **Proposed (unsound)** | "Name a *single* finding that would change the plan. If you can't → stop." |
| ✅ **Sound** | "Is there **any reachable state of this review process** in which a finding would change the plan? If not → stop." |

**Authority:** Hay et al. **Theorem 9** — myopic stopping is optimal on a set of states **closed under transitions** (Def. 8). Equivalently Hansen & Zilberstein **Theorem 1 condition (2)** — MEVC non-positive now *and* at every reachable `(t+Δt, q+Δq)`.

**Operationally**, EXPECTED_PLAN_CHANGE may fire only if the orchestrator can assert the *closure* claim, which in practice means one of:
- every lens in the review set has already been run (the state set is trivially closed — no transitions remain), **or**
- the remaining lenses are about facets the plan provably does not depend on, **or**
- the empirical hazard for round `k` is below threshold (§5.4).

**Why this is the right call:** it is a small edit to the spec, it preserves the proposal's correct kernel (§2.1) and its zero-false-continue guarantee (§2.2), and it converts an *unsound* rule into a *sound* one with a named theorem behind it. Cost ≈ zero.

**Transfer condition (required per role brief):** the closure claim is still asserted **instructionally** by the orchestrator — see §6. That is a genuine weakness and is why §4.4/§5.4 exist.

### 4.2 [TIER 2] The blinkered policy — the literature's own drop-in replacement

Hay et al., **Definition 14** [PROVES]:

> *"With independent actions, we can talk about metalevel policies that focus on computations affecting a single action. **These policies are not myopic—they can consider arbitrarily many computations—but they are blinkered because they can look in only a single direction at a time.**"*
> `π^b(s) = argmax_{a∈As} Q^b(s,a)` where `Q^b(s,⊥) = ⊥` and `Q^b(s,E_i) = sup_{π∈Π^b_i} Q^π(s,E_i)`, with `Π^b_i` the policies that only ever choose computations in `E_i`.

**Guarantee** [PROVES]: *"Clearly, blinkered policies are better than myopic: **Q^m(s,a) ≤ Q^b(s,a) ≤ Q\*(s,a)**."*
**Cost** [PROVES]: Theorem 16 decomposes it into `k` one-action subproblems; *"the blinkered policy can be numerically computed in time O(D/c²) independent of k."*
**Evidence** [PROVES]: *"The blinkered policy significantly outperforms all others"* (Fig. 2, k=25, wide range of c).

**Why it fits our domain beautifully** [INFER]: one "direction" = **one review lens**. Blinkered asks *"could **this one lens**, run to exhaustion (arbitrarily many findings), change the plan?"* — not *"could one finding?"* That is exactly the right granularity for a lens-based review process, and it is a far weaker bar to clear than nameability.

**Required input — and the honest gap:** Definition 13, **independent actions**: `E` must partition into `E_1 ∪ … ∪ E_k` with `{U_i} ∪ E_i` independent across `i`. **Our lenses are almost certainly not independent** — a bad spec produces *correlated* findings across lenses (the TaxAhead run in §3.7 is a direct example: one root cause surfaced through three lenses). The ordering `Q^m ≤ Q^b ≤ Q*` is stated in the paper under the independent-actions assumption; **off that assumption the guarantee is not established.** Do not claim it holds for us. Treat blinkered as a *better heuristic with a conditional theorem*, not a proven dominance.

### 4.3 [TIER 3] Non-myopic DP monitoring — Hansen & Zilberstein §3.3

The value function [PROVES]:

```
V(qi, t) = max_d { U(qi, t)                              if d = stop
                 { Σ_j Pr(qj | qi, t) · V(qj, t + Δt)    if d = continue
```

**Theorem 2** [PROVES]: *"A monitoring policy that maximizes the above value function is optimal when quality improvement satisfies the Markov property and monitoring has no cost."*
**Cost** [PROVES]: `O(|m|²|n|)`, computed **off-line** — *"Because computation is off-line, this is an example of what Horvitz calls compilation of metareasoning."*

**Required input:** the **dynamic performance profile** `Pr(q_j | q_i, t)` — Definition 5 [PROVES]: *"denotes the probability of getting a solution of quality q_j by continuing the algorithm for time interval Δt when the currently available solution has quality q_i."*

**This is the only tier whose input we can actually estimate** — see §5.2. It is the right *destination*; Tier 1 is the right *next step*.

### 4.4 [USE IMMEDIATELY, NEARLY FREE] The EVPI budget ceiling — Hay et al. Theorem 5

**Theorem 5** [PROVES] — verbatim:

> *"The optimal policy's expected number of computations is bounded by **the value of perfect information (Howard, 1966) times the inverse cost 1/c**:*
> `E^π*[N | S_0 = s] ≤ (1/c) · ( E[max_i U_i | S_0 = s] − max_i μ_i(s) )`
> *Further, any policy π with infinite expected number of computations has negative infinite value, hence the optimal policy stops with probability one."*

**Deliberation budget ≤ EVPI ÷ cost-per-round.** This needs only a crude EVPI guess ("a wrong plan costs ~1 wasted build") and a cost-per-round number — **both of which we already have.** It is the cheapest real thing in this dossier, and note what it bounds: **the opposite failure** (planning forever). It is the correct tool for the pathology the proposal is actually aimed at, and unlike EXPECTED_PLAN_CHANGE it cannot false-stop — it only imposes a ceiling.

**Caveat** [PROVES]: the bound is on the **expectation** only. Example 3 (§3.9) shows the *actual* count can be unbounded.

### 4.5 [THE PRAGMATIC ANSWER] Satisfice the stop, don't optimize it

"Optimize the stop" needs `Pr(q_j|q_i,t)` and a utility scale (§5.1) — we have neither. "Satisfice the stop" needs only an **aspiration level**: *stop when the plan clears bar A*, not *stop when marginal VOI < cost*.

Simon & Kadane (1975) [PROVES] establish that satisficing search is a distinct problem with its own optimal algorithms — *"search where the goal is to reach any solution, no distinction being made among different solutions… quite different from search for best solutions."* Kalagnanam & Henrion connect their own optimal C/P rule to it [PROVES]: *"This task is an example of what Simon & Kadane (1975) have called satisficing search."*

**[INFER]** For loop-team, the aspiration-level framing is: *"stop when the last N rounds found only gaps below severity S"* — a threshold on **observed findings**, not on **imagined ones**. It is cheaper to implement correctly than any VOI rule because it requires **no distribution over computation outcomes at all** — only a severity bar and a counter. And it degrades gracefully: it errs toward more review when severity is ambiguous, which is the safe direction (§3.2).

**This is very likely the right thing to actually ship**, with §4.4's EVPI ceiling as the anti-spin guard on the other side.

### 4.6 Rejected: exact metalevel MDP / exact VOI

Requires the full metalevel probability model `(U_1,…,U_k, E)`. Not available (§5.1). Not a candidate.

---

## 5. What is cheaply computable vs. what requires probability estimates we do not have

**This is the section to be brutal in, so: most of the theory above is unrunnable by us, and the proposal's central quantity is not merely hard to estimate — it is not defined for our domain.**

### 5.1 NOT AVAILABLE — and not "hard," genuinely absent

| Quantity | Needed by | Why we don't have it |
|---|---|---|
| `U_i` — utility of implementation plan `i` | Everything | **There is no utility scale for plans at all.** Not "poorly estimated" — undefined. We have no cardinal quality metric for a spec. |
| `μ_i(s) = E[U_i \| evidence]` | Metalevel MDP, myopic VOI, blinkered | Requires `U`. Absent. |
| The metalevel probability model `(U_1,…,U_k, E)` | Hay et al. everything | Requires a **joint distribution over plan utilities and review outcomes**. Not estimable from 92 logs. |
| **`Q^m(s,E) = E[−c + max_i μ_i(S_1)]`** | **The proposal itself** | Requires all of the above. **NOT COMPUTABLE.** |
| `F_i` — reward distribution per lens | Weitzman `z_i` | Absent. (And §3.8: the rule wouldn't be optimal anyway.) |
| Exact `EVPI = E[max_i U_i] − max_i μ_i(s)` | Hay Thm 5 | Requires `U`. Only an order-of-magnitude guess available — which is enough for §4.4. |
| Likelihoods `p_0, p_1` | SPRT | Absent, and the i.i.d. premise fails (§3.9). |

**The load-bearing consequence, stated plainly: true myopic VOI is not computable for us either.** `Q^m(s,E)` needs a posterior over what the next review round will find. **That is exactly why the proposal replaces the expectation with "state the smallest plausible finding."** The nameability oracle is not a simplification of the theory — **it is a substitution for the one input the theory requires and we cannot supply.** That substitution is the largest unstated assumption in the proposal and it has never been validated (§5.4).

### 5.2 CHEAPLY COMPUTABLE — the dynamic performance profile, and the literature says to get it exactly this way

Exactly one object in the entire dossier is estimable from what we already log: **Hansen & Zilberstein's `Pr(q_j | q_i, t)` (Def. 5)**. And the anytime literature explicitly prescribes the empirical route — Zilberstein & Russell (1996), §2.2.3 *"Acquiring and Representing Performance Profiles"* [PROVES] — verbatim:

> *"In general, however, such structural analysis of the code is hard because the improvement in quality in each iteration and its run-time may be unpredictable. To overcome this difficulty, **a general simulation method can be used. It is based on gathering statistics on the performance of the algorithm on randomly generated problem instances. Ideally, the statistics are gathered for the same population of instances as will appear when the algorithm is deployed. This can be ensured by learning the profiles during actual operation.**"*

**We have 92 `plan_check_log.md` files. That *is* "actual operation."** Available today, no new instrumentation:

| Signal | Where | Status |
|---|---|---|
| **Per-round defect hazard `h(k)`** | 59 parseable logs | ✅ **computed** (§3.7): 0.81 / 0.67 / 0.84 / 0.73 / 0.60 / 0.50 |
| Round-count distribution | round headers | ✅ computed: 54 / 47 / 37 / 23 / 11 / 9 / 2 / 1 … (rounds 1→8) |
| **`gap_type:`** (`DESIGN`, …) | logged per round | ✅ present — **this is the missing severity/quality dimension**; it is the natural `q` |
| `broken_assumption` / `why_it_fails` / `proposed_fix` | logged per round | ✅ present — supports finer quality coding |
| Cost per round `c` | credits/tokens/wall-clock per dispatch | ✅ already logged |
| Terminal outcome (PLAN_PASS vs escalation) | logs | ✅ present |

Mapping: `q ≈ (round index, cumulative gap_type severity)`, `t ≈ round index`, `Pr(q_j|q_i,t) ≈` the hazard table conditioned on `gap_type`. **That is a real dynamic performance profile, from real operation, at ~zero marginal cost.**

**Honest limits:** heterogeneous formats (59/92 parse); 35/241 sections UNK; PLAN_FAIL is binary; rounds correlated within a run; and the selection bias of §3.7. Cleaning this up = standardizing the `outcome:` line, which is a one-line spec change to the plan-check role.

### 5.3 The proxy that should substitute for VOI

**Replace the un-estimable `Q^m(s,E) > 0` with an empirically-calibrated hazard threshold:**

> **Continue iff** `ĥ(k | gap_type history) × (expected cost of shipping a defective plan) > (cost of one review round)`

where `ĥ` is **read off the historical profile, not off the orchestrator's introspection.**

Why this is the right substitution:
- It is **exactly the input Tier-3 DP needs** (§4.3), so it is on the path to the correct formalism rather than a detour.
- It is **estimable today** (§5.2).
- It is **falsifiable**: it predicts *"round k+1 finds a defect with probability ĥ"*, which the next run confirms or refutes. EXPECTED_PLAN_CHANGE makes no falsifiable prediction at all.
- It is a **frequency measured from the process's own history**, not a self-report.

**The decisive structural argument** [INFER — my reasoning; grounded in R&W's "steps enable other steps" mechanism (§3.1), not asserted by any paper about this proposal]:

> **EXPECTED_PLAN_CHANGE asks the orchestrator to estimate the value of information that would correct the orchestrator's own model. But if the orchestrator could name the finding, the finding would already be incorporated — a nameable defect is a fixed defect.** The test's power is therefore *systematically lowest exactly when the plan contains unknown-unknowns* — i.e. precisely when review is most valuable. Its sensitivity is **anti-correlated with need.**

This is the structural reason to expect the pattern §3.7 measured: the orchestrator's ability to *name* a specific plan-changing defect surely decays with round number, while the empirical hazard that one *exists* stays flat at ~0.7–0.84. **The rule's confidence and the world's defect rate diverge.** A hazard estimate has no such pathology: it does not require anyone to imagine the defect, only to have counted past ones.

### 5.4 [THE MISSING MEASUREMENT — do this before enforcing anything]

**Nobody — not this dossier, not the literature — has measured the one number that decides this:**

> **`Pr(a plan defect exists at round k | the orchestrator cannot name a plausible plan-changing finding at round k)`**

That is the false-stop rate of EXPECTED_PLAN_CHANGE. Theory (§3.2) says it is the only way the rule can fail. §3.7 bounds the *unconditional* defect rate at ~0.7–0.84 but says nothing about the *conditional* rate, because the conditioning event was never logged.

**It is cheap to measure — shadow mode:**
1. At every plan-check round, the orchestrator **records** its EXPECTED_PLAN_CHANGE verdict + the finding it named (or "none — more confidence only").
2. **The round runs anyway.** The governor advises; it does not gate.
3. Score: when the verdict was "stop," did the round find a defect? At what `gap_type`?
4. After N rounds you have the false-stop rate **and** a `gap_type`-conditioned hazard profile — which is simultaneously the input Tier-3 DP needs (§4.3, §5.3). One experiment, two deliverables.

**Cost: ~zero** — you are running the rounds regardless. **Kill criterion:** if the false-stop rate at `gap_type: DESIGN` exceeds [threshold Nnamdi sets], the rule is refuted for autonomous use and stays advisory.

**Recommendation: do not enforce EXPECTED_PLAN_CHANGE as a gate until this number exists.** The theory says its only failure mode is silent premature stopping; the repo's own data says the defect hazard doesn't decay; and the rule's proposed authority is precisely to stop. Shadow-run it.

---

## 6. Transfer-condition check (required by the role brief)

| Mechanism | (a) Execution context required | (b) Satisfied by loop-team? | (c) Structural or instructional? |
|---|---|---|---|
| **EXPECTED_PLAN_CHANGE as proposed** | A calibrated posterior over review outcomes; a utility scale over plans | ❌ **No** — neither exists (§5.1) | ⚠️ **Instructional** — orchestrator self-reports. **FLAGGED: silent + load-bearing.** See below. |
| **Closure test (§4.1)** | Same, plus reachability reasoning over the lens set | ⚠️ Partially — the "all lenses run" form is checkable structurally | Mixed: the *"all lenses run"* form is **structural** (countable). The *"no reachable finding"* form is **instructional**. **Prefer the countable form.** |
| **Blinkered policy (§4.2)** | Independent-actions partition (Hay Def. 13) | ❌ **No** — lenses produce correlated findings (§3.7 TaxAhead) | Structural if implemented in code; but its **theorem does not transfer** off the independence assumption |
| **DP monitoring (§4.3)** | `Pr(q_j\|q_i,t)`; Markov quality; ~free monitoring | ⚠️ Profile estimable (§5.2); Markov assumption **untested** | **Structural** — a compiled policy table, indexed at runtime |
| **EVPI ceiling (§4.4)** | Crude EVPI + cost-per-round | ✅ **Yes** | **Structural** — a hard round-count cap, enforceable by the harness |
| **Aspiration level (§4.5)** | A severity bar + a counter | ✅ **Yes** — `gap_type` already logged | **Structural** — countable from the logs |
| **Weitzman reservation rule** | Obligatory inspection; known `F_i` | ❌ **No** on both (§3.8) | n/a — **refuted, do not build** |

**FLAGGED per role brief — instructional guarantee whose failure is silent AND load-bearing:**

EXPECTED_PLAN_CHANGE as proposed depends on the orchestrator *honestly and competently* introspecting. A compliance failure is **not detectable as an error**. Concretely: an orchestrator under credit/latency pressure that wants to stop planning simply… fails to name a finding. The gate opens. The bad plan ships. **And every downstream gate passes** — because downstream verification checks *the build against the plan*, not *the plan against reality*. A plan defect that review would have caught becomes a build that **correctly implements a wrong plan**, with a green suite.

This is the worst available failure shape, and it is the exact pattern the role brief instructs me to flag: *the failure would not surface as a detectable error but would instead produce wrong outputs that pass downstream checks.* It also rhymes with this repo's own documented lesson `feedback_green_suite_missed_operative_ac` (a 36/36-green suite missed an operative AC; only a live-run Verifier caught it).

**Mitigation:** §4.5's aspiration rule and §4.4's EVPI ceiling are both **countable from logs** — structural, not instructional. Prefer them.

---

## 7. Bottom line

| Question | Answer |
|---|---|
| **What is it?** | Meta-greedy stopping under the single-step assumption (Russell & Wefald 1989; Hay et al. 2012 Def. 6; Hansen & Zilberstein 2001 Defs. 6–7) — with a **nameability oracle substituted for the VOI expectation** and **no cost term**. |
| **Is the kernel right?** | **Yes.** "Information that can't change a decision has zero value" is correct and worth encoding. |
| **Is the implementation right?** | **No.** The single-step quantifier is the one approximation its own inventors called *"untenable in general"* and *"the most serious theoretical problem."* |
| **How does it fail?** | **Only** by stopping too early (Hay Thm 7 is one-directional) — and **worse as specs get bigger** (R&W §8: *"bar almost all nodes … incapable"*). |
| **Would it be OK here?** | **No — measured.** Its licensing condition is diminishing returns (H&Z Cor. 1). This repo's plan-check hazard is **flat**: 0.81 / 0.67 / **0.84** / 0.73. |
| **Is Weitzman the model?** | **REFUTED.** Plan-review is *non-obligatory-inspection* search (Doval 2018) → *"cannot be solved optimally by any simple ranking-based policy"* (Beyhaghi & Kleinberg, EC 2019). |
| **What should we use?** | **§4.1** closure test (cheap, sound) + **§4.4** EVPI ceiling (free, structural) + **§4.5** aspiration-level satisficing (the pragmatic ship) → **§4.3** DP monitoring once the profile is clean. |
| **What must we do first?** | **§5.4 shadow-mode.** Measure the false-stop rate before enforcing. It costs nothing and yields the DP profile as a byproduct. |
| **Recommendation** | **Do not ship EXPECTED_PLAN_CHANGE as an enforcing gate.** Ship it as an **advisory prompt** + a **structural round-cap** (§4.4) + an **aspiration rule on `gap_type`** (§4.5), and shadow-log its verdict to earn the right to enforce it later. |

*(Per role brief: this is a recommendation handed to Oga. I have not modified `fix_plan.md` or any spec.)*

---

## 8. Sources — provenance and honesty flags

**Opened in full, quoted directly (primary, verified):**

| # | Citation | URL opened |
|---|---|---|
| 1 | **Hay, N., Russell, S., Tolpin, D., Shimony, S.E. (2012).** "Selecting Computations: Theory and Applications." *UAI-12*, pp. 346–355. arXiv:1207.5879. | [abs](https://arxiv.org/abs/1207.5879) · [pdf](https://arxiv.org/pdf/1207.5879v1) — full text extracted |
| 2 | **Russell, S. & Wefald, E. (1989).** "On Optimal Game-Tree Search using Rational Meta-Reasoning." *IJCAI-89*, pp. 334–340. | [ijcai.org](https://www.ijcai.org/Proceedings/89-1/Papers/053.pdf) — full text extracted |
| 3 | **Heckerman, D., Horvitz, E., Middleton, B. (1991).** "An Approximate Nonmyopic Computation for Value of Information." *UAI-91*, Los Angeles, pp. 135–141. Morgan Kaufmann. arXiv:1303.5720. | [pdf](https://arxiv.org/pdf/1303.5720) — full text extracted |
| 4 | **Hansen, E.A. & Zilberstein, S. (2001).** "Monitoring and control of anytime algorithms: A dynamic programming approach." *Artificial Intelligence* 126:139–157. | [umass pdf](http://rbr.cs.umass.edu/papers/HZaij01a.pdf) — full text extracted |
| 5 | **Zilberstein, S. & Russell, S. (1996).** "Optimal composition of real-time systems." *Artificial Intelligence* 82(1–2):181–213. | [berkeley pdf](https://people.eecs.berkeley.edu/~russell/papers/aij-anytime.pdf) — full text extracted |
| 6 | **Horvitz, E. (1987).** "Reasoning about Beliefs and Actions under Computational Resource Constraints." *UAI-87*, Seattle, pp. 429–444. arXiv:1304.2759. | [pdf](https://arxiv.org/pdf/1304.2759) — full text extracted; citation cross-checked on [Horvitz's own page](https://erichorvitz.com/paprecent_limitedresources.htm) |
| 7 | **Kalagnanam, J. & Henrion, M. (1990).** "A Comparison of Decision Analysis and Expert Rules for Sequential Diagnosis." *Uncertainty in Artificial Intelligence 4*, pp. 271–281. arXiv:1304.2362. | [pdf](https://arxiv.org/pdf/1304.2362) — full text extracted |
| 8 | **Simon, H.A. & Kadane, J.B. (1975).** "Optimal Problem-Solving Search: All-or-None Solutions." *Artificial Intelligence* 6(3):235–247. | [CMU archive pdf](https://iiif.library.cmu.edu/file/Simon_box00066_fld05074_bdl0001_doc0001/Simon_box00066_fld05074_bdl0001_doc0001.pdf) — full text extracted |

**Opened with a stated caveat:**

| # | Citation | Caveat |
|---|---|---|
| 9 | **Weitzman, M.L.** "Optimal Search for the Best Alternative." *Econometrica* 47(3):641–654 (May 1979). | ⚠️ **All Weitzman quotes are from the MIT Energy Lab working-paper version** (MIT-EL-78-008, May 1978), [dspace pdf](http://dspace.mit.edu/bitstream/handle/1721.1/31303/MIT-EL-78-008-05532979.pdf) — full text extracted. **The published Econometrica version was NOT opened** (econometricsociety.org and scholar.harvard.edu both returned 403). Pandora's Rule and the reservation-price definition are identical in substance in the working paper; equation numbering may differ from the published version. OCR of eq. (5)–(7) is degraded; I reconstructed the no-discounting form `c_i = ∫_{z_i}^∞ (x_i − z_i) dF_i(x_i)` — **flagged as reconstruction.** |
| 10 | **Russell, S. & Wefald, E.** "Principles of metareasoning." *KR-89*, Morgan Kaufmann, pp. 400–411; expanded in *Artificial Intelligence* 49(1–3):361–395 (1991), DOI 10.1016/0004-3702(91)90015-C. | ⚠️ **Only page 1 opened** (title/authors/abstract) via [CMU Newell archive](http://iiif.library.cmu.edu/file/Newell_box00014_fld01011_doc0001/Newell_box00014_fld01011_doc0001.pdf) — the scan is 1 page. **The AIJ full text was NOT opened** (ScienceDirect 403). **I therefore do not quote "Principles of Metareasoning" body text anywhere.** All Russell & Wefald quotes come from the IJCAI-89 companion paper (#2), which I opened in full. Hay et al. attribute the "single-step assumption" specifically to **Russell & Wefald (1991a) = *Do The Right Thing*, MIT Press** (the book) — per their reference list, which I read. |
| 11 | **Doval, L. (2018).** "Whether or not to open Pandora's box." *Journal of Economic Theory* 175:127–158. DOI 10.1016/j.jet.2018.01.005. | ⚠️ **Abstract only**, via [RePEc/IDEAS](https://ideas.repec.org/a/eee/jetheo/v175y2018icp127-158.html). Columbia and ScienceDirect returned 403. Quote is the abstract verbatim. |
| 12 | **Beyhaghi, H. & Kleinberg, R. (2019).** "Pandora's Problem with Nonobligatory Inspection." *EC 2019*. arXiv:1905.01428. | ⚠️ **Abstract only**, via [arXiv abs](https://arxiv.org/abs/1905.01428). The "cannot be solved optimally by any simple ranking-based policy" quote is from the abstract. |
| 13 | **Howard, R.A. (1966).** "Information Value Theory." *IEEE Transactions on Systems Science and Cybernetics* 2(1):22–26. DOI 10.1109/TSSC.1966.300074. | ⚠️ **Citation verified, full text NOT opened** (IEEE paywall; ieeexplore fetch returned empty). Verified via [SciRP reference page](https://www.scirp.org/reference/referencespapers?referenceid=3961252) + Google Scholar lookup (vol. 2, pp. 22–26, DOI matches) + Hay et al.'s in-text citation of it in Theorem 5. **I make no claim about its contents beyond "EVPI/VOI originates here," which is how Hay et al. cite it.** |

**[SECONDARY] — cited by a paper I opened, but NOT independently opened. Do not treat as verified:**

- **Pearl, J. (1988).** *Probabilistic Reasoning in Intelligent Systems.* Morgan Kaufmann. — Russell & Wefald write *"related to what Pearl [1988] has called a 'myopic policy'."* **I verified that R&W say this; I did not open Pearl.**
- **Wald, A. (1945).** "Sequential tests of statistical hypotheses." *Annals of Mathematical Statistics* 16:117–186. — from Hay et al.'s reference list. **Not opened.**
- **Wald, A. & Wolfowitz, J. (1948).** "Optimum Character of the Sequential Probability Ratio Test." *Annals of Mathematical Statistics* 19(3):326–339. [projecteuclid](https://projecteuclid.org/euclid.aoms/1177730197) — **search-verified only, not opened.**
- **Gorry (1968)** — myopic-analysis-doesn't-hurt-accuracy study. Known only via Heckerman et al.'s summary. **Not opened.**
- **Gittins, J. (1979/1989)** — index theorem. Via Hay et al.'s references. **Not opened.**
- **Horvitz, E., Suermondt, H.J., Cooper, G.F. (1989).** "Bounded conditioning: Flexible inference for decisions under scarce resources." *UAI-89*, Windsor ON, pp. 182–193. — **citation verified verbatim on [Horvitz's own publication page](https://erichorvitz.com/paprecent_limitedresources.htm); full text not opened.** This is the algorithm Hansen & Zilberstein name as the MEVC failure case.
- **Breese, J.S. & Horvitz, E. (1990).** "Ideal Reformulation of Belief Networks." *UAI-90*, Cambridge MA, pp. 64–72. — citation verified on Horvitz's page. (Note: Hansen & Zilberstein's ref [3] gives pp. 129–143; Horvitz's own page gives pp. 64–72. **Discrepancy noted, immaterial to any claim here.**)
- **Horvitz, E. (1990).** "Computation and Action under Bounded Resources." PhD Dissertation, Stanford. — citation verified on Horvitz's page; not opened.
- **Horsch, M.C. & Poole, D.** "Estimating the value of computation in flexible information refinement." — Hansen & Zilberstein's ref [12] reads *"Proc. 7th Conference on Uncertainty in Artificial Intelligence, 1999"*, which is **internally inconsistent** (UAI-7 was 1991). **Not opened; cite with caution.**
- **Simon, H.A. (1955).** "A Behavioral Model of Rational Choice." *QJE* 69(1):99–118. — **search-verified only, not opened.** Aspiration-level/satisficing framing in §4.5 rests on Simon & Kadane (1975), which I *did* open, not on this.

**Not researched to citation depth (stated rather than asserted):**
- **Secretary problem** — §3.9's verdict is a structural argument [INFER]; I cite no result and did not chase one. If the orchestrator wants that ruled out formally, it needs its own pass.

**[MEASURED] — computed by me from this repo:**
- Hazard table and round-count distribution (§3.7, §5.2). Source data: 92 `plan_check_log.md` files under `<HOME>/Claude/loop` (59 parseable). Script: `/private/tmp/claude-501/-Users-eobodoechine/92b560fb-4598-4d57-abdc-37b2f6872c8e/scratchpad/profile.py` (**scratch — copy into `loop-team/harness/` if this is to be reproduced durably**). Caveats in §3.7 — especially **selection bias**, which is real and which I do not claim to have controlled for.
- Worked failure-mode instance: `<HOME>/Claude/loop/runs/2026-07-08_taxahead-wiring/plan_check_log.md`.

**Data-access scope note:** all repo reads were confined to `~/Claude/loop` (this repo). No session transcripts or out-of-repo stores were read.
