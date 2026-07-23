#!/usr/bin/env python3
"""
pre_tool_use_oga_guard.py — PreToolUse hook that structurally prevents Oga
(the loop-team orchestrator) from writing code directly without first dispatching
a sub-agent via the Agent tool.

Fires BEFORE Write/Edit/NotebookEdit executes. Not bypassable by user interrupt
(unlike the Stop hook, which fires at turn end).

Only activates when the loop-team skill is in scope (detected from transcript).
"""
import json, sys, os, re, time

FALLBACK_CODER_DETECT = re.compile(
    r"role:\s*coder\b"
    r"|\bcoder for\b"
    r"|roles/coder"
    r"|\byou are (?:now )?the coder\b"
    r"|\bact as (?:the )?coder\b"
    r"|\bimplement\b.{0,120}\b(?:directly|using (?:the )?(?:edit|write|multiedit|apply_patch) tools?)\b"
    r"|\b(?:edit|write|multiedit|apply_patch) tools?\b.{0,120}\bimplement\b",
    re.I,
)


def _fallback_detect_coder_dispatch(dispatch_name, dispatch_input):
    """Fail-closed Coder detector for degraded import/parser paths."""
    inp = dispatch_input if isinstance(dispatch_input, dict) else {}
    tool = {"type": "tool_use", "name": dispatch_name, "input": inp}
    try:
        hook_dir = os.path.dirname(os.path.abspath(__file__))
        if hook_dir not in sys.path:
            sys.path.insert(0, hook_dir)
        import spec_bound_verifier_credit as _fallback_sb
        return bool(_fallback_sb.is_coder_dispatch(tool))
    except Exception:
        pass

    if str(inp.get("subagent_type", "") or "").strip().lower() == "coder":
        return True
    if dispatch_name == "Workflow":
        text = str(inp.get("script", "") or "")
    else:
        text = "%s\n%s" % (
            str(inp.get("description", "") or ""),
            str(inp.get("prompt", "") or ""),
        )
    return FALLBACK_CODER_DETECT.search(text) is not None


try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {}) or {}


def _dispatch_view(raw_name, raw_input):
    """Normalize Codex multi-agent dispatches into the Agent/Task shape used
    by the existing loop-team dispatch gates.

    Codex records sub-agent launches as `spawn_agent` with
    `{agent_type,message}` instead of Claude Code's Agent/Task
    `{subagent_type,description,prompt}` fields. Keep the existing gate
    implementations canonical by adapting only this hook boundary.
    """
    if raw_name == "spawn_agent" and isinstance(raw_input, dict):
        message = str(raw_input.get("message", "") or "")
        agent_type = str(raw_input.get("agent_type", "") or "")
        return "Agent", {
            "description": "",
            "prompt": message,
            "subagent_type": agent_type,
        }
    return raw_name, raw_input if isinstance(raw_input, dict) else {}


dispatch_tool_name, dispatch_tool_input = _dispatch_view(tool_name, tool_input)

# --- Auto-arm micro-step gates as a side effect of Oga's step-4 harness run ---
# Spec: loop-team/runs/2026-07-02_h-arm-1-auto-arm-gates/specs/spec.md (AC1-AC9).
# Independent, additive branch for Bash calls -- inserted BEFORE the
# WORKER_TOOLS early-exit below, since Bash is not a WORKER_TOOLS member and
# would otherwise exit immediately with no processing. Pure side-effect: never
# blocks, never modifies tool_input, never prints. Wrapped in one outer
# try/except so any exception here can never affect Bash's own execution or
# this hook's exit code (this repo's universal defensive-hook convention).
if tool_name == "Bash":
    try:
        # Activation gate: mirror micro_step_gates.py's own dynamic-marker
        # construction technique exactly (non-contiguous string literals so
        # reading this file never arms anything).
        _AA_M_OGA = "you are " + "**oga**"
        _AA_M_PLAYBOOK = "orchestrator " + "playbook"

        _aa_transcript_path = data.get("transcript_path")
        _aa_active = False
        if _aa_transcript_path and os.path.exists(_aa_transcript_path):
            _aa_blob = open(_aa_transcript_path, encoding="utf-8", errors="ignore").read().lower()
            _aa_active = (_AA_M_OGA in _aa_blob) or (_AA_M_PLAYBOOK in _aa_blob)

        if _aa_active:
            _aa_command = (data.get("tool_input", {}) or {}).get("command", "") or ""

            _aa_candidate = None

            # Primary detection: MANDATORY python prefix immediately before
            # verify.py (round-1 plan-check Finding A fix -- rejects
            # `grep verify.py file.txt`, a commit message mentioning
            # "verify.py", or `echo "...verify.py /real/repo/path..."`,
            # since none of those have a python3/python token immediately
            # preceding verify.py).
            _AA_PRIMARY_RE = re.compile(r'python3?\s+\S*verify\.py\s+(\S+)')
            _aa_m = _AA_PRIMARY_RE.search(_aa_command)
            if _aa_m:
                _aa_token = _aa_m.group(1)
                if _aa_token.startswith("-"):
                    _aa_token = None
                elif not os.path.exists(os.path.abspath(os.path.expanduser(_aa_token))):
                    _aa_token = None
                if _aa_token:
                    _aa_candidate = _aa_token

            # Secondary detection (only if primary found nothing): --testmon
            # preceded in the SAME command string by an explicit `cd <path> &&`.
            # No preceding cd -- do not guess a cwd; skip arming entirely.
            if _aa_candidate is None:
                _AA_TESTMON_RE = re.compile(r'pytest\b[^|;&]*--testmon')
                if _AA_TESTMON_RE.search(_aa_command):
                    _AA_CD_RE = re.compile(r'cd\s+(\S+)\s*&&')
                    _aa_cd_m = _AA_CD_RE.search(_aa_command)
                    if _aa_cd_m:
                        _aa_candidate = _aa_cd_m.group(1)

            if _aa_candidate:
                # Resolve absolute, then walk UP (not down) for a .git dir,
                # capped at 10 levels. No .git found within the cap -> skip.
                _aa_path = os.path.abspath(os.path.expanduser(_aa_candidate))
                _aa_target = None
                _aa_walk = _aa_path
                for _ in range(10):
                    if os.path.isdir(os.path.join(_aa_walk, ".git")):
                        _aa_target = _aa_walk
                        break
                    _aa_parent = os.path.dirname(_aa_walk)
                    if _aa_parent == _aa_walk:
                        break
                    _aa_walk = _aa_parent

                if _aa_target:
                    _aa_session_id = data.get("session_id", "") or ""
                    if _aa_session_id:
                        _aa_gate_dir = os.path.expanduser(
                            os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
                        os.makedirs(_aa_gate_dir, exist_ok=True)
                        _aa_tfile = os.path.join(_aa_gate_dir, "%s_target" % _aa_session_id)
                        _aa_existing = None
                        if os.path.isfile(_aa_tfile):
                            _aa_existing = open(_aa_tfile, encoding="utf-8").read()
                        if _aa_existing != _aa_target:
                            with open(_aa_tfile, "w", encoding="utf-8") as _aa_f:
                                _aa_f.write(_aa_target)
    except Exception:
        pass
    sys.exit(0)

# --- dispatch_check presence check (H-BLOB-DISPLAY-1, Part B), advisory-only ---
# Spec: runs/2026-07-03_h-workflow-blindspot-and-blob-display/specs/spec.md,
# "Design -- Part B". Records, per Agent/Task/Workflow dispatch, whether a
# dispatch_check JSON block (orchestrator.md's required pre-dispatch
# structure) appears in the span of turn text belonging to THIS dispatch.
# Pure logging side effect -- never emits a permissionDecision, never affects
# any other branch. Wrapped in try/except (this repo's universal defensive-
# hook convention), structurally parallel to the Bash-arming branch above.
if tool_name in ("Agent", "Task", "Workflow"):
    try:
        import sys as _dc_sys, os as _dc_os
        _dc_sys.path.insert(0, _dc_os.path.dirname(_dc_os.path.abspath(__file__)))
        from dispatch_check_presence import evaluate_presence

        _dc_transcript_path = data.get("transcript_path")
        _dc_text = ""
        if _dc_transcript_path and _dc_os.path.exists(_dc_transcript_path):
            _dc_lines = open(_dc_transcript_path, encoding="utf-8", errors="ignore").read().splitlines()
            _dc_events = []
            for _dc_ln in _dc_lines:
                try:
                    _dc_events.append(json.loads(_dc_ln))
                except Exception:
                    pass

            # Turn-boundary walk -- IDENTICAL logic to loop_stop_guard.py's own
            # (real lines 57-75 of that file): walk back to the last genuine
            # HUMAN user message, skipping user-role entries that only carry a
            # tool_result (which would otherwise cut the turn off early and
            # drop the dispatch_check text that preceded a mid-turn tool call).
            def _dc_content(e):
                m = e.get("message")
                if isinstance(m, dict) and "content" in m:
                    return m["content"]
                return e.get("content")

            def _dc_is_tool_result_turn(e):
                c = _dc_content(e)
                if isinstance(c, list):
                    return any(isinstance(p, dict) and p.get("type") == "tool_result" for p in c)
                return False

            _dc_start = 0
            for _dc_i in range(len(_dc_events) - 1, -1, -1):
                _dc_e = _dc_events[_dc_i]
                _dc_is_user = _dc_e.get("role") == "user" or _dc_e.get("type") == "user"
                if _dc_is_user and not _dc_is_tool_result_turn(_dc_e):
                    _dc_start = _dc_i
                    break
            _dc_turn = _dc_events[_dc_start:]

            # v6 (round-5 targeted re-check finding — v5's tail-only trim was
            # insufficient, see "What changed from v5 to v6" below): bound the
            # scan on BOTH ends to just the span between the IMMEDIATELY
            # PRECEDING dispatch-shaped tool_use in this turn (exclusive) and
            # THIS dispatch's own tool_use (exclusive, since it's a tool_use
            # block, not text) -- not merely "everything from turn-start up
            # to here." A turn with two dispatch-shaped tool_uses (one
            # justified, one not) needs the SECOND one's scan to exclude the
            # FIRST one's genuine dispatch_check block, or evaluate_presence
            # (which reports present=True if a block exists ANYWHERE in the
            # given text, with no per-dispatch anchoring of its own) would
            # still find the first dispatch's block and misreport it as
            # belonging to the second.
            #
            # Operates at CONTENT-BLOCK granularity, not per-event: a single
            # assistant message's content list can interleave text/tool_use
            # blocks (e.g. text, tool_use A, text, tool_use B, all one event),
            # so flatten the whole turn into one ordered (kind, value) list
            # first, preserving true document order across AND within events.
            _dc_flat = []
            for _dc_e in _dc_turn:
                _dc_c = _dc_content(_dc_e)
                if not isinstance(_dc_c, list):
                    continue
                for _dc_p in _dc_c:
                    if not isinstance(_dc_p, dict):
                        continue
                    if _dc_p.get("type") == "text":
                        _dc_flat.append(("text", _dc_p.get("text", "")))
                    elif _dc_p.get("type") == "tool_use":
                        _dc_flat.append(("tool_use", _dc_p))

            # Locate THIS dispatch's own tool_use block: the LAST flat entry
            # matching name+input (this exact call was just appended to the
            # transcript before PreToolUse fired). Count ALL matches (not
            # just find-last) -- two byte-identical Agent/Task/Workflow
            # tool_uses in the same turn are genuinely indistinguishable by
            # name+input equality alone (spec's own Residual risk / AC9
            # degenerate-case note), so more than one match must be treated
            # as an unresolvable self-match, not silently resolved to
            # whichever one happens to be last.
            _dc_tool_input = data.get("tool_input", {}) or {}
            _dc_match_positions = [
                _dc_i for _dc_i, (_dc_kind, _dc_val) in enumerate(_dc_flat)
                if _dc_kind == "tool_use" and _dc_val.get("name") == tool_name
                and _dc_val.get("input") == _dc_tool_input
            ]
            _dc_self_pos = _dc_match_positions[-1] if len(_dc_match_positions) == 1 else None

            if _dc_self_pos is None:
                # Fallback if self-match fails (e.g. two byte-identical
                # dispatches in the same message -- indistinguishable by
                # content alone): scan the whole turn, the pre-fix behavior.
                # Fail toward the old, already-accepted-imprecise behavior,
                # never toward a crash or a wrong per-dispatch attribution.
                _dc_text = " ".join(v for k, v in _dc_flat if k == "text")
            else:
                # Find the immediately PRECEDING dispatch-shaped tool_use
                # (any Agent/Task/Workflow tool_use before self, not just
                # ones matching this hook's own tool_name) -- text before
                # THAT one belongs to an earlier dispatch, not this one.
                _dc_prev_pos = -1
                for _dc_i in range(_dc_self_pos - 1, -1, -1):
                    _dc_kind, _dc_val = _dc_flat[_dc_i]
                    if _dc_kind == "tool_use" and _dc_val.get("name") in ("Agent", "Task", "Workflow"):
                        _dc_prev_pos = _dc_i
                        break
                _dc_text = " ".join(
                    v for k, v in _dc_flat[_dc_prev_pos + 1:_dc_self_pos] if k == "text"
                )

        _dc_result = evaluate_presence(_dc_text)
        _dc_gate_dir = _dc_os.environ.get("LOOP_GATE_DIR") or _dc_os.path.expanduser("~/.loop-gate")
        _dc_os.makedirs(_dc_gate_dir, exist_ok=True)
        with open(_dc_os.path.join(_dc_gate_dir, "dispatch_check_debug.jsonl"), "a", encoding="utf-8") as _dc_f:
            _dc_f.write(json.dumps({
                "ts": time.time(),
                "tool": tool_name,
                "session_id": data.get("session_id", ""),
                "present": _dc_result["present"],
                "complete": _dc_result["complete"],
                "missing_keys": _dc_result["missing_keys"],
            }) + "\n")
    except Exception:
        pass
    # Advisory only -- NEVER sys.exit here, NEVER print a hookSpecificOutput
    # deny/ask block. Fall through so this tool_name still reaches the
    # existing WORKER_TOOLS gate below (which no-ops for Agent/Task/Workflow
    # anyway, since none of them are in WORKER_TOOLS) -- this branch adds a
    # log side effect only, changing nothing about the real allow/deny logic.

# --- Repo-health classification gate v1 ---
# Structural follow-up for fix_plan.md H-REPO-GATE-CLASSIFICATION-
# MECHANICAL-1. Applies only to Agent/Task Coder dispatches. Workflow Coder
# dispatch remains unsupported by the spec-bound gate below.
if dispatch_tool_name in ("Agent", "Task"):
    try:
        import os as _rh_os, sys as _rh_sys
        _rh_sys.path.insert(0, _rh_os.path.dirname(_rh_os.path.abspath(__file__)))
        import repo_health_dispatch_gate as _rh

        _rh_ok, _rh_reason = _rh.authorize_dispatch(
            dispatch_tool_name,
            dispatch_tool_input,
            data.get("transcript_path"),
            cwd=_rh_os.getcwd(),
        )
        if not _rh_ok:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "[OGA GUARD] repo-health classification gate blocked "
                        "%s dispatch: %s"
                    ) % (tool_name, _rh_reason),
                }
            }))
            _rh_sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        try:
            if _fallback_detect_coder_dispatch(dispatch_tool_name, dispatch_tool_input):
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            "[OGA GUARD] repo-health classification gate blocked "
                            "%s dispatch: internal parser error"
                        ) % (tool_name,),
                    }
                }))
                sys.exit(0)
        except Exception:
            pass

# --- Spec-bound Verifier/Coder credit gate v1 ---
# Shared with loop_stop_guard.py so PreToolUse and Stop agree on spec refs,
# hash checking, transcript-window parsing, and paired Verifier result logic.
if dispatch_tool_name in ("Agent", "Task", "Workflow"):
    try:
        import os as _sb_os, sys as _sb_sys
        _sb_sys.path.insert(0, _sb_os.path.dirname(_sb_os.path.abspath(__file__)))
        import spec_bound_verifier_credit as _sb

        _sb_input = dispatch_tool_input
        _sb_tool = {"type": "tool_use", "name": dispatch_tool_name, "input": _sb_input}
        def _sb_deny(_reason):
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "[OGA GUARD] spec-bound Verifier/Coder credit gate blocked "
                        "%s dispatch: %s"
                    ) % (tool_name, _reason),
                }
            }))
            _sb_sys.exit(0)

        if dispatch_tool_name in ("Agent", "Task") and _sb.is_verifier_dispatch(_sb_tool):
            _sb_err = _sb.verifier_dispatch_hash_error(dispatch_tool_name, _sb_input, cwd=_sb_os.getcwd())
            if _sb_err:
                _sb_deny(_sb_err)

        if _sb.is_coder_dispatch(_sb_tool):
            if dispatch_tool_name == "Workflow":
                _sb_deny("Workflow Coder dispatch is unsupported in v1")
            _sb_ok, _sb_reason = _sb.authorize_coder_from_transcript(
                data.get("transcript_path"), dispatch_tool_name, _sb_input,
                cwd=_sb_os.getcwd(), session_id=data.get("session_id", "") or "")
            if not _sb_ok:
                _sb_deny(_sb_reason)
    except SystemExit:
        raise
    except Exception:
        # Fail closed only for spec-bound Coder dispatches where we can still
        # recognize the current payload; otherwise preserve existing hook
        # fail-open behavior for unrelated dispatches.
        try:
            if _fallback_detect_coder_dispatch(dispatch_tool_name, dispatch_tool_input):
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            "[OGA GUARD] spec-bound Verifier/Coder credit gate blocked "
                            "%s dispatch: internal parser error"
                        ) % (tool_name,),
                    }
                }))
                sys.exit(0)
        except Exception:
            pass

# --- Verifier hygiene/adjacency PreToolUse hard-deny (H-PRETOOLUSE-VERIFIER-
# HYGIENE-1, Part 3) --- Spec: runs/2026-07-03_h-pretooluse-verifier-hygiene/
# specs/spec.md. Runs the SAME hygiene-marker-residue scan and adjacency-
# path-scan loop_stop_guard.py's Stop-hook gates already contain against a
# Verifier-shaped Agent/Task/Workflow tool_use BEFORE it is allowed to fire.
# Unlike H-BLOB-DISPLAY-1's dispatch_check_presence branch above (advisory-
# only), THIS branch has real decision-making power: it can deny an
# Agent/Task dispatch outright. Placed AFTER dispatch_check_presence (round-1
# concurrency-isolation finding) so a denied dispatch still gets its
# dispatch_check_debug.jsonl entry written first -- an early sys.exit(0) on
# deny must never skip that other branch's own log side effect.
if tool_name in ("Agent", "Task", "Workflow"):
    try:
        import os as _vh_os, sys as _vh_sys
        _vh_sys.path.insert(0, _vh_os.path.dirname(_vh_os.path.abspath(__file__)))
        from verifier_hygiene_scan import VERIFIER_DETECT, hyg_known_lines, evaluate_hygiene, \
            adj_read_target_dir, evaluate_adjacency

        _vh_input = data.get("tool_input", {}) or {}
        if tool_name == "Workflow":
            _vh_desc_text = str(_vh_input.get("script", "")).lower()
            _vh_prompt_text = str(_vh_input.get("script", ""))
        else:
            # DELIBERATE DIVERGENCE from _tu_dispatch_text's real, shipped
            # fallback-to-prompt-when-empty behavior (round-1 precision-of-
            # instruction finding): _tu_dispatch_text's fallback is safe at
            # Stop-hook time because a misclassification there is advisory
            # (flags the transcript after the sub-agent already ran) -- here
            # it would be a HARD permissionDecision:deny that can block a
            # legitimate Coder/Task dispatch (a real, established pattern --
            # see VERIFIER_TASK, an empty-description fixture already in this
            # codebase's own test suite -- whenever its prompt happens to
            # discuss verifier concepts alongside a hygiene-marker phrase like
            # a scenario where the tests are reported as passing, a
            # plausible, non-contrived Coder prompt). A
            # PreToolUse HARD BLOCK must only fire on a HIGH-CONFIDENCE
            # signal fully within Oga's own control (its own description
            # text), never on a fallback/inferred one. If description is
            # empty, this branch does not classify the dispatch as Verifier
            # at all -- the Stop-hook gate (which DOES use the fallback)
            # remains the sole backstop for that narrower, already-accepted-
            # residual-risk case, exactly as it is today.
            _vh_desc_text = str(_vh_input.get("description", "")).lower()
            _vh_prompt_text = str(_vh_input.get("prompt", ""))

        if VERIFIER_DETECT.search(_vh_desc_text):
            _vh_roles_base = _vh_os.path.normpath(_vh_os.path.join(
                _vh_os.path.dirname(_vh_os.path.abspath(__file__)), "..", "loop-team"))
            if not _vh_os.path.isdir(_vh_roles_base):
                _vh_roles_base = _vh_os.path.expanduser("~/Claude/loop/loop-team")
            _vh_known = hyg_known_lines(_vh_roles_base)

            _vh_hyg_hit = evaluate_hygiene(_vh_prompt_text, _vh_known) if _vh_known is not None else None
            _vh_session_id = data.get("session_id", "") or ""
            _vh_cwd = _vh_os.getcwd()
            _vh_target_dir = adj_read_target_dir(_vh_session_id)
            if _vh_target_dir:
                _vh_target_dir = _vh_os.path.expanduser(_vh_target_dir)
            _vh_adj_hit = evaluate_adjacency(_vh_prompt_text, _vh_cwd, _vh_target_dir)

            # Workflow scope reduction (round-2 state-completeness finding --
            # read the Goal section's "Scope correction" note first): a
            # Workflow script legitimately bundles MULTIPLE sub-dispatches in
            # one call (this exact plan-check round is itself an example --
            # 4 lenses launched from one Workflow orchestration). Scanning
            # the WHOLE script for both VERIFIER_DETECT classification and
            # hygiene/adjacency residue means a script containing one
            # legitimate Verifier lens PLUS, elsewhere in that SAME script,
            # unrelated text that happens to contain a hygiene marker (e.g. a
            # different lens's own prompt mentioning that its tests are
            # reported as passing, as part of its instructions) would
            # hard-deny the ENTIRE Workflow
            # tool_use -- blocking every bundled lens/dispatch in that one
            # call, not just the implicated one. This is exactly the
            # "fallback/inferred signal" risk round 1 already established as
            # unacceptable for a hard PreToolUse deny (round 1 fixed this for
            # Agent/Task via description-only classification; Workflow has no
            # equivalent narrow field to classify against without actually
            # parsing the script's own embedded sub-dispatch structure, which
            # is out of scope for this build). For `Workflow` specifically,
            # this branch is ADVISORY-ONLY: log the violation, never deny.
            if tool_name == "Workflow":
                if _vh_hyg_hit or _vh_adj_hit:
                    try:
                        _vh_gate_dir = _vh_os.environ.get("LOOP_GATE_DIR") or _vh_os.path.expanduser("~/.loop-gate")
                        _vh_os.makedirs(_vh_gate_dir, exist_ok=True)
                        with open(_vh_os.path.join(_vh_gate_dir, "verifier_hygiene_debug.jsonl"), "a", encoding="utf-8") as _vh_f:
                            _vh_f.write(json.dumps({
                                "ts": time.time(),
                                "tool": tool_name,
                                "session_id": data.get("session_id", ""),
                                "hygiene_hit": _vh_hyg_hit,
                                "adjacency_hit": {
                                    "path": _vh_adj_hit[0],
                                    "status_doc": _vh_adj_hit[1],
                                } if _vh_adj_hit else None,
                                "blocked": False,
                            }) + "\n")
                    except Exception:
                        pass
                # Never deny for Workflow -- fall through regardless of hit.
            else:
                if _vh_hyg_hit:
                    print(json.dumps({
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                "[OGA GUARD] Verifier-dispatch hygiene violation, blocked "
                                "BEFORE dispatch: this %s carries the result-shaped phrase "
                                "%r in Oga-added context. The Verifier must form its own "
                                "provisional verdict BEFORE seeing the harness result, and "
                                "must never see the Coder's decision-" + "log -- withholding "
                                "the document is not enough; do not paraphrase, summarize, "
                                "or hint at either (orchestrator.md access-control rules). "
                                "Re-dispatch with the spec BY PATH and the artifact only."
                            ) % (tool_name, _vh_hyg_hit)
                        }
                    }))
                    _vh_sys.exit(0)
                if _vh_adj_hit:
                    _vh_path, _vh_doc = _vh_adj_hit
                    print(json.dumps({
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                "[OGA GUARD] Verifier-dispatch adjacency violation, blocked "
                                "BEFORE dispatch: this %s references %r, whose directory "
                                "also contains the status doc %r. A hygiene-clean prompt is "
                                "not enough -- the Verifier can find prior verdicts/"
                                "decision-" + "logs by exploring the directory. Remedy: copy "
                                "the spec to an isolated specs/ dir (or a scratch path) so "
                                "Verifier inputs never sit beside run-status docs, then "
                                "re-dispatch."
                            ) % (tool_name, _vh_path, _vh_doc)
                        }
                    }))
                    _vh_sys.exit(0)
    except Exception:
        pass
    # Fall through if clean or on any internal error (fail-open -- an exception
    # in this branch must never itself block a legitimate dispatch; the
    # Stop-hook gates remain the backstop either way).

WORKER_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit", "apply_patch"}
if tool_name not in WORKER_TOOLS:
    sys.exit(0)

CODE_EXT = re.compile(
    r'\.(py|ts|tsx|js|jsx|go|rs|java|rb|sh|php|cpp|cc|c|h|swift|kt|css|vue|yaml|yml|json|sql)$'
    r'|dockerfile$|makefile$|skill\.md$',
    re.I
)


def _patch_paths(raw_input):
    """Extract touched paths from Codex apply_patch payloads.

    Codex can present apply_patch as a freeform patch body rather than a
    Claude-style `{file_path: ...}` payload, so use the patch headers as the
    public path source. Unknown shapes fail open, matching this hook's
    defensive convention.
    """
    if isinstance(raw_input, str):
        text = raw_input
    elif isinstance(raw_input, dict):
        direct = raw_input.get("file_path") or raw_input.get("path")
        if direct:
            return [str(direct)]
        text = (
            raw_input.get("patch")
            or raw_input.get("input")
            or raw_input.get("cmd")
            or raw_input.get("command")
            or ""
        )
    else:
        return []
    if not isinstance(text, str):
        return []
    paths = []
    for line in text.splitlines():
        m = re.match(r"\*\*\* (?:Add|Update|Delete) File:\s+(.+?)\s*$", line)
        if m:
            paths.append(m.group(1).strip())
    return paths


def _worker_paths(raw_name, raw_input):
    if raw_name == "apply_patch":
        return _patch_paths(raw_input)
    if isinstance(raw_input, dict):
        path = raw_input.get("file_path", "") or raw_input.get("path", "")
        return [str(path)] if path else []
    return []


# Only gate code files — not docs, markdown, fixtures, env files.
tool_input = data.get("tool_input", {})
file_paths = _worker_paths(tool_name, tool_input)
code_paths = [p for p in file_paths if CODE_EXT.search(os.path.basename(p))]
if not code_paths:
    sys.exit(0)
file_path = code_paths[0]

# Read transcript
transcript_path = data.get("transcript_path")
if not transcript_path or not os.path.exists(transcript_path):
    sys.exit(0)

try:
    events = [json.loads(l) for l in open(transcript_path, encoding="utf-8").read().splitlines() if l.strip()]
except Exception:
    sys.exit(0)

# Only enforce when the loop-team orchestrator's playbook is actually loaded in
# THIS transcript (H-GUARD-SUBAGENT fix, fix_plan.md). The injected available-
# skills list mentions oga/loop-team in EVERY session -- including Coder
# sub-agents -- so those words alone must never arm the guard. Detection keys
# on orchestrator.md content instead. Markers are built dynamically so a
# session that merely READS this file (or its tests) never self-arms.
_M_OGA = "you are " + "**oga**"
_M_PLAYBOOK = "orchestrator " + "playbook"
_M_CODEX_DISPATCH = "loop-team " + "orchestrator " + "dispatch " + "constraints"
session_blob = json.dumps(events).lower()
loop_team_active = (
    (_M_OGA in session_blob)
    or (_M_PLAYBOOK in session_blob)
    or (_M_CODEX_DISPATCH in session_blob)
)
if not loop_team_active:
    sys.exit(0)


def _write_debug_row(decision, in_flight_ids):
    """Best-effort debug log (never affects the allow/deny outcome).
    AC-RH5 (residual_holes_spec.md): rows carry caller-identity evidence --
    session_id (verbatim), transcript_basename (basename ONLY; never a
    home/tmp directory path in the log), and payload_keys (sorted top-level
    stdin keys, VALUES redacted)."""
    try:
        gate_dir = os.environ.get("LOOP_GATE_DIR") or os.path.expanduser("~/.loop-gate")
        os.makedirs(gate_dir, exist_ok=True)
        with open(os.path.join(gate_dir, "oga_guard_debug.jsonl"), "a", encoding="utf-8") as dbg:
            dbg.write(json.dumps({
                "ts": time.time(),
                "tool": tool_name,
                "file": file_path,
                "decision": decision,
                "in_flight_ids": in_flight_ids,
                "session_id": data.get("session_id", ""),
                "transcript_basename": os.path.basename(transcript_path or ""),
                "payload_keys": sorted(data.keys()),
            }) + "\n")
    except Exception:
        pass


# --- Exact worker identity guard (structural PLAN_PASS evidence guard) ---
# The earlier H-LT6 allow paths were intentionally broad: any truthy
# top-level agent_id, or any unretired Agent dispatch in the transcript, could
# authorize a protected worker edit. That fixed false positives but left an
# integrity bypass: worker-B could inherit worker-A's in-flight allowance, and
# a Verifier/Researcher identity could edit implementation files. The default
# path below requires the current top-level runtime identity to resolve to the
# exact same active, same-session, unretired Coder/Test-writer dispatch record.
# The old in-flight-only behavior is retained only as an explicit, warning-
# emitting compatibility fallback behind LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1.
TOOL_USE_ID_RE = re.compile(r'<tool-use-id>([^<]+)</tool-use-id>')
AGENT_ID_RE = re.compile(r'\bagentId:\s*([^\s(]+)')
STALE_SECONDS = 60 * 60
STALE_EVENT_FALLBACK = 400
WRITE_CAPABLE_ROLES = {"coder", "test-writer", "test_writer"}


def _content(e):
    m = e.get("message")
    if isinstance(m, dict):
        return m.get("content", [])
    return e.get("content", [])


def _role(e):
    return e.get("role") or (
        e.get("message", {}).get("role", "") if isinstance(e.get("message"), dict) else ""
    )


def _timestamp(e):
    ts = e.get("timestamp")
    if ts is None and isinstance(e.get("message"), dict):
        ts = e["message"].get("timestamp")
    return ts


def _is_queue_operation(e):
    return e.get("type") == "queue-operation"


def _event_text_blob(e):
    """Flatten an event to a string for <tool-use-id> tag scanning."""
    return json.dumps(e)


def _tool_result_parts(e):
    c = _content(e)
    if not isinstance(c, list):
        return []
    return [
        p for p in c
        if isinstance(p, dict) and p.get("type") == "tool_result"
    ]


def _part_text(p):
    value = p.get("content", "")
    if isinstance(value, list):
        value = "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in value
        )
    return str(value)


def _event_session_id(e):
    if e.get("session_id"):
        return str(e.get("session_id"))
    if e.get("sessionId"):
        return str(e.get("sessionId"))
    message = e.get("message")
    if isinstance(message, dict) and message.get("session_id"):
        return str(message.get("session_id"))
    if isinstance(message, dict) and message.get("sessionId"):
        return str(message.get("sessionId"))
    return ""


def _dispatch_role(tool_input):
    if not isinstance(tool_input, dict):
        return "unknown"
    subagent_type = str(tool_input.get("subagent_type", "") or "").strip().lower()
    if subagent_type:
        return subagent_type
    text = (
        str(tool_input.get("description", "") or "")
        + "\n"
        + str(tool_input.get("prompt", "") or "")
    ).lower()
    if re.search(r"\btest[-_ ]writer\b", text):
        return "test-writer"
    if re.search(r"\bcoder\b", text):
        return "coder"
    if re.search(r"\bresearcher\b", text):
        return "researcher"
    if re.search(r"\bverifier\b", text):
        return "verifier"
    return "unknown"


# 1) Collect dispatched Agent tool_use ids, each with its dispatch index and
#    timestamp (for the staleness cap).
dispatched = {}  # tool_use_id -> active-dispatch metadata
for i, e in enumerate(events):
    c = _content(e)
    if not isinstance(c, list):
        continue
    for p in c:
        if isinstance(p, dict) and p.get("type") == "tool_use" and p.get("name") == "Agent":
            tid = p.get("id") or p.get("tool_use_id")
            if tid:
                dispatched[tid] = {
                    "dispatch_id": str(tid),
                    "index": i,
                    "timestamp": _timestamp(e),
                    "session_id": _event_session_id(e),
                    "role": _dispatch_role(p.get("input", {}) or {}),
                    "agent_id": "",
                }

# 1b) Pair launch-ack metadata back to the original dispatch. When present,
#     the runtime's agentId is the canonical worker identity; otherwise the
#     dispatch id remains the only fallback identity.
for e in events:
    for p in _tool_result_parts(e):
        tid = p.get("tool_use_id")
        if tid not in dispatched:
            continue
        match = AGENT_ID_RE.search(_part_text(p))
        if match:
            dispatched[tid]["agent_id"] = match.group(1).strip()

# 2) Scan BOTH channels (role:user events and queue-operation events) for
#    embedded <tool-use-id> tags. A tag only retires a dispatch if its id is
#    in the dispatched-Agent-id set — ids from Monitor/background-Bash
#    notifications never match an Agent id (opaque unique tokens) so they
#    cannot spoof a retirement.
retired = set()
for e in events:
    role = _role(e)
    if role != "user" and not _is_queue_operation(e):
        continue
    for tid in TOOL_USE_ID_RE.findall(_event_text_blob(e)):
        if tid in dispatched:
            retired.add(tid)

# 3) Staleness cap: a dispatch with no retirement in either channel is only
#    "in flight" if it is recent enough. Prefer event timestamps; fall back
#    to an event-count window when timestamps are absent.
now = time.time()
last_index = len(events) - 1


def _is_stale(info):
    ts = info["timestamp"]
    if ts:
        try:
            # Support both epoch numbers and ISO-8601 strings.
            if isinstance(ts, (int, float)):
                dispatch_time = float(ts)
            else:
                import datetime
                s = str(ts)
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dispatch_time = datetime.datetime.fromisoformat(s).timestamp()
            return (now - dispatch_time) > STALE_SECONDS
        except Exception:
            pass
    # Fallback: no usable timestamp -- use event-count window.
    return (last_index - info["index"]) > STALE_EVENT_FALLBACK


in_flight_ids = [
    tid for tid, info in dispatched.items()
    if tid not in retired and not _is_stale(info)
]

payload_session_id = str(data.get("session_id", "") or data.get("sessionId", "") or "")


def _same_session(info):
    return bool(payload_session_id and info.get("session_id") and info.get("session_id") == payload_session_id)


active_dispatches = [
    info for tid, info in dispatched.items()
    if tid in in_flight_ids and _same_session(info)
]


def _canonical_agent_identity(info):
    return info.get("agent_id") or info.get("dispatch_id")


def _record_key(info):
    return info.get("dispatch_id")


def _resolve_agent_id(value):
    if not value:
        return None
    matches = [
        info for info in active_dispatches
        if _canonical_agent_identity(info) == str(value)
    ]
    if len(matches) == 1:
        return matches[0]

    # Claude Code currently exposes two agent identity namespaces: the
    # human-facing launch ack (`agentId: ...`) recorded in the parent
    # transcript, and the fresh top-level `agent_id` attached to each worker
    # tool-call payload. When those differ, a real worker can still be resolved
    # safely if there is exactly one active, same-session write-capable worker;
    # additional task_id/dispatch_id fields below must still agree with it.
    write_capable = [
        info for info in active_dispatches
        if info.get("role") in WRITE_CAPABLE_ROLES
    ]
    return write_capable[0] if len(write_capable) == 1 else None


def _resolve_task_or_dispatch_id(value):
    if not value:
        return None
    value = str(value)
    matches = [
        info for info in active_dispatches
        if info.get("dispatch_id") == value or _canonical_agent_identity(info) == value
    ]
    return matches[0] if len(matches) == 1 else None


# --- Codex-side Exact worker identity guard (2026-07-16 fix) ---
# Spec: loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/
# spec.md, Section D. The Claude-Code-shaped mechanism above never
# recognizes a genuine Codex sub-agent's own dispatch: its `dispatched`
# collector only ever matches a `{"type":"tool_use","name":"Agent"}` block
# inside `message.content`, a shape no real Codex transcript produces (a
# Codex dispatch is recorded as a `spawn_agent` `function_call`
# `response_item` on the PARENT's own transcript, and a Codex sub-agent's
# own later `transcript_path` points at a SEPARATE file from where that
# dispatch was recorded -- there is nothing to usefully cross-reference in
# the CURRENT transcript). Instead, the child's own transcript
# self-certifies its own legitimacy via its FIRST `session_meta` event's
# `thread_source` field -- a value written by the Codex runtime itself,
# never derivable from conversation content, so it is not something a
# prompt-injection or role-collapse attempt could produce.
#
# Imported the SAME sibling-module, fail-open way every other gate in this
# file imports its own sibling module (repo-health, spec-bound-credit,
# verifier-hygiene gates above): a broken/missing adapter must never break
# the pre-existing Claude-Code-shaped path below -- it just falls back to
# "unknown", `_detect_runtime`'s own pre-existing behavior for every
# non-Codex transcript already.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from codex_transcript_adapter import _detect_runtime as _codex_detect_runtime
except Exception:
    def _codex_detect_runtime(_transcript_path):
        return "unknown"


def _codex_first_session_meta(events):
    """The FIRST event whose own type=="session_meta" (not literally
    events[0] -- 2+ session_meta events can appear with conflicting
    thread_source, and only the first one governs, in either direction)."""
    for e in events:
        if isinstance(e, dict) and e.get("type") == "session_meta":
            return e
    return None


def _codex_dispatch_retired_anywhere(events):
    """A real, terminal event_msg (task_complete or turn_aborted -- Codex's
    two confirmed real terminal shapes) ANYWHERE in the child transcript
    retires this dispatch. Scanned whole-file, not only the last line, so a
    transcript with content appended after its own terminal event is still
    caught."""
    for e in events:
        if not isinstance(e, dict) or e.get("type") != "event_msg":
            continue
        payload = e.get("payload")
        if isinstance(payload, dict) and payload.get("type") in ("task_complete", "turn_aborted"):
            return True
    return False


def _codex_timestamp_parseable(ts):
    """Mirrors _is_stale()'s own parse attempt (an int/float epoch, or an
    ISO-8601 "Z"-suffixed string) WITHOUT reusing its event-count fallback
    -- that fallback is an Oga-direct-call-turn-count proxy tuned for the
    Claude-Code path, and gives the wrong answer for a single, usually-short
    Codex child transcript: a missing/malformed timestamp must deny
    outright, not fall through to a small-file event-count heuristic that
    would misreport it as fresh."""
    if not ts:
        return False
    try:
        if isinstance(ts, (int, float)):
            float(ts)
        else:
            s = str(ts)
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            import datetime
            datetime.datetime.fromisoformat(s)
        return True
    except Exception:
        return False


def _classify_codex_task_name(task_name):
    """A NEW, Codex-only role classifier -- deliberately separate from
    _dispatch_role() above. Widening _dispatch_role()'s shared free-text
    regex to tolerate underscore-joined tokens would newly misclassify a
    Claude-Code Researcher/Verifier dispatch whose free-text prompt merely
    mentions a real identifier like "coder_structural_guard" in prose as
    write-capable "coder" -- exactly the vulnerability this guard exists to
    prevent. `task_name` is different: a short, structured,
    Codex-runtime-generated field drawn from a controlled snake_case
    vocabulary, never free prose that could incidentally mention an
    unrelated identifier -- so normalizing underscore/hyphen/space
    uniformly as separators is safe here in a way it is not for
    _dispatch_role()'s own free-text branch. Same keyword vocabulary/
    check-order as _dispatch_role(); a task_name containing two role
    keywords resolves to whichever is checked first -- a named, accepted
    residual, analogous to _dispatch_role()'s own existing ambiguity for
    Claude-Code free text, not solved here."""
    text = re.sub(r"[-_]+", " ", str(task_name or "")).lower()
    if re.search(r"\btest[-_ ]writer\b", text):
        return "test-writer"
    if re.search(r"\bcoder\b", text):
        return "coder"
    if re.search(r"\bresearcher\b", text):
        return "researcher"
    if re.search(r"\bverifier\b", text):
        return "verifier"
    return "unknown"


def _codex_exact_worker_identity_allows(transcript_path, events):
    """True iff `transcript_path`/`events` (the CURRENT call's own
    transcript) is a legitimately Codex-runtime-dispatched, write-capable
    sub-agent's own transcript. False covers every other case -- not
    Codex-shaped, a non-"subagent"/malformed thread_source, retired,
    stale/malformed timestamp, missing agent_path, or a non-write-capable/
    unclassifiable role -- all of which fall through to the PRE-EXISTING
    Claude-Code-shaped identity resolution below, unchanged (that path
    already denies with "missing top-level worker identity" for a genuine
    Codex payload, since Codex never sets agent_id/task_id/dispatch_id)."""
    if _codex_detect_runtime(transcript_path) != "codex":
        return False

    first_meta = _codex_first_session_meta(events)
    if first_meta is None:
        return False

    meta_payload = first_meta.get("payload")
    thread_source = meta_payload.get("thread_source") if isinstance(meta_payload, dict) else None
    if thread_source != "subagent":
        # Covers BOTH: present-but-not-"subagent" (Codex's own top-level
        # session) and malformed/absent payload or thread_source key --
        # both fall through to the same deny-then-legacy-fallback path the
        # Claude-Code no-agent_id case already uses.
        return False

    if _codex_dispatch_retired_anywhere(events):
        return False

    # Staleness: reuses _is_stale()'s own parser/STALE_SECONDS comparison
    # unmodified; _codex_timestamp_parseable() exists ONLY so a missing/
    # malformed timestamp denies directly, rather than silently falling
    # into _is_stale()'s own event-count fallback.
    ts = first_meta.get("timestamp")
    if not _codex_timestamp_parseable(ts):
        return False
    if _is_stale({"timestamp": ts, "index": 0}):
        return False

    # Guard agent_path before extracting task_name: the real, live
    # namespace=="multi_agent_v1" (OLD-shape) population satisfies
    # thread_source=="subagent" but has a literal JSON null agent_path --
    # never call the classifier on it.
    agent_path = meta_payload.get("agent_path")
    if not isinstance(agent_path, str) or not agent_path.strip():
        return False

    task_name = agent_path[len("/root/"):] if agent_path.startswith("/root/") else agent_path
    role = _classify_codex_task_name(task_name)

    # Fails closed: an "unknown" or non-write-capable role denies, mirroring
    # this file's own existing convention.
    return role in WRITE_CAPABLE_ROLES


try:
    if _codex_exact_worker_identity_allows(transcript_path, events):
        _write_debug_row("allow", ["codex-subagent-write-capable"])
        sys.exit(0)
except SystemExit:
    raise
except Exception:
    pass


identity_records = []
identity_error = None
top_agent_id = data.get("agent_id")
top_task_id = data.get("task_id")
top_dispatch_id = data.get("dispatch_id")

if top_agent_id:
    rec = _resolve_agent_id(top_agent_id)
    if rec is None:
        identity_error = "top-level agent_id does not match an active same-session worker"
    else:
        identity_records.append(("agent_id", rec))
elif top_task_id:
    rec = _resolve_task_or_dispatch_id(top_task_id)
    if rec is None:
        identity_error = "top-level task_id does not match an active same-session worker"
    else:
        identity_records.append(("task_id", rec))
elif top_dispatch_id:
    rec = _resolve_task_or_dispatch_id(top_dispatch_id)
    if rec is None:
        identity_error = "top-level dispatch_id does not match an active same-session worker"
    else:
        identity_records.append(("dispatch_id", rec))
else:
    identity_error = "missing top-level worker identity"

# Additional top-level identity fields are allowed only when they resolve to
# the same active dispatch record. agent_id remains authoritative: if it was
# present and failed, we never fall back to task_id/dispatch_id.
if identity_error is None:
    if top_agent_id and top_task_id:
        rec = _resolve_task_or_dispatch_id(top_task_id)
        if rec is None or _record_key(rec) != _record_key(identity_records[0][1]):
            identity_error = "top-level agent_id/task_id identity conflict"
        else:
            identity_records.append(("task_id", rec))
    if top_agent_id and top_dispatch_id:
        rec = _resolve_task_or_dispatch_id(top_dispatch_id)
        if rec is None or _record_key(rec) != _record_key(identity_records[0][1]):
            identity_error = "top-level agent_id/dispatch_id identity conflict"
        else:
            identity_records.append(("dispatch_id", rec))
    if (not top_agent_id) and top_task_id and top_dispatch_id:
        rec = _resolve_task_or_dispatch_id(top_dispatch_id)
        if rec is None or _record_key(rec) != _record_key(identity_records[0][1]):
            identity_error = "top-level task_id/dispatch_id identity conflict"
        else:
            identity_records.append(("dispatch_id", rec))

if identity_error is None and identity_records:
    active_record = identity_records[0][1]
    if active_record.get("role") in WRITE_CAPABLE_ROLES:
        _write_debug_row("allow", [_record_key(active_record)])
        sys.exit(0)
    identity_error = "active worker role is not write-capable"

if os.environ.get("LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK") == "1" and in_flight_ids:
    _write_debug_row("allow_legacy_inflight_fallback", in_flight_ids)
    sys.stderr.write(
        "[OGA GUARD WARNING] LOOP_OGA_GUARD_LEGACY_INFLIGHT_FALLBACK=1 used; "
        "legacy in-flight worker fallback expires on 2026-09-30.\n"
    )
    sys.exit(0)

# Best-effort debug log (never affects the decision) -- see _write_debug_row
# for the AC-RH5 caller-identity fields.
_write_debug_row("deny", in_flight_ids)

# Block: no in-flight sub-agent
# AC4 (plan_check_spec.md): deny-message text only — no change to the
# allow/deny decision above. Three content points, in order: (i) the
# orchestrator purpose (dispatch a Coder sub-agent rather than edit code
# inline); (ii) misfire guidance for the case where the blocked actor is
# ITSELF a dispatched sub-agent (fix_plan.md H-GUARD-4 / H-LT6) — note the
# misfire in the final report, complete the assigned work with permitted
# tools, and do NOT dispatch another sub-agent in response (the historical
# runaway-delegation-chain failure mode); (iii) this guard is an advisory
# role-collapse check, not a security boundary (Bash writes bypass it).
basename = os.path.basename(file_path)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"[OGA GUARD] {tool_name}('{basename}') blocked. In a loop-team session, "
            "the delegated write must carry a top-level identity for the exact active, "
            "same-session, unretired Coder/Test-writer dispatch. "
            f"Identity check failed: {identity_error}. The orchestrator (Oga) must "
            "dispatch a Coder sub-agent (Agent tool) rather than edit code inline: "
            "dispatch Agent(description='Coder for ...', prompt='...') first, then "
            "the delegated write tool will be allowed. "
            "If you are seeing this message as a DISPATCHED SUB-AGENT (e.g. a Coder "
            "already assigned this work), this block is a known misfire (fix_plan.md "
            "H-GUARD-4 / H-LT6): note the misfire in your final report and complete the "
            "assigned work using your permitted tools — do NOT dispatch another sub-agent "
            "in response, as that produces runaway delegation chains. "
            "This guard is an advisory role-collapse check, not a security boundary — "
            "it can be bypassed via Bash, so it is not relied on as one."
        )
    }
}))
sys.exit(0)
