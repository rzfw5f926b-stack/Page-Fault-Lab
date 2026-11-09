import unittest

from clients.errors import PermanentError, TransientError
from clients.orders import OrdersClient
from clients.retry import call_with_retry
from clients.users import UsersClient


def flaky(failures, result="ok", exc=TransientError):
    state = {"left": failures}

    def transport(method, path):
        if state["left"]:
            state["left"] -= 1
            raise exc("x")
        return result
    return transport


class T(unittest.TestCase):
    def test_retry_returns(self):
        slept = []
        calls = []
        self.assertEqual(call_with_retry(lambda: calls.append(1) or "v", slept.append), "v")
        self.assertEqual(slept, [])

    def test_users_backoff(self):
        slept = []
        self.assertEqual(UsersClient(flaky(2), slept.append).get_user(1), "ok")
        self.assertEqual(slept, [0.1, 0.2])

    def test_users_permanent_not_retried(self):
        slept = []
        with self.assertRaises(PermanentError):
            UsersClient(flaky(1, exc=PermanentError), slept.append).get_user(1)
        self.assertEqual(slept, [])

    def test_orders_exhausted(self):
        slept = []
        with self.assertRaises(TransientError):
            OrdersClient(flaky(5), slept.append).get_order(1)
        self.assertEqual(slept, [0.1, 0.2])
