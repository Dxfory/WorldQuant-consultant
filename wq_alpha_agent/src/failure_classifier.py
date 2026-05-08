from __future__ import annotations


def classify_failure(metrics: dict) -> str:
    if metrics.get("error"):
        return "api_error"
    sharpe = metrics.get("sharpe", 0)
    fitness = metrics.get("fitness", 0)
    turnover = metrics.get("turnover", 1)
    if sharpe < 1.2:
        return "low_sharpe"
    if fitness < 1.0:
        return "low_fitness"
    if turnover > 0.6:
        return "high_turnover"
    return "unknown"
