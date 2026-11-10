import time

from .retry import call_with_retry


class UsersClient:
    def __init__(self, transport, sleep=time.sleep):
        self.transport = transport
        self.sleep = sleep

    def get_user(self, user_id):
        return call_with_retry(
            lambda: self.transport("GET", f"/users/{user_id}"),
            self.sleep,
        )
