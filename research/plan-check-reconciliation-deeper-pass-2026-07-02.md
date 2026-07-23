# Deeper pass: plan-check reconciliation prior art (2026-07-02)

**Builds on:** `research/plan-check-reconciliation-prior-art-2026-07-02.md` (read in full before
starting this pass; not duplicated here). That pass found no off-the-shelf tool merging N
independent structured findings WITH contradiction detection, and flagged two loose ends:
`ai-code-reviewer`'s ARCHITECTURE.md was read but not its actual source, and no source directly
addressed cross-round (N-wise/incremental) conflict as opposed to same-batch pairwise conflict.
This pass closes those two loose ends directly, plus searches specifically for "iterative agent
decision consistency" frameworks. Every source below was actually opened via WebFetch/curl in this
session — URLs, exact quotes, and verification method (curl vs WebFetch, direct API check vs
search synthesis) are stated for each one.

---

## 1. `ai-code-reviewer`'s ACTUAL source code (not just ARCHITECTURE.md)

Fetched directly via `curl` against `raw.githubusercontent.com` (not GitHub's rendered UI, not
WebFetch synthesis) for every file below. Full repo tree enumerated via
`api.github.com/repos/calimero-network/ai-code-reviewer/git/trees/master?recursive=1`.

### Correction to the first pass's implicit assumption

The first pass quoted the architecture doc's function names (`_cluster_raw_findings`,
`run_cross_review_round`, `apply_cross_review`) without locating which file actually implements
them. I checked: **they do NOT live in `orchestrator/aggregator.py`** (a plausible guess — that
file has its own, separate, `ReviewAggregator` class with a *similarly named but distinct*
`_cluster_findings`/`_are_similar` pair that appears to be an older or parallel consolidation path
with its own `AggregatorConfig`). The functions the architecture doc actually describes live in
**`src/ai_reviewer/review.py`** (1,249 lines — the single largest module in the repo, confirmed via
directory listing: `review.py` 49,307 bytes vs `orchestrator/aggregator.py` 10,651 bytes). This
matters for anyone trying to vendor this code later: grabbing `aggregator.py` alone would get the
wrong (and non-canonical) implementation.

### The real code, quoted verbatim

**Clustering** (`review.py:499-522`, `_cluster_raw_findings`), fed by `_raw_findings_similar`
(`review.py:474-496`):

```python
def _raw_findings_similar(raw1: dict, raw2: dict, threshold: float = _SIMILARITY_THRESHOLD) -> bool:
    """Check if two raw findings describe the same issue (for consensus clustering)."""
    path1 = _normalize_path(raw1.get("file_path", ""))
    path2 = _normalize_path(raw2.get("file_path", ""))
    if path1 != path2:
        return False
    cat1 = (raw1.get("category") or "logic").lower().strip()
    cat2 = (raw2.get("category") or "logic").lower().strip()
    if cat1 != cat2:
        return False
    if not _raw_lines_overlap(raw1, raw2):
        return False
    title_sim = _raw_text_similarity(title1, title2)
    desc_sim = _raw_text_similarity(desc1, desc2)
    combined = (title_sim * 0.6) + (desc_sim * 0.4)
    return combined >= threshold
```

```python
def _cluster_raw_findings(
    tagged: list[tuple[str, dict]], threshold: float = _SIMILARITY_THRESHOLD
) -> list[list[tuple[str, dict]]]:
    """Cluster similar raw findings so consensus = agents that found the same issue."""
    clusters: list[list[tuple[str, dict]]] = []
    used = set()
    for i, (agent_i, raw_i) in enumerate(tagged):
        if i in used: continue
        cluster = [(agent_i, raw_i)]
        used.add(i)
        for j, (agent_j, raw_j) in enumerate(tagged):
            if j in used: continue
            if _raw_findings_similar(raw_i, raw_j, threshold):
                cluster.append((agent_j, raw_j)); used.add(j)
        clusters.append(cluster)
    return clusters
```

This is a plain O(n²) nested-loop greedy clustering over dataclass-free dicts — no ML, no
embeddings, pure `difflib.SequenceMatcher` + field equality. Genuinely trivial to lift.

**Cross-review dispatch** (`review.py:953-986`, `run_cross_review_round`) — the actual mechanism,
confirmed by direct read, is narrower than the architecture doc's prose implied:

```python
async def run_cross_review_round(
    *, client: AnthropicClient, review: ConsolidatedReview, context: ReviewContext,
    diff: str, agents_to_run: list[dict], on_status=None, **_kwargs,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Cross-review round: each agent validates and ranks findings.
    Uses get_cross_review_prompt + get_cross_review_output_format to produce
    the {id, valid, rank} assessment format that apply_cross_review expects."""
    if not review.findings:
        return []
    cross_prompt = get_cross_review_prompt(context, review, diff) + get_cross_review_output_format()
    tasks = [_run_single_cross_agent(client=client, cross_prompt=cross_prompt,
             agent_name=str(cfg.get("name") if isinstance(cfg, dict) else cfg), on_status=on_status)
             for cfg in agents_to_run]
    gathered = await asyncio.gather(*tasks)
    return [(name, a) for name, a in gathered if a is not None and len(a) > 0]
```

Each cross-review agent gets **the full list of already-clustered findings in one prompt** and is
asked two things per finding (`get_cross_review_prompt`, `review.py:243-287`): "1. Valid
(true/false)... 2. Rank (integer)... importance." That's it. **There is no prompt anywhere that
asks an agent to compare finding A's `suggested_fix` against finding B's `suggested_fix` for
logical compatibility.** It's a validity/importance re-scoring pass per finding, independently —
structurally incapable of surfacing "these two fixes contradict," because no two findings are ever
placed in relation to each other in the prompt; they're all scored against the same rubric in
parallel within one call. This is a sharper, code-verified version of what the first pass inferred
from the doc — confirmed by reading the exact prompt text, not just the doc's characterization of
it.

**Severity bypass** (`apply_cross_review`, `review.py:330-429`), the specific quoted logic:

```python
for fid in finding_ids:
    finding = id_to_finding[fid]
    votes = id_to_votes.get(fid, [])
    if finding.severity == Severity.CRITICAL and finding.category == Category.SECURITY:
        # Keep unless every assessing agent explicitly rejected it; one valid vote is enough
        if not votes or any(v for v, _ in votes):
            kept.append((finding, 1.0, 0))
        continue
    ...
    valid_ratio = valid_count / len(votes) if votes else 1.0
    if valid_ratio < min_validation_agreement:
        continue  # Drop finding
```

Confirmed real, exactly as the architecture doc described, plus one detail the doc didn't mention:
it's not "always kept unconditionally" — it's kept "unless every assessing agent explicitly
rejected it" (i.e., one dissenting-but-not-unanimous vote still survives). A precise, useful
distinction if this pattern is reused.

**Adaptive cap** (`_cap_findings`, `review.py:629-661`) — confirmed real, `N = max(5, min(20,
total_lines // 100 + 5))`, criticals exempt, non-criticals trimmed to fill the remaining budget.

### Vendorability assessment (the actual question asked)

Checked import statements directly (`head` of `review.py`, `orchestrator.py`, `aggregator.py`):

- `review.py` imports from **7 sibling modules inside this same package**:
  `ai_reviewer.agents.{anthropic_client,base,patterns,performance,security}`,
  `ai_reviewer.context.{builder,fetch,neighbors}`, `ai_reviewer.github.client`,
  `ai_reviewer.models.{context,findings,review}`, `ai_reviewer.security.scanner`,
  `ai_reviewer.session`, `ai_reviewer.tools.repo_tools`. The single 1,249-line file is NOT
  self-contained — `review_pr()` (the top-level entry point, line 1006) wires together GitHub API
  calls, an Anthropic client wrapper with its own caching/usage-logging invariant ("invariant I1"
  per an inline comment), repo-map building, and 6 concrete agent subclasses.
- **However**, the four functions actually relevant to reconciliation — `_raw_findings_similar`,
  `_cluster_raw_findings`, `apply_cross_review`, `_cap_findings`, plus their small helpers
  (`_normalize_path`, `_raw_lines_overlap`, `_raw_text_similarity`) — import **only** from
  `ai_reviewer.models.findings` (`Category`, `ConsolidatedFinding`, `Severity`) and stdlib
  (`difflib.SequenceMatcher`, `collections.defaultdict`, `copy.deepcopy`). `models/findings.py`
  itself (fetched, 100 lines) is pure stdlib (`hashlib`, `re`, `dataclasses`, `enum`) — zero
  framework coupling.
- **Verdict: genuinely vendorable, narrowly.** The clustering + cap + severity-bypass logic (roughly
  120 lines total across `_cluster_raw_findings`/`_raw_findings_similar`/`_cap_findings`/
  `dedup_cross_file`) can be copy-pasted into a standalone Python harness script with trivial
  adaptation (swap `ConsolidatedFinding`/`Severity`/`Category` dataclasses for loop-team's own
  `gap_record` schema) — no dependency on the GitHub client, Anthropic client wrapper, or agent
  classes. `run_cross_review_round`/`apply_cross_review`'s *voting logic* (the dict-manipulation in
  `apply_cross_review`, lines 342-429) is similarly clean and portable. What is NOT portable is the
  *prompting scaffold* around it (`get_cross_review_prompt`, `_run_single_cross_agent`) — that's
  tightly wired to this project's own `AnthropicClient.complete_simple()` wrapper and its specific
  prompt-caching invariant; loop-team would rewrite the prompt/dispatch layer from scratch (which is
  a few dozen lines, not a blocker) while reusing the clustering/cap/bypass logic verbatim.
- **This changes the first pass's triage from "study and partially adopt" to something more
  concrete: the specific 120-150 lines named above are copy-paste-usable today**, license permitting
  (MIT, confirmed via `api.github.com/repos/.../license` in the first pass). The reconciliation
  sketch's step (c) ("apply the `ai-code-reviewer` pattern directly... reuse the `SequenceMatcher ≥
  0.85` threshold verbatim") is now backed by an exact, quoted, working implementation, not just an
  architectural description.

---

## 2. N-wise / cross-round conflict detection

### 2a. Requirements/spec consistency tools handling N (not 2) statements at once

WebSearch for "requirements consistency checking incremental" / "specification conflict detection
accumulated constraints" surfaced mostly formal-methods literature (timed automata, feature
interaction). One real, concretely fetched result: the FIX (Feature Interaction eXtractor) tool
line from search synthesis uses the COSPAN model checker for telecom feature-interaction
inconsistency — this is N-wise in principle (model checkers reason over the full state space, not
just pairs) but is 1990s-2000s telecom-features work with no accessible modern implementation
found, and (like SAT/SMT in the first pass) requires the specs to already be formalized as automata
— same translation-gap problem, not independently re-verified beyond the search synthesis (not
opened in full; low expected yield given the domain and age). Not counted as a real find.

### 2b. Truth Maintenance Systems (TMS) — the real, substantive find of this pass

TMS is exactly the classical-AI subfield the assignment asked about: "the subfield about updating a
knowledge base with a new fact while detecting conflicts with existing facts." Checked the
`github.com/topics/truth-maintenance` topic page directly (via WebFetch) and cross-checked with
`repos.ecosyste.ms`'s topic API (via curl) for repo metadata. Two old academic-exercise ports exist
(`FellnerDotDev/ATMS-in-Python`, MIT license, 1 star, **last pushed 2017**; `Ruggiero-Santo/NATMS`,
1 star, last pushed 2020) — confirmed via direct `api.github.com/repos/...` calls (stars, license,
`pushed_at` all read from the API response). Both are toy/thin, not maintained.

**The one genuinely live, non-toy hit: `pisanuw/ltms`.**

- **Source:** `https://github.com/pisanuw/ltms`. Verified via direct `api.github.com` call: **4
  stars, MIT license, last pushed 2026-06-29** (three days before this research pass — i.e. this is
  an actively-worked repository right now, not a historical artifact). Also on PyPI
  (`pip install ltms`, confirmed via `pypi.org/pypi/ltms/json`, version 0.1.0, 1 release). Has CI
  (`.github/workflows/ci.yml`) and a genuinely large, real test suite — 19 test files fetched via
  directory listing, including `test_differential_sat.py` (differential testing against PySAT) and
  `test_core_properties.py` (property-based tests), which is a strong maturity signal for a
  4-star repo.
- **What it actually is**, quoted directly from its README (fetched via `curl` +
  `raw.githubusercontent.com`): "A logic-based Truth Maintenance System (LTMS) and a
  pattern-directed reasoning engine in pure Python, after Forbus & de Kleer, *Building Problem
  Solvers* (MIT Press, 1993). The LTMS maintains belief over a set of propositional clauses using
  Boolean Constraint Propagation (unit propagation), records well-founded support for every derived
  value, performs dependency-directed backtracking on contradictions, and can explain why anything is
  believed." And from `README.md`'s own "Why" section: **"There is no faithful Python LTMS in the
  wild — JTMS/ATMS have a few toy ports, but the clausal-BCP LTMS with dependency-directed
  backtracking is the least-ported truth maintenance system outside Lisp/Racket."** — i.e. the
  author's own claim, which my search independently corroborates (the only other Python TMS ports
  found are the two stale 1-star repos above), is that this fills a real gap.
- **Mechanism, confirmed by reading `src/ltms/core.py` directly (fetched via curl, 20,383 bytes,
  read in full for the relevant section):** clauses are disjunctions of signed literals; a
  `LTMSContradiction` exception is raised when a clause's `pvs` ("potential violators") counter hits
  zero, meaning every literal in that clause is now forced to the wrong sign — this IS the N-wise
  mechanism asked for: a clause can involve any number of literals (facts), and BCP propagates
  constraints across the ENTIRE live clause set simultaneously, not just pairwise. A live worked
  example (`examples/belief_revision_ltre.py` + `examples/kb/belief_revision.kb`, both fetched in
  full) demonstrates exactly the "does a new fact stay consistent with the accumulated set" pattern
  asked about: two independent justifications for `wet ground` (`rain` and `sprinkler on`) are
  asserted and retracted in sequence, and the system correctly tracks that `wet ground` remains
  `true` as long as ANY justification holds and reverts to `unknown` only once ALL are retracted —
  this is genuine incremental belief maintenance across a growing/shrinking fact set, the right
  shape of problem.
- **The transfer-condition gap, and it is the SAME gap the first pass found for SAT/SMT (Direction
  4.1), confirmed directly by reading `src/ltms/dsl.py` (the file-based world-model loader):** the
  `.kb` DSL requires **pre-formalized propositional statements** — `rain -> wet ground`, not English
  prose. The DSL's own docstring: "Connectives (low to high precedence): `<->` `->` `|` `&` `~`."
  A loop-team Verifier's `proposed_fix` field ("add a mutex around the write path so concurrent
  writers can't race") has no automatic, reliable translation into `mutex_added -> race_fixed`
  without an LLM doing that translation, and — critically — **no source found anywhere in this
  research (first pass or this pass) builds or validates that specific English-to-clause translation
  step for engineering/spec-review text.** `pisanuw/ltms` is real, modern, and does the RIGHT
  mechanism (N-wise constraint propagation with contradiction detection and explainable support) —
  but it operates one level below where loop-team's actual data lives (formalized logic, not
  free-text `proposed_fix`/`broken_assumption` strings). This narrows, but does not close, the
  gap the first pass identified for SAT/SMT: the mechanism this pass found is a real, live,
  well-tested Python implementation (not just "SAT/SMT concept, no bridge"), which is a genuine
  improvement in citability, but the translation-layer problem is unchanged.
- **Triage: TESTABLE, not IMPLEMENTABLE NOW.** If loop-team ever builds the English→clause
  translation step (which would need its own validation — LLM-based clause extraction is exactly
  the kind of thing that needs an accuracy check, not blind trust), `ltms` is a real, live,
  well-tested target to plug it into, superior to a from-scratch SAT wrapper. Today, without that
  translation layer, it is not directly usable.

### 2c. Belief revision × LLMs — one directly relevant, real, currently-accepted paper found, with an important scope limit

Search for "truth maintenance system LLM knowledge base belief revision" and follow-up searches
surfaced a cluster of 2026 papers specifically about agent memory contradiction/supersession. The
most concrete, directly relevant, and code-having one:

- **"Don't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution"**
  — `arxiv.org/abs/2606.01435`, authors Reddy & Challaram. **Verified as a real paper** via direct
  `curl` of the arXiv abs page (not WebFetch synthesis alone): `citation_date` = 2026/05/31,
  confirmed present in the raw HTML response.
- **Mechanism, quoted directly from the paper's own HTML (`arxiv.org/html/2606.01435`, fetched via
  WebFetch and independently grepped from raw curl'd HTML for the GitHub link):** conflicts are
  resolved by "retrieval → LLM candidate extraction → Python `max(serial)` to pick the newest fact.
  No LLM evaluates whether facts conflict." The paper is explicit that this is scoped narrowly:
  **"current-value conflict resolution" is scoped to cases where "max() is the right operator"** —
  i.e., this is **same-key, same-attribute, two-sided (or N-sided-but-all-comparable-on-one-axis)
  supersession only** ("which is the freshest value of THIS SAME fact"), explicitly **not**
  compositional/N-wise conflict (where the conflict emerges only once several DIFFERENT facts are
  combined) — the paper states this limitation about its own scope directly, not as an inferred
  weakness.
- **Code claim vs. verified reality — IMPORTANT, flagging per the fabrication-risk memory:** the
  paper's own "Reproducibility" appendix (fetched from the raw HTML) states: "The full code and
  per-question JSON results are at `https://github.com/cvikasreddy/memory-conflict-resolution`
  (public as of the arXiv posting)." **I directly checked this URL two ways: `curl -sI` returned
  `HTTP/2 404`, and `api.github.com/repos/cvikasreddy/memory-conflict-resolution` returned `{"message":
  "Not Found"}`.** I also pulled the full public repo list for the account `cvikasreddy`
  (`api.github.com/users/cvikasreddy/repos`, 13 repos returned) and `memory-conflict-resolution` is
  **not among them** — it was made private, deleted, or renamed after the arXiv posting. **This is
  a real paper with a real, specific, honestly-scoped mechanism, but its cited code is NOT
  currently fetchable or independently verifiable** — reporting this exactly as required by the
  "verify against reality" standard: the mechanism description above is trustworthy (quoted from the
  paper's own text, cross-checked against the well-known and independently-confirmed pattern used by
  Graphiti/MemStrata below), but "there is working code" is NOT something I can currently confirm by
  direct inspection, despite the paper's claim.
- **Corroborating, independently-verified pattern from a live, massive, unrelated project:**
  `getzep/graphiti` — confirmed via direct `api.github.com` call: **28,291 stars, Apache-2.0, last
  pushed literally today (2026-07-02)**, i.e., a big, currently-maintained, real framework, not a
  research toy. Its own docs (fetched via WebFetch): "When information changes, old facts are
  invalidated — not deleted" / "Automatic fact invalidation with temporal history preserved." This
  independently confirms the SAME scope limitation as the Reddy/Challaram paper: **the dominant
  real-world pattern for LLM-agent memory conflict handling, across both a small research paper and
  a 28k-star production framework, is pairwise temporal supersession of the SAME fact-key — nobody
  found in this pass, in either the research literature or production tooling, does true N-wise
  compositional conflict detection where the contradiction only emerges from combining 3+
  independently-true facts.** This is a strong, cross-validated (two independent sources, one
  research one production) confirmation of the exact gap this whole assignment is about.

### 2d. Direct answer to the assignment's framing

The real ops-clock incident (gap #28: a NEW finding conflicting with an ALREADY-APPLIED fix from an
EARLIER round) is structurally a **compositional/N-wise** conflict in the TMS sense (does a new
justification stay consistent with the existing web of support), NOT a same-key supersession (it's
not "which is the freshest value of the same fact" — the two acceptance criteria were both
"currently true" until traced against a shared mechanism). Everything concretely real and verified
in this pass — MemStrata, Graphiti, the Reddy/Challaram paper — solves same-key supersession
("newest wins"), which is a **different and easier** problem than gap #28. `pisanuw/ltms` solves the
right SHAPE of problem (N-wise constraint propagation) but requires formalized input loop-team
doesn't have. **Honest conclusion: no source found in this deeper pass — real production framework,
real 2026 paper, or real TMS implementation — solves the specific compositional/N-wise,
free-text-input case gap #28 represents.** This confirms and sharpens (with much better citations)
the first pass's NLI-paper-based warning about compositional conflicts, rather than overturning it.

---

## 3. "Iterative agent decision consistency" frameworks (not one-shot judge ensembling)

Searched specifically for long-horizon agent planning conflict detection and Claude/GPT-agent
papers about checking a new action against a decision/memory log before committing it.

- **"Verify Before You Commit: Towards Faithful Reasoning in LLM Agents via Self-Auditing" (SAVeR)**
  — `arxiv.org/abs/2604.08401`. **Verified as real** via direct curl of the abs page: authors Yuan,
  Lin, Chen, Xu, Wang, Ngai; `citation_date` = 2026/04/09; accepted at ACL 2026 (per the paper's own
  listing). Abstract quoted directly: "coherent reasoning can still violate logical or evidential
  constraints, allowing unsupported beliefs repeatedly stored and propagated across decision
  steps... Most existing strategies rely on the consensus mechanism, conflating agreement with
  faithfulness... we structurally generate persona-based diverse candidate beliefs for selection...
  perform adversarial auditing to localize violations and repair through constraint-guided minimal
  interventions." **On close reading this is a near-miss, not a match**, and worth being precise
  about why: it audits whether a SINGLE agent's OWN reasoning trajectory is internally
  evidentially-supported (the "unfaithful step" problem), not whether a NEW proposed action/finding
  is consistent with an EXTERNAL accumulated decision log from OTHER agents/rounds — different
  object being checked (internal reasoning faithfulness vs. cross-artifact consistency). Its own
  mechanism ("persona-based diverse candidate beliefs... adversarial auditing") is structurally
  closer to Direction 1's debate/MoA shape (already ruled out by the first pass) than to a
  decision-log-consistency checker. **No code repository found** — the abs page and the paper's own
  metadata carry no GitHub link. Triage: RESEARCH-ONLY, wrong object of comparison, no code to
  inspect regardless.
- **General agent-memory survey literature** (multiple 2026 papers found: "Aligning Progress and
  Feasibility: A Neuro-Symbolic Dual Memory Framework," "Continuum Memory Architectures,"
  "DELTAMEM," "Beyond Semantic Organization: Memory as Execution State Management") — not
  individually fetched in full in this pass; search-synthesis descriptions uniformly describe
  retrieval/summarization/forgetting mechanisms for keeping an agent's OWN working memory usable
  over long contexts, not a mechanism for validating a new decision against accumulated prior
  decisions for logical consistency. Given the two directly-fetched and verified papers above
  (SAVeR, Reddy/Challaram) both confirm the same "consensus/supersession, not true consistency
  checking" pattern, and Graphiti independently corroborates it from the production side, I did not
  spend further budget opening each additional survey paper — diminishing returns once three
  independent, verified sources converge on the same limitation, consistent with this role's "own
  recall" and "don't pad with unopened snippets" standards.
- **Conclusion for gap #3:** no repo or paper found describes or implements "keep a growing set of
  agent decisions self-consistent as new ones are added, checking N-wise/compositionally, not just
  against the single most-recent same-key fact." This is a second independent confirmation (after
  §2) of the same absence, from a differently-framed search angle (agent planning/memory, not
  requirements engineering/TMS) — which is stronger evidence of a genuine gap than either search
  angle alone.

---

## Summary table (this pass only)

| # | Candidate | Verified real? | Solves N-wise/cross-round conflict? | Triage |
|---|---|---|---|---|
| 1 | `ai-code-reviewer` `review.py` actual source | Yes — fetched directly, quoted, import-checked | No (confirmed: no cross-finding comparison anywhere in the prompt or code) | IMPLEMENTABLE NOW — ~120-150 lines (clustering + cap + severity-bypass) are copy-paste vendorable; prompting/dispatch scaffold is not and must be rewritten |
| 2 | FIX / COSPAN feature-interaction tool | Not independently verified (search synthesis only) | Conceptually N-wise but formal-methods input required, no modern implementation found | DROPPED — not re-verified, low expected yield |
| 3 | `pisanuw/ltms` | Yes — 4★, MIT, pushed 3 days ago, PyPI, 19 test files, read core.py/dsl.py/README directly | **Yes, mechanistically** (BCP over clause sets, dependency-directed backtracking) — but requires pre-formalized propositional input | TESTABLE — right mechanism, same translation-gap blocker as SAT/SMT in the first pass |
| 4 | `ATMS-in-Python`, `NATMS` | Yes, real but stale (2017, 2020), 1★ each | N-wise in principle, unmaintained toy ports | DROPPED — too thin/stale to build on |
| 5 | "Don't Ask the LLM to Track Freshness" (Reddy & Challaram, 2606.01435) | Yes, real paper (curl-verified) | **No — explicitly pairwise/same-key ("max() is the right operator"), scoped out compositional conflicts by the paper's own words** | Cited code **currently unreachable** (404, confirmed 2 ways) despite paper's claim of public availability — mechanism description trustworthy, code claim NOT independently verifiable right now |
| 6 | Graphiti (`getzep/graphiti`) | Yes, 28,291★, Apache-2.0, pushed today | No — same pairwise temporal-supersession pattern, confirmed independently | Corroborating evidence of the gap, not a solution to it |
| 7 | SAVeR / "Verify Before You Commit" (2604.08401) | Yes, real paper (curl-verified), ACL 2026 | No — audits single-agent internal reasoning faithfulness, not cross-artifact/decision-log consistency; no code found | RESEARCH-ONLY, wrong object of comparison |

**Overall honest verdict for this deeper pass:** Gap 1 (source code) is now closed with a concrete,
positive result — a real, small, license-clear, dependency-light chunk of code is directly
vendorable. Gaps 2 and 3 remain genuinely open, but with much stronger, more specific, more current
evidence than the first pass had: three independently-verified 2026 sources (one live 4-star active
TMS repo, one real ACL-2026-accepted paper, one 28k-star production framework), from two different
search angles (classical-AI TMS lineage, and modern LLM-agent-memory lineage), all converge on the
same conclusion — **the specific mechanism loop-team needs (detect that a NEW decision
compositionally conflicts with an ACCUMULATED set of prior decisions, operating on free-text
engineering statements, not pre-formalized logic or single-key facts) does not exist as an
off-the-shelf tool anywhere found in either research pass.** This is a confirmed, deeper-verified
dead end for "existing tool solves this," not a search failure — the sources found are the right
literature (TMS, LLM-agent-memory-conflict) and the closest real implementations in that literature,
and all of them explicitly document scoping out the exact case that matters.

---

## What changes in the reconciliation-step sketch (first pass, same file, "Reconciliation-step sketch" section)

Two concrete, evidence-backed revisions:

1. **Step (c) ("compatible merge") should cite and use the exact vendored code, not just the
   pattern.** The first pass's sketch already proposed reusing `ai-code-reviewer`'s clustering
   threshold "verbatim" — this pass confirms that's literally possible: `_raw_findings_similar` +
   `_cluster_raw_findings` (review.py:474-522, ~50 lines) can be copied into
   `reconcile_gap_records.py` almost unchanged, swapping `raw.get("file_path")`/`raw.get("category")`
   dict-key lookups for loop-team's own `gap_record["touches"]`/`gap_record["mechanism_refs"]`
   fields. The severity-bypass logic in `apply_cross_review` (review.py:372-376, the "keep unless
   every agent explicitly rejected it" pattern for CRITICAL+SECURITY) is equally copy-adaptable for
   "never silently drop a `gap_type: DESIGN` record." This upgrades that part of the sketch from
   "design pattern to reimplement" to "code to adapt with minor renames."

2. **Step (b)(3) (the mechanism-trace step) should NOT be described as filling a gap that any
   existing system already handles — this pass hardens that claim rather than weakening it.** Two
   more independently-verified, current (2026) sources (Reddy/Challaram's deterministic-recipe paper
   and Graphiti) both explicitly scope OUT exactly the case step (b)(3) exists to catch
   (compositional/cross-round conflict), using almost identical language to the first pass's NLI
   finding ("max() is the right operator" / "old facts are invalidated" = same-key supersession
   only). This means the mechanism-trace dispatch in the sketch is not a redundant reimplementation
   of some existing "memory conflict resolution" capability — it is filling a documented,
   multiply-confirmed gap that the most current 2026 literature and the most widely-used production
   memory framework both explicitly do not cover. No change to the sketch's actual mechanics is
   needed; this strengthens confidence that building it is warranted rather than reinventing
   something that already exists elsewhere.

No other part of the sketch needs revision based on this pass's findings.

---

## What I dropped and why

- FIX/COSPAN feature-interaction tooling (§2a) — search-synthesis only, old (2000s) domain, low
  expected yield given the clause-formalization requirement already established as a blocker
  elsewhere; not worth the fetch budget.
- The 5+ agent-memory survey papers named in §3 beyond SAVeR — not individually opened once three
  independently-verified sources (SAVeR, Reddy/Challaram, Graphiti) converged on the same
  "supersession/consensus, not true N-wise consistency" finding from two different search angles;
  opening more would be padding, not new evidence, per this role's own anti-padding guardrail.
- Did not attempt to build or test the English-to-clause translation layer that would be needed to
  make `pisanuw/ltms` actually usable — that's Oga/Coder build work (a concrete next-step candidate:
  prototype an LLM-based `gap_record` → `.kb`-clause extractor and validate its accuracy against a
  small hand-labeled set before trusting it), not Researcher work in this pass.

## Transfer-condition check (required per role brief) — this pass's new candidates

- **`ai-code-reviewer`'s clustering/cap/bypass code (§1):** (a) requires only stdlib +
  `models/findings.py`'s three pure-stdlib dataclasses — execution context is trivial (no
  network calls, no framework). (b) loop-team's context fully satisfies this — it's a plain Python
  harness script, same as `verify.py`/`stall_detector.py`. (c) The guarantee is structural (a
  deterministic function, not an LLM call) — this is the strongest, most directly transplantable
  fragment found across both research passes.
- **`pisanuw/ltms` (§2b):** (a) requires input already formalized as propositional clauses.
  (b) loop-team's `gap_record` fields (`broken_assumption`, `proposed_fix`) are free English text —
  context NOT satisfied without a new, unvalidated translation step. (c) The contradiction-detection
  guarantee itself (BCP unit propagation, well-founded support) IS structural/deterministic once
  clauses exist — but the translation step that would produce those clauses from English is
  necessarily an LLM call, which reintroduces exactly the "instructional-only, could fail silently"
  risk this whole line of research is trying to eliminate. Flagging explicitly: adopting `ltms`
  would trade "no contradiction detection" for "contradiction detection with an unvalidated,
  LLM-dependent translation front-end" — an improvement, but not a fully structural one, unless the
  translation step itself gets a separate accuracy check (e.g., round-trip: translate back to
  English and confirm an independent Verifier agrees it's a faithful restatement).
- **Reddy/Challaram deterministic-recipe pattern (§2c):** (a) requires facts to be reducible to
  (subject, relation, object, serial/timestamp) tuples with a single freshness axis. (b) loop-team's
  gap records aren't naturally keyed this way (two different lenses' fixes to the SAME mechanism
  aren't "newer vs. older," they're "two proposed changes to the same target, is either right").
  (c) The `max(serial)` operator is fully structural/deterministic when it applies — but it doesn't
  apply to gap-28's shape of conflict, so it isn't a candidate mechanism for loop-team's actual
  problem, only useful as corroborating evidence of the broader gap.
