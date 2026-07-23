#!/bin/bash
# DEPRECATED (2026-07-01): this script targeted the removed public/ submodule
# mirror. Publishing now goes through scripts/snapshot-publish.sh (git-archive
# snapshot of the root repo -> ~/loop-public -> github). Kept for reference.
#
# publish.sh — safely mirror the framework's TRACKED loop-team/ content from the
# private MAIN working tree into the PUBLIC repo, then PII-guard and push it.
#
# The loop's own principle ("something must be able to say no") applied to the
# whole publish pipeline: it is impossible to publish a private / untracked /
# gitignored / PII-bearing file, and impossible to push a tree that isn't on the
# expected branch — the script fails closed at every gate.
#
# ─── WHAT PUBLISHES ──────────────────────────────────────────────────────────
# ONLY content that is *tracked in MAIN* (committed to git) under loop-team/.
# An untracked, uncommitted, or gitignored file is structurally excluded because
# `git ls-files` never emits it. So to publish a new file you must commit it to
# main first (COMMIT IT TO MAIN FIRST). Nothing else can leak downstream.
#
# ─── ⚠️  WARNING ─────────────────────────────────────────────────────────────
# Do NOT `git add -f` a gitignored private path into MAIN. Force-adding a
# gitignored file makes it TRACKED, and tracked-in-main == publishable. The
# gitignore is your last line of defense for private paths (loop-team/runs/,
# __pycache__, secrets) — never override it for something that must stay private.
#
# ─── USAGE ───────────────────────────────────────────────────────────────────
#   scripts/publish.sh ["commit message"]      # sync + guard + commit + push
#   scripts/publish.sh --dry-run ["message"]   # sync + guard + report, NO commit/push
#
#   Env overrides (default to ~/Claude/loop and ~/Claude/loop/public):
#     LOOP_MAIN_DIR    private working tree (read-only: only `git ls-files`)
#     LOOP_PUBLIC_DIR  public repo to publish into
#
#   Requirements / gates:
#     - PUBLIC must be on branch 'phase1-eval-harness' (else abort).
#     - scripts/pii-guard.sh must report clean against the STAGED public content
#       (else abort: unstage, no commit, no push).
#
# This script NEVER runs a git WRITE against MAIN — MAIN is read with
# `git ls-files` only. All staging / commit / push happen in PUBLIC.

echo "publish.sh is RETIRED (2026-07-01): it mirrored into the removed public/ submodule" >&2
echo "and has NO README-freshness gate. Use scripts/snapshot-publish.sh instead." >&2
exit 1

set -u

# ─── config ──────────────────────────────────────────────────────────────────
PUBLISH_BRANCH="phase1-eval-harness"
SUBTREE="loop-team"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAIN="${LOOP_MAIN_DIR:-$HOME/Claude/loop}"
PUBLIC="${LOOP_PUBLIC_DIR:-$HOME/Claude/loop/public}"

# ─── flags ─────────────────────────────────────────────────────────────────--
DRY_RUN=0
COMMIT_MSG=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) COMMIT_MSG="$arg" ;;
  esac
done
[ -n "$COMMIT_MSG" ] || COMMIT_MSG="publish: sync ${SUBTREE}/ from main ($(date -u +%Y-%m-%dT%H:%M:%SZ))"

die() { echo "  ⛔  publish: $*" >&2; exit 1; }

# ─── preconditions ─────────────────────────────────────────────────────────--
[ -d "$MAIN" ]   || die "MAIN dir not found: $MAIN"
[ -d "$PUBLIC" ] || die "PUBLIC dir not found: $PUBLIC"
git -C "$MAIN"   rev-parse --git-dir >/dev/null 2>&1 || die "MAIN is not a git repo: $MAIN"
git -C "$PUBLIC" rev-parse --git-dir >/dev/null 2>&1 || die "PUBLIC is not a git repo: $PUBLIC"

# ─── branch guard (fail-closed, BEFORE any mutation) ─────────────────────────-
cur_branch="$(git -C "$PUBLIC" rev-parse --abbrev-ref HEAD 2>/dev/null)"
if [ "$cur_branch" != "$PUBLISH_BRANCH" ]; then
  die "PUBLIC is on '$cur_branch', expected '$PUBLISH_BRANCH' — refusing to publish."
fi

# clear a stale index lock if present (safe — no concurrent git here)
rm -f "$PUBLIC/.git/index.lock" 2>/dev/null || true

# ─── build publish_set (TRACKED-ONLY positive control) ───────────────────────-
# `git ls-files` emits ONLY tracked paths — never untracked, never gitignored.
# This is the structural guarantee that a stray private file cannot leak.
declare -A PUBLISH_SET=()
copied=0
while IFS= read -r -d '' f; do
  PUBLISH_SET["$f"]=1
  mkdir -p "$PUBLIC/$(dirname "$f")"
  cp "$MAIN/$f" "$PUBLIC/$f"
  copied=$((copied + 1))
done < <(git -C "$MAIN" ls-files -z -- "$SUBTREE")

[ "$copied" -gt 0 ] || die "no tracked files under '$SUBTREE/' in MAIN — nothing to publish."

# ─── PRUNE (filesystem-based) ────────────────────────────────────────────────-
# Walk the PUBLIC subtree on the FILESYSTEM and delete any file NOT in the
# publish_set. This removes stale / now-removed / previously-leaked files —
# even ones git would ignore — so PUBLIC is an EXACT mirror of publish_set.
pruned=0
if [ -d "$PUBLIC/$SUBTREE" ]; then
  while IFS= read -r -d '' abs; do
    rel="${abs#"$PUBLIC"/}"
    if [ -z "${PUBLISH_SET["$rel"]:-}" ]; then
      rm -f "$abs"
      # fail closed: a stale/leaked file that we could NOT delete must not slip
      # through to publish. (git index lock excluded — that's handled above.)
      [ -e "$abs" ] && die "could not prune stale file '$rel' from PUBLIC — refusing to publish."
      pruned=$((pruned + 1))
    fi
  done < <(find "$PUBLIC/$SUBTREE" -type f -print0)
fi

# ─── stage so pii-guard's `git grep` sees the NEW content ────────────────────-
git -C "$PUBLIC" add -A || die "git add -A failed in PUBLIC"

# ─── PII GUARD (fail-closed) ─────────────────────────────────────────────────-
# Run from within PUBLIC so the guard's `git rev-parse --show-toplevel` resolves
# to PUBLIC and it scans the freshly-staged published content.
if ! ( cd "$PUBLIC" && "$SCRIPT_DIR/pii-guard.sh" ); then
  git -C "$PUBLIC" reset >/dev/null 2>&1   # unstage everything
  die "PII guard FAILED — nothing staged, NO commit, NO push. Scrub and retry."
fi

# ─── report (what will publish) ──────────────────────────────────────────────-
echo "  publish: synced $copied tracked file(s), pruned $pruned stale file(s)." >&2
echo "  ── git status --short ──" >&2
git -C "$PUBLIC" status --short >&2
echo "  ── git diff --cached --stat ──" >&2
git -C "$PUBLIC" diff --cached --stat >&2

# ─── commit + push (only when clean AND not --dry-run) ───────────────────────-
if [ "$DRY_RUN" -eq 1 ]; then
  echo "  ✓  publish --dry-run: guard clean, staged for review. NO commit, NO push." >&2
  exit 0
fi

if git -C "$PUBLIC" diff --cached --quiet; then
  echo "  ✓  publish: nothing changed — no commit needed." >&2
  exit 0
fi

git -C "$PUBLIC" commit -m "$COMMIT_MSG" >/dev/null || die "commit failed"
git -C "$PUBLIC" push origin "$PUBLISH_BRANCH" || die "push failed"
echo "  ✓  publish: committed and pushed to origin/$PUBLISH_BRANCH." >&2
exit 0
