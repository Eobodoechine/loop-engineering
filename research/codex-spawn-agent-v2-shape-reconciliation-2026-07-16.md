# Domain brief — Codex product/version identity + ground-truth spawn_agent/wait_agent wire shape reconciliation

**Mode:** D (domain research for a build). **Trigger:** pre-spec research for a `codex_transcript_adapter.py`
staleness fix (spec not yet written — this brief is its input). **Date:** 2026-07-16. **Researcher scope
note:** all reads/greps/WebSearch/WebFetch calls below were done directly, no sub-agent dispatched, per the
dispatch's explicit instruction ("Do NOT dispatch your own sub-agents"). Reading real Codex session
transcripts under `~/.codex/sessions/` was explicitly authorized by this dispatch's own text ("ground-truth
the real spawn_agent/wait_agent wire shape... against live `~/.codex/sessions/` transcripts"). Only
structural fields (event types, ids, timestamps, task names, argument key names) were extracted; the one
genuinely-encrypted field found (`message` under the new shape) was read only far enough to confirm its
literal opacity, never decrypted.

**Relationship to the two same-day sibling docs**, both read in full before starting:
- `research/codex-pretooluse-session-id-caller-identity-2026-07-16.md` — established the `session_id`=parent /
  `_find_child_verdict()` mismatch and first surfaced the shape-staleness risk (its Part 4) as an *adjacent*
  finding, explicitly flagged there as "not squarely inside" that brief's own primary question.
- `research/codex-pretooluse-agent-id-caller-identity-2026-07-16.md` — established `agent_id` reliability on
  PreToolUse and directly discusses `_dispatch_view()`, but only for the OLD shape's `agent_type`/`message`
  keys; it never checked what `_dispatch_view()` does with a `task_name`/`fork_turns` payload.

This brief's job was to take the shape-staleness risk both docs flagged in passing and become its dedicated,
ground-truth investigation — reconciling what is real, versioned, and in-scope. **Net new findings beyond
both prior docs:** (1) the OSS-vs-Desktop version-identity question is now resolved (both prior docs left it
an open, unreconciled constraint); (2) the shape split is shown to be governed by the call's own `namespace`
field, not by cli_version/date, with a 100%-clean, zero-exception empirical mapping; (3) the OLD shape is
directly proven still-live *today*, on a brand-new session, not merely "possibly still out there somewhere";
(4) the exact parent-child correlation field for the NEW shape (`agent_path` == output's `task_name`) is
identified and verified 14/14, closing a gap neither prior doc closed; (5) `wait_agent`'s own wire shape
under the NEW namespace is shown to carry **no per-agent status/completion text at all** (69/69 real calls
checked) — a materially different, more severe fact than either prior doc examined, since neither looked at
`wait_agent` specifically.

## Q1 — Version/product identity: same product, two distributions, one stale

**Answer:** `codex --version` (direct invocation) returns `codex-cli 0.41.0`. This is the terminal CLI
distribution of the **same** open-source project (`github.com/openai/codex`, Apache-2.0) that also ships as
"Codex App"/"Codex Desktop" (a separate, auto-updating GUI surface) — not a different product on a different
numbering scheme. The disparity between `0.41.0` and the `0.142.x`–`0.144.x` values recorded inside every
real session transcript is because **this exact machine's Homebrew-installed CLI binary is ~10 months stale
and was never upgraded**, while "Codex Desktop" is the surface that has continued auto-updating and is the
one actually producing essentially every transcript this repo's hooks read.

- `brew info codex` (run live): `codex: stable 0.41.0, HEAD ... https://github.com/openai/codex ...
  Installed (on request)`. `/opt/homebrew/Cellar/codex/` contains exactly **one** version directory,
  `0.41.0`, timestamped `Sep 25 2025` — confirming a single install nearly 10 months before this research
  date, never subsequently `brew upgrade`d (only one Cellar entry ever existed).
- Official `github.com/openai/codex` README (fetched live): explicitly distinguishes **"Codex CLI"** (this
  repo, the terminal tool) from **"Codex App"** (a separate desktop experience, launchable via `codex app` or
  `chatgpt.com/codex?app-landing-page=true`), **"Codex Web"** (`chatgpt.com/codex`), and IDE integrations —
  all documented as related-but-distinct surfaces of one project. License: Apache-2.0.
- Official changelog (`developers.openai.com/codex/changelog?type=codex-app` → redirects to
  `learn.chatgpt.com/docs/changelog?type=codex-app`, fetched live): verbatim entries **"2026-07-09 Codex joins
  the ChatGPT desktop app"** and **"2026-07-08 Codex CLI 0.143.0"** (`npm install -g @openai/codex@0.143.0`)
  — i.e. the officially-published CLI release train was at `0.143.0` on 2026-07-08, the same week real
  "Codex Desktop" transcripts on this machine show `cli_version` moving `0.144.0-alpha.4` → `0.144.2` — **the
  same numbering family, same week**, not two unrelated schemes.
- `github.com/openai/codex/releases` (fetched live): current tags include `0.144.4`, `0.144.5`,
  `0.145.0-alpha.12`–`alpha.16` — one continuous, actively-maintained semver line for the whole project.
  WebSearch independently surfaced a real historical tag `rust-v0.141.0` in the same repo, consistent with
  one unbroken numbering line running from at least the 0.14x range upward (I could not locate a `0.41.0` tag
  specifically on the current releases listing, consistent with it being an old point release from well
  before the repo's now-visible release window, not a different project).
- **Direct data cross-check:** every real session transcript sampled across all 12 available dates
  (2026-07-01 through 2026-07-16) shows `originator: "Codex Desktop"` **except exactly one file**:
  `~/.codex/sessions/2026/07/07/rollout-2026-07-07T21-12-59-019f3f49-0b4b-7853-aa99-a0c9ab31ac01.jsonl`, whose
  `session_meta.payload` reads `"originator":"codex_cli_rs","cli_version":"0.41.0"` — an **exact** match to
  this machine's locally-invoked `codex --version` output. This is the one time the actual terminal binary
  produced a transcript; every other one of the ~1934 real files on this machine came from Codex Desktop.

**State plainly: the product that writes `~/.codex/sessions/**/*.jsonl` in this environment is "Codex
Desktop," not the stale local `codex` CLI.** Any fix must be grounded in what Codex Desktop emits (which is
what every finding below describes), not in what the locally-invocable, out-of-date CLI binary would emit if
run today.

## Q2 — Direct before/after diff: NOT a clean chronological cutover; a `namespace`-keyed split, live in parallel

**Answer:** I opened the exact 07/09 file the fixture-builder's docstring cites, plus two 07/16 (today)
examples — one of each shape, since (this is the key finding) **both shapes coexist on 2026-07-16**, not
just historically.

**07/09 verbatim** (`~/.codex/sessions/2026/07/09/rollout-2026-07-09T14-03-17-019f480c-5c61-7b53-8b62-25f48e47cefb.jsonl`,
`cli_version: "0.144.0-alpha.4"`, line 18/19):
```json
{"timestamp":"2026-07-09T18:04:28.423Z","type":"response_item","payload":{
  "type":"function_call","id":"fc_05685506d9117b05016a4fe2a8037c8190ba6fbf47e0d8052b",
  "name":"spawn_agent","namespace":"multi_agent_v1",
  "arguments":"{\"agent_type\":\"explorer\",\"message\":\"You are an explorer agent for the TaxAhead Gmail connector build.\\n\\nRepo/worktree: <HOME>/.codex/worktrees/af44/taxahead-connector-platform...\",\"fork_context\":false}",
  "call_id":"call_B0mbALMCAEhPmHlExZTsElfU", ...}}
{"timestamp":"2026-07-09T18:04:35.160Z","type":"response_item","payload":{
  "type":"function_call_output","call_id":"call_B0mbALMCAEhPmHlExZTsElfU",
  "output":"{\"agent_id\":\"019f480d-8083-7cc3-916f-e7bf2873f27e\",\"nickname\":\"Ohm\"}", ...}}
```

**07/16 (today) OLD shape verbatim** — a **brand-new** top-level session (`session_id==id`,
`thread_source:"user"`, created `2026-07-16T04:23:57Z`, `cli_version:"0.144.2"`), file
`rollout-2026-07-16T00-23-57-019f692a-c0ad-75c3-bd81-2d2f6fa31f9d.jsonl`, line 116/117:
```json
{"timestamp":"2026-07-16T04:26:29.163Z","type":"response_item","payload":{
  "type":"function_call","name":"spawn_agent","namespace":"multi_agent_v1",
  "arguments":"{\"agent_type\":\"explorer\",\"fork_context\":false,\"message\":\"Role: loop-team Researcher Mode D / mission-slice grounder.\\n\\nTask: Ground the current PadSplit Cockpit finish-slice mission...\"}",
  "call_id":"call_hhRtfbOYgILV2DOMhAxRYEou", ...}}
{"timestamp":"2026-07-16T04:26:29.614Z","type":"response_item","payload":{
  "type":"function_call_output","call_id":"call_hhRtfbOYgILV2DOMhAxRYEou",
  "output":"{\"agent_id\":\"019f692d-121d-7802-80fa-b9a0a4cc39b9\",\"nickname\":\"Carver\"}", ...}}
```

**07/15→16 NEW shape verbatim** (same `cli_version:"0.144.2"`), file
`rollout-2026-07-15T22-13-53-019f68b3-acea-7540-8466-b7f96524e784.jsonl`, line 35/37:
```json
{"timestamp":"2026-07-16T02:15:21.818Z","type":"response_item","payload":{
  "type":"function_call","name":"spawn_agent","namespace":"collaboration",
  "arguments":"{\"task_name\":\"framework_gap_research\",\"fork_turns\":\"all\",\"message\":\"gAAAAABqWD65LcMVj-R_wbuyKTPn4uAYtkb7VU4IjvG4l1IkVGZQqf73jP-RDjFYzNjcSV1MTz5C4Ens9MwxGJhKH4tiRVE37Q...\"}",
  "call_id":"call_bYZyGunQNuq8RcP4jOXp2B9H", ...}}
{"timestamp":"2026-07-16T02:15:22.235Z","type":"response_item","payload":{
  "type":"function_call_output","call_id":"call_bYZyGunQNuq8RcP4jOXp2B9H",
  "output":"{\"task_name\":\"/root/framework_gap_research\"}", ...}}
```

**Systematic cross-tab (not anecdote):** I grepped all 1935 session files for `"spawn_agent"` (89 hit files),
then parsed every function_call/function_call_output pair in each (1689–1692 calls depending on parse-edge
handling). Result: the shape is a **100%-clean, zero-exception function of the call's own `namespace`
field**:
- `namespace=="multi_agent_v1"` → **always** `{agent_type[,fork_context][,reasoning_effort][,items]?,message}`
  args / `{agent_id,nickname}` output (1196+157 calls checked, 0 exceptions).
- `namespace=="collaboration"` → **always** `{task_name,fork_turns,message}` args / `{task_name}` output
  (339 calls checked, 0 exceptions).
- **Zero of the 80 spawn_agent-containing files mix both true shapes internally** (checked programmatically:
  every file is either 100% one shape or 100% the other; no file shows both a true-OLD and true-NEW call).
- **This is NOT a date-gated cutover.** `multi_agent_v1`-shaped calls appear on every sampled date from
  07/01 through 07/16 (today), including on `cli_version 0.144.2` — the identical client version that *also*
  produces `collaboration`-shaped calls elsewhere on the same machine, same day, sometimes literally the same
  hour. `session_meta.multi_agent_version` (a session-level field, distinct from the individual call's own
  `namespace` field), *when present*, perfectly predicts the shape (`v1`→old, `v2`→new, 0 exceptions) — but it
  is frequently **absent** (`None`/missing key) even on unambiguously-one-shape sessions, so it cannot be used
  alone as a version gate.
- **The "collaboration" namespace name is an officially documented, intentional rename, not a guess or a
  coincidence I inferred.** The official changelog (fetched live, same page as above) contains the verbatim
  entry **"Namespace multi-agent v2 tools under collaboration" (#29067)**, directly confirming this.

## Q3 — Is `message` really opaque? Yes for the NEW shape, no for the OLD shape — and this maps 1:1 to `namespace`, not to date

**Answer:** Read directly, not assumed. `namespace=="multi_agent_v1"` calls carry a **fully plaintext**
`message` — verbatim natural-language dispatch prompts, e.g. (07/16, today) *"Role: loop-team Researcher Mode
D / mission-slice grounder... Canonical repo: <HOME>/Claude/Projects/padsplit-cockpit..."*.
`namespace=="collaboration"` calls carry a `message` that starts `gAAAAAB...` — the well-known Fernet-token
version-byte signature (the `cryptography` library's symmetric-encryption token format always begins with a
`0x80` version byte, which URL-safe-base64-encodes to `gAAAAA...`). I did not attempt to decrypt it, and
confirmed no plaintext content is visible in it.

Cross-tabulated across all calls found: **1084/1084 `multi_agent_v1` messages classify as plaintext** (either
natural prose, a `{"dispatch...` JSON-shaped string, or `# Role: ...` markdown — all human/machine-readable),
**339/339 `collaboration` messages classify as Fernet-token-shaped** — a perfectly clean split with zero
cross-contamination in either direction.

**Direct consequence, confirmed not assumed:** the dispatch's own concern is correct and more severe than a
naming issue. `_VERIFIER_DETECT`-style regex matching against `message` (used in
`codex_transcript_adapter.py::extract_verifier_dispatches` line 334 and
`micro_step_gates.py::_codex_thrash_past_green` lines 306-308) **cannot be fixed by a field-rename alone** for
`collaboration`-namespace dispatches, because the plaintext content the regex needs (role/intent keywords) no
longer exists anywhere in the accessible payload for that shape — it is encrypted, full stop. A correct fix
for the NEW shape cannot recover role/verifier-intent from `message` at all. (One observable, un-encrypted
signal that IS available and did carry human-readable role information in every real example I opened:
`task_name` — e.g. `"test_writer_structural_guard"`, `"coder_structural_guard"`,
`"verifier_structural_guard_postbuild"` from the 14-call example below — reported as a fact for the
spec-writer to weigh, not a recommendation.)

## Q4 — Parent-child correlation key: confirmed precisely, and it is DIFFERENT per shape

**Answer:** I read 4 real child transcripts directly end-to-end (their own `session_meta`), plus
systematically verified a 14/14 correlation, well beyond the "at least 3" asked for.

**Both shapes, common mechanism (the coarse "which top-level thread"):** every child's own `session_meta`
carries `session_id` == the **parent's** own id (never the child's own distinct identity — confirmed both
here and independently by the sibling `session-id` brief) plus `parent_thread_id` == the parent's id again (an
explicit, purpose-built, redundant field). Verified across **1854 of 1862 (99.6%)** subagent-tagged session
files sampled across every date 07/01–07/16 — this is a stable, cross-version, cross-date pattern, not new.
(The 8 exceptions — including the exact file `_codex_fixture_builders.py`'s own docstring cites as its
grounding — are `session_id==id`/no-`parent_thread_id` outliers, a small persistent minority in every
date/version bucket; I could not determine what makes them different. Flagged in Constraints.)

**OLD shape (`multi_agent_v1`) — additional, exact fields, directly verified:**
Child `rollout-2026-07-16T00-26-29-019f692d-121d-7802-80fa-b9a0a4cc39b9.jsonl` (the real child of the
Carver/explorer dispatch quoted in Q2):
```
session_id: 019f692a-c0ad-75c3-bd81-2d2f6fa31f9d   (== parent's own id)
id:         019f692d-121d-7802-80fa-b9a0a4cc39b9   (own distinct identity)
parent_thread_id: 019f692a-c0ad-75c3-bd81-2d2f6fa31f9d
agent_nickname: Carver     <- EXACTLY equals the parent's output "nickname":"Carver"
agent_role: explorer       <- EXACTLY equals the parent's call arguments "agent_type":"explorer"
```
So: output's `agent_id` == child's own `id`; output's `nickname` == child's own `agent_nickname`; call's
`agent_type` == child's own `agent_role`. Three independently-matching fields, directly confirmed (not
inferred) — this closes a gap the sibling `agent-id` brief's own honesty bar explicitly left open (it could
only prove agent_id/child-identity equivalence for `SubagentStop`, via one captured fixture; it explicitly
flagged PreToolUse-time equivalence as an unverified structural inference in its own `not_found` section).

**NEW shape (`collaboration`) — additional, exact field, directly verified 14/14, not anecdotal:** the
parent's output only ever carries `{"task_name":"/root/<name>"}` — no id, no nickname at all. I found the
child transcript matching the `framework_gap_research` dispatch
(`rollout-2026-07-15T22-15-21-019f68b5-0637-7133-bfb8-926cfa48701d.jsonl`) and its own `session_meta` reads:
```
session_id: 019f68b3-acea-7540-8466-b7f96524e784   (== parent's own id)
id:         019f68b5-0637-7133-bfb8-926cfa48701d   (own distinct identity)
forked_from_id: 019f68b3-acea-7540-8466-b7f96524e784
agent_path: /root/framework_gap_research           <- EXACTLY equals the parent output's "task_name" value
agent_nickname: Descartes
```
I then systematically extracted **all 14** `spawn_agent` calls in that one parent file (task_name in, task_name
echo out) and matched each to its real, temporally-adjacent child, checking `child.agent_path ==
call_output.task_name`: **14/14 matched exactly**, zero exceptions.

**A load-bearing, already-shipped bug this confirms, independent of shape/version:**
`codex_transcript_adapter.py::_find_child_verdict()` (lines 219-272) hard-codes its matching rule as
`session_meta.payload.session_id == agent_id` (docstring line 221, implementation line 249). Per everything
above, **this comparison can never succeed, for either shape, on real data** — a child's own `session_id` is
always its PARENT's id (never its own), while the target `agent_id` (from a OLD-shape output) is that
specific child's OWN id. Comparing "any child's parent-id" to "one specific child's own id" is comparing two
values that can never be equal by construction (a UUID cannot equal a different UUID). This is a categorical
field-choice error baked into the existing shipped code, not merely a staleness issue that a new-shape
branch would fix — it needs the correlating field flipped to `payload.id`/`parent_thread_id` (OLD shape) or
`payload.agent_path` (NEW shape), regardless of what else changes.

## Q5 — Backward compatibility: the OLD shape is NOT retired; it is being produced right now, on a brand-new session

**Answer, directly confirmed, not inferred:** I checked the OLD-shape 07/16 session
(`019f692a-c0ad-75c3-bd81-2d2f6fa31f9d`) for whether it might just be an old, long-resumed thread that
predates some cutover. It is not: `session_meta.session_id == id` and `thread_source: "user"`, created fresh
at `2026-07-16T04:23:57Z` — i.e., a **genuinely brand-new, top-level Codex Desktop session, started today**,
on `cli_version 0.144.2` (the exact same client version that, on this same machine, on the same day, also
produces `collaboration`/v2-shaped dispatches in other sessions). Two minutes after creation, its first
`spawn_agent` call used the OLD `multi_agent_v1`/`agent_type` shape with a fully plaintext message.

**A correct fix must handle both shapes concurrently, indefinitely — not "old vs new" as a migration, but
"both, per-session, ongoing."** There is no reliable client-version or date gate that predicts which shape a
given real session will use. I could not determine the mechanism that decides this (feature flag, A/B
rollout bucket, per-workspace/per-agent-role toggle, or a user-visible setting) — flagged honestly in
`not_found` below; it is genuinely open, not something I found and I am withholding, and no OpenAI
changelog/release-note entry I found explains it either.

## Q6 — Scope completeness: the 6-call-site list is confirmed and correctly scoped; 2 additional files are confirmed out-of-scope; test-fixture routing is split

**`_dispatch_view()`** (`hooks/pre_tool_use_oga_guard.py:23-40`), read directly:
```python
def _dispatch_view(raw_name, raw_input):
    if raw_name == "spawn_agent" and isinstance(raw_input, dict):
        message = str(raw_input.get("message", "") or "")
        agent_type = str(raw_input.get("agent_type", "") or "")
        return "Agent", {"description": "", "prompt": message, "subagent_type": agent_type}
    return raw_name, raw_input if isinstance(raw_input, dict) else {}
```
Confirmed OLD-shape-only. For a real `collaboration`-shaped live call, `agent_type` is absent (key doesn't
exist in that shape at all) so `subagent_type` silently resolves to `""`; `message` IS present under the same
key name in both shapes, so `prompt` would receive the Fernet-encrypted ciphertext blob, live, at PreToolUse
time. **This is in-scope and more urgent than the adapter/test-staleness framing suggests: it is LIVE code
executing on every real PreToolUse call today**, not post-hoc transcript parsing — a real `collaboration`
dispatch right now would already be feeding an empty `subagent_type` and ciphertext `prompt` into the
downstream `dispatch_check_presence`/repo-health/spec-bound-credit gates this file's own comment says consume
`_dispatch_view`'s output.

Does `codex-pretooluse-agent-id-caller-identity-2026-07-16.md`'s "specific regression" section already cover
this? **Yes, but only partially.** Its Answer Part 3 explicitly names `_dispatch_view()` and states its
conclusion as: the normalizer maps `spawn_agent`→`Agent`-shape, but that output "is consumed only by the
dispatch-gating branches... never by the in-flight collector, which reads raw transcript event content
directly." That conclusion is about **who consumes** `_dispatch_view`'s output (three specific gates, not the
in-flight fallback) — it does not check, and does not claim to check, whether `_dispatch_view` itself handles
the `collaboration`/v2 shape. That specific question was unexamined by either sibling doc; my direct code
read above is the first confirmation that `_dispatch_view` itself is OLD-shape-only.

**`hooks/subagent_stop_gate.py`** (lines 100-109, the "Codex SubagentStop payloads include both the parent
transcript_path and agent_transcript_path" comment): read directly + grepped the whole file for
`spawn_agent`/`agent_type`/`_VERIFIER_DETECT`/`VERIFIER_DETECT`/`codex_transcript_adapter` — **zero hits, all
four**. This comment is about **which transcript file to read** (`agent_transcript_path` vs
`transcript_path`, both fields already supplied by the Codex hook payload itself), not about parsing
`spawn_agent`'s own call/output shape at all. **Confirmed out of scope** for this specific staleness issue.

**`hooks/spec_bound_verifier_credit.py`** (line 545, the "Codex-adapter-produced records" comment): read
directly + grepped the whole file for `extract_spec_credit_records`/`codex_transcript_adapter`/`import.*codex`
— **zero hits, all three**. This module has no Codex-awareness of its own; it operates purely on an
already-normalized `records` list built by a caller, and the line-545 comment only acknowledges that some
records in that list might have no `"synthetic"` key (because they came from the adapter) without doing any
Codex-specific parsing itself. **Confirmed out of scope.** The actual glue is `hooks/loop_stop_guard.py`
(line 67 `import spec_bound_verifier_credit as _spec_credit`; lines 82-92 import `extract_spec_credit_records`
as `_codex_extract_spec_credit_records` from the adapter, with a `return []` fallback stub if the import
fails; line 186 `_TURN_RECORDS = _codex_extract_spec_credit_records(tpath)` when Codex is detected) —
`loop_stop_guard.py` itself does no independent shape parsing either; it is a pure wiring/glue site that
plumbs the adapter's (stale) output through to the (shape-agnostic) credit-gate functions. Naming it here for
completeness of the data-flow picture, not as a 7th call site needing its own separate fix.

**`micro_step_gates.py::_codex_thrash_past_green`** (function starts line 265; relevant body lines 296-314):
confirmed exactly as briefed, with one refinement. Its underlying function-call *extraction* IS shared/
adapter-routed — `_codex_extract_function_calls` (used at line 297) is a plain import-alias of
`codex_transcript_adapter.extract_function_calls` (see `micro_step_gates.py:40-49`; the local `def
_codex_extract_function_calls(...): return []` at line 48 is only the except-branch fallback if that import
fails), and that shared extractor is itself shape-agnostic (it just structurally pairs
function_call+function_call_output regardless of the args/output key names). But the *semantic
interpretation* — line 305 `agent_type = args.get("agent_type")`, line 306 `message = args.get("message")`,
lines 307-308 `if agent_type in _CODEX_WORKER_TYPES or (... _CODER_PAT.search(message.lower()))` — is
independently, locally re-derived, confirmed a genuinely separate duplication of OLD-shape-only logic, not
routed through any shared classifier. `_CODEX_WORKER_TYPES = ("worker",)` (line 262) is a single OLD-shape
`agent_type` vocabulary value, structurally unreachable for a real `collaboration` call (no `agent_type` key
exists in that shape at all, so this branch of the `or` can never fire for a v2 dispatch, and the `message`
branch can't fire either per Q3). Confirmed in scope exactly as briefed.

**Test-file fixture routing** (grepped all four): `test_codex_transcript_adapter.py` (6 calls),
`test_codex_parity_gates.py` (4 calls), and `test_loop_stop_guard.py` (5 calls) **all** route through
`_codex_fixture_builders.py::codex_spawn_agent()` — meaning all three automatically inherit whatever shape
the shared builder hardcodes (currently OLD-shape-only), by construction, with zero inline duplication.
`test_pre_tool_use_oga_guard.py` **does not** import the shared fixture builder at all (0 references) — it
hand-rolls its own inline fixtures directly (14 literal `"agent_type"` occurrences, 12 literal `"agent_id"`
occurrences). **This means fixing `_codex_fixture_builders.py` alone will not extend this file's own
fixtures** — it has independent, separately-authored OLD-shape-only fixture code that would need its own
separate update if new-shape test coverage is wanted there too.

## Additional finding beyond the dispatch's own hypotheses — `wait_agent`'s wire shape, not just `spawn_agent`'s

The dispatch's own top-line task explicitly named both `spawn_agent` **and** `wait_agent`. I ground-truthed
`wait_agent` directly and found something more severe than a shape rename:

**OLD shape (`multi_agent_v1`)** — `wait_agent` takes an explicit target list and returns per-agent text:
```json
{"arguments":"{\"targets\":[\"019f480d-8083-7cc3-916f-e7bf2873f27e\",\"019f480d-e233-7e23-a440-29d0cbe2637e\"],\"timeout_ms\":600000}"}
{"output":"{\"status\":{\"019f480d-e233-7e23-a440-29d0cbe2637e\":{\"completed\":\"Blocked by sandbox during branch creation...\"}},\"timed_out\":false}"}
```
This matches exactly what `codex_transcript_adapter.py:480-497` and `_codex_fixture_builders.py::codex_wait_agent()`'s
docstring both assume (`status` dict keyed by `agent_id`, each value `{"completed": "<text>"}`).

**NEW shape (`collaboration`)** — I checked **every one of the 69 `wait_agent` calls** in the same 14-dispatch
parent transcript used above. **All 69, with zero exceptions**, look like this:
```json
{"arguments":"{\"timeout_ms\":30000}"}
{"output":"{\"message\":\"Wait completed.\",\"timed_out\":false}"}
```
or `{"message":"Wait timed out.","timed_out":true}`. **No `targets` array in any call. No `status` dict, no
per-agent key, no completion text, in any output — 69/69.** This is a materially different, more severe fact
than a field rename: under the `collaboration` architecture, `wait_agent` structurally cannot deliver a
sub-agent's result text through this codebase's existing extraction logic (`codex_transcript_adapter.py:480-483`'s
`status.items()` loop finds `status` absent and produces zero records for every v2 `wait_agent` call, not
just mis-shaped ones). Combined with Q4's finding that `_find_child_verdict()`'s own matching key is wrong
for both shapes, this means: **for the NEW shape, neither of this codebase's existing two channels
(wait_agent output, nor the child-transcript fallback as currently keyed) can deliver a sub-agent's result
today** — the child-transcript route (keyed correctly, by `agent_path`/`task_name`, per Q4) is not an
optional nicety for v2, it would need to be the *only* viable path. I looked for a plausible alternative
channel (an available-but-possibly-unused `read_thread` MCP-style tool is present in the same session's
`dynamic_tools` schema, described as "Read recent status and turn summaries for one Codex thread without
opening it") but found **zero actual `read_thread` function_call invocations** in the transcript checked —
so I cannot confirm this is the real mechanism Codex Desktop's own UI uses internally; flagged as an unverified
lead, not a finding, in `not_found` below.

## Sources

- `codex --version` (direct Bash invocation, 2026-07-16) → `codex-cli 0.41.0`
- `brew info codex` / `brew list --versions codex` / `ls /opt/homebrew/Cellar/codex/` (direct Bash, 2026-07-16)
  → `codex: stable 0.41.0`, homepage `https://github.com/openai/codex`, `Installed (on request)`; single
  Cellar entry `0.41.0` dated `Sep 25 2025`
- [`https://github.com/openai/codex`](https://github.com/openai/codex) (fetched live 2026-07-16) — README
  distinguishes Codex CLI / Codex App / Codex Web / IDE integrations; Apache-2.0 license
- [`https://github.com/openai/codex/releases`](https://github.com/openai/codex/releases) (fetched live
  2026-07-16) — current tags `0.144.4`, `0.144.5`, `0.145.0-alpha.12`–`alpha.16`
- [`https://learn.chatgpt.com/docs/changelog?type=codex-app`](https://learn.chatgpt.com/docs/changelog?type=codex-app)
  (redirected from `developers.openai.com/codex/changelog?type=codex-app`, fetched live 2026-07-16) —
  "2026-07-09 Codex joins the ChatGPT desktop app"; "2026-07-08 Codex CLI 0.143.0"; "Namespace multi-agent v2
  tools under collaboration" (#29067)
- WebSearch: `openai/codex` release history cross-check (`rust-v0.141.0` tag confirmed; no `0.41.0` tag
  visible in current listing, consistent with an old point release)
- `<HOME>/.codex/sessions/2026/07/{01,02,07,08,09,10,11,12,13,14,15,16}/*.jsonl` (1935 real
  files, ~3.4GB, this machine, read live 2026-07-16) — full `session_meta` scan (all 1935 files' line 0),
  targeted `spawn_agent`/`wait_agent` grep+parse scan (89 files matched, 1689-1692 calls parsed), full
  parent/child `session_meta` cross-tab (1862 subagent-tagged files)
- `~/.codex/sessions/2026/07/07/rollout-2026-07-07T21-12-59-019f3f49-0b4b-7853-aa99-a0c9ab31ac01.jsonl` — the
  one real `originator:"codex_cli_rs"`/`cli_version:"0.41.0"` file, exact match to local `codex --version`
- `~/.codex/sessions/2026/07/09/rollout-2026-07-09T14-03-17-019f480c-5c61-7b53-8b62-25f48e47cefb.jsonl` — the
  exact file `_codex_fixture_builders.py`'s docstring cites; verbatim spawn_agent (line 18) + output (line 19)
  + wait_agent (line 29) + output (line 30) quoted above; full session_meta read (line 0): `session_id==id`,
  no `parent_thread_id` — an outlier within its own date/version bucket (199 sibling files same date+version
  DO show `parent_thread_id`/`session_id!=id`)
- `~/.codex/sessions/2026/07/16/rollout-2026-07-16T00-23-57-019f692a-c0ad-75c3-bd81-2d2f6fa31f9d.jsonl` —
  brand-new top-level session created today; verbatim OLD-shape spawn_agent (line 116) + output (line 117) +
  wait_agent (line 161) + output (line 162) quoted above
- `~/.codex/sessions/2026/07/16/rollout-2026-07-16T00-26-29-019f692d-121d-7802-80fa-b9a0a4cc39b9.jsonl` — real
  child of the above; full session_meta read, `agent_nickname:"Carver"`/`agent_role:"explorer"` matched
  exactly against the parent's output
- `~/.codex/sessions/2026/07/15/rollout-2026-07-15T22-13-53-019f68b3-acea-7540-8466-b7f96524e784.jsonl` — the
  same NEW-shape parent transcript the sibling `session-id` brief used; verbatim NEW-shape spawn_agent (line
  35) + output (line 37) quoted above; all 14 spawn_agent calls + all 69 wait_agent calls in this file
  extracted and tabulated; `read_thread` tool-schema text present (in `dynamic_tools`) but zero actual
  `read_thread` function_call invocations found
- `~/.codex/sessions/2026/07/15/rollout-2026-07-15T22-15-21-019f68b5-0637-7133-bfb8-926cfa48701d.jsonl` — real
  child of the `framework_gap_research` dispatch; full session_meta read, `agent_path:"/root/framework_gap_research"`
  matched exactly against the parent output's `task_name`
- `hooks/pre_tool_use_oga_guard.py:1-40` — `_dispatch_view()`, read directly, quoted verbatim above
- `hooks/codex_transcript_adapter.py:1-119` (`_detect_runtime`), `:219-272` (`_find_child_verdict`, docstring
  line 221, implementation line 249), `:279-363` (`extract_verifier_dispatches`, line 334 message-regex, line
  342 `agent_id`, line 346 `agent_type`), `:377-427` (`extract_function_calls`, shape-agnostic), `:430-503`
  (`extract_spec_credit_records`, line 459 `agent_id`, line 463 `agent_type`, lines 480-483 `wait_agent`
  `status.items()` loop) — all read directly
- `hooks/_codex_fixture_builders.py:96-169` — module docstring, `codex_session_meta` (default
  `cli_version="0.144.0-alpha.4"`), `codex_function_call` (default `namespace="multi_agent_v1"`),
  `codex_spawn_agent` (hardcoded `{agent_type,message}` in / `{agent_id,nickname}` out), `codex_wait_agent`
  (lines 172+, `status: {agent_id: {"completed": ...}}`) — all read directly
- `hooks/micro_step_gates.py:30-49` (import-alias block for `_codex_extract_function_calls`), `:262`
  (`_CODEX_WORKER_TYPES = ("worker",)`), `:265-314` (`_codex_thrash_past_green`, lines 296-314 quoted) — read
  directly
- `hooks/subagent_stop_gate.py:70-130` — read directly; grepped whole file for
  `spawn_agent`/`agent_type`/`_VERIFIER_DETECT`/`codex_transcript_adapter`: zero hits
- `hooks/spec_bound_verifier_credit.py:520-580` — read directly; grepped whole file for
  `extract_spec_credit_records`/`codex_transcript_adapter`/`import.*codex`: zero hits
- `hooks/loop_stop_guard.py:60-95,180-190` — read directly; confirms this file (not
  `spec_bound_verifier_credit.py`) is the actual glue calling `extract_spec_credit_records`
- `hooks/test_codex_transcript_adapter.py`, `hooks/test_codex_parity_gates.py`, `hooks/test_loop_stop_guard.py`,
  `hooks/test_pre_tool_use_oga_guard.py` — grepped for `_codex_fixture_builders` import, `codex_spawn_agent()`
  call count, inline `"agent_type"`/`"agent_id"`/`"task_name"`/`"fork_turns"` literals (counts quoted above)

## Constraints

- **`namespace` (a per-function_call field) and `multi_agent_version` (a per-session_meta field) are
  different fields that happen to correlate perfectly when both are present** — do not conflate them in a
  fix. `namespace` is the one that is always present on every real spawn_agent/wait_agent call and is what I
  used as the primary, always-available discriminator throughout this brief. `multi_agent_version` is a
  useful corroborating signal when present but is frequently absent even on unambiguous sessions.
- **The 8/1862 (~0.4%) parent/child session_meta outliers** (same_id=True, no `parent_thread_id`) were found
  in every date/version bucket sampled but not explained — I did not find a structural distinguishing feature
  beyond "small persistent minority." Not fully investigated further given time budget; flagged rather than
  silently normalized away.
- **The `read_thread` MCP-tool lead (in the `wait_agent` finding) is unverified** — its schema text is present
  in the session but I found zero actual invocations in the one transcript checked. I did not check other
  transcripts for `read_thread` usage; this is a real gap, not a claim.
- **Version-pinned, but now doubly-confirmed stable across a wide window:** every empirical finding above is
  drawn from real transcripts dated 2026-07-01 through 2026-07-16 on this one machine (`cli_version` ranging
  `0.142.5` through `0.144.2`, `originator: "Codex Desktop"` for all but one file). Given hooks/multi-agent
  wire formats are an explicitly evolving Codex surface (per the sibling briefs' own findings), re-verify
  after any further Codex Desktop update — but note this is not a fragile one-day snapshot: the OLD shape's
  liveness was independently confirmed at the *start* of the observable data (07/01) and *today* (07/16),
  15 days apart, with the NEW shape overlapping it for at least the final 4 days (07/13-07/16) observed so
  far.
- **I did not audit every consumer of `extract_verifier_dispatches`/`extract_spec_credit_records` beyond the
  specific files the dispatch named** (e.g., I did not re-audit `loop_stop_guard.py`'s OWN, larger,
  Claude-Code-shaped detection logic for any independent Codex-shape assumptions beyond the two import sites
  quoted). The scope-completeness check above answers exactly the files/questions the dispatch asked about;
  a fuller sweep of the whole `hooks/` tree for any other `"agent_type"`/`"agent_id"` literal was not
  performed (out of scope for this brief; a grep-sweep would be cheap follow-up if wanted).

## not_found

- **Why a given brand-new session gets the OLD vs. NEW shape** — no feature-flag/config file, per-workspace
  setting, or user-visible toggle was found that predicts this. Both shapes are demonstrably live,
  concurrently, today, on the same client version, but the selection mechanism is invisible from the
  transcript data and hook payloads available to this Researcher. A future check would need either an
  OpenAI-side changelog entry naming a staged rollout percentage, or direct correlation against Codex
  Desktop's own local app-settings/preferences file (not checked here — out of the explicitly-authorized
  scope of `~/.codex/sessions/` and this repo).
- **The real, current mechanism (if any) Codex Desktop's own UI uses to surface a sub-agent's result to the
  user, given `wait_agent`'s NEW-shape output carries no completion text** — not established. `read_thread`
  is a plausible, schema-available candidate but zero real invocations were found in the one transcript
  checked; this needs either a wider search across more transcripts or is simply resolved client-side without
  ever showing up as an externally-visible tool call at all (in which case this repo's hooks have no
  observable channel to it regardless, and the child-transcript route is the only option by necessity, not
  by choice).
- **Whether `0.41.0` is a genuine, much-older tag of the exact same `openai/codex` repository, or something
  Homebrew's formula pulled from a differently-versioned source snapshot** — I found strong, consistent
  circumstantial evidence (the formula's own homepage field, the shared semver format, the overlapping
  release-train dates for 0.143.x/0.144.x) but did not locate the literal `0.41.0` tag itself in the
  repository's history via the tools available to me (WebFetch/WebSearch on the releases page surfaces only
  recent tags). I am confident in the practical conclusion (same project, stale local install) but flag the
  specific tag-history lookup as unconfirmed at that level of precision.
