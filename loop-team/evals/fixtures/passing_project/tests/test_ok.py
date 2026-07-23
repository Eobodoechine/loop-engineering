import unittest


class T(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(1, 1)


if __name__ == "__main__":
    unittest.main()
