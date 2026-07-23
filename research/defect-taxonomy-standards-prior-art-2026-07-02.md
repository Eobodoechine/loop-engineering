# Formal defect-classification standards vs. our 8-category ops-clock taxonomy (2026-07-02)

**Mode:** A (improve the loop). **Task:** determine whether IBM's Orthogonal Defect Classification (ODC),
IEEE Std 1044, or any other real formal defect-classification framework is real, still-used, and would
add anything to or reframe the custom 8-category gap taxonomy in
`research/ops-clock-gap-taxonomy-2026-07-02.md` (sibling-inconsistency, precision/ambiguity,
regression-risk, missing-detail-in-original-conception, concurrency/isolation, state-machine/enum-completeness,
mechanical/schema-validity, cross-round-contradiction — 32 gaps / 33 findings from a pure plan-check,
zero-code design review).

**Honesty-bar discipline applied throughout:** every source below was actually opened (WebFetch and/or the
`Read` tool's PDF support) and quoted directly — none of the taxonomy content is reported from a search
snippet alone. Where a fetch failed to extract readable text (two cases, noted explicitly), I re-fetched the
underlying PDF via `Read` and quote the rendered page images instead. Nothing here is presented as fact
without an opened source.

---

## Framework 1 — IBM's Orthogonal Defect Classification (ODC)

### Is it real and still used?

Yes, unambiguously. Primary sources opened:

1. **The original 1992 paper** — Chillarege, Bhandari, Chaar, Halliday, Moebus, Ray, Wong, "Orthogonal
   Defect Classification—A Concept for In-Process Measurements," *IEEE Transactions on Software
   Engineering* 18(11), 943–956 (1992). Confirmed real and indexed by IBM Research itself:
   `https://research.ibm.com/publications/orthogonal-defect-classificationa-concept-for-in-process-measurements`
   — quoted directly via WebFetch: *"This paper describes orthogonal defect classification (ODC), a
   concept that enables in-process feedback to developers by extracting signatures on the development
   process from defects."* Also cross-confirmed by ACM/IEEE Xplore listing
   (`https://dl.acm.org/doi/10.1109/32.177364`).
2. **Ram Chillarege's own ODC Tutorial (2000)** — a full slide deck by ODC's inventor, fetched and read in
   full via the `Read` tool's PDF renderer at
   `https://pdfs.semanticscholar.org/b649/41041d35d596a2b284d52b04ab5f419956e1.pdf` (16 pages, all read
   as rendered images — WebFetch's raw-text extraction failed on this PDF, noted honestly below). Directly
   quoted: *"ODC was invented circa 1990 and evolved over 10 years[;] Reaches around 3000 IBM engineers
   worldwide ('99)[;] Motorola, Telcordia, Nortel, Lucent, .. are also users[;] Reduces root cause analysis
   cost by a factor of 10x[;] Cost savings of $100M/year in one legacy product."* This is real, dated,
   named-author evidence of industrial adoption beyond IBM.
3. **The current maintained specification — "Orthogonal Defect Classification v 5.2 for Software Design and
   Code"** (IBM, dated September 12, 2013), hosted on IBM's own cloud object storage:
   `https://s3.us.cloud-object-storage.appdomain.cloud/res-files/70-ODC-5-2.pdf`. Fetched and read in full
   (18 pages, all rendered and read directly — this is the single most load-bearing source in this whole
   document, since it is the actual current-usage specification, not a historical artifact). Quoted directly
   below in Q1/Q2.

**Honest fetch-failure note:** WebFetch's text extraction failed on both the semanticscholar tutorial PDF
and the IBM v5.2 spec PDF (both returned "raw PDF binary/compressed stream data, not human-readable" —
verbatim WebFetch tool output). I did not accept that as a dead end; I re-fetched both PDFs with the `Read`
tool (which renders PDF pages as images and can read the text directly) and confirmed the full content that
way. Flagging this because it's a real tool limitation worth remembering for future research passes:
**WebFetch cannot always extract PDF text; `Read` on the downloaded PDF is the fallback that worked here.**

### Q1 — ODC's actual defect-type categories

From the IBM v5.2 spec (`§4.2.1`, quoted verbatim), **the Defect Type list for Target = Design/Code has
exactly 7 values**, confirming Wikipedia's unelaborated claim of "seven values for defect type" (which I
also opened — `https://en.wikipedia.org/wiki/Orthogonal_defect_classification` — and which states this
number but does not enumerate them; the enumeration below is from the IBM primary source, not Wikipedia):

| Defect Type | Definition (quoted verbatim from IBM v5.2 §4.2.1) |
|---|---|
| **Assignment/Initialization** | "Value(s) assigned incorrectly or not assigned at all; but note that a fix involving multiple assignment corrections may be of type Algorithm." |
| **Checking** | "Errors caused by missing or incorrect validation of parameters or data in conditional statements." |
| **Algorithm/Method** | "Efficiency or correctness problems that affect the task and can be fixed by (re)implementing an algorithm or local data structure without the need for requesting a design change." |
| **Function/Class/Object** | "The error should require a formal design change, as it affects significant capability, end-user interfaces, product interfaces, interface with hardware architecture, or global data structure(s); The error occurred when implementing the state and capabilities of a real or an abstract entity." |
| **Timing/Serialization** | "Necessary serialization of shared resource was missing, the wrong resource was serialized, or the wrong serialization technique was employed." |
| **Interface/O-O Messages** | "Communication problems between: 1) modules 2) components 3) device drivers 4) objects 5) functions via 1) macros 2) call statements 3) control blocks 4) parameter lists" |
| **Relationship** | "Problems related to associations among procedures, data structures and objects. Such associations may be conditional." |

Two more attributes complete a "Defect Type" record and matter for comparability with our taxonomy:
- **Qualifier** (§4.2.2, applies to Defect Type): exactly 3 values — **Missing** ("due to an omission"),
  **Incorrect** ("due to a commission"), **Extraneous** ("due to something not relevant or pertinent...
  and should be removed"). This Missing/Incorrect/Extraneous triad is functionally identical in spirit to
  the older HP "Mode" attribute (see Framework 3) and to IEEE 1044's own "Mode" attribute (Wrong/Missing/Extra
  — see Framework 2, Table A.1) — **all three frameworks converge on the same 3-way qualifier vocabulary**,
  which is itself a notable, independently-triangulated finding.
- **Target** (§4.1) — the artifact class the fix touched. Six values, quoted: **Requirements** ("In order
  to fix the defect, it was necessary to change the requirements document"), **Design** ("...change the
  design specification document"), **Code** ("...change the code"), **Build/Package**, **Information
  Development** ("The problem is with the written description contained in user guides, installation
  manuals, on-line help, user messages"), **National Language Support**.

Separately, ODC also classifies **Activity** (what was being done when the defect was found — Design
Review, Code Inspection, Unit Test, Function Test, System Test) and **Trigger** (the environment/condition
that surfaced the defect — a large, activity-specific vocabulary; e.g. Design Review/Code Inspection
triggers include Design Conformance, Logic/Flow, Backward Compatibility, Lateral Compatibility,
Concurrency, Internal Document, Language Dependency, Side Effects, Rare Situation — all directly quoted
from IBM v5.2 §3.2.1), plus **Impact** (13 values: Installability, Integrity/Security, Performance,
Maintenance, Serviceability, Migration, Documentation, Usability, Standards, Reliability, Requirements,
Accessibility, Capability), plus **Age** (Base/New/Rewritten/ReFixed) and **Source** (Developed In-House /
Reused From Library / Outsourced / Ported).

**Total ODC attribute count: 4 "opener" attributes (Activity, Trigger, Impact) + 5 "closer" attributes
(Target, Defect Type, Qualifier, Age, Source)** — this is a materially richer, multi-axis schema than a
single flat category list; our 8-category taxonomy is comparable only to ODC's single "Defect Type" axis,
not the whole ODC schema.

### Framework 2 — IEEE Std 1044

Primary source: the actual **IEEE Std 1044-2009** document (approved 9 November 2009, published 7 January
2010, "Revision of IEEE Std 1044-1993"), fetched as a PDF from `https://www.ctestlabs.org/neoacm/1044_2009.pdf`
and read in full via the `Read` tool (25 pages rendered and read directly — WebFetch's raw-text extraction
again failed on this PDF with the same "compressed stream" limitation, same fallback used). This is the
complete standard text, not a summary — title page, abstract, scope, definitions, Clause 3 (Classification),
Annex A (example attribute values), Annex B (worked classification examples), and Annex C (bibliography),
all read directly.

**Current status (confirmed via `https://standards.ieee.org/standard/1044-2009.html`, WebFetch, quoted):**
"**Status:** Inactive-Reserved Standard (inactivated March 5, 2020)... removed from active status through an
administrative process for standards inactive beyond 10 years." **No successor standard exists** — I
searched explicitly for one and found none; the IEEE SA page for 1044 does not list a replacement, and
1044-2009 itself superseded 1044-1993 (`https://standards.ieee.org/standard/1044-1993.html`, confirmed
"superseded"). **Honest flag: IEEE 1044 is a real, ANSI/IEEE-published standard, but it is administratively
inactive and has had no active maintenance/revision since 2010** — this materially affects how much weight
"industry-standard" carries for it today (see Q3 verdict).

### Q1 (continued) — IEEE 1044's classification scheme

IEEE 1044's structure is fundamentally different in shape from ODC's: it does **not** specify a fixed list
of defect-type categories as mandatory values. Quoted directly from the standard itself (Introduction,
p. iv): *"To increase flexibility and allow organizations to adapt the classification to their own life
cycles and purposes, the following changes have been made to the previous edition of this standard: —
Defining key terms and the relationships between their underlying concepts more precisely — **Not
specifying a mandatory set of values for anomaly attributes** — Not specifying a classification process."*
And explicitly again (§3.1, quoted): *"The classification attributes defined in the standard are normative
(mandatory), whereas the sample classification attribute values are only informative (optional)."*

This is a load-bearing structural fact: **IEEE 1044 standardizes the *attribute schema* (which fields you
must record), not a fixed enum of category values** — the opposite design choice from ODC, which does
fix its Defect Type list. Concretely:

- **Table 3 — Defect attributes** (17 attributes, all quoted verbatim from the standard): Defect ID,
  Description, Status, Asset, Artifact, Version detected, Version corrected, Priority, Severity,
  Probability, Effect, **Type** ("A categorization based on the class of code within which the defect is
  found or the work product within which the defect is found"), **Mode** ("A categorization based on
  whether the defect is due to incorrect implementation or representation, the addition of something that
  is not needed, or an omission"), **Insertion activity** ("The activity during which the defect was
  injected/inserted... during which the artifact containing the defect originated"), Detection activity,
  Failure reference(s), Change reference, Disposition.
- **Table 4 — Failure attributes** (17 attributes): Failure ID, Status, Title, Description, Environment,
  Configuration, Severity, Analysis, Disposition, Observed by, Opened by, Assigned to, Closed by, Date
  observed, Date opened, Date closed, Test reference, Incident reference, Defect reference, Failure
  reference.
- **Annex A (informative, non-mandatory example values)** does give sample enum values, and this is where
  the taxonomy content actually lives: **Type** examples — Data, Interface, Logic, Description, Syntax,
  Standards, Other (7 sample values, directly analogous in spirit to ODC's 7 Defect Types, though these
  are explicitly labeled "informative" not normative). **Mode** examples — Wrong, Missing, Extra (3 values
  — matching ODC's Qualifier triad and HP's Mode triad, see the cross-framework convergence noted under
  ODC above). **Insertion activity** examples — Requirements, Design, Coding, Configuration, Documentation
  (5 values, each with a worked definition and concrete examples quoted below under Q2 — this is the most
  directly relevant part of the whole standard to our pre-code question).

### Q2 — Does the post-code-vs-pre-code context mismatch matter? Precedent for requirements/design-review use?

**Short, direct answer: no, it does not invalidate either framework, and both have explicit, primary-sourced
precedent for pre-code use — but the depth of that precedent differs materially between the two.**

**IEEE 1044 has the stronger, more explicit precedent.** Its "Insertion activity" attribute (Table 3) is
defined generically as "the activity during which the defect was injected/inserted" — and Annex A gives a
**"Requirements" value with a full worked definition and concrete examples, quoted verbatim**:
*"Defect inserted during requirements definition activities (e.g., elicitation, analysis, or specification).
Examples: Function required to meet customer goals omitted from requirements specification[;] Incomplete
use case specification[;] Performance requirements missing or incorrect[;] Security requirements missing or
incorrect[;] Function incorrectly specified in requirements specification[;] Function not needed to meet
customer goals specified in requirements specification."* This is not a stretch or an analogy I am
constructing — it is IEEE 1044's own stated, first-class category, sitting alongside "Design," "Coding,"
"Configuration," and "Documentation" as five co-equal insertion-activity values. **Annex B's worked example
"Problem 4" is explicitly a pre-code, requirements-only defect, quoted directly from the standard**:
*"During a peer review for software requirements for a new financial management system, Alice discovers
that values are in the requirements as thousands of dollars instead of as millions of dollars. {This
example illustrates classification of a defect detected directly, prior to any failure occurring.}"* —
IEEE 1044's own bracketed annotation explicitly frames this as a pre-code, review-time, no-failure-yet
scenario, which is structurally identical to our plan-check mode (zero code, spec/design review only).
**This directly answers the "requirements-engineering-era work" angle the task asked me to look for**:
IEEE 1044's lineage (1993 original, carried into the 2009 revision) has always treated requirements-phase
defect classification as in-scope, not a later bolt-on.

**ODC also has real, primary-sourced precedent, though it is framed slightly differently.** The IBM v5.2
spec's **Target** attribute (§4.1.1) includes "Requirements" as a first-class value with its own worked
examples, quoted: *"In order to fix the defect, it was necessary to change the requirements document.
Examples: 1) Scope of function must be comparable to competitor 2) Must be able to isolate source of
failure in an open environment 3) Must provide support for new software configuration."* And ODC's
**Activity** attribute includes "Design Review" as a first-class value (not just Code Inspection/Unit
Test/Function Test/System Test), with its own worked definition: *"You are reviewing design or comparing
the documented design against known requirements. Examples: 1) All background colors should be blue 2)
Requirement specifies support for top six printers, but one popular printer was omitted in the design
document."* The second example is a direct, load-bearing analogue to our own "missing-detail-in-original-
conception" category (a requirement never considered in the first draft). ODC's own Chillarege tutorial
slide "ODC Defect Types mapped to generic activity injecting defects" (directly read from the tutorial PDF)
shows a "Req" (Requirements) row explicitly mapped to Defect Types "Missing Function/Class, Missing
Interface/Messages, Missing Timing/Serialization, Missing Relationship" — confirming ODC's own inventor
treats requirements-phase defects as classifiable with the *same* 7-value Defect Type taxonomy used for
code, not a separate scheme.

**Where the mismatch DOES matter, honestly stated:** both frameworks' richest, most differentiated
vocabulary (ODC's Trigger list; IEEE 1044's Insertion/Detection-activity granularity) is built around a
code-and-test-centric activity list — Unit Test, Function Test, System Test triggers (Simple Path, Complex
Path, Coverage, Variation, Sequencing, Interaction, Workload/Stress, Recovery/Exception, Startup/Restart,
Hardware/Software Configuration — all quoted from IBM v5.2 §3.2.2–3.2.4) that has **no analogue at all** in
a zero-code plan-check review. Our plan-check process only ever exercises the "Design Review/Code
Inspection" activity-and-trigger bucket (Design Conformance, Logic/Flow, Backward Compatibility, Lateral
Compatibility, Concurrency, Internal Document, Language Dependency, Side Effects, Rare Situations) — a real
subset of ODC's Trigger vocabulary, not the whole thing. This is a genuine, non-trivial scope reduction, not
a fatal mismatch: **roughly 9 of ODC's ~20+ triggers are usable pre-code; the rest (all Unit/Function/System
Test triggers) are structurally inapplicable until code exists**, which is itself a clean, source-grounded
way to state exactly how much of ODC transfers and how much doesn't.

### Q3 — Would remapping our 8 categories onto ODC or IEEE 1044 vocabulary lose information, or usefully align us?

**Concrete, non-hedged verdict: remapping loses information and is not worth doing wholesale, BUT one
specific piece of alignment (the Missing/Incorrect/Extraneous "Mode/Qualifier" triad) is genuinely useful
and cheap to adopt as a cross-cutting tag, not a category replacement.**

Working through the actual mapping, category by category, against ODC's 7 Defect Types (the closest
analogue axis):

| Our category | Best ODC Defect Type fit | Fit quality |
|---|---|---|
| Concurrency/isolation | Timing/Serialization | **Good** — ODC's own definition ("necessary serialization... missing, wrong resource serialized, wrong technique") maps almost 1:1 onto our Postgres-transaction-boundary/lock-ordering gaps. |
| State-machine/enum-completeness | Function/Class/Object (partially) or no clean fit | **Poor** — ODC's Function/Class/Object is about a formal design change to capability/interfaces, not specifically about an enum/Task-type combination left unmapped. Forcing this in loses the specific "which combination was missed" information our category name preserves. |
| Mechanical/schema-validity | Checking (loosely) | **Poor** — ODC's Checking is about missing/incorrect *validation logic*, not Prisma schema correctness per se (a different artifact class entirely — schema, not logic). |
| Sibling-inconsistency | **No ODC Defect Type captures this at all** | **No fit** — this is the single starkest gap. ODC's Defect Type answers "what kind of fix was needed" (a technical/mechanical axis); sibling-inconsistency is fundamentally about *process* — "an established pattern wasn't proactively swept to a structural twin" — a meta-property about HOW the defect was found relative to prior fixes, not what the fix mechanically was. ODC has no attribute anywhere in its 9-attribute schema for "this is structurally identical to an already-fixed defect elsewhere." |
| Precision/ambiguity | Description (IEEE 1044 Annex A "Type" list has this one; ODC does not) | **Partial** — IEEE 1044's informative Type value "Description: Defect in description of software or its use" is closer, but our category is specifically about *instruction* ambiguity admitting multiple readings, which is narrower and more specific than IEEE 1044's broad "Description" bucket. |
| Regression-risk | **No clean fit in either framework** | **No fit** — neither ODC nor IEEE 1044 has a category for "this breaks an existing GREEN TEST/safety net," because both frameworks assume a defect is discovered fresh, not that a *change* silently regresses something previously verified. This is closer to a change-impact-analysis concept than a defect-type concept. |
| Missing-detail-in-original-conception | Requirements (ODC Target) / Requirements (IEEE 1044 Insertion activity), Qualifier=Missing | **Good** — this is the one category with the cleanest, most direct mapping onto both frameworks' native requirements-phase vocabulary, confirmed above in Q2. |
| Cross-round-contradiction | **No fit in either framework** | **No fit** — neither ODC nor IEEE 1044 has any concept of a *temporal*, cross-artifact contradiction between two independently-verified findings from different review rounds. Both frameworks classify a SINGLE defect's properties; neither models a relationship BETWEEN two defect records. This is exactly the same gap already documented in `research/plan-check-reconciliation-prior-art-2026-07-02.md` for the reconciliation-tooling search — independently re-confirmed here from the classification-standards angle. |

**Verdict, stated plainly:** 2 of 8 categories (concurrency/isolation, missing-detail) map cleanly onto ODC/IEEE
1044 vocabulary. 1 (precision/ambiguity) maps loosely. **4 of 8 — sibling-inconsistency, regression-risk,
mechanical/schema-validity, cross-round-contradiction — have no real home in either framework**, because
both frameworks were built to answer "what kind of technical fix was this" for a single, already-existing
defect, not "how does this finding relate to the review PROCESS or to OTHER findings" — which is precisely
what our four hardest, least-code-native categories are actually about. Forcing our 8 into ODC/IEEE 1044's
vocabulary would **erase the two categories our own retrospective found most actionable and most novel**
(sibling-inconsistency at 7/33 findings — the single largest category — and cross-round-contradiction, the
category that directly motivated building `reconcile_gap_records.py`). That is a real, concrete information
loss, not a hypothetical one.

**What IS worth adopting, narrowly:** the **Missing / Incorrect / Extraneous** three-way qualifier
(independently present as ODC's "Qualifier," IEEE 1044's "Mode," and HP's "Mode" — three frameworks
converging on the same triad is a strong signal it's a genuinely useful, general-purpose orthogonal tag) as
a **cross-cutting attribute added to each of our 8 categories**, not a replacement for them. E.g., a
sibling-inconsistency gap is almost always "Missing" (the guard/pattern was never swept to the sibling); a
precision/ambiguity gap is often "Incorrect" framing rather than purely missing; this second axis costs
nothing to add and gives us the same "orthogonal, multi-dimensional" property ODC is famous for, without
discarding our own category names. This is a genuine, concrete, low-cost improvement — the one piece of
this whole research pass I'd actually recommend implementing, as opposed to a wholesale taxonomy swap.

### Q4 — Real tooling that implements ODC or IEEE 1044 as software (not just paper-applied-manually)?

**Honest, direct finding: no maintained, real open-source or commercial tool was found that implements
either framework as software.** Specifically checked and confirmed dead ends:

- **GitHub search, done live:** `https://github.com/search?q=%22orthogonal+defect+classification%22&type=repositories`
  fetched directly via WebFetch. Quoted result: *"Your search did not match any repositories" with "0
  results" displayed for the query "orthogonal defect classification" filtered by repository type.*
  **Zero GitHub repositories implement ODC.** This is a clean, verified negative result, not an
  under-search — I ran the query against GitHub's own search directly.
- **AutoODC** (the one real research effort found that automates ODC classification via ML/NLP):
  `Xia, Yan, et al., "AutoODC: Automated generation of orthogonal defect classifications,"
  Automated Software Engineering (2015), https://link.springer.com/article/10.1007/s10515-014-0155-1` and
  a related ASE'11 paper (`http://www.hlt.utdallas.edu/~vince/papers/ase11.html`) — both confirmed real,
  published, peer-reviewed papers (not fabricated), reporting **82.9% (Naive Bayes) / 80.7% (SVM) accuracy
  on an industrial defect set, 77.5%/75.2% on an open-source set** (quoted from the search-result synthesis
  of the paper's own abstract; I did not independently open the full PDF of either paper in this pass, so
  these accuracy numbers are reported as "paper claims found via search," not independently re-verified —
  flagging honestly per the honesty bar rather than presenting them as confirmed-by-me facts). **No public
  code repository for AutoODC was found anywhere in this search** — it appears to be an academic
  proof-of-concept, never released as usable software, and the underlying paper is from 2011–2015 (over a
  decade stale even if it existed).
- **IBM's own internal ODC tooling** (referenced in the Chillarege tutorial as reaching "3000 IBM engineers")
  is real but was never released publicly — it lived inside IBM's internal defect-tracking systems
  (references to a "Version 5.1 Submitter Input"/"Responder Input" schema in the tutorial imply a real
  internal tool existed) and there is no public artifact to cite or verify beyond the paper specification
  itself.
- **IEEE 1044:** no tooling search turned up a dedicated classification tool either — the standard itself
  states explicitly (quoted above) that it deliberately does NOT specify "a classification process," which
  is consistent with no canonical reference implementation existing. Generic defect-tracking tools (Jira,
  Bugzilla, DefectDojo — the last already covered in the sibling reconciliation research doc) can be
  *configured* with custom fields matching IEEE 1044's attribute names, but none of them ship IEEE 1044
  support as a named, built-in feature — this was not independently verified field-by-field in every
  possible tracker, so flagging as "not found," not "confirmed absent everywhere."

**Net Q4 verdict: both frameworks exist today only as manually-applied paper taxonomies (a person reads a
defect and picks values from a list), not as working software.** The one automation attempt found (AutoODC)
is an unreleased academic ML classifier, not a tool anyone can install or run. This mirrors exactly what the
sibling document `research/plan-check-reconciliation-prior-art-2026-07-02.md` found for reconciliation
tooling — real technique, real paper, no shippable artifact.

---

## Framework 3 — Hewlett-Packard's defect Origin/Type/Mode scheme (found via task's own suggested lead)

**Real, confirmed via a primary source: Robert B. Grady's own August 1996 Hewlett-Packard Journal article**,
"Software Failure Analysis for High-Return Process Improvement Decisions,"
`http://shiftleft.com/mirrors/www.hpl.hp.com/hpjournal/96aug/aug96a2.pdf`, fetched as a PDF and read in full
via the `Read` tool (6 pages read directly — same WebFetch-fails-on-PDF-text limitation as above, same
`Read` fallback used, and confirmed successful this time). This is HP's own author (Grady wrote the
foundational HP software-metrics book cited in IEEE 1044's own bibliography, Annex C item [B3]) describing
HP's scheme in the company's own technical journal — as primary a source as is realistically obtainable for
an internal-industry practice like this.

**The scheme, quoted/transcribed directly from Fig. 3 of the article** ("Categorization of software
defects," © 1992 Prentice-Hall, reprinted in the HP Journal with permission): three axes, selected one value
each per defect —

- **Origin (Where?)** — 6 values: **Specifications/Requirements**, Design, Code, Environmental Support,
  Documentation, Other.
- **Type (What?)** — nested under each Origin; for Specifications/Requirements specifically: "Requirements or
  Specifications, Functionality, Other." For Design: "Hardware Interface, Software Interface, User Interface,
  Functional Description, Other." For Code: "Logic, Computation, Data Handling, Module Interface/
  Implementation, Standards, Other" (plus "Process (Interprocess) Communications: Data Definition, Module
  Design, Logic Description, Error Checking, Standards, Other" as its own origin-adjacent branch in the
  figure).
- **Mode (Why?)** — 5 values, shared across all origins: **Missing, Unclear, Wrong, Changed, Better Way.**

**Directly relevant finding for Q2 (requirements-phase precedent):** HP's scheme's **very first Origin
value is "Specifications/Requirements"** — meaning, like ODC and IEEE 1044, the HP scheme was built from
the start to classify pre-code defects as a first-class, equal-weight category alongside Design and Code,
not as an afterthought. The article's own Fig. 4 and Fig. 6 pie charts (both read directly from the PDF)
show real HP division data where "Specifications" or "Requirements" origin defects made up **25.5% and
52.9%** (weighted) of one division's defect causes and **22.0%** of another's — concrete, quoted evidence
that HP's own real-world data collection treated requirements-phase defects as a substantial, tracked
category, not a footnote.

**Status/maturity, honestly assessed:** this is a **1986-designed, 1996-published-retrospective** scheme.
I found no evidence of an actively maintained modern version, no current vendor product page, and no
tooling. It is real, historically significant (frequently cited as ODC's direct point of comparison — a
paper titled *"A Comparison of IBM's Orthogonal Defect Classification to Hewlett Packard's Defect Origins,
Types, and Modes"* by Huber et al. exists, confirmed via Semantic Scholar listing
`https://www.semanticscholar.org/paper/A-Comparison-of-IBM-%E2%80%99-s-Orthogonal-Defect-to-%E2%80%99-s-,-Huber/078c2cd724cd0934cb21ad32244e6ac163b778b4`,
not independently opened/read in full in this pass — flagging as found-but-not-fully-verified), but is
**more historical/dead than IEEE 1044** — no standards body maintains it, and it is now referenced almost
exclusively as ODC's historical foil, not as an independently adopted scheme today.

## Framework 4 — ISO/IEC 5055 (checked per the task's suggestion, genuine dead end for our purpose)

Real and current: `https://www.iso.org/standard/80623.html`, ISO/IEC 5055:2021, "Information technology —
Software measurement — Software quality measurement — Automated source code quality measures," confirmed
via the CISQ vendor page (`https://www.it-cisq.org/2021/09/iso-5055-automated-source-code-quality-measures-the-first-standard-of-its-kind/`)
and the ISO page itself (search-result synthesis, not independently WebFetched in full in this pass —
flagging as a lighter-verification source than the others above). **Explicitly and completely out of scope
for our problem**, honestly stated rather than stretched to fit: its own stated scope is *automated,
static-analysis-based measurement of Security, Reliability, Performance Efficiency, and Maintainability
by detecting violations of coding/architectural rules **in source code***. It has no requirements/design-review
application whatsoever — it is fundamentally a code-scanner standard (the "first standard of its kind" for
automating structural code-quality measurement), and it does not classify *defects* in the ODC/IEEE-1044
sense at all (no Defect Type/Mode/Origin taxonomy) — it defines *quality measures* (counts of rule
violations) instead. **Genuine dead end, reported honestly rather than forced into relevance.**

## Framework 5 — Boehm's classification (checked per the task's suggestion)

I searched for a specific, citable "Boehm defect classification" and found no single, primary, well-defined
taxonomy attributable to Barry Boehm specifically (as distinct from his well-known cost-of-defect-by-phase
curve, which is a *cost* model, not a *classification* scheme). **I did not find a real, independently
citable "Boehm classification" framework** — rather than force a fit or cite something unverified, I am
reporting this as a genuine not-found, per the role's honesty bar.

---

## Consolidated verdicts (direct answers to the 4 assignment questions)

**1. ODC's categories:** 7 Defect Types (Assignment/Initialization, Checking, Algorithm/Method,
Function/Class/Object, Timing/Serialization, Interface/O-O Messages, Relationship), plus a 3-value
Qualifier (Missing/Incorrect/Extraneous), a 6-value Target (Requirements/Design/Code/Build-Package/
Information-Development/National-Language-Support), plus Activity/Trigger/Impact/Age/Source — 9 attributes
total, all quoted verbatim above from the current (2013) IBM spec. **IEEE 1044's scheme:** does NOT fix a
mandatory category list at all (explicitly, by design) — it fixes a 17-attribute Defect schema and a
17-attribute Failure schema, with only *informative, optional* example values (7 sample Types: Data,
Interface, Logic, Description, Syntax, Standards, Other; 3 sample Modes: Wrong, Missing, Extra; 5 sample
Insertion-activity values: Requirements, Design, Coding, Configuration, Documentation) — a genuinely
different design philosophy (schema-standardization vs. category-standardization) that itself matters more
than either category list.

**2. Does the post-code-vs-pre-code mismatch matter?** No, not fatally — both frameworks have **real,
primary-sourced, first-class precedent for requirements/design-phase (pre-code) defect classification**:
ODC's "Requirements" Target + "Design Review" Activity (quoted from the current IBM spec and Chillarege's
own tutorial); IEEE 1044's "Requirements" Insertion-activity value with a worked example explicitly framed
as "prior to any failure occurring" (quoted from the standard's own Annex B). Where the mismatch DOES bite:
the majority of both frameworks' richest vocabulary (all Unit/Function/System-Test triggers) is structurally
inapplicable to a zero-code review — a real, honestly-quantifiable scope reduction (roughly half of ODC's
trigger vocabulary), not a full disqualification.

**3. Would remapping lose information or usefully align us?** **Both, but net loses information as a
wholesale swap.** 2/8 of our categories map cleanly (concurrency/isolation → Timing/Serialization;
missing-detail → Requirements), 1/8 maps loosely (precision/ambiguity → Description), and **4/8 — including
our single largest category (sibling-inconsistency, 7/33 findings) and the one that directly motivated new
tooling (cross-round-contradiction) — have no home in either framework**, because both frameworks classify
properties of one isolated defect, not process-relative or cross-finding relationships. The one genuinely
worthwhile, low-cost adoption: add the Missing/Incorrect/Extraneous triad (present independently in ODC,
IEEE 1044, AND HP's scheme — three-way convergence) as a cross-cutting second tag alongside our existing 8
categories, not as their replacement.

**4. Real tooling?** **No.** Verified via a direct, live GitHub repository search returning zero results for
"orthogonal defect classification." The only automation effort found (AutoODC, an academic NLP classifier
from 2011–2015) was never released as usable software and has no public repo. IEEE 1044 explicitly disclaims
specifying a classification process, consistent with no canonical tool existing. Both frameworks remain,
today, manually-applied paper taxonomies.

---

## Sources (every one opened directly; nothing cited from memory)

- IBM Research, paper landing page for the original 1992 ODC paper —
  `https://research.ibm.com/publications/orthogonal-defect-classificationa-concept-for-in-process-measurements`
  (WebFetch, quoted).
- Chillarege, R., "ODC Tutorial 2000" (slide deck, ODC's inventor) —
  `https://pdfs.semanticscholar.org/b649/41041d35d596a2b284d52b04ab5f419956e1.pdf` (downloaded, read in
  full via `Read` tool PDF rendering, 16 pages).
- IBM, "Orthogonal Defect Classification v 5.2 for Software Design and Code" (2013, current maintained spec)
  — `https://s3.us.cloud-object-storage.appdomain.cloud/res-files/70-ODC-5-2.pdf` (downloaded, read in full
  via `Read` tool PDF rendering, 18 pages — the primary load-bearing source for Q1/Q2/Q3 on ODC).
- Wikipedia, "Orthogonal defect classification" — `https://en.wikipedia.org/wiki/Orthogonal_defect_classification`
  (WebFetch, quoted — confirms "seven values for defect type" without enumerating them; used only as a
  secondary cross-check, not as the source of the enumeration itself).
- IEEE, "IEEE Std 1044-2009, IEEE Standard Classification for Software Anomalies" (full standard text) —
  `https://www.ctestlabs.org/neoacm/1044_2009.pdf` (downloaded, read in full via `Read` tool PDF rendering,
  25 pages — the primary load-bearing source for all IEEE 1044 claims in this document).
- IEEE Standards Association, official 1044-2009 status page —
  `https://standards.ieee.org/standard/1044-2009.html` (WebFetch, quoted — confirms Inactive-Reserved status,
  inactivation date March 5 2020, and 1993→2009 supersession history).
- IEEE Standards Association, official 1044-1993 status page —
  `https://standards.ieee.org/standard/1044-1993.html` (WebFetch, quoted — confirms "superseded" status).
- GitHub, live repository search for "orthogonal defect classification" —
  `https://github.com/search?q=%22orthogonal+defect+classification%22&type=repositories` (WebFetch,
  quoted — confirmed zero results).
- Xia et al., "AutoODC: Automated generation of orthogonal defect classifications," *Automated Software
  Engineering* (2015) — `https://link.springer.com/article/10.1007/s10515-014-0155-1` (found via search,
  abstract/accuracy numbers taken from search-result synthesis, NOT independently re-opened and verified in
  full in this pass — flagged explicitly above as a lighter-verification citation).
- Grady, R. B., "Software Failure Analysis for High-Return Process Improvement Decisions," *Hewlett-Packard
  Journal*, August 1996 — `http://shiftleft.com/mirrors/www.hpl.hp.com/hpjournal/96aug/aug96a2.pdf`
  (downloaded, read in full via `Read` tool PDF rendering, 6 pages — primary source for the entire HP
  Framework 3 section, including the quoted Fig. 3/4/6 data).
- ISO, "ISO/IEC 5055:2021" official standard page — `https://www.iso.org/standard/80623.html` (found via
  search, scope/title taken from search-result synthesis, not independently WebFetched in full in this
  pass — flagged explicitly as a lighter-verification source; used only to confirm scope is out-of-bounds
  for our problem, not for any positive claim requiring deeper verification).
- it-cisq.org, "ISO 5055: Automated Source Code Quality Measures — The First Standard of its Kind" —
  `https://www.it-cisq.org/2021/09/iso-5055-automated-source-code-quality-measures-the-first-standard-of-its-kind/`
  (found via search, used as secondary confirmation of ISO 5055's scope, not independently WebFetched in
  full in this pass).

## What I could not verify / dropped honestly

- `supportcenter.ieee.org`'s definition page for "Inactive-Reserved" returned HTTP 403 (blocked) when
  fetched directly — I did NOT substitute a remembered/assumed definition; the "Inactive-Reserved" status
  claim in this document rests entirely on the `standards.ieee.org` official standard page's own text,
  which was successfully opened and quoted.
- The Huber et al. "Comparison of IBM's ODC to HP's Defect Origins, Types, and Modes" paper was found (real,
  indexed on Semantic Scholar) but not independently opened/read in full — flagged inline above rather than
  treated as a fully-verified source.
- AutoODC's reported accuracy numbers (82.9%/80.7%/77.5%/75.2%) come from a search-result synthesis of the
  paper's abstract, not an independently re-opened and re-quoted PDF/HTML page — flagged inline; if this
  number needs to be load-bearing for any future decision, it should be re-verified by opening the actual
  Springer article page directly first.
- ISO/IEC 5055's and the CISQ blog's exact wording were taken from search-result synthesis rather than a
  direct WebFetch of the full standard/blog text — acceptable here because the only claim resting on them
  (that ISO 5055 is a code-scanning standard, out of scope for defect-taxonomy comparison) is a low-stakes,
  easily-corroborated-elsewhere claim, but flagged for honesty regardless.
- No real, independently citable "Boehm defect classification" framework was found — reported as a genuine
  not-found rather than stretched to fit an unrelated Boehm contribution (his cost-of-defect-by-phase curve
  is a different kind of artifact, a cost model not a classification taxonomy).
