from .errors import CalcError

_OPERATORS = {"+", "-", "*", "/", "%", "**"}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def current(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_type=None, expected_op=None):
        tok = self.current()
        if tok is None:
            raise CalcError("unexpected end of input")
        if expected_type and tok[0] != expected_type:
            raise CalcError(f"expected {expected_type} but got {tok[0]!r}")
        if expected_op and tok[1] != expected_op:
            raise CalcError(f"expected {expected_op!r} but got {tok[1]!r}")
        self.pos += 1
        return tok

    # ---- entry point ----
    def parse(self):
        node = self.parse_add()
        if self.current() is not None:
            raise CalcError("unexpected trailing token")
        return node

    # ---- grammar ----
    # add_expr : mul_expr (('+' | '-') mul_expr)*
    def parse_add(self):
        node = self.parse_mul()
        while True:
            tok = self.current()
            if tok and tok[0] == "OP" and tok[1] in ("+", "-"):
                self.pos += 1
                right = self.parse_mul()
                node = ("bin", tok[1], node, right)
            else:
                break
        return node

    # mul_expr : unary_expr (('*' | '/' | '%') unary_expr)*
    def parse_mul(self):
        node = self.parse_unary()
        while True:
            tok = self.current()
            if tok and tok[0] == "OP" and tok[1] in ("*", "/", "%"):
                self.pos += 1
                right = self.parse_unary()
                node = ("bin", tok[1], node, right)
            else:
                break
        return node

    # unary_expr : '-' unary_expr | power_expr
    def parse_unary(self):
        tok = self.current()
        if tok and tok[0] == "OP" and tok[1] == "-":
            self.pos += 1
            operand = self.parse_unary()
            return ("unary", "-", operand)
        return self.parse_power()

    # power_expr : primary ('**' power_expr)?
    def parse_power(self):
        node = self.parse_primary()
        tok = self.current()
        if tok and tok[0] == "OP" and tok[1] == "**":
            self.pos += 1
            right = self.parse_power()  # right associative
            return ("bin", "**", node, right)
        return node

    # primary : NUM | NAME | FUNC '(' [args] ')' | '(' add_expr ')'
    def parse_primary(self):
        tok = self.current()
        if tok is None:
            raise CalcError("unexpected end of input")

        if tok[0] == "NUM":
            self.pos += 1
            return ("num", tok[1])

        if tok[0] in ("NAME", "FUNC"):
            name = tok[1]
            self.pos += 1
            open_tok = self.current()
            if open_tok and open_tok[0] == "LPAREN":
                self.pos += 1
                args = self.parse_args()
                close_tok = self.consume("RPAREN", ")")
                return ("call", name, args)
            return ("name", name)

        if tok[0] == "LPAREN":
            self.pos += 1
            node = self.parse_add()
            self.consume("RPAREN", ")")
            return node

        if tok[0] == "OP":
            raise CalcError(f"unexpected operator {tok[1]!r}")

        raise CalcError(f"unexpected token {tok!r}")

    def parse_args(self):
        args = []
        if self.current() and self.current()[0] == "RPAREN":
            return args
        args.append(self.parse_add())
        while True:
            tok = self.current()
            if tok and tok[0] == "COMMA":
                self.pos += 1
                args.append(self.parse_add())
            elif tok and tok[0] == "RPAREN":
                break
            else:
                raise CalcError("expected ',' or ')'")
        return args


def parse(tokens):
    if not tokens:
        raise CalcError("empty input")
    parser = Parser(tokens)
    return parser.parse()
