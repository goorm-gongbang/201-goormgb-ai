"""Arithmetic challenge solver (MVP).

Security prompt is currently a simple arithmetic quiz (e.g., "3 + 4 = ?").
Per secure coding guide, do not use eval().
"""

from __future__ import annotations

import re


_EXPR_RE = re.compile(r"(-?\d+)\s*([+\-*/])\s*(-?\d+)")


class ArithmeticParseError(ValueError):
    pass


def solve_arithmetic_prompt(prompt: str) -> str:
    """Solve a basic integer arithmetic expression contained in the prompt.

    Supports: +, -, *, /
    Returns an integer string when division is exact, otherwise a float string.
    """
    m = _EXPR_RE.search(prompt)
    if not m:
        raise ArithmeticParseError(f"unsupported prompt: {prompt!r}")

    a = int(m.group(1))
    op = m.group(2)
    b = int(m.group(3))

    if op == "+":
        return str(a + b)
    if op == "-":
        return str(a - b)
    if op == "*":
        return str(a * b)
    if op == "/":
        if b == 0:
            raise ArithmeticParseError("division by zero")
        q, r = divmod(a, b)
        if r == 0:
            return str(q)
        return str(a / b)

    raise ArithmeticParseError(f"unsupported operator: {op!r}")

