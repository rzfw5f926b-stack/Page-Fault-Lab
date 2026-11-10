from .errors import CalcError


class Parser:
    """Recursive-descent parser with precedence levels:
    expr    → additive (+, -)       left assoc
    term    → multiplicative (*, /, %)  left assoc
    power   → exponentiation (**)     right assoc
    unary   → unary +/-             right assoc
    atom    → num, name, call, (...)
    """

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def parse(self):
        if not self.tokens:
            raise CalcError("expected expression, got nothing")
        node = self.parse_expr()
        if self.pos < len(self.tokens):
            raise CalcError(f"unexpected token {self.tokens[self.pos]}")
        return node

    # ── helpers ──────────────────────────────────────────
    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, typ, val=None):
        tok = self.peek()
        if tok is None or tok[0] != typ or (val is not None and tok[1] != val):
            raise CalcError(f"expected {typ!r} {val!r}, got {tok!r}")
        return self.advance()

    # ── precedence levels ────────────────────────────────
    def parse_expr(self):
        """Additive: + and -, left associative."""
        left = self.parse_term()
        while True:
            tok = self.peek()
            if tok and tok[0] == "OP" and tok[1] in ("+", "-"):
                op = self.advance()[1]
                right = self.parse_term()
                left = ("bin", op, left, right)
            else:
                break
        return left

    def parse_term(self):
        """Multiplicative: *, /, %, left associative."""
        left = self.parse_power()
        while True:
            tok = self.peek()
            if tok and tok[0] == "OP" and tok[1] in ("*", "/", "%"):
                op = self.advance()[1]
                right = self.parse_power()
                left = ("bin", op, left, right)
            else:
                break
        return left

    def parse_power(self):
        """Exponentiation: **, right associative."""
        base = self.parse_unary()
        tok = self.peek()
        if tok and tok[0] == "OP" and tok[1] == "**":
            self.advance()
            exp = self.parse_power()  # right assoc → recurse here
            return ("bin", "**", base, exp)
        return base

    def parse_unary(self):
        """Unary +/- (lower precedence than **)."""
        tok = self.peek()
        if tok and tok[0] == "OP" and tok[1] in ("+", "-"):
            op = self.advance()[1]
            operand = self.parse_power()
            return ("unary", op, operand)
        return self.parse_atom()

    def parse_atom(self):
        """Number, variable, function call, or parenthesized expression."""
        tok = self.peek()
        if tok is None:
            raise CalcError("unexpected end of expression")

        if tok[0] == "NUM":
            self.advance()
            return ("num", tok[1])

        if tok[0] == "NAME":
            name = self.advance()[1]
            # Check for function call
            next_tok = self.peek()
            if next_tok and next_tok[0] == "LPAREN":
                self.advance()  # consume '('
                args = []
                if self.peek() and self.peek()[0] != "RPAREN":
                    args.append(self.parse_expr())
                    while self.peek() and self.peek()[0] == "COMMA":
                        self.advance()  # consume ','
                        args.append(self.parse_expr())
                self.expect("RPAREN", ")")
                return ("call", name, args)
            return ("var", name)

        if tok[0] == "LPAREN":
            self.advance()  # consume '('
            node = self.parse_expr()
            self.expect("RPAREN", ")")
            return node

        raise CalcError(f"unexpected token {tok!r}")


def parse(tokens):
    return Parser(tokens).parse()
