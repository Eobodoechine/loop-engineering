#!/usr/bin/env python3
"""Loop Team -- MVVP judge validator (trust the gate before you use it).

Before any LLM judge's verdict is allowed to count in the eval suite, validate
it with the Minimum Viable Validation Protocol (Reliability without Validity,
arXiv 2606.19544). Raw exact-match agreement overstates a judge's skill by
33-41 points vs chance-corrected kappa, and a judge can be perfectly
self-consistent yet badly position-biased -- so all three checks must pass:

  1. Chance-corrected agreement   kappa(gold, judge) >= 0.60   (NOT exact-match)
  2. Position-swap bias audit      flip-rate          <= 0.10
  3. Test-retest reliability        kappa(pass1, pass2) > 0.95

The suite's frozen `expected` labels are the human gold, so the eval cases
double as the judge-validation calibration set. Pure-stdlib Cohen's kappa (no
sklearn needed for the math); cross-checked against scikit-learn in the tests.

CLI:  python3 judge_validate.py --selftest
"""
from collections import Counter

KAPPA_MIN = 0.60     # substantial agreement (Landis-Koch); >=0.80 near-gold
RETEST_MIN = 0.95    # near-deterministic re-judgment
FLIP_MAX = 0.10      # max tolerated position-driven verdict flips


def cohen_kappa(a, b):
    """Cohen's kappa for two equal-length sequences of categorical labels.

    kappa = (po - pe) / (1 - pe), where po is observed agreement and pe is the
    agreement expected by chance from each rater's marginal label frequencies.
    Labels may be any hashable (e.g. 'PASS'/'FAIL'/'FALSE-PASS').
    """
    a = list(a)
    b = list(b)
    if len(a) != len(b):
        raise ValueError("rater sequences must be equal length")
    n = len(a)
    if n == 0:
        raise ValueError("need at least one item")
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    labels = set(ca) | set(cb)
    pe = sum((ca.get(l, 0) / n) * (cb.get(l, 0) / n) for l in labels)
    if pe == 1.0:
        return 1.0  # both raters constant and identical -> perfect by convention
    return (po - pe) / (1 - pe)


def gwet_ac1(a, b):
    """Gwet's AC1 -- a chance-corrected agreement that does NOT collapse under
    class imbalance the way Cohen's kappa does (the "kappa paradox": when one
    verdict dominates, kappa can be near 0 even at 95%+ observed agreement). AC1
    uses pe = (1/(q-1)) * sum_k pi_k(1-pi_k), pi_k = the category's mean prevalence
    across both raters. Report it ALONGSIDE kappa -- on a balanced set they agree;
    where they diverge, the set is imbalanced and AC1 is the more trustworthy read.
    (arXiv 2603.06865 / 2606.00093.)"""
    a, b = list(a), list(b)
    n = len(a)
    if n == 0:
        raise ValueError("need at least one item")
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    cats = set(ca) | set(cb)
    q = len(cats)
    if q < 2:
        return 1.0  # single category, everyone agrees
    pi = {k: (ca.get(k, 0) + cb.get(k, 0)) / (2 * n) for k in cats}
    pe = sum(p * (1 - p) for p in pi.values()) / (q - 1)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def confusion(a, b):
    """Confusion counts as {(gold,judge): n} -- the full picture a scalar hides."""
    out = {}
    for x, y in zip(a, b):
        out[(x, y)] = out.get((x, y), 0) + 1
    return out


def exact_match(a, b):
    a, b = list(a), list(b)
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


def position_flip_rate(forward_winners, swapped_winners):
    """Fraction of pairwise judgments that are NOT order-invariant.

    forward_winners[i] / swapped_winners[i] = the item the judge picked when the
    pair was shown in original vs swapped order. If the judge is unbiased it
    picks the same ITEM regardless of position; a different pick is a
    position-driven flip. (Only relevant for pairwise judges.)
    """
    f, s = list(forward_winners), list(swapped_winners)
    if len(f) != len(s):
        raise ValueError("forward/swapped must be equal length")
    if not f:
        return 0.0
    return sum(1 for x, y in zip(f, s) if x != y) / len(f)


def validate_judge(gold, judge, retest=None, swap=None,
                   kappa_min=KAPPA_MIN, retest_min=RETEST_MIN, flip_max=FLIP_MAX):
    """Run MVVP. Returns a report dict; `certified` is True only if every
    PROVIDED check passes, and `complete` is True only if all three were run."""
    # Materialize once so generator inputs aren't exhausted by the first metric
    # (which previously left exact_match/len with an empty sequence -> ZeroDivision).
    gold, judge = list(gold), list(judge)
    if retest is not None:
        retest = list(retest)
    k = cohen_kappa(gold, judge)
    em = exact_match(gold, judge)
    ac1 = gwet_ac1(gold, judge)
    report = {
        "n": len(gold),
        "exact_match": em,
        "kappa": k,
        "ac1": ac1,                          # imbalance-robust agreement (report, not gated)
        "ac1_vs_kappa": ac1 - k,             # large gap => imbalanced set => trust AC1 more
        "confusion": confusion(gold, judge),
        "inflation_vs_exact_match": em - k,
        "kappa_pass": k >= kappa_min,
        "retest_kappa": None, "retest_pass": None,
        "flip_rate": None, "flip_pass": None,
        "reasons": [],
    }
    if k < kappa_min:
        report["reasons"].append("kappa %.3f < %.2f (exact-match %.3f overstates it)"
                                 % (k, kappa_min, em))
    if retest is not None:
        rk = cohen_kappa(judge, retest)
        report["retest_kappa"] = rk
        report["retest_pass"] = rk > retest_min
        if rk <= retest_min:
            report["reasons"].append("test-retest kappa %.3f <= %.2f" % (rk, retest_min))
    if swap is not None:
        fr = position_flip_rate(swap[0], swap[1])
        report["flip_rate"] = fr
        report["flip_pass"] = fr <= flip_max
        if fr > flip_max:
            report["reasons"].append("position-flip rate %.3f > %.2f (position-biased)"
                                     % (fr, flip_max))
    checks = [report["kappa_pass"]]
    if report["retest_pass"] is not None:
        checks.append(report["retest_pass"])
    if report["flip_pass"] is not None:
        checks.append(report["flip_pass"])
    report["complete"] = (retest is not None) and (swap is not None)
    report["certified"] = all(checks)
    return report


def print_report(r):
    print("MVVP judge validation  (n=%d)" % r["n"])
    print("  exact-match agreement : %.3f" % r["exact_match"])
    print("  cohen's kappa         : %.3f  (gate >= %.2f)  %s"
          % (r["kappa"], KAPPA_MIN, "PASS" if r["kappa_pass"] else "FAIL"))
    print("    -> exact-match overstates kappa by %.3f" % r["inflation_vs_exact_match"])
    if "ac1" in r:
        print("  gwet's AC1            : %.3f  (imbalance-robust; gap vs kappa = %.3f)"
              % (r["ac1"], r["ac1_vs_kappa"]))
    if r["retest_kappa"] is not None:
        print("  test-retest kappa     : %.3f  (gate > %.2f)   %s"
              % (r["retest_kappa"], RETEST_MIN, "PASS" if r["retest_pass"] else "FAIL"))
    if r["flip_rate"] is not None:
        print("  position-flip rate    : %.3f  (gate <= %.2f)  %s"
              % (r["flip_rate"], FLIP_MAX, "PASS" if r["flip_pass"] else "FAIL"))
    print("  complete (all 3 run)  : %s" % r["complete"])
    print("  CERTIFIED             : %s" % r["certified"])
    for why in r["reasons"]:
        print("    - %s" % why)


def _selftest():
    """Demonstrate MVVP on synthetic judges: a good one certifies; a
    position-biased one and a chance-level one are rejected."""
    gold = (["PASS", "FAIL", "FALSE-PASS"] * 10)
    # Good judge: agrees with gold except 2 slips; stable on retest.
    good = list(gold)
    good[3], good[7] = "PASS", "PASS"   # two honest slips vs gold -> kappa ~0.95
    retest = list(good)                  # low-temp judge reproduces identically
    # Unbiased pairwise audit: same item wins both orders (no flips).
    items = [("x%d" % i, "y%d" % i) for i in range(20)]
    fwd = [p[0] for p in items]
    swp = [p[0] for p in items]  # winner order-invariant
    ok = True

    print("== good judge ==")
    rg = validate_judge(gold, good, retest=retest, swap=(fwd, swp))
    print_report(rg)
    ok = ok and rg["certified"] and rg["complete"]

    print("\n== position-biased judge (always picks first slot) ==")
    swp_biased = [p[1] for p in items]  # swapped order -> different winner every time
    rb = validate_judge(gold, good, retest=retest, swap=(fwd, swp_biased))
    print_report(rb)
    ok = ok and (not rb["certified"]) and rb["flip_pass"] is False

    print("\n== chance-level judge (kappa ~ 0) ==")
    chance = ["PASS"] * len(gold)  # constant guess -> high exact-match, ~0 kappa
    rc = validate_judge(gold, chance)
    print_report(rc)
    ok = ok and (not rc["certified"])

    print("\nSELFTEST: %s" % ("OK" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    print(__doc__)
