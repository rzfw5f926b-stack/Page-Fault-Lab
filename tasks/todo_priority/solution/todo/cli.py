import argparse
import sys

from .model import Task
from .store import Store

RANK = {"high": 0, "normal": 1, "low": 2}


def build_parser():
    p = argparse.ArgumentParser(prog="todo")
    p.add_argument("--file", default="todo.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("title")
    a.add_argument("--priority", choices=list(RANK), default="normal")
    d = sub.add_parser("done")
    d.add_argument("id", type=int)
    ls = sub.add_parser("list")
    ls.add_argument("--sort", choices=["priority"])
    return p


def main(argv, out=sys.stdout):
    args = build_parser().parse_args(argv)
    store = Store(args.file)
    tasks = store.load()
    if args.cmd == "add":
        next_id = max((t.id for t in tasks), default=0) + 1
        tasks.append(Task(next_id, args.title, priority=args.priority))
        store.save(tasks)
    elif args.cmd == "done":
        for t in tasks:
            if t.id == args.id:
                t.done = True
        store.save(tasks)
    else:
        key = (lambda t: (RANK[t.priority], t.id)) if args.sort else (lambda t: t.id)
        for t in sorted(tasks, key=key):
            mark = "x" if t.done else " "
            suffix = "" if t.priority == "normal" else f" ({t.priority})"
            print(f"{t.id} [{mark}] {t.title}{suffix}", file=out)
    return 0
