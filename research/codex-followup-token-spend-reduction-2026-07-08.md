# Token-spend-reduction stack — independent verification of a Codex CLI follow-up

**Date:** 2026-07-08 · **Mode:** A (loop-improvement radar) · **Researcher pass:** direct WebFetch/WebSearch/GitHub-API verification of every claim, no sub-agents dispatched.

**Task:** a separate Codex CLI diagnostic session recommended a "token-spend-reduction stack" for
`~/Claude/loop` (this loop-team framework). Every specific repo/paper claim below was independently
opened and quoted — nothing here is restated from Codex's summary without a fresh fetch. Method:
`WebFetch` for docs/READMEs/arXiv abstracts, `curl` against the raw GitHub REST API for maturity
signals (stars/license/archived flag/`pushed_at`/commit dates/release dates — more reliable than
WebFetch's markdown scraping of a live GitHub page, which the Researcher role brief itself flags as
prone to fabricating specifics), and direct `npm pack` of the current `@anthropic-ai/claude-code`
package to attempt source verification of one finding.

**Headline result:** the single most load-bearing, directly-actionable finding is not on Codex's
list at all — it surfaced while verifying "provider prompt-prefix caching" against Anthropic's own
docs. See **Finding 0** below before the per-item verification table; it changes the priority
ordering of everything else.

---

## Finding 0 (not in Codex's list, surfaced during verification): Agent-SDK subagent prompt-caching may be broken for exactly this framework's dispatch pattern

This loop-team's entire architecture is built on `Agent` tool dispatches to custom subagent types
(`roles/coder.md`, `roles/verifier.md`, etc. via `.claude/agents/<name>.md` frontmatter,
per `orchestrator.md` "How roles are dispatched"). That is **exactly** the code path a real, open,
unresolved GitHub issue says is losing prompt-cache benefit.

- **Official doc, opened and quoted:** [code.claude.com/docs/en/prompt-caching](https://code.claude.com/docs/en/prompt-caching)
  → "Subagents and the cache": *"A subagent starts its own conversation with its own system prompt
  and tool set, separate from the parent's. It builds its own cache, starting with no cache hits on
  its first call and warming up across its own turns. Subagents use the five-minute TTL even on a
  subscription."* This describes the *intended* behavior.
- **Open GitHub issue, fetched via GitHub API (not WebFetch) for the exact text:**
  [anthropics/claude-code#29966](https://github.com/anthropics/claude-code/issues/29966) —
  "Agent SDK subagents have prompt caching disabled by default (enablePromptCaching: false)."
  State: **open**. Created 2026-03-02, last activity 2026-05-25. Labels: `bug`, `has repro`,
  `area:cost`, `area:agent-sdk`. Quoted verbatim from the issue body: *"Subagent requests spawned
  via the Agent tool have `enablePromptCaching` hardcoded to `false`, causing all subagent API
  calls to miss prompt caching entirely."* Reporter's real proxy-log evidence: *"54 subagent
  requests × 7,013 uncached tokens each = ~378,000 wasted uncached input tokens per session."*
- **Anthropic engineer's reply (2026-04-05, quoted from the thread):** disputes the reporter's
  specific *code-path* diagnosis ("the code path you identified isn't the one subagents use... The
  subagent path does enable caching by default") but does **not** dispute the symptom, and asks for
  more detail — *"zero `cache_control` markers across 54 requests is worth understanding... One
  possibility is that cache markers depend on the shape of the system prompt, so a custom subagent
  system prompt may not get them even when caching is on."* This loop-team's subagents are
  precisely "custom subagent system prompt" cases (5 distinct `.claude/agents/*.md` role types).
- **Independent second reporter (2026-04-06, quoted):** confirmed with side-by-side proxy logs —
  main-CLI requests show pre-existing cache breakpoints and reads; Agent-SDK subagent requests show
  `pre=0` (zero `cache_control` markers) even for non-custom subagents; manually injecting the
  breakpoints via a reverse proxy fixed it, "proving the API supports it, the SDK just isn't
  sending them." Built a public workaround proxy:
  [KevinZhao/claudecode-bedrock-proxy](https://github.com/KevinZhao/claudecode-bedrock-proxy).
- **Adjacent, independently useful comment on the same issue (nicolasnoble, 2026-04-19, quoted):**
  *"Today subagents inherit the full user-scope CLAUDE.md from `~/.claude/` plus any project
  CLAUDE.md in cwd. With substantial user-scope customization, that's easily 10-20k tokens of
  preamble per spawn, most of which a typical research or edit subagent doesn't need."* This
  directly describes this project's own setup: `~/.claude/CLAUDE.md` (with the full MEMORY.md
  digest) plus `~/Claude/CLAUDE.md` are both large and are re-sent, unabbreviated, on **every
  single Coder/Verifier/Test-writer/Researcher dispatch** in every loop-team run.
- **Confirmed, real, currently-shipped mitigation** (opened the actual page, not a search
  snippet): [code.claude.com/docs/en/agent-sdk/modifying-system-prompts §"Improve prompt caching
  across users and machines"](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts) —
  quoted verbatim: *"By default, two sessions that use the same `claude_code` preset and `append`
  text still cannot share a prompt cache entry if they run from different working directories...
  set `excludeDynamicSections: true` in TypeScript or `"exclude_dynamic_sections": True` in
  Python."* Requires `@anthropic-ai/claude-agent-sdk` v0.2.98+ (TS) or `claude-agent-sdk` v0.1.58+
  (Python) — confirmed via `npm view`/registry query that the **currently published** SDK version
  is `0.3.204`, well past that floor, so the flag is available today if loop-team's Oga process
  invokes the Agent SDK directly.
- **What I could NOT verify:** whether the bug still reproduces on the *current* Claude Code
  release. The bug report cites CLI v2.1.63 / Agent SDK v0.2.63; `npm view` shows the current
  published versions are CLI `2.1.204` / SDK `0.3.204` — many releases later. I attempted a direct
  source check (`npm pack @anthropic-ai/claude-code@2.1.204`, unpacked, inspected contents) to
  grep for the `enablePromptCaching` literal the way the original reporter did; the current
  package **no longer ships an inspectable `cli.js`** — it downloads a platform-specific compiled
  binary at `postinstall` (`optionalDependencies` per-OS/arch packages, `bin/claude.exe` is a stub
  launcher). I could not grep a compiled binary for this string within reasonable scope, so this
  is an **honest gap**, not a confirmed-fixed or confirmed-still-broken state. The GitHub issue
  itself is still open with no maintainer "fixed in vX" comment as of its last activity
  (2026-05-25).
- **Why this matters more than anything else on Codex's list:** it's the actual runtime substrate
  this exact framework already runs on (not a third-party library to newly adopt), the cost
  mechanism is real numbers from real production proxy logs corroborated by two independent
  parties, and — critically — **it is cheap to check directly**: the docs state
  `cache_read_input_tokens`/`cache_creation_input_tokens` are already returned on every API
  response and visible via a statusline script or the OTel exporter
  (`code.claude.com/docs/en/monitoring-usage`). Zero new infrastructure needed to find out whether
  this loop-team's own Coder/Verifier dispatches are actually getting cache reads.

**Recommended falsifiable check (ready to run, no adoption decision needed yet):** during the next
loop-team run, capture `cache_creation_input_tokens` vs `cache_read_input_tokens` on 2+ consecutive
same-type subagent dispatches (e.g. two Coder dispatches within the same micro-step loop, a few
minutes apart) via the OTel usage export or a debug proxy. If `cache_read_input_tokens` stays near
zero across dispatches that share an identical role-brief system prompt, the bug reproduces here
and now; if reads climb on the 2nd+ dispatch, the Anthropic engineer's rebuttal holds for this
setup and the issue doesn't apply. Either result is informative and costs nothing to gather.

---

## 1. Provider prompt-prefix caching (Anthropic + OpenAI official docs)

**Confirmed real and current** — both docs opened directly (with redirect-follow, both moved to new
hosts in 2026: Anthropic's docs moved from `docs.anthropic.com` → `platform.claude.com`; OpenAI's
moved from `platform.openai.com` → `developers.openai.com`).

**Anthropic** ([platform.claude.com/docs/en/docs/build-with-claude/prompt-caching](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching)):
- Mechanism: exact-prefix match against a recent cache entry up to a `cache_control` breakpoint.
- Minimum cacheable prefix varies by model: 512 tokens (Fable 5 / Mythos 5 family; 1,024 on
  Bedrock), 1,024 tokens (Opus 4/4.1/4.5/4.6, Sonnet 4.5/4.6/5), 2,048 tokens (Mythos Preview,
  Opus 4.7), 4,096 tokens (Haiku 4.5).
- TTL: 5-minute default (free refresh on hit) or 1-hour extended (written at 2× base input price).
- Cost multipliers: 5-min cache write 1.25×, 1-hour cache write 2×, cache read 0.1× of base input
  price. Up to 4 explicit breakpoints, or fully automatic mode.
- Recent change confirmed in the doc: as of 2026-02-05, cache isolation moved from
  organization-level to **workspace-level** on the Claude API / Claude Platform on AWS / Microsoft
  Foundry (Bedrock and Google Cloud still isolate at org level) — relevant if this project ever
  runs multiple workspaces sharing role-brief prefixes.

**OpenAI** ([developers.openai.com/api/docs/guides/prompt-caching](https://developers.openai.com/api/docs/guides/prompt-caching)):
- Fully automatic for prompts ≥1,024 tokens, no code change, no extra fee.
- Retention: 5–10 min inactivity / up to 1 hour on older models; up to **24 hours** on newer models
  (GPT-5.5, GPT-5.5-pro).
- Discount: "reduce latency by up to 80% and input token costs by up to 90%" on cached tokens.

**Status:** both are mature, industry-standard, ADOPTED-by-the-industry provider features — not
something to "adopt" as a new tool, they're already running under the hood for any direct API call.
**What Codex's framing likely missed** (confirmed by Finding 0 above): whether this specific
framework's *sub-agent dispatch pattern* structurally receives that benefit is an open, actively
disputed question on Anthropic's own issue tracker — the provider feature being real does not mean
this framework is currently benefiting from it on every dispatch. Treat "provider caching exists"
and "loop-team's dispatches are cached" as two separate claims; only the first is settled.

---

## 2. `microsoft/LLMLingua` (+ LLMLingua-2, LongLLMLingua)

**Confirmed real**, opened directly at [github.com/microsoft/LLMLingua](https://github.com/microsoft/LLMLingua)
and cross-checked against the GitHub REST API (not just WebFetch scraping):

```
stars: 6,419 · archived: false · license: MIT
last commit (API): 2025-10-28  (adds "SecurityLingua" — a jailbreak-detection guardrail, not core compression)
last tagged release: v0.2.2, 2024-04-09  (over 2 years old as of 2026-07-08)
```

README, quoted: *"compress the prompt and KV-Cache, which achieves up to 20x compression with
minimal performance loss."* Three real, peer-reviewed variants bundled in one repo:
LLMLingua (EMNLP 2023), LongLLMLingua (ACL 2024, targets the "lost in the middle" problem
directly — see item 11), LLMLingua-2 (ACL 2024 Findings, GPT-4-distilled, "3×–6× speed
improvement").

**Maturity flag — genuinely worth catching, likely understated by a Codex-style summary that just
reports "6.4k stars, MIT":** the project has **not shipped a tagged release in over two years**
(last: April 2024) despite 6.4k stars and Microsoft backing; real commit activity exists but is
sparse and now oriented toward the security/guardrail spinoff, not core compression improvements.
This is a **low-but-not-abandoned** maintenance signal — not archived, not dead, but not actively
evolving the core compression method either.

**Transfer-condition check (per orchestrator.md guardrails):** LLMLingua's compression is *lossy*
and was designed/evaluated for natural-language QA/summarization prompts where dropping
"non-essential" tokens preserves meaning approximately. This framework's dispatch content is
mostly **exact, load-bearing text** — acceptance criteria, diffs, decision logs, spec text — where
losing the wrong token silently changes correctness with no error raised (an unbounded/instructional
failure mode, exactly the kind orchestrator.md's transfer-condition rule calls out as dangerous:
"a compliance failure would be silent and load-bearing"). No benchmark evidence exists for LLMLingua
on agentic coding/tool-use prompts specifically — all published numbers are QA/reasoning benchmarks.
Narrow, non-default use (e.g., compressing an incidental long log dump handed to a Researcher, never
a spec/AC/diff handed to a Coder or Verifier) is the only defensible scope.

---

## 3. `zilliztech/GPTCache`

**Confirmed real**, opened at [github.com/zilliztech/GPTCache](https://github.com/zilliztech/GPTCache),
cross-checked via GitHub API:

```
stars: 8,091 · archived: false · license: MIT
last commit (API): 2025-07-11  (~1 year stale as of 2026-07-08)
last tagged release: 0.1.44, 2024-08-01
```

Commit history shows a real gap: Aug 2024 → Sep 2024 (one commit) → **nothing until July 2025**
(11-month silence), then two commits in July 2025 and nothing since. README, quoted: *"Semantic
cache for LLMs. Fully integrated with LangChain and llama_index"* — *"Slash Your LLM API Costs by
10x, Boost Speed by 100x."*

**Decay flag:** this is a materially staler project than a "8k-star, actively-integrated" framing
would suggest — nearly a year with zero commits, no release in ~2 years. Worth flagging as
**DECAYING-leaning**, not a confidently-adoptable CANDIDATE.

**Transfer-condition check:** GPTCache's mechanism (embed the query, return a cached response if
cosine similarity clears a threshold) is built for chat-service workloads with genuinely repeated,
similarly-phrased user queries (FAQ bots, support chat). This framework's Coder/Verifier/Researcher
dispatches each handle a **different** spec/task/code context per call — there is little repeated
query structure to exploit. Worse: applying a similarity-threshold response cache to a **Verifier**
or **Coder** role risks returning a stale, wrong verdict/diff for a "semantically similar but
actually different" spec — a silent, load-bearing correctness failure that directly contradicts
this project's own hard-won Verifier-independence and no-priming discipline. Not recommended for
either role; no other role in the current roster has the repeated-query shape this tool targets.

---

## 4. "SCALM" semantic-cache paper

**Confirmed real**, arXiv abstract opened directly: [arxiv.org/abs/2406.00025](https://arxiv.org/abs/2406.00025)
— "SCALM: Towards Semantic Caching for Automated Chat Services with Large Language Models," Jiaxing
Li et al., submitted 2024-05-24. Abstract confirms the reported numbers: *"a relative increase of
63% in cache hit ratio and a relative improvement of 77% in tokens savings"* — explicitly measured
**against GPTCache as the baseline it's compared to**, not built on top of / integrated into
GPTCache. **Correcting a plausible Codex-style conflation:** SCALM is an independent research
proposal that *outperforms GPTCache in the paper's own benchmark*; it is not a feature of GPTCache
and does not ship inside it.

**No public code repository found** — searched directly (`SCALM ... github`) and via the paper's
own aggregator pages; no GitHub link surfaced anywhere, including the authors' own pages. This is
**paper-only**: per the researcher role's honesty bar, confidence is capped ≤0.3 regardless of the
reported numbers. Same domain mismatch as GPTCache (chat-service caching, not agentic dispatch) —
RESEARCH_ONLY, parked.

---

## 5. FrugalGPT paper (+ `stanford-futuredata/FrugalGPT` repo)

**Confirmed real and peer-reviewed** — arXiv abstract opened: [arxiv.org/abs/2305.05176](https://arxiv.org/abs/2305.05176),
Chen/Zaharia/Zou, Stanford, submitted 2023-05-09. **Confirmed via a follow-up search (not assumed):**
published in **Transactions on Machine Learning Research (TMLR), December 2024** — a real,
peer-reviewed outcome, not just an arXiv preprint (dblp record: `journals/tmlr/ChenZ024`). Core
mechanism, quoted from the abstract's framing: three levers — prompt adaptation (shorter effective
prompts), LLM approximation (cheaper models fine-tuned/distilled to match an expensive one on a
task), and **LLM cascade** (route each query to the cheapest model likely to answer it correctly,
escalating only on low confidence). Reported result: up to 98% cost reduction matching the best
individual LLM's accuracy, or +4% accuracy at equal cost.

Repo checked via GitHub API: [stanford-futuredata/FrugalGPT](https://github.com/stanford-futuredata/FrugalGPT) —
```
stars: 268 · archived: false · license: Apache-2.0
last commit (API): 2025-02-10  (~17 months stale as of 2026-07-08; small, low-activity companion repo)
```

**Transfer-condition check — this is the one candidate on Codex's list with a genuinely direct
structural match to this framework:** `orchestrator.md`'s own "Model routing" table already does
*static* cascading by role (`haiku`/`sonnet`/`opus`), and the stall-detector/retry-cap machinery
already effectively escalates on failure signal (Researcher Mode B / human escalation after N
repeated failure signatures). FrugalGPT's cascade generalizes this into an *adaptive*, confidence-
triggered escalation rather than a fixed per-role tier — e.g., a first Coder attempt on a cheaper
tier, escalating to the current default only when a low-confidence/failure signal fires. No
coding-agent-specific FrugalGPT benchmark exists (all reported numbers are classification/QA/
reading-comprehension tasks), so the specific % is not portable — but the *cascade pattern* is a
legitimate generalization of a mechanism this framework already partially implements.

---

## 6. LiteLLM gateway (`BerriAI/litellm`)

**Confirmed real and very actively maintained** — GitHub API:
```
stars: 52,922 · archived: false · license: MIT for core (see caveat) · open_issues: 3,720
last push (API): 2026-07-08  (same day as this research — pushed hours before this check)
latest releases: v1.93.0-dev.1 (2026-07-08), v1.91.0 (2026-07-04)  — active near-daily release cadence
```
README, quoted: *"LiteLLM is an open source AI Gateway that gives you a single, unified interface to
call 100+ LLM providers — OpenAI, Anthropic, Gemini, Bedrock, Azure, and more — using the OpenAI
format."* License nuance confirmed by reading the actual `LICENSE` file at the repo root, quoted:
*"All content that resides under the 'enterprise/' directory of this repository, if that directory
exists, is licensed under the license defined in 'enterprise/LICENSE'... Content outside of the
above mentioned directories... is available under the MIT license."* — mostly MIT, but the
`enterprise/` subtree is not; flag before assuming pure-MIT.

**Caching support confirmed via the actual caching docs** (not just the README, which
under-reports this): [docs.litellm.ai/docs/proxy/caching](https://docs.litellm.ai/docs/proxy/caching) —
supports in-memory, disk, Redis (exact-match, default), **and semantic caching backends**: Qdrant,
Redis, and Valkey semantic cache, with a configurable `similarity_threshold`.

**Transfer-condition check — genuinely structurally supported, with a material caveat Codex's
summary likely missed:** Claude Code officially supports routing through a third-party gateway via
`ANTHROPIC_BASE_URL` — confirmed by opening [code.claude.com/docs/en/llm-gateway](https://code.claude.com/docs/en/llm-gateway)
directly: *"Any gateway that exposes a supported API format works. Anthropic doesn't endorse,
maintain, or audit third-party gateway products."* **The load-bearing caveat, quoted exactly:**
*"While a gateway credential variable... is active, a developer's claude.ai subscription isn't
used: the credential replaces the subscription login for that session, and the subscription's usage
limits don't apply. That traffic is billed per token..."* — meaning inserting LiteLLM (or Portkey)
in front of a **subscription-billed** Claude Code session switches billing from flat-rate/included
usage to metered per-token billing. For a token-*spend*-reduction goal, this can be a **net cost
regression** unless the caching/routing savings clearly outweigh the subscription-to-metered switch
— and I could not confirm which billing model this specific loop-team deployment currently uses, so
this must be checked before any gateway adoption, not assumed. Separately: LiteLLM's own semantic
cache carries the **same correctness risk flagged for GPTCache** if pointed at a Verifier or Coder
role — safest scope is Researcher-only, non-judging traffic, or pure cost-tracking/observability
(budgets, per-role token attribution) rather than response caching.

---

## 7. "semantic-router" (`aurelio-labs/semantic-router`)

**Confirmed real and actively maintained** — GitHub API:
```
stars: 3,678 · archived: false · license: MIT
last push (API): 2026-05-23 · latest release: v0.1.15, 2026-05-23
```
README, quoted: *"a superfast decision-making layer for your LLMs and agents"* — it classifies a
user query against pre-defined intent "routes" using embedding similarity **to decide which handler
to invoke, before any LLM call**, i.e. intent classification / request routing.

**Correcting a likely name-based conflation in Codex's summary:** "semantic-router" is **not** a
caching tool, and does not do semantic caching — it is a routing/classification layer, a distinct
concern from everything else on this list. **Transfer-condition check:** this framework's dispatch
decisions (which role, which mode, DESIGN vs KNOWLEDGE gap-routing, etc.) are already made by
Oga's own deterministic, spec-encoded branching logic in `orchestrator.md` — there is no freeform
natural-language "classify user intent into N buckets" bottleneck in the current architecture that
this tool would address. Real, well-maintained tool; no applicable fit found in this framework
today.

---

## 8. Portkey gateway (`Portkey-AI/gateway`)

**Confirmed real and maintained** — GitHub API:
```
stars: 12,353 · archived: false · license: MIT
last push (API): 2026-05-25 · latest release: v1.15.2, 2026-01-12
```
Recent commits (fetched directly) show real, current work: auth-validation fixes, log redaction,
admin-token hardening — genuine maintenance, not just dependency-bump noise. README, quoted: *"The
AI Gateway is designed for fast, reliable & secure routing to 1600+ language, vision, audio, and
image models"* — "Smart caching," load balancing, 45+ providers.

**Confirmed overstatement risk in the caching claim** — opened the actual caching doc, not just the
README: [portkey.ai/docs/product/ai-gateway/cache-simple-and-semantic](https://portkey.ai/docs/product/ai-gateway/cache-simple-and-semantic),
quoted exactly: *"Semantic cache works with requests under 8,191 tokens and ≤4 messages"* and,
critically, **"Semantic caching is available only on select Enterprise plans and requires a vector
database to function."** A summary that presents "Portkey does semantic caching" without this gate
is materially overstated for a personal/small-project deployment (this project is not an Enterprise
Portkey customer) — the open-source/free tier gets simple exact-match caching only. Same
subscription-vs-metered-billing caveat as LiteLLM applies if routed in front of a Claude Code
session (see item 6). Same Verifier/Coder correctness-risk caveat applies to any response-caching
use.

---

## 9. RECOMP paper (+ `carriex/recomp` repo)

**Confirmed real, peer-reviewed** — arXiv abstract opened: [arxiv.org/abs/2310.04408](https://arxiv.org/abs/2310.04408),
Xu/Shi/Choi, submitted 2023-10-06, published at **ICLR 2024**. Quoted from the abstract: *"documents
... often spanning hundreds of words, make inference substantially more expensive"* — proposes an
extractive compressor (selects useful sentences) and an abstractive compressor (multi-document
summary), both trainable to emit an **empty string** for irrelevant documents (selective
augmentation). Compression rate as low as 6% with minimal task-performance loss reported.

Repo checked via GitHub API: [carriex/recomp](https://github.com/carriex/recomp) —
```
stars: 149 · archived: false · license: MIT
last commit (API): 2026-01-06  ("Change download links for training data" — light maintenance, not dead)
```

**Transfer-condition check — a direct conflict with this project's own documented lesson, worth
flagging explicitly:** RECOMP-style compression targets retrieval-augmented QA, where retrieved
documents are often irrelevant/redundant. Applying an analogous "summarize before handing to the
model" step to this framework's Coder-retry-history or Verifier-evidence content would directly
contradict `orchestrator.md`'s own explicit, evidence-based rule: *"Hand a retry Coder the FULL
prior-attempt history, not just the latest failure"* and the standing guardrail *"Read everything,
no lazy reading or skipping... A conclusion whose evidence you did not read is not verified."* Both
rules exist because this project already had real incidents where summarization/sampling caused
missed gaps. RECOMP is legitimate for its intended domain; it is a poor and specifically
**contraindicated** fit for this framework's core dispatch content.

---

## 10. AttentionRAG paper

**Confirmed real** — arXiv abstract opened: [arxiv.org/abs/2503.10720](https://arxiv.org/abs/2503.10720),
Fang/Sun/Shi/Gu, v1 2025-03-13, v2 2025-10-27. Quoted from the abstract: reformulates a RAG query
into a next-token-prediction framing to isolate "the query's semantic focus to a single token,"
reporting *"up to 6.3× context compression while outperforming LLMLingua methods by about 10% in
key metrics"* on LongBench and Babilong.

**Could not confirm peer-reviewed acceptance status.** There is a matching OpenReview submission
page, but I could not load its review/decision page past a bot-check wall to confirm accept/reject
— treat as an arXiv preprint with an unconfirmed venue outcome, not a confirmed-accepted paper.

**No public code repository found** — searched directly for the authors' names + "github" +
"AttentionRAG"; nothing surfaced beyond the paper page and aggregator sites. **Paper-only: capped
confidence ≤0.3.** The "outperforms LLMLingua by ~10%" figure is the authors' own self-reported
comparison, not an independently reproduced result. Same domain mismatch as items 2/9 (long-context
QA, not agentic coding) — RESEARCH_ONLY, parked, lowest-priority item on this list given no code and
unconfirmed venue.

---

## 11. "Lost in the Middle" (Liu et al.)

**Confirmed real and foundational** — arXiv abstract opened: [arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172),
Liu/Lin/Hewitt/Paranjape/Bevilacqua/Petroni/Liang, v1 2023-07-06, v3 2023-11-20, published in
**Transactions of the Association for Computational Linguistics (TACL) 2023** — genuinely
peer-reviewed, widely cited. Abstract quoted in full: *"...performance is often highest when
relevant information occurs at the beginning or end of the input context, and significantly
degrades when models must access relevant information in the middle of long contexts, even for
explicitly long-context models."*

**This is not a tool to adopt — it's an empirical finding that should inform how existing prompts
are structured**, not something with a repo or a triage verdict in the usual sense. Directly
relevant to this framework in two ways: (1) it is the literal motivation cited by LongLLMLingua
(item 2) for why it exists; (2) it's a legitimate reason to audit whether this project's own
longest, highest-stakes documents (`orchestrator.md` itself, at 600+ lines; large `spec.md` files
after 2+ plan-check revision rounds) ever bury a load-bearing constraint in the middle of a long
prose block rather than at the start or a clearly-headed section. Note: `code.claude.com`'s own
prompt-caching design (content ordered "rarely-changes-first" — system prompt, then project
context, then conversation) is motivated by *caching efficiency*, not this paper's *correctness*
concern — the two are different reasons pointing at a similar practice, worth stating explicitly
since it would be easy to conflate them.

---

## Priority scoring (per `orchestrator.md` → "Prioritizing radar candidates")

Formula used exactly as specified: `priority = 0.40·(effect×confidence) + 0.20·phase_fit +
0.15·risk_reduction + 0.10·uncertainty − 0.15·cost_to_test`. Per the section's own honesty-bar rule,
every paper-only/no-code candidate is capped at **confidence ≤ 0.3**. `effect` throughout is
adapted to this task's actual ask — predicted % reduction in token spend / cost-per-run — since
that is the measured number Codex's "token-spend-reduction" framing is about, rather than the
framework's more usual caught-hole/false-pass metric; this adaptation is stated explicitly per the
role's honesty-bar discipline, not silently substituted.

| Candidate | effect | confidence | phase_fit | risk_reduction | uncertainty | cost_to_test | **priority** |
|---|---|---|---|---|---|---|---|
| **Agent-SDK subagent caching gap (Finding 0)** | 0.65 | 0.55 | 1.00 | 0.50 | 0.70 | 0.05 | **0.48** |
| FrugalGPT cascade pattern (routing generalization) | 0.50 | 0.45 | 0.60 | 0.20 | 0.50 | 0.20 | **0.26** |
| "Lost in the Middle" — audit long prompts for buried constraints | 0.25 | 0.75 | 0.40 | 0.15 | 0.15 | 0.05 | **0.185** |
| LLMLingua (narrow scope: incidental logs only) | 0.30 | 0.30 | 0.50 | 0.10 | 0.60 | 0.35 | **0.16** |
| LiteLLM gateway (cost-visibility framing, not caching) | 0.30 | 0.55 | 0.40 | 0.10 | 0.30 | 0.45 | **0.12** |
| Portkey gateway | 0.25 | 0.50 | 0.35 | 0.05 | 0.25 | 0.45 | **0.085** |
| RECOMP | 0.20 | 0.40 | 0.30 | 0.00 | 0.30 | 0.35 | **0.07** |
| GPTCache | 0.15 | 0.30 | 0.20 | 0.00 | 0.30 | 0.30 | **0.04** |
| semantic-router | 0.10 | 0.50 | 0.15 | 0.00 | 0.20 | 0.30 | **0.025** |
| AttentionRAG (paper-only, no code) | 0.20 | 0.25 | 0.25 | 0.00 | 0.30 | 0.50 | **0.025** |
| SCALM (paper-only, no code) | 0.15 | 0.20 | 0.20 | 0.00 | 0.30 | 0.50 | **0.007** |

Provider caching itself (Anthropic/OpenAI, item 1) is not scored as a candidate row — it is an
already-ADOPTED platform baseline, not a decision this project can accept/reject; Finding 0 is the
scoreable, actionable derivative of it.

**Reading the ranking honestly:** the RAG-context-compression family (LLMLingua, RECOMP,
AttentionRAG, SCALM) clusters at the bottom not because the papers are fake or badly done — all
four are real, and two are genuinely peer-reviewed — but because their evidence base is long-context
*QA/retrieval* benchmarks, a different task distribution than this framework's agentic
coding/verification dispatches, and two of them (RECOMP, LLMLingua/LongLLMLingua's lossy dropping)
sit in direct tension with this project's own documented "read everything in full, hand over the
complete history" lessons. The caching-adjacent gateways (GPTCache, LiteLLM, Portkey) are real and
some are very actively maintained, but their most-touted feature (semantic response caching) is
either enterprise-gated (Portkey), correctness-risky for a Verifier/Coder role (all three), or
requires a billing-model check this research could not resolve either way. The two candidates that
actually rank highest are the ones most tightly coupled to *this specific framework's own runtime
and prompt-structure*, not a new library to bolt on — which is consistent with the researcher role's
stated preference for reproducible, directly-verifiable evidence over novelty.

---

## What Codex's summary most likely got wrong or overstated (synthesized across the above)

1. **The single biggest lever (Finding 0) isn't a third-party library at all** — it's a live,
   open, disputed bug/gap in the very platform this framework runs on. A summary built from listing
   external repos/papers would structurally never surface this, since it required reading
   `code.claude.com`'s own docs against a live GitHub issue.
2. **"Semantic caching" claims for GPTCache/LiteLLM/Portkey need the Verifier/Coder correctness
   risk stated up front**, not as a footnote — a stale-but-similar cache hit on a judging role is a
   silent false-pass, the exact failure category this project's Verifier-independence rules exist
   to prevent.
3. **Portkey's semantic caching is Enterprise-plan-gated** — a real, concrete gate a generic
   "Portkey supports semantic caching" line would miss for a non-enterprise deployment.
4. **A gateway (LiteLLM/Portkey) in front of a subscription-billed Claude Code session switches
   billing to metered per-token** — a token-spend-reduction recommendation that doesn't surface this
   risks recommending a net cost *increase*.
5. **"Semantic-router" is not a caching tool** — likely name-conflated with semantic caching in a
   fast summary; it's an intent-classification/routing layer with no clear fit in this framework's
   current architecture.
6. **LLMLingua/GPTCache "actively maintained" claims need the actual commit/release cadence
   quoted**, not just star count — both are real and not archived, but both show genuine
   multi-month-to-year gaps (GPTCache: ~1 year since last commit; LLMLingua: 2+ years since last
   tagged release) that a stars-only framing hides.
7. **SCALM and AttentionRAG have no public code** — any framing that implies either is
   "implementable" rather than "an unreproduced paper claim" overstates readiness; both are capped
   at confidence ≤0.3 per the honesty-bar rule and are RESEARCH_ONLY.
8. **FrugalGPT and RECOMP's benchmark numbers (98% cost cut, 6% compression) are from
   classification/QA/reading-comprehension tasks, not coding-agent workloads** — real numbers, wrong
   distribution; portable as a *pattern*, not as a literal expected effect size here.

## Sources (every URL opened/fetched directly in this pass)

- https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://code.claude.com/docs/en/prompt-caching
- https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts
- https://code.claude.com/docs/en/llm-gateway
- https://github.com/anthropics/claude-code/issues/29966 (+ its comment thread, via GitHub API)
- https://github.com/KevinZhao/claudecode-bedrock-proxy
- https://github.com/microsoft/LLMLingua (+ GitHub API: stars/license/commits/releases)
- https://github.com/zilliztech/GPTCache (+ GitHub API)
- https://arxiv.org/abs/2406.00025 (SCALM)
- https://arxiv.org/abs/2305.05176 (FrugalGPT) + https://github.com/stanford-futuredata/FrugalGPT (+ GitHub API)
- https://arxiv.org/abs/2310.04408 (RECOMP) + https://github.com/carriex/recomp (+ GitHub API)
- https://arxiv.org/abs/2503.10720 (AttentionRAG)
- https://arxiv.org/abs/2307.03172 (Lost in the Middle)
- https://github.com/BerriAI/litellm (+ GitHub API) + https://docs.litellm.ai/docs/proxy/caching + raw LICENSE file
- https://github.com/aurelio-labs/semantic-router (+ GitHub API)
- https://github.com/Portkey-AI/gateway (+ GitHub API, recent commits) + https://portkey.ai/docs/product/ai-gateway/cache-simple-and-semantic
- npm registry: `@anthropic-ai/claude-code` (2.1.204), `@anthropic-ai/claude-agent-sdk` (0.3.204) — version/dist-tag check + direct `npm pack` source inspection attempt

## Linked from

- `~/Claude/loop/research/radar.md` — new dated section "Token-spend-reduction stack verification
  (2026-07-08 Codex follow-up)", appended per this file's findings.
