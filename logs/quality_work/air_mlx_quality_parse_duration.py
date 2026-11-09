


assert parse_duration('1h30m15s') == 5415
assert parse_duration('45m') == 2700
assert parse_duration('2h') == 7200
assert parse_duration('90s') == 90
assert parse_duration('1h5s') == 3605
for bad in ['', '5x', 'm', '1s1h', '1h1h', 'h5']:
    try:
        parse_duration(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('no ValueError for ' + repr(bad))

print('PASS')
