#!/usr/bin/env bash
# recompute_verdict.sh -- slice-closure gate verdict RECOMPUTED from live
# GitHub at the head SHA (closure adapter P2.2 deliverable).
#
# Usage: recompute_verdict.sh <owner>/<repo> <ref> <required-context>
#   <ref>              git ref (branch) whose HEAD SHA is resolved via GitHub.
#   <required-context> exact check-run NAME that must be GREEN.
#
# Output (exactly one machine line):
#   GREEN <repo> <sha> <context>
#   RED   <repo> <sha> <context>: <reason>          (reason <= 200 chars)
# Exit 0 iff GREEN, nonzero iff RED.
#
# Verdict rule (revised, spec round 2): computed ONLY from check runs at the
# head SHA: at least one run whose `name` equals the required context AND
# EVERY such run must have `conclusion: success` (all-runs-must-pass). The
# legacy commit status `slice-gate-verdict` is DATA-ONLY -- last-write-wins,
# forgeable, NEVER sufficient; at most printed in a RED reason as info.
#
# Hardening:
#   * gh is resolved via PATH only (`command -v gh`); fail-closed with a
#     clear error when missing.
#   * No `timeout(1)` binary needed (macOS): every gh api call is capped
#     in-process with a `read -t` watchdog.
#   * The ref argv travels to `gh api` as ONE quoted argument -- never
#     shell-evaluated, so metacharacters stay literal (a hostile ref cannot
#     inject anything; it can only 404, which is RED).
#   * JSON keys are decoded with /usr/bin/perl core JSON::PP -- position-
#     independent and robust against nesting (app, output objects) and
#     whitespace; the fake `gh` shim stays reachable unchanged.
#   * Never reads worker-written claims; never writes files.
set -u

GH_TIMEOUT=30        # cap for each gh api call       (recompute budget)
STATUS_TIMEOUT=15    # cap for the informational sidecar status fetch

S_REPO="${1:-}"
S_REF="${2:-}"
S_CTX="${3:-}"
SHA="unknown"

if [ -z "$S_REPO" ] || [ -z "$S_REF" ] || [ -z "$S_CTX" ]; then
    printf 'usage: %s <owner>/<repo> <ref> <required-context>\n' "${0##*/}" >&2
    exit 2
fi

GH_BIN="$(command -v gh 2>/dev/null || true)"
if [ -z "$GH_BIN" ]; then
    printf 'RED  %s %s %s: gh CLI not found on PATH (gh api required)\n' \
        "$S_REPO" "$SHA" "$S_CTX"
    exit 1
fi

# gh_get <timeout> <var> <args...>
# Runs `gh <args...>` capped by an in-shell deadline; stores the first stdout
# line into <var> (gh api emits compact single-line JSON). Returns 0 on
# success; nonzero on failure/empty/timeout (fail-closed).
gh_get() {
    local _mt="$1" _var="$2"; shift 2
    local _line
    if IFS= read -r -t "$_mt" _line < <("$GH_BIN" "$@" 2>/dev/null; printf '\n'); then
        printf -v "$_var" '%s' "$_line"
        return 0
    fi
    return 1
}

# JSON keys are decoded with /usr/bin/perl core JSON::PP -- position-
# independent and robust against nesting (app, output objects) and spacing.
emit_green() {
    printf 'GREEN %s %s %s\n' "$S_REPO" "$SHA" "$S_CTX"
    exit 0
}
emit_red() {
    local reason="$1"
    printf 'RED  %s %s %s: %.200s\n' "$S_REPO" "$SHA" "$S_CTX" "$reason"
    exit 1
}

# sidecar_hint: informational only; NEVER used to allow (forgable statuses).
sidecar_hint() {
    local st_line sv
    if gh_get "$STATUS_TIMEOUT" st_line "api" "repos/$S_REPO/commits/$SHA/status"; then
        sv="$(printf '%s' "$st_line" | /usr/bin/perl -MJSON::PP -e '
            my $j = eval { JSON::PP->new->decode(do { local $/; <STDIN> }) };
            exit 0 if !$j;
            for my $s (@{ $j->{statuses} || [] }) {
                if (defined $s->{context} && defined $s->{state} &&
                    $s->{context} eq "slice-gate-verdict") {
                    print $s->{state} eq "success" ? "success" : ($s->{state} || "unknown"); exit 0
                }
            }
            print "absent";' 2>/dev/null)"
        if [ "$sv" = "success" ]; then
            printf '%s' ' (sidecar slice-gate-verdict=success is data-only, never sufficient)'
        fi
    fi
    return 0
}

# ---- 1. Resolve the real head SHA for the ref (fast-fail, fail closed) -----
resolved=""
if ! gh_get "$GH_TIMEOUT" resolved \
        "api" "repos/$S_REPO/commits/$S_REF"; then
    emit_red "could not resolve ref '$S_REF' (gh api commit lookup failed)"
fi
SHA="$(printf '%s' "$resolved" | /usr/bin/perl -MJSON::PP -e '
    my $j = eval { JSON::PP->new->decode(do { local $/; <STDIN> }) };
    print(defined $j && ref($j) eq "HASH" && $j->{sha} =~ /^[0-9a-f]{40}$/ ? $j->{sha} : "ERR");')"
if [ "$SHA" = "ERR" ]; then
    SHA="unknown"
    emit_red "could not resolve head sha for ref '$S_REF' (fail-closed)"
fi

# ---- 2. Query check runs at the EXACT head SHA -----------------------------
cr_line=""
if ! gh_get "$GH_TIMEOUT" cr_line \
        "api" "repos/$S_REPO/commits/$SHA/check-runs?per_page=100"; then
    emit_red "gh api check-runs query failed for $SHA"
fi

# ---- 3. Verdict: >=1 run named <context>, ALL such runs success ------------
cr_row="$(printf '%s' "$cr_line" | /usr/bin/perl -MJSON::PP -e '
    my $j = eval { JSON::PP->new->decode(do { local $/; <STDIN> }) };
    print "ERR\n" unless $j;
    exit 0 unless $j;
    for my $r (@{ $j->{check_runs} || [] }) {
        my $n = defined $r->{name} ? $r->{name} : "";
        my $c = defined $r->{conclusion} ? $r->{conclusion} : "";
        print "$n\t$c\n";
    }')"
tally_total=0
tally_ok=0
while IFS=$'\t' read -r rname rconc; do
    if [ -n "$rname" ] && [ "$rname" = "$S_CTX" ]; then
        tally_total=$((tally_total + 1))
        if [ "$rconc" = "success" ]; then
            tally_ok=$((tally_ok + 1))
        fi
    fi
done <<< "$cr_row"

if [ "$tally_total" -eq 0 ]; then
    emit_red "no check run named \"$S_CTX\" at $SHA (fail-closed)$(sidecar_hint)"
fi
if [ "$tally_ok" -ne "$tally_total" ]; then
    emit_red "check run \"$S_CTX\" not all green at $SHA ($tally_ok/$tally_total success; all-runs-must-pass)$(sidecar_hint)"
fi

emit_green