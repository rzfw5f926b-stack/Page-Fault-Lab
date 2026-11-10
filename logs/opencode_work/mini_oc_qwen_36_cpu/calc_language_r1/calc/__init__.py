from .evaluator import evaluate
from .lexer import tokenize
from .parser import parse


def calc(src, env=None):
    return evaluate(parse(tokenize(src)), env or {})
