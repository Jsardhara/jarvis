"""Notifier tests — Pushover + noop."""
from __future__ import annotations

import httpx

from jarvis.apps.sentinel.notifier import (
    NoopNotifier,
    NtfyNotifier,
    PushoverNotifier,
    default_notifier,
)


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
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    from jarvis.config import get_settings
    get_settings.cache_clear()
    n = default_notifier()
    assert isinstance(n, NoopNotifier)


def test_ntfy_no_topic_returns_false():
    n = NtfyNotifier(topic=None)
    assert n.push("t", "b") is False


def test_ntfy_publishes_to_topic():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = req.content
        captured["title"] = req.headers.get("Title")
        captured["priority"] = req.headers.get("Priority")
        return httpx.Response(200)

    n = NtfyNotifier(topic="jarvis-test", server="https://ntfy.sh", transport=httpx.MockTransport(handler))
    assert n.push("hello", "world", priority=2) is True
    assert captured["url"] == "https://ntfy.sh/jarvis-test"
    assert captured["body"] == b"world"
    assert captured["title"] == "hello"
    assert captured["priority"] == "5"  # 2 + 3, clamped to <= 5


def test_ntfy_handles_http_error():
    n = NtfyNotifier(
        topic="jarvis-test",
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    )
    assert n.push("t", "b") is False


def test_default_notifier_picks_ntfy_when_topic_set(monkeypatch):
    monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
    monkeypatch.delenv("PUSHOVER_API_TOKEN", raising=False)
    monkeypatch.setenv("NTFY_TOPIC", "jarvis-test")
    from jarvis.config import get_settings
    get_settings.cache_clear()
    n = default_notifier()
    assert isinstance(n, NtfyNotifier)
    get_settings.cache_clear()


def test_default_notifier_prefers_pushover_over_ntfy(monkeypatch):
    monkeypatch.setenv("PUSHOVER_USER_KEY", "u")
    monkeypatch.setenv("PUSHOVER_API_TOKEN", "a")
    monkeypatch.setenv("NTFY_TOPIC", "jarvis-test")
    from jarvis.config import get_settings
    get_settings.cache_clear()
    n = default_notifier()
    assert isinstance(n, PushoverNotifier)
    get_settings.cache_clear()
