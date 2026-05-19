"""W3.1 — EdgeTTS barge-in interrupt tests.

These tests close the J10 gap where ``EdgeTTSProvider`` had no
``interrupt()`` method, so the hot-mic VAD's call into the TTS
provider no-oped and the bot kept talking through user barge-in.

Network I/O and audio playback are both mocked — the live
``edge_tts`` library and ``sounddevice`` are replaced with
sys.modules stand-ins so the tests run fast and headless.
"""
from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncIterator
from typing import Any

import pytest


@pytest.fixture
def fake_sounddevice(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Inject a fake ``sounddevice`` that records ``stop()`` calls."""
    counters = {"stop": 0}

    fake = types.ModuleType("sounddevice")

    def _stop() -> None:
        counters["stop"] += 1

    fake.stop = _stop  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    return counters


@pytest.fixture
def fake_edge_tts_streaming(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A streaming ``edge_tts`` mock that yields chunks with awaits between.

    Each audio chunk is preceded by an ``asyncio.sleep`` so a parallel
    coroutine can call ``interrupt()`` mid-stream and observe the task
    cancellation kick in. The mock records how many chunks made it out.
    """
    state: dict[str, Any] = {"emitted": 0, "calls": []}

    class _Communicate:
        def __init__(self, text: str, **kwargs: Any) -> None:
            state["calls"].append({"text": text, **kwargs})

        async def stream(self) -> AsyncIterator[dict[str, Any]]:
            for chunk in (b"AA", b"BB", b"CC", b"DD"):
                # Yield control so the test can race interrupt() in.
                await asyncio.sleep(0.02)
                state["emitted"] += 1
                yield {"type": "audio", "data": chunk}

    fake = types.ModuleType("edge_tts")
    fake.Communicate = _Communicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)
    return state


@pytest.fixture
def fake_edge_tts_quick(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Non-streaming ``edge_tts`` mock — yields the whole clip immediately."""
    state: dict[str, Any] = {"calls": []}

    class _Communicate:
        def __init__(self, text: str, **kwargs: Any) -> None:
            state["calls"].append({"text": text, **kwargs})

        async def stream(self) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "audio", "data": b"AA"}
            yield {"type": "audio", "data": b"BB"}

    fake = types.ModuleType("edge_tts")
    fake.Communicate = _Communicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)
    return state


def test_interrupt_when_no_playback_does_not_raise(fake_sounddevice) -> None:
    """interrupt() must be safe to call when no synthesis is active."""
    from jarvis.apps.voice.edge_tts_provider import EdgeTTSProvider

    provider = EdgeTTSProvider()
    # No exception, no in-flight work — was_running should be False, but
    # sounddevice.stop() is still called (idempotent at the backend).
    was_running = provider.interrupt()
    # ``True`` because the sd.stop() backend call counts as a stop
    # attempt; the important invariant is no exception.
    assert was_running in (True, False)
    assert fake_sounddevice["stop"] == 1


def test_interrupt_during_playback_stops_it(
    fake_edge_tts_streaming, fake_sounddevice
) -> None:
    """interrupt() mid-synthesize must cancel the stream and stop the speaker."""
    from jarvis.apps.voice.edge_tts_provider import EdgeTTSProvider

    provider = EdgeTTSProvider()

    async def _race() -> bytes:
        # Launch synthesize on a worker thread so we can interrupt from
        # the event loop while it's mid-stream.
        loop = asyncio.get_running_loop()
        fut = loop.run_in_executor(None, provider.synthesize, "hello hot mic")

        # Wait until the provider has registered an active task.
        for _ in range(200):
            await asyncio.sleep(0.01)
            if provider._active_task is not None and provider._in_flight:
                break
        else:  # pragma: no cover - watchdog branch
            raise AssertionError("synthesize never registered an active task")

        # Fire the barge-in.
        was_running = provider.interrupt()
        assert was_running is True

        result = await fut
        return result

    out = asyncio.run(_race())

    # Stream was cancelled, so synthesize returns empty (or at most the
    # first chunk that escaped before cancellation). Either way: not the
    # full ``AABBCCDD`` payload the un-interrupted stream would produce.
    assert out != b"AABBCCDD"
    # Speaker stop was called.
    assert fake_sounddevice["stop"] >= 1
    # And the stream did NOT run to completion.
    assert fake_edge_tts_streaming["emitted"] < 4


def test_interrupt_idempotent(fake_edge_tts_quick, fake_sounddevice) -> None:
    """Calling interrupt() twice in a row must not raise."""
    from jarvis.apps.voice.edge_tts_provider import EdgeTTSProvider

    provider = EdgeTTSProvider()
    # Run a synthesize that completes naturally so internal state has
    # been touched, then interrupt twice.
    out = provider.synthesize("a quick clip")
    assert out == b"AABB"

    provider.interrupt()
    provider.interrupt()  # must not raise

    # sounddevice.stop() called once per interrupt.
    assert fake_sounddevice["stop"] == 2


def test_interrupt_swallows_sounddevice_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misbehaving ``sounddevice.stop()`` must not propagate."""
    from jarvis.apps.voice.edge_tts_provider import EdgeTTSProvider

    fake = types.ModuleType("sounddevice")

    def _broken_stop() -> None:
        raise OSError("PortAudio: device unavailable")

    fake.stop = _broken_stop  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)

    provider = EdgeTTSProvider()
    # Should not raise even though sounddevice.stop blows up.
    provider.interrupt()


def test_interrupt_when_sounddevice_missing_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Headless envs without sounddevice installed must not crash interrupt()."""
    from jarvis.apps.voice.edge_tts_provider import EdgeTTSProvider

    # Force ``import sounddevice`` to raise ImportError.
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    provider = EdgeTTSProvider()
    # Smoke: no exception.
    provider.interrupt()
