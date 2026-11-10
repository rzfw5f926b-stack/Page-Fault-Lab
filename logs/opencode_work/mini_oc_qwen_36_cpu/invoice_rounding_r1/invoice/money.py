"""Money helpers. All internal amounts are integer cents."""

from decimal import Decimal, ROUND_HALF_UP


def to_cents(amount):
    return int(Decimal(amount) * 100)


def from_cents(cents):
    return f"{cents / 100:.2f}"
