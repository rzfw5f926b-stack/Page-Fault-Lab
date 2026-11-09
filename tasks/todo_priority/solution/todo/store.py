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
            data = json.load(f)
        if isinstance(data, dict):
            if data.get("version") != 2:
                raise ValueError(f"unsupported version: {data.get('version')}")
            data = data["tasks"]
        return [Task.from_dict(d) for d in data]

    def save(self, tasks):
        with open(self.path, "w") as f:
            json.dump({"version": 2, "tasks": [t.to_dict() for t in tasks]}, f, indent=2)
