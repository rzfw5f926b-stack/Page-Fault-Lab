The `calc` package evaluates expressions but only supports integers with `+` and `-`. Extend it. Keep the lexer, parser and evaluator as separate modules, and keep `calc(src, env=None)` as the entry point.

Add:
1. Decimal numbers such as `1.5`.
2. `*`, `/`, `%` and `**`. `/` is true division. `*`, `/`, `%` bind tighter than `+`, `-` and are left associative.
3. `**` binds tighter than unary minus and is right associative: `-2**2` is `-4`, `2**3**2` is `512`, and `2**-1` is `0.5`.
4. Parentheses and unary minus.
5. Variables looked up in `env`.
6. Function calls `min(...)`, `max(...)` and `abs(x)` with comma separated arguments. `min` and `max` take one or more arguments, `abs` exactly one.

Every error must raise `CalcError` from `calc.errors`: malformed input (including empty input and trailing tokens such as `1 2`), division or modulo by zero, unknown variables, unknown functions and wrong argument counts.
