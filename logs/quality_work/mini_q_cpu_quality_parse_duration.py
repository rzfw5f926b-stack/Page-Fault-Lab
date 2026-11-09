import re

def parse_duration(s: str) -> int:
    if not s:
        raise ValueError("Empty string")
    
    # Pattern to match duration components: optional number followed by unit
    pattern = r'^(\d+h)?(\d+m)?(\d+s)?$'
    match = re.match(pattern, s)
    
    if not match:
        raise ValueError("Invalid format")
    
    hours = 0
    minutes = 0
    seconds = 0
    
    # Extract components
    if match.group(1):  # hours
        hours = int(match.group(1)[:-1])
    if match.group(2):  # minutes
        minutes = int(match.group(2)[:-1])
    if match.group(3):  # seconds
        seconds = int(match.group(3)[:-1])
    
    # Check for repeated units (should be handled by regex, but let's be safe)
    components = [match.group(1), match.group(2), match.group(3)]
    seen_units = set()
    for component in components:
        if component:
            unit = component[-1]
            if unit in seen_units:
                raise ValueError("Repeated units")
            seen_units.add(unit)
    
    # Check order (h, m, s) - this is implicitly checked by regex pattern
    # But we should verify that if m exists, h exists, and if s exists, m exists
    # Actually, the regex pattern ensures correct order
    
    # Verify that we have at least one component with a number
    if hours == 0 and minutes == 0 and seconds == 0:
        raise ValueError("Missing numbers")
    
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
