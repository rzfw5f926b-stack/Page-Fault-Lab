from .money import from_cents, to_cents, round_half_up
from .tax import tax_cents


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def _line_discount(self, line_gross):
        discount_amount = round_half_up(line_gross * self.discount_percent / 100)
        return line_gross - discount_amount

    def net_cents(self):
        total = 0
        for _, price, qty, _ in self.lines:
            line_gross = price * qty
            total += self._line_discount(line_gross)
        return total

    def tax_cents(self):
        total = 0
        for _, price, qty, cat in self.lines:
            line_gross = price * qty
            discounted_net = self._line_discount(line_gross)
            total += tax_cents(discounted_net, cat)
        return total

    def total(self):
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross)
