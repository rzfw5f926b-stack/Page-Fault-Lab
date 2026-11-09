import argparse
import sys

from .model import Task
from .store import Store


def build_parser():
    p = argparse.ArgumentParser(prog="todo")
    p.add_argument("--file", default="todo.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("title")
    d = sub.add_parser("done")
    d.add_argument("id", type=int)
    sub.add_parser("list")
    return p


def main(argv, out=sys.stdout):
    args = build_parser().parse_args(argv)
    store = Store(args.file)
    tasks = store.load()
    if args.cmd == "add":
        next_id = max((t.id for t in tasks), default=0) + 1
        tasks.append(Task(next_id, args.title))
        store.save(tasks)
    elif args.cmd == "done":
        for t in tasks:
            if t.id == args.id:
                t.done = True
        store.save(tasks)
    else:
        for t in sorted(tasks, key=lambda t: t.id):
            mark = "x" if t.done else " "
            print(f"{t.id} [{mark}] {t.title}", file=out)
    return 0
