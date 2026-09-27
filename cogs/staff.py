from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils import checks, embeds, ticketing
from utils.emojis import e


class Staff(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="mod", fallback="help", description="Manage ModMail staff members.")
    @checks.admin_only()
    async def mod_group(self, ctx: commands.Context) -> None:
        await ctx.reply(view=embeds.info("Use `mod add`, `mod remove`, or `mod list`."), mention_author=False)

    @mod_group.command(name="add", description="Give a user the ModMail staff role.")
    @checks.admin_only()
    @app_commands.describe(user="The user to make staff")
    async def mod_add(self, ctx: commands.Context, user: discord.Member) -> None:
        cfg = await self.bot.db.get_guild_config(ctx.guild.id)
        if not cfg.staff_role_id:
            return await ctx.reply(view=embeds.error("No staff role is configured yet - run `/setup` first."), mention_author=False)
        role = ctx.guild.get_role(cfg.staff_role_id)
        if not role:
            return await ctx.reply(view=embeds.error("The configured staff role no longer exists - run `/setup` again."), mention_author=False)
        if role in user.roles:
            return await ctx.reply(view=embeds.warning(f"{user.mention} already has the staff role."), mention_author=False)
        try:
            await user.add_roles(role, reason=f"Added as ModMail staff by {ctx.author}")
        except discord.Forbidden:
            return await ctx.reply(view=embeds.error("I don't have permission to manage that role."), mention_author=False)
        await ticketing.log_action(self.bot, ctx.guild, ctx.author, "Staff added", f"{user.mention} (`{user.id}`)")
        await ctx.reply(view=embeds.success(f"Added {role.mention} to {user.mention}."), mention_author=False)

    @mod_group.command(name="remove", description="Remove the ModMail staff role from a user.")
    @checks.admin_only()
    @app_commands.describe(user="The user to remove staff from")
    async def mod_remove(self, ctx: commands.Context, user: discord.Member) -> None:
        cfg = await self.bot.db.get_guild_config(ctx.guild.id)
        if not cfg.staff_role_id:
            return await ctx.reply(view=embeds.error("No staff role is configured yet - run `/setup` first."), mention_author=False)
        role = ctx.guild.get_role(cfg.staff_role_id)
        if not role or role not in user.roles:
            return await ctx.reply(view=embeds.warning(f"{user.mention} doesn't have the staff role."), mention_author=False)
        try:
            await user.remove_roles(role, reason=f"Removed as ModMail staff by {ctx.author}")
        except discord.Forbidden:
            return await ctx.reply(view=embeds.error("I don't have permission to manage that role."), mention_author=False)
        await ticketing.log_action(self.bot, ctx.guild, ctx.author, "Staff removed", f"{user.mention} (`{user.id}`)")
        await ctx.reply(view=embeds.success(f"Removed {role.mention} from {user.mention}."), mention_author=False)

    @mod_group.command(name="list", description="List everyone with the ModMail staff role.")
    @checks.staff_only()
    async def mod_list(self, ctx: commands.Context) -> None:
        cfg = await self.bot.db.get_guild_config(ctx.guild.id)
        if not cfg.staff_role_id:
            return await ctx.reply(view=embeds.error("No staff role is configured yet - run `/setup` first."), mention_author=False)
        role = ctx.guild.get_role(cfg.staff_role_id)
        if not role:
            return await ctx.reply(view=embeds.error("The configured staff role no longer exists - run `/setup` again."), mention_author=False)
        members = role.members
        body = "\n".join(f"{m.mention} (`{m.id}`)" for m in members) or "No one has the staff role yet."
        await ctx.reply(view=embeds.build(title=f"{e.staff} Staff members", body=body), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Staff(bot))
