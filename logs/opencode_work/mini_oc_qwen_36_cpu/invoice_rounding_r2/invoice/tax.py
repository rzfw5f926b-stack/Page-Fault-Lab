RATES = {"standard": 20, "reduced": 5, "zero": 0}
from decimal import Decimal, ROUND_HALF_UP


def tax_cents(net_cents, category):
    raw = Decimal(net_cents) * RATES[category] / Decimal(100)
    return int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
