from __future__ import annotations

import asyncio
import re
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import checks, embeds, ticketing
from utils.emojis import e
from utils.transcript import generate_transcript

_DURATION_RE = re.compile(r"(\d+)\s*(d|h|m)")

PRIORITY_COLOUR = {
    "low": embeds.ACCENT,
    "normal": embeds.ACCENT,
    "high": embeds.WARNING,
    "urgent": embeds.ERROR,
}


def _parse_duration(text: str) -> int | None:
    matches = _DURATION_RE.findall(text.lower())
    if not matches:
        return None
    total = 0
    for amount, unit in matches:
        amount = int(amount)
        if unit == "d":
            total += amount * 86400
        elif unit == "h":
            total += amount * 3600
        elif unit == "m":
            total += amount * 60
    return total or None


class TicketPanelView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, ticket_id: str | None = None, user: discord.abc.User | None = None, reason_label: str | None = None):
        super().__init__(timeout=None)
        self.bot = bot

        c = embeds.container()
        header = f"### New ticket"
        if user:
            header += f"\nOpened by {user.mention} (`{user.id}`)"
        c.add_item(embeds.text(header))
        c.add_item(embeds.sep(divider=False))

        info_lines = []
        if ticket_id:
            info_lines.append(f"**Ticket ID**\n`{ticket_id}`")
        if reason_label:
            info_lines.append(f"**Category**\n{reason_label}")
        if info_lines:
            c.add_item(embeds.text("\n".join(info_lines)))
        c.add_item(embeds.sep())

        row = discord.ui.ActionRow()

        claim_btn = discord.ui.Button(label="Claim", style=discord.ButtonStyle.primary, custom_id="riv:claim")
        claim_btn.callback = self.on_claim
        row.add_item(claim_btn)

        reply_btn = discord.ui.Button(label="Quick Reply", style=discord.ButtonStyle.secondary, custom_id="riv:quickreply")
        reply_btn.callback = self.on_quick_reply
        row.add_item(reply_btn)

        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="riv:close")
        close_btn.callback = self.on_close
        row.add_item(close_btn)

        c.add_item(row)
        self.add_item(c)

    async def _member_and_ticket(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member) or not await checks.is_staff(self.bot, member):
            await interaction.response.send_message(view=embeds.error("Only staff can use this."), ephemeral=True)
            return None, None
        ticket = await self.bot.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(view=embeds.error("This isn't an active ticket channel."), ephemeral=True)
            return None, None
        return member, ticket

    async def on_claim(self, interaction: discord.Interaction) -> None:
        member, ticket = await self._member_and_ticket(interaction)
        if not ticket:
            return
        if ticket["status"] != "open":
            return await interaction.response.send_message(view=embeds.error("This ticket is already closed."), ephemeral=True)

        await self.bot.db.set_claim(ticket["ticket_id"], member.id)
        await ticketing.log_action(self.bot, interaction.guild, member, "Ticket claimed", f"Ticket `{ticket['ticket_id']}`")
        await interaction.response.send_message(view=embeds.success(f"{member.mention} claimed this ticket."))

    async def on_quick_reply(self, interaction: discord.Interaction) -> None:
        member, ticket = await self._member_and_ticket(interaction)
        if not ticket:
            return
        if ticket["status"] != "open":
            return await interaction.response.send_message(view=embeds.error("This ticket is already closed."), ephemeral=True)
        await interaction.response.send_modal(QuickReplyModal(self.bot, ticket))

    async def on_close(self, interaction: discord.Interaction) -> None:
        member, ticket = await self._member_and_ticket(interaction)
        if not ticket:
            return
        if ticket["status"] != "open":
            return await interaction.response.send_message(view=embeds.error("This ticket is already closed."), ephemeral=True)
        await interaction.response.send_message(view=CloseConfirmView(self.bot, ticket))


class CloseConfirmView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, ticket):
        super().__init__(timeout=120)
        self.bot = bot
        self.ticket = ticket

        c = embeds.container(embeds.WARNING)
        c.add_item(embeds.text(f"### Close this ticket?"))
        c.add_item(embeds.sep(divider=False))
        c.add_item(embeds.text("A transcript will be generated and the channel deleted shortly after."))
        c.add_item(embeds.sep())

        row = discord.ui.ActionRow()
        yes = discord.ui.Button(label="Yes, close it", style=discord.ButtonStyle.danger)
        yes.callback = self.on_yes
        row.add_item(yes)
        no = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        no.callback = self.on_no
        row.add_item(no)
        c.add_item(row)
        self.add_item(c)

    async def on_yes(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=embeds.loading("Closing ticket..."))
        cog: ModMail = self.bot.get_cog("ModMail")
        await cog.close_ticket(interaction.channel, self.ticket, interaction.user)

    async def on_no(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=embeds.info("Close cancelled."))


class QuickReplyModal(discord.ui.Modal, title="Reply to ticket"):
    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=1800)

    def __init__(self, bot: commands.Bot, ticket):
        super().__init__()
        self.bot = bot
        self.ticket = ticket

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        mode = await self.bot.db.get_staff_mode(self.ticket["ticket_id"], interaction.user.id)
        await ticketing.deliver_staff_reply(
            self.bot, self.ticket, interaction.channel, interaction.user,
            str(self.message), anonymous=(mode == "anonymous"), mirror_in_channel=False,
        )
        await interaction.followup.send(view=embeds.success("Reply sent."), ephemeral=True)


class ModMail(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scheduled_closes: dict[str, asyncio.Task] = {}

    async def cog_load(self) -> None:
        self.bot.add_view(TicketPanelView(self.bot))
        self.bot.add_dynamic_items(ticketing.UserCloseButton)
        self.auto_close_loop.start()

    async def cog_unload(self) -> None:
        self.auto_close_loop.cancel()
        for task in self.scheduled_closes.values():
            task.cancel()

    @tasks.loop(minutes=15)
    async def auto_close_loop(self) -> None:
        configs = await self.bot.db.all_guild_configs()
        for cfg_row in configs:
            if not cfg_row["auto_close_hours"]:
                continue
            guild = self.bot.get_guild(cfg_row["guild_id"])
            if not guild:
                continue
            cutoff = int(time.time()) - cfg_row["auto_close_hours"] * 3600
            stale = await self.bot.db.stale_open_tickets(guild.id, cutoff)
            for ticket in stale:
                channel = guild.get_channel(ticket["channel_id"])
                if not channel:
                    await self.bot.db.close_ticket(ticket["ticket_id"], self.bot.user.id)
                    continue
                await channel.send(view=embeds.warning("This ticket has been inactive and will be closed automatically."))
                await self.close_ticket(channel, ticket, self.bot.user)

    @auto_close_loop.before_loop
    async def before_auto_close(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not self.bot.is_ready():
            return

        if isinstance(message.channel, discord.DMChannel):
            await self._handle_dm(message)
            return

        if message.guild and self.bot.user in message.mentions and message.content.strip() in (
            f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"
        ):
            return await self._send_mention_card(message)

        if message.guild and not message.content.startswith(self.bot.command_prefix_str):
            await self._handle_possible_staff_reply(message)

    async def _send_mention_card(self, message: discord.Message) -> None:
        body = (
            f"Prefix is `{self.bot.command_prefix_str}` or use `/`.\n\n"
            f"{e.dot} DM me to open a ticket\n"
            f"{e.dot} `guide` - how ModMail works\n"
            f"{e.dot} `help` - see every command"
        )
        view = embeds.build(title=f"__**Hey, I'm {message.guild.me.display_name}**__", body=body)
        await message.reply(view=view, mention_author=False)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.author.bot or not isinstance(after.channel, discord.DMChannel):
            return
        await ticketing.sync_dm_edit(self.bot, before, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not isinstance(message.channel, discord.DMChannel):
            return
        await ticketing.sync_dm_delete(self.bot, message)

    async def _handle_dm(self, message: discord.Message) -> None:
        user = message.author

        target_guild, candidates = await ticketing.resolve_target_guild(self.bot, user)

        if target_guild is None and not candidates:
            return await message.reply(
                view=embeds.warning("I couldn't find a server where ModMail is set up for you. Ask a server admin to run `/setup` first."),
                mention_author=False,
            )

        if target_guild is None:
            return await message.reply(view=ticketing.GuildPickerView(self.bot, user, candidates), mention_author=False)

        guild = target_guild
        blacklisted = await self.bot.db.is_blacklisted(guild.id, user.id)
        if blacklisted:
            return await message.reply(
                view=embeds.error(f"You're blacklisted from ModMail in **{guild.name}**.\nReason: {blacklisted['reason'] or 'No reason provided'}"),
                mention_author=False,
            )

        try:
            ticket_row, channel = await ticketing.get_or_create_ticket(self.bot, user, guild)
        except ticketing.NeedsReasonPicker as exc:
            return await message.reply(view=ticketing.ReasonPickerView(self.bot, user, guild, exc.reasons), mention_author=False)
        except ticketing.TicketCooldownError as exc:
            minutes = max(1, exc.remaining_seconds // 60)
            return await message.reply(view=embeds.warning(f"You need to wait **{minutes} more minute(s)** before opening a new ticket here."), mention_author=False)

        if not ticket_row or not channel:
            return await message.reply(
                view=embeds.error("ModMail isn't fully configured on that server yet. Please try again later."),
                mention_author=False,
            )

        await ticketing.relay_dm_to_channel(self.bot, message, ticket_row, channel)

    async def _handle_possible_staff_reply(self, message: discord.Message) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(message.channel.id)
        if not ticket or ticket["status"] != "open":
            return
        if not isinstance(message.author, discord.Member) or not await checks.is_staff(self.bot, message.author):
            return

        content = await ticketing.resolve_snippet_content(self.bot, message.guild.id, message.content)
        if not content.strip() and not message.attachments:
            return

        mode = await self.bot.db.get_staff_mode(ticket["ticket_id"], message.author.id)
        delivered = await ticketing.deliver_staff_reply(
            self.bot, ticket, message.channel, message.author,
            content, anonymous=(mode == "anonymous"), mirror_in_channel=False,
        )

        if message.attachments:
            user = self.bot.get_user(ticket["user_id"])
            if user:
                files = [await a.to_file() for a in message.attachments]
                try:
                    await user.send(files=files)
                except discord.Forbidden:
                    delivered = False

        try:
            await message.add_reaction("{e.success}" if delivered else "{e.error}")
        except discord.HTTPException:
            pass

    async def close_ticket(self, channel: discord.TextChannel, ticket, closed_by: discord.abc.User) -> None:
        guild = channel.guild
        cfg = await self.bot.db.get_guild_config(guild.id)

        self.scheduled_closes.pop(ticket["ticket_id"], None)

        file, _ = await generate_transcript(channel, ticket["ticket_id"], self.bot)

        user = self.bot.get_user(ticket["user_id"])
        if user:
            close_msg = cfg.close_message or "Your ticket has been closed. Feel free to message again if you need anything else."
            try:
                await user.send(view=embeds.info(close_msg))
                file.reset()
                await user.send(file=file)
            except discord.Forbidden:
                pass

        if cfg.transcript_channel_id:
            log_channel = guild.get_channel(cfg.transcript_channel_id)
            if log_channel:
                file.reset()
                summary = embeds.build(
                    title=f"Ticket closed | `{ticket['ticket_id']}`",
                    fields=[
                        ("User", f"<@{ticket['user_id']}> (`{ticket['user_id']}`)"),
                        ("Closed by", f"{closed_by}"),
                    ],
                )
                await log_channel.send(view=summary)
                await log_channel.send(file=file)

        await self.bot.db.close_ticket(ticket["ticket_id"], closed_by.id)
        await ticketing.log_action(self.bot, guild, closed_by, "Ticket closed", f"Ticket `{ticket['ticket_id']}`")
        await channel.send(view=embeds.warning("This channel will be deleted in 5 seconds."))
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"RiV Mail ticket closed by {closed_by}")
        except discord.HTTPException:
            pass

    @commands.hybrid_command(name="close", description="Close this ModMail ticket, optionally after a delay like 1h or 30m.")
    @checks.staff_only()
    @app_commands.describe(when="Optional delay before closing, e.g. 30m or 1h")
    async def close_cmd(self, ctx: commands.Context, *, when: str | None = None) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket or ticket["status"] != "open":
            return await ctx.reply(view=embeds.error("This isn't an open ticket channel."), mention_author=False)

        if when:
            seconds = _parse_duration(when)
            if not seconds:
                return await ctx.reply(view=embeds.error("Couldn't parse that delay. Try something like `30m`, `1h`, or `1h30m`."), mention_author=False)

            async def _delayed_close():
                await asyncio.sleep(seconds)
                fresh = await self.bot.db.get_ticket(ticket["ticket_id"])
                if fresh and fresh["status"] == "open":
                    await self.close_ticket(ctx.channel, fresh, ctx.author)

            task = asyncio.create_task(_delayed_close())
            self.scheduled_closes[ticket["ticket_id"]] = task
            return await ctx.reply(view=embeds.success(f"This ticket will close in **{when}**. Use `closecancel` to stop it."), mention_author=False)

        await ctx.reply(view=CloseConfirmView(self.bot, ticket), mention_author=False)

    @commands.hybrid_command(name="closecancel", description="Cancel a scheduled close on this ticket.")
    @checks.staff_only()
    async def closecancel_cmd(self, ctx: commands.Context) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(view=embeds.error("This isn't a ticket channel."), mention_author=False)
        task = self.scheduled_closes.pop(ticket["ticket_id"], None)
        if not task:
            return await ctx.reply(view=embeds.warning("No scheduled close on this ticket."), mention_author=False)
        task.cancel()
        await ctx.reply(view=embeds.success("Scheduled close cancelled."), mention_author=False)

    @commands.hybrid_command(name="claim", description="Claim this ModMail ticket.")
    @checks.staff_only()
    async def claim_cmd(self, ctx: commands.Context) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket or ticket["status"] != "open":
            return await ctx.reply(view=embeds.error("This isn't an open ticket channel."), mention_author=False)
        await self.bot.db.set_claim(ticket["ticket_id"], ctx.author.id)
        await ticketing.log_action(self.bot, ctx.guild, ctx.author, "Ticket claimed", f"Ticket `{ticket['ticket_id']}`")
        await ctx.reply(view=embeds.success(f"{ctx.author.mention} claimed this ticket."), mention_author=False)

    @commands.hybrid_command(name="unclaim", description="Unclaim this ModMail ticket.")
    @checks.staff_only()
    async def unclaim_cmd(self, ctx: commands.Context) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket or ticket["status"] != "open":
            return await ctx.reply(view=embeds.error("This isn't an open ticket channel."), mention_author=False)
        await self.bot.db.set_claim(ticket["ticket_id"], None)
        await ctx.reply(view=embeds.success("Ticket unclaimed."), mention_author=False)

    @commands.hybrid_command(name="delete", description="Permanently delete this ticket channel (owner only).")
    @checks.owner_only()
    async def delete_cmd(self, ctx: commands.Context) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(view=embeds.error("This isn't a ticket channel."), mention_author=False)
        await ctx.reply(view=embeds.warning("Deleting this channel in 3 seconds..."), mention_author=False)
        await asyncio.sleep(3)
        try:
            await ctx.channel.delete(reason=f"RiV Mail ticket force-deleted by {ctx.author}")
        except discord.HTTPException:
            pass

    @commands.hybrid_command(name="rename", description="Rename this ticket channel.")
    @checks.staff_only()
    @app_commands.describe(name="New channel name")
    async def rename_cmd(self, ctx: commands.Context, *, name: str) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(view=embeds.error("This isn't a ticket channel."), mention_author=False)
        try:
            await ctx.channel.edit(name=name[:90], reason=f"Renamed by {ctx.author}")
        except discord.HTTPException as exc:
            return await ctx.reply(view=embeds.error(f"Couldn't rename channel: {exc}"), mention_author=False)
        await ctx.reply(view=embeds.success(f"Channel renamed to **{name}**."), mention_author=False)

    @commands.hybrid_command(name="transcript", description="Generate a transcript of this ticket.")
    @checks.staff_only()
    async def transcript_cmd(self, ctx: commands.Context) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(view=embeds.error("This isn't a ticket channel."), mention_author=False)
        await ctx.defer()
        file, _ = await generate_transcript(ctx.channel, ticket["ticket_id"], self.bot)
        await ctx.reply(view=embeds.success(f"Transcript for `{ticket['ticket_id']}` generated."), mention_author=False)
        await ctx.channel.send(file=file)

    @commands.hybrid_command(name="priority", description="Set this ticket's priority.")
    @checks.staff_only()
    @app_commands.choices(level=[
        app_commands.Choice(name="Low", value="low"),
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="High", value="high"),
        app_commands.Choice(name="Urgent", value="urgent"),
    ])
    async def priority_cmd(self, ctx: commands.Context, level: str) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(view=embeds.error("This isn't a ticket channel."), mention_author=False)
        await self.bot.db.set_priority(ticket["ticket_id"], level)
        await ctx.reply(
            view=embeds.build(title=f"Priority set to {level.title()}", colour=PRIORITY_COLOUR.get(level, embeds.ACCENT)),
            mention_author=False,
        )

    @commands.hybrid_command(name="note", description="Leave an internal note on this ticket (not visible to the user).")
    @checks.staff_only()
    @app_commands.describe(content="Note content")
    async def note_cmd(self, ctx: commands.Context, *, content: str) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(view=embeds.error("This isn't a ticket channel."), mention_author=False)
        await self.bot.db.note_add(ticket["ticket_id"], ctx.author.id, content)
        await ctx.reply(
            view=embeds.build(title=f"Internal note", body=f"{content}\n\n-# By {ctx.author}", colour=embeds.WARNING),
            mention_author=False,
        )

    @commands.hybrid_command(name="notes", description="View every internal note on this ticket.")
    @checks.staff_only()
    async def notes_cmd(self, ctx: commands.Context) -> None:
        ticket = await self.bot.db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(view=embeds.error("This isn't a ticket channel."), mention_author=False)
        rows = await self.bot.db.note_list(ticket["ticket_id"])
        if not rows:
            return await ctx.reply(view=embeds.info("No notes on this ticket yet."), mention_author=False)
        body = "\n\n".join(f"{r['content']}\n-# By <@{r['staff_id']}>" for r in rows)
        await ctx.reply(view=embeds.build(title=f"Notes", body=body, colour=embeds.WARNING), mention_author=False)

    @commands.hybrid_command(name="history", description="View a user's past ModMail tickets in this server.")
    @checks.staff_only()
    @app_commands.describe(user="The user to look up")
    async def history_cmd(self, ctx: commands.Context, user: discord.User) -> None:
        rows = await self.bot.db.user_ticket_history(ctx.guild.id, user.id)
        if not rows:
            return await ctx.reply(view=embeds.info(f"{user} has no ModMail history here."), mention_author=False)
        lines = []
        for r in rows[:15]:
            status_icon = e.success if r["status"] == "open" else e.dot
            lines.append(f"{status_icon} `{r['ticket_id']}` - {r['status']} - <t:{r['created_at']}:R>")
        await ctx.reply(
            view=embeds.build(title=f"History for {user}", body="\n".join(lines), fields=[("Total tickets", str(len(rows)))]),
            mention_author=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModMail(bot))
