"""Notification routing — Pushover primary, desktop fallback, no-op in tests."""
from __future__ import annotations

import logging
from typing import Protocol

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def push(self, title: str, body: str, priority: int = 0) -> bool: ...


class PushoverNotifier:
    """Pushover client. https://pushover.net/api"""

    URL = "https://api.pushover.net/1/messages.json"

    def __init__(self, user_key: str | None = None, api_token: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self.user_key = user_key or s.pushover_user_key
        self.api_token = api_token or s.pushover_api_token
        self._client = httpx.Client(timeout=5.0, transport=transport)

    def push(self, title: str, body: str, priority: int = 0) -> bool:
        if not (self.user_key and self.api_token):
            log.warning("Pushover not configured; skipping push: %s", title)
            return False
        try:
            r = self._client.post(self.URL, data={
                "token": self.api_token,
                "user": self.user_key,
                "title": title,
                "message": body,
                "priority": priority,
            })
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.error("Pushover failure: %s", e)
            return False


class NtfyNotifier:
    """ntfy.sh client — free push, topic-based, no API key.

    Phone subscribes to the topic in the ntfy app; server publishes to
    `${server}/${topic}`. https://docs.ntfy.sh/publish/
    """

    def __init__(
        self,
        topic: str | None = None,
        server: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        s = get_settings()
        self.topic = topic or s.ntfy_topic
        self.server = (server or s.ntfy_server).rstrip("/")
        self._client = httpx.Client(timeout=5.0, transport=transport)

    def push(self, title: str, body: str, priority: int = 0) -> bool:
        if not self.topic:
            log.warning("ntfy not configured; skipping push: %s", title)
            return False
        # ntfy priority: 1 (min) … 5 (max). Map our 0 → default 3.
        ntfy_priority = max(1, min(5, priority + 3 if priority else 3))
        try:
            r = self._client.post(
                f"{self.server}/{self.topic}",
                content=body.encode("utf-8"),
                headers={
                    "Title": title,
                    "Priority": str(ntfy_priority),
                    "Tags": "robot",
                },
            )
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.error("ntfy failure: %s", e)
            return False


class NoopNotifier:
    """For tests + when no provider is configured. Records calls."""

    def __init__(self):
        self.calls: list[tuple[str, str, int]] = []

    def push(self, title: str, body: str, priority: int = 0) -> bool:
        self.calls.append((title, body, priority))
        return True


def default_notifier() -> Notifier:
    s = get_settings()
    if s.pushover_user_key and s.pushover_api_token:
        return PushoverNotifier()
    if s.ntfy_topic:
        return NtfyNotifier()
    return NoopNotifier()
