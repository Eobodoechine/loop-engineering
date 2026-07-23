#!/usr/bin/env python3
"""Run a role-under-test on an eval case and parse its verdict.

For a role-level eval case (`requires: "judge"`), the role's OWN verdict on the
case artifact is what we grade against the frozen `expected` label -- so to score
a candidate Verifier prompt we simply run the Verifier with that prompt on each
case and read its verdict. `make_role_judge` returns a `judge(case)` adapter that
plugs straight into `run_evals.run_suite(judge=...)`.
"""
import re

VERDICTS = ("FALSE-PASS", "FAIL", "PASS")  # order matters: FALSE-PASS contains PASS


def parse_verdict(text):
    """Extract PASS | FAIL | FALSE-PASS from a role's free-text response.

    Prefers an explicit 'VERDICT: X' line, taking the LAST one -- a model that
    thinks out loud may write a tentative verdict and then self-correct
    ("VERDICT: FAIL ... wait, recompute ... VERDICT: PASS"); its FINAL verdict is
    the answer, so the last match wins (taking the first mis-scored real models as
    failures -- a measurement bug that corrupted the independence findings).
    Falls back to the first bare verdict token. None if none found."""
    if not text:
        return None
    matches = re.findall(r"verdict\s*[:=]\s*(false[\s_-]*pass|false-pass|fail|pass)",
                         text, re.IGNORECASE)
    if matches:
        tok = matches[-1].upper().replace(" ", "-").replace("_", "-")
        return "FALSE-PASS" if tok.startswith("FALSE") else tok
    # Normalize unhyphenated "FALSE PASS"/"FALSE_PASS" so the fallback scan below
    # doesn't mis-read it as a bare PASS.
    up = re.sub(r"FALSE[ _]PASS", "FALSE-PASS", text.upper())
    best = None
    best_pos = len(up) + 1
    for v in VERDICTS:
        pos = up.find(v)
        if pos != -1 and pos < best_pos:
            best, best_pos = v, pos
    return best


def all_verdicts(text):
    """Every VERDICT token in the response, in order, normalized. More than one
    DISTINCT value means the model SELF-CORRECTED / was unstable mid-answer
    ("VERDICT: FAIL ... wait ... VERDICT: PASS"). A bare verdict hides that;
    surfacing it is how you tell a model gap from a measurement gap (taking the
    FIRST token here once cost a multi-hour false 'blind spot')."""
    if not text:
        return []
    out = []
    for tok in re.findall(r"verdict\s*[:=]\s*(false[\s_-]*pass|false-pass|fail|pass)",
                          text, re.IGNORECASE):
        t = tok.upper().replace(" ", "-").replace("_", "-")
        out.append("FALSE-PASS" if t.startswith("FALSE") else t)
    return out


def build_prompt(role_prompt, case):
    """Compose the instruction the role-under-test sees for one case.

    IMPORTANT: the case `rubric` and `expected` are GOLD-side grading metadata —
    they state what a correct verdict is — and must NOT be shown to the
    role-under-test, or the test leaks its own answer. The role sees only its own
    instructions + the artifact, exactly as in a real run; whether its prompt
    leads it to the right verdict from the artifact alone is the whole measurement.
    """
    return (
        role_prompt.strip()
        + "\n\n---\nApply your role to this single artifact and decide a verdict.\n"
        + "ARTIFACT:\n" + str(case.get("artifact", "")).strip() + "\n\n"
        + "Respond with exactly one line: `VERDICT: PASS`, `VERDICT: FAIL`, or "
        + "`VERDICT: FALSE-PASS`, then a one-sentence reason.")


_ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.IGNORECASE | re.DOTALL)


def build_prompt_answer_block(role_prompt, case):
    """Variant prompt format under A/B test: reason FIRST, then commit the final
    verdict inside an <answer> tag. The verdict is parsed ONLY from <answer>, so a
    model that thinks out loud and self-corrects in its reasoning cannot corrupt
    the parsed verdict (the principled version of the last-token fix). Same
    answer-isolation as build_prompt (no gold-side fields shown)."""
    return (
        role_prompt.strip()
        + "\n\n---\nApply your role to this single artifact and decide a verdict.\n"
        + "ARTIFACT:\n" + str(case.get("artifact", "")).strip() + "\n\n"
        + "First, reason step by step about the artifact. THEN give your FINAL "
        + "verdict on its own line inside an <answer> tag, exactly like:\n"
        + "<answer>VERDICT: PASS</answer>   (or VERDICT: FAIL, or VERDICT: FALSE-PASS)\n"
        + "Output exactly ONE <answer> block, as the LAST thing in your response.")


def parse_answer_block(text):
    """Parse the verdict from the LAST <answer>...</answer> block (the model's
    committed final answer); if no block is present, fall back to parse_verdict on
    the whole text (so a non-compliant response still yields something)."""
    if not text:
        return None
    blocks = _ANSWER_RE.findall(text)
    if blocks:
        return parse_verdict(blocks[-1])
    return parse_verdict(text)


def build_prompt_rrd(role_prompt, case):
    """Variant prompt format under A/B test: Recursive Rubric Decomposition (RRD).

    Instead of one holistic judgment over a flat rubric, instruct the judge to (1)
    DECOMPOSE its role into the concrete, atomic sub-criteria that actually apply to
    THIS artifact, (2) evaluate each sub-criterion against the artifact with cited
    evidence, then (3) AGGREGATE bottom-up to a single final verdict. The hypothesis
    (arXiv 2602.05125: flat rubrics hurt, RRD +17.7pp on JudgeBench) is that
    decomposition curbs the holistic-impression bias that makes a paranoid judge
    over-reject a sound artifact and a lenient one wave a subtle defect through.

    SAME answer-isolation as build_prompt (no gold-side `rubric`/`expected` shown) and
    SAME final-verdict contract: exactly ONE `VERDICT: X` line LAST, so parse_verdict
    (last-wins) reads it unchanged -- the decomposition is the ONLY variable vs
    build_prompt, not the answer format (that was a separate, already-rejected A/B).
    Sub-criteria are marked `- [name]: meets|fails|unclear` and must NOT use the word
    VERDICT, which is reserved for the single aggregate line."""
    return (
        role_prompt.strip()
        + "\n\n---\nApply your role to this single artifact by DECOMPOSING it, not by a "
        + "holistic impression.\n"
        + "ARTIFACT:\n" + str(case.get("artifact", "")).strip() + "\n\n"
        + "Work in three steps:\n"
        + "1. DECOMPOSE: list the specific, atomic sub-criteria from your role that "
        + "actually apply to THIS artifact (only the relevant ones).\n"
        + "2. EVALUATE each on its own line as `- [criterion]: meets|fails|unclear` "
        + "followed by the exact evidence from the artifact (quote it). Do NOT write "
        + "the word VERDICT on these lines.\n"
        + "3. AGGREGATE: any disqualifying sub-criterion that fails (or an unclear one "
        + "that the role requires confirmed) rejects the artifact; only if every "
        + "required sub-criterion is satisfied by cited evidence does it pass.\n\n"
        + "Then give your FINAL aggregate verdict as the LAST line, exactly one of: "
        + "`VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: FALSE-PASS`.")


def run_role(llm, role_prompt, case):
    """Run the role on a case; return its verdict string (or None)."""
    return parse_verdict(llm(build_prompt(role_prompt, case)))


def run_role_explained(llm, role_prompt, case):
    """Run the role and RETAIN its reasoning, not just the verdict -- so the
    orchestrator/verifier can read WHY before acting on it. A verdict without its
    reasoning is not verified: you can't tell whether a 'wrong' answer is a model
    gap, a spec gap, or OUR measurement/parse gap until you read the actual words.

    Returns {verdict, raw, all_verdicts, self_corrected}. `self_corrected` flags a
    response that changed its mind mid-answer (>1 distinct verdict) -- the exact
    pattern that, parsed by its first token, manufactured a fake model 'blind
    spot' and sent the loop in circles for hours."""
    raw = llm(build_prompt(role_prompt, case))
    verds = all_verdicts(raw)
    return {
        "verdict": parse_verdict(raw),
        "raw": raw,
        "all_verdicts": verds,
        "self_corrected": len(set(verds)) > 1,
    }


def make_role_judge(llm, role_prompt):
    """Return judge(case) -> verdict, for run_evals.run_suite(judge=...).

    Verdict-ONLY: use this only where the reasoning is genuinely not needed (e.g.
    run_evals' simple pending-case adapter). DECISION/measurement paths that act on
    a verdict must use make_explained_judge instead, so the 'why' is never
    discarded (enforced by verify_build.operational_invariants)."""
    def judge(case):
        return run_role(llm, role_prompt, case)
    return judge


def make_explained_judge(llm, role_prompt):
    """Return judge(case) -> {verdict, raw, all_verdicts, self_corrected}.

    The reasoning-capturing adapter for any path that ACTS on a verdict (the MVVP
    panel, the adversarial loop). A verdict is never consumed without its 'why',
    and self-correction is surfaced -- the structural fix for the failure where a
    self-corrected verdict, read as a bare label, was chased for hours."""
    def judge(case):
        return run_role_explained(llm, role_prompt, case)
    return judge
