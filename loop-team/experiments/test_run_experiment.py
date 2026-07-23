"""Tests for the experiment harness.

Unit tests use synthetic correctness vectors (full control over discordant
pairs). One integration test scores the REAL verify.py against a guard-removed
copy on the live suite, proving the harness composes with run_evals + acceptor.

Run with:
    python3 -m pytest loop-team/experiments/test_run_experiment.py -q
"""
import os
import sys
import tempfile
import unittest

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXP_DIR)
import run_experiment as rx  # noqa: E402


class Decide(unittest.TestCase):
    def test_clearly_better_variant_is_accepted_and_wins(self):
        # Baseline misses 15 cases the variant catches -> 15 discordant wins.
        base = [0] * 15 + [1] * 10
        variant = [1] * 25
        out = rx.decide(base, {"better": variant})
        self.assertEqual(out["results"]["better"].decision, "ACCEPT")
        self.assertEqual(out["winner"], "better")

    def test_worse_variant_is_rejected(self):
        base = [1] * 25
        variant = [0] * 15 + [1] * 10  # loses 15 discordant pairs
        out = rx.decide(base, {"worse": variant})
        self.assertEqual(out["results"]["worse"].decision, "REJECT")
        self.assertIsNone(out["winner"])

    def test_equivalent_variant_not_accepted(self):
        base = [1, 0, 1, 0, 1] * 5
        out = rx.decide(base, {"same": list(base)})
        self.assertEqual(out["results"]["same"].decision, "REJECT")  # 0 discordant
        self.assertIsNone(out["winner"])

    def test_best_accepted_variant_wins_among_several(self):
        base = [0] * 20 + [1] * 5
        strong = [1] * 25            # wins all 20 discordant
        weak = [0] * 12 + [1] * 13   # wins 8 discordant, loses none -> may accept later
        out = rx.decide(base, {"strong": strong, "weak": weak})
        self.assertEqual(out["winner"], "strong")
        self.assertGreaterEqual(out["results"]["strong"].wealth,
                                out["results"]["weak"].wealth)


class IntegrationOnRealSuite(unittest.TestCase):
    """Score the real verify.py vs a guard-removed copy on the live suite."""

    def _broken_harness(self):
        src = os.path.normpath(os.path.join(EXP_DIR, "..", "harness", "verify.py"))
        with open(src, encoding="utf-8") as f:
            code = f.read()
        broken = code.replace(
            "def _zero_tests(output, code):",
            "def _zero_tests(output, code):\n    return False  # disabled")
        fd, path = tempfile.mkstemp(suffix="_verify_broken.py")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(broken)
        self.addCleanup(os.remove, path)
        return path

    def test_broken_variant_is_not_accepted_over_real(self):
        # The broken harness misses zero-test-green; it must never be accepted
        # as an improvement over the real one.
        real = os.path.normpath(os.path.join(EXP_DIR, "..", "harness", "verify.py"))
        out = rx.run_experiment(real, {"guard_removed": self._broken_harness()})
        self.assertEqual(out["results"]["guard_removed"].decision, "REJECT")
        self.assertIsNone(out["winner"])

    def test_real_scores_at_least_as_high_as_broken(self):
        real = os.path.normpath(os.path.join(EXP_DIR, "..", "harness", "verify.py"))
        out = rx.run_experiment(self._broken_harness(), {"real": real})
        # The real harness catches a trap the broken one misses, so it scores
        # strictly higher -- even if the single discordant pair is too few to
        # cross the acceptance bar (honest "insufficient evidence").
        self.assertGreater(out["variant_scores"]["real"], out["baseline_score"])


if __name__ == "__main__":
    unittest.main()
