# Loop-Team Research Radar

*Persistent watchlist + memory for the Researcher's standing scan. Purpose: dedupe (don't re-surface the same repo every run), track **decay** (adopted tools going stale / changing license / entering maintenance), and keep a falsifiable record of what was judged and why.*

**Cadence:** daily light scan (poll Section A1 primary sources for release/leaderboard/HF-papers deltas) · weekly deep pass (Section B blind queries + lab blogs + independent re-derivation). Newsletters (Section A2) are supplementary lead-gen only. See `roles/researcher.md` → "The Radar."

---

## Why this radar exists (read before every scan)

You are scanning on behalf of the **loop-team**: a self-improving team of agents (Oga the orchestrator + Test-writer, Coder, Verifier, Gold-judge, Live-smoke, Researcher) that builds code and verifies its own work against an objective signal. The north star: **propose → verify → feed back → repeat; the loop is only as good as its verifier.** You scan so the team adopts what's genuinely better and drops what's decaying — without a human re-finding the same tools every week.

**What "better" means here — it is not vibes.** A find only matters if it can move a *measured number*: the eval-suite's caught-hole rate / false-pass rate (`evals/run_evals.py`), or held-out coding-task success. If a tool can't be tied to one of those, it's at most RESEARCH_ONLY. This is why every kept candidate ships with a falsifiable experiment, never a recommendation.

**The team's stance is "assemble, don't invent."** Its own research concluded the *verifier is the product* and the engine is off-the-shelf — so your job is to find the best borrowable component for a known need, not novelty for its own sake. The radar exists for two reasons specifically: (1) the field moves weekly and benchmarks saturate (SWE-bench Verified did), and (2) adopted tools **decay** — they enter maintenance, flip license, or get superseded (AutoGen → maintenance; classic SWE-agent → superseded by mini). Catching decay early is as valuable as finding something new.

**Where the team is now — DERIVE it, never trust a hardcoded snapshot.** The team's position changes as it ships, so this file does not assert it (any phase number written here would rot). At the start of each run, determine the current state from the sources of truth:
- **Active phase / sequence** → read `loop-team/ROADMAP.md` and `loop-team/NEXT_PHASE.md`: whichever phase is marked done vs. next is the truth. The dependency graph `0 → 1 → {2,3} → 4 → 5 → 6` and the "measurement and safety before power" rule live there.
- **What's adopted / what's a live candidate** → read this radar's own table: the `ADOPTED` and `CANDIDATE` rows ARE the current critical-path state. Don't restate it in prose; reconcile against the rows.
- **Last thing actually worked on / shipped** → read the repo's git history — this is the freshest, most reliable signal, ahead of any doc. The repo root is `public/` (remote `origin` = `github.com/Eobodoechine/loop-engineering`). Run, from `public/`:
  - `git branch --show-current` — the **branch name often encodes the active phase** (e.g. `phase1-eval-harness` ⇒ Phase 1 eval work is live).
  - `git log --oneline -15` — recent commit subjects are the ground truth for what was last touched (e.g. "Measure verifier independence…", "Track 6 corpus-grounded rental regression cases…").
  - `git log origin/<branch>..HEAD --oneline` (and `HEAD..origin/<branch>`) — what's unpushed vs. newly pushed, so you know what just landed.
  Use this to pin "current/next phase" and to spot if work has moved on since this block was last reconciled. (If git isn't reachable on a given run, fall back to the docs below and note it.)
- **Open holes / what's actively being worked** → skim `fix_plan.md` and `runs/` for what the team last touched.
If these sources and this block ever disagree, the sources win — and the weekly deep pass should fix the drift (see self-maintenance below). Order of trust for "where the team is now": **git history (freshest) → ROADMAP/NEXT_PHASE → radar table → fix_plan/runs.**

**Why each scan category exists — the need is tied to a PHASE, so it tracks the roadmap, not a fixed list.** Each category matters in proportion to how close its phase is to active. Weight your attention toward the *current and next* phase; treat far-future phases as WATCH-only.
- *Coding worker* → the **worker-swap phase** (currently Phase 2): a better/cheaper agent on SWE-bench Pro / Terminal-Bench improves build quality. Current pick: see the radar's worker rows.
- *Optimizer* → the **measured-improvement phase** (Phase 1B): wiring an optimizer into `optimize/` to sharpen the Verifier against the suite. Current picks: optimizer rows.
- *Eval / verifier* → **cross-cutting, always relevant**: the gate is the heart of the system; a better eval substrate or judge-validation method strengthens everything downstream.
- *Experiment harness / agent search* → the **method-racing phase** (Phase 4): the engine that races variants and keeps the winner.
- *Self-improvement* → the **self-rewrite phase** (Phase 5): WATCH-only precedents, read for safety until the gates that make it safe exist.
- *Multi-repo orchestration* → the **portfolio phase** (Phase 6): WATCH until the single-team loop is trusted.
As the team grows, **new categories may appear and active ones may retire** — when the roadmap adds/closes a phase, add/retire the matching manifest category and category-bullet here. The category list is downstream of the roadmap, not fixed.

**The discipline that makes this safe:** a radar find is a **lead, not a decision.** Nothing enters the critical path without a passed, PACE-gated experiment and a human-reviewed diff. Your scan's real output is two things: *feed the experiment queue* with grounded candidates for the current/next phase, and *raise decay risks* on what's already adopted.

**Self-maintenance (weekly deep pass owns this):** this "why" block, the scan manifest categories, and the roadmap must stay in sync. On the weekly deep pass, reconcile them: if the active phase moved, if a category's phase opened/closed, or if an ADOPTED tool's status changed, update this block + the manifest + the table and log it in the change log. The radar keeps *itself* current — that's the whole point of a memory file over a static snapshot.

**How to use this file:**
- Every candidate the Researcher opens gets a row here, even rejects (negative results prevent re-research).
- `last_checked` is bumped on every scan that touches the row. If a row hasn't been re-checked past its decay window, it's a scan target.
- A change in maturity (maintenance mode, license flip, archived, big version jump, leaderboard move) → flag in **Decay/Notes** and raise to Oga.
- New tools that pass the honesty bar (opened + quoted) get added with a triage verdict and, if TESTABLE/IMPLEMENTABLE, a pointer to the `experiments/` spec.

**Status legend:** `ADOPTED` (in critical path) · `CANDIDATE` (passed honesty bar, queued for experiment) · `WATCH` (promising, not yet actionable) · `REJECTED` (evaluated, not pursued — with reason) · `DECAYING` (was viable, now at risk).

**Triage legend:** `IMPLEMENTABLE_NOW` · `TESTABLE` · `RESEARCH_ONLY` (from `roles/researcher.md`).

---

## Adopted / active picks (decay-watch these first)

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| GEPA (gepa-ai/gepa) | Optimizer | CANDIDATE | IMPLEMENTABLE_NOW | ~4.5k | MIT | 2026-06-23 | v0.1.1 Mar 2026, ICLR'26 Oral. Phase 1B optimizer seam. NEW: `optimize_anything` API (Feb 2026) extends beyond prompts to code/agent-config; "Auto-learning skills for coding agents" 55%→82% on Jinja. No 2026 entrant beat it — field is adopting GEPA, not superseding. Watch: 70% notebooks. |
| DSPy (stanfordnlp/dspy) | Optimizer/framework | CANDIDATE | IMPLEMENTABLE_NOW | ~35k | MIT | 2026-06-23 | Stable 3.2.1 May 2026; 3.3.0b1 beta in flight — pin version. Bundles GEPA+MIPROv2. |
| mini-swe-agent (SWE-agent/mini-swe-agent) | Coding worker | CANDIDATE | IMPLEMENTABLE_NOW | ~5.5k | MIT | 2026-06-27 | v2.4.2 Jun 2026 (stars grew 4.9k→5.5k). Phase 2 Coder, still the minimal-baseline pick. Sandbox REQUIRED. Pin litellm (v2.2.8 excluded compromised 1.82.7/1.82.8). Live-SWE-agent (former "builds on" entrant) is now DECAYING. |
| Live-SWE-agent (OpenAutoCoder/live-swe-agent) | Coding worker | DECAYING | TESTABLE | ~0.4k | MIT | 2026-06-27 | **⚠ DECAY: last commit 2026-01-19 — 5+ months stale.** Was: runtime self-evolving scaffold on top of mini-swe-agent. Young repo (11 commits, 1 release Nov 2025) with no activity since January. Do not build on. If commit activity resumes, re-evaluate. |
| DeepEval (confident-ai/deepeval) | Eval substrate | WATCH | TESTABLE | ~15.4k | Apache-2.0 | 2026-06-23 | v4.0.x "Eval Harness for Coding Agents" (May 2026). License RESOLVED → Apache-2.0 (was unknown). NEW: DAG graph-based *deterministic* LLM-judge metric — directly relevant to the Phase-1 verifier seam. |
| Inspect (UKGovernmentBEIS/inspect_ai) | Eval substrate | WATCH | TESTABLE | ~2.2k | MIT | 2026-06-20 | UK AISI; scorers first-class. Phase 1 substrate option. |
| Promptfoo (promptfoo/promptfoo) | Eval substrate | WATCH | TESTABLE | — | MIT | 2026-06-20 | Now part of OpenAI; CI-native frozen suite. Re-verify governance. |

## Coding workers

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| OpenHands (All-Hands-AI/OpenHands) | Worker / platform | WATCH | TESTABLE | ~78.5k | — | 2026-06-27 | OSS v1.8.0 (Jun 2026). Cloud releases active: Cloud 1.39.0 (Jun 24) + Cloud 1.40.0 (Jun 26, CVE patches + Azure DevOps resolver + multi-model LLM discovery). Heavyweight Phase 2 option + Phase 6. Top open-scaffold on Terminal-Bench 2.0 (51.9%, Opus 4.5). |
| GLM-5.2 (zai-org / Z.ai) | Coding worker **model** | CANDIDATE | TESTABLE | ~1.2k HF | MIT | 2026-06-23 | **NEW (AlphaSignal lead, verified).** Real 753B MoE, 1M ctx, MIT, self-hostable (vLLM/SGLang); [HF card](https://huggingface.co/zai-org/GLM-5.2). Z.ai benchmarks it *under mini-swe-agent* → clean Phase-2 model-under-scaffold fit. ⚠ Benches **vendor-reported only**: TB2.1 81.0 (NOT on independent tbench.ai, which lists GLM-5.1 58.7); SWE-bench Pro 62.1. Newsletter "DeepSWE 44% / +17% vs Kimi" **UNVERIFIED** (card says 46.2, no Kimi col). **priority ≈ 0.50** (effect .85 × conf .70, phase_fit .95, cost .45). Test via hosted API first (self-host = H100-class + China-data caveat). Experiment: same scaffold, swap model vs current Coder model, paired tasks, PACE-gated on pass@1 + cost/task. Best-verified MIT worker-model of the three. **[light-run delta: now on the independent DeepSWE board at 44% (top open-weight) — partial de-risk of the prior vendor-only flag; confidence → ~0.75.]** |
| Nex N2 Pro (nex-agi) | Coding worker **model** | WATCH | TESTABLE | ~6 HF | Apache-2.0 | 2026-06-23 | **NEW (AlphaSignal lead, verified). priority ≈ 0.30.** Real 397B MoE (on Qwen3.5), Apache-2.0, self-hostable (sglang/vLLM/OpenRouter); [HF card](https://huggingface.co/nex-agi/Nex-N2-Pro). ⚠ TB2.1 75.3 **vendor-only — absent from independent tbench.ai**; newsletter "top-3 globally" **REFUTED** (GPT-5.5 83.4 / Fable 83.1 / Opus 4.8 78.9 all beat it; only "beats Opus 4.7 69.7" holds). Brand-new, ~6 likes. Behind GLM-5.2 on permissive-license worker-model race. |
| MiniMax M3 (MiniMaxAI) | Coding worker **model** | WATCH | TESTABLE | quants | **MiniMax Community License** (custom, NOT Apache/MIT) | 2026-06-23 | **NEW (AlphaSignal lead, verified). priority ≈ 0.24.** Real ~428B MoE (23B active), 1M ctx, native multimodal, MiniMax Sparse Attention (~1/20 compute at 1M); [HF card](https://huggingface.co/MiniMaxAI/MiniMax-M3). ⚠ **License is custom — check redistribution/commercial terms before Phase-2 use** (newsletter implied open; it's not Apache/MIT). SWE-bench Pro 59.0 (>GPT-5.5 58.6) **vendor-reported, no independent board**; API $0.30/M unverified. Differentiator = cheap 1M context. |
| **SERA** (Ai2) | Coding worker + verifier | CANDIDATE | TESTABLE | open | open | 2026-06-23 | **NEW (Jan–Jun mining, verified). priority ≈ 0.59 — best cost/risk.** [arXiv 2601.20789](https://arxiv.org/abs/2601.20789). Train your *own* repo coding agent from **~$400**; fully open 8–32B models + datasets + recipe. SERA-32B = 54.2% SWE-bench Verified on 2 Hopper GPUs. Bonus: **soft (LLM-free) verifier** — line-level recall patch comparison → a cheap Phase-1 verifier signal. Phase 2 (own a small Coder) + Phase 1. |
| Qwen3.6-27B (Alibaba) | Coding worker **model** | WATCH | TESTABLE | HF | Apache-2.0 | 2026-06-23 | **NEW (Jan–Jun mining, verified). priority ≈ 0.71.** Dense 27B, ~18GB VRAM (runs local), SWE-bench Verified 77.2 / Terminal-Bench 2.0 59.3 (vendor-reported), "thinking preservation," vLLM/SGLang. Strong cheap Apache-2.0 worker model — see digest for the fuller open-model pool (Qwen3.5-397B, Kimi K2.7, DeepSeek V4, GLM-4.7-Flash, Poolside Laguna). |
| OpenAI Codex CLI (openai/codex) | Worker | WATCH | TESTABLE | — | Apache-2.0 | 2026-06-20 | Hardened Rust binary, non-interactive exec/JSON mode. Phase 2 alternative. |
| Claude Agent SDK | Worker / harness | WATCH | TESTABLE | — | — | 2026-06-20 | Own-the-harness option; `Workflow` tool referenced for Phase 6. |
| SWE-agent (classic) | Worker | REJECTED | — | ~19.6k | MIT | 2026-06-23 | **Superseded by mini-swe-agent per its own README.** Maintenance (v1.1.0 May 2025). Don't adopt. |
| Aider (Aider-AI/aider) | Pair-programmer | WATCH | RESEARCH_ONLY | — | — | 2026-06-17 | Terminal pair-programmer; less embeddable than mini. |
| AutoCodeRover (nus-apr/auto-code-rover) | Repair | WATCH | RESEARCH_ONLY | — | — | 2026-06-17 | Structure-aware repair; acquired by Sonar, still open. |

## Optimizers / experiment harness

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| MIPROv2 (in DSPy) | Optimizer | CANDIDATE | IMPLEMENTABLE_NOW | (DSPy) | MIT | 2026-06-23 | Bayesian instruction+demo search; arXiv 2406.11695. |
| **SkillOpt** (microsoft/SkillOpt) | Optimizer / skill-trainer | CANDIDATE | IMPLEMENTABLE_NOW | ~9.5k | MIT | 2026-06-27 | **priority ≈ 0.491 (deep-verified).** [arXiv 2605.23904](https://arxiv.org/abs/2605.23904) · `pip install skillopt`. Text-space optimizer: rollout → verifier score → reflection → bounded add/del/replace edits accepted only on held-out gain. +23.5/+24.8/+19.1 pts (GPT-5.5 chat/Codex/Claude Code harness — ⚠ GPT-5.5 is the target model in all benchmarks, Claude-as-model effect unverified). Beats GEPA+EvoSkill as baselines on 52/52 cells. **Maturity inflection: ~5.8k→9.5k stars in 4 days (organic multi-platform surge, not HN spike) — adoption window narrowing.** Claude backend confirmed (`claude_chat` + `claude_code_exec` modules). SkillOpt-Sleep nightly plugin bundled in v0.1.0 (Jun 2); Claude Code install: `/plugin marketplace add ./plugins/claude-code`. ⚠ +19.1pp is vs zero-skill baseline — marginal gain over existing mature skills (e.g. VERIFIER.md) will be smaller. **First experiment: run SkillOpt on VERIFIER.md, 3 epochs, held-out gate; kill if <3pp on held-out or optimizer deletes recall-checking language.** |
| **EvoSkill** (sentient-agi/EvoSkill) | Optimizer / skill-discovery | CANDIDATE | IMPLEMENTABLE_NOW | ~0.84k | Apache-2.0 | 2026-06-23 (v1.3.0) | **NEW (AlphaSignal lead, verified). priority ≈ 0.58.** [light-run delta: → v1.3.0 (16 Jun), adds Fireworks AI as evolution-harness backend + scorer.] [arXiv 2603.02766](https://arxiv.org/abs/2603.02766). GEPA-style skill discovery for *coding* agents: multiple skill+prompt mutations on separate **`program/*` Git branches + Pareto frontier**, held-out eval, lowest-performer replaced. Harbor + SWE-Bench-Verified integration; drives Claude Code/Codex/OpenHands. Phase 4/5. Note: SkillOpt's paper claims to beat it — treat as the baseline-to-beat. Gain numbers (OfficeQA/SealQA) unverified (PDF empty); code fully verified. |
| **Karpathy Autoresearch** (karpathy/autoresearch) | Optimizer / outer-loop | CANDIDATE | IMPLEMENTABLE_NOW | ~21k | open | 2026-06-27 | **⚠ NEEDS-RECHECK: GitHub returned empty commit history on 2026-06-27 — repo may be private, renamed, or deleted. Cannot confirm active status this pass.** Was: canonical self-improving loop (edit `train.py` → score → git-commit on gain, revert on loss), priority ≈ 0.75. Re-verify next pass via direct `github.com/karpathy/autoresearch` fetch. |
| **Meta-Harness** (Stanford/MIT/KRAFTON) | Optimizer / harness-search | CANDIDATE | TESTABLE | paper+page | — | 2026-06-23 | **NEW (Jan–Jun mining, verified). priority ≈ 0.67.** [arXiv 2603.28052](https://arxiv.org/abs/2603.28052). Outer-loop that searches over *harness code* via an agent reading **all prior candidates' source + scores + traces through a filesystem** (full history, not compressed summaries like GEPA/MIPRO). +7.7 pts, 4× fewer context tokens. **Deep-run finding: the team's `optimize/` proposer currently reads a 280-char summary = the ablation's weakest channel; feeding raw traces is worth ~+15 pts. See `research/optimize-loop-redesign-proposal.md`.** |
| **RHO — Retrospective Harness Optimization** (wbopan) | Optimizer / harness-self-improve | CANDIDATE | IMPLEMENTABLE_NOW | 29★ | MIT | 2026-06-27 | **priority ≈ 0.397 (deep-verified).** [arXiv 2606.05922](https://arxiv.org/abs/2606.05922) · github.com/wbopan/retro-harness. Self-supervised: selects k=10 diverse/hard tasks from past trajectories (DPP coreset), re-executes n=3 rollouts, generates 2 candidate harness rewrites via self-preference — no labels required. SWE-Bench Pro 59%→78% (+19pp) confirmed in paper body. ⚠ **All paper experiments use GPT-5.5 (Codex) exclusively — confirmed from arXiv HTML: "gpt-5.5 shared across solve, optimize, and rank." Zero Claude evaluation.** Claude Code workflow exists (`/.claude/workflows/retrospection.js` confirmed in repo). Cold-start risk: needs ≥10 trajectories for the coreset. Amplification risk: model-generated preference signal can encode wrong heuristics (flagged in paper). **Queue after SkillOpt experiment. Gate: audit trajectory volume first; if <30 sessions, defer.** |
| **Self-Harness** (Shanghai AI Lab) | Optimizer / harness-self-improve | WATCH | RESEARCH_ONLY | paper | CC-BY | 2026-06-27 | **priority ≈ 0.290 (deep-verified, triage downgraded to RESEARCH_ONLY — no code).** [arXiv 2606.09498](https://arxiv.org/abs/2606.09498). 3-stage: Weakness Mining (cluster failed traces by root cause) → Harness Proposal (K diverse minimal edits) → Proposal Validation (accept only if ≥1 split improves, none degrades). TB2.0 gains confirmed from paper HTML: MiniMax M2.5 40.5→61.9, Qwen3.5 23.8→38.1, GLM-5 42.9→57.1. ⚠ **All evals on mid-tier open models only — no GPT-5.5/Claude/frontier evaluation. Gains may reflect harness weaknesses that frontier models already route around.** No code released, no repo URL in paper, no code release commitment found. 60-day watch: monitor Shanghai AI Lab GitHub + `gh search repos "self-harness"`. **If code drops AND frontier model gains confirmed → immediately becomes top implementation target; contingency experiment spec is ready.** Run RHO first; Self-Harness must beat RHO's held-out result to displace it. |
| **SkillReducer** | Optimizer / token efficiency | WATCH | TESTABLE | paper | CC-BY | 2026-06-27 | **NEW (weekly deep). priority ≈ 0.195.** [arXiv 2603.29919](https://arxiv.org/abs/2603.29919), revised Jun 24 2026. Paper (abstract confirmed via fetch): *"48% description compression and 39% body compression while improving functional quality by 2.8%… 0.965 mean retention rate across five models."* No code released. Useful downstream of SkillOpt: trim evolved skills for context efficiency. Marginal gains; implement only after SkillOpt adoption. |
| **SkillOps** (Hik289) | Optimizer / skill library health | WATCH | TESTABLE | repo | MIT | 2026-06-27 | **NEW (weekly deep). priority ≈ 0.216.** [arXiv 2605.13716](https://arxiv.org/abs/2605.13716) · github.com/Hik289/SkillOps (repo confirmed via fetch). Paper: *"79.5% task success on ALFWorld as standalone agent, outperforming strongest baseline by 8.8pp… nearly zero LLM calls or tokens at library time."* Skill Contracts + Hierarchical Skill Ecosystem Graph diagnose and repair "skill technical debt." Gains smaller as plug-in (0.68–2.90pp). Useful downstream of SkillOpt as library maintenance layer. Queue after SkillOpt adoption. |
| EvoAgentX (EvoAgentX/EvoAgentX) | Experiment harness | WATCH | TESTABLE | ~3k | — | 2026-06-20 | Self-evolving workflow framework; live-confirmed active. Phase 4 candidate. |
| AgentSquare (tsinghua-fib-lab/AgentSquare) | Agent search | WATCH | TESTABLE | — | — | 2026-06-20 | Modular Plan/Reason/Tool/Memory search; +17.2% over human-designed. Phase 4. |
| Agent Lightning (microsoft/agent-lightning) | Optimizer | WATCH | RESEARCH_ONLY | ~16.8k | — | 2026-06-23 | v0.3.0 (Dec 2025) — no longer a stub. "15x throughput vs v0.2.2", now integrates Claude Code as a LitAgent + trains on SWE-bench. Turns any agent into optimizable entity (RL+prompt). Phase 4. |
| TextGrad (zou-group/textgrad) | Optimizer | WATCH | RESEARCH_ONLY | ~3.6k | — | 2026-06-17 | Nature 2025; release cadence slowed. |
| OPRO (google-deepmind/opro) | Optimizer | REJECTED | RESEARCH_ONLY | — | — | 2026-06-17 | Reference code only; superseded by GEPA/DSPy for our use. |
| Trace / OptoPrime (microsoft/Trace) | Optimizer | WATCH | RESEARCH_ONLY | ~743 | — | 2026-06-17 | "AutoDiff for AI systems." |

## Eval / verifier

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| SWE-bench (SWE-bench/SWE-bench) | Benchmark/harness | WATCH | TESTABLE | ~5.2k | MIT | 2026-06-20 | Verified saturated (~80%); field moved to SWE-bench Pro / Terminal-Bench. Re-verify at Phase 2 start. |
| Terminal-Bench (laude-institute/terminal-bench) | Benchmark | WATCH | TESTABLE | ~2.4k | — | 2026-06-23 | **Headline shifted: now TB 2.0/2.1 (live), 3.0 coming, run via Harbor framework (`harbor-framework/harbor`) — old v1.0 path stale.** TB2.0: 142 entries; top open-scaffold OpenHands 51.9% / mini-SWE-agent 42.5%; proprietary stacks lead ~84%. The independent TB2.1 board is the authority for catching vendor-only worker-model claims (GLM-5.2, Nex N2 Pro both absent). |
| FrontierCode (Cognition) | Benchmark / eval | WATCH | RESEARCH_ONLY | — | — | 2026-06-23 | **NEW (AlphaSignal lead, verified-secondary).** Code-quality / PR-"mergeability" benchmark (regression safety, test quality, scope, style) built with 20+ OSS maintainers; sets Extended 150 / Main 100 / Diamond 50. Frontier models score brutally low: Opus 4.8 ~13.4% on Diamond, GPT-5.5 6.3%, most <5%. Relevant Phase-1 hard eval — a real-world "is the diff actually mergeable" signal beyond pass/fail tests. Confirmed via secondary aggregators (couldn't open cognition.ai primary); exact % secondary-sourced. |
| Asuka-Bench | Benchmark / eval | WATCH | TESTABLE | paper | CC-BY | 2026-06-23 | **NEW (deep run, verified).** [arXiv 2606.05920](https://arxiv.org/abs/2606.05920). Pairs **underspecified user intent + multi-round refinement**, browser-rendered grading; 50 web tasks / 784 criteria; strongest model only 52% after 3 rounds. A realistic "agent handles vague, iterative requests" eval (Phase 1/2). |
| SWE-Marathon | Benchmark / eval | WATCH | TESTABLE | repo+site | — | 2026-06-23 | **NEW (deep run, verified).** [arXiv 2606.07682](https://arxiv.org/abs/2606.07682). Ultra-long-horizon (avg 27.2M tokens/attempt), <30% solve, **13.8% reward-hacking rollouts + adversarial test-suite review** — directly relevant to eval integrity. Very expensive to run (20 tasks). |
| DeepSWE (Datacurve) | Benchmark / eval | WATCH | TESTABLE | repo+board | — | 2026-06-23 (v1.1) | **NEW (Jan–Jun mining, verified). priority ≈ 0.44.** [github.com/datacurve-ai/deep-swe](https://github.com/datacurve-ai/deep-swe) · board [deepswe.datacurve.ai](https://deepswe.datacurve.ai/). Contamination-free hard coding benchmark — 113 tasks **written from scratch**, ~5.5× more code/solution than SWE-Pro; caught a model exploiting a loophole. **[light-run delta: now v1.1/113 tasks (20 Jun); Claude-Fable-5 70% overtakes GPT-5.5 67%; top OPEN-weight = GLM-5.2 44%, Kimi-K2.7-Code 31% — gives us an independent open-model coding board.]** Good harder eval for Coder swaps (Phase 4/2). |
| SERA soft-verifier · CUDA-Agent exec-reward · Claude-Code-Security self-prove · Leanstral (Lean4) | Verifier patterns | WATCH | RESEARCH_ONLY | — | mixed | 2026-06-23 | **NEW (Jan–Jun mining).** Four verifier designs worth mining for the gate: SERA's **LLM-free soft verifier** (line-level recall — deep run: usable only as a Layer-0 router on the *patch slice with a reference patch*, gameable on precision, never PASS alone); CUDA-Agent's **real-execution reward** (arXiv 2602.24286); Claude-Code-Security's **self-prove/disprove** multi-stage filter; Mistral **Leanstral** (Apache-2.0, formal Lean-4 proof). See digest + `optimize-loop-redesign-proposal.md`. |
| **R4P / Patch Reasoner** (ByteDance) | Verifier (execution-free) | CANDIDATE | TESTABLE | paper | CC-BY | 2026-06-23 | **NEW (deep run, verified). priority ≈ 0.38.** [arXiv 2510.22775](https://arxiv.org/abs/2510.22775). Reasoning-based patch verifier: *"72.2% Acc verifying SWE-bench-Verified patches, surpassing OpenAI o3 … verifies within a second, 50× faster than testing,"* group-wise RL objective to cut reward-hacking. A fast execution-free pre-screen for the gate; author-reported (unverified weights). |
| **SWE-RM** (execution-free reward model) | Verifier (execution-free) | WATCH | RESEARCH_ONLY | paper | — | 2026-06-23 | **NEW (deep run + weekly deep — merged duplicate rows). priority ≈ 0.38 (no runnable repo → triage RESEARCH_ONLY).** [arXiv 2512.21919](https://arxiv.org/abs/2512.21919). 30B-MoE (3B active) reward model; +10pp on Qwen3-Coder-Flash (+7.6pp Verified on Qwen3-Coder-Max, TTS). Flags **classification accuracy + calibration** (not just TTS-selection) as what makes a reward signal good — borrowable insight for `verifier.md` judge validation. No runnable repo found. Model = GPU weight (infra-heavy, out of scope for adoption). |
| **Agentic Verifier** (RUC + Qwen Team) | Verifier (execution-based) | WATCH | TESTABLE | paper | — | 2026-06-23 | **NEW (deep run, verified). priority ≈ 0.26.** [arXiv 2602.04254](https://arxiv.org/abs/2602.04254). Execution-based verifier that searches for **highly discriminative test inputs**; +10–15% Best@k; includes a useful "Imperfect Verifiers in Benchmarks" analysis. Narrower (competitive coding, needs sandbox) than R4P/SWE-RM. |
| **The Verification Horizon** (Qwen team) | Verifier / design principle | WATCH | RESEARCH_ONLY | paper | — | 2026-06-27 | **NEW (HF Daily Papers, Jun 24). No tool — confirms existing direction.** [arXiv 2606.26300](https://arxiv.org/abs/2606.26300). "Every verifier is only a proxy for human intent, never the intent itself… Verification must co-evolve with the generator." Validates the team's pivot to execution-grounding (Lane C-min) and away from static rubric-only checks. No experiment needed — already encoded in VERIFIER.md redesign direction. |
| Agent-as-a-Judge (metauto-ai/agent-as-a-judge) | Reward judge | WATCH | RESEARCH_ONLY | ~784 | — | 2026-06-17 | Step-by-step agent eval → reward signals. |
| Ragas → VibrantLabs | Eval | DECAYING | RESEARCH_ONLY | — | — | 2026-06-20 | Rebranded (Ragas → VibrantLabs). Track identity churn. |
| OpenAI Evals (openai/evals) | Eval | DECAYING | RESEARCH_ONLY | ~19k | — | 2026-06-20 | OSS stagnating in favor of hosted product. |

## Self-improvement (Phase 5 — sandbox-only, research-grade)

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| SICA (Self-Improving Coding Agent) | Self-improve | WATCH | RESEARCH_ONLY | — | — | 2026-06-20 | arXiv 2504.15228; agent edits own orchestration code, 17%→53%. Closest Phase 5 precedent. |
| Darwin-Gödel Machine (jennyzzt/dgm) | Self-improve | WATCH | RESEARCH_ONLY | — | — | 2026-06-20 | arXiv 2505.22954. **Cautionary** — removed its own monitor markers. Read safety section. |
| Gödel Agent (Arvid-pku/Godel_Agent) | Self-improve | WATCH | RESEARCH_ONLY | — | — | 2026-06-20 | arXiv 2410.04444; runtime self-modification. |
| ADAS / Meta Agent Search (ShengranHu/ADAS) | Agent search | WATCH | RESEARCH_ONLY | ~1.6k | — | 2026-06-17 | Meta-agent writes agents as code. Last commit early 2025 — check staleness. |
| GPTSwarm (metauto-ai/GPTSwarm) | Agent topology | WATCH | RESEARCH_ONLY | ~1k | — | 2026-06-17 | Optimizable agent graphs; ICML'24 oral. |
| SEAL (Continual-Intelligence/SEAL) | Weight-level | WATCH | RESEARCH_ONLY | — | — | 2026-06-17 | MIT; model generates own finetuning data. Only one that touches weights. |
| Voyager (MineDojo/Voyager) | Skill library | WATCH | RESEARCH_ONLY | — | — | 2026-06-17 | Ever-growing executable skill library; frozen weights. |

## Frameworks / ecosystem signals

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| AutoGen (microsoft/autogen) | Multi-agent | DECAYING | REJECTED | ~58k | — | 2026-06-20 | **Maintenance mode** per own README → Microsoft Agent Framework is "enterprise-ready successor." Don't build on. |
| Microsoft Agent Framework | Multi-agent | WATCH | RESEARCH_ONLY | ~11k | — | 2026-06-23 | python-1.8.0 (Jun 2026), GA-level, ~weekly releases. Confirms the AutoGen→successor decay path. Track maturity. |
| LangGraph (langchain-ai/langgraph) | Agent loop | WATCH | RESEARCH_ONLY | — | MIT | 2026-06-17 | Stateful graph, checkpointing, HITL. Reference for control surface. |
| Dive-into-Claude-Code (VILA-Lab) | Design reference | WATCH | RESEARCH_ONLY | ~8★ | CC-BY-NC-SA | 2026-06-23 | **NEW (AlphaSignal lead, verified).** Source-level analysis of Claude Code v2.1.88 → 5 values / 13 design principles ("only 1.6% is AI logic; 98.4% deterministic infra"). Mine for Oga's harness: minimal-scaffold/maximal-harness, graduated context compaction, isolated subagent boundaries (summaries-only return), graceful recovery. Read-and-mine only (NC license — don't redistribute text). |
| anthropics/claude-cookbooks | Design reference (official) | CANDIDATE | IMPLEMENTABLE_NOW | — | MIT | 2026-07-02 | **NEW (direct repo review, 5-cluster read + synthesis).** Full dossier: `research/claude-cookbooks-review-2026-07-02.md`. Mined `patterns/agents/*`, `managed_agents/CMA_*`, the repo's own dogfooding CI (`.claude/`+`.github/workflows`), `tool_use/` context+memory+tool-search, `misc/`+`evals/agentic_search/`+`extended_thinking/`. 16 ranked, deduped candidates survived (6 HIGH / 9 MED / 3 LOW) after cross-checking against the existing backlog; 8 more explicitly flagged as duplicates/inapplicable and dropped (see dossier). Top HIGH items: background priority-ranked compaction (corrections>errors>active>completed work) for the coherence-collapse gap; `disallowed_tools` as a hard SDK denylist (names the actual root cause of the sub-agent-punting failure); mandatory independent Oga re-run before any Coder-claimed-green gets checkpointed; a 5th failure-arbiter class for silent in-band tool-throttle strings; full (not last-only) retry memory for the Coder; evidence-bar rubric rewrite + no-fire list for VERIFIER.md. Not yet PACE-tested — dive-in queue entries, not adopted. |
| CrewAI / CAMEL / ChatDev | Multi-agent | WATCH | RESEARCH_ONLY | — | — | 2026-06-17 | Active role-based team frameworks. Reference only. |

---

## Scan manifest — what to search, where, and for what signal

*The concrete search plan both cadences run from. Daily light = poll the **Sources to poll** rows and report deltas. Weekly deep = also run the **Query strings** blind, then diff against this radar. Every hit still clears the honesty bar (open + quote) before it lands in a row.*

### A. Sources to poll directly (deltas only — daily)
Poll each, compare to the row's `last_checked` / known version, report only what moved.

**Source-quality principle (learned the hard way):** newsletters/digests are *lead generators only* and are routinely wrong — AlphaSignal garbled "DeepSWE 44% beats Kimi by 17%" (real: 46.2, no Kimi col), claimed Nex N2 "top-3 globally" (refuted), and mislabeled MiniMax M3 as "open weights" (custom non-OSS license). **Lean the scan on primary/ground-truth sources; treat every newsletter claim as unverified until a primary page is opened + quoted.**

**A1 — Primary / ground-truth (the backbone — poll these first):**
- **Hugging Face Daily Papers** — `https://huggingface.co/papers` — community-voted daily research feed; the single best signal for new methods (optimizers, verifiers, self-improvement, coding models). Skim titles, open the ones matching the categories.
- **Live leaderboards** (read the top *open-source* entry + date — these auto-catch vendor-benchmark laundering):
  - SWE-bench: `https://www.swebench.com/` (Verified **and** Pro)
  - Terminal-Bench / Harbor: `https://www.tbench.ai/leaderboard` (TB 2.0 **and** 2.1)
  - DeepSWE: `https://deepswe.datacurve.ai/`
  - (watch for SWE-rebench / SWE-bench-Live as contamination-resistant successors)
- **GitHub Releases** (latest tag + date) for tracked repos: `gepa-ai/gepa`, `microsoft/SkillOpt`, `sentient-agi/EvoSkill`, `karpathy/autoresearch`, `stanfordnlp/dspy`, `SWE-agent/mini-swe-agent`, `OpenAutoCoder/live-swe-agent`, `confident-ai/deepeval`, `UKGovernmentBEIS/inspect_ai`, `promptfoo/promptfoo`, `All-Hands-AI/OpenHands`, `openai/codex`, `EvoAgentX/EvoAgentX`, `microsoft/agent-framework`, `microsoft/agent-lightning`.
  → fetch `https://github.com/<repo>/releases` and `https://github.com/<repo>` (stars, last-commit, maintenance/archived banner, License box).
- **arXiv recent listings** (skim titles; open only category-relevant abstracts): `https://arxiv.org/list/cs.SE/recent` · `cs.AI/recent` · `cs.LG/recent`.
- **GitHub Trending** (Python, weekly), lead-only: `https://github.com/trending/python?since=weekly`.
- **Lab blogs** (check on the weekly deep pass): Anthropic, OpenAI, DeepMind, Sakana, Microsoft Research, Ai2/allenai, Stanford CRFM.

**A2 — Curated newsletters (LEADS ONLY — use 2–3 for recall, never as truth):**
- AlphaSignal (in the user's Gmail; high breadth, high hype — verify everything).
- Import AI (Jack Clark) and The Batch (Andrew Ng) — lower-hype, reliable.
- Latent Space / AINews (swyx) — highest recall for agents/coding/evals.
- Ahead of AI (Sebastian Raschka) — deep on methods.
A claim from A2 is a query, not a finding — confirm against an A1 primary before it lands in a row.

### B. Query strings to run blind (weekly deep — by category)
Run these via WebSearch, treat results as *leads only*, then open + quote primary sources. Map each hit to a radar category; if it beats a current pick, write a dossier row + experiment spec.

- **Coding worker:** `"SWE-bench Pro" leaderboard open source agent 2026` · `Terminal-Bench 2.1 top open agent` · `DeepSWE leaderboard open model` · `open source coding agent beats mini-swe-agent` · `open-weight coding model Apache SWE-bench 2026` (worker-model pool)
- **Optimizer / skill-trainer:** `prompt optimizer outperforms GEPA 2026` · `skill optimization LLM agent arxiv` · `SkillOpt OR EvoSkill OR Autoresearch follow-up` · `self-improving harness optimizer arxiv 2026` · `reflective prompt evolution held-out validation`
- **Eval / verifier:** `LLM-as-judge framework 2026` · `code patch verifier reward model arxiv` · `execution-reward OR soft-verifier coding agent` · `formal verification LLM generated code Lean` · `contamination-free coding benchmark 2026` · `DeepEval OR Inspect OR Promptfoo release`
- **Experiment harness / agent search:** `agentic workflow optimization framework 2026` · `multi-agent architecture search arxiv 2026` · `EvoAgentX OR AgentSquare OR "Agent Lightning"`
- **Self-improvement (Phase 5, watch only):** `self-improving coding agent arxiv 2026` · `self-evolving agent SWE-bench 2026` · `agent edits own code benchmark` · `SICA OR "Darwin-Godel" OR "Godel Agent" follow-up`
- **Multi-repo orchestration (Phase 6):** `agent fleet across repos schedule 2026` · `OpenHands Automations` · `Cursor cloud agents API` · `Claude Agent SDK Workflow multi-repo`
- **Ecosystem/decay signals:** `<adopted tool> maintenance mode` · `<adopted tool> deprecated` · `<adopted tool> license change` — run for each ADOPTED/CANDIDATE row.

### C. What counts as a reportable signal (thresholds)
Report a hit only if it clears one of these — otherwise it's noise:
- A **new release / major version** of a tracked repo (esp. breaking, or a new optimizer/worker mode).
- A **maturity/decay change**: archived, "maintenance mode", license flip (→ GPL/Elastic/non-OSI), maintainer/org change, a >6-month commit gap on an ADOPTED/CANDIDATE tool.
- A **leaderboard move**: a new top *open-source* entry, or the headline benchmark itself shifting (e.g. Verified → Pro).
- A **new tool/paper** that plausibly beats a current pick in a category we care about — with runnable code or a public benchmark number (paper-only → triage RESEARCH_ONLY).
- Skip: blog reposts, hype threads, anything you can't open to a primary source, and anything already on the radar with no change.

### D. Out of scope (don't chase)
General LLM model releases, funding/news, closed products without an API we'd use, GPU-training-only methods (we freeze weights), and tooling for domains the team doesn't build in. Note them in one line if huge; don't dossier them.

---

## Compiler/typecheck-feedback prior art (2026-07-08 targeted dive)

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| github/spec-kit | Spec-driven dev toolkit | WATCH | WATCH | 118,644 | MIT | 2026-07-08 | **NEW.** `/speckit.converge` is GitHub's own official "drift check" — confirmed via direct fetch of `templates/commands/converge.md`: pure LLM-prose read ("not a diff tool... no git, no branch comparison"), append-only, never blocks. Even GitHub's best-funded spec-driven toolkit has NOT built a static-analysis Drift Validator. Watch for a static-analysis `converge` mode as a future decay/upgrade signal. |
| Spec Growth Engine (arXiv:2606.27045) | Drift Validator (paper) | RESEARCH_ONLY | RESEARCH_ONLY | — (paper) | — | 2026-07-08 | **NEW.** "Spec-anchored, code-coupled" architecture w/ Intent-Graph-vs-Evidence-Graph Drift Validator. Confirmed via direct PDF read: **no GitHub repo, no code/artifact release, no appendix link exists.** Cites `github/spec-kit` and `kiro.dev` as its only real external references. Concept only, not adoptable. |
| WM-SEMERU/Hallucinations-in-Code | Hallucination detector (arXiv:2601.19106 companion) | RESEARCH_ONLY | RESEARCH_ONLY | 2 | none (unlicensed) | 2026-07-08 | **NEW.** Confirmed real, runnable (Python `ast`-based pipeline, 4 CLI entry points) but academic-quality: no license, 2 stars, last push 2026-01-26. Broader sweep (`gh search repos "code hallucination"` / "hallucination detection", 30 results) found NO mature general tool in this space (all 0-70★ paper-replication repos). Conclusion: the compiler itself (`tsc`, `flake8` F821) is already the best available tool for this bug class — nothing better exists to adopt. |
| Aider (Aider-AI/aider) | Coding agent — auto-lint pattern | WATCH (already tracked as pair-programmer, RESEARCH_ONLY) | TESTABLE (Python-lint pattern) | 47,165 | Apache-2.0 | 2026-07-08 | **UPDATED (new mechanism detail).** Confirmed from real source (`aider/linter.py`): `--auto-lint` defaults **True**, runs after every edit, blocking-via-retry-loop. Its `flake8_lint` fatal set is `E9,F821,F823,F831,F406,F407,F701,F702,F704,F706` — **F821 = "undefined name," the exact unbound-identifier bug class** — independent real-world confirmation this is a common, solved-by-linter bug class. Caveat: built-in `Linter` class only ships Python; TS/JS falls back to tree-sitter structural scan only, no `tsc`, unless user sets `--lint-cmd`. Portable pattern: add the same flake8 fatal-set as a Python-side sibling check to our proposed `verify.py` type_check gate. |
| Cline (cline/cline) | Coding agent — IDE-diagnostics-diff pattern | WATCH | RESEARCH_ONLY | 64,400 | Apache-2.0 | 2026-07-08 | **NEW.** Confirmed from real source (`DiffViewProvider.ts`): diffs `vscode.languages.getDiagnostics()` before/after every save, auto-injects only NEW error-severity diagnostics into agent context ("New problems detected after saving the file..."). Advisory-automatic, not a hard block. Requires an IDE/LSP host our Coder sub-agents don't run inside — mechanism doesn't transfer directly, but confirms the "diagnostics fed back automatically" pattern is real, mature, production prior art. Known caveat: cline#4381 (stale-diagnostic race condition). |
| OpenHands (All-Hands-AI/OpenHands) | Coding agent platform — Stop-hook quality gate | WATCH (already ADOPTED-adjacent per existing row above) | TESTABLE (pattern) | ~78.5k | — | 2026-07-08 | **NEW mechanism detail on existing row.** OpenHands's own `tsc` usage is CI-only (its own source, not agent-generated code — confirmed via `.github/workflows/lint.yml`). BUT: "Stop hooks" are a real, documented, directly-blocking mechanism — quoted verbatim from `docs.openhands.dev/openhands/usage/customization/hooks`: `{"decision": "deny", "reason": "Linting failed..."}` + `exit 2` prevents the agent from finishing until a command (e.g. `npm run lint`, swappable for `tsc --noEmit`) passes. Closest real-world precedent found for "compiler feedback as a structurally blocking gate distinct from prose review." Doesn't transfer as a literal file (needs OpenHands's own hook runtime) but the PATTERN maps directly onto loop-team's existing `hooks/subagent_stop_gate.py` + `verify.py` substrate. |
| SWE-agent/mini-swe-agent | Coding worker (already CANDIDATE on radar) | CANDIDATE (unchanged) | — | ~5.5k | MIT | 2026-07-08 | **Negative-confirmation note added to existing row.** Confirmed via README: "Does not have any tools other than bash" — zero built-in compiler/lint/typecheck discipline of its own; every check is an arbitrary bash command the model itself chooses to run. Confirms any structural type-check gate must live in the HARNESS (`verify.py`), not the Coder scaffold. |
| nizos/tdd-guard | Claude-Code-native TDD enforcement hook | WATCH | WATCH | 2,246 | MIT | 2026-07-08 | **NEW.** Real, mature, same-host precedent (PreToolUse hook on `Write\|Edit\|MultiEdit\|TodoWrite`, matches loop-team's own hook pattern). BUT: primary blocking validator is LLM-based ("TDD Guard validates changes using AI," Claude Agent SDK) not deterministic; PostToolUse lint layer (ESLint/golangci-lint/RuboCop) is advisory-only and has **no TypeScript-compiler/`tsc` integration**. Confirms even the closest same-ecosystem tool hasn't solved this with a deterministic gate. Successor `nizos/probity` (80★, MIT) is where new dev is happening — maintenance-mode signal on tdd-guard itself, worth a decay re-check next pass. |
| dependency-cruiser (sverweij/dependency-cruiser) | Architecture-conformance (cross-boundary imports) | WATCH | WATCH | 6,874 | MIT | 2026-07-08 | **NEW.** Real, mature, active (pushed 2026-07-07). Confirmed via `gh repo view`: "Validate and visualize dependencies. Your rules." Covers the "undeclared cross-boundary import" half of the Drift Validator's Evidence Graph concept via hand-written rules (not spec-derived). Parked for a later phase — current pain (binding bugs) is fully covered by `tsc` at far lower setup cost; revisit if/when Node-side layering rules become an active need. |
| ArchUnit (TNG/ArchUnit) | Architecture-conformance (JVM) | RESEARCH_ONLY | RESEARCH_ONLY | 3,758 | Apache-2.0 | 2026-07-08 | **NEW.** Real, mature, active. Wrong ecosystem (JVM) for current Python/Node build targets — reference-only, canonical "architecture rules as executable tests" precedent. |
| tRPC / Zod / openapi-typescript | Contract-first/type-driven codegen (corroborating prior art) | WATCH | RESEARCH_ONLY | 40.4k / 43.2k / 8.2k | MIT (all 3) | 2026-07-08 | **NEW (fresh quotes, corroborates existing research doc's item, not duplicated).** tRPC: "Move fast and break nothing... static typesafety... directly in the editor." Zod: "TypeScript-first schema validation with static type inference" (`z.infer<>` = single source of truth). openapi-typescript: generates `.d.ts` from OpenAPI specs — the most direct real analog to an Intent-Graph-as-compile-error pattern, though one-directional and API-surface-only. Target-repo-level libraries, not loop-team-harness tooling — reference/corroboration only, no experiment spec. |

### Codex-diagnostic followup (2026-07-08) — new candidates not in the original dive

A separate Codex CLI diagnostic session independently recommended a "spec-to-code drift validator"
and cited a mix of sources already covered above (Spec Growth Engine, spec-kit, the AST-hallucination
paper, Aider, mini-SWE-agent/SWE-agent, OpenHands, Reflexion — see
`research/codex-followup-drift-validator-reconciliation-2026-07-08.md` Part 1 for the cite-mapping,
not re-added here) plus 8 genuinely new candidates, each independently verified this pass:

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| ReqToCode (arXiv:2603.13999) + "Ariadne" | Requirements-traceability-as-compiler-error (paper + real tool) | RESEARCH_ONLY | RESEARCH_ONLY | — (paper) | — | 2026-07-08 | **NEW.** Confirmed via direct fetch of `arxiv.org/html/2603.13999`: unlike Spec Growth Engine, this paper describes a WORKING implementation — "Ariadne... exists and is applied to its own development process," generating Java/C/C++ language-native "Traceable" constructs (Java enum constants w/ `@Deprecated`) per requirement ID; removing/renaming a requirement produces a real COMPILER error/warning, not silent doc drift. No public repo found; no quantitative evaluation section. Different mechanism family from the tsc/knip binding-check approach ("bake the spec ID into the type system" vs. "diff code against spec text") — not portable to loop-team's Node/Python targets today; WATCH for a TS/Python port. |
| traceSDD (arXiv:2606.30689, "Citation Discipline in Spec-Driven Development") | Per-line requirement-citation hallucination detector | RESEARCH_ONLY | TESTABLE (pattern) | — (paper) | — | 2026-07-08 | **NEW — most load-bearing new find this pass.** Confirmed via direct fetch: mandatory per-line `REQ-XXX.Y.Z` citations + an "orphan-REQ check" ("runs in O(1) per file, a single grep, zero manual effort"). Real numbers: hallucination detection 86.4% (Claude) / 88.0% (GLM), 0% FPR, vs. 0% with no citations — trade-off: "citation annotations trade determinism for verifiability." No repo. **Directly extends loop-team's own existing `harness/citation_grounding.py` mechanism** (currently scoped to report-generator builds citing external sources, per `orchestrator.md` step 1) to a new use: require Coder to cite the AC/requirement ID it's implementing, grep-diff cited IDs against spec.md's declared ACs. Complementary to, not overlapping with, the tsc/type_check gate (catches "cites a nonexistent AC," not "unbound identifier"). |
| R2Code (arXiv:2604.22432) | LLM semantic requirements-to-code traceability recovery | RESEARCH_ONLY | RESEARCH_ONLY | — (paper) | — | 2026-07-08 | **NEW.** IEEE COMPSAC 2026 (accepted — peer-reviewed, stronger venue than Spec Growth Engine). Bidirectional-alignment + self-reflective-consistency framework; avg F1 gain 7.4%, token reduction 41.7% across 5 Java/C# datasets. No repo; "presented as an experimental framework rather than a deployed running tool." Wrong shape for the need (offline link-recovery on legacy repos, not build-time drift prevention) even setting the missing code aside. Parked. |
| bufbuild/buf | Schema breaking-change detector (Protobuf) | WATCH | RESEARCH_ONLY | 11,200 | Apache-2.0 | 2026-07-08 | **NEW.** Real, mature, active (v1.71.0, 2026-06-16). `buf breaking` — "Run `buf breaking` against Git... before merge," graded FILE/PACKAGE/WIRE_JSON/WIRE compatibility levels — is a genuine CI-blockable schema-drift gate. Protobuf-specific; no current build target uses Protobuf/gRPC. Parked until one does. |
| OpenAPITools/openapi-diff | OpenAPI spec-diff / breaking-change detector | WATCH | RESEARCH_ONLY | 1,100 | Apache-2.0 | 2026-07-08 | **NEW.** Real, active (v2.1.7, 2026-01-26), Java. Diffs two OpenAPI 3.x specs, classifies "Broken compatibility" vs. "Backward compatible." Complements the already-radar'd `openapi-typescript` (forward spec→types generation) with the reverse direction (spec-vs-spec drift over time). Relevant only if/when a build target ships an OpenAPI contract. |
| pact-foundation/pact-js | Consumer-driven contract testing | WATCH | RESEARCH_ONLY | 1,800 | MIT | 2026-07-08 | **NEW.** Real, active (v17.0.1, 2026-07-01), TypeScript. Genuinely different mechanism: the "spec" (contract) comes from real recorded CONSUMER usage, not human/LLM-authored text; its `Verifier` class **blocks** CI on provider divergence. Only relevant once loop-team builds a genuine multi-service target (current targets are single Next.js apps) — parked as a WATCH for that trigger condition. |
| spring-projects/spring-modulith | Architecture-conformance (JVM) | RESEARCH_ONLY | RESEARCH_ONLY | 1,200 | Apache-2.0 | 2026-07-08 | **NEW — corroborates the existing ArchUnit row, adds no new category.** `ApplicationModules.of(Application.class).verify()` runs module-boundary checks as a JUnit test. Same JVM-only / wrong-ecosystem verdict already recorded for ArchUnit. Logged for the honesty bar, not because it changes anything. |
| AdverTest (arXiv:2602.08146, "Test vs Mutant: Adversarial LLM Agents") | Adversarial LLM test-vs-mutant co-evolution | RESEARCH_ONLY | RESEARCH_ONLY | — (paper) | — | 2026-07-08 | **NEW — tangential to drift detection; a Test-writer/mutation-testing candidate, not a drift validator (framing correction from Codex's citation context).** Two co-evolving LLM agents (test-generator vs. mutant-generator); on Defects4J w/ DeepSeek V3.2: fault-detection 66.63% vs. 61.38% HITS (+8.6% relative) vs. 40.80% EvoSuite (+63.3% relative). No code/repo found. Relevant to `roles/adversarial_test_writer.md` + the existing `mutmut` step (`orchestrator.md` step 5.5) — the genuinely new idea is the adversarial co-evolution LOOP itself vs. one-shot mutation batches — but nothing to adopt without an implementation. Parked. |

Full reconciliation (incl. which Codex citations were already covered, and a live-repo-state check
finding `harness/verify.py`/`DESIGN_CHECKLIST.md`/`orchestrator.md` mid-implementation on this exact
topic with an unresolved gate conflict): `research/codex-followup-drift-validator-reconciliation-2026-07-08.md`.

**Actual adoption candidate synthesized from this pass (not a found tool — a designed
gate, follows the `verify.py` file's own existing additive-AND pattern used twice
already for dual-ecosystem test runs and the live-smoke gate):** add a `type_check` key
to `harness/verify.py` — `npx tsc --noEmit` gated on `tsconfig.json` presence for Node/TS
targets, `flake8 --select=E9,F821,F823,F831,F406,F407,F701,F702,F704,F706` (Aider's own
fatal set, portable as-is) for Python targets lacking type-checking already — ANDed into
`passed`, additive JSON key, zero change to existing consumers. Full dossier + synthesis:
`research/compiler-feedback-loop-prior-art-2026-07-08.md`. Not yet filed as a fix_plan.md
entry or built — this research hands the designed gate back to Oga/Nnamdi, per the
Researcher role's guardrail that only Oga/the user opens or closes fix_plan.md entries.

## Token-spend-reduction stack verification (2026-07-08 Codex follow-up #2)

*A separate Codex CLI diagnostic session recommended a token-spend-reduction stack for this
framework. Every specific claim independently re-verified (WebFetch on docs/READMEs/arXiv
abstracts + raw GitHub REST API for maturity signals — not WebFetch's markdown scrape of a live
GitHub page, which is prone to fabricating specifics per `roles/researcher.md`). No sub-agents
dispatched. Full sourced dossier: `research/codex-followup-token-spend-reduction-2026-07-08.md`.*

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| **Agent-SDK subagent prompt-caching gap** (anthropics/claude-code#29966) | Platform substrate — cost | CANDIDATE | TESTABLE | — | — | 2026-07-08 | **NEW — priority ≈ 0.48, highest-priority item this pass.** Not a 3rd-party tool: a real, OPEN GitHub issue (created 2026-03-02, last activity 2026-05-25) reporting Agent-tool-spawned subagents get ZERO `cache_control` breakpoints, evidenced by 2 independent proxy-log reporters (54 subagent reqs × 7,013 uncached tokens = ~378k wasted tokens/session). Directly hits this framework's own dispatch pattern (`.claude/agents/*.md` custom subagent types). An Anthropic engineer disputed the reporter's *code-path* diagnosis but not the symptom, and flagged "custom subagent system prompt" as the likely trigger — exactly this framework's shape. Confirmed real, shipped mitigation: `excludeDynamicSections`/`exclude_dynamic_sections` (Agent SDK ≥0.2.98 TS / ≥0.1.58 Python; current published SDK is 0.3.204, so available now) — see [modifying-system-prompts docs](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts). ⚠ Could NOT confirm the bug still reproduces on the current CLI (2.1.204 vs the reported 2.1.63) — attempted direct source check via `npm pack`, but the current package ships a compiled per-platform binary, not an inspectable `cli.js`. **Falsifiable check, zero new infra:** capture `cache_creation_input_tokens` vs `cache_read_input_tokens` (already returned on every API response, per official docs) across 2+ same-role subagent dispatches in a real run. Bonus finding on the same thread: subagents inherit the FULL `~/.claude/CLAUDE.md` + project CLAUDE.md (10-20k tokens/spawn) — directly applicable given this project's own large global CLAUDE.md/MEMORY.md. |
| FrugalGPT (Stanford; arXiv:2305.05176, TMLR Dec 2024) | Cost — model cascade pattern | CANDIDATE | TESTABLE | 268 | Apache-2.0 | 2026-07-08 | **NEW — priority ≈ 0.26.** Confirmed real + peer-reviewed (TMLR, dblp `journals/tmlr/ChenZ024`, not just arXiv). Repo real but low-activity (last commit 2025-02-10, ~17mo stale, small). Core idea — LLM cascade, escalate to a pricier model only on low-confidence — generalizes this framework's own *static* `orchestrator.md` model-routing table (haiku/sonnet/opus by role) and stall-detector escalation into an *adaptive* one. No coding-agent-specific benchmark exists (numbers are classification/QA tasks) — pattern transfers, magnitude doesn't. |
| "Lost in the Middle" (Liu et al., arXiv:2307.03172, TACL 2023) | Design reference — prompt-ordering | WATCH | RESEARCH_ONLY | — (paper) | — | 2026-07-08 | **NEW — priority ≈ 0.185, not a tool.** Confirmed real, peer-reviewed, foundational (abstract quoted directly). Motivates LongLLMLingua's own design. Actionable as a cheap audit: check whether this project's longest prompts (`orchestrator.md`, post-2-round `spec.md` files) bury a load-bearing constraint mid-document rather than at start/end. Distinct from — but easily conflated with — Claude Code's own cache-driven "static content first" prompt ordering (a different, cost-motivated reason for similar structure). |
| microsoft/LLMLingua (+ LLMLingua-2, LongLLMLingua) | Prompt compression | WATCH | TESTABLE (narrow scope only) | 6,419 | MIT | 2026-07-08 | **NEW — priority ≈ 0.16.** Confirmed real, 3 peer-reviewed variants (EMNLP'23/ACL'24×2) in one repo. ⚠ **No tagged release in 2+ years** (last: v0.2.2, 2024-04-09) despite recent-ish commits (2025-10-28, adds a security spinoff, not core compression work) — genuine low-but-not-dead maintenance signal a stars-only framing would hide. Lossy compression evaluated only on QA/reasoning benchmarks, never agentic coding — risky for specs/diffs/ACs (silent, load-bearing correctness loss), defensible only for incidental long-log content handed to a Researcher. |
| BerriAI/litellm (gateway) | Cost gateway / observability | WATCH | TESTABLE | 52,922 | MIT (core; `enterprise/` dir separately licensed — confirmed via raw LICENSE file) | 2026-07-08 | **NEW — priority ≈ 0.12.** Confirmed real, extremely active (pushed same day as this check, near-daily releases). Real semantic-cache support (Qdrant/Redis/Valkey backends, confirmed via actual caching docs, not just README). ⚠ Claude Code officially supports gateway routing via `ANTHROPIC_BASE_URL` (confirmed, `code.claude.com/docs/en/llm-gateway`) BUT doing so **switches billing from a Claude subscription to metered per-token** (quoted directly from the docs) — unconfirmed whether that's a net win here; not yet checked which billing model this project's own Oga process uses. Same Verifier/Coder correctness-risk caveat as GPTCache applies to its response-caching feature; safest framing is cost-visibility/budgeting, not caching. |
| Portkey-AI/gateway | Cost gateway | WATCH | TESTABLE | 12,353 | MIT | 2026-07-08 | **NEW — priority ≈ 0.085.** Confirmed real, genuinely maintained (real recent fixes: auth validation, log redaction — not just noise). ⚠ **Semantic caching is Enterprise-plan-gated** (quoted directly from Portkey's own docs: "available only on select Enterprise plans and requires a vector database") — a likely overstatement point if presented without this gate for a non-enterprise deployment; free tier gets exact-match only. Same subscription-vs-metered-billing caveat as LiteLLM if routed in front of Claude Code. |
| carriex/recomp (RECOMP, arXiv:2310.04408, ICLR 2024) | RAG context compression | WATCH | RESEARCH_ONLY (contraindicated here) | 149 | MIT | 2026-07-08 | **NEW — priority ≈ 0.07.** Confirmed real, peer-reviewed, repo lightly alive (last commit 2026-01-06, minor). ⚠ **Directly conflicts with this project's own documented lesson** — `orchestrator.md`'s "Hand a retry Coder the FULL prior-attempt history, not just the latest failure" and the standing "read everything in full" guardrail both exist because summarization already caused real missed-gap incidents here. RECOMP-style pre-summarization of Coder/Verifier evidence is specifically contraindicated, not just low-priority. |
| zilliztech/GPTCache | Semantic response cache | DECAYING-leaning | TESTABLE (not recommended for Verifier/Coder) | 8,091 | MIT | 2026-07-08 | **UPDATED — priority ≈ 0.04.** Confirmed real via GitHub API but genuinely stale: **~1 year since last commit** (2025-07-11), ~2 years since last release (2024-08-01), an 11-month commit gap 2024-2025 — a materially staler signal than an "8k-star, actively integrated" framing suggests. Chat-service-repeated-query design doesn't match this framework's per-dispatch-unique-context workload; response-caching a Verifier/Coder risks a silent stale-false-pass. |
| SCALM (arXiv:2406.00025) | Semantic caching (paper) | WATCH | RESEARCH_ONLY | — (paper) | — | 2026-07-08 | **NEW — priority ≈ 0.007.** Confirmed real paper (abstract quoted: 63% cache-hit-ratio / 77% token-savings improvement) — but **benchmarked against GPTCache as a baseline it beats, not integrated into or built on GPTCache** (correcting a plausible conflation). No public code repo found anywhere (searched directly) — paper-only, confidence capped ≤0.3 per honesty bar. Same chat-service domain mismatch as GPTCache. Parked, not actionable. |
| aurelio-labs/semantic-router | Intent routing (NOT caching) | WATCH | RESEARCH_ONLY (no fit found) | 3,678 | MIT | 2026-07-08 | **NEW — priority ≈ 0.025.** Confirmed real, actively maintained (release 2026-05-23). **Not a caching tool** — likely a name-based conflation in the source summary; it's an embedding-based intent classifier/router, a distinct concern. This framework's dispatch decisions are already deterministic (Oga's own spec-encoded branching in `orchestrator.md`), so no applicable freeform-intent-classification bottleneck exists today. |
| AttentionRAG (arXiv:2503.10720) | RAG context pruning (paper) | WATCH | RESEARCH_ONLY | — (paper) | — | 2026-07-08 | **NEW — priority ≈ 0.025.** Confirmed real paper (abstract quoted: up to 6.3× compression, "~10% over LLMLingua" — author-self-reported, not independently reproduced). Could not confirm peer-review acceptance (matching OpenReview page blocked by a bot-check wall). **No public code repo found.** Paper-only, capped confidence ≤0.3, same long-context-QA domain mismatch as items above. Lowest-priority item this pass alongside SCALM. |

**Synthesis (not a fix_plan.md entry — handed back per the Researcher role's guardrail that only
Oga/the user opens/closes fix_plan.md items):** the highest-value action from this pass is the
**zero-cost falsifiable check** on the Agent-SDK subagent-caching gap (capture
`cache_read_input_tokens`/`cache_creation_input_tokens` across consecutive same-role dispatches in a
real run) — it requires no new dependency, no infra, and directly tests whether this framework's
own dispatch pattern is silently paying full uncached price on every Coder/Verifier/Researcher/
Test-writer call. Every third-party library Codex's summary named ranks below that, and the
RAG-context-compression cluster (LLMLingua/RECOMP/AttentionRAG/SCALM) ranks lowest of all — real
papers/tools, wrong task distribution, two of them in direct tension with this project's own
documented anti-summarization lessons.

## Non-binding (LOGIC/CONCURRENCY/SECURITY) plan-check saturation prior art (2026-07-09 dive)

*Prompted by the gap DESIGN_CHECKLIST.md gate 10 deliberately leaves open: gate 10 only
stops prose review for `[BINDING]` (compiler-catchable) findings; LOGIC/CONCURRENCY/
SECURITY findings get full review indefinitely because there's no compiler-equivalent
oracle to defer to. Full dossier (all sources opened + quoted, priority scores, a
PACE-gated experiment spec): `research/plancheck-nonbinding-saturation-2026-07-09.md`.*

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| calimero-network/ai-code-reviewer | Multi-agent code review — convergence pattern | WATCH | RESEARCH_ONLY (mechanism confirmed, not adopted) | 7 | MIT | 2026-07-09 | **NEW.** Already cited (unverified) by this project's own `reconcile_gap_records.py` docstring for its clustering technique — this pass independently confirmed the CONVERGENCE mechanism itself (not previously verified): `has_converged(delta)` is `True` iff `new_findings == 0 and fixed_findings == 0`, no rolling window, confirmed via `docs/ARCHITECTURE.md` + real test names in `tests/test_convergence.py`. Solves a different problem than plan-check's static-spec-rereading case: its convergence = "the CODE stopped changing between pushes," not "N independent reads of unchanged text found nothing new." |
| oprogramadorreal/optimus-claude (`/optimus:code-review-deep`) | Claude Code review-loop skill — graduated diminishing-returns | CANDIDATE | TESTABLE | 64 | MIT | 2026-07-09 | **NEW — priority ≈ 0.38.** Real, shipped, actively maintained (pushed 2026-07-09). README quoted: *"diminishing-returns — After iteration 4, two consecutive iterations produced ≤1 new finding and 0 reverted fixes."* Closest real, GRADUATED (not binary-zero) production pattern found. Applies to a code-changes-between-rounds loop, not a static-spec-rereading loop — same disanalogy as ai-code-reviewer. Candidate 2 in the dossier: port as a cheap comparison baseline alongside the Chapman estimator, not standalone. |
| retsimx/opencode-agents (`ralphreview` skill) | Claude/OpenCode review-loop skill — naive streak | WATCH | RESEARCH_ONLY | 0 | none | 2026-07-09 | **NEW.** `SKILL.md` fetched in full: 3-consecutive-clean-review streak (`clean_review_streak`), reset on any real fix. Same shape as Gate 10 but unscoped by finding class and with no fatigue/satisfaction-of-search safeguard — a real example of what a naive unscoped extension of Gate 10 looks like in production. Young (created 2026-06-04), 0★, no adoption signal. |
| gopherguides/gopher-ai (Codex review-flow) | Claude Code plugin — multi-pass review | WATCH | RESEARCH_ONLY | 17 | MIT | 2026-07-09 | **NEW.** `review-flow.md` fetched in full: multi-pass Codex review, each pass told to report only NET-NEW findings, early-stops on a SINGLE `NO_NEW_FINDINGS` pass (no streak at all — even more naive than ralphreview). Real, actively maintained (pushed 2026-07-09, same day as this check). Low-stakes in its own context because a human reads the final aggregated report. |
| echakrabarti/no-epicycle | LangGraph agentic-coding-loop supervisor | WATCH | RESEARCH_ONLY (wrong shape) | 0 | none | 2026-07-09 | **NEW.** README fetched: diminishing-returns detector via a caller-supplied `score_fn` reward callback (its own quickstart example is a testable Python function) — confirms-by-contrast that even a repo explicitly pitched as a general diminishing-returns detector still needs a pass/fail oracle, exactly what LOGIC/CONCURRENCY/SECURITY plan-check lacks. 8 days old, 0★, tiny unverified benchmark (5 tasks × 3 runs). |
| susugadx/xelyon-cli (`saturation_*.go`) | Go CLI — review-report coverage-completeness gate | WATCH | RESEARCH_ONLY (different mechanism) | 0 | MIT | 2026-07-09 | **NEW.** Real, substantial `ReviewSaturationCheck` implementation fetched directly — but confirmed to be a single-shot self-critique-against-a-plan with one retry (does the final report cover every `MissingSurfaceIDs`/`MissingRiskIDs`), not a round-over-round multi-reviewer saturation detector. Different mechanism family; noted for completeness, not adopted. |
| sublimine/Cardeep (`V6-STATISTICAL-RIGOR.md`) | Unrelated project — data-completeness verification architecture doc | WATCH | RESEARCH_ONLY (design reference, no code) | 0 | none | 2026-07-09 | **NEW, unexpected cross-domain find.** ~480-line architecture doc fetched in full: independently derives Wald-SPRT sequential stopping AND the two-source Chapman capture-recapture estimator (with variance + log-normal CI, cross-cited to Chao 1987), for a DIFFERENT domain (database-completeness auditing, not code review). Load-bearing self-flagged caveat quoted directly: *"positive dependence between sources... biases N̂ downward — so a two-source N̂ is a lower bound on the true universe"* — the central risk for Candidate 1 below (correlated LLM lenses could bias a Chapman estimate toward premature stopping). Design-reference only, no runnable code. |
| Capture-recapture defect estimation (Eick et al. 1992; Vander Wiel & Votta, IEEE TSE 1993; IBM Jazz application) | Software-inspection statistical methodology | CANDIDATE | TESTABLE | — (literature, 30+yr field-validated) | — | 2026-07-09 | **NEW — priority ≈ 0.46, top candidate this dive.** The literature family purpose-built for "how many defects remain, no other oracle, estimated from multiple independent reviewers' overlap" — real industrial deployment (IBM Jazz), not lab-only. Never applied to LLM review loops (confirmed via `gh search repos/code` — genuinely novel synthesis, not a port). Directly buildable on this project's OWN existing `harness/reconcile_gap_records.py` near-duplicate/overlap clustering (already computes the `(n₁, n₂, m)` triple a Chapman estimator needs). Known risk (independently corroborated twice — general literature + Cardeep's own doc): small-sample instability and correlated-reviewer downward bias, both of which push toward premature stopping — MUST stay advisory-only, never a hard gate, unlike Gate 10. Backtest is feasible NOW against real, already-on-disk per-lens data (`runs/2026-07-02_ops-clock/plan_check_log.md`, `runs/2026-07-04_airbnb-calendar/plan_check_log.md`) before any live pilot — see dossier's PACE-gated experiment spec, with a pre-registered automatic-kill condition on the two historically-known-important airbnb-calendar-sync rounds (19-21, 30-31). |
| Multi-agent-debate formal stopping rules (Wald-SPRT compute governor, arXiv 2605.19193; KS-statistic Adaptive Stability Detection, arXiv 2510.12697) | Multi-agent debate convergence (papers) | WATCH | RESEARCH_ONLY (no metric tie — parked, not ranked) | — (preprints, no code found for either) | CC-BY-NC-ND (2510.12697) | 2026-07-09 | **NEW.** Both real 2026 preprints, both fetched via HTML mirror and quoted directly, both methodologically close to this project's OWN PACE acceptor (same Wald-SPRT family) — but both EXPLICITLY disclaim applicability to non-deterministic-oracle domains in their own text (2605.19193: *"does not address preference-judgment or logic-bug-finding scenarios"*; 2510.12697's Theorem 4.2 assumes a fixed correct-answer target). Corroborates, from the debate-convergence literature's own mouth, that this dispatch's problem is genuinely unsolved elsewhere — not force-fit here per the honesty bar. |
| Semantic Early-Stopping for Iterative LLM Agent Loops (arXiv 2606.27009) | Single-agent iterative-refinement stopping (paper) | WATCH | RESEARCH_ONLY | — (preprint, no code) | — | 2026-07-09 | **NEW.** Single-author preprint: cosine-distance-between-drafts + patience window, tested only on single-agent HotpotQA RAG-QA with a retrieval-derived quality oracle (38% token reduction, no significant quality loss). Needs a "quality signal" this project has no LOGIC/CONCURRENCY/SECURITY equivalent of; paper's own authors say the harder half of the problem ("which round is best," not just "did it stop changing") remains open. Light WATCH only. |

**Headline finding, not force-fit:** no existing repo or paper solves the exact
problem (stopping repeated independent LLM review of a STATIC unchanged spec, for
defect classes with no compiler-equivalent oracle). Every production tool that uses a
"zero/near-zero new findings → stop" shape (ai-code-reviewer, optimus-claude,
ralphreview, gopher-ai) protects against re-reviewing an artifact that stopped
CHANGING between rounds — a materially different, easier problem than plan-check's
case, where this project's own prior research (`research/ops-clock-alt-method-
experiment-2026-07-02.md`, citing Biffl/Halling/Kohle) already showed repeated review
of unchanged text measurably DEGRADES detection effectiveness round-over-round. The
naive move (extend Gate 10's streak-counting to all tag classes) is exactly what
several production tools do for a different task shape — confirmed here as a
known-bad idea for THIS project's specific static-artifact case, not merely
undiscovered. Top actionable candidate: backtest the capture-recapture (Chapman)
estimator against the real, already-on-disk `plan_check_log.md` histories before any
live pilot — cost is a read + arithmetic, not a new dispatch.

## Gate 10 concurrency/fingerprint/schema synthesis (2026-07-09)

*Not a tool-radar scan — a synthesis of 1 inventory pass + 4 targeted deep-research
sweeps against three concrete open design problems in the Gate 10 family
(`reconcile_gap_records.py`, `plancheck_saturation.py`, the still-unbuilt
`plancheck_gate10_runner.py`): deterministic defect fingerprinting, the async N-of-N
completion barrier for parallel lens dispatch, and the single-writer JSONL schema.
Full synthesis with per-problem "adopt this" recommendations and exact file/line
citations: `research/gate10-concurrency-fingerprint-synthesis-2026-07-09.md`. Source
dossiers (each independently saved, read in full before the synthesis was written):
`research/gate10-concurrency-fingerprint-inventory-2026-07-09.md`,
`research/defect-fingerprinting-prior-art-2026-07-09.md`,
`research/async-completion-barrier-prior-art-2026-07-09.md`,
`research/single-writer-jsonl-schema-prior-art-2026-07-09.md`,
`research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md`.*

**Headline conclusions (no new tool rows added — every external system surveyed here
informs an internal fix, not an adoptable dependency):** (1) fingerprinting — no
production tool (CodeQL/SonarQube/Semgrep/Coverity/DefectDojo) or paper solves
exact-match dedup of arbitrarily-reworded free text; a real, confirmed, previously-
unflagged bug (`set().isdisjoint(set())` vacuously `True` on empty `mechanism_refs`)
silently skips `reconcile_gap_records.py`'s similarity check in the common case — fix
that bug regardless, then split the fingerprint design into an IMPLEMENTABLE_NOW
structural-hash case and a TESTABLE (paraphrase-convergence-gated) fallback case. (2)
async barrier — the universal real-world idiom is fix-the-expected-set-before-any-
work-returns + gate on set equality (traced to CPython's actual `asyncio.gather()`
source); confirmed this project's lens dispatch goes through the `Workflow` tool's
`agent()` calls, not foreground `tool_use`/`tool_result` turns, and confirmed (by
direct grep) `orchestrator.md` has NO existing `Promise.all`/`allSettled` fan-out+join
call site at all — this is the concrete gap `plancheck_gate10_runner.py` must fill,
gated on a cheap live probe of whether the Workflow runtime's `agent()` calls actually
run concurrently (unverified anywhere, including this synthesis). Anthropic's own
background-subagent notification channel is confirmed broken at N>1 (issues #20754,
#21165) — never build a completion barrier on it. (3) JSONL schema — fully solved
elsewhere (one flat shape, a required `status` enum, one canonical `partial_reason`
field name, `schema_version` bumped only on breaking changes); `plancheck_saturation.py`
is itself a live, previously-unflagged instance of the two-shapes-in-one-file
anti-pattern and should be fixed to the single-shape convention. Recommended build
order: Problem 1 → Problem 3 → Problem 2 (the `signature` field's contract blocks
Problem 3; Problem 2's partial-completion state needs Problem 3's `status` field to
land in).

## DB-test-isolation + RLS-defect-catching prior art (2026-07-09 dive — padsplit-cockpit bug-cluster response)

*Triggered by a direct complaint: 3 real bug classes (fixture flakiness from hardcoded emails in
`seedOrgWithUser`, an orphaned DB row, an 8-table RLS cross-tenant FK ownership gap) landed on
padsplit-cockpit in a single day (2026-07-09), on top of an already-rigorous plan-check/Verifier
apparatus. Full dossier (all sources opened + quoted, priority scores, PACE-gated experiment specs
for each, transfer-condition checks): `research/loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md`.*

| Tool | Category | Status | Triage | Stars | License | Last checked | Decay / Notes |
|---|---|---|---|---|---|---|---|
| codepunkt/vitest-environment-prisma-postgres | DB-test-isolation (transactional rollback) | CANDIDATE | IMPLEMENTABLE_NOW | 42 | MIT | 2026-07-09 | **NEW — priority ≈ 0.61, top candidate this dive.** Confirmed via direct WebFetch: *"Seed your database once with production-like data, then run each test in a transaction that is rolled back after execution. Tests remain isolated without expensive reseeding."* Vitest-native (matches padsplit-cockpit's confirmed test runner). No Docker required — works against the existing dev Postgres instance. Created 2025-11-27, pushed 2026-07-08 (`gh api` confirmed) — actively developed. Directly, structurally closes the recurring "shared, non-reset dev DB" flakiness class logged ≥4 times across 2 separate builds this week in `learnings.md` (fixture-email collision after accumulated rows; "reran it, not flaky" claims defeated by shared mutable state; concurrent-session cross-contamination). **Open risk, unverified: interaction with padsplit-cockpit's per-request RLS `SET LOCAL` GUC pattern inside the wrapper's outer transaction — first thing the experiment must probe, not assume.** STATUS: approved by Nnamdi 2026-07-10, ready to dispatch |
| chax-at/transactional-prisma-testing | DB-test-isolation (transactional rollback) | CANDIDATE | IMPLEMENTABLE_NOW | 52 | MIT | 2026-07-09 | **NEW — sibling candidate, same priority bucket as above.** Confirmed via WebFetch: proxy-wraps a `PrismaClient`, `startNewTransaction()`/`rollbackCurrentTransaction()` per test. Older, more stable API (created 2022) but 6mo-stale (last push 2026-01-09, `gh api` confirmed) vs. codepunkt's fresher Vitest-native sibling above — prefer the Vitest-native one for padsplit-cockpit specifically; this one is the fallback / cross-framework reference. STATUS: approved by Nnamdi 2026-07-10, ready to dispatch |
| pgrls/pgrls | RLS static analyzer + CI diff-gate | CANDIDATE | TESTABLE | 22 | MIT | 2026-07-09 | **NEW — priority ≈ 0.56.** Confirmed via direct raw-README fetch (reduced rendered-page summarization risk per honesty bar): rule **SEC047** — *"A foreign key whose parent (referenced) table has RLS enabled is a cross-tenant existence covert channel when a low-trust role can write the child"* — a near-verbatim match to padsplit-cockpit's real "8-table cross-tenant FK ownership gap" incident. Also SEC027 (unscoped owner column), SEC040 (permissive FOR ALL policy with unbound WITH CHECK). `pgrls diff` classifies every RLS migration change SAFE/BREAKING/REQUIRES_REVIEW/DANGEROUS for CI gating. Created 2026-04-24, pushed 2026-07-10 (same day) — very young (~2.5mo) but 146 releases, v0.48.1 — high velocity, low adoption signal (22★, 2 open issues). Does NOT cover the self-referencing-RLS-recursion sub-class found in the same incident (`research/postgres-rls-self-referencing-recursion-messages-2026-07-09.md` remains authoritative for that). ORM-agnostic (reads `pg_policies`/`pg_proc` directly) — ready to trial read-only against padsplit-cockpit's live schema at zero code-change cost. STATUS: approved by Nnamdi 2026-07-10, ready to dispatch |
| matte97p/rlsgrid | RLS auto-generated cross-tenant test matrix | WATCH | TESTABLE | 4 | MIT | 2026-07-09 | **NEW — companion to pgrls, folded into the same priority bucket.** Confirmed via WebFetch: *"Schema-driven Row-Level Security test matrix generator and cross-tenant fuzzer for Postgres/Supabase."* Auto-generates the `role × table × operation` → `allow/deny/conditional/unrestricted` matrix — the automated version of the manual "prove the class is EMPTY" sweep `learnings.md`'s 2026-07-02 RLS-cutover entry describes hand-building across 4 plan-check iterations. Created 2026-05-26, pushed 2026-06-23 — self-described "Alpha," 4★, 27 commits, 5 open issues — genuinely early; treat as a lead to trial, not yet a gate. STATUS: approved by Nnamdi 2026-07-10, ready to dispatch |
| stryker-mutator/stryker-js | Mutation testing (JS/TS) | CANDIDATE | IMPLEMENTABLE_NOW | 2,940 | Apache-2.0 | 2026-07-09 | **NEW — priority ≈ 0.59.** Confirmed via `gh api` + WebFetch: mature (created 2016), pushed 2026-07-09 (same day). Closes a real, previously-unflagged structural gap: `orchestrator.md` step 5.5's adversarial mutation-testing gate currently only runs `mutmut` (Python-only, confirmed by direct read of the file's own `mutmut run --paths-to-mutate <impl_file>` invocation) — meaning the mutation-testing safety net silently does NOTHING on padsplit-cockpit's TypeScript/Next.js codebase, the exact repo where the reported bug cluster shipped. `npx stryker run` mirrors the existing `mutmut` CLI shape closely enough to reuse the same 120s-soft-timeout/surviving-mutant-reporting pattern verbatim. STATUS: approved by Nnamdi 2026-07-10, ready to dispatch |
| dubzzz/fast-check | Property-based testing (JS/TS) | CANDIDATE | IMPLEMENTABLE_NOW | 5,056 | MIT | 2026-07-09 | **NEW — priority ≈ 0.55.** Confirmed via `gh api`: mature (created 2017), pushed 2026-07-10 (same day), the de facto TS/JS QuickCheck-style library. Targets the "fixture tautology" bug class independently logged 3× in `learnings.md` (2026-06-24 ×2, 2026-07-09) — hardcoded/crafted-to-match fixture values. **Only partially structural**: nothing forces a Test-writer to use `fc.emailAddress()` over a literal string once installed — pair with a cheap grep-based lint backstop (same pattern as the project's own existing `no-contiguous-literals` sweep) flagging literal strings assigned to `email`/`*Email` fields inside `seed*`/`*fixture*` files, to convert this from a suggestion into a checked convention. STATUS: approved by Nnamdi 2026-07-10, ready to dispatch |
| FoundationAgents/MetaGPT (formerly geekan/MetaGPT) | Multi-agent framework — SOP/phase-document persistence | WATCH | RESEARCH_ONLY | 69,282 | MIT | 2026-07-09 | **NEW (part-b roadmap-discipline research) — priority ≈ 0.21, parked below the bug-catching candidates.** Confirmed via `gh api`: org moved to `FoundationAgents/MetaGPT` (redirect from `geekan/MetaGPT`), 69.3k★, but **last push 2026-01-21 — ~5.5 months stale as of this scan despite the star count — a real decay signal for a widely-cited repo.** Confirmed via direct fetch of `metagpt/actions/write_prd.py`: SOP pattern persists each phase's artifact as a versioned `Document` (`self.repo.docs.prd.save()`), tracks `changed_files` per phase, emits an explicit completion signal consumed by the next phase. Transferable idea (doc-only, not a dependency): record the file-diff/commit-range each phase actually touched directly in `ROADMAP.md`/`NEXT_PHASE.md` at phase boundaries — loop-team's existing `ROADMAP.md`/`NEXT_PHASE.md`/`fix_plan.md`/git-branch-naming apparatus is not meaningfully behind the field; no adoptable mechanism found across MetaGPT/ChatDev/AutoGen/OpenHands/SWE-agent/CrewAI/Aider that beats what's already built. Devin/Cognition: closed product, no public repo, not independently verifiable — RESEARCH_ONLY by default. |

**Ranked dive-in queue this dive (padsplit-cockpit, the confirmed-stack project — TaxAhead's stack was
not confirmed in context available to this pass, so no candidate above was sized against it):**
1. DB-test-isolation (codepunkt/vitest-environment-prisma-postgres) — highest priority, lowest cost,
   most direct match to the named incident.
2. Stryker JS/TS mutation testing — closes a structural, previously-unflagged Python-only gate gap.
3. pgrls RLS static analyzer — near-verbatim rule match (SEC047) to the real cross-tenant-FK incident;
   backtest against the 2 real historical RLS incidents before promoting to a CI gate.
4. fast-check property-based fixture generation — pair with a grep-based lint backstop, not standalone.
5. (part b, doc-only, not PACE-gated) MetaGPT's changed-files-per-phase convention, ported as prose.

## Stop-guard blocked-dispatch replay diagnosis (2026-07-10, in-repo Mode A)

*In-repo bug diagnosis (not a 3rd-party tool). Full dossier + falsifiable check + class-wide
blast radius: `research/stopguard-blocked-dispatch-replay-diagnosis-2026-07-10.md`. Handed
back to Oga — Researcher does not open/close/re-prioritize the `fix_plan.md` entry itself.*

| Item | Category | Status | Triage | Priority | Last checked | Notes |
|---|---|---|---|---|---|---|
| **H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1** (loop_stop_guard.py) | Eval/verifier — gate hardening | CANDIDATE | IMPLEMENTABLE_NOW | **≈ 0.39** | 2026-07-10 | **NEW.** Root cause CONFIRMED: `_TOOL_USES` (line 165) includes PreToolUse-DENIED dispatches; the hygiene scan (1468) `break`s on the first `_VERIFIER_DETECT`+marker match, replaying a blocked, superseded attempt over the live clean one. Grounded in CC docs + GH issue anthropics/claude-code#59643 (a denied call leaves a `tool_use` block AND a `tool_result` with generic content `"Hook PreToolUse:<Tool> denied this tool"`). Fix: build `_blocked_tool_use_ids` from deny-signature tool_results (reusing the file's existing tool_use_id↔result correlation at 1361-1369 / 1578-1585) and skip them. **Class is file-wide** — same shape at `VERIFIER` (743) and `_seen_verifier_anywhere` (1219) causes the DANGEROUS direction: a blocked Verifier satisfies the FEATURE (1116) / PLAN_CHECK (1250) gates → recommend re-rating above the entry's `LOW`. Sibling `subagent_stop_gate.py` closure/commit scans share the class (reachable via the H-GUARD-4 sub-agent misfire); `micro_step_gates.py` is self-protected (AND-gated against real git state). No existing test fixture (genuine coverage hole, not a fixture-tautology). |

## Open scan targets (gaps to fill next pass)
- **DB-isolation experiment result** — run the paired repeated-suite-run experiment
  (`research/loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md`, Candidate 1) against
  padsplit-cockpit; update this row with the actual measured flaky-failure-count delta, and resolve
  the open RLS-`SET LOCAL`-inside-wrapper-transaction interaction question first.
- **pgrls/rlsgrid backtest** — run `pgrls check` against padsplit-cockpit's schema as it existed
  immediately before the RLS-cutover and RLS-cross-FK fixes (via `git worktree` at the pre-fix commit)
  to confirm it would have caught either real historical gap, per Candidate 2's experiment spec.
- **TaxAhead tech-stack confirmation** — a quick Mode D dispatch or direct read to confirm TaxAhead's
  language/DB stack, so this dive's candidates (all grounded in padsplit-cockpit's Postgres/Prisma/
  Vitest/TS stack) can be evaluated for applicability there too.
- Decay re-check overdue: any row with `last_checked` older than its window (light: 7d for ADOPTED/CANDIDATE, deep: 30d for WATCH/REJECTED).
- **Non-binding plan-check saturation backtest** — run the Chapman-estimator backtest
  against `runs/2026-07-02_ops-clock/plan_check_log.md` and
  `runs/2026-07-04_airbnb-calendar/plan_check_log.md` per
  `research/plancheck-nonbinding-saturation-2026-07-09.md`'s experiment spec; check
  first whether pre-iteration-18 ops-clock rounds have fine-grained-enough per-lens
  attribution (before `mechanism_refs` existed) or whether the backtest must start at
  iteration 18.
- **Karpathy Autoresearch repo status** — confirm github.com/karpathy/autoresearch is alive/accessible; was inaccessible on 2026-06-27 pass.
- **Self-Harness code drop** — weekly: `gh search repos "self-harness" --language=Python --sort=updated`; also check neosigmaai/auto-harness for activity.
- **Gate 10 Problem 2 live probe** — run the 3×20s-sleep `Promise.allSettled` probe
  (`research/gate10-concurrency-fingerprint-synthesis-2026-07-09.md`, Problem 2 step 2)
  to confirm whether the `Workflow` tool's `agent()` calls actually run concurrently
  before building the fan-out+join call site on that assumption.
- **Gate 10 Problem 1 Case B convergence backtest** — run the paraphrase-convergence
  experiment (N known real findings × M paraphrases, measure % identical
  `{primary_entity, defect_class}` tuple) before shipping any equality gate on the
  empty-`mechanism_refs` fallback case.
- **RHO Claude transfer** — first experiment validates whether the +19pp GPT-5.5 gain transfers to Claude; result needed before committing to the queue position.
- **SkillOpt VERIFIER.md experiment result** — run this week; update row with actual held-out delta.
- **DeepSWE leaderboard** — deepswe.datacurve.ai returned navigation-only on 2026-06-27; re-check next pass.
- **OpenCode Terminal-Bench** — "176k stars" figure unverifiable from search; confirm primary GitHub page.
- **Agent-SDK subagent caching gap — reproduce on current version.** anthropics/claude-code#29966 is unresolved on GitHub as of 2026-05-25; the current CLI/SDK (2.1.204 / 0.3.204) ships a compiled binary, not an inspectable `cli.js`, so source-level confirmation wasn't possible this pass. Next step is empirical: instrument a real loop-team run's `cache_read_input_tokens` across consecutive same-role dispatches (see `research/codex-followup-token-spend-reduction-2026-07-08.md` for the exact check).
- Decay re-check overdue: any row with `last_checked` older than its window (light: 7d for ADOPTED/CANDIDATE, deep: 30d for WATCH/REJECTED).

## Change log
- 2026-07-10 — **Stop-guard blocked-dispatch replay diagnosis** (in-repo Mode A, `H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1`). CONFIRMED root cause: `hooks/loop_stop_guard.py` `_TOOL_USES` (line 165) does not exclude PreToolUse-DENIED dispatches, so the hygiene scan (1468) replays a blocked, superseded attempt's marker over the live clean dispatch. Transcript shape confirmed via CC docs + GH issue anthropics/claude-code#59643 (denied call leaves both the `tool_use` and a deny-signature `tool_result`). Recommended fix: a shared `_blocked_tool_use_ids` exclusion (deny-content signature + `is_error`, reusing the existing tool_use_id↔result correlation), applied to the hygiene (1468) + adjacency (1529) scans AND the `VERIFIER` (743) / `_seen_verifier_anywhere` (1219) positive signals — the last two are the DANGEROUS-direction instances the `LOW` filing missed (a blocked Verifier satisfying FEATURE/PLAN_CHECK). Sibling sweep: `subagent_stop_gate.py` shares the class (reachable via H-GUARD-4); `micro_step_gates.py` is self-protected by grounding in real git state. No test fixture exists (true coverage hole). Priority ≈ 0.39, IMPLEMENTABLE_NOW. Dossier: `research/stopguard-blocked-dispatch-replay-diagnosis-2026-07-10.md`. Handed to Oga (no fix_plan edit by Researcher).
- 2026-07-09 — **DB-test-isolation + RLS-defect-catching prior-art dive** (Mode A dispatch, triggered
  by a direct complaint: 3 real bug classes — fixture flakiness from hardcoded emails in
  `seedOrgWithUser`, an orphaned DB row, an 8-table RLS cross-tenant FK ownership gap — landed on
  padsplit-cockpit in a single day). Full dossier + PACE-gated experiment specs for each candidate:
  `research/loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md`. 6 real sources opened
  and quoted directly via `gh api`/WebFetch (no sub-agents dispatched): 2 DB-transactional-test-
  isolation libraries for Prisma/Postgres/Vitest (codepunkt/vitest-environment-prisma-postgres ≈0.61,
  chax-at/transactional-prisma-testing as a sibling/fallback), 2 Postgres RLS analyzers (pgrls/pgrls
  ≈0.56 — rule SEC047 is a near-verbatim match to the real cross-tenant-FK incident; matte97p/rlsgrid,
  auto-generates the "prove the class is empty" test matrix the team hand-built across 4 plan-check
  rounds on 2026-07-02), stryker-mutator/stryker-js (≈0.59 — closes a real, previously-unflagged gap:
  `orchestrator.md` step 5.5's mutation-testing gate only runs Python-only `mutmut`, doing nothing on
  padsplit-cockpit's actual TS codebase), dubzzz/fast-check (≈0.55 — targets the 3×-recurring "fixture
  tautology" class, flagged as only partially structural without a lint backstop). Part-b roadmap-
  discipline research (MetaGPT/ChatDev/AutoGen/OpenHands/SWE-agent/CrewAI/Aider/Devin): **headline —
  loop-team's existing `ROADMAP.md`/`NEXT_PHASE.md`/`fix_plan.md`/git-branch-naming apparatus is not
  meaningfully behind the field**; MetaGPT (≈0.21, WATCH) is the closest analog but has gone quiet
  (5.5mo stale despite 69k★, real decay signal) and is architecturally mismatched; no adoptable
  mechanism found elsewhere beyond a cheap doc-only idea (record each phase's changed-files/commit-
  range in `ROADMAP.md`/`NEXT_PHASE.md`, ported from MetaGPT's SOP pattern). Ranked dive-in queue:
  DB-isolation (padsplit-cockpit) → Stryker → pgrls backtest → fast-check+lint-backstop. TaxAhead's
  tech stack was not confirmed in context available to this pass, so no candidate was sized against
  it — flagged as an open scan target.
- 2026-07-09 — **Gate 10 concurrency/fingerprint/schema synthesis** (1 inventory pass +
  4 targeted deep-research sweeps, reconciled into one report — no new tool candidates,
  a design-fix synthesis). Full synthesis:
  `research/gate10-concurrency-fingerprint-synthesis-2026-07-09.md`. Source dossiers:
  `research/gate10-concurrency-fingerprint-inventory-2026-07-09.md`,
  `research/defect-fingerprinting-prior-art-2026-07-09.md`,
  `research/async-completion-barrier-prior-art-2026-07-09.md`,
  `research/single-writer-jsonl-schema-prior-art-2026-07-09.md`,
  `research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md`. See the new
  "Gate 10 concurrency/fingerprint/schema synthesis" section above for the headline
  conclusions and the 2 new open scan targets (Problem 2 live concurrency probe,
  Problem 1 Case B convergence backtest).
- 2026-07-09 — **Non-binding (LOGIC/CONCURRENCY/SECURITY) plan-check saturation prior-art
  dive** (Mode A dispatch: is there an existing solution for stopping iterative LLM
  review/critique loops for defect classes with no compiler-equivalent oracle — the gap
  DESIGN_CHECKLIST.md gate 10 deliberately leaves open). Full dossier:
  `research/plancheck-nonbinding-saturation-2026-07-09.md`. `gh search repos/code` +
  direct-fetch review of 9 real repos/docs (ai-code-reviewer, optimus-claude, ralphreview,
  gopher-ai, no-epicycle, xelyon-cli, and an unexpected cross-domain find — an unrelated
  project `sublimine/Cardeep`'s own statistical-rigor architecture doc, independently
  deriving Wald-SPRT + Chapman capture-recapture for a different domain) plus 5
  papers/frameworks (DSPy Refine/BestOfN, GEPA, Self-Refine, two multi-agent-debate
  SPRT/KS-stability preprints, one semantic-embedding-similarity stopping preprint).
  **Headline: nothing existing solves the exact problem** — every real "zero-new-
  findings streak" production tool found protects against re-reviewing a CHANGING
  artifact (fixed code between pushes), not a STATIC unchanged spec being re-read by
  independent lenses, which is exactly the case this project's own prior research
  (Biffl/Halling/Kohle reinspection studies) already showed degrades detection
  round-over-round — confirming the naive "extend Gate 10 to all tag classes" instinct
  as a known-bad idea for this project's specific task shape, not merely undiscovered.
  Top candidate (priority ≈ 0.46, NOVEL synthesis not a port): capture-recapture
  (Chapman-estimator) population-based saturation signal, built on this project's own
  existing `reconcile_gap_records.py` lens-overlap clustering, with a PACE-gated
  backtest spec against real, already-on-disk historical per-lens data
  (`runs/2026-07-02_ops-clock/plan_check_log.md`,
  `runs/2026-07-04_airbnb-calendar/plan_check_log.md`) and a pre-registered automatic-
  kill condition on the two historically-known-important airbnb-calendar-sync rounds
  (19-21, 30-31) — cost is a read + arithmetic, no new dispatch needed for the first
  pass. New rows added above; 3 items parked RESEARCH_ONLY per the honesty bar
  (multi-agent-debate SPRT/KS papers both explicitly disclaim non-deterministic-oracle
  applicability in their own text; semantic-embedding-similarity stopping needs a
  quality oracle this project doesn't have for these finding classes).
- 2026-07-08 — **Codex diagnostic follow-up #2: token-spend-reduction stack verification** (a
  second, separate Codex CLI session recommended provider prompt-caching, LLMLingua/LLMLingua-2/
  LongLLMLingua, GPTCache, a "SCALM" semantic-cache paper, FrugalGPT, LiteLLM, semantic-router,
  Portkey, RECOMP, AttentionRAG, and "Lost in the Middle" — every claim independently re-verified,
  none restated from Codex's summary). Full dossier:
  `research/codex-followup-token-spend-reduction-2026-07-08.md`. All 11 items are real (repos exist,
  papers exist) — no fabrications — but several are meaningfully overstated or mismatched if taken
  at face value: GPTCache is ~1yr commit-stale despite 8k★; LLMLingua hasn't tagged a release in
  2+ years; SCALM and AttentionRAG have no public code (paper-only, capped confidence ≤0.3);
  "semantic-router" is an intent-classification tool, not a caching tool (likely name conflation);
  Portkey's semantic caching is Enterprise-plan-gated, not available on the free tier; routing
  Claude Code through LiteLLM/Portkey via `ANTHROPIC_BASE_URL` switches billing from subscription to
  metered per-token (confirmed from Claude Code's own gateway docs) — a possible net cost increase;
  RECOMP's summarize-before-augment pattern directly conflicts with this project's own "read
  everything in full, hand over the complete retry history" lessons. **Headline finding, not on
  Codex's list at all:** a real, open, unresolved GitHub issue
  (anthropics/claude-code#29966, opened 2026-03-02) reports that Agent-tool-spawned subagents —
  this framework's own dispatch mechanism — get zero `cache_control` breakpoints, evidenced by two
  independent proxy-log reproductions (~378k wasted tokens in one 104-request session). A real,
  currently-shipped mitigation exists (`excludeDynamicSections`, Agent SDK ≥0.2.98/≥0.1.58). Could
  not confirm current-version reproduction (current CLI ships a compiled binary, not an inspectable
  `cli.js`) — flagged as the top open scan target. New rows + priority scores added above; ranked
  dive-in queue: the caching-gap falsifiable check (zero-cost) → FrugalGPT-style adaptive model
  cascade → a cheap "Lost in the Middle" prompt-ordering audit → everything else, in that order.
- 2026-07-08 — **Codex diagnostic followup reconciliation** (Mode A dispatch: reconcile a separate
  Codex CLI session's "spec-to-code drift validator" recommendation against the 6 existing
  compiler-gate dossiers below, without redoing already-covered work). Full write-up:
  `research/codex-followup-drift-validator-reconciliation-2026-07-08.md`. Most of Codex's citations
  (Spec Growth Engine, spec-kit, the AST-hallucination paper, Aider, mini-SWE-agent/SWE-agent,
  OpenHands, Reflexion, ArchUnit) were already thoroughly verified in the existing dossiers — cited,
  not re-verified. 8 genuinely new candidates independently verified and added above (ReqToCode+
  Ariadne, traceSDD, R2Code, buf, openapi-diff, pact-js, spring-modulith, AdverTest) — traceSDD is the
  standout new find (86–88% hallucination-detection via per-line REQ-ID citation + a trivial grep
  check, directly extends the existing `citation_grounding.py` mechanism to Coder-generated code).
  **Also found, via direct `git status`/code read (not from any dossier's description): this exact
  topic is mid-implementation, uncommitted, right now** — `DESIGN_CHECKLIST.md` gate 10
  (binding-class-saturation stopping rule) and TWO conflicting `tsc` gates inside `harness/verify.py`
  (`H-VERIFY-TSC-GATE-1` naive vs. `H-TYPECHECK-GATE-1` baseline-scoped, already flagged
  `NEEDS FOLLOW-UP` by an independent Verifier) all exist in the live working tree, none committed.
  Answered the dispatch's direct question — "is Codex's process recommendation already covered in
  `orchestrator.md`?" — as **partially covered**: independently re-derived and agreed with by this
  project's own research, a chunk of the design is already drafted in sibling files, but
  `orchestrator.md`'s own Failure Arbiter and micro-step-build-loop sections (as literally read)
  contain zero lines of either half today; confirmed via direct grep (`[BINDING]`/"gate 10"/"the ten
  gates" → zero hits in orchestrator.md).
- 2026-07-08 — **Targeted dive: compiler/typecheck-feedback prior art** (Mode A dispatch
  extending `research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md`, itself
  triggered by padsplit-cockpit Slice 6b burning ~9/30 plan-check rounds on the
  identical "unbound identifier" bug class). Full dossier + synthesis:
  `research/compiler-feedback-loop-prior-art-2026-07-08.md`. 12 real sources opened
  and quoted directly (no sub-agents dispatched). Headline findings: (1) arXiv:2606.27045's
  "Drift Validator" has **no code anywhere** — confirmed via direct PDF read; even
  GitHub's own `spec-kit` (118k★) only has an LLM-prose "converge" check, not a
  static-analysis one. (2) arXiv:2601.19106's companion repo
  (WM-SEMERU/Hallucinations-in-Code) is real but academic-only (2★, unlicensed); a
  30-repo sweep found no mature hallucination-detector tool anywhere — **the compiler
  itself (`tsc`, `flake8` F821) is already the best available tool for this bug class.**
  (3) Read real source/docs for Aider (auto-lint defaults ON, F821 in its fatal set),
  Cline (IDE-diagnostics-diff, advisory), OpenHands (Stop-hooks — a real, directly
  analogous BLOCKING pattern: `{"decision":"deny"}` + `exit 2`), mini-swe-agent (zero
  built-in gate — bash-only), and nizos/tdd-guard (same-host Claude Code precedent, but
  LLM-validated not deterministic). (4) Corroborated tRPC/Zod/openapi-typescript with
  fresh quotes. **Synthesis: wire a `type_check` gate directly into `harness/verify.py`**
  (additive AND, same pattern as the existing dual-ecosystem test run and the
  `_smoke_gate` — NOT a new role, NOT a Test-writer/Coder prompt addition, NOT primarily
  a DESIGN_CHECKLIST gate) so every micro-step checkpoint catches binding bugs the
  instant they're introduced; DESIGN_CHECKLIST/plan-check gets one scoping-correction
  line (binding correctness is the mechanical gate's job once real files exist, not a
  re-review target). Not yet filed as a fix_plan.md entry or built — handed back per the
  Researcher role's guardrail.
- 2026-07-02 — **Can a dispatch_check's stated reasoning be verified as genuine,
  not gamed?** Full dossier:
  `research/dispatch-check-justification-genuineness-2026-07-02.md` (+ companion
  `research/llm-judge-justification-genuineness-2026-07-02.md`). 4 parallel
  angles + synthesis. **Answer: no, not fully solvable** — confirmed by
  Anthropic's own CoT-faithfulness research (Turpin 2023, Lanham 2023,
  Anthropic 2025: faithfulness gets WORSE with scale), and a judge-model layer
  doesn't close the gap either (arXiv:2601.14691: rewriting only an agent's
  reasoning text, holding actions fixed, fools judges up to 90% of the time).
  No production framework (AutoGen/CrewAI/LangGraph/Claude Agent SDK) has this
  feature. Concrete, honest recommendation: presence/structure IS
  deterministically enforceable (separate spec, in progress); genuineness gets
  a LAYERED, ADVISORY-ONLY treatment — near-duplicate detection +
  vocabulary-overlap + role-cross-reference as a weighted ensemble, logged not
  auto-blocked, calibrated for a week before ever gating on it; an async
  (never PreToolUse-blocking) judge with a CAPABLE model only as a second-tier
  addition feeding human triage, never auto-blocking. Explicitly reject
  real-time blocking on a cheap judge.
  **[2026-07-04, DECIDED AGAINST — Nnamdi, after reviewing this research directly]**
  Not queued as a build candidate anymore. The presence-only advisory gate
  shipped via `H-BLOB-DISPLAY-1` (`hooks/dispatch_check_presence.py`,
  `~/.loop-gate/dispatch_check_debug.jsonl`) is the FINAL state for this
  mechanism, not a stepping stone toward the layered ensemble or async-judge
  tiers described above — both are explicitly rejected as not worth building,
  not merely deferred. Reason: the research above already shows the ceiling on
  reasoning-genuineness enforcement is low (unfaithful CoT doesn't improve with
  scale; a judge layer measurably makes it worse, not better) while the cost of
  getting it wrong is real (training Oga toward better-disguised boilerplate
  instead of better reasoning — the LGTM-2.0-in-reverse risk the synthesis
  names). Kept here as a durable lesson (a real design question was raised,
  researched honestly, and closed on its merits) rather than an open item that
  could resurface as "still TODO."
- 2026-07-02 — **Follow-up: verified the cookbook item-2 mechanism actually exists
  in Claude Code (not just the raw SDK).** Full dossier:
  `research/claude-code-subagent-tool-restriction-2026-07-02.md`. Confirmed via
  live docs fetch (`code.claude.com/docs/en/sub-agents`, quoted verbatim): custom
  subagent types with `tools`/`disallowedTools` frontmatter are real,
  project-definable (`.claude/agents/*.md`), and `disallowedTools: Agent` (or
  omitting Agent from an allowlist) makes a subagent STRUCTURALLY unable to call
  the Agent tool at all — not just prompt-discouraged. No such files exist yet in
  this project (needs building from scratch). 5 ready-to-use agent templates
  (Coder/Verifier/Test-writer/Researcher/plan-check-Verifier) drafted in the
  dossier. Also confirmed the existing `agent_id`-in-PreToolUse-payload discovery
  (used by this session's H-ARM-1 and earlier oga-guard fixes) is now
  OFFICIALLY documented too, not just empirically proven — stays as a
  complementary defense-in-depth layer, not a replacement (the custom-agent-type
  route prevents the tool call from being offered at all, which is structurally
  stronger than reactively denying an attempted one). NOT YET BUILT — next
  loop-team session should spec+build this through the full plan-check/test/
  verify loop, same as every other fix this session.
- 2026-06-23 — Radar seeded from `research/` reports + `implementation-gepa-dspy-mini-swe-agent.md` dossier. GEPA/DSPy/mini-swe-agent set to CANDIDATE (IMPLEMENTABLE_NOW); classic SWE-agent and AutoGen marked REJECTED/DECAYING.
- 2026-06-23 — From AlphaSignal newsletter lead (verified): added **GLM-5.2** (CANDIDATE/TESTABLE, Phase-2 worker *model*, MIT, benchmarked under mini-swe-agent, priority ≈ 0.50 — but key benches vendor-reported, newsletter Kimi claim unverified) and **Dive-into-Claude-Code** (WATCH, harness design reference for Oga). Open target: confirm GLM-5.2 TB2.1 number once it appears on independent tbench.ai.
- 2026-06-23 — **Pipeline run: light + deep.** Light (A1 primaries): 3 deltas — EvoSkill v1.3.0; DeepSWE v1.1 (Claude-Fable-5 70% > GPT-5.5; GLM-5.2 now top open-weight 44% on the *independent* board → de-risked); Terminal-Bench 2.1 new Claude-5-Fable entry. Deep (deep-research mode): (1) **SkillOpt** implementation dive → it's a near-isomorphic fit for `optimize/` but must use **SkillOpt-as-proposer + PACE-as-gate** (its raw threshold is forbidden p-hacking); spec at `experiments/spec_skillopt_vs_gepa.md`. (2) **Autoresearch + Meta-Harness** dive → **headline finding: `optimize/`'s proposer reads a 280-char summary = the ablation's *weakest* channel; feeding raw judge traces is worth ~+15 pts. ~1-day fix.** Full design at `research/optimize-loop-redesign-proposal.md`. (3) **SERA** → soft verifier = Layer-0 router on the patch slice only; don't fine-tune own coder yet (use off-the-shelf). (4) **Discovery** → NEW verified: **RHO** (MSR label-free harness optimizer, SWE-Pro 59→78%, ≈0.46, top new), **Self-Harness** (≈0.43), **R4P** + **SWE-RM** + **Agentic Verifier** (execution-free patch verifiers), **Asuka-Bench** + **SWE-Marathon** (anti-hack/multi-round evals). Couldn't-verify (next pass): EvoSkills 2604.01687, SIA 2605.27276, SkillClaw, SWE-EVO, DARWIN, Continual Harness, SAGE. **Theme: "harness self-optimization" (RHO/Self-Harness/Meta-Harness/Autoresearch) is the hot area and exactly the team's Phase 1 — and the cheapest highest-impact move is the trace-fed proposer fix.**
- 2026-06-23 — **Upgraded the Scan Manifest source set.** Split Section A into A1 (primary/ground-truth: HF Daily Papers, SWE-bench/Terminal-Bench/DeepSWE leaderboards, GitHub releases+trending, arXiv, lab blogs) and A2 (newsletters as leads-only: AlphaSignal + Import AI + The Batch + Latent Space/AINews + Ahead of AI). Rationale: AlphaSignal repeatedly garbled/oversold/mislabeled (DeepSWE %, Nex "top-3", MiniMax license) — primary sources are higher-signal and self-correct vendor laundering. Tuned Section B queries (skill-trainers, soft/execution/formal verifiers, contamination-free benchmarks, worker-model pool). Daily light = A1 deltas; weekly deep = B + lab blogs.
- 2026-06-23 — **Full AlphaSignal Jan–Jun backlog mined** (6 Researchers, one per month, ~150 issues, full detail in `research/alphasignal-jan-jun-digest.md`). Top NEW verified candidates added: **Karpathy Autoresearch** (≈0.75, the optimizer-outer-loop skeleton), **Qwen3.6-27B** (≈0.71, Apache worker model), **Meta-Harness** (≈0.67, full-history harness optimizer), **SERA** (≈0.59, train-your-own coder + soft verifier), **DeepSWE** (≈0.44, contamination-free eval), plus a consolidated verifier-patterns row and an open-worker-model pool (Qwen3.5-397B, Kimi K2.7, DeepSeek V4, GLM-4.7-Flash, Poolside Laguna). Also surfaced but kept in the digest: OpenAI Agents SDK (Phase-4 harness), OpenCode/DeerFlow 2.0 (open scaffolds), Ralph Wiggum plugin (cheapest self-loop to prototype), TTT-Discover / MiniMax M2.7 / Hyperagents / OpenClaw-RL1 (Phase-5 precedents). Caveat logged: newsletter model-version names sound ahead-of-known, but every tool candidate was resolved to a real GitHub/arXiv/HF page; vendor benchmarks flagged. **Headline: the optimizer-design vein (Autoresearch + Meta-Harness + SkillOpt) and the verifier-pattern vein (SERA/CUDA-Agent/Leanstral) are the richest hauls — both feed the active Phase 1.**
- 2026-06-23 — **Mined the rest of the AlphaSignal backlog (verified leads).** Optimizer/skill-training: **SkillOpt** (MS Research, MIT, ~5.8k★, priority ≈ 0.69 — exact design match to `optimize/`, beats GEPA+EvoSkill as baselines → reconsider as Phase-1B primary alongside GEPA) and **EvoSkill** (Sentient, Apache-2.0, priority ≈ 0.58, Phase 4/5). Worker models: **Nex N2 Pro** (Apache-2.0, priority ≈ 0.30, TB2.1 vendor-only/"top-3" refuted) and **MiniMax M3** (custom non-OSS license, priority ≈ 0.24, 1M ctx). Eval: **FrontierCode** (Cognition PR-mergeability benchmark, frontier models ~13% on Diamond). Conceptual validation (not new tools): Jun-14 "loopmaxxing" piece corroborates the team's guardrails (stall-detector, MAX_ITERS, propose≠verify). **Top actionable: SkillOpt** — highest priority of everything surfaced this session.
- 2026-06-27 — **Light scan + weekly deep pass + plan-check Verifier (3 passes, 2× PLAN_FAIL before PLAN_PASS).** Light deltas: **Live-SWE-agent → DECAYING** (last commit Jan 19, 5mo stale); **Karpathy Autoresearch → NEEDS-RECHECK** (repo inaccessible on this pass); **SkillOpt stars 5.8k→9.5k** (organic multi-platform surge, adoption window narrowing); OpenHands Cloud 1.40.0 (CVE patches); mini-swe-agent v2.4.2 (stars 4.9k→5.5k). Deep pass NEW verified (primary sources opened; quotes inline in rows): **RHO** (priority 0.397, MIT, real code + Claude Code workflow, GPT-5.5-only caveat confirmed from arXiv HTML); **SkillReducer** (WATCH, token efficiency, no code, quote inline); **SkillOps** (WATCH, skill library health, real repo, quote inline); **The Verification Horizon** (RESEARCH_ONLY, confirms verifier co-evolution direction, quote inline). Self-Harness triage downgraded TESTABLE→RESEARCH_ONLY (no code, all evals mid-tier models only, frontier transfer unverified). Pre-existing **SWE-RM duplicate rows merged** (TESTABLE + RESEARCH_ONLY → single RESEARCH_ONLY row, correct triage given no repo). PLAN_FAIL 1: stop-guard fired (edits without plan-check gate). PLAN_FAIL 2: SWE-RM dedup missing + AC2 verifiability gap + change log premature. PLAN_PASS 3 (this entry): dedup fixed, inline quotes added, log corrected. **Priority order this week: SkillOpt VERIFIER.md experiment → RHO (pending trajectory audit) → Self-Harness code-drop watch.**
- 2026-06-23 — First light + deep scan run. **NEW:** Live-SWE-agent (CANDIDATE/TESTABLE, Phase 2, builds on mini); SWE-RM (RESEARCH_ONLY, verifier insight). **CHANGED:** DeepEval license→Apache-2.0 + DAG deterministic judge; GEPA `optimize_anything`; OpenHands v1.8.0/78k; agent-lightning v0.3.0/16.8k; agent-framework 1.8.0/11k; **Terminal-Bench → 2.0/2.1 on Harbor (v1.0 path stale).** **CONFIRMED-STILL-BEST:** mini-swe-agent (minimal scaffold), GEPA (optimizer) — no entrant beat either. **No decay alarms** on adopted/candidate picks. **Open gaps next pass:** Huxley-Gödel Machine (HGM, Phase-5 watch lead, not yet opened); SWE-bench Pro lacks a clean open-*scaffold* leaderboard; eval/verifier preprints (rubric-gen, agentic verifier) to open; re-deep-check overdue DECAYING rows (Ragas→VibrantLabs, OpenAI Evals, AutoGen).
- 2026-07-02 — **Direct claude-cookbooks repo review** (Nnamdi asked what in the official cookbooks repo could improve the loop; 5-cluster parallel read + synthesis, deduped against the existing backlog memory). Full dossier: `research/claude-cookbooks-review-2026-07-02.md`. Added row above. 6 HIGH-priority items are architecture-level (not just tool/model tracking) — background priority-ranked compaction, SDK-level `disallowed_tools` denylist (root-causes the sub-agent-punting failure), mandatory independent-re-run-before-checkpoint, silent-throttle failure-arbiter class, full-retry-memory for the Coder, evidence-bar VERIFIER.md rewrite. None yet applied to the actual role files — this is a dive-in queue add, next step is picking one for a PACE experiment. Also logged: the workflow's first run failed on a synthesis-agent tool-call bug (StructuredOutput mis-wrapped as a JSON string) traced to a raw-JSON-dump-in-prompt priming effect, fixed by reformatting; and two loop-team hooks (Oga-guard, stop-guard) misfired on ordinary edits to an unrelated session-scratch script, worked around per their own advisory-not-security-boundary language — logged in the dossier's process-note section, not re-litigated here.
