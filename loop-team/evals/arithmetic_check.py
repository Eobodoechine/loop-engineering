#!/usr/bin/env python3
"""Deterministic arithmetic consistency check for verifier artifacts.

The measured weakness: an LLM judge recomputes a stated derived number only
*sometimes* — it caught "$41.10 x 40 x 52 = $85,888" on one run (true 85,488) and
missed it on another, and conversely caught/missed a dedupe subtraction depending
on the run. Recompute reliability is noisy in BOTH the terse and the reasoning
invocation. The robust fix is to NOT ask the LLM to multiply at all: extract the
numbers and check the arithmetic in code. The LLM judges soundness; this checks math.

Two checkers, both high-precision (fire only when the pattern is unambiguous):
  - check_equations: explicit `a op b (op c ...) = result` lines (annualization,
    fee rollups, dedupe subtractions stated as equations).
  - check_count_reconciliation: the no-equation list form (Source N / removed a /
    suppressed b / Final M) where the LLM is weakest -- M must equal N - (a+b+...).

`arithmetic_flags(text)` returns a list of human-readable mismatch strings. A
non-empty list is a deterministic FALSE-PASS signal (a confidently stated wrong
number). An empty list is NOT a pass -- it only means no stated arithmetic was
caught wrong; the LLM still judges everything else.
"""
import re

# A money/number token: optional $, digits with thousands commas, optional decimals.
_NUM = r"\$?\d[\d,]*(?:\.\d+)?"
_OPS = "×xX*+-"
# An equation: number, then >=1 (operator number), then = result.
_EQ_RE = re.compile(
    r"(" + _NUM + r"(?:\s*[" + _OPS + r"]\s*" + _NUM + r"){1,})\s*=\s*(" + _NUM + r")")
_TOKEN_RE = re.compile(r"[" + _OPS + r"]|" + _NUM)


def _val(tok):
    return float(tok.replace("$", "").replace(",", ""))


def _eval_left_to_right(lhs):
    """Evaluate a flat 'a op b op c' chain strictly left-to-right -- matches how
    reports state running math (rent + fee + fee; source - a - b; rate × hrs × 52).

    SKIPS (returns None) any chain that MIXES multiplicative (× *) with additive
    (+ -) operators: left-to-right would ignore precedence and could false-flag a
    correct PEMDAS expression (e.g. '80000 + 5000 × 2'). Precision over recall --
    a chain we can't trust we don't judge. All real report equations use a single
    operator class, so this loses nothing in practice."""
    toks = _TOKEN_RE.findall(lhs)
    if not toks or toks[0] in _OPS:
        return None
    ops = [t for t in toks if t in _OPS]
    if any(o in "×xX*" for o in ops) and any(o in "+-" for o in ops):
        return None  # mixed precedence -- not safe to evaluate left-to-right
    acc = _val(toks[0])
    i = 1
    while i < len(toks):
        op = toks[i]
        if op not in _OPS or i + 1 >= len(toks):
            return None
        v = _val(toks[i + 1])
        if op in "×xX*":
            acc *= v
        elif op == "+":
            acc += v
        elif op == "-":
            acc -= v
        i += 2
    return acc


def check_equations(text, tol=1.0):
    """Find explicit equations and verify each. Returns rows
    {expr, stated, computed, ok}. `tol` absorbs cent-rounding; a real defect (off
    by 3, off by $400) is far outside it."""
    rows = []
    for m in _EQ_RE.finditer(text):
        lhs, rhs = m.group(1), m.group(2)
        computed = _eval_left_to_right(lhs)
        if computed is None:
            continue
        stated = _val(rhs)
        rows.append({"expr": "%s = %s" % (lhs.strip(), rhs.strip()),
                     "stated": stated, "computed": round(computed, 2),
                     "ok": abs(computed - stated) <= tol})
    return rows


# Labels for the no-equation count list. Order matters: source first, then the
# subtracted buckets, then the final.
_SRC_RE = re.compile(r"(?im)^[^\n]*\b(source|received|rows in|import|input rows)\b[^\n]*?(" + _NUM + r")")
_CUT_RE = re.compile(
    r"(?im)^[^\n]*\b(removed|suppress\w*|duplicat\w*|invalid|dedup\w*|match\w*)\b[^\n]*?(" + _NUM + r")")
_FIN_RE = re.compile(r"(?im)^[^\n]*\b(final|launch audience|sendable|enrolled|queue|send count)\b[^\n]*?(" + _NUM + r")")


def check_count_reconciliation(text):
    """The no-equation list form (Source N / removed a / suppressed b / Final M).
    Returns {source, cuts, stated_final, computed_final, ok} or None when the
    pattern can't be unambiguously identified (then we stay silent -- precision
    over recall; the LLM still judges)."""
    src = _SRC_RE.search(text)
    fin = _FIN_RE.findall(text)
    cuts = _CUT_RE.findall(text)
    if not src or not fin or not cuts:
        return None
    source = _val(src.group(2))
    stated_final = _val(fin[-1][1])      # the last 'final' figure is the launch count
    cut_vals = [_val(c[1]) for c in cuts]
    computed_final = source - sum(cut_vals)
    return {"source": source, "cuts": cut_vals, "stated_final": stated_final,
            "computed_final": round(computed_final, 2),
            "ok": abs(computed_final - stated_final) <= 0.5}


def arithmetic_flags(text):
    """Public API: human-readable mismatch flags. Empty == no stated arithmetic
    caught wrong (NOT a pass signal). Non-empty == a deterministic FALSE-PASS cue."""
    flags = []
    for r in check_equations(text):
        if not r["ok"]:
            flags.append("stated arithmetic is wrong: '%s' -- left side computes to %s, not %s"
                         % (r["expr"], _fmt(r["computed"]), _fmt(r["stated"])))
    rec = check_count_reconciliation(text)
    if rec and not rec["ok"]:
        flags.append("count list does not reconcile: %s - %s = %s, but final is stated %s"
                     % (_fmt(rec["source"]), "+".join(_fmt(c) for c in rec["cuts"]),
                        _fmt(rec["computed_final"]), _fmt(rec["stated_final"])))
    return flags


def _fmt(n):
    return ("%d" % n) if float(n).is_integer() else ("%.2f" % n)


def guard_judge(inner_judge):
    """Wrap a judge(case)->verdict with a DETERMINISTIC arithmetic layer.

    The two-layer verifier in one function: if the case artifact contains a
    provably-wrong stated number (`arithmetic_flags` non-empty), return FALSE-PASS
    WITHOUT calling the LLM -- the math is incontestable and the LLM's recompute is
    the unreliable step we're routing around. Otherwise defer to `inner_judge`
    (the LLM handles everything arithmetic can't see). This is the wiring that makes
    `arithmetic_check` load-bearing in the judging path, not just advisory in
    verifier.md. Opt-in: a measurement of the LLM prompt ALONE should not wrap."""
    def judge(case):
        if arithmetic_flags(case.get("artifact", "")):
            return "FALSE-PASS"
        return inner_judge(case)
    return judge


if __name__ == "__main__":
    import sys
    txt = sys.stdin.read() if not sys.argv[1:] else open(sys.argv[1]).read()
    fl = arithmetic_flags(txt)
    print("\n".join(fl) if fl else "no arithmetic mismatch found")
    sys.exit(1 if fl else 0)
