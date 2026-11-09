"""Money helpers. All internal amounts are integer cents."""


def to_cents(amount):
    # Convert a decimal string to integer cents accurately
    from decimal import Decimal
    # Multiply by 100 and convert to int to avoid floating point errors
    return int(Decimal(amount) * 100)


def from_cents(cents):
    return f"{cents / 100:.2f}"
