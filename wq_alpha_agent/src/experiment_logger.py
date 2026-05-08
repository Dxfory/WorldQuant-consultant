from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping


def write_csv(path: Path, rows: Iterable[Mapping]):
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
