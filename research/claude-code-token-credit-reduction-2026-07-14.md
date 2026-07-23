# Reducing Claude Code token/credit consumption (Max 20x plan)

**Date:** 2026-07-14
**Method:** deep-research workflow (95 sub-agents, 3 search angles, 15 sources fetched, 25 claims adversarially verified 3-vote)
**Trigger:** hitting 5-hour (73%) and weekly (15%) usage limits on Max 20x plan

## Core mechanism

Claude Code re-sends the entire conversation history as input tokens on every turn — cost scales with accumulated context, not just the new message (confirmed, code.claude.com/docs/en/context-window; platform.claude.com/docs/en/build-with-claude/context-windows). Prompt caching is what makes this affordable: cache hits are 90% cheaper (0.1x multiplier) but cache writes carry a premium (1.25x for 5-min TTL, 2x for 1-hour TTL) — so caching only pays off once the same prefix is reused 1-2+ times before expiry (platform.claude.com/docs/en/build-with-claude/prompt-caching). Everything else below is either protecting that cached prefix or cutting fixed per-session overhead.

## Prioritized action list

1. **Install a usage monitor** — see burn-rate against the 5h/weekly windows in real time instead of discovering the limit after hitting it.
2. **Default to Sonnet; reserve Opus deliberately** for hard architecture/debugging only. Anthropic's own support docs: "Spending Opus on routine work is the fastest way to drain a daily limit."
3. **Set `CLAUDE_CODE_SUBAGENT_MODEL=haiku`** (confirmed current env var, code.claude.com/docs/en/env-vars) so subagents/Explore/workflow agents run cheap while the main session stays on Sonnet.
4. **Avoid Agent Teams / heavy multi-instance dispatch for routine work** — Anthropic's own docs cite ~7x token cost vs. a single session when teammates run in plan mode (each teammate keeps its own full context window). Reserve for tasks genuinely worth the multiplier.
5. **Trim CLAUDE.md to <200 lines**, move workflow-specific instructions into on-demand Skills — CLAUDE.md loads into every session regardless of relevance (code.claude.com/docs/en/costs, verbatim recommendation). Directly applicable: this user's global CLAUDE.md carries a detailed `/loop-team` file-path override block that could become a Skill instead.
6. **Prefer CLI tools (`gh`, `aws`, `gcloud`, `sentry-cli`) over equivalent MCP servers** where both exist — MCP tool defs are deferred by default (only names load until used) but still add real per-session overhead that a CLI invocation doesn't.
7. **Fresh session per distinct task; run `/compact` proactively**, not after ballooning — unrelated accumulated history is pure waste even with caching.
8. **Add PreToolUse hooks to pre-filter verbose output** (grep ERROR/FAIL from long logs/test runs) before it enters context — documented Anthropic example cuts tens of thousands of tokens to hundreds.
9. **Batch related requests within one cache TTL window** rather than spacing them out sparsely — scattered requests forfeit the caching discount.

## GitHub tools (vetted via gh/web search — stars + last-push checked)

| Repo | Stars | Last push | What it does |
|---|---|---|---|
| [ryoppippi/ccusage](https://github.com/ryoppippi/ccusage) | ~17.2k | 2026-07-14 (today) | CLI usage/cost analyzer, reads local session logs, no API key needed. Most actively maintained of the three. Its README claims a dedicated "5-Hour Blocks Report," but that specific claim only scored 1-2 on adversarial verification — treat as plausible-but-unconfirmed, verify yourself before relying on it. |
| [Maciek-roboblog/Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) | 8,443 | 2026-07-05 | Live token/message/cost tracking within 5-hour windows, burn-rate analytics, session-expiry forecasting, native `--plan max20` support. **Confirmed** (3-0). Does NOT have a hardcoded ~220k token/5hr budget baked in — that specific claim was refuted. |
| [phuryn/claude-usage](https://github.com/phuryn/claude-usage) | 2,017 | 2026-07-10 | Reads local JSONL session transcripts from `~/.claude/projects/` into a local SQLite DB, stdlib-only, no telemetry. **Confirmed** (3-0). Does not render quota-specific progress bars (that claim was refuted).|
| [cnighswonger/claude-code-cache-fix](https://github.com/cnighswonger/claude-code-cache-fix) | (smaller/blog-tier source) | — | Documents a prompt-cache regression in Claude Code's `--resume`/`/resume` path causing up to 20x cost increase on resumed sessions (~$0.50/hr → $5-10/hr with no visible warning). Worth checking if you use `/resume` heavily. Not independently re-verified to the same bar as the three above — treat as a lead, not a confirmed fact. |

## Claims specifically checked and REFUTED (common myths — do not rely on these)

- MCP tool schemas are NOT confirmed to follow a documented cacheable hierarchy (tools→system→messages).
- No confirmed rolling 5-hour reset tied to the *credit allowance* itself (distinct from the session-window concept).
- Claude Projects content is **not** confirmed exempt from usage limits via caching.
- "Frequently repeated similar prompts are partially served from cache" outside the documented cache-control mechanism — refuted.
- No authoritative "10,000-20,000 tokens per MCP server" overhead figure — real estimates vary wildly (4x-35x) with no single number.
- No confirmed "/compact at 40-50% context" or "250k-300k tokens" trigger threshold from Anthropic — best guidance is simply "proactively, before near the limit," not a precise number.
- "75% cost cut from model routing" and "60% token reduction from workflow discipline" — both unsubstantiated single-blog claims, not general findings.

## Open questions

- Anthropic doesn't publish a formula for how much cache-hit rate translates into extra Claude Code turns within a 5-hour Max-plan window.
- Per-MCP-server context overhead has no authoritative number — run `/context` yourself with your actual connected servers to get a real figure.
- No official `/compact` trigger threshold exists — practical guidance is "before you're close to the limit," not a specific %.
- Whether Anthropic's "weekly" limit resets on a literal calendar week or a ~72-hour rolling cycle wasn't independently confirmed — worth checking against your own account's actual reset behavior.

## Caveat on this guidance's shelf life

Primary sources reference Claude Code v2.1.208 and 2026 features (Opus 4.6 agent teams, Fable) — this reflects Claude Code's mid-2026 state. `CLAUDE_CODE_SUBAGENT_MODEL` behavior has already changed once recently (Explore agent's default model source). Re-verify env-var names against `code.claude.com/docs/en/env-vars` before scripting around them.
