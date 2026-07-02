#!/usr/bin/env python3
"""Loop Team -- Adversarial hard-case loop (ratchet the suite until it bites).

Part 2/3 of the "hard adversarial test cases" plan. The Researcher (Mode C, on a
DIFFERENT model) generates candidate cases grounded in a real failure taxonomy;
this harness decides which are actually HARD and worth freezing:

  for each candidate:
    judge_verdict    = MVVP-VALIDATED gold judge on the artifact   (e.g. Haiku)
    verifier_verdict = the VERIFIER-UNDER-TEST on the artifact      (verifier.md)
    gold_confirmed   = judge agrees with the candidate's proposed gold
    verifier_wrong   = verifier disagrees with the proposed gold (accept/reject)
    KEEP it iff gold_confirmed AND verifier_wrong  -> hard by construction.

Three roles stay distinct (a model never grades cases written to fool itself):
  case-author = Researcher Mode C   !=   verifier-under-test = verifier.md   !=
  gold-judge = gold_judge.md (the MVVP-certified judge from meta_validate.py).

Trust tiers (faithful to the plan's "validate-on-fact-gold -> extend-to-judgment"):
  - a candidate carrying an `objective_fact` is JUDGE-CONFIRMABLE -> kept-confirmed.
  - a pure-judgment candidate (no objective_fact) is kept-PROVISIONAL: the judge's
    opinion isn't yet certified on judgment cases, so it needs a human spot-check
    before it counts. We never silently promote a judgment case.

Metrics per round: adversarial yield (kept / candidates), verifier recall on
judge-confirmed traps, verifier precision on judge-confirmed goods. Across rounds
(history log), the Path-B trigger: when hand-edits stop reaching GREEN without
regressing (half-life ~ 1), the gradient is too rich for hand-edits -> switch to
GEPA (Path B).

Scoring is injectable (judge/verifier are callables case->verdict) so the glue is
FakeLLM-tested with no key. --live wires the real Haiku judge + verifier.md.

CLI:
    python3 adversarial_loop.py --selftest
    python3 adversarial_loop.py --live [--candidates DIR] [--verifier-model M]
"""
import json
import os
import sys

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATES_DIR = os.path.join(EVALS_DIR, "cases", "candidates")
ROLES_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "roles"))
OPTIMIZE_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))
HISTORY_LOG = os.path.join(EVALS_DIR, "adversarial_history.json")

sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPTIMIZE_DIR)

import meta_validate as mv     # noqa: E402  -- _collapse, load_role, build_live_judge
import role_runner             # noqa: E402  -- run_role(llm, prompt, case) -> verdict

_REJECT = ("FAIL", "FALSE-PASS")


def load_candidates(directory=CANDIDATES_DIR):
    cases = []
    if not os.path.isdir(directory):
        return cases
    for fn in sorted(os.listdir(directory)):
        if fn.endswith(".json"):
            with open(os.path.join(directory, fn), encoding="utf-8") as f:
                cases.append(json.load(f))
    return cases


def _verdict_of(result):
    """Normalize a judge/verifier result: an EXPLAINED dict (live path -- reasoning
    captured) or a bare verdict string (simple test stubs). Returns (verdict, raw,
    self_corrected)."""
    if isinstance(result, dict):
        return result.get("verdict"), result.get("raw", ""), bool(result.get("self_corrected"))
    return result, "", False


def score_candidate(case, judge, verifier):
    """Run one candidate through the gold judge and the verifier-under-test.

    `judge`/`verifier` are callables(case)-> an explained dict {verdict, raw,
    self_corrected} (the live, reasoning-capturing path via make_explained_judge)
    OR a bare verdict string (simple stubs). Returns a row describing whether the
    case is hard and keepable -- retaining each side's reasoning so a kept case's
    'why' is legible, never a bare label."""
    proposed = case.get("expected")
    artifact_case = {"artifact": case.get("artifact", "")}
    judge_verdict, judge_raw, judge_sc = _verdict_of(judge(artifact_case))
    verifier_verdict, verifier_raw, verifier_sc = _verdict_of(verifier(artifact_case))

    g = mv._collapse(proposed)
    gold_confirmed = mv._collapse(judge_verdict) == g and judge_verdict is not None
    verifier_wrong = mv._collapse(verifier_verdict) != g
    has_fact = bool(case.get("objective_fact"))
    needs_spotcheck = not has_fact

    if verifier_wrong and gold_confirmed and not needs_spotcheck:
        bucket = "kept_confirmed"
    elif verifier_wrong and (gold_confirmed or needs_spotcheck):
        # verifier missed it, but gold needs a human spot-check before it counts
        bucket = "kept_provisional"
    elif not verifier_wrong:
        bucket = "verifier_correct"        # not hard -- the verifier already nails it
    else:
        bucket = "gold_unconfirmed"        # judge rejects the proposed gold -> case suspect

    return {
        "id": case.get("id", "<unknown>"),
        "proposed": proposed,
        "judge": judge_verdict,
        "verifier": verifier_verdict,
        "gold_confirmed": gold_confirmed,
        "needs_spotcheck": needs_spotcheck,
        "verifier_wrong": verifier_wrong,
        "is_trap": g == "REJECT",
        "bucket": bucket,
        "failure_mode": case.get("failure_mode"),
        "why_hard": case.get("why_hard"),
        # reasoning retained so a kept case's 'why' is legible, not a bare label
        "judge_raw": judge_raw,
        "verifier_raw": verifier_raw,
        "self_corrected": judge_sc or verifier_sc,
    }


def run_round(candidates, judge, verifier):
    """Score a batch of candidates; return rows + round metrics."""
    rows = [score_candidate(c, judge, verifier) for c in candidates]
    n = len(rows)
    kept_confirmed = [r for r in rows if r["bucket"] == "kept_confirmed"]
    kept_provisional = [r for r in rows if r["bucket"] == "kept_provisional"]
    kept = kept_confirmed + kept_provisional

    # Recall/precision are computed ONLY over cases with TRUSTWORTHY gold: the
    # judge confirmed it AND it is objective-fact-backed (not a provisional
    # judgment case). The gold judge is MVVP-certified on objective facts only, so
    # a judgment case it happens to agree with cannot yet score the verifier -- it
    # waits for a human spot-check. Otherwise an uncertified opinion would inflate
    # or deflate the verifier's measured recall/precision.
    confirmed = [r for r in rows if r["gold_confirmed"] and not r["needs_spotcheck"]]
    conf_traps = [r for r in confirmed if r["is_trap"]]
    conf_goods = [r for r in confirmed if not r["is_trap"]]
    # verifier "caught" a trap = it rejected it (verifier not wrong on a trap)
    recall = (sum(1 for r in conf_traps if not r["verifier_wrong"]) / len(conf_traps)
              if conf_traps else None)
    precision = (sum(1 for r in conf_goods if not r["verifier_wrong"]) / len(conf_goods)
                 if conf_goods else None)

    return {
        "n_candidates": n,
        "kept": len(kept),
        "kept_confirmed": len(kept_confirmed),
        "kept_provisional": len(kept_provisional),
        "verifier_correct": sum(1 for r in rows if r["bucket"] == "verifier_correct"),
        "gold_unconfirmed": sum(1 for r in rows if r["bucket"] == "gold_unconfirmed"),
        "adversarial_yield": (len(kept) / n) if n else 0.0,
        "verifier_recall_on_confirmed_traps": recall,
        "verifier_precision_on_confirmed_goods": precision,
        "rows": rows,
    }


def pathb_triggered(round_outcomes, n=3):
    """Path-B (switch to GEPA) trigger: the last `n` hand-edit rounds all failed to
    reach GREEN (each `outcome` is True iff that round's hand-edit made the suite
    green without regressing). A standing plateau (hand-edit half-life ~ 1) means
    the gradient is too rich for hand-edits -- adopt GEPA on evidence, not vibes.
    Fewer than `n` rounds -> not enough evidence -> False."""
    if len(round_outcomes) < n:
        return False
    return not any(round_outcomes[-n:])


def hand_edit_half_life(round_outcomes):
    """Number of consecutive GREEN hand-edit rounds before the most recent failure
    (a rough 'how many cases one edit fixes before regressing'). Long = hand-edits
    still working; ~1 = plateau."""
    streak = 0
    for ok in reversed(round_outcomes):
        if ok:
            streak += 1
        else:
            break
    return streak


def print_round(report):
    print("Loop Team -- Adversarial hard-case round")
    print("=" * 64)
    print("roles: case-author=Researcher(ModeC)  verifier-under-test=verifier.md  "
          "gold-judge=gold_judge.md(MVVP-certified)")
    print("candidates: %d\n" % report["n_candidates"])
    print("  %-30s %-6s %-6s %-6s %s" % ("id", "gold", "judge", "verif", "bucket"))
    for r in report["rows"]:
        flag = ""
        if r["bucket"] == "kept_confirmed":
            flag = "  <== HARD (verifier wrong, gold confirmed)"
        elif r["bucket"] == "kept_provisional":
            flag = "  <== HARD? (verifier wrong; needs human spot-check)"
        elif r["bucket"] == "gold_unconfirmed":
            flag = "  (gold judge rejects proposed label -- case suspect)"
        print("  %-30s %-6s %-6s %-6s %-16s%s"
              % (r["id"], r["proposed"], r["judge"] or "-", r["verifier"] or "-",
                 r["bucket"], flag))
    print("-" * 64)
    print("  kept (hard): %d  (confirmed %d + provisional %d)   "
          "verifier already-correct: %d   gold-unconfirmed: %d"
          % (report["kept"], report["kept_confirmed"], report["kept_provisional"],
             report["verifier_correct"], report["gold_unconfirmed"]))
    print("  adversarial yield        : %.0f%%" % (report["adversarial_yield"] * 100))
    rec = report["verifier_recall_on_confirmed_traps"]
    pre = report["verifier_precision_on_confirmed_goods"]
    print("  verifier recall (traps)  : %s" % ("%.0f%%" % (rec * 100) if rec is not None else "n/a"))
    print("  verifier precision(goods): %s" % ("%.0f%%" % (pre * 100) if pre is not None else "n/a"))
    sc = sum(1 for r in report["rows"] if r.get("self_corrected"))
    if sc:
        print("  self-corrected verdicts  : %d  <-- READ these (judge/verifier changed its mind)" % sc)
    if report["kept"]:
        print("\n  HARD cases that beat the current verifier (the gradient) -- with the WHY:")
        for r in report["rows"]:
            if r["bucket"].startswith("kept"):
                print("   - %-28s %s" % (r["id"], r["failure_mode"] or ""))
                # surface the verifier's actual reasoning -- never act on a bare label
                why = " ".join((r.get("verifier_raw") or "").split())
                if why:
                    print("       verifier said: %s" % why[:180])


def _resolve_gold_judge():
    """Gold judge defaults to the CROSS-FAMILY OpenAI model when OPENAI_GOLD_MODEL
    is set (true judge≠verifier family separation); else the Anthropic Haiku judge."""
    m = os.environ.get("OPENAI_GOLD_MODEL")
    if m and os.environ.get("OPENAI_API_KEY"):
        return ("openai", m)
    return ("anthropic", "claude-haiku-4-5-20251001")


def run_live(candidates_dir=CANDIDATES_DIR, verifier_model="claude-sonnet-4-6",
             verifier_provider="anthropic", gold=None):
    candidates = load_candidates(candidates_dir)
    if not candidates:
        raise SystemExit("no candidate cases in %s -- run the Mode C generator first"
                         % candidates_dir)
    gold_provider, gold_model = gold or _resolve_gold_judge()
    gold_prompt = mv.load_role("gold_judge.md")
    verifier_prompt = mv.load_role("verifier.md")
    judge_llm = mv.build_live_judge(gold_model, provider=gold_provider)   # gold judge
    verifier_llm = mv.build_live_judge(verifier_model, provider=verifier_provider)
    print("gold judge: %s/%s   verifier-under-test: %s/%s%s"
          % (gold_provider, gold_model, verifier_provider, verifier_model,
             "   [CROSS-FAMILY]" if gold_provider != verifier_provider else ""))
    # Reasoning-capturing judges (make_explained_judge): a kept case's 'why' is
    # retained, never a bare label -- enforced by verify_build.operational_invariants.
    judge = role_runner.make_explained_judge(judge_llm, gold_prompt)
    verifier = role_runner.make_explained_judge(verifier_llm, verifier_prompt)
    report = run_round(candidates, judge, verifier)
    print_round(report)
    return 0


def _selftest():
    """FakeLLM glue check: a known mix of candidates buckets correctly."""
    from llm import FakeLLM
    # Build candidates with explicit expected gold + objective_fact presence.
    cases = [
        {"id": "trap-verifier-misses", "expected": "FAIL", "artifact": "ART_A",
         "objective_fact": "x", "failure_mode": "authoritative-unsourced"},
        {"id": "good-verifier-overrejects", "expected": "PASS", "artifact": "ART_B",
         "objective_fact": "y", "failure_mode": "looks-bad-but-valid"},
        {"id": "verifier-already-correct", "expected": "FAIL", "artifact": "ART_C",
         "objective_fact": "z", "failure_mode": "easy"},
        {"id": "judgment-no-fact", "expected": "FAIL", "artifact": "ART_D",
         "failure_mode": "sycophancy"},                    # no objective_fact -> provisional
        {"id": "gold-suspect", "expected": "FAIL", "artifact": "ART_E",
         "objective_fact": "w", "failure_mode": "mislabeled"},
    ]
    # Gold judge: confirms A,B,C,D's proposed gold; DISAGREES with E (suspect gold).
    judge_map = {"ART_A": "FAIL", "ART_B": "PASS", "ART_C": "FAIL",
                 "ART_D": "FAIL", "ART_E": "PASS"}
    # Verifier-under-test: WRONG on A (passes a trap), B (fails a good), D (passes a
    # trap), E (passes); CORRECT on C (fails the trap).
    verif_map = {"ART_A": "PASS", "ART_B": "FAIL", "ART_C": "FAIL",
                 "ART_D": "PASS", "ART_E": "PASS"}

    def judge(case):
        for k, v in judge_map.items():
            if k in case["artifact"]:
                return v
        return None

    def verifier(case):
        for k, v in verif_map.items():
            if k in case["artifact"]:
                return v
        return None

    report = run_round(cases, judge, verifier)
    print_round(report)
    ok = True
    by_id = {r["id"]: r for r in report["rows"]}
    ok &= by_id["trap-verifier-misses"]["bucket"] == "kept_confirmed"
    ok &= by_id["good-verifier-overrejects"]["bucket"] == "kept_confirmed"
    ok &= by_id["verifier-already-correct"]["bucket"] == "verifier_correct"
    ok &= by_id["judgment-no-fact"]["bucket"] == "kept_provisional"
    ok &= by_id["gold-suspect"]["bucket"] == "gold_unconfirmed"
    ok &= report["kept"] == 3 and report["kept_confirmed"] == 2 and report["kept_provisional"] == 1
    # recall over confirmed traps {A,C}: verifier wrong on A, right on C -> 1/2
    ok &= report["verifier_recall_on_confirmed_traps"] == 0.5
    # precision over confirmed goods {B}: verifier wrong on B -> 0/1
    ok &= report["verifier_precision_on_confirmed_goods"] == 0.0

    # Path-B trigger logic
    ok &= pathb_triggered([False, False, False]) is True
    ok &= pathb_triggered([True, False, False]) is False
    ok &= pathb_triggered([False, False]) is False        # too few rounds
    ok &= hand_edit_half_life([True, True, False]) == 0
    ok &= hand_edit_half_life([False, True, True]) == 2

    print("\nSELFTEST: %s" % ("OK" if ok else "FAIL"))
    return ok


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    if "--live" in sys.argv:
        cdir = CANDIDATES_DIR
        vmodel = "claude-sonnet-4-6"
        if "--candidates" in sys.argv:
            cdir = sys.argv[sys.argv.index("--candidates") + 1]
        if "--verifier-model" in sys.argv:
            vmodel = sys.argv[sys.argv.index("--verifier-model") + 1]
        sys.exit(run_live(candidates_dir=cdir, verifier_model=vmodel))
    print(__doc__)


if __name__ == "__main__":
    main()
