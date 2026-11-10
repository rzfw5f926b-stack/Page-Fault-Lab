"""Money helpers. All internal amounts are integer cents."""


def round_half_up(value):
    """Round to nearest cent, with .5 rounding up."""
    import math
    return math.floor(value + 0.5)


def to_cents(amount):
    return round_half_up(float(amount) * 100)


def from_cents(cents):
    return f"{cents / 100:.2f}"
