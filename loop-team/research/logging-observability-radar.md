# Logging & Observability Radar — Loop Team

**Researcher (Mode A) · compiled 2026-06-30 · all claims web-grounded (quotes inline), current as of 2025–2026.**

## Baseline we are improving on

What the repo has *today* (read from the codebase, not the web):

- **22 files emit via bare `print()`** (`grep -rl "print(" loop-team --include=*.py | wc -l` → `22`). Unstructured, unleveled, no run correlation.
- **`runner/run_trace.py`** — the one structured piece: an append-only `<run_dir>/trace.jsonl`, one JSON object per event, flush-as-you-go, a small per-model rate table for cumulative token/cost (`cum_tokens`, `cum_cost_usd`), canonical event vocabulary (`role_dispatch`, `verify`, `verdict`, `plan_check`, `adversarial_bug`, `lesson`). Unknown model → `cost=null` (never fabricates a price).
- **In-flight (TDD, tests written, impl not yet present):** a stdlib-only shared `harness/log.py` — leveled JSON-line logger, per-run `<run_dir>/log.jsonl`, stderr console, **never-raises** (`harness/test_log.py` exists; `harness/log.py` does not yet). This is the *baseline* every candidate below is scored against.

So the gap is **not** "we have no structure" — `trace.jsonl` already gives token/cost and an event vocabulary. The gap is: (a) 22 files of `print()` that should route through one leveled logger, and (b) no **waterfall/span view, cost dashboard, or eval-linked analytics** over what `trace.jsonl` records. That framing drives the scoring: a JSON-logger swap is a near-zero-cost *incremental* win; an observability platform is a higher-cost *step-change* that adds views `trace.jsonl` cannot.

Posture constraints (from the task + orchestrator): **privacy-sensitive** (self-host / local strongly preferred), **low-dep** (stdlib-only is the current bar), **PACE-gated** adoption (score only orders the queue; the experiment + acceptor + human diff-review decide adoption).

---

## 1) Landscape table

### Bucket A — Python structured-logging libraries

| Tool | Self-host | OTel-native | Structured / traces | Maint / adoption signal | License | One-line fit |
|---|---|---|---|---|---|---|
| **stdlib `logging` + `python-json-logger`** | n/a (in-process) | no (bridge) | JSON via formatter; no traces | stdlib + small dep; "safe, universal" | stdlib / BSD-ish | "zero surprises" baseline; what a hand-rolled `log.py` essentially is |
| **structlog** | n/a (in-process) | **yes** (native OTel support) | JSON/logfmt via processor chain; contextvars across async | "production at every scale since 2013", Dev-Status 5/Production-Stable, ~4.8k★, releases through 2025 (25.4.0/25.5.0) | **Apache-2.0 + MIT** (dual) | best *incremental* upgrade: processor chain = redaction/enrichment/sampling, contextvars = per-run/per-role binding |
| **loguru** | n/a (in-process) | no (bridge via stdlib) | JSON serialize; rotation/compression built in | popular; "import logger and use it" | MIT | fastest to adopt, but "requires bridging through the standard library" for OTel; ~25% slower than structlog for JSON |

### Bucket B — LLM / agent observability & tracing platforms

| Tool | Self-host | OTel-native | Structured / traces | Maint / adoption signal | License | One-line fit |
|---|---|---|---|---|---|---|
| **OTel + GenAI semconv** | n/a (a *standard*) | **is** the standard | spans + `gen_ai.usage.input_tokens/output_tokens`, `gen_ai.request.model` | semconv **v1.42.0**; GenAI SIG (formed Apr 2024) very active — conventions *moved to a dedicated repo*, agent/MCP/eval scope expanding | Apache-2.0 / CC-BY-4.0 docs | the wire format to emit; lets you swap backends without re-instrumenting |
| **Arize Phoenix** | **yes, one command** (`docker run … arizephoenix/phoenix`; runs on a laptop, no API key) | **yes** (OTLP + OpenInference) | spans/waterfall, evals, no-cloud-account local mode | OSS, "10,000+ GitHub stars", actively maintained | **Elastic License v2 (ELv2)** | best **privacy-fit step-change**: local OTel waterfall + evals, no egress |
| **Langfuse** | yes (Postgres + ClickHouse + Redis + S3; "≥4 vCPU / 8 GB / 100 GB") | yes (ingests OTel) | traces/spans, cost, eval scores, prompt mgmt | "open source leader … 28,000+ stars", MIT; **acquired by ClickHouse Jan 2026**, MIT preserved | **MIT** | most full-featured OSS; heavier self-host footprint |
| **Pydantic Logfire** | **no (SaaS only)** | yes ("opinionated wrapper around OpenTelemetry") | full-stack spans + AI; cheapest at scale | vendor-backed (Pydantic); flat **$2/1M spans** | proprietary SaaS (SDK OSS) | cheapest/easiest if SaaS egress were acceptable — it is **not** here |
| **OpenLLMetry (Traceloop)** | yes (it's an SDK; point at any OTel backend) | **yes** (OTel instrumentation lib) | auto-captures model, prompt/completion tokens, latency, errors as OTel spans | Traceloop-maintained, multi-language (py/ts/go/ruby) | **Apache-2.0** | the *instrumentation* layer that feeds Phoenix/Langfuse/any OTel backend |
| **LangSmith** | mostly SaaS | partial | traces, evals, datasets | LangChain-backed, widely used | proprietary SaaS | per-seat + per-trace billing; "collapses under agentic workloads"; egress |
| **W&B Weave / Helicone / Braintrust** | Helicone OSS self-host; others SaaS-leaning | varies | traces/evals/cost | vendor-backed | mixed | viable but no privacy/dep edge over Phoenix/Langfuse here |

---

## 2) Ranked dive-in queue (orchestrator scoring)

Formula (from `orchestrator.md` ll.159–167):
`priority = 0.40·(effect×confidence) + 0.20·phase_fit + 0.15·risk_reduction + 0.10·uncertainty − 0.15·cost_to_test`
— `confidence`: shipped+public+maintained → high; paper-only → low (RESEARCH_ONLY capped ≤0.3). `cost_to_test`: config swap ≈0, new infra ≈1. `effect` must move a *measured* number.

**Measured numbers we target:** (M1) failure-diagnosis time per failed run; (M2) % of runs whose logs are *actionable* (level + run-id + role correlation present); (M3) cost/token visibility (already partly served by `trace.jsonl`); (M4) availability of a per-role **waterfall** + cost dashboard that `trace.jsonl` does not render.

| # | Candidate | effect | conf | phase_fit | risk_red | uncert | cost_test | **priority** | Triage |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **structlog** (replace `log.py` formatter/processor chain) | 0.65 | 0.90 | 1.0 | 0.55 | 0.25 | 0.10 | **0.654** | ADOPT-candidate |
| 2 | **Arize Phoenix** (local OTel waterfall + evals) | 0.80 | 0.80 | 0.8 | 0.70 | 0.45 | 0.55 | **0.617** | TRIAL |
| 3 | **OpenLLMetry/Traceloop → OTel emit** (GenAI semconv on `trace.jsonl` events) | 0.55 | 0.75 | 0.7 | 0.60 | 0.40 | 0.45 | **0.535** | TRIAL |
| 4 | **Langfuse** (self-host, full platform) | 0.80 | 0.85 | 0.6 | 0.65 | 0.30 | 0.90 | **0.486** | DEFER (infra) |
| 5 | **OTel GenAI semconv** (adopt the attribute names only) | 0.40 | 0.70 | 0.7 | 0.55 | 0.35 | 0.20 | **0.500** | ADOPT-cheap (naming) |
| 6 | **loguru** | 0.45 | 0.85 | 0.8 | 0.40 | 0.20 | 0.15 | **0.495** | ALT to #1 |
| 7 | **Pydantic Logfire** | 0.85 | 0.90 | 0.7 | 0.70 | 0.35 | 0.30 (SaaS) | **0.685 raw → DISQUALIFIED** | DEFER (privacy: SaaS-only) |

**Score notes (anti-gaming, sub-scores tied to evidence):**
- **#1 structlog** — `effect` 0.65: directly moves M2 (run-id/role binding via `contextvars`, "works correctly across async boundaries without extra setup") and modestly M1 (consistent JSON, redaction processors). `confidence` 0.90: shipped since 2013, Production/Stable, dual Apache+MIT, releases through 2025. `cost_to_test` 0.10: a formatter/processor swap behind the existing `log.py` surface — near config-swap. Highest priority because high-confidence × meaningful-effect × ~zero cost.
- **#2 Phoenix** — `effect` 0.80: only candidate that delivers **M4** (a per-role waterfall + eval view `trace.jsonl` can't render) plus M1. `confidence` 0.80: shipped OSS, 10k★, one-command Docker, OTLP-native. `cost_to_test` 0.55: stands up new local infra (a container) but **no egress** and no account — privacy-clean. `uncertainty` 0.45: genuinely under-tested *for our event shape* — we'd learn whether spans-per-dispatch beat the flat JSONL.
- **#3 OpenLLMetry** — feeds #2/#4; `cost_to_test` 0.45 (a dep + emit shim). Lower `effect` alone because it's plumbing, not a view; high leverage *combined* with #2.
- **#4 Langfuse** — strong `effect`/`confidence` (MIT, 28k★, ClickHouse-backed) but `cost_to_test` 0.90: self-host needs "Postgres + ClickHouse + Redis + S3", "≥4 vCPU / 8 GB / 100 GB"; Logfire's own writeup claims real deployments "required 500+ vCPUs" at volume. Heavy for a single-box privacy-sensitive loop → **defer** until #2 proves the view is worth it.
- **#5 OTel GenAI semconv (names only)** — adopting `gen_ai.usage.input_tokens` / `gen_ai.request.model` as our field names is ~free and future-proofs any later backend. RESEARCH-ish only in that the spec is **moving repos / churning** (`uncertainty` 0.35) — adopt the *stable* attribute names, don't chase the bleeding edge.
- **#7 Logfire** — would top the queue on raw score (cheapest, flattest pricing, OTel-native), but it is **SaaS-only** ("no" self-host) → every span egresses. **Disqualified** by the privacy posture, not by the math. Recorded so the decision is explicit, not silently dropped.
- No RESEARCH_ONLY candidate is floated above confidence 0.3; nothing here is paper-only — all are shipped, public, maintained.

---

## 3) One-variable A/B experiments (top 3, vs the stdlib `log.py` baseline)

All three are framed for `experiments/run_experiment.py` (PACE-gated A/B; accept a variant only if `evals/acceptor.py` says it is *significantly* better — not on raw score).

### Experiment 1 — structlog as `log.py`'s formatter (INCREMENTAL, cheapest)
- **Instrument:** route a fixed corpus of recorded failing runs through both loggers; both write `<run_dir>/log.jsonl`.
- **Single variable:** the formatter/emit path — `A` = stdlib hand-rolled JSON (current `log.py`); `B` = structlog processor chain (`merge_contextvars` + JSONRenderer, run-id/role bound via `bind_contextvars`). **Everything else identical** (same call sites, same level API, same file path).
- **Metric:** M2 — % of log lines carrying `{level, run_id, role}` correctly under concurrent role dispatch (structlog's contextvars should win on async/threaded correlation); secondary M1 — time-to-locate the failing event in a seeded-bug run.
- **Cheapest trial:** add `structlog` to a venv, write a ~30-line `log.py` variant with the same public surface, diff the two `log.jsonl` outputs. No infra.
- **Decay/maint:** LOW — Apache+MIT, maintained since 2013, releases through 2025.
- **Privacy:** CLEAN — in-process, no egress, +1 dep (vs stdlib-only bar — the only posture cost).

### Experiment 2 — OTel exporter to local Phoenix vs flat `trace.jsonl` (STEP-CHANGE)
- **Instrument:** emit each `run_trace.py` event **both** as today's JSONL line *and* as an OTel span (one span per `role_dispatch`, child spans for `verify`/`verdict`), exported to a **local** Phoenix container (`docker run -p 6006:6006 arizephoenix/phoenix`).
- **Single variable:** the *consumption surface* — `A` = read `trace.jsonl` by hand/grep; `B` = Phoenix waterfall + cost view. Recorded events identical.
- **Metric:** M1 — wall-clock to diagnose 5 seeded failure modes (which role stalled, where cost spiked) in A vs B; M4 — can a reviewer answer "which dispatch burned the most tokens?" without writing code.
- **Cheapest trial:** Phoenix is one Docker command, no account, runs on the box; use OpenLLMetry/OpenInference to map events → spans. Tear down the container after.
- **Decay/maint:** LOW-MED — Phoenix OSS 10k★, active; **ELv2 license** (Elastic v2) — fine for internal self-host, *check before any SaaS/managed-service redistribution*.
- **Privacy:** CLEAN — fully local, no API key, no cloud account, **zero egress**. This is the privacy-preferred step-change.

### Experiment 3 — OTel GenAI attribute names on our events (INCREMENTAL, future-proofing)
- **Instrument:** rename `trace.jsonl`'s token fields to the GenAI semconv names (`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.request.model`) behind a compat shim.
- **Single variable:** field naming — `A` = current ad-hoc keys; `B` = semconv keys. Same data.
- **Metric:** M3/M4 — does any OTel backend (Phoenix in Exp 2) ingest our events with *zero* mapping code when names match the spec?
- **Cheapest trial:** a dict-rename in `run_trace.py`; assert Phoenix shows token/cost without a custom mapper.
- **Decay/maint:** MED — spec is **actively moving** (just migrated to a dedicated `semantic-conventions-genai` repo, v1.42.0); pin to *stable* attribute names, expect minor churn.
- **Privacy:** CLEAN — naming only, no new egress.

**Recommended ordering:** run Exp 1 first (near-zero cost, settles the incremental question), then Exp 2 (the real step-change test), with Exp 3 folded into Exp 2's emit shim.

---

## 4) Bottom-line recommendation

Tied to the **privacy-sensitive, self-host-preferring, low-dep, PACE-gated** posture:

- **ADOPT NOW (incremental):** finish the stdlib `harness/log.py` (kills the 22 bare `print()`s — that's the biggest single hygiene win and needs no dep), and **adopt OTel GenAI *attribute names*** for `trace.jsonl`'s token/model fields (free, future-proofs any backend). These are config-swaps, not bets.
- **TRIAL (experiment, PACE-gated):**
  1. **structlog behind `log.py`** (Exp 1) — highest priority (0.654): high-confidence, ~zero cost, real win on async/role-correlated logs. If the acceptor shows it significantly beats the hand-rolled formatter on M2, take the one dep; if not, the stdlib version stands and we've lost nothing.
  2. **Arize Phoenix, local** (Exp 2, priority 0.617) — the privacy-clean step-change: one Docker command, OTLP-native, **no egress**, gives the per-role waterfall + cost view `trace.jsonl` structurally cannot. Trial it as a *read surface* over events we already emit.
- **DEFER (research-only / blocked):**
  - **Langfuse** — best full OSS platform (MIT, 28k★) but the self-host footprint (Postgres+ClickHouse+Redis+S3; "≥4 vCPU/8 GB", "500+ vCPUs" at scale) is too heavy for a single-box loop *until Phoenix proves the view earns its keep*.
  - **Pydantic Logfire** — cheapest and flattest-priced ($2/1M spans, OTel-native) and would top the raw score, but **SaaS-only = data egress**. **Disqualified by privacy**, revisit only if a self-host tier ships or the privacy posture relaxes.
  - **loguru** — fine library, but no edge over structlog here (slower JSON, OTel only via stdlib bridge); keep as the fallback if structlog's dep is rejected.

Net: the dramatic step-change worth A/B-testing is **local Phoenix** (only because it's self-hostable with zero egress); the incremental win worth adopting/trialing is **structlog**; everything SaaS or heavy-infra is deferred on privacy/dep grounds.

---

## Sources (retrieved 2026-06-30)

- Better Stack — Python logging libraries comparison: https://betterstack.com/community/guides/logging/best-python-logging-libraries/ — "structlog shows approximately a 25% performance advantage over Loguru for JSON output … structlog has native OpenTelemetry support, while Loguru requires bridging through the standard library."
- structlog docs (contextvars / stdlib / license): https://www.structlog.org/en/stable/contextvars.html — "safe to be used both in threaded as well as asynchronous code"; license: "dually licensed under the Apache License, Version 2 and the MIT license."
- structlog GitHub / PyPI: https://github.com/hynek/structlog , https://pypi.org/project/structlog/ — "Development Status :: 5 - Production/Stable"; "used in production at every scale since 2013"; ~4.8k stars; releases 25.4.0 / 25.5.0 in 2025.
- OpenTelemetry GenAI spans (status + token attributes): https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/ — "Semantic conventions 1.42.0"; "GenAI semantic conventions have moved to the OpenTelemetry GenAI semantic conventions repository. This page … is no longer maintained in this repository." Token attrs `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` / `gen_ai.request.model` per the GenAI SIG (formed April 2024).
- OpenTelemetry for LLMs (SIG scope): https://openobserve.ai/blog/opentelemetry-for-llms/ — GenAI SIG "expanded to cover agent orchestration, MCP tool calling, content capture, and quality evaluation."
- Arize Phoenix docs + GitHub: https://arize.com/docs/phoenix , https://github.com/arize-ai/phoenix — "self-hosted to keep sensitive data on your own infrastructure, and is ELv2 licensed"; "docker run -p 6006:6006 -i -t arizephoenix/phoenix"; "runs entirely on your machine with a single function call — no API keys, no cloud account, no vendor lock-in"; "built on top of OpenTelemetry … accepts traces over OpenTelemetry (OTLP)"; 10,000+ stars.
- Langfuse self-hosting: https://langfuse.com/self-hosting , https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse — "Postgres for transactional … ClickHouse for … OLAP … Redis/Valkey cache … S3"; "Allocate at least 4 vCPU and 8 GB RAM, starting with 100 GB disk"; "can be deployed within a VPC or on-premises … internet access being optional."
- Langfuse OSS leadership + ClickHouse acquisition: https://www.firecrawl.dev/blog/best-llm-observability-tools , https://langfuse.com/ — "open source leader … over 28,000 GitHub stars … MIT license"; "acquired by ClickHouse in January 2026 … MIT license preserved."
- Pydantic Logfire pricing & self-host: https://pydantic.dev/articles/ai-observability-pricing-comparison — "Logfire charges $2.00 per million spans, flat"; "8× less expensive than Arize, 27× less expensive than Langfuse, and 40× less expensive than LangSmith"; on Langfuse self-host: "Real-world deployments have required 500+ vCPUs"; on LangSmith: per-seat/per-trace, "collapses under agentic workloads." (Logfire is SaaS — its own FAQ confirms no self-host tier: https://pydantic.dev/docs/logfire/get-started/faq/.)
- OpenLLMetry / Traceloop: https://github.com/traceloop/openllmetry , https://www.traceloop.com/docs/openllmetry/introduction — "Apache 2.0 license"; "captures LLM-specific data points such as model name and version, prompt and completion tokens … latency, and errors"; "outputting standard OpenTelemetry data that can be connected to your observability stack."
- Logfire vs LangSmith/Langfuse/Arize scope: https://softcery.com/lab/top-8-observability-platforms-for-ai-agents-in-2025 — full-stack OTel vs LLM-only scope framing.
