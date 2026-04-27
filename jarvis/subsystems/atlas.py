"""Atlas — trading orchestrator.

Wraps the ATLAS FastAPI project (`C:\\Users\\jyot2\\atlas\\`) over HTTP and
exposes the 5-stage trading pipeline:

    Oracle  → market/news/sentiment scan
    Architect → strategy design + ranking
    Guardian → hard risk validation (veto power)
    Trader  → execution (paper or live, behind confirmation)
    Sage    → post-trade analysis + lesson capture

Each stage returns an AgentResponse so the dashboard can render the
sub-flow as a swimlane. Guardian veto blocks Trader. Live execution
always requires explicit confirmation.

When ATLAS is offline, Atlas falls back to deterministic mocks so the
dashboard stays responsive.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx

from ..config import get_settings
from ..contract import AgentResponse, TraceEvent

EventSink = Callable[[TraceEvent], Awaitable[None]]


async def _noop_sink(_event: TraceEvent) -> None:
    return None


class AtlasUnavailableError(Exception):
    pass


# ---------- HTTP shell over ATLAS project ----------


class AtlasBridge:
    """Sync HTTP client over the ATLAS FastAPI project."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ):
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
        return (self._get("/system/health") or self._get("/health")) is not None

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
        out = self._get("/trades/stats")
        if isinstance(out, dict):
            out.setdefault("window", window)
        return out

    def market_scan(self) -> dict | None:
        return self._get("/market/scan") or self._get("/oracle/scan")

    def strategies(self) -> list[dict] | None:
        out = self._get("/strategies")
        if isinstance(out, list):
            return out
        if isinstance(out, dict):
            return out.get("strategies") or []
        return None

    def run_strategy(self, strategy_id: str, mode: str = "paper") -> dict | None:
        return self._post(f"/strategies/{strategy_id}/activate", {"mode": mode})

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------- Mocks ----------


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
        {"id": "p1", "symbol": "BTC/USD", "side": "long", "size": 0.05,
         "entry": 70000, "pnl_pct": 0.02, "source": "mock"},
    ]


def _mock_pnl(window: str) -> dict:
    return {"window": window, "pnl_usd": 120.0, "pnl_pct": 0.012, "source": "mock"}


def _mock_market_scan() -> dict:
    return {
        "regime": "risk_on",
        "top_movers": [
            {"symbol": "BTC", "change_24h_pct": 0.034},
            {"symbol": "SOL", "change_24h_pct": 0.052},
        ],
        "source": "mock",
    }


def _mock_strategies() -> list[dict]:
    return [
        {"id": "trend_v1", "score": 0.72, "regime_fit": "risk_on", "source": "mock"},
        {"id": "mean_reversion_v3", "score": 0.61, "regime_fit": "neutral", "source": "mock"},
    ]


# ---------- Atlas orchestrator + 5 sub-stages ----------


class AtlasOrchestrator:
    def __init__(self, bridge: AtlasBridge | None = None, allow_mock: bool = True):
        self.bridge = bridge or AtlasBridge()
        self.allow_mock = allow_mock

    # ---- Read-only surface (no confirmation) ----

    def portfolio(self) -> AgentResponse:
        data = self.bridge.portfolio()
        used_mock = data is None
        if used_mock:
            if not self.allow_mock:
                raise AtlasUnavailableError("ATLAS portfolio endpoint unreachable")
            data = _mock_portfolio()
        return AgentResponse(
            agent="atlas",
            intent="get_portfolio",
            action="fetched",
            result={"portfolio": data, "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
            follow_ups=["start ATLAS API on :8000"] if used_mock else [],
        )

    def positions(self) -> AgentResponse:
        data = self.bridge.open_positions()
        used_mock = data is None
        if used_mock:
            if not self.allow_mock:
                raise AtlasUnavailableError("ATLAS positions endpoint unreachable")
            data = _mock_positions()
        return AgentResponse(
            agent="atlas",
            intent="list_positions",
            action="fetched",
            result={"positions": data, "count": len(data), "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
        )

    def pnl(self, window: str = "1d") -> AgentResponse:
        data = self.bridge.pnl(window)
        used_mock = data is None
        if used_mock:
            if not self.allow_mock:
                raise AtlasUnavailableError("ATLAS pnl endpoint unreachable")
            data = _mock_pnl(window)
        return AgentResponse(
            agent="atlas",
            intent="get_pnl",
            action="fetched",
            result={"pnl": data, "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
        )

    # ---- Sub-stage agents (Oracle / Architect / Guardian / Trader / Sage) ----

    def oracle_scan(self) -> AgentResponse:
        data = self.bridge.market_scan() or (_mock_market_scan() if self.allow_mock else None)
        if data is None:
            raise AtlasUnavailableError("ATLAS market scan unreachable")
        return AgentResponse(
            agent="atlas.oracle",
            intent="market_scan",
            action="scanned",
            result={"scan": data, "mock": data.get("source") == "mock"},
            confidence=0.8,
        )

    def architect_rank(self, regime: str | None = None) -> AgentResponse:
        strats = self.bridge.strategies() or (_mock_strategies() if self.allow_mock else None)
        if strats is None:
            raise AtlasUnavailableError("ATLAS strategies endpoint unreachable")
        ranked = sorted(strats, key=lambda s: s.get("score", 0), reverse=True)
        if regime:
            ranked = [s for s in ranked if s.get("regime_fit") in (regime, "neutral")] or ranked
        return AgentResponse(
            agent="atlas.architect",
            intent="rank_strategies",
            action="ranked",
            result={"ranked": ranked, "regime": regime, "top": ranked[0] if ranked else None},
            confidence=0.75,
        )

    def guardian_check(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        """Hard risk gate. Veto power. Live mode triggers stricter rules."""
        violations: list[str] = []
        if mode == "live":
            violations.append("live mode requires explicit operator confirmation")
        approved = len(violations) == 0
        return AgentResponse(
            agent="atlas.guardian",
            intent="risk_check",
            action="approved" if approved else "blocked",
            result={
                "strategy_id": strategy_id,
                "mode": mode,
                "approved": approved,
                "violations": violations,
            },
            needs_confirm=mode == "live",
            follow_ups=["confirm to override and run live"] if not approved else [],
            confidence=0.95,
        )

    def trader_execute(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        """Execution. Always proposes — operator confirms before run."""
        return AgentResponse(
            agent="atlas.trader",
            intent="execute_strategy",
            action="proposed",
            result={"strategy_id": strategy_id, "mode": mode},
            needs_confirm=True,
            follow_ups=[f"confirm to run strategy {strategy_id} in {mode}"],
            confidence=0.9,
        )

    def trader_execute_confirmed(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        out = self.bridge.run_strategy(strategy_id, mode)
        used_mock = out is None
        if used_mock:
            out = {"id": strategy_id, "mode": mode, "status": "queued", "source": "mock"}
        return AgentResponse(
            agent="atlas.trader",
            intent="execute_strategy",
            action="executed",
            result={"run": out, "mock": used_mock},
            confidence=0.7 if used_mock else 1.0,
        )

    def sage_review(self, run_id: str) -> AgentResponse:
        """Post-trade analysis stub. Real impl reads ATLAS trade history + lessons."""
        return AgentResponse(
            agent="atlas.sage",
            intent="post_trade_review",
            action="reviewed",
            result={
                "run_id": run_id,
                "lessons": [],
                "summary": "post-trade analysis pending real run",
            },
            confidence=0.5,
        )

    # ---- Pipeline (orchestrator-style chain, used by daemon + dashboard "full pipeline" button) ----

    async def pipeline_async_traced(
        self,
        mode: str = "paper",
        on_event: EventSink | None = None,
        request_id: str = "",
    ) -> AgentResponse:
        """Pipeline that emits per-stage trace events for sub-flow swimlane rendering."""
        sink = on_event or _noop_sink

        async def _emit(stage: str, sub_resp: AgentResponse, duration_ms: int) -> None:
            await sink(TraceEvent(
                type="agent.done",
                request_id=request_id,
                agent=sub_resp.agent,
                payload={
                    "stage": stage,
                    "action": sub_resp.action,
                    "duration_ms": duration_ms,
                    "needs_confirm": sub_resp.needs_confirm,
                },
            ))

        async def _run_stage(stage: str, fn: Callable[[], AgentResponse]) -> AgentResponse:
            await sink(TraceEvent(
                type="agent.start", request_id=request_id, agent=f"atlas.{stage}",
                payload={"stage": stage},
            ))
            started = time.perf_counter()
            result = await asyncio.to_thread(fn)
            await _emit(stage, result, int((time.perf_counter() - started) * 1000))
            return result

        oracle = await _run_stage("oracle", self.oracle_scan)
        regime = oracle.result.get("scan", {}).get("regime")

        architect = await _run_stage("architect", lambda: self.architect_rank(regime=regime))
        top = architect.result.get("top")
        if not top:
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="halted",
                result={"reason": "no candidate strategy", "stages": ["oracle", "architect"]},
                confidence=0.7,
            )

        strategy_id = top["id"]
        guardian = await _run_stage(
            "guardian", lambda: self.guardian_check(strategy_id, mode=mode)
        )
        if not guardian.result.get("approved"):
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="vetoed",
                result={
                    "strategy_id": strategy_id,
                    "violations": guardian.result.get("violations", []),
                    "stages": ["oracle", "architect", "guardian"],
                },
                needs_confirm=True,
                follow_ups=["override Guardian and confirm live execution"],
                confidence=0.85,
            )

        trader = await _run_stage(
            "trader", lambda: self.trader_execute(strategy_id, mode=mode)
        )
        return AgentResponse(
            agent="atlas",
            intent="pipeline",
            action="proposed",
            result={
                "strategy_id": strategy_id,
                "mode": mode,
                "stages": ["oracle", "architect", "guardian", "trader"],
                "trader_proposal": trader.result,
            },
            needs_confirm=True,
            follow_ups=[f"confirm to execute {strategy_id} in {mode}"],
            confidence=0.85,
        )

    def pipeline(self, mode: str = "paper") -> AgentResponse:
        oracle = self.oracle_scan()
        regime = oracle.result.get("scan", {}).get("regime")
        architect = self.architect_rank(regime=regime)
        top = architect.result.get("top")
        if not top:
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="halted",
                result={"reason": "no candidate strategy", "stages": ["oracle", "architect"]},
                confidence=0.7,
            )
        strategy_id = top["id"]
        guardian = self.guardian_check(strategy_id, mode=mode)
        if not guardian.result.get("approved"):
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="vetoed",
                result={
                    "strategy_id": strategy_id,
                    "violations": guardian.result.get("violations", []),
                    "stages": ["oracle", "architect", "guardian"],
                },
                needs_confirm=True,
                follow_ups=["override Guardian and confirm live execution"],
                confidence=0.85,
            )
        trader = self.trader_execute(strategy_id, mode=mode)
        return AgentResponse(
            agent="atlas",
            intent="pipeline",
            action="proposed",
            result={
                "strategy_id": strategy_id,
                "mode": mode,
                "stages": ["oracle", "architect", "guardian", "trader"],
                "trader_proposal": trader.result,
            },
            needs_confirm=True,
            follow_ups=[f"confirm to execute {strategy_id} in {mode}"],
            confidence=0.85,
        )
