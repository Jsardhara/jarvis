"""TDD tests for WebSocket inbox broadcast.

Covers:
- append_inbox triggers registered listener callback
- listener receives inbox.event message shape
- multiple listeners all receive the event
- removing a listener stops delivery
"""
from __future__ import annotations

import pytest

from jarvis.contract import InboxEvent
from jarvis.state import append_inbox, register_inbox_listener, unregister_inbox_listener


def test_append_inbox_triggers_listener():
    """Registered listener is called when append_inbox fires."""
    received: list[InboxEvent] = []

    def listener(event: InboxEvent) -> None:
        received.append(event)

    register_inbox_listener(listener)
    try:
        evt = InboxEvent(agent="tempo", severity="info", summary="ws-test-1")
        append_inbox(evt)
        assert len(received) == 1
        assert received[0].summary == "ws-test-1"
    finally:
        unregister_inbox_listener(listener)


def test_append_inbox_multiple_listeners():
    """All registered listeners are called."""
    a: list[InboxEvent] = []
    b: list[InboxEvent] = []

    def la(ev: InboxEvent) -> None:
        a.append(ev)

    def lb(ev: InboxEvent) -> None:
        b.append(ev)

    register_inbox_listener(la)
    register_inbox_listener(lb)
    try:
        append_inbox(InboxEvent(agent="lens", severity="warn", summary="multi"))
        assert len(a) == 1
        assert len(b) == 1
    finally:
        unregister_inbox_listener(la)
        unregister_inbox_listener(lb)


def test_unregister_stops_delivery():
    """After unregistering, listener is no longer called."""
    received: list[InboxEvent] = []

    def listener(ev: InboxEvent) -> None:
        received.append(ev)

    register_inbox_listener(listener)
    append_inbox(InboxEvent(agent="forge", severity="info", summary="first"))
    assert len(received) == 1

    unregister_inbox_listener(listener)
    append_inbox(InboxEvent(agent="forge", severity="info", summary="second"))
    assert len(received) == 1  # no new delivery


def test_duplicate_register_is_idempotent():
    """Registering the same function twice calls it only once per event."""
    received: list[InboxEvent] = []

    def listener(ev: InboxEvent) -> None:
        received.append(ev)

    register_inbox_listener(listener)
    register_inbox_listener(listener)  # duplicate
    try:
        append_inbox(InboxEvent(agent="atlas", severity="alert", summary="dup-test"))
        assert len(received) == 1
    finally:
        unregister_inbox_listener(listener)


def test_listener_exception_does_not_abort_others():
    """A failing listener must not prevent subsequent listeners from running."""
    good: list[InboxEvent] = []

    def bad(ev: InboxEvent) -> None:
        raise RuntimeError("boom")

    def ok(ev: InboxEvent) -> None:
        good.append(ev)

    register_inbox_listener(bad)
    register_inbox_listener(ok)
    try:
        append_inbox(InboxEvent(agent="scholar", severity="info", summary="resilient"))
        assert len(good) == 1
    finally:
        unregister_inbox_listener(bad)
        unregister_inbox_listener(ok)


# ── API integration: /ws receives inbox.event ─────────────────────────────


def test_ws_receives_inbox_event():
    """The WebSocket /ws endpoint receives an inbox.event broadcast.

    Opens WS (which captures the running loop in `_active_loop`), then calls
    `append_inbox` from main thread — the registered listener schedules the
    broadcast onto the captured loop via `run_coroutine_threadsafe`.
    """
    pytest.importorskip("fastapi")

    from fastapi.testclient import TestClient

    from jarvis.apps.api.app import make_app

    app = make_app()
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        evt = InboxEvent(agent="tempo", severity="info", summary="ws-inbox-push")
        append_inbox(evt)
        data = ws.receive_json()
        assert data["type"] == "inbox.event"
        assert data["event"]["summary"] == "ws-inbox-push"


def test_make_app_registers_inbox_listener():
    """make_app registers _push_inbox_event as an inbox listener."""
    pytest.importorskip("fastapi")
    from jarvis.state import _inbox_listeners
    from jarvis.apps.api.app import _push_inbox_event, make_app

    make_app()
    assert _push_inbox_event in _inbox_listeners
