import re
from typing import Dict

# Mapping for conversion from integer to Roman numeral
_ROMAN_MAP = [
    (1000, "M"),
    (900,  "CM"),
    (500,  "D"),
    (400,  "CD"),
    (100,  "C"),
    (90,   "XC"),
    (50,   "L"),
    (40,   "XL"),
    (10,   "X"),
    (9,    "IX"),
    (5,    "V"),
    (4,    "IV"),
    (1,    "I"),
]

# Regular expression that matches valid Roman numerals from 1 to 3999
_ROMAN_VALID_RE = re.compile(
    r"^M{0,3}"
    r"(CM|CD|D?C{0,3})"
    r"(XC|XL|L?X{0,3})"
    r"(IX|IV|V?I{0,3})$"
)

# Mapping for conversion from Roman numeral to integer
_ROMAN_VALUE: Dict[str, int] = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}


def to_roman(n: int) -> str:
    """
    Convert an integer to a Roman numeral.

    Parameters
    ----------
    n : int
        Integer to convert. Must be in the range 1 <= n <= 3999.

    Returns
    -------
    str
        Roman numeral representation of ``n``.

    Raises
    ------
    ValueError
        If ``n`` is outside the allowed range.
    """
    if not isinstance(n, int):
        raise ValueError(f"Input must be an integer, got {type(n).__name__}")
    if n < 1 or n > 3999:
        raise ValueError("Integer out of range (1-3999)")

    result = []
    for value, numeral in _ROMAN_MAP:
        while n >= value:
            result.append(numeral)
            n -= value
    return "".join(result)


def from_roman(s: str) -> int:
    """
    Parse a Roman numeral and return its integer value.

    Parameters
    ----------
    s : str
        Roman numeral string. Must be a valid representation of a number
        between 1 and 3999 inclusive.

    Returns
    -------
    int
        Integer value of the Roman numeral.

    Raises
    ------
    ValueError
        If ``s`` is empty, contains invalid characters, or is not a
        standard Roman numeral.
    """
    if not isinstance(s, str):
        raise ValueError(f"Input must be a string, got {type(s).__name__}")
    if not s:
        raise ValueError("Empty string is not a valid Roman numeral")

    # Ensure the string is uppercase; reject lowercase or mixed case
    if s != s.upper():
        raise ValueError("Roman numerals must be uppercase")

    if not _ROMAN_VALID_RE.match(s):
        raise ValueError(f"Invalid Roman numeral: {s}")

    total = 0
    prev_value = 0
    for ch in reversed(s):
        value = _ROMAN_VALUE[ch]
        if value < prev_value:
            total -= value
        else:
            total += value
            prev_value = value

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
