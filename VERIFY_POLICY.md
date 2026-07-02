# Verification-resilience policy (don't let a flaky API become an hour-long spin)

This codifies HOW the independent-verifier step runs, so a transient infrastructure
error never again causes open-ended retries. It exists because a `529 Overloaded`
storm once met five blind retries and burned **~1h17m / ~290k tokens** before a
fallback was tried. That violated the loop's own rule (`RUN.md`: *"BUDGET = hard
enforcement, not alerts. Terminate/pause at a ceiling."*) and is exactly the
"same failure signature recurring = stuck" condition `harness/stall_detector.py`
already models — here applied to **infra errors**, not code bugs.

Core idea: **two layers, and only the cheap one is load-bearing.**

## Layer 1 — deterministic, always run FIRST (cannot 529)
Run `python3 loop-team/evals/verify_build.py` before spawning any judgment
sub-agent. It needs ZERO API and gives most of the signal: full pytest sweep,
`run_evals` GREEN, case lint (valid JSON / required fields / no answer-leakage /
no PII / trap-good balance), and red-team probes on the keep-logic. If Layer 1
fails, the build is not done — fix it; do not bother the judgment layer yet.

Because Layer 1 always produces signal, a blocked judgment sub-agent can NEVER
again block *all* verification — which removes the pressure that caused the spin.

## Layer 2 — the agentic judgment verifier (bounded, degradable, never spins)
For what only a model can do (adaptive red-teaming, ruling on judgment calls),
spawn an INDEPENDENT verifier sub-agent (a model DIFFERENT from the writer, fresh
context, sees only artifact + rubric). Apply this ladder, with hard ceilings:

1. **Spawn once** on the preferred independent model.
2. On a **transient infra error** (`429 / 500 / 502 / 503 / 529 / Overloaded /
   timeout / connection`): at most **2 retries**, short backoff. Not five. Not an hour.
3. Still failing → **one** model-fallback spawn (e.g. a different tier). State the
   result as **PARTIAL independence** and log which model produced it.
4. Still failing → **STOP and surface to the human**: report the Layer-1 result +
   "judgment layer blocked on infra," and defer or let the human choose. **Never spin.**
5. **Hard ceilings (the circuit-breaker):** ≤ **4 total** Layer-2 attempts AND a
   wall-clock/token budget for the verify step (stop after ~10 min or a fixed token
   cap spent on retries) — whichever comes first. A transient error is *infra*, not
   a defect; treat repetition as "stuck," not "try harder."

A non-transient error (a real bug in the build, a failed assertion) is NOT
retried — it routes straight back to the writer.

## Our own live LLM calls (meta_validate / adversarial_loop / optimize)
Every live `messages.create` goes through `optimize/llm.call_with_retry`: bounded
exponential backoff + jitter on transient errors, capped by attempts AND a
total-time budget, then a clear `RuntimeError("infra unavailable …")`. The
Anthropic client is created with `max_retries=0` so this wrapper is the single,
predictable source of retry behavior. Same principle as Layer 2, enforced in code.

## What's check-enforced vs discipline-enforced (be honest about the gap)
The project's rule is "a rule only counts if a check enforces it" — so be explicit
about which rungs above are CODE-enforced and which are JUDGMENT:
- **Code-enforced (a check can say no):** Layer 1 (`verify_build.py`, runs or it
  doesn't); `call_with_retry`'s bounded retries on our own live calls; and the
  `operational_invariants()` check in `verify_build.py`, which FAILS the build if
  any live `messages.create` isn't wrapped in `call_with_retry`, any
  `anthropic.Anthropic(` lacks `max_retries=0`, or any `subprocess.run(` lacks a
  `timeout=`. A future unwrapped call or unbounded subprocess is caught automatically.
- **Discipline-enforced only (no check can cover it):** the *sub-agent* retry cap
  (≤2 → fallback → STOP). How the orchestrating MODEL decides to spawn/retry a
  sub-agent is in-context judgment a script can't observe. We do NOT pretend a test
  covers this — the code-enforced backstops (Layer 1 always gives signal;
  `call_with_retry` bounds our own calls) exist precisely so this judgment rung is
  not load-bearing alone.

## Operational incidents become frozen regressions too (extend the flywheel)
The project's flywheel is "real work → real holes → real cases," but historically
only *correctness* holes were ever frozen as eval cases; the 529 storm showed
*operational* failures (cost / time / infra / degradation) had no tested home and
so recurred unbounded. Rule going forward: **any real incident — operational OR
correctness — gets frozen as a regression** (an `operational_invariants()` rule or
an eval case), not merely logged in `fix_plan.md`. Operational resilience is a
first-class tested category, not an afterthought.

## One-line summary
Always have deterministic signal (Layer 1); bound, degrade, then STOP the live
judgment layer (Layer 2) — never an open-ended retry against an overloaded API.
Enforce what code can (`operational_invariants()`), and be honest about the one
rung only discipline can hold.
