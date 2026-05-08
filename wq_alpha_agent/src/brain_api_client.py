from __future__ import annotations

import hashlib


class BrainApiClient:
    """Mock-friendly BRAIN client.

    Replace `simulate_alpha` with real API calls when credentials are configured.
    """

    def simulate_alpha(self, alpha_expr: str, region: str, universe: str, decay: int, neutralization: str, delay: int) -> dict:
        key = f"{alpha_expr}|{region}|{universe}|{decay}|{neutralization}|{delay}"
        h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
        sharpe = (h % 300) / 100.0 - 0.2
        fitness = (h % 220) / 100.0
        turnover = ((h // 7) % 90) / 100.0
        return {
            "sharpe": round(sharpe, 3),
            "fitness": round(fitness, 3),
            "turnover": round(turnover, 3),
            "weight_concentration": round(((h // 17) % 100) / 100.0, 3),
        }
