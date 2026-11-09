from decimal import Decimal, ROUND_HALF_UP

from .money import from_cents, to_cents
from .tax import tax_cents

class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def net_cents(self):
        total = 0
        for _, price, qty, _ in self.lines:
            line_net = price * qty
            discounted = (Decimal(line_net) * Decimal(100 - self.discount_percent) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            total += int(discounted)
        return total

    def tax_cents(self):
        total = 0
        for _, price, qty, cat in self.lines:
            line_net = price * qty
            discounted = (Decimal(line_net) * Decimal(100 - self.discount_percent) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            net_after_discount = int(discounted)
            total += tax_cents(net_after_discount, cat)
        return total

    def total(self):
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross)
