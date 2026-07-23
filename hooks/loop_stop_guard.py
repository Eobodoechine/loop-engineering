#!/usr/bin/env python3
"""
loop_stop_guard.py — Stop hook that ACTIVELY BLOCKS the agent from finishing a turn in which it
built/edited a feature but did NOT run an independent verifier sub-agent.

This is the real enforcement ("something that can say no"): it blocks the AGENT, not the user.
On Stop, Claude Code passes {transcript_path, stop_hook_active}. We scan the current turn:
  - feature_work  = a Write/Edit to a skill/script/loop/build/.py/.skill artifact (not a resume/doc)
  - verifier_ran  = a Task (sub-agent) call whose prompt invokes the independent verifier
If feature_work and not verifier_ran -> exit 2 with a message on stderr; Claude Code feeds that back
and the agent must continue (i.e., run the loop). stop_hook_active guards against re-entry loops.

Evidence-Gate Phase 4 (this build's own spec) adds three new gates that
validate `fix_plan.md` CLOSED-heading closures against this file's own
`Proof:` block requirements:
  - Part C: detects a CLOSED heading whose closure-relevant portion
    (heading line or Proof: span) OGA'S OWN turn touched directly.
  - Part D: a self-healing Layer-1 flag-file bridge for `.closure_violation`
    flags a dispatched sub-agent's own SubagentStop hook may have written --
    unlike a commit-violation flag (an immutable historical fact), a
    closure-violation flag describes a FIXABLE state, so each fresh flag is
    RE-VALIDATED (self-healing) against the CURRENT on-disk fix_plan.md
    before it is allowed to block; a flag whose named heading(s) are now
    all clean is deleted rather than left to block for the rest of its TTL.
  - Part E: a closure-gate Layer 2 that directly scans a dispatched
    sub-agent's own transcript (mirroring the REVIEW_COMMIT gate's own
    Layer 2), covering the async-race case where Oga's Stop hook fires
    before the sub-agent's own SubagentStop has run and written a flag.

All three gates share one theme-4 advisory-vs-blocking split: the LIVE-git-
worktree-reading checks (staleness, dirty-worktree) are ADVISORY ONLY in
this automated hook path -- they are still surfaced as WARNING diagnostics
(on stderr, or embedded in a violation's own message text) but never by
themselves cause a block. Missing/incomplete/fabricated Proof blocks remain
unconditionally blocking in every path.

INSTALL: see README.md (hooks.Stop in ~/.claude/settings.json).
"""
import sys, json, re, glob, os, fnmatch, time, difflib, tempfile

# H-PRETOOLUSE-VERIFIER-HYGIENE-1 Part 2: the hygiene/adjacency detection
# logic (previously inline in this file) now lives in the sibling module
# verifier_hygiene_scan.py so hooks/pre_tool_use_oga_guard.py can run the
# IDENTICAL check before a dispatch fires, not just this file after it fires
# -- one canonical implementation, not two that can drift (the exact class
# of bug H-VERIFIER-REGEX-DUPLICATE-1 already found once). sys.path setup
# follows the same sibling-module convention already used elsewhere in this
# hooks/ directory (e.g. pre_tool_use_oga_guard.py's own dispatch_check_presence
# import).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verifier_hygiene_scan import (
    VERIFIER_DETECT as _VERIFIER_DETECT,
    hyg_markers as _shared_hyg_markers,
    hyg_known_lines as _shared_hyg_known_lines,
    evaluate_hygiene as _shared_evaluate_hygiene,
    adj_read_target_dir as _shared_adj_read_target_dir,
    evaluate_adjacency as _shared_evaluate_adjacency,
    # _adj_extract_tokens/_adj_candidate_paths are also called directly (not
    # through evaluate_adjacency) by the separate run-log enforcement gate
    # further down this file (H-RUNLOG-LOGGING-GAPS-1) -- kept available
    # under their original names via this alias so that gate's own code
    # (out of this refactor's blast radius; not touched) continues to work
    # unchanged now that the inline definitions are gone.
    adj_extract_tokens as _adj_extract_tokens,
    adj_candidate_paths as _adj_candidate_paths,
)
import spec_bound_verifier_credit as _spec_credit

# Deliverable A (Codex enforcement parity, spec-codex-parity-and-consent-
# installer-2026-07-09.md): the shared runtime discriminator + Codex-shaped
# Verifier-dispatch extractor, imported the SAME sibling-module way as
# verifier_hygiene_scan.py above -- one canonical implementation. Wrapped in
# try/except (module import can, in principle, fail mid-build on this very
# file's own sibling) so a broken/missing adapter NEVER breaks the existing,
# unmodified Claude-Code-shaped scan below: it just falls back to "unknown",
# which is this module's own pre-existing behavior on every non-Codex
# transcript today (zero regression on the runtime this framework's other
# gates already rely on).
try:
    from codex_transcript_adapter import (
        _detect_runtime as _detect_codex_runtime,
        extract_verifier_dispatches as _codex_extract_verifier_dispatches,
        extract_spec_credit_records as _codex_extract_spec_credit_records,
    )
except Exception:
    def _detect_codex_runtime(_tpath):
        return "unknown"

    def _codex_extract_verifier_dispatches(_tpath, current_turn_only=False):
        return []

    def _codex_extract_spec_credit_records(_tpath):
        return []

try:
    from loop_logger import log_gate as _log_gate
except Exception:
    _log_gate = None

try:
    from codex_hook_stdin_capture import capture_once as _capture_codex_stdin_once
except Exception:
    def _capture_codex_stdin_once(_raw_stdin, _source_hook):
        return

# AC1 (plan_check_spec.md): a plan-pass flag counts as fresh credit iff
# now - mtime(flag) <= PLAN_PASS_TTL_SECONDS. Module-level so tests can
# monkeypatch it.
PLAN_PASS_TTL_SECONDS = 24 * 3600

_VIOLATIONS = []

try:
    _RAW_STDIN = sys.stdin.read()
    _capture_codex_stdin_once(_RAW_STDIN, "loop_stop_guard.py")
    data = json.loads(_RAW_STDIN)
except Exception:
    sys.exit(0)

if data.get("stop_hook_active"):   # already continued due to this hook once — don't trap
    sys.exit(0)

tpath = data.get("transcript_path")
if not tpath:
    sys.exit(0)

# Read the transcript (JSONL). Only inspect the CURRENT turn (since the last user message).
try:
    lines = open(tpath, encoding="utf-8").read().splitlines()
except Exception:
    sys.exit(0)

events = []
_TRANSCRIPT_JSONL_STRICT = True
for ln in lines:
    try:
        events.append(json.loads(ln))
    except Exception:
        _TRANSCRIPT_JSONL_STRICT = False

# walk back to the start of the current turn = the last HUMAN user message.
# NB: in real Claude Code transcripts, tool_results are recorded as user-type
# entries too. Slicing at the last user-type entry would cut the turn off at a
# trailing tool_result (e.g. after running a command) and drop the edit that
# preceded it -- silently bypassing the gate. So skip user entries that merely
# carry a tool_result, and stop at the genuine human turn boundary.
def _content(e):
    m = e.get("message")
    if isinstance(m, dict) and "content" in m:
        return m["content"]
    return e.get("content")

def _is_tool_result_turn(e):
    c = _content(e)
    if isinstance(c, list):
        return any(isinstance(p, dict) and p.get("type") == "tool_result" for p in c)
    return False

start = 0
for i in range(len(events) - 1, -1, -1):
    e = events[i]
    is_user = e.get("role") == "user" or e.get("type") == "user"
    if is_user and not _is_tool_result_turn(e):
        start = i; break
turn = events[start:]
blob = json.dumps(turn).lower()

# --- Structural extraction of real tool calls/results (NOT free text) ---
# Verification signals (a suite run, a spawned verifier) are read ONLY from
# actual tool_use / tool_result entries. If they were matched against the blob,
# an agent could bypass the gate by merely WRITING "run_evals.py ... SUITE:
# GREEN ... independent verifier" in prose without running anything.
def _parts(evs):
    for e in evs:
        c = _content(e)
        if isinstance(c, list):
            for p in c:
                if isinstance(p, dict):
                    yield p

_TOOL_USES = [p for p in _parts(turn) if p.get("type") == "tool_use"]
_TOOL_RESULTS = [p for p in _parts(turn) if p.get("type") == "tool_result"]
_TURN_RECORDS = _spec_credit.flatten_records(_spec_credit.current_turn(events))
try:
    if _detect_codex_runtime(tpath) == "codex":
        _TURN_RECORDS = _codex_extract_spec_credit_records(tpath)
except Exception:
    # Preserve the hook's existing fail-open behavior for adapter drift; the
    # Claude-Code-shaped path remains unchanged for non-Codex transcripts.
    pass

# ── Layer 1 (PRIMARY, authoritative): flag-file bridge (H-SUBAGENT-COMMIT-
# GATE-1, spec item 3). A dispatched sub-agent's own SubagentStop hook
# (hooks/subagent_stop_gate.py) may have detected a raw `git commit` on a
# scope-listed file inside ITS OWN Bash tool_use and written a
# `{session_id}_{agent_id}.commit_violation` flag under $LOOP_GATE_DIR. This
# gate globs for any FRESH such flag belonging to THIS session and blocks
# Oga's own Stop on it — the only way Oga (who has real attention/visibility)
# learns a sub-agent's raw commit ever happened, since SubagentStop's own
# sys.exit(2) blocks only the ALREADY-FINISHED sub-agent's turn, never Oga's.
#
# Placement (spec.md item 3, "Placement, made explicit", round-3 pinned
# anchor): immediately after the _TOOL_USES/_TOOL_RESULTS construction above
# (the end of the structural/transcript-parsing preamble) and strictly
# BEFORE line ~414 (ROLE_OR_HARNESS_EDIT, the FIRST existing sys.exit(2)-
# capable gate in this file) — this is before EVERY existing gate that can
# exit early (ROLE_OR_HARNESS_EDIT, FEATURE, the plan-check gate, the
# research gate, the hygiene/adjacency gates, the micro-step-gates block,
# the existing H-REVIEW-COMMIT-1 gate), not merely before `_plan_check_
# violated`. This ensures a real `.commit_violation` flag is never silently
# skipped merely because some OTHER gate happens to fire first this turn.
# Layer 1 needs no `_rc_target` (it only reads/parses `.commit_violation`
# flag files, no dependency on `_msg_mod`/`_LAST_ACTIVATION`), so this early
# placement introduces no ordering contradiction with item 1(b)'s
# requirement to leave `_rc_target`'s resolution at its original location.
#
# Exception-handling layering (spec.md item 3, "Exception-handling layering,
# made explicit"): the JSON-parse step for each fresh flag's content is
# wrapped in its OWN, INNER try/except (below) that specifically catches
# JSON decode/shape errors and treats them as "malformed but still a
# violation" (AC4b) — this inner catch is NOT the same exception scope as
# THIS outer, file-spanning try/except, which exists ONLY to catch genuinely
# unexpected exceptions (a glob() failure, an unexpected OSError variant,
# etc.) for fail-open ALLOW (AC13b). A single flat try/except around the
# entire gate body would incorrectly let a JSON decode error fall through to
# fail-open, silently violating the malformed-content requirement.
try:
    import glob as _l1_glob, os as _l1_os, time as _l1_time, json as _l1_json

    _l1_gate_dir = _l1_os.path.expanduser(
        _l1_os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
    _l1_session_id = data.get("session_id", "") or ""  # None-safe
    if _l1_session_id:
        # Escaped via glob.escape, mirroring the EXACT pattern the PLAN_PASS
        # credit block already uses at its own glob call — a metachar
        # session_id still finds its own literal-named fresh flag, and can
        # never wildcard-match a different session's flag.
        _l1_flags = _l1_glob.glob(_l1_os.path.join(
            _l1_gate_dir, "%s_*.commit_violation" % _l1_glob.escape(_l1_session_id)))
    else:
        _l1_flags = []

    _l1_now = _l1_time.time()
    _l1_fresh_reports = []  # list of (agent_id, evidence_str)
    _l1_flagged_shas = set()  # (agent_id, sha) tuples — populated below, per SHA
    for _l1_f in _l1_flags:
        try:
            _l1_mtime = _l1_os.path.getmtime(_l1_f)
        except OSError:
            continue
        if (_l1_now - _l1_mtime) > PLAN_PASS_TTL_SECONDS:
            # Stale — best-effort cleanup, mirroring the PLAN_PASS sweep.
            # Never touched on a FRESH match (non-consuming design, mirrors
            # H-GUARD-3/H-LT7b) — Oga must actually address the violation.
            try: _l1_os.remove(_l1_f)
            except OSError: pass
            continue

        # FRESH match — parse agent_id from the filename (algorithm, made
        # explicit, round-2 finding): basename = os.path.basename(flag_path);
        # strip the .commit_violation suffix; session_id, agent_id =
        # stripped.rsplit("_", 1) — safe because real session_id (a UUID)
        # and agent_id (observed live: alphanumeric) values never contain
        # underscores.
        _l1_basename = _l1_os.path.basename(_l1_f)
        _l1_stripped = _l1_basename
        if _l1_stripped.endswith(".commit_violation"):
            _l1_stripped = _l1_stripped[: -len(".commit_violation")]
        if "_" in _l1_stripped:
            _l1_sid_part, _l1_agent_id = _l1_stripped.rsplit("_", 1)
        else:
            _l1_agent_id = _l1_stripped

        # Malformed content handling, made explicit (round-1/round-2
        # findings): if the content is not valid JSON, is valid JSON but not
        # the expected [{"sha": ..., "touched": [...]}, ...] shape, OR is a
        # syntactically-valid empty list [] (treated the same as malformed,
        # since a fresh flag existing at all signals a detected violation
        # regardless of what its content parses to) — the gate must STILL
        # BLOCK, with a message naming the agent_id and stating the detail
        # could not be parsed, rather than crashing or silently allowing.
        # This inner try/except is deliberately scoped to JUST the JSON
        # parse/shape-check — it must not be the same exception scope as the
        # outer, file-spanning wrapper (AC13b).
        _l1_evidence = None
        try:
            with open(_l1_f, encoding="utf-8") as _l1_fh:
                _l1_content = _l1_fh.read()
            _l1_parsed = _l1_json.loads(_l1_content)
            if (not isinstance(_l1_parsed, list) or not _l1_parsed
                    or not all(
                        isinstance(_l1_item, dict)
                        and "sha" in _l1_item and "touched" in _l1_item
                        for _l1_item in _l1_parsed)):
                raise ValueError("malformed or empty violation content shape")
            _l1_parts_str = []
            for _l1_item in _l1_parsed:
                _l1_sha = _l1_item.get("sha")
                _l1_touched = _l1_item.get("touched")
                # Dedup-set membership is attempted in its OWN narrow
                # try/except, isolated from evidence-string building: an
                # unhashable sha on THIS item must never poison or discard a
                # SIBLING item's own reporting (the exact masking bug this
                # isolation exists to close — see adversarial test
                # DedupKeyPoisoningFromMalformedSiblingItem).
                try:
                    _l1_flagged_shas.add((_l1_agent_id, _l1_sha))
                except TypeError:
                    pass  # unhashable sha -- cannot be meaningfully deduped, contributes nothing
                _l1_touched_str = (", ".join(str(_x) for _x in _l1_touched)
                                    if isinstance(_l1_touched, list) else str(_l1_touched))
                _l1_parts_str.append("%s (touches: %s)" % (
                    _l1_sha, _l1_touched_str))
            _l1_evidence = "; ".join(_l1_parts_str)
        except Exception:
            _l1_evidence = ("<could not parse violation detail from flag "
                            "content — the flag's existence alone still "
                            "signals a detected violation>")

        _l1_fresh_reports.append((_l1_agent_id, _l1_evidence))

    if _l1_fresh_reports:
        # Multi-violation handling: report EVERY fresh flag's content, not
        # just the first found — do not let Oga clear the block after
        # addressing only one violation while another sits unaddressed.
        _l1_lines = ["agent %s: %s" % (_aid, _ev) for _aid, _ev in _l1_fresh_reports]
        if _log_gate:
            _log_gate("SUBAGENT_COMMIT_VIOLATION", True, "; ".join(_l1_lines)[:200], 2)
        _l1_msg = (
            "[LOOP STOP-GUARD] Layer 1 (flag-file bridge): a dispatched "
            "sub-agent ran a raw `git commit` this turn (or a prior turn "
            "within the TTL window) that touched scope-listed shared "
            "framework file(s) WITHOUT going through commit_diff_reread.py's "
            "re-diff-immediately-before-commit guarantee: "
            + "; ".join(_l1_lines) + ". This content was NOT re-verified "
            "against what was actually reviewed. Remedy now: run `git show "
            "<sha>` (or `git diff <sha>~1 <sha>`) for each SHA above against "
            "the ACTUAL committed bytes, and decide whether to keep/revert/"
            "route the content through the normal loop — per "
            "orchestrator.md's \"Review-to-commit re-diff\" section, \"On a "
            "`committed: false` result\" guidance (the same remedy prescribed "
            "for this incident class when caught by `check`)."
        )
        _VIOLATIONS.append(("SUBAGENT_COMMIT_VIOLATION", _l1_msg))
except SystemExit:
    raise
except Exception as _l1_e:
    # Blanket fail-open requirement, made explicit (round-1 finding): this
    # new gate's ENTIRE logic (glob, TTL check, multi-flag aggregation, and
    # any exception NOT caught by the inner JSON-parse try/except above)
    # MUST be wrapped the same file-spanning way every other risk-bearing
    # gate in this file already uses — not just PLAN_PASS's narrower
    # per-call try/except OSError pattern, and not in a way that swallows
    # the JSON-parse step's own, more-specific handling above.
    sys.stderr.write(
        "[subagent-commit-violation-gate] disabled by error (fail-open): %r\n"
        % (_l1_e,))


# ── Part D (Evidence-Gate Phase 4, self-healing Layer-1 flag-file bridge for
# closure violations) ───────────────────────────────────────────────────────
# spec: this build's own spec, "Part D, redesigned -- self-healing Layer-1
# flag-file bridge". Structural mirror of
# the SUBAGENT_COMMIT_VIOLATION Layer 1 block immediately above (same glob-
# for-{session_id}_*.EXT-under-$LOOP_GATE_DIR shape, same TTL, same non-
# consuming-on-fresh-match/stale-cleanup-on-expiry semantics, same
# malformed-content-still-blocks handling, same _log_gate call) for
# `.closure_violation` flags a sub-agent's own SubagentStop hook
# (subagent_stop_gate.py's Fifth responsibility) may have written -- PLUS
# theme 5's self-healing addition: unlike a commit-violation flag (an
# immutable historical fact), a closure-violation flag describes a FIXABLE
# state (Oga can add/correct a Proof block after the fact), so before
# treating a fresh flag as a block, each of its named headings is RE-
# CHECKED against the CURRENT on-disk fix_plan.md via
# fixplan_closure_lint.check_single_heading(advisory=True). A heading whose
# re-check finds zero blocking messages is dropped (fixed); if EVERY named
# heading in a flag is now clean, the flag itself is deleted (best-effort)
# instead of lingering for the rest of its TTL; if some but not all are
# fixed, the flag is rewritten to keep only the still-bad entries and only
# those are reported/blocked.
#
# Placement: same early placement rationale as the SUBAGENT_COMMIT_VIOLATION
# Layer 1 block above (before EVERY existing gate that can exit early,
# including the PLAN_CHECK short-circuit region below) -- Part D needs no
# _rc_target/_msg_mod dependency (independent __file__-relative resolution,
# theme 1's fix), so this early placement introduces no ordering
# contradiction.
#
# _pd_reported_headings is declared OUTSIDE the try block (spec: "Part D
# must expose the set of heading_line strings it reported as still-
# violating this turn... as a value Part E can read and dedup against") so
# it is guaranteed to exist (as an empty set, at minimum) for Part E to read
# even if Part D's own try block fails open partway through.
_pd_reported_headings = set()
try:
    import glob as _pd_glob, os as _pd_os, time as _pd_time, json as _pd_json, sys as _pd_sys

    _pd_sys.path.insert(0, _pd_os.path.dirname(_pd_os.path.abspath(__file__)))
    _pd_harness_dir = _pd_os.path.normpath(_pd_os.path.join(
        _pd_os.path.dirname(_pd_os.path.abspath(__file__)),
        "..", "loop-team", "harness"))
    _pd_sys.path.insert(0, _pd_harness_dir)
    from fixplan_closure_lint import check_single_heading as _pd_check_heading
    from status_claim_audit import audit_fix_plan_content as _pd_status_audit

    _pd_target_path = _pd_os.path.join(
        _pd_os.path.dirname(_pd_os.path.abspath(__file__)), "..", "fix_plan.md")

    _pd_gate_dir = _pd_os.path.expanduser(
        _pd_os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
    _pd_session_id = data.get("session_id", "") or ""
    if _pd_session_id:
        _pd_flags = _pd_glob.glob(_pd_os.path.join(
            _pd_gate_dir, "%s_*.closure_violation" % _pd_glob.escape(_pd_session_id)))
    else:
        _pd_flags = []

    _pd_now = _pd_time.time()
    _pd_fresh_reports = []  # list of (agent_id, evidence_str)
    _pd_target_content = None
    _pd_target_content_loaded = False

    for _pd_f in _pd_flags:
        try:
            _pd_mtime = _pd_os.path.getmtime(_pd_f)
        except OSError:
            continue
        if (_pd_now - _pd_mtime) > PLAN_PASS_TTL_SECONDS:
            # Stale -- best-effort cleanup, mirroring Layer 1's own sweep.
            try: _pd_os.remove(_pd_f)
            except OSError: pass
            continue

        # FRESH match -- parse agent_id from the filename, same algorithm as
        # Layer 1 (basename minus the .closure_violation suffix, rsplit on
        # the last "_" -- safe because a real session_id/agent_id never
        # contains an underscore).
        _pd_basename = _pd_os.path.basename(_pd_f)
        _pd_stripped = _pd_basename
        if _pd_stripped.endswith(".closure_violation"):
            _pd_stripped = _pd_stripped[: -len(".closure_violation")]
        if "_" in _pd_stripped:
            _pd_sid_part, _pd_agent_id = _pd_stripped.rsplit("_", 1)
        else:
            _pd_agent_id = _pd_stripped

        # Malformed content handling (same as Layer 1): not valid JSON, not
        # the expected [{"heading": ...}, ...] shape, or a syntactically-
        # valid empty list -- the flag's own existence still signals a
        # detected violation; it cannot be self-healed (no heading list to
        # re-check), so it is reported as-is, unconditionally.
        try:
            with open(_pd_f, encoding="utf-8") as _pd_fh:
                _pd_raw_content = _pd_fh.read()
            _pd_entries = _pd_json.loads(_pd_raw_content)
            if (not isinstance(_pd_entries, list) or not _pd_entries
                    or not all(
                        isinstance(_pd_e, dict) and "heading" in _pd_e
                        for _pd_e in _pd_entries)):
                raise ValueError("malformed or empty closure_violation content shape")
        except Exception:
            _pd_fresh_reports.append((
                _pd_agent_id,
                "<could not parse closure-violation detail from flag "
                "content -- the flag's existence alone still signals a "
                "detected violation>",
            ))
            continue

        # Self-healing re-validation (theme 5): re-run check_single_heading
        # against the CURRENT on-disk fix_plan.md (read ONCE per hook
        # firing, lazily, only once we know we actually need it -- an
        # unreadable fix_plan.md here is an unavoidable, undefended file
        # read per spec; it propagates to this gate's own outer
        # except/fail-open, exactly like every other risk-bearing gate).
        if not _pd_target_content_loaded:
            with open(_pd_target_path, encoding="utf-8") as _pd_cf:
                _pd_target_content = _pd_cf.read()
            _pd_target_content_loaded = True

        _pd_still_bad_entries = []
        _pd_status_findings = []
        try:
            _pd_status_result = _pd_status_audit(
                _pd_target_content, touched_ranges=None, full_sweep=True)
            _pd_status_findings = [
                _sf for _sf in (_pd_status_result.get("findings") or [])
                if _sf.get("blocking")
            ]
        except Exception:
            _pd_status_findings = []
        for _pd_entry in _pd_entries:
            _pd_heading = _pd_entry.get("heading")
            if not isinstance(_pd_heading, str):
                continue
            _pd_heading_status = [
                _sf for _sf in _pd_status_findings
                if _sf.get("heading") == _pd_heading
            ]
            if _pd_heading_status:
                _pd_still_bad_entries.append({
                    "heading": _pd_heading,
                    "messages": [
                        "status claim %r: %s" % (
                            _sf.get("claim"), _sf.get("classifier"))
                        for _sf in _pd_heading_status
                    ],
                    "warnings": [],
                })
                continue
            _pd_recheck = _pd_check_heading(
                _pd_target_content, _pd_heading, _pd_target_path, advisory=True)
            _pd_recheck_messages = _pd_recheck.get("messages") or []
            if _pd_recheck_messages:
                _pd_still_bad_entries.append({
                    "heading": _pd_heading,
                    "messages": _pd_recheck_messages,
                    "warnings": _pd_recheck.get("warnings") or [],
                })

        if not _pd_still_bad_entries:
            # Every named heading is now clean -- delete the flag
            # (best-effort) rather than leaving it to linger for the rest of
            # its TTL (theme 5: it no longer describes current reality).
            try: _pd_os.remove(_pd_f)
            except OSError: pass
            continue

        if len(_pd_still_bad_entries) < len(_pd_entries):
            # Partial fix -- rewrite the flag to drop the resolved
            # heading(s) so a stale, already-fixed entry never keeps getting
            # read on a future turn.
            try:
                with open(_pd_f, "w", encoding="utf-8") as _pd_wf:
                    _pd_wf.write(_pd_json.dumps(_pd_still_bad_entries))
            except OSError:
                pass

        _pd_parts_str = []
        for _pd_entry in _pd_still_bad_entries:
            _pd_heading = _pd_entry["heading"]
            _pd_reported_headings.add(_pd_heading)
            _pd_lines = list(_pd_entry.get("messages") or [])
            for _pd_w in (_pd_entry.get("warnings") or []):
                _pd_lines.append("WARNING (advisory, not blocking): %s" % _pd_w)
            _pd_parts_str.append("%r: %s" % (_pd_heading, "; ".join(_pd_lines)))
        _pd_fresh_reports.append((_pd_agent_id, "; ".join(_pd_parts_str)))

    if _pd_fresh_reports:
        _pd_lines_out = ["agent %s: %s" % (_aid, _ev) for _aid, _ev in _pd_fresh_reports]
        if _log_gate:
            _log_gate("CLOSURE_VALIDATION", True, "; ".join(_pd_lines_out)[:200], 2)
        _pd_msg = (
            "[LOOP STOP-GUARD] CLOSURE_VALIDATION Part D (flag-file bridge): "
            "a dispatched sub-agent touched the closure-relevant portion of a CLOSED "
            "fix_plan.md heading this turn (or a prior turn within the TTL "
            "window) that still has unresolved issue(s) on re-check: "
            + "; ".join(_pd_lines_out) + ". Fix the Proof block(s) named "
            "above (or if already fixed, this flag should self-heal on the "
            "next Stop)."
        )
        _VIOLATIONS.append(("CLOSURE_VALIDATION", _pd_msg))
except SystemExit:
    raise
except Exception as _pd_e:
    sys.stderr.write(
        "[closure-violation-flag-bridge-gate] disabled by error (fail-open): %r\n"
        % (_pd_e,))


# ── Part E (Evidence-Gate Phase 4, closure-gate Layer 2 -- direct sub-agent-
# transcript scan) ──────────────────────────────────────────────────────────
# spec: "Part E, new -- closure-gate Layer 2 (direct sub-agent-transcript
# scan)". Structurally mirrors the REVIEW_COMMIT gate's own Layer 2 (its
# sub-agent-transcript-enumeration mechanism via a raw JSONL event's
# top-level `toolUseResult.agentId` key, and its dedup-against-Layer-1
# approach) but explicitly NOT its placement: REVIEW_COMMIT's Layer 2 sits
# late (after the PLAN_CHECK credit region, deep in the file) only because
# it depends on `_rc_target`, which is not resolved until deep inside the
# micro-step-gates block. Part E has NO `_rc_target` dependency (theme 1's
# fix applies here too -- independent __file__-relative resolution) and is
# placed HERE, immediately after Part D, so Part D's own
# `_pd_reported_headings` accumulator already exists for Part E to dedup
# against, and so Part E always runs -- even on a fresh-plan-pass-credit
# Coder-dispatch turn that would otherwise reach the PLAN_CHECK region
# before Part E's own code ever executed.
try:
    import sys as _pe_sys, os as _pe_os, json as _pe_json

    _pe_sys.path.insert(0, _pe_os.path.dirname(_pe_os.path.abspath(__file__)))
    from closure_touch_scan import find_touched_closed_headings as _pe_find_touched

    _pe_harness_dir = _pe_os.path.normpath(_pe_os.path.join(
        _pe_os.path.dirname(_pe_os.path.abspath(__file__)),
        "..", "loop-team", "harness"))
    _pe_sys.path.insert(0, _pe_harness_dir)
    from fixplan_closure_lint import check_single_heading as _pe_check_heading
    from status_claim_audit import (
        audit_fix_plan_content as _pe_status_audit,
        touched_ranges_for_tool_uses as _pe_status_touched_ranges,
    )

    _pe_target_path = _pe_os.path.join(
        _pe_os.path.dirname(_pe_os.path.abspath(__file__)), "..", "fix_plan.md")

    _pe_agent_ids = []
    for _pe_ev in turn:
        _pe_tur = _pe_ev.get("toolUseResult")
        if isinstance(_pe_tur, dict):
            _pe_aid = _pe_tur.get("agentId")
            if isinstance(_pe_aid, str) and _pe_aid and _pe_aid not in _pe_agent_ids:
                _pe_agent_ids.append(_pe_aid)

    _pe_session_id = data.get("session_id") or ""
    _pe_reports = []  # list of (agent_id, [(heading, combined_text), ...])

    for _pe_aid in _pe_agent_ids:
        _pe_project_dir = _pe_os.path.dirname(tpath)
        _pe_sub_path = _pe_os.path.join(
            _pe_project_dir, _pe_session_id, "subagents",
            "agent-%s.jsonl" % _pe_aid)
        try:
            if not _pe_os.path.isfile(_pe_sub_path):
                continue
            _pe_sub_lines = open(_pe_sub_path, encoding="utf-8").read().splitlines()
        except Exception:
            continue  # fail open: unreadable/missing sub-agent transcript

        _pe_sub_events = []
        for _pe_ln in _pe_sub_lines:
            try:
                _pe_sub_events.append(_pe_json.loads(_pe_ln))
            except Exception:
                pass

        _pe_sub_tool_uses = [p for p in _parts(_pe_sub_events) if p.get("type") == "tool_use"]
        _pe_sub_tool_results = [p for p in _parts(_pe_sub_events) if p.get("type") == "tool_result"]
        _pe_blocked_ids = set()
        _pe_result_ids = set()
        for _pe_tr in _pe_sub_tool_results:
            _pe_tid = _pe_tr.get("tool_use_id") or _pe_tr.get("id")
            if not _pe_tid:
                continue
            _pe_result_ids.add(_pe_tid)
            _pe_txt = str(_pe_tr.get("content", "")).lower()
            if (_pe_tr.get("is_error") is True
                    or "denied this tool call" in _pe_txt[:200]
                    or _pe_txt.strip().startswith("hook pretooluse:")):
                _pe_blocked_ids.add(_pe_tid)

        def _pe_effective_tool_use(_pe_tu):
            _pe_nm = (_pe_tu.get("name") or "").lower()
            if _pe_nm not in ("write", "edit", "multiedit"):
                return True
            _pe_tid = _pe_tu.get("id") or _pe_tu.get("tool_use_id")
            if _pe_tid in _pe_blocked_ids:
                return False
            if _pe_tid and _pe_tid not in _pe_result_ids:
                _pe_inp = _pe_tu.get("input") if isinstance(_pe_tu.get("input"), dict) else {}
                if _pe_nm == "write":
                    return False
                if _pe_nm == "edit":
                    return _pe_inp.get("old_string") != _pe_inp.get("new_string")
                _pe_edits = _pe_inp.get("edits") or []
                return not all(
                    isinstance(_e, dict) and _e.get("old_string") == _e.get("new_string")
                    for _e in _pe_edits
                )
            return True

        _pe_effective_tool_uses = [
            _tu for _tu in _pe_sub_tool_uses if _pe_effective_tool_use(_tu)
        ]

        _pe_touched = _pe_find_touched(_pe_effective_tool_uses, _pe_target_path)

        try:
            with open(_pe_target_path, encoding="utf-8") as _pe_f:
                _pe_content = _pe_f.read()
        except OSError:
            continue

        _pe_hits = []
        for _pe_heading in _pe_touched:
            if _pe_heading in _pd_reported_headings:
                # Already reported by Part D's own flag-read this same turn
                # -- dedup, do not report the same heading twice.
                continue
            _pe_result = _pe_check_heading(
                _pe_content, _pe_heading, _pe_target_path, advisory=True)
            _pe_messages = _pe_result.get("messages") or []
            _pe_warnings = _pe_result.get("warnings") or []
            if not _pe_messages:
                for _pe_w in _pe_warnings:
                    sys.stderr.write(
                        "[LOOP STOP-GUARD] Part E WARNING (advisory, not "
                        "blocking) for CLOSED heading %r (agent %s): %s\n"
                        % (_pe_heading, _pe_aid, _pe_w))
                continue
            _pe_lines = list(_pe_messages)
            for _pe_w in _pe_warnings:
                _pe_lines.append("WARNING (advisory, not blocking): %s" % _pe_w)
            _pe_hits.append((_pe_heading, "; ".join(_pe_lines)))

        _pe_status_ranges = _pe_status_touched_ranges(
            _pe_effective_tool_uses, _pe_sub_tool_results, _pe_target_path,
            content=_pe_content)
        if _pe_status_ranges:
            _pe_status_result = _pe_status_audit(
                _pe_content, touched_ranges=_pe_status_ranges,
                full_sweep=False)
            for _pe_finding in (_pe_status_result.get("findings") or []):
                if not _pe_finding.get("blocking"):
                    continue
                _pe_heading = _pe_finding.get("heading")
                if _pe_heading in _pd_reported_headings:
                    continue
                _pe_hits.append((
                    _pe_heading,
                    "status claim %r: %s" % (
                        _pe_finding.get("claim"),
                        _pe_finding.get("classifier")),
                ))

        if _pe_hits:
            _pe_reports.append((_pe_aid, _pe_hits))

    if _pe_reports:
        _pe_lines_out = []
        for _pe_aid, _pe_hits in _pe_reports:
            for _pe_heading, _pe_text in _pe_hits:
                _pe_lines_out.append("agent %s: %r: %s" % (_pe_aid, _pe_heading, _pe_text))
        if _log_gate:
            _log_gate("SUBAGENT_CLOSURE_VIOLATION_LAYER2", True,
                       "; ".join(_pe_lines_out)[:200], 2)
        _pe_msg = (
            "[LOOP STOP-GUARD] SUBAGENT_CLOSURE_VIOLATION_LAYER2 (direct "
            "transcript scan): a sub-agent touched the closure-relevant "
            "portion of a CLOSED fix_plan.md heading this turn that still "
            "has unresolved issue(s): " + "; ".join(_pe_lines_out)
            + ". Fix the Proof block(s) named above."
        )
        _VIOLATIONS.append(("SUBAGENT_CLOSURE_VIOLATION_LAYER2", _pe_msg))
except SystemExit:
    raise
except Exception as _pe_e:
    sys.stderr.write(
        "[closure-violation-layer2-gate] disabled by error (fail-open): %r\n"
        % (_pe_e,))


def _tu_input(tu):
    return json.dumps(tu.get("input", "")).lower()


def _tu_dispatch_text(tu):
    """Detectable CLASSIFICATION text for a dispatch-shaped tool_use, regardless
    of tool type. Agent/Task tool_uses carry `description` at the input's top
    level -- returned ALONE when non-empty, matching the CURRENT, real
    behavior at sites 4-5 byte-for-byte (v1 mistakenly concatenated `prompt`
    in here too, which would have broadened _VERIFIER_DETECT's match surface
    to fire on a Coder dispatch whose PROMPT merely discusses verifier
    concepts -- reopening the exact confusion class H_GUARD_1_Regression
    already hardened this file against; fixed in v2, do not reintroduce).
    v8: when `description` is empty or absent entirely, falls back to
    `prompt` -- several established, pre-existing fixtures (predating this
    spec) have no `description` key at all and rely on prompt-only
    classification signal (e.g. VERIFIER_TASK = tool_use("Task",
    prompt="spawn an independent verifier...")); this fallback ONLY
    activates when description is empty, so it never re-widens the match
    surface for a dispatch that already has an unambiguous description (the
    H_GUARD_1_Regression class's own fixtures all have non-empty
    descriptions and never reach this branch). A `Workflow` tool_use carries
    no top-level 'description' at all -- its real dispatch content
    (including every embedded lens's own prompt text) lives in the 'script'
    field, handled by its own branch, unaffected by this fallback."""
    inp = tu.get("input") or {}
    if tu.get("name", "").lower() == "workflow":
        return str(inp.get("script", "")).lower()
    _desc = str(inp.get("description", "")).lower()
    if _desc:
        return _desc
    return str(inp.get("prompt", "")).lower()


def _tu_dispatch_prompt_text(tu):
    """Detectable SCAN text (path tokens, hygiene markers) for a dispatch-
    shaped tool_use. For Workflow tool_uses this is the full, un-lowercased
    script text (where per-lens prompts and any referenced paths live); for
    Agent/Task it's the prompt field verbatim, byte-identical to what the
    hygiene/adjacency gates already scan today for those tool types -- zero
    behavior change for the non-Workflow case."""
    inp = tu.get("input") or {}
    if tu.get("name", "").lower() == "workflow":
        return str(inp.get("script", ""))
    return str(inp.get("prompt", ""))


def _tr_text(tr):
    c = tr.get("content", "")
    if isinstance(c, list):
        c = " ".join((p.get("text", "") if isinstance(p, dict) else str(p)) for p in c)
    return str(c).lower()


# H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1 (spec-v5.md D.1): a PreToolUse deny
# does not remove the tool_use block from the transcript -- it only produces
# a correlated tool_result carrying a deny signature. Without this guard, a
# BLOCKED, never-executed dispatch is scanned identically to a live one by
# every downstream consumer of _TOOL_USES (see D.2's five load-bearing
# sites). `_tr_is_pretooluse_deny` is ANCHORED (startswith), not a substring
# match anywhere in the tool_result's text -- a substring check would also
# match a genuinely-dispatched sub-agent's own free-text report that merely
# DISCUSSES "PreToolUse"/"deny" as a topic (plausible, since this framework
# repeatedly builds/reviews specs about its own PreToolUse-deny mechanics --
# this very fix being an instance), wrongly excluding a real Verifier (see
# spec-v5.md Section A, v2 finding 2 / AC9).
def _tr_is_pretooluse_deny(tr):
    txt = _tr_text(tr).strip()  # already lowercased by _tr_text
    return (
        (txt.startswith("hook pretooluse:") and "denied this tool" in txt[:120])
        or txt.startswith("blocked before dispatch")
        or txt.startswith("[oga guard]")
    )


# Built exactly once, reused at all five load-bearing sites (AC6): the
# VERIFIER signal, the plan-check classification loop, the hygiene scan, the
# adjacency scan, and the Researcher-gate loop. `is_error is True` is an
# additional OR term at the outer set level -- a robustness hedge for a deny
# shape that doesn't match the string signature -- but is intentionally not
# used exclusively, since it would also exclude a Verifier that genuinely
# ran and then errored for an unrelated reason. This is purely ADDITIVE: it
# can only ever REMOVE a tool_use from a walk that would otherwise have
# included it, never make any site more permissive (Section D.3).
_blocked_tool_use_ids = {
    (tr.get("tool_use_id") or tr.get("id"))
    for tr in _TOOL_RESULTS
    if _tr_is_pretooluse_deny(tr) or tr.get("is_error") is True
}
_blocked_tool_use_ids.discard(None)


def _tu_id_is_blocked(tu):
    tid = tu.get("id") if tu.get("id") is not None else tu.get("tool_use_id")
    return isinstance(tid, str) and tid in _blocked_tool_use_ids


# H-LOOPSTOPGUARD-DUAL-TURN-WINDOW-FALSEDENY-1: the credit-gate's own
# plan-check-violation loop (below, ~line 1415) walks the WIDE _TURN_RECORDS
# window (built from the shared, turn-boundary-aware _spec_credit.current_turn),
# not the narrow local `turn` window _blocked_tool_use_ids above is built
# from. An earlier, already PreToolUse-denied Coder tool_use can fall INSIDE
# the wide window but OUTSIDE the narrow one -- _blocked_tool_use_ids never
# captures its id in that case, so the credit-gate loop wrongly treats it as
# a live, unauthorized dispatch and fires a false PLAN_CHECK violation before
# ever reaching a later, correctly-credited Coder dispatch. Fix: a SEPARATE
# wide-window blocked-ids set, sourced from _TURN_RECORDS the same way
# _blocked_tool_use_ids is sourced from _TOOL_RESULTS, used ONLY at the two
# credit-gate-specific call sites (this file's own PLAN_CHECK loop) -- the
# narrow _blocked_tool_use_ids variable and all its other ~13 consumers
# (findings-persistence, the repo-health structural-writes scan, the run-log
# gates, the review-commit gate, the hygiene/adjacency scans) are untouched.
_CREDIT_GATE_BLOCKED_IDS = {
    (rec["part"].get("tool_use_id") or rec["part"].get("id"))
    for rec in _TURN_RECORDS
    if rec.get("kind") == "tool_result"
    and (_tr_is_pretooluse_deny(rec["part"]) or rec["part"].get("is_error") is True)
}
_CREDIT_GATE_BLOCKED_IDS.discard(None)


def _credit_gate_tu_id_is_blocked(tu):
    tid = tu.get("id") if tu.get("id") is not None else tu.get("tool_use_id")
    return isinstance(tid, str) and tid in _CREDIT_GATE_BLOCKED_IDS


# H-FINDINGS-PERSISTENCE-1 v2: a marked adversarial-review dispatch that
# returns confirmed findings must persist them in the explicit target repo's
# KNOWN_ISSUES.md under the current FINDINGS_RUN_ID. This gate is independent
# of micro_step_gates target activation on purpose: TARGET_REPO is the only
# accepted repo source for this contract.
try:
    from adversarial_review_scan import find_findings_persistence_violations as _fp_find

    _fp_messages = _fp_find(
        _TOOL_USES,
        _TOOL_RESULTS,
        blocked_ids=_blocked_tool_use_ids,
        loop_root=os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")),
    )
    for _fp_msg in _fp_messages:
        if _log_gate:
            _log_gate("FINDINGS_PERSISTENCE_MISSING", True, _fp_msg[:120], 2)
        _VIOLATIONS.append(("FINDINGS_PERSISTENCE_MISSING", _fp_msg))
except SystemExit:
    raise
except Exception as _fp_e:
    sys.stderr.write(
        "[findings-persistence-gate] disabled by error (fail-open): %r\n" % (_fp_e,))


# Edit detection stays blob-based: over-firing on a mere mention is the SAFE
# direction (it only blocks unnecessarily). Under-detecting verification is not.
_CODE = r'(skills?/|hooks?/|\.py\b|\.skill\b|\.ts\b|\.tsx\b|\.js\b|\.jsx\b|\.go\b|\.rs\b|\.java\b|\.rb\b|\.sh\b|\.php\b|\.cpp\b|\.cc\b|\.c\b|\.h\b|\.swift\b|\.kt\b|\.css\b|\.html\b|\.vue\b|\.ya?ml\b|\.json\b|\.sql\b|dockerfile|makefile|skill\.md)'
FEATURE = re.search(r'"(write|edit|str_replace|create|multiedit)".{0,600}' + _CODE, blob)
# Trivial/content work to exclude (resumes, cover letters, plain docs) — NOT code/skills.
TRIVIAL_ONLY = bool(re.search(r'resume|cover letter|\.docx', blob)) and not re.search(_CODE, blob)
# Phase-1 regression gate: editing the team's OWN self-improvement surface
# (a role prompt or the harness) must be re-checked by the eval/regression suite.
# roles/*.md isn't caught by FEATURE above (not skill.md/code), so this also
# closes that coverage gap.
_role_match = re.search(
    r'"(write|edit|str_replace|multiedit)"[^}]{0,800}(roles/[a-z0-9_]+\.md|harness/[a-z0-9_]+\.py)',
    blob)
ROLE_OR_HARNESS_EDIT = bool(_role_match)

# Verification signals — STRUCTURAL only.
SUITE_GREEN = (
    any(tu.get("name", "").lower() in ("bash", "shell") and "run_evals.py" in _tu_input(tu)
        for tu in _TOOL_USES)
    and any(re.search(r'suite:\s*green|"green":\s*true', _tr_text(tr))
            for tr in _TOOL_RESULTS))
# hguard6d spec: SUITE_GREEN alone does NOT prove role-content (judge-graded)
# cases actually ran — `python3 run_evals.py` with no --judge flag parks every
# `requires: "judge"` case (all role-behavior cases) as bucket "pending", which
# run_suite()'s green computation ignores, so a plain (non-`--judge`) run
# still prints its green suite verdict even when every judge case never ran.
# _rh_judge_suite_green is the stricter proxy:
# SUITE_GREEN AND the SAME Bash/Shell tool_use's own input dict (not the
# whole-turn blob) shows a run_evals.py invocation adjacent to a --judge
# flag. This is a proxy only (it does not confirm the judge cases
# individually resolved non-pending, nor that --judge pointed at a real
# adapter) — accepted residual per spec, closing that fully is future work.
#
# ROUND 3 fix (post-build Verifier finding 1, AC1c): this check MUST be
# scoped to the same single tool_use's own `_tu_input(tu)` that already
# satisfies SUITE_GREEN's run_evals.py-in-command check — mirroring
# SUITE_GREEN's own per-tool_use loop above — not a regex over the whole
# turn blob. A whole-blob regex would let a roles/*.md Edit's prose content
# (e.g. documentation that merely mentions "run_evals.py --judge") satisfy
# this detector even when the actual Bash invocation that produced the
# green suite verdict was plain (no --judge). The --judge flag must appear
# in the SAME Bash tool_use's own input as the run_evals.py invocation.
_rh_judge_suite_green = bool(SUITE_GREEN and any(
    tu.get("name", "").lower() in ("bash", "shell")
    and "run_evals.py" in _tu_input(tu)
    and "--judge" in _tu_input(tu)
    for tu in _TOOL_USES))
VERIFIER = any(
    tu.get("name", "").lower() in ("task", "agent", "subagent", "workflow")
    and not _tu_id_is_blocked(tu)
    and re.search(r'independent verifier|verifier\.md|verify|plan-?check verifier|verifier plan-?check', _tu_dispatch_text(tu))
    for tu in _TOOL_USES)

# ── AC-RH1 / AC-RH2 structural exemptions (residual_holes_spec.md; fix_plan
# June H-GUARD-3 /tmp FP, H-GUARD-3b settings FP, RH-1c mention-vs-edit,
# H-GH2 sub-hole). The blob regexes above still DETECT; the exemptions below
# only SUPPRESS a blob-level fire when the turn's ACTUAL writes — collected
# structurally from Write/Edit/MultiEdit tool_use inputs, realpath-resolved
# BEFORE classification so symlink evasion (tmp -> repo, runs/*.md -> roles/)
# never qualifies — are provably out of the gate's scope. A blob fire with
# ZERO structural writes keeps today's blocking behavior (AC-RH1d: over-fire
# is the safe direction).
_RH_WRITE_TOOLS = {"write", "edit", "multiedit"}

# Pinned code-extension set, mirroring pre_tool_use_oga_guard.py's CODE_EXT
# (basename match). The blob _CODE directory prefixes (skills?/, hooks?/) do
# NOT define structural collection — only real file extensions do.
_RH_CODE_EXT = re.compile(
    r'\.(py|ts|tsx|js|jsx|go|rs|java|rb|sh|php|cpp|cc|c|h|swift|kt|css|vue|yaml|yml|json|sql)$'
    r'|dockerfile$|makefile$|skill\.md$',
    re.I
)


def _rh_structural_writes():
    """(tool_name_lower, realpath, input_dict) per Write/Edit/MultiEdit call."""
    out = []
    _result_ids = {
        (tr.get("tool_use_id") or tr.get("id"))
        for tr in _TOOL_RESULTS
        if (tr.get("tool_use_id") or tr.get("id"))
    }
    for _tu in _TOOL_USES:
        _nm = _tu.get("name", "").lower()
        if _nm not in _RH_WRITE_TOOLS:
            continue
        _tid = _tu.get("id") or _tu.get("tool_use_id")
        if _tid in _blocked_tool_use_ids:
            continue
        if _tid and _tid not in _result_ids:
            _tin = _tu.get("input") if isinstance(_tu.get("input"), dict) else {}
            if _nm == "write":
                continue
            if _nm == "edit" and _tin.get("old_string") == _tin.get("new_string"):
                continue
            if _nm == "multiedit":
                _edits = _tin.get("edits") or []
                if all(isinstance(_e, dict) and _e.get("old_string") == _e.get("new_string")
                       for _e in _edits):
                    continue
        _in = _tu.get("input")
        if not isinstance(_in, dict):
            continue
        _fp = _in.get("file_path") or _in.get("path") or ""
        if not isinstance(_fp, str) or not _fp:
            continue
        out.append((_nm, os.path.realpath(os.path.expanduser(_fp)), _in))
    return out


def _rh_under(real, root):
    root = root.rstrip(os.sep)
    return real == root or real.startswith(root + os.sep)


def _rh_temp_roots():
    # Exempt temp roots are realpath'd JUST LIKE the write paths: on macOS,
    # tempfile.gettempdir()/$TMPDIR live under /var/folders/, which realpaths
    # to /private/var/folders/ — without resolving the ROOTS too, no
    # realpath'd write could ever prefix-match them.
    roots = set()
    for _c in (tempfile.gettempdir(), "/tmp", "/private/tmp",
               os.environ.get("TMPDIR"), "/var/folders"):
        if _c:
            roots.add(os.path.realpath(_c))
    return roots


# AC-RH1b: EXACTLY these two basenames under ~/.claude/ — never the whole
# dir (~/.claude/skills/**/SKILL.md still gates).
_RH_SETTINGS_FILES = {
    os.path.realpath(os.path.expanduser("~/.claude/settings.json")),
    os.path.realpath(os.path.expanduser("~/.claude/settings.local.json")),
}

_rh_writes = _rh_structural_writes()
_rh_raw_write_tool_seen = any(
    (_tu.get("name", "").lower() in _RH_WRITE_TOOLS)
    for _tu in _TOOL_USES
)
_rh_no_successful_structural_writes = _rh_raw_write_tool_seen and not _rh_writes

# ── Part C (Evidence-Gate Phase 4, CLOSURE_VALIDATION gate) ────────────────
# spec: this build's own spec, "Part C -- Oga's own direct-edit detection".
# Detects a CLOSED fix_plan.md heading
# whose closure-relevant portion (heading line or Proof: span -- NOT
# ordinary body prose, per theme 2's anti-over-fire fix) OGA'S OWN turn
# (not a sub-agent's -- that is Part B/D/E's job) genuinely touched, then
# validates it via fixplan_closure_lint.check_single_heading(advisory=True).
#
# Placement (spec's own explicit instruction): immediately after
# `_rh_writes = _rh_structural_writes()` above (reused here, NOT
# recomputed -- avoids a second _rh_structural_writes() call / re-deriving
# realpath/tool-type filtering), strictly BEFORE the ROLE_OR_HARNESS_EDIT
# gate below. Target resolution is independent, __file__-relative ONLY
# (theme 1's fix -- NO _rc_target/_msg_mod dependency: fix_plan.md is
# always THIS repo's own single, fixed tracking file, one level up from
# hooks/, matching fixplan_closure_lint.py's own _default_path()
# resolution) -- this avoids the round-1 NameError trap where a placement
# satisfying one dependency's availability broke the other's.
#
# Theme 4 (advisory-vs-blocking split): a heading with ZERO blocking
# `messages` never blocks by itself, even if it has advisory `warnings`
# (STALE/dirty-worktree) -- those are still surfaced as non-blocking
# diagnostics on stderr so they are never silently swallowed (AC13). A
# heading WITH >=1 blocking message appends ONE ("CLOSURE_VALIDATION", ...)
# violation whose text includes both the blocking messages and any advisory
# warnings, clearly labeled.
#
# Wrapped in the SAME try/except-SystemExit-reraise/except-Exception-
# fail-open pattern every other gate in this file uses (AC19).
try:
    import sys as _pc_sys, os as _pc_os
    _pc_sys.path.insert(0, _pc_os.path.dirname(_pc_os.path.abspath(__file__)))
    from closure_touch_scan import find_touched_closed_headings as _pc_find_touched

    _pc_harness_dir = _pc_os.path.normpath(_pc_os.path.join(
        _pc_os.path.dirname(_pc_os.path.abspath(__file__)),
        "..", "loop-team", "harness"))
    _pc_sys.path.insert(0, _pc_harness_dir)
    from fixplan_closure_lint import check_single_heading as _pc_check_heading

    _pc_target_path = _pc_os.path.join(
        _pc_os.path.dirname(_pc_os.path.abspath(__file__)), "..", "fix_plan.md")

    # Adapt the ALREADY-COMPUTED _rh_writes 3-tuple shape
    # (tool_name_lower, realpath, input_dict) into the raw tool_use dict
    # shape find_touched_closed_headings documents as its public contract
    # (spec's own recommended wiring for Part C).
    _pc_tool_uses = [
        {"type": "tool_use", "name": _nm, "input": _in}
        for _nm, _real, _in in _rh_writes
    ]
    _pc_touched_headings = _pc_find_touched(_pc_tool_uses, _pc_target_path)

    if _pc_touched_headings:
        with open(_pc_target_path, encoding="utf-8") as _pc_fh:
            _pc_content = _pc_fh.read()

        for _pc_heading in _pc_touched_headings:
            _pc_result = _pc_check_heading(
                _pc_content, _pc_heading, _pc_target_path, advisory=True)
            _pc_messages = _pc_result.get("messages") or []
            _pc_warnings = _pc_result.get("warnings") or []
            if not _pc_messages:
                # Zero blocking messages -- advisory warnings never by
                # themselves cause a block for this heading (theme 4), but
                # are still surfaced as non-blocking diagnostics so they are
                # never silently swallowed (AC13).
                for _pc_w in _pc_warnings:
                    sys.stderr.write(
                        "[LOOP STOP-GUARD] Part C WARNING (advisory, not "
                        "blocking) for CLOSED heading %r: %s\n"
                        % (_pc_heading, _pc_w))
                continue
            _pc_lines = list(_pc_messages)
            for _pc_w in _pc_warnings:
                _pc_lines.append("WARNING (advisory, not blocking): %s" % _pc_w)
            if _log_gate:
                _log_gate("CLOSURE_VALIDATION", True, _pc_heading[:200], 2)
            _VIOLATIONS.append(("CLOSURE_VALIDATION", (
                "[LOOP STOP-GUARD] CLOSURE_VALIDATION Part C: this turn "
                "touched the closure-relevant portion (heading line or "
                "Proof: span) of CLOSED heading %r in fix_plan.md, and it "
                "still has unresolved issue(s): %s"
            ) % (_pc_heading, "; ".join(_pc_lines))))
except SystemExit:
    raise
except Exception as _pc_e:
    sys.stderr.write(
        "[closure-validation-gate] disabled by error (fail-open): %r\n" % (_pc_e,))

# ── v1 anti-false-status gate: broader than the older CLOSED-heading proof
# lint above. It audits touched high-risk status claims (DONE/READY/GREEN/
# tests-passed/etc.) plus their attached evidence spans, and uses successful
# tool-result pairing so denied/errored/missing-result writes cannot make an
# old bad claim look newly touched.
try:
    import sys as _sca_sys, os as _sca_os
    _sca_harness_dir = _sca_os.path.normpath(_sca_os.path.join(
        _sca_os.path.dirname(_sca_os.path.abspath(__file__)),
        "..", "loop-team", "harness"))
    _sca_sys.path.insert(0, _sca_harness_dir)
    from status_claim_audit import (
        audit_fix_plan_content as _sca_audit_content,
        touched_ranges_for_tool_uses as _sca_touched_ranges,
    )

    _sca_target_path = _sca_os.path.join(
        _sca_os.path.dirname(_sca_os.path.abspath(__file__)), "..", "fix_plan.md")
    with open(_sca_target_path, encoding="utf-8") as _sca_f:
        _sca_content = _sca_f.read()
    _sca_ranges = _sca_touched_ranges(
        _TOOL_USES, _TOOL_RESULTS, _sca_target_path, content=_sca_content)
    if _sca_ranges:
        _sca_result = _sca_audit_content(
            _sca_content, touched_ranges=_sca_ranges,
            now=None, full_sweep=False)
        _sca_findings = [
            _f for _f in (_sca_result.get("findings") or [])
            if _f.get("blocking")
        ]
        if _sca_findings:
            _sca_parts = []
            for _f in _sca_findings:
                _sca_parts.append("%r claim %r: %s" % (
                    _f.get("heading"), _f.get("claim"), _f.get("classifier")))
            if _log_gate:
                _log_gate("CLOSURE_VALIDATION", True, "; ".join(_sca_parts)[:200], 2)
            _VIOLATIONS.append(("CLOSURE_VALIDATION", (
                "[LOOP STOP-GUARD] CLOSURE_VALIDATION v1 status-claim "
                "audit: this turn touched a high-risk fix_plan.md status "
                "claim or attached evidence span without sufficient "
                "mechanical proof/evidence: %s"
            ) % ("; ".join(_sca_parts),)))
except SystemExit:
    raise
except Exception as _sca_e:
    sys.stderr.write(
        "[status-claim-audit-gate] disabled by error (fail-open): %r\n" % (_sca_e,))

_rh_code_writes = [_w for _w in _rh_writes
                   if _RH_CODE_EXT.search(os.path.basename(_w[1]))]


# AC-0 (hguard6_spec.md): root-agnostic surface classifiers mirroring the
# ROLE_OR_HARNESS blob regex (roles/[a-z0-9_]+\.md / harness/[a-z0-9_]+\.py).
# Path-SEGMENT checks (os.sep-aware), NOT basename substrings and NOT
# repo-root anchored — so /x/loop-team/roles/verifier.md classifies as a role
# file regardless of where the clone lives.
def _rh_is_role_md(real):
    _low = real.lower()
    return (os.sep + "roles" + os.sep) in _low and _low.endswith(".md")


def _rh_is_harness_py(real):
    _low = real.lower()
    return (os.sep + "harness" + os.sep) in _low and _low.endswith(".py")


# AC-3 (H-GUARD-7, NARROWED v3 to gating-inode match): os.path.realpath
# resolves symlinks but NOT hardlinks, so a runs/*.md hard-linked to a gating
# roles/*.md would classify as benign. The v2 signal (bare st_nlink > 1) fired
# on ANY multi-linked inode, so an innocently-hardlinked plain doc (a cp -l
# backup, a dedup tool, an editor backup — NEITHER name a gating file) wrongly
# BLOCKED a close-out. Live-confirmed over-fire. NARROWED here to: a write's
# inode is ALSO reachable as a real gating surface. TRUE iff ANY structural
# write's realpath is an existing file, has st_nlink > 1, AND whose
# (st_dev, st_ino) identity matches that of a real roles/*.md or harness/*.py
# under <repo>/loop-team/. A nonexistent path (or stat error) is NOT
# hardlinked-to-gating. Wired (negated) into every exemption predicate below so
# a genuinely-gating hardlinked write disqualifies the exemption and the gate
# BLOCKS (safe direction); an innocent hardlink no longer does.
_rh_gating_base = os.path.realpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "loop-team"))


def _rh_gating_inodes():
    """Set of (st_dev, st_ino) tuples for every real roles/*.md and
    harness/*.py under <repo>/loop-team/. Every listdir/stat is wrapped in
    try/except — a missing dir/file contributes nothing (clone-safe)."""
    inodes = set()
    for _sub, _ext in (("roles", ".md"), ("harness", ".py")):
        _dir = os.path.join(_rh_gating_base, _sub)
        try:
            _names = os.listdir(_dir)
        except OSError:
            continue
        for _n in _names:
            if not _n.lower().endswith(_ext):
                continue
            try:
                _st = os.stat(os.path.join(_dir, _n))
            except OSError:
                continue
            inodes.add((_st.st_dev, _st.st_ino))
    return inodes


def _rh_multilinked_writes():
    """Structural writes whose realpath is an existing file with st_nlink > 1,
    as (realpath, (st_dev, st_ino)). A stat error is treated as not-hardlinked."""
    out = []
    for _nm, _real, _in in _rh_writes:
        try:
            _st = os.stat(_real)
        except OSError:
            continue
        if _st.st_nlink > 1:
            out.append((_real, (_st.st_dev, _st.st_ino)))
    return out


# PERFORMANCE: only scan the gating dirs if at least one structural write is
# multi-linked — the no-hardlink common case does ZERO directory scanning.
_rh_multilinked = _rh_multilinked_writes()
if _rh_multilinked:
    _rh_gating_inode_set = _rh_gating_inodes()
    _rh_hardlinked_to_gating = any(
        _ident in _rh_gating_inode_set for _real, _ident in _rh_multilinked)
else:
    _rh_hardlinked_to_gating = False

# AC-RH1a+b: >=1 structural code write, and ALL of them under a temp root or
# exactly one of the two settings files -> FEATURE suppressed. A mixed turn
# (one temp write + one repo write) still blocks.
_rh_tmp_roots = _rh_temp_roots()
_rh_exempt_paths_only = bool(_rh_code_writes) and not _rh_hardlinked_to_gating and all(
    _real in _RH_SETTINGS_FILES
    or any(_rh_under(_real, _root) for _root in _rh_tmp_roots)
    for _nm, _real, _in in _rh_code_writes)

# AC-RH1c (RH-1c mention-vs-edit): the turn's structural writes (ANY
# extension) are ALL .md files under <repo>/runs/ (repo = this hooks dir's
# parent — same derivation as the hygiene gate's role-file base) -> the turn
# is plan production; text ABOUT code is not code. Suppresses BOTH the
# FEATURE and ROLE_OR_HARNESS gates. A single non-runs/ or non-.md
# structural write disqualifies.
_rh_runs_root = os.path.realpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "runs"))
_rh_plan_production = bool(_rh_writes) and not _rh_hardlinked_to_gating and all(
    _real.lower().endswith(".md") and _rh_under(_real, _rh_runs_root)
    for _nm, _real, _in in _rh_writes)

# AC-RH2 (fix_plan H-GH2 sub-hole) — RULING: for agent-executed artifacts,
# prose IS logic; the general doc-vs-logic heuristic stays REJECTED, and
# content edits to SKILL.md legitimately gate. ONE narrow, capped exemption:
# the turn contains EXACTLY ONE structural code-matching edit call, that call
# is an Edit (not Write/MultiEdit) on a .md file, old_string/new_string have
# equal line counts, and SequenceMatcher ratio >= 0.9 (typo scale) -> FEATURE
# suppressed. ACCEPTED COLLATERAL: a single semantic-token flip (e.g. `>=`
# -> `<=`) inside one .md can slip this gate — acceptable because Bash writes
# already bypass the gate entirely, so the marginal evasion surface is ~zero.
# N typo-scale edits composing a rewrite do NOT qualify (the one-call cap).
_rh_typo_exempt = False
if len(_rh_code_writes) == 1 and not _rh_hardlinked_to_gating:
    _rh_nm, _rh_real, _rh_in = _rh_code_writes[0]
    if _rh_nm == "edit" and _rh_real.lower().endswith(".md"):
        _rh_old = _rh_in.get("old_string")
        _rh_new = _rh_in.get("new_string")
        if (isinstance(_rh_old, str) and isinstance(_rh_new, str)
                and len(_rh_old.splitlines()) == len(_rh_new.splitlines())
                and difflib.SequenceMatcher(None, _rh_old, _rh_new).ratio() >= 0.9):
            _rh_typo_exempt = True

# AC-1 (H-GUARD-6): doc-only suppression. A loop close-out that edits ONLY
# non-gating .md docs (fix_plan.md, README.md, a memory .md) — whose text
# necessarily NAMES the .py/roles files just verified in a PRIOR turn — must
# not fire either gate. TRUE iff >=1 structural write AND every structural
# write is a .md that is NEITHER a "gating .md" (a SKILL.md via _RH_CODE_EXT
# basename, OR a /roles/-segment .md via _rh_is_role_md) NOR hardlink-
# disqualified (AC-3). Subsumes _rh_plan_production (a runs/*.md is .md, not
# SKILL.md, not under /roles/) — additive; _rh_plan_production stays in the
# gate conditions for stability.
_rh_doc_only = bool(_rh_writes) and not _rh_hardlinked_to_gating and all(
    _real.lower().endswith(".md")
    and not _RH_CODE_EXT.search(os.path.basename(_real))
    and not _rh_is_role_md(_real)
    for _nm, _real, _in in _rh_writes)

# AC-2 (exemption asymmetry, tightened): a REAL gating surface written this
# turn — any structural write that is a /roles/ .md or a /harness/ .py. Used
# only to keep the tmp/settings exemption from letting a genuine role/harness
# edit escape the ROLE gate.
_rh_has_gating_role_write = any(
    _rh_is_role_md(_real) or _rh_is_harness_py(_real)
    for _nm, _real, _in in _rh_writes)

# hguard6d (H-GUARD-6 sharpened sub-case (d)): a turn whose ONLY structural
# write is roles/*.md prose (even prose that happens to NAME a .py path, e.g.
# "harness/verify.py") trips FEATURE via the blob-level _CODE regex even
# though ROLE_OR_HARNESS_EDIT is the correct, sufficient check for pure-prose
# role edits — demanding a SECOND, independent Verifier re-read the same prose
# is pure loop friction. Narrow, capped exemption: suppress FEATURE iff EVERY
# structural write this turn is a roles/*.md file (_rh_is_role_md) AND the
# ROLE_OR_HARNESS_EDIT condition for this turn did not block (either it's
# false, or it's true and satisfied by the STRICTER _rh_judge_suite_green —
# NOT plain SUITE_GREEN, per HGUARD6D-01) AND the write is not hardlink-
# disqualified, exactly like every other exemption. Does NOT extend to
# harness/*.py (real code, not prose) — a turn containing any harness/*.py
# write, or any non-roles/*.md write, never qualifies.
_rh_role_md_feature_exempt = bool(_rh_writes) and not _rh_hardlinked_to_gating and all(
    _rh_is_role_md(_real) for _nm, _real, _in in _rh_writes
) and (not ROLE_OR_HARNESS_EDIT or _rh_judge_suite_green)

# A gating-hardlinked structural write (AC-3, H-GUARD-7, NARROWED v3) arms the
# ROLE gate directly: realpath cannot see the hardlink, so the blob never names
# the linked gating file — but a (st_dev, st_ino) match against a real
# roles/*.md or harness/*.py proves a second name into a gating surface exists.
# (The v2 mechanism — arming ROLE — was correct; only the SIGNAL narrowed from
# bare st_nlink>1, which over-fired on innocent hardlinks, to the gating-inode
# match.) With every exemption already disqualified by
# `not _rh_hardlinked_to_gating`, arming here makes the turn BLOCK (safe
# direction) instead of silently passing.
#
# AC7 (round 3, documents post-build Verifier finding 2): this gate
# deliberately still checks plain SUITE_GREEN here, NOT the stricter
# _rh_judge_suite_green — by design, this block is unchanged from before the
# hguard6d exemption work. That means AC1b/AC1c's exit-2 guarantee (a
# roles/*.md-only turn with a --judge-less plain-green run must still block)
# does NOT come from this gate refusing to fire. On a plain-green run this
# `if` is FALSE (SUITE_GREEN is true) and does not block by itself; the
# actual exit 2 in AC1b/AC1c comes from the FEATURE gate below firing
# unsuppressed, because `_rh_role_md_feature_exempt`'s
# `(not ROLE_OR_HARNESS_EDIT or _rh_judge_suite_green)` clause evaluates
# False (ROLE_OR_HARNESS_EDIT is True and _rh_judge_suite_green is False),
# so the FEATURE exemption does not apply — and FEATURE's own blob `_CODE`
# regex still matches (the prose names a .py/skills//hooks/-style path
# token). In other words, AC1b/AC1c currently pass as a side effect of
# FEATURE's blob regex ALSO firing on these fixtures, not as a standalone
# guarantee from this gate. This is accepted as a known, disclosed shape for
# THIS build (do not rearchitect ROLE_OR_HARNESS_EDIT's own gate to check
# _rh_judge_suite_green) — but it means a FUTURE narrowing of FEATURE's
# _CODE regex (e.g. to require a stronger path match) could silently make a
# roles/*.md edit whose prose contains no matching path token sail through
# on plain SUITE_GREEN alone, with no gate catching it. Any change to
# FEATURE's _CODE regex must re-run AC1b/AC1c (RoleMdFeatureExemptionHGuard6d)
# to confirm this guarantee still holds.
if ((ROLE_OR_HARNESS_EDIT or _rh_hardlinked_to_gating) and not SUITE_GREEN
        and not _rh_plan_production
        and not _rh_doc_only
        and not (_rh_exempt_paths_only and not _rh_has_gating_role_write)):
    _role_evidence = _role_match.group(0)[:200] if _role_match else ""
    if _log_gate: _log_gate("ROLE_OR_HARNESS_EDIT", True, _role_evidence, 2)
    _VIOLATIONS.append(("ROLE_OR_HARNESS_EDIT",
        "[LOOP STOP-GUARD] You edited a loop-team role (roles/*.md) or the harness "
        "(harness/*.py) this turn, but the eval/regression suite is not green this turn. "
        "Phase-1 rule: a change to the team's own gate surface must be re-checked by the "
        "suite, which freezes every past gate-hole as a frozen case. Run "
        "`python3 loop-team/evals/run_evals.py` and confirm it prints `SUITE:" + " GREEN` "
        "(a RED suite means you regressed a lesson — fix it first). Then finish."
        + " Matched: %r" % (_role_evidence,)
    ))

if (FEATURE and not TRIVIAL_ONLY and not VERIFIER
        and not (_rh_exempt_paths_only or _rh_plan_production
                 or _rh_typo_exempt or _rh_doc_only
                 or _rh_role_md_feature_exempt
                 or _rh_no_successful_structural_writes)):
    _feature_evidence = FEATURE.group(0)[:200] if FEATURE else ""
    if _log_gate: _log_gate("FEATURE", True, _feature_evidence, 2)
    _VIOLATIONS.append(("FEATURE",
        "[LOOP STOP-GUARD] You edited a feature this turn but did not run an INDEPENDENT verifier "
        "sub-agent. The loop is not done until an independent verifier re-tests the change and confirms "
        "PASS (writer self-testing does not count). Use this project's loop kit if it has one "
        "(loop-team/roles/verifier.md; plus private RUN/VERIFIER rubrics if present). Spawn the verifier "
        "sub-agent now, fix from its findings, then finish."
        + " Matched: %r" % (_feature_evidence,)
    ))

# Gate: plan-check Verifier must precede Coder in the same turn.
#
# H-GUARD-1 fix (2026-06-24): the original code checked Coder FIRST (if/elif),
# which caused a false positive when a plan-check Verifier dispatch had "Coder for"
# prose in its prompt body (e.g. describing dispatch format). The Coder pattern
# matched the Verifier's prompt before the elif ever reached the Verifier pattern,
# so _seen_verifier_pre stayed False and the gate fired incorrectly.
#
# Fix — two parts:
# 1. Expand _VERIFIER_DETECT to match description-level "plan-check verifier" /
#    "verifier plan-check" patterns so Oga doesn't need to embed the exact phrase
#    "independent verifier" in every Verifier prompt.
# 2. Check Verifier FIRST in the if/elif. The tight patterns in _VERIFIER_DETECT
#    (no bare "verify") mean a real Coder prompt won't accidentally fire the
#    Verifier branch, so Bug-1 (the original reason for Coder-first) is not
#    reintroduced. Verified: coder.md does not contain any _VERIFIER_DETECT pattern.
_CODER_DETECT = re.compile(r'role:\s*coder\b|\bcoder for\b|roles/coder')
# _VERIFIER_DETECT is imported from verifier_hygiene_scan (see top of file,
# H-PRETOOLUSE-VERIFIER-HYGIENE-1 Part 2) -- same name at every call site
# below, so no other line in this file needs to change.
# AC2 (plan_check_spec.md, H-LT7a): order-insensitive within-turn check. A
# violation exists iff >=1 _CODER_DETECT dispatch is present AND zero
# _VERIFIER_DETECT dispatches are present anywhere in the turn — regardless
# of which comes first in the transcript. This replaces the prior ordered
# if/elif scan (which blocked a same-turn Coder-then-Verifier pair even
# though the substance — a plan-check Verifier ran this turn — was
# satisfied).
_plan_check_violated = False
_first_coder_match_tu = None
_first_plan_check_reason = ""

for _rec_pos, _rec in enumerate(_TURN_RECORDS):
    if _rec["kind"] != "tool_use":
        continue
    _tu = _rec["part"]
    if _credit_gate_tu_id_is_blocked(_tu):
        continue
    if not _spec_credit.is_dispatch_tool(_tu):
        continue

    if _tu.get("name", "").lower() == "workflow" and _spec_credit.is_coder_dispatch(_tu):
        if _first_coder_match_tu is None:
            _first_coder_match_tu = _tu
        _plan_check_violated = True
        _first_plan_check_reason = "Workflow Coder dispatch is unsupported in v1"
        break

    if _spec_credit.is_verifier_dispatch(_tu):
        continue

    if _spec_credit.is_coder_dispatch(_tu):
        if _first_coder_match_tu is None:
            _first_coder_match_tu = _tu
        _coder_info, _coder_info_error = _spec_credit.extract_spec_info(_tu, cwd=os.getcwd())
        if _coder_info is None:
            _plan_check_violated = True
            _first_plan_check_reason = _coder_info_error or "invalid Coder spec hash contract"
            break

        _ok, _reason = _spec_credit.prior_verifier_credit(
            _TURN_RECORDS, _rec_pos, _coder_info, cwd=os.getcwd(),
            blocked_ids=_CREDIT_GATE_BLOCKED_IDS, strict_jsonl=_TRANSCRIPT_JSONL_STRICT)
        if not _ok:
            # Fall back to flag-based cross-turn credit for this session
            _l3_session_id = data.get("session_id", "") or ""
            _l3_coder_hash = _coder_info.get("hash") if _coder_info else None
            if _l3_session_id and _l3_coder_hash:
                _l3_flag_ok, _l3_flag_reason = _spec_credit.check_verifier_pass_flags(
                    _l3_session_id, _l3_coder_hash)
                if _l3_flag_ok:
                    _ok = True
                    _reason = _l3_flag_reason
            if not _ok:
                _plan_check_violated = True
                _first_plan_check_reason = _reason
                break
        continue

if _plan_check_violated:
    if _log_gate: _log_gate("PLAN_CHECK", True, "coder-before-verifier", 2)
    _coder_snippet = ""
    if _first_coder_match_tu is not None:
        _coder_in = _first_coder_match_tu.get("input")
        if isinstance(_coder_in, dict):
            _coder_desc = _coder_in.get("description")
            if isinstance(_coder_desc, str) and _coder_desc.strip():
                _coder_snippet = _coder_desc
            else:
                _coder_prompt = _coder_in.get("prompt")
                if isinstance(_coder_prompt, str):
                    _coder_snippet = _coder_prompt[:150]
                elif isinstance(_coder_in.get("script"), str):
                    _coder_snippet = _coder_in.get("script")[:150]
    _coder_snippet = _coder_snippet[:200]
    _VIOLATIONS.append(("PLAN_CHECK",
        "[LOOP STOP-GUARD] A Coder sub-agent was dispatched this turn without a preceding "
        "same-window plan-check Verifier approval for the same current spec bytes. "
        "Per orchestrator.md step 1: produce the spec, dispatch the Verifier on the "
        "spec/ACs with SPEC_SHA256, get its paired PLAN_PASS result echoing "
        "REVIEWED_SPEC_SHA256, THEN dispatch the Coder. "
        "See loop-team/orchestrator.md step 1. "
        + ("Reason: %s. " % _first_plan_check_reason if _first_plan_check_reason else "")
        + "Matched: %r" % (_coder_snippet,)
    ))

# Gate: Researcher (Mode D) dispatched this turn → Oga directly edits a feature
# file → but no plan-check Verifier ran between the Researcher and the edit.
#
# Detection uses an ordered scan of _TOOL_USES (chronological in the transcript).
# Scope is intentionally "direct Oga edits" only — Coder sub-agent edits are
# covered by the _plan_check_violated gate above.
#
# _RESEARCHER_DETECT_V2 anchors to the description JSON field to avoid false-
# matches when a Verifier or Coder prompt merely DISCUSSES "researcher mode d".
_RESEARCHER_DETECT_V2 = re.compile(
    r'"description"\s*:\s*"[a-z ]{0,15}researcher|role:\s*researcher\b'
)
_EDIT_TOOLS = {"write", "edit", "str_replace_based_edit", "multiedit"}

# AC-RH3b (residual_holes_spec.md; fix_plan Mode-D addendum): a Researcher
# DISPATCH alone never arms the gate — the CURRENT TURN must also contain
# RETURNED-EVIDENCE for that dispatch. Dual-channel scan (adapted from the
# oga-guard in-flight retirement scan — same JSONL event model):
#   (1) a tool_result part whose tool_use_id equals the dispatch's own id;
#   (2) a queue-operation event embedding a <tool-use-id> tag for it.
# Scope is deliberately the CURRENT TURN's events only (`turn`), NOT the whole
# transcript — do not widen it. KNOWN, ACCEPTED under-fire: a user-channel
# task-notification opens a NEW turn under the walk-back above, so the fully-
# async dispatch→notification shape never arms this gate. That is the safe
# direction for a gate whose purpose is killing false positives (an unarmed
# gate only means the FEATURE/plan-check gates decide instead).
_RH3_TID_RE = re.compile(r'<tool-use-id>([^<]+)</tool-use-id>')
_rh3_returned_ids = set()
for _tr in _TOOL_RESULTS:
    _rh3_tid = _tr.get("tool_use_id")
    if _rh3_tid:
        _rh3_returned_ids.add(_rh3_tid)
for _ev in turn:
    if _ev.get("type") == "queue-operation":
        _rh3_returned_ids.update(_RH3_TID_RE.findall(json.dumps(_ev)))


def _rh3_is_code_edit(tu):
    """AC-RH3a: STRUCTURAL edit classification for the Researcher gate. An
    edit tool_use participates only via its file_path (realpath-resolved with
    the same helpers as the RH1 exemptions, so symlink evasion never
    re-classifies) — content mentions of code paths never classify an edit as
    a code edit. An edit whose realpath is a .md under <repo>/runs/ is plan
    production and never sets the violation."""
    _in3 = tu.get("input")
    if not isinstance(_in3, dict):
        return False
    _fp3 = _in3.get("file_path") or _in3.get("path") or ""
    if not isinstance(_fp3, str) or not _fp3:
        return False
    _real3 = os.path.realpath(os.path.expanduser(_fp3))
    if _real3.lower().endswith(".md") and _rh_under(_real3, _rh_runs_root):
        return False
    return bool(_RH_CODE_EXT.search(os.path.basename(_real3)))


_seen_researcher2 = False
_seen_plan_verifier_after_research = False
_research_direct_edit_without_verify = False
# H-GUARD-8 item 4: the violating edit tool_use's own file path, captured at
# the exact point the violation is detected -- same extraction
# (file_path/path) as _rh3_is_code_edit's own, so this is real, concrete
# evidence rather than the fixed "researcher-then-direct-edit" label.
_research_violation_path = ""

for _tu in _TOOL_USES:
    # H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1 (spec-v5.md D.2 item 5): ONE
    # continue guard at the TRUE top of this loop, before ANY of the three
    # consumers below (_seen_researcher2's own build, the
    # _seen_plan_verifier_after_research elif, and the _EDIT_TOOLS branch).
    # A blocked, never-executed dispatch must not arm _seen_researcher2
    # itself -- not merely the downstream elif -- since _rh3_returned_ids
    # (built above with zero deny/success filtering) would otherwise still
    # contain a blocked dispatch's own tool_use_id.
    if _tu_id_is_blocked(_tu):
        continue
    _name2 = _tu.get("name", "").lower()
    _inp2 = _tu_input(_tu)
    _inp2_verifier = _tu_dispatch_text(_tu)
    if _name2 in ("task", "agent", "subagent", "workflow"):
        if _RESEARCHER_DETECT_V2.search(_inp2):
            _rh3_rid = _tu.get("id") or _tu.get("tool_use_id")
            if _rh3_rid and _rh3_rid in _rh3_returned_ids:
                _seen_researcher2 = True
        elif (_seen_researcher2
              and not _seen_plan_verifier_after_research
              and _VERIFIER_DETECT.search(_inp2_verifier)):
            _seen_plan_verifier_after_research = True
    elif (_name2 in _EDIT_TOOLS
          and _seen_researcher2
          and not _seen_plan_verifier_after_research
          and _rh3_is_code_edit(_tu)):
        _research_direct_edit_without_verify = True
        _in4 = _tu.get("input")
        if isinstance(_in4, dict):
            _fp4 = _in4.get("file_path") or _in4.get("path") or ""
            if isinstance(_fp4, str):
                _research_violation_path = _fp4
        break

if _research_direct_edit_without_verify:
    if _log_gate: _log_gate("RESEARCH_GATE", True, "researcher-then-direct-edit", 2)
    _VIOLATIONS.append(("RESEARCH_GATE",
        "[LOOP STOP-GUARD] A Researcher (Mode D) sub-agent ran this turn and Oga directly "
        "edited files from its findings — without a plan-check Verifier approving the approach "
        "first. Research findings are inputs to a plan, not a license to act. Required flow: "
        "Research → synthesize plan → plan-check Verifier (PLAN_PASS) → then Coder or edit. "
        "Produce the plan now, dispatch the plan-check Verifier, get PLAN_PASS, then proceed."
        + " Matched: %r" % (_research_violation_path[:200],)
    ))

# ── Verifier-dispatch hygiene gate (independence, made mechanical; spec AC-B5).
# A Verifier dispatch must never carry the Coder's decision-log content or a green-result
# assertion in Oga-added context. Role files themselves contain result-shaped
# phrases (verifier.md's own output-format instruction and harness-green prose), so the gate
# scans only the RESIDUE after subtracting known role/orchestrator lines.
# Markers built dynamically: reading this file must never arm anything.
#
# H-PRETOOLUSE-VERIFIER-HYGIENE-1 Part 2: the marker list, known-role-lines
# lookup, and residue-scan logic now live in verifier_hygiene_scan.py
# (imported at top of this file as _shared_hyg_known_lines/_shared_evaluate_
# hygiene) so pre_tool_use_oga_guard.py can run the IDENTICAL check before a
# dispatch fires. roles_base is derived here (the caller), same derivation
# the original inline _hyg_known_lines() used internally. _hyg_markers()
# itself is kept as a thin delegator (rather than removed outright) so this
# file still exposes the single canonical marker list under its original
# name -- TestNoLiteralMarkersInHooks::test_hyg_marker_source_still_exists
# pins that "def _hyg_markers" remains real, live source in this file, not
# just documentation, precisely so the marker-literal sweep in that same
# test class stays synced to an actual function instead of silently drifting
# if this file's own copy were ever deleted outright.
def _hyg_markers():
    return _shared_hyg_markers()


_hyg_roles_base = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "loop-team"))
if not os.path.isdir(_hyg_roles_base):
    _hyg_roles_base = os.path.expanduser("~/Claude/loop/loop-team")

_hyg_violation = None
_known = _shared_hyg_known_lines(_hyg_roles_base)
if _known is not None:
    for _tu in _TOOL_USES:
        # H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1 (spec-v5.md D.2 item 3): a
        # blocked, never-executed dispatch's own dispatch text must not be
        # scanned for a hygiene marker -- it never actually ran.
        if _tu_id_is_blocked(_tu):
            continue
        if _tu.get("name", "").lower() not in ("task", "agent", "subagent", "workflow"):
            continue
        _desc = _tu_dispatch_text(_tu)
        if not _VERIFIER_DETECT.search(_desc):
            continue
        _prompt = _tu_dispatch_prompt_text(_tu)
        _mk = _shared_evaluate_hygiene(_prompt, _known)
        if _mk:
            _hyg_violation = (_desc[:60], _mk)
            break

if _hyg_violation:
    if _log_gate: _log_gate("VERIFIER_HYGIENE", True, "%s | %s" % _hyg_violation, 2)
    _VIOLATIONS.append(("VERIFIER_HYGIENE",
        ("[LOOP STOP-GUARD] Verifier-dispatch hygiene violation: the dispatch %r carries "
         "the result-shaped phrase %r in Oga-added context. The Verifier must form its own "
         "provisional verdict BEFORE seeing the harness result, and must never see the "
         "Coder's decision-" + "log — withholding the document is not enough; do not "
         "paraphrase, summarize, or hint at either (orchestrator.md access-control rules). "
         "Re-dispatch the Verifier with the spec BY PATH and the artifact only.")
        % _hyg_violation))

# ── Verifier-dispatch ADJACENCY gate (H-LT4; additive extension of the hygiene
# gate above — fires ONLY for dispatches matching _VERIFIER_DETECT, same scope
# as the residue-scan gate, so Coder/Test-writer dispatches never see this
# check: no new over-fire surface, per fix_plan H-GH2).
#
# The hygiene gate above blocks result-shaped PROSE in the prompt. It cannot
# stop a clean prompt that merely POINTS at a path which happens to sit beside
# a status doc (HANDOFF.md, plan_check_log.md, a decision-log file, a run-log
# file, a summary) — the Verifier finds those by exploring the directory, not
# by reading the prompt. This gate makes that adjacency DETERMINISTICALLY
# blocked: for every existing path referenced in a Verifier dispatch prompt,
# inspect its real parent directory for a status-doc-shaped filename.
#
# Path extraction — THREE forms (plan-check iter 1: the project's own
# canonical dispatch idiom is a BARE RELATIVE path, e.g. "runs/x/spec.md";
# extracting only absolute/~ paths would leave the project's actual usage
# pattern uncovered):
#   (a) absolute paths starting with "/"
#   (b) "~/..." paths (tilde-expanded)
#   (c) bare relative tokens: contain "/", do not start with "/" or "~"
# All three are resolved against candidate base directories and EXISTENCE-
# GATED: a token that does not resolve to a real file/dir under any base is
# ignored (a hypothetical/example path in prose must never flag).
#
# H-PRETOOLUSE-VERIFIER-HYGIENE-1 Part 2: STATUS_DOC_DENYLIST, the token-
# extraction regex, and the extract/candidate/target-dir/status-doc/adjacency
# helpers now live in verifier_hygiene_scan.py (imported at top of this file
# as _shared_adj_read_target_dir/_shared_evaluate_adjacency) so
# pre_tool_use_oga_guard.py can run the IDENTICAL check before a dispatch
# fires. See that module for the denylist patterns' own reasoning
# (run_log*/*run_log*, summary*/run_summary* anchoring, etc. -- unchanged).
_adj_violation = None  # (offending_path, status_doc_name)
_adj_session_id = data.get("session_id", "") or ""
_adj_cwd = os.getcwd()
_adj_target_dir = _shared_adj_read_target_dir(_adj_session_id)
if _adj_target_dir:
    _adj_target_dir = os.path.expanduser(_adj_target_dir)

for _tu in _TOOL_USES:
    if _adj_violation:
        break
    # H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1 (spec-v5.md D.2 item 4): a
    # blocked, never-executed dispatch's own dispatch text must not be
    # scanned for an adjacency violation -- it never actually ran.
    if _tu_id_is_blocked(_tu):
        continue
    if _tu.get("name", "").lower() not in ("task", "agent", "subagent", "workflow"):
        continue
    _adj_desc = _tu_dispatch_text(_tu)
    if not _VERIFIER_DETECT.search(_adj_desc):
        continue
    _adj_prompt = _tu_dispatch_prompt_text(_tu)
    _adj_violation = _shared_evaluate_adjacency(_adj_prompt, _adj_cwd, _adj_target_dir)

if _adj_violation:
    _adj_path, _adj_doc = _adj_violation
    if _log_gate: _log_gate("VERIFIER_ADJACENCY", True, "%s | %s" % (_adj_path, _adj_doc), 2)
    _VIOLATIONS.append(("VERIFIER_ADJACENCY",
        ("[LOOP STOP-GUARD] Verifier-dispatch adjacency violation: the dispatch references "
         "%r, whose directory also contains the status doc %r. A hygiene-clean prompt is not "
         "enough — the Verifier can find prior verdicts/decision-" + "logs by exploring the "
         "directory. Remedy: copy the spec to an isolated specs/ dir (or a scratch path) "
         "so Verifier inputs never sit beside run-status docs, then re-dispatch.")
        % (_adj_path, _adj_doc)
    ))

# ── Run-log enforcement gate (H-RUNLOG-LOGGING-GAPS-1, items 2-3; spec v4). ──
# Nothing previously checked that a run log was actually WRITTEN before a
# post-build Verifier's own VERDICT: PASS is treated as "done" -- this gate
# closes that enforcement gap. Mirrors the VERIFIER_ADJACENCY gate's own
# per-dispatch, per-pair discipline (never a whole-turn blob scan): a
# candidate run directory is only ever collected from the SAME tool_use/
# tool_result pair that carries both the Verifier-shaped dispatch AND its own
# "verdict: pass". _tu_dispatch_text/_tu_dispatch_prompt_text already exist in
# this file (H-WORKFLOW-BLINDSPOT-1 landed first, confirmed via
# `grep -n "_tu_dispatch_text" hooks/loop_stop_guard.py` before writing this
# gate) and "workflow" is already a member of every sibling tool-name
# allowlist in this file -- so this gate is written Workflow-aware from day
# one: it both (a) uses the shared text-extraction helpers in place of a
# hand-rolled input.prompt access, and (b) includes "workflow" in its own
# dispatch-shape membership check, per the spec's "yes" branch (both halves
# are required together; using the helpers alone does not make the
# tool-NAME membership check Workflow-aware on its own).
try:
    _RUNLOG_SPEC_FILE_RE = re.compile(r'spec(_v\d+)?\.md$')
    _RUNLOG_PLAN_CHECK_RE = re.compile(
        r'plan[-_ ]?check|plan[-_ ]?check[-_ ]?verifier|verifier[-_ ]?plan[-_ ]?check',
        re.I)
    _RUNLOG_SUPPORT_MARKER_RE = re.compile(
        r'\b(?:LOOP_GATE:\s*PLAN_(?:PASS|FAIL)|PLAN_SUPPORT_JSON=|REVIEWED_SPEC_SHA256=)',
        re.I)
    _RUNLOG_POSTBUILD_RE = re.compile(
        r'\b(?:verifier\s+for|post[-_ ]?build|code[-_ ]?verify|judgment)\b',
        re.I)

    def _runlog_is_plan_check_pair(dispatch_text, prompt_text, result_text):
        _combined = "\n".join([dispatch_text or "", prompt_text or "", result_text or ""])
        return bool(
            _RUNLOG_PLAN_CHECK_RE.search(_combined)
            or _RUNLOG_SUPPORT_MARKER_RE.search(_combined)
        )

    def _runlog_is_postbuild_tool_use(tu, result_text):
        _dispatch_text = _tu_dispatch_text(tu)
        _prompt_text = _tu_dispatch_prompt_text(tu)
        if _runlog_is_plan_check_pair(_dispatch_text, _prompt_text, result_text):
            return False
        _inp = tu.get("input") or {}
        _subagent_type = str(_inp.get("subagent_type", "") or "").strip().lower()
        return _subagent_type == "verifier" or bool(_RUNLOG_POSTBUILD_RE.search(_dispatch_text))

    def _runlog_is_postbuild_codex_dispatch(dispatch):
        _agent_type = str(getattr(dispatch, "agent_type", "") or "").strip().lower()
        _prompt_text = getattr(dispatch, "prompt_text", "") or ""
        _result_text = getattr(dispatch, "result_text", "") or ""
        if _runlog_is_plan_check_pair(_prompt_text, _prompt_text, _result_text):
            return False
        return _agent_type == "verifier" or bool(_RUNLOG_POSTBUILD_RE.search(_prompt_text))

    _runlog_candidate_dirs = set()  # real, resolved RUN directories to check
    for _rl_tu in _TOOL_USES:
        if _rl_tu.get("name", "").lower() not in ("task", "agent", "subagent", "workflow"):
            continue
        _rl_tu_id = _rl_tu.get("id") or _rl_tu.get("tool_use_id")
        _rl_result_text = ""
        for _rl_tr in _TOOL_RESULTS:
            if (_rl_tr.get("tool_use_id") or _rl_tr.get("id")) == _rl_tu_id:
                _rl_result_text = _tr_text(_rl_tr)
                break
        if not re.search(r'verdict:\s*pass', _rl_result_text, re.I):
            continue
        if not _runlog_is_postbuild_tool_use(_rl_tu, _rl_result_text):
            continue
        _rl_prompt = _tu_dispatch_prompt_text(_rl_tu)
        for _rl_tok in (_adj_extract_tokens(_rl_prompt) + _adj_extract_tokens(_rl_result_text)):
            for _rl_cand in _adj_candidate_paths(_rl_tok, _adj_cwd, _adj_target_dir):
                # Require an actual spec FILE match, not a bare directory -- a
                # background/context-handoff mention of a prior run ("see
                # runs/X/ for precedent") is a directory reference; only the
                # dispatch's OWN subject is ever given as an explicit
                # spec-file path, per this project's own established
                # dispatch convention.
                if os.path.isfile(_rl_cand) and _RUNLOG_SPEC_FILE_RE.search(_rl_cand):
                    _rl_parent = os.path.dirname(_rl_cand)
                    # Two LIVE, concurrent conventions in the real corpus
                    # (v3 round-3 finding): runs/<name>/specs/spec.md (newer)
                    # AND runs/<name>/spec.md directly at run-dir root
                    # (older, still in real use) -- branch, do not hard-
                    # require the specs/ wrapper.
                    if os.path.basename(_rl_parent) == "specs":
                        _rl_run_dir = os.path.dirname(_rl_parent)
                    else:
                        _rl_run_dir = _rl_parent
                    _runlog_candidate_dirs.add(os.path.realpath(_rl_run_dir))

    # Codex parity (Deliverable A, AC-3/AC-4/AC-5): gated on the shared
    # content-shape runtime discriminator -- never on stdin field presence
    # (see codex_transcript_adapter.py's own module docstring / the spec's
    # REVISION NOTE). The Claude-Code-shaped scan above already finds
    # nothing on a genuine Codex transcript (it has no message.content[]
    # tool_use/tool_result entries at all), so this is purely additive: it
    # never suppresses or replaces the scan above, it only adds candidate
    # run directories found via the Codex-shaped extraction path. Reuses
    # the EXACT SAME token-extraction/candidate-resolution/specs-wrapper
    # logic as the Claude-Code path above -- only the SOURCE of the
    # (prompt_text, result_text) pair differs.
    if _detect_codex_runtime(tpath) == "codex":
        for _rl_d in _codex_extract_verifier_dispatches(tpath, current_turn_only=True):
            _rl_result_text = _rl_d.result_text
            if not re.search(r'verdict:\s*pass', _rl_result_text, re.I):
                continue
            if not _runlog_is_postbuild_codex_dispatch(_rl_d):
                continue
            _rl_prompt = _rl_d.prompt_text
            for _rl_tok in (_adj_extract_tokens(_rl_prompt) + _adj_extract_tokens(_rl_result_text)):
                for _rl_cand in _adj_candidate_paths(_rl_tok, _adj_cwd, _adj_target_dir):
                    if os.path.isfile(_rl_cand) and _RUNLOG_SPEC_FILE_RE.search(_rl_cand):
                        _rl_parent = os.path.dirname(_rl_cand)
                        if os.path.basename(_rl_parent) == "specs":
                            _rl_run_dir = os.path.dirname(_rl_parent)
                        else:
                            _rl_run_dir = _rl_parent
                        _runlog_candidate_dirs.add(os.path.realpath(_rl_run_dir))

    _RUNLOG_NAMES = ("run_log.md", "RUN_LOG.md", "iteration_log.md")

    def _runlog_has_real_log(dirpath):
        """True iff dirpath contains a non-empty (post-.strip()) run log
        under any of the 3 grandfathered names."""
        for _rl_name in _RUNLOG_NAMES:
            _rl_path = os.path.join(dirpath, _rl_name)
            try:
                if os.path.isfile(_rl_path):
                    with open(_rl_path, encoding="utf-8") as _rl_fh:
                        if _rl_fh.read().strip():
                            return True
            except OSError:
                continue
        return False

    _runlog_dirs_without_log = sorted(
        d for d in _runlog_candidate_dirs if not _runlog_has_real_log(d)
    )

    if _runlog_dirs_without_log:
        if _log_gate:
            _log_gate("RUNLOG_MISSING", True, ", ".join(_runlog_dirs_without_log)[:200], 2)
        _VIOLATIONS.append(("RUNLOG_MISSING", (
            "[LOOP STOP-GUARD] A post-build Verifier returned VERDICT: PASS this turn for a "
            "build referencing %s, but no non-empty run_log.md/RUN_LOG.md/iteration_log.md "
            "exists there. Per orchestrator.md step 7, write run_log.md (the brief, the spec, "
            "each iteration's diff+verdict, and the final summary) before considering this "
            "build done."
        ) % ", ".join(_runlog_dirs_without_log)))
except Exception as _rl_e:
    # Fail-open: an unexpected error anywhere in this mechanism (malformed
    # target file, permissions error, unreadable candidate) disables JUST
    # this gate -- never crashes the hook. Matches every other risk-bearing
    # gate in this file.
    sys.stderr.write(
        "[runlog-enforcement-gate] disabled by error (fail-open): %r\n" % (_rl_e,))

# ── Micro-step gates (deterministic; FAIL-OPEN on any error — the module may be
# mid-build in the very session whose Stop hook loads it; spec AC-B1). ──────────
try:
    import os as _msg_os, sys as _msg_sys
    _msg_sys.path.insert(0, _msg_os.path.dirname(_msg_os.path.abspath(__file__)))
    import micro_step_gates as _msg_mod
    _msg_blocked, _msg_text = _msg_mod.run(data, record_sigs=(not _VIOLATIONS))
    if _msg_blocked:
        if _log_gate: _log_gate("MICRO_STEP", True, _msg_text[:80], 2)
        _VIOLATIONS.append(("MICRO_STEP", _msg_text))
    # shadow slop report (never blocks; best-effort)
    try:
        import subprocess as _msg_sp
        # H-REVIEW-COMMIT-1: read the cached result of run()'s OWN internal
        # _activation() call (line ~218 inside micro_step_gates.py, invoked
        # via _msg_mod.run(data) above) instead of calling _activation()
        # again — one underlying resolution per hook firing, not two.
        _msg_act = getattr(_msg_mod, "_LAST_ACTIVATION", None)
        if _msg_act:
            _msg_sp.run([sys.executable,
                         _msg_os.path.join(_msg_os.path.dirname(
                             _msg_os.path.abspath(__file__)), "slop_gate.py"),
                         _msg_act[0], _msg_act[1]],
                        capture_output=True, timeout=60)
    except Exception:
        pass
except SystemExit:
    raise
except Exception as _msg_e:
    sys.stderr.write("[micro-step-gates] disabled by error (fail-open): %r\n" % (_msg_e,))

# Gate: raw git commit on a scope-listed file bypasses commit_diff_reread.py
#
# H-REVIEW-COMMIT-1. Timing model: this is a Stop hook, firing AFTER the
# turn's tool calls already ran — by the time this gate can fire, any raw
# `git commit` has already executed and the commit already exists in git
# history. This gate cannot prevent the commit (that needs PreToolUse, which
# is unavailable to Oga per the standing settings.json constraint); it can
# only block the STOP, forcing Oga to address the violation post-hoc: re-diff
# the actual committed content and decide whether to keep/revert/route it
# through the normal loop (see orchestrator.md's "Review-to-commit re-diff"
# section, "On a `committed: false` result" guidance — the same remedy this
# gate's block message points at).
#
# Design note (do NOT re-read `git show HEAD`): a fresh HEAD read at Stop-hook
# time races a concurrent session's own commits on the same working tree
# (the exact root cause of commit 96693f8), misses an earlier raw commit in
# the same turn if a later one doesn't touch a scope file, and has no way to
# represent "no commit resulted" or reason about --amend. Instead: extract
# the actual commit SHA(s) from each raw `git commit` Bash tool_use's OWN
# tool_result (git prints `[<branch> <sha>] <message>` on success, for a
# normal commit and for --amend alike), then git-show THAT exact SHA.
#
# H-SUBAGENT-COMMIT-GATE-1 refactor (spec.md item 1(b)/(c)): the detection
# logic itself now lives in the shared, importable
# `commit_scope_scan.find_commit_scope_violations()` function (see
# hooks/commit_scope_scan.py) so subagent_stop_gate.py can reuse it without
# duplicating ~180 lines. `_rc_target`'s resolution logic stays HERE, at its
# ORIGINAL location — it depends on `_msg_mod`/`_LAST_ACTIVATION`, which is
# only populated after the micro-step-gates block above has already run.
# Zero behavior change versus the pre-refactor inline block.
try:
    import sys as _cs_sys, os as _cs_os
    _cs_sys.path.insert(0, _cs_os.path.dirname(_cs_os.path.abspath(__file__)))
    from commit_scope_scan import find_commit_scope_violations as _find_csv

    # Item 3: resolve <target> via the module-level cache set inside
    # _activation() (never a 2nd/3rd independent _activation() call) — this
    # gate runs strictly after the micro-step-gates block above (whose own
    # run(data) call, and therefore _activation(), already ran), so
    # _LAST_ACTIVATION reflects this same hook firing's one resolution.
    _rc_act = getattr(_msg_mod, "_LAST_ACTIVATION", None) if "_msg_mod" in globals() else None
    if _rc_act:
        _rc_target = _rc_act[0]
    else:
        # Fallback: no micro-step target armed — resolve <target> as the repo
        # containing this file itself (path-string only, no file contents
        # read, so a concurrent editor of loop_stop_guard.py/micro_step_
        # gates.py cannot race this computation).
        _rc_target = os.path.realpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".."))

    # Item 4: fire when ANY extracted SHA's file list touches >=1
    # scope-listed file. Item 6 (exemption): a commit_diff_reread.py-mediated
    # commit never produces a git success line (it prints JSON to stdout),
    # so item 2 finds no SHA for it and it is simply absent here — no
    # special-case needed beyond what items 1-4 already do.
    _rc_violations = _find_csv(_TOOL_USES, _TOOL_RESULTS, _rc_target)
    if _rc_violations:
        _rc_lines = []
        for _rc_sha, _rc_hit in _rc_violations:
            _rc_lines.append("%s (touches: %s)" % (_rc_sha, ", ".join(_rc_hit)))
        if _log_gate:
            _log_gate("REVIEW_COMMIT", True, "; ".join(_rc_lines)[:200], 2)
        _VIOLATIONS.append(("REVIEW_COMMIT",
            "[LOOP STOP-GUARD] A raw `git commit` this turn touched scope-listed "
            "shared framework file(s) WITHOUT going through "
            "commit_diff_reread.py's re-diff-immediately-before-commit "
            "guarantee: " + "; ".join(_rc_lines) + ". This content was NOT "
            "re-verified against what was actually reviewed. Remedy now: run "
            "`git show <sha>` (or `git diff <sha>~1 <sha>`) for each SHA above "
            "against the ACTUAL committed bytes, and decide whether to "
            "keep/revert/route the content through the normal loop — per "
            "orchestrator.md's \"Review-to-commit re-diff\" section, \"On a "
            "`committed: false` result\" guidance (the same remedy prescribed "
            "for this incident class when caught by `check`)."
        ))

    # ── Layer 2 (SECONDARY, defense-in-depth — H-SUBAGENT-COMMIT-GATE-1 item
    # 4): directly locates and scans a dispatched sub-agent's own transcript
    # file, without relying on the flag file at all — catches the
    # async-dispatch-ordering edge case where Oga's own Stop hook could fire
    # before an async sub-agent's SubagentStop has run. Deliberately placed
    # HERE, at the SAME location as the pre-existing Oga-scoped commit gate
    # above (not moved before line ~499 the way Layer 1 is) — this logic
    # needs `_rc_target`, which is only resolved at this original location
    # (depends on `_msg_mod._LAST_ACTIVATION`, itself only populated after
    # the micro-step-gates block runs). Moving it earlier would reference
    # `_rc_target` before it exists.
    #
    # Mechanism: scan the CURRENT turn's RAW JSONL events (not the
    # _parts()-flattened _TOOL_USES/_TOOL_RESULTS lists this file's other
    # gates use) for any event whose top-level `toolUseResult` key is a dict
    # containing an `agentId` key. `toolUseResult` is a TOP-LEVEL sibling key
    # of `message` on such an event — it is NEVER reachable via the existing
    # _parts()/_TOOL_RESULTS extraction (which only walks message.content
    # list items and has no knowledge of `toolUseResult` at all).
    _l2_agent_ids = []
    for _l2_ev in turn:
        _l2_tur = _l2_ev.get("toolUseResult")
        if isinstance(_l2_tur, dict):
            _l2_aid = _l2_tur.get("agentId")
            if isinstance(_l2_aid, str) and _l2_aid and _l2_aid not in _l2_agent_ids:
                _l2_agent_ids.append(_l2_aid)

    _l2_violations_by_agent = []  # list of (agent_id, [(sha, [touched])...])
    _l2_session_id = data.get("session_id") or ""
    for _l2_aid in _l2_agent_ids:
        # path-formula (spec.md item 4, path-formula correction): project_dir
        # = os.path.dirname(<oga's own transcript_path>) (strips only the
        # trailing <session_id>.jsonl filename); <session_id> itself must be
        # inserted as an EXPLICIT path segment between project_dir and
        # subagents/ — confirmed live against this machine's own directory
        # structure.
        _l2_project_dir = os.path.dirname(tpath)
        _l2_sub_path = os.path.join(
            _l2_project_dir, _l2_session_id, "subagents",
            "agent-%s.jsonl" % _l2_aid)
        try:
            if not os.path.isfile(_l2_sub_path):
                continue
            _l2_sub_lines = open(_l2_sub_path, encoding="utf-8").read().splitlines()
        except Exception:
            continue  # fail open: unreadable/missing sub-agent transcript

        _l2_sub_events = []
        for _l2_ln in _l2_sub_lines:
            try:
                _l2_sub_events.append(json.loads(_l2_ln))
            except Exception:
                pass

        # Flat parse — a sub-agent transcript IS one turn's worth of tool
        # calls in the relevant sense; do NOT reuse the turn-boundary
        # walk-back logic (it does not apply to a flat transcript).
        _l2_sub_tool_uses = [p for p in _parts(_l2_sub_events) if p.get("type") == "tool_use"]
        _l2_sub_tool_results = [p for p in _parts(_l2_sub_events) if p.get("type") == "tool_result"]

        try:
            _l2_hits = _find_csv(_l2_sub_tool_uses, _l2_sub_tool_results, _rc_target)
        except Exception:
            _l2_hits = []
        if _l2_hits:
            _l2_violations_by_agent.append((_l2_aid, _l2_hits))

    _l2_violations_filtered = []
    for _l2_aid, _l2_hits in _l2_violations_by_agent:
        _l2_hits_new = [
            (sha, touched) for (sha, touched) in _l2_hits
            if (_l2_aid, sha) not in _l1_flagged_shas
        ]
        if _l2_hits_new:
            _l2_violations_filtered.append((_l2_aid, _l2_hits_new))

    if _l2_violations_filtered:
        _l2_lines = []
        for _l2_aid, _l2_hits in _l2_violations_filtered:
            for _l2_sha, _l2_hit in _l2_hits:
                _l2_lines.append("agent %s: %s (touches: %s)" % (
                    _l2_aid, _l2_sha, ", ".join(_l2_hit)))
        if _log_gate:
            _log_gate("REVIEW_COMMIT_LAYER2", True, "; ".join(_l2_lines)[:200], 2)
        _l2_msg = (
            "[LOOP STOP-GUARD] Layer 2 (direct transcript scan): a sub-agent's "
            "raw `git commit` this turn touched scope-listed shared framework "
            "file(s) WITHOUT going through commit_diff_reread.py's "
            "re-diff-immediately-before-commit guarantee: " + "; ".join(_l2_lines)
            + ". This content was NOT re-verified against what was actually "
            "reviewed. Remedy now: run `git show <sha>` (or `git diff <sha>~1 "
            "<sha>`) for each SHA above against the ACTUAL committed bytes, "
            "and decide whether to keep/revert/route the content through the "
            "normal loop — per orchestrator.md's \"Review-to-commit re-diff\" "
            "section, \"On a `committed: false` result\" guidance (the same "
            "remedy prescribed for this incident class when caught by `check`)."
        )
        _VIOLATIONS.append(("REVIEW_COMMIT_LAYER2", _l2_msg))
except SystemExit:
    raise
except Exception as _rc_e:
    # Item 8 (fail-open discipline, mandatory): ANY exception anywhere in
    # this gate's logic must result in ALLOW, never a crash, never an
    # accidental false block.
    sys.stderr.write("[review-commit-gate] disabled by error (fail-open): %r\n" % (_rc_e,))

if _VIOLATIONS:
    if len(_VIOLATIONS) > 1:
        sys.stderr.write(
            "[LOOP STOP-GUARD] %d violations detected this turn — ALL shown in full "
            "below, nothing masked, highest-priority gate first (%s):\n\n"
            % (len(_VIOLATIONS), _VIOLATIONS[0][0]))
        for _idx, (_name, _msg) in enumerate(_VIOLATIONS, 1):
            sys.stderr.write(
                "----- Violation %d/%d (%s) -----\n%s\n\n"
                % (_idx, len(_VIOLATIONS), _name, _msg.rstrip("\n")))
    else:
        sys.stderr.write(_VIOLATIONS[0][1])
    sys.exit(2)
else:
    if _log_gate:
        _log_gate("ALL_GATES", False, "", 0)
    sys.exit(0)
