# Spec-first prose review vs. compiler-in-the-loop for AI-agent builds (2026-07-08)

## Why this was researched

padsplit-cockpit's Slice 6b (Airbnb iCal calendar sync) went 30+ rounds of a
plan-check loop (spec.md written by an LLM, reviewed by 5 parallel adversarial
"lens" agents per round, fixes applied between rounds) without full convergence.
Nnamdi asked directly why so many rounds were needed and whether the methodology
itself needed to change, and asked for deep research on alternatives.

Concrete pattern that triggered the question: ~9 of the ~30 rounds' findings were
the identical "identifier referenced but never imported/exported/bound" bug class
— something a `tsc --noEmit` run would have caught instantly and exhaustively — and
1 finding was a test-oracle bug (AC19 checked the wrong org's table, so it would
pass green even against a fully broken security check) that survived 10 rounds of
manual "re-walk the scenario" review.

## Method

Deep-research workflow: 6 search angles, 27 sources fetched, 126 candidate claims
extracted, 25 adversarially voted (3-vote consensus, need 2/3 refute to kill). The
run hit Anthropic's session rate limit partway through verification and the final
synthesis step failed outright — 7 claims survived adversarial voting with 2-1 or
3-0 confirm votes; 9 were refuted; 9 errored (rate-limited, not falsified — still
directionally credible since several triangulate onto already-confirmed sources).
This document is a manual synthesis of the raw claims, done because the workflow's
own synthesis step didn't complete.

## Confirmed claims (2/3+ adversarial vote)

1. **Mechanical detection of hallucinated/unbound identifiers works, and works
   well.** A deterministic, non-executing AST-analysis framework detected exactly
   this bug class (invented APIs, missing imports, misused identifiers) in
   LLM-generated code with 100% precision (zero false positives on 39 clean
   samples) and 87.6% recall (93.4% F1) across a 200-sample benchmark; a related,
   unverified-but-corroborating claim from the same paper put missing-import
   detection specifically at 97.9%. [arXiv:2601.19106](https://arxiv.org/pdf/2601.19106)

2. **Relative cross-references ("see above/below") are a known, named
   documentation anti-pattern**, not something specific to this project. Stable,
   author-assigned anchor IDs (not position language) are the established fix —
   Metanorma generates cross-reference label text automatically from anchor IDs
   rather than hardcoding "above"/"below". [metanorma.org](https://www.metanorma.org/author/topics/document-format/xrefs/)
   Google's developer-docs style guide independently makes the same
   recommendation (cite the actual section/heading name, not relative position) —
   this claim didn't survive the adversarial vote due to a rate-limit error, not a
   refutation, and is corroborated by the Metanorma finding.

3. **Test-oracle quality needs a mechanical check, not more re-reading.**
   AdverTest (adversarial LLM test-generation research) uses two agents — a test
   generator and a mutant generator — in a bidirectional loop where **mutation
   score**, an executable/behavioral signal, is what validates whether generated
   tests actually detect faults, not manual/prose review of the test's logic.
   [arXiv:2602.08146](https://arxiv.org/pdf/2602.08146)

4. **High coverage (or, by extension, repeated scenario re-derivation) does not
   establish oracle correctness.** It's an established finding that coverage
   measures whether code executed, not whether the test's assertions actually
   distinguish correct from incorrect behavior — directly explains why AC19
   survived 10 rounds of "walk the scenario again" review: walking the scenario
   is a coverage-like act, it doesn't verify the check itself is well-formed.
   [arXiv:2602.08146](https://arxiv.org/pdf/2602.08146)

5. **Independent, structurally-different oracles are the literature's answer to
   "who checks the checker."** Retromorphic Testing proposes a mathematically
   independent round-trip relation (f⁻¹(f(x)) = x via a separate forward/backward
   program pair) instead of a hand-written expected output, specifically so the
   check is derived a different way than the original implementation.
   [arXiv:2310.06433](https://arxiv.org/pdf/2310.06433) Differential testing
   achieves the same independence by cross-comparing multiple independently
   implemented equivalent programs rather than trusting one hand-specified
   "correct answer." [ACM DL:3563835.3567662](https://dl.acm.org/doi/10.1145/3563835.3567662)

6. **The exact architecture this project should move toward already has a name
   and a working implementation.** The "Spec Growth Engine"'s Drift Validator
   derives an "Intent Graph" from spec files and an "Evidence Graph" from static
   analysis of actual code (imports/exports/routes/tests), and treats certain
   mismatches — orphan code, undeclared cross-boundary imports — as **hard errors
   that block merge unconditionally**, not something a human/LLM reviewer is
   trusted to catch by reading. [arXiv:2606.27045](https://arxiv.org/pdf/2606.27045)

## The central framing (from the same source as #6, claim itself rate-limited but
matches the confirmed Drift-Validator finding exactly)

The paper explicitly names two failure extremes in AI-driven spec-to-code
workflows:
- **"spec-first"** — the spec drives code generation and is then discarded (e.g.
  AWS Kiro-style flows). Nothing keeps the spec and code in sync after generation.
- **"spec-as-source"** — code is continuously generated FROM the spec (e.g.
  Tessl/MDA-style flows), which reintroduces nondeterminism every regeneration.

It proposes a third position: **"spec-anchored, code-coupled"** — code remains
primary and authoritative; the spec is a *verified contract*, and alignment is
enforced by an automated, blocking gate (the Drift Validator), not by reviewer
discipline or repeated prose review.

**padsplit-cockpit's Slice 6b plan-check loop was, in effect, running a pure
"spec-first" process for far longer than the interface/schema-level design
questions actually needed** — the entire feature (three files' worth of
imports, exports, JSX, and directives) was being validated by prose tracing
alone, long after the point where writing real (even stub) files and running
`tsc`/`next build` would have caught the binding-class bugs exhaustively and
instantly.

## Refuted or unverified-but-corroborating (not acted on directly, listed for completeness)

- Whether compiler-feedback specifically produced the single largest quality
  jump among 5 iterative LLM-codegen feedback loops (LLMLOOP, arXiv:2603.23613)
  did not survive adversarial vote (0-3) — treat as unconfirmed, not refuted by
  counter-evidence, just insufficiently checked before the rate limit hit.
- Whether search-based (EvoSuite) oracles are structurally more reliable than
  LLM/human-written ones because they encode actual vs. intended behavior (same
  paper) also did not survive vote — same caveat.
- Package-hallucination persistence/rate claims (arXiv:2406.10279,
  arXiv:2605.17062) mostly errored on rate limit rather than being checked; the
  general phenomenon (LLMs hallucinating non-existent imports/packages,
  sometimes repeatably) is well enough established elsewhere in the literature
  that it doesn't need to rest on these specific unverified numbers.

## Practitioner sources (not put through adversarial voting, but directly relevant)

- Simon Willison's "Agentic Engineering Patterns" and Addy Osmani's AI-coding
  workflow writeup both describe reliable agent workflows as tight loops of
  small generation steps with **immediate execution/compiler/test feedback fed
  back into context**, not one large artifact reviewed repeatedly before any
  code exists.
- A contrasting critique (dev.to/chrisywz, "The limits of spec-driven
  development") makes the point most relevant to this specific pain: keeping a
  prose spec in sync with a growing system "creates a maintenance tax that grows
  with system complexity" and can **double** overall overhead rather than reduce
  it — directly matches the observed pattern where fixing one round's findings
  kept introducing new pointer/binding bugs into the same document.
- A companion piece (yuvalyeret) argues detailed, execution-ready specs should
  be written close to the point of implementation, not fully fleshed out far in
  advance — specs should emerge iteratively alongside code, not be exhaustively
  completed before any code exists.
- Contract-first/type-driven tooling (tRPC, OpenAPI-codegen, discriminated-union
  types) converges on the same structural idea from a different angle: make
  certain bug classes (undefined API references, illegal states) a **compile
  error**, not a review target.

## Recommendation applied

See `~/Claude/loop/fix_plan.md` entry **H-AC-ORACLE-TARGET-1** for the concrete,
gated, procedural fix adopted from finding #4/#5 above (adversarial-AC oracle
mutation-checking, added to `DESIGN_CHECKLIST.md` gate 9, `roles/test_writer.md`
LOOP-M3, `roles/verifier.md` LOOP-M6 — validated via a blind dispatch that
independently reproduced the AC19 diagnosis in one pass).

Findings #1/#2/#6 (mechanical detection of binding bugs, stable anchors instead of
relative pointers, and the general "spec-anchored, code-coupled" architecture) are
NOT yet turned into a loop-team gate as of this writing — flagged for a follow-up
orchestrator.md change: introduce real compiler/typecheck feedback into the loop
once a slice's interface/schema shape is settled, rather than continuing pure
prose-lens review through the binding-and-wiring layer of a build.
