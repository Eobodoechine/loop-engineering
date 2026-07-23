# Diagnosis + proposed fix: Stop-guard hygiene scan replays a PreToolUse-BLOCKED dispatch

**Mode:** A (loop-improvement diagnosis, not a build)
**fix_plan entry:** `H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1` (OPEN, filed 2026-07-10)
**Author dispatch:** loop-team Researcher, 2026-07-10
**Status:** root cause CONFIRMED (grounded in code + CC docs/issue); fix DESIGNED, not built.

---

## 1. Root cause (confirmed, not guessed)

`hooks/loop_stop_guard.py` builds `_TOOL_USES` (line 165) from **every** `tool_use`
content-part in the current turn, with **zero filtering** for calls that a PreToolUse
hook denied before execution:

```python
_TOOL_USES   = [p for p in _parts(turn) if p.get("type") == "tool_use"]      # line 165
_TOOL_RESULTS= [p for p in _parts(turn) if p.get("type") == "tool_result"]   # line 166
```

The Verifier-dispatch hygiene gate (lines 1465-1478) then walks `_TOOL_USES` in
transcript (chronological) order and **breaks on the first** `_VERIFIER_DETECT` match
whose prompt carries a hygiene marker:

```python
for _tu in _TOOL_USES:                                   # line 1468
    if _tu.get("name","").lower() not in ("task","agent","subagent","workflow"):
        continue
    _desc = _tu_dispatch_text(_tu)
    if not _VERIFIER_DETECT.search(_desc):
        continue
    _prompt = _tu_dispatch_prompt_text(_tu)
    _mk = _shared_evaluate_hygiene(_prompt, _known)       # markers from verifier_hygiene_scan.hyg_markers()
    if _mk:
        _hyg_violation = (_desc[:60], _mk)
        break                                            # <-- first match wins, no live/blocked distinction
```

The loop has **no correlation to the tool_use's tool_result** and **no notion of a
blocked call**. So when the turn contains:

1. attempt #1 — a Verifier dispatch containing `"tests passed"`, **denied pre-dispatch**
   by the PreToolUse hygiene gate (`pre_tool_use_oga_guard.py` lines 352-369, which
   `print`s a `permissionDecision:"deny"` and `sys.exit(0)`), then
2. attempt #2 — a rewritten, byte-clean Verifier dispatch that actually ran,

…both `tool_use` blocks live in `_TOOL_USES`, attempt #1 sorts first, and the scan
matches its marker and blocks — exactly the observed symptom. The live dispatch #2 is
never reached because of the `break`. This matches the fix_plan "Found" evidence
byte-for-byte.

### Why a blocked call is even in the transcript (the load-bearing fact)

A PreToolUse `deny` does **not** erase the tool call. Confirmed against the CC docs and
a live-runtime issue report:

- The assistant's `tool_use` block **still appears** in the transcript.
- A `tool_result` **is** generated for the denied call. On the current runtime its
  content is the **generic** string `"Hook PreToolUse:<Tool> denied this tool"` (the
  `permissionDecisionReason` is, per the open bug, not surfaced) — e.g.
  `"Hook PreToolUse:Agent denied this tool"`.

So a blocked dispatch is distinguishable: it has a correlated `tool_result` (matched by
`tool_use_id`) that carries a **PreToolUse-deny signature** in its content (and is
flagged as an error result). A genuinely-dispatched call instead has a normal success
result — and for Agent/Task specifically, a raw JSONL event whose `toolUseResult`
carries an `agentId` (already relied on by this same file at lines 552-558).

This answers the open question the fix_plan entry left ("synthetic error tool_result vs.
no tool_result at all"): **it IS a tool_result, carrying a deny-signature string.**

---

## 2. The scan already has the correlation primitive it needs

This file **already** correlates a tool_use to its tool_result by `tool_use_id` in two
places — the fix is to reuse that idiom, not invent one:

- Researcher gate, lines 1361-1369: builds `_rh3_returned_ids` = `{tr.tool_use_id …}`.
- Run-log gate, lines 1578-1583: matches `_rl_tu_id == (tr.tool_use_id or tr.id)`.

The `tool_result` reader `_tr_text(tr)` (line 690) already lower-cases content, so a
content-signature check is a one-liner over `_TOOL_RESULTS`.

---

## 3. Proposed fix (two candidate mechanisms, one recommended)

Build a `_blocked_tool_use_ids` set **once**, right after `_tr_text` is defined (≈ line
694), then add a single skip-guard at the top of each affected `_TOOL_USES` walk.

### Candidate A — key off `is_error` alone
```python
_blocked = {tr.get("tool_use_id") for tr in _TOOL_RESULTS if tr.get("is_error") is True}
```
- **Pro:** trivial, structural boolean.
- **Con:** too broad — also excludes a Verifier that *actually ran* and then errored
  (different failure, arguably should still be scanned); and `is_error` presence is not
  documented as guaranteed across runtimes (if absent, the set is empty → silently
  no-ops).

### Candidate B — key off the PreToolUse-deny content signature (RECOMMENDED)
```python
def _tr_is_pretooluse_deny(tr):
    txt = _tr_text(tr)                        # already lowercased
    return ("denied this tool" in txt        # generic CC deny string (current runtime)
            or ("pretooluse" in txt and "deny" in txt)
            or "blocked before dispatch" in txt   # OGA-GUARD reason text, if a fixed
            or "[oga guard]" in txt)              #   runtime surfaces permissionDecisionReason
_blocked_tool_use_ids = {
    (tr.get("tool_use_id") or tr.get("id"))
    for tr in _TOOL_RESULTS
    if _tr_is_pretooluse_deny(tr) or tr.get("is_error") is True   # B, hardened with A as an OR
}
_blocked_tool_use_ids.discard(None)
```
Then in each walk:
```python
_tu_id = _tu.get("id") or _tu.get("tool_use_id")
if _tu_id and _tu_id in _blocked_tool_use_ids:
    continue
```

**Why B over A:** (1) It is grounded in the *concretely documented* tool_result content
(`"Hook PreToolUse:<Tool> denied this tool"`, GH issue #59643) rather than an
unconfirmed field. (2) It is **precise** to PreToolUse denials — it does not wrongly
skip a genuinely-dispatched-but-errored Verifier. (3) It covers **both** the current
generic-string runtime **and** a future runtime that surfaces the OGA-GUARD reason text
(the `"[oga guard]" / "blocked before dispatch"` terms match the exact strings
`pre_tool_use_oga_guard.py` emits at lines 358-365 / 377-384). (4) Adding `is_error` as
an OR term is a free robustness hedge. (5) **Fail-safe direction:** if the signature
ever fails to match (version drift), the guard no-ops and we are back to *today's known
false positive* — never a NEW false negative. This matches the file's own repeatedly
stated "over-fire is the safe direction" stance.

**Transfer-condition note (per researcher.md):** the mechanism requires only that a
denied call leaves a correlated, signature-bearing `tool_result` in the same transcript
the Stop hook already reads — which is the runtime's own behavior, not something a
participant must remember to do. The guarantee is therefore **structural**, not
instructional; a compliance failure cannot silently produce a wrong pass (it degrades to
the pre-existing over-fire).

---

## 4. Blast radius — this is a CLASS, not a single line

The "walk `_TOOL_USES`, treat every entry as a live event" shape recurs. Per this
project's own "name the complete class" rule, the sweep:

### Within `loop_stop_guard.py` — same file, other consumers

| Site | Line | Direction if a BLOCKED dispatch is counted | Severity |
|---|---|---|---|
| **Hygiene scan** (reported bug) | 1468 | false POSITIVE — blocks a clean turn | noise (safe-ish) |
| **Adjacency scan** (sibling) | 1529 | false POSITIVE — same class | noise (safe-ish) |
| **`VERIFIER` positive signal** | 743 | **false NEGATIVE** — a blocked Verifier satisfies `not VERIFIER`, so the **FEATURE gate (1116) passes feature work with no real verifier** | **dangerous** |
| **`_seen_verifier_anywhere`** | 1219-1220 | **false NEGATIVE** — a blocked plan-check Verifier suppresses `_plan_check_violated` (1250), licensing a Coder with no real plan-check | **dangerous** |
| `_seen_coder_anywhere` | 1221/1245 | false POSITIVE — a blocked Coder can trip PLAN_CHECK | noise (safe-ish) |
| Researcher gate `_rh3_returned_ids` | 1362-1408 | a blocked Researcher dispatch's deny-result id counts as "returned evidence" → can arm RESEARCH_GATE | noise (safe-ish) |
| `_rh_structural_writes()` | 769-783 | a denied code Write/Edit still counts as a structural write (feeds ROLE_OR_HARNESS / closure classifiers) — but a denied edit never lands on disk; direction is over-fire | low |
| **Run-log gate** | 1573-1585 | **self-protected** — requires `verdict:\s*pass` in the *correlated* result; a deny-result never matches | none |

The two **dangerous** rows are the real reason to treat this above the fix_plan entry's
own `priority: LOW` — that LOW was assigned looking only at the false-positive-noise
angle and **missed the false-negative instances** where a blocked Verifier satisfies the
FEATURE / PLAN_CHECK gates. Recommend applying the `_blocked_tool_use_ids` skip to
**all four** load-bearing sites (1468, 1529, 743, 1206-loop), not just the hygiene gate.
(Researcher does not re-prioritize fix_plan entries — flagging this to Oga per role
guardrails.)

### Sibling gate hooks (task item 5)

- **`micro_step_gates.py` — LOW/None.** Its gates AND-gate the tool_use signals against
  **real git working-tree state** (`_dirty_code_files(target)`, `git log` epoch — lines
  388-409, 428). A blocked edit/dispatch that changed nothing on disk cannot by itself
  trip a gate. This is the project's own "verify against reality, not artifacts"
  principle protecting it. Not a reachable dangerous instance.
- **`subagent_stop_gate.py` — REACHABLE, same class.** Its closure-touch scan (Fifth
  responsibility, `_cts_*`, lines 387-415 → `closure_touch_scan.find_touched_closed_headings`,
  which keys on `write/edit/multiedit` inputs targeting `fix_plan.md`, lines 99-118 of
  `closure_touch_scan.py`) and commit-scope scan (Fourth responsibility, `_cv_*`, lines
  283-315) read the **sub-agent's own** Write/Edit/Bash tool_uses with **no deny/is_error
  filter**. A sub-agent's `fix_plan.md` Edit that the OGA-guard PreToolUse *denies* (the
  known H-GUARD-4 sub-agent misfire) would still be counted as "touched a CLOSED heading"
  → a false `.closure_violation` flag. Same fix pattern applies, but note the deny
  signature would live in the **sub-agent** transcript, and the exposure is gated on the
  separate H-GUARD-4 misfire firing. Lower priority than the loop_stop_guard sites but
  the same root class.

---

## 5. Test-coverage gap (checked — genuinely absent, not a fixture-tautology)

There is **no** existing fixture for a blocked-then-retried dispatch. Grep of all
`hooks/test_*.py` for `"denied this tool"`, an `is_error: true` tool_result, or a
"first attempt blocked → clean retry" sequence returns nothing. The hygiene-gate tests
(`hooks/test_verifier_hygiene_gate.py`) all use **single**-dispatch fixtures
(`test_b_green_leak_in_added_context_blocks`, `test_c_pasted_decision_log_blocks`, etc.)
with one Verifier tool_use and a plain (non-deny) or absent tool_result. The nearest
"second dispatch" test (`test_loop_stop_guard.py:423 test_flag_consumed_second_dispatch_blocks`)
is about the **plan-pass flag TTL credit**, not a blocked→clean sequence. So this is a
true coverage hole (absence), **not** the "fixture doesn't match real transcript shape"
tautology class from `learnings.md`. The fix must ship a **red-first** fixture that
constructs a deny-shaped tool_result (content `"Hook PreToolUse:Agent denied this tool"`,
`is_error: true`) for a dirty attempt #1, correlated by `tool_use_id`, followed by a
clean attempt #2 — and asserts the Stop hook exits **0**. A second fixture (dirty
attempt that RAN, normal success result) must still exit 2, to prove the exclusion did
not weaken the real gate.

---

## 6. Falsifiable check for the eventual build

- **Red-before:** the blocked→clean fixture above → today's code exits 2 (reproduces the
  bug). After the fix → exits 0.
- **Guard-not-weakened:** a genuinely-dispatched dirty Verifier (marker in a *success*
  result's dispatch) → still exits 2 before and after.
- **Mutation check (per the project's AC oracle-targeting gate):** delete the
  `if _tu_id in _blocked_tool_use_ids: continue` line → the blocked→clean fixture must go
  red, proving the fixture actually exercises the new code path.

---

## 7. Sources (opened + quoted)

- **GH issue anthropics/claude-code#59643** — "PreToolUse hook deny reason not surfaced
  to agent's tool_result (v2.1.143)." Confirms: the denied call's `tool_use` still
  appears; a `tool_result` **is** generated; its content is the generic
  `"Hook PreToolUse:Bash denied this tool"` (reason not surfaced).
  https://github.com/anthropics/claude-code/issues/59643
- **Claude Code Hooks reference** — PreToolUse `deny` "Blocks the tool call"; "Claude
  Code reads the JSON decision, blocks the tool call, and shows Claude the reason";
  exit-2 semantics table. https://code.claude.com/docs/en/hooks
- **In-repo (this session, read in full):** `hooks/loop_stop_guard.py`
  (`_TOOL_USES` build line 165; hygiene gate 1465-1489; adjacency 1522-1550; `VERIFIER`
  743-746; coder/verifier loop 1206-1250; FEATURE gate 1116-1129; existing tool_use↔result
  correlation 1361-1369, 1578-1585; `agentId` use 552-558);
  `hooks/verifier_hygiene_scan.py` (`hyg_markers()` 24-29; `evaluate_hygiene` 76-85);
  `hooks/pre_tool_use_oga_guard.py` (Verifier-hygiene deny 261-390);
  `hooks/subagent_stop_gate.py`, `hooks/micro_step_gates.py`, `hooks/closure_touch_scan.py`.

---

## 8. Radar scoring (per orchestrator.md "Prioritizing radar candidates")

| sub-score | value | reason |
|---|---|---|
| effect | 0.35 | Real correctness gain (kills a false positive + closes two false-negative gate holes) but narrow; no current suite case measures it — needs a new regression case. |
| confidence | 0.85 | Root cause confirmed live + grounded in CC docs/issue for the transcript shape; a diagnosed bug, not a speculative technique. |
| phase_fit | 0.90 | Gate/verifier hardening = the "always relevant" cross-cutting category; hardens core Stop-guard infra. |
| risk_reduction | 0.60 | Removes a false-negative where a blocked Verifier satisfies FEATURE/PLAN_CHECK, plus the habituation risk of dismissing Stop-hook feedback. |
| uncertainty | 0.15 | Low — mechanism fully understood, not an exploration. |
| cost_to_test | 0.10 | One shared set + 4 one-line skips + 2 fixtures; config-swap tier. |

`priority = 0.40·(0.35×0.85) + 0.20·0.90 + 0.15·0.60 + 0.10·0.15 − 0.15·0.10 ≈ **0.39**`

**Triage: IMPLEMENTABLE_NOW** (self-contained, in-repo, no new deps). Recommend Oga
re-rate the fix_plan entry above `LOW` given the two dangerous-direction instances the
original filing missed.
