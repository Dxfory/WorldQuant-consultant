from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request


class BrainApiClient:
    """WorldQuant BRAIN API client with mock fallback.

    Set `WQ_BRAIN_USERNAME` and `WQ_BRAIN_PASSWORD` to enable real API mode.
    """

    def __init__(self, base_url: str = "https://api.worldquantbrain.com"):
        self.base_url = os.getenv("WQ_BRAIN_BASE_URL", base_url).rstrip("/")
        self.username = os.getenv("WQ_BRAIN_USERNAME", "")
        self.password = os.getenv("WQ_BRAIN_PASSWORD", "")
        self.real_mode = bool(self.username and self.password)

    def simulate_alpha(self, alpha_expr: str, region: str, universe: str, decay: int, neutralization: str, delay: int) -> dict:
        if self.real_mode:
            return self._simulate_real(alpha_expr, region, universe, decay, neutralization, delay)
        return self._simulate_mock(alpha_expr, region, universe, decay, neutralization, delay)

    def _simulate_real(self, alpha_expr: str, region: str, universe: str, decay: int, neutralization: str, delay: int) -> dict:
        payload = {
            "type": "REGULAR",
            "settings": {
                "instrumentType": "EQUITY",
                "region": region,
                "universe": universe,
                "delay": delay,
                "decay": decay,
                "neutralization": neutralization,
                "truncation": 0.08,
                "pasteurization": "ON",
                "unitHandling": "VERIFY",
                "nanHandling": "OFF",
                "language": "FASTEXPR",
            },
            "regular": alpha_expr,
        }
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        req = urllib.request.Request(
            f"{self.base_url}/simulations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"error": f"http_{e.code}", "sharpe": 0.0, "fitness": 0.0, "turnover": 1.0, "weight_concentration": 1.0}
        except Exception:
            return {"error": "request_failed", "sharpe": 0.0, "fitness": 0.0, "turnover": 1.0, "weight_concentration": 1.0}

        # 兼容不同字段命名
        return {
            "sharpe": float(data.get("sharpe", data.get("isSharpe", 0.0))),
            "fitness": float(data.get("fitness", data.get("isFitness", 0.0))),
            "turnover": float(data.get("turnover", 1.0)),
            "weight_concentration": float(data.get("weightConcentration", 1.0)),
        }

    def _simulate_mock(self, alpha_expr: str, region: str, universe: str, decay: int, neutralization: str, delay: int) -> dict:
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
