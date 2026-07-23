#!/usr/bin/env bash
# codex-review.sh — minimal Codex-as-reviewer via artifact handoff.
#
# Why artifact handoff and not the MCP session API: the official Codex MCP
# server historically did not return the conversation/thread id needed for
# multi-turn, so session-based integration is fragile. For a *reviewer*
# (one-shot: here's a diff, give me a verdict) you don't need a session at
# all. This shells `codex exec` in read-only mode and captures the verdict
# to a file. No credit gate, no worker identity, no hooks.
#
# Requires: Codex CLI installed and authed (`codex --version` works).
# The reviewer's verdict is ADVISORY. A human or a Claude Verifier still
# owns the real PASS — this is a second opinion, not a gate.
#
# Usage:
#   ./codex-review.sh                 # reviews `git diff` (unstaged) in cwd
#   ./codex-review.sh --staged        # reviews staged changes
#   ./codex-review.sh <ref>           # reviews `git diff <ref>` (e.g. main)
#   ./codex-review.sh --file path.ts  # reviews a single file's full contents
set -euo pipefail

MODE="worktree"
TARGET=""
case "${1:-}" in
  --staged) MODE="staged" ;;
  --file)   MODE="file"; TARGET="${2:?--file needs a path}" ;;
  "")       MODE="worktree" ;;
  *)        MODE="ref"; TARGET="$1" ;;
esac

OUTDIR="${CODEX_REVIEW_OUT:-.codex-reviews}"
mkdir -p "$OUTDIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
REQ="$OUTDIR/review-$STAMP.request.md"
OUT="$OUTDIR/review-$STAMP.verdict.md"

# 1) Assemble the thing to review into a handoff file.
{
  echo "# Code review request"
  echo
  case "$MODE" in
    worktree) echo "## Diff (unstaged working tree)"; echo '```diff'; git diff;          echo '```' ;;
    staged)   echo "## Diff (staged)";               echo '```diff'; git diff --staged; echo '```' ;;
    ref)      echo "## Diff vs $TARGET";             echo '```diff'; git diff "$TARGET"; echo '```' ;;
    file)     echo "## Full file: $TARGET";          echo '```';     cat "$TARGET";      echo '```' ;;
  esac
} > "$REQ"

if [ ! -s "$REQ" ] || ! grep -q '[^[:space:]]' <(tail -n +4 "$REQ"); then
  echo "Nothing to review (empty diff). Stage changes or pass a ref." >&2
  exit 3
fi

# 2) The reviewer prompt. Forces a structured, decisive verdict.
read -r -d '' PROMPT <<'EOF' || true
You are an independent code reviewer giving a SECOND OPINION. You did not write
this code. Read the review request file provided and return ONLY this structure:

VERDICT: PASS | FAIL | PASS_WITH_CONCERNS
SUMMARY: one sentence.
FINDINGS: numbered list, most severe first. For each: file:line, what's wrong,
  and a concrete failure scenario (inputs -> wrong result). If none, write "none".
MISSED_TESTS: cases the change should test but doesn't. If none, "none".

Rules: be adversarial — try to find the bug, don't rubber-stamp. Default to
FAIL if you cannot convince yourself the change is correct. No praise, no
restating the diff. Do not suggest running commands; just judge what you see.
EOF

# 3) Hand off to Codex, read-only, non-interactive.
#    `codex exec` runs one turn and exits. --sandbox read-only guarantees it
#    cannot modify the repo. Flags are conservative; adjust to your CLI version
#    (`codex exec --help`).
echo "→ Codex reviewing ($MODE) ... verdict -> $OUT"
codex exec \
  --sandbox read-only \
  "$PROMPT

Review request file: $REQ
Read that file and produce the verdict." \
  | tee "$OUT"

echo
echo "Saved: $OUT"
# Surface a nonzero exit if Codex said FAIL, so CI/scripts can branch on it.
if grep -qiE '^VERDICT:\s*FAIL' "$OUT"; then exit 1; fi
