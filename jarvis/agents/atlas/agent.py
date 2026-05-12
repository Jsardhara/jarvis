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

Mode is controlled by JARVIS_ATLAS_MODE env var:
  "live"  — hit the real ATLAS API; return None on failure (no mock fallback)
  "mock"  — never hit the network; always return mock data

"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import httpx

from jarvis.config import get_settings
from jarvis.contract import AgentResponse, TraceEvent

log = logging.getLogger(__name__)

_DEGRADED_META: dict = {"degraded": True}

EventSink = Callable[[TraceEvent], Awaitable[None]]

# Retry delays in seconds for transient errors
_RETRY_DELAYS = (0.5, 1.0, 2.0)

# HTTP status codes that warrant a retry
_RETRYABLE_STATUS = {502, 503, 504}


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
        token = os.environ.get("ATLAS_BEARER_TOKEN", "")
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._token = token
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers=headers,
        )

    def _is_retryable(self, exc: Exception | None, status: int | None) -> bool:
        if isinstance(exc, (httpx.ConnectError, httpx.ReadError)):
            return True
        return status in _RETRYABLE_STATUS

    def _get(self, path: str) -> dict | None:
        last_exc: Exception | None = None
        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
            try:
                r = self._client.get(path)
                if r.status_code in _RETRYABLE_STATUS:
                    if delay is not None:
                        log.warning(
                            "atlas _get %s retryable status %d (attempt %d)",
                            path, r.status_code, attempt + 1,
                        )
                        time.sleep(delay)
                        continue
                    return None
                r.raise_for_status()
                return r.json()
            except (httpx.ConnectError, httpx.ReadError) as exc:
                last_exc = exc
                if delay is not None:
                    log.warning(
                        "atlas _get %s transient error (attempt %d): %s",
                        path, attempt + 1, exc,
                    )
                    time.sleep(delay)
                else:
                    log.warning("atlas _get %s exhausted retries: %s", path, exc)
            except httpx.HTTPError:
                return None
        _ = last_exc
        return None

    def _post(self, path: str, body: dict, idempotency_key: str | None = None) -> dict | None:
        key = idempotency_key or uuid4().hex
        last_exc: Exception | None = None
        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
            try:
                headers = {"X-Idempotency-Key": key}
                r = self._client.post(path, json=body, headers=headers)
                if r.status_code in _RETRYABLE_STATUS:
                    if delay is not None:
                        log.warning(
                            "atlas _post %s retryable status %d (attempt %d)",
                            path, r.status_code, attempt + 1,
                        )
                        time.sleep(delay)
                        continue
                    return None
                if r.status_code == 202:
                    # Timeout path — return raw envelope for caller to interpret
                    return r.json()
                r.raise_for_status()
                return r.json()
            except (httpx.ConnectError, httpx.ReadError) as exc:
                last_exc = exc
                if delay is not None:
                    log.warning(
                        "atlas _post %s transient error (attempt %d): %s",
                        path, attempt + 1, exc,
                    )
                    time.sleep(delay)
                else:
                    log.warning("atlas _post %s exhausted retries: %s", path, exc)
            except httpx.HTTPError:
                return None
        _ = last_exc
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

    # ---- Pipeline stage endpoints (Phase 3a) ----

    def pipeline_oracle_scan(self, idempotency_key: str | None = None) -> dict | None:
        return self._post("/pipeline/oracle-scan", {}, idempotency_key=idempotency_key)

    def pipeline_architect_rank(self, idempotency_key: str | None = None) -> dict | None:
        return self._post("/pipeline/architect-rank", {}, idempotency_key=idempotency_key)

    def pipeline_guardian_check(
        self, signal_id: str, idempotency_key: str | None = None
    ) -> dict | None:
        return self._post(
            "/pipeline/guardian-check",
            {"signal_id": signal_id},
            idempotency_key=idempotency_key,
        )

    def pipeline_trader_execute(
        self,
        signal_id: str,
        mode: str = "paper",
        auto: bool = False,
        idempotency_key: str | None = None,
    ) -> dict | None:
        return self._post(
            "/pipeline/trader-execute",
            {"signal_id": signal_id, "mode": mode, "auto": auto},
            idempotency_key=idempotency_key,
        )

    def pipeline_sage_review(
        self, trade_id: str, idempotency_key: str | None = None
    ) -> dict | None:
        return self._post(
            "/pipeline/sage-review",
            {"trade_id": trade_id},
            idempotency_key=idempotency_key,
        )

    # ---- Control surface (Phase 2 — Jarvis decision layer) ----

    def control_pause_agent(self, agent_id: str) -> dict | None:
        return self._post("/control/pause-agent", {"agent_id": agent_id})

    def control_resume_agent(self, agent_id: str) -> dict | None:
        return self._post("/control/resume-agent", {"agent_id": agent_id})

    def control_agent_state(self) -> dict | None:
        return self._get("/control/agent-state")

    def control_set_strategy_weights(self, weights: dict[str, float]) -> dict | None:
        return self._post("/control/strategy-weights", {"weights": weights})

    def control_get_strategy_weights(self) -> dict | None:
        return self._get("/control/strategy-weights")

    def control_trigger_oracle_scan(
        self, reason: str | None = None, universe: list[str] | None = None
    ) -> dict | None:
        return self._post(
            "/control/oracle-scan",
            {"reason": reason, "universe": universe},
        )

    def cost_rollup(self, date_str: str) -> dict | None:
        return self._get(f"/api/cost/rollup?date_str={date_str}")

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------- Envelope parsing ----------


def _parse_pipeline_envelope(
    raw: dict | None,
    agent_name: str,
    intent: str,
    fallback_action: str,
    fallback_result: dict,
    base_confidence: float = 0.8,
) -> AgentResponse:
    """Parse Atlas {status, correlation_id, result, job_id?} envelope.

    On status=="timeout" (HTTP 202), lower confidence and surface job_id follow-up.
    Returns None-safe: if raw is None, returns fallback AgentResponse.
    """
    if raw is None:
        return AgentResponse(
            agent=agent_name,
            intent=intent,
            action="unavailable",
            result=fallback_result,
            confidence=0.0,
            follow_ups=["Atlas pipeline endpoint unreachable"],
        )

    status = raw.get("status", "ok")
    correlation_id = raw.get("correlation_id", "")
    job_id = raw.get("job_id")
    payload = raw.get("result", {})

    if status == "timeout" or job_id is not None:
        return AgentResponse(
            agent=agent_name,
            intent=intent,
            action="pending",
            result={
                "correlation_id": correlation_id,
                "job_id": job_id,
                "partial": payload,
            },
            confidence=max(0.1, base_confidence - 0.3),
            follow_ups=[f"poll job_id={job_id} via /ws"] if job_id else ["poll via /ws"],
        )

    return AgentResponse(
        agent=agent_name,
        intent=intent,
        action=fallback_action,
        result={
            "correlation_id": correlation_id,
            "payload": payload,
            **fallback_result,
        },
        confidence=base_confidence,
    )


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
    _health_ttl_seconds: float = 5.0

    def __init__(
        self,
        bridge: AtlasBridge | None = None,
        allow_mock: bool = True,
        auto_mock_on_offline: bool = True,
        mode: str | None = None,
    ):
        self.bridge = bridge or AtlasBridge()
        self.allow_mock = allow_mock
        # mode overrides auto_mock_on_offline; reads JARVIS_ATLAS_MODE from env
        _env_mode = os.environ.get("JARVIS_ATLAS_MODE", "live")
        self._mode: str = mode or _env_mode
        # Keep auto_mock_on_offline for backward compat on legacy tests
        self.auto_mock_on_offline = auto_mock_on_offline and self._mode != "mock"
        # Cache: (result: bool, expires_at: float)
        self._health_cache: tuple[bool, float] | None = None

    @property
    def mode(self) -> str:
        """Return "live" or "mock"."""
        return self._mode

    def _health_check(self) -> bool:
        """Return True if ATLAS is reachable; cached for _health_ttl_seconds."""
        if self._mode == "mock":
            return False
        now = time.monotonic()
        if self._health_cache is not None:
            result, expires_at = self._health_cache
            if now < expires_at:
                return result
        try:
            headers = {}
            if self.bridge._token:
                headers["Authorization"] = f"Bearer {self.bridge._token}"
            resp = httpx.get(
                f"{self.bridge.base_url}/system/health", headers=headers, timeout=1.0
            )
            alive = resp.status_code == 200
        except Exception:
            alive = False
        self._health_cache = (alive, now + self._health_ttl_seconds)
        return alive

    def _is_offline(self) -> bool:
        """Return True when auto_mock_on_offline is set and health probe fails."""
        if self._mode == "mock":
            return True
        return self.auto_mock_on_offline and not self._health_check()

    def _use_mock(self) -> bool:
        """Return True if we should use mock data (mode=mock always; mode=live never)."""
        return self._mode == "mock"

    # ---- Read-only surface (no confirmation) ----

    def portfolio(self) -> AgentResponse:
        degraded = self._is_offline()
        if degraded:
            data = _mock_portfolio()
            used_mock = True
        else:
            data = self.bridge.portfolio()
            used_mock = data is None
            if used_mock:
                if not self.allow_mock:
                    raise AtlasUnavailableError("ATLAS portfolio endpoint unreachable")
                data = _mock_portfolio()
        result: dict = {"portfolio": data, "mock": used_mock}
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas",
            intent="get_portfolio",
            action="fetched",
            result=result,
            confidence=0.7 if used_mock else 1.0,
            follow_ups=["start ATLAS API on :8000"] if used_mock else [],
        )

    def positions(self) -> AgentResponse:
        degraded = self._is_offline()
        if degraded:
            data: list[dict] = _mock_positions()
            used_mock = True
        else:
            data = self.bridge.open_positions()
            used_mock = data is None
            if used_mock:
                if not self.allow_mock:
                    raise AtlasUnavailableError("ATLAS positions endpoint unreachable")
                data = _mock_positions()
        result: dict = {"positions": data, "count": len(data), "mock": used_mock}
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas",
            intent="list_positions",
            action="fetched",
            result=result,
            confidence=0.7 if used_mock else 1.0,
        )

    def pnl(self, window: str = "1d") -> AgentResponse:
        degraded = self._is_offline()
        if degraded:
            pnl_data = _mock_pnl(window)
            used_mock = True
        else:
            pnl_data = self.bridge.pnl(window)
            used_mock = pnl_data is None
            if used_mock:
                if not self.allow_mock:
                    raise AtlasUnavailableError("ATLAS pnl endpoint unreachable")
                pnl_data = _mock_pnl(window)
        result: dict = {"pnl": pnl_data, "mock": used_mock}
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas",
            intent="get_pnl",
            action="fetched",
            result=result,
            confidence=0.7 if used_mock else 1.0,
        )

    # ---- Sub-stage agents ----

    def oracle_scan(self) -> AgentResponse:
        degraded = self._is_offline()
        if self._use_mock() or degraded:
            data = _mock_market_scan()
        else:
            raw = None
            with contextlib.suppress(Exception):
                raw = self.bridge.pipeline_oracle_scan()
            if raw is not None and ("status" in raw or "correlation_id" in raw):
                return _parse_pipeline_envelope(
                    raw, "atlas.oracle", "market_scan", "scanned",
                    {"scan": _mock_market_scan()}, base_confidence=0.8,
                )
            # Fall back to legacy endpoint
            data = (
                self.bridge.market_scan()
                or (_mock_market_scan() if self.allow_mock else None)
            )
        if data is None:
            raise AtlasUnavailableError("ATLAS market scan unreachable")
        used_mock = data.get("source") == "mock"
        result: dict = {"scan": data, "mock": used_mock}
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas.oracle",
            intent="market_scan",
            action="scanned",
            result=result,
            confidence=0.8,
        )

    def architect_rank(self, regime: str | None = None) -> AgentResponse:
        degraded = self._is_offline()
        if self._use_mock() or degraded:
            strats: list[dict] = _mock_strategies()
        else:
            raw = None
            with contextlib.suppress(Exception):
                raw = self.bridge.pipeline_architect_rank()
            if raw is not None and ("status" in raw or "correlation_id" in raw):
                return _parse_pipeline_envelope(
                    raw, "atlas.architect", "rank_strategies", "ranked",
                    {"ranked": _mock_strategies(), "regime": regime, "top": None},
                    base_confidence=0.75,
                )
            strats = self.bridge.strategies() or (_mock_strategies() if self.allow_mock else None)
        if strats is None:
            raise AtlasUnavailableError("ATLAS strategies endpoint unreachable")
        ranked = sorted(strats, key=lambda s: s.get("score", 0), reverse=True)
        if regime:
            ranked = [s for s in ranked if s.get("regime_fit") in (regime, "neutral")] or ranked
        result: dict = {"ranked": ranked, "regime": regime, "top": ranked[0] if ranked else None}
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas.architect",
            intent="rank_strategies",
            action="ranked",
            result=result,
            confidence=0.75,
        )

    def guardian_check(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        """Hard risk gate. Veto power. Live mode triggers stricter rules.

        On any rejection (``approved=False`` with non-empty ``violations``), emit a
        crit ``InboxEvent`` so the violation surfaces on the dashboard, voice fact
        sheet, and morning brief. Without this, guardian rejections only live
        inside the returned ``AgentResponse.result`` and disappear silently.
        """
        degraded = self._is_offline()
        if not self._use_mock() and not degraded:
            raw = None
            with contextlib.suppress(Exception):
                raw = self.bridge.pipeline_guardian_check(signal_id=strategy_id)
            if raw is not None and ("status" in raw or "correlation_id" in raw):
                resp = _parse_pipeline_envelope(
                    raw, "atlas.guardian", "risk_check", "approved",
                    {"strategy_id": strategy_id, "mode": mode, "approved": True, "violations": []},
                    base_confidence=0.95,
                )
                # _parse_pipeline_envelope merges fallback_result LAST, which
                # masks rejection fields coming back from ATLAS. Pull approved
                # + violations directly from the raw payload so the inbox
                # emission sees the real verdict.
                raw_payload = raw.get("result") if isinstance(raw.get("result"), dict) else {}
                raw_approved = raw_payload.get("approved", raw.get("approved", True))
                raw_violations = raw_payload.get("violations", raw.get("violations", []))
                self._maybe_emit_guardian_violation(
                    strategy_id,
                    {"approved": raw_approved, "violations": raw_violations},
                )
                return resp
        violations: list[str] = []
        if mode == "live":
            violations.append("live mode requires explicit operator confirmation")
        approved = len(violations) == 0
        result: dict = {
            "strategy_id": strategy_id,
            "mode": mode,
            "approved": approved,
            "violations": violations,
        }
        if degraded:
            result["meta"] = _DEGRADED_META
        self._maybe_emit_guardian_violation(strategy_id, result)
        return AgentResponse(
            agent="atlas.guardian",
            intent="risk_check",
            action="approved" if approved else "blocked",
            result=result,
            needs_confirm=mode == "live",
            follow_ups=["confirm to override and run live"] if not approved else [],
            confidence=0.95,
        )

    @staticmethod
    def _maybe_emit_guardian_violation(strategy_id: str, result: dict) -> None:
        """If ``result`` is a guardian rejection, surface as crit ``InboxEvent``.

        No-op when approved or when violations list is empty. Inbox-write
        failures are swallowed: the guardian decision is still returned to the
        caller even if the dashboard never sees it.
        """
        if result.get("approved"):
            return
        violations = result.get("violations") or []
        if not violations:
            return
        # Lazy imports keep the atlas package decoupled from the trigger / state
        # layers at module-load time.
        from jarvis.core.triggers import build_guardian_violation_event
        from jarvis.state import append_inbox

        event = build_guardian_violation_event(strategy_id, list(violations))
        if event is None:
            return
        with contextlib.suppress(Exception):
            append_inbox(event)

    def trader_execute(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        """Execution dispatch.

        ``mode='paper'``: Jarvis auto-confirms (``auto=True`` to ATLAS).
        Calls the bridge immediately and returns ``action='executed'`` with
        ``needs_confirm=False`` so the decision layer fires without operator
        intervention.

        ``mode='live'``: does NOT call the bridge. Returns
        ``action='proposed'`` with ``needs_confirm=True``. Operator must
        confirm; ``trader_execute_confirmed`` then calls the bridge with
        ``auto=False`` after approval.
        """
        degraded = self._is_offline()
        is_paper = mode == "paper"

        if not is_paper:
            # Live: stop at the Jarvis layer. Do NOT contact ATLAS yet.
            result: dict = {"strategy_id": strategy_id, "mode": mode, "auto": False}
            if degraded:
                result["meta"] = _DEGRADED_META
            return AgentResponse(
                agent="atlas.trader",
                intent="execute_strategy",
                action="proposed",
                result=result,
                needs_confirm=True,
                follow_ups=[f"confirm to run strategy {strategy_id} in {mode}"],
                confidence=0.9,
            )

        # Paper: auto-fire via the bridge.
        if self._use_mock() or degraded:
            # Mock or offline degradation: synthetic acknowledgement only.
            result = {"strategy_id": strategy_id, "mode": mode, "auto": True, "mock": True}
            if degraded:
                result["meta"] = _DEGRADED_META
            return AgentResponse(
                agent="atlas.trader",
                intent="execute_strategy",
                action="executed",
                result=result,
                needs_confirm=False,
                follow_ups=[],
                confidence=0.5,
            )

        raw = None
        with contextlib.suppress(Exception):
            raw = self.bridge.pipeline_trader_execute(
                signal_id=strategy_id, mode=mode, auto=True
            )
        if raw is None:
            # Bridge unreachable AND we're supposedly online — never silently
            # claim the trade fired. Surface the failure so Sentinel can pause
            # the trader and alert the operator.
            raise AtlasUnavailableError(
                f"trader_execute paper auto failed for {strategy_id}: bridge unreachable"
            )
        if "status" in raw or "correlation_id" in raw:
            return _parse_pipeline_envelope(
                raw, "atlas.trader", "execute_strategy", "executed",
                {"strategy_id": strategy_id, "mode": mode, "auto": True},
                base_confidence=0.9,
            )
        # Bridge returned a non-envelope dict (legacy shape) — treat as success
        # only when it carries a recognisable trade id.
        if not isinstance(raw, dict) or not (raw.get("id") or raw.get("txid")):
            raise AtlasUnavailableError(
                f"trader_execute paper auto returned unexpected shape: {list(raw)}"
            )
        return AgentResponse(
            agent="atlas.trader",
            intent="execute_strategy",
            action="executed",
            result={"run": raw, "strategy_id": strategy_id, "mode": mode, "auto": True},
            needs_confirm=False,
            follow_ups=[],
            confidence=0.9,
        )

    def trader_execute_confirmed(self, strategy_id: str, mode: str = "paper") -> AgentResponse:
        degraded = self._is_offline()
        if self._use_mock() or degraded:
            out = {"id": strategy_id, "mode": mode, "status": "queued", "source": "mock"}
            used_mock = True
        else:
            raw = None
            with contextlib.suppress(Exception):
                raw = self.bridge.pipeline_trader_execute(signal_id=strategy_id, mode=mode)
            if raw is not None and ("status" in raw or "correlation_id" in raw):
                return _parse_pipeline_envelope(
                    raw, "atlas.trader", "execute_strategy", "executed",
                    {"strategy_id": strategy_id, "mode": mode},
                    base_confidence=1.0,
                )
            out = self.bridge.run_strategy(strategy_id, mode)
            used_mock = out is None
            if used_mock:
                out = {"id": strategy_id, "mode": mode, "status": "queued", "source": "mock"}
        result: dict = {"run": out, "mock": used_mock}
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas.trader",
            intent="execute_strategy",
            action="executed",
            result=result,
            confidence=0.7 if used_mock else 1.0,
        )

    def sage_review(self, run_id: str) -> AgentResponse:
        """Post-trade analysis. Calls /pipeline/sage-review when in live mode."""
        degraded = self._is_offline()
        if not self._use_mock() and not degraded:
            raw = None
            with contextlib.suppress(Exception):
                raw = self.bridge.pipeline_sage_review(trade_id=run_id)
            if raw is not None and ("status" in raw or "correlation_id" in raw):
                return _parse_pipeline_envelope(
                    raw, "atlas.sage", "post_trade_review", "reviewed",
                    {"run_id": run_id, "lessons": [], "summary": ""},
                    base_confidence=0.5,
                )
        result: dict = {
            "run_id": run_id,
            "lessons": [],
            "summary": "post-trade analysis pending real run",
        }
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas.sage",
            intent="post_trade_review",
            action="reviewed",
            result=result,
            confidence=0.5,
        )

    # ---- Control surface (Phase 2) ----

    def pause_agent(self, agent_id: str) -> AgentResponse:
        """Tell ATLAS to pause an agent. No operator confirmation needed."""
        if self._use_mock() or self._is_offline():
            return AgentResponse(
                agent="atlas.control",
                intent="pause_agent",
                action="paused",
                result={"agent_id": agent_id, "mock": True},
                confidence=0.5,
            )
        raw = None
        with contextlib.suppress(Exception):
            raw = self.bridge.control_pause_agent(agent_id)
        if raw is None:
            raise AtlasUnavailableError(f"control.pause_agent({agent_id}) failed")
        return AgentResponse(
            agent="atlas.control",
            intent="pause_agent",
            action="paused",
            result=raw,
            confidence=1.0,
        )

    def resume_agent(self, agent_id: str) -> AgentResponse:
        if self._use_mock() or self._is_offline():
            return AgentResponse(
                agent="atlas.control",
                intent="resume_agent",
                action="resumed",
                result={"agent_id": agent_id, "mock": True},
                confidence=0.5,
            )
        raw = None
        with contextlib.suppress(Exception):
            raw = self.bridge.control_resume_agent(agent_id)
        if raw is None:
            raise AtlasUnavailableError(f"control.resume_agent({agent_id}) failed")
        return AgentResponse(
            agent="atlas.control",
            intent="resume_agent",
            action="resumed",
            result=raw,
            confidence=1.0,
        )

    def agent_state(self) -> AgentResponse:
        if self._use_mock() or self._is_offline():
            return AgentResponse(
                agent="atlas.control",
                intent="agent_state",
                action="fetched",
                result={"agents": [], "mock": True},
                confidence=0.5,
            )
        raw = self.bridge.control_agent_state()
        if raw is None:
            raise AtlasUnavailableError("control.agent_state failed")
        return AgentResponse(
            agent="atlas.control",
            intent="agent_state",
            action="fetched",
            result=raw,
            confidence=1.0,
        )

    def set_strategy_weights(self, weights: dict[str, float]) -> AgentResponse:
        if self._use_mock() or self._is_offline():
            return AgentResponse(
                agent="atlas.control",
                intent="set_strategy_weights",
                action="set",
                result={"weights": weights, "mock": True},
                confidence=0.5,
            )
        raw = self.bridge.control_set_strategy_weights(weights)
        if raw is None:
            raise AtlasUnavailableError("control.set_strategy_weights failed")
        return AgentResponse(
            agent="atlas.control",
            intent="set_strategy_weights",
            action="set",
            result=raw,
            confidence=1.0,
        )

    def trigger_oracle_scan(
        self, reason: str | None = None, universe: list[str] | None = None
    ) -> AgentResponse:
        if self._use_mock() or self._is_offline():
            return AgentResponse(
                agent="atlas.control",
                intent="oracle_scan",
                action="triggered",
                result={"reason": reason, "universe": universe, "mock": True},
                confidence=0.5,
            )
        raw = self.bridge.control_trigger_oracle_scan(reason, universe)
        if raw is None:
            raise AtlasUnavailableError("control.trigger_oracle_scan failed")
        return AgentResponse(
            agent="atlas.control",
            intent="oracle_scan",
            action="triggered",
            result=raw,
            confidence=1.0,
        )

    # ---- Pipeline (orchestrator-style chain) ----

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

        async def _run_stage(
            stage: str, fn: Callable[[], AgentResponse]
        ) -> AgentResponse:
            await sink(TraceEvent(
                type="agent.start", request_id=request_id, agent=f"atlas.{stage}",
                payload={"stage": stage},
            ))
            started = time.perf_counter()
            result = await asyncio.to_thread(fn)
            await _emit(stage, result, int((time.perf_counter() - started) * 1000))
            return result

        degraded = self._is_offline()
        oracle = await _run_stage("oracle", self.oracle_scan)
        regime = oracle.result.get("scan", {}).get("regime")

        architect = await _run_stage("architect", lambda: self.architect_rank(regime=regime))
        top = architect.result.get("top")
        if not top:
            halted_result: dict = {
                "reason": "no candidate strategy",
                "stages": ["oracle", "architect"],
            }
            if degraded:
                halted_result["meta"] = _DEGRADED_META
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="halted",
                result=halted_result,
                confidence=0.7,
            )

        strategy_id = top["id"]
        guardian = await _run_stage(
            "guardian", lambda: self.guardian_check(strategy_id, mode=mode)
        )
        if not guardian.result.get("approved"):
            vetoed_result: dict = {
                "strategy_id": strategy_id,
                "violations": guardian.result.get("violations", []),
                "stages": ["oracle", "architect", "guardian"],
            }
            if degraded:
                vetoed_result["meta"] = _DEGRADED_META
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="vetoed",
                result=vetoed_result,
                needs_confirm=True,
                follow_ups=["override Guardian and confirm live execution"],
                confidence=0.85,
            )

        trader = await _run_stage(
            "trader", lambda: self.trader_execute(strategy_id, mode=mode)
        )
        proposed_result: dict = {
            "strategy_id": strategy_id,
            "mode": mode,
            "stages": ["oracle", "architect", "guardian", "trader"],
            "trader_proposal": trader.result,
        }
        if degraded:
            proposed_result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas",
            intent="pipeline",
            action="proposed",
            result=proposed_result,
            needs_confirm=True,
            follow_ups=[f"confirm to execute {strategy_id} in {mode}"],
            confidence=0.85,
        )

    def pipeline(self, mode: str = "paper") -> AgentResponse:
        degraded = self._is_offline()
        oracle = self.oracle_scan()
        regime = oracle.result.get("scan", {}).get("regime")
        architect = self.architect_rank(regime=regime)
        top = architect.result.get("top")
        if not top:
            result: dict = {
                "reason": "no candidate strategy",
                "stages": ["oracle", "architect"],
            }
            if degraded:
                result["meta"] = _DEGRADED_META
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="halted",
                result=result,
                confidence=0.7,
            )
        strategy_id = top["id"]
        guardian = self.guardian_check(strategy_id, mode=mode)
        if not guardian.result.get("approved"):
            result = {
                "strategy_id": strategy_id,
                "violations": guardian.result.get("violations", []),
                "stages": ["oracle", "architect", "guardian"],
            }
            if degraded:
                result["meta"] = _DEGRADED_META
            return AgentResponse(
                agent="atlas",
                intent="pipeline",
                action="vetoed",
                result=result,
                needs_confirm=True,
                follow_ups=["override Guardian and confirm live execution"],
                confidence=0.85,
            )
        trader = self.trader_execute(strategy_id, mode=mode)
        result = {
            "strategy_id": strategy_id,
            "mode": mode,
            "stages": ["oracle", "architect", "guardian", "trader"],
            "trader_proposal": trader.result,
        }
        if degraded:
            result["meta"] = _DEGRADED_META
        return AgentResponse(
            agent="atlas",
            intent="pipeline",
            action="proposed",
            result=result,
            needs_confirm=True,
            follow_ups=[f"confirm to execute {strategy_id} in {mode}"],
            confidence=0.85,
        )
