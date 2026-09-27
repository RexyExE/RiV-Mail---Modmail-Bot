from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils import checks, embeds
from utils.emojis import e


class Reasons(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="reasons", description="Manage ticket category options users pick from when opening a ticket.", invoke_without_command=True)
    @checks.admin_only()
    async def reasons_group(self, ctx: commands.Context) -> None:
        await self._list(ctx)

    @reasons_group.command(name="add", description="Add a ticket category option.")
    @checks.admin_only()
    @app_commands.describe(
        key="Short unique id, e.g. support",
        label="What users see, e.g. General Support",
        emoji="Optional emoji shown in the picker",
        category="Route tickets with this reason into a specific category (optional)",
        staff_role="Route tickets with this reason to a specific staff role (optional)",
    )
    async def reasons_add(
        self, ctx: commands.Context, key: str, label: str,
        emoji: str | None = None,
        category: discord.CategoryChannel | None = None,
        staff_role: discord.Role | None = None,
    ) -> None:
        await self.bot.db.reason_add(
            ctx.guild.id, key, label, emoji,
            category.id if category else None,
            staff_role.id if staff_role else None,
        )
        await ctx.reply(view=embeds.success(f"Category `{key.lower()}` saved."), mention_author=False)

    @reasons_group.command(name="remove", description="Remove a ticket category option.")
    @checks.admin_only()
    @app_commands.describe(key="The category id to remove")
    async def reasons_remove(self, ctx: commands.Context, key: str) -> None:
        removed = await self.bot.db.reason_remove(ctx.guild.id, key)
        if not removed:
            return await ctx.reply(view=embeds.warning(f"No category named `{key.lower()}`."), mention_author=False)
        await ctx.reply(view=embeds.success(f"Category `{key.lower()}` removed."), mention_author=False)

    @reasons_group.command(name="list", description="List every ticket category option.")
    @checks.admin_only()
    async def reasons_list(self, ctx: commands.Context) -> None:
        await self._list(ctx)

    async def _list(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.reason_list(ctx.guild.id)
        if not rows:
            return await ctx.reply(
                view=embeds.info("No custom categories set - users go straight into the default ticket category. Add one with `/reasons add`."),
                mention_author=False,
            )
        lines = []
        for r in rows:
            line = f"{r['emoji'] or e.dot} **{r['label']}** (`{r['key']}`)"
            if r["category_id"]:
                line += f"\n{e.arrow} <#{r['category_id']}>"
            if r["staff_role_id"]:
                line += f"\n{e.arrow} <@&{r['staff_role_id']}>"
            lines.append(line)
        await ctx.reply(view=embeds.build(title=f"Ticket categories", body="\n\n".join(lines)), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reasons(bot))
