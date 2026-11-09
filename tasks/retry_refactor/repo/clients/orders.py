import time

from .errors import TransientError


class OrdersClient:
    def __init__(self, transport, sleep=time.sleep):
        self.transport = transport
        self.sleep = sleep

    def get_order(self, order_id):
        delay = 0.1
        for attempt in range(3):
            try:
                return self.transport("GET", f"/orders/{order_id}")
            except TransientError:
                if attempt == 2:
                    raise
                self.sleep(delay)
                delay *= 2

    def cancel_order(self, order_id):
        delay = 0.1
        for attempt in range(3):
            try:
                return self.transport("POST", f"/orders/{order_id}/cancel")
            except TransientError:
                if attempt == 2:
                    raise
                self.sleep(delay)
                delay *= 2
