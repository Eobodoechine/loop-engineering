# Compiler-gate / drift-validator external research (2026-07-08)

## Why this was researched

Follow-up to `research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md`. That doc
converged on two arXiv IDs (2606.27045, 2601.19106) and named terms ("Intent Graph",
"Evidence Graph", "Drift Validator") as if quoting the papers directly, under session
rate-limit pressure that broke the original adversarial-voting pipeline before synthesis
completed. Nnamdi asked for a harder pass: actually open both papers and confirm the
terms/numbers are real (not paraphrase drift), then go find real, existing, inspectable
repos/tools that already do "compiler feedback inside an LLM code loop" or "spec-vs-code
drift checking," so the team has real material — not vibes — to design a gate from.

**Scope discipline (per dispatch):** this file is external material only. It makes NO
recommendation about how/whether to wire anything into `orchestrator.md` — that is a
separate internal-grounding task running in parallel.

## Method / honesty notes

Every source below was actually opened via `WebFetch` or GitHub's REST API via `gh api`
(not just a search snippet) before being cited. Where a claim could only be corroborated
via a `WebSearch` snippet and I could not independently open the primary source to confirm
it, it is marked **(search-snippet only, not independently opened)** below — per the
Researcher role's honesty bar, that is a lead, not a confirmed fact. `gh api` was used for
GitHub maturity signals (stars, `archived` flag, `pushed_at`, license SPDX ID) because it
returns ground-truth JSON, not a WebFetch summary — this caught one real discrepancy (see
AlphaCodium staleness below) that a README-only read would have missed.

---

## 1. The two arXiv papers — confirmed to exist, terms checked against full text

### arXiv:2606.27045 — "The Spec Growth Engine: Spec-Anchored, Code-Coupled,
Drift-Enforced Architecture for AI-Assisted Software Development"

- **Confirmed real.** Fetched `arxiv.org/abs/2606.27045`, `arxiv.org/pdf/2606.27045`, and
  `arxiv.org/html/2606.27045`.
- **Author:** Hartwig Grabowski, a professor at Hochschule Offenburg (Germany) —
  confirmed via WebSearch hits for his faculty page (`hs-offenburg.de`) and dblp listing.
  **Single author.** Submitted cs.SE, June 25 2026.
- **Abstract (verbatim):** "AI coding agents dramatically accelerate implementation speed
  but introduce two structural failure modes that existing spec-driven approaches do not
  fully solve: (1) context explosion... and (2) silent spec-code drift... We present the
  Spec Growth Engine, a lightweight framework that addresses both failure modes through a
  machine-readable spec graph whose nodes carry explicit contract/design separation, a
  Spine context assembler that scopes agent context to an ownership path, a vertical-slice
  growth protocol that enforces hardest-first ordering, and a drift gate that makes
  spec-code divergence a blocking merge condition."
- **"Spec-anchored, code-coupled" is a real, direct quote** from the paper (it's in the
  title itself).
- **"Intent Graph", "Evidence Graph", and "Drift Validator" ARE the paper's real terms —
  but they do NOT appear in the abstract.** A first abstract-only fetch reported these
  terms absent, which would have wrongly flagged the earlier research doc as having
  drifted from the source. Fetching the **full HTML text (Section 5.4)** found them
  verbatim:
  > "Drift validation compares two derived graphs: **Intent Graph** — Specs: contracts,
  > invariants, acceptance criteria. **Evidence Graph** — Code: imports/exports,
  > routes/events, tests." (Figure 5 caption, Section 5.4, "Drift Validation: Intent Graph
  > vs. Evidence Graph")
  > "The engine consists of five interlocking components: the *Spec Graph*, the *Context
  > Assembler*, the *Drift Validator*, the *Governance Gates*, and the *Capability
  > Registry*." (Section 5)
  **Lesson for future verification of this kind of claim: check the full text, not just
  the abstract — a term can be 100% real and still be invisible to an abstract-only
  fetch.**
- **The mechanics, quoted exactly** (Section 5.4): Hard errors that **block merge
  unconditionally**: "Orphan code (a source file with no spec owner)"; "Undeclared
  dependency (code imports across a spec boundary without a declared edge)"; "Dependency
  bypasses contract (code imports internal files of another node)"; "Missing dependency
  contract (a target node has no contract)." Soft warnings that do NOT block: "Declared
  dependency with no code evidence"; "Public export not mentioned in the contract";
  "Contract behaviour without test evidence." The paper's own framing: "This transforms
  drift from a social/process problem into a structural impossibility."
- **"Spec-first" / "spec-as-source" definitions, quoted exactly** (Section 1 and Section
  8, citing "Böckeler's maturity axis"): **Spec-first**: "specs guide an initial
  generation, then are discarded" (cites AWS Kiro, Tessl). **Spec-anchored**: "specs are
  living artefacts kept in sync with code." **Spec-as-source**: "specs are the single
  source of truth from which code is generated" (cites MDA, "some model-driven IDEs").
  This matches the earlier doc's framing closely, with one nuance: the Introduction
  additionally frames spec-first as costing "upfront overhead and the risk of specifying
  the wrong thing," which the earlier doc didn't carry.
- **CRITICAL MATURITY FLAG — this is a design paper, not a working tool.** Direct
  full-text fetch, asked explicitly about implementation/evaluation status: **"The Spec
  Growth Engine is maintained as an internal design-document set; a public release is
  planned, and the documents are available from the author on request."** There is **no
  GitHub repo, no prototype, no empirical evaluation section** — the paper works through
  one hypothetical e-commerce example (Section 7) and compares itself to Kiro/spec-kit/Tessl
  only conceptually, not experimentally. **Triage: RESEARCH-ONLY.** It is the best
  *framing* found (the architecture and the two-graph vocabulary are genuinely useful to
  borrow as a mental model / spec), but there is no code to copy and zero benchmark
  evidence it works in practice — treat the whole paper as a naming/architecture
  reference, not adoption-ready prior art.

### arXiv:2601.19106 — "Detecting and Correcting Hallucinations in LLM-Generated Code via
Deterministic AST Analysis"

- **Confirmed real.** Fetched `arxiv.org/abs/2601.19106` and `arxiv.org/html/2601.19106`.
- **Authors:** Dipin Khati, Daniel Rodriguez-Cardenas, Paul Pantzer, Denys Poshyvanyk — all
  William & Mary (SEMERU Lab). Denys Poshyvanyk is an established, widely-published
  software-engineering/mining-software-repositories researcher, which is a real
  credibility signal (this is not an anonymous or single-hobbyist artifact).
- **Abstract (verbatim):** "Large Language Models (LLMs) for code generation boost
  productivity but frequently introduce Knowledge Conflicting Hallucinations (KCHs),
  subtle, semantic errors, such as non-existent API parameters, that evade linters and
  cause runtime failures... We propose a post-processing framework that parses generated
  code into an Abstract Syntax Tree (AST) and validates it against a dynamically-generated
  Knowledge Base (KB) built via library introspection. This non-executing approach uses
  deterministic rules to find and fix both API and identifier-level conflicts. On a
  manually-curated dataset of 200 Python snippets, our framework detected KCHs with **100%
  precision and 87.6% recall (0.934 F1-score)**, and successfully auto-corrected **77.0%**
  of all identified hallucinations."
- **Confirms the earlier doc's headline numbers exactly**: 100% precision / 87.6% recall /
  0.934 F1 on 200 samples, 77.0% overall auto-correction.
- **Important correction/nuance the earlier doc did NOT have** — the per-category
  breakdown (Table 3 of the paper), fetched directly, is much more informative than the
  aggregate number and matters for our design:
  | KCH category | Detection rate | Correction/fix accuracy |
  |---|---|---|
  | Missing imports | 97.9% | 97.9% |
  | Mis-typed API calls (e.g. `pd.read_exel`) | 84.5% | 70.0% |
  | **Contextual mismatches** (e.g. using `pd.read_excel` to load a `.csv`) | **33.3%** | **0.0%** |
  **This is the load-bearing caveat**: the earlier doc's "97.9%" figure is real, but it is
  the *missing-imports-specific* number, not a general figure — and the framework is
  essentially blind to *semantically*-wrong-but-syntactically-valid API misuse
  (contextual mismatches), which a plain `tsc`/typechecker also would not catch (those are
  "correct types, wrong behavior" bugs, not binding bugs). The 100%/87.6% aggregate is
  driven almost entirely by the missing-import and mis-typed-API categories, which are
  exactly the padsplit-cockpit Slice 6b bug class (unbound/never-imported identifiers) —
  so the number is real and it is directly on-target for our specific pain, but it should
  not be oversold as "catches most LLM code bugs" — it catches *binding* bugs, not
  *logic* bugs.
- **Real, open artifact exists** — the paper states: "All data, code, and experimental
  configurations are publicly available in our replication package," citing "SEMERU Lab.
  2025. Hallucinations-in-code. https://github.com/WM-SEMERU/Hallucinations-in-Code".
  Confirmed via `gh api repos/WM-SEMERU/Hallucinations-in-Code`: **exists, not archived,
  2 stars, no license set (default all-rights-reserved), last pushed 2026-01-26.** This is
  a genuine research-code artifact (the actual detector used to produce the paper's
  numbers) but it is thin (2 stars, no license, unmaintained-feeling) — worth reading for
  the AST/KB detection *method*, but not something to `pip install` and depend on; treat
  it as a reference implementation of the *idea* (introspect the library's real API
  surface into a KB, diff generated code's AST against it), not production tooling.
  **Triage: TESTABLE / reference-only.**

**Bottom line for task 1:** both IDs resolve to the papers we thought, the specific
numbers hold up on direct fetch, and "Intent Graph"/"Evidence Graph"/"Drift Validator" are
genuine paper terminology (Section 5.4 of 2606.27045) — but 2606.27045 itself is an
unimplemented, unbenchmarked, single-author design proposal, and 2601.19106's headline
number is real but category-specific (binding bugs only, not semantic-mismatch bugs).

---

## 2. Real, inspected tools/repos — what already does this

Every entry below was independently opened (README via WebFetch, maturity via `gh api`).

### COPY THIS — directly reusable, mechanically does the thing we need

**knip** (`github.com/webpro-nl/knip`, née `webpro/knip`) — TS/JS dead-code and
dead-import detector. **11,692 stars, ISC license, actively maintained (last push
2026-07-07, the day before this research).** Fetched `knip.dev/reference/issue-types`
directly: it has an issue-type literally called **`unresolved`**, described as **"Unable
to resolve this (import) specifier"** — this is a mechanical, off-the-shelf detector for
exactly the "referenced identifier never actually bound" bug class that burned ~9 of
padsplit-cockpit Slice 6b's ~30 plan-check rounds. It also separately flags `unlisted`
("used dependencies not listed in package.json"), unused exports, and unused files.
*Transfer condition:* requires a real TS/JS repo with resolvable module graph (works on
real files, not prose/spec text) — this only helps once stub/real files exist, matching
exactly the point in the Slice 6b loop where prose review was still running long after
real files could have existed. Guarantee is **structural**: knip either resolves the
import or it doesn't; there's no LLM judgment step to fail silently.

**aider's auto-lint / auto-test loop** (`github.com/Aider-AI/aider`) — **47,165 stars,
Apache-2.0, actively maintained.** This is the single most concrete, already-running
implementation of "compiler/lint feedback inside an LLM edit loop" found in this pass.
Pulled the **actual source**, `aider/coders/base_coder.py`:
- `max_reflections = 3` (line 101) — aider will self-repair from lint/test failures **at
  most 3 times** per turn before giving up: `"Only {self.max_reflections} reflections
  allowed, stopping."` (line 940).
- `auto_lint = True` by default (line 105); after an edit, `lint_edited()` runs the
  linter, and if it finds errors: `self.reflected_message = lint_errors; return` (lines
  1599-1607) — the lint output is fed back into the next LLM turn as the "reflected
  message," i.e. exactly a compiler-feedback loop, with a **hard round cap**, not
  open-ended retry.
- `auto_test` / `--test-cmd` is opt-in (default `False`) and works the same way: "Aider
  will try and fix any errors if the command returns a non-zero exit code" (per
  `aider.chat/docs/usage/lint-test.html`).
*Transfer condition:* this is a single-agent, single-repo CLI loop, not a multi-role
plan-check pipeline — the directly transferable piece is the **pattern** (bounded
reflection count + machine-checkable pass/fail signal fed back verbatim), not the code
itself. The guarantee is structural (exit code is unambiguous), and the round cap is a
real, load-bearing design choice worth matching — 3, not unbounded.

### ADAPT THIS — real, working, would need glue code

**dependency-cruiser** (`github.com/sverweij/dependency-cruiser`) — **6,874 stars, MIT,
actively maintained (last push 2026-07-07).** README confirms: circular-dependency
detection, "orphan" module detection (**different sense than the Grabowski paper** — here
"orphan" = a module with no dependencies at all, not "a file with no spec owner" — flagging
this so the terms aren't conflated), and custom **forbidden-dependency rules** that can
enforce "module A may not import from module B" boundaries — e.g. its own example, "don't
allow dependencies from outside the test folder to test." This is the closest *existing,
runnable* tool to the Drift Validator's "Undeclared dependency" / "Dependency bypasses
contract" hard-error rules — it just needs a config file mapping our own
node/boundary/contract structure onto its rule DSL; it does not know about "spec
ownership" out of the box, that mapping is on us.

**TypeChat** (`github.com/microsoft/TypeChat`) — **8,675 stars, MIT, actively maintained
(last commit 2026-07-07** — confirmed via `gh api`, correcting an initial worry that this
might be a deprecated Microsoft research toy; it is not). Pulled the **actual source**,
`typescript/src/typechat.ts`: the validate-then-repair loop is real and is exactly
**one repair attempt**, not open-ended:
```
async function translate(request, promptPreamble) {
  ...
  let attemptRepair = typeChat.attemptRepair;   // default true
  while (true) {
    const response = await model.complete(prompt);
    ...
    if (validation.success) return validation;
    if (!attemptRepair) return error(`JSON validation failed: ${validation.message}...`);
    prompt.push({ role: "assistant", content: responseText });
    prompt.push({ role: "user", content: typeChat.createRepairPrompt(validation.message) });
    attemptRepair = false;   // only one repair attempt is ever made
  }
}
```
The repair prompt template itself, also pulled verbatim: `"The JSON object is invalid for
the following reason:\n"""\n${validationError}\n"""\nThe following is a revised JSON
object:\n"`. *Transfer condition:* this pattern (schema-validate the LLM's structured
output, and on failure, feed the validator's own error message back verbatim as the next
turn's prompt, capped at one retry) is a clean, minimal template for any "generate,
mechanically validate, feed the failure back once" step — directly relevant to how a
Drift-Validator-style gate would hand its failure output back to a Coder agent. The
guarantee here is structural (schema validation is deterministic), and the one-shot cap is
a deliberate, load-bearing design choice (not unlimited retry).

**ast-grep** (`github.com/ast-grep/ast-grep`, 14,973 stars, MIT, active) and **Semgrep**
(`github.com/semgrep/semgrep`, 15,804 stars, LGPL-2.1, active, latest release June 24
2026) — both are real, mature, structural (AST-based, not regex-based) rule engines
supporting custom YAML rules across many languages. Neither ships an "unbound identifier"
rule out of the box the way knip does for JS/TS, but both are viable engines to *write*
a custom structural rule for other languages (e.g. Python) where knip doesn't apply.
Semgrep's LGPL-2.1 license is a real (if mild) adoption-risk flag depending on how it
would be distributed/embedded; ast-grep is plain MIT.

**madge** (`github.com/pahen/madge`, 10,125 stars, MIT) — module dependency graph
visualizer, circular-dependency and orphan-module detection for JS/TS/Sass/Less. Real and
usable, but **maturity flag: last push 2026-01-21**, ~5.5 months stale relative to this
research date — still within a reasonable window, not abandoned, but noticeably less
active than knip/dependency-cruiser/aider, which all pushed within the last 24-48 hours of
this research. Lower priority than dependency-cruiser for the same job.

### PRIOR ART — real and instructive, not directly reusable for THIS bug class

**SWE-agent** (`github.com/SWE-agent/SWE-agent`, 19,727 stars, MIT, active, "SWE-agent
1.0 + Claude 3.7 is SoTA on SWE-Bench full" per its own README) and **OpenHands**
(`github.com/All-Hands-AI/OpenHands`, 79,905 stars, core is MIT — `enterprise/` subdir has
a separate license — very active, v1.9.2 released 2026-07-07) are both large, mature,
general-purpose coding-agent harnesses. Neither README (fetched directly) makes an
explicit, quotable claim of "we run a compiler/typechecker and feed diagnostics back as a
structural gate" — the closest is SWE-agent's general "agent-computer interface" framing
and the implicit fact that both let the agent run arbitrary shell commands (so a
compiler/lint run is *possible* inside their loops, just not a named, first-class,
blocking feature the way aider's is). These are relevant as *harness* prior art (how a
tool-using coding agent loop is structured generally) but not as a drift-validator/gate
implementation specifically.

**AlphaCodium** (`github.com/Codium-ai/AlphaCodium`, 3,946 stars, AGPL-3.0). Confirmed
via its own arXiv abstract (2401.08500, fetched directly): "GPT-4 accuracy (pass@5)
increased from 19% with a single well-designed direct prompt to 44% with the AlphaCodium
flow" on the CodeContests validation set — this number is real and matches the repo's own
claim. **Maturity flag, caught only by `gh api` (a README read would have missed this):
last pushed 2026-01-25, but the actual last commit on the default branch is dated
2024-11-25** — over 19 months stale as of this research. This is "flow engineering"
(iterative AI-generated-test-based self-repair), a real and well-cited technique, but the
repo itself looks effectively frozen (superseded by Qodo's commercial product) — treat the
*technique* as prior art, not the repo as something to depend on. AGPL-3.0 is also a
real license consideration if any code were ever vendored in.

**Academic compiler-feedback lineage** (all fetched directly at `arxiv.org/abs/<id>`,
numbers quoted verbatim from each abstract):
- **CompCoder / "Compilable Neural Code Generation with Compiler Feedback"**
  (arXiv:2203.05132, ACL Findings 2022): "improving the success rate of compilation from
  44.18 to 89.18" in code completion and "from 70.3 to 96.2" in text-to-code generation,
  vs. CodeGPT.
- **Self-Edit / "Fault-Aware Code Editor for Code Generation"** (arXiv:2305.04087, ACL
  2023): "improve the average of pass@1 by 89% on APPS-dev, 31% on APPS-test, and 48% on
  HumanEval over nine popular code generation LLMs" — using *execution* results (not
  compiler diagnostics) wrapped as comments fed back to a fault-aware editor.
- **CodeT / "Code Generation with Generated Tests"** (arXiv:2207.10397): "CodeT improves
  the pass@1 metric on HumanEval to 65.8%, which represents an absolute improvement of
  18.8% over the code-davinci-002 model" — selects among generated samples via dual
  execution agreement against LLM-generated tests, not a compiler signal per se.
- **Reflexion / "Language Agents with Verbal Reinforcement Learning"** (arXiv:2303.11366,
  NeurIPS 2023): "Reflexion achieves a 91% pass@1 accuracy on the HumanEval coding
  benchmark, surpassing the previous state-of-the-art GPT-4 that achieves 80%" — general
  verbal-feedback-into-episodic-memory pattern, of which execution/test feedback is one
  instantiation.
- **RLCF / "Coarse-Tuning Models of Code with Reinforcement Learning Feedback"**
  (arXiv:2305.18341) — confirmed real and on-topic (uses a compiler-derived "grounding
  function" plus an LLM-comparison signal, evaluated on MBJP/MathQA-X for Java, claims
  parity with 2-8x larger models), **but I could not extract the exact numeric table**
  (the PDF fetch returned binary/garbled content and the abstract page itself didn't
  surface the number) — the qualitative claim is confirmed from the abstract, the precise
  percentage improvement is **not independently verified in this pass**, flagged
  honestly rather than guessed.
- **StepCoder** (arXiv:2402.01391) — confirmed real, abstract fetched directly, describes
  splitting long-sequence code generation into a curriculum of subtasks plus fine-grained
  optimization that masks unexecuted code segments when applying compiler-feedback RL —
  but the abstract itself reports **no specific numeric results** ("outperforms
  state-of-the-art approaches in corresponding benchmarks" is as precise as the abstract
  gets); not citing a specific number here rather than inventing one.

None of these six papers is runnable, adoptable tooling for our loop — they are RL-training
techniques (fine-tuning a base model), not inference-time agent-harness features. They are
useful as evidence that "feed the compiler/execution signal back into the loop" is a
well-established, repeatedly-validated idea across a decade of separate research groups —
which strengthens confidence in the *category* of fix (compiler-in-the-loop), even though
none of them is something to literally install.

### NEGATIVE FINDINGS — explicitly checked and found NOT to already do this

**GitHub spec-kit** (`github.com/github/spec-kit`, **118,645 stars**, MIT, extremely
active, v0.12.7 released 2026-07-07). Its own README, fetched directly, describes a
seven-step workflow (Constitution → Specification → Clarification → Planning → Task
Breakdown → Analysis → Implementation) and a `/speckit.converge` command described as
assessing "the codebase against spec/plan/tasks and append remaining work as new tasks."
**This is AI-assisted analysis, not a mechanical/blocking gate** — the agent reviews and
writes new tasks; there is no compiler/typecheck step and nothing blocks a merge. This is
useful as a *negative* confirmation: even the most popular (by far) spec-driven-dev
toolkit on GitHub has not built the Drift-Validator-style hard gate the Grabowski paper
proposes — that idea is still a genuine gap in existing tooling, not something already
solved and merely unadopted by us.

**AWS Kiro "Spec Validator."** A WebSearch snippet (from a third-party blog, not
`kiro.dev` itself) claimed: "Specs don't just live in a document... Spec Validator:
Continuously checks your code against your specs and highlights divergences." **This did
NOT hold up under direct verification** — fetching `kiro.dev/docs/specs/` itself and
asking explicitly whether a "Spec Validator" feature exists returned: "Kiro does not
appear to have a feature called 'Spec Validator'... The documentation does not reference
any feature matching the 'Spec Validator' name or function you described." **Flagging this
explicitly per the honesty bar: treat the third-party blog's "Spec Validator" claim as
unverified/likely marketing overstatement, not confirmed fact.** This also means the
earlier research doc's characterization of Kiro as classic "spec-first" (spec drives
generation, then is effectively discarded/not mechanically re-checked) is the
better-supported reading, consistent with the Grabowski paper's own categorization of Kiro.

---

## 3. Google developer-docs style guide + Metanorma — cross-reference convention, re-verified

**Google developer documentation style guide**, fetched directly (two pages, since the
convention is split across them):
- `developers.google.com/style/word-list`, exact entries: **"above"** — "Don't use to
  refer to a position in a document. Instead, use *earlier* or *preceding*." **"below"**
  — "Don't use to refer to a position in a document. Instead, use *later* or *following*."
- `developers.google.com/style/cross-references`: "Link to the most relevant page and
  heading." Under "Write descriptive link text": example given is "For more information,
  see the [Write descriptive link text](#descriptive-link-text) section of this
  document" — i.e., link directly to the actual heading (which in HTML is an anchor ID),
  not a spatial description of where it sits on the page.

**Nuance/correction versus the earlier doc's paraphrase:** Google's own word-list entries
do NOT simply say "use an anchor ID instead" — they say don't use spatial words
("above"/"below," which break under reflow/translation/screen-reader use), and if you
must use a word, prefer **order-based** language ("earlier," "preceding," "later,"
"following") over **position-based** language. The *separate* recommendation to link to
the actual heading/anchor comes from the cross-references page, not the word-list page.
Combined, the two pages do support the earlier doc's conclusion (stable, named references
beat "as shown above"), but it's two distinct pieces of guidance stacked together, not one
unified directive — worth being precise about if this is cited again.

**Metanorma**, re-fetched at `metanorma.org/author/topics/document-format/xrefs/`, exact
quote: "The label of the item cross-referenced, the use of brackets, and the containing
reference are all taken care of by Metanorma; the document author needs only give the item
identifier in the AsciiDoc source (e.g. `<<formulaB-1>>` generates either 'Formula (B.1)'
or 'B.6, Formula (B.1)', depending on where in the document it occurs.)" **Nuance:**
Metanorma's actual mechanism is that the author writes a stable identifier
(`formulaB-1`) and Metanorma computes and inserts the correct **numbered label** wherever
it's cited — it is not literally "generates the words above/below," it's "the author
never needs relative language at all because the system computes a correct absolute
label from the anchor, everywhere the anchor is referenced." That is the same underlying
principle (anchor beats relative position) but the earlier doc's phrasing ("generates
cross-reference label text automatically... rather than hardcoding above/below") slightly
overstated the literal mechanism — corrected here.

**Confirmed: both sources independently support "stable anchored IDs over relative
position language" as an established documentation convention**, with the precise
mechanism now quoted directly from both primary sources rather than paraphrased.

---

## Ranked ledger

| Item | Verdict | Why |
|---|---|---|
| knip `unresolved` issue type | **COPY THIS** | Off-the-shelf, mechanical, exactly the bug class; MIT-adjacent (ISC), very active |
| aider `max_reflections=3` + auto-lint loop | **COPY THIS (pattern)** | Real running code, bounded-retry compiler-feedback loop, source quoted line-and-verse |
| TypeChat validate→repair (1 attempt) | **COPY THIS (pattern)** | Real running code, minimal clean template for gate-failure-to-agent handoff |
| dependency-cruiser boundary/orphan rules | **ADAPT THIS** | Real, active, MIT; needs our own boundary config to mimic Drift Validator's hard errors |
| ast-grep / Semgrep | **ADAPT THIS** | Structural rule engines for languages knip doesn't cover |
| madge | **ADAPT THIS (lower priority)** | Works, but less active than dependency-cruiser for the same job |
| arXiv:2601.19106 (KCH/AST detector) + its repo | **PRIOR ART / reference method, not production tool** | Real numbers hold up, but repo is 2-star research code, no license; category breakdown shows it's binding-bugs-only, not logic-bugs |
| arXiv:2606.27045 (Spec Growth Engine) | **RESEARCH-ONLY** | Real paper, real terms confirmed in Section 5.4, but zero implementation, zero empirical evaluation, single author, "available on request" |
| SWE-agent / OpenHands | **PRIOR ART (harness-level only)** | Mature, real, huge adoption — but no explicit compiler-gate feature to borrow specifically |
| AlphaCodium | **PRIOR ART, technique only** | Real, cited number confirmed — but repo effectively frozen since Nov 2024 (AGPL-3.0) |
| CompCoder / Self-Edit / CodeT / Reflexion / RLCF / StepCoder | **PRIOR ART, not reusable tooling** | Real, numbers mostly confirmed (RLCF/StepCoder partially), but these are training-time RL techniques, not inference-time harness features |
| GitHub spec-kit `/speckit.converge` | **NEGATIVE FINDING** | Most popular spec-driven toolkit (118k stars) still has no mechanical drift gate — confirms the gap is real, not already solved |
| AWS Kiro "Spec Validator" | **NEGATIVE FINDING / unverified claim** | Third-party blog claim did not survive direct docs check |

## Full source list (everything actually opened this pass)

- https://arxiv.org/abs/2606.27045 , https://arxiv.org/pdf/2606.27045 , https://arxiv.org/html/2606.27045
- https://arxiv.org/abs/2601.19106 , https://arxiv.org/html/2601.19106
- https://github.com/WM-SEMERU/Hallucinations-in-Code (via `gh api`)
- https://github.com/Aider-AI/aider (README + `aider/coders/base_coder.py` source + `gh api`)
- https://aider.chat/docs/usage/lint-test.html
- https://github.com/All-Hands-AI/OpenHands (README + LICENSE + `gh api`)
- https://github.com/SWE-agent/SWE-agent (README + `gh api`)
- https://github.com/Codium-ai/AlphaCodium (README + `gh api`) and https://arxiv.org/abs/2401.08500
- https://github.com/webpro-nl/knip (`gh api`) and https://knip.dev/reference/issue-types
- https://github.com/sverweij/dependency-cruiser (README + `gh api`)
- https://github.com/pahen/madge (README + `gh api`)
- https://github.com/microsoft/TypeChat (README + `typescript/src/typechat.ts` source + `gh api`)
- https://github.com/ast-grep/ast-grep (README + `gh api`)
- https://github.com/semgrep/semgrep (README + `gh api`)
- https://github.com/dsherret/ts-morph (`gh api`, maturity signal only)
- https://github.com/github/spec-kit (README + `gh api`)
- https://kiro.dev/docs/specs/
- https://arxiv.org/abs/2203.05132 (CompCoder)
- https://arxiv.org/abs/2305.04087 (Self-Edit)
- https://arxiv.org/abs/2207.10397 (CodeT)
- https://arxiv.org/abs/2303.11366 (Reflexion)
- https://arxiv.org/abs/2305.18341 and https://arxiv.org/pdf/2305.18341 (RLCF — abstract confirmed, exact numeric table not extracted, flagged)
- https://arxiv.org/abs/2402.01391 (StepCoder)
- https://developers.google.com/style/word-list
- https://developers.google.com/style/cross-references
- https://www.metanorma.org/author/topics/document-format/xrefs/
- WebSearch used only as a lead-generator for arXiv IDs (RLCF, CompCoder, Self-Edit, CodeT,
  Reflexion, StepCoder, Hartwig Grabowski's affiliation) — every lead was then opened
  directly before being cited above.

## What I could not verify / gaps

- RLCF's (arXiv:2305.18341) exact percentage-point improvement table on MBJP/MathQA-X —
  PDF fetch returned unreadable binary content; the qualitative claim (compiler-grounded
  RL improves compile/pass rate, matches 2-8x larger models) is confirmed from the
  abstract, the precise numbers are not.
- StepCoder's (arXiv:2402.01391) benchmark numbers — abstract itself doesn't state them
  ("outperforms state-of-the-art... in corresponding benchmarks" is the full precision
  available without pulling the PDF body, which I did not do given the RLCF PDF-fetch
  failure above suggested low yield for the extra round-trip).
- No repo/tool found in this pass that implements the *full* Intent-Graph-vs-Evidence-Graph
  two-graph comparison as a single, adoptable, off-the-shelf product — the closest
  approximations (knip + dependency-cruiser combined) each cover part of it (binding
  resolution; boundary/import rules) but neither derives an "Intent Graph" from prose specs
  the way the Grabowski paper proposes. That specific synthesis appears to not exist yet
  as real, runnable code anywhere I could find and open.
