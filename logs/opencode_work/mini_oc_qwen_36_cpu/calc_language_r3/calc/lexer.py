from .errors import CalcError

_KEYWORDS = {"min", "max", "abs"}


def tokenize(src):
    if not src or src.strip() == "":
        raise CalcError("empty input")
    tokens = []
    i = 0
    length = len(src)
    while i < length:
        ch = src[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit():
            j = i
            while j < length and src[j].isdigit():
                j += 1
            start = j
            if j < length and src[j] == ".":
                j += 1
                while j < length and src[j].isdigit():
                    j += 1
                if j == start:
                    raise CalcError(f"malformed number at position {i}")
                tokens.append(("NUM", float(src[i:j])))
            else:
                tokens.append(("NUM", int(src[i:start])))
            i = j
        elif ch == "*":
            if i + 1 < length and src[i + 1] == "*":
                tokens.append(("OP", "**"))
                i += 2
            else:
                tokens.append(("OP", ch))
                i += 1
        elif ch in "+-":
            tokens.append(("OP", ch))
            i += 1
        elif ch == "/":
            tokens.append(("OP", "/"))
            i += 1
        elif ch == "%":
            tokens.append(("OP", "%"))
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
            while j < length and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            if word in _KEYWORDS:
                tokens.append(("FUNC", word))
            else:
                tokens.append(("NAME", word))
            i = j
        else:
            raise CalcError(f"unexpected character {ch!r}")
    return tokens
