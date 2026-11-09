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
            tokens.append(("NUM", int(src[i:j])))
            i = j
        elif ch in "+-":
            tokens.append(("OP", ch))
            i += 1
        else:
            raise CalcError(f"unexpected character {ch!r}")
    return tokens
