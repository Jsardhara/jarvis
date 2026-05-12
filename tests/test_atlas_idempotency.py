"""Tests: X-Idempotency-Key is stable across retries, unique across calls."""
from __future__ import annotations

import httpx
import respx

from jarvis.agents.atlas.agent import AtlasBridge


def test_same_key_used_across_retries(monkeypatch):
    """A single logical _post call reuses the same idempotency key across retries."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    seen_keys: list[str] = []
    call_count = 0

    def _capture(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        key = request.headers.get("x-idempotency-key", "")
        seen_keys.append(key)
        if call_count < 3:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"status": "ok", "result": {}})

    with respx.mock(base_url="http://atlas-idem:8000", assert_all_called=False) as mock:
        mock.post("/pipeline/oracle-scan").mock(side_effect=_capture)
        bridge = AtlasBridge(base_url="http://atlas-idem:8000")
        bridge._post("/pipeline/oracle-scan", {})

    assert call_count == 3
    assert len(seen_keys) == 3
    # All retries share the same key
    assert len(set(seen_keys)) == 1
    assert seen_keys[0] != ""


def test_different_calls_get_different_keys(monkeypatch):
    """Two separate _post calls each get a distinct idempotency key."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    seen_keys: list[str] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("x-idempotency-key", "")
        seen_keys.append(key)
        return httpx.Response(200, json={"status": "ok", "result": {}})

    with respx.mock(base_url="http://atlas-idem2:8000", assert_all_called=False) as mock:
        mock.post("/pipeline/oracle-scan").mock(side_effect=_capture)
        bridge = AtlasBridge(base_url="http://atlas-idem2:8000")
        bridge._post("/pipeline/oracle-scan", {})
        bridge._post("/pipeline/oracle-scan", {})

    assert len(seen_keys) == 2
    assert seen_keys[0] != seen_keys[1]


def test_caller_supplied_key_is_preserved_across_retries(monkeypatch):
    """When caller supplies idempotency_key, that exact key is reused on retries."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    fixed_key = "fixed-key-abc123"
    seen_keys: list[str] = []
    call_count = 0

    def _capture(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        seen_keys.append(request.headers.get("x-idempotency-key", ""))
        if call_count < 2:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"status": "ok", "result": {}})

    with respx.mock(base_url="http://atlas-idem3:8000", assert_all_called=False) as mock:
        mock.post("/pipeline/oracle-scan").mock(side_effect=_capture)
        bridge = AtlasBridge(base_url="http://atlas-idem3:8000")
        bridge._post("/pipeline/oracle-scan", {}, idempotency_key=fixed_key)

    assert all(k == fixed_key for k in seen_keys)
