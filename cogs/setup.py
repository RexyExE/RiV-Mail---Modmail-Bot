from __future__ import annotations

import discord
from discord.ext import commands

from utils import checks, embeds
from utils.database import GuildConfig
from utils.emojis import e


class TicketFormatModal(discord.ui.Modal, title="Ticket channel name format"):
    fmt = discord.ui.TextInput(
        label="Format",
        placeholder="ticket-{username}",
        default="ticket-{username}",
        max_length=80,
    )

    def __init__(self, wizard: "SetupWizard"):
        super().__init__()
        self.wizard = wizard
        self.fmt.default = wizard.pending.ticket_name_format or "ticket-{username}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.wizard.pending.ticket_name_format = str(self.fmt)
        await interaction.response.edit_message(view=self.wizard.render())


class AdvancedSettingsModal(discord.ui.Modal, title="Advanced settings"):
    auto_close = discord.ui.TextInput(label="Auto-close after inactivity (hours, 0 = off)", required=False, max_length=4)
    cooldown = discord.ui.TextInput(label="Cooldown before reopening (minutes, 0 = off)", required=False, max_length=4)
    away_message = discord.ui.TextInput(label="Away message (blank = disabled)", style=discord.TextStyle.paragraph, required=False, max_length=300)

    def __init__(self, wizard: "SetupWizard"):
        super().__init__()
        self.wizard = wizard
        self.auto_close.default = str(wizard.pending.auto_close_hours or 0)
        self.cooldown.default = str(wizard.pending.ticket_cooldown_minutes or 0)
        self.away_message.default = wizard.pending.away_message or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.wizard.pending.auto_close_hours = max(0, int(str(self.auto_close) or 0))
            self.wizard.pending.ticket_cooldown_minutes = max(0, int(str(self.cooldown) or 0))
        except ValueError:
            return await interaction.response.send_message(view=embeds.error("Auto-close and cooldown must be whole numbers."), ephemeral=True)
        self.wizard.pending.away_message = str(self.away_message) or None
        self.wizard.pending.away_enabled = bool(self.wizard.pending.away_message)
        await interaction.response.edit_message(view=self.wizard.render())


class SetupWizard(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, author_id: int, cfg: GuildConfig):
        super().__init__(timeout=300)
        self.bot = bot
        self.author_id = author_id
        self.pending = cfg
        self.render()

    def _status_line(self, ok: bool, label: str, value: str | None) -> str:
        icon = e.success if ok else e.warning
        return f"{icon} **{label}:** {value if value else 'Not set'}"

    def render(self) -> "SetupWizard":
        self.clear_items()
        c = embeds.container()
        c.add_item(embeds.text(f"__**RiV Mail setup**__"))
        c.add_item(embeds.sep(divider=False))
        c.add_item(embeds.text(
            self._status_line(bool(self.pending.staff_role_id), "Staff role", f"<@&{self.pending.staff_role_id}>" if self.pending.staff_role_id else None) + "\n" +
            self._status_line(bool(self.pending.category_id), "Ticket category", f"<#{self.pending.category_id}>" if self.pending.category_id else None) + "\n" +
            self._status_line(bool(self.pending.log_channel_id), "Log channel (optional)", f"<#{self.pending.log_channel_id}>" if self.pending.log_channel_id else None) + "\n" +
            self._status_line(bool(self.pending.transcript_channel_id), "Transcript channel (optional)", f"<#{self.pending.transcript_channel_id}>" if self.pending.transcript_channel_id else None) + "\n" +
            self._status_line(True, "Ticket name format", self.pending.ticket_name_format or "ticket-{username}") + "\n" +
            self._status_line(True, "Ping staff role on new ticket", "Yes" if self.pending.ping_staff else "No") + "\n" +
            self._status_line(True, "Auto-close after", f"{self.pending.auto_close_hours}h" if self.pending.auto_close_hours else "Off") + "\n" +
            self._status_line(True, "Reopen cooldown", f"{self.pending.ticket_cooldown_minutes}m" if self.pending.ticket_cooldown_minutes else "Off") + "\n" +
            self._status_line(True, "Away mode", "On" if self.pending.away_enabled else "Off")
        ))
        c.add_item(embeds.sep())

        role_row = discord.ui.ActionRow()
        role_select = discord.ui.RoleSelect(placeholder="Select the staff role")
        role_select.callback = self._on_role
        role_row.add_item(role_select)
        c.add_item(role_row)

        cat_row = discord.ui.ActionRow()
        cat_select = discord.ui.ChannelSelect(placeholder="Select the ticket category", channel_types=[discord.ChannelType.category])
        cat_select.callback = self._on_category
        cat_row.add_item(cat_select)
        c.add_item(cat_row)

        log_row = discord.ui.ActionRow()
        log_select = discord.ui.ChannelSelect(placeholder="Select the log channel (optional)", channel_types=[discord.ChannelType.text])
        log_select.callback = self._on_log
        log_row.add_item(log_select)
        c.add_item(log_row)

        transcript_row = discord.ui.ActionRow()
        transcript_select = discord.ui.ChannelSelect(placeholder="Select the transcript channel (optional)", channel_types=[discord.ChannelType.text])
        transcript_select.callback = self._on_transcript
        transcript_row.add_item(transcript_select)
        c.add_item(transcript_row)

        button_row = discord.ui.ActionRow()

        fmt_btn = discord.ui.Button(label="Name format", style=discord.ButtonStyle.secondary)
        fmt_btn.callback = self._on_format
        button_row.add_item(fmt_btn)

        advanced_btn = discord.ui.Button(label="Advanced", style=discord.ButtonStyle.secondary)
        advanced_btn.callback = self._on_advanced
        button_row.add_item(advanced_btn)

        ping_btn = discord.ui.Button(
            label=f"Ping staff: {'On' if self.pending.ping_staff else 'Off'}",
            style=discord.ButtonStyle.secondary,
        )
        ping_btn.callback = self._on_toggle_ping
        button_row.add_item(ping_btn)

        save_btn = discord.ui.Button(label="Save", style=discord.ButtonStyle.success)
        save_btn.callback = self._on_save
        button_row.add_item(save_btn)

        c.add_item(button_row)
        self.add_item(c)
        return self

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(view=embeds.error("Only the person who ran `/setup` can use this."), ephemeral=True)
            return False
        return True

    async def _on_role(self, interaction: discord.Interaction) -> None:
        self.pending.staff_role_id = int(interaction.data["values"][0])
        await interaction.response.edit_message(view=self.render())

    async def _on_category(self, interaction: discord.Interaction) -> None:
        self.pending.category_id = int(interaction.data["values"][0])
        await interaction.response.edit_message(view=self.render())

    async def _on_log(self, interaction: discord.Interaction) -> None:
        self.pending.log_channel_id = int(interaction.data["values"][0])
        await interaction.response.edit_message(view=self.render())

    async def _on_transcript(self, interaction: discord.Interaction) -> None:
        self.pending.transcript_channel_id = int(interaction.data["values"][0])
        await interaction.response.edit_message(view=self.render())

    async def _on_format(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TicketFormatModal(self))

    async def _on_advanced(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AdvancedSettingsModal(self))

    async def _on_toggle_ping(self, interaction: discord.Interaction) -> None:
        self.pending.ping_staff = not self.pending.ping_staff
        await interaction.response.edit_message(view=self.render())

    async def _on_save(self, interaction: discord.Interaction) -> None:
        if not self.pending.staff_role_id or not self.pending.category_id:
            return await interaction.response.send_message(
                view=embeds.error("A staff role and ticket category are required before saving."), ephemeral=True
            )
        self.pending.setup_complete = True
        await self.bot.db.upsert_guild_config(self.pending)
        await interaction.response.edit_message(view=embeds.success("RiV Mail is set up. DM the bot to test it out!"))


class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="setup", description="Configure RiV Mail for this server.")
    @checks.admin_only()
    async def setup_cmd(self, ctx: commands.Context) -> None:
        cfg = await self.bot.db.get_guild_config(ctx.guild.id)
        wizard = SetupWizard(self.bot, ctx.author.id, cfg)
        await ctx.reply(view=wizard, mention_author=False)

    @commands.hybrid_command(name="config", description="View RiV Mail's current configuration for this server.")
    @checks.admin_only()
    async def config_cmd(self, ctx: commands.Context) -> None:
        cfg = await self.bot.db.get_guild_config(ctx.guild.id)
        body = (
            f"**Staff role:** {f'<@&{cfg.staff_role_id}>' if cfg.staff_role_id else 'Not set'}\n"
            f"**Category:** {f'<#{cfg.category_id}>' if cfg.category_id else 'Not set'}\n"
            f"**Log channel:** {f'<#{cfg.log_channel_id}>' if cfg.log_channel_id else 'Not set'}\n"
            f"**Transcript channel:** {f'<#{cfg.transcript_channel_id}>' if cfg.transcript_channel_id else 'Not set'}\n"
            f"**Ticket name format:** `{cfg.ticket_name_format or 'ticket-{username}'}`\n"
            f"**Ping staff on new ticket:** {'Yes' if cfg.ping_staff else 'No'}\n"
            f"**Auto-close after:** {f'{cfg.auto_close_hours}h' if cfg.auto_close_hours else 'Off'}\n"
            f"**Reopen cooldown:** {f'{cfg.ticket_cooldown_minutes}m' if cfg.ticket_cooldown_minutes else 'Off'}\n"
            f"**Away mode:** {'On' if cfg.away_enabled else 'Off'}\n"
            f"**Ready:** {e.success if cfg.is_ready else e.error}"
        )
        await ctx.reply(view=embeds.build(title=f"__**RiV Mail configuration**__", body=body), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Setup(bot))
