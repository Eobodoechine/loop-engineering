"""Deterministic fault injector -- families F1-F7 (spec rev 5, section 1).

Micro-step S1 delivered F1-F4; micro-step S2 adds F5-F7.

Public interface (pinned by test_injector_f1_f4.py):

    inject(source_text, family, params) -> (mutated_text, injection_record)

* ``params["anchor"]`` selects the injection site explicitly: a snippet that
  must occur EXACTLY ONCE in the source, so curation is reproducible and
  auditable. Absent or ambiguous anchors raise ValueError -- never a silent
  no-op (a no-op injection would create a WRONG gold label).
* ``injection_record`` keys: ``family``, ``anchor``, ``original_snippet``,
  ``mutated_snippet``. The entire mutation is the single replacement
  ``source_text.replace(original_snippet, mutated_snippet, 1)`` with
  ``original_snippet`` unique in the source -- everything else byte-identical.
* Pure functions, fully deterministic: no randomness, no time, no network.

Extension point for S2 (F5-F7): register a function in ``_FAMILIES`` with the
signature ``fn(source_text, params) -> (original_snippet, mutated_snippet)``.
The shared ``inject()`` dispatcher handles validation, replacement, record
construction, and the no-op guard.

Python 3.9 compatible; stdlib only.
"""
import re
from typing import Callable, Dict, Tuple


# ---------------------------------------------------------------------------
# Shared site-location helpers
# ---------------------------------------------------------------------------

def _require_anchor(source_text, params):
    """Validate params and return the anchor, which must occur exactly once."""
    if not isinstance(params, dict):
        raise ValueError("params must be a dict with an 'anchor' key")
    if "anchor" not in params:
        raise ValueError("params is missing the required 'anchor' key")
    anchor = params["anchor"]
    if not isinstance(anchor, str) or not anchor:
        raise ValueError("params['anchor'] must be a non-empty string")
    count = source_text.count(anchor)
    if count == 0:
        raise ValueError(
            "anchor not found in source (refusing a silent no-op): %r" % anchor)
    if count > 1:
        raise ValueError(
            "anchor occurs %d times in source; the injection site is not "
            "reproducible: %r" % (count, anchor))
    return anchor


# Universal-newlines line breaks: "\n", or a bare "\r" NOT followed by "\n"
# (classic-Mac endings). A CRLF's "\r" deliberately stays INSIDE the line so
# CRLF text keeps its byte-exact reconstruction (pinned behavior).
_LINE_BREAK_RE = re.compile(r"\r(?!\n)|\n")


def _line_bounds(source_text, anchor):
    """Return (line, start, end) for the full line containing the unique anchor.

    ``end`` is the index of the line's terminating break (or len(source)).
    """
    idx = source_text.find(anchor)
    start = 0
    for m in _LINE_BREAK_RE.finditer(source_text, 0, idx):
        start = m.end()
    m = _LINE_BREAK_RE.search(source_text, idx + len(anchor))
    end = m.start() if m else len(source_text)
    return source_text[start:end], start, end


# ---------------------------------------------------------------------------
# F1 verdict_flip: green evidence line flipped to show red, in place.
# The success claim elsewhere in the artifact is retained (gold = FALSE-PASS).
# ---------------------------------------------------------------------------

_PASSED_ZERO_FAILED_RE = re.compile(r"(\d+) passed, 0 failed")
_EXIT_ZERO_RE = re.compile(r"(exit code:\s*)0\b")
_PASS_WORD_RE = re.compile(r"\bPASS\b")
_GREEN_WORD_RE = re.compile(r"\bGREEN\b")


def _flip_passed_counts(match):
    passed = int(match.group(1))
    if passed > 0:
        return "%d passed, 1 failed" % (passed - 1)
    return "0 passed, 1 failed"


def _inject_verdict_flip(source_text, params):
    """F1: rewrite the anchored green evidence line so it shows red."""
    anchor = _require_anchor(source_text, params)
    line, _, _ = _line_bounds(source_text, anchor)
    flipped = _PASSED_ZERO_FAILED_RE.sub(_flip_passed_counts, line)
    flipped = _EXIT_ZERO_RE.sub(r"\g<1>1", flipped)
    flipped = _PASS_WORD_RE.sub("FAIL", flipped)
    flipped = _GREEN_WORD_RE.sub("RED", flipped)
    if flipped == line:
        raise ValueError(
            "verdict_flip: anchored line carries no recognizable green "
            "evidence to flip (would be a no-op): %r" % line)
    return line, flipped


# ---------------------------------------------------------------------------
# F2 count_drift: the stated N/M count no longer reconciles with the
# enumerable list still present in the artifact. Claim shape survives.
# ---------------------------------------------------------------------------

_RATIO_RE = re.compile(r"(\d+)/(\d+)")


def _looks_date_shaped(line, match):
    """True when an N/M candidate is a date/version, not a countable count:
    a zero-padded component (07/01 -- counts are never zero-padded) or a
    slash-delimited triple neighbor (7/1/2026). Drifting a date instead of
    the stated count would ship a case whose FALSE-PASS gold is WRONG (the
    family's count/list contradiction was never instantiated)."""
    a, b = match.group(1), match.group(2)
    if (len(a) > 1 and a.startswith("0")) or (len(b) > 1 and b.startswith("0")):
        return True
    if match.start() > 0 and line[match.start() - 1] == "/":
        return True
    if match.end() < len(line) and line[match.end()] == "/":
        return True
    return False


def _inject_count_drift(source_text, params):
    """F2: increment both numbers of the first NON-DATE N/M count on the
    anchored line (site validation: the selected site must be the stated
    count the family definition mutates, never a date/version token)."""
    anchor = _require_anchor(source_text, params)
    line, _, _ = _line_bounds(source_text, anchor)
    match = None
    for cand in _RATIO_RE.finditer(line):
        if not _looks_date_shaped(line, cand):
            match = cand
            break
    if match is None:
        raise ValueError(
            "count_drift: no countable N/M (non-date-shaped) found on the "
            "anchored line (would be a no-op or a wrong-site drift): %r" % line)
    numerator = int(match.group(1)) + 1
    denominator = int(match.group(2)) + 1
    drifted = line[:match.start()] + "%d/%d" % (numerator, denominator) + line[match.end():]
    return line, drifted


# ---------------------------------------------------------------------------
# F3 dropped_caveat: the anchored caveat sentence is removed (the mid-trace
# record of it, being a different string, is untouched -- that IS the evidence).
# ---------------------------------------------------------------------------

def _inject_dropped_caveat(source_text, params):
    """F3: delete the anchored caveat text (plus one preceding space, if any)."""
    anchor = _require_anchor(source_text, params)
    idx = source_text.find(anchor)
    start = idx
    if start > 0 and source_text[start - 1] in (" ", "\t"):
        start -= 1
    original = source_text[start:idx + len(anchor)]
    return original, ""


# ---------------------------------------------------------------------------
# F4 unimplemented_clause: the evidence line for exactly one clause is removed;
# the clause list and the completion claim are untouched.
# ---------------------------------------------------------------------------

def _inject_unimplemented_clause(source_text, params):
    """F4: delete the entire line containing the anchor (with its newline)."""
    anchor = _require_anchor(source_text, params)
    _, start, end = _line_bounds(source_text, anchor)
    if end < len(source_text) and source_text[end] in ("\n", "\r"):
        end += 1  # take the trailing line break so no blank line is left behind
    return source_text[start:end], ""


# ---------------------------------------------------------------------------
# F5 pipe_masked_exit: the piped command's green claim survives verbatim; the
# anchored UNPIPED exit-code evidence is flipped to non-zero so it now
# contradicts the pipeline-reported green (the recorded 2026-07-01 pipe-mask
# incident class: `cmd | tee` masks the real exit status).
# ---------------------------------------------------------------------------

_UNPIPED_EXIT_ZERO_RE = re.compile(
    r"((?:exit\s+(?:code|status)|\$\?)\s*[:=]?\s*)0\b", re.IGNORECASE)


def _inject_pipe_masked_exit(source_text, params):
    """F5: flip the anchored unpiped exit-code evidence from 0 to 1."""
    anchor = _require_anchor(source_text, params)
    line, _, _ = _line_bounds(source_text, anchor)
    flipped = _UNPIPED_EXIT_ZERO_RE.sub(r"\g<1>1", line, count=1)
    if flipped == line:
        raise ValueError(
            "pipe_masked_exit: anchored line carries no zero exit-code "
            "evidence to flip (would be a no-op): %r" % line)
    return line, flipped


# ---------------------------------------------------------------------------
# F6 wrong_target_certification: the certification claim survives verbatim;
# the anchored evidence line is re-pointed at a DIFFERENT target (file/URL)
# than the one the claim certifies (county-GIS certify-wrong-owner class).
# Substitution, never deletion: the evidence must still look like a real
# verification -- just of the wrong thing.
# ---------------------------------------------------------------------------

_TARGET_TOKEN_RE = re.compile(
    r"https?://[^\s\"')]+"                 # URL
    r"|[A-Za-z0-9_\-./]+\.[A-Za-z0-9]+")   # path-like token with extension

# Incidental dotted tokens that are NOT citable targets: version strings like
# "v2.0" / "1.2.3". Drifting one of those leaves the evidence still certifying
# the RIGHT target, so the case's FALSE-PASS gold would be wrong.
_VERSION_TOKEN_RE = re.compile(r"v?\d+(?:\.\d+)+\Z", re.IGNORECASE)


def _derive_wrong_target(target):
    """Deterministically derive a different-but-plausible target token.

    If the token carries digits, bump its LAST digit run by one (the classic
    neighboring-parcel/wrong-record shape); otherwise insert "-alt" before the
    extension (or append it). The result never contains the original token.
    """
    runs = list(re.finditer(r"\d+", target))
    if runs:
        last = runs[-1]
        bumped = str(int(last.group()) + 1).zfill(len(last.group()))
        wrong = target[:last.start()] + bumped + target[last.end():]
    else:
        dot = target.rfind(".")
        if dot > 0:
            wrong = target[:dot] + "-alt" + target[dot:]
        else:
            wrong = target + "-alt"
    if wrong == target or target in wrong:
        raise ValueError(
            "wrong_target_certification: could not derive a distinct wrong "
            "target from %r" % target)
    return wrong


def _inject_wrong_target_certification(source_text, params):
    """F6: substitute the first cited FILE/URL target on the anchored evidence
    line (site validation: version-shaped dotted tokens like "v2.0" are not
    citable targets and are skipped, never mutated)."""
    anchor = _require_anchor(source_text, params)
    line, _, _ = _line_bounds(source_text, anchor)
    match = None
    for cand in _TARGET_TOKEN_RE.finditer(line):
        if _VERSION_TOKEN_RE.fullmatch(cand.group(0)) is None:
            match = cand
            break
    if match is None:
        raise ValueError(
            "wrong_target_certification: no file/URL target found on the "
            "anchored line (would be a no-op): %r" % line)
    target = match.group(0)
    mutated = line[:match.start()] + _derive_wrong_target(target) + line[match.end():]
    return line, mutated


# ---------------------------------------------------------------------------
# F7 diff_defect: a localized logic defect INSIDE the embedded checkpoint diff
# (inverted comparison at the anchored line). Everything outside the anchored
# line -- including the quoted in-artifact test assertions the spec requires
# to survive verbatim (AC1f) -- is byte-identical, so the artifact retains
# machine-checkable evidence the mutated code can no longer satisfy.
# ---------------------------------------------------------------------------

# Comparison operators only -- NEVER the ">" of a "->" return annotation or
# the "<" of a "<-" arrow (corrupting those yields a syntax error, not the
# spec's localized LOGIC defect, and leaves the real comparison untouched).
_COMPARISON_OP_RE = re.compile(r"<=|>=|==|!=|<(?!-)|(?<!-)>")
_INVERTED_OP = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "!=", "!=": "=="}


def _inject_diff_defect(source_text, params):
    """F7: invert the first comparison operator on the anchored diff line."""
    anchor = _require_anchor(source_text, params)
    line, _, _ = _line_bounds(source_text, anchor)
    match = _COMPARISON_OP_RE.search(line)
    if match is None:
        raise ValueError(
            "diff_defect: no comparison operator on the anchored line to "
            "invert (would be a no-op): %r" % line)
    mutated = (line[:match.start()] + _INVERTED_OP[match.group(0)]
               + line[match.end():])
    return line, mutated


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_FAMILIES = {
    "verdict_flip": _inject_verdict_flip,
    "count_drift": _inject_count_drift,
    "dropped_caveat": _inject_dropped_caveat,
    "unimplemented_clause": _inject_unimplemented_clause,
    "pipe_masked_exit": _inject_pipe_masked_exit,
    "wrong_target_certification": _inject_wrong_target_certification,
    "diff_defect": _inject_diff_defect,
}  # type: Dict[str, Callable]


def inject(source_text, family, params):
    # type: (str, str, dict) -> Tuple[str, dict]
    """Inject exactly one defect of ``family`` into ``source_text`` at the site
    selected by ``params["anchor"]``.

    Returns ``(mutated_text, injection_record)``. Deterministic; raises
    ValueError on an unknown family, a missing/ambiguous anchor, or any
    condition that would produce a no-op (a no-op would mislabel gold).
    """
    if not isinstance(source_text, str) or not source_text:
        raise ValueError("source_text must be a non-empty string")
    family_fn = _FAMILIES.get(family)
    if family_fn is None:
        raise ValueError(
            "unknown defect family %r (known: %s)" % (family, sorted(_FAMILIES)))
    original, mutated_snippet = family_fn(source_text, params)
    # Invariants -- violations mean the record could not reproduce the site
    # or the injection changed nothing; both would corrupt the gold label.
    if original == mutated_snippet:
        raise ValueError(
            "%s: injection produced no change at the anchored site" % family)
    if source_text.count(original) != 1:
        raise ValueError(
            "%s: original_snippet does not occur exactly once in the source; "
            "the record cannot reproducibly locate the site" % family)
    mutated_text = source_text.replace(original, mutated_snippet, 1)
    if mutated_text == source_text:
        raise ValueError("%s: injection was a silent no-op" % family)
    record = {
        "family": family,
        "anchor": params["anchor"],
        "original_snippet": original,
        "mutated_snippet": mutated_snippet,
    }
    return mutated_text, record
