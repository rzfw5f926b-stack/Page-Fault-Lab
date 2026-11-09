from .errors import CalcError

ARITY = {"min": (lambda *a: min(a), 1, None), "max": (lambda *a: max(a), 1, None), "abs": (abs, 1, 1)}


def evaluate(node, env):
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "neg":
        return -evaluate(node[1], env)
    if kind == "var":
        if node[1] not in env:
            raise CalcError(f"unknown variable {node[1]}")
        return env[node[1]]
    if kind == "call":
        if node[1] not in ARITY:
            raise CalcError(f"unknown function {node[1]}")
        fn, low, high = ARITY[node[1]]
        n = len(node[2])
        if n < low or (high is not None and n > high):
            raise CalcError(f"wrong argument count for {node[1]}")
        return fn(*[evaluate(a, env) for a in node[2]])
    _, op, left, right = node
    a, b = evaluate(left, env), evaluate(right, env)
    try:
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        if op == "%":
            return a % b
        return a ** b
    except ZeroDivisionError as e:
        raise CalcError(str(e)) from e
