"""Tests for jarvis-desktop MCP server — pyautogui/pygetwindow tool wrappers.

Mocks pyautogui + pygetwindow so tests don't move the real mouse or take real
screenshots.
"""
from __future__ import annotations

import asyncio
import base64
import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from jarvis.tools import desktop_mcp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_gui(monkeypatch):
    """Replace pyautogui + pygetwindow with mocks."""
    pg = MagicMock()
    gw = MagicMock()
    img = Image.new("RGB", (8, 8), color="red")
    pg.screenshot = MagicMock(return_value=img)
    pg.position = MagicMock(return_value=MagicMock(x=10, y=20))
    pg.size = MagicMock(return_value=(1920, 1080))
    monkeypatch.setattr(desktop_mcp, "pyautogui", pg)
    monkeypatch.setattr(desktop_mcp, "gw", gw)
    return pg, gw


def _call(name: str, args: dict):
    """Drive the @server.call_tool() handler synchronously."""
    return asyncio.run(desktop_mcp.call_tool(name, args))


# ---------------------------------------------------------------------------
# list_tools — schema surface
# ---------------------------------------------------------------------------

def test_list_tools_returns_all_13():
    tools = asyncio.run(desktop_mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "desktop_screenshot", "desktop_click", "desktop_double_click",
        "desktop_right_click", "desktop_type", "desktop_press_key",
        "desktop_move_mouse", "desktop_scroll", "desktop_get_mouse_position",
        "desktop_get_screen_size", "desktop_list_windows",
        "desktop_focus_window", "desktop_drag",
    }
    assert names == expected


def test_list_tools_have_input_schema():
    tools = asyncio.run(desktop_mcp.list_tools())
    for t in tools:
        assert isinstance(t.inputSchema, dict)
        assert t.inputSchema.get("type") == "object"


# ---------------------------------------------------------------------------
# screenshot
# ---------------------------------------------------------------------------

def test_screenshot_returns_png_image_and_dims(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_screenshot", {})
    assert len(out) == 2
    img_msg, txt_msg = out
    assert img_msg.type == "image"
    assert img_msg.mimeType == "image/png"
    # Decode b64 → PIL: confirm shape matches mock
    raw = base64.b64decode(img_msg.data)
    decoded = Image.open(io.BytesIO(raw))
    assert decoded.size == (8, 8)
    assert "8x8px" in txt_msg.text


# ---------------------------------------------------------------------------
# Click family
# ---------------------------------------------------------------------------

def test_click_default_left(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_click", {"x": 100, "y": 200})
    pg.click.assert_called_once_with(100, 200, button="left")
    assert "left at (100, 200)" in out[0].text


def test_click_with_button_arg(mock_gui):
    pg, _ = mock_gui
    _call("desktop_click", {"x": 50, "y": 60, "button": "middle"})
    pg.click.assert_called_once_with(50, 60, button="middle")


def test_double_click(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_double_click", {"x": 1, "y": 2})
    pg.doubleClick.assert_called_once_with(1, 2)
    assert "Double-clicked" in out[0].text


def test_right_click(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_right_click", {"x": 3, "y": 4})
    pg.rightClick.assert_called_once_with(3, 4)
    assert "Right-clicked" in out[0].text


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

def test_type_default_interval(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_type", {"text": "hello"})
    pg.write.assert_called_once_with("hello", interval=0.02)
    assert "Typed 5 chars" in out[0].text


def test_type_custom_interval(mock_gui):
    pg, _ = mock_gui
    _call("desktop_type", {"text": "ab", "interval": 0.1})
    pg.write.assert_called_once_with("ab", interval=0.1)


def test_press_single_key(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_press_key", {"key": "enter"})
    pg.press.assert_called_once_with("enter")
    assert "Pressed: enter" in out[0].text


def test_press_hotkey_combo(mock_gui):
    pg, _ = mock_gui
    _call("desktop_press_key", {"key": "ctrl+shift+t"})
    pg.hotkey.assert_called_once_with("ctrl", "shift", "t")


# ---------------------------------------------------------------------------
# Mouse motion + scroll + position queries
# ---------------------------------------------------------------------------

def test_move_mouse(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_move_mouse", {"x": 5, "y": 6})
    pg.moveTo.assert_called_once_with(5, 6, duration=0.1)
    assert "Mouse moved" in out[0].text


def test_move_mouse_custom_duration(mock_gui):
    pg, _ = mock_gui
    _call("desktop_move_mouse", {"x": 5, "y": 6, "duration": 0.5})
    pg.moveTo.assert_called_once_with(5, 6, duration=0.5)


def test_scroll_up(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_scroll", {"x": 1, "y": 2, "clicks": 3})
    pg.scroll.assert_called_once_with(3, x=1, y=2)
    assert "up" in out[0].text


def test_scroll_down(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_scroll", {"x": 1, "y": 2, "clicks": -5})
    pg.scroll.assert_called_once_with(-5, x=1, y=2)
    assert "down" in out[0].text
    assert "5 clicks" in out[0].text


def test_get_mouse_position(mock_gui):
    out = _call("desktop_get_mouse_position", {})
    assert "x=10" in out[0].text and "y=20" in out[0].text


def test_get_screen_size(mock_gui):
    out = _call("desktop_get_screen_size", {})
    assert "width=1920" in out[0].text and "height=1080" in out[0].text


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def test_list_windows_with_titles(mock_gui):
    _, gw = mock_gui
    gw.getAllTitles = MagicMock(return_value=["Notepad", "  ", "Chrome", "Notepad"])
    out = _call("desktop_list_windows", {})
    text = out[0].text
    assert "Windows (3)" in text  # count includes duplicate before dedupe
    assert "Notepad" in text and "Chrome" in text


def test_list_windows_empty(mock_gui):
    _, gw = mock_gui
    gw.getAllTitles = MagicMock(return_value=["", "  "])
    out = _call("desktop_list_windows", {})
    assert "No visible windows" in out[0].text


def test_focus_window_match(mock_gui):
    _, gw = mock_gui
    win = MagicMock()
    win.title = "Visual Studio Code"
    win.activate = MagicMock()
    gw.getAllWindows = MagicMock(return_value=[win])
    out = _call("desktop_focus_window", {"title": "code"})
    win.activate.assert_called_once()
    assert "Focused: Visual Studio Code" in out[0].text


def test_focus_window_no_match(mock_gui):
    _, gw = mock_gui
    gw.getAllWindows = MagicMock(return_value=[])
    out = _call("desktop_focus_window", {"title": "xyz"})
    assert "No window matching" in out[0].text


def test_focus_window_falls_back_to_minimize_restore(mock_gui):
    """activate() raising → fallback path uses minimize+restore."""
    _, gw = mock_gui
    win = MagicMock()
    win.title = "Stuck Window"
    win.activate = MagicMock(side_effect=RuntimeError("denied"))
    win.minimize = MagicMock()
    win.restore = MagicMock()
    gw.getAllWindows = MagicMock(return_value=[win])
    out = _call("desktop_focus_window", {"title": "stuck"})
    win.minimize.assert_called_once()
    win.restore.assert_called_once()
    assert "Focused" in out[0].text


# ---------------------------------------------------------------------------
# Drag
# ---------------------------------------------------------------------------

def test_drag(mock_gui):
    pg, _ = mock_gui
    out = _call("desktop_drag", {
        "start_x": 1, "start_y": 2, "end_x": 100, "end_y": 200,
    })
    pg.moveTo.assert_called_once_with(1, 2)
    pg.dragTo.assert_called_once_with(100, 200, duration=0.5, button="left")
    assert "(1,2)" in out[0].text and "(100,200)" in out[0].text


def test_drag_custom_duration(mock_gui):
    pg, _ = mock_gui
    _call("desktop_drag", {
        "start_x": 0, "start_y": 0, "end_x": 50, "end_y": 50, "duration": 1.0,
    })
    pg.dragTo.assert_called_once_with(50, 50, duration=1.0, button="left")


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_unknown_tool_returns_error(mock_gui):
    out = _call("desktop_quantum_teleport", {})
    assert "Unknown tool" in out[0].text


def test_pyautogui_exception_captured_as_error(mock_gui):
    pg, _ = mock_gui
    pg.click = MagicMock(side_effect=RuntimeError("display offline"))
    out = _call("desktop_click", {"x": 1, "y": 1})
    assert out[0].text.startswith("ERROR:")
    assert "display offline" in out[0].text
