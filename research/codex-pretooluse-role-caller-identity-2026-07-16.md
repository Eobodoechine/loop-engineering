# Domain brief — does `agent_nickname`/`agent_path` (or any other real field) reliably indicate a genuine Codex sub-agent's ROLE, or is `task_name` text-heuristic matching the only option?

**Mode:** D (domain research for a build). **Build:** `fix/oga-guard-codex-worker-identity`
(`loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md`) — the fix for
`H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`'s Codex-worker regression. **Follow-up to (same
methodology, third in this chain):** `research/codex-pretooluse-agent-id-caller-identity-2026-07-16.md`
(agent_id), `research/codex-pretooluse-session-id-caller-identity-2026-07-16.md` (session_id). **Date:**
2026-07-16. **Researcher scope note:** all reads/greps done directly by me, no sub-agent dispatched.
Reading real Codex transcripts under `~/.codex/sessions/` was explicitly (re-)authorized by this
dispatch's own text ("Re-open the same real child transcripts you already read"), the same category of
access the two prior briefs in this chain already used and disclosed.

## Question

For a real, live Codex sub-agent dispatch, what field (if any) reliably indicates the dispatched
agent's ROLE (Coder / Test-writer / Researcher / Verifier / other)? Do `agent_nickname` and
`agent_path` (seen in real child transcripts' `session_meta` events but not detailed in the prior
brief's summary table) carry real role information, or is `task_name` (on the parent's own
`spawn_agent` call) the only usable signal — and if so, what happens when a `task_name` doesn't
contain a recognizable keyword?

## Answer — short version

**No structured field reliably carries role. `task_name` (via its exact duplicate, `agent_path`) is
the only place a role-like word ever appears, and it requires the same kind of text-heuristic
matching `_dispatch_role()` already does for Claude Code — with one previously-unknown, mechanically
confirmed defect: the existing regex, applied verbatim to real Codex `task_name` strings, misses
100% of them (14/14), including the literal task_name of the two live production-denied dispatches
from the prior brief, because Codex/this-project's snake_case naming uses `_` as a word separator and
Python's `\b` treats `_` as a word character. A trivial separator-normalization fix restores 5/5
correct write-capable classifications on the real sample — but the active spec's own drafted design
(Section D candidate (a), AC3, Section H) currently assumes a field literally named `agent_type`
carries role on the dispatch record itself. That field does not exist there. A field with that exact
name DOES exist elsewhere (the child's own subsequent PreToolUse hook payload), but it carries a
different, Codex-internal, closed vocabulary (`"default"`/`"explorer"`/`"worker"`) that can never
equal "coder"/"test-writer"/"researcher"/"verifier". This is caught here, before the build, so the
spec's three `agent_type`-based sections can be corrected before a Coder builds a
self-consistent-but-wrong fixture against them.**

---

## Part 1 — Full `session_meta` payload for the 4 known child transcripts (answers investigation #1)

Re-opened all 4 child files from the prior brief and printed the complete `session_meta.payload`
(only the large `base_instructions`/`instructions` prompt blobs elided — structural fields only,
matching this role's scope discipline):

| child file | `agent_nickname` | `agent_path` | `agent_role` (top-level, dup'd inside `source.subagent.thread_spawn`) | `multi_agent_version` |
|---|---|---|---|---|
| `rollout-2026-07-16T00-45-17-019f693e-4ade-72e0-b381-aebfbca4d849.jsonl` | `"Noether"` | `"/root/test_writer_structural_guard"` | `null` | `"v2"` |
| `rollout-2026-07-16T00-47-08-019f693f-fa33-7950-9a7d-ab8405458426.jsonl` | `"Bacon"` | `null` | `"worker"` | `"v1"` |
| `rollout-2026-07-16T00-52-34-019f6944-f508-7a41-9e3f-a46c2ac6d530.jsonl` | `"Hume"` | `"/root/coder_structural_guard"` | `null` | `"v2"` |
| `rollout-2026-07-16T01-03-43-019f694f-2b1a-7670-b516-66cf0cb053f0.jsonl` | `"Schrodinger"` | `"/root/test_writer_reconcile_broad_suite"` | `null` | `"v2"` |

**`agent_nickname` values do not look like role identifiers** — they are single first/last names of
historical scientists/philosophers ("Noether", "Bacon", "Hume", "Schrodinger"), not "coder"/"researcher"/
anything role-shaped. **`agent_path`, when non-null, is exactly `"/root/" + <task_name>`** — a direct
copy of the orchestrator's own dispatch-call argument, not independent information (proven exactly in
Part 2). **A second field, `agent_role`, exists in the same schema** (both at
`payload.agent_nickname`/`payload.agent_role` top-level and nested inside
`payload.source.subagent.thread_spawn`) but is `null` on every `agent_path`-populated ("v2") row and
takes the generic value `"worker"` on the one "v1" row in this 4-file sample — never a domain role
(full characterization in Part 3).

## Part 2 — Cross-reference against the parent's own `spawn_agent` `task_name` (answers investigation #2)

Extracted **all 14** real `spawn_agent` `function_call` entries from the parent transcript
(`<HOME>/.codex/sessions/2026/07/15/rollout-2026-07-15T22-13-53-019f68b3-acea-7540-8466-b7f96524e784.jsonl`,
0-indexed lines 35,41,151,251,516,583,620,674,725,752,804,880,960,1033 — confirmed these are
**0-indexed**, i.e. `sed`/1-indexed line = index+1, verified directly: 0-idx line 35 is a `type:"message"`
event; 0-idx line 36 is the actual `spawn_agent` `function_call`) and matched each dispatch timestamp
(UTC) against the corresponding child transcript filename (which encodes the same instant in local EDT)
found under `~/.codex/sessions/2026/07/16/`. **Full 9-way correlation, exact matches, zero exceptions:**

| `task_name` (parent `spawn_agent` arg) | dispatch ts (UTC) | matching child file (filename ts, EDT) | `agent_path` (child `session_meta`) | `agent_nickname` |
|---|---|---|---|---|
| `current_state_researcher` | `04:26:35.599Z` | `...T00-26-35-019f692d-2bbb...` | `/root/current_state_researcher` | Bernoulli |
| `plancheck_structural_guard_spec` | `04:29:26.096Z` | `...T00-29-26-019f692f-c5a9...` | `/root/plancheck_structural_guard_spec` | Lorentz |
| `plancheck_structural_guard_spec_bounded` | `04:32:00.864Z` | `...T00-32-01-019f6932-228f...` | `/root/plancheck_structural_guard_spec_bounded` | Volta |
| `plancheck_structural_guard_spec_round2` | `04:36:15.523Z` | `...T00-36-15-019f6936-047a...` | `/root/plancheck_structural_guard_spec_round2` | Aristotle |
| `plancheck_structural_guard_spec_round3` | `04:40:57.868Z` | `...T00-40-58-019f693a-53f5...` | `/root/plancheck_structural_guard_spec_round3` | Laplace |
| `test_writer_structural_guard` | `04:45:17.838Z` | `...T00-45-17-019f693e-4ade...` | `/root/test_writer_structural_guard` | Noether |
| `coder_structural_guard` | `04:52:34.271Z` | `...T00-52-34-019f6944-f508...` | `/root/coder_structural_guard` | Hume |
| `test_writer_reconcile_broad_suite` | `05:03:43.758Z` | `...T01-03-43-019f694f-2b1a...` | `/root/test_writer_reconcile_broad_suite` | Schrodinger |
| `test_writer_reconcile_adjacent_hooks` | `05:18:55.557Z` | `...T01-18-55-019f695d-14b4...` | `/root/test_writer_reconcile_adjacent_hooks` | Carver |
| `verifier_structural_guard_postbuild` | `05:30:22.726Z` | `...T01-30-22-019f6967-90d2...` | `/root/verifier_structural_guard_postbuild` | Boyle |

(The remaining 4 of the 14 — `framework_gap_research`, `independent_guard_audit`, `repair_plan_check`,
`bounded_plan_verifier` — dispatched before local midnight, so their child files live under
`.../2026/07/15/`, out of this dispatch's re-opened `2026/07/16/` set; not re-checked, not needed —
the 9-way match above already spans every target role: coder, test-writer (×3), researcher, verifier,
plus a 5th "plancheck" family (×4).)

**`agent_path` = `"/root/" + task_name`, byte-for-byte, 9/9, zero exceptions.** It is not independent
information — it is the same string the orchestrator already put in its own `spawn_agent` call,
wrapped in a fixed `/root/` prefix. **`agent_nickname` shows zero role correlation**: the *same* role
(test-writer) gets three *different* nicknames across three dispatches (Noether, Schrodinger, Carver),
and the *same* nickname ("Carver") is independently reused for a completely unrelated repo/role
elsewhere (see the 111-row scan below, row for `padsplit-cockpit`, `agent_role:"explorer"`) — the pool
is shared and reused without regard to task or role.

## Part 3 — `agent_role`/`agent_type`: a real field, but a different, Codex-internal, closed vocabulary — never a domain role

To characterize `agent_role` beyond the 4-file sample, I scanned **every** file under
`~/.codex/sessions/2026/07/16/` (111 files) for `session_meta` events with
`payload.thread_source=="subagent"` and printed `agent_nickname`/`agent_path`/`agent_role`/
`multi_agent_version`/`cwd`. Full result: `agent_role` takes **exactly four values across all 111
rows: `null`, `"default"`, `"explorer"`, `"worker"`** — never `"coder"`, `"test-writer"`/`"test_writer"`,
`"researcher"`, or `"verifier"`. The pattern is bimodal and mutually exclusive, not complementary:

- **`multi_agent_version:"v2"` rows** (this project's own `spawn_agent`-with-`task_name` convention):
  `agent_path` populated (task-name-shaped), `agent_role` **always `null`**. Seen only under
  `cwd=<HOME>/Claude/loop` in this sample.
- **`multi_agent_version:"v1"` rows** (a separate, Codex-native sub-agent mechanism — seen firing
  under `padsplit-cockpit`, `taxahead-connector-platform`, **and** the `loop` repo itself under a
  *different* parent session lineage, `019f698f-2472-...`, rows for nicknames Nash/Hegel/Boole/Maxwell/
  Galileo — proving `v1` isn't tied to a specific repo, it can fire in this same repo too): `agent_path`
  **always `null`**, `agent_role` populated from `{"default","explorer","worker"}`.

**A real, unredacted confirmation of the same vocabulary at the actual hook-payload level** (not just
inside transcript content): `hooks/fixtures/ac1_captured_codex_stop_stdin.json` — a genuinely captured
`SubagentStop` payload (2026-07-10) — has verbatim:
```json
"agent_id": "019f4eee-8924-76c2-999c-0d0b1f81fd59",
"agent_type": "explorer",
```
`"explorer"` is exactly one of the four generic values found in the 111-row `session_meta.agent_role`
scan — strong, concrete evidence that the hook-payload's top-level `agent_type` field and the
transcript's `session_meta.agent_role` field are the same underlying Codex concept, and that concept's
value space is a small, closed, **Codex-internal** set describing what kind of native Codex sub-agent
mechanism produced the call (default chat / autonomous explorer / autonomous worker) — structurally
incapable of ever equaling this project's own Coder/Test-writer/Researcher/Verifier labels.

**This `agent_type` key is also independently confirmed to exist on the live top-level hook stdin
payload for genuine Codex sub-agent `PreToolUse` calls** (not just inside transcript content): filtering
`~/.loop-gate/oga_guard_debug.jsonl` to real Codex rows (identical filter to both prior briefs: 1,098
rows) and grouping by `sorted(payload_keys)` yields exactly 3 distinct top-level key-sets:
1. `(cwd, hook_event_name, model, permission_mode, session_id, tool_input, tool_name, tool_use_id,
   transcript_path)` — no `turn_id` at all → Claude Code's shape.
2. `(agent_id, agent_type, cwd, hook_event_name, model, permission_mode, session_id, tool_input,
   tool_name, tool_use_id, transcript_path, turn_id)` — **1,056 rows**, exactly matching the prior
   brief's independently-derived "1,056 child rows" count → a genuine Codex **sub-agent's own** call.
3. `(cwd, hook_event_name, model, permission_mode, session_id, tool_input, tool_name, tool_use_id,
   transcript_path, turn_id)` — **42 rows**, exactly matching the prior brief's "42 own/root rows" →
   Codex's **root session's own** direct call (has `turn_id`, since that's PreToolUse-specific per the
   official docs quoted in the prior brief, but no `agent_id`/`agent_type` since it isn't itself a
   sub-agent).

So `agent_type` genuinely is present, structurally, on every real Codex sub-agent `PreToolUse` call —
it is not a fabrication of the fixture builder. **The problem is not that it's missing; it's that its
real value space is the wrong vocabulary for this project's role question**, and the debug log redacts
values (logs only key names), so this is confirmed by direct value for `SubagentStop` (the fixture
above) and by consistent, closed-vocabulary structural inference for `PreToolUse` (same field name,
same runtime, same 4-value ceiling observed everywhere else this concept appears) — see `not_found`
for the exact residual gap.

## Part 4 — `task_name` text-heuristic: the only usable signal, but the existing regex has a 100% miss rate on real Codex names (mechanically confirmed, not theorized)

Since `task_name` (via `agent_path`) is the only field carrying a role-shaped word at all, I tested
whether the file's own existing Claude-Code-oriented fallback, `_dispatch_role()`
(`hooks/pre_tool_use_oga_guard.py:728-747`), would actually work if pointed at these real strings.
Copied its exact regexes (`\btest[-_ ]writer\b`, `\bcoder\b`, `\bresearcher\b`, `\bverifier\b`) into a
standalone script and ran them against all 14 real `task_name` values extracted directly from the
parent transcript in Part 2:

```
framework_gap_research                        -> regex_role=unknown      write_capable=False
independent_guard_audit                       -> regex_role=unknown      write_capable=False
repair_plan_check                             -> regex_role=unknown      write_capable=False
bounded_plan_verifier                         -> regex_role=unknown      write_capable=False   (intended: verifier)
current_state_researcher                      -> regex_role=unknown      write_capable=False   (intended: researcher)
plancheck_structural_guard_spec               -> regex_role=unknown      write_capable=False
plancheck_structural_guard_spec_bounded       -> regex_role=unknown      write_capable=False
plancheck_structural_guard_spec_round2        -> regex_role=unknown      write_capable=False
plancheck_structural_guard_spec_round3        -> regex_role=unknown      write_capable=False
test_writer_structural_guard                  -> regex_role=unknown      write_capable=False   (intended: test-writer -- WRONG)
coder_structural_guard                        -> regex_role=unknown      write_capable=False   (intended: coder -- WRONG)
test_writer_reconcile_broad_suite             -> regex_role=unknown      write_capable=False   (intended: test-writer -- WRONG)
test_writer_reconcile_adjacent_hooks          -> regex_role=unknown      write_capable=False   (intended: test-writer -- WRONG)
verifier_structural_guard_postbuild           -> regex_role=unknown      write_capable=False
```

**14/14 → `"unknown"`.** Including the exact `task_name` of the two dispatches the prior brief traced
as **live, real, production denials** (`coder_structural_guard`, `test_writer_reconcile_broad_suite`) —
if a fix naively reused this regex verbatim against `task_name`, it would still deny both of those
real Coder/Test-writer dispatches even after "fixing" the file-scanning/shape-matching problem, because
of a second, independent, previously-undocumented bug.

**Root cause, confirmed directly in Python:** Python's `\b` word-boundary is a transition between a
`\w` character (`[a-zA-Z0-9_]` — **underscore included**) and a non-`\w` character. Codex task names in
this project use `_` as the word separator (`coder_structural_guard`), so the character immediately
after "coder" is `_` — a `\w` character — meaning **there is no boundary there**, and `\bcoder\b` never
matches:
```
>>> re.search(r'\bcoder\b', 'some-coder-task')     # hyphen IS a non-\w char -> boundary exists -> MATCHES
>>> re.search(r'\bcoder\b', 'some_coder_task')     # underscore IS a \w char -> no boundary -> DOES NOT MATCH
>>> re.search(r'\bcoder\b', 'encoder module')      # correctly does NOT match a substring inside a larger word
```
This means the regex was implicitly written for **Claude Code's freeform prose** (`description`/
`prompt` text, hyphen- or space-separated) and silently fails on **Codex's snake_case task identifiers**
— not a corner case, the *entire* real sample. A one-line fix (normalize `_`/`-` to spaces before
matching) restores correct classification for all 5 real write-capable dispatches
(`coder_structural_guard` → coder; the three `test_writer_*` → test-writer) while correctly leaving the
9 non-write-capable ones (`researcher`/`verifier`/`plancheck`/ambiguous-audit names) as non-write-capable
— confirmed by re-running the same 14 names through the normalized version.

**A residual, structural false-positive risk remains even after the separator fix**, inherent to
unscoped substring/token matching against a freeform, schema-less string: the existing check order
(`test-writer` → `coder` → `researcher` → `verifier`) resolves the *first* matching keyword, so a
hypothetical (not observed in the real 14-sample) task name containing two role words —
e.g. `"coder_regression_researcher_followup"` (a plausible name for a *Researcher* investigating a
*coder* bug) — classifies as `"coder"` (write-capable) when the intent is `"researcher"` (should NOT be
write-capable). Confirmed directly: `classify("coder regression researcher followup") == "coder"`. No
real task_name in the 14-sample exhibits this, but nothing in Codex's `spawn_agent` schema constrains
`task_name` to avoid it — it is whatever string the orchestrator/Oga chooses to pass, unvalidated.

## Part 5 — Fail-open or fail-closed on an unrecognized `task_name`? Confirmed via code inspection: fails CLOSED

Traced the existing code's own handling of an unrecognized role string
(`hooks/pre_tool_use_oga_guard.py:667,920-925`): `WRITE_CAPABLE_ROLES = {"coder", "test-writer",
"test_writer"}` (line 667) is a literal set; `_dispatch_role()`'s fallback return value for anything
unmatched is the literal string `"unknown"` (line 747), which is not a member of that set. At
lines 920-925: `if active_record.get("role") in WRITE_CAPABLE_ROLES: ...allow...` else
`identity_error = "active worker role is not write-capable"` — which falls through (absent the
time-boxed `LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1` escape hatch, lines 927-933, itself set to expire
2026-09-30) to the unconditional `deny` at line 937. **Confirmed: an unrecognized/unmatched role string
fails CLOSED (denies), never open.** This is a real, already-proven property of the existing
Claude-Code-side mechanism (not an inference) — and if a symmetric Codex-side classifier is built
reusing the *same* `WRITE_CAPABLE_ROLES` membership check (the natural, minimal-surface-area design,
per the spec's own Section D framing of extending rather than forking the mechanism), the same
fail-closed property carries over **by construction**: any output that isn't exactly the string
`"coder"`, `"test-writer"`, or `"test_writer"` (case- and spelling-exact — a `"Coder"` or a hypothetical
`"coder "` with trailing whitespace would ALSO fail closed) denies. This part is a grounded design
inference about new code, not yet-observed live Codex behavior — flagged as such.

## Part 6 — Direct correction to the active spec: it currently assumes `agent_type` carries role on the dispatch record; that assumption is empirically false

Grepped `loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md` for every mention of
`agent_type`/`task_name`/`agent_nickname`/`agent_path`/`agent_role`. Result: `task_name`,
`agent_nickname`, `agent_path`, and `agent_role` are **never mentioned anywhere in the spec** —
`agent_type` is mentioned **exactly 3 times**, and all 3 assume it is the field that carries role on
the Codex dispatch record itself:

- **Section D, candidate (a)** (line 87): "...built from `extract_function_calls(transcript_path,
  name="spawn_agent")` (for dispatch records: `agent_type` → role, the resulting `agent_id`...)"
- **Section E, AC3** (line 115): "Same as AC1 but dispatched as a non-write-capable role
  (Researcher/Verifier `agent_type`)"
- **Section H** (line 143): "a real `spawn_agent` dispatch with `agent_type` mapping to a
  write-capable role, followed by an `apply_patch` call carrying that dispatch's own `agent_id`"

**All three are empirically wrong as written**, on the evidence above: (i) real `spawn_agent`
`function_call` arguments have exactly the keys `{fork_turns, message, task_name}` — confirmed
exhaustively across all 14 real calls in the parent transcript, zero `agent_type` key present, ever
(Part 4's source data, independently re-confirming the prior brief's Part 2.3 finding in this fresh
session); (ii) a field literally named `agent_type` DOES exist, but on the child's own *subsequent*
hook payload, not the dispatch record, and takes only `{null,"default","explorer","worker"}` (Part 3) —
it can never equal "Researcher" or "Verifier" as AC3 assumes. **If a Test-writer builds Section H's
"exploit-probe replay" fixture exactly as worded — a `spawn_agent` call whose arguments include
`agent_type` mapping to a role — the fixture will be internally self-consistent (both the fixture and
a naive implementation agree on the shape) but shaped nothing like a real Codex transcript**, which is
precisely the "self-consistent-but-wrong fixture" risk the prior brief's Part 4 already found this
codebase's `_codex_fixture_builders.py`/`codex_transcript_adapter.py` to already contain — now
confirmed to also be baked into this *active, not-yet-built* spec's own text, catchable before the
build rather than after.

**Recommended correction (for Oga/plan-check to decide, not something I'm authorized to change
myself):** Section D candidate (a), AC3, and Section H should each be reworded to derive role from
`task_name` (via a fixed, keyword-normalized mapping — e.g. reusing `_dispatch_role()`'s pattern with
the underscore/hyphen-to-space fix demonstrated in Part 4) rather than from `agent_type`. Whether the
implementation sources `task_name` from the parent's own `spawn_agent` call (requires the guard to
locate and open a *second*, sibling transcript file — a new capability not present today, since
`transcript_path` for a child's own call points only at the child's file) or from the child's own
`agent_path` (already sitting in `events[0]`, the same file already loaded, zero new file I/O, but
silently absent — `null` — for any dispatch using Codex's native "v1" sub-agent mechanism rather than
this project's own `task_name`-based `spawn_agent` convention) is a design trade-off for Section D to
state explicitly, now that both options are characterized.

## Sources

- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-45-17-019f693e-4ade-72e0-b381-aebfbca4d849.jsonl:1` — full `session_meta` payload (minus `base_instructions`/`instructions`), quoted verbatim in Part 1
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-47-08-019f693f-fa33-7950-9a7d-ab8405458426.jsonl:1` — full `session_meta` payload, quoted verbatim in Part 1 (the "v1"/`agent_role:"worker"` example)
- `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T00-52-34-019f6944-f508-7a41-9e3f-a46c2ac6d530.jsonl:1`, `<HOME>/.codex/sessions/2026/07/16/rollout-2026-07-16T01-03-43-019f694f-2b1a-7670-b516-66cf0cb053f0.jsonl:1` — full `session_meta` payloads, Part 1
- `~/.codex/sessions/2026/07/16/*.jsonl` (all 111 files present in the directory at research time; `ls` count independently reconfirmed) — scanned every `session_meta` with `thread_source=="subagent"`, 111 matching rows, full table basis for Part 3's `agent_role` vocabulary claim ({null,"default","explorer","worker"}, never a domain role)
- `<HOME>/.codex/sessions/2026/07/15/rollout-2026-07-15T22-13-53-019f68b3-acea-7540-8466-b7f96524e784.jsonl` — 0-indexed lines 35,41,151,251,516,583,620,674,725,752,804,880,960,1033 (`sed` 1-indexed = +1): all 14 real `spawn_agent` `function_call` entries, `arguments` parsed, exhaustive keyset check `{fork_turns,message,task_name}` only (Part 2, Part 4, Part 6) — confirmed 0-indexing by direct inspection (0-idx line 35 = a `message` event; 0-idx line 36 = the actual `spawn_agent` call)
- `hooks/fixtures/ac1_captured_codex_stop_stdin.json` — real captured `SubagentStop` payload (2026-07-10), `"agent_type":"explorer"` quoted verbatim in Part 3 (the one real, unredacted value on record for this field)
- `~/.loop-gate/oga_guard_debug.jsonl` (read live 2026-07-16) — grouped by `sorted(payload_keys)` across the same 1,098-real-Codex-row filter both prior briefs used: 3 distinct key-sets, `agent_id`+`agent_type`+`turn_id` present on exactly 1,056 rows (matching the prior brief's independently-derived child count), absent on 42 (matching its root-session count) — Part 3
- `hooks/pre_tool_use_oga_guard.py:667` — `WRITE_CAPABLE_ROLES = {"coder", "test-writer", "test_writer"}`
- `hooks/pre_tool_use_oga_guard.py:728-747` — `_dispatch_role()`, the exact regex copied and tested in Part 4
- `hooks/pre_tool_use_oga_guard.py:750-768` — `dispatched` collection loop (unreachable for Codex, per the prior session_id brief's Part 2 — cited, not re-derived here)
- `hooks/pre_tool_use_oga_guard.py:823-838,920-937` — `active_dispatches`, `WRITE_CAPABLE_ROLES` membership check, `LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK` escape hatch, final unconditional `deny` — Part 5's fail-closed trace
- `hooks/pre_tool_use_oga_guard.py:23-40` — `_dispatch_view()`, a SEPARATE, earlier mechanism in this same file that ALSO assumes `spawn_agent`'s own `tool_input` carries `raw_input.get("agent_type", "")` (line 34) — confirmed empty for real Codex calls for the identical reason as Part 6; feeds the older spec-bound Verifier/Coder credit gate (lines 331-390) and its own text-heuristic fallbacks (`_rh_type`/`_sb_type` checks at lines 312, 377) — out of this dispatch's build scope (`spec.md` Section F explicitly excludes 331-392) but directly corroborating: this codebase already has ONE Codex `agent_type`-assumption bug in production, in a different gate, for the same root cause
- `loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md:87,115,143` — the 3 exact `agent_type` mentions corrected in Part 6; confirmed via `grep -n` that `task_name`/`agent_nickname`/`agent_path`/`agent_role` never appear anywhere in this spec
- `fix_plan.md:9299` — `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`, the tracked item this build closes
- `git log -1 --format="%H %cI %s" -- hooks/pre_tool_use_oga_guard.py` → `4ace7a9c... 2026-07-16T01:40:10-04:00` (unchanged since the prior brief)
- `stat -f "%Sm" hooks/pre_tool_use_oga_guard.py` → `Thu Jul 16 00:58:57 2026` (unchanged since the prior brief)
- Python 3 `re` module, direct live tests (Part 4) — `\bcoder\b` against `"some-coder-task"` (matches), `"some_coder_task"` (does not match), `"encoder module"` (correctly does not match) — reproducible, not a citation to an external doc, a live mechanical check I ran myself

## Constraints

- **`agent_type`'s real value for genuine `PreToolUse` calls is confirmed only for one adjacent event
  type (`SubagentStop`), not independently re-proven at `PreToolUse` itself** — the debug log redacts
  values (key names only), so I cannot show a second, unredacted, `PreToolUse`-specific `agent_type`
  string the way I can for `SubagentStop`. The inference that it shares the same 4-value vocabulary at
  `PreToolUse` is well-grounded (same field name, same runtime, same "Common input fields" contract
  cited in the prior brief covers both event types, and the *key's presence* is independently confirmed
  at `PreToolUse` via `payload_keys`) but is an inference, not a second direct value-read. Flagged
  explicitly in `not_found` below, mirroring the prior brief's own honesty-bar treatment of the
  analogous `agent_id`-at-`PreToolUse` gap.
- **The 4 non-re-opened early dispatches** (`framework_gap_research`, `independent_guard_audit`,
  `repair_plan_check`, `bounded_plan_verifier`) have child files under `~/.codex/sessions/2026/07/15/`,
  outside this dispatch's explicitly re-authorized `2026/07/16/` directory — not opened, not needed
  (the 9 re-opened dispatches already span every target role at least once, several roles multiple
  times, with zero exceptions to the `agent_path == "/root/" + task_name` rule).
- **Scope discipline, as in both prior briefs:** `~/.loop-gate/oga_guard_debug.jsonl` lives outside the
  repo tree (established authoritative evidence source elsewhere in this project — `fix_plan.md:838,
  5657`); reading real files under `~/.codex/sessions/` (outside the repo tree) was explicitly
  authorized by this dispatch's own text. I extracted only structural fields (event types, ids,
  timestamps, task/nicknames, argument key names) — never the encrypted `message` payload content of
  any real `spawn_agent` call, and never any `base_instructions`/`instructions` system-prompt text
  (elided from every JSON dump above).
- **The false-positive ambiguity example in Part 4 (`"coder_regression_researcher_followup"`) is a
  constructed illustration, not an observed real task_name.** No real dispatch in the 14-sample
  exhibits this specific ambiguity; it is reported as a structural risk inherent to the matching
  approach, not a confirmed live bug.
- **This brief does not re-litigate the session_id/agent_id findings** already fully established in
  the two prior briefs in this chain — cited, not re-derived, except where directly load-bearing for
  cross-checking a count (the 1,056/42 split, independently reconfirmed here as a byproduct of the
  `agent_type` key-presence check, landing on the identical numbers).

## not_found

- I could not directly read an unredacted, real `agent_type` **value** from a genuine `PreToolUse`
  hook invocation specifically (only from the one captured `SubagentStop` fixture). A future check:
  extend whatever mechanism captured `ac1_captured_codex_stop_stdin.json` to also capture one real,
  unredacted `PreToolUse` stdin payload for a Codex sub-agent's own follow-up tool call, and confirm
  its `agent_type` value falls in the same `{"default","explorer","worker"}` set (or find a fifth value
  this research didn't encounter).
- I did not determine **why** two independent Codex sub-agent mechanisms coexist (`multi_agent_version`
  `"v1"` with generic `agent_role`, vs `"v2"` with `task_name`-shaped `agent_path`) or what triggers a
  given top-level session to use one vs the other — the same top-level repo (`loop`) was observed using
  both, under different parent session lineages, so it is not a simple per-repo or per-config-file
  switch. This would need either an OpenAI Codex Desktop changelog/release-note check (not done, out of
  scope for this dispatch) or a direct question to whoever configures this project's Codex sessions.
- I did not check whether `task_name` is subject to ANY validation/schema on the Codex side (e.g., a
  max length, a reserved-character set) that might already prevent the ambiguous dual-keyword scenario
  in Part 4 from ever occurring in practice — I only confirmed it is unconstrained in the 14 real
  samples observed (a wide variety of shapes, no evidence of enforced structure beyond "valid as a
  single path segment after `/root/`").
