# J6 — Vision / Multimodal Awareness

**Date:** 2026-05-14
**Audit finding:** The vision foundation already existed (link_handler.py for URL images, llm/queue.submit_multimodal, tools/desktop_mcp.py screenshot). What was missing was the integration into voice and chat surfaces, plus a frontend image upload.

This pass closes that gap.

---

## What landed

### J6.1 — `jarvis/tools/screen.py` (new module)
- `capture_screen() -> (bytes, media_type)` — wraps pyautogui in-process (vs the MCP subprocess in desktop_mcp.py).
- `image_content_block(bytes, media_type)` — builds Anthropic image content block.
- `capture_and_block()` — one-shot convenience wrapper.
- `ScreenCaptureError` for graceful degradation.
- Auto-downscales >4 MB raw to stay under Anthropic's image budget.

### J6.2 — Voice screen-vision (`cheap_handler.py`)
- 6 regex phrase patterns: "look at my screen", "what's on my screen", "what do you see", "take a screenshot", "read this for me", "see this".
- Public `wants_screen_vision(text)` helper.
- `_screen_vision_response(text)`: captures screen, submits multimodal to Sonnet via `submit_multimodal` with a dedicated `_SCREEN_VISION_SYSTEM` prompt. Falls back cleanly on capture or LLM failure — never crashes voice.
- Wired into `handle()` between link_handler and Tier 0 routing.

### J6.3 — Chat screen-vision (`agent.py`)
- `stream()` short-circuits on `/screen` slash OR `wants_screen_vision` match. Same regex as voice — single source of truth.
- New `_stream_via_screen_vision(message, surface, session_id)` mirrors `_stream_via_link_handler`: emits model badge, runs capture+multimodal in executor thread, emits text+done events, records turn through standard pathways.
- Slash prefix stripped; empty question defaults to "What's on my screen right now?"

### J6.4 — Dashboard image upload
- `useChatTurns.ChatImage` type + `send(text, image?)` signature extension.
- `CommandPanel.tsx` adds:
  - **Paste from clipboard** — window-level paste handler captures image data.
  - **Drag-and-drop** — dashed cyan outline appears on hover; drop captures.
  - **File picker** — IMG button opens a hidden `<input type="file">`.
  - **Attached chip** — small cyan strip above composer with X button to clear.
  - Composer placeholder switches to "Optional question..." when image staged.
  - Send button enables on image-only (no text needed).
- `jarvis/apps/api/app.py:/api/jarvis/chat` accepts `image_b64` + `image_media_type` in payload; routes to new `JarvisChat.stream_with_image()` when present.
- `JarvisChat.stream_with_image()` mirrors `_stream_via_screen_vision` but uses the user-supplied image instead of capturing the desktop.

### J6.5 — Tests (`tests/test_vision.py`)
- 4 screen helper tests (capture, missing-pyautogui error, block shape, capture-and-block).
- 10 phrase-detection tests (5 positive, 5 negative — including the trap "the screen flickered last night" which mentions "screen" but should not trigger).
- All tests use mock pyautogui — no real screen capture in CI.

---

## Try it

### From voice
Say any of:
- "Jarvis, look at my screen."
- "What's on my screen?"
- "Read this for me."
- "What do you see?"

### From the dashboard chat (CommandPanel)
- **Paste:** copy any image (Win+Shift+S or Ctrl+PrtSc on Windows), focus the chat panel, Ctrl+V.
- **Drag-drop:** drag an image file from File Explorer onto the chat panel — dashed cyan outline confirms.
- **File pick:** click the IMG button (next to DONE / MIC).
- **Slash command:** type `/screen` (or `/screen what code is wrong here`) and hit Enter — captures your screen and asks Sonnet.

### From the API directly
```bash
curl -X POST http://localhost:8765/api/jarvis/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "what is wrong with this code",
    "image_b64": "<base64>",
    "image_media_type": "image/png"
  }'
```

---

## Verify

```powershell
cd C:\Users\jyot2\jarvis

# Run the new test file:
pytest tests\test_vision.py -v

# Full suite + ruff + tsc + build:
pytest --cov=jarvis --cov-fail-under=70
ruff check jarvis\
cd web
pnpm tsc --noEmit
pnpm build
```

Expected: 14 new tests pass. Total test count goes 1047 → 1061.

---

## Commit message

```
jarvis-vision: voice + chat + dashboard see what you see

- J6.1: jarvis/tools/screen.py — in-process screen capture helper +
  Anthropic image content block builder. Auto-downscales >4MB.
- J6.2: voice phrase detection ("look at my screen" / "what do you see"
  / "take a screenshot" / "read this for me") triggers
  _screen_vision_response which captures + submits multimodal to Sonnet.
- J6.3: chat stream() short-circuits on /screen slash OR same phrase
  detector; new _stream_via_screen_vision mirrors link_handler pattern.
  stream_with_image() handles operator-supplied images.
- J6.4: CommandPanel adds paste/drag-drop/file-picker for images,
  staged attachment chip, send-on-image-alone. useChatTurns.send accepts
  optional ChatImage and forwards image_b64+image_media_type to FastAPI.
  /api/jarvis/chat routes payload.image_b64 to stream_with_image.
- J6.5: 14 new tests (screen helper + phrase detection coverage).

See docs/VISION_LANDED_2026-05-14.md.
```

---

## What this unlocks

- **"What's wrong with this code"** → Jarvis sees your editor, points to the bug.
- **"What does this dashboard mean"** → Jarvis reads the chart.
- **"Read this for me"** → Jarvis OCR-equivalents the PDF page you have open.
- **Drag a screenshot into chat** → ask anything about it.
- **Paste a Slack message screenshot** → "draft a reply to this."

Together with the prior J2-J5 passes (memory, proactivity, persona, routing), Jarvis now:

- Remembers what you said across sessions.
- Surfaces high-value events proactively.
- Sounds consistent and witty across all surfaces.
- Routes compound requests correctly.
- **And now: sees what you see.**
