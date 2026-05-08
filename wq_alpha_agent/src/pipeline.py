from __future__ import annotations

import argparse
import csv
from itertools import product
from pathlib import Path

import json

from .brain_api_client import BrainApiClient
from .duplicate_filter import deduplicate
from .experiment_logger import write_csv
from .failure_classifier import classify_failure
from .generator import GenerationConfig, generate_candidates
from .mutator import expand_variants


def load_seed(path: Path):
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row["alpha_expr"] for row in reader]


def run_pipeline(config_path: Path, seed_file: Path):
    config = json.loads(config_path.read_text(encoding="utf-8"))

    # 阶段一：Alpha101 + API 工具 + 实验记录
    seed_alphas = load_seed(seed_file)
    client = BrainApiClient()

    # 阶段二：候选生成 + 去重 + 变体 + 失败分类
    candidates = generate_candidates(
        seed_alphas,
        GenerationConfig(
            llm_enabled=config.get("llm_enabled", False),
            max_candidates=config.get("max_candidates", 100),
        ),
    )
    expanded = expand_variants(candidates)
    unique_alphas = deduplicate(expanded)

    registry_rows = []
    failure_rows = []
    accepted_rows = []

    # 阶段三：多维实验矩阵
    for region, universe, decay, neutralization, delay in product(
        config["regions"],
        config["universes"],
        config["decays"],
        config["neutralizations"],
        config["delays"],
    ):
        for alpha_expr in unique_alphas:
            metrics = client.simulate_alpha(alpha_expr, region, universe, decay, neutralization, delay)
            row = {
                "region": region,
                "universe": universe,
                "decay": decay,
                "neutralization": neutralization,
                "delay": delay,
                "alpha_expr": alpha_expr,
                **metrics,
            }
            registry_rows.append(row)

            passed = (
                metrics["sharpe"] >= config["min_sharpe"]
                and metrics["fitness"] >= config["min_fitness"]
                and metrics["turnover"] <= config["max_turnover"]
            )
            if passed:
                accepted_rows.append(row)
            else:
                failure_rows.append({**row, "failure_reason": classify_failure(metrics)})

    out = Path("wq_alpha_agent/experiments")
    write_csv(out / "registry.csv", registry_rows)
    write_csv(out / "failure_log.csv", failure_rows)
    write_csv(out / "accepted_alphas.csv", accepted_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    args = parser.parse_args()
    run_pipeline(args.config, args.seed_file)
