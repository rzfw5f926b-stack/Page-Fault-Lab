from .errors import TransientError


def call_with_retry(fn, sleep, attempts=3, base_delay=0.1):
    delay = base_delay
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except TransientError as e:
            last = e
            if _ == attempts - 1:
                raise
            sleep(delay)
            delay *= 2
