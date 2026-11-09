from .money import from_cents, to_cents
from .tax import tax_cents as _tax_cents
from decimal import Decimal, ROUND_HALF_UP


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        # Store price in cents for internal calculations
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def _discount_cents(self, base_cents: int) -> int:
        if self.discount_percent == 0:
            return 0
        return int((Decimal(base_cents) * Decimal(self.discount_percent) / Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))

    def net_cents(self):
        total = 0
        for _, price, qty, _ in self.lines:
            base = price * qty
            disc = self._discount_cents(base)
            total += base - disc
        return total

    def tax_cents(self):
        total = 0
        for _, price, qty, cat in self.lines:
            base = price * qty
            disc = self._discount_cents(base)
            net = base - disc
            total += _tax_cents(net, cat)
        return total

    def total(self):
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross)
