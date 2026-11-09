import re

from .errors import CalcError

TOKEN = re.compile(r"\s*(?:(\d+\.\d+|\d+)|([A-Za-z_]\w*)|(\*\*|[-+*/%(),]))")


def tokenize(src):
    tokens = []
    i = 0
    src = src.rstrip()
    while i < len(src):
        m = TOKEN.match(src, i)
        if not m:
            raise CalcError(f"unexpected input at {i}")
        num, name, op = m.groups()
        if num:
            tokens.append(("NUM", float(num) if "." in num else int(num)))
            if m.end() < len(src) and (src[m.end()] == "." or src[m.end()].isalpha()):
                raise CalcError("malformed number")
        elif name:
            tokens.append(("NAME", name))
        else:
            tokens.append(("OP", op))
        i = m.end()
    return tokens
