# Loop Team

A reusable team of agents that builds things — apps, agents, skills, modules — and verifies its own work against an objective signal. You hand it a **Brief**; **Oga** (the orchestrator) drives a build-test-fix loop with specialist sub-agents until the work passes a real verifier.

The build loop and its **measurement layer are built and exercised** (Phase 0 + most of Phase 1): an independent two-layer verifier, a frozen regression suite, an anytime-valid acceptance gate (PACE), an MVVP-validated judge, and an adversarial hard-case ratchet. The roles that let the team *rewrite itself* (Tool-builder, Bug-identifier, Oga self-improvement) and *swap in a stronger external coder* are designed-for but **not yet built** — see the roadmap.

## The idea in one line

> Propose → verify → feed back → repeat. The loop is only as good as its verifier, so the verifier is the heart of the system.

## How it works

```
Brief ──▶ Oga (orchestrator)
            │  1. plan + spec  → plan-check Verifier (must emit LOOP_GATE: PLAN_PASS)
            │  2. Test-writer        ─▶ executable tests, each [DOC] or [BEHAVIORAL]
            │  3. Coder              ─▶ minimal implementation + a withheld Decision Log
            │  4. harness/verify.py  ─▶ {passed, runner, output}   (0 tests = forced fail)
            │  5. if fail → errors back to Coder, repeat (max 6 iters);
            │              stall_detector → Researcher (Mode B) for one informed retry
            │  5.5 Adversarial Test-writer ─▶ property/mutation tests (if any [BEHAVIORAL])
            │  6. Verifier judgment check (de-primed): meets the brief's intent, not just tests?
            │  6.5 Live-smoke: open every URL / run every command through the real path
            │  6.6 Deployment gate: confirm the artifact is actually installed & invocable
            ▼
        run log in runs/<timestamp>/  +  lessons → learnings.md  +  working, tested code
```

The **verifier is split in two**: a deterministic harness (`harness/verify.py`, runs the tests/build — cheap and impossible to argue with) and a judgment agent (`roles/verifier.md`, catches what tests miss, like test-gaming). That two-layer design is deliberate — a green test suite over weak tests is a *false pass*, and the judgment layer exists to catch exactly that. The Verifier never sees the Coder's Decision Log or the green verdict until it commits its own — independence is engineered, not hoped.

## The roster (built)

| Role | What it does |
|---|---|
| `orchestrator.md` (Oga) | Drives the loop; may only dispatch sub-agents, synthesize, or ask — never writes code itself |
| `roles/test_writer.md` | Turns acceptance criteria into executable tests; labels each `[DOC]` vs `[BEHAVIORAL]` |
| `roles/adversarial_test_writer.md` | Attacks a passing implementation from the code (10-category taxonomy, property/mutation tests) |
| `roles/coder.md` | Writes minimal code; may never edit/weaken a test; emits a Decision Log (withheld from the Verifier) |
| `roles/verifier.md` | Deterministic + judgment, calibrated against both false-pass and false-rejection |
| `roles/gold_judge.md` | Independent fact/arithmetic judge for the meta-verification layer (distinct model) |
| `roles/live_smoke.md` | Real-browser liveness check for external-touching artifacts (DEAD vs bot-walled) |
| `roles/researcher.md` | Four modes: loop-improvement radar / Coder-unblock / adversarial eval cases / domain research |

**Not yet built:** Tool-builder, Bug-identifier, and Oga self-improvement (the team rewriting its own roles).

## The measurement layer (built — the load-bearing part)

`evals/` is the "verifier-for-the-verifier": every hard-won gate-hole is frozen as a regression case the suite re-checks.

- `evals/run_evals.py` — scorecard runner (caught / missed / false-pass / regression); GREEN only with ≥1 runnable case and zero misses/regressions.
- `evals/verify_build.py` — Layer-1, zero-API meta-verifier (case lint, gold-leak/PII checks, and `operational_invariants()` that fails the build if a live LLM call isn't retry-wrapped or a `subprocess.run` lacks a timeout).
- `evals/acceptor.py` — **PACE**, an anytime-valid testing-by-betting gate: commit a change only when the e-process clears `1/α`, not when "the score went up" (which p-hacks itself over many rounds). Monte-Carlo verified false-accept ≤ α.
- `evals/judge_validate.py` + `meta_validate.py` — **MVVP** judge validation on incontestable objective-fact gold (chance-corrected Cohen's κ, Gwet's AC1, position-swap flip, test-retest). On objective gold, **Haiku certified** (κ 0.769 / retest 1.0 / flip 0.0); Sonnet was *not* certified (the swap audit caught a position-bias its forward score hid).
- `evals/adversarial_loop.py` — the ratchet: keeps a generated case only if `gold_confirmed AND verifier_wrong` (hard by construction).
- `evals/arithmetic_check.py` + `recorded_fetch_check.py` — deterministic execution lanes: code recomputes the number / checks the recorded snapshot and routes a provable contradiction to FALSE-PASS without consulting the LLM.
- `evals/replay_judge.py` + `JUDGE_ADAPTER_SUBAGENT.md` — a free ($0) subscription judge path; a cross-family OpenAI judge is wired for true model-independence.
- `optimize/` — a PACE-gated reflective optimizer for the Verifier prompt (writes numbered proposals; never auto-promotes). `experiments/` races prompt variants and keeps the statistically-best.

**Honest status:** the suite is currently **saturated** — a 2026-06-23 hard-case hunt found that both Sonnet and Haiku judge every compound trap correctly, and two prompt A/Bs (RRD rubric, answer-block format) PACE-*rejected* for lack of measurable gain. The finding is structural: *a case with incontestable objective gold is, by construction, reachable by a careful read*. So the next gains come from **execution grounding** and **cross-family disagreement**, not harder text prompts (see `cases/hard/README.md`).

## File map

| Path | What it is |
|---|---|
| `orchestrator.md`, `roles/` | Oga + the eight built role briefs |
| `harness/verify.py` | Deterministic test/build runner → JSON verdict. No deps. Python + Node. Forces a fail on 0 tests collected |
| `harness/live_smoke.py`, `stall_detector.py`, `linear_reporter.py` | Real-URL liveness, objective stuck-detection, optional Linear reporting |
| `harness/dashboard.py` | Renders every run (logs + `trace.jsonl`) into a self-contained HTML status page: pass rate, adversarial bugs caught, plan-check rounds, per-run trace |
| `harness/log.py` | Shared structured logger: leveled JSON-line records to `<run_dir>/log.jsonl` (flush+fsync, crash-safe) + stderr by level, never stdout, never raises; `structlog` backend with a stdlib fallback; `bind_context(run_id, role)` for run/role correlation; wired into `live_smoke`, `verify_build`, and the runner |
| `runner/run_trace.py` | Per-run event trace (`trace.jsonl`) + atomic `checkpoint.json` + `resume()`; the runner emits these when `run(brief, run_dir=...)` is given a dir |
| `evals/` | The regression suite, PACE acceptor, MVVP judge validation, adversarial ratchet, deterministic lanes, cases |
| `optimize/`, `experiments/` | The measured optimizer seam + the A/B experiment harness |
| `briefs/EXAMPLE_brief.md` | Brief template — copy, fill, hand to Oga |
| `examples/duration_parser/` | A working sample build used to smoke-test the harness |
| `runs/` | Per-build logs (brief, spec, iterations, verdicts) |
| `../hooks/` | Deterministic Claude Code gates (loop_stop_guard, pre_tool_use_oga_guard, subagent_stop_gate); wired via `~/.claude/settings.json` |

## Structured logging

Modules log through one shared, stdlib-first logger (`harness/log.py`). `get_logger(name, run_dir=...)` returns a logger whose `.debug/.info/.warning/.error/.critical(msg, **fields)` calls each emit **one JSON line** — `{ts, level, logger, msg, **fields}` — to `<run_dir>/log.jsonl` (flush+fsync per line, crash-safe in the same posture as `trace.jsonl`) and to stderr filtered by level. It **never writes stdout** (so machine-readable tool output like `live_smoke`'s JSON and `verify_build`'s report stays clean) and **never raises** (an unwritable path or an unserializable field degrades silently). `bind_context(run_id=..., role=...)` attaches correlation fields to every subsequent line, isolated across threads and async tasks.

When `structlog` is installed it drives the emit chain (processor pipeline + contextvars); otherwise the module falls back to a stdlib-only path with the identical public surface — so it is a recommended, not required, dependency. It is wired into `live_smoke`, `verify_build`, and the runner so failures log by level and persist per run alongside `trace.jsonl`. The choice of a stdlib core over a hard `structlog` dependency is measured, not assumed: a PACE-gated A/B (`experiments/exp1_logging/`) found structlog gave no correctness edge on run/role correlation, so the stdlib path stands as the default and structlog rides on top when present.

## Run the verifier yourself

```bash
python loop-team/harness/verify.py loop-team/examples/duration_parser
# → {"passed": true, "runner": "pytest", ...}

python3 loop-team/evals/run_evals.py        # the regression scorecard → SUITE: GREEN
python3 loop-team/evals/acceptor.py --selftest   # PACE false-accept ≤ α
```

`verify.py` auto-detects the runner: **pytest** (falls back to `unittest discover`) for Python, **`npm test`** for Node. It always prints a JSON object and exits 0 (pass) / 1 (fail), so the loop can read the result programmatically.

## Running the full test suite (no skips)

Two tests skip when their optional dependency (or, for the browser test, a launchable browser) is missing. Install the dev deps and the chromium runtime to run everything green:

```bash
pip install -r loop-team/requirements-dev.txt
python3 -m playwright install chromium                 # browser binary for the live-smoke test
# headless Linux / CI also needs the system libs:
python3 -m playwright install --with-deps chromium
```

Then run the suite:

```bash
cd loop-team && python3 -m pytest -q -rs
```

Notes:

- **`evals/test_judge_validate.py`** needs **scikit-learn** (it cross-checks `judge_validate.cohen_kappa` against `sklearn.metrics.cohen_kappa_score`). Without it the suite skips; with it, all 16 cases run.
- **`harness/test_live_smoke.py` (the `Behavioral` test)** needs **playwright *and* a working chromium runtime**. It is execution-based, not import-based: it actually launches chromium against a live URL. In a **headless sandbox without browser system libs it legitimately SKIPS as `LAUNCH_FAILED`** — by design, it refuses to false-pass when it cannot truly launch a browser. On macOS / a dev machine with `playwright install chromium` done, it runs green.
- **structlog is optional at runtime, and its backend tests skip without it.** `harness/log.py` prefers it as the logging backend but falls back to a stdlib-only path if it is absent — installing it is recommended, not required. `harness/test_log_structlog.py` (the structlog-backend tests) SKIPS as a module when structlog is not installed; the stdlib fallback path is fully covered by `harness/test_log.py`, which always runs.
- **opentelemetry is optional (experimental).** `experiments/exp2_phoenix/` is the only consumer; its tests SKIP cleanly when `opentelemetry` is not installed (see the commented line in `requirements-dev.txt`).

## How to start a build

1. Copy `briefs/EXAMPLE_brief.md`, fill in `goal`, `acceptance_criteria`, `target` (existing repo *or* new project), and `constraints`.
2. Hand the brief to Oga (in a Cowork session: ask Claude to "run the Loop Team on this brief" and follow `orchestrator.md`; sub-agents are spawned via the Agent tool).
3. Oga loops until the harness is green, the judgment check passes, live-smoke is clean, and the deployment gate confirms the artifact is invocable — then writes a run log and reports.

It works on **existing repos** (Oga reads first, works on a branch/copy) and **new projects** (scaffolds from scratch).

## Design choices (why it's built this way)

- **Hybrid foundation.** Native orchestration (runs in your Cowork/subagent world, schedulable like your existing pipelines) driving a real code-execution verifier. A clean seam exists to delegate heavy code work to a stronger coding-agent base (mini-swe-agent / OpenHands / Claude Agent SDK) later — the Phase-2 worker swap.
- **Tests as the verifier.** Because "do the tests pass" is the cheapest, hardest-to-fake oracle available — the same reason coding agents are the most reliable family of self-improving systems.
- **Anti-gaming is a first-class rule.** The Coder may never weaken tests; the Verifier actively hunts for false passes; the harness force-fails on zero tests collected. Reward hacking is the field's deepest failure mode, so it's guarded at the role *and* the code level.
- **Honest acceptance.** Adoption of any self-improvement is gated by PACE (an anytime-valid e-process) + human diff-review — never by a raw score going up.

## Roadmap (full detail in `ROADMAP.md`)

Phase 0 (hardened build loop) and most of Phase 1 (measured self-improvement: regression suite + PACE + MVVP judge + adversarial ratchet) are **built**. What remains:

1. **Finish Phase 1's measurable headroom** — the suite saturates, so grow what the verifier can *check* (execution-grounded lanes) and mine **cross-family judge disagreements** for genuinely hard cases, rather than generating harder text puzzles (proven to saturate).
2. **Phase 2 — Proven worker** — swap the hand-rolled Coder for a battle-tested agent (mini-swe-agent first), behind the eval suite that can prove no regression, with a sandbox + spending cap.
3. **Phase 3 — Roster expansion** — Bug-identifier (feeds the suite), Tool-builder, plus the already-built Researcher.
4. **Phase 4 — Experiment harness** — race 2–3 methods, keep the statistically-best (the `experiments/` seam exists).
5. **Phase 5 — Oga self-improvement** — the team proposes edits to its own roles, gated by everything above plus monitor-tampering tripwires and immutable lineage.
6. **Phase 6 — Multi-build / portfolio** — run the team across many repos on a schedule.
