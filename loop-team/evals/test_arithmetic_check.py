"""Tests for the deterministic arithmetic checker (no API).

It must catch a stated-wrong derived number (the LLM's noisy blind spot) and stay
SILENT on clean math (a false flag on a good artifact would defeat the point).

Run with: python3 -m pytest loop-team/evals/test_arithmetic_check.py -q
"""
import os
import sys
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVALS_DIR)
import arithmetic_check as ac  # noqa: E402


class Equations(unittest.TestCase):
    def test_correct_addition_chain_ok(self):
        rows = ac.check_equations("required total $1,780 + $20 + $25 = $1,825")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["computed"], 1825)

    def test_wrong_multiplication_flagged(self):
        rows = ac.check_equations("$41.10 × 40 × 52 = $85,888")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["ok"])
        self.assertEqual(rows[0]["computed"], 85488)   # not the stated 85,888

    def test_subtraction_chain(self):
        self.assertTrue(ac.check_equations("1,264 - 41 - 17 = 1,206")[0]["ok"])
        self.assertFalse(ac.check_equations("1,264 - 41 - 17 = 1,209")[0]["ok"])

    def test_no_equation_is_empty(self):
        self.assertEqual(ac.check_equations("Base rent $1,865; cap $1,900; Walk Score 82"), [])

    def test_salary_range_is_not_an_equation(self):
        # "$88,000-$91,500" has no '=' -> not parsed as arithmetic (no false hit).
        self.assertEqual(ac.check_equations("Base comp $88,000-$91,500 below floor"), [])

    def test_mixed_precedence_equation_is_skipped_not_false_flagged(self):
        # '80000 + 5000 x 2 = 90000' is correct by PEMDAS; left-to-right would get
        # 170000 and wrongly flag it. Mixed mul+add chains must be SKIPPED, not judged.
        self.assertEqual(ac.check_equations("$80,000 + $5,000 × 2 = $90,000"), [])
        self.assertEqual(ac.arithmetic_flags("Comp: $80,000 + $5,000 × 2 = $90,000"), [])

    def test_cent_rounding_tolerated(self):
        # $19.99 x 3 = 59.97; stating 59.98 (a cent off) should not flag.
        self.assertTrue(ac.check_equations("$19.99 × 3 = $59.98", tol=1.0)[0]["ok"])


class CountReconciliation(unittest.TestCase):
    def test_matching_list_ok(self):
        txt = ("Source file rows received: 842\nExact email duplicates removed: 19\n"
               "Client suppressions removed: 14\nFinal launch audience: 809")
        r = ac.check_count_reconciliation(txt)
        self.assertIsNotNone(r)
        self.assertTrue(r["ok"])
        self.assertEqual(r["computed_final"], 809)

    def test_mismatch_flagged(self):
        txt = ("Source records: 1,264\nExact duplicates removed: 41\n"
               "Client suppression removals: 17\nFinal audience loaded: 1,209")
        r = ac.check_count_reconciliation(txt)
        self.assertFalse(r["ok"])
        self.assertEqual(r["computed_final"], 1206)

    def test_match_label_counted_as_deduction(self):
        # The 'CRM client matches: 27' line must count as a removal (was a false-positive bug).
        txt = ("Input rows: 955\nRemoved:\n- duplicate emails: 31\n- CRM client matches: 27\n"
               "Final queue: 897")
        r = ac.check_count_reconciliation(txt)
        self.assertEqual(sorted(r["cuts"]), [27, 31])
        self.assertTrue(r["ok"])               # 955 - 31 - 27 = 897, no false flag

    def test_no_pattern_returns_none(self):
        self.assertIsNone(ac.check_count_reconciliation("just some prose with a number 42"))


class Flags(unittest.TestCase):
    def test_flags_wrong_equation(self):
        fl = ac.arithmetic_flags("Annualized base: $41.10 × 40 × 52 = $85,888. Meets floor.")
        self.assertTrue(fl)
        self.assertIn("85488", "".join(fl))

    def test_flags_count_mismatch(self):
        fl = ac.arithmetic_flags("Source: 1,486\nremoved 37\nsuppressed 24\nduplicate 19\n"
                                 "Final audience loaded: 1,409")
        self.assertTrue(fl)
        self.assertIn("reconcile", "".join(fl).lower())

    def test_silent_on_clean_math(self):
        # A fully-consistent report must produce ZERO flags (precision over recall).
        clean = ("Base rent $1,780 + utility $20 + tech $25 = $1,825 (under $1,850 cap).\n"
                 "Input rows: 955\nduplicate emails removed: 31\nCRM client matches: 27\n"
                 "Final queue: 897")
        self.assertEqual(ac.arithmetic_flags(clean), [])

    def test_empty_on_no_arithmetic(self):
        self.assertEqual(ac.arithmetic_flags("A whole unit in budget, walkable, legitimate."), [])


class GuardJudge(unittest.TestCase):
    WRONG = {"id": "x", "artifact": "Annualized: $41.10 × 40 × 52 = $85,888. Meets floor."}
    CLEAN = {"id": "y", "artifact": "Base $86,250 clears the $85,000 floor; remote US; live req."}

    def test_overrides_to_false_pass_without_calling_llm(self):
        def inner(_c):
            raise AssertionError("LLM judge must NOT be called when arithmetic is provably wrong")
        self.assertEqual(ac.guard_judge(inner)(self.WRONG), "FALSE-PASS")

    def test_defers_to_inner_when_arithmetic_is_clean(self):
        self.assertEqual(ac.guard_judge(lambda c: "PASS")(self.CLEAN), "PASS")
        self.assertEqual(ac.guard_judge(lambda c: "FALSE-PASS")(self.CLEAN), "FALSE-PASS")


class RunEvalsArithGuard(unittest.TestCase):
    """The opt-in --arith-guard wiring catches a stated-wrong-math trap even when
    the LLM judge would wave it through."""
    def setUp(self):
        sys.path.insert(0, EVALS_DIR)
        import run_evals
        self.run_evals = run_evals
        self._orig = run_evals.load_cases
        trap = {"id": "math-trap", "target": "verifier", "requires": "judge",
                "expected": "FALSE-PASS",
                "artifact": "Comp: $41.10 × 40 × 52 = $85,888, above the $85,500 floor. Fit."}
        run_evals.load_cases = lambda: [trap]
        self.addCleanup(lambda: setattr(run_evals, "load_cases", self._orig))

    def test_bare_judge_misses_but_guard_catches(self):
        always_pass = lambda _c: "PASS"  # a lenient LLM that doesn't recompute
        missed = self.run_evals.run_suite(judge=always_pass, arith_guard=False)
        self.assertEqual(missed["counts"]["missed"], 1)        # trap slips through
        guarded = self.run_evals.run_suite(judge=always_pass, arith_guard=True)
        self.assertEqual(guarded["counts"]["caught"], 1)       # deterministic layer catches it
        self.assertEqual(guarded["counts"]["missed"], 0)


if __name__ == "__main__":
    unittest.main()
