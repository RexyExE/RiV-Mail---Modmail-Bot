from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils import checks, embeds, ticketing


class Reply(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _reply(self, ctx: commands.Context, content: str, anonymous: bool) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket or ticket["status"] != "open":
            return await ctx.reply(view=embeds.error("This isn't an open ticket channel."), mention_author=False)

        content = await ticketing.resolve_snippet_content(self.bot, ctx.guild.id, content)
        delivered = await ticketing.deliver_staff_reply(
            self.bot, ticket, ctx.channel, ctx.author, content, anonymous=anonymous
        )
        if not delivered:
            await ctx.reply(view=embeds.warning("Sent, but the user's DMs are closed so they may not have received it."), mention_author=False)

    @commands.hybrid_command(name="reply", description="Reply to the user in this ticket.")
    @checks.staff_only()
    @app_commands.describe(message="Your reply, or !snippetname to send a saved snippet")
    async def reply_cmd(self, ctx: commands.Context, *, message: str) -> None:
        await self._reply(ctx, message, anonymous=False)

    @commands.hybrid_command(name="areply", description="Reply to the user anonymously (shown as 'Staff Member').")
    @checks.staff_only()
    @app_commands.describe(message="Your reply, or !snippetname to send a saved snippet")
    async def areply_cmd(self, ctx: commands.Context, *, message: str) -> None:
        await self._reply(ctx, message, anonymous=True)

    @commands.hybrid_command(name="mode", description="Set your default reply mode for this ticket (used when you just type in the channel).")
    @checks.staff_only()
    @app_commands.describe(mode="normal shows your name, anonymous shows 'Staff Member'")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="Anonymous", value="anonymous"),
    ])
    async def mode_cmd(self, ctx: commands.Context, mode: str) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket or ticket["status"] != "open":
            return await ctx.reply(view=embeds.error("This isn't an open ticket channel."), mention_author=False)
        await self.bot.db.set_staff_mode(ticket["ticket_id"], ctx.author.id, mode)
        await ctx.reply(view=embeds.success(f"Your reply mode in this ticket is now **{mode}**."), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reply(bot))
