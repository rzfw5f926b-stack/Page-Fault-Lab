from .money import round_half_up

RATES = {"standard": 20, "reduced": 5, "zero": 0}


def tax_cents(net_cents, category):
    rate = RATES[category]
    return round_half_up(net_cents * rate / 100)
