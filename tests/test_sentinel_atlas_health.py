"""Tests: Sentinel Atlas health check — 200→503 transition triggers push notification."""
from __future__ import annotations

import httpx
import respx

from jarvis.daemon.sentinel import _atlas_health_last, atlas_health_tick


def _reset_health_state():
    """Reset module-level health tracking between tests."""
    _atlas_health_last["healthy"] = None


def test_first_check_no_transition(monkeypatch):
    """First health check (no prior state) never emits a notification."""
    _reset_health_state()
    pushed: list[str] = []

    def _fake_append(event):
        pushed.append(event.summary)

    # append_inbox is imported locally inside atlas_health_tick — patch at source
    monkeypatch.setattr("jarvis.state.append_inbox", _fake_append)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("http://atlas-h1:8000/system/health").mock(return_value=httpx.Response(200))
        result = atlas_health_tick("http://atlas-h1:8000")

    assert result["healthy"] is True
    assert result["transitioned"] is False
    assert pushed == []


def test_healthy_to_degraded_transition(monkeypatch):
    """200→503 transition pushes 'Atlas degraded' notification."""
    _reset_health_state()
    _atlas_health_last["healthy"] = True  # Simulate previously healthy

    pushed: list[str] = []

    def _fake_append(event):
        pushed.append(event.summary)

    monkeypatch.setattr("jarvis.state.append_inbox", _fake_append)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("http://atlas-h2:8000/system/health").mock(return_value=httpx.Response(503))
        result = atlas_health_tick("http://atlas-h2:8000")

    assert result["healthy"] is False
    assert result["transitioned"] is True
    assert any("degraded" in s.lower() for s in pushed)


def test_degraded_to_healthy_transition(monkeypatch):
    """503→200 transition pushes 'Atlas recovered' notification."""
    _reset_health_state()
    _atlas_health_last["healthy"] = False  # Simulate previously degraded

    pushed: list[str] = []

    def _fake_append(event):
        pushed.append(event.summary)

    monkeypatch.setattr("jarvis.state.append_inbox", _fake_append)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("http://atlas-h3:8000/system/health").mock(return_value=httpx.Response(200))
        result = atlas_health_tick("http://atlas-h3:8000")

    assert result["healthy"] is True
    assert result["transitioned"] is True
    assert any("recovered" in s.lower() for s in pushed)


def test_stable_healthy_no_notification(monkeypatch):
    """200→200 (no transition) does not push any notification."""
    _reset_health_state()
    _atlas_health_last["healthy"] = True

    pushed: list[str] = []

    def _fake_append(event):
        pushed.append(event.summary)

    monkeypatch.setattr("jarvis.state.append_inbox", _fake_append)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("http://atlas-h4:8000/system/health").mock(return_value=httpx.Response(200))
        atlas_health_tick("http://atlas-h4:8000")

    assert pushed == []


def test_network_error_treated_as_unhealthy(monkeypatch):
    """ConnectError is treated as unhealthy (False)."""
    _reset_health_state()
    _atlas_health_last["healthy"] = True  # Was healthy

    pushed: list[str] = []

    def _fake_append(event):
        pushed.append(event.summary)

    monkeypatch.setattr("jarvis.state.append_inbox", _fake_append)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("http://atlas-h5:8000/system/health").mock(
            side_effect=httpx.ConnectError("refused")
        )
        result = atlas_health_tick("http://atlas-h5:8000")

    assert result["healthy"] is False
    assert result["transitioned"] is True
    assert any("degraded" in s.lower() for s in pushed)


def test_atlas_health_job_registered_in_scheduler():
    """build_scheduler registers atlas_health job with 60s interval."""
    from apscheduler.schedulers.background import BackgroundScheduler

    from jarvis.daemon.sentinel import build_scheduler

    sched = build_scheduler(BackgroundScheduler(timezone="UTC"))
    job_ids = {j.id for j in sched.get_jobs()}
    assert "atlas_health" in job_ids
    by_id = {j.id: j for j in sched.get_jobs()}
    assert by_id["atlas_health"].trigger.interval.total_seconds() == 60
