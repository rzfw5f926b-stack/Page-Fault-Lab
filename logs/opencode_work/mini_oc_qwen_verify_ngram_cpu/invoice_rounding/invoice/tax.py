import math

RATES = {"standard": 20, "reduced": 5, "zero": 0}


def round_half_up(value):
    """Round to nearest cent, with .5 rounding up."""
    return math.floor(value + 0.5)


def tax_cents(net_cents, category):
    # Calculate tax with proper rounding to nearest cent (half up)
    tax = net_cents * RATES[category] / 100
    return round_half_up(tax)
