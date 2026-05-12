"""Link handler — ingest URLs and answer questions about them.

Supported surfaces:

* **video** (YouTube, Instagram, TikTok, X/Twitter, generic mp4) —
  ``yt-dlp`` downloads the source, ffmpeg samples evenly-spaced
  keyframes, vision pass on Sonnet summarizes content + answers any
  follow-up question in the user's message.
* **image** (jpg/png/gif/webp) — direct vision pass.
* **pdf** — anthropic document block.
* **audio** (mp3/wav/m4a/ogg) — yt-dlp/ffmpeg → faster-whisper transcribe →
  text summary.
* **article / generic page** — fetched HTML, stripped to readable text,
  Sonnet summary + question answer.

Returns the standard subsystem envelope:

    {agent, intent, action, result, follow_ups, confidence, needs_confirm}

Designed to be cheap to test:

* All network I/O isolated behind ``_fetch_*`` helpers (mockable).
* yt-dlp and ffmpeg invocations isolated behind ``_run_yt_dlp`` and
  ``_extract_keyframes`` helpers.
* Claude calls go through ``claude_queue.submit`` and
  ``claude_queue.submit_multimodal`` (already mocked by test_cheap_handler
  fixtures).
"""
from __future__ import annotations

import base64
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from jarvis.llm import queue as claude_queue

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / model routing
# ---------------------------------------------------------------------------

DEFAULT_VISION_MODEL = "claude-sonnet-4-6"
DEFAULT_TEXT_MODEL = "claude-sonnet-4-6"
KEYFRAMES_PER_VIDEO = 8
MAX_FRAME_EDGE_PX = 1024
MAX_TOKENS_REPLY = 768
HTTP_TIMEOUT_SEC = 30.0
ARTICLE_MAX_CHARS = 12_000

# yt-dlp recognises these hosts natively.
VIDEO_HOSTS = (
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    "twitter.com", "x.com", "vimeo.com", "facebook.com", "fb.watch",
    "reddit.com", "v.redd.it",
)

VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv", ".avi")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")
PDF_EXTS = (".pdf",)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkResponse:
    """Subsystem-contract envelope."""

    agent: str = "link"
    intent: str = "ingest_url"
    action: str = "summarized"
    result: dict[str, Any] = field(default_factory=dict)
    follow_ups: list[str] = field(default_factory=list)
    confidence: float = 0.85
    needs_confirm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "intent": self.intent,
            "action": self.action,
            "result": self.result,
            "follow_ups": self.follow_ups,
            "confidence": self.confidence,
            "needs_confirm": self.needs_confirm,
        }


_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def extract_urls(text: str) -> list[str]:
    """Pull every http(s) URL from free-form text. Order preserved, deduped."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.findall(text or ""):
        u = m.rstrip(".,;:!?)]}>'\"")
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def classify(url: str) -> str:
    """Return one of: video | image | pdf | audio | article."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().lstrip("www.")
    path = (parsed.path or "").lower()

    if any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
        return "video"
    if path.endswith(VIDEO_EXTS):
        return "video"
    if path.endswith(IMAGE_EXTS):
        return "image"
    if path.endswith(AUDIO_EXTS):
        return "audio"
    if path.endswith(PDF_EXTS):
        return "pdf"
    return "article"


def handle(text: str) -> LinkResponse:
    """Top-level entry — finds URL in ``text``, dispatches, returns envelope.

    ``text`` is the operator's full message (e.g. "what is this?
    https://...instagram.com/reel/..."). Question portion is preserved
    and passed to the Claude prompt so the answer is targeted.
    """
    urls = extract_urls(text)
    if not urls:
        return LinkResponse(
            action="no_url",
            confidence=0.0,
            result={"message": "no URL in input"},
        )
    url = urls[0]
    question = _strip_url(text, url)
    kind = classify(url)
    log.info("link_handler: kind=%s url=%s", kind, url)

    try:
        if kind == "video":
            summary = _handle_video(url, question)
        elif kind == "image":
            summary = _handle_image(url, question)
        elif kind == "pdf":
            summary = _handle_pdf(url, question)
        elif kind == "audio":
            summary = _handle_audio(url, question)
        else:
            summary = _handle_article(url, question)
    except Exception as exc:  # noqa: BLE001
        log.exception("link_handler: %s failed", kind)
        return LinkResponse(
            action="failed",
            confidence=0.2,
            result={"url": url, "kind": kind, "error": f"{type(exc).__name__}: {exc}"},
        )

    return LinkResponse(
        action="summarized",
        result={"url": url, "kind": kind, "summary": summary},
        follow_ups=_follow_ups_for(kind),
    )


# ---------------------------------------------------------------------------
# Handlers — one per kind
# ---------------------------------------------------------------------------


def _handle_article(url: str, question: str) -> str:
    text = _fetch_article_text(url)
    if not text:
        raise RuntimeError("empty page body")
    user_msg = (
        f"URL: {url}\n\n"
        f"Page text (truncated to {ARTICLE_MAX_CHARS} chars):\n---\n"
        f"{text[:ARTICLE_MAX_CHARS]}\n---\n\n"
        f"Operator question: {question or 'Summarize this page in 4-6 sentences.'}"
    )
    return claude_queue.submit(
        system=_TEXT_SYSTEM,
        user=user_msg,
        model=DEFAULT_TEXT_MODEL,
    )


def _handle_image(url: str, question: str) -> str:
    raw = _fetch_bytes(url)
    media_type = _guess_image_media_type(url)
    block = _image_block(raw, media_type)
    return claude_queue.submit_multimodal(
        system=_VISION_SYSTEM,
        content=[
            block,
            {"type": "text", "text": question or "Describe what's in this image."},
        ],
        model=DEFAULT_VISION_MODEL,
        max_tokens=MAX_TOKENS_REPLY,
    )


def _handle_pdf(url: str, question: str) -> str:
    raw = _fetch_bytes(url)
    block = {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.b64encode(raw).decode("ascii"),
        },
    }
    return claude_queue.submit_multimodal(
        system=_TEXT_SYSTEM,
        content=[
            block,
            {
                "type": "text",
                "text": question or "Summarize this PDF in 4-6 sentences.",
            },
        ],
        model=DEFAULT_TEXT_MODEL,
        max_tokens=MAX_TOKENS_REPLY,
    )


def _handle_video(url: str, question: str) -> str:
    with tempfile.TemporaryDirectory(prefix="jarvis_link_") as tmp:
        video_path = _run_yt_dlp(url, Path(tmp))
        frames = _extract_keyframes(video_path, count=KEYFRAMES_PER_VIDEO)
    if not frames:
        raise RuntimeError("no keyframes extracted")

    blocks: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Video URL: {url}\n"
                f"Below are {len(frames)} evenly-spaced keyframes from the video. "
                f"Use them together to understand what's happening."
            ),
        },
    ]
    for raw in frames:
        blocks.append(_image_block(raw, "image/jpeg"))
    blocks.append(
        {
            "type": "text",
            "text": question
            or "Describe what's happening in this video in 4-6 sentences.",
        }
    )

    return claude_queue.submit_multimodal(
        system=_VISION_SYSTEM,
        content=blocks,
        model=DEFAULT_VISION_MODEL,
        max_tokens=MAX_TOKENS_REPLY,
    )


def _handle_audio(url: str, question: str) -> str:
    """Transcribe audio via faster-whisper, then summarize the transcript."""
    with tempfile.TemporaryDirectory(prefix="jarvis_link_") as tmp:
        audio_path = _run_yt_dlp(url, Path(tmp), audio_only=True)
        transcript = _transcribe_audio(audio_path)
    if not transcript.strip():
        raise RuntimeError("empty transcript")

    user_msg = (
        f"Audio URL: {url}\n\n"
        f"Transcript:\n---\n{transcript[:ARTICLE_MAX_CHARS]}\n---\n\n"
        f"Operator question: {question or 'Summarize this audio in 4-6 sentences.'}"
    )
    return claude_queue.submit(
        system=_TEXT_SYSTEM,
        user=user_msg,
        model=DEFAULT_TEXT_MODEL,
    )


# ---------------------------------------------------------------------------
# Helpers — fetching, ffmpeg, encoding
# ---------------------------------------------------------------------------


def _strip_url(text: str, url: str) -> str:
    """Return text with the URL removed, used as the operator question."""
    return (text or "").replace(url, "").strip()


def _follow_ups_for(kind: str) -> list[str]:
    if kind == "video":
        return ["want me to pull a transcript instead?"]
    if kind == "article":
        return ["want the key takeaways extracted?"]
    return []


def _fetch_bytes(url: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=HTTP_TIMEOUT_SEC) as cx:
        r = cx.get(url, headers={"User-Agent": "Mozilla/5.0 (jarvis-link)"})
        r.raise_for_status()
        return r.content


def _fetch_article_text(url: str) -> str:
    """GET the URL, strip HTML to readable text via a tiny regex pass."""
    raw = _fetch_bytes(url).decode("utf-8", errors="replace")
    # Strip script/style blocks.
    raw = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", raw, flags=re.IGNORECASE)
    # Strip all other tags.
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Collapse whitespace.
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _guess_image_media_type(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".gif"):
        return "image/gif"
    if path.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _image_block(raw: bytes, media_type: str) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(raw).decode("ascii"),
        },
    }


def _run_yt_dlp(url: str, out_dir: Path, *, audio_only: bool = False) -> Path:
    """Download video (or audio-only) into ``out_dir`` and return the file path.

    Uses the bundled ffmpeg from ``imageio_ffmpeg`` so no system install is
    required. Caps download size to keep things sane.
    """
    import imageio_ffmpeg
    import yt_dlp

    ffmpeg_loc = imageio_ffmpeg.get_ffmpeg_exe()
    out_template = str(out_dir / "media.%(ext)s")
    opts: dict[str, Any] = {
        "outtmpl": out_template,
        "quiet": True,
        "noprogress": True,
        "ffmpeg_location": ffmpeg_loc,
        "max_filesize": 200 * 1024 * 1024,  # 200 MB ceiling
    }
    if audio_only:
        opts["format"] = "bestaudio/best"
    else:
        # Prefer mp4 H.264 + small height so vision frames stay reasonable.
        opts["format"] = "best[height<=720]/best"

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Resolve actual filename (yt-dlp picks the extension).
        path = Path(ydl.prepare_filename(info))
        if not path.exists():
            # Some extractors pick a different extension after post-process.
            for child in out_dir.iterdir():
                if child.is_file():
                    return child
            raise RuntimeError(f"yt-dlp downloaded but file missing at {path}")
        return path


def _extract_keyframes(video_path: Path, *, count: int = 8) -> list[bytes]:
    """Sample ``count`` evenly-spaced JPEG frames from the video.

    Uses ffmpeg's ``select=not(mod(n\\,...))`` filter via a single subprocess
    call. Returns raw JPEG bytes for each frame, sorted by time.
    """
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if shutil.which(ffmpeg) is None and not Path(ffmpeg).exists():
        raise RuntimeError(f"ffmpeg not found at {ffmpeg}")

    duration = _probe_duration_sec(video_path)
    if duration <= 0:
        raise RuntimeError("video duration unknown / zero")

    interval = duration / max(1, count)
    frames: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="jarvis_frames_") as fd:
        out_pattern = str(Path(fd) / "frame_%03d.jpg")
        # Single ffmpeg pass: take 1 frame per `interval` seconds, scale to fit.
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-i", str(video_path),
            "-vf", f"fps=1/{interval:.4f},scale='min({MAX_FRAME_EDGE_PX},iw)':-2",
            "-frames:v", str(count),
            "-q:v", "4",
            out_pattern,
        ]
        result = subprocess.run(cmd, capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg keyframe extraction failed: "
                f"{result.stderr.decode('utf-8', errors='ignore')[:300]}"
            )
        for p in sorted(Path(fd).iterdir()):
            if p.suffix.lower() == ".jpg":
                frames.append(p.read_bytes())
    return frames


def _probe_duration_sec(video_path: Path) -> float:
    """Return video duration via ffmpeg -i parsing (no ffprobe needed)."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-i", str(video_path)]
    result = subprocess.run(cmd, capture_output=True, check=False)
    err = result.stderr.decode("utf-8", errors="ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not m:
        return 0.0
    h, mm, ss = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mm * 60 + ss


def _transcribe_audio(audio_path: Path) -> str:
    """faster-whisper transcribe (CPU). Optional dep — caller catches ImportError."""
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper not installed — pip install -e '.[voice]'"
        ) from exc

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(audio_path), beam_size=1)
    return " ".join(seg.text.strip() for seg in segments).strip()


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_VISION_SYSTEM = (
    "You are Jarvis — terse personal assistant. The operator just sent a "
    "link with media in it. Look at the supplied image(s) carefully and "
    "answer the operator's question, or summarize what's there if no "
    "specific question was asked. Plain prose, 4-6 sentences max, no "
    "markdown, no bullet lists, no preamble like 'I see' or 'this image "
    "shows'. Just describe what matters."
)

_TEXT_SYSTEM = (
    "You are Jarvis — terse personal assistant. The operator just sent a "
    "link with text content. Answer the operator's question or summarize "
    "the content. Plain prose, 4-6 sentences max, no markdown, no preamble."
)
