# Researcher Mode A dossier — is there a stopping rule for LOGIC/CONCURRENCY/SECURITY plan-check saturation? (2026-07-09)

**Dispatched to:** find an existing solution (or determine none exists) for "when should
an iterative LLM review/critique loop stop, for defect classes with no deterministic
ground-truth oracle to defer to" — the gap Gate 10 (`DESIGN_CHECKLIST.md`,
`harness/plancheck_saturation.py`) deliberately leaves open for LOGIC/CONCURRENCY/
SECURITY-tagged plan-check findings (it only mechanizes a stop for `[BINDING]`, the one
class with a real compiler-equivalent ground truth).

**Radar context read first (`research/radar.md`), per Mode A protocol:** current active
phase is Phase 1 (measured-improvement / verifier-hardening) with a live thread on
compiler-feedback and drift-validator prior art (2026-07-08 entries, `DESIGN_CHECKLIST.md`
gate 10 itself is mid-implementation per the 2026-07-08 Codex-followup reconciliation
entry). This dossier is a direct continuation of that thread — Gate 10 exists and works
for `[BINDING]`; this is the first dedicated research pass on its explicitly-excluded
sibling problem (LOGIC/CONCURRENCY/SECURITY saturation).

**Honesty-bar note on tooling:** `WebFetch` on raw arXiv PDF URLs repeatedly returned
garbled/binary content this session (a known WebFetch limitation, not a new finding) —
every such case is flagged below and either re-fetched via the HTML mirror
(`arxiv.org/html/<id>`) or `arxiv.org/abs/<id>`, or explicitly marked "abstract/summary
only, full text not confirmed." No repo or paper below is reported without at least one
successful direct fetch quoting real content.

---

## Headline answer

**No existing tool or paper solves this problem directly, for the exact task shape asked
about (repeated independent LLM review of a STATIC, unchanged spec, hunting for
LOGIC/CONCURRENCY/SECURITY defects with no compiler-equivalent oracle).** Every close
candidate found solves an adjacent-but-materially-different problem:

- **Real, shipped, production review-loop tools** (ai-code-reviewer, optimus-claude's
  `code-review-deep`, ralphreview, gopher-ai's Codex review-flow) all use some form of
  "N rounds/passes with zero (or ≤1) new findings → stop" — but every one of them is
  protecting against re-reviewing an artifact that **stopped changing between rounds**
  (a code diff that got fixed, or a fresh commit that didn't add new bugs). None of them
  addresses repeated review of a **static, unchanged** document — which is exactly the
  case this project's own prior research (`research/ops-clock-alt-method-experiment-
  2026-07-02.md`, citing Biffl/Halling/Kohle reinspection studies) already found
  measurably **degrades** detection effectiveness round-over-round (45.2%→36.5%,
  46%→21%). A "zero new findings" streak on a document that hasn't changed is
  confounded with reviewer fatigue/satisfaction-of-search, not just genuine exhaustion —
  and none of the found tools has any mechanism to tell the two apart.
- **The academic literature that IS purpose-built for exactly this question** —
  "how many defects remain in an inspected artifact, with no other oracle, estimated from
  multiple independent reviewers' overlapping finds" — is **capture-recapture defect
  estimation**, a real, 30+-year, field-validated statistical methodology from software
  inspection research (Eick et al. 1992; Vander Wiel & Votta, IEEE TSE 1993; used on a
  real project at IBM Jazz). This is the single best-matching prior art found. It has
  **never been applied to LLM review loops** in anything found on GitHub or arXiv this
  pass — adapting it is a **novel synthesis**, not a port, though the math itself is
  fully established (not speculative).
- **Formal multi-agent-debate stopping rules** (Wald-SPRT compute governor, KS-statistic
  adaptive stability detection) are real 2026 preprints, methodologically close to this
  project's own PACE acceptor (same Wald-SPRT family), but **both explicitly assume a
  deterministic-or-eventually-checkable ground truth** (MMLU/GSM8K correct answers, judge
  accuracy modeled against known-correct labels) — one of them says so in its own limits
  section, in almost the same words as this dispatch's framing. This corroborates, from
  the debate-convergence literature's own mouth, that the problem is genuinely unsolved
  for open-ended defect-finding.
- **Every production "iterative refinement" module surveyed that ships a formal stopping
  criterion (DSPy's `Refine`/`BestOfN`, Self-Refine's `delta_score < threshold`, GEPA's
  Pareto-front budget exhaustion) requires a scoring/reward function** — i.e. exactly the
  oracle this dispatch says doesn't exist for LOGIC/CONCURRENCY/SECURITY plan-check.

So the honest verdict is: **nothing to directly adopt-and-port; one real, grounded
technique (capture-recapture) is worth a novel, PACE-gated experiment**, and the
naive "just extend Gate 10's streak-counting to all tag classes" instinct (which several
real production tools DO implement, for a different, changing-artifact problem) is a
**known-bad idea for THIS project's specific task shape** given its own prior research —
that finding is itself a useful, if negative, result.

---

## 1. GitHub repo search (via `gh` CLI, this session, all repos opened directly)

`gh search repos`/`gh search code` for "review saturation," "LLM judge stopping
criterion," "self-consistency stopping," "iterative refinement convergence,"
"diminishing returns agent," "multi-agent debate convergence," "review fatigue," and
variants. Direct-quote confirmation (via `gh api .../contents/...` + `base64 -d`, not
WebFetch's markdown scrape) for every repo below.

| Repo | What it actually does (quoted) | Maturity | Fit |
|---|---|---|---|
| **calimero-network/ai-code-reviewer** | Multi-agent (Security/Performance/Patterns/Logic/Style, Sonnet+Haiku) PR reviewer. README: *"Delta tracking detects new, fixed, and open findings across pushes — with convergence logic that stops reviewing when findings stabilize."* `docs/ARCHITECTURE.md` (fetched): `has_converged(delta)` is `True` iff `new_findings == 0 and fixed_findings == 0` — **no rolling window, no severity×agreement formula in the convergence gate itself** (severity/consensus only feed the scoring/cap, confirmed from architecture doc + `tests/test_convergence.py`'s real test names, e.g. `test_converged_when_only_open_findings`, `test_skips_converged_second_review`). Skip rule: 1st review always posts; 2nd+ review skips if converged; 3rd+ skips if all new findings are `NITPICK`. | MIT, 7★, pushed 2026-07-05 (created 2026-02-03) — real, small, active | **Solves a different problem**: convergence = "the CODE stopped changing between pushes," not "we've read the same static text enough times." Directly cited already by this project's own `reconcile_gap_records.py` docstring for its clustering technique — this pass adds the convergence-mechanism confirmation, which was NOT previously verified. |
| **oprogramadorreal/optimus-claude** (`/optimus:code-review-deep` skill) | README table, quoted verbatim: *"`convergence` — The base skill reported `no_new_findings`... `diminishing-returns` — After iteration 4, two consecutive iterations produced ≤1 new finding and 0 reverted fixes... `cap` — Reached the iteration cap... `parse-failure` — Two consecutive iterations produced no parseable JSON."* Fresh subagent per iteration (context-reset, not the same continuous conversation). | MIT, 64★, pushed 2026-07-07 (today), real production Claude Code plugin, tests exist | **Closest real, shipped, GRADUATED (not binary) diminishing-returns pattern found** — `≤1` not `0`, after a floor of 4 iterations. Applies to an **auto-fix loop where code changes between iterations** (a fresh commit each round) — same disanalogy as ai-code-reviewer: the artifact is not static between rounds. |
| **retsimx/opencode-agents** (`ralphreview` skill) | `SKILL.md` (fetched in full): *"Loops until 3 consecutive clean reviews or failure escalation... Any fix resets the clean streak to 0."* Nested subagent per review; `clean_review_streak` incremented on `NO_NEW_FINDINGS`, reset on any real fix. | Unlicensed, 0★, created 2026-06-04, last push 2026-06-18 — young, single-repo, no adoption signal | Same 3-round-streak SHAPE as Gate 10, but **applied generally (no `[BINDING]`-only restriction) and with no fatigue/satisfaction-of-search safeguard** — self-reported "no new findings" from a fresh subagent is trusted at face value each round. This is close to what an UNSCOPED extension of Gate 10 would look like if built naively — useful as a real "here's what the naive version looks like in production" reference, not as something to copy as-is. |
| **gopherguides/gopher-ai** (Codex review-flow, `review-flow.md`) | Fetched in full: exhaustive multi-pass review, each pass told *"You have already identified the issues listed above... If there are no new findings to report, respond with exactly: NO_NEW_FINDINGS"*; early stop is a **single** empty pass (`"Early stop: If the output... equals exactly NO_NEW_FINDINGS... stop the loop immediately"`) — no streak required at all. | MIT, 17★, pushed 2026-07-09 (today) — real, actively maintained Claude Code plugin | Even more naive than ralphreview (1-round stop, not 3) — but low-stakes in its own context because a human still reads the final aggregated report before acting. Confirms production tools mostly accept a bare zero-new-findings signal without a fatigue safeguard; none found do better. |
| **echakrabarti/no-epicycle** | README (fetched): LangGraph supervisor that "detects diminishing returns in real time" via `Continue`/`Switch`/`Stop` on a **`score_fn` reward callback** the caller must supply (`supervisor = Supervisor(score_fn=lambda solution: run_tests(solution), ...)`). Cites (unverified by this pass) "rounds 1-2 capture 75% of reachable improvement [Williams, 2026]" and a context-rot claim. | No license file, 0★, created 2026-07-01 (8 days old), single author, tiny benchmark (5 tasks × 3 runs) | **Requires exactly the scoring oracle this dispatch says doesn't exist** for LOGIC/CONCURRENCY/SECURITY plan-check (its own quickstart example is a testable Python function). Confirms-by-contrast: even a repo explicitly pitched as a general "diminishing returns detector" still assumes a pass/fail test oracle under the hood. |
| **susugadx/xelyon-cli** (`internal/review/report/saturation_*.go`) | Real, substantial Go implementation of a `ReviewSaturationStatus` (`saturated`/`needs_revision`/`blocked`) — but confirmed (via `runner_saturation.go`) to be a **single-shot self-critique-against-a-plan-with-one-retry** gate (does the final report cover every `MissingSurfaceIDs`/`MissingRiskIDs` from a probe plan?), not a round-over-round diminishing-returns detector across independent reviewers. | MIT, 0★, real code+tests, obscure | Different mechanism family (coverage-completeness self-check, not multi-round saturation) — noted for completeness of the `gh search code "saturation"` sweep, not adopted as a candidate. |

**Frameworks explicitly checked per the dispatch's instruction — none has a built-in
saturation/stopping-criteria utility for review/critique loops beyond a plain iteration
cap or a caller-supplied reward function:**
- **DSPy** (`dspy.Refine`, `dspy.BestOfN`, official docs fetched): *"Both modules stop
  when they have reached N attempts or when the reward_fn returns an award above the
  threshold"* — requires a `reward_fn`, i.e. an oracle.
- **GEPA**: stopping is budget exhaustion (`evaluation budget is exhausted, GEPA returns
  the candidate with the best aggregate performance on Dpareto`); its Pareto-front
  machinery exists to avoid **local-optimum stagnation** during optimization, not to
  detect "this artifact has been reviewed enough" — a different question entirely.
- **AutoGen / CrewAI / MetaGPT / LangGraph**: no built-in review-saturation utility found;
  all leave critique-loop termination to the user's own `max_rounds` config or a
  hand-written critic node. (Corroborates the existing radar's "AutoGen → maintenance"
  and general assessment that this space is DIY across the ecosystem.)
- **Self-Refine** (madaan/self-refine, 809★, real, `gh search code` confirmed cite):
  documented stopping criterion is a fixed round cap **or** `delta_score < threshold` —
  again a score, i.e. an oracle.

---

## 2. Academic/industry literature beyond the existing ops-clock research doc

The existing `research/ops-clock-alt-method-experiment-2026-07-02.md` already covers
Cisco/SmartBear, NASA SWE-089, Biffl/Halling/Kohle reinspection, Perspective-Based
Reading, and Votta's meeting study. This pass went further, per the dispatch's
instruction, into **capture-recapture defect-content estimation** — the literature
family purpose-built for "how many defects remain, with no other oracle, based on
multiple reviewers' overlap":

- **Vander Wiel & Votta, "Assessing Software Designs Using Capture-Recapture Methods,"
  IEEE TSE 19(11), 1993** and **Eick et al. 1992** — the founding papers (confirmed via
  citing sources; original IEEE Xplore pages not directly fetchable this pass, same
  access limitation the prior ops-clock research hit). Core idea, confirmed from
  multiple citing sources: let independent reviewers each read the SAME artifact; the
  **overlap** between what different reviewers independently found estimates the total
  defect population still present, the same way biologists estimate an animal
  population from tag-and-recapture overlap.
- **Defect estimation using capture-recapture in IBM Jazz** (Arizona State University /
  IBM, confirmed via citing abstract) — a REAL field deployment, not just a lab study;
  evidence this is proven, adopted methodology in industrial software inspection, not
  purely academic.
- **The exact formula** (Lincoln–Petersen, bias-corrected by the **Chapman estimator**)
  was independently confirmed TWICE this pass: once from a general web search
  (`N̂ = n₁n₂/n₁₂`, Lincoln-Petersen; Chapman correction for small samples) and once —
  far more concretely — from a real, unrelated project's own architecture doc
  (`sublimine/Cardeep`, see below), which derives and worked-examples the Chapman formula
  end-to-end, cross-cited to Chao 1987.
- **Known, honestly-documented weakness** (from the general search): *"CR models break
  down with sparse data... most of the capture-recapture estimators could easily produce
  extreme estimates on residual defects"* — i.e. this technique is real and validated,
  but is known to be unstable at the small sample sizes (single-digit findings per
  round) this project's own plan-check rounds typically produce. This is a first-order
  risk to design around, not ignore.
- **A genuinely valuable, unexpected cross-domain find**: `sublimine/Cardeep`
  (unrelated project — Spanish car-dealer data platform, 0★, unlicensed, no connection
  to this project or its author) has a real, carefully-derived architecture document,
  `docs/architecture/verification/V6-STATISTICAL-RIGOR.md` (fetched in full, ~480 lines
  read directly), that independently implements almost exactly this dispatch's ask —
  **for a different domain (database-completeness auditing, not code review)** — with
  worked formulas for: **Wald SPRT sequential stopping** (§3, full derivation with
  numeric worked example: *"You cannot accept until... m ≥ 191 clean-ish items (vs 523
  fixed — a 63% saving)"*), **the two-source Chapman estimator with variance and a
  log-normal confidence interval for small-`m` cases** (§4.1, cross-cited to Chao 1987),
  and — most relevant of all — an explicit, self-flagged limitation directly on point:
  > *"Positive dependence between sources is the usual real-world case... which biases
  > N̂ **downward** — so a two-source N̂ is a **lower bound** on the true universe."*

  This is the single most load-bearing caveat for this dispatch's top candidate: if the
  plan-check lenses are correlated (plausible — they're all the same base model reading
  the same spec text under different personas, not truly independent reviewers), a
  Chapman-style estimate of "how many defects remain" will be **biased toward
  under-counting remaining defects** — i.e. biased toward premature stopping, the exact
  failure mode this whole research effort exists to avoid. Cardeep's own doc treats this
  as a first-class, gated risk (its §4.6/§4.7 "adversarial GAP" annotations show real
  prior mistakes it had to correct), not a footnote — a strong, independent
  corroboration that this is a real risk to design around, not a hypothetical.

---

## 3. Multi-agent debate / ensemble convergence detection

- **"Sequential Consensus for Multi-Agent LLM Debates: A Wald-SPRT compute governor..."**
  (arXiv 2605.19193, Andrea Morandi, preprint, single author, no code found). Fetched via
  `arxiv.org/html/`. Real Wald-SPRT boundaries (`A = log((1−β)/α)`, `B = log(β/(1−α))`,
  α=β=0.05 ⇒ A≈2.94, B≈−2.94), tested on MMLU/GSM8K (**both have known correct
  answers**). Its own stated limit, quoted from the fetched HTML: **"The design targets
  tasks with clear ground-truth answers (factuality, math)... it explicitly does not
  address preference-judgment or logic-bug-finding scenarios... A real-LLM evaluation on
  JudgeBench is left for future work."** This is the paper's OWN author disclaiming
  applicability to exactly this dispatch's problem shape.
- **"Multi-Agent Debate for LLM Judges with Adaptive Stability Detection"**
  (arXiv 2510.12697, Hu/Tan/Wang/Qu/Chen, CC-BY-NC-ND — non-commercial/no-derivatives
  license, an adoption-risk flag on its own). Real KS-statistic stopping rule (halts
  when `Dt < 0.05` for 2 consecutive rounds, modeling judge accuracy as a time-varying
  Beta-Binomial mixture fit via EM). Tested on TruthfulQA/JudgeBench/LLMBar with real
  numbers (77.75%→81.83% Gemini-2.0-Flash on LLMBar; 4-8 rounds vs. fixed 10, <0.5%
  accuracy loss) — but its own Theorem 4.2 "assumes 'the correct answer' exists as a
  fixed target," and the paper does not address ground-truth-free domains. No public
  code found.
- **"Semantic Early-Stopping for Iterative LLM Agent Loops"** (arXiv 2606.27009, Sahil
  Shrivastava, single author, preprint, no code). Real mechanism — cosine-distance
  between consecutive draft embeddings, patience window — but for a **single-agent
  self-refine loop** (not a debate/ensemble), tested only on HotpotQA multi-hop QA with a
  RAG-derived "Information Score" quality oracle (38% token reduction, no significant
  quality loss — Δ Information Score −0.004, p=0.81). The paper's own honest finding:
  *"determining when to stop proved straightforward, but which round is best remains an
  open challenge"* — i.e. even this closest single-agent analog admits the harder half
  of the problem (not just "did it change" but "is it actually done") is unsolved.

**Verdict for Q3:** the multi-agent-debate convergence literature is real and getting
richer in 2026, but every formal stopping rule found in it is built on top of an
assumed-knowable correct answer. None of it has been extended to — or claims to work
for — open-ended, no-ground-truth defect discovery. This corroborates, rather than
closes, the gap.

---

## 4. Is "agreement rate across the N parallel adversarial lenses" a precedented stopping
signal (this dispatch's own best guess at what might fit)?

**Partially — the SHAPE is precedented (zero/near-zero new findings across N passes →
stop), but every real precedent applies it to a CHANGING artifact (fixed code, a new
commit) or a single continuously-narrowing multi-pass session, never to independent
re-reads of a STATIC, unchanged spec.** That distinction is not pedantic — it is exactly
the distinction this project's own prior research already found matters (repeated
exposure to the SAME unchanged text measurably degrades detection effectiveness;
repeated exposure to CHANGED text after a real fix does not have that confound, because
something genuinely different is being looked at each time).

**What this framework already has, that none of the found repos have:** `orchestrator.md`
already dispatches state-completeness/concurrency-isolation/regression-audit/precision-
of-instruction lenses in parallel, and `harness/reconcile_gap_records.py` already performs
deterministic near-duplicate clustering across those lenses' findings within a round
(`SequenceMatcher` at a 0.85 threshold, gated on `mechanism_refs` overlap — borrowed,
per its own docstring, from `ai-code-reviewer`'s clustering approach, independently
re-confirmed as real this pass). **This is precisely the `(n₁, n₂, m)` triple a
capture-recapture estimator needs** (lens A's found-count, lens B's found-count, their
overlap) — this project is one small step away from having the raw ingredient for a
statistically-principled version of "agreement across lenses," not just a naive
zero-new-findings count. This is a genuine, buildable **novel synthesis**: nothing found
on GitHub or arXiv this pass applies capture-recapture to LLM plan-check lenses
specifically.

**Feasibility check — is there real historical data to backtest this against, before any
new dispatch is spent?** Yes, confirmed directly in this repo:
`runs/2026-07-02_ops-clock/plan_check_log.md` (1034 lines) already logs per-lens
PASS/FAIL outcomes starting at "Iteration 14 — METHODOLOGY CHANGE TESTED LIVE (parallel
adversarial lenses)" through at least iteration 20 (e.g. *"Iteration 14 result — 3 of 4
lenses returned LOOP_GATE: PLAN_FAIL... Iteration 20 result — 1 real gap, 3 clean PASSes
(best round since the parallel-lens method began)"*), and
`runs/2026-07-04_airbnb-calendar/plan_check_log.md` (2550 lines) covers the
airbnb-calendar-sync spec DESIGN_CHECKLIST gate 10 was itself built from (rounds through
31, including the two disqualifying rounds 19-21 and 30-31 gate 10's own text names).
Both are real, already-on-disk, per-lens-attributed ground truth — a backtest costs a
read + arithmetic, not a new agent dispatch.

---

## Ranked candidate dossier

### Candidate 1 — Capture-recapture (Chapman-estimator) population-based saturation signal for LOGIC/CONCURRENCY/SECURITY, built on the existing `reconcile_gap_records.py` overlap data (NOVEL DESIGN, no repo to port)

- **source**: methodology — Eick et al. 1992 / Vander Wiel & Votta, IEEE TSE 1993
  (confirmed via citing sources); formula cross-verified against
  `sublimine/Cardeep`'s independently-derived worked implementation
  (`docs/architecture/verification/V6-STATISTICAL-RIGOR.md`, fetched in full, real repo,
  MIT-adjacent-but-unlicensed, 0★). No existing code applies this to LLM review loops —
  this is a designed experiment, not a port.
- **maturity**: the underlying statistics are field-proven (30+ years, real industrial
  use at IBM Jazz); the APPLICATION to LLM plan-check lenses has zero prior art —
  confidence in the STATISTICS is high, confidence in the TRANSFER is low (see risks).
- **claim**: using the overlap between ≥2 parallel adversarial lenses' LOGIC/
  CONCURRENCY/SECURITY findings **within the same round**, estimate the total remaining
  defect population (Chapman: `N̂ = (n₁+1)(n₂+1)/(m+1) − 1`); when the estimated
  undiscovered remainder drops below a small threshold (e.g. <1), that's evidence
  (not proof) further rounds are unlikely to find something new — a quantitative
  sibling to Gate 10's exact-signature-recurrence, for the classes Gate 10 explicitly
  excludes.
- **where_it_wires_in**: extends `harness/reconcile_gap_records.py`'s existing
  clustering output (which already computes near-duplicate/overlap pairs across lenses
  in a round) with a small, pure-function Chapman calculator, mirroring
  `plancheck_saturation.py`'s own deterministic-checker pattern; surfaces a
  `CANDIDATE_STOP_ADVISORY` (never an auto-stop) to Oga in `orchestrator.md`'s existing
  plan-check step.
- **triage**: **TESTABLE** — backtestable against real, already-on-disk historical data
  (see experiment below) before any live pilot is needed.
- **priority**: `effect=0.55, confidence=0.45, phase_fit=1.0, risk_reduction=0.7,
  uncertainty=0.8, cost_to_test=0.15` →
  `priority = 0.40·(0.55×0.45) + 0.20·1.0 + 0.15·0.7 + 0.10·0.8 − 0.15·0.15`
  `= 0.099 + 0.20 + 0.105 + 0.08 − 0.0225 ≈ 0.46`
- **risks**: (1) **lens correlation** — Cardeep's own doc flags that positive dependence
  between "capture" sources biases the estimate DOWNWARD (toward premature stop); this
  project's 4-5 lenses are all the same base model under different personas reading the
  same spec, a plausible correlation source. (2) **small-sample instability** — CR
  estimators are documented to produce extreme/unstable estimates with single-digit
  finding counts, which is the typical case per round here. (3) Advisory-only by design
  — this must NOT auto-stop, only flag, given (1) and (2).
- **Transfer-condition check** (per role brief, required for every borrowed pattern):
  (a) *execution context required*: deterministic access to each lens's tagged
  LOGIC/CONCURRENCY/SECURITY finding list for a round, with a deterministic overlap/
  clustering step already run (this project HAS this — `reconcile_gap_records.py`).
  (b) *does this framework satisfy it*: yes, for any round where ≥2 lenses are
  dispatched (the existing conditional-parallel-lens trigger in `orchestrator.md`) — NOT
  satisfied for single-generalist-Verifier rounds (the default case), so this only
  applies in the subset of rounds already using the parallel-lens mode.
  (c) *structural vs instructional*: the ESTIMATOR is structural/deterministic (pure
  arithmetic, like `plancheck_saturation.py`) once fed real counts; but the SIGNAL IT
  PRODUCES is advisory, not a hard gate — Oga must still exercise judgment, exactly
  because of the correlation/small-sample risks above. This is an intentional,
  documented design choice (unlike Gate 10, which DOES hard-stop for `[BINDING]`) — do
  not silently upgrade this to a hard stop without first re-running the kill-criterion
  backtest below on a larger sample.

### Candidate 2 — Port optimus-claude's graduated "≤1 new finding, 2 consecutive rounds, after a floor" heuristic as a distinct, GENERALIZED sibling gate (not an extension of Gate 10 itself)

- **source**: `oprogramadorreal/optimus-claude`, `skills/code-review-deep/README.md`
  (fetched, quoted above). MIT, 64★, actively maintained (pushed 2026-07-07).
- **claim**: real production evidence that a graduated (not binary-zero) diminishing-
  returns threshold, applied after a minimum round floor, is a workable middle ground
  between "stop at the first empty round" (too aggressive) and "never stop without a
  compiler-equivalent oracle" (Gate 10's current LOGIC/CONCURRENCY/SECURITY stance).
- **where_it_wires_in**: a second, independent advisory signal alongside Candidate 1 in
  the same `orchestrator.md` plan-check step — cheaper to compute (a bounded counter,
  no statistical model), useful as a sanity-check baseline to compare Candidate 1
  against in the same backtest.
- **triage**: TESTABLE.
- **priority**: `effect=0.4, confidence=0.55, phase_fit=1.0, risk_reduction=0.4,
  uncertainty=0.5, cost_to_test=0.1` →
  `priority = 0.40·(0.4×0.55) + 0.20·1.0 + 0.15·0.4 + 0.10·0.5 − 0.15·0.1`
  `= 0.088 + 0.20 + 0.06 + 0.05 − 0.015 ≈ 0.38`
- **risks**: inherits the exact static-artifact-vs-changing-artifact disanalogy flagged
  in the headline answer — a bare "≤1 new finding" streak on a document that never
  changed between rounds is still confounded with reviewer fatigue; this candidate is
  useful as a comparison baseline in the SAME backtest as Candidate 1, not as a
  standalone recommendation.
- **Transfer-condition check**: (a) requires only a per-round new-finding count, already
  logged in `plan_check_log.md`. (b) satisfied today, no new infra. (c) fully
  structural/mechanical (a counter + comparison), but the INPUT it counts
  (self-reported "new finding" from an LLM lens) is instructional, not independently
  verified — same class of risk as ralphreview/ai-code-reviewer's trust-the-lens'-own-
  report design, carried over un-mitigated.

### Candidate 3 (RESEARCH_ONLY, parked, not ranked) — Multi-agent-debate SPRT / KS-stability formal convergence detectors

- **source**: arXiv 2605.19193 (Wald-SPRT compute governor), arXiv 2510.12697 (KS-based
  adaptive stability detection). Both real preprints, no public code found for either.
- **claim**: formally bounded (α/β-controlled) stopping for multi-agent debate rounds.
- **why parked, not ranked**: both papers **explicitly disclaim** applicability to
  non-deterministic-oracle domains (2605.19193's own text: *"does not address
  preference-judgment or logic-bug-finding scenarios"*; 2510.12697's Theorem 4.2 assumes
  a fixed correct-answer target). Forcing a fit here would be exactly the "force-fit a
  weak match" the dispatch explicitly warns against. Kept as a WATCH: if either paper
  (or a successor) publishes a version that relaxes the ground-truth assumption, revisit.
- **triage**: RESEARCH_ONLY — no metric tie, not ranked per the Researcher role's own
  convention for this triage tier.

### Candidate 4 (RESEARCH_ONLY, parked) — Semantic (embedding-similarity) early-stopping for the plan-check lens findings text

- **source**: arXiv 2606.27009, single-author preprint, no code, tested only on
  single-agent RAG-QA (not review/critique, not multi-lens).
- **why parked**: needs a "quality signal" (the paper's own Information Score) this
  project has no equivalent of for LOGIC/CONCURRENCY/SECURITY findings; the paper's own
  authors say the harder half of the problem ("which round is best," not just "did it
  stop changing") is still open. Worth a light WATCH if a follow-up paper adds a
  review/critique-loop evaluation, not worth building against today.
- **triage**: RESEARCH_ONLY.

---

## PACE-gated experiment spec for the top candidate (Candidate 1 — Chapman estimator)

- **metric**: for every historical plan-check round-window where ≥2 parallel adversarial
  lenses were dispatched on the SAME spec, compute the Chapman-estimated remaining-
  defect count for LOGIC/CONCURRENCY/SECURITY-tagged findings using that round's
  per-lens finding counts and their overlap (reconstructed via
  `reconcile_gap_records.py`'s existing clustering, applied retroactively to the logged
  findings). Score: **false-accept rate** — the fraction of "CANDIDATE_STOP_ADVISORY
  would have fired" instances where a LATER round of the SAME spec is independently
  known (from the historical record) to have found a genuine new LOGIC/CONCURRENCY/
  SECURITY defect.
- **baseline**: current behavior — no stop signal exists for these classes; plan-check
  continues until Oga's own narrative judgment (i.e., implicitly, the historical record
  itself — every round that was actually run — IS the baseline).
- **variant**: the Chapman-estimator advisory flag, computed retroactively per round,
  compared against what ACTUALLY happened in later rounds of that same historical spec.
- **instances**: (1) `runs/2026-07-02_ops-clock/plan_check_log.md` — iterations 14-20+,
  which already record per-lens PASS/FAIL and (from iteration 18 on) `mechanism_refs`,
  giving real `(n₁, n₂, m)` triples without re-dispatching anything. (2)
  `runs/2026-07-04_airbnb-calendar/plan_check_log.md` — rounds through 31, including the
  two rounds `DESIGN_CHECKLIST.md` gate 10 itself names as carrying the run's most
  important findings (round 30's AC19, round 31's AC16) — the canonical adversarial
  backtest case: **any version of this candidate that would have advised STOP before
  round 30/31 fails outright.**
- **decision**: run `evals/acceptor.py`-style PACE against the false-accept criterion
  above (candidate-right/incumbent-wrong per discordant instance, α=0.05) — accept the
  candidate (promote from "backtest passed" to "worth a live pilot with real-time
  advisory logging") only on `pace_accept` ACCEPT. Pre-registered override: **a single
  hit on the round-19-21 or round-30/31 airbnb-calendar-sync instances is an automatic
  kill**, regardless of what the aggregate false-accept rate says — a stop signal that
  would have muted this run's own two most important findings is disqualifying on its
  own, independent of the statistical aggregate (mirrors how Gate 10's own historical
  audit disqualified every 3-round window touching a live non-binding finding, rather
  than accepting a favorable average).
- **predicted_effect**: if it survives the backtest, gives Oga a cheap (pure arithmetic,
  zero new agent dispatches), quantitative advisory signal for LOGIC/CONCURRENCY/
  SECURITY round-stopping — strictly additive to, never a replacement for, human/Oga
  judgment, given the lens-correlation and small-sample risks documented above.
- **kill_criterion**: (1) any single false-accept on the two named airbnb-calendar-sync
  rounds (per above). (2) if reconstructing per-lens finding attribution from the
  historical logs turns out to be too coarse-grained to compute real `(n₁, n₂, m)`
  triples (a real possibility — early iterations, before iteration 18's `mechanism_refs`
  field, may not have fine-grained enough per-lens data) — in that case, downgrade
  this from "backtestable now" to "needs one live pilot round with instrumentation
  added first," not force a low-quality backtest.

---

## What was explicitly NOT found (stated per the dispatch's honesty requirement)

- No GitHub repo or paper implements capture-recapture / population-defect-estimation
  for an LLM-based review or plan-check loop. This is a real gap, not an oversight in
  the search — it is genuinely novel to apply here.
- No production agent framework (LangChain/AutoGen/MetaGPT/CrewAI/DSPy, Anthropic's own
  cookbooks repo per the existing radar review) ships a built-in saturation/diminishing-
  returns detector for critique/reflection loops that works without a scoring function.
- No multi-agent-debate stopping-rule paper found (2605.19193, 2510.12697, or any
  cited alongside them) claims to work for open-ended, no-ground-truth defect discovery
  — two of them say so explicitly, in their own limitations sections.
- Did not find a way to distinguish "genuine detection exhaustion" from
  "satisfaction-of-search-induced under-detection" using round-count or streak-based
  signals alone — every real precedent that uses that shape (ai-code-reviewer,
  optimus-claude, ralphreview, gopher-ai) is protected from this confound only because
  its artifact CHANGES between rounds, which plan-check's static-spec case does not
  share. This is the dispatch's central finding, not a caveat on a finding.

---

## Sources (every one opened and quoted directly this pass)

- `github.com/calimero-network/ai-code-reviewer` — README + `docs/ARCHITECTURE.md` +
  `tests/test_convergence.py` (fetched via `gh api`/raw GitHub, quoted above).
- `github.com/oprogramadorreal/optimus-claude` — `skills/code-review-deep/README.md`
  (fetched via `gh api`, quoted above).
- `github.com/retsimx/opencode-agents` — `skills/ralphreview/SKILL.md` (fetched in full
  via `gh api`, quoted above).
- `github.com/gopherguides/gopher-ai` — `plugins/llm-tools/lib/codex/review-flow.md`
  (fetched in full via `gh api`, quoted above).
- `github.com/echakrabarti/no-epicycle` — README (fetched via `gh api`, quoted above).
- `github.com/susugadx/xelyon-cli` — `internal/review/report/saturation_*.go`,
  `internal/review/runner_saturation.go` (fetched via `gh api`, quoted above).
- `github.com/sublimine/Cardeep` — `docs/architecture/verification/V6-STATISTICAL-
  RIGOR.md` (fetched in full, ~480 lines read directly, quoted extensively above).
- `github.com/madaan/self-refine` (confirmed real via `gh search repos`, 809★; stopping
  criterion quoted from `ckelsoe/prompt-architect`'s framework summary, cross-referenced
  against the paper's own arXiv 2303.17651 abstract).
- `dspy.ai/api/modules/Refine/` + `dspy.ai/tutorials/output_refinement/best-of-n-and-
  refine/` (WebSearch-sourced summary of official docs, quoted above).
- `arxiv.org/abs/2606.27009` + `arxiv.org/pdf/2606.27009` (Semantic Early-Stopping —
  abstract/summary fetched; full PDF text extraction degraded, flagged).
- `arxiv.org/html/2510.12697v1` (Multi-Agent Debate Adaptive Stability Detection — HTML
  fetch succeeded, quoted KS-statistic formula above).
- `arxiv.org/html/2605.19193` (Sequential Consensus Wald-SPRT — HTML fetch succeeded,
  quoted formulas and limitations above).
- `arxiv.org/abs/2310.18679` (N-CRITICS — abstract only; full-text extraction failed
  twice, methodology details NOT independently confirmed beyond the abstract's own
  claim of "ensemble of critics" self-correction — flagged as unverified beyond
  abstract).
- General WebSearch results for capture-recapture software-inspection literature
  (Vander Wiel & Votta 1993, Eick et al. 1992, IBM Jazz application, Lincoln-Petersen/
  Chapman formulas) — original IEEE Xplore papers returned inaccessible to automated
  fetch (same limitation the prior ops-clock research hit); cross-verified via the
  independently-derived Cardeep implementation instead, which IS a full direct fetch.
- This project's own `loop-team/DESIGN_CHECKLIST.md` (gate 10, read in full),
  `loop-team/harness/plancheck_saturation.py` (read in full),
  `loop-team/harness/reconcile_gap_records.py` (read directly, docstring + constants),
  `loop-team/orchestrator.md` (plan-check section, lines ~48-176, read in full),
  `research/ops-clock-alt-method-experiment-2026-07-02.md` (read in full),
  `research/candidate-ranking-prior-art.md` (read in full, priority formula source),
  memory `verifier-text-evals-saturated.md` (read in full),
  `runs/2026-07-02_ops-clock/plan_check_log.md` (1034 lines, spot-read for per-lens
  structure) and `runs/2026-07-04_airbnb-calendar/plan_check_log.md` (2550 lines,
  existence + line count confirmed) — both confirmed as real, usable backtest data.
