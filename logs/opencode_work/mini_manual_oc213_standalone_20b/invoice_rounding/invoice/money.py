"""Money helpers. All internal amounts are integer cents."""

from decimal import Decimal


def to_cents(amount):
    # Convert a decimal string to an exact integer number of cents.
    # Use Decimal to avoid floating point errors.
    return int(Decimal(amount) * 100)


def from_cents(cents):
    return f"{cents / 100:.2f}"
