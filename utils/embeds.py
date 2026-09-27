from __future__ import annotations

import discord
from discord import ui

import config
from utils.emojis import e


def _colour(hex_str: str) -> discord.Colour:
    return discord.Colour(int(hex_str.lstrip("#"), 16))


ACCENT = _colour(config.ACCENT_COLOR)
ERROR = _colour(config.ERROR_COLOR)
SUCCESS = _colour(config.SUCCESS_COLOR)
WARNING = _colour(config.WARNING_COLOR)


class Layout(ui.LayoutView):
    def __init__(self, container: ui.Container, *, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.add_item(container)


def container(colour: discord.Colour = ACCENT) -> ui.Container:
    return ui.Container(accent_colour=colour)


def text(content: str) -> ui.TextDisplay:
    return ui.TextDisplay(content)


def sep(*, divider: bool = True, large: bool = False) -> ui.Separator:
    return ui.Separator(
        spacing=discord.SeparatorSpacing.large if large else discord.SeparatorSpacing.small,
        visible=divider,
    )


def section(header: str, thumbnail_url: str | None = None) -> ui.Section:
    sec = ui.Section(ui.TextDisplay(header))
    if thumbnail_url:
        sec.accessory = ui.Thumbnail(thumbnail_url)
    return sec


def _simple(colour: discord.Colour, content: str) -> Layout:
    c = container(colour)
    c.add_item(text(content))
    return Layout(c)


def success(message: str) -> Layout:
    return _simple(SUCCESS, f"{e.success} {message}")


def error(message: str) -> Layout:
    return _simple(ERROR, f"{e.error} {message}")


def warning(message: str) -> Layout:
    return _simple(WARNING, f"{e.warning} {message}")


def info(message: str) -> Layout:
    return _simple(ACCENT, f"{e.info} {message}")


def loading(message: str = "Working on it...") -> Layout:
    return _simple(ACCENT, f"{e.loading} {message}")


def build(
    *,
    title: str | None = None,
    body: str | None = None,
    fields: list[tuple[str, str]] | None = None,
    thumbnail_url: str | None = None,
    colour: discord.Colour = ACCENT,
    rows: list[ui.ActionRow] | None = None,
) -> Layout:
    c = container(colour)

    if title and thumbnail_url:
        sec = ui.Section(ui.TextDisplay(title))
        sec.accessory = ui.Thumbnail(thumbnail_url)
        c.add_item(sec)
    elif title:
        c.add_item(text(title))

    if body:
        if title:
            c.add_item(sep())
        c.add_item(text(body))

    if fields:
        c.add_item(sep(divider=False))
        for label, value in fields:
            c.add_item(text(f"**{label}**\n{value}"))

    if rows:
        c.add_item(sep(divider=False))
        for row in rows:
            c.add_item(row)

    return Layout(c)
