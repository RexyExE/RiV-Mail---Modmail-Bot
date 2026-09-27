from __future__ import annotations

from discord.ext import commands

from scripts.emoji_uploader import run as run_emoji_upload
from utils import checks, embeds
from utils.emojis import reload_cache


class Owner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="reload", description="Reload all cogs and re-sync commands (owner only).")
    @checks.owner_only()
    async def reload_cmd(self, ctx: commands.Context) -> None:
        msg = await ctx.reply(view=embeds.loading("Reloading..."), mention_author=False)

        reloaded, failed = [], []
        for name in list(self.bot.extensions.keys()):
            try:
                await self.bot.reload_extension(name)
                reloaded.append(name)
            except Exception as exc:
                failed.append(f"{name}: {exc}")

        synced = await self.bot.tree.sync()

        body = f"Reloaded **{len(reloaded)}** cogs, synced **{len(synced)}** commands."
        if failed:
            body += "\n\n**Failed:**\n" + "\n".join(f"`{f}`" for f in failed)
            return await msg.edit(view=embeds.warning(body))
        await msg.edit(view=embeds.success(body))

    @commands.hybrid_command(name="syncemojis", description="Re-run the emoji uploader (owner only).")
    @checks.owner_only()
    async def sync_emojis_cmd(self, ctx: commands.Context) -> None:
        msg = await ctx.reply(view=embeds.loading("Uploading missing emojis..."), mention_author=False)
        uploaded = await run_emoji_upload()
        reload_cache()
        await msg.edit(view=embeds.success(f"Emoji sync complete. **{len(uploaded)}** keys resolved."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Owner(bot))
