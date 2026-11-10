


assert to_roman(1994) == 'MCMXCIV'
assert to_roman(3999) == 'MMMCMXCIX'
assert to_roman(4) == 'IV'
for n in range(1, 4000):
    assert from_roman(to_roman(n)) == n
for bad in [0, 4000]:
    try:
        to_roman(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
for bad in ['IIII', 'IC', 'VV', '']:
    try:
        from_roman(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)

print('PASS')
