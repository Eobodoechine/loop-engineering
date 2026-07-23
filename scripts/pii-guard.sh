#!/bin/bash
# pii-guard.sh — block publishing personal data. The loop's own principle
# ("something must be able to say no") applied to git push.
#
# This is the CANONICAL, version-controlled copy. Git hooks live in .git/hooks/
# which is NOT cloned, so after cloning install it as your pre-push hook:
#
#     ln -sf ../../scripts/pii-guard.sh .git/hooks/pre-push
#
# (or `cp scripts/pii-guard.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push`)
#
# Run manually any time:  ./scripts/pii-guard.sh
# As a pre-push hook it scans every tracked file and exits non-zero (blocking
# the push) if any personal marker is found.

repo="$(git rev-parse --show-toplevel)" || exit 0
cd "$repo" || exit 0

# Generic markers that are SAFE TO PUBLISH (API-key prefixes only). Personal
# markers — names, home paths, private project slugs — live in a LOCAL,
# gitignored file so THIS published script contains no personal strings:
#     scripts/.pii-markers.local   (copy scripts/pii-markers.example to create it;
#                                    one regex alternative per line, '#' comments ok)
# High-signal markers ONLY — deliberately NOT bare words like "atlanta"/"rental"
# that legitimately appear in the scraping war-stories.
PATTERN='sk-ant|sk-proj'
markers_file="$repo/scripts/.pii-markers.local"
if [ -f "$markers_file" ]; then
  extra="$(grep -vhE '^[[:space:]]*#|^[[:space:]]*$' "$markers_file" | paste -sd '|' -)"
  [ -n "$extra" ] && PATTERN="$PATTERN|$extra"
fi

# Scan all tracked files EXCEPT the key-detection TOOLING itself, which legitimately
# contains the key-prefix literals and would otherwise self-trip (same reason the
# guard excludes itself): this guard + verify_build.py's PII lint + its tests. The
# local markers file is gitignored, so git grep never scans it.
hits="$(git grep -IniE "$PATTERN" -- \
  ':!scripts/pii-guard.sh' \
  ':!scripts/.pii-markers.local' \
  ':!scripts/pii-markers.example' \
  ':!loop-team/evals/verify_build.py' \
  ':!loop-team/evals/test_verify_build.py' 2>/dev/null)"

if [ -n "$hits" ]; then
  {
    echo ""
    echo "  ⛔  PUSH BLOCKED — personal data found in tracked files:"
    echo "$hits" | sed 's/^/      /'
    echo ""
    echo "  Scrub these before publishing, then push again."
    echo "  (guard: scripts/pii-guard.sh — edit PATTERN to tune)"
    echo ""
  } >&2
  exit 1
fi

echo "  ✓  PII guard: clean — publishing." >&2
exit 0
