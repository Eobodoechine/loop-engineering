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

INSTALL: see README.md (hooks.Stop in ~/.claude/settings.json).
"""
import sys, json, re, glob, os, fnmatch, time, difflib, tempfile

try:
    from loop_logger import log_gate as _log_gate
except Exception:
    _log_gate = None

# AC1 (plan_check_spec.md): a plan-pass flag counts as fresh credit iff
# now - mtime(flag) <= PLAN_PASS_TTL_SECONDS. Module-level so tests can
# monkeypatch it.
PLAN_PASS_TTL_SECONDS = 24 * 3600

try:
    data = json.load(sys.stdin)
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
for ln in lines:
    try: events.append(json.loads(ln))
    except Exception: pass

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

def _tu_input(tu):
    return json.dumps(tu.get("input", "")).lower()

def _tr_text(tr):
    c = tr.get("content", "")
    if isinstance(c, list):
        c = " ".join((p.get("text", "") if isinstance(p, dict) else str(p)) for p in c)
    return str(c).lower()

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
VERIFIER = any(
    tu.get("name", "").lower() in ("task", "agent", "subagent")
    and re.search(r'independent verifier|verifier\.md|verify|plan-?check verifier|verifier plan-?check', _tu_input(tu))
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
    for _tu in _TOOL_USES:
        _nm = _tu.get("name", "").lower()
        if _nm not in _RH_WRITE_TOOLS:
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
_rh_code_writes = [_w for _w in _rh_writes
                   if _RH_CODE_EXT.search(os.path.basename(_w[1]))]

# AC-RH1a+b: >=1 structural code write, and ALL of them under a temp root or
# exactly one of the two settings files -> FEATURE suppressed. A mixed turn
# (one temp write + one repo write) still blocks.
_rh_tmp_roots = _rh_temp_roots()
_rh_exempt_paths_only = bool(_rh_code_writes) and all(
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
_rh_plan_production = bool(_rh_writes) and all(
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
if len(_rh_code_writes) == 1:
    _rh_nm, _rh_real, _rh_in = _rh_code_writes[0]
    if _rh_nm == "edit" and _rh_real.lower().endswith(".md"):
        _rh_old = _rh_in.get("old_string")
        _rh_new = _rh_in.get("new_string")
        if (isinstance(_rh_old, str) and isinstance(_rh_new, str)
                and len(_rh_old.splitlines()) == len(_rh_new.splitlines())
                and difflib.SequenceMatcher(None, _rh_old, _rh_new).ratio() >= 0.9):
            _rh_typo_exempt = True

if ROLE_OR_HARNESS_EDIT and not SUITE_GREEN and not _rh_plan_production:
    if _log_gate: _log_gate("ROLE_OR_HARNESS_EDIT", True,
                             _role_match.group(0)[:200] if _role_match else "", 2)
    sys.stderr.write(
        "[LOOP STOP-GUARD] You edited a loop-team role (roles/*.md) or the harness "
        "(harness/*.py) this turn, but the eval/regression suite is not green this turn. "
        "Phase-1 rule: a change to the team's own gate surface must be re-checked by the "
        "suite, which freezes every past gate-hole as a frozen case. Run "
        "`python3 loop-team/evals/run_evals.py` and confirm it prints `SUITE:" + " GREEN` "
        "(a RED suite means you regressed a lesson — fix it first). Then finish."
    )
    sys.exit(2)

if (FEATURE and not TRIVIAL_ONLY and not VERIFIER
        and not (_rh_exempt_paths_only or _rh_plan_production or _rh_typo_exempt)):
    if _log_gate: _log_gate("FEATURE", True,
                             FEATURE.group(0)[:200] if FEATURE else "", 2)
    sys.stderr.write(
        "[LOOP STOP-GUARD] You edited a feature this turn but did not run an INDEPENDENT verifier "
        "sub-agent. The loop is not done until an independent verifier re-tests the change and confirms "
        "PASS (writer self-testing does not count). Use this project's loop kit if it has one "
        "(loop-team/roles/verifier.md; plus private RUN/VERIFIER rubrics if present). Spawn the verifier "
        "sub-agent now, fix from its findings, then finish."
    )
    sys.exit(2)   # blocks the stop; agent continues

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
_VERIFIER_DETECT = re.compile(
    r'independent verifier|verifier\.md|plan-?check verifier|verifier plan-?check'
)
# AC2 (plan_check_spec.md, H-LT7a): order-insensitive within-turn check. A
# violation exists iff >=1 _CODER_DETECT dispatch is present AND zero
# _VERIFIER_DETECT dispatches are present anywhere in the turn — regardless
# of which comes first in the transcript. This replaces the prior ordered
# if/elif scan (which blocked a same-turn Coder-then-Verifier pair even
# though the substance — a plan-check Verifier ran this turn — was
# satisfied).
_seen_verifier_anywhere = False
_seen_coder_anywhere = False
for _tu in _TOOL_USES:
    if _tu.get("name", "").lower() not in ("task", "agent", "subagent"):
        continue
    _inp = _tu_input(_tu)
    # Verifier checked FIRST per dispatch: a Verifier dispatch whose prompt
    # discusses Coder dispatch formats must not be misclassified as a Coder
    # (H-GUARD-1) — this classification order is per-dispatch, independent
    # of the (now irrelevant) transcript order between dispatches.
    if _VERIFIER_DETECT.search(_inp):
        _seen_verifier_anywhere = True
    elif _CODER_DETECT.search(_inp):
        _seen_coder_anywhere = True

_plan_check_violated = _seen_coder_anywhere and not _seen_verifier_anywhere

if _plan_check_violated:
    # AC1 (plan_check_spec.md, H-GUARD-3/H-LT7b): non-consuming, TTL-bounded
    # plan-pass credit. A flag counts iff it belongs to THIS session and is
    # fresh (now - mtime <= PLAN_PASS_TTL_SECONDS). Any fresh flag licenses
    # the dispatch WITHOUT being deleted — one PLAN_PASS licenses every
    # subsequent Coder dispatch in the session for the TTL window, which is
    # what a micro-step run (one Coder per step, many turns, one plan-check)
    # needs. Stale flags belonging to THIS session may be unlinked
    # best-effort; other sessions' files are never touched.
    import glob as _glob, os as _os
    _gate_dir = _os.path.expanduser(_os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
    _session_id = data.get("session_id", "") or ""  # None-safe
    if _session_id:
        # AC-RH7 (residual_holes_spec.md; fix_plan H-GUARD-5): session_id is an
        # EXTERNAL identifier interpolated into a glob pattern. Escape it so a
        # metachar id (e.g. containing "[...]" or "*") still finds its own
        # literal-named fresh flag (no self-lockout) and can never wildcard-
        # match a different session's flag. Verified: this is the only
        # external-id glob interpolation site in this file (the hygiene gate's
        # glob uses fixed literals; the adjacency gate does no globbing).
        _flags = _glob.glob(_os.path.join(
            _gate_dir, "%s_*.verifier_pass" % _glob.escape(_session_id)))
    else:
        _flags = []
    _now = time.time()
    _fresh_flag_found = False
    for _f in _flags:
        try:
            _mtime = _os.path.getmtime(_f)
        except OSError:
            continue
        if (_now - _mtime) <= PLAN_PASS_TTL_SECONDS:
            _fresh_flag_found = True
        else:
            try: _os.remove(_f)  # stale flag of THIS session — best-effort cleanup
            except OSError: pass
    if _fresh_flag_found:
        sys.exit(0)
    if _log_gate: _log_gate("PLAN_CHECK", True, "coder-before-verifier", 2)
    sys.stderr.write(
        "[LOOP STOP-GUARD] A Coder sub-agent was dispatched this turn without a preceding "
        "plan-check Verifier. Per orchestrator.md step 1: produce the spec, dispatch the "
        "Verifier on the spec/ACs, get its approval, THEN dispatch the Coder. "
        "See loop-team/orchestrator.md step 1."
    )
    sys.exit(2)

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

for _tu in _TOOL_USES:
    _name2 = _tu.get("name", "").lower()
    _inp2 = _tu_input(_tu)
    if _name2 in ("task", "agent", "subagent"):
        if _RESEARCHER_DETECT_V2.search(_inp2):
            _rh3_rid = _tu.get("id") or _tu.get("tool_use_id")
            if _rh3_rid and _rh3_rid in _rh3_returned_ids:
                _seen_researcher2 = True
        elif (_seen_researcher2
              and not _seen_plan_verifier_after_research
              and _VERIFIER_DETECT.search(_inp2)):
            _seen_plan_verifier_after_research = True
    elif (_name2 in _EDIT_TOOLS
          and _seen_researcher2
          and not _seen_plan_verifier_after_research
          and _rh3_is_code_edit(_tu)):
        _research_direct_edit_without_verify = True
        break

if _research_direct_edit_without_verify:
    if _log_gate: _log_gate("RESEARCH_GATE", True, "researcher-then-direct-edit", 2)
    sys.stderr.write(
        "[LOOP STOP-GUARD] A Researcher (Mode D) sub-agent ran this turn and Oga directly "
        "edited files from its findings — without a plan-check Verifier approving the approach "
        "first. Research findings are inputs to a plan, not a license to act. Required flow: "
        "Research → synthesize plan → plan-check Verifier (PLAN_PASS) → then Coder or edit. "
        "Produce the plan now, dispatch the plan-check Verifier, get PLAN_PASS, then proceed."
    )
    sys.exit(2)

# ── Verifier-dispatch hygiene gate (independence, made mechanical; spec AC-B5).
# A Verifier dispatch must never carry the Coder's decision-log content or a green-result
# assertion in Oga-added context. Role files themselves contain result-shaped
# phrases (verifier.md's own output-format instruction and harness-green prose), so the gate
# scans only the RESIDUE after subtracting known role/orchestrator lines.
# Markers built dynamically: reading this file must never arm anything.
def _hyg_markers():
    return [
        "last " + "verdict", "tests " + "passed", "tests are " + "passing",
        "all " + "green", "suite: " + "green", "harness is " + "green",
        "decision " + "log", "spec " + "interpretation:", "alternatives " + "rejected",
    ]

def _hyg_known_lines():
    import glob as _g
    # Derive the role-file base from THIS file's location (hooks/ and loop-team/
    # are siblings in every clone), so the gate is ACTIVE from any clone path;
    # the personal install path is only a fallback.
    base = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "loop-team"))
    if not os.path.isdir(base):
        base = os.path.expanduser("~/Claude/loop/loop-team")
    lines = set()
    files = _g.glob(os.path.join(base, "roles", "*.md")) + [os.path.join(base, "orchestrator.md")]
    for f in files:
        try:
            for ln in open(f, encoding="utf-8"):
                ln = ln.strip().lower()
                if ln:
                    lines.add(ln)
        except OSError:
            return None  # unreadable role surface -> gate skips (fail-open)
    return lines

_hyg_violation = None
_known = _hyg_known_lines()
if _known is not None:
    for _tu in _TOOL_USES:
        if _tu.get("name", "").lower() not in ("task", "agent", "subagent"):
            continue
        _desc = str((_tu.get("input") or {}).get("description", "")).lower()
        if not _VERIFIER_DETECT.search(_desc):
            continue
        _prompt = str((_tu.get("input") or {}).get("prompt", ""))
        _residue_lines = [ln.strip().lower() for ln in _prompt.splitlines()
                          if ln.strip() and ln.strip().lower() not in _known]
        _residue = re.sub(r"\s+", " ", " ".join(_residue_lines))
        for _mk in _hyg_markers():
            if _mk in _residue:
                _hyg_violation = (_desc[:60], _mk)
                break
        if _hyg_violation:
            break

if _hyg_violation:
    if _log_gate: _log_gate("VERIFIER_HYGIENE", True, "%s | %s" % _hyg_violation, 2)
    sys.stderr.write(
        ("[LOOP STOP-GUARD] Verifier-dispatch hygiene violation: the dispatch %r carries "
         "the result-shaped phrase %r in Oga-added context. The Verifier must form its own "
         "provisional verdict BEFORE seeing the harness result, and must never see the "
         "Coder's decision-" + "log — withholding the document is not enough; do not "
         "paraphrase, summarize, or hint at either (orchestrator.md access-control rules). "
         "Re-dispatch the Verifier with the spec BY PATH and the artifact only.")
        % _hyg_violation)
    sys.exit(2)

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
_STATUS_DOC_DENYLIST = [
    "handoff*", "plan_check_log*", "*decision_log*",
    # run_log*: prefix form (run_log.md, RUN_LOG.md).
    # *run_log*: suffix/embedded form (plan-check iter 3 evidence: a live
    # corpus scan of ~/Claude/loop/runs/*/ found restyle_run_log.md — a
    # verdict-bearing run-log file that "run_log*" (prefix-only) does not
    # match. "*run_log*" is chosen over the fully-open "*run*" /
    # "*log*" precisely because it stays anchored to the two-word compound
    # "run_log" (with underscore) rather than either word alone — a scan of
    # this repo (hooks/, loop-team/) turned up test_run_evals.py,
    # test_run_experiment.py, test_run_trace.py, test_runner.py, none of
    # which contain the literal substring "run_log", so none false-positive
    # under "*run_log*". A hypothetical "test_run_logger.py" WOULD match
    # "*run_log*" (substring "run_log" is present) — that residual risk is
    # accepted because (1) no such file exists in this corpus today, (2) it
    # is a test file that would only ever sit beside other test files, not
    # beside a Verifier's spec dispatch target, and (3) the alternative
    # (leaving the class uncovered) lets a real verdict-bearing file leak.
    "run_log*", "*run_log*",
    # summary*/run_summary*: ANCHORED forms (not "*summary*") — plan-check
    # iter 2 evidence: a live corpus scan found summary.md/SUMMARY.md/
    # run_summary.md in 6 run dirs carrying literal verdict text. Anchored so
    # neither matches incidental repo files like test_summary_parser.py.
    # "summary*" alone does NOT match "run_summary.md" (no leading "summary")
    # -- both patterns are required together.
    "summary*", "run_summary*",
]

_ABS_TOKEN_RE = re.compile(r"(?<!\S)(/[^\s\"'`)]+|~[^\s\"'`)]*|[A-Za-z0-9_.\-]+/[^\s\"'`)]*)")


def _adj_extract_tokens(prompt_text):
    """Extract candidate path-like tokens from dispatch prompt text: absolute
    paths, ~-paths, and bare relative tokens containing '/'. Trailing
    punctuation commonly glued to prose (.,;:) is stripped."""
    tokens = []
    for m in _ABS_TOKEN_RE.finditer(prompt_text):
        tok = m.group(0).rstrip(".,;:")
        if tok:
            tokens.append(tok)
    return tokens


def _adj_candidate_paths(token, cwd, target_dir):
    """Resolve a single extracted token to candidate filesystem paths under
    every applicable base, per its form. Returns a list (not existence-checked
    yet)."""
    cands = []
    if token.startswith("~"):
        cands.append(os.path.expanduser(token))
    elif token.startswith("/"):
        cands.append(token)
    else:
        # bare relative token (contains '/', no leading '/' or '~'):
        # resolve against BOTH the hook process cwd and the run's target dir
        # if armed via $LOOP_GATE_DIR/<session>_target.
        cands.append(os.path.join(cwd, token))
        if target_dir:
            cands.append(os.path.join(target_dir, token))
    return cands


def _adj_read_target_dir(session_id):
    """Read $LOOP_GATE_DIR/<session>_target if armed (same convention as
    micro_step_gates.py's _target file). Returns the target dir string or
    None if not armed/unreadable. Never raises."""
    if not session_id:
        return None
    try:
        gate_dir = os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
        tfile = os.path.join(gate_dir, "%s_target" % session_id)
        if not os.path.isfile(tfile):
            return None
        with open(tfile, encoding="utf-8") as f:
            val = f.read().strip()
        return val or None
    except OSError:
        return None


def _adj_status_doc_in_dir(dirpath):
    """Return the first entry name in dirpath that case-insensitively matches
    the status-doc denylist, or None. dirpath must be a real, existing dir."""
    try:
        entries = os.listdir(dirpath)
    except OSError:
        return None
    for name in entries:
        low = name.lower()
        for pat in _STATUS_DOC_DENYLIST:
            if fnmatch.fnmatch(low, pat):
                return name
    return None


_adj_violation = None  # (offending_path, status_doc_name)
_adj_session_id = data.get("session_id", "") or ""
_adj_cwd = os.getcwd()
_adj_target_dir = _adj_read_target_dir(_adj_session_id)
if _adj_target_dir:
    _adj_target_dir = os.path.expanduser(_adj_target_dir)

for _tu in _TOOL_USES:
    if _adj_violation:
        break
    if _tu.get("name", "").lower() not in ("task", "agent", "subagent"):
        continue
    _adj_desc = str((_tu.get("input") or {}).get("description", "")).lower()
    if not _VERIFIER_DETECT.search(_adj_desc):
        continue
    _adj_prompt = str((_tu.get("input") or {}).get("prompt", ""))
    for _tok in _adj_extract_tokens(_adj_prompt):
        for _cand in _adj_candidate_paths(_tok, _adj_cwd, _adj_target_dir):
            if not os.path.exists(_cand):
                continue  # existence-gated: hypothetical paths never flag
            _real = os.path.realpath(_cand)  # symlink evasion: resolve BEFORE parent scan
            _parent = _real if os.path.isdir(_real) else os.path.dirname(_real)
            if not _parent or not os.path.isdir(_parent):
                continue
            _hit = _adj_status_doc_in_dir(_parent)
            if _hit:
                _adj_violation = (_cand, _hit)
                break
        if _adj_violation:
            break

if _adj_violation:
    _adj_path, _adj_doc = _adj_violation
    if _log_gate: _log_gate("VERIFIER_ADJACENCY", True, "%s | %s" % (_adj_path, _adj_doc), 2)
    sys.stderr.write(
        ("[LOOP STOP-GUARD] Verifier-dispatch adjacency violation: the dispatch references "
         "%r, whose directory also contains the status doc %r. A hygiene-clean prompt is not "
         "enough — the Verifier can find prior verdicts/decision-" + "logs by exploring the "
         "directory. Remedy: copy the spec to an isolated specs/ dir (or a scratch path) "
         "so Verifier inputs never sit beside run-status docs, then re-dispatch.")
        % (_adj_path, _adj_doc)
    )
    sys.exit(2)

# ── Micro-step gates (deterministic; FAIL-OPEN on any error — the module may be
# mid-build in the very session whose Stop hook loads it; spec AC-B1). ──────────
try:
    import os as _msg_os, sys as _msg_sys
    _msg_sys.path.insert(0, _msg_os.path.dirname(_msg_os.path.abspath(__file__)))
    import micro_step_gates as _msg_mod
    _msg_blocked, _msg_text = _msg_mod.run(data)
    if _msg_blocked:
        if _log_gate: _log_gate("MICRO_STEP", True, _msg_text[:80], 2)
        sys.stderr.write(_msg_text)
        sys.exit(2)
    # shadow slop report (never blocks; best-effort)
    try:
        import subprocess as _msg_sp
        _msg_act = _msg_mod._activation(data)
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

if _log_gate: _log_gate("ALL_GATES", False, "", 0)
sys.exit(0)
