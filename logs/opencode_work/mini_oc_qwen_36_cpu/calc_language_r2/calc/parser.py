from .errors import CalcError

BUILTINS = {
    "min": 1,  # min args, max args (variable arity)
    "max": 1,
    "abs": (1, 1),
}


def parse(tokens):
    if not tokens:
        raise CalcError("empty input")
    pos, node = _parse_expr(tokens, 0)
    if pos < len(tokens):
        raise CalcError(f"unexpected token {tokens[pos]!r}")
    return node


def _parse_expr(tokens, i):
    """Parse add/sub (left associative)."""
    i, left = _parse_term(tokens, i)
    while i < len(tokens) and tokens[i] == ("OP", "+") or i < len(tokens) and tokens[i] == ("OP", "-"):
        op = tokens[i][1]
        i += 1
        if i >= len(tokens):
            raise CalcError("malformed expression")
        i, right = _parse_term(tokens, i)
        left = ("bin", op, left, right)
    return i, left


def _parse_term(tokens, i):
    """Parse mul/div/mod (left associative)."""
    i, left = _parse_power(tokens, i)
    while i < len(tokens) and tokens[i][0] == "OP" and tokens[i][1] in ("*", "/", "%"):
        op = tokens[i][1]
        i += 1
        if i >= len(tokens):
            raise CalcError("malformed expression")
        i, right = _parse_power(tokens, i)
        left = ("bin", op, left, right)
    return i, left


def _parse_power(tokens, i):
    """Parse exponentiation (right associative)."""
    i, base = _parse_unary(tokens, i)
    if i < len(tokens) and tokens[i] == ("OP", "**"):
        i += 1
        if i >= len(tokens):
            raise CalcError("malformed expression")
        i, exp = _parse_power(tokens, i)  # right-recursive
        return i, ("bin", "**", base, exp)
    return i, base


def _parse_unary(tokens, i):
    """Parse unary minus."""
    if i < len(tokens) and tokens[i] == ("OP", "-"):
        i += 1
        if i >= len(tokens):
            raise CalcError("malformed expression")
        i, operand = _parse_power(tokens, i)
        return i, ("neg", operand)
    return _parse_atom(tokens, i)


def _parse_atom(tokens, i):
    """Parse numbers, identifiers (variables/functions), parenthesized expressions."""
    if i >= len(tokens):
        raise CalcError("unexpected end of input")

    tok = tokens[i]

    # Number
    if tok[0] == "NUM":
        return i + 1, ("num", tok[1])

    # Parenthesized expression
    if tok[0] == "LPAREN":
        i += 1
        i, node = _parse_expr(tokens, i)
        if i >= len(tokens) or tokens[i][0] != "RPAREN":
            raise CalcError("unexpected end of input")
        return i + 1, node

    # Identifier: variable or function call
    if tok[0] == "IDENT":
        name = tok[1]
        i += 1
        if i < len(tokens) and tokens[i][0] == "LPAREN":
            return _parse_call(tokens, i, name)
        return i, ("var", name)

    raise CalcError(f"unexpected token {tok!r}")


def _parse_call(tokens, i, name):
    """Parse function call: name( arg1, arg2, ... )."""
    i += 1  # consume (
    args = []
    if i < len(tokens) and tokens[i][0] != "RPAREN":
        i, arg = _parse_expr(tokens, i)
        args.append(arg)
        while i < len(tokens) and tokens[i][0] == "COMMA":
            i += 1
            if i >= len(tokens):
                raise CalcError("malformed expression")
            i, arg = _parse_expr(tokens, i)
            args.append(arg)
    if i >= len(tokens) or tokens[i][0] != "RPAREN":
        raise CalcError(f"expected ')' in function call")
    i += 1  # consume )

    if name == "min" or name == "max":
        min_args, max_args = 1, float("inf")
    else:
        min_args, max_args = BUILTINS.get(name, (0, 0))

    if name not in BUILTINS:
        raise CalcError(f"unknown function {name!r}")
    if not (min_args <= len(args) <= max_args):
        raise CalcError(f"{name}() expects {min_args if min_args == max_args else f'{min_args}-{max_args}'} argument(s)")

    return i, ("call", name, args)
