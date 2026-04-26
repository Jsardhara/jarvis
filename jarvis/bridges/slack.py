"""Slack bridge — Events API webhook + send via chat.postMessage.

Phase 4 ships verifying signature + parsing event payload + send method.
Wire-up to FastAPI app lives in jarvis/web/ (Phase 6) but the verifier
and parser are usable today.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import httpx

from ..config import get_settings


class SlackSignatureError(Exception):
    pass


def verify_slack_signature(body: bytes, timestamp: str, signature: str,
                           signing_secret: str, max_skew: int = 60 * 5) -> bool:
    """Slack v0 signing. https://api.slack.com/authentication/verifying-requests-from-slack"""
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > max_skew:
        return False
    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_event(payload: dict) -> dict | None:
    """Pull a normalized {surface, channel, channel_type, user, text, ts} dict."""
    if payload.get("type") == "url_verification":
        return None
    event = payload.get("event") or {}
    if event.get("type") != "message" or event.get("subtype"):
        return None
    return {
        "surface": "slack",
        "channel": event.get("channel"),
        "channel_type": event.get("channel_type"),
        "user": event.get("user"),
        "text": event.get("text", ""),
        "ts": event.get("ts"),
    }


class SlackBridge:
    surface = "slack"
    URL = "https://slack.com/api/chat.postMessage"

    def __init__(self, bot_token: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.bot_token = bot_token or get_settings().slack_bot_token
        self._client = httpx.Client(timeout=5.0, transport=transport)

    def send(self, channel: str, body: str) -> dict[str, Any]:
        if not self.bot_token:
            return {"ok": False, "error": "no_bot_token"}
        r = self._client.post(self.URL, json={"channel": channel, "text": body},
                              headers={"Authorization": f"Bearer {self.bot_token}"})
        return r.json() if r.status_code == 200 else {"ok": False, "status": r.status_code}
