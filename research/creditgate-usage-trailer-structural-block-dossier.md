# Bug-fix dossier — H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1

**Mode B (Coder-unblock) research dossier.** Read-only investigation, 2026-07-16.
Grounds the URGENT gate-hole logged at `~/Claude/loop/fix_plan.md` ~line 9346.
Consuming work: that fix_plan entry + the spec a Coder will build to fix it.

**Target file:** `~/Claude/loop/hooks/spec_bound_verifier_credit.py` (at HEAD `4ace7a9`,
branch `fix/oga-guard-codex-worker-identity`).
**Bottom line:** the fix_plan entry's *mechanism* is CONFIRMED (empirically reproduced
against real bytes), but its *"reuse the older wrapper's logic still in this same file"*
claim is **REFUTED at HEAD** — that logic was deleted by the same commit that introduced the
bug and now survives only in git history / a sibling worktree. Fixture found: **YES.**

---

## 1. Confirmed root cause

### 1a. The ordering claim — CONFIRMED

`result_plan_pass_status_for_hash` spans **lines 343-447**. The relevant control flow:

```python
# line 361-368
    gate_positions = [
        (idx, ln) for idx, ln in enumerate(lines) if ln.startswith("LOOP_GATE:")
    ]
    if len(gate_positions) != 1:
        return False, "expected exactly one LOOP_GATE line"
    gate_idx, gate_line = gate_positions[0]
    if gate_idx != len(lines) - 1:
        return False, "LOOP_GATE: PLAN_PASS must be the final non-empty line"
```

The glued-`agentId` tolerance branch is **lines 397-426**, strictly *after* the final-line
check:

```python
# line 397-399
    if gate_line != "LOOP_GATE: PLAN_PASS":
        if not gate_line.startswith("LOOP_GATE: PLAN_PASSagentId:"):
            return False, "final gate line is not LOOP_GATE: PLAN_PASS"
```

CONFIRMED: the final-line check at **line 367** returns False at **line 368** before control
can ever reach the glued-`agentId` branch at line 397. (`lines` is the blank-filtered list
built at line 355: `lines = [ln.strip() for ln in text.splitlines() if ln.strip()]`, and
`text = tool_result_text(tool_result)` at line 354. `tool_result_text` (lines 261-268) returns
the raw content and does **not** strip any `<usage>` block.)

Note a subtlety the fix_plan slightly conflates: the glued `agentId:` sits on the *same* line
as the gate, so it does **not** by itself make the gate non-final. It is the **separate
`<usage>` block on subsequent lines** that trips line 367. The glue and the `<usage>` trailer
are two independent harness additions; only the second one causes *this* failure.

### 1b. The mechanism & "unsatisfiable" claim — CONFIRMED empirically

I imported the current module and ran `result_plan_pass_status_for_hash` against real
captured byte-strings (see §3). Results:

```
A_fg_oldcontract        -> ok=False  reason='LOOP_GATE: PLAN_PASS must be the final non-empty line'
B_notif_newcontract     -> ok=False  reason='LOOP_GATE: PLAN_PASS must be the final non-empty line'
C_fg_newcontract_glued  -> ok=False  reason='LOOP_GATE: PLAN_PASS must be the final non-empty line'
Ctl_gate_truly_last     -> ok=False  reason='no PLAN_SUPPORT_JSON support citation'   (gets PAST line 367)
```

Every real trailer shape fails at line 368; only a synthetic body whose gate is *literally*
the last non-empty line gets past it. Since the harness appends a `<usage>` block to every
Agent-tool result, the new final-line requirement is **unsatisfiable by any real dispatch** —
CONFIRMED. This is not a formatting issue a better-instructed Verifier can dodge.

### 1c. The "reuse the older wrapper's consume-until-closing-tag logic still in this same file" claim — REFUTED at HEAD (important correction for the Coder)

At current HEAD, `result_is_final_plan_pass_for_hash` (**lines 450-452**) is a **3-line
delegator with no tolerance logic of its own**:

```python
def result_is_final_plan_pass_for_hash(tool_result, reviewed_hash, cwd=None):
    ok, _reason = result_plan_pass_status_for_hash(tool_result, reviewed_hash, cwd=cwd)
    return ok
```

`grep -n "usage" hooks/spec_bound_verifier_credit.py` on HEAD returns **nothing** in either
function — the whole file has **zero `<usage>` handling**. The two functions do **not**
currently duplicate the tolerance; **neither has it**.

Git blame explains why. `git log -L 450,452:hooks/spec_bound_verifier_credit.py` shows commit
**`4ace7a9` ("Harden plan-check evidence and worker identity guards")** — the same commit that
landed H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1 — **rewrote** the old
`result_is_final_plan_pass_for_hash` into the new `result_plan_pass_status_for_hash` (adding
the `PLAN_SUPPORT_JSON` requirement) and, in doing so, **replaced the old tolerant
trailing-region while-loop with the strict `gate_idx != len(lines) - 1` check** and collapsed
the wrapper to a delegator. `4ace7a9` is the regression commit. `b16cc78` (its immediate
predecessor and an ancestor of HEAD, confirmed via `git merge-base --is-ancestor b16cc78
HEAD`) still had the working `<usage>` skip.

So the fix_plan's "still in this same file" is off by one refactor. The reusable logic is
recoverable (see §2), but the Coder must **port it from history / a worktree**, not reference
a live function that contains it.

---

## 2. The reusable tolerance logic (verbatim)

The consume-until-closing-tag `<usage>` skip does **not** exist at HEAD. It exists verbatim in
three read-only places:

- **git history:** `git show b16cc78:hooks/spec_bound_verifier_credit.py` (predecessor of HEAD)
- **sibling worktree copy (readable now):**
  `~/Claude/loop/worktrees/durable-proof-enforcement/hooks/spec_bound_verifier_credit.py`
  **lines 363-380** (branch `codex/durable-proof-enforcement` @ `838174e`, pre-`4ace7a9`)
- **unmerged branch:** `fix/credit-gate-usage-block` @ `0d4f877`
  ("fix(credit-gate): skip full multi-line `<usage>` block in
  result_is_final_plan_pass_for_hash") — NOT an ancestor of HEAD.

Verbatim (durable-proof-enforcement worktree, lines 363-380 — identical to b16cc78):

```python
    # existing trailing-validation loop (unchanged shape), operating on `trailing` only.
    i = 0
    n = len(trailing)
    while i < n:
        ln = trailing[i]
        if REVIEWED_HASH_RE.search(ln) or ln.startswith("agentId:"):
            i += 1
            continue
        if ln.startswith("<usage"):
            # The runtime's <usage> tail can span multiple (stripped) lines on a FOREGROUND
            # (synchronous) Agent result (subagent_tokens / tool_uses / duration_ms). Skip the
            # whole block, not just its first line, so a foreground plan-check PLAN_PASS is
            # credited the same as a background one.
            while i < n and "</usage>" not in trailing[i]:
                i += 1
            i += 1  # consume the line containing </usage> (or run off the end if unterminated)
            continue
        return False
```

`trailing` is defined just above it (worktree line 353): `trailing = lines[gate_idx + 1:]`.

**The `<usage>`-skip inner block (worktree lines 371-378) is the exact piece to reuse.**
**Caveat — do NOT port the whole while-loop verbatim:** the outer loop *also* tolerates a
trailing `REVIEWED_HASH` line and a trailing `agentId:` line (line 368). That was correct for
the OLD verifier.md convention (hash *after* the gate). The NEW convention puts the hash and
`PLAN_SUPPORT_JSON` *before* the gate, and the current test AC4
(`test_support_or_hash_after_final_gate_is_rejected`, §5) deliberately requires trailing
support/hash material to be **rejected**. So the fix must tolerate **only** a trailing
`<usage>...</usage>` block, not arbitrary trailing hash/agentId lines.

---

## 3. Real fixture bytes (FOUND — YES)

All captures below are byte-exact `repr()` extractions of real tool_result *content strings*
from live 2026-07-16 transcripts. I searched the dispatch-authorized locations
(`~/.claude/projects/`, in-repo `runs/` + `loop-team/runs/`) surgically — matching on the
co-occurrence of `LOOP_GATE: PLAN_PASS` + `</usage>` and extracting only the matching content
tails, not whole conversations.

### Capture B — the primary fixture: real NEW-contract PASS from the TaxAhead session
Source: `~/.claude/projects/-Users-eobodoechine/eab6d0fa-5082-4c03-be4f-078d9c6dbb2c.jsonl`
(session references `taxahead-connector-platform` 225×). This is the correct new-contract
order — `PLAN_SUPPORT_JSON` → `REVIEWED_SPEC_SHA256` → `LOOP_GATE: PLAN_PASS` — followed by a
real `<usage>` trailer. **Decoded** (real newlines shown):

```
PLAN_SUPPORT_JSON={"artifact_path":"<HOME>/Claude/Projects/taxahead-connector-platform/loop-team/runs/2026-07-15_mission-control-reconciliation/specs/spec.md","line_start":316,"line_end":346,"evidence_sha256":"7d9222de42b55b823061c9acf59fa3817746f2e861243a0a6b3ca526b4984e4d","claim":"AC6's two audit_refs entries (exact paths, sha256 hashes, and the assert-throws-on-first-failure masking behavior) were independently live-verified: ...","spec_sha256":"87564dc2e2eda6810de8b877211ffda1d1a071dd7973676fdc4e3259fdf44646"}
REVIEWED_SPEC_SHA256=87564dc2e2eda6810de8b877211ffda1d1a071dd7973676fdc4e3259fdf44646
LOOP_GATE: PLAN_PASS</result>
<usage><subagent_tokens>123220</subagent_tokens><tool_uses>39</tool_uses><duration_ms>732848</duration_ms></usage>
```

Two real details the Coder needs from this capture:
- **`<usage>` format #1 (notification / inline):** single line, nested tags —
  `<usage><subagent_tokens>N</subagent_tokens><tool_uses>N</tool_uses><duration_ms>N</duration_ms></usage>`.
- **Second glue variant:** the gate line here is `LOOP_GATE: PLAN_PASS</result>` — a glued
  **`</result>`** suffix (from `<result>...</result>` wrapping), *not* `agentId:`. If the fix
  only relaxes the final-line check, this capture then hits the glued-suffix branch (line 397)
  and is rejected because the suffix isn't `agentId:`. **Note:** when such a result arrives as
  a real `<task-notification>` event it goes through `NOTIF_RESULT_RE`
  (`<result>([\s\S]*?)</result>`, source line 20), which extracts the inner content ending at
  `LOOP_GATE: PLAN_PASS` and strips both `</result>` and the trailing `<usage>` — so that path
  may already pass. The failing path is when the same bytes arrive as a **raw foreground
  content-part** (bypassing notification extraction). Flag for the spec author: decide whether
  `</result>`-glue tolerance is in scope, or rely on notification extraction to handle it.

### Capture A — real FOREGROUND multi-line `<usage>` format
Source: `~/.claude/projects/-Users-eobodoechine/73a73d31-b80b-43e9-a9bd-d80481da0c85.jsonl`
(the live debugging session, mtime 2026-07-16T02:06). **Decoded:**

```
...No other section was re-reviewed, per scope.

LOOP_GATE: PLAN_PASS
REVIEWED_SPEC_SHA256=273f567bda4b1e1370ddf1963e439d0c72e54d7e9d4042aba73dcce44a767185
agentId: a44af2e1a6acca237 (use SendMessage with to: 'a44af2e1a6acca237', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 124319
tool_uses: 8
duration_ms: 619020</usage>
```

Real details:
- **`<usage>` format #2 (foreground / multi-line):** three physical lines, colon-space —
  opens `<usage>subagent_tokens: N`, then `tool_uses: N`, then `duration_ms: N</usage>`.
  **The fix's consume-until-closing-tag must handle BOTH formats** (single-line and
  multi-line). The `while ... "</usage>" not in trailing[i]` walk handles both: single-line
  matches on its own line; multi-line consumes to the `</usage>`-bearing line.
- **Real `agentId:` line format (separate-line variant):**
  `agentId: <id> (use SendMessage with to: '<id>', summary: '<5-10 word recap>' to continue this agent)`.
- This capture is the OLD convention (hash *after* gate), so under a *narrow* `<usage>`-only
  fix it would still be rejected (trailing hash + agentId lines) — that's acceptable; it is not
  the new-contract shape. Use it only for the authentic multi-line `<usage>` bytes.

### The glued-`agentId` variant (from the source's own comment, source lines 376-377)
The current file documents the real glued form verbatim:
`LOOP_GATE: PLAN_PASSagentId: a6792fad616e56f8f (use SendMessage with to: ...)`.

**Recommended regression fixture (built from real components):** new-contract body
(`PLAN_SUPPORT_JSON=` → `REVIEWED_SPEC_SHA256=` → gate) with the gate line carrying a glued
`agentId:` suffix, followed by a real `<usage>` block — parametrized over **both** `<usage>`
formats. This is capture "C" in my repro (all three fail identically at line 368). Every byte
is sourced from a real capture above; only the assembly is ours.

---

## 4. Call sites & blast radius

`grep -rn "result_plan_pass_status_for_hash\|result_is_final_plan_pass_for_hash" hooks/`:

- **`result_plan_pass_status_for_hash`** — defined line 343.
  - **Production authorization path:** called at **line 552** inside `prior_verifier_credit`
    (`pass_ok, pass_reason = result_plan_pass_status_for_hash(result, coder_info["hash"], ...)`),
    which is reached from `authorize_coder_from_transcript` (line ~528). This is the function
    that authorizes every Coder dispatch and the PreToolUse Coder-dispatch credit gate. **This
    is why the bug "blocks EVERY Coder dispatch."**
  - Called by the wrapper at line 451.
- **`result_is_final_plan_pass_for_hash`** — the thin wrapper (lines 450-452); used by ~30
  existing tests and older call sites that only need a bool.

**What an incorrect fix would break (regression traps):**
- Dropping / weakening the final-line check wholesale would **reopen the "textually last wins"
  decoy-verdict hijack** the D.2.e comment (source lines 357-360) and AC4 (§5) defend against.
  The fix must keep rejecting a *decoy* trailing `LOOP_GATE`/support/hash line while tolerating
  *only* a `<usage>` block.
- The glued-suffix decoy scans (source lines 409, 425) must remain — they guard against
  `agentId:`-suffix injection proven exploitable live (comments at lines 386-396).
- The `PLAN_SUPPORT_JSON`-before-gate evidence binding (lines 428-447) must remain intact; the
  fix is only about what may follow the gate line.

---

## 5. Existing tests — what changes, what's added, fixture-tautology flags

File: `~/Claude/loop/hooks/test_spec_bound_verifier_credit.py`.

**Fixture-tautology CONFIRMED (the bug's hiding place).** The 5 tests in class
`StructuralPlanSupportJsonEvidenceBinding` (line 2469) — the ones cited as "5 passed" in the
H-STRUCTURAL slice's evidence — build their body with `plan_support_result_body` (lines
2461-2466):

```python
def plan_support_result_body(spec_hash, support_json):
    return (
        "PLAN_SUPPORT_JSON=%s\n"
        "REVIEWED_SPEC_SHA256=%s\n"
        "LOOP_GATE: PLAN_PASS"      # <-- gate is literally the last bytes; no <usage>, no glue, no trailing \n
    ) % (support_json, spec_hash)
```

`plain_result` (lines 1091-1098) wraps this into a raw `{"type":"tool_result","content":...}`
that **bypasses the notification machinery** — i.e. it uses the same raw path a real
foreground result uses — but the body **never carries the `<usage>` trailer that every real
dispatch appends**. So `test_valid_support_json_with_recomputed_span_hash_is_accepted` (line
2508) is green *only* because its fixture is the one shape the harness never actually produces.
This is precisely the "fixture tautology" lesson (`loop-team/learnings.md`, 2026-06-24).

**No existing test exercises the raw-inline `<usage>` path.** The other `<usage>` fixtures
(test lines 163, 264) are embedded inside `<task-notification>...</result>\n<usage>...</usage>
\n</task-notification>` wrappers, which go through `NOTIF_RESULT_RE` and have the `<usage>`
**stripped** before the gate check — so they never hit line 367 with an inline `<usage>`.

**Test that must be preserved (tension to respect):**
`test_support_or_hash_after_final_gate_is_rejected` (AC4, line 2558) asserts that a trailing
`PLAN_SUPPORT_JSON=` line or a trailing `REVIEWED_SPEC_SHA256=` line after the gate is
**rejected**. The fix must keep both of those red while turning a trailing `<usage>` block
green. A narrow `<usage>`-only tolerance satisfies both.

**Changes vs. additions:**
- **Change:** none of the current assertions need to flip. (AC4's two cases stay rejected; the
  valid-body case stays accepted.)
- **Add:** new cases asserting `result_plan_pass_status_for_hash` (and the wrapper) return
  `True` for a valid new-contract body **plus** a trailing `<usage>` block — parametrized over
  **both** real `<usage>` formats (multi-line colon; single-line nested-tag) and over
  gate-line-clean vs. gate-line-with-glued-`agentId`. Build these from the real bytes in §3.
- **Add (negative):** a trailing non-`<usage>` decoy line after the gate (e.g. a second
  `LOOP_GATE`, or trailing support/hash) still returns `False` — proving the tolerance stayed
  narrow and the decoy-hijack defense is intact.
- **Recommended:** strengthen the module's real-fixture corpus with capture B verbatim, so the
  new-contract + trailer shape is frozen from real data.

---

## 6. Collision / worktree recommendation

- **`git status --short`:** `hooks/spec_bound_verifier_credit.py` is **CLEAN** — it has **no
  uncommitted changes** right now (committed at HEAD `4ace7a9`). The only modified files in the
  root tree are unrelated (`test_fixplan_closure_lint.py`, `test_plancheck_saturation.py`,
  `learnings.md`, `research/SOURCES_INDEX.md`, `scripts/test_snapshot_publish.py`).
- **`git log --oneline -8 -- hooks/spec_bound_verifier_credit.py`:**
  `4ace7a9` (regression) → `2a4f1b1` → `0848717` → `b16cc78` (last good `<usage>` skip) →
  `8d69cee`. Root repo is on branch `fix/oga-guard-codex-worker-identity`.
- **Worktrees touching this file:** `worktrees/durable-proof-enforcement`
  (branch `codex/durable-proof-enforcement` @ `838174e`) holds a **pre-`4ace7a9`** copy of the
  file (the old while-loop structure) — divergent, do not build there. `worktrees/
  mission-control-slice1-proof` also exists. Branch `fix/credit-gate-usage-block` (`0d4f877`)
  carries the unmerged multi-line `<usage>` fix and is **not** an ancestor of HEAD.
- **`ps aux | grep -i claude`:** multiple live claude-code sessions are running (≥5 stream-json
  processes; one is this Researcher's own opus-4-8 session, several sonnet-5 sessions, plus a
  padsplit-cockpit vitest run). The fix_plan explicitly warns this file is under **live active
  development** by whoever is landing `verifier-credit-citation-permanent-fix` (run dir:
  `loop-team/runs/2026-07-15_verifier-credit-citation-permanent-fix/`).

**Verdict:** the file is clean *this instant*, but with multiple live sessions and an in-flight
credit-gate fix on this exact file, do the fix in a **fresh worktree branched from current HEAD
`4ace7a9`** (one session per worktree, per standing practice) — do **not** reuse
`durable-proof-enforcement` or `fix/credit-gate-usage-block` (divergent branches, stale file
structure). Re-check `git log`/`git status` on this file immediately before landing, since a
concurrent session may commit to it first.

---

## 7. Recommended fix shape (for the spec author — not a spec)

Both options keep the `PLAN_SUPPORT_JSON`-before-gate binding (lines 428-447) and the
glued-`agentId` decoy scans (lines 397-426) fully intact. The only change is what may follow
the gate line.

**Option 1 (preferred — narrow trailing-`<usage>` tolerance).** Replace the hard
`if gate_idx != len(lines) - 1: return False` (lines 367-368) with a check that the region
after the gate consists of **at most one tolerated `<usage>...</usage>` block and nothing
else**. Port the consume-until-closing-tag walk from the durable-proof-enforcement worktree
**lines 371-378** (§2), applied to `trailing = lines[gate_idx + 1:]`: allow a run that starts
with a `<usage`-prefixed line and consume through the line containing `</usage>`; if any
non-empty line remains after that (or a trailing line is not part of a `<usage>` block), return
False (`"unexpected content after final gate line"`). This keeps AC4's trailing-support/hash
rejection green (those aren't `<usage>` blocks) and the decoy-hijack defense intact, while
turning every real trailer shape in §3 green. Handles **both** `<usage>` formats because the
walk keys only on `startswith("<usage")` and `"</usage>" in line`.

**Option 2 (fold into the glued-suffix branch).** Keep line 367 but treat a trailing pure
`<usage>` block as "gate is effectively final": compute an effective last index by skipping a
trailing `<usage>...</usage>` block before comparing to `gate_idx`. Functionally equivalent;
Option 1 is cleaner because it reuses the proven walk verbatim and states the intent directly.

**Do not** re-port the *entire* old while-loop (it also tolerated trailing `REVIEWED_HASH` and
`agentId:` lines, which the new AC4 wants rejected). Reuse only the `<usage>` inner block.

**Falsifiable check for the Coder's fix:** after the change,
`result_plan_pass_status_for_hash` returns `True` for the new-contract body + trailing
`<usage>` block (both formats, clean gate and glued-`agentId` gate) with a matching on-disk
support span; returns `False` for the same body with a trailing decoy `LOOP_GATE`/support/hash
line; and the full suite (`python3 -m pytest hooks/test_spec_bound_verifier_credit.py -q`) stays
green including AC4 (`test_support_or_hash_after_final_gate_is_rejected`) and the
`StructuralPlanSupportJsonEvidenceBinding` class.

---

### Provenance / honesty notes
- Every code quote is from the real files at the stated paths/commits (HEAD `4ace7a9`; sibling
  worktree; `git show b16cc78`), not from the fix_plan's prose.
- The empirical repro (§1b) ran the **current** module against real captured bytes; the
  `reason` strings are verbatim program output.
- Real fixtures were read surgically from dispatch-authorized transcript locations by matching
  the `LOOP_GATE: PLAN_PASS` + `</usage>` co-occurrence and extracting only the matching
  content tails.
- I did **not** edit any source, spec, or the fix_plan entry (Researcher scope).
