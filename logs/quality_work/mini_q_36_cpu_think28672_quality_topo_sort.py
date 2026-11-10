import heapq

def topo_sort(deps: dict[str, list[str]]) -> list[str]:
    all_nodes = set(deps.keys())
    for deps_list in deps.values():
        all_nodes.update(deps_list)
        
    in_degree = {node: 0 for node in all_nodes}
    adj = {node: [] for node in all_nodes}
    
    for item, dependencies in deps.items():
        unique_deps = set(dependencies)
        in_degree[item] = len(unique_deps)
        for dep in unique_deps:
            adj[dep].append(item)
            
    heap = [node for node in all_nodes if in_degree[node] == 0]
    heapq.heapify(heap)
    
    result = []
    while heap:
        node = heapq.heappop(heap)
        result.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                heapq.heappush(heap, neighbor)
                
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
