#!/usr/bin/env python
"""Jarvis Desktop MCP Server.

Exposes Windows desktop GUI control as MCP tools:
  desktop_screenshot, desktop_click, desktop_double_click,
  desktop_right_click, desktop_type, desktop_press_key,
  desktop_move_mouse, desktop_scroll, desktop_get_mouse_position,
  desktop_get_screen_size, desktop_list_windows, desktop_focus_window,
  desktop_drag

Run via stdio (registered in ~/.claude.json mcpServers).
"""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Sequence
from typing import Any

import pyautogui
import pygetwindow as gw
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Safety config
pyautogui.PAUSE = 0.05       # small delay between actions
pyautogui.FAILSAFE = True    # move mouse to top-left corner to abort

server = Server("jarvis-desktop")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="desktop_screenshot",
            description=(
                "Capture a screenshot of the full desktop. "
                "Returns a base64-encoded PNG image."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="desktop_click",
            description="Click at screen coordinates (x, y).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X pixel coordinate"},
                    "y": {"type": "integer", "description": "Y pixel coordinate"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left",
                    },
                },
                "required": ["x", "y"],
            },
        ),
        types.Tool(
            name="desktop_double_click",
            description="Double-click at screen coordinates (x, y).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        ),
        types.Tool(
            name="desktop_right_click",
            description="Right-click at screen coordinates (x, y).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        ),
        types.Tool(
            name="desktop_type",
            description="Type text at the current cursor/focus position.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "interval": {
                        "type": "number",
                        "description": "Seconds between keystrokes (default 0.02)",
                        "default": 0.02,
                    },
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="desktop_press_key",
            description=(
                "Press a key or key combination. "
                "Examples: 'enter', 'ctrl+c', 'alt+f4', 'win', 'ctrl+shift+t'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key name or hotkey string (use + for combos)",
                    },
                },
                "required": ["key"],
            },
        ),
        types.Tool(
            name="desktop_move_mouse",
            description="Move mouse cursor to (x, y) without clicking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {
                        "type": "number",
                        "description": "Seconds to animate the move (default 0.1)",
                        "default": 0.1,
                    },
                },
                "required": ["x", "y"],
            },
        ),
        types.Tool(
            name="desktop_scroll",
            description=(
                "Scroll at coordinates (x, y). "
                "Positive clicks = up, negative = down."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "clicks": {
                        "type": "integer",
                        "description": "Scroll amount (negative = down)",
                    },
                },
                "required": ["x", "y", "clicks"],
            },
        ),
        types.Tool(
            name="desktop_get_mouse_position",
            description="Return current mouse cursor position as {x, y}.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="desktop_get_screen_size",
            description="Return screen resolution as {width, height}.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="desktop_list_windows",
            description="List all visible window titles.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="desktop_focus_window",
            description=(
                "Bring a window to the foreground by partial title match. "
                "Case-insensitive."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Partial window title to match (case-insensitive)",
                    },
                },
                "required": ["title"],
            },
        ),
        types.Tool(
            name="desktop_drag",
            description="Click-drag from one point to another.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer"},
                    "start_y": {"type": "integer"},
                    "end_x": {"type": "integer"},
                    "end_y": {"type": "integer"},
                    "duration": {
                        "type": "number",
                        "description": "Drag animation duration in seconds (default 0.5)",
                        "default": 0.5,
                    },
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(
    name: str, arguments: dict[str, Any]
) -> Sequence[types.TextContent | types.ImageContent]:
    try:
        if name == "desktop_screenshot":
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            w, h = img.size
            return [
                types.ImageContent(type="image", data=b64, mimeType="image/png"),
                types.TextContent(type="text", text=f"Screenshot captured: {w}x{h}px"),
            ]

        elif name == "desktop_click":
            x, y = arguments["x"], arguments["y"]
            button = arguments.get("button", "left")
            pyautogui.click(x, y, button=button)
            return [types.TextContent(type="text", text=f"Clicked {button} at ({x}, {y})")]

        elif name == "desktop_double_click":
            x, y = arguments["x"], arguments["y"]
            pyautogui.doubleClick(x, y)
            return [types.TextContent(type="text", text=f"Double-clicked at ({x}, {y})")]

        elif name == "desktop_right_click":
            x, y = arguments["x"], arguments["y"]
            pyautogui.rightClick(x, y)
            return [types.TextContent(type="text", text=f"Right-clicked at ({x}, {y})")]

        elif name == "desktop_type":
            text = arguments["text"]
            interval = float(arguments.get("interval", 0.02))
            pyautogui.write(text, interval=interval)
            return [types.TextContent(type="text", text=f"Typed {len(text)} chars")]

        elif name == "desktop_press_key":
            key = arguments["key"]
            if "+" in key:
                parts = [p.strip() for p in key.split("+")]
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(key)
            return [types.TextContent(type="text", text=f"Pressed: {key}")]

        elif name == "desktop_move_mouse":
            x, y = arguments["x"], arguments["y"]
            duration = float(arguments.get("duration", 0.1))
            pyautogui.moveTo(x, y, duration=duration)
            return [types.TextContent(type="text", text=f"Mouse moved to ({x}, {y})")]

        elif name == "desktop_scroll":
            x, y, clicks = arguments["x"], arguments["y"], arguments["clicks"]
            pyautogui.scroll(clicks, x=x, y=y)
            direction = "up" if clicks > 0 else "down"
            return [
                types.TextContent(
                    type="text",
                    text=f"Scrolled {abs(clicks)} clicks {direction} at ({x}, {y})",
                )
            ]

        elif name == "desktop_get_mouse_position":
            pos = pyautogui.position()
            return [types.TextContent(type="text", text=f"x={pos.x}, y={pos.y}")]

        elif name == "desktop_get_screen_size":
            w, h = pyautogui.size()
            return [types.TextContent(type="text", text=f"width={w}, height={h}")]

        elif name == "desktop_list_windows":
            titles = [t for t in gw.getAllTitles() if t.strip()]
            if not titles:
                return [types.TextContent(type="text", text="No visible windows found")]
            lines = "\n".join(f"  - {t}" for t in sorted(set(titles)))
            return [types.TextContent(type="text", text=f"Windows ({len(titles)}):\n{lines}")]

        elif name == "desktop_focus_window":
            query = arguments["title"].lower()
            windows = gw.getAllWindows()
            matches = [w for w in windows if query in w.title.lower() and w.title.strip()]
            if not matches:
                return [
                    types.TextContent(type="text", text=f"No window matching '{query}'")
                ]
            win = matches[0]
            try:
                win.activate()
            except Exception:
                win.minimize()
                win.restore()
            return [types.TextContent(type="text", text=f"Focused: {win.title}")]

        elif name == "desktop_drag":
            sx, sy = arguments["start_x"], arguments["start_y"]
            ex, ey = arguments["end_x"], arguments["end_y"]
            duration = float(arguments.get("duration", 0.5))
            pyautogui.moveTo(sx, sy)
            pyautogui.dragTo(ex, ey, duration=duration, button="left")
            return [
                types.TextContent(
                    type="text", text=f"Dragged ({sx},{sy}) → ({ex},{ey})"
                )
            ]

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as exc:
        return [types.TextContent(type="text", text=f"ERROR: {exc}")]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
