# Compiler-gate design recommendation — 2026-07-08

**Header:** This document synthesizes two upstream docs —
`<HOME>/Claude/loop/research/compiler-gate-external-research-2026-07-08.md` and
`<HOME>/Claude/loop/research/compiler-gate-internal-grounding-2026-07-08.md` —
after all 12 of their most load-bearing citations were independently re-verified against
primary sources (11 straightforward CONFIRMED, 1 labeled REFUTED but which is a
claim-polarity restatement artifact whose underlying evidence text actually corroborates the
original finding — kiro.dev has zero reference to any "Spec Validator" feature, consistent
with the original research).

---

## Part 1 — External material: what to copy, adapt, or shelve

Both cited arXiv papers are real — re-confirmed by independently re-fetching them:
- arXiv:2601.19106 (Khati et al., William & Mary SEMERU Lab) — 100% precision / 87.6% recall
  / 0.934 F1 is real, but it's category-specific: missing-imports detection is 97.9%,
  mis-typed API calls 84.5%, and "contextual mismatch" (semantically wrong but syntactically
  valid) is only 33.3% detection / 0% correction. This is squarely the padsplit-cockpit
  "undeclared identifier" bug class — but would be oversold if cited as "catches most LLM
  code bugs."
- arXiv:2606.27045 (Grabowski, sole author) — coined "spec-anchored, code-coupled" and the
  Intent-Graph-vs-Evidence-Graph "Drift Validator," confirmed verbatim in its Section 5.4.
  But it's an unimplemented, unbenchmarked design paper — "maintained as an internal
  design-document set... available from the author on request." Treat it as
  naming/architecture inspiration only, not adoptable code.

Real, running tools, ranked:

| Verdict | Tool | Why |
|---|---|---|
| Copy | knip's `unresolved` issue type (github.com/webpro-nl/knip) | 11.7k stars, ISC, active — off-the-shelf detector for exactly "referenced identifier never bound," once real TS/JS files exist |
| Copy (pattern) | aider's `max_reflections = 3` + auto-lint loop (github.com/Aider-AI/aider) | 47k stars, Apache-2.0 — lint failure feeds back as next turn's prompt, capped at 3 attempts, not open-ended |
| Copy (pattern) | TypeChat's validate-then-repair loop (github.com/microsoft/TypeChat) | 8.7k stars, MIT — one bounded repair attempt, feeds the validator's own error back verbatim |
| Adapt | dependency-cruiser (github.com/sverweij/dependency-cruiser) | 6.9k stars, MIT — closest existing tool to "undeclared dependency"/"bypasses contract" hard errors, needs our own boundary config |
| Adapt | ast-grep / Semgrep | structural rule engines for languages knip doesn't cover |
| Prior art only | SWE-agent, OpenHands, AlphaCodium, CompCoder/Self-Edit/CodeT/Reflexion/RLCF/StepCoder | confirms "compiler/execution feedback in the loop" is a decade-deep, repeatedly-validated idea — but none is adoptable harness tooling, they're training-time techniques or general agent harnesses with no named compiler-gate feature |
| Negative finding | GitHub spec-kit (118k stars — the most popular spec-driven toolkit) | its `/speckit.converge` is pure LLM analysis appending tasks to markdown — explicitly "not a diff tool," zero compiler/lint/test invocation, nothing blocks a merge |
| Negative finding | AWS Kiro | no "Spec Validator" feature exists in its docs, despite a third-party blog claim |

Bottom line: nobody has actually built the Drift-Validator-style blocking gate yet. This is a
genuine, unclaimed gap — not a wheel we'd be reinventing.

The Google style-guide / Metanorma anchored-ID convention is also confirmed (with a precision
correction: Google splits it into two guidances — avoid spatial words, and link to the actual
heading; Metanorma's real mechanism is author-supplies-stable-ID → system computes the label
at each citation site).

## Part 2 — Internal grounding: answers to the 3 design questions

**Q1 — Is "round 20-24" the real transition point?** No — falsified by the actual 31-round
record (padsplit-cockpit's Airbnb-calendar slice, plan_check_log.md):
- The binding-bug class starts at round 16-17, not round 20 — round 17's find (5 undeclared
  identifiers) is literally logged as "the single most severe individual finding of the whole
  process."
- It recurs continuously through round 30 (9 self-tracked instances: rounds 17, 22, 23, 24,
  26, 27, 28, 29, 30).
- Real design/security findings kept surfacing in the same window, not before it — and
  critically, the two most consequential findings of the entire run (the AC19/AC16 cross-org
  security-oracle bugs that directly produced the existing H-AC-ORACLE-TARGET-1 gate) landed
  at rounds 30 and 31, the very end.
- The real decision anchor is a human judgment call at round 31, retrospectively reviewing
  "rounds 24-31" — not a mechanically-detectable round-20 inflection.
- One real signal does hold: the backend concurrency logic converged early and stayed clean
  for 7 straight rounds while the UI-wiring layer's binding bugs never stopped until a human
  called it — "design-sensitive core stabilizes before the wiring layer" is real; "round
  20-24" as a trigger isn't.

**Q2 — New role, Test-writer addition, or DESIGN_CHECKLIST gate?** Neither of the first two,
in favor of a narrow DESIGN_CHECKLIST variant:
- Reject folding into Test-writer — this is the same mistake H-AC-ORACLE-TARGET-1 already
  made and reversed four days before this dispatch: its first version put an executable check
  in test_writer.md, and an independent Verifier caught that the file's own header states it
  "runs strictly BEFORE any implementation exists," making the check unexecutable there. A
  compiler pass has the identical shape.
- Reject a new "Stub-and-compile" subagent type — heaviest, least-precedented option; no gate
  in this framework's history has ever been introduced as a new role (H-AC-ORACLE-TARGET-1
  itself spread across four existing role files), and a new custom subagent type costs a
  session restart just to take effect.
- The plan-check Verifier is tool-level blocked from ever running a compiler (tools: Read,
  Grep, Glob; Bash explicitly disallowed) — confirming the check has to live downstream,
  after real files exist.
- harness/verify.py — "the objective signal the whole loop optimizes against" — has literally
  zero tsc/typecheck/build step today, even though tsc --noEmit has already been run manually
  for this exact project. Real, standing gap.
- What actually happened live on this exact slice: the round-31 human decision didn't invent
  a role — it stopped prose plan-check and told Test-writer/Coder to proceed with required
  real next build/tsc --noEmit verification, reusing the existing pipeline.
- Recommendation: (i) a DESIGN_CHECKLIST.md stopping-rule — once N consecutive rounds
  saturate on the same binding-class signature with zero new logic/security finding, stop
  prose review of that class and proceed to Test-writer→Coder; (ii) wire an actual tsc
  --noEmit/next build into verify.py as a standing step. Zero new roles, zero
  session-restart cost, matches exactly what was actually decided for the real slice.

**Q3 — Same treatment for the cross-reference anti-pattern?** Yes:
- Zero spec.md-authoring guidance exists anywhere in orchestrator.md today.
- The same real run burned 9+ distinct rounds on this exact defect class — including one
  round where fixing a prior instance introduced 3 new ones.
- It does not become moot post-code: spec.md is an explicitly maintained living artifact in
  this framework (Test-writer's spec↔code contract check, Verifier's post-build "re-read the
  goal/ACs" pass), and the dedicated sweeping mechanism that catches these stops once
  plan-check rounds end — so exposure per remaining read goes up post-code.
- Gate on revision count, not line count (the first instance predates any size discussion) —
  reuse orchestrator.md's own existing "≥2 plan-check rounds" threshold rather than inventing
  a new constant. This fix is far cheaper than the compiler gate (a one-line grep, no new
  tools/roles) and doesn't need to wait on that harder decision.

## Bottom line

Three concrete, evidence-backed candidates, none requiring new roles or subagent types:
1. A DESIGN_CHECKLIST.md stopping-rule for binding-class saturation during plan-check.
2. Wire tsc --noEmit/next build into harness/verify.py (currently absent).
3. A spec.md cross-reference rule: ban relative "above/below" language once a spec has had
   ≥2 plan-check revision rounds.

Status: this is a design recommendation, not yet built. Per this framework's own precedent
(H-AC-ORACLE-TARGET-1), adopting any of these three should go through: design it as an
explicit fix_plan.md entry, validate with a blind test before trusting it, get an independent
Verifier pass, and confirm a green run_evals.py — before it enters
DESIGN_CHECKLIST.md/orchestrator.md/verify.py for real.
