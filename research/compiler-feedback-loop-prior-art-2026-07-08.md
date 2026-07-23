# Compiler/typecheck-feedback-in-the-loop: prior art and a concrete wiring proposal (2026-07-08)

## Why this was researched

Extends `research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md` (read that
first — this file does not repeat its synthesis). That doc named a target architecture
("spec-anchored, code-coupled" with a blocking "Drift Validator", arXiv:2606.27045) but
left it unimplemented, and flagged the concrete gap: padsplit-cockpit Slice 6b burned
~9 of ~30 plan-check rounds on the identical "referenced identifier never bound"
bug class that `tsc --noEmit` catches mechanically. This dispatch's job: find REAL,
verifiable repos/mechanisms for (1) an actual Drift-Validator implementation, (2) a
mature hallucinated/unbound-identifier detector, (3) how real coding-agent frameworks
sequence compiler feedback, (4) contract-first prior art — then answer, concretely,
where in `orchestrator.md` real compiler feedback should be wired in.

**Every source below was opened directly (WebFetch/`gh api`/`gh repo view`/`gh search`)
and quoted before being cited — per the honesty bar.** No sub-agents were dispatched;
all research done directly in this session.

---

## 1. Drift Validator / Intent-Graph-vs-Evidence-Graph — does it exist as real code?

### Candidate: the Spec Growth Engine paper itself (arXiv:2606.27045)
- **name:** "The Spec Growth Engine: Spec-Anchored, Code-Coupled, Drift-Enforced
  Architecture for AI-Assisted Software Development" — Hartwig Grabowski.
- **source:** [arxiv.org/abs/2606.27045](https://arxiv.org/abs/2606.27045) /
  [PDF](https://arxiv.org/pdf/2606.27045) — fetched both the abstract page and the full
  PDF text directly.
- **maturity:** paper artifact only. Direct PDF read found **no GitHub repo, no code/
  artifact-availability statement, no appendix link** — "This appears to be an arXiv
  position paper presenting conceptual architecture rather than a technical
  implementation paper with available artifacts." The only two concrete external tools
  the paper itself cites are `github.com/github/spec-kit` and `kiro.dev` (see below) —
  i.e. the paper points at existing spec-driven tooling as prior art, not at its own
  released implementation.
- **claim:** Intent Graph (from spec) vs. Evidence Graph (from static analysis of real
  code — imports/exports/routes/tests) with certain mismatches (orphan code, undeclared
  cross-boundary imports) as hard, unconditional merge-blocking errors.
- **where_it_wires_in:** N/A — nothing to wire in; there is no running implementation to
  adopt.
- **triage:** RESEARCH_ONLY (confirmed no code exists anywhere for this exact paper).
- **priority:** not scored — no artifact, no metric tie.
- **risks:** none (nothing to adopt) — the risk is treating the *name* as if it denoted
  a real tool. It does not. The loop-team's own prior research doc already flagged this
  architecture as "NOT yet turned into a loop-team gate" — this pass confirms it is not
  turned into ANY gate, anywhere, by anyone, as of 2026-07-08.
- **experiment:** none — not adoptable.

### Candidate: github/spec-kit's `/speckit.converge` — the closest REAL thing to a
"drift check," and it is explicitly NOT static-analysis-grounded
- **source:** [github.com/github/spec-kit](https://github.com/github/spec-kit) — opened
  directly (`gh repo view` + fetched `templates/commands/converge.md` verbatim via
  `gh api`).
- **maturity:** **118,644 stars**, MIT license, pushed 2026-07-07, latest release
  v0.12.7 (2026-07-07) — extremely active, GitHub's own official spec-driven-dev
  toolkit, not a side project.
- **claim / mechanism (quoted directly from `templates/commands/converge.md`):**
  > "Close the gap between what a feature's specification, plan, and tasks call for and
  > what the codebase currently implements. Read `spec.md`, `plan.md`, and `tasks.md` as
  > the **sole source of intent**... assess the current state of the code, determine
  > which requirements... are unmet, incomplete, or only partially satisfied..."
  >
  > "This is **not** a diff tool and does **not** track changes. It assesses the present
  > state of the code relative to the feature's artifacts — no git, no branch
  > comparison, no history."
  This is a pure **LLM-prose read of the code against the spec** — the same mechanism
  category as our own plan-check Verifier, not a static-analysis Intent-Graph/
  Evidence-Graph comparison. It is APPEND-ONLY (writes new tasks to `tasks.md`, never
  blocks a merge, never asserts a hard gate) — explicitly the opposite of arXiv:2606.27045's
  "hard error that blocks merge unconditionally" design.
- **Honest finding this settles:** even the single most popular, best-funded, most
  actively maintained spec-driven-development toolkit on GitHub (118k stars, a GitHub
  org product) has NOT built a static/deterministic drift-detection mechanism — its
  closest analog is still LLM-prose review. This corroborates (does not merely repeat)
  the earlier research doc's finding that the "spec-anchored, code-coupled" architecture
  with a real Drift Validator is aspirational, not yet built anywhere in the observable
  ecosystem — not just absent from loop-team.
- **where_it_wires_in:** N/A for direct adoption (it's an LLM-prose mechanism, the thing
  we're trying to move away from for the binding-bug class) — but WATCH it: if spec-kit
  ever ships a static-analysis-backed `converge` mode, that's a decay/upgrade signal
  worth catching on the next radar pass.
- **triage:** WATCH.
- **priority:** not scored (no metric tie; radar-watch item, not an experiment candidate).
- **risks:** none from adoption (not adopting it) — risk is only in radar-staleness if
  its mechanism changes and we don't notice.
- **experiment:** none now; the "experiment" is future re-verification (next radar pass:
  re-open `templates/commands/converge.md`, diff against this quote).

### Architecture-conformance / dependency-boundary checkers (the OTHER half of the
Drift Validator's stated scope — "undeclared cross-boundary imports")
- **dependency-cruiser** (`sverweij/dependency-cruiser`) — **6,874 stars, MIT, pushed
  2026-07-07**. Confirmed via `gh repo view`: "Validate and visualize dependencies. Your
  rules. JavaScript, TypeScript, CoffeeScript." This is a REAL, mature, static tool that
  enforces exactly the "undeclared cross-boundary import" half of arXiv:2606.27045's
  Evidence Graph check (e.g. "no module in `services/` may import from `ui/`") as a
  rule-based, deterministic, CI-blockable check on the actual dependency graph. It does
  NOT do the spec-side "Intent Graph" comparison — it enforces hand-written architecture
  rules, not a spec-derived contract — so it's a narrower, complementary tool, not a
  full Drift Validator.
  - **triage:** WATCH (not needed yet — padsplit-cockpit's current pain is the *binding*
    bug class, which `tsc` already covers with far less setup; dependency-cruiser is the
    right next tool once/if the loop-team starts enforcing layering rules across a
    growing codebase).
  - **priority:** not scored yet (no current metric — parked for a phase when
    cross-boundary layering becomes an active pain point, same treatment as other
    far-future WATCH rows on the radar).
- **ArchUnit** (`TNG/ArchUnit`, Java) — **3,758 stars, Apache-2.0, pushed 2026-07-06**.
  Confirmed via `gh repo view`: "A Java architecture test library, to specify and
  assert architecture rules in plain Java." Same category as dependency-cruiser, JVM
  ecosystem only — not directly applicable to a Node/TS repo like padsplit-cockpit, but
  the canonical reference implementation of "architecture rules as executable tests."
  Note for the record, not for adoption (loop-team's current build targets are
  Python/Node, not JVM).
  - **triage:** RESEARCH_ONLY (wrong ecosystem for current targets — reference only).
- **GitHub topic sweep for "spec drift"** (`gh search repos "spec drift"`, 15 results
  opened): every hit is either a tiny (0–37 star) hobby/experimental project (e.g.
  `nantobv/pituitary` — 21★, "Catch spec drift before it catches you... detects
  overlap, contradictions, stale docs, and code that drifts from what was decided" —
  README-only claim, unopened beyond the search snippet, too small/unverified to cite
  as real evidence) or unrelated (audio "SpecDrift" plugins, a spectral-analysis
  research repo). **No mature, general "spec drift detector" tool exists on GitHub as
  of this scan** — reinforces that the Drift Validator concept is a research proposal,
  not an assemble-don't-invent candidate today.

---

## 2. Hallucinated/unbound-identifier detectors — is there a mature tool, or is `tsc`/`flake8` already the answer?

### arXiv:2601.19106 — confirmed title, confirmed NO branded tool name, confirmed repo
- **title:** "Detecting and Correcting Hallucinations in LLM-Generated Code via
  Deterministic AST Analysis" — Dipin Khati, Daniel Rodriguez-Cardenas, Paul Pantzer,
  Denys Poshyvanyk. Confirmed via direct fetch of both the abstract page and the PDF.
- **Tool name:** the paper does **not** brand the framework — it's called generically "a
  deterministic, explainable pipeline... using static analysis, a knowledge base of
  valid APIs, and prompt-guided inference" (quoted from the repo README, see below — the
  arXiv PDF itself doesn't name it either).
- **Repo (confirmed real, opened directly):**
  [github.com/WM-SEMERU/Hallucinations-in-Code](https://github.com/WM-SEMERU/Hallucinations-in-Code)
  — **maturity: 2 stars, no license file, last push 2026-01-26, last update
  2026-05-19.** This is an academic paper-companion repo, not a production tool.
  Confirmed contents (98.9% Python / 1.1% Dockerfile): `hallucination_pipeline/` module
  with four runnable entry points (`build_kb`, `hallucination_generator`,
  `run_on_detected`, `evaluator`). Quoted from its own README: "Parses code using
  Python's `ast` module... Extracts import statements, aliases, and function calls." So
  the mechanism really is a bespoke Python-`ast`-based analyzer, not a wrapper around
  `pyflakes`/`tsc`/an existing linter — but it is Python-only, single-author-adjacent
  (WM-SEMERU is a research lab, not a maintained OSS project), unlicensed (a real
  adoption blocker — no license means no legal right to redistribute/modify), and 2
  stars/no releases.
- **triage:** RESEARCH_ONLY — real code, but not adoption-ready (no license, no
  maintenance signal, narrow Python-only scope, academic-quality packaging).
- **Broader GitHub sweep** (`gh search repos "hallucination detection"` /
  `"code hallucination"`, 30 results across two queries, all opened at the listing
  level): every single result is a paper-replication or research-only repo, star counts
  0–70 (the single outlier, `idosal/git-mcp` at 8,237 stars, is an MCP server that feeds
  an LLM the REAL repo's docs to prevent hallucination at generation time — a different,
  earlier-stage mitigation, not a post-hoc AST checker). **No mature, general-purpose,
  production "LLM code hallucination detector" tool exists on GitHub.**
- **The honest conclusion this sweep supports:** the field has not produced (and, per
  this scan, is not close to producing) a better bespoke tool for this exact bug class
  than what already ships with every mainstream compiler/linter. For TypeScript,
  `tsc --noEmit` IS the production-grade unbound-identifier/missing-import detector —
  it's not a research prototype, it's the language's own type-checker, already proven
  in this project's own history (`learnings.md`, 2026-07-01: `tsc --noEmit` caught a
  `TS2307` "module not found" error a vitest-only run missed). For Python, the
  equivalent is `flake8`'s F821 (`undefined name`) check — see Aider's own use of it
  below, which is independent confirmation this is the established, no-bespoke-tool-
  needed answer.
- **priority:** not applicable to the WM-SEMERU repo (RESEARCH_ONLY, no metric tie) —
  see Section 4 below (the `verify.py` tsc-gate candidate) for the actual scored,
  adoptable candidate this section's finding feeds.

---

## 3. How real coding-agent frameworks sequence compiler/typecheck feedback — read from source/docs, not summaries

### Aider (Aider-AI/aider) — auto-lint is ON BY DEFAULT, runs after EVERY edit, blocking-via-retry
- **maturity:** 47,165 stars, Apache-2.0, actively maintained (pushed 2026-05-22).
- **Mechanism, confirmed from official docs (fetched directly) + actual source
  (`aider/linter.py`, fetched via `gh api`):**
  > "By default, aider will lint any files which it edits." (`--no-auto-lint` to
  > disable.) "If there are linting errors, aider expects the command to print them on
  > stdout/stderr and return a non-zero exit code." — [aider.chat/docs/usage/lint-test.html](https://aider.chat/docs/usage/lint-test.html)
  >
  > `--auto-lint` defaults to **True**; `--auto-test` defaults to **False** (opt-in via
  > `--test-cmd` + `--auto-test`). When enabled, "Aider reads the [linter] message,
  > modifies the code to satisfy the rule, and re-runs until the linter is happy or it
  > gives up after a sensible number of tries."
- **Directly relevant to THIS bug class — quoted straight from `aider/linter.py`'s
  `flake8_lint` method (source, not docs):**
  ```python
  fatal = "E9,F821,F823,F831,F406,F407,F701,F702,F704,F706"
  flake8_cmd = [sys.executable, "-m", "flake8", f"--select={fatal}", ...]
  ```
  **`F821` is flake8's "undefined name" code — the exact "identifier referenced but
  never bound" bug class this dispatch was created to address.** Aider's own default,
  always-on auto-lint gate specifically hard-codes this check as one of a small fatal
  set, run after every single edit, with the result fed back to the model automatically
  — independent, real-world confirmation (not just the arXiv paper's benchmark number)
  that this exact bug class is (a) common enough in LLM-generated code that a major
  production tool special-cases it, and (b) fully solved by an off-the-shelf linter, not
  a bespoke hallucination detector.
- **Caveat (found by reading the same source):** Aider's built-in `Linter` class only
  ships a real linter for **Python** (`languages = dict(python=self.py_lint)`). For
  every other language (including TypeScript), the fallback is `basic_lint` (a
  tree-sitter structural scan, NOT a compiler/type-check) unless the user explicitly
  configures `--lint-cmd <cmd>` themselves. **Aider does not run `tsc` for you by
  default** — this is a real limitation, not an oversight to gloss over.
- **triage:** TESTABLE (Python-side pattern directly portable: run `flake8 --select=F821,...`
  after every Coder edit on Python targets, same as our proposed TS-side `tsc` gate).
- **where_it_wires_in:** the same `verify.py` extension proposed in Section 4, as a
  Python-ecosystem sibling check to the TS-ecosystem `tsc --noEmit` check.

### Cline (cline/cline) — IDE-diagnostics diff, fed back automatically (advisory, not a hard block)
- **maturity:** 64.4k stars, Apache-2.0, very actively maintained (latest CLI release
  v3.0.38, 2026-07-07).
- **README claim (quoted):** "It monitors linter and compiler errors as it works,
  fixing issues like missing imports, type mismatches, and syntax errors before you
  even see them."
- **Actual mechanism, confirmed by reading real source**
  (`apps/vscode/src/integrations/editor/DiffViewProvider.ts`, fetched via `gh api`):
  ```
  this.preDiagnostics = (await HostProvider.workspace.getDiagnostics({})).fileDiagnostics
  ...
  const postDiagnostics = (await HostProvider.workspace.getDiagnostics({})).fileDiagnostics
  const newProblems = getNewDiagnostics(this.preDiagnostics, postDiagnostics)
  const problems = await diagnosticsToProblemsString(newProblems, [DiagnosticSeverity.DIAGNOSTIC_ERROR])
  ...
  newProblemsMessage = newProblems.length > 0
    ? `\n\nNew problems detected after saving the file:\n${newProblems}` : ""
  ```
  This diffs VS Code's own `vscode.languages.getDiagnostics()` output (whatever
  language servers are attached — tsserver for TS, Pylance for Python, etc.) before and
  after each file save, and **auto-injects only the NEW error-severity diagnostics**
  into the next message sent back to the agent. **This is advisory-automatic, not a hard
  block**: nothing prevents Cline from continuing/finishing with diagnostics still
  present — the new-problems text is just appended to context so the model *can* choose
  to fix it. (Confirmed separately: a real open GitHub issue, cline#4381, describes race
  conditions where stale/incomplete diagnostics get read before the language server
  finishes — a known reliability caveat of this exact mechanism.)
- **Transfer-condition check:** this mechanism structurally REQUIRES a running IDE host
  with attached language servers (VS Code's `vscode.languages` API) — our loop-team's
  Coder sub-agents run in a CLI/harness context with no IDE host, so this exact
  mechanism does not transfer. The OUTCOME it achieves (compiler-grade diagnostics fed
  back automatically) is achievable more cheaply and more portably by invoking
  `tsc --noEmit` as a subprocess directly — no IDE/LSP runtime required. Also worth
  noting for the enforcement-type question: Cline's mechanism is **instructional**
  (diagnostics are surfaced to the model, which may or may not act on them) — our
  proposed `verify.py` extension (Section 4) is **structural** (a boolean AND on the
  harness's `passed` field, unconditionally), which is the stronger guarantee.
- **triage:** RESEARCH_ONLY (real, well-sourced precedent; not directly portable given
  our non-IDE execution context — informs design, not adoption).

### OpenHands (All-Hands-AI/OpenHands, ~78.5k★, already ADOPTED-category-adjacent on
the radar) — TWO separate findings, one negative and one directly load-bearing

- **Negative finding (confirmed by reading `.github/workflows/lint.yml` directly via
  `gh api`):** OpenHands DOES run `tsc` — but only on **its own source code**, in CI,
  on push/PR to `main`:
  ```yaml
  - name: Lint, TypeScript compilation, and translation checks
    run: |
      cd frontend
      npm run lint
      npm run make-i18n && npx tsc
  ```
  This is OpenHands maintaining ITS OWN codebase's quality, not a feature of the agent
  runtime that checks code OpenHands generates for a user's target repo. Worth stating
  plainly: this is NOT evidence that OpenHands's agent loop runs `tsc` on generated
  code by default.
- **The actually load-bearing finding — OpenHands "Stop hooks", a REAL, documented,
  directly-analogous precedent for exactly the gate this dispatch is designing:**
  Confirmed by direct fetch of
  [docs.openhands.dev/openhands/usage/customization/hooks](https://docs.openhands.dev/openhands/usage/customization/hooks):
  > "a `Stop` hook can force the agent to keep working if linting checks haven't passed
  > yet." Executes "when the agent tries to finish" — a final quality gate before
  > session completion, not on every turn.
  >
  > Documented example (quoted verbatim):
  > ```bash
  > #!/bin/bash
  > # Stop hook: Don't let the agent stop if linting fails
  > cd "$OPENHANDS_PROJECT_DIR"
  > if ! npm run lint 2>&1; then
  >     echo '{"decision": "deny", "reason": "Linting failed. Please fix the issues before finishing."}'
  >     exit 2
  > fi
  > exit 0
  > ```
  > wired via `.openhands/hooks.json`: `{"stop": [{"matcher": "*", "hooks": [{"command": ".openhands/hooks/lint_check.sh", "timeout": 120}]}]}`.
  This is a STRUCTURALLY blocking gate (`"decision": "deny"` + non-zero exit literally
  prevents the agent from finishing) — the closest real-world precedent found in this
  entire research pass to "compiler feedback as a blocking gate distinct from prose
  review." It's user-configurable per-repo (the example uses `npm run lint`, but nothing
  restricts the command to a linter — `tsc --noEmit` fits the identical slot).
- **Transfer-condition check:** requires OpenHands's own hook-execution runtime
  (`.openhands/hooks.json` + its Stop-event dispatch) — our loop-team doesn't run inside
  OpenHands, so the literal file/convention doesn't transfer. But loop-team already HAS
  an equivalent structural substrate for this exact purpose:
  `hooks/subagent_stop_gate.py` (referenced throughout `orchestrator.md`, e.g. the
  `.verifier_pass` flag-credit mechanism) is our own Stop-hook-equivalent layer, and
  `verify.py` is our own synchronous, exit-code-driven, Oga-invoked blocking gate
  (already explicitly carved out of Oga's "no direct tool use" self-check rule as "the
  step-4 harness run and the micro-step checkpoint verify"). **The pattern transfers
  cleanly; the specific file does not need to.**
- **triage:** TESTABLE (the pattern, not the file) — directly informs Section 4's design.

### mini-swe-agent (SWE-agent/mini-swe-agent, already CANDIDATE/ADOPTED-adjacent on the
radar, 5.5k★) — negative-confirmation contrast case
- Confirmed via direct README fetch: **"Does not have any tools other than bash — it
  doesn't even need to use the tool-calling interface of the LMs."** Every check
  (lint, typecheck, test) is just an arbitrary bash command the model itself decides to
  run — there is no structural, deterministic, always-on gate built into the scaffold
  at all. This is a useful negative data point: our current Coder-model pick's minimal
  scaffold has ZERO built-in compiler-feedback discipline of its own — whatever gate
  exists has to come from the harness OUTSIDE the scaffold (i.e. `verify.py`, which is
  exactly where Section 4 proposes adding it).
- **triage:** N/A (not a candidate — a confirming data point for why the gate belongs in
  `verify.py`, not in the Coder role/scaffold itself).

### nizos/tdd-guard — real, mature, Claude-Code-native hook precedent (same host environment as loop-team)
- **maturity:** 2,246 stars, MIT, latest release v1.7.0 (2026-06-23), actively
  maintained (pushed 2026-07-06). Its successor project `nizos/probity` (80★, MIT,
  pushed 2026-07-06, "TDD enforcement and guardrails for Claude Code, Codex, and GitHub
  Copilot CLI") is where new development is happening — README states "TDD Guard grew
  into Probity...New projects should start there. TDD Guard remains maintained for the
  projects that rely on it" (a maintenance-mode signal worth radar-tracking).
- **Mechanism, confirmed from real docs (fetched `docs/installation.md`,
  `docs/linting.md`, `docs/validation-model.md` directly):**
  - The PRIMARY, blocking gate is a `PreToolUse` hook (`matcher: "Write|Edit|MultiEdit|TodoWrite"`)
    that runs `tdd-guard` before every edit — but the validator itself is **LLM-based,
    not deterministic**: "TDD Guard validates changes using AI... uses the Claude Agent
    SDK to communicate with Claude directly" (default model `claude-sonnet-4-6`).
  - A SEPARATE, later `PostToolUse` hook adds optional linting (ESLint/golangci-lint/
    RuboCop — **no TypeScript-compiler/`tsc` integration mentioned anywhere in its
    docs**) — and this lint pass is explicitly advisory: "the coding agent will be
    prompted to fix them," not a hard merge-block.
- **Directly relevant precedent:** this confirms loop-team's own hook infrastructure
  (`hooks/subagent_stop_gate.py`, `hooks/micro_step_gates.py`) is architecturally the
  SAME pattern a real, 2.2k-star, actively-maintained Claude-Code tool uses (PreToolUse
  gate on Write/Edit) — but also shows that even this closest same-ecosystem precedent
  has NOT wired in a deterministic type-checker; its enforcement is LLM-judgment-based
  for the blocking layer and lint-only (not typecheck) for the advisory layer. No
  existing Claude-Code tool found in this scan does what Section 4 proposes.
- **triage:** WATCH (real, close-to-home precedent for hook-based blocking; not directly
  adoptable since its validator is LLM-based, the opposite of the deterministic
  guarantee we want).

---

## 4. Contract-first/type-driven codegen — "make the bug class a compile error"

(Corroborating, not duplicating, the existing research doc's item — each quote below is
freshly fetched and verbatim, not restated from memory.)

- **tRPC** (`trpc/trpc`) — **40.4k★, MIT, v11.18.0 (2026-06-18).** README tagline
  (quoted): **"Move fast and break nothing. End-to-end typesafe APIs made easy."** —
  "build fully typesafe APIs without schemas or code generation, providing static
  typesafety and autocompletion directly in the editor for inputs, outputs, and
  errors." A client calling a renamed/removed procedure is a compile-time TS error, by
  construction — no runtime discovery needed.
- **Zod** (`colinhacks/zod`) — **43.2k★, MIT, v4.4.3 (2026-05-04).** "TypeScript-first
  schema validation with static type inference" — `z.infer<>` ties the runtime schema
  and the static type to one source of truth; a schema/type drift is impossible because
  the type IS derived from the schema, not hand-duplicated.
- **openapi-typescript** (`openapi-ts/openapi-typescript`) — **8,214★, MIT, pushed
  2026-07-08 (actively maintained).** "Generate TypeScript types from OpenAPI 3 specs."
  This is the most direct real-world analog to arXiv:2606.27045's Intent-Graph idea:
  the OpenAPI spec IS the Intent Graph, and the generated `.d.ts` file IS the Evidence
  Graph's contract surface — any code that doesn't match the generated types fails
  `tsc`, immediately, deterministically. It's one-directional (spec → types; it doesn't
  detect code that silently diverges from an UN-regenerated spec) and API-surface-only
  (doesn't cover internal binding/import correctness) — narrower than the full Drift
  Validator vision, but it's real, mature, and already the working version of "spec
  compliance enforced by the compiler" for the API-contract slice of the problem.
- **triage (all three):** WATCH / reference-only — these validate the underlying
  PRINCIPLE (make illegal states/mismatches a compile error) but aren't things the
  loop-team framework itself would "adopt" (they're target-repo-level libraries a Coder
  might use when building an API, not loop-team-harness-level tooling). No experiment
  spec — they're prior-art corroboration, not a candidate to A/B.

---

## Synthesis — where should real compiler/typecheck feedback go in `orchestrator.md`?

**Answer: it is a new, additive, structural check inside `harness/verify.py` —
NOT a new dedicated role, NOT an addition to Test-writer/Coder's prompts, and NOT
(primarily) a `DESIGN_CHECKLIST.md` gate.** Here's why, grounded in what this research
actually found:

1. **The mechanism has to be deterministic to be worth building at all — and every
   piece of real prior art that tried to make it "a role's judgment" instead of "a
   compiler's verdict" ended up with the SAME weakness we're trying to fix.**
   `tdd-guard`'s PRIMARY blocking gate is LLM-based (Section 3) despite being the
   closest same-ecosystem (Claude Code, hook-native) precedent found. `spec-kit`'s
   `/speckit.converge` — from GitHub itself, 118k stars — is explicitly "not a diff
   tool," pure LLM prose-read (Section 1). Both are more mature, better-funded
   projects than loop-team, and both still land on prose/LLM judgment for their
   "drift" check, because that's the natural pull of any system built by a role
   dispatch. Making the fix "a new role" or "a Test-writer/Coder prompt instruction"
   reproduces exactly this pull — it would be one more participant asked to remember
   to run `tsc` and read the output correctly, i.e. instructional, not structural,
   enforcement (see the role brief's transfer-condition check: an instructional
   guarantee whose failure is silent and load-bearing is exactly the pattern to avoid).
   A dedicated "compile-check role" is also simply redundant overhead: `tsc --noEmit`
   needs no reasoning, no context window, no model call at all — wrapping it in an
   agent dispatch only adds latency, cost, and a NEW instructional-compliance surface
   (the role could still be skipped, mis-invoked, or have its output misread) for zero
   benefit over a subprocess call.

2. **`verify.py` already IS the loop's structural, un-skippable, boolean-AND gate, and
   it already has the exact additive pattern needed — twice.** It ANDs Python and Node
   test results together when both ecosystems are present (`detect_and_run`'s
   dual-ecosystem path, lines 254–291) and it ANDs an entirely separate concern — the
   live-smoke URL sweep — into the same `passed` field via `_smoke_gate` (lines
   294–370, wired in at `main()`, lines 386–398), using a manifest-driven, purely
   additive JSON key (`smoke`) that "existing consumers that read `runner` alone are
   unaffected" by. A `type_check` gate is the same shape a third time: detect a
   `tsconfig.json` (parallel to the existing `_load_package_json`/`detect_node_runner`
   logic already in the file), run `npx tsc --noEmit` (falling back to a local `tsc`
   binary the same way `node_runner_argv` prefers `npx`), AND its exit code into
   `passed`, and add an additive `type_check: {"ran": bool, "passed": bool, "output": ...}`
   key — zero changes to any existing consumer's contract, following the file's own
   established, tested pattern (there are already `test_verify_node.py` and
   `test_verify_harness.py` files to extend). For Python targets, Aider's own default
   gate (Section 3) is directly portable as a sibling check: `flake8 --select=E9,F821,F823,F831,F406,F407,F701,F702,F704,F706`
   when a Python target has no `pytest`/type-checker already covering it.

3. **This closes the gap at exactly the right TIME, not just the right PLACE.** The
   micro-step build loop (`orchestrator.md` item 2: "when it returns, OGA runs the
   impacted tests ITSELF... green → git checkpoint commit immediately") already calls
   `verify.py` (or `pytest --testmon`) at EVERY checkpoint, per-step — this is the same
   per-step-verification principle the file already cites MAKER (arXiv:2511.09030) for.
   Baking the type-check into `verify.py` means every micro-step checkpoint gets it for
   free, catching a binding bug the instant it's introduced — not 9 rounds and one
   entire spec-level review cycle later, which is precisely the padsplit-cockpit Slice
   6b failure mode this whole research thread started from.

4. **`DESIGN_CHECKLIST.md` still gets a small, correctly-scoped touch — but as a
   SCOPING correction, not as the enforcement mechanism.** The plan-check step
   (`orchestrator.md` step 1) is pre-implementation prose review; its entire value is
   INTERFACE/schema/behavioral-correctness judgment a compiler cannot make (does this
   AC test the right thing, is a security guard's oracle well-targeted — the exact kind
   of finding H-AC-ORACLE-TARGET-1 formalized). Binding correctness (does this import
   resolve, does this export exist) is not a judgment call at all once real files
   exist — asking a plan-check lens to keep re-deriving it by re-reading imports is the
   literal "spec-first" over-extension the earlier research doc diagnosed. The
   correctly-scoped fix is one line added to `orchestrator.md`'s plan-check section (not
   a new DESIGN_CHECKLIST gate number): once a slice's interface/schema shape is settled
   and real (even stub) files exist, binding/wiring-level findings (imports, exports,
   identifier existence) are owned by the mechanical `verify.py` type-check gate, not by
   further plan-check rounds — a plan-check lens finding a binding bug after that point
   is a signal the mechanical gate wasn't run yet or isn't armed for this target, not a
   case for more prose review.

5. **Transfer-condition discipline (per the role brief, applied to the actual adopted
   pattern):** execution context required = a subprocess call from Oga's main
   transcript (already how `verify.py` is invoked today — "the harness command does not"
   count as forbidden direct-tool-use, per Oga's own self-check carve-out). Our context
   satisfies this already, with zero new infrastructure. Enforcement type = **structural**:
   `passed` is a boolean AND over exit codes; there is no participant who could "forget"
   to honor it, unlike DESIGN_CHECKLIST's nine (soon to remain nine) gates, which are
   all instructional prose disciplines a role must remember to apply. This is the
   strongest guarantee category available and matches exactly what H-AC-ORACLE-TARGET-1
   used for ITS enforcement layer (an executable mutation check, not a re-read
   instruction) — same rigor, same reason it was chosen there.

**Net recommendation for the fix_plan.md entry that should follow this research (Oga's
call, not mine to file):** design a `type_check` gate inside `harness/verify.py`
(TS: `tsc --noEmit` gated on `tsconfig.json` presence; Python: `flake8` fatal-set gated
on `.py` presence, mirroring Aider's own default set) as the primary mechanism, a
one-line plan-check scoping correction in `orchestrator.md` step 1 as the secondary
fix, and — per the H-AC-ORACLE-TARGET-1 template this dispatch was asked to follow —
validate the new gate with a blind test (a synthetic diff containing exactly one unbound
identifier, confirm `verify.py` catches it with `passed: false` and a legible error,
confirm a clean diff still passes) plus an independent Verifier re-check, before
trusting it as adopted.

---

## Dropped / not pursued (negative results, so they aren't re-researched)

- **A bespoke hallucination-detector tool** (beyond the compiler itself) — searched
  exhaustively (Section 2), found nothing production-grade. Kill criterion already met:
  if a future scan finds a >500-star, licensed, actively-maintained general hallucinated-
  identifier tool, it's worth a second look; nothing today beats `tsc`/`flake8` for this
  exact bug class, which is a genuinely good outcome (assemble, don't invent — the
  existing compiler already IS the best tool).
- **Cline's IDE-diagnostics-diff mechanism** — real and well-documented, but requires an
  IDE/LSP host our Coder sub-agents don't run inside of. Not pursued as a literal port;
  its OUTCOME is achieved more cheaply via direct `tsc` subprocess invocation.
- **tdd-guard as a direct adoption** — real, close-to-home (Claude Code native), but its
  blocking layer is LLM-validated, not deterministic, which is the opposite property we
  need for this specific bug class. Its `PostToolUse` lint-only advisory layer also
  doesn't cover TypeScript type errors (ESLint/golangci-lint/RuboCop only, no `tsc`).
  Worth a radar WATCH row for its Probity successor's evolution, not adoption now.
- **ArchUnit / full architecture-conformance tooling** — real and mature, wrong
  ecosystem (JVM) or premature for the loop-team's current pain (binding bugs, not
  cross-boundary layering violations). Parked as a later-phase WATCH candidate
  (`dependency-cruiser` for when/if Node-side layering rules become the active problem).
