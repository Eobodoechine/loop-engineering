# Domain brief — the exact `task_complete`-style event shape and timestamp availability in a real Codex sub-agent's own child transcript

**Mode:** D (domain research for a build). **Build:** `fix/oga-guard-codex-worker-identity`
(`loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md`) — the Codex-support
design for `hooks/pre_tool_use_oga_guard.py`'s "Exact worker identity guard"
(`H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`). **Follow-up to (same investigation chain, same
methodology):** `research/codex-pretooluse-agent-id-caller-identity-2026-07-16.md`,
`research/codex-pretooluse-session-id-caller-identity-2026-07-16.md` (Part 2 point 2 of the latter
first surfaced that real child transcripts contain `event_msg` entries wrapping
`task_started`/`task_complete`/`agent_message`, but did not drill into the exact nesting/field
shape — that gap is what this brief closes). **Date:** 2026-07-16. **Researcher scope note:** all
reads/greps done directly, no sub-agent dispatched. Reading the specific real Codex session
transcript files named below was explicitly authorized by this dispatch's own text ("the 4 child
transcripts under `~/.codex/sessions/2026/07/16/`... and the parent... rollout-2026-07-15T22-13-53-...").
Per the prior briefs' precedent and the Researcher role's data-access-scope discipline, I read
**only** those 5 already-named files (the same 4 children + 1 parent already opened earlier in this
chain) — I did not open any of the ~150 other files in that directory (confirmed present via a
filename-only `ls`, content not read) even though the dispatch's phrasing ("if findable, one that
might represent a still-in-progress dispatch") invited looking further; see `not_found` for why I
stayed inside the named set instead of expanding scope.

**A live misfire happened again during this research, worth stating up front (third occurrence in
this chain).** My own `Write` call (writing my analysis script to my own scratchpad) was blocked by
the exact mechanism under study: `[OGA GUARD] Write('analyze_codex_transcripts.py') blocked...
Identity check failed: top-level agent_id does not match an active same-session worker.` Per the
guard's own printed instructions and the prior briefs' precedent, I switched to Bash (not gated by
`WORKER_TOOLS`) for all scratch-file writes and continued without dispatching another sub-agent.
Reported as corroborating evidence, not hearsay.

## Question

1. For a real Codex sub-agent's own child transcript, what is the EXACT top-level shape of an
   `event_msg` entry, and specifically of a `task_complete`-shaped one? Does it reliably appear as
   the LAST (or near-last) entry in a transcript known to be fully finished, versus one that might
   still be in progress?
2. Does `session_meta` (or any other event type — `function_call`, `event_msg`, etc.) in these
   transcripts carry a timestamp field usable for a staleness comparison? Exact key names and real
   values.
3. Is "does this child transcript contain a `task_complete`-shaped event" a usable "is this dispatch
   retired" signal, analogous to Claude Code's own retirement check? Is a wall-clock timestamp
   available, or is an event-count fallback (like `STALE_EVENT_FALLBACK=400`) the only option?
4. Say plainly if the evidence is inconclusive anywhere.

## Answer

### Part 1 — Exact shape confirmed byte-for-byte; `task_complete` is the literal LAST line in all 4 real, finished child transcripts

**Every line in every child transcript (100%, not a sample) is wrapped in an identical 3-key
envelope: `{"timestamp": <ISO-8601 string>, "type": <string>, "payload": {...}}`.** For `event_msg`
rows, `payload.type` names the inner event. This exactly matches the shape hypothesized in the
dispatch — confirmed directly, not inferred.

**Real, raw `task_started` (always the file's line-index 1, immediately after `session_meta` at line
0), from `rollout-2026-07-16T00-45-17-019f693e-4ade-72e0-b381-aebfbca4d849.jsonl:1`:**
```json
{"timestamp": "2026-07-16T04:45:18.241Z", "type": "event_msg", "payload": {"type": "task_started", "turn_id": "019f693e-4bbb-7d50-97ad-722a7cb4ab63", "started_at": 1784177118, "model_context_window": 258400, "collaboration_mode_kind": "default"}}
```

**Real, raw `task_complete` from the same file, line 217 — which is the file's LAST line (218 total
lines, 0-indexed 0-217):**
```json
{"timestamp": "2026-07-16T04:51:52.898Z", "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "019f693e-4bbb-7d50-97ad-722a7cb4ab63", "last_agent_message": "Implemented the focused regression tests only.\n\nChanged files:\n\n- hooks/test_spec_bound_verifier_credit.py\n- hooks/test_pre_tool_use_oga_guard.py\n\n[... full free-text completion report, ~1400 chars, quoting test names added and verification commands run — truncated here, not fabricated; every other field/value below is exact and complete ...]", "completed_at": 1784177512, "duration_ms": 394744, "time_to_first_token_ms": 6323}}
```

**This is a clean 4/4 result across every real child transcript in the authorized set — `task_complete`
is the literal terminal line, not merely "near the end," in every one:**

| child file (basename) | total lines | `task_started` index | `task_complete` index | last line index | is `task_complete` == last line? |
|---|---|---|---|---|---|
| `...00-45-17-019f693e...849.jsonl` | 218 | 1 | 217 | 217 | YES |
| `...00-47-08-019f693f...426.jsonl` | 206 | 1 | 205 | 205 | YES |
| `...00-52-34-019f6944...530.jsonl` | 299 | 1 | 298 | 298 | YES |
| `...01-03-43-019f694f...f0.jsonl` | 322 | 1 | 321 | 321 | YES |

`task_started` and `task_complete` are paired 1:1 via a shared `payload.turn_id` (confirmed identical
string on both ends in all 4 files — e.g. file 1's pair both carry `turn_id:
"019f693e-4bbb-7d50-97ad-722a7cb4ab63"`), and all 4 files have exactly one of each (single-turn
dispatches — `session_meta`/`world_state`/`turn_context` each also appear exactly once per file).

**Internal-consistency cross-check (not just a schema match — the numbers agree with each other):**
`started_at`(1784177118) → `date -u -r` → `2026-07-16T04:45:18Z`, matching the `task_started`
wrapper's own `"timestamp":"2026-07-16T04:45:18.241Z"` to the second. `completed_at`(1784177512) →
`2026-07-16T04:51:52Z`, matching the `task_complete` wrapper's own `"timestamp":"2026-07-16T04:51:52.898Z"`
to the second. `completed_at - started_at = 394` seconds vs. `duration_ms=394744` (394.744s) — the
integer epoch fields round to whole seconds; `duration_ms` is the sub-second-precision figure. Three
independently-arithmetic-checked pairs (this one plus two more below) all agree — this is measured
wall-clock data, not a placeholder or copy-pasted constant.

**Is there a still-in-progress example to contrast against?** No — not within the authorized file
set, and I did not expand scope to manufacture one (see `not_found`). All 4 children's own mtimes
(`00:51`, `00:56`, `01:01`, `01:14` EDT) are hours stale relative to when this check ran
(`03:29:27 EDT` — confirmed via `date` at research time); none was still growing. This is itself
informative: the Claude-Code-side test this brief's dispatch cites
(`hooks/test_pre_tool_use_oga_guard.py:2637-2671`) synthesizes staleness with `stale_ts = time.time()
- (2 * 60 * 60)` — a 2-hour-old timestamp. These real dispatches are independently sitting in almost
exactly that same "2+ hours old" zone right now, which is a nice real-world echo of the test's own
synthetic value, though it does not by itself prove the "still in progress" half of the question.

**A genuinely relevant, additional real finding (found while establishing the above, not asked for
directly but directly load-bearing for Part 3): `task_complete` is not the only real terminal
`event_msg` shape.** The (also-authorized) parent transcript — a much longer, multi-turn thread —
has 4 `task_started` events but only 3 `task_complete` events. The missing pairing is explained by a
second, distinct terminal shape, `turn_aborted`, found at `rollout-2026-07-15T22-13-53-...:453`:
```json
{"timestamp": "2026-07-16T03:46:52.052Z", "type": "event_msg", "payload": {"type": "turn_aborted", "turn_id": "019f6908-b841-7ad0-8b7d-1d981053b296", "reason": "interrupted", "completed_at": 1784173612, "duration_ms": 4877}}
```
This `turn_id` matches exactly the `task_started` at line 446
(`"turn_id": "019f6908-b841-7ad0-8b7d-1d981053b296"`), confirming `turn_aborted` closes a turn that
`task_started` opened, the same pairing mechanism as `task_complete`, just for an abnormal
(`"reason":"interrupted"`) instead of a normal end. `turn_aborted` carries `completed_at`+`duration_ms`
(both epoch/ms, same shape family as `task_complete`) but not `last_agent_message`/
`time_to_first_token_ms`. **Caveat, stated plainly:** I did not find `turn_aborted` inside any of
the 4 CHILD (subagent-sourced) transcripts themselves — only inside the parent's own `"user"`-sourced
thread. Its applicability to a child transcript is a structural inference (child and parent threads
share an identical event schema — same `task_started`/`task_complete` shape observed identically in
both), not an independently re-confirmed child-transcript fact. A robust design should treat
`payload.type in {"task_complete", "turn_aborted"}` as terminal, not `task_complete` alone, or it
risks never retiring an aborted/interrupted child dispatch (the 60-minute staleness cap would still
eventually catch this as a backstop, but retirement should not depend on that alone).

### Part 2 — Timestamps: present on EVERY event, not just `session_meta`, plus dedicated epoch fields on the lifecycle events

**Every single line in all 4 child transcripts (218/218, 206/206, 299/299, 322/322 — a 100% count,
not a sample) carries a top-level `"timestamp"` key**, an ISO-8601 string with millisecond precision
and a trailing `"Z"` (e.g. `"2026-07-16T04:45:18.241Z"`), regardless of the line's `"type"`
(`session_meta`, `event_msg`, `response_item`, `world_state`, `turn_context`,
`inter_agent_communication_metadata` all carry it). Confirmed on non-`event_msg` types directly, not
just inferred from the count:

- `response_item`/`function_call` (`...00-45-17...849.jsonl:16`):
  `{"timestamp": "2026-07-16T04:45:35.966Z", "type": "response_item", "payload": {"type": "function_call", "name": "update_plan", ...}}`
- `response_item`/`custom_tool_call` (`...00-45-17...849.jsonl:134`):
  `{"timestamp": "2026-07-16T04:48:54.266Z", "type": "response_item", "payload": {"type": "custom_tool_call", "name": "apply_patch", ...}}`
- `response_item`/`custom_tool_call_output` (`...00-45-17...849.jsonl:136`):
  `{"timestamp": "2026-07-16T04:48:54.603Z", "type": "response_item", "payload": {"type": "custom_tool_call_output", ..., "internal_chat_message_metadata_passthrough": {"turn_id": "019f693e-4bbb-7d50-97ad-722a7cb4ab63"}}}`

**`session_meta` specifically carries TWO timestamp fields, not one** — the universal top-level
wrapper `"timestamp"`, and a second, nested `payload.timestamp` a few hundred milliseconds *earlier*
(the moment the thread object itself was created, versus the moment this log line was appended).
Example, `...00-45-17...849.jsonl:0`: top-level `"timestamp":"2026-07-16T04:45:18.241Z"` vs. nested
`"payload":{"timestamp":"2026-07-16T04:45:17.956Z", "session_id":"019f68b3-...", "id":"019f693e-...",
"parent_thread_id":"019f68b3-...", "thread_source":"subagent", ...}`.

**Dedicated epoch-integer fields on the lifecycle events themselves** (in addition to the wrapper's
ISO string): `task_started.payload.started_at` (e.g. `1784177118`), `task_complete.payload.completed_at`
+ `.duration_ms` + `.time_to_first_token_ms` (e.g. `1784177512` / `394744` / `6323`), and
`turn_aborted.payload.completed_at` + `.duration_ms` (e.g. `1784173612` / `4877`). All are Unix epoch
seconds (integers), confirmed by direct `date -u -r <epoch>` conversion matching the enclosing
wrapper's own ISO timestamp to the second (three independent pairs checked: file 1's
`task_started`/`task_complete`, and the parent's `turn_aborted`).

**Cross-file validation against an independent prior finding in this chain:** the prior brief
(`research/codex-pretooluse-session-id-caller-identity-2026-07-16.md`, Part 3) independently recorded,
from the PARENT transcript's own `spawn_agent` call at line 804, that the Coder sub-agent dispatch
that produced child file 3 (`...00-52-34-019f6944...530.jsonl`) was "dispatched at
`2026-07-16T04:52:34.271Z` UTC." That child file's OWN `session_meta` (opened fresh in this brief)
shows top-level `"timestamp":"2026-07-16T04:52:35.119Z"` and nested `payload.timestamp:
"2026-07-16T04:52:34.767Z"` — both within about one second of the parent's independently-recorded
dispatch instant. **A child's own `session_meta` timestamp is a faithful (sub-2-second-accurate),
independently-cross-validated proxy for its actual dispatch/creation time**, not merely a
self-consistent-but-meaningless value.

**One near-miss on the "time" substring search, reported for completeness/honesty:** `world_state`
events carry `payload.state.environments.timezone` (a string like `"America/New_York"`) and
`payload.realtime_active` (a bool). Neither is a comparable instant — they are environment
configuration, not a usable staleness input. Flagged so this isn't mistaken for a 5th timestamp
source.

**A related, real, negative finding on the PARENT side (adjacent to but not literally the child-
transcript question, included because it directly bears on whether the child's own file is the
*only* place a completion signal exists):** the parent transcript's own `event_msg` vocabulary
includes 28 `sub_agent_activity` events, all sharing the same keys — `{"type":"sub_agent_activity",
"event_id":..., "occurred_at_ms":<epoch-ms int>, "agent_thread_id":<child's own id>,
"agent_path":<task_name>, "kind":<string>}` — confirmed via `rollout-2026-07-15T22-13-53-...:753`
(`{"timestamp": "2026-07-16T04:45:18.140Z", ..., "payload": {"type": "sub_agent_activity",
"event_id": "call_NZIE8DSte5rulCy0Czfrjjhf", "occurred_at_ms": 1784177118139, "agent_thread_id":
"019f693e-4ade-72e0-b381-aebfbca4d849", "agent_path": "/root/test_writer_structural_guard", "kind":
"started"}}`, timestamped essentially identically to that same child's own `task_started.started_at`
above — another cross-file second-level match). **The full distinct `kind` value set across all 28
is `{"started": 14, "interacted": 9, "interrupted": 5}` — there is no `"completed"`/`"finished"`/`"done"`
kind anywhere in this real vocabulary.** The 14 `"started"` count matches exactly the 14 real
`spawn_agent` calls the prior brief found. **This means the parent's own transcript never echoes
back "child X finished" in an obviously-named way** — reinforcing that the child's own
`task_complete` (Part 1) is the primary, and on this evidence the only, direct completion signal
available; it is not redundant with something already visible parent-side.

### Part 3 — Yes, a usable retirement signal exists, directly in the same file the hook already reads; yes, a wall-clock timestamp exists too, so an event-count fallback is not the only option

**Retirement:** `payload.type in {"task_complete", "turn_aborted"}` inside `event_msg` is a real,
confirmed, structurally-terminal event — present as the literal last line in 4/4 finished child
transcripts (Part 1), paired via `turn_id` to the `task_started` that opened the same turn. The prior
brief in this chain (`research/codex-pretooluse-session-id-caller-identity-2026-07-16.md`, Part 2.1)
already established that for a genuine Codex sub-agent's own subsequent tool call, the PreToolUse
payload's `transcript_path` points at the CHILD's OWN separate file — **the exact file this brief's
Parts 1-2 analyzed.** That means a Codex-aware guard checking "has this dispatch already retired" can
look for a terminal `event_msg` **inside the very file it is already given**, with no separate
cross-file lookup needed — structurally simpler than Claude Code's own mechanism, where retirement is
inferred from a *later, separate* event in the calling session's own stream
(`hooks/pre_tool_use_oga_guard.py:787-794`, a `<tool-use-id>` tag inside a subsequent `role:"user"` or
`queue-operation` event). **One inference, stated plainly as such, not independently captured live:**
this only works because a still-genuinely-active child's own transcript, read AT THE MOMENT of one of
its own in-flight tool calls, cannot yet contain its own `task_complete`/`turn_aborted` (that event is
only appended once the turn ends — and if it already ended, a further tool call from that same turn
would be anomalous). I did not capture a live mid-run snapshot to directly observe this
(retrospective files only show the finished state); the inference is grounded in (a) real file-mtime
evidence that these files grow incrementally over the run's actual duration and stop growing exactly
when `task_complete` is written (file 1: created `00:45:17`, mtime stops at `00:51`, task_complete
timestamped `04:51:52.898Z` UTC = `00:51:52` EDT — matches), and (b) the strict one-`task_started`
per-turn / one-terminal-event-per-turn structure confirmed in both the child files and the parent.

**Staleness:** a real, usable, independently-cross-validated wall-clock timestamp exists
(`session_meta`'s own top-level `"timestamp"` or nested `payload.timestamp`, Part 2) — this is
**not** the "timestamps are absent" case the dispatch's own phrasing anticipated as the trigger for
an event-count-only fallback. The existing Claude Code `_is_stale()` function
(`hooks/pre_tool_use_oga_guard.py:803-820`) already parses exactly this shape without modification:
its ISO-8601 branch (`hooks/pre_tool_use_oga_guard.py:811-815`: `if s.endswith("Z"): s = s[:-1] +
"+00:00"` then `datetime.datetime.fromisoformat(s).timestamp()`) is built for precisely a
`"...Z"`-suffixed millisecond ISO string like every real value found here, and its numeric branch
(`isinstance(ts, (int, float))`) equally fits the epoch-integer `started_at`/`completed_at` fields.
A Codex adapter would only need to populate `info["timestamp"]` from `e.get("timestamp")` (or
`e["payload"]["timestamp"]`) read off the child's own `session_meta` line — no new parsing logic
required. `STALE_SECONDS = 60 * 60` (`hooks/pre_tool_use_oga_guard.py:665`) and
`STALE_EVENT_FALLBACK = 400` (`:666`) are the exact Claude-Code constants the dispatch's own
"analogous to" framing points at; nothing found here argues for different numbers, only for a
different *source* of the timestamp (child's own `session_meta` instead of the parent's dispatching
`Agent` tool_use event).

**Net:** both halves of an analogous mechanism are independently confirmed buildable from real data —
retirement via a terminal `event_msg` inside the child's own already-read file, and staleness via a
real, cross-validated timestamp on that same file's `session_meta` — with the existing `_is_stale()`
parsing logic already compatible with the exact string/int shapes found. An event-count fallback
(mirroring `STALE_EVENT_FALLBACK`) remains buildable as a defense-in-depth backstop (e.g., counting
lines from `session_meta` to "now" the same way `_is_stale()` already falls back today), but is not
strictly necessary here, unlike the framing in the dispatch's own question — timestamps are not
absent for Codex child transcripts.

### Part 4 — Explicit statement of what is NOT conclusively settled

The core ask (exact event shape; reliable terminal position; timestamp existence and usability) is
conclusively settled — 4/4 real files, byte-exact quotes, cross-validated arithmetic. Three specific
sub-points are explicitly not settled, stated plainly rather than glossed over:

1. **No genuinely still-in-progress child transcript was available to directly contrast against** a
   finished one, within the authorized file set (all 4 stopped growing hours before this check ran).
   I did not expand scope into the ~150 other files in the same directory to manufacture one (would
   have meant reading unrelated, unauthorized session content — see `not_found`).
2. **`turn_aborted` was not directly observed inside a real CHILD/subagent-sourced transcript** — only
   inside the parent's own `"user"`-sourced thread. Its applicability to children rests on the shared
   schema (structural inference), not an independently reconfirmed child-transcript instance.
3. **The "a still-active child's own file cannot yet contain its own terminal event" claim is a
   structural/logical inference from retrospective (post-hoc) file evidence** (mtime growth pattern,
   turn-bracket structure), not a live mid-run snapshot independently captured during this research.

## Sources (file:line / transcript:line for every claim above)

- `hooks/pre_tool_use_oga_guard.py:665-666` — `STALE_SECONDS = 60 * 60`, `STALE_EVENT_FALLBACK = 400`
- `hooks/pre_tool_use_oga_guard.py:683-687` — `_timestamp(e)`: `e.get("timestamp")` else `e["message"]["timestamp"]`
- `hooks/pre_tool_use_oga_guard.py:750-768` — `dispatched` collection loop, `"timestamp": _timestamp(e)` at line 764
- `hooks/pre_tool_use_oga_guard.py:787-794` — `retired` set via `TOOL_USE_ID_RE` scan of `role:"user"`/`queue-operation` events
- `hooks/pre_tool_use_oga_guard.py:803-820` — `_is_stale()`; ISO-8601-with-"Z" branch at 811-815, epoch numeric branch, event-count fallback at 820
- `hooks/pre_tool_use_oga_guard.py:823-838` — `in_flight_ids`, `payload_session_id`, `_same_session()`, `active_dispatches`
- `hooks/test_pre_tool_use_oga_guard.py:2637-2671` — `TestExactWorkerIdentityGuard.test_stale_retired_nested_and_cross_session_identity_deny`; `stale_ts = time.time() - (2 * 60 * 60)` at line 2638
- `hooks/test_pre_tool_use_oga_guard.py:2520-2550` — `_identity_dispatch_events()`, wiring `timestamp=`/`retired=` params into the fixture
- `hooks/test_pre_tool_use_oga_guard.py:45-89` — `_user_event`/`_assistant_tool_use`/`_notification_event`/`_queue_operation_event`/`_stop_hook_feedback_event`, confirming `e["timestamp"]` is the literal key the dispatch-side fixture sets (matches `_timestamp()`'s primary check)
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-45-17-019f693e-4ade-72e0-b381-aebfbca4d849.jsonl` — 218 lines; line 0 `session_meta` (both timestamp fields quoted above); line 1 `task_started` (quoted in full above); line 16 `function_call`/`update_plan`; line 134/136 `custom_tool_call`/`custom_tool_call_output`; line 217 `task_complete` (quoted in full above, the file's last line)
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-47-08-019f693f-fa33-7950-9a7d-ab8405458426.jsonl` — 206 lines; line 1 `task_started`; line 205 `task_complete` (last line), `completed_at=1784177792`, `duration_ms=563871`, `time_to_first_token_ms=8041`
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-52-34-019f6944-f508-7a41-9e3f-a46c2ac6d530.jsonl` — 299 lines; line 0 `session_meta` (`timestamp`/`payload.timestamp` cross-validated against the prior brief's independent parent-side dispatch-time finding); line 1 `task_started`; line 298 `task_complete` (last line), `completed_at=1784178110`, `duration_ms=555666`, `time_to_first_token_ms=8261`
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T01-03-43-019f694f-2b1a-7670-b516-66cf0cb053f0.jsonl` — 322 lines; line 1 `task_started`; line 321 `task_complete` (last line), `completed_at=1784178871`, `duration_ms=647059`, `time_to_first_token_ms=7034`
- `<HOME>/.codex/sessions/2026/07/15/rollout-2026-07-15T22-13-53-019f68b3-acea-7540-8466-b7f96524e784.jsonl` — 1152 lines (parent); `event_msg` inner-type counts: `task_started:4, task_complete:3, turn_aborted:1, sub_agent_activity:28, ...`; `task_started` indices `[1, 391, 446, 456]`; `task_complete` indices `[389, 444, 1151]` (1151 = the file's own last line); `turn_aborted` at line 453 (quoted in full above), `turn_id` matches `task_started` at line 446; `sub_agent_activity` at line 753 (quoted in full above) and 28 total, `kind` value counts `{"started": 14, "interacted": 9, "interrupted": 5}` (no "completed" kind found); line 0/447 (of 3 total) `session_meta` (`thread_source:"user"` both times, `parent_thread_id: None`)
- `research/codex-pretooluse-session-id-caller-identity-2026-07-16.md`, Part 1c and Part 3 — the prior brief's independently-recorded parent-side dispatch time for child file 3 (`"dispatched at 2026-07-16T04:52:34.271Z"`), cross-validated against this brief's own fresh read of that same child's `session_meta` timestamps
- `date -u -r 1784177118 "+%Y-%m-%dT%H:%M:%SZ"` → `2026-07-16T04:45:18Z`; `date -u -r 1784177512` → `2026-07-16T04:51:52Z`; `date -u -r 1784173612` → `2026-07-16T03:46:52Z` (run live, this research) — the three epoch/ISO cross-checks
- `ls -la` + `date` (run live, this research) — the 4 child files' mtimes (`00:51`/`00:56`/`01:01`/`01:14` EDT) versus "now" (`03:29:27 EDT`) confirming none was still growing at check time

## Constraints

- **Scope discipline, as in the prior briefs:** only the 5 already-named files (4 children + 1
  parent) were read for content. The parent directory's other ~150 files were listed by filename
  only (via `ls -la`, already run in this chain for a different purpose) and never opened — the
  dispatch's "if findable" phrasing was treated as inviting a search *within the already-authorized
  set*, not a license to open unrelated session content, per the Researcher role's data-access-scope
  rule.
- **Version-pinned finding, as in the prior briefs:** all shapes described are confirmed for real
  transcripts dated 2026-07-15/16 on this machine (`cli_version 0.144.2`, `"originator":"Codex
  Desktop"`, `multi_agent_version:"v2"` per session_meta). Re-verify after any Codex upgrade — the
  prior briefs already flagged this surface as evolving (the fixture-builder/adapter staleness found
  in the session-id brief's Part 4 is a concrete example of exactly this kind of drift already having
  happened once).
- **`last_agent_message` values are truncated in this brief's quotes** (they are long free-text
  completion reports, several hundred to ~1400 characters); every other field name and value in every
  quoted JSON object is exact and complete, not paraphrased.
- **The `turn_aborted`/`sub_agent_activity` findings (Part 1's bonus finding, Part 2's negative
  finding) are adjacent to, not squarely inside, the literal question asked** — included because they
  directly and concretely strengthen or qualify the Part 3 answer with hard evidence, not because
  they were the primary target of this brief.

## not_found

- No genuinely still-in-progress (actively growing) child transcript was available inside the
  authorized file set at the time of this check — all 4 had already finished, hours earlier. The
  "does a not-yet-retired dispatch's own file omit `task_complete`" claim is therefore a structural
  inference from retrospective evidence (file-growth/mtime pattern, turn-bracket structure), not a
  live-captured counterexample. A future check: capture a child transcript's own file mid-run (read it
  DURING an active dispatch, before it finishes) to directly confirm the absence of `task_complete`/
  `turn_aborted` at that point — this requires timing the read against a live dispatch, which was not
  available during this research window.
- `turn_aborted` was not observed inside any actual sub-agent (`thread_source:"subagent"`) transcript
  in this evidence set — only inside the parent's own `"user"`-sourced thread. I did not find a way to
  independently confirm it fires identically inside a child transcript without either waiting for a
  real one to occur (not controllable) or opening additional out-of-scope files that might contain
  one (declined, per scope discipline).
- I did not check whether `turn_aborted.payload.reason` has values other than `"interrupted"` (e.g. an
  error/timeout-specific reason) — only one real example was available.
- Whether Codex ever appends anything to a child's own transcript file AFTER its `task_complete`/
  `turn_aborted` line (e.g., a final flush/close marker) is not settled beyond "not observed in these
  4 files" — a small sample (4), though a consistent one.
