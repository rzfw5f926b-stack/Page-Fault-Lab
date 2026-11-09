def evaluate(node, env):
    if node[0] == "num":
        return node[1]
    _, op, left, right = node
    a, b = evaluate(left, env), evaluate(right, env)
    return a + b if op == "+" else a - b
