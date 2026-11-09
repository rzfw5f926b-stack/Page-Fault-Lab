RATES = {"standard": 20, "reduced": 5, "zero": 0}


def tax_cents(net_cents, category):
    return round(net_cents * RATES[category] / 100)
