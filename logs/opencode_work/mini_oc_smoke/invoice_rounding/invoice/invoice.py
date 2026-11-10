from .money import from_cents, to_cents
from .tax import tax_cents
from decimal import Decimal, ROUND_HALF_UP


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def _round_half_up(self, value):
        """Round a number to the nearest integer cent using HALF_UP.

        ``value`` can be an int, float or Decimal.  The function returns an
        int.
        """
        return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def net_cents(self):
        """Return the sum of line nets after applying the discount.

        The discount is applied to each line's unit price before the quantity
        is multiplied and the result is rounded half up to the nearest cent.
        """
        total = 0
        for _, unit_cents, qty, _ in self.lines:
            discount_per_unit = self._round_half_up(unit_cents * self.discount_percent / 100)
            net_per_unit = unit_cents - discount_per_unit
            total += net_per_unit * qty
        return total

    def tax_cents(self):
        """Return the sum of tax cents for the discounted line nets.

        For each line we apply the discount to the unit price, multiply by the
        quantity to get the discounted line net, then use the module‑level
        ``tax_cents`` helper to compute tax on that net.
        """
        total_tax = 0
        for _, unit_cents, qty, cat in self.lines:
            discount_per_unit = self._round_half_up(unit_cents * self.discount_percent / 100)
            net_per_unit = unit_cents - discount_per_unit
            net_line_cents = net_per_unit * qty
            total_tax += tax_cents(net_line_cents, cat)
        return total_tax

    def total(self):
        """Return the formatted total amount.

        The total is the sum of the discounted net and the tax, formatted as a
        string with two decimal places via :func:`from_cents`.
        """
        total_cents = self.net_cents() + self.tax_cents()
        return from_cents(total_cents)
