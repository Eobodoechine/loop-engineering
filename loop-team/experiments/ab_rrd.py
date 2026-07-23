#!/usr/bin/env python3
"""A/B: Recursive Rubric Decomposition (RRD) vs the flat one-shot judge prompt (PACE-gated).

Tests dossier pick C2 (arXiv 2602.05125: flat LLM rubrics HURT, GPT-4o 55.6->42.9%;
RRD +17.7pp on JudgeBench -- the largest measured lift in the prompting dossier).

The ONLY variable is the rubric structure -- both arms use the SAME verifier role
prompt, the SAME judge model, the SAME cases, and the SAME parser (parse_verdict,
last-wins). The answer FORMAT is held constant (a single trailing `VERDICT:` line),
so this does not re-run the already-rejected <answer>-block A/B:
  - baseline: build_prompt      -> one holistic judgment over the flat rubric
  - rrd:      build_prompt_rrd   -> decompose the role into per-artifact sub-criteria,
              evaluate each with cited evidence, aggregate bottom-up to one verdict

Scored on the BALANCED verifier-target cases (traps AND goods) -- NOT the saturated
objective-fact cases, where both arms ace everything and no gradient exists. The
hypothesis is that decomposition curbs the holistic-impression bias that makes a
paranoid verifier over-reject sound GOOD artifacts while still catching traps.

Adoption into verifier.md is a SEPARATE, diff-reviewed change, made ONLY if PACE
returns a significant win -- no adoption on the headline number alone.

CLI:
    python3 ab_rrd.py --selftest                 # FakeLLM, no key
    ANTHROPIC_API_KEY=... python3 ab_rrd.py --live [--model M] [--provider P]
    OPENAI_API_KEY=...    python3 ab_rrd.py --live --provider openai --model gpt-...
"""
import os
import sys

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "evals"))
OPT_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)
sys.path.insert(0, EXP_DIR)

import meta_validate as mv       # noqa: E402  -- _collapse, load_role, build_live_judge
import optimize_verifier as ov   # noqa: E402  -- verifier_cases (the balanced suite)
import role_runner               # noqa: E402
import run_experiment            # noqa: E402  -- decide() = PACE pairing

# Both arms parse identically (parse_verdict, last-wins) -- only the BUILDER differs.
FORMATS = {
    "baseline": (role_runner.build_prompt, role_runner.parse_verdict),
    "rrd": (role_runner.build_prompt_rrd, role_runner.parse_verdict),
}


def run_format(llm, role_prompt, cases, builder, parser):
    """Run one prompt format over the cases; return per-case diagnostic rows.

    Correctness is the gate-as-rejector binary (`_collapse`): a trap (expected
    FAIL/FALSE-PASS) is correct on ANY rejection; a good case (expected PASS) is
    correct only on PASS -- identical to run_evals.classify, so this measures the
    same thing the suite does, just across two prompt arms."""
    rows = []
    for c in cases:
        raw = llm(builder(role_prompt, {"artifact": c.get("artifact", "")}))
        verdict = parser(raw)
        rows.append({
            "id": c["id"],
            "gold": c["expected"],
            "verdict": verdict,
            "correct": mv._collapse(verdict) == mv._collapse(c["expected"]),
            "parse_failed": verdict is None,
            "self_corrected": len(set(role_runner.all_verdicts(raw or ""))) > 1,
        })
    return rows


def _correctness(rows):
    return [1 if r["correct"] else 0 for r in rows]


def run_ab(llm, role_prompt, cases, min_discordant=5):
    """Score both formats on the same judge/cases; PACE-decide on accuracy."""
    results = {fmt: run_format(llm, role_prompt, cases, b, p)
               for fmt, (b, p) in FORMATS.items()}
    decision = run_experiment.decide(
        _correctness(results["baseline"]),
        {"rrd": _correctness(results["rrd"])},
        min_discordant=min_discordant)
    return results, decision


def _diag(rows):
    n = len(rows)
    goods = [r for r in rows if r["gold"] == "PASS"]
    traps = [r for r in rows if r["gold"] != "PASS"]
    return {
        "correct": sum(1 for r in rows if r["correct"]),
        "good_correct": sum(1 for r in goods if r["correct"]),
        "good_n": len(goods),
        "trap_correct": sum(1 for r in traps if r["correct"]),
        "trap_n": len(traps),
        "parse_failed": sum(1 for r in rows if r["parse_failed"]),
        "self_corrected": sum(1 for r in rows if r["self_corrected"]),
        "n": n,
    }


def print_ab(results, decision, cases):
    print("A/B -- Recursive Rubric Decomposition vs flat one-shot judge prompt")
    print("=" * 64)
    for fmt in FORMATS:
        d = _diag(results[fmt])
        print("  %-9s correct=%d/%d  (traps %d/%d, goods %d/%d)  parse-fail=%d  self-corr=%d"
              % (fmt, d["correct"], d["n"], d["trap_correct"], d["trap_n"],
                 d["good_correct"], d["good_n"], d["parse_failed"], d["self_corrected"]))
    print("-" * 64)
    r = decision["results"]["rrd"]
    print("  PACE (accuracy): %s  (wealth=%.2f, discordant=%d) -- %s"
          % (r.decision, r.wealth, r.discordant, r.reason))
    print("  WINNER: %s" % (decision["winner"] or "baseline (no significant accuracy gain)"))
    diffs = [(b["id"], b["gold"], b["verdict"], a["verdict"])
             for b, a in zip(results["baseline"], results["rrd"])
             if b["verdict"] != a["verdict"]]
    if diffs:
        print("  format disagreements (id [gold]: baseline -> rrd):")
        for cid, gold, bv, av in diffs:
            print("    %-34s [%s] %s -> %s" % (cid, gold, bv, av))


# Both arms MUST get the same, GENEROUS token budget. The baseline emits one
# verdict line and never truncates; RRD emits a multi-step decomposition (~400-700
# words) and WILL truncate before its final `VERDICT:` line under a tight cap -- a
# truncated RRD response either parses to None or has parse_verdict fall back to an
# early sub-criterion token, manufacturing fake parse-failures and trap LEAKS. The
# first live run used build_live_judge's default max_tokens=512 and measured that
# truncation, NOT the rubric structure (baseline 39/39 vs RRD 22/39 with 3 None);
# raising the cap to 2000 made every probed RRD verdict correct. So the A/B holds
# the token budget EQUAL and generous -- the format is the only variable.
FAIR_MAX_TOKENS = 2000


def run_live(model="claude-sonnet-4-6", provider="anthropic", max_tokens=FAIR_MAX_TOKENS):
    cases = ov.verifier_cases()
    if not cases:
        raise SystemExit("no verifier-target cases found")
    role_prompt = mv.load_role("verifier.md")
    llm = mv.build_live_judge(model, provider=provider, max_tokens=max_tokens)
    print("max_tokens=%d (equal for both arms)" % max_tokens)
    goods = sum(1 for c in cases if c["expected"] == "PASS")
    print("judge: %s/%s   verifier-target cases: %d (%d traps, %d goods)\n"
          % (provider, model, len(cases), len(cases) - goods, goods))
    results, decision = run_ab(llm, role_prompt, cases)
    print_ab(results, decision, cases)
    return 0


def _selftest():
    """FakeLLM mechanics (no key): the harness runs, scores both arms with the
    gate-as-rejector binary, and the PACE decision reflects a real difference.

    The discrimination case models RRD's hypothesized advantage directly: a paranoid
    judge that holistically REJECTS sound GOOD artifacts on the flat prompt, but whose
    forced per-criterion decomposition finds every required criterion met and so
    correctly PASSes them. RRD correctness must exceed baseline here -- proving the
    harness can SEE a gain (so a live tie is a real tie, not a blind harness)."""
    cases = ov.verifier_cases()
    role_prompt = mv.load_role("verifier.md")
    from llm import FakeLLM
    ok = True

    # (1) An accurate judge on both arms -> both score full; 0 discordant -> REJECT
    #     (no evidence of a difference) is the correct PACE call.
    def correct_judge(prompt):
        for c in cases:
            if c["artifact"] in prompt:
                return "...\nVERDICT: %s" % c["expected"]
        return "VERDICT: PASS"
    results, decision = run_ab(FakeLLM(correct_judge), role_prompt, cases)
    base_ok = _diag(results["baseline"])["correct"] == len(cases)
    rrd_ok = _diag(results["rrd"])["correct"] == len(cases)
    ok = ok and base_ok and rrd_ok
    ok = ok and decision["results"]["rrd"].decision == "REJECT"  # 0 discordant
    print("(1) both-accurate: baseline=%d rrd=%d decision=%s"
          % (_diag(results["baseline"])["correct"], _diag(results["rrd"])["correct"],
             decision["results"]["rrd"].decision))

    # (2) Discrimination: a paranoid judge that over-rejects GOOD artifacts on the
    #     flat prompt but, when forced to decompose (the prompt contains "DECOMPOSE"),
    #     correctly PASSes them. RRD correctness must beat baseline.
    def paranoid_judge(prompt):
        is_rrd = "DECOMPOSE" in prompt
        for c in cases:
            if c["artifact"] in prompt:
                if c["expected"] == "PASS" and not is_rrd:
                    return "VERDICT: FALSE-PASS"   # flat arm: paranoid over-rejection
                return "VERDICT: %s" % c["expected"]
        return "VERDICT: PASS"
    results2, _ = run_ab(FakeLLM(paranoid_judge), role_prompt, cases)
    base_correct = _diag(results2["baseline"])["correct"]
    rrd_correct = _diag(results2["rrd"])["correct"]
    ok = ok and rrd_correct > base_correct
    print("(2) paranoid-over-rejection trap: baseline correct=%d  rrd correct=%d"
          % (base_correct, rrd_correct))

    print("\nSELFTEST: %s" % ("OK" if ok else "FAIL"))
    return ok


def _flag_value(argv, flag):
    """Return the value following `flag` in argv; exit with a clean usage
    error (not an IndexError) if `flag` is present but has no following
    value (e.g. the flag is the last token on the command line)."""
    i = argv.index(flag)
    if i + 1 >= len(argv):
        sys.exit("error: %s requires a value" % flag)
    return argv[i + 1]


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    if "--live" in sys.argv:
        model = "claude-sonnet-4-6"
        provider = "anthropic"
        max_tokens = FAIR_MAX_TOKENS
        if "--model" in sys.argv:
            model = _flag_value(sys.argv, "--model")
        if "--provider" in sys.argv:
            provider = _flag_value(sys.argv, "--provider")
        if "--max-tokens" in sys.argv:
            max_tokens = int(_flag_value(sys.argv, "--max-tokens"))
        sys.exit(run_live(model=model, provider=provider, max_tokens=max_tokens))
    print(__doc__)


if __name__ == "__main__":
    main()
