import re

def parse_duration(s: str) -> int:
    """
    Convert a duration string into total seconds.

    The string may contain hours (h), minutes (m), and seconds (s) in that order,
    each appearing at most once. Numbers must precede their unit.

    Examples:
        '1h30m15s' -> 5415
        '45m'      -> 2700
        '2h'       -> 7200
        '90s'      -> 90
        '1h5s'     -> 3605

    Raises:
        ValueError: if the string is empty, contains unknown units,
                    units out of order, repeated units, or missing numbers.
    """
    if not s:
        raise ValueError("Duration string cannot be empty")

    pattern = r'^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$'
    match = re.fullmatch(pattern, s)
    if not match:
        raise ValueError(f"Invalid duration format: {s!r}")

    hours_str, minutes_str, seconds_str = match.groups()
    hours = int(hours_str) if hours_str else 0
    minutes = int(minutes_str) if minutes_str else 0
    seconds = int(seconds_str) if seconds_str else 0

    return hours * 3600 + minutes * 60 + seconds



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
