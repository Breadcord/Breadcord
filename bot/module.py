from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from bot.__main__ import Bot


class Module(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
