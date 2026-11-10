from .money import from_cents, to_cents, round_half_up
from .tax import tax_cents


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def net_cents(self):
        total = 0
        for _, price, qty, category in self.lines:
            # Calculate line net before discount
            line_net = price * qty
            # Apply discount to line net
            discounted_net = line_net * (100 - self.discount_percent) / 100
            # Round to nearest cent (half up)
            discounted_net = round_half_up(discounted_net)
            total += discounted_net
        return total

    def tax_cents(self):
        total = 0
        for _, price, qty, category in self.lines:
            # Calculate line net before discount
            line_net = price * qty
            # Apply discount to line net
            discounted_net = line_net * (100 - self.discount_percent) / 100
            # Round to nearest cent (half up)
            discounted_net = round_half_up(discounted_net)
            # Calculate tax on discounted net
            tax = tax_cents(discounted_net, category)
            total += tax
        return total

    def total(self):
        gross = self.net_cents() + self.tax_cents()
        return from_cents(gross)
