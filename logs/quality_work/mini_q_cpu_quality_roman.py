def to_roman(n: int) -> str:
    if not isinstance(n, int) or n < 1 or n > 3999:
        raise ValueError("Input must be an integer between 1 and 3999")
    
    values = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    symbols = ['M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I']
    
    result = []
    for i in range(len(values)):
        count = n // values[i]
        if count:
            result.append(symbols[i] * count)
            n -= values[i] * count
    
    return ''.join(result)

def from_roman(s: str) -> int:
    if not isinstance(s, str) or not s:
        raise ValueError("Input must be a non-empty string")
    
    roman_values = {
        'I': 1, 'V': 5, 'X': 10, 'L': 50,
        'C': 100, 'D': 500, 'M': 1000
    }
    
    # Check for invalid patterns
    invalid_patterns = ['IIII', 'VV', 'XXXX', 'LL', 'CCCC', 'DD', 'MMMM']
    for pattern in invalid_patterns:
        if pattern in s:
            raise ValueError("Invalid roman numeral pattern")
    
    # Check for invalid subtraction patterns
    if 'IL' in s or 'IC' in s or 'ID' in s or 'IM' in s:
        raise ValueError("Invalid subtraction pattern")
    if 'XD' in s or 'XM' in s:
        raise ValueError("Invalid subtraction pattern")
    if 'VL' in s or 'VM' in s:
        raise ValueError("Invalid subtraction pattern")
    
    total = 0
    prev_value = 0
    
    for char in reversed(s):
        if char not in roman_values:
            raise ValueError("Invalid roman numeral character")
        
        current_value = roman_values[char]
        if current_value < prev_value:
            total -= current_value
        else:
            total += current_value
        prev_value = current_value
    
    # Verify the result by converting back
    if to_roman(total) != s:
        raise ValueError("Invalid roman numeral")
    
    return total



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
