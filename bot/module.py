from __future__ import annotations

import inspect

from discord.ext import commands

from bot import Bot


class Module(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
