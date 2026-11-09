import time

from .retry import call_with_retry


class OrdersClient:
    def __init__(self, transport, sleep=time.sleep):
        self.transport = transport
        self.sleep = sleep

    def get_order(self, order_id):
        return call_with_retry(lambda: self.transport("GET", f"/orders/{order_id}"), self.sleep)

    def cancel_order(self, order_id):
        return call_with_retry(lambda: self.transport("POST", f"/orders/{order_id}/cancel"), self.sleep)
