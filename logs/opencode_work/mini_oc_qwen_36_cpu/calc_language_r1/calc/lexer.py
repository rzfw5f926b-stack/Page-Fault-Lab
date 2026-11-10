from .errors import CalcError


def tokenize(src):
    tokens = []
    i = 0
    while i < len(src):
        ch = src[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit():
            j = i
            while j < len(src) and src[j].isdigit():
                j += 1
            if j < len(src) and src[j] == ".":
                j += 1
                while j < len(src) and src[j].isdigit():
                    j += 1
                tokens.append(("NUM", float(src[i:j])))
            else:
                tokens.append(("NUM", int(src[i:j])))
            i = j
        elif ch == "*":
            if i + 1 < len(src) and src[i + 1] == "*":
                tokens.append(("OP", "**"))
                i += 2
            else:
                tokens.append(("OP", "*"))
                i += 1
        elif ch in "+-/%":
            tokens.append(("OP", ch))
            i += 1
        elif ch == "/":
            tokens.append(("OP", "/"))
            i += 1
        elif ch == "(":
            tokens.append(("LPAREN", "("))
            i += 1
        elif ch == ")":
            tokens.append(("RPAREN", ")"))
            i += 1
        elif ch == ",":
            tokens.append(("COMMA", ","))
            i += 1
        elif ch.isalpha() or ch == "_":
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] == "_"):
                j += 1
            tokens.append(("NAME", src[i:j]))
            i = j
        else:
            raise CalcError(f"unexpected character {ch!r}")
    return tokens
