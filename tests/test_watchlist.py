"""Tests for watchlist state helpers and API endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.config import Settings


def _fake_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        state_dir=tmp_path,
        atlas_api="http://localhost:8000",
    )


# ──────────────────────────────────────────────────────────────────────────────
# State helpers
# ──────────────────────────────────────────────────────────────────────────────


def test_load_watchlist_defaults_when_missing(tmp_path: Path, monkeypatch) -> None:
    """load_watchlist returns default items when watchlist.json doesn't exist."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from jarvis.state import load_watchlist

    items = load_watchlist()
    assert isinstance(items, list)
    assert len(items) >= 1  # defaults exist


def test_load_watchlist_default_contents(tmp_path: Path, monkeypatch) -> None:
    """Default watchlist contains BTC, ETH, SOL."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from jarvis.state import load_watchlist

    items = load_watchlist()
    assert "BTC" in items
    assert "ETH" in items
    assert "SOL" in items


def test_save_and_load_watchlist_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """save_watchlist then load_watchlist returns same list."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from jarvis.state import load_watchlist, save_watchlist

    new_items = ["AAPL", "NVDA", "TSLA"]
    save_watchlist(new_items)
    loaded = load_watchlist()
    assert loaded == new_items


def test_save_watchlist_persists_to_disk(tmp_path: Path, monkeypatch) -> None:
    """save_watchlist writes watchlist.json to state_dir."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from jarvis.state import save_watchlist

    save_watchlist(["XYZ"])
    wl_path = tmp_path / "watchlist.json"
    assert wl_path.exists()
    import json

    data = json.loads(wl_path.read_text(encoding="utf-8"))
    assert data["items"] == ["XYZ"]


def test_save_watchlist_immutable(tmp_path: Path, monkeypatch) -> None:
    """save_watchlist does not mutate the input list."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from jarvis.state import save_watchlist

    original = ["BTC", "ETH"]
    save_watchlist(original)
    assert original == ["BTC", "ETH"]


# ──────────────────────────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch):
    """TestClient with state patched to tmp_path."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)
    # Also patch inside api module
    monkeypatch.setattr("jarvis.apps.api.app.read_inbox", lambda limit=50: [])

    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    app = make_app()
    return TestClient(app)


def test_api_get_watchlist_returns_defaults(tmp_path: Path, monkeypatch) -> None:
    """GET /api/watchlist returns default items before any save."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    app = make_app()
    client = TestClient(app)
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "BTC" in data["items"]


def test_api_put_watchlist_saves_and_returns(tmp_path: Path, monkeypatch) -> None:
    """PUT /api/watchlist saves list and returns updated items."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    app = make_app()
    client = TestClient(app)
    resp = client.put("/api/watchlist", json={"items": ["AAPL", "GOOG"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == ["AAPL", "GOOG"]


def test_api_watchlist_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """PUT then GET returns the same items."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    app = make_app()
    client = TestClient(app)
    client.put("/api/watchlist", json={"items": ["SOL", "DOT"]})
    resp = client.get("/api/watchlist")
    assert resp.json()["items"] == ["SOL", "DOT"]


def test_api_put_watchlist_rejects_non_list(tmp_path: Path, monkeypatch) -> None:
    """PUT /api/watchlist with non-list items returns 422."""
    fake = _fake_settings(tmp_path)
    monkeypatch.setattr("jarvis.state.get_settings", lambda: fake)

    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    app = make_app()
    client = TestClient(app)
    resp = client.put("/api/watchlist", json={"items": "not-a-list"})
    assert resp.status_code == 422
