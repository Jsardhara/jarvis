"""TDD tests for operator preferences.

Covers:
- load_preferences returns defaults if state/preferences.json missing
- save_preferences persists; subsequent load returns saved values
- load/save roundtrip is lossless
- API GET /api/preferences returns dict
- API PUT /api/preferences persists and echoes back
- PUT rejects bad types (422)
"""
from __future__ import annotations

import json

import pytest

from jarvis.config import Settings
from jarvis.state.memory import OperatorPreferences, load_preferences, save_preferences

# ── unit tests ─────────────────────────────────────────────────────────────


def test_load_preferences_returns_defaults_if_missing(tmp_path, monkeypatch):
    """load_preferences returns a default OperatorPreferences when file absent."""
    fake = Settings(project_root=tmp_path, state_dir=tmp_path, atlas_api="http://x")
    monkeypatch.setattr("jarvis.state.memory.get_settings", lambda: fake)

    prefs = load_preferences()
    assert isinstance(prefs, OperatorPreferences)
    assert prefs.important_senders == ()
    assert prefs.scholar_lead_time_days == 7
    assert prefs.atlas_risk_tolerance == 0.05


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    """Saved preferences can be loaded back identically."""
    fake = Settings(project_root=tmp_path, state_dir=tmp_path, atlas_api="http://x")
    monkeypatch.setattr("jarvis.state.memory.get_settings", lambda: fake)

    prefs = OperatorPreferences(
        important_senders=("alice@example.com", "bob@example.com"),
        scholar_lead_time_days=14,
        atlas_risk_tolerance=0.02,
    )
    save_preferences(prefs)
    loaded = load_preferences()
    assert loaded.important_senders == ("alice@example.com", "bob@example.com")
    assert loaded.scholar_lead_time_days == 14
    assert loaded.atlas_risk_tolerance == 0.02


def test_save_preferences_writes_json_file(tmp_path, monkeypatch):
    """save_preferences creates a preferences.json in state_dir."""
    fake = Settings(project_root=tmp_path, state_dir=tmp_path, atlas_api="http://x")
    monkeypatch.setattr("jarvis.state.memory.get_settings", lambda: fake)

    prefs = OperatorPreferences(scholar_lead_time_days=3)
    save_preferences(prefs)

    path = tmp_path / "preferences.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["scholar_lead_time_days"] == 3


def test_save_is_atomic_on_repeated_writes(tmp_path, monkeypatch):
    """Second save overwrites cleanly — no duplicate keys."""
    fake = Settings(project_root=tmp_path, state_dir=tmp_path, atlas_api="http://x")
    monkeypatch.setattr("jarvis.state.memory.get_settings", lambda: fake)

    save_preferences(OperatorPreferences(scholar_lead_time_days=5))
    save_preferences(OperatorPreferences(scholar_lead_time_days=10))

    loaded = load_preferences()
    assert loaded.scholar_lead_time_days == 10


# ── API tests ──────────────────────────────────────────────────────────────


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from jarvis.config import Settings
    from jarvis.apps.api.app import make_app

    fake = Settings(project_root=tmp_path, state_dir=tmp_path, atlas_api="http://x")
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)
    monkeypatch.setattr("jarvis.state.memory.get_settings", lambda: fake)
    monkeypatch.setattr("jarvis.config.get_settings", lambda: fake)

    return TestClient(make_app())


def test_get_preferences_returns_200(api_client):
    r = api_client.get("/api/preferences")
    assert r.status_code == 200


def test_get_preferences_shape(api_client):
    body = api_client.get("/api/preferences").json()
    assert "important_senders" in body
    assert "scholar_lead_time_days" in body
    assert "atlas_risk_tolerance" in body


def test_put_preferences_persists(api_client, tmp_path, monkeypatch):
    payload = {
        "important_senders": ["x@y.com"],
        "scholar_lead_time_days": 3,
        "atlas_risk_tolerance": 0.03,
    }
    r = api_client.put("/api/preferences", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["scholar_lead_time_days"] == 3
    assert body["atlas_risk_tolerance"] == 0.03
    assert "x@y.com" in body["important_senders"]


def test_put_preferences_bad_type_rejected(api_client):
    """scholar_lead_time_days must be int; string should return 422."""
    r = api_client.put(
        "/api/preferences",
        json={"scholar_lead_time_days": "not-an-int"},
    )
    assert r.status_code == 422


def test_put_preferences_invalid_risk_tolerance(api_client):
    """atlas_risk_tolerance > 1.0 is invalid — expect 422."""
    r = api_client.put(
        "/api/preferences",
        json={"atlas_risk_tolerance": 5.0},
    )
    assert r.status_code == 422


def test_get_after_put_reflects_update(api_client):
    api_client.put(
        "/api/preferences",
        json={"scholar_lead_time_days": 21},
    )
    body = api_client.get("/api/preferences").json()
    assert body["scholar_lead_time_days"] == 21
