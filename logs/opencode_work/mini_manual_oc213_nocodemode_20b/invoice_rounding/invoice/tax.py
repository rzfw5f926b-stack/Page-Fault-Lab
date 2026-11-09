RATES = {"standard": 20, "reduced": 5, "zero": 0}

from decimal import Decimal, ROUND_HALF_UP

def tax_cents(net_cents: int, category: str) -> int:
    """Return tax amount in cents, rounded half up."""
    rate = RATES[category]
    return int((Decimal(net_cents) * Decimal(rate) / Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))
