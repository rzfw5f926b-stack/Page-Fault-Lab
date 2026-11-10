from decimal import Decimal, ROUND_HALF_UP

RATES = {"standard": 20, "reduced": 5, "zero": 0}


def round_half_up(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def tax_cents(net_cents, category):
    tax = Decimal(net_cents) * RATES[category] / Decimal(100)
    return int(tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
