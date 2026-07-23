# Verification deep-dive: 3 claims from spec-first-vs-code-first-ai-agent-builds-2026-07-08.md

**Purpose:** these 3(+1) claims survived the original adversarial-voting run only partially
(rate-limited, not refuted, or cited only at summary depth). This dispatch opens the primary
sources directly and pulls implementation-level detail, per the Mode A honesty bar (open and
quote, never re-cite a summary). Companion doc:
`~/Claude/loop/research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md`.
Feeds the compiler/typecheck-earlier-in-loop gate design following the
`H-AC-ORACLE-TARGET-1` rigor template in `~/Claude/loop/fix_plan.md`.

**Scope note:** did not dispatch any sub-agents (H-WF-DELEGATE-1 respected). All fetches below
were done directly with WebFetch/WebSearch/Bash(curl) against the live URL.

---

## 1. arXiv:2606.27045 — "The Spec Growth Engine"

**Verified via:** `https://arxiv.org/abs/2606.27045`, `https://arxiv.org/pdf/2606.27045`,
`https://arxiv.org/html/2606.27045` (the HTML render was the only one that yielded readable
prose — the raw PDF fetch returned undecoded PDF stream objects, not text, so anything below
that came only from the HTML render or the abstract page is marked as such).

- **Title (verbatim):** "The Spec Growth Engine: Spec-Anchored, Code-Coupled, Drift-Enforced
  Architecture for AI-Assisted Software Development"
- **Author (verbatim, single author — not a lab/team paper):** "Hartwig Grabowski, Hochschule
  Offenburg, hartwig.grabowski@hs-offenburg.de, ORCID: 0009-0001-4300-2626" — Hochschule
  Offenburg is a German university of applied sciences, not a major industry/research lab.
- **Venue:** arXiv:2606.27045 [cs.SE], submitted June 25, 2026. **No peer-reviewed venue found**
  — this is an arXiv preprint, not a published/accepted paper (contrast with item 2 below, which
  is FORGE 2026-accepted). Flag this maturity gap explicitly when using it to justify a gate.
- **Abstract (verbatim, opening):** "AI coding agents dramatically accelerate implementation
  speed but introduce two structural failure modes that existing spec-driven approaches do not
  fully solve: (1) context explosion – the agent must reason over an entire repository at once,
  degrading output quality as the context window fills; and (2) silent spec-code drift – code
  evolves, the specification does not, and the divergence becomes invisible until it is costly
  to repair."

### Drift Validator mechanism — the implementation detail we needed

**Verbatim (Section 5.4, from the HTML render's Figure 5 caption + surrounding text):**
> "Drift validation compares two derived graphs: Intent Graph — Specs: contracts, invariants,
> acceptance criteria. Evidence Graph — Code: imports/exports, routes/events, tests. DriftCheck."
> "The key invariant: spec and code may never diverge silently."
> "The engine derives the Intent Graph from SPEC.md files and the Evidence Graph from static
> code analysis."

So concretely:
- **Intent Graph** = derived from `SPEC.md` files; nodes carry contracts, invariants, acceptance
  criteria (i.e., spec-declared obligations).
- **Evidence Graph** = derived from static analysis of the actual codebase; nodes/edges are
  imports/exports, routes/events, and tests (i.e., what the code actually does/wires up).
- **DriftCheck** = the comparator between the two graphs.

**Hard errors (block merge unconditionally) — verbatim list from Section 5.4:**
1. "Orphan code (a source file with no spec owner)"
2. "Undeclared dependency (code imports across a spec boundary without a declared edge)"
3. "Dependency bypasses contract (code imports internal files of another node)"
4. "Missing dependency contract (a target node has no contract)"

**Soft warnings (non-blocking) — verbatim list from Section 5.4:**
1. "Declared dependency with no code evidence"
2. "Public export not mentioned in the contract"
3. "Contract behaviour without test evidence"

This maps almost exactly onto the padsplit-cockpit Slice 6b bug class (imports/exports/JSX
wiring reviewed by prose instead of caught mechanically) — items 2 and 3 in the hard-error list
are precisely "an identifier/module referenced but never bound/exported," which is the ~9-round
repeat finding that motivated this whole line of research.

### What the paper does NOT give us (important gaps, stated plainly, not papered over)

- **No reference implementation or public repo.** Verbatim, Section 10 (Availability):
  "The Spec Growth Engine is maintained as an internal design-document set; a public release is
  planned, and the documents are available from the author on request." There is nothing to
  clone, fork, or run today.
- **No empirical evaluation at all.** Targeted searches of the full HTML-rendered text for
  "evaluation", "benchmark", "case study", "TypeScript", "JavaScript", "Python" returned: zero
  hits for "evaluation," zero hits for "case study," zero hits for TypeScript/JavaScript/Python
  (the single "benchmark" hit is an unrelated citation about context-window degradation: "a
  strong model dropping from 29% to 3% on a long software-engineering benchmark as the window
  grows from 32K to 256K tokens" — not the authors' own results). **This means the paper is a
  proposed architecture/position paper, not a validated system with measured precision/recall
  or a demonstrated language ecosystem.** We should treat "Drift Validator" as a design pattern
  to independently implement and validate ourselves (exactly the H-AC-ORACLE-TARGET-1 posture:
  gate design → log → blind validation → independent verification), not as a proven tool with
  benchmark numbers to cite.
- **No stated language/ecosystem.** The paper never names TypeScript, JavaScript, or Python as
  the evaluated target — because there is no evaluation. Whether "imports/exports/routes/events"
  as evidence-graph primitives maps cleanly onto our TS/Next.js stack is an assumption we'd be
  making, not something the paper confirms.

**Bottom line for gate design:** the *concept* (two independently-derived graphs — one from
spec, one from static code analysis — diffed for hard-error-vs-soft-warning mismatches) is
concrete and directly reusable as a design pattern. The *evidence* that it works is absent —
zero benchmarks, zero public code, single-author unreviewed preprint. Cite it as "where we got
the graph-diff idea," not as "a validated technique."

---

## 2. arXiv:2601.19106 — AST-analysis hallucination detector

**Verified via:** `https://arxiv.org/abs/2601.19106`, `https://arxiv.org/pdf/2601.19106`
(binary/undecoded, same limitation as above), `https://arxiv.org/html/2601.19106` (readable).

- **Title (verbatim):** "Detecting and Correcting Hallucinations in LLM-Generated Code via
  Deterministic AST Analysis"
- **Authors (verbatim):** Dipin Khati, Daniel Rodriguez-Cardenas, Paul Pantzer, Denys
  Poshyvanyk
- **Venue:** **Accepted to FORGE 2026** (International Conference on the Foundations of
  Software Engineering / ICSE-affiliated forge track); submitted January 27, 2026,
  arXiv:2601.19106. This is a stronger maturity signal than item 1 — peer-reviewed acceptance,
  not just a preprint.
- **Tool/framework name:** confirmed **no branded/capitalized tool name exists**. The paper
  refers to it descriptively throughout as "our framework," "the framework," "our deterministic
  approach" — there is no acronym like "the paper's Foo tool." (Our original doc's "AST-analysis
  framework" phrasing was already correct — there's no missed proper-noun name to correct it to.)
- **What the framework does (verbatim):** "a post-processing framework that parses generated
  code into an Abstract Syntax Tree (AST) and validates it against a dynamically-generated
  Knowledge Base (KB) built via library introspection," addressing "Knowledge Conflicting
  Hallucinations (KCHs) — semantic errors in LLM-generated code like non-existent API
  parameters, that evade linters and cause runtime failures."

### Precision / recall / F1 — re-confirmed directly

**Verbatim:** "the framework detected KCHs with 100% precision and 87.6% recall (0.934
F1-score)." (0.934 = 2·1.0·0.876/(1.0+0.876), so the F1 figure is internally consistent, not a
copy error.) A separate "overall detection performance" figure is also given: "90% accuracy and
a 93.4% F1-Score" — accuracy is a distinct metric from precision/recall (accuracy counts
correctly-classified-either-way over ALL samples including true negatives; precision/recall are
computed only over positive predictions/actual positives), so these two stats are not in
conflict, just different lenses on the same run.

### The 97.9% missing-import number — RESOLVED (this was the specific gap flagged in our doc)

**This is now fully verified from the paper's own results table**, and the resolution is more
nuanced than our prior doc's phrasing ("missing-import detection specifically at 97.9%"):

**Table 3 verbatim ("Detection and Correction Performance by KCH Type"):**

| Hallucination Type | Sample count | Detect. Rate | Corr. Acc. |
|---|---|---|---|
| Missing Imports | 48 | 97.9% | 97.9% |
| Mis-typed API Calls | 110 | 84.5% | 70.0% |
| Contextual Mismatches | 3 | 33.3% | 0.0% |

**Verbatim surrounding sentence:** "The fix rate was highest for Missing Imports (97.9%) but
dropped for Mis-typed APIs (70.0%)."

**Resolution:** 97.9% is genuinely a per-category number **directly reported in the paper's own
results table**, not an "unverified-but-corroborating" inference as our prior doc hedged — that
hedge can be dropped. But note the nuance: the table gives **both** a Detection Rate (97.9%) and
a Correction Accuracy (97.9%) for the Missing Imports category, and they happen to be numerically
identical for this row (they diverge sharply for the other two categories — e.g. Mis-typed API
Calls detects at 84.5% but only corrects 70.0% of those). So "97.9%" is correct for BOTH
detection and auto-fix of missing imports specifically (n=48 samples), and our doc should cite it
as a verified table figure with that dual caveat, not as a single ambiguous number.

**Method definitions (verbatim):** "Hallucination Detection Accuracy: The detector's ability to
identify KCHs, treated as a binary classification problem" vs. "Hallucination Fix Accuracy: For
snippets correctly identified as hallucinated, we measure the 'fix accuracy.'"

- **Dataset:** 200 manually-curated Python snippets (39 clean + hallucinated samples across the
  three KCH categories above). **This confirms the doc's implicit assumption that the benchmark
  is Python-only** — there is no TypeScript/JavaScript evaluation in this paper either. If we
  want this exact precision/recall profile for our TS/Next.js stack, it would need re-validation
  on a TS-specific AST + library-introspection KB; the paper's numbers don't transfer
  automatically across languages.
- **Auto-correction overall:** "Our framework achieved a high overall Fix Accuracy of 77.0%."

---

## 3. Cross-reference / "see above/below" style-guide stance — 3 independent sources, all confirmed

The original doc flagged this claim as not surviving adversarial vote "due to a rate-limit
error, not a refutation." Fully resolved below with 3 independent primary sources (Google,
Microsoft, MDN) plus a working lint rule (bonus item 4).

### 3a. Google developer documentation style guide

**Source:** `https://developers.google.com/style/word-list` (word-list entries) and
`https://developers.google.com/style/accessibility` (rationale). The dedicated
`/style/cross-references` page (`https://developers.google.com/style/cross-references`) does
NOT itself contain the above/below guidance — it covers same-page section-linking mechanics
instead (verbatim: "When you're linking to another section on the same page, let the reader know
that the link takes you to a different section of the same page," with example "For more
information, see the [Write descriptive link text](#descriptive-link-text) section of this
document."). The above/below rule specifically lives in the word list and accessibility pages,
not the cross-references page — correcting our prior doc's implicit assumption about where in
Google's guide this rule sits.

**Word list, verbatim:**
- "above" entry: "Don't use for a range of version numbers. Instead, use *later*. Don't use to
  refer to a position in a document. Instead, use *earlier* or *preceding*." (Acceptable in
  non-directional/hierarchical use.)
- "below" entry: "Don't use for a range of version numbers. Instead, use *earlier*. Don't use to
  refer to a position in a document. Instead, use *later* or *following*." (Acceptable in set
  phrases like "below average," "below zero.")

**Accessibility page, verbatim:** "Don't use directional language to orient the reader, such as
*above*, *below*, or *right-hand*" — "doesn't work well for accessibility or for localization
reasons" (RTL languages reverse spatial positioning; screen readers have no concept of "above").
Example pair given: recommended "In the preceding diagram, clients run jobs..." vs. not
recommended "In the diagram above, clients run jobs..."

### 3b. Microsoft Writing Style Guide — independent second source, CONFIRMED

**Source:** `https://learn.microsoft.com/en-us/style-guide/a-z-word-list-term-collections/a/above`
(fetched directly, full page content retrieved including metadata — last updated 2026-07-06).

**Verbatim:** "Don't use to mean *earlier*. Don't use as an adjective preceding a noun (*the
above section*) or following a noun (*the code above*). Use a link, or use *previous, preceding,*
or *earlier.*" Example given: "Use the preceding code to display information about the database.
See [Installation instructions](https://example.com/). See Installation instructions, earlier in
this article." A parallel "below" entry exists at
`/en-us/style-guide/a-z-word-list-term-collections/b/below` with the mirror-image guidance (use a
link, *later*, or *the following* instead of "below").

Note: `https://learn.microsoft.com/en-us/style-guide/cross-references` (the URL guessed from the
page-naming pattern) returned a **404 — that specific path does not exist**; the real content
lives under the A-Z word-list term-collection path found via search, not a dedicated
"cross-references" page. Flagging this so nobody re-tries the guessed URL and reports a false
"Microsoft has no cross-reference guidance."

### 3c. MDN Writing Style Guide — third independent source

**Source:** `https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Writing_style_guide`
(fetched directly).

**Verbatim:** "Avoid using spatial and directional words, such as 'above', 'below', 'left',
'right', or 'here'. These terms assume a specific visual layout, which may not apply to all
users. They can also be unclear or misleading—especially for users relying on screen readers or
those reading translated content, where directional language can be ambiguous or difficult to
translate accurately." With paired correct/incorrect examples, e.g. correct: "This concept is
explained in the earlier section titled Creating a media query" vs. incorrect: "This concept is
explained in the section above."

**Conclusion: 3-for-3, all independently confirmed, not a single-source or rate-limit-orphaned
claim.** Google, Microsoft, and MDN all independently proscribe "above/below" as document
position-references and all recommend the same fix family: either a real link/anchor, or
positionally-neutral language ("earlier," "preceding," "following," "later"). This is safe to
promote from "unverified, rate-limited" to fully confirmed in the source doc.

---

## 4. Bonus — an existing lint rule for this exact anti-pattern (adopt, don't hand-roll)

**Found: yes, a real, working rule exists** — but it is narrower than the full "as mentioned
above / see below" phrase pattern; it catches the bare word "above" only.

**Source:** `https://github.com/errata-ai/Google` — "A Vale-compatible implementation of the
Google Developer Documentation Style Guide," and specifically
`https://raw.githubusercontent.com/errata-ai/Google/master/Google/WordList.yml` (fetched raw via
curl, not summarized).

**Verbatim rule (from the actual YAML, first ~15 lines confirmed via `curl`):**
```yaml
extends: substitution
message: "Use '%s' instead of '%s'."
link: "https://developers.google.com/style/word-list"
level: warning
ignorecase: false
action:
  name: replace
swap:
  ...
  above: preceding
  ...
```
This is a **Vale `substitution`-type rule**, `level: warning` (non-blocking by default, but Vale
supports promoting any rule to `level: error` in a project's `.vale.ini` for CI-blocking use),
linked directly back to the Google word-list page fetched in item 3a. Confirmed via `grep -i
"above\|below"` on the raw file that **only `above: preceding` exists — there is no `below`
entry in this file**, and no dedicated rule for full phrases like "see above," "as mentioned
above," or "see below" anywhere in the `Google/` rule directory (confirmed by listing the
directory's YAML files: WordList.yml, Acronyms.yml, Spelling.yml, Slang.yml, Latin.yml,
AMPM.yml, Colons.yml, Contractions.yml, DateFormat.yml, Ellipses.yml, EmDash.yml, Exclamation.yml,
FirstPerson.yml, Gender.yml, GenderBias.yml, HeadingPunctuation.yml, Headings.yml, LyHyphens.yml,
OptionalPlurals.yml, Ordinal.yml, OxfordComma.yml, Parens.yml, Passive.yml, Periods.yml,
Quotes.yml, Ranges.yml, Semicolons.yml, Spacing.yml, Units.yml, We.yml, Will.yml — none of these
target directional cross-reference phrases beyond the single WordList.yml swap).

**Actionable conclusion:** Vale + the official `errata-ai/Google` style package is a real,
installable, zero-authoring-cost way to catch bare "above" in markdown specs today (`vale
--config=... spec.md`, with the Google style package added). It does **not** fully cover "see
below," "as mentioned above," or "as discussed below" as multi-word phrases — those would need a
small custom Vale `existence`-type rule (a regex list) layered on top, which is cheap to
hand-write (a 5-10 line YAML) rather than needing to invent the linting approach from scratch.
`markdownlint` was searched and has no equivalent built-in rule (its rule set is structural/
formatting-focused — heading levels, list markers, line length — not prose-content rules; that
class of check is Vale/textlint's job, not markdownlint's).

---

## Honesty-bar summary — what could and could not be verified

| # | Claim | Status |
|---|---|---|
| 1 | 2606.27045 title/author/venue | VERIFIED — single author, unreviewed arXiv preprint (not FORGE/ICSE-accepted) |
| 1 | Drift Validator / Intent Graph / Evidence Graph mechanism detail | VERIFIED — exact hard-error/soft-warning lists quoted from Section 5.4 |
| 1 | Reference implementation / repo | **NOT AVAILABLE** — paper states explicitly it's an internal doc set, "available from the author on request," no public code |
| 1 | Language/ecosystem evaluated | **NOT VERIFIABLE — because none exists.** No empirical evaluation of any kind in the paper (confirmed by targeted full-text search for "evaluation," "benchmark," "TypeScript," "Python," "case study") |
| 2 | 2601.19106 title/authors/venue | VERIFIED — FORGE 2026 accepted, 4 named authors |
| 2 | 100% precision / 87.6% recall / 93.4% F1 | VERIFIED verbatim from paper text |
| 2 | 97.9% missing-import number | VERIFIED — in Table 3, but is BOTH the detection rate AND correction accuracy for that category (identical values), not a single unambiguous stat; dataset is Python-only (200 snippets) |
| 3 | Google style guide above/below stance | VERIFIED verbatim (word-list + accessibility pages; NOT on the cross-references page as might be assumed) |
| 3 | Microsoft Writing Style Guide, second source | VERIFIED verbatim (A-Z word list page; the guessed `/style-guide/cross-references` URL 404s — use the word-list path instead) |
| 3 | MDN, third source | VERIFIED verbatim (bonus — a third independent confirmation beyond what was asked) |
| 4 | Existing lint rule for the anti-pattern | VERIFIED — real Vale rule exists (`errata-ai/Google` WordList.yml, `above: preceding`, warning-level) but only covers the single word "above," not full phrases or "below" |

**Nothing in this dispatch hit an unresolvable rate-limit or paywall** — every URL fetched
successfully on the first or second attempt (the only failures were an incorrectly-guessed
Microsoft URL, resolved by finding the correct one via search, and the raw-PDF fetches returning
undecoded binary, resolved by using the `arxiv.org/html/...` render instead).

## Implication for the gate design (not yet acted on — for Oga to weigh)

The single most load-bearing correction this dispatch makes to the source doc: **arXiv:2606.27045
is not a validated system** — no benchmark, no public code, unreviewed preprint, single author at
a teaching-focused university. It should be cited in the gate's design rationale as "where the
Intent-Graph/Evidence-Graph pattern name comes from," with the actual precision/recall evidence
for "mechanical detection catches binding bugs" resting on arXiv:2601.19106 instead (which IS
peer-reviewed and DOES report real numbers) — but that paper is Python/AST-only, so its 87.6%
recall / 100% precision figures do not directly transfer to a TypeScript/Next.js gate; if the new
gate's efficacy claim needs a number, it will have to be measured on our own stack (tsc/eslint
output on the padsplit-cockpit repo), not borrowed from either paper.
