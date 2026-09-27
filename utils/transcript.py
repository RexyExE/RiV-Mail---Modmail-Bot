from __future__ import annotations

import io
from datetime import timezone

import discord


async def generate_transcript(channel: discord.TextChannel, ticket_id: str, bot: discord.Client) -> tuple[discord.File, str]:
    filename = f"transcript-{ticket_id}.html"
    try:
        import chat_exporter

        html = await chat_exporter.export(channel, limit=None, bot=bot)
        if html is None:
            raise RuntimeError("chat_exporter returned no content")
        buf = io.BytesIO(html.encode("utf-8"))
        return discord.File(buf, filename=filename), filename
    except Exception:
        return await _plain_text_fallback(channel, ticket_id)


async def _plain_text_fallback(channel: discord.TextChannel, ticket_id: str) -> tuple[discord.File, str]:
    lines: list[str] = [f"Transcript for ticket {ticket_id}", "=" * 40, ""]
    async for msg in channel.history(limit=None, oldest_first=True):
        if msg.author.bot and not msg.content and not msg.embeds and not msg.components:
            continue
        ts = msg.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        content = msg.content or "*[component/embed message]*"
        lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {content}")

    filename = f"transcript-{ticket_id}.txt"
    buf = io.BytesIO("\n".join(lines).encode("utf-8"))
    return discord.File(buf, filename=filename), filename
