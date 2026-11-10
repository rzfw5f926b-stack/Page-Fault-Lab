


assert top_words('b a B c a b', 2) == ['b', 'a']
assert top_words('Dog cat dog CAT bird', 3) == ['cat', 'dog', 'bird']
assert top_words('x', 5) == ['x']
assert top_words('', 3) == []

print('PASS')
