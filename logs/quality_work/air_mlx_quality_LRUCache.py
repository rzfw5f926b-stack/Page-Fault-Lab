


c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)
assert c.get(2) == -1
c.put(1, 10)
c.put(4, 4)
assert c.get(3) == -1
assert c.get(1) == 10 and c.get(4) == 4
d = LRUCache(1)
d.put('a', 1); d.put('a', 2)
assert d.get('a') == 2

print('PASS')
