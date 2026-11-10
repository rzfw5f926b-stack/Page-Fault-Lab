import json
import os

from .model import Task


VERSION = 2
SUPPORTED_VERSIONS = {2}


class Store:
    def __init__(self, path):
        self.path = path

    def load(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            data = json.load(f)
        if isinstance(data, list):
            for d in data:
                d.setdefault("priority", "normal")
            return [Task.from_dict(d) for d in data]
        if isinstance(data, dict):
            version = data.get("version")
            if version not in SUPPORTED_VERSIONS:
                raise ValueError(
                    f"Unsupported file version: {version}"
                )
            return [Task.from_dict(t) for t in data.get("tasks", [])]
        raise ValueError("Unexpected data format")

    def save(self, tasks):
        with open(self.path, "w") as f:
            json.dump({"version": VERSION, "tasks": [t.to_dict() for t in tasks]}, f, indent=2)
