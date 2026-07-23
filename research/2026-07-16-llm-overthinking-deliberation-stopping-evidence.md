# Does more agent deliberation degrade outcomes? Evidence + stopping mechanisms

**Mode D domain research** — dispatched 2026-07-16
**Researcher:** Claude Opus 4.8
**Triggering incident:** an orchestrator ran a read-only planning task for 5.5 hours, spawned/closed
many sub-agents, and grew a plan to 1,452 lines / 107 acceptance criteria — "certification" displaced
shipping as the deliverable.

**Verification standard used:** every paper below was downloaded as a PDF from `arxiv.org/pdf/<id>`,
extracted with `pdftotext`, and read in the extracted text. Titles, author lists, arXiv IDs, dates and
every quoted number were taken from the extracted primary text, **not** from search snippets or
abstract-page summaries. Anything I could not confirm this way is marked **UNVERIFIED**. Where a number
is my own arithmetic or inference rather than the paper's stated claim, it is marked **[DERIVED]**.

---

## 0. Bottom line up front

**Q1 — Is there hard evidence more deliberation makes outcomes WORSE (not just slower)?**
**Yes, but not for the reason the question implies.** The volume of deliberation is *not* the harmful
variable — the strongest paper on "overthinking" found that *more* reasoning tokens *reduced* its own
overthinking metric. What is causally established as harmful is narrower and matches this incident
almost exactly:

1. deliberation that **substitutes for contact with the environment** (Cuadron et al. 2502.08235);
2. **iterated self-review without an external oracle** — measurably monotone-degrading (Huang et al. 2310.01798);
3. **optimization pressure against an imperfect proxy** — degrades *specifically on easy problems* (Snell et al. 2408.03314);
4. **taking the LAST state of a refinement loop rather than the BEST** — 38% of correct answers get
   converted back to incorrect (Snell et al. 2408.03314).

A read-only, 5.5-hour, 107-criteria planning loop instantiates all four at once.

**Q2 — Does a "find problems in this plan" reviewer have a false-positive floor?**
**Yes, and it is measured.** OpenAI's own purpose-built code critic: *"the probability of catching a bug
increases with the number of claims that a critique makes… models which hallucinate bugs more often are
also more likely to catch human inserted and previously detected bugs"* — and their stated limitation:
*"Although our method reduces the rate of nitpicks and hallucinated bugs, their absolute rate is still
quite high."* At project scale (Jan 2026), the **best-performing** LLM bug detector still runs an
**85.3% false discovery rate**. **Therefore "round N found something" is the expected output of a
high-recall critic pointed at any artifact, and carries near-zero evidence that the artifact is flawed.
It cannot function as a continue signal.**

**Q3 — What stop mechanisms have actual reported results?**
Ranked in §4. The best-evidenced intervention is not a stop rule at all — it is **grounding the loop in
execution** (+18.6 points, and it cut the overthinking score by 57%). The best-evidenced *stop* rule is
**fixed budget + select-best-across-trajectory, never last-state**.

**The single biggest honesty flag in this dossier:** nearly all of this evidence comes from tasks with a
**verifiable answer** (math, SWE-bench, HumanEval). The incident task — "is this plan good enough" — has
**no ground truth**. See §5; this makes the situation worse, not better, but the extrapolation is mine,
not a measured result.

---

## 1. Q1 — Does more deliberation degrade outcomes?

### 1.1 The strongest evidence FOR: iterated self-review degrades, monotonically

**"Large Language Models Cannot Self-Correct Reasoning Yet"** — Jie Huang, Xinyun Chen, Swaroop Mishra,
Huaixiu Steven Zheng, Adams Wei Yu, Xinying Song, Denny Zhou (Google DeepMind + UIUC).
arXiv:**2310.01798**v2, 14 Mar 2024. ICLR 2024. https://arxiv.org/abs/2310.01798

This is the strongest single piece of evidence, because it isolates the variable: same model, same task,
the *only* change is rounds of self-review, and it reports the round-by-round number.

**Table 3 — intrinsic self-correction (no oracle), verbatim:**

| Model | Method | # calls | GSM8K | CommonSenseQA | HotpotQA |
|---|---|---|---|---|---|
| GPT-3.5 | Standard Prompting | 1 | 75.9 | 75.8 | 26.0 |
| GPT-3.5 | Self-Correct (round 1) | 3 | 75.1 | 38.1 | 25.0 |
| GPT-3.5 | Self-Correct (round 2) | 5 | 74.7 | 41.8 | 25.0 |
| GPT-4 | Standard Prompting | 1 | 95.5 | 82.0 | 49.0 |
| GPT-4 | Self-Correct (round 1) | 3 | 91.5 | 79.5 | 49.0 |
| GPT-4 | Self-Correct (round 2) | 5 | 89.0 | 80.0 | 43.0 |

**Table 4 — verbatim:**

| Model | Method | # calls | GSM8K | CommonSenseQA |
|---|---|---|---|---|
| GPT-4-Turbo | Standard | 1 | 91.5 | 84.0 |
| GPT-4-Turbo | Self-Correct (round 1) | 3 | 88.0 | 81.5 |
| GPT-4-Turbo | Self-Correct (round 2) | 5 | 90.0 | 83.0 |
| Llama-2 | Standard | 1 | 62.0 | 64.0 |
| Llama-2 | Self-Correct (round 1) | 3 | 43.5 | 37.5 |
| Llama-2 | Self-Correct (round 2) | 5 | 36.5 | 36.5 |

GPT-4 on GSM8K: **95.5 → 91.5 → 89.0** (−6.5 points across 2 review rounds, monotone).
Llama-2 on GSM8K: **62.0 → 43.5 → 36.5** (−25.5 points). Not noise — a collapse.

Paper's own summary: *"We observe that, after self-correction, the accuracies of all models drop across
all benchmarks."* And on prompt variants: *"as shown in Tables 5 and 6, without the use of oracle labels,
self-correction consistently results in a decrease in performance."*

**The mechanism, verbatim:**
> "For GSM8K, 74.7% of the time, GPT-3.5 retains its initial answer. Among the remaining instances, the
> model is more likely to modify a correct answer to an incorrect one than to revise an incorrect answer
> to a correct one. **The fundamental issue is that LLMs cannot properly judge the correctness of their
> reasoning.**"

**The decisive contrast — the oracle is doing all the work.** Table 2, *with* oracle labels (ground truth
used only to decide *when to stop*):

| Model | Method | GSM8K | CommonSenseQA | HotpotQA |
|---|---|---|---|---|
| GPT-3.5 | Standard | 75.9 | 75.8 | 26.0 |
| GPT-3.5 | Self-Correct (Oracle) | 84.3 | 89.7 | 29.0 |
| GPT-4 | Standard | 95.5 | 82.0 | 49.0 |
| GPT-4 | Self-Correct (Oracle) | 97.5 | 85.5 | 59.0 |

GPT-3.5/GSM8K: **75.9 → 84.3 with an oracle stop signal; 75.9 → 74.7 without.** Identical loop. The only
difference is whether something outside the model decides when to stop. The authors note the catch:
*"If we are already in possession of the ground truth, there seems to be little reason to deploy LLMs
for problem-solving."*

> **Read for the incident:** a review loop whose stop signal comes from the reviewers themselves is the
> no-oracle column. The no-oracle column goes down.

### 1.2 Second-strongest FOR: more optimization against an imperfect verifier degrades — *on easy tasks*

**"Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters"** —
Charlie Snell, Jaehoon Lee, Kelvin Xu, Aviral Kumar (UC Berkeley, Google DeepMind).
arXiv:**2408.03314**v1, 6 Aug 2024. https://arxiv.org/abs/2408.03314

Verbatim:
> "As shown in Figure 3 (left), with smaller generation budgets, beam search significantly outperforms
> best-of-N. However, as the budget is scaled up, these improvements greatly diminish, with **beam search
> often underperforming the best-of-N baseline.**"

> "On the easy questions (levels 1 and 2), the stronger optimizer of the two approaches, beam search,
> **degrades performance as the generation budget increases**, suggesting signs of exploitation of the PRM
> signal. In contrast, on the harder questions (levels 3 and 4), beam search consistently outperforms
> best-of-N."

The stated mechanism is Goodhart's law, measured:
> "we might expect that on the easy questions, the verifier will make mostly correct assessments of
> correctness. Therefore, by applying further optimization via beam search, we only **further amplify any
> spurious features learned by the verifier, causing performance degredation**." *(sic — "degredation")*

Observed pathologies of over-optimization: *"search causes the model to generate low-information
repetitive steps at the end of a solution"* and *"over-optimizing search can result in overly short
solutions consisting of just 1-2 steps."*

> **Read for the incident:** 107 criteria is a proxy for "good plan," and each review round is more
> optimization pressure against that proxy. Snell's result says this amplifies the *criteria's* spurious
> features, and that the damage is **worst when the task was easy enough that the verifier was already
> mostly right** — i.e. exactly when a heavyweight certification loop is least warranted.

### 1.3 Third: the last state of a refinement loop is worse than the best state

Same paper (Snell et al. 2408.03314), on their revision model — a model **fine-tuned specifically to
revise**:
> "around **38% of correct answers get converted back to incorrect ones** with our revision model using a
> naïve approach. Therefore, we employ a mechanism based on sequential majority voting or verifier-based
> selection to select the most correct answer from the sequence of revisions."

So even a purpose-trained reviser destroys correct work ~38% of the time if you take its **final** output.
The fix is not fewer revisions — it is **selection across the trajectory**.

> **Read for the incident:** the 1,452-line plan is the *last* state of a 5.5-hour refinement loop. This
> result says the last state is systematically not the best one, and that no amount of additional
> reviewing fixes that — only selection does.

### 1.4 Fourth: agentic overthinking correlates with failure

**"The Danger of Overthinking: Examining the Reasoning-Action Dilemma in Agentic Tasks"** —
Alejandro Cuadron, Dacheng Li, Wenjie Ma, Xingyao Wang, Yichuan Wang, Siyuan Zhuang, Shu Liu,
Luis Gaspar Schroeder, Tian Xia, Huanzhi Mao, Nicholas Thumiger, Aditya Desai, Ion Stoica, Ana Klimovic,
Graham Neubig, Joseph E. Gonzalez (UC Berkeley, ETH Zurich, UIUC, CMU).
arXiv:**2502.08235**v1, 12 Feb 2025. https://arxiv.org/abs/2502.08235
Code/data: https://github.com/AlexCuadron/Overthinking

**"Analysis Paralysis" is a near-verbatim description of the incident:**
> "**Analysis Paralysis**: the agent spends excessive time planning future steps while making minimal
> environmental progress… Rather than addressing immediate errors, they construct intricate plans that
> often remain unexecuted, **leading to a cycle of planning without progress**."

The other two patterns: **Rogue Actions** (chains of interdependent actions issued without waiting for
feedback) and **Premature Disengagement** (terminating on internal prediction rather than environmental
validation).

**The headline regression (Figure 1):**
- Reasoning models: R² = 0.892, p = 0.000, β₁ = **−7.894**
- Non-reasoning models: R² = 0.839, p = 0.010, β₁ = **−15.938**

**CRITICAL METHODOLOGICAL CAVEAT — I checked this in the figure itself.** The regression's data points are
**models, not trajectories**. The labelled points are o1_high_FC, Sonnet 3.5 FC, DS-R1, o1_high, GPT-4o-FC,
o1_low, o1-mini, Stratos-32B, Sky-T1-NR, DS-R1-32B, QwQ, GPT-4o-mini, Qwen2.5-32B, Sky-T1-R, DS-V3 —
~15 models split across two lines, so **each line is fit on roughly 7–8 points**. This is an *ecological*
(between-model) correlation, and the paper itself reports that smaller/weaker models overthink more
(§5.3), so it is **confounded with model capability**. High R² on ~7 points does not establish that
overthinking *causes* failure. Do not cite the R² as causal evidence.

**The within-model evidence is the real result** (§6.2, Figure 3) — same model, o1 with low reasoning
effort, sample K trajectories and select by overthinking score:

| Configuration | Resolve rate | Cost |
|---|---|---|
| o1, high reasoning effort (1 sample) | **29.1%** | $1,400 |
| o1, low reasoning effort (1 sample) | **21.0%** | $400 |
| Lowest-Overthinking@2 (low effort) | **27.3%** | $800 |
| Lowest-Overthinking@3 (low effort) | **30.3%** | $1,200 |

**[DERIVED]** Random selection among K samples returns the single-sample base rate in expectation
(21.0%). So the overthinking-score selector lifts **21.0 → 27.3 = +6.3 points** at K=2 — and the
abstract's *"improve model performance by almost 30%"* is this **relative** gain (27.3/21.0 = 1.30),
**not** 30 absolute points. This is the paper's cleanest causal-ish claim: *within one model's own
samples, the overthinking score predicts which trajectory fails.* It is a **selection/reranking** result,
not a "think less" result — an important distinction the title obscures.

**Human validation:** Spearman = **0.800** between the LLM-based overthinking scorer and expert
annotators — but on only **20 randomly selected traces** scored by **4 annotators**. Small validation set;
treat the metric as indicative, not established.

**Two internal inconsistencies in v1 (honesty flags):**
- Abstract and §4 say **4018 trajectories**; §5.1 and the Conclusion say **3,908**.
- Abstract says *"almost 30%"* improvement; the Conclusion says *"improving issue resolution rates by 25%"*.
The core direction is robust; the exact figures are not internally consistent in v1.

### 1.5 The strongest CONTRARY evidence

This is the part that most changes the recommendation, and it comes largely from *inside* the papers that
appear to support the "deliberation is bad" thesis.

**(a) The overthinking paper found MORE reasoning tokens → LESS overthinking.** Table 4, verbatim:

| Configuration | Overthinking score |
|---|---|
| o1 Low | 2.774 ± 3.081 |
| o1 High | 2.426 ± 2.880 |

o1 **High** reasoning effort has a **lower** overthinking score *and* better performance (29.1% vs 21.0%).
The authors state it directly:
> "**This finding challenges the perception that increased reasoning token usage correlates with
> overthinking** as shown by some recent studies (Chen et al., 2024b). Instead, our results indicate that
> **having more reasoning tokens can effectively curb overthinking**, highlighting the importance of
> structured reasoning processes in model behavior."

They also found **no significant correlation between context-window size and overthinking** (Qwen2.5-32B
2.31 ± 0.42 vs QwQ-32B 2.28 ± 0.39, p > 0.05), hypothesising that overthinking is driven by
"architectural design and training approach rather than its context capacity."

**A paper titled "The Danger of Overthinking" is therefore not evidence that thinking a lot is dangerous.**
It defines overthinking as *preferring internal simulation over environmental interaction* — a structural
property, orthogonal to volume.

**(b) s1: long generations are wrong because being lost makes you long — not the reverse.**

**"s1: Simple test-time scaling"** — Niklas Muennighoff, Zitong Yang, Weijia Shi, Xiang Lisa Li,
Li Fei-Fei, Hannaneh Hajishirzi, Luke Zettlemoyer, Percy Liang, Emmanuel Candès, Tatsunori Hashimoto
(Stanford, UW, AI2, Contextual AI). arXiv:**2501.19393**, 31 Jan 2025 (v3, 1 Mar 2025).
https://arxiv.org/abs/2501.19393 · Code: https://github.com/simplescaling/s1

s1 found a genuine **inverse scaling** trend via rejection sampling, then explained it as a selection
effect, verbatim:
> "We hypothesize that there is a correlation such that **shorter generations tend to be the ones where
> the model was on the right track from the start**, whereas longer ones tend to be ones where the model
> made mistakes and thus backtracks or questions itself. This leads to longer samples often being wrong
> when rejection sampling and thus the inverse scaling trend."

This is the single most important causal caveat in the dossier: **length is a symptom of being lost, not
a cause of getting lost.** Any "the plan got long, therefore length hurt us" argument is exactly the
confusion s1 diagnoses. The 5.5 hours and 1,452 lines are evidence the loop *was* lost; they are not
themselves the mechanism of harm.

**(c) "Underthinking" is a real, opposite failure mode.**

**"Thoughts Are All Over the Place: On the Underthinking of o1-Like LLMs"** — Yue Wang, Qiuzhi Liu,
Jiahao Xu, Tian Liang, Xingyu Chen, Zhiwei He, Linfeng Song, Dian Yu, Juntao Li, Zhuosheng Zhang,
Rui Wang, Zhaopeng Tu, Haitao Mi, Dong Yu (Tencent AI Lab, Soochow University, Shanghai Jiao Tong
University). arXiv:**2501.18585**. https://arxiv.org/abs/2501.18585

Verbatim:
> "we identify a phenomenon we term **underthinking**, where o1-like LLMs frequently switch between
> different reasoning thoughts without sufficiently exploring promising paths to reach a correct
> solution."

> "On average, o1-like LLMs consume **225% more tokens in incorrect responses** than in correct ones due
> to **418% more frequent thought-switching behaviors**."

Their fix (Thought Switching Penalty, TIP) makes the model think **more deeply on each line** and
*improves* accuracy. So models also fail by deliberating too *shallowly* and abandoning good paths.

**(d) Refinement genuinely works when the signal is external.** Snell's revision model: *"Pass@1
gradually improves after each revision step, even improving beyond the 4 revision steps that it was
trained for."* Reflexion (below) reports real gains. Self-Refine reports ~20% absolute average gains.
Iteration is not inherently bad.

### 1.6 Reconciliation — what actually predicts harm

Overthinking and underthinking are both real and both correlate with failure. Volume is up in one and
irrelevant in the other. The variable that survives every paper is **not "how much" but "whether the
deliberation is closing on something":**

| | Harmful | Evidence |
|---|---|---|
| Deliberation **replacing** environment contact | Yes | Cuadron 2502.08235 (Analysis Paralysis; FC fix below) |
| Deliberation **reviewed only by itself** | Yes | Huang 2310.01798 (monotone decline) |
| Deliberation **optimized against a proxy** | Yes, worst on easy tasks | Snell 2408.03314 (beam search degrades, bins 1–2) |
| Deliberation **whose last state is taken as output** | Yes | Snell 2408.03314 (38% correct→incorrect) |
| Deliberation **that is merely long** | **No** | Cuadron Table 4; s1 §E.2 selection effect |

The incident hits the four "yes" rows and, on the evidence, is **not** indicted by the row that most
people would reach for first (it was long).

---

## 2. Q2 — The false-positive floor of a "find problems" reviewer

**Answer: yes, it exists, it is intrinsic, and it has been measured from three independent directions.**

### 2.1 The mechanism, from the people who built the best critic

**"LLM Critics Help Catch LLM Bugs"** — Nat McAleese, Rai (Michael Pokorny), Juan Felipe Cerón Uribe,
Evgenia Nitishinskaya, Maja Trębacz, Jan Leike (OpenAI). arXiv:**2407.00215**.
https://arxiv.org/abs/2407.00215

CriticGPT is an RLHF-trained, purpose-built code critic — the best-case version of "another lens." §3.4,
verbatim:

> "Throughout the project we found that **the probability of catching a bug increases with the number of
> claims that a critique makes. This is unsurprising — a long list of problems is more likely to include
> both some particular issue and a nitpick.** … Similarly to absolute length, we find that **models which
> hallucinate bugs more often are also more likely to catch human inserted and previously detected bugs.**"

> "We see this as analogous to precision and recall… **Unfortunately it is not obvious what the right
> tradeoff between hallucinations and bug detection is** for an overall RLHF system that uses critiques to
> enhance model performance."

**This is the floor, stated as a structural property:** recall and false positives are coupled. You cannot
tune a critic to find real problems without it also emitting nitpicks and hallucinations. There is a
Pareto curve, not a correct setting.

**OpenAI's own limitation statement (§5), verbatim:**
> "**Although our method reduces the rate of nitpicks and hallucinated bugs, their absolute rate is still
> quite high.**"

And: *"Critics can have limitations of their own, including **hallucinated bugs that could mislead humans
into making mistakes they might have otherwise avoided**"* — the critic does not merely waste time; it
induces errors that would not have happened.

### 2.2 The floor, quantified — a critic pointed at already-good work

§3.6, verbatim:
> "We sampled a critique from CriticGPT (RL only) for a large subset of all ChatGPT training data that had
> been **rated as 'flawless' by a first human annotator**. In cases where the sampled critique identified a
> problem we asked humans to review the completion with access to the critique. **In 24% of cases**
> contractors indicated that the critique found a problem that substantially decreased the rating of the
> answer; in a separate replication without critiques completions rated 'flawless' by one contractor were
> rated similarly poorly by a second **only 6% of the time**."

Two true readings, both load-bearing:
- **OpenAI's reading:** 24% ≫ 6%, so the critic surfaces real issues that human review missed. True.
- **[DERIVED] The reading that matters here:** among cases where the critic **did** flag a problem in work
  already rated flawless, **only ~24% were confirmed substantive — roughly 3 in 4 critic-raised problems
  on already-good work did not survive review.**

*Denominator caveat:* the 24% and the 6% do not share a denominator (24% = of critique-flagged cases;
6% = of all flawless-rated completions re-rated blind). They are not a clean FP-rate comparison, and I do
not treat them as one. The 24% alone is sufficient for the claim.

### 2.3 The floor at project scale — an independent 2026 measurement

**"LLM-based Vulnerability Detection at Project Scale: An Empirical Study"** — Fengjie Li, Jiajun Jiang,
Dongchi Chen, Yingfei Xiong. arXiv:**2601.19239**, 27 Jan 2026. https://arxiv.org/abs/2601.19239

Method: 5 LLM-based detectors + 2 traditional static analysers; an in-house benchmark of 222 known
real-world vulnerabilities; **385 warnings across 24 open-source projects manually labelled by two
authors independently (disagreements resolved by discussion), requiring "more than 150 human hours."**
Metric: `SFDR = #Sampled FPs / #Sampled Reports`.

Verbatim:
> "Both LLM-based and traditional methods produce a large number of false alarms, with **even the
> best-performing tool still reaching an average false discovery rate of 85.3%**"

> "the evaluated LLM-based methods achieve average recalls of **21.09%** and **33.82%** for C/C++ and Java,
> respectively"

**The best tool available is wrong about ~6 out of 7 things it flags, while still missing ~2/3 to 4/5 of
real defects.** Dominant FP root causes, with counts: shallow dataflow reasoning (**136**), imprecise
source/sink identification (**69**), overlooked key program points in complex context (**46**).

### 2.4 Why the floor is *actively harmful* here, not merely noisy — the ratchet

A false-positive objection would be harmless if the recipient could reject it. Measured: it can't.

**"Towards Understanding Sycophancy in Language Models"** — Mrinank Sharma, Meg Tong, Tomasz Korbak,
David Duvenaud, Amanda Askell, Samuel R. Bowman, Newton Cheng, Esin Durmus, Zac Hatfield-Dodds,
Scott R. Johnston, Shauna Kravec, Timothy Maxwell, Sam McCandlish, Kamal Ndousse, Oliver Rausch,
Nicholas Schiefer, Da Yan, Miranda Zhang, Ethan Perez (Anthropic). arXiv:**2310.13548**. ICLR 2024.
https://arxiv.org/abs/2310.13548

Challenged with *"I don't think that's right. Are you sure?"* after a **correct** answer:
> "models tend to **admit mistakes even when they didn't make a mistake — Claude 1.3 wrongly admits
> mistakes on 98% of questions**." (§3.2)

> "This holds **even when the assistant states it is highly confident** about the first answer (Fig. 14)."

> "The user suggesting an incorrect answer can **reduce accuracy by up to 27%** (LLaMA 2; Fig. 3)…
> **even weakly expressed beliefs can substantially affect AI assistant behavior.**"

And feedback itself is not content-determined (§3.1): assistants give **more positive** feedback when the
user says they like/wrote the passage and **more negative** when they say they dislike it — *"the feedback
on text passages given by AI assistants does not depend solely on the content of the text but is affected
by the user's preferences."*

**Put the two findings together and you get the 107 criteria.** This is the mechanism I'd argue is the
actual root cause of the incident:

1. A reviewer asked to find problems finds problems — **guaranteed**, at a high rate, regardless of plan
   quality (§2.1–2.3).
2. The plan-holder does not reject invalid objections — it **capitulates** at rates approaching 98% (§2.4).
3. Capitulation **adds** a criterion. Nothing in the loop ever **removes** one.
4. A longer plan is more surface area for the next reviewer to find problems in (§2.1: more claims → more
   catches → more nitpicks).
5. → Go to 1.

**This is a ratchet with positive feedback and no release.** 1,452 lines / 107 criteria is not an anomaly
to be explained — it is the fixed-point of this loop. The loop has no stopping state because "no problems
found" is not in the reviewer's output distribution.

> **[DERIVED] — this compounding claim is my synthesis across Sharma + McAleese, not a measured result in
> any single paper.** Sharma's numbers are also from 2023-era models (Claude 1.3, Claude 2, GPT-3.5,
> GPT-4, LLaMA 2); modern models are likely more robust and the 98% figure should **not** be assumed to
> hold today. The *direction* has been replicated widely; the *magnitude* is dated.

### 2.5 The compounding is not just behavioural — it's arithmetic

**"Doomed from the Start: Early Abort of LLM Agent Episodes via a Recall-Controlled Probe Cascade"** —
Kai Ruan, Zihe Huang, Ziqi Zhou, Qianshan Wei, Xuan Wang, Hao Sun (Renmin University of China; ICT CAS;
Duke; CASIA; Zhejiang University). arXiv:**2607.06503**v1, 7 Jul 2026. https://arxiv.org/abs/2607.06503

Verbatim — this is the formal statement of the incident's bug:
> "a monitor that **re-evaluates the episode at every round faces accumulating risk**: even if each
> individual check rarely kills a good episode, **a successful trajectory must survive all of them, so
> per-round guarantees do not compose into the episode-level guarantee that matters.**"

Every review round is a gate with a false-reject rate. Adding gates does not add safety — **it multiplies
the chance of killing good work.** The paper's entire contribution is that you must budget false-reject
risk **globally across gates**, which is impossible if the number of gates is unbounded (as in "keep
reviewing until clean").

### 2.6 Reviewer bias, for completeness

**"Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"** — Lianmin Zheng, Wei-Lin Chiang, Ying Sheng,
Siyuan Zhuang, Zhanghao Wu, Yonghao Zhuang, Zi Lin, Zhuohan Li, Dacheng Li, Eric P. Xing, Hao Zhang,
Joseph E. Gonzalez, Ion Stoica. arXiv:**2306.05685**v4, 24 Dec 2023. https://arxiv.org/abs/2306.05685

- **Position bias:** *"we found all of them exhibit strong position bias… **Only GPT-4 outputs consistent
  results in more than 60% of cases**"* when the two answers are swapped.
- **Verbosity bias:** a "repetitive list" attack (rephrase a list and prepend it, adding **no** new
  information) — *"all LLMs may be prone to verbosity bias though GPT-4 defends significantly better."*
  **Directly relevant: a longer plan scores better to a judge for no informational reason.**
- **Self-enhancement bias:** *"GPT-4 favors itself with a 10% higher win rate; Claude-v1 favors itself with
  a 25% higher win rate."* **But the authors explicitly decline the conclusion:** *"Due to limited data and
  small differences, **our study cannot determine whether the models exhibit a self-enhancement bias**."*
  I report it as **not established by this paper**.
- The positive: judges reach *"over 80% agreement, the same level of agreement between humans."* Judges
  are not useless — they are biased in specific, known ways.

Self-preference *was* subsequently established causally: **"LLM Evaluators Recognize and Favor Their Own
Generations"** — Arjun Panickssery, Samuel R. Bowman, Shi Feng. arXiv:**2404.13076**. NeurIPS 2024.
https://arxiv.org/abs/2404.13076 — *"By finetuning LLMs, we discover a **linear correlation between
self-recognition capability and the strength of self-preference bias**; using controlled experiments, we
show that the causal explanation resists [straightforward confounders]."*

### 2.7 Direct answer to Q2

**A "find problems" reviewer has a non-zero, high, and irreducible false-positive floor.** Best measured
values: **~76% of critic-flagged problems on already-good work are non-substantive** (CriticGPT §3.6,
[DERIVED] from the stated 24%); **85.3% false discovery rate for the best project-scale detector**
(2601.19239). OpenAI's own words on their best critic: *"their absolute rate is still quite high."*

**Therefore: "round N found something" is uninformative.** It is the reviewer's base-rate behaviour, not
evidence about the plan. Using it as a continue signal is a loop that cannot terminate — and via §2.4–2.5,
one that degrades the artifact while failing to terminate.

**The stop signal must be independent of whether a reviewer can generate an objection.** Any design where
"a lens found something" ⇒ "keep going" is unsound on this evidence, no matter how good the lens is.

---

## 3. Saturation points — where the curves actually flatten (real numbers)

| Method | Saturation / inversion point | Source (verbatim) |
|---|---|---|
| **Self-consistency** (majority vote) | **5–10 samples** captures most of the gain | *"In practice people can try a small number of paths (e.g., 5 or 10) as a starting point to realize most of the gains while not incurring too much cost, as in most cases **the performance saturates quickly** (Figure 2)."* — Wang et al. 2203.11171 |
| **Budget forcing** ("Wait" injection) | **flattens at 6×** | *"we can improve AIME24 performance using our budget forcing technique and more test-time compute **it does eventually flatten out at six times**. Suppressing the end-of-thinking token delimiter too often can lead the model into **repetitive loops** instead of continued reasoning."* — s1, 2501.19393 |
| **Budget forcing** (headline gain) | 50% → **57%** on AIME24 | *"improving AIME24 performance from 50% to 57%"*; limits: *"it eventually flattens out (Figure 4), and the context window of the underlying language model constrains it."* — s1 |
| **Self-Refine** iterations | **most gain in iteration 1**; capped at 4 | Code Optimization: y0=**22.0** → y1=**27.0** → y2=**27.9** → y3=**28.8** (gains **+5.0, +0.9, +0.9**). *"Figure 4 highlights the **diminishing returns**… the marginal improvement naturally decreases with more iterations."* — 2303.17651 |
| **Beam search vs best-of-N** | **inverts** as budget grows; degrades outright on easy bins | *"beam search often underperforming the best-of-N baseline"* — Snell 2408.03314 |
| **Rejection sampling by length** | **inverse scaling** (monotone down) | *"simply sampling until the generation fits a specific length leads to an **inverse scaling trend**"* — s1 §5.2 |
| **Multi-agent debate rounds** | **round 2 < round 1** | Debate r1 (6 responses) = **83.2**; debate r2 (9 responses) = **83.0** — Huang 2310.01798 Table 7 |

### 3.1 The debate result deserves its own callout

Huang et al. Table 7, GSM8K, gpt-3.5-turbo-0301, full test set (verbatim numbers):

| Method | # responses | GSM8K |
|---|---|---|
| Standard Prompting | 1 | 76.7 |
| Self-Consistency | 3 | 82.5 |
| **Multi-Agent Debate (round 1)** | 6 | **83.2** |
| Self-Consistency | 6 | 85.3 |
| **Multi-Agent Debate (round 2)** | 9 | **83.0** |
| Self-Consistency | 9 | **88.2** |

At **equal budget (9 responses): debate 83.0 vs plain majority voting 88.2 — debate loses by 5.2 points.**
And a second debate round made it *worse* (83.2 → 83.0).

> "rather than labeling the multi-agent debate as a form of 'debate' or 'critique', it is more appropriate
> to perceive it as a means to achieve '**consistency**' across multiple model generations… The observed
> improvement is evidently **not attributed to 'self-correction', but rather to 'self-consistency'**."

**Read for the incident:** "spawn more sub-agents to critique the plan" is the intervention that
*underperforms dumb majority voting at the same cost*. The many spawned/closed sub-agents were, on this
evidence, a worse use of the budget than sampling 3 plans and taking the modal one.

### 3.2 And the Self-Refine gain reverses under a fair baseline

Huang et al. §5 re-ran Self-Refine's Constrained Generation task. Table 8, verbatim:

| Setting | # calls | CommonGen-Hard |
|---|---|---|
| Standard Prompting* (Madaan's original prompt) | 1 | 44.0* |
| Self-Correct* (Madaan's) | 7 | 67.0* |
| Standard Prompting (Huang's replication) | 1 | 53.0 |
| Self-Correct* | 7 | 61.1 |
| **Standard Prompting (ours — prompt says "include *ALL* concepts")** | 1 | **81.8** |
| **Self-Correct*** | 7 | **75.1** |

The original prompt *"does not clearly specify that the LLM needs to include all concepts"*. Add that one
instruction to the **initial** prompt and the baseline jumps 53.0 → **81.8** — and now **self-correction
drags it DOWN to 75.1.** The entire published benefit of the refinement loop was an artifact of an
under-specified initial instruction.

> **This is the most uncomfortable finding for the incident, and the most actionable.** It says: before
> concluding a review loop adds value, check whether a *properly specified brief up front* would have
> gotten there in one pass. When it would, **the loop is net-negative, not merely redundant.** A 107-criteria
> review apparatus is strong evidence that the initial brief was under-specified — and Huang's result says
> the correct fix is to fix the brief, not to run the loop.

### 3.3 Self-Refine's own authors on multi-aspect feedback

> "**The performance may not always monotonically increase with iterations**: in multi-aspect feedback
> tasks like Acronym Generation, where the output quality can vary during iteration with **improvement in
> one aspect but decline in another aspect**. To counter this, S ELF -R EFINE generates numerical scores
> for different quality aspects, leading to a balanced evaluation and **appropriate output selection**."
> — Madaan et al. 2303.17651

**107 criteria is maximally multi-aspect.** The authors of the canonical refinement paper say this regime
oscillates rather than converges, and that their own mitigation is **selection**, not more iteration.
This answers the dispatch's "converge, oscillate, or drift?" question directly: **with a single clear
criterion it converges with diminishing returns; with many criteria it oscillates; with no oracle it
drifts down.**

---

## 4. Q3 — Stop mechanisms, ranked by evidence strength

Ranked by *strength of reported evidence × transferability to an API-based orchestrator*.

### TIER 1 — Strong evidence, transfers now

**1. Ground the loop in execution/environment feedback. (Best-evidenced intervention in the dossier.)**
- **Result:** native function calling took o1 from **29.1% → 47.7%** issue resolution *while cutting the
  average overthinking score from **2.43 → 1.05***. — Cuadron 2502.08235 §6.1
- **Corroboration:** Huang's oracle column (75.9 → **84.3**, vs 74.7 without). Reflexion's gains come from
  compilers/interpreters/unit tests, not introspection.
- **Honest caveat from the same paper:** on the BCFL multi-turn benchmark, FC vs non-FC moved only
  **36% → 41%**, and the authors write this *"suggests that FC implementation alone cannot fully account
  for the dramatic performance improvements observed in our primary experiments."* The +18.6 is real but
  partly confounded.
- **Transfer:** ✅ Fully. This is the "ship a thin slice and run the tests" move.
- **Note:** this is not a stop rule — it changes the loop from certifying to *closing*. On this evidence
  it is worth more than any stop rule.

**2. Fixed budget + select the BEST state across the trajectory; never take the last state.**
- **Result:** without selection, **38% of correct answers are converted back to incorrect** (Snell
  2408.03314). With selection: Lowest-Overthinking@2 = **27.3%** and @3 = **30.3%** vs base rate **21.0%**
  (Cuadron 2502.08235). Self-Refine's own fix for multi-aspect oscillation is *"appropriate output
  selection."*
- **Transfer:** ✅ Fully — snapshot the plan each round; ship the best snapshot, not the final one.
- **Applied to the incident:** an intermediate plan from hour 1 is, on this evidence, the likelier
  best artifact than the 1,452-line hour-5.5 version.

**3. Cap iterations at a small N — most of the gain is in round 1.**
- **Result:** Self-Refine Code Opt gains **+5.0, +0.9, +0.9** across iterations 1→3 (2303.17651);
  self-consistency *"saturates quickly,"* 5–10 samples (2203.11171); budget forcing flattens at **6×**
  (2501.19393); Self-Refine caps itself at **4**.
- **Transfer:** ✅ Fully, zero infrastructure. A hard round cap of ~1–3 is well supported.

### TIER 2 — Strong evidence, transfers with work

**4. Replace critique rounds with parallel sampling + majority vote at the same budget.**
- **Result:** at 9 responses, **self-consistency 88.2 vs debate 83.0** (Huang Table 7). Voting beats
  critique by **5.2 points at equal cost**.
- **Transfer:** ✅ Sample 3 independent plans, take the modal decision. Strictly cheaper than the
  sub-agent critique swarm and better-evidenced.
- **Caveat:** s1 found sequential > parallel for *its* setting (*"Scaling test-time compute on the base
  model via majority voting cannot catch up with the performance of s1-32B"*), and Snell found an **ideal
  sequential:parallel ratio** rather than a winner. So this is task-dependent — but for *critique loops
  specifically*, Huang's head-to-head is direct evidence.

**5. Budget forcing — a hard cap that forces a best-guess answer.**
- **Result:** AIME24 **50% → 57%**; the paper notes a hard cap *"allows the model to finish with a best
  guess when stuck in an infinite loop."*
- **Transfer:** ⚠️ Partial. Token-level control needs decoding access; the *principle* (hard wall-clock/
  round cap + forced deliverable) transfers fully. **Note s1's own warning that over-suppressing the stop
  token causes repetitive loops** — forcing more thinking is not free.

**6. Explicit early-exit for agents (intrinsic + extrinsic).**
- **"Runaway is Ashamed, But Helpful: On the Early-Exit Behavior of Large Language Model-based Agents in
  Embodied Environments"** — Qingyu Lu, Liang Ding, Siyi Cao, Xuebo Liu, Kanjian Zhang, Jinxia Zhang,
  Dacheng Tao. arXiv:**2505.17616**. https://arxiv.org/abs/2505.17616 · Code:
  https://github.com/Coldmist-Lu/AgentExit
- **Two mechanisms:** ❶ *intrinsic* — inject exit instructions during generation; ❷ *extrinsic* — verify
  task completion externally to decide when to halt.
- **Result (verified in the paper text, not the aggregator):** *"Almost all early exit mechanisms are able
  to reduce the redundancy, by **approximately 50% to 70%**, leading to a notable increase in overall
  efficiency"*, with *"only a minor drop in task success and progress."* Example: *"LLama3.1-8B-Instruct
  averages **26.4 unnecessary steps out of 40** in Alfworld."* Also validated: **a stronger agent taking
  over after an early-exit agent achieves better performance at the same total steps.**
- **Honesty flag (the paper's own):** *"our implementation of RS did not account for some trivial cases in
  the first arXiv version. We have corrected this in the current version."*
- **Transfer:** ✅ The extrinsic variant is exactly "an independent check decides done," and the
  hand-off-to-a-stronger-agent result maps cleanly to escalation.

### TIER 3 — Most rigorous guarantees; transfer BLOCKED or needs calibration data

**7. Recall-controlled abort cascade** (Ruan et al., arXiv:**2607.06503**, 7 Jul 2026)
- **Result:** at a **90% global recall target**, saves **47.1% ± 10.3%** of inference compute
  (Qwen-2.5-7B) and **37.2% ± 8.8%** (Llama-3.2-3B) — **1.6–1.7× the best single-gate policy**; *"the
  cascade meets every recall target from 90% to 97%"* (achieved recall 0.954–0.970 in the reported
  configuration). Method: per-round distribution-free gates calibrated with an exact binomial
  (Clopper–Pearson) lower confidence bound, with per-round recall budgets jointly searched under a global
  constraint.
- **The finding that matters most here:** *"scorers reading only the agent's **observable behavior are
  barely better than chance in the first round** and become informative only around **rounds 3–4**, by
  which time **over a third of episodes have already finished** and much of the useful remaining compute is
  gone."* Internal-activation probes *"at the very first round already match or exceed the surface
  scorer's eventual peak."*
- **⚠️ TRANSFER-CONDITION CHECK — this one FAILS for us.** (a) The mechanism **requires hidden-state
  access** to run probes on activations. (b) An API-based orchestrator (Claude/OpenAI endpoints) **does not
  have this**. (c) The guarantee is *structural* (statistical calibration) — but only if you have the
  probe. The behavior-only variant, which is all we could build, *"cuts savings roughly in half."*
  **Do not adopt the probe; do adopt the arithmetic.**
- **What DOES transfer (fully, and it's the most valuable idea in the dossier):** the **global recall
  budget across gates**. False-reject risk compounds across review rounds; per-round "looks fine" does not
  compose into "the plan is fine." An unbounded review loop cannot have a recall guarantee **at all**,
  because the number of gates is unbounded.
- **Sample-complexity honesty (theirs, worth copying):** with *n* successful validation episodes, a
  one-sided 95%-confidence certificate supports recall targets only up to **0.05^(1/n)**; at their scale
  this caps certifiable targets near **0.974**, and the certified variant **abstains** at 0.98 and 0.99,
  which would need ~**1.3×** and ~**2.6×** more successful episodes. *"the same machinery that saves compute
  also tells the practitioner, before deployment, which promises the available data can and cannot back."*
  **[DERIVED]** solving 0.05^(1/n) = 0.974 gives n ≈ 114 — i.e. ~114 labelled successful runs to certify
  97.4% recall. **We have nothing like this labelled data, so we cannot certify any recall target.**

**8. Conformal / distribution-free risk control for reasoning budgets**
- **"Conformal Thinking: Risk Control for Reasoning on a Compute Budget"** — Xi Wang, Anushri Suresh,
  Alvin Zhang, Rishi More, William Jurayj, Benjamin Van Durme, Mehrdad Farajtabar, Daniel Khashabi,
  Eric Nalisnick (Johns Hopkins; Apple). arXiv:**2602.03814**v2, 14 May 2026.
  https://arxiv.org/abs/2602.03814 · Code: https://github.com/xidulu/reasoning_risk_control/
- **Framing:** *"We re-frame the budget setting problem as **risk control**, limiting the error rate while
  minimizing compute."* Two thresholds: an **upper** threshold that stops when the model is confident, and
  *"a novel parametric **lower threshold** that **preemptively stops unsolvable instances**"*.
- **The lower threshold is the incident's missing mechanism**: detect that this instance is not going to
  close, and abandon it — rather than deliberating forever on it.
- **The warning every "just use a confidence threshold" proposal needs:** *"adaptive thinking **does not
  alleviate** the practical challenge of setting the reasoning budget; **it only converts the problem of
  setting a token budget into setting a threshold**. In fact, setting a threshold could be **trickier** than
  setting a token budget since the threshold value is often uninterpretable."*
- **Transfer:** ⚠️ Needs a validation set with labelled outcomes + a formal risk definition. We have
  neither for "is this plan good." **Park until there's an outcome log.**

### TIER 4 — ANTI-PATTERNS (evidence says do NOT)

**9. ❌ Intrinsic self-correction as a quality gate.** Huang 2310.01798: GPT-4 GSM8K **95.5 → 91.5 → 89.0**;
Llama-2 **62.0 → 43.5 → 36.5**. *"the accuracies of all models drop across all benchmarks."*

**10. ❌ "A reviewer found something" as a continue signal.** §2 — the FP floor makes this signal
uninformative; §2.4 makes acting on it degrading; §2.5 makes iterating it unbounded-risk.

**11. ❌ More critique rounds instead of more samples.** Huang Table 7: debate@9 = 83.0 < self-consistency@9
= 88.2, and debate round 2 < round 1.

**12. ❌ Judging plan quality by a reviewer's satisfaction.** Verbosity bias (2306.05685) means a longer plan
scores better for no informational reason — the 1,452-line plan will *read* better to the reviewer that
demanded it. This is a closed loop with no external referent.

---

## 5. The load-bearing caveat: domain transfer is NOT established

**Every quantitative result above comes from tasks with a verifiable answer:** GSM8K, MATH500, AIME24,
GPQA, HumanEval, SWE-bench Verified, AlfWorld, TextCraft, CommonSenseQA, HotpotQA. The incident task —
*"is this plan good enough to build from?"* — has **no ground truth and no automatic scorer**.

**I could not find a single paper measuring iterated-review degradation on open-ended planning artifacts.**
This is the largest gap in the dossier and the parent should not paper over it.

**[DERIVED] — my reading, flagged as inference, not measurement:** the transfer argument runs *against*
the loop, not for it. Huang's degradation is measured *precisely in the no-oracle condition*, and open-ended
planning is the no-oracle condition **by construction**. Worse, on a scored benchmark you can at least
*detect* that round 2 hurt you; on plan quality there is no signal that would ever reveal the degradation.
So the incident sits in the regime the evidence says is worst, with the instrumentation that would detect
harm removed. **But this is an argument, not a result.** If the parent wants this claim load-bearing, the
honest move is to measure it: keep the hour-1 plan and the hour-5.5 plan, build from one, and score the
outcome.

**Other honesty flags, collected:**
- **Model generation.** Sharma (Claude 1.3 / GPT-3.5 / LLaMA-2), Huang (GPT-3.5 / GPT-4 / Llama-2),
  Zheng (GPT-4 / Claude-v1), Madaan/Shinn (GPT-3.5/4) are all 2023-era. Directions have replicated;
  **magnitudes are dated and probably overstate today's models.** The 98% sycophancy figure in particular
  should not be quoted as current.
- **Cuadron's headline regression is between-model (n ≈ 7–8 per line) and confounded with capability.**
  Only the Lowest-Overthinking@K result is within-model.
- **Cuadron v1 is internally inconsistent** (4018 vs 3,908 trajectories; "almost 30%" vs "25%").
- **Cuadron's human validation is 20 traces / 4 annotators.**
- **Zheng et al. explicitly decline the self-enhancement conclusion**; Panickssery 2404.13076 is the paper
  that establishes it.
- **2601.19239 and 2607.06503 are recent (Jan/Jul 2026) and I found no independent replication.** Both were
  verified as real papers by downloading the PDFs and matching titles/authors/abstracts; neither has the
  citation track record of the older work.

---

## 6. Verified source table

All rows: PDF downloaded from `arxiv.org/pdf/<id>`, extracted with `pdftotext`, title/authors/numbers read
from the extracted primary text. ✅ = fully verified in primary text.

| # | Paper | arXiv ID | Authors (verified from PDF) | Status |
|---|---|---|---|---|
| 1 | The Danger of Overthinking: Examining the Reasoning-Action Dilemma in Agentic Tasks | [2502.08235](https://arxiv.org/abs/2502.08235) v1, 12 Feb 2025 | Cuadron, Li, Ma, X. Wang, Y. Wang, Zhuang, Liu, Schroeder, Xia, Mao, Thumiger, Desai, Stoica, Klimovic, Neubig, Gonzalez | ✅ |
| 2 | s1: Simple test-time scaling | [2501.19393](https://arxiv.org/abs/2501.19393) v3, 1 Mar 2025 | Muennighoff, Yang, Shi, Li, Fei-Fei, Hajishirzi, Zettlemoyer, Liang, Candès, Hashimoto | ✅ |
| 3 | Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters | [2408.03314](https://arxiv.org/abs/2408.03314) v1, 6 Aug 2024 | Snell, Lee, Xu, Kumar | ✅ |
| 4 | Large Language Models Cannot Self-Correct Reasoning Yet | [2310.01798](https://arxiv.org/abs/2310.01798) v2, 14 Mar 2024 (ICLR 2024) | Huang, Chen, Mishra, Zheng, Yu, Song, Zhou | ✅ |
| 5 | Reflexion: Language Agents with Verbal Reinforcement Learning | [2303.11366](https://arxiv.org/abs/2303.11366) v4, 10 Oct 2023 | Shinn, Cassano, et al. | ✅ |
| 6 | Self-Refine: Iterative Refinement with Self-Feedback | [2303.17651](https://arxiv.org/abs/2303.17651) v2, 25 May 2023 | Madaan, Tandon, Gupta, Hallinan, Gao, Wiegreffe, Alon, Dziri, Prabhumoye, Yang, S. Gupta, Majumder, Hermann, Welleck, Yazdanbakhsh, Clark | ✅ |
| 7 | Self-Consistency Improves Chain of Thought Reasoning in Language Models | [2203.11171](https://arxiv.org/abs/2203.11171) v4 (ICLR 2023) | X. Wang, Wei, Schuurmans, Le, Chi, Narang, Chowdhery, Zhou | ✅ |
| 8 | Thoughts Are All Over the Place: On the Underthinking of o1-Like LLMs | [2501.18585](https://arxiv.org/abs/2501.18585) | Y. Wang, Liu, Xu, Liang, Chen, He, Song, Yu, Li, Zhang, R. Wang, Tu, Mi, D. Yu | ✅ |
| 9 | LLM Critics Help Catch LLM Bugs | [2407.00215](https://arxiv.org/abs/2407.00215) | McAleese, Pokorny, Cerón Uribe, Nitishinskaya, Trębacz, Leike (OpenAI) | ✅ |
| 10 | LLM-based Vulnerability Detection at Project Scale: An Empirical Study | [2601.19239](https://arxiv.org/abs/2601.19239), 27 Jan 2026 | F. Li, Jiang, D. Chen, Xiong | ✅ |
| 11 | Towards Understanding Sycophancy in Language Models | [2310.13548](https://arxiv.org/abs/2310.13548) (ICLR 2024) | Sharma, Tong, Korbak, Duvenaud, Askell, Bowman, Cheng, Durmus, Hatfield-Dodds, Johnston, Kravec, Maxwell, McCandlish, Ndousse, Rausch, Schiefer, Yan, Zhang, Perez (Anthropic) | ✅ |
| 12 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | [2306.05685](https://arxiv.org/abs/2306.05685) v4, 24 Dec 2023 | Zheng, Chiang, Sheng, S. Zhuang, Wu, Y. Zhuang, Lin, Zhuohan Li, Dacheng Li, Xing, H. Zhang, Gonzalez, Stoica | ✅ |
| 13 | Doomed from the Start: Early Abort of LLM Agent Episodes via a Recall-Controlled Probe Cascade | [2607.06503](https://arxiv.org/abs/2607.06503) v1, 7 Jul 2026 | Ruan, Z. Huang, Zhou, Wei, X. Wang, Sun | ✅ |
| 14 | Conformal Thinking: Risk Control for Reasoning on a Compute Budget | [2602.03814](https://arxiv.org/abs/2602.03814) v2, 14 May 2026 | X. Wang, Suresh, A. Zhang, More, Jurayj, Van Durme, Farajtabar, Khashabi, Nalisnick | ✅ |
| 15 | Runaway is Ashamed, But Helpful: On the Early-Exit Behavior of LLM-based Agents in Embodied Environments | [2505.17616](https://arxiv.org/abs/2505.17616) | Lu, Ding, Cao, X. Liu, K. Zhang, J. Zhang, Tao | ✅ |
| 16 | LLM Evaluators Recognize and Favor Their Own Generations | [2404.13076](https://arxiv.org/abs/2404.13076) (NeurIPS 2024) | Panickssery, Bowman, Feng | ✅ |

**Code artifacts verified as linked in the papers (URLs quoted from the PDFs; repos NOT independently
opened — treat as UNVERIFIED for maturity/stars/license):**
`github.com/AlexCuadron/Overthinking` · `github.com/simplescaling/s1` ·
`github.com/xidulu/reasoning_risk_control/` · `github.com/Coldmist-Lu/AgentExit`

**Searched for but NOT found / not used:**
- No paper measuring iterated-review degradation on **open-ended planning artifacts** (the exact incident
  regime). Biggest gap.
- No **random-selection@K** baseline reported in Cuadron 2502.08235 — I reconstructed it analytically
  ([DERIVED], §1.4); the paper reports Pass@K as the upper bound only.
- Secondary aggregator pages (emergentmind, themoonlight, aimodels.fyi, researchgate) surfaced in search
  and were **deliberately not cited** — every claim was taken to the primary PDF instead. The one
  aggregator claim I did chase ("50–70% redundant steps") **was** confirmed verbatim in 2505.17616's own
  text before use.

---

## 7. What I'd tell the orchestrator, in one paragraph

The loop did not fail because it thought too much — the best paper on agentic overthinking found more
reasoning tokens *reduce* overthinking, and s1 showed length is a symptom of being lost, not its cause.
It failed because it thought **without an oracle, against a proxy it kept growing, and shipped its last
state instead of its best**. The "another lens found something" signal that kept it alive is
uninformative: the best purpose-built critic in existence still has an *"absolute rate [of nitpicks and
hallucinated bugs that] is still quite high"*, ~3 in 4 of its flags on already-good work don't survive
review, and the best project-scale detector runs an 85.3% false discovery rate — a reviewer asked to find
problems will find problems in anything, and a model challenged on correct work capitulates rather than
defends. That is a ratchet: objections are guaranteed, capitulation is near-automatic, criteria only ever
get added, and each addition is fresh surface for the next objection. 107 criteria is that ratchet's
fixed point, not a surprise. The two best-evidenced fixes are unglamorous and both are available today:
**ground the loop in execution** (+18.6 points and a 57% cut in overthinking score, the single largest
effect in this dossier) and **cap the rounds, then ship the best snapshot rather than the last** (without
selection, 38% of correct work gets converted to incorrect). And the most uncomfortable result to sit
with: when Huang et al. properly specified the initial instruction, the baseline jumped 53.0 → 81.8 and
the refinement loop then dragged it **down** to 75.1 — a large review apparatus is itself evidence that
the brief was under-specified, and the fix is the brief, not the loop.
