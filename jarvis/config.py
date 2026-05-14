"""Runtime config — env-var driven."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    project_root: Path
    state_dir: Path
    atlas_api: str
    pushover_user_key: str | None = None
    pushover_api_token: str | None = None
    ntfy_topic: str | None = None
    ntfy_server: str = "https://ntfy.sh"
    slack_bot_token: str | None = None
    slack_signing_secret: str | None = None
    discord_bot_token: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone: str | None = None
    # Voice subsystem (Phase 5.1)
    voice_enabled: bool = False
    voice_engine_stt: str = "whisper-local"  # whisper-local | deepgram
    voice_engine_tts: str = "edge-tts"  # edge-tts | elevenlabs | piper
    voice_wake_backend: str = "openwakeword"  # openwakeword | porcupine | mock
    voice_wake_word: str = "hey jarvis"
    voice_name: str = "en-US-AndrewMultilingualNeural"  # default; locked after Phase B A/B
    voice_rate: str = "+0%"  # edge-tts speech rate, e.g. "+0%", "+10%", "-5%"
    voice_whisper_model: str = "base.en"  # tiny.en | base.en | small.en | medium.en
    voice_silence_threshold: float = 500.0  # int16 RMS — energy VAD cutoff
    voice_max_response_tokens: int = 120  # cap LLM reply length for terse voice
    deepgram_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    picovoice_access_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    project_root = Path(
        os.environ.get("JARVIS_PROJECT_ROOT", Path(__file__).resolve().parents[1])
    )
    state_dir = Path(os.environ.get("JARVIS_STATE_DIR", project_root / "state"))
    state_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        project_root=project_root,
        state_dir=state_dir,
        atlas_api=os.environ.get("JARVIS_ATLAS_API", "http://localhost:8000"),
        pushover_user_key=os.environ.get("PUSHOVER_USER_KEY"),
        pushover_api_token=os.environ.get("PUSHOVER_API_TOKEN"),
        ntfy_topic=os.environ.get("NTFY_TOPIC"),
        ntfy_server=os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
        slack_bot_token=os.environ.get("SLACK_BOT_TOKEN"),
        slack_signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
        discord_bot_token=os.environ.get("DISCORD_BOT_TOKEN"),
        twilio_account_sid=os.environ.get("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=os.environ.get("TWILIO_AUTH_TOKEN"),
        twilio_phone=os.environ.get("TWILIO_PHONE"),
        voice_enabled=os.environ.get("VOICE_ENABLED", "false").lower() in ("1", "true", "yes"),
        voice_engine_stt=os.environ.get("VOICE_ENGINE_STT", "whisper-local"),
        voice_engine_tts=os.environ.get("VOICE_ENGINE_TTS", "edge-tts"),
        voice_wake_backend=os.environ.get("VOICE_WAKE_BACKEND", "openwakeword"),
        voice_wake_word=os.environ.get("VOICE_WAKE_WORD", "hey jarvis"),
        voice_name=os.environ.get("VOICE_NAME", "en-US-AndrewMultilingualNeural"),
        voice_rate=os.environ.get("VOICE_RATE", "+0%"),
        voice_whisper_model=os.environ.get("VOICE_WHISPER_MODEL", "base.en"),
        voice_silence_threshold=float(os.environ.get("VOICE_SILENCE_THRESHOLD", "500")),
        voice_max_response_tokens=int(os.environ.get("VOICE_MAX_RESPONSE_TOKENS", "120")),
        deepgram_api_key=os.environ.get("DEEPGRAM_API_KEY") or None,
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY") or None,
        elevenlabs_voice_id=os.environ.get("ELEVENLABS_VOICE_ID") or None,
        picovoice_access_key=os.environ.get("PICOVOICE_ACCESS_KEY") or None,
    )
