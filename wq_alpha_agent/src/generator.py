from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class GenerationConfig:
    llm_enabled: bool = False
    max_candidates: int = 100


def generate_candidates(seed_alphas: Iterable[str], cfg: GenerationConfig) -> List[str]:
    seeds = [s.strip() for s in seed_alphas if s and s.strip()]
    candidates = list(seeds)

    # 规则化扩展（可替代全随机）
    templates = [
        "rank({x})",
        "zscore({x})",
        "ts_mean({x}, 10)",
        "ts_rank({x}, 20)",
    ]
    for expr in seeds:
        for tpl in templates:
            candidates.append(tpl.format(x=expr))

    # LLM 入口（这里保留可插拔接口，默认关闭）
    if cfg.llm_enabled:
        candidates.extend([f"group_rank({expr}, sector)" for expr in seeds])

    return candidates[: cfg.max_candidates]
