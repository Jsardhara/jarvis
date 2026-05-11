"""Tests for link_handler — URL detection, classification, dispatch."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.subsystems import link_handler


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------


def test_extract_urls_finds_http_and_https():
    out = link_handler.extract_urls("see http://a.com and https://b.com/x?y=1")
    assert out == ["http://a.com", "https://b.com/x?y=1"]


def test_extract_urls_strips_trailing_punctuation():
    out = link_handler.extract_urls("look at https://x.com/post.")
    assert out == ["https://x.com/post"]


def test_extract_urls_dedupes():
    out = link_handler.extract_urls("https://a.com and https://a.com")
    assert out == ["https://a.com"]


def test_extract_urls_empty_string():
    assert link_handler.extract_urls("") == []
    assert link_handler.extract_urls(None) == []  # type: ignore[arg-type]


def test_extract_urls_no_match():
    assert link_handler.extract_urls("just plain text, no link") == []


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,kind",
    [
        ("https://www.instagram.com/reel/abc123", "video"),
        ("https://youtu.be/dQw4w9WgXcQ", "video"),
        ("https://www.youtube.com/watch?v=abc", "video"),
        ("https://tiktok.com/@user/video/1", "video"),
        ("https://x.com/user/status/1", "video"),
        ("https://twitter.com/x/status/1", "video"),
        ("https://vimeo.com/123", "video"),
        ("https://example.com/clip.mp4", "video"),
        ("https://example.com/image.jpg", "image"),
        ("https://example.com/foo.PNG", "image"),
        ("https://example.com/anim.gif", "image"),
        ("https://example.com/doc.pdf", "pdf"),
        ("https://example.com/song.mp3", "audio"),
        ("https://example.com/track.m4a", "audio"),
        ("https://nytimes.com/article", "article"),
        ("https://example.com/", "article"),
    ],
)
def test_classify(url, kind):
    assert link_handler.classify(url) == kind


# ---------------------------------------------------------------------------
# LinkResponse envelope
# ---------------------------------------------------------------------------


def test_response_to_dict_default():
    r = link_handler.LinkResponse(result={"summary": "ok"})
    d = r.to_dict()
    assert d["agent"] == "link"
    assert d["result"]["summary"] == "ok"
    assert d["needs_confirm"] is False


# ---------------------------------------------------------------------------
# handle() — no URL path
# ---------------------------------------------------------------------------


def test_handle_no_url_returns_no_url_action():
    r = link_handler.handle("hello there, no link")
    assert r.action == "no_url"
    assert r.confidence == 0.0


# ---------------------------------------------------------------------------
# handle() — article path (mocked WebFetch + Claude)
# ---------------------------------------------------------------------------


def test_handle_article_dispatches_to_text_model(monkeypatch):
    monkeypatch.setattr(
        link_handler,
        "_fetch_article_text",
        lambda url: "the page body text here",
    )

    submitted = {}

    def fake_submit(*, system, user, model):
        submitted.update({"system": system, "user": user, "model": model})
        return "article summary"

    monkeypatch.setattr(link_handler.claude_queue, "submit", fake_submit)

    r = link_handler.handle("explain this https://example.com/article")
    assert r.action == "summarized"
    assert r.result["kind"] == "article"
    assert r.result["summary"] == "article summary"
    assert "explain this" in submitted["user"]
    assert "the page body text" in submitted["user"]


def test_handle_article_empty_body_failed(monkeypatch):
    monkeypatch.setattr(link_handler, "_fetch_article_text", lambda url: "")
    r = link_handler.handle("https://example.com/article")
    assert r.action == "failed"
    assert "empty page body" in r.result["error"]


# ---------------------------------------------------------------------------
# handle() — image path
# ---------------------------------------------------------------------------


def test_handle_image_sends_image_block(monkeypatch):
    monkeypatch.setattr(link_handler, "_fetch_bytes", lambda url: b"PNGDATA")

    called = {}

    def fake_mm(*, system, content, model, max_tokens):
        called["content"] = content
        return "a cat sitting on a windowsill"

    monkeypatch.setattr(link_handler.claude_queue, "submit_multimodal", fake_mm)

    r = link_handler.handle("what's this? https://example.com/cat.png")
    assert r.action == "summarized"
    assert r.result["kind"] == "image"
    # First block image, second text with question
    assert called["content"][0]["type"] == "image"
    assert called["content"][0]["source"]["media_type"] == "image/png"
    assert called["content"][1]["type"] == "text"
    assert "what's this?" in called["content"][1]["text"]


def test_image_media_type_guess():
    assert link_handler._guess_image_media_type("https://x/y.png") == "image/png"
    assert link_handler._guess_image_media_type("https://x/y.gif") == "image/gif"
    assert link_handler._guess_image_media_type("https://x/y.webp") == "image/webp"
    assert link_handler._guess_image_media_type("https://x/y.jpg") == "image/jpeg"
    assert link_handler._guess_image_media_type("https://x/y") == "image/jpeg"


# ---------------------------------------------------------------------------
# handle() — pdf path
# ---------------------------------------------------------------------------


def test_handle_pdf_sends_document_block(monkeypatch):
    monkeypatch.setattr(link_handler, "_fetch_bytes", lambda url: b"%PDF-1.4...")

    captured = {}

    def fake_mm(*, system, content, model, max_tokens):
        captured["content"] = content
        return "pdf summary"

    monkeypatch.setattr(link_handler.claude_queue, "submit_multimodal", fake_mm)

    r = link_handler.handle("https://example.com/paper.pdf")
    assert r.action == "summarized"
    assert r.result["kind"] == "pdf"
    assert captured["content"][0]["type"] == "document"
    assert captured["content"][0]["source"]["media_type"] == "application/pdf"


# ---------------------------------------------------------------------------
# handle() — video path with full yt-dlp + ffmpeg mocks
# ---------------------------------------------------------------------------


def test_handle_video_extracts_keyframes_and_sends_vision(monkeypatch, tmp_path):
    """Drive _handle_video without touching yt-dlp / ffmpeg."""
    fake_video = tmp_path / "media.mp4"
    fake_video.write_bytes(b"\x00")

    monkeypatch.setattr(
        link_handler,
        "_run_yt_dlp",
        lambda url, out_dir, audio_only=False: fake_video,
    )
    monkeypatch.setattr(
        link_handler,
        "_extract_keyframes",
        lambda video_path, count=8: [b"FRAME1", b"FRAME2", b"FRAME3"],
    )

    captured = {}

    def fake_mm(*, system, content, model, max_tokens):
        captured["content"] = content
        return "person doing parkour"

    monkeypatch.setattr(link_handler.claude_queue, "submit_multimodal", fake_mm)

    r = link_handler.handle("what's happening here? https://instagram.com/reel/xyz")
    assert r.action == "summarized"
    assert r.result["kind"] == "video"
    assert r.result["summary"] == "person doing parkour"
    # Header text + 3 image blocks + final question text = 5 blocks
    assert len(captured["content"]) == 5
    assert captured["content"][0]["type"] == "text"
    assert all(b["type"] == "image" for b in captured["content"][1:4])
    assert captured["content"][-1]["type"] == "text"
    assert "what's happening here?" in captured["content"][-1]["text"]


def test_handle_video_no_frames_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        link_handler,
        "_run_yt_dlp",
        lambda url, out_dir, audio_only=False: tmp_path / "media.mp4",
    )
    monkeypatch.setattr(
        link_handler, "_extract_keyframes", lambda video_path, count=8: []
    )
    r = link_handler.handle("https://youtu.be/abc")
    assert r.action == "failed"
    assert "no keyframes" in r.result["error"]


# ---------------------------------------------------------------------------
# handle() — audio path
# ---------------------------------------------------------------------------


def test_handle_audio_transcribes_and_summarizes(monkeypatch, tmp_path):
    fake_audio = tmp_path / "media.mp3"
    fake_audio.write_bytes(b"\x00")
    monkeypatch.setattr(
        link_handler,
        "_run_yt_dlp",
        lambda url, out_dir, audio_only=False: fake_audio,
    )
    monkeypatch.setattr(
        link_handler, "_transcribe_audio", lambda p: "this is the transcript"
    )
    monkeypatch.setattr(
        link_handler.claude_queue,
        "submit",
        lambda *, system, user, model: "audio summary",
    )

    r = link_handler.handle("https://example.com/podcast.mp3 what did they say")
    assert r.action == "summarized"
    assert r.result["kind"] == "audio"
    assert r.result["summary"] == "audio summary"


def test_handle_audio_empty_transcript_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        link_handler,
        "_run_yt_dlp",
        lambda url, out_dir, audio_only=False: tmp_path / "media.mp3",
    )
    monkeypatch.setattr(link_handler, "_transcribe_audio", lambda p: "   ")
    r = link_handler.handle("https://example.com/x.mp3")
    assert r.action == "failed"


# ---------------------------------------------------------------------------
# handle() — exception path
# ---------------------------------------------------------------------------


def test_handle_catches_unexpected_exception(monkeypatch):
    def boom(url):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(link_handler, "_fetch_article_text", boom)
    r = link_handler.handle("https://example.com/page")
    assert r.action == "failed"
    assert "network exploded" in r.result["error"]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def test_strip_url_removes_url_only():
    out = link_handler._strip_url("see https://x.com please", "https://x.com")
    assert out == "see  please"


def test_follow_ups_for_kind():
    assert link_handler._follow_ups_for("video") != []
    assert link_handler._follow_ups_for("article") != []
    assert link_handler._follow_ups_for("image") == []


def test_image_block_shape():
    block = link_handler._image_block(b"abc", "image/png")
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"
    assert block["source"]["type"] == "base64"
    import base64

    assert base64.b64decode(block["source"]["data"]) == b"abc"


def test_fetch_article_text_strips_tags(monkeypatch):
    monkeypatch.setattr(
        link_handler,
        "_fetch_bytes",
        lambda url: b"<html><script>alert(1)</script><body>Hello <b>world</b></body></html>",
    )
    out = link_handler._fetch_article_text("https://x")
    assert "Hello" in out
    assert "world" in out
    assert "alert" not in out
    assert "<" not in out


def test_fetch_bytes_uses_httpx(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.content = b"DATA"
    fake_resp.raise_for_status = MagicMock()

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None):
            return fake_resp

    monkeypatch.setattr(link_handler.httpx, "Client", FakeClient)
    out = link_handler._fetch_bytes("https://x")
    assert out == b"DATA"


# ---------------------------------------------------------------------------
# _probe_duration_sec
# ---------------------------------------------------------------------------


def test_probe_duration_parses_hms(monkeypatch, tmp_path):
    fake_stderr = b"Duration: 00:01:23.50, start: 0.000000"

    def fake_run(cmd, *a, **kw):
        return MagicMock(returncode=0, stderr=fake_stderr, stdout=b"")

    monkeypatch.setattr(link_handler.subprocess, "run", fake_run)
    out = link_handler._probe_duration_sec(tmp_path / "v.mp4")
    assert out == pytest.approx(83.5, rel=1e-3)


def test_probe_duration_missing_returns_zero(monkeypatch, tmp_path):
    def fake_run(cmd, *a, **kw):
        return MagicMock(returncode=1, stderr=b"no duration here", stdout=b"")

    monkeypatch.setattr(link_handler.subprocess, "run", fake_run)
    assert link_handler._probe_duration_sec(tmp_path / "v.mp4") == 0.0


# ---------------------------------------------------------------------------
# _extract_keyframes — ffmpeg failure path
# ---------------------------------------------------------------------------


def test_extract_keyframes_zero_duration_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(link_handler, "_probe_duration_sec", lambda p: 0.0)
    with pytest.raises(RuntimeError, match="duration unknown"):
        link_handler._extract_keyframes(tmp_path / "v.mp4")


def test_extract_keyframes_ffmpeg_nonzero_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(link_handler, "_probe_duration_sec", lambda p: 10.0)

    def fake_run(cmd, *a, **kw):
        return MagicMock(returncode=1, stderr=b"ffmpeg boom", stdout=b"")

    monkeypatch.setattr(link_handler.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="keyframe extraction failed"):
        link_handler._extract_keyframes(tmp_path / "v.mp4")


def test_extract_keyframes_reads_jpgs(monkeypatch, tmp_path):
    monkeypatch.setattr(link_handler, "_probe_duration_sec", lambda p: 10.0)

    # Simulate ffmpeg writing 3 JPEGs into the temp dir it gets passed.
    def fake_run(cmd, *a, **kw):
        # The output pattern is the last positional arg.
        out_pattern = cmd[-1]
        out_dir = Path(out_pattern).parent
        for i in range(3):
            (out_dir / f"frame_{i:03d}.jpg").write_bytes(f"JPG{i}".encode())
        return MagicMock(returncode=0, stderr=b"", stdout=b"")

    monkeypatch.setattr(link_handler.subprocess, "run", fake_run)
    frames = link_handler._extract_keyframes(tmp_path / "v.mp4", count=3)
    assert frames == [b"JPG0", b"JPG1", b"JPG2"]
