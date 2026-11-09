from .errors import CalcError

LEVELS = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take_op(self, op):
        if self.peek() == ("OP", op):
            self.i += 1
            return True
        return False

    def expect(self, op):
        if not self.take_op(op):
            raise CalcError(f"expected {op!r}")

    def binary(self, level):
        if level > 2:
            return self.unary()
        node = self.binary(level + 1)
        while True:
            kind, op = self.peek()
            if kind == "OP" and LEVELS.get(op) == level:
                self.i += 1
                node = ("bin", op, node, self.binary(level + 1))
            else:
                return node

    def unary(self):
        if self.take_op("-"):
            return ("neg", self.unary())
        return self.power()

    def power(self):
        base = self.atom()
        if self.take_op("**"):
            return ("bin", "**", base, self.unary())
        return base

    def atom(self):
        kind, value = self.peek()
        if kind == "NUM":
            self.i += 1
            return ("num", value)
        if kind == "NAME":
            self.i += 1
            if not self.take_op("("):
                return ("var", value)
            args = [self.binary(1)] if self.peek() != ("OP", ")") else []
            while self.take_op(","):
                args.append(self.binary(1))
            self.expect(")")
            return ("call", value, args)
        if self.take_op("("):
            node = self.binary(1)
            self.expect(")")
            return node
        raise CalcError("expected a value")


def parse(tokens):
    p = Parser(tokens)
    node = p.binary(1)
    if p.i != len(tokens):
        raise CalcError("trailing tokens")
    return node
