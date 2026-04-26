"""Notifier tests — Pushover + noop."""
from __future__ import annotations

import httpx

from jarvis.daemon.notifier import NoopNotifier, PushoverNotifier, default_notifier


def test_noop_records_calls():
    n = NoopNotifier()
    assert n.push("t", "b", priority=1) is True
    assert n.calls == [("t", "b", 1)]


def test_pushover_no_creds_returns_false():
    n = PushoverNotifier(user_key=None, api_token=None)
    assert n.push("t", "b") is False


def test_pushover_calls_api():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"status": 1}))
    n = PushoverNotifier(user_key="u", api_token="a", transport=transport)
    assert n.push("t", "b", priority=0) is True


def test_pushover_handles_http_error():
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    n = PushoverNotifier(user_key="u", api_token="a", transport=transport)
    assert n.push("t", "b") is False


def test_default_notifier_returns_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
    monkeypatch.delenv("PUSHOVER_API_TOKEN", raising=False)
    from jarvis.config import get_settings
    get_settings.cache_clear()
    n = default_notifier()
    assert isinstance(n, NoopNotifier)
