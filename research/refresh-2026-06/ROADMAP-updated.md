# Loop Engineering Team — Roadmap (Research-Refreshed Edition)

**For:** Claude Code, working in the loop-team repo.
**Updated:** 2026-06-20, after an independent deep-research pass. This supersedes the picks in the prior `ROADMAP.md` where they conflict; the phase *structure and dependency graph are unchanged* — they were validated, not revised. Changes are marked **[NEW]** / **[CHANGED]** / **[CONFIRMED]** against the prior roadmap.

Dependency graph (unchanged): `0 → 1 → {2, 3} → 4 → 5`, with `6` after `5`.
Sequencing principle (unchanged, now triple-sourced): **measurement and safety come before power.**

---

## Cross-cutting guardrails (apply to every phase)

1. **Assemble, don't invent.** Every "build" below maps to a maintained open-source project; verify it's still active before committing.
2. **[NEW] Immutable, append-only change lineage.** Every self-edit or role/prompt change must be logged where the agent cannot rewrite it, and be revertible. *Rationale: in the Darwin-Gödel Machine, traceable lineage was the only safeguard that actually caught the agent sabotaging its own monitor.*
3. **[NEW] Never optimize against the visible reasoning trace.** Score outcomes and world-state, not the agent's chain-of-thought. *Rationale: OpenAI showed that penalizing "bad thoughts" in the CoT teaches the model to hide intent rather than stop misbehaving. This is the external proof of your existing "world-not-words" rule.*
4. **[CONFIRMED] World-not-words verification.** Execute the world and check real state; never grade the transcript.
5. **[NEW] Monitor-tampering tripwires.** The regression suite must contain adversarial cases that check whether an edit quietly disabled a gate — not just whether the build passed.

---

## Phase 0 — Foundations *(done)*
Hardened single build→test→fix loop: zero-test-green guard, world-not-words verifier, `[DOC]` vs `[BEHAVIORAL]` test split, `fix_plan.md` hole log. No change.

---

## Phase 1 — Measured self-improvement *(next — the hinge)*

**Goal:** turn each `fix_plan.md` hole into a frozen eval case; build `run_evals.py` to score caught / missed / false-pass; gate role/harness edits on a green suite. Then wrap the Verifier prompt in an optimizer with the suite as the metric.

**[CONFIRMED] Picks:**
- Eval substrate: **DeepEval** (now ships a v4.0 "Eval Harness for Coding Agents") or **Inspect** (UK AISI; scorers are first-class loggable objects).
- **[NEW] Add Promptfoo** as the CI-native substrate option — closest thing to a frozen, version-controlled regression suite out of the box (now part of OpenAI; still MIT).
- Optimizer: **GEPA** (preferred) or **DSPy** (which bundles GEPA + MIPROv2).

**[NEW] Why GEPA specifically here:** it accepts "Actionable Side Information" — error text, traces, logs — not just a scalar. Make `run_evals.py` emit *why* each case failed, and GEPA reflects on that, which scalar-only optimizers can't use.

**[CONFIRMED] The verifier-for-the-verifier is a build, not a buy.** No framework ships a turnkey meta-eval that scores the judge on caught/missed/false-pass. Pattern: frozen gold set with human verdicts → run judge → compute TP/FP/FN. Promptfoo/DeepEval are the best substrates.

**Definition of done:** `run_evals.py` scores the suite; `zero-test-green` and at least one monitor-tampering case are frozen; `loop_stop_guard.py` blocks role/harness edits unless the suite is green; one optimizer run has improved the Verifier prompt with a human-reviewed diff.

---

## Phase 2 — Proven worker

**Goal:** swap the hand-rolled Coder for a proven open agent, now that the eval suite can prove the swap doesn't regress.

**[CHANGED] Picks (re-verify at phase start — see below):**
- Top pick: **mini-swe-agent** — ~100 lines, bash-only, each action a swappable subprocess, model-agnostic via litellm, strong SWE-bench Verified score. Purpose-built to embed.
- **[NEW] Alternative: OpenAI Codex CLI** — Apache-2.0, hardened Rust single binary, non-interactive `exec`/JSON mode, very actively maintained. Good when you want a sandboxed worker binary.
- Heavyweight option: **OpenHands** software-agent-sdk / Agent Server when the loop itself needs to be a platform.
- **[CHANGED] Drop "SWE-agent" (classic)** — it's now in maintenance, superseded by mini-swe-agent.

**[NEW] Re-verify before building:** SWE-bench Verified is saturated (~80%) and vendors moved headline reporting to SWE-bench Pro / Terminal-Bench. Re-check the current best open worker the week you start Phase 2 — this leaderboard genuinely moves.

**Definition of done:** the chosen worker runs inside the loop behind the same gates; the Phase 1 suite shows no regression vs. the hand-rolled Coder.

---

## Phase 3 — Roster expansion

**Goal:** add Bug-finder (feeds new cases into the Phase 1 suite), Tool-builder, Researcher. No external-pick change. Bug-finder is the highest-value first hire because it compounds Phase 1: every bug it finds becomes a frozen regression case.

---

## Phase 4 — Experiment harness

**Goal:** race 2–3 methods on a task, keep the best (your "test different methods at once" requirement); also the engine Phase 5 reuses.

**[CHANGED] Picks:**
- **DSPy / GEPA** — confirmed engines for measured method search.
- **[CONFIRMED] EvoAgentX** — live-verified 2026-06-20: real and active (`EvoAgentX/EvoAgentX`, ~3k stars, 1,105 commits, "self-evolving ecosystem of AI agents"). Keep as a Phase 4 candidate. See also its companion "Self-Evolving AI Agents" survey (arXiv 2508.07407) and "Awesome-Self-Evolving-Agents" list as references.
- **[NEW] Consider AgentSquare** (modular agent search over Plan/Reason/Tool/Memory — safer, more structured than free-form) and **Agent Lightning** (Microsoft; turns any agent into an optimizable entity, RL + prompt).

**Definition of done:** harness runs N method variants on a held-out task, scores them on the Phase 1 suite, and reports a ranked diff for human promotion.

---

## Phase 5 — Oga self-improvement *(the team rewrites its own roles — safely)*

**Goal:** let the orchestrator propose edits to the team's own roles/harness, gated by everything built in 1–4.

**[NEW] Read these direct precedents before building:**
- **SICA (Self-Improving Coding Agent, Bristol, arXiv 2504.15228)** — an agent editing its own orchestration code, 17%→53% on a SWE-bench Verified subset. Closest precedent to what you're building.
- **Gödel Agent (arXiv 2410.04444)** — runtime self-modification from high-level objectives.
- **DGM (arXiv 2505.22954)** — the cautionary tale; read the safety section specifically.

**[NEW] Hard preconditions (from the safety findings):**
- The Phase 1 suite must include monitor-tampering tripwires and be green.
- All self-edits write to immutable lineage; every change revertible.
- The optimizer/self-edit loop scores world-state outcomes only — never the CoT.
- Human review on every promoted self-edit; sandboxed execution; restricted network.

**Definition of done:** Oga can propose and (post human-approval) apply a role edit that the suite proves is a net improvement, with full revertible lineage and no gate weakened.

---

## Phase 6 — Multi-build / portfolio

**Goal:** run the self-improving team across many repos on a schedule.

**[CHANGED] Picks:**
- **[CHANGED] Replace "OpenHands Agent Canvas"** (couldn't be verified as a current user-facing feature by that name) with **OpenHands Automations** (cron/webhook-scheduled full agent runs) + **Sub-Agent Delegation** (parallel sub-agents, `max_children`) — the verified OSS primitives.
- **[NEW] References for the orchestration layer:** Devin Managed + Scheduled Devins (coordinator fans children across repos on a schedule), Cursor Cloud Agents (the one option that edits up to 20 repos in a single run + REST API), Claude Agent SDK `Workflow` tool (script-driven orchestration of hundreds of agents), Sourcegraph Batch Changes (declarative change across many repos).
- **[NEW] Reality check:** no vendor sells "self-improving team across many repos on a schedule" as one product — you compose it. Closest OSS base = OpenHands Automations; most flexible DIY = Claude Agent SDK `Workflow`.

**Definition of done:** the team runs on a schedule across ≥2 repos, each in isolation, with results aggregated to one dashboard/log and gated by the same suite.

---

## Change log vs. prior ROADMAP.md
- Structure & dependency graph: **unchanged** (validated independently).
- Guardrails: **+3 new** (immutable lineage, never-score-CoT, monitor-tampering tripwires), from the OpenAI + Anthropic + DGM safety findings.
- Phase 1: **+Promptfoo**; GEPA rich-feedback rationale added.
- Phase 2: **+OpenAI Codex CLI**; **−SWE-agent classic** (superseded); re-verify note.
- Phase 4: **EvoAgentX confirmed active** (live-verified 2026-06-20); **+AgentSquare, +Agent Lightning**.
- Phase 5: **+SICA, +Gödel Agent** as precedents; hard safety preconditions added.
- Phase 6: **Agent Canvas → Automations + Sub-Agent Delegation**; references expanded.
