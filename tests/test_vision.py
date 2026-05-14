"""Vision pipeline tests — phrase detection, screenshot helper, chat slash.

Mocks ``pyautogui.screenshot`` and ``jarvis.llm.queue.submit_multimodal`` so
the suite never actually captures the desktop or makes a network call.
"""
from __future__ import annotations

import base64
import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jarvis.apps.voice import cheap_handler
from jarvis.tools import screen


# ─── J6.1 — capture_screen / image_content_block ──────────────────────────────


class _StubImage:
    """Minimal PIL.Image stand-in supporting .save() and .resize()."""

    def __init__(self, size: tuple[int, int] = (10, 8), payload: bytes = b"PNGDATA"):
        self.size = size
        self._payload = payload

    def save(self, buf: io.BytesIO, format: str = "PNG", **_: Any) -> None:
        assert format == "PNG"
        buf.write(self._payload)

    def resize(self, new_size: tuple[int, int]) -> "_StubImage":
        return _StubImage(size=new_size, payload=self._payload)


def test_capture_screen_returns_png_bytes_and_media_type() -> None:
    fake_pyautogui = MagicMock()
    fake_pyautogui.screenshot.return_value = _StubImage()
    with patch.dict("sys.modules", {"pyautogui": fake_pyautogui}):
        raw, media_type = screen.capture_screen()
    assert raw == b"PNGDATA"
    assert media_type == "image/png"
    fake_pyautogui.screenshot.assert_called_once()


def test_capture_screen_raises_when_pyautogui_missing() -> None:
    with patch.dict("sys.modules", {"pyautogui": None}):  # type: ignore[arg-type]
        with pytest.raises(screen.ScreenCaptureError):
            screen.capture_screen()


def test_image_content_block_shape() -> None:
    block = screen.image_content_block(b"hello", "image/png")
    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/png"
    assert block["source"]["data"] == base64.b64encode(b"hello").decode("ascii")


def test_capture_and_block_round_trip() -> None:
    fake_pyautogui = MagicMock()
    fake_pyautogui.screenshot.return_value = _StubImage()
    with patch.dict("sys.modules", {"pyautogui": fake_pyautogui}):
        block = screen.capture_and_block()
    assert block["type"] == "image"
    assert block["source"]["data"] == base64.b64encode(b"PNGDATA").decode("ascii")


# ─── J6.2 — voice phrase detection ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        "look at my screen",
        "what's on my screen",
        "what is on my screen",
        "what do you see",
        "take a screenshot",
        "grab a screenshot",
        "read this for me",
        "see this",
        "describe my screen",
        "check my screen",
    ],
)
def test_wants_screen_vision_positive(phrase: str) -> None:
    assert cheap_handler.wants_screen_vision(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        "",
        "what's my schedule today",
        "send an email to my professor",
        "the screen flickered last night",  # mentions "screen" but no action verb
        "draft a reply",
        "atlas portfolio",
    ],
)
def test_wants_screen_vision_negative(phrase: str) -> None:
    assert not cheap_handler.wants_screen_vision(phrase), phrase
