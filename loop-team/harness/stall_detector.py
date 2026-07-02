#!/usr/bin/env python3
"""Loop Team -- Stall detector: an OBJECTIVE "is the Coder stuck?" signal.

The orchestrator escalates a stuck bug to the Researcher (Coder-unblock mode)
instead of letting the Coder grind on the same failure. "Stuck" should not be a
judgment call -- it is mechanical: the same failure signature recurring N times
in a row. This normalizes a test/build failure into a stable signature (so the
same bug looks the same across runs even as line numbers and paths shift) and
reports when the last N attempts share it.

Pairs with: orchestrator.md (iterate/escalate step) + roles/researcher.md
(Coder-unblock mode). No third-party dependencies.
"""
import re
from collections import namedtuple

StallVerdict = namedtuple("StallVerdict", "stuck signature repeat_count")

_HEX = re.compile(r"0x[0-9a-fA-F]+")
_PATH = re.compile(r"(?:/[^\s:\"']+/)+([\w.\-]+)")   # /a/b/c/foo.py -> foo.py
# Strip line numbers only in a file-location context (file.ext:NN), NOT arbitrary
# colon-numbers in a message (e.g. a port `localhost:8080` or a status `failed:500`),
# which are part of what distinguishes one bug from another.
_LINENO = re.compile(r"(\.\w{1,5}):\d+")
_WS = re.compile(r"\s+")
# A real exception line (AssertionError, ValueError, ...). The trailing \b means
# benign 'Warning' lines like 'PytestUnraisableExceptionWarning' do NOT match
# (no word boundary after 'Exception'), so a warning can't mask the real error
# and collapse two distinct failures into one signature.
_EXC = re.compile(r"\b\w*(?:Error|Exception)\b", re.IGNORECASE)
# A pytest/unittest failure-DETAIL line (the 'E   ...' marker, a 'FAILED test::x'
# row, or 'FAIL:'/'ERROR:' header). Used only when no exception line is present.
_FAILLINE = re.compile(r"^(?:E\s|FAILED\b|FAIL:|ERROR:)", re.IGNORECASE)
# A summary count line ('1 failed in 0.2s', '=== 2 failed ===') -- noise; it is
# identical across different failures, so it must never become the signature.
_SUMMARY = re.compile(r"^[=\s]*\d+\s+(?:failed|passed|error)", re.IGNORECASE)


def _normalize_line(line):
    s = _HEX.sub("0xADDR", line.strip())
    s = _PATH.sub(r"\1", s)        # collapse absolute paths to basenames
    s = _LINENO.sub(r"\1", s)      # drop file line numbers (file.ext:NN -> file.ext)
    s = _WS.sub(" ", s).strip()
    return s


def error_signature(text):
    """Reduce a failure blob (traceback / test output) to a stable signature.

    Prefers the last line that names an error/assertion; falls back to the
    normalized last few lines. Two failures that differ only in paths, line
    numbers, or hex addresses produce the SAME signature.
    """
    if not text:
        return ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    # 1) Prefer a real exception line (most specific, distinguishes bugs).
    for ln in reversed(lines):
        if _EXC.search(ln):
            return _normalize_line(ln)
    # 2) Else a pytest/unittest failure-detail line, but NOT a summary count line.
    for ln in reversed(lines):
        if _FAILLINE.search(ln) and not _SUMMARY.search(ln):
            return _normalize_line(ln)
    # 3) No explicit failure line -> signature off the tail (still normalized).
    return _normalize_line(" / ".join(lines[-3:]))


def is_stuck(signatures, threshold=2):
    """Given failure signatures in attempt order (oldest -> newest), report
    whether the Coder is stuck: the last `threshold` attempts share a non-empty
    signature. Returns StallVerdict(stuck, signature, repeat_count).

    A different signature on the latest attempt means progress (the bug changed),
    so the streak resets -- only an unchanging failure escalates.
    """
    if threshold < 1:
        raise ValueError("threshold must be >= 1")
    sigs = list(signatures)
    if not sigs:
        return StallVerdict(False, None, 0)
    last = sigs[-1]
    if not last:
        return StallVerdict(False, last, 0)
    # repeat_count is always the true trailing run of `last` (not len(sigs)).
    count = 0
    for s in reversed(sigs):
        if s == last:
            count += 1
        else:
            break
    return StallVerdict(count >= threshold, last, count)


def stuck_from_outputs(outputs, threshold=2):
    """Convenience: take raw failure outputs (oldest -> newest), signature each,
    and report the stall verdict."""
    return is_stuck([error_signature(o) for o in outputs], threshold=threshold)


if __name__ == "__main__":
    import sys
    # Read failure blobs separated by a line of '==='; report the verdict.
    blobs = sys.stdin.read().split("\n===\n") if not sys.stdin.isatty() else []
    v = stuck_from_outputs(blobs)
    print("stuck=%s repeat=%d signature=%r" % (v.stuck, v.repeat_count, v.signature))
    sys.exit(0)
