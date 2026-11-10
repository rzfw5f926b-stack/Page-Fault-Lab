import math

from .errors import CalcError

BUILTINS = {
    "min": min,
    "max": max,
    "abs": abs,
}


def evaluate(node, env):
    kind = node[0]

    if kind == "num":
        return node[1]

    if kind == "var":
        name = node[1]
        if name not in env:
            raise CalcError(f"unknown variable {name!r}")
        return env[name]

    if kind == "bin":
        _, op, left, right = node
        a = evaluate(left, env)
        b = evaluate(right, env)
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise CalcError("division by zero")
            return a / b
        if op == "%":
            if b == 0:
                raise CalcError("modulo by zero")
            return a % b
        if op == "**":
            return a ** b

    if kind == "neg":
        return -evaluate(node[1], env)

    if kind == "call":
        _, name, args = node
        func = BUILTINS[name]
        evaluated = [evaluate(a, env) for a in args]
        return func(*evaluated)

    raise CalcError(f"unknown node type {kind!r}")
