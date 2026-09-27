from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils import checks, embeds, ticketing
from utils.emojis import e


class Blacklist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="blacklist", description="Manage the ModMail blacklist.", invoke_without_command=True)
    @checks.admin_only()
    async def blacklist_group(self, ctx: commands.Context) -> None:
        await self._list(ctx)

    @blacklist_group.command(name="add", description="Block a user from opening ModMail tickets.")
    @checks.admin_only()
    @app_commands.describe(user="The user to blacklist", reason="Why they're being blacklisted")
    async def blacklist_add(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided") -> None:
        existing = await self.bot.db.is_blacklisted(ctx.guild.id, user.id)
        if existing:
            return await ctx.reply(view=embeds.warning(f"{user} is already blacklisted."), mention_author=False)
        await self.bot.db.blacklist_add(ctx.guild.id, user.id, reason, ctx.author.id)
        await ticketing.log_action(self.bot, ctx.guild, ctx.author, "User blacklisted", f"{user} (`{user.id}`) - {reason}")
        await ctx.reply(
            view=embeds.build(
                title=f"{e.success} User blacklisted",
                fields=[("User", f"{user} (`{user.id}`)"), ("Reason", reason)],
                colour=embeds.ERROR,
            ),
            mention_author=False,
        )

    @blacklist_group.command(name="remove", description="Unblock a user from ModMail.")
    @checks.admin_only()
    @app_commands.describe(user="The user to unblacklist")
    async def blacklist_remove(self, ctx: commands.Context, user: discord.User) -> None:
        removed = await self.bot.db.blacklist_remove(ctx.guild.id, user.id)
        if not removed:
            return await ctx.reply(view=embeds.warning(f"{user} isn't blacklisted."), mention_author=False)
        await ticketing.log_action(self.bot, ctx.guild, ctx.author, "User unblacklisted", f"{user} (`{user.id}`)")
        await ctx.reply(view=embeds.success(f"{user} can use ModMail again."), mention_author=False)

    @blacklist_group.command(name="list", description="View everyone blacklisted from ModMail.")
    @checks.admin_only()
    async def blacklist_list(self, ctx: commands.Context) -> None:
        await self._list(ctx)

    async def _list(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.blacklist_list(ctx.guild.id)
        if not rows:
            return await ctx.reply(view=embeds.info("The blacklist is empty."), mention_author=False)
        body = "\n".join(f"{e.dot} <@{r['user_id']}> (`{r['user_id']}`) - {r['reason']}" for r in rows)
        await ctx.reply(view=embeds.build(title=f"{e.error} Blacklisted users", body=body), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Blacklist(bot))
