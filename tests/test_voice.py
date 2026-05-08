"""Voice subsystem tests — wake, STT, TTS, loop pipeline."""
from __future__ import annotations

import asyncio

import httpx

from jarvis.voice.loop import _voice_summary, process_utterance
from jarvis.voice.stt import DeepgramSTT, MockSTT
from jarvis.voice.tts import ElevenLabsTTS, MockTTS
from jarvis.voice.wake import MockWakeDetector


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


def test_voice_summary_email_counts():
    out = _voice_summary({
        "responses": {
            "aide": {"agent": "aide", "action": "triaged",
                     "result": {"counts": {"action_required": 3}}}
        }
    })
    assert "3 action emails" in out


def test_voice_summary_calendar():
    out = _voice_summary({
        "responses": {
            "chronos": {"agent": "chronos", "action": "listed", "result": {"count": 4}}
        }
    })
    assert "4 events today" in out


def test_voice_summary_ledger():
    out = _voice_summary({
        "responses": {
            "ledger": {"agent": "ledger", "action": "fetched",
                       "result": {"pnl": {"pnl_pct": 0.012}}}
        }
    })
    assert "1.2%" in out


def test_voice_summary_needs_confirm():
    out = _voice_summary({"needs_confirm": True, "responses": {}})
    assert "confirm" in out.lower()


def test_voice_summary_empty():
    assert _voice_summary({"responses": {}}) == "Nothing to report."


def test_voice_summary_other_agent():
    out = _voice_summary({"responses": {"sherlock": {"agent": "sherlock", "action": "researched"}}})
    assert "sherlock" in out


def test_process_utterance_pipeline():
    async def stub_handle(text):
        return {"responses": {"chronos": {"agent": "chronos", "action": "listed",
                                          "result": {"count": 2}}}}
    tts = MockTTS()
    response, audio = asyncio.run(process_utterance("what's today", stub_handle, tts))
    assert "2 events today" in tts.calls[0]
    assert b"<mock-audio:" in audio
