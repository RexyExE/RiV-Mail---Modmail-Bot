import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_list(key: str, default: str = "") -> list[str]:
    raw = os.getenv(key, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


TOKEN: str = os.getenv("BOT_TOKEN", "")
PREFIX: str = os.getenv("PREFIX", "!")
BOT_NAME: str = os.getenv("BOT_NAME", "RiV Mail")

OWNER_IDS: list[int] = [int(x) for x in _env_list("OWNER_IDS")]

ACCENT_COLOR: str = os.getenv("ACCENT_COLOR", "#000000")
ERROR_COLOR: str = os.getenv("ERROR_COLOR", "#ED4245")
SUCCESS_COLOR: str = os.getenv("SUCCESS_COLOR", "#57F287")
WARNING_COLOR: str = os.getenv("WARNING_COLOR", "#FEE75C")

DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "rivmail.db"))
TRANSCRIPT_DIR: str = os.getenv("TRANSCRIPT_DIR", str(BASE_DIR / "data" / "transcripts"))

EMOJIS_JSON: str = os.getenv("EMOJIS_JSON", str(BASE_DIR / "emojis.json"))
EMOJIS_UPLOADED_JSON: str = os.getenv("EMOJIS_UPLOADED_JSON", str(BASE_DIR / "emojis_uploaded.json"))
AUTO_UPLOAD_EMOJIS: bool = _env_bool("AUTO_UPLOAD_EMOJIS", True)

DEFAULT_TICKET_NAME_FORMAT: str = os.getenv("DEFAULT_TICKET_NAME_FORMAT", "ticket-{username}")

SYNC_COMMANDS_ON_STARTUP: bool = _env_bool("SYNC_COMMANDS_ON_STARTUP", True)

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
