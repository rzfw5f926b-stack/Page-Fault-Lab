def to_roman(n: int) -> str:
    if not isinstance(n, int) or not (1 <= n <= 3999):
        raise ValueError("Integer must be between 1 and 3999")
    val_map = [
        (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
        (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
        (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')
    ]
    result = []
    for val, sym in val_map:
        while n >= val:
            result.append(sym)
            n -= val
    return ''.join(result)

def from_roman(s: str) -> int:
    if not isinstance(s, str) or not s:
        raise ValueError("Invalid Roman numeral")
    roman_values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    val = 0
    prev = 0
    for char in reversed(s):
        if char not in roman_values:
            raise ValueError("Invalid Roman numeral")
        curr = roman_values[char]
        if curr < prev:
            val -= curr
        else:
            val += curr
        prev = curr
    if to_roman(val) != s:
        raise ValueError("Invalid Roman numeral")
    return val



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
