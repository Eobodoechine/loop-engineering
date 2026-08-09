#!/usr/bin/env bash
# test_recompute_verdict.sh -- deterministic tests for recompute_verdict.sh.
#
# Usage:  bash test_recompute_verdict.sh
#
# Runs the real, not-yet-written ../recompute_verdict.sh (relative to this
# file) against a FAKE `gh` shim (fakes/gh) that shadows the real gh
# (/opt/homebrew/bin/gh) purely by PATH ordering -- the real binary is
# NEVER reached during fake cases.
#
# Contract under test (from spec.md, written for the implementer):
#   Usage: recompute_verdict.sh <owner>/<repo> <ref> <required-context>
#   Prints exactly one machine line:
#       GREEN <repo> <sha> <context>
#       RED   <repo> <sha> <context>: <reason>     (reason <= 200 chars)
#   exit 0 iff GREEN, nonzero iff RED.
#   Must call bare `gh` (resolved via PATH), wrapped in `timeout 30`
#   internally (recompute timeout: 30s). gh missing / gh api error / parse
#   failure -> RED + nonzero (fail-closed). Writes nothing except --json.

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$DIR/recompute_verdict.sh"
FAKE_BIN="$DIR/fakes"

PASS=0
FAIL=0
ARTIFACT_OK=1

note() { printf '%s\n' "$*"; }
fail() { note "  $*"; }

# run_impl <fake-case> <ref> [extra-env]
# Runs in a FRESH empty cwd; sets OUT ERR RC_V ELAPSED RUN_WORK.
run_impl() {
    local fake_case="$1" ref="${2:-ref-x}" extra="${3:-}"
    local work start
    work="$(mktemp -d)"
    start=$(date +%s)
    # shellcheck disable=SC2086
    ( cd "$work" && env -i $extra PATH="$FAKE_BIN:/usr/bin:/bin" FAKE_GH_CASE="$fake_case" \
        FAKE_GH_LOG="$work/fake-gh.log" \
        bash "$SCRIPT" "NEO-Venturez/wf-fix-test" "$ref" \
            "slice-closure-gate / slice-closure-gate" \
        > "$work/out" 2> "$work/err"; printf '%s' "$?" > "$work/rc" )
    RC_V="$(cat "$work/rc")"
    OUT="$(cat "$work/out")"
    ERR="$(cat "$work/err")"
    ELAPSED=$(( $(date +%s) - start ))
    RUN_WORK="$work"
}

verify_red()   { [ "$RC_V" -ne 0 ] && printf '%s' "$OUT" | grep -q '^RED '; }
verify_green() { [ "$RC_V" -eq 0 ] && printf '%s' "$OUT" | grep -q '^GREEN '; }

test_green() {
    # [BEHAVIORAL] exactly one success run with the required name
    #              -> exit 0 and line starts with GREEN.
    run_impl green-exact
    verify_green || { fail "green-exact: want exit 0 + 'GREEN ' line; got rc=$RC_V out=[$OUT] err=[$ERR]"; return 1; }
    return 0
}

test_mixed() {
    # [BEHAVIORAL] two runs SAME name, one success + one failed
    #              -> RED (all-runs-must-pass).
    run_impl mixed-same-context
    verify_red || { fail "mixed-same-context: expected RED; got rc=$RC_V out=[$OUT]"; return 1; }
    return 0
}

test_missing() {
    # [BEHAVIORAL] required context missing entirely -> RED (fail-closed).
    run_impl missing-context
    verify_red || { fail "missing-context: expected RED; got rc=$RC_V out=[$OUT]"; return 1; }
    return 0
}

test_pending() {
    # [BEHAVIORAL] required run status=pending (in_progress) -> RED.
    run_impl pending
    verify_red || { fail "pending: expected RED; got rc=$RC_V out=[$OUT]"; return 1; }
    return 0
}

test_sidecar() {
    # [BEHAVIORAL] slice-gate-verdict commit-status success but NO green
    #              composite check-run -> RED (sidecar data-only, never
    #              sufficient).
    run_impl sidecar-only
    verify_red || { fail "sidecar-only: expected RED; got rc=$RC_V out=[$OUT]"; return 1; }
    return 0
}

test_api_error() {
    # [BEHAVIORAL] `gh api` exits nonzero (network/auth) -> RED, fail-closed,
    #              and fail fast (whole run under 10s).
    run_impl api-error
    verify_red || { fail "api-error: expected RED; got rc=$RC_V out=[$OUT]"; return 1; }
    if [ "$ELAPSED" -ge 10 ]; then
        fail "api-error: took ${ELAPSED}s; must fail fast"; return 1
    fi
    return 0
}

test_injection() {
    # [BEHAVIORAL] ref arg containing `;` shell metacharacters must not be
    # interpolated: the touch target is never created, the script goes RED,
    # and the shim log proves the ref travelled to gh as a SINGLE argv.
    local pwn="/tmp/pwned.${$}.$$"
    rm -f "$pwn"
    local ref="does-not-exist-xyz;touch $pwn"
    local work rc
    work="$(mktemp -d)"
    ( cd "$work" && env -i PATH="$FAKE_BIN:/usr/bin:/bin" FAKE_GH_CASE=green-exact \
        FAKE_GH_LOG="$work/fake-gh.log" \
        bash "$SCRIPT" "NEO-Venturez/wf-fix-test" "$ref" \
            "slice-closure-gate / slice-closure-gate" > "$work/out" 2>&1
        printf '%s' "$?" > "$work/rc" )
    rc="$(cat "$work/rc")"
    if [ -e "$pwn" ]; then
        rm -f "$pwn"
        fail "injection: attacker-controlled file created -> ref WAS shell-interpolated"
        return 1
    fi
    if [ "$rc" -eq 0 ]; then
        rm -f "$pwn"
        fail "injection: expected RED (nonzero exit); got 0"
        return 1
    fi
    if ! grep -q -- "commits/does-not-exist-xyz;touch" "$work/fake-gh.log" 2>/dev/null; then
        rm -f "$pwn"
        fail "injection: ref never reached gh as one argv (log: $(cat "$work/fake-gh.log" 2>/dev/null))"
        return 1
    fi
    rm -f "$pwn"
    return 0
}

test_timeout_guard() {
    # [BEHAVIORAL] fake gh hangs 60s per call; recompute_verdict.sh must
    # apply an internal `timeout 30` on its gh invocation and return
    # well before the hang would finish: assert completion in < 55s and
    # exit RED (fail-closed).
    run_impl hang
    if [ "$ELAPSED" -ge 55 ]; then
        fail "timeout-guard: finished in ${ELAPSED}s; 30s timeout on gh not applied"
        return 1
    fi
    verify_red || { fail "timeout-guard: expected RED after timeout; got rc=$RC_V out=[$OUT]"; return 1; }
    return 0
}

test_gh_missing() {
    # [BEHAVIORAL] no `gh` discoverable via PATH -> RED, nonzero exit, and
    #              a clear error line referencing gh.
    local work rc out err
    work="$(mktemp -d)"
    ( cd "$work" && env -i HOME="$HOME" PATH="/usr/bin:/bin" \
        bash "$SCRIPT" "NEO-Venturez/wf-fix-test" "ab8b004b" \
            "slice-closure-gate / slice-closure-gate" > "$work/out" 2> "$work/err"
        printf '%s' "$?" > "$work/rc" )
    rc="$(cat "$work/rc")"; out="$(cat "$work/out")"; err="$(cat "$work/err")"
    [ "$rc" -ne 0 ] || { fail "gh-missing: exit 0 with gh absent -> not fail-closed"; return 1; }
    printf '%s\n%s' "$out" "$err" | grep -qi 'gh' || {
        fail "gh-missing: no clear error mentioning gh (out=[$out] stderr=[$err])"; return 1
    }
    return 0
}

test_ac4_no_writes() {
    # [BEHAVIORAL] AC4: the RED path must not write any file into its cwd
    # (no spool/across-temp per call). Run inside a fresh, dedicated cwd
    # and assert that cwd stays empty.
    local work rc
    work="$(mktemp -d)"
    mkdir "$work/cwd"
    ( cd "$work/cwd" && env -i PATH="$FAKE_BIN:/usr/bin:/bin" FAKE_GH_CASE=sidecar-only \
        bash "$SCRIPT" "NEO-Venturez/wf-fix-test" "ref-x" \
            "slice-closure-gate / slice-closure-gate" >/dev/null 2>&1
        printf '%s' "$?" > "$work/rc" )
    rc="$(cat "$work/rc")"
    if [ "$rc" -eq 0 ]; then
        fail "AC4: expected RED run, got exit 0"
        return 1
    fi
    local files
    files="$(find "$work/cwd" -mindepth 1 | wc -l | tr -d ' ')"
    if [ "$files" -ne 0 ]; then
        fail "AC4: RED path wrote files into cwd: $(find "$work/cwd" -mindepth 1 -exec basename {} \;)"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
if [ ! -f "$SCRIPT" ]; then
    ARTIFACT_OK=0
    note "ARTIFACT-MISSING: $SCRIPT not found (not yet written -- expected)."
fi
if [ ! -x "$FAKE_BIN/gh" ]; then
    ARTIFACT_OK=0
    note "ARTIFACT-MISSING: $FAKE_BIN/gh not executable"
fi
chmod +x "$FAKE_BIN/gh" 2>/dev/null || true

run_test() {
    local name="$1" fn="$2"
    if [ "$ARTIFACT_OK" -eq 0 ]; then
        note "FAIL $name" "  (artifact missing: $SCRIPT)"
        FAIL=$((FAIL + 1))
        return
    fi
    if "$fn"; then
        PASS=$((PASS + 1))
        note "PASS $name"
    else
        FAIL=$((FAIL + 1))
        note "FAIL $name"
    fi
}

run_test "green-exact (exit 0, GREEN)"                   test_green
run_test "mixed-same-context (all-runs-must-pass RED)"  test_mixed
run_test "missing-context (fail-closed RED)"            test_missing
run_test "pending -> RED"                                test_pending
run_test "sidecar-only -> RED (data-only)"               test_sidecar
run_test "api-error -> RED (fail fast)"                  test_api_error
run_test "shell-injection in ref -> RED"                 test_injection
run_test "timeout guard (hang < 55s)"                    test_timeout_guard
run_test "gh missing -> RED with clear error"            test_gh_missing
run_test "AC4: no writes on RED path"                    test_ac4_no_writes

note ""
note "Summary: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0