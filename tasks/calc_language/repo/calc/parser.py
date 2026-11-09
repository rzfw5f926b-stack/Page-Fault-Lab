from .errors import CalcError


def parse(tokens):
    if not tokens or tokens[0][0] != "NUM":
        raise CalcError("expected number")
    node = ("num", tokens[0][1])
    i = 1
    while i < len(tokens):
        if tokens[i][0] != "OP" or i + 1 >= len(tokens) or tokens[i + 1][0] != "NUM":
            raise CalcError("malformed expression")
        node = ("bin", tokens[i][1], node, ("num", tokens[i + 1][1]))
        i += 2
    return node
