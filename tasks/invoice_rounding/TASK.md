Bug report for the `invoice` package: invoice totals are wrong. Fix the package so these rules hold.

1. Amounts are decimal strings and must convert to exact cents: `to_cents("19.99")` is `1999`.
2. The percentage discount applies to each line before tax. Each line's discount amount is rounded half up to the cent and then subtracted from that line: a 33% discount on a 50-cent line is 17 cents off, leaving 33 cents.
3. Tax is calculated per line on that line's discounted net, rounded half up to the cent.
4. `Invoice.net_cents()` is the sum of the discounted line nets, `Invoice.tax_cents()` is the sum of the line taxes, and `Invoice.total()` returns their sum formatted by `from_cents`.

Keep all existing public names and signatures.
