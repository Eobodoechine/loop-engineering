# Loop Engineering Team — The Next Phase

*A doc for Claude Code. What to build next, why it's the right next step, and how to build it. Written to be actioned.*

---

## Where the team is now (honest assessment)

The team is four roles (Oga orchestrator, Test-writer, Coder, Verifier) plus a deterministic harness, running a single build → test → fix loop. What's notable is how it has *matured through real use*: it is now hardened against the field's deepest failure mode — the **false pass**:

- The harness (`harness/verify.py`) force-fails when **0 tests were collected** (a green run that proved nothing).
- The Verifier (`roles/verifier.md`) now does a **Layer-2 reality check** — execute the real thing, don't grade the transcript — and **red-teams the spec itself**.
- The Test-writer (`roles/test_writer.md`) classifies every criterion **`[DOC]` vs `[BEHAVIORAL]`** and refuses to let a keyword-grep stand in for a behavioral check.
- The Orchestrator (`orchestrator.md`) **probes reality before designing fixes** and red-teams the brief's acceptance criteria.

Every one of those came from a real incident (the playwright `import`-vs-chromium-binary miss; the zero-test green). That's the loop working: a hole was found, a gate was added.

**But here is the limitation that defines the next phase:** all of that improvement is **manual and unguarded**. A human or Claude notices a hole and appends it to `fix_plan.md` in prose. The hooks enforce *"did you run a verifier"* — they do **not** enforce *"is the verifier still as good as it was yesterday."* And there is no metric, so two versions of a role prompt can't be compared objectively, and nothing can optimize them.

Root cause, stated plainly: **the team can build and verify a *product*, but it cannot yet verify or improve *itself* with a measurement.** `fix_plan.md` is a *log of holes*, not an *executable suite that re-checks them*.

---

## The next phase: an Eval Harness → measured self-improvement

This is the team's own founding principle turned inward. The project already insists: *"a rule only counts if a check enforces it."* You've applied that to the work. The next step is to apply it to **the team itself**. Two sub-phases, in order:

- **Sub-phase A — the Eval/Regression Suite** (the verifier-for-the-verifier). *Prerequisite.*
- **Sub-phase B — a Measured Optimizer on top** (DSPy/GEPA against the suite). *Unlocked by A.*

### Why this, and why now

1. **It protects the gains you already made.** Right now every hard-won lesson (playwright binary, zero-test green, non-direct link, comp base-floor) is one careless prompt edit away from silently regressing, because nothing re-checks them. An eval suite makes each lesson a *frozen test* — edit a role freely, and you instantly see if you broke an old gate.
2. **It's the missing metric.** You can't improve what you can't score. The suite *is* the score. Once it exists, "is variant B of the verifier prompt better than A?" becomes an answerable, automatable question instead of a vibe.
3. **It is the safety prerequisite for everything more ambitious.** Letting the team rewrite its own roles (Oga self-improvement / ADAS-style) is *dangerous without this* — you'd have no way to catch a self-edit that quietly disables a gate. That is literally the Darwin-Gödel Machine's overseer-disabling incident. Build the regression suite first, then self-improvement becomes safe.

### Why not the other roadmap items first

- **Swap the Coder to OpenHands / SWE-agent** — worth doing, but it's a capability *swap* you can do anytime, in parallel. It isn't the bottleneck; manual, unguarded gate-improvement is.
- **Oga self-improvement (team rewrites itself)** — the highest-value end state, but unsafe until the regression suite exists (see #3). This phase is its prerequisite.
- **Tool-builder / Researcher roles** — capabilities, not the compounding core. They don't make the verifier measurably better.

---

## How to build it (assemble, don't invent)

### Sub-phase A — the Eval/Regression Suite

1. **Data model.** Create `loop-team/evals/`. Each case is a small JSON + fixture:
   ```
   { "id": "zero-test-green",
     "origin": "fix_plan: harness false-green",
     "type": "DOC | BEHAVIORAL",
     "target": "harness | verifier | test_writer | orchestrator",
     "fixture": "<path to a tiny project, OR an artifact+rubric to grade>",
     "expected": "PASS | FAIL | FALSE-PASS" }
   ```
2. **Seed it from `fix_plan.md`.** Turn the top holes into frozen cases — at minimum: zero-tests-collected green; playwright `import`-vs-binary (a `[BEHAVIORAL]` criterion that a `[DOC]` grep would wrongly pass); a non-direct link presented as direct; a weak/hard-coded test the Verifier must call FALSE-PASS; a wrong-spec criterion the Orchestrator should red-team. Each becomes a regression you never have to re-discover.
3. **Runner.** `loop-team/evals/run_evals.py` replays each case through the relevant role/harness and compares to `expected`, printing a scorecard: **caught / missed / false-pass-rate / regressions**. The zero-tests case is runnable against `verify.py` *today* — start there to prove the harness end-to-end.
4. **Use a real eval substrate, don't hand-roll metrics.** Wrap it in **DeepEval** ("pytest for LLMs," ships agentic + LLM-judge metrics) or **UK AISI Inspect**. Deterministic cases (the harness ones) are plain pytest fixtures. (Both are free, open-source.)
5. **Gate it.** Extend `hooks/loop_stop_guard.py` so that editing any role file or the harness **requires the eval suite to be green**. Your deterministic "something that can say no" now also says no to *gate regressions* — closing the exact gap that lets a careless edit undo a lesson.

### Sub-phase B — the Measured Optimizer

1. Pick **one** role to start — the **Verifier** (highest leverage; it's the heart).
2. Express its prompt as a **DSPy** module, or use **GEPA** (reflective prompt evolution; sample-efficient, optimizes prose prompts well). The **metric is the eval suite score** from Sub-phase A (maximize holes-caught, minimize false-passes — with a hard penalty for any regression).
3. Run the optimizer to propose improved role prompts; keep the variant that scores best on the suite.
4. **Human-review the diff before promoting**, and log the promotion to `fix_plan.md` (matches your provenance norms — versioned, reviewable, never a silent self-edit). This is the safe, measured version of self-improvement; full Oga-rewrites-the-team comes *after* this is trusted.

---

## Definition of done

- **A:** every significant `fix_plan.md` hole has a frozen eval case; `run_evals.py` prints a scorecard; editing a role or the harness without a green suite is **blocked by the hook**.
- **B:** at least one role prompt has been improved by the optimizer with a **measured gain on the suite and zero regression**, and the promotion was diff-reviewed and logged.

## Metrics to track (you already named these in fix_plan.md "Process upgrades")

caught-hole rate · false-pass rate · regressions-introduced · tokens-per-successful-task · intervention rate.

---

## Claude Code — starter steps

1. Read `~/Claude/loop/fix_plan.md`, the four role files in `~/Claude/loop/loop-team/roles/`, and `harness/verify.py`.
2. Scaffold `loop-team/evals/` + `run_evals.py`; convert the top ~8 `fix_plan.md` holes into cases (start with `zero-test-green` against `verify.py`).
3. Wire the regression gate into `hooks/loop_stop_guard.py`.
4. Then prototype a GEPA (or DSPy) optimizer over `roles/verifier.md` with the eval suite as the metric; show a measured improvement with no regression before promoting.

The throughline: you made the team good at refusing to fool *itself about a build*. This phase makes it refuse to fool *itself about itself* — and that's the unlock for everything after.
