from __future__ import annotations

import time
import secrets
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            INTEGER PRIMARY KEY,
    staff_role_id       INTEGER,
    category_id         INTEGER,
    log_channel_id      INTEGER,
    transcript_channel_id INTEGER,
    ticket_name_format  TEXT,
    ping_staff          INTEGER DEFAULT 1,
    default_anonymous   INTEGER DEFAULT 0,
    welcome_message     TEXT,
    close_message       TEXT,
    setup_complete      INTEGER DEFAULT 0,
    auto_close_hours    INTEGER DEFAULT 0,
    ticket_cooldown_minutes INTEGER DEFAULT 0,
    away_enabled        INTEGER DEFAULT 0,
    away_message        TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id       TEXT PRIMARY KEY,
    guild_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    channel_id      INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    claimed_by      INTEGER,
    reply_mode      TEXT NOT NULL DEFAULT 'normal',
    created_at      INTEGER NOT NULL,
    closed_at       INTEGER,
    closed_by       INTEGER,
    last_activity_at INTEGER,
    priority        TEXT NOT NULL DEFAULT 'normal',
    reason_key      TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_open_user ON tickets (user_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_channel ON tickets (channel_id);
CREATE INDEX IF NOT EXISTS idx_tickets_guild_user ON tickets (guild_id, user_id);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT NOT NULL,
    sender_id   INTEGER NOT NULL,
    sender_name TEXT NOT NULL,
    content     TEXT,
    is_staff    INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    source_message_id INTEGER,
    mirror_message_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_msgs_ticket ON ticket_messages (ticket_id);

CREATE TABLE IF NOT EXISTS staff_reply_modes (
    ticket_id   TEXT NOT NULL,
    staff_id    INTEGER NOT NULL,
    mode        TEXT NOT NULL DEFAULT 'normal',
    PRIMARY KEY (ticket_id, staff_id)
);

CREATE TABLE IF NOT EXISTS blacklist (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    reason      TEXT,
    added_by    INTEGER,
    added_at    INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS snippets (
    guild_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_by  INTEGER,
    created_at  INTEGER,
    PRIMARY KEY (guild_id, name)
);

CREATE TABLE IF NOT EXISTS ticket_reasons (
    guild_id        INTEGER NOT NULL,
    key             TEXT NOT NULL,
    label           TEXT NOT NULL,
    emoji           TEXT,
    category_id     INTEGER,
    staff_role_id   INTEGER,
    PRIMARY KEY (guild_id, key)
);

CREATE TABLE IF NOT EXISTS ticket_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT NOT NULL,
    staff_id    INTEGER NOT NULL,
    content     TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_ticket ON ticket_notes (ticket_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    actor_id    INTEGER NOT NULL,
    action      TEXT NOT NULL,
    detail      TEXT,
    created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_guild ON audit_log (guild_id, created_at);
"""

MIGRATIONS = [
    "ALTER TABLE guild_config ADD COLUMN auto_close_hours INTEGER DEFAULT 0",
    "ALTER TABLE guild_config ADD COLUMN ticket_cooldown_minutes INTEGER DEFAULT 0",
    "ALTER TABLE guild_config ADD COLUMN away_enabled INTEGER DEFAULT 0",
    "ALTER TABLE guild_config ADD COLUMN away_message TEXT",
    "ALTER TABLE tickets ADD COLUMN last_activity_at INTEGER",
    "ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'",
    "ALTER TABLE tickets ADD COLUMN reason_key TEXT",
    "ALTER TABLE ticket_messages ADD COLUMN source_message_id INTEGER",
    "ALTER TABLE ticket_messages ADD COLUMN mirror_message_id INTEGER",
    "CREATE INDEX IF NOT EXISTS idx_msgs_source ON ticket_messages (source_message_id)",
]


def _new_ticket_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@dataclass
class GuildConfig:
    guild_id: int
    staff_role_id: Optional[int] = None
    category_id: Optional[int] = None
    log_channel_id: Optional[int] = None
    transcript_channel_id: Optional[int] = None
    ticket_name_format: Optional[str] = None
    ping_staff: bool = True
    default_anonymous: bool = False
    welcome_message: Optional[str] = None
    close_message: Optional[str] = None
    setup_complete: bool = False
    auto_close_hours: int = 0
    ticket_cooldown_minutes: int = 0
    away_enabled: bool = False
    away_message: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        return bool(self.setup_complete and self.staff_role_id and self.category_id)


class Database:
    def __init__(self, path: str = config.DB_PATH):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        for stmt in MIGRATIONS:
            try:
                await self._conn.execute(stmt)
            except aiosqlite.OperationalError:
                pass
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None
        return self._conn

    async def get_guild_config(self, guild_id: int) -> GuildConfig:
        cur = await self.conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if not row:
            return GuildConfig(guild_id=guild_id)
        keys = row.keys()
        return GuildConfig(
            guild_id=row["guild_id"],
            staff_role_id=row["staff_role_id"],
            category_id=row["category_id"],
            log_channel_id=row["log_channel_id"],
            transcript_channel_id=row["transcript_channel_id"],
            ticket_name_format=row["ticket_name_format"],
            ping_staff=bool(row["ping_staff"]),
            default_anonymous=bool(row["default_anonymous"]),
            welcome_message=row["welcome_message"],
            close_message=row["close_message"],
            setup_complete=bool(row["setup_complete"]),
            auto_close_hours=row["auto_close_hours"] if "auto_close_hours" in keys and row["auto_close_hours"] is not None else 0,
            ticket_cooldown_minutes=row["ticket_cooldown_minutes"] if "ticket_cooldown_minutes" in keys and row["ticket_cooldown_minutes"] is not None else 0,
            away_enabled=bool(row["away_enabled"]) if "away_enabled" in keys else False,
            away_message=row["away_message"] if "away_message" in keys else None,
        )

    async def upsert_guild_config(self, cfg: GuildConfig) -> None:
        await self.conn.execute(
            """
            INSERT INTO guild_config (
                guild_id, staff_role_id, category_id, log_channel_id,
                transcript_channel_id, ticket_name_format, ping_staff,
                default_anonymous, welcome_message, close_message, setup_complete,
                auto_close_hours, ticket_cooldown_minutes, away_enabled, away_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                staff_role_id=excluded.staff_role_id,
                category_id=excluded.category_id,
                log_channel_id=excluded.log_channel_id,
                transcript_channel_id=excluded.transcript_channel_id,
                ticket_name_format=excluded.ticket_name_format,
                ping_staff=excluded.ping_staff,
                default_anonymous=excluded.default_anonymous,
                welcome_message=excluded.welcome_message,
                close_message=excluded.close_message,
                setup_complete=excluded.setup_complete,
                auto_close_hours=excluded.auto_close_hours,
                ticket_cooldown_minutes=excluded.ticket_cooldown_minutes,
                away_enabled=excluded.away_enabled,
                away_message=excluded.away_message
            """,
            (
                cfg.guild_id, cfg.staff_role_id, cfg.category_id, cfg.log_channel_id,
                cfg.transcript_channel_id, cfg.ticket_name_format, int(cfg.ping_staff),
                int(cfg.default_anonymous), cfg.welcome_message, cfg.close_message,
                int(cfg.setup_complete), cfg.auto_close_hours, cfg.ticket_cooldown_minutes,
                int(cfg.away_enabled), cfg.away_message,
            ),
        )
        await self.conn.commit()

    async def configured_guild_ids(self) -> list[int]:
        cur = await self.conn.execute("SELECT guild_id FROM guild_config WHERE setup_complete = 1")
        rows = await cur.fetchall()
        return [r["guild_id"] for r in rows]

    async def all_guild_configs(self) -> list[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM guild_config WHERE setup_complete = 1")
        return await cur.fetchall()

    async def get_open_ticket_for_user(self, user_id: int, guild_id: int) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? AND guild_id = ? AND status = 'open'",
            (user_id, guild_id),
        )
        return await cur.fetchone()

    async def get_last_closed_ticket(self, user_id: int, guild_id: int) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? AND guild_id = ? AND status = 'closed' "
            "ORDER BY closed_at DESC LIMIT 1",
            (user_id, guild_id),
        )
        return await cur.fetchone()

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
        return await cur.fetchone()

    async def get_ticket(self, ticket_id: str) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        return await cur.fetchone()

    async def create_ticket(self, guild_id: int, user_id: int, channel_id: int, reason_key: str | None = None) -> str:
        ticket_id = _new_ticket_id()
        now = int(time.time())
        await self.conn.execute(
            "INSERT INTO tickets (ticket_id, guild_id, user_id, channel_id, status, created_at, last_activity_at, reason_key) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?, ?)",
            (ticket_id, guild_id, user_id, channel_id, now, now, reason_key),
        )
        await self.conn.commit()
        return ticket_id

    async def close_ticket(self, ticket_id: str, closed_by: int) -> None:
        await self.conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ? WHERE ticket_id = ?",
            (int(time.time()), closed_by, ticket_id),
        )
        await self.conn.commit()

    async def set_claim(self, ticket_id: str, staff_id: Optional[int]) -> None:
        await self.conn.execute("UPDATE tickets SET claimed_by = ? WHERE ticket_id = ?", (staff_id, ticket_id))
        await self.conn.commit()

    async def set_priority(self, ticket_id: str, priority: str) -> None:
        await self.conn.execute("UPDATE tickets SET priority = ? WHERE ticket_id = ?", (priority, ticket_id))
        await self.conn.commit()

    async def touch_activity(self, ticket_id: str) -> None:
        await self.conn.execute(
            "UPDATE tickets SET last_activity_at = ? WHERE ticket_id = ?", (int(time.time()), ticket_id)
        )
        await self.conn.commit()

    async def stale_open_tickets(self, guild_id: int, older_than_ts: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND status = 'open' AND last_activity_at < ?",
            (guild_id, older_than_ts),
        )
        return await cur.fetchall()

    async def guild_ticket_stats(self, guild_id: int) -> dict:
        cur = await self.conn.execute(
            "SELECT status, COUNT(*) as n FROM tickets WHERE guild_id = ? GROUP BY status", (guild_id,)
        )
        rows = await cur.fetchall()
        stats = {"open": 0, "closed": 0}
        for r in rows:
            stats[r["status"]] = r["n"]
        stats["total"] = stats["open"] + stats["closed"]

        day_ago = int(time.time()) - 86400
        week_ago = int(time.time()) - 7 * 86400
        cur = await self.conn.execute(
            "SELECT COUNT(*) as n FROM tickets WHERE guild_id = ? AND created_at >= ?", (guild_id, day_ago)
        )
        stats["today"] = (await cur.fetchone())["n"]
        cur = await self.conn.execute(
            "SELECT COUNT(*) as n FROM tickets WHERE guild_id = ? AND created_at >= ?", (guild_id, week_ago)
        )
        stats["this_week"] = (await cur.fetchone())["n"]
        return stats

    async def staff_leaderboard(self, guild_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT staff_id,
                   SUM(claims) as claims,
                   SUM(closes) as closes
            FROM (
                SELECT claimed_by as staff_id, 1 as claims, 0 as closes
                FROM tickets WHERE guild_id = ? AND claimed_by IS NOT NULL
                UNION ALL
                SELECT closed_by as staff_id, 0 as claims, 1 as closes
                FROM tickets WHERE guild_id = ? AND closed_by IS NOT NULL
            )
            GROUP BY staff_id
            ORDER BY (SUM(claims) + SUM(closes)) DESC
            LIMIT ?
            """,
            (guild_id, guild_id, limit),
        )
        return await cur.fetchall()

    async def user_ticket_history(self, guild_id: int, user_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id),
        )
        return await cur.fetchall()

    async def log_message(
        self, ticket_id: str, sender_id: int, sender_name: str, content: str, is_staff: bool,
        source_message_id: int | None = None, mirror_message_id: int | None = None,
    ) -> int:
        cur = await self.conn.execute(
            "INSERT INTO ticket_messages (ticket_id, sender_id, sender_name, content, is_staff, created_at, source_message_id, mirror_message_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, sender_id, sender_name, content, int(is_staff), int(time.time()), source_message_id, mirror_message_id),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_messages(self, ticket_id: str) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC, id ASC", (ticket_id,)
        )
        return await cur.fetchall()

    async def find_message_by_source(self, source_message_id: int) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM ticket_messages WHERE source_message_id = ?", (source_message_id,)
        )
        return await cur.fetchone()

    async def get_staff_mode(self, ticket_id: str, staff_id: int, default: str = "normal") -> str:
        cur = await self.conn.execute(
            "SELECT mode FROM staff_reply_modes WHERE ticket_id = ? AND staff_id = ?", (ticket_id, staff_id)
        )
        row = await cur.fetchone()
        return row["mode"] if row else default

    async def set_staff_mode(self, ticket_id: str, staff_id: int, mode: str) -> None:
        await self.conn.execute(
            "INSERT INTO staff_reply_modes (ticket_id, staff_id, mode) VALUES (?, ?, ?) "
            "ON CONFLICT(ticket_id, staff_id) DO UPDATE SET mode = excluded.mode",
            (ticket_id, staff_id, mode),
        )
        await self.conn.commit()

    async def is_blacklisted(self, guild_id: int, user_id: int) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM blacklist WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        return await cur.fetchone()

    async def blacklist_add(self, guild_id: int, user_id: int, reason: str, added_by: int) -> None:
        await self.conn.execute(
            "INSERT INTO blacklist (guild_id, user_id, reason, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET reason=excluded.reason",
            (guild_id, user_id, reason, added_by, int(time.time())),
        )
        await self.conn.commit()

    async def blacklist_remove(self, guild_id: int, user_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM blacklist WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await self.conn.commit()
        return cur.rowcount > 0

    async def blacklist_list(self, guild_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM blacklist WHERE guild_id = ? ORDER BY added_at DESC", (guild_id,))
        return await cur.fetchall()

    async def snippet_get(self, guild_id: int, name: str) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM snippets WHERE guild_id = ? AND name = ?", (guild_id, name.lower())
        )
        return await cur.fetchone()

    async def snippet_set(self, guild_id: int, name: str, content: str, created_by: int) -> None:
        await self.conn.execute(
            "INSERT INTO snippets (guild_id, name, content, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(guild_id, name) DO UPDATE SET content=excluded.content",
            (guild_id, name.lower(), content, created_by, int(time.time())),
        )
        await self.conn.commit()

    async def snippet_delete(self, guild_id: int, name: str) -> bool:
        cur = await self.conn.execute("DELETE FROM snippets WHERE guild_id = ? AND name = ?", (guild_id, name.lower()))
        await self.conn.commit()
        return cur.rowcount > 0

    async def snippet_list(self, guild_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM snippets WHERE guild_id = ? ORDER BY name ASC", (guild_id,))
        return await cur.fetchall()

    async def reason_add(self, guild_id: int, key: str, label: str, emoji: str | None, category_id: int | None, staff_role_id: int | None) -> None:
        await self.conn.execute(
            "INSERT INTO ticket_reasons (guild_id, key, label, emoji, category_id, staff_role_id) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(guild_id, key) DO UPDATE SET "
            "label=excluded.label, emoji=excluded.emoji, category_id=excluded.category_id, staff_role_id=excluded.staff_role_id",
            (guild_id, key.lower(), label, emoji, category_id, staff_role_id),
        )
        await self.conn.commit()

    async def reason_remove(self, guild_id: int, key: str) -> bool:
        cur = await self.conn.execute("DELETE FROM ticket_reasons WHERE guild_id = ? AND key = ?", (guild_id, key.lower()))
        await self.conn.commit()
        return cur.rowcount > 0

    async def reason_list(self, guild_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM ticket_reasons WHERE guild_id = ? ORDER BY key ASC", (guild_id,))
        return await cur.fetchall()

    async def reason_get(self, guild_id: int, key: str) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM ticket_reasons WHERE guild_id = ? AND key = ?", (guild_id, key.lower())
        )
        return await cur.fetchone()

    async def note_add(self, ticket_id: str, staff_id: int, content: str) -> None:
        await self.conn.execute(
            "INSERT INTO ticket_notes (ticket_id, staff_id, content, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, staff_id, content, int(time.time())),
        )
        await self.conn.commit()

    async def note_list(self, ticket_id: str) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM ticket_notes WHERE ticket_id = ? ORDER BY created_at ASC", (ticket_id,)
        )
        return await cur.fetchall()

    async def audit_add(self, guild_id: int, actor_id: int, action: str, detail: str) -> None:
        await self.conn.execute(
            "INSERT INTO audit_log (guild_id, actor_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, actor_id, action, detail, int(time.time())),
        )
        await self.conn.commit()
