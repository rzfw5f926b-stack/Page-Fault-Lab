import time


class UsersClient:
    def __init__(self, transport, sleep=time.sleep):
        self.transport = transport
        self.sleep = sleep

    def get_user(self, user_id):
        last = None
        for _ in range(3):
            try:
                return self.transport("GET", f"/users/{user_id}")
            except Exception as e:
                last = e
                self.sleep(0.1)
        raise last
