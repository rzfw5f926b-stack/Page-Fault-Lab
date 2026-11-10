from .errors import CalcError


def evaluate(node, env):
    if node[0] == "num":
        return node[1]

    if node[0] == "name":
        name = node[1]
        if name in env:
            return env[name]
        raise CalcError(f"unknown variable {name!r}")

    if node[0] == "unary":
        _, op, operand = node
        if op == "-":
            return -evaluate(operand, env)
        raise CalcError(f"unknown unary operator {op!r}")

    if node[0] == "bin":
        _, op, left, right = node
        a = evaluate(left, env)
        b = evaluate(right, env)
        return _binop(op, a, b)

    if node[0] == "call":
        _, func, args = node
        return _call(func, args, env)

    raise CalcError(f"unknown node type {node[0]!r}")


def _binop(op, a, b):
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


def _min(args, env):
    if len(args) < 1:
        raise CalcError("min requires at least one argument")
    values = [evaluate(a, env) for a in args]
    return min(values)


def _max(args, env):
    if len(args) < 1:
        raise CalcError("max requires at least one argument")
    values = [evaluate(a, env) for a in args]
    return max(values)


def _abs(args, env):
    if len(args) != 1:
        raise CalcError("abs requires exactly one argument")
    return abs(evaluate(args[0], env))


_BUILTINS = {
    "min": _min,
    "max": _max,
    "abs": _abs,
}


def _call(name, args, env):
    if name in _BUILTINS:
        return _BUILTINS[name](args, env)
    raise CalcError(f"unknown function {name!r}")
