import io
import json
import os
import tempfile
import unittest

from todo.cli import main
from todo.model import Task
from todo.store import Store


class H(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.d.name, "t.json")

    def tearDown(self):
        self.d.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        main(["--file", self.path, *argv], out)
        return out.getvalue().splitlines()

    def test_legacy_file_migrates(self):
        with open(self.path, "w") as f:
            json.dump([{"id": 1, "title": "old", "done": True}], f)
        tasks = Store(self.path).load()
        self.assertEqual(tasks[0].priority, "normal")
        self.assertTrue(tasks[0].done)
        Store(self.path).save(tasks)
        with open(self.path) as f:
            data = json.load(f)
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["tasks"][0]["priority"], "normal")

    def test_unknown_version(self):
        with open(self.path, "w") as f:
            json.dump({"version": 3, "tasks": []}, f)
        with self.assertRaises(ValueError):
            Store(self.path).load()

    def test_invalid_priority(self):
        with self.assertRaises(SystemExit) as c:
            self.run_cli("add", "x", "--priority", "urgent")
        self.assertEqual(c.exception.code, 2)

    def test_ties_by_id_and_done_keeps_priority(self):
        for p in ("low", "high", "high", "normal"):
            self.run_cli("add", "t", "--priority", p)
        self.run_cli("done", "2")
        lines = self.run_cli("list", "--sort", "priority")
        self.assertEqual(lines, ["2 [x] t (high)", "3 [ ] t (high)", "4 [ ] t", "1 [ ] t (low)"])

    def test_default_list_by_id(self):
        self.run_cli("add", "a", "--priority", "low")
        self.run_cli("add", "b", "--priority", "high")
        self.assertEqual([l.split()[0] for l in self.run_cli("list")], ["1", "2"])

    def test_model_default(self):
        self.assertEqual(Task(1, "x").priority, "normal")
