def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    
    # Sort intervals by start time
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    
    merged = [sorted_intervals[0]]
    
    for current_start, current_end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        
        # If current interval overlaps or touches the last merged interval
        if current_start <= last_end:
            # Merge them by extending the end time
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            # No overlap, add the current interval
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
