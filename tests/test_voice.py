"""Voice subsystem tests — wake, STT, TTS, loop pipeline."""
from __future__ import annotations

import asyncio

import httpx

from jarvis.apps.voice import loop as voice_loop
from jarvis.apps.voice.loop import _spoken_text, process_utterance
from jarvis.apps.voice.stt import DeepgramSTT, MockSTT
from jarvis.apps.voice.tts import ElevenLabsTTS, MockTTS
from jarvis.apps.voice.wake import MockWakeDetector


def test_wake_detects_keyword():
    d = MockWakeDetector()
    assert d.listen([b"random", b"Hey Jarvis what's up"]) is True


def test_wake_no_match():
    d = MockWakeDetector()
    assert d.listen([b"silence", b"weather"]) is False


def test_wake_custom_keyword():
    d = MockWakeDetector(keyword="atlas wake")
    assert d.listen([b"ATLAS WAKE up"]) is True


def test_mock_stt():
    s = MockSTT(response="check inbox")
    assert s.transcribe(b"audio") == "check inbox"


def test_deepgram_stt_parses_response():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={
        "results": {"channels": [{"alternatives": [{"transcript": "hello world"}]}]}
    }))
    s = DeepgramSTT(api_key="t", transport=transport)
    assert s.transcribe(b"audio") == "hello world"


def test_deepgram_stt_handles_error():
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    s = DeepgramSTT(api_key="t", transport=transport)
    assert s.transcribe(b"audio") == ""


def test_deepgram_stt_handles_empty_channels():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"results": {"channels": []}}))
    s = DeepgramSTT(api_key="t", transport=transport)
    assert s.transcribe(b"audio") == ""


def test_mock_tts_records_calls():
    t = MockTTS()
    audio = t.synthesize("hello")
    assert b"hello" in audio
    assert t.calls == ["hello"]


def test_elevenlabs_tts_returns_bytes():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"AUDIO"))
    t = ElevenLabsTTS(api_key="k", voice_id="v", transport=transport)
    assert t.synthesize("hi") == b"AUDIO"


def test_elevenlabs_tts_returns_empty_on_failure():
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    t = ElevenLabsTTS(api_key="k", voice_id="v", transport=transport)
    assert t.synthesize("hi") == b""


# ---------------------------------------------------------------------------
# _spoken_text — extracts/synthesizes the spoken-ready line from handler dict
# ---------------------------------------------------------------------------


def test_spoken_text_uses_voice_tier_reply():
    """Cheap-handler tiers (local/Haiku/Sonnet) put spoken text in responses.voice."""
    out = _spoken_text({
        "responses": {
            "voice": {
                "agent": "voice",
                "action": "Yeah, three emails — none urgent.",
                "result": {"text": "Yeah, three emails — none urgent.", "source": "local"},
            }
        },
        "source": "local",
    })
    assert out == "Yeah, three emails — none urgent."


def test_spoken_text_falls_back_to_action_when_result_text_missing():
    out = _spoken_text({
        "responses": {"voice": {"agent": "voice", "action": "Got it."}},
    })
    assert out == "Got it."


def test_spoken_text_voice_tier_empty_string_fallback():
    out = _spoken_text({
        "responses": {"voice": {"agent": "voice", "action": "", "result": {"text": ""}}},
    })
    assert out == "Got it."


def test_spoken_text_needs_confirm():
    out = _spoken_text({"needs_confirm": True, "responses": {}})
    assert "okay" in out.lower() or "confirm" in out.lower()


def test_spoken_text_empty_responses():
    out = _spoken_text({"responses": {}})
    assert out  # non-empty
    assert "?" in out  # invites follow-up


def test_spoken_text_dispatch_path_calls_humanizer(monkeypatch):
    """Tier 3 (orchestrator) — no voice tier present → humanizer runs."""
    captured = {}

    def fake_humanize(response):
        captured["response"] = response
        return "Drafted that — held for your review."

    monkeypatch.setattr(voice_loop, "_humanize_dispatch", fake_humanize)
    out = _spoken_text({
        "responses": {"tempo": {"agent": "tempo", "action": "drafted", "result": {"id": "abc"}}},
        "source": "orchestrator",
    })
    assert out == "Drafted that — held for your review."
    assert captured["response"]["source"] == "orchestrator"


def test_humanize_dispatch_uses_submit(monkeypatch):
    """Humanizer routes through claude_queue.submit with Haiku model."""
    seen = {}

    def fake_submit(*, system, user, model):
        seen["system"] = system
        seen["user"] = user
        seen["model"] = model
        return "  Got it — anything else?  "

    import jarvis.llm.queue as cq
    monkeypatch.setattr(cq, "submit", fake_submit)

    out = voice_loop._humanize_dispatch({
        "responses": {"tempo": {"action": "drafted"}}
    })
    assert out == "Got it — anything else?"
    assert seen["model"] == voice_loop.HUMANIZER_MODEL
    assert "Background work output" in seen["user"]


def test_humanize_dispatch_swallows_errors(monkeypatch):
    """LLM failure → fallback string, voice never crashes."""
    def boom(**kwargs):
        raise RuntimeError("rate limited")

    import jarvis.llm.queue as cq
    monkeypatch.setattr(cq, "submit", boom)

    out = voice_loop._humanize_dispatch({"responses": {"tempo": {"action": "drafted"}}})
    assert out  # non-empty fallback
    assert "?" in out


# ---------------------------------------------------------------------------
# process_utterance — full pipeline
# ---------------------------------------------------------------------------


def test_process_utterance_pipeline_voice_tier():
    """Voice-tier reply (Tier 0/1/2) → spoken text passed straight to TTS."""
    async def stub_handle(text):
        return {
            "responses": {
                "voice": {
                    "agent": "voice",
                    "action": "Three events on the calendar today.",
                    "result": {"text": "Three events on the calendar today."},
                }
            },
            "source": "local",
        }
    tts = MockTTS()
    response, audio = asyncio.run(process_utterance("what's today", stub_handle, tts))
    assert "Three events" in tts.calls[0]
    assert b"<mock-audio:" in audio
    assert response["source"] == "local"


def test_process_utterance_pipeline_dispatch(monkeypatch):
    """Orchestrator dispatch → humanizer produces spoken ack."""
    async def stub_handle(text):
        return {
            "responses": {"tempo": {"agent": "tempo", "action": "drafted", "result": {"id": "x"}}},
            "source": "orchestrator",
        }
    monkeypatch.setattr(voice_loop, "_humanize_dispatch",
                        lambda r: "Drafted — want me to send it?")
    tts = MockTTS()
    _response, _audio = asyncio.run(process_utterance("draft email to bob", stub_handle, tts))
    assert tts.calls[0] == "Drafted — want me to send it?"
