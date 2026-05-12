"""Tests: AtlasBridge retries on ConnectError/ReadError and 502/503/504."""
from __future__ import annotations

import httpx
import respx

from jarvis.agents.atlas.agent import AtlasBridge


def test_get_retries_on_connect_error_then_succeeds(monkeypatch):
    """_get retries on ConnectError and succeeds on the 4th attempt."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    # Suppress sleep delays in tests
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    call_count = 0

    def _flaky(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 4:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"ok": True})

    with respx.mock(base_url="http://atlas-retry:8000", assert_all_called=False) as mock:
        mock.get("/portfolio").mock(side_effect=_flaky)
        bridge = AtlasBridge(base_url="http://atlas-retry:8000")
        result = bridge._get("/portfolio")

    assert result == {"ok": True}
    assert call_count == 4


def test_get_returns_none_after_exhausting_retries(monkeypatch):
    """_get returns None after 3 retries all fail with ConnectError."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    call_count = 0

    def _always_fail(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("refused")

    with respx.mock(base_url="http://atlas-exhaust:8000", assert_all_called=False) as mock:
        mock.get("/portfolio").mock(side_effect=_always_fail)
        bridge = AtlasBridge(base_url="http://atlas-exhaust:8000")
        result = bridge._get("/portfolio")

    assert result is None
    assert call_count == 4  # initial + 3 retries


def test_get_retries_on_503(monkeypatch):
    """_get retries on HTTP 503 and succeeds on recovery."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    call_count = 0

    def _flaky_503(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"data": "live"})

    with respx.mock(base_url="http://atlas-503:8000", assert_all_called=False) as mock:
        mock.get("/market/scan").mock(side_effect=_flaky_503)
        bridge = AtlasBridge(base_url="http://atlas-503:8000")
        result = bridge._get("/market/scan")

    assert result == {"data": "live"}
    assert call_count == 3


def test_post_retries_on_read_error_then_succeeds(monkeypatch):
    """_post retries on ReadError and returns result on recovery."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    call_count = 0

    def _flaky_read(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.ReadError("read error")
        return httpx.Response(200, json={"status": "ok", "result": {}})

    with respx.mock(base_url="http://atlas-read:8000", assert_all_called=False) as mock:
        mock.post("/pipeline/oracle-scan").mock(side_effect=_flaky_read)
        bridge = AtlasBridge(base_url="http://atlas-read:8000")
        result = bridge._post("/pipeline/oracle-scan", {})

    assert result == {"status": "ok", "result": {}}
    assert call_count == 2


def test_get_warns_on_each_retry(monkeypatch, caplog):
    """_get logs a warning for each retry attempt."""
    import logging

    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("jarvis.agents.atlas.agent.time.sleep", lambda _: None)

    def _always_fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with respx.mock(base_url="http://atlas-warn:8000", assert_all_called=False) as mock:
        mock.get("/portfolio").mock(side_effect=_always_fail)
        bridge = AtlasBridge(base_url="http://atlas-warn:8000")
        with caplog.at_level(logging.WARNING, logger="jarvis.agents.atlas.agent"):
            bridge._get("/portfolio")

    # 3 retries = 3 warnings (+ 1 final exhausted warning)
    warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_msgs) >= 3
