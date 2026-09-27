from __future__ import annotations

import time

import discord
from discord.ext import commands

import config
from utils import embeds
from utils.emojis import e

HELP_PAGES = {
    "general": {
        "label": "General",
        "body": (
            f"{e.dot} `!ping` - Latency\n"
            f"{e.dot} `!guide` - How ModMail works\n"
            f"{e.dot} `!stats` - Ticket stats"
        ),
    },
    "staff": {
        "label": "Staff",
        "body": (
            f"{e.dot} `!reply <message>` - Reply to the user\n"
            f"{e.dot} `!areply <message>` - Reply anonymously\n"
            f"{e.dot} `!mode <normal|anonymous>` - Default reply mode\n"
            f"{e.dot} `!claim` / `!unclaim` - Claim or release a ticket\n"
            f"{e.dot} `!close [1h|30m]` - Close now or on a delay\n"
            f"{e.dot} `!closecancel` - Cancel a scheduled close\n"
            f"{e.dot} `!priority <level>` - Set ticket priority\n"
            f"{e.dot} `!note <text>` / `notes` - Internal ticket notes\n"
            f"{e.dot} `!transcript` - Generate a transcript\n"
            f"{e.dot} `!rename <name>` - Rename this ticket channel\n"
            f"{e.dot} `!history <user>` - Past tickets for a user\n"
            f"{e.dot} `!snippet add/remove/list` - Canned replies"
        ),
    },
    "admin": {
        "label": "Admin",
        "body": (
            f"{e.dot} `!setup` / `!config` - Configure RiV Mail\n"
            f"{e.dot} `!reasons add/remove/list` - Ticket category routing\n"
            f"{e.dot} `!mod add/remove/list` - Manage staff\n"
            f"{e.dot} `!blacklist add/remove/list` - Manage the blacklist"
        ),
    },
    "owner": {
        "label": "Owner",
        "body": (
            f"{e.dot} `delete` - Force-delete a ticket channel\n"
            f"{e.dot} `reload` - Reload the bot\n"
            f"{e.dot} `syncemojis` - Re-run the emoji uploader"
        ),
    },
}


class HelpView(discord.ui.LayoutView):
    def __init__(self, page: str = "general"):
        super().__init__(timeout=180)
        self.page = page
        self.render()

    def render(self) -> "HelpView":
        self.clear_items()
        data = HELP_PAGES[self.page]
        c = embeds.container()
        c.add_item(embeds.text(f"### {config.BOT_NAME} commands\n__**{data['label']}**__"))
        c.add_item(embeds.sep())
        c.add_item(embeds.text(data["body"]))
        c.add_item(embeds.sep(divider=False))

        row = discord.ui.ActionRow()
        select = discord.ui.Select(
            placeholder="Choose a category",
            options=[
                discord.SelectOption(label=v["label"], value=k, default=(k == self.page))
                for k, v in HELP_PAGES.items()
            ],
        )
        select.callback = self._on_select
        row.add_item(select)
        c.add_item(row)
        self.add_item(c)
        return self

    async def _on_select(self, interaction: discord.Interaction) -> None:
        self.page = interaction.data["values"][0]
        await interaction.response.edit_message(view=self.render())


class StatsView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.page = 0
        self.pages = ["overview", "leaderboard"]

    async def build(self) -> "StatsView":
        self.clear_items()
        c = embeds.container()

        if self.pages[self.page] == "overview":
            stats = await self.bot.db.guild_ticket_stats(self.guild.id)
            body = (
                f"**Open tickets:** {stats['open']}\n"
                f"**Closed tickets:** {stats['closed']}\n"
                f"**Total tickets:** {stats['total']}\n"
                f"**Opened today:** {stats['today']}\n"
                f"**Opened this week:** {stats['this_week']}"
            )
            c.add_item(embeds.text(f"## {e.stats} ModMail stats\n**Overview**"))
            c.add_item(embeds.sep())
            c.add_item(embeds.text(body))
        else:
            rows = await self.bot.db.staff_leaderboard(self.guild.id)
            if not rows:
                body = "No staff activity recorded yet."
            else:
                lines = []
                for r in rows:
                    lines.append(f"{e.staff} <@{r['staff_id']}> - {e.claim} {r['claims']} claims, {e.close} {r['closes']} closes")
                body = "\n".join(lines)
            c.add_item(embeds.text(f"### ModMail stats\n**Staff leaderboard**"))
            c.add_item(embeds.sep())
            c.add_item(embeds.text(body))

        c.add_item(embeds.sep(divider=False))
        row = discord.ui.ActionRow()
        prev_btn = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
        prev_btn.callback = self._on_prev
        row.add_item(prev_btn)
        next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, disabled=(self.page == len(self.pages) - 1))
        next_btn.callback = self._on_next
        row.add_item(next_btn)
        c.add_item(row)

        self.add_item(c)
        return self

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(view=await self.build())

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        await interaction.response.edit_message(view=await self.build())


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Check the bot's latency.")
    async def ping_cmd(self, ctx: commands.Context) -> None:
        start = time.perf_counter()
        msg = await ctx.reply(view=embeds.loading("Pinging..."), mention_author=False)
        rtt = (time.perf_counter() - start) * 1000
        body = f"**Websocket:** {round(self.bot.latency * 1000)}ms\n**Response:** {round(rtt)}ms"
        await msg.edit(view=embeds.build(title=f"{e.ping} Pong!", body=body))

    @commands.hybrid_command(name="stats", description="View ModMail ticket stats for this server.")
    async def stats_cmd(self, ctx: commands.Context) -> None:
        view = await StatsView(self.bot, ctx.guild).build()
        await ctx.reply(view=view, mention_author=False)

    @commands.hybrid_command(name="guide", description="How to contact the staff team.")
    async def guide_cmd(self, ctx: commands.Context) -> None:
        body = (
            "**Step 1 - Send a DM**\nSend this bot a direct message with your question or issue.\n\n"
            "**Step 2 - Ticket created**\nA private ticket is opened and the staff team is notified.\n\n"
            "**Step 3 - Conversation**\nKeep chatting in this DM - staff replies arrive here automatically."
        )
        await ctx.reply(view=embeds.build(title=f"{e.guide} Contacting staff", body=body), mention_author=False)

    @commands.hybrid_command(name="help", description="View every RiV Mail command.")
    async def help_cmd(self, ctx: commands.Context) -> None:
        await ctx.reply(view=HelpView(), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
