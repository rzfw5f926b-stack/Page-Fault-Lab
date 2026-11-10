import io
import json
import os
import tempfile
import unittest

from todo.cli import main


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.d.name, "t.json")

    def tearDown(self):
        self.d.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        main(["--file", self.path, *argv], out)
        return out.getvalue().splitlines()

    def test_priority_shown(self):
        self.run_cli("add", "Buy milk", "--priority", "high")
        self.run_cli("add", "Read")
        self.assertEqual(self.run_cli("list"), ["1 [ ] Buy milk (high)", "2 [ ] Read"])

    def test_sort(self):
        self.run_cli("add", "a", "--priority", "low")
        self.run_cli("add", "b", "--priority", "high")
        self.run_cli("add", "c")
        got = [line.split()[0] for line in self.run_cli("list", "--sort", "priority")]
        self.assertEqual(got, ["2", "3", "1"])

    def test_file_version(self):
        self.run_cli("add", "a")
        with open(self.path) as f:
            self.assertEqual(json.load(f)["version"], 2)
