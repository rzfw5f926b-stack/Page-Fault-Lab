from collections import defaultdict, deque

def topo_sort(deps: dict[str, list[str]]) -> list[str]:
    # Build reverse dependency map and in-degree count
    reverse_deps = defaultdict(list)
    in_degree = defaultdict(int)
    
    # Initialize all nodes
    all_nodes = set(deps.keys())
    for node, dependencies in deps.items():
        all_nodes.add(node)
        for dep in dependencies:
            all_nodes.add(dep)
            reverse_deps[dep].append(node)
            in_degree[node] += 1
    
    # Find all nodes with no incoming edges (in-degree = 0)
    queue = deque()
    for node in all_nodes:
        if in_degree[node] == 0:
            queue.append(node)
    
    # Sort queue alphabetically to ensure alphabetical order
    queue = deque(sorted(queue))
    
    result = []
    
    while queue:
        # Get the lexicographically smallest node
        current = queue.popleft()
        result.append(current)
        
        # Remove current node and update in-degrees
        for neighbor in reverse_deps[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
        
        # Sort queue alphabetically again
        queue = deque(sorted(queue))
    
    # Check for cycles
    if len(result) != len(all_nodes):
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
