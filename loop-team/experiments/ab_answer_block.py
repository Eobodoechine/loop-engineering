#!/usr/bin/env python3
"""A/B: the <answer>-block judge format vs the current one-line format (PACE-gated).

Tests Candidate-1 from the June-2026 prompting dossier. Same judge model + same
cases for both arms:
  - baseline:     build_prompt        + parse_verdict        (one line, last-token)
  - answer_block: build_prompt_answer_block + parse_answer_block (reason, then a
                  committed <answer>VERDICT: X</answer>, parsed only from the block)

It reports BOTH:
  1. accuracy vs gold -> run_experiment.decide (PACE; adopt only on a significant win)
  2. a parse-robustness delta -- parse-failures + self-correction rate -- which is
     the format's hypothesized real advantage even when accuracy ties.

Adoption into verifier.md / gold_judge.md is a SEPARATE, diff-reviewed change, made
ONLY if this experiment justifies it.

CLI:
    python3 ab_answer_block.py --selftest                 # FakeLLM, no key
    ANTHROPIC_API_KEY=... python3 ab_answer_block.py --live [--model M] [--provider P]
"""
import os
import sys

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "evals"))
OPT_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)
sys.path.insert(0, EXP_DIR)

import meta_validate as mv       # noqa: E402  -- _collapse, load_objective_cases, build_live_judge, load_role
import role_runner               # noqa: E402
import run_experiment            # noqa: E402  -- decide() = PACE pairing

FORMATS = {
    "baseline": (role_runner.build_prompt, role_runner.parse_verdict),
    "answer_block": (role_runner.build_prompt_answer_block, role_runner.parse_answer_block),
}


def run_format(llm, role_prompt, cases, builder, parser):
    """Run one prompt format over the cases; return per-case diagnostic rows."""
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
        {"answer_block": _correctness(results["answer_block"])},
        min_discordant=min_discordant)
    return results, decision


def _diag(rows):
    n = len(rows)
    return {
        "correct": sum(1 for r in rows if r["correct"]),
        "parse_failed": sum(1 for r in rows if r["parse_failed"]),
        "self_corrected": sum(1 for r in rows if r["self_corrected"]),
        "n": n,
    }


def print_ab(results, decision, cases):
    print("A/B -- <answer>-block vs one-line judge format")
    print("=" * 60)
    for fmt in FORMATS:
        d = _diag(results[fmt])
        print("  %-13s correct=%d/%d  parse-failures=%d  self-corrected=%d"
              % (fmt, d["correct"], d["n"], d["parse_failed"], d["self_corrected"]))
    print("-" * 60)
    r = decision["results"]["answer_block"]
    print("  PACE (accuracy): %s  (wealth=%.2f, discordant=%d) -- %s"
          % (r.decision, r.wealth, r.discordant, r.reason))
    print("  WINNER: %s" % (decision["winner"] or "baseline (no significant accuracy gain)"))
    # per-case disagreements between the two formats (where the choice matters)
    diffs = [(b["id"], b["verdict"], a["verdict"])
             for b, a in zip(results["baseline"], results["answer_block"])
             if b["verdict"] != a["verdict"]]
    if diffs:
        print("  format disagreements (id: baseline -> answer_block):")
        for cid, bv, av in diffs:
            print("    %-26s %s -> %s" % (cid, bv, av))


def run_live(model="claude-sonnet-4-6", provider="anthropic"):
    cases = mv.load_objective_cases()
    if not cases:
        raise SystemExit("no objective-fact cases found")
    role_prompt = mv.load_role("gold_judge.md")
    llm = mv.build_live_judge(model, provider=provider)
    print("judge: %s/%s   cases: %d\n" % (provider, model, len(cases)))
    results, decision = run_ab(llm, role_prompt, cases)
    print_ab(results, decision, cases)
    return 0


def _selftest():
    """FakeLLM mechanics (no key): the harness runs, scores both formats, and the
    PACE decision reflects a variant that parses a case the baseline misparses."""
    from llm import FakeLLM
    cases = mv.load_objective_cases()
    role_prompt = mv.load_role("gold_judge.md")
    ok = True

    # (1) Both formats correct -> both score full; decide returns a result (REJECT on
    #     0 discordant is correct: no evidence of a difference).
    def correct_judge(prompt):
        for c in cases:
            if c["artifact"] in prompt:
                v = c["expected"]
                # answer_block format if the prompt asked for a block
                if "<answer>" in prompt:
                    return "some reasoning...\n<answer>VERDICT: %s</answer>" % v
                return "VERDICT: %s -- reason" % v
        return "VERDICT: PASS"
    results, decision = run_ab(FakeLLM(correct_judge), role_prompt, cases)
    base_ok = _diag(results["baseline"])["correct"] == len(cases)
    var_ok = _diag(results["answer_block"])["correct"] == len(cases)
    ok = ok and base_ok and var_ok
    ok = ok and decision["results"]["answer_block"].decision == "REJECT"  # 0 discordant
    print("(1) both-correct: baseline=%d var=%d decision=%s"
          % (_diag(results["baseline"])["correct"], _diag(results["answer_block"])["correct"],
             decision["results"]["answer_block"].decision))

    # (2) Discrimination: a judge whose ONE-LINE output buries a hypothetical second
    #     verdict the last-token parse mis-reads, but whose <answer> block is clean.
    #     answer_block should be >= baseline in correctness on that case.
    target = cases[0]
    def trappy_judge(prompt):
        if target["artifact"] in prompt:
            if "<answer>" in prompt:
                return "reasoning\n<answer>VERDICT: %s</answer>" % target["expected"]
            # one-line arm: correct verdict, then a trailing hypothetical that
            # last-token parse will wrongly grab (the failure mode the block fixes)
            wrong = "PASS" if target["expected"] != "PASS" else "FAIL"
            return ("VERDICT: %s -- correct. Note: if it were otherwise it would be "
                    "VERDICT: %s." % (target["expected"], wrong))
        for c in cases:
            if c["artifact"] in prompt:
                v = c["expected"]
                return ("reasoning\n<answer>VERDICT: %s</answer>" % v
                        if "<answer>" in prompt else "VERDICT: %s" % v)
        return "VERDICT: PASS"
    results2, _ = run_ab(FakeLLM(trappy_judge), role_prompt, cases)
    base_correct = _diag(results2["baseline"])["correct"]
    var_correct = _diag(results2["answer_block"])["correct"]
    ok = ok and var_correct > base_correct  # the block recovered the trapped case
    print("(2) trailing-hypothetical trap: baseline correct=%d  answer_block correct=%d"
          % (base_correct, var_correct))

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
        if "--model" in sys.argv:
            model = _flag_value(sys.argv, "--model")
        if "--provider" in sys.argv:
            provider = _flag_value(sys.argv, "--provider")
        sys.exit(run_live(model=model, provider=provider))
    print(__doc__)


if __name__ == "__main__":
    main()
