"""Money helpers. All internal amounts are integer cents."""
from decimal import Decimal


def to_cents(amount):
    return int(Decimal(str(amount)) * 100)


def from_cents(cents):
    return f"{cents / 100:.2f}"


def percent_half_up(cents, percent):
    return (cents * percent + 50) // 100
