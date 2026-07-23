# Coder-unblock dossier: Spec-bound Verifier/Coder credit gate v1 (Mode B)

**Date:** 2026-07-17
**Follow-up to:** `research/repo-health-classification-gate-marker-2026-07-17.md` (same
session, same target dispatch).
**Requested by:** Oga, after two `subagent_type="plan-check-verifier"` Agent dispatches were
both blocked pre-execution with `[OGA GUARD] spec-bound Verifier/Coder credit gate blocked
Agent dispatch: expected exactly one spec ref`, while two `subagent_type="verifier"`
dispatches in the same session passed clean. Question: why the split, and exactly what a
`coder` dispatch needs.
**Target dispatch:** edit
`loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md`.
**Confidence:** CONFIRMED for every mechanism below — each is grounded in live source AND
independently reproduced by directly executing the real, unmodified function (not a mock),
using the repo's own vetted test-fixture helpers for fidelity. One caveat is flagged as
UNVERIFIABLE FROM HERE (see "What I could not check" below) — stated plainly, not guessed.

## 1. Source location

`<HOME>/Claude/loop/hooks/spec_bound_verifier_credit.py` (676 lines), invoked
from the **"Spec-bound Verifier/Coder credit gate v1"** block at
`<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py:331-392`, which runs
immediately after the repo-health gate for every `Agent`/`Task`/`Workflow` dispatch. Key
functions:

- `extract_spec_info_from_text()` (line 242) — parses the spec-ref + hash markers out of a
  dispatch's `prompt` text. Source of the exact reported error string (line 251):
  `if len(refs) != 1: return None, "expected exactly one spec ref"`.
- `is_verifier_dispatch()` (line 176) / `is_coder_dispatch()` (line 203) — classify a
  dispatch by `subagent_type` and/or content.
- `prior_verifier_credit()` (line 536) / `authorize_coder_from_transcript()` (line 657) — the
  Coder-side authorization: requires a qualifying prior same-turn Verifier PASS.
- `classify_plan_result_for_hash()` (line 353) — validates a Verifier's RESULT text (not its
  prompt) against the `LOOP_GATE:`/`REVIEWED_SPEC_SHA256=`/`PLAN_SUPPORT_JSON=` contract.

## 2. Exact regex/parsing logic and field

```python
HASH_RE = re.compile(r"\bSPEC_SHA256=([0-9a-f]{64})\b")
REVIEWED_HASH_RE = re.compile(r"\bREVIEWED_SPEC_SHA256=([0-9a-f]{64})(?:\b|(?=agentId:))")
SPEC_LINE_RE = re.compile(r"(?im)^\s*(?:SPEC|Review exactly one spec)\s*:\s*(.+?)\s*$")
SPEC_TOKEN_RE = re.compile(r"(?:~|/|\.\.?/)?[^\s\"'`),;]+\.md\b")
```//spec_bound_verifier_credit.py:11-17

**Both `SPEC_SHA256=` and `REVIEWED_SPEC_SHA256=` are real, distinct fields — not an
either/or guess:**
- **`SPEC_SHA256=<64 lowercase hex>`** — required in the dispatch's own `prompt` (both the
  Coder's AND the Verifier's dispatch prompt use this to declare what spec they're about).
- **`REVIEWED_SPEC_SHA256=<64 lowercase hex>`** — required in the **Verifier's RESULT text**
  (its tool_result content, i.e. what it reports back after running), not in any dispatch
  prompt. It attests which hash the Verifier actually reviewed.

**Field scanned: `prompt` ONLY, never `description`.** `extract_spec_info()` calls
`dispatch_prompt(tool_use)` (line 260-261), and `dispatch_prompt()` (line 169-173) returns
`tool_input["prompt"]` directly for Agent/Task (only Workflow falls back to `"script"`) — no
description-fallback here. This is the opposite of the repo-health gate's marker scan (which
concatenates description+prompt) and the opposite of `is_verifier_dispatch`'s own
CONTENT-based classification (which uses `dispatch_text()`, a description-first-then-prompt
fallback) — three different fields for three different purposes in the same hook chain.

**Why "exactly one spec ref":** `extract_spec_info_from_text()` (line 242-257) collects every
`.md`-token match from every line starting with `SPEC:`/`Review exactly one spec:` (case-
insensitive) across the WHOLE prompt, and requires the grand total to be exactly 1 (zero =
missing/wrong-format line; 2+ = duplicated or a line naming two files). Live-confirmed
(section 5) that Oga's two blocked `plan-check-verifier` attempts had a prompt whose spec
reference did not satisfy this exact line-start shape (any looser phrasing — e.g. "Please
review `<path>` for correctness" — produces 0 refs, tripping this exact error).

## 3. Does it key on `subagent_type`? CONFIRMED, with the exact literal string

`is_verifier_dispatch()` (line 176-200):

```python
subagent_says_verifier = (
    str(inp.get("subagent_type", "") or "").strip().lower() == "plan-check-verifier"
)
```//spec_bound_verifier_credit.py:185-187

This is an **exact string comparison to `"plan-check-verifier"`** — not `"verifier"`. A
dispatch with `subagent_type="verifier"` fails this check; it is only classified as a
Verifier dispatch if its TEXT independently matches `VERIFIER_DETECT` (imported from
`verifier_hygiene_scan.py:11-13`: `r'independent verifier|verifier\.md|plan-?check
verifier|verifier plan-?check'`) or this file's own `VERIFIER_FALLBACK_RE` (line 22:
`r"plan-?check[- ]verifier|verifier[- ]plan-?check"`, case-insensitive). `is_coder_dispatch()`
similarly only matches `subagent_type == "coder"` or `CODER_DETECT` content.

**Live-confirmed (not inferred):** a dispatch with `subagent_type="verifier"` and a neutral
description (`"review the routing pilot spec before coder dispatch"` — no "plan-check
verifier"/"independent verifier"/"verifier.md" substring) returns **both**
`is_verifier_dispatch() == False` **and** `is_coder_dispatch() == False`. Since
`pre_tool_use_oga_guard.py` only calls the spec-ref-parsing check when `is_verifier_dispatch`
is True (line 355), and only calls Coder authorization when `is_coder_dispatch` is True (line
360), **neither branch of this gate ever runs on such a dispatch** — it passes through
untouched regardless of its prompt's spec-ref formatting. This directly and fully explains
why the two `subagent_type="verifier"` dispatches passed clean while the two
`subagent_type="plan-check-verifier"` dispatches (which DO trip `is_verifier_dispatch`) hit
the spec-ref parsing bug.

**A second, more consequential live-confirmed finding from the same mechanism:** even if a
`subagent_type="verifier"` dispatch runs successfully and produces a textually-perfect
`LOOP_GATE: PLAN_PASS` result, it **grants zero credit toward a later Coder dispatch**,
because `prior_verifier_credit()`'s scan loop explicitly skips any record where
`is_verifier_dispatch()` is False (line 579: `if vid in blocked_ids or not
is_agent_task_dispatch(verifier) or not is_verifier_dispatch(verifier): continue`). Live test
(section 5, Test 3c-FIXED): identical same-turn, same-hash, textually-valid PASS, differing
ONLY in `subagent_type="verifier"` vs `"plan-check-verifier"` → Coder authorization flips
from `True` to `False`. **If the "two prior verifier passes" Oga is relying on used
`subagent_type="verifier"`, they produce no usable credit for the Coder dispatch no matter
how good their content is — a fresh `plan-check-verifier`-typed (or content-matching) dispatch
is required.**

## 4. What else is required beyond the hash marker

Nothing else goes in the **Coder's own prompt** — `extract_spec_info` only needs the one
`SPEC:` line + one `SPEC_SHA256=` line (section 2). The "plan-check citation" lives entirely
in the **prior Verifier dispatch's RESULT text**, validated by `classify_plan_result_for_hash()`
(line 353-503):

- Exactly one line, trimmed, equal to `LOOP_GATE: PLAN_PASS` (narrow tolerance exists for one
  trailing `<usage>...</usage>` block or one specific harness-glued `agentId:` suffix — a
  clean literal line is the safe target). `LOOP_GATE: PLAN_FAIL` or 0/2+ `LOOP_GATE:` lines
  are rejected/veto.
- Exactly one `REVIEWED_SPEC_SHA256=<64-hex>` line **before** the gate line, equal to the
  same hash the Coder will cite.
- At least one `PLAN_SUPPORT_JSON=<json>` line before the gate line, a JSON object with
  `artifact_path` (str, must resolve to a real file), `line_start`/`line_end` (positive ints),
  `evidence_sha256` (64-hex, must equal the REAL SHA-256 of that file's exact
  `lines[line_start-1:line_end]` joined text — hash-verified, not just asserted),
  `claim` (non-empty str), `spec_sha256` (must equal the reviewed hash). Any support line that
  fails validation, or zero support lines at all, makes the result "support-invalid" — neutral
  (does not grant OR veto credit), not an outright pass.

**A further requirement discovered only by live-testing (not obvious from a static read):**
the Verifier dispatch's `run_in_background` value governs how its result is recognized.
`prior_verifier_credit()` (line 595) reads `tool_input(verifier).get("run_in_background",
True)` — **defaults to background/True if the field is simply omitted.** For a
background-classified dispatch, its first RAW (non-notification) tool_result is always
treated as the non-terminal "launch ack" stub and skipped, REGARDLESS of its content — only
the genuine async `<task-notification>` completion event (or a dispatch explicitly marked
`run_in_background: false`) counts as the real terminal PASS. Getting this wrong produces the
exact same denial reason as having no Verifier record at all — a live trap when hand-building
a test transcript (this exact mistake cost me a debugging cycle in section 5).

## 5. Live verification (real function, both target file + hash)

All calls below use the target file's real path and its real, freshly-recomputed hash (see
section 6), and reuse `hooks/test_spec_bound_verifier_credit.py`'s own vetted fixture
helpers (`write_spec`, `agent_tool_use`, `human_event`, `tool_result_event`, `coder_input`,
`coder_prompt`, `pass_result_body`, `authorize`, `notification_content`/`notification_event`)
for maximum fidelity — not hand-rolled JSON.

```
TEST 1 (reproduces the reported failure): plan-check-verifier dispatch, prompt referencing
the spec in prose ("Please review <path> ...") instead of a "SPEC:" line ->
  verifier_dispatch_hash_error(...) -> 'expected exactly one spec ref'   [exact match]

TEST 2 (subagent_type classification): same malformed prompt, subagent_type="verifier"
(generic), neutral description ->
  is_verifier_dispatch -> False
  is_coder_dispatch    -> False
  (neither gate branch fires -- confirms section 3's core finding)

TEST 3a-FIXED (Coder authorization, happy path): human turn -> plan-check-verifier dispatch
(run_in_background=False) with "SPEC: <real path>\nSPEC_SHA256=<real hash>" -> paired
tool_result = valid PLAN_PASS+PLAN_SUPPORT_JSON+REVIEWED_SPEC_SHA256 (same hash) -> Coder
dispatch, same turn ->
  authorize_coder_from_transcript -> True ''

TEST 3b-FIXED (turn-boundary exclusion): identical to 3a, but a genuine new human/orchestrator
message is inserted BETWEEN the Verifier's PASS result and the Coder dispatch ->
  authorize_coder_from_transcript -> False 'no prior successful paired Verifier result
  reviewed this spec hash'
  (current_turn() resets on any genuine new user-role, non-tool-result event -- a PASS from
  an earlier turn is invisible to a later turn's Coder dispatch, confirmed live)

TEST 3c-FIXED (generic "verifier" grants no credit): identical to 3a, but the Verifier
dispatch's subagent_type is "verifier" (not "plan-check-verifier"), neutral description,
otherwise a perfect same-turn same-hash PASS ->
  authorize_coder_from_transcript -> False 'no prior successful paired Verifier result
  reviewed this spec hash'
  (confirms section 3's second finding: a "verifier"-typed pass is real but non-crediting)

TEST 3d (background + real async completion also works): background-dispatched
plan-check-verifier + its actual <task-notification> completion event (not just the launch
stub), same turn ->
  authorize_coder_from_transcript -> True ''

TEST 3e (background stub alone is not yet credit-worthy): background-dispatched
plan-check-verifier, only the synchronous launch-ack visible (notification not yet arrived)
->
  authorize_coder_from_transcript -> False 'no prior successful paired Verifier result
  reviewed this spec hash'
  (correct/intended: a background Verifier that hasn't actually finished must not credit)

TEST 4 (Coder prompt marker edge cases):
  "SPEC: <path>\nSPEC_SHA256=<hash>"        -> extracts cleanly, hash matches
  missing "SPEC_SHA256=" entirely           -> None, 'expected exactly one SPEC_SHA256'
  hash in UPPERCASE hex (HASH_RE is [0-9a-f] only, lowercase) -> None, 'expected exactly one
  SPEC_SHA256'  (an uppercase-hex hash silently fails to match at all -- worth flagging since
  it's an easy real mistake)
  duplicated "SPEC:" line                    -> None, 'expected exactly one spec ref'
```

**Existing test-suite corroboration:** `hooks/test_spec_bound_verifier_credit.py`'s own
`ContentPrefixFallbackOnlyWhenOriginAbsentAC17` test independently proves the same
turn-boundary exclusion mechanism against a different, real-transcript-derived fixture
("a genuine human message... must still reset the window as a real turn boundary, excluding
the earlier Verifier+PASS from the Coder's credit window").

**Full suite run:** `python3 -m pytest hooks/test_spec_bound_verifier_credit.py -q` (111
tests) → **110 passed, 1 failed**. The one failure —
`ProductionAuthorizationBoundaryAC6::test_other_five_hooks_suites_stay_green_after_this_files_own_changes`
— is a meta-test that shells out to run 5 OTHER hook test files as one subprocess against its
own hardcoded 400-second timeout; that subprocess call itself hit `TimeoutExpired` at ~405-416s
both in the full run and re-run in complete isolation (no concurrent load) — i.e. it is a real,
reproducible timing gap in the meta-test's own budget vs. the actual combined runtime of those
5 suites on this machine, not a logic regression in any assertion about the credit gate's
behavior. All 110 tests that directly exercise `spec_bound_verifier_credit.py`'s actual
parsing/classification/authorization logic passed clean, both times.

## 6. Target file's exact current SHA-256 (recomputed fresh, not reused)

```
<HOME>/Claude/loop/loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md
7745e91e689f8091406ae5e7037ef2c150cfc9bd298ac5a1513e94cdc197b61b
```

Computed independently three times during this dossier: `shasum -a 256` (CLI), Python
`hashlib.sha256` (matches byte-for-byte), and a third re-check inside the live-verify script
moments before running the authorization tests (`assert T.sha256_of(SPEC_PATH) == SPEC_HASH`
passed). 58,123 bytes. This is the CURRENT, pre-edit hash — it is only valid for the Coder
dispatch (and only matches whatever a prior Verifier record reviewed) as long as the file's
bytes do not change between now and the dispatch; if anything touches the file first, this
value is stale and must be recomputed.

## Recommended marker lines for the Coder dispatch's `prompt` field

```
SPEC: <HOME>/Claude/loop/loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md
SPEC_SHA256=7745e91e689f8091406ae5e7037ef2c150cfc9bd298ac5a1513e94cdc197b61b
```

(Plus the repo-health markers from the prior dossier, in `prompt` or `description`:
`REPO_HEALTH_CLASSIFICATION=continuing-phase` / `REPO_HEALTH_REPO=loop`.)

**This is necessary but very likely NOT sufficient on its own.** These two lines only satisfy
`extract_spec_info`'s syntactic parsing. `prior_verifier_credit` separately requires an
ALREADY-EXISTING, same-session, same-turn (since the last genuine human/orchestrator message),
same-path+hash, `is_verifier_dispatch()`-qualifying record whose paired result is a validated
`VALID_PASS` (section 4) to already be sitting in the transcript. Given Oga's own account —
two `plan-check-verifier` attempts that were blocked before ever running (never produced a
result) and two `verifier`-typed dispatches that (per section 3, live-confirmed) grant no
credit even if their own content was a perfect PASS — there is a real, source-and-live-
confirmed risk that no qualifying credit currently exists, and the Coder dispatch could still
be denied with `"no prior successful paired Verifier result reviewed this spec hash"` — a
DIFFERENT error from the one already seen. **Recommended concrete sequence:** dispatch a fresh
`subagent_type="plan-check-verifier"` review with a prompt containing exactly one `SPEC:` line
and one `SPEC_SHA256=` line in this same format, let it actually run to completion (foreground,
or background plus the real notification — both live-confirmed to work), confirm its result
ends with `LOOP_GATE: PLAN_PASS` + `REVIEWED_SPEC_SHA256=7745e91e6...b61b` + a valid
`PLAN_SUPPORT_JSON=` citation, all **without a fresh human message intervening**, and only then
dispatch the Coder with the markers above.

## What I could not check (stated plainly, not guessed)

I do not have access to Oga's live orchestrator session transcript (I run as a separately
dispatched sub-agent with my own transcript) and per this role's data-access-scope rule,
reaching for it without explicit authorization is out of bounds anyway. I therefore cannot
confirm from here whether a qualifying Verifier record already exists in Oga's actual current
turn right now — the "very likely NOT sufficient" warning above is a source-and-mechanism-
grounded risk assessment, not a confirmed transcript read. Oga is in the only position to
check this directly (or simply attempt the dispatch and read whatever denial reason comes
back, if any).

## Sources (all opened directly)

- `<HOME>/Claude/loop/hooks/spec_bound_verifier_credit.py` (full file read,
  lines 1-676)
- `<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py:250-392`
- `<HOME>/Claude/loop/hooks/verifier_hygiene_scan.py:11-13` (`VERIFIER_DETECT`)
- `<HOME>/Claude/loop/hooks/test_spec_bound_verifier_credit.py` (fixture helpers
  read in full; `REAL_VERIFIER_SUBAGENT_TYPE = "plan-check-verifier"` constant at line 94;
  `ContentPrefixFallbackOnlyWhenOriginAbsentAC17` at line 890-933; full 111-test live run)
- Live re-execution of `verifier_dispatch_hash_error`, `is_verifier_dispatch`,
  `is_coder_dispatch`, `extract_spec_info_from_text`, and end-to-end
  `authorize_coder_from_transcript` against 8 constructed scenarios, all performed during this
  dossier's research (not merely read) — see section 5.
- Fresh `shasum -a 256` + Python `hashlib.sha256` (independently cross-matching) of the real
  target file, recomputed 3 times across this session.
