from __future__ import annotations

from typing import Iterable, List


def expand_variants(expressions: Iterable[str], windows=(5, 10, 20), decays=(2, 4, 8)) -> List[str]:
    out: List[str] = []
    for expr in expressions:
        base = expr.strip()
        if not base:
            continue
        out.append(base)
        for w in windows:
            out.append(f"ts_mean({base}, {w})")
            out.append(f"ts_rank({base}, {w})")
        for d in decays:
            out.append(f"decay_linear({base}, {d})")
    return out
