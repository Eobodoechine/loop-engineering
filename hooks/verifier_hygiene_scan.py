"""verifier_hygiene_scan.py -- shared, side-effect-free hygiene/adjacency
detection for a Verifier-shaped dispatch. Extracted from loop_stop_guard.py
(H-PRETOOLUSE-VERIFIER-HYGIENE-1) so hooks/pre_tool_use_oga_guard.py can run
the IDENTICAL check before a dispatch fires, not just loop_stop_guard.py
after it fires -- one canonical implementation, not two that can drift
(the exact class of bug H-VERIFIER-REGEX-DUPLICATE-1 already found once)."""
import fnmatch
import os
import re

VERIFIER_DETECT = re.compile(
    r'independent verifier|verifier\.md|plan-?check verifier|verifier plan-?check'
)

STATUS_DOC_DENYLIST = [
    "handoff*", "plan_check_log*", "*decision_log*",
    "run_log*", "*run_log*",
    "summary*", "run_summary*",
]

_ABS_TOKEN_RE = re.compile(r"(?<!\S)(/[^\s\"'`)]+|~[^\s\"'`)]*|[A-Za-z0-9_.\-]+/[^\s\"'`)]*)")


def hyg_markers():
    return [
        "last " + "verdict", "tests " + "passed", "tests are " + "passing",
        "all " + "green", "suite: " + "green", "harness is " + "green",
        "decision " + "log", "spec " + "interpretation:", "alternatives " + "rejected",
    ]


def hyg_known_lines(roles_base):
    """roles_base: the loop-team/ directory to glob roles/*.md + orchestrator.md
    from. Caller resolves this (loop_stop_guard.py and pre_tool_use_oga_guard.py
    each derive it from their own __file__ location, same convention, same
    result since they're siblings in hooks/). Returns None on unreadable role
    surface (fail-open, matching the original).

    H-HYGIENE-SCAN-SOURCE-EMBED-FP-1: also folds in every line of hooks/*.py
    source (the sibling directory of roles_base, same "../hooks" derivation
    both callers already use for roles_base itself: roles_base is
    ".../loop-team", so ".../loop-team/../hooks" == ".../hooks"). A Verifier
    dispatch that embeds a hook's own source (realistic -- this repo builds on
    its own hooks) must not be flagged just because a comment or regex literal
    inside that source happens to contain a marker substring; the source is
    not a self-reported hygiene violation, it's the artifact under review.
    This corpus addition is best-effort: an unreadable/missing hooks/ dir
    (e.g. the roles_base fixtures used by the existing unit tests, which have
    no sibling hooks/ dir at all) is silently skipped rather than turned into
    a fail-open None, since the ORIGINAL contract (fail-open only when the
    role-file surface itself -- roles/*.md + orchestrator.md -- is missing or
    unreadable) must be preserved unchanged."""
    import glob as _g
    lines = set()
    files = _g.glob(os.path.join(roles_base, "roles", "*.md")) + [os.path.join(roles_base, "orchestrator.md")]
    for f in files:
        try:
            for ln in open(f, encoding="utf-8"):
                ln = ln.strip().lower()
                if ln:
                    lines.add(ln)
        except OSError:
            return None
    hooks_dir = os.path.normpath(os.path.join(roles_base, "..", "hooks"))
    for f in _g.glob(os.path.join(hooks_dir, "*.py")):
        try:
            for ln in open(f, encoding="utf-8"):
                ln = ln.strip().lower()
                if ln:
                    lines.add(ln)
        except OSError:
            continue
    return lines


def evaluate_hygiene(prompt_text, known_lines):
    """Returns (matched_marker) or None. known_lines: from hyg_known_lines(),
    or None (caller must skip calling this at all if None -- fail-open)."""
    residue_lines = [ln.strip().lower() for ln in prompt_text.splitlines()
                     if ln.strip() and ln.strip().lower() not in known_lines]
    residue = re.sub(r"\s+", " ", " ".join(residue_lines))
    for mk in hyg_markers():
        if mk in residue:
            return mk
    return None


def adj_extract_tokens(prompt_text):
    tokens = []
    for m in _ABS_TOKEN_RE.finditer(prompt_text):
        tok = m.group(0).rstrip(".,;:")
        if tok:
            tokens.append(tok)
    return tokens


def adj_candidate_paths(token, cwd, target_dir):
    cands = []
    if token.startswith("~"):
        cands.append(os.path.expanduser(token))
    elif token.startswith("/"):
        cands.append(token)
    else:
        cands.append(os.path.join(cwd, token))
        if target_dir:
            cands.append(os.path.join(target_dir, token))
    return cands


def adj_read_target_dir(session_id, gate_dir=None):
    if not session_id:
        return None
    try:
        gate_dir = gate_dir or os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
        tfile = os.path.join(gate_dir, "%s_target" % session_id)
        if not os.path.isfile(tfile):
            return None
        with open(tfile, encoding="utf-8") as f:
            val = f.read().strip()
        return val or None
    except OSError:
        return None


def adj_status_doc_in_dir(dirpath, exclude_name=None):
    """exclude_name: when given, the directory entry whose name matches
    exclude_name (case-insensitive, matching this function's own
    already-lowercased comparison convention) is skipped -- used by
    evaluate_adjacency() to exclude a FILE candidate from matching against
    its own parent directory's listing (self-match exclusion; see that
    function's docstring). None (the default) preserves the original,
    unexcluded scan -- used for the directory-candidate case, where no
    exclusion applies."""
    try:
        entries = os.listdir(dirpath)
    except OSError:
        return None
    _exclude_low = exclude_name.lower() if exclude_name else None
    for name in entries:
        low = name.lower()
        if _exclude_low is not None and low == _exclude_low:
            continue
        for pat in STATUS_DOC_DENYLIST:
            if fnmatch.fnmatch(low, pat):
                return name
    return None


def evaluate_adjacency(prompt_text, cwd, target_dir):
    """Returns (offending_path, status_doc_name) or None.

    Self-match exclusion (research/loop-stop-guard-misfire-dossier-
    2026-07-08.md section 2; fix_plan.md new H- entry): when the resolved
    candidate `real` is itself a FILE, it is excluded from the directory
    listing scanned for a denylist match against its own parent -- a target
    that IS the status doc (e.g. a dispatch instructed to read
    plan_check_log.md directly) must not flag itself as though it were an
    unrelated neighbor. This exclusion applies ONLY in the file case; when
    `real` is a DIRECTORY, behavior is unchanged (a directory target that
    CONTAINS a status doc must keep blocking)."""
    for tok in adj_extract_tokens(prompt_text):
        for cand in adj_candidate_paths(tok, cwd, target_dir):
            if not os.path.exists(cand):
                continue
            real = os.path.realpath(cand)
            _is_file_target = os.path.isfile(real)
            parent = real if os.path.isdir(real) else os.path.dirname(real)
            if not parent or not os.path.isdir(parent):
                continue
            _exclude_name = os.path.basename(real) if _is_file_target else None
            hit = adj_status_doc_in_dir(parent, exclude_name=_exclude_name)
            if hit:
                return (cand, hit)
    return None
