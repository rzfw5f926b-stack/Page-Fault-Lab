from .money import percent_half_up

RATES = {"standard": 20, "reduced": 5, "zero": 0}


def tax_cents(net_cents, category):
    return percent_half_up(net_cents, RATES[category])
