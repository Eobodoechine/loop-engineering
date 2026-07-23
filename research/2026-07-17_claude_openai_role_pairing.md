# Claude x OpenAI role pairing — decision dossier

**Date:** 2026-07-17 · **Mode:** Researcher Mode D (platform/domain) + repo-state recon
**Question:** Can we pair Claude models with OpenAI models across loop-team roles (orchestrator, test-writer, implementer, plan-check/post-build reviewer, researcher)? What exists, what is possible today, and which 2–3 pairing architectures are worth running?
**Motivating hypothesis (researched, not assumed):** a reviewer from a different model family has decorrelated failure modes and catches defects a same-family reviewer shares with the author.
**Citation roots:** repo paths are relative to `<HOME>/Claude/loop/`. Every external claim carries a URL I actually opened, or an UNVERIFIED tag.

---

## 0. Executive summary

- **More is already built than the mission implied.** The repo has a live per-role provider router (`anthropic` | `openai`) in `loop-team/runner/dispatch.py`, a working OpenAI cross-family judge in `loop-team/optimize/llm.py`, a full cross-family disagreement-mining harness in `loop-team/evals/disagreement_harness.py`, a sealed `codex exec` subprocess adapter + subscription pilot (built and plan-checked, real run not yet successfully executed — first attempt died on an argv-ordering bug now spec'd for fix), an inverse bridge doc for Codex-as-orchestrator with Claude sub-roles, and a hooks-side Codex event normalizer with 5 open enforcement-parity gaps logged in `fix_plan.md`.
- **Possible today with ~zero build:** OpenAI API as a second, decorrelated judge/plan-check lens (Architecture C). `OPENAI_API_KEY` file exists at `~/.config/openai/key` (existence checked, not read), `openai` SDK 2.41.1 installed, `openai_llm()` already written.
- **Possible with moderate build:** `codex exec` read-only as the plan-check/post-build reviewer (Architecture A) — but the local `codex` binary (0.41.0) is severely stale vs upstream 0.144.5 (released 2026-07-16), the JSONL event schema drifted between those versions, and our credit/hygiene gates cannot currently see or credit a subprocess reviewer without a new artifact-credit path.
- **Evidence on the hypothesis is real but indirect.** Peer-adjacent literature strongly supports decorrelation mechanisms (self-preference bias is measured and linear in self-recognition; disjoint-family judge panels beat single big judges; heterogeneous debate peers cut harmful revisions ~89%→35%). Direct, controlled evidence that cross-family CODE REVIEW catches more real defects is thin — mostly vendor blogs and a 7-star tool. The honest move is to measure it in-house; the instrument (`disagreement_harness.py` + the D1 fault-injection corpus) already exists.

---

## 1. Repo state — what integration already exists

### 1.1 API path (live today)

**Per-role provider routing — `loop-team/runner/dispatch.py`:**
- `LoopTeam._get_llm(role_name)` resolves "1. Per-role override in config (e.g. `role.coder.provider=openai`) 2. Default config provider" (dispatch.py:78-80).
- `provider == "openai"` → `optimize.llm.openai_llm(model=model)` (dispatch.py:107-108); anything else raises `Unknown provider … Expected 'anthropic' or 'openai'` (dispatch.py:110).
- `dispatch_role()` prepends the role file and routes every call through `call_with_retry` (dispatch.py:139-179). Config lives at `~/.loop-team-config` (dispatch.py:60).

**OpenAI judge factory — `loop-team/optimize/llm.py`:**
- `openai_llm(model, …)` (llm.py:148-207), docstring: "a CROSS-FAMILY judge, the real fix for the model-independence weakness (all-Anthropic judges fail in correlated ways; a disjoint family gives true PoLL diversity)" (llm.py:149-151).
- Reads `OPENAI_API_KEY`; error text instructs `OPENAI_API_KEY=$(cat ~/.config/openai/key)` (llm.py:164-168). Uses Chat Completions (`client.chat.completions.create`, llm.py:197) — **not** the Responses API and **no** strict-schema structured output; contract is plain `llm(prompt)->str`. Temperature-0 with automatic drop when a reasoning model rejects it (llm.py:192-202); proactive RPM spacing via `OPENAI_MIN_INTERVAL_S` (llm.py:159-173).
- The retry taxonomy already knows OpenAI's permanent quota-429 shape ("insufficient_quota", llm.py:38-45).
- Anthropic sibling defaults to `claude-haiku-4-5-20251001` (llm.py:117).

**Cross-family disagreement miner — `loop-team/evals/disagreement_harness.py`:**
- Runs "TWO judges of disjoint model families over a pool of cases" — the OpenAI judge via `optimize.llm.openai_llm` and the Anthropic verifier — and "records every case where the two verdicts DISAGREE", each flagged `needs_human_gold: true` (disagreement_harness.py:2-19). Rationale in-file: "an all-Anthropic panel fails in correlated ways (self-preference / EPC collapse); a disjoint OpenAI family gives true Panel-of-LLM-Judges diversity" (disagreement_harness.py:26-28). Example invocation uses `--openai-model gpt-4o-mini` (disagreement_harness.py:35) — a dated model id; works with any current id.

### 1.2 CLI path (`codex exec` subprocess) — built, sealed, not yet successfully run live

**Adapter — `loop-team/runner/codex_exec_adapter.py`:**
- `CodexExecAdapter` "Execute one frozen Codex request through an argv-only boundary" (codex_exec_adapter.py:664-665). `_argv()` builds: `codex --ask-for-approval never exec --cd <clone> --model <m> --sandbox read-only|workspace-write -c model_reasoning_effort=<effort> [--skip-git-repo-check] --json --output-last-message <path> -` (codex_exec_adapter.py:1274-1289). Note the approval flag is already in the fixed (global, pre-`exec`) position.
- JSONL stdout parser recognizes `session.started`, `session_configured`, `turn.completed`, and `msg.type == "token_count"` events (codex_exec_adapter.py:1397-1413) — the **0.41.0-era** schema (see §2.1 drift risk).
- `ProductionSeatbeltPreflight`: pins `CODEX_BINARY = /opt/homebrew/bin/codex`, `CODEX_VERSION = "codex-cli 0.41.0"`, `TARGET_MODELS = ("gpt-5.6-sol","gpt-5.6-terra","gpt-5.6-luna")`, a model/effort/sandbox probe MATRIX, and protected-roots write-denial probes (codex_exec_adapter.py:232-248, 328-432); reads `~/.codex/models_cache.json` for model-slug freshness (codex_exec_adapter.py:258-260, 434-456).
- Usage normalized with `provider="openai"`, `execution_mode="codex_subscription"`, `billing_authority = "unavailable_subscription_no_usd_billing_authority"`, `promotion_eligible = False` (codex_exec_adapter.py:801-814). `PROMOTION_BOUNDARY = "PILOT_ONLY/NO_ROUTING_PROMOTION"` (codex_exec_adapter.py:30).
- Secret-redaction patterns for bearer/api-key/sk- strings baked in (codex_exec_adapter.py:686-694).

**Pilot controller — `loop-team/runner/codex_subscription_pilot.py`:**
- "Authority-gated controller for the fixed non-promoting Codex pilot" (line 1). `EXACT_CALL_PLAN`: 1 smoke (`gpt-5.6-sol`/high) + 3 planner (`sol`/high) + 3 incumbent_coder (`gpt-5.6-terra`/high) + 3 challenger_coder (`gpt-5.6-luna`/medium) — max 10 provider calls (codex_subscription_pilot.py:~50-58).

**Pilot spec — `loop-team/runs/2026-07-16_model-routing-pace/specs/codex_product_pilot.md`:**
- "one-time `codex_subscription` pilot against installed `codex-cli 0.41.0`, not a routing-policy experiment capable of promotion" (spec lines 3-7); arms table §2.1. Real execution `HUMAN_RECONFIRMATION_REQUIRED`.
- **Governance caveat:** project memory records that this run's spec once had its plan-check verdict misreported (real `PLAN_FAIL` relayed as PASS; the hash cited belonged to a superseded gitignored draft) — memory `project_model_routing_pace_spec_fabricated_claim`. Any resumption should re-verify the spec's current review status from scratch.
- **Claude-side sibling:** `loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md` — "Spec only. No implementation exists yet … the direct Claude-side sibling of the already-executed `codex_subscription` pilot" (header). (Its "already-executed" phrasing refers to the Codex pilot's *implementation+fake-tests*, not a completed real run — see next bullet.)
- **Real-run status:** the first real attempt failed — "Bug reproduced: run id `2026-07-16-model-routing-pace-prepare-019f698a-06`, packet 0 of 10, exit code 2, 0 network attempts" (`loop-team/runs/2026-07-17_codex-exec-argv-order-fix/specs/spec.md`, header). Root cause: `--ask-for-approval` argv ordering. **Two overlapping fix specs exist and need reconciliation before any Coder dispatch:** `runs/2026-07-16_codex-exec-approval-flag-fix/specs/spec.md` (Revision 3; rounds of PLAN_FAIL documented in its header) and `runs/2026-07-17_codex-exec-argv-order-fix/specs/spec.md` (self-contained; its §0 explicitly recommends "a human or Oga should choose one spec to carry forward, most likely this one").

### 1.3 Inverse bridge — Codex as orchestrator, Claude as sub-roles

`loop-team/CODEX_CLAUDE_TEAM.md`:
- "Codex/Oga stays in this chat as coordinator, primary builder, integrator, and final local verifier. Claude Code supplies independent non-Coder roles through `claude -p`." (lines 5-6).
- Roles supported via `loop-team/harness/claude_role_runner.py`: `plan-check-verifier`, `post-build-verifier`, `test-writer`, `researcher`, `gold-judge`, `live-smoke`; "The `coder` role is intentionally not supported by this bridge" (lines 56-65). The runner mechanically validates the final verdict line (`LOOP_GATE: PLAN_PASS|PLAN_FAIL`, `VERDICT: PASS|FAIL|FALSE-PASS`, lines 32-54). This file is the proven template for a mirror-image `codex_role_runner`.

### 1.4 Hook/event normalization for Codex runtimes — what exists and what is open

**Existing normalizer — `hooks/codex_transcript_adapter.py`:**
- Purpose: "produce the SAME normalized shape the existing logic already consumes (a list of VerifierDispatch tuples pairing a verifier-shaped dispatch with its result text) so the RUNLOG_MISSING / thrash-past-green decision-making in those two files is reused unchanged" — consumed by `hooks/loop_stop_guard.py` and `hooks/micro_step_gates.py` (codex_transcript_adapter.py:11-17).
- `_detect_runtime()` is a strict structural discriminator: "codex" iff a transcript line's own top-level `"type" == "session_meta"`; "claude_code" iff `message.content[]` contains an item with `"type" == "tool_use"`; else "unknown" (codex_transcript_adapter.py:68-119).
- After `H-CODEX-SHAPE-STALENESS-FIX-1` it handles BOTH Codex multi-agent shapes (OLD `multi_agent_v1`, NEW `collaboration`) across 6 call sites (fix_plan.md:10242-10258).
- Also present: `hooks/pre_tool_use_oga_guard.py` normalizes Codex `spawn_agent` in `_dispatch_view` (fix_plan.md:7333, 10254); `hooks/codex_hook_stdin_capture.py` captures live Codex hook stdin (fix_plan.md:10414-10416); fixture builders in `hooks/_codex_fixture_builders.py`.

**What it does NOT cover — open `fix_plan.md` gap entries (headings verbatim):**
1. `## H-CODEX-MESSAGE-ENCRYPTION-MARKER-GAP-1 (OPEN, filed 2026-07-17, priority: MEDIUM -- disclosed, accepted limitation, not a defect H-CODEX-SHAPE-STALENESS-FIX-1 could close) -- marker-based text enforcement is structurally non-functional for `collaboration`-namespace (NEW-shape) Codex dispatches` (fix_plan.md:10313-10316). NEW-shape `spawn_agent.message` is Fernet-encrypted ("339/339 real messages checked carry the literal `gAAAAA...` version-byte prefix", fix_plan.md:10318-10320) → `SPEC_SHA256=`/`REVIEWED_SPEC_SHA256=`/`REPO_HEALTH_*` marker scans can never match, and the RUNLOG_MISSING Stop-gate "fail[s] OPEN (silently) in the realistic/common case" (fix_plan.md:10326-10333).
2. `## H-CODEX-CLAUDE-ONLY-CREDIT-PARSER-BLIND-1 (OPEN, filed 2026-07-17, priority: HIGH …) -- `pre_tool_use_oga_guard.py`'s PreToolUse spec-bound Verifier/Coder credit gate (~lines 334-392) calls `spec_bound_verifier_credit.py::authorize_coder_from_transcript()`, which internally parses the transcript via … a CLAUDE-CODE-ONLY parser` (fix_plan.md:10340-10354) — `records` is "unconditionally `[]` for EVERY real Codex transcript"; OLD shape actively wrongly DENIES, NEW shape silently no-ops (fix_plan.md:10356-10361). Nnamdi's recorded scope decision: sweep the whole Claude-Code-only-extraction class in one follow-up pass (fix_plan.md:10363-10368).
3. `## H-CODEX-CLAUDE-ONLY-HYGIENE-GATE-BLIND-1 (OPEN, filed 2026-07-17, priority: HIGH -- no enforcement layer anywhere in this framework, PreToolUse or Stop-hook, can currently catch a hygiene-violating or status-doc-adjacent Codex-dispatched Verifier …)` (fix_plan.md:10370-10374) — two dispatch-gating blocks gate on raw `tool_name` (`"spawn_agent"`), and the Stop-hook copies scan `_TOOL_USES`/`_TOOL_RESULTS` built by the same blind helpers (fix_plan.md:10375-10385).
4. `## H-CODEX-SHAPE-SELECTION-UNKNOWN-1 (OPEN, filed 2026-07-17, priority: LOW …) -- no known feature-flag, config file, or user-visible toggle determines whether a given new Codex Desktop session uses the OLD (`multi_agent_v1`) or NEW (`collaboration`) `spawn_agent` namespace` (fix_plan.md:10395-10398) — both shapes proven live on the same day, same `cli_version 0.144.2` (fix_plan.md:10400-10403).
5. `## H-CODEX-V2-PRETOOLUSE-LIVE-CAPTURE-GAP-1 (OPEN, filed 2026-07-17, priority: MEDIUM -- real but fail-safe residual risk, not yet closed by a live capture) -- `_dispatch_view()`'s NEW-shape branch (added by H-CODEX-SHAPE-STALENESS-FIX-1) was never validated against a real, live PreToolUse `tool_input` payload for a `collaboration`-namespace `spawn_agent` call` (fix_plan.md:10409-10412).
6. Older, related: `## H-CODEX-WORKER-GUARD-MULTIAGENTV1-UNSUPPORTED-1 (OPEN -- by-design scope boundary, filed 2026-07-16, priority: MEDIUM) -- namespace=="multi_agent_v1" (OLD) Codex dispatches remain permanently denied by the exact-worker-identity guard; tracked here per spec instruction, not a second investigation` (fix_plan.md:10032); `## H-CHECKPOINTING-CODEX-PARITY-PROOF-1 — EVIDENCED-FIXTURE-SLICE / LIVE-STOP OPEN (2026-07-11)` (fix_plan.md:7847 — fixture-proven, live Codex Stop-hook capture still open); `H-CODEX-SPAWN-PRETOOLUSE-DISPATCH-GAP-1 — VERIFIED-MECHANICAL-SLICE (2026-07-11)` (fix_plan.md:7314). Closed umbrella: `## H-CODEX-SHAPE-STALENESS-FIX-1 (CLOSED, filed 2026-07-17 …)` (fix_plan.md:10222-10225, proof block 10289-10298).

**Net:** for a Codex process running as a *peer session* (Desktop/interactive multi-agent), our observation layer exists but has two HIGH-priority blind spots (credit parser, hygiene gate) and one structural one (Fernet-encrypted NEW-shape messages). For a Codex process we launch as a *sealed subprocess* (`codex exec` via the adapter), observation is by construction better than hooks: argv allowlist, Seatbelt containment probes, JSONL capture, hash-bound output files.

### 1.5 Portability doc + research archive

- `PORTABILITY.md` maps Codex CLI hooks: "hooks via `hooks.json` / `[hooks]` in `config.toml`" with links to the official hooks docs and config reference, plus known issues (#16732 edit-bypass, #18491 expansion, #18067 silent failures on large files, #19385) and — critically — "`codex exec` (headless): **UNVERIFIED** — a 10-minute empirical test" for whether hooks fire under headless exec (PORTABILITY.md:44-56).
- A large Codex research archive exists under `research/` (noted, not re-read per dispatch): `codex-pretooluse-role-caller-identity-2026-07-16.md`, `codex-pretooluse-session-id-caller-identity-2026-07-16.md`, `codex-pretooluse-agent-id-caller-identity-2026-07-16.md`, `codex-spawn-agent-v2-shape-reconciliation-2026-07-16.md`, `codex-child-transcript-task-complete-staleness-2026-07-16.md`, `spec-codex-parity-and-consent-installer-2026-07-09.md`, `gmail-connector-codex-vs-loopteam-comparison-2026-07-10.md`, `run-logging-enforcement-gap-codex-vs-claude-code-2026-07-09.md`, `codex-followup-token-spend-reduction-2026-07-08.md`, `codex-followup-drift-validator-reconciliation-2026-07-08.md`, `session-continuation-codex-parity-consent-installer-2026-07-09.md`.
- Prior cross-runtime hook-trust lesson: `H-CODEX-PARITY-2026-07-08` (CLOSED, fix_plan.md:4133-4228) — editing `~/.codex/hooks.json` invalidated Codex's per-hook SHA-256 `trusted_hash` in `~/.codex/config.toml` `[hooks.state]`, silently disabling all 5 safety hooks until Nnamdi re-trusted them (source-confirmed in `codex-rs/hooks/src/engine/discovery.rs` + `codex-rs/config/src/fingerprint.rs`).

### 1.6 Local tooling state (checked this session)

- `which codex` → `/opt/homebrew/bin/codex`; `codex --version` → `codex-cli 0.41.0`. **Stale**: upstream latest is 0.144.5 (2026-07-16, §2.1), and Codex Desktop sessions on this machine already report `cli_version 0.144.2` (fix_plan.md:10400-10401).
- `~/.codex/` exists and is populated: `AGENTS.md`, `ambient-suggestions`, `archived_sessions`, `attachments`, `auth.json` (auth artifact present — consistent with ChatGPT-plan login; file not read).
- `printenv | grep -i openai` → nothing set in this shell. But `~/.config/openai/key` EXISTS (existence checked only; content never read) — exactly where `llm.py:168` expects it.
- Python SDKs installed: `openai` 2.41.1, `anthropic` 0.105.2.
- `codex mcp serve` (Codex as an MCP stdio server for Claude Code) has been used live on this machine: a Claude Code process was configured with `--mcp-config {"mcpServers":{"codex":{"type":"stdio","command":"codex","args":["mcp","serve"]}}}` (fix_plan.md:10420-10422).

---

## 2. Live platform findings (July 2026)

### 2.1 OpenAI Codex CLI headless (`codex exec`)

Source: https://github.com/openai/codex (repo page, opened) and the official non-interactive docs at https://developers.openai.com/codex/noninteractive (308-redirects to https://learn.chatgpt.com/docs/non-interactive-mode, opened).

- **Latest release:** 0.144.5, released 2026-07-16 (github.com/openai/codex repo page). Our pinned 0.41.0 is roughly 100 releases behind.
- **Auth (verbatim from repo page):** "We recommend signing into your ChatGPT account to use Codex as part of your Plus, Pro, Business, Edu, or Enterprise plan. You can also use Codex with an API key, but this requires additional setup." Headless API-key form: `CODEX_API_KEY=<api-key> codex exec` — docs advise setting it inline, "not as environment variables in CI jobs containing untrusted code"; ChatGPT-account auth persists via `~/.codex/auth.json` (learn.chatgpt.com/docs/non-interactive-mode).
- **JSON/structured output:** `--json` → "stdout becomes a JSON Lines (JSONL) stream so you can capture every event" with event types `thread.started`, `turn.started`, `turn.completed`, `item.*`, `error`; `--output-schema` → "request a final response that conforms to a JSON Schema"; `-o/--output-last-message <path>` writes the final message to a file (learn.chatgpt.com/docs/non-interactive-mode).
- **Schema drift (repo-impacting):** our adapter parses `session.started` / `session_configured` / `turn.completed` (codex_exec_adapter.py:1404-1413) — the 0.41.0 grammar. Current docs list `thread.*` / `item.*`. Upgrading the binary requires porting `_parse_jsonl` and possibly `_argv` (docs for current `exec` list `--sandbox` but do not list `--ask-for-approval`; whether the global flag still exists in 0.144.x argv grammar is UNVERIFIED — the argv fix specs validated against the *installed 0.41.0* binary only).
- **Sandbox/approvals:** default read-only; `--sandbox workspace-write`, `--sandbox danger-full-access`; `--ignore-user-config` (skip `$CODEX_HOME/config.toml`), `--ignore-rules` (skip execpolicy `.rules`); `--ephemeral` "doesn't persist session rollout files to disk" (learn.chatgpt.com/docs/non-interactive-mode). Note: 0.41.0 has no `--ephemeral` (adapter's own disclosure string, codex_exec_adapter.py:1301-1303) — an upgrade would let us stop worrying about `~/.codex/sessions` side-writes for sealed calls; conversely `--ephemeral` would remove the rollout files our transcript adapter reads for peer-session observation. Session resume: `codex exec resume --last` / `codex exec resume <SESSION_ID>`.
- **Model selection:** `--model <slug>` (repo argv, confirmed in current cheat-sheet docs); per-review model configurable via `review_model` in `~/.codex/config.toml`; `/review` runs a code review, recommended pattern includes read-only pre-commit review (source: https://codex.danielvaughan.com/2026/03/27/codex-cli-code-review-pr-integration/ — third-party knowledge base, flagged as secondary).
- **Hooks (per-turn events for our observation layer):** official hooks docs (https://developers.openai.com/codex/hooks → https://learn.chatgpt.com/docs/hooks, opened): events `SessionStart`, `SubagentStart`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `UserPromptSubmit`, `SubagentStop`, `Stop`; "Turn hooks list `turn_id` as a Codex-specific extension"; config via `hooks.json` or `[hooks]` in `config.toml` (`~/.codex/` or `<repo>/.codex/`); stdin JSON carries `session_id`, `cwd`, `hook_event_name`, `model`; "Only `type: \"command\"` handlers run today"; trust: "Before a non-managed command hook can run, Codex requires you to review and trust the exact hook definition" (the trust-hash trap we already hit — §1.5), with `--dangerously-bypass-hook-trust` as an automation escape. **The docs do not say whether hooks fire under `codex exec`** — matches PORTABILITY.md's standing UNVERIFIED flag; still needs the 10-minute empirical test before any architecture depends on it.
- **MCP:** Codex is both an MCP client — `[mcp_servers.<name>]` in `~/.codex/config.toml` (stdio `command`/`args`/`env`, or streamable HTTP `url` + `bearer_token_env_var`), managed by `codex mcp add`, verified with `/mcp` (official doc: https://developers.openai.com/codex/mcp; community corroboration: https://agentpatch.ai/blog/codex-cli-mcp-setup/) — and an MCP server (`codex mcp serve`), already used live on this machine (fix_plan.md:10420-10422).

### 2.2 OpenAI API for judge/reviewer duty

Sources opened: https://developers.openai.com/api/docs/models (301-redirect target of platform.openai.com/docs/models), https://developers.openai.com/api/docs/pricing, https://developers.openai.com/api/docs/guides/structured-outputs (via search snippet + guide listing; strict-mode semantics corroborated by https://openai.com/index/introducing-structured-outputs-in-the-api/).

- **Current lineup (frontier):** `gpt-5.6-sol` — "Frontier model for complex professional work", 1.05M-token context; `gpt-5.6-terra` — balances intelligence and cost, 1.05M; `gpt-5.6-luna` — "Optimized for cost-sensitive workloads", 1.05M. All support "Functions, Web search, File search, Computer use" (developers.openai.com/api/docs/models). This exactly matches the repo's pinned `TARGET_MODELS` (codex_exec_adapter.py:237) — the pilot's model choices are still current.
- **Specialized:** `gpt-5.3-codex` (agentic-coding model; system card dated Feb 5 2026: https://cdn.openai.com/pdf/23eca107-a9b1-4d2c-b156-7deb4fbc697c/GPT-5-3-Codex-System-Card-02.pdf — "additionally trained on agentic coding tasks including PR creation, code review, debugging sessions" per search-result summary of that card; card PDF itself not page-read this pass → treat the training-mix detail as secondary). Third-party trackers report the Codex product's backbone moved to GPT-5.5+ by May 2026 (https://codex.danielvaughan.com/2026/05/07/codex-cli-model-routing-may-2026-gpt55-gpt54-spark-decision-framework/ — secondary, flagged).
- **Pricing (per 1M tokens, standard tier, verbatim from pricing page):** `gpt-5.6-sol` $5.00 in / $30.00 out / $0.50 cached-in; `gpt-5.6-terra` $2.50 / $15.00 / $0.25; `gpt-5.6-luna` $1.00 / $6.00 / $0.10; `gpt-5.3-codex` $1.75 / $14.00 / $0.175; `gpt-5.4-mini` $0.75 / $4.50 / $0.075; `gpt-5.4-nano` $0.20 / $1.25 / $0.02.
- **Structured output:** strict JSON-schema mode (`response_format: {"type":"json_schema", …, "strict": true}`) is current and supported on GPT-5.6; OpenAI's own eval claim is 100% schema compliance in strict mode (openai.com structured-outputs announcement + developers.openai.com guide). Our `openai_llm()` does not use it yet (plain text contract) — an upgrade candidate, not a blocker (the verdict-line regex contract also works).
- **Which model for review duty:** OpenAI's docs position sol as the frontier "complex professional work" model and terra as the intelligence/cost balance; there is no page I opened that literally says "use X for code review" for the API (the `/review` feature's `review_model` guidance is Codex-product-side). Recommendation derived, not quoted: `gpt-5.6-terra` as the default decorrelated reviewer (mid cost, frontier family), `gpt-5.6-sol` for hard/final gates, `gpt-5.4-mini` or `gpt-5.6-luna` for panel/triage seats. Tag: model-for-review mapping = derived judgment.

### 2.3 Prior art — heterogeneous teams / cross-model verification (all sources opened)

1. **PoLL — "Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models"** (Verga et al.), https://arxiv.org/abs/2404.18796. Finding: a panel of smaller models drawn from disjoint families **outperforms a single large judge across three judge settings and six datasets, reduces intra-model bias, and costs over 7x less**. Directly supports panel-of-families judging; not code-review-specific.
2. **"LLM Evaluators Recognize and Favor Their Own Generations"** (Panickssery, Bowman, Feng), https://arxiv.org/abs/2404.13076. Finding: "LLMs such as GPT-4 and Llama 2 have non-trivial accuracy at distinguishing themselves from other LLMs and humans," and there is "a linear correlation between self-recognition capability and the strength of self-preference bias," validated causally via fine-tuning. This is the measured mechanism behind "a same-family reviewer shares the author's blind spots."
3. **"Heterogeneous LLM Debate Under Adversarial Peers: Honest Gains, Replacement Costs, and Resilience"** (Nilayam et al., submitted 2026-06-18), https://arxiv.org/abs/2606.19826. Finding: with honest peers, harmful revision on MATH-hard dropped **from 89% (homogeneous) to 35%** when an honest heterogeneous peer joined; with an adversarial same-family peer present, adding an honest heterogeneous peer cut the flip rate on initially-correct answers **from 31% to 6%**; abstract: "heterogeneity is therefore not only an attack surface but, when an adversary is already present, also a defense." Held across four model families / three benchmarks. Caveat: reasoning benchmarks, **not** code review.
4. **formin/multi-model-review** (tool), https://github.com/formin/multi-model-review. README: "Write specs with one model, implement with another, and review with a different one"; "a model reviewing its own output often rationalizes" it. Supports Claude (direct session), Codex (CLI with MCP fallback), Gemini (CLI); handoff = on-disk markdown packages (`.cross-review/packages/<timestamp>/` with spec/plan/task briefs + diff manifests). Maturity: **7 stars, v0.1.2 released 2026-06-18, MIT** — pattern-donor, not an adoption candidate.

**Honest assessment of the hypothesis:** the *mechanism* (self-preference bias; correlated same-family failure; diversity gains) is well-evidenced in peer-reviewed-adjacent work (#1-#3). The *specific claim* — cross-family review of code catches defects same-family review misses, at a rate that matters — has only weak direct evidence: vendor content claims "40 to 60 percent higher" detection for cross-family review (https://www.mindstudio.ai/blog/cross-vendor-ai-agent-review-claude-codex — marketing blog, methodology not shown, UNVERIFIED; do not cite as fact), and one report of only 28% finding-overlap between two models on a PR (same source class). Verdict: **plausible, mechanism-backed, unproven at our task distribution — measure it in-house.** The measurement instrument exists: run `disagreement_harness.py` (or the D1 fault-injection corpus, memory `project_d1_fault_injection_status`: 21-case batch, A_s=21.4%) with the Claude verifier vs an OpenAI reviewer and score caught-defect deltas against gold repairs.

---

## 3. Capability matrix

Cost classes: cheap ≈ ≤$1/M-in (gpt-5.4-mini/nano, gpt-5.6-luna, Haiku) · mid ≈ $1.75-2.50/M-in (gpt-5.6-terra, gpt-5.3-codex, Sonnet-class) · expensive (gpt-5.6-sol, Opus-class). Claude-side API prices not re-verified this pass; Claude sub-agents via the Agent tool and `codex` via ChatGPT login are **subscription-metered**, OpenAI API calls are **per-token** — a real budget-shape difference.

| Role | Claude option (today) | OpenAI option | Invocation mechanism | Structured output | Can our PreToolUse/Stop hooks observe it? | Cost class |
|---|---|---|---|---|---|---|
| Orchestrator (Oga) | Claude Code session (current) | Codex Desktop/CLI as Oga with Claude sub-roles (`CODEX_CLAUDE_TEAM.md`) | native session / codex interactive | n/a | Claude: full native hooks. Codex-as-Oga: Codex hooks exist (learn.chatgpt.com/docs/hooks) but our gates have 2 HIGH blind spots + Fernet gap (§1.4) | expensive |
| Plan-check verifier | Agent-tool sub-agent (current, credited by `spec_bound_verifier_credit.py`) | (a) OpenAI API judge via `openai_llm` (exists); (b) `codex exec --sandbox read-only --output-schema` (needs runner) | Agent tool / direct API / subprocess | Claude: verdict-line contract; API: strict json_schema; codex exec: `--output-schema` | Agent tool: YES (PreToolUse + SubagentStop + transcript credit). API: NO hook events — but fully code-mediated (harness sees everything). codex exec: NO hook events for us; JSONL stdout + hash-bound output file instead; hooks-under-exec UNVERIFIED | cheap-mid |
| Post-build verifier | Agent-tool sub-agent (current) | same two options; codex exec read-only can run tests only if workspace-write → prefer read-only + our harness runs tests | same | same | same | mid-expensive |
| Test-writer | Agent-tool sub-agent (current) | `codex exec --sandbox workspace-write` in isolated clone (pilot pattern) | Agent tool / subprocess | n/a | Agent: yes. codex exec: adapter containment instead of hooks | mid |
| Implementer (Coder) | Agent-tool Coder (current; OGA-GUARD enforced) | `codex exec workspace-write` in sealed clone (built: `codex_exec_adapter.py`) | Agent tool / subprocess | n/a | Agent: yes. codex exec: Seatbelt + argv allowlist + protected roots (stronger than hook observation, weaker on mid-run interruption) | expensive |
| Researcher | Agent-tool sub-agent (this dispatch) | OpenAI API with web-search tool (models page lists "Web search" support) or codex exec read-only | Agent tool / API / subprocess | partial | Agent: yes; others: code-mediated | mid |
| Gold-judge / second-opinion | `anthropic_llm` (Haiku) | `openai_llm` (exists TODAY); panel per PoLL | direct API | strict schema available (not yet wired) | code-mediated (no hooks needed) | cheap |

---

## 4. Pairing architectures, ranked

### Rank 1 — Architecture C (minimal): OpenAI API as a second judge only — no CLI runtime

**Shape:** keep every role Claude-native and credited exactly as today. Add an OpenAI-family second opinion at the two judgment chokepoints: (1) plan-check — after the Claude plan-check Verifier rules, run the same spec + lens prompt through `openai_llm("gpt-5.6-terra")`; (2) post-build — same for the verify handoff. Disagreement does not flip a verdict; it forces one extra Claude round with the OpenAI reasoning pasted in (the `disagreement_harness.py` philosophy: "the harness deliberately does NOT pick a winner").
**Exists already:** `openai_llm` (llm.py:148), routing (dispatch.py:107), disagreement miner (evals/disagreement_harness.py), key file (`~/.config/openai/key`), SDK 2.41.1. **Build:** a thin second-opinion wrapper + disagreement log; optionally upgrade `openai_llm` to strict-schema Responses output.
**Gate/hook mechanics:** nothing breaks. API calls emit no PreToolUse events, so the credit gate neither sees nor credits them — fine, because the Claude Verifier remains the credited gate-of-record; the OpenAI opinion is advisory input to Oga.
**Biggest risk:** *soft-compliance decay* — an advisory, uncredited signal gets skimmed then ignored (exact precedent: memory `feedback_dispatch_check_json_not_rendered`, `feedback_oga_role_collapse`). Mitigation: write each disagreement to the run dir and make the extra round mechanically required when verdicts differ (a checkable artifact, not a norm).
**Why rank 1:** it is the cheapest falsifiable test of the decorrelation hypothesis (PoLL + self-preference evidence says expect signal), runnable this week, zero blast radius.

### Rank 2 — Architecture A (the hypothesis-bearer): OpenAI as the decorrelated plan-check + post-build reviewer; Claude keeps implementer + test-writer

**Shape:** the reviewer seats move to the OpenAI family. Two sub-variants: **A-api** — reviewer = OpenAI API call with strict-schema verdict JSON (findings[], verdict, cited spec lines) — simpler and hook-irrelevant; **A-cli** — reviewer = `codex exec --sandbox read-only --output-schema verdict.json -o last_msg.txt` in a `codex_role_runner.py` mirroring `claude_role_runner.py`'s verdict-line validation (CODEX_CLAUDE_TEAM.md:32-54 is the template in the other direction). A-cli buys the Codex harness (repo-map, AGENTS.md, tools) at subscription cost; A-api buys simplicity at token cost.
**What breaks / must be built:**
- **Credit gate:** `spec_bound_verifier_credit.py` credits Verifier work from Claude-transcript dispatch/result pairs with `REVIEWED_SPEC_SHA256=` markers. A subprocess/API reviewer produces neither an Agent-tool PreToolUse event nor transcript records — under current code the subsequent Coder dispatch would be DENIED for lack of prior verifier credit. Needs a new *artifact-credit path*: accept a hash-bound verdict file (spec sha256 quoted inside the schema-enforced JSON, file sha256 recorded) as credit. This is adjacent to — and should be designed together with — the open `H-CODEX-CLAUDE-ONLY-CREDIT-PARSER-BLIND-1` class sweep (fix_plan.md:10363-10368).
- **Version/schema:** either keep pinned 0.41.0 (known argv grammar, `session.*` JSONL, already Seatbelt-probed) or upgrade to 0.144.x and port `_parse_jsonl` (+ re-validate argv; `--ask-for-approval` presence in current grammar UNVERIFIED) and re-run the preflight matrix. Do not straddle.
- **Hygiene/adjacency gates:** these scan Claude transcripts; an external reviewer bypasses them. Equivalent checks must run in the runner (e.g. refuse to pass the reviewer a status-doc-bearing run dir — H-LT4 discipline enforced in code, which is *stronger* than the current instructional form).
- **Citation-genuineness:** memory `feedback_verifier_credit_citation_requirement` / `feedback_verifier_citation_fabrication` apply to ANY family: require the schema to include verbatim quoted spec lines + `REVIEWED_SPEC_SHA256`, verified mechanically by the runner against the real file.
**Biggest risk:** **enforcement-parity regression** — we would be moving the most safety-critical seat (the gate) from the runtime where our observation/credit machinery is strongest to one where it must be rebuilt; a bug in the new artifact-credit path is a silent false-PASS channel. Mitigation: for the first N runs, dual-gate (Claude Verifier remains the credited gate; OpenAI reviewer must ALSO pass) and only consider promoting the OpenAI seat after the in-house A/B shows it catches defects the Claude gate misses (measured on D1 fault-injection gold repairs).

### Rank 3 — Architecture B (maximal): dual-implementer A/B — one Claude, one OpenAI — with cross-review of each other's diffs

**Shape:** already designed in miniature by the pilots: `codex_product_pilot.md` (incumbent `gpt-5.6-terra` vs challenger `gpt-5.6-luna` coders in sealed clones) + the spec-only `claude_product_pilot.md` sibling. Generalized: same brief to a Claude Coder (worktree 1) and a `codex exec workspace-write` Coder (sealed clone 2); each family reviews the other's diff; Oga integrates the winner or a merge.
**What breaks / must be built:** everything in A, plus worktree/branch reconciliation at scale (memory `feedback_one_session_per_worktree`, `feedback_isolated_worktree_deployment_gap`), double compute per feature, and OGA-GUARD/identity markers cover only the Claude side (the Codex side substitutes adapter containment). The pilot's own governance history demands re-verification before reuse (§1.2 fabricated-claim caveat).
**Biggest risk:** **cost/complexity swamps the gain** — reconciliation of two independent implementations is the exact class of merge-fight the repo's history warns about; per the prior-art, most of the decorrelation benefit is available much cheaper at the *review* seat (A) or *judge* seat (C).
**When justified:** for a high-stakes, well-specified component where two independent implementations double as mutual oracles (N-version programming), or to generate hard disagreement cases for the eval suite.

**Ranking rationale:** C → A → B is ascending integration cost and ascending risk to gate integrity, with the marginal decorrelation benefit per dollar falling after the review seat is diversified. C also produces the measurement (disagreement + caught-defect deltas) that would justify or kill A and B — accuracy-over-speed, per standing practice.

---

## 5. Transfer-condition check (required for each borrowed pattern)

| Pattern | Execution context required | Satisfied here? | Guarantee type | Silent-failure flag |
|---|---|---|---|---|
| PoLL panel-of-families judging | code-controlled dispatch of ≥2 judges + verdict aggregation | YES — `dispatch.py`/`llm.py`/`disagreement_harness.py` | Structural (harness makes both calls) | Low — a missing judge raises, doesn't silently pass |
| Cross-family reviewer via `codex exec` | subprocess control, hash-bound artifacts, version-pinned binary | Partially — adapter exists but pinned to stale 0.41.0; credit path missing | Containment structural (Seatbelt/argv); *review honesty instructional* (model must genuinely read the spec) | **FLAGGED**: an un-read spec still yields a schema-valid verdict → passes downstream checks. Mitigate: schema-required verbatim spec quotes + sha256, runner-verified |
| Codex hooks for peer-session observation | hooks fire in that runtime + trust-hash intact + our parsers Codex-aware | NO — hooks-under-exec UNVERIFIED; 2 HIGH parser blind spots + Fernet gap open | Instructional + fragile state (trust hash) | **FLAGGED**: trust-hash invalidation silently disables enforcement (already happened once, fix_plan.md:4148-4185) |
| Advisory second opinion (C) | orchestrator actually reads/acts on disagreements | Yes mechanically, but compliance is behavioral | Instructional unless disagreement-blocks are made mechanical | **FLAGGED**: soft-compliance decay precedent (`dispatch_check`, oga-role-collapse) — make the extra round artifact-gated |

---

## 6. Explicitly UNVERIFIED / not found this pass

- Whether Codex **hooks fire under `codex exec`** (headless). Official docs silent; PORTABILITY.md:56 already flags it. 10-minute empirical test defined there.
- Whether **`--ask-for-approval` still exists / where it sits in 0.144.x argv grammar** (validated only against installed 0.41.0 by the argv-fix specs).
- **gpt-5.3-codex training-mix detail** ("trained on … code review") — from a search summary of the system-card PDF; the PDF itself was not page-read.
- **MindStudio "40-60% higher detection" and "28% finding-overlap"** figures — vendor blog, no methodology shown. Cited only as the weak tier of evidence.
- **Codex product backbone = GPT-5.5+ since May 2026** — third-party tracker (codex.danielvaughan.com), not confirmed on an OpenAI page I opened.
- **Claude-side API pricing** — not re-verified this pass (Claude seats here are subscription-metered via Agent tool, so it was not load-bearing).
- `~/.codex/auth.json` **contents/mode** (ChatGPT vs API key) — deliberately not read; presence only.

## 7. Recommended next actions (for Oga/Nnamdi — not self-executed)

1. **Run Architecture C this week** as a PACE-shaped A/B: metric = caught-hole rate on the D1 fault-injection gold set (and/or plan-check-found-real-gap rate), baseline = Claude-only gate, variant = Claude gate + `gpt-5.6-terra` second opinion with mechanical disagreement-round. Kill criterion: after the full case set, zero defects caught by the OpenAI seat that the Claude seat missed.
2. **Reconcile the two argv-fix specs** (`2026-07-16_codex-exec-approval-flag-fix` vs `2026-07-17_codex-exec-argv-order-fix`) and land one, before any real `codex exec` reviewer work.
3. **Decide the binary strategy** (stay pinned 0.41.0 vs upgrade to 0.144.x + port `_parse_jsonl`/argv + re-preflight) as a prerequisite for Architecture A-cli; A-api needs no binary at all.
4. **Fold the artifact-credit path** for non-Agent reviewers into the already-mandated `H-CODEX-CLAUDE-ONLY-*` class sweep so credit logic is designed once for all non-Claude event sources.

## 8. Source index (all opened this session unless tagged)

- https://github.com/openai/codex — repo page: release 0.144.5 (2026-07-16); ChatGPT-plan-vs-API-key auth quote.
- https://learn.chatgpt.com/docs/non-interactive-mode (via developers.openai.com/codex/noninteractive) — `codex exec` flags, JSONL event types, `--output-schema`, `CODEX_API_KEY`, resume.
- https://learn.chatgpt.com/docs/hooks (via developers.openai.com/codex/hooks) — hook events, config, stdin contract, trust flow, `--dangerously-bypass-hook-trust`.
- https://developers.openai.com/api/docs/models — gpt-5.6-sol/terra/luna, 1.05M ctx, positioning quotes.
- https://developers.openai.com/api/docs/pricing — per-1M prices for sol/terra/luna/gpt-5.3-codex/gpt-5.4-mini/nano.
- https://developers.openai.com/api/docs/guides/structured-outputs + https://openai.com/index/introducing-structured-outputs-in-the-api/ — strict json_schema mode (guide located via search; strict-mode semantics corroborated by the announcement post).
- https://developers.openai.com/codex/mcp — Codex MCP client config (located via search; corroborated by https://agentpatch.ai/blog/codex-cli-mcp-setup/, secondary).
- https://arxiv.org/abs/2404.18796 — PoLL (panel of disjoint-family judges > single large judge; >7x cheaper).
- https://arxiv.org/abs/2404.13076 — self-preference bias linear in self-recognition (Panickssery et al.).
- https://arxiv.org/abs/2606.19826 — heterogeneous debate: 89%→35% harmful-revision, 31%→6% adversarial flip-rate.
- https://github.com/formin/multi-model-review — build-with-one/review-with-another tool (7 stars, v0.1.2 2026-06-18, MIT).
- Secondary/flagged: https://www.mindstudio.ai/blog/cross-vendor-ai-agent-review-claude-codex; https://codex.danielvaughan.com/… (model routing, /review pre-commit); https://cdn.openai.com/pdf/23eca107-a9b1-4d2c-b156-7deb4fbc697c/GPT-5-3-Codex-System-Card-02.pdf (not page-read).
- Repo files cited throughout §1 with line numbers; fix_plan.md entries at lines 4133, 7314, 7847, 10032, 10222, 10313, 10340, 10370, 10395, 10409.
