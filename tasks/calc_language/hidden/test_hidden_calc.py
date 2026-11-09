import unittest

from calc import calc
from calc.errors import CalcError


class H(unittest.TestCase):
    def test_values(self):
        for src, want in [("10 - 3 - 2", 5), ("7 / 2", 3.5), ("7 % 4 * 2", 6), ("2 * 3 % 4", 2),
                          ("1.5 + 2.25", 3.75), ("2**-1", 0.5), ("--3", 3), ("(2 + 3) ** 2", 25),
                          ("abs(-3) + min(4, 2, 8)", 5), ("max(1)", 1), ("2 ** 3 * 2", 16),
                          ("-(-(2))", 2), ("min((1 + 1), 3)", 2)]:
            with self.subTest(src):
                self.assertEqual(calc(src), want)

    def test_env(self):
        self.assertEqual(calc("rate * base + 1", {"rate": 2, "base": 10}), 21)
        self.assertEqual(calc("x1 + _y", {"x1": 1, "_y": 2}), 3)

    def test_errors(self):
        for src in ["", "   ", "1 +", "(1", "1)", "1 2", "* 3", "1 / 0", "5 % 0", "nope", "foo(1)",
                    "min()", "max()", "abs(1, 2)", "abs()", "min(1,)", "1.2.3", "2 $ 3", "()"]:
            with self.subTest(src):
                with self.assertRaises(CalcError):
                    calc(src)
