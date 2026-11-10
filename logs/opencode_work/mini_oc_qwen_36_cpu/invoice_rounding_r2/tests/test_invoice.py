import unittest
from invoice.invoice import Invoice
from invoice.money import to_cents


class T(unittest.TestCase):
    def test_exact_cents(self):
        self.assertEqual(to_cents("19.99"), 1999)

    def test_tax_rounds_half_up(self):
        i = Invoice()
        i.add_line("a", "19.99", 1)
        self.assertEqual(i.tax_cents(), 400)
        self.assertEqual(i.total(), "23.99")

    def test_discount_before_tax(self):
        i = Invoice(discount_percent=15)
        i.add_line("a", "10.00", 3)
        self.assertEqual(i.net_cents(), 2550)
        self.assertEqual(i.tax_cents(), 510)
        self.assertEqual(i.total(), "30.60")
