from .errors import TransientError


def call_with_retry(fn, sleep, attempts=3, base_delay=0.1):
    delay = base_delay
    for attempt in range(attempts):
        try:
            return fn()
        except TransientError:
            if attempt == attempts - 1:
                raise
            sleep(delay)
            delay *= 2
