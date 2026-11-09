"""Money helpers. All internal amounts are integer cents."""


def to_cents(amount):
    return int(float(amount) * 100)


def from_cents(cents):
    return f"{cents / 100:.2f}"
