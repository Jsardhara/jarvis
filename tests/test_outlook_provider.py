"""Tests for jarvis.subsystems.outlook_provider.

MSAL is mocked via unittest.mock; Graph is mocked via httpx.MockTransport.
No network. No real MSAL import path exercised.
"""
from __future__ import annotations

import inspect
import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from jarvis.subsystems.outlook_provider import (
    SCOPES,
    OutlookGraphError,
    OutlookProvider,
)
from jarvis.subsystems.providers import OutlookProvider as OutlookProtocol

# ---------- Helpers ----------


def _msal_app(token: str = "tok-1", *, has_account: bool = True, fail: bool = False):
    app = MagicMock()
    cache = MagicMock()
    cache.has_state_changed = False
    cache.serialize.return_value = "{}"
    app.token_cache = cache
    app.get_accounts.return_value = (
        [{"username": "user@example.com"}] if has_account else []
    )
    if fail:
        app.acquire_token_silent.return_value = None
        app.initiate_device_flow.return_value = {
            "user_code": "ABC123",
            "message": "Visit https://example.test/devicelogin and enter ABC123",
        }
        app.acquire_token_by_device_flow.return_value = {"error": "boom"}
        return app
    app.acquire_token_silent.return_value = {"access_token": token}
    app.initiate_device_flow.return_value = {
        "user_code": "ABC123",
        "message": "Visit https://example.test/devicelogin and enter ABC123",
    }
    app.acquire_token_by_device_flow.return_value = {"access_token": token}
    return app


def _provider(handler, msal_app: Any | None = None) -> OutlookProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return OutlookProvider(
        client_id="test-client",
        tenant="consumers",
        cache_path=None,
        http=client,
        msal_app=msal_app or _msal_app(),
    )


def _ok(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


# ---------- Protocol conformance ----------


def test_provider_satisfies_protocol_signatures():
    proto_methods = {
        name: inspect.signature(getattr(OutlookProtocol, name))
        for name in dir(OutlookProtocol)
        if not name.startswith("_") and callable(getattr(OutlookProtocol, name))
    }
    for name, sig in proto_methods.items():
        impl = getattr(OutlookProvider, name, None)
        assert impl is not None, f"missing method {name}"
        impl_sig = inspect.signature(impl)
        assert list(impl_sig.parameters) == list(sig.parameters), (
            f"signature mismatch on {name}: {impl_sig} vs {sig}"
        )


def test_eleven_protocol_methods_present():
    expected = {
        "list_unread", "get_message", "draft_reply", "send",
        "list_events", "create_event", "find_free", "cancel_event",
        "list_tasks", "add_task_remote", "complete_task_remote",
    }
    assert expected <= set(dir(OutlookProvider))


# ---------- Auth ----------


def test_acquire_token_silent_hit_skips_device_flow():
    app = _msal_app(token="silent-token")
    p = _provider(lambda req: _ok({"value": []}), msal_app=app)
    assert p._acquire_token() == "silent-token"
    app.initiate_device_flow.assert_not_called()


def test_acquire_token_silent_miss_falls_to_device_flow(capsys):
    app = _msal_app()
    app.get_accounts.return_value = []
    app.acquire_token_silent.return_value = None
    app.acquire_token_by_device_flow.return_value = {"access_token": "device-tok"}
    p = _provider(lambda req: _ok({"value": []}), msal_app=app)
    tok = p._acquire_token()
    assert tok == "device-tok"
    out = capsys.readouterr().out
    assert "ABC123" in out
    assert "device-tok" not in out


def test_acquire_token_failure_raises():
    app = _msal_app(fail=True)
    app.get_accounts.return_value = []
    p = _provider(lambda req: _ok({"value": []}), msal_app=app)
    with pytest.raises(OutlookGraphError):
        p._acquire_token()


def test_missing_client_id_raises_at_auth_time(monkeypatch):
    monkeypatch.delenv("OUTLOOK_CLIENT_ID", raising=False)
    p = OutlookProvider(client_id=None, msal_app=None, http=httpx.Client())
    with pytest.raises(OutlookGraphError):
        p._acquire_token()


def test_token_cache_persisted_when_state_changed(tmp_path):
    cache = MagicMock()
    cache.has_state_changed = True
    cache.serialize.return_value = '{"some":"state"}'
    app = MagicMock()
    app.token_cache = cache
    app.get_accounts.return_value = [{}]
    app.acquire_token_silent.return_value = {"access_token": "tok"}

    cache_path = tmp_path / "msal_cache.json"
    p = OutlookProvider(
        client_id="x",
        cache_path=cache_path,
        http=httpx.Client(transport=httpx.MockTransport(lambda r: _ok({"value": []}))),
        msal_app=app,
    )
    p._acquire_token()
    assert cache_path.exists()
    assert cache_path.read_text() == '{"some":"state"}'


def test_scopes_constant_includes_required():
    for s in (
        "Mail.ReadWrite",
        "Mail.Send",
        "Calendars.ReadWrite",
        "Tasks.ReadWrite",
        "User.Read",
    ):
        assert s in SCOPES


# ---------- Mail ----------


def test_list_unread_maps_graph_response():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1.0/me/messages"
        assert "isRead eq false" in req.url.params["$filter"]
        return _ok({
            "value": [{
                "id": "m1",
                "isRead": False,
                "subject": "hi",
                "bodyPreview": "snip",
                "from": {"emailAddress": {"address": "a@b.com"}},
                "categories": ["Important"],
            }]
        })

    p = _provider(handler)
    out = p.list_unread()
    assert out == [{
        "id": "m1",
        "from": "a@b.com",
        "subject": "hi",
        "snippet": "snip",
        "labels": ["INBOX", "UNREAD", "IMPORTANT"],
    }]


def test_get_message_returns_full_body():
    def handler(req):
        assert req.url.path == "/v1.0/me/messages/m9"
        return _ok({
            "id": "m9",
            "isRead": True,
            "subject": "s",
            "bodyPreview": "p",
            "from": {"emailAddress": {"address": "x@y.z"}},
        })
    p = _provider(handler)
    out = p.get_message("m9")
    assert out["id"] == "m9"
    assert out["from"] == "x@y.z"
    assert "UNREAD" not in out["labels"]


def test_send_mail_returns_synth_id_on_202():
    def handler(req):
        assert req.url.path == "/v1.0/me/sendMail"
        body = json.loads(req.content)
        assert (
            body["message"]["toRecipients"][0]["emailAddress"]["address"] == "to@x.com"
        )
        assert body["saveToSentItems"] is True
        return httpx.Response(202)
    p = _provider(handler)
    rec = p.send("to@x.com", "subj", "hello")
    assert rec["id"].startswith("sent-")
    assert rec["to"] == "to@x.com"
    assert rec["subject"] == "subj"
    assert rec["body"] == "hello"
    assert rec["ts"]


def test_draft_reply_creates_then_patches():
    calls: list[tuple[str, str]] = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "POST" and req.url.path.endswith("/createReply"):
            return _ok({"id": "draft-7"}, status=201)
        if req.method == "PATCH":
            body = json.loads(req.content)
            assert body["body"]["content"] == "reply text"
            return _ok({"id": "draft-7"})
        raise AssertionError(f"unexpected {req.method} {req.url}")

    p = _provider(handler)
    out = p.draft_reply("m1", "reply text")
    assert out == {"draft_id": "draft-7", "in_reply_to": "m1", "body": "reply text"}
    assert calls[0] == ("POST", "/v1.0/me/messages/m1/createReply")
    assert calls[1] == ("PATCH", "/v1.0/me/messages/draft-7")


# ---------- Calendar ----------


def test_list_events_calendar_view_maps_iso():
    def handler(req):
        assert req.url.path == "/v1.0/me/calendarView"
        assert req.url.params["startDateTime"] == "2026-04-27T00:00:00+00:00"
        return _ok({
            "value": [{
                "id": "e1",
                "subject": "Standup",
                "start": {"dateTime": "2026-04-27T14:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2026-04-27T14:30:00", "timeZone": "UTC"},
                "attendees": [
                    {"emailAddress": {"address": "team@example.com"}, "type": "required"}
                ],
            }]
        })

    p = _provider(handler)
    out = p.list_events("2026-04-27T00:00:00+00:00", "2026-04-27T23:59:59+00:00")
    assert out == [{
        "id": "e1",
        "summary": "Standup",
        "start": "2026-04-27T14:00:00+00:00",
        "end": "2026-04-27T14:30:00+00:00",
        "attendees": ["team@example.com"],
    }]


def test_create_event_payload_shape():
    captured: dict = {}

    def handler(req):
        captured["body"] = json.loads(req.content)
        return _ok({
            "id": "e2",
            "subject": "Sync",
            "start": {"dateTime": "2026-04-27T15:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2026-04-27T15:30:00", "timeZone": "UTC"},
            "attendees": [{"emailAddress": {"address": "x@y.z"}, "type": "required"}],
        }, status=201)

    p = _provider(handler)
    out = p.create_event(
        "Sync", "2026-04-27T15:00:00", "2026-04-27T15:30:00", ["x@y.z"]
    )
    assert captured["body"]["subject"] == "Sync"
    assert captured["body"]["attendees"][0]["emailAddress"]["address"] == "x@y.z"
    assert captured["body"]["start"]["timeZone"] == "UTC"
    assert out["id"] == "e2"
    assert out["attendees"] == ["x@y.z"]


def test_find_free_maps_suggestions():
    def handler(req):
        assert req.url.path == "/v1.0/me/findMeetingTimes"
        body = json.loads(req.content)
        assert body["meetingDuration"] == "PT45M"
        return _ok({
            "meetingTimeSuggestions": [{
                "meetingTimeSlot": {
                    "start": {"dateTime": "2026-04-27T15:00:00", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-04-27T15:45:00", "timeZone": "UTC"},
                }
            }]
        })
    p = _provider(handler)
    slots = p.find_free(45, "2026-04-27T09:00:00", "2026-04-27T17:00:00")
    assert slots == [{
        "start": "2026-04-27T15:00:00+00:00",
        "end": "2026-04-27T15:45:00+00:00",
        "duration_min": 45,
    }]


def test_cancel_event_204_returns_found_true():
    p = _provider(lambda req: httpx.Response(204))
    assert p.cancel_event("ev-1") == {"cancelled": "ev-1", "found": True}


def test_cancel_event_404_returns_found_false():
    p = _provider(lambda req: httpx.Response(404, json={"error": "missing"}))
    assert p.cancel_event("ev-x") == {"cancelled": "ev-x", "found": False}


def test_cancel_event_other_error_raises():
    p = _provider(lambda req: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(OutlookGraphError):
        p.cancel_event("ev-x")


# ---------- Tasks ----------


def test_list_tasks_resolves_default_list_and_memoizes():
    calls: list[str] = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path == "/v1.0/me/todo/lists":
            return _ok({
                "value": [
                    {"id": "list-default", "wellknownListName": "defaultList"},
                    {"id": "list-other", "wellknownListName": "flagged"},
                ]
            })
        if req.url.path == "/v1.0/me/todo/lists/list-default/tasks":
            return _ok({
                "value": [
                    {"id": "t1", "title": "Submit PSet", "status": "notStarted"},
                    {
                        "id": "t2",
                        "title": "Review",
                        "status": "completed",
                        "dueDateTime": {
                            "dateTime": "2026-05-01T00:00:00",
                            "timeZone": "UTC",
                        },
                    },
                ]
            })
        raise AssertionError(f"unexpected path {req.url.path}")

    p = _provider(handler)
    out = p.list_tasks()
    assert out == [
        {"id": "t1", "title": "Submit PSet", "due": None, "status": "open"},
        {"id": "t2", "title": "Review", "due": "2026-05-01T00:00:00", "status": "done"},
    ]
    p.list_tasks()
    list_lookups = [c for c in calls if c == "/v1.0/me/todo/lists"]
    assert len(list_lookups) == 1


def test_add_task_remote_with_due():
    captured: dict = {}

    def handler(req):
        if req.url.path == "/v1.0/me/todo/lists":
            return _ok({"value": [{"id": "L1", "wellknownListName": "defaultList"}]})
        captured["body"] = json.loads(req.content)
        return _ok({
            "id": "tnew",
            "title": "Pay tuition",
            "status": "notStarted",
            "dueDateTime": {"dateTime": "2026-06-01T00:00:00", "timeZone": "UTC"},
        }, status=201)

    p = _provider(handler)
    out = p.add_task_remote("Pay tuition", due="2026-06-01T00:00:00")
    assert captured["body"]["dueDateTime"]["dateTime"] == "2026-06-01T00:00:00"
    assert out == {
        "id": "tnew",
        "title": "Pay tuition",
        "due": "2026-06-01T00:00:00",
        "status": "open",
    }


def test_add_task_remote_without_due():
    captured: dict = {}

    def handler(req):
        if req.url.path == "/v1.0/me/todo/lists":
            return _ok({"value": [{"id": "L1", "wellknownListName": "defaultList"}]})
        captured["body"] = json.loads(req.content)
        return _ok({"id": "t9", "title": "Hi", "status": "notStarted"}, status=201)

    p = _provider(handler)
    p.add_task_remote("Hi", due=None)
    assert "dueDateTime" not in captured["body"]


def test_complete_task_remote_ok():
    def handler(req):
        if req.url.path == "/v1.0/me/todo/lists":
            return _ok({"value": [{"id": "L1", "wellknownListName": "defaultList"}]})
        return _ok({"id": "t1", "title": "x", "status": "completed"})
    p = _provider(handler)
    assert p.complete_task_remote("t1") == {
        "id": "t1", "title": "x", "due": None, "status": "done",
    }


def test_complete_task_remote_404_returns_not_found():
    def handler(req):
        if req.url.path == "/v1.0/me/todo/lists":
            return _ok({"value": [{"id": "L1", "wellknownListName": "defaultList"}]})
        return _ok({"error": "missing"}, status=404)
    p = _provider(handler)
    assert p.complete_task_remote("missing") == {
        "id": "missing", "status": "not_found",
    }


def test_resolve_default_list_empty_raises():
    p = _provider(lambda req: _ok({"value": []}))
    with pytest.raises(OutlookGraphError):
        p.list_tasks()


# ---------- Retry behavior ----------


def test_401_invalidates_token_and_retries():
    states = {"calls": 0}

    def handler(req):
        states["calls"] += 1
        if states["calls"] == 1:
            return httpx.Response(401, json={"error": "expired"})
        return _ok({"value": []})

    p = _provider(handler)
    p.list_unread()
    assert states["calls"] == 2


def test_429_respects_retry_after():
    states = {"calls": 0}

    def handler(req):
        states["calls"] += 1
        if states["calls"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return _ok({"value": []})

    p = _provider(handler)
    p.list_unread()
    assert states["calls"] == 2


def test_non_recoverable_error_raises():
    p = _provider(lambda req: httpx.Response(500, json={"error": "down"}))
    with pytest.raises(OutlookGraphError) as exc:
        p.list_unread()
    assert exc.value.status == 500


def test_safe_body_falls_back_to_text():
    p = _provider(lambda req: httpx.Response(500, content=b"not-json"))
    with pytest.raises(OutlookGraphError) as exc:
        p.list_unread()
    assert exc.value.body == "not-json"


# ---------- Logging hygiene ----------


def test_token_never_logged(caplog, capsys):
    caplog.set_level("DEBUG", logger="jarvis.subsystems.outlook_provider")
    app = _msal_app(token="SUPER-SECRET-TOKEN")
    p = _provider(lambda req: _ok({"value": []}), msal_app=app)
    p.list_unread()
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "SUPER-SECRET-TOKEN" not in blob
    assert "SUPER-SECRET-TOKEN" not in capsys.readouterr().out
