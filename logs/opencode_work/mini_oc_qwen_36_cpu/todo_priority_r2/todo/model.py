from dataclasses import asdict, dataclass


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    priority: str = "normal"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)
