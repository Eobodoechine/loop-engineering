# Deeper pass #2: plan-check reconciliation prior art — consolidation (2026-07-02)

**Builds on:**
- `research/plan-check-reconciliation-prior-art-2026-07-02.md` (first pass) — established no
  off-the-shelf tool merges N independent findings WITH contradiction detection; `ai-code-reviewer`'s
  clustering has no contradiction detection; NLI-based detection (F1 22-55%) misses compositional
  conflicts.
- `research/plan-check-reconciliation-deeper-pass-2026-07-02.md` (an EARLIER, separately-run deeper
  pass, already on disk) — closed two different loose ends via `ai-code-reviewer`'s actual source,
  `pisanuw/ltms` (TMS), Reddy/Challaram's memory-conflict paper, Graphiti, and SAVeR. That pass's
  conclusions are compatible with and independently reinforce this one (see cross-reference note at
  the end of §0).

**This document** consolidates a THIRD, later research thread (three sub-dispatches on proposal #2's
reconciliation gap, run this session) whose findings were produced as chat output only and never
saved to disk — the actual reason this document exists. Two of its most load-bearing claims were
independently re-verified by direct tool calls in this pass (not re-trusted from the summary handed
to me); one produced a correction, documented in §1.

---

## 0. Note on document lineage (read this first)

There are now, as of this research pass, **two independently-produced "deeper pass" documents** that
both build on the same first-pass doc but investigated different sources:

| | Earlier deeper-pass doc (already on disk before this pass started) | THIS document |
|---|---|---|
| `ai-code-reviewer` source | Fetched `review.py`, quoted `_cluster_raw_findings`/`apply_cross_review`/`_cap_findings`, did an import/vendorability audit | Independently re-fetched and re-confirmed the same two functions verbatim (see §1) — same conclusion, second independent confirmation |
| N-wise/cross-round mechanism | `pisanuw/ltms` (classical TMS, BCP over clauses) | `pisanuw/ltms` NOT found by this thread; instead found TOKI (bitemporal operator algebra, VLDB 2027 preprint) — a DIFFERENT real candidate for the same gap |
| Production memory-system evidence | Reddy/Challaram paper (2606.01435) + Graphiti (28k★) — both same-key supersession only | Letta/MemGPT (`core_memory_replace`/`append`, zero contradiction checking) + MemConflict benchmark (six production systems scored, max 0.2501/1.0) — different production systems, same conclusion |
| Iterative-agent-consistency literature | SAVeR (ACL 2026) — near-miss, checks internal reasoning not cross-artifact consistency | Generative Agents (Park et al.) — confirmed zero consistency-checking; Egyed's incremental UML checking — closest classical-SE pattern match, paywalled |
| Formal/classical-CS angle | LTMS — real, live, 4★, MIT, BCP/dependency-directed backtracking | SAT/SMT unsat-core (Z3 push/pop) — same translation-gap conclusion as the first pass, reconfirmed via neurosymbolic/SatLM literature |

**Neither document supersedes the other — they are complementary, independently-sourced
confirmations of the same overall verdict**, arrived at via different search paths (this is a good
sign: convergent evidence from disjoint literatures, not the same source read twice). Anyone building
`reconcile_gap_records.py` should treat both as inputs; I have NOT merged them into a single file, to
avoid destructively editing the earlier pass's already-committed, independently-useful document. This
document's own final verdict table (§5) incorporates rows from the earlier pass, marked as such, so a
reader only needs to open this one file for the full current picture — but the earlier file remains
the canonical source for its own findings' full detail (exact line numbers, full quotes) and should
not be deleted.

---

## 1. Spot-checks performed in this pass (before trusting the handed-off summary)

Per this role's brief ("you're being handed summaries rather than having done the legwork
yourself"), I independently re-verified two of the three most load-bearing claims via direct tool
calls before writing anything below as fact.

### 1a. `ai-code-reviewer` source code — RE-CONFIRMED, exact match

Fetched directly: `curl https://raw.githubusercontent.com/calimero-network/ai-code-reviewer/master/src/ai_reviewer/review.py`
(1,249 lines, HTTP 200) and `.../models/findings.py` (HTTP 200).

- `_cluster_raw_findings` exists at line 499; `apply_cross_review` exists at line 330;
  `run_cross_review_round` exists at line 953 — matches the handed-off summary's function names and
  approximate locations exactly.
- The severity-bypass logic is verbatim as claimed:
  ```python
  if finding.severity == Severity.CRITICAL and finding.category == Category.SECURITY:
      # Keep unless every assessing agent explicitly rejected it; one valid vote is enough
      if not votes or any(v for v, _ in votes):
          kept.append((finding, 1.0, 0))
      continue
  ```
- `models/findings.py`'s only imports are `hashlib`, `re`, `dataclasses`, `enum` — confirmed pure
  stdlib, zero framework coupling, exactly as claimed.
- **Verdict: Finding A confirmed as described, no discrepancy.** (This is also the second
  independent confirmation of this exact code — the earlier on-disk deeper-pass doc fetched and
  quoted the same functions via a different session; both agree.)

### 1b. TOKI repo — CONFIRMED REAL, but meaningfully MORE capable than summarized (correction)

Fetched directly: `api.github.com/repos/ZenAlexa/toki-bitemporal-memory` (HTTP 200) and
`raw.githubusercontent.com/.../main/README.md` (HTTP 200), plus the full repo file tree via the
GitHub Trees API.

Confirmed: real, **MIT license** (`"license":{"key":"mit"}`), **52 stars**, last pushed
2026-05-26, Python 3.11+, has a real experiment harness (`experiments/`, `artefact/`,
`results/anomaly_bench/`), a real test suite (`tests/bitemporal/test_conflict_set.py`,
`test_judge_log_persistence.py`), and genuine PostgreSQL concurrency experiments
(`isolation_concurrency.py`, 16 measured cells across a writers × isolation-level grid).

**Where this pass's summary undersold the finding:** the handed-off description said TOKI's
detection primitive is "structurally scoped to same-(subject, predicate)-key fact versioning... not
open-ended free-text semantic conflict" — true as far as it goes (TOKI's write path IS keyed on
`(s, p)` pairs, confirmed in the README), but the README's own "What's new since the last review"
section states the *n-ary* case explicitly:

> "n-ary conflict-set algebra — `implementation/bitemporal/operators.py::resolve_conflict_set`
> resolves a set of `n` mutually-contradicting incumbents in one fold (not just the pairwise case)...
> Verified by `tests/bitemporal/test_conflict_set.py`."

This is a real, tested, n-way (not just pairwise) reduction — a stronger match to loop-team's
"reconcile N gap records" shape than a plain pairwise comparator would be, even though it's still
keyed on `(subject, predicate)` rather than open-ended free text (the same translation-gap caveat
that applies to LTMS/SAT-SMT applies here too: loop-team's `gap_record.proposed_fix` would need to
be reduced to a `(subject, predicate, value)` triple before TOKI's algebra could run on it — nobody
in either research pass has built or validated that reduction step for engineering prose).

**One important fact the handed-off summary omitted entirely:** TOKI's own README status badge
reads **"Status: preprint, not peer-reviewed"**, explicitly targeting "PVLDB Vol. 20 / VLDB 2027" —
i.e. this is an **unpublished, unreviewed 2027-target submission**, not an accepted/published
result. The README says so itself: "the theorems, numbers, and claims here may change before
publication." Also worth flagging in the interest of not overselling: TOKI's own utility experiment
(`experiments/g2_utility/`) reports its own result honestly as underpowered/null — "achieved power
0.0347 against a 0.80 target... the artifact reports this honestly rather than claiming a
measured-slice win." This is a mark of intellectual honesty in the source (good sign for trusting
its other claims), but it also means TOKI's practical utility benefit is NOT yet empirically
established even by its own authors' pre-registered test.

**Verdict: TOKI is real, MIT-licensed, and its n-ary conflict-set algebra is a genuinely closer
mechanism-shape match than summarized — but it is an unpublished preprint (not vetted, could
change), and it still requires the same English-to-structured-fact translation step that blocks
LTMS/SAT-SMT from being usable today.** Correcting the record on this point for anyone deciding
whether to lean on it later.

### 1c. Letta/MemGPT — spot-checked as a bonus (not required, cheap given tool access), CONFIRMED

Fetched directly: `raw.githubusercontent.com/letta-ai/letta/main/letta/functions/function_sets/base.py`.
Confirmed `core_memory_append` (line 246) and `core_memory_replace` (line 263) are exactly as
described: `core_memory_replace` does a Python string `.replace(old_content, new_content)` on an
in-memory block value, raising only if `old_content not in current_value` — a plain
existence-then-substring-replace operation. Zero semantic contradiction checking of any kind, exactly
as claimed. No discrepancy.

**Summary of spot-checks:** 3 of 3 checked claims confirmed real; 1 of 3 (TOKI) had a correction
worth surfacing (stronger n-ary capability than summarized, but unpublished-preprint status not
mentioned in the original summary). No fabricated citations found — a good sign given this
project's own standing memory note about verifier citation fabrication risk.

---

## 2. Finding A, consolidated: `ai-code-reviewer`'s clustering/consensus code is copy-paste portable

(Independently confirmed in §1a above, and by the separate earlier deeper-pass doc via its own
fetch — two independent confirmations.)

- `_cluster_raw_findings` (dict-based `SequenceMatcher` clustering, keyed on file path + category +
  line-range overlap + text similarity ≥ 0.85) and `apply_cross_review` (the severity-bypass
  consensus filter) depend on nothing but stdlib (`difflib`, `dataclasses`, `enum`).
- Only `run_cross_review_round` has real coupling to this project — one call through an
  `AnthropicClient` wrapper's `complete_simple(model, system, user, max_tokens, temperature) -> str`
  method, which is trivially substitutable for loop-team's own `Agent`-tool dispatch mechanism.
- **Practical implication for `reconcile_gap_records.py`:** the clustering + severity-bypass logic
  (roughly 100-150 lines total) can be vendored close to verbatim, swapping `raw.get("file_path")`/
  `raw.get("category")` dict-key lookups for loop-team's own `gap_record["touches"]`/
  `gap_record["mechanism_refs"]` fields, and swapping `Severity.CRITICAL`/`Category.SECURITY` for
  loop-team's own `gap_type: DESIGN` exemption rule. This is the single most directly transplantable
  fragment found across all research passes on this topic (this one, and the earlier separately-run
  deeper pass, which reached the same conclusion independently).
- **What it still doesn't do, confirmed by direct code read (not just the architecture doc):**
  `run_cross_review_round`'s cross-review prompt asks each agent to assess `valid`(bool) +
  `rank`(int) per finding, independently, in parallel — no two findings' `proposed_fix`/`suggested_fix`
  text is ever placed in relation to each other in any prompt. Structurally incapable of surfacing
  "these two fixes contradict." This closes the loop on the first pass's inference from the
  architecture doc alone — the actual code confirms the same limitation, more precisely: it's not
  merely "no contradiction check exists," it's "the prompt design makes cross-finding comparison
  structurally impossible even in principle," since findings are scored one-at-a-time against a
  fixed rubric, never against each other.

---

## 3. Finding B, consolidated: iterative agent decision consistency / belief revision — unsolved everywhere

Three independent lines of evidence, from two different research passes with almost no source
overlap, converge on the same conclusion:

| Source | Verified how | What it actually does | Solves gap-28's shape? |
|---|---|---|---|
| Letta/MemGPT `core_memory_replace`/`append` | Direct source fetch, this pass (§1c) | Plain string substring-replace, zero checking | No |
| MemConflict benchmark (six production systems: Letta, Mem0, MemOS, A-Mem, LangMem, Memobase) | Handed off as arxiv.org/html/2605.20926 + github.com/TaoZhen1110/MemConflict — **NOT independently re-fetched in this pass** (budget prioritized the two spot-checks above); treating the "max score 0.2501/1.0" figure as reported-not-independently-confirmed | Benchmarks conflict *recognition* across 6 real deployed memory systems | No — this is the evidence that it's unsolved, not a candidate that solves it |
| Generative Agents (Park et al., arxiv 2304.03442) | Handed off as fetched 3x via ar5iv + PDF mirror — **not independently re-fetched in this pass** | Retrieval/reflection/planning memory architecture | No — "consistency"/"contradiction"/"conflict" reportedly absent from its technical sections |
| `pisanuw/ltms` (from the EARLIER, separately-run deeper-pass doc, not this thread) | Confirmed by that pass via curl (4★, MIT, pushed 3 days before that pass, PyPI, 19 test files) | Real classical TMS: BCP over propositional clauses, dependency-directed backtracking, N-wise (not just pairwise) | Mechanistically yes, but requires pre-formalized propositional clauses, not free text |
| TOKI (this pass) | Confirmed by direct fetch in this pass (§1b) | Bitemporal operator algebra, n-ary `resolve_conflict_set` fold | Mechanistically closer (n-ary, tested), but keyed on `(subject, predicate)` structured facts, not free text; unpublished preprint |
| Reddy/Challaram "Don't Ask the LLM to Track Freshness" (2606.01435) (earlier deeper-pass doc) | Confirmed real via curl of arXiv abs page by that pass; cited code confirmed 404/unreachable by that pass | `max(serial)` picks freshest same-key fact; paper's own words scope this OUT of compositional/N-wise conflicts | No — explicitly out of scope by the paper's own text |
| Graphiti (`getzep/graphiti`, 28k★, earlier deeper-pass doc) | Confirmed via api.github.com by that pass: pushed literally same-day | "Old facts invalidated, not deleted" — same-key temporal supersession | No — same pattern as Reddy/Challaram, independently corroborating |

**Consolidated verdict on Finding B:** Every production memory system checked across BOTH research
passes — Letta, Mem0, MemOS, A-Mem, LangMem, Memobase (via MemConflict's benchmark), Graphiti, plus
the generative-agents research lineage — either does no contradiction checking at all (Letta: plain
string ops) or does only same-key temporal supersession ("which value of THIS SAME fact is
freshest," confirmed independently for Graphiti and the Reddy/Challaram paper). None does
open-ended, free-text, N-wise compositional conflict detection — the exact shape of gap-28 (two
individually-valid ACs from different rounds, each individually "currently true," conflicting only
once traced against a shared mechanism). This is now a triple-confirmed absence (this pass's Letta
check + the handed-off MemConflict/Generative-Agents summary + the earlier pass's Reddy/
Challaram+Graphiti+LTMS findings), via three non-overlapping search angles (classical-AI TMS
lineage, production LLM-memory-system lineage, and agent-planning-literature lineage). That's strong
convergent evidence rather than a single search's blind spot.

**Caveat on unverified pieces:** the MemConflict "max score 0.2501" figure and the Generative
Agents "consistency doesn't appear in the text" claim were handed to me as already-verified by an
earlier sub-dispatch, but I did not re-fetch them myself in this pass (time-boxed the independent
verification to 3 checks per the assignment's own "spot-check 2-3, don't redo everything"
instruction, and picked the two most mechanically load-bearing ones plus one bonus). They are
consistent with, and not contradicted by, everything I did independently verify (Letta, TOKI,
ai-code-reviewer) — but per this project's own "citation fabrication" caution, they should be
treated as reported-with-moderate-confidence rather than doubly-verified, if anyone needs to cite
the exact 0.2501 figure externally later.

---

## 4. Finding C, consolidated: N-wise/cross-round conflict detection specifically

- **DOORS/Polarion/ReqIF:** no disclosed open algorithm — only marketing copy or basic schema
  validation. Confirmed dead end (not independently re-verified in this pass; consistent with the
  first pass's own finding that commercial requirements-management tooling doesn't publish its
  internals, and with this pass's general pattern of every checked source landing on the same gap).
- **LangChain/LangMem, AutoGen, CrewAI:** no TMS/belief-revision adoption — these frameworks compare
  a new input only against the immediately-preceding turn, never an accumulated set. Consistent with
  the earlier deeper-pass doc's own finding that LLM-agent frameworks broadly do same-key
  supersession at best.
- **Egyed's incremental UML consistency checking (ICSE 2007):** the closest classical-software-
  engineering PATTERN match — "scope"-based re-validation, where only the parts of a model that
  causally depend on what just changed get re-checked, rather than re-checking everything from
  scratch. This is architecturally the right shape for bounding the cost of a cross-round check (you
  don't need to re-trace EVERY prior gap record against every new one — only those whose
  `mechanism_refs`/`touches` sets actually overlap, which is precisely what the existing
  reconciliation sketch's orthogonality pre-filter already does). Paywalled/unverifiable as available
  software today — a design-pattern citation, not a vendorable tool, same class of contribution as
  CodeRabbit's fail-closed pattern in the first pass.
- **Kumiho** (AGM-postulate-compliant graph memory, arxiv.org/abs/2603.17244): real published
  benchmark numbers and a formal proof, per the hand-off, but proprietary/closed-source — its own
  benchmark repo reportedly ships only harness code requiring an API token, not the actual
  contradiction-detection implementation. Not independently re-verified in this pass; treating as
  reported, consistent with the pattern that every closed-source or paywalled candidate found across
  both passes turns out to be uninspectable in exactly this way.
- **TOKI** (this pass, confirmed in §1b): the strongest REAL, INSPECTABLE code hit for the N-wise
  shape specifically — `resolve_conflict_set` explicitly handles n-ary conflict sets in one
  operation (confirmed via direct README fetch), stronger than a from-scratch pairwise loop, though
  still keyed on structured `(subject, predicate)` facts rather than open-ended prose, and unpublished.
- **Incremental SAT/SMT (Z3 push/pop + unsat-core-with-assumptions):** mature, real, off-the-shelf
  mechanism for the GENERAL N-wise conflict-detection shape — confirmed by the same conclusion in
  the first pass (Direction 4.1) AND the earlier deeper-pass doc's independent `pisanuw/ltms` finding
  (a live, modern instance of the same BCP/clause-based mechanism family). The one blocker,
  confirmed convergently across all three research passes now (first pass, earlier deeper pass via
  LTMS, this pass via TOKI): translating free-text engineering decisions into formal
  logical/structured constraints first is itself an unreliable, unvalidated step — confirmed via the
  SatLM/neurosymbolic literature (LLM→logic translation is lossy for complex semantics) and now
  triple-corroborated by TOKI's and LTMS's own native input requirements.

---

## 5. Final verdict table — all three research passes combined

| Candidate | Real? (how verified) | Solves cross-round N-wise, free-text conflict? | License | Triage |
|---|---|---|---|---|
| `ai-code-reviewer` clustering/severity-bypass (`review.py`) | **Yes** — independently fetched and quoted twice, by two separate research passes (this one, §1a/§2; earlier deeper pass) | Partial — solves the "compatible merge / never drop critical" half only; explicitly NOT contradiction detection (confirmed by direct prompt-content read) | MIT | **IMPLEMENTABLE NOW** — ~100-150 lines vendorable near-verbatim |
| CodeRabbit merge-conflict decision pattern (first pass) | Yes, production | N/A — different input shape (git branches); reusable as a fail-closed DECISION PATTERN only | N/A (SaaS) | IMPLEMENTABLE NOW (pattern, not mechanism) |
| NLI requirements-conflict detection (arXiv 2405.05135, first pass) | Yes, real paper | Partial — F1 22-55%, explicitly misses compositional conflicts (its own stated limitation, which matches gap-28's shape) | N/A (research) | TESTABLE, not sufficient alone |
| `pisanuw/ltms` (earlier deeper pass) | Yes — 4★, MIT, pushed 3 days prior, PyPI, 19 tests, curl-verified | Mechanistically yes (BCP, N-wise, dependency-directed backtracking) — but requires pre-formalized propositional clauses | MIT | TESTABLE — right mechanism, blocked on translation layer |
| TOKI (this pass, §1b) | Yes — 52★, MIT, curl-verified, real PG concurrency experiments and test suite | Mechanistically closer (tested n-ary `resolve_conflict_set` fold) — but keyed on structured `(subject,predicate)` facts, not free text; **unpublished VLDB-2027-target preprint, not peer-reviewed** | MIT | TESTABLE — stronger mechanism than LTMS for the "N at once" shape, same translation-gap blocker, plus preprint-immaturity caveat |
| Letta/MemGPT `core_memory_*` (this pass, §1c) | Yes — direct source fetch | No — plain string ops, zero checking | (Letta license, not re-checked) | Confirms absence; not a candidate |
| MemConflict benchmark (six systems, handed-off, not independently re-fetched) | Reported, not independently re-verified this pass | N/A — it's a benchmark showing the gap (max 0.2501/1.0), not a solution | N/A | Corroborating evidence of the gap; cite with moderate confidence |
| Reddy/Challaram (2606.01435) + Graphiti (earlier deeper pass) | Yes, both independently curl-verified by that pass | No — explicitly same-key supersession only, by the paper's own words | Apache-2.0 (Graphiti) | Corroborating evidence of the gap |
| Generative Agents (Park et al., handed-off, not re-fetched this pass) | Reported (fetched 3x per hand-off, not independently redone here) | No — no consistency-checking mechanism present | N/A (research) | Corroborating evidence of the gap |
| SAVeR (earlier deeper pass) | Yes, curl-verified, ACL 2026 | No — audits single-agent internal reasoning faithfulness, wrong object of comparison | N/A (research) | RESEARCH-ONLY |
| Egyed incremental UML consistency (this pass) | Reported (classical citation, not independently re-fetched — paywalled) | Pattern match (scope-based re-validation) — not a usable tool today | N/A (paywalled) | Design-pattern citation only |
| Kumiho (this pass) | Reported, not independently re-verified | Claims yes per its own benchmark, but closed-source | Proprietary | Cannot inspect; not adoptable |
| SAT/SMT unsat-core (all three passes) | Real, mature technique | Conceptually yes, but requires English→formal-clause translation, which is itself unvalidated everywhere checked | N/A | RESEARCH-ONLY (concept, not tool) |
| DOORS/Polarion/ReqIF, LangChain/LangMem/AutoGen/CrewAI | Real products, no algorithm disclosed / confirmed same-turn-only | No | N/A | Confirmed dead ends |

**Overall verdict across all three research passes now completed on this question: no real,
inspectable, license-clear, off-the-shelf tool solves "detect that a new free-text decision
compositionally conflicts with an accumulated set of prior free-text decisions, across N items, not
just pairwise, without first translating everything into a formal or structured representation."**
This has now been checked from four independent angles — LLM-judge/code-review ensembling (first
pass), classical AI truth-maintenance (earlier deeper pass via LTMS), production LLM-agent-memory
systems (earlier deeper pass + this pass, six-plus systems), and database-style bitemporal
contradiction algebra (this pass via TOKI) — and all four converge on the same structural gap. This
is about as thorough a "this doesn't exist yet" finding as this kind of research can produce.

---

## 6. Recommendation on the current reconciliation-logic spec

Read `~/Claude/loop/loop-team/runs/2026-07-02_plan-check-reconciliation/specs/spec.md` in full before
writing this section. Current build status (checked directly): Test-writer has already written
`loop-team/harness/test_reconcile_gap_records.py` (real fixtures pulled from the literal
`runs/2026-07-02_ops-clock/plan_check_log.md` gap-28 and iteration-14 records, per that test file's
own header); `reconcile_gap_records.py` itself does not yet exist. So the spec is not yet frozen for
Coder — a research-driven addition is still cheap to fold in now, before Coder builds against it.

**My independent view: this deeper research pass VALIDATES the spec's existing design, and I agree
with the pre-supplied read — but I want to name two specific, small, additive changes, not just
rubber-stamp the "no redesign needed" conclusion.**

Reasoning: the spec's mandatory-mechanism-trace trigger (fires whenever two gap records share ALL
`mechanism_refs`, dispatching a fresh, unprimed Verifier to trace both against the real mechanism,
regardless of what any cheap screen says) is precisely the right response to a confirmed,
four-times-independently-corroborated absence of any off-the-shelf tool for this exact shape of
problem. If literally nothing — not TOKI, not LTMS, not any of six production memory systems, not
NLI classifiers — solves free-text N-wise compositional conflict detection today, then the spec's
choice to make the expensive, structural, dispatch-triggered fresh-Verifier trace MANDATORY (not
optional, not "nice to have if a cheap screen flags it") is the only defensible design under the
evidence. A weaker design (e.g., trusting a cheap NLI/LLM screen alone) would be reintroducing
exactly the risk both the first pass and this pass explicitly warn against.

**Two specific additions I'd recommend, both small and additive — not a redesign:**

1. **Adopt TOKI's provenance/audit-trail pattern explicitly, in the spec's step (d) escalation
   logging.** TOKI's core design principle (per its own README, confirmed by direct fetch) is that a
   losing/superseded fact is never silently discarded — it's preserved in a dual-row "audit" record
   with K-semiring provenance, specifically so a later party can reconstruct WHY a conflict resolved
   the way it did. The spec's existing step (d) already logs a `CONTRADICTION` entry naming both
   lenses, both fixes, and the shared mechanism — this is already close to TOKI's pattern in spirit,
   but I'd make explicit (as a one-line addition to spec.md's step (d) description, not a new AC)
   that the log entry must preserve BOTH full `proposed_fix` texts verbatim even after one is
   discarded by the tie-break, not just the winning one — i.e., don't let the tie-break dispatch's
   output overwrite/replace the losing record in `plan_check_log.md`, only ADD the resolution on top.
   This is a one-sentence spec clarification, not a new mechanism, and directly imports a concrete,
   real, load-bearing design principle from the one genuinely N-ary-capable system found across all
   three passes.

2. **Add an explicit scaling-cost caveat to the spec's Non-goals section, given the pairwise-scan
   cost this research surfaced repeatedly.** Every real N-wise mechanism found across all three
   passes (`ai-code-reviewer`'s clustering, LTMS's BCP, TOKI's `resolve_conflict_set`) is, under the
   hood, built on an O(n²) pairwise comparison or an equivalent full-clause-set propagation — none of
   them found a way to avoid this. The current spec's orthogonality pre-filter already bounds this in
   the common case (most pairs are disjoint and short-circuit for free), but the spec doesn't
   currently say anything about what happens if a FUTURE round has, say, 10+ parallel lenses instead
   of 3-4 (yielding up to 45 pairs to screen). Given Egyed's incremental/scope-based re-validation
   pattern (§4) is architecturally exactly the right mitigation (only re-check pairs whose
   `mechanism_refs`/`touches` sets actually changed since the last reconciliation, not the full
   cross-product every time), I'd recommend adding one sentence to the Non-goals section: "This v1
   does not optimize for finding-count scaling beyond the orthogonality pre-filter; if parallel-lens
   fan-out grows materially (e.g., beyond ~6-8 lenses routinely), revisit with an Egyed-style
   scope-based incremental re-check restricted to mechanism/touch-set deltas, rather than a full
   pairwise rescan." This costs nothing to add now and prevents a future build from having to
   rediscover this exact scaling consideration from scratch.

**What I am NOT recommending:** no change to the mandatory-mechanism-trace trigger itself, no
attempt to adopt TOKI's or LTMS's actual algebra/BCP engine (both require an unvalidated
English-to-structured-fact translation step that would reintroduce the exact "instructional-only,
could fail silently" risk this whole project exists to eliminate — confirmed as a blocker
independently in all three research passes now), and no change to the Non-goals section's existing
decision to stub the NLI/LLM screening step rather than build it in v1 (that call is well-supported:
the F1 22-55% ceiling and the compositional-conflict blind spot are exactly why the mandatory trace
trigger exists as a structural backstop regardless of the screen's verdict).

---

## What I dropped and why

- Did not independently re-fetch the MemConflict benchmark paper/repo or the Generative Agents
  paper — time-boxed spot-checking to 3 of the most mechanically load-bearing claims (ai-code-reviewer
  source, TOKI, plus a bonus Letta check) per the assignment's own "spot-check 2-3, don't redo
  everything" instruction. Their claims are consistent with everything independently checked and are
  reported here with a clear "handed-off, not independently re-verified" flag rather than silently
  upgraded to verified status.
- Did not independently re-verify DOORS/Polarion/ReqIF, Kumiho, or Egyed's paywalled ICSE 2007 paper
  — these were already flagged as unverified/paywalled by the hand-off, and re-attempting them
  wouldn't change the triage (paywalled/closed-source either way).
- Did not attempt to prototype or test an English→structured-fact translation layer for TOKI or
  LTMS — that's Oga/Coder build work, flagged as a candidate next step in the earlier deeper-pass
  doc, not Researcher work in either pass.
- Did not merge this document with the earlier, separately-run deeper-pass doc into one file — see
  §0 for the reasoning (avoiding destructive edits to an already-committed, independently-useful
  document; both are cross-referenced instead).

## Transfer-condition check (required per role brief)

- **`ai-code-reviewer` clustering/severity-bypass code:** (a) requires only stdlib + three pure-stdlib
  dataclasses from `models/findings.py` — trivial execution context. (b) loop-team's context (a plain
  Python harness script, same pattern as `verify.py`/`stall_detector.py`) fully satisfies this. (c)
  The guarantee is structural (a deterministic function), the strongest transplant found across all
  passes.
- **TOKI's `resolve_conflict_set`:** (a) requires facts already reduced to `(subject, predicate,
  value, timestamp)`-shaped structured records. (b) loop-team's `gap_record.proposed_fix`/
  `broken_assumption` are free English prose — context NOT satisfied without a new, unvalidated
  translation step, identical gap to LTMS/SAT-SMT. (c) TOKI's own soundness theorems are structural
  and machine-checked (confirmed real experiments/tests) ONCE the input is in its native format — but
  the translation step that would produce that format from English is necessarily an LLM call,
  reintroducing the instructional-only risk this project exists to close, unless that translation
  step gets its own independent accuracy check (e.g., round-trip validation).
- **Letta/MemGPT's memory functions:** (a) requires nothing (plain string ops) — but (b)/(c) don't
  apply since this is cited only as negative evidence (confirms the absence), not as a candidate
  mechanism to adopt.

---

**Saved to:** `~/Claude/loop/research/plan-check-reconciliation-deeper-pass-2-2026-07-02.md`
(named `-2-` to avoid overwriting the earlier, separately-run deeper-pass doc at
`research/plan-check-reconciliation-deeper-pass-2026-07-02.md`, which this document cross-references
throughout rather than replaces — see §0 for why both are kept).
