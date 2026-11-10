import re

def parse_duration(s: str) -> int:
    if not s:
        raise ValueError("Empty string")
    parts = re.findall(r'(\d+)([hms])', s)
    if not parts or ''.join(f"{n}{u}" for n, u in parts) != s:
        raise ValueError("Invalid format")
    units = [u for _, u in parts]
    if units != [u for u in 'hms' if u in units]:
        raise ValueError("Wrong order or repeated units")
    return sum(int(n) * (3600 if u == 'h' else 60 if u == 'm' else 1) for n, u in parts)



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
