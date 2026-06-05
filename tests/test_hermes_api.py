"""Tests for Hermes-normalized API endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_hermes_agents_endpoint_returns_manifest_cards(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_API_TOKEN", raising=False)
    monkeypatch.delenv("MC_API_TOKEN", raising=False)

    from jarvis.apps.api import app as api_module

    client = TestClient(api_module.make_app(registry={}))
    resp = client.get("/api/hermes/agents")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["system"] == "jarvis-hermes"
    assert payload["migration_strategy"] == "hybrid"

    by_id = {agent["id"]: agent for agent in payload["agents"]}
    assert set(by_id) == {"jarvis", "tempo", "scholar", "lens", "forge", "atlas", "sentinel", "me"}
    assert by_id["jarvis"]["role"] == "Chief-of-staff orchestrator"
    assert by_id["tempo"]["color"] == "blue"
    assert by_id["atlas"]["status"] == "paper"
    assert by_id["atlas"]["safety"]["atlas_source_read_only_default"] is True
    assert "source_path" not in by_id["atlas"]["safety"]
    assert "pending_approvals" in by_id["jarvis"]["dashboard"]["primary_widgets"]
