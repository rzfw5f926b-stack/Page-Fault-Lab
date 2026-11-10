"""Money helpers. All internal amounts are integer cents."""


def to_cents(amount):
    """Convert a decimal string to integer cents.

    ``amount`` is expected to be a decimal number represented as a string –
    e.g. ``"19.99"``.  Using ``float`` can introduce binary floating‑point
    errors (e.g. ``0.1`` becomes ``0.10000000000000000555``).  The tests rely
    on exact conversion, so we use :class:`decimal.Decimal` which preserves
    the exact value.

    The function multiplies the amount by 100 and returns an integer.  The
    conversion is safe because the input is a decimal string with at most a
    few fractional digits.
    """
    from decimal import Decimal
    return int((Decimal(amount) * Decimal(100)).to_integral_value())


def from_cents(cents):
    return f"{cents / 100:.2f}"
