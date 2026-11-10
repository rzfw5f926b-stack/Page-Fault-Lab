RATES = {"standard": 20, "reduced": 5, "zero": 0}


def tax_cents(net_cents, category):
    """Return tax cents rounded half up.

    ``net_cents`` is an integer number of cents.  ``category`` selects the
    rate from ``RATES``.

    The calculation is ``net_cents * rate / 100``.  Because the intermediate
    value can be a fraction of a cent we round *half up* to the nearest
    cent.
    """
    from decimal import Decimal, ROUND_HALF_UP
    rate = RATES[category]
    # Use Decimal for exact arithmetic and rounding.
    tax = Decimal(net_cents) * Decimal(rate) / Decimal(100)
    return int(tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
