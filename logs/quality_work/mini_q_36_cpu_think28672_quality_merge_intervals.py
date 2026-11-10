def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged



data = [(5, 7), (1, 3), (2, 4), (8, 10), (10, 12)]
copy = list(data)
assert merge_intervals(data) == [(1, 4), (5, 7), (8, 12)]
assert data == copy
assert merge_intervals([]) == []
assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]
assert merge_intervals([(3, 3)]) == [(3, 3)]

print('PASS')
