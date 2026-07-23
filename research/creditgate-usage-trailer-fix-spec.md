# FIX SPEC — Creditgate `<usage>` trailer structural block (restore foreground plan-check credit)

**Satisfies:** `fix_plan.md` → `H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1` (OPEN, URGENT, filed 2026-07-16)
**Root-cause dossier:** `research/creditgate-usage-trailer-structural-block-dossier.md`
**Regressing commit:** `4ace7a9` — "Harden plan-check evidence and worker identity guards" (implements `structural-planpass-evidence-guard`, 2026-07-16)
**Target:** `hooks/spec_bound_verifier_credit.py` → `result_plan_pass_status_for_hash`
**Status:** ready to build — hand off to whoever owns the fix_plan entry. Do **not** apply without first confirming no concurrent session owns `~/Claude/loop` (the worktree is dirty).

---

## Root cause (do NOT undo the hardening)

`4ace7a9` intentionally added an anti-smuggling rule: `LOOP_GATE: PLAN_PASS` must be the **final non-empty line** of the tool result (`spec_bound_verifier_credit.py:367-368`), pinned by the new test `test_support_or_hash_after_final_gate_is_rejected` ("AC4") and the `roles/verifier.md` contract *"Put no non-empty content after the final `LOOP_GATE:` line."* That rule is correct and must stay.

In the same refactor, the **foreground** `<usage>…</usage>` trailer-strip branch was dropped. The runtime appends a `<usage>…</usage>` block to **every** Agent-tool result, so a foreground plan-check result's true last line is the `<usage>` trailer — not the gate line — and the finality check fails. Net effect: **foreground plan-check credit is currently unsatisfiable by any real dispatch.** Background is unaffected (`NOTIF_RESULT_RE` strips the `<result>` envelope; the foreground path has no equivalent). This is an unforeseen side-effect of a deliberate hardening, not a design decision to revert.

## The fix (surgical, end-anchored strip — NOT a revert)

In `result_plan_pass_status_for_hash`, immediately after `text = tool_result_text(tool_result)` (currently ~line 354 — verify at apply-time) and before the line-split (~line 355):

```python
text = re.sub(r"\s*<usage\b[\s\S]*?</usage>\s*\Z", "", text)
```

- `\Z` anchors the strip to end-of-text, so it removes **only** the harness-appended trailer (which no model controls). `re` is already imported in this file.
- After the strip, the real final line (`LOOP_GATE: PLAN_PASS`, or the glued `…PLAN_PASSagentId:<id>` form the tolerance at ~396-423 already handles) is once again `lines[-1]`, the finality check at 367-368 passes, and control reaches the agentId branch that is currently dead.

**Do NOT restore the old `8d69cee`/parent consume-until-`</usage>` loop.** Its purpose was to *tolerate* `REVIEWED_SPEC_SHA256` / `agentId` / prose after the gate — exactly what AC4 now forbids. A tolerant revert reopens the trailer-smuggling hole `4ace7a9` just closed.

## Acceptance criteria (two-sided — the mutation guard is the crux)

1. **AC-1 restore credit** — a foreground-shaped result whose real final line is `LOOP_GATE: PLAN_PASS` followed by a harness `<usage>…</usage>` block → **credited** (`ok=True`) for the matching hash.
2. **AC-2 glued form** — same, but with the `…PLAN_PASSagentId:<id>` glued trailer + `<usage>` block → **credited** (reaches the agentId branch ~396-423).
3. **AC-3 smuggling still blocked (mutation oracle)** — a result with a **model-authored** non-empty line after `LOOP_GATE: PLAN_PASS` (e.g. a forged `REVIEWED_SPEC_SHA256=…` or `PLAN_SUPPORT_JSON` line, no `<usage>` wrapper) → **still rejected**. This case must stay RED with the fix applied (and is RED with or without the strip). If it ever goes green, the fix reopened the hole.
4. **AC-4 existing rule intact** — `test_support_or_hash_after_final_gate_is_rejected` still passes unchanged.
5. **AC-5 background unchanged** — background / notification-path credit is unaffected.

## Test guidance

Add a **foreground `<usage>` fixture** to the credit-gate test module (it currently carries `<usage>` only inside `<task-notification>` envelopes — that gap is precisely why this regression turned no test red). Include the AC-3 mutation case. Run the full module and record the **with-fix / without-fix delta**: AC-1/AC-2 flip green with the strip; AC-3 stays red both ways.

## Handoff notes

- **Correct the fix_plan entry:** `H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1`'s proposed fix says to reuse consume-until-`</usage>` logic *"still in this same file"* — **stale**; that logic now lives only in git history (`8d69cee` / parent of HEAD). Reimplement the end-anchored strip above instead.
- **Tree hygiene:** the target file is clean (== HEAD `4ace7a9`), but the worktree has other uncommitted work — confirm single ownership of `~/Claude/loop` before editing, and re-diff immediately before commit.
- On landing, close `H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1` citing the with/without-fix test delta as evidence.
