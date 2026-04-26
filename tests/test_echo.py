"""Echo + bridge tests."""
from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from jarvis.bridges.discord import DiscordBridge
from jarvis.bridges.slack import SlackBridge, parse_event, verify_slack_signature
from jarvis.bridges.twilio_sms import TwilioBridge, parse_twilio_form
from jarvis.subsystems.echo import (
    URGENCY_FYI,
    URGENCY_NOW,
    URGENCY_TODAY,
    Echo,
    classify_urgency,
)


def test_classify_urgency_keyword():
    assert classify_urgency({"text": "URGENT need this"}) == URGENCY_NOW


def test_classify_urgency_dm_default_today():
    assert classify_urgency({"text": "hey", "channel_type": "dm"}) == URGENCY_TODAY


def test_classify_urgency_mention():
    assert classify_urgency({"text": "@you", "channel_type": "mention"}) == URGENCY_NOW


def test_classify_urgency_channel_default_fyi():
    assert classify_urgency({"text": "fyi", "channel_type": "channel"}) == URGENCY_FYI


def test_echo_triage_buckets():
    e = Echo()
    msgs = [
        {"text": "asap please", "channel_type": "channel"},
        {"text": "hello", "channel_type": "dm"},
        {"text": "fyi update", "channel_type": "channel"},
    ]
    resp = e.triage(msgs)
    assert resp.result["counts"][URGENCY_NOW] == 1
    assert resp.result["counts"][URGENCY_TODAY] == 1
    assert resp.result["counts"][URGENCY_FYI] == 1


def test_echo_send_no_bridge_fails():
    e = Echo()
    resp = e.send("slack", "C123", "hi")
    assert resp.action == "failed"


def test_echo_send_with_bridge():
    class FakeBridge:
        surface = "slack"
        def send(self, channel, body):
            return {"ok": True, "channel": channel}
    e = Echo()
    e.register(FakeBridge())
    resp = e.send("slack", "C123", "hi")
    assert resp.action == "sent"


def test_echo_draft_needs_confirm():
    e = Echo()
    resp = e.draft_reply("slack", "C123", "yo")
    assert resp.needs_confirm is True


# -------- Bridge signature/parse --------

def test_slack_signature_valid():
    body = b'{"type":"event_callback"}'
    ts = str(int(time.time()))
    secret = "abc"
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    assert verify_slack_signature(body, ts, sig, secret) is True


def test_slack_signature_skewed_rejected():
    body = b"x"
    ts = str(int(time.time()) - 10000)
    secret = "abc"
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    assert verify_slack_signature(body, ts, sig, secret) is False


def test_slack_signature_bad_timestamp():
    assert verify_slack_signature(b"x", "not-a-ts", "v0=x", "abc") is False


def test_slack_parse_event_message():
    payload = {
        "event": {"type": "message", "channel": "C1", "channel_type": "channel",
                  "user": "U1", "text": "hi", "ts": "1.0"}
    }
    out = parse_event(payload)
    assert out["surface"] == "slack"
    assert out["text"] == "hi"


def test_slack_parse_event_url_verification_returns_none():
    assert parse_event({"type": "url_verification", "challenge": "x"}) is None


def test_slack_parse_event_subtype_returns_none():
    assert parse_event({"event": {"type": "message", "subtype": "bot_message"}}) is None


def test_twilio_parse_form():
    out = parse_twilio_form({"From": "+1", "Body": "hi", "MessageSid": "SM123"})
    assert out["surface"] == "sms"
    assert out["channel_type"] == "dm"


def test_slack_send_no_token():
    b = SlackBridge(bot_token=None)
    assert b.send("C", "x")["ok"] is False


def test_slack_send_with_token():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))
    b = SlackBridge(bot_token="xoxb-test", transport=transport)
    assert b.send("C", "x") == {"ok": True}


def test_discord_send_no_token():
    b = DiscordBridge(bot_token=None)
    assert b.send("123", "x")["ok"] is False


def test_discord_send_with_token():
    transport = httpx.MockTransport(lambda r: httpx.Response(201, json={"id": "x"}))
    b = DiscordBridge(bot_token="t", transport=transport)
    out = b.send("123", "x")
    assert out["ok"] is True


def test_twilio_missing_creds():
    b = TwilioBridge(account_sid=None, auth_token=None, from_number=None)
    assert b.send("+1", "x")["ok"] is False


def test_twilio_send():
    transport = httpx.MockTransport(lambda r: httpx.Response(201, json={"sid": "SM1"}))
    b = TwilioBridge(account_sid="AC", auth_token="t", from_number="+1", transport=transport)
    out = b.send("+19999999999", "x")
    assert out["ok"] is True
    assert out["sid"] == "SM1"
