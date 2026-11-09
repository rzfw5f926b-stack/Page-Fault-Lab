def merge_intervals(intervals):
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = []
    for interval in sorted_intervals:
        start = interval[0]
        end = interval[1]
        if merged and merged[-1][1] >= start:
            new_start = merged[-1][0]
            new_end = max(merged[-1][1], end)
            merged[-1] = (new_start, new_end)
        else:
            merged.append(interval)
    return merged



data = [(5, 7), (1, 3), (2, 4), (8, 10), (10, 12)]
copy = list(data)
assert merge_intervals(data) == [(1, 4), (5, 7), (8, 12)]
assert data == copy
assert merge_intervals([]) == []
assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]
assert merge_intervals([(3, 3)]) == [(3, 3)]

print('PASS')
