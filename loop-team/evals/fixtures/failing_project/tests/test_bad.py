import unittest


class T(unittest.TestCase):
    def test_bad(self):
        # Genuinely failing assertion — the harness must report passed=False.
        self.assertEqual(1, 2)


if __name__ == "__main__":
    unittest.main()
