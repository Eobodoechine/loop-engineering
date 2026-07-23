# OGA-GUARD Exact-Worker-Identity Guard — Regression Dossier

**Mode:** B (Coder-unblock, read-only investigation)
**Date:** 2026-07-16
**Investigated session:** `5dec499f-d96d-44ff-a345-149c1349a2b4` (creditgate-usage-trailer-block build)
**Blocking build:** `SPEC_SHA256=879b9b8141bfe3ac934f24aeb2981c30dc6928c01c3fb79e03f0231ba74d4485`,
worktree `<HOME>/Claude/loop-worktrees/creditgate-usage-trailer-block`
(branch `fix/creditgate-usage-trailer-block`, based on `4ace7a9`)

**Cross-reference:** this dossier independently corroborates, from a second, separate session, a
root cause already hypothesized (but not confirmed with an unredacted value comparison) in
`fix_plan.md` entry `H-OGAGUARD-EXACTWORKER-AGENTID-NAMESPACE-MISMATCH-1` (lines 9403-9473),
filed the same day from session `73a73d31-b80b-43e9-a9bd-d80481da0c85`. Everything below is
grounded in this session's own transcript/debug-log evidence, read fresh — not copied from that
entry — and the two data points agree in every particular checked.

---

## 1. Confirmed root cause

**The mechanism, exactly as implemented, `hooks/pre_tool_use_oga_guard.py`:**

Step 1 — collect every `Agent` dispatch in the transcript (lines 750-768):
```python
dispatched = {}  # tool_use_id -> active-dispatch metadata
for i, e in enumerate(events):
    ...
    if isinstance(p, dict) and p.get("type") == "tool_use" and p.get("name") == "Agent":
        tid = p.get("id") or p.get("tool_use_id")
        if tid:
            dispatched[tid] = {
                "dispatch_id": str(tid),
                ...
                "agent_id": "",
            }
```

Step 1b — pair the launch-acknowledgment's human-facing `agentId:` text onto that record
(lines 770-780):
```python
AGENT_ID_RE = re.compile(r'\bagentId:\s*([^\s(]+)')
...
for e in events:
    for p in _tool_result_parts(e):
        tid = p.get("tool_use_id")
        if tid not in dispatched:
            continue
        match = AGENT_ID_RE.search(_part_text(p))
        if match:
            dispatched[tid]["agent_id"] = match.group(1).strip()
```

Steps 2-3 — retirement (`<tool-use-id>` tag scan) and a staleness cap produce `in_flight_ids`
(lines 787-826); combined with a same-session filter this produces `active_dispatches`
(lines 828-838).

Step 4 — canonical identity + resolution (lines 841-867):
```python
def _canonical_agent_identity(info):
    return info.get("agent_id") or info.get("dispatch_id")

def _resolve_agent_id(value):
    if not value:
        return None
    matches = [info for info in active_dispatches
               if _canonical_agent_identity(info) == str(value)]
    return matches[0] if len(matches) == 1 else None
```

Step 5 — the actual gate (lines 870-895):
```python
top_agent_id = data.get("agent_id")
top_task_id = data.get("task_id")
top_dispatch_id = data.get("dispatch_id")

if top_agent_id:
    rec = _resolve_agent_id(top_agent_id)
    if rec is None:
        identity_error = "top-level agent_id does not match an active same-session worker"
    else:
        identity_records.append(("agent_id", rec))
elif top_task_id:
    ...
```

The deny message (lines 949-971) is byte-identical to what both real dispatches received —
confirmed by direct string comparison against the task-notification results captured in this
session's own transcript (see §3).

**What "top-level identity" means concretely:** the PreToolUse hook's own stdin JSON `data` dict
(`data.get("agent_id")` / `data.get("task_id")` / `data.get("dispatch_id")`) — i.e. fields the
Claude Code runtime itself is expected to attach fresh to *every* tool-call hook invocation,
including ones fired from inside a dispatched sub-agent's own execution context. The "active,
same-session, unretired... dispatch record" it matches against comes entirely from a *transcript
scan* of the orchestrator's own session JSONL (`data["transcript_path"]`) — there is no flag file
or other out-of-band store involved in identity resolution itself (a gate-arming flag file,
`~/.loop-gate/<session>_target`, exists elsewhere in this same hook file but is unrelated to this
mechanism).

**The confirmed break:** the observed error text on both real blocks matches *exactly* the
`if top_agent_id:` branch's own string at line 879 (`"top-level agent_id does not match an active
same-session worker"`) — not the `else` branch's `"missing top-level worker identity"` (line 895).
Since the if/elif/else structure at lines 876-895 can *only* reach the line-879 string when
`top_agent_id` is truthy, this alone proves `data["agent_id"]` **was present and non-empty** on
both blocked calls. Independently, `~/.loop-gate/oga_guard_debug.jsonl`'s redacted `payload_keys`
field (see §3, this file's own AC-RH5 "values redacted, keys only" design) confirms `"agent_id"`
was literally a top-level key in the real stdin payload for both blocks. So `_resolve_agent_id(top_agent_id)`
ran and returned `None` — meaning no active-dispatch record's `_canonical_agent_identity()` (i.e.
neither its scraped `agent_id` nor its `dispatch_id` fallback) equalled the real runtime's
`data["agent_id"]` value, **despite the correct record genuinely being present and in-flight** at
block time (proven below, §3). This is a **value-comparison mismatch**, not a
missing-record/staleness/retirement bug — those upstream mechanics (steps 1-3) are independently
proven correct in this session's own data.

The unredacted *value* of the real `data["agent_id"]` is not directly observable from any source
this dossier had authorized access to (transcripts and the redacted debug log) — see §3's honesty
note. This dossier's conclusion rests on the *structural* proof above (record present + correct
role + correct session + still denied), not on having read the literal mismatched string.

---

## 2. What a passing case requires (from the test suite)

`hooks/test_pre_tool_use_oga_guard.py`, class `TestExactWorkerIdentityGuard` (lines 2564-2672,
6 test methods — confirms the fix_plan's cited "8 passed" count once the 2 sibling
`old_bare_plan_pass`/`valid_plan_support_json` tests from a different class are added). Its own
docstring (lines 2564-2572) states these are "routed through the real PreToolUse subprocess path
rather than a private helper" — confirmed true: `_run_hook_with_payload` (lines 542-570) actually
`subprocess.run`s `HOOK = .../pre_tool_use_oga_guard.py` with a JSON stdin payload, so the
*mechanism itself* is genuinely exercised, not stubbed.

The fixture that builds every passing case, `_identity_dispatch_events` (lines 2520-2550), and its
companion `_identity_launch_ack` (lines 2512-2517):
```python
def _identity_launch_ack(agent_id):
    return (
        "Async agent launched successfully. (internal metadata)\n"
        "agentId: %s (internal ID - do not mention to user. Use SendMessage "
        "with to: '%s', summary: 'continue worker')" % (agent_id, agent_id)
    )

def _identity_dispatch_events(worker_id="worker-A", role="Coder", ...):
    """...The fixture carries both the Agent tool_use id (`dispatch-<worker>`) and
    the launch-ack `agentId` (`worker_id`) because the structural fix must
    prefer the launch-ack identity when present while still pairing it to the
    original top-level dispatch record.
    """
    ...
    ack = _pt_tool_result(dispatch_id, _identity_launch_ack(worker_id))
```

And the one passing test itself, `test_exact_active_coder_and_test_writer_identity_allow`
(lines 2574-2586):
```python
worker_id = "worker-%s" % agent_type
proc = _run_identity_guard(
    _identity_dispatch_events(worker_id=worker_id, role=role),
    payload_extras={
        "session_id": "identity-session",
        "agent_id": worker_id,
        "agent_type": agent_type,
    },
)
```

**A passing case requires exactly one thing structurally:** the top-level stdin payload's
`agent_id` value must be *literally the same string* as the `agentId:` text embedded in the
dispatch's own launch-ack tool_result. In every one of the 6 tests in this class, `worker_id` is
the single shared Python variable that constructs *both* sides of that comparison — there is no
test anywhere in this 2700+-line file (confirmed: `grep -in "real captured|namespace"
hooks/test_pre_tool_use_oga_guard.py` returns zero matches) that sources the top-level `agent_id`
from anything other than the same string used to build the launch-ack. This is the textbook
"fixture tautology" shape this repo has flagged before (`loop-team/learnings.md`, 2026-06-24) —
the test suite can only ever prove the comparison logic is *internally consistent*, never that it
matches what the real runtime actually sends.

---

## 3. Why the two real Coder dispatches failed to meet that

Both dispatches in this session are confirmed, by tool_use id, from the transcript:

| Dispatch | tool_use id | agentId (launch-ack) | `run_in_background` | Outcome |
|---|---|---|---|---|
| "Implement usage-trailer credit-gate fix" | `toolu_0166qufcSS9QReugUE6wHW9x` | `adfe12a55678ead27` | `true` (background) | Blocked |
| "Apply pre-designed usage-trailer fix diff" | `toolu_01CH5MAsmi4MB3LnbvPo4Vky` | `a62aba0bca9a1ea35` | `false` (foreground) | Blocked |

Both received the byte-identical deny text (captured verbatim in each sub-agent's own final
report, delivered back to the orchestrator as a `<task-notification>` / synchronous tool_result):

```
[OGA GUARD] Edit('spec_bound_verifier_credit.py') blocked. In a loop-team session, the delegated
write must carry a top-level identity for the exact active, same-session, unretired Coder/Test-
writer dispatch. Identity check failed: top-level agent_id does not match an active same-session
worker. ...
```

**Proof the correct record genuinely existed and was in-flight at block time** — from
`~/.loop-gate/oga_guard_debug.jsonl`, filtered to `session_id ==
"5dec499f-d96d-44ff-a345-149c1349a2b4"` (this repo's own hook, `_write_debug_row`, lines 629-650,
writes one row per allow/deny decision; it deliberately redacts payload *values*, logging only
`payload_keys`, per its own AC-RH5 docstring):

```json
{"tool": "Edit", "file": ".../hooks/spec_bound_verifier_credit.py", "decision": "deny",
 "in_flight_ids": ["toolu_01PKPt2fnB7hZ8DhW7SqyEmc", "toolu_01Wa73xkyEm2y8Doy3wwsG3n",
                    "toolu_01R2hS8CFqYHyWNuR4jAPkFx", "toolu_0166qufcSS9QReugUE6wHW9x"],
 "session_id": "5dec499f-d96d-44ff-a345-149c1349a2b4",
 "payload_keys": ["agent_id","agent_type","cwd","effort","hook_event_name","permission_mode",
                   "prompt_id","session_id","tool_input","tool_name","tool_use_id","transcript_path"]}
{"tool": "Edit", "file": ".../hooks/spec_bound_verifier_credit.py", "decision": "deny",
 "in_flight_ids": ["toolu_01PKPt2fnB7hZ8DhW7SqyEmc", "toolu_01Wa73xkyEm2y8Doy3wwsG3n",
                    "toolu_01R2hS8CFqYHyWNuR4jAPkFx", "toolu_01CH5MAsmi4MB3LnbvPo4Vky"],
 "session_id": "5dec499f-d96d-44ff-a345-149c1349a2b4",
 "payload_keys": [... same shape ...]}
```

Note that `toolu_0166qufcSS9QReugUE6wHW9x` (the background Coder's *own* dispatch id) is present
in `in_flight_ids` at the moment of *its own* Edit block, and `toolu_01CH5MAsmi4MB3LnbvPo4Vky`
(the foreground Coder's own dispatch id) is present at the moment of *its* block — proving steps
1-3 (dispatch collection, retirement scan, staleness cap, same-session filter) correctly produced
an `active_dispatches` entry for the exact worker that was blocked, every time. This rules out a
missing-record or premature-retirement bug and isolates the failure to the final
`_canonical_agent_identity(info) == str(top_agent_id)` comparison in step 4.

**Two additional facts sharpen this:**
- `payload_keys` confirms the real runtime attaches `agent_id`, `agent_type`, and `tool_use_id` as
  three *distinct* sibling top-level fields on a sub-agent's own tool-call hook payload — yet the
  guard's identity logic (§1) never reads `agent_type` or `tool_use_id` at all. This exact
  observation — "`data` has `tool_use_id`, `agent_type`, `prompt_id` ... none of which the current
  identity-resolution code even inspects" — is independently reproduced in this session (this is
  the *second* independent session, alongside `73a73d31-...`, to observe this identical
  `payload_keys` shape on a real deny).
- `grep -c '"isSidechain":true' 5dec499f-....jsonl` → **0**. A sub-agent's own internal tool calls
  (including the literal blocked `Edit` and its exact hook stdin payload) are never persisted
  inline in the orchestrator's own session transcript — they live only in the sub-agent's own
  separate output file, which the orchestrator is explicitly instructed never to read directly
  ("it is the full subagent JSONL transcript and reading it will overflow your context," per the
  launch-ack text itself, jsonl line 414). This is why neither this session nor the sibling session
  could observe the raw `data["agent_id"]` *value* directly — only its redacted key-presence
  footprint. It also directly answers the dispatch's own question about how a nested sub-agent's
  tool call is identified to the guard at all: **the PreToolUse hook fires fresh, in the
  sub-agent's own process, receiving its own stdin `data` blob that includes the orchestrator's
  `transcript_path`** (confirmed: all four debug rows carry `transcript_basename:
  "5dec499f-....jsonl"`, i.e. the *orchestrator's* transcript, even though the tool call itself
  came from inside the sub-agent) — so transcript-scan-based record lookup (steps 1-3) works
  correctly by design. Only the sub-agent's own `agent_id` value, carried separately on that same
  stdin blob, is where the mismatch lives.

**No genuinely-passing real-world case exists anywhere in the available evidence.** The
Test-writer's earlier, successful edit to `hooks/test_spec_bound_verifier_credit.py` in this same
session (confirmed via `git diff --stat`: "709 insertions(+), 5 deletions(-)") is *not* a passing
case of this guard — `Bash` is not in `WORKER_TOOLS` (`{"Write", "Edit", "NotebookEdit",
"MultiEdit", "apply_patch"}`, line 539), so a Bash-based edit never invokes this identity check at
all; it is a complete bypass, exactly as the guard's own deny text admits ("it can be bypassed via
Bash, so it is not relied on as one"). Combined with the sibling session's 4 real denials (0
passes) and this session's 2 real denials (0 passes), there are now **6 confirmed real-world
denials across 2 independent sessions/worktrees on the mechanism's first day of production
existence, and zero confirmed real-world passes.**

---

## 4. Blast radius

**Total regression, not narrow.** The guard is armed by scanning the transcript for
orchestrator-playbook markers (`_M_OGA`/`_M_PLAYBOOK`/`_M_CODEX_DISPATCH`, lines 616-626) — i.e.
it activates in *every* loop-team session, independent of repo or worktree. The failure mode
(record correctly found in-flight, comparison still fails) is identical across two unrelated
sessions on two different builds on the same day, and is structural to how `_resolve_agent_id`
compares `data["agent_id"]` against a value scraped from launch-ack text — nothing about either
failure ties it to this specific worktree, spec, or file. Given:
- the mechanism shipped in commit `4ace7a9` earlier the same day,
- its own landing evidence (`fix_plan.md` H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`) is
  100% synthetic/fixture-based (the tautological fixtures in §2),
- and every known real-world exercise of it since (6/6) has denied a legitimate Coder/Test-writer,

this dossier concludes the guard **currently blocks essentially all real Coder/Test-writer
protected-file writes, in all sessions, unconditionally** — not a corner case. The two
already-documented escape hatches are: (a) `LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1` (env var,
pre-existing, warns and expires 2026-09-30, restores the broader pre-4ace7a9 in-flight-only check
— zero code change required), and (b) a Bash-based file edit, which fully bypasses `WORKER_TOOLS`
gating entirely (not identity-check-specific; pre-dates this guard). Both are operationally
available today; neither is a fix to the comparison bug itself.

---

## 5. Recommended fix (for a spec author — not written here)

1. **Close the one remaining evidence gap first.** Neither this session nor the sibling session
   directly observed the unredacted `data["agent_id"]` value (by design — `_write_debug_row`
   redacts values per AC-RH5). Before changing comparison logic, get one real, unredacted
   side-by-side: temporarily log the real `top_agent_id` next to `info["agent_id"]` /
   `info["dispatch_id"]` for one genuine sub-agent dispatch, to a private/gitignored scratch
   location — **not** the shared `oga_guard_debug.jsonl`. This confirms precisely what the two
   values actually are and whether `agent_id` is a stable-but-differently-namespaced per-worker
   token, or something unrelated to worker identity altogether.
2. **Branch on that result:**
   - If `data["agent_id"]` is a stable, attributable-to-one-worker token distinct from the
     launch-ack `agentId:` text — extend the dispatch-record construction (step 1/1b, lines
     750-780) to capture and match against whatever *that* real field actually is, using the
     payload's own already-observed sibling fields (`agent_type`, `tool_use_id`) as a starting
     point for what else might need to flow into the comparison, since the current code ignores
     both entirely.
   - If no reliable per-invocation identity signal exists in the payload for the guard to match
     against at all, fall back — as this file's own already-shipped
     `LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1` mechanism already does — to a documented, broader
     in-flight/role check rather than an exact per-invocation match the runtime's payload schema
     may not actually support today. The guard is explicitly documented (lines 967-968) as
     advisory, not a security boundary; a mechanism with a 100% real-world false-positive rate is
     a strictly worse trade than the broader check it replaced.
3. **Either way, the regression test that closes this must use a REAL captured launch-ack event
   paired with a REAL captured subsequent-tool-call PreToolUse payload for the same dispatch** —
   not two ends constructed from one shared test variable (§2). This is the same "fixture
   tautology" standard this repo already applies elsewhere (e.g. the sibling
   `H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1` entry's own proposed-fix language).
4. **Interim operational note for whoever is unblocking the live build:** since this is now
   doubly-confirmed as a total, same-day regression with zero known real-world passes (not a
   worktree-specific fluke), the already-shipped `LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1`
   env-var escape hatch is a reasonable interim path for unblocking the URGENT
   `H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1` build specifically, while the identity-match
   logic itself gets a proper spec'd fix — that operational decision belongs to Oga, not to this
   dossier.

---

## Appendix — exact evidence index

- `hooks/pre_tool_use_oga_guard.py:663-667,750-895,920-972` — the guard mechanism (quoted in full
  in §1).
- `hooks/test_pre_tool_use_oga_guard.py:542-570` (`_run_hook_with_payload`), `:2512-2561`
  (`_identity_launch_ack`/`_identity_dispatch_events`/`_run_identity_guard`), `:2564-2672`
  (`TestExactWorkerIdentityGuard`, all 6 tests) — the fixture-tautology evidence (§2).
- `fix_plan.md:9299-9362` (`H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1`, the landing slice) and
  `fix_plan.md:9403-9473` (`H-OGAGUARD-EXACTWORKER-AGENTID-NAMESPACE-MISMATCH-1`, OPEN, the
  sibling-session finding this dossier corroborates).
- Session transcript `~/.claude/projects/-Users-eobodoechine/5dec499f-d96d-44ff-a345-149c1349a2b4.jsonl`:
  jsonl line 411 (background Coder dispatch, `toolu_0166qufcSS9QReugUE6wHW9x`), line 414 (its
  launch-ack, `agentId: adfe12a55678ead27`), line 419/422 (its blocked-Edit report), and the
  foreground Coder dispatch/result at lines ~430-448 (`toolu_01CH5MAsmi4MB3LnbvPo4Vky`, `agentId:
  a62aba0bca9a1ea35`).
- `~/.loop-gate/oga_guard_debug.jsonl`, 4 rows filtered to `session_id ==
  "5dec499f-d96d-44ff-a345-149c1349a2b4"` (quoted in full in §3).

**Honesty note:** this dossier does not claim to have read the literal unredacted value of
`data["agent_id"]` on either blocked call — that value is redacted by this repo's own logging
design (AC-RH5) and the sub-agent's raw hook stdin is never persisted to any transcript this
dossier had authorized access to. The root-cause conclusion rests on the structural proof in §3
(correct record present + correct role + correct session + still denied, reproduced identically
across 2 independent sessions), not on having observed the mismatched strings directly. Closing
that last gap (recommendation §5.1) is explicitly left as the next concrete step, matching the
sibling `fix_plan.md` entry's own stated residual gap.
