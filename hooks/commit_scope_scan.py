#!/usr/bin/env python3
"""
commit_scope_scan.py — shared, importable commit-scope-violation scanner.

Extracted from `hooks/loop_stop_guard.py`'s pre-existing `H-REVIEW-COMMIT-1`
gate (originally lines 928-1110, a monolithic inline `try` block) into a
reusable, pure function so BOTH `loop_stop_guard.py` (Oga's own Stop hook)
and `hooks/subagent_stop_gate.py` (a sub-agent's SubagentStop hook) can call
the SAME detection logic without duplicating ~180 lines of regex/SHA-
extraction/scope-check code (spec.md H-SUBAGENT-COMMIT-GATE-1, item 1).

This module is stdlib-only and imports NEITHER `loop_stop_guard.py` NOR
`subagent_stop_gate.py` — that would recreate the exact "one hook imports the
other hook's internals" coupling this module's own placement exists to avoid
(spec.md item 1, "Where should this shared function live?").

`find_commit_scope_violations()` is a PURE function: it takes the
tool_uses/tool_results/target to scan explicitly as arguments and makes no
assumption about WHICH transcript they came from (Oga's own current turn, or
a sub-agent's own flat transcript) — it must not read any module-level state
belonging to either calling hook file.
"""
import re
import subprocess


# Item 1: detect a raw `git commit`-shaped Bash/Shell tool_use. The literal
# token `git`, then any run of whitespace-separated non-`commit` tokens
# (accommodates `git -C <repo> commit ...`, `git -c a=1 -c b=2 commit ...`,
# etc.), then the token `commit` as a whole word. Bound at {0,15}
# intermediate tokens (live-verified: a real invocation stacking multiple -c
# overrides needs more than the {0,5} an earlier draft used). This also
# matches real, unrelated git subcommands that merely CONTAIN "commit" as a
# dotted config key (e.g. `git config commit.gpgsign false`) — not a
# detection bug; the success-line extraction below (which such commands
# never produce) is what actually neutralizes those, not a narrower regex
# here. Reused byte-for-byte from the pre-refactor inline gate.
_rc_commit_re = re.compile(r'\bgit\b(?:\s+\S+){0,15}\s+commit\b')

# Item 2: tolerate a multi-token, space-containing phrase between `[` and
# the sha — `[main (root-commit) 7d4787e] msg` and `[detached HEAD 47d9bf9]
# msg` both have more than one whitespace-free token there. The non-greedy
# `.+?` matches up to the LAST whitespace-delimited hex run immediately
# before `]`. Reused byte-for-byte from the pre-refactor inline gate.
_rc_sha_re = re.compile(r'^\[.+?\s([0-9a-f]{7,40})\]', re.MULTILINE)

# Scope list (verbatim from orchestrator.md's "Review-to-commit re-diff"
# section) — exact-match semantics per entry type: named repo-root files
# match iff the touched path, relative to <target>, equals EXACTLY that
# filename with no directory prefix (root-anchored, not basename-anywhere);
# loop-team/* matches iff the touched path starts with the literal prefix
# "loop-team/". The Scope section's own open-ended final clause ("any other
# file directly under loop-team/ or the repo root that is prose/config") is
# explicitly OUT OF SCOPE for this mechanical check — deciding "is this
# prose/config vs. code" is a semantic call a path-match cannot make
# reliably; that part stays instructional-only.
_rc_named_files = {
    "RUN.md", "VERIFIER.md", "VERIFIER_RENTALS.md", "fix_plan.md",
    "search_playbook.md",
}


def _tu_input(tu):
    """Inlined copy of loop_stop_guard.py's module-level `_tu_input(tu)`
    helper (current line 93, a trivial one-line body with no module-state
    dependency) — per spec.md item 1's dependency-correction, this module
    must not import either hook file, so the trivial body is copied here
    directly rather than imported."""
    import json
    return json.dumps(tu.get("input", "")).lower()


def _rc_result_text(tr):
    """Dedicated, newline-preserving text accessor for this gate's
    result_text. A plain space-join of multi-part `content` lists can
    destroy the newline immediately preceding `[` at a part boundary —
    breaking re.MULTILINE's `^` anchor. Reused byte-for-byte from the
    pre-refactor inline gate."""
    c = tr.get("content", "")
    if isinstance(c, list):
        c = "\n".join((p.get("text", "") if isinstance(p, dict) else str(p)) for p in c)
    return str(c)


def _rc_in_scope(path):
    """Root-anchored exact-match + `loop-team/` prefix semantics. Reused
    byte-for-byte from the pre-refactor inline gate."""
    path = path.strip()
    if not path:
        return False
    if path in _rc_named_files:
        return True
    if path.startswith("loop-team/"):
        return True
    return False


def find_commit_scope_violations(tool_uses, tool_results, target):
    """Returns a list of (sha, [touched_scope_files]) tuples. Pure function:
    takes the tool_uses/tool_results/target to scan explicitly as arguments,
    makes no assumption about WHICH transcript they came from (Oga's own
    turn, or a sub-agent's own transcript).

    Mirrors, byte-for-byte in behavior, the pre-refactor inline gate in
    hooks/loop_stop_guard.py: detect commit-shaped Bash tool_use -> extract
    SHA(s) via re.finditer -> per-SHA `git show --name-only` with an explicit
    `.returncode` check -> scope-match. Per-SHA isolation: one SHA's
    git-show failure must not discard an already-confirmed violation from
    another SHA.

    Any exception raised by an individual step (a malformed tool_result
    shape, a `git show` subprocess failure) is caught locally and treated as
    "this item contributes nothing" — callers are still responsible for
    their OWN outer fail-open wrapper for anything unexpected that escapes
    this function entirely, per each hook file's own fail-open discipline.
    """
    def _rc_tool_result_for(tu):
        """Correlate a tool_use to its own tool_result via the same
        dual-fallback id lookup used elsewhere in this file family."""
        _tid = tu.get("id") or tu.get("tool_use_id")
        if not _tid:
            return None
        for _tr in tool_results:
            if _tr.get("tool_use_id") == _tid:
                return _tr
        return None

    # Item 1: collect every matching Bash/Shell tool_use in the turn.
    _rc_candidate_tus = [
        _tu for _tu in tool_uses
        if _tu.get("name", "").lower() in ("bash", "shell")
        and _rc_commit_re.search(_tu_input(_tu))
    ]

    # Item 2: for each, extract EVERY candidate SHA from its own paired
    # tool_result via re.finditer (never re.search — a single tool_use can
    # chain multiple commits, e.g. `git commit -m "a" && git commit -m "b"`,
    # and every produced SHA must be collected, not just the first).
    _rc_shas = []  # list of (sha, source_tool_use) for message-building
    for _rc_tu in _rc_candidate_tus:
        _rc_tr = _rc_tool_result_for(_rc_tu)
        if _rc_tr is None:
            continue
        _rc_text = _rc_result_text(_rc_tr)
        for _rc_m in _rc_sha_re.finditer(_rc_text):
            _rc_shas.append((_rc_m.group(1), _rc_tu))

    # Item 3 continued: per-SHA git show --name-only, with explicit
    # .returncode check (the load-bearing mechanism, not the try/except
    # alone — a failed git command does not raise here, it returns a
    # CompletedProcess with nonzero .returncode) and per-SHA isolation (one
    # SHA's failure must not discard an already-confirmed violation from an
    # earlier SHA in the same loop).
    _rc_violations = []  # list of (sha, [scope_files])
    for _rc_sha, _rc_src_tu in _rc_shas:
        try:
            _rc_show = subprocess.run(
                ["git", "-C", target, "show", "--name-only", "--format=", _rc_sha],
                capture_output=True, text=True, timeout=30,
            )
        except Exception:
            continue  # this SHA contributes nothing; keep going
        if _rc_show.returncode != 0:
            continue  # e.g. returncode 128 "fatal: bad object" — not raised
        _rc_touched = [ln.strip() for ln in _rc_show.stdout.splitlines() if ln.strip()]
        _rc_hit = [p for p in _rc_touched if _rc_in_scope(p)]
        if _rc_hit:
            _rc_violations.append((_rc_sha, _rc_hit))

    return _rc_violations
