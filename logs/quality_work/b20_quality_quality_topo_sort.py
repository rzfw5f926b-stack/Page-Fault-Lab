from collections import defaultdict
from heapq import heapify, heappop, heappush
from typing import Dict, List

def topo_sort(deps: Dict[str, List[str]]) -> List[str]:
    """
    Perform a topological sort on a dependency graph.

    Parameters
    ----------
    deps : dict[str, list[str]]
        Mapping from an item to the list of items it depends on.

    Returns
    -------
    list[str]
        A list of items sorted so that each item appears after all of its
        dependencies. Items that appear only as dependencies are also
        included. When multiple items are ready at the same time, they are
        returned in alphabetical order.

    Raises
    ------
    ValueError
        If the dependency graph contains a cycle.
    """
    # Gather all nodes (keys + dependencies)
    nodes = set(deps.keys())
    for dep_list in deps.values():
        nodes.update(dep_list)

    # Compute indegrees and adjacency list
    indegree = {node: 0 for node in nodes}
    adjacency = defaultdict(list)

    for node, dep_list in deps.items():
        for dep in dep_list:
            adjacency[dep].append(node)
            indegree[node] += 1

    # Initialize heap with nodes that have no incoming edges
    heap = [node for node in nodes if indegree[node] == 0]
    heapify(heap)

    result = []

    while heap:
        node = heappop(heap)
        result.append(node)
        for neighbor in adjacency[node]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                heappush(heap, neighbor)

    if len(result) != len(nodes):
        raise ValueError("Cycle detected in dependency graph")

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
