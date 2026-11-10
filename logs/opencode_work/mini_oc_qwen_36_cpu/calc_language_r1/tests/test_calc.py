import unittest

from calc import calc
from calc.errors import CalcError


class T(unittest.TestCase):
    def test_existing(self):
        self.assertEqual(calc("1 + 2 - 4"), -1)

    def test_precedence(self):
        self.assertEqual(calc("1 + 2 * 3"), 7)

    def test_parens_unary(self):
        self.assertEqual(calc("-(1 + 2) * 3"), -9)

    def test_power(self):
        self.assertEqual(calc("-2**2"), -4)
        self.assertEqual(calc("2**3**2"), 512)

    def test_env_and_functions(self):
        self.assertEqual(calc("max(x, 2 + y)", {"x": 1, "y": 5}), 7)

    def test_division_by_zero(self):
        with self.assertRaises(CalcError):
            calc("1 / 0")
