from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config

_FALLBACK: dict[str, str] = {
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️", "loading": "⏳",
    "staff": "🛡️", "admin": "🛡️", "owner": "👑", "user": "👤",
    "lock": "🔒", "unlock": "🔓", "add": "➕", "remove": "➖",
    "arrow": "➜", "dot": "🔘", "blank": "\u3164",
    "ticket": "🎫", "reply": "💬", "close": "🚫", "delete": "🗑️",
    "claim": "🙋", "unclaim": "↩️", "reload": "🔄", "transcript": "📄",
    "guide": "📖", "mail": "📬", "setup": "⚙️", "mode": "🕵️",
    "snippet": "📌", "stats": "📊", "ping": "🏓", "vip": "💎",
    "cancel": "✖️", "next": "➡️", "prev": "⬅️", "page": "📄",
    "priority": "🚩", "note": "🗒️", "history": "🕘", "away": "🌙", "audit": "📋",
}

_uploaded_cache: dict[str, Any] | None = None


def _load_uploaded() -> dict[str, Any]:
    global _uploaded_cache
    path = Path(config.EMOJIS_UPLOADED_JSON)
    if not path.exists():
        _uploaded_cache = {}
        return _uploaded_cache
    try:
        _uploaded_cache = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _uploaded_cache = {}
    return _uploaded_cache


def reload_cache() -> None:
    _load_uploaded()


def get(key: str) -> str:
    data = _uploaded_cache if _uploaded_cache is not None else _load_uploaded()
    entry = data.get(key)
    if entry and entry.get("id") and entry.get("name"):
        animated = "a" if entry.get("animated") else ""
        return f"<{animated}:{entry['name']}:{entry['id']}>"
    return _FALLBACK.get(key, "")


class _EmojiProxy:
    def __getattr__(self, key: str) -> str:
        return get(key)


e = _EmojiProxy()
