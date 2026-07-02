# Source-Verified Repo & Tool Table — Loop Engineering / Self-Improving Code

**Compiled:** 2026-06-20 · **Method:** independent deep-research pass, primary sources fetched directly (GitHub repo pages, arXiv, official docs). Star counts and release dates are as rendered on the live pages at fetch time. Pick (✓ keep / + add / ⚠ correct / ? re-verify) is relative to the prior session's baseline.

> Caveat that applies to every row: live web *search* was unavailable during the run, so findings rest on direct primary-source fetches (the strongest source for maturity/maintenance, but it means open-ended discovery of brand-new June-2026 preprints was limited). Leaderboards move monthly — re-verify fast-movers at phase start.
>
> **Live verification (2026-06-20):** A follow-up live-fetch pass first-hand confirmed: AutoGen "Maintenance Mode" header verbatim (→ Microsoft Agent Framework); DSPy 3.2.1 / 34.9k stars; SWE-bench Verified leaderboard newest data ~Feb 2026 with mini-swe-agent "bash-only" + Opus 4.5 among the top; and **EvoAgentX confirmed active** (`EvoAgentX/EvoAgentX`, ~3k stars, 1,105 commits — see row in §4). WebSearch itself was down, so latest-preprint discovery is still pending.

## 1 — Coding worker agents (build→test→fix loops)

| Project | What it is | OSS / License | Stars | Maintenance (latest) | Loop-worker fit | Pick | Primary URL |
|---|---|---|---|---|---|---|---|
| **mini-SWE-agent** | ~100-line bash-only ReAct agent; SWE-bench team's reference scaffold | Yes / MIT | 4.9k | Very active — v2.3.0 (May 2026); ~76.8% Verified w/ Opus 4.5 | **Top pick** — linear history, each action a swappable subprocess, model-agnostic via litellm | ✓ keep | github.com/SWE-agent/mini-swe-agent |
| **OpenHands** (ex-OpenDevin) | Self-hosted control center to run agents across local/remote/cloud | Core OSS / MIT | 77.8k | Very active — v1.8.0 (Jun 10 2026); split into software-agent-sdk + agent-canvas | Heavy but built for orchestrating many agents over REST | ✓ keep | github.com/OpenHands/OpenHands |
| **Claude Agent SDK (Python)** | Python SDK wrapping Claude Code loop; tools, hooks, subagents | Yes / MIT (bundles closed CLI) | 7.3k | Very active — v0.2.101 (Jun 13 2026) | Best when you want programmatic control + permission gates | ✓ keep | github.com/anthropics/claude-agent-sdk-python |
| **OpenAI Codex CLI** | Lightweight local coding agent (Rust); `exec`/JSON, sandboxed | Yes / Apache-2.0 | 82.5k | Extremely active — 0.130.0 (May 2026), 784 releases | Strong hardened single-binary worker | **+ add** | github.com/openai/codex |
| **SWE-agent** (classic) | GitHub-issue→patch agent; NeurIPS 2024 | Yes / MIT | 19.6k | **Maintenance** — v1.1.0 (May 2025); superseded by mini | Use mini instead | ⚠ note: superseded | github.com/SWE-agent/SWE-agent |
| **Aider** | Terminal AI pair-programmer; repo-map + git | Yes / Apache-2.0 | 46.5k | Slowing — v0.86.0 (Aug 2025), no newer release | Usable, but cadence stalled | ? watch | github.com/Aider-AI/aider |
| **Agentless** (UIUC) | 3-phase localize→repair→validate, no agent | Yes / MIT | 2.1k | Stale — v1.5.0 (Oct 2024) | Deterministic reference only | research ref | github.com/OpenAutoCoder/Agentless |
| **AutoCodeRover** | Autonomous program improvement | Yes | 3.1k | Stale — v1.1.0 (Sep 2024) | Reference only | research ref | github.com/AutoCodeRoverSG/auto-code-rover |
| **Moatless Tools** | Experimental LLM-edits-code toolset | Yes / MIT | 641 | Light — 0.0.2 (Jun 2025) | Hobby reference | research ref | github.com/aorwall/moatless-tools |

**SWE-bench Verified context:** now ~80% and largely **saturated**; vendors have shifted headline reporting to **SWE-bench Pro / Terminal-Bench**. Top live full-agent entries (~79%): live-SWE-agent and Sonar Foundation Agent, both + Claude Opus 4.5. This validates the prior advice to re-check the best worker *just before* Phase 2.

## 2 — Eval / regression-test frameworks

| Project | What it is | OSS / License | Stars | Maintenance (latest) | Regression-suite fit | Pick | Primary URL |
|---|---|---|---|---|---|---|---|
| **DeepEval** (Confident AI) | Pytest-style LLM/agent testing; agentic metrics | Yes / Apache-2.0 | 15.4k | Very active — **v4.0 "Eval Harness for Coding Agents" (May 13 2026)** | Strong — pytest, frozen "goldens", CI gating | ✓ keep (strengthened) | github.com/confident-ai/deepeval |
| **Inspect** (UK AISI) | Gov-backed eval framework; solvers, sandboxing, model-graded scorers | Yes / MIT | 2k | Extremely active — 211 release tags | Strong — scorers are first-class loggable objects | ✓ keep | github.com/UKGovernmentBEIS/inspect_ai |
| **Promptfoo** | CLI/lib to eval + red-team prompts/agents; declarative YAML | Yes / MIT | 21.3k | Very active — 0.121.x (May 2026). **Now part of OpenAI** | Strongest out-of-box frozen suite + CI | **+ add** | github.com/promptfoo/promptfoo |
| **LangSmith** | Commercial eval+observability; explicit offline regression tests | Commercial (free tier) | n/a | Active | Strong — docs literally describe regression gating + dataset versioning | + add | docs.langchain.com/langsmith/evaluation-concepts |
| **Braintrust** | Commercial eval; experiments as permanent records | Commercial (free tier) | n/a | Active | Strong — "catch regressions before deploy" | + add | braintrust.dev/docs/evaluation-quickstart |
| **W&B Weave** | Tracing + `weave.Evaluation` over datasets/scorers | Yes / Apache-2.0 | 1.1k (SDK) | Very active — v0.52.x (Jun 2026) | Good — reproducible version-over-version compare | + option | github.com/wandb/weave |
| **TruLens** (Snowflake) | Instrumentation + 7 agentic evaluators | Yes / MIT | 3.4k | Active — 2.8.1 (May 2026) | Good for agent trajectories specifically | + option | github.com/truera/trulens |
| **Arize Phoenix** | OTEL tracing + evals + versioned datasets | Source-available / **Elastic License 2.0** | (unverified) | Very active | Good; note non-OSI license | + option | github.com/Arize-ai/phoenix |
| **OpenAI Evals** | Benchmark framework + registry | Yes / MIT | 18.6k | **Slow** — superseded by hosted Evals | Weaker for agents now | ? legacy | github.com/openai/evals |
| **Ragas** | LLM-app eval toolkit (RAG→agents) | Yes / Apache-2.0 | 14.4k | Active, slower — rebranded org `vibrantlabsai` | Partial — metric-centric | + option | github.com/vibrantlabsai/ragas |
| **τ²/τ³-bench** (Sierra) | Tool-agent-user benchmark; **Pass^k** reliability + auto-error-ID | Yes / MIT | ~1.3k | Active (tau2/tau3) | Frozen agent-behavior benchmark pattern | **+ add (pattern)** | github.com/sierra-research/tau2-bench |

**Cross-cutting finding (the "verifier-for-the-verifier"):** **no** framework ships a turnkey meta-eval that scores the judge itself on caught/missed/false-pass. You assemble it: a frozen gold set + run the judge + compute TP/FP/FN. Best substrates: **Promptfoo, DeepEval** (code-first, CI-native), then LangSmith/Braintrust (managed, versioned experiments). This directly confirms the prior Phase-1 plan is a *build*, not a *buy*.

## 3 — Prompt / program optimizers

| Project | Optimizes | OSS / License | Stars | Maintenance (latest) | Custom metric? | Pick | Primary URL |
|---|---|---|---|---|---|---|---|
| **DSPy** (Stanford) | Prompts, demos, weights across pipelines | Yes / MIT | 35.1k | Very active — 3.2.1 (May 2026); bundles GEPA, MIPROv2, SIMBA… | Yes (core design) | ✓ keep | github.com/stanfordnlp/dspy |
| **GEPA** | Any text artifact via reflection + Pareto evolution | Yes / MIT | 4.4k | Active — v0.1.1 (Mar 2026); now the de-facto backend in MLflow, Opik, Google ADK, Pydantic AI, OpenAI Cookbook | **Yes + consumes rich feedback** (error text/traces, not just a scalar) | ✓ keep (strengthened) | github.com/gepa-ai/gepa · arxiv 2507.19457 |
| **MIPROv2** | Instructions + few-shot demos | Yes (in DSPy) | — | Active | Yes | ✓ keep | dspy.ai/api/optimizers/MIPROv2 · arxiv 2406.11695 |
| **TextGrad** (Stanford) | Any text var via "textual gradients" | Yes / MIT | 3.6k | **Slowing** — v0.1.6 (Dec 2024), but **Nature-published Mar 2025** | Yes | + option | github.com/zou-group/textgrad · nature s41586-025-08661-4 |
| **Agent Lightning** (MS) | Weights (RL/SFT) **and** prompts for ANY agent | Yes / MIT | 17.1k | Very active — v0.3.0 (Dec 2025) | Yes (reward/eval fns) | **+ add** | github.com/microsoft/agent-lightning · arxiv 2508.03680 |
| **AdalFlow** (UT Austin) | Zero-shot instructions + demos, whole pipelines | Yes / MIT | 4.1k | Active — v1.1.3 (Sep 2025) | Yes | + option | github.com/SylphAI-Inc/AdalFlow · arxiv 2501.16673 |
| **OPRO** (DeepMind) | Prompt instructions | Yes / Apache-2.0 | 754 | **Static** — 12 commits, reference only | Adapt scorer | research ref | github.com/google-deepmind/opro · arxiv 2309.03409 |
| **EvoPrompt** (MS) | Discrete prompt text (GA/DE) | Yes / MIT | 241 | **Static** research code | Override metric | research ref | github.com/beeevita/EvoPrompt |
| **PromptBreeder** (DeepMind) | Task + mutation prompts | **No official code** | — | Paper only (2023) | N/A | research ref | arxiv 2309.16797 |

**Why GEPA matters for the loop:** it accepts **diagnostic text** from the evaluator ("Actionable Side Information"), not just a number — so a regression suite that emits *why* a case failed feeds GEPA better than scalar-only optimizers. Paper claims 35× fewer rollouts than RL (peer-reviewed); production/cost claims are vendor-reported (flagged).

## 4 — Self-improving / self-modifying agent architectures

| Project / paper | What self-improves | OSS? | Maturity | Pick | Primary URL |
|---|---|---|---|---|---|
| **Darwin-Gödel Machine (DGM)** — Sakana/Clune | Agent's own code (tools, prompts, edit logic); frozen FM | Yes / Apache-2.0 (~2.1k) | Research prototype; SWE-bench 20→50% | ✓ keep (the cautionary tale) | github.com/jennyzzt/dgm · arxiv 2505.22954 |
| **ADAS / Meta Agent Search** — Hu, Lu, Clune | Agent architectures written in code | Yes | Research prototype | ✓ keep | github.com/ShengranHu/ADAS · arxiv 2408.08435 |
| **GPTSwarm** — Schmidhuber lab | Node prompts + edge (inter-agent) topology | Yes | Research lib, ICML 2024 | ✓ keep | github.com/metauto-ai/gptswarm · arxiv 2402.16823 |
| **SICA — Self-Improving Coding Agent** — Bristol | Its own orchestration code/tools | Yes (CC-BY) | Prototype; **17→53% SWE-bench Verified subset** | **+ add** (direct precedent) | arxiv 2504.15228 |
| **Gödel Agent** — PKU/UCSB | Its own runtime logic via prompting | Yes | Prototype, ACL 2025 | **+ add** | github.com/Arvid-pku/Godel_Agent · arxiv 2410.04444 |
| **AgentSquare** — Tsinghua | Recombines 4 standard modules (Plan/Reason/Tool/Memory) | Yes | Prototype; +17.2% over best human agents | **+ add** | github.com/tsinghua-fib-lab/AgentSquare · arxiv 2410.06153 |
| **EvoAgentX** | Auto-builds + self-evolves multi-agent workflows from a goal; experiment/evolution harness | Yes | ~3k stars, 1,105 commits — active (live-verified 2026-06-20) | **+ add (Phase 4)** | github.com/EvoAgentX/EvoAgentX · survey arxiv 2508.07407 |
| **AlphaEvolve** — DeepMind | Evolves *external* algorithms (not its own code) | **No** (closed; OpenEvolve is 3rd-party) | Production at Google | + reference | deepmind.google/blog/alphaevolve… |
| **Self-Rewarding LMs** — Meta/NYU | Model weights + its own reward model | Method public | ICML 2024 | + reference | arxiv 2401.10020 |

## 5 — Multi-agent orchestration frameworks (maintenance status)

| Framework | Status | OSS | Stars | Latest release | Primary URL |
|---|---|---|---|---|---|
| **Microsoft AutoGen** | **Maintenance mode** — README says so verbatim; → MAF | MIT | 58k | python-v0.7.5 (Sep 2025) | github.com/microsoft/autogen |
| **Microsoft Agent Framework (MAF)** | **Active** — AutoGen + Semantic Kernel successor | MIT | 10.4k | dotnet-1.5.0 (May 2026) | github.com/microsoft/agent-framework |
| **LangGraph** | Active — hit 1.0 | MIT | 34.3k | 1.2.4 (Jun 2026) | github.com/langchain-ai/langgraph |
| **CrewAI** | Active (high velocity) | MIT | 53k | 1.14.6 (May 2026) | github.com/crewAIInc/crewAI |
| **OpenAI Agents SDK** | Active | MIT | 26.3k | v0.17.2 (May 2026) | github.com/openai/openai-agents-python |
| **OpenAI Swarm** | **Deprecated** → Agents SDK | MIT | 21.5k | none | github.com/openai/swarm |
| **Google ADK** | Active | Apache-2.0 | 19.6k | v1.33.0 (May 2026) | github.com/google/adk-python |
| **A2A protocol** | Active — now under **Linux Foundation** | Apache-2.0 | 24.4k | v1.0.1 (May 2026) | github.com/a2aproject/A2A |
| **LlamaIndex Workflows** | Active | MIT | 49.6k | v0.14.22 (May 2026) | github.com/run-llama/llama_index |
| **Claude Agent SDK** | Active | MIT | 7.3k | v0.2.101 (Jun 2026) | github.com/anthropics/claude-agent-sdk-python |
| **Magentic-One** | **Maintenance** (inside AutoGen) | MIT | (in AutoGen) | — | github.com/microsoft/autogen |

**Confirms prior baseline note** "AutoGen in maintenance mode → Microsoft Agent Framework" — verbatim from Microsoft's own repo. Adds: Swarm deprecated, Magentic-One frozen, A2A now vendor-neutral.

## 6 — Agents at scale / multi-repo orchestration

| Option | Scheduled? | Parallel model | Multi-repo in one run? | OSS | Primary URL |
|---|---|---|---|---|---|
| **OpenHands Automations + Sub-Agent Delegation** | Yes (cron/webhook) | Parallel sub-agents (threads, `max_children`) | No (per-sandbox) | Core OSS | docs.openhands.dev/openhands/usage/automations |
| **Devin Managed + Scheduled Devins** | Yes | Coordinator spawns child Devins (map-reduce) | Via fan-out | No | cognition.ai/blog/devin-can-now-manage-devins |
| **GitHub Copilot Mission Control / Agent HQ** | Yes (Automations) | Many concurrent single-repo sessions | No (single-repo, 59-min cap) | No | github.blog/changelog/2025-10-28… |
| **Cursor Cloud Agents** | Yes (Automations) | Unbounded parallel; REST API + SDK | **Yes — up to 20 repos/agent** (rare exception) | No | cursor.com/docs/cloud-agent/api/overview |
| **Claude Agent SDK `Workflow`** | Via CI/cron | Orchestrates dozens–hundreds of agents in a script | DIY | SDK OSS | code.claude.com/docs/en/workflows |
| **Sourcegraph Batch Changes + Amp** | Declarative | Per-repo command across many repos/hosts | **Yes (Batch Changes)**, Enterprise | No | sourcegraph.com/docs/batch-changes |

**⚠ Correction to prior baseline:** "OpenHands **Agent Canvas**" could **not** be verified as a current shipped feature by that name (the repo does contain an `agent-canvas` package post-restructure, but the user-facing multi-repo story is **Automations + Sub-Agent Delegation + Cloud**). The bigger picture: no vendor sells "self-improving team across many repos on a schedule" as one product — you compose it. Closest OSS = OpenHands Automations; closest turnkey commercial = Devin Managed/Scheduled; most flexible DIY = Claude Agent SDK `Workflow`.
