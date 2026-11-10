"""Money helpers. All internal amounts are integer cents."""

from decimal import Decimal, ROUND_HALF_UP


def to_cents(amount):
    return int(Decimal(amount) * 100)


def from_cents(cents):
    return f"{cents / 100:.2f}"


def round_half_up(value):
    """Round a Decimal value to the nearest integer, half up."""
    return int(Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
