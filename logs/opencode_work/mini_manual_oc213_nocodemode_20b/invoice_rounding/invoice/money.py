"""Money helpers. All internal amounts are integer cents."""

from decimal import Decimal, ROUND_HALF_UP


def to_cents(amount: str) -> int:
    """Convert a decimal string to integer cents.

    Uses Decimal for exact arithmetic to avoid floating point errors.
    """
    # Decimal will preserve the exact decimal representation.
    return int((Decimal(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> str:
    """Format integer cents back to a two‑decimal string."""
    return f"{cents / 100:.2f}"
