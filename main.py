from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

import config
from utils.banner import print_banner
from utils.database import Database
from utils.emojis import reload_cache
from scripts.emoji_uploader import run as run_emoji_upload

logging.basicConfig(level=config.LOG_LEVEL, format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("rivmail")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True
INTENTS.dm_messages = True

COGS = (
    "cogs.setup",
    "cogs.reasons",
    "cogs.modmail",
    "cogs.reply",
    "cogs.staff",
    "cogs.blacklist",
    "cogs.snippets",
    "cogs.utility",
    "cogs.owner",
)


class RiVMail(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=config.PREFIX, intents=INTENTS, help_command=None)
        self.command_prefix_str = config.PREFIX
        self.db = Database(config.DB_PATH)

    async def setup_hook(self) -> None:
        await self.db.connect()
        log.info("Database ready.")

        if config.AUTO_UPLOAD_EMOJIS:
            log.info("Running emoji uploader...")
            try:
                await run_emoji_upload()
                reload_cache()
            except Exception:
                log.exception("Emoji upload failed.")

        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("Loaded %s", cog)
            except Exception:
                log.exception("Failed to load %s", cog)

        if config.SYNC_COMMANDS_ON_STARTUP:
            synced = await self.tree.sync()
            log.info("Synced %d application commands.", len(synced))

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="RiV MaiL  |  !help"))


async def main() -> None:
    print_banner(config.BOT_NAME, config.PREFIX)

    if not config.TOKEN:
        raise SystemExit("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    bot = RiVMail()
    try:
        await bot.start(config.TOKEN)
    finally:
        await bot.db.close()


if __name__ == "__main__":
    asyncio.run(main())
