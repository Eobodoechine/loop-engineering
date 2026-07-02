"""Tests for the PACE acceptor.

Run with:
    python3 -m pytest loop-team/evals/test_acceptor.py -q
"""
import os
import sys
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVALS_DIR)
import acceptor  # noqa: E402


class Decisions(unittest.TestCase):
    def test_clear_winner_accepts(self):
        # Candidate wins every discordant pair -> wealth climbs past 1/alpha.
        pairs = [(0, 1)] * 10
        r = acceptor.pace_accept(pairs)
        self.assertEqual(r.decision, "ACCEPT")
        self.assertGreaterEqual(r.wealth, r.threshold)
        # Anytime-valid: it stops the moment the threshold is crossed, so it
        # commits after the minimum winning streak rather than consuming all 10.
        self.assertGreaterEqual(r.discordant, 5)
        self.assertLessEqual(r.discordant, 10)

    def test_clear_loser_rejects(self):
        # Candidate loses every discordant pair -> wealth decays -> keep incumbent.
        r = acceptor.pace_accept([(1, 0)] * 10)
        self.assertEqual(r.decision, "REJECT")
        self.assertLess(r.wealth, 1.0)

    def test_concordant_ties_are_discarded(self):
        r = acceptor.pace_accept([(1, 1)] * 8 + [(0, 0)] * 8)
        self.assertEqual(r.decision, "REJECT")
        self.assertEqual(r.discordant, 0)
        self.assertIn("too few discordant", r.reason)

    def test_min_discordant_guard_blocks_early_accept(self):
        # With lam=0.9, five wins push wealth past the threshold, but the
        # min_discordant guard must refuse to commit on so few pairs.
        five_wins = [(0, 1)] * 5
        crossed = acceptor.pace_accept(five_wins, lam=0.9, min_discordant=1)
        self.assertEqual(crossed.decision, "ACCEPT")  # crosses when guard is low
        guarded = acceptor.pace_accept(five_wins, lam=0.9, min_discordant=10)
        self.assertEqual(guarded.decision, "REJECT")  # same wealth, blocked by guard
        self.assertIn("too few discordant", guarded.reason)

    def test_pairs_from_correctness_pairs_up(self):
        pairs = acceptor.pairs_from_correctness([True, False, True], [True, True, False])
        self.assertEqual(pairs, [(1, 1), (0, 1), (1, 0)])

    def test_pairs_from_correctness_rejects_mismatched_length(self):
        with self.assertRaises(ValueError):
            acceptor.pairs_from_correctness([1, 0], [1])

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            acceptor.pace_accept([(0, 1)], lam=1.5)
        with self.assertRaises(ValueError):
            acceptor.pace_accept([(0, 1)], alpha=0)


class FalseAcceptBound(unittest.TestCase):
    """Criterion #5 -- the anytime-valid guarantee, checked empirically."""

    def test_montecarlo_bound_holds(self):
        self.assertTrue(acceptor._selftest(trials=3000, n=250),
                        "H0 false-accept rate must stay <= alpha under peeking")


if __name__ == "__main__":
    unittest.main()
