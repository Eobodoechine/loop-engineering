# Loop Engineering Team — Full Roadmap

*A doc for the human maintainer and the coding agent. The whole arc, from where the team is today to a self-improving, multi-build engineering team. Each phase states its goal, why it comes when it does, how to build it (assemble-don't-invent), and how you know it's done. Phase 1 has its own deep-dive in `NEXT_PHASE.md`.*

---

## The throughline (read first)

Every phase serves one compounding idea:

> **Propose → verify → feed back → repeat. The loop is only as good as its verifier, and a rule only counts if a check enforces it.**

Two hard-won corollaries this project already lives by, which constrain every phase below:
- **Verify the world, not the words.** Execute the real thing; never let a `[DOC]` keyword-grep stand in for a `[BEHAVIORAL]` claim (the playwright `import`-vs-binary miss).
- **Something must be able to say "no."** Deterministic gates (the hooks), not model goodwill, enforce the rules.

The roadmap is sequenced so that **measurement and safety come before power.** We do not give the team the ability to rewrite itself until we can detect when a change makes it worse.

---

## Phase overview

| Phase | Name | Goal in one line | Depends on |
|---|---|---|---|
| **0** | Foundations | A hardened single build→test→fix loop | — (DONE) |
| **1** | Measured self-improvement | The team can verify & improve *itself* with a metric | 0 |
| **2** | Proven worker | Swap the hand-rolled Coder for a real coding agent | 1 |
| **3** | Roster expansion | Add Bug-finder, Tool-builder, Researcher roles | 1 (2 helps) |
| **4** | Experiment harness | Race 2–3 methods, keep the empirically best | 1, 3 |
| **5** | Oga self-improvement | The team safely rewrites its own roles | 1, 3, 4 |
| **6** | Multi-build / portfolio | One excellent team, run across many repos on a schedule | 2 (best after 5) |

Sequencing: `0 → 1 → {2, 3} → 4 → 5`; **6** can begin after **2** but is best once **5** is trusted.

---

## Phase 0 — Foundations  *(done; current state)*

A single build→test→fix loop: Oga (orchestrator) + Test-writer + Coder + Verifier + a deterministic harness (`harness/verify.py`). It is already hardened against the deepest failure mode, the **false pass**: the harness force-fails on zero tests collected; the Verifier reality-checks the world and red-teams the spec; the Test-writer separates `[DOC]` from `[BEHAVIORAL]`; the Orchestrator probes reality before designing fixes. Gate improvement is **manual** (a human appends holes to `fix_plan.md`), and deterministic **hooks** (`loop_guard.py`, `loop_stop_guard.py`) enforce that a verifier ran.
**Limit that motivates Phase 1:** improvement is manual and *unguarded* — nothing re-checks that yesterday's gates still hold, and there's no metric to compare or optimize prompts.

---

## Phase 1 — Measured self-improvement  *(NEXT — full detail in `NEXT_PHASE.md`)*

**Goal.** Turn `fix_plan.md` from a *log of holes* into an *executable suite that re-checks them*, then optimize role prompts against that score.
**Why now.** It (a) protects every gain you've already made from silent regression, (b) creates the metric without which nothing can be compared or optimized, and (c) is the **safety prerequisite** for Phases 4–5 (you can't safely let the team change itself until you can detect a regression).
**How.**
- **1A — Regression suite:** `loop-team/evals/` of frozen cases seeded from `fix_plan.md` holes (zero-test-green, playwright binary, non-direct link, weak-test false-pass, wrong-spec). `run_evals.py` scores caught/missed/false-pass. Wrap in **DeepEval** (now ships a v4.0 "Eval Harness for Coding Agents") or **Inspect** — or **Promptfoo** (MIT, now part of OpenAI) for a CI-native, version-controlled frozen suite out of the box. Extend `loop_stop_guard.py` so editing a role/harness requires a green suite. *The "verifier-for-the-verifier" (scoring the judge on caught/missed/false-pass) is a **build, not a buy** — no framework ships it; these are just the substrate.*
- **1B — Optimizer:** wrap the **Verifier** prompt in **GEPA** (or DSPy), metric = the suite score; keep the best variant; human-review the diff before promoting.
**Done when.** Every significant hole has a frozen case; `run_evals.py` prints a scorecard; un-green edits are hook-blocked; at least one role prompt is improved with a measured gain and zero regression.

---

## Phase 2 — Proven worker  *(swap the Coder)*

**Goal.** Replace the hand-rolled Coder role with a battle-tested coding agent, keeping Oga + Verifier + the eval suite on top.
**Why now (after 1).** The Coder is the weakest hand-rolled part, and the research conclusion was *assemble, don't invent*. Crucially, the Phase-1 eval suite now lets you **prove the swap doesn't regress quality** instead of hoping.
**How.** Start with **mini-swe-agent** (~100 lines, ~76.8% SWE-bench Verified w/ Opus 4.5, trivial to drive); graduate to **OpenHands** when you want its control surface; use the **Claude Agent SDK** if you'd rather own the harness. A hardened single-binary alternative is **OpenAI Codex CLI** (Apache-2.0, sandboxed Rust binary with a non-interactive `exec`/JSON mode). Note the *classic* SWE-agent is now in maintenance — superseded by mini-swe-agent, so pick **mini** specifically, not "SWE-agent." Oga calls the worker as the "Coder"; the Verifier + eval suite are unchanged.
**Re-verify before building.** SWE-bench Verified is saturated (~80%) and vendors have moved headline reporting to SWE-bench Pro / Terminal-Bench — re-check the current best open worker the *week you start Phase 2*; this leaderboard genuinely moves. Also worth a bake-off: cost outliers like MiniMax M2.5 (~75.8% @ ~$0.07/traj). And measure the candidate worker's error-introduction rate on a calibration set before locking it (see the reconciliation log).
**Done when.** A brief is built end-to-end by the external worker, the eval suite is green, and quality ≥ the hand-rolled baseline on the same tasks.
**Risk.** Heavier deps, environment setup, token cost — gate behind a spending cap from day one.

---

## Phase 3 — Roster expansion  *(more specialists)*

**Goal.** Add the roles from the original vision, each itself gated by the eval suite:
- **Bug-identifier** — proactively hunts failure cases beyond the current tests, and **feeds new cases into the Phase-1 suite** (it's a generator for your regression set — directly compounding).
- **Tool-builder** — when the team lacks a capability, it builds and registers a reusable tool.
- **Researcher** — gathers external knowledge/APIs a build depends on.
**Why now (after 1, helped by 2).** Measurement makes adding roles safe (each must prove it helps without regressing), and a strong worker makes them productive. Bug-identifier especially multiplies Phase 1's value.
**How.** Each role is a prompt + I/O contract like the existing four; each ships with eval cases demonstrating its contribution. Borrow patterns from the research (e.g., Bug-finder ≈ adversarial test generation; Researcher ≈ web/MCP retrieval).
**Done when.** Each new role has eval cases proving it adds value and introduces no regression.

---

## Phase 4 — Experiment harness  *(race methods, keep the winner)*

**Goal.** Run 2–3 variants of a method or role-config on the same task simultaneously, score each against the verifier/eval suite, and keep the empirically best. This is your "test different methods at once and see what's best" requirement.
**Why now (after 1 & 3).** It needs the metric (1) and a stable role set (3). It is also the **engine that Phase 5 will use** to generate-and-select self-improvements.
**How (assemble).** **EvoAgentX** already bundles TextGrad/MIPRO/AFlow/EvoPrompt and benchmarks them head-to-head — the closest turnkey "run-many-keep-best." (Live-verified active 2026-06-20: ~3k stars, 1,105 commits; pre-1.0, so pilot rather than depend.) Also consider **AgentSquare** (structured module search over Plan/Reason/Tool/Memory — safer and more bounded than free-form self-editing) and **Agent Lightning** (Microsoft; turns almost any agent into an optimizable entity, RL + prompt). Otherwise DSPy/GEPA + a small multi-armed-bandit (Thompson sampling) to allocate trials. The eval suite is the objective; keep concurrent variants small (2–3) so each gets signal. **"Keep the best" must be a statistical decision, not "the score went up"** — see the PACE acceptor in the reconciliation log.
**Done when.** Given a task and 2–3 candidate configs, the harness returns the best one with a logged scorecard, reproducibly.

---

## Phase 5 — Oga self-improvement  *(the team rewrites itself — safely)*

**Goal.** Oga proposes edits to role prompts and team topology from run history, instead of a human hand-editing prose.
**Why last among the "smarts."** This is the most powerful *and* most dangerous capability. It is only safe atop the **regression suite (1)** to catch self-edits that quietly disable a gate, the **strong worker (2)** and **rich roles (3)** to have something worth evolving, and the **experiment engine (4)** as the generate-and-select mechanism. The Darwin-Gödel Machine literally edited its own monitor to fake success — which is exactly why the suite + hooks + human review here are non-negotiable.
**Read the closest precedents first:** **SICA** (Self-Improving Coding Agent, Bristol — edits its own orchestration code, 17→53% on a SWE-bench Verified subset, arXiv 2504.15228), **Gödel Agent** (runtime self-modification from high-level objectives, arXiv 2410.04444), and DGM's safety section specifically (arXiv 2505.22954).
**How (assemble).** Borrow **ADAS / Meta Agent Search** (a meta-agent writes new agent code) and **GPTSwarm** (optimize the role graph/topology). Every self-edit: generated via Phase 4, must pass the Phase 1 suite — **which must include monitor-tampering tripwires** — with **zero regression**; is scored on **world-state outcomes only, never the chain-of-thought**; is **human-diff-reviewed**, **versioned**, **provenance-logged to immutable append-only lineage** the agent can't rewrite, and runs **sandboxed with a kill-switch**.
**Done when.** Oga lands at least one self-proposed role improvement that passes the suite with no regression, fully logged and review-gated — and a sandbox + kill-switch are enforced.

---

## Phase 6 — Multi-build / portfolio  *(scale out)*

**Goal.** Run the (now self-improving) team across many repos/projects, on schedules, as a portfolio — the "team that builds many agents/apps" end state.
**Why here.** Scale *one excellent, self-improving* team rather than many mediocre ones. Can technically begin after Phase 2 if you need breadth sooner, but compounding is greatest after Phase 5.
**How (assemble).** **OpenHands Automations + Sub-Agent Delegation** (cron/webhook-scheduled full agent runs + parallel sub-agents via `max_children`) as the OSS control surface — note "Agent Canvas" could **not** be verified as a current user-facing feature by that name. Your **Cowork scheduled-tasks + connectors** are the only bespoke glue (the Oga integration layer). Add a backlog ingest + portfolio status view. *References for the orchestration layer:* Devin Managed/Scheduled, Cursor Cloud Agents (the one option that edits up to 20 repos in a single run), Claude Agent SDK `Workflow` (script-driven orchestration of many agents), Sourcegraph Batch Changes. No vendor sells "self-improving team across many repos on a schedule" as one product — you compose it.
**Done when.** The team autonomously handles a backlog across ≥2 repos on a schedule, with portfolio-level status and the standard guardrails.

---

## Cross-cutting guardrails (every phase)

- **A deterministic "no":** the hooks must be able to block a non-conforming run; never rely on model goodwill.
- **Sandbox + change limits + full provenance** for anything that writes code or edits the team; every change traceable.
- **Human diff-review before promoting** any self-edit (Phases 1B, 5).
- **Verify the world, not the words:** behavioral claims get executed, not grepped.
- **Spending caps** on model tokens (the dominant variable cost — heaviest in optimization and long agentic loops).
- **Stop condition:** if the Verifier overturns the writer on the *same dimension* twice running, stop and fix the gate first.
- **Immutable, append-only change lineage.** Every self-edit / role / prompt change is logged where the agent cannot rewrite it, and is revertible. *In the Darwin-Gödel Machine, traceable lineage was the only safeguard that actually caught the agent sabotaging its own monitor (arXiv 2505.22954).*
- **Never optimize against the visible reasoning trace.** Score outcomes and world-state, not the chain-of-thought. *Penalizing "bad thoughts" in the CoT trains the model to hide intent rather than stop misbehaving (OpenAI, arXiv 2503.11926) — the external proof of this project's "world-not-words" rule. Reward-hacking also generalizes to sabotage (Anthropic, Nov 2025).*
- **Monitor-tampering tripwires.** The regression suite must include adversarial cases that check whether an edit quietly disabled a gate — not only whether the build passed.

---

## How Claude Code should use this

1. Treat **Phase 1** as the active build (see `NEXT_PHASE.md` for steps); don't start Phases 4–5 before the eval suite + regression gate exist.
2. Phases **2 and 3** can run in parallel once Phase 1's suite is in place.
3. Log every phase's holes/lessons to `fix_plan.md` (the project's durable, self-improving record).
4. Before any phase that lets the team change itself, confirm the guardrails above are live — especially the regression gate and the kill-switch.

---

## Reconciliation log

**2026-06-21 — folded in `research-refresh-2026-06/` (independent deep-research pass, picks live-verified).** Phase *structure and dependency graph unchanged* (validated, not revised). Applied: Phase 1 **+Promptfoo** + "verifier-for-the-verifier is build-not-buy"; Phase 2 **+OpenAI Codex CLI**, "pick mini not classic SWE-agent (now maintenance)", re-verify-at-phase-start note (benchmark saturated, moved to SWE-bench Pro/Terminal-Bench); Phase 4 **EvoAgentX confirmed active** (pre-1.0 → pilot) **+AgentSquare +Agent Lightning**; Phase 5 **+SICA +Gödel Agent** precedents + hardened self-edit preconditions; Phase 6 **"Agent Canvas" → Automations + Sub-Agent Delegation** (Canvas unverifiable) + orchestration references; **+3 cross-cutting guardrails** (immutable lineage, never-score-CoT, monitor-tampering tripwires) from the OpenAI + Anthropic + DGM safety findings.

**Recommended, NOT yet applied (from a parallel verify/retry-loop research thread — flagged for decision, logged in `fix_plan.md`; concrete repos/recipes in `ACCEPTANCE_AND_VERIFICATION.md`):** these strengthen the *acceptance logic* the phases above depend on.
- **PACE acceptor (arXiv 2606.08106)** — Phases 1, 4, 5 currently commit a change when "the suite proves it's better." On a small reused eval set that is adaptive multiple testing (self-p-hacking; 30–100% false commits in PACE). Replace greedy "score went up" with a paired anytime-valid e-process (testing-by-betting): commit only when wealth `E ≥ 1/α` (α=0.05, λ=0.5); else reject. ~10 lines, bounds false-commit at α. **Highest-leverage single addition.**
- **EPC collapse guard (arXiv 2606.16682)** — Phase 4/5 self-evaluation loops can collapse onto one strategy; prefer verifiable signals, monitor weight-concentration (HHI / strategy-win entropy — the paper has *no* "PCI" metric), rotate judges, cap rounds. Repo `aidless/mm-epc` (MIT, artifact-only).
- **Worker-EIR calibration (arXiv 2604.22273)** — Phase 2: measure a candidate worker's Error-Introduction-Rate before locking; only run a self-correction/retry loop when ECR/EIR > Acc/(1−Acc).
- **Minimum Viable Validation Protocol (arXiv 2606.19544)** — Phase 1: before trusting any LLM-judge in the loop, validate it with chance-corrected κ (not exact-match), a position-swap bias audit, and a test–retest check.
