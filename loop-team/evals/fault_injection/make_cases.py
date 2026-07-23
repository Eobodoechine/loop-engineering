"""Fail-closed sanitizer + lint-conformant case emitter (spec rev 5, sections
2-3). Micro-step S3.

Public interface (pinned by test_sanitizer_emitter.py):

    load_markers(markers_path)                    -> list of marker strings
    sanitize_text(text, markers_path)             -> sanitized str
    assert_no_markers(text, markers_path)         -> None (raises on survivor)
    sanitize_manifest_entry(entry, markers_path)  -> new sanitized dict
    build_case(case_id, artifact_text, expected, origin, rubric, markers_path)
                                                  -> lint-conformant case dict

Fail-closed rule (spec section 2): a MISSING or EMPTY (or comment-only) marker
file at emission time raises ValueError BEFORE anything is produced. This
deliberately does NOT inherit verify_build.pii_pattern's fail-open fallback --
acceptable for a lint that runs everywhere, wrong for an EMITTER that writes
repo-committed files from private run logs. Markers are loaded at runtime from
the given path; no marker ever appears as a literal in this file.

Python 3.9 compatible; stdlib only; deterministic (no randomness/time/network).
"""
import os
import re
import sys

# Absolute home-path shapes (slash-Users or slash-home, then a <name>
# component) are replaced with this placeholder; the rest of the path is
# preserved (spec: "<REPO>-style").
# Non-canonical spellings a run log can emit -- doubled slashes, ./ or ../
# segments before the username, any casing (/users/, /HOME/) -- must redact
# too; over-redaction is acceptable, under-redaction never (Oga ruling,
# adversarial round 2026-07-02).
_HOME_PATH_RE = re.compile(
    r"/+(?:Users|home)/+(?:\.{1,2}/+)*[^/\s]+", re.IGNORECASE)
_REPO_PLACEHOLDER = "<REPO>"
_REDACTED = "<REDACTED>"

# Valid `expected` labels (mirrors verify_build.LABELS; a typo'd label must
# never reach classify(), which buckets silently instead of raising).
VALID_EXPECTED = ("PASS", "FAIL", "FALSE-PASS")

# Opaque id shape (spec section 2): zero-padded fi-NNN, no family/difficulty/
# control tokens -- the id is the one per-case field the blind export keeps.
# ASCII digits only (\d matches any Unicode decimal digit) and \Z (a bare $
# matches BEFORE a trailing newline): the id is a filename and a verdicts-file
# key, so "fi-007\n" and "fi-<arabic digits>" must both be rejected.
_CASE_ID_RE = re.compile(r"^fi-[0-9]{3}\Z")


def load_markers(markers_path):
    """Load PII markers (one per line; blank and '#'-comment lines skipped).

    Fail-closed: raises ValueError if the file is missing, unreadable, empty,
    or contains zero usable marker lines. Zero markers means the environment
    is wrong, not that there are no markers (spec section 2).
    """
    try:
        # utf-8-sig: an editor-default BOM must not weld itself onto the FIRST
        # marker and silently disarm it (fail-closed means the marker matches).
        with open(markers_path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise ValueError(
            "fail-closed: marker file missing/unreadable at %r (%s); "
            "refusing to emit anything" % (markers_path, e))
    # Robust per-line strip: whitespace plus any stray mid-file BOM character.
    markers = [s.strip().strip(u"\ufeff").strip() for s in lines]
    markers = [s for s in markers if s and not s.startswith("#")]
    if not markers:
        raise ValueError(
            "fail-closed: marker file %r has no usable marker lines "
            "(empty or comment-only); refusing to emit anything" % markers_path)
    return markers


def _check_no_markers(text, markers):
    """Raise ValueError if any loaded marker survives in `text`.

    Case-insensitive, matching the live lint's IGNORECASE search. The raised
    message identifies the marker by index/length only -- never echoes it.
    """
    for i, m in enumerate(markers):
        if re.search(re.escape(m), text, re.IGNORECASE):
            raise ValueError(
                "fail-closed: marker #%d (%d chars) survives in text; "
                "refusing to emit" % (i, len(m)))


def _sanitize_with(text, markers):
    """Strip markers, replace absolute home paths, then gate the result."""
    out = text
    for m in markers:
        out = re.sub(re.escape(m), _REDACTED, out, flags=re.IGNORECASE)
    out = _HOME_PATH_RE.sub(_REPO_PLACEHOLDER, out)
    _check_no_markers(out, markers)  # belt and suspenders: never emit a survivor
    return out


def sanitize_text(text, markers_path):
    """Sanitize one string: markers stripped, home paths -> <REPO> placeholder.

    Raises (via load_markers) on a missing/empty marker file BEFORE producing
    any output, and raises if any marker somehow survives sanitization.
    """
    return _sanitize_with(text, load_markers(markers_path))


def assert_no_markers(text, markers_path):
    """The explicit fail-closed gate: raise ValueError if ANY marker survives
    in `text`; return None on clean text."""
    _check_no_markers(text, load_markers(markers_path))


def _sanitize_value(value, markers):
    """Recursively sanitize a manifest value: every STRING LEAF goes through
    the same sanitize-then-gate path as sanitize_text, containers (dict/list/
    tuple) are walked, scalars (int/float/bool/None) pass through, and any
    other type raises -- FAIL-CLOSED, never a silent pass-through (Oga ruling,
    adversarial round 2026-07-02: a marker inside a nested field must be
    sanitized or raise; it may never come back live)."""
    if isinstance(value, str):
        return _sanitize_with(value, markers)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str):
                # Keys are schema, not content: rewriting them would silently
                # change the shape, so a marker in a key raises instead.
                _check_no_markers(k, markers)
            out[k] = _sanitize_value(v, markers)
        return out
    if isinstance(value, (list, tuple)):
        walked = [_sanitize_value(v, markers) for v in value]
        return tuple(walked) if isinstance(value, tuple) else walked
    if value is None or isinstance(value, (int, float, bool)):
        return value
    raise ValueError(
        "fail-closed: manifest value of unsupported type %s cannot be "
        "sanitized; refusing to emit it" % type(value).__name__)


def sanitize_manifest_entry(entry, markers_path):
    """Return a NEW dict with every string leaf sanitized via the same path
    as sanitize_text (spec section 2: the sanitizer runs on every manifest
    string field -- original_snippet, mutated_snippet, source_file,
    description included), recursing into list/dict container fields.
    Non-string scalar fields pass through unchanged; a marker surviving
    ANYWHERE in the entry raises."""
    markers = load_markers(markers_path)  # fail-closed before producing anything
    return _sanitize_value(dict(entry), markers)


def _blind_export_guard(case):
    """Run the REAL replay_judge.export_blind over the built case so the
    blind-file curation rule (rubric/origin must not open with a >=20-char
    verbatim artifact quote) fails at BUILD time, not at S5 export time."""
    evals_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if evals_dir not in sys.path:
        sys.path.insert(0, evals_dir)
    import replay_judge
    replay_judge.export_blind([case])


def build_case(case_id, artifact_text, expected, origin, rubric, markers_path):
    """Build one lint-conformant top-level case dict (spec section 2).

    Fixed fields: target="verifier", requires="judge", type="BEHAVIORAL",
    suite="fault_injection". artifact/origin/rubric are sanitized; raises
    ValueError on a bad `expected` label, a non-opaque id, or a missing/empty
    marker file -- always BEFORE anything is emitted.
    """
    markers = load_markers(markers_path)  # fail-closed FIRST: emit nothing
    if not _CASE_ID_RE.match(str(case_id)):
        raise ValueError(
            "case id %r does not match the opaque fi-NNN shape (spec section 2: "
            "ids must carry zero per-case signal)" % (case_id,))
    if expected not in VALID_EXPECTED:
        raise ValueError(
            "bad expected label %r (must be one of %s); classify() would "
            "bucket a typo silently, so the emitter refuses it"
            % (expected, "/".join(VALID_EXPECTED)))
    case = {
        "id": case_id,
        "expected": expected,
        "artifact": _sanitize_with(artifact_text, markers),
        "rubric": _sanitize_with(rubric, markers),
        "origin": _sanitize_with(origin, markers),
        "target": "verifier",
        "requires": "judge",
        "type": "BEHAVIORAL",
        "suite": "fault_injection",
    }
    _blind_export_guard(case)
    return case
