import json
import os

from .model import Task


class Store:
    def __init__(self, path):
        self.path = path

    def load(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [Task.from_dict(d) for d in json.load(f)]

    def save(self, tasks):
        with open(self.path, "w") as f:
            json.dump([t.to_dict() for t in tasks], f, indent=2)
