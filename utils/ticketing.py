from __future__ import annotations

import time

import discord
from discord.ext import commands

import config
from utils import embeds
from utils.database import GuildConfig
from utils.emojis import e


class TicketError(Exception):
    pass


class TicketCooldownError(TicketError):
    def __init__(self, remaining_seconds: int):
        self.remaining_seconds = remaining_seconds


class NeedsReasonPicker(TicketError):
    def __init__(self, reasons: list):
        self.reasons = reasons


async def log_action(bot: commands.Bot, guild: discord.Guild, actor: discord.abc.User, action: str, detail: str = "") -> None:
    await bot.db.audit_add(guild.id, actor.id, action, detail)
    cfg = await bot.db.get_guild_config(guild.id)
    if not cfg.log_channel_id:
        return
    channel = guild.get_channel(cfg.log_channel_id)
    if not channel:
        return
    body = f"**By:** {actor.mention} (`{actor.id}`)"
    if detail:
        body += f"\n{detail}"
    view = embeds.build(title=f"{e.audit} {action}", body=body)
    try:
        await channel.send(view=view)
    except discord.HTTPException:
        pass


async def resolve_target_guild(bot: commands.Bot, user: discord.abc.User) -> tuple[discord.Guild | None, list[discord.Guild]]:
    candidates: list[discord.Guild] = []
    ready_ids = set(await bot.db.configured_guild_ids())
    for guild in bot.guilds:
        if guild.id not in ready_ids:
            continue
        if guild.get_member(user.id) is not None:
            candidates.append(guild)

    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates


class GuildPickerView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, user: discord.abc.User, guilds: list[discord.Guild]):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user

        c = embeds.container()
        c.add_item(embeds.text(f"## {e.mail} Which server?\nYou share more than one RiV Mail server with me - pick one to open a ticket in."))
        c.add_item(embeds.sep())

        row = discord.ui.ActionRow()
        select = discord.ui.Select(
            placeholder="Choose a server",
            options=[discord.SelectOption(label=g.name, value=str(g.id)) for g in guilds[:25]],
        )
        select.callback = self._on_pick
        row.add_item(select)
        c.add_item(row)
        self.add_item(c)

    async def _on_pick(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(view=embeds.error("This isn't your picker."), ephemeral=True)
        guild_id = int(interaction.data["values"][0])
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await interaction.response.edit_message(view=embeds.error("That server isn't available anymore."))
        await interaction.response.edit_message(view=embeds.loading("Opening your ticket..."))
        await open_ticket_flow(self.bot, self.user, guild)


class ReasonPickerView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, user: discord.abc.User, guild: discord.Guild, reasons: list):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.guild = guild

        c = embeds.container()
        c.add_item(embeds.text(f"## {e.ticket} What do you need help with?\nPick a category for **{guild.name}**."))
        c.add_item(embeds.sep())

        row = discord.ui.ActionRow()
        select = discord.ui.Select(
            placeholder="Choose a category",
            options=[
                discord.SelectOption(label=r["label"], value=r["key"], emoji=r["emoji"] or None)
                for r in reasons[:25]
            ],
        )
        select.callback = self._on_pick
        row.add_item(select)
        c.add_item(row)
        self.add_item(c)

    async def _on_pick(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(view=embeds.error("This isn't your picker."), ephemeral=True)
        reason_key = interaction.data["values"][0]
        await interaction.response.edit_message(view=embeds.loading("Opening your ticket..."))
        try:
            ticket_row, channel = await get_or_create_ticket(self.bot, self.user, self.guild, reason_key=reason_key)
        except TicketCooldownError as exc:
            minutes = max(1, exc.remaining_seconds // 60)
            await self.user.send(view=embeds.warning(f"You need to wait **{minutes} more minute(s)** before opening a new ticket here."))
            return
        if not ticket_row:
            await self.user.send(view=embeds.error("ModMail isn't fully configured on that server yet."))


async def open_ticket_flow(bot: commands.Bot, user: discord.abc.User, guild: discord.Guild) -> None:
    try:
        ticket_row, channel = await get_or_create_ticket(bot, user, guild)
    except NeedsReasonPicker as exc:
        await user.send(view=ReasonPickerView(bot, user, guild, exc.reasons))
        return
    except TicketCooldownError as exc:
        minutes = max(1, exc.remaining_seconds // 60)
        await user.send(view=embeds.warning(f"You need to wait **{minutes} more minute(s)** before opening a new ticket here."))
        return

    if not ticket_row:
        await user.send(view=embeds.error("ModMail isn't fully configured on that server yet."))


class UserCloseButton(discord.ui.DynamicItem[discord.ui.Button], template=r"riv:uclose:(?P<ticket_id>[A-Z0-9]+)"):
    def __init__(self, ticket_id: str):
        super().__init__(
            discord.ui.Button(
                label="Close ticket",
                style=discord.ButtonStyle.danger,
                custom_id=f"riv:uclose:{ticket_id}",
            )
        )
        self.ticket_id = ticket_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match) -> "UserCloseButton":
        return cls(match["ticket_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: commands.Bot = interaction.client
        ticket = await bot.db.get_ticket(self.ticket_id)
        if not ticket or ticket["status"] != "open":
            return await interaction.response.send_message(view=embeds.error("This ticket is already closed."), ephemeral=True)

        guild = bot.get_guild(ticket["guild_id"])
        channel = guild.get_channel(ticket["channel_id"]) if guild else None
        await interaction.response.send_message(view=embeds.loading("Closing your ticket..."))
        if channel:
            cog = bot.get_cog("ModMail")
            await cog.close_ticket(channel, ticket, interaction.user)
        else:
            await bot.db.close_ticket(self.ticket_id, interaction.user.id)


async def get_or_create_ticket(
    bot: commands.Bot,
    user: discord.abc.User,
    guild: discord.Guild,
    *,
    reason_key: str | None = None,
) -> tuple[dict | None, discord.TextChannel | None]:
    cfg = await bot.db.get_guild_config(guild.id)
    if not cfg.is_ready:
        return None, None

    existing = await bot.db.get_open_ticket_for_user(user.id, guild.id)
    if existing:
        channel = guild.get_channel(existing["channel_id"])
        if channel:
            return existing, channel

    reasons = await bot.db.reason_list(guild.id)
    if reasons and not reason_key:
        raise NeedsReasonPicker(reasons)

    if cfg.ticket_cooldown_minutes:
        last_closed = await bot.db.get_last_closed_ticket(user.id, guild.id)
        if last_closed and last_closed["closed_at"]:
            elapsed = int(time.time()) - last_closed["closed_at"]
            remaining = cfg.ticket_cooldown_minutes * 60 - elapsed
            if remaining > 0:
                raise TicketCooldownError(remaining)

    reason_row = None
    if reason_key:
        reason_row = await bot.db.reason_get(guild.id, reason_key)

    category_id = reason_row["category_id"] if reason_row and reason_row["category_id"] else cfg.category_id
    staff_role_id = reason_row["staff_role_id"] if reason_row and reason_row["staff_role_id"] else cfg.staff_role_id

    category = guild.get_channel(category_id)
    staff_role = guild.get_role(staff_role_id)
    if category is None or staff_role is None:
        return None, None

    name_format = cfg.ticket_name_format or config.DEFAULT_TICKET_NAME_FORMAT
    channel_name = name_format.format(username=user.name, id=user.id, ticket_id="new")[:90]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        staff_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, embed_links=True,
            attach_files=True, read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_webhooks=True),
    }

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        topic=f"RiV Mail ticket | {user} ({user.id})",
        overwrites=overwrites,
        reason=f"RiV Mail ticket opened by {user} ({user.id})",
    )

    ticket_id = await bot.db.create_ticket(guild.id, user.id, channel.id, reason_key=reason_key)

    from cogs.modmail import TicketPanelView

    panel = TicketPanelView(bot, ticket_id, user, reason_row["label"] if reason_row else None)
    if cfg.ping_staff:
        await channel.send(content=staff_role.mention, allowed_mentions=discord.AllowedMentions(roles=True))
    await channel.send(view=panel)

    welcome = cfg.welcome_message or (
        f"Your message has been forwarded to the staff team of **{guild.name}**. "
        f"They'll reply here as soon as they can - just keep chatting in this DM."
    )
    if cfg.away_enabled and cfg.away_message:
        welcome += f"\n\n{e.away} {cfg.away_message}"

    row = discord.ui.ActionRow()
    row.add_item(UserCloseButton(ticket_id))
    user_container = embeds.container()
    user_container.add_item(embeds.text(f"## {e.ticket} Ticket opened\n{welcome}"))
    user_container.add_item(embeds.sep(divider=False))
    user_container.add_item(embeds.text(f"**Ticket ID**\n`{ticket_id}`"))
    user_container.add_item(embeds.sep(divider=False))
    user_container.add_item(row)
    user_view = embeds.Layout(user_container)

    try:
        await user.send(view=user_view)
    except discord.Forbidden:
        pass

    ticket_row = await bot.db.get_ticket(ticket_id)
    return ticket_row, channel


async def _ticket_webhook(channel: discord.TextChannel) -> discord.Webhook | None:
    try:
        hooks = await channel.webhooks()
        for hook in hooks:
            if hook.name == "RiV Mail Relay":
                return hook
        return await channel.create_webhook(name="RiV Mail Relay", reason="RiV Mail message relay")
    except discord.Forbidden:
        return None


async def relay_dm_to_channel(bot: commands.Bot, message: discord.Message, ticket_row, channel: discord.TextChannel) -> None:
    user = message.author
    content = message.content or ""
    files = [await a.to_file() for a in message.attachments] if message.attachments else []

    webhook = await _ticket_webhook(channel)
    mirror_id = None
    if webhook and (content or files):
        try:
            sent = await webhook.send(
                content=content or None,
                username=str(user)[:80],
                avatar_url=user.display_avatar.url,
                files=files,
                wait=True,
            )
            mirror_id = sent.id
        except discord.HTTPException:
            webhook = None

    if not webhook:
        view = embeds.build(title=f"{e.user} {user}", body=content or "*[no text content]*")
        sent = await channel.send(view=view)
        mirror_id = sent.id
        if files:
            await channel.send(files=files)

    await bot.db.log_message(
        ticket_row["ticket_id"], user.id, str(user), content, is_staff=False,
        source_message_id=message.id, mirror_message_id=mirror_id,
    )
    await bot.db.touch_activity(ticket_row["ticket_id"])
    try:
        await message.add_reaction("✅")
    except discord.HTTPException:
        pass


async def sync_dm_edit(bot: commands.Bot, before: discord.Message, after: discord.Message) -> None:
    row = await bot.db.find_message_by_source(before.id)
    if not row or not row["mirror_message_id"]:
        return
    ticket = await bot.db.get_ticket(row["ticket_id"])
    if not ticket:
        return
    guild = bot.get_guild(ticket["guild_id"])
    channel = guild.get_channel(ticket["channel_id"]) if guild else None
    if not channel:
        return
    webhook = await _ticket_webhook(channel)
    if not webhook:
        return
    try:
        await webhook.edit_message(row["mirror_message_id"], content=f"{after.content}\n-# (edited)")
    except discord.HTTPException:
        pass


async def sync_dm_delete(bot: commands.Bot, message: discord.Message) -> None:
    row = await bot.db.find_message_by_source(message.id)
    if not row or not row["mirror_message_id"]:
        return
    ticket = await bot.db.get_ticket(row["ticket_id"])
    if not ticket:
        return
    guild = bot.get_guild(ticket["guild_id"])
    channel = guild.get_channel(ticket["channel_id"]) if guild else None
    if not channel:
        return
    webhook = await _ticket_webhook(channel)
    if not webhook:
        return
    try:
        await webhook.edit_message(row["mirror_message_id"], content="*[message deleted]*")
    except discord.HTTPException:
        pass


async def deliver_staff_reply(
    bot: commands.Bot,
    ticket_row,
    channel: discord.TextChannel,
    staff: discord.Member,
    content: str,
    *,
    anonymous: bool,
    mirror_in_channel: bool = True,
) -> bool:
    guild = channel.guild
    user = bot.get_user(ticket_row["user_id"]) or await bot.fetch_user(ticket_row["user_id"])

    sender_label = "Staff Member" if anonymous else str(staff)
    dm_view = embeds.build(title=f"{e.reply} Reply from {guild.name}", body=f"{content}\n\n-# {sender_label}")
    delivered = True
    try:
        await user.send(view=dm_view)
    except discord.Forbidden:
        delivered = False

    if mirror_in_channel:
        note = f"By {staff} - {'anonymous' if anonymous else 'visible'}"
        if not delivered:
            note += " - delivery failed, DMs closed"
        mirror = embeds.build(title=f"{e.reply} Sent to {user}", body=f"{content}\n\n-# {note}")
        await channel.send(view=mirror)

    await bot.db.log_message(ticket_row["ticket_id"], staff.id, str(staff), content, is_staff=True)
    await bot.db.touch_activity(ticket_row["ticket_id"])
    return delivered


async def resolve_snippet_content(bot: commands.Bot, guild_id: int, text_value: str) -> str:
    if not text_value.startswith("!"):
        return text_value
    name = text_value[1:].strip()
    row = await bot.db.snippet_get(guild_id, name)
    return row["content"] if row else text_value
