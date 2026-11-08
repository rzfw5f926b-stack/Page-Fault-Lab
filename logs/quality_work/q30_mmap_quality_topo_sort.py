from collections import defaultdict, deque

def topo_sort(deps: dict[str, list[str]]) -> list[str]:
    # Build reverse dependency map and in-degree count
    reverse_deps = defaultdict(list)
    in_degree = defaultdict(int)
    
    # Initialize all nodes
    all_items = set(deps.keys())
    for item, dependencies in deps.items():
        all_items.update(dependencies)
    
    # Build graph
    for item, dependencies in deps.items():
        in_degree[item] += len(dependencies)
        for dep in dependencies:
            reverse_deps[dep].append(item)
    
    # Find all items with no dependencies
    queue = deque(sorted([item for item in all_items if in_degree[item] == 0]))
    result = []
    
    while queue:
        # Get the lexicographically smallest item
        current = queue.popleft()
        result.append(current)
        
        # Remove current item and update dependencies
        for dependent in reverse_deps[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    
    # Check for cycles
    if len(result) != len(all_items):
        raise ValueError("Cycle detected")
    
    return result



assert topo_sort({'b': ['a'], 'c': ['b'], 'a': []}) == ['a', 'b', 'c']
assert topo_sort({'app': ['lib', 'util'], 'lib': ['util']}) == ['util', 'lib', 'app']
assert topo_sort({'z': [], 'y': [], 'x': ['z']}) == ['y', 'z', 'x']
try:
    topo_sort({'a': ['b'], 'b': ['a']})
except ValueError:
    pass
else:
    raise AssertionError('cycle not detected')

print('PASS')
