import unittest
from invoice.invoice import Invoice
from invoice.money import to_cents


class H(unittest.TestCase):
    def test_more_exact_cents(self):
        self.assertEqual(to_cents("1.15"), 115)
        self.assertEqual(to_cents("4.35"), 435)
        self.assertEqual(to_cents("1234567.89"), 123456789)

    def test_tax_is_per_line(self):
        i = Invoice()
        for _ in range(3):
            i.add_line("x", "0.10", 1, "reduced")
        self.assertEqual(i.tax_cents(), 3)
        self.assertEqual(i.total(), "0.33")

    def test_half_up_low_side(self):
        i = Invoice()
        i.add_line("a", "0.05", 1, "reduced")
        self.assertEqual(i.tax_cents(), 0)

    def test_discount_half_up_per_line(self):
        i = Invoice(discount_percent=33)
        i.add_line("a", "0.50", 1, "zero")
        self.assertEqual(i.net_cents(), 33)
        i.add_line("b", "0.50", 1, "zero")
        self.assertEqual(i.net_cents(), 66)
