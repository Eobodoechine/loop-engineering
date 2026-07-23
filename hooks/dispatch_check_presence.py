"""dispatch_check_presence.py -- detects whether a dispatch_check JSON block
(orchestrator.md's required pre-dispatch structure) is present in the CURRENT
assistant turn's text, for advisory logging only (H-BLOB-DISPLAY-1). Never
returns a blocking verdict -- presence/absence is a fact this module reports,
not a decision it makes."""
import json, re

_DISPATCH_CHECK_RE = re.compile(r'"dispatch_check"\s*:\s*\{', re.I)
_REQUIRED_KEYS = ("task", "role", "why_this_role", "why_not_other")


def find_dispatch_check_blocks(text):
    """Return a list of parsed dispatch_check dicts found in `text` (usually
    zero or one, but never assume exactly one). v1 used hand-rolled brace-
    depth counting with NO JSON-string-literal awareness -- a literal '{'/'}'
    character inside any of the 4 free-text prose values (entirely plausible
    prose, e.g. a why_this_role justification quoting a snippet) desynced the
    counter and silently dropped a real, well-formed block. v2 uses the
    stdlib's own JSONDecoder.raw_decode, which is already quote/escape-aware
    -- smaller and correct, not a patched version of the same bug class."""
    found = []
    decoder = json.JSONDecoder()
    for m in _DISPATCH_CHECK_RE.finditer(text):
        start = text.index("{", m.end() - 1)
        try:
            obj, _end = decoder.raw_decode(text, start)
        except Exception:
            continue
        found.append(obj)
    return found


def evaluate_presence(text):
    """Returns a dict: {"present": bool, "complete": bool, "missing_keys":
    [...]}. present=True iff at least one dispatch_check block parses at
    all. complete=True iff at least one parsed block has all 4 required keys
    present AND non-empty (after .strip() for string values)."""
    blocks = find_dispatch_check_blocks(text)
    if not blocks:
        return {"present": False, "complete": False, "missing_keys": list(_REQUIRED_KEYS)}
    best_missing = list(_REQUIRED_KEYS)
    for b in blocks:
        missing = [
            k for k in _REQUIRED_KEYS
            if not (isinstance(b.get(k), str) and b.get(k).strip())
        ]
        if len(missing) < len(best_missing):
            best_missing = missing
        if not missing:
            return {"present": True, "complete": True, "missing_keys": []}
    return {"present": True, "complete": False, "missing_keys": best_missing}
