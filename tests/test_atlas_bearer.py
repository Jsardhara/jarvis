"""Tests: AtlasBridge injects Authorization header when ATLAS_BEARER_TOKEN is set."""
from __future__ import annotations

import httpx
import respx

from jarvis.subsystems.atlas import AtlasBridge


def test_bearer_token_injected_in_get(monkeypatch):
    """When ATLAS_BEARER_TOKEN is set, GET requests carry Authorization header."""
    monkeypatch.setenv("ATLAS_BEARER_TOKEN", "test-token-abc")

    with respx.mock(base_url="http://atlas-bearer-test:8000", assert_all_called=False) as mock:
        received_headers: dict = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            received_headers.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True})

        mock.get("/portfolio").mock(side_effect=_capture)
        bridge = AtlasBridge(base_url="http://atlas-bearer-test:8000")
        bridge._get("/portfolio")

    assert "authorization" in received_headers
    assert received_headers["authorization"] == "Bearer test-token-abc"


def test_bearer_token_injected_in_post(monkeypatch):
    """When ATLAS_BEARER_TOKEN is set, POST requests carry Authorization header."""
    monkeypatch.setenv("ATLAS_BEARER_TOKEN", "post-token-xyz")

    with respx.mock(base_url="http://atlas-bearer-test2:8000", assert_all_called=False) as mock:
        received_headers: dict = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            received_headers.update(dict(request.headers))
            return httpx.Response(200, json={"status": "ok", "result": {}})

        mock.post("/pipeline/oracle-scan").mock(side_effect=_capture)
        bridge = AtlasBridge(base_url="http://atlas-bearer-test2:8000")
        bridge._post("/pipeline/oracle-scan", {})

    assert "authorization" in received_headers
    assert received_headers["authorization"] == "Bearer post-token-xyz"


def test_no_bearer_token_omits_header(monkeypatch):
    """When ATLAS_BEARER_TOKEN is empty, no Authorization header is sent."""
    monkeypatch.setenv("ATLAS_BEARER_TOKEN", "")

    with respx.mock(base_url="http://atlas-no-token:8000", assert_all_called=False) as mock:
        received_headers: dict = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            received_headers.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True})

        mock.get("/portfolio").mock(side_effect=_capture)
        bridge = AtlasBridge(base_url="http://atlas-no-token:8000")
        bridge._get("/portfolio")

    assert "authorization" not in received_headers


def test_token_unset_omits_header(monkeypatch):
    """When ATLAS_BEARER_TOKEN env var is absent, no Authorization header is sent."""
    monkeypatch.delenv("ATLAS_BEARER_TOKEN", raising=False)

    with respx.mock(base_url="http://atlas-no-token2:8000", assert_all_called=False) as mock:
        received_headers: dict = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            received_headers.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True})

        mock.get("/portfolio").mock(side_effect=_capture)
        bridge = AtlasBridge(base_url="http://atlas-no-token2:8000")
        bridge._get("/portfolio")

    assert "authorization" not in received_headers
