import math

from .errors import CalcError


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
        raise CalcError(f"unknown operator {op!r}")

    if kind == "unary":
        _, op, operand = node
        val = evaluate(operand, env)
        if op == "+":
            return val
        if op == "-":
            return -val
        raise CalcError(f"unknown unary operator {op!r}")

    if kind == "call":
        _, name, args = node
        evaluated = [evaluate(a, env) for a in args]
        if name == "min":
            if not evaluated:
                raise CalcError("min requires at least 1 argument")
            return min(evaluated)
        if name == "max":
            if not evaluated:
                raise CalcError("max requires at least 1 argument")
            return max(evaluated)
        if name == "abs":
            if len(evaluated) != 1:
                raise CalcError("abs requires exactly 1 argument")
            return abs(evaluated[0])
        raise CalcError(f"unknown function {name!r}")

    raise CalcError(f"unknown AST node type {kind!r}")
