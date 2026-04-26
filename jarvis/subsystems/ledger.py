"""Ledger — finance + ATLAS bridge.

Thin HTTP client over ATLAS FastAPI. Verified ATLAS routes (api/routers/*):
- GET  /system/health
- GET  /portfolio                 — current snapshot
- GET  /portfolio/history?limit=  — historical snapshots
- GET  /trades, /trades/open, /trades/stats, /trades/{id}
- POST /trades/{id}/close
- GET  /strategies, /strategies/{id}
- POST /strategies/{id}/activate, /strategies/{id}/archive, /strategies/generate

When ATLAS is offline, the client falls back to a deterministic mock so
the orchestrator and daemon can still answer "what would my portfolio
look like" without crashing.
"""
from __future__ import annotations

import httpx

from ..config import get_settings
from ..contract import AgentResponse


class AtlasUnavailable(Exception):
    """Raised when ATLAS API is unreachable AND no mock is in use."""


class AtlasClient:
    """Synchronous HTTP client. Daemon uses async via httpx.AsyncClient elsewhere."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = (base_url or get_settings().atlas_api).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

    def _get(self, path: str) -> dict | None:
        try:
            r = self._client.get(path)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, httpx.ConnectError, httpx.ReadError):
            return None

    def _post(self, path: str, body: dict) -> dict | None:
        try:
            r = self._client.post(path, json=body)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, httpx.ConnectError, httpx.ReadError):
            return None

    def health(self) -> bool:
        out = self._get("/system/health") or self._get("/health")
        return out is not None

    def portfolio(self) -> dict | None:
        return self._get("/portfolio")

    def open_positions(self) -> list[dict] | None:
        out = self._get("/trades/open")
        if isinstance(out, list):
            return out
        if isinstance(out, dict):
            return out.get("trades") or out.get("positions") or []
        return None

    def pnl(self, window: str = "1d") -> dict | None:
        # ATLAS exposes aggregate trade stats; window currently advisory.
        out = self._get("/trades/stats")
        if isinstance(out, dict):
            out.setdefault("window", window)
        return out

    def run_strategy(self, strategy_id: str, mode: str = "paper") -> dict | None:
        return self._post(f"/strategies/{strategy_id}/activate", {"mode": mode})

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _mock_portfolio() -> dict:
    return {
        "total_value_usd": 10000.0,
        "cash": 2500.0,
        "holdings": [
            {"symbol": "BTC", "qty": 0.05, "value_usd": 3500.0},
            {"symbol": "ETH", "qty": 1.2, "value_usd": 4000.0},
        ],
        "source": "mock",
    }


def _mock_positions() -> list[dict]:
    return [
        {"id": "p1", "symbol": "BTC/USD", "side": "long", "size": 0.05, "entry": 70000, "pnl_pct": 0.02, "source": "mock"},
    ]


def _mock_pnl(window: str) -> dict:
    return {"window": window, "pnl_usd": 120.0, "pnl_pct": 0.012, "source": "mock"}


class Ledger:
    def __init__(self, client: AtlasClient | None = None, allow_mock: bool = True):
        self.client = client or AtlasClient()
        self.allow_mock = allow_mock

    def portfolio(self) -> AgentResponse:
        data = self.client.portfolio()
        used_mock = False
        if data is None:
            if not self.allow_mock:
                raise AtlasUnavailable("ATLAS portfolio endpoint unreachable")
            data = _mock_portfolio()
            used_mock = True
        return AgentResponse(
            agent="ledger",
            intent="get_portfolio",
            action="fetched",
            result={"portfolio": data, "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
            follow_ups=["start ATLAS API"] if used_mock else [],
        )

    def positions(self) -> AgentResponse:
        data = self.client.open_positions()
        used_mock = False
        if data is None:
            if not self.allow_mock:
                raise AtlasUnavailable("ATLAS positions endpoint unreachable")
            data = _mock_positions()
            used_mock = True
        return AgentResponse(
            agent="ledger",
            intent="list_positions",
            action="fetched",
            result={"positions": data, "count": len(data), "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
        )

    def pnl(self, window: str = "1d") -> AgentResponse:
        data = self.client.pnl(window)
        used_mock = False
        if data is None:
            if not self.allow_mock:
                raise AtlasUnavailable("ATLAS pnl endpoint unreachable")
            data = _mock_pnl(window)
            used_mock = True
        return AgentResponse(
            agent="ledger",
            intent="get_pnl",
            action="fetched",
            result={"pnl": data, "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
        )

    def trigger_strategy(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        # Always confirm before triggering — destructive in live mode
        return AgentResponse(
            agent="ledger",
            intent="trigger_strategy",
            action="proposed",
            result={"strategy_id": strategy_id, "mode": mode},
            needs_confirm=True,
            follow_ups=[f"confirm to run strategy {strategy_id} in {mode}"],
            confidence=0.95,
        )

    def trigger_strategy_confirmed(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        out = self.client.run_strategy(strategy_id, mode)
        used_mock = out is None
        if used_mock:
            out = {"id": strategy_id, "mode": mode, "status": "queued", "source": "mock"}
        return AgentResponse(
            agent="ledger",
            intent="trigger_strategy",
            action="triggered",
            result={"run": out, "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
        )
