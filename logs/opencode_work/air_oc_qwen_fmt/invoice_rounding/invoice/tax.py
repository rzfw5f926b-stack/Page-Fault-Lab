RATES = {"standard": 20, "reduced": 5, "zero": 0}


def tax_cents(net_cents, category):
    return net_cents * RATES[category] // 100
