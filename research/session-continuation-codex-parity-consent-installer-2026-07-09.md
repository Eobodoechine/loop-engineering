# Session continuation — Codex parity + consent-gated installer

**Status as of 2026-07-09: VERIFIED PASS. Nothing committed yet.**

## Why this doc exists

This build (Codex enforcement parity for `RUNLOG_MISSING` + checkpoint gates, plus a
consent-gated cross-tool installer for `github.com/Eobodoechine/loop-engineering`)
went through the full loop: research → 3 rounds of plan-check → test-writer (68 tests)
→ Coder → independent Verifier (PASS, with real mutation-testing and live-execution
evidence, not just pytest trust). Full history and reasoning live in the sibling files
in this directory — read those for the "why," this doc is the "what's left."

Nnamdi disclosed mid-build that other live sessions are editing `~/Claude/loop/`
directly (same directory, not separate worktrees) right now. To avoid further
collision risk, the remaining work moves to an isolated `git worktree` rather than
continuing in the shared directory. **This doc is the handoff for whoever/whatever
continues that work.**

## Read these first, in this order

1. `spec-codex-parity-and-consent-installer-2026-07-09.md` — the frozen, 3-times-plan-checked spec. Do not reinterpret its design.
2. `run-logging-enforcement-gap-codex-vs-claude-code-2026-07-09.md` (+ its checkpointing addendum) — the original root-cause research this whole build exists to fix.
3. This doc — current status and exactly what's left.

## What's genuinely done (do not redo)

- Spec: PLAN_PASS, round 3, independently re-verified with real primary-source evidence (actual Codex rollout files, actual live Claude Code transcripts) and a mutation-style analysis of the adversarial test-fixture pair.
- Tests: 68 tests across 8 files (listed below). Written before implementation existed.
- Implementation: Deliverables A (Codex adapter), B (consent installer), C (fallback docs) — all built.
- Independent verification: **PASS**. The Verifier ran every test file itself (not trusting the Coder's self-report — which turned out to be stale on one count, see below), read the actual implementation code, and additionally:
  - Wrote a mutation test (weakened `_detect_runtime()` to the exact naive substring-scan the design forbids) and confirmed 6 tests go red — proof the test oracle is real, not vacuous.
  - Live-executed the installer with a real `pty.fork()` in a scratch `$HOME` — confirmed genuine JSON-merge (byte-for-byte preservation of unrelated existing config), fail-closed on no-tty, loud abort on malformed JSON, silent no-op on repeat installs.
  - Found the Coder's "9 pre-existing Phase4AC failures" claim did not reproduce (re-run came back 292/292 clean) — almost certainly a concurrent session's in-flight work that has since landed. Treat all self-reports from this build's Coder/test-writer with the same skepticism; independent re-verification is what caught this.

## Exact file list touched by this build (scope ALL git/file operations to this list)

**Created:**
- `hooks/codex_transcript_adapter.py`
- `hooks/test_codex_transcript_adapter.py`
- `hooks/test_codex_parity_gates.py`
- `hooks/_codex_fixture_builders.py`
- `loop-guards/detect_install_state.py`
- `loop-guards/install.py`
- `loop-guards/README.md`
- `loop-guards/bootstrap/CLAUDE_MD_SNIPPET.md`
- `loop-guards/bootstrap/AGENTS_MD_SNIPPET.md`
- `loop-guards/tests/_install_test_helpers.py`
- `loop-guards/tests/_tty_harness.py`
- `loop-guards/tests/test_detect_install_state.py`
- `loop-guards/tests/test_install_consent.py`
- `loop-guards/tests/test_install_merge_and_safety.py`
- `loop-guards/tests/test_loop_guards_docs.py`

**Modified (pre-existing files — additive only, gated behind `_detect_runtime()=="codex"`, zero change to existing Claude Code code paths):**
- `hooks/loop_stop_guard.py` (+49 lines)
- `hooks/micro_step_gates.py` (+92 lines)

**None of this is committed.** It exists only as uncommitted changes in `~/Claude/loop/`'s working directory.

## What's NOT done — pick up here

1. **Move to an isolated worktree first**, before anything else below. `~/Claude/loop` has **no git remote** (confirmed earlier in this build) — do NOT use the `EnterWorktree` tool, which defaults to tracking `origin/<branch>` and will fail or silently misbehave on a remoteless repo. Use `git worktree add <path> -b <new-branch-name> HEAD` directly instead. Since the file list above is uncommitted, `git worktree add` alone will NOT bring those files into the new worktree — they must be copied (plain file copy) from `~/Claude/loop/` into the new worktree path after it's created.

2. **fix_plan.md logging** — Nnamdi wanted to decide timing on this given the shared-directory situation. Once in the isolated worktree, logging to that worktree's own `fix_plan.md` (or the canonical one, if safe) still needs his go-ahead if not already given.

3. **Git commit** — explicitly gated by Nnamdi on confirming the other concurrent sessions are clear. Do not commit until that's separately confirmed, regardless of which worktree you're in — the eventual merge back to the shared history still needs that coordination.

4. **[Non-blocking follow-up] Fix AC-4b byte-level pre-assertions** — `hooks/test_codex_transcript_adapter.py` lines ~424 and ~441 (class `TestAC4bAdversarialEmbeddedTextCollisionPair`) assert on raw unescaped JSON bytes that can never appear in valid output from `_codex_fixture_builders.py`'s `write_jsonl()` (which correctly uses `json.dumps()`, so embedded quotes are always escaped). This is a genuine bug in the test fixture, not the implementation — confirmed by the Verifier's mutation test. Fix: assert against the escaped form, or better, assert against the parsed structure instead of raw bytes. This is test-writer work, not Coder work — do not let a Coder "fix" this by weakening the assertion's intent.

5. **[Optional, non-blocking] Codex thrash-gate timestamp parity** — `micro_step_gates.py`'s `_codex_thrash_past_green()` uses transcript line-order instead of each Codex event's real embedded ISO8601 timestamp compared against `git log` epoch (unlike the Claude Code path, which does use real timestamps). Verifier judged this acceptable as shipped: the only failure direction is over-firing (forcing an unnecessary extra commit), never under-firing (missing a real thrash) — and this codebase already treats over-firing as the deliberately safe direction elsewhere. Real Codex events do carry usable timestamps per the fixture builders, so closing this gap is cheap if wanted, but it's not required for PASS.

6. **AC-1's still-open item** (distinct from AC-1b, which IS satisfied): a real, human-run live Codex session with hook debug logging on, to capture the literal `Stop`/`SubagentStop` hook stdin JSON verbatim. This cannot be done by any agent — it requires Nnamdi to actually run one. The shipped `_detect_runtime()` does NOT depend on this (it was redesigned in round 2 of plan-check to depend on transcript content-shape instead, which IS independently verified) — so this is a narrower, separately-valuable validation of the raw stdin schema, not a blocker on anything currently built.

## Rules for whoever continues this

- Never run `git status`/`git diff`/`git add`/`git stash`/`git commit` without an explicit pathspec scoped to the file list above, until Nnamdi confirms the shared-directory concurrency situation is resolved — and even then, prefer working in the isolated worktree.
- Don't re-litigate the spec's frozen design (3 rounds of adversarial plan-check went into it). Bugs in the *tests* (like item 4 above) are fair game; the *design* is not, absent new evidence as rigorous as what overturned it in round 1.
- Treat any Coder/test-writer self-report on this build with real skepticism and re-verify independently — this build's own history (the stale Phase4AC claim) is the proof of why.
