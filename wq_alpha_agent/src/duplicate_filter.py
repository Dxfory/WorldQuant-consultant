from __future__ import annotations

import re
from typing import Iterable, List

_SPACE = re.compile(r"\s+")


def _canonical(expr: str) -> str:
    return _SPACE.sub("", expr.lower())


def deduplicate(expressions: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for expr in expressions:
        c = _canonical(expr)
        if c in seen:
            continue
        seen.add(c)
        out.append(expr)
    return out
