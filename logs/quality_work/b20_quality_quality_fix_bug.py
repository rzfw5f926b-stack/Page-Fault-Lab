import re

def top_words(text, k):
    # Count words case‑insensitively
    counts = {}
    for w in re.findall(r'[a-z]+', text.lower()):
        counts[w] = counts.get(w, 0) + 1

    # Sort by count descending, then alphabetically ascending
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    # Return the top k words (or all if fewer than k)
    return [w for w, _ in items[:k]]



assert top_words('b a B c a b', 2) == ['b', 'a']
assert top_words('Dog cat dog CAT bird', 3) == ['cat', 'dog', 'bird']
assert top_words('x', 5) == ['x']
assert top_words('', 3) == []

print('PASS')
