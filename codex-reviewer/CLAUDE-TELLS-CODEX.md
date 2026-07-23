# Claude → Codex review handoff (Claude-driven version)

Companion to `codex-review.sh` / `README.md`. That script is for a human to run from a
terminal. This file is for **Claude** (in a Claude Code / Cowork session) to follow when
the user asks for a Codex second opinion on code Claude just wrote or is about to ship —
e.g. "get Codex to review this," "have Codex check this diff," "second opinion from Codex."

Same artifact-handoff pattern as the shell script — no MCP session, no thread-id, no
credit-gate. Codex's verdict is **advisory only**. It never counts as the real PASS; a
Claude Verifier or the user still owns that.

---

## What Claude does, step by step

1. **Capture the diff.** Run via Bash:
   ```
   git diff > /tmp/codex-review-request.md      # unstaged
   # or: git diff --staged > ...                # staged
   # or: git diff <ref> > ...                    # vs a ref
   ```
   If the diff is empty, stop and tell the user there's nothing to review — don't fabricate
   a review of nothing.

2. **Write the review request file** (Claude does this with the Write tool, not by hand-typing
   in a prompt — Codex reads the file itself, so the diff never has to round-trip through
   Claude's own context as a second copy):
   ```
   # Code review request

   ## Diff
   ```diff
   <contents of the captured diff>
   ```
   ```

3. **Dispatch Codex via Bash**, read-only sandbox, one-shot:
   ```
   codex exec --sandbox read-only "You are an independent code reviewer giving a SECOND
   OPINION. You did not write this code. Read /tmp/codex-review-request.md and return ONLY:

   VERDICT: PASS | FAIL | PASS_WITH_CONCERNS
   SUMMARY: one sentence.
   FINDINGS: numbered, most severe first. file:line, what's wrong, concrete failure
     scenario (inputs -> wrong result). 'none' if none.
   MISSED_TESTS: cases this change should test but doesn't. 'none' if none.

   Be adversarial — try to find the bug, don't rubber-stamp. Default to FAIL if you
   cannot convince yourself the change is correct." > /tmp/codex-review-verdict.md
   ```
   (Check `codex exec --help` once per environment — flag names drift across CLI versions.
   `--sandbox read-only` is the load-bearing flag: it guarantees Codex cannot touch the repo.)

4. **Read the verdict back** with the Read tool — don't trust your own memory of what you
   piped in; read the actual file Codex wrote.

5. **Report to the user as a second opinion, not a verdict Claude endorsed by default.**
   - If `VERDICT: FAIL` or `PASS_WITH_CONCERNS`: surface every finding verbatim. Don't soften
     or summarize away specifics — the whole point of an adversarial second reviewer is the
     concrete failure scenario, not a vibe.
   - If `VERDICT: PASS`: say so plainly, but note it's one model's read, not a substitute for
     tests actually passing.
   - Never write or imply "Codex approved this, shipping now" as if that were a gate clearing.
     If the user's own process requires a logged independent-verifier PASS (loop-team's
     `LOOP_GATE: PLAN_PASS` convention, etc.), Codex's verdict is input to that decision, not
     a replacement for it.

## Guardrails (why these exist)

- **Read-only sandbox is non-negotiable.** Claude is already the one with write access to the
  repo; Codex's job here is to read and judge, never to edit. Don't drop `--sandbox read-only`
  to "let Codex fix it too" — that collapses the independence the second opinion is for.
- **File handoff, not inline prompt-pasting.** Keeps this working across Codex CLI versions
  (avoids the known MCP thread-id fragility) and keeps the diff a single source of truth
  instead of two copies that can drift.
- **Advisory boundary is the whole point.** The moment Codex's PASS auto-satisfies a real gate,
  this stops being a 5-minute spike and becomes the credit-gate/worker-identity machinery this
  was built specifically to avoid.

## When NOT to use this

- Routine single-file edits with no review requested — don't proactively shell out to Codex
  unasked; it's not free and it's not part of the default loop.
- Anything where the user wants Codex to *write* code, not review it — that's a different,
  bigger conversation about routing/credit than this spike covers.
