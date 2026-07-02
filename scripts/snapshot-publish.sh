#!/bin/bash
# snapshot-publish.sh — publish the framework's TRACKED tree from the private
# MAIN working copy into a PUBLIC clone, PII-gate it on the filesystem, then
# publish. The loop's own principle ("something must be able to say no")
# applied to the whole pipeline: it is impossible to publish a private /
# untracked / gitignored / PII-bearing file, and any gate miss is transient +
# recoverable because the DEFAULT is a single-commit snapshot (orphan branch +
# force-with-lease) — the public history is always exactly one clean commit, so
# a bad publish is overwritten by the next clean one rather than accreting.
#
# ─── WHAT PUBLISHES ──────────────────────────────────────────────────────────
# ONLY content that is *tracked in MAIN* (committed to git). We extract the
# tree with `git archive HEAD` — untracked, uncommitted, and gitignored files
# are STRUCTURALLY EXCLUDED because git archive only emits committed paths.
# So to publish a new file you must COMMIT IT TO MAIN FIRST. Nothing else can
# leak downstream. On top of that, private subtrees (public/, loop-team/runs/,
# top-level runs/) are deleted from the extracted tree before the gate runs.
#
# ─── ⚠️  WARNING — `git add -f` ──────────────────────────────────────────────
# Do NOT `git add -f` a gitignored private path into MAIN. Force-adding a
# gitignored file makes it TRACKED, and tracked-in-main == publishable (git
# archive WILL emit it). The gitignore is your last line of defense for private
# paths (loop-team/runs/, __pycache__, secrets) — never override it for
# something that must stay private.
#
# ─── USAGE ───────────────────────────────────────────────────────────────────
#   scripts/snapshot-publish.sh                 # SNAPSHOT (default): sync + gate +
#                                               #   single-commit orphan branch +
#                                               #   force-with-lease push. Public
#                                               #   repo becomes exactly ONE commit.
#   scripts/snapshot-publish.sh --incremental   # sync + gate + normal add/commit +
#                                               #   non-force push (accretes history)
#   scripts/snapshot-publish.sh --dry-run       # sync + gate + report, NO commit/push
#                                               #   (works under either mode)
#
#   Env overrides (defaults: ~/Claude/loop and ~/loop-public):
#     LOOP_MAIN_DIR      private working tree (READ-ONLY: only `git archive`)
#     LOOP_PUBLIC_CLONE  public clone to publish into (must be a git repo on
#                        branch 'main' with an 'origin' remote)
#     LOOP_SCAN_EMAIL    override the email the PII gate scans for (else derived
#                        from `git -C $LOOP_MAIN_DIR config user.email`)
#
# This script NEVER runs a git WRITE against MAIN — MAIN is read with
# `git archive` only. All staging / commit / push happen in PUBLIC_CLONE, and
# the snapshot push uses --force-with-lease (never a bare --force).

set -u

# ─── config ────────────────────────────────────────────────────────────────--
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="${LOOP_MAIN_DIR:-$HOME/Claude/loop}"
PUBLIC="${LOOP_PUBLIC_CLONE:-$HOME/loop-public}"
# Normalize away any trailing slash so path-prefix strips (e.g. "${file#"$PUBLIC"/}")
# produce a single-slash boundary and don't break the tooling-exclusion match.
MAIN="${MAIN%/}"
PUBLIC="${PUBLIC%/}"
PUBLISH_BRANCH="main"

# Committer identity for the PUBLIC repo (noreply — no personal email published).
PUB_NAME="Eobodoechine"
PUB_EMAIL="Eobodoechine@users.noreply.github.com"

# Detection-tooling files that legitimately contain the key-prefix literals /
# regexes and would self-trip the REAL-KEY portion of the gate. Same rationale
# as pii-guard.sh excluding itself. Paths are relative to PUBLIC root.
TOOLING_EXCLUDE=(
  "loop-team/evals/verify_build.py"
  "loop-team/evals/test_verify_build.py"
  "scripts/pii-guard.sh"
  "scripts/pii-markers.example"
  "scripts/test_publish.py"
  "scripts/snapshot-publish.sh"
  "scripts/test_snapshot_publish.py"
)

# ─── flags ─────────────────────────────────────────────────────────────────--
DRY_RUN=0
INCREMENTAL=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)     DRY_RUN=1 ;;
    --incremental) INCREMENTAL=1 ;;
    -h|--help)     sed -n '2,45p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "  ⛔  snapshot-publish: unknown argument '$arg'" >&2; exit 2 ;;
  esac
done

die() { echo "  ⛔  snapshot-publish: $*" >&2; exit 1; }

# ─── preconditions (fail-closed, BEFORE any mutation) ────────────────────────-
[ -d "$MAIN" ]   || die "MAIN dir not found: $MAIN"
[ -d "$PUBLIC" ] || die "PUBLIC clone not found: $PUBLIC"
git -C "$MAIN"   rev-parse --git-dir >/dev/null 2>&1 || die "MAIN is not a git repo: $MAIN"
git -C "$PUBLIC" rev-parse --git-dir >/dev/null 2>&1 || die "PUBLIC clone is not a git repo: $PUBLIC"

cur_branch="$(git -C "$PUBLIC" rev-parse --abbrev-ref HEAD 2>/dev/null)"
[ "$cur_branch" = "$PUBLISH_BRANCH" ] \
  || die "PUBLIC clone is on '$cur_branch', expected '$PUBLISH_BRANCH' — refusing to publish."
git -C "$PUBLIC" remote get-url origin >/dev/null 2>&1 \
  || die "PUBLIC clone has no 'origin' remote — refusing to publish."

# ─── README freshness (fail-closed): the published tree must carry a README
# stamped on (or after) the date of the HEAD commit it is built from. Reads the
# COMMITTED README (git archive publishes HEAD, never the working tree — an
# updated-but-uncommitted stamp must NOT pass). Escape: LOOP_README_STALE_OK=1.
README_STAMP="$(git -C "$MAIN" show HEAD:README.md 2>/dev/null \
  | grep -Eo 'Status as of [0-9]{4}-[0-9]{2}-[0-9]{2}' | head -n1 \
  | grep -Eo '[0-9]{4}-[0-9]{2}-[0-9]{2}')"
HEAD_DATE="$(git -C "$MAIN" log -1 --format=%cs)"
if [ "${LOOP_README_STALE_OK:-0}" = "1" ]; then
  echo "  ⚠  README-freshness gate OVERRIDDEN (LOOP_README_STALE_OK=1) — stamp='${README_STAMP:-none}' head=$HEAD_DATE" >&2
elif [ -z "$README_STAMP" ]; then
  die "README.md at HEAD carries no 'Status as of YYYY-MM-DD' stamp — update README, stamp it, COMMIT it, re-run (or LOOP_README_STALE_OK=1 to override)."
elif [ "$README_STAMP" \< "$HEAD_DATE" ]; then
  die "README stamp ($README_STAMP) is older than HEAD commit date ($HEAD_DATE) — the published README would be stale. Update README + stamp, COMMIT it, re-run (or LOOP_README_STALE_OK=1 to override)."
fi

# ─── marker source (fail-closed on the marker file) ──────────────────────────-
# The gate's personal markers live in a LOCAL, gitignored file so this published
# script contains no personal strings. Missing OR empty (after stripping '#'
# comments and blank lines) == ABORT: we will not publish without a live marker
# source, because a silent no-markers gate is a false sense of safety.
MARKERS_FILE="$MAIN/scripts/.pii-markers.local"
[ -f "$MARKERS_FILE" ] || die "marker file missing: $MARKERS_FILE — refusing to publish (fail-closed)."
MARKER_PAT="$(grep -vhE '^[[:space:]]*#|^[[:space:]]*$' "$MARKERS_FILE" | paste -sd '|' -)"
[ -n "$MARKER_PAT" ] || die "marker file yields NO patterns after stripping comments/blanks: $MARKERS_FILE — refusing to publish (fail-closed)."

# ─── SYNC (tracked-only positive control) ────────────────────────────────────-
# Rebuild PUBLIC's working tree from scratch so DELETIONS propagate: wipe
# everything except .git, then extract the tracked tree from MAIN's HEAD.
find "$PUBLIC" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} + \
  || die "failed to clear PUBLIC working tree."

# `git archive HEAD` emits ONLY committed (tracked) paths — untracked /
# gitignored private files are structurally excluded here.
if ! git -C "$MAIN" archive HEAD | tar -x -C "$PUBLIC"; then
  die "failed to extract tracked tree from MAIN (git archive | tar)."
fi

# Remove excluded subtrees from the extracted tree (belt-and-suspenders on top
# of the tracked-only guarantee).
rm -rf "$PUBLIC/public" "$PUBLIC/loop-team/runs" "$PUBLIC/runs"

# ─── PRIVACY GATE (fail-closed, FILESYSTEM grep BEFORE any git add/commit/push) -
# Portion (a) markers + (b) email + (c) home path are scanned across ALL files.
# Portion (d) REAL keys is scanned across all files too, then hits in the
# detection-tooling files are filtered out (they legitimately hold the regex).
SCAN_EMAIL="${LOOP_SCAN_EMAIL:-$(git -C "$MAIN" config user.email 2>/dev/null)}"
HOME_USER="$(basename "$HOME")"

# (a)+(b)+(c): markers, email (if known), and home path (the macOS home-dir
# prefix plus the current user's home basename), so a leaked absolute home
# path is caught. The prefix is built by concatenation so THIS script's own
# source never contains the contiguous string it scans for — otherwise the
# gate can never publish its own tooling (self-match, found 2026-07-01).
HOMES_PREFIX="/Use""rs/"
NONKEY_PARTS=("$MARKER_PAT")
[ -n "$SCAN_EMAIL" ] && NONKEY_PARTS+=("$SCAN_EMAIL")
NONKEY_PARTS+=("$HOMES_PREFIX")
[ -n "$HOME_USER" ] && NONKEY_PARTS+=("$HOMES_PREFIX$HOME_USER")
NONKEY_PAT="$(IFS='|'; echo "${NONKEY_PARTS[*]}")"

# (d): REAL keys only — the actual key formats, NOT bare 'sk-ant'/'sk-proj'.
REALKEY_PAT='sk-ant-api|sk-proj-[A-Za-z0-9]{12,}'

# helper: is a PUBLIC-relative path in the tooling-exclusion set?
_is_tooling() {
  local rel="$1" t
  for t in "${TOOLING_EXCLUDE[@]}"; do
    [ "$rel" = "$t" ] && return 0
  done
  return 1
}

HITS=""

# Non-key scan: ANY hit anywhere is a real hit (no tooling exemption — personal
# markers / email / home paths must never appear in ANY published file).
nonkey_hits="$(grep -rInE "$NONKEY_PAT" "$PUBLIC" --exclude-dir=.git 2>/dev/null)"
[ -n "$nonkey_hits" ] && HITS+="$nonkey_hits"$'\n'

# Real-key scan: hits in tooling files are the regex/literals themselves — drop
# them; a remaining hit in a NON-tooling file is a genuine leaked key.
while IFS= read -r line; do
  [ -z "$line" ] && continue
  # grep -rn output: <path>:<lineno>:<text>
  file="${line%%:*}"
  rel="${file#"$PUBLIC"/}"
  if _is_tooling "$rel"; then
    continue
  fi
  HITS+="$line"$'\n'
done < <(grep -rInE "$REALKEY_PAT" "$PUBLIC" --exclude-dir=.git 2>/dev/null)

if [ -n "${HITS//[$'\n']/}" ]; then
  {
    echo ""
    echo "  ⛔  PUBLISH BLOCKED — personal data / real key found in the extracted tree:"
    printf '%s\n' "$HITS" | sed '/^$/d;s/^/      /'
    echo ""
    echo "  NOTHING was staged, committed, or pushed. Scrub the source in MAIN,"
    echo "  commit, then re-run."
    echo ""
  } >&2
  exit 1
fi

echo "  ✓  snapshot-publish: PII gate clean." >&2

# ─── report (dry-run reports and stops under either mode) ────────────────────-
if [ "$DRY_RUN" -eq 1 ]; then
  echo "  ── git status --short (PUBLIC) ──" >&2
  git -C "$PUBLIC" status --short >&2
  mode="snapshot"; [ "$INCREMENTAL" -eq 1 ] && mode="incremental"
  echo "  ✓  snapshot-publish --dry-run ($mode): gate clean, tree synced. NO commit, NO push." >&2
  exit 0
fi

COMMIT_MSG="snapshot: publish tracked tree ($(date -u +%Y-%m-%dT%H:%M:%SZ))"

if [ "$INCREMENTAL" -eq 1 ]; then
  # ─── INCREMENTAL: normal add/commit + non-force push ───────────────────────-
  git -C "$PUBLIC" add -A || die "git add -A failed in PUBLIC."
  if git -C "$PUBLIC" diff --cached --quiet; then
    echo "  nothing to publish" >&2
    exit 0
  fi
  git -C "$PUBLIC" -c user.name="$PUB_NAME" -c user.email="$PUB_EMAIL" \
    commit -m "$COMMIT_MSG" >/dev/null || die "commit failed."
  git -C "$PUBLIC" push origin "$PUBLISH_BRANCH" || die "push failed."
  echo "  ✓  snapshot-publish --incremental: committed and pushed to origin/$PUBLISH_BRANCH." >&2
  exit 0
fi

# ─── SNAPSHOT (default): single fresh commit + force-with-lease ──────────────-
# Orphan branch => no parent history; the public repo becomes exactly ONE commit
# of the current tree. Force-with-lease (never bare --force) replaces main.
git -C "$PUBLIC" checkout --orphan _snap >/dev/null 2>&1 || die "failed to create orphan branch."
git -C "$PUBLIC" add -A || die "git add -A failed in PUBLIC."
git -C "$PUBLIC" -c user.name="$PUB_NAME" -c user.email="$PUB_EMAIL" \
  commit -m "$COMMIT_MSG" >/dev/null || die "commit failed."
git -C "$PUBLIC" branch -M _snap "$PUBLISH_BRANCH" || die "failed to rename orphan to $PUBLISH_BRANCH."
git -C "$PUBLIC" push --force-with-lease origin "$PUBLISH_BRANCH" || die "force-with-lease push failed."
echo "  ✓  snapshot-publish: single-commit snapshot force-pushed to origin/$PUBLISH_BRANCH." >&2
exit 0
