"""Tests for the FastAPI bearer auth middleware on the Jarvis API."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def authed_client(monkeypatch: Any) -> TestClient:
    """Build a TestClient with JARVIS_API_TOKEN configured."""
    monkeypatch.setenv("JARVIS_API_TOKEN", "secret-token-123")
    monkeypatch.delenv("MC_API_TOKEN", raising=False)
    # Reload api module so the middleware picks up the env var.
    from jarvis.apps.api import app as api_module

    app = api_module.make_app()
    return TestClient(app)


@pytest.fixture()
def open_client(monkeypatch: Any) -> TestClient:
    """Build a TestClient with no auth token configured (open access)."""
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.delenv("MC_API_TOKEN", raising=False)
    from jarvis.apps.api import app as api_module

    app = api_module.make_app()
    return TestClient(app)


def test_health_endpoint_open_when_token_set(authed_client: TestClient) -> None:
    """`/api/health` is reachable without a token even when auth is enabled."""
    resp = authed_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_protected_endpoint_rejects_missing_header(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/inbox")
    assert resp.status_code == 401
    assert "Authorization" in resp.json()["error"]


def test_protected_endpoint_rejects_wrong_token(authed_client: TestClient) -> None:
    resp = authed_client.get(
        "/api/inbox", headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401


def test_protected_endpoint_accepts_correct_token(authed_client: TestClient) -> None:
    resp = authed_client.get(
        "/api/inbox", headers={"Authorization": "Bearer secret-token-123"}
    )
    assert resp.status_code == 200


def test_open_mode_no_auth_required(open_client: TestClient) -> None:
    """When JARVIS_API_TOKEN is unset, all routes are open."""
    resp = open_client.get("/api/inbox")
    assert resp.status_code == 200


def test_mc_api_token_fallback(monkeypatch: Any) -> None:
    """When JARVIS_API_TOKEN is unset but MC_API_TOKEN is set, MC_API_TOKEN gates the API."""
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.setenv("MC_API_TOKEN", "mc-secret")
    from jarvis.apps.api import app as api_module

    client = TestClient(api_module.make_app())
    assert client.get("/api/inbox").status_code == 401
    assert (
        client.get("/api/inbox", headers={"Authorization": "Bearer mc-secret"}).status_code
        == 200
    )


def test_options_request_skipped_for_cors(authed_client: TestClient) -> None:
    """Preflight OPTIONS requests bypass auth so CORS works."""
    resp = authed_client.options(
        "/api/inbox",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Either 200 (handled by CORS middleware) or 405 (no OPTIONS handler) — both are
    # acceptable; the assertion is that auth did NOT 401 it.
    assert resp.status_code != 401
