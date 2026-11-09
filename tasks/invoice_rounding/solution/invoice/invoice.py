from .money import from_cents, percent_half_up, to_cents
from .tax import tax_cents


class Invoice:
    def __init__(self, discount_percent=0):
        self.lines = []
        self.discount_percent = discount_percent

    def add_line(self, description, unit_price, quantity, category="standard"):
        self.lines.append((description, to_cents(unit_price), quantity, category))

    def _nets(self):
        for _, price, qty, cat in self.lines:
            line = price * qty
            yield line - percent_half_up(line, self.discount_percent), cat

    def net_cents(self):
        return sum(net for net, _ in self._nets())

    def tax_cents(self):
        return sum(tax_cents(net, cat) for net, cat in self._nets())

    def total(self):
        return from_cents(self.net_cents() + self.tax_cents())
