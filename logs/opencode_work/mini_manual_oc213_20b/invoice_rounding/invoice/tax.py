RATES = {"standard": 20, "reduced": 5, "zero": 0}


def tax_cents(net_cents, category):
    # Calculate tax rounding half up to the cent
    rate = RATES[category]
    return (net_cents * rate + 50) // 100
