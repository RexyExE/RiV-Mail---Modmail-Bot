from __future__ import annotations

from discord import app_commands
from discord.ext import commands

from utils import checks, embeds
from utils.emojis import e


class Snippets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="snippet", description="Manage saved snippet replies.", invoke_without_command=True)
    @checks.staff_only()
    async def snippet_group(self, ctx: commands.Context) -> None:
        await self._list(ctx)

    @snippet_group.command(name="add", description="Save a new snippet.")
    @checks.admin_only()
    @app_commands.describe(name="Short name (used as !name)", content="The snippet's text")
    async def snippet_add(self, ctx: commands.Context, name: str, *, content: str) -> None:
        await self.bot.db.snippet_set(ctx.guild.id, name, content, ctx.author.id)
        await ctx.reply(view=embeds.success(f"Snippet `{name.lower()}` saved. Use it with `!{name.lower()}` in a ticket."), mention_author=False)

    @snippet_group.command(name="remove", description="Delete a snippet.")
    @checks.admin_only()
    @app_commands.describe(name="Snippet to delete")
    async def snippet_remove(self, ctx: commands.Context, name: str) -> None:
        removed = await self.bot.db.snippet_delete(ctx.guild.id, name)
        if not removed:
            return await ctx.reply(view=embeds.warning(f"No snippet named `{name.lower()}`."), mention_author=False)
        await ctx.reply(view=embeds.success(f"Snippet `{name.lower()}` deleted."), mention_author=False)

    @snippet_group.command(name="list", description="List all saved snippets.")
    @checks.staff_only()
    async def snippet_list(self, ctx: commands.Context) -> None:
        await self._list(ctx)

    async def _list(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.snippet_list(ctx.guild.id)
        if not rows:
            return await ctx.reply(view=embeds.info("No snippets saved yet. Add one with `/snippet add`."), mention_author=False)
        body = "\n".join(f"`!{r['name']}`" for r in rows)
        await ctx.reply(view=embeds.build(title=f"Saved snippets", body=body), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Snippets(bot))
