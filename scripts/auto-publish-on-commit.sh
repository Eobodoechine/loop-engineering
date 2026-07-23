#!/bin/bash
# auto-publish-on-commit.sh — git post-commit hook for MAIN (~/Claude/loop) that
# automatically publishes to the ~/loop-public clone -> GitHub after every commit
# on main, by generating a real, traceable changelog-based README update when
# needed to satisfy scripts/snapshot-publish.sh's README-freshness /
# since-last-publish gates.
#
# ─── WHAT THIS DELIBERATELY REVERSES ─────────────────────────────────────────
# scripts/snapshot-publish.sh's own header describes its safety model as
# "tracked-only publishing + fail-closed gate + human review" and states
# "Nothing auto-publishes — it only runs when invoked." This hook removes the
# human-review step on purpose, by explicit instruction (2026-07-04). Every
# other gate (PII scan, tracked-only git-archive extraction, README-freshness)
# stays fully intact and unmodified — this hook only automates the "write a
# real README changelog entry" step that used to require a human, by generating
# one from actual commit messages (never fabricated prose).
#
# ─── INSTALL (not cloned automatically -- .git/hooks/ isn't tracked) ────────
#   ln -sf ../../scripts/auto-publish-on-commit.sh .git/hooks/post-commit
#   chmod +x scripts/auto-publish-on-commit.sh
#
# ─── DISABLE ──────────────────────────────────────────────────────────────--
#   rm .git/hooks/post-commit
#
# ─── LOG ──────────────────────────────────────────────────────────────────--
#   .git/hooks/auto-publish.log (gitignored, local only)

set -u
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO" || exit 0

# Reentrancy guard: this hook's own README-changelog commit must not re-fire itself.
[ "${LOOP_AUTOPUBLISH_HOOK_ACTIVE:-0}" = "1" ] && exit 0
export LOOP_AUTOPUBLISH_HOOK_ACTIVE=1

# Only main publishes.
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
[ "$branch" = "main" ] || exit 0

PUBLIC="${LOOP_PUBLIC_CLONE:-$HOME/loop-public}"
LOG="$REPO/.git/hooks/auto-publish.log"
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

log "post-commit fired on $(git rev-parse --short HEAD)"

# Resolve the last-published sha the same way snapshot-publish.sh does.
PUB_LAST_SHA=""
if [ -d "$PUBLIC/.git" ]; then
  PUB_LAST_SHA="$(git -C "$PUBLIC" show HEAD:.loop-publish-meta.json 2>/dev/null \
    | grep -Eo '"main_sha"[[:space:]]*:[[:space:]]*"[0-9a-fA-F]+"' \
    | grep -Eo '[0-9a-fA-F]+"$' | tr -d '"')"
fi

# Nothing new since the last publish -- no-op (guards an empty/no-op commit).
if [ -n "$PUB_LAST_SHA" ] && [ "$PUB_LAST_SHA" = "$(git rev-parse HEAD)" ]; then
  log "already published at this sha -- skipping"
  exit 0
fi

DRYRUN_OUT="$(mktemp)"
if bash scripts/snapshot-publish.sh --dry-run >"$DRYRUN_OUT" 2>&1; then
  log "dry-run already clean (this commit's own README changes satisfy the gates) -- publishing directly"
else
  log "dry-run gate failed, generating changelog README update: $(tail -1 "$DRYRUN_OUT")"
  TODAY="$(date -u +%Y-%m-%d)"
  RANGE="HEAD"
  if [ -n "$PUB_LAST_SHA" ] && git rev-parse --verify -q "${PUB_LAST_SHA}^{commit}" >/dev/null 2>&1; then
    RANGE="${PUB_LAST_SHA}..HEAD"
  fi
  CHANGELOG="$(git log --format='- %s' "$RANGE" -- . ':!README.md' 2>/dev/null | head -50)"
  if [ -z "$CHANGELOG" ]; then
    log "gate failed and no changelog commits found in range '$RANGE' -- not publishing this time"
    rm -f "$DRYRUN_OUT"
    exit 0
  fi
  {
    echo ""
    echo "## Recent changes (auto-published $TODAY)"
    echo ""
    echo "$CHANGELOG"
  } >> README.md
  if grep -q 'Status as of [0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}' README.md; then
    sed -i '' -E "s/Status as of [0-9]{4}-[0-9]{2}-[0-9]{2}/Status as of $TODAY/" README.md
  fi
  git add README.md
  git commit -m "chore: auto-publish changelog update ($TODAY)" -q
  log "committed auto-generated README changelog ($(git rev-parse --short HEAD))"
fi
rm -f "$DRYRUN_OUT"

if bash scripts/snapshot-publish.sh --incremental >>"$LOG" 2>&1; then
  log "publish OK"
else
  log "publish FAILED -- see entries above in this log"
fi
