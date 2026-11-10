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
        if isinstance(data, list):
            for t in data:
                t.setdefault("priority", "normal")
            return [Task.from_dict(d) for d in data]
        if isinstance(data, dict):
            version = data.get("version")
            if version == 2:
                return [Task.from_dict(d) for d in data["tasks"]]
            raise ValueError(f"unsupported version: {version}")
        raise ValueError("unexpected data format")

    def save(self, tasks):
        with open(self.path, "w") as f:
            json.dump({"version": 2, "tasks": [t.to_dict() for t in tasks]}, f, indent=2)
