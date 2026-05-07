"""Atlas proxy routes — forwards /api/atlas/* to the Atlas backend.

All routes reuse the AtlasBridge httpx.Client (which already carries the
Bearer token + retry logic).  The SSE stream route opens a separate
async httpx.AsyncClient because the bridge client is synchronous.

Mount via ``_register_atlas_proxy(app, reg)`` called from ``make_app``.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_bridge(reg: dict[str, Any]) -> Any:
    """Return the AtlasBridge from registry, or None if atlas not registered."""
    from ..subsystems.atlas import AtlasOrchestrator

    atlas_desc = reg.get("atlas")
    if atlas_desc is None:
        return None
    inst = atlas_desc.instance
    if not isinstance(inst, AtlasOrchestrator):
        return None
    return inst


def _atlas_proxy(
    bridge_inst: Any,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Forward a request to Atlas via the bridge's httpx.Client.

    Returns (status_code, json_body).
    Raises HTTPException(503) when Atlas is unreachable.
    Converts Atlas 401 → 502 (don't leak bearer-rejected info to client).
    Forwards all other 4xx/5xx unchanged.
    """
    from fastapi import HTTPException

    client: httpx.Client = bridge_inst._client
    headers: dict[str, str] = {}
    token: str = getattr(bridge_inst, "_token", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        if method.upper() == "GET":
            resp = client.get(path, params=params, headers=headers)
        else:
            resp = client.post(path, json=body, params=params, headers=headers)
    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
        log.error("atlas proxy %s %s unreachable: %s", method, path, exc)
        raise HTTPException(status_code=503, detail="atlas unreachable") from exc
    except httpx.HTTPError as exc:
        log.error("atlas proxy %s %s http error: %s", method, path, exc)
        raise HTTPException(status_code=503, detail="atlas unreachable") from exc

    if resp.status_code == 401:
        log.error("atlas proxy bearer rejected for %s %s (ops issue)", method, path)
        raise HTTPException(status_code=502, detail="bad gateway")

    try:
        json_body = resp.json()
    except Exception:
        json_body = {"raw": resp.text}

    return resp.status_code, json_body


# ── Router factory ────────────────────────────────────────────────────────────


def register_atlas_proxy(app: Any, reg: dict[str, Any]) -> None:  # noqa: C901
    """Register all /api/atlas/* proxy routes onto the FastAPI app."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse

    def _require_live_bridge() -> Any:
        """Return bridge or raise 503 if atlas is absent or in mock mode."""
        from ..subsystems.atlas import AtlasOrchestrator

        inst = _get_bridge(reg)
        if inst is None:
            raise HTTPException(status_code=503, detail="atlas not registered")
        # Re-fetch the instance directly from desc (may be replaced in tests)
        atlas_desc = reg.get("atlas")
        orch: AtlasOrchestrator = atlas_desc.instance  # type: ignore[union-attr]
        if orch.mode != "live":
            raise HTTPException(status_code=503, detail="atlas in mock mode")
        return orch.bridge

    # ── Portfolio ─────────────────────────────────────────────────────────────

    @app.get("/api/atlas/portfolio")
    async def atlas_portfolio() -> JSONResponse:
        bridge = _require_live_bridge()
        status, body = _atlas_proxy(bridge, "GET", "/portfolio")
        return JSONResponse(content=body, status_code=status)

    @app.get("/api/atlas/portfolio/history")
    async def atlas_portfolio_history() -> JSONResponse:
        bridge = _require_live_bridge()
        status, body = _atlas_proxy(bridge, "GET", "/portfolio/history")
        return JSONResponse(content=body, status_code=status)

    # ── Trades ────────────────────────────────────────────────────────────────

    @app.get("/api/atlas/trades")
    async def atlas_trades(
        limit: int | None = None,
        offset: int | None = None,
        status: str | None = None,
        pair: str | None = None,
    ) -> JSONResponse:
        bridge = _require_live_bridge()
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if status is not None:
            params["status"] = status
        if pair is not None:
            params["pair"] = pair
        code, body = _atlas_proxy(bridge, "GET", "/trades", params=params)
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/atlas/trades/open")
    async def atlas_trades_open() -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", "/trades/open")
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/atlas/trades/stats")
    async def atlas_trades_stats() -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", "/trades/stats")
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/atlas/trades/{trade_id}")
    async def atlas_trade_by_id(trade_id: str) -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", f"/trades/{trade_id}")
        return JSONResponse(content=body, status_code=code)

    # ── Signals ───────────────────────────────────────────────────────────────

    @app.get("/api/atlas/signals")
    async def atlas_signals(limit: int | None = None) -> JSONResponse:
        bridge = _require_live_bridge()
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        code, body = _atlas_proxy(bridge, "GET", "/signals", params=params)
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/atlas/signals/active")
    async def atlas_signals_active() -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", "/signals/active")
        return JSONResponse(content=body, status_code=code)

    # ── Strategies ────────────────────────────────────────────────────────────

    @app.get("/api/atlas/strategies")
    async def atlas_strategies() -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", "/strategies")
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/atlas/strategies/{strategy_id}")
    async def atlas_strategy_by_id(strategy_id: str) -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", f"/strategies/{strategy_id}")
        return JSONResponse(content=body, status_code=code)

    # ── Atlas agents (sub-agents, not Jarvis agents) ──────────────────────────

    @app.get("/api/atlas/agents")
    async def atlas_agents() -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", "/agents")
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/atlas/agents/{agent_id}/memory")
    async def atlas_agent_memory(agent_id: str) -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", f"/agents/{agent_id}/memory")
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/atlas/agents/{agent_id}")
    async def atlas_agent_by_id(agent_id: str) -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(bridge, "GET", f"/agents/{agent_id}")
        return JSONResponse(content=body, status_code=code)

    @app.post("/api/atlas/agents/{agent_id}/chat")
    async def atlas_agent_chat(
        agent_id: str, payload: dict[str, Any]
    ) -> JSONResponse:
        bridge = _require_live_bridge()
        code, body = _atlas_proxy(
            bridge, "POST", f"/agents/{agent_id}/chat", body=payload
        )
        return JSONResponse(content=body, status_code=code)

    # ── SSE chat stream (separate async client — bridge is sync) ──────────────

    @app.get("/api/atlas/agents/{agent_id}/chat/stream")
    async def atlas_agent_chat_stream(agent_id: str) -> StreamingResponse:
        """Pass-through SSE stream from Atlas agent chat endpoint."""
        from ..subsystems.atlas import AtlasOrchestrator

        atlas_desc = reg.get("atlas")
        if atlas_desc is None:
            raise HTTPException(status_code=503, detail="atlas not registered")
        orch: AtlasOrchestrator = atlas_desc.instance
        if orch.mode != "live":
            raise HTTPException(status_code=503, detail="atlas in mock mode")

        bridge = orch.bridge
        base_url: str = bridge.base_url.rstrip("/")
        token: str = getattr(bridge, "_token", "")
        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = f"{base_url}/agents/{agent_id}/chat/stream"

        async def _stream_generator():
            try:
                async with httpx.AsyncClient() as async_client, async_client.stream(
                    "GET", url, headers=headers
                ) as upstream:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk
            except (httpx.ConnectError, httpx.ReadError) as exc:
                log.error("atlas SSE stream failed: %s", exc)

        return StreamingResponse(
            _stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
