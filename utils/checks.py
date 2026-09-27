from __future__ import annotations

import discord
from discord.ext import commands

import config


def is_owner(user_id: int) -> bool:
    return user_id in config.OWNER_IDS


async def is_staff(bot: commands.Bot, member: discord.Member) -> bool:
    if is_owner(member.id):
        return True
    if member.guild_permissions.administrator:
        return True
    cfg = await bot.db.get_guild_config(member.guild.id)
    if cfg.staff_role_id and any(r.id == cfg.staff_role_id for r in member.roles):
        return True
    return False


def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        return is_owner(ctx.author.id)

    return commands.check(predicate)


def staff_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False
        return await is_staff(ctx.bot, ctx.author)

    return commands.check(predicate)


def admin_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False
        if is_owner(ctx.author.id):
            return True
        return ctx.author.guild_permissions.administrator

    return commands.check(predicate)
