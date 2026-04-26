"""FastAPI webhook receiver smoke tests."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.subsystems.echo import Echo
from jarvis.web.webhooks import make_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
    from jarvis.config import get_settings
    get_settings.cache_clear()
    app = make_app(Echo())
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_slack_url_verification(client):
    body = {"type": "url_verification", "challenge": "abc123"}
    r = client.post("/webhooks/slack", json=body)
    assert r.status_code == 200
    assert r.text == "abc123"


def test_slack_message_event_no_secret(client):
    body = {"event": {"type": "message", "channel": "C1", "channel_type": "channel",
                      "user": "U1", "text": "hi", "ts": "1.0"}}
    r = client.post("/webhooks/slack", json=body)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_slack_signature_required_when_secret_set(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "topsecret")
    from jarvis.config import get_settings
    get_settings.cache_clear()
    app = make_app(Echo())
    client = TestClient(app)

    body = json.dumps({"event": {"type": "message"}}).encode()
    r = client.post("/webhooks/slack", content=body,
                    headers={"x-slack-signature": "v0=bad",
                             "x-slack-request-timestamp": str(int(time.time()))})
    assert r.status_code == 401


def test_slack_signature_passes_when_correct(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "topsecret")
    from jarvis.config import get_settings
    get_settings.cache_clear()
    app = make_app(Echo())
    client = TestClient(app)

    body = json.dumps({"event": {"type": "message", "channel": "C1",
                                 "channel_type": "channel", "user": "U", "text": "hi",
                                 "ts": "1"}}).encode()
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(b"topsecret", f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    r = client.post("/webhooks/slack", content=body,
                    headers={"x-slack-signature": sig, "x-slack-request-timestamp": ts})
    assert r.status_code == 200


def test_twilio_webhook(client):
    r = client.post("/webhooks/twilio",
                    data={"From": "+15551234567", "Body": "yo", "MessageSid": "SM1"})
    assert r.status_code == 200
    assert "<Response/>" in r.text


def test_discord_webhook(client):
    r = client.post("/webhooks/discord", json={
        "channel_id": "123", "author": {"id": "u1"}, "content": "hello", "id": "msg1",
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
