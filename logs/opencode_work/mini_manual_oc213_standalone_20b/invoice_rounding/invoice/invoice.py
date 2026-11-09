from .money import from_cents, to_cents
from .tax import tax_cents as tax_func


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
            net = price * qty
            discount = (net * self.discount_percent + 50) // 100
            total += net - discount
        return total

    def tax_cents(self):
        # Sum of taxes on discounted nets
        total = 0
        for _, price, qty, cat in self.lines:
            net = price * qty
            discount = (net * self.discount_percent + 50) // 100
            net_discounted = net - discount
            tax = (net_discounted * tax_func(cat) + 50) // 100
            total += tax
        return total

    def total(self):
        return from_cents(self.net_cents() + self.tax_cents())
