from .money import from_cents, to_cents
from .tax import tax_cents


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def net_cents(self):
        return sum(price * qty for _, price, qty, _ in self.lines)

    def tax_cents(self):
        return sum(tax_cents(price * qty, cat) for _, price, qty, cat in self.lines)

    def total(self):
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross - gross * self.discount_percent // 100)
