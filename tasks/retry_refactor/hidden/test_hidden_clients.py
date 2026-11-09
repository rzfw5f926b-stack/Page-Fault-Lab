import ast
import pathlib
import unittest
from unittest import mock

import clients.orders
import clients.users
from clients.errors import TransientError
from clients.orders import OrdersClient
from clients.retry import call_with_retry
from clients.users import UsersClient


class H(unittest.TestCase):
    def test_no_loops_left(self):
        for mod in (clients.orders, clients.users):
            tree = ast.parse(pathlib.Path(mod.__file__).read_text())
            loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]
            self.assertEqual(loops, [], mod.__name__)

    def test_custom_attempts_and_delay(self):
        slept = []

        def boom():
            raise TransientError("x")
        with self.assertRaises(TransientError):
            call_with_retry(boom, slept.append, attempts=4, base_delay=1)
        self.assertEqual(slept, [1, 2, 4])

    def test_one_attempt_never_sleeps(self):
        slept = []

        def boom():
            raise TransientError("x")
        with self.assertRaises(TransientError):
            call_with_retry(boom, slept.append, attempts=1)
        self.assertEqual(slept, [])

    def test_last_error_is_raised(self):
        errs = [TransientError("1"), TransientError("2"), TransientError("3")]

        def boom():
            raise errs.pop(0)
        with self.assertRaises(TransientError) as c:
            call_with_retry(boom, lambda s: None)
        self.assertEqual(str(c.exception), "3")

    def test_paths_unchanged(self):
        seen = []
        t = lambda m, p: seen.append((m, p)) or "ok"
        OrdersClient(t).get_order(7)
        OrdersClient(t).cancel_order(7)
        UsersClient(t).get_user(9)
        self.assertEqual(seen, [("GET", "/orders/7"), ("POST", "/orders/7/cancel"), ("GET", "/users/9")])

    def test_clients_delegate(self):
        for mod, call in ((clients.orders, lambda: OrdersClient(lambda m, p: 1).cancel_order(1)),
                          (clients.users, lambda: UsersClient(lambda m, p: 1).get_user(1))):
            with mock.patch.object(mod, "call_with_retry", return_value="patched"):
                self.assertEqual(call(), "patched")
