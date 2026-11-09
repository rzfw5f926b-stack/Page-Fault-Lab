RATES = {"standard": 20, "reduced": 5, "zero": 0}


def tax_cents(net_cents, category):
    from decimal import Decimal, ROUND_HALF_UP
    rate = RATES[category]
    return int((Decimal(net_cents) * Decimal(rate) / Decimal(100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
