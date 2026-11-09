"""Money helpers. All internal amounts are integer cents."""


def to_cents(amount):
    from decimal import Decimal, ROUND_HALF_UP
    return int((Decimal(amount) * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_cents(cents):
    from decimal import Decimal
    return f"{Decimal(cents) / Decimal(100):.2f}"
