# Defect-discovery saturation & scope freeze: when have you reviewed ENOUGH?

**Mode D domain research — 2026-07-16**
**Dispatched question:** an agent review loop keeps finding new plan defects each round and never
stops. "Round N found something" is not a stop signal. What is the statistically principled version
of "have we found enough defects to stop looking?"

**Honesty bar applied:** every paper below was downloaded and text-extracted locally (`pdftotext`)
or fetched and quoted. Numbers are quoted from primary sources. Every figure I could NOT trace to a
primary source is explicitly flagged `MIS-CITED` or `UNVERIFIED`. The widely-repeated code-review
numbers (the "200–400 LOC/hour" family) were traced to origin and **two of the three are
misattributed** — see §6.2.

---

## HEADLINE ANSWERS (the three must-answer questions)

### Q1. Can we compute a residual-defect ESTIMATE from overlapping lens findings?

**Yes — the formula is simple, and the inputs are things the loop already has.** The estimator the
software-inspection literature converged on after ~10 years is the **first-order Jackknife for model
Mh (Mh-JK)**:

> **N̂ = D + ((k−1)/k) · f₁**
> **residual = N̂ − D = ((k−1)/k) · f₁**

where `D` = number of distinct defects found by anyone, `f₁` = number of defects found by **exactly
one** lens (singletons), `k` = number of lenses.
Source: Petersson & Wohlin, EASE'99, §2.1 (verbatim: *"N̂ = D + ((k–1)/k) f₁ ... where D denotes the
number of unique defects, N̂ denotes the estimated total number of defects and k denotes the number
of reviewers"*).

The intuition is exactly the thing the dispatch asked for: **singletons are the signal of
undiscovered territory.** If every lens finds the same things (`f₁ = 0`) the estimate says zero
remain → stop. If the lenses find disjoint things (`f₁ = D`) the estimate says ~as many remain as you
found → keep going. This converts "run another lens?" from a vibe into arithmetic.

**But it is invalid for our case.** See Q2 — the assumption violation is not a caveat, it is fatal,
and it fails in the *dangerous* direction (it says STOP when you should not).

### Q2. Honest verdict on the correlated-detector problem

**They break it. Decisively, and in the worst direction. This is not a close call.**

Three independent lines of evidence converge:

1. **The direction of the bias is "underestimate."** Chao et al. (2001), the canonical biostatistics
   tutorial, verbatim: *"Petersen's estimator underestimates the true size if both samples are
   positively dependent. Conversely, it overestimates for negatively dependent samples. A similar
   argument is also valid for a general number of samples... Therefore, a negative (positive) bias
   exists for any estimator which assumes independence."* Positively-correlated lenses ⇒ **the
   estimator tells you fewer defects remain than actually do** ⇒ it fires STOP early. The failure
   mode of the estimator is *precisely* the failure mode you are trying to prevent.

2. **LLM lenses are measurably, heavily positively correlated.** Kohli (arXiv:2605.29800, 28 May
   2026) measured a panel of **9 frontier LLMs from 7 different model families**: mean pairwise phi
   φ̄ = **0.391**, effective votes **n_eff = 2.18** (95% CI [2.07, 2.31]), independence ratio
   **24.2%**. Verbatim: *"the 9 judges effectively provide only about 2 independent votes' worth of
   information. Roughly three-quarters of the panel's nominal independence is lost because the models
   make the same mistakes on the same items."* Note: **7 different families and still only 2.18.**
   Lenses sharing ONE base model are strictly worse than this measurement.

3. **The two requirements are arithmetically incompatible.** Capture-recapture needs **≥4 real
   inspectors** (Briand et al.; below 4 *"no model is sufficiently accurate and underestimation may
   be substantial"*), and biostatistics says the jackknife needs **>5** samples (Otis et al. via
   Chao). Under the Kish design effect `n_eff = k / (1 + (k−1)·φ̄)`, the **asymptotic ceiling** as
   k→∞ is `1/φ̄`. At the measured φ̄ = 0.391 that ceiling is **2.56**.

   > **2.56 < 4.** You cannot reach the estimator's minimum requirement by adding lenses. Ever.
   > Not with 9, not with 100. The ceiling is below the floor.

   I verified this arithmetic reproduces Kohli's reported numbers exactly (my `n_eff` at k=9 =
   2.180 vs. paper's 2.18; my independence ratio 24.2% vs. paper's 24.2%), which validates the
   formula application.

**So: adding an Nth correlated lens does not just have diminishing returns — it cannot in principle
purchase the independence the estimator requires.** The honest verdict is that capture-recapture on
same-base-model LLM lenses is **not a noisy estimator, it is an invalid one**, and its errors point
toward premature stopping.

**What would fix it (and the price):** to get the ceiling above 4 you need **φ̄ ≤ 0.25**; above 5 you
need **φ̄ ≤ 0.20**. And even at φ̄ = 0.20 you need **k = 16 lenses** to reach n_eff = 4. The
prescription for lowering φ̄ is in Chao et al. §4.3 and it is not "prompt them differently" — it is
*"correlation bias due to heterogeneity could be reduced if two different sampling schemes were used
(for example, trapping and then resighting, or netting and then angling)... there is almost no
covariance between the distributions for two distinct samplings."* In our terms: **a genuinely
different KIND of detector** (a test run, a type-checker, a compiler, a human) — not another prompt
against the same weights.

### Q3. Is there a practice-based rule that beats the statistical one because it's cheaper and tamper-proof?

**Yes — and it is supported by the single largest industrial inspection experiment on record,
which happens to have been co-authored by the man who invented capture-recapture for inspections.**

Porter, Siy, Toman & Votta (IEEE TSE 23(6), 1997), an 18-month randomized experiment on a live
commercial product (Lucent 5ESS), randomly assigned **1, 2, or 4 reviewers**:

> **"Team Size (H1). We found no difference in the interval or effectiveness of inspections of two-
> or four-person teams. The effectiveness of one-reviewer teams was poorer than both of the others."**

**The plateau is at TWO, not four.** 1 → 2 buys a real improvement; **2 → 4 buys nothing measurable.**
And re-review didn't help either: *"We found that two two-person teams weren't more effective than
one, two-person team."*

The practice rule that beats the estimator:

> **Fixed lens budget: k = 2 independent lenses of DIFFERENT KIND, one pass. Then freeze.**
> Escalate only on an *external* trigger (a failing test, a named risk, a human request) — never on
> "round N found something."

Why it beats the statistical rule on all three axes:
- **Cheaper:** no estimator, no overlap bookkeeping, no per-round fitting.
- **Tamper-proof:** `k=2, one pass` is a *count*, checkable from outside, with no free parameters.
  An estimator whose stop threshold is a tunable number is exactly the kind of gate that gets
  "calibrated" until it says what the loop wants. `f₁`, moreover, is **directly gameable**: a lens
  that pads its report with unique-but-bogus findings inflates `f₁` and forces "keep going";
  a lens that copies another's findings deflates `f₁` and forces "stop."
- **Not worse:** the estimator can't be valid here anyway (Q2), and Porter measured that the extra
  reviewers it would spend your budget on don't find more defects.

**And the deeper Porter finding says the whole "add another lens" strategy is the wrong axis:**

> *"Although a significant amount of software inspection research has focused on making structural
> changes (team size, number of sessions, etc.) to the process, these changes did not always have the
> intended effect. Consequently, we believe that significant improvements to the inspection process
> are unlikely to come from just reorganizing the process, but rather will depend on the development
> of new defect detection techniques."*

Adding round N+1 is a *structural* change. The largest industrial experiment in the field says
structural changes don't move defect detection. Chao's decorrelation prescription says the same thing
from the statistics side. Kohli's "best single judge matches or outperforms the full panel across all
conditions" says it from the LLM side. **Three literatures, three methods, one answer: change the
detector kind, don't add detectors of the same kind.**

---

## 1. Capture-recapture: the actual estimators and their inputs

### 1.1 The origin and the base formula

Capture-recapture came to software inspection via **Eick, S., Loader, C., Long, D., Votta, L., &
Vander Wiel, S., "Estimating software fault content before coding," Proc. 14th ICSE, Melbourne,
1992, pp. 59–65.** *(Bibliographic details confirmed via the Petersson et al. 2004 survey's reference
list and dblp; I could not open the ACM DL page itself — it returns HTTP 403. Flagged
`SECONDARY-CONFIRMED`, not fabricated: the survey I did open cites it as the first application and
describes its content.)*

The base estimator is **Lincoln-Petersen**, given verbatim in Briand/El Emam/Freimut/Laitenberger
(IESE Report, eq. 1):

> **N̂ = (n₁ · n₂) / m₂**

where `n₁` = defects found by inspector 1, `n₂` = by inspector 2, `m₂` = the overlap (found by both).

Chao et al. (2001) derive it in one line: if the two samples are independent, the recapture rate
`m₂/n₂` should equal the marked rate `n₁/N`, so `m₂/n₂ = n₁/N` ⇒ `N̂ = n₁n₂/m₂`.

### 1.2 The model taxonomy (what assumption each one relaxes)

From Petersson, Thelin, Runeson & Wohlin (JSS 72(2), 2004), Table 1 — verbatim:

| Model | Prerequisites | Estimators |
|---|---|---|
| **M0** | All faults have equal detection probability. All reviewers have equal detection ability. | M0-ML (Otis et al. 1978) |
| **Mt** | All faults equal detection probability. Reviewers **may differ** in ability. | Mt-ML; Mt-Ch (Chao 1989) |
| **Mh** | Faults **may differ** in detection probability. All reviewers equal ability. | **Mh-JK** (Burnham & Overton 1978); Mh-Ch (Chao 1987) |
| **Mth** | **Both** vary. | Mth-Ch (Chao et al. 1992) |

Mnemonic from the survey: *"Mh stands for model with heterogeneity... Mt stands for model with time
response... The trapping occasions mean in the software context different reviewers, and hence Mt
refers to variability between reviewer abilities."*

**Note what is NOT in the table: there is no model for reviewer DEPENDENCE.** The behavioural-response
model (Mb/Mtb) exists in biology but the IESE authors explicitly rejected it for inspections:
*"the estimators for this source of variation depend on the order of trapping occasions (i.e.,
inspectors). Since no ordering of inspectors seems reasonable in the context of inspections, this
estimator is not considered adequate."* And the arXiv dependence paper (1703.03022) notes Mtb *"is
not estimable"* in the two-list case. **The one thing we most need to model is the one thing the
model family doesn't offer.**

### 1.3 The recommended estimator and its inputs

The survey's flat statement of 10 years of accumulated evidence (§4, verbatim):

> 1. **most estimators underestimate,**
> 2. **Mh-JK is the best estimator for software inspections,**
> 3. **Mh-JK is appropriate to use for 4 reviewers and more**
> 4. **DPM is the best curve fitting method, and**
> 5. **capture-recapture estimators can be used together with PBR.**

**Mh-JK first-order (Petersson & Wohlin EASE'99, §2.1):**

> **N̂ = D + ((k−1)/k)·f₁**

**Required inputs — all cheap, all already in the loop's data:**
- `k` — number of lenses
- `D` — number of *distinct, deduplicated* defects found by anyone
- `f₁` — number of defects found by *exactly one* lens
- (higher-order jackknives additionally use `f₂, f₃, ...` = defects found by exactly 2, 3, ... lenses)

**The dedup step is a hidden, load-bearing cost.** The survey is explicit that a human must
adjudicate identity: *"Before the estimation, it is important that the person tries to identify which
faults noted by the individual reviewers may actually be regarded as the same."* If two lenses
describe the same defect differently and you count them as distinct, `f₁` inflates and the estimator
says "keep going." **The estimator's input is not free-text findings; it's an adjudicated defect
identity map.** For LLM lenses that produce prose findings, this adjudication is itself an
error-prone LLM judgment — a second-order correlated-judge problem inside the estimator meant to fix
the first.

**Chao's Mh estimator:** commonly `N̂ = D + f₁²/(2f₂)`. **`UNVERIFIED`** — I could not confirm this
exact closed form from a primary source in this pass. Chao et al. (2001) describes the jackknife as
*"a linear function of the capture frequencies {f₁; f₂; ...; f_t}"* but I did not locate the explicit
Mh-Ch algebra in the fetched texts. Do not cite the `f₁²/(2f₂)` form from this dossier. What IS
verified is its failure condition (§2.3).

### 1.4 Confidence intervals

Thelin et al. (2002), via the survey: **log-normal** intervals are best. *"They conclude that
log-normal distributions are the best alternative when creating confidence intervals."* Vander Wiel
& Votta (1993) recommended the Likelihood interval over Wald's, but *"the Likelihood confidence
interval is too conservative, which often leads to wide intervals."*

---

## 2. The measured bias and the minimum inspector count

### 2.1 The direction is underestimate — consistently

Briand, El Emam, Freimut & Laitenberger, IESE Report ISERN-97-22 (the tech-report version of the work
published as *"A Comprehensive Evaluation of Capture-Recapture Models for Estimating Software Defect
Content,"* IEEE TSE 26(6):518–540, 2000), Results §4.1, verbatim:

> *"(a) Generally, there is an obvious trend towards underestimation. The median values consistently
> underestimate. **Underestimation of the number of remaining defects may be substantially more
> harmful than overestimation since it leads to insufficient effort spent on inspections and poor
> quality artifacts.**"*

The authors flagged the asymmetry themselves: the error direction is the harmful one.

### 2.2 The minimum inspector count — four convergent sources

| Source | Requirement | Verbatim |
|---|---|---|
| **Briand et al. (IESE), abstract** | **≥ 4** | *"When the number of inspectors is below 4, no model is sufficiently accurate and underestimation may be substantial."* |
| **Briand et al., Results (c)** | **≥ 4** | *"For less than 4 inspectors, no model yields satisfactory results."* |
| **Briand et al., Results (e)** | 3 is not usable | *"For 3 inspectors, the Jackknife estimator for Mh performed better in terms of RE and RE variability. However, **the median RE is still large, i.e. >27%.** Therefore, without calibration, this estimator is not likely to be usable in practice."* |
| **Petersson et al. survey** | **4–5** | *"Some studies have shown that at least four to five reviewers should participate in order to make the accuracy acceptable (Briand et al., 2000; Miller, 1999)."* |
| **Otis et al., via Chao et al. 2001** | **> 5** | *"the bias of the jackknife is within a tolerable range if the number of trapping samples is greater than five."* |
| **Chao et al. 2001** | **≥ 5 lists** | *"except for the Rasch model, heterogeneous ecological models are recommended only when at least five lists are available."* |
| **Chao et al. 2001** | **≥ 3 to model dependence AT ALL** | *"at least three samples are required to reasonably estimate any dependence parameters."* |
| **Biology rule of thumb, via IESE** | 5, ideally 7–10 | *"a number of 5 trapping occasions... is recommended as a rule of thumb, though a number of 7 or 10 was deemed more appropriate [Otis; White]. However, **no quantitative justification or evidence is provided.**"* (the IESE authors' own flag) |

**The measured bias number to quote: at 3 inspectors, median relative error > 27% (underestimate).**
At 2, the models are worse than useless — the IESE authors note *"Surprisingly, Mt and Mh performed
even worse than M0, the simplest model"* and that **Mth-Ch cannot produce an estimate at all** at k=2
because *"the estimator has a (k-2) term in one of its denominators."*

Dispersion is as damning as bias: the survey's Figure 1 plots Mh-JK bias across 30 real data sets at
**4 reviewers** and the spread runs roughly **−0.6 to +0.8**. Same estimator, same team size, real
inspection data — the bias on any *individual* artifact is close to a coin flip.

### 2.3 Failure rates (the estimator sometimes returns nothing)

From IESE §4.3:
- *"all estimators fail more often for a low number of inspectors."*
- Mh-JK: *"Failures of the Jackknife estimator can occur for a low number of inspectors and when
  there is no overlap in defects detected amongst the inspectors. However, during our simulations for
  4 or more inspectors, this never occurred."*
- Mh-Ch: *"Chao's estimator for model Mh for 5 inspectors failed approximately 5% of the time... This
  estimator fails when there are no defects that have been detected by exactly two inspectors."*

### 2.4 The two-inspector case, and the most honest paragraph in the literature

El Emam & Laitenberger, *"Evaluating Capture-Recapture Models with Two Inspectors,"* NRC/ERB-1068,
Dec 1999 (Monte Carlo, code-inspection context). They recommend **Mt-Ch** (Chao's estimator, orig.
Chapman) for k=2 — but read their own verdict:

> *"While these results are encouraging... **admittedly, they are not fully satisfying.** First, at a
> conceptual level **taking advantage of bias and lack of precision to make the correct reinspection
> decision seems cumbersome and lacks parsimony.** Furthermore, the decision accuracies, while better
> than the default decision of always passing the document to the next phase, are **frequently below
> the "psychological" threshold of 70% accuracy.**"*

Read that carefully: the k=2 recommendation **works only because two errors cancel**. The estimator
underestimates, and the underestimate happens to produce the right call when effectiveness is above
threshold; its huge error dispersion happens to produce the right call when below. That is not an
estimator, it is a coincidence with a formula attached. And it still lands under 70% decision
accuracy.

Note also this contradicts the earlier empirical study they cite (their ref [10]): *"In that study
the authors concluded that capture-recapture models are not usable with two inspectors."* The survey
attributes the "not suitable" conclusion to **Ekros et al. (1998)**: *"Ekros et al. (1998) state that
capture-recapture models are not suitable to software inspections whereas Miller (2002) found that no
such empirical evidence can be proved."* **The field does not agree with itself at k=2.**

### 2.5 RDA — the evaluation criterion we should steal regardless

El Emam & Laitenberger's most transferable contribution is **Relative Decision Accuracy**:

> **RDA = DA − A_d**

where `DA` = accuracy of decisions made using the estimate, and `A_d` = accuracy of the **default
decision** (in their case, "always pass"). Verbatim: *"It is positive if the CR model decision is
better, zero if they are the same, and negative if the CR model decision is worse than the default
decision."*

Their rationale is exactly our situation: *"If this default decision is the correct one say 90% of
the time and the use of CR model estimates also results in achieving the correct decision 90% of the
time, then using the CR model estimates does not add any value... they are simply an overhead."*

**This is the bar any proposed stop-rule for the loop must clear: it must beat the trivial policy
("always stop after k=2", or "always run exactly 3 rounds") — not merely be "principled."** Absolute
accuracy is not evidence; the delta against the default is.

---

## 3. The correlated-detector problem — the full case

### 3.1 The mechanism, from the canonical source

Chao, Tsay, Lin, Shau & Chao, *"Tutorial in Biostatistics: The applications of capture-recapture
models to epidemiological data,"* **Statistics in Medicine 20:3123–3157 (2001)** — downloaded from
the author's own site, 35 pp. Two distinct dependence sources (§3, verbatim):

> *"(i) **Local dependence** (also called list dependence...) within each individual; conditional on
> any individual, the inclusion in one source has a direct causal effect on his/her inclusion in
> other sources."*
> *"(ii) **Heterogeneity between individuals**; even if the two lists are independent within
> individuals, the ascertainment of the two sources may become dependent if the capture probabilities
> are heterogeneous among individuals. This phenomenon is similar to Simpson's paradox..."*
> *"These two types of dependencies are usually confounded and cannot be easily disentangled in a
> data analysis."*

**Both apply to us, and both push the same direction:**
- **(i) Local dependence** — two lenses sharing a base model have literally correlated inclusion:
  a defect salient to the weights is salient to both. This is direct causal, not incidental.
- **(ii) Heterogeneity** — plan defects are wildly heterogeneous in detectability (a missing null
  check vs. a subtle ordering race). Chao says heterogeneity *alone* induces the same downward bias
  **even if the lenses were locally independent.**

And the derivation of the direction (§3, verbatim):

> *"if the two samples are positively correlated, then those individuals captured in the first sample
> are more easily captured in the second sample. The recapture rate in the second sample tends to be
> larger than the marked rate in the population. That is, we would expect that m₂/n₂ > n₁/N, which
> yields N > n₁n₂/m₂. As a result, **Petersen's estimator underestimates the true size if both samples
> are positively dependent.** Conversely, it overestimates for negatively dependent samples... **a
> negative (positive) bias exists for any estimator which assumes independence.**"*

Confirmed independently by the arXiv dependence paper (1703.03022, §1): *"model Mt (equivalently, the
LP estimator) often fails due to positive dependence among the two lists... which leads to
underestimation of N (Hook and Regal, 1982; Chao et al., 2001)."* And the PLOS One review
(PMC4987016): *"As the dependence between sources increases, the bias of the Lincoln-Petersen
estimator and the Chapman estimator, will increase; the relative bias of the estimators is a function
of the odds ratio."*

### 3.2 The identifiability wall

Chao et al. (2001) §3.2, verbatim:

> *"When only two lists are available, three cells are observable... However, there are **four
> parameters**: N, two mean capture probabilities and a dependence measure. **The data are
> insufficient for estimating dependence unless additional covariates are available. All existing
> methods unavoidably encounter this problem and adopt the independence assumption. This independence
> assumption has become the main weak point in the use of the capture-recapture method for two
> lists.**"*

> *"For the three-list cases, there are seven observable categories and eight parameters... One
> constraint is still needed, yet it is possible to model dependence. Consequently, **at least three
> samples are required to reasonably estimate any dependence parameters.**"*

**You cannot detect your own dependence problem with 2 lenses. The data literally do not contain the
information.** At k=2 you are forced to *assume* the thing that is false.

### 3.3 The measured correlation of LLMs — direct evidence

**(a) Kim, Garg, Peng & Garg, "Correlated Errors in Large Language Models," arXiv:2506.07962
(9 Jun 2025)** — abstract verbatim:

> *"Diversity in training data, architecture, and providers is assumed to mitigate homogeneity in
> LLMs. However, we lack empirical evidence on whether different LLMs differ meaningfully. We conduct
> a large-scale empirical evaluation on over 350 LLMs overall... **We find substantial correlation in
> model errors -- on one leaderboard dataset, models agree 60% of the time when both models err.** We
> identify factors driving model correlation, including shared architectures and providers.
> **Crucially, however, larger and more accurate models have highly correlated errors, even with
> distinct architectures and providers.**"*

The last sentence kills the obvious escape hatch: *you cannot decorrelate by buying a better model
from a different vendor.* Capability itself is a correlating force.

**(b) Kohli, "Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels,"
arXiv:2605.29800 (28 May 2026, cs.CL)** — abstract verbatim:

> *"LLM-as-a-judge panels aggregate votes from multiple models, with the expectation that diverse
> models yield more reliable evaluations... Testing a panel of **9 frontier LLMs from 7 model
> families** on three natural language inference datasets (each with 100 human annotations per item),
> we find that **the 9 judges effectively provide only about 2 independent votes' worth of
> information. Roughly three-quarters of the panel's nominal independence is lost because the models
> make the same mistakes on the same items.** The consequences are stark: the panel's actual accuracy
> falls **8-22 percentage points** short of what independent voting would achieve, and **the best
> single judge matches or outperforms the full panel across all conditions.**"*

Measured values (from the paper body): **φ̄ = 0.391** (σ=0.111, range [0.161, 0.603]);
**n_eff = 2.18** (95% bootstrap CI [2.07, 2.31]); **independence ratio 24.2%**; human annotators by
contrast **n_eff ≈ 4–6**, roughly double.

### 3.4 The arithmetic that settles it

Kish design effect: **n_eff = k / (1 + (k−1)·φ̄)**. As k→∞, **n_eff → 1/φ̄**.

I recomputed this at the paper's φ̄ = 0.391 and it reproduces their published figures exactly
(n_eff(9) = 2.180 vs. reported 2.18; ratio 24.2% vs. reported 24.2%), which confirms I'm applying the
formula as they did:

| k lenses | n_eff at φ̄ = 0.391 |
|---|---|
| 2 | 1.44 |
| 3 | 1.68 |
| 4 | 1.84 |
| 5 | 1.95 |
| 9 | **2.18** ← matches paper |
| 16 | 2.33 |
| 50 | 2.48 |
| 1000 | 2.55 |
| **∞ (ceiling = 1/φ̄)** | **2.56** |

**Requirement: n_eff ≥ 4 (Briand) or > 5 (Otis/Chao). Ceiling: 2.56. The ceiling is below the floor.**

What φ̄ would be needed, and what it would cost:

| φ̄ | ceiling (1/φ̄) | lenses k needed for n_eff = 4 |
|---|---|---|
| 0.05 | 20.0 | 4.7 |
| 0.10 | 10.0 | 6.0 |
| 0.15 | 6.7 | 8.5 |
| 0.20 | 5.0 | **16.0** |
| 0.25 | 4.0 | **impossible** (ceiling = floor) |
| **0.391 (measured, 7 families)** | **2.56** | **impossible** |

**Conclusion: a valid Mh-JK residual estimate over same-base-model LLM lenses is not achievable at
any lens count.** The correct response is not "use more lenses" or "use a better estimator" — it is
**"this instrument does not work on this population."**

### 3.5 The one escape route the literature does endorse

Chao et al. (2001) §4.3, discussing why CCV (their dependence parameter) goes to zero:

> *"Researchers in fishery sciences have suggested that **correlation bias due to heterogeneity could
> be reduced if two different sampling schemes were used** (for example, trapping and then resighting,
> or netting and then angling). This was justified by Seber...; it also could be seen from formula
> (6b) because **there is almost no covariance between the distributions for two distinct
> samplings.**"*

And a second, sharper one:

> *"It follows from (6a) that **the CCV is zero if the capture probabilities for one sample are
> constant** (that is, a random sample); in this case, **no correlation bias arises even if the other
> sample is highly heterogeneous** provided that no local dependence exists."*

**This is the actionable design rule.** You do not need all lenses to be independent. You need **one
lens whose detection probability is flat across defects** — i.e. a detector that doesn't care whether
a defect is "interesting." A test suite, a type checker, a schema validator, a linter, a
property-based checker: these have (approximately) constant capture probability over the defects in
their scope. **Pairing one LLM lens with one mechanical detector is worth more than nine LLM lenses**,
and it is the same conclusion Porter reached from the industrial side and Kohli from the panel side.

Ebrahimi (IEEE TSE 23:529–532, 1997) proposed a dependence-tolerant estimator. Per the survey:
*"Ebrahimi (1997) argues that in the software development environment, some degree of collusion among
reviewers cannot be avoided. He presents an estimator that does not have the restriction of
independence among reviewers... **However, the estimator needs to be evaluated and compared to other
estimators when applied to other data sets.**" `RESEARCH-ONLY` — one paper, never replicated in 29
years, compared only against Mt-ML with "similar results." Not a foundation to build a gate on.

---

## 4. Negative results (recorded so nobody re-researches them)

1. **Votta's own field verdict.** Porter/Siy/Toman/**Votta** 1997 §5.1 — and note Lawrence Votta is a
   co-author of Eick et al. 1992, *the paper that invented capture-recapture for inspections*:
   > *"**our attempts to use statistical methods to estimate the original defect content were
   > unsuccessful.** Future research should look into better estimation methods."*
   The inventor tried it on a real 18-month industrial project and it did not work. This is the single
   most important citation in this dossier.

2. **Ekros et al. (1998)** concluded capture-recapture models are **not suitable** for software
   inspections; **Miller (2002)** found no empirical evidence for that claim. The field is unresolved.
   (Via the Petersson et al. survey; primary not fetched — `SECONDARY-CONFIRMED`.)

3. **Model selection doesn't work.** Survey §3.3: *"Model selection has been evaluated by the use of
   distance measures, chi-square tests and smoothing algorithms (Thelin and Runeson, 2000b) and is
   further analysed by the use of Akaike model selection criterion... **None of these approaches works
   appropriately for the data used in software inspections.**"* You can't rescue it by auto-picking
   the estimator per-round.

4. **The Briand EDPM/Mh-JK selection procedure failed replication.** *"It showed promising results in
   the initial study, but was rejected in the replication by Petersson and Wohlin (1999a)."*

5. **Adoption never happened.** After 10 years and 28 papers, the survey found **exactly one**
   industrial experience report — and *"That paper only uses results from the very first paper on
   capture-recapture in software engineering (Eick et al., 1992) and no later research."* A technique
   with 30+ years of literature and ~1 field adoption is telling you something.

6. **Choice overload — the empirical base for "analysis paralysis" — does not replicate.** See §8.

---

## 5. Topic 2 — Defect discovery curves / reliability growth

### 5.1 The real formulations

From Mičko, Chren & Rossi, *"Applicability of Software Reliability Growth Models to Open Source
Software,"* SEAA'22 (arXiv:2205.02599), Table I — real mean value functions µ(t):

| Model | Type | µ(t) |
|---|---|---|
| **Goel-Okumoto (GO)** | Concave | **a(1 − e^(−bt))** |
| **Goel-Okumoto S-Shaped (GOS)** | S-Shaped | **a(1 − (1 + bt)e^(−bt))** |
| Hossain-Dahiya (HD) | Concave | a(1 − e^(−bt))/(1 + c·e^(−bt)) |
| **Musa-Okumoto (MO)** | **Infinite** | **α·ln(βt + 1)** |
| Duane (DU) | Infinite | α·t^β |
| Weibull (WE) | Concave | a(1 − e^(−bt^c)) |
| Log-Logistic (LL) | S-Shaped | a(λt)^κ / (1 + (λt)^κ) |

Primary citation for MO given as [8] J. D. Musa and K. Okumoto, *"A logarithmic poisson execution
time model for software reliability measurement"* (Proc. 7th ICSE, 1984). **I could not open the Musa
& Okumoto primary** (Springer/ACM both gated); the formula above is quoted from the SEAA'22 table
which cites it. `SECONDARY-CONFIRMED`.

### 5.2 The critical structural distinction for our purposes

> *"**Concave models** – they assume that **the total number of faults in software is finite**, and
> that it is possible to achieve fault-free software in finite time."*

**This matters enormously.** The `a` parameter in GO/GOS **is the total defect count**. So:

> **residual = a − (defects found so far)**, where `a` is the fitted asymptote of the cumulative
> discovery curve.

**This is a residual-defect estimator that needs NO overlap and NO independence between reviewers.**
It only needs the cumulative find-count per round. For a loop that runs rounds against a static
artifact, this is a strictly better-conditioned instrument than capture-recapture: **the correlated-
lens problem does not arise, because the model never assumes the lenses are independent of each
other.** It assumes something different (and also questionable — see below).

**Musa-Okumoto is the wrong choice for us**: it is an **"Infinite"** failure model — no asymptote, so
no residual estimate exists. Musa-Okumoto answers "what is the current failure intensity," not "how
many are left." If someone reaches for "Musa's model" as a stop rule, they want **Goel-Okumoto**
(finite/concave) or its S-shaped variant, not Musa-Okumoto.

The SEAA'22 authors' honest verdict on 88 OSS projects: *"Overall, we found good applicability of
SRGMs to OSS, but with different performance when segmenting the dataset into releases and domains,
**highlighting the difficulty in generalizing**."* And they flag the assumption most likely to break
for us: *"the models assume a **perfect debugging process** in which the detected fault is
immediately removed."* Our loop reviews a **static, unchanged** artifact — nothing is being removed
between rounds — so we are further from the model's premise than OSS is, in a different way. **Flag
this as the open question if this route is pursued.**

### 5.3 The inspection-specific version: the Detection Profile Method (DPM)

Wohlin & Runeson (1998), described in Petersson & Wohlin EASE'99 §2.2, verbatim:

> *"The method is based on plotting the defects versus the number of reviewers that have found a
> specific defect... It is observed that the form of the curve resembled an exponentially decreasing
> function. **The estimate of the remaining number of defects is obtained from where the exponential
> curve is equal to 0.5**... The mean relative error is similar to other methods, but the variance is
> slightly smaller."*

**Procedure:** sort defects by how many lenses found each, descending. Fit `f(x) = a·e^(−bx)`. The
total-defect estimate N̂ is the x where the fitted curve crosses **0.5** (below half a reviewer =
you'd never have seen it).
*(The closed form `N̂ = ln(2a)/b` follows from `a·e^(−bN̂) = 0.5`. That algebra step is mine, not
quoted — flagged as my derivation.)*

Survey verdict: *"DPM is the best curve fitting method"* but *"Mh-JK estimates most accurately"*, and
the derivative-DPM improvement *"is no improvement compared to Mh-JK."* Also, DPM's input is still
per-defect lens-counts, so it inherits the same dedup burden — and, on reflection, the same
correlation problem in disguise: if lenses are correlated, the profile is artificially steep, `a` and
`b` shift, and the crossing point moves in — **underestimate again**. DPM is *less* obviously broken
than Mh-JK, not *un*broken.

### 5.4 The "discovery rate drop" release criterion

Genuinely exists and is applied to inspections: **"Using a Reliability Growth Model to Control
Software Inspection," Empirical Software Engineering** (DOI 10.1023/A:1016396232448). It *"proposes a
reliability growth model and two heuristic linear models for software inspection, which estimate the
likely number of additional defects to be found during reinspection."* **`UNVERIFIED-FULL-TEXT`** —
Springer redirected to an auth wall and academia.edu 403'd; I have the DOI, venue and topical
abstract only, not the model or its accuracy. **This is the most valuable unclosed gap in this
dossier** and the obvious target for a follow-up pass (try the authors' institutional pages).

---

## 6. Topic 3 — Inspection effectiveness and diminishing returns

### 6.1 The reviewer-count plateau — the REAL source and the REAL number

**Porter, A., Siy, H., Toman, C., & Votta, L., "An Experiment to Assess the Cost-Benefits of Code
Inspections in Large Scale Software Development," IEEE Trans. Software Engineering 23(6):329–346,
June 1997.** Downloaded full text. This is the primary source people gesture at when they say
"2–4 reviewers."

Design (abstract, verbatim): *"For each inspection, we randomly assigned three independent variables:
1) **the number of reviewers on each inspection team (1, 2, or 4)**, 2) the number of teams inspecting
the code unit (1 or 2), and 3) the requirement that defects be repaired between the first and second
team's inspections. The reviewers for each inspection were randomly selected without replacement from
a pool of 11 experienced software developers... Our results showed that **these treatments did not
significantly influence the defect detection effectiveness**, but that certain combinations of changes
dramatically increased the inspection interval."*

Results (§3.7, verbatim): *"There was **no difference between two- and four-person inspections**, but
both performed better than one-person inspections."*
And §4: *"Increasing team size does not always improve performance. (**1sX1p < 1sX2p, but 1sX2p =
1sX4p**)"*
And §5.2: *"For practitioners this suggests that **reducing the default number of reviewers from four
to two may significantly reduce effort without increasing interval or reducing effectiveness.**"*

> **The correct statement of the finding is: the plateau begins at 2. "2 to 4 reviewers" is a
> mis-statement of a result that actually says 4 is NO BETTER THAN 2.**

Scale context (§1): *"a typical release of Lucent Technologies' 5ESS switch (0.5M lines of added and
changed code per release on a base of 5M lines) can require roughly 1,500 inspections, each with four,
five, or even more participants."* This was a live, high-stakes, 18-month industrial experiment — not
students.

**Multiple sessions also plateaued** (§5.2): *"We found that **two two-person teams weren't more
effective than one, two-person team.** We found that two two-person (one-person) teams were not more
effective than one four-person (two-person) team... In practice this suggests that **two-session
inspections may not be worth their extra effort.**"*
→ *A second independent review pass over the same artifact did not find more.* This is the closest
thing in the literature to a direct measurement of "should the loop run another round," and the
answer was no.

**The 87% false-positive rate — the number most relevant to "round N found something":**
§3.4: *"Across all 233 preparation reports, **only 13 percent of all issues turn out to be true
defects**."*
§5.3: *"Our data indicate that **about one-half of the issues reported during preparation turn out to
be false positives**, **approximately 35 to 40 percent pertain to nonfunctional style and maintenance
issues.** Finally, **only 13 percent concern defects that will compromise the functionality of the
delivered system.**"*

> **Base rate: a raw "finding" from an individual reviewer is ~13% likely to be a real functional
> defect.** ~50% are outright false positives; ~35–40% are real-but-cosmetic (style/maintenance).
> **"Round N found something" is ~87% likely to be noise or nitpick even with expert human
> reviewers.** This is the single strongest justification in the literature for the dispatch's
> premise that raw round-N-found-something is not a stop signal — and it also quietly corrupts the
> capture-recapture route, since false positives enter `D` and `f₁` and inflate N̂ (the survey
> half-heartedly calls this a *feature*: *"this may not be a big problem since false positives are
> often included in the inspection data, which would increase the estimation result"* — i.e. two
> errors cancelling again).

Porter's interpretive conclusion (§5.4) is the money quote for our loop:
> *"Although a significant amount of software inspection research has focused on making **structural
> changes (team size, number of sessions, etc.)** to the process, **these changes did not always have
> the intended effect.** Consequently, we believe that **significant improvements to the inspection
> process are unlikely to come from just reorganizing the process, but rather will depend on the
> development of new defect detection techniques.**"*

### 6.2 The Cisco / SmartBear numbers — MIS-CITATION AUDIT

Primary source located and downloaded: **"Code Review at Cisco Systems," a chapter of Jason Cohen,
*Best Kept Secrets of Peer Code Review* (SmartBear, 2006), pp. 63–87.** Study: *"In May of 2006 Smart
Bear Software wrapped up a 10-month case study of peer code review in the Cisco MeetingPlace product
group at Cisco Systems, Inc. With **2500 reviews of 3.2 million lines of code written by 50
developers**, this is the largest case study ever done on what's known as a 'lightweight' code review
process."*

| Widely-cited claim | Verdict | Evidence |
|---|---|---|
| **"200–400 LOC per review"** | **PARTLY REAL, distorted** | The study's own finding is about **≤200**: *"Reviewers are most effective at reviewing small amounts of code. **Anything below 200 lines produces a relatively high rate of defects**, often several times the average. After that the results trail off considerably; **no review larger than 250 lines produced more than 37 defects per 1000 lines of code**."* The "400" comes from a *different* sentence about a *hypothesis*, not a finding (see next row). |
| **"200–400 LOC/hour inspection rate"** | **MIS-CITED — not the study's finding** | The study says: *"**Industry experts say** inspection rates should not exceed 200 lines per hour if you want an effective review."* — the Cisco study is **quoting pre-existing folklore, not measuring it.** Their OWN measured result is a different number: *"**Reviewers slower than 400 lines per hour were above average** in their ability to uncover defects. But **when faster than 450 lines/hour the defect density is below average in 87% of the cases.**"* → **The real, measured Cisco threshold is ~400–450 LOC/hour, not 200.** |
| **"Effectiveness collapses after ~60 minutes"** | **UNVERIFIED — asserted, not measured here** | Verbatim: *"Another explanation comes from the **well-established fact** that after 60 minutes reviewers 'wear out' and stop finding additional defects⁶. Given this, a reviewer will probably not be able to review more than 300-400 lines of code before his performance drops."* Footnote 6 points to *"the 'Brand New Information' essay"* — **another essay in the same book**, not an external study. The Cisco data does **not** establish the 60-minute figure; the chapter treats it as given and uses it to *explain* the LOC result. **The "300-400 lines" figure is a downstream inference from the unverified 60-minute premise — this is very likely the true origin of the folkloric "300-400 LOC" number.** |
| **"70–90% defect discovery"** | **MIS-ATTRIBUTED — not in the study** | SmartBear's marketing page ([best-practices-for-peer-code-review](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/)) attributes *"a properly conducted review would find between seven and nine of them"* to *"a SmartBear study of a Cisco Systems programming team."* **That claim does not appear in the Cisco chapter.** It cannot: the study never establishes a total-defect denominator. What it actually reports is *"Our reviews had an average **32 defects per 1000 lines of code**. **61% of the reviews uncovered no defects.**"* — a defect *density*, not a discovery *rate*. **Do not cite "70-90%" to the Cisco study.** |

**Also note the study's own load-bearing assumption**, which it flags honestly in footnote 5: *"we're
tacitly assuming that true defect density is constant over both large and small code changes. That
is, we assume a 400-line change necessarily contains four times the number of defects in a 100-line
change, and thus if defect densities in code review fall short of this the review must be 'less
effective.'"* — **the "large reviews are less effective" conclusion is partly an artifact of this
assumption.** If big changes are genuinely less dense (they give the example of a documented
interface), the effect shrinks.

**Net:** the honest, primary-sourced Cisco numbers are: **≤200 LOC per review; <400 LOC/hour to be
above average; >450 LOC/hour is below average 87% of the time; 32 defects/kLOC; 61% of reviews found
nothing.** The "200-400 LOC/hr, 60 min, 70-90%" package that circulates is a blend of one quoted piece
of folklore, one unverified assertion, and one fabricated attribution.

*(Also worth noting for our purposes: the capture-recapture data sets in the Petersson survey used
code artifacts of **100–300 LOC** and specs of **9–30 pages** — the same order of magnitude. Nobody
has validated any of this at the size of a real plan document.)*

### 6.3 Fagan

Fagan (1976) is the origin of formal inspection and is cited as such by every source here (*"It was
first described by Fagan (1976)"* — Petersson et al. survey §1). **I did not fetch Fagan's primary
paper this pass** (IBM Systems Journal 15(3):182–211, 1976). `SECONDARY-CONFIRMED` — cited
consistently by five sources I did open; no numeric claim in this dossier depends on it.

### 6.4 Baseline effectiveness

*"A recent literature review found that, on average, **software inspections find only 57% of defects
in code and design documents**"* — El Emam & Laitenberger 1999, §1, citing their ref [8] = **Briand,
El Emam, Laitenberger & Fussbroich, "Using Simulation to Build Inspection Efficiency Benchmarks for
Development Projects," ICSE'98, pp. 340–349.** They use **0.57 (average)** and **0.70 (best in class)**
as the effectiveness thresholds in their simulation. `SECONDARY-CONFIRMED` (I have El Emam quoting it
with a full citation; I did not open the ICSE'98 paper itself).

> **Sobering frame:** even good human inspection leaves ~43% of defects in. A stop rule that implies
> "we found them all" is not describing any process ever measured.

---

## 7. Topic 4 — Scope freeze / stop-planning practice (real definitions)

### 7.1 Last Responsible Moment (LRM)

Definition, verbatim: **"Delay commitment until the last responsible moment, that is, the moment at
which failing to make a decision eliminates an important alternative."**
Attribution: **Mary & Tom Poppendieck, *Lean Software Development: An Agile Toolkit*.**
(Verified via agilepainrelief.com's glossary, which quotes the definition and attributes it to the
Poppendiecks. The concept's earlier root in Lean Construction is **not** credited by that source and I
did not confirm it — `UNVERIFIED` on the construction-origin claim.)

The operative tension, also quoted: *"When we delay too long, we lose the ability to make the decision
altogether."* Counterpoint recorded: **Rebecca Wirfs-Brock** argues for the *"most responsible
moment"* rather than *"nervously delaying until an alternative is about to disappear."*

**Why LRM is the wrong tool for our problem:** LRM is about *when to commit a decision you must
eventually make*, not *when to stop looking for defects*. It has no stopping rule for search. Worse,
misapplied, LRM is an *argument for the pathology* — "we can always review one more round, we haven't
hit the LRM yet." **The loop's failure mode is LRM taken literally.**

### 7.2 Set-Based Concurrent Engineering (SBCE)

**Ward, A., Liker, J. K., Cristiano, J. J., & Sobek, D. K. II, "The Second Toyota Paradox: How
Delaying Decisions Can Make Better Cars Faster," MIT Sloan Management Review 36 (Spring 1995),
pp. 43–61.** Verbatim from the article page:

> *"while in most cases CE seeks to **freeze specifications quickly**, Toyota's engineers and managers
> try to **delay decisions and provide their suppliers with hard specifications very late in the
> process.**"*
> *"while conventional concurrent engineering reduces the number of prototypes, **Toyota's suppliers
> seem to multiply prototypes, in some cases to an apparently absurd degree.**"*

The mechanism: designers *"explicitly communicate and think about **sets** of design alternatives...
They **gradually narrow these sets by eliminating inferior alternatives** until they come to a final
solution."*

**Direct relevance:** SBCE is the closest legitimate ancestor of "run multiple lenses" — but note the
*shape*. Toyota **converges by elimination against real tests**, on a **schedule**. The sets narrow
monotonically and the process terminates because narrowing is the only permitted move. A review loop
that *expands* the finding set every round is not doing SBCE; it is doing the opposite. **SBCE's stop
rule is "the set has one member left," which requires an elimination mechanism — the loop has none.**

### 7.3 YAGNI

**Martin Fowler, "Yagni," martinfowler.com, 26 May 2015.** Four costs of building presumptive
features: **cost of build, cost of delay, cost of carry, cost of repair.** Crucial scoping constraint,
verbatim:

> *"**Yagni only applies to capabilities built into the software to support a presumptive feature, it
> does not apply to effort to make the software easier to modify.**"*

Refactoring, self-testing code, and continuous delivery are **explicitly exempt**. So YAGNI is *not*
a licence to skip verification work — the naive reading ("don't over-review, YAGNI") is a misuse.
YAGNI argues against building speculative *capability*, not against checking what you built.

### 7.4 Cost of Delay (Reinertsen)

**Donald G. Reinertsen, *The Principles of Product Development Flow: Second Generation Lean Product
Development* (2009).** I could not open the book text; the strongest primary I fetched is Reinertsen
**in his own words** in a Lean Magazine interview (20 Feb 2012):

- On why intuition fails: *"the intuition of members of the same team typically **differs by 50 to 1**"* —
  which is why CoD must be *calculated*, not felt.
- On what happens when teams actually compute it: *"they are surprised at **how large the number is**.
  Second, they are surprised at **how little time it takes to do the calculation**. Third, they are
  surprised at **how much consensus they can reach** on the value."*
- On prioritisation: *"prioritize projects with the **highest cost of delay per unit of scarce
  resource consumed**."*

The famous *"if you only quantify one thing, quantify the cost of delay"* is widely attributed to
Reinertsen and is consistent with the interview, but **I could not verify that exact sentence against
the book — `UNVERIFIED` as a verbatim quote.** The *substance* is verified.

**This is the framing that actually resolves our problem.** The loop's question is posed as an
epistemics question ("have we found enough?") but it is an **economics** question:

> **Continue iff: (P(defect remains) × cost of that defect escaping) > (cost of another round +
> cost of delay incurred by that round).**

Reinertsen's point is that the right-hand term is real, large, and almost never quantified — so it
gets treated as zero, and then "one more round" is *always* justified. **A loop that never stops is
a loop that has implicitly set its cost of delay to zero.** You don't need a residual-defect
estimator to fix that; you need a non-zero delay cost. That is cheaper *and* tamper-proof, because
it's a constant you set once, outside the loop.

### 7.5 Change control boards / Definition of Done / Definition of Ready

`NOT RESEARCHED THIS PASS` — deprioritised in favour of the capture-recapture core, per the
dispatch's ranking. Named in the brief; no primary source fetched; **no claims made.** Flagged for a
follow-up if wanted. (Expected sources: CMMI/IEEE 1028 for CCB; Scrum Guide for DoD; DoR has no
authoritative definition and is contested — worth checking before relying on it.)

### 7.6 The one operational stop-procedure the literature does offer

Petersson et al. (2004) §5 exists precisely because *"the application part was found to be weak"* —
they invented a process to fill the gap. Decision point **A** (after individual review, before
meeting), five options, *"listed from the most negative to the most positive"*:

- **A1.** Terminate the inspection, send the artefact back — *"the artefact was not really ready for
  inspection."* ← **note this option: too many findings means the ARTEFACT is broken, not that you
  should review harder.**
- **A2.** Hold a meeting (the normal path).
- **A3.** Assign additional reviewers — *"This decision indicates that there is an uncertainty in
  terms of the quality and that more opinions are needed. **This basically means postponing the
  decision**, and wait for more input."*
- **A4.** Continue development without a meeting — *"the artefact is viewed as having good enough
  quality and the estimated number of faults is sufficiently low."*

With the standing caveat (§5): *"since the estimator has a tendency to underestimate, **it is
recommended to keep track of the actual behaviour so that any systematic estimation error can be
compensated in the long run.** This means keeping track of **historical data** in terms of estimation
accuracy."* — i.e. even the survey's own authors say **the estimator is only usable if you calibrate
it against ground truth over many runs.** We have no ground truth. **That closes the door.**

**A1 is the most under-appreciated option in this whole dossier.** The loop's actual situation —
"every round finds new defects, forever" — maps onto A1, not A3. In the inspection literature, an
artefact that keeps yielding defects is a **rejected artefact**, not an under-reviewed one. The
correct action is *send the plan back / rewrite it*, not *review it again*.

---

## 8. Topic 5 — Analysis paralysis: named, but empirically thin

**Verdict: this is the weakest-supported item in the brief, and the dispatch's instinct to demand
empirics is exactly right — the popular empirical basis fails to replicate.**

The canonical "too much analysis hurts" evidence is **choice overload**, popularised by **Iyengar &
Lepper (2000)** (the 6-vs-24 jams supermarket study). The meta-analysis:

**Scheibehenne, B., Greifeneder, R., & Todd, P. M., "Can There Ever Be Too Many Options? A
Meta-Analytic Review of Choice Overload," Journal of Consumer Research 37(3):409–425 (Oct 2010).**
Downloaded from the first author's site. Abstract, verbatim:

> *"In a meta-analysis of **63 conditions from 50 published and unpublished experiments (N = 5,036)**,
> we found a **mean effect size of virtually zero** but considerable variance between studies."*

**So: "more options → paralysis" does not survive meta-analysis.** Anyone citing the jam study to
justify a stop rule is citing a result with a null pooled effect. `MIS-CITED` if used that way.

"Analysis paralysis" as a software antipattern is real as a *named pattern* (AntiPatterns, Brown et
al. 1998 — `NOT FETCHED`, no claim made) and is described in Wikipedia/DevIQ-tier sources, but **I
found no controlled empirical study measuring over-analysis harm in software projects.** If such a
study exists I did not find it in this pass.

**Honest conclusion: do not ground the loop's stop rule in "analysis paralysis."** It is a folk
label with a null-effect empirical base. The defensible grounding is the *economic* one (§7.4) and
the *measured plateau* one (§6.1) — both of which are real, primary-sourced, and quantitative.

---

## 9. What this means for the loop — recommendation

**The dispatch asked for the principled version of "have we found enough defects to stop looking?"
The principled answer, honestly derived, is: on same-base-model LLM lenses, that question is not
answerable by any estimator in this literature, and the reason is structural, not fixable by tuning.**

Ranked recommendations:

**1. Adopt the practice rule, not the estimator. `IMPLEMENTABLE NOW`**
`k = 2 lenses of different KIND, one pass, then freeze.` Grounded in Porter's `1sX2p = 1sX4p` and
`2sX2p = 1sX2p`. Tamper-proof (a count, not a threshold), zero marginal cost, and no worse than the
alternative since the estimator is invalid here.

**2. Make the delay cost explicit and non-zero. `IMPLEMENTABLE NOW`**
Per Reinertsen. A loop with an implicit CoD of zero *cannot* terminate — "one more round" always
wins. Fix the loop's *objective*, not its *estimator*. This alone probably resolves the reported
symptom.

**3. Treat "round N found new defects, again" as an A1 signal, not an A3 signal. `IMPLEMENTABLE NOW`**
Per Petersson et al. §5. Persistent yield = **the artefact is not ready**; send it back / rewrite it.
Reviewing a broken plan more times is the one action the literature explicitly does *not* recommend.
Consider a rule: *if rounds 1..N all yield material defects, stop reviewing and rewrite the plan.*

**4. Spend the lens budget on KIND-diversity, not COUNT. `TESTABLE`**
Chao's *"two different sampling schemes"* + *"CCV is zero if the capture probabilities for one sample
are constant"* + Porter's *"new defect detection techniques"* + Kohli's *"best single judge matches or
outperforms the full panel"* — four sources, one prescription. One LLM lens + one mechanical detector
(tests / types / schema / property checks) > N LLM lenses.

**5. If anyone wants a number anyway, measure φ̄ first — it's cheap and it's the kill-switch.
`TESTABLE`**
Before computing any N̂, compute the **mean pairwise correlation φ̄ across lenses** (Kish) and/or
**Chao's sample coverage** `Ĉ = 1 − (1/t)·Σ(S_k/n_k)` — *"the average (over three lists) of the
fraction of cases found more than once... the complement of the fraction of singletons."*
- Kill-switch A: **if `1/φ̄ < 4`, stop — the estimator cannot be valid at any lens count.** (At the
  published φ̄ = 0.391, `1/φ̄` = 2.56, so this fires immediately. Expect it to fire.)
- Kill-switch B: Chao's usability floor — *"the estimated sample coverage should be at least 55 per
  cent"* (their ref [29] simulations). Below that, *"the undercount cannot be measured accurately due
  to insufficient overlap."*
- Also per Chao: **you need ≥3 lenses to estimate dependence at all.** At k=2 you cannot even run the
  diagnostic.
**Note the useful asymmetry: measuring φ̄ is cheap and decisive, while N̂ is expensive and invalid.
If we do any statistics here, do this one.**

**6. Do not build capture-recapture into a gate. `REJECT`**
Reasons, all sourced: ceiling below floor (§3.4); underestimates in the dangerous direction (§2.1);
needs ≥4–5 truly independent lenses we cannot obtain (§2.2); `f₁` is directly gameable by a lens that
pads or copies (§Q3); requires human dedup adjudication as input (§1.3); requires historical
ground-truth calibration we don't have (§7.6); ~1 industrial adoption in 30 years (§4.5); and the
method's own co-inventor reported it failed in the field (§4.1).

**7. Open gap worth one more pass. `RESEARCH`**
*"Using a Reliability Growth Model to Control Software Inspection"* (Empirical Software Engineering,
DOI 10.1023/A:1016396232448) — the one paper that directly targets "estimate additional defects
findable by re-inspection." Blocked by paywall this pass. The **Goel-Okumoto route (§5.2) is the only
residual estimator found that does not assume inter-lens independence**, which makes it the sole
statistical candidate not already killed by §3. Its own suspect assumption (perfect/immediate
debugging) needs checking against our static-artefact case before it's trusted.

---

## 10. Source index — verification status

**Downloaded, text-extracted, quoted (primary):**

| # | Source | Status |
|---|---|---|
| 1 | [Petersson, Thelin, Runeson & Wohlin, *Capture-recapture in Software Inspections after 10 Years Research*, J. Systems & Software 72(2):249–264, 2004](https://wohlin.eu/jss04-1.pdf) | ✅ 18pp, full |
| 2 | [Briand, El Emam, Freimut & Laitenberger, *Quantitative Evaluation of Capture-Recapture Models to Control Software Inspections*, IESE-Report / ISERN-97-22 (→ IEEE TSE 26(6):518–540, 2000)](https://edocs.tib.eu/files/e001/254163734.pdf) | ✅ 9pp, full |
| 3 | [El Emam & Laitenberger, *Evaluating Capture-Recapture Models with Two Inspectors*, NRC/ERB-1068, Dec 1999](https://www.ehealthinformation.ca/web/default/files/wp-files/1068.pdf) | ✅ full |
| 4 | [Petersson & Wohlin, *Evaluation of using Capture-Recapture Methods on Software Review Data*, EASE'99](https://www.wohlin.eu/ease99.pdf) | ✅ full (Jackknife + DPM formulas) |
| 5 | [Wohlin, Petersson, Höst & Runeson, *Defect Content Estimation for Two Reviewers*, ISSRE 2001, pp. 340–345](https://wohlin.eu/issre01.pdf) | ✅ downloaded (identity confirmed; used lightly) |
| 6 | **[Chao, Tsay, Lin, Shau & Chao, *Tutorial in Biostatistics: The applications of capture-recapture models to epidemiological data*, Statistics in Medicine 20:3123–3157, 2001](https://sites.google.com/view/chao-lab-website/publication)** (author's own PDF copy, linked from that page) | ✅ 35pp, full — **the dependence result** |
| 7 | **[Porter, Siy, Toman & Votta, *An Experiment to Assess the Cost-Benefits of Code Inspections in Large Scale Software Development*, IEEE TSE 23(6):329–346, 1997](https://users.ece.utexas.edu/~perry/education/SE-Intro/porter-tse23.pdf)** | ✅ full — **the reviewer plateau + 13% + Votta's negative result** |
| 8 | **[Cohen (SmartBear), *Code Review at Cisco Systems*, ch. of *Best Kept Secrets of Peer Code Review*, 2006, pp. 63–87](https://static0.smartbear.co/support/media/resources/cc/book/code-review-cisco-case-study.pdf)** | ✅ 25pp, full — **mis-citation audit** |
| 9 | [Scheibehenne, Greifeneder & Todd, *Can There Ever Be Too Many Options? A Meta-Analytic Review of Choice Overload*, J. Consumer Research 37(3):409–425, 2010](https://scheibehenne.com/ScheibehenneGreifenederTodd2010.pdf) | ✅ 10pp, full |
| 10 | [Chatterjee & Bhuyan, *On the estimation of population size from a post-stratified two sample capture-recapture data under dependence*, arXiv:1703.03022](https://arxiv.org/pdf/1703.03022) | ✅ full (dependence direction; Hook & Regal 1982 cite) |
| 11 | [Mičko, Chren & Rossi, *Applicability of Software Reliability Growth Models to Open Source Software*, SEAA'22, arXiv:2205.02599](https://arxiv.org/pdf/2205.02599) | ✅ full (SRGM table) |

**Fetched and quoted (primary, web):**

| # | Source | Status |
|---|---|---|
| 12 | **[Kohli, *Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels*, arXiv:2605.29800, 28 May 2026 (cs.CL)](https://arxiv.org/abs/2605.29800)** | ✅ abs + html; **φ̄=0.391, n_eff=2.18, 24.2%** — arithmetic independently reproduced |
| 13 | **[Kim, Garg, Peng & Garg, *Correlated Errors in Large Language Models*, arXiv:2506.07962, 9 Jun 2025](https://arxiv.org/abs/2506.07962)** | ✅ abstract verbatim; 350+ LLMs, 60% co-error agreement |
| 14 | [Ward, Liker, Cristiano & Sobek, *The Second Toyota Paradox*, MIT Sloan Mgmt Review 36:43–61, Spring 1995](https://sloanreview.mit.edu/article/the-second-toyota-paradox-how-delaying-decisions-can-make-better-cars-faster/) | ✅ quoted |
| 15 | [Fowler, *Yagni*, 26 May 2015](https://martinfowler.com/bliki/Yagni.html) | ✅ quoted |
| 16 | [Reinertsen interview, *Cost of Delay*, Lean Magazine, 20 Feb 2012](http://leanmagazine.net/lean/cost-of-delay-don-reinertsen/) | ✅ quoted (Reinertsen's own words) |
| 17 | [Last Responsible Moment glossary (quotes Poppendieck definition)](https://agilepainrelief.com/glossary/last-responsible-moment/) | ✅ definition verbatim; secondary for attribution |
| 18 | [Rossi et al., *Capture-Recapture Estimators in Epidemiology...*, PLOS One 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4987016/) | ✅ dependence↔odds-ratio bias |
| 19 | [SmartBear, *Best Practices for Peer Code Review* (the mis-attribution's origin)](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/) | ✅ fetched — 70-90% claim attributed to Cisco study; **claim absent from that study** |
| 20 | [Zhang, Rong & Zhang, *An empirical study on independence-driven data selection for improving capture-recapture estimation*, EASE 2016](https://dl.acm.org/doi/10.1145/2915970.2915991) | ⚠️ **identity confirmed via dblp** (authors/year/venue); ACM 403 — full text NOT read. Search-snippet claim (removing dependent inspectors improves accuracy; *"more inspectors, higher accuracy" is not always valid*) is **UNVERIFIED**; supports §3 but no claim rests on it |

**Named in brief, NOT verified — no claims made:**
- Eick, Loader, Long, Votta & Vander Wiel, ICSE 1992 — `SECONDARY-CONFIRMED` (bibliographic details
  from survey ref list + dblp; ACM DL 403). Existence and role certain; contents not read.
- Vander Wiel & Votta 1993 (TSE) — `SECONDARY-CONFIRMED` via survey.
- Musa & Okumoto 1984 — `SECONDARY-CONFIRMED`; formula from SEAA'22 table.
- Fagan 1976 — `SECONDARY-CONFIRMED`; no numeric claim depends on it.
- Ekros et al. 1998; Miller 1999/2002; Briand et al. 1997/1998; Thelin et al. 2002 — via survey only.
- *Using a Reliability Growth Model to Control Software Inspection* — `UNVERIFIED-FULL-TEXT`, paywalled.
- Reinertsen, *Principles of Product Development Flow* (book) — `UNVERIFIED` for the exact
  "quantify one thing" sentence; substance verified via interview.
- Change control boards / DoD / DoR — `NOT RESEARCHED`.
- Brown et al., *AntiPatterns* (1998) — `NOT FETCHED`.
- Chao Mh closed form `N̂ = D + f₁²/(2f₂)` — `UNVERIFIED`; **do not cite from this dossier.**
- Iyengar & Lepper (2000) primary — not fetched; only the meta-analysis that nulls it (#9) is quoted.
- Lean Construction Institute as LRM origin — `UNVERIFIED`.

**Tooling note:** WebFetch returns raw binary on arXiv PDF URLs and 403s on ACM DL / Springer /
academia.edu. Every PDF above was retrieved with `curl -sL` to the scratchpad and extracted with
`pdftotext -layout`. Beware `curl -o` in this environment: cwd resets between bash calls, so relative
output paths land in the repo, not the scratchpad — use absolute paths.
