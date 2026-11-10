from .money import from_cents, to_cents
from .tax import tax_cents, round_half_up


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def _line_discounted_net(self, price, qty, cat):
        gross = price * qty
        discount_amount = round_half_up(gross * self.discount_percent / 100)
        return gross - discount_amount

    def net_cents(self):
        return sum(self._line_discounted_net(price, qty, cat)
                   for _, price, qty, cat in self.lines)

    def tax_cents(self):
        return sum(tax_cents(self._line_discounted_net(price, qty, cat), cat)
                   for _, price, qty, cat in self.lines)

    def total(self):
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross)
