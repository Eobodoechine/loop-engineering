# PACE Testability & Power Analysis — What Can Actually Be Tested Against the Existing Corpus

**Date:** 2026-07-16
**Mode:** A (loop-improvement). Read-only analysis.
**Question:** Of the four candidate policy changes surviving the planning-stop-governor kill, which are PACE-testable against the corpus we already have — and what is the one test worth running?
**Answer in one line:** **None of the four are PACE-testable as backtests.** Three fail on the oracle, one is the wrong instrument, one has n=1. But the corpus surfaced a **different, better-powered, higher-value measurement** (n=927) that no dossier has proposed, and which **blocks the SYNTHESIS's own Recommendation #8**.

**Predecessor:** `research/2026-07-16-planning-stop-governor-SYNTHESIS.md` (and its five source dossiers). Not redone here; this builds on it and **corrects two of its claims**.

---

## 0. Headline findings (ranked by consequence)

1. **`min_discordant=5` is dead code.** At the default `alpha=0.05`, the wealth threshold already requires **≥8** discordant pairs for *any* ACCEPT, at *every* legal `lam ∈ (0,1)`. The correct power question is never "does it clear 5?" — it is "does it clear **8**, at a **≥63.09%** win rate?" Every power claim in this repo that cites 5 as the bar is understating it by 60%.
2. **The reconciler's duplicate-identity function has an apparently ~100% false-negative rate on cross-lens duplicates.** Measured: **0 of 2,491** cross-lens pairs reach the 0.85 merge threshold; **max observed similarity = 0.338**. A confirmed true duplicate scores 0.338. Therefore `f₁ = 613/613 = 100%` is a **structural artifact, not a property of the lenses**.
3. **Consequence: SYNTHESIS Rec #8 ("measure φ̄ first") is blocked by Rec #7 (build the finding-identity function).** The SYNTHESIS lists these as independent recommendations. They are **sequentially dependent**. φ̄ is not measurable on this corpus today.
4. **Nnamdi's Part-3 prediction is CONFIRMED but for a partly wrong reason — and the true reason is stronger.** The 84:16 reproduces only under one of two scorings; under the other it is 16:0. Either way REJECT. The deeper result: under that scoring **every pair is discordant by construction**, so the PACE statistic is an *algebraic re-encoding of h(k)* — a number already on disk. The test is **mis-specified, not underpowered**.
5. **Retrospective PACE is exploitable, demonstrated on this corpus.** At round 1 (n=52, W=10), ordering the pairs wins-first yields **ACCEPT** for a stop rule that is **wrong 81% of the time**. Under random ordering it accepts 0.000% of the time. Any backtest needs a **pre-registered, data-independent ordering**.

---

## PART 1 — The mechanism, pinned from source

**File:** `<HOME>/Claude/loop/loop-team/evals/acceptor.py` (122 lines, no third-party deps).

### 1.1 What `pace_accept` actually computes

**It is not McNemar's test. It is not an exact binomial test.** It is a **paired testing-by-betting e-process** (a test martingale) whose validity rests on **Ville's inequality**, not on a chi-square or binomial reference distribution.

It shares McNemar's **data reduction** — discard concordant pairs, use only discordant ones — but replaces the inference entirely. The docstring is explicit and accurate (lines 11–23):

> ```
>   - Evaluate incumbent and candidate on the SAME instances (paired).
>   - Discard concordant pairs (both right or both wrong). For each DISCORDANT
>     pair, w=1 if the candidate wins, else 0.
>   - Bet: E <- E * (1 + lam*(2w-1)), starting E=1 (a test martingale).
>   - ACCEPT the first time E >= 1/alpha (and after a minimum number of discordant
>     pairs); otherwise REJECT on budget exhaustion -- fail-safe = keep incumbent.
> ```

The operative loop (lines 57–67), quoted verbatim:

```python
    for inc, cand in pairs:
        peeks += 1
        if cand == inc:
            continue  # concordant tie -> discard, no bet
        discordant += 1
        w = 1 if cand > inc else 0
        E *= (1 + lam * (2 * w - 1))
        trajectory.append(E)
        if E >= threshold and discordant >= min_discordant:
            return AcceptResult("ACCEPT", E, discordant, peeks, threshold,
                                alpha, lam, "wealth crossed 1/alpha", trajectory)
```

The guarantee it buys (docstring lines 19–23): under H0, `E` is a non-negative supermartingale started at 1, so `P(E ever >= 1/alpha) <= alpha` **at every stopping time**. That is what licenses unlimited peeking and defeats dev-set p-hacking. It is a *one-sided* test: it can only ever ACCEPT the candidate; the incumbent wins by default. There is no way to conclude "the incumbent is better."

### 1.2 What EXACTLY is a "pair"

**Required shape:** an iterable of 2-tuples `(incumbent_score, candidate_score)`.

**Type:** "Scores may be 0/1 correctness flags or **any comparable numbers**" (docstring, lines 38–40). The code only ever uses `==` and `>`, so any totally-ordered type works. Three cases:

| condition | meaning | effect |
|---|---|---|
| `cand == inc` | concordant tie | **discarded**, no bet, `discordant` not incremented |
| `cand > inc` | candidate wins | `w=1` → `E *= (1+lam)` |
| `cand < inc` | candidate loses | `w=0` → `E *= (1-lam)` |

**Magnitude is discarded.** `(0, 1)` and `(0, 1000)` are the identical bet. PACE consumes only the *sign* of the difference. A candidate that wins narrowly and loses catastrophically looks identical to one that wins narrowly and loses narrowly.

The canonical worked definition, from the real spec at `loop-team/runs/2026-07-16_model-routing-pace/specs/spec.md:389`:

> "A PACE pair is the same evaluation `case_id` under incumbent and challenger."

### 1.3 What `lam=0.5` does — traced, not guessed

`lam` is the **fixed bet fraction**: the proportion of current wealth wagered on each discordant pair. Traced through `E *= (1 + lam * (2*w - 1))`:

- `w=1` → `E *= (1 + 0.5)` = **×1.5**
- `w=0` → `E *= (1 - 0.5)` = **×0.5**

Confirmed by the docstring (line 42): *"lam: bet fraction in (0,1) (default 0.5 -> win x1.5, loss x0.5)."* Validated by `if not 0 < lam < 1: raise ValueError`.

Three consequences worth naming:

- **It is Kelly-optimal for a true win probability p = 0.75** (Kelly: `lam* = 2p − 1`). If the candidate's true edge is at the break-even 0.63, `lam=0.5` **over-bets**.
- **It is fixed, not adaptive.** The PACE/testing-by-betting literature typically uses adaptive or mixture betting (ONS, aGRAPA). This is the simplest possible constant-fraction bet. That costs power but keeps the martingale property exactly.
- **It sets the win-rate floor.** See §1.5.

### 1.4 What `min_discordant=5` gates — and why it is dead code

**What it gates:** ACCEPT only. It appears in exactly two places:
1. Line 65 — the conjunct `and discordant >= min_discordant` in the ACCEPT condition.
2. Lines 68–70 — the REJECT **reason string** only.

**Decision values: exactly two — `"ACCEPT"` and `"REJECT"`.** There is no `INCONCLUSIVE`, no `CONTINUE`. This is a real consumer trap: a test with 3 discordant pairs returns **`REJECT`**, the same token as a genuinely refuted candidate. The two are distinguishable *only* by `.reason`:

```python
    reason = ("budget exhausted; wealth %.3f < %.1f" % (E, threshold)
              if discordant >= min_discordant
              else "too few discordant pairs (%d < %d)" % (discordant, min_discordant))
```

**The finding: `min_discordant=5` can never bind at the default `alpha=0.05`.** Maximum attainable wealth after D discordant pairs is `(1+lam)^D` (all wins). Reaching `1/alpha = 20` requires:

```
D_min = ceil( log(1/alpha) / log(1+lam) )
```

Measured across the legal `lam` range at `alpha=0.05`:

| `lam` | 0.1 | 0.25 | **0.5** | 0.75 | 0.9 | 0.99 |
|---|---|---|---|---|---|---|
| min wins to reach E≥20 | 32 | 14 | **8** | 6 | 5 | 5 |

**`D_min ≥ 5` for every `lam ∈ (0,1)`.** Driving it below 5 would need `(1+lam) ≥ 20^(1/4) = 2.115`, i.e. `lam ≥ 1.115` — outside the validated range. So the guard is unreachable at default alpha.

Verified empirically against the real function (all-wins sequences):

```
D=4  -> REJECT  wealth= 5.062  reason=too few discordant pairs (4 < 5)
D=5  -> REJECT  wealth= 7.594  reason=budget exhausted; wealth 7.594 < 20.0   <-- guard released, still rejects
D=7  -> REJECT  wealth=17.086  reason=budget exhausted; wealth 17.086 < 20.0
D=8  -> ACCEPT  wealth=25.629  reason=wealth crossed 1/alpha                  <-- the REAL floor
```

**The real floor at defaults is D ≥ 8, not 5.** `min_discordant` becomes live only at larger alpha (e.g. `alpha=0.5` → threshold 2 → 2 wins suffice → the guard binds), or when a spec sets it deliberately above the arithmetic floor — which the model-routing spec does (§1.7).

### 1.5 The win-rate floor (the power fact that actually matters)

Solving `W·log(1+lam) + (D−W)·log(1−lam) ≥ log(1/alpha)` for W at `alpha=0.05, lam=0.5`:

```
W ≥ 2.7268 + 0.63093·D
```

| D | 8 | 10 | 12 | 15 | 20 | 25 | 30 | 40 | 50 |
|---|---|---|---|---|---|---|---|---|---|
| **W needed** | 8 | 10 | 11 | 13 | 16 | 19 | 22 | 28 | 35 |
| **win rate** | 100% | 100% | 92% | 87% | 80% | 76% | 73% | 70% | 70% |

**Asymptotic floor: the candidate must win >63.09% of discordant pairs even with infinite data.** A candidate with a true 60% edge is *never* accepted at these settings, at any n. This is a `lam` artifact, not a statistical necessity — but it is the shipped default.

### 1.6 Order dependence — the constraint that governs every backtest

`pace_accept` returns **the moment** the running wealth crosses the threshold. The verdict therefore depends on the **running max**, not the final wealth — so it is **order-dependent**. Same multiset, opposite verdicts:

```
8 wins / 100 losses, wins FIRST  : ACCEPT  wealth=25.629  peeks=8
8 wins / 100 losses, losses FIRST: REJECT  wealth=2.0e-29 peeks=108
```

Under H0 with a natural/random order, the bound holds comfortably (measured 0.01%–0.68% accept over 20k shuffles at 8W/8L through 20W/20L; author's own selftest: FAR = **0.0375 ≤ α=0.05**, power(0.5 vs 0.85) = **1.000**). But **the analyst chooses the order in a backtest**, and an adversarial wins-first sort ACCEPTs *any* set with W ≥ 8 regardless of loss count.

> **Binding constraint on any retrospective PACE run: the pair ordering must be pre-registered and data-independent** (e.g. chronological by case id, fixed before outcomes are inspected). Otherwise the α guarantee — the entire reason to use this instrument — does not transfer. §3.3 demonstrates this exploit on our real corpus.

### 1.7 The sibling helpers

**`pairs_from_correctness(incumbent_correct, candidate_correct)` — line 75.** Zips two equal-length correctness sequences into score pairs. Raises `ValueError("incumbent/candidate correctness must be paired (equal length)")` on length mismatch — the only structural guard against unpaired data. Coerces via `int(bool(a))`, so any truthy value → 1. Intended use, per its docstring: *"two run_evals reports over the same cases."*

**`_selftest(...)` and its inner `campaign(p_inc, p_cand)` — line 97.** Monte-Carlo validation. `campaign` builds n=300 independent Bernoulli pairs and returns whether PACE accepted. Used twice: H0 (0.6 vs 0.6) must give FAR ≤ α; power (0.5 vs 0.85) should mostly accept. Note the power check is a **huge** effect — under independence ~50% of pairs are discordant with an 85% candidate win rate, far above the 63% floor — so `power=1.000` is not evidence of power at realistic effect sizes.

### 1.8 The real worked example

`loop-team/experiments/test_model_routing_pace_contract.py` + `loop-team/runs/2026-07-16_model-routing-pace/specs/spec.md` (862 lines). The frozen manifest (`_manifest()`, lines 42–50):

```python
"alpha": 0.005, "lambda": 0.5, "min_discordant": 16, "max_pace_units": 24,
```

with 10 hypotheses H01–H10, each `evaluation_case_ids` = 24 and `held_out_case_ids` = 12, disjointness enforced by `validate_pace_manifest`.

**This spec is the one place `min_discordant` is live.** At `alpha=0.005` (threshold 200) and `lam=0.5` the arithmetic floor is 14 wins; the spec sets `min_discordant=16` **above** it — a deliberate, correct choice.

But note the resulting bar: at D=16 the challenger needs **W≥15 (94%)**; at the D=24 cap it needs **W≥20 (83%)**. With `max_pace_units=24`, reaching D=24 requires *every* case to be discordant. This experiment is itself near-unpowered for anything but an overwhelming effect — which is presumably why the spec *also* pre-registers a separate held-out threshold (`challenger − incumbent >= 2/12 cases, no critical false-pass`, spec.md:283–292) rather than relying on PACE alone. **That belt-and-braces pattern is the right model for anything we build.**

---

## PART 2 — The corpus, counted

**Method.** `find` over `<HOME>/Claude/loop`, **content-hash deduplicated** (the prior dossier's `profile.py` used bare `rglob` and did not dedupe). Both run roots covered: `./runs/` and `./loop-team/runs/`, plus `./worktrees/` and `runs/.../preserved/lineage*/`.

### 2.0 Corpus inventory

| artifact | on disk | unique by content | notes |
|---|---|---|---|
| `plan_check_log.md` | **93** | 92 | 3 under `worktrees/`, 6 under `preserved/` |
| — with parseable `## Round N` | **60** | — | 53 excluding worktree/preserved |
| gap_record `.json`/`.jsonl` | **144** | **124** | 20 duplicate copies, all under `worktrees/` |
| **leaf gap records extracted** | **1,053** | — | across 9 distinct container shapes |
| reconciled files w/ `merged_items` | 55 | — | 613 merged findings |

The dispatch's estimates (~50 logs, ~42 gap_records) were low: the real numbers are **93 logs / 124 unique gap-record files / 1,053 records**. More data than expected — which makes the negative verdicts below more damning, not less.

Field presence across all 1,053 records:

| field | present | field | present |
|---|---|---|---|
| `lens` | **100.0%** | `severity` | 8.4% |
| `gap_type` | **100.0%** | `tag` | **7.4%** |
| `broken_assumption` | 100.0% | `tags` | 4.0% |
| `source_file` | 37.8% | `blocking_kind` | **3.0%** |

---

### (a) Oracle routing — **NOT-BACKTESTABLE (oracle undefined) + rigged sampling**

> *This is the one the dispatch most wanted. It fails, three independent ways. The dispatch asked me to be honest if the tagging can't support mechanical classification. **It cannot.***

**Finding 1 — `gap_type` carries almost no information.** It is 100% present and **93.4% a single value**:

| value | n |
|---|---|
| **`DESIGN`** | **984** (93.4%) |
| `INSTRUCTION` | 30 |
| `LOGIC` | 10 |
| `SECURITY` | 10 |
| `KNOWLEDGE` | 6 |
| `DESIGN [LOGIC]` | 3 |
| `CONCURRENCY` | 2 |
| **`BINDING`** | **2** |
| `CONTRADICTION / ORACLE`, `SCHEMA / BINDING`, `INPUT AUTHORITY / BINDING`, `REDUCER / NON-DETERMINISM`, `COMPLETION ORACLE`, `NON-FALSIFIABLE ACCEPTANCE` | 1 each |

**There is no controlled vocabulary.** `gap_type` is free text: composite values (`SCHEMA / BINDING`), one-off inventions (`NON-FALSIFIABLE ACCEPTANCE`), and a bracket-tag leaking into the type (`DESIGN [LOGIC]`). Three competing fields carry overlapping vocabularies — `gap_type` (100%), `tag` (7.4%), `tags` (4.0%) — and even *within* `tag`, the same concept appears twice: **`'[LOGIC]'` (28) and `'LOGIC'` (26)**.

**Finding 2 — BINDING-class findings: n = 9.** Pooling every field, deduplicated: **9 distinct records out of 1,053 (0.85%)**. Even at face value that is a hair over the D≥8 floor — with zero margin, and only if every one is usable.

**Finding 3 (the structural kill) — there is no code to route to.** Of the 398 records carrying `source_file`, **398 are `.md` — 100.0%.** Not one points at a source file. `touches` values are spec-section identifiers (`AC-12`, `LIFECYCLE-1`, `SCHEMA-2`, `VERIFY-2`, `§TRANS`), 1,209 distinct free-text values.

This is what plan-check *is*: it reviews the **spec, before implementation**. The candidate policy "route it to the build/compiler" has **no artifact to act on**. The oracle "would a build/typecheck/import-check have caught this for free?" is not merely hard to compute — it is **undefined** on this corpus.

**Finding 4 — reading all 9 BINDING records confirms it from the other direction.** Not one describes a compile, type, or import error. Every one is an **absence-of-specification** finding:

- *"Unix path components may contain non-UTF-8 bytes. The spec requires lossless lexical byte paths but supplies no base64/escape representation."*
- *"No seed preimage, sample size, per-stratum allocation, ordering, replacement rule, or empty/small-stratum behavior is given."*
- *"Ok.payload has no axis-specific schema; the expected source key and cardinality set is undefined."*
- *"No canonical snapshot path, complete snapshot document, capture timestamp, source manifest schema… are supplied."*

**A compiler is structurally the wrong oracle for this class.** These findings are about what the spec **does not say**. A compiler validates that code **is well-formed**; it would happily compile an implementation that resolved each of these ambiguities arbitrarily — and *that arbitrary resolution is precisely the defect*. The counterfactual "the build would have caught it for free" is **near-always NO for the BINDING class by definition**, not by measurement.

**Finding 5 (the sampling kill, and it generalizes) — the corpus is conditioned on `incumbent_found = 1`.** Every record exists *because* the prose review found it. There is no record of what the prose review **missed**. So:

- incumbent (prose round) score = **1 by construction, on every instance**
- candidate (compiler) score = 0 (per Finding 4)
- ⇒ **every pair is `(1, 0)`. D = n, W = 0. Guaranteed REJECT, zero information.**

> **You cannot estimate a candidate's recall advantage from a sample drawn from the incumbent's successes.** The design measures only "does the compiler reproduce the prose reviewer?", which is guaranteed to lose and answers nothing about "is routing to the compiler cheaper/better?". This is the *same* selection bias the SYNTHESIS flagged for the hazard measurement (§1, "selection bias inflates the level"), in a more fatal form: there, it biased a level; here, it determines every pair.

**Verdict (a): NOT-BACKTESTABLE — oracle undefined (100% `.md`, no build exists at plan-check time), classification requires human judgment (n=9, no controlled vocabulary, 93.4% single-valued `gap_type`), and the sample is conditioned on the incumbent's own found-set.** Fixing the tags would not rescue it; findings 3 and 5 are independent of tagging.

---

### (b) Kind-diversity — **NOT-BACKTESTABLE-NEEDS-LIVE-PILOT** (confirmed, exactly as hypothesised)

**Count of historical cases where a mechanical detector and an LLM lens reviewed the same artifact: ZERO.**

All **63 distinct `lens` values across 1,053 records are LLM prose lenses.** Top of the distribution: `precision-of-instruction` (163), `state-transition-table` (159), `state-completeness` (127), `concurrency-isolation` (104), `regression-audit` (62). There is no `compiler`, `tsc`, `mypy`, `pytest`, `schema-validate`, or `import-check` lens anywhere.

I checked the five suspicious names individually — `implementation-proof`, `live-source`, `oracle`, `security-oracle`, `regression-oracle` — and **all five are LLM lenses emitting prose**, not mechanical detectors. (`security-oracle` is the closest: it reports *"empirically the assertion stays green with line 171 n[eutered]"* — an LLM lens that **used** a mutation check. But it is a prose record from an LLM arm, not a separate mechanical arm with an independent signal.)

Also worth recording: the lens vocabulary is free text with the same lens under up to five spellings — `precision-of-instruction` (163) / `precision of instruction` (22) / `standard-precision` (6) / `precision` (2) / `precision-reuse` (2); likewise `state-completeness` / `state completeness`, `concurrency-isolation` / `concurrency/isolation`. Any future mechanical analysis over `lens` needs normalization first.

**Verdict (b): NOT-BACKTESTABLE-NEEDS-LIVE-PILOT. n=0. There is no paired data because the candidate arm has never been run.** This is not a power problem; it is an absence-of-data problem. The dispatch's hypothesis is confirmed.

---

### (c) Artifact-size cap — **WRONG-INSTRUMENT** (confirmed) **and the right instrument is also blocked**

**Is spec size recorded per-run? NO.** Zero files contain `spec_lines`, `spec_size`, `spec_bytes`, or `artifact_size`.

**But it is measurable.** A spec `.md` is findable on disk for **48 of 53** runs with a parseable plan-check log.

**Confirming the dispatch's framing: PACE is the wrong instrument.** PACE requires two *policies* scored on the same *instance*. A size cap is a **continuous predictor** (size) against an **outcome** (rounds). There is no candidate arm to score without re-running each build with a capped spec. Paired testing does not apply. **The right instrument is a regression / rank correlation** — or, for the causal claim, a prospective randomized cap.

**I ran the regression anyway (n=48):**

- **Spearman ρ = 0.448** (t = 3.40, df = 46 → p ≈ 0.001)
- Pearson r = 0.897 — *inflated*; the gap from ρ is the airbnb-calendar outlier (4,207 lines / 31 rounds)
- ρ² ≈ 0.20

**But the association is causally uninterpretable, and the fix is unobtainable.** The `spec.md` on disk is the **final** spec — after every round ratcheted criteria into it. The SYNTHESIS documents this arrow itself (§2): *"Capitulation ADDS a criterion. Nothing ever REMOVES one."* So **rounds → size** by the loop's own mechanism, and an observational size~rounds correlation cannot separate it from **size → rounds**.

De-confounding needs the **round-0 spec size**. It is **unobtainable**:

- `.gitignore:40-41` excludes **`runs/`** and **`loop-team/runs/`** — the entire run corpus is untracked.
- Tracked exceptions total 43 files: **2** `spec.md`, **1** `plan_check_log.md`, 20 gap_records.
- **Zero** run specs have any revision history. Round-0 size cannot be recovered for essentially any run.

**Verdict (c): WRONG-INSTRUMENT. The right instrument is regression — but the observational regression (ρ=0.448) is confounded by construction, and the de-confounding variable (round-0 spec size) is UNOBTAINABLE because `runs/` is gitignored.** A size cap can only be evaluated by a **prospective randomized trial**, or by first recording round-0 size going forward (a ~free logging change, and the cheapest durable improvement in this dossier).

---

### (d) Persistent-yield → rewrite — **UNDERPOWERED (n=1, need 8)**

**Nnamdi's prediction of ~1 is confirmed exactly. n = 1.**

A systematic sweep of the durable logs (`learnings.md`, `fix_plan.md`, `research/*.md`) for `NNN→NN lines` shrink events returns **exactly one**: `learnings.md:2717` — **TaxAhead 782→97**.

The sweep surfaced a **second, different** rewrite that must not be double-counted — the two are distinct patterns:

| | pattern | instance | outcome |
|---|---|---|---|
| **Rewrite-to-CUT** (SYNTHESIS Rec #2 / A1) | shrink the artifact because yield persists | TaxAhead 782→97 (`learnings.md:2717`) | worked |
| **Rewrite-to-INCORPORATE** | full `Write` rewrite to apply findings | `H-SPEC-REWRITE-DIFF-1` v2→v3 (`fix_plan.md:2695-2717`) | **introduced a defect** — silently dropped the entire `record_sigs` subsection |

Only the first is "persistent-yield → rewrite." **n=1 vs a floor of 8.**

**And the single instance is contaminated.** Per `learnings.md:2714-2717`, the 782→97 rewrite happened **off-log, inside a gap**: *"no round-6 dispatch trace anywhere (`trace.jsonl`'s last entry predates the spec's own file mtime) before the spec was rewritten 782→97 lines in that same gap."* It was an artifact of the **false-PLAN_PASS narrative incident**, not a deliberate policy decision with a recorded counterfactual. It is a **precedent**, correctly cited by the SYNTHESIS as such — but it is **not an experimental instance**, and it cannot be scored as one.

**Verdict (d): UNDERPOWERED (n=1, need ≥8). The lone instance is also off-log and confounded with a known incident.** 8× more data is needed; at ~1 occurrence per corpus-lifetime, that is years away. This must be adopted on judgement + literature (Petersson A1, Huang §5), or not at all — it will never be PACE-gated.

---

## PART 3 — The prediction, tested

> **Nnamdi's claim:** *"a stop rule pace-tested against the default 'always continue' policy LOSES ~84:16 on discordant pairs (from the measured flat hazard h(3)=0.84), so running it would burn tokens to reproduce a verdict we already have."*

**Verdict: the conclusion is CORRECT. The mechanism is partly wrong. The true reason is stronger than the stated one — and there is a live exploit the claim does not anticipate.**

### 3.1 First, the hazard reproduces exactly

Independent re-derivation (my own parser, plus content-hash dedup the original lacked):

| k | 1 | 2 | **3** | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| at risk | 52 | 33 | **19** | 11 | 5 | 2 |
| failed | 42 | 22 | **16** | 8 | 3 | 1 |
| **h(k)** | 0.81 | 0.67 | **0.84** | 0.73 | 0.60 | 0.50 |

**Identical to `2026-07-16-rational-metareasoning-stopping-theory.md` §3.7 to two decimals.** (I find 93 logs / 60 parseable vs their 92 / 59 — one log was added today; the table is unchanged. Dedup dropped only 1 byte-identical file.) **The measurement is reproducible and stable.** h(3) = 16/19 = 0.8421.

### 3.2 The 84:16 depends entirely on an unstated scoring choice

Everything turns on **what the score is** — which Nnamdi's claim does not specify. There are two candidates, and they disagree:

**Scoring A — recall ("did this arm surface a defect?"):**
- incumbent (continue) = 1 if round 3 found a defect, else 0
- candidate (stop) = **0 always** — it didn't run, so it found nothing

```
pairs n=19  candidate WINS=0  LOSSES=16  concordant TIES(discarded)=3
-> PACE REJECT   D=16   E=1.526e-05   needed W>=13 of 16, got 0
```

**It is 16:0, not 84:16.** The 3 no-defect rounds are **not candidate wins** — they are `(0,0)` **concordant ties that PACE discards**. Under recall scoring the candidate **cannot win a single discordant pair**, because stopping can never *find* what continuing did not.

**Scoring B — decision-correctness ("was this arm's call right?"):**
- incumbent correct ⟺ a defect existed; candidate correct ⟺ none existed

```
pairs n=19  candidate WINS=3  LOSSES=16  concordant TIES=0
-> PACE REJECT   D=19   E=5.150e-05   needed W>=15 of 19, got 3
   discordant split 16:3 = 84:16   <-- CLAIM REPRODUCED
```

**So the 84:16 is right if and only if decision-correctness scoring is intended.** Both scorings REJECT. The conclusion survives; the number only exists under one reading.

### 3.3 The correction that matters: the verdict is order-robust at round 3 — but the corpus *is* p-hackable at round 1

I initially derived a closed-form boundary `h* = 0.369 − 2.73/n` and it **mismatched the real acceptor**. My formula assumed *final* wealth; `pace_accept` returns on the **running max** (§1.6). My formula was wrong. Corrected, there are three zones:

- **W < 8** → REJECT under **every** ordering (max attainable wealth `1.5^W < 20`)
- **final wealth ≥ 20** → ACCEPT under every ordering
- **otherwise** → **the analyst's ordering decides**

Applying this to the real corpus under Scoring B:

| k | n | W | L | true win% | wins-first | losses-first | random (20k shuffles) |
|---|---|---|---|---|---|---|---|
| 1 | 52 | 10 | 42 | 19% | **ACCEPT** | REJECT | 0.000% |
| 2 | 33 | 11 | 22 | 33% | **ACCEPT** | REJECT | 0.005% |
| **3** | **19** | **3** | **16** | **16%** | **REJECT** | **REJECT** | **0.000%** |
| 4 | 11 | 3 | 8 | 27% | REJECT | REJECT | 0.000% |
| 5 | 5 | 2 | 3 | 40% | REJECT | REJECT | 0.000% |
| 6 | 2 | 1 | 1 | 50% | REJECT | REJECT | 0.000% |

**At round 3 — the round Nnamdi cites — W=3 < 8, so the verdict is REJECT under every possible ordering. His claim is not just right, it is order-robust.**

**But at round 1, the same corpus can be ordered into an ACCEPT for a stop rule that is wrong 81% of the time.** That is the retrospective p-hack, live, on our own data. It is invisible to anyone who reports only `.decision`.

### 3.4 The deepest reason — and why it is stronger than "we already have the verdict"

Under Scoring B, the two arms are **perfectly anti-correlated by construction**: the stopper is right exactly when the continuer is wrong. Therefore:

- **Every pair is discordant. D = n, always. Zero ties.** PACE's entire mechanism — discarding concordant pairs to concentrate power on informative ones — **does nothing**.
- **W = (1 − h(k))·n, exactly.** The win count is a deterministic function of the hazard.
- ⇒ **The PACE statistic is an algebraic re-encoding of h(k)**: `E = 1.5^((1−h)n) · 0.5^(hn)`.

**There is exactly one bit of information per instance — "did round k find a defect?" — and both arms' scores are determined by it. PACE cannot manufacture information that isn't there.** Running it computes a deterministic function of a number already sitting in `2026-07-16-rational-metareasoning-stopping-theory.md` §3.7.

**Nnamdi's conclusion — "burn tokens to reproduce a verdict we already have" — is exactly right, and this is the proof of it.**

### 3.5 The one thing the claim misses: the test is mis-specified, not merely redundant

Scoring B **silently prices a missed defect exactly equal to a wasted round** — both worth 1 unit. That 1:1 exchange rate is set **by fiat, in the scoring function**. But the exchange rate *is the entire question*. Set a missed defect at 10 wasted rounds and the stop rule loses far worse; set it at 0.1 and it could win.

**PACE cannot discover this rate. It is an input, not an output.** And once you supply it, the verdict follows by arithmetic — you still never needed PACE.

This is the SYNTHESIS's own hole, restated from the acceptor's side (§5, *Economics, not epistemics*): *"the proposal's `Q^m(s,E)` has three ingredients, and the proposal **omitted the cost term `c` entirely**."*

> **So: the stop-rule PACE test is not underpowered. It is mis-specified.** Its answer is fully determined by a parameter you must choose before running it. That is a stronger reason not to run it than "we already know the answer," because it means **no sample size would ever rescue it.**

---

## PART 4 — Verdicts and the one test worth running

### 4.1 Ranked verdict

| # | candidate | verdict | real n | why |
|---|---|---|---|---|
| 1 | **(a) Oracle routing** | **NOT-BACKTESTABLE** — oracle undefined | 9 BINDING records / 1,053 | 100% of `source_file` = `.md`; no build exists at plan-check time. `gap_type` 93.4% single-valued, free-text, no controlled vocabulary → classification needs a human. All 9 BINDING records are *absence-of-specification*, a class a compiler cannot catch **by definition**. And the corpus is conditioned on `incumbent_found=1` → every pair is `(1,0)` → guaranteed REJECT, zero information. |
| 2 | **(b) Kind-diversity** | **NOT-BACKTESTABLE-NEEDS-LIVE-PILOT** | **0** | 63/63 lens values are LLM prose lenses. No mechanical detector has *ever* reviewed any artifact here. No paired data exists because the candidate arm has never run. |
| 3 | **(c) Artifact-size cap** | **WRONG-INSTRUMENT** → regression, not PACE | 48 measurable | Confirmed: continuous predictor vs outcome, no candidate arm. But the right instrument is *also* blocked: ρ=0.448 is confounded (rounds→size, per SYNTHESIS §2's ratchet) and round-0 size is **UNOBTAINABLE** — `.gitignore:40-41` excludes `runs/`; 0 specs have revision history. Needs a **prospective randomized cap**. |
| 4 | **(d) Persistent-yield → rewrite** | **UNDERPOWERED (n=1, need 8)** | **1** | TaxAhead 782→97 only. Prediction confirmed. The lone instance is off-log (no dispatch trace) and confounded with the false-PLAN_PASS incident — a precedent, not an instance. Will never be PACE-gated. |
| — | **(Part 3) Stop rule vs always-continue** | **MIS-SPECIFIED** (worse than underpowered) | 19 @ round 3 | Verdict REJECT, order-robust at round 3. But every pair is discordant by construction → PACE re-encodes h(k) → zero new information. And the round/defect exchange rate is an input, not an output. No n rescues it. |

**The honest headline: none of the four are adequately powered as backtests, and the fifth is mis-specified. Do not run any of them.** That is a real result and it saves real money — it is exactly the outcome the dispatch pre-authorized.

### 4.2 The ONE test worth running

It is **not** any of (a)–(d). The corpus handed me something better while I was counting it.

**The finding.** The reconciler's duplicate-identity function is **`SequenceMatcher` char-level ≥ 0.85** over concatenated free prose (`broken_assumption + why_it_fails + proposed_fix`) — `reconcile_gap_records.py:65`, `_cluster_text():144`, `cluster_near_duplicates():225`. (The `mechanism_tracer` is a *different* stage: it detects **contradictions**, not duplicates. Duplicate identity is decided by the 0.85 threshold **exclusively**.)

Measured over **2,491 cross-lens pairs** from real multi-lens rounds:

```
min=0.003   median=0.027   mean=0.033   p90=0.054   p99=0.188   MAX=0.338
MERGE THRESHOLD = 0.85
pairs at/above threshold: 0 / 2491 = 0.000%
```

**Nothing can ever merge.** And here is the confirmed true duplicate that did not — two lenses, three shared `touches`, plainly the same defect:

```
sim=0.338  shared touches=['AC-20','FILES','LIFECYCLE-1']
  regression-audit-evidence: `PUBLICATION-1` says `I_g` covers the Final-Verifier input-bundle seal, while `VERIFY-2` says t...
  state-transition-table:    `PUBLICATION-1` says I_g covers the Final-Verifier input-bundle seal, while `VERIFY-2` says tha...
```

**Therefore `f₁ = 613/613 = 100%` is a structural artifact of the instrument, not a property of the lenses.** Across 55 reconciled files and 613 merged findings, **zero** were found by ≥2 lenses — in rounds that ran **5 distinct lenses**.

**Why this is the highest-value thing on the board — it resolves a live contradiction in the SYNTHESIS:**

- SYNTHESIS §2 asserts *"N lenses do not give N looks. They give ~2"* on **φ̄ = 0.391 borrowed from Kohli (arXiv:2605.29800)** — 9 frontier LLMs, 7 families, a **different task**.
- **Our own corpus measures cross-lens overlap = 0.** Those are in direct tension.
- SYNTHESIS §3's kill shot — *"Kish ceiling = 1/φ̄ = 2.56 effective lenses… 2.56 < 4 ⇒ no lens count ever reaches validity"* — **rests entirely on that borrowed φ̄**. If our lenses really are near-orthogonal, the Kish ceiling does not bind here and a load-bearing kill is wrong. If they are not, **the reconciler is broken and the ratchet has a mechanical cause**.
- **We currently cannot tell which**, because the instrument that would measure it has an apparently ~100% false-negative rate.

**⇒ SYNTHESIS Rec #8 ("If anyone insists on a number: measure φ̄ first") is BLOCKED by Rec #7 ("Build the finding-identity function").** The SYNTHESIS lists them as independent. **They are sequentially dependent.** This is a new finding and the single most actionable thing in this dossier.

There is also a bias direction worth flagging: Mh-JK's residual is `((k−1)/k)·f₁`. With `f₁` pinned at 100% **by construction**, any capture-recapture estimate built on this reconciler would **always** report a large residual — i.e. **always say "keep reviewing."** An instrument that structurally cannot say "stop" is a *mechanistic* candidate explanation for the ratchet the SYNTHESIS describes in §2.

#### The test

**Phase 1 — the labeling study (this is the one to run).**

- **Instance:** one **cross-lens gap-record pair** from the same round on the same spec.
- **Population:** **2,491** available. **Stratify by the reconciler's own `orthogonality_filter` signal** — INDEPENDENT iff `touches` **and** `mechanism_refs` are both disjoint:

  | stratum | n | % |
  |---|---|---|
  | INDEPENDENT (both disjoint) — filter short-circuits | 1,564 | 62.8% |
  | **`touches` overlap only** | **875** | **35.1%** |
  | **BOTH `touches` + `mechanism_refs` overlap** | **34** | **1.4%** |
  | `mechanism_refs` overlap only | 18 | 0.7% |
  | **⇒ candidate-duplicate pool (any overlap)** | **927** | **37.2%** |

  **0 of those 927 were merged** by the 0.85 threshold. These are pairs the reconciler *itself* declines to certify as independent.
- **Oracle:** a **human same/different label** — "do these two records name the same underlying defect?" This is **objective and decidable** (the `PUBLICATION-1`/`I_g` pair settles in seconds), and it is the `objective_fact` discipline the Researcher role already requires in Mode C. **This is the only oracle in this entire analysis that actually exists.**
- **Cost:** pair extraction is **~0 tokens** (done — it's the script behind this dossier). Label a stratified sample of ~150 (oversampling the 34 both-overlap and the high-similarity tail, weighting back to the population). Bounded, hours not days.
- **Deliverable:** the **cross-lens duplicate rate**, hence φ̄, hence `1/φ̄` — the exact number Rec #8 demands and cannot currently obtain.
- **Decisive either way — pre-register both branches:**
  - **rate ≈ 0** → the lenses ARE near-orthogonal; **Kohli's φ̄=0.391 does not transfer**; SYNTHESIS §3's Kish-ceiling kill is **wrong for this loop** and capture-recapture is back on the table. *(This would overturn a load-bearing SYNTHESIS claim — which is why it is worth paying for.)*
  - **rate > 0** → the reconciler is **confirmed broken**; `1/φ̄` becomes computable; Rec #8's gate can finally fire; and the ratchet gains a mechanical, fixable cause.
- **Kill criterion:** if <20 of the 150 labeled pairs are judgeable without reading the full spec, the objective-fact oracle fails and this becomes a judgment study — stop and report.

**Phase 2 — the PACE test (only after Phase 1 supplies gold labels).** *Now* there is a properly-shaped, real-oracle PACE experiment:

- **Pair:** `(incumbent_correct, candidate_correct)` on one **gold-labeled cross-lens pair**, via `pairs_from_correctness`.
- **Incumbent:** the shipped identity function — `SequenceMatcher(char) >= 0.85` → SAME/DIFFERENT.
- **Candidate:** a normalized **claim**-identity function (SYNTHESIS Rec #7) — e.g. `touches` ∪ `mechanism_refs` overlap + token-set/embedding similarity, or an LLM same/different judge (**MVVP-validate that judge first** — Researcher guardrail: a judge rating its own output requires `evals/judge_validate.py`).
- **n:** up to **927** in-pool instances — **116× the D≥8 floor**. The only candidate examined here with power to spare.
- **Ordering: pre-register it** — chronological by `(run_dir, round, record_index)`, fixed before labels are inspected. **Non-negotiable** per §1.6/§3.3, which showed this corpus flipping to ACCEPT under a wins-first sort.
- **Predicted effect:** incumbent scores 0/927 "SAME". If the true duplicate rate is even 5%, the candidate wins essentially every discordant pair and PACE ACCEPTs almost immediately. **If Phase 1 shows the rate is that lopsided, skip Phase 2 — you don't need an anytime-valid test to beat a detector with a ~100% false-negative rate.** Phase 2 earns its cost only if Phase 1 finds a rate in the ambiguous middle where the candidate might also over-merge.
- **Guard against the mirror failure:** score **both directions** (false-merge AND false-split), or you will adopt an identity function that merges everything. Per the Researcher role's own Mode-C rule: *"a kept set that is all traps measures only recall."*

### 4.3 Free, adjacent, and worth doing regardless (not tests — logging)

Both are pure additions; neither needs an experiment:

1. **Record round-0 spec size** at dispatch. Unblocks (c)'s regression *causally* and costs one line. Currently unobtainable forever because `runs/` is gitignored (`.gitignore:40-41`) — every day without this is a permanently lost data point.
2. **Controlled vocabulary for `gap_type`.** It is 100% present and 93.4% useless. Collapse `gap_type`/`tag`/`tags` to one enum, normalize `[LOGIC]`→`LOGIC` and the 5 spellings of `precision-of-instruction`. This is the precondition for **any** future mechanical analysis of the finding corpus — including a rerun of (a) if a code-artifact oracle ever exists.

---

## 5. Honesty ledger

- **I made an error and corrected it.** My first closed-form boundary (`h* = 0.369 − 2.73/n`) assumed *final* wealth; `pace_accept` returns on the **running max**. It mismatched the real function on 9 of 18 checks. The corrected three-zone analysis (§3.3) replaces it, and the error is what surfaced the ordering exploit — the most consequential methodological finding in Part 1.
- **Everything numeric here is measured**, from the real files, by scripts run in this session. Hazard table independently re-derived (matches the prior dossier exactly). No count is estimated.
- **Selection bias is not controlled** in the hazard table. I inherit the prior dossier's caveat (§3.7) and do not claim to have fixed it. My Part-3 argument does not depend on the level.
- **Scoring A vs B is my reconstruction.** The dispatch's claim did not state a scoring function; I tested both and reported which reproduces the 84:16. If a third scoring was intended, that branch is untested.
- **The "confirmed true duplicate" is one pair**, judged by me from 60-char excerpts + 3 shared `touches`. It is sufficient to prove **existence** (hence that f₁=100% is an artifact) but says **nothing about the rate** — that is precisely what Phase 1 must measure. I did not extrapolate it.
- **`min_discordant` inertness** is proven for `alpha=0.05` across `lam ∈ (0,1)`. At other alphas it can bind — the model-routing spec (`alpha=0.005`, `min_discordant=16`) is a live example, and correctly set above the arithmetic floor.
- **Dedup caveat:** worktree/preserved copies are byte-*divergent* but may be the same logical run. Only 1 byte-identical `plan_check_log.md` duplicate existed; the hazard table is unchanged with or without dedup. For gap records, 20 of 144 files were exact worktree duplicates and were dropped.
- **Not read:** `spec.md` (862 lines) and `codex_product_pilot.md` in the model-routing run were grepped for their PACE parameters, not read in full.
- **Constraints honored:** no sub-agents spawned. No file modified except this dossier. `research/SOURCES_INDEX.md` untouched; `research_sources_index.py` not run.

---

## 6. Sources (all internal, all opened)

| artifact | what it grounded |
|---|---|
| `loop-team/evals/acceptor.py` (read in full, executed, self-tested) | Part 1 in its entirety |
| `loop-team/experiments/test_model_routing_pace_contract.py` | the live `min_discordant=16` / `alpha=0.005` manifest |
| `loop-team/runs/2026-07-16_model-routing-pace/specs/spec.md:283-292, 389` | the canonical pair definition; the belt-and-braces held-out threshold |
| `loop-team/harness/reconcile_gap_records.py:20, 49, 65, 144, 160-190, 225-280, 312-330, 418-440` | the 0.85 identity function; the orthogonality filter; tracer-vs-cluster separation |
| 124 unique gap_record files → **1,053 leaf records** | every count in Part 2 |
| 92 unique `plan_check_log.md` (60 parseable) | the independently re-derived hazard table |
| `research/2026-07-16-planning-stop-governor-SYNTHESIS.md` §§1,2,3,5,8 | the claims tested and the two corrected |
| `research/2026-07-16-rational-metareasoning-stopping-theory.md` §3.7 | h(k) — reproduced exactly |
| `research/2026-07-16-planning-stop-governor-internal-grounding-redteam.md:162, 228-234` | TaxAhead 782→97 provenance |
| `loop-team/learnings.md:2706-2740` | the 782→97 rewrite was off-log (n=1, contaminated) |
| `fix_plan.md:2695-2717` | `H-SPEC-REWRITE-DIFF-1` — the distinct rewrite-to-incorporate pattern |
| `.gitignore:40-41` | `runs/` + `loop-team/runs/` untracked → round-0 size unobtainable |

**Consumer link:** this dossier answers the PACE-testability question left open by `research/2026-07-16-planning-stop-governor-SYNTHESIS.md` §8 ("Open items"). Its operative output is a **dependency correction** — Rec #8 is blocked by Rec #7 — and a **Phase-1 labeling study** on 927 pre-extracted cross-lens pairs. Oga decides whether to run it; per the Researcher guardrail, I have not modified `fix_plan.md`.
