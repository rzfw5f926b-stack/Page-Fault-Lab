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
        for description, price, qty, category in self.lines:
            # Apply discount before tax
            discounted_price = round(price * (100 - self.discount_percent) / 100)
            net = discounted_price * qty
            total += net
        return total

    def tax_cents(self):
        total = 0
        for description, price, qty, category in self.lines:
            # Apply discount before tax
            discounted_price = round(price * (100 - self.discount_percent) / 100)
            net = discounted_price * qty
            tax = tax_cents(net, category)
            total += tax
        return total

    def total(self):
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross)
