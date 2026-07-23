# Deep research: debugging/defect-detection methodologies, and a head-to-head experiment against the live ops-clock spec (2026-07-02)

**Prompted by:** Nnamdi asking why 20 rounds of plan-check keep finding new gaps, whether that's expected, and whether the ops-clock thread itself could be used as a live testbed to compare debugging methods.

**IMPORTANT RELIABILITY NOTE — read first:** this research was run as a 6-topic parallel sweep. **2 of the 6 topics (the "formal methods / TLA+ / Alloy" topic and the "ensemble/hybrid methods" topic) silently returned degenerate placeholder content** ("test" as the claim, source, and verdict for every field) instead of real research, despite passing schema validation cleanly — a different and more concerning failure mode than iteration 20's loud `StructuredOutput retry cap exceeded` error, since this one could easily have been trusted without noticing. Only 4 of 6 topics produced real, verified findings: defect-detection efficiency/plateauing, static analysis (Semgrep/CodeQL), Jepsen/concurrency testing, and mutation testing. **Any claim below attributed to "formal methods" or "TLA+ precedent" should be read as informal/analogical, not backed by verified sources in this pass** — logged as H-DEGENERATE-OUTPUT-1 in `fix_plan.md`.

---

## Part 1 — Why are we not finding all bugs at once (verified findings)

**A widely-circulated "87% → 28% defect detection by PR size" statistic attributed to the SmartBear/Cisco code review study does not exist anywhere in the actual study** — verified by fetching and full-text-extracting the real Cisco MeetingPlace case study PDF directly. The real, verified findings from that study: optimal review size is under 200 LOC (never exceed 400), optimal inspection rate is under 300 LOC/hour, sessions should be 30–90 minutes — and critically, the study found **no** reviewer- or size-specific constant inspection rate; pace varied enormously and unpredictably even for the same reviewer on similar code. Lesson: don't cite a plausible-sounding industry stat without fetching the primary source — a discipline this whole research pass tried to hold itself to.

**The single closest published analog to "many sequential rounds on the same artifact" is a 2-cycle, not 20-cycle, study** (Biffl/Halling/Kohle and Biffl/Freimut/Laitenberger reinspection studies of the same requirements document, verified via a citing academic survey — the original IEEE papers themselves returned 403s to automated fetch). Detection effectiveness roughly **halves** round-over-round even on a genuinely pre-code requirements artifact: 45.2% → 36.5%, or 46% → 21% in a second pass, with efficiency (defects/hour) also dropping. No literature exists at anything like our own 20-round scale — there's no "expected curve" to compare our own numbers against as a hard target.

**A broader meta-summary across many inspection studies (code, scenario-based, requirements-focused) shows single-pass detection ranging from 8.5% to 92.7%, median ~30%.** No stable universal "inspection finds X%" constant exists across techniques and artifact types. NASA's own guidance: a well-performed inspection typically removes 60–90% of defects "regardless of artifact type," and inspections have the most impact applied early — at requirements/design stages specifically (matches our pre-code context).

**Perspective-Based Reading (PBR) research — the most directly relevant finding, upgraded to primary-source-verified during the adversarial pass** (Basili et al., fetched directly): different reviewer *perspectives* (not just more raw reviewer-hours) each cover a different, non-overlapping subset of a requirements document's defect space. This maps directly onto our own iteration-18 result: 2 of 4 lenses independently converging on the *same* gap from different framings is exactly what PBR predicts when perspectives are well-rotated, and is a validity signal, not redundancy.

**"Satisfaction of search"** — a real, verified cognitive-science finding (radiology/vision literature): once a searcher finds one target, they measurably relax scrutiny for additional distinct targets in the same case, even when instructed to find all of them. Plausible mechanism for why a reviewer who just found 3 concurrency bugs might unconsciously relax on the next category in the same pass — domain-general, not software-specific, but a real, named phenomenon.

**Votta's inspection-meeting study** (Lucent 5ESS project): formal inspection *meetings* did not find significantly more defects than individual, non-meeting review, and cost meaningfully more. Relevant to a different but related question (is our async multi-agent format better than a synchronous review meeting would be) — the answer the evidence points to is: probably yes, don't add meeting overhead.

## Part 2 — Ranked candidate methods

Of 8 candidates the research surfaced, only **3 are PRE-CODE-APPLICABLE** at all (usable before any code exists, our actual current situation) — the other 5 are structurally POST-CODE-ONLY, confirmed by direct inspection of each tool's actual input requirements:

| Method | Pre-code? | Verdict |
|---|---|---|
| Structured state-transition-table enumeration | Yes | **Top candidate, tested below — genuinely different mechanism (enumeration-first vs. our narrative-first lenses)** |
| Perspective-Based Reading, rotated perspectives | Yes | Not a new method — this is what our 4 lenses already are; iteration 18's convergence is direct evidence it's working |
| Fagan-style formal inspection meeting | Yes | Rejected — same plateau rate as we're already seeing (Biffl data), plus Votta's evidence that meeting overhead doesn't pay for itself |
| Mutation testing (mutmut/Stryker) | **No** | Structurally requires existing code to mutate; even post-code, a real fault study (Just et al., FSE 2014, 357 real faults) found 27% of real faults aren't coupled to any generated mutant — a missing atomic-update pattern is an unwritten line, not a mutated token |
| Jepsen-style concurrent-transaction testing | **No** | Requires a running Postgres instance and real client code. Real, verified precedent: Jepsen found a genuine, previously-unknown PostgreSQL SERIALIZABLE bug (G2-item anomalies) on a *single-node* instance — directly relevant to our stack once code exists, but it confirms/tests a hypothesized race, it doesn't discover an unimagined one |
| Postgres `isolationtester` | **No** | Same as Jepsen — real, primary-sourced (Postgres's own `src/test/isolation`), post-code only |
| fast-check (property-based/model-based testing) | **No** | Real, mature, TS-native. Important limiting finding: its race scheduler operates at the JS Promise level only — it does not model real Postgres transaction-abort/MVCC semantics, so it can't discover gaps 26/36's actual mechanism, only systematically explore interleavings of an *already-known* one |
| Semgrep / CodeQL custom rules | **No** | Both require a real parseable/compiled source tree. Semgrep's `pattern-not-inside` idiom is a verified, near-exact template for our gap-19/22/29/33/35 shape ("a Prisma call inside `$transaction` with no accompanying count-check") — a real, reusable recipe for the eventual build-phase CI gate, not usable now |

## Part 3 — The experiment: state-transition-table enumeration vs. the live spec

**Design:** a single dispatch, methodologically distinct from our 4 narrative lenses — build an explicit grid (rows = the spec's own 7 tracked Task-mutating actions; columns = `Room.alertState` × open-task-set combinations × the FLIP-orthogonal axis) *before* any prose reasoning, then trace every reachable cell against the spec's literal text, flagging silent/ambiguous cells as candidates — then cross-check every surviving candidate against the full 38-gap history to filter rediscoveries from genuinely new findings.

**Honest pre-registered expectation** (stated by the synthesis before running): "roughly a coin flip weighted slightly toward confirms convergence" — i.e., the most likely outcome was finding nothing new, which would *itself* have been a valid, useful result (confirmation we're near the tail).

**Actual result: 2 genuinely new gaps found**, both the same class the enumeration approach specifically targets (a shared "same pattern/rule" instruction that doesn't hold identically at every structurally-similar call site):

1. **`resolvePaymentDispute`'s dual-open recompute mirror was never named** — AC11 tests curing COLLECTIONS while DISPUTE is open; the mirror direction (resolving DISPUTE while COLLECTIONS is open) was only asserted by analogy, never exercised through `resolvePaymentDispute` itself.
2. **`completeTask`'s DISPUTE-type branch and dual-open-via-`taskId` case were completely unexercised**, despite being reachable through a live UI button.

Both fixed in the spec (AC46b, AC55, AC56) — see `plan_check_log.md`'s iteration-20-adjacent entry.

**Two gap-candidates were correctly self-filtered as non-gaps** during the experiment's own Step 3 (cross-checking against the spec's literal algorithm text and the established "no AC's observable outcome depends on it" non-blocking precedent from iteration 14) — a real signal the method has calibration discipline, not just a tendency to over-flag.

## Part 4 — What this changes

1. **The state-transition-table enumeration method earned its place as a supplementary technique**, at least for one more pass — it found something 20 rounds of narrative review missed, on exactly the category (sibling-instruction-masks-divergence) our own taxonomy already flagged as our largest single bug class. Worth considering as a recurring 5th lens, or a periodic cross-check every N narrative rounds, rather than a one-time replacement for the 4-lens method.
2. **All 5 post-code methods (mutation testing, Jepsen/isolationtester, fast-check, Semgrep, CodeQL) are genuinely queued for the eventual build phase**, not now — several have concrete, near-ready recipes (the Semgrep `pattern-not-inside` template for gap-19/22/29/33/35-class rules; a Jepsen/isolationtester-style concurrent-transaction test for gaps 26/36/AC44/AC53/AC54 once the Coder implements those functions).
3. **H-DEGENERATE-OUTPUT-1** (the silent placeholder-content failure) is logged in `fix_plan.md` as an open reliability concern — worth watching for and spot-checking research/verification agent output for real substance, not just schema validity, going forward.

## Sources

- Cisco MeetingPlace case study PDF (SmartBear "Best Kept Secrets of Peer Code Review"), fetched and full-text-extracted directly.
- NASA Software Engineering Handbook (SWE-089/SWE-087), fetched via WebFetch.
- Stefan Wagner, "A Literature Survey of the Software Quality Economics of Defect-Detection Techniques," TUM-I0614 (2006) — fetched and extracted directly; cites the original Biffl/Halling/Kohle and Biffl/Freimut/Laitenberger studies (IEEE Xplore originals returned 403 to automated fetch, so these numbers are verified against a citing academic survey, not the primary paper's own text — flagged explicitly).
- Basili et al., Perspective-Based Reading, primary source fetched directly during the adversarial verification pass.
- Just et al., "Are Mutants a Valid Substitute for Real Faults in Software Testing?", FSE 2014 — fetched and read directly (PDF rendered as images, full text extracted).
- Jepsen (jepsen.io / jepsen-io/jepsen GitHub), including the PostgreSQL 12.3 SERIALIZABLE report, fetched directly.
- PostgreSQL's own `isolationtester` (`src/test/isolation`), confirmed via primary source.
- fast-check (dubzzz/fast-check) documentation, fetched directly.
- Semgrep and CodeQL documentation/KB examples, fetched directly.
- `research/ops-clock-gap-taxonomy-2026-07-02.md` and `runs/2026-07-02_ops-clock/plan_check_log.md` — our own real 38-gap ground truth this research was benchmarked against.
