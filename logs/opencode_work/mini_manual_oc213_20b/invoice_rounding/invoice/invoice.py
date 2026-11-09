from .money import from_cents, to_cents
from .tax import tax_cents


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def net_cents(self):
        # Sum of discounted line nets
        total = 0
        for _, price, qty, _ in self.lines:
            line_net = price * qty
            discount = (line_net * self.discount_percent + 50) // 100
            total += line_net - discount
        return total

    def tax_cents(self):
        # Sum of tax on discounted net per line
        total = 0
        for _, price, qty, category in self.lines:
            line_net = price * qty
            discount = (line_net * self.discount_percent + 50) // 100
            discounted_net = line_net - discount
            total += tax_cents(discounted_net, category)
        return total

    def total(self):
        # Total is net + tax (discount already applied to net)
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross)
