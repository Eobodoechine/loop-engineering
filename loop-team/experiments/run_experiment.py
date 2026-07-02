#!/usr/bin/env python3
"""Loop Team -- Experiment harness ("does it really help?").

Given a baseline and one or more variants, score each on the SAME instances and
accept a variant over the baseline only if the PACE acceptor says it is
significantly better (anytime-valid, false-accept <= alpha). This is the engine
the Researcher's experiment specs feed into: it turns "we should try X" into a
measured ACCEPT/REJECT, and it refuses to adopt a variant just because it scored
higher on the reused suite (that is the dev-set p-hacking the acceptor stops).

Scoring is pluggable. The built-in `harness_scorer` scores a verify.py
implementation by the suite's per-case correctness, so you can A/B two harness
versions today. A task-success scorer over a held coding set (Phase 2+) drops in
the same way: any callable returning a per-instance correctness vector works,
as long as baseline and variants are scored on the SAME ordered instances.

No third-party dependencies. Reuses evals/acceptor.py + evals/run_evals.py.

CLI:
    python run_experiment.py --baseline path/to/verify.py \\
        --variant improved=path/to/verify_v2.py --variant other=path/to/v3.py
"""
import argparse
import os
import sys

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.normpath(os.path.join(EXP_DIR, "..", "evals"))
sys.path.insert(0, EVALS_DIR)
import acceptor  # noqa: E402
import run_evals  # noqa: E402


def harness_scorer(harness_path):
    """Per-case correctness of a verify.py implementation on the eval suite.

    1 if the gate handled the case correctly (a trap caught, a good case passed),
    0 otherwise. Pending judge cases are excluded so the vector is deterministic
    and comparable across harnesses.
    """
    report = run_evals.run_suite(harness=harness_path)
    return [1 if r["bucket"] in ("caught", "ok") else 0
            for r in report["rows"] if r["bucket"] != "pending"]


def decide(baseline_correct, variant_corrects, alpha=0.05, lam=0.5, min_discordant=5):
    """Pure decision step: PACE each variant against the baseline (paired).

    baseline_correct: list[int] per-instance correctness of the incumbent.
    variant_corrects: dict name -> list[int] (same length / order as baseline).
    Returns {winner, results}. winner is the accepted variant with the highest
    betting wealth, or None (keep baseline) if none cleared the bar.
    """
    results = {}
    for name, vc in variant_corrects.items():
        pairs = acceptor.pairs_from_correctness(baseline_correct, vc)
        results[name] = acceptor.pace_accept(pairs, alpha=alpha, lam=lam,
                                             min_discordant=min_discordant)
    accepted = {n: r for n, r in results.items() if r.decision == "ACCEPT"}
    winner = max(accepted, key=lambda n: accepted[n].wealth) if accepted else None
    return {"winner": winner, "results": results}


def run_experiment(baseline, variants, scorer=harness_scorer,
                   alpha=0.05, lam=0.5, min_discordant=5):
    """Score baseline + variants with `scorer`, then decide. `baseline` and the
    values of `variants` are whatever the scorer accepts (e.g. harness paths)."""
    base = scorer(baseline)
    variant_corrects = {name: scorer(v) for name, v in variants.items()}
    out = decide(base, variant_corrects, alpha=alpha, lam=lam,
                 min_discordant=min_discordant)
    out["baseline_score"] = sum(base)
    out["n_instances"] = len(base)
    out["variant_scores"] = {n: sum(v) for n, v in variant_corrects.items()}
    return out


def print_report(out):
    print("Experiment -- PACE-gated A/B  (n_instances=%d)" % out["n_instances"])
    print("  baseline correct: %d" % out["baseline_score"])
    for name, r in out["results"].items():
        print("  variant %-16s correct=%d  %s  (wealth=%.2f, discordant=%d) -- %s"
              % (name, out["variant_scores"][name], r.decision, r.wealth,
                 r.discordant, r.reason))
    print("  WINNER: %s" % (out["winner"] or "baseline (no variant cleared the bar)"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="baseline verify.py path")
    ap.add_argument("--variant", action="append", default=[], metavar="name=PATH",
                    help="a variant verify.py as name=path (repeatable)")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--min-discordant", type=int, default=5)
    args = ap.parse_args()
    variants = {}
    for spec in args.variant:
        if "=" not in spec:
            ap.error("--variant must be name=PATH, got %r" % spec)
        name, path = spec.split("=", 1)
        variants[name] = path
    out = run_experiment(args.baseline, variants, alpha=args.alpha, lam=args.lam,
                         min_discordant=args.min_discordant)
    print_report(out)
    sys.exit(0)


if __name__ == "__main__":
    main()
