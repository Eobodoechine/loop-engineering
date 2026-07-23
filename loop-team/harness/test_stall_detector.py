"""Tests for the stall detector.

Run with:
    python3 -m pytest loop-team/harness/test_stall_detector.py -q
"""
import os
import sys
import unittest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)
import stall_detector as sd  # noqa: E402


class Signature(unittest.TestCase):
    def test_stable_across_line_numbers_and_paths(self):
        a = ('Traceback (most recent call last):\n'
             '  File "/home/x/proj/app.py", line 42, in run\n'
             '    do()\n'
             'KeyError: \'user_id\'')
        b = ('Traceback (most recent call last):\n'
             '  File "/tmp/other/app.py", line 999, in run\n'
             '    do()\n'
             'KeyError: \'user_id\'')
        self.assertEqual(sd.error_signature(a), sd.error_signature(b))
        self.assertIn("KeyError", sd.error_signature(a))

    def test_different_errors_differ(self):
        a = "ValueError: invalid literal"
        b = "TypeError: unsupported operand"
        self.assertNotEqual(sd.error_signature(a), sd.error_signature(b))

    def test_pytest_assertion_line_captured(self):
        out = ("E       assert 1 == 2\n"
               "tests/test_x.py:7: AssertionError")
        sig = sd.error_signature(out)
        self.assertTrue(sig)
        # line numbers normalized away
        self.assertNotIn(":7", sig)

    def test_empty_is_empty(self):
        self.assertEqual(sd.error_signature(""), "")
        self.assertEqual(sd.error_signature("   \n  "), "")

    def test_message_colon_numbers_not_collapsed(self):
        # A port / status code in the message is NOT a line number -> must stay
        # distinct so two different bugs don't collapse into one signature.
        a = "RuntimeError: request to localhost:8080 refused"
        b = "RuntimeError: request to localhost:9090 refused"
        self.assertNotEqual(sd.error_signature(a), sd.error_signature(b))

    def test_file_line_numbers_still_collapsed(self):
        a = "AssertionError at helper.py:12"
        b = "AssertionError at helper.py:347"
        self.assertEqual(sd.error_signature(a), sd.error_signature(b))

    def test_hex_addresses_normalized(self):
        a = "TypeError: <obj at 0x10af3e2b0> is not callable"
        b = "TypeError: <obj at 0x7ffee1c0> is not callable"
        self.assertEqual(sd.error_signature(a), sd.error_signature(b))


class WarningMasking(unittest.TestCase):
    """Bug-finder HIGH: a benign warning line must not mask the real failure and
    collapse two DIFFERENT bugs into one signature (false 'stuck')."""

    def test_benign_warning_does_not_collapse_distinct_failures(self):
        o1 = ("PytestUnraisableExceptionWarning: ignored\n"
              "FAILED tests/test_a.py::test_login - returned 500 not 200\n"
              "1 failed in 0.2s")
        o2 = ("PytestUnraisableExceptionWarning: ignored\n"
              "FAILED tests/test_b.py::test_parser - off by one in index\n"
              "1 failed in 0.2s")
        self.assertNotEqual(sd.error_signature(o1), sd.error_signature(o2))
        self.assertFalse(sd.stuck_from_outputs([o1, o2]).stuck)

    def test_summary_count_line_is_not_the_signature(self):
        sig = sd.error_signature("FAILED tests/x.py::t - boom\n1 failed in 0.1s")
        self.assertNotIn("1 failed", sig)
        self.assertIn("FAILED", sig)

    def test_real_exception_still_preferred(self):
        out = ("DeprecationWarning: old API\n"
               "Traceback ...\nValueError: bad input")
        self.assertIn("ValueError", sd.error_signature(out))


class IsStuck(unittest.TestCase):
    def test_repeat_count_accurate_below_threshold(self):
        # Bug-finder LOW: repeat_count must be the true trailing run, not len(sigs).
        v = sd.is_stuck(["A", "B"], threshold=3)
        self.assertFalse(v.stuck)
        self.assertEqual(v.repeat_count, 1)

    def test_single_attempt_not_stuck(self):
        self.assertFalse(sd.is_stuck(["KeyError: x"]).stuck)

    def test_same_twice_is_stuck(self):
        v = sd.is_stuck(["KeyError: x", "KeyError: x"])
        self.assertTrue(v.stuck)
        self.assertEqual(v.repeat_count, 2)

    def test_progress_resets_streak(self):
        # Latest attempt has a different (new) failure -> not stuck.
        v = sd.is_stuck(["KeyError: x", "KeyError: x", "TypeError: y"])
        self.assertFalse(v.stuck)
        self.assertEqual(v.repeat_count, 1)

    def test_threshold_three(self):
        self.assertFalse(sd.is_stuck(["a", "a"], threshold=3).stuck)
        self.assertTrue(sd.is_stuck(["a", "a", "a"], threshold=3).stuck)

    def test_streak_counts_only_trailing_run(self):
        v = sd.is_stuck(["a", "b", "b", "b"], threshold=2)
        self.assertTrue(v.stuck)
        self.assertEqual(v.repeat_count, 3)

    def test_empty_latest_not_stuck(self):
        self.assertFalse(sd.is_stuck(["a", ""]).stuck)

    def test_invalid_threshold_raises(self):
        with self.assertRaises(ValueError):
            sd.is_stuck(["a"], threshold=0)


class StuckFromOutputs(unittest.TestCase):
    def test_normalizes_then_decides(self):
        # Same bug, shifting line numbers across two attempts -> stuck.
        o1 = 'File "app.py", line 10\nKeyError: \'id\''
        o2 = 'File "app.py", line 88\nKeyError: \'id\''
        v = sd.stuck_from_outputs([o1, o2])
        self.assertTrue(v.stuck)

    def test_different_bugs_not_stuck(self):
        v = sd.stuck_from_outputs(["ValueError: a", "KeyError: b"])
        self.assertFalse(v.stuck)


if __name__ == "__main__":
    unittest.main()
