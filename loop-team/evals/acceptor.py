#!/usr/bin/env python3
"""Loop Team -- PACE acceptor (anytime-valid commit test).

Decides whether to ACCEPT a candidate (e.g. an optimized role prompt) over the
incumbent. Naive "candidate scored higher on the reused eval set -> keep it" is
adaptive multiple testing: peek after enough rounds and you p-hack yourself into
committing changes that aren't real improvements (PACE reports 30-100% false
commits for greedy acceptance). This replaces that with a paired
testing-by-betting e-process.

Method (PACE, arXiv 2606.08106; safe-anytime-valid inference):
  - Evaluate incumbent and candidate on the SAME instances (paired).
  - Discard concordant pairs (both right or both wrong). For each DISCORDANT
    pair, w=1 if the candidate wins, else 0.
  - Bet: E <- E * (1 + lam*(2w-1)), starting E=1 (a test martingale).
  - ACCEPT the first time E >= 1/alpha (and after a minimum number of discordant
    pairs); otherwise REJECT on budget exhaustion -- fail-safe = keep incumbent.

Guarantee (Ville's inequality): under H0 "candidate no better," E is a
non-negative supermartingale from 1, so P(E ever >= 1/alpha) <= alpha at EVERY
stopping time. That bound -- holding under unlimited peeking -- is what defeats
dev-set p-hacking. Validate empirically with `python3 acceptor.py --selftest`
(Monte-Carlo false-accept rate <= alpha) before trusting it.

No third-party dependencies. The e-process math is standard; cross-check a
trajectory against `confseq`/`expectation` if you want an external reference.
"""
from collections import namedtuple

AcceptResult = namedtuple(
    "AcceptResult",
    "decision wealth discordant peeks threshold alpha lam reason trajectory")


def pace_accept(pairs, alpha=0.05, lam=0.5, min_discordant=5):
    """Run the paired betting acceptance test over (incumbent, candidate) score pairs.

    pairs: iterable of (incumbent_score, candidate_score). Scores may be 0/1
        correctness flags or any comparable numbers; equal scores are concordant
        ties and discarded.
    alpha: false-accept bound under H0 (default 0.05 -> threshold 1/alpha = 20).
    lam: bet fraction in (0,1) (default 0.5 -> win x1.5, loss x0.5).
    min_discordant: do not ACCEPT before this many discordant pairs (guards
        against committing on a tiny sample even if wealth spikes early).

    Returns an AcceptResult. decision == "ACCEPT" means commit the candidate.
    """
    if not 0 < lam < 1:
        raise ValueError("lam must be in (0, 1)")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    E = 1.0
    threshold = 1.0 / alpha
    discordant = 0
    peeks = 0
    trajectory = [1.0]
    for inc, cand in pairs:
        peeks += 1
        if cand == inc:
            continue  # concordant tie -> discard, no bet
        discordant += 1
        w = 1 if cand > inc else 0
        E *= (1 + lam * (2 * w - 1))
        trajectory.append(E)
        if E >= threshold and discordant >= min_discordant:
            return AcceptResult("ACCEPT", E, discordant, peeks, threshold,
                                alpha, lam, "wealth crossed 1/alpha", trajectory)
    reason = ("budget exhausted; wealth %.3f < %.1f" % (E, threshold)
              if discordant >= min_discordant
              else "too few discordant pairs (%d < %d)" % (discordant, min_discordant))
    return AcceptResult("REJECT", E, discordant, peeks, threshold,
                        alpha, lam, reason, trajectory)


def pairs_from_correctness(incumbent_correct, candidate_correct):
    """Zip two equal-length sequences of per-instance correctness (bool/0-1)
    into score pairs for pace_accept. Use when you already scored each model on
    the shared instances (e.g. two run_evals reports over the same cases)."""
    inc = list(incumbent_correct)
    cand = list(candidate_correct)
    if len(inc) != len(cand):
        raise ValueError("incumbent/candidate correctness must be paired (equal length)")
    return [(int(bool(a)), int(bool(b))) for a, b in zip(inc, cand)]


def _selftest(alpha=0.05, lam=0.5, trials=4000, n=300, seed=12345):
    """Monte-Carlo the false-accept bound (criterion #5) and a power sanity check.

    Under H0 the candidate is no better than the incumbent, so each discordant
    pair is symmetric (w ~ Bernoulli(0.5)); Ville bounds P(ACCEPT) <= alpha even
    while peeking every pair. We also check that a clearly-better candidate is
    usually accepted (power).
    """
    import random
    rng = random.Random(seed)

    def campaign(p_inc, p_cand):
        pairs = [(1 if rng.random() < p_inc else 0,
                  1 if rng.random() < p_cand else 0) for _ in range(n)]
        return pace_accept(pairs, alpha=alpha, lam=lam).decision == "ACCEPT"

    # H0: equal skill -> false-accept must be <= alpha.
    false_accepts = sum(campaign(0.6, 0.6) for _ in range(trials))
    far = false_accepts / trials
    # Power: a clearly better candidate -> mostly accepted.
    accepts_better = sum(campaign(0.5, 0.85) for _ in range(trials // 4))
    power = accepts_better / (trials // 4)

    print("PACE self-test  alpha=%.3f lam=%.2f n=%d trials=%d" % (alpha, lam, n, trials))
    print("  H0 false-accept rate: %.4f  (must be <= alpha=%.3f)" % (far, alpha))
    print("  power (p .50 vs .85): %.3f" % power)
    ok = far <= alpha
    print("  RESULT: %s" % ("OK -- bound holds" if ok else "FAIL -- bound violated"))
    return ok


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    print(__doc__)
