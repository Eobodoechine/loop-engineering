# The Loop — Integration Plan & Cost Breakdown (v1)

*Assemble, don't invent. Wire proven open-source pieces into a thin orchestration layer that runs in your Cowork environment. Below: the pick for each layer, the honest cost picture (the short version: **software = free, LLM tokens = the real cost**), a first build target, and a phased path.*

---

## Will it be free? The honest answer

**The frameworks are 100% free and open-source** (licenses verified): DSPy (Apache-2.0), GEPA (MIT), OpenHands (MIT), SWE-agent / mini-swe-agent (MIT), DeepEval (Apache-2.0), Inspect (MIT), Langfuse (MIT). You can clone and run all of them at no licensing cost, forever.

**What actually costs money is LLM inference — the tokens.** Every agent step and every optimization trial calls a model. There are three ways to pay for that, and you can mix them:

| Path | Marginal cost | Trade-off |
|---|---|---|
| **Your existing Claude / Cowork access** | Already paid for | Great for the **orchestration** (Oga) and light loops; heavy autonomous/optimization runs may hit usage limits |
| **Local / open models** (Qwen, DeepSeek, Llama via Ollama or vLLM) | **$0 per token** | Needs a capable GPU (own or rented); quality below frontier but rising fast |
| **Pay-as-you-go API** (Anthropic / OpenAI / Google) | Per token | Best quality; cost scales with usage — this is where a bill can surprise you |

**The two token-hungry parts to watch:**
1. **The coding worker** — agentic loops use long context and many iterations per task.
2. **Optimization** — DSPy/GEPA run *many* trial evaluations to tune a prompt; a single optimization run can be the most expensive thing you do.

**Bottom line:** you can stand the whole thing up and prototype for **$0** (open-source + local models, or your existing Claude access for light use). Real money appears only when you run frontier-model APIs at volume — and even then it's controllable. **Put a hard spending cap in from day one** (it doubles as a safety guardrail for an autonomous loop). Note we are deliberately **not** using the paid products (Devin, Cursor, Copilot), so those subscription costs don't apply.

---

## The pick for each layer

| Layer | What it does | Recommended pick | Why | Cost |
|---|---|---|---|---|
| **Orchestration (Oga)** | Runs the loop, dispatches roles, schedules, logs | **Cowork skill + subagents** (what you already run); graduate to **LangGraph** if it needs durable state/branching | Native to your world, schedulable, zero new infra | Uses existing Claude access |
| **Worker (builds code)** | Reads repo, writes code, runs tests, iterates | **mini-swe-agent** to start → **OpenHands** when you need the control center | mini is ~100 lines, hackable, ~65–74% SWE-bench; OpenHands adds the multi-agent server + automation | Free software; tokens per run |
| **Verifier** | The objective signal | **pytest / execution** for code; **DeepEval** (or **Inspect**) for judgment & non-code | Test execution is the non-gameable oracle; DeepEval adds agentic + LLM-judge metrics | Free software; judge calls cost tokens |
| **Optimizer (experiment harness)** | Tune prompts/methods, keep the winner | **DSPy + GEPA**; **EvoAgentX** if you want a multi-optimizer bake-off | The standard; GEPA is sample-efficient (fewer trials = less token spend) | Free software; trials cost tokens |
| **Memory / persistence** | Run history, what worked | **SQLite / JSON** to start; **Letta** if you want managed agent memory | Clean attribution substrate; no infra to start | Free |
| **Team self-improvement** *(later, sandboxed)* | Oga improves the team | Borrow **ADAS / GPTSwarm** patterns | Reference designs exist; treat carefully | Free software; tokens |

The only thing you actually *write* is the thin Oga glue that calls these and runs on your Cowork schedule with your connectors.

---

## First build target (small, real, exercises the whole loop)

**"Spec → tested module, on a real task in one of your repos."** This reuses the `loop-team/` scaffold but swaps my hand-rolled pieces for the real tools:

1. **Oga** (your existing skill) takes a brief.
2. **mini-swe-agent** is the worker — it writes the code in the repo.
3. **pytest** is the verifier — runs the tests, returns pass/fail (replaces my `verify.py`).
4. The run is logged (SQLite/JSON).
5. Then add **DSPy+GEPA** to tune the worker's instruction over ~10–20 tasks, scored by pass rate — proving the "test methods, keep the best" loop end-to-end.

This is deliberately small: one repo, one well-scoped task type, a real oracle. If it works, every other ambition (multi-repo, self-improvement, the job-application agent) is the same machine pointed at a new verifier.

---

## Phased path

| Phase | Deliverable | Cost to run |
|---|---|---|
| **1. Swap the worker** | Replace hand-rolled coder with **mini-swe-agent**; keep Oga; verifier = pytest; run one real task end-to-end | Free w/ local model, or cents–dollars on cheap API |
| **2. Real verifier layer** | Execution oracle for code + **DeepEval** for judgment/false-pass detection | Free + small judge-token cost |
| **3. Optimizer** | A **DSPy** module for one role + **GEPA** to tune it over a small task set; keep the winner | Optimization run = the main token spend (use GEPA for efficiency) |
| **4. Persistence + scheduling + guardrails** | Run history store; runs on your Cowork schedule; daily cap + kill switch + provenance | Free infra; tokens per scheduled run |
| **5. (Later) Team self-improvement** | ADAS/GPTSwarm-style search over the team, sandboxed | Token-heavy; gate behind a budget |

---

## What to install (when we start Phase 1)

```bash
pip install mini-swe-agent dspy-ai gepa deepeval inspect-ai
# + one model backend:
#   local & free:  ollama (run qwen2.5-coder / deepseek-coder)
#   or API:        set ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY
```

Everything above is free to install. The only account that may cost money is the model API key — and you can skip even that by running a local model through Ollama.

---

## My recommendation

Start Phase 1 on the **free path**: mini-swe-agent + pytest, driven by either a local Ollama model or your existing Claude access, on one small real task in this repo. That proves the assemble model with **zero new spend**. We turn on a paid API (and a spending cap) only when you want frontier quality or start running optimization at volume.

If you tell me a target repo + a small first task (and whether you'd rather run local or via an API), I'll wire Phase 1 and run it end-to-end.
