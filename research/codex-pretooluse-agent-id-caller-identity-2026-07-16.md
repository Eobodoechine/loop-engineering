# Domain brief — does Codex's own PreToolUse payload carry a reliable caller-identity signal (agent_id)?

**Mode:** D (domain research for a build). **Build:** `fix/oga-guard-caller-identity`
(`loop-team/runs/2026-07-15_oga-guard-caller-identity/specs/spec.md`). **Date:** 2026-07-16.
**Researcher scope note:** all reads/greps below were done directly by the Researcher, no
sub-agent dispatched, per the dispatch's instruction.

## Question

Does a genuinely-dispatched Codex sub-agent's own PreToolUse payload (for its own
`apply_patch`/edit call) carry a reliable top-level caller-identity signal analogous to Claude
Code's `agent_id` field — or is this actually unconfirmed/unknown in this codebase today?

## Answer (three-part — the honest picture has three layers, not one verdict)

**1. Empirically: YES, reliably, on this machine's real, current Codex runtime — but this
evidence lives OUTSIDE the checked-in test suite and outside any doc, in a live debug log.**
`~/.loop-gate/oga_guard_debug.jsonl` (this repo's own `pre_tool_use_oga_guard.py` writes it,
per `_write_debug_row()`, `hooks/pre_tool_use_oga_guard.py:629-650`) has 5,176 real rows on this
machine, 1,197 of them `tool: "apply_patch"`. Filtering to rows with a real Codex-shaped
`transcript_basename` (`rollout-<timestamp>-<uuid>.jsonl`) and a non-synthetic `session_id`
(excludes pytest-suite pollution and hand-run probes, both confirmed present in the same file —
see Constraints) leaves **1,078 real rows**: **1,039 carry `agent_id` (+`agent_type`) as a
top-level payload key and every one of them was `decision: "allow"`; 39 lack it and every one of
them was `decision: "deny"` — a 100% clean split, zero exceptions.** Grouped by
`transcript_basename` (125 distinct real files): **11 are the session's own "main" transcript**
(basename's trailing UUID equals its own `session_id` — i.e. the top-level Codex session calling
`apply_patch` directly) and **all 11 consistently show no `agent_id`**; **113 are a different
transcript than the tagged `session_id`** (a dispatched sub-agent's own separate transcript file)
and **all 113 consistently show `agent_id` present**. Two session_ids give a directly-paired
natural experiment — the *same* `session_id`, at different timestamps, produces both shapes:

| session_id | transcript (own vs child) | has agent_id | decision | file |
|---|---|---|---|---|
| `019f4fb9-e98e-...-a69f0505f336` | own (`rollout-...-019f4fb9...jsonl`) | no | deny | `research/transparent-mission-control/control-plane-goal-status.json` |
| `019f4fb9-e98e-...-a69f0505f336` | child (`rollout-...-019f5419...jsonl`) | yes | allow | same file |
| `019f594d-99e5-...-633449c4d55d` | own (`rollout-...-019f594d...jsonl`) | no | deny | `loop-team/harness/mission_control.py` |
| `019f594d-99e5-...-633449c4d55d` | child (`rollout-...-019f59a5...jsonl`) | yes | allow | `runs/2026-07-12_control-plane-live-two-product/gap_records/regression-audit.json` |
| `019f594d-99e5-...-633449c4d55d` | child (`rollout-...-019f5bf0...jsonl`) | yes | allow | `loop-team/harness/reconcile_manifest.py` |

The touched files (`mission_control.py`, `reconcile_manifest.py`, `control-plane-goal-status.json`
— all present as real untracked files in `git status --short` on this exact repo right now) confirm
these are genuine sessions from this project's own real work, not fabricated rows. **Installed
runtime this evidence describes:** `codex --version` → `codex-cli 0.41.0` (confirmed by direct
invocation, not inferred).

**2. But no checked-in test or official documentation confirms it — the dispatch's framing is
correct on that specific claim.**
- **Test suite:** `hooks/test_pre_tool_use_oga_guard.py`'s `TestAgentIdCallerIdentity` class
  (lines 613-677) is the *only* place the `agent_id` fast path is asserted — every one of its
  cases calls `_run_hook_with_payload(..., tool_name=...)` whose **default `tool_name` is `"Edit"`**
  (line 501) — Claude Code's own tool name. No test in that class passes `tool_name="apply_patch"`.
  `TestCodexSpawnAgentPreToolUseParity` (lines 2137-2203) is Codex-shaped but tests a *different*
  thing entirely: it dispatches **into** Codex's `spawn_agent` (via `_run_codex_spawn_payload`,
  lines 1780-1802, which hardcodes `tool_name="spawn_agent"` and never sets `agent_id`) — i.e. Oga
  launching a Codex sub-agent, not a Codex sub-agent's own follow-up `apply_patch` call.
  `TestCodexOgaSessionArms`'s three `apply_patch` tests (lines 205-244) exercise the base
  WORKER_TOOLS deny path and also never include `agent_id` in the payload. **Zero automated tests
  construct "Codex sub-agent's own apply_patch call carrying agent_id."**
- **This project's own research:** `research/spec-codex-parity-and-consent-installer-2026-07-09.md`
  (the spec that added `apply_patch`/`WORKER_TOOLS`/`_M_CODEX_DISPATCH`/`spawn_agent` normalization
  to this exact hook) fetched Codex's official hooks docs and recorded the `Stop`/`SubagentStop`
  field lists in detail (lines 97-101) but **contains zero mentions of "PreToolUse" anywhere in its
  522 lines** (grep-confirmed) — the spec's own author never investigated PreToolUse's schema.
  `PORTABILITY.md` (lines 40, 44-56) documents Codex's hook event mapping and even flags a historical
  Codex issue where "PreToolUse historically fired for shell only — `apply_patch` edits bypassed
  hooks" (openai/codex#16732, expansion tracked in #18491) — but likewise never mentions `agent_id`.
- **Official docs, fetched live today (2026-07-16), twice, independently, with verbatim
  reproduction on the second pass:** `https://developers.openai.com/codex/hooks` (redirects to
  `https://learn.chatgpt.com/docs/hooks`). The documented `PreToolUse` fields are: common fields
  (`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, `permission_mode`) plus
  event-specific `turn_id`, `tool_name`, `tool_use_id`, `tool_input`. **`agent_id`/`agent_type` are
  NOT in that list.** They appear only in the `SubagentStart` and `SubagentStop` tables. So the
  *current, official, published* contract says Codex's PreToolUse should **not** carry `agent_id`
  at all — directly at odds with what layer 1 (above) empirically observes. GitHub issues #16732 and
  #18491 (the PreToolUse-coverage-expansion issues) were also checked directly and neither mentions
  `agent_id`/`agent_type`/sub-agent differentiation.
- **Practical reading of the contradiction:** hooks are an explicitly experimental, evolving Codex
  surface (the docs' own transcript-format caveat: "may change over time"; PreToolUse's own
  apply_patch coverage was itself added after a GitHub issue, per PORTABILITY.md). The most likely
  explanation is that the real 0.41.0 runtime already attaches `agent_id`/`agent_type` to *every*
  hook event fired from inside a sub-agent's turn context (consistent with the "Common input
  fields" doc's own note that `session_id` "Subagent hooks use the parent session id" — exactly the
  behavior observed in the paired rows above) even though the PreToolUse-specific doc table hasn't
  been updated to say so. That is a real, live, favorable behavior today — but it is **undocumented**,
  meaning nothing prevents a future Codex release from tightening PreToolUse's payload to match its
  own currently-published field list (i.e. dropping `agent_id`), which would silently regress this.

**3. Independent of (1)/(2): the in-flight fallback this build's spec proposes to gate more tightly
cannot help Codex regardless, today or after the fix.** The fallback's dispatched-Agent-id
collector (`hooks/pre_tool_use_oga_guard.py:705-716`) scans the CURRENT transcript's own history
for a prior dispatch, but its match condition is `p.get("type") == "tool_use" and
p.get("name") == "Agent"` (line 713) — **literally, only the string `"Agent"`, never
`"spawn_agent"`**. The file's own `_dispatch_view()` normalizer (lines 23-40) *does* map
`spawn_agent` → `"Agent"`-shaped output, but that normalized `dispatch_tool_name`/
`dispatch_tool_input` is consumed only by the dispatch-gating branches earlier in the file
(`dispatch_check_presence` at line 140, repo-health classification at line 278, spec-bound-credit
at lines 334-392) — **never by the in-flight collector**, which reads raw transcript event
content directly. Separately, Codex's real transcript shape is `session_meta`/`response_item`
top-level objects (confirmed both by `codex_transcript_adapter.py`'s own `_detect_runtime()`,
lines 68-119, and by the real captured structure documented in the 2026-07-09 spec, lines 112-134),
not the `message.content` list of `tool_use` blocks that `_content()`/`_role()`
(`hooks/pre_tool_use_oga_guard.py:676-686`) expect. **So for a genuine Codex session, the
fallback's `dispatched` set is structurally guaranteed to stay empty — `in_flight_ids` is always
`[]`.** This matches the real data exactly: of the 39 real "no `agent_id`" apply_patch rows, 0 were
ever `allow` (consistent with — not just theorized from — the code reading). **Consequence for
this build's Option A "legacy escape-hatch" env var (`LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1`):
it would not actually protect a Codex sub-agent even if `agent_id` ever stopped being populated —
the fallback it re-enables cannot recognize a Codex dispatch to begin with.** This is a
pre-existing gap (not created by the proposed redesign) but is directly relevant to the redesign's
risk assessment, since Option A's `AC7`/design question explicitly asks about the value of a
cross-check against "a still-in-flight ... Agent tool_use" — for Codex that check is already inert.

## What this means for the specific regression the dispatch asked about

Per Section E of the spec (`loop-team/runs/2026-07-15_oga-guard-caller-identity/specs/spec.md`),
Option A's deny-by-default only changes behavior on the **falsy**-`agent_id` branch (AC2-AC6); AC1
(`agent_id` truthy → allow, unchanged) is untouched. Since a genuine Codex sub-agent's own
`apply_patch` call empirically carries a truthy `agent_id` today (layer 1, 1,039/1,039), **it hits
the unchanged AC1 fast path and the proposed redesign would NOT newly deny it, today, on this
runtime/version.** The real risk is forward-looking and narrower than "this fix breaks Codex right
now": it is "if/when Codex's PreToolUse payload ever conforms to its own currently-published,
`agent_id`-less schema, a genuine Codex sub-agent's follow-up edit would then be denied with **no**
working fallback" — a risk that exists in the codebase already (independent of this spec) because
of finding 3 above, and that this spec's design should probably name explicitly rather than treat
as fully closed.

## Sources (every claim above, file:line or URL)

- `hooks/pre_tool_use_oga_guard.py:539` — `WORKER_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit", "apply_patch"}`
- `hooks/pre_tool_use_oga_guard.py:23-40` — `_dispatch_view()`, Codex `spawn_agent` → `Agent`-shape normalizer
- `hooks/pre_tool_use_oga_guard.py:618-626` — `_M_CODEX_DISPATCH` marker, session-arming for Codex loop-team sessions
- `hooks/pre_tool_use_oga_guard.py:629-650` — `_write_debug_row()` (writes `~/.loop-gate/oga_guard_debug.jsonl`, AC-RH5 fields)
- `hooks/pre_tool_use_oga_guard.py:653-663` — the `agent_id` fast path (`if data.get("agent_id"): allow`, line 661)
- `hooks/pre_tool_use_oga_guard.py:665-716` — in-flight fallback; line 713 `p.get("name") == "Agent"` (never `"spawn_agent"`)
- `hooks/pre_tool_use_oga_guard.py:676-686` — `_content()`/`_role()`, Claude-Code-transcript-shaped helpers
- `hooks/codex_hook_stdin_capture.py:1-66` (whole file) — one-shot capture, gated to `hook_event in ("Stop", "SubagentStop")` only (line 30); never wired into `pre_tool_use_oga_guard.py` (confirmed: zero matches for `codex_hook_stdin_capture`/`capture_once` in that file)
- `hooks/loop_stop_guard.py:101`, `hooks/subagent_stop_gate.py:88` — the only two call sites of `capture_once`
- `hooks/fixtures/ac1_captured_codex_stop_stdin.json` + `.meta.json` — the one real captured Codex payload on disk; `hook_event_name: "SubagentStop"` (not PreToolUse); carries top-level `agent_id`/`agent_type` (confirms SubagentStop's schema empirically, says nothing about PreToolUse)
- `hooks/codex_transcript_adapter.py:1-119` — `_detect_runtime()`, confirms Codex's real transcript shape (`session_meta`/`response_item`) differs structurally from Claude Code's (`message.content` list); this module parses PAST session-transcript content for Verifier-dispatch extraction, not live PreToolUse stdin shape
- `hooks/test_pre_tool_use_oga_guard.py:90-107` (`_run_hook`), `111-128` (`_run_hook_tool_input`), `500-528` (`_run_hook_with_payload`, default `tool_name="Edit"` at line 501) — none ever pair `tool_name="apply_patch"` with an `agent_id` payload extra
- `hooks/test_pre_tool_use_oga_guard.py:196-244` — `TestCodexOgaSessionArms` (apply_patch base-deny tests, no `agent_id`)
- `hooks/test_pre_tool_use_oga_guard.py:599-677` — `TestAgentIdCallerIdentity` (the only `agent_id` fast-path tests; all Claude-Code-shaped)
- `hooks/test_pre_tool_use_oga_guard.py:1780-1802` (`_run_codex_spawn_payload`), `2137-2203` (`TestCodexSpawnAgentPreToolUseParity`) — Codex-shaped, but tests dispatch-into-Codex, not a sub-agent's own follow-up edit
- `fix_plan.md:833-849` — H-LT6 "PROPER FIX DONE" entry; original evidence ("57 vs 122 rows... runtime schema not source-verified") is Claude-Code-only (see git evidence below)
- `fix_plan.md:7314-7361` — `H-CODEX-SPAWN-PRETOOLUSE-DISPATCH-GAP-1`; explicitly flags as still open: "capture live PreToolUse stdin for Codex `spawn_agent` if the team wants live hook registration/runtime proof rather than fixture-level proof"
- `research/spec-codex-parity-and-consent-installer-2026-07-09.md:96-101` — Codex's official Stop/SubagentStop schema (source: developers.openai.com/codex/hooks, as fetched 2026-07-09); zero "PreToolUse" mentions in the whole 522-line file (grep-confirmed 2026-07-16)
- `PORTABILITY.md:40,44-56` — Codex PreToolUse hook-mapping notes, historical apply_patch-bypasses-hooks issue (openai/codex#16732, #18491); no `agent_id` mention anywhere in the file
- git: `a5327f0` (2026-07-02, "H-LT6 caller-identity fix") — `git show a5327f0:hooks/pre_tool_use_oga_guard.py` shows `WORKER_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}` (no `apply_patch`) and **zero** occurrences of `apply_patch`/`spawn_agent`/`CODEX` in that exact historical file version — proves the original agent_id evidence could not have included any Codex row
- git: `git log -S"apply_patch" -- hooks/pre_tool_use_oga_guard.py` → first (only) hit is `2a4f1b1` (2026-07-15) — apply_patch support landed in this file 13 days after the original H-LT6 commit
- `~/.loop-gate/oga_guard_debug.jsonl` (this machine, read 2026-07-16; 5,176 total rows, 1,197 `tool=="apply_patch"`, 1,078 classified real after excluding synthetic/pytest rows) — see Constraints for the exact filter and for the pytest-pollution/manual-probe rows also found in the same file
- [`https://developers.openai.com/codex/hooks`](https://developers.openai.com/codex/hooks) (redirects to [`https://learn.chatgpt.com/docs/hooks`](https://learn.chatgpt.com/docs/hooks)) — fetched twice live 2026-07-16; verbatim per-event field tables quoted above; `PreToolUse` fields do not include `agent_id`/`agent_type`, `SubagentStart`/`SubagentStop` do
- [`https://github.com/openai/codex/issues/18491`](https://github.com/openai/codex/issues/18491), [`https://github.com/openai/codex/issues/16732`](https://github.com/openai/codex/issues/16732) — PreToolUse/apply_patch coverage-expansion issues, fetched live 2026-07-16; neither mentions `agent_id`/`agent_type`
- Installed runtime: `codex --version` → `codex-cli 0.41.0` (direct Bash invocation, 2026-07-16)

## Constraints / data-hygiene notes on the `~/.loop-gate/oga_guard_debug.jsonl` evidence

- **Scope disclosure (read this before weighting the evidence):** this file lives outside the repo
  tree (`~/.loop-gate/`, this machine's `LOOP_GATE_DIR` default), not inside `~/Claude/loop/`. It is
  **not** a session transcript — it is a purpose-built, redacted debug log this repo's *own* hook
  writes (`_write_debug_row`, cited above), whose schema is deliberately limited to
  `{ts, tool, file, decision, in_flight_ids, session_id, transcript_basename, payload_keys}` —
  key **names** only, values redacted, transcript path reduced to a basename. `fix_plan.md` already
  treats this exact file as this mechanism's authoritative evidence source (e.g. line 838: "the
  AC-RH5 debug fields answered the blocker"; line 5657: "verified directly against this machine's
  real `~/.loop-gate/oga_guard_debug.jsonl` (1760 real rows) before committing to an approach"), and
  `loop-team/learnings.md:591-594` states the standing practice explicitly: "Your own live session
  is a probe corpus... Harvest the session, don't just endure it." Judged in-scope on that basis —
  flagged here explicitly per the honesty bar so Oga/the plan-check Verifier can independently agree
  or disagree with that call.
- **The same file is polluted by two other row sources**, both identified and excluded from the
  1,078-row "real" count: (a) the pytest suite itself — `_run_hook`/`_run_hook_tool_input`
  (`hooks/test_pre_tool_use_oga_guard.py:90-128`) never override `LOOP_GATE_DIR`, so running
  `TestCodexOgaSessionArms`'s apply_patch tests writes real rows with `session_id: ""` and
  `transcript_basename` like `tmpXXXXXXXX.jsonl` into this same file; (b) at least one prior
  hand-run manual verification probe, session_ids literally `test-codex-agentid-1` /
  `test-codex-applypatch-1` / `test-codex-mixed-1` (files `/tmp/widget4.py` etc.) — these are 100%
  consistent with the main finding (agent_id present → allow, absent → deny) but are synthetic, not
  live sub-agent behavior, so excluded from the headline count. Filter used: real-Codex row =
  `transcript_basename` matches `rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-[0-9a-f-]+\.jsonl` AND
  `session_id` is non-empty and does not start with `test-`.
- **Version-pinned finding:** the empirical agent_id-on-PreToolUse behavior is confirmed only for
  installed `codex-cli 0.41.0` on this machine, 2026-07-11 through 2026-07-15. Re-verify after any
  Codex CLI upgrade — the official docs explicitly do not guarantee this field on PreToolUse today.
- **On/around 2026-07-02 (original H-LT6 fix):** the "57 vs 122 rows" / "3 real rows confirmed"
  evidence that grounded the fast path was Claude-Code-only — proven structurally (the file at that
  exact commit had no Codex-awareness at all), not merely inferred from dates.

## not_found

- No primary-source explanation for *why* the real runtime attaches `agent_id` to PreToolUse when
  the official docs' PreToolUse table doesn't list it — this brief can report the empirical fact and
  a plausible mechanism (parent-session-id propagation applies broadly to "subagent hooks," per the
  docs' own common-fields note) but could not find an OpenAI changelog/release-note entry confirming
  this was an intentional, stable addition versus an implementation detail that happens to work today.
  A future search should check `developers.openai.com/codex` release notes / changelog for any
  PreToolUse-schema-related entry after the #18491 apply_patch-coverage expansion.
  - **Update while finalizing this brief:** confirmed 0 references anywhere in this repo's own
    Codex-facing docs (`research/spec-codex-parity-and-consent-installer-2026-07-09.md`,
    `PORTABILITY.md`, `loop-team/CODEX_CLAUDE_TEAM.md`) to a changelog/release note settling this —
    genuinely open, not just unchecked.
- No test exists (and this brief does not author one — tests are Test-writer/Coder territory) that
  would pin this behavior as a regression check. If the build wants a durable guarantee rather than
  a one-time empirical observation, `TestCodexSpawnAgentPreToolUseParity`-style coverage for
  `tool_name="apply_patch"` + a top-level `agent_id` payload extra is the natural place, mirroring
  `TestAgentIdCallerIdentity`'s existing Claude-Code-shaped cases (lines 619-677).
- Could not determine whether Codex's `agent_id` attachment to non-Subagent* hook events is
  documented anywhere in OpenAI's private/internal engineering docs (only the public
  `developers.openai.com/codex/hooks` page was checked, per the honesty bar's "real sources only" —
  no such internal source is accessible to this Researcher).
