# loop-engineering

A team of agents that builds software and **verifies its own work against an
objective signal** — then applies the same discipline to itself. You hand it a brief;
an orchestrator (Oga) drives plan-check → test-writer → coder → **independent
verifier** in enforced micro-steps until the work passes a real gate, with every rule
backed by a deterministic check that can say *no*.

> **Propose → verify → feed back → repeat. The loop is only as good as its verifier,
> and a rule only counts if a check enforces it.**

_Status as of 2026-07-02._

## What is built and verified (today, on this tree)

| Layer | What | Evidence |
|---|---|---|
| Build loop | Oga + Test-writer + Coder + independent Verifier + Researcher, plan-check gate before any code, failure arbiter before any re-dispatch | `loop-team/orchestrator.md`, `loop-team/TEAM_RELATIONS.md` |
| **Micro-step enforcement** | Five deterministic gates in Claude Code hooks (table below) + a shadow erosion gate | `hooks/`, 163-test hook suite |
| Deterministic harness | `verify.py` (zero-test runs force-fail; Node/vitest repos supported, dual-ecosystem results AND-ed), live-smoke URL checker with layer-classified verdicts, stall detector | `loop-team/harness/`, loop-team suite (518 passing / 7 skipped on a clean checkout at this stamp) |
| Verifier-for-the-verifier | Frozen regression cases (15/15 deterministic traps caught, incl. 2 erosion traps + a hard-good over-rejection guard), per-target case lint | `loop-team/evals/run_evals.py` → `SUITE: GREEN` |
| **Fault-injection ratchet** | 7-family deterministic injector over real run artifacts (gold = the injection log, never judge consensus), fail-closed PII sanitizer/emitter, 21-case blind batch (opaque ids), two-tier × two-round scoring with a completeness gate and an exhaustive decision table (control-accuracy preconditions, band agreement, min-n) | `loop-team/evals/fault_injection/` (113 tests incl. 43 adversarial); first live measurement: strong-tier 21.4% trap accuracy → suite audit confirmed 6 real verifier holes (count-reconciliation, target cross-refs) + 5 gold repairs queued |
| Honest acceptance | **PACE** anytime-valid commit gate (Monte-Carlo verified false-accept ≤ α); **MVVP** judge validation (chance-corrected κ, position-swap, test-retest); adversarial hard-case ratchet | `loop-team/evals/acceptor.py --selftest`, `judge_validate.py` |
| Execution grounding | Deterministic lanes that recompute facts in code — arithmetic checks, recorded-fetch contradiction routing, citation grounding (code owns evidence IDs), erosion metrics | `loop-team/evals/`, `hooks/slop_gate.py` |

### The five deterministic gates (the micro-step loop)

| Gate | Rule it enforces | On violation |
|---|---|---|
| Thrash-past-green | A green checkpoint is committed before any further coding can bury it | Stop blocked: "commit the green state" |
| Step-size | ≤ 200 changed code lines per micro-step | Stop blocked: commit (WIP if red) first |
| Retry-cap | Same failure signature never gets a third blind retry | Stop blocked: escalate to research |
| Testmon impact gate | The tests a change can break actually ran green; untested new modules can't slip through | Stop blocked: failing tests / orphan module |
| Dispatch hygiene | A Verifier is never primed with prior results or the coder's reasoning | Stop blocked: re-dispatch clean, spec by path |

The **slop gate** (SlopCodeBench-style erosion metrics on radon) runs in SHADOW mode —
it logs a verdict at every checkpoint but never blocks. Arming it is deliberately
deferred: threshold calibration on this repo's history is still degenerate (most
commit transitions have zero erosion delta), and a gate that false-blocks teaches
agents to route around gates. After 5–10 shadow runs, thresholds get fitted to
accepted transitions and arming becomes a measured, PACE-gated decision.

## Quickstart

See **[QUICKSTART.md](QUICKSTART.md)** — clone → run the harness on the shipped
example → install the five hooks (**[hooks/README.md](hooks/README.md)** has the full
`settings.json` block and per-hook verification) → watch a gate refuse an oversized
diff with your own eyes → first real run. The orchestrator entry point ships as
[skills/loop-team.SKILL.template.md](skills/loop-team.SKILL.template.md) +
[.loop-team-config.example](.loop-team-config.example).

**Other runtimes:** the playbooks and CLI tools run anywhere (OpenAI Codex CLI has
imported and used them — user report). Codex CLI, Gemini CLI, and Cursor now ship
Claude-style hooks, so the enforcement layer ports as adapters — the honest
per-runtime map, caveats, and effort-marked backlog live in
**[PORTABILITY.md](PORTABILITY.md)**.

## Lessons this project paid for (distilled)

1. **Verify the world, not the words.** An `import` check passed while the browser
   binary was missing; a documented URL 404'd silently. Execute the real thing.
2. **A green suite can prove nothing.** Zero-tests-collected once read as success;
   the harness now force-fails it.
3. **Fixture tautology.** Tests crafted to match a regex prove the regex matches the
   fixture. Fixtures must use the real labels/content the system produces.
4. **Citation fabrication is a capability problem.** A verifier invented GitHub issue
   numbers as "evidence." Code now owns evidence IDs; models only reference them.
5. **Over-rejection is an invocation artifact.** Terse forced verdicts over-reject;
   reasoning room fixes it. Both failure directions get graded.
6. **Text suites saturate.** Cases with incontestable gold are, by construction,
   reachable by a careful read — both model tiers hit the ceiling. Durable gains come
   from execution grounding, not harder prose.
7. **Blob-level checks must be specified against the real corpus they scan.** A
   leak-marker list matched the verifier role file's own output instructions —
   role-text subtraction fixed it.
8. **A detector must sweep its own home.** Marker literals kept reappearing in the
   detector's comments, tests, and docs — seven self-catches in one day. The sweep
   test is load-bearing.
9. **Pipes mask exit codes.** `pytest | tail` reported the pipe's success and a red
   suite got committed — twice. Gates now check exit codes unpiped.
10. **Same-second, same-size edits run stale bytecode.** Python's mtime+size pyc
    check let a broken function report "1 passed." The gates set
    `PYTHONDONTWRITEBYTECODE=1`.
11. **The published artifact is HEAD, not your working tree.** A freshness gate that
    grepped the filesystem would have waved through a stale committed README — the
    exact forgot-to-commit case it existed to catch.

## Future steps

- **Fault-injection round 2** — apply the audited gold repairs (5 traps + 1 control),
  re-measure with reason-grounded catch scoring, freeze the band placement, then point
  the prompt optimizer at the confirmed verifier holes (never hand-patch the prompt
  against the suite that measures it).
- **Reproduction-oracle lane** — a FAIL claim ships an executable repro or an
  explicit reproduction-impossible declaration (the strongest measured oracle signal).
- **Trajectory-check case family** — deterministic detection of
  destroyed-own-correct-patch failures from run traces.
- **Slop-gate arming** (after shadow calibration) and Stop-hook `additionalContext`
  upgrades (corrective feedback instead of bare blocks).
- **Worker swap** (Phase 2): a battle-tested coding agent behind the same verifier +
  eval suite, proven non-regressing before adoption.
- **Portability backlog** — pre-commit/CI package, per-runtime hook adapters and
  templates (see PORTABILITY.md).
- **Self-improvement (Phase 5) hard rules, decided in advance:** the rewritable set
  permanently excludes `verify.py`, the eval cases, the acceptor, and the hooks —
  enforced at the hook layer; role rewrites are never gated on LLM-attributed blame;
  acceptance uses an out-of-family judge or a deterministic gate.

## Reading path

`loop-team/orchestrator.md` (the method) → `loop-team/TEAM_RELATIONS.md` (who is told
what — and what is withheld) → `loop-team/roles/` (verifier.md is the heart) →
`loop-team/evals/README.md` (the measurement layer) → `hooks/README.md` (enforcement)
→ `PORTABILITY.md`. Private per-installation files (a fix_plan gate-hole log, personal
rubrics) are referenced with "skip if missing" semantics throughout — you start
without them and accrete your own.

## Publishing model

This public tree is a single-commit snapshot published by
`scripts/snapshot-publish.sh`: tracked-content-only (`git archive`), a fail-closed PII
gate, and a **README-freshness gate** — a push whose HEAD README stamp predates the
HEAD commit date aborts. What you read here is, enforced-by-construction, the state
it describes. License: MIT.
