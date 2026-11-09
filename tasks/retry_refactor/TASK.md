`clients/orders.py` and `clients/users.py` each contain their own copy of retry logic, and the copy in `users.py` has bugs. Refactor it.

1. Create `clients/retry.py` with `call_with_retry(fn, sleep, attempts=3, base_delay=0.1)`. It calls `fn()` and returns its result.
2. Only `TransientError` is retried. Any other exception propagates immediately without sleeping.
3. Backoff is exponential: with the defaults it sleeps 0.1 then 0.2 between the three attempts. It never sleeps after the last attempt. When attempts run out, the last `TransientError` is raised.
4. All methods of `OrdersClient` and `UsersClient` must use `call_with_retry`, and no `for` or `while` loops may remain in `orders.py` or `users.py`.

Public client methods and constructor signatures must not change.
