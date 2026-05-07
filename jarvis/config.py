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
    )
