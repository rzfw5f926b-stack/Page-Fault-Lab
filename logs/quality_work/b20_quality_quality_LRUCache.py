from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1
        value = self.cache.pop(key)
        self.cache[key] = value  # re‑insert to mark as most recently used
        return value

    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            self.cache.pop(key)
        elif len(self.cache) >= self.capacity:
            self.cache.popitem(last=False)  # remove least recently used
        self.cache[key] = value



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
