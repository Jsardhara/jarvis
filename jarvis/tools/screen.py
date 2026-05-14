"""Screen capture helper — wraps pyautogui for in-process screenshot use.

Used by the voice loop, chat brain, and the dashboard API endpoint to feed
the operator's screen contents into Claude vision calls. Distinct from
``jarvis/tools/desktop_mcp.py`` (which exposes the same capability via the
MCP protocol for SDK tool-use) so we can capture from inside the Python
process without spawning an MCP subprocess.

Usage:

    from jarvis.tools.screen import capture_screen, image_content_block

    png_bytes, media_type = capture_screen()
    block = image_content_block(png_bytes, media_type)
    # then pass `[block, {"type": "text", "text": "..."}]` to
    # `jarvis.llm.queue.submit_multimodal`.

Failure semantics: ``capture_screen`` raises ``ScreenCaptureError`` on any
underlying error (pyautogui unavailable, PIL missing, etc.). Callers are
expected to catch and degrade to a text-only response — never let a
screenshot failure crash the chat path.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

log = logging.getLogger(__name__)

# Anthropic image content blocks are limited to ~5 MB after base64 encoding.
# A full 4K desktop screenshot at PNG quality usually lands around 1–3 MB.
# We cap raw size at 4 MB before encoding to leave headroom; downscale if over.
_MAX_RAW_BYTES = 4 * 1024 * 1024
_PNG_MEDIA_TYPE = "image/png"


class ScreenCaptureError(RuntimeError):
    """Raised when a screenshot cannot be produced (pyautogui/PIL missing, etc.)."""


def capture_screen() -> tuple[bytes, str]:
    """Capture the full primary-monitor screen as PNG bytes.

    Returns ``(png_bytes, media_type)`` where ``media_type`` is the string
    Anthropic expects in the ``source.media_type`` field of an image block.

    Raises:
        ScreenCaptureError: when pyautogui / PIL is unavailable or capture
            fails for any reason. The original exception is chained.
    """
    try:
        import pyautogui  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — runtime missing dep
        raise ScreenCaptureError(
            "pyautogui not installed — screen capture unavailable"
        ) from exc

    try:
        image = pyautogui.screenshot()
    except Exception as exc:  # noqa: BLE001 — pyautogui can raise pillow / X / etc.
        raise ScreenCaptureError(f"screenshot failed: {exc}") from exc

    try:
        buf = io.BytesIO()
        # PNG keeps text crisp; JPEG saves bandwidth at the cost of OCR fidelity.
        # The vision pipeline benefits more from PNG sharpness on UI captures.
        image.save(buf, format="PNG", optimize=True)
        raw = buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        raise ScreenCaptureError(f"png encode failed: {exc}") from exc

    if len(raw) > _MAX_RAW_BYTES:
        raw = _downscale_until_under(image, _MAX_RAW_BYTES)

    return raw, _PNG_MEDIA_TYPE


def _downscale_until_under(image: Any, max_bytes: int) -> bytes:
    """Iteratively halve image dimensions until PNG bytes fit under ``max_bytes``.

    Falls back to the smallest attempt even if still over budget — the model
    will accept it; Anthropic just may reject if truly enormous. We make a
    best-effort.
    """
    width, height = image.size
    for divisor in (2, 4, 8):
        new_size = (max(1, width // divisor), max(1, height // divisor))
        resized = image.resize(new_size)
        buf = io.BytesIO()
        resized.save(buf, format="PNG", optimize=True)
        out = buf.getvalue()
        if len(out) <= max_bytes:
            return out
    return out  # smallest attempt; caller deals with size if rejected


def image_content_block(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    """Build an Anthropic image content block from raw bytes.

    Mirrors the helper in ``agents/lens/link_handler.py`` but lives in a
    runtime-shared location so voice + chat + API all reuse one shape.
    """
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(image_bytes).decode("ascii"),
        },
    }


def capture_and_block() -> dict[str, Any]:
    """One-shot: capture the screen and return an Anthropic content block.

    Convenience wrapper for the common case where the caller doesn't need
    the raw bytes separately. Raises ``ScreenCaptureError`` on failure.
    """
    raw, media_type = capture_screen()
    return image_content_block(raw, media_type)


__all__ = [
    "ScreenCaptureError",
    "capture_and_block",
    "capture_screen",
    "image_content_block",
]
