from __future__ import annotations
from typing import List, Tuple

def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Merge overlapping or touching closed intervals.

    Parameters
    ----------
    intervals : list[tuple[int, int]]
        A list of (start, end) tuples. The input list is not modified.

    Returns
    -------
    list[tuple[int, int]]
        A new list of merged intervals sorted by start.
    """
    if not intervals:
        return []

    # Work on a copy to avoid mutating the input
    sorted_intervals = sorted(intervals, key=lambda x: x[0])

    merged: List[Tuple[int, int]] = []
    current_start, current_end = sorted_intervals[0]

    for start, end in sorted_intervals[1:]:
        if start <= current_end:  # overlapping or touching
            current_end = max(current_end, end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end

    merged.append((current_start, current_end))
    return merged



data = [(5, 7), (1, 3), (2, 4), (8, 10), (10, 12)]
copy = list(data)
assert merge_intervals(data) == [(1, 4), (5, 7), (8, 12)]
assert data == copy
assert merge_intervals([]) == []
assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]
assert merge_intervals([(3, 3)]) == [(3, 3)]

print('PASS')
